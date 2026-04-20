# api/claude/extractor.py
# Llama a la API de Claude con el PDF en base64 y devuelve un
# ExtractionResponseAI validado por Pydantic.

import base64
import json
import re

from api.claude.client import get_client
from api.claude.prompts import SYSTEM_PROMPT
from api.claude.pipeline import run_pipeline
from api.models import ExtractionResponseAI

MODEL = "claude-opus-4-7"
MAX_TOKENS = 8192


_VALID_FIELDS = set(ExtractionResponseAI.model_fields.keys())

_USER_TEXT = (
    "Extrae todos los datos de esta factura según las instrucciones del sistema. "
    "Devuelve ÚNICAMENTE un bloque ```json``` con los campos extraídos. "
    "Sin texto adicional antes ni después del bloque JSON."
)


def _sanitize_json(raw: str) -> str:
    """
    Limpia JSON-like text generado por Claude:
      - Elimina comentarios // de línea (respetando strings)
      - Elimina comentarios /* ... */
      - Elimina trailing commas antes de } o ]
    """
    result = []
    i = 0
    n = len(raw)
    in_string = False

    while i < n:
        c = raw[i]

        # Escape dentro de string → pasar tal cual
        if in_string and c == '\\' and i + 1 < n:
            result.append(c)
            result.append(raw[i + 1])
            i += 2
            continue

        # Límites de string
        if c == '"':
            in_string = not in_string
            result.append(c)
            i += 1
            continue

        if not in_string:
            # Comentario de línea //
            if c == '/' and i + 1 < n and raw[i + 1] == '/':
                while i < n and raw[i] != '\n':
                    i += 1
                continue
            # Comentario de bloque /* ... */
            if c == '/' and i + 1 < n and raw[i + 1] == '*':
                i += 2
                while i < n - 1:
                    if raw[i] == '*' and raw[i + 1] == '/':
                        i += 2
                        break
                    i += 1
                continue

        result.append(c)
        i += 1

    clean = ''.join(result)
    # Trailing commas: ,  }  o  ,  ]
    clean = re.sub(r',(\s*[}\]])', r'\1', clean)
    return clean


def _parse_json_from_text(text: str) -> dict:
    """Extrae y parsea el JSON del texto de respuesta de Claude.
    Maneja bloques ```json cerrados, no cerrados (truncados) y JSON puro.
    Sanea comentarios JS y trailing commas antes de parsear."""

    def _load(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return json.loads(_sanitize_json(raw))
            except json.JSONDecodeError:
                import ast
                result = ast.literal_eval(raw)
                if not isinstance(result, dict):
                    raise ValueError("ast.literal_eval no devolvió dict")
                return result

    # Bloque ```json ... ``` cerrado
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return _load(match.group(1))
    # Bloque ```json sin cerrar (respuesta truncada por max_tokens)
    match_open = re.search(r"```(?:json)?\s*([\s\S]+)", text)
    if match_open:
        return _load(match_open.group(1).strip())
    # JSON puro sin bloque
    return _load(text.strip())


def _build_response(data: dict) -> ExtractionResponseAI:
    """Filtra claves desconocidas y construye ExtractionResponseAI.
    Convierte 'otros' y 'descuentos' de string JSON a dict si es necesario.
    Convierte 'IVA' dict → IVABlock."""
    from api.models import IVABlock

    filtered = {k: v for k, v in data.items() if k in _VALID_FIELDS}

    # String JSON → dict para otros y descuentos
    for field in ("otros", "descuentos"):
        val = filtered.get(field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val) if val.strip() else None
                filtered[field] = parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, ValueError):
                filtered[field] = None

    # dias_facturados debe ser string (Claude a veces devuelve int)
    if "dias_facturados" in filtered and not isinstance(filtered["dias_facturados"], str):
        filtered["dias_facturados"] = str(filtered["dias_facturados"]) if filtered["dias_facturados"] is not None else None

    # Campos que deben ser float pero Claude a veces devuelve dict estructurado
    _FLOAT_FIELDS = (
        "bono_social", "alq_eq_dia", "imp_ele", "iva",
        "importe_factura", "imp_ele_eur_kwh",
        "imp_termino_energia_eur", "imp_termino_potencia_eur",
        "imp_impuesto_electrico_eur", "imp_alquiler_eur", "imp_iva_eur",
        "impuesto_electricidad_importe", "alquiler_equipos_medida_importe",
        "IVA_TOTAL_EUROS", "margen_de_error",
    )
    for field in _FLOAT_FIELDS:
        val = filtered.get(field)
        if isinstance(val, dict):
            # Intentar extraer un valor numérico útil del dict:
            # buscar 'importe_eur', 'precio_eur_dia', 'valor', o el primer float
            candidate = (
                val.get("importe_eur")
                or val.get("precio_eur_dia")
                or val.get("valor")
                or next((v for v in val.values() if isinstance(v, (int, float))), None)
            )
            filtered[field] = float(candidate) if candidate is not None else None
            print(f"  ⚠️  {field} devuelto como dict — extraído: {filtered[field]}")

    # Dict → IVABlock
    iva_val = filtered.get("IVA")
    if isinstance(iva_val, dict):
        try:
            filtered["IVA"] = IVABlock(**{
                k: v for k, v in iva_val.items()
                if k in IVABlock.model_fields
            })
        except Exception:
            filtered["IVA"] = None
    elif iva_val is not None and not isinstance(iva_val, IVABlock):
        filtered["IVA"] = None

    return ExtractionResponseAI(**filtered)


def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF al pipeline multi-agente y devuelve los datos estructurados."""
    return run_pipeline(pdf_bytes)
