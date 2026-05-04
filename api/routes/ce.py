# api/routes/ce.py
# GET /ce/foto?name={nombre_ce}
# Busca Comunidad Energética por Name en Zoho CRM y devuelve Image_URL.

from fastapi import APIRouter, HTTPException, Query
from api.zoho_crm import buscar_foto_ce

router = APIRouter(prefix="/ce", tags=["ce"])


@router.get("/foto")
async def get_foto_ce(name: str = Query(..., description="Nombre exacto de la CE")):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Parámetro 'name' vacío.")

    foto_url = await buscar_foto_ce(name)

    if foto_url is None:
        raise HTTPException(status_code=404, detail={"foto_url": None})

    return {"foto_url": foto_url}
