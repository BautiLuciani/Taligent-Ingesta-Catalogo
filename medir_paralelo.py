"""Medición del paso 8 (semana 3): la corrida de fichas completa con 1 fichador y con 3. Lo único que cambia es eso.

Por cada cantidad de fichadores:
  1. Corre el orquestador tal cual lo correrías vos (python orquestador.py --fichas --fichadores N): los 5 proveedores,
     reusando las lecturas guardadas (así una lectura que varía no ensucia la comparación; la lectura se midió en el paso 3).
  2. Guarda una copia de resultados.json de esa corrida (salida/medicion_paralelo/resultados_N.json).
  3. Corre el evaluador sobre todos los archivos de casos (evaluacion/casos_*.json).
Al final compara las dos corridas ficha por ficha (estado, motivos, duplicado, cada campo y cada fuente) y guarda todo en
salida/medicion_paralelo.json. El gráfico de carriles lo arma después carriles.py con las mediciones de cada corrida.

Correr: python medir_paralelo.py      (~US$ 0,45 y ~17 min: dos corridas completas de fichas)
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from evaluar import comparar_caso

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
CARPETA_MEDICION = CARPETA_SALIDA / "medicion_paralelo"
CORRIDAS = [1, 3]  # cuántos fichadores a la vez: 1 = de a una tanda (la versión secuencial), 3 = el tope del paso 2


def evaluar_todo(resultados: dict) -> dict:
    """El evaluador sobre todos los archivos de casos. Devuelve, por archivo y en total, cuántas fichas y fuentes dan bien."""
    por_archivo, mal = {}, []
    for ruta in sorted((CARPETA_PROYECTO / "evaluacion").glob("casos_*.json")):
        casos = json.loads(ruta.read_text(encoding="utf-8"))
        fichas = fuentes = 0
        for caso in casos:
            errores, errores_fuente, _ = comparar_caso(caso["esperado"], resultados.get(caso["item_id"]))
            fichas += not errores
            fuentes += not errores_fuente
            if errores or errores_fuente:
                mal.append({"item_id": caso["item_id"], "errores": errores, "errores_fuente": errores_fuente})
        por_archivo[ruta.name] = {"casos": len(casos), "fichas_ok": fichas, "fuentes_ok": fuentes}
    total = {clave: sum(a[clave] for a in por_archivo.values()) for clave in ("casos", "fichas_ok", "fuentes_ok")}
    return {"total": total, "por_archivo": por_archivo, "mal": mal}


def diferencias(a: dict, b: dict) -> list[str]:
    """Qué cambia entre dos corridas, ficha por ficha. No se compara la explicación de la categoría (es texto libre)."""
    distintas = [f"{item_id}: solo en una de las dos corridas" for item_id in sorted(set(a) ^ set(b))]
    for item_id in sorted(set(a) & set(b)):
        x, y = a[item_id], b[item_id]
        for clave in ("estado", "duplicado_de"):
            if x.get(clave) != y.get(clave):
                distintas.append(f"{item_id}.{clave}: {x.get(clave)!r} vs {y.get(clave)!r}")
        if sorted(x.get("motivos_revision", [])) != sorted(y.get("motivos_revision", [])):
            distintas.append(f"{item_id}.motivos: {x.get('motivos_revision')} vs {y.get('motivos_revision')}")
        for campo in sorted(set(x["ficha"]) | set(y["ficha"])):
            if x["ficha"].get(campo) != y["ficha"].get(campo):
                distintas.append(f"{item_id}.{campo}: {x['ficha'].get(campo)!r} vs {y['ficha'].get(campo)!r}")
        if x.get("fuentes") != y.get("fuentes"):
            distintas.append(f"{item_id}.fuentes distintas")
    return distintas


def main():
    # Sin opciones, pero con argparse: así "python medir_paralelo.py --help" explica y NO arranca una corrida que se paga
    argparse.ArgumentParser(description="Corre las fichas con 1 y con 3 fichadores y las compara (~US$ 0,45, ~17 min).").parse_args()
    CARPETA_MEDICION.mkdir(parents=True, exist_ok=True)
    corridas = {}
    for fichadores in CORRIDAS:
        print(f"\n▶ Corrida con {fichadores} fichador(es) ...", flush=True)
        inicio = time.perf_counter()
        # Sin capturar la salida: el orquestador escribe directo en la consola (en Windows, capturarla rompe los "✔")
        proceso = subprocess.run([sys.executable, "orquestador.py", "--fichas", "--fichadores", str(fichadores)],
                                 cwd=CARPETA_PROYECTO)
        if proceso.returncode != 0:
            sys.exit(f"✖ Falló la corrida con {fichadores} fichador(es) (código {proceso.returncode}). Se frena la medición.")
        segundos_total = time.perf_counter() - inicio

        medicion = json.loads((CARPETA_SALIDA / f"medicion_fichas_{fichadores}.json").read_text(encoding="utf-8"))
        if medicion["escritor"]["frenados"]:  # un proveedor sin escribir tendría las fichas de OTRA corrida: no sirve
            sys.exit(f"✖ El escritor frenó a {list(medicion['escritor']['frenados'])}: la comparación no sería justa.")
        copia = CARPETA_MEDICION / f"resultados_{fichadores}.json"
        shutil.copyfile(CARPETA_SALIDA / "resultados.json", copia)
        resultados = json.loads(copia.read_text(encoding="utf-8"))
        corridas[fichadores] = {
            "segundos_fichas": medicion["segundos"],
            "segundos_con_todo": round(segundos_total, 1),  # incluye levantar el orquestador, la etapa 1 y el escritor
            "costo_usd": medicion["costo_usd"],
            "tandas": len(medicion["tandas"]),
            "propuestas": medicion["propuestas"],
            "tandas_con_problemas": medicion["tandas_con_problemas"],
            "evaluador": evaluar_todo(resultados),
            "resultados": copia.name,
        }

    uno, tres = (json.loads((CARPETA_MEDICION / f"resultados_{n}.json").read_text(encoding="utf-8")) for n in CORRIDAS)
    distintas = diferencias(uno, tres)
    resumen = {"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "corridas": corridas,
               "aceleracion": round(corridas[1]["segundos_fichas"] / corridas[3]["segundos_fichas"], 2),
               "diferencias_entre_corridas": distintas}
    ruta = CARPETA_SALIDA / "medicion_paralelo.json"
    ruta.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Medición del paso 8: 1 fichador vs 3 (las mismas 15 tandas, los 5 proveedores)")
    print(f"{'fichadores':<12}{'fichas (s)':>11}{'con todo (s)':>14}{'US$':>9}{'propuestas':>12}{'evaluador':>12}")
    for fichadores, c in corridas.items():
        evaluador = c["evaluador"]["total"]
        print(f"{fichadores:<12}{c['segundos_fichas']:>11.1f}{c['segundos_con_todo']:>14.1f}{c['costo_usd']:>9.4f}"
              f"{c['propuestas']:>12}{str(evaluador['fichas_ok']) + '/' + str(evaluador['casos']):>12}")
        for problema in c["tandas_con_problemas"]:
            print(f"   ⚠ {problema}")
        for caso in c["evaluador"]["mal"]:
            print(f"   ✖ evaluador: {caso['item_id']}: {(caso['errores'] + caso['errores_fuente'])[:3]}")
    print(f"\nCon 3 fichadores, las fichas tardan {resumen['aceleracion']}x menos.")
    print(f"Diferencias entre las dos corridas: {len(distintas)}")
    for diferencia in distintas[:15]:
        print(f"   ≠ {diferencia}")
    print(f"Guardado en salida/{ruta.name} (y una copia de cada resultados.json en salida/{CARPETA_MEDICION.name}/)")
    print("Gráfico de carriles: python carriles.py")


if __name__ == "__main__":
    main()