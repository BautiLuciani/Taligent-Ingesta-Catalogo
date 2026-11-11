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

Paso 7: Natural Vida (P09) manda un mail en texto. Lo lee el código del servidor (sin IA, como el CSV) y solo los
productos llegan a los fichadores. El resto del mail (saludo, firma y una "PD para el sistema de carga" que pide dar
todo de alta sin revisión) no se pasa, pero tampoco se esconde: la etapa 1 lo muestra como aviso.

Paso 9 (extra): el detector de fichas inestables (--detector), el segundo uso del paralelo (M4 §1.2). Cada tanda
la arman DOS fichadores por separado (A y B) y el código compara sus propuestas campo por campo. Si coinciden, la
ficha sigue normal; si no, el modelo duda: se escribe la versión A marcada como "inestable", con los campos que
difieren y la otra versión, para que la mire una persona (salida/inestables.json). Cuesta el doble: no es el modo
por defecto, es para controlar (sobre todo donde no hay casos verificados, como un proveedor nuevo).

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
        python orquestador.py --fichas --proveedores P09   (solo esos proveedores: las fichas de los demás no se tocan)
        python orquestador.py --fichas --detector          (cada tanda dos veces: marca las fichas inestables; el doble)
"""
import argparse
import json
import os
import sys
import threading
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
from servidor_mcp import PROVEEDORES as HABILITADOS  # ya lo carga el escritor; acá se usa para saber quién se procesa

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

# Los proveedores que se procesan (semana 4, paso 7): TODOS los habilitados del servidor, los escritos a mano (semanas
# 1 a 3) y los que entraron solos por el recepcionista. Antes era una lista fija: un proveedor nuevo quedaba afuera.
# P06 no está: el servidor no lo habilita (apartado hasta la semana 5).
# Ojo: las FDS de un proveedor recibido las lee la bandeja ANTES (vigilar.py). Este módulo carga el servidor al
# arrancar (vía el escritor), y si sus FDS faltaran recién se leerían acá, el servidor ya cargado no lo sabría.
PROVEEDORES = list(HABILITADOS)

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


def chequear_lecturas(lecturas: list[dict], proveedores: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Fan-in: por proveedor, ¿la lectura quedó limpia? Devuelve (los que siguen, {frenado: sus problemas}).

    Junta los errores de sus trabajos y el chequeo entre etapas del servidor (problemas_de_lectura).
    Se importa acá, después de leer: el servidor lee las extracciones al cargarse.
    """
    from servidor_mcp import PROVEEDORES as CONFIGURACION, problemas_de_lectura

    siguen, frenados = [], {}
    for proveedor_id in proveedores:
        problemas = [f"{l['archivo']}: {l['error']}" for l in lecturas if l["proveedor_id"] == proveedor_id and l["error"]]
        problemas += problemas_de_lectura(CONFIGURACION[proveedor_id])
        if problemas:
            frenados[proveedor_id] = problemas
        else:
            siguen.append(proveedor_id)
    return siguen, frenados


def avisos_de_lectura(proveedores: list[str]) -> dict[str, list[str]]:
    """Lo que el lector dejó afuera a propósito y una persona tiene que ver (paso 7).

    El texto de un mail que no es un producto: el saludo, la firma o una "PD para el sistema de carga". No frena a
    nadie (no es un error de lectura) y no llega a los fichadores: el archivo es un dato, no instrucciones.
    """
    from servidor_mcp import PROVEEDORES as CONFIGURACION, leer_mail

    avisos = {}
    for proveedor_id in proveedores:
        config = CONFIGURACION[proveedor_id]
        if config.get("formato") == "mail":
            avisos[proveedor_id] = [f"línea {otra['linea']}: {otra['texto']}"
                                    for otra in leer_mail(proveedor_id, config)["otras_lineas"]]
    return avisos


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
        de_otro_archivo = [fila for fila in filas  # un dato que vino de OTRO archivo (no de otra línea del mismo)
                           if any(f["archivo"] != fila["fuente"]["archivo"] for f in fila["calculado"].get("fuentes", {}).values())]
        resumen[proveedor_id] = {
            "productos": len(filas),
            "con_fds": sum(1 for c in calculados if c.get("fds")),
            "con_datos_de_otro_archivo": len(de_otro_archivo),
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


def fichar(tanda: tuple, cliente, modelo: str, reloj: float, carpeta_trazas: Path, version: str = "") -> dict:
    """Corre UNA tanda con un fichador y devuelve qué pasó: cuándo empezó y terminó, cuánto costó, qué propuso.

    Igual que leer(): si el fichador falla, el error queda anotado y no tira abajo a los demás.
    version: con el detector (paso 9), cada tanda se corre dos veces, "A" y "B" (cada una con su traza).
    """
    proveedor_id, desde, cantidad = tanda
    # Qué fichador (hilo) la corre: el pool nombra sus hilos "fichador_0", "fichador_1"... (paso 8: el gráfico de
    # carriles necesita saber en qué carril fue cada tanda, no solo cuándo empezó y terminó)
    nombre_hilo = threading.current_thread().name
    fichador = int(nombre_hilo.rsplit("_", 1)[1]) + 1 if nombre_hilo.startswith("fichador_") else 1
    inicio = time.perf_counter() - reloj
    error, resultado = None, {}
    try:
        resultado = FICHADOR(cliente, modelo, proveedor_id, desde, cantidad,
                             carpeta_trazas / f"{proveedor_id}_desde_{desde:03d}{'_' + version if version else ''}.jsonl")
    except Exception as excepcion:
        error = f"{type(excepcion).__name__}: {excepcion}"
    fin = time.perf_counter() - reloj
    return {"proveedor_id": proveedor_id, "desde": desde, "cantidad": cantidad, "version": version, "fichador": fichador,
            "inicio": round(inicio, 1),
            "fin": round(fin, 1), "segundos": round(fin - inicio, 1),
            "como_termino": resultado.get("como_termino"), "registrados": resultado.get("registrados", 0),
            "faltan": resultado.get("faltan", items_de_la_tanda(proveedor_id, desde, cantidad) if error else []),
            "vueltas": resultado.get("vueltas", 0), "input_tokens": resultado.get("input_tokens", 0),
            "output_tokens": resultado.get("output_tokens", 0), "costo_usd": resultado.get("costo_usd", 0.0),
            "error": error, "propuestas": resultado.get("propuestas", {}),
            "frenos": resultado.get("frenos", [])}  # semana 4, paso 5: lo que frenaron los hooks en esa tanda


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


def comparar_propuestas(a: dict, b: dict) -> list[str]:
    """Qué difiere entre dos propuestas del MISMO producto (paso 9). Vacía = coinciden.

    Compara lo que va a resultados.json: estado, duplicado, motivos (sin importar el orden), cada campo de la ficha y
    cada fuente. No la explicación de la categoría: es texto libre, dos frases distintas pueden decir lo mismo.
    Ejemplo: ["ficha.marca", "motivos_revision"] si una corrida puso la marca y la otra la dejó vacía y mandó a revisión.
    """
    distintos = [clave for clave in ("estado", "duplicado_de") if a.get(clave) != b.get(clave)]
    if sorted(a.get("motivos_revision", [])) != sorted(b.get("motivos_revision", [])):
        distintos.append("motivos_revision")
    for grupo in ("ficha", "fuentes"):
        de_a, de_b = a.get(grupo, {}), b.get(grupo, {})
        distintos += [f"{grupo}.{campo}" for campo in sorted(set(de_a) | set(de_b)) if de_a.get(campo) != de_b.get(campo)]
    return distintos


def combinar_versiones(de_a: dict[str, dict], de_b: dict[str, dict]) -> tuple[dict[str, dict], list[dict]]:
    """El detector (paso 9): junta las propuestas de las corridas A y B. Devuelve (propuestas, inestables).

    - Coinciden: va la de A, sin marca.
    - No coinciden: va la de A con "inestable" (los campos que difieren y la otra versión). No se fuerza a revisión:
      los motivos son una lista cerrada del estándar y "inestable" no está; la marca es la que avisa.
    - Solo una corrida lo propuso: va esa, marcada "sin segunda opinión" (no se pudo comparar).
    """
    propuestas, inestables = {}, []
    for item_id in sorted(set(de_a) | set(de_b)):
        a, b = de_a.get(item_id), de_b.get(item_id)
        if a is None or b is None:
            marca = {"campos": ["(sin segunda opinión: solo una de las dos corridas lo propuso)"], "otra_version": None}
        else:
            campos = comparar_propuestas(a, b)
            marca = {"campos": campos, "otra_version": b} if campos else None
        propuestas[item_id] = {**(a or b), "inestable": marca} if marca else a
        if marca:
            inestables.append({"item_id": item_id, "campos": marca["campos"]})
    return propuestas, inestables


def etapa_fichas(cliente, modelo: str, consolidado: dict[str, dict], fichadores: int,
                 detector: bool = False) -> tuple[dict, dict]:
    """Etapa 2: reparte todas las tandas entre `fichadores` fichadores a la vez y junta lo que propusieron.

    El ThreadPoolExecutor ES la fila: con max_workers=3 corre 3 tandas, y cuando una termina arranca la siguiente.
    Con detector=True (paso 9), cada tanda entra dos veces a la fila (A y B) y se combinan con combinar_versiones.
    Devuelve (la medición, las propuestas por ítem).
    """
    tandas = armar_tandas(consolidado)
    trabajos = [(tanda, version) for tanda in tandas for version in (("A", "B") if detector else ("",))]
    carpeta_trazas = CARPETA_TRAZAS / f"paralelo_{datetime.now():%Y%m%d_%H%M%S}_{fichadores}{'_detector' if detector else ''}"
    carpeta_trazas.mkdir(parents=True, exist_ok=True)
    reloj = time.perf_counter()
    with ThreadPoolExecutor(max_workers=fichadores, thread_name_prefix="fichador") as hilos:
        fichas = list(hilos.map(lambda trabajo: fichar(trabajo[0], cliente, modelo, reloj, carpeta_trazas, trabajo[1]),
                                trabajos))
    segundos = time.perf_counter() - reloj
    inestables = []
    if detector:
        de_a, fuera_a = juntar_propuestas([f for f in fichas if f["version"] == "A"])
        de_b, fuera_b = juntar_propuestas([f for f in fichas if f["version"] == "B"])
        propuestas, inestables = combinar_versiones(de_a, de_b)
        fuera = fuera_a + fuera_b
    else:
        propuestas, fuera = juntar_propuestas(fichas)
    # Falta un producto si ninguna corrida lo propuso (con el detector, una sola alcanza: queda "sin segunda opinión")
    faltan = [item_id for tanda in tandas for item_id in items_de_la_tanda(*tanda) if item_id not in propuestas]
    etapa = {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "fichadores": fichadores,
        "detector": detector,
        "tanda": TANDA,
        "segundos": round(segundos, 1),
        "segundos_uno_detras_de_otro": round(sum(f["segundos"] for f in fichas), 1),
        "costo_usd": round(sum(f["costo_usd"] for f in fichas), 6),
        "productos": sum(tanda[2] for tanda in tandas),
        "propuestas": len(propuestas),
        "faltan": faltan,
        "inestables": inestables,
        "tandas_con_problemas": [f"{f['proveedor_id']} desde {f['desde']}{' ' + f['version'] if f['version'] else ''}: "
                                 f"{f['error'] or f['como_termino']}"
                                 for f in fichas if f["error"] or f["como_termino"] != "end_turn"],
        "fuera_de_su_tanda": fuera,
        "trazas": carpeta_trazas.name,
        # Semana 4, paso 5: todos los frenos de los hooks, con la tanda que los tuvo (es lo que va a salida/hooks.json)
        "frenos": [{"proveedor_id": f["proveedor_id"], "desde": f["desde"], "version": f["version"], **freno}
                   for f in fichas for freno in f["frenos"]],
        "tandas": [{k: v for k, v in f.items() if k not in ("propuestas", "frenos")} for f in fichas],
    }
    return etapa, propuestas


def mostrar_fichas(etapa: dict) -> None:
    """Imprime cada tanda con su carril de tiempo y el resumen de la etapa 2."""
    detector = " · detector: cada tanda dos veces (A y B)" if etapa.get("detector") else ""
    print(f"\n=== Etapa 2: fichas con {etapa['fichadores']} fichador(es) a la vez (tandas de {etapa['tanda']}){detector}")
    print(f"{'tanda':<18}{'empieza':>8}{'termina':>8}{'seg':>6}{'fichas':>8}{'US$':>9}")
    for f in etapa["tandas"]:
        estado = f"  ✖ {f['error'] or f['como_termino']}" if f["error"] or f["como_termino"] != "end_turn" else ""
        nombre = f"{f['proveedor_id']} desde {f['desde']}{' ' + f['version'] if f.get('version') else ''}"
        print(f"{nombre:<18}{f['inicio']:>8.1f}{f['fin']:>8.1f}"
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
    frenos = etapa.get("frenos", [])
    corregidos = sum(1 for freno in frenos if freno["corregido"])
    print(f"Hooks: {len(frenos)} freno(s)" + (f", {corregidos} corregido(s) por el modelo" if frenos else "")
          + " · detalle en salida/hooks.json")
    for freno in frenos:
        print(f"   {'✔' if freno['corregido'] else '✖'} {freno['hook']} · {freno['item_id']} · {freno['motivo'][:110]}")
    if etapa.get("detector"):
        print(f"Detector: {len(etapa['inestables'])} ficha(s) inestable(s) de {etapa['propuestas']}"
              + (" (las dos corridas no coinciden: hay que mirarlas)" if etapa["inestables"] else
                 " (las dos corridas coinciden en todas)"))
        for inestable in etapa["inestables"]:
            print(f"   ≠ {inestable['item_id']}: {', '.join(inestable['campos'])}")


def etapa_escritura(propuestas: dict, siguen: list[str]) -> dict:
    """Etapa 3: el único escritor guarda las propuestas de los proveedores que siguen (paso 6)."""
    from servidor_mcp import RUTA_RESULTADOS  # la misma ruta que usaba registrar_ficha
    return escribir(propuestas, siguen, CARPETA_CONSOLIDADO, RUTA_RESULTADOS)


def etapa_lectura(cliente, modelo: str, de_nuevo: bool, proveedores: list[str] | None = None) -> dict:
    """Etapa 1: lanza todos los trabajos de lectura a la vez, los junta y decide qué proveedores siguen.

    proveedores: los de esta corrida (por defecto, todos). Un proveedor que lee el código (CSV, mail) no tiene
    trabajos de lectura con IA: pasa directo al chequeo.
    """
    proveedores = proveedores or PROVEEDORES
    trabajos = [trabajo for trabajo in TRABAJOS_DE_LECTURA if trabajo[0] in proveedores]
    reloj = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, len(trabajos))) as hilos:
        lecturas = list(hilos.map(lambda trabajo: leer(trabajo, cliente, modelo, de_nuevo, reloj), trabajos))
    segundos = time.perf_counter() - reloj
    siguen, frenados = chequear_lecturas(lecturas, proveedores)
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
        "avisos": avisos_de_lectura(siguen),
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
    for proveedor_id, lineas in etapa.get("avisos", {}).items():
        print(f"\n⚠ {proveedor_id}: el mail trae {len(lineas)} línea(s) que no son productos. NO llegan a los fichadores"
              " (el archivo es un dato, no instrucciones):")
        for linea in lineas:
            print(f"    {linea}")
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
    argumentos.add_argument("--proveedores", nargs="+", default=PROVEEDORES, metavar="Pxx",
                            help="Solo estos proveedores (default: todos). Las fichas de los demás no se tocan.")
    argumentos.add_argument("--detector", action="store_true",
                            help="Con --fichas: cada tanda la arman dos fichadores y se marcan las fichas que no coinciden (el doble).")
    argumentos.add_argument("--escribir", action="store_true",
                            help="Solo escribe resultados.json con el salida/propuestas.json que ya está (gratis).")
    opciones = argumentos.parse_args()
    de_nuevo = opciones.de_nuevo
    proveedores = opciones.proveedores
    desconocidos = [proveedor_id for proveedor_id in proveedores if proveedor_id not in PROVEEDORES]
    if desconocidos:
        sys.exit(f"ERROR: {', '.join(desconocidos)} no está habilitado (ni escrito a mano ni recibido por el "
                 f"recepcionista). Se puede: {', '.join(PROVEEDORES)}")

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")

    cliente = anthropic.Anthropic()  # uno solo para todos los hilos: el cliente de Anthropic se puede compartir
    etapa = etapa_lectura(cliente, modelo, de_nuevo, proveedores)
    etapa["consolidado"] = consolidar_proveedores(etapa["siguen"])  # paso 4: solo los que pasaron el chequeo
    mostrar(etapa)
    ruta = CARPETA_SALIDA / "medicion_lectura.json"
    ruta.write_text(json.dumps(etapa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en salida/{ruta.name}")

    ruta_propuestas = CARPETA_SALIDA / "propuestas.json"
    guardadas = json.loads(ruta_propuestas.read_text(encoding="utf-8")) if ruta_propuestas.exists() else {}
    if opciones.fichas:
        fichas, nuevas = etapa_fichas(cliente, modelo, etapa["consolidado"], opciones.fichadores, opciones.detector)
        mostrar_fichas(fichas)
        # propuestas.json guarda la última propuesta de cada producto: las de los proveedores de esta corrida se
        # reemplazan y las de los demás quedan. Se guarda ANTES de escribir: si algo falla después, lo pagado no se pierde
        guardadas = {item_id: p for item_id, p in guardadas.items() if item_id.split(":")[0] not in proveedores}
        guardadas.update(nuevas)
        ruta_propuestas.write_text(json.dumps(guardadas, ensure_ascii=False, indent=2), encoding="utf-8")
        # Semana 4, paso 5: los frenos de los hooks de esta corrida (cada uno con si el modelo lo corrigió)
        (CARPETA_SALIDA / "hooks.json").write_text(json.dumps(
            {"fecha": fichas["fecha"], "proveedores": proveedores, "frenos": fichas["frenos"],
             "total": len(fichas["frenos"]), "corregidos": sum(1 for f in fichas["frenos"] if f["corregido"])},
            ensure_ascii=False, indent=2), encoding="utf-8")
        if opciones.detector:  # paso 9: las inestables, con las dos versiones, para que las mire una persona
            inestables = [{"item_id": item_id, "campos": p["inestable"]["campos"],
                           "version_a": {k: v for k, v in p.items() if k != "inestable"},
                           "version_b": p["inestable"]["otra_version"]}
                          for item_id, p in nuevas.items() if p.get("inestable")]
            (CARPETA_SALIDA / "inestables.json").write_text(json.dumps(inestables, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")
            print(f"Las {len(inestables)} inestable(s), con sus dos versiones, en salida/inestables.json")
    elif opciones.escribir:
        if not guardadas:
            sys.exit("✖ No hay salida/propuestas.json para escribir: corré primero con --fichas.")
    else:
        return

    # Al escritor van solo las propuestas de los proveedores de esta corrida (las de los demás no se tocan)
    propuestas = {item_id: p for item_id, p in guardadas.items() if item_id.split(":")[0] in proveedores}
    informe = etapa_escritura(propuestas, etapa["siguen"])
    mostrar_escritura(informe)
    if opciones.fichas:  # la medición, una por cantidad de fichadores (para comparar en el paso 8)
        fichas["escritor"] = informe
        sufijo = "" if set(proveedores) == set(PROVEEDORES) else "_" + "_".join(proveedores)  # una parcial no pisa la completa
        sufijo += "_detector" if opciones.detector else ""
        ruta = CARPETA_SALIDA / f"medicion_fichas_{opciones.fichadores}{sufijo}.json"
        ruta.write_text(json.dumps(fichas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardado en salida/{ruta_propuestas.name} y salida/{ruta.name}")


if __name__ == "__main__":
    main()