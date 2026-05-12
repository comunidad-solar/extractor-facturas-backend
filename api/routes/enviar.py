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
from api.zoho_workdrive import upload_pdf_to_deal_workdrive

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

    # --- 1. Substituir factura pela versão Claude (da sessão) se disponível ---
    existing_session_id = parsed.get("session_id")
    existing_session = leer_sesion(existing_session_id) if existing_session_id else None

    if existing_session and "factura" in existing_session:
        parsed["factura"] = existing_session["factura"]
        print(f"[/enviar] factura substituída pela versão Claude (sessão {existing_session_id})")
    else:
        factura = dict(parsed.get("factura") or {})
        factura.pop("archivo", None)
        factura.pop("api", None)
        parsed["factura"] = factura
        print(f"[/enviar] factura obtida do payload do frontend (sem sessão Claude)")

    # Injectar campos de suministro da sessão AI (top-level) se não estiverem na factura
    for field in ("nombre_cliente", "direccion_suministro", "suministro_lat", "suministro_lon"):
        if existing_session and existing_session.get(field) is not None:
            parsed["factura"].setdefault(field, existing_session[field])

    # --- 2. Enviar JSON ao Zoho Flow (com factura Claude) ---
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

    # --- 3. Tentar obter dealId/mpklogId da sessão do /continuar (callback Zoho) ---
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

    # --- 4. Fallback: buscar no Zoho CRM se ainda em falta ---
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

    # --- 5. Actualizar ou criar sessão ---
    session_payload = {**parsed, "factura": parsed["factura"], "dealId": deal_id, "mpklogId": mpklog_id}
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

    # Upload PDF para WorkDrive do deal (non-blocking)
    extraction_folder_id = (existing_session or {}).get("workdrive_id")
    if deal_id and extraction_folder_id:
        print(f"  ⏳  WorkDrive deal: agendando upload PDF → deal {deal_id}")
        asyncio.create_task(
            upload_pdf_to_deal_workdrive(
                deal_id=deal_id,
                extraction_folder_id=extraction_folder_id,
            )
        )

    return {"ok": True, "dealId": deal_id, "mpklogId": mpklog_id, "session_id": session_id}
