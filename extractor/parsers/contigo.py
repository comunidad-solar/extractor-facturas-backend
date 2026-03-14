# extractor/parsers/contigo.py
# Parser para facturas de Contigo Energía (Gesternova S.A.).
# Sobrescribe 5 métodos porque el formato de la factura difiere del BaseParser:
#
#   extraer_comercializadora(): captura "Gesternova S.A." del pie de página
#   extraer_precios_potencia(): formato "P1. Potencia facturada X kW PRECIO"
#   extraer_imp_ele():          factor decimal "0,051127" en línea "Impuesto Eléctrico"
#   extraer_iva():              "21" en tabla "Base Imponible 1 BASE 21 IMP TOTAL"
#   extraer_alquiler():         total €/período sin €/día explícito → fallback forzado
#
# Modificado: 2026-02-27 | Rodrigo Costa

import re
from typing import Optional

from ..base import norm, to_date
from .base_parser import BaseParser


class ContigoParser(BaseParser):

    # ── COMERCIALIZADORA ─────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        El nombre legal aparece en el pie de página:
        "Factura emitida en Madrid por Gesternova S.A., inscrito en..."
        """
        m = re.search(
            r"por\s+(Gesternova\s+S\.A\.)",
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
        Formato Contigo:
          "P1. Precio: 29,891661 X (30 / 366) = 2,450136 €/kW"  ← precio calculado
          "P1. Potencia facturada  6,900 kW  2,450136  16,91"    ← línea con el precio
        Se captura el precio de la línea "Potencia facturada" de cada período.
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        for linha in self.linhas:
            if "potencia facturada" not in linha.lower():
                continue

            # Extraer todos los números de la línea
            numeros = re.findall(r"[0-9]+[,\.][0-9]+", linha)
            if len(numeros) < 2:
                continue

            # Formato: "X,XXX kW  PRECIO  TOTAL" → segundo número es el precio €/kW
            try:
                precio = norm(numeros[1])
            except IndexError:
                continue

            if re.search(r"\bP1\b", linha, re.IGNORECASE) and pp1 is None:
                pp1 = precio
                src1 = linha[:80]
            elif re.search(r"\bP2\b", linha, re.IGNORECASE) and pp2 is None:
                pp2 = precio
                src2 = linha[:80]

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    # ── IMPUESTO ELÉCTRICO ────────────────────────────────────────────────────

    def extraer_imp_ele(self) -> Optional[str]:
        """
        Formato Contigo: "Impuesto Eléctrico  147,730  0,051127  7,55"
        El impuesto aparece como factor decimal (0,051127 = 5.1127%).
        """
        for linha in self.linhas:
            if "impuesto" not in linha.lower():
                continue
            if "eléctrico" not in linha.lower() and "electrico" not in linha.lower():
                continue
            if "impuesto sobre el valor" in linha.lower():
                continue

            # Factor decimal com vírgula: "BASE 0,0XXXXX TOTAL"
            m = re.search(r"\b(0[,\.][0-9]{4,})\b", linha)
            if m:
                try:
                    factor = float(norm(m.group(1)))
                    if 0.005 <= factor <= 0.1:
                        self.raw["imp_ele"] = linha[:80]
                        return str(round(factor * 100, 6))
                except ValueError:
                    pass

            # Fallback: porcentaje explícito razonable
            m = re.search(r"([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
            if m:
                try:
                    num = float(norm(m.group(1)))
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return norm(m.group(1))
                except ValueError:
                    pass

        return super().extraer_imp_ele()

    # ── IVA ──────────────────────────────────────────────────────────────────

    def extraer_iva(self) -> Optional[str]:
        """
        Formato Contigo: "Base Imponible 1  156,08  21  32,78  188,86"
        El IVA aparece como número entero en una tabla sin la palabra "IVA".
        Se busca la línea "Base Imponible" y se extrae el porcentaje (10 o 21).
        """
        for linha in self.linhas:
            if "base imponible" not in linha.lower():
                continue

            # Buscar 10 o 21 como entero en la línea
            m = re.search(r"\b(10|21)\b", linha)
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)

        return super().extraer_iva()

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato Contigo: "Importe alquiler equipo de medida  1  0,800000  0,80"
        No hay €/día explícito — el total es 0,80€ para el período completo.
        Se divide el total entre los días facturados.
        """
        dias = self._calcular_dias()

        for linha in self.linhas:
            if "alquiler" not in linha.lower():
                continue
            if "distribuidora" in linha.lower():
                continue

            # Buscar el importe total (último número de la línea)
            numeros = re.findall(r"[0-9]+[,\.][0-9]+", linha)
            if not numeros:
                continue

            try:
                total = float(norm(numeros[-1]))
                if 0.1 <= total <= 5.0 and dias > 0:
                    self.raw["alq_eq_dia"] = f"{linha[:55]} [calculado: {total}/{dias}]"
                    return str(round(total / dias, 6))
            except ValueError:
                pass

        return super().extraer_alquiler()