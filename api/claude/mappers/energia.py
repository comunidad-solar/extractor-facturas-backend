# api/claude/mappers/energia.py
# Maps raw energy lines → pe_p* (€/kWh) and consumo_p* (kWh).
# Handles: PRECIO ÚNICO, CASO A (weighted average), CASO B (temporal tramos).

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que asigna los precios de energía (pe_p*) y consumos (consumo_p*) de una factura eléctrica española.

REGLAS (en orden de prioridad):

PRECIO ÚNICO — si todos los kWh tienen el mismo precio independientemente del período horario:
  pe_p1 = ese precio; pe_p2..pe_p6 = null.
  consumo_p1_kwh = total kWh; consumo_p2..p6 = null.
  Obs: "pe_p1 = precio único aplicado a X kWh totales".

CASO A — si un período tarifario específico (P1, P2, P3…) tiene MÚLTIPLES LÍNEAS con distintos precios:
  pe_p* = Σ(kwh_i × precio_i) / Σ(kwh_i)  [media ponderada por kWh]
  consumo_p* = Σ(kwh_i)  [suma de todos los sub-tramos]
  Obs: "pe_p* media ponderada de N sub-tramos".
  Ejemplo: P1 con (79.76 kWh × 0.092539) + (64.24 kWh × 0.097553) → pe_p1 = 13.65/144 = 0.094792; consumo_p1 = 144.

CASO B — si TODO el período de facturación está dividido en tramos temporales (cambio de precios a mitad del período):
  Señales de CASO B (cualquiera de estas):
    a) Las líneas de energía NO tienen label de período P* (o tienen el mismo label) y están diferenciadas por rango de fechas (ej: "16/12/2025-31/12/2025" y "31/12/2025-19/01/2026").
    b) El primer grupo de líneas cubre todos los P* (P1, P2, P3) para el tramo 1; el segundo grupo para el tramo 2.
  En CASO B: asignar tramo 1 → pe_p1/consumo_p1, tramo 2 → pe_p2/consumo_p2. NUNCA calcular media ponderada.
  Si cada tramo tiene un único precio para todos sus kWh (no discrimina punta/llano/valle internamente):
    pe_p1 = precio del tramo 1, consumo_p1_kwh = kWh del tramo 1.
    pe_p2 = precio del tramo 2, consumo_p2_kwh = kWh del tramo 2.
  Ejemplo Iberdrola 2.0TD: líneas "76 kWh × 0.17347" (tramo 16/12-31/12) y "176 kWh × 0.18051" (tramo 31/12-19/01):
    pe_p1=0.17347, consumo_p1_kwh=76, pe_p2=0.18051, consumo_p2_kwh=176.
    INCORRECTO: pe_p1=media_ponderada, pe_p2=null. INCORRECTO: pe_p1=null.
  Obs: "pe_p1/pe_p2 = precios de tramos temporales (cambio DD/MM/YYYY), no períodos tarifarios P1/P2".

COHERENCIA pe_p* / consumo_p*:
  Si consumo_pN tiene valor → pe_pN NUNCA puede ser null (y viceversa).
  Excepción: PRECIO ÚNICO → pe_p2..p6 = null Y consumo_p2..p6 = null.

ZEROS vs NULL:
  Períodos que EXISTEN en la tarifa pero tuvieron 0 kWh → pe_p* = 0.0, consumo_p* = 0.0.
  Períodos que NO EXISTEN en la tarifa → pe_p* = null, consumo_p* = null.

imp_termino_energia_eur: usar "termino_energia.total_bruto" (BRUTO, incluyendo reactiva si la factura la agrupa en ese total). NUNCA el valor neto después de descuentos.

Devuelve ÚNICAMENTE este JSON:
{
  "pe_p1": <float o null>, "pe_p2": <float o null>, "pe_p3": <float o null>,
  "pe_p4": <float o null>, "pe_p5": <float o null>, "pe_p6": <float o null>,
  "consumo_p1_kwh": <float o null>, "consumo_p2_kwh": <float o null>, "consumo_p3_kwh": <float o null>,
  "consumo_p4_kwh": <float o null>, "consumo_p5_kwh": <float o null>, "consumo_p6_kwh": <float o null>,
  "imp_termino_energia_eur": <float o null>,
  "observacion": [<string>]
}"""


def map_energia(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
