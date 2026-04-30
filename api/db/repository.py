import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from api.db.models import SessionRecord


def db_save_session(db: Session, session_id: str, payload: Any, expires_at=None) -> None:
    """Insert or replace a session record."""
    url = payload.get("url") if isinstance(payload, dict) else None
    record = SessionRecord(
        session_id=session_id,
        payload=json.dumps(payload, ensure_ascii=False, default=str),
        url=url,
        expires_at=expires_at,
    )
    db.merge(record)  # insert or update
    db.commit()


def db_get_session(db: Session, session_id: str) -> Any | None:
    """Return parsed payload or None if not found."""
    record = db.get(SessionRecord, session_id)
    if record is None:
        return None
    if record.expires_at and datetime.utcnow() > record.expires_at:
        db.delete(record)
        db.commit()
        return None
    return json.loads(record.payload)


def db_update_session(db: Session, session_id: str, payload: Any) -> bool:
    """Update payload of existing session. Returns False if not found."""
    record = db.get(SessionRecord, session_id)
    if record is None:
        return False
    if record.expires_at and datetime.utcnow() > record.expires_at:
        db.delete(record)
        db.commit()
        return False
    url = payload.get("url") if isinstance(payload, dict) else None
    record.payload = json.dumps(payload, ensure_ascii=False, default=str)
    if url:
        record.url = url
    db.commit()
    return True
