# api/models.py
# Schemas Pydantic para request y response del endpoint /facturas/extraer.
#
# Modificado: 2026-02-27 | Rodrigo Costa

from pydantic import BaseModel
from typing import Optional


class ExtractionResponse(BaseModel):

    # ── Campos extraídos del PDF ──────────────────────────────────────────────
    cups:               Optional[str]   = None
    periodo_inicio:     Optional[str]   = None
    periodo_fin:        Optional[str]   = None
    comercializadora:   Optional[str]   = None
    pp_p1:              Optional[float] = None
    pp_p2:              Optional[float] = None
    pp_p3:              Optional[float] = None  # ex: CoxParser (3.0TD)
    pp_p4:              Optional[float] = None  # ex: CoxParser (3.0TD)
    pp_p5:              Optional[float] = None  # ex: CoxParser (3.0TD)
    pp_p6:              Optional[float] = None  # ex: CoxParser (3.0TD)
    pe_p1:              Optional[float] = None  # precio energía P1 (€/kWh)
    pe_p2:              Optional[float] = None  # precio energía P2 (€/kWh)
    pe_p3:              Optional[float] = None  # precio energía P3 (€/kWh)
    pe_p4:              Optional[float] = None  # precio energía P4 (€/kWh)
    pe_p5:              Optional[float] = None  # precio energía P5 (€/kWh)
    pe_p6:              Optional[float] = None  # precio energía P6 (€/kWh)
    imp_ele:            Optional[float] = None
    iva:                Optional[int]   = None
    alq_eq_dia:         Optional[float] = None
    bono_social:        Optional[float] = None
    descuentos:         Optional[dict]  = None
    importe_factura:    Optional[float] = None

    # ── Campos completados por API Ingebau ────────────────────────────────────
    tarifa_acceso:      Optional[str]   = None
    distribuidora:      Optional[str]   = None
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
    dias_facturados:    Optional[str]   = None

    # ── Metadatos ─────────────────────────────────────────────────────────────
    api_ok:             bool            = False
    api_error:          Optional[str]   = None
    fichero_json:       Optional[str]   = None


class ClaudeExtractionInput(BaseModel):
    """Modelo slim para output_format de messages.parse().
    Sem campos Optional — usa defaults 0.0/""/dict vazio para evitar union types
    que causam timeout de compilação na API. O mapper converte zeros/vazios → None.
    Períodos extra (pp_p3..p6, pe_p4..p6) vão em 'otros'."""

    cups:               str   = ""
    periodo_inicio:     str   = ""
    periodo_fin:        str   = ""
    comercializadora:   str   = ""
    importe_factura:    float = 0.0
    pp_p1:              float = 0.0
    pp_p2:              float = 0.0
    pe_p1:              float = 0.0
    pe_p2:              float = 0.0
    pe_p3:              float = 0.0
    imp_ele:            float = 0.0
    iva:                int   = 0
    alq_eq_dia:         float = 0.0
    bono_social:        float = 0.0
    imp_termino_energia_eur:    float = 0.0
    imp_termino_potencia_eur:   float = 0.0
    imp_impuesto_electrico_eur: float = 0.0
    imp_alquiler_eur:           float = 0.0
    imp_iva_eur:                float = 0.0
    otros:              str   = ""  # JSON string com pp_p3..p6, pe_p4..p6, descuentos, etc.


class IVABlock(BaseModel):
    """Bloque IVA estructurado — soporta IVA único o fracionado (RDL 8/2023)."""
    IVA_PERCENT_1:          Optional[int]   = None
    IVA_PERCENT_2:          Optional[int]   = None
    IVA_BASE_IMPONIBLE_1:   Optional[float] = None
    IVA_BASE_IMPONIBLE_2:   Optional[float] = None
    IVA_SUBTOTAL_EUROS_1:   Optional[float] = None
    IVA_SUBTOTAL_EUROS_2:   Optional[float] = None
    IVA_TOTAL_EUROS:        Optional[float] = None


class ValidacionCuadre(BaseModel):
    cuadra:             bool
    importe_factura:    Optional[float] = None
    suma_conceptos:     Optional[float] = None
    diferencia_eur:     Optional[float] = None
    error:              Optional[str]   = None


class ExtractionResponseAI(ExtractionResponse):
    """Extiende ExtractionResponse con importes en € extraídos por Claude
    y los campos de reconciliación contable (R13)."""

    # IEE en €/kWh (formato post RDL 7/2026 — null si viene como porcentaje)
    imp_ele_eur_kwh:                Optional[float]    = None

    # Importes en € de cada línea de la factura (extraídos por Claude)
    imp_termino_energia_eur:        Optional[float]    = None
    imp_termino_potencia_eur:       Optional[float]    = None
    imp_impuesto_electrico_eur:     Optional[float]    = None
    imp_alquiler_eur:               Optional[float]    = None
    imp_iva_eur:                    Optional[float]    = None

    # Nuevos campos raíz de importes totales
    impuesto_electricidad_importe:  Optional[float]    = None
    alquiler_equipos_medida_importe: Optional[float]   = None
    IVA_TOTAL_EUROS:                Optional[float]    = None

    # Bloque IVA estructurado (IVA único o fracionado)
    IVA:                            Optional[IVABlock] = None

    # Conceptos no estándar con estructura costes/creditos/observacion
    otros:                          Optional[dict]     = None

    # Reconciliación contable: % de desviación entre suma conceptos e importe
    margen_de_error:                Optional[float]    = None

    # Reconciliación contable R13 (calculada en el servidor)
    validacion_cuadre:              Optional[ValidacionCuadre] = None

    # ID de sesión creada en /sesion tras la extracción
    session_id:                     Optional[str]      = None