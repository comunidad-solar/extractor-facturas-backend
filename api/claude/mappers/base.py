# api/claude/mappers/base.py
# Shared helper: calls claude-haiku with a system prompt and raw data JSON.
# Returns parsed dict. All mappers use this.

import json
import re

from api.claude.client import get_client

MAPPER_MODEL = "claude-sonnet-4-6"
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
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    text = response.content[0].text if response.content else ""
    return _parse_json(text)


def _clean(s: str) -> str:
    """Normalise common model output issues."""
    # Stray word appended to a numeric VALUE (after "key": NUMBER...)
    # Matches only in value position (after ": ") to avoid touching string content.
    # e.g.  "pp_p4": 0.01526distrib",  →  "pp_p4": 0.01526,
    s = re.sub(
        r'(":\s*)(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)[a-zA-Z_]\w*"?(?=\s*[,}\]])',
        r"\1\2",
        s,
    )
    # Trailing commas before } or ]
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # Python literals
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    return s


def _parse_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    raw = match.group(1) if match else text.strip()

    for candidate in (raw, _clean(raw)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Last resort: extract first {...} block from entire response
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            return json.loads(_clean(brace_match.group(0)))
        except json.JSONDecodeError:
            pass

    print(f"  [WARN] _parse_json failed. Raw response:\n{text[:600]}")
    raise json.JSONDecodeError("Could not parse mapper response", text, 0)
