# api/routes/deals.py
# POST /deals/lead-source
# Actualiza Lead_Source no Deal com a URL do plan screen.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routes.sesion import leer_sesion
from api.zoho_crm import actualizar_campo_deal

router = APIRouter(prefix="/deals", tags=["deals"])


class LeadSourcePayload(BaseModel):
    session_id: str
    plan_url: str


@router.post("/lead-source")
async def guardar_lead_source(payload: LeadSourcePayload):
    session = leer_sesion(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    deal_id = session.get("dealId") or session.get("cliente", {}).get("dealId")
    if not deal_id:
        raise HTTPException(status_code=404, detail="dealId ainda não disponível na sessão.")

    ok = await actualizar_campo_deal(deal_id, "Lead_Source", payload.plan_url)
    if not ok:
        raise HTTPException(status_code=502, detail="Erro ao actualizar Lead_Source no Zoho CRM.")

    print(f"[deals/lead-source] dealId={deal_id} Lead_Source actualizado: {payload.plan_url[:80]}")
    return {"ok": True, "dealId": deal_id}
