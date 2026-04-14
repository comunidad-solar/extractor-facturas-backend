# extractor/parsers/naturgy.py
# Parser específico para facturas de Naturgy Iberia.
# Sobrescribe los métodos con comportamiento diferente al genérico.
#
# Particularidades de Naturgy:
#   - El PDF tiene líneas con puntos separadores que ocultan el texto real:
#       "...T...é....r..m......i.n...o...."  →  "Término"
#     Se limpian eliminando TODOS los puntos antes de procesar.
#   - imp_ele: usa factor decimal "69,91€ 0,025 1,75€" en lugar de porcentaje
#   - pp_p1/p2: "Término de potencia P1 (2,300 kW) 28 días 0,077976€/kW día"
#   - alq_eq_dia: "Alquiler de contador 28 días 0,026429€/día"
#   - Ignorar líneas del gráfico de tarta con porcentajes (9,49%, 0,84%, etc.)
#   - extraer_precios_energia(): precio único por sub-períodos → media ponderada → pe_p1
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from typing import Optional
from .base_parser import BaseParser
from ..base import norm

try:
    import fitz  # PyMuPDF
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False


def _desspacar(linha: str) -> str:
    """
    Colapsa caracteres separados por espaços simples produzidos pelo pdfplumber
    ao extrair a coluna direita de tabelas Naturgy.
    Exemplo: 'C o n s u m o' → 'Consumo'
             '0 ,.1 3 2 3 2 8' → '0,132328'
    Estratégia:
      1. Normalizar ',.N' ou ', .N' (artefacto decimal) → ',N'
      2. Se a linha parece "espaçada" (maioria dos tokens tem 1 char) → colapsar.
    """
    # Artefacto: vírgula+ponto antes de dígito  →  só vírgula
    s = re.sub(r',\s*\.\s*(?=\d)', ',', linha)
    tokens = s.split(' ')
    if len(tokens) < 4:
        return s
    single = sum(1 for t in tokens if len(t) == 1)
    if single / len(tokens) >= 0.55:
        s = ''.join(tokens)
        # Restaurar espaços antes de unidades e palavras-chave comuns
        s = re.sub(r'(\d)(kWh|kW|€|días?|día)', r'\1 \2', s, flags=re.IGNORECASE)
        s = re.sub(r'(kWh|kW|€|días?|día)(\w)', r'\1 \2', s, flags=re.IGNORECASE)
    return s


def _normalizar_espaçado(s: str) -> str:
    """
    Remove espaços entre caracteres individuais numa substring espaçada.
    '0 ,.1 3 2 3 2 8' → '0,132328'
    'C o n s u m o' → 'Consumo'
    """
    # Normalizar ',.' → ','
    s = re.sub(r',\s*\.\s*(?=\d)', ',', s)
    # Colapsar tokens de 1 char separados por espaço
    tokens = s.split(' ')
    resultado = []
    buffer = []
    for t in tokens:
        if len(t) <= 2:
            buffer.append(t)
        else:
            if buffer:
                resultado.append(''.join(buffer))
                buffer = []
            resultado.append(t)
    if buffer:
        resultado.append(''.join(buffer))
    return ' '.join(resultado)


def _limpiar(linha: str) -> str:
    """
    Elimina los separadores de puntos de Naturgy (secuencias de 2+
    puntos), pero preserva los puntos decimales (punto entre dígitos).
    Colapsa los espacios resultantes.
    Convierte "...T...é....r..m...i.n...o..." en "Término".
    """
    # Eliminar secuencias de 2 o más puntos
    s = re.sub(r'\.{2,}', ' ', linha)
    # Eliminar puntos aislados que NO estén entre dígitos
    # (preserva "0.151404" pero elimina " . " o "P1.")
    s = re.sub(r'(?<!\d)\.(?!\d)', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class NaturgyParser(BaseParser):

    def __init__(self, text: str, pdf_path: str = None):
        super().__init__(text)
        self.pdf_path      = pdf_path
        # Guardar texto original antes de cualquier preprocesado (pontos decimais intactos)
        self.text_original = text
        # Pre-procesar todas las líneas eliminando los puntos separadores
        self.linhas_clean  = [_desspacar(_limpiar(l)) for l in self.linhas]
        self._fitz_text    = None  # lazy — só extraído se necessário

    def _texto_fitz(self) -> str:
        """
        Extrai texto completo do PDF usando PyMuPDF (fitz),
        que lida melhor com tabelas de 2 colunas.
        Requer que self.pdf_path esteja definido.
        """
        if not _FITZ_OK or not getattr(self, 'pdf_path', None):
            return ""
        try:
            doc  = fitz.open(self.pdf_path)
            text = "\n".join(str(page.get_text()) for page in doc)
            doc.close()
            return text
        except Exception:
            return ""

    def _get_fitz_text(self) -> str:
        if self._fitz_text is None:
            self._fitz_text = self._texto_fitz()
        return self._fitz_text

    def extraer_precios_potencia(self):
        """
        Naturgy: "Término de potencia P1 (2,300 kW) 28 días 0,077976€/kW día 5,03€"
        Soporta P1..P6 (3.0TD). Usa las líneas limpias (sin puntos separadores).
        """
        resultados = {}  # período (int) → precio (str)

        patron_periodo = re.compile(r'P([1-6])', re.IGNORECASE)
        patron_precio  = re.compile(
            r"\([0-9,\.]+\s*kW\)\s*[0-9]+\s*d[ií]as?\s*([0-9]+[,\.][0-9]+)\s*€/kW",
            re.IGNORECASE
        )
        # Mapeo de palabras clave → período (facturas 2.0TD sin P1/P2 explícito)
        kw_periodo = {"punta": 1, "llano": 2, "valle": 3}

        # ── Prioridade 1: fitz (mais fiável para tabelas de 2 colunas) ──────────
        fitz_text = self._get_fitz_text()
        if fitz_text:
            patron_fitz = re.compile(
                r'[Tt]érmino de potencia P([1-6])\s*\([0-9,\.]+\s*kW\)\s*'
                r'([0-9]+)\s*d[ií]as?\s*([0-9,\.]+)\s*€/kW',
                re.IGNORECASE
            )
            for m in patron_fitz.finditer(fitz_text):
                periodo = int(m.group(1))
                precio  = norm(m.group(3))
                if precio and periodo not in resultados:
                    resultados[periodo] = precio
                    self.raw[f"pp_p{periodo}"] = m.group(0)[:80]
                    print(f"  ✅  pp_p{periodo:<22} = {precio:<20} ← Naturgy fitz P{periodo}")

        # ── Prioridade 2: pdfplumber (complementa o que fitz não encontrou) ────
        for linha_orig in self.linhas:
            linha = _normalizar_espaçado(linha_orig)
            linha = re.sub(r',\.', ',', linha)
            l = linha.lower()
            if "término de potencia" not in l and "termino de potencia" not in l:
                continue

            m_precio = patron_precio.search(linha)
            if not m_precio:
                continue

            precio = norm(m_precio.group(1))

            # Intentar capturar Pn explícito
            m_per = patron_periodo.search(linha)
            if m_per:
                per = int(m_per.group(1))
            else:
                per = next((v for k, v in kw_periodo.items() if k in l), None)

            # Só guardar se fitz ainda não preencheu este período
            if per is not None and per not in resultados:
                resultados[per] = precio
                self.raw[f"pp_p{per}"] = linha[:80]

        # Devolver pp_p1 y pp_p2 para compatibilidad con BaseParser
        pp1 = resultados.get(1)
        pp2 = resultados.get(2)

        # Escribir P3..P6 directamente en self.fields
        for per, precio in resultados.items():
            if per >= 3:
                try:
                    self.fields[f"pp_p{per}"] = float(precio)
                except (TypeError, ValueError):
                    pass

        return pp1, pp2

    def extraer_imp_ele(self):
        """
        Naturgy usa factor decimal: "Impuesto electricidad 69,91€ 0,025 1,75€"
        Se convierte multiplicando x 100.
        Ignora los porcentajes del gráfico de tarta de la página 1.
        """
        for linha in self.linhas_clean:
            l = linha.lower()
            if "impuesto electricidad" not in l:
                continue

            # "BASE€ 0,025 IMPORTE€"
            m = re.search(r"[0-9,\.]+\s*€\s+(0[,\.][0-9]+)\s+[0-9,\.]+\s*€", linha)
            if m:
                try:
                    factor = float(norm(m.group(1)))
                    if 0.005 <= factor <= 0.1:
                        self.raw["imp_ele"] = linha[:80]
                        return str(round(factor * 100, 6))
                except ValueError:
                    pass

        # Fallback: formato Tipo Mínimo Comunitario "X,XXX MWh  Y,YY€/MWh  Z,ZZ€"
        for linha in self.linhas_clean:
            l = linha.lower()
            if "impuesto electricidad" not in l:
                continue
            # Captura la tasa €/MWh (no es un porcentaje, es el precio unitario)
            m = re.search(
                r"impuesto electricidad.*?m[ií]nimo comunitario.*?([0-9]+[,\.][0-9]+)\s*€/MWh",
                linha, re.IGNORECASE
            )
            if m:
                try:
                    self.raw["imp_ele"] = linha[:80]
                    return norm(m.group(1))  # €/MWh, no multiplicar × 100
                except ValueError:
                    pass

        return None

    def extraer_alquiler(self):
        """
        Naturgy: "Alquiler de contador 28 días 0,026429€/día 0,74€"
        Usa las líneas limpias (sin puntos separadores).
        """
        for linha in self.linhas_clean:
            l = linha.lower()
            if "alquiler" not in l:
                continue
            # Ignorar línea del gráfico de tarta (texto sin espacios y muy larga)
            if len(l) > 100 and " " not in l[:20]:
                continue

            # "N días X,XXXXXX€/día" — con o sin espacio antes de días
            m = re.search(
                r"([0-9]+)\s*d[ií]as?\s*([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                linha, re.IGNORECASE
            )
            if m:
                self.raw["alq_eq_dia"] = linha[:80]
                return norm(m.group(2))

        return None

    # ── BONO SOCIAL ───────────────────────────────────────────────────────────

    def extraer_bono_social(self) -> Optional[str]:
        """
        Naturgy: "Financiación del Bono Social 28 días 0,006282€/día 0,18€"
        pdfplumber não extrai esta linha — usar fitz como fonte primária.
        """
        def _buscar(linhas):
            for linha in linhas:
                l = linha.lower()
                if "bono social" not in l:
                    continue
                # Padrão 1 — €/día explícito
                m = re.search(
                    r"([0-9]+[,\.][0-9]+)\s*€/d[ií]a",
                    linha, re.IGNORECASE
                )
                if m:
                    self.raw["bono_social"] = linha[:80]
                    return norm(m.group(1))
                # Padrão 2 — dividir total pelos dias
                m = re.search(r"([0-9]+[,\.][0-9]+)\s*€", linha, re.IGNORECASE)
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

        # Fonte primária: fitz
        fitz_text = self._get_fitz_text()
        if fitz_text:
            result = _buscar(fitz_text.splitlines())
            if result:
                return result

        # Fallback: linhas limpas e originais
        return _buscar(self.linhas_clean) or _buscar(self.linhas)

    # ── PRECIOS DE ENERGÍA ────────────────────────────────────────────────────

    def extraer_precios_energia(self) -> None:
        """
        Naturgy — três casos tratados por ordem de prioridade:

        1) 3.0TD — "Consumo electricidad P1  0 kWh  0,151404€/kWh  0,00€"
           Usa self.text_original (com pontos decimais intactos).
           Captura todos os períodos P1..P6 mesmo com consumo zero.

        2) Preço único por sub-períodos — "Período de DD.MM.YYYY a DD.MM.YYYY  X kWh  Y€/kWh"
           Usa linhas limpas; calcula média ponderada → pe_p1.

        3) Fallback ao BaseParser com text_original (evita que pontos removidos
           destruam decimais dos preços).
        """
        # ── Padrão 1: 3.0TD com "Consumo electricidad P1..P6" ────────────────
        # Usa linhas originais normalizadas (lida com texto misto + chars espaçados)
        patron_3td = re.compile(
            r'Consumo\s*electricidad\s*P([1-6])\s*([\d,\.]+)\s*kWh\s*([\d,\.]+)\s*€/kWh',
            re.IGNORECASE
        )
        for linha_orig in self.linhas:
            linha_norm = _normalizar_espaçado(linha_orig)
            linha_norm = re.sub(r',\.', ',', linha_norm)
            m = patron_3td.search(linha_norm)
            if m:
                periodo = int(m.group(1))
                val = norm(m.group(3))
                if val is None:
                    continue
                try:
                    precio = float(val)
                    campo = f"pe_p{periodo}"
                    if self.fields.get(campo) is None:
                        self.fields[campo] = precio
                        self.raw[campo] = linha_norm[:80]
                        print(f"  ✅  {campo:<26} = {precio:<20} ← Naturgy 3.0TD P{periodo}")
                except ValueError:
                    pass

        # Se encontrou menos de 2 períodos, tentar via fitz
        achados = sum(1 for n in range(1, 7) if self.fields.get(f"pe_p{n}") is not None)
        if achados < 2:
            fitz_text = self._get_fitz_text()
            if fitz_text:
                patron_fitz = re.compile(
                    r'Consumo electricidad P([1-6])\s+([\d,\.]+)\s*kWh\s+([\d,\.]+)\s*€/kWh',
                    re.IGNORECASE
                )
                for m in patron_fitz.finditer(fitz_text):
                    periodo = int(m.group(1))
                    val = norm(m.group(3))
                    if val is None:
                        continue
                    try:
                        precio = float(val)
                        campo = f"pe_p{periodo}"
                        if self.fields.get(campo) is None:
                            self.fields[campo] = precio
                            self.raw[campo]    = m.group(0)[:80]
                            print(f"  ✅  {campo:<26} = {precio:<20} ← Naturgy fitz P{periodo}")
                    except ValueError:
                        pass

        achou = any(self.fields.get(f"pe_p{n}") is not None for n in range(1, 7))
        if achou:
            return

        # ── Padrão 2: preço único por sub-períodos ────────────────────────────
        patron_subperiodo = re.compile(
            r'Per[ií]odo\s+de\s+[\d\.]+\s+a\s+[\d\.]+\s+'
            r'([\d\.]+)\s*kWh\s+([0-9]+[,\.][0-9]+)\s*€/kWh',
            re.IGNORECASE
        )
        kwh_total   = 0.0
        valor_total = 0.0
        encontrou   = False

        for linha in self.linhas_clean:
            m = patron_subperiodo.search(linha)
            if m:
                try:
                    kwh   = float(norm(m.group(1)))
                    preco = float(norm(m.group(2)))
                    kwh_total   += kwh
                    valor_total += kwh * preco
                    encontrou    = True
                    self.raw["pe_p1"] = linha[:80]
                except ValueError:
                    pass

        if encontrou and kwh_total > 0:
            media = round(valor_total / kwh_total, 6)
            self.fields["pe_p1"] = media
            print(f"  ✅  {'pe_p1':<26} = {media:<20} ← precio energía único (media ponderada)")
            return

        # ── Fallback: BaseParser com texto original (pontos decimais intactos) ─
        texto_backup = self.text
        self.text = self.text_original
        try:
            super().extraer_precios_energia()
        finally:
            self.text = texto_backup

    def extraer_potencias_contratadas(self) -> dict:
        """
        Naturgy 3.0TD: "Potencia contratada P1  6,67 kW"
        Naturgy 2.0TD: "Potencia contratada P1  2,30 kW / P2  2,30 kW"
        Usa fitz como fonte primária (tabela de 2 colunas).
        """
        result = {}

        # Fonte primária: fitz
        fitz_text = self._get_fitz_text()
        texto = fitz_text if fitz_text else self.text

        for p in range(1, 7):
            m = re.search(
                rf"[Pp]otencia\s+contratada\s+P{p}\s+([0-9,\.]+)\s*kW",
                texto, re.IGNORECASE
            )
            if m:
                result[f"pot_p{p}_kw"] = float(norm(m.group(1)))

        # Fallback com linhas limpas
        if not result:
            for linha in self.linhas_clean:
                for p in range(1, 7):
                    m = re.search(
                        rf"[Pp]otencia\s+contratada\s+P{p}\s+([0-9,\.]+)\s*kW",
                        linha, re.IGNORECASE
                    )
                    if m and f"pot_p{p}_kw" not in result:
                        result[f"pot_p{p}_kw"] = float(norm(m.group(1)))

        return result or super().extraer_potencias_contratadas()