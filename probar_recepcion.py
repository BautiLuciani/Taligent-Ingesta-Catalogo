"""Pruebas del recepcionista sin IA, con los Excel REALES de los proveedores nuevos. Correr: python probar_recepcion.py"""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import recepcion
from recepcion import (MOTIVO_NO_VA, elegir_ejemplos, forma_del_contenido, pedir_receta, propuesta_de_la_respuesta, proveedor_de_la_ruta,
                       recibir, resumen_del_excel, ruta_de_la_llamada, separador_de_los_datos, tool_receta,
                       verificar_receta)

PROVEEDORES = Path(__file__).parent / "Data" / "proveedores"
RIVERA = PROVEEDORES / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx"
HIGIENE = PROVEEDORES / "P04_Higiene_Total" / "HigieneTotal_novedades.xlsx"
NORTE = PROVEEDORES / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


print("--- 2A · resumen_del_excel: Rivera (encabezado corrido, títulos de sección) ---")
rivera = resumen_del_excel(RIVERA)
hoja = rivera["hojas"][0]
chequear("Una hoja, 'Altas', encabezado en la fila 5", (len(rivera["hojas"]), hoja["hoja"], hoja["fila_encabezado"]),
         (1, "Altas", 5))
chequear("La columna del código la detecta el código, no el modelo", hoja["columna_codigo"], "COD. RIV")
chequear("Columnas de datos (sin la del código)", hoja["columnas"], ["DESCRIPCION", "EAN", "P. COSTO", "OBS"])
chequear("50 productos", hoja["productos"], 50)
chequear("Los textos de arriba (título), con su fila", [t["fila"] for t in hoja["textos_de_arriba"]], [1, 2])
chequear("Los títulos de sección quedan a la vista", [f["texto"] for f in hoja["filas_que_no_son_productos"]],
         ["== CAPILAR ==", "== DESODORANTES =="])
chequear("Ejemplos tal cual: el EAN con guiones no se arregla acá", hoja["ejemplos"][1]["valores"]["EAN"], "779-7137-44403-8")
chequear("OBS vacía en las 3 primeras -> se suma la primera fila que la llena (fila 10)",
         [(e["fila"], e["valores"]["OBS"]) for e in hoja["ejemplos"][3:]], [(10, "PACK PROMO CON NECESER")])

print("--- 2A · Higiene Total (dos hojas iguales por dentro) ---")
higiene = resumen_del_excel(HIGIENE)
chequear("Las dos hojas, en orden", [h["hoja"] for h in higiene["hojas"]], ["Altas", "Discontinuados"])
chequear("Mismas columnas en las dos: solo el NOMBRE de la hoja las distingue",
         higiene["hojas"][0]["columnas"] == higiene["hojas"][1]["columnas"], True)
chequear("28 y 8 productos", [h["productos"] for h in higiene["hojas"]], [28, 8])
chequear("Sin textos de arriba (el encabezado está en la fila 1)", higiene["hojas"][0]["textos_de_arriba"], [])

print("--- 2A · Norte (en inglés) ---")
norte = resumen_del_excel(NORTE)
hoja = norte["hojas"][0]
chequear("Columnas en inglés, tal cual", hoja["columnas"], ["Description", "Size", "UPC/EAN", "Unit cost (USD)", "Origin"])
chequear("El contenido llega como texto ('4.8 fl oz'): la cuenta la hace el código después",
         hoja["ejemplos"][0]["valores"]["Size"], "4.8 fl oz")
chequear("Se puede pasar a JSON (va dentro del mensaje al modelo)", isinstance(json.dumps(norte), str), True)
chequear("Es chico: menos de 3.000 caracteres (el archivo entero no hace falta)", len(json.dumps(norte)) < 3000, True)

print("--- 2A · elegir_ejemplos (casos armados) ---")
filas = [{"original": {"A": n, "B": None}} for n in range(5)] + [{"original": {"A": 9, "B": "algo"}}]
chequear("3 primeras + la primera con B", [f["original"]["A"] for f in elegir_ejemplos(filas)], [0, 1, 2, 9])
chequear("Una columna siempre vacía no suma nada", len(elegir_ejemplos(filas[:5])), 3)
chequear("Hoja sin productos: sin ejemplos", elegir_ejemplos([]), [])

print("--- 2B · tool_receta: los enum salen del archivo ---")
tool = tool_receta(higiene)
propiedades = tool["input_schema"]["properties"]
chequear("Higiene Total: solo puede elegir entre sus 2 hojas", propiedades["hoja_productos_nuevos"]["enum"],
         ["Altas", "Discontinuados"])
chequear("Cada dato: una de sus columnas o null (semana 5: anyOf, como lo acepta strict)",
         propiedades["columna_ean"]["anyOf"], [{"type": "string", "enum": ["Descripcion", "Cont.", "UM", "EAN13", "Costo"]},
                                               {"type": "null"}])
chequear("La columna del código no se ofrece (la resolvió el código)",
         "Item" in propiedades["columna_ean"]["anyOf"][0]["enum"], False)
chequear("Formulario plano: un casillero por dato, al mismo nivel",
         [c for c in propiedades if c.startswith("columna_")],
         ["columna_descripcion", "columna_ean", "columna_precio", "columna_contenido", "columna_unidad"])
chequear("El separador decimal ya no se le pregunta al modelo (lo calcula el código)",
         [c for c in propiedades if "separador" in c], [])
chequear("Dónde está el contenido tampoco (lo deduce el código de columna_contenido)", "contenido_en" in propiedades, False)
chequear("Norte: las columnas en inglés, tal cual",
         tool_receta(norte)["input_schema"]["properties"]["columna_precio"]["anyOf"][0]["enum"],
         ["Description", "Size", "UPC/EAN", "Unit cost (USD)", "Origin"])
chequear("Rivera: una sola hoja para elegir", tool_receta(rivera)["input_schema"]["properties"]["hoja_productos_nuevos"]["enum"],
         ["Altas"])
chequear("Moneda: lista cerrada", propiedades["moneda"]["enum"], ["UYU", "USD"])
chequear("Todo el formulario es obligatorio", len(tool["input_schema"]["required"]), len(propiedades))
print("--- semana 5, paso 3A · el formulario va con strict ---")
chequear("strict: true (la API garantiza la forma y los enum)", tool["strict"], True)
chequear("Paso 3D: el formulario ya no pregunta 'columnas_que_no_van' (las calcula el código)",
         "columnas_que_no_van" in propiedades, False)


def objetos_sin_cerrar(nodo) -> list:
    """Los objetos del schema que admiten claves libres (strict exige additionalProperties: false en todos)."""
    if isinstance(nodo, dict):
        propios = [nodo.get("description", "?")] if nodo.get("type") == "object" and nodo.get("additionalProperties") is not False else []
        return propios + [x for valor in nodo.values() for x in objetos_sin_cerrar(valor)]
    if isinstance(nodo, list):
        return [x for valor in nodo for x in objetos_sin_cerrar(valor)]
    return []


chequear("Todos los objetos sin claves libres (additionalProperties false)", objetos_sin_cerrar(tool["input_schema"]), [])
chequear("Ningún tipo como lista junto con enum (la API lo rechaza: paso 1)",
         [c for c, p in propiedades.items() if isinstance(p.get("type"), list)], [])

print("--- 2B · pedir_receta con un cliente falso (no gasta) ---")


class ClienteFalso:
    """Imita cliente.messages.create: guarda con qué lo llamaron y devuelve una respuesta armada."""
    def __init__(self):
        self.messages = self
        self.pedido = None

    def create(self, **pedido):
        self.pedido = pedido
        return SimpleNamespace(model_dump=lambda: {"content": [{"type": "tool_use", "name": "entregar_receta",
                                                                "input": {"moneda": "USD"}}], "stop_reason": "tool_use"})


falso = ClienteFalso()
respuesta = pedir_receta(falso, "modelo-x", norte)
chequear("La tool va forzada (la respuesta viene sí o sí como formulario)", falso.pedido["tool_choice"],
         {"type": "tool", "name": "entregar_receta"})
chequear("El resumen va como DATO, entre etiquetas <excel>", falso.pedido["messages"][0]["content"].startswith("<excel>"),
         True)
chequear("Usa el modelo que se le pasa (sale del .env)", falso.pedido["model"], "modelo-x")
chequear("Devuelve la respuesta como diccionario", propuesta_de_la_respuesta(respuesta), {"moneda": "USD"})

print("--- 2B · propuesta_de_la_respuesta y la huella ---")
uso = {"type": "tool_use", "name": "entregar_receta", "input": {"a": 1}}
chequear("Sin formulario: None (no se adivina)", propuesta_de_la_respuesta({"content": [{"type": "text", "text": "hola"}]}), None)
chequear("Dos formularios: None (no se elige uno)", propuesta_de_la_respuesta({"content": [uso, uso]}), None)
otro = copy.deepcopy(higiene)
otro["hojas"][0]["productos"] = 29
chequear("Si el archivo cambia, cambia el nombre de la respuesta guardada (no se reusa una ajena)",
         ruta_de_la_llamada(HIGIENE, higiene) == ruta_de_la_llamada(HIGIENE, otro), False)
chequear("Mismo archivo, mismo nombre (se reusa y no se paga dos veces)",
         ruta_de_la_llamada(HIGIENE, higiene) == ruta_de_la_llamada(HIGIENE, resumen_del_excel(HIGIENE)), True)
antes = ruta_de_la_llamada(HIGIENE, higiene)
instruccion = recepcion.INSTRUCCION_RECEPCION
recepcion.INSTRUCCION_RECEPCION = instruccion + " (cambiada)"
chequear("Si cambiamos la instrucción, cambia el nombre (la respuesta vieja queda como evidencia)",
         ruta_de_la_llamada(HIGIENE, higiene) == antes, False)
recepcion.INSTRUCCION_RECEPCION = instruccion

print("--- 2C · verificar_receta: las 3 recetas correctas (armadas a mano, mirando los archivos) ---")
BUENAS = {
    "Rivera": (RIVERA, rivera, {
        "hoja_productos_nuevos": "Altas", "evidencia_hoja": "Planilla de altas - Octubre 2026", "hojas_que_no_entran": [],
        "columna_descripcion": "DESCRIPCION", "columna_ean": "EAN", "columna_precio": "P. COSTO",
        "columna_contenido": "DESCRIPCION", "columna_unidad": None,
        "moneda": "UYU", "evidencia_moneda": None}),
    "Higiene Total": (HIGIENE, higiene, {
        "hoja_productos_nuevos": "Altas", "evidencia_hoja": "Discontinuados",
        "hojas_que_no_entran": [{"hoja": "Discontinuados", "motivo": "productos discontinuados"}],
        "columna_descripcion": "Descripcion", "columna_ean": "EAN13", "columna_precio": "Costo", "columna_contenido": "Cont.", "columna_unidad": "UM",
        "moneda": "UYU", "evidencia_moneda": None}),
    "Norte": (NORTE, norte, {
        "hoja_productos_nuevos": "New items", "evidencia_hoja": "New items", "hojas_que_no_entran": [],
        "columna_descripcion": "Description", "columna_ean": "UPC/EAN", "columna_precio": "Unit cost (USD)", "columna_contenido": "Size", "columna_unidad": None,
        "moneda": "USD", "evidencia_moneda": "Unit cost (USD)"}),
}
for nombre, (ruta, resumen, propuesta) in BUENAS.items():
    v = verificar_receta(resumen, propuesta, ruta)
    chequear(f"{nombre}: todos los controles pasan y hay receta", (v["problemas"], v["receta"] is not None), ([], True))
BEBE = PROVEEDORES / "P06_Bebe_Feliz" / "BebeFeliz_altas.xlsx"  # semana 5, paso 7C: la receta que propuso el modelo
receta_bebe = {"hoja_productos_nuevos": "Altas", "evidencia_hoja": "Altas", "hojas_que_no_entran": [],
               "columna_descripcion": "Producto", "columna_ean": "EAN", "columna_precio": "Precio lista",
               "columna_contenido": "Cantidad", "columna_unidad": "Cantidad", "moneda": "UYU", "evidencia_moneda": None}
v = verificar_receta(resumen_del_excel(BEBE), receta_bebe, BEBE)
chequear("Bebé Feliz: entra y ahora el contenido sale en las 32 filas (antes 20: 'x 50' y '2 x 60 un')",
         (v["problemas"], {c["control"]: c["detalle"] for c in v["controles"]}["El contenido se puede calcular (columna_con_unidad)"]),
         ([], "32 de 32 filas"))
chequear("...y sin filas sin contenido, no hay aviso", v["avisos"], [])
v = verificar_receta(resumen_del_excel(BEBE), {**receta_bebe, "columna_contenido": "Talle / etapa", "columna_unidad": "Talle / etapa"}, BEBE)
chequear("Una columna de contenido mala: no entra (la mayoría no se calcula)", v["receta"], None)
import recepcion as modulo_recepcion  # noqa: E402
original_separar = modulo_recepcion.contenido_de_la_fila
modulo_recepcion.contenido_de_la_fila = lambda f, *a: (None, None) if f.get("Cantidad") == "x 50" else original_separar(f, *a)
v = verificar_receta(resumen_del_excel(BEBE), receta_bebe, BEBE)
modulo_recepcion.contenido_de_la_fila = original_separar
chequear("Si algunas filas no dan contenido, entra igual pero AVISA cuántas y cuáles (antes era en silencio)",
         (v["receta"] is not None, v["avisos"][0].startswith("3 de 32 filas sin contenido calculado (ej. 'x 50')")), (True, True))
chequear("Norte: las que no van las calcula el código (Origin)",
         verificar_receta(norte, BUENAS["Norte"][2], NORTE)["receta"]["decisiones"]["columnas_que_no_van"],
         [{"columna": "Origin", "motivo": MOTIVO_NO_VA}])
receta = verificar_receta(norte, BUENAS["Norte"][2], NORTE)["receta"]
chequear("Norte: la receta tiene la forma de PROVEEDORES (campos, moneda, separador calculado)",
         (receta["formato"], receta["hoja"], receta["campos"]["precio"], receta["moneda"], receta["separador_decimal"]),
         ("excel", "New items", "Unit cost (USD)", "USD", "."))
chequear("Norte: la receta no trae las columnas en null", "unidad" in receta["campos"], False)
controles = {c["control"]: c["detalle"] for c in verificar_receta(rivera, BUENAS["Rivera"][2], RIVERA)["controles"]}
receta_rivera = verificar_receta(rivera, BUENAS["Rivera"][2], RIVERA)["receta"]
chequear("Rivera: la receta no trae 'contenido' como columna propia (lo dice contenido_en)",
         (receta_rivera["contenido_en"], "contenido" in receta_rivera["campos"]), ("dentro_de_la_descripcion", False))
chequear("Rivera: el contenido sale de la descripción en las 50 filas",
         controles["El contenido se puede calcular (dentro_de_la_descripcion)"], "50 de 50 filas")
chequear("Higiene Total: los 5 sin EAN no cuentan (23 con algo, 23 con forma de código)",
         {c["control"]: c["detalle"] for c in verificar_receta(higiene, BUENAS["Higiene Total"][2], HIGIENE)["controles"]}
         ["«EAN13» tiene forma de código de barras"], "23 de 23 filas")

print("--- 2C · forma_del_contenido: la deduce el código ---")
chequear("Contenido = descripción -> dentro de la descripción",
         forma_del_contenido({"descripcion": "D", "contenido": "D", "unidad": None}), "dentro_de_la_descripcion")
chequear("Contenido solo -> columna con unidad", forma_del_contenido({"descripcion": "D", "contenido": "S", "unidad": None}),
         "columna_con_unidad")
chequear("Contenido + unidad -> separadas", forma_del_contenido({"descripcion": "D", "contenido": "C", "unidad": "U"}),
         "cantidad_y_unidad_separadas")
chequear("Nada -> no figura", forma_del_contenido({"descripcion": "D", "contenido": None, "unidad": None}), "no_figura")
chequear("Unidad sin contenido -> no tiene sentido", forma_del_contenido({"descripcion": "D", "contenido": None, "unidad": "U"}),
         None)
chequear("Unidad en la misma columna que el contenido -> columna con unidad",
         forma_del_contenido({"descripcion": "D", "contenido": "S", "unidad": "S"}), "columna_con_unidad")
chequear("Contenido y unidad dentro de la descripción -> dentro de la descripción",
         forma_del_contenido({"descripcion": "D", "contenido": "D", "unidad": "D"}), "dentro_de_la_descripcion")
chequear("Contenido en la descripción y unidad en otra columna -> no tiene sentido",
         forma_del_contenido({"descripcion": "D", "contenido": "D", "unidad": "U"}), None)

print("--- 2C · el separador decimal lo calcula el código, con todas las filas ---")
for nombre, esperado in (("Rivera", (",", "TRAT. CAP. ALBORADA NUTRICION 0,5 KG")), ("Norte", (".", "4.8 fl oz")),
                         ("Higiene Total", (",", None))):
    ruta, resumen, propuesta = BUENAS[nombre]
    r = verificar_receta(resumen, propuesta, ruta)["receta"]
    chequear(f"{nombre}: {esperado[0]!r} por {esperado[1]!r}", (r["separador_decimal"], r["decisiones"]["evidencia_separador"]),
             esperado)
chequear("Rivera: el '0,5 KG' estaba en la fila 28, fuera de los ejemplos (el modelo no lo podía ver)",
         any("0,5" in str(v) for e in rivera["hojas"][0]["ejemplos"] for v in e["valores"].values()), False)
chequear("Las dos formas en el mismo archivo: no se elige", separador_de_los_datos(["4.8 fl oz", "0,5 KG"])[0], None)
chequear("'1.000' es de miles, no un decimal", separador_de_los_datos(["1.000 UN"]), (",", None))
chequear("Sin texto: coma (estándar, sección 4)", separador_de_los_datos([]), (",", None))

print("--- 2C · propuestas malas a propósito: cada una tiene que frenar, con su motivo ---")


def mala(nombre: str, cambios: dict) -> dict:
    """Una copia de la propuesta buena con algo cambiado."""
    ruta, resumen, propuesta = BUENAS[nombre]
    propuesta = copy.deepcopy(propuesta)
    for clave, valor in cambios.items():
        propuesta[clave.replace("columnas.", "columna_")] = valor
    return verificar_receta(resumen, propuesta, ruta)


def frena(origen: str, v: dict, se_espera: str) -> None:
    chequear(origen, (v["receta"], any(se_espera in problema for problema in v["problemas"])), (None, True))


frena("Sin formulario", verificar_receta(norte, None, NORTE), "El modelo entregó el formulario")
incompleta = copy.deepcopy(BUENAS["Norte"][2])
del incompleta["columna_ean"]
frena("Falta un casillero: no entra y no se cae", verificar_receta(norte, incompleta, NORTE), "vino completo")
frena("Una lista mal armada: no entra y no se cae", mala("Norte", {"hojas_que_no_entran": ["Altas"]}), "bien armado")
frena("Higiene Total: eligió Discontinuados", mala("Higiene Total", {
    "hoja_productos_nuevos": "Discontinuados", "hojas_que_no_entran": [{"hoja": "Altas", "motivo": "x"}]}),
    "no se llama como lo que no entra")
frena("Higiene Total: se olvidó de decidir una hoja", mala("Higiene Total", {"hojas_que_no_entran": []}),
      "Cada hoja quedó decidida")
frena("Rivera: el precio como EAN (no tiene forma de código)", mala("Rivera", {"columnas.ean": "P. COSTO"}), "forma de código")
frena("Rivera: la misma columna para dos datos", mala("Rivera", {"columnas.precio": "EAN"}), "dos datos")
v = mala("Higiene Total", {"columnas_que_no_van": [{"columna": "Descripcion", "motivo": "x"}]})
chequear("Semana 5: si una respuesta vieja trae la lista 'no van', no se usa (las calcula el código): entra, sin 'no van'",
         (v["problemas"], v["receta"]["decisiones"]["columnas_que_no_van"]), ([], []))
frena("Rivera: dice que el contenido no figura, pero las 50 descripciones lo traen", mala("Rivera", {"columnas.contenido": None}),
      "no lo traen")
v = mala("Norte", {"columnas.unidad": "Size"})
chequear("Norte con unidad = Size (como en la 4ª corrida): entra, y la receta no repite Size",
         (v["problemas"], v["receta"]["contenido_en"], "unidad" in v["receta"]["campos"]), ([], "columna_con_unidad", False))
v = mala("Rivera", {})
chequear("Semana 5: OBS no se eligió para nada -> el código la anota como 'no va' (ninguna columna desaparece en silencio)",
         v["receta"]["decisiones"]["columnas_que_no_van"], [{"columna": "OBS", "motivo": MOTIVO_NO_VA}])
frena("Rivera: OBS como descripción (no se puede calcular el contenido)", mala("Rivera", {
    "columnas.descripcion": "OBS"}), "contenido")
frena("Higiene Total: 'Cont.' como si trajera la unidad (no la trae)", mala("Higiene Total", {
    "columnas.unidad": None}), "El contenido se puede calcular")
frena("Higiene Total: una unidad sin contenido no tiene sentido", mala("Higiene Total", {
    "columnas.contenido": None}), "tienen sentido juntas")
frena("Norte: UYU aunque la columna dice USD", mala("Norte", {"moneda": "UYU"}), "moneda coincide")
frena("Rivera: USD sin que el archivo lo diga", mala("Rivera", {"moneda": "USD", "evidencia_moneda": "USD"}), "moneda")
frena("Norte: evidencia inventada", mala("Norte", {"evidencia_moneda": "Prices in US dollars"}), "evidencia de la moneda")
v = mala("Rivera", {"columnas.ean": None})
chequear("Sin columna de EAN: no frena, pero avisa (irán a revisión con gtin_faltante)",
         (v["receta"] is not None, "gtin_faltante" in " ".join(v["avisos"])), (True, True))

frena("Rivera: evidencia con dos textos pegados (no existe así en el archivo)",
      mala("Rivera", {"evidencia_hoja": "COSMÉTICA RIVERA S.A. / Planilla de altas - Octubre 2026"}), "evidencia de la hoja")

print("--- 2D · las respuestas REALES de las corridas del 11/11 (congeladas en salida/experimentos/) ---")
EXPERIMENTOS = Path(__file__).parent / "salida" / "experimentos"


def respuesta_real(carpeta: str, prefijo: str) -> dict:
    ruta = next((EXPERIMENTOS / carpeta).glob(f"{prefijo}*.receta_*.json"))
    return propuesta_de_la_respuesta(json.loads(ruta.read_text(encoding="utf-8")))


def al_formulario_de_hoy(vieja: dict) -> dict:
    """Pasa una respuesta de un formulario viejo (columnas anidadas, separador, contenido_en) al de hoy, sin tocar las
    columnas que eligió el modelo:
    así se ve qué hacen los arreglos con lo que REALMENTE contestó el modelo."""
    nueva = {clave: valor for clave, valor in vieja.items()
             if clave not in ("columnas", "separador_decimal", "evidencia_separador", "contenido_en")}
    columnas = vieja["columnas"] if "columnas" in vieja else {c: vieja[f"columna_{c}"] for c in
                                                                ("descripcion", "ean", "precio", "contenido", "unidad")}
    return {**{k: v for k, v in nueva.items() if not k.startswith("columna_")},
            **{f"columna_{campo}": columna for campo, columna in columnas.items()}}


v = verificar_receta(higiene, respuesta_real("recepcion_v2", "HigieneTotal"), HIGIENE)
chequear("Higiene Total v2 (columnas sueltas): no entra, sin caerse, con su motivo",
         (v["receta"], "vino completo" in v["problemas"][0]), (None, True))
v = verificar_receta(rivera, al_formulario_de_hoy(respuesta_real("recepcion_v2", "ALTAS RIVERA")), RIVERA)
chequear("Rivera v2 (la única vez que dejó contenido en null): no entra, las descripciones lo traen",
         (v["receta"], any("no lo traen" in p for p in v["problemas"])), (None, True))
for nombre, prefijo, forma in (("Rivera", "ALTAS RIVERA", "dentro_de_la_descripcion"),
                               ("Higiene Total", "HigieneTotal", "cantidad_y_unidad_separadas"),
                               ("Norte", "NorteImports", "columna_con_unidad")):
    ruta, resumen, _ = BUENAS[nombre]
    for corrida in ("recepcion_v3", "recepcion_v4", "recepcion_v6"):
        v = verificar_receta(resumen, al_formulario_de_hoy(respuesta_real(corrida, prefijo)), ruta)
        chequear(f"{nombre} {corrida[-2:]} (sus columnas tal cual): entra con la forma deducida",
                 (v["problemas"], v["receta"]["contenido_en"] if v["receta"] else None), ([], forma))
v = verificar_receta(higiene, respuesta_real("recepcion_v5", "HigieneTotal"), HIGIENE)
chequear("Higiene Total v5 ('Descripcion' usada y en 'no van'): semana 5, la lista ya no se usa -> entra, sin contradicción",
         (v["problemas"], v["receta"]["decisiones"]["columnas_que_no_van"]), ([], []))
for nombre, prefijo in (("Rivera", "ALTAS RIVERA"), ("Norte", "NorteImports")):
    ruta, resumen, _ = BUENAS[nombre]
    chequear(f"{nombre}: v5 y v6 (dos corridas seguidas) dan la MISMA receta",
             verificar_receta(resumen, respuesta_real("recepcion_v5", prefijo), ruta)["receta"] | {"decisiones": None} ==
             verificar_receta(resumen, respuesta_real("recepcion_v6", prefijo), ruta)["receta"] | {"decisiones": None}, True)
v = verificar_receta(higiene, al_formulario_de_hoy(respuesta_real("recepcion_v1", "HigieneTotal")), HIGIENE)
chequear("Higiene Total v1: con 'Item' aceptado (arreglo A), entra", v["problemas"], [])
v = verificar_receta(rivera, al_formulario_de_hoy(respuesta_real("recepcion_v1", "ALTAS RIVERA")), RIVERA)
chequear("Rivera v1: contenido=DESCRIPCION ya está bien; sigue sin entrar solo por la evidencia con dos textos pegados",
         (v["receta"], v["problemas"]), (None, ["La evidencia de la hoja está en el archivo: evidencia "
                                                "'COSMÉTICA RIVERA S.A. / Planilla de altas - Octubre 2026'"]))

print("--- 2D · recibir de punta a punta, con un cliente falso que contesta la receta buena de Norte ---")


class ClienteConReceta:
    """Imita a la API: contesta con un formulario armado y cuenta cuántas veces lo llamaron."""
    def __init__(self, propuesta):
        self.messages, self.propuesta, self.llamadas = self, propuesta, 0

    def create(self, **pedido):
        self.llamadas += 1
        respuesta = {"content": [{"type": "tool_use", "name": "entregar_receta", "input": self.propuesta}],
                     "stop_reason": "tool_use", "usage": {"input_tokens": 3000, "output_tokens": 400}}
        return SimpleNamespace(model_dump=lambda: respuesta)


carpeta = Path(tempfile.mkdtemp())  # nunca escribe en salida/recepcion/ real
falso = ClienteConReceta(BUENAS["Norte"][2])
resultado = recibir(falso, "modelo-x", NORTE, carpeta=carpeta)
chequear("Entra: hay receta y ningún problema", (resultado["receta"] is not None, resultado["problemas"]), (True, []))
chequear("El costo sale de usage: 3.000 in x 0,10 + 400 out x 0,50 por millón", resultado["costo_usd"], 0.0005)
guardado = json.loads((carpeta / "P08_NorteImports_new_items_Q4.json").read_text(encoding="utf-8"))
chequear("Guarda el resultado entero en <proveedor>_<archivo>.json", guardado["receta"]["moneda"], "USD")
chequear("Paso 7: el resultado dice de qué proveedor es y dónde está el archivo (relativo al proyecto)",
         (guardado["proveedor_id"], guardado["ruta"]),
         ("P08", "Data/proveedores/P08_Importadora_Norte/NorteImports_new_items_Q4.xlsx"))
recibir(falso, "modelo-x", NORTE, carpeta=carpeta)
chequear("La segunda vez reusa la respuesta guardada (no paga de nuevo)", falso.llamadas, 1)
recibir(falso, "modelo-x", NORTE, de_nuevo=True, carpeta=carpeta)
chequear("Con de_nuevo, sí vuelve a llamar", falso.llamadas, 2)
malo = ClienteConReceta({**BUENAS["Norte"][2], "moneda": "UYU"})
resultado = recibir(malo, "modelo-x", NORTE, de_nuevo=True, carpeta=carpeta)
chequear("Una receta mala no entra, y el motivo queda guardado", (resultado["receta"], len(resultado["problemas"]) > 0),
         (None, True))
chequear("Semana 5, paso 7: ya no hay proveedores apartados (Bebé Feliz salió)", recepcion.APARTADOS, set())
recepcion.APARTADOS = {"P06"}  # el mecanismo sigue: se prueba apartando a P06 solo para esta prueba
try:
    recibir(falso, "modelo-x", PROVEEDORES / "P06_Bebe_Feliz" / "BebeFeliz_altas.xlsx", carpeta=carpeta)
    chequear("Un proveedor apartado se frena", "no frenó", "frenó")
except ValueError as error:
    chequear("Un proveedor apartado se frena antes de leer nada, con su motivo", "apartado" in str(error), True)
finally:
    recepcion.APARTADOS = set()
chequear("Con el apartado no se llamó a la API", falso.llamadas, 2)
afuera = carpeta / "una_carpeta_cualquiera" / "lista.xlsx"
afuera.parent.mkdir()
shutil.copyfile(NORTE, afuera)
try:
    recibir(falso, "modelo-x", afuera, carpeta=carpeta)
    chequear("Un archivo fuera de la carpeta de un proveedor se frena", "no frenó", "frenó")
except ValueError as error:
    chequear("Un archivo fuera de la carpeta de un proveedor se frena (no se adivina de quién es)",
             "no se sabe de qué proveedor es" in str(error), True)
chequear("...sin llamar a la API", falso.llamadas, 2)
shutil.rmtree(carpeta, ignore_errors=True)

print("--- 7A · proveedor_de_la_ruta: de quién es un archivo, por la carpeta donde está ---")
chequear("En Data/proveedores/P08_Importadora_Norte/ -> P08", proveedor_de_la_ruta(NORTE), "P08")
chequear("En la bandeja entrada/P02_Cosmetica_Rivera/ (con otro nombre de archivo) -> P02",
         proveedor_de_la_ruta(Path("entrada") / "P02_Cosmetica_Rivera" / "ALTAS RIVERA NOV.xlsx"), "P02")
chequear("En una carpeta que no es de ningún proveedor -> None", proveedor_de_la_ruta(Path("entrada") / "Varios" / "x.xlsx"), None)
chequear("Bebé Feliz se reconoce por su carpeta",
         proveedor_de_la_ruta(PROVEEDORES / "P06_Bebe_Feliz" / "BebeFeliz_altas.xlsx"), "P06")

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
