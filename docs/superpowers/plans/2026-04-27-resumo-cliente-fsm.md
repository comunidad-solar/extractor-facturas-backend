# Retoma de Processo por FSMState Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the client clicks "Continuar" on Step 1, verify if their email already has an existing deal in Zoho CRM; if so, route them to the correct screen based on their FSMState instead of restarting the flow.

**Architecture:** New backend endpoint `GET /verificar-cliente` queries Zoho CRM's MPK_Logs by email (no retry — synchronous check before flow creation). FSMState determines frontend routing: blocked states show status screens and trigger a Zoho advisor task; `08_PROPUESTA` restores Plan screen from SQLite-stored propuesta data; `07_PERDIDO_NO_CONTRATA_ALQ` continues normally with `fsmPrevious` set.

**Tech Stack:** Python/FastAPI (backend), SQLite via `sqlite3` stdlib (propuesta store), React 19 (frontend), Zoho CRM v8 API

---

## Scope: Two Repos

- **Backend:** `extractor-facturas-backend/`
- **Frontend:** `extractor-facturas-frontend/`

---

## FSMState Routing Table

| FSMState | Action |
|---|---|
| Not found | Continue normal flow (zone check → Step 2) |
| `01_DENTRO_ZONA` | Continue normal flow (zone check → Step 2) |
| `02_FUERA_ZONA` | Show waiting list screen with option A (new deal) or C (new email) |
| `03_CONTRATA` | Block + create advisor Zoho task + show status screen |
| `04_NO_CONTRATA` | Block + create advisor Zoho task + show status screen |
| `05_FIRMA` | Block + create advisor Zoho task + show status screen |
| `06_PAGA` | Block + create advisor Zoho task + show status screen |
| `07_PERDIDO_NO_CONTRATA_ALQ` | Continue normally; set `fsmPrevious = "07_PERDIDO_NO_CONTRATA_ALQ"` |
| `08_PROPUESTA` | Restore Plan Screen from saved propuesta data |

---

## File Map

### Backend (new/modified)
- **Modify:** `api/zoho_crm.py` — extend `_fetch_mpklog` to return `FSM_State`; add `verificar_cliente_por_email()`; add `crear_tarea_asesor()`
- **Create:** `api/db/propuesta.py` — SQLite helper for propuesta persistence
- **Create:** `api/routes/verificar.py` — `GET /verificar-cliente?correo=`
- **Create:** `api/routes/propuesta.py` — `POST /propuesta/guardar`, `GET /propuesta/{correo}`
- **Modify:** `api/main.py` — register two new routers

### Frontend (modified only)
- **Modify:** `src/components/FacturaUpload.jsx` — inject client check in `handleContinuar`; add new status screens; handle each FSMState; save propuesta after QUOTING_URL

---

## Task 1: Extend `_fetch_mpklog` to return FSM_State

**Files:**
- Modify: `api/zoho_crm.py`

- [ ] **Step 1: Add `FSM_State` to mpklog fetch fields**

In `_fetch_mpklog`, change the `fields` param:
```python
# before
"fields": "id,Email",
# after
"fields": "id,Email,FSM_State",
```

Change return type from `str | None | Literal[...]` to `dict | None | Literal[...]`:
```python
async def _fetch_mpklog(correo: str, token: str) -> dict | None | Literal["UNAUTHORIZED", "NOT_FOUND"]:
    url = f"{ZOHO_API_DOMAIN}/crm/v8/MPK_Logs/search"
    params = {
        "criteria":   f"(Email:equals:{correo})",
        "fields":     "id,Email,FSM_State",
        "sort_by":    "id",
        "sort_order": "desc",
        "per_page":   1,
    }
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params, headers=headers)
        if r.status_code == 401:
            return "UNAUTHORIZED"
        if r.status_code == 204:
            return "NOT_FOUND"
        if r.status_code != 200:
            print(f"  ⚠️  MPK_Logs search HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json().get("data", [])
        if not data:
            return "NOT_FOUND"
        row = data[0]
        return {"id": str(row["id"]), "fsm_state": row.get("FSM_State", "")}
```

- [ ] **Step 2: Fix `buscar_mpklog_por_email` to handle dict return**

The existing function returns `str | None`. Update it to return `str | None` (keep interface) — extract just `.id` from the dict:
```python
async def buscar_mpklog_por_email(correo: str) -> str | None:
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")
    result = await _fetch_mpklog(correo, token)
    if result == "UNAUTHORIZED":
        token = await refresh_access_token()
        result = await _fetch_mpklog(correo, token)
    if isinstance(result, dict):
        return result["id"]
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        print(f"  🔄  MPK_Log não encontrado ainda, retry {attempt}/{len(_RETRY_DELAYS)} em {delay}s ({correo})")
        await asyncio.sleep(delay)
        result = await _fetch_mpklog(correo, token)
        if isinstance(result, dict):
            return result["id"]
    print(f"  ⚠️  buscar_mpklog_por_email — mpklogId não encontrado após retries: {correo}")
    return None
```

- [ ] **Step 3: Commit**
```bash
git add api/zoho_crm.py
git commit -m "feat(zoho): fetch FSM_State in mpklog search"
```

---

## Task 2: Add `verificar_cliente_por_email()` to zoho_crm.py

**Files:**
- Modify: `api/zoho_crm.py`

This function is a **fast, no-retry** check — it runs before the deal exists, so "NOT_FOUND" is the expected happy path.

- [ ] **Step 1: Add function**

```python
async def verificar_cliente_por_email(correo: str) -> dict:
    """
    Fast check (no retry). Returns:
      { "exists": False }
      { "exists": True, "deal_id": str, "mpklog_id": str, "fsm_state": str }
    """
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")

    # Fetch mpklog (has FSM_State)
    mpklog_result = await _fetch_mpklog(correo, token)
    if mpklog_result == "UNAUTHORIZED":
        token = await refresh_access_token()
        mpklog_result = await _fetch_mpklog(correo, token)

    if not isinstance(mpklog_result, dict):
        return {"exists": False}

    mpklog_id = mpklog_result["id"]
    fsm_state = mpklog_result.get("fsm_state", "")

    # Fetch deal id
    deal_result = await _fetch_deal(correo, token)
    if deal_result == "UNAUTHORIZED":
        token = await refresh_access_token()
        deal_result = await _fetch_deal(correo, token)
    deal_id = deal_result if isinstance(deal_result, str) and deal_result not in ("UNAUTHORIZED", "NOT_FOUND") else None

    return {
        "exists":     True,
        "deal_id":    deal_id,
        "mpklog_id":  mpklog_id,
        "fsm_state":  fsm_state,
    }
```

- [ ] **Step 2: Commit**
```bash
git add api/zoho_crm.py
git commit -m "feat(zoho): add verificar_cliente_por_email (no-retry fast check)"
```

---

## Task 3: Add `crear_tarea_asesor()` to zoho_crm.py

**Files:**
- Modify: `api/zoho_crm.py`

Creates a Zoho CRM Task linked to the Deal so an advisor knows to contact the client.

- [ ] **Step 1: Add function**

```python
from datetime import date

async def crear_tarea_asesor(deal_id: str, correo: str, fsm_state: str) -> bool:
    """Creates a Zoho CRM Task linked to the deal. Returns True on success."""
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")

    subject = f"[Bot] Cliente volvió — estado: {fsm_state} — {correo}"
    payload = {
        "data": [{
            "Subject":  subject,
            "Due_Date": date.today().isoformat(),
            "Status":   "Not Started",
            "What_Id":  {"id": deal_id, "type": "Deals"},
        }]
    }
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    url = f"{ZOHO_API_DOMAIN}/crm/v8/Tasks"

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code == 401:
            token = await refresh_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code in (200, 201):
            print(f"  ✅  Tarea creada para deal {deal_id} ({correo})")
            return True
        print(f"  ⚠️  Error creando tarea Zoho: {r.status_code} {r.text[:200]}")
        return False
```

- [ ] **Step 2: Commit**
```bash
git add api/zoho_crm.py
git commit -m "feat(zoho): add crear_tarea_asesor — creates CRM task on blocked FSM"
```

---

## Task 4: Create `GET /verificar-cliente` route

**Files:**
- Create: `api/routes/verificar.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create `api/routes/verificar.py`**

```python
# api/routes/verificar.py
# GET /verificar-cliente?correo=X
# Fast pre-flow check: does this email already have a deal?
# If yes and FSMState is a blocker (03/04/05/06), also creates a Zoho advisor task.

from fastapi import APIRouter, HTTPException, Query
from api.zoho_crm import verificar_cliente_por_email, crear_tarea_asesor

router = APIRouter(prefix="/verificar-cliente", tags=["verificar"])

_BLOCKER_STATES = {"03_CONTRATA", "04_NO_CONTRATA", "05_FIRMA", "06_PAGA"}


@router.get("")
async def verificar_cliente(correo: str = Query(..., description="Email del cliente")):
    if not correo or "@" not in correo:
        raise HTTPException(status_code=400, detail="correo inválido")

    result = await verificar_cliente_por_email(correo)

    if not result["exists"]:
        return {"exists": False}

    fsm_state = result.get("fsm_state", "")
    deal_id   = result.get("deal_id")

    # For blocker states: fire-and-forget Zoho advisor task
    if fsm_state in _BLOCKER_STATES and deal_id:
        try:
            await crear_tarea_asesor(deal_id, correo, fsm_state)
        except Exception as e:
            print(f"  ⚠️  crear_tarea_asesor falhou (non-fatal): {e}")

    return {
        "exists":    True,
        "deal_id":   deal_id,
        "mpklog_id": result.get("mpklog_id"),
        "fsm_state": fsm_state,
    }
```

- [ ] **Step 2: Register router in `api/main.py`**

```python
from api.routes.verificar import router as verificar_router
# ...
app.include_router(verificar_router)
```

- [ ] **Step 3: Test manually**

Start API: `uvicorn api.main:app --reload --port 8000`

Test with a known email in Zoho:
```bash
curl "http://localhost:8000/verificar-cliente?correo=test@example.com"
# Expected: {"exists": true, "deal_id": "...", "mpklog_id": "...", "fsm_state": "..."}
```

Test with unknown email:
```bash
curl "http://localhost:8000/verificar-cliente?correo=noexiste@example.com"
# Expected: {"exists": false}
```

- [ ] **Step 4: Commit**
```bash
git add api/routes/verificar.py api/main.py
git commit -m "feat: add GET /verificar-cliente endpoint"
```

---

## Task 5: SQLite propuesta store (Option B)

**Files:**
- Create: `api/db/propuesta.py`
- Create: `api/db/__init__.py`
- Create: `api/routes/propuesta.py`
- Modify: `api/main.py`

Stores the Plan Screen data (QUOTING_URL response) keyed by correo, so it can be recovered when FSMState = `08_PROPUESTA`.

- [ ] **Step 1: Create `api/db/__init__.py`** (empty)

```python
```

- [ ] **Step 2: Create `api/db/propuesta.py`**

```python
# api/db/propuesta.py
# SQLite store for propuesta (plan) data keyed by correo.
# DB file: propuestas.db in project root.

import json
import sqlite3
from pathlib import Path
from datetime import datetime

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "propuestas.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS propuestas (
            correo      TEXT PRIMARY KEY,
            deal_id     TEXT,
            data        TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def guardar_propuesta(correo: str, deal_id: str | None, data: dict) -> None:
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO propuestas (correo, deal_id, data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(correo) DO UPDATE SET
                deal_id    = excluded.deal_id,
                data       = excluded.data,
                updated_at = excluded.updated_at
        """, (correo, deal_id, json.dumps(data), datetime.utcnow().isoformat()))


def leer_propuesta(correo: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM propuestas WHERE correo = ?", (correo,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])
```

- [ ] **Step 3: Create `api/routes/propuesta.py`**

```python
# api/routes/propuesta.py
# POST /propuesta/guardar  — saves plan data for a client
# GET  /propuesta/{correo} — retrieves saved plan data

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from api.db.propuesta import guardar_propuesta, leer_propuesta

router = APIRouter(prefix="/propuesta", tags=["propuesta"])


class PropuestaPayload(BaseModel):
    correo:  str
    deal_id: str | None = None
    data:    dict[str, Any]


@router.post("/guardar")
async def post_guardar_propuesta(body: PropuestaPayload):
    if not body.correo or "@" not in body.correo:
        raise HTTPException(status_code=400, detail="correo inválido")
    guardar_propuesta(body.correo, body.deal_id, body.data)
    return {"ok": True}


@router.get("/{correo:path}")
async def get_propuesta(correo: str):
    data = leer_propuesta(correo)
    if data is None:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    return {"ok": True, "data": data}
```

- [ ] **Step 4: Register router in `api/main.py`**

```python
from api.routes.propuesta import router as propuesta_router
# ...
app.include_router(propuesta_router)
```

- [ ] **Step 5: Add `propuestas.db` to `.gitignore`**

Check current `.gitignore` and add if not present:
```
propuestas.db
```

- [ ] **Step 6: Verify endpoints**

```bash
# Save
curl -X POST http://localhost:8000/propuesta/guardar \
  -H "Content-Type: application/json" \
  -d '{"correo":"test@example.com","deal_id":"123","data":{"ahorro25Anos":15000}}'
# Expected: {"ok": true}

# Retrieve
curl "http://localhost:8000/propuesta/test%40example.com"
# Expected: {"ok": true, "data": {"ahorro25Anos": 15000}}
```

- [ ] **Step 7: Commit**
```bash
git add api/db/ api/routes/propuesta.py api/main.py .gitignore
git commit -m "feat: SQLite propuesta store + GET/POST /propuesta endpoints"
```

---

## Task 6: Frontend — inject client check in `handleContinuar`

**Files:**
- Modify: `src/components/FacturaUpload.jsx`

Inject the `/verificar-cliente` call at the top of `handleContinuar`, before geocoding. If the client has an existing deal, route based on FSMState and return early.

- [ ] **Step 1: Add `clienteExistente` state**

Near the other state declarations (around line 26–110):
```jsx
const [clienteExistente, setClienteExistente] = useState(null);
// { deal_id, mpklog_id, fsm_state } — populated when verificar-cliente finds a match
```

- [ ] **Step 2: Inject check at start of `handleContinuar`**

In `handleContinuar` (line 482), after `if (!validateCliente()) return;` and before `setLoading(true)`:

```jsx
// --- Verificar si ya existe un deal para este correo ---
setLoading(true);
setLoadingMsg("Verificando tu cuenta...");
try {
  const vRes = await fetch(`${API_BASE}/verificar-cliente?correo=${encodeURIComponent(cliente.correo)}`);
  if (vRes.ok) {
    const vData = await vRes.json();
    if (vData.exists) {
      const fsm = vData.fsm_state ?? "";
      setClienteExistente({ deal_id: vData.deal_id, mpklog_id: vData.mpklog_id, fsm_state: fsm });
      setDealId(vData.deal_id ?? null);
      setMpklogId(vData.mpklog_id ?? null);

      if (["03_CONTRATA", "05_FIRMA", "06_PAGA"].includes(fsm)) {
        setStatus("bloqueado_contrata");
        setLoading(false);
        return;
      }
      if (fsm === "04_NO_CONTRATA") {
        setStatus("bloqueado_no_contrata");
        setLoading(false);
        return;
      }
      if (fsm === "08_PROPUESTA") {
        // Recover plan screen
        await _recuperarPropuesta(vData.deal_id, cliente.correo);
        setLoading(false);
        return;
      }
      if (fsm === "07_PERDIDO_NO_CONTRATA_ALQ") {
        setFsmPrevious("07_PERDIDO_NO_CONTRATA_ALQ");
        // fall through to normal zone check
      }
      // 01_DENTRO_ZONA or anything else → fall through to normal flow
    }
  }
} catch (e) {
  console.warn("[handleContinuar] verificar-cliente falhou (non-fatal):", e);
}
// --- End verificar ---
setLoadingMsg("Verificando tu ubicación...");
```

> **Note:** Remove the original `setLoading(true); setLoadingMsg("Verificando tu ubicación...");` lines that were at the top, since they're now inside the block above (after the check sets loading). Actually keep the structure: the original `setLoading(true)` moves to just before the verify block, and the `setLoadingMsg` is updated as shown.

- [ ] **Step 3: Add `_recuperarPropuesta` helper function** (add near other handlers, before `handleContinuar`)

```jsx
const _recuperarPropuesta = async (dealId, correo) => {
  try {
    const r = await fetch(`${API_BASE}/propuesta/${encodeURIComponent(correo)}`);
    if (!r.ok) throw new Error("not found");
    const { data } = await r.json();
    setPlanData(data);
    setStatus("sent"); // "sent" renders PlanScreen
  } catch {
    // No saved propuesta → continue to Step 2 as if new
    setStep(2);
  }
};
```

- [ ] **Step 4: Commit**
```bash
git add src/components/FacturaUpload.jsx
git commit -m "feat(frontend): check existing deal on Continuar, route by FSMState"
```

---

## Task 7: Frontend — blocked FSM status screens

**Files:**
- Modify: `src/components/FacturaUpload.jsx`

Add two new status screens rendered in the existing conditional section (around line 1411 where `fuera_zona` renders).

- [ ] **Step 1: Add `bloqueado_contrata` screen**

After the `fuera_zona` block (around line 1428), add:

```jsx
{!loading && status === "bloqueado_contrata" && (
  <div className="cs-results-card fade-in" style={{ textAlign: "center", padding: "60px 40px" }}>
    <p style={{ fontSize: 20, fontWeight: 700, color: "#121212", marginBottom: 12 }}>
      Tu proceso está en marcha
    </p>
    <p style={{ fontSize: 15, color: "#555", marginBottom: 8 }}>
      Tu solicitud ya está en proceso. Estamos preparando tu contrato.
    </p>
    <p style={{ fontSize: 14, color: "#777", marginBottom: 32 }}>
      Estado: <strong>{clienteExistente?.fsm_state}</strong><br />
      Revisa tu correo electrónico para los próximos pasos.
    </p>
    <button
      className="cs-btn-primary"
      onClick={() => window.open("https://wa.me/34XXXXXXXXX", "_blank")}
    >
      Hablar con un asesor
    </button>
    <button
      className="cs-btn-ghost"
      style={{ marginTop: 12 }}
      onClick={() => { setStatus("idle"); setClienteExistente(null); }}
    >
      Volver
    </button>
  </div>
)}
```

> **Note:** Replace `34XXXXXXXXX` with the real WhatsApp number before shipping.

- [ ] **Step 2: Add `bloqueado_no_contrata` screen**

```jsx
{!loading && status === "bloqueado_no_contrata" && (
  <div className="cs-results-card fade-in" style={{ textAlign: "center", padding: "60px 40px" }}>
    <p style={{ fontSize: 20, fontWeight: 700, color: "#121212", marginBottom: 12 }}>
      Tienes una solicitud anterior
    </p>
    <p style={{ fontSize: 15, color: "#555", marginBottom: 8 }}>
      Anteriormente decidiste no continuar. Si has cambiado de opinión, un asesor puede ayudarte.
    </p>
    <p style={{ fontSize: 14, color: "#777", marginBottom: 32 }}>
      Revisa tu correo o contacta con nosotros.
    </p>
    <button
      className="cs-btn-primary"
      onClick={() => window.open("https://wa.me/34XXXXXXXXX", "_blank")}
    >
      Hablar con un asesor
    </button>
    <button
      className="cs-btn-ghost"
      style={{ marginTop: 12 }}
      onClick={() => { setStatus("idle"); setClienteExistente(null); }}
    >
      Volver
    </button>
  </div>
)}
```

- [ ] **Step 3: Add `02_FORA_ZONA` screen with options A and C**

The existing `fuera_zona` status screen (around line 1411) currently shows a waiting list message. Update it to include two options:

**Option A** — Try with same email but new address (clear form, stay on Step 1):
```jsx
<button
  className="cs-btn-ghost"
  style={{ marginTop: 12 }}
  onClick={() => {
    // Clear address + coords, keep name/email/phone, allow re-submission
    setCliente(prev => ({ ...prev, direccion: "" }));
    setUserCoords(null);
    setClienteExistente(null);
    setStatus("idle");
    setStep(1);
  }}
>
  Probar con otra dirección
</button>
```

**Option C** — Use a different email (full reset):
```jsx
<button
  className="cs-btn-ghost"
  style={{ marginTop: 12 }}
  onClick={() => handleVolver()}
>
  Empezar con otro correo
</button>
```

- [ ] **Step 4: Commit**
```bash
git add src/components/FacturaUpload.jsx
git commit -m "feat(frontend): add blocked FSM status screens (contrata, no_contrata, fuera_zona options)"
```

---

## Task 8: Frontend — save propuesta after QUOTING_URL

**Files:**
- Modify: `src/components/FacturaUpload.jsx`

After `setPlanData(proposta)` in `handleEnviar` (around line 991–1075), fire-and-forget save to `/propuesta/guardar`.

- [ ] **Step 1: Find where `setPlanData` is called after QUOTING_URL**

Locate the block around line 1075:
```jsx
setPlanData(proposta);
setPanelesSel(panelesPropuesta);
```

- [ ] **Step 2: Add fire-and-forget save after `setPlanData`**

```jsx
setPlanData(proposta);
setPanelesSel(panelesPropuesta ?? 3);

// Save propuesta for potential 08_PROPUESTA recovery
const _correo = cliente?.correo ?? buildClientePayload()?.correo ?? "";
const _dealId = dealId ?? null;
if (_correo) {
  fetch(`${API_BASE}/propuesta/guardar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ correo: _correo, deal_id: _dealId, data: proposta }),
  }).catch(() => {});
}
```

Also add the same save in the `handleEnviar` path that sets `setPlanData` for the regular (non-optimizer) flow. Search for all `setPlanData(` calls and add the save after each one that receives quoting data (skip the `setPlanData(null)` reset call).

- [ ] **Step 3: Commit**
```bash
git add src/components/FacturaUpload.jsx
git commit -m "feat(frontend): save propuesta to backend after QUOTING_URL for 08_PROPUESTA recovery"
```

---

## Task 9: Frontend — `07_PERDIDO_NO_CONTRATA_ALQ` in `handleContratar`

**Files:**
- Modify: `src/components/FacturaUpload.jsx`

When `fsmPrevious` is `"07_PERDIDO_NO_CONTRATA_ALQ"`, `handleContratar` must send `Fsmstate: "01_DENTRO_ZONA"` and `FsmPrevious: "07_PERDIDO_NO_CONTRATA_ALQ"`.

- [ ] **Step 1: Locate Fsmstate determination in `handleContratar`**

Find the section in `handleContratar` (around line 1200+) where `Fsmstate` is assigned. It currently uses the current `fsmstate` value. The state is already set to `01_DENTRO_ZONA` (since the zone check ran normally for `07`), so `fsmPrevious` just needs to be set.

Verify that when `07_PERDIDO_NO_CONTRATA_ALQ` flow goes through Task 6's `setFsmPrevious("07_PERDIDO_NO_CONTRATA_ALQ")`, that value is picked up in `handleContratar` at the `FsmPrevious` field:

```jsx
FsmPrevious: fsmPrevious,   // already in the payload — should now carry "07_PERDIDO_NO_CONTRATA_ALQ"
```

No code change needed if `fsmPrevious` state is already wired to `FsmPrevious` in the payload (confirmed at line 905). **Only verify** that `setFsmPrevious` in Task 6 Step 2 is the correct setter.

- [ ] **Step 2: Verify with console log**

In `handleContratar`, the existing debug log at line 1101 shows current state. Add temporarily:
```jsx
console.log("[handleContratar] fsmPrevious:", fsmPrevious);
```

Test the `07_PERDIDO` path manually, confirm `fsmPrevious` shows `"07_PERDIDO_NO_CONTRATA_ALQ"` in the log.

Remove the log after confirming.

- [ ] **Step 3: Commit**
```bash
git add src/components/FacturaUpload.jsx
git commit -m "feat(frontend): wire fsmPrevious=07_PERDIDO_NO_CONTRATA_ALQ through handleContratar"
```

---

## Task 10: Integration test — manual E2E

No automated tests in this project. Manual checklist via browser + Swagger UI.

- [ ] **Test: New client (no deal)**
  1. Fill Step 1 with email not in Zoho → click Continuar
  2. Verify: zone check runs, Step 2 loads
  3. Network tab: `GET /verificar-cliente` returns `{"exists": false}`

- [ ] **Test: Existing `03_CONTRATA` client**
  1. Fill Step 1 with email in Zoho that has FSM `03_CONTRATA` → click Continuar
  2. Verify: `bloqueado_contrata` screen shown
  3. Zoho CRM: task created on that deal
  4. Network tab: `GET /verificar-cliente` returns `{"exists": true, "fsm_state": "03_CONTRATA"}`

- [ ] **Test: Existing `08_PROPUESTA` client**
  1. First: complete a flow (upload PDF → Enviar → plan loads) with email X
  2. Verify: `POST /propuesta/guardar` called (Network tab)
  3. Refresh browser / new session → fill Step 1 with email X → click Continuar
  4. Verify: Plan Screen appears with saved plan data

- [ ] **Test: `07_PERDIDO` client**
  1. Fill Step 1 with email that has FSM `07_PERDIDO_NO_CONTRATA_ALQ`
  2. Verify: zone check runs normally, Step 2 loads
  3. Complete flow → click Contratar
  4. Verify in Zoho: `FsmPrevious = 07_PERDIDO_NO_CONTRATA_ALQ`, `Fsmstate = 01_DENTRO_ZONA`

- [ ] **Test: `02_FUERA_ZONA` with new address**
  1. Fill Step 1 with email that has FSM `02_FUERA_ZONA`
  2. Current behavior: zone check runs, shows `fuera_zona` screen
  3. Click "Probar con otra dirección": form resets address only
  4. Enter new address in zone → Continuar → zone check finds CE → Step 2

- [ ] **Final commit**
```bash
git add .
git commit -m "chore: post-integration cleanup"
```

---

## Open Points / Decisions Left

| # | Question | Decision |
|---|---|---|
| 1 | WhatsApp number for "Hablar con asesor" button | Fill in Task 7 Step 1 and 2 before shipping |
| 2 | `02_FORA_ZONA` Option A: if client retries with new address and is now in zone, does the old `02_FUERA_ZONA` deal get updated? Currently: new deal created by Flow (normal flow). If this creates duplicates, consider adding logic to pass `dealId` in the payload to Flow so it updates instead. | Defer unless duplicates are a problem |
| 3 | `08_PROPUESTA` recovery: propuesta TTL. Currently SQLite keeps forever. Add cleanup? | Defer |
| 4 | Option A (save propuesta in Zoho MPK_Log via Flow) is not implemented here — only Option B (SQLite). If Zoho persistence is needed across server restarts, implement Option A separately. | Addressed by Option B for now |
