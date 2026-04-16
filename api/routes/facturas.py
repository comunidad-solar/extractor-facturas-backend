# api/routes/facturas.py
# Endpoint POST /facturas/extraer
# Usa Claude API como caminho de extracção principal.
# Ingebau desactivado temporalmente.

import asyncio
import json
import os
from typing import Optional

import anthropic
from fastapi import APIRouter, Form, UploadFile, File, HTTPException

from api.claude.extractor import extract_with_claude
from api.models import ExtractionResponseAI
from api.routes.sesion import crear_sesion
from api.zoho_crm import buscar_deal_por_email, buscar_mpklog_por_email
from api.zoho_workdrive import upload_factura_files

router = APIRouter(prefix="/facturas", tags=["facturas"])

RESULTADOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)

_EXCLUDE = {"api_ok", "api_error", "fichero_json", "descuentos"}


def _build_factura_payload(result: ExtractionResponseAI) -> dict:
    """
    Constrói o payload de factura com campos planos (retrocompatibilidade com o
    cotizador) e grupos aninhados (novos consumidores). Ambos coexistem no mesmo dict.

    Mudanças v2:
    - 'descuentos' removido do nível raiz e do grupo 'otros'
    - 'otros' reestruturado com costes/creditos/observacion
    - Novos campos raíz: impuesto_electricidad_importe, alquiler_equipos_medida_importe,
      IVA_TOTAL_EUROS, IVA (bloco estruturado)
    - Migração backward-compat: se otros.creditos vazio, lê de result.descuentos
    """
    # ── Ler estructura nueva de otros ────────────────────────────────────────
    otros_raw   = result.otros or {}
    costes      = dict(otros_raw.get("costes") or {})
    creditos    = dict(otros_raw.get("creditos") or {})
    observacion = list(otros_raw.get("observacion") or [])

    # Migración backward-compat: si Claude aún llena 'descuentos' en lugar de
    # 'otros.creditos', migrar los valores
    if not creditos and result.descuentos:
        creditos = {k: v for k, v in result.descuentos.items()}

    # IVA bloque
    iva_block = result.IVA.model_dump() if result.IVA else None

    return {
        # ── Campos de identificação ───────────────────────────────────────────
        "cups":             result.cups,
        "comercializadora": result.comercializadora,
        "distribuidora":    result.distribuidora,
        "tarifa_acceso":    result.tarifa_acceso,
        "periodo_inicio":   result.periodo_inicio,
        "periodo_fin":      result.periodo_fin,
        "dias_facturados":  result.dias_facturados,
        "importe_factura":  result.importe_factura,

        # ── Campos planos (retrocompatibilidade com cotizador) ────────────────
        # NOTA: 'descuentos' removido — migrado para otros.creditos
        "pp_p1": result.pp_p1, "pp_p2": result.pp_p2, "pp_p3": result.pp_p3,
        "pp_p4": result.pp_p4, "pp_p5": result.pp_p5, "pp_p6": result.pp_p6,
        "pe_p1": result.pe_p1, "pe_p2": result.pe_p2, "pe_p3": result.pe_p3,
        "pe_p4": result.pe_p4, "pe_p5": result.pe_p5, "pe_p6": result.pe_p6,
        "pot_p1_kw": result.pot_p1_kw, "pot_p2_kw": result.pot_p2_kw,
        "pot_p3_kw": result.pot_p3_kw, "pot_p4_kw": result.pot_p4_kw,
        "pot_p5_kw": result.pot_p5_kw, "pot_p6_kw": result.pot_p6_kw,
        "consumo_p1_kwh": result.consumo_p1_kwh, "consumo_p2_kwh": result.consumo_p2_kwh,
        "consumo_p3_kwh": result.consumo_p3_kwh, "consumo_p4_kwh": result.consumo_p4_kwh,
        "consumo_p5_kwh": result.consumo_p5_kwh, "consumo_p6_kwh": result.consumo_p6_kwh,
        "imp_ele":         result.imp_ele,
        "imp_ele_eur_kwh": result.imp_ele_eur_kwh,
        "iva":             result.iva,
        "alq_eq_dia":      result.alq_eq_dia,
        "bono_social":     result.bono_social,

        # ── Novos campos raíz de importes totais ──────────────────────────────
        "impuesto_electricidad_importe":  result.impuesto_electricidad_importe,
        "alquiler_equipos_medida_importe": result.alquiler_equipos_medida_importe,
        "IVA_TOTAL_EUROS":                result.IVA_TOTAL_EUROS,
        "IVA":                            iva_block,

        # ── Grupos aninhados (novos consumidores) ─────────────────────────────
        "potencias_kw": {
            "p1": result.pot_p1_kw, "p2": result.pot_p2_kw,
            "p3": result.pot_p3_kw, "p4": result.pot_p4_kw,
            "p5": result.pot_p5_kw, "p6": result.pot_p6_kw,
        },
        "consumos_kwh": {
            "p1": result.consumo_p1_kwh, "p2": result.consumo_p2_kwh,
            "p3": result.consumo_p3_kwh, "p4": result.consumo_p4_kwh,
            "p5": result.consumo_p5_kwh, "p6": result.consumo_p6_kwh,
        },
        "precios_potencia": {
            "p1": result.pp_p1, "p2": result.pp_p2, "p3": result.pp_p3,
            "p4": result.pp_p4, "p5": result.pp_p5, "p6": result.pp_p6,
        },
        "precios_energia": {
            "pe_p1": result.pe_p1, "pe_p2": result.pe_p2, "pe_p3": result.pe_p3,
            "pe_p4": result.pe_p4, "pe_p5": result.pe_p5, "pe_p6": result.pe_p6,
        },
        "impuestos": {
            "imp_ele":         result.imp_ele,
            "imp_ele_eur_kwh": result.imp_ele_eur_kwh,
            "iva":             result.iva,
            "IVA":             iva_block,
        },
        "otros": {
            "alq_eq_dia":       result.alq_eq_dia,   # mantido para retrocompat
            "cuotaAlquilerMes": None,
            "costes":           costes,
            "creditos":         creditos,
            "observacion":      observacion,
        },

        # ── Validação de cuadre ───────────────────────────────────────────────
        "margen_de_error": result.margen_de_error,
    }


def _log_cuadre(result: ExtractionResponseAI) -> None:
    """Imprime en terminal el desglose completo del cuadre contable línea a línea."""
    W       = 68
    importe = result.importe_factura or 0.0
    dias    = int(result.dias_facturados or 0)

    def row(label: str, formula: str, valor: float, estimado: bool = False) -> None:
        flag = " (*)" if estimado else "    "
        print(f"  │{flag} {label:<28} {formula:<24} {valor:>+10.2f} €  │")

    def sep(char: str = "─") -> None:
        print(f"  ├{'─' if char == '─' else char*1}{'─'*(W-2)}┤")

    print(f"\n  ┌{'─'*W}┐")
    print(f"  │{'  CUADRE CONTABLE — DESGLOSE COMPLETO':^{W}}│")

    # ════════════════════════════════════════════════════════
    # BLOQUE POTENCIA
    # ════════════════════════════════════════════════════════
    sep()
    print(f"  │  {'POTENCIA':<{W-4}}│")
    sep()
    pot_total   = 0.0
    pot_claude  = result.imp_termino_potencia_eur or 0.0
    periodos_pp = [
        ("P1", result.pp_p1, result.pot_p1_kw),
        ("P2", result.pp_p2, result.pot_p2_kw),
        ("P3", result.pp_p3, result.pot_p3_kw),
        ("P4", result.pp_p4, result.pot_p4_kw),
        ("P5", result.pp_p5, result.pot_p5_kw),
        ("P6", result.pp_p6, result.pot_p6_kw),
    ]
    for pn, pp, kw in periodos_pp:
        if pp and kw and dias:
            val  = pp * kw * dias
            pot_total += val
            fml  = f"{kw} kW × {dias}d × {pp:.6f}"
            row(f"  Potencia {pn}", fml, val)
    if pot_claude:
        diff_pot = pot_claude - pot_total
        row("  SUBTOTAL potencia (Claude)", "campo imp_termino_potencia_eur", pot_claude)
        if abs(diff_pot) > 0.02:
            row("  ↳ vs. cálculo propio", f"diff = {diff_pot:+.2f} €", diff_pot, estimado=True)
        pot_total = pot_claude
    else:
        row("  SUBTOTAL potencia (*calc)", "Σ pN × kW × días", pot_total, estimado=True)

    # ════════════════════════════════════════════════════════
    # BLOQUE ENERGÍA
    # ════════════════════════════════════════════════════════
    sep()
    print(f"  │  {'ENERGÍA':<{W-4}}│")
    sep()
    ene_total  = 0.0
    ene_claude = result.imp_termino_energia_eur or 0.0
    periodos_pe = [
        ("P1", result.pe_p1, result.consumo_p1_kwh),
        ("P2", result.pe_p2, result.consumo_p2_kwh),
        ("P3", result.pe_p3, result.consumo_p3_kwh),
        ("P4", result.pe_p4, result.consumo_p4_kwh),
        ("P5", result.pe_p5, result.consumo_p5_kwh),
        ("P6", result.pe_p6, result.consumo_p6_kwh),
    ]
    for pn, pe, kwh in periodos_pe:
        if pe and kwh:
            val  = pe * kwh
            ene_total += val
            fml  = f"{kwh} kWh × {pe:.6f}"
            row(f"  Energía {pn}", fml, val)
    if ene_claude:
        diff_ene = ene_claude - ene_total
        row("  SUBTOTAL energía (Claude)", "campo imp_termino_energia_eur", ene_claude)
        if abs(diff_ene) > 0.02:
            row("  ↳ vs. cálculo propio", f"diff = {diff_ene:+.2f} €", diff_ene, estimado=True)
        ene_total = ene_claude
    else:
        row("  SUBTOTAL energía (*calc)", "Σ pN × kWh", ene_total, estimado=True)

    # ════════════════════════════════════════════════════════
    # BLOQUE IMPUESTOS Y SERVICIOS
    # ════════════════════════════════════════════════════════
    sep()
    print(f"  │  {'IMPUESTOS Y SERVICIOS':<{W-4}}│")
    sep()

    iee_eur      = result.imp_impuesto_electrico_eur or 0.0
    alquiler_eur = result.imp_alquiler_eur           or 0.0
    iva_eur      = result.imp_iva_eur                or 0.0
    bono         = result.bono_social                or 0.0

    # IEE — mostrar también cálculo desde %
    if result.imp_ele and not iee_eur:
        iee_base = pot_total + ene_total
        iee_eur  = iee_base * result.imp_ele / 100
        row("  IEE (*calc)", f"{result.imp_ele}% × base", iee_eur, estimado=True)
    elif iee_eur:
        fml_iee = f"campo imp_impuesto_electrico_eur"
        if result.imp_ele:
            fml_iee = f"{result.imp_ele}% → {iee_eur:.2f}"
        row("  Impuesto eléctrico", fml_iee, iee_eur)

    # Alquiler — mostrar €/día × días
    if not alquiler_eur and result.alq_eq_dia and dias:
        alquiler_eur = result.alq_eq_dia * dias
        row("  Alquiler (*calc)", f"{result.alq_eq_dia} €/día × {dias}d", alquiler_eur, estimado=True)
    elif alquiler_eur:
        fml_alq = f"campo imp_alquiler_eur"
        if result.alq_eq_dia and dias:
            fml_alq = f"{result.alq_eq_dia} €/día × {dias}d"
        row("  Alquiler contador", fml_alq, alquiler_eur)

    if bono:
        row("  Bono social", "campo bono_social", -bono)

    # Descuentos línea a línea
    desc_sum = 0.0
    for nombre, val in (result.descuentos or {}).items():
        if isinstance(val, (int, float)):
            desc_sum += val
            row(f"  Dto: {nombre[:24]}", "descuentos[...]", val)

    # IVA — mostrar % × base si disponible
    if not iva_eur and result.iva:
        iva_base = pot_total + ene_total + iee_eur + alquiler_eur - bono + desc_sum
        iva_eur  = iva_base * result.iva / 100
        row("  IVA (*calc)", f"{result.iva}% × base", iva_eur, estimado=True)
    elif iva_eur:
        fml_iva = f"campo imp_iva_eur"
        if result.iva:
            fml_iva = f"{result.iva}% → {iva_eur:.2f}"
        row("  IVA", fml_iva, iva_eur)

    # ════════════════════════════════════════════════════════
    # BLOQUE OTROS
    # ════════════════════════════════════════════════════════
    otros_items = {
        k: v for k, v in (result.otros or {}).items()
        if isinstance(v, (int, float)) and k not in ("alq_eq_dia", "cuotaAlquilerMes")
    }
    otros_sum = sum(otros_items.values())
    if otros_items:
        sep()
        print(f"  │  {'OTROS CONCEPTOS':<{W-4}}│")
        sep()
        for nombre, val in otros_items.items():
            row(f"  {nombre[:30]}", "otros[...]", val)

    # ════════════════════════════════════════════════════════
    # TOTALES
    # ════════════════════════════════════════════════════════
    sep()
    suma = pot_total + ene_total + iee_eur + alquiler_eur + iva_eur - bono + desc_sum + otros_sum
    diff = abs(suma - importe)
    pct  = (diff / importe * 100) if importe else 0.0
    ok   = pct <= 5.0

    print(f"  │  {'SUMA CONCEPTOS':<28} {'':24} {suma:>+10.2f} €  │")
    print(f"  │  {'IMPORTE FACTURA (PDF)':<28} {'':24} {importe:>+10.2f} €  │")
    print(f"  │  {'Diferencia':<28} {'':24} {diff:>+10.2f} €  │")
    sep()
    s_icon = "✅" if ok else "⚠️ "
    print(f"  │  {s_icon}  {'Margen error servidor':<{W-14}} {pct:>+8.2f} %  │")
    if result.margen_de_error is not None:
        c_icon = "✅" if result.margen_de_error <= 5.0 else "⚠️ "
        print(f"  │  {c_icon}  {'Margen error Claude':<{W-14}} {result.margen_de_error:>+8.2f} %  │")

    # Advertencia si hay campos EUR ausentes
    missing = [f for f, v in [
        ("imp_termino_potencia_eur",   result.imp_termino_potencia_eur),
        ("imp_termino_energia_eur",    result.imp_termino_energia_eur),
        ("imp_impuesto_electrico_eur", result.imp_impuesto_electrico_eur),
        ("imp_alquiler_eur",           result.imp_alquiler_eur),
        ("imp_iva_eur",                result.imp_iva_eur),
    ] if not v]
    if missing:
        sep()
        print(f"  │  ⚠️  Campos EUR no rellenados por Claude (valores con (*) son estimados):{'':>{W-74}}│")
        for m in missing:
            print(f"  │     · {m:<{W-7}}│")
    print(f"  └{'─'*W}┘")


@router.post("/extraer", response_model=ExtractionResponseAI,
             response_model_exclude=_EXCLUDE)
async def extraer_factura(
    file: UploadFile = File(...),
    data: Optional[str] = Form(None, description='JSON: {"cliente": {...}, "ce": {...}, "Fsmstate": "...", "FsmPrevious": "..."}'),
):
    """
    Recibe una factura PDF y extrae los campos usando Claude API.
    El campo 'data' (JSON opcional) puede incluir cliente, ce, Fsmstate, etc.
    Si 'data' contiene cliente.correo, busca dealId y mpklogId en Zoho CRM.
    """
    # Parsear data opcional
    extra: dict = {}
    if data:
        try:
            extra = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Campo 'data' no es JSON válido.")

    correo = extra.get("cliente", {}).get("correo", "")
    print(f"\n  [/facturas/extraer] ficheiro: {file.filename}  |  correo: {correo or '(no proporcionado)'}")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()

    try:
        result = extract_with_claude(pdf_bytes)
    except anthropic.APIStatusError as e:
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  [ERROR]  APIStatusError {e.status_code}: {msg}")
        raise HTTPException(status_code=502, detail=f"Error de la API de Claude ({e.status_code}): {e}")
    except anthropic.APITimeoutError:
        print("  [ERROR]  APITimeoutError")
        raise HTTPException(status_code=504, detail="Timeout llamando a la API de Claude.")
    except Exception as e:
        import traceback
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  [ERROR]  Error inesperado: {msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {e}")

    _log_cuadre(result)

    # Buscar dealId y mpklogId en Zoho CRM si hay correo
    deal_id, mpklog_id = None, None
    if correo:
        deal_id, mpklog_id = await asyncio.gather(
            buscar_deal_por_email(correo),
            buscar_mpklog_por_email(correo),
        )
        if deal_id:
            print(f"  ✅  dealId: {deal_id}")
        if mpklog_id:
            print(f"  ✅  mpklogId: {mpklog_id}")

    # Inyectar dealId/mpklogId en cliente
    if "cliente" in extra:
        extra["cliente"]["dealId"]   = deal_id
        extra["cliente"]["mpklogId"] = mpklog_id

    # Construir payload completo para la sesión
    session_payload = {
        **extra,                             # cliente, ce, Fsmstate, FsmPrevious, ...
        "factura":  _build_factura_payload(result),
        "dealId":   deal_id,
        "mpklogId": mpklog_id,
    }

    result.session_id = crear_sesion(session_payload)
    print(f"  ✅  Sessão criada: {result.session_id}")

    # Guardar JSON local
    cups   = result.cups or "sin_cups"
    inicio = (result.periodo_inicio or "").replace("/", "-")
    fin    = (result.periodo_fin    or "").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}.json"
    ruta   = os.path.join(RESULTADOS_DIR, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(session_payload, f, ensure_ascii=False, indent=2)
    print(f"  ✅  JSON local guardado: resultados/{nombre}")

    # WorkDrive upload (non-blocking)
    _nomedopdf = os.path.splitext(file.filename)[0]
    _tarifa    = result.tarifa_acceso or "sin_tarifa"
    print(f"  ⏳  WorkDrive: agendando upload para '{_nomedopdf}_{_tarifa}/'...")
    asyncio.create_task(
        upload_factura_files(
            nomedopdf       = _nomedopdf,
            tarifa_acceso   = _tarifa,
            pdf_bytes       = pdf_bytes,
            result          = result,
            session_payload = session_payload,
        )
    )

    return result
