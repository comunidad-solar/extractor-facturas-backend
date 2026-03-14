# extractor/detector.py
# Identifica la comercializadora de una factura a partir del texto extraído del PDF.
# Devuelve un string normalizado que se usa para seleccionar el parser adecuado.
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - Añadido patrón para Cox Energía

import re

_PATRONES: list[tuple[str, str]] = [
    (r"repsol\s+comercializadora",          "repsol"),
    (r"naturgy\s+iberia",                   "naturgy"),
    (r"iberdrola\s+clientes",               "iberdrola"),
    (r"endesa\s+energ[ií]a",                "endesa"),
    (r"octopus\s+energy\s+espa[ñn]a",       "octopus"),
    (r"cox\s+energ[ií]a\s+comercializadora", "cox"),
    (r"en[eé]rgya[\s\-]*vm",  "energyavm"),
    (r"contigo\s*energ[ií]a|gesternova",  "contigo"),
    (r"comercializadora\s+regulada|gas\s*&\s*power", "naturgy_regulada"),
    (r"pepe\s*energy|energ[ií]a\s+colectiva", "pepeenergy"),
    (r"plenitude|eni\s+plenitude", "plenitude"),


]


def detectar(text: str) -> str:
    """
    Analiza el texto del PDF y devuelve el identificador de comercializadora.
    Si no se reconoce ninguna, devuelve 'generic'.
    """
    texto_lower = text.lower()
    for patron, nombre in _PATRONES:
        if re.search(patron, texto_lower):
            print(f"  🏷️   Comercializadora detectada: {nombre.upper()}")
            return nombre

    print("  🏷️   Comercializadora no reconocida — usando parser genérico")
    return "generic"