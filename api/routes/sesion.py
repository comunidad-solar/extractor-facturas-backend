# api/routes/sesion.py
# Sessões temporárias em memória.
# POST  /sesion        — cria sessão com TTL de 40 minutos
# GET   /sesion/{id}  — lê sessão (apaga se expirada)
# PATCH /sesion/{id}  — merge parcial nos dados existentes, renova TTL

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


def leer_sesion(session_id: str) -> Any | None:
    """Devuelve los datos de la sesión o None si no existe/expiró."""
    entry = _store.get(session_id)
    if entry is None:
        return None
    if datetime.utcnow() > entry["expires_at"]:
        del _store[session_id]
        return None
    return entry["data"]


def actualizar_sesion(session_id: str, data: Any) -> bool:
    """Actualiza los datos de una sesión existente. Devuelve False si no existe o expiró."""
    entry = _store.get(session_id)
    if entry is None:
        return False
    if datetime.utcnow() > entry["expires_at"]:
        del _store[session_id]
        return False
    entry["data"] = data
    entry["expires_at"] = datetime.utcnow() + timedelta(minutes=_TTL_MINUTES)  # renueva TTL
    return True


@router.post("")
async def post_sesion(body: Any = None):
    session_id = crear_sesion(body)
    return {"session_id": session_id}


@router.patch("/{session_id}")
async def patch_sesion(session_id: str, body: dict = None):
    entry = _store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if datetime.utcnow() > entry["expires_at"]:
        del _store[session_id]
        raise HTTPException(status_code=410, detail="Sessão expirada.")
    if isinstance(entry["data"], dict) and isinstance(body, dict):
        entry["data"].update(body)
    else:
        entry["data"] = body
    entry["expires_at"] = datetime.utcnow() + timedelta(minutes=_TTL_MINUTES)
    return {"ok": True}


@router.get("/{session_id}")
async def get_sesion(session_id: str):
    entry = _store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if datetime.utcnow() > entry["expires_at"]:
        del _store[session_id]
        raise HTTPException(status_code=410, detail="Sessão expirada.")
    return entry["data"]
