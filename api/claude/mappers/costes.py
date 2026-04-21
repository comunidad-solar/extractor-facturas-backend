# api/claude/mappers/costes.py
# Maps bono social, additional services, and discounts.
# Rules: alquiler NEVER in costes; "Varios" is a section header; discounts go in creditos.

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que clasifica los costes adicionales y créditos de una factura eléctrica española.

REGLAS:

BONO SOCIAL:
  bono_social_importe: suma total del período (sumar todos los tramos si hay varios).
  bono_social_precio_dia: si hay un único tramo → precio_dia de ese tramo.
    Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
  Si no hay bono social → ambos null.

ALQUILER DE EQUIPOS:
  NUNCA incluir en costes_adicionales. El alquiler ya está en imp_alquiler_eur / importes_totalizados.

SECCIÓN "VARIOS" EN FACTURAS PVPC (Energía XXI, etc.):
  "Varios" es un ENCABEZADO DE SECCIÓN, no un servicio.
  Los conceptos dentro de esa sección (ej: Financiación Bono Social) ya tienen su campo nombrado.
  NUNCA crear clave "varios_importe" en costes_adicionales.

SERVICIOS ADICIONALES (Pack Hogar, Asistente Smart Hogar, Servicio FACILITA, etc.):
  Si el servicio tiene un descuento asociado:
    costes_adicionales["<nombre>_importe"] = importe BRUTO (antes del descuento).
    creditos["descuento_<nombre>"] = importe del descuento (negativo).
  Si no tiene descuento: solo en costes_adicionales.
  Clave: usar snake_case del nombre descriptivo + "_importe" (ej: "asistente_smart_hogar_importe").

DESCUENTOS SOBRE CONSUMO (ej: Descuento 15%):
  Van en creditos con valor negativo.
  Clave descriptiva snake_case (ej: "descuento_consumo_15": -6.74).

PRECIO FINAL ENERGÍA ACTIVA:
  precio_final_energia_activa: usar "termino_energia.total_activa_bruto" (BRUTO, antes de descuentos sobre consumo).
  Si hay reactiva, NO incluirla en precio_final_energia_activa (eso va en coste_energia_reactiva en importes_totalizados).

Devuelve ÚNICAMENTE este JSON:
{
  "bono_social_precio_dia": <float o null>,
  "bono_social_importe": <float o null>,
  "precio_final_energia_activa": <float o null>,
  "costes_adicionales": {
    "<nombre_servicio>_importe": <float>
  },
  "creditos": {
    "<nombre_descuento>": <float negativo>
  },
  "observacion": [<string>]
}
Nota: "costes_adicionales" y "creditos" pueden ser {} si no hay ninguno."""


def map_costes(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
