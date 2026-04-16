# Payload Restructure — Implementación Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reestruturar o payload de facturas adicionando `otros.costes/creditos/observacion`, bloco `IVA` estruturado, novos campos raíz de importes, remover `descuentos` do raíz, corrigir `0.0` vs `null` e adicionar regras por comercializadora.

**Architecture:** As mudanças atravessam 4 camadas em ordem: (1) modelos Pydantic, (2) parser de resposta do Claude, (3) construtor do payload de sessão, (4) prompt do Claude. Cada camada depende da anterior. Sem testes automatizados — validação manual via Swagger UI + log do terminal.

**Tech Stack:** Python 3.x, FastAPI, Pydantic v2, Anthropic SDK (claude-sonnet-4-6)

---

## Ficheiros modificados

| Acção | Ficheiro | O que muda |
|---|---|---|
| Modificar | `api/models.py` | Adicionar `IVABlock`; novos campos em `ExtractionResponseAI` |
| Modificar | `api/claude/extractor.py` | `_build_response`: converter `IVA` dict → `IVABlock`; handle `otros` novo formato |
| Modificar | `api/routes/facturas.py` | `_build_factura_payload`: novo `otros`, remover `descuentos`, adicionar novos campos; `_log_cuadre`: ler de `otros.creditos/costes` |
| Modificar | `api/claude/prompts.py` | `_PREAMBLE`: todas as novas instruções |

---

## Task 1: Adicionar `IVABlock` e novos campos ao modelo Pydantic

**Files:**
- Modify: `api/models.py`

- [ ] **Step 1: Adicionar classe `IVABlock` antes de `ValidacionCuadre`**

Em `api/models.py`, inserir após a linha `class ClaudeExtractionInput(BaseModel):` block (após linha 85, antes de `class ValidacionCuadre`):

```python
class IVABlock(BaseModel):
    """Bloque IVA estructurado — soporta IVA único o fracionado (RDL 8/2023)."""
    IVA_PERCENT_1:          Optional[int]   = None
    IVA_PERCENT_2:          Optional[int]   = None
    IVA_BASE_IMPONIBLE_1:   Optional[float] = None
    IVA_BASE_IMPONIBLE_2:   Optional[float] = None
    IVA_SUBTOTAL_EUROS_1:   Optional[float] = None
    IVA_SUBTOTAL_EUROS_2:   Optional[float] = None
    IVA_TOTAL_EUROS:        Optional[float] = None
```

- [ ] **Step 2: Adicionar novos campos a `ExtractionResponseAI`**

Em `api/models.py`, substituir o bloco de `ExtractionResponseAI` por:

```python
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
```

- [ ] **Step 3: Verificar que o servidor arranca sem erros**

```bash
py -3.13 -m uvicorn api.main:app --port 8000
```

Esperado: `Application startup complete.` sem erros de importação.

- [ ] **Step 4: Commit**

```bash
git add api/models.py
git commit -m "feat: add IVABlock model and new root fields to ExtractionResponseAI"
```

---

## Task 2: Actualizar `_build_response` para converter `IVA` dict → `IVABlock`

**Files:**
- Modify: `api/claude/extractor.py:40-54`

- [ ] **Step 1: Substituir a função `_build_response`**

```python
def _build_response(data: dict) -> ExtractionResponseAI:
    """Filtra claves desconocidas y construye ExtractionResponseAI.
    Convierte 'otros' y 'descuentos' de string JSON a dict si es necesario.
    Convierte 'IVA' dict → IVABlock."""
    from api.models import IVABlock

    filtered = {k: v for k, v in data.items() if k in _VALID_FIELDS}

    # String JSON → dict para otros y descuentos
    for field in ("otros", "descuentos"):
        val = filtered.get(field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val) if val.strip() else None
                filtered[field] = parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, ValueError):
                filtered[field] = None

    # Dict → IVABlock
    iva_val = filtered.get("IVA")
    if isinstance(iva_val, dict):
        try:
            filtered["IVA"] = IVABlock(**{
                k: v for k, v in iva_val.items()
                if k in IVABlock.model_fields
            })
        except Exception:
            filtered["IVA"] = None
    elif iva_val is not None and not isinstance(iva_val, IVABlock):
        filtered["IVA"] = None

    return ExtractionResponseAI(**filtered)
```

- [ ] **Step 2: Verificar arranque**

```bash
py -3.13 -m uvicorn api.main:app --port 8000
```

Esperado: `Application startup complete.`

- [ ] **Step 3: Commit**

```bash
git add api/claude/extractor.py
git commit -m "feat: convert IVA dict to IVABlock in _build_response"
```

---

## Task 3: Actualizar `_build_factura_payload` — nova estrutura `otros`, remover `descuentos`

**Files:**
- Modify: `api/routes/facturas.py:28-100`

- [ ] **Step 1: Substituir `_build_factura_payload` completo**

```python
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
```

- [ ] **Step 2: Actualizar `_EXCLUDE` para excluir `descuentos` do response da API**

Localizar em `api/routes/facturas.py`:
```python
_EXCLUDE = {"api_ok", "api_error", "fichero_json"}
```
Substituir por:
```python
_EXCLUDE = {"api_ok", "api_error", "fichero_json", "descuentos"}
```

- [ ] **Step 3: Verificar arranque e testar via Swagger**

```bash
py -3.13 -m uvicorn api.main:app --port 8000
```

Abrir `http://localhost:8000/docs` → `POST /facturas/extraer` → enviar um PDF.

Verificar no payload da sessão:
- `factura.otros` tem `costes`, `creditos`, `observacion`
- `factura.otros` NÃO tem `descuentos`
- `factura` raíz NÃO tem `descuentos`
- `factura.IVA` presente (pode ser `null` se Claude ainda não preencheu)

- [ ] **Step 4: Commit**

```bash
git add api/routes/facturas.py
git commit -m "feat: restructure otros with costes/creditos/observacion, remove descuentos from payload"
```

---

## Task 4: Actualizar `_log_cuadre` para nova estrutura `otros`

**Files:**
- Modify: `api/routes/facturas.py` — função `_log_cuadre`

- [ ] **Step 1: Actualizar leitura de descontos e outros na função `_log_cuadre`**

Localizar o bloco:
```python
    bono     = result.bono_social or 0.0
    desc_sum = sum((result.descuentos or {}).values())
    otros_sum = sum(
        v for v in (result.otros or {}).values()
        if isinstance(v, (int, float))
    )
```

Substituir por:
```python
    bono        = result.bono_social or 0.0
    otros_raw   = result.otros or {}
    costes_dict = otros_raw.get("costes") or {}
    creditos_dict = otros_raw.get("creditos") or {}

    # Soma de creditos (descuentos, compensacion) — já negativos
    desc_sum = sum(
        v for v in creditos_dict.values()
        if isinstance(v, (int, float)) and v is not None
    )
    # Migração: se creditos vazio, ler de descuentos ainda existente
    if not desc_sum and result.descuentos:
        desc_sum = sum(
            v for v in result.descuentos.values()
            if isinstance(v, (int, float))
        )

    # Soma de costes extra — excluir alquiler e bono para não duplicar
    _skip_costes = {"alquiler_equipos_medida_importe", "bono_social_importe"}
    otros_sum = sum(
        v for k, v in costes_dict.items()
        if isinstance(v, (int, float)) and v is not None
        and k not in _skip_costes
    )
```

Localizar o bloco de log de descuentos e otros:
```python
    if desc_sum:
        print(f"  │  {'Descuentos (suma)':<34} {desc_sum:>+10.2f} €  │")
    if otros_sum:
        print(f"  │  {'Otros (suma)':<34} {otros_sum:>+10.2f} €  │")
```

Substituir por:
```python
    if desc_sum:
        print(f"  │  {'Créditos/descuentos (suma)':<34} {desc_sum:>+10.2f} €  │")
    if otros_sum:
        print(f"  │  {'Costes extra (suma)':<34} {otros_sum:>+10.2f} €  │")
```

Localizar no bloco OTROS CONCEPTOS:
```python
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
```

Substituir por:
```python
    if costes_dict or creditos_dict:
        sep()
        print(f"  │  {'OTROS CONCEPTOS':<{W-4}}│")
        sep()
        for nombre, val in costes_dict.items():
            if isinstance(val, (int, float)) and val is not None:
                row(f"  costes.{nombre[:26]}", "otros.costes", val)
        for nombre, val in creditos_dict.items():
            if isinstance(val, (int, float)) and val is not None:
                row(f"  creditos.{nombre[:24]}", "otros.creditos", val)
```

- [ ] **Step 2: Verificar log no terminal**

Enviar PDF via Swagger. O terminal deve mostrar:
```
  │  OTROS CONCEPTOS                                                           │
  ├────────────────────────────────────────────────────────────────────────────┤
  │    costes.exceso_potencia_importe   otros.costes       +118.65 €  │
  │    costes.coste_energia_reactiva    otros.costes        +55.08 €  │
  │    creditos.descuento_10pct         otros.creditos      -10.41 €  │
```

- [ ] **Step 3: Commit**

```bash
git add api/routes/facturas.py
git commit -m "feat: update _log_cuadre to read from otros.costes/creditos"
```

---

## Task 5: Actualizar o prompt — novas instruções para toda a estrutura

**Files:**
- Modify: `api/claude/prompts.py`

- [ ] **Step 1: Substituir o `_PREAMBLE` completo**

```python
_PREAMBLE = (
    "Eres un extractor de datos de facturas eléctricas españolas.\n"
    "Tu única tarea es leer el PDF adjunto y devolver un JSON estructurado "
    "con todos los campos que puedas extraer.\n"
    "NO escribas ficheros. NO ejecutes scripts. Solo devuelve el JSON.\n"
    "Los campos 'validacion_cuadre' y 'session_id' deben ser siempre null "
    "(se calculan en el servidor).\n"
    "\n"
    "PRECISIÓN NUMÉRICA: nunca redondees ningún valor numérico. Preserva todos los "
    "decimales exactamente como aparecen en la factura. "
    "Ejemplos correctos: 5.11269632 (no 5.11), 0.197918 (no 0.198), "
    "0.073783 (no 0.074).\n"
    "\n"
    "ZEROS vs NULL: usa null (no 0.0) para períodos que no existen en la tarifa. "
    "Ejemplos: tarifa 2.0TD → pot_p3_kw..pot_p6_kw = null, consumo_p4_kwh..consumo_p6_kwh = null. "
    "Usa 0.0 solo para períodos que SÍ existen en la tarifa pero tuvieron consumo/potencia cero.\n"
    "\n"
    "CAMPO 'otros' — estructura obligatoria. Devolver SIEMPRE como dict (no string) con:\n"
    "  {\n"
    "    'costes': {\n"
    "      'bono_social_importe': <total € del período o null>,\n"
    "      'exceso_potencia_importe': <importe exceso potencia € o null>,\n"
    "      'alquiler_equipos_medida_importe': <total alquiler € del período o null>,\n"
    "      'coste_energia_reactiva': <importe energía reactiva € o null>\n"
    "    },\n"
    "    'creditos': {\n"
    "      'compensacion_excedentes_kwh': <kWh negativos o null>,\n"
    "      'compensacion_excedentes_importe': <importe negativo o null>,\n"
    "      <nombre_descuento>: <importe negativo o null>  (uno por cada descuento)\n"
    "    },\n"
    "    'observacion': [<lista de strings con notas, nunca null — lista vacía si no hay>]\n"
    "  }\n"
    "Regla: costes siempre positivo, creditos siempre negativo. "
    "Campo ausente en la factura → null (no omitir la clave).\n"
    "NO incluir 'descuentos' dentro de 'otros' — los descuentos van en 'otros.creditos'.\n"
    "\n"
    "BLOQUE IVA — rellenar siempre el campo 'IVA' con:\n"
    "  {\n"
    "    'IVA_PERCENT_1': <tipo principal, ej: 21>,\n"
    "    'IVA_PERCENT_2': <tipo reducido o null>,\n"
    "    'IVA_BASE_IMPONIBLE_1': <base del tipo principal €>,\n"
    "    'IVA_BASE_IMPONIBLE_2': <base del tipo reducido € o null>,\n"
    "    'IVA_SUBTOTAL_EUROS_1': <importe tipo principal €>,\n"
    "    'IVA_SUBTOTAL_EUROS_2': <importe tipo reducido € o null>,\n"
    "    'IVA_TOTAL_EUROS': <suma total IVA €>\n"
    "  }\n"
    "También rellenar 'IVA_TOTAL_EUROS' al nivel raíz del JSON (mismo valor).\n"
    "\n"
    "CAMPOS OBLIGATORIOS — subtotales en € que DEBES rellenar siempre:\n"
    "  - imp_termino_potencia_eur: total término potencia €\n"
    "  - imp_termino_energia_eur: total término energía €\n"
    "  - imp_impuesto_electrico_eur: importe IEE €\n"
    "  - imp_alquiler_eur: importe alquiler equipos €\n"
    "  - imp_iva_eur: importe total IVA € (mismo que IVA.IVA_TOTAL_EUROS)\n"
    "  - impuesto_electricidad_importe: igual que imp_impuesto_electrico_eur\n"
    "  - alquiler_equipos_medida_importe: igual que imp_alquiler_eur\n"
    "\n"
    "CAMPO 'descuentos' (nivel raíz): mantener null o vacío. "
    "Los descuentos van SOLO en 'otros.creditos'.\n"
    "\n"
    "VALIDACIÓN OBLIGATORIA antes de devolver el JSON — sigue estos pasos en orden:\n"
    "  1. Suma: imp_termino_potencia_eur + imp_termino_energia_eur "
    "+ imp_impuesto_electrico_eur + imp_alquiler_eur + imp_iva_eur "
    "+ sum(otros.costes values, excluir alquiler y bono ya contados) "
    "+ sum(otros.creditos values, negativos).\n"
    "  2. margen_de_error = |suma - importe_factura| / importe_factura * 100.\n"
    "  3. Si margen_de_error > 5: REVISAR. Busca conceptos faltantes "
    "(excesos de potencia, energía reactiva, servicios adicionales) y añádelos "
    "en 'otros.costes'. Corrige importes en € mal extraídos. Repite.\n"
    "  4. Incluir siempre 'margen_de_error' en el JSON. "
    "Si importe_factura es null → margen_de_error: null.\n"
    "\n"
    "CRÍTICO — campos pp_p1..pp_p6 (precio de potencia): "
    "SIEMPRE en €/kW·día. Detecta la unidad y convierte: "
    "(a) €/kW·año → divide entre 365. "
    "(b) €/kW·mes → divide entre dias_facturados. "
    "Sin unidad indicada → asume €/kW·año y divide entre 365. "
    "Añadir en otros.observacion: 'pp_p* convertido de €/kW/año a €/kW/día dividiendo por 365'. "
    "SUB-PERÍODOS (Energía XXI): media ponderada por días antes de convertir. "
    "Añadir: 'pp_p* y pe_p* calculados como media ponderada de N sub-periodos por cambio de tarifas'.\n"
    "\n"
    "REGLAS POR COMERCIALIZADORA:\n"
    "  Octopus: Punta=P1, Llano=P2, Valle=P3. "
    "Si solo factura Punta y Valle: pp_p2=null, pp_p3=<precio valle>. "
    "Añadir en otros.observacion: 'Octopus: Punta=P1, Llano=P2, Valle=P3'.\n"
    "  Iberdrola 3.0TD: pp_p* = suma peajes+cargos por período. "
    "Añadir: 'pp_p* calculado como suma peajes+cargos por periodo'.\n"
    "  Iberdrola con autoconsumo: compensacion_excedentes_kwh (negativo) y "
    "compensacion_excedentes_importe (negativo) en otros.creditos. "
    "Añadir: 'Compensacion excedentes detectada'.\n"
    "  Iberdrola IVA fracionado: IVA con dos tramos. iva = tipo principal. "
    "Añadir: 'IVA fraccionado: X% + Y%'.\n"
    "  Cox Energy: alquiler_equipos_medida_importe = suma de TODOS los contadores. "
    "alq_eq_dia = valor del contador individual. "
    "Añadir: 'Alquiler con N contadores: importe_total = N × importe_individual'.\n"
    "  Tarifa 2.0TD con discriminación P1/P3 (sin P2): pot_p2_kw=null. "
    "Añadir: 'pot_p2_kw null: tarifa 2.0TD con discriminacion P1/P3'.\n"
)
```

- [ ] **Step 2: Verificar que o SYSTEM_PROMPT carrega sem erros**

```bash
py -3.13 -c "from api.claude.prompts import SYSTEM_PROMPT; print(f'OK — {len(SYSTEM_PROMPT)} chars')"
```

Esperado: `OK — NNNN chars` (sem excepções).

- [ ] **Step 3: Verificar arranque**

```bash
py -3.13 -m uvicorn api.main:app --port 8000
```

Esperado: `Application startup complete.`

- [ ] **Step 4: Commit**

```bash
git add api/claude/prompts.py
git commit -m "feat: update Claude prompt with otros structure, IVA block, precision rules, comercializadora rules"
```

---

## Task 6: Teste de integração completo

**Files:** nenhum — validação manual

- [ ] **Step 1: Enviar fatura 2.0TD simples (ex: Iberdrola ou Repsol)**

Abrir `http://localhost:8000/docs` → `POST /facturas/extraer`.

Verificar no JSON da resposta:
- `otros` tem chaves `costes`, `creditos`, `observacion`
- `otros` NÃO tem `descuentos`
- `IVA` não é null (tem pelo menos `IVA_PERCENT_1` e `IVA_TOTAL_EUROS`)
- `IVA_TOTAL_EUROS` no raíz não é null
- `impuesto_electricidad_importe` não é null
- `alquiler_equipos_medida_importe` não é null
- `pot_p3_kw`..`pot_p6_kw` são null (não 0.0) para 2.0TD
- `observacion` é lista (pode ser vazia `[]`)

- [ ] **Step 2: Verificar log do cuadre no terminal**

Deve mostrar bloco `OTROS CONCEPTOS` com itens de `costes` e `creditos` separados.
`Margen error servidor` e `Margen error Claude` devem estar próximos.

- [ ] **Step 3: Enviar fatura 3.0TD (ex: Quantium/Iberdrola 3.0TD)**

Verificar:
- `otros.costes.exceso_potencia_importe` preenchido se houver excesso
- `otros.costes.coste_energia_reactiva` preenchido se houver reactiva
- `observacion` inclui string sobre conversão de pp_p*
- `margen_de_error` ≤ 5% (ou próximo)

- [ ] **Step 4: Verificar payload na sessão via GET /sesion/{id}**

Copiar `session_id` da resposta e fazer `GET /sesion/{session_id}`.

Verificar `data.factura`:
- Tem `IVA` (dict ou null)
- Tem `impuesto_electricidad_importe`
- Tem `alquiler_equipos_medida_importe`  
- NÃO tem `descuentos` no raíz
- `otros` tem `costes`, `creditos`, `observacion`

- [ ] **Step 5: Commit final**

```bash
git add .
git commit -m "feat: payload restructure v2 complete — otros costes/creditos, IVA block, new fields"
```

---

## Referência rápida — Estrutura `otros` esperada por comercializadora

### 2.0TD sem autoconsumo (caso base)
```json
"otros": {
  "costes": {
    "bono_social_importe": 0.15,
    "exceso_potencia_importe": null,
    "alquiler_equipos_medida_importe": 0.64,
    "coste_energia_reactiva": null
  },
  "creditos": {},
  "observacion": []
}
```

### 3.0TD com excesso potência e energia reactiva
```json
"otros": {
  "costes": {
    "bono_social_importe": null,
    "exceso_potencia_importe": 118.65,
    "alquiler_equipos_medida_importe": 5.94,
    "coste_energia_reactiva": 55.08
  },
  "creditos": {},
  "observacion": ["pp_p* convertido de €/kW/año a €/kW/día dividiendo por 365"]
}
```

### Iberdrola com autoconsumo e desconto
```json
"otros": {
  "costes": {
    "bono_social_importe": 0.37,
    "exceso_potencia_importe": null,
    "alquiler_equipos_medida_importe": 0.77,
    "coste_energia_reactiva": null
  },
  "creditos": {
    "compensacion_excedentes_kwh": -225.73,
    "compensacion_excedentes_importe": -18.06,
    "descuento_consumo_10pct": -10.41
  },
  "observacion": ["Compensacion excedentes detectada"]
}
```
