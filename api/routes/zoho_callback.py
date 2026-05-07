# api/routes/zoho_callback.py
# POST /zoho/ids-callback
# Recebe dealId + mpklogId do Zoho Flow após criação dos registos.
# Actualiza a sessão correspondente ao correo.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.routes.sesion import _store, actualizar_sesion

router = APIRouter(prefix="/zoho", tags=["zoho"])


class IdsCallbackPayload(BaseModel):
    correo: str
    dealId: str
    mpklogId: str


@router.post("/ids-callback")
async def ids_callback(payload: IdsCallbackPayload):
    print(f"[zoho/ids-callback] *** CALLBACK RECEBIDO *** correo={payload.correo} dealId={payload.dealId} mpklogId={payload.mpklogId}")
    correo = payload.correo.strip().lower()

    # Encontrar sessão pelo correo (percorrer _store em memória)
    session_id = None
    for sid, entry in list(_store.items()):
        data = entry.get("data", {})
        if isinstance(data, dict):
            c = data.get("cliente", {})
            if isinstance(c, dict) and c.get("correo", "").strip().lower() == correo:
                session_id = sid
                break

    if session_id is None:
        print(f"[zoho/ids-callback] sessao nao encontrada para correo={correo}")
        raise HTTPException(status_code=404, detail="Sessão não encontrada para este correo.")

    from api.routes.sesion import leer_sesion
    existing = leer_sesion(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Sessão expirada.")

    existing["dealId"]   = payload.dealId
    existing["mpklogId"] = payload.mpklogId
    if "cliente" in existing and isinstance(existing["cliente"], dict):
        existing["cliente"]["dealId"]   = payload.dealId
        existing["cliente"]["mpklogId"] = payload.mpklogId

    actualizar_sesion(session_id, existing)
    print(f"[zoho/ids-callback] sessao {session_id[:8]} actualizada — dealId={payload.dealId} mpklogId={payload.mpklogId}")

    return {"ok": True}
