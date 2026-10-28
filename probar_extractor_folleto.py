"""Pruebas de extractor_folleto.py con las citas REALES del paso 7A. Correr: python probar_extractor_folleto.py"""
import json
from pathlib import Path

from extractor_folleto import bloques_de_una_cita, campos_del_bloque, leer_cierre, productos_del_folleto, renglones_con_pagina

CARPETA_EXPERIMENTOS = Path(__file__).parent / "salida" / "experimentos"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def citas_de(nombre):
    """Todas las citas de una respuesta guardada en el paso 7A, en orden."""
    contenido = json.loads((CARPETA_EXPERIMENTOS / f"citas_dermalab_{nombre}.json").read_text(encoding="utf-8"))["content"]
    return [cita for bloque in contenido for cita in (bloque.get("citations") or [])]


def respuesta_de(nombre):
    """Los bloques de una respuesta guardada en el paso 7A (como los recibe productos_del_folleto)."""
    return json.loads((CARPETA_EXPERIMENTOS / f"citas_dermalab_{nombre}.json").read_text(encoding="utf-8"))["content"]


def bloque_citado(*textos, pagina=1, texto="x"):
    """Un bloque de respuesta armado a mano, con una cita por texto (para los casos que el folleto real no tiene)."""
    return {"type": "text", "text": texto, "citations": [
        {"cited_text": t, "start_page_number": pagina, "end_page_number": pagina + 1} for t in textos]}


BLOQUES = citas_de("bloques")  # la corrida --bloques: una cita por producto, 18 citas


def cita_que_empieza(codigo):
    """La cita de BLOQUES que empieza con el cierre de ese código (y sigue con el producto siguiente)."""
    return next(cita for cita in BLOQUES if cita["cited_text"].startswith("Contenido neto: ") and
                cita["cited_text"].split("\r\n")[0].endswith(codigo))


print("--- leer_cierre ---")
chequear("Cierre normal", leer_cierre("Contenido neto: 50 ml · Código: DL-151"), ("50 ml", "DL-151"))
chequear("Sin espacio después de los dos puntos (tolerado por las dudas)",
         leer_cierre("Contenido neto:50 ml · Código: DL-151"), ("50 ml", "DL-151"))
chequear("El nombre de un producto no es un cierre", leer_cierre("Dermalab Purify"), None)
chequear("El tipo y la descripción no son un cierre", leer_cierre("Gel limpiador. Limpia en profundidad."), None)
chequear("Un renglón que solo menciona un código no es un cierre",
         leer_cierre("Esta presentación es distinta del DL-109"), None)

print("\n--- renglones_con_pagina ---")
cita_103 = cita_que_empieza("DL-103")
chequear("Una cita de la pág. 1: todos sus renglones en la 1", renglones_con_pagina(cita_103["cited_text"], 1), [
    ("Contenido neto: 300 ml · Código: DL-103", 1),
    ("Dermalab Sun SPF 50+", 1),
    ("Protector solar. Amplio espectro UVA/UVB. Resistente al agua.", 1),
    ("Contenido neto: 50 ml · Código: DL-106", 1),
    ("Dermalab Urea 10 %", 1),
    ("Crema.", 1),
])

cita_136 = cita_que_empieza("DL-133")
chequear("La trampa (DL-136): la cita cruza de página; lo que sigue al pie va en la 2",
         renglones_con_pagina(cita_136["cited_text"], cita_136["start_page_number"]), [
    ("Contenido neto: 50 ml · Código: DL-133", 1),
    ("Dermalab Sun Kids SPF 50+", 1),
    ("Protector solar. Amplio espectro UVA/UVB. Resistente al agua. Formulado especialmente para la piel de los niños.", 2),
    ("Contenido neto: 200 ml · Código: DL-136", 2),
    ("Dermalab Sun After Sun", 2),
    ("Gel.", 2),
])

cita_148 = cita_que_empieza("DL-145")
chequear("Un pie solo al final no deja renglón",
         renglones_con_pagina(cita_148["cited_text"], 2)[-1], ("Contenido neto: 200 ml · Código: DL-148", 2))

print("\n--- los 18 cierres de la corrida real ---")
codigos = {}
for cita in BLOQUES:
    for renglon, pagina in renglones_con_pagina(cita["cited_text"], cita["start_page_number"]):
        cierre = leer_cierre(renglon)
        if cierre:
            codigos.setdefault(cierre[1], set()).add(pagina)
chequear("Están los 18 códigos del folleto", len(codigos), 18)
chequear("DL-151 (el primero del folleto) está", "DL-151" in codigos, True)
chequear("DL-136 siempre en la pág. 2 (aunque su cita empiece en la 1)", codigos["DL-136"], {2})
chequear("DL-133 en la pág. 1", codigos["DL-133"], {1})

print("\n--- bloques_de_una_cita ---")
bloques = bloques_de_una_cita(cita_que_empieza("DL-151")["cited_text"], 1)
chequear("Una cita con 2 cierres da 2 bloques", [b["codigo"] for b in bloques], ["DL-151", "DL-103"])
chequear("El 1º no tiene anterior: la cita empieza con su cierre (bloque vacío)", (bloques[0]["anterior"], bloques[0]["renglones"]), (None, []))
chequear("El 2º está PROBADO: lo que hay entre los dos cierres es DL-103", bloques[1], {
    "codigo": "DL-103", "contenido": "300 ml", "pagina_cierre": 1, "anterior": "DL-151",
    "renglones": [("Dermalab Purify", 1), ("Gel limpiador. Limpia en profundidad sin resecar. Para piel mixta a grasa.", 1)]})
chequear("Lo que queda después del último cierre no es un bloque (no tiene código)", len(bloques), 2)

print("\n--- productos_del_folleto: la corrida real --bloques ---")
productos, problemas = productos_del_folleto(respuesta_de("bloques"))
chequear("Los 18 productos, sin problemas", (len(productos), problemas), (18, []))
chequear("En el orden del folleto", list(productos), [
    "DL-151", "DL-103", "DL-106", "DL-109", "DL-112", "DL-115", "DL-118", "DL-121", "DL-124", "DL-127",
    "DL-154", "DL-130", "DL-133", "DL-136", "DL-139", "DL-142", "DL-145", "DL-148"])
chequear("DL-151 (el primero): su nombre es Hydra Plus, no Purify", productos["DL-151"]["renglones"], [
    ("Dermalab Hydra Plus", 1), ("Crema. Textura liviana de rápida absorción. Hidratación facial de uso diario.", 1)])
chequear("DL-103 es Purify (en su misma cita estaba 'Sun SPF 50+', que es DL-106)",
         productos["DL-103"]["renglones"][0], ("Dermalab Purify", 1))
chequear("DL-106 es el protector Sun SPF 50+", productos["DL-106"]["renglones"][0], ("Dermalab Sun SPF 50+", 1))
chequear("DL-136: nombre en la pág. 1, descripción y cierre en la 2",
         (productos["DL-136"]["renglones"], productos["DL-136"]["pagina_cierre"]),
         ([("Dermalab Sun Kids SPF 50+", 1), ("Protector solar. Amplio espectro UVA/UVB. Resistente al agua. "
                                              "Formulado especialmente para la piel de los niños.", 2)], 2))
chequear("DL-148 (el último): Urea 10 %, 200 ml, pág. 2",
         (productos["DL-148"]["renglones"][0], productos["DL-148"]["contenido"]), (("Dermalab Urea 10 %", 2), "200 ml"))

print("\n--- productos_del_folleto: la corrida real SIN --bloques (ninguna cita con 2 cierres) ---")
productos, problemas = productos_del_folleto(respuesta_de("preguntas"))
chequear("No arma ninguno: sería adivinar el orden", len(productos), 0)
chequear("...y los 18 quedan como problema (nada desaparece)", len(problemas), 18)

print("\n--- productos_del_folleto: casos armados ---")
C1, C2, C3 = "Contenido neto: 50 ml · Código: DL-901", "Contenido neto: 30 ml · Código: DL-902", "Contenido neto: 20 ml · Código: DL-903"
productos, problemas = productos_del_folleto([bloque_citado(
    f"Producto A\r\nCrema. Uno.\r\n{C1}\r\nProducto B\r\nGel. Dos.\r\n{C2}",
    f"{C1}\r\nProducto OTRO\r\nGel. Dos.\r\n{C2}")])
chequear("Dos versiones distintas del mismo bloque: no se elige", "DL-902" in productos, False)
chequear("...y queda el problema", problemas, ["DL-902: el texto citado trae dos versiones distintas de su bloque: no se elige una."])

productos, problemas = productos_del_folleto([bloque_citado(
    f"Producto A\r\nCrema. Uno.\r\n{C1}\r\nProducto B\r\nGel. Dos.\r\n{C2}",
    f"{C1}\r\nProducto C\r\nSérum. Tres.\r\n{C3}")])
chequear("Un código con dos productos siguientes distintos: no se elige ninguno", sorted(productos), ["DL-901"])
chequear("...y queda el problema", problemas,
         ["DL-901: el texto citado le da 2 productos siguientes (DL-902 y DL-903): no se elige ninguno."])

productos, problemas = productos_del_folleto([bloque_citado(
    f"Producto A\r\nCrema. Uno.\r\n{C1}", f"Gel. Dos.\r\n{C2}", texto="DL-901 y DL-904")])
chequear("Dos posibles 'primeros': no se elige ninguno", list(productos), [])
chequear("...los dos como problema, y el que Haiku nombró sin cita también", sorted(problemas), [
    "DL-901: ninguna cita muestra qué producto viene antes: no se arma (sería adivinar).",
    "DL-902: ninguna cita muestra qué producto viene antes: no se arma (sería adivinar).",
    "DL-904: Haiku lo nombró pero no aparece en ningún cierre citado."])

print("\n--- campos_del_bloque: los 18 reales ---")
productos, _ = productos_del_folleto(respuesta_de("bloques"))
campos = {codigo: campos_del_bloque(producto) for codigo, producto in productos.items()}
chequear("Los 18 sin problemas", [c for c, (_, _, problemas) in campos.items() if problemas], [])
chequear("DL-109: nombre, tipo, descripción y contenido como están escritos", campos["DL-109"][0], {
    "nombre": "Dermalab Urea 10 %", "tipo": "Crema",
    "descripcion": "Textura liviana de rápida absorción. Hidratación intensa para el cuerpo, ideal para piel muy seca.",
    "contenido": "400 ml"})
chequear("DL-109: todo en la pág. 1", campos["DL-109"][1], {"nombre": 1, "tipo": 1, "descripcion": 1, "contenido": 1})
chequear("DL-136: el nombre en la pág. 1 y lo demás en la 2 (la trampa, resuelta por campo)", campos["DL-136"][1],
         {"nombre": 1, "tipo": 2, "descripcion": 2, "contenido": 2})
chequear("DL-136: es el protector Kids (DER-SOL-INF lo decide el agente con esto)",
         (campos["DL-136"][0]["nombre"], campos["DL-136"][0]["tipo"]), ("Dermalab Sun Kids SPF 50+", "Protector solar"))
chequear("Tipos de dos palabras: DL-103 Gel limpiador y DL-154 Agua micelar",
         (campos["DL-103"][0]["tipo"], campos["DL-154"][0]["tipo"]), ("Gel limpiador", "Agua micelar"))
chequear("Los 6 tipos del folleto", sorted({c[0]["tipo"] for c in campos.values()}),
         ["Agua micelar", "Crema", "Gel", "Gel limpiador", "Protector solar", "Sérum"])

print("\n--- campos_del_bloque: bloques que no tienen la forma (no se adivina) ---")
def armado(*renglones):
    return {"renglones": [(r, 1) for r in renglones], "contenido": "50 ml", "pagina_cierre": 1}
chequear("Tipo solo, sin descripción ('Gel.')", campos_del_bloque(armado("Producto X", "Gel."))[0],
         {"nombre": "Producto X", "tipo": "Gel", "descripcion": "", "contenido": "50 ml"})
chequear("Un solo renglón: problema", campos_del_bloque(armado("Gel limpiador. Limpia."))[2],
         ["el bloque no trae nombre y descripción (la cita pudo empezar a mitad del producto)"])
chequear("El 1er renglón termina en punto (cita cortada): problema",
         campos_del_bloque(armado("Para piel mixta a grasa.", "Otra cosa."))[2],
         ["el primer renglón no parece un nombre ('Para piel mixta a grasa.'): la cita pudo empezar a mitad del producto"])
chequear("Sin punto no hay tipo: problema", campos_del_bloque(armado("Producto X", "Texto sin punto"))[2],
         ["no se encuentra el tipo de producto (lo que va antes del primer punto) en 'Texto sin punto'"])

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")