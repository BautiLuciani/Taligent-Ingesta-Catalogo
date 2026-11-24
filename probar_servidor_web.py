"""Pruebas sin IA de la interfaz web (semana 7): el servidor levanta de verdad y se le piden las pantallas.

Lee las 257 fichas CONGELADAS del cierre de la semana 5 (referencias_sem6/), no la última corrida de salida/.
"""
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import referencias  # noqa: F401  (antes que nada que lea salida/)

os.environ["INGESTA_CARPETA_SALIDA"] = str(referencias.CARPETA_REFERENCIAS_SEM6)

import uvicorn  # noqa: E402

import servidor_web  # noqa: E402

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


# --- 1. Las cuentas, sin servidor ---
resultados = json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8"))
numeros = servidor_web.resumen(resultados)
probar("resumen: 257 fichas", numeros["total"] == 257)
probar("resumen: 209 + 24 + 24 = 257", (numeros["lista_para_alta"], numeros["duplicado"], numeros["a_revision"]) == (209, 24, 24))
probar("resumen: 9 proveedores", numeros["proveedores"] == 9)
probar("resumen de nada: todo en 0", servidor_web.resumen({}) == {"total": 0, "lista_para_alta": 0, "duplicado": 0,
                                                                   "a_revision": 0, "proveedores": 0})
probar("lee de la copia congelada, no de salida/", servidor_web.RUTA_RESULTADOS == referencias.RUTA_RESULTADOS_SEM5)

menu = servidor_web.enlaces_del_menu("/fichas", numeros)
probar("menú: 5 enlaces", menu.count('class="nav-link') == 5)
probar("menú: marca solo la pantalla actual", menu.count("nav-activo") == 1 and 'href="/fichas" class="nav-link nav-activo"' in menu)
probar("menú: la actual con aria-current", menu.count('aria-current="page"') == 1)
probar("menú: 257 al lado de Fichas", '<span class="nav-contador">257</span>' in menu)
probar("menú: insignia con 24 en Para revisar", '<span class="nav-insignia">24</span>' in menu)
sin_revision = servidor_web.enlaces_del_menu("/", {**numeros, "a_revision": 0})
probar("menú: sin productos para revisar no hay insignia", "nav-insignia" not in sin_revision)
probar("completar no deja {{ }} sin reemplazar", "{{" not in servidor_web.armar_pantalla("/fichas", resultados))


# --- 2. El servidor de verdad, en un puerto libre ---
def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PUERTO = puerto_libre()
servidor = uvicorn.Server(uvicorn.Config(servidor_web.app, host="127.0.0.1", port=PUERTO, log_level="error"))
hilo = threading.Thread(target=servidor.run, daemon=True)
hilo.start()
for _ in range(100):
    if servidor.started:
        break
    time.sleep(0.05)
probar("el servidor levanta", servidor.started)


def pedir(direccion):
    """(código, tipo de contenido, texto) de lo que contesta el servidor."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}{direccion}", timeout=10) as respuesta:
            return respuesta.status, respuesta.headers.get("content-type", ""), respuesta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("content-type", ""), ""


TITULOS = {"/": "¿Qué lista llegó hoy?", "/fichas": "Fichas", "/revision": "Para revisar",
           "/asistente": "Asistente", "/costos": "Corridas y costos"}
for direccion, titulo in TITULOS.items():
    codigo, tipo, texto = pedir(direccion)
    probar(f"{direccion}: contesta 200 en HTML", codigo == 200 and tipo.startswith("text/html"))
    probar(f"{direccion}: título «{titulo}»", f'<h1 class="titulo">{titulo}</h1>' in texto)
    probar(f"{direccion}: con el menú y su pantalla marcada",
           'class="sidebar"' in texto and f'href="{direccion}" class="nav-link nav-activo"' in texto)
    probar(f"{direccion}: sin {{{{ }}}} sueltos", "{{" not in texto)

_, _, texto = pedir("/fichas")
probar("Fichas: el encabezado cuenta las fichas reales", "Los 257 productos nuevos de los 9 proveedores" in texto)
_, _, texto = pedir("/revision")
probar("Para revisar: el encabezado cuenta las reales", "24 productos que Ceibo no pudo resolver solo" in texto)

codigo, tipo, texto = pedir("/api/resumen")
probar("/api/resumen: JSON con los números", codigo == 200 and tipo.startswith("application/json")
       and json.loads(texto) == numeros)

codigo, tipo, texto = pedir("/web/estilos.css")
probar("los estilos se sirven", codigo == 200 and "text/css" in tipo and "--rojo: #B4282B" in texto)
codigo, tipo, _ = pedir("/web/fuentes/onest-latin.woff2")
probar("la letra va guardada en el proyecto (funciona sin internet)", codigo == 200)
probar("ninguna pantalla pide nada a internet", all("http" not in pedir(d)[2].replace("http://www.w3.org", "")
                                                    for d in TITULOS))
codigo, _, _ = pedir("/no-existe")
probar("una dirección que no existe: 404", codigo == 404)
codigo, _, _ = pedir("/web/../servidor_web.py")
probar("no se puede salir de web/ para leer el código", codigo == 404)

servidor.should_exit = True
hilo.join(timeout=5)

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
