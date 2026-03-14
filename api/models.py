# api/models.py
# Schemas Pydantic para request y response del endpoint /facturas/extraer.
#
# Modificado: 2026-02-27 | Rodrigo Costa

from pydantic import BaseModel
from typing import Optional


class ExtractionResponse(BaseModel):
    # ── Campos extraídos del PDF ──────────────────────────────────────────────
    cups:               Optional[str] = None
    periodo_inicio:     Optional[str] = None
    periodo_fin:        Optional[str] = None
    comercializadora:   Optional[str] = None
    pp_p1:              Optional[float] = None
    pp_p2:              Optional[float] = None
    imp_ele:            Optional[float] = None
    iva:                Optional[int] = None
    alq_eq_dia:         Optional[float] = None

    # ── Campos completados por API Ingebau ────────────────────────────────────
    tarifa_acceso:      Optional[str] = None
    distribuidora:      Optional[str] = None
    pot_p1_kw:          Optional[float] = None
    pot_p2_kw:          Optional[float] = None
    pot_p3_kw:          Optional[float] = None
    pot_p4_kw:          Optional[float] = None
    pot_p5_kw:          Optional[float] = None
    pot_p6_kw:          Optional[float] = None
    consumo_p1_kwh:     Optional[float] = None
    consumo_p2_kwh:     Optional[float] = None
    consumo_p3_kwh:     Optional[float] = None
    consumo_p4_kwh:     Optional[float] = None
    consumo_p5_kwh:     Optional[float] = None
    consumo_p6_kwh:     Optional[float] = None
    dias_facturados:    Optional[str] = None
    pp_p1:              Optional[float] = None
    pp_p2:              Optional[float] = None
    pp_p3:              Optional[float] = None  # ← adicionar
    pp_p4:              Optional[float] = None  # ← adicionar
    pp_p5:              Optional[float] = None  # ← adicionar
    pp_p6:              Optional[float] = None  # ← adicionar
    imp_ele:            Optional[float] = None

    # ── Metadatos ─────────────────────────────────────────────────────────────
    api_ok:             bool = False
    api_error:          Optional[str] = None
    fichero_json:       Optional[str] = None  # ruta del JSON guardado