# api/routes/enviar.py
# Proxy para Zoho Flow.
# POST /enviar — reenvía {cliente, factura, ...} al webhook de Zoho Flow (JSON)

import json

import httpx
from fastapi import APIRouter, Form, HTTPException
from typing import Any, Dict

ZOHO_WEBHOOK = (
    "https://flow.zoho.eu/20067915739/flow/webhook/incoming"
    "?zapikey=1001.333e94b169d89fa9db9d59ecf859b773.0377ab428b917dde7096df8db25b29eb"
    "&isdebug=false"
)

router = APIRouter(prefix="/enviar", tags=["enviar"])


# ---------------------------------------------------------------------------
# POST /enviar — Zoho Flow (JSON)
# ---------------------------------------------------------------------------

@router.post("")
async def enviar_datos(
    data: str = Form(..., description='JSON: {"cliente": {...}, "factura": {...}, "Fsmstate": "...", "FsmPrevious": "...", "ce": {...}}'),
):
    """
    Parseia o JSON e envia ao Zoho Flow.
    """
    # --- Validar JSON ---
    try:
        parsed: Dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Campo 'data' no es JSON válido: {e}")

    if "cliente" not in parsed:
        raise HTTPException(status_code=400, detail="Campo 'data' debe contener al menos 'cliente'.")

    print(f"[/enviar] Campos recibidos: {list(parsed.keys())}")

    # --- Enviar JSON ao Zoho Flow ---
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ZOHO_WEBHOOK, json=parsed)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Error de conexión con Zoho Flow")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en Zoho Flow")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de Zoho Flow: {e.response.status_code}")

    print(f"[/enviar] Zoho respondió: {resp.status_code}")

    return {"ok": True}
