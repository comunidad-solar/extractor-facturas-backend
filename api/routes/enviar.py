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
from api.routes.sesion import crear_sesion, actualizar_sesion, leer_sesion

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

    # --- 1. Enviar JSON ao Zoho Flow ---
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

    # --- 2. Tentar obter dealId/mpklogId da sessão do /continuar (callback Zoho) ---
    correo = parsed.get("cliente", {}).get("correo", "")
    deal_id = None
    mpklog_id = None

    continuar_sid = parsed.get("continuar_session_id")
    if continuar_sid:
        continuar_sess = leer_sesion(continuar_sid)
        if continuar_sess:
            deal_id   = continuar_sess.get("dealId") or continuar_sess.get("cliente", {}).get("dealId")
            mpklog_id = continuar_sess.get("mpklogId") or continuar_sess.get("cliente", {}).get("mpklogId")
            if deal_id:
                print(f"  ✅  dealId via continuar_session: {deal_id}")
            if mpklog_id:
                print(f"  ✅  mpklogId via continuar_session: {mpklog_id}")

    # --- 3. Fallback: buscar no Zoho CRM se ainda em falta ---
    if (deal_id is None or mpklog_id is None) and correo:
        delay = int(os.getenv("ZOHO_DEAL_FETCH_DELAY", "4"))
        await asyncio.sleep(delay)
        if deal_id is None:
            deal_id = await buscar_deal_por_email(correo)
            if deal_id:
                print(f"  ✅  dealId recuperado via CRM: {deal_id} ({correo})")
            else:
                print(f"  ⚠️  dealId não encontrado para: {correo}")
        if mpklog_id is None:
            mpklog_id = await buscar_mpklog_por_email(correo)
            if mpklog_id:
                print(f"  ✅  mpklogId recuperado via CRM: {mpklog_id} ({correo})")
            else:
                print(f"  ⚠️  mpklogId não encontrado para: {correo}")

    # --- 4. Usar factura extraída por Claude (da sessão) se disponível ---
    existing_session_id = parsed.get("session_id")
    existing_session = leer_sesion(existing_session_id) if existing_session_id else None

    if existing_session and "factura" in existing_session:
        factura = existing_session["factura"]
        print(f"[/enviar] factura obtida da sessão Claude ({existing_session_id})")
    else:
        # Fallback: usar factura do frontend, removendo campos legados
        factura = dict(parsed.get("factura") or {})
        factura.pop("archivo", None)
        factura.pop("api", None)
        print(f"[/enviar] factura obtida do payload do frontend (sem sessão prévia)")

    # --- 5. Actualizar ou criar sessão ---
    session_payload = {**parsed, "factura": factura, "dealId": deal_id, "mpklogId": mpklog_id}
    # Actualizar também dentro de cliente para evitar duplicação
    if "cliente" in session_payload:
        session_payload["cliente"]["dealId"]   = deal_id
        session_payload["cliente"]["mpklogId"] = mpklog_id

    if existing_session_id and actualizar_sesion(existing_session_id, session_payload):
        session_id = existing_session_id
        print(f"[/enviar] Sessão actualizada: {session_id}")
    else:
        session_id = crear_sesion(session_payload)
        print(f"[/enviar] Sessão criada (nova): {session_id}")

    return {"ok": True, "dealId": deal_id, "mpklogId": mpklog_id, "session_id": session_id}
