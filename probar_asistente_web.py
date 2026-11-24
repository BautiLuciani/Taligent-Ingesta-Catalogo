"""Pruebas sin IA del asistente en la interfaz (semana 7, paso 4).

El asistente falso contesta con respuestas REALES del asistente, congeladas de la última corrida del evaluador de
consultas (referencias_sem7/respuestas_asistente.json: 29 de 29). Las fichas son las congeladas de referencias_sem6/.
"""
import asyncio
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import referencias

import asistente_web as a
import presentacion

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


GUARDADAS = json.loads((referencias.CARPETA_REFERENCIAS_SEM7 / "respuestas_asistente.json").read_text(encoding="utf-8"))
FICHAS = {f["id"]: f for f in presentacion.fichas_para_pantalla(json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8")))}
POR_PREGUNTA = {v["consulta"]: v for v in GUARDADAS.values()}

# --- La respuesta para la pantalla ---
r = a.respuesta_para_pantalla(GUARDADAS["V02.1"], FICHAS)
probar("V02.1: el texto del asistente, sin tocar", r["texto"] == GUARDADAS["V02.1"]["texto"])
probar("V02.1: 4 productos para revisar", r["valor"] == "4" and r["etiqueta"] == "productos para revisar" and r["estado_comun"] == "a_revision")
probar("V02.1: cada producto con su nombre tal cual la ficha y su motivo",
       [(i["codigo"], i["nombre"], i["detalle"]) for i in r["items"][:1]] ==
       [("AN-1103", "DOLOREX 400 MG COMPRIMIDOS X 20 UN", "Falta un dato obligatorio: principio activo")])
probar("V02.1: las fuentes como chips (tipo, archivo real y lugar)",
       all(f["tipo"] in ("PDF", "Excel") and f["ubicacion"] for f in r["fuentes"]) and len(r["fuentes"]) == len(GUARDADAS["V02.1"]["fuentes"]))
probar("V02.1: tiempo y costo en palabras", r["meta"] == f"Contestó en {GUARDADAS['V02.1']['segundos']:.1f} segundos y costó US$ {GUARDADAS['V02.1']['costo_usd']:.3f}".replace(".", ","))
r = a.respuesta_para_pantalla(GUARDADAS["Q01"], FICHAS)
probar("Q01: el precio con coma (320,80), sin etiqueta de productos", r["valor"] == "320,80" and r["etiqueta"] == "")
probar("Q01: un producto lista para alta: el detalle es proveedor y precio", r["items"][0]["detalle"] == "Laboratorio Andes S.A., UYU 320,80")
r = a.respuesta_para_pantalla(GUARDADAS["Q18"], FICHAS)
probar("Q18: 209, sin productos ni fuentes", r["valor"] == "209" and not r["items"] and not r["fuentes"])
r = a.respuesta_para_pantalla(GUARDADAS["Q22"], FICHAS)
probar("Q22 (no está): sin valor, sin productos, sin fuentes", (r["valor"], r["items"], r["fuentes"]) == ("", [], []))
probar("Q22: costó US$ 0,0003: dice «menos de US$ 0,001» (no «US$ 0,000»)", r["meta"].endswith("costó menos de US$ 0,001"))
r = a.respuesta_para_pantalla({"texto": "x", "items": ["P99:NO-EXISTE"], "fuentes": [], "valor": None}, FICHAS)
probar("un producto que no está en las fichas se muestra con su código, sin inventar nombre", r["items"][0]["nombre"] == "P99:NO-EXISTE")
probar("números: 1.101 con punto de miles", a.numero_en_palabras(1101) == "1.101")
probar("un texto queda tal cual", a.numero_en_palabras("USD 5,17") == "USD 5,17")

# --- Las sugerencias: las conversaciones de la consigna ---
guiones = a.guion_de_conversaciones()
probar("las 2 conversaciones de la consigna (V01 y V02)", len(guiones) == 2 and len(guiones[1]) == 3)
probar("después del turno 1 de V02 se sugiere el 2", a.sugerencia_despues_de("¿Qué quedó a revisión de Laboratorio Andes?", guiones)
       == "¿Cuáles de esos por diferencias entre los dos archivos?")
probar("después del último turno, nada", a.sugerencia_despues_de("¿Dónde está cada versión?", guiones) is None)
probar("una pregunta cualquiera, nada", a.sugerencia_despues_de("hola", guiones) is None)
probar("los 3 ejemplos de la bienvenida son consultas de la consigna",
       all(e in POR_PREGUNTA for e in a.EJEMPLOS))

# --- Los errores, en palabras ---
class AuthenticationError(Exception):
    pass


probar("key inválida: dice cómo revisarla", "verificar_entorno" in a.error_en_palabras(AuthenticationError("401")))
probar("sin MODELO: el motivo tal cual", "MODELO" in a.error_en_palabras(RuntimeError("Falta MODELO en el .env")))


# --- El motor, con un asistente falso que recuerda la conversación ---
class ConversacionFalsa:
    def __init__(self):
        self.historial = []

    async def preguntar(self, texto):
        self.historial.append(texto)
        await asyncio.sleep(0.05)
        if texto == "explotá":
            raise RuntimeError("se cortó")
        base = POR_PREGUNTA.get(texto, {"consulta": texto, "texto": "No está en lo generado.", "valor": None, "items": [],
                                         "fuentes": [], "avisos": [], "segundos": 0.1, "costo_usd": 0.0})
        return {**base, "turno": len(self.historial)}


abiertas = []


async def abrir_falsa(estado):
    estado["veces"] = estado.get("veces", 0) + 1
    abiertas.append(ConversacionFalsa())
    return abiertas[-1]


motor = a.MotorDelAsistente(abrir_falsa)
uno = motor.nueva()
probar("abrir una conversación devuelve un id", len(uno) == 12)
respuesta = motor.preguntar(uno, "¿Qué quedó a revisión de Laboratorio Andes?")
probar("preguntar devuelve la respuesta del asistente", respuesta["valor"] == 4 and respuesta["turno"] == 1)
probar("la misma conversación recuerda (memoria): segundo turno", motor.preguntar(uno, "¿Y cuál es el más caro?")["turno"] == 2)
otro = motor.nueva()
probar("una conversación nueva empieza vacía", motor.preguntar(otro, "hola")["turno"] == 1 and len(abiertas[0].historial) == 2)
try:
    motor.preguntar("noexiste1234", "hola")
    probar("una conversación que no existe: error claro", False)
except KeyError as error:
    probar("una conversación que no existe: error claro", "nueva" in str(error))
try:
    motor.preguntar(uno, "explotá")
    probar("si el asistente falla, el error llega (no se cuelga)", False)
except RuntimeError:
    probar("si el asistente falla, el error llega (no se cuelga)", True)
resultados = []
hilos = [threading.Thread(target=lambda t=t: resultados.append(motor.preguntar(uno, f"pregunta {t}"))) for t in range(3)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
probar("3 preguntas a la vez se contestan de a una, sin mezclarse", sorted(x["turno"] for x in resultados) == [4, 5, 6])

# --- El servidor ---
os.environ["INGESTA_CARPETA_SALIDA"] = str(referencias.CARPETA_REFERENCIAS_SEM6)
import uvicorn  # noqa: E402

import servidor_web  # noqa: E402

servidor_web._motor = a.MotorDelAsistente(abrir_falsa)
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


codigo, datos = pedir("/api/asistente")
probar("/api/asistente: los ejemplos", codigo == 200 and datos["ejemplos"] == a.EJEMPLOS)
codigo, texto = pedir("/asistente")
probar("la pantalla: estilos, programa y el marco de chat (encabezado y caja fijos)",
       "/web/asistente.css" in texto and "/web/asistente.js" in texto and 'class="app pantalla-chat"' in texto)
codigo, conversacion = pedir("/api/asistente/conversaciones", b"")
probar("abrir una conversación por la web", codigo == 200 and conversacion["id"])
url = f"/api/asistente/conversaciones/{conversacion['id']}/preguntas"
codigo, datos = pedir(url, json.dumps({"texto": "¿Qué quedó a revisión de Laboratorio Andes?"}).encode())
probar("preguntar por la web: la respuesta lista para la pantalla",
       codigo == 200 and datos["respuesta"]["etiqueta"] == "productos para revisar" and len(datos["respuesta"]["items"]) == 4)
probar("y la sugerencia del turno siguiente de la consigna", datos["sugerencia"] == "¿Cuáles de esos por diferencias entre los dos archivos?")
codigo, datos = pedir(url, json.dumps({"texto": "   "}).encode())
probar("una pregunta vacía: 400", codigo == 400)
codigo, datos = pedir(url, json.dumps({"texto": "x" * 1001}).encode())
probar("una pregunta larguísima: 400", codigo == 400)
codigo, datos = pedir(url, b"no es json")
probar("un pedido mal armado: 400", codigo == 400)
codigo, datos = pedir("/api/asistente/conversaciones/noexiste1234/preguntas", json.dumps({"texto": "hola"}).encode())
probar("una conversación que no existe: 404 con el motivo", codigo == 404 and "nueva" in datos["error"])
codigo, datos = pedir(url, json.dumps({"texto": "explotá"}).encode())
probar("si el asistente falla: 503 con el motivo, sin tirar abajo el servidor", codigo == 503 and "se cortó" in datos["error"])


async def abrir_sin_modelo(estado):
    raise RuntimeError("Falta MODELO en el .env: el asistente no puede arrancar.")


servidor_web._motor = a.MotorDelAsistente(abrir_sin_modelo)
codigo, datos = pedir("/api/asistente/conversaciones", b"")
probar("sin MODELO en el .env: 503 que lo dice", codigo == 503 and "MODELO" in datos["error"])
servidor.should_exit = True

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
