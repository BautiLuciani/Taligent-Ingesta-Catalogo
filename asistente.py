"""El asistente de consultas (semana 6, paso 3): un agente conversacional que contesta sobre lo que generó el sistema.

Uso:
    python asistente.py                                   # conversación: preguntás, contesta, y sigue el hilo
    python asistente.py "¿Por qué AN-1103 va a revisión?"  # una sola pregunta

Cómo está armado (todo reusado de las semanas anteriores, nada nuevo en el servidor salvo sus 4 tools):
  - El loop del M2 (agente.correr_loop): el modelo pide tools, el código las ejecuta, hasta que contesta.
  - Tools de SOLO lectura, por permisos (permisos.py, rol "asistente"): no puede tocar una ficha aunque se lo pidan.
  - System = prompt_asistente.md + el criterio de revisión (el MISMO prompt MCP que usa el fichador) + el estándar.
    Con caché (M6): system + tools se mandan una vez y después se leen del caché.
  - Memoria in-context: cada pregunta se suma al historial; así "¿y cuál es el más caro?" sabe de qué se habla.
    Cada vuelta reenvía la conversación entera: por eso se mide el costo de cada pregunta y se cachea el historial.
  - Respuesta con forma fija (output_config.format, M6 §2.1): {texto, valor, items, fuentes} como la guía.
  - El código verifica la respuesta (el "hook al terminar" del asistente): cada fuente y cada producto citado tienen
    que haber salido de una tool en ESTA conversación. Si no, se le devuelve el motivo una vez; si insiste, lo que no
    se puede verificar se saca y se avisa. Nada inventado llega a la persona.
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from agente import (CARPETA_PROYECTO, CARPETA_TRAZAS, RUTA_SERVIDOR, anotar, armar_system_prompt, correr_loop,
                    obtener_tools)
from permisos import tools_permitidas

ROL = "asistente"
RUTA_PROMPT_ASISTENTE = CARPETA_PROYECTO / "prompt_asistente.md"
TOPE_REINTENTOS = 1  # M4 §1.5: si la respuesta trae algo que no se puede verificar, se le explica UNA vez

# La forma de la respuesta final (la "Respuesta" de la guía, sección 4). Las fuentes van como casilleros fijos, igual
# que en la ficha estructurada de la semana 5: el modelo llena casilleros y el código arma {archivo, linea} /
# {archivo, pagina} / {archivo, hoja, fila}. Todo obligatorio y sin claves libres (lo que piden las salidas estructuradas).
FORMATO_RESPUESTA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "texto": {"type": "string"},
            "esta_en_lo_generado": {"type": "boolean"},
            "valor": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "null"}]},
            "items": {"type": "array", "items": {"type": "string"}},
            "fuentes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "archivo": {"type": "string"},
                        "tipo_ubicacion": {"type": "string", "enum": ["linea", "pagina", "hoja_fila"]},
                        "numero": {"type": "integer"},
                        "hoja": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": ["archivo", "tipo_ubicacion", "numero", "hoja"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["texto", "esta_en_lo_generado", "valor", "items", "fuentes"],
        "additionalProperties": False,
    },
}

PATRON_ITEM = re.compile(r"^P\d{2}:[A-Z0-9][A-Z0-9-]*$")


# --- De casilleros a la forma de la guía, y qué se vio en las tools ---

def fuente_de_casillero(casillero: dict) -> dict | None:
    """{archivo, tipo_ubicacion, numero, hoja} -> {archivo, linea} / {archivo, pagina} / {archivo, hoja, fila}.
    Un casillero incoherente (un Excel sin hoja) devuelve None: no se adivina."""
    archivo, tipo, numero = casillero.get("archivo"), casillero.get("tipo_ubicacion"), casillero.get("numero")
    if not archivo or not isinstance(numero, int):
        return None
    if tipo == "linea":
        return {"archivo": archivo, "linea": numero}
    if tipo == "pagina":
        return {"archivo": archivo, "pagina": numero}
    if tipo == "hoja_fila" and casillero.get("hoja"):
        return {"archivo": archivo, "hoja": casillero["hoja"], "fila": numero}
    return None


def clave(fuente: dict) -> tuple:
    """La fuente como tupla para comparar (misma regla que consultas.clave_fuente, sin importar el servidor)."""
    if "linea" in fuente:
        return (fuente["archivo"], "linea", int(fuente["linea"]))
    if "pagina" in fuente:
        return (fuente["archivo"], "pagina", int(fuente["pagina"]))
    return (fuente["archivo"], "hoja", fuente.get("hoja"), "fila", int(fuente["fila"]))


def lo_visto_en_las_tools(mensajes: list) -> tuple[set[tuple], set[str]]:
    """Todas las fuentes y todos los item_id que aparecieron en los tool_result de la conversación.

    Es la vara del hook: el modelo solo puede citar lo que una tool le mostró (no lo que "recuerda" ni lo que inventa).
    """
    fuentes, items = set(), set()

    def recorrer(valor):
        if isinstance(valor, dict):
            if "archivo" in valor and any(k in valor for k in ("linea", "pagina", "fila")):
                try:
                    fuentes.add(clave(valor))
                except (TypeError, ValueError):
                    pass
            for hijo in valor.values():
                recorrer(hijo)
        elif isinstance(valor, list):
            for hijo in valor:
                recorrer(hijo)
        elif isinstance(valor, str) and PATRON_ITEM.match(valor):
            items.add(valor)

    for mensaje in mensajes:
        if mensaje["role"] != "user" or isinstance(mensaje["content"], str):
            continue
        for bloque in mensaje["content"]:
            if isinstance(bloque, dict) and bloque.get("type") == "tool_result" and not bloque.get("is_error"):
                try:
                    recorrer(json.loads(bloque["content"]))
                except (json.JSONDecodeError, TypeError):
                    continue
    return fuentes, items


# --- El hook al terminar del asistente ---

def leer_respuesta(texto: str) -> dict | None:
    """El JSON de la respuesta final (con output_config.format viene entero; si no se puede leer, None)."""
    try:
        datos = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return None
    return datos if isinstance(datos, dict) else None


def problemas_de_la_respuesta(respuesta: dict, fuentes_vistas: set[tuple], items_vistos: set[str]) -> list[str]:
    """Lo que el código no puede verificar en la respuesta: fuentes o productos que ninguna tool mostró."""
    problemas = []
    for casillero in respuesta.get("fuentes", []):
        fuente = fuente_de_casillero(casillero)
        if fuente is None:
            problemas.append(f"La fuente {casillero} está mal armada (un Excel lleva hoja; una línea o página, no).")
        elif clave(fuente) not in fuentes_vistas:
            problemas.append(f"La fuente {fuente} no salió de ninguna tool en esta conversación: citá solo fuentes "
                             "que te devolvieron las tools, tal cual.")
    for item_id in respuesta.get("items", []):
        if item_id not in items_vistos:
            problemas.append(f"El producto {item_id!r} no salió de ninguna tool en esta conversación: consultalo o "
                             "sacalo (los item_id van como proveedor:código, por ejemplo P01:AN-1124).")
    return problemas


def limpiar_respuesta(respuesta: dict, fuentes_vistas: set[tuple], items_vistos: set[str]) -> tuple[dict, list[str]]:
    """Después del reintento: lo que siga sin verificar se saca (no llega a la persona) y queda el aviso."""
    fuentes, items, avisos = [], [], []
    for casillero in respuesta.get("fuentes", []):
        fuente = fuente_de_casillero(casillero)
        if fuente is not None and clave(fuente) in fuentes_vistas:
            if fuente not in fuentes:
                fuentes.append(fuente)
        else:
            avisos.append(f"se sacó una fuente que no se pudo verificar: {casillero}")
    for item_id in respuesta.get("items", []):
        if item_id in items_vistos:
            if item_id not in items:
                items.append(item_id)
        else:
            avisos.append(f"se sacó un producto que no se pudo verificar: {item_id}")
    return {**respuesta, "fuentes": fuentes, "items": items}, avisos


class HooksDelAsistente:
    """Los hooks del loop para el asistente: permisos antes de cada tool (candado 2) y nada después."""

    def __init__(self, permitidas: set[str]):
        self.permitidas = permitidas
        self.frenos: list[dict] = []

    def antes_de_tool(self, nombre: str, argumentos: dict) -> str | None:
        if nombre not in self.permitidas:
            self.frenos.append({"hook": "permisos", "tool": nombre})
            return (f"[permisos] La tool {nombre!r} no está permitida para el asistente. Solo podés usar: "
                    f"{', '.join(sorted(self.permitidas))}.")
        return None

    def despues_de_tool(self, nombre: str, argumentos: dict, resultado: dict) -> None:
        return None


# --- La conversación ---

class Conversacion:
    """Una conversación con el asistente: el historial (memoria in-context) y lo que va costando."""

    def __init__(self, cliente_claude, cliente_mcp: Client, modelo: str, system: str, tools: list[dict],
                 ruta_traza: Path):
        self.cliente_claude, self.cliente_mcp, self.modelo = cliente_claude, cliente_mcp, modelo
        self.system, self.tools, self.ruta_traza = system, tools, ruta_traza
        self.hooks = HooksDelAsistente({tool["name"] for tool in tools})
        self.mensajes: list = []
        self.total = {"preguntas": 0, "costo_usd": 0.0, "input_tokens": 0, "cache_leidos": 0, "output_tokens": 0}

    async def preguntar(self, pregunta: str) -> dict:
        """Una pregunta: corre el loop, verifica la respuesta y devuelve la Respuesta de la guía + costo y tiempo."""
        inicio = time.perf_counter()
        uso = {"vueltas": 0, "input_tokens": 0, "output_tokens": 0, "etiqueta": ""}
        anotar(self.ruta_traza, {"evento": "pregunta", "texto": pregunta})
        self.mensajes.append({"role": "user", "content": pregunta})
        avisos, reintentos = [], 0
        while True:
            como_termino, texto = await correr_loop(self.cliente_claude, self.cliente_mcp, self.modelo, self.system,
                                                    self.tools, self.mensajes, uso, self.ruta_traza, self.hooks,
                                                    formato=FORMATO_RESPUESTA)
            respuesta = leer_respuesta(texto) if como_termino == "end_turn" else None
            if respuesta is None:
                # cortada (max_tokens), negativa (refusal) o tope: no se lee a medias (M6 §5.5)
                respuesta = {"texto": f"No pude completar la respuesta ({como_termino}).", "esta_en_lo_generado": False,
                             "valor": None, "items": [], "fuentes": []}
                avisos.append(f"la respuesta terminó con {como_termino}")
                break
            fuentes_vistas, items_vistos = lo_visto_en_las_tools(self.mensajes)
            problemas = problemas_de_la_respuesta(respuesta, fuentes_vistas, items_vistos)
            if not problemas:
                respuesta = {**respuesta, "fuentes": [fuente_de_casillero(c) for c in respuesta["fuentes"]]}
                break
            anotar(self.ruta_traza, {"evento": "hook_al_terminar", "problemas": problemas, "reintento": reintentos})
            if reintentos >= TOPE_REINTENTOS:
                respuesta, avisos_limpieza = limpiar_respuesta(respuesta, fuentes_vistas, items_vistos)
                avisos += avisos_limpieza
                break
            reintentos += 1
            print(f"   ⛔ [hook al terminar] {problemas[0][:150]}")
            self.mensajes.append({"role": "user", "content": "[hook al terminar] Tu respuesta no se pudo verificar: "
                                  + " | ".join(problemas) + " Corregila y volvé a contestar."})

        segundos = time.perf_counter() - inicio
        self.total["preguntas"] += 1
        for campo in ("input_tokens", "output_tokens"):
            self.total[campo] += uso[campo]
        self.total["cache_leidos"] += uso.get("cache_leidos", 0)
        self.total["costo_usd"] += uso.get("costo_usd", 0.0)
        resultado = {
            "consulta": pregunta,
            "texto": respuesta["texto"],
            "valor": respuesta["valor"],
            "items": respuesta["items"],
            "fuentes": respuesta["fuentes"],
            "esta_en_lo_generado": respuesta["esta_en_lo_generado"],
            "avisos": avisos,
            "reintentos": reintentos,
            "vueltas": uso["vueltas"],
            "segundos": round(segundos, 1),
            "costo_usd": round(uso.get("costo_usd", 0.0), 6),
            "input_tokens": uso["input_tokens"],
            "cache_leidos": uso.get("cache_leidos", 0),
            "output_tokens": uso["output_tokens"],
        }
        anotar(self.ruta_traza, {"evento": "respuesta_final", **resultado})
        return resultado


def fuente_legible(fuente: dict) -> str:
    if "linea" in fuente:
        return f"{fuente['archivo']} · línea {fuente['linea']}"
    if "pagina" in fuente:
        return f"{fuente['archivo']} · pág. {fuente['pagina']}"
    return f"{fuente['archivo']} · hoja {fuente['hoja']}, fila {fuente['fila']}"


def mostrar(resultado: dict, total: dict) -> None:
    print()
    print(resultado["texto"])
    if resultado["items"]:
        print(f"\n  Productos: {', '.join(resultado['items'])}")
    for fuente in resultado["fuentes"]:
        print(f"  Fuente: {fuente_legible(fuente)}")
    for aviso in resultado["avisos"]:
        print(f"  ⚠ {aviso}")
    leido = 100 * resultado["cache_leidos"] / resultado["input_tokens"] if resultado["input_tokens"] else 0
    print(f"\n  [{resultado['vueltas']} vueltas · {resultado['segundos']} s · US$ {resultado['costo_usd']:.4f} esta "
          f"pregunta ({leido:.0f} % del caché) · US$ {total['costo_usd']:.4f} la conversación]")


async def abrir(cliente_claude, modelo: str, cliente_mcp: Client, ruta_traza: Path) -> Conversacion:
    """Arma lo fijo (system con el criterio y el estándar, tools del rol) y devuelve una conversación vacía."""
    system = await armar_system_prompt(cliente_mcp, RUTA_PROMPT_ASISTENTE)
    tools = await obtener_tools(cliente_mcp, ROL)
    if {tool["name"] for tool in tools} != tools_permitidas(ROL):
        raise ValueError("Las tools del asistente no coinciden con permisos.py")
    return Conversacion(cliente_claude, cliente_mcp, modelo, system, tools, ruta_traza)


async def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente_claude = anthropic.Anthropic()
    CARPETA_TRAZAS.mkdir(parents=True, exist_ok=True)
    ruta_traza = CARPETA_TRAZAS / f"asistente_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    una_sola = " ".join(sys.argv[1:]).strip()

    async with Client(PythonStdioTransport(str(RUTA_SERVIDOR))) as cliente_mcp:
        conversacion = await abrir(cliente_claude, modelo, cliente_mcp, ruta_traza)
        if una_sola:
            mostrar(await conversacion.preguntar(una_sola), conversacion.total)
            return
        print("Asistente de consultas. Escribí tu pregunta (Enter vacío para salir, /nueva para empezar de cero).")
        while True:
            pregunta = (await asyncio.to_thread(input, "\n> ")).strip()
            if not pregunta:
                break
            if pregunta == "/nueva":
                conversacion = await abrir(cliente_claude, modelo, cliente_mcp, ruta_traza)
                print("(conversación nueva)")
                continue
            mostrar(await conversacion.preguntar(pregunta), conversacion.total)
        print(f"\n{conversacion.total['preguntas']} preguntas · US$ {conversacion.total['costo_usd']:.4f} · "
              f"traza en {ruta_traza.relative_to(CARPETA_PROYECTO)}")


if __name__ == "__main__":
    asyncio.run(main())
