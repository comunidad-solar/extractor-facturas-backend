# extractor/parsers/energyavm.py
# Parser para facturas de Enérgya VM Gestión de Energía, S.L.U.
# Sobrescribe extraer_comercializadora() y extraer_precios_potencia().
#
# extraer_comercializadora(): el rodapié del PDF aparece invertido en pdfplumber
#   — se invierte cada línea con [::-1] para recuperar el texto legible.
# extraer_precios_potencia(): filtra explícitamente líneas con "€/kW/día"
#   para evitar capturar precios de energía (€/kWh) con el mismo label P1/P2.
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - extraer_precios_potencia(): re.match → re.search para capturar "Término de potencia P1:"
#   - extraer_comercializadora(): añadido debug temporal para diagnóstico

import re
from typing import Optional

from ..base import norm
from .base_parser import BaseParser


class EnergyaVMParser(BaseParser):

    # ── COMERCIALIZADORA ─────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        El nombre legal nunca aparece en una línea legible completa en pdfplumber
        (el rodapié lateral se extrae fragmentado letra a letra).
        Se devuelve el nombre legal hardcodeado ya que el detector garantiza
        que este parser solo se activa para facturas de esta comercializadora.
        """
        self.raw["comercializadora"] = "hardcoded — rodapié fragmentado en pdfplumber"
        return "Enérgya VM Gestión de Energía, S.L.U."

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        La factura EnergyaVM tiene energía y potencia con el mismo label P1/P2.
        Se filtra explícitamente buscando solo líneas con "€/kW/día"
        para evitar capturar precios de energía (€/kWh).
        Formato: "Término de potencia P1: 1,700 kW x 28 días x 0,094197 €/kW/día."
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        for linha in self.linhas:
            # Solo procesar líneas con precio de potencia — ignorar €/kWh
            if not re.search(r"€/kW/d[ií]a", linha, re.IGNORECASE):
                continue

            # Capturar precio: "X kW x N días x PRECIO €/kW/día"
            m = re.search(
                r"[0-9,\.]+\s*kW\s*[x×]\s*[0-9]+\s*d[ií]as?\s*[x×]\s*([0-9]+[,\.][0-9]+)\s*€/kW/d[ií]a",
                linha, re.IGNORECASE
            )
            if not m:
                continue

            precio = norm(m.group(1))

            # re.search en lugar de re.match — captura "Término de potencia P1:" también
            if re.search(r"\bP1\s*:", linha, re.IGNORECASE) and pp1 is None:
                pp1 = precio
                src1 = linha[:80]
            elif re.search(r"\bP2\s*:", linha, re.IGNORECASE) and pp2 is None:
                pp2 = precio
                src2 = linha[:80]

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    def extraer_potencias_contratadas(self) -> dict:
        """
        EnergyaVM: "Término de potencia P1: 1,700 kW x 28 días x 0,094197 €/kW/día."
        O valor kW está na linha de potência (antes de "x N días").
        """
        result = {}
        for linha in self.linhas:
            if not re.search(r"€/kW/d[ií]a", linha, re.IGNORECASE):
                continue
            for p in range(1, 3):
                m = re.search(
                    rf"P{p}\s*:\s*([0-9,\.]+)\s*kW",
                    linha, re.IGNORECASE
                )
                if m and f"pot_p{p}_kw" not in result:
                    result[f"pot_p{p}_kw"] = float(norm(m.group(1)))
        return result or super().extraer_potencias_contratadas()

    def extraer_consumos(self) -> dict:
        """
        EnergyaVM: "Término de energía P1: 12,82 kWh, Precio: 0,104900 €/kWh."
        Os kWh estão na linha de energía por período.
        """
        result = {}

        patron = re.compile(
            r'(?:T[eé]rmino\s+de\s+energ[ií]a\s+)?'
            r'P([1-6])\s*:\s*([0-9]+[,\.][0-9]+)\s*kWh',
            re.IGNORECASE
        )
        for m in patron.finditer(self.text):
            try:
                periodo = int(m.group(1))
                campo   = f"consumo_p{periodo}_kwh"
                if campo not in result:
                    result[campo] = float(norm(m.group(2)))
            except (ValueError, TypeError):
                pass

        return result or super().extraer_consumos()

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Formato EnergyaVM:
          "Término de energía P1: 12,82 kWh, Precio: 0,104900 €/kWh."
          "P2: 17,65 kWh, Precio: 0,104900 €/kWh."   ← línea de continuación
          "P3: 31,87 kWh, Precio: 0,104900 €/kWh."
        Las líneas P2/P3 no tienen "Término de energía" — son continuaciones.
        """
        patron = re.compile(
            r'(?:T[eé]rmino\s+de\s+energ[ií]a\s+)?'
            r'P([1-6])\s*:\s*[\d.,]+\s*kWh\s*,\s*'
            r'Precio\s*:\s*(\d+[.,]\d+)\s*€/kWh',
            re.IGNORECASE
        )
        for match in patron.finditer(self.text):
            periodo = int(match.group(1))
            precio  = float(norm(match.group(2)))
            campo   = f"pe_p{periodo}"
            if campo not in self.fields:
                self.fields[campo] = precio
                self.raw[campo]    = match.group(0)[:80]
                print(f"  ✅  {campo:<26} = {precio:<20} ← P{periodo} {precio} €/kWh")