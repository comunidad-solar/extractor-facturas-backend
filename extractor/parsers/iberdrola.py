# extractor/parsers/iberdrola.py
# Parser específico para facturas de Iberdrola Clientes.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias conocidas respecto al BaseParser:
#   - imp_ele: formato "X% s/BASE" (cubierto en base)
#
# Modificado: 2026-02-26 | Rodrigo Costa

from .base_parser import BaseParser


class IberdrolaParser(BaseParser):
    pass
    # Actualmente el BaseParser cubre los casos conocidos de Iberdrola.
    # Añadir sobrescrituras aquí cuando se detecten diferencias en pruebas reales.
