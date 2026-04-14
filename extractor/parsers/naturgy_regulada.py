# extractor/parsers/naturgy_regulada.py
# Modificado: 2026-04-14 | Rodrigo Costa
#   - extraer_precios_energia(): fix PVPC — pe_p1 = importe_total / consumo_total
#   - extraer_descuentos(): captura "Descuento por Bono Social" con valor absoluto

import re
from typing import Optional

from ..base import norm, fmt_date
from .base_parser import BaseParser

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


def _fecha_extenso(texto: str) -> Optional[str]:
    m = re.search(
        r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})",
        texto, re.IGNORECASE
    )
    if m:
        dia  = int(m.group(1))
        mes  = MESES.get(m.group(2).lower())
        anio = int(m.group(3))
        if mes:
            from datetime import datetime
            return fmt_date(datetime(anio, mes, dia))
    return None


class NaturgyReguladaParser(BaseParser):

    def extraer_periodo(self) -> tuple[Optional[str], Optional[str]]:
        patron = (
            r"(\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})"
            r"\s+a\s+"
            r"(\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})"
        )
        m = re.search(patron, self.text, re.IGNORECASE)
        if m:
            inicio = _fecha_extenso(m.group(1))
            fin    = _fecha_extenso(m.group(2))
            if inicio and fin:
                match = m.group(0)[:80]
                self.raw["periodo_inicio"] = match
                self.raw["periodo_fin"]    = match
                return inicio, fin
        return super().extraer_periodo()

    def extraer_comercializadora(self) -> Optional[str]:
        m = re.search(
            r"(Comercializadora\s+Regulada\s*,?\s*Gas\s*&\s*Power\s*,?\s*S\.A\.?)",
            self.text, re.IGNORECASE
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
            self.raw["comercializadora"] = m.group(0)[:80]
            return val
        return super().extraer_comercializadora()

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        pp1 = pp2 = None
        src1 = src2 = ""

        for linha in self.linhas:
            if not re.search(r"€/kW\s*y\s*a[ñn]o", linha, re.IGNORECASE):
                continue
            if "margen" in linha.lower():
                continue

            m = re.search(
                r"[0-9,\.]+\s*kW\s*\*\s*([0-9]+[,\.][0-9]+)\s*€/kW\s*y\s*a[ñn]o",
                linha, re.IGNORECASE
            )
            if not m:
                continue

            try:
                precio_anual = float(norm(m.group(1)))
                precio_dia   = round(precio_anual / 365, 6)
                precio_str   = str(precio_dia)
            except ValueError:
                continue

            if re.search(r"\bP1\b|punta", linha, re.IGNORECASE) and pp1 is None:
                pp1  = precio_str
                src1 = linha[:80]
            elif re.search(r"\bP2\b|valle", linha, re.IGNORECASE) and pp2 is None:
                pp2  = precio_str
                src2 = linha[:80]

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    def extraer_precios_energia(self) -> None:
        es_pvpc = bool(re.search(r"PVPC|Mercado\s+Regulado", self.text, re.IGNORECASE))
        if not es_pvpc:
            super().extraer_precios_energia()
            return

        corte = re.search(r"excede\s+el\s+l.mite", self.text, re.IGNORECASE)
        texto = self.text[:corte.start()] if corte else self.text

        patron_peaje = re.compile(
            r'P([1-3])\s*\([^)]+\)\s*:\s*([0-9]+(?:[,\.][0-9]+)?)\s*kWh\s*[x×\*]\s*'
            r'([0-9]+[,\.][0-9]+)\s*(?:€|Eur)/kWh',
            re.IGNORECASE
        )

        acumulado = {}
        for m in patron_peaje.finditer(texto):
            try:
                periodo = int(m.group(1))
                kwh     = float(norm(m.group(2)))
                precio  = float(norm(m.group(3)))
                eur     = kwh * precio

                if periodo not in acumulado:
                    acumulado[periodo] = {"kwh": 0.0, "eur": 0.0, "count": 0}
                acumulado[periodo]["kwh"]   += kwh
                acumulado[periodo]["eur"]   += eur
                acumulado[periodo]["count"] += 1
            except (ValueError, TypeError):
                pass

        if acumulado:
            for periodo, acc in acumulado.items():
                if acc["kwh"] > 0:
                    precio = round(acc["eur"] / acc["kwh"], 6)
                    campo  = f"pe_p{periodo}"
                    self.fields[campo] = precio
                    self.raw[campo]    = f"media ponderada {acc['count']} subperiodos"
                    print(f"  ✅  {campo:<26} = {precio:<20} ← media ponderada peajes ({acc['count']} subperíodos)")
            return

        super().extraer_precios_energia()

    def extraer_potencias_contratadas(self) -> dict:
        result = {}
        m = re.search(r"punta[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))
        m = re.search(r"valle[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))

        if not result:
            for p in range(1, 3):
                m = re.search(
                    rf"P{p}\s*\([^)]+\)\s*:\s*([0-9,\.]+)\s*kW",
                    self.text, re.IGNORECASE
                )
                if m:
                    result[f"pot_p{p}_kw"] = float(norm(m.group(1)))

        return result or super().extraer_potencias_contratadas()

    def extraer_alquiler(self) -> Optional[str]:
        """
        NaturgyRegulada: texto concatenado pelo pdfplumber.
        Formato: "Alquilerdelcontador: 26días*0,026630€/día"
        O BaseParser falha porque espera espaços entre os tokens.
        """
        for linha in self.linhas:
            if "alquiler" not in linha.lower():
                continue

            # Formato concatenado: "Nd[ií]as*PRECIO€/d[ií]a"
            m = re.search(
                r"[0-9]+\s*d[ií]as?\s*\*\s*([0-9]+[,\.][0-9]+)\s*[€e]\s*/\s*d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))

            # Formato con espacios — fallback al BaseParser
        return super().extraer_alquiler()

    def extraer_iva(self) -> Optional[str]:
        for linha in self.linhas:
            l = linha.lower()
            if "i.v.a" not in l and "iva" not in l:
                continue
            m = re.search(r"\b(10|21)\s*%", linha, re.IGNORECASE)
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)
        return super().extraer_iva()

    def extraer_descuentos(self) -> dict:
        """
        NaturgyRegulada: "Descuento por Bono Social: 69,63 € * -42,5% ... -29,59 €"
        Captura el valor absoluto del importe final del descuento.
        """
        resultado = {}

        for linha in self.linhas:
            l = linha.lower()
            if "descuento" not in l:
                continue
            if "financiaci" in l or "impuesto" in l:
                continue

            # Buscar valor negativo final: "-29,59 €"
            valores_negativos = re.findall(
                r"-\s*([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if valores_negativos:
                try:
                    valor = abs(float(norm(valores_negativos[-1])))
                    if 0.01 <= valor <= 99999:
                        nombre = re.split(r"[\d€\-\*\:]", linha)[0].strip()
                        nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,: ")
                        if len(nombre) >= 3:
                            # Normalizar nome para comparação (remove espaços e lowercase)
                            nombre_norm = re.sub(r"\s+", "", nombre.lower())
                            ja_existe = any(
                                re.sub(r"\s+", "", k.lower()) == nombre_norm
                                or abs(v - round(valor, 6)) < 0.01
                                for k, v in resultado.items()
                            )
                            if not ja_existe:
                                resultado[nombre] = round(valor, 6)
                                self.raw[f"descuento_{nombre[:20]}"] = linha[:80]
                                print(f"  ✅  {'descuento':<26} = {valor:<20} ← {nombre}")
                except (ValueError, TypeError):
                    pass

        # Complementar con BaseParser aplicando mesma deduplicação
        base = super().extraer_descuentos()
        for k, v in base.items():
            k_norm = re.sub(r"\s+", "", k.lower())
            ja_existe = any(
                re.sub(r"\s+", "", r.lower()) == k_norm
                or abs(rv - v) < 0.01
                for r, rv in resultado.items()
            )
            if not ja_existe:
                resultado[k] = v

        return resultado
