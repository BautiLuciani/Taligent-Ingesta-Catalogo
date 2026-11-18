"""Pruebas sin IA del evaluador del asistente (semana 6, paso 4). Correr: python probar_evaluar_consultas.py

Las respuestas de ejemplo son las REALES de la primera prueba (18/11): Q01 y la conversación V01.
"""
import json

from evaluar_consultas import (RUTA_ESPERADAS, calificar, casos, informe, numeros_del_texto, valor_coincide)

ESPERADAS = json.loads(RUTA_ESPERADAS.read_text(encoding="utf-8"))
POR_ID = {c["id"]: c for c in ESPERADAS["consultas"]}
V01 = next(v for v in ESPERADAS["conversaciones"] if v["id"] == "V01")["turnos"]

errores = 0


def chequear(origen, obtenido, esperado):
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def respuesta(texto, valor=None, items=(), fuentes=(), esta=True):
    return {"texto": texto, "valor": valor, "items": list(items), "fuentes": list(fuentes), "esta_en_lo_generado": esta}


EXCEL_12 = {"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12}
PDF_1 = {"archivo": "Lista_de_precios_octubre_2026.pdf", "pagina": 1}
NORTE_5 = {"archivo": "NorteImports_new_items_Q4.xlsx", "hoja": "New items", "fila": 5}

print("== lo que tiene que haber")
chequear("las 23 sueltas y las 2 conversaciones (29 turnos)", sum(len(t) for _, t in casos(ESPERADAS, None)), 29)
chequear("--solo filtra", [i for i, _ in casos(ESPERADAS, {"Q01", "V02"})], ["Q01", "V02"])

print("== números")
chequear("lee coma decimal", 320.8 in numeros_del_texto("es 320,80 UYU"), True)
chequear("lee punto decimal", 10.66 in numeros_del_texto("a 10.66 USD"), True)
chequear("el valor puede venir solo en el texto", valor_coincide(320.8, respuesta("Cuesta 320,80 UYU", None)), True)
chequear("un número que no es", valor_coincide(320.8, respuesta("Cuesta 306,73", 306.73)), False)

print("== textos y sinónimos")
chequear("SKU en el valor", valor_coincide("SKU100889", respuesta("...", "SKU100889")), True)
chequear("motivo dicho con palabras", valor_coincide("gtin_invalido", respuesta("El dígito verificador no coincide", None)), True)
chequear("estado con guion bajo o con espacios", valor_coincide("a_revision", respuesta("Sigue a revisión", "a revisión")), True)

print("== respuestas reales del 18/11")
q01 = respuesta("El precio de costo de AN-1124 (DERMACORT 1 % CREMA X 30 G) es 320,80 UYU. Sale de la hoja Actualización "
                "del Excel ...", 320.8, ["P01:AN-1124"], [EXCEL_12, PDF_1])
chequear("Q01 real: bien (citar de más no resta)", calificar(POR_ID["Q01"], q01)["ok"], True)
v01_1 = respuesta("Son 14 productos de Importadora Norte con precio en dólares (USD)...", 14,
                  [f"P08:IN70{n:02d}" for n in range(3, 43, 3)])
chequear("V01.1 real: los 14", calificar(V01[0], v01_1)["ok"], True)
v01_2 = respuesta("El más caro es P08:IN7012, VITALIS VITAMINA D3 2000 UI CAPSULAS X 120 UN, a 10,66 USD sin IVA.",
                  10.66, ["P08:IN7012"], [NORTE_5])
chequear("V01.2 real", calificar(V01[1], v01_2)["ok"], True)
v01_3 = respuesta("El precio de 10,66 USD sale de NorteImports_new_items_Q4.xlsx, hoja New items, fila 5.",
                  10.66, ["P08:IN7012"], [NORTE_5])
chequear("V01.3 real", calificar(V01[2], v01_3)["ok"], True)

print("== lo que tiene que fallar")
chequear("sin la fuente esperada -> falla 'fuentes'",
         calificar(POR_ID["Q01"], respuesta("320,80", 320.8, ["P01:AN-1124"], [PDF_1]))["chequeos"]["fuentes"], False)
chequear("un producto de más -> falla 'productos'",
         calificar(POR_ID["Q01"], respuesta("320,80", 320.8, ["P01:AN-1124", "P01:AN-1127"], [EXCEL_12]))["chequeos"]["productos"], False)
q03_sin = calificar(POR_ID["Q03"], respuesta("Tiene 142 ml.", 142, ["P08:IN7003"],
                                             [{"archivo": "NorteImports_new_items_Q4.xlsx", "hoja": "New items", "fila": 2}]))
chequear("Q03 sin decir qué decía el archivo -> falla el 'menciona'", q03_sin["ok"], False)
q03_coma = calificar(POR_ID["Q03"], respuesta("Tiene 142 ml; el archivo decía 4,8 fl oz.", 142, ["P08:IN7003"],
                                              [{"archivo": "NorteImports_new_items_Q4.xlsx", "hoja": "New items", "fila": 2}]))
chequear("Q03 con '4,8 fl oz' (coma) también vale", q03_coma["ok"], True)

print("== lo que no está (Q22, Q23)")
chequear("Q22 dice que no está -> bien",
         calificar(POR_ID["Q22"], respuesta("El sistema no tiene datos de ventas.", None, esta=False))["ok"], True)
chequear("Q22 inventa un número -> mal",
         calificar(POR_ID["Q22"], respuesta("Se vendieron 120.", 120, esta=True))["ok"], False)
chequear("Q23 dice que no está y nombra el costo como dato relacionado -> bien",
         calificar(POR_ID["Q23"], respuesta("No hay precio al público; el de costo es 736,22.", None, ["P05:DL-109"],
                                            [{"archivo": "Dermalab_lista_precios.xlsx", "hoja": "Lista", "fila": 2}], esta=False))["ok"], True)

print("== diagnóstico de redacción")
from evaluar_consultas import problemas_de_redaccion  # noqa: E402
chequear("'(SKU IN7012)' es un código del proveedor llamado SKU", problemas_de_redaccion("es VITALIS (SKU IN7012)"),
         ["código del proveedor llamado SKU"])
chequear("'SKU100889' está bien", problemas_de_redaccion("coincide con SKU100889"), [])
chequear("'quedó lista_para_alta' es un nombre interno", problemas_de_redaccion("quedó lista_para_alta"), ["nombre interno"])
chequear("'quedó lista para alta' está bien", problemas_de_redaccion("quedó lista para alta"), [])

print("== el informe")
datos = informe(ESPERADAS, {"Q01": {**q01, "costo_usd": 0.0021, "segundos": 8.7},
                            "Q22": {**respuesta("No está.", None, esta=False), "costo_usd": 0.001, "segundos": 3}}, None)
chequear("cuenta solo lo respondido, con costo", (datos["bien"], datos["total"], datos["costo_usd"]), (2, 2, 0.0031))

print()
print("Resultado: todo OK" if errores == 0 else f"Resultado: {errores} con error")
