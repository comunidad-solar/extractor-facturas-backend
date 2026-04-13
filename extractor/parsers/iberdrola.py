# extractor/parsers/iberdrola.py
# Parser específico para facturas de Iberdrola Clientes.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias conocidas respecto al BaseParser:
#   - imp_ele: formato "X% s/BASE" (cubierto en base)
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from typing import Optional
from ..base import norm
from .base_parser import BaseParser


class IberdrolaParser(BaseParser):

    def extraer_potencias_contratadas(self) -> dict:
        """
        Iberdrola: "Potencia punta: 4 kW / Potencia valle: 2 kW"
        """
        result = {}
        m = re.search(r"[Pp]otencia\s+punta[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))
        m = re.search(r"[Pp]otencia\s+valle[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))
        return result or super().extraer_potencias_contratadas()
