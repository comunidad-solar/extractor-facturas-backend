# Guia de Campos do Payload

> Baseado num exemplo real: fatura 3.0TD, Quantium Lux, 30 dias, €1895.42.

Payload:

{
	"cliente": {
		"nombre": "Flow",
		"apellidos": "Test",
		"correo": "Test@gmail.com",
		"telefono": "654789123",
		"direccion": "Robregordo, Comunidade de Madrid, Espanha",
		"lat": 41.1064517,
		"lon": -3.5937466,
		"dealId": "230641000182098126",
		"mpklogId": "230641000182326253",
		"databaseId": "",
		"dni": "",
		"tipoVenta": "Alquiler"
	},
	"factura": {
		"cups": "ES0021000010960268KY0F",
		"comercializadora": "QUANTIUM LUX 6.4, SL",
		"distribuidora": "IBERDROLA DISTRIBUCIÓN ELÉCTRICA, S.A.U",
		"tarifa_acceso": "3.0TD",
		"periodo_inicio": "31/10/2025",
		"periodo_fin": "30/11/2025",
		"dias_facturados": "30",
		"importe_factura": 1895.42,
		"pp_p1": 0.00014756,
		"pp_p2": 7.696e-05,
		"pp_p3": 3.2e-05,
		"pp_p4": 2.763e-05,
		"pp_p5": 1.749e-05,
		"pp_p6": 1.018e-05,
		"pe_p1": 0.0,
		"pe_p2": 0.163966,
		"pe_p3": 0.143213,
		"pe_p4": 0.0,
		"pe_p5": 0.0,
		"pe_p6": 0.125853,
		"pot_p1_kw": 22.0,
		"pot_p2_kw": 27.7,
		"pot_p3_kw": 27.7,
		"pot_p4_kw": 27.7,
		"pot_p5_kw": 27.7,
		"pot_p6_kw": 27.7,
		"consumo_p1_kwh": 0.0,
		"consumo_p2_kwh": 3879.0,
		"consumo_p3_kwh": 2444.0,
		"consumo_p4_kwh": 0.0,
		"consumo_p5_kwh": 0.0,
		"consumo_p6_kwh": 1903.0,
		"imp_ele": 5.11269,
		"imp_ele_eur_kwh": null,
		"iva": 21,
		"alq_eq_dia": 0.198,
		"bono_social": null,
		"impuesto_electricidad_importe": 75.9,
		"alquiler_equipos_medida_importe": 5.94,
		"IVA_TOTAL_EUROS": 328.96,
		"IVA": {
			"IVA_PERCENT_1": 21,
			"IVA_PERCENT_2": null,
			"IVA_BASE_IMPONIBLE_1": 1566.46,
			"IVA_BASE_IMPONIBLE_2": null,
			"IVA_SUBTOTAL_EUROS_1": 328.96,
			"IVA_SUBTOTAL_EUROS_2": null,
			"IVA_TOTAL_EUROS": 328.96
		},
		"potencias_kw": {
			"p1": 22.0,
			"p2": 27.7,
			"p3": 27.7,
			"p4": 27.7,
			"p5": 27.7,
			"p6": 27.7
		},
		"consumos_kwh": {
			"p1": 0.0,
			"p2": 3879.0,
			"p3": 2444.0,
			"p4": 0.0,
			"p5": 0.0,
			"p6": 1903.0
		},
		"precios_potencia": {
			"p1": 0.00014756,
			"p2": 7.696e-05,
			"p3": 3.2e-05,
			"p4": 2.763e-05,
			"p5": 1.749e-05,
			"p6": 1.018e-05
		},
		"precios_energia": {
			"pe_p1": 0.0,
			"pe_p2": 0.163966,
			"pe_p3": 0.143213,
			"pe_p4": 0.0,
			"pe_p5": 0.0,
			"pe_p6": 0.125853
		},
		"impuestos": {
			"imp_ele": 5.11269,
			"imp_ele_eur_kwh": null,
			"iva": 21,
			"IVA": {
				"IVA_PERCENT_1": 21,
				"IVA_PERCENT_2": null,
				"IVA_BASE_IMPONIBLE_1": 1566.46,
				"IVA_BASE_IMPONIBLE_2": null,
				"IVA_SUBTOTAL_EUROS_1": 328.96,
				"IVA_SUBTOTAL_EUROS_2": null,
				"IVA_TOTAL_EUROS": 328.96
			}
		},
		"otros": {
			"alq_eq_dia": 0.198,
			"cuotaAlquilerMes": null,
			"costes": {
				"bono_social_importe": null,
				"exceso_potencia_importe": 118.65,
				"alquiler_equipos_medida_importe": 5.94,
				"coste_energia_reactiva": 55.08
			},
			"creditos": {
				"compensacion_excedentes_kwh": null,
				"compensacion_excedentes_importe": null
			},
			"observacion": [
				"pp_p1 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,053859/365=0,00014756",
				"pp_p2 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,028087/365=0,00007696",
				"pp_p3 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,011678/365=0,00003200",
				"pp_p4 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,010086/365=0,00002763",
				"pp_p5 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,006379/365=0,00001749",
				"pp_p6 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,003716/365=0,00001018",
				"Tarifa 3.0TD con 6 periodos P1-P6",
				"Coste Exceso Potencia incluido: 118,65 €",
				"Coste Energía Reactiva incluido: 55,08 €",
				"energia_facturada_kwh calculada como suma de consumos por periodo: P2(3879)+P3(2444)+P6(1903)=10226 kWh",
				"pe_p1=0 y pe_p4=pe_p5=0 porque consumo es 0 kWh en esos periodos",
				"alq_eq_dia calculado como 5,94/30=0,198 €/día"
			]
		},
		"margen_de_error": 9.16
	},
	"Fsmstate": "01_DENTRO_ZONA",
	"FsmPrevious": null,
	"ce": {
		"nombre": "Ayuntamiento Robregordo",
		"direccion": "",
		"status": "Waiting list",
		"etiqueta": "",
		"id_generacion": "230641000154599216"
	},
	"session_id": "29adb900-ba1d-4feb-ad86-3f6e1e54ed0d",
	"dealId": "230641000182098126",
	"mpklogId": "230641000182326253"
}

---

## Bloco `cliente`

Dados do cliente, preenchidos pelo frontend antes de enviar.

| Campo | Valor exemplo | O que é |
|---|---|---|
| `nombre` / `apellidos` | "Flow Test" | Nome e apelidos |
| `correo` | "Test@gmail.com" | Email — usado para buscar `dealId` no Zoho CRM |
| `telefono` | "654789123" | Telefone |
| `direccion` | "Robregordo..." | Morada |
| `lat` / `lon` | 41.10 / -3.59 | Coordenadas GPS (geolocalização do endereço) |
| `dealId` | "230641000182098126" | ID do negócio no Zoho CRM. O servidor busca-o por email após o Zoho Flow criar o registo |
| `mpklogId` | "230641000182326253" | ID do log MPK no Zoho CRM. Igual ao dealId mas de outro módulo |
| `databaseId` / `dni` | "" | Opcionais, enviados pelo frontend se disponíveis |
| `tipoVenta` | "Alquiler" | Tipo de venda (Alquiler / Compra / etc.) |

---

## Bloco `factura`

### Identificação

| Campo | Valor | O que é | Fonte |
|---|---|---|---|
| `cups` | "ES0021000010960268KY0F" | Código universal do ponto de suministro (como um NIF da instalação eléctrica). Sempre começa por "ES" + 20 dígitos | PDF — extraído pelo Claude |
| `comercializadora` | "QUANTIUM LUX 6.4, SL" | Empresa que vende a electricidade | PDF |
| `distribuidora` | "IBERDROLA DISTRIBUCIÓN..." | Empresa dona da rede (não muda com o fornecedor) | PDF |
| `tarifa_acceso` | "3.0TD" | Tarifa contratada. 2.0TD = doméstica, 3.0TD = trifásica/industrial, 6.1TD = grande consumo | PDF |
| `periodo_inicio` / `periodo_fin` | "31/10/2025" / "30/11/2025" | Início e fim do período faturado | PDF |
| `dias_facturados` | "30" | Número de dias do período. Aqui 31/10 → 30/11 = 30 dias | PDF |
| `importe_factura` | 1895.42 | Total da fatura em €. É o valor final que aparece no rodapé da fatura | PDF |

---

### Preços de Potência — `pp_p1` a `pp_p6`

**Unidade sempre em €/kW·dia** (o Claude converte se a fatura usar outra unidade).

Estes valores representam o custo diário por cada kW contratado em cada período.

| Campo | Valor | Cálculo original | Significado |
|---|---|---|---|
| `pp_p1` | 0.00014756 | 0.053859 €/kW·ano ÷ 365 | Preço da potência no período de ponta (P1) |
| `pp_p2` | 0.00007696 | 0.028087 €/kW·ano ÷ 365 | Período chão (P2) |
| `pp_p3` | 0.00003200 | 0.011678 €/kW·ano ÷ 365 | P3 |
| `pp_p4` | 0.00002763 | 0.010086 €/kW·ano ÷ 365 | P4 |
| `pp_p5` | 0.00001749 | 0.006379 €/kW·ano ÷ 365 | P5 |
| `pp_p6` | 0.00001018 | 0.003716 €/kW·ano ÷ 365 | P6 — período supervale |

> **Como usar:** `pp_p1 × pot_p1_kw × dias_facturados` = importe da potência contratada em P1.
> Ex: `0.00014756 × 22 kW × 30 dias = 0.097 €`

> **Conversão:** A fatura Quantium vinha em **€/kW·ano**. O Claude dividiu por 365 para obter €/kW·dia. O campo `otros.observacion` regista esta conversão linha a linha.

---

### Preços de Energia — `pe_p1` a `pe_p6`

**Unidade: €/kWh** — sem conversão, valor directo da fatura.

| Campo | Valor | Significado |
|---|---|---|
| `pe_p1` | 0.0 | P1 não teve consumo → preço 0 (há consumo 0 neste período) |
| `pe_p2` | 0.163966 | Preço da energia consumida em P2 |
| `pe_p3` | 0.143213 | Preço em P3 |
| `pe_p4` | 0.0 | Sem consumo em P4 |
| `pe_p5` | 0.0 | Sem consumo em P5 |
| `pe_p6` | 0.125853 | Preço em P6 (supervale — mais barato) |

> **Regra:** `null` = período não existe na tarifa. `0.0` = período existe mas não houve consumo. Neste caso 3.0TD tem 6 períodos, por isso os períodos sem consumo ficam `0.0`.

> **Como usar:** `pe_p2 × consumo_p2_kwh` = custo da energia em P2.
> Ex: `0.163966 × 3879 kWh = 635.87 €`

---

### Potências Contratadas — `pot_p1_kw` a `pot_p6_kw`

**Unidade: kW** — potência máxima contratada em cada período.

| Campo | Valor | Fonte |
|---|---|---|
| `pot_p1_kw` | 22.0 kW | API Ingebau (base de dados de contadores) |
| `pot_p2_kw` a `pot_p6_kw` | 27.7 kW | API Ingebau |

> P1 tem potência menor (22 kW) — é o período de ponta, onde contratar mais potência é mais caro. Os outros períodos têm 27.7 kW.

---

### Consumos — `consumo_p1_kwh` a `consumo_p6_kwh`

**Unidade: kWh** — energia efectivamente consumida em cada período.

| Campo | Valor | Fonte |
|---|---|---|
| `consumo_p1_kwh` | 0.0 | Sem consumo em P1 (ponta) |
| `consumo_p2_kwh` | 3879.0 | API Ingebau |
| `consumo_p3_kwh` | 2444.0 | API Ingebau |
| `consumo_p4_kwh` | 0.0 | Sem consumo |
| `consumo_p5_kwh` | 0.0 | Sem consumo |
| `consumo_p6_kwh` | 1903.0 | API Ingebau |

> **Total consumido:** P2 + P3 + P6 = 3879 + 2444 + 1903 = **8226 kWh** neste mês.

---

### Impostos e Serviços

| Campo | Valor | O que é | Cálculo |
|---|---|---|---|
| `imp_ele` | 5.11269 | Imposto sobre a electricidade em % | `base × 5.11269% = IEE em €` |
| `imp_ele_eur_kwh` | null | Formato alternativo pós-2026 (€/kWh). Null = esta fatura usa o formato % | — |
| `iva` | 21 | IVA em % | — |
| `alq_eq_dia` | 0.198 | Aluguer do contador em €/dia | `5.94 € ÷ 30 dias = 0.198 €/dia` |
| `bono_social` | null | Desconto social para famílias vulneráveis. Null = não se aplica | — |

---

### Novos Campos de Importes Totais

Subtotais em € extraídos directamente da fatura (não calculados a partir de preços × quantidades).

| Campo | Valor | O que é |
|---|---|---|
| `impuesto_electricidad_importe` | 75.90 € | Valor total do IEE na fatura |
| `alquiler_equipos_medida_importe` | 5.94 € | Valor total do aluguer do contador no período |
| `IVA_TOTAL_EUROS` | 328.96 € | Valor total do IVA cobrado |

---

### Bloco `IVA`

Detalhe do IVA, suporta dois tipos (caso existam taxas diferentes na mesma fatura).

```json
"IVA": {
  "IVA_PERCENT_1": 21,              // Tipo único: 21%
  "IVA_PERCENT_2": null,            // Null = não há segundo tipo de IVA
  "IVA_BASE_IMPONIBLE_1": 1566.46,  // Base tributável: soma de todos os conceitos antes do IVA
  "IVA_BASE_IMPONIBLE_2": null,
  "IVA_SUBTOTAL_EUROS_1": 328.96,   // 1566.46 × 21% = 328.96 €
  "IVA_SUBTOTAL_EUROS_2": null,
  "IVA_TOTAL_EUROS": 328.96         // Total IVA = soma dos dois subtotais
}
```

> Se a fatura aplicasse IVA reduzido a uma parte (ex: 10% ao aluguer + 21% ao resto), `IVA_PERCENT_2 = 10` e os campos `_2` estariam preenchidos.

---

### Grupos Aninhados

Repetem os campos planos em formato agrupado para facilitar o consumo pelo frontend.

| Grupo | Conteúdo |
|---|---|
| `potencias_kw` | `{p1: 22.0, p2: 27.7, ..., p6: 27.7}` — igual a `pot_p*_kw` |
| `consumos_kwh` | `{p1: 0.0, p2: 3879.0, ..., p6: 1903.0}` — igual a `consumo_p*_kwh` |
| `precios_potencia` | `{p1: 0.00014756, ..., p6: 0.00001018}` — igual a `pp_p*` |
| `precios_energia` | `{pe_p1: 0.0, pe_p2: 0.163966, ..., pe_p6: 0.125853}` — igual a `pe_p*` |
| `impuestos` | `{imp_ele, imp_ele_eur_kwh, iva, IVA}` — todos os impostos juntos |

> Existem tanto os campos planos (ex: `pp_p1`) como os grupos (ex: `precios_potencia.p1`) — **são o mesmo valor**, em formatos diferentes para retrocompatibilidade.

---

### Bloco `otros`

Conceitos que não têm campo fixo no modelo — variam por comercializadora.

```json
"otros": {
  "alq_eq_dia": 0.198,        // Retrocompatibilidade — igual ao campo raíz
  "cuotaAlquilerMes": null,   // Calculado pelo frontend (alq_eq_dia × 30)

  "costes": {
    // Conceitos que AUMENTAM o total da fatura (sempre positivos)
    "bono_social_importe": null,              // Não há bono social
    "exceso_potencia_importe": 118.65,        // Penalização por exceder a potência contratada
    "alquiler_equipos_medida_importe": 5.94,  // Total do aluguer (= campo raíz)
    "coste_energia_reactiva": 55.08           // Cobrança por energia reactiva (cos φ < mínimo)
  },

  "creditos": {
    // Conceitos que REDUZEM o total (sempre negativos)
    "compensacion_excedentes_kwh": null,      // Autoconsumo — kWh excedentes não se aplica
    "compensacion_excedentes_importe": null   // Compensação monetária por excedentes
  },

  "observacion": [
    // Notas do Claude sobre o processo de extracção
    "pp_p1 convertido de €/kW/año a €/kW/día dividiendo por 365: 0,053859/365=0,00014756",
    // ... uma linha por cada conversão ou decisão relevante
    "pe_p1=0 y pe_p4=pe_p5=0 porque consumo es 0 kWh en esos periodos",
    "alq_eq_dia calculado como 5,94/30=0,198 €/día"
  ]
}
```

**Significado dos sub-campos de `costes`:**

| Campo | Valor | O que é |
|---|---|---|
| `exceso_potencia_importe` | 118.65 € | Penalização aplicada quando o consumo instantâneo ultrapassou a potência contratada. Comum em 3.0TD com instalações industriais |
| `coste_energia_reactiva` | 55.08 € | Cobrança por energia reactiva excessiva. Aparece quando o factor de potência (cos φ) está abaixo de 0.95 — indica equipamentos não eficientes (motores, transformadores) |
| `alquiler_equipos_medida_importe` | 5.94 € | Mesmo valor que `alquiler_equipos_medida_importe` no raíz — incluído aqui para o cálculo de cuadre |

---

### `margen_de_error`

| Campo | Valor | O que é |
|---|---|---|
| `margen_de_error` | 9.16 | Desvio percentual entre a soma dos conceitos extraídos e o `importe_factura` |

**Fórmula:**
```
soma = imp_termino_potencia_eur
     + imp_termino_energia_eur
     + imp_impuesto_electrico_eur (75.90)
     + imp_alquiler_eur (5.94)
     + imp_iva_eur (328.96)
     + exceso_potencia_importe (118.65)
     + coste_energia_reactiva (55.08)
     - descontos (0)

margen_de_error = |soma - 1895.42| / 1895.42 × 100
```

> **9.16% significa** que a soma dos conceitos que o Claude conseguiu identificar difere 9.16% do total da fatura. Valores abaixo de 5% são considerados bons. Acima disso pode haver algum conceito não capturado, ou imprecisão nos subtotais extraídos.

---

## Campos de Contexto (raíz do payload)

| Campo | Valor | O que é |
|---|---|---|
| `Fsmstate` | "01_DENTRO_ZONA" | Estado da máquina de estados do Zoho Flow — indica em que fase do processo está o cliente |
| `FsmPrevious` | null | Estado anterior (null = primeiro estado) |
| `session_id` | "29adb900-..." | UUID da sessão temporária criada no servidor. Válida 40 minutos. Usada pelo frontend para ler estes dados via `GET /sesion/{id}` |
| `dealId` | "230641000182098126" | ID do negócio no Zoho CRM (repetido aqui por conveniência) |
| `mpklogId` | "230641000182326253" | ID do log MPK no Zoho CRM (repetido aqui) |

---

## Bloco `ce`

Dados da comunidade energética associada.

| Campo | Valor | O que é |
|---|---|---|
| `nombre` | "Ayuntamiento Robregordo" | Nome da CE |
| `direccion` | "" | Morada da CE |
| `status` | "Waiting list" | Estado do cliente na CE (Available / Waiting list / etc.) |
| `etiqueta` | "" | Etiqueta interna |
| `id_generacion` | "230641000154599216" | ID do ponto de geração associado |

---

## Resumo Visual do Fluxo de Dados

```
PDF da fatura
    │
    ▼
Claude lê o PDF
    ├─ cups, comercializadora, tarifa → campos de identificação
    ├─ preços potência (converte €/kW·ano ÷ 365) → pp_p*
    ├─ preços energia (directo €/kWh) → pe_p*
    ├─ impostos (IEE %, IVA %, aluguer €/dia) → imp_ele, iva, alq_eq_dia
    ├─ subtotais € de cada bloco → imp_termino_*_eur
    ├─ conceitos extra → otros.costes / otros.creditos
    ├─ notas do processo → otros.observacion
    ├─ bloco IVA estruturado → IVA { }
    └─ validação interna → margen_de_error
    │
    ▼
API Ingebau (por CUPS)
    ├─ potências contratadas → pot_p*_kw
    └─ consumos do período → consumo_p*_kwh
    │
    ▼
Servidor monta o payload
    ├─ agrupa campos em potencias_kw, consumos_kwh, precios_*, impuestos
    ├─ calcula cuotaAlquilerMes (frontend)
    ├─ busca dealId / mpklogId no Zoho CRM
    └─ cria sessão → session_id
    │
    ▼
payload completo guardado na sessão + enviado ao Zoho Flow
```
