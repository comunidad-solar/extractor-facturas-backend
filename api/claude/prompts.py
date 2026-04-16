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
    "Si no hay datos extra, usa la cadena vacía \"\".\n"
    "CRÍTICO — campos pp_p1..pp_p6 (precio de potencia): "
    "SIEMPRE en €/kW·día. Detecta la unidad en que aparece el precio y convierte: "
    "(a) €/kW·año → divide entre 365. "
    "Ejemplo: 26,930550 €/kW·año → 26.930550 / 365 = 0.073783 €/kW·día. "
    "(b) €/kW·mes → divide entre el número de días facturados del período. "
    "Ejemplo: precio 2,24450 €/kW·mes con 31 días → 2.24450 / 31 = 0.072403 €/kW·día. "
    "Si la factura no indica la unidad, asume €/kW·año y divide entre 365. "
    "CASO ESPECIAL — Energía XXI (y otras con sub-períodos): algunas facturas dividen "
    "un mismo período tarifario en dos sub-períodos con precios distintos y un número "
    "de días para cada uno. En ese caso calcula la media ponderada por días antes de "
    "convertir a €/kW·día. "
    "Ejemplo: sub-período A → 0,044800 €/kW·día × 15 días; "
    "sub-período B → 0,051200 €/kW·día × 16 días; "
    "media ponderada = (0.044800×15 + 0.051200×16) / (15+16) = 0.048129 €/kW·día."
)


def get_system_prompt() -> str:
    return _PREAMBLE + "\n\n" + _PROMPT_PATH.read_text(encoding="utf-8")


# Cargado una sola vez al importar el módulo → prompt caching efectivo
SYSTEM_PROMPT: str = get_system_prompt()
