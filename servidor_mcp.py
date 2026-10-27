"""Servidor MCP del proyecto: las tools con las que el agente lee los datos y registra las fichas.

Se comunica por stdio: NUNCA usar print() acá (stdout es el canal con el agente).
"""
import csv
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from cuentas import (cargar_abreviaturas, cargar_vocabulario, contenido_de_presentacion, convertir_condicion,
                     convertir_contenido, convertir_numero, convertir_precio, expandir_abreviaturas, normalizar_gtin,
                     separar_contenido)

CARPETA_DATA = Path(__file__).parent / "Data"
ABREVIATURAS = cargar_abreviaturas()
VOCABULARIO = cargar_vocabulario()

# Dónde se guardan los resultados. Se puede cambiar con una variable de entorno
# (las pruebas la usan para escribir en una carpeta temporal y no pisar los resultados reales).
CARPETA_SALIDA = Path(os.getenv("INGESTA_CARPETA_SALIDA", Path(__file__).parent / "salida"))
RUTA_RESULTADOS = CARPETA_SALIDA / "resultados.json"

# Lo que sacó extractor_pdf.py de cada PDF (semana 2). Es una ENTRADA, no una salida de las pruebas:
# por eso no depende de INGESTA_CARPETA_SALIDA.
CARPETA_EXTRACCIONES = Path(__file__).parent / "salida" / "extracciones"

# Cómo leer el archivo de cada proveedor habilitado.
# P06 (Bebé Feliz) NO está: es el proveedor apartado hasta la semana 5.
PROVEEDORES = {
    "P03": {
        "formato": "csv",
        "archivo": CARPETA_DATA / "proveedores" / "P03_Distribuidora_Litoral" / "litoral_altas_102026.csv",
        "separador": ";",
        "decimal": ",",
        "moneda": "UYU",  # el CSV no indica moneda -> pesos uruguayos (estándar, sección 6)
    },
    "P07": {
        "formato": "pdf",
        "extraccion": CARPETA_EXTRACCIONES / "LHS_catalogo_nuevos_productos.json",  # lo armó extractor_pdf.py
        # Qué columna del PDF es cada cosa (las columnas las fija COLUMNAS_POR_PDF del extractor)
        "campos": {"descripcion": "descripcion", "contenido": "contenido", "ean": "ean", "precio": "costo"},
        "fds": CARPETA_EXTRACCIONES / "fds_P07_Limpieza_Hogar_Sur.json",  # lo armó extractor_fds.py
        "moneda": "UYU",  # solo si un precio viniera sin símbolo; los de LHS traen "$" -> UYU (estándar, sección 6)
    },
    "P01": {
        "formato": "pdf",
        "extraccion": CARPETA_EXTRACCIONES / "Lista_de_precios_octubre_2026.json",  # lo armó extractor_pdf.py
        # Andes no trae "contenido" sino "presentacion" ("Comp. rec. x 20"), y trae la condición de venta (VL/VBR)
        "campos": {"descripcion": "producto", "presentacion": "presentacion", "ean": "ean", "precio": "precio",
                   "condicion": "condicion"},
        "moneda": "UYU",  # la lista está en "$" -> pesos uruguayos (estándar, sección 6)
    },
}


# --- Catálogo actual: se carga una sola vez al arrancar el servidor ---
RUTA_CATALOGO = CARPETA_DATA / "catalogo" / "catalogo_actual.csv"


def cargar_catalogo() -> list[dict]:
    """Lee el catálogo actual. A cada producto le agrega su fuente (archivo y línea)."""
    productos = []
    with open(RUTA_CATALOGO, encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        for fila in lector:
            fila["fuente"] = {"archivo": RUTA_CATALOGO.name, "linea": lector.line_num}
            productos.append(fila)
    return productos


CATALOGO = cargar_catalogo()
CATALOGO_POR_GTIN = {producto["gtin"]: producto for producto in CATALOGO}  # índice para buscar al instante


def clave_parecido(marca, contenido: int | None, unidad: str | None) -> tuple:
    """La "llave" para buscar parecidos: marca + contenido + unidad, todo ya normalizado."""
    return (str(marca).strip().upper(), contenido, unidad)


def indexar_parecidos(catalogo: list[dict]) -> dict[tuple, list[dict]]:
    """Arma el índice (marca, contenido, unidad) -> productos del catálogo con esos valores.

    El catálogo viejo tiene unidades como GRS o CC: las pasamos por convertir_contenido
    para comparar contra los productos nuevos en la misma unidad.
    """
    indice = {}
    for producto in catalogo:
        contenido, unidad = convertir_contenido(convertir_numero(producto["contenido"]), producto["unidad"])
        clave = clave_parecido(producto["marca"], contenido, unidad)
        indice.setdefault(clave, []).append(producto)
    return indice


CATALOGO_POR_PARECIDO = indexar_parecidos(CATALOGO)

mcp = FastMCP("ingesta-catalogo")


def leer_filas_csv(proveedor_id: str, config: dict) -> list[dict]:
    """Lee el CSV del proveedor y arma cada fila con su fuente y los valores ya calculados por código."""
    ruta = config["archivo"]
    filas = []
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter=config["separador"])
        for fila in lector:
            gtin, motivo_gtin = normalizar_gtin(fila["ean"])
            cantidad = convertir_numero(fila["contenido"], config["decimal"])
            contenido, unidad = convertir_contenido(cantidad, fila["unidad"])
            filas.append({
                "item_id": f"{proveedor_id}:{fila['codigo']}",
                "fuente": {"archivo": ruta.name, "linea": lector.line_num},
                "original": fila,
                "calculado": {
                    "gtin": gtin,
                    "motivo_gtin": motivo_gtin,
                    "descripcion_expandida": expandir_abreviaturas(fila["descripcion"], ABREVIATURAS),
                    "marca": fila["marca"].strip().upper(),
                    "contenido": contenido,
                    "unidad": unidad,
                    "precio_costo": convertir_numero(fila["precio"], config["decimal"]),
                    "moneda": config["moneda"],
                },
            })
    return filas


def leer_filas_pdf(proveedor_id: str, config: dict) -> list[dict]:
    """Lee lo que sacó extractor_pdf.py de un PDF y arma cada fila con la MISMA forma que leer_filas_csv.

    La fuente es {archivo, pagina} (la página la dio la API con citations, no el modelo).
    En original va la fila verificada del PDF, sus campos tal cual y los problemas de la extracción.
    config["campos"] dice qué columna es cada cosa (cada PDF tiene las suyas): el contenido sale de "contenido"
    ("X 500 ML") o de "presentacion" ("Comp. rec. x 20"), y la condición de venta, solo si la lista la trae.
    El PDF no trae la marca en una columna aparte: no va en calculado, la decide el agente desde la descripción.
    """
    ruta = config["extraccion"]
    if not ruta.exists():
        raise FileNotFoundError(f"Falta {ruta.name}: primero hay que correr extractor_pdf.py sobre ese PDF.")
    extraccion = json.loads(ruta.read_text(encoding="utf-8"))

    mapa = config["campos"]
    filas = []
    for producto in extraccion["productos"]:
        campos = producto["campos"]

        def columna(cosa):
            """El valor tal cual de la columna que en este PDF es esa cosa (None si el PDF no la tiene)."""
            return campos.get(mapa[cosa]) if cosa in mapa else None

        gtin, motivo_gtin = normalizar_gtin(columna("ean"))
        if "contenido" in mapa:
            contenido, unidad = convertir_contenido(*separar_contenido(columna("contenido")))
        else:
            contenido, unidad = convertir_contenido(*contenido_de_presentacion(columna("presentacion")))
        precio, moneda = convertir_precio(columna("precio"))
        if precio is not None and moneda is None:
            moneda = config["moneda"]  # precio sin símbolo: rige la moneda de la lista
        calculado = {
            "gtin": gtin,
            "motivo_gtin": motivo_gtin,
            "descripcion_expandida": expandir_abreviaturas(columna("descripcion"), ABREVIATURAS),
            "contenido": contenido,
            "unidad": unidad,
            "precio_costo": precio,
            "moneda": moneda,
        }
        if "condicion" in mapa:  # solo las listas de medicamentos la traen
            calculado["condicion_venta"] = convertir_condicion(columna("condicion"))
        filas.append({
            "item_id": f"{proveedor_id}:{producto['codigo']}",
            "fuente": producto["fuente"],
            "original": {"fila": producto["fila"], **campos, "problemas_extraccion": producto["problemas"]},
            "calculado": calculado,
        })
    return filas


# Cada formato de archivo, con la función que lo lee. Todas devuelven filas con la misma forma.
LECTORES = {"csv": leer_filas_csv, "pdf": leer_filas_pdf}


def indexar_fds(ruta: Path | None) -> dict[str, list[dict]]:
    """código -> las FDS que lo nombran en su sección 1 (lo que armó extractor_fds.py).

    Un proveedor sin FDS (ruta None) da un índice vacío: ninguno de sus productos tiene ficha de seguridad.
    """
    if ruta is None:
        return {}
    if not ruta.exists():
        raise FileNotFoundError(f"Falta {ruta.name}: primero hay que correr extractor_fds.py sobre esas FDS.")
    indice = {}
    for ficha in json.loads(ruta.read_text(encoding="utf-8"))["fichas"]:
        for codigo in ficha["codigos"]:
            indice.setdefault(codigo, []).append(ficha)
    return indice


def fds_del_producto(codigo: str, indice_fds: dict[str, list[dict]]) -> dict | None:
    """Cruza un producto con su FDS por código (el dato que cruza archivos se consolida en código).

    - Ninguna FDS lo nombra -> None (si es de las familias que llevan FDS, el agente pone pendiente_fds).
    - Una FDS -> su peligro_deposito, numero_onu y fuente (la página de la sección 14 de ESA FDS).
    - Más de una -> sin peligro y con el problema: no se elige una (lo mismo que con las filas del PDF).
    """
    fichas = indice_fds.get(codigo, [])
    if not fichas:
        return None
    if len(fichas) > 1:
        archivos = ", ".join(ficha["archivo"] for ficha in fichas)
        return {"peligro_deposito": None, "numero_onu": None, "fuente": None,
                "problemas": [f"{codigo} aparece en {len(fichas)} FDS ({archivos}): no se elige una."]}
    ficha = fichas[0]
    return {"peligro_deposito": ficha["peligro_deposito"], "numero_onu": ficha["numero_onu"],
            "fuente": ficha["fuente"], "problemas": ficha["problemas"]}


def leer_filas(proveedor_id: str, config: dict) -> list[dict]:
    """Lee las filas de un proveedor con el lector de su formato (CSV, PDF...) y le suma a cada una su FDS."""
    filas = LECTORES[config["formato"]](proveedor_id, config)
    indice_fds = indexar_fds(config.get("fds"))
    for fila in filas:
        codigo = fila["item_id"].split(":", 1)[1]  # "P07:LHS-206" -> "LHS-206"
        fila["calculado"]["fds"] = fds_del_producto(codigo, indice_fds)
    return filas


@mcp.tool(annotations={"readOnlyHint": True})
def leer_archivo_proveedor(
    proveedor_id: Annotated[Literal["P01", "P03", "P07"], Field(description="Código del proveedor a leer.")],
    desde: Annotated[int, Field(ge=0, description="Posición de la primera fila (empieza en 0).")] = 0,
    cantidad: Annotated[int, Field(ge=1, le=25, description="Cuántas filas devolver (máximo 25).")] = 10,
) -> dict:
    """Lee los productos nuevos que mandó un proveedor, de a tandas.

    Usala para obtener los productos a procesar. Cada fila trae:
    - item_id y fuente (archivo y línea en un CSV; archivo y página en un PDF) para citar de dónde sale cada dato;
    - original: los valores tal como vinieron en el archivo (en un PDF, la fila verificada y sus campos);
    - calculado: lo que ya resolvió el código (GTIN validado y su motivo si hay problema,
      descripción sin abreviaturas, contenido en ML/G/UN, precio como número y moneda, la condición de venta
      (VENTA_LIBRE o BAJO_RECETA) cuando la lista la trae, y la marca
      cuando el archivo la trae en su propia columna) y fds: la ficha de datos de seguridad que lo nombra
      (peligro_deposito, numero_onu y su fuente), o null si ninguna FDS del proveedor lo nombra.
      Usá estos valores: no rehagas las cuentas.
      Lo que calculado no trae (por ejemplo, la marca en un PDF) lo decidís desde original.
    Si 'siguiente' no es null, hay más filas: volvé a llamarla con desde=siguiente.
    """
    filas = leer_filas(proveedor_id, PROVEEDORES[proveedor_id])
    total = len(filas)
    if desde >= total:
        raise ToolError(f"'desde'={desde} está fuera de rango: el archivo tiene {total} filas (0 a {total - 1}).")

    tanda = filas[desde:desde + cantidad]
    siguiente = desde + cantidad if desde + cantidad < total else None
    return {"proveedor_id": proveedor_id, "total": total, "desde": desde, "siguiente": siguiente, "filas": tanda}


@mcp.tool(annotations={"readOnlyHint": True})
def buscar_por_gtin(
    gtin: Annotated[str, Field(pattern=r"^\d{13}$", description="GTIN de 13 dígitos (el campo calculado.gtin de la fila).")],
) -> dict:
    """Busca un GTIN en el catálogo actual de la cadena.

    Usala con cada producto que trae GTIN válido (calculado.gtin no es null), para saber si ya existe.
    - encontrado=true: el producto ya está cargado -> estado duplicado, con el sku en duplicado_de.
    - encontrado=false: el GTIN no está en el catálogo.
    """
    producto = CATALOGO_POR_GTIN.get(gtin)
    if producto is None:
        return {"gtin": gtin, "encontrado": False}
    return {
        "gtin": gtin,
        "encontrado": True,
        "sku": producto["sku"],
        "descripcion": producto["descripcion"],
        "fuente": producto["fuente"],
    }


@mcp.tool(annotations={"readOnlyHint": True})
def buscar_parecidos(
    marca: Annotated[str, Field(min_length=1, description="Marca del producto: calculado.marca, o la que decidiste desde original si calculado no la trae.")],
    contenido: Annotated[int, Field(ge=1, description="Contenido ya convertido (calculado.contenido).")],
    unidad: Annotated[Literal["ML", "G", "UN"], Field(description="Unidad ya convertida (calculado.unidad).")],
) -> dict:
    """Busca en el catálogo productos de la misma marca, contenido y unidad.

    Usala SOLO con productos que NO traen GTIN (calculado.gtin es null), para detectar un posible duplicado.
    Devuelve candidatos: NO son duplicados automáticamente. Comparalos con el producto del proveedor
    según el estándar (marca, tipo, variante, contenido, concentración y unidades por envase):
    - si todo coincide -> a_revision con motivo posible_duplicado y el sku en duplicado_de;
    - si difieren en un solo atributo (por ejemplo, la variante) -> son productos distintos.
    El catálogo viejo tiene descripciones abreviadas y la variante metida en la descripción:
    por eso cada candidato trae también descripcion_expandida.
    """
    candidatos = CATALOGO_POR_PARECIDO.get(clave_parecido(marca, contenido, unidad), [])
    return {
        "buscado": {"marca": marca.strip().upper(), "contenido": contenido, "unidad": unidad},
        "cantidad": len(candidatos),
        "candidatos": [
            {
                "sku": p["sku"],
                "descripcion": p["descripcion"],
                "descripcion_expandida": expandir_abreviaturas(p["descripcion"], ABREVIATURAS),
                "tipo": p["tipo"],
                "variante": p["variante"],
                "concentracion": p["concentracion"],
                "unidades_por_envase": p["unidades_por_envase"],
                "fuente": p["fuente"],
            }
            for p in candidatos
        ],
    }


# --- registrar_ficha: la ÚNICA tool que escribe ---
# Para validar: todos los item_id que existen en los archivos de los proveedores habilitados, y todos los SKU.
ITEMS_VALIDOS = {
    fila["item_id"]
    for proveedor_id, config in PROVEEDORES.items()
    for fila in leer_filas(proveedor_id, config)
}
SKUS_CATALOGO = {producto["sku"] for producto in CATALOGO}

Estado = Literal[tuple(VOCABULARIO["estados"])]            # lista_para_alta | duplicado | a_revision
Motivo = Literal[tuple(VOCABULARIO["motivos_revision"])]   # gtin_faltante | gtin_invalido | ...


class CategoriaDecididaPor(BaseModel):
    """El extra de la semana 1: qué dato de la ficha decidió la categoría (le ahorra a Compras revisar a ciegas)."""
    campo: Literal["tipo", "variante", "marca"] = Field(description="El campo de la ficha que decidió la categoría.")
    valor: str = Field(description="El valor de ese campo, tal como quedó en la ficha.")
    explicacion: str = Field(max_length=200, description="Una frase corta: por qué ese dato lleva a esa categoría.")


def validar_coherencia(item_id: str, estado: str, motivos: list[str], duplicado_de: str | None) -> list[str]:
    """Revisa que el resultado tenga sentido según el estándar. Devuelve la lista de problemas (vacía = OK)."""
    problemas = []

    if item_id not in ITEMS_VALIDOS:
        problemas.append(f"item_id {item_id!r} no existe en los archivos de los proveedores.")
    if len(motivos) != len(set(motivos)):
        problemas.append("motivos_revision tiene motivos repetidos.")
    if duplicado_de is not None and duplicado_de not in SKUS_CATALOGO:
        problemas.append(f"duplicado_de {duplicado_de!r} no es un SKU del catálogo.")

    if estado == "lista_para_alta":
        if motivos:
            problemas.append("Un ítem lista_para_alta no lleva motivos_revision.")
        if duplicado_de is not None:
            problemas.append("Un ítem lista_para_alta no lleva duplicado_de.")
    elif estado == "duplicado":
        if duplicado_de is None:
            problemas.append("Un ítem duplicado tiene que informar el SKU en duplicado_de.")
        if motivos:
            problemas.append("Un ítem duplicado no lleva motivos_revision.")
    elif estado == "a_revision":
        if not motivos:
            problemas.append("Un ítem a_revision tiene que tener al menos un motivo.")
        if "posible_duplicado" in motivos and duplicado_de is None:
            problemas.append("Con motivo posible_duplicado hay que informar el SKU candidato en duplicado_de.")
        if "posible_duplicado" not in motivos and duplicado_de is not None:
            problemas.append("duplicado_de solo se informa en un a_revision con motivo posible_duplicado.")

    return problemas


def guardar_resultado(resultado: dict) -> int:
    """Guarda (o reemplaza) el resultado de un ítem en resultados.json. Devuelve cuántos hay guardados."""
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    resultados = {}
    if RUTA_RESULTADOS.exists():
        resultados = json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))

    resultados[resultado["item_id"]] = resultado  # si el ítem ya estaba, se reemplaza

    # Escribimos primero a un archivo temporal y después lo renombramos:
    # si el programa se corta a la mitad, resultados.json nunca queda roto.
    temporal = RUTA_RESULTADOS.with_suffix(".tmp")
    temporal.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(RUTA_RESULTADOS)
    return len(resultados)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
def registrar_ficha(
    item_id: Annotated[str, Field(description="Identificador del ítem, tal como vino en la fila (ej. P03:LT-3303).")],
    estado: Annotated[Estado, Field(description="Estado del ítem según el estándar.")],
    ficha: Annotated[dict[str, Any], Field(description="Los campos de la ficha (estándar, sección 1). Un campo que no se pudo determinar va en null.")],
    fuentes: Annotated[dict[str, dict], Field(description="Para cada campo completado de la ficha, de dónde salió: la fuente de su fila ({archivo, linea} o {archivo, pagina}).")],
    categoria_decidida_por: Annotated[CategoriaDecididaPor, Field(description="Qué dato de la ficha decidió la categoría elegida.")],
    motivos_revision: Annotated[list[Motivo], Field(default_factory=list, description="Motivos de revisión. Vacío si no va a revisión.")],
    duplicado_de: Annotated[str | None, Field(description="SKU del catálogo: si es duplicado, o el candidato si es posible_duplicado.")] = None,
) -> dict:
    """Registra el resultado de un ítem. Es la ÚNICA forma de guardar una ficha.

    Llamala una vez por ítem, cuando ya decidiste su estado y armaste su ficha.
    Antes de guardar, el código revisa que el resultado sea coherente con el estándar
    (por ejemplo, que un duplicado traiga su SKU). Si no lo es, NO se guarda y vuelve un error
    que explica qué corregir: corregilo y volvé a llamarla. Si registrás el mismo ítem dos veces,
    el último reemplaza al anterior.
    En categoria_decidida_por indicá qué campo de la ficha (tipo, variante o marca) decidió la
    categoría, con su valor exacto y una frase corta de por qué.
    """
    problemas = validar_coherencia(item_id, estado, motivos_revision, duplicado_de)
    if ficha.get(categoria_decidida_por.campo) != categoria_decidida_por.valor:
        problemas.append(f"categoria_decidida_por cita {categoria_decidida_por.campo}={categoria_decidida_por.valor!r}, "
                        f"pero en la ficha ese campo vale {ficha.get(categoria_decidida_por.campo)!r}. "
                        "Tiene que citar un dato real de la ficha.")
    if problemas:
        raise ToolError("No se guardó. Corregí esto y volvé a registrar: " + " | ".join(problemas))

    total = guardar_resultado({
        "item_id": item_id,
        "estado": estado,
        "duplicado_de": duplicado_de,
        "motivos_revision": motivos_revision,
        "ficha": ficha,
        "fuentes": fuentes,
        "categoria_decidida_por": categoria_decidida_por.model_dump(),
    })
    return {"registrado": item_id, "estado": estado, "total_registrados": total}


# --- Resources: el estándar, para que el agente lo ponga en su system prompt ---
CARPETA_ESTANDAR = CARPETA_DATA / "estandar"


@mcp.resource("estandar://ficha_de_producto", mime_type="text/markdown")
def recurso_ficha_de_producto() -> str:
    """Estándar de ficha de producto: campos, normalización, precio, estados y motivos de revisión."""
    return (CARPETA_ESTANDAR / "ficha_de_producto.md").read_text(encoding="utf-8-sig")


@mcp.resource("estandar://vocabulario", mime_type="text/yaml")
def recurso_vocabulario() -> str:
    """Listas cerradas: tipos por familia, unidades, monedas, estados, motivos y abreviaturas."""
    return (CARPETA_ESTANDAR / "vocabulario.yaml").read_text(encoding="utf-8-sig")


@mcp.resource("estandar://taxonomia", mime_type="text/csv")
def recurso_taxonomia() -> str:
    """Las 50 categorías: código, sus tres niveles y una nota de qué entra en cada una."""
    return (CARPETA_ESTANDAR / "taxonomia.csv").read_text(encoding="utf-8-sig")


if __name__ == "__main__":
    mcp.run(show_banner=False)