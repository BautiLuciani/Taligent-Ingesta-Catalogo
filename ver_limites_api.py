"""Paso 2 (semana 3): ¿cuántos fichadores pueden trabajar a la vez sin chocar con los límites de la cuenta?

En vez de probar hasta que salte un error 429, se le pregunta a la API: cada respuesta trae en sus encabezados
los límites de la cuenta (pedidos, tokens de entrada y de salida por minuto, M6). Se hace UNA llamada mínima.
Después se calcula, con las corridas reales ya guardadas (salida/corrida_P0x.json), cuántos tokens por minuto
gasta UN fichador trabajando solo, y cuántos entran a la vez dejando un margen.

Correr: python ver_limites_api.py      (~US$ 0,00001)
"""
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

CARPETA_PROYECTO = Path(__file__).parent
MARGEN = 0.8  # usar hasta el 80% del límite: los tokens por minuto no son parejos (hay picos)


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()

    # Una llamada mínima: sin thinking (si no, con max_tokens chico se va todo en pensar, M4 §1.4)
    crudo = cliente.messages.with_raw_response.create(
        model=modelo, max_tokens=16, thinking={"type": "disabled"},
        messages=[{"role": "user", "content": "Decí OK."}],
    )
    limites = {nombre: valor for nombre, valor in crudo.headers.items() if nombre.startswith("anthropic-ratelimit")}
    print("Límites de la cuenta (encabezados de la respuesta):")
    for nombre, valor in sorted(limites.items()):
        print(f"  {nombre}: {valor}")
    if not limites:
        sys.exit("La respuesta no trajo encabezados de límites: no se puede calcular.")

    # Lo que gasta UN fichador por minuto, medido en las corridas reales (cada una fue de a una tanda por vez)
    print("\nLo que gasta un fichador trabajando solo (corridas guardadas):")
    entrada, salida, segundos = 0, 0, 0.0
    for ruta in sorted((CARPETA_PROYECTO / "salida").glob("corrida_P0*.json")):
        corrida = json.loads(ruta.read_text(encoding="utf-8"))
        entrada += corrida["input_tokens"]
        salida += corrida["output_tokens"]
        segundos += corrida["segundos"]
        print(f"  {ruta.name}: {corrida['input_tokens'] / corrida['segundos'] * 60:>8,.0f} tokens de entrada/min · "
              f"{corrida['output_tokens'] / corrida['segundos'] * 60:>7,.0f} de salida/min")
    por_minuto = {"input": entrada / segundos * 60, "output": salida / segundos * 60}
    print(f"  promedio: {por_minuto['input']:,.0f} de entrada/min · {por_minuto['output']:,.0f} de salida/min")

    print(f"\nCuántos fichadores a la vez (usando hasta el {MARGEN:.0%} de cada límite):")
    for tipo in ("input", "output"):
        limite = limites.get(f"anthropic-ratelimit-{tipo}-tokens-limit")
        if limite is None:
            print(f"  {tipo}: la respuesta no trae ese límite")
            continue
        cuantos = int(int(limite) * MARGEN // por_minuto[tipo])
        print(f"  tokens de {'entrada' if tipo == 'input' else 'salida'}: límite {int(limite):,}/min "
              f"-> hasta {cuantos} fichadores")


if __name__ == "__main__":
    main()