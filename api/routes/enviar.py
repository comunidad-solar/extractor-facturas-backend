# api/routes/enviar.py
# Proxy para webhooks externos.
# POST /enviar          — reenvía {cliente, factura} al webhook de Zoho Flow (JSON)
#                         y dispara internamente el backend de cálculo (fire-and-forget).
# POST /enviar/calcular — reenvía datos + PDF al backend de cálculo (multipart).

import json
import os

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from typing import Any, Dict, Optional

ZOHO_WEBHOOK = (
    "https://flow.zoho.eu/20067915739/flow/webhook/incoming"
    "?zapikey=1001.333e94b169d89fa9db9d59ecf859b773.0377ab428b917dde7096df8db25b29eb"
    "&isdebug=false"
)

CALC_BACKEND_URL = os.getenv("CALC_BACKEND_URL", "")

router = APIRouter(prefix="/enviar", tags=["enviar"])


# ---------------------------------------------------------------------------
# Função interna: dispara cálculo sem propagar exceções
# ---------------------------------------------------------------------------

async def _enviar_calculo(
    parsed: Dict[str, Any],
    pdf_bytes: Optional[bytes],
    pdf_filename: Optional[str],
) -> None:
    if not CALC_BACKEND_URL:
        print("[/enviar] _enviar_calculo: CALC_BACKEND_URL não configurada — ignorando")
        return

    files_part: Dict[str, Any] = {}
    if pdf_bytes is not None:
        files_part["file"] = (pdf_filename or "factura.pdf", pdf_bytes, "application/pdf")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                CALC_BACKEND_URL,
                data={"data": json.dumps(parsed, ensure_ascii=False)},
                files=files_part if files_part else None,
            )
        print(f"[/enviar] Cálculo disparado: {resp.status_code}")
    except Exception as e:
        print("[/enviar] ⚠️ Erro ao disparar cálculo:", e)


# ---------------------------------------------------------------------------
# POST /enviar — Zoho Flow (JSON) + disparo interno de cálculo
# ---------------------------------------------------------------------------

@router.post("")
async def enviar_datos(
    data: str = Form(..., description='JSON: {"cliente": {...}, "factura": {...}, "Fsmstate": "...", "FsmPrevious": "...", "ce": {...}}'),
    file: Optional[UploadFile] = File(None, description="PDF de la factura (opcional)"),
):
    """
    Parseia o JSON, envia ao Zoho Flow e, em seguida, dispara o backend de
    cálculo internamente (sem bloquear nem propagar erros do cálculo).
    """
    # --- Validar JSON ---
    try:
        parsed: Dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Campo 'data' no es JSON válido: {e}")

    if "cliente" not in parsed:
        raise HTTPException(status_code=400, detail="Campo 'data' debe contener al menos 'cliente'.")

    print(f"[/enviar] Campos recibidos: {list(parsed.keys())}")

    # --- Ler PDF se presente ---
    pdf_bytes: Optional[bytes] = None
    pdf_filename: Optional[str] = None
    if file is not None:
        is_pdf = (
            file.content_type == "application/pdf"
            or (file.filename or "").lower().endswith(".pdf")
        )
        if not is_pdf:
            raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")
        pdf_bytes = await file.read()
        pdf_filename = file.filename
        print(f"[/enviar] PDF recibido: {pdf_filename!r} ({len(pdf_bytes)} bytes)")

    # --- Enviar JSON ao Zoho Flow ---
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ZOHO_WEBHOOK, json=parsed)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Error de conexión con Zoho Flow")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en Zoho Flow")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de Zoho Flow: {e.response.status_code}")

    print(f"[/enviar] Zoho respondió: {resp.status_code}")

    # --- Disparar cálculo internamente (fire-and-forget) ---
    try:
        await _enviar_calculo(parsed, pdf_bytes, pdf_filename)
    except Exception as e:
        print("[/enviar] ⚠️ Erro ao disparar cálculo:", e)

    return {"ok": True}
