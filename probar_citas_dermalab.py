"""Paso 7A de la semana 2: experimento con citations sobre el folleto en prosa de Dermalab.

No toca el sistema. El folleto NO es una tabla: cada producto ocupa 3 renglones (nombre; tipo y descripción;
"Contenido neto: N ml · Código: DL-xxx"). Antes de diseñar el lector queremos ver:
  1. Cómo corta la API este PDF en pedazos (chunks): ¿un producto entero por cita, un renglón, una oración?
  2. Qué página cita para DL-136, que tiene el nombre al pie de la página 1 y el resto en la página 2.

Usa la forma de preguntar que funcionó en Andes (paso 6A): por cada producto, citando.

Hallazgo de la corrida 1: la API corta en oraciones y el renglón del código no termina en punto, así que
cada cita trae el FINAL de un producto (su código) y el PRINCIPIO del siguiente (su nombre y su tipo).
Ninguna cita tenía dos códigos, así que el texto solo no dice qué producto viene después de cuál.
La opción --bloques prueba pedir UNA cita por producto, desde su nombre hasta su código: si una cita trae
dos códigos seguidos (X ... Y), lo que hay entre ellos es el producto Y, y eso lo prueba el texto citado.

Correr: python probar_citas_dermalab.py            (1: preguntar por cada producto)
        python probar_citas_dermalab.py --bloques  (2: una cita por producto, de su nombre a su código)
"""
import base64
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from extractor_pdf import EFFORT, MAX_TOKENS, costo_usd

CARPETA_PROYECTO = Path(__file__).parent
RUTA_DERMALAB = CARPETA_PROYECTO / "Data" / "proveedores" / "P05_Dermalab" / "Dermalab_lanzamientos_2026.pdf"
CARPETA_EXPERIMENTOS = CARPETA_PROYECTO / "salida" / "experimentos"

PREGUNTA_PRODUCTOS = (
    "Para cada producto del documento, decime qué dice el documento sobre él (nombre, tipo de producto, "
    "descripción, contenido neto y código), citando el documento. Un párrafo por producto, empezando por su "
    "código. Si un dato no figura, decí que no figura."
)

PREGUNTA_BLOQUES = (
    "Para cada producto del documento, escribí UNA sola oración con todo lo que el documento dice sobre él "
    "(nombre, tipo, descripción, contenido neto y código), respaldada por UNA sola cita que abarque todo su "
    "bloque: desde el renglón de su nombre hasta el renglón de su código, inclusive. Un párrafo por producto, "
    "empezando por su código, en el orden en que aparecen en el documento."
)


def pedir_con_citas(cliente, modelo: str, pregunta: str) -> dict:
    """El folleto con citations prendido y la pregunta DESPUÉS (M3: documentos primero)."""
    pdf_base64 = base64.standard_b64encode(RUTA_DERMALAB.read_bytes()).decode("utf-8")
    respuesta = cliente.messages.create(
        model=modelo, max_tokens=MAX_TOKENS, output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
             "title": RUTA_DERMALAB.name, "citations": {"enabled": True}},
            {"type": "text", "text": pregunta},
        ]}],
    )
    return respuesta.model_dump()


def citas_distintas(contenido: list[dict]) -> list[dict]:
    """Cada texto citado DISTINTO una sola vez, en el orden en que aparece."""
    vistas, citas = set(), []
    for bloque in contenido:
        for cita in (bloque.get("citations") or []):
            clave = (cita["cited_text"], cita["start_page_number"])
            if clave not in vistas:
                vistas.add(clave)
                citas.append(cita)
    return citas


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    CARPETA_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)

    if "--bloques" in sys.argv:
        print("=== 1) Una cita por producto, de su nombre a su código ===")
        respuesta = pedir_con_citas(cliente, modelo, PREGUNTA_BLOQUES)
        ruta_salida = CARPETA_EXPERIMENTOS / "citas_dermalab_bloques.json"
    else:
        print("=== 1) Preguntar por cada producto del folleto ===")
        respuesta = pedir_con_citas(cliente, modelo, PREGUNTA_PRODUCTOS)
        ruta_salida = CARPETA_EXPERIMENTOS / "citas_dermalab_preguntas.json"
    ruta_salida.write_text(json.dumps(respuesta, ensure_ascii=False, indent=2), encoding="utf-8")

    bloques = [b for b in respuesta["content"] if b.get("type") == "text" and b["text"].strip()]
    con_cita = [b for b in bloques if b.get("citations")]
    citas = citas_distintas(respuesta["content"])
    print(f"stop_reason: {respuesta['stop_reason']} · bloques con texto: {len(bloques)} · con cita: {len(con_cita)}")
    print(f"Textos citados distintos: {len(citas)}")

    print("\n=== 2) Cómo corta la API el folleto (cada texto citado, con su página) ===")
    for numero, cita in enumerate(citas, 1):
        pagina = cita["start_page_number"]
        hasta = cita["end_page_number"] - 1  # end_page_number es exclusivo
        paginas = f"pág. {pagina}" if hasta == pagina else f"págs. {pagina}-{hasta}"
        print(f"\n[cita {numero}] {paginas} · {cita['cited_text']!r}")

    print("\n=== 3) ¿En qué cita aparece cada código? ===")
    codigos = {}
    for cita in citas:
        for codigo in re.findall(r"DL-\d{3}", cita["cited_text"]):
            codigos.setdefault(codigo, []).append(cita["start_page_number"])
    for codigo in sorted(codigos):
        print(f"   {codigo}: pág. {codigos[codigo]}")
    print(f"   Códigos encontrados en las citas: {len(codigos)} (el folleto tiene 18)")

    print("\n=== 4) La trampa: todo lo que se citó sobre Sun Kids / DL-136 ===")
    for cita in citas:
        if "Kids" in cita["cited_text"] or "DL-136" in cita["cited_text"] or "niños" in cita["cited_text"]:
            print(f"   pág. {cita['start_page_number']} · {cita['cited_text']!r}")

    print("\n=== 5) ¿Qué producto viene después de cuál? (citas con 2 códigos o más) ===")
    siguiente = {}
    for cita in citas:
        en_orden = re.findall(r"DL-\d{3}", cita["cited_text"])
        for anterior, posterior in zip(en_orden, en_orden[1:]):
            siguiente[anterior] = posterior
    for anterior, posterior in siguiente.items():
        print(f"   {anterior} -> {posterior}")
    print(f"   Pares probados por el texto citado: {len(siguiente)} de 17")

    print(f"\nCosto: US$ {costo_usd(respuesta):.6f} · guardado en salida/experimentos/{ruta_salida.name}")


if __name__ == "__main__":
    main()