# extractor/parsers/base_parser.py
# Clase base para todos los parsers de comercializadoras.
# Implementa la extracción genérica de los 8 campos del PDF.
# Cada subclase puede sobrescribir únicamente los métodos que necesite adaptar.
#
# Campos extraídos aquí (PDF):
#   cups, periodo_inicio, periodo_fin, comercializadora,
#   pp_p1, pp_p2, imp_ele, iva, alq_eq_dia
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from datetime import datetime
from typing import Optional

from ..base import norm, numeros, to_date, fmt_date, normalizar_fecha, log


class BaseParser:
    """
    Parser genérico. Contiene la lógica de extracción que funciona para la
    mayoría de comercializadoras españolas. Las subclases sobrescriben solo
    los métodos con comportamiento diferente.
    """

    def __init__(self, text: str):
        self.text   = text
        self.linhas = text.splitlines()
        self.fields: dict = {}
        self.raw:    dict = {}

    def save(self, key: str, value, match: str = "") -> None:
        """Guarda un campo en los diccionarios internos."""
        self.fields[key] = value
        self.raw[key]    = match

    def parse(self) -> tuple[dict, dict]:
        """
        Ejecuta todos los extractores en orden y devuelve (fields, raw).
        Las subclases pueden sobrescribir métodos individuales sin tocar este flujo.
        """
        print("\n  [1/6] EXTRACCIÓN DESDE PDF")
        print("  " + "-"*50)

        cups = self.extraer_cups()
        self.save("cups", cups, self.raw.get("cups", ""))
        log("cups", cups, self.raw.get("cups", ""))

        inicio, fin = self.extraer_periodo()
        self.save("periodo_inicio", inicio, self.raw.get("periodo_inicio", ""))
        self.save("periodo_fin",    fin,    self.raw.get("periodo_fin", ""))
        log("periodo_inicio", inicio, self.raw.get("periodo_inicio") or "no encontrado en PDF")
        log("periodo_fin",    fin,    self.raw.get("periodo_fin")    or "no encontrado en PDF")

        com = self.extraer_comercializadora()
        self.save("comercializadora", com, self.raw.get("comercializadora", ""))
        log("comercializadora", com, self.raw.get("comercializadora") or "no encontrado en PDF")

        pp1, pp2 = self.extraer_precios_potencia()
        self.save("pp_p1", pp1, self.raw.get("pp_p1", ""))
        self.save("pp_p2", pp2, self.raw.get("pp_p2", ""))
        log("pp_p1", pp1, self.raw.get("pp_p1") or "no encontrado en PDF")
        log("pp_p2", pp2, self.raw.get("pp_p2") or "no encontrado en PDF")

        imp = self.extraer_imp_ele()
        self.save("imp_ele", imp, self.raw.get("imp_ele", ""))
        log("imp_ele", imp, self.raw.get("imp_ele") or "no encontrado en PDF")

        iva = self.extraer_iva()
        self.save("iva", iva, self.raw.get("iva", ""))
        log("iva", iva, self.raw.get("iva") or "no encontrado en PDF")

        alq = self.extraer_alquiler()
        self.save("alq_eq_dia", alq, self.raw.get("alq_eq_dia", ""))
        log("alq_eq_dia", alq, self.raw.get("alq_eq_dia") or "no encontrado en PDF")

        bono = self.extraer_bono_social()
        self.fields["bono_social"] = bono
        if bono:
            print(f"  ✅  {'bono_social':<26} = {bono:<20} ← bono social €/día")

        self.extraer_precios_energia()

        importe = self.extraer_importe_factura()
        self.fields["importe_factura"] = float(importe) if importe else None
        log("importe_factura", self.fields["importe_factura"], self.raw.get("importe_factura", ""))

        return self.fields, self.raw

    # ── CUPS ─────────────────────────────────────────────────────────────────

    def extraer_cups(self) -> Optional[str]:
        """
        Extrae el CUPS del PDF.
        Soporta formato junto (ES0021...) y separado por espacios (ES 0021 0000...).
        """
        # 1ª prioridad — CUPS por contexto explícito ("cups" en la línea)
        for linha in self.linhas:
            if "cups" not in linha.lower():
                continue
            m = re.search(r"(ES[0-9]{16,20}[A-Z0-9]{2,4})", linha)
            if m:
                self.raw["cups"] = m.group(0)[:80]
                return m.group(1)

        # 2ª prioridad — regex genérico excluyendo IBANs
        for m in re.finditer(r"(ES[0-9]{16,20}[A-Z0-9]{0,4})", self.text):
            contexto = self.text[max(0, m.start() - 10):m.start()].upper()
            if "IBAN" in contexto:
                continue
            self.raw["cups"] = m.group(0)[:80]
            return m.group(1)

        # 3ª prioridad — formato con espacios
        m = re.search(
            r"(ES(?:\s+[A-Z0-9]{4}){4,6}(?:\s+[A-Z0-9]{1,4})?)",
            self.text, re.IGNORECASE
        )
        if m:
            cups_raw = re.sub(r"\s+", "", m.group(1)).upper()
            self.raw["cups"] = m.group(0)[:80]
            if re.match(r"^ES[A-Z0-9]{16,24}$", cups_raw):
                return cups_raw

        return None

    # ── PERÍODO ──────────────────────────────────────────────────────────────

    def extraer_periodo(self) -> tuple[Optional[str], Optional[str]]:
        """
        Extrae las fechas de inicio y fin del período de facturación.
        Soporta múltiples formatos de fecha y etiquetas.
        """
        date_pat = r"(\d{2}[/.\-]\d{2}[/.\-]\d{2,4})"
        patrones = [
            rf"[Pp]eriodo\s*(?:de\s*(?:consumo|facturaci[oó]n))?\s*:?\s*{date_pat}\s*(?:al?|a|-)\s*{date_pat}",
            rf"(?:del?|desde)[^\d]{{0,10}}{date_pat}\s*(?:al?|a|-)\s*{date_pat}",
            rf"{date_pat}\s*(?:–|-)\s*{date_pat}",
            rf"[Pp]eriodo\s+de\s+facturaci[oó]n\s+{date_pat}\s*-\s*{date_pat}",
        ]
        for pat in patrones:
            m = re.search(pat, self.text, re.IGNORECASE)
            if m:
                inicio = normalizar_fecha(m.group(1))
                fin    = normalizar_fecha(m.group(2))
                match  = m.group(0)[:80]
                self.raw["periodo_inicio"] = match
                self.raw["periodo_fin"]    = match
                return inicio, fin

        return None, None

    # ── COMERCIALIZADORA ─────────────────────────────────────────────────────

    def extraer_comercializadora(self) -> Optional[str]:
        """
        Extrae el nombre legal de la comercializadora.
        Las subclases pueden sobrescribir este método para añadir patrones propios.
        """
        patrones = [
            r"(Repsol\s+Comercializadora[^,\n]{0,50}(?:S\.L\.U|S\.A\.U|S\.L|S\.A)\.?)",
            r"(Naturgy\s+Iberia\s*,?\s*S\.A\.?)",
            r"(Iberdrola\s+Clientes\s*,?\s*S\.A\.U\.?)",
            r"(Endesa\s+Energ[ií]a\s*,?\s*S\.A\.?[^\n,]{0,20})",
            r"(Octopus\s+Energy\s+España\s*,?\s*S\.L\.U\.?)",
        ]
        for pat in patrones:
            m = re.search(pat, self.text, re.IGNORECASE)
            if m:
                val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.")
                self.raw["comercializadora"] = m.group(0)[:80]
                return val
        return None

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self) -> tuple[Optional[str], Optional[str]]:
        """
        Extrae pp_p1 y pp_p2 (€/kW/día).
        Soporta los formatos más habituales de las comercializadoras españolas.
        """
        pp1, src1 = self._precio_pot(["punta", "p1", "pot. punta", "p1. potencia", "periodo 1"])
        pp2, src2 = self._precio_pot(["valle", "p2", "pot. valle", "p2. potencia", "periodo 2"])
        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
        return pp1, pp2

    def _precio_pot(self, labels: list[str]) -> tuple[Optional[str], str]:
        """Busca el precio de potencia para un conjunto de etiquetas de período."""
        for i, linha in enumerate(self.linhas):
            if not any(l.lower() in linha.lower() for l in labels):
                continue
            trecho = " ".join(self.linhas[i:i+3])

            # "X kW * N días Y €/kW/día" — Octopus
            m = re.search(
                r"[0-9,\.]+\s*kW\s*[*x×]\s*[0-9]+\s*d[ií]as?\s*[*x×]?\s*([0-9]+[,\.][0-9]{2,})\s*€/kW",
                trecho, re.IGNORECASE
            )
            if m:
                return norm(m.group(1)), linha[:80]

            # "X kW x N días x Y €" — Repsol / Iberdrola
            m = re.search(
                r"[0-9,\.]+\s*kW\s*[x×]\s*[0-9]+\s*d[ií]as?\s*[x×]\s*([0-9]+[,\.][0-9]{4,})\s*€",
                trecho, re.IGNORECASE
            )
            if m:
                return norm(m.group(1)), linha[:80]

            # "X kW x PRECIO Eur/kW" — Endesa
            m = re.search(
                r"[0-9,\.]+\s*kW\s*[x×]\s*([0-9]+[,\.][0-9]{4,})\s*Eur/kW",
                trecho, re.IGNORECASE
            )
            if m:
                return norm(m.group(1)), linha[:80]

            # "P1 (X kW) N días PRECIO" — Naturgy
            m = re.search(
                r"\([0-9,\.]+\s*kW\)\s*[0-9]+\s*d[ií]as?\s+([0-9]+[,\.][0-9]{4,})",
                trecho, re.IGNORECASE
            )
            if m:
                return norm(m.group(1)), linha[:80]

            # Secuencia pot/días/precio — Comunidad Solar / genérico
            nums = numeros(trecho)
            for j in range(len(nums) - 2):
                try:
                    pot   = float(nums[j])
                    dias  = float(nums[j+1])
                    preco = float(nums[j+2])
                    if 0.1 <= pot <= 500 and 10 <= dias <= 365 and 0.001 <= preco <= 2.0:
                        return nums[j+2], linha[:80]
                except ValueError:
                    continue

        return None, ""

    # ── IMPUESTO ELÉCTRICO ────────────────────────────────────────────────────

    def extraer_imp_ele(self) -> Optional[str]:
        """
        Extrae el porcentaje de impuesto eléctrico (0.5% – 15%).
        Soporta múltiples formatos: X% s/BASE, BASE x X%, BASE € X%, factor decimal.
        """
        for linha in self.linhas:
            l = linha.lower()
            if not any(x in l for x in ["impuesto", "electricidad", "eléctrico", "electrico"]):
                continue
            if "impuesto sobre el valor" in l:
                continue

            # "X% s/BASE" — Iberdrola
            m = re.search(r"([0-9]+[,\.][0-9]+)\s*%\s*s/[0-9]", linha, re.IGNORECASE)
            if m:
                self.raw["imp_ele"] = linha[:80]
                return norm(m.group(1))

            # "€ BASE x X%" o "BASE x X%" — Repsol / Comunidad Solar
            m = re.search(
                r"[0-9,\.]+\s*(?:€\s*)?[0-9,\.]*\s*[x×]\s*([0-9]+[,\.][0-9]+)\s*%",
                linha, re.IGNORECASE
            )
            if m:
                try:
                    num = float(norm(m.group(1)))
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return norm(m.group(1))
                except ValueError:
                    pass

            # "BASE € X,XX %" — Octopus
            m = re.search(r"[0-9,\.]+\s*€\s+([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
            if m:
                try:
                    num = float(norm(m.group(1)))
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return norm(m.group(1))
                except ValueError:
                    pass

            # Genérico: porcentaje razonable
            m = re.search(r"([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
            if m:
                try:
                    num = float(norm(m.group(1)))
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return norm(m.group(1))
                except ValueError:
                    pass

            # Factor decimal 0.025 = 2.5% — Naturgy
            m = re.search(r"\b(0\.[0-9]+)\b", linha)
            if m:
                try:
                    factor = float(m.group(1))
                    if 0.005 <= factor <= 0.1:
                        self.raw["imp_ele"] = linha[:80]
                        return str(round(factor * 100, 6))
                except ValueError:
                    pass

        return None

    # ── IVA ──────────────────────────────────────────────────────────────────

    def extraer_iva(self) -> Optional[str]:
        """
        Extrae el porcentaje de IVA. En España: 10% o 21%.
        Se guarda el valor más alto encontrado para evitar capturar el 10% del bono.
        """
        val_iva = None
        match_iva = ""
        for linha in self.linhas:
            if "iva" not in linha.lower():
                continue
            for pat in [
                r"IVA[^0-9]{0,20}([1-9][0-9])[,\.]?[0-9]*\s*%",
                r"([1-9][0-9])[,\.]?[0-9]*\s*%[^0-9]{0,10}IVA",
                r"IVA[^\n]{0,30}?\s([1-9][0-9])[,\.][0-9]+\s*%",
            ]:
                m = re.search(pat, linha, re.IGNORECASE)
                if m:
                    candidate = m.group(1)
                    try:
                        if val_iva is None or int(candidate) > int(val_iva):
                            val_iva   = candidate
                            match_iva = linha[:80]
                    except ValueError:
                        pass

        self.raw["iva"] = match_iva
        return val_iva

    # ── ALQUILER DE EQUIPOS ───────────────────────────────────────────────────

    def extraer_alquiler(self) -> Optional[str]:
        """
        Extrae el precio de alquiler de equipos de medida en €/día.
        Si solo hay total, lo divide entre los días del período.
        """
        dias_facturados = self._calcular_dias()

        keywords = ["alquiler", "equipos de medida", "equipos medida",
                    "equipo de medida", "equipo medida"]

        for linha in self.linhas:
            l = linha.lower()
            if not any(x in l for x in keywords):
                continue
            # Excluir líneas que empiezan por "distribuidora" o "conceptos de distribuidora"
            if l.startswith("distribuidora") or l.startswith("conceptos de distribuidora"):
                continue

            # Patrón explícito: "N días X €/día"
            m = re.search(
                r"[0-9]+\s*d[ií]as?\s*[x×]?\s*([0-9]+[,\.][0-9]+)\s*€?/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(1))

            # Secuencia días + precio pequeño
            nums = numeros(linha)
            for j in range(len(nums) - 1):
                try:
                    dias  = float(nums[j])
                    preco = float(nums[j+1])
                    if 10 <= dias <= 365 and 0.001 <= preco <= 0.5:
                        self.raw["alq_eq_dia"] = linha[:80]
                        return nums[j+1]
                except ValueError:
                    continue

            # Fallback: calcular €/día a partir del total
            if dias_facturados > 0:
                m = re.search(r"([0-9]+[,\.][0-9]+)\s*€", linha, re.IGNORECASE)
                if m:
                    try:
                        total = float(norm(m.group(1)))
                        if 0.1 <= total <= 5.0:
                            self.raw["alq_eq_dia"] = f"{linha[:55]} [calculado: {total}/{dias_facturados}]"
                            return str(round(total / dias_facturados, 6))
                    except ValueError:
                        pass

        return None

    # ── BONO SOCIAL ───────────────────────────────────────────────────────────

    def extraer_bono_social(self) -> Optional[str]:
        """
        Formato Repsol:
          "Financiación Bono Social  0,37 €  29 días x 0,012742 €/día"
        Captura o valor por día directamente da linha.
        Fallback: divide o total pelos dias facturados.
        """
        for linha in self.linhas:
            l = linha.lower()
            if "bono social" not in l and "bono_social" not in l:
                continue

            # Padrão 1 — valor €/día explícito
            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["bono_social"] = linha[:80]
                return norm(m.group(1))

            # Padrão 2 — total € sem €/día → dividir pelos dias
            m = re.search(
                r"([0-9]+[,\.][0-9]+)\s*€",
                linha, re.IGNORECASE
            )
            if m:
                try:
                    dias = self._calcular_dias()
                    normed = norm(m.group(1))
                    if normed is None:
                        continue
                    total = float(normed)
                    if 0.01 <= total <= 10.0 and dias > 0:
                        self.raw["bono_social"] = f"{linha[:55]} [calculado: {total}/{dias}]"
                        return str(round(total / dias, 6))
                except ValueError:
                    pass

        return None

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Extrae pe_p1..pe_p6 (€/kWh) de la sección de energía.
        Prueba 4 patrones en orden de prioridad; usa el primero que encuentre resultados.
        """
        precios: dict[int, float] = {}

        # Patrón 1 — Precio único: "Precio Energía 0,114009 €/kWh"
        m = re.search(
            r'[Pp]recio\s+[Ee]nerg[ií]a[\s:]+(\d+[.,]\d+)\s*€?/kWh',
            self.text
        )
        if m:
            val = float(m.group(1).replace(",", "."))
            if val >= 0.01:
                precios[1] = val
                self.fields["pe_p1"] = val
                self.raw["pe_p1"] = m.group(0)[:80]

        # Patrón 2 — Por período: "P1  0,128456 €/kWh"
        if not precios:
            for m2 in re.finditer(r'[Pp](\d)\s+(\d+[.,]\d+)\s*€?/kWh', self.text):
                periodo = int(m2.group(1))
                val = float(m2.group(2).replace(",", "."))
                if 1 <= periodo <= 6 and val >= 0.01:
                    precios[periodo] = val
                    self.fields[f"pe_p{periodo}"] = val
                    self.raw[f"pe_p{periodo}"] = m2.group(0)[:80]

        # Patrón 3 — Tabla "Energía P1  58 kWh  0,128456 €/kWh  7,45 €"
        if not precios:
            for m3 in re.finditer(
                r'[Ee]nerg[ií]a\s+P(\d).*?(\d+[.,]\d{4,6})\s*€?/kWh',
                self.text
            ):
                periodo = int(m3.group(1))
                val = float(m3.group(2).replace(",", "."))
                if 1 <= periodo <= 6 and val >= 0.01:
                    precios[periodo] = val
                    self.fields[f"pe_p{periodo}"] = val
                    self.raw[f"pe_p{periodo}"] = m3.group(0)[:80]

        # Patrón 4 — Fallback: todos los €/kWh en el texto, asignar secuencialmente
        if not precios:
            encontrados = []
            for m4 in re.finditer(r'(\d+[.,]\d{4,6})\s*€/kWh', self.text):
                val = float(m4.group(1).replace(",", "."))
                if val >= 0.01:
                    encontrados.append((val, m4.group(0)[:80]))
            for i, (val, src) in enumerate(encontrados[:6], start=1):
                precios[i] = val
                self.fields[f"pe_p{i}"] = val
                self.raw[f"pe_p{i}"] = src

        # Log de resultados
        for i in range(1, 7):
            key = f"pe_p{i}"
            val = self.fields.get(key)
            if val is not None:
                print(f"  ✅  {key:<26} = {val:<20} ← precio energía P{i}")

    # ── IMPORTE TOTAL DE LA FACTURA ───────────────────────────────────────────

    def extraer_importe_factura(self) -> Optional[str]:
        """
        Captura el importe total de la factura.
        Soporta separadores de miles con punto: "2.738,15 €"
        Patrones por orden de prioridad:
          1. "TOTAL IMPORTE FACTURA ... X.XXX,XX €"
          2. "TOTAL ... X,XX €"
          3. "Total a pagar ... X,XX €"
          4. "IMPORTE FACTURA: X,XX €"
        Acepta valores entre 1 € y 99999 €.
        """
        def parse_importe(texto: str) -> Optional[float]:
            # Eliminar puntos separadores de miles: "2.738,15" → "2738,15"
            limpio = re.sub(r'\.(?=\d{3}[,\d])', '', texto)
            try:
                val = float(norm(limpio))
                if 1.0 <= val <= 99999.0:
                    return val
            except (ValueError, TypeError):
                pass
            return None

        patrones = [
            r'TOTAL\s+IMPORTE\s+FACTURA[^\d]*([0-9]+(?:\.[0-9]{3})*[,\.][0-9]+)\s*€',
            r'TOTAL[^\d\n]{0,30}([0-9]+(?:\.[0-9]{3})*[,\.][0-9]+)\s*€',
            r'Total\s+a\s+pagar[^\d\n]{0,20}([0-9]+(?:\.[0-9]{3})*[,\.][0-9]+)\s*[€e]',
            r'IMPORTE\s+FACTURA\s*:[^\d\n]{0,10}([0-9]+(?:\.[0-9]{3})*[,\.][0-9]+)\s*€',
        ]
        for patron in patrones:
            m = re.search(patron, self.text, re.IGNORECASE)
            if m:
                val = parse_importe(m.group(1))
                if val is not None:
                    self.raw["importe_factura"] = m.group(0)[:80]
                    return str(val)
        return None

    # ── POTENCIAS CONTRATADAS ─────────────────────────────────────────────────

    def extraer_potencias_contratadas(self) -> dict:
        """
        Padrão genérico — tenta vários formatos comuns.
        Devolve dict com os campos encontrados: {"pot_p1_kw": X, ...}
        """
        result = {}

        # Padrão 1: "Potencia contratada en punta: X kW"
        m = re.search(
            r"potencia\s+contratada\s+en\s+punta[:\s]+([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result["pot_p1_kw"] = float(norm(m.group(1)))

        m = re.search(
            r"potencia\s+contratada\s+en\s+valle[:\s]+([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result["pot_p2_kw"] = float(norm(m.group(1)))

        # Padrão 2: "Potencia contratada P1 X kW" (Naturgy 3.0TD)
        for p in range(1, 7):
            m = re.search(
                rf"[Pp]otencia\s+contratada\s+P{p}\s+([0-9,\.]+)\s*kW",
                self.text, re.IGNORECASE
            )
            if m:
                result[f"pot_p{p}_kw"] = float(norm(m.group(1)))

        # Padrão 3: "Potencias contratadas: punta X kW"
        m = re.search(
            r"[Pp]otencias?\s+contratadas?[:\s]+punta\s+([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result.setdefault("pot_p1_kw", float(norm(m.group(1))))

        m = re.search(
            r"[Pp]otencias?\s+contratadas?[:\s]+.*?valle\s+([0-9,\.]+)\s*kW",
            self.text, re.IGNORECASE
        )
        if m:
            result.setdefault("pot_p2_kw", float(norm(m.group(1))))

        return result

    def _calcular_dias(self) -> int:
        """Calcula los días del período a partir de periodo_inicio y periodo_fin ya guardados."""
        inicio = self.fields.get("periodo_inicio")
        fin    = self.fields.get("periodo_fin")
        if not inicio or not fin:
            return 0
        dt_ini = to_date(inicio)
        dt_fin = to_date(fin)
        if dt_ini and dt_fin:
            return (dt_fin - dt_ini).days
        return 0
