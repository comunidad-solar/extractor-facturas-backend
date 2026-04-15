# api/claude/client.py
# Singleton del cliente Anthropic — se inicializa una sola vez al primer uso.

import os
import anthropic

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key="ANTHROPIC_API_KEY_REMOVED")
    return _client
