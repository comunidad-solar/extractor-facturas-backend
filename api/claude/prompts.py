# api/claude/prompts.py
# Carga el system prompt para extracción de facturas en tiempo de importación
# para que el caché de Anthropic sea efectivo (el texto debe ser byte-idéntico
# entre llamadas).

from pathlib import Path

_PROMPT_PATH = (
    Path(__file__).parent.parent.parent
    / ".claude/skills/leer-factura/prompt_lectura_factura.md"
)

_PREAMBLE = (
    "Eres un extractor de datos de facturas eléctricas españolas.\n"
    "Tu única tarea es leer el PDF adjunto y devolver un JSON estructurado "
    "con todos los campos que puedas extraer.\n"
    "NO escribas ficheros. NO ejecutes scripts. Solo devuelve el JSON.\n"
    "Los campos 'validacion_cuadre' y 'session_id' deben ser siempre null "
    "(se calculan en el servidor).\n"
    "El campo 'otros' debe ser una cadena JSON válida (string) con cualquier "
    "dato extra: períodos adicionales (pp_p3..pp_p6, pe_p4..pe_p6), descuentos, "
    "conceptos no estándar, etc. Ejemplo: '{\"pp_p3\": 0.035, \"descuentos\": {\"pack\": -5.0}}'. "
    "Si no hay datos extra, usa la cadena vacía \"\"."
)


def get_system_prompt() -> str:
    return _PREAMBLE + "\n\n" + _PROMPT_PATH.read_text(encoding="utf-8")


# Cargado una sola vez al importar el módulo → prompt caching efectivo
SYSTEM_PROMPT: str = get_system_prompt()
