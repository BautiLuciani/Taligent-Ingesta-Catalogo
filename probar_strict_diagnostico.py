"""Semana 5, paso 1 (B2): diagnóstico de "Grammar compilation timed out". No toca el sistema.

La variante B de probar_strict.py respetaba los topes visibles (0 uniones, 19 opcionales) y aun así la API no
pudo compilar el formulario en 180 s. Acá se prueba UNA sospecha por formulario para saber cuál es la causa,
en vez de adivinar. Los 5 corren a la vez (un timeout tarda varios minutos). Pedido mínimo y tool forzada: lo que
importa es si COMPILA, no la respuesta.

Primera versión: un timeout de NUESTRO lado (no un 400) tiró abajo el programa y se perdieron los otros 4
resultados. Ahora cada formulario ataja cualquier error y lo anota, y cada resultado se imprime apenas llega
(misma regla que el orquestador de la semana 3: si uno falla, no arrastra a los demás).

Correr: python probar_strict_diagnostico.py   (paga < US$ 0,005; lo que no compila no se cobra)
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from probar_strict import BASE, CAMPOS, COMUNES, SIEMPRE, contar

CARPETA_PROYECTO = Path(__file__).parent
RUTA_SALIDA = CARPETA_PROYECTO / "salida" / "experimentos" / "strict_diagnostico_sem5.json"
PEDIDO = "Es una prueba: registrá un producto de ejemplo cualquiera con la tool."
TIMEOUT_NUESTRO = 600  # segundos: más que los 180 s de compilación de la API, con margen


def sin_enum(esquema: dict) -> dict:
    return {k: v for k, v in esquema.items() if k != "enum"}


def o_null(esquema: dict) -> dict:
    """'Este tipo o null', bien escrito: anyOf con dos opciones (corrige el error de la variante A)."""
    return {"anyOf": [esquema, {"type": "null"}]}


def objeto(propiedades: dict, obligatorias: list) -> dict:
    return {"type": "object", "properties": propiedades, "required": obligatorias, "additionalProperties": False}


def ficha_opcional(con_enums: bool) -> dict:
    """Los 14 campos que pueden faltar, opcionales (sin null)."""
    props = {c: BASE[c] if con_enums else sin_enum(BASE[c]) for c in CAMPOS}
    return objeto(props, [c for c in CAMPOS if c in SIEMPRE])


def ficha_obligatoria() -> dict:
    """Todos los campos obligatorios; los que pueden faltar, 'tipo o null' (anyOf). Con enums."""
    return objeto({c: BASE[c] if c in SIEMPRE else o_null(BASE[c]) for c in CAMPOS}, CAMPOS)


FUENTE_LISTA_OPCIONAL = {"type": "array", "items": objeto(
    {"campo": {"type": "string", "enum": CAMPOS}, "archivo": {"type": "string"}, "pagina": {"type": "integer"},
     "hoja": {"type": "string"}, "fila": {"type": "integer"}, "linea": {"type": "integer"}}, ["campo", "archivo"])}

# Diseño C: casilleros fijos (sin opcionales ni uniones); el código la convierte a la forma de la guía después
FUENTE_LISTA_FIJA = {"type": "array", "items": objeto(
    {"campo": {"type": "string", "enum": CAMPOS}, "archivo": {"type": "string"},
     "tipo_ubicacion": {"type": "string", "enum": ["pagina", "hoja_fila", "linea"]},
     "numero": {"type": "integer"},
     "hoja": {"type": "string", "description": "Nombre de la hoja si es un Excel; vacío en los demás casos."}},
    ["campo", "archivo", "tipo_ubicacion", "numero", "hoja"])}

FORMULARIOS = {
    "1. ficha 14 opcionales, sin enums": objeto({"ficha": ficha_opcional(False)}, ["ficha"]),
    "2. ficha 14 opcionales, con enums": objeto({"ficha": ficha_opcional(True)}, ["ficha"]),
    "3. ficha obligatoria con anyOf null": objeto({"ficha": ficha_obligatoria()}, ["ficha"]),
    "4. fuentes lista 4 opcionales": objeto({"fuentes": FUENTE_LISTA_OPCIONAL}, ["fuentes"]),
    "5. C completa": objeto({**COMUNES, "ficha": ficha_obligatoria(), "fuentes": FUENTE_LISTA_FIJA,
                             "duplicado_de": o_null({"type": "string"})},
                            [*COMUNES, "ficha", "fuentes", "duplicado_de"]),
}


def probar(cliente, modelo: str, nombre: str, esquema: dict) -> dict:
    """Una llamada mínima con la tool en strict y forzada. Mide cuánto tardó y si compiló.

    Nunca lanza una excepción: cualquier error queda anotado con su tipo, para no perder los otros resultados.
    """
    tool = {"name": "registrar_ficha", "description": "Registra el resultado de un ítem.", "strict": True,
            "input_schema": esquema}
    inicio = time.perf_counter()
    try:
        respuesta = cliente.messages.create(
            model=modelo, max_tokens=2_000, tools=[tool],
            tool_choice={"type": "tool", "name": "registrar_ficha"},  # forzada: sin thinking, barata
            messages=[{"role": "user", "content": PEDIDO}], output_config={"effort": "low"},
        )
        entrada = next((b.input for b in respuesta.content if b.type == "tool_use"), None)
        resultado = {"compilo": True, "stop_reason": respuesta.stop_reason, "input": entrada}
    except anthropic.BadRequestError as error:        # 400 de la API (schema inválido o "compilation timed out")
        resultado = {"compilo": False, "error": f"400 de la API: {error.message}"}
    except anthropic.APITimeoutError:                  # NUESTRO tope: la API no contestó en TIMEOUT_NUESTRO s
        resultado = {"compilo": False, "error": f"sin respuesta en {TIMEOUT_NUESTRO} s (timeout nuestro)"}
    except Exception as error:                         # cualquier otra cosa: se anota, no se cae
        resultado = {"compilo": False, "error": f"{type(error).__name__}: {error}"}
    return {"formulario": nombre, **contar(esquema), "segundos": round(time.perf_counter() - inicio, 1), **resultado}


def mostrar(r: dict) -> None:
    marca = "✔ compiló" if r["compilo"] else f"✖ {r['error'][:110]}"
    print(f"{r['formulario']:<38} {r['uniones']:>2} uniones · {r['opcionales']:>2} opcionales · "
          f"{r['segundos']:>5} s · {marca}", flush=True)


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    # sin reintentos: un timeout repetido sería esperar de más (y es justo lo que queremos ver)
    cliente = anthropic.Anthropic(timeout=TIMEOUT_NUESTRO, max_retries=0)

    print(f"Probando {len(FORMULARIOS)} formularios a la vez; cada uno se muestra apenas termina...\n", flush=True)
    resultados = []
    with ThreadPoolExecutor(max_workers=len(FORMULARIOS)) as pool:
        futuros = [pool.submit(probar, cliente, modelo, nombre, esquema) for nombre, esquema in FORMULARIOS.items()]
        for futuro in as_completed(futuros):  # en el orden en que TERMINAN, no en el que se pidieron
            resultados.append(futuro.result())
            mostrar(resultados[-1])

    resultados.sort(key=lambda r: r["formulario"])
    completa = next(r for r in resultados if r["formulario"].startswith("5."))
    if completa["compilo"]:
        print(f"\nEjemplo del formulario C (lo que inventó para la prueba):\n"
              f"{json.dumps(completa['input'], ensure_ascii=False)}")

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo,
                                       "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()