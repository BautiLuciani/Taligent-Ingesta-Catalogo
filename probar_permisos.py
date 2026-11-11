"""Pruebas de los permisos por agente (semana 4, paso 6) sin IA, contra el servidor real. Correr: python probar_permisos.py"""
import asyncio
import copy
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from referencias import ENTORNO_PRUEBAS, RUTA_RESULTADOS_REFERENCIA  # carpetas congeladas: va antes que agente
import permisos  # noqa: E402
from agente import RUTA_SERVIDOR, armar_system_prompt, obtener_tools, procesar_tanda  # noqa: E402

RESULTADOS = json.loads(RUTA_RESULTADOS_REFERENCIA.read_text(encoding="utf-8"))
LITORAL = RESULTADOS["P03:LT-3303"]
REGISTRO = {clave: LITORAL[clave] for clave in ("item_id", "estado", "ficha", "fuentes", "categoria_decidida_por",
                                                 "motivos_revision", "duplicado_de")}

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


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


class ClaudeGuionado:
    """Imita a la API sin IA: contesta un guion y guarda las tools que le ofrecieron y los mensajes que recibió."""
    def __init__(self, guion: list):
        self.messages, self.guion, self.recibidos, self.tools_ofrecidas = self, list(guion), [], None

    def stream(self, **pedido):
        self.tools_ofrecidas = [tool["name"] for tool in pedido["tools"]]
        self.recibidos.append(copy.deepcopy(pedido["messages"]))
        bloques, stop = self.guion.pop(0) if self.guion else ([SimpleNamespace(type="text", text="Listo.")], "end_turn")
        return _Stream(SimpleNamespace(stop_reason=stop, content=bloques,
                                       usage=SimpleNamespace(input_tokens=100, output_tokens=10)))


def pedido(nombre, argumentos, id_):
    return SimpleNamespace(type="tool_use", id=id_, name=nombre, input=argumentos)


async def con_el_servidor(prueba):
    async with Client(PythonStdioTransport(RUTA_SERVIDOR, env={**ENTORNO_PRUEBAS, "INGESTA_MODO_PROPUESTA": "1"})) as cliente:
        return await prueba(cliente)


print("--- 6 · la tabla de permisos ---")
chequear("El fichador: sus 4 tools", sorted(permisos.tools_permitidas("fichador")),
         ["buscar_parecidos", "buscar_por_gtin", "leer_archivo_proveedor", "registrar_ficha"])
chequear("Cada agente con su forma de hacerlo cumplir y su porqué",
         all(p["como"] in ("servidor", "forzada", "sin_tools") and p["por_que"] for p in permisos.PERMISOS.values()), True)
chequear("Los que llaman al modelo con un formulario: solo ese formulario",
         (permisos.tools_permitidas("recepcionista"), permisos.tools_permitidas("extractor_pdf")),
         ({"entregar_receta"}, {"entregar_campos"}))
try:
    permisos.tools_permitidas("agente_sin_permisos")
    chequear("Un agente que no está en la tabla no tiene ninguna tool", "tuvo", "no tuvo")
except ValueError:
    chequear("Un agente que no está en la tabla no tiene ninguna tool (falla, no se le da todo)", True, True)

print("--- 6 · candado 1: el modelo solo VE sus tools ---")
permisos.PERMISOS["lector_de_prueba"] = {"tools": {"leer_archivo_proveedor", "buscar_por_gtin"}, "como": "servidor",
                                         "por_que": "Solo para las pruebas: un agente que solo puede leer."}
permisos.PERMISOS["mal_configurado"] = {"tools": {"leer_archivo_proveedor", "borrar_catalogo"}, "como": "servidor",
                                        "por_que": "Solo para las pruebas: nombra una tool que no existe."}


async def candado_1(cliente):
    fichador = [t["name"] for t in await obtener_tools(cliente)]
    lector = [t["name"] for t in await obtener_tools(cliente, "lector_de_prueba")]
    try:
        await obtener_tools(cliente, "mal_configurado")
        error = None
    except ValueError as excepcion:
        error = str(excepcion)
    return fichador, lector, error


fichador, lector, error = asyncio.run(con_el_servidor(candado_1))
chequear("El fichador recibe sus 4 tools", sorted(fichador), sorted(permisos.tools_permitidas("fichador")))
chequear("El de solo lectura recibe solo las 2 de lectura (registrar_ficha ni la ve)", sorted(lector),
         ["buscar_por_gtin", "leer_archivo_proveedor"])
chequear("Una lista con una tool que el servidor no tiene: no arranca, y dice cuál",
         error is not None and "borrar_catalogo" in error, True)

print("--- 6 · candado 2: si el modelo pide una tool que no es suya, el código la frena ---")
carpeta = Path(tempfile.mkdtemp())


async def tanda(cliente, rol: str, guion: list, nombre: str):
    claude = ClaudeGuionado(guion)
    tools = await obtener_tools(cliente, rol)
    system = await armar_system_prompt(cliente)
    resultado = await procesar_tanda(claude, cliente, "falso", system, tools, "P03", 0, 1, carpeta / f"{nombre}.jsonl")
    return claude, resultado


claude, r = asyncio.run(con_el_servidor(lambda c: tanda(
    c, "lector_de_prueba", [([pedido("registrar_ficha", REGISTRO, "t1")], "tool_use")], "lector")))
devuelto = [b["content"] for b in claude.recibidos[1][-1]["content"]][0]
chequear("Solo lectura pide registrar_ficha: recibe el freno de permisos como error",
         (claude.recibidos[1][-1]["content"][0]["is_error"], devuelto.startswith("[permisos]")), (True, True))
chequear("...y la ficha NO se registró (no llegó al servidor)", r["propuestas"], {})
chequear("...el freno figura con su hook", [f["hook"] for f in r["frenos"]][0], "permisos")

claude, r = asyncio.run(con_el_servidor(lambda c: tanda(
    c, "fichador", [([pedido("borrar_catalogo", {"confirmar": True}, "t1")], "tool_use"),
                    ([pedido("registrar_ficha", REGISTRO, "t2")], "tool_use")], "inventada")))
devuelto = claude.recibidos[1][-1]["content"][0]["content"]
chequear("El fichador pide una tool inventada (borrar_catalogo): frenada por permisos, no por el servidor",
         (devuelto.startswith("[permisos]"), "borrar_catalogo" in devuelto), (True, True))
chequear("...y sigue trabajando con lo suyo: registra su ficha (1/1)", (r["registrados"], r["como_termino"]), (1, "end_turn"))
chequear("El fichador sigue viendo sus 4 tools (nada de más)", sorted(claude.tools_ofrecidas),
         sorted(permisos.tools_permitidas("fichador")))
shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
