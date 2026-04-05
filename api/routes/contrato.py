# api/routes/contrato.py
# Callback de contrato assinado (Zoho Sign → webhook → store em memória).
# POST /contrato/callback — guarda contractUrl indexada por dealId
# GET  /contrato/{dealId} — devolve e remove a contractUrl do store

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

contrato_store: dict[str, str] = {}  # { dealId: contractUrl }

router = APIRouter(prefix="/contrato", tags=["contrato"])


class ContratoCallback(BaseModel):
    dealId: str
    contractUrl: str

    model_config = {"coerce_numbers_to_str": True}


@router.post("/callback")
async def contrato_callback(body: ContratoCallback):
    if not body.dealId or not body.contractUrl:
        raise HTTPException(status_code=400, detail="Campos 'dealId' e 'contractUrl' são obrigatórios.")
    contrato_store[body.dealId] = body.contractUrl
    print(f"[/contrato/callback] dealId={body.dealId} guardado")
    return {"ok": True}


@router.get("/{dealId}")
async def get_contrato(dealId: str):
    url = contrato_store.get(dealId)
    if url is not None:
        del contrato_store[dealId]
        return {"found": True, "contractUrl": url}
    return {"found": False}
