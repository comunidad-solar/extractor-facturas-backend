# extractor/parsers/iberdrola.py
# Modificado: 2026-04-15 | Rodrigo Costa
#   - Bug #1: regex de consumos desagregados anclado a "Sus consumos desagregados han sido"
#     para evitar capturar el primer match (lecturas acumuladas del contador).
#   - Bug #2: override extraer_imp_ele() para evitar capturar "10,1%" del gráfico de
#     distribución del coste; sólo acepta líneas que empiecen con "Impuesto sobre electricidad".
#   - Bug #4: descuentos diferenciados por porcentaje en el nombre (no se sobrescriben).
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

        FIX Bug #1 (2026-04-15): el regex anterior capturaba el primer bloque "punta: X kWh; llano: ...",
        que en facturas con autoconsumo podía coincidir con las LECTURAS ACUMULADAS del contador
        (ej. "punta: 23.501 kWh; llano: 22.865 kWh; valle 45.734 kWh") en vez de los CONSUMOS del
        periodo (ej. "punta: 107,00 kWh; llano: 142,00 kWh; valle 510,00 kWh").
        Solución: anclar al texto literal "Sus consumos desagregados han sido" + soportar
        formato decimal "X,XX kWh" además del entero.
        """
        result = {}

        # 2.0TD: anclado a "Sus consumos desagregados han sido"
        m = re.search(
            r"[Ss]us\s+consumos\s+desagregados\s+han\s+sido\s+"
            r"punta\s*:\s*([0-9.,]+)\s*kWh[^;]*;\s*"
            r"llano\s*:\s*([0-9.,]+)\s*kWh[^;]*;\s*"
            r"valle\s*:?\s*([0-9.,]+)\s*kWh",
            self.text, re.IGNORECASE,
        )
        if m:
            def _parse_kwh(s: str) -> float:
                # "107,00" → 107.0; "1.489" → 1489.0; "247" → 247.0
                s = s.strip()
                if "," in s:
                    return float(s.replace(".", "").replace(",", "."))
                if s.count(".") == 1:
                    int_p, dec_p = s.split(".")
                    if len(dec_p) == 3:
                        return float(s.replace(".", ""))
                return float(s)
            try:
                result["consumo_p1_kwh"] = _parse_kwh(m.group(1))
                result["consumo_p2_kwh"] = _parse_kwh(m.group(2))
                result["consumo_p3_kwh"] = _parse_kwh(m.group(3))
                return result
            except (ValueError, TypeError):
                pass

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

    def extraer_imp_ele(self) -> Optional[str]:
        """
        Iberdrola — Override del genérico (FIX Bug #2, 2026-04-15).

        El método base captura cualquier "X,XX %" entre 0.5 y 15 en cualquier línea con
        "impuesto" o "electricidad". Esto incluía falsamente el "10,1 %" del gráfico
        "Distribución del coste → Impuestos 10,1 %" cuando aparece cerca de palabras
        como "impuesto" en el pie de página.

        Aquí restringimos a líneas que empiecen literalmente con "Impuesto sobre electricidad"
        y aceptamos dos formatos:
          - Pre-RDL 7/2026: "Impuesto sobre electricidad   X,XX % s/BASE €"
          - Post-RDL 7/2026: "Impuesto sobre electricidad   N kWh × X,XXX €/kWh"
            En este caso devolvemos None (no es un porcentaje); el campo
            imp_ele_eur_kwh se rellenaría aparte (pendiente de añadir como Field).
        """
        for linha in self.linhas:
            l_strip = linha.strip().lower()
            if not l_strip.startswith("impuesto sobre electricidad"):
                continue

            # Formato porcentaje: "X,XX % s/BASE €" (puede tener (*) o cualquier
            # carácter no numérico entre "electricidad" y el porcentaje)
            m = re.search(
                r"impuesto\s+sobre\s+electricidad[^0-9]*?([0-9]+[,\.][0-9]+)\s*%\s*s\s*/",
                linha, re.IGNORECASE,
            )
            if m:
                self.raw["imp_ele"] = linha[:80]
                return norm(m.group(1))

            # Formato €/kWh (post RDL 7/2026): "N kWh × X €/kWh"
            m = re.search(
                r"impuesto\s+sobre\s+electricidad[^0-9]*?[0-9.,]+\s*kWh\s*[x×]\s*[0-9.,]+\s*€\s*/\s*kWh",
                linha, re.IGNORECASE,
            )
            if m:
                self.raw["imp_ele"] = linha[:80] + "  [formato €/kWh — ver imp_ele_eur_kwh]"
                return None  # imp_ele (%) no aplica en este formato

        return None

    def extraer_servicios_otros(self) -> dict:
        """
        Extrae servicios de valor añadido positivos que no son descuentos
        y no tienen un campo dedicado. Devolvemos un dict para `otros`.

        Patrones Iberdrola:
          "Pack Iberdrola Hogar  1 mes × 8,95 €/mes           8,95 €"
          "Pack Iberdrola        1,01 meses × 8,19 €/mes      8,27 €"
          "Asistencia PYMES Iberdrola  0,88 meses × 8,27 €/mes 7,28 €"

        No incluye `Descuento Pack Iberdrola Hogar` (negativo) — ese ya se captura
        por el método extraer_descuentos() estándar.
        """
        resultado = {}
        patrones = [
            # "Pack Iberdrola [Hogar]  N[,M] (mes|meses) [×|x] P,PP €/mes  IMPORTE €"
            r"(Pack\s+Iberdrola(?:\s+Hogar)?)\s+[0-9.,]+\s+(?:mes|meses)\s*[x×]\s*[0-9.,]+\s*€/mes\s+([0-9]+[,\.][0-9]+)\s*€",
            # "Asistencia PYMES Iberdrola ..."
            r"(Asistencia\s+PYMES\s+Iberdrola)\s+[0-9.,]+\s+(?:mes|meses)\s*[x×]\s*[0-9.,]+\s*€/mes\s+([0-9]+[,\.][0-9]+)\s*€",
        ]
        for pat in patrones:
            for m in re.finditer(pat, self.text, re.IGNORECASE):
                nombre = m.group(1).strip()
                try:
                    val = float(norm(m.group(2)))
                except (ValueError, TypeError):
                    continue
                # Evitar duplicar si ya existe (regex puede solaparse)
                if nombre in resultado:
                    continue
                # Comprobación: ignorar si aparece "Descuento Pack..." justo antes
                # (evitar capturar el "Pack" del descuento negativo).
                ctx_start = max(0, m.start() - 20)
                ctx = self.text[ctx_start:m.start()].lower()
                if "descuento" in ctx:
                    continue
                resultado[nombre] = val
                print(f"  ✅  {'servicio_otros':<26} = {val:<20} ← {nombre}")
        return resultado

    def extraer_iva_split(self) -> dict:
        """
        FIX Bug #3 (2026-04-15).

        Cuando la factura tiene IVA split (10 % Reducido + 21 % General) por
        RDL 8/2023 o RDL 7/2026, extraer los dos tramos como bloques separados:
          - iva_reducido (porcentaje), iva_reducido_base, iva_reducido_importe
          - iva (porcentaje general), iva_general_base, iva_general_importe

        Formatos del PDF Iberdrola:
          "IVA Reducido (*) 10 % s/201,26 €    20,13 €"
          "IVA              21 % s/8,95 €      1,88 €"

        Retorna dict vacío si no hay split (sólo 1 IVA), y el método base
        `extraer_iva()` devuelve el único tipo presente.
        """
        result = {}

        # IVA Reducido: "IVA Reducido (*) X % s/BASE € ... IMPORTE €"
        m_red = re.search(
            r"IVA\s+Reducido[^0-9]*?([0-9]+(?:[,\.][0-9]+)?)\s*%\s*s\s*/\s*([0-9.,]+)\s*€[^€]*?([0-9.,]+)\s*€",
            self.text, re.IGNORECASE,
        )
        if not m_red:
            return {}

        def _f(s: str) -> Optional[float]:
            try:
                return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
            except (ValueError, TypeError):
                return None

        iva_red_pct = _f(m_red.group(1))
        iva_red_base = _f(m_red.group(2))
        iva_red_importe = _f(m_red.group(3))

        if iva_red_pct is not None:
            result["iva_reducido"] = iva_red_pct
        if iva_red_base is not None:
            result["iva_reducido_base"] = iva_red_base
        if iva_red_importe is not None:
            result["iva_reducido_importe"] = iva_red_importe

        # IVA general (tras el Reducido): "IVA   X % s/BASE €   IMPORTE €"
        # Buscar desde la posición donde termina el Reducido para no capturarlo dos veces.
        inicio = m_red.end()
        m_gen = re.search(
            r"IVA(?!\s+Reducido)[^\S\n]+([0-9]+(?:[,\.][0-9]+)?)\s*%\s*s\s*/\s*([0-9.,]+)\s*€[^€]*?([0-9.,]+)\s*€",
            self.text[inicio:], re.IGNORECASE,
        )
        if m_gen:
            iva_gen_pct = _f(m_gen.group(1))
            iva_gen_base = _f(m_gen.group(2))
            iva_gen_importe = _f(m_gen.group(3))
            if iva_gen_pct is not None:
                result["iva"] = iva_gen_pct
            if iva_gen_base is not None:
                result["iva_general_base"] = iva_gen_base
            if iva_gen_importe is not None:
                result["iva_general_importe"] = iva_gen_importe

        return result

    def extraer_imp_ele_eur_kwh(self) -> Optional[float]:
        """
        Iberdrola — Captura el precio €/kWh del impuesto eléctrico cuando
        el formato es post-RDL 7/2026: "Impuesto sobre electricidad N kWh × X €/kWh = Y €".
        Retorna None si la línea no existe o el formato es porcentaje.
        Mutuamente excluyente con extraer_imp_ele() (% sobre base).
        """
        for linha in self.linhas:
            l_strip = linha.strip().lower()
            if not l_strip.startswith("impuesto sobre electricidad"):
                continue
            m = re.search(
                r"impuesto\s+sobre\s+electricidad[^0-9]*?"
                r"[0-9.,]+\s*kWh\s*[x×]\s*([0-9]+[,\.][0-9]+)\s*€\s*/\s*kWh",
                linha, re.IGNORECASE,
            )
            if m:
                try:
                    val_str = m.group(1).replace(".", "").replace(",", ".") if "," in m.group(1) else m.group(1)
                    return float(val_str)
                except (ValueError, TypeError):
                    return None
        return None

    def extraer_descuentos(self) -> dict:
        """
        Iberdrola: "Descuento pertenencia Comunidad Solar 5%  5 % s/152,57 €  -7,63 €"
        Ignora linha de resumen "DESCUENTOS ENERGÍA" sem detalle de cálculo.

        FIX Bug #4 (2026-04-15): el método anterior usaba `nombre = re.split(r"[\\d%€\\-]", linha)[0]`,
        que cortaba al primer dígito y producía nombres genéricos como "Descuento sobre consumo"
        para líneas como "Descuento sobre consumo 10%" y "Descuento sobre consumo 5%". El segundo
        descuento se sobrescribía/saltaba.
        Solución: extraer el porcentaje del título y construir clave única:
          "Descuento sobre consumo 10%" + "Descuento sobre consumo 5%"
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
            if not valores_negativos:
                continue

            try:
                valor = abs(float(norm(valores_negativos[-1])))
                if not (0.01 <= valor <= 99999):
                    continue

                # Extraer nombre con porcentaje (FIX Bug #4)
                # Captura: "Descuento <texto> X%" donde X% está en el TÍTULO (antes del cálculo)
                # Ejemplo: "Descuento sobre consumo 10%       10 % s/208,81 €     -20,88 €"
                #   → grupo1 = "Descuento sobre consumo ", grupo2 = "10"
                m_titulo = re.match(
                    r"^\s*([Dd]escuento[^\d%]*?)(\d+(?:[,\.]\d+)?)\s*%",
                    linha,
                )
                if m_titulo:
                    base_nombre = m_titulo.group(1).strip().rstrip(".,: ")
                    pct = m_titulo.group(2).replace(",", ".")
                    nombre = f"{base_nombre} {pct}%"
                else:
                    # Fallback al método anterior si no cumple el patrón con %
                    nombre = re.split(r"[\d%€\-]", linha)[0].strip()
                    nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".,: ")

                if len(nombre) < 3:
                    continue

                nombre_norm = re.sub(r"\s+", "", nombre.lower())
                # CONVENCIÓN (2026-04-15): descuentos y excedentes son NEGATIVOS.
                # Coherente con el signo del PDF y con el schema `_processed.json`.
                valor_firmado = round(-valor, 6)
                # Dedup: misma clave normalizada Y mismo valor (comparamos valor absoluto
                # porque en el dict ya guardado también es negativo)
                ja_existe = any(
                    (re.sub(r"\s+", "", k.lower()) == nombre_norm)
                    and (abs(abs(v) - valor) < 0.01)
                    for k, v in resultado.items()
                )
                if not ja_existe:
                    resultado[nombre] = valor_firmado
                    self.raw[f"descuento_{nombre[:20]}"] = linha[:80]
                    print(f"  ✅  {'descuento':<26} = {valor_firmado:<20} ← {nombre}")
            except (ValueError, TypeError):
                pass

        base = super().extraer_descuentos()
        for k, v in base.items():
            k_norm = re.sub(r"\s+", "", k.lower())
            # base_parser.py devuelve valores absolutos — aquí los negativamos
            # para mantener la convención (2026-04-15).
            v_neg = round(-abs(v), 6)
            # Dedup AND (no OR como antes): la entrada del base se omite si:
            #   (a) ya existe una clave con MISMO nombre normalizado y MISMO valor, O
            #   (b) el nombre del base es PREFIJO de una clave nuestra con porcentaje
            #       y el valor coincide.
            ja_existe = False
            for r, rv in resultado.items():
                r_norm = re.sub(r"\s+", "", r.lower())
                if abs(abs(rv) - abs(v)) >= 0.01:
                    continue
                if r_norm == k_norm:
                    ja_existe = True
                    break
                # Caso (b): r_norm contiene k_norm seguido de un dígito (% en el sufijo)
                if r_norm.startswith(k_norm) and re.match(rf"^{re.escape(k_norm)}\d", r_norm):
                    ja_existe = True
                    break
            if not ja_existe:
                resultado[k] = v_neg

        return resultado
