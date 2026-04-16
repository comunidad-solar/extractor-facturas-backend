# Prompt — Lectura y extracción de facturas eléctricas (mercado español)

> Prompt reutilizable para indicar a un agente cómo leer una factura eléctrica en PDF (Iberdrola, Endesa, Naturgy, Repsol, TotalEnergies, etc.) y producir **dos archivos de salida simultáneamente**: `<nombre>.md` (humano) y `<nombre>.json` (máquina), sin omitir información.

---

## Objetivo

Dado un PDF de factura eléctrica española, el agente debe:

1. Leer el PDF **completo** (todas las páginas).
2. Extraer **exhaustivamente** todos los datos visibles y textos legales.
3. Generar **dos archivos** con el mismo stem que el PDF:
   - `<stem>.md` — versión legible en Markdown con 20 secciones estructuradas.
   - `<stem>.json` — versión estructurada en JSON con 24 claves raíz.
4. Ejecutar validaciones de coherencia y documentar advertencias.
5. Confirmar que el JSON valida con `json.load` antes de entregar.

Los dos archivos deben contener **exactamente la misma información**, sólo diferentes en formato.

---

## Workflow obligatorio

```
[1] Leer PDF completo (todas las páginas)
        ↓
[2] Extraer bloques 1–20 distinguiendo facturado / desagregado / lectura (R12)
        ↓
[3] Ejecutar validaciones R1–R7 (coherencia + reconciliación R13)
        ↓
[4] Generar <stem>_ai.md (humano, plantilla 21 secciones)
        ↓
[5] Generar <stem>_ai.json (AI completo, 24 claves raíz, anidado)
        ↓
[5b] Generar <stem>_processed.json (plano, schema endpoint, validacion_cuadre + otros + error)
        ↓
[6] Validar JSON con `python3 -c "import json; json.load(open('...'))"` (ambos JSONs)
        ↓
[7] Registrar advertencias de coherencia si las hubiere
        ↓
[8] Reportar al usuario: ruta de los 3 archivos + resumen de validaciones + cuadre
```

**Convención de nombres (3 outputs por PDF):**
- `<stem>_ai.md` — human readable, 21 secciones
- `<stem>_ai.json` — extracción AI completa, anidada, 24 claves raíz
- `<stem>_processed.json` — formato plano compatible con endpoint del backend, con `validacion_cuadre`, `otros` y `error`

---

## Instrucciones de lectura

### 1. Lectura página por página (obligatorio)

No asumas que toda la información está en la primera página. Una factura típica tiene **4 páginas**:

- **Página 1 — Portada / resumen**
  - Datos del titular, nº factura, nº contrato, periodo, total, potencia contratada, plan, contactos principales, dirección de suministro.
  - Sellos y certificaciones del emisor (AENOR, IQNet, PEFC, etc.).
  - Códigos de barras y referencias postales (remite, códigos internos).
- **Página 2 — Detalle de factura**
  - Gráfica de evolución de consumo, consumo medio diario.
  - Desglose ENERGÍA, CARGOS NORMATIVOS, SERVICIOS y totales.
  - Datos técnicos: CUPS, ATR, contador, distribuidora, IBAN, BIC, etc.
  - Lecturas desagregadas (P1/P2/P3), consumos desagregados, potencias máximas demandadas.
  - Desglose de peajes sin impuestos.
  - Distribución porcentual del coste (energía / peajes / impuestos / cargos).
  - **Notas legales al pie** (RDL 8/2023 sobre impuesto eléctrico, nota sobre compensación de excedentes, etc.).
- **Página 3 — Textos legales**
  - Texto completo de reclamaciones (dirección postal, junta arbitral, plazos).
  - RDL 8/2023 aplicable al IVA.
  - Promociones vigentes (ej.: 50 % Pack Hogar × 4 meses).
  - Enlaces a comparador CNMC.
- **Página 4 — Información ambiental**
  - Mix de generación (comercializadora vs. nacional).
  - Emisiones CO₂ y residuos radiactivos + escala A–G.
  - Etiquetado global del año anterior (ej.: categoría D = media nacional).

### 2. Extracción por bloques

Para cada factura, extraer los siguientes bloques **en este orden**. Si un bloque no está presente en el PDF, registrarlo como `null`/"no aplica", no omitirlo.

#### Bloque 1 — Identificación del documento
- Tipo de documento (Factura de electricidad / Factura rectificativa / Abono)
- Nº de factura
- Fecha de emisión (formato ISO: `YYYY-MM-DD`)
- Nº de páginas del documento
- Periodo de facturación (inicio / fin) en ISO
- Días facturados
- Fecha prevista de cobro
- Referencia del código de barras
- Códigos internos visibles en el pie/lateral

#### Bloque 2 — Emisor (comercializadora)
- Nombre legal
- CIF
- Domicilio fiscal
- Domicilio social
- Registro Mercantil (tomo, folio, hoja)
- Dirección de correos (remite)
- Marca / web / email / app

#### Bloque 3 — Cliente
- Titular
- NIF del titular
- Dirección completa de suministro (calle, CP, municipio, provincia)

#### Bloque 4 — Contrato
- Plan contratado (nombre comercial)
- Nº de contrato
- Fecha final del contrato
- Permanencia (Sí/No)
- Potencia contratada por franja (P1/P2/…/P6 en kW)
- Peaje de acceso / tarifa (ATR: 2.0TD, 3.0TD, 6.1TD, etc.)
- Mercado (Libre / Regulado / PVPC)
- Segmento tarifario
- CUPS (Código Universal del Punto de Suministro)
- Nº de contador
- Nº de contrato de acceso
- Empresa distribuidora + web
- Precios peajes acceso (referencia B.O.E.)
- Garantía de origen de la energía (Renovable %, mix, etc.)

#### Bloque 5 — Forma de pago
- Tipo (Domiciliación / Transferencia / Tarjeta)
- IBAN (con asteriscos si vienen ocultos por seguridad)
- BIC
- Código de mandato SEPA

#### Bloque 6 — Resumen económico
- Energía (€)
- Descuentos energía (€, con signo)
- Cargos normativos (€)
- Servicios y otros conceptos (€)
- Base IVA (€)
- IVA (€)
- **TOTAL factura (€)**

#### Bloque 7 — Detalle ENERGÍA (desglose línea a línea)
Para **cada línea** del detalle, capturar: concepto, cálculo literal (ej.: `6,9 kW × 24 días × 0,113358 €/kW·día`), importe.

- Potencia facturada por franja (P1…P6)
- Total potencia
- Energía consumida por franja + precio unitario
- Descuentos sobre consumo (% y base)
- **Compensación de excedentes** (si aplica): kWh vertidos, precio €/kWh, importe
- **Nota legal literal** sobre compensación de excedentes

#### Bloque 8 — Cargos normativos
- Financiación bono social
- Impuesto sobre electricidad (% + base)
- Total bloque energía
- **Nota legal RDL 8/2023** sobre impuesto eléctrico

#### Bloque 9 — Servicios y otros conceptos
- Alquiler equipos de medida
- Packs/servicios adicionales + descuentos
- Subtotal servicios
- Importe base IVA
- IVA (%, base, importe)
- **Nota legal RDL 8/2023** sobre IVA (si aparece)
- Total factura

#### Bloque 10 — Precios unitarios (resumen)
Listar todos los precios unitarios extraídos:
- Potencia €/kW·día por franja
- Energía €/kWh por franja
- Compensación excedentes €/kWh
- Bono social €/día
- Alquiler contador €/día
- Impuesto eléctrico %
- IVA %

#### Bloque 11 — Consumo

Organizado en **3 sub-bloques** según autoritividad (ver R12):

##### 11.1 Consumo facturado (🟢 vinculante para el cálculo del importe)
- `energia_facturada_kwh`: valor X en la línea `Energía consumida X kWh × Y €/kWh = Z €`.
- `precio_facturado_eur_kwh`: valor Y de esa línea.
- `importe_facturado_eur`: resultado Z de esa línea.
- **Verificación R12:** X × Y debe ser ≈ Z (tolerancia 0,02 €).

##### 11.2 Consumos desagregados por franja (🟡 informativo)
- `desagregado_kwh.p1..p6` desde `Sus consumos desagregados han sido…`.
- Consumo medio diario factura (€)
- Consumo medio diario últimos N meses (€)
- Consumo medio CP (kWh, referencia comparativa)
- **Nota obligatoria:** en facturas con autoconsumo, la suma de desagregados puede ser mayor que `energia_facturada_kwh` (diferencia = autoconsumo instantáneo).

##### 11.3 Lecturas del contador (🔴 informativo, nunca vinculante)
- Tipo de lecturas (Reales / Estimadas)
- Fecha de lectura
- Lecturas acumuladas por franja (kWh) — del tablón "Las lecturas desagregadas según la tarifa"
- Potencias máximas demandadas en el último año (P1/P2)
- Maxímetros del periodo (si aparecen en tabla estructurada, tarifa 3.0TD)
- Energía reactiva por franja (kVArh, si aparece)

#### Bloque 12 — Autoconsumo
- Compensación de excedentes (Sí/No)
- Energía compensada (kWh)
- Importe compensado (€)
- Solar Cloud / app de monitorización (Sí/No)
- Modalidad de autoconsumo si se indica

#### Bloque 13 — Peajes de acceso (sin impuestos)
- Peajes totales + desglose (potencia / energía / alquiler contador)
- Impuestos aplicables indicados
- Nota sobre si están englobados en el total

#### Bloque 14 — Distribución porcentual del coste
- Energía %
- Peajes transporte y distribución %
- Impuestos %
- Alquiler contador %
- Bono social %
- Cargos % (y su desglose: anualidades déficit, sobrecoste no peninsular, renovables/cogeneración/residuos, otros)

#### Bloque 15 — Origen de la electricidad (mix)
- Año de referencia
- Mix de la comercializadora (Renovable, Cogeneración, CC Gas Natural, Carbón, Fuel/Gas, Nuclear, Otras no renovables)
- Mix nacional (mismos campos)
- Texto introductorio literal

#### Bloque 16 — Impacto medioambiental
- Emisiones CO₂ eq. (g/kWh) comercializadora + media nacional + escala A–G
- Residuos radiactivos de alta actividad (µg/kWh) + escala
- Etiquetado global del año (categoría A–G y su significado literal)

#### Bloque 17 — Observaciones legales y promociones
- Todos los textos con "(*)" o notas a pie:
  - RDL 8/2023 — impuesto eléctrico
  - RDL 8/2023 — IVA
  - Promociones activas (duración, importe/porcentaje)
- Enlaces a comparador CNMC, gdo.cnmc.es, etc.

#### Bloque 18 — Reclamaciones
- **Texto literal completo** (no parafrasear)
- Apartado de correos
- Teléfono Junta Arbitral
- Plazo indicado

#### Bloque 19 — Contactos
- Canal digital (web, app, email, área cliente, web de consejos)
- Teléfonos (atención, averías, reparaciones, autoconsumo) — listarlos **todos**
- Oficinas físicas con dirección completa
- Recursos externos (distribuidora, CNMC, Junta Arbitral)

#### Bloque 20 — Metadatos
- Códigos de barras
- Código postal de distribución
- Códigos internos por página
- Certificaciones visibles (AENOR, IQNet, PEFC, Empresa Adherida, Arbitraje de Consumo)
- Certificación del papel / soporte (ej.: "PEFC. Este papel procede de bosques gestionados de forma sostenible")

---

## Reglas de extracción

### R1. Preservar textos legales literalmente
Los bloques de **notas legales** (RDL 8/2023, nota de excedentes, texto de reclamaciones, texto del etiquetado ambiental) deben conservarse **palabra por palabra**:
- En Markdown: usar blockquote `>` con el texto exacto.
- En JSON: cadena exacta dentro del campo correspondiente (ej.: `nota_legal`, `texto_literal`).

### R2. Datos numéricos
- JSON: formato **numérico nativo** (no strings), con punto decimal (ej.: `118.60`, `728.65`).
- Markdown: formato original español (coma decimal, punto de millares: `23.501 kWh`, `118,60 €`).
- Importes negativos con signo menos (ej.: `-15.61`).
- Porcentajes como número (no string con `%`), ej.: `21` no `"21%"`.

### R3. Fechas
- JSON: **ISO 8601** (`YYYY-MM-DD`).
- Markdown: formato original de la factura (DD/MM/YYYY).

### R4. IBAN / datos sensibles
- Mantener los asteriscos de los 4 últimos dígitos: `ES58 0049 4321 8122 1002 ****`
- Añadir nota "Ocultos por seguridad" en un campo auxiliar (`iban_nota`).

### R5. CUPS
- Conservar espacios y formato original: `ES 0021 0000 0574 5673 XV`
- En JSON duplicar: `cups` (sin espacios, para lookup) + `cups_formato_original` (con espacios).

### R6. Unidades
- **kWh** para energía.
- **kW** para potencia.
- **kW·día** para precio de potencia.
- **€/kWh**, **€/día**, **µg/kWh**, **g/kWh** según el campo.
- No incluir la unidad en el valor JSON — usar el nombre del campo (ej.: `precio_eur_kwh: 0.142855`).

### R7. Franjas horarias
- Nomenclatura estándar: **P1 (punta)**, **P2 (llano)**, **P3 (valle)** para tarifas 2.0TD.
- Para tarifas 3.0TD/6.1TD: P1–P6.
- Atención: a veces la factura usa "valle" tanto para **P2** (potencia) como para **P3** (consumo), depende del ATR. Contextualizar por el nº de franjas disponibles.

### R8. Campos nullables
Si un campo no aparece en el PDF, registrarlo como `null` en JSON y "no aplica" o "no indicado" en Markdown. **Nunca inventar valores.**

### R9. Detección de tipo de factura
Identificar si es:
- Factura normal
- Factura rectificativa
- Abono / nota de crédito
- Factura proforma / estimada

Buscar palabras clave: "Factura de electricidad", "Rectificativa", "Abono", "Estimada".

### R10. Autoconsumo
Si hay línea de "Compensación de excedentes" o aparece "Solar Cloud", "autoconsumo", "energía vertida":
- Marcar `compensacion_excedentes: true` (o análogo).
- Capturar kWh vertidos, precio €/kWh de compensación e importe.
- Reportar la modalidad si se indica.

### R11. Consistencia entre MD y JSON
Cada dato que aparezca en el `.md` **debe** estar también en el `.json` y viceversa. No duplicar información entre ambos: son representaciones equivalentes del mismo contenido.

### R12. Valores facturados son la ÚNICA fuente de verdad para reconciliación

**CRÍTICO.** En una factura eléctrica hay varios valores de kWh que pueden diferir entre sí. **Sólo los valores facturados** (los que aparecen en líneas con el formato `X kWh × Y €/kWh = Z €`) se usan para reconstruir el importe total.

**Jerarquía de valores (de MÁS autoritativo a SÓLO informativo):**

1. 🟢 **Valor facturado** (autoritativo — se usa para cálculo del importe):
   - Línea `Energía consumida X kWh × Y €/kWh = Z €` → `energia_facturada_kwh = X`
   - Línea `Punta X kW × N días × Y €/kW día = Z €` → `potencia_facturada_pN_kw = X`
   - Línea `Compensación de excedentes -X kWh × Y €/kWh = -Z €` → `compensacion_excedentes_kwh = -X`

2. 🟡 **Consumos desagregados** (informativo — puede no coincidir con facturado):
   - Frase `Sus consumos desagregados han sido punta: X kWh; llano: Y; valle Z`
   - En facturas **con autoconsumo**: la suma puede ser **mayor** que el facturado porque incluye autoconsumo instantáneo (consumido directamente de paneles sin pasar por la red).
   - En facturas **sin autoconsumo**: suele coincidir con el facturado.

3. 🔴 **Lecturas acumuladas del contador** (informativo — nunca vinculante):
   - Frase `Las lecturas desagregadas según la tarifa de acceso, tomadas el DD/MM/YYYY son: punta: X kWh; ...`
   - Son los totales del contador; no tienen relación con kWh del periodo facturado.

**Regla dorada:** para reconstruir el importe total, usar **siempre** los valores facturados (categoría 1). Los valores de categoría 2 y 3 son sólo para reporting.

**Ejemplo práctico (iberdrola_1):**
- Energía consumida (facturada): `728,65 kWh × 0,142855 €/kWh = 104,09 €` ✅
- Desagregados: `107 + 142 + 510 = 759 kWh` (≠ 728,65) — diferencia por autoconsumo.
- Si multiplicamos mal: `759 × 0,142855 = 108,42 €` ≠ importe real → rompe la factura.

### R13. Reconciliación contable obligatoria (cuadre)

Antes de finalizar la extracción, calcular el sumatorio de todos los conceptos facturados y comparar con el `total_factura`:

```
suma_conceptos = potencia_facturada_total
               + energia_facturada_importe
               + sum(descuentos_importes)            (normalmente negativos)
               + compensacion_excedentes_importe     (negativo si existe)
               + bono_social_importe
               + impuesto_electricidad_importe
               + sum(servicios_importes)             (alquiler + packs + asistencias + etc.)
               + iva_total
```

Comparar con `total_factura` (tolerancia 0,02 €).

**Si cuadra:** registrar en `validacion_cuadre.cuadra: true` del `_processed.json`.

**Si NO cuadra:**
1. Revisar el detalle de la factura línea por línea buscando importes en € no capturados.
2. Cualquier línea no clasificable en los conceptos estándar va al campo `otros: { "<descripción>": <importe> }`.
3. Si tras añadir `otros` sigue sin cuadrar, poblar el campo `error` del `_processed.json` con:
   ```
   "error": "Suma de conceptos (XX,XX €) no cuadra con el importe factura (YY,YY €). Diferencia: Z,ZZ €."
   ```

**Nunca ajustar valores para forzar cuadre.** El `error` es la señal para el sistema downstream.

---

## Validaciones de coherencia (obligatorias)

Antes de entregar la extracción, comprobar:

1. **Suma del resumen = total**: `energía + descuentos + cargos_normativos + servicios_y_otros + IVA ≈ TOTAL factura` (tolerancia 0,02 €).
2. **Energía facturada × precio = importe**: `energia_facturada_kwh × precio_eur_kwh ≈ importe_energia_facturada` (tolerancia 0,02 €). **Esta es la validación real** — NO comparar con suma de desagregados.
2b. **(Informativo)** `sum(desagregados) - energia_facturada_kwh`. Si la diferencia > 1 kWh y **no hay autoconsumo**, documentar como advertencia. Si hay autoconsumo, es esperado — marcar como `SKIP`.
3. **Base IVA × % IVA ≈ IVA**: (tolerancia 0,01 €). Si hay IVA split, validar cada tramo por separado.
4. **Peajes sin impuestos (detalle) = suma (potencia + energía + alquiler contador)** (tolerancia 0,01 €).
5. **Porcentajes de distribución del coste ≈ 100 %** (tolerancia 0,5 %).
6. **Mix energético ≈ 100 %** para comercializadora y para nacional.
7. **Reconciliación contable (R13)**: `suma_conceptos ≈ total_factura` (tolerancia 0,02 €). Si falla → `otros` + `error` en `_processed.json`.

Si alguna validación **falla**, añadir una sección `Advertencias` (en Markdown) y una clave `advertencias` (en JSON) con:
- `tipo`: identificador corto (ej.: `"coherencia_consumo"`).
- `descripcion`: descripción de la discrepancia con valores concretos.

**Nunca ajustar valores para forzar que una validación pase.** Reportar la discrepancia tal cual aparece en el PDF.

---

## Plantilla Markdown (`<stem>.md`)

Usar **exactamente** esta estructura:

```markdown
# Factura <comercializadora> — Extracción completa

**Archivo fuente:** `<stem>.pdf`
**Tipo de documento:** <tipo>
**Nº factura:** <numero>
**Total:** <importe> €
**Fecha emisión:** DD/MM/YYYY
**Nº de páginas:** <n>

---

## 1. Emisor (comercializadora)
- **Empresa:** ...
- **CIF:** ...
- **Domicilio fiscal:** ...
- **Domicilio social:** ...
- **Registro Mercantil:** ...
- **Dirección de correos (remite):** ...

---

## 2. Cliente / titular
- **Titular:** ...
- **NIF:** ...
- **Dirección de suministro:**
  - <calle>
  - <CP> <municipio> (<provincia>)

---

## 3. Datos de la factura
- **Nº de factura:** ...
- **Nº de contrato:** ...
- **Periodo de facturación:** DD/MM/YYYY – DD/MM/YYYY
- **Días facturados:** N
- **Fecha de emisión:** DD/MM/YYYY
- **Fecha prevista de cobro:** DD/MM/YYYY
- **TOTAL factura:** **X,XX €**

---

## 4. Datos técnicos del contrato / suministro
- **Plan contratado:** ...
- **Potencia punta (P1):** X,X kW
- **Potencia valle (P2):** X,X kW
- **Peaje acceso (ATR):** 2.0TD | 3.0TD | 6.1TD | ...
- **Mercado:** Libre | Regulado | PVPC
- **Segmento tarifario:** N
- **CUPS:** ES XXXX XXXX XXXX XXXX XX
- **Nº contador:** ...
- **Nº contrato de acceso:** ...
- **Empresa distribuidora:** ...
- **Web distribuidora:** ...
- **Fecha final del contrato:** DD/MM/YYYY
- **Permanencia:** Sí | No
- **Precios peajes acceso:** B.O.E. DD/MM/YYYY
- **Energía con garantía de origen:** Renovable X %

---

## 5. Forma de pago
- **Tipo:** Domiciliación bancaria
- **IBAN:** ES.. XXXX XXXX XXXX XXXX **** (últimos 4 dígitos ocultos por seguridad)
- **BIC:** ...
- **Código de mandato:** ...

---

## 6. Resumen económico
- **Energía:** X,XX €
- **Descuentos energía:** −X,XX €
- **Cargos normativos:** X,XX €
- **Servicios y otros conceptos:** X,XX €
- **IVA:** X,XX €
- **TOTAL:** **X,XX €**

---

## 7. Detalle ENERGÍA

### 7.1 Potencia facturada
- **Punta:** X kW × N días × X €/kW·día = **X,XX €**
- **Valle:** X kW × N días × X €/kW·día = **X,XX €**
- **Total potencia:** **X,XX €**

### 7.2 Consumo
- **Energía consumida:** X kWh × X €/kWh = **X,XX €**

### 7.3 Descuentos aplicados
- **Descuento X % s/consumo:** X % s/base = **−X,XX €**

### 7.4 Compensación de excedentes (autoconsumo)
- **Energía vertida:** −X kWh × X €/kWh = **−X,XX €**
- **Nota legal (literal de la factura):**
  > <texto literal>

---

## 8. Cargos normativos
- **Financiación bono social fijo:** N días × X €/día = **X,XX €**
- **Impuesto sobre electricidad:** X % s/base = **X,XX €**
- **Total Energía (bloque completo):** **X,XX €**

> **Nota legal:** <texto literal RDL 8/2023 impuesto eléctrico>

---

## 9. Servicios y otros conceptos
- **Alquiler equipos medida:** N días × X €/día = **X,XX €**
- **Pack Iberdrola Hogar:** N meses × X €/mes = **X,XX €**
- **Descuento Pack:** X % s/base = **−X,XX €**
- **Subtotal servicios:** **X,XX €**

### 9.1 Cálculo final
- **Importe total (base IVA):** X,XX €
- **IVA (X % s/base):** X,XX €
- **TOTAL FACTURA:** **X,XX €**

> **Nota legal IVA:** <texto literal RDL 8/2023 IVA>

---

## 10. Precios unitarios (resumen)

### 10.1 Potencia
- **Precio potencia punta:** X,XXXXXX €/kW·día
- **Precio potencia valle:** X,XXXXXX €/kW·día

### 10.2 Energía
- **Precio energía consumida:** X,XXXXXX €/kWh
- **Precio compensación de excedentes:** X,XX €/kWh

### 10.3 Otros conceptos
- **Bono social fijo:** X,XXXXXX €/día
- **Alquiler de contador:** X,XXXXXX €/día
- **Impuesto sobre electricidad:** X,XXXXXX %
- **IVA aplicado:** XX %

---

## 11. Consumo

### 11.1 Resumen
- **Consumo total factura:** X kWh
- **Consumo medio diario (factura):** X,XX €
- **Consumo medio diario (últ. N meses):** X,XX €
- **Consumo medio CP (referencia):** X,XX kWh

### 11.2 Consumo desagregado por franja
- **Punta (P1):** X,XX kWh
- **Llano (P2):** X,XX kWh
- **Valle (P3):** X,XX kWh

### 11.3 Lecturas tomadas el DD/MM/YYYY
- **Tipo de lecturas:** Reales | Estimadas
- **Punta:** X kWh
- **Llano:** X kWh
- **Valle:** X kWh

### 11.4 Potencias máximas demandadas (último año)
- **P1 (punta):** X,XX kW
- **P2 (valle):** X,XX kW

---

## 12. Autoconsumo
- **Compensación de excedentes:** Sí | No
- **Energía compensada:** X,XX kWh
- **Importe compensado:** −X,XX €
- **Solar Cloud disponible:** Sí | No
- **Energía 100 % renovable** con Garantía de Origen emitida por la CNMC

---

## 13. Peajes de acceso (sin impuestos)
- **Peajes totales:** X,XX €
  - Potencia: X,XX €
  - Energía: X,XX €
  - Alquiler contador: X,XX €
- **Impuestos aplicables:** ...
- **Nota:** <texto literal>

---

## 14. Distribución del coste (%)
- **Energía:** X,X %
- **Peajes transporte y distribución:** X,X %
- **Impuestos:** X,X %
- **Alquiler contador:** X,X %
- **Bono social:** X,X %
- **Cargos:** X,X %
  - Anualidades del déficit: X,X %
  - Sobrecoste generación no peninsular: X,X %
  - Renovables, cogeneración y residuos: X,X %
  - Otros: X,X %
- **Total impuestos y cargos:** **X,X %**

---

## 15. Origen de la electricidad (mix <año>)

> <texto introductorio literal>

### 15.1 <comercializadora>
- Renovable: X,X %
- Cogeneración alta eficiencia: X,X %
- CC Gas Natural: X,X %
- Carbón: X,X %
- Fuel/Gas: X,X %
- Nuclear: X,X %
- Otras no renovables: X,X %

### 15.2 Mix de generación nacional
- (mismos campos)

---

## 16. Impacto medioambiental

### 16.1 Emisiones de CO₂ equivalente
- **<comercializadora>:** X g/kWh — escala **A–G**
- **Media nacional:** X g/kWh

### 16.2 Residuos radiactivos de alta actividad
- **<comercializadora>:** X µg/kWh — escala **A–G**
- **Media nacional:** X µg/kWh

### 16.3 Etiquetado global <año>
> <texto literal sobre la categoría global asignada>

---

## 17. Observaciones legales y contractuales
- **RDL 8/2023 (impuesto eléctrico):** <texto literal>
- **RDL 8/2023 (IVA):** <texto literal>
- **Promoción de bienvenida:** <descripción con %, duración, producto>
- **Comparador oficial de ofertas (CNMC):** https://comparador.cnmc.gob.es

---

## 18. Reclamaciones (texto literal)

> <texto literal completo>

---

## 19. Contactos y canales de atención

### 19.1 Digital
- **Web:** ...
- **Área cliente:** ...
- **Email:** ...
- **App:** ...
- **Consejos eficiencia:** ...

### 19.2 Teléfonos
- **Atención al cliente:** ...
- **Notificación de averías:** ...
- **Reparaciones eléctricas:** ...
- **Smart Solar / autoconsumo:** ...

### 19.3 Oficinas
- <dirección 1>
- <dirección 2>

### 19.4 Recursos externos
- **Información origen electricidad:** gdo.cnmc.es
- **Comparador oficial CNMC:** https://comparador.cnmc.gob.es
- **Junta Arbitral de Consumo:** <teléfono>
- **Apartado de Correos reclamaciones:** <código>

---

## 20. Metadatos y códigos internos del documento
- **Código de barras:** ...
- **Código postal distribución:** ...
- **Códigos internos de página:**
  - p. 1: ...
  - p. 2: ...
  - p. N: ...
- **Certificaciones del emisor:**
  - <cert 1>
  - <cert 2>
- **Certificación del papel:** PEFC — ...

---

## 21. Advertencias (sólo si hay discrepancias)
- **<tipo>:** <descripción>
```

---

## Esquema JSON (`<stem>.json`)

El JSON debe tener **24 claves raíz** en este orden:

```json
{
  "archivo_fuente": "<stem>.pdf",
  "tipo_documento": "Factura de electricidad",
  "numero_paginas": 4,
  "emisor": {
    "empresa": "...",
    "cif": "...",
    "domicilio_fiscal": "...",
    "domicilio_social": "...",
    "registro_mercantil": "...",
    "apartado_correos_remite": "..."
  },
  "cliente": {
    "titular": "...",
    "nif": "...",
    "direccion_suministro": {
      "calle": "...",
      "codigo_postal": "...",
      "municipio": "...",
      "provincia": "..."
    }
  },
  "factura": {
    "numero_factura": "...",
    "numero_contrato": "...",
    "periodo_facturacion": { "inicio": "YYYY-MM-DD", "fin": "YYYY-MM-DD" },
    "dias_facturados": 0,
    "fecha_emision": "YYYY-MM-DD",
    "fecha_prevista_cobro": "YYYY-MM-DD",
    "total": 0.00,
    "moneda": "EUR"
  },
  "contrato": {
    "plan": "...",
    "potencia_punta_kw": 0.0,
    "potencia_valle_kw": 0.0,
    "peaje_acceso": "2.0TD",
    "mercado": "Libre",
    "segmento_tarifario": 1,
    "cups": "ESXXXXXXXXXXXXXXXXXX",
    "cups_formato_original": "ES XXXX XXXX XXXX XXXX XX",
    "numero_contador": "...",
    "numero_contrato_acceso": "...",
    "empresa_distribuidora": "...",
    "web_distribuidora": "...",
    "fecha_final_contrato": "YYYY-MM-DD",
    "permanencia": false,
    "precios_peajes_acceso_boe": "YYYY-MM-DD",
    "energia_garantia_origen": "Renovable 100%"
  },
  "forma_pago": {
    "tipo": "Domiciliación bancaria",
    "iban": "ESXX XXXX XXXX XXXX XXXX ****",
    "iban_nota": "Últimos 4 dígitos ocultos por seguridad",
    "bic": "...",
    "codigo_mandato": "..."
  },
  "resumen_economico": {
    "energia": 0.00,
    "descuentos_energia": 0.00,
    "cargos_normativos": 0.00,
    "servicios_y_otros": 0.00,
    "iva": 0.00,
    "total": 0.00
  },
  "detalle_energia": {
    "potencia": {
      "punta": { "potencia_kw": 0.0, "dias": 0, "precio_eur_kw_dia": 0.0, "importe": 0.00 },
      "valle": { "potencia_kw": 0.0, "dias": 0, "precio_eur_kw_dia": 0.0, "importe": 0.00 },
      "total_potencia": 0.00
    },
    "energia_consumida": { "kwh": 0.0, "precio_eur_kwh": 0.0, "importe": 0.00 },
    "descuentos": [
      { "concepto": "...", "porcentaje": 0, "base": 0.0, "importe": 0.00 }
    ],
    "compensacion_excedentes": {
      "kwh": 0.0,
      "precio_eur_kwh": 0.0,
      "importe": 0.00,
      "nota_legal": "<texto literal>"
    }
  },
  "cargos_normativos": {
    "financiacion_bono_social_fijo": { "dias": 0, "precio_eur_dia": 0.0, "importe": 0.00 },
    "impuesto_electricidad": { "porcentaje": 0.0, "base": 0.0, "importe": 0.00 },
    "total_energia_bloque": 0.00,
    "nota_legal_rdl_8_2023": "<texto literal>"
  },
  "servicios_y_otros": {
    "alquiler_equipos_medida": { "dias": 0, "precio_eur_dia": 0.0, "importe": 0.00 },
    "pack_iberdrola_hogar": { "meses": 0.0, "precio_eur_mes": 0.0, "importe": 0.00 },
    "descuento_pack_iberdrola_hogar": { "porcentaje": 0, "base": 0.0, "importe": 0.00 },
    "subtotal_servicios": 0.00,
    "importe_total_base_iva": 0.00,
    "iva": {
      "porcentaje": 21,
      "base": 0.00,
      "importe": 0.00,
      "nota_legal_rdl_8_2023": "<texto literal>"
    },
    "total_factura": 0.00
  },
  "precios_unitarios": {
    "potencia": { "punta_eur_kw_dia": 0.0, "valle_eur_kw_dia": 0.0 },
    "energia": { "consumida_eur_kwh": 0.0, "compensacion_excedentes_eur_kwh": 0.0 },
    "otros": {
      "bono_social_fijo_eur_dia": 0.0,
      "alquiler_contador_eur_dia": 0.0,
      "impuesto_electricidad_porcentaje": 0.0,
      "iva_porcentaje": 21
    }
  },
  "consumo": {
    "total_kwh": 0.0,
    "medio_diario_eur_factura": 0.0,
    "medio_diario_eur_ultimo_mes": 0.0,
    "medio_cp_referencia_kwh": 0.0,
    "desagregado_kwh": { "punta_p1": 0.0, "llano_p2": 0.0, "valle_p3": 0.0 },
    "lecturas_fecha": "YYYY-MM-DD",
    "lecturas_tipo": "Reales",
    "lecturas_desagregadas_kwh": { "punta": 0, "llano": 0, "valle": 0 },
    "potencias_maximas_demandadas_ultimo_ano": { "p1_punta_kw": 0.0, "p2_valle_kw": 0.0 }
  },
  "autoconsumo": {
    "compensacion_excedentes": false,
    "energia_compensada_kwh": 0.0,
    "precio_compensacion_eur_kwh": 0.0,
    "importe_compensado_eur": 0.00,
    "solar_cloud": false,
    "solar_cloud_app": null,
    "energia_100_renovable": false,
    "garantia_origen_cnmc": false
  },
  "peajes_acceso_sin_impuestos": {
    "total": 0.00,
    "potencia": 0.00,
    "energia": 0.00,
    "alquiler_contador": 0.00,
    "impuestos_aplicables": "...",
    "nota": "<texto literal>"
  },
  "distribucion_coste_porcentaje": {
    "energia": 0.0,
    "peajes_transporte_distribucion": 0.0,
    "impuestos": 0.0,
    "alquiler_contador": 0.0,
    "bono_social": 0.0,
    "cargos_total": 0.0,
    "cargos_detalle": {
      "anualidades_deficit": 0.0,
      "sobrecoste_no_peninsular": 0.0,
      "renovables_cogeneracion_residuos": 0.0,
      "otros": 0.0
    },
    "impuestos_y_cargos_totales": 0.0
  },
  "origen_electricidad_mix_2023": {
    "texto_introductorio": "<texto literal>",
    "iberdrola": {
      "renovable": 0.0,
      "cogeneracion_alta_eficiencia": 0.0,
      "cc_gas_natural": 0.0,
      "carbon": 0.0,
      "fuel_gas": 0.0,
      "nuclear": 0.0,
      "otras_no_renovables": 0.0
    },
    "mix_nacional": { "...": "mismos campos" }
  },
  "impacto_medioambiental": {
    "escala": "A a G (A=mínimo impacto, G=máximo impacto, D=media nacional)",
    "emisiones_co2_eq_g_kwh": { "iberdrola": 0, "media_nacional": 0, "categoria_iberdrola": "E" },
    "residuos_radiactivos_alta_actividad_ug_kwh": { "iberdrola": 0, "media_nacional": 0, "categoria_iberdrola": "D" },
    "etiquetado_global_2023": {
      "categoria": "D",
      "significado": "...",
      "texto_literal": "<texto literal>"
    }
  },
  "observaciones_legales_y_promociones": {
    "rdl_8_2023_impuesto_electrico": "<texto literal>",
    "rdl_8_2023_iva": "<texto literal>",
    "promocion_bienvenida": {
      "descripcion": "...",
      "porcentaje": 50,
      "duracion_meses": 4,
      "producto": "..."
    },
    "comparador_cnmc": "https://comparador.cnmc.gob.es"
  },
  "reclamaciones": {
    "texto_literal": "<texto literal completo>",
    "apartado_correos": "XXXXX, XXXXX Madrid",
    "junta_arbitral_consumo_madrid": "XXX XXX XXX",
    "plazo_dias": 30
  },
  "contactos": {
    "digital": {
      "web": "...",
      "area_cliente": "...",
      "email": "...",
      "app": "...",
      "web_consejos_eficiencia": "..."
    },
    "telefonos": {
      "atencion_cliente": ["...", "..."],
      "averias_zona": "...",
      "reparaciones_hogar": ["...", "..."],
      "smart_solar_autoconsumo": "..."
    },
    "oficinas": ["...", "..."],
    "recursos_externos": {
      "origen_electricidad_cnmc": "gdo.cnmc.es",
      "comparador_ofertas_cnmc": "https://comparador.cnmc.gob.es",
      "junta_arbitral_consumo_madrid": "...",
      "apartado_correos_reclamaciones": "..."
    }
  },
  "advertencias": [
    { "tipo": "<id>", "descripcion": "<detalle>" }
  ],
  "metadatos_documento": {
    "codigo_barras": "...",
    "codigo_postal_distribucion": "...",
    "codigos_internos_por_pagina": {
      "pagina_1": "...",
      "pagina_2": "...",
      "pagina_4": ["...", "..."]
    },
    "certificaciones_emisor": ["AENOR ISO 10002", "AENOR UNE-EN-ISO 9001", "IQNet", "..."],
    "certificacion_papel": {
      "estandar": "PEFC",
      "descripcion": "...",
      "web": "www.pefc.es"
    }
  }
}
```

Si no hay advertencias, la clave `advertencias` debe contener `[]` (array vacío), no omitirla.

---

## Esquema `_processed.json` (TERCER output — flat, compatible con endpoint del backend)

Este JSON tiene un esquema **plano** equivalente al `ExtractionResponse` del endpoint `POST /facturas/extraer` del proyecto. Su finalidad es ser consumido directamente por el sistema downstream sin transformaciones adicionales.

**Reglas obligatorias:**

1. **Usar valores facturados (R12)** — no desagregados ni lecturas acumuladas.
2. **Cuadrar el importe total (R13)** — `validacion_cuadre.suma_conceptos == importe_factura` con tolerancia 0,02 €.
3. **Conceptos no estándar al campo `otros`** — cada uno como `{ "<nombre del concepto>": <importe> }`.
4. **Si el cuadre falla**, poblar `error` con descripción + diferencia.

**Schema (claves obligatorias en este orden):**

```json
{
  "cups": "ESXXXXXXXXXXXXXXXXXX",
  "periodo_inicio": "DD/MM/YYYY",
  "periodo_fin": "DD/MM/YYYY",
  "dias_facturados": "30",
  "comercializadora": "...",
  "distribuidora": "...",
  "tarifa_acceso": "2.0TD",

  "pp_p1": 0.0, "pp_p2": 0.0, "pp_p3": null, "pp_p4": null, "pp_p5": null, "pp_p6": null,
  "pe_p1": 0.0, "pe_p2": null, "pe_p3": null, "pe_p4": null, "pe_p5": null, "pe_p6": null,
  "pot_p1_kw": 0.0, "pot_p2_kw": 0.0, "pot_p3_kw": 0.0, "pot_p4_kw": 0.0, "pot_p5_kw": 0.0, "pot_p6_kw": 0.0,

  "energia_facturada_kwh": 0.0,        ← VALOR FACTURADO (NO desagregado)
  "consumo_p1_kwh": 0.0,               ← desagregados (informativo, del bloque "Sus consumos desagregados")
  "consumo_p2_kwh": 0.0,
  "consumo_p3_kwh": 0.0,
  "consumo_p4_kwh": 0.0,
  "consumo_p5_kwh": 0.0,
  "consumo_p6_kwh": 0.0,

  "imp_ele": 5.11269632,               ← porcentaje (formato pre-2026), null si formato €/kWh
  "imp_ele_eur_kwh": null,             ← formato €/kWh (post RDL 7/2026), null si formato %
  "iva": 21,                           ← IVA general (porcentaje)
  "iva_reducido": null,                ← IVA reducido (porcentaje), null si no aplica split
  "alq_eq_dia": 0.0,
  "bono_social": 0.0,

  "compensacion_excedentes_kwh": null, ← negativo si existe
  "compensacion_excedentes_importe_eur": null,

  "descuentos": {
    "Descuento sobre consumo 10%": -10.41,
    "Descuento sobre consumo 5%": -5.20
  },

  "importe_factura": 0.00,

  "otros": {
    "Pack Iberdrola Hogar": 7.16,
    "Descuento Pack Iberdrola Hogar": -3.58,
    "Asistencia PYMES Iberdrola": null
  },

  "validacion_cuadre": {
    "potencia_total_calc": 24.87,
    "energia_facturada_calc": 104.09,
    "descuentos_total_calc": -15.61,
    "compensacion_excedentes_calc": -24.26,
    "bono_social_calc": 0.15,
    "impuesto_electricidad_calc": 4.56,
    "alquiler_contador_calc": 0.64,
    "otros_calc": 3.58,
    "iva_total_calc": 20.58,
    "suma_conceptos": 118.60,
    "importe_factura_pdf": 118.60,
    "diferencia_eur": 0.00,
    "tolerancia_eur": 0.02,
    "cuadra": true
  },

  "error": null
}
```

**Cuando hay IVA split (RDL 8/2023 o RDL 7/2026):**
- Añadir `iva_reducido` (porcentaje), `iva_reducido_base` y `iva_reducido_importe`.
- `iva` mantiene el porcentaje general (21).
- En `validacion_cuadre`, `iva_total_calc` = suma de ambos tramos.

**Cuando hay autoconsumo:**
- `compensacion_excedentes_kwh` y `compensacion_excedentes_importe_eur` son negativos y entran en `validacion_cuadre.compensacion_excedentes_calc`.

**Cuando un servicio no tiene campo dedicado:**
- Va al diccionario `otros`. Ej.: `Pack Iberdrola Hogar`, `Asistencia PYMES Iberdrola`, `Descuento Pack Iberdrola Hogar` (signo negativo).
- En `validacion_cuadre.otros_calc` = suma de `otros`.

**Cuando el cuadre falla:**
- `validacion_cuadre.cuadra: false`
- `validacion_cuadre.diferencia_eur`: importe_factura - suma_conceptos
- `error`: `"Suma de conceptos (XX,XX €) no cuadra con importe factura (YY,YY €). Diferencia: Z,ZZ €. Posible causa: <…>"`

**Cuando el PDF es ilegible o multi-factura:**
- `error`: `"PDF escaneado sin texto extraíble"` o `"PDF contiene múltiples facturas (N detectadas) — generar un _processed.json por factura"`.

---

## Checklist final (antes de declarar "extracción completa")

- [ ] Leí las **4 páginas** (o todas las que el PDF tenga).
- [ ] Extraje los **20 bloques** descritos.
- [ ] Capturé todos los textos legales literales en blockquote (MD) y como strings exactos (JSON).
- [ ] Capturé códigos de barras, códigos internos y certificaciones.
- [ ] Capturé dirección de correos **del remite** y **la de reclamaciones** (suelen ser apartados distintos).
- [ ] Distingui entre **potencia contratada** y **potencia máxima demandada**.
- [ ] Distingui entre **lecturas del contador** (acumuladas) y **consumos del periodo** (diferencia).
- [ ] Capturé el tipo de lecturas (Reales / Estimadas).
- [ ] Capturé todos los **teléfonos** (atención, averías, reparaciones, autoconsumo).
- [ ] Capturé todos los **enlaces** (web comercializadora, distribuidora, CNMC, comparador, app).
- [ ] **R12: distingui valores facturados (líneas `X kWh × Y €/kWh`) de desagregados informativos.**
- [ ] **R13: ejecuté reconciliación contable (suma_conceptos == importe_factura).**
- [ ] Ejecuté las **7 validaciones de coherencia** (incluida la nueva R13).
- [ ] Documenté **advertencias** si algún total no cuadra.
- [ ] Generé `<stem>_ai.md` con la plantilla exacta de 20 secciones (21 si hay advertencias).
- [ ] Generé `<stem>_ai.json` con las 24 claves raíz (anidado, exhaustivo).
- [ ] **Generé `<stem>_processed.json` (TERCER fichero, plano, schema endpoint, con `validacion_cuadre`, `otros` y `error`).**
- [ ] Los **3 JSONs** validan: `python3 -c "import json; json.load(open('...'))"` → sin errores.
- [ ] Los 3 archivos tienen **el mismo stem** que el PDF fuente.
- [ ] `<stem>_ai.md` y `<stem>_ai.json` contienen la **misma información**.
- [ ] `<stem>_processed.json.validacion_cuadre.cuadra == true` (o `error` poblado con descripción).

---

## Uso

### Invocación estándar

```
Lee el archivo <ruta>.pdf siguiendo las instrucciones del documento
prompt_lectura_factura.md y genera los TRES archivos:
  <ruta>_ai.md
  <ruta>_ai.json
  <ruta>_processed.json
```

### Ejemplo concreto

```
Lee facturas/iberdrola1.pdf siguiendo prompt_lectura_factura.md y genera
facturas/iberdrola1_ai.md, facturas/iberdrola1_ai.json y
facturas/iberdrola1_processed.json.
```

### Entrega al usuario

Al finalizar, reportar:
1. Ruta de los 2 archivos generados.
2. Resumen de las 6 validaciones (✅ / ⚠️).
3. Lista de advertencias si las hubiere.
4. Confirmación de que el JSON valida con `json.load`.
