# api/routes/cups.py
# Endpoint GET /cups/consultar
# Consulta el CUPS en la API Ingebau y devuelve datos del punto de suministro.

import os
import requests
from fastapi import APIRouter, Query, HTTPException
from dotenv import load_dotenv

from extractor.base import to_date, fmt_date

load_dotenv()
API_URL   = os.getenv("API_URL", "http://13.39.57.137:8004/Cups")
API_TOKEN = os.getenv("API_TOKEN")

router = APIRouter(prefix="/cups", tags=["cups"])


@router.get("/consultar")
def consultar_cups(cups: str = Query(..., description="Código CUPS a consultar")):
    """
    Consulta el CUPS en la API Ingebau y devuelve los datos del punto de
    suministro y el período de consumo más reciente.
    """
    if not cups:
        raise HTTPException(status_code=400, detail="CUPS requerido")

    try:
        resp = requests.get(
            API_URL,
            params={"cups": cups, "token": API_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Error de conexión con la API Ingebau")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout en la API Ingebau")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")

    if data.get("result") != "ok":
        raise HTTPException(
            status_code=400,
            detail=data.get("messages", "La API Ingebau no encontró el CUPS"),
        )

    ps_list       = data.get("data", {}).get("ps", [])
    consumos_list = data.get("data", {}).get("consumos", [])

    if not ps_list:
        raise HTTPException(status_code=404, detail="CUPS no encontrado en la API")

    ps = ps_list[0]
    resultado = {
        "tarifa_acceso": ps.get("TarifaATR") or "",
        "distribuidora": ps.get("NombreDistribuidora") or "",
        "pot_p1_kw":     str(ps.get("PotenciaContratadaP1kW") or ""),
        "pot_p2_kw":     str(ps.get("PotenciaContratadaP2kW") or ""),
        "pot_p3_kw":     str(ps.get("PotenciaContratadaP3kW") or "0"),
        "pot_p4_kw":     str(ps.get("PotenciaContratadaP4kW") or "0"),
        "pot_p5_kw":     str(ps.get("PotenciaContratadaP5kW") or "0"),
        "pot_p6_kw":     str(ps.get("PotenciaContratadaP6kW") or "0"),
    }

    if consumos_list:
        consumo = consumos_list[0]
        resultado["consumo_p1_kwh"] = str(consumo.get("EnergiaActivaP1(kWh)", 0))
        resultado["consumo_p2_kwh"] = str(consumo.get("EnergiaActivaP2(kWh)", 0))
        resultado["consumo_p3_kwh"] = str(consumo.get("EnergiaActivaP3(kWh)", 0))
        resultado["consumo_p4_kwh"] = str(consumo.get("EnergiaActivaP4(kWh)", 0))
        resultado["consumo_p5_kwh"] = str(consumo.get("EnergiaActivaP5(kWh)", 0))
        resultado["consumo_p6_kwh"] = str(consumo.get("EnergiaActivaP6(kWh)", 0))

        dt_desde = to_date(consumo.get("LecturaDesde", ""))
        dt_hasta = to_date(consumo.get("LecturaHasta", ""))
        if dt_desde and dt_hasta:
            resultado["dias_facturados"] = str((dt_hasta - dt_desde).days)
            resultado["periodo_inicio"]  = fmt_date(dt_desde)
            resultado["periodo_fin"]     = fmt_date(dt_hasta)

    return resultado
