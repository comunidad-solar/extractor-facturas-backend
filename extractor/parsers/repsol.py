# extractor/parsers/repsol.py
# Parser específico para facturas de Repsol Comercializadora.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias respecto al BaseParser:
#   - imp_ele: línea "BASE € BASE x X%" mezclada con "IVA" al final
#   - alquiler: solo hay total €, sin €/día explícito
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from .base_parser import BaseParser
from ..base import norm


class RepsolParser(BaseParser):
    pass
    # Actualmente el BaseParser cubre todos los casos de Repsol.
    # Este archivo existe para facilitar añadir casos especiales en el futuro.
