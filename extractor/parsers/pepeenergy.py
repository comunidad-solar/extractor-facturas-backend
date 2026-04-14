# extractor/parsers/pepeenergy.py
# Parser para facturas de Energía Colectiva SL (PepeEnergy).
# PDF basado en imagen — el texto proviene de OCR (Tesseract).
# Sobrescribe 5 métodos porque el formato difiere del BaseParser:
#
#   extraer_cups():             CUPS puede tener O/0 confundidos por OCR — regex flexible
#   extraer_periodo():          usa fecha emisión - días facturados para inferir período exacto
#                               Fallback 1: fecha emisión - 30 días
#                               Fallback 2: infiere inicio=día 1 y fin=último día del mes mencionado
#   extraer_comercializadora(): captura "Energía Colectiva SL" del pie de página
#   extraer_precios_potencia(): formato "X €/kW·mes" → divide entre días del mes
#   extraer_alquiler():         formato explícito "0,02663 €/día" — BaseParser debería capturar,
#                               pero OCR puede alterar el texto, así que se sobrescribe por seguridad
#
# Modificado: 2026-03-03 | Rodrigo Costa
#   - extraer_periodo(): cambiado de inferir mes completo a usar fecha emisión - días facturados

import re
import calendar
from datetime import datetime, timedelta
from typing import Optional

from ..base import norm, fmt_date
from .base_parser import BaseParser

# Meses en español → número
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


class PepeEnergyParser(BaseParser):

    # ── CUPS ──────────────────────────────────────────────────────────────────

    def extraer_cups(self) -> Optional[str]:
        """
        OCR puede confundir O y 0 — la corrección ya se aplicó en __init__.py,
        pero el regex acepta O como fallback por si queda algún caso residual.
        """
        m = re.search(r"(ES[A-Z0-9]{16,22})", self.text, re.IGNORECASE)
        if m:
            cups = m.group(1).upper()
            prefijo    = cups[:20].replace("O", "0")
            sufijo     = cups[20:]
            cups_fixed = prefijo + sufijo
            self.raw["cups"] = m.group(0)[:80]
            return cups_fixed
        return super().extraer_cups()

    # ── PERÍODO ───────────────────────────────────────────────────────────────

    def extraer_periodo(self) -> tuple[Optional[str], Optional[str]]:
        """
        PepeEnergy no incluye fechas exactas — solo el mes: "Factura de la luz de abril 2025"
        Estrategia principal: usar "Fecha emisión" y restar los días facturados.
        Fallback 1: fecha emisión - 30 días (si no se encuentran días del alquiler).
        Fallback 2: inferir inicio=día 1 y fin=último día del mes mencionado.
        """
        # Intentar extraer fecha de emisión
        fecha_emision = None
        m_emision = re.search(
            r"[Ff]echa\s+emisi[oó]n\s*[:\-]?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})",
            self.text, re.IGNORECASE
        )
        if m_emision:
            dia, mes, anio = m_emision.group(1), m_emision.group(2), m_emision.group(3)
            if len(anio) == 2:
                anio = "20" + anio
            try:
                fecha_emision = datetime(int(anio), int(mes), int(dia))
            except ValueError:
                pass

        # Intentar extraer días facturados del alquiler: "0,02663 €/día x 30"
        dias = 30  # fallback
        m_dias = re.search(
            r"€/d[ií]a\s*[x×*]\s*(\d+)",
            self.text, re.IGNORECASE
        )
        if m_dias:
            try:
                dias = int(m_dias.group(1))
            except ValueError:
                pass

        if fecha_emision:
            fin    = fecha_emision
            inicio = fecha_emision - timedelta(days=dias)
            match  = f"Fecha emisión {fecha_emision.strftime('%d/%m/%Y')} - {dias} días"
            self.raw["periodo_inicio"] = match
            self.raw["periodo_fin"]    = match
            return fmt_date(inicio), fmt_date(fin)

        # Fallback: inferir desde "Factura de la luz de abril 2025"
        m = re.search(
            r"[Ff]actura\s+de\s+la\s+luz\s+de\s+([a-záéíóú]+)\s+(\d{4})",
            self.text, re.IGNORECASE
        )
        if m:
            mes_str = m.group(1).lower()
            anio    = int(m.group(2))
            mes_num = MESES.get(mes_str)
            if mes_num:
                ultimo_dia = calendar.monthrange(anio, mes_num)[1]
                inicio = fmt_date(datetime(anio, mes_num, 1))
                fin    = fmt_date(datetime(anio, mes_num, ultimo_dia))
                match  = m.group(0)[:80]
                self.raw["periodo_inicio"] = match
                self.raw["periodo_fin"]    = match
                return inicio, fin

        return super().extraer_periodo()

    # ── COMERCIALIZADORA ──────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        Nombre legal: "Energía Colectiva SL"
        Aparece en el pie de página 1: "Factura emitida en Valéncia por Energía Colectiva SL"
        """
        m = re.search(
            r"(Energ[ií]a\s+Colectiva\s+S\.?L\.?U?\.?)",
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
        Formato: "Periodo P1 (Punta) — 2,244213 €/kW·mes x 4,3 kW"
        Precio en €/kW/mes → dividir entre días del mes para obtener €/kW/día.
        Los días del mes se obtienen del período ya extraído, o se usa 30 como fallback.
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        dias_mes = self._dias_mes()

        for linha in self.linhas:
            if not re.search(r"€/kW[·\-]?mes", linha, re.IGNORECASE):
                continue

            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€/kW[·\-]?mes",
                linha, re.IGNORECASE
            )
            if not m:
                continue

            try:
                precio_mes = float(norm(m.group(1)))
                precio_dia = round(precio_mes / dias_mes, 6)
                precio_str = str(precio_dia)
            except ValueError:
                continue

            if re.search(r"\bP1\b|[Pp]unta", linha) and pp1 is None:
                pp1  = precio_str
                src1 = linha[:80]
            elif re.search(r"\bP2\b|[Vv]alle", linha) and pp2 is None:
                pp2  = precio_str
                src2 = linha[:80]

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    def _dias_mes(self) -> int:
        """
        Calcula los días del mes a partir de periodo_inicio ya guardado.
        Fallback: 30 días.
        """
        inicio = self.fields.get("periodo_inicio")
        if inicio:
            try:
                dt = datetime.strptime(inicio, "%d/%m/%Y")
                return calendar.monthrange(dt.year, dt.month)[1]
            except ValueError:
                pass
        return 30

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato OCR: "Alquiler contador 0,02663 €/día x 30"
        El BaseParser debería capturarlo, pero el OCR puede alterar
        "contador" vs "equipos de medida" — se sobrescribe con keyword ampliado.
        """
        for linha in self.linhas:
            l = linha.lower()
            if not any(x in l for x in ["alquiler", "contador", "equipo", "medida"]):
                continue

            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))

        return super().extraer_alquiler()

    def extraer_potencias_contratadas(self) -> dict:
        """
        PepeEnergy: "Potencia contratada en P1 (Punta): 4,3 kW"
                    "Potencia contratada en P2 (Valle): 4,3 kW"
        """
        result = {}
        for p in range(1, 3):
            m = re.search(
                rf"[Pp]otencia\s+contratada\s+en\s+P{p}[^0-9]*([0-9,\.]+)\s*kW",
                self.text, re.IGNORECASE
            )
            if m:
                result[f"pot_p{p}_kw"] = float(norm(m.group(1)))
        return result or super().extraer_potencias_contratadas()

    def extraer_descuentos(self) -> dict:
        """
        PepeEnergy: "Descuento cliente Pepephone  -3,14 €"
        Línea con valor negativo explícito.
        """
        resultado = {}

        for linha in self.linhas:
            l = linha.lower()
            if "descuento" not in l and "cuota" not in l:
                continue
            if "financiaci" in l or "impuesto" in l or "bono social" in l:
                continue

            valores_negativos = re.findall(
                r"-\s*([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if valores_negativos:
                try:
                    valor = abs(float(norm(valores_negativos[-1])))
                    if 0.01 <= valor <= 99999:
                        nombre = re.split(r"[\d€\-\*]", linha)[0].strip()
                        nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,: ")
                        if len(nombre) >= 3:
                            resultado[nombre] = round(valor, 6)
                            self.raw[f"descuento_{nombre[:20]}"] = linha[:80]
                            print(f"  ✅  {'descuento':<26} = {valor:<20} ← {nombre}")
                except (ValueError, TypeError):
                    pass

        base = super().extraer_descuentos()
        for k, v in base.items():
            if k not in resultado:
                resultado[k] = v

        return resultado