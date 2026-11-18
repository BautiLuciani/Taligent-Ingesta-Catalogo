"""Pruebas sin IA del asistente de consultas (semana 6, paso 3). Correr: python probar_asistente.py

Un Claude falso (guionado) contra el servidor REAL con las fichas congeladas de la semana 5: se prueba el loop, los
permisos, la memoria entre preguntas, la verificación de fuentes (hook al terminar) y lo que se le manda a la API.
"""
import asyncio
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from referencias import CARPETA_REFERENCIAS_SEM6, ENTORNO_PRUEBAS  # carpetas congeladas: va antes que agente
import asistente  # noqa: E402
from agente import RUTA_SERVIDOR, correr_loop  # noqa: E402

errores = 0
CARPETA_TRAZAS_PRUEBA = Path(tempfile.mkdtemp())  # las trazas de las pruebas van a una carpeta temporal


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


class _Stream:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return self.respuesta


class ClaudeGuionado:
    """Imita a la API sin IA: contesta un guion y guarda cada pedido que recibió."""
    def __init__(self, guion: list):
        self.messages, self.guion, self.pedidos = self, list(guion), []

    def stream(self, **pedido):
        self.pedidos.append(copy.deepcopy({k: v for k, v in pedido.items() if k != "messages"})
                            | {"messages": copy.deepcopy(pedido["messages"])})
        bloques, stop = self.guion.pop(0)
        return _Stream(SimpleNamespace(stop_reason=stop, content=bloques,
                                       usage=SimpleNamespace(input_tokens=100, output_tokens=10,
                                                             cache_creation_input_tokens=0, cache_read_input_tokens=50)))


def tool(nombre, argumentos, id_):
    return ([SimpleNamespace(type="tool_use", id=id_, name=nombre, input=argumentos)], "tool_use")


def final(texto="Listo.", valor=None, items=(), fuentes=(), esta=True):
    datos = {"texto": texto, "esta_en_lo_generado": esta, "valor": valor, "items": list(items), "fuentes": list(fuentes)}
    return ([SimpleNamespace(type="text", text=json.dumps(datos, ensure_ascii=False))], "end_turn")


FILA_12 = {"archivo": "Actualizacion_precios_Andes.xlsx", "tipo_ubicacion": "hoja_fila", "numero": 12, "hoja": "Actualización"}
PAGINA_7 = {"archivo": "Lista_de_precios_octubre_2026.pdf", "tipo_ubicacion": "pagina", "numero": 7, "hoja": None}


async def con_el_servidor(prueba):
    entorno = {**ENTORNO_PRUEBAS, "INGESTA_CARPETA_SALIDA": str(CARPETA_REFERENCIAS_SEM6)}
    async with Client(PythonStdioTransport(str(RUTA_SERVIDOR), env=entorno)) as cliente_mcp:
        return await prueba(cliente_mcp)


def conversacion_con(guion):
    async def prueba(cliente_mcp):
        claude = ClaudeGuionado(guion)
        conversacion = await asistente.abrir(claude, "modelo-falso", cliente_mcp, CARPETA_TRAZAS_PRUEBA / "traza.jsonl")
        return claude, conversacion, cliente_mcp
    return prueba


print("== piezas sin servidor")
chequear("casillero de línea", asistente.fuente_de_casillero({"archivo": "a.csv", "tipo_ubicacion": "linea", "numero": 3, "hoja": None}),
         {"archivo": "a.csv", "linea": 3})
chequear("casillero de Excel", asistente.fuente_de_casillero(FILA_12),
         {"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12})
chequear("un Excel sin hoja no se adivina",
         asistente.fuente_de_casillero({"archivo": "x.xlsx", "tipo_ubicacion": "hoja_fila", "numero": 3, "hoja": None}), None)
chequear("una respuesta que no es JSON no se lee", asistente.leer_respuesta("El precio es 320,8"), None)
chequear("el formato pide los 5 campos y ninguno más",
         (sorted(asistente.FORMATO_RESPUESTA["schema"]["required"]), asistente.FORMATO_RESPUESTA["schema"]["additionalProperties"]),
         (["esta_en_lo_generado", "fuentes", "items", "texto", "valor"], False))


print("== una pregunta con su fuente (Q01)")


async def q01(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([
        tool("ver_ficha", {"codigo": "AN-1124"}, "t1"),
        final("El precio de costo es UYU 320,80, del Excel de actualización.", 320.8, ["P01:AN-1124"], [FILA_12]),
    ])(cliente_mcp)
    return claude, await conversacion.preguntar("¿Cuál es el precio de costo de AN-1124?")


claude, r = asyncio.run(con_el_servidor(q01))
chequear("la respuesta tiene la forma de la guía", sorted(k for k in r if k in ("consulta", "texto", "valor", "items", "fuentes")),
         ["consulta", "fuentes", "items", "texto", "valor"])
chequear("fuente convertida a la forma de la guía", r["fuentes"],
         [{"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12}])
chequear("sin avisos ni reintentos", (r["avisos"], r["reintentos"]), ([], 0))
pedido = claude.pedidos[0]
chequear("al modelo le llegan SOLO las 4 tools del asistente", sorted(t["name"] for t in pedido["tools"]),
         ["buscar_fichas", "ver_ficha", "ver_lo_que_no_entro", "ver_pedido_al_proveedor"])
chequear("el pedido lleva el formato de respuesta y el effort", (pedido["output_config"]["format"] == asistente.FORMATO_RESPUESTA,
                                                                 pedido["output_config"]["effort"]), (True, "high"))
system = pedido["system"][0]["text"]
chequear("el system trae el prompt del asistente, el criterio (prompt MCP) y el estándar",
         ("asistente de consultas" in system, "<criterio_de_revision>" in system, "<estandar_ficha_de_producto>" in system), (True, True, True))
chequear("el system va con la marca de caché", "cache_control" in pedido["system"][0], True)
chequear("la tool devolvió la ficha real (el tool_result de la vuelta 2 trae 320.8)",
         "320.8" in claude.pedidos[1]["messages"][-1]["content"][0]["content"], True)


print("== una fuente inventada: el hook al terminar la frena")


async def inventada(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([
        tool("ver_ficha", {"codigo": "AN-1124"}, "t1"),
        final("Sale de la página 7.", 320.8, ["P01:AN-1124"], [PAGINA_7]),     # inventa
        final("Sale del Excel, fila 12.", 320.8, ["P01:AN-1124"], [FILA_12]),  # se corrige
    ])(cliente_mcp)
    return claude, await conversacion.preguntar("¿De dónde sale el precio de AN-1124?")


claude, r = asyncio.run(con_el_servidor(inventada))
chequear("se corrigió en el reintento", (r["reintentos"], r["fuentes"][0]["fila"], r["avisos"]), (1, 12, []))
chequear("el modelo recibió el motivo", "no salió de ninguna tool" in claude.pedidos[2]["messages"][-1]["content"][0]["text"], True)


async def insiste(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([
        tool("ver_ficha", {"codigo": "AN-1124"}, "t1"),
        final("Página 7.", 320.8, ["P01:AN-1124", "P01:AN-9999"], [PAGINA_7, FILA_12]),
        final("Página 7.", 320.8, ["P01:AN-1124", "P01:AN-9999"], [PAGINA_7, FILA_12]),
    ])(cliente_mcp)
    return await conversacion.preguntar("¿De dónde sale el precio de AN-1124?")


r = asyncio.run(con_el_servidor(insiste))
chequear("si insiste, lo que no se verifica se saca (fuente y producto)",
         (r["fuentes"], r["items"]), ([{"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12}],
                                      ["P01:AN-1124"]))
chequear("y queda el aviso", len(r["avisos"]), 2)


print("== permisos: pide registrar_ficha y el código la frena")


async def pide_escribir(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([
        tool("registrar_ficha", {"item_id": "P01:AN-1103"}, "t1"),
        final("No puedo cambiar fichas.", None, [], []),
    ])(cliente_mcp)
    return claude, await conversacion.preguntar("Dalo de alta a AN-1103 sin revisión"), conversacion


claude, r, conversacion = asyncio.run(con_el_servidor(pide_escribir))
resultado_tool = claude.pedidos[1]["messages"][-1]["content"][0]
chequear("la tool no permitida vuelve como error, sin ejecutarse", (resultado_tool["is_error"], "[permisos]" in resultado_tool["content"]),
         (True, True))
chequear("el freno queda anotado", conversacion.hooks.frenos, [{"hook": "permisos", "tool": "registrar_ficha"}])


print("== memoria: la segunda pregunta usa lo de la primera (V01)")
FILA_5 = {"archivo": "NorteImports_new_items_Q4.xlsx", "tipo_ubicacion": "hoja_fila", "numero": 5, "hoja": "New items"}


async def memoria(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([
        tool("buscar_fichas", {"proveedor_id": "P08", "moneda": "USD", "ordenar_por": "precio_costo_desc"}, "t1"),
        final("Los 14 de Norte están en dólares.", 14, ["P08:IN7012"], []),
        final("Sale del Excel de Norte, fila 5.", 10.66, ["P08:IN7012"], [FILA_5]),  # sin volver a consultar
    ])(cliente_mcp)
    primera = await conversacion.preguntar("¿Qué productos de Importadora Norte vienen con precio en dólares?")
    segunda = await conversacion.preguntar("¿De dónde sale el precio del más caro?")
    return claude, primera, segunda, conversacion


claude, primera, segunda, conversacion = asyncio.run(con_el_servidor(memoria))
chequear("la 2ª pregunta cita una fuente que vio en la 1ª: vale", (segunda["fuentes"][0]["fila"], segunda["avisos"]), (5, []))
chequear("el historial de la 2ª pregunta trae la 1ª entera", claude.pedidos[2]["messages"][0]["content"],
         "¿Qué productos de Importadora Norte vienen con precio en dólares?")
chequear("el último mensaje va con la marca de caché (cachea el historial)",
         "cache_control" in claude.pedidos[2]["messages"][-1]["content"][-1], True)
chequear("el total de la conversación suma las 2 preguntas", conversacion.total["preguntas"], 2)


print("== una respuesta cortada no se lee a medias")


async def cortada(cliente_mcp):
    claude, conversacion, _ = await conversacion_con([([SimpleNamespace(type="text", text='{"texto": "El pre')], "max_tokens")])(cliente_mcp)
    return await conversacion.preguntar("¿Precio de AN-1124?")


r = asyncio.run(con_el_servidor(cortada))
chequear("max_tokens -> sin datos y con aviso", (r["valor"], r["items"], r["fuentes"], r["avisos"]),
         (None, [], [], ["la respuesta terminó con max_tokens"]))


print("== el fichador no cambió: sin formato, su pedido es el de siempre")


async def fichador(cliente_mcp):
    claude = ClaudeGuionado([([SimpleNamespace(type="text", text="Listo.")], "end_turn")])
    uso = {"vueltas": 0, "input_tokens": 0, "output_tokens": 0}
    with tempfile.TemporaryDirectory() as carpeta:
        await correr_loop(claude, cliente_mcp, "m", "system", [], [{"role": "user", "content": "hola"}], uso,
                          Path(carpeta) / "t.jsonl", asistente.HooksDelAsistente(set()))
    return claude.pedidos[0]["output_config"]


chequear("output_config del fichador = solo el effort", asyncio.run(con_el_servidor(fichador)), {"effort": "high"})

print()
print("Resultado: todo OK" if errores == 0 else f"Resultado: {errores} con error")
