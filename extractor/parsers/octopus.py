# extractor/parsers/octopus.py
# Parser específico para facturas de Octopus Energy España.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias respecto al BaseParser:
#   - pp_p1/pp2: formato "X kW * N días PRECIO €/kW/día" (cubierto en base)
#   - imp_ele: formato "BASE € X,XX %" (cubierto en base)
#   - extraer_precios_energia(): líneas "Punta/Llano/Valle X kWh Y €/kWh Z €"
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from typing import Optional
from .base_parser import BaseParser
from ..base import norm


class OctopusParser(BaseParser):

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato Octopus: "Alquiler de Equipos  29 días  0,027 €/día  0,77 €"
        Captura o valor €/día explícito directamente.
        """
        for linha in self.linhas:
            l = linha.lower()
            if "alquiler" not in l and "equipo" not in l:
                continue

            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))

        return super().extraer_alquiler()

    # ── BONO SOCIAL ───────────────────────────────────────────────────────────

    def extraer_bono_social(self) -> Optional[str]:
        """
        Formato Octopus: "Bono Social  29 días  0,013 €/día  0,37 €"
        Captura o valor €/día explícito directamente.
        """
        for linha in self.linhas:
            l = linha.lower()
            if "bono social" not in l and "bono_social" not in l:
                continue

            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["bono_social"] = linha[:80]
                return norm(m.group(1))

        return super().extraer_bono_social()

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Formato Octopus:
          "Punta    79,70 kWh    0,114 €/kWh    9,15 €"
          "Llano    83,16 kWh    0,116 €/kWh    9,55 €"
          "Valle    122,91 kWh   0,115 €/kWh    14,11 €"
        Solo captura la línea principal — ignora sub-líneas de peajes/cargos/margen.
        """
        mapeo = {
            "punta": "pe_p1",
            "llano": "pe_p2",
            "valle": "pe_p3",
        }
        patron = re.compile(
            r'^(punta|llano|valle)\s+'
            r'[\d.,]+\s*kWh\s+'
            r'(\d+[.,]\d+)\s*€/kWh',
            re.IGNORECASE | re.MULTILINE
        )
        for match in patron.finditer(self.text):
            label  = match.group(1).lower()
            precio = float(match.group(2).replace(",", "."))
            campo  = mapeo.get(label)
            if campo and campo not in self.fields:
                self.fields[campo] = precio
                self.raw[campo]    = match.group(0)[:80]
                print(f"  ✅  {campo:<26} = {precio:<20} ← {label} {precio} €/kWh")

    def extraer_potencias_contratadas(self) -> dict:
        """
        Octopus: tabela "Potencia Contratada (kW)  4,60  4,60  0  0  0  0"
        Os valores aparecem na linha "Potencia Contratada (kW)" separados por espaços.
        """
        result = {}
        for linha in self.linhas:
            if "potencia contratada" not in linha.lower():
                continue
            vals = []
            for n in re.findall(r"([0-9]+[,\.][0-9]+|[0-9]+)", linha):
                try:
                    vals.append(float(n.replace(",", ".")))
                except ValueError:
                    pass
            for i, val in enumerate(vals[:6], start=1):
                result[f"pot_p{i}_kw"] = val
            if result:
                break
        return result or super().extraer_potencias_contratadas()
