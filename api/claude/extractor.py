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
            return json.loads(_sanitize_json(raw))

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
        max_tokens=MAX_TOKENS,
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

    print(f"  stop_reason: {response.stop_reason}  |  chars resposta: {len(text)}")

    try:
        data = _parse_json_from_text(text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  ❌  JSON inválido: {e}")
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
    if result.margen_de_error is not None:
        ok = result.margen_de_error <= 5.0
        icon = "✅" if ok else "⚠️ "
        print(f"  {icon}  Margen de error: {result.margen_de_error:.2f}%"
              f"  ({'dentro del 5%' if ok else 'FUERA DEL 5% — revisar campos'})")
    print(f"{'='*70}\n")

    return result
