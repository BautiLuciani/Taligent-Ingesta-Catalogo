"""Pruebas sin IA de Para revisar (semana 7, paso 3): los grupos, la evidencia de cada producto y las decisiones.

Sobre las fichas CONGELADAS del cierre de la semana 5 (referencias_sem6/), el consolidado congelado (referencias_sem7/)
y los pedidos congelados. Las decisiones se escriben en una carpeta temporal. Los valores esperados salen de los
archivos de los proveedores, del catálogo y del estándar.
"""
import json
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import referencias

import para_revisar as r
import presentacion

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


RESULTADOS = json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8"))
CONSOLIDADOS = r.leer_consolidados(referencias.CARPETA_REFERENCIAS_SEM7 / "consolidado")
CATALOGO = r.leer_catalogo()
PROVEEDORES = presentacion.leer_proveedores()


def datos(decisiones=None):
    return r.productos_para_revisar(RESULTADOS, CONSOLIDADOS, CATALOGO, PROVEEDORES, decisiones or {}, referencias.CARPETA_PEDIDOS_SEM5)


d = datos()
por_id = {p["id"]: p for g in d["grupos"] for p in g["productos"]}

# --- Pedacitos ---
probar("nombre corto sin S.A. ni S.R.L.", (r.nombre_corto("Distribuidora Litoral S.R.L."), r.nombre_corto("Dermalab S.A.")) ==
       ("Distribuidora Litoral", "Dermalab"))
probar("código con el último dígito mal: dice cuál tendría que ser (7793092189062 -> 9)",
       "tendría que ser 9 y es 2" in r.por_que_no_vale("7793092189062"))
probar("código corto: cuántos dígitos tiene", "tiene 10 dígitos" in r.por_que_no_vale("7791234567"))
probar("código con letras", "no son números" in r.por_que_no_vale("77912A4567890"))
probar("12 dígitos (UPC): se completa con un 0 y se revisa el último", "tendría que ser" in r.por_que_no_vale("229962606560"))
probar("coincide: igual escrito", r.marca_de_coincidencia("PUREZA", "Pureza", None) == ("Pureza", "si"))
probar("coincide: sin acentos", r.marca_de_coincidencia("JABÓN", "JABON", None)[1] == "si")
probar("coincide: la variante dentro del nombre del catálogo", r.marca_de_coincidencia("ALOE", None, "TOALLITAS AQUAVIVA ALOE 80UN")
       == ("Dentro del nombre", "nombre"))
probar("no coincide: distinto", r.marca_de_coincidencia("ROSA", "LAVANDA", None)[1] == "no")
probar("falta: el proveedor no lo mandó", r.marca_de_coincidencia(None, "7791117297966", None)[1] == "falta")

# --- Los 24, en sus grupos ---
probar("24 para revisar, ninguno decidido", d["total"] == 24 and d["decididos"] == 0)
probar("4 grupos en orden, con 14 + 6 + 2 + 2",
       [(g["clave"], len(g["productos"])) for g in d["grupos"]] ==
       [("posible_duplicado", 14), ("faltan_datos", 6), ("conflicto_entre_fuentes", 2), ("gtin_invalido", 2)])
probar("cada producto está en un solo grupo", len(por_id) == 24)
probar("los 24 son los a_revision de resultados.json",
       set(por_id) == {i for i, x in RESULTADOS.items() if x["estado"] == "a_revision"})

# LT-3447: el jabón que podría ser SKU100889
p = por_id["P03:LT-3447"]
probar("LT-3447: la pregunta y la explicación", p["pregunta"] == "¿Es el mismo producto que ya tenemos?"
       and p["explicacion"].startswith("Distribuidora Litoral no mandó el código de barras"))
probar("LT-3447: el candidato SKU100889 con su descripción y su línea del catálogo",
       p["catalogo"]["sku"] == "SKU100889" and p["catalogo"]["descripcion"] == "JABON PUREZA ANTIBAC. 90GRS"
       and p["catalogo"]["fuente"]["archivo"] == "catalogo_actual.csv" and p["catalogo"]["fuente"]["ubicacion"].startswith("línea"))
comparacion = {c["campo"]: c for c in p["comparacion"]}
probar("LT-3447: marca y tipo coinciden", comparacion["Marca"]["coincide"] == "si" and comparacion["Tipo"]["coincide"] == "si")
probar("LT-3447: la variante está dentro del nombre viejo (ANTIBAC.)", comparacion["Variante"]["coincide"] == "nombre")
probar("LT-3447: 90 G contra 90 GRS: el código los compara en la misma unidad",
       comparacion["Contenido"]["nuevo"] == "90 G" and comparacion["Contenido"]["viejo"] == "90 GRS" and comparacion["Contenido"]["coincide"] == "si")
probar("LT-3447: el código de barras no lo mandó", comparacion["Código de barras"]["nuevo"] == "No lo mandó"
       and comparacion["Código de barras"]["coincide"] == "falta")
probar("LT-3447: sale del CSV, línea 46", p["fuente"]["archivo"] == "litoral_altas_102026.csv" and p["fuente"]["ubicacion"] == "línea 46")
probar("LT-3447: lo que se le pide a Litoral es lo del pedido real",
       p["pedido"] == ["El código de barras (EAN-13).", '¿Es el mismo producto que ya tenemos cargado como "JABON PUREZA ANTIBAC. 90GRS" (SKU100889)?'])
probar("LT-3447: 3 opciones: es el mismo, es otro, preguntarle a Distribuidora Litoral",
       [o["titulo"] for o in p["opciones"]] == ["Es el mismo", "Es otro producto", "Preguntarle a Distribuidora Litoral"])
probar("en los 14 posibles duplicados, todo lo que el código compara coincide (salvo el código de barras que falta)",
       all(c["coincide"] in ("si", "nombre") for x in d["grupos"][0]["productos"] for c in x["comparacion"] if c["campo"] != "Código de barras"))
probar("DL-151: además del duplicado, avisa que falta el precio", por_id["P05:DL-151"]["otros_motivos"] ==
       ["Falta un dato obligatorio: precio de costo, moneda"])

# Faltan datos
probar("AN-1103: falta el principio activo", por_id["P01:AN-1103"]["explicacion"].startswith("Laboratorio Andes no mandó el principio activo."))
probar("DL-103: sin código, sin precio ni moneda",
       por_id["P05:DL-103"]["explicacion"].startswith("Dermalab no mandó el código de barras, el precio de costo ni la moneda."))
probar("NV-203: sin código de barras", por_id["P09:NV-203"]["explicacion"].startswith("Natural Vida no mandó el código de barras."))
probar("faltan datos: 2 opciones (pedírselo o no darlo de alta)",
       [o["titulo"] for o in por_id["P01:AN-1103"]["opciones"]] == ["Pedírselo a Laboratorio Andes", "No darlo de alta"])

# Los dos archivos no coinciden
p = por_id["P01:AN-1133"]
probar("AN-1133: ¿cuál es el contenido correcto?", p["pregunta"] == "¿Cuál es el contenido correcto?")
probar("AN-1133: 20 G del PDF contra 30 G del Excel, cada uno con su lugar",
       [(v["valor"], v["fuente"]["archivo"], v["fuente"]["ubicacion"]) for v in p["versiones"]] ==
       [("20 G", "Lista_de_precios_octubre_2026.pdf", "pág. 1"), ("30 G", "Actualizacion_precios_Andes.xlsx", "fila 6")])
probar("AN-1133: las opciones son las dos versiones y preguntar",
       [(o["titulo"], o["detalle"]) for o in p["opciones"]] ==
       [("Vale 20 G", "Lo que dice el PDF (pág. 1)"), ("Vale 30 G", "Lo que dice el Excel (fila 6)"),
        ("Preguntarle a Laboratorio Andes", "Va al pedido del proveedor")])

# El código de barras está mal
p = por_id["P02:RIV-1203"]
probar("RIV-1203: el código tal cual lo mandó Rivera", p["codigo_de_barras"] == "7793092189062")
probar("RIV-1203: la cuenta del dígito verificador", "tendría que ser 9 y es 2" in p["explicacion"])
probar("NV-209: el código del mail", por_id["P09:NV-209"]["codigo_de_barras"] == "7795135511939")

# Los pedidos
probar("pedidos: Litoral con sus 3 productos", d["pedidos"]["P03"]["productos"] == 3 and "Distribuidora Litoral" in d["pedidos"]["P03"]["mensaje"])
probar("Norte no tiene pedido (no tiene nada para revisar)", "P08" not in d["pedidos"])

# --- Las decisiones ---
carpeta = Path(tempfile.mkdtemp())
ruta = carpeta / "decisiones.json"
opciones = por_id["P03:LT-3447"]["opciones"]
decision = r.guardar_decision(ruta, "P03:LT-3447", "es_el_mismo", opciones)
probar("guardar: queda anotada con su texto y la fecha", decision["titulo"] == "Es el mismo" and decision["fecha"])
probar("guardar: en salida/decisiones.json", json.loads(ruta.read_text(encoding="utf-8"))["P03:LT-3447"]["clave"] == "es_el_mismo")
r.guardar_decision(ruta, "P03:LT-3447", "preguntar", opciones)
probar("cambiar de idea: queda la última", r.leer_decisiones(ruta)["P03:LT-3447"]["clave"] == "preguntar")
try:
    r.guardar_decision(ruta, "P03:LT-3447", "borrar_el_catalogo", opciones)
    probar("una decisión que no es de sus opciones se rechaza", False)
except ValueError:
    probar("una decisión que no es de sus opciones se rechaza", r.leer_decisiones(ruta)["P03:LT-3447"]["clave"] == "preguntar")
r.guardar_decision(ruta, "P03:LT-3447", None, opciones)
probar("deshacer: se borra", "P03:LT-3447" not in r.leer_decisiones(ruta))
r.guardar_decision(ruta, "P01:AN-1133", "vale_2", por_id["P01:AN-1133"]["opciones"])
probar("con una decisión: 1 de 24 decididos, y el producto la trae", datos(r.leer_decisiones(ruta))["decididos"] == 1)
probar("decidir no toca la ficha (las fichas siguen siendo las mismas)",
       json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8")) == RESULTADOS)
ruta.write_text("{esto no es json", encoding="utf-8")
probar("un decisiones.json roto no rompe la pantalla", r.leer_decisiones(ruta) == {})

# --- El servidor ---
os.environ["INGESTA_CARPETA_SALIDA"] = str(referencias.CARPETA_REFERENCIAS_SEM6)
os.environ["INGESTA_CARPETA_CONSOLIDADO"] = str(referencias.CARPETA_REFERENCIAS_SEM7 / "consolidado")
os.environ["INGESTA_RUTA_DECISIONES"] = str(carpeta / "decisiones_servidor.json")
import uvicorn  # noqa: E402

import servidor_web  # noqa: E402

with socket.socket() as libre:
    libre.bind(("127.0.0.1", 0))
    PUERTO = libre.getsockname()[1]
servidor = uvicorn.Server(uvicorn.Config(servidor_web.app, host="127.0.0.1", port=PUERTO, log_level="error"))
threading.Thread(target=servidor.run, daemon=True).start()
while not servidor.started:
    time.sleep(0.05)


def pedir(direccion, cuerpo=None):
    pedido = urllib.request.Request(f"http://127.0.0.1:{PUERTO}{direccion}", data=cuerpo, method="POST" if cuerpo is not None else "GET",
                                    headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as respuesta:
            texto = respuesta.read().decode("utf-8")
            return respuesta.status, (json.loads(texto) if respuesta.headers.get("content-type", "").startswith("application/json") else texto)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


codigo, datos_api = pedir("/api/revision")
probar("/api/revision: 24 en 4 grupos", codigo == 200 and datos_api["total"] == 24 and len(datos_api["grupos"]) == 4)
codigo, texto = pedir("/revision")
probar("la pantalla carga sus estilos y su programa", codigo == 200 and "/web/revision.css" in texto and "/web/revision.js" in texto)
codigo, respuesta = pedir("/api/decisiones", json.dumps({"item": "P03:LT-3447", "decision": "es_el_mismo"}).encode())
probar("decidir por la web: queda anotado", codigo == 200 and respuesta["decision"]["titulo"] == "Es el mismo")
probar("la decisión se escribió en el archivo de decisiones (no en la referencia congelada)",
       (carpeta / "decisiones_servidor.json").exists() and not (referencias.CARPETA_REFERENCIAS_SEM6 / "decisiones.json").exists())
codigo, datos_api = pedir("/api/revision")
probar("al volver a pedir la lista, el producto trae su decisión", datos_api["decididos"] == 1)
codigo, _ = pedir("/api/decisiones", json.dumps({"item": "P08:IN7003", "decision": "es_el_mismo"}).encode())
probar("decidir sobre un producto que no está para revisar: 404", codigo == 404)
codigo, _ = pedir("/api/decisiones", json.dumps({"item": "P03:LT-3447", "decision": "inventada"}).encode())
probar("una decisión inventada: 400", codigo == 400)
codigo, _ = pedir("/api/decisiones", b"no es json")
probar("un pedido mal armado: 400", codigo == 400)
codigo, respuesta = pedir("/api/decisiones", json.dumps({"item": "P03:LT-3447", "decision": None}).encode())
probar("deshacer por la web", codigo == 200 and respuesta["decision"] is None)
with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/archivos/catalogo_actual.csv", timeout=10) as respuesta:
    probar("el catálogo actual se puede abrir desde su chip (como texto)", respuesta.status == 200
           and respuesta.headers.get("content-type", "").startswith("text/plain"))
servidor.should_exit = True

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
