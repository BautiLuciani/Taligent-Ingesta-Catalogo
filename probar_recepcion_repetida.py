"""Semana 5, paso 3D (seguimiento): ¿el recepcionista con strict entra SIEMPRE, con la receta de la semana 4? No toca el sistema.

Historia: en probar_strict_formularios.py Higiene Total no entró, y repitiéndola 5 veces no entró 3 de 5: el modelo
anotaba en "columnas_que_no_van" una columna que SÍ usaba ("Costo: se usa como columna_precio, no va en
columnas_que_no_van"). Causa: el formulario preguntaba lo mismo dos veces. Arreglo (opción A, aprobada): la lista ya no
se pregunta, la calcula el código. Primera corrida (con la lista) guardada en recepcion_repetida_sem5/v1..v5.

Esta prueba mide el arreglo: Higiene Total 5 veces y Rivera y Norte 2 veces cada uno, a la vez. Cada resultado se guarda
ENTERO (con la propuesta del modelo) en salida/experimentos/recepcion_repetida_sem5/arreglo/<archivo>_vN/ y cada receta
se compara con la de la semana 4 (congelada y verificada por Bauti), sin las "decisiones" (texto libre y lo que ahora
calcula el código).

Correr: python probar_recepcion_repetida.py   (paga ~US$ 0,005)
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from referencias import CARPETA_RECEPCION_REFERENCIA  # las recetas de la semana 4, congeladas
from recepcion import recibir  # noqa: E402

CARPETA_PROYECTO = Path(__file__).parent
CARPETA = CARPETA_PROYECTO / "salida" / "experimentos" / "recepcion_repetida_sem5" / "arreglo"
VECES = {"P04_HigieneTotal_novedades": 5, "P02_ALTAS RIVERA OCT": 2, "P08_NorteImports_new_items_Q4": 2}


def sin_decisiones(receta: dict | None) -> dict | None:
    return {k: v for k, v in receta.items() if k != "decisiones"} if receta else None


def una_vez(cliente, modelo: str, nombre: str, numero: int) -> dict:
    """Una recepción en su propia carpeta: las llamadas y los resultados de cada vez no se pisan."""
    antes = json.loads((CARPETA_RECEPCION_REFERENCIA / f"{nombre}.json").read_text(encoding="utf-8"))
    resultado = recibir(cliente, modelo, CARPETA_PROYECTO / antes["ruta"], de_nuevo=True,
                        carpeta=CARPETA / f"{nombre}_v{numero}")
    receta = resultado["receta"]
    return {"archivo": antes["archivo"], "vez": numero, "entra": receta is not None, "problemas": resultado["problemas"],
            "igual_a_la_semana_4": sin_decisiones(receta) == sin_decisiones(antes["receta"]),
            "no_van": [c["columna"] for c in receta["decisiones"]["columnas_que_no_van"]] if receta else None,
            "costo_usd": resultado["costo_usd"]}


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()

    pedidos = [(nombre, n) for nombre, veces in VECES.items() for n in range(1, veces + 1)]
    print(f"{len(pedidos)} recepciones a la vez (Higiene Total 5, Rivera 2, Norte 2)...\n", flush=True)
    with ThreadPoolExecutor(max_workers=len(pedidos)) as pool:
        veces = list(pool.map(lambda pedido: una_vez(cliente, modelo, *pedido), pedidos))

    for v in veces:
        if v["entra"]:
            marca = "✔ entra · " + ("igual a la semana 4" if v["igual_a_la_semana_4"] else "DISTINTA a la semana 4")
        else:
            marca = f"✖ no entra: {v['problemas']}"
        print(f"{v['archivo']:<32} v{v['vez']}: {marca} · no van (código): {v['no_van']}")
    bien = sum(1 for v in veces if v["entra"] and v["igual_a_la_semana_4"])
    costo = sum(v["costo_usd"] for v in veces)
    print(f"\nEntraron con la receta de la semana 4: {bien} de {len(veces)} · US$ {costo:.4f}")
    (CARPETA / "resumen.json").write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo,
                                                      "veces": veces, "bien": bien, "costo_usd": round(costo, 6)},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
    print("Cada resultado completo en salida/experimentos/recepcion_repetida_sem5/arreglo/ · resumen en arreglo/resumen.json")


if __name__ == "__main__":
    main()
