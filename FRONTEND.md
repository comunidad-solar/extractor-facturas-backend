# FRONTEND.md — Extractor Facturas Frontend (Comunidad Solar)

Repositório: `extractor-facturas-frontend`
Stack: React 19 + Vite 7 (SPA, sem router, sem lib de estado)

---

## Estrutura do Repositório

```
extractor-facturas-frontend/
├── public/
│   ├── logo.png          # Logo Comunidad Solar
│   ├── App.png           # Screenshot da app
│   ├── Footer.png        # Imagem do rodapé
│   ├── Intersect.png     # Imagem de instalação solar
│   └── domicilio.png     # Imagem de domicílio
├── src/
│   ├── components/
│   │   ├── FacturaUpload.jsx   # Componente principal (~1482 linhas)
│   │   └── FacturaUpload.css   # Estilos do componente
│   ├── App.jsx                 # Wrapper raiz
│   ├── main.jsx                # Entry point React
│   └── index.css               # Estilos globais
├── .env                        # Variáveis locais (não commitadas)
├── .env.example                # Template de variáveis
└── vite.config.js              # Config Vite + proxy de desenvolvimento
```

---

## Dependências

### Produção
| Pacote | Versão | Propósito |
|--------|--------|-----------|
| `react` | ^19.2.0 | Biblioteca UI |
| `react-dom` | ^19.2.0 | Renderização no browser |

### Desenvolvimento
| Pacote | Versão | Propósito |
|--------|--------|-----------|
| `vite` | ^7.3.1 | Bundler e servidor de desenvolvimento |
| `@vitejs/plugin-react` | ^5.1.1 | Suporte a JSX/React no Vite |
| `eslint` + plugins | ^9.x | Linting |

**Sem bibliotecas externas de UI, estado, routing ou HTTP** — usa apenas Fetch API nativo.

---

## Variáveis de Ambiente (`.env`)

```env
VITE_API_URL=http://localhost:8000
VITE_LEAD_URL=https://dummyjson.com/test
VITE_NOMINATIM_URL=https://nominatim.openstreetmap.org
VITE_CE_DETAIL_URL=https://comunidades-energeticas-api-20084454554.catalystserverless.eu
```

> **Atenção:** As variáveis `.env` estão **parcialmente ignoradas** no componente. Os URLs reais estão hardcoded em `FacturaUpload.jsx`:

```javascript
const API_BASE    = "https://extractor.13.38.9.119.nip.io";
const QUOTING_URL = "https://quoting-new.13.38.9.119.nip.io/api/asesores/factura-details-demo";
const LEAD_URL    = "https://quoting-new.13.38.9.119.nip.io/api/asesores/factura-details-demo";
const CE_API_URL  = "https://comunidades-energeticas-api-20084454554.catalystserverless.eu/server/api/get-ce-info-lat-lng";
const NOMINATIM_URL = "https://nominatim.openstreetmap.org";
```

### Proxy Vite (desenvolvimento local)
```javascript
// vite.config.js
proxy: {
  '/facturas': VITE_API_URL || 'http://localhost:8000',
  '/cups':     VITE_API_URL || 'http://localhost:8000',
  '/enviar':   VITE_API_URL || 'http://localhost:8000',
  '/ce-api': { target: VITE_CE_DETAIL_URL, changeOrigin: true, rewrite: ... }
}
```

---

## Fluxo Completo do Utilizador

```
LANDING (Step 1 — Dados Pessoais)
  └─► Preenchimento: nome, apelidos, email, telefone, morada (autocomplete)
       └─► Clique "Continuar"
            └─► Validação dos campos
                 └─► Geocodificação da morada (Nominatim)
                      └─► Cálculo de distância às CEs (Haversine)
                           ├─► Dentro de zona → Avança para Step 2
                           └─► Fora de zona  → Página "lista de espera"

STEP 2 — Seleção do método de entrada
  ├─► Modo PDF: upload de fatura → análise automática
  └─► Modo CUPS: código CUPS → consulta API

STEP 2 (PDF) — Upload + Resultados
  └─► Clique "Analisar fatura" → POST /facturas/extraer
       └─► Exibe campos extraídos → Clique "Enviar dados"
            └─► POST /enviar → POST (quoting) → Página do plano

STEP 2 (CUPS) — Consulta + Formulário manual
  └─► Clique "Consultar CUPS" → GET /cups/consultar
       └─► Campos automáticos + campos manuais → Clique "Enviar dados"
            └─► POST /enviar → POST (quoting) → Página do plano

PLANO SOLAR — Resultado personalizado
  └─► Painel de poupanças, painéis solares, financiamento, CE
```

---

## Todas as Chamadas API

### 1. Nominatim — Autocomplete de Morada
```
GET https://nominatim.openstreetmap.org/search
    ?q={texto}&format=json&limit=5&countrycodes=es&addressdetails=1

Headers: User-Agent: ComunidadSolar/1.0

Trigger: onChange do campo morada (debounce 500ms, mínimo 4 chars)

Resposta:
[{ "lat": "40.12", "lon": "-3.45", "display_name": "Rua...", ... }]

Fallback: Se falhar ou sem seleção → 2ª chamada ao Nominatim para geocodificação
          Se geocodificação falhar → aviso + continua sem verificação de zona
```

### 2. Nominatim — Geocodificação de Fallback
```
GET https://nominatim.openstreetmap.org/search
    ?q={morada}&format=json&limit=1&countrycodes=es

Trigger: Quando utilizador não selecionou sugestão do autocomplete
Fallback: Se falhar → Fsmstate="02_FUERA_ZONA", mostra aviso, avança para Step 2
```

### 3. CE API — Lista de Comunidades Energéticas
```
GET https://comunidades-energeticas-api-20084454554.catalystserverless.eu
    /server/api/get-ce-info-lat-lng

Trigger: useEffect no mount do componente (fire-and-forget)

Resposta:
{
  "data": [
    {
      "lat": "40.12", "lng": "-3.45",
      "name": "CE Nome",
      "addressName": "Morada",
      "status": "Available" | "Waiting list",
      "etiqueta": "label",
      "radioMetros": 2000
    }, ...
  ]
}

Fallback: Array vazio → zona não verificada, avança Step 2
```

### 4. CE API — Detalhes de Comunidade Energética
```
POST https://comunidades-energeticas-api-20084454554.catalystserverless.eu
     /server/api/get-ce-info?name={nome}

Body: vazio

Trigger: Após confirmar que utilizador está dentro da zona de uma CE

Resposta:
{
  "data": {
    "name": "CE Nome", "addressName": "Morada",
    "status": "Available" | "Waiting list", "etiqueta": "label"
  }
}

Fallback: Usa dados em cache da lista de CEs se este pedido falhar
```

### 5. Backend — Análise de Fatura PDF
```
POST https://extractor.13.38.9.119.nip.io/facturas/extraer

Body: FormData { "file": <PDF binário> }
Content-Type: multipart/form-data

Trigger: Clique "Analisar fatura →"

Resposta (ExtractionResponse):
{
  "cups": "ES0021000000000000AA",
  "comercializadora": "Iberdrola",
  "distribuidora": "...",
  "tarifa_acceso": "2.0A",
  "periodo_inicio": "2024-01-01",
  "periodo_fin": "2024-01-31",
  "dias_facturados": 31,
  "potencias_kw": { "p1": 3.3, "p2": null, ... },
  "consumos_kwh": { "p1": 150, "p2": null, ... },
  "precios_potencia": { "p1": 0.50, "p2": null, ... },
  "impuestos": { "imp_ele": 5.11, "iva": 21 },
  "otros": { "alq_eq_dia": 0.05 },
  "api_ok": true,
  "api_error": ""
}

Erros: 400 (não é PDF), 500 (erro de processamento)
Fallback: Mostra mensagem de erro, utilizador pode tentar nova fatura
```

### 6. Backend — Consulta CUPS
```
GET https://extractor.13.38.9.119.nip.io/cups/consultar?cups={codigo}

Trigger: Clique "Consultar CUPS →" ou Enter no campo CUPS

Resposta:
{
  "cups": "ES0021000000000000AA",
  "comercializadora": "...",
  "distribuidora": "...",
  "tarifa_acceso": "2.0A",
  "periodo_inicio": "2024-01-01",
  "periodo_fin": "2024-01-31",
  "dias_facturados": 31,
  "pot_p1_kw": 3.3, "pot_p2_kw": null, ...,
  "consumo_p1_kwh": 150, "consumo_p2_kwh": null, ...,
  "api_ok": true,
  "api_error": ""
}

Erros: 400, 404, 503, 504
Fallback: Mostra mensagem de erro, utilizador pode tentar outro CUPS
```

### 7. Backend — Envio de Dados (/enviar)
```
POST https://extractor.13.38.9.119.nip.io/enviar

Body: FormData {
  "data": JSON.stringify({
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
      "tarifa_acceso": "2.0A",
      "periodo_inicio": "2024-01-01",
      "periodo_fin": "2024-01-31",
      "dias_facturados": 31,
      "potencias_kw": { "p1": 3.3, "p2": null, ... },
      "consumos_kwh": { "p1": 150, "p2": null, ... },
      "precios_potencia": { "p1": 0.50, "p2": null, ... },
      "impuestos": { "imp_ele": 5.11, "iva": 21 },
      "otros": { "alq_eq_dia": 0.05 },
      "arquivo": {},
      "api": { "api_ok": true, "api_error": "" }
    },
    "Fsmstate": "01_DENTRO_ZONA" | "02_FUERA_ZONA",
    "FsmPrevious": null | "01_DENTRO_ZONA" | "02_FUERA_ZONA",
    "ce": {
      "nombre": "CE Nome",
      "direccion": "Morada CE",
      "status": "Available",
      "etiqueta": "label"
    }
  })
}

Nota: O campo "file" (PDF) foi removido do backend — /enviar já não aceita nem processa ficheiros.

Resposta: { "ok": true }

Erros: 400 (JSON inválido), 503 (sem conexão Zoho), 504 (timeout), 502 (erro Zoho)
O backend reencaminha este payload ao webhook Zoho Flow.
Fallback: Mostra mensagem de erro, utilizador pode tentar novamente
```

### 8. Quoting API — Geração do Plano Solar
```
POST https://quoting-new.13.38.9.119.nip.io/api/asesores/factura-details-demo

Body: JSON (mesmo payload de /enviar sem o FormData):
{
  "cliente": { ... },
  "factura": { ... },
  "Fsmstate": "01_DENTRO_ZONA" | "02_FUERA_ZONA",
  "FsmPrevious": null | "...",
  "ce": { ... }
}

Trigger: Após /enviar retornar { "ok": true }

Resposta:
{
  "numeroPaneles": 3,
  "pagoUnico": 3480.75,
  "pagoFinanciado": 41.33,
  "ahorroMensual": 38.35,
  "ahorroAnual": 460.20,
  "ahorro25Anos": 1575.35,
  "potenciaTotal": 3,
  "produccionAnual": 4101.25,
  "coeficienteDistribucion": 5,
  "plazoRecuperacion": 6.7
}

Fallback: Mostra erro, status="sent" mas sem dados de plano
```

### 9. Lead API — Registo de Lead (fire-and-forget)
```
POST https://quoting-new.13.38.9.119.nip.io/api/asesores/factura-details-demo

Body: JSON {
  "cliente": { nombre, apellidos, correo, telefono, direccion },
  "fsmstate": "01_DENTRO_ZONA" | "02_FUERA_ZONA",
  "ceNombre": "...",
  "ceDireccion": "...",
  "ceStatus": "...",
  "ceEtiqueta": "..."
}

Trigger: Após verificação de zona, antes de avançar para Step 2
Fire-and-forget: erros são silenciosos (apenas log) — não bloqueiam o fluxo
Fallback: Define leadWarn=true se falhar, mostra aviso interno
```

---

## Tabela de Fallbacks

| Chamada | Falha | Comportamento |
|---------|-------|---------------|
| Nominatim autocomplete | Erro de rede | Dropdown vazio, utilizador continua |
| Nominatim geocodificação | Falha | Aviso + Fsmstate="02_FUERA_ZONA" + avança Step 2 |
| CE lista | Falha | Array vazio, zona não verificada |
| CE detalhe | Falha | Usa cache da lista |
| `/facturas/extraer` | Erro | Mensagem de erro, retry disponível |
| `/cups/consultar` | Erro | Mensagem de erro, retry disponível |
| `/enviar` | Erro | Mensagem de erro, retry disponível |
| Quoting API | Erro | Mensagem de erro, plano não exibido |
| Lead API | Qualquer | Silencioso (fire-and-forget) |

---

## Estado da Aplicação (State Management)

Toda a lógica está em `FacturaUpload.jsx` via `useState` + `useRef`. Não há Context API nem biblioteca externa.

### Variáveis de estado principais

```javascript
// Navegação
step          // 1 | 2
mode          // null | "pdf" | "cups"
status        // "idle" | "analyzed" | "sent" | "fuera_zona"
modoAsesor    // boolean (?interno-asesores=true na URL)

// Dados do cliente (Step 1)
cliente       // { nombre, apellidos, correo, telefono, direccion }
clienteErrors // erros de validação por campo
userCoords    // { lat, lon } — da geocodificação

// Verificação de zona
Fsmstate      // "01_DENTRO_ZONA" | "02_FUERA_ZONA"
fsmPrevious   // estado anterior
ceNombre, ceDireccion, ceStatus, ceEtiqueta, ceDistancia, ceRadio

// PDF (Step 2A)
file          // File object
facturaData   // ExtractionResponse do backend

// CUPS (Step 2B)
cups          // string do código CUPS
cupsData      // resposta do /cups/consultar
manualFields  // campos que o utilizador preenche manualmente

// Plano resultante
planData      // resposta do quoting endpoint
panelesSel    // número de painéis selecionado (otimizador local)

// UI
loading, loadingMsg, error, sending, leadWarn
isDragging    // drag-and-drop do PDF
tabActiva     // "como" | "plan" | "condiciones"
```

### Refs
```javascript
nominatimTimerRef  // debounce do autocomplete
dropdownRef        // elemento do dropdown (para detetar clique fora)
fileRef            // input[type=file] (clique programático)
listaCERef         // cache da lista de CEs (evita closures obsoletas)
```

---

## Validações do Formulário (Step 1)

| Campo | Regra |
|-------|-------|
| nombre | Não vazio |
| apellidos | Não vazio |
| correo | Regex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/` |
| telefono | Regex `/^(?:\+34\|0034)?[679]\d{8}$/` (espaços removidos antes) |
| direccion | Não vazio |

---

## Campos Manuais (Modo CUPS)

Após consultar CUPS, o utilizador preenche campos que a API Ingebau não devolve:

| Campo | Label | Condicional |
|-------|-------|-------------|
| periodo_inicio | Período início | Sempre |
| periodo_fin | Período fim | Sempre |
| comercializadora | Comercializadora | Sempre |
| pp_p1 | Preço potência P1 (€/kW·dia) | Sempre |
| pp_p2 | Preço potência P2 (€/kW·dia) | Sempre |
| imp_ele | Imposto elétrico (%) | Sempre |
| iva | IVA (%) | Sempre |
| alq_eq_dia | Aluguer equipamento (€/dia) | Sempre |
| pp_p3 a pp_p6 | Preço potência P3-P6 | Só se `tarifa_acceso ≠ "2.0TD"` |

---

## Página de Resultados (Plano Solar)

Exibida quando `status === "sent"`. Dados vindos do quoting endpoint:

| Dado | Campo API | Exibido como |
|------|-----------|--------------|
| Número de painéis | `numeroPaneles` | Tabela + otimizador |
| Pagamento único | `pagoUnico` | Cartão + tabela |
| Financiado | `pagoFinanciado` | Cartão (€/mês) |
| Poupança mensal | `ahorroMensual` | Métricas |
| Poupança anual | `ahorroAnual` | Métricas |
| Poupança 25 anos | `ahorro25Anos` | Hero + métricas |
| Potência total | `potenciaTotal` | Tabela |
| Produção anual | `produccionAnual` | Tabela |
| Coef. distribuição | `coeficienteDistribucion` | Tabela |
| Prazo de retorno | `plazoRecuperacion` | Tabela |

O otimizador de painéis (`panelesSel`) é **apenas local** — não faz chamada API.

---

## Modo Asesor Interno

Ativado via URL: `?interno-asesores=true`

- Mostra badge "Modo interno — Asesores"
- Salta Step 1 (sem formulário de dados pessoais)
- Usa `ASESOR_ENVIO_URL` para submissão (atualmente não configurado)
- Se `ASESOR_REDIRECT_URL` configurado, redireciona após sucesso

---

## Upload de Ficheiro PDF

- Drag-and-drop + clique para navegar
- Validação: `file.type === "application/pdf"` ou extensão `.pdf`
- Sem limite de tamanho no cliente
- Campo `file` no FormData enviado para `/facturas/extraer`
- **Nota:** O envio do PDF para `/enviar` foi removido — o backend já não aceita `file` nesse endpoint

---

## Notas para Desenvolvimento

- Todo o código de UI está num único componente de 1482 linhas (`FacturaUpload.jsx`) — refatoração em sub-componentes seria benéfica mas não é prioritária
- Os URLs estão hardcoded no componente, apesar de existir `.env` — qualquer mudança de URL requer edição direta no componente
- O `QUOTING_URL` e o `LEAD_URL` apontam para o mesmo endpoint — verificar se é intencional
- Botões "CONTRATAR", "OPTIMIZAR" e "DESCARGAR" na página de resultados não têm handlers implementados
- O modo asesor (`ASESOR_ENVIO_URL`) não está configurado — submissão em modo asesor vai falhar silenciosamente
