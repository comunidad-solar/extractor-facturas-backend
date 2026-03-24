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
#
# Modificado: 2026-02-26 | Rodrigo Costa

import re
from .base_parser import BaseParser
from ..base import norm


def _limpiar(linha: str) -> str:
    """
    Elimina todos los puntos de una línea y colapsa los espacios resultantes.
    Convierte "...T...é....r..m...i.n...o..." en "Término".
    """
    s = re.sub(r'\.+', '', linha)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class NaturgyParser(BaseParser):

    def __init__(self, text: str):
        super().__init__(text)
        # Pre-procesar todas las líneas eliminando los puntos separadores
        self.linhas_clean = [_limpiar(l) for l in self.linhas]

    def extraer_precios_potencia(self):
        """
        Naturgy: "Término de potencia P1 (2,300 kW) 28 días 0,077976€/kW día 5,03€"
        Usa las líneas limpias (sin puntos separadores).
        """
        pp1 = pp2 = None
        src1 = src2 = ""

        for linha in self.linhas_clean:
            l = linha.lower()
            if "término de potencia" not in l and "termino de potencia" not in l:
                continue

            # "(X,XXX kW) N días Y,YYYYYY€/kW día"
            m = re.search(
                r"\([0-9,\.]+\s*kW\)\s*([0-9]+)\s*d[ií]as?\s*([0-9]+[,\.][0-9]+)\s*€/kW",
                linha, re.IGNORECASE
            )
            if m:
                precio = norm(m.group(2))
                if "p1" in l or "punta" in l:
                    pp1, src1 = precio, linha[:80]
                elif "p2" in l or "llano" in l or "valle" in l:
                    pp2, src2 = precio, linha[:80]

        self.raw["pp_p1"] = src1
        self.raw["pp_p2"] = src2
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