# api/claude/mappers/base.py
# Shared helper: calls claude-haiku with a system prompt and raw data JSON.
# Returns parsed dict. All mappers use this.

import json
import re

from api.claude.client import get_client

MAPPER_MODEL = "claude-haiku-4-5-20251001"
MAPPER_MAX_TOKENS = 2048


def call_haiku(system_prompt: str, raw_data: dict) -> dict:
    """Call haiku with raw_data as input, return parsed JSON dict."""
    client = get_client()
    user_text = (
        "Datos crudos de la factura:\n"
        "```json\n"
        + json.dumps(raw_data, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "Aplica las reglas del sistema y devuelve ÚNICAMENTE el bloque ```json``` con los campos asignados."
    )
    response = client.messages.create(
        model=MAPPER_MODEL,
        max_tokens=MAPPER_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    text = response.content[0].text if response.content else ""
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Remove trailing commas and retry
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)
        return json.loads(raw)
