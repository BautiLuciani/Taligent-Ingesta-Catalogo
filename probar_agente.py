"""Prueba las piezas de agente.py que no usan IA. Correr: python probar_agente.py"""
import asyncio
import json
import shutil
import tempfile
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from agente import RUTA_SERVIDOR, ejecutar_tool

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def pedido_falso(nombre, argumentos, id_="toolu_prueba"):
    """Imita un bloque tool_use de la respuesta de Haiku (tiene .id, .name y .input)."""
    return SimpleNamespace(id=id_, name=nombre, input=argumentos)


async def main():
    carpeta_temporal = tempfile.mkdtemp()  # registrar_ficha escribe acá, no en salida/
    transporte = PythonStdioTransport(RUTA_SERVIDOR, env={"INGESTA_CARPETA_SALIDA": carpeta_temporal})
    async with Client(transporte) as cliente:
        print("--- pedidos que salen bien ---")
        r = await ejecutar_tool(cliente, pedido_falso("buscar_por_gtin", {"gtin": "7798096023746"}, "toolu_01"))
        chequear("Tiene la forma de un tool_result", sorted(r), ["content", "is_error", "tool_use_id", "type"])
        chequear("Devuelve el mismo tool_use_id del pedido", r["tool_use_id"], "toolu_01")
        chequear("No es error", r["is_error"], False)
        chequear("El content es texto JSON con el SKU", json.loads(r["content"])["sku"], "SKU100301")

        r = await ejecutar_tool(cliente, pedido_falso("leer_archivo_proveedor", {"proveedor_id": "P03", "cantidad": 2}))
        chequear("leer_archivo_proveedor trae 2 filas", len(json.loads(r["content"])["filas"]), 2)

        print("\n--- pedidos que salen mal (vuelven como is_error, sin romper nada) ---")
        r = await ejecutar_tool(cliente, pedido_falso("registrar_ficha", {
            "item_id": "P03:LT-3306", "estado": "duplicado", "ficha": {}, "fuentes": {}}))
        chequear("registrar_ficha incoherente -> is_error", r["is_error"], True)
        print(f"      lo que lee Haiku: {r['content']}")

        r = await ejecutar_tool(cliente, pedido_falso("buscar_por_gtin", {"gtin": "123"}))
        chequear("Argumento inválido -> is_error", r["is_error"], True)

        r = await ejecutar_tool(cliente, pedido_falso("borrar_catalogo", {}))
        chequear("Tool que no existe -> is_error", r["is_error"], True)
        print(f"      lo que lee Haiku: {r['content'][:100]}")

    shutil.rmtree(carpeta_temporal, ignore_errors=True)
    print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")


asyncio.run(main())