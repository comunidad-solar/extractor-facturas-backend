# extractor/__init__.py
# Punto de entrada del paquete. Orquesta el flujo completo:
#   1. Extraer texto del PDF (pdfplumber → fallback OCR si PDF es imagen)
#   2. Detectar comercializadora
#   3. Parsear campos PDF con el parser específico
#   4. Completar campos con la API Ingebau
#   5. Imprimir resumen y devolver ExtractionResult
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - get_parser() recibe pdf_path para parsers que necesitan acceso directo al PDF
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - Fallback OCR con pdf2image + pytesseract cuando pdfplumber no extrae texto
#   - Corrección post-OCR del CUPS: O → 0 en posiciones numéricas (ES + 16-20 dígitos)

import re
import pdfplumber
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from .base      import ExtractionResult
from .detector  import detectar
from .api       import llamar_api
from .parsers   import get_parser


# ── OCR helpers ───────────────────────────────────────────────────────────────

def _ocr_extract(pdf_path: str) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
        import sys
        import os

        print("  ⚙️   PDF sin texto — aplicando OCR (Tesseract)...")

        # Localizar Poppler
        if sys.platform == "win32":
            # Caminho hardcoded Windows — fallback se não estiver no PATH
            poppler_path = r"C:\Users\ianro\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"
        else:
            poppler_path = None  # Linux/AWS encontra automaticamente

        pages = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
        text  = ""
        for page in pages:
            text += pytesseract.image_to_string(page, lang="spa") + "\n"
        return text

    except ImportError:
        print("  ⚠️   OCR no disponible — instala: pdf2image pytesseract tesseract-ocr")
        return ""
    except Exception as e:
        print(f"  ⚠️   OCR falló: {e}")
        return ""
   


def _corregir_cups(text: str) -> str:
    """
    Corrige errores OCR en el CUPS: la O mayúscula puede confundirse con 0.
    El CUPS español tiene formato: ES + 16 a 20 caracteres alfanuméricos.
    En las posiciones numéricas esperadas, reemplaza O → 0.

    Ejemplo: ES0031408215316008QCOF → ES0031408215316008QC0F
    """
    def fix_cups(m: re.Match) -> str:
        cups = m.group(0)
        # Los primeros 18 caracteres tras "ES" son numéricos — O → 0
        prefijo = cups[:20]   # "ES" + 18 dígitos
        sufijo  = cups[20:]   # código de control alfanumérico — no tocar
        prefijo_fixed = prefijo.replace("O", "0").replace("o", "0")
        return prefijo_fixed + sufijo

    return re.sub(r"ES[A-Z0-9]{16,22}", fix_cups, text, flags=re.IGNORECASE)


# ── Punto de entrada ──────────────────────────────────────────────────────────

def extract_from_pdf(pdf_path: str) -> ExtractionResult:
    """
    Procesa una factura PDF y devuelve un ExtractionResult con todos los campos.
    Esta es la única función pública del paquete — main.py solo importa esto.
    """
    print(f"\n{'='*70}")
    print(f"  PROCESANDO: {pdf_path}")
    print(f"{'='*70}")

    # ── 1. Extraer texto del PDF ──────────────────────────────────────────────
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            full_text += text + "\n"

    # Fallback OCR si pdfplumber no extrajo nada
    ocr_usado = False
    if not full_text.strip():
        full_text = _ocr_extract(pdf_path)
        ocr_usado = True

    # Corrección post-OCR del CUPS (O → 0 en posiciones numéricas)
    if ocr_usado and full_text:
        full_text = _corregir_cups(full_text)

    # ── 2. Detectar comercializadora ──────────────────────────────────────────
    comercializadora_id = detectar(full_text)

    # ── 3. Parsear campos del PDF ─────────────────────────────────────────────
    parser = get_parser(comercializadora_id, full_text, pdf_path)
    fields, raw = parser.parse()

    # ── 4. Extraer potencias contratadas del PDF ──────────────────────────────
    pot_pdf = parser.extraer_potencias_contratadas()
    for campo, valor in pot_pdf.items():
        if valor is not None:
            fields[campo] = valor
            print(f"  ✅  {campo:<26} = {valor:<20} ← [PDF]")

    # ── 5. Completar con API Ingebau ──────────────────────────────────────────
    cups           = fields.get("cups")
    periodo_inicio = fields.get("periodo_inicio")
    periodo_fin    = fields.get("periodo_fin")

    api_ok, api_error = llamar_api(cups, fields, raw, periodo_inicio, periodo_fin)

    # PDF prevalece sobre Ingebau para potencias contratadas
    for campo, valor in pot_pdf.items():
        if valor is not None:
            fields[campo] = valor

    # ── 6. Resumen ────────────────────────────────────────────────────────────
    tarifa = fields.get("tarifa_acceso", "")

    def campo_vazio(k, v):
        if v in [None, ""]:
            return True
        if v in ["0", "0.0"] and tarifa == "2.0TD" and any(f"_p{p}" in k for p in [3,4,5,6]):
            return False
        return False

    total  = len(fields)
    vacios = sum(1 for k, v in fields.items() if campo_vazio(k, v))
    ok     = total - vacios

    print(f"\n  [RESUMEN] {ok}/{total} campos extraídos  |  {vacios} vacíos")
    if vacios > 0:
        print("  Campos vacíos:")
        for k, v in fields.items():
            if campo_vazio(k, v):
                print(f"    ⚠️   {k}")
    print(f"{'='*70}\n")

    return ExtractionResult(
        fields      = fields,
        raw_matches = raw,
        api_ok      = api_ok,
        api_error   = api_error,
    )