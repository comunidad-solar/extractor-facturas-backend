# extractor/api.py
# Responsable de la llamada a la API Ingebau y la selección del período
# de consumo que corresponde a la factura procesada.
#
# Modificado: 2026-02-26 | Rodrigo Costa

import os
import requests
from datetime import timedelta
from typing import Optional

from dotenv import load_dotenv
from .base import to_date, fmt_date, log

load_dotenv()
API_URL   = os.getenv("API_URL")
API_TOKEN = os.getenv("API_TOKEN")


def llamar_api(cups: str, fields: dict, raw: dict,
               periodo_inicio: str, periodo_fin: str) -> tuple[bool, str]:
    """
    Llama a la API Ingebau con el CUPS dado y rellena los campos del punto
    de suministro y consumos en los diccionarios fields y raw.

    Retorna (api_ok: bool, api_error: str).
    """
    def save(key, value, match=""):
        fields[key] = value
        raw[key]    = match

    print(f"\n  [2/6] LLAMADA API INGEBAU — CUPS: {cups}")
    print("  " + "-"*50)

    if not cups:
        msg = "CUPS no encontrado — llamada a la API no realizada"
        print(f"  ❌  {msg}")
        return False, msg

    try:
        resp = requests.get(
            API_URL,
            params={"cups": cups, "token": API_TOKEN},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "ok":
            msg = f"API devolvió: {data.get('messages', 'error desconocido')}"
            print(f"  ❌  {msg}")
            return False, msg

        ps_list       = data.get("data", {}).get("ps", [])
        consumos_list = data.get("data", {}).get("consumos", [])

        if not ps_list:
            msg = "La API no devolvió datos de PS"
            print(f"  ❌  {msg}")
            return False, msg

        ps = ps_list[0]

        # Campos del punto de suministro
        save("tarifa_acceso", ps.get("TarifaATR"),                  "API")
        save("distribuidora", ps.get("NombreDistribuidora"),         "API")
        save("pot_p1_kw",     ps.get("PotenciaContratadaP1kW"),      "API")
        save("pot_p2_kw",     ps.get("PotenciaContratadaP2kW"),      "API")
        save("pot_p3_kw",     ps.get("PotenciaContratadaP3kW", "0"), "API")
        save("pot_p4_kw",     ps.get("PotenciaContratadaP4kW", "0"), "API")
        save("pot_p5_kw",     ps.get("PotenciaContratadaP5kW", "0"), "API")
        save("pot_p6_kw",     ps.get("PotenciaContratadaP6kW", "0"), "API")

        log("tarifa_acceso", fields["tarifa_acceso"], "API")
        log("distribuidora", fields["distribuidora"], "API")
        log("pot_p1_kw",     fields["pot_p1_kw"],     "API")
        log("pot_p2_kw",     fields["pot_p2_kw"],     "API")
        log("pot_p3_kw",     fields["pot_p3_kw"],     "API")
        log("pot_p4_kw",     fields["pot_p4_kw"],     "API")
        log("pot_p5_kw",     fields["pot_p5_kw"],     "API")
        log("pot_p6_kw",     fields["pot_p6_kw"],     "API")

        # Seleccionar el período de consumo que corresponde a la factura
        consumo = seleccionar_consumo(consumos_list, periodo_inicio, periodo_fin)

        if consumo:
            save("consumo_p1_kwh", str(consumo.get("EnergiaActivaP1(kWh)", 0)), "API")
            save("consumo_p2_kwh", str(consumo.get("EnergiaActivaP2(kWh)", 0)), "API")
            save("consumo_p3_kwh", str(consumo.get("EnergiaActivaP3(kWh)", 0)), "API")
            save("consumo_p4_kwh", str(consumo.get("EnergiaActivaP4(kWh)", 0)), "API")
            save("consumo_p5_kwh", str(consumo.get("EnergiaActivaP5(kWh)", 0)), "API")
            save("consumo_p6_kwh", str(consumo.get("EnergiaActivaP6(kWh)", 0)), "API")

            log("consumo_p1_kwh", fields["consumo_p1_kwh"], "API")
            log("consumo_p2_kwh", fields["consumo_p2_kwh"], "API")
            log("consumo_p3_kwh", fields["consumo_p3_kwh"], "API")
            log("consumo_p4_kwh", fields["consumo_p4_kwh"], "API")
            log("consumo_p5_kwh", fields["consumo_p5_kwh"], "API")
            log("consumo_p6_kwh", fields["consumo_p6_kwh"], "API")

            # Recalcular días del período real de la API
            dt_desde = to_date(consumo.get("LecturaDesde", ""))
            dt_hasta = to_date(consumo.get("LecturaHasta", ""))
            if dt_desde and dt_hasta:
                dias_api = (dt_hasta - dt_desde).days
                save("dias_facturados", str(dias_api), "API")
                log("dias_facturados", str(dias_api), "API")
                # Rellenar período si no se extrajo del PDF
                if not fields.get("periodo_inicio"):
                    save("periodo_inicio", fmt_date(dt_desde), "API")
                    log("periodo_inicio", fmt_date(dt_desde), "API (fallback)")
                if not fields.get("periodo_fin"):
                    save("periodo_fin", fmt_date(dt_hasta), "API")
                    log("periodo_fin", fmt_date(dt_hasta), "API (fallback)")

            print(f"\n  ✅  API Ingebau OK — {len(consumos_list)} períodos de consumo disponibles")
            print(f"       Período seleccionado: {consumo.get('LecturaDesde')} → {consumo.get('LecturaHasta')}")
        else:
            msg = "Ningún período de consumo correspondiente encontrado en la API"
            print(f"  ⚠️   {msg}")
            return True, msg

        return True, ""

    except requests.exceptions.ConnectionError:
        msg = "Error de conexión con la API Ingebau"
        print(f"  ❌  {msg}")
        return False, msg
    except requests.exceptions.Timeout:
        msg = "Timeout en la llamada a la API Ingebau"
        print(f"  ❌  {msg}")
        return False, msg
    except Exception as e:
        msg = f"Error inesperado en la API: {str(e)}"
        print(f"  ❌  {msg}")
        return False, msg


def seleccionar_consumo(consumos: list, periodo_inicio: str,
                        periodo_fin: str) -> Optional[dict]:
    """
    Selecciona el registro de consumo que mejor corresponde al período de la factura.
    Normaliza todas las fechas antes de comparar.
    Si la diferencia supera 15 días, devuelve el más reciente (primero de la lista).
    """
    if not consumos:
        return None

    dt_ini = to_date(periodo_inicio) if periodo_inicio else None
    dt_fin = to_date(periodo_fin)    if periodo_fin    else None

    mejor       = None
    mejor_delta = timedelta(days=9999)

    for consumo in consumos:
        dt_desde = to_date(consumo.get("LecturaDesde", ""))
        dt_hasta = to_date(consumo.get("LecturaHasta", ""))

        if not dt_desde or not dt_hasta:
            continue

        if dt_ini and dt_fin:
            # Correspondencia exacta
            if dt_desde == dt_ini and dt_hasta == dt_fin:
                return consumo

            # Aproximada — diferencia total de días
            delta = abs(dt_desde - dt_ini) + abs(dt_hasta - dt_fin)
            if delta < mejor_delta:
                mejor_delta = delta
                mejor       = consumo
        else:
            # Sin período en la factura — usar el más reciente
            if mejor is None:
                mejor = consumo

    # Si la mejor coincidencia está demasiado lejos, usar el más reciente
    if mejor_delta > timedelta(days=15):
        return consumos[0]

    return mejor
