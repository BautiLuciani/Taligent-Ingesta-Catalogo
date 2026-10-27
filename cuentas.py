"""Funciones de "cuentas": reglas fijas del estándar, en Python puro (sin IA)."""

import re
from datetime import date
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


def cargar_vocabulario(ruta: Path = RUTA_VOCABULARIO) -> dict:
    """Lee el vocabulario oficial completo (tipos, unidades, estados, motivos, abreviaturas...)."""
    with open(ruta, encoding="utf-8-sig") as archivo:
        return yaml.safe_load(archivo)


def cargar_abreviaturas(ruta: Path = RUTA_VOCABULARIO) -> dict[str, str]:
    """Lee las abreviaturas del vocabulario oficial. Ej: {"SH.": "SHAMPOO", "S/": "SIN", ...}"""
    return cargar_vocabulario(ruta)["abreviaturas"]


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



def separar_contenido(texto, separador_decimal: str = ",") -> tuple[float | None, str | None]:
    """Separa un contenido escrito todo junto en (cantidad, unidad), como vienen en los PDF.

    Ejemplos: "X 500 ML" -> (500.0, "ML") · "250ML" -> (250.0, "ML") · "60g" -> (60.0, "g")
              "0,5 KG" -> (0.5, "KG") · "4.8 fl oz" (inglés) -> (4.8, "fl oz")
    La unidad sale tal cual: la normaliza después convertir_contenido.
    Si no tiene la forma "número + unidad", devuelve (None, None): no inventamos.
    """
    texto = "" if texto is None else " ".join(str(texto).split())
    # Una "X" opcional adelante, el número (con coma o punto) y la unidad (letras, puede tener espacio: "fl oz")
    coincidencia = re.fullmatch(r"(?:[Xx]\s*)?(\d[\d.,]*)\s*([A-Za-z][A-Za-z. ]*)", texto)
    if coincidencia is None:
        return None, None
    cantidad = convertir_numero(coincidencia.group(1), separador_decimal)
    if cantidad is None:
        return None, None
    return cantidad, coincidencia.group(2).strip()


def convertir_precio(texto, separador_decimal: str = ",") -> tuple[float | None, str | None]:
    """Separa un precio escrito con su moneda en (monto, moneda), según el estándar (sección 6).

    Ejemplos: "$ 88,04" -> (88.04, "UYU") · "USD 12.50" (inglés) -> (12.5, "USD") · "117,34" -> (117.34, None)
    - "USD", "US$" o "U$S" -> USD (se mira primero: "US$" también tiene un "$").  "$" solo -> UYU.
    - Sin símbolo -> moneda None: la decide quien llama, con la moneda de la lista (no la adivinamos acá).
    """
    texto = "" if texto is None else str(texto).strip()
    numero = re.search(r"\d[\d.,]*", texto)
    monto = convertir_numero(numero.group(0), separador_decimal) if numero else None
    if monto is None:
        return None, None

    mayusculas = texto.upper()
    if "USD" in mayusculas or "US$" in mayusculas or "U$S" in mayusculas:
        return monto, "USD"
    if "$" in texto:
        return monto, "UYU"
    return monto, None


# Los meses en español, para las fechas escritas con palabras ("1 de octubre de 2026")
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def leer_fecha(texto) -> date | None:
    """La primera fecha que aparece en un texto, como fecha de Python (para poder compararlas).

    Ejemplos: "Vigencia desde: 15/10/2026" -> date(2026, 10, 15)
              "Vigencia desde el 1 de octubre de 2026" -> date(2026, 10, 1)
    Si no hay fecha, o la fecha no existe (31/02/2026), devuelve None: no se inventa.
    """
    texto = "" if texto is None else str(texto)
    numerica = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    con_palabras = re.search(r"(\d{1,2}) de ([a-záéíóú]+) de (\d{4})", texto.lower())
    try:
        if numerica:
            return date(int(numerica.group(3)), int(numerica.group(2)), int(numerica.group(1)))
        if con_palabras and con_palabras.group(2) in MESES:
            return date(int(con_palabras.group(3)), MESES[con_palabras.group(2)], int(con_palabras.group(1)))
    except ValueError:  # 31/02/2026 o 15/13/2026: la fecha no existe
        return None
    return None


def contenido_de_presentacion(texto, separador_decimal: str = ",") -> tuple[float | None, str | None]:
    """El contenido de una presentación de medicamento: el número después de la "x", con su unidad.

    Ejemplos: "Comp. rec. x 20" -> (20.0, "UN") · "Susp. x 200 ml" -> (200.0, "ml") · "Gel tópico x 60 gr" -> (60.0, "gr")
    Sin unidad se cuentan unidades: "comprimidos, cápsulas, sobres [...] se cuentan en UN" (estándar, sección 4).
    La unidad sale tal cual: la normaliza después convertir_contenido. Sin "x número" -> (None, None).
    """
    texto = "" if texto is None else " ".join(str(texto).split())
    coincidencia = re.search(r"\bx\s*(\d[\d.,]*)\s*([A-Za-z]*)\s*$", texto, re.IGNORECASE)
    if coincidencia is None:
        return None, None
    cantidad = convertir_numero(coincidencia.group(1), separador_decimal)
    if cantidad is None:
        return None, None
    return cantidad, coincidencia.group(2) or "UN"


# Condición de venta como la escriben los proveedores -> como la pide el estándar (vocabulario)
CONDICIONES = {"VL": "VENTA_LIBRE", "VBR": "BAJO_RECETA"}


def convertir_condicion(texto) -> str | None:
    """"VL" -> "VENTA_LIBRE" · "VBR" -> "BAJO_RECETA". Otra cosa -> None (no se adivina)."""
    return CONDICIONES.get("" if texto is None else str(texto).strip().upper())