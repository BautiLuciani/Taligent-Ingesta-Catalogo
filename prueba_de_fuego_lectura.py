"""Prueba de fuego del paso 1b (semana 3): ¿la lectura de los PDF sale SIEMPRE completa e igual?

Lee los PDF desde cero (--de-nuevo) VECES veces cada uno y compara cada resultado contra la versión del último
commit (la de la semana 2, verificada con el evaluador), producto por producto, en el mismo orden, y la vigencia.
Anota cuántas rondas dirigidas hicieron falta, el tiempo y el costo de cada lectura.

Versión 2: cada lectura se GUARDA (salida/experimentos/prueba_de_fuego/) y, si no es igual, se dice QUÉ difiere.
(En la versión 1 una lectura dio "distinta" y no se pudo saber por qué: el git restore borró la evidencia.)

Correr: python prueba_de_fuego_lectura.py           (Andes y LHS; ~US$ 0,08 y ~4 min)
        python prueba_de_fuego_lectura.py andes     (solo Andes)
Después: git restore salida/extracciones            (las lecturas del commit; las copias de la prueba quedan aparte)
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
PROVEEDORES = CARPETA_PROYECTO / "Data" / "proveedores"
CARPETA_PRUEBA = CARPETA_PROYECTO / "salida" / "experimentos" / "prueba_de_fuego"
VECES = 3
PDFS = {
    "andes": PROVEEDORES / "P01_Laboratorio_Andes" / "Lista_de_precios_octubre_2026.pdf",
    "lhs": PROVEEDORES / "P07_Limpieza_Hogar_Sur" / "LHS_catalogo_nuevos_productos.pdf",
}


def version_del_commit(ruta: Path) -> dict:
    """El resultado tal como está en el último commit (git show), para comparar contra algo fijo."""
    relativa = ruta.relative_to(CARPETA_PROYECTO).as_posix()
    texto = subprocess.run(["git", "show", f"HEAD:{relativa}"], cwd=CARPETA_PROYECTO,
                           capture_output=True, check=True).stdout.decode("utf-8")
    return json.loads(texto)


def diferencias(resultado: dict, referencia: dict) -> list[str]:
    """Qué difiere entre una lectura y la del commit: la vigencia, el orden y cada campo de cada producto."""
    distintas = []
    if resultado.get("vigencia") != referencia.get("vigencia"):
        distintas.append(f"vigencia: commit {referencia.get('vigencia')} · ahora {resultado.get('vigencia')}")
    codigos = [p["codigo"] for p in resultado["productos"]]
    codigos_ref = [p["codigo"] for p in referencia["productos"]]
    if sorted(codigos) != sorted(codigos_ref):
        distintas.append(f"productos: faltan {sorted(set(codigos_ref) - set(codigos))} · "
                         f"sobran {sorted(set(codigos) - set(codigos_ref))}")
    elif codigos != codigos_ref:
        distintas.append("orden de los productos distinto")
    por_codigo = {p["codigo"]: p for p in referencia["productos"]}
    for producto in resultado["productos"]:
        anterior = por_codigo.get(producto["codigo"], {})
        for clave, valor in producto.items():
            if anterior and valor != anterior.get(clave):
                distintas.append(f"{producto['codigo']}.{clave}: commit {anterior.get(clave)!r} · ahora {valor!r}")
    return distintas


def main():
    argumentos = argparse.ArgumentParser(description="Lee los PDF varias veces desde cero y compara con el commit.")
    argumentos.add_argument("cuales", nargs="?", choices=["andes", "lhs", "todos"], default="todos")
    cuales = argumentos.parse_args().cuales
    pdfs = list(PDFS.values()) if cuales == "todos" else [PDFS[cuales]]
    CARPETA_PRUEBA.mkdir(parents=True, exist_ok=True)

    lecturas = []
    for pdf in pdfs:
        ruta_resultado = CARPETA_PROYECTO / "salida" / "extracciones" / f"{pdf.stem}.json"
        referencia = version_del_commit(ruta_resultado)
        for vez in range(1, VECES + 1):
            print(f"\n▶ {pdf.stem}, lectura {vez}/{VECES} ...", flush=True)
            inicio = time.perf_counter()
            proceso = subprocess.run([sys.executable, "extractor_pdf.py", str(pdf), "--de-nuevo"], cwd=CARPETA_PROYECTO)
            segundos = time.perf_counter() - inicio
            if proceso.returncode != 0:
                sys.exit(f"✖ Falló la lectura (código {proceso.returncode}). Se frena la prueba.")

            copia = CARPETA_PRUEBA / f"{pdf.stem}_{vez}.json"  # la evidencia: el resultado de ESTA lectura
            shutil.copyfile(ruta_resultado, copia)
            resultado = json.loads(ruta_resultado.read_text(encoding="utf-8"))
            distintas = diferencias(resultado, referencia)
            lecturas.append({
                "pdf": pdf.name, "vez": vez, "segundos": round(segundos, 1),
                "costo_usd": resultado["costo_usd"]["total"], "rondas": resultado["rondas"],
                "productos": len(resultado["productos"]),
                "marcados": [p["codigo"] for p in resultado["productos"] if p["problemas"]],
                "problemas_generales": resultado["problemas"],
                "igual_al_commit": not distintas, "diferencias": distintas, "copia": copia.name,
            })

    print("\n=== Prueba de fuego de la lectura")
    print(f"{'PDF':<34}{'vez':>4}{'seg':>7}{'US$':>9}{'rondas':>8}{'prod.':>7}  igual al commit")
    for l in lecturas:
        print(f"{l['pdf']:<34}{l['vez']:>4}{l['segundos']:>7.0f}{l['costo_usd']:>9.4f}{l['rondas']:>8}"
              f"{l['productos']:>7}  {'SÍ' if l['igual_al_commit'] else 'NO'}")
        for diferencia in l["diferencias"][:8]:
            print(f"      ≠ {diferencia}")
    iguales = sum(l["igual_al_commit"] for l in lecturas)
    costo = sum(l["costo_usd"] for l in lecturas)
    print(f"\n{iguales}/{len(lecturas)} lecturas idénticas al commit · costo total US$ {costo:.4f}")

    ruta = CARPETA_PRUEBA / "resumen.json"
    ruta.write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "lecturas": lecturas},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resumen y copias de cada lectura en salida/experimentos/{CARPETA_PRUEBA.name}/")


if __name__ == "__main__":
    main()