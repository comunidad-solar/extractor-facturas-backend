# extractor/parsers/endesa.py
# Parser específico para facturas de Endesa Energía.
# Sobrescribe los métodos con comportamiento diferente al genérico.
#
# Particularidades de Endesa:
#   - imp_ele: la factura tiene una sección "DESTINO DEL IMPORTE" con "11,24% Impuestos"
#     que el BaseParser captura incorrectamente. El valor real está en la línea
#     "Impuesto electricidad ( BASE Eur X PORCENTAJE %)" dentro del DETALLE DE FACTURA.
#     Además, el IVA puede estar reducido al 10% (RDL 8/2023) pero el PDF también
#     contiene IVA 21% de la factura Endesa X Servicios (servicio adicional) — hay
#     que capturar el IVA de la factura principal (Endesa Energía), no el de servicios.
#   - imp_ele posibles valores: 5.11269632% (normal), 2.5% (reducido RDL 8/2023)
#   - iva posibles valores: 21% (desde 2025), 10% (reducido 2023-2024), 5% (Canarias)
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from .base_parser import BaseParser
from ..base import norm


class EndesaParser(BaseParser):

    def extraer_imp_ele(self):
        """
        Endesa: "Impuesto electricidad ( 41,64 Eur X 2,5 %)"
        Solo se acepta la línea que contiene "impuesto electricidad" explícito.
        Se ignoran las líneas del bloque "DESTINO DEL IMPORTE" que comienzan con ">"
        (p.ej. "> 11,24% Impuestos") ya que representan porcentajes del total y no
        el impuesto eléctrico real.
        """
        for linha in self.linhas:
            l = linha.lower()

            # Ignorar líneas del bloque "DESTINO DEL IMPORTE" (comienzan con ">")
            if linha.strip().startswith(">"):
                continue

            # Solo líneas con "impuesto electricidad" explícito
            if "impuesto electricidad" not in l and "impuesto eléctrico" not in l:
                continue
            if "impuesto sobre el valor" in l:
                continue

            # "BASE Eur X PORCENTAJE %" — Endesa
            m = re.search(
                r"[0-9,\.]+\s*(?:Eur|€)\s*[xX×]\s*([0-9]+[,\.][0-9]+)\s*%",
                linha, re.IGNORECASE
            )
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

            # "X,XX % s/BASE" — formato alternativo
            m = re.search(r"([0-9]+[,\.][0-9]+)\s*%\s*s/[0-9]", linha, re.IGNORECASE)
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

            # "BASE € X,XX %" — formato genérico en línea de impuesto
            m = re.search(r"[0-9,\.]+\s*€\s+([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

        return None

    def extraer_iva(self):
        """
        Endesa: el PDF puede contener dos facturas — Endesa Energía (principal) y
        Endesa X Servicios (adicional). El IVA de la factura principal puede ser
        10% (reducido) o 21% (normal). El IVA de Endesa X Servicios es siempre 21%.
        Se captura el IVA que está asociado a la factura principal:
        buscar "IVA normal X%" o "IVA X% s/BASE" antes de la sección Endesa X.
        """
        en_endesa_x = False  # Flag para ignorar la sección Endesa X Servicios

        for linha in self.linhas:
            l = linha.lower()

            # Detectar inicio de la sección Endesa X Servicios
            if "factura endesa x" in l or "endesa x servicios" in l:
                en_endesa_x = True
                continue
            if en_endesa_x:
                continue  # Ignorar todo lo que viene después

            if "iva" not in l:
                continue

            # "IVA normal X% s/BASE" — Endesa Energía con IVA reducido
            m = re.search(
                r"IVA\s+normal\s+([0-9]+)[,\.]?[0-9]*\s*%",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)

            # "IVA X% s/BASE" o "IVA (X%)" — formato estándar
            for pat in [
                r"IVA[^0-9]{0,20}([1-9][0-9])[,\.]?[0-9]*\s*%",
                r"([1-9][0-9])[,\.]?[0-9]*\s*%[^0-9]{0,10}IVA",
                r"IVA[^\n]{0,30}?\s([1-9][0-9])[,\.][0-9]+\s*%",
            ]:
                m = re.search(pat, linha, re.IGNORECASE)
                if m:
                    self.raw["iva"] = linha[:80]
                    return m.group(1)

        return None