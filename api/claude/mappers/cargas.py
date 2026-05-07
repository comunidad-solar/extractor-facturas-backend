# api/claude/mappers/cargas.py
# Determines if exceso_potencia and coste_energia_reactiva are INSIDE or OUTSIDE
# their respective imp_termino_* values (to avoid double-counting in cuadre).

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que clasifica dos cargos específicos de una factura eléctrica española.

TAREA: Determinar si el exceso de potencia y la energía reactiva ya están DENTRO de los totales principales o son líneas SEPARADAS.

REGLA EXCESO DE POTENCIA:
  Verificar: ¿termino_potencia.total_bruto ya incluye el exceso?
  Si "exceso_potencia.importe" + las líneas de potencia base = total_bruto → DENTRO (inside=true).
  Si el exceso aparece como línea completamente fuera del bloque de potencia → FUERA (inside=false).
  Cuando inside=true → exceso_potencia_importe en costes debe ser null (para no duplicar en cuadre).
  Cuando inside=false → exceso_potencia_importe en costes tiene valor y SE SUMA en cuadre.

REGLA ENERGÍA REACTIVA:
  Verificar: ¿termino_energia.total_bruto incluye la reactiva?
  Si "reactiva.importe" + total_activa_bruto ≈ total_bruto → reactiva DENTRO (inside=true).
  Si total_bruto = solo energía activa y reactiva es línea aparte → FUERA (inside=false).
  Cuando inside=true → coste_energia_reactiva en costes debe ser null (ya está contabilizada en imp_termino_energia_eur — poner cualquier valor causa doble contabilidad).
  Cuando inside=false → coste_energia_reactiva tiene valor y se suma en cuadre.

Devuelve ÚNICAMENTE este JSON:
{
  "exceso_potencia_importe": <float o null — null si inside=true, valor si inside=false>,
  "exceso_inside_potencia": <true|false>,
  "coste_energia_reactiva": <float si inside=false, null si inside=true o si no hay reactiva>,
  "reactiva_inside_energia": <true|false>,
  "observacion": [<string — explicación de cada decisión>]
}"""


def map_cargas(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
