"""Prueba segunda_opinion.py SIN IA: dudas armadas como las reales y un Claude falso que contesta lo que se le pide.
Correr: python probar_segunda_opinion.py"""
import json
import threading
from types import SimpleNamespace

from segunda_opinion import (NINGUNA, disputas_de_familias, disputas_del_detector, esquema, medir, pregunta, preguntar,
                             resumen)

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


FAMILIAS = {"inconsistentes": [{"proveedor_id": "P06", "en_el_archivo": ["CREMA DE CAMBIO PEQUEÑOS PASOS OXIDO DE ZINC"],
                                "items": ["P06:BF-527", "P06:BF-560"],
                                "campos": {"variante": [{"valor": "DE CAMBIO OXIDO DE ZINC", "items": ["P06:BF-527"]},
                                                        {"valor": "OXIDO DE ZINC", "items": ["P06:BF-560"]}]}}]}
INESTABLES = [{"item_id": "P08:IN7006", "campos": ["ficha.descripcion", "ficha.variante"],
               "version_a": {"ficha": {"variante": "SPORT LOTION FPS 50", "descripcion": "PROTECTOR ... LOTION ..."}},
               "version_b": {"ficha": {"variante": "SPORT FPS 50", "descripcion": "PROTECTOR ..."}}}]
FILAS = {"P06:BF-527": {"original": {"Producto": "Crema de cambio Pequeños Pasos Oxido De Zinc", "Cantidad": "120 g"},
                        "calculado": {"contenido": 120, "unidad": "G"}},
         "P06:BF-560": {"original": {"Producto": "Crema de cambio Pequeños Pasos Oxido De Zinc", "Cantidad": "60 g"},
                        "calculado": {"contenido": 60, "unidad": "G"}}}

print("--- de los detectores a las dudas ---")
de_familias = disputas_de_familias(FAMILIAS)
chequear("familias.json: una duda por campo, con las versiones y quién dijo qué",
         [(d["origen"], d["items"], d["campo"], d["versiones"]) for d in de_familias],
         [("familias", ["P06:BF-527", "P06:BF-560"], "variante", ["DE CAMBIO OXIDO DE ZINC", "OXIDO DE ZINC"])])
del_detector = disputas_del_detector(INESTABLES)
chequear("inestables.json: la descripción se arma con la variante -> se pregunta solo por la variante",
         [(d["origen"], d["items"], d["campo"], d["versiones"]) for d in del_detector],
         [("detector", ["P08:IN7006"], "variante", ["SPORT LOTION FPS 50", "SPORT FPS 50"])])
solo_descripcion = [{**INESTABLES[0], "campos": ["ficha.descripcion"]}]
chequear("Si lo único que difiere es la descripción, se pregunta por la descripción",
         [d["campo"] for d in disputas_del_detector(solo_descripcion)], ["descripcion"])
chequear("Sin dudas: listas vacías", (disputas_de_familias({}), disputas_del_detector([])), ([], []))

print("--- la pregunta y la forma de la respuesta ---")
forma = esquema(de_familias[0])
chequear("La elección solo puede ser una de las versiones o NINGUNA (forma garantizada)",
         forma["properties"]["eleccion"]["enum"], ["DE CAMBIO OXIDO DE ZINC", "OXIDO DE ZINC", NINGUNA])
chequear("...con el porqué obligatorio y nada más", (forma["required"], forma["additionalProperties"]), (["eleccion", "por_que"], False))
texto = pregunta(de_familias[0], FILAS)
chequear("La pregunta lleva las dos filas como dato, las versiones y la regla de la familia",
         all(t in texto for t in ('<fila item_id="P06:BF-527">', '<fila item_id="P06:BF-560">', "'OXIDO DE ZINC'",
                                  "misma familia llevan el mismo valor")), True)
chequear("Para el detector, dice que salió distinto en dos corridas", "dos corridas" in pregunta(del_detector[0], {}), True)


class Contexto:
    """Lo que devuelve messages.stream(): se usa con "with" y get_final_message() da la respuesta."""

    def __init__(self, mensaje):
        self.mensaje = mensaje

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return self.mensaje


class ClaudeFalso:
    """Contesta según el effort (rotando la lista de elecciones); guarda lo que recibió."""

    def __init__(self, por_effort, stop_reason="end_turn", explota=None):
        self.por_effort, self.stop_reason, self.explota = por_effort, stop_reason, explota
        self.pedidos, self.lock, self.messages = [], threading.Lock(), self

    def stream(self, **pedido):
        with self.lock:
            self.pedidos.append(pedido)
            n = len(self.pedidos)
        effort = pedido["output_config"]["effort"]
        if self.explota == effort:
            raise RuntimeError("400: effort no soportado")
        eleccion = self.por_effort[effort][(n - 1) % len(self.por_effort[effort])]
        return Contexto(SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking="..."),
                     SimpleNamespace(type="text", text=json.dumps({"eleccion": eleccion, "por_que": "regla"}))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0,
                                  cache_read_input_tokens=15000)))


print("--- preguntar ---")
falso = ClaudeFalso({"max": ["OXIDO DE ZINC"]})
r = preguntar(falso, "m", "SYSTEM", de_familias[0], FILAS, "max")
chequear("Lee la elección y el porqué, con el costo", (r["eleccion"], r["por_que"], r["costo_usd"] > 0), ("OXIDO DE ZINC", "regla", True))
pedido = falso.pedidos[0]
chequear("Va con el effort pedido, la forma garantizada y el system cacheado",
         (pedido["output_config"]["effort"], pedido["output_config"]["format"]["type"], "cache_control" in pedido["system"][-1]),
         ("max", "json_schema", True))
cortada = preguntar(ClaudeFalso({"max": ["OXIDO DE ZINC"]}, stop_reason="max_tokens"), "m", "S", de_familias[0], FILAS, "max")
chequear("Cortada (max_tokens): no se lee a medias, queda el motivo", ("eleccion" in cortada, "max_tokens" in cortada["error"]), (False, True))
error = preguntar(ClaudeFalso({}, explota="max"), "m", "S", de_familias[0], FILAS, "max")
chequear("Si la API rechaza el pedido, no se cae: queda el error", "effort no soportado" in error["error"], True)

print("--- resumen y medir: ¿se estabiliza? ---")
chequear("3 iguales: estable, con la elección", resumen([{"effort": "max", "eleccion": "A"}] * 3),
         {"max": {"elecciones": {"A": 3}, "estable": True, "eleccion": "A"}})
chequear("2 a 1: no estable", resumen([{"effort": "high", "eleccion": "A"}, {"effort": "high", "eleccion": "B"},
                                       {"effort": "high", "eleccion": "A"}])["high"]["estable"], False)
chequear("Con un error no cuenta como estable", resumen([{"effort": "max", "error": "x"}] * 3)["max"]["estable"], False)
falso = ClaudeFalso({"high": ["DE CAMBIO OXIDO DE ZINC", "OXIDO DE ZINC"], "max": ["OXIDO DE ZINC"]})
resultados = medir(falso, "m", "S", de_familias + del_detector, FILAS, ("high", "max"), 3)
chequear("2 dudas x 2 efforts x 3 veces = 12 preguntas", len(falso.pedidos), 12)
chequear("Cada duda con sus 6 respuestas", [len(r["respuestas"]) for r in resultados], [6, 6])
chequear("max (siempre lo mismo) estable", resultados[0]["resumen"]["max"]["estable"], True)
chequear("Las dudas guardan las versiones originales (no se pisa nada)", resultados[0]["versiones"],
         ["DE CAMBIO OXIDO DE ZINC", "OXIDO DE ZINC"])

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
