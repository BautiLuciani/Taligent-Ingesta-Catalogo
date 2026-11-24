"""Para revisar (semana 7, paso 3): los productos que Ceibo no pudo resolver solo, con la evidencia para decidir.

Funciones puras sobre lo que ya dejó el sistema: resultados.json (la ficha y sus motivos), el consolidado de cada
proveedor (lo que vieron los fichadores: las dos versiones de un conflicto, el código de barras que mandó el
proveedor), el catálogo actual y el pedido al proveedor. No cambia ninguna ficha.

Las decisiones que toma la persona ("es el mismo", "preguntarle al proveedor"...) se guardan aparte, en
salida/decisiones.json: la ficha no se toca (un solo escritor). Quedan anotadas para el alta.
"""
import csv
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from cuentas import calcular_digito_verificador, cargar_abreviaturas, convertir_contenido, convertir_numero, expandir_abreviaturas
from pedido_proveedor import pendientes_del_item

CARPETA_PROYECTO = Path(__file__).parent
RUTA_CATALOGO = CARPETA_PROYECTO / "Data" / "catalogo" / "catalogo_actual.csv"

# Los grupos, en el orden en que se muestran. Un producto va a UN grupo: el de su motivo más importante.
GRUPOS = [
    ("posible_duplicado", "Podría ser uno que ya tenemos", "Vino sin código de barras y se parece a un producto del catálogo"),
    ("faltan_datos", "Faltan datos del proveedor", "Sin código de barras, sin precio o sin principio activo"),
    ("conflicto_entre_fuentes", "Los dos archivos no coinciden", "Dos archivos del proveedor dicen cosas distintas"),
    ("gtin_invalido", "El código de barras está mal", "El código que mandó no es válido"),
]

CON_ARTICULO = {"código de barras": "el código de barras", "precio de costo": "el precio de costo", "moneda": "la moneda",
                "principio activo": "el principio activo", "marca": "la marca", "tipo": "el tipo", "contenido": "el contenido",
                "unidad": "la unidad", "unidades por envase": "las unidades por envase", "concentración": "la concentración",
                "condición de venta": "la condición de venta"}
NOMBRE_DEL_CAMPO = {"contenido": "contenido", "precio_costo": "precio", "descripcion": "nombre", "gtin": "código de barras"}


def sin_acentos(texto) -> str:
    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in normalizado if not unicodedata.combining(c)).upper().strip()


def nombre_corto(nombre: str) -> str:
    """"Distribuidora Litoral S.R.L." -> "Distribuidora Litoral" (para los botones y las frases)."""
    return re.sub(r"\s+(S\.?A\.?|S\.?R\.?L\.?)$", "", nombre.strip())


def grupo_de(resultado: dict) -> str:
    motivos = resultado.get("motivos_revision") or []
    if "posible_duplicado" in motivos:
        return "posible_duplicado"
    if "conflicto_entre_fuentes" in motivos:
        return "conflicto_entre_fuentes"
    if "gtin_invalido" in motivos:
        return "gtin_invalido"
    return "faltan_datos"


def leer_catalogo(ruta: Path = RUTA_CATALOGO) -> dict[str, dict]:
    """SKU -> producto del catálogo actual, con su línea en el archivo (como lo carga el servidor)."""
    productos = {}
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        for fila in lector:
            fila["fuente"] = {"archivo": ruta.name, "linea": lector.line_num}
            productos[fila["sku"]] = fila
    return productos


def leer_consolidados(carpeta: Path) -> dict[str, dict]:
    """item_id -> la fila consolidada que vieron los fichadores (salida/consolidado/Pxx.json)."""
    filas = {}
    for ruta in sorted(carpeta.glob("P*.json")):
        try:
            for fila in json.loads(ruta.read_text(encoding="utf-8")).get("filas", []):
                filas[fila["item_id"]] = fila
        except (json.JSONDecodeError, KeyError):
            continue
    return filas


def leer_decisiones(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


# --- La comparación con el producto del catálogo (posible duplicado) ---

def marca_de_coincidencia(nuevo, viejo, descripcion_vieja: str | None) -> tuple[str, str]:
    """(texto de lo que tenemos, "si" | "nombre" | "no" | "falta") para una fila de la comparación. Solo marca que
    coincide lo que el código puede comprobar: igual escrito (sin acentos), o metido en el nombre del catálogo."""
    if nuevo in (None, ""):
        return (viejo or "Sin dato"), ("si" if viejo in (None, "") else "falta")
    if viejo not in (None, "") and sin_acentos(nuevo) == sin_acentos(viejo):
        return viejo, "si"
    if viejo in (None, "") and descripcion_vieja and sin_acentos(nuevo) in sin_acentos(descripcion_vieja):
        return "Dentro del nombre", "nombre"
    return (viejo or "Sin dato"), "no"


def comparar_con_catalogo(ficha: dict, producto: dict, abreviaturas: dict) -> list[dict]:
    """Las filas de "Lo que mandó el proveedor / Lo que ya tenemos / ¿Coincide?", con lo que el código comprueba:
    la marca, el tipo y la variante escritos igual (o la variante dentro del nombre viejo), el contenido convertido a
    la misma unidad (el catálogo viejo dice GRS o CC) y las unidades por envase."""
    expandida = expandir_abreviaturas(producto["descripcion"], abreviaturas) or producto["descripcion"]
    filas = []
    for etiqueta, campo in (("Marca", "marca"), ("Tipo", "tipo"), ("Variante", "variante")):
        viejo, coincide = marca_de_coincidencia(ficha.get(campo), producto.get(campo) or None, expandida)
        filas.append({"campo": etiqueta, "nuevo": ficha.get(campo) or "Sin dato", "viejo": viejo, "coincide": coincide})
    contenido_viejo, unidad_vieja = convertir_contenido(convertir_numero(producto.get("contenido")), producto.get("unidad"))
    nuevo = f"{ficha.get('contenido')} {ficha.get('unidad')}" if ficha.get("contenido") is not None else None
    viejo = f"{producto.get('contenido')} {producto.get('unidad')}".strip()
    igual = nuevo is not None and (ficha.get("contenido"), ficha.get("unidad")) == (contenido_viejo, unidad_vieja)
    filas.append({"campo": "Contenido", "nuevo": nuevo or "Sin dato", "viejo": viejo or "Sin dato",
                  "coincide": "si" if igual else ("falta" if nuevo is None else "no")})
    if ficha.get("concentracion") or producto.get("concentracion"):
        viejo, coincide = marca_de_coincidencia(ficha.get("concentracion"), producto.get("concentracion") or None, expandida)
        filas.append({"campo": "Concentración", "nuevo": ficha.get("concentracion") or "Sin dato", "viejo": viejo, "coincide": coincide})
    upe_viejo = int(convertir_numero(producto.get("unidades_por_envase")) or 1)
    filas.append({"campo": "Unidades por envase", "nuevo": str(ficha.get("unidades_por_envase") or 1), "viejo": str(upe_viejo),
                  "coincide": "si" if (ficha.get("unidades_por_envase") or 1) == upe_viejo else "no"})
    filas.append({"campo": "Código de barras", "nuevo": ficha.get("gtin") or "No lo mandó", "viejo": producto.get("gtin") or "Sin dato",
                  "coincide": "falta" if not ficha.get("gtin") else ("si" if ficha.get("gtin") == producto.get("gtin") else "no")})
    return filas


# --- Por qué un código de barras no es válido ---

def por_que_no_vale(texto) -> str:
    """El motivo, en palabras y con la cuenta: cuántos dígitos tiene o qué dígito verificador tendría que tener."""
    limpio = str(texto or "").replace("-", "").replace(" ", "").strip()
    if not limpio:
        return "No mandó ningún código."
    if not limpio.isdigit():
        return f"Mandó «{texto}», que tiene caracteres que no son números."
    if len(limpio) == 12:
        limpio = "0" + limpio
    if len(limpio) != 13:
        return f"Mandó «{texto}», que tiene {len(limpio)} dígitos: un código de barras tiene 13."
    esperado = calcular_digito_verificador(limpio[:12])
    return (f"Mandó «{texto}». El último número es un control que sale de la cuenta de los otros 12: "
            f"tendría que ser {esperado} y es {limpio[-1]}. Puede ser un error al copiarlo.")


def codigo_que_mando(fila: dict | None) -> str | None:
    """El código de barras tal cual lo mandó el proveedor (la columna original de la fila consolidada)."""
    original = (fila or {}).get("original") or {}
    for clave, valor in original.items():
        if sin_acentos(clave) in ("EAN", "EAN13", "UPC/EAN", "EAN-13", "GTIN", "CODIGO DE BARRAS") and valor not in (None, ""):
            return str(valor)
    return None


# --- Cada producto para revisar, listo para la pantalla ---

def opciones_del_grupo(grupo: str, corto: str, versiones: list[dict] | None = None) -> list[dict]:
    """Las decisiones que se pueden tomar (clave, texto del botón y qué pasa)."""
    preguntar = {"clave": "preguntar", "titulo": f"Preguntarle a {corto}", "detalle": "Va al pedido del proveedor"}
    if grupo == "posible_duplicado":
        return [{"clave": "es_el_mismo", "titulo": "Es el mismo", "detalle": "No se da de alta"},
                {"clave": "es_otro", "titulo": "Es otro producto", "detalle": "Queda esperando el código"}, preguntar]
    if grupo == "conflicto_entre_fuentes" and versiones and len(versiones) == 2:
        from presentacion import fuente_para_pantalla
        detalles = [fuente_para_pantalla(v["fuente"]) or {} for v in versiones]
        return [{"clave": f"vale_{i + 1}", "titulo": f"Vale {v['valor']}",
                 "detalle": f"Lo que dice el {d.get('tipo', 'archivo')} ({d.get('ubicacion', '')})"}
                for i, (v, d) in enumerate(zip(versiones, detalles))] + [preguntar]
    return [{**preguntar, "titulo": f"Pedírselo a {corto}"},
            {"clave": "no_dar_de_alta", "titulo": "No darlo de alta", "detalle": "Queda afuera de esta lista"}]


def producto_para_revisar(resultado: dict, fila: dict | None, catalogo: dict, proveedores: dict, abreviaturas: dict,
                          decisiones: dict) -> dict:
    from presentacion import fuente_para_pantalla, motivos_en_palabras

    ficha = resultado["ficha"]
    nombre_proveedor = proveedores.get(ficha.get("proveedor_id"), {}).get("nombre", ficha.get("proveedor_id") or "")
    corto = nombre_corto(nombre_proveedor)
    grupo = grupo_de(resultado)
    codigo = ficha.get("codigo_proveedor") or resultado["item_id"].split(":", 1)[1]
    fuentes = resultado.get("fuentes") or {}
    item = {
        "id": resultado["item_id"], "codigo": codigo, "nombre": ficha.get("descripcion") or codigo,
        "proveedor_id": ficha.get("proveedor_id"), "proveedor": nombre_proveedor, "proveedor_corto": corto,
        "grupo": grupo, "motivos": motivos_en_palabras(resultado),
        "fuente": fuente_para_pantalla(fuentes.get("descripcion") or (fila or {}).get("fuente")),
        "comparacion": None, "catalogo": None, "versiones": None, "codigo_de_barras": None,
    }
    calculado = (fila or {}).get("calculado") or {}
    if grupo == "posible_duplicado":
        producto = catalogo.get(resultado.get("duplicado_de"))
        item["pregunta"] = "¿Es el mismo producto que ya tenemos?"
        item["explicacion"] = (f"{corto} no mandó el código de barras, así que Ceibo no lo puede comparar por código. "
                               "Por lo que es, se parece a un producto que ya está en el catálogo.")
        if producto:
            item["comparacion"] = comparar_con_catalogo(ficha, producto, abreviaturas)
            item["catalogo"] = {"sku": producto["sku"], "descripcion": producto["descripcion"],
                                "fuente": fuente_para_pantalla(producto["fuente"])}
    elif grupo == "conflicto_entre_fuentes":
        conflictos = calculado.get("conflictos") or []
        campo = conflictos[0]["campo"] if conflictos else None
        item["pregunta"] = f"¿Cuál es el {NOMBRE_DEL_CAMPO.get(campo, (campo or 'dato').replace('_', ' '))} correcto?"
        item["explicacion"] = (f"Los dos archivos de {corto} dicen cosas distintas. El precio se resuelve solo (vale el "
                               "archivo más nuevo); esto lo decide una persona, por eso la ficha lo deja vacío.")
        item["versiones"] = [{"valor": v["valor"], "fuente": fuente_para_pantalla(v["fuente"])}
                             for c in conflictos for v in c["versiones"]][:2] or None
    elif grupo == "gtin_invalido":
        mando = codigo_que_mando(fila)
        item["pregunta"] = "El código de barras no es válido"
        item["explicacion"] = por_que_no_vale(mando) if mando else "El código que mandó no pasa el control."
        item["codigo_de_barras"] = mando
    else:
        from presentacion import datos_obligatorios_que_faltan
        faltan = [CON_ARTICULO.get(f, f) for f in (["código de barras"] if "gtin_faltante" in (resultado.get("motivos_revision") or []) else [])
                  + datos_obligatorios_que_faltan(ficha)]
        item["pregunta"] = "Faltan datos para darlo de alta"
        item["explicacion"] = (f"{corto} no mandó " + (", ".join(faltan[:-1]) + " ni " + faltan[-1] if len(faltan) > 1 else
                                                     (faltan[0] if faltan else "un dato obligatorio"))
                               + ". Ceibo no lo inventa: sin eso, la ficha no está completa.")
    explicados = {"posible_duplicado": {"posible_duplicado", "gtin_faltante"}, "conflicto_entre_fuentes": {"conflicto_entre_fuentes"},
                  "gtin_invalido": {"gtin_invalido"}, "faltan_datos": {"gtin_faltante", "dato_obligatorio_faltante"}}[grupo]
    item["otros_motivos"] = motivos_en_palabras({**resultado, "motivos_revision": [m for m in resultado.get("motivos_revision") or []
                                                                                    if m not in explicados]})
    pedidos, _ = pendientes_del_item(resultado, fila, catalogo) if fila else ([], [])
    item["pedido"] = pedidos
    crudas = [v for c in (calculado.get("conflictos") or []) for v in c["versiones"]][:2]
    item["opciones"] = opciones_del_grupo(grupo, corto, crudas or None)
    item["decision"] = decisiones.get(resultado["item_id"])
    return item


def productos_para_revisar(resultados: dict, consolidados: dict, catalogo: dict, proveedores: dict, decisiones: dict,
                           carpeta_pedidos: Path) -> dict:
    """Los grupos con sus productos (en el orden de resultados.json) y el pedido de cada proveedor."""
    abreviaturas = cargar_abreviaturas()
    productos = [producto_para_revisar(r, consolidados.get(r["item_id"]), catalogo, proveedores, abreviaturas, decisiones)
                 for r in resultados.values() if r.get("estado") == "a_revision" and r.get("ficha")]
    grupos = [{"clave": clave, "titulo": titulo, "detalle": detalle,
               "productos": [p for p in productos if p["grupo"] == clave]} for clave, titulo, detalle in GRUPOS]
    pedidos = {}
    for proveedor_id in sorted({p["proveedor_id"] for p in productos}):
        ruta = carpeta_pedidos / f"pedido_{proveedor_id}.md"
        if ruta.exists():
            mensaje = ruta.read_text(encoding="utf-8")
            pedidos[proveedor_id] = {"mensaje": mensaje, "productos": len(re.findall(r"^\S+ · ", mensaje, flags=re.M))}
    return {"grupos": [g for g in grupos if g["productos"]], "total": len(productos), "pedidos": pedidos,
            "decididos": sum(1 for p in productos if p["decision"])}


# --- Las decisiones ---

def guardar_decision(ruta: Path, item_id: str, clave: str | None, opciones: list[dict]) -> dict:
    """Anota (o borra, con clave None) la decisión de una persona sobre un producto. Solo vale una de sus opciones."""
    decisiones = leer_decisiones(ruta)
    if clave is None:
        decisiones.pop(item_id, None)
    else:
        opcion = next((o for o in opciones if o["clave"] == clave), None)
        if opcion is None:
            raise ValueError("Esa decisión no es una de las opciones de este producto.")
        decisiones[item_id] = {"clave": clave, "titulo": opcion["titulo"], "detalle": opcion["detalle"],
                               "fecha": f"{datetime.now():%Y-%m-%d %H:%M}"}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(decisiones, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)
    return decisiones.get(item_id)
