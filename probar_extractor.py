"""Pruebas de extractor_pdf.py con el texto REAL que citó la API en el paso 1. Correr: python probar_extractor.py"""
import copy
import json
from pathlib import Path

from extractor_pdf import (COLUMNAS_POR_PDF, buscar_fila, campos_desde_respuesta, codigo_al_inicio, codigos_en_citas, filas_de_un_texto,
                           filas_desde_citas, filas_verificadas, normalizar_espacios, tool_campos, valor_en_fila,
                           verificar_campos)

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

COLUMNAS_LHS = COLUMNAS_POR_PDF["LHS_catalogo_nuevos_productos.pdf"]
COLUMNAS_ANDES = COLUMNAS_POR_PDF["Lista_de_precios_octubre_2026.pdf"]

print("--- verificar_campos ---")
FILA_215 = "LHS-215 Limpiador Clarita Multiuso Lavanda X 500 ML 7792189253836 $ 83,84"
BIEN_206 = {"descripcion": "Lavandina Clarita Concentrada", "contenido": "2000 ML",
            "ean": "7790840033469", "costo": "$ 88,04"}
campos, _, problemas = verificar_campos("LHS-206", FILA_206, BIEN_206, COLUMNAS_LHS, admite_ajeno=False)
chequear("LHS-206 bien separado: quedan los 4", campos, BIEN_206)
chequear("...sin problemas", problemas, [])
campos, _, problemas = verificar_campos("LHS-275", FILA_275, {"descripcion": "Alcohol Clarita 96 %", "contenido": "500 CC",
                                                           "ean": None, "costo": "$ 117,34"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("LHS-275 sin EAN: queda None y la fila cierra igual", (campos["ean"], problemas), (None, []))
campos, _, _ = verificar_campos("LHS-275", FILA_275, {"descripcion": "Alcohol Clarita 96 %", "contenido": "500 CC",
                                                   "ean": "", "costo": "$ 117,34"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("EAN vacío \"\" se toma como None", campos["ean"], None)
campos, _, problemas = verificar_campos("LHS-215", FILA_215, {"descripcion": "Limpiador Clarita Multiuso Lavanda",
                                                           "contenido": "X 500 ML", "ean": "7792189253836",
                                                           "costo": "$ 83,84"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("LHS-215 con la X en el contenido: cierra", problemas, [])
campos, _, problemas = verificar_campos("LHS-215", FILA_215, {"descripcion": "Limpiador Clarita Multiuso Lavanda",
                                                           "contenido": "500 ML", "ean": "7792189253836",
                                                           "costo": "$ 83,84"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("LHS-215 con la X perdida: problema (falta algo)", len(problemas), 1)
campos, _, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "descripcion": "Lavandina Clarita Concentrada 2000 ML"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("Descripción que se comió el contenido: problema (sobra algo)", len(problemas), 1)
chequear("...pero los campos no se tiran", campos["descripcion"], "Lavandina Clarita Concentrada 2000 ML")
campos, _, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "costo": "$ 88,40"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("Costo inventado: queda vacío", campos["costo"], None)
chequear("...y es el único problema (el control 2 no se suma)", len(problemas), 1)
campos, _, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "ean": "7794288526675"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("EAN de otra fila: queda vacío", (campos["ean"], len(problemas)), (None, 1))
campos, _, problemas = verificar_campos("LHS-206", FILA_206, {**BIEN_206, "costo": "$\xa088,04"}, COLUMNAS_LHS, admite_ajeno=False)
chequear("Espacio raro en el valor: se normaliza y pasa", (campos["costo"], problemas), ("$ 88,04", []))

print("--- campos_desde_respuesta ---")
FILAS_2 = {"LHS-206": {"codigo": "LHS-206", "pagina": 1, "fila": FILA_206},
           "LHS-275": {"codigo": "LHS-275", "pagina": 1, "fila": FILA_275}}
P206 = {"codigo": "LHS-206", **BIEN_206}
P275 = {"codigo": "LHS-275", "descripcion": "Alcohol Clarita 96 %", "contenido": "500 CC", "ean": None, "costo": "$ 117,34"}


def entrega(productos):
    """Una respuesta de mentira de la llamada 2: Haiku llamando a entregar_campos."""
    return [{"type": "tool_use", "id": "x", "name": "entregar_campos", "input": {"productos": productos}}]


productos, problemas = campos_desde_respuesta(entrega([P275, P206]), FILAS_2, COLUMNAS_LHS)
chequear("Llegan desordenados: salen en el orden del PDF", [p["codigo"] for p in productos], ["LHS-206", "LHS-275"])
chequear("...sin problemas en ningún lado", ([p["problemas"] for p in productos], problemas), ([[], []], []))
chequear("...y cada producto conserva su página y su fila", (productos[0]["pagina"], productos[0]["fila"]), (1, FILA_206))
productos, problemas = campos_desde_respuesta(entrega([P206]), FILAS_2, COLUMNAS_LHS)
chequear("Falta LHS-275: no desaparece", len(productos), 2)
chequear("...queda con campos vacíos y su marca", (productos[1]["campos"]["costo"], len(productos[1]["problemas"])), (None, 1))
productos, problemas = campos_desde_respuesta(entrega([P206, P275, {**P206, "codigo": "LHS-999"}, "basura"]), FILAS_2, COLUMNAS_LHS)
chequear("Código inventado y basura: 2 problemas generales", len(problemas), 2)
chequear("...y los productos buenos no se tocan", [p["problemas"] for p in productos], [[], []])
productos, _ = campos_desde_respuesta(entrega([P206, P206, P275]), FILAS_2, COLUMNAS_LHS)
chequear("Repetido idéntico: sin problemas", productos[0]["problemas"], [])
productos, _ = campos_desde_respuesta(entrega([P206, {**P206, "contenido": "2000"}, P275]), FILAS_2, COLUMNAS_LHS)
chequear("Repetido distinto: marcado y sin campos", (len(productos[0]["problemas"]), productos[0]["campos"]["descripcion"]), (1, None))
productos, problemas = campos_desde_respuesta([{"type": "text", "text": "Listo"}], FILAS_2, COLUMNAS_LHS)
chequear("No llamó a la tool: problema general", len(problemas), 1)
chequear("...y las 2 filas quedan marcadas, no desaparecen", [len(p["problemas"]) for p in productos], [1, 1])
productos, _ = campos_desde_respuesta(entrega([{**P206, "costo": "$ 88,40"}, P275]), FILAS_2, COLUMNAS_LHS)
chequear("Costo inventado: pasa por verificar_campos y queda vacío", productos[0]["campos"]["costo"], None)

print("--- codigo_al_inicio (paso 6B) ---")
chequear("Código normal", codigo_al_inicio("AN-1103 Dolorex 400mg Comp."), "AN-1103")
chequear("Código pegado a la palabra (cita de Andes)", codigo_al_inicio("AN-1148Gripanil 500 mg + 4 mg + 10"), "AN-1148")
chequear("Código sin guion (Norte)", codigo_al_inicio("IN7003 Dry Shampoo"), "IN7003")
chequear("Renglón de continuación: no es código", codigo_al_inicio("VBR 7797752654089 $ 159,80"), None)
chequear("Renglón suelto 'ml': no es código", codigo_al_inicio("ml"), None)
chequear("Un SKU no es un código de proveedor", codigo_al_inicio("SKU100301 PASTA DENTAL"), None)
chequear("Encabezado: no es código", codigo_al_inicio("Código Producto Monodroga"), None)

print("--- filas_de_un_texto (paso 6B) ---")
PEDAZO = ("x 20 VL 7794394922729 $\xa0265,29\r\nAN-1106 Antiacid 400 mg + 400 mg/5\r\nml\r\n"
          "Susp. x 200 ml VL 7799252522035 $\xa0156,16\r\nAN-1109 Febril 1g Paracetamol Comp. ")
chequear("Une los renglones partidos y lo de antes del primer código se ignora", filas_de_un_texto(PEDAZO), [
    ("AN-1106", "AN-1106 Antiacid 400 mg + 400 mg/5 ml Susp. x 200 ml VL 7799252522035 $ 156,16", True),
    ("AN-1109", "AN-1109 Febril 1g Paracetamol Comp.", False)])
chequear("Código pegado: se separa", filas_de_un_texto("AN-1148Gripanil 500 mg\r\nAN-1151 Flexigel")[0][1],
         "AN-1148 Gripanil 500 mg")
chequear("Ligadura del PDF (ﬁ -> fi)", filas_de_un_texto("AN-1166 Laxo\ufb01b 5mg")[0][1], "AN-1166 Laxofib 5mg")
chequear("Sin códigos: ninguna fila", filas_de_un_texto("Laboratorio Andes S.A.\r\nPrecios sin IVA. "), [])

print("--- filas_desde_citas (citas REALES de Andes, paso 6A) ---")
ANDES = json.loads((RUTA_EXPERIMENTO.parent / "citas_andes_preguntas.json").read_text(encoding="utf-8"))["content"]
filas_a, problemas_a = filas_desde_citas(ANDES)
chequear("Las 26 filas de Andes, sin problemas", (len(filas_a), problemas_a), (26, []))
chequear("AN-1106: 'ml' unido a su celda",
         filas_a["AN-1106"]["fila"], "AN-1106 Antiacid 400 mg + 400 mg/5 ml Susp. x 200 ml VL 7799252522035 $ 156,16")
chequear("AN-1139: 'Comprimidos x' + '30'",
         filas_a["AN-1139"]["fila"], "AN-1139 Cardiopres 20mg Enalapril Comprimidos x 30 VBR 7797752654089 $ 159,80")
chequear("AN-1142: 4 renglones en orden",
         filas_a["AN-1142"]["fila"], "AN-1142 Gripanil 500 mg + 4 mg + 10 mg Paracetamol + Clorfeniramina + "
                                     "Fenilefrina Comp. x 10 VL 7795761445278 $ 183,45")
chequear("AN-1151: 'x 60' + 'gr'", "Gel tópico x 60 gr VL" in filas_a["AN-1151"]["fila"], True)
chequear("AN-1148: pegado en una cita y separado en otra -> la misma fila",
         filas_a["AN-1148"]["fila"].startswith("AN-1148 Gripanil 500 mg + 4 mg + 10 mg"), True)
chequear("Todas de la página 1 (la da la API)", {f["pagina"] for f in filas_a.values()}, {1})
chequear("Solo la última (AN-1178) queda abierta, con el pie pegado",
         [c for c, f in filas_a.items() if not f["cerrada"]], ["AN-1178"])

print("--- filas_desde_citas (citas REALES de LHS, paso 1) ---")
filas_l, problemas_l = filas_desde_citas(copy.deepcopy(respuesta["content"]))
chequear("Las 25 filas de LHS (la cita traía la tabla entera), sin problemas", (len(filas_l), problemas_l), (25, []))
chequear("Las mismas filas que buscar_fila", {c: f["fila"] for c, f in filas_l.items() if f["cerrada"]},
         {c: buscar_fila(CITA, c) for c, f in filas_l.items() if f["cerrada"]})
chequear("LHS-269 (la última) abierta: su fila + el pie",
         filas_l["LHS-269"]["fila"], FILA_269 + " Las fichas de datos de seguridad se envían por separado.")

print("--- filas_desde_citas (casos armados) ---")


def bloque_citado(*textos, pagina=1, texto="x"):
    """Un bloque de mentira con una cita por cada texto."""
    return {"type": "text", "text": texto,
            "citations": [{"cited_text": t, "start_page_number": pagina, "end_page_number": pagina + 1} for t in textos]}


DOS = "AN-1160 Tiroxan 100 mcg Comprimidos x 30\r\nAN-1163 Diacort"
filas_c, problemas_c = filas_desde_citas([bloque_citado(DOS, DOS.replace("100 mcg", "100mcg"))])
chequear("Versiones que solo difieren en espacios: se elige, sin problema", ("AN-1160" in filas_c, problemas_c), (True, []))
filas_c, problemas_c = filas_desde_citas([bloque_citado(DOS, DOS.replace("x 30", "x 60"))])
chequear("Dos versiones completas distintas: no se elige", ("AN-1160" in filas_c, len(problemas_c)), (False, 1))
filas_c, problemas_c = filas_desde_citas([bloque_citado("AN-1160 Tiroxan 50 mcg", DOS)])
chequear("Versión cortada que no es el principio de la completa: no se elige", ("AN-1160" in filas_c, len(problemas_c)),
         (False, 1))
filas_c, problemas_c = filas_desde_citas([bloque_citado(DOS, pagina=1), bloque_citado(DOS, pagina=2)])
chequear("Mismos códigos en dos páginas: no se elige ninguno (son 2: AN-1160 y AN-1163)", (filas_c, len(problemas_c)),
         ({}, 2))
filas_c, problemas_c = filas_desde_citas([bloque_citado(DOS), {"type": "text", "text": "AN-1199: no figura", "citations": None}])
chequear("Haiku nombró un código que no está citado: problema de cobertura",
         problemas_c, ["AN-1199: Haiku lo nombró pero no aparece en ningún texto citado."])

print("--- columnas por PDF y texto ajeno (paso 6B2) ---")
herramienta = tool_campos(COLUMNAS_ANDES)
propiedades = herramienta["input_schema"]["properties"]["productos"]["items"]["properties"]
chequear("La tool de Andes tiene sus columnas + código + texto ajeno", list(propiedades),
         ["codigo", "producto", "monodroga", "presentacion", "condicion", "ean", "precio", "texto_ajeno"])
chequear("...y todas son obligatorias (se pueden mandar en null, no omitir)",
         herramienta["input_schema"]["properties"]["productos"]["items"]["required"], list(propiedades))
FILA_1106 = filas_a["AN-1106"]["fila"]
BIEN_1106 = {"producto": "Antiacid 400 mg + 400 mg/5 ml", "monodroga": None, "presentacion": "Susp. x 200 ml",
             "condicion": "VL", "ean": "7799252522035", "precio": "$ 156,16"}
campos, ajeno, problemas = verificar_campos("AN-1106", FILA_1106, BIEN_1106, COLUMNAS_ANDES, admite_ajeno=False)
chequear("AN-1106 (celda partida, sin monodroga): cierra", (campos, ajeno, problemas), (BIEN_1106, None, []))
FILA_1178 = filas_a["AN-1178"]["fila"]
PIE = "Laboratorio Andes S.A. · Lista de precios octubre 2026 Página 1 de 1"
BIEN_1178 = {"producto": "Febril 1g", "monodroga": "Paracetamol", "presentacion": "Comp. x 10", "condicion": "VL",
             "ean": "7792542521701", "precio": "$ 120,52"}
campos, ajeno, problemas = verificar_campos("AN-1178", FILA_1178, {**BIEN_1178, "texto_ajeno": PIE}, COLUMNAS_ANDES,
                                            admite_ajeno=True)
chequear("AN-1178 (la última): el pie va como texto ajeno y cierra", (ajeno, problemas), (PIE, []))
_, _, problemas = verificar_campos("AN-1178", FILA_1178, BIEN_1178, COLUMNAS_ANDES, admite_ajeno=True)
chequear("...si no dice nada del pie, la fila no cierra (nada se pierde sin decirlo)", len(problemas), 1)
_, ajeno, problemas = verificar_campos("AN-1106", FILA_1106, {**BIEN_1106, "texto_ajeno": "x"}, COLUMNAS_ANDES,
                                       admite_ajeno=False)
chequear("Texto ajeno en una fila que no es la última: no se acepta", (ajeno, len(problemas)), (None, 1))
SIN_PRECIO = {**BIEN_1106, "precio": None, "texto_ajeno": "$ 156,16"}
campos, _, problemas = verificar_campos("AN-1106", FILA_1106, SIN_PRECIO, COLUMNAS_ANDES, admite_ajeno=False)
chequear("Esconder el precio como 'texto ajeno' en una fila cerrada: no pasa (precio vacío + el problema)",
         (campos["precio"], len(problemas)), (None, 1))
FILAS_LHS = {"LHS-269": filas_l["LHS-269"]}
PIE_LHS = "Las fichas de datos de seguridad se envían por separado."
P269 = {"codigo": "LHS-269", "descripcion": "Lavandina Clarita Concentrada", "contenido": "1000 ML",
        "ean": "7793634603527", "costo": "$ 54,71", "texto_ajeno": PIE_LHS}
productos, _ = campos_desde_respuesta(entrega([P269]), FILAS_LHS, COLUMNAS_LHS)
chequear("LHS-269: sin problemas y el pie queda aparte", (productos[0]["problemas"], productos[0]["texto_ajeno"]),
         ([], PIE_LHS))
chequear("...y su 'fila' queda igual que antes (sin el pie)", productos[0]["fila"], FILA_269)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")