# Contexto Completo do Projeto — extractor-facturas-backend

> Documento de referência gerado em 2026-04-16.
> Cobre toda a arquitectura, endpoints, modelos, integrações e decisões de design.

---

## 1. Visão Geral

Sistema Python para extrair campos de facturas eléctricas espanholas em PDF, de múltiplas comercializadoras. Funciona em dois modos:

- **GUI Desktop** (`main.py`) — Tkinter, uso manual local
- **REST API** (`api/`) — FastAPI, consumida pelo frontend React

Há **dois pipelines de extracção** independentes que coexistem:

| Pipeline | Endpoint | Método | Quando usar |
|---|---|---|---|
| **Regex/OCR** (parsers) | `POST /facturas/extraer` (legado) | pdfplumber + regex + Ingebau | faturas de comercializadoras conhecidas |
| **Claude AI** | `POST /facturas/extraer` (principal) | Claude API (sonnet-4-6) + Zoho | produção — todos os casos |

O endpoint principal `POST /facturas/extraer` usa o pipeline Claude. O endpoint legado `POST /facturas/extraer-ai` também usa Claude mas sem Zoho/WorkDrive (endpoint mais simples).

---

## 2. Estrutura de Ficheiros

```
extractor-facturas-backend/
├── api/
│   ├── main.py                  # FastAPI app, CORS, registo de routers
│   ├── models.py                # Schemas Pydantic (ExtractionResponse, ExtractionResponseAI, IVABlock, ValidacionCuadre)
│   ├── claude/
│   │   ├── client.py            # Singleton cliente Anthropic
│   │   ├── extractor.py         # extract_with_claude() — chamada à API, parse JSON, build ExtractionResponseAI
│   │   └── prompts.py           # SYSTEM_PROMPT (carregado uma vez — prompt caching)
│   ├── routes/
│   │   ├── facturas.py          # POST /facturas/extraer (principal — Claude + Zoho + WorkDrive)
│   │   ├── facturas_ai.py       # POST /facturas/extraer-ai (simples — Claude sem Zoho)
│   │   ├── cups.py              # GET /cups/consultar (API Ingebau)
│   │   ├── enviar.py            # POST /enviar (proxy Zoho Flow)
│   │   ├── sesion.py            # POST/GET /sesion (store in-memory, TTL 40 min)
│   │   └── contrato.py          # POST /contrato/callback + GET /contrato/{dealId}
│   ├── zoho_crm.py              # buscar_deal_por_email(), buscar_mpklog_por_email()
│   └── zoho_workdrive.py        # upload_factura_files() — cria pasta + 5 ficheiros
├── extractor/
│   ├── __init__.py              # extract_from_pdf() — orquestração do pipeline regex
│   ├── base.py                  # ExtractionResult, helpers (norm, numeros, datas)
│   ├── detector.py              # Deteção de comercializadora por padrões regex
│   ├── api.py                   # Chamada à API Ingebau + seleção de período
│   ├── fields.py                # Definição dos 27 campos e metadados
│   └── parsers/
│       ├── __init__.py          # get_parser() — factory
│       ├── base_parser.py       # BaseParser — lógica genérica de extracção
│       ├── generic.py           # Fallback
│       ├── repsol.py
│       ├── octopus.py
│       ├── naturgy.py
│       ├── naturgy_regulada.py
│       ├── iberdrola.py
│       ├── endesa.py
│       ├── cox.py               # Usa PyMuPDF (layout 2 colunas)
│       ├── contigo.py
│       ├── energyavm.py
│       ├── energiaxxi.py
│       ├── pepeenergy.py
│       └── plenitude.py
├── main.py                      # GUI Desktop Tkinter
├── requirements.txt
├── .env / .env.example
├── CLAUDE.md                    # Instruções para o agente Claude Code
├── BACKEND.md                   # Documentação técnica completa do backend
├── log.md                       # Histórico de mudanças [001..027]
├── docs/
│   ├── extraccion_campos_claude.md   # Como Claude extrai/converte cada campo
│   └── superpowers/plans/            # Planos de implementação
└── resultados/                  # JSONs de saída (ignorado pelo git)
```

---

## 3. Stack Tecnológica

| Componente | Tecnologia |
|---|---|
| Linguagem | Python 3.13 |
| API Web | FastAPI + Uvicorn |
| GUI | Tkinter (nativo) |
| Validação | Pydantic v2 |
| AI Extracção | Anthropic Claude (`claude-sonnet-4-6`) |
| Extracção PDF (regex) | pdfplumber, PyMuPDF (fitz) |
| OCR | pytesseract + pdf2image + Pillow |
| HTTP Client | requests (síncrono), httpx (assíncrono) |
| Upload ficheiros | python-multipart |
| Integração CRM | Zoho CRM API v8 (EU) |
| Integração ficheiros | Zoho WorkDrive API v1 (EU) |
| Automação | Zoho Flow Webhook |

**Caminhos hardcoded Windows:**
- Tesseract: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Poppler: `C:\Users\ianro\AppData\Local\...\poppler-25.07.0\Library\bin`

---

## 4. Variáveis de Ambiente (`.env`)

```env
# API Ingebau
API_TOKEN=...
API_URL=http://13.39.57.137:8004/Cups

# Frontend CORS
FRONTEND_URL=http://localhost:5173
ALLOWED_ORIGINS=http://localhost:5173,...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...

# Zoho CRM
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
ZOHO_ACCESS_TOKEN=...
ZOHO_API_DOMAIN=https://www.zohoapis.eu
ZOHO_DEAL_FETCH_DELAY=4    # segundos de espera antes de buscar dealId

# Zoho WorkDrive
ZOHO_WORKDRIVE_ACCESS_TOKEN=...
ZOHO_WORKDRIVE_REFRESH_TOKEN=...
ZOHO_WORKDRIVE_FOLDER_ID=...   # ID da pasta pai no WorkDrive
```

---

## 5. Endpoints da API

### `GET /`
```json
{ "status": "ok", "version": "1.0.0" }
```

### `GET /health`
```json
{ "status": "ok", "service": "extractor-facturas" }
```

---

### `POST /facturas/extraer` — Principal

Upload de PDF → extracção Claude → sessão Zoho → WorkDrive.

**Request:** `multipart/form-data`
- `file`: ficheiro PDF (obrigatório)
- `data`: string JSON opcional com `{cliente, ce, Fsmstate, FsmPrevious}`

**Fluxo interno:**
1. Valida extensão `.pdf`
2. Lê bytes do PDF
3. Chama `extract_with_claude(pdf_bytes)` → `ExtractionResponseAI`
4. Imprime `_log_cuadre()` no terminal (desglose contabilístico completo)
5. Em paralelo busca `dealId` e `mpklogId` no Zoho CRM (por email do cliente, com retry)
6. Constrói `session_payload = {cliente, ce, Fsmstate, FsmPrevious, factura: _build_factura_payload(result), dealId, mpklogId}`
7. Cria sessão em `/sesion` → guarda `session_id` no `result`
8. Guarda JSON local em `resultados/{cups}_{inicio}_{fim}.json`
9. Agenda `upload_factura_files()` como fire-and-forget (asyncio.create_task)
10. Devolve `ExtractionResponseAI` (excluindo `api_ok`, `api_error`, `fichero_json`, `descuentos`)

**Response:** `ExtractionResponseAI` — ver secção 7

---

### `POST /facturas/extraer-ai` — Simples (sem Zoho)

Extracção Claude pura. Sem WorkDrive, sem Zoho CRM, sem sessão personalizada.

**Request:** `multipart/form-data`
- `file`: ficheiro PDF

**Fluxo:**
1. `extract_with_claude(pdf_bytes)`
2. Calcula `validacion_cuadre` (R13 — server-side)
3. Cria sessão simples com `result.model_dump()`
4. Guarda `resultados/{cups}_{inicio}_{fim}_ai.json`
5. Devolve `ExtractionResponseAI`

---

### `GET /cups/consultar?cups={codigo}`

Consulta dados do ponto de suministro na API Ingebau.

**Response:**
```json
{
  "tarifa_acceso": "2.0TD",
  "distribuidora": "Iberdrola Distribución Eléctrica",
  "pot_p1_kw": "3.3", "pot_p2_kw": "3.3",
  "pot_p3_kw": "0", "pot_p4_kw": "0", "pot_p5_kw": "0", "pot_p6_kw": "0",
  "consumo_p1_kwh": "150", "consumo_p2_kwh": "80",
  "consumo_p3_kwh": "0", "consumo_p4_kwh": "0",
  "consumo_p5_kwh": "0", "consumo_p6_kwh": "0",
  "dias_facturados": "31",
  "periodo_inicio": "01/01/2024",
  "periodo_fin": "31/01/2024"
}
```

---

### `POST /enviar` — Proxy Zoho Flow

Reenvia o payload ao webhook Zoho Flow e devolve `dealId`, `mpklogId`, `session_id`.

**Request:** `multipart/form-data`
- `data`: string JSON com `{cliente, factura, Fsmstate, FsmPrevious, ce, session_id?}`

**Fluxo:**
1. Envia JSON ao Zoho Flow webhook
2. Aguarda `ZOHO_DEAL_FETCH_DELAY` segundos
3. Busca `dealId` e `mpklogId` em paralelo (com retry automático até ~30s)
4. Se `session_id` presente no payload → usa factura da sessão Claude (se existir)
5. Actualiza ou cria sessão com `{...payload, factura, dealId, mpklogId}`

**Response:**
```json
{ "ok": true, "dealId": "...", "mpklogId": "...", "session_id": "..." }
```

---

### `POST /sesion` e `GET /sesion/{id}`

Store in-memory com TTL de 40 minutos.

- `POST /sesion` — cria sessão com qualquer `body`, devolve `{ "session_id": "uuid" }`
- `GET /sesion/{id}` — lê dados; 404 se não existe, 410 se expirada
- `actualizar_sesion(id, data)` — renova TTL e actualiza dados (usado por `/enviar`)

---

### `POST /contrato/callback` e `GET /contrato/{dealId}`

Callback do Zoho Sign. Quando um contrato é assinado, o webhook guarda `contractUrl` por `dealId`. O frontend lê e remove com GET.

---

## 6. Modelos Pydantic (`api/models.py`)

### `ExtractionResponse` — base (pipeline regex)

```python
cups, periodo_inicio, periodo_fin, comercializadora
pp_p1..pp_p6          # €/kW·dia
pe_p1..pe_p6          # €/kWh (null para períodos não facturados)
imp_ele               # IEE em % (ex: 5.11269632)
iva                   # IVA em % (int: 21 ou 10)
alq_eq_dia            # aluguer contador €/dia
bono_social           # importe total bono social €
descuentos            # dict (deprecated — migrado para otros.creditos)
importe_factura       # total da factura €
tarifa_acceso, distribuidora
pot_p1_kw..pot_p6_kw  # kW (da API Ingebau)
consumo_p1_kwh..consumo_p6_kwh  # kWh (da API Ingebau)
dias_facturados       # string (ex: "31")
api_ok, api_error, fichero_json  # metadados (excluídos da response)
```

### `IVABlock` — bloco IVA estruturado

Suporta IVA único ou fracionado (RDL 8/2023 com dois tipos):

```python
IVA_PERCENT_1, IVA_PERCENT_2              # tipos (int)
IVA_BASE_IMPONIBLE_1, IVA_BASE_IMPONIBLE_2  # bases €
IVA_SUBTOTAL_EUROS_1, IVA_SUBTOTAL_EUROS_2  # importes €
IVA_TOTAL_EUROS                            # soma total €
```

### `ValidacionCuadre` — reconciliação server-side

```python
cuadra: bool
importe_factura, suma_conceptos, diferencia_eur  # €
error: str | None
```

### `ExtractionResponseAI` — extende `ExtractionResponse` (pipeline Claude)

Campos adicionais:
```python
imp_ele_eur_kwh                    # IEE em €/kWh (post RDL 7/2026)
imp_termino_energia_eur            # subtotal energía €
imp_termino_potencia_eur           # subtotal potência €
imp_impuesto_electrico_eur         # subtotal IEE €
imp_alquiler_eur                   # subtotal aluguer €
imp_iva_eur                        # subtotal IVA €
impuesto_electricidad_importe      # = imp_impuesto_electrico_eur (alias)
alquiler_equipos_medida_importe    # = imp_alquiler_eur (alias)
IVA_TOTAL_EUROS                    # = IVA.IVA_TOTAL_EUROS
IVA: IVABlock                      # bloco estruturado
otros: dict                        # {costes, creditos, observacion}
margen_de_error: float             # % desvio (calculado pelo Claude)
validacion_cuadre: ValidacionCuadre  # calculado pelo servidor (extraer-ai)
session_id: str                    # UUID da sessão criada
```

---

## 7. Estrutura do Payload de Sessão

O `session_payload` enviado ao Zoho Flow e guardado na sessão tem esta estrutura:

```json
{
  "cliente": {
    "nombre": "...", "apellidos": "...", "correo": "...",
    "telefono": "...", "direccion": "...",
    "dealId": "123456789",
    "mpklogId": "987654321"
  },
  "ce": { "nombre": "...", "direccion": "...", "status": "Available", "etiqueta": "..." },
  "Fsmstate": "01_DENTRO_ZONA",
  "FsmPrevious": null,
  "factura": { ... },   // ver abaixo
  "dealId": "123456789",
  "mpklogId": "987654321"
}
```

### Estrutura de `factura` (produzida por `_build_factura_payload`)

```json
{
  // Identificação
  "cups": "ES0021000000000000AA",
  "comercializadora": "Iberdrola Clientes, S.A.U.",
  "distribuidora": "Iberdrola Distribución Eléctrica",
  "tarifa_acceso": "2.0TD",
  "periodo_inicio": "01/01/2024",
  "periodo_fin": "31/01/2024",
  "dias_facturados": "31",
  "importe_factura": 118.60,

  // Campos planos (retrocompatibilidade com cotizador)
  "pp_p1": 0.073783, "pp_p2": 0.073783, "pp_p3": null,
  "pp_p4": null, "pp_p5": null, "pp_p6": null,
  "pe_p1": 0.142855, "pe_p2": 0.142855, "pe_p3": 0.110000,
  "pe_p4": null, "pe_p5": null, "pe_p6": null,
  "pot_p1_kw": 3.3, "pot_p2_kw": 3.3,
  "pot_p3_kw": null, "pot_p4_kw": null, "pot_p5_kw": null, "pot_p6_kw": null,
  "consumo_p1_kwh": 107.0, "consumo_p2_kwh": 142.0, "consumo_p3_kwh": 510.0,
  "consumo_p4_kwh": null, "consumo_p5_kwh": null, "consumo_p6_kwh": null,
  "imp_ele": 5.11269632,
  "imp_ele_eur_kwh": null,
  "iva": 21,
  "alq_eq_dia": 0.020645,
  "bono_social": 0.15,

  // Novos campos raíz de importes
  "impuesto_electricidad_importe": 4.56,
  "alquiler_equipos_medida_importe": 0.64,
  "IVA_TOTAL_EUROS": 20.58,
  "IVA": {
    "IVA_PERCENT_1": 21, "IVA_PERCENT_2": null,
    "IVA_BASE_IMPONIBLE_1": 98.0, "IVA_BASE_IMPONIBLE_2": null,
    "IVA_SUBTOTAL_EUROS_1": 20.58, "IVA_SUBTOTAL_EUROS_2": null,
    "IVA_TOTAL_EUROS": 20.58
  },

  // Grupos aninhados (novos consumidores)
  "potencias_kw": { "p1": 3.3, "p2": 3.3, "p3": null, "p4": null, "p5": null, "p6": null },
  "consumos_kwh": { "p1": 107.0, "p2": 142.0, "p3": 510.0, "p4": null, "p5": null, "p6": null },
  "precios_potencia": { "p1": 0.073783, "p2": 0.073783, "p3": null, "p4": null, "p5": null, "p6": null },
  "precios_energia": { "pe_p1": 0.142855, "pe_p2": 0.142855, "pe_p3": 0.110000, "pe_p4": null, "pe_p5": null, "pe_p6": null },
  "impuestos": {
    "imp_ele": 5.11269632,
    "imp_ele_eur_kwh": null,
    "iva": 21,
    "IVA": { ... }
  },

  // Otros conceptos estruturados
  "otros": {
    "alq_eq_dia": 0.020645,         // retrocompat
    "cuotaAlquilerMes": null,        // calculado pelo frontend
    "costes": {
      "bono_social_importe": 0.15,
      "exceso_potencia_importe": null,
      "alquiler_equipos_medida_importe": 0.64,
      "coste_energia_reactiva": null
    },
    "creditos": {
      "compensacion_excedentes_kwh": null,
      "compensacion_excedentes_importe": null
      // + descontos nomeados, sempre negativos
    },
    "observacion": ["pp_p* convertido de €/kW/año a €/kW/día dividiendo por 365"]
  },

  "margen_de_error": 0.83
}
```

### Regras de `otros` por comercializadora

| Comercializadora | `costes` notável | `creditos` notável | `observacion` |
|---|---|---|---|
| 2.0TD base | `bono_social_importe`, `alquiler_equipos_medida_importe` | vazio | vazio ou conversão pp |
| 3.0TD (Cox, Quantium) | + `exceso_potencia_importe`, `coste_energia_reactiva` | vazio | conversão pp |
| Iberdrola autoconsumo | base | `compensacion_excedentes_kwh`, `compensacion_excedentes_importe` | "Compensacion excedentes detectada" |
| Iberdrola IVA fracionado | base | vazio | "IVA fraccionado: 21% + 10%" |
| Cox Energy (N contadores) | `alquiler_equipos_medida_importe` = N × individual | vazio | "Alquiler con N contadores: ..." |
| Octopus | base | descontos | "Octopus: Punta=P1, Llano=P2, Valle=P3" |

---

## 8. Pipeline Claude AI

### Arquitectura do Prompt

```
SYSTEM_PROMPT = _PREAMBLE + "\n\n" + prompt_lectura_factura.md
```

- `_PREAMBLE` (`api/claude/prompts.py`): regras de precisão, zeros vs null, estrutura `otros`, bloco `IVA`, campos obrigatórios, validação de cuadre, conversão pp_p*, regras por comercializadora
- `prompt_lectura_factura.md` (`.claude/skills/leer-factura/`): estrutura da factura, blocos 1–20, regras R1–R13, schema JSON completo

O prompt é carregado **uma vez** ao arrancar o servidor (`SYSTEM_PROMPT = get_system_prompt()` a nível de módulo) para activar o **prompt caching** da Anthropic.

### Chamada à API (`api/claude/extractor.py`)

```python
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
```

- PDF enviado em base64 como `document` (media_type `application/pdf`)
- System prompt com `cache_control: {"type": "ephemeral"}`
- Resposta: bloco ````json```` — parseado por `_parse_json_from_text()`
- `_build_response()`: filtra chaves desconhecidas, converte `otros`/`descuentos` string→dict, converte `IVA` dict→`IVABlock`

### Validação de Cuadre (feita pelo Claude)

Claude executa antes de devolver o JSON:
```
soma = imp_termino_potencia_eur
     + imp_termino_energia_eur
     + imp_impuesto_electrico_eur
     + imp_alquiler_eur
     + imp_iva_eur
     + sum(otros.costes, excl. alquiler e bono já contados)
     + sum(otros.creditos, negativos)

margen_de_error = |soma - importe_factura| / importe_factura × 100
```
Se `margen_de_error > 5%` → Claude relê a factura e corrige. Devolve sempre o valor final.

### Log do Cuadre no Terminal (`_log_cuadre`)

Após cada extracção, o terminal mostra um desglose completo:
```
  ┌────────────────────────────────────────────────────────────────────┐
  │           CUADRE CONTABLE — DESGLOSE COMPLETO                      │
  ├────────────────────────────────────────────────────────────────────┤
  │  POTENCIA                                                          │
  ├────────────────────────────────────────────────────────────────────┤
  │      Potencia P1          6.9 kW × 31d × 0.073783    +15.79 €     │
  │      Potencia P2          6.9 kW × 31d × 0.073783    +15.79 €     │
  │      SUBTOTAL potencia (Claude) imp_termino_potencia  +24.87 €     │
  ...
  │  OTROS CONCEPTOS                                                   │
  │      costes.bono_social_importe  otros.costes         +0.15 €      │
  │      creditos.descuento_10pct    otros.creditos       -10.41 €     │
  ...
  │  ✅  Margen error servidor                            +0.83 %      │
  │  ✅  Margen error Claude                              +0.83 %      │
  └────────────────────────────────────────────────────────────────────┘
```

### Conversões de Unidades (pp_p*)

| Caso | Regra | Exemplo |
|---|---|---|
| €/kW·ano | ÷ 365 | 26.930550 / 365 = 0.073783 |
| €/kW·mês | ÷ dias_facturados | 2.24450 / 31 = 0.072403 |
| €/kW·dia | sem conversão | 0.073783 |
| sem unidade | assume €/kW·ano ÷ 365 | |
| Sub-períodos (Energía XXI) | média ponderada por dias | (0.0448×15 + 0.0512×16) / 31 |

---

## 9. Integração Zoho CRM (`api/zoho_crm.py`)

- `buscar_deal_por_email(correo)` — busca em `Deals` por `Correo_electr_nico1`
- `buscar_mpklog_por_email(correo)` — busca em `MPK_Logs` por `Email`
- Ambas com retry automático: 3 tentativas com delays [5s, 10s, 15s]
- Token refresh automático em 401 (usa `ZOHO_REFRESH_TOKEN`)
- Usados em `POST /facturas/extraer` e `POST /enviar`

---

## 10. Integração Zoho WorkDrive (`api/zoho_workdrive.py`)

Após cada extracção, sobe 4–5 ficheiros para WorkDrive (fire-and-forget):

| Ficheiro | Conteúdo |
|---|---|
| `{nomedopdf}.pdf` | PDF original |
| `{nomedopdf}_claudeDatosBrutos.json` | `result.model_dump()` (ExtractionResponseAI) |
| `{nomedopdf}_claudeDatosTratados.json` | `session_payload["factura"]` (payload tratado) |
| `{nomedopdf}_datosEnviadosalCotizador.json` | `session_payload` completo |
| `parser_{nomedopdf}.json` | resultado do pipeline regex (BaseParser) — opcional |

Pasta criada: `{nomedopdf}_{tarifa_acceso}` dentro de `ZOHO_WORKDRIVE_FOLDER_ID`.

Token WorkDrive separado do CRM (`ZOHO_WORKDRIVE_REFRESH_TOKEN`). Refresh automático em 401 ou código de erro F7003 (Zoho devolve 500 para token expirado).

---

## 11. Pipeline Regex/OCR (legado — `extractor/`)

Usado pelo WorkDrive para gerar `parser_{nomedopdf}.json` e pela GUI desktop.

```
PDF
 └─ pdfplumber → texto (fallback OCR Tesseract se vazio)
     └─ _corregir_cups(): O→0 nos primeiros 20 chars do CUPS
         └─ detector.detectar() → id da comercializadora
             └─ get_parser(id, text, pdf_path) → parser específico
                 ├─ parse() → campos do PDF (cups, pp_p*, pe_p*, imp_ele, iva, alq_eq_dia)
                 ├─ extraer_potencias_contratadas() → pot_p*_kw
                 └─ extraer_consumos() → consumo_p*_kwh
                     └─ llamar_api(cups, fields, ...) → Ingebau
                         └─ ExtractionResult(fields, raw_matches, api_ok, api_error)
```

### Comercializadoras suportadas

| ID | Ficheiro | Particularidade |
|---|---|---|
| `repsol` | `repsol.py` | preço único pe_p1 |
| `naturgy` | `naturgy.py` | remove separadores de milhares |
| `naturgy_regulada` | `naturgy_regulada.py` | comercializadora regulada |
| `iberdrola` | `iberdrola.py` | extraer_consumos() para 2.0TD e 3.0TD |
| `endesa` | `endesa.py` | |
| `octopus` | `octopus.py` | Punta/Llano/Valle → P1/P2/P3 |
| `cox` | `cox.py` | PyMuPDF (layout 2 colunas), pp_p3..p6 |
| `energyavm` | `energyavm.py` | formato `P1: X kWh, Precio: Y €/kWh` |
| `contigo` | `contigo.py` | sem €/kWh explícito |
| `pepeenergy` | `pepeenergy.py` | €/kW·mês |
| `plenitude` | `plenitude.py` | preço único Consumo Fácil |
| `energiaxxi` | `energiaxxi.py` | sub-períodos com média ponderada |
| `generic` | `generic.py` | fallback sem adaptações |

---

## 12. Store de Sessões (`api/routes/sesion.py`)

Store in-memory (dict Python) — **não persistido entre reinicios**.

```python
_store: dict[str, { "data": Any, "expires_at": datetime }]
_TTL_MINUTES = 40
```

- `crear_sesion(data)` → UUID
- `leer_sesion(id)` → data | None (apaga se expirada)
- `actualizar_sesion(id, data)` → bool (renova TTL)

**Ciclo de vida da sessão num fluxo completo:**
1. `POST /facturas/extraer` → cria sessão com `{cliente, ce, Fsmstate, factura, dealId, mpklogId}` → devolve `session_id`
2. `POST /enviar` com `session_id` → lê factura Claude da sessão, actualiza com `dealId`/`mpklogId` finais
3. `GET /sesion/{id}` — frontend lê dados completos para pré-preencher cotizador

---

## 13. Campos por Fonte

| Campo | Fonte | Unidade |
|---|---|---|
| `cups` | PDF (parser/Claude) | string ES... |
| `comercializadora`, `distribuidora` | PDF/Claude | texto |
| `tarifa_acceso` | PDF/Claude ou Ingebau | ex: "2.0TD" |
| `periodo_inicio`, `periodo_fin` | PDF/Claude | DD/MM/YYYY |
| `dias_facturados` | PDF/Claude ou Ingebau | string "31" |
| `importe_factura` | PDF/Claude | € decimal |
| `pp_p1..pp_p6` | PDF/Claude | €/kW·**dia** (convertido) |
| `pe_p1..pe_p6` | PDF/Claude | €/kWh (sem conversão) |
| `imp_ele` | PDF/Claude | % float (ex: 5.11269632) |
| `imp_ele_eur_kwh` | Claude (post RDL 7/2026) | €/kWh |
| `iva` | PDF/Claude | % int (21 ou 10) |
| `alq_eq_dia` | PDF/Claude | €/dia |
| `bono_social` | Claude | € (importe total) |
| `descuentos` | Claude (deprecated) | dict nome→€ |
| `pot_p1_kw..pot_p6_kw` | Ingebau (ou PDF se disponível) | kW |
| `consumo_p1_kwh..consumo_p6_kwh` | Ingebau (ou PDF) | kWh |
| `imp_termino_*_eur` | Claude (subtotais €) | € |
| `IVA` | Claude | IVABlock |
| `otros.costes` | Claude | dict nome→€ (positivos) |
| `otros.creditos` | Claude | dict nome→€ (negativos) |
| `otros.observacion` | Claude | lista strings |
| `margen_de_error` | Claude (auto-validação) | % |
| `validacion_cuadre` | Servidor (extraer-ai) | ValidacionCuadre |
| `session_id` | Servidor | UUID |

---

## 14. Decisões de Design Importantes

**Por que dois pipelines?**
O pipeline regex existe desde o início e serve como fallback/validação. O Claude é o pipeline principal em produção. O WorkDrive gera ambos os JSONs para comparação.

**Por que `SYSTEM_PROMPT` é carregado a nível de módulo?**
Para activar o prompt caching da Anthropic — o texto deve ser byte-idêntico entre chamadas. Carregar em cada request invalidaria o cache.

**Por que `otros` como dict e não campos separados?**
Conceitos não-standard variam muito entre comercializadoras. `otros.costes/creditos` permite capturar qualquer conceito sem mudar o schema Python.

**Por que `descuentos` mantido no modelo mas excluído da response?**
Backward-compat: Claude antigo pode ainda preencher `descuentos`. O servidor migra automaticamente para `otros.creditos` se `creditos` estiver vazio. O campo é excluído via `_EXCLUDE` da response da API.

**Por que zeros vs null é crítico?**
O cotizador usa `null` para detectar períodos inexistentes na tarifa (ex: 2.0TD não tem P3..P6). Se Claude devolver `0.0`, o cotizador tentaria calcular com potência/energia zero, gerando cotizações erradas.

**WorkDrive é fire-and-forget:**
Erros de upload não afectam a resposta ao frontend. Todos os erros são logados no terminal.

**Zoho CRM tem retry com backoff:**
O Zoho Flow leva alguns segundos a criar o deal após receber o webhook. O retry [5s, 10s, 15s] acomoda esta latência.

---

## 15. Arrancar o Servidor

```bash
# Instalar dependências
pip install -r requirements.txt

# Variáveis de ambiente
cp .env.example .env
# editar .env com tokens reais

# Arrancar
py -3.13 -m uvicorn api.main:app --port 8000 --reload

# Swagger UI
# http://localhost:8000/docs
```

---

## 16. Adicionar Nova Comercializadora (Pipeline Regex)

1. Criar `extractor/parsers/{nome}.py` (subclasse de `BaseParser`)
2. Registar em `extractor/parsers/__init__.py` (dicionário de parsers)
3. Adicionar padrão regex em `extractor/detector.py` (`_PATRONES`)

O Claude não precisa de alterações — aprende automaticamente de qualquer comercializadora.
