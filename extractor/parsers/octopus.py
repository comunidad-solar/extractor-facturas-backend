# extractor/parsers/octopus.py
# Parser específico para facturas de Octopus Energy España.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias respecto al BaseParser:
#   - pp_p1/pp2: formato "X kW * N días PRECIO €/kW/día" (cubierto en base)
#   - imp_ele: formato "BASE € X,XX %" (cubierto en base)
#   - extraer_precios_energia(): líneas "Punta/Llano/Valle X kWh Y €/kWh Z €"
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from .base_parser import BaseParser


class OctopusParser(BaseParser):

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Formato Octopus:
          "Punta    79,70 kWh    0,114 €/kWh    9,15 €"
          "Llano    83,16 kWh    0,116 €/kWh    9,55 €"
          "Valle    122,91 kWh   0,115 €/kWh    14,11 €"
        Solo captura la línea principal — ignora sub-líneas de peajes/cargos/margen.
        """
        mapeo = {
            "punta": "pe_p1",
            "llano": "pe_p2",
            "valle": "pe_p3",
        }
        patron = re.compile(
            r'^(punta|llano|valle)\s+'
            r'[\d.,]+\s*kWh\s+'
            r'(\d+[.,]\d+)\s*€/kWh',
            re.IGNORECASE | re.MULTILINE
        )
        for match in patron.finditer(self.text):
            label  = match.group(1).lower()
            precio = float(match.group(2).replace(",", "."))
            campo  = mapeo.get(label)
            if campo and campo not in self.fields:
                self.fields[campo] = precio
                self.raw[campo]    = match.group(0)[:80]
                print(f"  ✅  {campo:<26} = {precio:<20} ← {label} {precio} €/kWh")
