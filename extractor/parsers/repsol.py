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
