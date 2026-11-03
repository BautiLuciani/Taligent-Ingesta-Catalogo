"""Prueba las piezas de agente.py que no usan IA. Correr: python probar_agente.py"""
import asyncio
import json
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from pathlib import Path

from agente import CARPETA_SALIDA, RUTA_SERVIDOR, ejecutar_tool, fichar_tanda, preparar_resultados

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


class ClaudeFalso:
    """Imita al cliente de Anthropic SIN IA: devuelve respuestas armadas a mano, una por llamada.

    Cada llamada tarda ESPERA segundos con time.sleep: frena el hilo igual que la llamada real (que es síncrona).
    Así se puede medir si varios fichadores trabajan de verdad a la vez, sin gastar un peso.
    ESPERA es de 2 s (no 1): así pesa más que lo que tarda en arrancar cada servidor (3 a la vez en una PC
    cargada arrancan más lento), y la prueba mide el paralelo, no la velocidad de la PC.
    """
    ESPERA = 2.0

    def __init__(self, item_id: str):
        ficha = {"gtin": "7793469616846", "marca": "SONRISA", "tipo": "PASTA DENTAL", "contenido": 90, "unidad": "G"}
        base = {"item_id": item_id, "ficha": ficha, "fuentes": {},
                "categoria_decidida_por": {"campo": "tipo", "valor": "PASTA DENTAL", "explicacion": "Cuidado bucal."}}
        # 1ª respuesta: registra el ítem bien y después lo registra MAL (duplicado sin SKU). 2ª: termina.
        self.respuestas = [
            self.respuesta("tool_use", [pedido_falso("registrar_ficha", {**base, "estado": "lista_para_alta"}, "t1"),
                                        pedido_falso("registrar_ficha", {**base, "estado": "duplicado"}, "t2")]),
            self.respuesta("end_turn", [SimpleNamespace(type="text", text="Listo.")]),
        ]
        self.messages = self  # para que ande cliente.messages.stream(...)

    @staticmethod
    def respuesta(stop_reason, bloques):
        for bloque in bloques:
            bloque.type = getattr(bloque, "type", "tool_use")
        return SimpleNamespace(stop_reason=stop_reason, content=bloques,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=10))

    def stream(self, **_):
        time.sleep(self.ESPERA)
        respuesta = self.respuestas.pop(0)
        return _Stream(respuesta)


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


def probar_fichar_tanda(carpeta: Path):
    """fichar_tanda con un Claude falso: propuestas, que no escriba, y que 3 a la vez sea paralelo DE VERDAD."""
    from servidor_mcp import PROVEEDORES, leer_filas
    items = [fila["item_id"] for fila in leer_filas("P03", PROVEEDORES["P03"])[:3]]
    ruta_resultados = CARPETA_SALIDA / "resultados.json"
    antes = ruta_resultados.stat().st_mtime if ruta_resultados.exists() else None

    print("\n--- fichar_tanda: una tanda sola, en modo propuesta (Claude falso, sin gastar) ---")
    inicio = time.perf_counter()
    r = fichar_tanda(ClaudeFalso(items[0]), "falso", "P03", 0, 1, carpeta / "traza_0.jsonl")
    una_sola = time.perf_counter() - inicio
    chequear("Terminó bien", r["como_termino"], "end_turn")
    chequear("El ítem quedó registrado (1/1)", (r["registrados"], r["esperados"]), (1, 1))
    chequear("Hay una propuesta, la de su ítem", list(r["propuestas"]), [items[0]])
    chequear("La rechazada (duplicado sin SKU) no pisa a la aceptada", r["propuestas"][items[0]]["estado"], "lista_para_alta")
    despues = ruta_resultados.stat().st_mtime if ruta_resultados.exists() else None
    chequear("No tocó salida/resultados.json", despues, antes)

    print("\n--- fichar_tanda: 3 tandas a la vez, cada una en su hilo ---")
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as hilos:
        resultados = list(hilos.map(
            lambda n: fichar_tanda(ClaudeFalso(items[n]), "falso", "P03", n, 1, carpeta / f"traza_{n}.jsonl"), range(3)))
    tres = time.perf_counter() - inicio
    chequear("Cada una propuso SU ítem", [list(r["propuestas"]) for r in resultados], [[item] for item in items])
    print(f"      una tanda sola: {una_sola:.1f} s · tres a la vez: {tres:.1f} s (de a una serían ~{3 * una_sola:.1f} s)")
    chequear("Tres a la vez tardan menos que dos de a una (paralelo de verdad)", tres < 2 * una_sola, True)
    chequear("Cada fichador escribió su propia traza", sorted(p.name for p in carpeta.glob("traza_*.jsonl")),
             ["traza_0.jsonl", "traza_1.jsonl", "traza_2.jsonl"])


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

    print("\n--- preparar_resultados: cada corrida limpia SOLO su proveedor ---")
    ruta = Path(carpeta_temporal) / "resultados.json"
    antes = {"P03:LT-3303": {"estado": "lista_para_alta"}, "P03:LT-3306": {"estado": "duplicado"},
             "P07:LHS-203": {"estado": "lista_para_alta"}}
    ruta.write_text(json.dumps(antes), encoding="utf-8")
    sacados = preparar_resultados(ruta, "P07")
    chequear("Saca el único ítem de P07", sacados, 1)
    chequear("Los de Litoral quedan", sorted(json.loads(ruta.read_text(encoding="utf-8"))), ["P03:LT-3303", "P03:LT-3306"])
    anterior = json.loads((Path(carpeta_temporal) / "resultados_anterior.json").read_text(encoding="utf-8"))
    chequear("La copia anterior tiene los 3 (no se pierde nada)", anterior, antes)
    chequear("Un pedazo de código (P0) no saca nada: compara \"P0:\" entero", preparar_resultados(ruta, "P0"), 0)
    chequear("Sin resultados.json previo: no hace nada", preparar_resultados(Path(carpeta_temporal) / "no_existe.json", "P07"), 0)

    shutil.rmtree(carpeta_temporal, ignore_errors=True)
    print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")


asyncio.run(main())

# fichar_tanda hace su propio asyncio.run (como en el orquestador, dentro de un hilo): por eso va afuera de main()
carpeta_trazas = Path(tempfile.mkdtemp())
probar_fichar_tanda(carpeta_trazas)
shutil.rmtree(carpeta_trazas, ignore_errors=True)
print(f"\nResultado final: {'todo OK' if errores == 0 else f'{errores} con error'}")