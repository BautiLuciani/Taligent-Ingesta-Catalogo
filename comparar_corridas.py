"""Compara dos resultados.json ficha por ficha (semana 4, paso 4). Sin IA, no gasta nada.

Sirve para probar que un cambio NO cambió las fichas: por defecto compara salida/resultados_anterior.json (lo que
había antes de la última escritura) con salida/resultados.json (lo nuevo). Usa la misma comparación que la medición
de la semana 3 (medir_paralelo.diferencias): estado, duplicado, motivos, cada campo y las fuentes; no la explicación
de la categoría, que es texto libre.
Correr: python comparar_corridas.py [anterior.json nuevo.json]
"""
import argparse
import json
from pathlib import Path

from medir_paralelo import diferencias

CARPETA_SALIDA = Path(__file__).parent / "salida"


def main():
    argumentos = argparse.ArgumentParser(description="Compara dos resultados.json ficha por ficha (gratis).")
    argumentos.add_argument("anterior", nargs="?", type=Path, default=CARPETA_SALIDA / "resultados_anterior.json")
    argumentos.add_argument("nuevo", nargs="?", type=Path, default=CARPETA_SALIDA / "resultados.json")
    opciones = argumentos.parse_args()
    anterior = json.loads(opciones.anterior.read_text(encoding="utf-8"))
    nuevo = json.loads(opciones.nuevo.read_text(encoding="utf-8"))
    distintas = diferencias(anterior, nuevo)
    print(f"{opciones.anterior.name}: {len(anterior)} fichas · {opciones.nuevo.name}: {len(nuevo)} fichas")
    if distintas:
        print(f"✘ {len(distintas)} diferencia(s):")
        for diferencia in distintas:
            print(f"  - {diferencia}")
    else:
        print("✔ 0 diferencias: las mismas fichas, campo por campo y con las mismas fuentes")


if __name__ == "__main__":
    main()
