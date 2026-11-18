"""Lo que puede consultar el asistente (semana 6, paso 2): funciones puras sobre la SALIDA del sistema, sin IA.

El asistente no lee los archivos de los proveedores ni el razonamiento de los fichadores: consulta lo que el sistema
ya generó (salida/resultados.json, las filas consolidadas del servidor, la recepción de cada Excel y los pedidos).
Si el pipeline no guardó bien de dónde salió un dato, se nota acá (lo dice la guía, semana 6).

Están acá y no dentro del servidor para poder probarlas sin levantarlo (probar_consultas.py); servidor_mcp.py las
registra como tools de solo lectura. Ninguna escribe nada.
"""
import json
import unicodedata
from pathlib import Path

from lector_excel import leer_tabla_excel

# Campos de la ficha que se muestran en una búsqueda (lo justo para elegir; el detalle lo da ver_ficha)
CAMPOS_DE_LA_LISTA = ("descripcion", "precio_costo", "moneda", "peligro_deposito", "numero_onu", "unidades_por_envase")
# Fuentes que se muestran en una búsqueda: la de la fila del producto y las de los campos por los que se suele filtrar
FUENTES_DE_LA_LISTA = ("descripcion", "precio_costo", "peligro_deposito", "unidades_por_envase")
CANTIDAD_MAXIMA = 50


def cargar_resultados(ruta: Path) -> dict:
    """salida/resultados.json: item_id -> resultado. Se lee en cada consulta (si el sistema vuelve a correr, se ve)."""
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def sin_acentos(texto: str) -> str:
    """Para buscar texto sin que importen mayúsculas ni acentos ("pañal" encuentra "PAÑALES", "jabon" a "JABÓN")."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c)).upper()


def clave_fuente(fuente: dict) -> tuple:
    """Una fuente como tupla comparable: {archivo, linea} / {archivo, pagina} / {archivo, hoja, fila}.

    Ignora claves de más y el tipo del número ("12" y 12 son la misma fila): sirve para comparar lo que cita el
    asistente con lo que existe de verdad.
    """
    archivo = fuente.get("archivo")
    if "linea" in fuente:
        return (archivo, "linea", int(fuente["linea"]))
    if "pagina" in fuente:
        return (archivo, "pagina", int(fuente["pagina"]))
    if "fila" in fuente:
        return (archivo, "hoja", fuente.get("hoja"), "fila", int(fuente["fila"]))
    return (archivo,)


# --- Lo que no entró (semana 4: la recepción decide qué hoja de un Excel no entra, por ejemplo Discontinuados) ---

def lo_que_no_entro(proveedores: dict) -> list[dict]:
    """Los productos de las hojas que la recepción decidió que NO entran (estándar §7), con su fuente y el motivo.

    Sale de la receta guardada de cada Excel recibido (decisiones.hojas_que_no_entran) y de leer esa hoja con el mismo
    lector de siempre. Nada se inventa: si la hoja no se puede leer, el problema queda a la vista.
    """
    no_entraron = []
    for proveedor_id, config in sorted(proveedores.items()):
        receta = config.get("receta")
        if not receta or not config.get("archivo"):
            continue
        for hoja in receta.get("decisiones", {}).get("hojas_que_no_entran", []):
            try:
                tabla = leer_tabla_excel(Path(config["archivo"]), hoja["hoja"])
            except Exception as error:  # el archivo se movió o la hoja cambió: se avisa, no se calla
                no_entraron.append({"proveedor_id": proveedor_id, "hoja": hoja["hoja"], "motivo": hoja["motivo"],
                                    "problema": f"No se pudo leer la hoja: {error}"})
                continue
            for fila in tabla["filas"]:
                no_entraron.append({
                    "item_id": f"{proveedor_id}:{fila['codigo']}",
                    "proveedor_id": proveedor_id,
                    "fuente": fila["fuente"],
                    "original": fila["original"],
                    "motivo": hoja["motivo"],
                })
    return no_entraron


# --- ver_ficha ---

def resolver_codigo(codigo: str, item_ids) -> str | None:
    """De lo que escribió el usuario al item_id: "P01:AN-1124", "AN-1124" o "an-1124" dan "P01:AN-1124".

    Los códigos de los proveedores no se repiten entre proveedores (cada uno tiene su prefijo); si alguna vez se
    repitieran, no se elige: devuelve None.
    """
    buscado = (codigo or "").strip().upper()
    if not buscado:
        return None
    if buscado in item_ids:
        return buscado
    coinciden = [item_id for item_id in item_ids if item_id.split(":", 1)[-1].upper() == buscado]
    return coinciden[0] if len(coinciden) == 1 else None


def ver_ficha(codigo: str, resultados: dict, filas_por_item: dict, catalogo_por_sku: dict,
              no_entraron: list[dict]) -> dict:
    """Todo lo que el sistema sabe de un producto: su ficha con la fuente de cada campo y la fila original del archivo.

    - encontrado=True: estado, motivos, duplicado_de (con la descripción del SKU en el catálogo), ficha, fuentes,
      qué dato decidió la categoría, la fila tal como vino (con su fuente), los conflictos entre archivos con sus
      dos versiones y fuentes, y la FDS que lo nombra.
    - encontrado=False y no_entro: el producto existe en un archivo pero no se cargó (por ejemplo, discontinuado).
    - encontrado=False sin más: ese código no está en nada de lo generado.
    """
    item_id = resolver_codigo(codigo, resultados.keys())
    if item_id is None:
        item_id_no_entro = resolver_codigo(codigo, [p["item_id"] for p in no_entraron if "item_id" in p])
        if item_id_no_entro:
            producto = next(p for p in no_entraron if p.get("item_id") == item_id_no_entro)
            return {"encontrado": False, "item_id": item_id_no_entro, "no_entro": producto,
                    "explicacion": "Este producto está en un archivo del proveedor, pero no se cargó: "
                                   + producto["motivo"]}
        return {"encontrado": False, "codigo": codigo,
                "explicacion": "Ningún producto de lo generado tiene ese código."}

    resultado = resultados[item_id]
    respuesta = {
        "encontrado": True,
        "item_id": item_id,
        "estado": resultado["estado"],
        "motivos_revision": resultado["motivos_revision"],
        "duplicado_de": resultado["duplicado_de"],
        "ficha": resultado["ficha"],
        "fuentes": resultado["fuentes"],
        "categoria_decidida_por": resultado.get("categoria_decidida_por"),
    }
    sku = resultado["duplicado_de"]
    if sku and sku in catalogo_por_sku:
        respuesta["producto_del_catalogo"] = {"sku": sku, "descripcion": catalogo_por_sku[sku]["descripcion"],
                                              "gtin": catalogo_por_sku[sku]["gtin"] or None}
    fila = filas_por_item.get(item_id)
    if fila:
        calculado = fila["calculado"]
        respuesta["archivo_original"] = {"fuente": fila["fuente"], "original": fila["original"]}
        if calculado.get("conflictos"):
            respuesta["conflictos"] = calculado["conflictos"]
        if calculado.get("fds"):
            respuesta["fds"] = calculado["fds"]
        if calculado.get("motivo_gtin"):
            respuesta["motivo_gtin"] = calculado["motivo_gtin"]
        if calculado.get("vigencia_precio"):
            respuesta["vigencia_precio"] = calculado["vigencia_precio"]
    return respuesta


# --- buscar_fichas ---

def buscar_fichas(resultados: dict, proveedor_id: str | None = None, estado: str | None = None,
                  motivo: str | None = None, peligro_deposito: str | None = None, moneda: str | None = None,
                  en_pack: bool | None = None, texto: str | None = None, ordenar_por: str | None = None,
                  desde: int = 0, cantidad: int = 25) -> dict:
    """Las fichas que cumplen TODOS los filtros dados (los que van en None no filtran).

    Devuelve el total, el conteo por estado de lo encontrado y una página de ítems (de a 'cantidad', con 'siguiente'
    si hay más). Cada ítem trae lo justo para elegir y la fuente de su fila; el detalle de uno, con ver_ficha.
    """
    encontrados = []
    for item_id, r in resultados.items():
        ficha = r["ficha"]
        if proveedor_id and not item_id.startswith(f"{proveedor_id}:"):
            continue
        if estado and r["estado"] != estado:
            continue
        if motivo and motivo not in r["motivos_revision"]:
            continue
        if peligro_deposito and ficha.get("peligro_deposito") != peligro_deposito:
            continue
        if moneda and ficha.get("moneda") != moneda:
            continue
        if en_pack is not None and ((ficha.get("unidades_por_envase") or 1) > 1) != en_pack:
            continue
        if texto and sin_acentos(texto) not in sin_acentos(ficha.get("descripcion")):
            continue
        encontrados.append(item_id)

    if ordenar_por in ("precio_costo_desc", "precio_costo_asc"):
        # sin precio van al final en los dos órdenes (no son "el más barato")
        con_precio = [i for i in encontrados if resultados[i]["ficha"].get("precio_costo") is not None]
        sin_precio = [i for i in encontrados if resultados[i]["ficha"].get("precio_costo") is None]
        con_precio.sort(key=lambda i: resultados[i]["ficha"]["precio_costo"], reverse=ordenar_por.endswith("desc"))
        encontrados = con_precio + sin_precio

    conteo = {}
    for item_id in encontrados:
        conteo[resultados[item_id]["estado"]] = conteo.get(resultados[item_id]["estado"], 0) + 1
    cantidad = max(1, min(cantidad, CANTIDAD_MAXIMA))
    pagina = encontrados[desde:desde + cantidad]
    return {
        "total": len(encontrados),
        "conteo_por_estado": conteo,
        "desde": desde,
        "siguiente": desde + cantidad if desde + cantidad < len(encontrados) else None,
        "items": [
            {
                "item_id": item_id,
                "estado": resultados[item_id]["estado"],
                "motivos_revision": resultados[item_id]["motivos_revision"],
                "duplicado_de": resultados[item_id]["duplicado_de"],
                **{campo: resultados[item_id]["ficha"].get(campo) for campo in CAMPOS_DE_LA_LISTA},
                "fuentes": {campo: fuente for campo, fuente in resultados[item_id]["fuentes"].items()
                            if campo in FUENTES_DE_LA_LISTA},
            }
            for item_id in pagina
        ],
    }


# --- pedido al proveedor (semana 2, extra) ---

def pedido_del_proveedor(proveedor_id: str, carpeta_pedidos: Path) -> dict:
    """El mensaje que armó pedido_proveedor.py con lo que falta para cerrar las revisiones de ese proveedor."""
    ruta = carpeta_pedidos / f"pedido_{proveedor_id}.md"
    if not ruta.exists():
        return {"proveedor_id": proveedor_id, "hay_pedido": False,
                "explicacion": "No hay pedido armado para este proveedor (no tiene revisiones abiertas que dependan "
                               "de él, o todavía no se corrió pedido_proveedor.py)."}
    return {"proveedor_id": proveedor_id, "hay_pedido": True, "archivo": ruta.name,
            "mensaje": ruta.read_text(encoding="utf-8")}


# --- todas las fuentes que existen (para verificar lo que cita el asistente, paso 3) ---

def fuentes_conocidas(resultados: dict, filas_por_item: dict, no_entraron: list[dict]) -> set[tuple]:
    """Toda fuente que aparece en lo generado: las de cada campo, la fila original, las dos versiones de un
    conflicto, la FDS, la actualización de precio y las filas que no entraron. Lo que el asistente cite tiene que
    estar acá; si no, lo inventó."""
    conocidas = set()
    for r in resultados.values():
        conocidas |= {clave_fuente(f) for f in r.get("fuentes", {}).values()}
    for fila in filas_por_item.values():
        conocidas.add(clave_fuente(fila["fuente"]))
        calculado = fila.get("calculado", {})
        conocidas |= {clave_fuente(f) for f in (calculado.get("fuentes") or {}).values()}
        for conflicto in calculado.get("conflictos") or []:
            conocidas |= {clave_fuente(v["fuente"]) for v in conflicto["versiones"]}
        if calculado.get("fds"):
            conocidas.add(clave_fuente(calculado["fds"]["fuente"]))
        actualizacion = fila.get("original", {}).get("actualizacion")
        if isinstance(actualizacion, dict) and actualizacion.get("fuente"):
            conocidas.add(clave_fuente(actualizacion["fuente"]))
    conocidas |= {clave_fuente(p["fuente"]) for p in no_entraron if "fuente" in p}
    return conocidas
