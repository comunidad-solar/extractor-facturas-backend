# extractor/parsers/plenitude.py
# Parser para facturas de Eni Plenitude Iberia, SL.
# PDF basado en imagen — el texto proviene de OCR (Tesseract).
# Sobrescribe 3 métodos porque el formato difiere del BaseParser:
#
#   extraer_comercializadora(): captura "Eni Plenitude Iberia, SL" del encabezado
#   extraer_precios_potencia(): OCR lee "día" sin acento — regex del BaseParser falla
#   extraer_alquiler():         OCR lee "dia" sin acento — captura valor directo €/día
#
# Modificado: 2026-02-27 | Rodrigo Costa

import re
from typing import Optional

from ..base import norm
from .base_parser import BaseParser


class PlenitudeParser(BaseParser):

    # ── COMERCIALIZADORA ──────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        Nombre legal: "Eni Plenitude Iberia, SL"
        Aparece en el encabezado de la página 1.
        """
        m = re.search(
            r"(Eni\s+Plenitude\s+Iberia\s*,?\s*S\.?L\.?)",
            self.text, re.IGNORECASE
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
            self.raw["comercializadora"] = m.group(0)[:80]
            return val
        return super().extraer_comercializadora()

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        Formato: "3,4500 kW * 0,073782 €/kW día * 30 dias"
        OCR lee "día" y "dias" sin acento — el BaseParser usa d[ií]as? y falla.
        Se amplía el regex para aceptar con y sin acento.
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        for i, linha in enumerate(self.linhas):
            l = linha.lower()
            if not any(x in l for x in ["periodo p1", "periodo p2", "p1 (", "p2 ("]):
                continue

            trecho = " ".join(self.linhas[i:i+3])

            # "X kW * PRECIO €/kW día * N dias" — Plenitude
            m = re.search(
                r"[0-9,\.]+\s*kW\s*\*\s*([0-9]+[,\.][0-9]+)\s*€/kW\s+d[ií]a",
                trecho, re.IGNORECASE
            )
            if m:
                precio = norm(m.group(1))
                if re.search(r"\bP1\b", linha, re.IGNORECASE) and pp1 is None:
                    pp1  = precio
                    src1 = linha[:80]
                elif re.search(r"\bP2\b", linha, re.IGNORECASE) and pp2 is None:
                    pp2  = precio
                    src2 = linha[:80]

        # Fallback al BaseParser si no encontró nada
        if pp1 is None and pp2 is None:
            return super().extraer_precios_potencia()

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    # ── ALQUILER ──────────────────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Formato: "30 dias * 0,026667 €/día"
        OCR puede leer "dia" sin acento — se amplía el regex.
        """
        for linha in self.linhas:
            l = linha.lower()
            if not any(x in l for x in ["alquiler", "equipo", "medida", "contador"]):
                continue

            # Patrón explícito: "N dias * PRECIO €/día" — con o sin acento
            m = re.search(
                r"\(?\s*[0-9]+\s*d[ií]as?\s*\*\s*([0-9]+[,\.][0-9]+)\s*€/d[ií]a\s*\)?",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))

        return super().extraer_alquiler()

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Formato Plenitude (OCR):
          "Consumo Fácil (...): 102,0000 kWh * 0,108981 €/kWh"
        OCR pode ler "€/kWh" como "€E/xWh", "€/KWh", "e/kwh", etc.
        Estratégia: capturar o número após "*" na linha "Consumo Fácil",
        que é sempre o preço unitário (o número antes da unidade corrompida).
        """
        for linha in self.linhas:
            if not re.search(r'consumo\s+f[aá]cil', linha, re.IGNORECASE):
                continue

            # Capturar último número após "*" — é sempre o preço unitário
            # "102,0000 kWh * 0,108981 €E/xWh"  →  grupo = "0,108981"
            m = re.search(
                r'\*\s*([0-9]+[,\.][0-9]+)\s*[€eE€]',
                linha, re.IGNORECASE
            )
            if m:
                precio = float(norm(m.group(1)))
                self.fields["pe_p1"] = precio
                self.raw["pe_p1"]    = linha[:80]
                print(f"  ✅  {'pe_p1':<26} = {precio:<20} ← Consumo Fácil (precio único)")
                return

        super().extraer_precios_energia()

    def extraer_potencias_contratadas(self) -> dict:
        """
        Plenitude: "Potencia contratada P1: 3,450 kW P2: 3,450 kW"
        OCR pode corromper "P1:" como "?::" — extrair os dois valores
        numéricos kW da linha directamente, atribuindo em ordem P1, P2.
        """
        result = {}
        for linha in self.linhas:
            if "potencia contratada" not in linha.lower():
                continue
            if "kwh" in linha.lower():
                continue
            # Ignorar linhas sem valores numéricos de potência
            if "facturación" in linha.lower() or "desglose" in linha.lower():
                continue
            # Ignorar linha de resumo "Por potencia contratada: X€"
            if re.search(r"[0-9]+[,\.][0-9]+\s*€", linha):
                continue

            # Extrair todos os valores kW (não kWh) da linha
            vals = re.findall(r"([0-9]+[,\.][0-9]+)\s*kW(?!h)", linha, re.IGNORECASE)
            for i, val in enumerate(vals[:2], start=1):
                try:
                    result[f"pot_p{i}_kw"] = float(norm(val))
                except (ValueError, TypeError):
                    pass
            if result:
                break

        return result or super().extraer_potencias_contratadas()

    def extraer_consumos(self) -> dict:
        """
        Plenitude OCR: "Desglose del consumo facturado por periodo: P1:25,00 kWh; P2:29,00 kWh; P3: 48,00 kWh;"
        """
        result = {}

        patron = re.compile(
            r'P([1-6])\s*:\s*([0-9]+[,\.][0-9]*)\s*k[wW]+[hH]+',
            re.IGNORECASE
        )

        for linha in self.linhas:
            if "desglose" not in linha.lower() and "consumo" not in linha.lower():
                continue
            if "periodo" not in linha.lower() and "period" not in linha.lower():
                continue

            for m in patron.finditer(linha):
                try:
                    periodo = int(m.group(1))
                    campo   = f"consumo_p{periodo}_kwh"
                    if campo not in result:
                        result[campo] = float(norm(m.group(2)))
                except (ValueError, TypeError):
                    pass

            if result:
                break

        return result or super().extraer_consumos()

    def extraer_descuentos(self) -> dict:
        """
        Plenitude: "Descuento asociado al ahorro de cargos establecido en el RDL 06/2022 de 29 de marzo: -4,20€"
        Aparece en el pie de página de la segunda hoja como texto informativo.
        """
        resultado = {}

        for linha in self.linhas:
            l = linha.lower()
            if "descuento" not in l and "rdl" not in l:
                continue
            if "financiaci" in l or "impuesto" in l or "bono social" in l:
                continue

            valores_negativos = re.findall(
                r"-\s*([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if valores_negativos:
                try:
                    valor = abs(float(norm(valores_negativos[-1])))
                    if 0.01 <= valor <= 99999:
                        nombre = re.split(r"[\d€\-\*]", linha)[0].strip()
                        nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,: ")
                        if len(nombre) >= 3:
                            resultado[nombre] = round(valor, 6)
                            self.raw[f"descuento_{nombre[:20]}"] = linha[:80]
                            print(f"  ✅  {'descuento':<26} = {valor:<20} ← {nombre}")
                except (ValueError, TypeError):
                    pass

        base = super().extraer_descuentos()
        for k, v in base.items():
            if k not in resultado:
                resultado[k] = v

        return resultado