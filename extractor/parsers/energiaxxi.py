# extractor/parsers/energiaxxi.py
# Parser para facturas de Energía XXI Comercializadora de Referencia S.L.U.
# Comercializadora regulada PVPC (Grupo Endesa).
#
# Particularidades:
#   - periodo: por extenso "10 de diciembre de 2025 a 14 de enero de 2026"
#   - pp_p1/p2: formato "X kW x Y Eur/kW y año x (N/365) días" → Y/365
#               sub-períodos → média ponderada pelos días
#               P1=punta-llano, P3=valle (mapeado para pp_p2)
#   - pe_p1/p2/p3: "X kWh x Y Eur/kWh" → média ponderada por período
#                  (são peajes de transporte, não preço total de energia)
#   - imp_ele: "BASE Eur X PORCENTAJE %"
#   - iva: "IVA normal: 21 % s/ BASE"
#   - alq_eq_dia: "N días x Y Eur/día" — sub-períodos mesmo valor
#   - bono_social: "N días x Y Eur/día"
#   - pot_p1_kw/p2_kw: "Potencia contratada en punta-llano: X kW / valle: X kW"

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

    # ── COMERCIALIZADORA ──────────────────────────────────────────────────────

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

    # ── PERÍODO ───────────────────────────────────────────────────────────────

    def extraer_periodo(self) -> tuple[Optional[str], Optional[str]]:
        """
        Formato: "10 de diciembre de 2025 a 14 de enero de 2026"
        Também: "Periodo de consumo: DD de MES de YYYY a DD de MES de YYYY"
        """
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

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        Formato: "6,928 kW x 26,930550 Eur/kW y año x (21 /365 ) días"
        Preço em €/kW/año → dividir por 365.
        Sub-períodos → média ponderada pelos días.
        P1 (Punta-Llano) → pp_p1
        P3 (valle)       → pp_p2
        """
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
            periodo_pdf = m.group(1)  # "1" ou "3"
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

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Formato: "P1 (punta) 79,760 kWh x 0,092539 Eur/kWh"
        Sub-períodos → média ponderada por período.
        P1=punta → pe_p1, P2=llano → pe_p2, P3=valle → pe_p3.
        """
        acumulado = {
            1: {"kwh": 0.0, "valor": 0.0},
            2: {"kwh": 0.0, "valor": 0.0},
            3: {"kwh": 0.0, "valor": 0.0},
        }

        patron = re.compile(
            r'P([123])\s*\([^)]+\)\s+'
            r'([0-9,\.]+)\s*kWh\s*[x×]\s*([0-9,\.]+)\s*Eur/kWh',
            re.IGNORECASE
        )

        for m in patron.finditer(self.text):
            try:
                periodo = int(m.group(1))
                kwh     = float(norm(m.group(2)))
                precio  = float(norm(m.group(3)))
                acumulado[periodo]["kwh"]   += kwh
                acumulado[periodo]["valor"] += kwh * precio
                self.raw[f"pe_p{periodo}"]  = m.group(0)[:80]
            except (ValueError, TypeError):
                pass

        for periodo, acc in acumulado.items():
            if acc["kwh"] > 0:
                media = round(acc["valor"] / acc["kwh"], 6)
                campo = f"pe_p{periodo}"
                self.fields[campo] = media
                print(f"  ✅  {campo:<26} = {media:<20} ← EnergiaXXI peaje energía P{periodo} (média ponderada)")

    # ── IMPUESTO ELÉCTRICO ────────────────────────────────────────────────────

    def extraer_imp_ele(self) -> Optional[str]:
        """
        Formato: "Impuesto electricidad: ( 154,68 Eur X 5,1126963 %)"
        """
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

    # ── IVA ───────────────────────────────────────────────────────────────────

    def extraer_iva(self) -> Optional[str]:
        """
        Formato: "IVA normal: 21 % s/ 164,16"
        """
        for linha in self.linhas:
            if "iva" not in linha.lower():
                continue
            m = re.search(r"IVA[^0-9]{0,20}(\d+)\s*%", linha, re.IGNORECASE)
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)
        return super().extraer_iva()

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato: "Alquiler del contador: ( 21 días x 0,044712 Eur/día )"
        Sub-períodos com mesmo valor — pegar o primeiro.
        """
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

    # ── BONO SOCIAL ───────────────────────────────────────────────────────────

    def extraer_bono_social(self) -> Optional[str]:
        """
        Formato: "Financiación Bono Social 21 días x 0,012742 Eur/día x 1,000000"
        """
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

    # ── POTENCIAS CONTRATADAS ─────────────────────────────────────────────────

    def extraer_potencias_contratadas(self) -> dict:
        """
        Formato: "Potencia contratada en punta-llano: 6,928 kW
                  Potencia contratada en valle: 6,928 kW"
        """
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
