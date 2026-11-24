"""Pruebas sin IA de Corridas y costos (semana 7, paso 5).

Los números salen de los reportes CONGELADOS de la última corrida completa (referencias_sem7/: corrida_completa.json
del 18/11, costo_por_ficha.json y consultas/evaluacion.json). "Correr los 9 proveedores" se prueba con un comando falso
que escribe trazas como los fichadores y deja un reporte nuevo: nunca se corre correr_todo.py de verdad.
"""
import json
import os
import socket
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import referencias

import corridas as c

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


N = " "  # el espacio que no se corta entre US$ y el monto
d = c.datos_de_costos(referencias.CARPETA_REFERENCIAS_SEM7)

# --- Formatos ---
probar("fecha en palabras", c.fecha_en_palabras("2026-11-18 20:51") == "18 de noviembre a las 20:51")
probar("minutos redondos: 653 s son 11 minutos, 1958 s son 33", (c.minutos_redondos(653), c.minutos_redondos(1958)) == ("11 minutos", "33 minutos"))
probar("dólares con coma y espacio que no se corta", c.dolares(0.0453, 3) == f"US${N}0,045")

# --- Los números de la corrida del 18/11 ---
probar("hay corrida", d["hay_corrida"])
probar("257 fichas, 11 min 1 s, US$ 0,38, US$ 0,0015 por ficha",
       (d["fichas"], d["tiempo"], d["costo"], d["por_ficha"]) == (257, "11 min 1 s", f"US${N}0,38", f"US${N}0,0015"))
probar("última corrida: 18 de noviembre a las 20:51, en el momento", (d["fecha"], d["modo"]) == ("18 de noviembre a las 20:51", "en el momento"))
probar("4 etapas en palabras, en orden",
       [e["titulo"] for e in d["etapas"]] == ["Recibir los Excel y sus fichas de seguridad", "Leer los PDF, el folleto y las fichas de seguridad",
                                            "Armar las 257 fichas y guardarlas", "Pedidos a proveedores y acuses de recibo"])
probar("la lectura no costó nada porque ya estaba leída", d["etapas"][1]["tiempo"] == "0 s, ya estaban leídos" and d["etapas"][1]["costo"] == "US$ 0")
probar("armar las fichas: 10 min 40 s y US$ 0,381, la barra más larga",
       (d["etapas"][2]["tiempo"], d["etapas"][2]["costo"], d["etapas"][2]["ancho"]) == ("10 min 40 s", f"US${N}0,381", 100.0))
probar("9 proveedores con su nombre tal cual el reporte", len(d["proveedores"]) == 9 and d["proveedores"][0]["nombre"] == "Laboratorio Andes S.A.")
probar("Andes: 26 fichas, US$ 0,045, US$ 0,0017 por ficha",
       (d["proveedores"][0]["fichas"], d["proveedores"][0]["costo"], d["proveedores"][0]["por_ficha"]) == (26, f"US${N}0,045", f"US${N}0,0017"))
probar("Rivera, el más caro, tiene la barra entera", d["proveedores"][1]["ancho"] == 100)
probar("evaluador: 115 de 116 fichas, 116 de 116 fuentes", (d["evaluador"]["ficha"], d["evaluador"]["fuente"], d["evaluador"]["casos"]) == (115, 116, 116))
probar("asistente: 29 de 29 a US$ 0,001 cada una", d["consultas"] == {"bien": 29, "total": 29, "por_consulta": f"US${N}0,001"})
probar("caché: 78 % de lo que lee", d["cache"] == 78)
probar("costo por ficha en 3 escenarios: 0,0022 / 0,0015 / 0,0008",
       [x["valor"] for x in d["por_ficha_escenarios"]] == [f"US${N}0,0022", f"US${N}0,0015", f"US${N}0,0008"])
probar("las dos formas de correr, con su tiempo y su costo",
       [o["detalle"] for o in d["opciones_de_corrida"]] == [f"Unos 11 minutos, cerca de US${N}0,38", f"Unos 33 minutos, cerca de US${N}0,21"])
probar("sin reportes: lo dice, sin romperse", c.datos_de_costos(Path(tempfile.mkdtemp())) == {"hay_corrida": False})

# --- Correr los 9 proveedores, con un comando falso ---
FALSO = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    salida = Path(sys.argv[1]); falla = sys.argv[2] == "falla"
    carpeta = salida / "trazas" / f"paralelo_{time.strftime('%Y%m%d_%H%M%S')}_3"; carpeta.mkdir(parents=True, exist_ok=True)
    traza = carpeta / "P08_desde_000.jsonl"
    for i in range(6):
        with open(traza, "a", encoding="utf-8") as f:
            f.write(json.dumps({"evento": "tool_result", "tool": "registrar_ficha", "is_error": False,
                                "content": json.dumps({"registrado": f"P08:IN70{i:02d}"})}) + "\\n")
        print("ficha", i, "→ armada"); sys.stdout.flush(); time.sleep(0.4)
    reporte = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "fichas": 6, "segundos": 3, "costo_usd": 0.01, "etapas": [],
               "proveedores": [], "frenados": {"P02": "su receta no entró"} if falla else {}}
    (salida / "corrida_completa.json").write_text(json.dumps(reporte), encoding="utf-8")
    sys.exit(1 if falla else 0)
''')
carpeta = Path(tempfile.mkdtemp())
script = carpeta / "correr_todo_falso.py"
script.write_text(FALSO, encoding="utf-8")


def esperar(corrida, tope=20):
    limite = time.time() + tope
    vistos = set()
    while corrida.corriendo() and time.time() < limite:
        vistos.add(corrida.estado_publico()["hechas"])
        time.sleep(0.1)
    return corrida.estado_publico(), vistos


salida = carpeta / "salida_bien"
salida.mkdir()
corrida = c.CorridaCompleta(salida, comando=lambda lote: [sys.executable, str(script), str(salida), "bien"])
corrida.empezar(lote=False, total_fichas=6)
try:
    corrida.empezar(lote=False, total_fichas=6)
    probar("mientras corre, no arranca otra", False)
except RuntimeError:
    probar("mientras corre, no arranca otra", True)
final, vistos = esperar(corrida)
probar("terminó bien, con las 6 fichas contadas desde las trazas", final["estado"] == "lista" and final["hechas"] == 6)
probar("el avance se vio de a poco", len(vistos) >= 3)
probar("dice cuánto tardó", final["texto"].startswith("Terminó en") and final["tiempo"])
registros = list((salida / "web" / "registros").glob("*_corrida_completa.log"))
probar("lo que imprimió quedó en el registro, con sus caracteres", registros and "→ armada" in registros[0].read_text(encoding="utf-8"))

salida = carpeta / "salida_mal"
salida.mkdir()
corrida = c.CorridaCompleta(salida, comando=lambda lote: [sys.executable, str(script), str(salida), "falla"])
corrida.empezar(lote=True, total_fichas=6)
final, _ = esperar(corrida)
probar("si se frena un proveedor: problema con el motivo del reporte", final["estado"] == "problema" and "P02: su receta no entró" in final["motivo"])

corrida = c.CorridaCompleta(carpeta, comando=lambda lote: [str(carpeta / "no_existe")])
corrida.empezar(lote=False, total_fichas=1)
final, _ = esperar(corrida)
probar("si el comando no arranca: problema que lo dice", final["estado"] == "problema" and "No se pudo arrancar" in final["motivo"])
probar("el comando de verdad: python correr_todo.py (y --batch por lote)",
       c.CorridaCompleta(carpeta).comando(False)[1:] == ["correr_todo.py"] and c.CorridaCompleta(carpeta).comando(True)[-1] == "--batch")

# --- El servidor ---
os.environ["INGESTA_CARPETA_SALIDA"] = str(referencias.CARPETA_REFERENCIAS_SEM6)
os.environ["INGESTA_CARPETA_REPORTES"] = str(referencias.CARPETA_REFERENCIAS_SEM7)
import uvicorn  # noqa: E402

import servidor_web  # noqa: E402

salida = carpeta / "salida_servidor"
salida.mkdir()
servidor_web._completa = c.CorridaCompleta(salida, comando=lambda lote: [sys.executable, str(script), str(salida), "bien"])
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


codigo, datos = pedir("/api/costos")
probar("/api/costos: los números y la corrida quieta", codigo == 200 and datos["datos"]["fichas"] == 257 and datos["corrida"]["estado"] == "quieta")
codigo, texto = pedir("/costos")
probar("la pantalla carga sus estilos y su programa", "/web/costos.css" in texto and "/web/costos.js" in texto)
codigo, _ = pedir("/api/costos/corrida", b"no es json")
probar("un pedido mal armado: 400", codigo == 400)
codigo, datos = pedir("/api/costos/corrida", json.dumps({"lote": False}).encode())
probar("correr por la web: arranca", codigo == 200 and datos["estado"] == "corriendo" and datos["total"] == 257)
codigo, datos = pedir("/api/costos/corrida", json.dumps({"lote": False}).encode())
probar("otra vez mientras corre: 409", codigo == 409)
mesa = servidor_web.mesa()
probar("mientras corre, Subir una lista no arranca (lo dice)", "corriendo los 9 proveedores" in (mesa.otro_trabajo() or ""))
limite = time.time() + 20
while time.time() < limite:
    codigo, datos = pedir("/api/costos/corrida")
    if datos["estado"] != "corriendo":
        break
    time.sleep(0.2)
probar("la corrida termina y lo cuenta", datos["estado"] == "lista")
probar("después, Subir una lista ya puede", mesa.otro_trabajo() is None)
servidor.should_exit = True

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
