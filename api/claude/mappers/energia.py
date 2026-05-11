# api/claude/mappers/energia.py
# Maps raw energy lines → pe_p* (€/kWh) and consumo_p* (kWh).
# Handles: PRECIO ÚNICO, CASO A (weighted average), CASO B (temporal tramos).

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que asigna los precios de energía (pe_p*) y consumos (consumo_p*) de una factura eléctrica española.

GUARDRAIL — VALIDACIÓN OBLIGATORIA ANTES DE DEVOLVER:
  pe_p* representa el precio TOTAL de la energía (peaje + coste mercado). Rango razonable: 0.05–0.50 €/kWh.
  Si cualquier pe_p* calculado es < 0.05 €/kWh → SEÑAL DE ERROR: estás usando solo el precio de peaje/acceso, no el precio total.
  En ese caso: revisar si existe costes_mercado en termino_energia y aplicar CASO PVPC (ver abajo).
  NUNCA devolver pe_p* < 0.05 €/kWh salvo que la factura lo justifique explícitamente (ej: compensación de excedentes, precio negativo de mercado).

CASO PVPC (peajes ATR + costes_mercado bulk) — MÁXIMA PRIORIDAD:
  Señales: termino_energia.costes_mercado NO es null Y costes_producto_por_periodo es null.
  Indica factura PVPC: las líneas muestran SOLO precios de peaje/acceso (valores bajos: ~0.002–0.10 €/kWh).
  El coste real de la energía incluye también costes_mercado (ej: "Costes de la energía: 111,88 €").
  NUNCA usar los precios de peaje directamente como pe_p* en este caso.
  Algoritmo:
    total_kwh = Σ kwh de todas las líneas.
    Para cada período P*:
      peaje_importe_pN = Σ(kwh_i × precio_i) para las líneas de ese período.
      kwh_pN = Σ(kwh_i) para las líneas de ese período.
      costes_mercado_pN = costes_mercado.importe × (kwh_pN / total_kwh).
      pe_pN = (peaje_importe_pN + costes_mercado_pN) / kwh_pN.
    consumo_pN_kwh = kwh_pN.
  Verificación: Σ(pe_pN × kwh_pN) ≈ termino_energia.total_bruto (tolerancia 0.10 €).
  Obs: "pe_pN = (peaje_pN + costes_mercado proporcional×kWh) / kWh — PVPC estructura peaje+mercado bulk".

CASO DUAL-BLOCK (Producto + ATR separados) — SEGUNDA PRIORIDAD:
  Si termino_energia.costes_producto_por_periodo NO es null:
  La factura tiene dos bloques de energía: uno de "Coste de Energía Producto" (capturado en costes_producto_por_periodo)
  y otro de "Término de Energía ATR" (capturado en lineas con precio €/kWh y importe €).
  pe_p* = (costes_producto_por_periodo[P*].importe + lineas[P*].importe) / lineas[P*].kwh
  consumo_p*_kwh = lineas[P*].kwh
  Obs: "pe_p* = (producto_importe + ATR_importe) / kwh — bloque dual Producto+ATR".
  NUNCA usar solo el precio ATR de lineas[].precio como pe_p* en este caso.

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

NULL vs 0:
  Si un período NO tiene línea explícita en la factura → pe_p* = null, consumo_p* = null. NUNCA devolver 0 o 0.0 si no hay línea de datos.
  Solo devuelve 0.0 si la factura incluye explícitamente una línea con "0 kWh" para ese período.

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
