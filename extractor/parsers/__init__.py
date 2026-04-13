# extractor/parsers/__init__.py
# Registro central de parsers por comercializadora.
# Para añadir una nueva: crear el archivo e importarlo aquí.
#
# Modificado: 2026-02-27 | Rodrigo Costa
#   - get_parser() acepta pdf_path opcional para parsers que necesitan acceso directo al PDF

from .energyavm import EnergyaVMParser
from .repsol    import RepsolParser
from .octopus   import OctopusParser
from .naturgy   import NaturgyParser
from .iberdrola import IberdrolaParser
from .endesa    import EndesaParser
from .generic   import GenericParser
from .cox       import CoxParser
from .contigo import ContigoParser
from .naturgy_regulada import NaturgyReguladaParser
from .pepeenergy import PepeEnergyParser
from .plenitude    import PlenitudeParser
from .energiaxxi   import EnergiaXXIParser



REGISTRY: dict = {
    "repsol":    RepsolParser,
    "octopus":   OctopusParser,
    "naturgy":   NaturgyParser,
    "iberdrola": IberdrolaParser,
    "endesa":    EndesaParser,
    "generic":   GenericParser,
    "cox":       CoxParser,
    "energyavm": EnergyaVMParser,  
    "contigo": ContigoParser,
    "naturgy_regulada": NaturgyReguladaParser, 
    "pepeenergy": PepeEnergyParser,
    "plenitude":   PlenitudeParser,
    "energiaxxi":  EnergiaXXIParser,
}


def get_parser(nombre: str, text: str, pdf_path: str = ""):
    """
    Devuelve una instancia del parser adecuado para la comercializadora dada.
    pdf_path se pasa únicamente a parsers que necesitan acceso directo al PDF (ej: CoxParser).
    Si el nombre no está en el registro, usa GenericParser.
    """
    cls = REGISTRY.get(nombre, GenericParser)
    # CoxParser y NaturgyParser aceptan pdf_path — los demás solo reciben text
    if cls in (CoxParser, NaturgyParser):
        return cls(text, pdf_path)
    return cls(text)