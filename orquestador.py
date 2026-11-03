"""Orquestador (semana 3, M4): los archivos de los proveedores se leen EN PARALELO y se consolidan por código.

Paso 3: etapa 1, la lectura. Patrón fan-out / fan-in (M4 §1.2), es un workflow: los pasos los define este código.
  - Fan-out: cada archivo que se lee con IA es un trabajo; todos se lanzan a la vez (ThreadPoolExecutor).
    Los de cada proveedor (PDF y FDS de LHS) y los proveedores entre sí, como pide la guía.
    El tope de llamadas a la API lo pone la puerta de llamada_guardada (extractor_pdf.TOPE_LLAMADAS).
  - Fan-in: por proveedor, se juntan los errores de sus trabajos y lo que dice el chequeo entre etapas
    (problemas_de_lectura del servidor, la misma función que usa leer_archivo_proveedor). Con algún problema,
    ese proveedor queda frenado con su motivo y no pasa a las fichas (M4 §1.1).

Paso 4: el fan-in por código, a la vista. Por cada proveedor que sigue, la MISMA consolidación del servidor
(leer_filas: precio por vigencia, conflictos, lo que completa otro archivo y la FDS de cada código) se guarda en
salida/consolidado/Pxx.json: es lo que van a ver los fichadores, el contrato entre la etapa 1 y la 2.

Paso 5: etapa 2, las fichas. Las tandas de TODOS los proveedores que siguen van a una sola fila y las toman
FICHADORES fichadores a la vez (el primero que se libera agarra la siguiente, sea del proveedor que sea).
Cada fichador corre agente.fichar_tanda en su hilo: su propio loop, su propio servidor en modo propuesta y su
propia traza. Los fichadores NO escriben: proponen. Lo propuesto queda en salida/propuestas.json para el
único escritor (paso 6).

Paso 6: el único escritor (escritor.py, código sin IA). Revisa por proveedor que no falte ni sobre ningún producto,
vuelve a validar cada propuesta con la regla del servidor y escribe resultados.json una sola vez. Un proveedor con
algún problema no se escribe: sus fichas anteriores quedan intactas.

Qué puede hacer cada pieza (blast radius, M4 §7.2):
  - Lectores (extractores): leen un archivo y escriben SU extracción en salida/extracciones/. Nada más.
  - Fichadores: leen los datos y PROPONEN fichas, solo de los productos de SU tanda. No escriben resultados.
  - Escritor: el ÚNICO que escribe resultados.json, y solo lo que pasó su revisión.
  - Orquestador: lanza, junta, decide quién sigue, guarda lo consolidado y las propuestas. No escribe fichas.

Correr: python orquestador.py                    (reusa las lecturas guardadas: instantáneo y gratis)
        python orquestador.py --de-nuevo         (lee todo desde cero a la vez y mide el tiempo; ~US$ 0,04)
        python orquestador.py --fichas           (además, las fichas con 3 fichadores a la vez; ~US$ 0,16)
        python orquestador.py --fichas --fichadores 1   (lo mismo, de a uno: para comparar en el paso 8)
        python orquestador.py --escribir         (solo escribe, con el salida/propuestas.json que ya está: gratis)
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from agente import CARPETA_TRAZAS, TANDA, fichar_tanda
from escritor import escribir
from escritor import mostrar as mostrar_escritura
from extractor_fds import extraer_fds
from extractor_folleto import extraer_folleto
from extractor_pdf import TOPE_LLAMADAS, extraer_pdf

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
CARPETA_CONSOLIDADO = CARPETA_SALIDA / "consolidado"
DATA = CARPETA_PROYECTO / "Data" / "proveedores"

# Qué se lee con IA y con qué lector: configuración, no código (un archivo nuevo = una línea más).
# Los CSV y los Excel no están: los lee el código del servidor al momento, sin IA.
TRABAJOS_DE_LECTURA = [
    ("P07", "pdf", DATA / "P07_Limpieza_Hogar_Sur" / "LHS_catalogo_nuevos_productos.pdf"),
    ("P07", "fds", DATA / "P07_Limpieza_Hogar_Sur" / "fichas_de_seguridad"),
    ("P01", "pdf", DATA / "P01_Laboratorio_Andes" / "Lista_de_precios_octubre_2026.pdf"),
    ("P05", "folleto", DATA / "P05_Dermalab" / "Dermalab_lanzamientos_2026.pdf"),
]
LECTORES = {"pdf": extraer_pdf, "fds": extraer_fds, "folleto": extraer_folleto}

# Los proveedores que se procesan esta semana (P06 está apartado hasta la semana 5)
PROVEEDORES = ["P03", "P07", "P01", "P05"]

# Cuántos fichadores a la vez. Lo decidió el paso 2 con los límites de la cuenta: con 4 se pasa el límite de
# tokens de SALIDA por minuto (80.000; el thinking cuenta como salida). Más fichadores no es más rápido: es 429.
FICHADORES = 3
FICHADOR = fichar_tanda  # quién corre cada tanda (las pruebas lo cambian por uno falso, sin IA)


def leer(trabajo: tuple, cliente, modelo: str, de_nuevo: bool, reloj: float) -> dict:
    """Corre UN trabajo de lectura y devuelve qué pasó: cuándo empezó y terminó, cuánto costó y si falló.

    Si el lector lanza un error, no se propaga: queda anotado en el resultado. Así un archivo que falla
    no tira abajo a los demás (en un ThreadPoolExecutor, un error sin atrapar recién aparece al pedir el
    resultado y cortaría la junta de todos).
    """
    proveedor_id, tipo, ruta = trabajo
    inicio = time.perf_counter() - reloj
    error, costo = None, 0.0
    try:
        resultado = LECTORES[tipo](cliente, modelo, ruta, de_nuevo)
        costo = resultado["costo_usd"]["total"] if isinstance(resultado["costo_usd"], dict) else resultado["costo_usd"]
    except Exception as excepcion:  # cualquier falla del lector: se informa, no se esconde (M4 §2.2)
        error = f"{type(excepcion).__name__}: {excepcion}"
    fin = time.perf_counter() - reloj
    return {"proveedor_id": proveedor_id, "tipo": tipo, "archivo": ruta.name, "inicio": round(inicio, 1),
            "fin": round(fin, 1), "segundos": round(fin - inicio, 1), "costo_usd": round(costo, 6), "error": error}


def chequear_lecturas(lecturas: list[dict]) -> tuple[list[str], dict[str, list[str]]]:
    """Fan-in: por proveedor, ¿la lectura quedó limpia? Devuelve (los que siguen, {frenado: sus problemas}).

    Junta los errores de sus trabajos y el chequeo entre etapas del servidor (problemas_de_lectura).
    Se importa acá, después de leer: el servidor lee las extracciones al cargarse.
    """
    from servidor_mcp import PROVEEDORES as CONFIGURACION, problemas_de_lectura

    siguen, frenados = [], {}
    for proveedor_id in PROVEEDORES:
        problemas = [f"{l['archivo']}: {l['error']}" for l in lecturas if l["proveedor_id"] == proveedor_id and l["error"]]
        problemas += problemas_de_lectura(CONFIGURACION[proveedor_id])
        if problemas:
            frenados[proveedor_id] = problemas
        else:
            siguen.append(proveedor_id)
    return siguen, frenados


def consolidar_proveedores(siguen: list[str]) -> dict[str, dict]:
    """Paso 4: el fan-in por código. Guarda lo consolidado de cada proveedor que sigue y devuelve un resumen.

    Usa leer_filas del servidor (la misma función que usa la tool leer_archivo_proveedor, no una copia):
    así hay una sola versión de la verdad. Lo guardado es lo que van a recibir los fichadores.
    """
    from servidor_mcp import PROVEEDORES as CONFIGURACION, leer_filas

    CARPETA_CONSOLIDADO.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for proveedor_id in siguen:
        filas = leer_filas(proveedor_id, CONFIGURACION[proveedor_id])
        ruta = CARPETA_CONSOLIDADO / f"{proveedor_id}.json"
        ruta.write_text(json.dumps({"proveedor_id": proveedor_id, "filas": filas}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        calculados = [fila["calculado"] for fila in filas]
        resumen[proveedor_id] = {
            "productos": len(filas),
            "con_fds": sum(1 for c in calculados if c.get("fds")),
            "con_datos_de_otro_archivo": sum(1 for c in calculados if c.get("fuentes")),
            "con_conflicto": sum(1 for c in calculados if c.get("conflictos")),
        }
    return resumen


def armar_tandas(consolidado: dict[str, dict]) -> list[tuple[str, int, int]]:
    """Las tandas de todos los proveedores que siguen, en UNA sola fila: (proveedor, desde, cantidad).

    Ejemplo: P05 con 18 productos -> ("P05", 0, 10) y ("P05", 10, 8).
    """
    return [(proveedor_id, desde, min(TANDA, resumen["productos"] - desde))
            for proveedor_id, resumen in consolidado.items()
            for desde in range(0, resumen["productos"], TANDA)]


def items_de_la_tanda(proveedor_id: str, desde: int, cantidad: int) -> list[str]:
    """Los productos de una tanda, sacados de lo consolidado (el contrato entre la etapa 1 y la 2)."""
    filas = json.loads((CARPETA_CONSOLIDADO / f"{proveedor_id}.json").read_text(encoding="utf-8"))["filas"]
    return [fila["item_id"] for fila in filas[desde:desde + cantidad]]


def fichar(tanda: tuple, cliente, modelo: str, reloj: float, carpeta_trazas: Path) -> dict:
    """Corre UNA tanda con un fichador y devuelve qué pasó: cuándo empezó y terminó, cuánto costó, qué propuso.

    Igual que leer(): si el fichador falla, el error queda anotado y no tira abajo a los demás.
    """
    proveedor_id, desde, cantidad = tanda
    inicio = time.perf_counter() - reloj
    error, resultado = None, {}
    try:
        resultado = FICHADOR(cliente, modelo, proveedor_id, desde, cantidad,
                             carpeta_trazas / f"{proveedor_id}_desde_{desde:03d}.jsonl")
    except Exception as excepcion:
        error = f"{type(excepcion).__name__}: {excepcion}"
    fin = time.perf_counter() - reloj
    return {"proveedor_id": proveedor_id, "desde": desde, "cantidad": cantidad, "inicio": round(inicio, 1),
            "fin": round(fin, 1), "segundos": round(fin - inicio, 1),
            "como_termino": resultado.get("como_termino"), "registrados": resultado.get("registrados", 0),
            "faltan": resultado.get("faltan", items_de_la_tanda(proveedor_id, desde, cantidad) if error else []),
            "vueltas": resultado.get("vueltas", 0), "input_tokens": resultado.get("input_tokens", 0),
            "output_tokens": resultado.get("output_tokens", 0), "costo_usd": resultado.get("costo_usd", 0.0),
            "error": error, "propuestas": resultado.get("propuestas", {})}


def juntar_propuestas(fichas: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Fan-in de la etapa 2: junta las propuestas de todas las tandas. Devuelve (propuestas, fuera_de_su_tanda).

    Cada fichador solo puede proponer los productos de SU tanda (blast radius, M4 §7.2): si propuso uno de otra
    tanda, no se toma (podría pisar al fichador al que le tocaba) y queda anotado para revisarlo.
    """
    propuestas, fuera = {}, []
    for ficha in fichas:
        suyos = set(items_de_la_tanda(ficha["proveedor_id"], ficha["desde"], ficha["cantidad"]))
        for item_id, propuesta in ficha["propuestas"].items():
            if item_id in suyos:
                propuestas[item_id] = propuesta
            else:
                fuera.append(f"{item_id} (lo propuso la tanda {ficha['proveedor_id']} desde {ficha['desde']})")
    return propuestas, fuera


def etapa_fichas(cliente, modelo: str, consolidado: dict[str, dict], fichadores: int) -> tuple[dict, dict]:
    """Etapa 2: reparte todas las tandas entre `fichadores` fichadores a la vez y junta lo que propusieron.

    El ThreadPoolExecutor ES la fila: con max_workers=3 corre 3 tandas, y cuando una termina arranca la siguiente.
    Devuelve (la medición, las propuestas por ítem).
    """
    tandas = armar_tandas(consolidado)
    carpeta_trazas = CARPETA_TRAZAS / f"paralelo_{datetime.now():%Y%m%d_%H%M%S}_{fichadores}"
    carpeta_trazas.mkdir(parents=True, exist_ok=True)
    reloj = time.perf_counter()
    with ThreadPoolExecutor(max_workers=fichadores) as hilos:
        fichas = list(hilos.map(lambda tanda: fichar(tanda, cliente, modelo, reloj, carpeta_trazas), tandas))
    segundos = time.perf_counter() - reloj
    propuestas, fuera = juntar_propuestas(fichas)
    etapa = {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "fichadores": fichadores,
        "tanda": TANDA,
        "segundos": round(segundos, 1),
        "segundos_uno_detras_de_otro": round(sum(f["segundos"] for f in fichas), 1),
        "costo_usd": round(sum(f["costo_usd"] for f in fichas), 6),
        "productos": sum(f["cantidad"] for f in fichas),
        "propuestas": len(propuestas),
        "faltan": [item for f in fichas for item in f["faltan"]],
        "tandas_con_problemas": [f"{f['proveedor_id']} desde {f['desde']}: {f['error'] or f['como_termino']}"
                                 for f in fichas if f["error"] or f["como_termino"] != "end_turn"],
        "fuera_de_su_tanda": fuera,
        "trazas": carpeta_trazas.name,
        "tandas": [{k: v for k, v in f.items() if k != "propuestas"} for f in fichas],
    }
    return etapa, propuestas


def mostrar_fichas(etapa: dict) -> None:
    """Imprime cada tanda con su carril de tiempo y el resumen de la etapa 2."""
    print(f"\n=== Etapa 2: fichas con {etapa['fichadores']} fichador(es) a la vez (tandas de {etapa['tanda']})")
    print(f"{'tanda':<16}{'empieza':>8}{'termina':>8}{'seg':>6}{'fichas':>8}{'US$':>9}")
    for f in etapa["tandas"]:
        estado = f"  ✖ {f['error'] or f['como_termino']}" if f["error"] or f["como_termino"] != "end_turn" else ""
        print(f"{f['proveedor_id'] + ' desde ' + str(f['desde']):<16}{f['inicio']:>8.1f}{f['fin']:>8.1f}"
              f"{f['segundos']:>6.1f}{str(f['registrados']) + '/' + str(f['cantidad']):>8}{f['costo_usd']:>9.4f}{estado}")
    print(f"\nA la vez: {etapa['segundos']:.1f} s · una detrás de otra serían {etapa['segundos_uno_detras_de_otro']:.1f} s"
          f" · US$ {etapa['costo_usd']:.4f}")
    print(f"Propuestas: {etapa['propuestas']}/{etapa['productos']} productos · trazas en salida/trazas/{etapa['trazas']}/")
    if etapa["faltan"]:
        print(f"⚠ Sin propuesta: {etapa['faltan']}")
    if etapa["tandas_con_problemas"]:
        print(f"⚠ Tandas que no terminaron bien: {etapa['tandas_con_problemas']}")
    if etapa["fuera_de_su_tanda"]:
        print(f"⚠ Propuestas de productos de otra tanda (no se toman): {etapa['fuera_de_su_tanda']}")


def etapa_escritura(propuestas: dict, siguen: list[str]) -> dict:
    """Etapa 3: el único escritor guarda las propuestas de los proveedores que siguen (paso 6)."""
    from servidor_mcp import RUTA_RESULTADOS  # la misma ruta que usaba registrar_ficha
    return escribir(propuestas, siguen, CARPETA_CONSOLIDADO, RUTA_RESULTADOS)


def etapa_lectura(cliente, modelo: str, de_nuevo: bool) -> dict:
    """Etapa 1: lanza todos los trabajos de lectura a la vez, los junta y decide qué proveedores siguen."""
    reloj = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(TRABAJOS_DE_LECTURA)) as hilos:
        lecturas = list(hilos.map(lambda trabajo: leer(trabajo, cliente, modelo, de_nuevo, reloj), TRABAJOS_DE_LECTURA))
    segundos = time.perf_counter() - reloj
    siguen, frenados = chequear_lecturas(lecturas)
    return {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "de_nuevo": de_nuevo,
        "tope_llamadas": TOPE_LLAMADAS,
        "segundos": round(segundos, 1),
        "segundos_uno_detras_de_otro": round(sum(l["segundos"] for l in lecturas), 1),
        "costo_usd": round(sum(l["costo_usd"] for l in lecturas), 6),
        "lecturas": lecturas,
        "siguen": siguen,
        "frenados": frenados,
    }


def mostrar(etapa: dict) -> None:
    """Imprime cada trabajo con su carril de tiempo, el total y qué proveedores siguen o quedaron frenados."""
    print(f"\n=== Etapa 1: lectura en paralelo (tope de {etapa['tope_llamadas']} llamadas a la vez)")
    print(f"{'proveedor':<10}{'archivo':<38}{'empieza':>8}{'termina':>8}{'seg':>6}{'US$':>9}")
    for l in etapa["lecturas"]:
        estado = f"  ✖ {l['error']}" if l["error"] else ""
        print(f"{l['proveedor_id']:<10}{l['archivo']:<38}{l['inicio']:>8.1f}{l['fin']:>8.1f}{l['segundos']:>6.1f}"
              f"{l['costo_usd']:>9.4f}{estado}")
    costo = (f"US$ {etapa['costo_usd']:.4f}" if etapa["de_nuevo"]
             else f"US$ 0 (reusó lo guardado; esas lecturas habían costado US$ {etapa['costo_usd']:.4f})")
    print(f"\nA la vez: {etapa['segundos']:.1f} s · uno detrás de otro serían {etapa['segundos_uno_detras_de_otro']:.1f} s"
          f" · {costo}")
    print(f"Siguen a las fichas: {', '.join(etapa['siguen']) or 'ninguno'}")
    for proveedor_id, problemas in etapa["frenados"].items():
        print(f"✖ {proveedor_id} frenado ({len(problemas)} problema(s)):")
        for problema in problemas[:5]:
            print(f"    - {problema}")
    if etapa.get("consolidado"):
        print("\n=== Consolidado por código (lo que van a ver los fichadores, en salida/consolidado/)")
        print(f"{'proveedor':<10}{'productos':>10}{'con FDS':>9}{'con datos de otro archivo':>27}{'con conflicto':>15}")
        for proveedor_id, r in etapa["consolidado"].items():
            print(f"{proveedor_id:<10}{r['productos']:>10}{r['con_fds']:>9}{r['con_datos_de_otro_archivo']:>27}"
                  f"{r['con_conflicto']:>15}")


def main():
    argumentos = argparse.ArgumentParser(description="Lee en paralelo los archivos de los proveedores y arma las fichas.")
    argumentos.add_argument("--de-nuevo", action="store_true", help="Lee todo desde cero (paga las llamadas).")
    argumentos.add_argument("--fichas", action="store_true", help="Corre también la etapa 2, las fichas (paga).")
    argumentos.add_argument("--fichadores", type=int, default=FICHADORES, help=f"Fichadores a la vez (default {FICHADORES}).")
    argumentos.add_argument("--escribir", action="store_true",
                            help="Solo escribe resultados.json con el salida/propuestas.json que ya está (gratis).")
    opciones = argumentos.parse_args()
    de_nuevo = opciones.de_nuevo

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")

    cliente = anthropic.Anthropic()  # uno solo para todos los hilos: el cliente de Anthropic se puede compartir
    etapa = etapa_lectura(cliente, modelo, de_nuevo)
    etapa["consolidado"] = consolidar_proveedores(etapa["siguen"])  # paso 4: solo los que pasaron el chequeo
    mostrar(etapa)
    ruta = CARPETA_SALIDA / "medicion_lectura.json"
    ruta.write_text(json.dumps(etapa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en salida/{ruta.name}")

    ruta_propuestas = CARPETA_SALIDA / "propuestas.json"
    if opciones.fichas:
        fichas, propuestas = etapa_fichas(cliente, modelo, etapa["consolidado"], opciones.fichadores)
        mostrar_fichas(fichas)
        # Las propuestas se guardan ANTES de escribir: si algo falla después, lo que se pagó no se pierde
        ruta_propuestas.write_text(json.dumps(propuestas, ensure_ascii=False, indent=2), encoding="utf-8")
    elif opciones.escribir:
        if not ruta_propuestas.exists():
            sys.exit("✖ No hay salida/propuestas.json para escribir: corré primero con --fichas.")
        propuestas = json.loads(ruta_propuestas.read_text(encoding="utf-8"))
    else:
        return

    informe = etapa_escritura(propuestas, etapa["siguen"])
    mostrar_escritura(informe)
    if opciones.fichas:  # la medición, una por cantidad de fichadores (para comparar en el paso 8)
        fichas["escritor"] = informe
        ruta = CARPETA_SALIDA / f"medicion_fichas_{opciones.fichadores}.json"
        ruta.write_text(json.dumps(fichas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardado en salida/{ruta_propuestas.name} y salida/{ruta.name}")


if __name__ == "__main__":
    main()