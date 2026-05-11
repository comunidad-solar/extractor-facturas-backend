# api/claude/pipeline.py
# 2-stage extraction pipeline:
#   Stage 1 — opus reads ALL raw data from PDF (no interpretation)
#   Stage 2 — 4 haiku mappers run in PARALLEL, each applying focused rules
#   Stage 3 — Python assembles results into ExtractionResponseAI

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.claude.client import get_client
from api.claude.raw_prompt import RAW_SYSTEM_PROMPT, RAW_USER_TEXT
from api.claude.mappers.potencia import map_potencia
from api.claude.mappers.energia import map_energia
from api.claude.mappers.cargas import map_cargas
from api.claude.mappers.costes import map_costes
from api.models import ExtractionResponseAI, IVABlock

RAW_MODEL = "claude-opus-4-7"
RAW_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# Stage 1: PDF → RawInvoiceData
# ---------------------------------------------------------------------------

def _extract_raw(pdf_bytes: bytes) -> dict:
    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    response = client.messages.create(
        model=RAW_MODEL,
        max_tokens=RAW_MAX_TOKENS,
        system=[{
            "type": "text",
            "text": RAW_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                },
                {"type": "text", "text": RAW_USER_TEXT},
            ],
        }],
    )
    text = response.content[0].text if response.content else ""
    usage = response.usage
    print(f"  [Stage 1] stop={response.stop_reason} | "
          f"in={usage.input_tokens:,} out={usage.output_tokens:,} "
          f"cache_read={getattr(usage,'cache_read_input_tokens',0):,}")
    return _parse_raw_json(text)


def _parse_raw_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)
        return json.loads(raw)


# ---------------------------------------------------------------------------
# Stage 2: RawInvoiceData → field dicts (parallel haiku calls)
# ---------------------------------------------------------------------------

def _run_mappers(raw: dict) -> dict:
    tasks = {
        "potencia": map_potencia,
        "energia": map_energia,
        "cargas": map_cargas,
        "costes": map_costes,
    }
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn, raw): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
            print(f"  [Stage 2] mapper '{name}' done")
    return results


# ---------------------------------------------------------------------------
# Stage 3: Assemble ExtractionResponseAI (pure Python, no LLM)
# ---------------------------------------------------------------------------

def _assemble(raw: dict, mapped: dict) -> ExtractionResponseAI:
    meta = raw.get("meta", {})
    pot = mapped["potencia"]
    eng = mapped["energia"]
    cargas = mapped["cargas"]
    costes = mapped["costes"]

    # Identity fields
    cups = meta.get("cups")
    comercializadora = meta.get("comercializadora")
    distribuidora = meta.get("distribuidora")
    tarifa_acceso = meta.get("tarifa_acceso")
    periodo_inicio = meta.get("periodo_inicio")
    periodo_fin = meta.get("periodo_fin")
    dias_facturados = str(meta.get("dias_facturados", "")) or None
    nombre_cliente = meta.get("nombre_cliente")
    direccion_suministro = meta.get("direccion_suministro")
    importe_factura = meta.get("importe_factura")

    # Potencias contratadas
    pc = {p["periodo"]: p["kw"] for p in raw.get("potencias_contratadas", [])}

    # Impuestos
    imp = raw.get("impuestos", {})
    iee = imp.get("iee") or {}
    imp_ele = iee.get("porcentaje")
    iva_lines = imp.get("iva") or []
    iva_pct = iva_lines[0].get("porcentaje") if iva_lines else None

    # IVA block
    iva_block = None
    if iva_lines:
        l1 = iva_lines[0]
        l2 = iva_lines[1] if len(iva_lines) > 1 else {}
        iva_block = IVABlock(
            IVA_PERCENT_1=l1.get("porcentaje"),
            IVA_PERCENT_2=l2.get("porcentaje"),
            IVA_BASE_IMPONIBLE_1=l1.get("base"),
            IVA_BASE_IMPONIBLE_2=l2.get("base"),
            IVA_SUBTOTAL_EUROS_1=l1.get("importe"),
            IVA_SUBTOTAL_EUROS_2=l2.get("importe"),
            IVA_TOTAL_EUROS=sum(l.get("importe", 0) for l in iva_lines),
        )
    iva_total_euros = iva_block.IVA_TOTAL_EUROS if iva_block else None

    # Alquiler
    alquiler_data = raw.get("alquiler", {})
    imp_alquiler_eur = alquiler_data.get("total")
    alq_lines = alquiler_data.get("lineas", [])
    alq_eq_dia = alq_lines[0].get("precio_dia") if alq_lines else None
    if alq_eq_dia is None and imp_alquiler_eur and dias_facturados:
        try:
            alq_eq_dia = round(imp_alquiler_eur / int(dias_facturados), 6)
        except (ValueError, ZeroDivisionError):
            pass

    # Cargas (exceso + reactiva)
    exceso_importe = cargas.get("exceso_potencia_importe")
    reactiva_importe = cargas.get("coste_energia_reactiva")
    reactiva_inside = cargas.get("reactiva_inside_energia", False)

    # Costes/Creditos dict
    bono_importe = costes.get("bono_social_importe")
    bono_dia = costes.get("bono_social_precio_dia")
    costes_adicionales = costes.get("costes_adicionales", {})
    creditos_dict = costes.get("creditos", {})
    precio_final_energia = costes.get("precio_final_energia_activa")

    # imp_termino_energia_eur: always gross (from energia mapper)
    imp_termino_energia = eng.get("imp_termino_energia_eur")

    # Build otros
    importes_totalizados = {
        "precio_final_energia_activa": precio_final_energia,
        "coste_energia_reactiva": reactiva_importe,
        "precio_final_potencia": pot.get("imp_termino_potencia_eur"),
        "total_impuestos_electrico": iee.get("importe"),
        "alquiler_equipos_medida_importe": imp_alquiler_eur,
        "subtotal_sin_impuestos": _get_subtotal(raw),
        "iva_total": iva_total_euros,
        "total_factura": importe_factura,
    }

    costes_block = {
        "bono_social_importe": bono_importe,
        "exceso_potencia_importe": exceso_importe,
        "coste_energia_reactiva": reactiva_importe,
        **costes_adicionales,
    }

    creditos_block = {
        "compensacion_excedentes_importe": None,
        **creditos_dict,
    }

    observacion = (
        pot.get("observacion", [])
        + eng.get("observacion", [])
        + cargas.get("observacion", [])
        + costes.get("observacion", [])
    )

    otros = {
        "importes_totalizados": importes_totalizados,
        "alq_eq_dia": alq_eq_dia,
        "cuotaAlquilerMes": None,
        "costes": costes_block,
        "creditos": creditos_block,
        "compensacion_excedentes_kwh": None,
        "observacion": observacion,
    }

    # margen_de_error (Python, no LLM)
    margen = _calc_margen(
        imp_termino_potencia=pot.get("imp_termino_potencia_eur"),
        imp_termino_energia=imp_termino_energia,
        imp_impuesto_electrico=iee.get("importe"),
        imp_alquiler=imp_alquiler_eur,
        imp_iva=iva_total_euros,
        costes_block=costes_block,
        creditos_block=creditos_block,
        reactiva_inside=reactiva_inside,
        importe_factura=importe_factura,
    )

    return ExtractionResponseAI(
        cups=cups,
        comercializadora=comercializadora,
        distribuidora=distribuidora,
        tarifa_acceso=tarifa_acceso,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        dias_facturados=dias_facturados,
        nombre_cliente=nombre_cliente,
        direccion_suministro=direccion_suministro,
        importe_factura=importe_factura,
        # Potencias contratadas
        pot_p1_kw=pc.get("P1"), pot_p2_kw=pc.get("P2"), pot_p3_kw=pc.get("P3"),
        pot_p4_kw=pc.get("P4"), pot_p5_kw=pc.get("P5"), pot_p6_kw=pc.get("P6"),
        # Precios potencia
        pp_p1=pot.get("pp_p1"), pp_p2=pot.get("pp_p2"), pp_p3=pot.get("pp_p3"),
        pp_p4=pot.get("pp_p4"), pp_p5=pot.get("pp_p5"), pp_p6=pot.get("pp_p6"),
        pp_unidad=pot.get("pp_unidad", "dia"),
        # Precios energía
        pe_p1=eng.get("pe_p1"), pe_p2=eng.get("pe_p2"), pe_p3=eng.get("pe_p3"),
        pe_p4=eng.get("pe_p4"), pe_p5=eng.get("pe_p5"), pe_p6=eng.get("pe_p6"),
        # Consumos
        consumo_p1_kwh=eng.get("consumo_p1_kwh"), consumo_p2_kwh=eng.get("consumo_p2_kwh"),
        consumo_p3_kwh=eng.get("consumo_p3_kwh"), consumo_p4_kwh=eng.get("consumo_p4_kwh"),
        consumo_p5_kwh=eng.get("consumo_p5_kwh"), consumo_p6_kwh=eng.get("consumo_p6_kwh"),
        # Impuestos
        imp_ele=imp_ele,
        iva=iva_pct,
        IVA=iva_block,
        IVA_TOTAL_EUROS=iva_total_euros,
        alq_eq_dia=alq_eq_dia,
        bono_social=bono_dia,
        # Importes
        imp_termino_energia_eur=imp_termino_energia,
        imp_termino_potencia_eur=pot.get("imp_termino_potencia_eur"),
        imp_impuesto_electrico_eur=iee.get("importe"),
        imp_alquiler_eur=imp_alquiler_eur,
        imp_iva_eur=iva_total_euros,
        impuesto_electricidad_importe=iee.get("importe"),
        alquiler_equipos_medida_importe=imp_alquiler_eur,
        # Otros
        otros=otros,
        margen_de_error=margen,
    )


def _get_subtotal(raw: dict) -> float | None:
    """Extract base imponible from IVA line (X% s/ Y → Y)."""
    iva_lines = raw.get("impuestos", {}).get("iva", [])
    if iva_lines:
        return iva_lines[0].get("base")
    return None


def _calc_margen(
    imp_termino_potencia, imp_termino_energia, imp_impuesto_electrico,
    imp_alquiler, imp_iva, costes_block, creditos_block,
    reactiva_inside, importe_factura,
) -> float | None:
    if importe_factura is None:
        return None
    try:
        suma = sum(v for v in [
            imp_termino_potencia, imp_termino_energia,
            imp_impuesto_electrico, imp_alquiler, imp_iva,
        ] if v is not None)

        # Add costes that are NOT already inside imp_termino_*
        for key, val in (costes_block or {}).items():
            if val is None:
                continue
            if key == "alquiler_equipos_medida_importe":
                continue  # already in imp_alquiler_eur
            if key == "coste_energia_reactiva":
                if reactiva_inside:
                    continue  # already inside imp_termino_energia_eur
            if key == "bono_social_importe":
                continue  # not a separate invoice line, it's informational
            if isinstance(val, (int, float)) and val > 0:
                suma += val

        # Add creditos (negative values)
        for key, val in (creditos_block or {}).items():
            if isinstance(val, (int, float)) and val < 0:
                suma += val

        return round(abs(suma - importe_factura) / importe_factura * 100, 4)
    except (TypeError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(pdf_bytes: bytes) -> ExtractionResponseAI:
    print(f"\n{'='*70}")
    print("  *** PIPELINE MULTI-AGENTE ***")
    print(f"{'='*70}")

    print("  [Stage 1] Extrayendo datos crudos (opus)...")
    raw = _extract_raw(pdf_bytes)
    print(f"  [Stage 1] Raw extraído: {raw.get('meta', {}).get('cups', '?')}")

    print("  [Stage 2] Ejecutando mappers en paralelo (Sonnet × 4)...")
    mapped = _run_mappers(raw)

    print("  [Stage 3] Ensamblando ExtractionResponseAI...")
    try:
        result = _assemble(raw, mapped)
    except Exception as exc:
        exc.raw_data    = raw
        exc.mapped_data = mapped
        raise

    ok = result.margen_de_error is not None and result.margen_de_error <= 5.0
    icon = "✅" if ok else "⚠️ "
    print(f"  {icon} Margen de error: {result.margen_de_error}%")
    print(f"  CUPS: {result.cups}")
    print(f"{'='*70}\n")
    return result
