# extractor/parsers/cox.py
# Parser para facturas de Cox Energía Comercializadora España, S.L.U.
# Sobrescribe extraer_cups(), extraer_imp_ele(), extraer_alquiler() y
# extraer_precios_potencia() porque el layout de dos columnas de Cox
# fragmenta el texto de pdfplumber. Usa PyMuPDF (fitz) para acceder
# correctamente al contenido del PDF.
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - Añadido extraer_precios_potencia() para leer P1-P6 en tarifas 3.0TD

import re
import fitz
from typing import Optional

from ..base import norm
from .base_parser import BaseParser


class CoxParser(BaseParser):

    def __init__(self, text: str, pdf_path: str = ""):
        super().__init__(text)
        self.pdf_path = pdf_path

    # ── COMERCIALIZADORA ──────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        m = re.search(
            r"(COX\s+ENERG[ÍI]A\s+COMERCIALIZADORA\s+ESPA[ÑN]A\s*,?\s*S\.L\.U\.?)",
            self.text, re.IGNORECASE
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
            self.raw["comercializadora"] = m.group(0)[:80]
            return val
        return super().extraer_comercializadora()

    # ── CUPS ──────────────────────────────────────────────────────────────────

    def extraer_cups(self) -> Optional[str]:
        """
        Usa PyMuPDF (fitz) para extraer el CUPS porque pdfplumber fragmenta
        el texto en este layout de dos columnas con rodapié rotado.
        """
        if not self.pdf_path:
            return super().extraer_cups()

        try:
            doc = fitz.open(self.pdf_path)
            fitz_text = doc[0].get_text()
            doc.close()

            for linha in fitz_text.splitlines():
                m = re.search(r"CUPS\s*:\s*(ES[A-Z0-9]{16,24})", linha, re.IGNORECASE)
                if m:
                    self.raw["cups"] = linha.strip()[:80]
                    return m.group(1)

        except Exception as e:
            print(f"  ⚠️  CoxParser.extraer_cups — error con fitz: {e}")

        return super().extraer_cups()

    # ── IMPUESTO ELÉCTRICO ────────────────────────────────────────────────────

    def extraer_imp_ele(self) -> Optional[str]:
        """
        Usa fitz para leer el texto completo y buscar el porcentaje.
        Formato Cox: "Impuesto de Electricidad (5,11269632% s/2.150,23 €):"
        """
        if not self.pdf_path:
            return super().extraer_imp_ele()

        try:
            doc = fitz.open(self.pdf_path)
            fitz_full = ""
            for page in doc:
                fitz_full += page.get_text() + "\n"
            doc.close()

            for linha in fitz_full.splitlines():
                l = linha.lower()
                if "impuesto de electricidad" not in l and "impuesto electricidad" not in l:
                    continue
                if "impuesto sobre el valor" in l:
                    continue

                m = re.search(r"\(?\s*([0-9]+[,\.][0-9]+)\s*%\s*s/[0-9]", linha, re.IGNORECASE)
                if m:
                    self.raw["imp_ele"] = linha.strip()[:80]
                    return norm(m.group(1))

                m = re.search(r"([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
                if m:
                    try:
                        num = float(norm(m.group(1)))
                        if 0.5 <= num <= 15:
                            self.raw["imp_ele"] = linha.strip()[:80]
                            return norm(m.group(1))
                    except ValueError:
                        pass

        except Exception as e:
            print(f"  ⚠️  CoxParser.extraer_imp_ele — error con fitz: {e}")

        return super().extraer_imp_ele()

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Usa fitz para leer la página 2 donde está el desglose del alquiler.
        "Alquiler de contador" aparece en una línea y el valor en la siguiente:
            'Alquiler de contador'
            '31 días * 0,009534 €/día'
        """
        if not self.pdf_path:
            return super().extraer_alquiler()

        try:
            doc = fitz.open(self.pdf_path)
            page2_lines = doc[1].get_text().splitlines()
            doc.close()

            for i, linha in enumerate(page2_lines):
                if "alquiler de contador" not in linha.lower():
                    continue
                for j in range(i + 1, min(i + 6, len(page2_lines))):
                    m = re.search(
                        r"[0-9]+\s*d[ií]as?\s*[x×*]\s*([0-9]+[,\.][0-9]+)\s*€?/d[ií]a",
                        page2_lines[j], re.IGNORECASE
                    )
                    if m:
                        self.raw["alq_eq_dia"] = page2_lines[j].strip()[:80]
                        return norm(m.group(1))

        except Exception as e:
            print(f"  ⚠️  CoxParser.extraer_alquiler — error con fitz: {e}")

        return super().extraer_alquiler()

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        Usa fitz para leer el desglose de potencia.
        Formato Cox: "P1 80,00 kW * 0,053859 €/kW * (31/365) días"
        El precio ya viene en €/kW/día — no requiere conversión.
        Extrae P1-P6 y almacena P3-P6 directamente en fields.
        Devuelve (pp_p1, pp_p2) por compatibilidad con BaseParser.
        """
        if not self.pdf_path:
            return super().extraer_precios_potencia()

        try:
            doc = fitz.open(self.pdf_path)
            fitz_full = ""
            for page in doc:
                fitz_full += page.get_text() + "\n"
            doc.close()

            precios = {}
            for linha in fitz_full.splitlines():
                m = re.match(
                    r"P([1-6])\s+[0-9,\.]+\s*kW\s*\*\s*([0-9]+[,\.][0-9]+)\s*€/kW",
                    linha.strip(), re.IGNORECASE
                )
                if m:
                    periodo = int(m.group(1))
                    precio  = norm(m.group(2))
                    if periodo not in precios:  # tomar solo el primero por período
                        precios[periodo] = (precio, linha.strip()[:80])

            # Almacenar P3-P6 directamente en fields
            for p in [3, 4, 5, 6]:
                if p in precios:
                    self.fields[f"pp_p{p}"] = precios[p][0]
                    self.raw[f"pp_p{p}"]    = precios[p][1]

            if 1 in precios:
                self.raw["pp_p1"] = precios[1][1]
            if 2 in precios:
                self.raw["pp_p2"] = precios[2][1]

            pp1 = precios[1][0] if 1 in precios else None
            pp2 = precios[2][0] if 2 in precios else None
            return pp1, pp2

        except Exception as e:
            print(f"  ⚠️  CoxParser.extraer_precios_potencia — error con fitz: {e}")

        return super().extraer_precios_potencia()