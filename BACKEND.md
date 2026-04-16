# BACKEND.md — Extractor Facturas Luz (Backend)

Repositório: `extractor-facturas-backend`
Stack: Python 3.x + FastAPI + Uvicorn

---

## Estrutura do Repositório

```
extractor-facturas-backend/
├── api/
│   ├── main.py              # FastAPI app, CORS, registo de routers
│   ├── models.py            # Schema Pydantic ExtractionResponse (27 campos)
│   └── routes/
│       ├── facturas.py      # POST /facturas/extraer
│       ├── cups.py          # GET /cups/consultar
│       └── enviar.py        # POST /enviar (proxy Zoho Flow)
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

### `POST /facturas/extraer`

**Propósito:** Recebe um PDF de fatura elétrica, extrai os campos e devolve os dados estruturados.

**Request:**
```
Content-Type: multipart/form-data
Campo: "file" — ficheiro PDF
```

**Processamento interno:**
1. Valida extensão `.pdf`
2. Guarda PDF num ficheiro temporário
3. Chama `extract_from_pdf(tmp_path)` — pipeline completo (ver secção Pipeline)
4. Elimina o ficheiro temporário
5. Guarda resultado em `resultados/{cups}_{inicio}_{fim}.json`
6. Devolve `ExtractionResponse`

**Resposta (200):**
```json
{
  "cups": "ES0021000000000000AA",
  "periodo_inicio": "01/01/2024",
  "periodo_fin": "31/01/2024",
  "comercializadora": "Iberdrola Clientes, S.A.U.",
  "pp_p1": 0.123456,
  "pp_p2": 0.067890,
  "pp_p3": null,
  "pp_p4": null,
  "pp_p5": null,
  "pp_p6": null,
  "pe_p1": 0.128456,
  "pe_p2": 0.098234,
  "pe_p3": 0.076123,
  "pe_p4": null,
  "pe_p5": null,
  "pe_p6": null,
  "imp_ele": 5.11269,
  "iva": 21,
  "alq_eq_dia": 0.052000,
  "tarifa_acceso": "2.0TD",
  "distribuidora": "Iberdrola Distribución Eléctrica",
  "pot_p1_kw": 3.3,
  "pot_p2_kw": 3.3,
  "pot_p3_kw": 0,
  "pot_p4_kw": 0,
  "pot_p5_kw": 0,
  "pot_p6_kw": 0,
  "consumo_p1_kwh": 150.0,
  "consumo_p2_kwh": 80.0,
  "consumo_p3_kwh": 0,
  "consumo_p4_kwh": 0,
  "consumo_p5_kwh": 0,
  "consumo_p6_kwh": 0,
  "dias_facturados": "31",
  "api_ok": true,
  "api_error": "",
  "fichero_json": "ES0021000000000000AA_01-01-2024_31-01-2024.json"
}
```

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | Ficheiro não termina em `.pdf` |
| 500 | Erro interno no processamento |

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
3. POST ao webhook Zoho Flow (timeout 30s) com o JSON parsed
4. Devolve `{"ok": true}`

**Destino do reenvio:**
```
POST https://flow.zoho.eu/20067915739/flow/webhook/incoming
     ?zapikey=...&isdebug=false
Content-Type: application/json
Body: <parsed JSON>
```

**Resposta (200):**
```json
{ "ok": true }
```

**Erros:**
| Código | Motivo |
|--------|--------|
| 400 | `data` não é JSON válido ou falta campo `cliente` |
| 503 | Erro de conexão com Zoho Flow |
| 504 | Timeout em Zoho Flow |
| 502 | Zoho Flow devolveu erro HTTP |

> **Nota:** O campo `file` (PDF) e o forward para `CALC_BACKEND_URL` foram **removidos** nesta versão. O `/enviar` aceita apenas o campo `data` e reenvia ao Zoho.

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
