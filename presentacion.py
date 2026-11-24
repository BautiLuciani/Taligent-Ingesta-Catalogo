"""Cómo se muestra una ficha en la interfaz (semana 7): funciones puras, sin IA y sin escribir nada.

La ficha NO se modifica: los textos van tal cual el estándar (en mayúsculas) y cada dato con su fuente real. Lo único
que hace este módulo es ponerle palabras a los códigos (un estado, un motivo, un peligro), darle formato al precio y
juntar el contenido con su unidad, para que una persona que no conoce el sistema lo pueda leer.
"""
import csv
import json
import unicodedata
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_DATA = CARPETA_PROYECTO / "Data"

ESTADOS = {"lista_para_alta": "Lista para alta", "duplicado": "Ya estaba en el catálogo", "a_revision": "Para revisar"}

MOTIVOS = {
    "gtin_faltante": "Vino sin código de barras",
    "gtin_invalido": "El código de barras que mandó no es válido",
    "dato_obligatorio_faltante": "Falta un dato obligatorio",
    "conflicto_entre_fuentes": "Los dos archivos dicen cosas distintas",
    "posible_duplicado": "Podría ser uno que ya tenemos",
}

PELIGROS = {"aerosol_inflamable": "Aerosol inflamable", "liquido_inflamable": "Líquido inflamable",
            "corrosivo": "Corrosivo", "no_peligroso": "No peligroso", "pendiente_fds": "Falta la ficha de seguridad"}

CONDICIONES = {"VENTA_LIBRE": "Venta libre", "BAJO_RECETA": "Bajo receta"}

# El tipo de archivo de una fuente, por su extensión: (etiqueta, color del texto, color de fondo). Del mockup.
TIPOS_DE_ARCHIVO = {"pdf": ("PDF", "#8E1F22", "#FBE9EC"), "xlsx": ("Excel", "#155C3D", "#E8F3EC"),
                    "csv": ("CSV", "#2D4675", "#E8EEF8"), "txt": ("Mail", "#5B3F86", "#F0EBF8")}

# Los obligatorios del estándar (sección 1) que, si faltan, se nombran en "Falta un dato obligatorio: ...".
# El código de barras y la categoría tienen su propio motivo o son consecuencia de otro dato.
OBLIGATORIOS = [("marca", "marca"), ("tipo", "tipo"), ("contenido", "contenido"), ("unidad", "unidad"),
                ("unidades_por_envase", "unidades por envase"), ("precio_costo", "precio de costo"), ("moneda", "moneda")]
DE_MEDICAMENTO = [("principio_activo", "principio activo"), ("concentracion", "concentración"),
                  ("condicion_venta", "condición de venta")]

SIN_DATO = "Sin dato"
NO_CORRESPONDE = "No corresponde: no es un medicamento"


# Semana 7, paso 6: lo que dice un error de Anthropic (o del .env), en palabras y con el paso para arreglarlo.
# Se busca en el texto del error o en lo que imprimió un proceso: el orden importa (el primero que aparece gana).
CAUSAS_CONOCIDAS = [
    (("AuthenticationError", "invalid x-api-key", "authentication_error"),
     "La key de Anthropic no es válida. Revisala con python verificar_entorno.py."),
    (("falta ANTHROPIC_API_KEY", "falta MODELO", "Windows tiene otra ANTHROPIC_API_KEY"),
     "Falta configurar el .env (la key o el modelo). Revisalo con python verificar_entorno.py."),
    (("credit balance is too low",), "La cuenta de Anthropic se quedó sin crédito. Cargá crédito y probá de nuevo."),
    (("APIConnectionError", "APITimeoutError", "ConnectError", "Connection error"),
     "No hay conexión con Anthropic. Revisá internet y probá de nuevo."),
    (("RateLimitError", "rate_limit_error"),
     "Anthropic pidió esperar un momento (límite de uso). Probá de nuevo en unos minutos."),
    (("OverloadedError", "overloaded_error"), "Anthropic está saturado en este momento. Probá de nuevo en unos minutos."),
]


def causa_conocida(texto: str | None) -> str | None:
    """La causa en palabras si el texto tiene un error conocido de Anthropic o del .env; si no, None (no se adivina)."""
    texto = texto or ""
    for marcas, causa in CAUSAS_CONOCIDAS:
        if any(marca in texto for marca in marcas):
            return causa
    return None


def sin_acentos(texto: str) -> str:
    """Para buscar sin que importen mayúsculas ni acentos (igual que consultas.py)."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c)).upper()


# --- Lo que hace falta leer una vez: proveedores, taxonomía y catálogo ---

def leer_proveedores(ruta: Path = CARPETA_DATA / "proveedores" / "proveedores.csv") -> dict[str, dict]:
    """proveedor_id -> {"nombre", "carpeta"}, tal cual proveedores.csv."""
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return {fila["proveedor_id"]: {"nombre": fila["nombre"], "carpeta": fila["carpeta"]}
                for fila in csv.DictReader(archivo)}


def leer_taxonomia(ruta: Path = CARPETA_DATA / "estandar" / "taxonomia.csv") -> dict[str, str]:
    """código -> "Nivel 1, Nivel 2, Nivel 3"."""
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return {fila["codigo"]: f"{fila['nivel_1']}, {fila['nivel_2']}, {fila['nivel_3']}"
                for fila in csv.DictReader(archivo)}


def leer_catalogo(ruta: Path = CARPETA_DATA / "catalogo" / "catalogo_actual.csv") -> dict[str, str]:
    """SKU -> descripción tal como está escrita en el catálogo actual."""
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return {fila["sku"]: fila["descripcion"] for fila in csv.DictReader(archivo)}


# --- Formatos ---

def formato_precio(precio, moneda) -> str | None:
    """88.04, "UYU" -> "UYU 88,04"; 1101.14 -> "UYU 1.101,14". Sin precio: None."""
    if precio is None:
        return None
    numero = f"{precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{moneda} {numero}" if moneda else numero


def formato_contenido(ficha: dict) -> str | None:
    """2000, "ML", 1 -> "2000 ML"; 60, "UN", 2 -> "60 UN, pack de 2". Sin contenido: None."""
    if ficha.get("contenido") is None:
        return None
    texto = f"{ficha['contenido']} {ficha.get('unidad') or ''}".strip()
    if (ficha.get("unidades_por_envase") or 1) > 1:
        texto += f", pack de {ficha['unidades_por_envase']}"
    return texto


def ubicacion(fuente: dict) -> str:
    """Dónde está el dato dentro del archivo, como lo dice la fuente: "pág. 1", "línea 46" o "fila 8"."""
    if "pagina" in fuente:
        return f"pág. {fuente['pagina']}"
    if "linea" in fuente:
        return f"línea {fuente['linea']}"
    if "fila" in fuente:
        return f"fila {fuente['fila']}"
    return ""


def fuente_para_pantalla(fuente: dict | None) -> dict | None:
    """La fuente de un dato lista para el chip: tipo de archivo, nombre real, ubicación y la descripción completa."""
    if not fuente or not fuente.get("archivo"):
        return None
    extension = fuente["archivo"].rsplit(".", 1)[-1].lower()
    tipo, color, fondo = TIPOS_DE_ARCHIVO.get(extension, (extension.upper(), "#3F4B46", "#F1F3F2"))
    detalle = fuente["archivo"] + (f", hoja {fuente['hoja']}" if fuente.get("hoja") else "") + f", {ubicacion(fuente)}"
    return {"archivo": fuente["archivo"], "tipo": tipo, "color": color, "fondo": fondo,
            "ubicacion": ubicacion(fuente), "detalle": detalle, "pagina": fuente.get("pagina")}


# --- La ficha ---

def es_medicamento(ficha: dict) -> bool:
    """Un medicamento: es de la categoría Medicamentos o trae condición de venta (solo las listas de medicamentos la
    traen). Un suplemento no lo es, aunque declare principio activo (estándar, sección 1)."""
    return (ficha.get("categoria") or "").startswith("MED") or ficha.get("condicion_venta") is not None


def lleva_datos_de_medicamento(ficha: dict) -> bool:
    """Si en pantalla van las filas de principio activo, concentración y condición de venta."""
    return es_medicamento(ficha) or any(ficha.get(campo) for campo, _ in DE_MEDICAMENTO)


def datos_obligatorios_que_faltan(ficha: dict) -> list[str]:
    """Los obligatorios en null, en palabras (los de medicamento, solo si es un medicamento)."""
    campos = OBLIGATORIOS + (DE_MEDICAMENTO if es_medicamento(ficha) else [])
    return [texto for campo, texto in campos if ficha.get(campo) is None]


def motivos_en_palabras(resultado: dict) -> list[str]:
    """Los motivos de revisión en palabras, en el orden en que los dejó el sistema."""
    textos = []
    for motivo in resultado.get("motivos_revision") or []:
        texto = MOTIVOS.get(motivo, motivo)
        if motivo == "dato_obligatorio_faltante":
            faltan = datos_obligatorios_que_faltan(resultado["ficha"])
            if faltan:
                texto += ": " + ", ".join(faltan)
        textos.append(texto)
    return textos


def campo(etiqueta: str, valor, fuente: dict | None) -> dict:
    vacio = valor is None or valor == ""
    return {"etiqueta": etiqueta, "valor": SIN_DATO if vacio else str(valor), "vacio": vacio,
            "fuente": None if vacio else fuente_para_pantalla(fuente)}


def grupos_de_la_ficha(ficha: dict, fuentes: dict) -> list[dict]:
    """Los datos de la ficha agrupados como en el mockup: el producto, el precio y (si corresponde) el depósito."""
    producto = [
        campo("Descripción", ficha.get("descripcion"), fuentes.get("descripcion")),
        campo("Marca", ficha.get("marca"), fuentes.get("marca")),
        campo("Tipo", ficha.get("tipo"), fuentes.get("tipo")),
        campo("Variante", ficha.get("variante"), fuentes.get("variante")),
        campo("Contenido", formato_contenido(ficha), fuentes.get("contenido")),
        campo("Código de barras", ficha.get("gtin"), fuentes.get("gtin")),
    ]
    if lleva_datos_de_medicamento(ficha):
        producto += [
            campo("Principio activo", ficha.get("principio_activo"), fuentes.get("principio_activo")),
            campo("Concentración", ficha.get("concentracion"), fuentes.get("concentracion")),
            campo("Condición de venta", CONDICIONES.get(ficha.get("condicion_venta"), ficha.get("condicion_venta")),
                  fuentes.get("condicion_venta")),
        ]
        if not es_medicamento(ficha):  # un suplemento: la condición de venta va vacía porque no corresponde (sección 1)
            producto[-1]["valor"] = NO_CORRESPONDE
    grupos = [
        {"titulo": "El producto", "campos": producto},
        {"titulo": "Precio", "campos": [campo("Precio de costo", formato_precio(ficha.get("precio_costo"), ficha.get("moneda")),
                                              fuentes.get("precio_costo"))]},
    ]
    if ficha.get("peligro_deposito"):
        grupos.append({"titulo": "Depósito", "campos": [
            campo("Cómo se guarda", PELIGROS.get(ficha["peligro_deposito"], ficha["peligro_deposito"]),
                  fuentes.get("peligro_deposito")),
            campo("Número ONU", ficha.get("numero_onu"), fuentes.get("numero_onu")),
        ]})
    return grupos


def ficha_para_pantalla(resultado: dict, proveedores: dict, taxonomia: dict, catalogo: dict) -> dict:
    """Un resultado de resultados.json, listo para la pantalla de Fichas."""
    ficha, fuentes = resultado["ficha"], resultado.get("fuentes") or {}
    proveedor = proveedores.get(ficha.get("proveedor_id"), {})
    codigo = ficha.get("codigo_proveedor") or resultado["item_id"].split(":", 1)[-1]
    nombre = ficha.get("descripcion") or codigo
    sku = resultado.get("duplicado_de")
    decidida = resultado.get("categoria_decidida_por") or {}
    principal = fuentes.get("descripcion") or next(iter(fuentes.values()), None)
    return {
        "id": resultado["item_id"],
        "estado": resultado["estado"],
        "estado_texto": ESTADOS.get(resultado["estado"], resultado["estado"]),
        "nombre": nombre,
        "codigo": codigo,
        "proveedor_id": ficha.get("proveedor_id"),
        "proveedor": proveedor.get("nombre", ficha.get("proveedor_id") or ""),
        "precio": formato_precio(ficha.get("precio_costo"), ficha.get("moneda")) or "sin precio",
        "categoria": taxonomia.get(ficha.get("categoria")) or "Sin categoría",
        "porque": decidida.get("explicacion") or "",
        "motivos": motivos_en_palabras(resultado),
        "sku": sku,
        "sku_descripcion": catalogo.get(sku) if sku else None,
        "grupos": grupos_de_la_ficha(ficha, fuentes),
        "archivo_principal": fuente_para_pantalla(principal),
        "busqueda": sin_acentos(" ".join(str(x) for x in (nombre, ficha.get("marca"), codigo, ficha.get("gtin"),
                                                           proveedor.get("nombre")) if x)),
    }


def fichas_para_pantalla(resultados: dict, proveedores: dict | None = None, taxonomia: dict | None = None,
                         catalogo: dict | None = None) -> list[dict]:
    """Todas las fichas, en el orden de resultados.json (agrupadas por proveedor)."""
    proveedores = proveedores if proveedores is not None else leer_proveedores()
    taxonomia = taxonomia if taxonomia is not None else leer_taxonomia()
    catalogo = catalogo if catalogo is not None else leer_catalogo()
    return [ficha_para_pantalla(r, proveedores, taxonomia, catalogo) for r in resultados.values() if r.get("ficha")]


def proveedores_con_cantidad(fichas: list[dict]) -> list[dict]:
    """Los proveedores que tienen fichas, en orden de código, con cuántas tiene cada uno (para el desplegable)."""
    cantidades: dict[str, dict] = {}
    for ficha in fichas:
        datos = cantidades.setdefault(ficha["proveedor_id"], {"id": ficha["proveedor_id"], "nombre": ficha["proveedor"],
                                                                "cantidad": 0})
        datos["cantidad"] += 1
    return [cantidades[clave] for clave in sorted(cantidades)]


# --- El Excel que se descarga ---

COLUMNAS_EXCEL = [
    ("Estado", lambda r, f: ESTADOS.get(r["estado"], r["estado"])),
    ("Motivos de revisión", lambda r, f: "; ".join(motivos_en_palabras(r))),
    ("Duplicado de (SKU)", lambda r, f: r.get("duplicado_de")),
    ("Proveedor", lambda r, f: f.get("proveedor_id")),
    ("Código del proveedor", lambda r, f: f.get("codigo_proveedor")),
    ("Código de barras", lambda r, f: f.get("gtin")),
    ("Descripción", lambda r, f: f.get("descripcion")),
    ("Marca", lambda r, f: f.get("marca")),
    ("Tipo", lambda r, f: f.get("tipo")),
    ("Variante", lambda r, f: f.get("variante")),
    ("Contenido", lambda r, f: f.get("contenido")),
    ("Unidad", lambda r, f: f.get("unidad")),
    ("Unidades por envase", lambda r, f: f.get("unidades_por_envase")),
    ("Principio activo", lambda r, f: f.get("principio_activo")),
    ("Concentración", lambda r, f: f.get("concentracion")),
    ("Condición de venta", lambda r, f: f.get("condicion_venta")),
    ("Categoría", lambda r, f: f.get("categoria")),
    ("Precio de costo", lambda r, f: f.get("precio_costo")),
    ("Moneda", lambda r, f: f.get("moneda")),
    ("Peligro en depósito", lambda r, f: f.get("peligro_deposito")),
    ("Número ONU", lambda r, f: f.get("numero_onu")),
]


def armar_excel(resultados: dict, ids: list[str], proveedores: dict | None = None, taxonomia: dict | None = None):
    """Un libro de Excel con las fichas pedidas (en ese orden): hoja Fichas (los 18 campos, tal cual, más el estado)
    y hoja Fuentes (de qué archivo y lugar sale cada dato). Devuelve el openpyxl.Workbook, sin guardarlo."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    proveedores = proveedores if proveedores is not None else leer_proveedores()
    taxonomia = taxonomia if taxonomia is not None else leer_taxonomia()
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Fichas"
    titulos = [titulo for titulo, _ in COLUMNAS_EXCEL] + ["Nombre del proveedor", "Categoría (nombre)"]
    hoja.append(titulos)
    hoja_fuentes = libro.create_sheet("Fuentes")
    hoja_fuentes.append(["Proveedor", "Código del proveedor", "Campo", "Archivo", "Hoja", "Lugar"])
    for item_id in ids:
        resultado = resultados.get(item_id)
        if not resultado or not resultado.get("ficha"):
            continue
        ficha = resultado["ficha"]
        hoja.append([obtener(resultado, ficha) for _, obtener in COLUMNAS_EXCEL]
                    + [proveedores.get(ficha.get("proveedor_id"), {}).get("nombre"), taxonomia.get(ficha.get("categoria"))])
        for nombre_campo, fuente in (resultado.get("fuentes") or {}).items():
            hoja_fuentes.append([ficha.get("proveedor_id"), ficha.get("codigo_proveedor"), nombre_campo,
                                 fuente.get("archivo"), fuente.get("hoja"), ubicacion(fuente)])
    for libro_hoja in (hoja, hoja_fuentes):
        for celda in libro_hoja[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="17211D")
        libro_hoja.freeze_panes = "A2"
        for columna in libro_hoja.columns:
            ancho = max(len(str(c.value)) if c.value is not None else 0 for c in columna)
            libro_hoja.column_dimensions[columna[0].column_letter].width = min(max(ancho + 2, 10), 60)
    # El código de barras como texto: si no, Excel lo muestra como 7,79E+12 y le saca el 0 del principio
    columna_gtin = titulos.index("Código de barras") + 1
    for fila in hoja.iter_rows(min_row=2, min_col=columna_gtin, max_col=columna_gtin):
        fila[0].number_format = "@"
    return libro


def cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
