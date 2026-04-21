# api/claude/mappers/potencia.py
# Maps raw potencia lines → pp_p1..pp_p6 (in €/kW·day) and imp_termino_potencia_eur.
# Handles: unit conversion (year/month/day), CASO A weighted average for sub-tramos.

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que calcula los precios de potencia (pp_p*) de una factura eléctrica española.

REGLAS (aplica en orden):
1. pp_p1..pp_p6 deben estar SIEMPRE en €/kW·DÍA. Detectar la unidad desde "formula_detectada" o "unidad_precio":
   - "EUR/kW/anio" o "EUR/kW/año" o formula "× (dias/365)": dividir entre 365. Obs: "pp_p* convertido de €/kW·año ÷ 365".
   - "EUR/kW/anio" con formula "× (dias/366)": dividir entre 366. Obs: "pp_p* convertido de €/kW·año ÷ 366 (año bisiesto)".
   - "EUR/kW/mes" o formula "× (dias/N)": dividir entre los días del mes facturado. Obs: "pp_p* convertido de €/kW·mes ÷ N".
   - "EUR/kW/dia" o formula "× dias": extraer directo, sin conversión.
   - Sin formula explícita: asumir EUR/kW/año, dividir entre 365.
   CRÍTICO: dividir siempre el precio base entre el divisor. NUNCA dividir el importe entre kW·días.

2. Si un período (ej: P1) aparece con MÚLTIPLES LÍNEAS (CASO A — sub-tramos del mismo período tarifario):
   pp_p1 = Σ(dias_i × precio_convertido_i) / Σ(dias_i)
   Obs: "pp_p1 media ponderada de N sub-tramos: (dias1×precio1 + dias2×precio2) / (dias1+dias2)".

3. Si los precios son de tramos temporales (CASO B — todo el período facturado dividido, no un P* específico):
   asignar directamente: tramo1 → pp_p1, tramo2 → pp_p2.
   Indicar en observacion: "pp_p1/pp_p2 son tramos temporales, no períodos tarifarios".

4. imp_termino_potencia_eur: usar "termino_potencia.total_bruto" directamente (ya incluye exceso si lo hay).

5. Períodos sin línea en la factura: pp_p* = null.
   Períodos existentes en tarifa sin potencia contratada: pp_p* = null.

CRÍTICO — FORMATO JSON:
- Cada valor numérico es ÚNICAMENTE el número final (ej: 0.000147559). NUNCA texto, letras ni palabras dentro del valor.
- Si calculas algo mentalmente, escribe SOLO el resultado en el campo JSON. Las explicaciones van en "observacion", no en los valores.
- No repitas la misma clave. No incluyas comentarios dentro del JSON.

Devuelve ÚNICAMENTE este JSON (sin texto antes ni después del bloque ```json```):
{
  "pp_p1": <float o null>,
  "pp_p2": <float o null>,
  "pp_p3": <float o null>,
  "pp_p4": <float o null>,
  "pp_p5": <float o null>,
  "pp_p6": <float o null>,
  "pp_unidad": "dia",
  "imp_termino_potencia_eur": <float o null>,
  "observacion": [<string>]
}"""


def map_potencia(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
