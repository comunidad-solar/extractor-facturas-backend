# api/routes/ce.py
# GET /ce/foto?name={nombre_ce}  — busca foto de CE por Name en Zoho CRM
# GET /ces                       — lista todas las CEs con coords (caché 5 min)

import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from api.zoho_crm import buscar_foto_ce, refresh_access_token, ZOHO_API_DOMAIN

import os

router = APIRouter(prefix="/ce", tags=["ce"])
ces_router = APIRouter(prefix="/ces", tags=["ces"])

# ── Cache en memoria ─────────────────────────────────────────────────────────
_CACHE_TTL = 300  # 5 minutos
_ces_cache: dict[str, Any] = {"data": None, "ts": 0.0}


def _parse_coord(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except ValueError:
        pass
    m = re.match(r"""(\d+)°(\d+)'([\d.]+)"([NSEW])""", str(val).strip())
    if m:
        deg, mins, secs, direction = m.groups()
        decimal = float(deg) + float(mins) / 60 + float(secs) / 3600
        return -decimal if direction in ("S", "W") else decimal
    return None


async def _fetch_ces_zoho(token: str) -> list[dict]:
    """Pagina por Comunidades_Energ_ticas hasta agotar more_records."""
    url = f"{ZOHO_API_DOMAIN}/crm/v8/Comunidades_Energ_ticas"
    fields = "Name,Direcci_n,Latitud,Longitud,Radio_en_metros,Estatus,Etiqueta"
    records: list[dict] = []
    page = 1

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = {"fields": fields, "per_page": 200, "page": page}
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            r = await client.get(url, params=params, headers=headers)

            if r.status_code == 401:
                return []  # señal de token expirado — el llamador renueva
            if r.status_code == 204:
                break  # sin más registros
            r.raise_for_status()

            body = r.json()
            records.extend(body.get("data", []))

            info = body.get("info", {})
            if not info.get("more_records", False):
                break
            page += 1

    return records


def _transform(records: list[dict]) -> list[dict]:
    out = []
    for rec in records:
        lat = _parse_coord(rec.get("Latitud"))
        lng = _parse_coord(rec.get("Longitud"))
        if lat is None or lng is None:
            continue  # excluir CEs sin coordenadas
        if rec.get("Estatus") == "Inactiva":
            continue  # excluir CEs inactivas

        radio_raw = rec.get("Radio_en_metros")
        try:
            radio = int(radio_raw) if radio_raw is not None else 5000
        except (ValueError, TypeError):
            radio = 5000

        out.append({
            "name":        rec.get("Name") or "",
            "addressName": rec.get("Direcci_n") or "",
            "lat":         lat,
            "lng":         lng,
            "radioMetros": radio,
            "status":      rec.get("Estatus") or "",
            "etiqueta":    rec.get("Etiqueta") or "",
        })
    return out


async def _get_ces_data() -> list[dict]:
    """Devuelve CEs desde caché o Zoho (con refresh de token si 401)."""
    now = time.monotonic()
    if _ces_cache["data"] is not None and now - _ces_cache["ts"] < _CACHE_TTL:
        return _ces_cache["data"]

    token = os.getenv("ZOHO_ACCESS_TOKEN", "")
    records = await _fetch_ces_zoho(token)

    if not records:
        # puede ser token expirado — renovar y reintentar
        token = await refresh_access_token()
        records = await _fetch_ces_zoho(token)

    result = _transform(records)
    _ces_cache["data"] = result
    _ces_cache["ts"] = now
    print(f"[/ces] cache actualizado — {len(result)} CEs con coordenadas")
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/foto")
async def get_foto_ce(name: str = Query(..., description="Nombre exacto de la CE")):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Parámetro 'name' vacío.")

    foto_url = await buscar_foto_ce(name)

    if foto_url is None:
        raise HTTPException(status_code=404, detail={"foto_url": None})

    return {"foto_url": foto_url}


@ces_router.get("")
async def get_ces():
    """
    Lista todas las Comunidades Energéticas del CRM con coordenadas válidas.
    Caché en memoria de 5 minutos.
    """
    try:
        data = await _get_ces_data()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al consultar Zoho CRM: {e}")

    return {"data": data}
