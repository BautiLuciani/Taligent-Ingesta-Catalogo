"""Extractor de folletos en prosa (Dermalab): cada producto con sus datos y la página de cada uno.

Semana 2, paso 7. El folleto no es una tabla: cada producto ocupa unos renglones (nombre; tipo y descripción)
y termina en un renglón de cierre: "Contenido neto: 50 ml · Código: DL-151".

Lo que mostró el experimento (paso 7A, probar_citas_dermalab.py):
  - La API corta en oraciones, y el renglón de cierre no termina en punto: queda pegado al nombre del producto
    SIGUIENTE. Por eso no se puede armar un producto con "el código y lo que está en su misma cita".
  - Pidiendo una cita por producto (de su nombre a su código), cada cita trae dos cierres seguidos:
    lo que queda ENTRE el cierre de X y el cierre de Y es el producto Y. Lo prueba el texto citado (17 de 17).
  - DL-136 tiene el nombre al pie de la página 1 y el resto en la 2: la cita cruza de página y en el medio
    trae el pie "Dermalab S.A. Página 1 de 2". Lo que sigue a ese pie está en la página 2.

Como en las FDS, el CÓDIGO lee los datos del texto citado (el documento real), no de la copia de Haiku.
Una sola llamada (con citations); no hace falta la llamada 2: los campos los separa el código.

Correr: python extractor_folleto.py            (el folleto de Dermalab; reusa la llamada ya guardada)
        python extractor_folleto.py --de-nuevo (vuelve a hacer la llamada)
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from extractor_fds import lineas
from extractor_pdf import (CARPETA_EXTRACCIONES, CARPETA_PROYECTO, EFFORT, MAX_TOKENS, PATRON_CODIGO_EN_TEXTO,
                           costo_usd, llamada_guardada, sin_espacios)

RUTA_DERMALAB = CARPETA_PROYECTO / "Data" / "proveedores" / "P05_Dermalab" / "Dermalab_lanzamientos_2026.pdf"

# El renglón que cierra cada producto: "Contenido neto: 50 ml · Código: DL-151".
# \s* después de los dos puntos: tolera "Contenido neto:50 ml" (sin espacio), por si algún folleto lo escribe así.
PATRON_CIERRE = re.compile(r"^Contenido neto:\s*(?P<contenido>.+?)\s*·\s*Código:\s*(?P<codigo>[A-Z]{2,3}-?\d{3,5})$")

# El pie de página: "Dermalab S.A. Página 1 de 2". A veces la API pega el renglón siguiente sin salto
# ("...Página 1 de 2Protector solar."): lo que sigue al pie es texto de la página siguiente.
PATRON_PIE = re.compile(r"^.*?Página\s*(?P<pagina>\d+)\s*de\s*\d+(?P<resto>.*)$")


def renglones_con_pagina(cited_text: str, pagina: int) -> list[tuple[str, int]]:
    """Parte un texto citado en renglones, cada uno con SU página. Los pies de página no son renglones.

    pagina: la página donde empieza la cita (start_page_number de la API).
    Ejemplo: "Dermalab Sun Kids SPF 50+\\r\\nDermalab S.A. Página 1 de 2Protector solar. ..." empezando en la 1
      -> [("Dermalab Sun Kids SPF 50+", 1), ("Protector solar. ...", 2)]
    """
    renglones = []
    for renglon in lineas(cited_text):
        pie = PATRON_PIE.match(renglon)
        if pie:
            pagina = int(pie["pagina"]) + 1  # lo que venga después del pie "Página N de M" está en la N+1
            renglon = pie["resto"].strip()
            if not renglon:
                continue
        renglones.append((renglon, pagina))
    return renglones


def leer_cierre(renglon: str) -> tuple[str, str] | None:
    """Si el renglón es el cierre de un producto, devuelve (contenido como está escrito, código). Si no, None.

    "Contenido neto: 50 ml · Código: DL-151" -> ("50 ml", "DL-151")
    "Dermalab Purify"                        -> None
    """
    cierre = PATRON_CIERRE.match(renglon)
    return (cierre["contenido"], cierre["codigo"]) if cierre else None


def bloques_de_una_cita(cited_text: str, pagina: int) -> list[dict]:
    """Los bloques de producto que trae UNA cita: lo que hay antes de cada renglón de cierre.

    Cada bloque: {"codigo", "contenido", "pagina_cierre", "renglones": [(texto, página)], "anterior"}.
    - "anterior" es el código del cierre que lo precede EN LA MISMA CITA: entonces el bloque está probado
      (empieza justo después de otro producto).
    - Si antes no hubo otro cierre, "anterior" es None: el bloque es lo que la cita trae antes de su cierre,
      y puede estar cortado (la cita pudo empezar a mitad del producto).
    Lo que queda después del último cierre (el principio del producto siguiente) no es un bloque: no tiene código.
    """
    bloques, anterior, pendientes = [], None, []
    for renglon, pagina_renglon in renglones_con_pagina(cited_text, pagina):
        cierre = leer_cierre(renglon)
        if cierre is None:
            pendientes.append((renglon, pagina_renglon))
            continue
        contenido, codigo = cierre
        bloques.append({"codigo": codigo, "contenido": contenido, "pagina_cierre": pagina_renglon,
                        "renglones": pendientes, "anterior": anterior})
        anterior, pendientes = codigo, []
    return bloques


def productos_del_folleto(contenido: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Arma cada producto del folleto con lo que hay ENTRE dos cierres seguidos, y controla todo lo demás.

    contenido: los bloques de la respuesta, como diccionarios (model_dump()["content"]).
    Reglas (como en filas_desde_citas, adaptadas a la prosa):
    - Vale el bloque PROBADO (con "anterior"): el texto citado muestra qué producto viene antes.
      Si un código tiene dos versiones probadas distintas (más allá de espacios), no se elige.
    - Un bloque sin "anterior" solo vale para el PRIMER producto del folleto: el único código que no viene
      después de ningún otro. Para cualquier otro sería adivinar el orden: es un problema.
    - Un código no puede tener dos productos siguientes distintos.
    - Cobertura: un código con cierre citado, o que Haiku nombró, y que no quedó armado es un problema.
    Devuelve (productos, problemas). productos va en el orden del folleto (del primero al último).
    """
    versiones = {}  # codigo -> todos sus bloques, de todas las citas
    for bloque in contenido:
        if bloque.get("type") != "text" or not bloque.get("citations"):
            continue
        for cita in bloque["citations"]:
            for producto in bloques_de_una_cita(cita["cited_text"], cita["start_page_number"]):
                versiones.setdefault(producto["codigo"], []).append(producto)

    def clave(producto):  # para comparar versiones sin que importen los espacios
        return [(sin_espacios(texto), pagina) for texto, pagina in producto["renglones"]]

    productos, problemas, siguiente = {}, [], {}
    for codigo, opciones in versiones.items():
        probadas = [v for v in opciones if v["anterior"] is not None]
        if not probadas:
            continue  # se decide abajo: puede ser el primero del folleto
        if len({repr(clave(v)) for v in probadas}) > 1 or len({v["anterior"] for v in probadas}) > 1:
            problemas.append(f"{codigo}: el texto citado trae dos versiones distintas de su bloque: no se elige una.")
            continue
        productos[codigo] = probadas[0]

    # Un código no puede tener dos productos siguientes: si pasa, no se elige ninguno de los dos
    despues_de = {}
    for codigo, producto in productos.items():
        despues_de.setdefault(producto["anterior"], []).append(codigo)
    for anterior, codigos in despues_de.items():
        if len(codigos) > 1:
            problemas.append(f"{anterior}: el texto citado le da {len(codigos)} productos siguientes "
                             f"({' y '.join(codigos)}): no se elige ninguno.")
            for codigo in codigos:
                del productos[codigo]
        else:
            siguiente[anterior] = codigos[0]

    # El primero del folleto: el único código que no viene después de ningún otro
    sin_probar = [codigo for codigo, opciones in versiones.items() if all(v["anterior"] is None for v in opciones)]
    if len(sin_probar) == 1:
        codigo = sin_probar[0]
        productos[codigo] = max(versiones[codigo], key=lambda v: len(clave(v)))  # la versión con más renglones
    else:
        for codigo in sin_probar:
            problemas.append(f"{codigo}: ninguna cita muestra qué producto viene antes: no se arma (sería adivinar).")

    # Cobertura: lo que Haiku nombró tiene que estar en algún cierre citado
    nombrados = {c for b in contenido if b.get("type") == "text" for c in PATRON_CODIGO_EN_TEXTO.findall(b["text"])}
    for codigo in sorted(nombrados - set(versiones)):
        problemas.append(f"{codigo}: Haiku lo nombró pero no aparece en ningún cierre citado.")

    # En el orden del folleto: desde el primero, siguiendo "qué viene después"
    ordenados, codigo = {}, next((c for c in productos if productos[c]["anterior"] is None), None)
    while codigo in productos and codigo not in ordenados:
        ordenados[codigo] = productos[codigo]
        codigo = siguiente.get(codigo)
    for codigo in productos:  # los que no se pudieron encadenar desde el primero, al final
        ordenados.setdefault(codigo, productos[codigo])
    return ordenados, problemas


def campos_del_bloque(producto: dict) -> tuple[dict, dict, list[str]]:
    """Separa los campos de un producto armado, cada uno con SU página.

    El bloque de un producto es: nombre (1er renglón) + "Tipo. Descripción..." (lo que sigue) + su cierre.
      ("Dermalab Urea 10 %", "Crema. Textura liviana... muy seca.", cierre "400 ml")
      -> nombre "Dermalab Urea 10 %", tipo "Crema", descripcion "Textura liviana... muy seca.", contenido "400 ml"
    Los valores quedan COMO ESTÁN ESCRITOS (las cuentas las hace el servidor, con cuentas.py).
    Devuelve (campos, paginas, problemas). Si el bloque no tiene esa forma, no se adivina: va como problema.
    """
    renglones = producto["renglones"]
    if len(renglones) < 2:
        return {}, {}, ["el bloque no trae nombre y descripción (la cita pudo empezar a mitad del producto)"]
    (nombre, pagina_nombre), (primero, pagina_texto) = renglones[0], renglones[1]
    if nombre.endswith("."):
        return {}, {}, [f"el primer renglón no parece un nombre ({nombre!r}): la cita pudo empezar a mitad del producto"]
    texto = " ".join(renglon for renglon, _ in renglones[1:])
    tipo, punto, descripcion = texto.partition(". ")
    if not punto:  # "Gel." solo, o un texto sin punto
        tipo, descripcion = (texto[:-1], "") if texto.endswith(".") else (None, texto)
    if not tipo:
        return {}, {}, [f"no se encuentra el tipo de producto (lo que va antes del primer punto) en {texto!r}"]
    campos = {"nombre": nombre, "tipo": tipo, "descripcion": descripcion, "contenido": producto["contenido"]}
    paginas = {"nombre": pagina_nombre, "tipo": pagina_texto, "descripcion": pagina_texto,
               "contenido": producto["pagina_cierre"]}
    return campos, paginas, []


# La pregunta que funcionó en el paso 7A (--bloques): una cita por producto, desde su nombre hasta su código.
# La respuesta de Haiku no se usa; solo sus citas (el texto del documento, con su página).
INSTRUCCION_BLOQUES = (
    "Para cada producto del documento, escribí UNA sola oración con todo lo que el documento dice sobre él "
    "(nombre, tipo, descripción, contenido neto y código), respaldada por UNA sola cita que abarque todo su "
    "bloque: desde el renglón de su nombre hasta el renglón de su código, inclusive. Un párrafo por producto, "
    "empezando por su código, en el orden en que aparecen en el documento."
)


def pedir_bloques_citados(cliente, modelo: str, ruta_pdf: Path) -> dict:
    """La única llamada: el folleto con citations prendido y la pregunta DESPUÉS (M3: documentos primero)."""
    pdf_base64 = base64.standard_b64encode(ruta_pdf.read_bytes()).decode("utf-8")
    respuesta = cliente.messages.create(
        model=modelo, max_tokens=MAX_TOKENS, output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
             "title": ruta_pdf.name, "citations": {"enabled": True}},
            {"type": "text", "text": INSTRUCCION_BLOQUES},
        ]}],
    )
    return respuesta.model_dump()


def main():
    """Extrae los productos de un folleto en prosa (por defecto, el de Dermalab) y guarda el resultado verificado."""
    argumentos = argparse.ArgumentParser(description="Extrae los productos de un folleto en prosa.")
    argumentos.add_argument("pdf", nargs="?", type=Path, default=RUTA_DERMALAB,
                            help="Folleto a extraer (por defecto, el de Dermalab).")
    argumentos.add_argument("--de-nuevo", action="store_true", help="Vuelve a hacer la llamada.")
    argumentos = argumentos.parse_args()

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()
    ruta_pdf = argumentos.pdf
    CARPETA_EXTRACCIONES.mkdir(parents=True, exist_ok=True)

    respuesta = llamada_guardada(CARPETA_EXTRACCIONES / f"{ruta_pdf.stem}.llamada.json",
                                 lambda: pedir_bloques_citados(cliente, modelo, ruta_pdf), argumentos.de_nuevo)
    armados, problemas = productos_del_folleto(respuesta["content"])

    productos = []
    for codigo, producto in armados.items():
        campos, paginas, problemas_campos = campos_del_bloque(producto)
        productos.append({
            "codigo": codigo,
            "fuente": {"archivo": ruta_pdf.name, "pagina": producto["pagina_cierre"]},  # donde está su código
            "bloque": [renglon for renglon, _ in producto["renglones"]],  # el texto citado, tal cual
            "campos": campos,
            "paginas": paginas,  # la página de CADA campo (DL-136: el nombre en la 1, lo demás en la 2)
            "problemas": problemas_campos,
        })

    resultado = {"archivo": ruta_pdf.name, "modelo": modelo, "productos": productos, "problemas": problemas,
                 "costo_usd": round(costo_usd(respuesta), 6)}
    ruta_resultado = CARPETA_EXTRACCIONES / f"{ruta_pdf.stem}.json"
    ruta_resultado.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    marcados = [p for p in productos if p["problemas"]]
    print(f"\n{len(productos)} productos · {len(productos) - len(marcados)} sin problemas · {len(marcados)} marcados")
    for p in productos:
        c, pag = p["campos"], p["paginas"]
        if p["problemas"]:
            print(f"  {p['codigo']:<7} ⚠ {'; '.join(p['problemas'])}")
            continue
        distintas = " (nombre en pág. %d)" % pag["nombre"] if pag["nombre"] != p["fuente"]["pagina"] else ""
        print(f"  {p['codigo']:<7} pág. {p['fuente']['pagina']}{distintas} · {c['nombre']} | {c['tipo']} | {c['contenido']}")
    print(f"\nProblemas generales: {problemas or 'ninguno'}")
    print(f"Costo: US$ {resultado['costo_usd']:.6f} (una sola llamada)")
    print(f"Resultado: {ruta_resultado.relative_to(CARPETA_PROYECTO)}")


if __name__ == "__main__":
    main()