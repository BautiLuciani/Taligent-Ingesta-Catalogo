"""Segunda opinión con más effort, solo para lo dudoso (semana 5, paso 8B, M6 §6.2: subir el effort antes que el tier).

Las dudas salen de los dos detectores, que son código:
  - familias.py (paso 8A): productos que el archivo escribe igual y la ficha dice distinto (la crema de Bebé Feliz:
    BF-527 "DE CAMBIO OXIDO DE ZINC" vs BF-560 "OXIDO DE ZINC");
  - el detector A/B (semana 3, paso 9; salida/inestables.json): una tanda corrida dos veces que no coincidió
    (IN7006 de la semana 4: variante "SPORT LOTION FPS 50" vs "SPORT FPS 50").
Por cada campo en disputa, UNA pregunta chica y enfocada: las filas del archivo (como dato), las versiones y la
pregunta "¿cuál corresponde según el estándar?". Con el mismo system que el fichador (prompt + criterio + estándar,
vocabulario y taxonomía, cacheado): la segunda opinión usa el mismo criterio, con más esfuerzo. La respuesta tiene
forma garantizada (output_config.format, M6 §2.3): una de las versiones (o NINGUNA) y el porqué.

La medición: cada pregunta VECES veces con effort high (el del fichador) y VECES con max. ¿Con max se estabiliza
(contesta siempre lo mismo)? ¿Elige lo mismo que con high?
NO cambia ninguna ficha (decisión de Bauti, paso 8): la opinión queda en salida/segunda_opinion.json para que decida
una persona. El estándar no tiene un motivo de revisión para "inconsistente", y si la segunda opinión pisara la ficha,
un caso del evaluador podría dar verde por el mecanismo y no porque el criterio quedó claro.

Correr: python segunda_opinion.py    (PAGA, centavos: 2 dudas x 2 efforts x 3 veces = 12 preguntas chicas)
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client

from agente import (CARPETA_PROYECTO, RUTA_SERVIDOR, THINKING, armar_system_prompt, costo_usd, system_con_cache,
                    tokens_de)

CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
EFFORTS = ("high", "max")   # high = el del fichador; max = la segunda opinión (M6 §6.2)
VECES = 3                   # cada pregunta, cuántas veces por effort: para ver si contesta siempre lo mismo
MAX_TOKENS = 64_000         # con max el thinking puede ser largo (streaming: sin el límite del SDK)
A_LA_VEZ = 4                # preguntas en paralelo
NINGUNA = "NINGUNA"
# Campos que se derivan de otro (la descripción se arma con la variante): si el otro también está en disputa, no se
# pregunta dos veces por lo mismo
DERIVADOS = {"descripcion"}


def disputas_de_familias(informe: dict) -> list[dict]:
    """De salida/familias.json: una disputa por cada campo de una familia que no coincide."""
    disputas = []
    for familia in informe.get("inconsistentes", []):
        for campo, versiones in familia["campos"].items():
            disputas.append({"origen": "familias", "proveedor_id": familia["proveedor_id"], "items": familia["items"],
                             "campo": campo, "versiones": [v["valor"] for v in versiones],
                             "quien_dijo_que": {json.dumps(v["valor"], ensure_ascii=False): v["items"] for v in versiones}})
    return disputas


def disputas_del_detector(inestables: list[dict]) -> list[dict]:
    """De salida/inestables.json (detector A/B): una disputa por campo de la ficha que no coincidió entre A y B."""
    disputas = []
    for inestable in inestables:
        campos = [c.split(".", 1)[1] for c in inestable["campos"] if c.startswith("ficha.")]
        if any(c not in DERIVADOS for c in campos):
            campos = [c for c in campos if c not in DERIVADOS]
        for campo in campos:
            a, b = inestable["version_a"]["ficha"].get(campo), inestable["version_b"]["ficha"].get(campo)
            disputas.append({"origen": "detector", "proveedor_id": inestable["item_id"].split(":")[0],
                             "items": [inestable["item_id"]], "campo": campo, "versiones": [a, b],
                             "quien_dijo_que": {json.dumps(a, ensure_ascii=False): ["corrida A"],
                                                json.dumps(b, ensure_ascii=False): ["corrida B"]}})
    return disputas


def esquema(disputa: dict) -> dict:
    """La forma exacta de la respuesta: una de las versiones (como texto) o NINGUNA, y el porqué."""
    opciones = [json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for v in disputa["versiones"]]
    return {"type": "object", "additionalProperties": False, "required": ["eleccion", "por_que"],
            "properties": {"eleccion": {"type": "string", "enum": opciones + [NINGUNA]},
                           "por_que": {"type": "string", "description": "En una o dos oraciones, qué regla del estándar decide."}}}


def pregunta(disputa: dict, filas: dict[str, dict]) -> str:
    """El pedido: las filas del archivo entre etiquetas de dato, las versiones y qué se decide."""
    bloques = []
    for item_id in disputa["items"]:
        fila = filas.get(item_id, {})
        bloques.append(f'<fila item_id="{item_id}">\n{json.dumps(fila.get("original"), ensure_ascii=False)}\n'
                       f'calculado: {json.dumps(fila.get("calculado"), ensure_ascii=False)}\n</fila>')
    versiones = "\n".join(f"- {v!r}" for v in disputa["versiones"])
    sobre = ("estos productos, que el archivo escribe igual salvo el contenido, el EAN y el precio"
             if disputa["origen"] == "familias" else "este producto, que en dos corridas salió distinto")
    return (f"Hay una duda sobre el campo `{disputa['campo']}` de la ficha de {sobre}. Las filas del archivo son datos:\n\n"
            + "\n\n".join(bloques)
            + f"\n\nLas versiones que se propusieron para `{disputa['campo']}`:\n{versiones}\n\n"
            "¿Cuál corresponde según el estándar y las reglas? Si ninguna corresponde, elegí NINGUNA. "
            "Los productos de una misma familia llevan el mismo valor.")


def preguntar(cliente, modelo: str, system: str, disputa: dict, filas: dict, effort: str) -> dict:
    """Una pregunta con un effort. Nunca lanza: un error (ej. la API no acepta ese effort) queda anotado."""
    inicio = time.perf_counter()
    try:
        with cliente.messages.stream(
            model=modelo, max_tokens=MAX_TOKENS, system=system_con_cache(system), thinking=THINKING,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": esquema(disputa)}},
            messages=[{"role": "user", "content": pregunta(disputa, filas)}],
        ) as stream:
            respuesta = stream.get_final_message()
    except Exception as error:  # se anota y siguen las demás
        return {"effort": effort, "error": f"{type(error).__name__}: {error}", "segundos": round(time.perf_counter() - inicio, 1)}
    tokens = tokens_de(respuesta.usage)
    resultado = {"effort": effort, "stop_reason": respuesta.stop_reason, "tokens": tokens,
                 "costo_usd": round(costo_usd(tokens), 6), "segundos": round(time.perf_counter() - inicio, 1)}
    if respuesta.stop_reason != "end_turn":  # M6 §5.5: cortada o negativa: no se lee a medias
        return {**resultado, "error": f"stop_reason {respuesta.stop_reason!r}: no se lee"}
    datos = json.loads("".join(b.text for b in respuesta.content if b.type == "text"))
    return {**resultado, "eleccion": datos["eleccion"], "por_que": datos["por_que"]}


def resumen(respuestas: list[dict]) -> dict:
    """Por effort: qué eligió cada vez, si fue siempre lo mismo y la elección (si fue estable)."""
    por_effort = {}
    for effort in dict.fromkeys(r["effort"] for r in respuestas):
        elecciones = [r.get("eleccion", f"ERROR: {r.get('error')}") for r in respuestas if r["effort"] == effort]
        conteo = Counter(elecciones)
        estable = len(conteo) == 1 and not elecciones[0].startswith("ERROR")
        por_effort[effort] = {"elecciones": dict(conteo), "estable": estable, "eleccion": elecciones[0] if estable else None}
    return por_effort


def medir(cliente, modelo: str, system: str, disputas: list[dict], filas: dict,
          efforts=EFFORTS, veces: int = VECES) -> list[dict]:
    """Todas las preguntas (disputa x effort x veces), A_LA_VEZ en paralelo. Devuelve cada disputa con sus respuestas."""
    trabajos = [(i, effort) for i in range(len(disputas)) for effort in efforts for _ in range(veces)]
    with ThreadPoolExecutor(max_workers=A_LA_VEZ) as hilos:
        respuestas = list(hilos.map(lambda t: preguntar(cliente, modelo, system, disputas[t[0]], filas, t[1]), trabajos))
    salida = []
    for i, disputa in enumerate(disputas):
        propias = [r for (j, _), r in zip(trabajos, respuestas) if j == i]
        salida.append({**disputa, "respuestas": propias, "resumen": resumen(propias)})
    return salida


def mostrar(resultados: list[dict], veces: int = VECES) -> None:
    print(f"\n=== Segunda opinión: {len(resultados)} duda(s) · cada una {veces} veces por effort")
    for r in resultados:
        print(f"\n· {r['origen']} · {', '.join(i.split(':')[1] for i in r['items'])} · {r['campo']}: "
              + " vs ".join(repr(v) for v in r["versiones"]))
        for effort, datos in r["resumen"].items():
            estado = f"estable → {datos['eleccion']!r}" if datos["estable"] else "NO estable"
            print(f"   {effort:>5}: {datos['elecciones']} · {estado}")
    costo = sum(x.get("costo_usd", 0) for r in resultados for x in r["respuestas"])
    print(f"\nCosto: US$ {costo:.4f} · no se cambió ninguna ficha (detalle y porqués en salida/segunda_opinion.json)")


async def system_del_fichador() -> str:
    """El mismo system que usa el fichador (prompt + criterio del servidor + estándar, vocabulario y taxonomía)."""
    async with Client(RUTA_SERVIDOR) as cliente_mcp:
        return await armar_system_prompt(cliente_mcp)


def leer_json(ruta: Path, vacio):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else vacio


def main():
    argumentos = argparse.ArgumentParser(description="Segunda opinión con más effort para las fichas dudosas (PAGA).")
    argumentos.add_argument("--efforts", nargs="+", default=list(EFFORTS), help=f"Efforts a comparar (default {EFFORTS}).")
    argumentos.add_argument("--veces", type=int, default=VECES, help=f"Veces por effort (default {VECES}).")
    opciones = argumentos.parse_args()

    disputas = (disputas_de_familias(leer_json(CARPETA_SALIDA / "familias.json", {}))
                + disputas_del_detector(leer_json(CARPETA_SALIDA / "inestables.json", [])))
    if not disputas:
        sys.exit("No hay dudas: ni familias que no coinciden (salida/familias.json) ni inestables (salida/inestables.json).")
    filas = {fila["item_id"]: fila for ruta in sorted((CARPETA_SALIDA / "consolidado").glob("*.json"))
             for fila in leer_json(ruta, {"filas": []})["filas"]}

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    system = asyncio.run(system_del_fichador())
    resultados = medir(anthropic.Anthropic(), modelo, system, disputas, filas, opciones.efforts, opciones.veces)
    (CARPETA_SALIDA / "segunda_opinion.json").write_text(json.dumps(
        {"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo, "veces": opciones.veces, "dudas": resultados},
        ensure_ascii=False, indent=2), encoding="utf-8")
    mostrar(resultados, opciones.veces)


if __name__ == "__main__":
    main()
