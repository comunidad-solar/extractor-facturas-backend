# Design: Integración Claude API — Endpoint `/facturas/extraer-ai`

**Fecha:** 2026-04-15  
**Autor:** Rodrigo Costa  
**Estado:** Aprobado

---

## Contexto

El backend actual (`POST /facturas/extraer`) extrae datos de facturas eléctricas españolas usando parsers regex por comercializadora (`extractor/parsers/`). Este diseño añade un segundo endpoint paralelo que delega la extracción a la Claude API (Anthropic), reutilizando el prompt de la skill `leer-factura` y el schema Pydantic existente.

**Motivación principal:** los parsers regex fallan en PDFs escaneados (Bug #5) y en layouts nuevos de comercializadoras. Claude lee PDFs nativamente vía visión, sin Tesseract ni Poppler.

---

## Decisiones

| Decisión | Elección | Justificación |
|---|---|---|
| Escenario de deployment | **A — endpoint paralelo** | Zero riesgo para el servicio actual; permite validar calidad antes de migrar |
| Modelo | **claude-sonnet-4-6** | ~6× más barato que Opus, 5–10s/factura, suficiente capacidad |
| System prompt | **Solo `prompt_lectura_factura.md`** + preamble | SKILL.md contiene workflow para Claude Code CLI (escribir ficheros, scripts) — irrelevante y contraproducente vía API |
| Prompt caching | **TTL 1h** | System prompt byte-idéntico entre llamadas → cache hit desde la 2ª factura de la hora |
| Output format | **Pydantic structured output** | `client.messages.parse()` garantiza schema válido sin regex/json.loads |
| ValidacionCuadre | **Implementar en este trabajo** | Double-check R13 server-side después de recibir respuesta de Claude |
| Estructura de código | **Módulo `api/claude/`** | Separación clara de responsabilidades; extensible para batch mode, Opus fallback |

---

## Arquitectura

### Ficheros nuevos

```
api/
└── claude/
    ├── __init__.py          # expone extract_with_claude
    ├── client.py            # singleton anthropic.Anthropic()
    ├── prompts.py           # lee prompt_lectura_factura.md → SYSTEM_PROMPT
    └── extractor.py         # extract_with_claude(pdf_bytes) → ExtractionResponseAI

api/routes/
└── facturas_ai.py           # POST /facturas/extraer-ai
```

### Ficheros modificados

| Fichero | Cambio |
|---|---|
| `api/models.py` | Añadir `ValidacionCuadre` + `ExtractionResponseAI(ExtractionResponse)` |
| `api/main.py` | Registrar `facturas_ai_router` |
| `requirements.txt` | Añadir `anthropic` |
| `.env.example` | Añadir `ANTHROPIC_API_KEY=sk-ant-...` |

### Sin cambios en

- `extractor/` (parsers regex intactos)
- `api/routes/facturas.py` (endpoint actual intacto)
- Cualquier otro router existente

---

## Modelos de datos (`api/models.py`)

### `ValidacionCuadre` (nuevo)

```python
class ValidacionCuadre(BaseModel):
    cuadra:            bool
    importe_factura:   Optional[float] = None   # valor del campo importe_factura
    suma_conceptos:    Optional[float] = None   # suma calculada de conceptos extraídos
    diferencia_eur:    Optional[float] = None   # abs(importe_factura - suma_conceptos)
    error:             Optional[str]  = None    # descripción si cuadra=False, null si OK
```

### `ExtractionResponseAI` (nuevo, hereda de `ExtractionResponse`)

```python
class ExtractionResponseAI(ExtractionResponse):
    otros:              Optional[dict]             = None  # conceptos no-standard
    validacion_cuadre:  Optional[ValidacionCuadre] = None
    session_id:         Optional[str]              = None  # ID de sesión creada en /sesion
```

**Porqué heredar:** `ExtractionResponse` no cambia → el endpoint `/extraer` existente no sufre breaking changes. El frontend actual no ve los campos nuevos.

---

## Módulo `api/claude/`

### `client.py`

Singleton lazy. Falla inmediatamente al arrancar si `ANTHROPIC_API_KEY` no está definida.

```python
import anthropic, os

_client = None

def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client
```

### `prompts.py`

Lee `prompt_lectura_factura.md` del disco. El `_PREAMBLE` reemplaza las instrucciones de workflow del SKILL.md (escribir ficheros, ejecutar scripts) por una instrucción directa de devolver JSON.

```python
from pathlib import Path

_PROMPT_PATH = Path(__file__).parent.parent.parent / ".claude/skills/leer-factura/prompt_lectura_factura.md"

_PREAMBLE = """
Eres un extractor de datos de facturas eléctricas españolas.
Tu única tarea es leer el PDF adjunto y devolver un JSON estructurado.
NO escribas ficheros. NO ejecutes scripts. Solo devuelve el JSON.
""".strip()

def get_system_prompt() -> str:
    return _PREAMBLE + "\n\n" + _PROMPT_PATH.read_text(encoding="utf-8")
```

**Regla crítica:** el system prompt debe ser byte-idéntico entre llamadas. No interpolar `datetime.now()`, UUIDs ni contenido dinámico — invalida el cache.

### `extractor.py`

```python
import base64
from api.claude.client import get_client
from api.claude.prompts import get_system_prompt
from api.models import ExtractionResponseAI

MODEL = "claude-sonnet-4-6"
SYSTEM_PROMPT = get_system_prompt()  # cargado en arranque del módulo

def extract_with_claude(pdf_bytes: bytes) -> ExtractionResponseAI:
    client = get_client()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral", "ttl": "1h"}
        }],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf_bytes).decode()
                    }
                },
                {"type": "text", "text": "Extrae todos los datos de esta factura según las instrucciones."}
            ]
        }],
        output_format=ExtractionResponseAI
    )
    return response.parsed_output
```

---

## Endpoint `POST /facturas/extraer-ai`

### Flujo completo

```
PDF upload
  └─► validar extensión .pdf
       └─► pdf_bytes = await file.read()
            └─► extract_with_claude(pdf_bytes)              # Claude API
                 └─► _calc_validacion_cuadre(result)        # R13 server-side
                      └─► crear_sesion(result.model_dump()) # → session_id (TTL 40min)
                           └─► guardar JSON en resultados/  # sufijo _ai
                                └─► devolver ExtractionResponseAI + session_id
```

Sin ficheros temporales en disco. Sin pdfplumber. Sin Tesseract.

`crear_sesion()` se importa directamente desde `api.routes.sesion` — sin HTTP interno.

### Tratamiento de errores

| Situación | HTTP | Detalle |
|---|---|---|
| Fichero no es PDF | 400 | Validación local, sin llamar a Claude |
| Error API Anthropic (4xx/5xx) | 502 | `anthropic.APIStatusError` |
| Timeout Claude | 504 | `anthropic.APITimeoutError` |
| Error inesperado | 500 | Genérico |

### Ficheros JSON guardados

Sufijo `_ai` para no colisionar con los del endpoint regex:
- Regex: `{cups}_{inicio}_{fin}.json`
- Claude: `{cups}_{inicio}_{fin}_ai.json`

---

## `_calc_validacion_cuadre`

Función en `api/routes/facturas_ai.py`. Recibe `ExtractionResponseAI` ya poblado por Claude y calcula cuadre R13:

```
suma_conceptos = imp_ele + imp_potencia + alq_eq + bono_social
               + sum(descuentos.values()) + sum(otros.values())
               + (suma_sin_iva * iva / 100)   # IVA calculado sobre base imponible
diferencia_eur = abs(importe_factura - suma_conceptos)
cuadra         = diferencia_eur <= 0.02
```

Si `cuadra=False`, `error` describe la diferencia. Los valores numéricos **nunca se ajustan** para forzar cuadre (R13).

---

## Prompt caching — resumen operativo

- **Cache hit:** `response.usage.cache_read_input_tokens > 0`
- **Ahorro real:** ~14% con 3 facturas/hora, ~32% en volumen alto
- **Verificación:** si `cache_read_input_tokens == 0` en la 2ª llamada dentro del TTL → hay un invalidador silencioso en el system prompt (comprobar que `get_system_prompt()` es puro y no incluye contenido dinámico)

---

## Variables de entorno

Añadir a `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

La clave nunca debe aparecer en logs, código ni repositorio.

---

## Criterios de aceptación

1. `POST /facturas/extraer-ai` devuelve `ExtractionResponseAI` con todos los campos de `ExtractionResponse` más `otros`, `validacion_cuadre` y `session_id`.
2. `session_id` presente en la respuesta permite recuperar los datos vía `GET /sesion/{session_id}` durante 40 minutos.
3. `validacion_cuadre.cuadra == True` y `diferencia_eur <= 0.02` en las facturas de referencia Iberdrola.
4. El endpoint `/facturas/extraer` existente no sufre cambios de comportamiento.
5. `ANTHROPIC_API_KEY` ausente → error claro al arrancar, no en tiempo de petición.
6. El sufijo `_ai` en los JSONs guardados no colisiona con los del parser regex.
