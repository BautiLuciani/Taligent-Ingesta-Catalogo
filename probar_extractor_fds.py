"""Pruebas de extractor_fds.py con las citas REALES del paso 4A. Correr: python probar_extractor_fds.py"""
import json
from pathlib import Path

from extractor_fds import leer_seccion_1, leer_seccion_14, lineas, secciones_citadas

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


def contenido_de(nombre):
    """Los bloques de la respuesta guardada en el paso 4A para esa FDS."""
    ruta = CARPETA_EXPERIMENTOS / f"citas_{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8"))["content"]


LAVANDINA = contenido_de("FDS_Clarita_lavandina")
MULTIUSO = contenido_de("FDS_Clarita_multiuso")

print("--- lineas ---")
chequear("Ligadura del PDF (ﬁ -> fi)", lineas("Identiﬁcación"), ["Identificación"])
chequear("\\r\\n, espacio raro y líneas vacías", lineas("  Número ONU:\xa01791 \r\n\r\nSección 15. "),
         ["Número ONU: 1791", "Sección 15."])

print("--- secciones_citadas (citas reales del paso 4A) ---")
secciones, problemas = secciones_citadas(LAVANDINA)
chequear("Lavandina: encuentra la 1 y la 14", sorted(secciones), ["1", "14"])
chequear("...sin problemas", problemas, [])
chequear("...la página la da la API", (secciones["1"]["pagina"], secciones["14"]["pagina"]), (1, 1))
chequear("...la 14 arranca con su título", secciones["14"]["lineas"][0], "Información relativa al transporte")
secciones_m, problemas_m = secciones_citadas(MULTIUSO)
chequear("Multiuso: encuentra la 1 y la 14, sin problemas", (sorted(secciones_m), problemas_m), (["1", "14"], []))

print("--- secciones_citadas (casos armados) ---")


def bloque(cited_text, pagina=1):
    """Un bloque citado de mentira, para probar casos que la API no dio."""
    return {"type": "text", "text": "x", "citations": [{"cited_text": cited_text, "start_page_number": pagina}]}


SECCION_2 = "Identificación de los peligros\r\nH314: Provoca quemaduras graves en la piel.\r\nSección 3. "
secciones, problemas = secciones_citadas([bloque(SECCION_2)])
chequear("La sección 2 NO se confunde con la 1 (línea entera)", secciones, {})
chequear("...y se avisa que faltan la 1 y la 14", len(problemas), 2)
SECCION_14 = "Información relativa al transporte\r\nNúmero ONU: 1791\r\nClase de peligro para el transporte: 8\r\n"
secciones, problemas = secciones_citadas([bloque(SECCION_14, pagina=1), bloque(SECCION_14.replace("8", "3"), pagina=1)])
chequear("La 14 citada con dos textos distintos: ambigua, no se elige", "14" in secciones, False)
chequear("...y queda como problema", any("textos distintos" in p for p in problemas), True)
chequear("Bloque sin cita: se ignora", secciones_citadas([{"type": "text", "text": "Número ONU: 1791", "citations": None}])[0], {})

print("--- leer_seccion_1 ---")
chequear("Lavandina: sus 4 códigos", leer_seccion_1(secciones_citadas(LAVANDINA)[0]["1"]["lineas"]),
         ["LHS-206", "LHS-218", "LHS-263", "LHS-269"])
chequear("Multiuso: sus 4 códigos", leer_seccion_1(secciones_m["1"]["lineas"]), ["LHS-203", "LHS-215", "LHS-236", "LHS-245"])
chequear("Un solo código (insecticida)", leer_seccion_1(["Códigos comerciales: LHS-260"]), ["LHS-260"])
chequear("Sin la línea de códigos: lista vacía", leer_seccion_1(["Identificación", "Producto: Lavandina Clarita"]), [])

print("--- leer_seccion_14 (tabla del estándar, sección 9) ---")
chequear("Lavandina real: clase 8 -> corrosivo + ONU 1791",
         leer_seccion_14(secciones_citadas(LAVANDINA)[0]["14"]["lineas"]), ("corrosivo", "1791", []))
chequear("Multiuso real: No regulado -> no_peligroso, sin ONU",
         leer_seccion_14(secciones_m["14"]["lineas"]), ("no_peligroso", None, []))
chequear("Clase 3 -> liquido_inflamable",
         leer_seccion_14(["Número ONU: 1170", "Clase de peligro para el transporte: 3"]), ("liquido_inflamable", "1170", []))
chequear("Clase 2.1 -> aerosol_inflamable (2.1 no es 2 ni 1)",
         leer_seccion_14(["Número ONU: 1950", "Clase de peligro para el transporte: 2.1"]), ("aerosol_inflamable", "1950", []))
peligro, onu, problemas = leer_seccion_14(["Número ONU: 2810", "Clase de peligro para el transporte: 6.1"])
chequear("Clase fuera de la tabla: peligro None (no se adivina)", (peligro, onu), (None, "2810"))
chequear("...y queda como problema", len(problemas), 1)
chequear("Sin clase ni «No regulado»: None + problema",
         (leer_seccion_14(["Información relativa al transporte"])[0], len(leer_seccion_14(["Información relativa al transporte"])[2])),
         (None, 1))

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")