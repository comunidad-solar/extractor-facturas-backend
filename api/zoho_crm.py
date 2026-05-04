# api/zoho_crm.py
# Integração com Zoho CRM (EU).
# Funções:
#   refresh_access_token() — renova o access_token via refresh_token
#   buscar_deal_por_email() — busca o deal mais recente por email do cliente

import asyncio
import os
from typing import Literal

import httpx

ZOHO_API_DOMAIN = os.getenv("ZOHO_API_DOMAIN", "https://www.zohoapis.eu")

# Retry: tentar até N vezes com intervalo crescente (segundos)
_RETRY_DELAYS = [5, 10, 15]  # total máx ~30s extra após o delay inicial


async def refresh_access_token() -> str:
    url = "https://accounts.zoho.eu/oauth/v2/token"
    params = {
        "grant_type":    "refresh_token",
        "client_id":     os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, params=params)
        r.raise_for_status()
        data = r.json()
        token = data["access_token"]
        os.environ["ZOHO_ACCESS_TOKEN"] = token
        return token


async def _fetch_deal(correo: str, token: str) -> str | None | Literal["UNAUTHORIZED", "NOT_FOUND"]:
    """
    Retorna:
      str           — id do deal encontrado
      "UNAUTHORIZED"— token inválido/expirado (401)
      "NOT_FOUND"   — deal não existe ainda (204)
      None          — erro inesperado
    """
    url = f"{ZOHO_API_DOMAIN}/crm/v8/Deals/search"
    params = {
        "criteria":   f"(Correo_electr_nico1:equals:{correo})",
        "fields":     "id,Deal_Name,Correo_electr_nico1",
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
            # Deal ainda não criado pelo Flow
            return "NOT_FOUND"
        if r.status_code != 200:
            print(f"  ⚠️  Zoho CRM search HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json().get("data", [])
        if not data:
            return "NOT_FOUND"
        return str(data[0]["id"])


async def _fetch_mpklog(correo: str, token: str) -> str | None | Literal["UNAUTHORIZED", "NOT_FOUND"]:
    url = f"{ZOHO_API_DOMAIN}/crm/v8/MPK_Logs/search"
    params = {
        "criteria":   f"(Email:equals:{correo})",
        "fields":     "id,Email",
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
        return str(data[0]["id"])


async def buscar_mpklog_por_email(correo: str) -> str | None:
    """
    Busca o MPK_Log com retry automático para acomodar a latência do Zoho Flow.
    Tenta até len(_RETRY_DELAYS)+1 vezes antes de desistir.
    """
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")

    # Primeira tentativa
    result = await _fetch_mpklog(correo, token)

    # Refresh de token se necessário (só uma vez)
    if result == "UNAUTHORIZED":
        token = await refresh_access_token()
        result = await _fetch_mpklog(correo, token)

    # Se já encontrou, retornar imediatamente
    if result not in ("NOT_FOUND", "UNAUTHORIZED", None):
        return result

    # Retry com backoff para dar tempo ao Flow criar o registo
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        print(f"  🔄  MPK_Log não encontrado ainda, retry {attempt}/{len(_RETRY_DELAYS)} em {delay}s ({correo})")
        await asyncio.sleep(delay)
        result = await _fetch_mpklog(correo, token)
        if result not in ("NOT_FOUND", "UNAUTHORIZED", None):
            return result

    print(f"  ⚠️  buscar_mpklog_por_email — mpklogId não encontrado após retries: {correo}")
    return None


async def buscar_foto_ce(nombre_ce: str) -> str | None:
    """Busca CE por Name exacto en Comunidades_Energ_ticas y devuelve Image_URL o None."""
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")
    url = f"{ZOHO_API_DOMAIN}/crm/v8/Comunidades_Energ_ticas/search"
    params = {
        "criteria": f"(Name:equals:{nombre_ce.strip()})",
        "fields":   "Name,Image_URL",
        "per_page": 1,
    }

    async def _fetch(t: str) -> str | None | Literal["UNAUTHORIZED"]:
        headers = {"Authorization": f"Zoho-oauthtoken {t}"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params, headers=headers)
        if r.status_code == 401:
            return "UNAUTHORIZED"
        if r.status_code == 204:
            return None
        if r.status_code != 200:
            print(f"  [ce/foto] Zoho HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json().get("data", [])
        if not data:
            return None
        return data[0].get("Image_URL") or None

    result = await _fetch(token)
    if result == "UNAUTHORIZED":
        token = await refresh_access_token()
        result = await _fetch(token)
    return result if result != "UNAUTHORIZED" else None


async def buscar_deal_por_email(correo: str) -> str | None:
    """
    Busca o deal com retry automático para acomodar a latência do Zoho Flow.
    Tenta até len(_RETRY_DELAYS)+1 vezes antes de desistir.
    """
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")

    # Primeira tentativa
    result = await _fetch_deal(correo, token)

    # Refresh de token se necessário (só uma vez)
    if result == "UNAUTHORIZED":
        token = await refresh_access_token()
        result = await _fetch_deal(correo, token)

    # Se já encontrou, retornar imediatamente
    if result not in ("NOT_FOUND", "UNAUTHORIZED", None):
        return result

    # Retry com backoff para dar tempo ao Flow criar o deal
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        print(f"  🔄  Deal não encontrado ainda, retry {attempt}/{len(_RETRY_DELAYS)} em {delay}s ({correo})")
        await asyncio.sleep(delay)
        result = await _fetch_deal(correo, token)
        if result not in ("NOT_FOUND", "UNAUTHORIZED", None):
            return result

    print(f"  ⚠️  buscar_deal_por_email — deal não encontrado após retries: {correo}")
    return None
