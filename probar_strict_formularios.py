"""Semana 5, paso 3D: los tres formularios forzados con salida estructurada, contra lo que ya teníamos. No toca el sistema.

  A. Recepcionista (tool forzada + strict): las recetas de Rivera, Higiene Total y Norte, pedidas DE NUEVO, contra las
     de la semana 4 (congeladas y verificadas por Bauti). Va por recibir(): resumen -> formulario -> controles del código.
  B. Extractor de PDF, llamada 2 (tool forzada + strict): los campos de las filas de LHS y Andes, pedidos de nuevo,
     contra la extracción congelada. Las filas son las de la extracción (con su pie de página, como llegaron).
  C. Catálogo viejo (output_config.format, deja pensar): una tanda de 25, contra las variantes de la semana 3.

Lo que se espera: A y B iguales (son mecánicos y el código verifica todo). C puede diferir en algún producto: decidir
la variante es criterio y cada corrida puede variar; lo que importa es que la respuesta llegue con la forma garantizada
y pase la validación del código. Todo se guarda en una carpeta temporal: no pisa recepciones ni extracciones reales.
Correr: python probar_strict_formularios.py   (paga ~US$ 0,02)
"""
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from referencias import CARPETA_RECEPCION_REFERENCIA, CARPETA_REFERENCIAS_SEM4  # congeladas (antes que el servidor)
from catalogo_viejo import TANDA, clasificar, leer_catalogo, resolver_tanda, sin_tildes  # noqa: E402
from extractor_pdf import COLUMNAS_POR_PDF, campos_desde_respuesta, costo_usd, pedir_campos  # noqa: E402
from recepcion import recibir  # noqa: E402

CARPETA_PROYECTO = Path(__file__).parent
RUTA_SALIDA = CARPETA_PROYECTO / "salida" / "experimentos" / "strict_formularios_sem5.json"
RUTA_CATALOGO_SEM3 = CARPETA_PROYECTO / "salida" / "catalogo_viejo" / "propuestas.json"
EXTRACCIONES = CARPETA_REFERENCIAS_SEM4 / "extracciones"


def probar_recepcion(cliente, modelo: str, carpeta: Path) -> list[dict]:
    """A. Cada Excel de la semana 4, de nuevo, contra su receta congelada (sin las 'decisiones': son texto libre)."""
    filas = []
    for congelada in sorted(CARPETA_RECEPCION_REFERENCIA.glob("*.json")):
        antes = json.loads(congelada.read_text(encoding="utf-8"))
        ahora = recibir(cliente, modelo, CARPETA_PROYECTO / antes["ruta"], de_nuevo=True, carpeta=carpeta)
        sin_decisiones = [{k: v for k, v in (r or {}).items() if k != "decisiones"} for r in (antes["receta"], ahora["receta"])]
        filas.append({"archivo": antes["archivo"], "entra": ahora["receta"] is not None, "problemas": ahora["problemas"],
                      "igual_a_la_semana_4": sin_decisiones[0] == sin_decisiones[1], "costo_usd": ahora["costo_usd"]})
    return filas


def probar_extractor(cliente, modelo: str) -> list[dict]:
    """B. La llamada 2 de cada PDF, de nuevo, con las filas de la extracción congelada."""
    filas_por_pdf = []
    for archivo in ("LHS_catalogo_nuevos_productos", "Lista_de_precios_octubre_2026"):
        extraccion = json.loads((EXTRACCIONES / f"{archivo}.json").read_text(encoding="utf-8"))
        columnas = COLUMNAS_POR_PDF[f"{archivo}.pdf"]
        # La fila tal como llegó de la llamada 1: con su pie de página (la extracción lo guarda aparte) y "abierta" si
        # es la última (la que trae el pie), como en la extracción real
        filas = {p["codigo"]: {"codigo": p["codigo"], "pagina": p["fuente"]["pagina"],
                               "fila": f"{p['fila']} {p['texto_ajeno']}" if p["texto_ajeno"] else p["fila"],
                               "cerrada": not p["texto_ajeno"]}
                 for p in extraccion["productos"]}
        respuesta = pedir_campos(cliente, modelo, filas, columnas)
        productos, problemas = campos_desde_respuesta(respuesta["content"], filas, columnas)
        distintos = [p["codigo"] for p, antes in zip(productos, extraccion["productos"])
                     if (p["campos"], p["texto_ajeno"]) != (antes["campos"], antes["texto_ajeno"])]
        filas_por_pdf.append({"archivo": archivo, "productos": len(productos), "distintos": distintos,
                              "con_problemas": [p["codigo"] for p in productos if p["problemas"]] + problemas,
                              "costo_usd": round(costo_usd(respuesta), 6)})
    return filas_por_pdf


def probar_catalogo(cliente, modelo: str, carpeta: Path) -> dict:
    """C. La primera tanda de productos 'criterio', contra la variante que decidió la semana 3."""
    criterio = [p for p in (clasificar(fila) for fila in leer_catalogo()) if p["estado"] == "criterio"][:TANDA]
    resuelta = resolver_tanda(cliente, modelo, criterio, carpeta)
    semana_3 = {}
    for producto in json.loads(RUTA_CATALOGO_SEM3.read_text(encoding="utf-8"))["productos"]:
        variante = next((c["propuesto"] for c in producto["cambios"] if c["campo"] == "variante"), None)
        semana_3[producto["sku"]] = variante
    distintas = []
    for sku, respuesta in resuelta["validas"].items():
        ahora = sin_tildes(" ".join(respuesta["variante"].split())) if respuesta["variante"] else None
        if ahora != semana_3.get(sku):
            distintas.append({"sku": sku, "semana_3": semana_3.get(sku), "ahora": ahora, "por_que": respuesta["por_que"]})
    return {"productos": len(criterio), "validas": len(resuelta["validas"]), "sin_propuesta": resuelta["sin_propuesta"],
            "distintas_a_la_semana_3": distintas, "costo_usd": round(resuelta["costo_usd"], 6)}


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    carpeta = Path(tempfile.mkdtemp())  # recepciones y llamadas de esta prueba: no pisan nada real

    print("Corriendo las 3 pruebas a la vez (recepcionista, extractor y catálogo viejo)...\n", flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        a = pool.submit(probar_recepcion, cliente, modelo, carpeta / "recepcion")
        b = pool.submit(probar_extractor, cliente, modelo)
        c = pool.submit(probar_catalogo, cliente, modelo, carpeta / "catalogo")
        recepcion, extractor, catalogo = a.result(), b.result(), c.result()

    print("A. Recepcionista (tool forzada + strict) contra las recetas de la semana 4:")
    for r in recepcion:
        marca = "✔ igual" if r["entra"] and r["igual_a_la_semana_4"] else f"✖ entra={r['entra']} problemas={r['problemas']}"
        print(f"   {r['archivo']:<38} {marca} · US$ {r['costo_usd']:.5f}")
    print("B. Extractor, llamada 2 (tool forzada + strict) contra la extracción congelada:")
    for e in extractor:
        marca = "✔ iguales" if not e["distintos"] and not e["con_problemas"] else \
            f"✖ distintos {e['distintos']} · con problemas {e['con_problemas']}"
        print(f"   {e['archivo']:<38} {e['productos']} productos · {marca} · US$ {e['costo_usd']:.5f}")
    print("C. Catálogo viejo (output_config.format) contra la semana 3:")
    print(f"   {catalogo['validas']}/{catalogo['productos']} con la forma garantizada y validadas por el código · "
          f"sin propuesta: {len(catalogo['sin_propuesta'])} · US$ {catalogo['costo_usd']:.5f}")
    for d in catalogo["distintas_a_la_semana_3"]:
        print(f"   ≠ {d['sku']}: semana 3 {d['semana_3']!r} · ahora {d['ahora']!r} ({d['por_que']})")
    costo = sum(r["costo_usd"] for r in recepcion) + sum(e["costo_usd"] for e in extractor) + catalogo["costo_usd"]
    print(f"\nCosto total: US$ {costo:.4f}")

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo,
                                       "recepcion": recepcion, "extractor": extractor, "catalogo": catalogo,
                                       "costo_usd": round(costo, 6)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()
