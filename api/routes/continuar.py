# api/routes/continuar.py
# POST /continuar — tela 1 (dados iniciais).
# Envia payload ao Zoho Flow, cria sessão e dispara background task
# para recuperar dealId + mpklogId enquanto o user está na tela 2.

import asyncio
import json
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Form, HTTPException

from api.routes.sesion import crear_sesion, leer_sesion, actualizar_sesion
from api.zoho_crm import refresh_access_token, _buscar_deal_once, _buscar_mpklog_once

ZOHO_WEBHOOK = (
    "https://flow.zoho.eu/20067915739/flow/webhook/incoming"
    "?zapikey=1001.333e94b169d89fa9db9d59ecf859b773.0377ab428b917dde7096df8db25b29eb"
    "&isdebug=false"
)

router = APIRouter(prefix="/continuar", tags=["continuar"])


async def _fetch_ids_background(correo: str, session_id: str) -> None:
    """Loop infinito a cada 10s até encontrar dealId + mpklogId. Não bloqueia o caller."""
    import time
    import os
    t0 = time.monotonic()
    token = os.getenv("ZOHO_ACCESS_TOKEN", "")
    deal_id: str | None = None
    mpklog_id: str | None = None
    attempt = 0

    print(f"[IDs background] INICIO — correo={correo} sessao={session_id[:8]}...")

    MAX_ATTEMPTS = 50  # ~8 minutos máximo (4×3s + 4×5s + 42×10s)
    try:
        while (deal_id is None or mpklog_id is None) and attempt < MAX_ATTEMPTS:
            # Verificar se callback do Zoho já actualizou a sessão
            _sess = leer_sesion(session_id)
            if _sess and _sess.get("dealId") and _sess.get("mpklogId"):
                print(f"[IDs background] IDs ja na sessao via callback — loop encerrado ({round(time.monotonic()-t0,1)}s)")
                return

            attempt += 1
            elapsed = round(time.monotonic() - t0, 1)
            pending = []
            if deal_id is None:
                pending.append("dealId")
            if mpklog_id is None:
                pending.append("mpklogId")
            print(f"[IDs background] tentativa {attempt} ({elapsed}s) — a buscar: {', '.join(pending)}")

            # Buscar em paralelo apenas os que ainda faltam
            tasks = []
            if deal_id is None:
                tasks.append(_buscar_deal_once(correo, token))
            if mpklog_id is None:
                tasks.append(_buscar_mpklog_once(correo, token))

            results = await asyncio.gather(*tasks)
            idx = 0

            if deal_id is None:
                r = results[idx]; idx += 1
                if r == "UNAUTHORIZED":
                    token = await refresh_access_token()
                    print(f"[IDs background] token renovado")
                elif r not in (None, "NOT_FOUND"):
                    deal_id = r
                    print(f"[IDs background] dealId OK: {deal_id} ({round(time.monotonic()-t0,1)}s)")

            if mpklog_id is None:
                r = results[idx]
                if r == "UNAUTHORIZED":
                    token = await refresh_access_token()
                elif r not in (None, "NOT_FOUND"):
                    mpklog_id = r
                    print(f"[IDs background] mpklogId OK: {mpklog_id} ({round(time.monotonic()-t0,1)}s)")

            if deal_id is None or mpklog_id is None:
                # Intervalos crescentes: 3s, 3s, 5s, 5s, depois 10s fixo
                _delays = [3, 3, 5, 5]
                wait = _delays[attempt - 1] if attempt <= len(_delays) else 10
                print(f"[IDs background] aguardando {wait}s...")
                await asyncio.sleep(wait)

        if deal_id is None or mpklog_id is None:
            print(f"[IDs background] TIMEOUT — {MAX_ATTEMPTS} tentativas esgotadas ({round(time.monotonic()-t0,1)}s) — dealId={deal_id} mpklogId={mpklog_id}")
            return

        # Ambos encontrados — actualizar sessão
        elapsed = round(time.monotonic() - t0, 1)
        existing = leer_sesion(session_id)
        if existing is None:
            print(f"[IDs background] sessao {session_id[:8]} expirou — IDs descartados")
            return

        existing["dealId"]   = deal_id
        existing["mpklogId"] = mpklog_id
        if "cliente" in existing and isinstance(existing["cliente"], dict):
            existing["cliente"]["dealId"]   = deal_id
            existing["cliente"]["mpklogId"] = mpklog_id

        actualizar_sesion(session_id, existing)
        print(f"[IDs background] CONCLUIDO em {elapsed}s ({attempt} tentativas) — sessao {session_id[:8]} actualizada")

    except asyncio.CancelledError:
        print(f"[IDs background] cancelado para sessao {session_id[:8]}")
    except Exception as e:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[IDs background] ERRO ({elapsed}s): {e}")


@router.post("")
async def continuar(
    data: str = Form(..., description='JSON: {"cliente": {...}, "ce": {...}, "Fsmstate": "01_DENTRO_ZONA"|"02_FUERA_ZONA", ...}'),
):
    """
    Tela 1 — dados iniciais do cliente.
    1. Envia payload ao Zoho Flow.
    2. Cria sessão com o payload.
    3. Dispara background task para recuperar dealId + mpklogId.
    4. Devolve imediatamente { "ok": true, "session_id": "..." }.
    """
    try:
        parsed: Dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Campo 'data' no es JSON válido: {e}")

    if "cliente" not in parsed:
        raise HTTPException(status_code=400, detail="Campo 'data' debe contener al menos 'cliente'.")

    print(f"[/continuar] Fsmstate={parsed.get('Fsmstate')} correo={parsed.get('cliente', {}).get('correo', '-')}")

    # 1. Enviar ao Zoho Flow
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ZOHO_WEBHOOK, json=parsed)
            resp.raise_for_status()
        print(f"[/continuar] Zoho respondeu: {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Error de conexión con Zoho Flow")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en Zoho Flow")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de Zoho Flow: {e.response.status_code}")

    # 2. Criar sessão
    session_id = crear_sesion(parsed)
    print(f"[/continuar] Sessão criada: {session_id}")

    # 3. Background task — não bloqueia
    correo = parsed.get("cliente", {}).get("correo", "")
    if correo:
        asyncio.create_task(_fetch_ids_background(correo, session_id))
    else:
        print("[/continuar] sem correo — IDs não serão recuperados")

    # 4. Resposta imediata
    return {"ok": True, "session_id": session_id}
