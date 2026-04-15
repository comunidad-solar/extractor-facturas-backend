# api/claude/extractor.py
# Llama a la API de Claude con el PDF en base64 y devuelve un
# ExtractionResponseAI validado por Pydantic.

import base64
import json
import re

from api.claude.client import get_client
from api.claude.prompts import SYSTEM_PROMPT
from api.models import ExtractionResponseAI

MODEL = "claude-sonnet-4-6"

_VALID_FIELDS = set(ExtractionResponseAI.model_fields.keys())

_USER_TEXT = (
    "Extrae todos los datos de esta factura según las instrucciones del sistema. "
    "Devuelve ÚNICAMENTE un bloque ```json``` con los campos extraídos. "
    "Sin texto adicional antes ni después del bloque JSON."
)


def _parse_json_from_text(text: str) -> dict:
    """Extrae y parsea el JSON del texto de respuesta de Claude."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    return json.loads(text.strip())


def _build_response(data: dict) -> ExtractionResponseAI:
    """Filtra claves desconocidas y construye ExtractionResponseAI."""
    filtered = {k: v for k, v in data.items() if k in _VALID_FIELDS}
    return ExtractionResponseAI(**filtered)


def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF a Claude en base64 y devuelve los datos estructurados."""
    print(f"\n{'='*70}")
    print(f"  *** API CLAUDE ***  ({MODEL})")
    print(f"{'='*70}")
    print(f"  PDF recibido: {len(pdf_bytes):,} bytes")
    print(f"  Enviando a Claude...")

    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": _USER_TEXT},
                ],
            }
        ],
    )

    text = response.content[0].text if response.content else ""

    try:
        data = _parse_json_from_text(text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  ❌  JSON inválido en respuesta de Claude: {e}")
        print(f"  Respuesta (primeros 500 chars):\n{text[:500]}")
        raise ValueError(f"Claude no devolvió JSON válido: {e}")

    result = _build_response(data)

    usage = response.usage
    print(f"  ✅  Extracción completada")
    print(f"  Tokens — input: {usage.input_tokens:,}  |  output: {usage.output_tokens:,}"
          f"  |  cache_read: {getattr(usage, 'cache_read_input_tokens', 0):,}"
          f"  |  cache_creation: {getattr(usage, 'cache_creation_input_tokens', 0):,}")
    print(f"  CUPS extraído: {result.cups or '(no detectado)'}")
    print(f"  Comercializadora: {result.comercializadora or '(no detectada)'}")
    print(f"  Período: {result.periodo_inicio} → {result.periodo_fin}")
    print(f"  Importe factura: {result.importe_factura} €")
    print(f"{'='*70}\n")

    return result
