# extractor/parsers/repsol.py
# Parser específico para facturas de Repsol Comercializadora.
# Sobrescribe solo los métodos con comportamiento diferente al genérico.
#
# Diferencias respecto al BaseParser:
#   - imp_ele: línea "BASE € BASE x X%" mezclada con "IVA" al final
#   - alquiler: solo hay total €, sin €/día explícito
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from typing import Optional
from .base_parser import BaseParser
from ..base import norm


class RepsolParser(BaseParser):

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato Repsol: "Equipos de medida  0,77 €" ou "0,83 €"
        Buscar especificamente a linha "Equipos de medida" para evitar
        capturar o total de "Otros conceptos".
        Divide pelo número de dias para obter €/día.
        """
        dias = self._calcular_dias()

        for linha in self.linhas:
            if "equipos de medida" not in linha.lower():
                continue

            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if m:
                try:
                    normed = norm(m.group(1))
                    if normed is None:
                        continue
                    total = float(normed)
                    if 0.1 <= total <= 5.0 and dias > 0:
                        self.raw["alq_eq_dia"] = f"{linha[:55]} [calculado: {total}/{dias}]"
                        return str(round(total / dias, 6))
                except ValueError:
                    pass

        return super().extraer_alquiler()

    def extraer_potencias_contratadas(self) -> dict:
        """
        Repsol: "Potencia contratada  Punta: 5,6kW  Valle: 5,6kW"
        Também: "Punta: 5,75kW / Valle: 5,75kW" na secção "TU CONTRATO"
        """
        result = {}
        m = re.search(r"[Pp]unta[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))

        m = re.search(r"[Vv]alle[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))

        return result or super().extraer_potencias_contratadas()

    def extraer_consumos(self) -> dict:
        """
        Repsol: tabela de consumos com 3 colunas na página 2.
        Formato: "(actual) hasta  58 kWh  39 kWh  87 kWh"
        Os valores são Punta, Llano, Valle respectivamente.
        """
        result = {}

        for linha in self.linhas:
            l = linha.lower()
            if "actual" not in l and "periodo" not in l:
                continue
            if "kwh" not in l:
                continue

            # Capturar 3 valores kWh na mesma linha
            vals = re.findall(r"([0-9]+(?:[,\.][0-9]+)?)\s*kWh", linha, re.IGNORECASE)
            if len(vals) >= 3:
                try:
                    result["consumo_p1_kwh"] = float(norm(vals[0]))
                    result["consumo_p2_kwh"] = float(norm(vals[1]))
                    result["consumo_p3_kwh"] = float(norm(vals[2]))
                    return result
                except (ValueError, TypeError):
                    pass

        return super().extraer_consumos()
