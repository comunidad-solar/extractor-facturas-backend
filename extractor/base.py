# extractor/base.py
# Utilidades compartidas: helpers de texto, fechas, logs y ExtractionResult.
# Importado por todos los módulos del paquete extractor.
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExtractionResult:
    """Contenedor del resultado de extracción de una factura."""
    fields:      dict
    raw_matches: dict
    api_ok:      bool = False
    api_error:   str  = ""


# ── Normalización ─────────────────────────────────────────────────────────────

def norm(value: str) -> Optional[str]:
    """Normaliza un valor: elimina espacios y reemplaza coma decimal por punto."""
    if value is None:
        return None
    return value.strip().replace(",", ".")


def numeros(texto: str) -> list[str]:
    """Extrae todos los números de un texto como lista de strings normalizados."""
    return [norm(n) for n in re.findall(r"\d+[,\.]\d+|\d+", texto)]


# ── Fechas ────────────────────────────────────────────────────────────────────

def to_date(val: str) -> Optional[datetime]:
    """
    Convierte cualquier formato de fecha a datetime.
    Soporta: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD
    """
    if not val:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    return None


def fmt_date(dt: datetime) -> str:
    """Formatea un datetime como DD/MM/YYYY."""
    return dt.strftime("%d/%m/%Y")


def normalizar_fecha(val: str) -> str:
    """Normaliza cualquier formato de fecha a DD/MM/YYYY."""
    dt = to_date(val)
    return fmt_date(dt) if dt else val


# ── Logs ──────────────────────────────────────────────────────────────────────

def log(campo: str, valor, fuente: str = "") -> None:
    """Imprime un log formateado para cada campo extraído."""
    estado = "✅" if valor else "⚠️ "
    if fuente == "API":
        fuente_str = "  ←  [API Ingebau]"
    elif fuente:
        fuente_str = f"  ←  {fuente[:80]}"
    else:
        fuente_str = ""
    print(f"  {estado}  {campo:<25} = {str(valor):<25}{fuente_str}")
