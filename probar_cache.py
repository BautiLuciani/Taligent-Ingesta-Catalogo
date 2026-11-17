"""Semana 5, paso 1 (A): experimento de prompt caching. No toca el sistema (servidor, agente ni resultados).

Pregunta: si marcamos el final del system prompt con cache_control, ¿la API escribe el prefijo (tools + system)
en el caché la primera vez y lo LEE la segunda? ¿Y qué pasa si algo del prefijo cambia? (M6 §3 y §8)

Usa el prefijo REAL del fichador: las tools que recibe + prompt_sistema.md + criterio + los 3 resources.
Correr: python probar_cache.py   (paga ~US$ 0,005)
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client

from agente import RUTA_SERVIDOR, armar_system_prompt, obtener_tools

CARPETA_PROYECTO = Path(__file__).parent
RUTA_SALIDA = CARPETA_PROYECTO / "salida" / "experimentos" / "cache_sem5.json"

EFFORT = "low"        # la respuesta no importa; fijo en las 3 llamadas (si cambiara, también rompe el caché)
MAX_TOKENS = 2_000
PREGUNTA = "Esto es una prueba de conexión: respondé solo «OK», sin usar tools."

# USD por millón de tokens (Haiku 5.5, módulo 6 §3.4)
PRECIO_INPUT = 0.10            # entrada normal (lo que no está en caché)
PRECIO_ESCRITURA_CACHE = 0.125  # 1,25x: guardar el prefijo la primera vez
PRECIO_LECTURA_CACHE = 0.01     # 0,1x: leerlo las siguientes
PRECIO_OUTPUT = 0.50


def system_con_cache(texto: str) -> list[dict]:
    """El system como bloque con cache_control al final. La API arma el prompt en orden tools → system → messages,
    así que esta marca cachea las tools y el system JUNTOS (M6 §3.3)."""
    return [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]


def costo(usage) -> float:
    """Costo de una respuesta con las 4 tarifas. usage es la fuente de verdad (M6 §6.3)."""
    return (usage.input_tokens * PRECIO_INPUT
            + (usage.cache_creation_input_tokens or 0) * PRECIO_ESCRITURA_CACHE
            + (usage.cache_read_input_tokens or 0) * PRECIO_LECTURA_CACHE
            + usage.output_tokens * PRECIO_OUTPUT) / 1_000_000


def llamar(cliente, modelo: str, system: list[dict], tools: list[dict], nombre: str) -> dict:
    """Una llamada y lo que dice su usage sobre el caché."""
    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=tools,
        tool_choice={"type": "none"},  # igual en las 3: la pregunta no necesita tools
        messages=[{"role": "user", "content": PREGUNTA}],
        output_config={"effort": EFFORT},
    )
    u = respuesta.usage
    fila = {
        "llamada": nombre,
        "stop_reason": respuesta.stop_reason,
        "sin_cache": u.input_tokens,
        "escritos_en_cache": u.cache_creation_input_tokens or 0,
        "leidos_de_cache": u.cache_read_input_tokens or 0,
        "output": u.output_tokens,
        "costo_usd": round(costo(u), 6),
    }
    print(f"{nombre:<26} sin caché {fila['sin_cache']:>6} · escritos {fila['escritos_en_cache']:>6} · "
          f"leídos {fila['leidos_de_cache']:>6} · out {fila['output']:>4} · US$ {fila['costo_usd']:.5f}")
    return fila


async def armar_prefijo() -> tuple[str, list[dict]]:
    """El system y las tools tal como los arma el fichador (mismas funciones, no una copia)."""
    async with Client(RUTA_SERVIDOR) as cliente_mcp:
        return await armar_system_prompt(cliente_mcp), await obtener_tools(cliente_mcp)


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()

    system, tools = asyncio.run(armar_prefijo())

    # Medir antes de gastar (M3): count_tokens es gratis
    medidos = cliente.messages.count_tokens(
        model=modelo, system=system, tools=tools, messages=[{"role": "user", "content": PREGUNTA}]
    ).input_tokens
    print(f"Prefijo (tools + system) + pregunta: {medidos} tokens · mínimo cacheable de Haiku 5.5: 512\n")

    filas = [
        llamar(cliente, modelo, system_con_cache(system), tools, "1. primera vez"),
        llamar(cliente, modelo, system_con_cache(system), tools, "2. mismo prefijo"),
        # La trampa del M6 §8: algo dinámico ADENTRO del prefijo. No da error: simplemente no lee
        llamar(cliente, modelo, system_con_cache(f"Fecha y hora: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n{system}"),
               tools, "3. con la hora adelante"),
    ]

    # Qué habría costado la llamada 2 sin caché: todos sus tokens de entrada a tarifa normal
    segunda = filas[1]
    entrada_total = segunda["sin_cache"] + segunda["escritos_en_cache"] + segunda["leidos_de_cache"]
    sin_cache_usd = (entrada_total * PRECIO_INPUT + segunda["output"] * PRECIO_OUTPUT) / 1_000_000
    print(f"\nLlamada 2 sin caché habría costado US$ {sin_cache_usd:.5f} · con caché US$ {segunda['costo_usd']:.5f}")

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_text(json.dumps({
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo, "tokens_medidos": medidos,
        "llamadas": filas, "llamada_2_sin_cache_usd": round(sin_cache_usd, 6),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()