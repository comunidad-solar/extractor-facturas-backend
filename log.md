# Log de Mudanças — extractor-facturas-backend

---

## 2026-04-15

---

### [048] Novo endpoint `POST /facturas/extraer-ai` via Claude API
**Prompt:** Integrar Claude API como caminho de extracção primário. O payload extraído deve ser enviado para `/sesion` e devolver `session_id`.

**Ficheiros:**
- `requirements.txt` — adicionado `anthropic`
- `.env.example` — adicionado `ANTHROPIC_API_KEY`
- `api/models.py` — adicionados `ValidacionCuadre` e `ExtractionResponseAI`
- `api/claude/__init__.py`, `api/claude/client.py` — singleton Anthropic
- `api/claude/prompts.py` — carrega `prompt_lectura_factura.md` + preamble; prompt caching (byte-idêntico entre chamadas)
- `api/claude/extractor.py` — chama `messages.parse()` com `output_format=ExtractionResponseAI`
- `api/routes/facturas_ai.py` — endpoint, reconciliação R13 (`_calc_validacion_cuadre`), criação de sessão
- `api/main.py` — registo de `facturas_ai_router`

**Mudança:**
- Antes: extracção só via parsers regex (`/facturas/extraer`)
- Depois: novo endpoint paralelo `/facturas/extraer-ai` usando `claude-sonnet-4-6`; parsers regex inalterados
- Reconciliação R13: compara soma dos conceitos (`imp_termino_energia_eur` + `imp_termino_potencia_eur` + IEE + aluguer + IVA + bónus + descontos + outros) com `importe_factura` (tolerância ≤ €0.02)
- `session_id` criado via `crear_sesion()` directo (sem chamada HTTP)
- JSON guardado com sufixo `_ai` em `resultados/`

---

## 2026-04-14

---

### [001] Adicionar `sessionId` ao payload do Zoho Flow
**Prompt:** Adicionar `sessionId` ao payload enviado ao Zoho Flow no `/enviar`.

**Ficheiros:** `api/routes/enviar.py`

**Mudança:**
- Criar sessão **antes** de enviar ao Zoho, para incluir `sessionId` no payload
- Ordem original: enviar Zoho → delay → buscar IDs → criar sessão
- Ordem nova: delay → buscar IDs → criar sessão → adicionar `sessionId` → enviar Zoho

---

### [002] Reverter fluxo `/enviar` — sessão dava 404
**Prompt:** Sessão dava 404; reverter para fluxo original sem `sessionId` no payload Zoho.

**Ficheiros:** `api/routes/enviar.py`

**Mudança:**
- Revertido para fluxo correcto: enviar Zoho → delay → buscar IDs → criar sessão
- `sessionId` removido do payload enviado ao Zoho
- `session_payload` volta a ser `{**parsed, "dealId": deal_id, "mpklogId": mpklog_id}`

---

### [003] Extracção de potências contratadas directamente dos PDFs
**Prompt:** Adicionar `extraer_potencias_contratadas()` em todos os parsers. PDF prevalece sobre Ingebau.

**Ficheiros:**
- `extractor/parsers/base_parser.py` — novo método `extraer_potencias_contratadas()` com 3 padrões genéricos
- `extractor/parsers/repsol.py` — override: captura "Punta/Valle: X kW"
- `extractor/parsers/octopus.py` — override: linha "Potencia Contratada (kW)" com valores por posição
- `extractor/parsers/naturgy.py` — override: fitz como fonte primária + linhas limpas
- `extractor/parsers/cox.py` — override: fitz, padrão "P{n} X kW *"
- `extractor/parsers/iberdrola.py` — override: "Potencia punta/valle: X kW"
- `extractor/parsers/endesa.py` — override: texto cortado antes de "FACTURA ENDESA X"
- `extractor/parsers/pepeenergy.py` — override: "Potencia contratada en P{n}: X kW"
- `extractor/parsers/plenitude.py` — override: extracção posicional (OCR corrompe "P1:")
- `extractor/parsers/contigo.py` — override: linha "Potencia facturada", primeiro número é kW
- `extractor/parsers/energyavm.py` — override: linha com "€/kW/día", captura "P{n}: X kW"
- `extractor/parsers/naturgy_regulada.py` — override: "punta/valle: X kW" + fallback PVPC
- `extractor/__init__.py` — pipeline: chama `extraer_potencias_contratadas()` após `parse()`, guarda snapshot antes de Ingebau, restaura depois

**Lógica:**
```
pot_pdf = parser.extraer_potencias_contratadas()
→ gravar em fields
→ llamar_api() (Ingebau pode sobrescrever)
→ restaurar campos_pot_pdf (PDF prevalece)
```

---

### [004] Fix `plenitude.py` — OCR capturava kWh como kW
**Prompt:** OCR lia "25,00 kWh" como "25,00 kW"; regex genérico capturava incorrectamente.

**Ficheiro:** `extractor/parsers/plenitude.py`

**Mudança:**
- Substituído regex genérico `P{p}[:\s]+X kW` por busca específica na linha "potencia contratada"
- Adicionado filtro: ignorar linhas com "kwh"
- Adicionado negative lookahead `kW(?!h)`

---

### [005] Fix `plenitude.py` — OCR corrompe "P1:" em "?::"
**Prompt:** OCR lê "P1:" como "?::" em `'Potencia contratada ?::3.450 kW P2:3.450 kw'`.

**Ficheiro:** `extractor/parsers/plenitude.py`

**Mudança:**
- Abandonada pesquisa por label "P1"/"P2"
- Extracção posicional: `findall(r"([0-9]+[,\.][0-9]+)\s*kW(?!h)")` → 1.º valor = P1, 2.º = P2
- Adicionados filtros extra: ignorar linhas com "facturación"/"desglose" e linhas com "€"

---

### [006] Novo parser `EnergiaXXIParser`
**Prompt:** Criar parser para Energía XXI Comercializadora de Referencia S.L.U. (PVPC Grupo Endesa).

**Ficheiros criados/alterados:**
- `extractor/parsers/energiaxxi.py` — **novo ficheiro** com 8 métodos:
  - `extraer_comercializadora()` — regex "Energía XXI Comercializadora de Referencia S.L.U."
  - `extraer_periodo()` — datas por extenso "10 de diciembre de 2025 a 14 de enero de 2026"
  - `extraer_precios_potencia()` — P1/P3 em €/kW/año ÷ 365, média ponderada por días; P3→pp_p2
  - `extraer_precios_energia()` — P1/P2/P3 em €/kWh, média ponderada por kWh
  - `extraer_imp_ele()` — "BASE Eur X PORCENTAJE %"
  - `extraer_iva()` — "IVA normal: 21 % s/ BASE"
  - `extraer_alquiler()` — "N días x Y Eur/día"
  - `extraer_bono_social()` — "N días x Y Eur/día"
  - `extraer_potencias_contratadas()` — "Potencia contratada en punta-llano: X kW"
- `extractor/detector.py` — adicionado padrão `energ[ií]a\s+xxi|energiaxxi\.com → "energiaxxi"`
- `extractor/parsers/__init__.py` — import e registo `"energiaxxi": EnergiaXXIParser`

---

### [007] Dockerfile — reduzir workers de 2 para 1
**Prompt:** Sessões em memória não são partilhadas entre workers; sessão criada no worker A não é encontrada no worker B.

**Ficheiro:** `Dockerfile`

**Mudança:**
```
# Antes
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# Depois
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

### [008] Eliminar duplicação de `dealId`/`mpklogId` no payload de sessão
**Prompt:** `dealId` e `mpklogId` apareciam duplicados: `null` em `cliente.*` e com valor na raiz.

**Ficheiro:** `api/routes/enviar.py`

**Mudança:**
- Após buscar `deal_id` e `mpklog_id`, actualizar também `session_payload["cliente"]["dealId"]` e `session_payload["cliente"]["mpklogId"]` com os valores reais
```python
# Adicionado após criar session_payload
if "cliente" in session_payload:
    session_payload["cliente"]["dealId"]   = deal_id
    session_payload["cliente"]["mpklogId"] = mpklog_id
```

---

### [009] `base_parser.py` — descuentos + media ponderada para sub-períodos duplicados
**Prompt:** Adicionar `extraer_descuentos()`, melhorar `extraer_precios_energia()` com média ponderada para períodos duplicados, e incluir descuentos em `parse()`.

**Ficheiro:** `extractor/parsers/base_parser.py`

**Mudanças:**

1. **`extraer_descuentos()`** — novo método:
   - Detecta linhas com keywords: `descuento`, `bonificaci`, `ajuste`, `compensaci`, etc.
   - Ignora bono social, financiación, IVA, imposto
   - Extrai valor absoluto do último `- X,XX €` da linha
   - Devolve `dict {nome_limpo: valor_float}`

2. **`extraer_precios_energia()`** — lógica adicional antes dos 4 padrões originais:
   - Isola secção "Facturación por energía consumida" com `_extraer_seccion_energia()`
   - Acumula `kWh` e `€` por período com `_acumular_kwh_eur()`
   - Se detectar períodos duplicados (`count > 1`), aplica média ponderada e retorna
   - Caso contrário, cai nos 4 padrões originais

3. **`parse()`** — adicionado no final:
   ```python
   descuentos = self.extraer_descuentos()
   self.fields["descuentos"] = descuentos if descuentos else {}
   ```

4. **Novos métodos auxiliares:**
   - `_extraer_seccion_energia()` — extrai bloco de texto da secção de energia
   - `_acumular_kwh_eur()` — acumula kWh e € por período P1..P6
   - `_limpiar_nombre_descuento()` — limpa nome do descuento removendo números e símbolos

---

### [010] Fix `energiaxxi.py` — PVPC `pe_p1` por importe_total/kwh_total
**Prompt:** Fix PVPC — `pe_p1 = importe_total / consumo_total` quando há "Costes de la energía" sem preço/kWh explícito.

**Ficheiro:** `extractor/parsers/energiaxxi.py`

**Mudança:**
- `extraer_precios_energia()` reescrito para detetar PVPC via `re.search(r"PVPC|Mercado\s+Regulado")`
- Acumula `kWh` e `€` das linhas de peajes (`P{n} X kWh × Y €/kWh`)
- Busca importe de "Costes de la energía" (OMIE) como linha separada sem preço/kWh
- Calcula `pe_p1 = (eur_peajes + eur_costes) / kwh_total`
- Fallback ao `BaseParser` se não PVPC ou se não conseguir calcular
- `pe_p2`, `pe_p3` ficam `null` (preço único PVPC)

---

### [010b] Fix `energiaxxi.py` — `extraer_precios_energia()` média ponderada por período
**Prompt:** Substituir lógica PVPC por média ponderada separada por P1/P2/P3 (peajes com €/kWh explícito por sub-período).

**Ficheiro:** `extractor/parsers/energiaxxi.py`

**Mudança:**
- Abandona cálculo `importe_total / kwh_total` (que colapsa todos os períodos num único `pe_p1`)
- Acumula `kWh` e `€` separadamente por período P1, P2, P3
- `pe_p{n} = soma(€ sub-períodos Pn) / soma(kWh sub-períodos Pn)`
- "Costes de la energía" (OMIE) não é capturado — não tem preço/kWh associável a um período
- Resultado esperado: `pe_p1≈0.094792`, `pe_p2≈0.028638`, `pe_p3≈0.003112`

---

### [011b] Fix `naturgy_regulada.py` — dois bugs no `extraer_precios_energia()`
**Prompt:** pe_p* errados — kWh inteiros sem decimal não fazem match; corte "excede el límite" não funciona por `í` → `\ufffd`.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Bugs corrigidos:**
1. `patron_peaje` — kWh como inteiro (`110kWh`) não batia com `[0-9]+[,\.][0-9]+`; corrigido para `[0-9]+(?:[,\.][0-9]+)?`
2. Corte `excede\s+el\s+l[ií]mite` não fazia match porque pdfplumber lê `í` como `\ufffd`; corrigido para `l.mite` (dot match)

**Resultado:** `pe_p1=0.092539`, `pe_p2=0.028201`, `pe_p3=0.002994`

---

### [011] Fix `naturgy_regulada.py` — PVPC `pe_p1` + `extraer_descuentos()`
**Prompt:** Fix PVPC — `pe_p1 = importe_total / consumo_total`; adicionar `extraer_descuentos()` para "Descuento por Bono Social".

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudanças:**

1. **`extraer_precios_energia()`** — reescrito com lógica PVPC idêntica à `energiaxxi.py`:
   - Deteta PVPC via `re.search(r"PVPC|Mercado\s+Regulado")`
   - Corta texto antes de "excede el límite" (evita duplicados do bono social)
   - Acumula kWh e € das linhas de peajes `P{n} (periodo): X kWh × Y €/kWh`
   - Busca "Coste de la energía: X €" (importe OMIE sem preço/kWh)
   - `pe_p1 = (eur_peajes + eur_costes) / kwh_total`
   - Fallback ao `BaseParser` se não PVPC ou se dados insuficientes

2. **`extraer_descuentos()`** — novo método:
   - Deteta linhas com "descuento" (exclui "financiaci" e "impuesto")
   - Captura valor absoluto do último `- X,XX €` da linha
   - Complementa com `super().extraer_descuentos()` para outros formatos

---

### [011c] `naturgy_regulada.py` — deduplicação em `extraer_descuentos()`
**Prompt:** "Descuento por Bono Social" aparecia duplicado (linha do resumo + linha do desglose com mesmo valor).

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudança:**
- Antes de inserir no dict, verifica se já existe entrada com valor próximo (`abs(v - valor) < 0.01`)
- Se sim, salta a inserção
- Resultado: `{"Descuento por Bono Social": 29.59}` — uma única entrada

---

### [011e] `naturgy_regulada.py` — reescrita final `extraer_precios_energia()` + deduplicação melhorada
**Prompt:** Consolidar método com acumulado por período (P1/P2/P3 independentes) e deduplicação por nome+valor.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudanças:**
1. `extraer_precios_energia()` — substituído por acumulado por período (idêntico a `energiaxxi.py`); kWh com decimal opcional `(?:[,\.][0-9]+)?`; `finditer(texto)` usa variável com corte
2. `extraer_descuentos()` — deduplicação reforçada: verifica nome normalizado (sem espaços, lowercase) E valor próximo (`< 0.01`)

**Resultado validado:** `pe_p1=0.092539`, `pe_p2=0.028201`, `pe_p3=0.002994`, `pe_p4=null`

---

### [011f] `naturgy_regulada.py` — deduplicação no merge com BaseParser em `extraer_descuentos()`
**Prompt:** BaseParser podia reinserir o mesmo descuento que já estava em `resultado`.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudança:**
- Bloco final do `extraer_descuentos()`: substituído `if k not in resultado` por verificação dupla — nome normalizado (sem espaços, lowercase) E valor próximo (`< 0.01`)
- Garante que `super().extraer_descuentos()` não duplica entradas já capturadas

---

### [011d] `naturgy_regulada.py` — `extraer_alquiler()` para texto concatenado
**Prompt:** pdfplumber concatena tokens sem espaços; BaseParser falha a extrair `alq_eq_dia`.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudança:**
- Novo override `extraer_alquiler()` com padrão `[0-9]+\s*días?\s*\*\s*PRECIO\s*€/día`
- Captura `0.026630` directamente em vez de calcular por divisão (`total / dias`)
- Fallback ao `BaseParser` se não fizer match

---

### [016] Adicionar `otros` ao payload de sessão + `descuentos` ao modelo
**Prompt:** Payload enviado à sessão deve conter os novos campos extraídos; reunir `bono_social` e `descuentos` dentro de `otros: {}`.

**Ficheiros:**
- `api/models.py` — adicionado `descuentos: Optional[dict] = None` ao `ExtractionResponse`
- `api/routes/enviar.py` — adicionado `session_payload["otros"]` com `bono_social` e `descuentos` extraídos de `parsed["factura"]`

**Estrutura resultante em `factura.otros`:**
```json
"factura": {
  "otros": {
    "alq_eq_dia": 0.044712,
    "bono_social": 0.012742,
    "cuotaAlquilerMes": null,
    "descuentos": { "Descuento por Bono Social": 29.59 }
  }
}
```
Nota: `otros` já existia em `factura` (vindo do frontend); `descuentos` é injectado no merge, sem criar chave `otros` duplicada na raiz.

---

### [012] `naturgy.py` — `extraer_descuentos()`
**Prompt:** Adicionar `extraer_descuentos()` para capturar "Descuento Real Decreto-ley 17/2021 -32,77€".

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- Novo método `extraer_descuentos()`:
  - Deteta linhas com "descuento" ou "real decreto" (ignora "financiaci", "impuesto", "bono social")
  - Captura valor absoluto do último número negativo `- X,XX €?` da linha
  - Nome extraído do texto antes do primeiro dígito/`€`/`-`/`*`
  - Complementa com `super().extraer_descuentos()`

---

### [013] `iberdrola.py` — `extraer_descuentos()` com deduplicação completa
**Prompt:** Substituir método por versão com deduplicação por linha, nome normalizado e valor.

**Ficheiro:** `extractor/parsers/iberdrola.py`

**Mudança:**
- Adicionado `linhas_processadas` (set) para ignorar linhas duplicadas
- Adicionado filtro `"iva"` aos exclusões
- Deduplicação por nome normalizado (sem espaços, lowercase) e valor próximo (`< 0.01`)
- Merge com `super().extraer_descuentos()` aplica a mesma deduplicação
- Resultado esperado: `{"Descuento pertenencia Comunidad Solar": 7.63}`

---

### [014] `pepeenergy.py` — `extraer_descuentos()`
**Prompt:** Adicionar `extraer_descuentos()` para capturar "Descuento cliente Pepephone -3,14 €".

**Ficheiro:** `extractor/parsers/pepeenergy.py`

**Mudança:**
- Novo método `extraer_descuentos()`:
  - Deteta linhas com "descuento" ou "cuota" (ignora "financiaci", "impuesto", "bono social")
  - Captura valor absoluto do último `- X,XX €` da linha
  - Nome extraído do texto antes do primeiro dígito/`€`/`-`/`*`
  - Complementa com `super().extraer_descuentos()`

---

### [015] `plenitude.py` — `extraer_descuentos()`
**Prompt:** Adicionar `extraer_descuentos()` para capturar "Descuento asociado al ahorro de cargos... RDL 06/2022: -4,20€".

**Ficheiro:** `extractor/parsers/plenitude.py`

**Mudança:**
- Novo método `extraer_descuentos()`:
  - Deteta linhas com "descuento" ou "rdl" (ignora "financiaci", "impuesto", "bono social")
  - Captura valor absoluto do último `- X,XX €` da linha
  - Nome extraído do texto antes do primeiro dígito/`€`/`-`/`*`
  - Complementa com `super().extraer_descuentos()`

---

### [041] `cox.py` — `extraer_consumos()` reescrito via linhas de energia fitz
**Prompt:** Substituir abordagem "Cons. kWh" (tabela) por padrão "P{n} X kWh * Y €/kWh" nas linhas de energia.

**Ficheiro:** `extractor/parsers/cox.py`

**Mudança:**
- Padrão anterior: `Cons. kWh val1..val6` (tabela com 6 colunas)
- Padrão novo: `P([1-6]) ([\d.,]+) kWh \* [\d.,]+ €/kWh` no texto colapsado
- Remove ponto de milhares antes de converter: `"2.959,00"` → `2959.0`
- Resultado esperado: `consumo_p3_kwh=2959.0`, `p4=1842.0`, `p6=6380.0`

---

### [040] Fix `naturgy.py` — `extraer_consumos()` 2.0TD decimal opcional
**Prompt:** "64kWh" sem decimal não dava match. Tornar decimal opcional nos dois sub-padrões.

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- Padrão 1: `[,\.][0-9]*` → `(?:[,\.][0-9]*)?`
- Padrão 2 (concatenado): idem
- Resultado esperado: `consumo_p1_kwh=64.0`, `p2=81.0`, `p3=153.0`

---

### [039] Fix `pepeenergy.py` — `extraer_consumos()` decimal opcional + remove debug
**Prompt:** `[,\.][0-9]*` não captura inteiros como "53 kWh". Tornar decimal opcional.

**Ficheiro:** `extractor/parsers/pepeenergy.py`

**Mudança:**
- `([0-9]+[,\.][0-9]*)` → `([0-9]+(?:[,\.][0-9]*)?)` — decimal opcional
- Removidos prints de diagnóstico

---

### [038] Fix `pepeenergy.py` — `extraer_consumos()` busca em texto completo
**Prompt:** OCR pode quebrar linha; buscar "Consumo facturado:" no texto completo e extrair os 200 chars seguintes.

**Ficheiro:** `extractor/parsers/pepeenergy.py`

**Mudança:**
- Substituído loop `self.linhas` por `re.search` em `self.text` + janela de 200 chars
- Padrão aplicado sobre `trecho` em vez de linha individual

---

### [037] `pepeenergy.py` — `extraer_consumos()` para "Consumo facturado: P1..."
**Prompt:** OCR PepeEnergy tem "Consumo facturado: P1 (Punta): 53 kWh. P2 (Llano): 55 kWh. P3 (Valle): 167 kWh."

**Ficheiro:** `extractor/parsers/pepeenergy.py`

**Mudança:**
- Novo método `extraer_consumos()`: filtra linha "consumo facturado", captura `P{n} (label): X kWh`
- Padrão tolerante a variantes OCR de kWh: `k[wW]+[hH]+`
- Resultado esperado: `consumo_p1_kwh=53.0`, `p2=55.0`, `p3=167.0`

---

### [036] Fix `plenitude.py` — `extraer_consumos()` aceita variantes OCR de kWh
**Prompt:** OCR pode ler "kWh" como "kwWh", "KWH", etc. Tornar padrão tolerante.

**Ficheiro:** `extractor/parsers/plenitude.py`

**Mudança:**
- `kWh` → `k[wW]+[hH]+` — aceita "kWh", "kwWh", "KWH", "kWH"

---

### [035] `plenitude.py` — `extraer_consumos()` para desglose por período
**Prompt:** OCR Plenitude tem "Desglose del consumo facturado por periodo: P1:25,00 kWh; P2:29,00 kWh; P3: 48,00 kWh".

**Ficheiro:** `extractor/parsers/plenitude.py`

**Mudança:**
- Novo método `extraer_consumos()`: filtra linhas com "desglose" + "periodo", captura `P{n}: X kWh`
- Resultado esperado: `consumo_p1_kwh=25.0`, `p2=29.0`, `p3=48.0`
- Fallback a `super().extraer_consumos()`

---

### [034] Fix `naturgy.py` — `extraer_consumos()` fitz decimal opcional
**Prompt:** `P1 0 kWh` (inteiro sem decimal) não dava match com `[0-9]+[,\.][0-9]*`. Tornar decimal opcional.

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- `([0-9]+[,\.][0-9]*)` → `([0-9]+(?:[,\.][0-9]*)?)` no padrão fitz
- Captura tanto `0 kWh` como `274 kWh` e `185,5 kWh`

---

### [033] Fix `naturgy.py` — `extraer_consumos()` fitz colapsa newlines
**Prompt:** fitz separa "Consumo electricidad P1" e "0 kWh" em linhas distintas; padrão não match. Colapsar `\n+` → espaço antes de aplicar regex.

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- Adicionado `fitz_collapsed = re.sub(r'\n+', ' ', fitz_text)` antes do `finditer`
- Padrão aplicado sobre `fitz_collapsed` em vez de `fitz_text`

---

### [032] `naturgy.py` — `extraer_consumos()` 3.0TD via fitz
**Prompt:** 3.0TD usa fitz como fonte primária ("Consumo electricidad P1\n0 kWh"); 2.0TD mantém pdfplumber concatenado.

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- Bloco fitz adicionado como prioridade 1: padrão `Consumo electricidad P([1-6]) ([0-9]+...) kWh` no texto fitz
- Bloco 2.0TD (pdfplumber) mantido como fallback
- Se fitz encontrar qualquer período, devolve imediatamente sem tentar pdfplumber
- Resultado 3.0TD: `consumo_p1_kwh=0.0`, `p2=274.0`, `p3=185.0`, `p4=0.0`, `p5=0.0`, `p6=584.0`
- Resultado 2.0TD: `consumo_p1_kwh=64.0`, `p2=81.0`, `p3=153.0`

---

### [031] Fix `iberdrola.py` — `extraer_consumos()` 3.0TD decimal e milhares
**Prompt:** Padrão 3.0TD capturava apenas inteiros; "1.275 kWh" (ponto de milhares) dava `1.275` errado.

**Ficheiro:** `extractor/parsers/iberdrola.py`

**Mudança:**
- Padrão: `([0-9]+)` → `([0-9]+(?:[.,][0-9]+)?)` — aceita decimal/milhares na coluna kWh
- Conversão: `float(m.group(2))` → `val_str.replace(".", "").replace(",", ".")` — remove ponto de milhares antes de converter
- Resultado esperado: `consumo_p2_kwh=1275.0, consumo_p3_kwh=682.0, consumo_p6_kwh=767.0`

---

### [030] Fix `naturgy_regulada.py` — decimal opcional em `extraer_consumos()`
**Prompt:** Padrão `[,\.][0-9]*` não captura inteiros como "85 kWh"; corrigir para `(?:[,\.][0-9]*)?`.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudança:**
- `[0-9]+[,\.][0-9]*` → `[0-9]+(?:[,\.][0-9]*)?` — decimal opcional
- Captura tanto "85 kWh" como "85,00 kWh"

---

### [029] `octopus.py` — `extraer_consumos()` para "Punta/Llano/Valle X kWh"
**Prompt:** Adicionar override de `extraer_consumos()` para formato Octopus com linha por período.

**Ficheiro:** `extractor/parsers/octopus.py`

**Mudança:**
- Novo método `extraer_consumos()`: padrão `^(punta|llano|valle) X kWh` com `re.MULTILINE`
- Mapeia punta→P1, llano→P2, valle→P3
- Fallback a `super().extraer_consumos()`

---

### [028] `energyavm.py` — `extraer_consumos()` para "P{n}: X kWh"
**Prompt:** Adicionar override de `extraer_consumos()` reutilizando padrão de `extraer_precios_energia()`.

**Ficheiro:** `extractor/parsers/energyavm.py`

**Mudança:**
- Novo método `extraer_consumos()`: captura `"P{n}: X,XX kWh"` (com ou sem prefixo "Término de energía")
- Fallback a `super().extraer_consumos()`

---

### [027] `energiaxxi.py` — `extraer_consumos()` para "Consumo en P{n}: X kWh"
**Prompt:** Adicionar override de `extraer_consumos()` para formato EnergíaXXI PVPC.

**Ficheiro:** `extractor/parsers/energiaxxi.py`

**Mudança:**
- Novo método `extraer_consumos()`: captura `"Consumo en P{n}: X,XX kWh"` para P1..P3
- Fallback a `super().extraer_consumos()`

---

### [026] `endesa.py` — `extraer_consumos()` com soma de sub-períodos
**Prompt:** Adicionar override de `extraer_consumos()` somando múltiplos sub-períodos "Facturación del Consumo X kWh".

**Ficheiro:** `extractor/parsers/endesa.py`

**Mudança:**
- Novo método `extraer_consumos()`: corta antes de "FACTURA ENDESA X", acumula todos os kWh de "Facturación del Consumo"
- Resultado único em `consumo_p1_kwh` (Endesa usa preço único, sem separação por período)
- Fallback a `super().extraer_consumos()`

---

### [025] `cox.py` — `extraer_consumos()` via fitz para tabela 3.0TD
**Prompt:** Adicionar override de `extraer_consumos()` usando fitz para capturar linha "Cons. kWh P1..P6".

**Ficheiro:** `extractor/parsers/cox.py`

**Mudança:**
- Novo método `extraer_consumos()`: abre PDF com fitz, localiza linha `"Cons. kWh val1..val6"`
- Os 6 grupos correspondem a P1..P6; só insere no dict se `val > 0`
- Fallback a `super().extraer_consumos()`

---

### [024] `contigo.py` — `extraer_consumos()` para "P1. Energía activa X kWh"
**Prompt:** Adicionar override de `extraer_consumos()` reutilizando padrão de `extraer_precios_energia()`.

**Ficheiro:** `extractor/parsers/contigo.py`

**Mudança:**
- Novo método `extraer_consumos()`: detecta linhas "energía activa" com label P{n} e valor kWh
- Ignora linhas com "peaje", "cargo", "importe", "bono"
- Fallback a `super().extraer_consumos()`

---

### [023] `repsol.py` — `extraer_consumos()` para tabela de 3 colunas
**Prompt:** Adicionar override de `extraer_consumos()` para formato Repsol com 3 valores kWh por linha.

**Ficheiro:** `extractor/parsers/repsol.py`

**Mudança:**
- Novo método `extraer_consumos()`: detecta linha com "actual"/"periodo" + 3 valores kWh
- Atribui em ordem: vals[0]→P1 (punta), vals[1]→P2 (llano), vals[2]→P3 (valle)
- Fallback a `super().extraer_consumos()`

---

### [022] Fix `naturgy_regulada.py` — `norm()` pode retornar `None` em `extraer_consumos()`
**Prompt:** Diagnóstico de tipo: `float(norm(...))` falha se `norm()` retorna `None`.

**Ficheiro:** `extractor/parsers/naturgy_regulada.py`

**Mudança:**
- Substituído `float(norm(m.group(2)))` por guard explícito `val = norm(...); if val is not None: float(val)`

---

### [021] `iberdrola.py` — `extraer_consumos()` para 2.0TD e 3.0TD
**Prompt:** Adicionar override de `extraer_consumos()` para formatos Iberdrola 2.0TD e 3.0TD.

**Ficheiro:** `extractor/parsers/iberdrola.py`

**Mudança:**
- Novo método `extraer_consumos()` com dois padrões:
  1. 2.0TD — `"punta: 330 kWh; llano: 308 kWh; valle 458 kWh"` (linha única no rodapé)
  2. 3.0TD — tabela `"Energía activa P{n} ... CONSUMO kWh"` (última coluna)
- Fallback a `super().extraer_consumos()`

---

### [020] `naturgy.py` — `extraer_consumos()` para texto concatenado
**Prompt:** Adicionar override de `extraer_consumos()` para formato Naturgy com texto concatenado.

**Ficheiro:** `extractor/parsers/naturgy.py`

**Mudança:**
- Novo método `extraer_consumos()` com dois padrões:
  1. `"Consumo:Punta X kWh"` (com espaço)
  2. `"Consumo:Punta64kWh"` (concatenado sem espaço)
- Mapeia punta→P1, llano→P2, valle→P3
- Fallback a `super().extraer_consumos()`

---

### [019] `extractor/__init__.py` — integrar `extraer_consumos()` no pipeline
**Prompt:** Após bloco de potencias, adicionar extracção de consumos do PDF com snapshot/restore idêntico.

**Ficheiro:** `extractor/__init__.py`

**Mudança:**
- Bloco `[4b]` após `[4]`: chama `parser.extraer_consumos()`, grava em `fields`, imprime campos encontrados
- Após `llamar_api()`: restaura `campos_con_pdf` sobre os valores da Ingebau (PDF prevalece)

---

### [018] `base_parser.py` — novo método `extraer_consumos()`
**Prompt:** Adicionar `extraer_consumos()` genérico na classe BaseParser; integração no pipeline fica no `__init__.py`.

**Ficheiro:** `extractor/parsers/base_parser.py`

**Mudança:**
- Novo método `extraer_consumos()` com 3 padrões por prioridade:
  1. `"Punta/Llano/Valle X kWh"` → P1/P2/P3 (Octopus, Naturgy)
  2. `"P1. Energía activa X,XXX kWh"` → genérico com label Pn (Contigo)
  3. `"Px X kWh * Y €/kWh"` → genérico com `*` ou `×`
- Devolve `dict {"consumo_p{n}_kwh": float}` apenas com períodos encontrados
- Ingebau preenche os restantes

---

### [017] `sesion.py` — TTL de 30 para 40 minutos
**Prompt:** Aumentar duração da sessão de 30 para 40 minutos.

**Ficheiro:** `api/routes/sesion.py`

**Mudança:**
```python
# Antes
_TTL_MINUTES = 30
# Depois
_TTL_MINUTES = 40
```
