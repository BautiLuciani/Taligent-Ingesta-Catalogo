"""Pruebas sin IA de Subir una lista (semana 7, paso 2): la corrida con pasos falsos que escriben trazas como los
fichadores de verdad, y el servidor web de punta a punta (subir el archivo, elegir el proveedor, seguir el avance).

Todo en una carpeta temporal: no toca entrada/, salida/ ni resultados.json del proyecto. La recepción y las fichas de
seguridad que devuelven los pasos falsos son las CONGELADAS de Norte (referencias_sem4/).
"""
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import referencias

CARPETA_PROYECTO = Path(__file__).parent
NORTE = CARPETA_PROYECTO / "Data" / "proveedores" / "P08_Importadora_Norte"
EXCEL_NORTE = NORTE / "NorteImports_new_items_Q4.xlsx"
RECEPCION_NORTE = json.loads((referencias.CARPETA_RECEPCION_REFERENCIA / "P08_NorteImports_new_items_Q4.json").read_text(encoding="utf-8"))
FDS_NORTE = json.loads((referencias.CARPETA_REFERENCIAS_SEM4 / "extracciones" / "fds_P08_Importadora_Norte.json").read_text(encoding="utf-8"))
RESULTADOS = json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8"))


class PasosFalsos:
    """Los pasos de la bandeja sin IA. fichar() escribe trazas como los fichadores (2 tandas a la vez, una ficha
    registrada cada `pausa` segundos), deja resultados.json, el consolidado y la medición con su costo."""

    def __init__(self, carpeta_salida: Path, receta_entra=True, codigo_fichar=0, pausa=0.08, rechazos=0, explota_en=None,
                 sin_conexion=False, ruta_log: Path | None = None):
        self.carpeta_salida, self.receta_entra, self.codigo_fichar = carpeta_salida, receta_entra, codigo_fichar
        self.pausa, self.rechazos, self.explota_en = pausa, rechazos, explota_en
        self.sin_conexion, self.ruta_log = sin_conexion, ruta_log
        self.llamadas = []

    def recibir(self, ruta):
        self.llamadas.append("recibir")
        if self.explota_en == "recibir":
            raise RuntimeError("AuthenticationError: invalid x-api-key")
        if not self.receta_entra:
            return {"receta": None, "costo_usd": 0.0004, "problemas": ["La moneda coincide con lo que dice el archivo"]}
        return json.loads(json.dumps(RECEPCION_NORTE))

    def leer_fds(self, carpeta):
        self.llamadas.append("leer_fds")
        return json.loads(json.dumps(FDS_NORTE))

    def fichar(self, proveedor_id):
        self.llamadas.append("fichar")
        if self.sin_conexion:  # como el orquestador real: termina con código 0, pero ninguna tanda armó su ficha
            self.ruta_log.parent.mkdir(parents=True, exist_ok=True)
            self.ruta_log.write_text("P08 desde 0  ✖ APIConnectionError: Connection error.\n", encoding="utf-8")
            return 0
        filas = json.loads((referencias.CARPETA_REFERENCIAS_SEM6 / "resultados.json").read_text(encoding="utf-8"))
        items = [i for i in filas if i.startswith(proveedor_id + ":")]
        carpeta = self.carpeta_salida / "trazas" / f"paralelo_{time.strftime('%Y%m%d_%H%M%S')}_3"
        carpeta.mkdir(parents=True, exist_ok=True)
        tandas = [items[:10], items[10:]]
        trazas = [carpeta / f"{proveedor_id}_desde_{d:03d}.jsonl" for d in (0, 10)]
        for traza, tanda in zip(trazas, tandas):
            with open(traza, "a", encoding="utf-8") as f:
                f.write(json.dumps({"evento": "inicio_tanda", "proveedor_id": proveedor_id, "esperados": tanda}) + "\n")
        for paso in range(max(len(t) for t in tandas)):
            for traza, tanda in zip(trazas, tandas):
                if paso < len(tanda):
                    with open(traza, "a", encoding="utf-8") as f:
                        if paso < self.rechazos:  # un freno del hook: no cuenta como ficha armada
                            f.write(json.dumps({"evento": "tool_result", "tool": "registrar_ficha", "is_error": True,
                                                "content": "Hook: el GTIN no es válido"}) + "\n")
                        f.write(json.dumps({"evento": "tool_result", "tool": "registrar_ficha", "is_error": False,
                                            "content": json.dumps({"registrado": tanda[paso], "estado": "lista_para_alta",
                                                                   "total_registrados": paso + 1})}) + "\n")
                        f.write('{"evento": "respuesta", "vuelta": ')  # una línea a medio escribir: se saltea
                        f.write("1}\n")
            time.sleep(self.pausa)
        for traza in trazas:
            with open(traza, "a", encoding="utf-8") as f:
                f.write(json.dumps({"evento": "fin_tanda"}) + "\n")
        (self.carpeta_salida / "resultados.json").write_text(json.dumps(filas, ensure_ascii=False), encoding="utf-8")
        consolidado = self.carpeta_salida / "consolidado"
        consolidado.mkdir(exist_ok=True)
        shutil.copyfile(referencias.CARPETA_REFERENCIAS_SEM7 / "consolidado" / f"{proveedor_id}.json",
                        consolidado / f"{proveedor_id}.json")
        (self.carpeta_salida / f"medicion_fichas_3_{proveedor_id}.json").write_text(json.dumps({"costo_usd": 0.0214}),
                                                                                   encoding="utf-8")
        return self.codigo_fichar

    def fichas_escritas(self, proveedor_id):
        return (0, 14) if self.sin_conexion else (14, 14)

    def pedir(self, proveedor_id):
        self.llamadas.append("pedir")
        return 0

    def acusar(self, ruta, registro):
        self.llamadas.append("acusar")
        return ruta.parent / "acuse.md"


def proyecto_temporal() -> Path:
    base = Path(tempfile.mkdtemp())
    (base / "salida").mkdir()
    return base


if __name__ == "__main__":
    import subir_lista as s

    fallas = 0

    def probar(nombre, condicion):
        global fallas
        print(("OK   " if condicion else "FALLA") + " " + nombre)
        if not condicion:
            fallas += 1

    s.SEGUNDOS_ENTRE_MIRADAS = 0.03  # en las pruebas se miran las trazas más seguido (las fichas falsas van rápido)
    A_MANO = {"P01", "P03", "P05", "P07", "P09"}  # como servidor_mcp.PROVEEDORES_A_MANO (sin cargarlo: tarda)

    # --- 1. Los proveedores del desplegable ---
    proveedores = s.proveedores_para_subir(A_MANO)
    probar("9 proveedores, con su nombre de proveedores.csv", len(proveedores) == 9 and proveedores[7]["nombre"] == "Importadora Norte S.A.")
    probar("se pueden elegir los 4 que mandan Excel (Rivera, Higiene Total, Bebé Feliz, Norte)",
           [p["id"] for p in proveedores if p["habilitado"]] == ["P02", "P04", "P06", "P08"])
    probar("Andes, apagado con el motivo", proveedores[0]["detalle"] == "PDF y Excel: todavía no se puede subir desde acá")
    probar("qué mandó Norte, en palabras", proveedores[7]["mando"] == "Excel y 2 fichas de seguridad")
    probar("qué mandó Natural Vida", proveedores[8]["mando"] == "Mail")
    probar("qué mandó Litoral", proveedores[2]["mando"] == "Planilla CSV")
    probar("el nombre del archivo de Norte sugiere a Norte", s.sugerir_proveedor("NorteImports_new_items_Q4.xlsx", proveedores) == "P08")
    probar("un archivo desconocido no sugiere nada", s.sugerir_proveedor("lista_nueva.xlsx", proveedores) is None)
    probar("un archivo de un proveedor apagado no se sugiere", s.sugerir_proveedor("litoral_altas_102026.csv", proveedores) is None)

    # --- 2. Palabras ---
    probar("tiempo: 1 min 35 s", s.tiempo_en_palabras(95) == "1 min 35 s")
    probar("tiempo: 42 s", s.tiempo_en_palabras(42.4) == "42 s")
    probar("costo chico con 3 decimales", s.costo_en_palabras(0.0214) == "US$ 0,021")
    probar("costo grande con 2 decimales", s.costo_en_palabras(0.3827) == "US$ 0,38")
    from acuse import ejemplo_de_contenido
    from lector_excel import leer_tabla_excel
    tabla = leer_tabla_excel(EXCEL_NORTE, "New items")
    linea = s.linea_de_recepcion(RECEPCION_NORTE, tabla, ejemplo_de_contenido(tabla["filas"], RECEPCION_NORTE["receta"]))
    probar("recepción de Norte: 14 productos, dólares y la conversión de onzas real",
           linea == "Una hoja con 14 productos. Precios en dólares, sin convertir. Tamaños como «4.8 fl oz», que pasamos a 142 ML.")
    codigos = {f["codigo"] for f in tabla["filas"]}
    probar("FDS de Norte: los productos de la lista que van como aerosol inflamable",
           s.linea_de_fds(FDS_NORTE, codigos, 0).endswith("al depósito como aerosol inflamable."))
    probar("FDS: avisa si alguna ya la había mandado antes", "ya la había mandado antes" in s.linea_de_fds(FDS_NORTE, codigos, 1))
    probar("registrado: lee el JSON de registrar_ficha", s.registrado_en('{"registrado": "P08:IN7003", "estado": "x"}') == "P08:IN7003")
    probar("registrado: texto que no es JSON -> None", s.registrado_en("Hook: no") is None)

    consolidado = json.loads((referencias.CARPETA_REFERENCIAS_SEM7 / "consolidado" / "P08.json").read_text(encoding="utf-8"))
    columnas, fila = s.columnas_entendidas(RECEPCION_NORTE, tabla, consolidado)
    por_columna = {c["columna"]: c for c in columnas}
    probar("así entendimos el archivo: las 6 columnas de Norte en el orden del archivo, ejemplo de la fila 2",
           [c["columna"] for c in columnas] == ["Item #", "Description", "Size", "UPC/EAN", "Unit cost (USD)", "Origin"] and fila == 2)
    probar("Item # es el código del proveedor, IN7003", por_columna["Item #"]["dato"] == "Código del proveedor" and por_columna["Item #"]["ejemplo"] == "IN7003")
    probar("Origin no se usa", por_columna["Origin"]["dato"] == "No se usa" and not por_columna["Origin"]["usa"])
    probar("el precio en dólares, sin convertir", por_columna["Unit cost (USD)"]["ejemplo"] == "5.17 dólares, sin convertir")
    probar("el contenido con la cuenta del código", por_columna["Size"]["ejemplo"] == "4.8 fl oz, que son 142 ML")
    probar("el código de barras completado a 13 dígitos", por_columna["UPC/EAN"]["ejemplo"] == "229962606567, completado a 13 dígitos")

    r = s.resumen_del_proveedor("P08", "Importadora Norte S.A.", RESULTADOS, False)
    probar("Norte: los 14 listos para alta, nada que pedir",
           r["titulo"] == "Los 14 productos de Importadora Norte S.A. están listos para dar de alta"
           and r["bajada"] == "Ninguno estaba ya en el catálogo y no hay nada que pedirle al proveedor." and (r["alta"], r["duplicado"], r["a_revision"]) == (14, 0, 0))
    r = s.resumen_del_proveedor("P04", "Higiene Total S.A.", RESULTADOS, True)
    probar("Higiene Total: 18 + 5 + 5, en palabras y con el pedido",
           r["titulo"] == "Listas las 28 fichas de Higiene Total S.A."
           and r["bajada"] == "18 para dar de alta, 5 ya estaban en el catálogo y 5 esperan que los mires. El pedido al proveedor ya está armado.")
    titulo, renglones, paso = s.detalle_del_problema({"estado": "no_entro", "problemas": ["La moneda coincide con lo que dice el archivo"]})
    probar("no entró: en palabras, en el paso 2", paso == s.ENTENDER and renglones[0] == "No se cumplió: la moneda coincide con lo que dice el archivo.")

    # --- 3. Las trazas ---
    base = proyecto_temporal()
    falsos = PasosFalsos(base / "salida", pausa=0)
    falsos.fichar("P08")
    registradas, en_curso = s.mirar_trazas(base / "salida" / "trazas", time.time() - 60)
    probar("trazas: 14 fichas registradas, ninguna en curso, sin contar líneas a medio escribir", len(registradas) == 14 and not en_curso)
    probar("trazas viejas (de antes de la corrida) no cuentan", s.mirar_trazas(base / "salida" / "trazas", time.time() + 60) == (set(), set()))
    probar("sin carpeta de trazas: nada", s.mirar_trazas(base / "no_existe", 0) == (set(), set()))

    # --- 4. Una corrida entera con la mesa de entradas ---
    usados = []  # los pasos falsos de cada corrida, para ver qué se llamó

    def mesa_temporal(**opciones):
        base = proyecto_temporal()

        def fabrica(ruta_log):
            usados.append(PasosFalsos(base / "salida", ruta_log=ruta_log, **opciones))
            return usados[-1]
        mesa = s.MesaDeEntradas(carpeta_proyecto=base, carpeta_entrada=base / "entrada", fabrica_de_pasos=fabrica, a_mano=A_MANO)
        return mesa, base

    def esperar(corrida, tope=20):
        limite = time.time() + tope
        while corrida.estado_publico()["estado"] == "corriendo" and time.time() < limite:
            time.sleep(0.05)
        return corrida.estado_publico()

    mesa, base = mesa_temporal()
    try:
        mesa.recibir_archivo("lista.csv", b"a;b")
        probar("un CSV no se recibe", False)
    except ValueError as error:
        probar("un CSV no se recibe (por ahora Excel y sus FDS en PDF)", "Excel" in str(error))
    raro = mesa.recibir_archivo("../../servidor_web.xlsx", EXCEL_NORTE.read_bytes())
    probar("un nombre con ../ queda solo con el nombre, dentro de la subida",
           raro["archivos"] == ["servidor_web.xlsx"] and (mesa.carpeta_subidas / raro["subida"] / "servidor_web.xlsx").exists())
    for nombre, contenido, se_espera in [("lista.xlsx", b"no soy un excel", "no es un Excel que se pueda abrir"),
                                         ("vieja.xlsx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 20, "formato viejo de Excel"),
                                         ("fds.pdf", b"hola", "no es un PDF")]:
        try:
            mesa.recibir_archivo(nombre, contenido)
            probar(f"{nombre} roto no se recibe", False)
        except ValueError as error:
            probar(f"{nombre} roto no se recibe, con el motivo", se_espera in str(error))
    subida = mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())
    probar("al subir el Excel de Norte, se sugiere Norte", subida["sugerido"] == "P08" and subida["excel"] == "NorteImports_new_items_Q4.xlsx")
    fds = NORTE / "fichas_de_seguridad" / "FDS_PureCare_in_sec.pdf"
    subida = mesa.recibir_archivo(fds.name, fds.read_bytes(), subida["subida"])
    probar("la FDS se suma a la misma subida", subida["fds"] == ["FDS_PureCare_in_sec.pdf"] and subida["excel"])
    try:
        mesa.empezar(subida["subida"], "P03")
        probar("Litoral (CSV) no se puede elegir", False)
    except ValueError as error:
        probar("Litoral (CSV) no se puede elegir", "todavía no se puede subir desde acá" in str(error))
    try:
        mesa.empezar("no-es-una-subida", "P08")
        probar("una subida inventada se rechaza", False)
    except ValueError:
        probar("una subida inventada se rechaza", True)

    corrida = mesa.empezar(subida["subida"], "P08")
    probar("el Excel quedó en entrada/P08_Importadora_Norte/", (base / "entrada" / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx").exists())
    probar("la FDS quedó en fichas_de_seguridad/", (base / "entrada" / "P08_Importadora_Norte" / "fichas_de_seguridad" / fds.name).exists())
    otra = mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())
    try:
        mesa.empezar(otra["subida"], "P08")
        segunda = "arrancó"
    except RuntimeError:
        segunda = "esperó"
    final = esperar(corrida)
    probar("mientras corre una lista, no arranca otra", segunda == "esperó")
    probar("la corrida terminó bien", final["estado"] == "listo")
    probar("los 5 pasos quedaron hechos", [p["estado"] for p in final["pasos"]] == ["hecho"] * 5)
    probar("paso 1: un Excel de Norte con su ficha de seguridad", final["pasos"][0]["linea"] == "Un Excel de Importadora Norte S.A., con 1 ficha de seguridad.")
    probar("paso 2: la línea de la recepción", final["pasos"][1]["linea"].startswith("Una hoja con 14 productos."))
    probar("paso 3: lo que dicen las fichas de seguridad", "aerosol inflamable" in final["pasos"][2]["linea"])
    probar("14 cuadraditos, todos hechos", final["total"] == 14 and final["hechas"] == 14 and all(p["estado"] == "hecho" for p in final["productos"]))
    probar("cada cuadradito con la descripción del Excel", final["productos"][0]["descripcion"] == "Pure Care Original Dry Shampoo")
    probar("el resultado: los 14 de Norte listos", final["resultado"]["titulo"].startswith("Los 14 productos de Importadora Norte"))
    probar("costo: solo lo pagado en esta corrida (las fichas, US$ 0,021)", final["resultado"]["costo_usd"] == 0.0214
           and "costó US$ 0,021" in final["resultado"]["tiempo_y_costo"])
    bandeja = json.loads((base / "salida" / "bandeja.json").read_text(encoding="utf-8"))
    anotado = next(iter(bandeja.values()))
    probar("se anotó en la bandeja como procesado, con su huella", len(bandeja) == 1 and anotado["estado"] == "procesado"
           and anotado["huella"] == __import__("vigilar").huella_del_archivo(EXCEL_NORTE))
    probar("se llamaron los pasos de la bandeja en orden, y el acuse",
           usados[-1].llamadas == ["recibir", "leer_fds", "fichar", "pedir", "acusar"])
    grabada = mesa.corrida_de_ejemplo()
    probar("la corrida quedó grabada para el plan B, con el avance de a poco",
           grabada and grabada["estados"][-1]["estado"] == "listo" and len(grabada["estados"]) > 10
           and grabada["estados"][0]["estado"] == "corriendo")
    probar("la grabación avanza en el tiempo", all(a["t"] <= b["t"] for a, b in zip(grabada["estados"], grabada["estados"][1:])))
    hechas = [e["hechas"] for e in grabada["estados"]]
    probar("en la grabación las fichas van apareciendo (no todas juntas)", len(set(hechas)) > 3)

    # La misma lista otra vez: se vuelve a procesar (la persona lo pidió), aunque la huella sea la misma
    corrida = mesa.empezar(otra["subida"], "P08")
    probar("la misma lista se puede volver a procesar", esperar(corrida)["estado"] == "listo")
    probar("la segunda vez, sin FDS nuevas, usa las que ya había mandado", "1 ficha de seguridad" in corrida.estado_publico()["pasos"][0]["linea"])

    # --- 5. Lo que no sale bien ---
    mesa, base = mesa_temporal(receta_entra=False)
    corrida = mesa.empezar(mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())["subida"], "P08")
    final = esperar(corrida)
    probar("receta que no entra: problema, frenado en el paso 2, sin fichas",
           final["estado"] == "problema" and final["pasos"][1]["estado"] == "error" and final["pasos"][3]["estado"] == "pendiente")
    probar("el motivo en palabras", "No se cumplió: la moneda coincide con lo que dice el archivo." in final["problema"]["detalle"]
           and final["pasos"][1]["linea"] == "Acá se frenó: el motivo está abajo.")
    probar("una corrida que no terminó bien no se graba como ejemplo", mesa.corrida_de_ejemplo() is None)

    mesa, base = mesa_temporal(codigo_fichar=1)
    final = esperar(mesa.empezar(mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())["subida"], "P08"))
    probar("si el orquestador falla: problema en el paso de las fichas", final["estado"] == "problema" and final["pasos"][3]["estado"] == "error")

    mesa, base = mesa_temporal(explota_en="recibir")
    final = esperar(mesa.empezar(mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())["subida"], "P08"))
    probar("si la API rechaza la key: problema en el paso 2, dicho en palabras",
           final["estado"] == "problema" and final["pasos"][1]["estado"] == "error"
           and final["problema"]["titulo"] == "No se pudo hablar con Anthropic"
           and "La key de Anthropic no es válida" in final["problema"]["detalle"][0])

    mesa, base = mesa_temporal(sin_conexion=True)
    final = esperar(mesa.empezar(mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())["subida"], "P08"))
    probar("sin conexión: el orquestador termina bien pero no escribió nada; se frena en las fichas, dicho en palabras",
           final["estado"] == "problema" and final["pasos"][3]["estado"] == "error" and final["pasos"][4]["estado"] == "pendiente"
           and final["problema"]["detalle"] == ["No hay conexión con Anthropic. Revisá internet y probá de nuevo."])
    probar("sin conexión: no se arma el pedido (no hay fichas nuevas)", "pedir" not in usados[-1].llamadas)

    def sin_env(ruta_log):
        raise SystemExit("ERROR: falta MODELO en el .env")
    base = proyecto_temporal()
    mesa = s.MesaDeEntradas(carpeta_proyecto=base, carpeta_entrada=base / "entrada", fabrica_de_pasos=sin_env, a_mano=A_MANO)
    final = esperar(mesa.empezar(mesa.recibir_archivo("NorteImports_new_items_Q4.xlsx", EXCEL_NORTE.read_bytes())["subida"], "P08"))
    probar("sin MODELO en el .env: lo dice, sin tirar abajo el servidor", final["estado"] == "problema" and ".env" in final["problema"]["detalle"][0])

    # --- 6. El servidor web, de punta a punta ---
    os.environ["INGESTA_CARPETA_SALIDA"] = str(referencias.CARPETA_REFERENCIAS_SEM6)
    import uvicorn
    import servidor_web
    mesa, base = mesa_temporal(pausa=0.03)
    servidor_web._mesa = mesa

    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        PUERTO = libre.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(servidor_web.app, host="127.0.0.1", port=PUERTO, log_level="error"))
    threading.Thread(target=servidor.run, daemon=True).start()
    while not servidor.started:
        time.sleep(0.05)

    def pedir(direccion, cuerpo=None, tipo="application/json"):
        pedido = urllib.request.Request(f"http://127.0.0.1:{PUERTO}{direccion}", data=cuerpo,
                                        method="POST" if cuerpo is not None else "GET", headers={"Content-Type": tipo})
        try:
            with urllib.request.urlopen(pedido, timeout=20) as respuesta:
                return respuesta.status, json.loads(respuesta.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    codigo, inicio = pedir("/api/inicio")
    probar("/api/inicio: números, las 9 listas procesadas y los 9 proveedores", codigo == 200 and inicio["numeros"]["total"] == 257
           and len(inicio["procesadas"]) == 9 and len(inicio["proveedores"]) == 9)
    probar("/api/inicio: Norte en la tabla, con lo que mandó", next(p for p in inicio["procesadas"] if p["id"] == "P08")
           == {"id": "P08", "nombre": "Importadora Norte S.A.", "formato": "Excel y 2 fichas de seguridad", "productos": 14,
               "alta": 14, "duplicado": 0, "a_revision": 0})
    probar("/api/inicio: sin corrida de ejemplo todavía", inicio["ejemplo"] is None)
    codigo, _ = pedir("/api/corrida_de_ejemplo")
    probar("/api/corrida_de_ejemplo sin grabación: 404", codigo == 404)
    codigo, datos = pedir("/api/subidas?nombre=lista.txt", b"hola", "application/octet-stream")
    probar("subir un .txt: 400 con el motivo", codigo == 400 and "Excel" in datos["error"])
    codigo, subida = pedir("/api/subidas?nombre=" + urllib.request.quote("NorteImports_new_items_Q4.xlsx"), EXCEL_NORTE.read_bytes(),
                           "application/octet-stream")
    probar("subir el Excel de Norte: sugiere Norte", codigo == 200 and subida["sugerido"] == "P08")
    codigo, datos = pedir("/api/corridas", json.dumps({"subida": subida["subida"], "proveedor": "P01"}).encode())
    probar("empezar con Andes: 400", codigo == 400)
    codigo, datos = pedir("/api/corridas", b"no es json")
    probar("empezar con un pedido mal armado: 400", codigo == 400)
    codigo, corrida = pedir("/api/corridas", json.dumps({"subida": subida["subida"], "proveedor": "P08"}).encode())
    probar("empezar con Norte: arranca", codigo == 200 and corrida["estado"] == "corriendo")
    vistos = set()
    limite = time.time() + 20
    while time.time() < limite:
        codigo, corrida = pedir(f"/api/corridas/{corrida['id']}")
        vistos.add(corrida["hechas"])
        if corrida["estado"] != "corriendo":
            break
        time.sleep(0.05)
    probar("siguiendo la corrida se ve el avance de a poco", len(vistos) > 3)
    probar("la corrida terminó y cuenta el resultado", corrida["estado"] == "listo" and corrida["resultado"]["total"] == 14)
    codigo, _ = pedir("/api/corridas/noexiste")
    probar("una corrida que no existe: 404", codigo == 404)
    codigo, inicio = pedir("/api/inicio")
    probar("después, /api/inicio ofrece la corrida de ejemplo", inicio["ejemplo"] is not None)
    codigo, grabacion = pedir("/api/corrida_de_ejemplo")
    probar("/api/corrida_de_ejemplo: la grabación entera", codigo == 200 and grabacion["estados"][-1]["estado"] == "listo")
    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/", timeout=10) as respuesta:
        pagina = respuesta.read().decode("utf-8")
    probar("la pantalla carga sus estilos y su programa", "/web/subir.css" in pagina and "/web/subir.js" in pagina)
    probar("la pantalla trae los números reales en el costado", 'id="numero-total">257<' in pagina)
    servidor.should_exit = True
    os.environ.pop("INGESTA_CARPETA_SALIDA", None)

    print()
    print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
