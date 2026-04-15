# Claude API Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir el endpoint `POST /facturas/extraer-ai` que extrae datos de facturas eléctricas vía Claude API (Sonnet 4.6), calcula la validación de cuadre R13, guarda el resultado en sesión, y devuelve `ExtractionResponseAI` con `session_id`.

**Architecture:** Módulo `api/claude/` con separación de responsabilidades (client singleton, prompt loader, extractor). El endpoint es paralelo al regex existente — cero cambios en `extractor/`. Claude recibe el PDF en base64 como `document` block, usa `messages.parse()` con `output_format=ExtractionResponseAI` para guaranteed structured output. El backend calcula `validacion_cuadre` (R13) y llama a `crear_sesion()` directamente.

**Tech Stack:** `anthropic` Python SDK, FastAPI, Pydantic v2, `messages.parse()` con structured outputs, prompt caching TTL 1h.

---

## Mapa de ficheros

| Fichero | Acción | Responsabilidad |
|---|---|---|
| `requirements.txt` | Modificar | Añadir `anthropic` |
| `.env.example` | Modificar | Añadir `ANTHROPIC_API_KEY` |
| `api/models.py` | Modificar | Añadir `ValidacionCuadre` + `ExtractionResponseAI` |
| `api/claude/__init__.py` | Crear | Exponer `extract_with_claude` |
| `api/claude/client.py` | Crear | Singleton `anthropic.Anthropic()` |
| `api/claude/prompts.py` | Crear | Cargar `prompt_lectura_factura.md` + preamble |
| `api/claude/extractor.py` | Crear | `extract_with_claude(pdf_bytes) → ExtractionResponseAI` |
| `api/routes/facturas_ai.py` | Crear | `POST /facturas/extraer-ai` + `_calc_validacion_cuadre` |
| `api/main.py` | Modificar | Registrar `facturas_ai_router` |

---

## Task 1: Dependencias y variables de entorno

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Añadir `anthropic` a requirements.txt**

Abrir `requirements.txt` y añadir al final de la sección "API REST":

```
# Claude API
anthropic
```

El fichero completo debe quedar:
```
# Extracción PDF
pdfplumber
pymupdf

# OCR (PDFs basados en imagen)
pytesseract
pdf2image
pillow

# API REST
fastapi
uvicorn[standard]
python-multipart

# Validación de datos
pydantic

# HTTP (llamadas a API Ingebau y proxies async)
requests
httpx

# Claude API
anthropic
```

- [ ] **Step 2: Añadir `ANTHROPIC_API_KEY` a `.env.example`**

Añadir al final del fichero:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

- [ ] **Step 3: Instalar la dependencia**

```bash
pip install anthropic
```

Verificar que no hay errores de resolución de dependencias.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add anthropic SDK dependency"
```

---

## Task 2: Modelos de datos (`api/models.py`)

**Files:**
- Modify: `api/models.py`

**Contexto:** `ExtractionResponse` (ya existe) contiene `imp_ele` como porcentaje IEE (%), `iva` como porcentaje (%), `alq_eq_dia` como €/día. Para calcular R13 server-side necesitamos los importes en € que Claude extrae directamente de las líneas de la factura (Claude ve "Término de energía: 34,12 €", "IVA 21%: 28,55 €", etc.).

- [ ] **Step 1: Añadir `ValidacionCuadre` a `api/models.py`**

Abrir `api/models.py`. Después de los imports existentes, añadir la clase `ValidacionCuadre` antes de `ExtractionResponse`:

```python
class ValidacionCuadre(BaseModel):
    cuadra:            bool
    importe_factura:   Optional[float] = None   # valor del campo importe_factura
    suma_conceptos:    Optional[float] = None   # suma calculada de conceptos extraídos
    diferencia_eur:    Optional[float] = None   # abs(importe_factura - suma_conceptos)
    error:             Optional[str]  = None    # descripción si cuadra=False, null si OK
```

- [ ] **Step 2: Añadir `ExtractionResponseAI` a `api/models.py`**

Al final del fichero, después de `ExtractionResponse`, añadir:

```python
class ExtractionResponseAI(ExtractionResponse):
    """Respuesta del endpoint /facturas/extraer-ai (Claude API).

    Hereda todos los campos de ExtractionResponse y añade:
    - Importes en € calculados directamente desde las líneas de factura (para R13)
    - otros: conceptos no estándar (Pack Iberdrola, Asistencia PYMES, etc.)
    - validacion_cuadre: resultado de la reconciliación R13 (calculado server-side)
    - session_id: ID de sesión en /sesion (calculado server-side)
    """

    # ── Importes en € extraídos de las líneas de factura (R12) ───────────────
    imp_termino_energia_eur:    Optional[float] = None  # Total término energía €
    imp_termino_potencia_eur:   Optional[float] = None  # Total término potencia €
    imp_impuesto_electrico_eur: Optional[float] = None  # IEE en € (no el %)
    imp_alquiler_eur:           Optional[float] = None  # Alquiler contador €
    imp_iva_eur:                Optional[float] = None  # IVA en €

    # ── Conceptos no estándar (R13) ───────────────────────────────────────────
    otros:              Optional[dict]             = None

    # ── Calculados server-side (Claude debe dejar estos campos null) ──────────
    validacion_cuadre:  Optional[ValidacionCuadre] = None
    session_id:         Optional[str]              = None
```

- [ ] **Step 3: Verificar que `api/models.py` importa bien**

```bash
python -c "from api.models import ExtractionResponse, ExtractionResponseAI, ValidacionCuadre; print('OK')"
```

Salida esperada: `OK`

- [ ] **Step 4: Commit**

```bash
git add api/models.py
git commit -m "feat: add ValidacionCuadre and ExtractionResponseAI models"
```

---

## Task 3: `api/claude/client.py`

**Files:**
- Create: `api/claude/__init__.py`
- Create: `api/claude/client.py`

- [ ] **Step 1: Crear `api/claude/__init__.py`** (vacío por ahora)

```python
# api/claude/__init__.py
```

- [ ] **Step 2: Crear `api/claude/client.py`**

```python
# api/claude/client.py
# Singleton del cliente Anthropic. Falla al arrancar si ANTHROPIC_API_KEY no está definida.

import os
import anthropic

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """Devuelve el cliente Anthropic (singleton lazy).

    Lanza KeyError si ANTHROPIC_API_KEY no está en el entorno.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client
```

- [ ] **Step 3: Verificar que el módulo importa correctamente (sin API key real)**

```bash
python -c "
import os
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-key')
from api.claude.client import get_client
client = get_client()
print(type(client).__name__)
"
```

Salida esperada: `Anthropic`

- [ ] **Step 4: Verificar que falla si no hay API key**

```bash
python -c "
import os
os.environ.pop('ANTHROPIC_API_KEY', None)
from api.claude.client import get_client
try:
    get_client()
    print('ERROR: debería haber fallado')
except KeyError as e:
    print(f'OK: KeyError {e}')
"
```

Salida esperada: `OK: KeyError 'ANTHROPIC_API_KEY'`

- [ ] **Step 5: Commit**

```bash
git add api/claude/__init__.py api/claude/client.py
git commit -m "feat: add Anthropic client singleton"
```

---

## Task 4: `api/claude/prompts.py`

**Files:**
- Create: `api/claude/prompts.py`

**Contexto:** El system prompt = preamble (sustituye workflow del SKILL.md) + `prompt_lectura_factura.md` (39KB, ~12K tokens). Debe ser byte-idéntico entre llamadas para que el cache funcione. Por eso se carga en el arranque del módulo (una sola vez) y no incluye nada dinámico.

- [ ] **Step 1: Crear `api/claude/prompts.py`**

```python
# api/claude/prompts.py
# Carga el system prompt para la extracción de facturas vía Claude API.
#
# REGLA CRÍTICA: el contenido de SYSTEM_PROMPT debe ser byte-idéntico entre
# llamadas — no interpolar datetime, UUIDs ni contenido dinámico, o el cache
# se invalida y cada llamada paga precio completo.

from pathlib import Path

_SKILL_DIR = Path(__file__).parent.parent.parent / ".claude" / "skills" / "leer-factura"
_PROMPT_PATH = _SKILL_DIR / "prompt_lectura_factura.md"

# Preamble: reemplaza las instrucciones de workflow del SKILL.md
# (escribir ficheros, ejecutar scripts, reportar al usuario) por una instrucción
# directa de devolver JSON estructurado.
_PREAMBLE = (
    "Eres un extractor de datos de facturas eléctricas españolas.\n"
    "Tu única tarea es leer el PDF adjunto y devolver un JSON estructurado "
    "con todos los campos que puedas extraer.\n"
    "NO escribas ficheros. NO ejecutes scripts. Solo devuelve el JSON.\n"
    "Los campos 'validacion_cuadre' y 'session_id' deben ser siempre null "
    "(se calculan en el servidor)."
)


def get_system_prompt() -> str:
    """Lee prompt_lectura_factura.md y lo combina con el preamble.

    Se evalúa una sola vez en el arranque del módulo.
    Lanza FileNotFoundError si el fichero de skill no existe.
    """
    prompt_text = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PREAMBLE + "\n\n" + prompt_text


# Constante cargada en arranque — garantiza byte-idéntico entre llamadas
SYSTEM_PROMPT: str = get_system_prompt()
```

- [ ] **Step 2: Verificar que el prompt carga correctamente**

```bash
python -c "
from api.claude.prompts import SYSTEM_PROMPT
tokens_aprox = len(SYSTEM_PROMPT.split()) // 0.75
print(f'Longitud: {len(SYSTEM_PROMPT)} chars')
print(f'Tokens aprox: {int(len(SYSTEM_PROMPT.split()) / 0.75)}')
print(f'Primeras 100 chars: {SYSTEM_PROMPT[:100]}')
"
```

Salida esperada (aproximada):
```
Longitud: ~47000 chars
Tokens aprox: ~12000
Primeras 100 chars: Eres un extractor de datos de facturas eléctricas españolas...
```

- [ ] **Step 3: Commit**

```bash
git add api/claude/prompts.py
git commit -m "feat: add system prompt loader for Claude API"
```

---

## Task 5: `api/claude/extractor.py`

**Files:**
- Create: `api/claude/extractor.py`
- Modify: `api/claude/__init__.py`

- [ ] **Step 1: Crear `api/claude/extractor.py`**

```python
# api/claude/extractor.py
# Extrae datos de una factura PDF usando la Claude API.

import base64

import anthropic

from api.claude.client import get_client
from api.claude.prompts import SYSTEM_PROMPT
from api.models import ExtractionResponseAI

MODEL = "claude-sonnet-4-6"

# Texto de usuario que acompaña al PDF — corto y estable (no afecta al cache
# del system prompt, que ya está marcado con cache_control).
_USER_TEXT = "Extrae todos los datos de esta factura según las instrucciones."


def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    """Envía el PDF a Claude y devuelve los datos extraídos.

    Args:
        pdf_bytes: Contenido binario del PDF.

    Returns:
        ExtractionResponseAI con todos los campos que Claude pudo extraer.
        Los campos `validacion_cuadre` y `session_id` quedan null (se calculan
        en el endpoint).

    Raises:
        anthropic.APIStatusError: Error de la API Anthropic (4xx/5xx).
        anthropic.APITimeoutError: Timeout de la API Anthropic.
    """
    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": _USER_TEXT},
                ],
            }
        ],
        output_format=ExtractionResponseAI,
    )

    return response.parsed_output
```

- [ ] **Step 2: Actualizar `api/claude/__init__.py`**

```python
# api/claude/__init__.py
from api.claude.extractor import extract_with_claude

__all__ = ["extract_with_claude"]
```

- [ ] **Step 3: Verificar que el módulo importa sin errores (sin llamar a la API)**

```bash
python -c "
import os
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-key')
from api.claude import extract_with_claude
print('OK:', extract_with_claude)
"
```

Salida esperada: `OK: <function extract_with_claude at 0x...>`

- [ ] **Step 4: Commit**

```bash
git add api/claude/__init__.py api/claude/extractor.py
git commit -m "feat: add extract_with_claude function"
```

---

## Task 6: `api/routes/facturas_ai.py`

**Files:**
- Create: `api/routes/facturas_ai.py`

**Contexto:** El endpoint replica la estructura de `api/routes/facturas.py` pero usa Claude en vez del parser regex. La función `_calc_validacion_cuadre` suma los importes en € que Claude extrajo de las líneas de la factura (campos `imp_*_eur`) y los compara con `importe_factura`. Los descuentos en `descuentos` son negativos (ya salen con signo negativo de la factura); `otros` son positivos.

- [ ] **Step 1: Crear `api/routes/facturas_ai.py`**

```python
# api/routes/facturas_ai.py
# Endpoint POST /facturas/extraer-ai
# Extrae datos de facturas eléctricas usando la Claude API.

import json
import os

import anthropic
from fastapi import APIRouter, File, HTTPException, UploadFile

from api.claude import extract_with_claude
from api.models import ExtractionResponseAI, ValidacionCuadre
from api.routes.sesion import crear_sesion

router = APIRouter(prefix="/facturas", tags=["facturas-ai"])

RESULTADOS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "resultados"
)
os.makedirs(RESULTADOS_DIR, exist_ok=True)


def _calc_validacion_cuadre(result: ExtractionResponseAI) -> ValidacionCuadre:
    """Calcula la reconciliación contable R13.

    Suma los importes en € que Claude extrajo de las líneas de la factura y
    compara con importe_factura. Diferencia <= 0.02€ se considera cuadre OK.

    Los descuentos en result.descuentos deben ser negativos (tal como aparecen
    en la factura). Los conceptos en result.otros son positivos.
    """
    if result.importe_factura is None:
        return ValidacionCuadre(
            cuadra=False,
            error="importe_factura no extraído — no se puede calcular cuadre",
        )

    conceptos: list[float] = []

    for campo in [
        result.imp_termino_energia_eur,
        result.imp_termino_potencia_eur,
        result.imp_impuesto_electrico_eur,
        result.imp_alquiler_eur,
        result.bono_social,
        result.imp_iva_eur,
    ]:
        if campo is not None:
            conceptos.append(campo)

    if result.descuentos:
        conceptos.extend(result.descuentos.values())

    if result.otros:
        conceptos.extend(result.otros.values())

    if not conceptos:
        return ValidacionCuadre(
            cuadra=False,
            importe_factura=result.importe_factura,
            suma_conceptos=0.0,
            diferencia_eur=round(abs(result.importe_factura), 2),
            error="No se extrajeron importes parciales — no se puede calcular cuadre",
        )

    suma = round(sum(conceptos), 2)
    diferencia = round(abs(result.importe_factura - suma), 2)
    cuadra = diferencia <= 0.02

    return ValidacionCuadre(
        cuadra=cuadra,
        importe_factura=result.importe_factura,
        suma_conceptos=suma,
        diferencia_eur=diferencia,
        error=(
            None
            if cuadra
            else (
                f"Diferencia de {diferencia}€ entre "
                f"importe_factura ({result.importe_factura}€) "
                f"y suma_conceptos ({suma}€)"
            )
        ),
    )


@router.post("/extraer-ai", response_model=ExtractionResponseAI)
async def extraer_factura_ai(file: UploadFile = File(...)):
    """Extrae datos de una factura PDF usando la Claude API (Sonnet 4.6).

    Devuelve ExtractionResponseAI con:
    - Todos los campos de ExtractionResponse extraídos por Claude
    - validacion_cuadre: reconciliación contable R13 (calculada server-side)
    - session_id: ID de sesión en /sesion con TTL de 40 minutos
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    pdf_bytes = await file.read()

    try:
        result = extract_with_claude(pdf_bytes)
    except anthropic.APIStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Claude API error {e.status_code}: {e.message}",
        )
    except anthropic.APITimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Claude API timeout. Intenta de nuevo.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando el PDF: {e}",
        )

    # Calcular validación de cuadre R13 server-side
    result.validacion_cuadre = _calc_validacion_cuadre(result)

    # Guardar en sesión (TTL 40 min) y obtener session_id
    result.session_id = crear_sesion(result.model_dump())

    # Guardar JSON en resultados/ con sufijo _ai
    cups   = result.cups or "sin_cups"
    inicio = (result.periodo_inicio or "").replace("/", "-")
    fin    = (result.periodo_fin    or "").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}_ai.json"
    ruta   = os.path.join(RESULTADOS_DIR, nombre)

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

    result.fichero_json = nombre
    return result
```

- [ ] **Step 2: Verificar que el módulo importa sin errores**

```bash
python -c "
import os
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-key')
from api.routes.facturas_ai import router, _calc_validacion_cuadre
print('router prefix:', router.prefix)
print('OK')
"
```

Salida esperada:
```
router prefix: /facturas
OK
```

- [ ] **Step 3: Verificar `_calc_validacion_cuadre` con datos de prueba**

```bash
python -c "
import os
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-key')
from api.models import ExtractionResponseAI
from api.routes.facturas_ai import _calc_validacion_cuadre

# Caso OK: cuadre correcto
r = ExtractionResponseAI(
    importe_factura=100.00,
    imp_termino_energia_eur=50.00,
    imp_termino_potencia_eur=20.00,
    imp_impuesto_electrico_eur=4.90,
    imp_iva_eur=25.10,
)
v = _calc_validacion_cuadre(r)
print(f'cuadra={v.cuadra} diferencia={v.diferencia_eur}€')

# Caso KO: diferencia > 0.02€
r2 = ExtractionResponseAI(
    importe_factura=100.00,
    imp_termino_energia_eur=50.00,
    imp_termino_potencia_eur=20.00,
)
v2 = _calc_validacion_cuadre(r2)
print(f'cuadra={v2.cuadra} error={v2.error}')
"
```

Salida esperada:
```
cuadra=True diferencia=0.0€
cuadra=False error=Diferencia de 30.0€ ...
```

- [ ] **Step 4: Commit**

```bash
git add api/routes/facturas_ai.py
git commit -m "feat: add /facturas/extraer-ai endpoint with R13 validation"
```

---

## Task 7: Registrar router en `api/main.py`

**Files:**
- Modify: `api/main.py`

- [ ] **Step 1: Añadir el import del nuevo router en `api/main.py`**

Después de la línea `from api.routes.sesion import router as sesion_router`, añadir:

```python
from api.routes.facturas_ai import router as facturas_ai_router
```

- [ ] **Step 2: Registrar el router**

Después de `app.include_router(sesion_router)`, añadir:

```python
app.include_router(facturas_ai_router)
```

- [ ] **Step 3: Verificar que la app arranca sin errores**

Crear un `.env` temporal con una key de test (si no existe):

```bash
# Solo si no existe .env con ANTHROPIC_API_KEY
echo "ANTHROPIC_API_KEY=test-key-for-import-check" >> .env
```

Verificar que la app importa y los endpoints están registrados:

```bash
python -c "
from api.main import app
routes = [r.path for r in app.routes]
print('Rutas registradas:')
for r in sorted(routes):
    print(' ', r)
assert '/facturas/extraer-ai' in routes, 'FALTA /facturas/extraer-ai'
assert '/facturas/extraer' in routes, 'FALTA /facturas/extraer (regresión)'
print('OK')
"
```

Salida esperada:
```
Rutas registradas:
  /
  /cups/consultar
  /enviar
  /facturas/extraer
  /facturas/extraer-ai
  /health
  /sesion
  /sesion/{session_id}
  ...
OK
```

- [ ] **Step 4: Commit**

```bash
git add api/main.py
git commit -m "feat: register facturas-ai router in FastAPI app"
```

---

## Task 8: Test manual vía Swagger UI

**Prerequisito:** `.env` debe tener `ANTHROPIC_API_KEY` real (no `test-key`).

- [ ] **Step 1: Arrancar el servidor**

```bash
uvicorn api.main:app --reload --port 8000
```

Verificar que arranca sin errores. Si sale `KeyError: 'ANTHROPIC_API_KEY'`, añadir la key real al `.env`.

- [ ] **Step 2: Abrir Swagger UI**

Navegar a `http://localhost:8000/docs`

Verificar que el endpoint `POST /facturas/extraer-ai` aparece bajo la sección **facturas-ai**.

- [ ] **Step 3: Test con factura Iberdrola**

En Swagger UI → `POST /facturas/extraer-ai` → **Try it out**:

1. Subir `facturas/iberdrola_1/iberdrola1.pdf` (o cualquier factura PDF disponible)
2. Hacer click en **Execute**
3. Esperar respuesta (5–15 segundos — latencia normal de Claude)

**Verificaciones en la respuesta:**

```json
{
  "cups": "ES0021...",           // debe estar presente
  "periodo_inicio": "...",       // debe estar presente
  "comercializadora": "Iberdrola",
  "importe_factura": 123.45,     // debe estar presente
  "validacion_cuadre": {
    "cuadra": true,              // objetivo: true con diferencia <= 0.02€
    "diferencia_eur": 0.01
  },
  "session_id": "uuid-...",      // debe estar presente
  "fichero_json": "ES0021..._ai.json"
}
```

- [ ] **Step 4: Verificar que `/facturas/extraer` sigue funcionando (no regresión)**

En Swagger UI → `POST /facturas/extraer` → subir la misma factura.

Verificar que devuelve `ExtractionResponse` sin los campos `validacion_cuadre`, `session_id`, `imp_termino_energia_eur` (esos son de AI).

- [ ] **Step 5: Verificar sesión guardada**

Copiar el `session_id` de la respuesta. En Swagger UI → `GET /sesion/{session_id}`:

Verificar que devuelve los datos de la factura extraída.

- [ ] **Step 6: Verificar prompt caching**

Enviar la misma factura (o cualquier otra) por segunda vez al endpoint.

En los logs del servidor o via debug, verificar que la segunda llamada es más rápida (~30-50% menos tiempo). El cache hit se confirma si `cache_read_input_tokens > 0` en la respuesta de la API Anthropic (visible si se añade logging al extractor).

- [ ] **Step 7: Verificar JSON guardado en `resultados/`**

```bash
ls resultados/*_ai.json
```

Abrir el fichero y verificar que tiene todos los campos incluyendo `validacion_cuadre` y `session_id`.

- [ ] **Step 8: Commit final**

```bash
git add .
git commit -m "feat: Claude API extractor endpoint complete

POST /facturas/extraer-ai:
- Extrae datos de facturas via Claude Sonnet 4.6
- Calcula validacion_cuadre R13 server-side
- Guarda resultado en sesion (TTL 40min)
- Devuelve ExtractionResponseAI + session_id"
```

---

## Criterios de aceptación

1. `POST /facturas/extraer-ai` responde con `ExtractionResponseAI` incluyendo `validacion_cuadre` y `session_id`.
2. `GET /sesion/{session_id}` devuelve los datos de la factura durante 40 minutos.
3. `validacion_cuadre.cuadra == true` en facturas Iberdrola bien formateadas.
4. `POST /facturas/extraer` existente no muestra cambios de comportamiento.
5. `ANTHROPIC_API_KEY` ausente → `KeyError` al arrancar, no en tiempo de petición.
6. Ficheros `*_ai.json` en `resultados/` no colisionan con los del parser regex.

---

## Troubleshooting

**`KeyError: 'ANTHROPIC_API_KEY'` al arrancar:**
→ Añadir `ANTHROPIC_API_KEY=sk-ant-...` al `.env` y reiniciar el servidor.

**`502 Claude API error 401`:**
→ La API key es inválida o ha expirado. Renovar en console.anthropic.com.

**`504 Claude API timeout`:**
→ PDF muy grande o timeout de red. Intentar de nuevo. Si persiste, verificar que el PDF no supera los 20MB.

**`validacion_cuadre.cuadra == false` con diferencia grande:**
→ Claude no extrajo los importes parciales (`imp_termino_energia_eur` etc. son null). Revisar el `prompt_lectura_factura.md` para ver si incluye instrucciones para extraer importes de líneas. Si no, añadir al preamble en `prompts.py`: `"Extrae siempre los importes totales en € de cada término: energía, potencia, impuesto eléctrico, alquiler e IVA."`.

**`cache_read_input_tokens` siempre 0:**
→ El system prompt tiene un invalidador. Verificar que `get_system_prompt()` es puro y no incluye `datetime.now()`, UUIDs ni contenido dinámico. Verificar que `prompt_lectura_factura.md` no ha cambiado entre llamadas.

**`AttributeError: 'Anthropic' object has no attribute 'messages.parse'`:**
→ La versión de `anthropic` instalada no soporta structured outputs. Actualizar: `pip install --upgrade anthropic`.
