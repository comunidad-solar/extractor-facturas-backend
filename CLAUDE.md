# CLAUDE.md — Extractor Facturas Luz (Backend)

## Visão Geral do Projeto

Sistema Python para extrair campos-chave de faturas de eletricidade espanholas em PDF, de múltiplas comercializadoras. Oferece dois modos de uso:

- **GUI Desktop** (`main.py`) — aplicação Tkinter para uso manual
- **REST API** (`api/`) — servidor FastAPI para processamento automatizado

---

## Estrutura do Repositório

```
extractor-facturas-backend/
├── api/
│   ├── main.py              # FastAPI app, CORS, migrações Alembic no startup, registo de routers
│   ├── models.py            # Schemas Pydantic (ExtractionResponse, ExtractionResponseAI)
│   ├── db/
│   │   ├── database.py      # Engine SQLAlchemy, SessionLocal, Base, DATABASE_URL
│   │   ├── models.py        # ORM model SessionRecord (tabela sessions)
│   │   └── repository.py    # db_save_session, db_get_session, db_update_session
│   ├── utils/
│   │   ├── __init__.py      # pacote utils
│   │   └── geo.py           # simplify_address(), geocode_address() via Nominatim
│   └── routes/
│       ├── facturas.py      # POST /facturas/extraer (pipeline multi-agente Claude — principal)
│       ├── facturas_ai.py   # POST /facturas/extraer-ai (legado — Claude direto)
│       ├── cups.py          # GET /cups/consultar
│       ├── enviar.py        # POST /enviar (proxy Zoho Flow)
│       └── sesion.py        # POST/GET/PATCH /sesion — memória + SQLite
├── alembic/                 # Migrações Alembic versionadas
│   └── versions/
│       └── 787deedd37e0_create_sessions_table.py
├── alembic.ini              # Configuração Alembic (DATABASE_URL via env)
├── data/                    # SQLite DB (volume Docker — não commitado)
├── extractor/
│   ├── __init__.py          # Pipeline principal: extract_from_pdf()
│   ├── base.py              # ExtractionResult, helpers (norm, numeros, datas)
│   ├── detector.py          # Deteção de comercializadora por padrões regex
│   ├── api.py               # Integração com API Ingebau
│   ├── fields.py            # Definição dos 27 campos e metadados
│   └── parsers/
│       ├── base_parser.py   # Classe base com lógica genérica de extração
│       ├── generic.py       # Parser de fallback
│       ├── repsol.py
│       ├── octopus.py
│       ├── naturgy.py
│       ├── naturgy_regulada.py
│       ├── iberdrola.py
│       ├── endesa.py
│       ├── cox.py           # Usa PyMuPDF (layout 2 colunas)
│       ├── contigo.py
│       ├── energyavm.py
│       ├── pepeenergy.py
│       └── plenitude.py
├── main.py                  # GUI Desktop (Tkinter)
├── requirements.txt
├── .env.example
└── resultados/              # JSONs de saída (ignorado pelo git)
```

---

## Stack Tecnológica

| Componente       | Tecnologia                                |
|------------------|-------------------------------------------|
| Linguagem        | Python 3.x                                |
| API Web          | FastAPI + Uvicorn                         |
| GUI              | Tkinter (nativo Python)                   |
| Validação        | Pydantic                                  |
| Extração PDF     | pdfplumber, PyMuPDF (fitz)                |
| OCR              | pytesseract + pdf2image + Pillow          |
| HTTP Client      | requests                                  |
| Subida de ficheiros | python-multipart                       |
| Base de dados    | SQLite + SQLAlchemy 2.x (ORM) + Alembic   |

**Ferramentas externas (Windows, caminhos fixos no código):**
- Tesseract OCR: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Poppler: `C:\Users\ianro\AppData\Local\...\poppler-25.07.0\Library\bin`

---

## Comandos Essenciais

### Instalar dependências
```bash
pip install -r requirements.txt
```

### Iniciar a API REST
```bash
uvicorn api.main:app --reload --port 8000
```
- Swagger UI: http://localhost:8000/docs

### Iniciar a GUI Desktop
```bash
python main.py
```

### Não há testes automatizados
O projeto não tem pytest nem framework de testes. O teste é manual via GUI ou endpoints da API.

---

## Variáveis de Ambiente

Copiar `.env.example` para `.env`:

```env
API_TOKEN=your_token_here
API_URL=http://13.39.57.137:8004/Cups
FRONTEND_URL=http://localhost:5173
```

- `API_TOKEN` — token de autenticação para a API Ingebau
- `API_URL` — endpoint da API Ingebau (tem default no código)
- `FRONTEND_URL` — URL do frontend para CORS (usado como `ALLOWED_ORIGINS`)
- `CALC_BACKEND_URL` — **removida**: o `/enviar` já não faz forward para backend de cálculo
- `DATABASE_URL` — URL SQLAlchemy para SQLite. Default: `sqlite:///./sessions.db` (local dev). Docker: `sqlite:////app/data/sessions.db`

---

## Endpoints da API

### `POST /facturas/extraer` *(principal)*
- Upload de ficheiro PDF + `data` JSON opcional (cliente, ce, Fsmstate)
- Pipeline multi-agente Claude: Stage 1 Opus (transcrição) + 4 mappers Sonnet (potencia, energia, cargas, costes)
- Geocodifica `direccion_suministro` via Nominatim → `suministro_lat`, `suministro_lon`
- Busca `dealId`/`mpklogId` no Zoho CRM pelo `correo`
- Devolve `ExtractionResponseAI` com `nombre_cliente`, `direccion_suministro`, `suministro_lat`, `suministro_lon`, `session_id`
- Erros: 400, 502, 504, 500

### `POST /facturas/extraer-ai` *(legado)*
- Claude direto (sem pipeline multi-agente); mantido para backward compat

### `GET /cups/consultar?cups={cups}`
- Consulta dados do ponto de fornecimento via API Ingebau
- Devolve: tarifa, distribuidora, potências contratadas, consumos, dias faturados
- Erros: 400, 404, 503, 504

### `POST /enviar`
- Proxy para webhook Zoho Flow
- Body: campo `data` (Form) com JSON `{cliente, factura, session_id, Fsmstate, FsmPrevious, ce}`
- **Substitui `factura` pela versão Claude da sessão** (se `session_id` presente)
- **Injeta `nombre_cliente`, `direccion_suministro`, `suministro_lat`, `suministro_lon`** na factura
- **Não aceita ficheiro PDF** (campo `file` foi removido)
- Devolve: `{"ok": true, "dealId": "...", "mpklogId": "...", "session_id": "..."}`

### `POST /sesion`
- Cria sessão temporária com payload JSON arbitrário
- Guarda em memória (TTL 40min) + SQLite (sem expiração)
- Devolve: `{"session_id": "<uuid>"}`

### `GET /sesion/{session_id}`
- Lê sessão — memória primeiro, fallback SQLite se expirada/reinício
- Devolve: payload JSON completo (inclui `facturaPreview` após PATCH do cotizador)
- Erros: 404 (não encontrada)

### `PATCH /sesion/{session_id}`
- Merge parcial do body nos dados existentes, renova TTL em memória
- Cotizador usa este endpoint para adicionar `facturaPreview` e `url` à sessão
- Devolve: `{"ok": true}`
- Erros: 404 (não encontrada)

### `GET /`
- Devolve: `{"status": "ok", "version": "1.0.0"}`

---

## Fluxo de Extração (Pipeline)

```
PDF
 └─► Extração de texto (pdfplumber → fallback OCR)
      └─► Deteção de comercializadora (regex em extractor/detector.py)
           └─► Parser específico (subclasse de BaseParser)
                └─► Campos extraídos do PDF:
                     cups, periodo_inicio/fin, comercializadora,
                     pp_p1..pp_p6, pe_p1..pe_p6, imp_ele, iva, alq_eq_dia
                     └─► Consulta API Ingebau (por CUPS)
                          └─► Campos adicionais da API:
                               tarifa_acceso, distribuidora,
                               pot_p1_kw..pot_p6_kw, consumo_p1_kwh..consumo_p6_kwh,
                               dias_facturados
                               └─► ExtractionResult → JSON em /resultados/ + resposta API
```

---

## Campos Extraídos

Os campos base estão definidos em `extractor/fields.py`. O schema completo da resposta está em `api/models.py`.

**Extraídos do PDF (parser):**
1. **Identificação** — CUPS, comercializadora, período início/fim
2. **Potências** — `pp_p1`..`pp_p6` em €/kW/dia
3. **Preços de energia** — `pe_p1`..`pe_p6` em €/kWh (só os períodos presentes na fatura)
4. **Impostos** — IEE (%), IVA (%)
5. **Aluguer** — aluguer de contador (€/dia)

**Completados pela API Ingebau:**
6. **Tarifa** — tarifa de acesso, distribuidora
7. **Potências contratadas** — `pot_p1_kw`..`pot_p6_kw` em kW
8. **Consumos** — `consumo_p1_kwh`..`consumo_p6_kwh` em kWh, dias faturados

**Nota sobre `pe_p*`:**
- Preço único (ex: Repsol): só `pe_p1` preenchido, `pe_p2`..`pe_p6` ficam `null`
- 2.0TD com 3 períodos: `pe_p1`, `pe_p2`, `pe_p3`
- 3.0TD (ex: Cox): apenas os períodos com consumo não-zero (ex: `pe_p3`, `pe_p4`, `pe_p6`)

---

## Arquitetura dos Parsers

- `BaseParser` (`extractor/parsers/base_parser.py`) — lógica genérica com múltiplos padrões regex para suportar variações de layout entre faturas
- Cada comercializadora tem uma subclasse que só sobrepõe o necessário
- **Exceção:** Cox usa PyMuPDF (`fitz`) em vez de pdfplumber por ter layout em 2 colunas
- **Exceção:** Naturgy pré-processa o texto para remover separadores de milhares (`.`)
- Fallback OCR quando pdfplumber não extrai texto suficiente
- Validação pós-OCR do CUPS: corrige `O→0` em posições numéricas esperadas

**`extraer_precios_energia()` — overrides por parser:**

| Parser | Formato | Resultado |
|--------|---------|-----------|
| `BaseParser` | 4 padrões genéricos (preço único, `P1 Y €/kWh`, `Energía P1 ... €/kWh`, fallback) | pe_p1..pe_p6 |
| `octopus.py` | `Punta/Llano/Valle X kWh Y €/kWh` | pe_p1/p2/p3 |
| `cox.py` | `P3 X kWh * Y €/kWh` via fitz (só períodos com consumo) | pe_pN variável |
| `energyavm.py` | `P1: X kWh, Precio: Y €/kWh` + linhas de continuação P2/P3 | pe_p1/p2/p3 |
| `contigo.py` | `P1. Energía activa X kWh PRECIO TOTAL` (sem €/kWh explícito) | pe_p1/p2/p3 |
| `plenitude.py` | `Consumo Fácil ... Y €/kWh` (preço único) | pe_p1 |

---

## Serviços Externos

- **API Ingebau** (`http://13.39.57.137:8004/Cups`) — dados de ponto de fornecimento e histórico de consumos. Tolerância de 15 dias no matching de períodos.
- **Zoho Flow Webhook** — integração downstream para automação de processos
- **Nominatim (OpenStreetMap)** (`https://nominatim.openstreetmap.org/search`) — geocodificação de endereços espanhóis. Requer `simplify_address()` antes da chamada; User-Agent `ComunidadSolar/1.0`. Veja `api/utils/geo.py`.

---

## Documentação Detalhada

- **`BACKEND.md`** — documentação completa do backend: todas as bibliotecas, endpoints com payload/resposta/erros, pipeline de extração, parsers, integração API Ingebau.
- **`FRONTEND.md`** — documentação completa do frontend (`extractor-facturas-frontend`): todas as chamadas API, payloads, fallbacks, fluxo do utilizador.

---

## Log de Mudanças

Cada alteração ao código deve ser registada em `log.md` com:
- Número sequencial `[NNN]`
- Data
- Prompt resumido
- Ficheiros alterados
- O que mudou (antes/depois quando relevante)

O `log.md` é o histórico de decisões do projecto — manter conciso mas completo.

---

## Notas Importantes para Desenvolvimento

- Os **caminhos do Tesseract e Poppler estão hardcoded** para Windows — não é cross-platform. Antes de criar configurações cross-platform, confirmar com o utilizador.
- O **URL do webhook Zoho** contém uma chave de API no código fonte (`enviar.py`) — nunca commitar chaves reais.
- O diretório `resultados/` é ignorado pelo git — não guardar dados de faturas reais no repositório.
- O `.gitignore` ignora `*.md` — o CLAUDE.md, BACKEND.md e FRONTEND.md devem ser excecionados se se quiser fazer commit.
- Não há testes automatizados — ao adicionar funcionalidade nova, testar manualmente via Swagger UI ou GUI.
- Ao adicionar suporte a nova comercializadora: criar ficheiro em `extractor/parsers/`, registar em `extractor/parsers/__init__.py`, e adicionar padrão de deteção em `extractor/detector.py`.
- O `/enviar` aceita apenas o campo `data` (Form) — o campo `file` e o forward para `CALC_BACKEND_URL` foram removidos. A `factura` enviada ao Zoho é a versão Claude da sessão (com `otros.importes_totalizados`), não a flat do frontend.
- **Geocodificação** — `api/utils/geo.py` contém `simplify_address()` e `geocode_address()`. Nunca duplicar inline — usar sempre o módulo partilhado. Endereços crus falham no Nominatim; `simplify_address()` é obrigatório.
- **`/facturas/extraer` é o endpoint principal** — `facturas_ai.py` é legado. Novas features vão em `facturas.py`.
- **Sessões persistem em SQLite** (`api/db/`). Alembic corre migrações automaticamente no startup. Em Docker, o DB fica em `/app/data/sessions.db` (volume `-v /home/ubuntu/data-dev:/app/data`). Sem volume → DB perde-se no redeploy.
- **Deploy dev EC2:** `cd /home/ubuntu/extractor-facturas-backend && git pull origin DEVELOP && docker stop extractor-facturas-dev && docker rm extractor-facturas-dev && docker build -t extractor-facturas-dev . && mkdir -p /home/ubuntu/data-dev && docker run -d --name extractor-facturas-dev --env-file .env.development -p 8011:8000 --restart always -v /home/ubuntu/data-dev:/app/data -e DATABASE_URL=sqlite:////app/data/sessions.db extractor-facturas-dev`
