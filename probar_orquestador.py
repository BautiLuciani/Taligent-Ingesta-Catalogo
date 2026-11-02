"""Pruebas del orquestador sin IA: lectores falsos que tardan (y uno que falla). Correr: python probar_orquestador.py"""
import asyncio
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

from fastmcp import Client

import orquestador

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def lector_falso(segundos, costo):
    """Un lector que tarda como si llamara a la API y devuelve un resultado con su costo (no escribe nada)."""
    def leer(cliente, modelo, ruta, de_nuevo):
        time.sleep(segundos)
        return {"costo_usd": costo}
    return leer


def lector_que_falla(cliente, modelo, ruta, de_nuevo):
    time.sleep(0.2)
    raise RuntimeError("no quedó ninguna fila")


print("--- etapa_lectura: los trabajos a la vez (fan-out) ---")
originales = dict(orquestador.LECTORES)
orquestador.LECTORES.update({"pdf": lector_falso(0.5, {"total": 0.01}), "fds": lector_falso(0.4, 0.005),
                             "folleto": lector_falso(0.3, 0.004)})
try:
    etapa = orquestador.etapa_lectura(None, "modelo", de_nuevo=True)
finally:
    orquestador.LECTORES.update(originales)
chequear("4 trabajos de 0,3 a 0,5 s: a la vez tardan lo que el más lento (~0,5 s), no la suma (1,7 s)",
         (etapa["segundos"] < 0.9, etapa["segundos_uno_detras_de_otro"] >= 1.6), (True, True))
chequear("...todos empiezan juntos (carriles en paralelo)", all(l["inicio"] < 0.2 for l in etapa["lecturas"]), True)
chequear("...el costo suma el de cada uno (número o detalle con 'total')", etapa["costo_usd"], 0.029)
chequear("...y con las lecturas limpias, siguen los 4 proveedores", (etapa["siguen"], etapa["frenados"]),
         (["P03", "P07", "P01", "P05"], {}))

print("--- un lector que falla: se anota, no tira abajo a los demás (fan-in) ---")
orquestador.LECTORES.update({"pdf": lector_falso(0.3, {"total": 0.01}), "fds": lector_falso(0.3, 0.005),
                             "folleto": lector_que_falla})
try:
    etapa = orquestador.etapa_lectura(None, "modelo", de_nuevo=True)
finally:
    orquestador.LECTORES.update(originales)
folleto = next(l for l in etapa["lecturas"] if l["tipo"] == "folleto")
chequear("El error del folleto queda anotado, con su tipo", folleto["error"], "RuntimeError: no quedó ninguna fila")
chequear("...Dermalab (P05) queda frenado con ese motivo",
         etapa["frenados"], {"P05": ["Dermalab_lanzamientos_2026.pdf: RuntimeError: no quedó ninguna fila"]})
chequear("...y los otros 3 siguen igual", etapa["siguen"], ["P03", "P07", "P01"])

print("--- consolidar_proveedores: el fan-in por código (paso 4) ---")
carpeta = Path(tempfile.mkdtemp())
original = orquestador.CARPETA_CONSOLIDADO
orquestador.CARPETA_CONSOLIDADO = carpeta
try:
    resumen = orquestador.consolidar_proveedores(["P03", "P07", "P01", "P05"])
finally:
    orquestador.CARPETA_CONSOLIDADO = original
chequear("Se guarda un archivo por proveedor", sorted(p.name for p in carpeta.glob("*.json")),
         ["P01.json", "P03.json", "P05.json", "P07.json"])
chequear("Litoral: 50 productos, un solo archivo (nada que cruzar)", resumen["P03"],
         {"productos": 50, "con_fds": 0, "con_datos_de_otro_archivo": 0, "con_conflicto": 0})
chequear("LHS: 22 de 25 cruzados con su FDS", (resumen["P07"]["productos"], resumen["P07"]["con_fds"]), (25, 22))
chequear("Andes: 12 con datos del Excel y 2 con conflicto",
         (resumen["P01"]["con_datos_de_otro_archivo"], resumen["P01"]["con_conflicto"]), (12, 2))
chequear("Dermalab: 14 completados por la lista", resumen["P05"]["con_datos_de_otro_archivo"], 14)


async def filas_de_la_tool(proveedor_id: str) -> list[dict]:
    """Todas las filas de un proveedor tal como las recibe un fichador (la tool del servidor, de a tandas)."""
    filas, desde = [], 0
    async with Client(Path(__file__).parent / "servidor_mcp.py") as cliente:
        while desde is not None:
            datos = (await cliente.call_tool("leer_archivo_proveedor",
                                             {"proveedor_id": proveedor_id, "desde": desde, "cantidad": 25})).data
            filas += datos["filas"]
            desde = datos["siguiente"]
    return filas


for proveedor_id in ("P01", "P05"):
    guardado = json.loads((carpeta / f"{proveedor_id}.json").read_text(encoding="utf-8"))["filas"]
    chequear(f"{proveedor_id}: lo guardado es EXACTAMENTE lo que recibe el fichador por la tool",
             guardado == asyncio.run(filas_de_la_tool(proveedor_id)), True)

print("--- etapa_fichas: las tandas de todos, repartidas entre los fichadores (paso 5) ---")


class FichadorFalso:
    """Imita a agente.fichar_tanda sin IA: tarda, propone sus productos y anota cuántos trabajan a la vez."""

    def __init__(self, segundos):
        self.segundos, self.trabajando, self.maximo = segundos, 0, 0
        self.candado = threading.Lock()  # el contador lo tocan varios hilos: se cuenta de a uno

    def __call__(self, cliente, modelo, proveedor_id, desde, cantidad, ruta_traza):
        with self.candado:
            self.trabajando += 1
            self.maximo = max(self.maximo, self.trabajando)
        time.sleep(self.segundos)
        with self.candado:
            self.trabajando -= 1
        if (proveedor_id, desde) == ("P05", 10):
            raise RuntimeError("se cayó el servidor")
        items = orquestador.items_de_la_tanda(proveedor_id, desde, cantidad)
        propuestas = {item: {"item_id": item, "estado": "lista_para_alta"} for item in items}
        if (proveedor_id, desde) == ("P03", 0):
            propuestas["P03:LT-3999"] = {"item_id": "P03:LT-3999"}  # uno que NO es de su tanda
        return {"como_termino": "end_turn", "registrados": cantidad, "faltan": [], "vueltas": 2,
                "input_tokens": 100, "output_tokens": 10, "costo_usd": 0.01, "propuestas": propuestas}


consolidado = {"P03": {"productos": 50}, "P07": {"productos": 25}, "P01": {"productos": 26}, "P05": {"productos": 18}}
tandas = orquestador.armar_tandas(consolidado)
chequear("13 tandas en una sola fila (P03 5 · P07 3 · P01 3 · P05 2)", len(tandas), 13)
chequear("La última de Dermalab tiene 8 productos", tandas[-1], ("P05", 10, 8))

orquestador.CARPETA_CONSOLIDADO = carpeta  # lo consolidado de arriba (el contrato entre etapas)
originales = (orquestador.FICHADOR, orquestador.CARPETA_TRAZAS)
orquestador.CARPETA_TRAZAS = carpeta / "trazas"
mediciones = {}
try:
    for cuantos in (1, 3):
        orquestador.FICHADOR = falso = FichadorFalso(0.2)
        mediciones[cuantos], propuestas = orquestador.etapa_fichas(None, "modelo", consolidado, cuantos)
        mediciones[cuantos]["maximo"] = falso.maximo
finally:
    orquestador.FICHADOR, orquestador.CARPETA_TRAZAS = originales
    orquestador.CARPETA_CONSOLIDADO = original
uno, tres = mediciones[1], mediciones[3]
print(f"      13 tandas de 0,2 s: con 1 fichador {uno['segundos']:.1f} s · con 3 a la vez {tres['segundos']:.1f} s")
chequear("Con 1 fichador nunca hay dos trabajando", uno["maximo"], 1)
chequear("Con 3, nunca más de 3 a la vez (el tope de los límites de la cuenta)", tres["maximo"], 3)
chequear("Con 3 tarda bastante menos (5 vueltas de 0,2 s, no 13)", tres["segundos"] < uno["segundos"] / 2, True)
chequear("Propuestas: todas menos las 8 de la tanda que falló", tres["propuestas"], 119 - 8)
chequear("...esas 8 quedan como faltantes", len(tres["faltan"]), 8)
chequear("...y la tanda que falló queda anotada con su error",
         tres["tandas_con_problemas"], ["P05 desde 10: RuntimeError: se cayó el servidor"])
chequear("La propuesta de un producto de otra tanda no se toma", "P03:LT-3999" in propuestas, False)
chequear("...y queda anotada", tres["fuera_de_su_tanda"], ["P03:LT-3999 (lo propuso la tanda P03 desde 0)"])
chequear("Cada tanda guarda sus carriles (empieza/termina) y no sus propuestas",
         ("inicio" in tres["tandas"][0], "propuestas" in tres["tandas"][0]), (True, False))
shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")