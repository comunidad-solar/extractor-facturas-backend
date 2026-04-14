# api/routes/sesion.py
# Sessões temporárias em memória.
# POST /sesion        — cria sessão com TTL de 30 minutos
# GET  /sesion/{id}   — lê sessão (apaga se expirada)

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from typing import Any

_store: dict[str, dict] = {}
# { session_id: { "data": {...}, "expires_at": datetime } }

router = APIRouter(prefix="/sesion", tags=["sesion"])

_TTL_MINUTES = 40


def crear_sesion(data: Any) -> str:
    """Guarda data no store e devolve o session_id gerado."""
    session_id = str(uuid4())
    _store[session_id] = {
        "data":       data,
        "expires_at": datetime.utcnow() + timedelta(minutes=_TTL_MINUTES),
    }
    return session_id


@router.post("")
async def post_sesion(body: Any = None):
    session_id = crear_sesion(body)
    return {"session_id": session_id}


@router.get("/{session_id}")
async def get_sesion(session_id: str):
    entry = _store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if datetime.utcnow() > entry["expires_at"]:
        del _store[session_id]
        raise HTTPException(status_code=410, detail="Sessão expirada.")
    return entry["data"]
