"""Pruebas de los hooks (semana 4, paso 5) sin IA. Correr: python probar_hooks.py"""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from referencias import RUTA_RESULTADOS_REFERENCIA  # carpetas congeladas: va antes que agente/servidor
from agente import fichar_tanda  # noqa: E402
from hooks import (TOPE_FRENOS_AL_TERMINAR, HooksDeLaTanda, campos_sin_fuente, problema_del_gtin,
                   problemas_de_la_ficha)

# Las 133 fichas de la semana 3, congeladas: están bien (evaluador 63/63), así que ningún hook las puede frenar
RESULTADOS = json.loads(RUTA_RESULTADOS_REFERENCIA.read_text(encoding="utf-8"))
LAVANDINA = RESULTADOS["P07:LHS-206"]  # la ficha de LHS-206 de la presentación de la semana 2

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def ficha_con(**cambios) -> dict:
    """Una copia de la ficha buena de LHS-206 con algo cambiado."""
    return {**copy.deepcopy(LAVANDINA["ficha"]), **cambios}


print("--- 5A · lo más importante: ningún falso positivo en las 133 fichas buenas ---")
chequear("Las 133: ninguna con GTIN inválido ni valores fuera del vocabulario",
         [k for k, r in RESULTADOS.items() if problemas_de_la_ficha(r["ficha"])], [])
chequear("Las 133: ninguna con un campo completado sin fuente",
         [k for k, r in RESULTADOS.items() if campos_sin_fuente(r["ficha"], r["fuentes"])], [])

print("--- 5A · problema_del_gtin (el dígito verificador lo calcula cuentas.py) ---")
chequear("GTIN bueno (LHS-206)", problema_del_gtin("7790840033469"), None)
chequear("Un dígito cambiado: dice con qué tendría que terminar", problema_del_gtin("7790840033468"),
         "gtin 7790840033468 tiene el dígito verificador inválido (con esos 12 primeros dígitos, termina en 9)")
chequear("12 dígitos (un UPC sin el 0): no es un GTIN-13", "13 dígitos" in problema_del_gtin("779084003346"), True)
chequear("Con guiones: no está normalizado", "13 dígitos" in problema_del_gtin("779-0840-03346-9"), True)
chequear("null: vale (lo resuelve el criterio de revisión)", problema_del_gtin(None), None)

print("--- 5A · problemas_de_la_ficha (listas cerradas del vocabulario y la taxonomía) ---")
chequear("La ficha buena no tiene problemas", problemas_de_la_ficha(LAVANDINA["ficha"]), [])
chequear("Un tipo que no existe", problemas_de_la_ficha(ficha_con(tipo="LAVANDINA EN GEL")),
         ["tipo 'LAVANDINA EN GEL' no está en el vocabulario"])
chequear("Una unidad vieja (CC, en vez de ML)", problemas_de_la_ficha(ficha_con(unidad="CC")),
         ["unidad 'CC' no está en el vocabulario"])
chequear("Una categoría inventada", problemas_de_la_ficha(ficha_con(categoria="HOG-LIM-XXX")),
         ["categoria 'HOG-LIM-XXX' no está en la taxonomía"])
chequear("La condición de venta abreviada (VL)", problemas_de_la_ficha(ficha_con(condicion_venta="VL")),
         ["condicion_venta 'VL' no está en el vocabulario"])
chequear("Un peligro que no es de la tabla", problemas_de_la_ficha(ficha_con(peligro_deposito="inflamable")),
         ["peligro_deposito 'inflamable' no está en el vocabulario"])
chequear("Moneda en minúsculas", problemas_de_la_ficha(ficha_con(moneda="uyu")), ["moneda 'uyu' no está en el vocabulario"])
chequear("Varios problemas juntos: los dice todos", len(problemas_de_la_ficha(ficha_con(gtin="7790840033468", tipo="X"))), 2)
chequear("null en cualquier campo: vale", problemas_de_la_ficha(ficha_con(tipo=None, categoria=None, gtin=None)), [])

print("--- 5A · campos_sin_fuente ---")
fuentes = copy.deepcopy(LAVANDINA["fuentes"])
del fuentes["marca"]
chequear("Falta la fuente de marca", campos_sin_fuente(LAVANDINA["ficha"], fuentes), ["marca"])
fuentes = {**LAVANDINA["fuentes"], "tipo": {"archivo": "LHS_catalogo_nuevos_productos.pdf"}}
chequear("Una fuente sin página, hoja+fila ni línea no es una fuente", campos_sin_fuente(LAVANDINA["ficha"], fuentes), ["tipo"])
chequear("Las 3 formas de la guía valen (página, hoja+fila, línea)",
         campos_sin_fuente({"a": 1, "b": 2, "c": 3}, {"a": {"archivo": "x.pdf", "pagina": 1},
                                                     "b": {"archivo": "x.xlsx", "hoja": "Altas", "fila": 7},
                                                     "c": {"archivo": "x.csv", "linea": 4}}), [])
chequear("Un campo en null no necesita fuente", campos_sin_fuente({"gtin": None, "marca": "X"}, {"marca": {"archivo": "a", "linea": 2}}), [])
chequear("Sin fuentes (no vino el campo): todos los completados", campos_sin_fuente({"marca": "X", "tipo": "Y"}, None),
         ["marca", "tipo"])

print("--- 5A · HooksDeLaTanda: antes_de_tool ---")
item = "P07:LHS-206"
registro_bueno = {"item_id": item, "estado": LAVANDINA["estado"], "ficha": LAVANDINA["ficha"], "fuentes": LAVANDINA["fuentes"]}
registro_malo = {**registro_bueno, "ficha": ficha_con(gtin="7790840033468")}
hooks = HooksDeLaTanda([item])
chequear("Otra tool (leer, buscar): pasa siempre", hooks.antes_de_tool("buscar_por_gtin", {"gtin": "123"}), None)
chequear("registrar_ficha con una ficha buena: pasa", hooks.antes_de_tool("registrar_ficha", registro_bueno), None)
motivo = hooks.antes_de_tool("registrar_ficha", registro_malo)
chequear("Con el GTIN inválido: frena, con el ítem y el motivo", (motivo.startswith("[hook antes de registrar_ficha]"),
         item in motivo, "dígito verificador" in motivo), (True, True, True))
chequear("...y queda anotado el freno", hooks.frenos, [{"hook": "antes_de_tool", "item_id": item,
         "motivo": problema_del_gtin("7790840033468")}])

print("--- 5A · despues_de_tool: la memoria de la conversación ---")
hooks.despues_de_tool("registrar_ficha", registro_malo, {"is_error": True, "content": "No se guardó..."})
chequear("Un registro que el servidor rechazó no cuenta como aceptado", hooks.aceptadas, {})
hooks.despues_de_tool("registrar_ficha", registro_bueno, {"is_error": False, "content": json.dumps({"registrado": item})})
chequear("Uno aceptado sí (con lo que registró el modelo)", hooks.aceptadas[item]["ficha"]["gtin"], "7790840033469")
chequear("El freno del GTIN quedó corregido (terminó aceptado y la ficha final cumple)",
         [f["corregido"] for f in hooks.resumen_de_frenos()], [True])

print("--- 5A · al_terminar ---")
chequear("Todo registrado y con fuentes: lo deja terminar", hooks.al_terminar(), None)
dos = HooksDeLaTanda([item, "P07:LHS-209"])
dos.despues_de_tool("registrar_ficha", registro_bueno, {"is_error": False, "content": json.dumps({"registrado": item})})
motivo = dos.al_terminar()
chequear("Falta registrar uno: no lo deja terminar (el recordatorio de la semana 1, ahora como hook)",
         (motivo.startswith("[hook al terminar]"), "P07:LHS-209" in motivo), (True, True))

sin_marca = {**registro_bueno, "fuentes": {k: v for k, v in LAVANDINA["fuentes"].items() if k != "marca"}}
tres = HooksDeLaTanda([item])
tres.despues_de_tool("registrar_ficha", sin_marca, {"is_error": False, "content": json.dumps({"registrado": item})})
motivo = tres.al_terminar()
chequear("Un campo completado sin fuente: no lo deja terminar, dice cuál", "sin fuente: marca" in motivo, True)
chequear(f"Frena como mucho {TOPE_FRENOS_AL_TERMINAR} veces", [tres.al_terminar() is not None for _ in range(2)], [True, False])
chequear("Después del tope, esa ficha se descarta (no se acepta a medias)", item in tres.aceptadas, False)
chequear("...y queda anotado por qué", "descartada" in tres.frenos[-1]["motivo"], True)
chequear("Los frenos de esa ficha figuran sin corregir", {f["corregido"] for f in tres.resumen_de_frenos()}, {False})

cuatro = HooksDeLaTanda([item])
cuatro.despues_de_tool("registrar_ficha", sin_marca, {"is_error": False, "content": json.dumps({"registrado": item})})
cuatro.al_terminar()
cuatro.despues_de_tool("registrar_ficha", registro_bueno, {"is_error": False, "content": json.dumps({"registrado": item})})
chequear("Si el modelo la vuelve a registrar con la fuente: lo deja terminar", cuatro.al_terminar(), None)
chequear("...y el freno figura corregido", [f["corregido"] for f in cuatro.resumen_de_frenos()], [True])

print("--- 5B · enchufados en el loop: un Claude falso que se equivoca a propósito, contra el servidor real ---")
LITORAL = RESULTADOS["P03:LT-3303"]  # la primera de Litoral: el fichador de prueba hace la tanda desde 0, de 1 producto
BUENO = {clave: LITORAL[clave] for clave in ("item_id", "estado", "ficha", "fuentes", "categoria_decidida_por",
                                              "motivos_revision", "duplicado_de")}
GTIN = BUENO["ficha"]["gtin"]
GTIN_MALO = {**BUENO, "ficha": {**BUENO["ficha"], "gtin": GTIN[:-1] + str((int(GTIN[-1]) + 1) % 10)}}  # otro último dígito
SIN_MARCA = {**BUENO, "fuentes": {k: v for k, v in BUENO["fuentes"].items() if k != "marca"}}


class ClaudeGuionado:
    """Imita a la API sin IA: contesta un guion (una respuesta por llamada) y guarda los mensajes que recibió."""
    def __init__(self, guion: list):
        self.messages, self.guion, self.recibidos = self, list(guion), []

    def stream(self, **pedido):
        self.recibidos.append(copy.deepcopy(pedido["messages"]))
        bloques, stop = self.guion.pop(0)
        usage = SimpleNamespace(input_tokens=100, output_tokens=10)
        return _Stream(SimpleNamespace(stop_reason=stop, content=bloques, usage=usage))

    @staticmethod
    def registrar(argumentos, id_):
        return SimpleNamespace(type="tool_use", id=id_, name="registrar_ficha", input=argumentos)


class _Stream:
    """Lo mínimo de un stream: se usa con "with" y entrega la respuesta completa."""
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return self.respuesta


FIN = ([SimpleNamespace(type="text", text="Listo.")], "end_turn")
carpeta = Path(tempfile.mkdtemp())


def textos_de_usuario(mensajes: list) -> list[str]:
    """Lo que le llegó al modelo como usuario: los textos y los tool_result (contenido y si era error)."""
    salida = []
    for mensaje in mensajes:
        if mensaje["role"] != "user":
            continue
        contenido = mensaje["content"]
        if isinstance(contenido, str):
            salida.append(contenido)
        else:
            salida += [f"{'ERROR ' if b['is_error'] else ''}{b['content']}" for b in contenido]
    return salida


# A) Registra con el GTIN mal, el hook lo frena, lo corrige y termina
claude = ClaudeGuionado([([ClaudeGuionado.registrar(GTIN_MALO, "t1")], "tool_use"),
                         ([ClaudeGuionado.registrar(BUENO, "t2")], "tool_use"), FIN])
r = fichar_tanda(claude, "falso", "P03", 0, 1, carpeta / "a.jsonl")
devuelto = textos_de_usuario(claude.recibidos[1])[-1]
chequear("A · GTIN mal: el modelo recibe el freno como ERROR (la tool no se ejecutó)",
         (devuelto.startswith("ERROR [hook antes de registrar_ficha]"), "dígito verificador" in devuelto), (True, True))
chequear("A · después lo registra bien y queda aceptado (1/1)", (r["registrados"], r["como_termino"]), (1, "end_turn"))
chequear("A · la propuesta aceptada es la buena (el GTIN correcto)", r["propuestas"]["P03:LT-3303"]["ficha"]["gtin"],
         BUENO["ficha"]["gtin"])
chequear("A · el freno figura, con su hook y corregido",
         [(f["hook"], f["item_id"], f["corregido"]) for f in r["frenos"]], [("antes_de_tool", "P03:LT-3303", True)])
traza = [json.loads(linea) for linea in (carpeta / "a.jsonl").read_text(encoding="utf-8").splitlines()]
chequear("A · la traza tiene el evento del hook", [e["evento"] for e in traza].count("hook_antes_de_tool"), 1)

# B) Registra sin la fuente de marca, quiere terminar, el hook no lo deja, lo vuelve a registrar bien
claude = ClaudeGuionado([([ClaudeGuionado.registrar(SIN_MARCA, "t1")], "tool_use"), FIN,
                         ([ClaudeGuionado.registrar(BUENO, "t2")], "tool_use"), FIN])
r = fichar_tanda(claude, "falso", "P03", 0, 1, carpeta / "b.jsonl")
aviso = textos_de_usuario(claude.recibidos[2])[-1]
chequear("B · sin fuente: al terminar, recibe el motivo como mensaje nuevo", (aviso.startswith("[hook al terminar]"),
         "sin fuente: marca" in aviso), (True, True))
chequear("B · lo corrige y termina: aceptado con todas sus fuentes",
         (r["registrados"], "marca" in r["propuestas"]["P03:LT-3303"]["fuentes"]), (1, True))
chequear("B · el freno figura corregido", [(f["hook"], f["corregido"]) for f in r["frenos"]], [("al_terminar", True)])

# C) Nunca agrega la fuente: después de 2 avisos, la ficha se descarta (no entra a medias)
claude = ClaudeGuionado([([ClaudeGuionado.registrar(SIN_MARCA, "t1")], "tool_use"), FIN, FIN, FIN])
r = fichar_tanda(claude, "falso", "P03", 0, 1, carpeta / "c.jsonl")
chequear("C · insiste sin fuente: 2 avisos y se descarta (0/1, falta el ítem)",
         (r["registrados"], r["faltan"], len(claude.recibidos)), (0, ["P03:LT-3303"], 4))
chequear("C · no queda propuesta: el escritor verá que falta y no escribe el proveedor a medias", r["propuestas"], {})
chequear("C · los frenos figuran sin corregir, el último dice 'descartada'",
         (r["frenos"][-1]["corregido"], "descartada" in r["frenos"][-1]["motivo"]), (False, True))

# D) Todo bien de entrada: los hooks no se notan
claude = ClaudeGuionado([([ClaudeGuionado.registrar(BUENO, "t1")], "tool_use"), FIN])
r = fichar_tanda(claude, "falso", "P03", 0, 1, carpeta / "d.jsonl")
chequear("D · sin errores: 1/1, ningún freno, 2 llamadas (las de siempre)", (r["registrados"], r["frenos"], len(claude.recibidos)),
         (1, [], 2))
shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
