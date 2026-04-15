# extractor/parsers/energiaxxi.py
# Modificado: 2026-04-14 | Rodrigo Costa
#   - extraer_precios_energia(): fix PVPC — pe_p1 = importe_total / consumo_total
#                                quando hay "Costes de la energía" sin precio/kWh
#   - extraer_descuentos(): hereda BaseParser (sin descuentos en esta factura)

import re
from typing import Optional
from .base_parser import BaseParser
from ..base import norm, fmt_date

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
        from datetime import datetime
        dia  = int(m.group(1))
        mes  = MESES.get(m.group(2).lower())
        anio = int(m.group(3))
        if mes:
            return fmt_date(datetime(anio, mes, dia))
    return None


class EnergiaXXIParser(BaseParser):

    def extraer_comercializadora(self) -> Optional[str]:
        m = re.search(
            r"(Energ[ií]a\s+XXI\s+Comercializadora\s+de\s+Referencia\s+S\.L\.U\.?)",
            self.text, re.IGNORECASE
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
            self.raw["comercializadora"] = m.group(0)[:80]
            return val
        return super().extraer_comercializadora()

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
                self.raw["periodo_inicio"] = m.group(0)[:80]
                self.raw["periodo_fin"]    = m.group(0)[:80]
                return inicio, fin
        return super().extraer_periodo()

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        acumulado = {
            "p1": {"dias": 0.0, "valor": 0.0, "raw": ""},
            "p2": {"dias": 0.0, "valor": 0.0, "raw": ""},
        }

        patron = re.compile(
            r'P([13])\s*\([^)]+\)\s+'
            r'([0-9,\.]+)\s*kW\s*[x×]\s*([0-9,\.]+)\s*Eur/kW\s*y\s*a[ñn]o\s*[x×]\s*'
            r'\(\s*([0-9]+)\s*/\s*365\s*\)\s*d[ií]as?',
            re.IGNORECASE
        )

        for m in patron.finditer(self.text):
            periodo_pdf = m.group(1)
            chave = "p1" if periodo_pdf == "1" else "p2"
            try:
                precio_anual = float(norm(m.group(3)))
                dias         = float(m.group(4))
                precio_dia   = precio_anual / 365
                acumulado[chave]["valor"] += precio_dia * dias
                acumulado[chave]["dias"]  += dias
                acumulado[chave]["raw"]    = m.group(0)[:80]
            except (ValueError, TypeError):
                pass

        pp1 = pp2 = None
        for chave, campo in [("p1", "pp_p1"), ("p2", "pp_p2")]:
            acc = acumulado[chave]
            if acc["dias"] > 0:
                media = round(acc["valor"] / acc["dias"], 6)
                self.fields[campo] = media
                self.raw[campo]    = acc["raw"]
                val = str(media)
                if chave == "p1":
                    pp1 = val
                else:
                    pp2 = val
                print(f"  ✅  {campo:<26} = {media:<20} ← EnergiaXXI potencia {chave} (média ponderada)")

        if not pp1 and not pp2:
            return super().extraer_precios_potencia()

        return pp1, pp2

    def extraer_precios_energia(self) -> None:
        """
        EnergíaXXI PVPC: la factura desglosa los peajes de energía en
        sub-períodos con kWh y €/kWh explícitos por período.

        Aplica media ponderada por período:
            pe_p1 = suma(€ subperíodos P1) / suma(kWh subperíodos P1)
            pe_p2 = suma(€ subperíodos P2) / suma(kWh subperíodos P2)
            pe_p3 = suma(€ subperíodos P3) / suma(kWh subperíodos P3)

        "Costes de la energía" (OMIE) no se captura — no tiene precio/kWh.
        Si no es PVPC, delega al BaseParser.
        """
        es_pvpc = bool(re.search(r"PVPC|Mercado\s+Regulado", self.text, re.IGNORECASE))
        if not es_pvpc:
            super().extraer_precios_energia()
            return

        # Patrón: "P1 (punta) 79,760 kWh x 0,092539 Eur/kWh"
        patron = re.compile(
            r'P([1-3])\s*\([^)]+\)\s*([0-9]+[,\.][0-9]+)\s*kWh\s*[x×]\s*'
            r'([0-9]+[,\.][0-9]+)\s*(?:€|Eur)/kWh',
            re.IGNORECASE
        )

        acumulado = {}
        for m in patron.finditer(self.text):
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

    def extraer_imp_ele(self) -> Optional[str]:
        for linha in self.linhas:
            l = linha.lower()
            if "impuesto electricidad" not in l:
                continue
            m = re.search(
                r"[0-9,\.]+\s*Eur\s*[xX×]\s*([0-9]+[,\.][0-9]+)\s*%",
                linha, re.IGNORECASE
            )
            if m:
                val = norm(m.group(1))
                try:
                    if 0.5 <= float(val) <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass
        return super().extraer_imp_ele()

    def extraer_iva(self) -> Optional[str]:
        for linha in self.linhas:
            if "iva" not in linha.lower():
                continue
            m = re.search(r"IVA[^0-9]{0,20}(\d+)\s*%", linha, re.IGNORECASE)
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)
        return super().extraer_iva()

    def extraer_alquiler(self) -> Optional[str]:
        for linha in self.linhas:
            if "alquiler" not in linha.lower():
                continue
            m = re.search(
                r"[0-9]+\s*d[ií]as?\s*[x×]\s*([0-9]+[,\.][0-9]+)\s*Eur/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))
        return super().extraer_alquiler()

    def extraer_bono_social(self) -> Optional[str]:
        for linha in self.linhas:
            if "bono social" not in linha.lower():
                continue
            m = re.search(
                r"[0-9]+\s*d[ií]as?\s*[x×]\s*([0-9]+[,\.][0-9]+)\s*Eur/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["bono_social"] = linha[:80]
                return norm(m.group(1))
        return super().extraer_bono_social()

    def extraer_potencias_contratadas(self) -> dict:
        result = {}
        m = re.search(
            r"[Pp]otencia\s+contratada\s+en\s+punta[^:]*:\s*([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))

        m = re.search(
            r"[Pp]otencia\s+contratada\s+en\s+valle[^:]*:\s*([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))

        return result or super().extraer_potencias_contratadas()

    def extraer_consumos(self) -> dict:
        """
        EnergíaXXI: "Consumo en P1: 144,00 kWh / Consumo en P2: 213,00 kWh / Consumo en P3: 601,00 kWh"
        """
        result = {}

        patron = re.compile(
            r'[Cc]onsumo\s+en\s+P([1-3])\s*:\s*([0-9]+[,\.][0-9]*)\s*kWh',
            re.IGNORECASE
        )
        for m in patron.finditer(self.text):
            try:
                periodo = int(m.group(1))
                campo   = f"consumo_p{periodo}_kwh"
                if campo not in result:
                    result[campo] = float(norm(m.group(2)))
            except (ValueError, TypeError):
                pass

        return result or super().extraer_consumos()
