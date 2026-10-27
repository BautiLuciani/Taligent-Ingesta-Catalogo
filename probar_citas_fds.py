"""Paso 4A de la semana 2: experimento con citations sobre una FDS (ficha de datos de seguridad).

No toca el sistema. Sirve para ver CÓMO cita la API la sección 1 (códigos) y la 14 (transporte)
de una FDS, que son líneas sueltas sin punto final, antes de diseñar el extractor de FDS.

Correr: python probar_citas_fds.py                          (la de la lavandina)
        python probar_citas_fds.py FDS_Clarita_multiuso.pdf (otra FDS de LHS)
"""
import base64
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_FDS = CARPETA_PROYECTO / "Data" / "proveedores" / "P07_Limpieza_Hogar_Sur" / "fichas_de_seguridad"
CARPETA_EXPERIMENTOS = CARPETA_PROYECTO / "salida" / "experimentos"

EFFORT = "high"       # el mismo que usa el agente
MAX_TOKENS = 16_000   # thinking + respuesta; sin streaming el SDK acepta hasta ~21.000

PRECIO_INPUT = 0.10   # USD por millón de tokens de entrada (Haiku 5.5)
PRECIO_OUTPUT = 0.50  # USD por millón de tokens de salida (el thinking se cobra como salida)

PREGUNTA = (
    "Copiá textual del documento, cada cosa en su propio párrafo:\n"
    "1. La línea que lista los códigos comerciales que cubre esta ficha.\n"
    "2. Lo que dice la sección 14 (transporte), línea por línea.\n"
    "Copiá solo lo que está escrito, sin agregar títulos, explicaciones ni resúmenes."
)


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    nombre_fds = sys.argv[1] if len(sys.argv) > 1 else "FDS_Clarita_lavandina.pdf"
    ruta_fds = CARPETA_FDS / nombre_fds
    if not ruta_fds.exists():
        sys.exit(f"ERROR: no existe {ruta_fds}")

    cliente = anthropic.Anthropic()
    pdf_base64 = base64.standard_b64encode(ruta_fds.read_bytes()).decode("utf-8")
    mensajes = [{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
                "title": ruta_fds.name,
                "citations": {"enabled": True},
            },
            {"type": "text", "text": PREGUNTA},  # la pregunta DESPUÉS del documento (M3)
        ],
    }]

    conteo = cliente.messages.count_tokens(model=modelo, messages=mensajes)
    print(f"{ruta_fds.name} · count_tokens: {conteo.input_tokens} tokens de entrada")

    respuesta = cliente.messages.create(
        model=modelo, max_tokens=MAX_TOKENS, messages=mensajes, output_config={"effort": EFFORT},
    )
    print(f"stop_reason: {respuesta.stop_reason}")

    numero = 0
    for bloque in respuesta.content:
        if bloque.type != "text":
            continue
        numero += 1
        print(f"\n[bloque {numero}] {bloque.text!r}")
        for cita in (bloque.citations or []):
            print(f"   └─ cita: págs. {cita.start_page_number} a {cita.end_page_number} (exclusivo)"
                  f" · {cita.cited_text!r}")

    CARPETA_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)
    ruta_json = CARPETA_EXPERIMENTOS / f"citas_{ruta_fds.stem}.json"
    ruta_json.write_text(respuesta.model_dump_json(indent=2), encoding="utf-8")

    uso = respuesta.usage
    costo = (uso.input_tokens * PRECIO_INPUT + uso.output_tokens * PRECIO_OUTPUT) / 1_000_000
    print(f"\nTokens: {uso.input_tokens} in / {uso.output_tokens} out · costo US$ {costo:.6f}")
    print(f"Respuesta completa guardada en: {ruta_json.relative_to(CARPETA_PROYECTO)}")


if __name__ == "__main__":
    main()