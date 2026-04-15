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
    return result
