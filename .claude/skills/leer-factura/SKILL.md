---
name: leer-factura
description: Extrae datos exhaustivos de facturas eléctricas españolas (Iberdrola, Endesa, Naturgy, Repsol, TotalEnergies) en PDF y genera TRES archivos — un .md legible, un _ai.json estructurado completo (24 claves raíz anidadas), y un _processed.json plano compatible con el endpoint del backend (con validacion_cuadre, otros y error). Aplica las reglas R12 (valores facturados como única fuente de verdad) y R13 (reconciliación contable obligatoria). Se activa cuando el usuario pide leer, extraer, procesar, parsear o convertir una factura eléctrica / factura de electricidad / factura de la luz (.pdf) del mercado español.
---

# Leer Factura Eléctrica (España)

Skill para extraer **exhaustivamente** todos los datos de una factura eléctrica española en PDF y generar dos archivos sincronizados: `<stem>.md` (humano) + `<stem>.json` (máquina).

## Cuándo activarse

El usuario menciona alguna de estas palabras/frases referidas a un archivo PDF:

- "factura eléctrica", "factura de electricidad", "factura de la luz"
- "leer factura", "extraer factura", "procesar factura", "parsear factura"
- "convertir factura a json / md"
- Nombres de comercializadoras: Iberdrola, Endesa, Naturgy, Repsol, TotalEnergies, Holaluz, etc.
- El usuario adjunta un `.pdf` en una carpeta `facturas/`

## Workflow (ejecutar en este orden)

### Paso 1 — Leer el prompt completo

Antes de tocar el PDF, leer el archivo `prompt_lectura_factura.md` que acompaña esta skill. Contiene:

- Las 20 secciones que deben extraerse.
- Las 11 reglas R1–R11 de extracción.
- Las 6 validaciones de coherencia obligatorias.
- La plantilla exacta del Markdown (21 secciones).
- El esquema JSON completo (24 claves raíz).
- El checklist final de 16 puntos.

El prompt está en la misma carpeta: `.claude/skills/leer-factura/prompt_lectura_factura.md`

### Paso 2 — Leer el PDF (todas las páginas)

Usar la herramienta Read sobre el PDF. **No asumir** que los datos relevantes están sólo en la portada — una factura eléctrica típica tiene 4 páginas con información distinta en cada una (ver prompt).

### Paso 3 — Extraer los 20 bloques

Seguir el orden y la estructura definidos en el prompt. Capturar textos legales **literalmente** (RDL 8/2023, nota de excedentes, reclamaciones, etiquetado ambiental).

### Paso 4 — Generar `<stem>_ai.md`

Usar la herramienta Write. Stem = nombre del PDF sin extensión + sufijo `_ai`. Ubicación = misma carpeta del PDF. Seguir la **plantilla Markdown** del prompt (21 secciones, la 21 sólo si hay advertencias).

### Paso 5 — Generar `<stem>_ai.json` (extracción AI completa, anidada)

Usar la herramienta Write. Mismo stem y carpeta + sufijo `_ai`. Seguir el **esquema JSON** del prompt (24 claves raíz, `advertencias` siempre presente como array — vacío si no hay discrepancias).

### Paso 5b — Generar `<stem>_processed.json` (TERCER fichero, plano, schema endpoint)

Usar la herramienta Write. Mismo stem + sufijo `_processed`. Schema **plano y compatible con el endpoint `POST /facturas/extraer`** del backend, con campos extra:

- `validacion_cuadre`: bloque con todos los `*_calc` derivados de los valores facturados (R12) que sumados = `importe_factura`.
- `otros`: diccionario de conceptos no estándar (Pack Iberdrola, Asistencia PYMES, etc.) con su importe.
- `error`: `null` si cuadre OK; string descriptiva si la suma de conceptos no cuadra con el total (R13).

Ver el esquema completo en `prompt_lectura_factura.md` (sección "Esquema `_processed.json`").

**REGLA CRÍTICA R12:** usar **valores facturados** (líneas `X kWh × Y €/kWh = Z €`) — NUNCA desagregados ni lecturas acumuladas.

### Paso 6 — Validar con `scripts/validate.py`

Ejecutar el script de validación sobre **ambos JSONs**:

```bash
python3 .claude/skills/leer-factura/scripts/validate.py <ruta_al_ai_json>
python3 .claude/skills/leer-factura/scripts/validate.py <ruta_al_processed_json>
```

El script:
- Valida que el JSON parsea correctamente.
- Ejecuta las 7 validaciones de coherencia (suma resumen, R2 energía facturada × precio, R2b desagregados informativo, IVA, peajes, distribución del coste, mix energético, R7 reconciliación contable).
- Imprime un informe con ✅ / ⚠️ / ⏭️ por cada check.
- Sale con código 0 siempre (las discrepancias son advertencias, no errores fatales).

### Paso 7 — Actualizar advertencias y `error` (si hay discrepancias)

Si el validador reporta ⚠️:
- En `_ai.json`: añadir entrada en `advertencias[]` con `tipo` y `descripcion`.
- En `_processed.json`: si la R7 falla, poblar `error` con descripción de la diferencia y mover conceptos no clasificables al diccionario `otros`.

**Nunca ajustar valores numéricos** para forzar cuadre — reportar la discrepancia tal cual.

### Paso 8 — Reportar al usuario

Entregar un resumen conciso:

1. Ruta de los **3 archivos generados** (`<stem>_ai.md`, `<stem>_ai.json`, `<stem>_processed.json`).
2. Resumen de las 7 validaciones (✅ / ⚠️ / ⏭️).
3. **Cuadre del `_processed.json`:** `cuadra: true/false`, diferencia en €.
4. Lista de advertencias y `error` si los hubiere.
5. Confirmación de que ambos JSONs validan con `json.load`.

## Reglas críticas (no negociables)

- **R1** — Textos legales palabra por palabra (blockquote en MD, string exacta en JSON).
- **R8** — Nunca inventar valores. Campos ausentes → `null` (JSON) / "no indicado" (MD).
- **R11** — MD y JSON deben contener la **misma información** (no hay datos en uno que no estén en el otro).
- **R12** — Valores **facturados** (líneas `X kWh × Y €/kWh`) son la única fuente de verdad para reconciliación. Desagregados y lecturas son sólo informativos.
- **R13** — Reconciliación contable obligatoria: `suma_conceptos == importe_factura`. Si no cuadra → `otros` + `error` en `_processed.json`.
- **Validación obligatoria** — Ejecutar `validate.py` sobre ambos JSONs antes de declarar la extracción completa.
- **3 outputs siempre** — Si el PDF está vacío o ilegible, generar igualmente `_processed.json` con `error: "<motivo>"` y todos los campos `null`.
- **No omitir secciones** — Si un bloque no aplica al PDF concreto, incluirlo igualmente con valores `null`.

## Ejemplos de uso

### Ejemplo 1 — Invocación explícita

> "Lee facturas/iberdrola1.pdf y extrae todos los datos"

Activación: ✅ (palabra "factura" + PDF)

### Ejemplo 2 — Invocación implícita

> "Proceso este PDF de Iberdrola"

Activación: ✅ (comercializadora + PDF)

### Ejemplo 3 — Batch

> "Procesa todos los PDFs de la carpeta facturas/"

Activación: ✅ (aplicar el workflow a cada PDF, generando `<stem>.md` y `<stem>.json` por cada uno).

## Ficheros de la skill

```
.claude/skills/leer-factura/
├── SKILL.md                         (este fichero, el manifiesto)
├── prompt_lectura_factura.md        (instrucciones detalladas)
├── README.md                        (documentación para humanos)
└── scripts/
    └── validate.py                  (validador de coherencia del JSON)
```

## Dependencias

- **Python 3.8+** — para ejecutar `validate.py`.
- Sin librerías externas. El validador usa sólo la stdlib (`json`, `sys`, `pathlib`).

## Limitaciones conocidas

- **Formato español**: la skill está diseñada para facturas del mercado eléctrico español (CUPS, ATR 2.0TD/3.0TD/6.1TD, compensación de excedentes CNMC, bono social). No aplicable a facturas de otros países sin adaptación.
- **OCR**: si el PDF es una imagen escaneada sin capa de texto, la extracción puede ser parcial. El validador detectará totales que no cuadran.
- **Facturas rectificativas / abonos**: la regla R9 indica cómo detectarlos, pero los cálculos de coherencia se han pensado para facturas normales. Revisar manualmente el signo de los importes en rectificativas.
