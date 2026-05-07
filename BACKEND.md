# BACKEND.md — Extractor Facturas Luz (Backend)

Repositório: `extractor-facturas-backend`
Stack: Python 3.x + FastAPI + Uvicorn

---

## Estrutura do Repositório

```
extractor-facturas-backend/
├── api/
│   ├── main.py              # FastAPI app, CORS, migrações Alembic no startup, registo de routers
│   ├── models.py            # Schema Pydantic ExtractionResponse (27 campos)
│   ├── db/
│   │   ├── database.py      # Engine SQLAlchemy, SessionLocal, Base, DATABASE_URL do env
│   │   ├── models.py        # ORM model SessionRecord (tabela sessions)
│   │   └── repository.py    # db_save_session, db_get_session, db_update_session
│   ├── utils/
│   │   ├── __init__.py      # pacote utils
│   │   └── geo.py           # simplify_address(), geocode_address() via Nominatim
│   └── routes/
│       ├── facturas.py      # POST /facturas/extraer (pipeline multi-agente Claude)
│       ├── facturas_ai.py   # POST /facturas/extraer-ai (legado — Claude direto, sem pipeline)
│       ├── cups.py          # GET /cups/consultar
│       ├── enviar.py        # POST /enviar (proxy Zoho Flow)
│       └── sesion.py        # POST/GET/PATCH /sesion — dual-layer memória+SQLite
├── alembic/                 # Migrações versionadas
│   └── versions/787deedd37e0_create_sessions_table.py
├── alembic.ini              # Config Alembic (DATABASE_URL via env)
├── data/                    # SQLite DB em produção (volume Docker)
├── extractor/
│   ├── __init__.py          # Orquestração do pipeline: extract_from_pdf()
│   ├── base.py              # ExtractionResult, helpers (norm, numeros, datas, log)
│   ├── detector.py          # Deteção de comercializadora por regex
│   ├── api.py               # Chamada à API Ingebau + seleção de período
│   ├── fields.py            # Definição dos campos (metadados)
│   └── parsers/
│       ├── __init__.py      # get_parser() — factory de parsers
│       ├── base_parser.py   # BaseParser — lógica genérica de extração
│       ├── generic.py       # Parser de fallback (sem comercializadora reconhecida)
│       ├── repsol.py
│       ├── octopus.py
│       ├── naturgy.py
│       ├── naturgy_regulada.py
│       ├── iberdrola.py
│       ├── endesa.py
│       ├── cox.py           # PyMuPDF (layout 2 colunas)
│       ├── contigo.py
│       ├── energyavm.py
│       ├── pepeenergy.py
│       └── plenitude.py
├── main.py                  # GUI Desktop Tkinter (uso manual)
├── requirements.txt
├── .env / .env.example
└── resultados/              # JSONs de saída (ignorado pelo git)
```

---

## Dependências (`requirements.txt`)

| Biblioteca | Propósito |
|-----------|-----------|
| `pdfplumber` | Extração de texto de PDFs nativos (layer de texto) |
| `pymupdf` (fitz) | Extração de PDFs com layout em colunas (Cox Energía) |
| `pytesseract` | OCR via Tesseract — fallback para PDFs baseados em imagem |
| `pdf2image` | Converte páginas PDF em imagens para o OCR |
| `pillow` | Manipulação de imagens (dependência do pdf2image/pytesseract) |
| `fastapi` | Framework web para a REST API |
| `uvicorn[standard]` | Servidor ASGI para FastAPI |
| `python-multipart` | Suporte a upload de ficheiros (multipart/form-data) |
| `pydantic` | Validação e serialização dos schemas de resposta |
| `requests` | Chamadas síncronas à API Ingebau (extractor/api.py, cups.py) |
| `httpx` | Chamadas assíncronas ao webhook Zoho Flow (enviar.py) |
| `python-dotenv` | Carrega variáveis do ficheiro `.env` |
| `sqlalchemy` | ORM para acesso ao SQLite — sem SQL raw espalhado |
| `alembic` | Migrações versionadas do schema da base de dados |

**Ferramentas externas (caminhos hardcoded para Windows):**
- Tesseract OCR: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Poppler: `C:\Users\ianro\AppData\Local\...\poppler-25.07.0\Library\bin`
- Em Linux/produção o Poppler é encontrado automaticamente no PATH.

---

## Variáveis de Ambiente (`.env`)

```env
API_TOKEN=your_token_here
API_URL=http://13.39.57.137:8004/Cups
FRONTEND_URL=http://localhost:5173
```

| Variável | Usada em | Propósito |
|----------|----------|-----------|
| `API_TOKEN` | `extractor/api.py`, `api/routes/cups.py` | Autenticação na API Ingebau |
| `API_URL` | `extractor/api.py`, `api/routes/cups.py` | Endpoint da API Ingebau |
| `ALLOWED_ORIGINS` | `api/main.py` | Origens CORS permitidas (default: localhost:5173, localhost:3000, amplify) |
| `DATABASE_URL` | `api/db/database.py` | URL SQLAlchemy. Default: `sqlite:///./sessions.db`. Docker: `sqlite:////app/data/sessions.db` |

> `CALC_BACKEND_URL` foi **removida** — o `/enviar` já não faz forward para backend de cálculo.

---

## Endpoints da API

### `GET /`
```
Resposta: { "status": "ok", "version": "1.0.0" }
```

### `GET /health`
```
Resposta: { "status": "ok", "service": "extractor-facturas" }
```

---

### `POST /sesion`

**Propósito:** Cria sessão temporária com payload JSON. Guarda em memória (40min TTL) + SQLite (permanente).

**Request:**
```
Content-Type: application/json
Body: qualquer JSON (cliente, factura, Fsmstate, etc.)
```

**Resposta (200):**
```json
{ "session_id": "550e8400-e29b-41d4-a716-446655440000" }
```

---

### `GET /sesion/{session_id}`

**Propósito:** Lê sessão. Memória primeiro → fallback SQLite se expirada ou após restart.

**Resposta (200):** payload JSON completo (inclui `facturaPreview` após PATCH do cotizador)

**Erros:** 404 (não encontrada ou expirada sem DB)

---

### `PATCH /sesion/{session_id}`

**Propósito:** Merge parcial do body JSON nos dados existentes. Renova TTL em memória. Persiste no SQLite.

**Request:**
```json
{
  "facturaPreview": { "periodo": "Enero 2025", "dias": 31, ... },
  "url": "https://master.dsg7um3zm296x.amplifyapp.com/?...&session_id=XXX",
  "ahorro_anual": 281.24
}
```

**Resposta (200):** `{ "ok": true }`

**Erros:** 404 (não encontrada)

---

### `POST /facturas/extraer`

**Propósito:** Recebe PDF de fatura elétrica, extrai campos via pipeline multi-agente Claude, geocodifica endereço de suministro, cria sessão e devolve dados estruturados.

**Request:**
```
Content-Type: multipart/form-data
Campo: "file" — ficheiro PDF (obrigatório)
Campo: "data" — JSON opcional: {"cliente": {...}, "ce": {...}, "Fsmstate": "...", "FsmPrevious": "..."}
```

**Processamento interno:**
1. Valida extensão `.pdf`
2. Chama `extract_with_claude(pdf_bytes)` — pipeline multi-agente (Stage 1 Opus + 4 mappers Sonnet)
3. Geocodifica `direccion_suministro` via Nominatim → `suministro_lat`, `suministro_lon`
4. Busca `dealId`/`mpklogId` no Zoho CRM pelo `correo` (se fornecido em `data`)
5. Cria sessão com payload completo (`factura`, `cliente`, `ce`, `dealId`, `mpklogId`, `extractor_url`)
6. Guarda JSON local em `resultados/{cups}_{inicio}_{fim}.json`
7. Upload assíncrono para WorkDrive (non-blocking)
8. Devolve `ExtractionResponseAI`

**Resposta (200) — campos principais:**
```json
{
  "cups": "ES0022000008401855LB1P",
  "periodo_inicio": "05/10/2025",
  "periodo_fin": "05/11/2025",
  "comercializadora": "TotalEnergies Clientes, S.A.U.",
  "nombre_cliente": "MARIA VANESA SANCHES PEREZ",
  "direccion_suministro": "CL DAMASO ALONSO 14, 3º, B ILLESCAS - TOLEDO",
  "suministro_lat": 40.1209488,
  "suministro_lon": -3.8554211,
  "pp_p1": 0.103156,
  "pe_p1": 0.224778,
  "imp_termino_potencia_eur": 11.03,
  "imp_termino_energia_eur": 29.67,
  "imp_impuesto_electrico_eur": 1.99,
  "imp_alquiler_eur": 0.83,
  "imp_iva_eur": 8.79,
  "importe_factura": 59.12,
  "margen_de_error": 3.16,
  "IVA": { "IVA_PERCENT_1": 21, "IVA_BASE_IMPONIBLE_1": 41.84, "IVA_SUBTOTAL_EUROS_1": 8.79, "IVA_TOTAL_EUROS": 8.79 },
  "otros": {
    "importes_totalizados": { "precio_final_energia_activa": 29.67, "precio_final_potencia": 11.03, "total_factura": 59.12, ... },
    "costes": { "bono_social_importe": 0.4, "servicio_facilita_importe": 7.02, ... },
    "creditos": { "descuento_consumo_7": -2.08 },
    "observacion": ["...raciocínio Claude..."]
  },
  "tarifa_acceso": "2.0TD",
  "distribuidora": "UNION FENOSA DISTRIBUCION, S.A.",
  "pot_p1_kw": 3.45,
  "consumo_p1_kwh": 132,
  "dias_facturados": "31",
  "session_id": "55c9f4fb-cd2e-4bd3-a73d-ff19c0c5603e"
}
```

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | Ficheiro não termina em `.pdf` ou `data` não é JSON válido |
| 502 | Erro na API Claude |
| 504 | Timeout na API Claude |
| 500 | Erro interno no processamento |

---

### `POST /facturas/extraer-ai` *(legado)*

Endpoint alternativo — usa `extract_with_claude` directamente (sem pipeline multi-agente). Aplica reconciliação R13 e geocodifica. Preferir `/facturas/extraer` para uso novo.

---

### `GET /cups/consultar?cups={codigo}`

**Propósito:** Consulta dados do ponto de fornecimento e consumos históricos na API Ingebau.

**Request:**
```
Query param: cups=ES0021000000000000AA
```

**Processamento interno:**
1. Valida que `cups` não está vazio
2. GET à API Ingebau: `{API_URL}?cups={cups}&token={API_TOKEN}` (timeout 15s)
3. Verifica `data.result == "ok"`
4. Extrai dados de `data.ps[0]` (ponto de suministro)
5. Extrai dados de `data.consumos[0]` (período mais recente)
6. Calcula `dias_facturados` e datas do período

**Resposta (200):**
```json
{
  "tarifa_acceso": "2.0TD",
  "distribuidora": "Iberdrola Distribución Eléctrica",
  "pot_p1_kw": "3.3",
  "pot_p2_kw": "3.3",
  "pot_p3_kw": "0",
  "pot_p4_kw": "0",
  "pot_p5_kw": "0",
  "pot_p6_kw": "0",
  "consumo_p1_kwh": "150",
  "consumo_p2_kwh": "80",
  "consumo_p3_kwh": "0",
  "consumo_p4_kwh": "0",
  "consumo_p5_kwh": "0",
  "consumo_p6_kwh": "0",
  "dias_facturados": "31",
  "periodo_inicio": "01/01/2024",
  "periodo_fin": "31/01/2024"
}
```

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | CUPS vazio ou API Ingebau devolveu erro |
| 404 | CUPS não encontrado na API |
| 503 | Erro de conexão com a API Ingebau |
| 504 | Timeout na API Ingebau |
| 500 | Erro inesperado |

---

### `POST /enviar`

**Propósito:** Valida o payload JSON e faz proxy para o webhook Zoho Flow.

**Request:**
```
Content-Type: multipart/form-data
Campo "data": string JSON com a seguinte estrutura:
```
```json
{
  "cliente": {
    "nombre": "João",
    "apellidos": "Silva",
    "correo": "joao@email.com",
    "telefono": "+34 600 123 456",
    "direccion": "Calle Mayor 1, Madrid"
  },
  "factura": {
    "cups": "ES0021000000000000AA",
    "comercializadora": "Iberdrola",
    "distribuidora": "...",
    "tarifa_acceso": "2.0TD",
    "periodo_inicio": "01/01/2024",
    "periodo_fin": "31/01/2024",
    "dias_facturados": 31,
    "potencias_kw": { "p1": 3.3, "p2": 3.3, "p3": null, ... },
    "consumos_kwh": { "p1": 150, "p2": 80, "p3": null, ... },
    "precios_potencia": { "p1": 0.123, "p2": 0.067, ... },
    "impuestos": { "imp_ele": 5.11, "iva": 21 },
    "otros": { "alq_eq_dia": 0.052 },
    "api": { "api_ok": true, "api_error": "" }
  },
  "Fsmstate": "01_DENTRO_ZONA",
  "FsmPrevious": null,
  "ce": {
    "nombre": "CE Comunidad Solar",
    "direccion": "Calle Ejemplo 1, Madrid",
    "status": "Available",
    "etiqueta": "label"
  }
}
```

**Processamento interno:**
1. Faz parse do campo `data` como JSON
2. Verifica que `cliente` está presente
3. **Substitui `factura` pela versão Claude da sessão** (se `session_id` presente e sessão existir com `factura`)
4. Injeta `nombre_cliente`, `direccion_suministro`, `suministro_lat`, `suministro_lon` na `factura` (via `setdefault`)
5. POST ao webhook Zoho Flow (timeout 30s) com JSON enriquecido
6. Tenta obter `dealId`/`mpklogId` via `continuar_session_id` (callback Zoho) ou fallback CRM (espera 4s)
7. Actualiza ou cria sessão com `dealId`/`mpklogId`
8. Devolve `{"ok": true, "dealId": "...", "mpklogId": "...", "session_id": "..."}`

**Destino do reenvio:**
```
POST https://flow.zoho.eu/20067915739/flow/webhook/incoming
     ?zapikey=...&isdebug=false
Content-Type: application/json
Body: <parsed JSON>
```

**Resposta (200):**
```json
{ "ok": true, "dealId": "230641000184606105", "mpklogId": "230641000185853200", "session_id": "..." }
```

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | `data` não é JSON válido ou falta campo `cliente` |
| 503 | Erro de conexão com Zoho Flow |
| 504 | Timeout em Zoho Flow |
| 502 | Zoho Flow devolveu erro HTTP |

> **Nota:** O campo `file` (PDF) e o forward para `CALC_BACKEND_URL` foram **removidos**. O `/enviar` aceita apenas o campo `data`. A `factura` enviada ao Zoho é a versão Claude (com `otros.importes_totalizados`), não a flat do frontend.

---

## Pipeline de Extração (`extractor/`)

```
PDF (ficheiro temporário)
  │
  ├─ [1] pdfplumber.open() → extrai texto página a página
  │       Se texto vazio → fallback OCR (pdf2image + Tesseract)
  │       Se OCR usado → corrigir CUPS (O→0 em posições numéricas)
  │
  ├─ [2] detector.detectar(text) → identifica comercializadora por regex
  │       Devolve: "repsol" | "naturgy" | "iberdrola" | "endesa" |
  │                "octopus" | "cox" | "energyavm" | "contigo" |
  │                "naturgy_regulada" | "pepeenergy" | "plenitude" | "generic"
  │
  ├─ [3] get_parser(id, text, pdf_path) → instancia parser específico
  │       parser.parse() → extrai campos do PDF:
  │         cups, periodo_inicio, periodo_fin, comercializadora,
  │         pp_p1..pp_p6, pe_p1..pe_p6 (só períodos presentes),
  │         imp_ele, iva, alq_eq_dia
  │
  ├─ [4] llamar_api(cups, fields, raw, periodo_inicio, periodo_fin)
  │       GET API Ingebau → completa 18 campos adicionais:
  │         tarifa_acceso, distribuidora,
  │         pot_p1_kw..pot_p6_kw (6 campos),
  │         consumo_p1_kwh..consumo_p6_kwh (6 campos),
  │         dias_facturados, [periodo_inicio, periodo_fin se vazios]
  │
  └─ [5] Devolve ExtractionResult(fields, raw_matches, api_ok, api_error)
```

---

## Deteção de Comercializadora (`extractor/detector.py`)

Regex aplicadas ao texto completo do PDF (case-insensitive):

| Pattern | ID devolvido |
|---------|-------------|
| `repsol\s+comercializadora` | `repsol` |
| `naturgy\s+iberia` | `naturgy` |
| `iberdrola\s+clientes` | `iberdrola` |
| `endesa\s+energ[ií]a` | `endesa` |
| `octopus\s+energy\s+espa[ñn]a` | `octopus` |
| `cox\s+energ[ií]a\s+comercializadora` | `cox` |
| `en[eé]rgya[\s\-]*vm` | `energyavm` |
| `contigo\s*energ[ií]a\|gesternova` | `contigo` |
| `comercializadora\s+regulada\|gas\s*&\s*power` | `naturgy_regulada` |
| `pepe\s*energy\|energ[ií]a\s+colectiva` | `pepeenergy` |
| `plenitude\|eni\s+plenitude` | `plenitude` |
| *(nenhum match)* | `generic` |

---

## Arquitetura dos Parsers (`extractor/parsers/`)

### `BaseParser` — lógica genérica

Cada método de extração suporta múltiplos padrões para cobrir variações entre comercializadoras:

| Método | Campo(s) extraído(s) | Abordagem |
|--------|---------------------|-----------|
| `extraer_cups()` | `cups` | Regex `ES[0-9]{16-20}[A-Z0-9]{0-4}` (junto ou com espaços) |
| `extraer_periodo()` | `periodo_inicio`, `periodo_fin` | 4 padrões regex de datas (DD/MM/YYYY, DD-MM-YYYY, etc.) |
| `extraer_comercializadora()` | `comercializadora` | 5 padrões regex com nome legal completo |
| `extraer_precios_potencia()` | `pp_p1`, `pp_p2` | 5 formatos: Octopus, Repsol/Iberdrola, Endesa, Naturgy, genérico sequencial |
| `extraer_precios_energia()` | `pe_p1`..`pe_p6` | 4 padrões por prioridade: preço único, `P1 Y €/kWh`, `Energía P1 ... €/kWh`, fallback sequencial |
| `extraer_imp_ele()` | `imp_ele` | 5 formatos: `X% s/BASE`, `BASE x X%`, `BASE € X%`, genérico, fator decimal (Naturgy) |
| `extraer_iva()` | `iva` | 3 padrões; guarda o valor mais alto (evita capturar 10% do bono social) |
| `extraer_alquiler()` | `alq_eq_dia` | `N dias x Y €/dia`, sequência numérica, fallback: total ÷ dias |

### Parsers específicos (subclasses)

| Parser | Diferença face ao BaseParser |
|--------|------------------------------|
| `cox.py` | Usa PyMuPDF (`fitz`) — layout em 2 colunas; extrai `pp_p3..pp_p6` e `pe_p*` via fitz |
| `octopus.py` | `extraer_precios_energia()`: linhas `Punta/Llano/Valle X kWh Y €/kWh` → pe_p1/p2/p3 |
| `energyavm.py` | `extraer_precios_potencia()`: filtra `€/kW/día`; `extraer_precios_energia()`: padrão `P1: X kWh, Precio: Y €/kWh` |
| `contigo.py` | `extraer_precios_energia()`: coluna numérica sem `€/kWh` explícito |
| `plenitude.py` | `extraer_precios_energia()`: `Consumo Fácil ... Y €/kWh` → pe_p1 (preço único) |
| `naturgy.py` | Pré-processa texto removendo separadores de milhares (`.`) |
| `naturgy_regulada.py` | Variante da Naturgy para comercializadora regulada |
| `generic.py` | Sem adaptações — usa BaseParser puro como fallback |
| Restantes | Sobrepõem apenas os métodos necessários |

### Fallback OCR

Ativado quando `pdfplumber` não extrai texto suficiente:
1. `pdf2image.convert_from_path(pdf_path, dpi=300)` — converte páginas em imagens
2. `pytesseract.image_to_string(page, lang="spa")` — OCR em espanhol
3. `_corregir_cups()` — substitui `O→0` nos primeiros 20 caracteres do CUPS (`ES` + 18 dígitos)

---

## Integração com API Ingebau (`extractor/api.py`)

**Endpoint:** `GET {API_URL}?cups={cups}&token={API_TOKEN}`

**Campos extraídos de `data.ps[0]`:**

| Campo API Ingebau | Campo interno |
|------------------|--------------|
| `TarifaATR` | `tarifa_acceso` |
| `NombreDistribuidora` | `distribuidora` |
| `PotenciaContratadaP1kW`..`P6kW` | `pot_p1_kw`..`pot_p6_kw` |

**Campos extraídos de `data.consumos[período selecionado]`:**

| Campo API Ingebau | Campo interno |
|------------------|--------------|
| `EnergiaActivaP1(kWh)`..`P6(kWh)` | `consumo_p1_kwh`..`consumo_p6_kwh` |
| `LecturaDesde` / `LecturaHasta` | `dias_facturados`, `periodo_inicio`/`fin` (fallback) |

**Seleção do período (`seleccionar_consumo`):**
1. Correspondência exata: `LecturaDesde == periodo_inicio && LecturaHasta == periodo_fin`
2. Correspondência aproximada: menor soma de diferenças de dias
3. Se melhor match > 15 dias de diferença → usa o mais recente (`consumos[0]`)
4. Se sem período no PDF → usa o mais recente diretamente

**Fallbacks da chamada API:**
| Situação | Comportamento |
|----------|--------------|
| CUPS vazio | Não chama a API; `api_ok=False`, `api_error="CUPS no encontrado"` |
| `result != "ok"` | `api_ok=False`, `api_error=<mensagem da API>` |
| `ps` vazio | `api_ok=False`, `api_error="La API no devolvió datos de PS"` |
| Nenhum período correspondente | `api_ok=True`, `api_error="Ningún período..."` (campos de consumo ficam vazios) |
| Erro de conexão | `api_ok=False`, `api_error="Error de conexión"` |
| Timeout (15s) | `api_ok=False`, `api_error="Timeout en la llamada"` |

---

## Schema de Resposta (`api/models.py`)

`ExtractionResponse` (Pydantic):

**Extraídos do PDF (parser):**
`cups`, `periodo_inicio`, `periodo_fin`, `comercializadora`,
`pp_p1`..`pp_p6` (preços potência €/kW·dia),
`pe_p1`..`pe_p6` (preços energia €/kWh — só os períodos presentes na fatura),
`imp_ele`, `iva`, `alq_eq_dia`

**Completados pela API Ingebau:**
`tarifa_acceso`, `distribuidora`,
`pot_p1_kw`..`pot_p6_kw` (6),
`consumo_p1_kwh`..`consumo_p6_kwh` (6),
`dias_facturados`

**Metadados:**
`api_ok` (bool), `api_error` (str), `fichero_json` (str)

Todos os campos são `Optional` exceto `api_ok`.

**Comportamento dos `pe_p*`:**
- Preço único (Repsol, Plenitude): só `pe_p1` preenchido, restantes `null`
- 2.0TD (Octopus, EnergyaVM, Contigo…): `pe_p1`, `pe_p2`, `pe_p3`
- 3.0TD (Cox): apenas períodos com consumo não-zero (ex: `pe_p3`, `pe_p4`, `pe_p6`)

---

## CORS (`api/main.py`)

Origens permitidas lidas de `ALLOWED_ORIGINS` (variável de ambiente, separada por vírgulas):

```
Default: http://localhost:5173, http://localhost:3000,
         https://master.dsg7um3zm296x.amplifyapp.com
```

`allow_methods=["*"]`, `allow_headers=["*"]`

---

## Serviços Externos

| Serviço | URL | Usado em |
|---------|-----|---------|
| API Ingebau | `http://13.39.57.137:8004/Cups` | `extractor/api.py`, `api/routes/cups.py` |
| Zoho Flow Webhook | `https://flow.zoho.eu/20067915739/flow/webhook/incoming?zapikey=...` | `api/routes/enviar.py` |

> **Segurança:** A chave `zapikey` do Zoho está hardcoded em `enviar.py` — nunca commitar a chave real em repositórios públicos.

---

## Notas para Desenvolvimento

- **Caminhos Tesseract/Poppler hardcoded para Windows** — em Linux/produção, Poppler é encontrado automaticamente; Tesseract precisa estar no PATH.
- **Sem testes automatizados** — testar manualmente via Swagger UI (`/docs`) ou GUI Tkinter.
- **Adicionar nova comercializadora:** criar `extractor/parsers/{nome}.py` → registar em `extractor/parsers/__init__.py` → adicionar padrão em `extractor/detector.py`.
- **O diretório `resultados/`** é ignorado pelo git — não guardar faturas reais no repositório.
- **O `.gitignore` ignora `*.md`** — o CLAUDE.md e BACKEND.md devem ser excecionados se se quiser fazer commit.
