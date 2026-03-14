# extractor/parsers/octopus.py
# Parser específico para facturas de Octopus Energy España.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias respecto al BaseParser:
#   - pp_p1/pp2: formato "X kW * N días PRECIO €/kW/día" (cubierto en base)
#   - imp_ele: formato "BASE € X,XX %" (cubierto en base)
#
# Modificado: 2026-02-26 | Rodrigo Costa

from .base_parser import BaseParser


class OctopusParser(BaseParser):
    pass
    # Actualmente el BaseParser cubre todos los casos de Octopus.
    # Este archivo existe para facilitar añadir casos especiales en el futuro.
