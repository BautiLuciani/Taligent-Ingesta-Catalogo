"""Experimento (semana 3, paso 9): ¿el detector habría encontrado SOLO el problema de la marca de Natural Vida?

En el paso 7 lo encontramos a mano: sin la marca fijada por el código, en 2 de 3 corridas el modelo dejó la marca
vacía y mandó los 14 productos a revisión. Acá se reproduce la situación de ANTES del arreglo, sin tocar el servidor:
un cliente que le saca a cada fila de Natural Vida la marca que hoy pone el código (calculado.marca y su fuente).
Sobre eso corre el detector tal cual lo usa el orquestador: cada tanda de P09 dos veces (A y B), 3 a la vez, y
combinar_versiones compara las dos versiones de cada producto.

Si el detector sirve, tiene que marcar como inestables los productos donde las dos corridas decidieron distinto
(esperado: ficha.marca y lo que arrastra, como el estado y los motivos). Si las dos corridas justo deciden igual,
no marca nada: el detector encuentra dudas, no errores que el modelo comete siempre igual (eso lo ve el evaluador).

Correr: python probar_detector.py      (~US$ 0,07: 2 tandas x 2 versiones; no toca resultados.json)
"""
import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import anthropic
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from agente import RUTA_SERVIDOR, armar_system_prompt, obtener_tools, procesar_tanda
from orquestador import combinar_versiones

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_EXPERIMENTO = CARPETA_PROYECTO / "salida" / "experimentos" / "detector_sin_marca"
TANDAS = [(0, 10), (10, 4)]  # las 2 tandas de Natural Vida: (desde, cantidad)


class ClienteSinMarca:
    """Envuelve al cliente MCP real: a cada fila de leer_archivo_proveedor le saca la marca que pone el código."""

    def __init__(self, cliente):
        self.cliente = cliente

    async def call_tool(self, nombre, argumentos, **opciones):
        resultado = await self.cliente.call_tool(nombre, argumentos, **opciones)
        if nombre != "leer_archivo_proveedor" or resultado.is_error:
            return resultado
        datos = json.loads(resultado.content[0].text)
        for fila in datos["filas"]:
            fila["calculado"].pop("marca", None)
            fila["calculado"].get("fuentes", {}).pop("marca", None)
            if not fila["calculado"].get("fuentes"):
                fila["calculado"].pop("fuentes", None)
        texto = json.dumps(datos, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=texto)], is_error=False, data=resultado.data)


def correr(cliente_claude, modelo: str, desde: int, cantidad: int, version: str) -> dict:
    """Una tanda de P09, sin la marca, en modo propuesta. Su propio hilo, loop y servidor (como un fichador)."""
    return asyncio.run(_correr(cliente_claude, modelo, desde, cantidad, version))


async def _correr(cliente_claude, modelo: str, desde: int, cantidad: int, version: str) -> dict:
    transporte = PythonStdioTransport(RUTA_SERVIDOR, env={"INGESTA_MODO_PROPUESTA": "1"})
    async with Client(transporte) as cliente_mcp:
        system = await armar_system_prompt(cliente_mcp)
        tools = await obtener_tools(cliente_mcp)
        return await procesar_tanda(cliente_claude, ClienteSinMarca(cliente_mcp), modelo, system, tools, "P09", desde,
                                    cantidad, CARPETA_EXPERIMENTO / f"traza_desde_{desde:03d}_{version}.jsonl",
                                    etiqueta=f"[P09 desde {desde} {version}] ")


def main():
    # Con argparse: así "--help" explica y NO arranca una corrida que se paga
    argparse.ArgumentParser(description="El detector sobre Natural Vida sin la marca fijada (~US$ 0,07).").parse_args()
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    CARPETA_EXPERIMENTO.mkdir(parents=True, exist_ok=True)
    cliente = anthropic.Anthropic()

    trabajos = [(desde, cantidad, version) for desde, cantidad in TANDAS for version in ("A", "B")]
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as hilos:
        corridas = list(hilos.map(lambda t: correr(cliente, modelo, *t), trabajos))
    segundos = time.perf_counter() - inicio

    de_a, de_b = {}, {}
    for (_, _, version), corrida in zip(trabajos, corridas):
        (de_a if version == "A" else de_b).update(corrida["propuestas"])
    _, inestables = combinar_versiones(de_a, de_b)
    costo = sum(c["costo_usd"] for c in corridas)

    print("\n=== Detector sobre Natural Vida SIN la marca fijada por el código (como antes del arreglo del paso 7)")
    for nombre, propuestas in (("A", de_a), ("B", de_b)):
        sin_marca = sum(1 for p in propuestas.values() if p["ficha"].get("marca") is None)
        a_revision = sum(1 for p in propuestas.values() if p["estado"] == "a_revision")
        print(f"Corrida {nombre}: {len(propuestas)} propuestas · {sin_marca} con la marca vacía · {a_revision} a revisión")
    print(f"\nInestables: {len(inestables)} de {len(set(de_a) | set(de_b))}")
    for inestable in inestables:
        print(f"   ≠ {inestable['item_id']}: {', '.join(inestable['campos'])}")
    print(f"({segundos:.0f} s, US$ {costo:.4f})")

    ruta = CARPETA_EXPERIMENTO / "resumen.json"
    ruta.write_text(json.dumps({"inestables": inestables, "version_a": de_a, "version_b": de_b, "costo_usd": costo},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resumen y trazas en salida/experimentos/{CARPETA_EXPERIMENTO.name}/")


if __name__ == "__main__":
    main()