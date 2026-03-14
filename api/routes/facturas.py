# api/routes/facturas.py
# Endpoint POST /facturas/extraer
# Recibe un PDF, extrae los 24 campos y guarda el resultado en resultados/.
#
# Modificado: 2026-02-27 | Rodrigo Costa

import os
import json
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from api.models import ExtractionResponse
from extractor import extract_from_pdf

router = APIRouter(prefix="/facturas", tags=["facturas"])

# Carpeta donde se guardan los JSONs
RESULTADOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)


@router.post("/extraer", response_model=ExtractionResponse)
async def extraer_factura(file: UploadFile = File(...)):
    """
    Recibe una factura PDF, extrae los 24 campos y guarda el resultado en JSON.
    """
    # Validar que sea PDF
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    # Guardar PDF temporalmente para que extract_from_pdf() pueda leerlo
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = extract_from_pdf(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {e}")
    finally:
        os.unlink(tmp_path)  # eliminar PDF temporal siempre

    fields = result.fields

    # Construir nombre del fichero JSON
    cups    = fields.get("cups") or "sin_cups"
    inicio  = (fields.get("periodo_inicio") or "").replace("/", "-")
    fin     = (fields.get("periodo_fin")    or "").replace("/", "-")
    nombre  = f"{cups}_{inicio}_{fin}.json"
    ruta    = os.path.join(RESULTADOS_DIR, nombre)

    # Guardar JSON
    payload = {**fields, "api_ok": result.api_ok, "api_error": result.api_error}
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return ExtractionResponse(
        **fields,
        api_ok       = result.api_ok,
        api_error    = result.api_error,
        fichero_json = nombre,
    )