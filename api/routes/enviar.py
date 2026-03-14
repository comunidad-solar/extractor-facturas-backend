# api/routes/enviar.py
# Proxy para el webhook de Zoho Flow.
# POST /enviar — reenvía {cliente, factura} al webhook externo.

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

ZOHO_WEBHOOK = (
    "https://flow.zoho.eu/20067915739/flow/webhook/incoming"
    "?zapikey=1001.333e94b169d89fa9db9d59ecf859b773.0377ab428b917dde7096df8db25b29eb"
    "&isdebug=false"
)

router = APIRouter(prefix="/enviar", tags=["enviar"])


class CeInfo(BaseModel):
    nombre: Optional[str] = ""
    direccion: Optional[str] = ""
    status: Optional[str] = ""
    etiqueta: Optional[str] = ""


class EnvioPayload(BaseModel):
    cliente: Dict[str, Any]
    factura: Optional[Dict[str, Any]] = None
    Fsmstate: Optional[str] = None
    FsmPrevious: Optional[str] = None
    ce: Optional[CeInfo] = None


@router.post("")
def enviar_datos(payload: EnvioPayload):
    """
    Reenvía los datos del cliente y factura al webhook de Zoho Flow.
    """
    try:
        resp = requests.post(ZOHO_WEBHOOK, json=payload.dict(), timeout=15)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Error de conexión con Zoho Flow")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout en Zoho Flow")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Error de Zoho Flow: {e.response.status_code}")

    return {"ok": True}
