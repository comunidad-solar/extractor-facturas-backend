# fields.py
# Define todos los campos que la aplicación intenta extraer de una factura de energía.
# Cada campo es un diccionario con metadatos usados por el parser, por la GUI y por el generador de JSON.

from dataclasses import dataclass, field
from typing import Optional

# ── Tipos posibles de un campo ───────────────────────────────────────────────
# "float"  → valor numérico decimal (ej: 0.072435)
# "string" → texto (ej: "2.0TD")
# "date"   → fecha en formato DD/MM/YYYY
# "int"    → número entero (ej: 29 días)

@dataclass
class Field:
    key: str                        # Nombre de la clave en el JSON final
    label_es: str                   # Label en español para la GUI
    tipo: str                       # "float", "string", "date", "int"
    bloque: str                     # Grupo al que pertenece (para organizar la GUI)
    required: bool = True           # Si True, la GUI lo destacará en rojo cuando falle
    default: Optional[str] = None   # Valor por defecto si no se encuentra (None = obligatorio)
    hint: str = ""                  # Sugerencia para el usuario en la GUI (ej: "Ej: 2.0TD")


# ── Definición de todos los campos ───────────────────────────────────────────
# Organizados por bloque para facilitar la renderización de la GUI en secciones

FIELDS: list[Field] = [

    # ── IDENTIFICACIÓN ────────────────────────────────────────────────────────
    Field("comercializadora",  "Comercializadora",       "string", "Identificación",
          hint="Ej: Repsol, Naturgy, Iberdrola..."),
    Field("distribuidora",     "Distribuidora",          "string", "Identificación",
          hint="Ej: I-DE, Edistribución..."),
    Field("cups",              "CUPS",                   "string", "Identificación",
          hint="Ej: ES0021000013483679RH1F"),
    Field("periodo_inicio",    "Inicio período",         "date",   "Identificación",
          hint="DD/MM/YYYY"),
    Field("periodo_fin",       "Fin período",            "date",   "Identificación",
          hint="DD/MM/YYYY"),
    Field("dias_facturados",   "Días facturados",        "int",    "Identificación",
          hint="Ej: 29"),

    # ── TARIFA ────────────────────────────────────────────────────────────────
    Field("tarifa_acceso",     "Tarifa de acceso",       "string", "Tarifa",
          hint="Ej: 2.0TD, 3.0TD"),

    # ── POTENCIAS CONTRATADAS ─────────────────────────────────────────────────
    # P3..P6 no son obligatorios porque en 2.0TD siempre valen 0
    Field("pot_p1_kw",  "Potencia contratada P1 (kW)",  "float",  "Potencias contratadas",
          hint="Ej: 5.6"),
    Field("pot_p2_kw",  "Potencia contratada P2 (kW)",  "float",  "Potencias contratadas",
          hint="Ej: 5.6"),
    Field("pot_p3_kw",  "Potencia contratada P3 (kW)",  "float",  "Potencias contratadas",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pot_p4_kw",  "Potencia contratada P4 (kW)",  "float",  "Potencias contratadas",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pot_p5_kw",  "Potencia contratada P5 (kW)",  "float",  "Potencias contratadas",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pot_p6_kw",  "Potencia contratada P6 (kW)",  "float",  "Potencias contratadas",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────
    Field("pp_p1",  "Precio potencia P1 (€/kW·día)",    "float",  "Precios de potencia",
          hint="Ej: 0.072435"),
    Field("pp_p2",  "Precio potencia P2 (€/kW·día)",    "float",  "Precios de potencia",
          hint="Ej: 0.067476"),
    Field("pp_p3",  "Precio potencia P3 (€/kW·día)",    "float",  "Precios de potencia",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pp_p4",  "Precio potencia P4 (€/kW·día)",    "float",  "Precios de potencia",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pp_p5",  "Precio potencia P5 (€/kW·día)",    "float",  "Precios de potencia",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("pp_p6",  "Precio potencia P6 (€/kW·día)",    "float",  "Precios de potencia",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),

    # ── CONSUMOS ──────────────────────────────────────────────────────────────
    Field("consumo_p1_kwh",  "Consumo P1 - Punta (kWh)",  "float", "Consumos",
          hint="Ej: 58.0"),
    Field("consumo_p2_kwh",  "Consumo P2 - Llano (kWh)",  "float", "Consumos",
          hint="Ej: 39.0"),
    Field("consumo_p3_kwh",  "Consumo P3 - Valle (kWh)",  "float", "Consumos",
          hint="Ej: 87.0"),
    Field("consumo_p4_kwh",  "Consumo P4 (kWh)",          "float", "Consumos",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("consumo_p5_kwh",  "Consumo P5 (kWh)",          "float", "Consumos",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),
    Field("consumo_p6_kwh",  "Consumo P6 (kWh)",          "float", "Consumos",
          required=False, default="0.0", hint="0 si tarifa 2.0TD"),

    # ── IMPUESTOS ─────────────────────────────────────────────────────────────
    Field("imp_ele",  "Impuesto eléctrico (%)",  "float", "Impuestos",
          hint="Ej: 5.11269632 o 2.5"),
    Field("iva",      "IVA (%)",                 "float", "Impuestos",
          hint="Ej: 21 o 10"),

    # ── ALQUILER ──────────────────────────────────────────────────────────────
    Field("alq_eq_dia",  "Alquiler equipo de medida (€/día)",  "float", "Alquiler",
          hint="Ej: 0.026429"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_field(key: str) -> Optional[Field]:
    """Devuelve un Field por su key. Útil en el parser y en la GUI."""
    return next((f for f in FIELDS if f.key == key), None)


def get_fields_by_bloque(bloque: str) -> list[Field]:
    """Devuelve todos los campos de un bloque específico. Usado por la GUI para renderizar secciones."""
    return [f for f in FIELDS if f.bloque == bloque]


def get_bloques() -> list[str]:
    """Devuelve la lista de bloques únicos, en orden de aparición. Usado por la GUI."""
    seen = []
    for f in FIELDS:
        if f.bloque not in seen:
            seen.append(f.bloque)
    return seen


def required_keys() -> list[str]:
    """Devuelve las keys de todos los campos obligatorios. Usado por el validador."""
    return [f.key for f in FIELDS if f.required]