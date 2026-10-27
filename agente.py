"""Agente de ingesta: procesa los productos de un proveedor usando las tools del servidor MCP.

Correr: python agente.py P03   (o el proveedor que sea: P07...)
"""
import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client

CARPETA_PROYECTO = Path(__file__).parent
RUTA_SERVIDOR = CARPETA_PROYECTO / "servidor_mcp.py"
RUTA_PROMPT = CARPETA_PROYECTO / "prompt_sistema.md"

# Los 3 resources del servidor que van abajo de las instrucciones, cada uno entre etiquetas
RESOURCES_ESTANDAR = {
    "estandar_ficha_de_producto": "estandar://ficha_de_producto",
    "vocabulario": "estandar://vocabulario",
    "taxonomia": "estandar://taxonomia",
}

CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
CARPETA_TRAZAS = CARPETA_SALIDA / "trazas"

# Configuración del modelo (decisiones del paso 4)
EFFORT = "high"         # Haiku 5.5: "high" para seguir instrucciones al pie de la letra. Fijo en toda la conversación
MAX_TOKENS = 32_000     # tope de salida por respuesta (thinking + texto + tools). Con streaming no hay límite del SDK
THINKING = {"type": "adaptive", "display": "summarized"}  # que el thinking llegue como resumen legible (no cambia el costo)
TANDA = 10              # productos por conversación (decisión del paso 4: lejos de los 100.000 tokens)

# Topes de seguridad (M1): si algo se descontrola, el loop frena en vez de gastar sin fin
MAX_VUELTAS = 30                # vueltas del loop por conversación
TOPE_TOKENS_ENTRADA = 80_000    # si un pedido llega a esto, frenamos: lejos de los 100.000 (tarifa x5)
TIMEOUT_TOOL = 30               # segundos: si una tool se cuelga, el agente no queda trabado para siempre (M2)

PRECIO_INPUT = 0.10   # USD por millón de tokens de entrada (Haiku 5.5, módulo 6)
PRECIO_OUTPUT = 0.50  # USD por millón de tokens de salida (el thinking se cobra como salida)


async def armar_system_prompt(cliente_mcp: Client) -> str:
    """Instrucciones de prompt_sistema.md + los 3 resources del estándar, cada uno entre etiquetas."""
    partes = [RUTA_PROMPT.read_text(encoding="utf-8")]
    for etiqueta, uri in RESOURCES_ESTANDAR.items():
        texto = (await cliente_mcp.read_resource(uri))[0].text
        partes.append(f"<{etiqueta}>\n{texto}\n</{etiqueta}>")
    return "\n\n".join(partes)


async def obtener_tools(cliente_mcp: Client) -> list[dict]:
    """Pide las tools al servidor y las pasa al formato que espera la API de Claude."""
    return [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in await cliente_mcp.list_tools()
    ]


async def ejecutar_tool(cliente_mcp: Client, bloque) -> dict:
    """Ejecuta en el servidor la tool que pidió Haiku y arma el tool_result para devolverle.

    Nunca lanza una excepción: si algo falla, el error vuelve al modelo con is_error=True
    para que lo lea y corrija (M2: los errores se devuelven, no se lanzan).
    """
    try:
        resultado = await cliente_mcp.call_tool(
            bloque.name, bloque.input, timeout=TIMEOUT_TOOL, raise_on_error=False
        )
        texto = "\n".join(parte.text for parte in resultado.content if parte.type == "text")
        es_error = resultado.is_error
    except Exception as error:  # timeout, servidor caído, tool inexistente...
        texto = f"No se pudo ejecutar la tool {bloque.name!r}: {error}"
        es_error = True

    return {
        "type": "tool_result",
        "tool_use_id": bloque.id,  # el "ticket" que une este resultado con el pedido de Haiku
        "content": texto or "(la tool no devolvió contenido)",
        "is_error": es_error,
    }


def mensaje_de_tanda(proveedor_id: str, desde: int, cantidad: int) -> str:
    """El pedido que le hacemos al agente para una tanda."""
    return (f"Procesá los productos del proveedor {proveedor_id}: "
            f"desde la posición {desde}, {cantidad} productos.")


def anotar(ruta_traza: Path, evento: dict) -> None:
    """Agrega un evento a la traza (una línea JSON por evento). Sin traza, debuggear es adivinar (M2)."""
    with open(ruta_traza, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")


def resumir_bloques(contenido) -> list[dict]:
    """Pasa los bloques de una respuesta de Claude a algo legible para la traza."""
    resumen = []
    for bloque in contenido:
        if bloque.type == "thinking":
            resumen.append({"tipo": "thinking", "texto": bloque.thinking})
        elif bloque.type == "text":
            resumen.append({"tipo": "text", "texto": bloque.text})
        elif bloque.type == "tool_use":
            resumen.append({"tipo": "tool_use", "id": bloque.id, "tool": bloque.name, "input": bloque.input})
        else:
            resumen.append({"tipo": bloque.type})
    return resumen


async def correr_loop(cliente_claude, cliente_mcp: Client, modelo: str, system: str, tools: list[dict],
                      mensajes: list, uso: dict, ruta_traza: Path) -> tuple[str, str]:
    """El loop del M2: pedirle a Claude, ejecutar las tools que pida, devolverle los resultados... hasta que termine.

    Modifica `mensajes` (el historial) y `uso` (vueltas, tokens y los item_id que quedaron registrados).
    Devuelve (como_termino, texto_final). como_termino es "end_turn" si terminó bien.
    """
    for _ in range(MAX_VUELTAS):
        uso["vueltas"] += 1

        # Streaming (M1): con salidas largas el SDK lo exige. get_final_message() devuelve la respuesta completa
        with cliente_claude.messages.stream(
            model=modelo,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=mensajes,
            output_config={"effort": EFFORT},
            thinking=THINKING,
        ) as stream:
            respuesta = stream.get_final_message()

        uso["input_tokens"] += respuesta.usage.input_tokens
        uso["output_tokens"] += respuesta.usage.output_tokens
        pedidos = [bloque for bloque in respuesta.content if bloque.type == "tool_use"]
        print(f"   vuelta {uso['vueltas']:>2} · {respuesta.stop_reason:<9} · "
              f"{respuesta.usage.input_tokens:>6} in / {respuesta.usage.output_tokens:>5} out · "
              f"pidió: {', '.join(p.name for p in pedidos) or '-'}")
        anotar(ruta_traza, {
            "evento": "respuesta", "vuelta": uso["vueltas"], "stop_reason": respuesta.stop_reason,
            "input_tokens": respuesta.usage.input_tokens, "output_tokens": respuesta.usage.output_tokens,
            "bloques": resumir_bloques(respuesta.content),
        })

        # La respuesta va ENTERA al historial, con el thinking adentro, sin editar ni reordenar (M2)
        mensajes.append({"role": "assistant", "content": respuesta.content})
        texto_final = "".join(bloque.text for bloque in respuesta.content if bloque.type == "text")

        if respuesta.stop_reason == "end_turn":
            return "end_turn", texto_final

        if respuesta.stop_reason != "tool_use":
            # max_tokens, refusal, model_context_window_exceeded...: no seguimos a ciegas
            return respuesta.stop_reason, texto_final

        if respuesta.usage.input_tokens >= TOPE_TOKENS_ENTRADA:
            return "tope_de_tokens", texto_final

        # Haiku puede pedir varias tools juntas: las ejecutamos DE A UNA, en orden (un solo escritor)
        resultados = []
        for pedido in pedidos:
            resultado = await ejecutar_tool(cliente_mcp, pedido)
            resultados.append(resultado)
            if pedido.name == "registrar_ficha" and not resultado["is_error"]:
                uso["registrados"].add(json.loads(resultado["content"])["registrado"])
            anotar(ruta_traza, {"evento": "tool_result", "vuelta": uso["vueltas"], "tool": pedido.name, **resultado})

        # TODOS los resultados juntos, en UN solo mensaje user y sin texto agregado (M2 + doc de tools en paralelo)
        mensajes.append({"role": "user", "content": resultados})

    return "max_vueltas", ""


async def items_de_la_tanda(cliente_mcp: Client, proveedor_id: str, desde: int, cantidad: int) -> tuple[list[str], int]:
    """Qué productos tiene la tanda (y cuántos tiene el archivo en total), preguntándole al servidor desde el código."""
    datos = (await cliente_mcp.call_tool(
        "leer_archivo_proveedor", {"proveedor_id": proveedor_id, "desde": desde, "cantidad": cantidad}
    )).data
    return [fila["item_id"] for fila in datos["filas"]], datos["total"]


async def procesar_tanda(cliente_claude, cliente_mcp: Client, modelo: str, system: str, tools: list[dict],
                         proveedor_id: str, desde: int, cantidad: int, ruta_traza: Path) -> dict:
    """Una conversación nueva con el agente para procesar una tanda de productos.

    Al terminar, el CÓDIGO chequea que cada producto de la tanda haya quedado registrado.
    Si falta alguno, le manda UN solo recordatorio en la misma conversación (decisión del paso 4).
    """
    esperados, _ = await items_de_la_tanda(cliente_mcp, proveedor_id, desde, cantidad)
    mensajes = [{"role": "user", "content": mensaje_de_tanda(proveedor_id, desde, cantidad)}]
    uso = {"vueltas": 0, "input_tokens": 0, "output_tokens": 0, "registrados": set()}
    anotar(ruta_traza, {"evento": "inicio_tanda", "proveedor_id": proveedor_id, "desde": desde, "esperados": esperados})

    como_termino, texto_final = await correr_loop(
        cliente_claude, cliente_mcp, modelo, system, tools, mensajes, uso, ruta_traza
    )

    faltan = [item for item in esperados if item not in uso["registrados"]]
    if faltan and como_termino == "end_turn":
        print(f"   ⚠ faltó registrar {faltan}: le mandamos un recordatorio")
        # Mensaje NUEVO de usuario, después de que terminó el turno (nunca pegado a los tool_result)
        recordatorio = f"Te faltó registrar estos productos de la tanda: {', '.join(faltan)}. Registralos."
        mensajes.append({"role": "user", "content": recordatorio})
        anotar(ruta_traza, {"evento": "recordatorio", "faltan": faltan})
        como_termino, texto_final = await correr_loop(
            cliente_claude, cliente_mcp, modelo, system, tools, mensajes, uso, ruta_traza
        )
        faltan = [item for item in esperados if item not in uso["registrados"]]

    costo = (uso["input_tokens"] * PRECIO_INPUT + uso["output_tokens"] * PRECIO_OUTPUT) / 1_000_000
    resultado = {
        "como_termino": como_termino, "texto_final": texto_final, "vueltas": uso["vueltas"],
        "input_tokens": uso["input_tokens"], "output_tokens": uso["output_tokens"], "costo_usd": round(costo, 6),
        "esperados": len(esperados), "registrados": len(esperados) - len(faltan), "faltan": faltan,
    }
    anotar(ruta_traza, {"evento": "fin_tanda", **resultado})
    return resultado


def preparar_resultados(ruta_resultados: Path, proveedor_id: str) -> int:
    """Antes de una corrida: guarda una copia de resultados.json y le saca los ítems de ESTE proveedor.

    Cada corrida de un proveedor arranca limpia (decisión de la semana 1), pero sin borrar lo de los otros
    proveedores. Corre ANTES de levantar el servidor: mientras corre el agente, el único que escribe
    resultados.json sigue siendo registrar_ficha. Devuelve cuántos ítems se sacaron.
    """
    if not ruta_resultados.exists():
        return 0
    resultados = json.loads(ruta_resultados.read_text(encoding="utf-8"))
    shutil.copyfile(ruta_resultados, ruta_resultados.with_name("resultados_anterior.json"))  # no se pierde nada
    quedan = {item_id: r for item_id, r in resultados.items() if not item_id.startswith(f"{proveedor_id}:")}
    ruta_resultados.write_text(json.dumps(quedan, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(resultados) - len(quedan)


async def main():
    argumentos = argparse.ArgumentParser(description="Procesa con el agente los productos nuevos de un proveedor.")
    argumentos.add_argument("proveedor_id", help="Código del proveedor (ej. P03, P07). El servidor decide cuáles se permiten.")
    proveedor_id = argumentos.parse_args().proveedor_id

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente_claude = anthropic.Anthropic()  # toma ANTHROPIC_API_KEY del entorno

    sacados = preparar_resultados(CARPETA_SALIDA / "resultados.json", proveedor_id)
    if sacados:
        print(f"Se sacaron {sacados} ítems de {proveedor_id} de una corrida anterior (copia en resultados_anterior.json)")

    CARPETA_TRAZAS.mkdir(parents=True, exist_ok=True)
    ruta_traza = CARPETA_TRAZAS / f"traza_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    print(f"Proveedor {proveedor_id} · tandas de {TANDA} · effort {EFFORT} · traza: {ruta_traza.name}")

    inicio = time.perf_counter()  # reloj para medir cuánto tarda la corrida
    tandas = []
    async with Client(RUTA_SERVIDOR) as cliente_mcp:
        system = await armar_system_prompt(cliente_mcp)
        tools = await obtener_tools(cliente_mcp)
        _, total = await items_de_la_tanda(cliente_mcp, proveedor_id, 0, 1)

        for desde in range(0, total, TANDA):
            cantidad = min(TANDA, total - desde)
            print(f"\nTanda {len(tandas) + 1}: posiciones {desde} a {desde + cantidad - 1}")
            resultado = await procesar_tanda(
                cliente_claude, cliente_mcp, modelo, system, tools, proveedor_id, desde, cantidad, ruta_traza
            )
            tandas.append(resultado)
            print(f"   → {resultado['como_termino']} · {resultado['registrados']}/{resultado['esperados']} registrados"
                  f" · US$ {resultado['costo_usd']:.4f}")
    segundos = time.perf_counter() - inicio

    registrados = sum(t["registrados"] for t in tandas)
    costo_total = sum(t["costo_usd"] for t in tandas)

    # El reporte de la corrida queda guardado (y se sube a Git): costo por ficha y tiempo, para comparar corridas
    reporte = {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "proveedor_id": proveedor_id,
        "modelo": modelo,
        "effort": EFFORT,
        "tanda": TANDA,
        "productos": total,
        "registrados": registrados,
        "faltan": [item for t in tandas for item in t["faltan"]],
        "tandas_con_problemas": [t["como_termino"] for t in tandas if t["como_termino"] != "end_turn"],
        "segundos": round(segundos, 1),
        "vueltas": sum(t["vueltas"] for t in tandas),
        "input_tokens": sum(t["input_tokens"] for t in tandas),
        "output_tokens": sum(t["output_tokens"] for t in tandas),
        "costo_total_usd": round(costo_total, 4),
        "costo_por_ficha_usd": round(costo_total / max(registrados, 1), 5),
        "traza": ruta_traza.name,
        "por_tanda": [{k: v for k, v in t.items() if k != "texto_final"} for t in tandas],
    }
    ruta_reporte = CARPETA_SALIDA / f"corrida_{proveedor_id}.json"  # uno por proveedor: no se pisan
    ruta_reporte.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Resumen: {registrados}/{total} productos registrados en {segundos:.0f} s"
          f" · costo total US$ {costo_total:.4f} · US$ {reporte['costo_por_ficha_usd']:.5f} por ficha")
    print(f"Tokens: {reporte['input_tokens']} in / {reporte['output_tokens']} out · vueltas: {reporte['vueltas']}"
          f" · reporte: salida/{ruta_reporte.name}")
    if reporte["faltan"]:
        print(f"⚠ Quedaron sin registrar: {reporte['faltan']}")
    if reporte["tandas_con_problemas"]:
        print(f"⚠ Tandas que no terminaron bien: {reporte['tandas_con_problemas']}")

if __name__ == "__main__":
    asyncio.run(main())