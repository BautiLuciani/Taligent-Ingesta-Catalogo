"""Paso 1 de la semana 2: experimento con citations sobre el PDF de Limpieza Hogar Sur.

No toca el sistema (servidor, agente ni resultados). Sirve para ver CÓMO cita la API
una tabla de PDF antes de diseñar el extractor.

Correr: python probar_citas.py
"""
import base64
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

CARPETA_PROYECTO = Path(__file__).parent
RUTA_PDF = CARPETA_PROYECTO / "Data" / "proveedores" / "P07_Limpieza_Hogar_Sur" / "LHS_catalogo_nuevos_productos.pdf"
CARPETA_EXPERIMENTOS = CARPETA_PROYECTO / "salida" / "experimentos"

# 3 casos distintos: uno normal, uno SIN EAN y la última fila de la tabla
CODIGOS = ["LHS-206", "LHS-275", "LHS-269"]

EFFORT = "high"       # el mismo que usa el agente, así lo que veamos acá vale para después
MAX_TOKENS = 16_000   # thinking + respuesta; sin streaming el SDK acepta hasta ~21.000

PRECIO_INPUT = 0.10   # USD por millón de tokens de entrada (Haiku 5.5)
PRECIO_OUTPUT = 0.50  # USD por millón de tokens de salida (el thinking se cobra como salida)


def armar_mensajes() -> list[dict]:
    """El PDF en un bloque document con citations prendido, y la pregunta DESPUÉS (M3: documentos primero)."""
    pdf_base64 = base64.standard_b64encode(RUTA_PDF.read_bytes()).decode("utf-8")
    pregunta = (
        f"Para cada uno de estos códigos: {', '.join(CODIGOS)}, decime qué dice el documento "
        "sobre su descripción, contenido, EAN y costo, tal como aparecen escritos. "
        "Si un dato no figura en el documento, decí que no figura. "
        "Respondé solo con lo que está en el documento."
    )
    return [{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
                "title": RUTA_PDF.name,
                "citations": {"enabled": True},
            },
            {"type": "text", "text": pregunta},
        ],
    }]


def mostrar_bloques(respuesta) -> None:
    """Imprime cada bloque de texto con sus citas: página y texto citado textual."""
    numero = 0
    for bloque in respuesta.content:
        if bloque.type != "text":
            continue  # el thinking no se imprime acá: queda guardado en el JSON
        numero += 1
        print(f"\n[bloque {numero}] {bloque.text!r}")  # !r muestra saltos de línea y espacios tal cual
        for cita in (bloque.citations or []):
            print(f"   └─ cita: págs. {cita.start_page_number} a {cita.end_page_number} (exclusivo)"
                  f" · {cita.cited_text!r}")


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    mensajes = armar_mensajes()

    # 1) Contar antes de gastar (M3): gratis y sin correr el modelo
    conteo = cliente.messages.count_tokens(model=modelo, messages=mensajes)
    print(f"count_tokens: {conteo.input_tokens} tokens de entrada (PDF + pregunta)")

    # 2) La llamada de verdad
    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        messages=mensajes,
        output_config={"effort": EFFORT},
    )
    print(f"stop_reason: {respuesta.stop_reason}")
    if respuesta.stop_reason != "end_turn":
        print("⚠ No terminó normalmente: mirá el JSON guardado antes de sacar conclusiones")

    # 3) Lo que vinimos a ver
    mostrar_bloques(respuesta)

    # 4) Guardar la respuesta entera para analizarla sin volver a pagar
    CARPETA_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)
    ruta_json = CARPETA_EXPERIMENTOS / "citas_lhs.json"
    ruta_json.write_text(respuesta.model_dump_json(indent=2), encoding="utf-8")

    uso = respuesta.usage
    costo = (uso.input_tokens * PRECIO_INPUT + uso.output_tokens * PRECIO_OUTPUT) / 1_000_000
    print(f"\nTokens: {uso.input_tokens} in / {uso.output_tokens} out · costo US$ {costo:.6f}")
    print(f"Respuesta completa guardada en: {ruta_json.relative_to(CARPETA_PROYECTO)}")


if __name__ == "__main__":
    main()