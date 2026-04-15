#!/usr/bin/env python3
"""
validate.py — Validador de coherencia para facturas eléctricas extraídas.

Uso:
    python3 validate.py <ruta_al_json>

Salida:
    - Informe con las 6 validaciones de coherencia obligatorias.
    - ✅ si pasa, ⚠️ si hay discrepancia (con valores concretos).
    - Sale siempre con código 0 (las discrepancias son advertencias, no errores fatales).
    - Si el JSON no parsea, sale con código 1.

Validaciones ejecutadas (según prompt_lectura_factura.md):
    1. Suma resumen económico == total factura (tolerancia 0,02 €)
    2. R12: energia_facturada_kwh × precio == importe energía facturada (tolerancia 0,02 €)
    2b. (Informativo) sum(desagregados) - energia_facturada_kwh — esperado en autoconsumo
    3. Base IVA × % IVA ≈ importe IVA (tolerancia 0,01 €)
    4. Peajes detalle = suma (potencia + energía + alquiler contador) (tolerancia 0,01 €)
    5. Distribución porcentual del coste ≈ 100 % (tolerancia 0,5 %)
    6. Mix energético ≈ 100 % para comercializadora y nacional (tolerancia 0,5 %)
    7. R13: reconciliación contable — suma(conceptos) == importe_factura (tolerancia 0,02 €)
"""

import json
import sys
from pathlib import Path


TOL_EUR = 0.02
TOL_KWH = 1.0
TOL_IVA = 0.01
TOL_PCT = 0.5


def _get(d, *keys, default=None):
    """Navegación defensiva por dict anidado."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _fmt(v, suffix=""):
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.2f}{suffix}"
    return f"{v}{suffix}"


def check_1_suma_resumen(data):
    r = data.get("resumen_economico", {})
    if not r:
        return ("resumen económico", "SKIP", "no presente en el JSON")

    energia = r.get("energia", 0) or 0
    descuentos = r.get("descuentos_energia", 0) or 0
    cargos = r.get("cargos_normativos", 0) or 0
    servicios = r.get("servicios_y_otros", 0) or 0
    iva = r.get("iva", 0) or 0
    total = r.get("total", 0) or 0

    suma = round(energia + descuentos + cargos + servicios + iva, 2)
    diff = abs(suma - total)
    desc = (
        f"energia({energia}) + descuentos({descuentos}) + cargos({cargos}) + "
        f"servicios({servicios}) + iva({iva}) = {suma} vs total {total}"
    )

    if diff <= TOL_EUR:
        return ("suma resumen = total", "OK", desc)
    return ("suma resumen = total", "WARN", f"{desc} → diff {diff:.2f} €")


def check_2_energia_facturada(data):
    """R12 — Validar que la línea facturada cuadra: kWh × precio = importe."""
    en = _get(data, "detalle_energia", "energia_consumida", default={})
    if not en:
        return ("R2 energía facturada × precio = importe", "SKIP", "bloque energía facturada no presente")

    kwh = en.get("kwh") or 0
    precio = en.get("precio_eur_kwh") or 0
    importe = en.get("importe") or 0

    importe_calc = round(kwh * precio, 2)
    diff = abs(importe_calc - importe)
    desc = f"{kwh} kWh × {precio} €/kWh = {importe_calc} € vs PDF {importe} €"

    if diff <= TOL_EUR:
        return ("R2 energía facturada × precio = importe", "OK", desc)
    return ("R2 energía facturada × precio = importe", "WARN", f"{desc} → diff {diff:.2f} €")


def check_2b_desagregados_vs_facturado(data):
    """R12 informativo — diferencia entre desagregados y facturado (esperada en autoconsumo)."""
    c = data.get("consumo", {})
    desag = c.get("desagregado_kwh", {})
    facturada = _get(data, "detalle_energia", "energia_consumida", "kwh")

    if not desag or facturada is None:
        return ("R2b desagregados vs facturado (informativo)", "SKIP", "datos no presentes")

    suma_desag = sum(v for v in desag.values() if isinstance(v, (int, float)))
    diff = abs(suma_desag - facturada)
    desc = f"sum desagregados = {suma_desag} kWh vs facturado {facturada} kWh"

    autoconsumo_activo = bool(_get(data, "autoconsumo", "compensacion_excedentes", default=False))

    if diff <= TOL_KWH:
        return ("R2b desagregados vs facturado (informativo)", "OK", desc)
    if autoconsumo_activo:
        return (
            "R2b desagregados vs facturado (informativo)",
            "SKIP",
            f"{desc} → diff {diff:.2f} kWh (esperado por autoconsumo instantáneo)",
        )
    return (
        "R2b desagregados vs facturado (informativo)",
        "WARN",
        f"{desc} → diff {diff:.2f} kWh (sin autoconsumo declarado — investigar)",
    )


def check_3_iva(data):
    iva = _get(data, "servicios_y_otros", "iva", default={})
    if not iva:
        return ("IVA = base × %", "SKIP", "bloque IVA no presente")

    base = iva.get("base", 0) or 0
    pct = iva.get("porcentaje", 0) or 0
    importe = iva.get("importe", 0) or 0

    esperado = round(base * pct / 100, 2)
    diff = abs(esperado - importe)
    desc = f"base({base}) × {pct}% = {esperado} vs importe {importe}"

    if diff <= TOL_IVA:
        return ("IVA coherente", "OK", desc)
    return ("IVA coherente", "WARN", f"{desc} → diff {diff:.2f} €")


def check_4_peajes(data):
    p = data.get("peajes_acceso_sin_impuestos", {})
    if not p:
        return ("peajes = suma componentes", "SKIP", "bloque peajes no presente")

    pot = p.get("potencia", 0) or 0
    ene = p.get("energia", 0) or 0
    alq = p.get("alquiler_contador", 0) or 0
    total = p.get("total", 0) or 0

    suma = round(pot + ene + alq, 2)
    diff = abs(suma - total)
    desc = f"potencia({pot}) + energía({ene}) + alquiler({alq}) = {suma} vs total {total}"

    if diff <= TOL_IVA:
        return ("peajes = suma componentes", "OK", desc)
    return ("peajes = suma componentes", "WARN", f"{desc} → diff {diff:.2f} €")


def check_5_distribucion(data):
    d = data.get("distribucion_coste_porcentaje", {})
    if not d:
        return ("distribución coste ≈ 100 %", "SKIP", "bloque distribución no presente")

    campos = [
        "energia", "peajes_transporte_distribucion", "impuestos",
        "alquiler_contador", "bono_social", "cargos_total",
    ]
    valores = {k: d.get(k, 0) or 0 for k in campos}
    suma = round(sum(valores.values()), 1)
    diff = abs(suma - 100.0)
    desc = " + ".join(f"{k}({v})" for k, v in valores.items()) + f" = {suma}%"

    if diff <= TOL_PCT:
        return ("distribución coste ≈ 100 %", "OK", desc)
    return ("distribución coste ≈ 100 %", "WARN", f"{desc} → diff {diff:.2f} %")


def check_6_mix(data):
    """Dos checks en uno: mix comercializadora + mix nacional."""
    results = []
    mix_block = None
    for k in data.keys():
        if k.startswith("origen_electricidad"):
            mix_block = data[k]
            break

    if not mix_block:
        return [("mix energético ≈ 100 %", "SKIP", "bloque mix no presente")]

    for nombre_clave, etiqueta in [
        (None, "comercializadora"),   # primera clave que no sea 'texto_introductorio' ni 'mix_nacional'
        ("mix_nacional", "nacional"),
    ]:
        if nombre_clave is None:
            # encontrar la primera clave que no sea el texto ni el nacional
            for k in mix_block:
                if k not in ("texto_introductorio", "mix_nacional"):
                    clave = k
                    break
            else:
                clave = None
        else:
            clave = nombre_clave

        if clave is None or clave not in mix_block:
            results.append((f"mix {etiqueta} ≈ 100 %", "SKIP", f"{clave} no presente"))
            continue

        mix = mix_block[clave]
        if not isinstance(mix, dict):
            results.append((f"mix {etiqueta} ≈ 100 %", "SKIP", "estructura inesperada"))
            continue

        suma = round(sum(v for v in mix.values() if isinstance(v, (int, float))), 1)
        diff = abs(suma - 100.0)
        desc = f"suma {etiqueta} = {suma}%"

        if diff <= TOL_PCT:
            results.append((f"mix {etiqueta} ≈ 100 %", "OK", desc))
        else:
            results.append((f"mix {etiqueta} ≈ 100 %", "WARN", f"{desc} → diff {diff:.2f} %"))

    return results


def check_7_reconciliacion_cuadre(data):
    """R13 — Suma de conceptos == importe factura (lee de _processed.json o reconstruye desde AI)."""
    # Si el JSON es _processed.json (tiene validacion_cuadre), usar ese campo directamente
    cuadre = data.get("validacion_cuadre")
    total_pdf = data.get("importe_factura")

    if cuadre and total_pdf is not None:
        suma = cuadre.get("suma_conceptos", 0) or 0
        diff = abs(suma - total_pdf)
        cuadra_flag = cuadre.get("cuadra")
        desc = f"suma_conceptos={suma} vs importe_factura={total_pdf} (cuadra flag={cuadra_flag})"
        if diff <= TOL_EUR:
            return ("R7 reconciliación contable (cuadre)", "OK", desc)
        return ("R7 reconciliación contable (cuadre)", "WARN", f"{desc} → diff {diff:.2f} €")

    # Si es _ai.json, reconstruir desde bloques
    pot_total = _get(data, "detalle_energia", "potencia", "total_potencia") or 0
    en_imp   = _get(data, "detalle_energia", "energia_consumida", "importe") or 0
    descs    = _get(data, "detalle_energia", "descuentos", default=[]) or []
    desc_sum = sum(d.get("importe", 0) or 0 for d in descs if isinstance(d, dict))
    excedentes = _get(data, "detalle_energia", "compensacion_excedentes", "importe") or 0
    bono     = _get(data, "cargos_normativos", "financiacion_bono_social_fijo", "importe") or 0
    imp_ele  = _get(data, "cargos_normativos", "impuesto_electricidad", "importe") or 0
    alq      = _get(data, "servicios_y_otros", "alquiler_equipos_medida", "importe") or 0
    pack     = _get(data, "servicios_y_otros", "pack_iberdrola_hogar", "importe") or 0
    pack_dto = _get(data, "servicios_y_otros", "descuento_pack_iberdrola_hogar", "importe") or 0
    iva_total = _get(data, "servicios_y_otros", "iva_total")
    if iva_total is None:
        iva_total = _get(data, "servicios_y_otros", "iva", "importe") or 0

    suma = round(
        pot_total + en_imp + desc_sum + excedentes + bono + imp_ele + alq + pack + pack_dto + iva_total,
        2,
    )
    total = _get(data, "factura", "total") or 0

    if not total:
        return ("R7 reconciliación contable (cuadre)", "SKIP", "factura.total no presente")

    diff = abs(suma - total)
    desc = (
        f"pot({pot_total}) + ene({en_imp}) + desc({round(desc_sum,2)}) + exced({excedentes}) "
        f"+ bono({bono}) + IE({imp_ele}) + alq({alq}) + pack({pack}+{pack_dto}) + IVA({iva_total}) "
        f"= {suma} vs total {total}"
    )

    if diff <= TOL_EUR:
        return ("R7 reconciliación contable (cuadre)", "OK", desc)
    return ("R7 reconciliación contable (cuadre)", "WARN", f"{desc} → diff {diff:.2f} €")


ICONS = {"OK": "✅", "WARN": "⚠️ ", "SKIP": "⏭️ "}


def main():
    if len(sys.argv) != 2:
        print("Uso: python3 validate.py <ruta_al_json>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Archivo no encontrado: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ JSON no válido: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Validando: {path}")
    print(f"JSON parsea OK — {len(data)} claves raíz\n")

    checks = [
        check_1_suma_resumen(data),
        check_2_energia_facturada(data),
        check_2b_desagregados_vs_facturado(data),
        check_3_iva(data),
        check_4_peajes(data),
        check_5_distribucion(data),
        check_7_reconciliacion_cuadre(data),
    ]
    # check_6_mix devuelve una lista
    checks.extend(check_6_mix(data))

    ok = warn = skip = 0
    print("Validaciones de coherencia:")
    print("-" * 60)
    for nombre, estado, desc in checks:
        icon = ICONS.get(estado, "?")
        print(f"  {icon} [{estado}] {nombre}")
        print(f"       {desc}")
        if estado == "OK":
            ok += 1
        elif estado == "WARN":
            warn += 1
        else:
            skip += 1

    print("-" * 60)
    print(f"Resumen: {ok} ✅  {warn} ⚠️   {skip} ⏭️ ")

    # Advertencias registradas en el JSON
    advertencias = data.get("advertencias", [])
    if advertencias:
        print(f"\nAdvertencias registradas en el JSON ({len(advertencias)}):")
        for a in advertencias:
            if isinstance(a, dict):
                print(f"  - [{a.get('tipo', '?')}] {a.get('descripcion', '')}")
            else:
                print(f"  - {a}")

    # Salida: siempre 0 (discrepancias son advertencias, no errores)
    sys.exit(0)


if __name__ == "__main__":
    main()
