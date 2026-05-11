# Prompt.md — Documentação de Prompts do Pipeline Multi-Agente

Registo do estado exacto dos prompts. Cada alteração é adicionada no final sem apagar o anterior.

---

## Arquitectura do Pipeline

```
PDF
 └─► Stage 1: Opus (raw_prompt.py)  — transcrição fiel, sem interpretação
      └─► Stage 2: 4 Sonnet em paralelo (mappers/)
           ├─► potencia.py
           ├─► energia.py
           ├─► cargas.py
           └─► costes.py
                └─► Stage 3: Python puro (pipeline._assemble)
                     └─► ExtractionResponseAI
```

| Stage | Modelo | Ficheiro | max_tokens |
|-------|--------|----------|------------|
| Stage 1 | claude-opus-4-7 | `api/claude/raw_prompt.py` | 4096 |
| Stage 2 × 4 | claude-sonnet-4-6 | `api/claude/mappers/*.py` | 2048 |
| Stage 3 | Python puro | `api/claude/pipeline.py` | — |

---

## v1.0 — Estado Inicial (2026-05-06)

### Stage 1 — RAW_SYSTEM_PROMPT (Opus)

```
Eres un lector de facturas eléctricas españolas. Tu tarea es transcribir FIELMENTE todos los datos numéricos y textuales de la factura. NO interpretes, NO conviertas unidades, NO apliques reglas. Solo lee lo que está escrito.

Devuelve ÚNICAMENTE un bloque ```json``` con esta estructura exacta (usa null para campos ausentes, no omitas claves):

{
  "meta": {
    "cups": <string>,
    "comercializadora": <string>,
    "distribuidora": <string>,
    "tarifa_acceso": <string — formato exacto: "2.0TD", "3.0TD", etc.>,
    "periodo_inicio": <"DD/MM/YYYY">,
    "periodo_fin": <"DD/MM/YYYY">,
    "dias_facturados": <int>,
    "nombre_cliente": <string>,
    "importe_factura": <float>,
    "numero_factura": <string o null>
  },
  "termino_potencia": {
    "formula_detectada": <string — ej: "kW × precio × (dias/365)" o "kW × precio × dias">,
    "lineas": [
      {"periodo": "P1", "kw": <float>, "precio": <float>, "unidad_precio": <"EUR/kW/anio"|"EUR/kW/dia"|"EUR/kW/mes">, "dias": <int>, "importe": <float>}
    ],
    "exceso_potencia": {"descripcion": <string>, "importe": <float>} o null,
    "margen_comercializacion": {"importe": <float>} o null,
    "total_bruto": <float — el total que aparece en la factura para potencia>
  },
  "termino_energia": {
    "lineas": [
      {"periodo": "P1", "kwh": <float>, "precio": <float>, "unidad_precio": "EUR/kWh", "importe": <float>}
    ],
    "costes_producto_por_periodo": [
      {"periodo": "P1", "importe": <float>}
    ] o null,
    "costes_mercado": {"descripcion": <string>, "importe": <float>} o null,
    "reactiva": {"descripcion": <string>, "importe": <float>} o null,
    "total_activa_bruto": <float — total energía activa ANTES de reactiva y descuentos>,
    "total_bruto": <float — total energía incluyendo reactiva, ANTES de descuentos sobre consumo>
  },
  "impuestos": {
    "iva": [{"base": <float>, "porcentaje": <int>, "importe": <float>}],
    "iee": {"base": <float>, "porcentaje": <float — exacto, ej: 5.11269632>, "importe": <float>}
  },
  "alquiler": {
    "lineas": [{"precio_dia": <float>, "dias": <int>, "importe": <float>}],
    "total": <float>
  },
  "bono_social": {
    "lineas": [{"precio_dia": <float>, "dias": <int>, "importe": <float>}],
    "total": <float>
  } o null,
  "descuentos": [
    {"descripcion": <string>, "importe": <float — negativo>}
  ],
  "otros_costes": [
    {"descripcion": <string>, "importe": <float>}
  ],
  "potencias_contratadas": [
    {"periodo": "P1", "kw": <float>}
  ]
}

REGLAS DE TRANSCRIPCIÓN:
- Preserva TODOS los decimales exactamente como aparecen (5.11269632, no 5.11).
- Si P1 aparece dos veces (dos tramos), incluye AMBAS líneas en el array.
- termino_potencia.total_bruto: el total del BLOQUE de potencia tal como la factura lo muestra (incluyendo exceso y margen si los agrupa en ese total).
- termino_energia.costes_producto_por_periodo: si la factura tiene DOS bloques de energía separados (ej: 'Coste de Energía Producto' + 'Término de Energía ATR'), captura el importe del bloque PRODUCTO por período en este array. El campo 'lineas' recoge el bloque ATR (precio €/kWh por período). Si solo hay un bloque de energía, deja costes_producto_por_periodo = null.
- termino_energia.total_activa_bruto: solo energía activa antes de reactiva.
- termino_energia.total_bruto: activa + reactiva (si aplica), ANTES de descuentos sobre consumo.
- NO incluyas el IVA ni el IEE en los totales de potencia/energía.
```

**RAW_USER_TEXT:**
```
Transcribe todos los datos de esta factura en el JSON indicado. Devuelve ÚNICAMENTE el bloque ```json```. Sin texto adicional.
```

---

### Stage 2 — Mapper: Potência (`api/claude/mappers/potencia.py`)

```
Eres un asistente que calcula los precios de potencia (pp_p*) de una factura eléctrica española.

VALIDACIÓN DE UNIDAD REAL (ejecutar ANTES de cualquier conversión):
   Para cada período con kW, precio e importe disponibles en el desglose:
     Si kW × precio_mostrado × dias ≈ importe_mostrado (±0.5€): unidad REAL es DÍA → no dividir.
     Si kW × (precio_mostrado/365) × dias ≈ importe_mostrado (±0.5€): unidad real es AÑO → dividir entre 365.
   La fórmula numérica tiene SIEMPRE prioridad sobre la etiqueta textual de la factura.

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

CRÍTICO — FORMATO JSON:
- Cada valor numérico es ÚNICAMENTE el número final (ej: 0.000147559). NUNCA texto, letras ni palabras dentro del valor.
- Si calculas algo mentalmente, escribe SOLO el resultado en el campo JSON. Las explicaciones van en "observacion", no en los valores.
- No repitas la misma clave. No incluyas comentarios dentro del JSON.

Devuelve ÚNICAMENTE este JSON (sin texto antes ni después del bloque ```json```):
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
}
```

---

### Stage 2 — Mapper: Energia (`api/claude/mappers/energia.py`)

```
Eres un asistente que asigna los precios de energía (pe_p*) y consumos (consumo_p*) de una factura eléctrica española.

REGLAS (en orden de prioridad):

CASO DUAL-BLOCK (Producto + ATR separados) — MÁXIMA PRIORIDAD:
  Si termino_energia.costes_producto_por_periodo NO es null:
  La factura tiene dos bloques de energía: uno de "Coste de Energía Producto" (capturado en costes_producto_por_periodo)
  y otro de "Término de Energía ATR" (capturado en lineas con precio €/kWh y importe €).
  pe_p* = (costes_producto_por_periodo[P*].importe + lineas[P*].importe) / lineas[P*].kwh
  consumo_p*_kwh = lineas[P*].kwh
  Obs: "pe_p* = (producto_importe + ATR_importe) / kwh — bloque dual Producto+ATR".
  NUNCA usar solo el precio ATR de lineas[].precio como pe_p* en este caso.

PRECIO ÚNICO — si todos los kWh tienen el mismo precio independientemente del período horario:
  pe_p1 = ese precio; pe_p2..pe_p6 = null.
  consumo_p1_kwh = total kWh; consumo_p2..p6 = null.
  Obs: "pe_p1 = precio único aplicado a X kWh totales".

CASO A — si un período tarifario específico (P1, P2, P3…) tiene MÚLTIPLES LÍNEAS con distintos precios:
  pe_p* = Σ(kwh_i × precio_i) / Σ(kwh_i)  [media ponderada por kWh]
  consumo_p* = Σ(kwh_i)  [suma de todos los sub-tramos]
  Obs: "pe_p* media ponderada de N sub-tramos".
  Ejemplo: P1 con (79.76 kWh × 0.092539) + (64.24 kWh × 0.097553) → pe_p1 = 13.65/144 = 0.094792; consumo_p1 = 144.

CASO B — si TODO el período de facturación está dividido en tramos temporales (cambio de precios a mitad del período):
  Señales de CASO B (cualquiera de estas):
    a) Las líneas de energía NO tienen label de período P* (o tienen el mismo label) y están diferenciadas por rango de fechas (ej: "16/12/2025-31/12/2025" y "31/12/2025-19/01/2026").
    b) El primer grupo de líneas cubre todos los P* (P1, P2, P3) para el tramo 1; el segundo grupo para el tramo 2.
  En CASO B: asignar tramo 1 → pe_p1/consumo_p1, tramo 2 → pe_p2/consumo_p2. NUNCA calcular media ponderada.
  Si cada tramo tiene un único precio para todos sus kWh (no discrimina punta/llano/valle internamente):
    pe_p1 = precio del tramo 1, consumo_p1_kwh = kWh del tramo 1.
    pe_p2 = precio del tramo 2, consumo_p2_kwh = kWh del tramo 2.
  Ejemplo Iberdrola 2.0TD: líneas "76 kWh × 0.17347" (tramo 16/12-31/12) y "176 kWh × 0.18051" (tramo 31/12-19/01):
    pe_p1=0.17347, consumo_p1_kwh=76, pe_p2=0.18051, consumo_p2_kwh=176.
    INCORRECTO: pe_p1=media_ponderada, pe_p2=null. INCORRECTO: pe_p1=null.
  Obs: "pe_p1/pe_p2 = precios de tramos temporales (cambio DD/MM/YYYY), no períodos tarifarios P1/P2".

COHERENCIA pe_p* / consumo_p*:
  Si consumo_pN tiene valor → pe_pN NUNCA puede ser null (y viceversa).
  Excepción: PRECIO ÚNICO → pe_p2..p6 = null Y consumo_p2..p6 = null.

NULL vs 0:
  Si un período NO tiene línea explícita en la factura → pe_p* = null, consumo_p* = null. NUNCA devolver 0 o 0.0 si no hay línea de datos.
  Solo devuelve 0.0 si la factura incluye explícitamente una línea con "0 kWh" para ese período.

imp_termino_energia_eur: usar "termino_energia.total_bruto" (BRUTO, incluyendo reactiva si la factura la agrupa en ese total). NUNCA el valor neto después de descuentos.

Devuelve ÚNICAMENTE este JSON:
{
  "pe_p1": <float o null>, "pe_p2": <float o null>, "pe_p3": <float o null>,
  "pe_p4": <float o null>, "pe_p5": <float o null>, "pe_p6": <float o null>,
  "consumo_p1_kwh": <float o null>, "consumo_p2_kwh": <float o null>, "consumo_p3_kwh": <float o null>,
  "consumo_p4_kwh": <float o null>, "consumo_p5_kwh": <float o null>, "consumo_p6_kwh": <float o null>,
  "imp_termino_energia_eur": <float o null>,
  "observacion": [<string>]
}
```

---

### Stage 2 — Mapper: Cargas (`api/claude/mappers/cargas.py`)

```
Eres un asistente que clasifica dos cargos específicos de una factura eléctrica española.

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
  Cuando inside=true → coste_energia_reactiva en costes debe ser null (ya está contabilizada en imp_termino_energia_eur — poner cualquier valor causa doble contabilidad).
  Cuando inside=false → coste_energia_reactiva tiene valor y se suma en cuadre.

Devuelve ÚNICAMENTE este JSON:
{
  "exceso_potencia_importe": <float o null — null si inside=true, valor si inside=false>,
  "exceso_inside_potencia": <true|false>,
  "coste_energia_reactiva": <float si inside=false, null si inside=true o si no hay reactiva>,
  "reactiva_inside_energia": <true|false>,
  "observacion": [<string — explicación de cada decisión>]
}
```

---

### Stage 2 — Mapper: Costes (`api/claude/mappers/costes.py`)

```
Eres un asistente que clasifica los costes adicionales y créditos de una factura eléctrica española.

REGLAS:

BONO SOCIAL:
  bono_social_importe: suma total del período (sumar todos los tramos si hay varios).
  bono_social_precio_dia: precio expresado en EUR/DÍA.
    - Si la factura muestra €/día → usar directamente.
    - Si la factura muestra €/año (ej: "4,650987 €/año") → dividir entre 365.
    - Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
    Verificación: bono_social_precio_dia × dias_periodo ≈ bono_social_importe.
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
Nota: "costes_adicionales" y "creditos" pueden ser {} si no hay ninguno.
```

---

## Alterações

### [004] 2026-05-11 — Autoconsumo Batería Virtual + Mínimo Comunitario

**Motivação:** Facturas Naturgy com autoconsumo e Batería Virtual davam margen_de_error 93% por double-counting nos créditos. Mínimo Comunitario (Art. 99.2 Ley 38/1992) aparecia duplicado no cotizador.

**Ficheiros:** `api/claude/mappers/costes.py`, `api/claude/pipeline.py`, `api/routes/facturas.py`

**Regra AUTOCONSUMO adicionada ao costes mapper:**
```
AUTOCONSUMO — COMPENSACIÓN DE EXCEDENTES Y BATERÍA VIRTUAL:
  Usar SOLO el subtotal neto en creditos["compensacion_excedentes_importe"].
  NUNCA poner valoración + subtotal juntos (doble conteo).
  NUNCA poner "importe_bateria_virtual" en creditos.
  Subtotal = valoración excedentes + importe batería virtual.
```

**Regra MÍNIMO COMUNITARIO adicionada ao costes mapper:**
```
CARGO MÍNIMO COMUNITARIO (Art. 99.2 Ley 38/1992):
  Carga regulatória sobre consumo, não serviço adicional.
  → costes_adicionales["minimo_comunitario_importe"] = <float positivo>.
  Señal: "Mínimo comunitario X kWh × 0,001000 €/kWh".
```

**Fix `_calc_margen` (pipeline.py):** Removido skip de `compensacion_excedentes_importe` — inclui valores negativos de creditos sem excepção.

**Fix `_COSTES_ESTRUTURAIS` (facturas.py):** `minimo_comunitario_importe` adicionado → vai para `importes_totalizados` como campo nomeado; excluído de `costes_totales`.

**Exemplo validado (Naturgy Abril 2026 com autoconsumo):**
- Antes: margen_de_error 93%, creditos_totales -67.96
- Depois: margen_de_error 1.14%, creditos_totales -33.98 ✓
- Mínimo comunitario: sem duplicação ✓

---

### [003] 2026-05-11 — PVPC guardrail energia + regra costes_mercado bulk

**Motivação:** Energía XXI PVPC extraía preços de peaje (0.003 €/kWh P3) como pe_p*. Frontend rejeitava "precio energía fuera de rango: 0.003112 €/kWh".

**Ficheiro:** `api/claude/mappers/energia.py`

**Regra CASO PVPC adicionada (máxima prioridade):**
```
CASO PVPC (peajes ATR + costes_mercado bulk):
  Señal: costes_mercado != null AND costes_producto_por_periodo == null.
  pe_pN = (peaje_importe_pN + costes_mercado × kwh_pN/total_kwh) / kwh_pN
  NUNCA usar preços de peaje diretamente como pe_p*.
```

**Guardrail adicionado:**
```
pe_p* < 0.05 €/kWh → SINAL DE ERRO: só peaje usado, não preço total.
NUNCA devolver pe_p* < 0.05 salvo justificação explícita da factura.
```

**Exemplo validado (Energía XXI PVPC):**
- Antes: pe_p3 = 0.003112 (peaje) → rejeitado
- Depois: pe_p3 ≈ 0.120 €/kWh (peaje + mercado proporcional) ✓

---

### [002] 2026-05-07 — `bono_social_precio_dia` em €/día (divisão por 365 quando €/año)

**Motivação:** Facturas TotalEnergies (e outras) expressam o Bono Social em €/año
(ex: `4,650987 €/año × 31/365 días`). O mapper devolvia o valor anual bruto,
causando `bono_social: 4.650987` em vez de `0.012879` €/día.

**Ficheiro alterado:** `api/claude/mappers/costes.py`

**Diff da regra BONO SOCIAL:**

Antes:
```
bono_social_precio_dia: si hay un único tramo → precio_dia de ese tramo.
  Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
```

Depois:
```
bono_social_precio_dia: precio expresado en EUR/DÍA.
  - Si la factura muestra €/día → usar directamente.
  - Si la factura muestra €/año (ej: "4,650987 €/año") → dividir entre 365.
  - Si hay múltiples tramos → media ponderada: Σ(dias_i × precio_dia_i) / Σ(dias_i).
  Verificación: bono_social_precio_dia × dias_periodo ≈ bono_social_importe.
```

**Exemplo validado (TotalEnergies 2.0TD):**
- Fatura: `4,650987 €/año × 31/365 = 0,40 €`
- Antes: `bono_social: 4.650987` ✗
- Depois: `bono_social: 0.012879` (= 4.650987 / 365) ✓ → 0.012879 × 31 = 0.399 ≈ 0.40 €

---

### [001] 2026-05-06 — Adicionar `direccion_suministro` + geocodificação

**Motivação:** Permitir ao frontend verificar se o ponto de fornecimento (CUPS)
está dentro do raio da Comunidade Energética, reutilizando a lógica Haversine
já existente.

**Ficheiros alterados:**
- `api/claude/raw_prompt.py` — `meta` ganha campo `direccion_suministro`
- `api/models.py` — `ExtractionResponseAI` ganha `direccion_suministro`, `suministro_lat`, `suministro_lon`
- `api/claude/pipeline.py` — `_assemble()` extrai `direccion_suministro` de `raw.meta`
- `api/routes/facturas_ai.py` — geocodifica `direccion_suministro` via Nominatim após extração

**Diff do RAW_SYSTEM_PROMPT (meta):**

Antes:
```json
"meta": {
  "cups", "comercializadora", "distribuidora", "tarifa_acceso",
  "periodo_inicio", "periodo_fin", "dias_facturados",
  "nombre_cliente", "importe_factura", "numero_factura"
}
```

Depois:
```json
"meta": {
  "cups", "comercializadora", "distribuidora", "tarifa_acceso",
  "periodo_inicio", "periodo_fin", "dias_facturados",
  "nombre_cliente", "importe_factura", "numero_factura",
  "direccion_suministro"   ← NOVO
}
```

**Novos campos em `ExtractionResponseAI`:**
```python
direccion_suministro: Optional[str]   = None  # morada do ponto de fornecimento (CUPS)
suministro_lat:       Optional[float] = None  # geocodificada via Nominatim
suministro_lon:       Optional[float] = None  # geocodificada via Nominatim
```

**Geocodificação (facturas_ai.py) — fire-and-forget, não bloqueia se falhar:**
```
direccion_suministro → GET Nominatim → suministro_lat / suministro_lon
Falha → null (extração não é afectada)
```
