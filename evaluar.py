"""Evaluador: compara las fichas que generó el agente contra los casos verificados a mano.

Correr: python evaluar.py
"""
import json
from collections import Counter
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
RUTA_CASOS = CARPETA_PROYECTO / "evaluacion" / "casos_litoral.json"
RUTA_RESULTADOS = CARPETA_PROYECTO / "salida" / "resultados.json"


def iguales(esperado, obtenido) -> bool:
    """Compara dos valores de la ficha. Números con tolerancia mínima (68.91 vs 68.910000001)."""
    if isinstance(esperado, (int, float)) and isinstance(obtenido, (int, float)):
        return abs(esperado - obtenido) < 0.001
    return esperado == obtenido


def comparar_caso(esperado: dict, obtenido: dict | None) -> tuple[list[str], list[str], list[str]]:
    """Devuelve (errores_de_ficha, errores_de_fuente, campos_mal) de un caso."""
    if obtenido is None:
        return ["el agente no registró este producto"], ["sin fuentes"], ["(no registrado)"]

    errores, errores_fuente, campos_mal = [], [], []

    # 1) El "sobre": estado, duplicado_de y motivos (los motivos sin importar el orden)
    for clave in ("estado", "duplicado_de"):
        if esperado[clave] != obtenido.get(clave):
            errores.append(f"{clave}: esperado {esperado[clave]!r}, obtenido {obtenido.get(clave)!r}")
            campos_mal.append(clave)
    if sorted(esperado["motivos_revision"]) != sorted(obtenido.get("motivos_revision", [])):
        errores.append(f"motivos: esperado {esperado['motivos_revision']}, obtenido {obtenido.get('motivos_revision')}")
        campos_mal.append("motivos_revision")

    # 2) Cada campo de la ficha
    ficha_obtenida = obtenido.get("ficha", {})
    for campo, valor_esperado in esperado["ficha"].items():
        valor_obtenido = ficha_obtenida.get(campo)
        if not iguales(valor_esperado, valor_obtenido):
            if valor_esperado is None:
                detalle = f"debía quedar vacío y se completó con {valor_obtenido!r}"  # inventar es peor (guía)
            else:
                detalle = f"esperado {valor_esperado!r}, obtenido {valor_obtenido!r}"
            errores.append(f"{campo}: {detalle}")
            campos_mal.append(campo)

    # 3) La fuente de cada campo completado (archivo y línea)
    fuentes_obtenidas = obtenido.get("fuentes", {})
    for campo, fuente_esperada in esperado["fuentes"].items():
        if fuentes_obtenidas.get(campo) != fuente_esperada:
            errores_fuente.append(f"{campo}: esperada {fuente_esperada}, obtenida {fuentes_obtenidas.get(campo)}")

    return errores, errores_fuente, campos_mal


def main():
    casos = json.loads(RUTA_CASOS.read_text(encoding="utf-8"))
    resultados = json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))

    fichas_ok = fuentes_ok = 0
    campos_con_error = Counter()
    for caso in casos:
        item_id = caso["item_id"]
        errores, errores_fuente, campos_mal = comparar_caso(caso["esperado"], resultados.get(item_id))
        fichas_ok += not errores
        fuentes_ok += not errores_fuente
        campos_con_error.update(campos_mal)

        marca = "OK " if not errores and not errores_fuente else "MAL"
        print(f"[{marca}] {item_id} — {caso['por_que']}")
        for error in errores:
            print(f"        ficha  · {error}")
        for error in errores_fuente:
            print(f"        fuente · {error}")

    total = len(casos)
    print(f"\n=== Acierto de ficha (entera): {fichas_ok}/{total} = {fichas_ok / total:.0%}")
    print(f"=== Acierto de fuente:         {fuentes_ok}/{total} = {fuentes_ok / total:.0%}")
    if campos_con_error:
        print("Diagnóstico, campos con error: " + ", ".join(f"{c} ({n})" for c, n in campos_con_error.most_common()))


if __name__ == "__main__":
    main()