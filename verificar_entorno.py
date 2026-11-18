"""Chequea que el entorno esté listo antes de correr el sistema.

Semana 1: Python, .env, datos y API.
Semana 6: además avisa si una variable de Windows pisa la key del .env.
Todos los scripts usan load_dotenv, que NO pisa una variable que ya existe:
si Windows tiene otra ANTHROPIC_API_KEY, gana esa y no la del .env
(pasó en la semana 5: una clave vieja de Windows daba 401).
"""
import os
import sys
from importlib.metadata import version
from pathlib import Path

import anthropic
from dotenv import dotenv_values, load_dotenv

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_DATA = CARPETA_PROYECTO / "Data"
CSV_LITORAL = CARPETA_DATA / "proveedores" / "P03_Distribuidora_Litoral" / "litoral_altas_102026.csv"

# Precios de Haiku 5.5 en USD por millón de tokens (módulo 6)
PRECIO_INPUT = 0.10
PRECIO_OUTPUT = 0.50

# Cómo borrar la variable de Windows (usuario) desde PowerShell
COMO_BORRAR = (
    "   Para borrarla (PowerShell):\n"
    "     [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $null, 'User')\n"
    "   y después cerrá y volvé a abrir VS Code (la terminal vieja la sigue teniendo)."
)


def mostrar_key(key: str) -> str:
    """La key sin mostrarla: el principio (dice qué tipo de clave es) y las últimas 4."""
    if len(key) <= 16:
        return f"({len(key)} caracteres)"
    return f"{key[:10]}...{key[-4:]}"


def revisar_key(del_sistema: str | None, del_env: str | None) -> tuple[bool, str]:
    """Decide qué key va a usar el sistema de verdad.

    del_sistema: ANTHROPIC_API_KEY que ya existía ANTES de leer el .env (Windows).
    del_env: la que está escrita en el .env.
    Devuelve (ok, mensaje). Es una función pura para poder probarla sin tocar Windows.
    """
    if not del_env:
        if del_sistema:
            return False, (
                "ERROR: el .env no tiene ANTHROPIC_API_KEY y se usaría la de Windows "
                f"({mostrar_key(del_sistema)}). Poné la key en el .env.\n" + COMO_BORRAR
            )
        return False, "ERROR: falta ANTHROPIC_API_KEY en el .env"
    if del_sistema and del_sistema != del_env:
        return False, (
            "ERROR: Windows tiene otra ANTHROPIC_API_KEY y le gana al .env.\n"
            f"   Windows: {mostrar_key(del_sistema)}  |  .env: {mostrar_key(del_env)}\n"
            "   Todos los scripts usarían la de Windows, no la del .env.\n" + COMO_BORRAR
        )
    if del_sistema:
        return True, f"key OK ({mostrar_key(del_env)}); Windows tiene la misma, no molesta"
    return True, f"key OK ({mostrar_key(del_env)}), sale del .env"


def main():
    # 1) Python y librerías instaladas
    print(f"1) Python {sys.version.split()[0]}")
    for paquete in ["anthropic", "fastmcp", "openpyxl", "python-dotenv", "pyyaml"]:
        print(f"   {paquete} {version(paquete)}")

    # 2) La key: primero miramos la de Windows (ANTES de leer el .env) y la del .env por separado
    archivo_env = CARPETA_PROYECTO / ".env"
    if not archivo_env.exists():
        sys.exit("ERROR: no existe el archivo .env en la carpeta del proyecto")
    del_sistema = os.environ.get("ANTHROPIC_API_KEY")
    valores_env = dotenv_values(archivo_env)
    ok, mensaje = revisar_key(del_sistema, valores_env.get("ANTHROPIC_API_KEY"))
    if not ok:
        sys.exit(mensaje)
    load_dotenv(archivo_env)
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    print(f"2) .env OK - {mensaje}, modelo {modelo}")

    # 3) Los datos están donde esperamos
    if not CSV_LITORAL.exists():
        sys.exit(f"ERROR: no encuentro {CSV_LITORAL}")
    print(f"3) Data OK - CSV de Litoral encontrado ({CSV_LITORAL.stat().st_size} bytes)")

    # 4) La API responde (llamada mínima y barata)
    client = anthropic.Anthropic()  # toma la key del entorno solo
    try:
        respuesta = client.messages.create(
            model=modelo,
            max_tokens=1000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Respondé solo: entorno listo"}],
        )
    except anthropic.AuthenticationError:
        sys.exit("ERROR 401: la API rechazó la key (vencida o mal copiada). Generá una nueva y ponela en el .env.")
    except anthropic.APIConnectionError:
        sys.exit("ERROR: no hay conexión con la API (¿internet?).")
    # Haiku 5.5 piensa antes de responder: el texto NO está en content[0],
    # hay que buscar los bloques de tipo "text" (módulo 1)
    texto = "".join(b.text for b in respuesta.content if b.type == "text")
    uso = respuesta.usage
    costo = (uso.input_tokens * PRECIO_INPUT + uso.output_tokens * PRECIO_OUTPUT) / 1_000_000
    print(f"4) API OK - respuesta: {texto!r} (stop_reason: {respuesta.stop_reason})")
    print(f"   tokens: {uso.input_tokens} entrada / {uso.output_tokens} salida -> US$ {costo:.6f}")


if __name__ == "__main__":
    main()
