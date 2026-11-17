"""Semana 5, paso 2C: ¿compilan con strict las tools REALES del fichador? No toca el sistema.

Lo que ya sabemos (paso 1): el formulario de la ficha (diseño C) compila. Lo que falta saber: las tools tal como las
arma el servidor después de la 2B, con lo que el paso 1 no probó: el pattern del GTIN (^\\d{13}$), minimum/maximum,
minLength, el maxLength de la explicación de la categoría, los titles que agrega pydantic y 2 parámetros opcionales
con valor por defecto (desde y cantidad de leer_archivo_proveedor). Y el tope de uniones suma TODAS las tools strict
del pedido.

Dos variantes a la vez: las 4 tools en strict, o solo registrar_ficha (lo que pide la guía). Pedido mínimo con la tool
forzada: lo que importa es si compila y si lo que devuelve entra en los modelos del servidor.
Correr: python probar_strict_tools.py   (paga < US$ 0,003; lo que no compila no se cobra)
"""
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client
from pydantic import ValidationError

from agente import RUTA_SERVIDOR, obtener_tools
from ficha_estructurada import Ficha, FuenteDeCampo
from probar_strict import contar

CARPETA_PROYECTO = Path(__file__).parent
RUTA_SALIDA = CARPETA_PROYECTO / "salida" / "experimentos" / "strict_tools_sem5.json"
PEDIDO = "Es una prueba: registrá un producto de ejemplo cualquiera con registrar_ficha."
TIMEOUT_NUESTRO = 600


def con_strict(tools: list[dict], cuales: set[str]) -> list[dict]:
    """Copia de las tools con strict: true en las que se nombran."""
    return [{**tool, "strict": True} if tool["name"] in cuales else dict(tool) for tool in tools]


def problemas_con_los_modelos(entrada: dict) -> list[str]:
    """¿Lo que devolvió la API entra en los modelos del servidor? (strict y pydantic tienen que decir lo mismo)"""
    problemas = []
    try:
        Ficha.model_validate(entrada.get("ficha"))
    except ValidationError as error:
        problemas.append(f"ficha: {error.error_count()} errores")
    for fuente in entrada.get("fuentes", []):
        try:
            FuenteDeCampo.model_validate(fuente)
        except ValidationError as error:
            problemas.append(f"fuente: {error.error_count()} errores")
    return problemas


def probar(cliente, modelo: str, nombre: str, tools: list[dict]) -> dict:
    """Una llamada mínima con registrar_ficha forzada. Nunca lanza: cualquier error queda anotado."""
    cuenta = {"uniones": 0, "opcionales": 0}
    for tool in tools:
        if tool.get("strict"):
            for clave, valor in contar(tool["input_schema"]).items():
                cuenta[clave] += valor
    inicio = time.perf_counter()
    try:
        respuesta = cliente.messages.create(
            model=modelo, max_tokens=3_000, tools=tools,
            tool_choice={"type": "tool", "name": "registrar_ficha"},  # forzada: sin thinking, barata
            messages=[{"role": "user", "content": PEDIDO}], output_config={"effort": "low"},
        )
        entrada = next((b.input for b in respuesta.content if b.type == "tool_use"), None)
        resultado = {"compilo": True, "input": entrada,
                     "problemas_con_los_modelos": problemas_con_los_modelos(entrada) if entrada else ["sin tool_use"]}
    except anthropic.BadRequestError as error:
        resultado = {"compilo": False, "error": f"400 de la API: {error.message}"}
    except anthropic.APITimeoutError:
        resultado = {"compilo": False, "error": f"sin respuesta en {TIMEOUT_NUESTRO} s (timeout nuestro)"}
    except Exception as error:
        resultado = {"compilo": False, "error": f"{type(error).__name__}: {error}"}
    return {"variante": nombre, "strict_en": sorted(t["name"] for t in tools if t.get("strict")), **cuenta,
            "segundos": round(time.perf_counter() - inicio, 1), **resultado}


async def tools_del_fichador() -> list[dict]:
    async with Client(RUTA_SERVIDOR) as cliente_mcp:
        return await obtener_tools(cliente_mcp)  # las mismas que recibe el fichador (permisos incluidos)


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic(timeout=TIMEOUT_NUESTRO, max_retries=0)

    tools = asyncio.run(tools_del_fichador())
    print(f"Tools del fichador: {', '.join(t['name'] for t in tools)}\n")
    variantes = {
        "A. las 4 en strict": con_strict(tools, {t["name"] for t in tools}),
        "B. solo registrar_ficha": con_strict(tools, {"registrar_ficha"}),
    }
    with ThreadPoolExecutor(max_workers=len(variantes)) as pool:
        resultados = list(pool.map(lambda par: probar(cliente, modelo, *par), variantes.items()))

    for r in resultados:
        if r["compilo"]:
            marca = "✔ compiló · " + ("entra en los modelos del servidor" if not r["problemas_con_los_modelos"]
                                      else f"NO entra: {r['problemas_con_los_modelos']}")
        else:
            marca = f"✖ {r['error'][:120]}"
        print(f"{r['variante']:<26} {r['uniones']:>2} uniones · {r['opcionales']:>2} opcionales · {r['segundos']:>5} s · {marca}")

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo,
                                       "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()