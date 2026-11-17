"""Prueba cliente_batch.py SIN IA: con una Batch API falsa que devuelve desordenado y hace fallar pedidos a propósito.
Correr: python probar_cliente_batch.py"""
import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from cliente_batch import TARIFAS_BATCH, BatchFallido, ClienteBatch, a_json, con_ttl

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def exito(texto):
    return SimpleNamespace(type="succeeded", message=f"respuesta a {texto}")


def error(tipo):
    return SimpleNamespace(type="errored", error=SimpleNamespace(error=SimpleNamespace(type=tipo, message="falló")))


class BatchesFalsos:
    """Imita api.messages.batches. decidir(custom_id, params, numero_de_batch) -> resultado, o None si no vuelve.
    Devuelve los resultados AL REVÉS (desordenados) y tarda una consulta en terminar."""

    def __init__(self, decidir=None):
        self.decidir = decidir or (lambda cid, params, n: exito(params["messages"][0]["content"]))
        self.creados = []      # cada batch: la lista de pedidos que recibió
        self.cancelados = []
        self.consultas = {}

    def create(self, requests):
        json.dumps(requests)  # el batch viaja como JSON: si algo no se puede pasar, falla acá como en la real
        self.creados.append(requests)
        return SimpleNamespace(id=f"msgbatch_{len(self.creados)}")

    def retrieve(self, batch_id):
        self.consultas[batch_id] = self.consultas.get(batch_id, 0) + 1
        estado = "ended" if self.consultas[batch_id] >= 2 else "in_progress"
        return SimpleNamespace(processing_status=estado, request_counts=SimpleNamespace(processing=1))

    def results(self, batch_id):
        numero = int(batch_id.split("_")[1])
        salida = []
        for pedido in self.creados[numero - 1]:
            resultado = self.decidir(pedido["custom_id"], pedido["params"], numero)
            if resultado is not None:
                salida.append(SimpleNamespace(custom_id=pedido["custom_id"], result=resultado))
        return list(reversed(salida))

    def cancel(self, batch_id):
        self.cancelados.append(batch_id)


def cliente_con(batches, carpeta, **opciones):
    api = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    avisos = []
    opciones = {"espera_consulta": 0.01, "espera_juntar": 5, **opciones}
    return ClienteBatch(api, carpeta, avisar=avisos.append, **opciones), avisos


def preguntar(cliente, texto):
    """Lo que hace el fichador: una conversación con una vuelta."""
    with cliente.conversacion():
        with cliente.messages.stream(model="m", system=[{"type": "text", "text": "s", "cache_control": {"type": "ephemeral"}}],
                                     messages=[{"role": "user", "content": texto}]) as stream:
            return stream.get_final_message()


def preguntar_o_motivo(cliente, texto):
    try:
        return preguntar(cliente, texto)
    except BatchFallido as falla:
        return f"FALLÓ: {falla}"


carpeta = Path(tempfile.mkdtemp())

# --- 1. a_json y con_ttl (sin la ventanilla) ---
class BloqueSDK(BaseModel):
    type: str
    text: str
    citations: list | None = None

chequear("a_json pasa objetos del SDK a JSON con los campos que vinieron (como el SDK en tiempo real)",
         a_json({"messages": [{"role": "assistant", "content": [BloqueSDK(type="text", text="hola"),
                                                                BloqueSDK(type="text", text="chau", citations=None)]}]}),
         {"messages": [{"role": "assistant", "content": [{"type": "text", "text": "hola"},
                                                         {"type": "text", "text": "chau", "citations": None}]}]})
import anthropic.types as tipos_sdk  # noqa: E402  (objetos reales del SDK, armados como los arma la respuesta)
mensaje_real = tipos_sdk.Message.model_validate({
    "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "stop_reason": "tool_use",
    "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
    "content": [{"type": "thinking", "thinking": "pienso", "signature": "FIRMA"},
                {"type": "tool_use", "id": "toolu_1", "name": "registrar_ficha", "input": {"a": 1}}]})
chequear("a_json con un Message real del SDK: el thinking con su firma y el tool_use, tal cual",
         a_json(mensaje_real.content),
         [{"type": "thinking", "thinking": "pienso", "signature": "FIRMA"},
          {"type": "tool_use", "id": "toolu_1", "name": "registrar_ficha", "input": {"a": 1}}])
chequear("con_ttl agrega el TTL a cada cache_control (system y mensajes)",
         con_ttl({"system": [{"text": "s", "cache_control": {"type": "ephemeral"}}],
                  "messages": [{"content": [{"text": "m", "cache_control": {"type": "ephemeral"}}]}]}, "1h"),
         {"system": [{"text": "s", "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
          "messages": [{"content": [{"text": "m", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}]})
chequear("tarifas de batch: la mitad de las de tiempo real",
         TARIFAS_BATCH, {"input": 0.05, "escritura_cache": 0.10, "lectura_cache": 0.005, "output": 0.25})

# --- 2. Tres tandas a la vez: un solo batch, y cada una recibe SU respuesta aunque vuelvan al revés ---
batches = BatchesFalsos()
cliente, avisos = cliente_con(batches, carpeta / "dos")
cliente.planificar(conversaciones=3, a_la_vez=3)
with ThreadPoolExecutor(3) as hilos:
    respuestas = list(hilos.map(lambda t: preguntar(cliente, t), ["A", "B", "C"]))
chequear("3 tandas -> 1 solo batch con 3 pedidos", [len(b) for b in batches.creados], [3])
chequear("cada tanda recibe SU respuesta (por custom_id, no por posición)", respuestas,
         ["respuesta a A", "respuesta a B", "respuesta a C"])
chequear("el pedido viaja con el TTL de 1 hora",
         batches.creados[0][0]["params"]["system"][0]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
registro = json.loads(cliente.ruta_registro.read_text(encoding="utf-8"))
chequear("el registro anota el batch (id, pedidos, estados)",
         (registro[0]["batch_id"], registro[0]["pedidos"], registro[0]["estados"]),
         ("msgbatch_1", 3, {"succeeded": 3}))

# --- 2b. Sin planificar, la primera tanda que llega sale sola (por eso existe planificar) ---
batches = BatchesFalsos()
cliente, avisos = cliente_con(batches, carpeta / "dosb")
with ThreadPoolExecutor(2) as hilos:
    primera = hilos.submit(preguntar, cliente, "A")
    time.sleep(0.2)
    segunda = hilos.submit(preguntar, cliente, "B")
    primera.result(timeout=5), segunda.result(timeout=5)
chequear("sin planificar: 2 batches de 1", [len(b) for b in batches.creados], [1, 1])

# --- 2c. 4 tandas con 2 fichadores: cada vuelta junta a las 2 que están en curso ---
batches = BatchesFalsos()
cliente, avisos = cliente_con(batches, carpeta / "dosc")
cliente.planificar(conversaciones=4, a_la_vez=2)
with ThreadPoolExecutor(2) as hilos:
    respuestas = list(hilos.map(lambda t: preguntar(cliente, t), ["A", "B", "C", "D"]))
chequear("4 tandas de a 2: batches de 2 y 2", [len(b) for b in batches.creados], [2, 2])
chequear("las 4 reciben su respuesta", respuestas, [f"respuesta a {t}" for t in "ABCD"])

# --- 3. Un error del servidor se reintenta SOLO para ese pedido, en el batch siguiente ---
def falla_b_una_vez(cid, params, n):
    texto = params["messages"][0]["content"]
    return error("overloaded_error") if texto == "B" and n == 1 else exito(texto)

batches = BatchesFalsos(falla_b_una_vez)
cliente, avisos = cliente_con(batches, carpeta / "tres")
cliente.planificar(conversaciones=3, a_la_vez=3)
with ThreadPoolExecutor(3) as hilos:
    respuestas = list(hilos.map(lambda t: preguntar_o_motivo(cliente, t), ["A", "B", "C"]))
chequear("errored (overloaded) se reintenta y termina bien", respuestas,
         ["respuesta a A", "respuesta a B", "respuesta a C"])
chequear("el segundo batch lleva solo el pedido de B, con otro nombre (_r1)",
         [(p["params"]["messages"][0]["content"], p["custom_id"].endswith("_r1")) for p in batches.creados[1]],
         [("B", True)])
chequear("batches: 3 pedidos y después 1", [len(b) for b in batches.creados], [3, 1])

# --- 4. Un error del pedido (invalid_request_error) NO se reintenta ---
batches = BatchesFalsos(lambda cid, params, n: error("invalid_request_error"))
cliente, avisos = cliente_con(batches, carpeta / "cuatro")
respuesta = preguntar_o_motivo(cliente, "A")
chequear("invalid_request_error: falla sin reintentar", (respuesta.startswith("FALLÓ"), len(batches.creados)),
         (True, 1))
chequear("el motivo dice qué error fue", "invalid_request_error" in respuesta, True)

# --- 5. expired para siempre: se reintenta 2 veces y después falla con el motivo ---
batches = BatchesFalsos(lambda cid, params, n: SimpleNamespace(type="expired"))
cliente, avisos = cliente_con(batches, carpeta / "cinco")
respuesta = preguntar_o_motivo(cliente, "A")
chequear("expired: 1 intento + 2 reintentos = 3 batches", len(batches.creados), 3)
chequear("después falla diciendo cuántos reintentos hizo", "después de 2 reintento(s)" in respuesta, True)

# --- 6. Un resultado que no vuelve en el archivo también se reintenta ---
batches = BatchesFalsos(lambda cid, params, n: None if n == 1 else exito(params["messages"][0]["content"]))
cliente, avisos = cliente_con(batches, carpeta / "seis")
chequear("sin resultado -> se reintenta y termina bien", preguntar_o_motivo(cliente, "A"), "respuesta a A")

# --- 7. Una tanda lenta no traba a las demás: pasado espera_juntar se manda con los que hay ---
batches = BatchesFalsos()
cliente, avisos = cliente_con(batches, carpeta / "siete", espera_juntar=0.3)
listo = threading.Event()
def tanda_lenta():
    with cliente.conversacion():
        listo.wait(5)  # todavía "pensando" su primer pedido
with ThreadPoolExecutor(2) as hilos:
    lenta = hilos.submit(tanda_lenta)
    time.sleep(0.05)
    inicio = time.monotonic()
    rapida = hilos.submit(lambda: preguntar(cliente, "A")).result(timeout=5)
    tardo = time.monotonic() - inicio
    listo.set()
chequear("la rápida no espera a la lenta para siempre", (rapida, tardo < 3), ("respuesta a A", True))

# --- 8. Si el batch entero no se puede crear, cada fichador recibe el motivo ---
class BatchesRotos(BatchesFalsos):
    def create(self, requests):
        raise ConnectionError("sin red")

cliente, avisos = cliente_con(BatchesRotos(), carpeta / "ocho")
respuesta = preguntar_o_motivo(cliente, "A")
chequear("si create falla, la tanda falla con el motivo", "sin red" in respuesta, True)

# --- 9. cancelar(): cancela el batch en curso y no reencola nada ---
class BatchesQueNoTerminan(BatchesFalsos):
    def retrieve(self, batch_id):
        estado = "ended" if batch_id in self.cancelados else "in_progress"
        return SimpleNamespace(processing_status=estado, request_counts=SimpleNamespace(processing=1))

batches = BatchesQueNoTerminan(lambda cid, params, n: SimpleNamespace(type="canceled"))
cliente, avisos = cliente_con(batches, carpeta / "nueve")
with ThreadPoolExecutor(1) as hilos:
    futuro = hilos.submit(preguntar_o_motivo, cliente, "A")
    while not batches.creados:
        time.sleep(0.01)
    time.sleep(0.05)
    cliente.cancelar()
    respuesta = futuro.result(timeout=5)
chequear("cancelar avisa a la API con el id del batch", batches.cancelados, ["msgbatch_1"])
chequear("lo cancelado falla y no se reencola", (respuesta.startswith("FALLÓ"), len(batches.creados)), (True, 1))
chequear("después de cancelar, un pedido nuevo falla enseguida",
         preguntar_o_motivo(cliente, "B").startswith("FALLÓ"), True)

print()
print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
