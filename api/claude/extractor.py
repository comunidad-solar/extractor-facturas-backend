# api/claude/extractor.py
# Llama a la API de Claude con el PDF vía Files API (upload → file_id → delete)
# en lugar de base64 inline. Más eficiente para PDFs grandes.

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
    """Sube el PDF a la Files API, extrae datos con Claude y borra el fichero."""
    print(f"\n{'='*70}")
    print(f"  *** API CLAUDE ***  ({MODEL})")
    print(f"{'='*70}")
    print(f"  PDF recibido: {len(pdf_bytes):,} bytes")

    client = get_client()

    # 1. Subir el PDF a la Files API
    print(f"  Subiendo PDF a Files API...")
    file_upload = client.beta.files.upload(
        file=("factura.pdf", pdf_bytes, "application/pdf"),
    )
    file_id = file_upload.id
    print(f"  File ID: {file_id}")

    try:
        # 2. Llamar a Claude referenciando el fichero por ID
        print(f"  Enviando a Claude...")
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            betas=["files-api-2025-04-14"],
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
                                "type": "file",
                                "file_id": file_id,
                            },
                        },
                        {"type": "text", "text": _USER_TEXT},
                    ],
                }
            ],
        )
    finally:
        # 3. Borrar el fichero siempre (éxito o error)
        try:
            client.beta.files.delete(file_id)
            print(f"  Fichero {file_id} eliminado de Files API")
        except Exception as e:
            print(f"  ⚠️  No se pudo eliminar el fichero {file_id}: {e}")

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
