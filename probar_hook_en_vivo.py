"""Experimento (semana 4, paso 5): un hook frenando una ficha EN VIVO, con el modelo real corrigiéndose.

Haiku casi nunca escribe un GTIN mal (copia el que calculó el código), así que para ver el hook trabajar se PROVOCA
el error, igual que con el detector en la semana 3: un cliente envoltorio deja pasar las respuestas reales de Haiku,
pero en la PRIMERA que registra una ficha con GTIN le cambia el último dígito a ese GTIN (ERROR INYECTADO, a propósito,
y queda dicho así en la salida y en el resumen). Todo lo demás es real: el loop, los hooks, el servidor y Haiku.

Qué tiene que pasar: el hook antes_de_tool frena ese registrar_ficha (la ficha no llega al servidor), Haiku recibe el
motivo como error, lo lee y vuelve a registrar el producto con el GTIN correcto. Al final: el freno figura corregido.
Sin el hook, esa ficha se habría aceptado: el servidor no revisa el dígito verificador (solo la coherencia).

Correr: python probar_hook_en_vivo.py      (~US$ 0,02: una tanda de Litoral; no toca resultados.json)
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from agente import RUTA_SERVIDOR, TANDA, armar_system_prompt, obtener_tools, procesar_tanda

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_EXPERIMENTO = CARPETA_PROYECTO / "salida" / "experimentos" / "hook_en_vivo"
PROVEEDOR, DESDE = "P03", 0  # la primera tanda de Litoral (el proveedor más simple: el error inyectado es lo único raro)


def otro_ultimo_digito(gtin: str) -> str:
    """El mismo GTIN con el último dígito cambiado: el dígito verificador queda mal."""
    return gtin[:-1] + str((int(gtin[-1]) + 1) % 10)


class ClaudeConUnError:
    """Envuelve al cliente real de Anthropic. Deja pasar todo, salvo UNA vez: en la primera respuesta que registra una
    ficha con GTIN, le cambia el último dígito. Anota qué cambió (inyectado) para mostrarlo."""

    def __init__(self, cliente):
        self.cliente = cliente
        self.messages = self  # para que ande cliente.messages.stream(...)
        self.inyectado = None

    def stream(self, **pedido):
        return _StreamConUnError(self.cliente.messages.stream(**pedido), self)


class _StreamConUnError:
    def __init__(self, stream_real, envoltorio: ClaudeConUnError):
        self.stream_real, self.envoltorio = stream_real, envoltorio

    def __enter__(self):
        self.abierto = self.stream_real.__enter__()
        return self

    def __exit__(self, *error):
        return self.stream_real.__exit__(*error)

    def get_final_message(self):
        respuesta = self.abierto.get_final_message()
        if self.envoltorio.inyectado is None:
            for bloque in respuesta.content:
                ficha = bloque.input.get("ficha") if bloque.type == "tool_use" and bloque.name == "registrar_ficha" else None
                if isinstance(ficha, dict) and ficha.get("gtin"):
                    original = ficha["gtin"]
                    ficha["gtin"] = otro_ultimo_digito(original)
                    self.envoltorio.inyectado = {"item_id": bloque.input.get("item_id"), "gtin_de_haiku": original,
                                                 "gtin_inyectado": ficha["gtin"]}
                    break
        return respuesta


async def correr(cliente_claude, modelo: str) -> dict:
    """Una tanda, como un fichador: su servidor en modo propuesta (no escribe resultados.json) y su traza."""
    CARPETA_EXPERIMENTO.mkdir(parents=True, exist_ok=True)
    transporte = PythonStdioTransport(RUTA_SERVIDOR, env={"INGESTA_MODO_PROPUESTA": "1"})
    async with Client(transporte) as cliente_mcp:
        system = await armar_system_prompt(cliente_mcp)
        tools = await obtener_tools(cliente_mcp)
        return await procesar_tanda(cliente_claude, cliente_mcp, modelo, system, tools, PROVEEDOR, DESDE, TANDA,
                                    CARPETA_EXPERIMENTO / "traza.jsonl")


def mostrar(envoltorio: ClaudeConUnError, resultado: dict) -> dict:
    """Imprime lo que pasó y arma el resumen que se guarda."""
    inyectado = envoltorio.inyectado
    print("\n=== Hook en vivo (ERROR INYECTADO a propósito: no lo cometió Haiku)")
    if inyectado is None:
        print("No hubo ningún registrar_ficha con GTIN: no se inyectó nada (volvé a correrlo).")
        return {"inyectado": None, "resultado": resultado}
    item = inyectado["item_id"]
    print(f"Inyectado: en {item}, Haiku registró el GTIN {inyectado['gtin_de_haiku']} y se lo cambiamos por "
          f"{inyectado['gtin_inyectado']}")
    frenos = [f for f in resultado["frenos"] if f["item_id"] == item]
    for freno in frenos:
        print(f"Hook: {freno['hook']} frenó {item}: {freno['motivo']}")
    final = resultado["propuestas"].get(item, {}).get("ficha", {}).get("gtin")
    corregido = bool(frenos) and all(f["corregido"] for f in frenos) and final == inyectado["gtin_de_haiku"]
    print(f"Haiku lo volvió a registrar con el GTIN {final}: {'✔ corregido' if corregido else '✖ NO corregido'}")
    print(f"Tanda: {resultado['registrados']}/{resultado['esperados']} registrados · {resultado['vueltas']} vueltas · "
          f"US$ {resultado['costo_usd']:.4f} · {resultado['como_termino']}")
    print(f"Traza en salida/experimentos/{CARPETA_EXPERIMENTO.name}/traza.jsonl")
    return {"inyectado": inyectado, "frenos": frenos, "gtin_final": final, "corregido": corregido,
            "registrados": resultado["registrados"], "esperados": resultado["esperados"],
            "vueltas": resultado["vueltas"], "costo_usd": resultado["costo_usd"], "como_termino": resultado["como_termino"]}


def main():
    # Con argparse: así "--help" explica y NO arranca una corrida que se paga (regla de la semana 3)
    argparse.ArgumentParser(description="Un hook frenando una ficha en vivo, con un error inyectado (~US$ 0,02).").parse_args()
    import anthropic  # recién acá: con --help no hace falta
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    envoltorio = ClaudeConUnError(anthropic.Anthropic())
    resultado = asyncio.run(correr(envoltorio, modelo))
    resumen = mostrar(envoltorio, resultado)
    (CARPETA_EXPERIMENTO / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
