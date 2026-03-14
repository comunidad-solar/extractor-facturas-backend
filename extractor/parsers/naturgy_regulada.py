# extractor/parsers/naturgy_regulada.py
# Parser para facturas de Comercializadora Regulada, Gas & Power, S.A. (Grupo Naturgy).
# Sobrescribe 4 métodos porque el formato difiere del BaseParser:
#
#   extraer_periodo():          fechas por extenso "8 de julio de 2025 a 3 de agosto de 2025"
#   extraer_comercializadora(): captura "Comercializadora Regulada, Gas & Power, S.A."
#   extraer_precios_potencia(): formato "X kW * Y €/kW y año * (N/365) días" → calcula Y/365
#   extraer_iva():              "I.V.A." con puntos — "iva" not in "i.v.a." en BaseParser
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - extraer_precios_potencia(): \s+ → \s* en filtro y regex para texto concatenado sin espacios

import re
from typing import Optional

from ..base import norm, fmt_date
from .base_parser import BaseParser

# Meses en español → número
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


def _fecha_extenso(texto: str) -> Optional[str]:
    """
    Convierte "8 de julio de 2025" → "08/07/2025".
    Devuelve None si no hace match.
    """
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

    # ── PERÍODO ───────────────────────────────────────────────────────────────

    def extraer_periodo(self) -> tuple[Optional[str], Optional[str]]:
        """
        Formato: "8 de julio de 2025 a 3 de agosto de 2025"
        También intenta el BaseParser por si hay otra línea con formato DD/MM/YYYY.
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
                match = m.group(0)[:80]
                self.raw["periodo_inicio"] = match
                self.raw["periodo_fin"]    = match
                return inicio, fin

        return super().extraer_periodo()

    # ── COMERCIALIZADORA ──────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        Nombre legal: "Comercializadora Regulada, Gas & Power, S.A."
        Aparece en el encabezado de la página 1.
        """
        m = re.search(
            r"(Comercializadora\s+Regulada\s*,?\s*Gas\s*&\s*Power\s*,?\s*S\.A\.?)",
            self.text, re.IGNORECASE
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
            self.raw["comercializadora"] = m.group(0)[:80]
            return val
        return super().extraer_comercializadora()

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        Formato pdfplumber (texto concatenado sin espacios):
            "P1(punta): 9,900kW*26,930550€/kWyaño*(26/365)días"
        El precio está en €/kW/año → se divide entre 365 para obtener €/kW/día.
        Se ignoran líneas de "margen de comercialización" que tienen el mismo formato.
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        for linha in self.linhas:
            # Filtro: solo líneas con precio anual — \s* cubre texto concatenado
            if not re.search(r"€/kW\s*y\s*a[ñn]o", linha, re.IGNORECASE):
                continue

            # Ignorar línea de margen de comercialización
            if "margen" in linha.lower():
                continue

            # Capturar precio anual: "X kW * PRECIO €/kW y año"
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

    # ── IVA ───────────────────────────────────────────────────────────────────

    def extraer_iva(self) -> Optional[str]:
        """
        Formato: "I.V.A.: 21% s/ 49,26 €"
        El BaseParser falla porque busca "iva" como substring y "i.v.a." no lo contiene.
        """
        for linha in self.linhas:
            l = linha.lower()
            if "i.v.a" not in l and "iva" not in l:
                continue

            m = re.search(r"\b(10|21)\s*%", linha, re.IGNORECASE)
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)

        return super().extraer_iva()