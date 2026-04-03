# api/routes/enviar.py
# Proxy para Zoho Flow.
# POST /enviar — reenvía {cliente, factura, ...} al webhook de Zoho Flow (JSON)

import asyncio
import json
import os

import httpx
from fastapi import APIRouter, Form, HTTPException
from typing import Any, Dict

from api.zoho_crm import buscar_deal_por_email, buscar_mpklog_por_email

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

    # Aguardar o Flow criar o deal (assíncrono — não bloqueante)
    delay = int(os.getenv("ZOHO_DEAL_FETCH_DELAY", "4"))
    await asyncio.sleep(delay)

    # Buscar dealId e mpklogId em paralelo
    correo = parsed.get("cliente", {}).get("correo", "")
    deal_id = None
    mpklog_id = None
    if correo:
        deal_id, mpklog_id = await asyncio.gather(
            buscar_deal_por_email(correo),
            buscar_mpklog_por_email(correo),
        )
        if deal_id:
            print(f"  ✅  dealId recuperado: {deal_id} ({correo})")
        else:
            print(f"  ⚠️  dealId não encontrado para: {correo}")
        if mpklog_id:
            print(f"  ✅  mpklogId recuperado: {mpklog_id} ({correo})")
        else:
            print(f"  ⚠️  mpklogId não encontrado para: {correo}")

    return {"ok": True, "dealId": deal_id, "mpklogId": mpklog_id}
