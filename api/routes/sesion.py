# api/routes/sesion.py
# Sessões temporárias — memória (TTL 40min) + SQLite (persistente).
# POST  /sesion        — cria sessão
# GET   /sesion/{id}   — lê sessão (memória → DB fallback)
# PATCH /sesion/{id}   — merge parcial, renova TTL

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, HTTPException

from api.db.database import SessionLocal
from api.db.repository import db_save_session, db_get_session, db_update_session

_store: dict[str, dict] = {}
# { session_id: { "data": Any, "expires_at": datetime } }
router = APIRouter(prefix="/sesion", tags=["sesion"])
_TTL_MINUTES = 40


def crear_sesion(data: Any) -> str:
    session_id = str(uuid4())
    expires_at_mem = datetime.now(timezone.utc) + timedelta(minutes=_TTL_MINUTES)
    _store[session_id] = {"data": data, "expires_at": expires_at_mem}
    with SessionLocal() as db:
        db_save_session(db, session_id, data, expires_at=None)  # NULL = forever
    return session_id


def leer_sesion(session_id: str) -> Any | None:
    # 1 — memory hit
    entry = _store.get(session_id)
    if entry is not None:
        if datetime.now(timezone.utc) <= entry["expires_at"]:
            return entry["data"]
        del _store[session_id]

    # 2 — DB fallback
    with SessionLocal() as db:
        data = db_get_session(db, session_id)
    if data is None:
        return None
    # restore to memory for subsequent fast reads
    _store[session_id] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=_TTL_MINUTES),
    }
    return data


def actualizar_sesion(session_id: str, data: Any) -> bool:
    entry = _store.get(session_id)
    if entry is not None:
        if datetime.now(timezone.utc) > entry["expires_at"]:
            del _store[session_id]
        else:
            entry["data"] = data
            entry["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=_TTL_MINUTES)

    with SessionLocal() as db:
        updated = db_update_session(db, session_id, data)

    if not updated:
        # session exists in memory but not in DB yet (edge case) — save it
        if session_id in _store:
            with SessionLocal() as db:
                db_save_session(db, session_id, data, expires_at=None)
            return True
        return False
    return True


@router.post("")
async def post_sesion(body: Any = None):
    session_id = crear_sesion(body)
    return {"session_id": session_id}


@router.patch("/{session_id}")
async def patch_sesion(session_id: str, body: dict = None):
    existing = leer_sesion(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if isinstance(existing, dict) and isinstance(body, dict):
        merged = {**existing, **body}
    else:
        merged = body
    actualizar_sesion(session_id, merged)
    return {"ok": True}


@router.get("/{session_id}")
async def get_sesion(session_id: str):
    data = leer_sesion(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return data
