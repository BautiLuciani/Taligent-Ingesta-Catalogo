"""Pruebas de extractor_pdf.py con el texto REAL que citó la API en el paso 1. Correr: python probar_extractor.py"""
import copy
import json
from pathlib import Path

from extractor_pdf import (buscar_fila, codigos_en_citas, filas_verificadas, normalizar_espacios, valor_en_fila, verificar_campos)

RUTA_EXPERIMENTO = Path(__file__).parent / "salida" / "experimentos" / "citas_lhs.json"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


# Del JSON del paso 1: los bloques de texto que traen cita (la fila que copió Haiku + lo que citó la API)
respuesta = json.loads(RUTA_EXPERIMENTO.read_text(encoding="utf-8"))
citados = [b for b in respuesta["content"] if b["type"] == "text" and b.get("citations")]
CITA = citados[0]["citations"][0]["cited_text"]  # la tabla entera, como vino de la API
COPIA_206 = citados[0]["text"]                   # lo que escribió Haiku para LHS-206

FILA_206 = "LHS-206 Lavandina Clarita Concentrada 2000 ML 7790840033469 $ 88,04"
FILA_275 = "LHS-275 Alcohol Clarita 96 % 500 CC $ 117,34"
FILA_269 = "LHS-269 Lavandina Clarita Concentrada 1000 ML 7793634603527 $ 54,71"

print("--- normalizar_espacios ---")
chequear("Espacio raro entre $ y número", normalizar_espacios("$\xa088,04"), "$ 88,04")
chequear("Salto \\r\\n y espacios de más", normalizar_espacios("  LHS-206\r\n  Lavandina  "), "LHS-206 Lavandina")

print("--- buscar_fila (con la cita real) ---")
chequear("LHS-206 normal", buscar_fila(CITA, "LHS-206"), FILA_206)
chequear("LHS-275 sin EAN", buscar_fila(CITA, "LHS-275"), FILA_275)
chequear("LHS-203 primera fila", buscar_fila(CITA, "LHS-203"),
         "LHS-203 Limpiador Clarita Multiuso Lavanda 900 ML 7798367700178 $ 143,33")
chequear("LHS-269 última fila", buscar_fila(CITA, "LHS-269"), FILA_269)
chequear("Código cortado LHS-26 no es LHS-263", buscar_fila(CITA, "LHS-26"), None)
chequear("Código que no está", buscar_fila(CITA, "LHS-999"), None)
chequear("Código en dos filas = ambiguo", buscar_fila("LHS-1 uno\r\nLHS-1 otro", "LHS-1"), None)

print("--- valor_en_fila ---")
chequear("EAN de LHS-206 en su fila", valor_en_fila("7790840033469", FILA_206), True)
chequear("EAN de LHS-209 en la fila de 206 (el riesgo del paso 1)", valor_en_fila("7794288526675", FILA_206), False)
chequear("Precio escrito con espacio común", valor_en_fila("$ 88,04", FILA_206), True)
chequear("Contenido completo", valor_en_fila("2000 ML", FILA_206), True)
chequear("200 no es 2000", valor_en_fila("200", FILA_206), False)
chequear("88 no es 88,04", valor_en_fila("88", FILA_206), False)
chequear("88,0 no es 88,04", valor_en_fila("88,0", FILA_206), False)
chequear("Valor vacío", valor_en_fila("", FILA_206), False)
chequear("La copia de Haiku coincide con la fila", valor_en_fila(COPIA_206, FILA_206), True)


def bloque(texto, pagina=1):
    """Un bloque citado de mentira, armado con la cita REAL del paso 1 (para probar casos que la API no dio)."""
    return {"type": "text", "text": texto,
            "citations": [{"cited_text": CITA, "start_page_number": pagina, "end_page_number": pagina + 1}]}


print("--- filas_verificadas (con la respuesta real del paso 1) ---")
filas, problemas = filas_verificadas(copy.deepcopy(respuesta["content"]))
chequear("Salen los 3 códigos pedidos", sorted(filas), ["LHS-206", "LHS-269", "LHS-275"])
chequear("Sin problemas", problemas, [])
chequear("LHS-206 completo, página 1 de la API", filas.get("LHS-206"),
         {"codigo": "LHS-206", "pagina": 1, "fila": FILA_206})
chequear("LHS-275 (sin EAN) verificado igual", filas.get("LHS-275", {}).get("fila"), FILA_275)

print("--- filas_verificadas (casos armados) ---")
EAN_AJENO = "LHS-206 Lavandina Clarita Concentrada 2000 ML 7794288526675 $ 88,04"  # EAN de LHS-209
filas, problemas = filas_verificadas([bloque(EAN_AJENO)])
chequear("Copia con EAN de otra fila: no entra", filas, {})
chequear("...y queda como problema", len(problemas), 1)
filas, problemas = filas_verificadas([bloque("LHS-999 Producto inventado 1 L $ 10,00")])
chequear("Código que no está en la cita: no entra", filas, {})
chequear("...y queda como problema", len(problemas), 1)
filas, problemas = filas_verificadas([bloque(FILA_275), bloque(FILA_275)])
chequear("Repetido idéntico: queda una vez", sorted(filas), ["LHS-275"])
chequear("...sin problemas", problemas, [])
filas, problemas = filas_verificadas([bloque(FILA_275, pagina=1), bloque(FILA_275, pagina=2), bloque(FILA_275)])
chequear("Mismo código en dos páginas: ambiguo, no entra", filas, {})
chequear("...un solo problema, aunque aparezca 3 veces", len(problemas), 1)
filas, problemas = filas_verificadas([{"type": "text", "text": "**LHS-206**", "citations": None}])
chequear("Bloque sin cita: se ignora", (filas, problemas), ({}, []))

print("--- codigos_en_citas (cobertura) ---")
codigos = codigos_en_citas(respuesta["content"])
chequear("La cita real trae los 25 productos de la tabla", len(codigos), 25)
chequear("Incluye la primera y la última fila", {"LHS-203", "LHS-269"} <= codigos, True)
chequear("No toma el encabezado ni el pie", {"Descripción", "Las"} & codigos, set())
filas, _ = filas_verificadas(copy.deepcopy(respuesta["content"]))
chequear("Con el paso 1 (3 pedidos) faltarían 22", len(codigos - set(filas)), 22)
chequear("Bloque sin cita: no aporta códigos", codigos_en_citas([{"type": "text", "text": "LHS-206", "citations": None}]), set())

print("--- verificar_campos ---")
FILA_215 = "LHS-215 Limpiador Clarita Multiuso Lavanda X 500 ML 7792189253836 $ 83,84"
BIEN_206 = {"descripcion": "Lavandina Clarita Concentrada", "contenido": "2000 ML",
            "ean": "7790840033469", "costo": "$ 88,04"}
campos, problemas = verificar_campos("LHS-206", FILA_206, BIEN_206)
chequear("LHS-206 bien separado: quedan los 4", campos, BIEN_206)
chequear("...sin problemas", problemas, [])
campos, problemas = verificar_campos("LHS-275", FILA_275, {"descripcion": "Alcohol Clarita 96 %", "contenido": "500 CC",
                                                           "ean": None, "costo": "$ 117,34"})
chequear("LHS-275 sin EAN: queda None y la fila cierra igual", (campos["ean"], problemas), (None, []))
campos, _ = verificar_campos("LHS-275", FILA_275, {"descripcion": "Alcohol Clarita 96 %", "contenido": "500 CC",
                                                   "ean": "", "costo": "$ 117,34"})
chequear("EAN vacío \"\" se toma como None", campos["ean"], None)
campos, problemas = verificar_campos("LHS-215", FILA_215, {"descripcion": "Limpiador Clarita Multiuso Lavanda",
                                                           "contenido": "X 500 ML", "ean": "7792189253836",
                                                           "costo": "$ 83,84"})
chequear("LHS-215 con la X en el contenido: cierra", problemas, [])
campos, problemas = verificar_campos("LHS-215", FILA_215, {"descripcion": "Limpiador Clarita Multiuso Lavanda",
                                                           "contenido": "500 ML", "ean": "7792189253836",
                                                           "costo": "$ 83,84"})
chequear("LHS-215 con la X perdida: problema (falta algo)", len(problemas), 1)
campos, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "descripcion": "Lavandina Clarita Concentrada 2000 ML"})
chequear("Descripción que se comió el contenido: problema (sobra algo)", len(problemas), 1)
chequear("...pero los campos no se tiran", campos["descripcion"], "Lavandina Clarita Concentrada 2000 ML")
campos, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "costo": "$ 88,40"})
chequear("Costo inventado: queda vacío", campos["costo"], None)
chequear("...y es el único problema (el control 2 no se suma)", len(problemas), 1)
campos, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "ean": "7794288526675"})
chequear("EAN de otra fila: queda vacío", (campos["ean"], len(problemas)), (None, 1))
campos, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "costo": "$\xa088,04"})
chequear("Espacio raro en el valor: se normaliza y pasa", (campos["costo"], problemas), ("$ 88,04", []))

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")