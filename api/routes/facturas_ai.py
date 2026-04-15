# api/routes/facturas_ai.py
# Endpoint POST /facturas/extraer-ai
# Extrae datos de una factura eléctrica PDF usando la API de Claude,
# aplica reconciliación contable R13 y crea una sesión en /sesion.

import json
import os

import anthropic
from fastapi import APIRouter, File, HTTPException, UploadFile

from api.claude.extractor import extract_with_claude
from api.models import ExtractionResponseAI, ValidacionCuadre
from api.routes.sesion import crear_sesion

router = APIRouter(prefix="/facturas", tags=["facturas"])

RESULTADOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)

_TOLERANCE = 0.02  # €


def _calc_validacion_cuadre(result: ExtractionResponseAI) -> ValidacionCuadre:
    """Reconciliación contable R13: suma conceptos y compara con importe_factura."""
    importe = result.importe_factura
    if importe is None:
        return ValidacionCuadre(
            cuadra=False,
            error="importe_factura no disponible — no se puede validar el cuadre",
        )

    conceptos: list[float] = []

    for val in [
        result.imp_termino_energia_eur,
        result.imp_termino_potencia_eur,
        result.imp_impuesto_electrico_eur,
        result.imp_alquiler_eur,
        result.imp_iva_eur,
        result.bono_social,
    ]:
        if val is not None:
            conceptos.append(val)

    if result.descuentos:
        conceptos.extend(v for v in result.descuentos.values() if v is not None)

    if result.otros:
        conceptos.extend(v for v in result.otros.values() if v is not None)

    if not conceptos:
        return ValidacionCuadre(
            cuadra=False,
            importe_factura=importe,
            error="No hay conceptos desglosados para validar el cuadre",
        )

    suma = round(sum(conceptos), 2)
    diferencia = round(abs(importe - suma), 2)
    cuadra = diferencia <= _TOLERANCE

    return ValidacionCuadre(
        cuadra=cuadra,
        importe_factura=importe,
        suma_conceptos=suma,
        diferencia_eur=diferencia,
        error=None if cuadra else f"Diferencia de {diferencia:.2f} € entre suma de conceptos y importe facturado",
    )


@router.post("/extraer-ai", response_model=ExtractionResponseAI)
async def extraer_factura_ai(file: UploadFile = File(...)):
    """
    Extrae datos de una factura PDF usando Claude API (claude-sonnet-4-6).
    Aplica reconciliación contable R13 y crea una sesión temporal con los datos.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()

    try:
        result = extract_with_claude(pdf_bytes)
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de la API de Claude: {e.message}")
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="Timeout llamando a la API de Claude.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {e}")

    # Reconciliación contable R13
    result.validacion_cuadre = _calc_validacion_cuadre(result)

    # Crear sesión con el payload extraído
    result.session_id = crear_sesion(result.model_dump())

    # Guardar JSON con sufijo _ai para no colisionar con parsers regex
    cups   = result.cups or "sin_cups"
    inicio = (result.periodo_inicio or "").replace("/", "-")
    fin    = (result.periodo_fin    or "").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}_ai.json"
    ruta   = os.path.join(RESULTADOS_DIR, nombre)

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

    result.fichero_json = nombre
    return result
