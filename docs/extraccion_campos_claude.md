# Disglose: Extracción de campos por Claude API

> Documento técnico que explica, campo a campo, cómo Claude extrae y calcula cada valor
> que aparece en el payload de `/facturas/extraer`.
>
> **Fuente del prompt:** `_PREAMBLE` (api/claude/prompts.py) + `.claude/skills/leer-factura/prompt_lectura_factura.md`

---

## Arquitectura del prompt

Claude recibe **dos capas de instrucciones**:

| Capa | Origen | Contenido |
|---|---|---|
| `_PREAMBLE` | `api/claude/prompts.py` | Reglas de conversión de unidades, validación de cuadre, formato de `otros` |
| Prompt extenso | `.claude/skills/leer-factura/prompt_lectura_factura.md` | Estructura de la factura, bloques 1–20, reglas R1–R13, schema JSON |

El prompt se carga **una sola vez** al arrancar el servidor (para activar prompt caching de Anthropic).
Claude recibe el PDF completo en base64 y devuelve un único bloque ```json```.

---

## Campos de identificación

### `cups`
- **Fuente en PDF:** bloque de datos técnicos, línea "CUPS"
- **Conversión:** se eliminan espacios (`ES 0021 0000 ...` → `ES0021000...`)
- **Regla R5:** en el JSON interno se guardan dos versiones (con y sin espacios); el endpoint solo expone la versión sin espacios

### `comercializadora`
- **Fuente:** nombre del emisor (cabecera o pie de página)
- **Conversión:** ninguna — texto literal tal como aparece

### `distribuidora`
- **Fuente:** campo "Empresa distribuidora" en datos técnicos del contrato
- **Conversión:** ninguna

### `tarifa_acceso`
- **Fuente:** campo ATR / Peaje de acceso
- **Ejemplos:** `2.0TD`, `3.0TD`, `6.1TD`
- **Conversión:** ninguna

### `periodo_inicio` / `periodo_fin`
- **Fuente:** "Período de facturación" en cabecera
- **Conversión:** mantenido como string `DD/MM/YYYY` (no se convierte a ISO)

### `dias_facturados`
- **Fuente:** número de días del período, indicado explícitamente en la factura
- **Conversión:** guardado como string, no como entero (`"31"`, `"30"`)

### `importe_factura`
- **Fuente:** campo "TOTAL factura" o equivalente
- **Conversión:** decimal con punto (`118.60`)

---

## Precios de potencia — `pp_p1` .. `pp_p6`

> **Campo crítico: siempre se devuelve en €/kW·día**

Claude detecta la unidad en que está expresado el precio y convierte:

### Caso A — Factura en €/kW·día (la mayoría)
La línea de potencia ya aparece en la unidad correcta:
```
Punta: 6,9 kW × 31 días × 0,073783 €/kW·día = 15,79 €
```
→ `pp_p1 = 0.073783` (sin conversión)

### Caso B — Factura en €/kW·año (ej: algunas Iberdrola, Endesa)
```
Precio potencia punta: 26,930550 €/kW·año
```
→ `pp_p1 = 26.930550 / 365 = 0.073783 €/kW·día`

### Caso C — Factura en €/kW·mes (ej: PepeEnergy)
```
Precio potencia P1: 2,24450 €/kW·mes  — período 31 días
```
→ `pp_p1 = 2.24450 / 31 = 0.072403 €/kW·día`

El divisor es el **número de días facturados del período**, no 30 ni 365.

### Caso D — Sub-períodos (ej: Energía XXI)
Algunas facturas dividen el mismo período tarifario en dos tramos con precios diferentes:
```
Sub-período 1: 0,044800 €/kW·día × 15 días
Sub-período 2: 0,051200 €/kW·día × 16 días
```
→ Media ponderada: `(0.044800×15 + 0.051200×16) / (15+16) = 0.048129 €/kW·día`

**Si la factura no indica la unidad** → se asume €/kW·año y se divide entre 365.

---

## Precios de energía — `pe_p1` .. `pe_p6`

> **No hay conversión de unidades. Se extrae directamente en €/kWh.**

Claude busca líneas con el patrón:
```
Energía consumida: X kWh × Y €/kWh = Z €
```
o variantes según comercializadora:
```
P1 – Punta: 107 kWh × 0,142855 €/kWh = 15,29 €
P2 – Llano: 142 kWh × 0,142855 €/kWh = 20,29 €
P3 – Valle: 510 kWh × 0,110000 €/kWh = 56,10 €
```

→ `pe_p1 = 0.142855`, `pe_p2 = 0.142855`, `pe_p3 = 0.110000`

**Reglas de nulidad:**
- Si un período no tiene consumo ni precio en la factura → `null` (no `0.0`)
- Factura con precio único (ej: Repsol) → solo `pe_p1` relleno, `pe_p2`..`pe_p6` = `null`
- 2.0TD típica → `pe_p1`, `pe_p2`, `pe_p3`; el resto `null`

---

## Potencias contratadas — `pot_p1_kw` .. `pot_p6_kw`

- **Fuente:** tabla de potencias contratadas del contrato
- **Conversión:** ninguna, en kW directamente
- **Ejemplo:** `Potencia contratada: P1 = 6,9 kW | P2 = 6,9 kW`
  → `pot_p1_kw = 6.9`, `pot_p2_kw = 6.9`
- Períodos sin contratar (tarifa 2.0TD solo tiene P1 y P2) → `null`

---

## Consumos por franja — `consumo_p1_kwh` .. `consumo_p6_kwh`

- **Fuente:** bloque "Sus consumos desagregados han sido..."
- **Conversión:** ninguna, en kWh directamente
- **⚠️ ATENCIÓN — Regla R12:** estos son los consumos **informativos/desagregados**,
  NO los valores facturados. En facturas con autoconsumo pueden ser distintos.
- Los valores facturados (los que se usan para calcular el importe) están en
  `imp_termino_energia_eur` via la línea `X kWh × Y €/kWh = Z €`

---

## Impuestos

### `imp_ele` — Impuesto sobre la Electricidad (formato porcentaje)
- **Fuente:** línea "Impuesto sobre electricidad X % s/base"
- **Conversión:** número decimal (no string con `%`)
- **Ejemplo:** `5,11269632 %` → `imp_ele = 5.11269632`
- **Nulo cuando:** la factura usa formato €/kWh (post RDL 7/2026)

### `imp_ele_eur_kwh` — IEE en €/kWh (post RDL 7/2026)
- **Fuente:** línea "Impuesto sobre electricidad X €/kWh"
- **Conversión:** ninguna
- **Nulo cuando:** la factura usa formato porcentaje (pre-2026)

*Solo uno de los dos campos estará relleno en cada factura.*

### `iva`
- **Fuente:** porcentaje de IVA aplicado
- **Tipo:** entero (`21`, `10`)
- **Nota:** si hay IVA split (RDL 8/2023), `iva` = tipo general; el reducido va en `otros`

---

## Alquiler de contador — `alq_eq_dia`

- **Fuente:** línea "Alquiler equipos de medida N días × X €/día = Z €"
- **Lo que Claude extrae:** el precio unitario `X` en €/día
- **Ejemplo:**
  ```
  Alquiler equipos medida: 31 días × 0,020645 €/día = 0,64 €
  ```
  → `alq_eq_dia = 0.020645`

---

## Bono social — `bono_social`

- **Fuente:** línea "Financiación bono social fijo N días × X €/día = Z €"
- **Lo que Claude extrae:** el importe total `Z` en €
- **Ejemplo:** `31 días × 0,004839 €/día = 0,15 €` → `bono_social = 0.15`
- **Nulo cuando:** no aparece en la factura (la mayoría de contratos de mercado libre)

---

## Importes en € — líneas de la factura

Estos campos son los **subtotales en € de cada bloque**, extraídos directamente de la factura
(no calculados por Claude desde precios unitarios × cantidades).

| Campo | Qué es | Ejemplo |
|---|---|---|
| `imp_termino_potencia_eur` | Total término de potencia | `24.87 €` |
| `imp_termino_energia_eur` | Total energía consumida (neto, tras descuentos) | `104.09 €` |
| `imp_impuesto_electrico_eur` | Importe IEE en € | `4.56 €` |
| `imp_alquiler_eur` | Importe alquiler contador en € | `0.64 €` |
| `imp_iva_eur` | Importe total de IVA en € | `20.58 €` |

**Por qué existen:** permiten hacer la reconciliación contable sin recalcular desde los
precios unitarios (que pueden tener pequeños errores de redondeo).

---

## Descuentos — `descuentos`

- **Fuente:** líneas de descuento dentro del bloque ENERGÍA
- **Formato:** dict `{ "nombre del descuento": importe_negativo }`
- **Ejemplo:**
  ```
  Descuento 10% sobre consumo: -10,41 €
  ```
  → `descuentos = {"Descuento 10% sobre consumo": -10.41}`
- Los valores son **negativos** (reducen el importe)

---

## Otros conceptos — `otros`

Cualquier concepto de la factura que no tiene campo dedicado en el modelo:
- Packs comerciales (Pack Iberdrola Hogar, Asistencia PYMES, etc.)
- Descuentos sobre packs
- IVA reducido adicional
- Servicios especiales

**Formato:** dict `{ "nombre_concepto": importe_eur }`

Claude devuelve `otros` como **string JSON** en la respuesta; el backend lo convierte a dict.

---

## Validación de cuadre — `margen_de_error`

Claude ejecuta esta validación **antes de devolver el JSON** (instrucción en `_PREAMBLE`):

### Fórmula
```
suma = imp_termino_potencia_eur
     + imp_termino_energia_eur
     + imp_impuesto_electrico_eur
     + imp_alquiler_eur
     + imp_iva_eur
     - bono_social          (si existe, es positivo pero resta del total neto)
     - sum(descuentos)      (valores ya negativos)
     + sum(otros)           (pueden ser positivos o negativos)

margen_de_error = |suma - importe_factura| / importe_factura × 100
```

### Lógica de auto-corrección
1. Claude extrae todos los campos
2. Calcula `margen_de_error`
3. Si `margen_de_error > 5 %` → relée la factura, identifica el campo erróneo y lo corrige
4. Repite hasta que `margen_de_error ≤ 5 %` o no pueda mejorar más
5. Devuelve siempre el valor final en el campo `margen_de_error`

**Rango aceptable:** 0.0 – 5.0 %
**Causas comunes de error > 0 %:** redondeos en los importes, descuentos no capturados, IVA split

---

## Campos que Claude NO calcula

Los siguientes campos **no son calculados por Claude** — vienen de otras fuentes:

| Campo | Fuente real |
|---|---|
| `tarifa_acceso` | Extraído del PDF (no calculado) |
| `distribuidora` | Extraído del PDF |
| `validacion_cuadre` | Calculado por el servidor (actualmente siempre `null`) |
| `session_id` | Generado por el servidor tras crear la sesión |
| `api_ok`, `api_error`, `fichero_json` | Metadatos del servidor (excluidos del response) |

---

## Flujo completo: de PDF a payload

```
PDF (base64)
    │
    ▼
Claude lee las N páginas completas
    │
    ▼
Extrae campos en bruto (texto literal del PDF)
    │
    ├─ pp_p1..p6: detecta unidad → convierte a €/kW·día
    ├─ pe_p1..p6: extrae directo en €/kWh (sin conversión)
    ├─ imp_ele: extrae como % o null (si formato €/kWh)
    ├─ imp_ele_eur_kwh: extrae si formato post-2026
    ├─ importes en €: lee subtotales de cada bloque
    └─ otros: captura conceptos no estándar como dict
    │
    ▼
Validación de cuadre (margen_de_error)
    │ Si > 5% → revisión y corrección
    │
    ▼
Devuelve ```json``` con todos los campos
    │
    ▼
Backend (extractor.py)
    ├─ Parsea el JSON
    ├─ Filtra claves desconocidas
    ├─ Convierte 'otros'/'descuentos' de string → dict
    └─ Construye ExtractionResponseAI
    │
    ▼
facturas.py
    ├─ Busca dealId/mpklogId en Zoho CRM
    ├─ Crea sesión (_build_factura_payload → session_payload)
    ├─ Guarda JSON local en resultados/
    └─ Sube 5 ficheros a Zoho WorkDrive (fire-and-forget)
    │
    ▼
Response: ExtractionResponseAI (con session_id relleno)
```

---

## Tabla resumen de conversiones

| Campo | Unidad en PDF | Unidad en payload | Conversión |
|---|---|---|---|
| `pp_p1..p6` | €/kW·año, €/kW·mes o €/kW·día | €/kW·día | ÷365 o ÷dias_facturados |
| `pe_p1..p6` | €/kWh | €/kWh | Ninguna |
| `imp_ele` | % | % (float) | Ninguna |
| `imp_ele_eur_kwh` | €/kWh | €/kWh | Ninguna |
| `iva` | % | % (int) | Ninguna |
| `alq_eq_dia` | €/día | €/día | Ninguna |
| `bono_social` | €/día × dias | € (importe total) | Claude extrae el importe final |
| `consumo_pN_kwh` | kWh | kWh | Ninguna |
| `pot_pN_kw` | kW | kW | Ninguna |
| `importe_factura` | € | € | Ninguna |
