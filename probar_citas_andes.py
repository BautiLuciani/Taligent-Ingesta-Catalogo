"""Paso 6A de la semana 2: experimento con citations sobre el PDF de Laboratorio Andes.

No toca el sistema. Prueba la llamada 1 REAL del extractor (pedir_filas_citadas) sobre una tabla con
celdas de 2 renglones, para ver qué cita la API y qué pasa con buscar_fila. Además pregunta por la
línea de vigencia (desde cuándo rige la lista), para ver si se puede leer con su cita.

Nota (paso 6B3): la llamada 1 del extractor ahora pregunta por cada producto y las filas las arma el código
(filas_desde_citas). Lo que devolvía la llamada 1 VIEJA (copiar la fila: 0 citas) quedó guardado en
salida/experimentos/citas_andes_filas.json.

Correr: python probar_citas_andes.py              (1 y 2: la llamada 1 del extractor y la vigencia)
        python probar_citas_andes.py --renglones  (3: copiar renglón por renglón, sin unir nada)
        python probar_citas_andes.py --preguntar  (4: preguntar por cada producto, como en el paso 1)
"""
import base64
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from extractor_pdf import EFFORT, MAX_TOKENS, costo_usd, filas_desde_citas, pedir_filas_citadas

CARPETA_PROYECTO = Path(__file__).parent
RUTA_ANDES = CARPETA_PROYECTO / "Data" / "proveedores" / "P01_Laboratorio_Andes" / "Lista_de_precios_octubre_2026.pdf"
CARPETA_EXPERIMENTOS = CARPETA_PROYECTO / "salida" / "experimentos"

PREGUNTA_RENGLONES = (
    "Copiá la tabla del documento renglón por renglón, tal como aparece escrita: cada renglón en su propio "
    "párrafo, con las mismas palabras, números y símbolos. No unas renglones: si una celda ocupa dos renglones, "
    "copiá los dos renglones por separado, como están. No agregues títulos, explicaciones ni resúmenes."
)

PREGUNTA_PRODUCTOS = (
    "Para cada producto de la tabla del documento, decime qué dice el documento sobre él "
    "(producto, monodroga, presentación, condición, EAN y precio), citando el documento. "
    "Un párrafo por producto, empezando por su código. Si un dato no figura, decí que no figura."
)

PREGUNTA_VIGENCIA = ("Copiá textual la línea del documento que dice desde cuándo rige esta lista. "
                     "Solo esa línea, sin agregar nada.")


def pedir_con_citas(cliente, modelo: str, pregunta: str) -> dict:
    """El PDF de Andes con citations prendido y la pregunta DESPUÉS (M3: documentos primero)."""
    pdf_base64 = base64.standard_b64encode(RUTA_ANDES.read_bytes()).decode("utf-8")
    respuesta = cliente.messages.create(
        model=modelo, max_tokens=MAX_TOKENS, output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
             "title": RUTA_ANDES.name, "citations": {"enabled": True}},
            {"type": "text", "text": pregunta},
        ]}],
    )
    return respuesta.model_dump()


def mostrar_citas(contenido: list[dict]) -> None:
    """Cada texto citado DISTINTO una sola vez (si la cita es la tabla entera, no la imprime 26 veces)."""
    vistos = []
    for bloque in contenido:
        for cita in (bloque.get("citations") or []):
            if cita["cited_text"] not in vistos:
                vistos.append(cita["cited_text"])
                print(f"\n[cita {len(vistos)}] pág. {cita['start_page_number']} · {cita['cited_text']!r}")


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    CARPETA_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)

    if "--preguntar" in sys.argv:
        print("=== 4) Preguntar por cada producto (como en el paso 1) ===")
        respuesta = pedir_con_citas(cliente, modelo, PREGUNTA_PRODUCTOS)
        (CARPETA_EXPERIMENTOS / "citas_andes_preguntas.json").write_text(
            json.dumps(respuesta, ensure_ascii=False, indent=2), encoding="utf-8")
        bloques = [b for b in respuesta["content"] if b.get("type") == "text" and b["text"].strip()]
        con_cita = [b for b in bloques if b.get("citations")]
        print(f"stop_reason: {respuesta['stop_reason']} · bloques con texto: {len(bloques)} · con cita: {len(con_cita)}")
        print("\nLos primeros 10 bloques con cita (texto · citas):")
        for bloque in con_cita[:10]:
            print(f"   {bloque['text']!r} · {len(bloque['citations'])} cita(s)")
        mostrar_citas(respuesta["content"])
        print(f"\nCosto: US$ {costo_usd(respuesta):.6f} · guardado en salida/experimentos/citas_andes_preguntas.json")
        return

    if "--renglones" in sys.argv:
        print("=== 3) Renglón por renglón, sin unir nada ===")
        respuesta = pedir_con_citas(cliente, modelo, PREGUNTA_RENGLONES)
        (CARPETA_EXPERIMENTOS / "citas_andes_renglones.json").write_text(
            json.dumps(respuesta, ensure_ascii=False, indent=2), encoding="utf-8")
        bloques = [b for b in respuesta["content"] if b.get("type") == "text" and b["text"].strip()]
        con_cita = [b for b in bloques if b.get("citations")]
        print(f"stop_reason: {respuesta['stop_reason']} · bloques con texto: {len(bloques)} · con cita: {len(con_cita)}")
        print("\nLos primeros 12 bloques (texto · cantidad de citas):")
        for bloque in bloques[:12]:
            print(f"   {bloque['text']!r} · {len(bloque.get('citations') or [])} cita(s)")
        mostrar_citas(respuesta["content"])
        print(f"\nCosto: US$ {costo_usd(respuesta):.6f} · guardado en salida/experimentos/citas_andes_renglones.json")
        return

    print("=== 1) La llamada 1 del extractor, tal cual, sobre Andes ===")
    filas_resp = pedir_filas_citadas(cliente, modelo, RUTA_ANDES)
    (CARPETA_EXPERIMENTOS / "citas_andes_filas.json").write_text(
        json.dumps(filas_resp, ensure_ascii=False, indent=2), encoding="utf-8")
    copias = [b["text"] for b in filas_resp["content"] if b.get("type") == "text" and b.get("citations")]
    print(f"stop_reason: {filas_resp['stop_reason']} · bloques con cita: {len(copias)}")
    print("\nLo que copió Haiku (los primeros 6):")
    for copia in copias[:6]:
        print(f"   {copia!r}")
    mostrar_citas(filas_resp["content"])

    filas, problemas = filas_desde_citas(filas_resp["content"])
    print(f"\nfilas_desde_citas: {len(filas)} · problemas: {len(problemas)}")
    for problema in problemas:
        print(f"   ⚠ {problema}")

    print("\n=== 2) La línea de vigencia ===")
    vigencia_resp = pedir_con_citas(cliente, modelo, PREGUNTA_VIGENCIA)
    (CARPETA_EXPERIMENTOS / "citas_andes_vigencia.json").write_text(
        json.dumps(vigencia_resp, ensure_ascii=False, indent=2), encoding="utf-8")
    for bloque in vigencia_resp["content"]:
        if bloque.get("type") == "text":
            print(f"   {bloque['text']!r}")
    mostrar_citas(vigencia_resp["content"])

    costo = costo_usd(filas_resp) + costo_usd(vigencia_resp)
    print(f"\nCosto de las 2 llamadas: US$ {costo:.6f}")
    print("Guardado en salida/experimentos/citas_andes_filas.json y citas_andes_vigencia.json")


if __name__ == "__main__":
    main()