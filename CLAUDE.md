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
│   ├── main.py              # FastAPI app, CORS, registo de routers
│   ├── models.py            # Schemas Pydantic (ExtractionResponse)
│   └── routes/
│       ├── facturas.py      # POST /facturas/extraer
│       ├── cups.py          # GET /cups/consultar
│       └── enviar.py        # POST /enviar (proxy Zoho Flow)
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

---

## Endpoints da API

### `POST /facturas/extraer`
- Upload de ficheiro PDF
- Devolve `ExtractionResponse` com 27 campos extraídos
- Guarda JSON em `/resultados/{cups}_{periodo}.json`
- Erros: 400 (não é PDF), 500 (erro de processamento)

### `GET /cups/consultar?cups={cups}`
- Consulta dados do ponto de fornecimento via API Ingebau
- Devolve: tarifa, distribuidora, potências contratadas, consumos, dias faturados
- Erros: 400, 404, 503, 504

### `POST /enviar`
- Proxy para webhook Zoho Flow
- Body: campo `data` (Form) com JSON `{cliente, factura, Fsmstate, FsmPrevious, ce}`
- **Não aceita ficheiro PDF** (campo `file` foi removido)
- **Não faz forward para `CALC_BACKEND_URL`** (removido)
- Devolve: `{"ok": true}`

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
- O `/enviar` aceita apenas o campo `data` (Form) — o campo `file` e o forward para `CALC_BACKEND_URL` foram removidos.
