#!/usr/bin/env python3
"""
run_extractor.py — Ejecuta extract_from_pdf() sobre un PDF y guarda el
resultado en JSON en la carpeta indicada (default: ./resultados/).

Uso:
    python3 run_extractor.py <ruta_pdf> [<carpeta_salida>]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extractor import extract_from_pdf


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 run_extractor.py <ruta_pdf> [<carpeta_salida>]", file=sys.stderr)
        sys.exit(2)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"❌ PDF no encontrado: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("resultados")
    out_dir.mkdir(parents=True, exist_ok=True)

    result = extract_from_pdf(str(pdf_path))
    fields = result.fields
    payload = {**fields, "api_ok": result.api_ok, "api_error": result.api_error}

    cups   = fields.get("cups") or "sin_cups"
    inicio = (fields.get("periodo_inicio") or "sin_fecha").replace("/", "-")
    fin    = (fields.get("periodo_fin")    or "sin_fecha").replace("/", "-")
    nombre = f"{cups}_{inicio}_{fin}.json"
    ruta   = out_dir / nombre

    with ruta.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅ JSON guardado en: {ruta}")


if __name__ == "__main__":
    main()
