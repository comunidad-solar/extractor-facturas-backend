# extractor/parsers/iberdrola.py
# Modificado: 2026-04-14 | Rodrigo Costa
#   - extraer_descuentos(): captura "Descuento X% s/BASE €" → valor absoluto

import re
from typing import Optional
from ..base import norm
from .base_parser import BaseParser


class IberdrolaParser(BaseParser):

    def extraer_potencias_contratadas(self) -> dict:
        result = {}
        m = re.search(r"[Pp]otencia\s+punta[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))
        m = re.search(r"[Pp]otencia\s+valle[:\s]+([0-9,\.]+)\s*kW", self.text, re.IGNORECASE)
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))
        return result or super().extraer_potencias_contratadas()

    def extraer_consumos(self) -> dict:
        """
        Iberdrola 2.0TD: "Sus consumos desagregados han sido punta: 330 kWh; llano: 308 kWh; valle 458 kWh"
        Iberdrola 3.0TD: tabela "Energía activa P2 ... 1.275 kWh" (última coluna)
        """
        result = {}

        # 2.0TD: linha de consumos desagregados no rodapé
        m = re.search(
            r"punta\s*:\s*([0-9]+)\s*kWh[^;]*;\s*llano\s*:\s*([0-9]+)\s*kWh[^;]*;\s*valle\s*([0-9]+)\s*kWh",
            self.text, re.IGNORECASE
        )
        if m:
            result["consumo_p1_kwh"] = float(m.group(1))
            result["consumo_p2_kwh"] = float(m.group(2))
            result["consumo_p3_kwh"] = float(m.group(3))
            return result

        # 3.0TD: tabela "Energía activa P{n} ... CONSUMO kWh"
        patron = re.compile(
            r'Energ[ií]a\s+activa\s+P([1-6])\s+[\d/]+\s+[\d.,]+\s+[\d/]+\s+[\d.,]+\s+([0-9]+(?:[.,][0-9]+)?)\s*kWh',
            re.IGNORECASE
        )
        for m in patron.finditer(self.text):
            try:
                periodo = int(m.group(1))
                campo   = f"consumo_p{periodo}_kwh"
                if campo not in result:
                    # Remove ponto de milhares antes de converter
                    val_str = m.group(2).replace(".", "").replace(",", ".")
                    result[campo] = float(val_str)
            except (ValueError, TypeError):
                pass

        return result or super().extraer_consumos()

    def extraer_descuentos(self) -> dict:
        """
        Iberdrola: "Descuento pertenencia Comunidad Solar 5%  5 % s/152,57 €  -7,63 €"
        Ignora linha de resumen "DESCUENTOS ENERGÍA" sem detalle de cálculo.
        Deduplica por nome normalizado e valor.
        """
        resultado = {}
        linhas_processadas = set()

        for linha in self.linhas:
            l = linha.lower()
            if "descuento" not in l:
                continue
            if "descuentos energ" in l:
                continue
            if any(x in l for x in ["financiaci", "impuesto", "iva", "bono social"]):
                continue

            linha_norm = re.sub(r"\s+", "", linha.lower())
            if linha_norm in linhas_processadas:
                continue
            linhas_processadas.add(linha_norm)

            valores_negativos = re.findall(
                r"-\s*([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if valores_negativos:
                try:
                    valor = abs(float(norm(valores_negativos[-1])))
                    if 0.01 <= valor <= 99999:
                        nombre = re.split(r"[\d%€\-]", linha)[0].strip()
                        nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,: ")
                        if len(nombre) >= 3:
                            nombre_norm = re.sub(r"\s+", "", nombre.lower())
                            ja_existe = any(
                                re.sub(r"\s+", "", k.lower()) == nombre_norm
                                or abs(v - round(valor, 6)) < 0.01
                                for k, v in resultado.items()
                            )
                            if not ja_existe:
                                resultado[nombre] = round(valor, 6)
                                self.raw[f"descuento_{nombre[:20]}"] = linha[:80]
                                print(f"  ✅  {'descuento':<26} = {valor:<20} ← {nombre}")
                except (ValueError, TypeError):
                    pass

        base = super().extraer_descuentos()
        for k, v in base.items():
            k_norm = re.sub(r"\s+", "", k.lower())
            ja_existe = any(
                re.sub(r"\s+", "", r.lower()) == k_norm
                or abs(rv - v) < 0.01
                for r, rv in resultado.items()
            )
            if not ja_existe:
                resultado[k] = v

        return resultado
