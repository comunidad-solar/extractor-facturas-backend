# Multi-Agent Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-model extraction with a 2-stage pipeline where a powerful model reads all raw data from the PDF and 4 focused haiku subagents (running in parallel) apply each their own specific rules to map values to fields.

**Architecture:** Stage 1 uses `claude-opus-4-7` to transcribe ALL raw values from the invoice into a structured `RawInvoiceData` dict — no interpretation, just faithful reading. Stage 2 runs 4 `claude-haiku-4-5-20251001` subagents in parallel via `ThreadPoolExecutor`, each receiving only the raw data and only the rules for its field group. Stage 3 is pure Python: assembles all mapper outputs into `ExtractionResponseAI` and calculates `margen_de_error`. The public API (`extract_with_claude(pdf_bytes) -> ExtractionResponseAI`) stays identical so no routes change.

**Tech Stack:** Python 3.x, `anthropic` SDK (sync), `concurrent.futures.ThreadPoolExecutor` for parallel subagents, FastAPI + Pydantic (unchanged externally).

---

## File Structure

**Create:**
- `api/claude/raw_prompt.py` — Stage 1 system prompt (loose transcription, no rules)
- `api/claude/mappers/__init__.py` — empty
- `api/claude/mappers/base.py` — `call_haiku(system, user_json)` helper
- `api/claude/mappers/potencia.py` — `map_potencia(raw) -> dict`
- `api/claude/mappers/energia.py` — `map_energia(raw) -> dict`
- `api/claude/mappers/cargas.py` — `map_cargas(raw) -> dict` (exceso + reactiva classification)
- `api/claude/mappers/costes.py` — `map_costes(raw) -> dict` (bono, costes dict, creditos dict)
- `api/claude/pipeline.py` — `run_pipeline(pdf_bytes) -> ExtractionResponseAI`

**Modify:**
- `api/claude/extractor.py` — replace body of `extract_with_claude()` to call `run_pipeline()`

---

## RawInvoiceData Schema

Stage 1 produces this JSON. Every mapper receives the full dict.

```json
{
  "meta": {
    "cups": "ES0021...",
    "comercializadora": "QUANTIUM LUX 6.4, SL",
    "distribuidora": "IBERDROLA DISTRIBUCIÓN ELÉCTRICA, S.A.U",
    "tarifa_acceso": "3.0TD",
    "periodo_inicio": "31/10/2025",
    "periodo_fin": "30/11/2025",
    "dias_facturados": 30,
    "nombre_cliente": "EMPRESA XYZ",
    "importe_factura": 1895.42,
    "numero_factura": "FAC-2025-001"
  },
  "termino_potencia": {
    "formula_detectada": "kW × precio × (dias/365)",
    "lineas": [
      {"periodo": "P1", "kw": 22.0, "precio": 0.053859, "unidad_precio": "EUR/kW/anio", "dias": 30, "importe": 9.70},
      {"periodo": "P2", "kw": 27.7, "precio": 0.028087, "unidad_precio": "EUR/kW/anio", "dias": 30, "importe": 6.37}
    ],
    "exceso_potencia": {"descripcion": "Coste Exceso Potencia", "importe": 118.65},
    "margen_comercializacion": {"importe": 5.00},
    "total_bruto": 204.01
  },
  "termino_energia": {
    "lineas": [
      {"periodo": "P2", "kwh": 3879.0, "precio": 0.163966, "unidad_precio": "EUR/kWh", "importe": 636.07},
      {"periodo": "P3", "kwh": 2444.0, "precio": 0.143213, "unidad_precio": "EUR/kWh", "importe": 350.01}
    ],
    "costes_mercado": {"descripcion": "Costes de la energía", "importe": null},
    "reactiva": {"descripcion": "Coste Energía Reactiva", "importe": 55.08},
    "total_activa_bruto": 1225.53,
    "total_bruto": 1280.61
  },
  "impuestos": {
    "iva": [
      {"base": 1566.46, "porcentaje": 21, "importe": 328.96}
    ],
    "iee": {"base": 1485.87, "porcentaje": 5.11269, "importe": 75.9}
  },
  "alquiler": {
    "lineas": [{"precio_dia": 0.198, "dias": 30, "importe": 5.94}],
    "total": 5.94
  },
  "bono_social": null,
  "descuentos": [],
  "otros_costes": [],
  "potencias_contratadas": [
    {"periodo": "P1", "kw": 22.0},
    {"periodo": "P2", "kw": 27.7},
    {"periodo": "P3", "kw": 27.7},
    {"periodo": "P4", "kw": 27.7},
    {"periodo": "P5", "kw": 27.7},
    {"periodo": "P6", "kw": 27.7}
  ]
}
```

---

## Task 1: Stage 1 System Prompt

**Files:**
- Create: `api/claude/raw_prompt.py`

- [ ] **Step 1: Create `api/claude/raw_prompt.py`**

```python
# api/claude/raw_prompt.py
# Prompt for Stage 1: faithful transcription of ALL raw values from the invoice.
# No interpretation, no conversion, no rules — just read what the PDF shows.

RAW_SYSTEM_PROMPT = (
    "Eres un lector de facturas eléctricas españolas. "
    "Tu tarea es transcribir FIELMENTE todos los datos numéricos y textuales de la factura. "
    "NO interpretes, NO conviertas unidades, NO apliques reglas. Solo lee lo que está escrito.\n"
    "\n"
    "Devuelve ÚNICAMENTE un bloque ```json``` con esta estructura exacta "
    "(usa null para campos ausentes, no omitas claves):\n"
    "\n"
    "{\n"
    '  "meta": {\n'
    '    "cups": <string>,\n'
    '    "comercializadora": <string>,\n'
    '    "distribuidora": <string>,\n'
    '    "tarifa_acceso": <string — formato exacto: "2.0TD", "3.0TD", etc.>,\n'
    '    "periodo_inicio": <"DD/MM/YYYY">,\n'
    '    "periodo_fin": <"DD/MM/YYYY">,\n'
    '    "dias_facturados": <int>,\n'
    '    "nombre_cliente": <string>,\n'
    '    "importe_factura": <float>,\n'
    '    "numero_factura": <string o null>\n'
    "  },\n"
    '  "termino_potencia": {\n'
    '    "formula_detectada": <string — ej: "kW × precio × (dias/365)" o "kW × precio × dias">,\n'
    '    "lineas": [\n'
    '      {"periodo": "P1", "kw": <float>, "precio": <float>, "unidad_precio": <"EUR/kW/anio"|"EUR/kW/dia"|"EUR/kW/mes">, "dias": <int>, "importe": <float>}\n'
    "    ],\n"
    '    "exceso_potencia": {"descripcion": <string>, "importe": <float>} o null,\n'
    '    "margen_comercializacion": {"importe": <float>} o null,\n'
    '    "total_bruto": <float — el total que aparece en la factura para potencia>\n'
    "  },\n"
    '  "termino_energia": {\n'
    '    "lineas": [\n'
    '      {"periodo": "P1", "kwh": <float>, "precio": <float>, "unidad_precio": "EUR/kWh", "importe": <float>}\n'
    "    ],\n"
    '    "costes_mercado": {"descripcion": <string>, "importe": <float>} o null,\n'
    '    "reactiva": {"descripcion": <string>, "importe": <float>} o null,\n'
    '    "total_activa_bruto": <float — total energía activa ANTES de reactiva y descuentos>,\n'
    '    "total_bruto": <float — total energía incluyendo reactiva, ANTES de descuentos sobre consumo>\n'
    "  },\n"
    '  "impuestos": {\n'
    '    "iva": [{"base": <float>, "porcentaje": <int>, "importe": <float>}],\n'
    '    "iee": {"base": <float>, "porcentaje": <float — exacto, ej: 5.11269632>, "importe": <float>}\n'
    "  },\n"
    '  "alquiler": {\n'
    '    "lineas": [{"precio_dia": <float>, "dias": <int>, "importe": <float>}],\n'
    '    "total": <float>\n'
    "  },\n"
    '  "bono_social": {\n'
    '    "lineas": [{"precio_dia": <float>, "dias": <int>, "importe": <float>}],\n'
    '    "total": <float>\n'
    "  } o null,\n"
    '  "descuentos": [\n'
    '    {"descripcion": <string>, "importe": <float — negativo>}\n'
    "  ],\n"
    '  "otros_costes": [\n'
    '    {"descripcion": <string>, "importe": <float>}\n'
    "  ],\n"
    '  "potencias_contratadas": [\n'
    '    {"periodo": "P1", "kw": <float>}\n'
    "  ]\n"
    "}\n"
    "\n"
    "REGLAS DE TRANSCRIPCIÓN:\n"
    "- Preserva TODOS los decimales exactamente como aparecen (5.11269632, no 5.11).\n"
    "- Si P1 aparece dos veces (dos tramos), incluye AMBAS líneas en el array.\n"
    "- termino_potencia.total_bruto: el total del BLOQUE de potencia tal como la factura lo muestra "
    "(incluyendo exceso y margen si los agrupa en ese total).\n"
    "- termino_energia.total_activa_bruto: solo energía activa antes de reactiva.\n"
    "- termino_energia.total_bruto: activa + reactiva (si aplica), ANTES de descuentos sobre consumo.\n"
    "- NO incluyas el IVA ni el IEE en los totales de potencia/energía.\n"
)

RAW_USER_TEXT = (
    "Transcribe todos los datos de esta factura en el JSON indicado. "
    "Devuelve ÚNICAMENTE el bloque ```json```. Sin texto adicional."
)
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/raw_prompt.py
git commit -m "feat: add Stage 1 raw extraction prompt"
```

---

## Task 2: Base Mapper Helper

**Files:**
- Create: `api/claude/mappers/__init__.py`
- Create: `api/claude/mappers/base.py`

- [ ] **Step 1: Create `api/claude/mappers/__init__.py`**

```python
# api/claude/mappers/__init__.py
```

- [ ] **Step 2: Create `api/claude/mappers/base.py`**

```python
# api/claude/mappers/base.py
# Shared helper: calls claude-haiku with a system prompt and raw data JSON.
# Returns parsed dict. All mappers use this.

import json
import re

from api.claude.client import get_client

MAPPER_MODEL = "claude-haiku-4-5-20251001"
MAPPER_MAX_TOKENS = 2048


def call_haiku(system_prompt: str, raw_data: dict) -> dict:
    """Call haiku with raw_data as input, return parsed JSON dict."""
    client = get_client()
    user_text = (
        "Datos crudos de la factura:\n"
        "```json\n"
        + json.dumps(raw_data, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "Aplica las reglas del sistema y devuelve ÚNICAMENTE el bloque ```json``` con los campos asignados."
    )
    response = client.messages.create(
        model=MAPPER_MODEL,
        max_tokens=MAPPER_MAX_TOKENS,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )
    text = response.content[0].text if response.content else ""
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Remove trailing commas and retry
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)
        return json.loads(raw)
```

- [ ] **Step 3: Commit**

```bash
git add api/claude/mappers/__init__.py api/claude/mappers/base.py
git commit -m "feat: add haiku mapper base helper"
```

---

## Task 3: Potencia Mapper

**Files:**
- Create: `api/claude/mappers/potencia.py`

Returns: `pp_p1..pp_p6`, `pp_unidad`, `imp_termino_potencia_eur`, `observacion`.

- [ ] **Step 1: Create `api/claude/mappers/potencia.py`**

```python
# api/claude/mappers/potencia.py
# Maps raw potencia lines → pp_p1..pp_p6 (in €/kW·day) and imp_termino_potencia_eur.
# Handles: unit conversion (year/month/day), CASO A weighted average for sub-tramos.

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que calcula los precios de potencia (pp_p*) de una factura eléctrica española.

REGLAS (aplica en orden):
1. pp_p1..pp_p6 deben estar SIEMPRE en €/kW·DÍA. Detectar la unidad desde "formula_detectada" o "unidad_precio":
   - "EUR/kW/anio" o "EUR/kW/año" o formula "× (dias/365)": dividir entre 365. Obs: "pp_p* convertido de €/kW·año ÷ 365".
   - "EUR/kW/anio" con formula "× (dias/366)": dividir entre 366. Obs: "pp_p* convertido de €/kW·año ÷ 366 (año bisiesto)".
   - "EUR/kW/mes" o formula "× (dias/N)": dividir entre los días del mes facturado. Obs: "pp_p* convertido de €/kW·mes ÷ N".
   - "EUR/kW/dia" o formula "× dias": extraer directo, sin conversión.
   - Sin formula explícita: asumir EUR/kW/año, dividir entre 365.
   CRÍTICO: dividir siempre el precio base entre el divisor. NUNCA dividir el importe entre kW·días.

2. Si un período (ej: P1) aparece con MÚLTIPLES LÍNEAS (CASO A — sub-tramos del mismo período tarifario):
   pp_p1 = Σ(dias_i × precio_convertido_i) / Σ(dias_i)
   Obs: "pp_p1 media ponderada de N sub-tramos: (dias1×precio1 + dias2×precio2) / (dias1+dias2)".

3. Si los precios son de tramos temporales (CASO B — todo el período facturado dividido, no un P* específico):
   asignar directamente: tramo1 → pp_p1, tramo2 → pp_p2.
   Indicar en observacion: "pp_p1/pp_p2 son tramos temporales, no períodos tarifarios".

4. imp_termino_potencia_eur: usar "termino_potencia.total_bruto" directamente (ya incluye exceso si lo hay).

5. Períodos sin línea en la factura: pp_p* = null.
   Períodos existentes en tarifa sin potencia contratada: pp_p* = null.

Devuelve ÚNICAMENTE este JSON:
{
  "pp_p1": <float o null>,
  "pp_p2": <float o null>,
  "pp_p3": <float o null>,
  "pp_p4": <float o null>,
  "pp_p5": <float o null>,
  "pp_p6": <float o null>,
  "pp_unidad": "dia",
  "imp_termino_potencia_eur": <float o null>,
  "observacion": [<string>]
}"""


def map_potencia(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/mappers/potencia.py
git commit -m "feat: add potencia mapper (pp_p* conversion + CASO A/B)"
```

---

## Task 4: Energía Mapper

**Files:**
- Create: `api/claude/mappers/energia.py`

Returns: `pe_p1..pe_p6`, `consumo_p1_kwh..consumo_p6_kwh`, `imp_termino_energia_eur`, `observacion`.

- [ ] **Step 1: Create `api/claude/mappers/energia.py`**

```python
# api/claude/mappers/energia.py
# Maps raw energy lines → pe_p* (€/kWh) and consumo_p* (kWh).
# Handles: PRECIO ÚNICO, CASO A (weighted average), CASO B (temporal tramos).

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que asigna los precios de energía (pe_p*) y consumos (consumo_p*) de una factura eléctrica española.

REGLAS (en orden de prioridad):

PRECIO ÚNICO — si todos los kWh tienen el mismo precio independientemente del período horario:
  pe_p1 = ese precio; pe_p2..pe_p6 = null.
  consumo_p1_kwh = total kWh; consumo_p2..p6 = null.
  Obs: "pe_p1 = precio único aplicado a X kWh totales".

CASO A — si un período tarifario específico (P1, P2, P3…) tiene MÚLTIPLES LÍNEAS con distintos precios:
  pe_p* = Σ(kwh_i × precio_i) / Σ(kwh_i)  [media ponderada por kWh]
  consumo_p* = Σ(kwh_i)  [suma de todos los sub-tramos]
  Obs: "pe_p* media ponderada de N sub-tramos".
  Ejemplo: P1 con (79.76 kWh × 0.092539) + (64.24 kWh × 0.097553) → pe_p1 = 13.65/144 = 0.094792; consumo_p1 = 144.

CASO B — si TODO el período de facturación está dividido temporalmente (cambio de precios a mitad del período):
  Las líneas NO son del mismo período P*, sino del mismo tramo temporal con distintos P* internos.
  Señal: el primer grupo de líneas cubre todos los P* (P1, P2, P3) para el tramo 1; el segundo grupo para el tramo 2.
  En este caso: extraer pe_p1 = precio tramo 1, consumo_p1_kwh = kWh tramo 1 (el total del tramo, NO punta/llano/valle).
              pe_p2 = precio tramo 2, consumo_p2_kwh = kWh tramo 2.
  Obs: "pe_p1/pe_p2 = precios de tramos temporales (cambio DD/MM/YYYY), no períodos tarifarios P1/P2".

COHERENCIA pe_p* / consumo_p*:
  Si consumo_pN tiene valor → pe_pN NUNCA puede ser null (y viceversa).
  Excepción: PRECIO ÚNICO → pe_p2..p6 = null Y consumo_p2..p6 = null.

ZEROS vs NULL:
  Períodos que EXISTEN en la tarifa pero tuvieron 0 kWh → pe_p* = 0.0, consumo_p* = 0.0.
  Períodos que NO EXISTEN en la tarifa → pe_p* = null, consumo_p* = null.

imp_termino_energia_eur: usar "termino_energia.total_bruto" (BRUTO, incluyendo reactiva si la factura la agrupa en ese total). NUNCA el valor neto después de descuentos.

Devuelve ÚNICAMENTE este JSON:
{
  "pe_p1": <float o null>, "pe_p2": <float o null>, "pe_p3": <float o null>,
  "pe_p4": <float o null>, "pe_p5": <float o null>, "pe_p6": <float o null>,
  "consumo_p1_kwh": <float o null>, "consumo_p2_kwh": <float o null>, "consumo_p3_kwh": <float o null>,
  "consumo_p4_kwh": <float o null>, "consumo_p5_kwh": <float o null>, "consumo_p6_kwh": <float o null>,
  "imp_termino_energia_eur": <float o null>,
  "observacion": [<string>]
}"""


def map_energia(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/mappers/energia.py
git commit -m "feat: add energia mapper (pe_p*, consumo_p*, CASO A/B/PRECIO ÚNICO)"
```

---

## Task 5: Cargas Mapper (exceso + reactiva classification)

**Files:**
- Create: `api/claude/mappers/cargas.py`

Returns: whether `exceso_potencia` and `coste_energia_reactiva` are inside or outside their respective `imp_termino_*`.

- [ ] **Step 1: Create `api/claude/mappers/cargas.py`**

```python
# api/claude/mappers/cargas.py
# Determines if exceso_potencia and coste_energia_reactiva are INSIDE or OUTSIDE
# their respective imp_termino_* values (to avoid double-counting in cuadre).

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que clasifica dos cargos específicos de una factura eléctrica española.

TAREA: Determinar si el exceso de potencia y la energía reactiva ya están DENTRO de los totales principales o son líneas SEPARADAS.

REGLA EXCESO DE POTENCIA:
  Verificar: ¿termino_potencia.total_bruto ya incluye el exceso?
  Si "exceso_potencia.importe" + las líneas de potencia base = total_bruto → DENTRO (inside=true).
  Si el exceso aparece como línea completamente fuera del bloque de potencia → FUERA (inside=false).
  Cuando inside=true → exceso_potencia_importe en costes debe ser null (para no duplicar en cuadre).
  Cuando inside=false → exceso_potencia_importe en costes tiene valor y SE SUMA en cuadre.

REGLA ENERGÍA REACTIVA:
  Verificar: ¿termino_energia.total_bruto incluye la reactiva?
  Si "reactiva.importe" + total_activa_bruto ≈ total_bruto → reactiva DENTRO (inside=true).
  Si total_bruto = solo energía activa y reactiva es línea aparte → FUERA (inside=false).
  Cuando inside=true → coste_energia_reactiva en costes tiene su valor informativo PERO no se suma en cuadre.
  Cuando inside=false → se suma en cuadre.

Devuelve ÚNICAMENTE este JSON:
{
  "exceso_potencia_importe": <float o null — null si inside=true, valor si inside=false>,
  "exceso_inside_potencia": <true|false>,
  "coste_energia_reactiva": <float o null — siempre el importe si existe, null si no hay reactiva>,
  "reactiva_inside_energia": <true|false>,
  "observacion": [<string — explicación de cada decisión>]
}"""


def map_cargas(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/mappers/cargas.py
git commit -m "feat: add cargas mapper (exceso/reactiva inside-or-outside classification)"
```

---

## Task 6: Costes Mapper

**Files:**
- Create: `api/claude/mappers/costes.py`

Returns: `bono_social_precio_dia`, `bono_social_importe`, `costes_adicionales` dict, `creditos` dict, `precio_final_energia_activa`, `observacion`.

- [ ] **Step 1: Create `api/claude/mappers/costes.py`**

```python
# api/claude/mappers/costes.py
# Maps bono social, additional services, and discounts.
# Rules: alquiler NEVER in costes; "Varios" is a section header; discounts go in creditos.

from api.claude.mappers.base import call_haiku

_SYSTEM = """Eres un asistente que clasifica los costes adicionales y créditos de una factura eléctrica española.

REGLAS:

BONO SOCIAL:
  bono_social_importe: suma total del período (sumar todos los tramos si hay varios).
  bono_social_precio_dia: si hay un único tramo → precio_dia de ese tramo.
    Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
  Si no hay bono social → ambos null.

ALQUILER DE EQUIPOS:
  NUNCA incluir en costes_adicionales. El alquiler ya está en imp_alquiler_eur / importes_totalizados.

SECCIÓN "VARIOS" EN FACTURAS PVPC (Energía XXI, etc.):
  "Varios" es un ENCABEZADO DE SECCIÓN, no un servicio.
  Los conceptos dentro de esa sección (ej: Financiación Bono Social) ya tienen su campo nombrado.
  NUNCA crear clave "varios_importe" en costes_adicionales.

SERVICIOS ADICIONALES (Pack Hogar, Asistente Smart Hogar, Servicio FACILITA, etc.):
  Si el servicio tiene un descuento asociado:
    costes_adicionales["<nombre>_importe"] = importe BRUTO (antes del descuento).
    creditos["descuento_<nombre>"] = importe del descuento (negativo).
  Si no tiene descuento: solo en costes_adicionales.
  Clave: usar snake_case del nombre descriptivo + "_importe" (ej: "asistente_smart_hogar_importe").

DESCUENTOS SOBRE CONSUMO (ej: Descuento 15%):
  Van en creditos con valor negativo.
  Clave descriptiva snake_case (ej: "descuento_consumo_15": -6.74).

PRECIO FINAL ENERGÍA ACTIVA:
  precio_final_energia_activa: usar "termino_energia.total_activa_bruto" (BRUTO, antes de descuentos sobre consumo).
  Si hay reactiva, NO incluirla en precio_final_energia_activa (eso va en coste_energia_reactiva en importes_totalizados).

Devuelve ÚNICAMENTE este JSON:
{
  "bono_social_precio_dia": <float o null>,
  "bono_social_importe": <float o null>,
  "precio_final_energia_activa": <float o null>,
  "costes_adicionales": {
    "<nombre_servicio>_importe": <float>
  },
  "creditos": {
    "<nombre_descuento>": <float negativo>
  },
  "observacion": [<string>]
}
Nota: "costes_adicionales" y "creditos" pueden ser {} si no hay ninguno."""


def map_costes(raw: dict) -> dict:
    return call_haiku(_SYSTEM, raw)
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/mappers/costes.py
git commit -m "feat: add costes mapper (bono social, servicios adicionales, creditos)"
```

---

## Task 7: Pipeline Orchestrator

**Files:**
- Create: `api/claude/pipeline.py`

- [ ] **Step 1: Create `api/claude/pipeline.py`**

```python
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
        temperature=0,
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
    importe_factura = meta.get("importe_factura")

    # Potencias contratadas
    pc = {p["periodo"]: p["kw"] for p in raw.get("potencias_contratadas", [])}

    # Impuestos
    imp = raw.get("impuestos", {})
    iee = imp.get("iee", {})
    imp_ele = iee.get("porcentaje")
    iva_lines = imp.get("iva", [])
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
            if key == "exceso_potencia_importe":
                continue  # always null when inside; if not null, it's separate → sum it
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
            if key == "compensacion_excedentes_importe":
                continue
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

    print("  [Stage 2] Ejecutando mappers en paralelo (haiku × 4)...")
    mapped = _run_mappers(raw)

    print("  [Stage 3] Ensamblando ExtractionResponseAI...")
    result = _assemble(raw, mapped)

    ok = result.margen_de_error is not None and result.margen_de_error <= 5.0
    icon = "✅" if ok else "⚠️ "
    print(f"  {icon} Margen de error: {result.margen_de_error}%")
    print(f"  CUPS: {result.cups}")
    print(f"{'='*70}\n")
    return result
```

- [ ] **Step 2: Commit**

```bash
git add api/claude/pipeline.py
git commit -m "feat: add multi-agent pipeline orchestrator (opus + 4x haiku + python assembly)"
```

---

## Task 8: Wire Pipeline into extractor.py

**Files:**
- Modify: `api/claude/extractor.py`

The existing `extract_with_claude(pdf_bytes)` is the entry point for all routes. Replace its body to delegate to `run_pipeline`. Keep all helper functions (`_sanitize_json`, `_parse_json_from_text`, `_build_response`) in place — they may still be useful.

- [ ] **Step 1: Add pipeline import and replace function body in `api/claude/extractor.py`**

At the top of `api/claude/extractor.py`, add the import:

```python
from api.claude.pipeline import run_pipeline
```

Replace the body of `extract_with_claude` (keep the function signature and docstring):

```python
def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF al pipeline multi-agente y devuelve los datos estructurados."""
    return run_pipeline(pdf_bytes)
```

The full resulting `extract_with_claude` function:

```python
def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF al pipeline multi-agente y devuelve los datos estructurados."""
    return run_pipeline(pdf_bytes)
```

All other functions in `extractor.py` (`_sanitize_json`, `_parse_json_from_text`, `_build_response`) remain untouched.

- [ ] **Step 2: Restart the server**

```bash
uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 3: Commit**

```bash
git add api/claude/extractor.py
git commit -m "feat: wire multi-agent pipeline into extract_with_claude entry point"
```

---

## Task 9: Manual Testing

No automated tests exist in this project. Testing is manual via Swagger UI at `http://localhost:8000/docs`.

- [ ] **Step 1: Test with Quantium 3.0TD invoice**

Upload via `POST /facturas/extraer-ai`. Expected:
- `exceso_potencia_importe: null` in `otros.costes` (inside imp_termino_potencia_eur)
- `coste_energia_reactiva: 55.08` in `otros.costes`
- `margen_de_error: 0.0`
- `pp_p1..pp_p6` correctly converted from €/kW·año ÷ 365

- [ ] **Step 2: Test with Iberdrola 2.0TD invoice (2 temporal tramos)**

Expected:
- `pe_p1 = 0.17347`, `pe_p2 = 0.18051` (CASO B — temporal tramos)
- `consumo_p1_kwh = 76`, `consumo_p2_kwh = 176` (NOT 47/57/148 punta/llano/valle)
- `margen_de_error` ≤ 5%

- [ ] **Step 3: Test with Energía XXI PVPC invoice**

Expected:
- `pe_p1..pe_p3` as weighted averages of peajes (CASO A)
- No `varios_importe` in `otros.costes`
- `bono_social_importe = 0.54` in `otros.costes`
- `margen_de_error: 0.0`

- [ ] **Step 4: Test same invoice 3× and verify consistent outputs**

The parallel haiku mappers with focused prompts should produce identical results across runs for the same invoice.

---

## Self-Review

**Spec coverage:**
- ✅ Powerful model does raw extraction
- ✅ Cheap subagents map values to fields
- ✅ Potencia: conversion formulas + CASO A/B
- ✅ Energía: PRECIO ÚNICO + CASO A + CASO B + coherence rule
- ✅ Cargas: exceso_potencia null when inside imp_termino_potencia_eur
- ✅ Cargas: reactiva_inside_energia verification
- ✅ Costes: alquiler never in costes dict
- ✅ Costes: "Varios" section not creating varios_importe
- ✅ Costes: precio_final_energia_activa always gross
- ✅ margen_de_error calculated in Python with correct exclusions
- ✅ Public interface (`extract_with_claude`) unchanged — no route changes needed

**No placeholders found.**

**Type consistency:**
- `map_potencia`, `map_energia`, `map_cargas`, `map_costes` all take `raw: dict` and return `dict` ✅
- `run_pipeline` calls all four and passes results to `_assemble` ✅
- `_assemble` reads specific keys from each mapper output — keys match what each mapper prompt specifies ✅
