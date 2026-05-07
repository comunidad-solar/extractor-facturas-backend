# Melhorias ao Prompt Claude API — Extração de Facturas Eléctricas

WorkDrive de referência:
https://workdrive.zoho.eu/2895v6e186dc1b5f148dc9de8670b0a6403a1/teams/2895v6e186dc1b5f148dc9de8670b0a6403a1/ws/nr78289408951cb8e422aabd9101843e15e8b/folders/ozkvle81ed1fb44774a8bb37319fa35477515

---

## [MOD-001] Desconto já aplicado no valor final — evitar dupla contabilidade

**Data:** 2026-04-17
**Comercializadora referência:** TotalEnergies (fatura 1NSN251100248746, período 05.10.2025–05.11.2025)
**Aplicável a:** qualquer comercializadora que apresente descontos no formato "Subtotal - Descuento = Total"

### Problema detectado

Na factura TotalEnergies 2.0TD analisada, o desconto de 7% sobre consumo eléctrico aparece discriminado da seguinte forma na factura:

```
Consumo: 132 kWh × 0,224778 €/kWh = 29,67 € (Subtotal) − 7% Descuento = 27,59 € (Total sin IVA)
```

O valor extraído para `precio_final_energia_activa` (ou equivalente) é **27,59 €**, que já inclui o desconto aplicado.

No entanto, Claude também extrai:
```json
"creditos": {
  "descuento_7_pct_consumo_electrico": -2.08
}
```

Isto causa **dupla contabilidade**: o desconto de −2,08 € já está embutido nos 27,59 €, e ao mesmo tempo aparece como crédito separado — tornando o total facturado incorreto no payload.

### Padrão a identificar

Claude deve reconhecer os seguintes padrões textuais como indicadores de que o desconto **já foi aplicado** no valor final apresentado:

**Padrão tabular com coluna "Descuento" (caso desta factura)**
- `Cantidad × Precio = Subtotal − Descuento% = Total sin IVA`
- Tabela com colunas explícitas: `Período | Cantidad | Precio | Subtotal | Descuento | Total`
- O campo "Descuento" é uma coluna da mesma linha do consumo — o "Total" já reflecte o desconto

**Padrão inline numa única linha**
- `X kWh × Y €/kWh con Z% dto. = W €`
- `X kWh a Y €/kWh (−Z%) = W €`
- `Precio base X € − descuento Z% = W €`
- `[importe] menos [Z]% de descuento = [total]`

**Padrão com preço unitário já descontado**
- `Precio con descuento del Z%: Y €/kWh` seguido do cálculo `X kWh × Y €/kWh = W €`
- `Precio dto.: Y €/kWh` — o preço por kWh já é o preço final após desconto

**Padrão de duas linhas consecutivas do mesmo conceito**
- Linha 1: `Energía activa: X €`
- Linha 2 imediatamente a seguir: `Descuento Y%: −Z €`
- Linha 3: `Total energía: W €`
  → O "Total energía" já é W = X − Z; o desconto NÃO é conceito independente

**Padrão com rótulo explícito de desconto incluído**
- `Energía activa (con descuento del Z%): W €`
- `Consumo eléctrico con dto. Z%: W €`
- `Importe energía (aplicado Z% descuento fidelización): W €`

**Padrão de "Ahorro" dentro do bloco de energia**
- `Ahorro Z%: −Y €` aparece dentro do mesmo bloco de cálculo do consumo (não como línea separada após "Total electricidad")
- Distinguir de `Ahorro` que aparece depois do total geral — esse é crédito independente

**Indicadores negativos — NÃO aplicar esta regra se:**
- O desconto aparece como línea autónoma **após** o "Total electricidad / Total energía"
- O desconto tem cabeçalho próprio separado (ex: "Descuentos y bonificaciones", "Créditos aplicados")
- O desconto se refere a um conceito diferente do que está no campo extraído (ex: desconto na potência mas campo é de energia)

Estes padrões distinguem-se de créditos separados (ex: "Bono Social", "descuento por fidelización en línea separada") que aparecem como conceptos independientes **depois** do subtotal de energia/potência.

### Verificação numérica obrigatória

Antes de concluir que o desconto foi aplicado, Claude **deve confirmar o cálculo**. A identificação textual do padrão é necessária mas não suficiente — pode haver erros de leitura ou descontos que aparecem descritos mas não foram de facto deduzidos.

**Fórmulas de verificação por tipo de padrão:**

| Situação | Verificação |
|---|---|
| Desconto % sobre subtotal | `subtotal × (1 − desconto/100) ≈ valor_final` |
| Desconto em € sobre subtotal | `subtotal − desconto_eur ≈ valor_final` |
| Preço unitário já descontado | `preco_unitario × (1 − desconto/100) ≈ preco_dto` e `preco_dto × quantidade ≈ valor_final` |
| Duas linhas (total = linha1 − linha2) | `valor_linha1 − abs(valor_linha2) ≈ total` |

**Tolerância:** diferença ≤ 0,02 € (arredondamento da factura). Se a diferença for superior, o desconto **não foi confirmado** e deve tratar-se como crédito independente.

**Exemplo de verificação para esta factura (TotalEnergies):**
```
subtotal energia = 132 kWh × 0,224778 €/kWh = 29,67 €
desconto 7%      = 29,67 × 0,07 = 2,0769 € → arredondado 2,08 €
valor esperado   = 29,67 − 2,08 = 27,59 €
valor na factura = 27,59 € ✓ → desconto confirmado, registar como null em creditos
```

### Comportamento correto

Quando Claude detecta o padrão **e** confirma o cálculo:

1. **Não incluir o desconto em `creditos`** — definir o campo correspondente como `null`
2. **Adicionar entrada em `observacion`** com o seguinte formato:

```
"Desconto [descrição] de [valor €] já aplicado em [campo] (verificado: [subtotal] − [desconto%/€] = [total])"
```

Exemplo concreto para esta factura:
```json
"creditos": {
  "descuento_7_pct_consumo_electrico": null
},
"observacion": [
  "Desconto 7% consumo eléctrico de -2,08 € já aplicado no precio_final_energia_activa (verificado: 29,67 € − 7% = 27,59 €)"
]
```

Quando deteta o padrão mas o cálculo **não confirma** (diferença > 0,02 €):
- Manter o valor em `creditos` normalmente
- Adicionar em `observacion`: `"Aviso: desconto [descrição] não confirmado numericamente — registado em creditos"`

### Créditos que SÃO válidos em `creditos` (não confundir)

Os seguintes tipos de crédito **devem** continuar a aparecer em `creditos` porque são conceitos separados do valor de energia/potência:

- Descuentos por fidelización en línea separada
- Compensaciones por reclamación
- Cualquier crédito que aparezca **após** o "Total electricidad" ou equivalente

### Instrução a acrescentar ao prompt Claude

```
REGRA CRÍTICA — DESCONTOS JÁ APLICADOS:

Antes de registar qualquer valor em `creditos`, verifica se esse desconto já foi deduzido
no cálculo do valor final do campo correspondente. O indicador principal é o padrão
"Subtotal - Descuento = Total" ou equivalente na factura.

PASSO 1 — IDENTIFICAÇÃO: detectar o padrão textual (coluna Descuento, inline, rótulo, etc.)
PASSO 2 — VERIFICAÇÃO NUMÉRICA obrigatória:
  - Desconto %: subtotal × (1 − desconto/100) ≈ valor_final (tolerância ≤ 0,02 €)
  - Desconto €: subtotal − desconto_eur ≈ valor_final (tolerância ≤ 0,02 €)
  - Se a diferença > 0,02 €: o desconto NÃO está confirmado → tratar como crédito independente

Se o desconto JÁ ESTÁ aplicado (padrão identificado E cálculo confirmado):
  - Define o campo em `creditos` como null
  - Adiciona em `observacion`:
    "Desconto [descrição] de [valor €] já aplicado em [campo] (verificado: [subtotal] − [%/€] = [total])"

Se o padrão foi identificado MAS o cálculo não confirma (diferença > 0,02 €):
  - Mantém em `creditos` com o valor negativo correcto
  - Adiciona em `observacion`: "Aviso: desconto [descrição] não confirmado numericamente — registado em creditos"

Se o desconto aparece como CONCEITO SEPARADO depois do subtotal de electricidade:
  - Mantém em `creditos` com o valor negativo correcto

Esta regra aplica-se a todas as comercializadoras (TotalEnergies, Iberdrola, Endesa,
Naturgy, Repsol, etc.) — o padrão de desconto inline é transversal ao mercado espanhol.
```

---

## [MOD-002] `compensacion_excedentes_kwh` — campo direto em `otros`, não em `creditos`

**Data:** 2026-04-17
**Comercializadora referência:** Iberdrola (fatura 21240709010502454, período 06/06/2024–30/06/2024)
**Aplicável a:** qualquer comercializadora com autoconsumo/compensación de excedentes

### Problema detectado

Claude extrai `compensacion_excedentes_kwh` dentro de `creditos`, onde os valores são somados monetariamente em `creditos_totales`. Porém, este campo é uma **quantidade em kWh**, não um importe em euros, e a sua soma com valores monetários produz um resultado incorreto.

Estrutura incorreta extraída:
```json
"creditos": {
  "compensacion_excedentes_kwh": -303.31,
  "compensacion_excedentes_importe": -24.26
}
```

### Estrutura correta

`compensacion_excedentes_kwh` deve ser um **campo direto em `otros`** (mesmo nível que `costes`, `creditos`, `importes_totalizados`). O importe em euros (`compensacion_excedentes_importe`) permanece em `creditos`.

```json
"otros": {
  "importes_totalizados": { ... },
  "costes": { ... },
  "creditos": {
    "compensacion_excedentes_importe": -24.26
  },
  "compensacion_excedentes_kwh": -303.31,
  "observacion": []
}
```

Se não há compensação de excedentes na factura: `"compensacion_excedentes_kwh": null`.

### Instrução a acrescentar ao prompt Claude

```
REGRA — COMPENSACIÓN DE EXCEDENTES (AUTOCONSUMO):

O campo compensacion_excedentes_kwh representa uma quantidade em kWh, NÃO um importe.
Nunca o colocar dentro de `creditos` (que contém apenas valores monetários em €).

Colocação correcta:
  - compensacion_excedentes_kwh → campo direto em `otros` (mesmo nível que costes/creditos)
  - compensacion_excedentes_importe → dentro de `creditos` (valor monetário negativo em €)

Se a factura não tem autoconsumo: "compensacion_excedentes_kwh": null em `otros`.
```

---

## [MOD-003] Consumo kWh — usar "Energía consumida", não leituras do contador

**Data:** 2026-04-17
**Comercializadora referência:** Iberdrola (fatura 21240709010502454)
**Aplicável a:** todas as comercializadoras com leituras desagregadas no rodapé

### Problema detectado

Iberdrola (e outras comercializadoras) incluem no rodapé da factura as leituras absolutas do contador:
```
"Las lecturas desagregadas según la tarifa de acceso, tomadas el 30/06/2024 son:
punta: 23.501 kWh; llano: 22.865 kWh; valle 45.734 kWh"
```

Claude está a capturar estes valores (23.501, 22.865, 45.734) como consumos do período, quando na realidade são **leituras acumuladas absolutas do contador** — não o consumo faturado.

O consumo real do período está na linha:
```
Energía consumida  728,65 kWh × 0,142855 €/kWh  104,09 €
```

### Hierarquia de fontes para consumo kWh

Claude deve seguir esta ordem de prioridade, parando na primeira fonte encontrada:

1. Linha explícita "Energía consumida X kWh" no bloco ENERGÍA/DETALLE DE FACTURA
2. "Consumo total de esta factura: X kWh" no bloco de resumo
3. Consumos desagregados por período se sommam ao total correto: "Sus consumos desagregados han sido punta: X kWh; llano: Y kWh; valle: Z kWh" (estes são os consumos do período, distintos das leituras absolutas)

**NUNCA usar** os valores das "lecturas desagregadas" absolutas (ex: "punta: 23.501 kWh") — esses são contadores acumulados, não consumo do período.

### Instrução a acrescentar ao prompt Claude

```
REGRA CRÍTICA — CONSUMO kWh:

Usar SEMPRE a linha "Energía consumida X kWh" do bloco de detalle para o consumo total.
NUNCA confundir com as "lecturas desagregadas" absolutas do contador (valores como
23.501 kWh, 22.865 kWh, etc.) que aparecem no rodapé informativo — esses são leituras
acumuladas do medidor, não o consumo do período faturado.

Para consumos por período (P1/P2/P3): usar "Sus consumos desagregados han sido
punta: X kWh; llano: Y kWh; valle: Z kWh" — estes SÃO os consumos do período.
```

---

## [MOD-004] Serviços adicionais (Pack, Facilita, etc.) — também em `costes`

**Data:** 2026-04-17
**Comercializadora referência:** Iberdrola (fatura 21240709010502454)
**Aplicável a:** TotalEnergies (Servicio FACILITA), Iberdrola (Pack Iberdrola Hogar), e similares

### Problema detectado

Serviços como "Pack Iberdrola Hogar" e "Servicio FACILITA" são extraídos em `servicios_adicionales`, mas o seu custo bruto não aparece em `costes`, nem o desconto associado em `creditos`. Isto impede o cálculo correto de `costes_totales` e `creditos_totales`.

Exemplo Iberdrola:
```
Pack Iberdrola Hogar     0,8 meses × 8,95 €/mes    7,16 €
Descuento Pack Hogar 50%  50% s/7,16 €             -3,58 €
```

### Estrutura correta

O **valor bruto** do serviço vai para `costes`, e o **desconto associado** vai para `creditos`:

```json
"costes": {
  "pack_iberdrola_hogar_importe": 7.16
},
"creditos": {
  "descuento_pack_iberdrola_hogar": -3.58
}
```

Manter igualmente em `servicios_adicionales` se o campo existir no schema — não é substituição, é adição.

### Instrução a acrescentar ao prompt Claude

```
REGRA — SERVIÇOS ADICIONAIS COM DESCONTO:

Serviços como "Pack Iberdrola Hogar", "Servicio FACILITA", e similares devem ter:
  - O importe BRUTO (antes de desconto) em `costes` com chave descritiva (ex: pack_iberdrola_hogar_importe)
  - O desconto associado em `creditos` com valor negativo (ex: descuento_pack_iberdrola_hogar: -3.58)

Isto garante que costes_totales e creditos_totales reflectem correctamente todos os conceitos.
Se o serviço não tem desconto associado, apenas o importe em `costes`.
```

---

> Este ficheiro concentra as melhorias identificadas ao prompt do Claude API para extração
> de facturas. Cada entrada deve incluir: ID sequencial, data, comercializadora de referência,
> problema, padrão a identificar, comportamento correcto e instrução concreta para o prompt.
