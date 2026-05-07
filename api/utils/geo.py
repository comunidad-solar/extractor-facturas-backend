# api/utils/geo.py
# Geocodificação via Nominatim para moradas de facturas eléctricas espanholas.

import re

import httpx

_VIA_ABREV = {
    "CL": "CALLE", "C/": "CALLE", "AV": "AVENIDA", "AVD": "AVENIDA",
    "AVDA": "AVENIDA", "PL": "PLAZA", "PZ": "PLAZA", "PS": "PASEO",
    "PG": "POLIGONO", "CR": "CARRETERA", "UR": "URBANIZACION",
    "BL": "BLOQUE", "BQ": "BLOQUE",
}


def simplify_address(addr: str) -> str:
    """Simplifica morada para Nominatim: expande abreviaturas, remove andar/porta, normaliza separadores."""
    a = addr.strip()
    upper = a.upper()
    for abr, full in _VIA_ABREV.items():
        if upper.startswith(abr + " "):
            a = full + a[len(abr):]
            break
    a = a.replace(" - ", ", ")
    parts = [p.strip() for p in a.split(",") if p.strip()]
    if len(parts) >= 3:
        first = parts[0]
        location = " ".join(parts[-2:]) if len(parts) >= 4 else parts[-1]
        a = f"{first} {location}"
    else:
        a = " ".join(parts)
    return re.sub(r"\s+", " ", a).strip().upper()


async def geocode_address(addr: str) -> tuple[float | None, float | None]:
    """Geocodifica morada via Nominatim. Devolve (lat, lon) ou (None, None) se falhar."""
    q = simplify_address(addr)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            geo = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "es"},
                headers={"User-Agent": "ComunidadSolar/1.0"},
            )
            hits = geo.json()
            if hits:
                return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception as e:
        print(f"[geo] geocodificação fallida para '{q}': {e}")
    return None, None
