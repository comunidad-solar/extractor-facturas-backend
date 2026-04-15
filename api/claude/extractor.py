# api/claude/extractor.py
# Llama a la API de Claude con el PDF en base64 y devuelve un
# ExtractionResponseAI validado por Pydantic.

import base64

from api.claude.client import get_client
from api.claude.prompts import SYSTEM_PROMPT
from api.models import ExtractionResponseAI

MODEL = "claude-sonnet-4-6"

_USER_TEXT = (
    "Extrae todos los datos de esta factura según las instrucciones del sistema."
)


def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF a Claude y devuelve los datos estructurados."""
    print(f"\n{'='*70}")
    print(f"  *** API CLAUDE ***  ({MODEL})")
    print(f"{'='*70}")
    print(f"  PDF recibido: {len(pdf_bytes):,} bytes")
    print(f"  Enviando a Claude...")

    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = client.messages.parse(
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
        output_format=ExtractionResponseAI,
    )

    result = response.parsed_output
    if result is None:
        raise ValueError("Claude no devolvió un objeto estructurado válido")

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
