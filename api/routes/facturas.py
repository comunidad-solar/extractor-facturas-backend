# api/routes/facturas.py
# Endpoint POST /facturas/extraer
# Usa Claude API como caminho de extracção principal.
# Ingebau desactivado temporalmente.

import asyncio
import json
import os
from typing import Optional

import anthropic
from fastapi import APIRouter, Form, UploadFile, File, HTTPException

from api.claude.extractor import extract_with_claude
from api.models import ExtractionResponseAI
from api.routes.sesion import crear_sesion
from api.zoho_crm import buscar_deal_por_email, buscar_mpklog_por_email

router = APIRouter(prefix="/facturas", tags=["facturas"])

RESULTADOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)

_EXCLUDE = {"api_ok", "api_error", "fichero_json"}


@router.post("/extraer", response_model=ExtractionResponseAI,
             response_model_exclude=_EXCLUDE)
async def extraer_factura(
    file: UploadFile = File(...),
    data: Optional[str] = Form(None, description='JSON: {"cliente": {...}, "ce": {...}, "Fsmstate": "...", "FsmPrevious": "..."}'),
):
    """
    Recibe una factura PDF y extrae los campos usando Claude API.
    El campo 'data' (JSON opcional) puede incluir cliente, ce, Fsmstate, etc.
    Si 'data' contiene cliente.correo, busca dealId y mpklogId en Zoho CRM.
    """
    # Parsear data opcional
    extra: dict = {}
    if data:
        try:
            extra = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Campo 'data' no es JSON válido.")

    correo = extra.get("cliente", {}).get("correo", "")
    print(f"\n  [/facturas/extraer] ficheiro: {file.filename}  |  correo: {correo or '(no proporcionado)'}")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()

    try:
        result = extract_with_claude(pdf_bytes)
    except anthropic.APIStatusError as e:
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  [ERROR]  APIStatusError {e.status_code}: {msg}")
        raise HTTPException(status_code=502, detail=f"Error de la API de Claude ({e.status_code}): {e}")
    except anthropic.APITimeoutError:
        print("  [ERROR]  APITimeoutError")
        raise HTTPException(status_code=504, detail="Timeout llamando a la API de Claude.")
    except Exception as e:
        import traceback
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  [ERROR]  Error inesperado: {msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {e}")

    # Buscar dealId y mpklogId en Zoho CRM si hay correo
    deal_id, mpklog_id = None, None
    if correo:
        deal_id, mpklog_id = await asyncio.gather(
            buscar_deal_por_email(correo),
            buscar_mpklog_por_email(correo),
        )
        if deal_id:
            print(f"  ✅  dealId: {deal_id}")
        if mpklog_id:
            print(f"  ✅  mpklogId: {mpklog_id}")

    # Inyectar dealId/mpklogId en cliente
    if "cliente" in extra:
        extra["cliente"]["dealId"]   = deal_id
        extra["cliente"]["mpklogId"] = mpklog_id

    # Construir payload completo para la sesión
    factura_payload = {
        k: v for k, v in result.model_dump().items()
        if k not in _EXCLUDE
    }
    session_payload = {
        **extra,                      # cliente, ce, Fsmstate, FsmPrevious, ...
        "factura":  factura_payload,  # datos extraídos por Claude
        "dealId":   deal_id,
        "mpklogId": mpklog_id,
    }

    result.session_id = crear_sesion(session_payload)
    print(f"  ✅  Sessão criada: {result.session_id}")

    # Guardar JSON
    cups   = result.cups or "sin_cups"
    inicio = (result.periodo_inicio or "").replace("/", "-")
    fin    = (result.periodo_fin    or "").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}.json"
    ruta   = os.path.join(RESULTADOS_DIR, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(session_payload, f, ensure_ascii=False, indent=2)

    return result
