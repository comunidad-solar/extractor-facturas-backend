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


def _build_factura_payload(result: ExtractionResponseAI) -> dict:
    """Convierte el resultado plano de Claude al formato anidado usado por /enviar."""
    descuentos = dict(result.descuentos or {})
    if result.bono_social:
        descuentos["bono_social"] = result.bono_social

    otros_extra = dict(result.otros or {})

    return {
        "cups":             result.cups,
        "comercializadora": result.comercializadora,
        "distribuidora":    result.distribuidora,
        "tarifa_acceso":    result.tarifa_acceso,
        "periodo_inicio":   result.periodo_inicio,
        "periodo_fin":      result.periodo_fin,
        "dias_facturados":  result.dias_facturados,
        "importe_factura":  result.importe_factura,
        "potencias_kw": {
            "p1": result.pot_p1_kw, "p2": result.pot_p2_kw,
            "p3": result.pot_p3_kw, "p4": result.pot_p4_kw,
            "p5": result.pot_p5_kw, "p6": result.pot_p6_kw,
        },
        "consumos_kwh": {
            "p1": result.consumo_p1_kwh, "p2": result.consumo_p2_kwh,
            "p3": result.consumo_p3_kwh, "p4": result.consumo_p4_kwh,
            "p5": result.consumo_p5_kwh, "p6": result.consumo_p6_kwh,
        },
        "precios_potencia": {
            "p1": result.pp_p1, "p2": result.pp_p2, "p3": result.pp_p3,
            "p4": result.pp_p4, "p5": result.pp_p5, "p6": result.pp_p6,
        },
        "precios_energia": {
            "pe_p1": result.pe_p1, "pe_p2": result.pe_p2, "pe_p3": result.pe_p3,
            "pe_p4": result.pe_p4, "pe_p5": result.pe_p5, "pe_p6": result.pe_p6,
        },
        "impuestos": {
            "imp_ele":         result.imp_ele,
            "imp_ele_eur_kwh": result.imp_ele_eur_kwh,
            "iva":             result.iva,
        },
        "otros": {
            "alq_eq_dia":      result.alq_eq_dia,
            "cuotaAlquilerMes": None,
            "descuentos":      descuentos,
            **otros_extra,
        },
        "archivo": {},
    }


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
    session_payload = {
        **extra,                             # cliente, ce, Fsmstate, FsmPrevious, ...
        "factura":  _build_factura_payload(result),
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
