"""Semana 5, paso 1 (C): experimento de la Batch API. No toca el sistema.

Preguntas: (1) ¿cuánto tarda de verdad un batch chico? (define si "un batch por vuelta" es viable);
(2) ¿los resultados vuelven en otro orden? (el join es el custom_id, nunca la posición, M6 §7.2);
(3) ¿se lee el caché dentro de un batch? (la doc: best-effort, 30-98 %; recomienda el TTL de 1 hora);
(4) un pedido roto a propósito: ¿lo rechaza al crear el batch o vuelve como "errored"?

5 pedidos con el prefijo REAL del fichador (tools + system), cada uno con otra pregunta corta, + 1 roto.
El batch vive en los servidores de Anthropic: si se corta el script, sigue. Se retoma con --id.

Correr: python probar_batch.py            (crea el batch y espera; paga ~US$ 0,003)
        python probar_batch.py --id msgbatch_...   (retoma uno ya creado, sin pagar de nuevo)
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from probar_cache import armar_prefijo

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_EXPERIMENTOS = CARPETA_PROYECTO / "salida" / "experimentos"
RUTA_ID = CARPETA_EXPERIMENTOS / "batch_sem5_id.txt"
RUTA_SALIDA = CARPETA_EXPERIMENTOS / "batch_sem5.json"

PEDIDOS_BUENOS = 5
ESPERA_ENTRE_CONSULTAS = 10   # segundos entre una consulta de estado y la siguiente
EFFORT = "low"                # la respuesta no importa; fijo en todos (si cambiara, cambia el caché)

# USD por millón de tokens con el descuento de batch (50 %). La escritura con TTL de 1 hora cuesta 2x el input
# (M6 §3.4: 0,20) -> 0,10 en batch. Calculado con los multiplicadores de la doc, no leído de una factura.
PRECIO_INPUT, PRECIO_ESCRITURA_1H, PRECIO_LECTURA, PRECIO_OUTPUT = 0.05, 0.10, 0.005, 0.25


def armar_pedidos(modelo: str, system: str, tools: list[dict]) -> list[dict]:
    """5 pedidos con el MISMO prefijo y distinta pregunta (como tandas distintas) + 1 roto a propósito."""
    system_cacheado = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    pedidos = [{
        "custom_id": f"pedido-{n}",  # el join con nuestros datos (solo letras, números, - y _)
        "params": {
            "model": modelo, "max_tokens": 2_000, "system": system_cacheado, "tools": tools,
            "tool_choice": {"type": "none"},
            "messages": [{"role": "user", "content": f"Prueba {n}: respondé solo con el número {n}."}],
            "output_config": {"effort": EFFORT},
        },
    } for n in range(1, PEDIDOS_BUENOS + 1)]
    roto = json.loads(json.dumps(pedidos[0]))  # copia independiente
    roto["custom_id"] = "pedido-roto"
    roto["params"]["max_tokens"] = 999_999     # más que el máximo de salida de Haiku 5.5 (128.000)
    return pedidos + [roto]


def crear_batch(cliente, pedidos: list[dict]) -> tuple[str, str]:
    """Crea el batch. Si la API rechaza TODO por el pedido roto, lo anota y lo crea sin él."""
    try:
        lote = cliente.messages.batches.create(requests=pedidos)
        return lote.id, "el pedido roto entró al batch (se valida adentro)"
    except anthropic.BadRequestError as error:
        print(f"La API rechazó el batch entero al crearlo (400): {error.message}\n→ Se crea sin el pedido roto.")
        lote = cliente.messages.batches.create(requests=pedidos[:-1])
        return lote.id, f"rechazado al crear: {error.message}"


def esperar(cliente, lote_id: str) -> float:
    """Consulta el estado hasta que termina (M6 §7.2: el consumo es asíncrono, no hay aviso). Devuelve los segundos."""
    inicio = time.perf_counter()
    while True:
        lote = cliente.messages.batches.retrieve(lote_id)
        c = lote.request_counts
        segundos = time.perf_counter() - inicio
        print(f"   {segundos:>6.0f} s · {lote.processing_status:<11} · procesando {c.processing} · ok {c.succeeded} · "
              f"errored {c.errored} · canceled {c.canceled} · expired {c.expired}", flush=True)
        if lote.processing_status == "ended":
            return segundos
        time.sleep(ESPERA_ENTRE_CONSULTAS)


def leer_resultados(cliente, lote_id: str) -> list[dict]:
    """Cada resultado con su custom_id, en el ORDEN EN QUE VUELVEN (para ver si coincide con el pedido)."""
    filas = []
    for resultado in cliente.messages.batches.results(lote_id):
        fila = {"custom_id": resultado.custom_id, "tipo": resultado.result.type}
        if resultado.result.type == "succeeded":
            mensaje = resultado.result.message
            u = mensaje.usage
            fila.update({
                "texto": "".join(b.text for b in mensaje.content if b.type == "text"),
                "sin_cache": u.input_tokens, "escritos": u.cache_creation_input_tokens or 0,
                "leidos": u.cache_read_input_tokens or 0, "output": u.output_tokens,
                "costo_usd": round((u.input_tokens * PRECIO_INPUT + (u.cache_creation_input_tokens or 0) * PRECIO_ESCRITURA_1H
                                    + (u.cache_read_input_tokens or 0) * PRECIO_LECTURA
                                    + u.output_tokens * PRECIO_OUTPUT) / 1_000_000, 6),
            })
        elif resultado.result.type == "errored":
            fila["error"] = f"{resultado.result.error.error.type}: {resultado.result.error.error.message}"
        filas.append(fila)
    return filas


def main():
    argumentos = argparse.ArgumentParser(description="Experimento de la Batch API (semana 5, paso 1C).")
    argumentos.add_argument("--id", help="id de un batch ya creado, para retomarlo sin crear otro")
    lote_id = argumentos.parse_args().id

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    CARPETA_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)

    como_entro_el_roto = "batch retomado con --id"
    if not lote_id:
        system, tools = asyncio.run(armar_prefijo())
        lote_id, como_entro_el_roto = crear_batch(cliente, armar_pedidos(modelo, system, tools))
        RUTA_ID.write_text(lote_id, encoding="utf-8")  # si se corta el script, se retoma con --id
    print(f"Batch {lote_id} (guardado en salida/experimentos/{RUTA_ID.name})\n")

    segundos = esperar(cliente, lote_id)
    filas = leer_resultados(cliente, lote_id)

    print(f"\nResultados en el orden en que volvieron ({segundos:.0f} s de espera):")
    for f in filas:
        if f["tipo"] == "succeeded":
            print(f"   {f['custom_id']:<12} succeeded · sin caché {f['sin_cache']:>4} · escritos {f['escritos']:>6} · "
                  f"leídos {f['leidos']:>6} · respondió {f['texto'].strip()!r} · US$ {f['costo_usd']:.5f}")
        else:
            print(f"   {f['custom_id']:<12} {f['tipo']} · {f.get('error', '')}")

    pedidos_en_orden = [f"pedido-{n}" for n in range(1, PEDIDOS_BUENOS + 1)]
    volvieron = [f["custom_id"] for f in filas if f["custom_id"] in pedidos_en_orden]
    leyeron = sum(1 for f in filas if f.get("leidos"))
    costo = sum(f.get("costo_usd", 0) for f in filas)
    print(f"\n¿Mismo orden que se pidió? {'sí' if volvieron == pedidos_en_orden else 'NO'} · "
          f"pedidos que leyeron del caché: {leyeron} de {sum(1 for f in filas if f['tipo'] == 'succeeded')} · "
          f"costo total US$ {costo:.5f}")
    print(f"Pedido roto: {como_entro_el_roto}")

    RUTA_SALIDA.write_text(json.dumps({
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo, "batch_id": lote_id,
        "segundos_de_espera": round(segundos), "pedido_roto": como_entro_el_roto, "resultados": filas,
        "mismo_orden": volvieron == pedidos_en_orden, "leyeron_cache": leyeron, "costo_usd": round(costo, 6),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()