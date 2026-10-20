"""Funciones de "cuentas": reglas fijas del estándar, en Python puro (sin IA)."""

import re
from pathlib import Path

import yaml

RUTA_VOCABULARIO = Path(__file__).parent / "Data" / "estandar" / "vocabulario.yaml"


def calcular_digito_verificador(primeros_12: str) -> int:
    """Calcula el dígito verificador de un GTIN-13 a partir de sus primeros 12 dígitos.

    Ejemplo: "779346961684" -> 6  (el GTIN completo es 7793469616846)
    """
    if len(primeros_12) != 12 or not primeros_12.isdigit():
        raise ValueError(f"Se esperaban 12 dígitos, llegó: {primeros_12!r}")

    suma = 0
    for posicion, caracter in enumerate(primeros_12):
        peso = 1 if posicion % 2 == 0 else 3  # posiciones 0, 2, 4... pesan 1; 1, 3, 5... pesan 3
        suma += int(caracter) * peso

    return (10 - suma % 10) % 10  # lo que falta para la próxima decena (si la suma ya es decena, 0)


def normalizar_gtin(texto) -> tuple[str | None, str | None]:
    """Limpia el código de barras que mandó el proveedor y lo valida.

    Devuelve (gtin, motivo):
      - Si está bien:  ("7797137444038", None)
      - Si hay algo mal: (None, "gtin_faltante") o (None, "gtin_invalido")
    """
    texto = "" if texto is None else str(texto).strip()

    # Sin ningún número -> el proveedor no lo informó (vacío, o una frase como "se lo paso la semana que viene")
    if not any(caracter.isdigit() for caracter in texto):
        return None, "gtin_faltante"

    # Sacamos guiones y espacios, que son solo formato ("779-7137-44403-8")
    limpio = texto.replace("-", "").replace(" ", "")
    if not limpio.isdigit():
        return None, "gtin_invalido"  # quedaron letras u otros símbolos

    # 12 dígitos = UPC (código de EE.UU.) -> se pasa a GTIN-13 con un 0 adelante
    if len(limpio) == 12:
        limpio = "0" + limpio

    if len(limpio) != 13:
        return None, "gtin_invalido"

    if calcular_digito_verificador(limpio[:12]) != int(limpio[-1]):
        return None, "gtin_invalido"

    return limpio, None


def convertir_numero(texto, separador_decimal: str = ",") -> float | None:
    """Convierte un número escrito como en el archivo del proveedor a float.

    En español (separador_decimal=","): "68,91" -> 68.91 · "1.000" -> 1000.0 · "1.234,56" -> 1234.56
    En inglés  (separador_decimal="."): "4.8" -> 4.8 · "1,000" -> 1000.0
    Si está vacío o no es un número, devuelve None (no inventamos un valor).
    """
    texto = "" if texto is None else str(texto).strip()
    if texto == "":
        return None

    if separador_decimal == ",":
        texto = texto.replace(".", "")    # el punto es de miles: lo sacamos
        texto = texto.replace(",", ".")   # la coma es decimal: la pasamos a punto (como lo entiende Python)
    else:
        texto = texto.replace(",", "")    # en inglés la coma es de miles: la sacamos

    try:
        return float(texto)
    except ValueError:
        return None


# Cada unidad que puede mandar un proveedor -> (unidad del estándar, factor para multiplicar)
UNIDADES = {
    "ML": ("ML", 1),
    "CC": ("ML", 1),
    "L": ("ML", 1000),
    "LT": ("ML", 1000),
    "LTS": ("ML", 1000),
    "FL OZ": ("ML", 29.5735),  # onza líquida
    "G": ("G", 1),
    "GR": ("G", 1),
    "GRS": ("G", 1),
    "KG": ("G", 1000),
    "OZ": ("G", 28.3495),      # onza de peso
    "UN": ("UN", 1),
    "UNID": ("UN", 1),
    "CT": ("UN", 1),           # "count" en inglés
}


def convertir_contenido(cantidad: float | None, unidad) -> tuple[int | None, str | None]:
    """Lleva el contenido a la unidad del estándar (ML, G o UN), redondeado al entero.

    Ejemplos: (0.25, "LT") -> (250, "ML") · (90, "GR") -> (90, "G") · (4.8, "fl oz") -> (142, "ML")
    Si falta la cantidad o la unidad no se conoce, devuelve (None, None): no inventamos.
    """
    if cantidad is None or unidad is None:
        return None, None

    clave = str(unidad).strip().upper().rstrip(".")  # "ml." -> "ML", " Lts" -> "LTS"
    if clave not in UNIDADES:
        return None, None

    unidad_estandar, factor = UNIDADES[clave]
    valor = cantidad * factor
    return int(valor + 0.5), unidad_estandar  # redondeo "de la escuela": .5 sube


def cargar_abreviaturas(ruta: Path = RUTA_VOCABULARIO) -> dict[str, str]:
    """Lee las abreviaturas del vocabulario oficial. Ej: {"SH.": "SHAMPOO", "S/": "SIN", ...}"""
    with open(ruta, encoding="utf-8-sig") as archivo:
        vocabulario = yaml.safe_load(archivo)
    return vocabulario["abreviaturas"]


def expandir_abreviaturas(texto, abreviaturas: dict[str, str]) -> str | None:
    """Pasa el texto a mayúsculas y escribe completas las abreviaturas del vocabulario.

    Ej: "Pasta Dental Blanq." -> "PASTA DENTAL BLANQUEADORA"
        "DESOD. AER. BRISA S/ PERF." -> "DESODORANTE AEROSOL BRISA SIN PERFUME"
    """
    if texto is None:
        return None

    resultado = str(texto).upper()

    # De la más larga a la más corta, para que "TRAT. CAP." se reemplace entera
    for abreviatura in sorted(abreviaturas, key=len, reverse=True):
        # Solo si ANTES no hay una letra o número (así "REP/CION" no se toca por "P/")
        patron = r"(?<![A-ZÑ0-9])" + re.escape(abreviatura)
        resultado = re.sub(patron, abreviaturas[abreviatura] + " ", resultado)

    return " ".join(resultado.split())  # deja un solo espacio entre palabras