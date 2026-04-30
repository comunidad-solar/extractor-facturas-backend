# Persistent Sessions (SQLite) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist session data in SQLite so that `factura_preview` and full plan payload survive server restarts and are recoverable from any device via `session_id` in the plan URL.

**Architecture:** Add SQLAlchemy ORM + Alembic on top of existing in-memory `_store`. Reads hit memory first, fall back to DB on miss. Writes go to both. `session_id` (UUID) is the primary key — cotizador adds it to the plan URL as `&session_id=xxx` so any device can recover the full session including `factura_preview`.

**Tech Stack:** SQLAlchemy 2.x (sync), Alembic, aiosqlite (not used — sync only), SQLite via `DATABASE_URL` env var, Docker volume for persistence.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `api/db/__init__.py` | Empty package marker |
| Create | `api/db/database.py` | Engine, Base, SessionLocal, `get_db` |
| Create | `api/db/models.py` | `SessionRecord` ORM model |
| Create | `api/db/repository.py` | `save`, `fetch`, `update` — no raw SQL elsewhere |
| Modify | `api/routes/sesion.py` | Use repository for DB read/write alongside `_store` |
| Modify | `api/main.py` | Run Alembic migrations on startup |
| Modify | `requirements.txt` | Add `sqlalchemy`, `alembic` |
| Modify | `.env.example` | Add `DATABASE_URL` |
| Create | `alembic.ini` | Alembic config pointing to `DATABASE_URL` |
| Create | `alembic/env.py` | Alembic env with our `Base.metadata` |
| Create | `alembic/versions/0001_create_sessions.py` | Migration: create `sessions` table |

---

### Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add packages to requirements.txt**

Add after the existing `httpx` line:

```
# Database
sqlalchemy
alembic
```

- [ ] **Step 2: Add DATABASE_URL to .env.example**

Add to `.env.example`:

```env
DATABASE_URL=sqlite:////app/data/sessions.db
```

For local dev (non-Docker), use:
```env
DATABASE_URL=sqlite:///./sessions.db
```

- [ ] **Step 3: Install dependencies**

```bash
pip install sqlalchemy alembic
```

Expected: installs without error. Verify:
```bash
python -c "import sqlalchemy, alembic; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add sqlalchemy and alembic dependencies"
```

---

### Task 2: Create DB package — engine, Base, model, repository

**Files:**
- Create: `api/db/__init__.py`
- Create: `api/db/database.py`
- Create: `api/db/models.py`
- Create: `api/db/repository.py`

- [ ] **Step 1: Create `api/db/__init__.py`**

```python
```
(empty file)

- [ ] **Step 2: Create `api/db/database.py`**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sessions.db")

# check_same_thread=False required for SQLite with multiple threads
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: Create `api/db/models.py`**

```python
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from api.db.database import Base


class SessionRecord(Base):
    __tablename__ = "sessions"

    session_id = Column(String(36), primary_key=True, index=True)
    payload    = Column(Text, nullable=False)        # JSON string
    url        = Column(Text, nullable=True)          # plan URL (metadata)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)      # NULL = persist forever
```

- [ ] **Step 4: Create `api/db/repository.py`**

```python
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
```

- [ ] **Step 5: Commit**

```bash
git add api/db/
git commit -m "feat: add db package with SQLAlchemy engine, Session model and repository"
```

---

### Task 3: Configure Alembic

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (directory)

- [ ] **Step 1: Initialize Alembic**

Run from project root:
```bash
alembic init alembic
```

Expected: creates `alembic.ini` and `alembic/` directory.

- [ ] **Step 2: Edit `alembic.ini` — point to env var**

Find this line in `alembic.ini`:
```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

Replace with:
```ini
sqlalchemy.url =
```
(leave empty — we set it in env.py)

- [ ] **Step 3: Replace `alembic/env.py` with**

```python
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from api.db.database import Base
import api.db.models  # noqa: F401 — ensure models are registered

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sessions.db")


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Commit**

```bash
git add alembic.ini alembic/
git commit -m "chore: configure alembic for session persistence migrations"
```

---

### Task 4: Write and run initial migration

**Files:**
- Create: `alembic/versions/0001_create_sessions_table.py`

- [ ] **Step 1: Generate migration**

```bash
alembic revision --autogenerate -m "create sessions table"
```

Expected: creates `alembic/versions/XXXX_create_sessions_table.py` with `sessions` table.

- [ ] **Step 2: Verify generated migration**

Open the generated file. Confirm `upgrade()` contains:
```python
op.create_table('sessions',
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('session_id')
)
op.create_index(op.f('ix_sessions_session_id'), 'sessions', ['session_id'], unique=False)
```

If autogenerate missed anything, add manually.

- [ ] **Step 3: Run migration locally**

```bash
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create sessions table
```

Verify with:
```bash
python -c "from sqlalchemy import create_engine, inspect; e = create_engine('sqlite:///./sessions.db'); print(inspect(e).get_columns('sessions'))"
```

Expected: list of 5 columns (session_id, payload, url, created_at, expires_at).

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: migration 0001 — create sessions table"
```

---

### Task 5: Modify `sesion.py` — write to DB, fall back on miss

**Files:**
- Modify: `api/routes/sesion.py`

- [ ] **Step 1: Replace `api/routes/sesion.py` with**

```python
# api/routes/sesion.py
# Sessões temporárias — memória (TTL 40min) + SQLite (persistente).
# POST  /sesion        — cria sessão
# GET   /sesion/{id}   — lê sessão (memória → DB fallback)
# PATCH /sesion/{id}   — merge parcial, renova TTL

from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, HTTPException

from api.db.database import SessionLocal
from api.db.repository import db_save_session, db_get_session, db_update_session

_store: dict[str, dict] = {}
router = APIRouter(prefix="/sesion", tags=["sesion"])
_TTL_MINUTES = 40


def crear_sesion(data: Any) -> str:
    session_id = str(uuid4())
    expires_at_mem = datetime.utcnow() + timedelta(minutes=_TTL_MINUTES)
    _store[session_id] = {"data": data, "expires_at": expires_at_mem}
    with SessionLocal() as db:
        db_save_session(db, session_id, data, expires_at=None)  # NULL = forever
    return session_id


def leer_sesion(session_id: str) -> Any | None:
    # 1 — memory hit
    entry = _store.get(session_id)
    if entry is not None:
        if datetime.utcnow() <= entry["expires_at"]:
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
        "expires_at": datetime.utcnow() + timedelta(minutes=_TTL_MINUTES),
    }
    return data


def actualizar_sesion(session_id: str, data: Any) -> bool:
    entry = _store.get(session_id)
    if entry is not None:
        if datetime.utcnow() > entry["expires_at"]:
            del _store[session_id]
        else:
            entry["data"] = data
            entry["expires_at"] = datetime.utcnow() + timedelta(minutes=_TTL_MINUTES)

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
    entry = _store.get(session_id)
    # merge into existing data
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
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from api.routes.sesion import crear_sesion; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add api/routes/sesion.py
git commit -m "feat: persist sessions to SQLite with memory-first read and DB fallback"
```

---

### Task 6: Run Alembic migrations on startup

**Files:**
- Modify: `api/main.py`

- [ ] **Step 1: Add migration call to `api/main.py`**

Add after existing imports:

```python
from alembic.config import Config
from alembic import command
import os
```

Add after `app = FastAPI(...)` and before `app.add_middleware(...)`:

```python
def _run_migrations():
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(__file__), "..", "alembic"),
    )
    command.upgrade(alembic_cfg, "head")

_run_migrations()
```

- [ ] **Step 2: Start server and verify**

```bash
uvicorn api.main:app --reload --port 8000
```

Expected in logs:
```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create sessions table
```

(On subsequent restarts: no migration output — already at head.)

- [ ] **Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat: run alembic migrations automatically on server startup"
```

---

### Task 7: Docker volume for SQLite persistence

**Files:**
- No code change — configuration note for deployment

- [ ] **Step 1: Ensure `data/` directory exists and is in `.gitignore`**

```bash
mkdir -p data
echo "data/" >> .gitignore
```

- [ ] **Step 2: Add to `docker-compose.yml` (create if not exists)**

If `docker-compose.yml` already exists, add the volume to the extractor service:

```yaml
services:
  extractor:
    # ... existing config ...
    environment:
      - DATABASE_URL=sqlite:////app/data/sessions.db
    volumes:
      - ./data:/app/data
```

If no `docker-compose.yml`, create one:

```yaml
version: "3.9"
services:
  extractor:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:////app/data/sessions.db
    volumes:
      - ./data:/app/data
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore docker-compose.yml
git commit -m "chore: add docker volume for SQLite session persistence"
```

---

### Task 8: Manual end-to-end verification

- [ ] **Step 1: Start server**

```bash
uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 2: Create a session via Swagger**

Open http://localhost:8000/docs → `POST /sesion` → body:
```json
{"test": "hello", "factura_preview": {"periodo": "Mes Medio"}}
```

Copy the returned `session_id`.

- [ ] **Step 3: Verify session is in DB**

```bash
python -c "
from api.db.database import SessionLocal
from api.db.repository import db_get_session
with SessionLocal() as db:
    data = db_get_session(db, 'PASTE_SESSION_ID_HERE')
    print(data)
"
```

Expected: dict with `test` and `factura_preview` keys.

- [ ] **Step 4: Restart server (simulates deploy)**

Stop server (Ctrl+C), restart:
```bash
uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 5: Verify session survives restart**

Open http://localhost:8000/docs → `GET /sesion/{session_id}` with the same ID.

Expected: `200` with the original payload. Memory was cleared by restart, DB fallback served it.

- [ ] **Step 6: Test PATCH**

`PATCH /sesion/{session_id}` with body:
```json
{"factura_preview": {"periodo": "Enero 2025", "dias": 31}}
```

Then `GET /sesion/{session_id}` — verify `factura_preview.periodo` is `"Enero 2025"`.

Restart server again, GET again — verify PATCH persisted.

---

## Self-Review

**Spec coverage:**
- ✅ SQLAlchemy ORM — `models.py` + `repository.py`
- ✅ Alembic migrations — Task 3 + 4
- ✅ UUID primary key — `session_id` from `str(uuid4())`
- ✅ Decoupled models — `api/db/` isolated from routes
- ✅ `DATABASE_URL` in `.env` — Task 1
- ✅ No raw SQL scattered — all in `repository.py`
- ✅ No SQLite-specific types — `String`, `Text`, `DateTime` all portable
- ✅ Docker persistence — Task 7
- ✅ Memory-first read, DB fallback — `leer_sesion()`
- ✅ Writes to both — `crear_sesion()`, `actualizar_sesion()`
- ✅ Persistent forever — `expires_at=None`
- ✅ `factura_preview` survives restart — Task 8 verifies

**Note for cotizador team:** Plan URL must include `&session_id={session_id}` so the frontend can pass it to `GET /sesion/{session_id}` from any device/browser.
