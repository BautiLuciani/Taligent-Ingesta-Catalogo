"""Paso 1: chequea que el entorno esté listo antes de escribir el agente."""
import os
import sys
from importlib.metadata import version
from pathlib import Path

import anthropic
from dotenv import load_dotenv

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_DATA = CARPETA_PROYECTO / "Data"
CSV_LITORAL = CARPETA_DATA / "proveedores" / "P03_Distribuidora_Litoral" / "litoral_altas_102026.csv"

# Precios de Haiku 5.5 en USD por millón de tokens (módulo 6)
PRECIO_INPUT = 0.10
PRECIO_OUTPUT = 0.50


def main():
    # 1) Python y librerías instaladas
    print(f"1) Python {sys.version.split()[0]}")
    for paquete in ["anthropic", "fastmcp", "python-dotenv", "pyyaml"]:
        print(f"   {paquete} {version(paquete)}")

    # 2) El .env se lee bien (nunca imprimimos la key)
    load_dotenv(CARPETA_PROYECTO / ".env")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    modelo = os.getenv("MODELO")
    if not api_key:
        sys.exit("ERROR: falta ANTHROPIC_API_KEY en el .env")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    print(f"2) .env OK - key cargada ({len(api_key)} caracteres), modelo {modelo}")

    # 3) Los datos están donde esperamos
    if not CSV_LITORAL.exists():
        sys.exit(f"ERROR: no encuentro {CSV_LITORAL}")
    print(f"3) Data OK - CSV de Litoral encontrado ({CSV_LITORAL.stat().st_size} bytes)")

    # 4) La API responde (llamada mínima y barata)
    client = anthropic.Anthropic()  # toma la key del entorno solo
    respuesta = client.messages.create(
        model=modelo,
        max_tokens=1000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Respondé solo: entorno listo"}],
    )
    # Haiku 5.5 piensa antes de responder: el texto NO está en content[0],
    # hay que buscar los bloques de tipo "text" (módulo 1)
    texto = "".join(b.text for b in respuesta.content if b.type == "text")
    uso = respuesta.usage
    costo = (uso.input_tokens * PRECIO_INPUT + uso.output_tokens * PRECIO_OUTPUT) / 1_000_000
    print(f"4) API OK - respuesta: {texto!r} (stop_reason: {respuesta.stop_reason})")
    print(f"   tokens: {uso.input_tokens} entrada / {uso.output_tokens} salida -> US$ {costo:.6f}")


if __name__ == "__main__":
    main()