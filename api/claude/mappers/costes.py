# api/claude/mappers/costes.py
# Maps bono social, additional services, and discounts.
# Rules: alquiler NEVER in costes; "Varios" is a section header; discounts go in creditos.

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que clasifica los costes adicionales y créditos de una factura eléctrica española.

REGLAS:

BONO SOCIAL:
  bono_social_importe: suma total del período (sumar todos los tramos si hay varios).
  bono_social_precio_dia: precio expresado en EUR/DÍA.
    - Si la factura muestra €/día → usar directamente.
    - Si la factura muestra €/año (ej: "4,650987 €/año") → dividir entre 365.
    - Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
    Verificación: bono_social_precio_dia × dias_periodo ≈ bono_social_importe.
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

AUTOCONSUMO — COMPENSACIÓN DE EXCEDENTES Y BATERÍA VIRTUAL:
  Si la factura tiene líneas de autoconsumo (excedentes, batería virtual):
    "Valoración excedentes": importe negativo (ej: -46.02 €).
    "Importe a cargar en la Batería Virtual": importe positivo (ej: +12.04 €) — reduce la compensación.
    "Subtotal Compensación Excedentes": el NETO = valoración + batería (ej: -33.98 €).
  REGLA: poner SOLO el neto en creditos["compensacion_excedentes_importe"].
    creditos["compensacion_excedentes_importe"] = Subtotal Compensación Excedentes (negativo).
  NUNCA poner valoración + subtotal juntos (doble conteo).
  NUNCA poner "importe_bateria_virtual" en creditos.
  Si no hay subtotal explícito → usar valoración directamente.
  Clave obligatoria: "compensacion_excedentes_importe" (no renombrar).

CARGO MÍNIMO COMUNITARIO (Art. 99.2 Ley 38/1992):
  Es un cargo regulatorio sobre el consumo, NO un servicio adicional.
  Va en costes_adicionales["minimo_comunitario_importe"] = <float positivo>.
  Señal: línea "Mínimo comunitario X kWh × 0,001000 €/kWh".

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
