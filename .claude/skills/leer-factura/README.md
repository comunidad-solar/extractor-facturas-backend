# Skill `leer-factura`

Skill de Claude Code para extraer **exhaustivamente** datos de facturas eléctricas españolas en PDF y generar dos archivos sincronizados: uno legible (`.md`) y uno estructurado (`.json`).

## Estructura

```
.claude/skills/leer-factura/
├── SKILL.md                    Manifiesto (activación + workflow)
├── prompt_lectura_factura.md   Instrucciones detalladas (20 bloques, esquema JSON, plantilla MD)
├── README.md                   Este fichero
└── scripts/
    └── validate.py             Validador de coherencia del JSON generado
```

## Instalación

Esta skill ya está instalada en el proyecto (project-level). Para activarla tras cambios:

```bash
/reload-plugins
```

O reiniciar la sesión de Claude Code.

## Uso

### Desde Claude Code (automático)

Simplemente pide al agente que procese una factura:

> "Lee `facturas/iberdrola1.pdf` y extrae todos los datos."

La skill se activa automáticamente al detectar palabras clave (`factura`, `electricidad`, `luz`, `Iberdrola`, `Endesa`, `Naturgy`, etc.).

### Salida esperada

Por cada PDF procesado, se generan **dos ficheros** con el mismo stem, en la misma carpeta del PDF:

- `<stem>.md` — Markdown con 20 (o 21 con advertencias) secciones estructuradas:
  1. Emisor · 2. Cliente · 3. Factura · 4. Contrato · 5. Forma pago
  6. Resumen económico · 7. Detalle energía · 8. Cargos normativos
  9. Servicios y otros · 10. Precios unitarios · 11. Consumo
  12. Autoconsumo · 13. Peajes · 14. Distribución coste
  15. Mix electricidad · 16. Impacto ambiental · 17. Observaciones legales
  18. Reclamaciones · 19. Contactos · 20. Metadatos · (21. Advertencias)

- `<stem>.json` — JSON estructurado con 24 claves raíz (tipos nativos, snake_case, ISO 8601 para fechas).

### Validación manual

Para validar un JSON generado:

```bash
python3 .claude/skills/leer-factura/scripts/validate.py <ruta_al_json>
```

El validador ejecuta 7 chequeos de coherencia:

| # | Check | Tolerancia |
|---|---|---|
| 1 | Suma resumen económico = total factura | ±0,02 € |
| 2 | Consumo desagregado (P1+P2+P3) = total kWh | ±1 kWh |
| 3 | Base IVA × % = importe IVA | ±0,01 € |
| 4 | Peajes = potencia + energía + alquiler | ±0,01 € |
| 5 | Distribución coste = 100 % | ±0,5 % |
| 6 | Mix comercializadora = 100 % | ±0,5 % |
| 7 | Mix nacional = 100 % | ±0,5 % |

Salida: `✅ OK`, `⚠️ WARN` (discrepancia), `⏭️ SKIP` (datos no presentes). Siempre sale con código 0 — los warnings son advertencias, no errores fatales.

## Reglas críticas

1. **Preservar textos legales literalmente** — RDL 8/2023, nota de excedentes, texto de reclamaciones, etiquetado ambiental.
2. **Nunca inventar valores** — Campos ausentes: `null` (JSON) / "no indicado" (MD).
3. **MD y JSON deben contener la misma información** — No hay datos en uno que no estén en el otro.
4. **Ejecutar el validador siempre** antes de declarar la extracción completa.
5. **No ajustar valores** para forzar que una validación pase — reportar la discrepancia tal cual en `advertencias`.

## Comercializadoras soportadas

Probado con facturas de **Iberdrola**. Diseñado para adaptarse a:

- Endesa
- Naturgy
- Repsol
- TotalEnergies
- Holaluz
- Cualquier comercializadora del mercado eléctrico español que siga el formato estándar (CUPS, ATR, peajes de acceso, bono social, compensación de excedentes CNMC).

## Tarifas soportadas

- **2.0TD** (doméstico): franjas P1 (punta), P2 (llano), P3 (valle)
- **3.0TD / 6.1TD** (industrial): franjas P1–P6

## Limitaciones

- **OCR**: si el PDF es una imagen escaneada sin capa de texto, la extracción será parcial. El validador detectará totales que no cuadran.
- **Facturas rectificativas / abonos**: la regla R9 del prompt indica cómo detectarlos, pero los cálculos de coherencia se han pensado para facturas normales. Revisar el signo de los importes en rectificativas.
- **Mercado regulado (PVPC)**: el prompt incluye el campo `mercado`, pero el desglose de energía en PVPC es diferente (precios horarios del mercado diario). Puede requerir campos adicionales.

## Dependencias

- **Python 3.8+** para el validador.
- Sin librerías externas. Usa sólo la stdlib (`json`, `sys`, `pathlib`).

## Desarrollo / extensión

### Añadir una nueva comercializadora

1. Procesar un PDF de muestra con la skill.
2. Si hay campos no cubiertos en el esquema JSON, editarlos en `prompt_lectura_factura.md` (bloques 1–20 + esquema JSON).
3. Ajustar las validaciones en `scripts/validate.py` si aplican cálculos distintos.

### Añadir una validación

Editar `scripts/validate.py` y añadir una función `check_N_<nombre>(data)` que devuelva `(titulo, estado, descripcion)` con estado ∈ {`OK`, `WARN`, `SKIP`}. Registrarla en la lista `checks` de `main()`.

## Licencia

Proyecto interno del repositorio `extractor-facturas-backend`.
