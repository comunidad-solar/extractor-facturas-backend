# extractor/parsers/endesa.py
# Parser específico para facturas de Endesa Energía.
# Sobrescribe los métodos con comportamiento diferente al genérico.
#
# Particularidades de Endesa:
#   - periodo: la sección "FACTURA ENDESA X SERVICIOS" contiene datas mais antigas;
#     o período correto está no cabeçalho da fatura principal.
#   - imp_ele: la factura tiene una sección "DESTINO DEL IMPORTE" con "11,24% Impuestos"
#     que el BaseParser captura incorrectamente. El valor real está en la línea
#     "Impuesto electricidad ( BASE Eur X PORCENTAJE %)" dentro del DETALLE DE FACTURA.
#     Además, el IVA puede estar reducido al 10% (RDL 8/2023) pero el PDF también
#     contiene IVA 21% de la factura Endesa X Servicios (servicio adicional) — hay
#     que capturar el IVA de la factura principal (Endesa Energía), no el de servicios.
#   - imp_ele posibles valores: 5.11269632% (normal), 2.5% (reducido RDL 8/2023)
#   - iva posibles valores: 21% (desde 2025), 10% (reducido 2023-2024), 5% (Canarias)
#   - extraer_precios_energia(): preço único por sub-períodos → pe_p1 média ponderada
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from .base_parser import BaseParser
from ..base import norm


class EndesaParser(BaseParser):

    # ── PERÍODO ───────────────────────────────────────────────────────────────

    def extraer_periodo(self):
        """
        Endesa: período no cabeçalho da fatura principal.
        Formatos conhecidos:
          "Periodo de facturación: del 17/12/2023 a 14/02/2024 (59 días)"
          "Periodo de facturación: 19/01/2025 - 19/02/2025"
        Corta o texto antes de "FACTURA ENDESA X" para evitar capturar
        datas da sub-fatura de serviços.
        """
        corte = re.search(
            r"FACTURA\s+ENDESA\s+X|ENDESA\s+X\s+SERVICIOS",
            self.text, re.IGNORECASE
        )
        texto = self.text[:corte.start()] if corte else self.text

        # Formato: "del DD/MM/YYYY a DD/MM/YYYY"
        m = re.search(
            r"del\s+(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})",
            texto, re.IGNORECASE
        )
        if m:
            self.raw["periodo_inicio"] = m.group(0)[:80]
            self.raw["periodo_fin"]    = m.group(0)[:80]
            return m.group(1), m.group(2)

        # Fallback ao BaseParser (cobre formato DD/MM/YYYY - DD/MM/YYYY)
        linhas_originais = self.linhas
        self.linhas = texto.splitlines()
        try:
            return super().extraer_periodo()
        finally:
            self.linhas = linhas_originais

    # ── PRECIOS DE POTENCIA ───────────────────────────────────────────────────

    def extraer_precios_potencia(self):
        """
        Endesa: sub-períodos com preços diferentes para Punta e Valle.
        Formato: "Pot. Punta 4,600 kW x 0,087879 Eur/kW x 14 días"
        Calcula média ponderada pelos días para pp_p1 (Punta) e pp_p2 (Valle).
        """
        corte = re.search(
            r"FACTURA\s+ENDESA\s+X|ENDESA\s+X\s+SERVICIOS",
            self.text, re.IGNORECASE
        )
        texto = self.text[:corte.start()] if corte else self.text

        patron = re.compile(
            r'Pot\.\s*(Punta|Valle)\s+'
            r'[0-9,\.]+\s*kW\s*[xX×]\s*([0-9]+[,\.][0-9]+)\s*Eur/kW\s*[xX×]\s*([0-9]+)\s*d[ií]as?',
            re.IGNORECASE
        )

        acumulado = {"punta": {"dias": 0.0, "valor": 0.0, "raw": ""},
                     "valle": {"dias": 0.0, "valor": 0.0, "raw": ""}}

        for m in patron.finditer(texto):
            label = m.group(1).lower()
            try:
                normed = norm(m.group(2))
                if normed is None:
                    continue
                precio = float(normed)
                dias   = float(m.group(3))
                acumulado[label]["valor"] += precio * dias
                acumulado[label]["dias"]  += dias
                acumulado[label]["raw"]    = m.group(0)[:80]
            except (ValueError, TypeError):
                pass

        mapa = {"punta": "pp_p1", "valle": "pp_p2"}
        encontrou = False

        for label, campo in mapa.items():
            acc = acumulado[label]
            if acc["dias"] > 0:
                media = round(acc["valor"] / acc["dias"], 6)
                self.fields[campo] = media
                self.raw[campo]    = acc["raw"]
                print(f"  ✅  {campo:<26} = {media:<20} ← Endesa potencia {label} (média ponderada)")
                encontrou = True

        if not encontrou:
            return super().extraer_precios_potencia()

        return self.fields.get("pp_p1"), self.fields.get("pp_p2")

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self):
        """
        Endesa: preço único de energia em sub-períodos.
        Formato: "Facturación del Consumo X kWh x Y Eur/kWh"
        Guarda pe_p1 com a média ponderada dos sub-períodos.
        Corta antes de "FACTURA ENDESA X" para evitar capturar
        preços da sub-fatura de serviços.
        """
        corte = re.search(
            r"FACTURA\s+ENDESA\s+X|ENDESA\s+X\s+SERVICIOS",
            self.text, re.IGNORECASE
        )
        texto = self.text[:corte.start()] if corte else self.text

        patron = re.compile(
            r'Facturaci[oó]n\s+del\s+Consumo\s+'
            r'([0-9]+[,\.][0-9]+)\s*kWh\s*[xX×]\s*([0-9]+[,\.][0-9]+)\s*Eur/kWh',
            re.IGNORECASE
        )

        kwh_total   = 0.0
        valor_total = 0.0
        encontrou   = False

        for m in patron.finditer(texto):
            try:
                kwh   = float(norm(m.group(1)))
                preco = float(norm(m.group(2)))
                kwh_total   += kwh
                valor_total += kwh * preco
                encontrou    = True
                self.raw["pe_p1"] = m.group(0)[:80]
            except ValueError:
                pass

        if encontrou and kwh_total > 0:
            media = round(valor_total / kwh_total, 6)
            self.fields["pe_p1"] = media
            print(f"  ✅  {'pe_p1':<26} = {media:<20} ← precio energía único (media ponderada)")
            return

        # Fallback ao BaseParser
        linhas_originais = self.linhas
        self.linhas = texto.splitlines()
        try:
            super().extraer_precios_energia()
        finally:
            self.linhas = linhas_originais

    # ── IMPORTE TOTAL ─────────────────────────────────────────────────────────

    def extraer_importe_factura(self):
        """
        Endesa: a fatura principal tem "TOTAL 48,68 €" (sem "IMPORTE FACTURA").
        A sub-fatura Endesa X tem "TOTAL IMPORTE FACTURA 5,09 €".
        Cortar antes de "FACTURA ENDESA X" para evitar capturar o total errado.
        Depois procurar "Total X,XX €" ou "TOTAL X,XX €" no texto cortado.
        """
        corte = re.search(
            r"FACTURA\s+ENDESA\s+X|ENDESA\s+X\s+SERVICIOS",
            self.text, re.IGNORECASE
        )
        texto = self.text[:corte.start()] if corte else self.text

        patrones = [
            r'(?:^|\n)\s*TOTAL\s+([0-9]+[,\.][0-9]+)\s*€',
            r'Total\s+([0-9]+[,\.][0-9]+)\s*€\s*\n',
        ]
        for patron in patrones:
            m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
            if m:
                try:
                    val = float(m.group(1).replace(",", "."))
                    if 1.0 <= val <= 99999.0:
                        self.raw["importe_factura"] = m.group(0).strip()[:80]
                        return str(val)
                except ValueError:
                    pass

        # Fallback ao BaseParser com texto cortado
        texto_original   = self.text
        linhas_originais = self.linhas
        self.text   = texto
        self.linhas = texto.splitlines()
        try:
            return super().extraer_importe_factura()
        finally:
            self.text   = texto_original
            self.linhas = linhas_originais

    # ── IMPUESTO ELÉCTRICO ────────────────────────────────────────────────────

    def extraer_imp_ele(self):
        """
        Endesa: "Impuesto electricidad ( 41,64 Eur X 2,5 %)"
        Solo se acepta la línea que contiene "impuesto electricidad" explícito.
        Se ignoran las líneas del bloque "DESTINO DEL IMPORTE" que comienzan con ">"
        (p.ej. "> 11,24% Impuestos") ya que representan porcentajes del total y no
        el impuesto eléctrico real.
        """
        for linha in self.linhas:
            l = linha.lower()

            # Ignorar líneas del bloque "DESTINO DEL IMPORTE" (comienzan con ">")
            if linha.strip().startswith(">"):
                continue

            # Solo líneas con "impuesto electricidad" explícito
            if "impuesto electricidad" not in l and "impuesto eléctrico" not in l:
                continue
            if "impuesto sobre el valor" in l:
                continue

            # "BASE Eur X PORCENTAJE %" — Endesa
            m = re.search(
                r"[0-9,\.]+\s*(?:Eur|€)\s*[xX×]\s*([0-9]+[,\.][0-9]+)\s*%",
                linha, re.IGNORECASE
            )
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

            # "X,XX % s/BASE" — formato alternativo
            m = re.search(r"([0-9]+[,\.][0-9]+)\s*%\s*s/[0-9]", linha, re.IGNORECASE)
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

            # "BASE € X,XX %" — formato genérico en línea de impuesto
            m = re.search(r"[0-9,\.]+\s*€\s+([0-9]+[,\.][0-9]+)\s*%", linha, re.IGNORECASE)
            if m:
                val = norm(m.group(1))
                try:
                    num = float(val)
                    if 0.5 <= num <= 15:
                        self.raw["imp_ele"] = linha[:80]
                        return val
                except ValueError:
                    pass

        return None

    def extraer_iva(self):
        """
        Endesa: el PDF puede contener dos facturas — Endesa Energía (principal) y
        Endesa X Servicios (adicional). El IVA de la factura principal puede ser
        10% (reducido) o 21% (normal). El IVA de Endesa X Servicios es siempre 21%.
        Se captura el IVA que está asociado a la factura principal:
        buscar "IVA normal X%" o "IVA X% s/BASE" antes de la sección Endesa X.
        """
        en_endesa_x = False  # Flag para ignorar la sección Endesa X Servicios

        for linha in self.linhas:
            l = linha.lower()

            # Detectar inicio de la sección Endesa X Servicios
            if "factura endesa x" in l or "endesa x servicios" in l:
                en_endesa_x = True
                continue
            if en_endesa_x:
                continue  # Ignorar todo lo que viene después

            if "iva" not in l:
                continue

            # "IVA normal X% s/BASE" — Endesa Energía con IVA reducido
            m = re.search(
                r"IVA\s+normal\s+([0-9]+)[,\.]?[0-9]*\s*%",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["iva"] = linha[:80]
                return m.group(1)

            # "IVA X% s/BASE" o "IVA (X%)" — formato estándar
            for pat in [
                r"IVA[^0-9]{0,20}([1-9][0-9])[,\.]?[0-9]*\s*%",
                r"([1-9][0-9])[,\.]?[0-9]*\s*%[^0-9]{0,10}IVA",
                r"IVA[^\n]{0,30}?\s([1-9][0-9])[,\.][0-9]+\s*%",
            ]:
                m = re.search(pat, linha, re.IGNORECASE)
                if m:
                    self.raw["iva"] = linha[:80]
                    return m.group(1)

        return None