# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)

1. **[2026-05-06] No automated tests — validate manually**
   Do instead: test via Swagger UI (http://localhost:8000/docs) or GUI (`python main.py`) after every change.

2. **[2026-05-06] Alembic migrations run automatically on startup**
   Do instead: add new DB columns via Alembic migration in `alembic/versions/`; never alter `db/models.py` without a migration.

3. **[2026-05-06] Log every code change in `log.md`**
   Do instead: append `[NNN] YYYY-MM-DD | prompt summary | files changed | before/after` after every commit.

## Shell & Command Reliability

1. **[2026-05-06] Dev deploy on EC2 — full command required**
   Do instead: `cd /home/ubuntu/extractor-facturas-backend && git pull origin DEVELOP && docker stop extractor-facturas-dev && docker rm extractor-facturas-dev && docker build -t extractor-facturas-dev . && mkdir -p /home/ubuntu/data-dev && docker run -d --name extractor-facturas-dev --env-file .env.development -p 8011:8000 --restart always -v /home/ubuntu/data-dev:/app/data -e DATABASE_URL=sqlite:////app/data/sessions.db extractor-facturas-dev`

2. **[2026-05-06] Start API locally**
   Do instead: `uvicorn api.main:app --reload --port 8000`

## Domain Behavior Guardrails

1. **[2026-05-06] Cox parser uses PyMuPDF (fitz), not pdfplumber**
   Do instead: when editing Cox parser, use `fitz` API — it has 2-column layout that pdfplumber can't handle.

2. **[2026-05-06] Naturgy parser pre-processes text — removes thousand separators**
   Do instead: strip `.` as thousand separator before regex matching in Naturgy parser.

3. **[2026-05-06] pe_p* fields: only fill periods present in the bill**
   Do instead: leave `pe_p2`..`pe_p6` as `null` when not in the bill; don't default to zero.

4. **[2026-05-06] Adding new comercializadora — 3 steps**
   Do instead: (1) create `extractor/parsers/<name>.py`, (2) register in `extractor/parsers/__init__.py`, (3) add regex pattern in `extractor/detector.py`.

5. **[2026-05-06] `/enviar` — no file field, no CALC_BACKEND_URL forward**
   Do instead: only accept `data` (Form) field with JSON `{cliente, factura, Fsmstate, FsmPrevious, ce}`; proxies to Zoho Flow only.

6. **[2026-05-06] Zoho webhook URL contains API key in source**
   Do instead: never commit real keys; use env var or confirm with user before touching `enviar.py`.

7. **[2026-05-06] SQLite data lost in Docker without volume**
   Do instead: always mount `/home/ubuntu/data-dev:/app/data` in docker run; verify volume exists before deploy.

8. **[2026-05-07] `/enviar` sends Claude factura (from session), not flat frontend factura**
   Do instead: frontend must pass `session_id` in payload; backend reads Claude session factura before posting to Zoho. Do not change this flow — Zoho expects `otros.importes_totalizados`.

9. **[2026-05-07] Nominatim fails on raw Spanish addresses — simplify first**
   Do instead: always run `simplify_address()` before Nominatim call. Raw "CL DAMASO ALONSO 14, 3º, B ILLESCAS - TOLEDO" → no hits. Simplified "CALLE DAMASO ALONSO ILLESCAS TOLEDO" → resolves. Logic in `api/utils/geo.py`.

10. **[2026-05-07] Shared geocoding utility — never inline**
    Do instead: use `from api.utils.geo import simplify_address, geocode_address`. Never duplicate in route files — caused circular import when `facturas_ai.py` tried to import from `facturas.py`.

## Pipeline Claude — Casos Especiais

1. **[2026-05-11] PVPC: peajes ≠ preço total de energia**
   Do instead: detectar `costes_mercado != null` → aplicar CASO PVPC no energia mapper (distribuir bulk por kWh). Guardrail: pe_p* < 0.05 → erro. Afecta Energía XXI, Comercializadora de Referencia.

2. **[2026-05-11] Autoconsumo Batería Virtual: só subtotal neto em creditos**
   Do instead: `compensacion_excedentes_importe` = subtotal neto (-33.98). NUNCA incluir `valoracion_excedentes` + `subtotal` separados (double-count). NUNCA incluir `importe_bateria_virtual` em creditos.

3. **[2026-05-11] Mínimo Comunitario (Art. 99.2 Ley 38/1992) é IEE, não serviço**
   Do instead: vai em `costes_adicionales["minimo_comunitario_importe"]` e promovido a `importes_totalizados` como campo nomeado. Excluído de `costes_totales`. Sinal: linha "X kWh × 0,001000 €/kWh".

4. **[2026-05-11] `imp.get(key, {})` não usa default quando chave existe com None**
   Do instead: usar `imp.get(key) or {}` (e `or []` para listas). Causa: mapper retornou `"iee": null` → `.get("iee", {})` devolve `None` → AttributeError.

## User Directives

1. **[2026-05-06] Tesseract + Poppler paths are Windows-hardcoded**
   Do instead: before adding cross-platform paths, confirm with user first.

2. **[2026-05-06] `resultados/` and `*.md` ignored by .gitignore**
   Do instead: if CLAUDE.md/BACKEND.md/FRONTEND.md need committing, add exceptions to `.gitignore` explicitly.

3. **[2026-05-07] `/facturas/extraer` is the main endpoint — `/facturas/extraer-ai` is legacy**
   Do instead: direct new features and fixes to `api/routes/facturas.py`. `facturas_ai.py` kept for backward compat only.
