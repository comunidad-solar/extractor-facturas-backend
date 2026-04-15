# api/routes/facturas.py
# Endpoint POST /facturas/extraer
# Usa Claude API como caminho de extracção principal.
# Ingebau desactivado temporalmente.
#
# Modificado: 2026-04-15 | Rodrigo Costa
#   - Redirigido a extract_with_claude() en lugar de extract_from_pdf() (regex)
#   - Ingebau desactivado temporalmente (TODO: reactivar cuando se retome)

import json
import os

import anthropic
from fastapi import APIRouter, UploadFile, File, HTTPException
from api.models import ExtractionResponseAI
from api.claude.extractor import extract_with_claude
from api.routes.sesion import crear_sesion

router = APIRouter(prefix="/facturas", tags=["facturas"])

RESULTADOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)


@router.post("/extraer", response_model=ExtractionResponseAI)
async def extraer_factura(file: UploadFile = File(...)):
    """
    Recibe una factura PDF y extrae los campos usando Claude API.
    Ingebau desactivado temporalmente — solo Claude.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()

    try:
        result = extract_with_claude(pdf_bytes)
    except anthropic.APIStatusError as e:
        print(f"  ❌  APIStatusError {e.status_code}: {e}")
        raise HTTPException(status_code=502, detail=f"Error de la API de Claude ({e.status_code}): {e}")
    except anthropic.APITimeoutError:
        print("  ❌  APITimeoutError")
        raise HTTPException(status_code=504, detail="Timeout llamando a la API de Claude.")
    except Exception as e:
        import traceback
        print(f"  ❌  Error inesperado: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {e}")

    # Crear sesión con el payload extraído
    result.session_id = crear_sesion(result.model_dump())

    # Guardar JSON
    cups   = result.cups or "sin_cups"
    inicio = (result.periodo_inicio or "").replace("/", "-")
    fin    = (result.periodo_fin    or "").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}.json"
    ruta   = os.path.join(RESULTADOS_DIR, nombre)

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

    result.fichero_json = nombre
    return result
