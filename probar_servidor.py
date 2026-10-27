"""Prueba el servidor MCP sin IA: lo levanta, lista sus tools y las llama. Correr: python probar_servidor.py"""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

RUTA_SERVIDOR = Path(__file__).parent / "servidor_mcp.py"
CARPETA_ESTANDAR = Path(__file__).parent / "Data" / "estandar"

# Respuestas verificadas a mano (Bitácora, semana 1)
DUPLICADOS_ESPERADOS = {
    "P03:LT-3306": "SKU102786",
    "P03:LT-3312": "SKU104011",
    "P03:LT-3327": "SKU102387",
    "P03:LT-3333": "SKU100301",
    "P03:LT-3354": "SKU101253",
    "P03:LT-3423": "SKU102541",
    "P03:LT-3432": "SKU104004",
}
POSIBLES_DUPLICADOS_ESPERADOS = {
    "P03:LT-3357": "SKU102275",
    "P03:LT-3447": "SKU100889",
    "P03:LT-3450": "SKU102632",
}

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


async def leer_todas(cliente, proveedor_id):
    """Lee todas las filas del proveedor, tanda por tanda."""
    filas, desde = [], 0
    while desde is not None:
        tanda = (await cliente.call_tool(
            "leer_archivo_proveedor", {"proveedor_id": proveedor_id, "desde": desde, "cantidad": 25}
        )).data
        filas += tanda["filas"]
        desde = tanda["siguiente"]
    return filas


async def main():
    # El servidor escribe en una carpeta temporal: las pruebas nunca pisan los resultados reales
    carpeta_temporal = tempfile.mkdtemp()
    transporte = PythonStdioTransport(RUTA_SERVIDOR, env={"INGESTA_CARPETA_SALIDA": carpeta_temporal})
    async with Client(transporte) as cliente:
        print("--- tools disponibles ---")
        for tool in await cliente.list_tools():
            print(f"- {tool.name}")

        print("\n--- leer_archivo_proveedor ---")
        filas = await leer_todas(cliente, "P03")
        chequear("Litoral tiene 50 filas", len(filas), 50)
        por_id = {fila["item_id"]: fila for fila in filas}
        chequear("LT-3303 en la línea 2", por_id["P03:LT-3303"]["fuente"]["linea"], 2)
        chequear("LT-3345 0,25 LT -> 250 ML",
                 (por_id["P03:LT-3345"]["calculado"]["contenido"], por_id["P03:LT-3345"]["calculado"]["unidad"]), (250, "ML"))
        chequear("LT-3357 sin EAN", por_id["P03:LT-3357"]["calculado"]["motivo_gtin"], "gtin_faltante")
        resultado = await cliente.call_tool("leer_archivo_proveedor", {"proveedor_id": "P06"}, raise_on_error=False)
        chequear("P06 (apartado) bloqueado", resultado.is_error, True)

        print("\n--- leer_archivo_proveedor: el PDF de Limpieza Hogar Sur (semana 2) ---")
        filas_lhs = await leer_todas(cliente, "P07")
        chequear("LHS tiene 25 filas", len(filas_lhs), 25)
        lhs = {fila["item_id"]: fila for fila in filas_lhs}
        chequear("LHS-206: fuente con página (no línea)", lhs["P07:LHS-206"]["fuente"],
                 {"archivo": "LHS_catalogo_nuevos_productos.pdf", "pagina": 1})
        chequear("LHS-206: en original va la fila verificada del PDF", lhs["P07:LHS-206"]["original"]["fila"],
                 "LHS-206 Lavandina Clarita Concentrada 2000 ML 7790840033469 $ 88,04")
        calculado_206 = lhs["P07:LHS-206"]["calculado"]
        chequear("LHS-206: GTIN válido", (calculado_206["gtin"], calculado_206["motivo_gtin"]), ("7790840033469", None))
        chequear("LHS-206: $ 88,04 -> 88.04 UYU", (calculado_206["precio_costo"], calculado_206["moneda"]), (88.04, "UYU"))
        chequear("LHS-206: el PDF no trae marca en columna (la decide el agente)", "marca" in calculado_206, False)
        contenidos = {item: (lhs[item]["calculado"]["contenido"], lhs[item]["calculado"]["unidad"])
                      for item in ["P07:LHS-215", "P07:LHS-212", "P07:LHS-224", "P07:LHS-230", "P07:LHS-218", "P07:LHS-257"]}
        chequear("Contenidos del PDF: X 500 ML, 250ML, 60g, 1 L, 2 LT, 60cc", contenidos,
                 {"P07:LHS-215": (500, "ML"), "P07:LHS-212": (250, "ML"), "P07:LHS-224": (60, "G"),
                  "P07:LHS-230": (1000, "ML"), "P07:LHS-218": (2000, "ML"), "P07:LHS-257": (60, "ML")})
        sin_ean = sorted(item for item, fila in lhs.items() if fila["calculado"]["motivo_gtin"] == "gtin_faltante")
        chequear("LHS: los 2 sin EAN", sin_ean, ["P07:LHS-272", "P07:LHS-275"])
        chequear("LHS: ningún GTIN inválido", [i for i, f in lhs.items() if f["calculado"]["motivo_gtin"] == "gtin_invalido"], [])

        print("\n--- leer_archivo_proveedor: el PDF de Laboratorio Andes (paso 6D2) ---")
        filas_andes = await leer_todas(cliente, "P01")
        chequear("Andes tiene 26 filas", len(filas_andes), 26)
        andes = {fila["item_id"]: fila for fila in filas_andes}
        c_1124 = andes["P01:AN-1124"]["calculado"]
        chequear("AN-1124: 'Crema x 30 g' -> 30 G", (c_1124["contenido"], c_1124["unidad"]), (30, "G"))
        chequear("AN-1124: VL -> VENTA_LIBRE y GTIN válido", (c_1124["condicion_venta"], c_1124["motivo_gtin"]),
                 ("VENTA_LIBRE", None))
        chequear("AN-1112: VBR -> BAJO_RECETA", andes["P01:AN-1112"]["calculado"]["condicion_venta"], "BAJO_RECETA")
        chequear("AN-1103: 'Comp. rec. x 20' -> 20 UN", (andes["P01:AN-1103"]["calculado"]["contenido"],
                 andes["P01:AN-1103"]["calculado"]["unidad"]), (20, "UN"))
        chequear("AN-1106: 'Susp. x 200 ml' -> 200 ML", andes["P01:AN-1106"]["calculado"]["contenido"], 200)
        chequear("AN-1103: sin monodroga en el PDF (queda null en original)", andes["P01:AN-1103"]["original"]["monodroga"],
                 None)
        chequear("AN-1178: el pie no ensucia la fila", andes["P01:AN-1178"]["original"]["fila"],
                 "AN-1178 Febril 1g Paracetamol Comp. x 10 VL 7792542521701 $ 120,52")
        chequear("Todas con precio y condición; contenido vacío solo en los 2 con conflicto (paso 6D3)",
                 (all(f["calculado"]["precio_costo"] and f["calculado"]["condicion_venta"] for f in filas_andes),
                  sorted(i for i, f in andes.items() if f["calculado"]["contenido"] is None)),
                 (True, ["P01:AN-1133", "P01:AN-1136"]))
        chequear("LHS no trae condición de venta (no es lista de medicamentos)", "condicion_venta" in calculado_206, False)

        print("\n--- el cruce PDF <-> Excel de Andes (paso 6D3) ---")
        EXCEL = "Actualizacion_precios_Andes.xlsx"
        c_1124 = andes["P01:AN-1124"]["calculado"]
        chequear("AN-1124: rige el precio del Excel (más nuevo), 320.8 (Q01)", (c_1124["precio_costo"], c_1124["moneda"],
                 c_1124["vigencia_precio"]), (320.8, "UYU", "2026-10-15"))
        chequear("...con SU fuente: el Excel, hoja y fila 12", c_1124["fuentes"]["precio_costo"],
                 {"archivo": EXCEL, "hoja": "Actualización", "fila": 12})
        chequear("...y el contenido no cambió (30 G en los dos): sin conflictos", (c_1124["contenido"], c_1124["conflictos"]),
                 (30, []))
        c_1136 = andes["P01:AN-1136"]["calculado"]
        chequear("AN-1136: conflicto de contenido, con las dos versiones y sus fuentes", c_1136["conflictos"], [
            {"campo": "contenido", "versiones": [
                {"valor": "20 UN", "fuente": {"archivo": "Lista_de_precios_octubre_2026.pdf", "pagina": 1}},
                {"valor": "30 UN", "fuente": {"archivo": EXCEL, "hoja": "Actualización", "fila": 5}}]}])
        chequear("...el contenido queda vacío (no se elige)", (c_1136["contenido"], c_1136["unidad"]), (None, None))
        chequear("...pero el precio sí se resuelve por vigencia: 200.8", c_1136["precio_costo"], 200.8)
        chequear("Con conflicto: solo AN-1133 y AN-1136",
                 sorted(i for i, f in andes.items() if f["calculado"]["conflictos"]), ["P01:AN-1133", "P01:AN-1136"])
        chequear("AN-1148 'Sobres x 6' vs 'Polvo p/ sol. oral, sobres x 6': NO es conflicto",
                 (andes["P01:AN-1148"]["calculado"]["contenido"], andes["P01:AN-1148"]["calculado"]["conflictos"]), (6, []))
        c_1103 = andes["P01:AN-1103"]["calculado"]
        chequear("AN-1103 (no está en el Excel): precio y vigencia del PDF, sin fuentes aparte",
                 (c_1103["precio_costo"], c_1103["vigencia_precio"], c_1103["fuentes"]), (265.29, "2026-10-01", {}))
        chequear("Los 12 del Excel llevan su fila en original.actualizacion",
                 sum("actualizacion" in f["original"] for f in filas_andes), 12)
        chequear("LHS no tiene actualizaciones: sin conflictos ni fuentes aparte",
                 ("conflictos" in calculado_206, "fuentes" in calculado_206), (False, False))

        print("\n--- calculado.fds: el cruce producto <-> FDS (paso 4C) ---")
        chequear("LHS-206: la lavandina, corrosivo + ONU 1791 con la fuente de SU FDS", lhs["P07:LHS-206"]["calculado"]["fds"],
                 {"peligro_deposito": "corrosivo", "numero_onu": "1791",
                  "fuente": {"archivo": "FDS_Clarita_lavandina.pdf", "pagina": 1}, "problemas": []})
        chequear("LHS-203: multiuso no regulado, sin ONU",
                 (lhs["P07:LHS-203"]["calculado"]["fds"]["peligro_deposito"], lhs["P07:LHS-203"]["calculado"]["fds"]["numero_onu"]),
                 ("no_peligroso", None))
        chequear("LHS-275 (sin EAN) igual tiene su FDS: alcohol, líquido inflamable",
                 lhs["P07:LHS-275"]["calculado"]["fds"]["peligro_deposito"], "liquido_inflamable")
        chequear("LHS-260 y LHS-233: aerosoles inflamables",
                 {lhs[i]["calculado"]["fds"]["peligro_deposito"] for i in ["P07:LHS-260", "P07:LHS-233"]}, {"aerosol_inflamable"})
        sin_fds = sorted(item for item, fila in lhs.items() if fila["calculado"]["fds"] is None)
        chequear("Sin FDS: justo los 3 que no nombra ninguna", sin_fds, ["P07:LHS-221", "P07:LHS-248", "P07:LHS-266"])
        chequear("Litoral: no mandó FDS, fds es null", por_id["P03:LT-3303"]["calculado"]["fds"], None)

        print("\n--- buscar_por_gtin / buscar_parecidos: LHS contra el catálogo ---")
        encontrados_lhs = {}
        for fila in filas_lhs:
            if fila["calculado"]["gtin"] is not None:
                respuesta = (await cliente.call_tool("buscar_por_gtin", {"gtin": fila["calculado"]["gtin"]})).data
                if respuesta["encontrado"]:
                    encontrados_lhs[fila["item_id"]] = respuesta["sku"]
        chequear("LHS: los 3 duplicados por GTIN", encontrados_lhs,
                 {"P07:LHS-221": "SKU102464", "P07:LHS-248": "SKU101505", "P07:LHS-266": "SKU101834"})
        candidatos_lhs = {}
        for item, marca in [("P07:LHS-275", "CLARITA"), ("P07:LHS-272", "FULMIN")]:  # la marca la pondría el agente
            calculado = lhs[item]["calculado"]
            respuesta = (await cliente.call_tool("buscar_parecidos", {
                "marca": marca, "contenido": calculado["contenido"], "unidad": calculado["unidad"]})).data
            candidatos_lhs[item] = [c["sku"] for c in respuesta["candidatos"]]
        chequear("LHS-272 (Fulmin crema 100 G) trae solo su candidato", candidatos_lhs["P07:LHS-272"], ["SKU102282"])
        chequear("LHS-275 (Clarita 96 % 500 CC) trae los 4 Clarita de 500 ML, con el correcto entre ellos",
                 (len(candidatos_lhs["P07:LHS-275"]), "SKU101386" in candidatos_lhs["P07:LHS-275"]), (4, True))

        print("\n--- buscar_por_gtin: los 50 de Litoral ---")
        encontrados = {}
        for fila in filas:
            gtin = fila["calculado"]["gtin"]
            if gtin is None:
                continue  # sin GTIN: no se busca por acá
            respuesta = (await cliente.call_tool("buscar_por_gtin", {"gtin": gtin})).data
            if respuesta["encontrado"]:
                encontrados[fila["item_id"]] = respuesta["sku"]
                print(f"      {fila['item_id']} -> {respuesta['sku']} {respuesta['descripcion']} (línea {respuesta['fuente']['linea']})")
        chequear("Se encontraron exactamente los 7 duplicados esperados", encontrados, DUPLICADOS_ESPERADOS)

        print("\n--- buscar_por_gtin: argumentos malos (tienen que dar error) ---")
        resultado = await cliente.call_tool("buscar_por_gtin", {"gtin": "779-7137-44403-8"}, raise_on_error=False)
        chequear("GTIN con guiones se rechaza", resultado.is_error, True)
        resultado = await cliente.call_tool("buscar_por_gtin", {"gtin": "123"}, raise_on_error=False)
        chequear("GTIN corto se rechaza", resultado.is_error, True)

        print("\n--- buscar_parecidos: los 3 de Litoral sin GTIN ---")
        candidatos_por_item = {}
        for fila in filas:
            calculado = fila["calculado"]
            if calculado["gtin"] is not None:
                continue  # con GTIN no se buscan parecidos
            respuesta = (await cliente.call_tool("buscar_parecidos", {
                "marca": calculado["marca"], "contenido": calculado["contenido"], "unidad": calculado["unidad"],
            })).data
            candidatos_por_item[fila["item_id"]] = [c["sku"] for c in respuesta["candidatos"]]
            for c in respuesta["candidatos"]:
                print(f"      {fila['item_id']} {calculado['descripcion_expandida']} {calculado['marca']} "
                      f"-> {c['sku']} {c['descripcion_expandida']}")
        chequear("Cada uno trae exactamente su candidato",
                 candidatos_por_item, {item: [sku] for item, sku in POSIBLES_DUPLICADOS_ESPERADOS.items()})

        print("\n--- buscar_parecidos: casos que el agente tiene que juzgar ---")
        respuesta = (await cliente.call_tool("buscar_parecidos", {"marca": "SONRISA", "contenido": 180, "unidad": "G"})).data
        chequear("SONRISA 180 G trae 3 candidatos (distintas variantes)", respuesta["cantidad"], 3)
        respuesta = (await cliente.call_tool("buscar_parecidos", {"marca": "DENTIBLANC", "contenido": 180, "unidad": "G"})).data
        chequear("DENTIBLANC 180 G no trae ninguno", respuesta["cantidad"], 0)
        resultado = await cliente.call_tool("buscar_parecidos",
                                            {"marca": "PUREZA", "contenido": 90, "unidad": "GRS"}, raise_on_error=False)
        chequear("Unidad sin normalizar (GRS) se rechaza", resultado.is_error, True)

        print("\n--- registrar_ficha: resultados coherentes (se guardan) ---")
        fuente_3303 = por_id["P03:LT-3303"]["fuente"]
        ficha_ejemplo = {"gtin": "7793469616846", "marca": "SONRISA", "tipo": "PASTA DENTAL", "contenido": 90, "unidad": "G"}
        fuentes_ejemplo = {campo: fuente_3303 for campo in ficha_ejemplo}
        categoria_ejemplo = {"campo": "tipo", "valor": "PASTA DENTAL", "explicacion": "Pasta dental va en cuidado bucal."}
        base = {"ficha": ficha_ejemplo, "fuentes": fuentes_ejemplo, "categoria_decidida_por": categoria_ejemplo}
        casos_ok = [
            ("lista_para_alta", {"item_id": "P03:LT-3303", "estado": "lista_para_alta"}),
            ("duplicado con su SKU", {"item_id": "P03:LT-3333", "estado": "duplicado", "duplicado_de": "SKU100301"}),
            ("a_revision posible duplicado", {"item_id": "P03:LT-3447", "estado": "a_revision",
                                              "motivos_revision": ["gtin_faltante", "posible_duplicado"],
                                              "duplicado_de": "SKU100889"}),
            ("mismo ítem otra vez (reemplaza)", {"item_id": "P03:LT-3303", "estado": "lista_para_alta"}),
        ]
        for nombre, argumentos in casos_ok:
            resultado = await cliente.call_tool(
                "registrar_ficha", {**base, **argumentos}, raise_on_error=False)
            chequear(nombre, resultado.is_error, False)
        chequear("Quedaron 3 ítems guardados (no 4)", resultado.data["total_registrados"], 3)

        print("\n--- registrar_ficha: resultados incoherentes (NO se guardan) ---")
        casos_error = [
            ("duplicado sin SKU", {"item_id": "P03:LT-3306", "estado": "duplicado"}),
            ("a_revision sin motivo", {"item_id": "P03:LT-3357", "estado": "a_revision"}),
            ("lista_para_alta con motivo", {"item_id": "P03:LT-3309", "estado": "lista_para_alta",
                                            "motivos_revision": ["gtin_faltante"]}),
            ("posible_duplicado sin SKU", {"item_id": "P03:LT-3450", "estado": "a_revision",
                                           "motivos_revision": ["gtin_faltante", "posible_duplicado"]}),
            ("SKU que no existe", {"item_id": "P03:LT-3312", "estado": "duplicado", "duplicado_de": "SKU999999"}),
            ("ítem que no existe", {"item_id": "P03:LT-9999", "estado": "lista_para_alta"}),
            ("estado fuera del vocabulario", {"item_id": "P03:LT-3315", "estado": "aprobado"}),
            ("motivo fuera del vocabulario", {"item_id": "P03:LT-3318", "estado": "a_revision",
                                              "motivos_revision": ["sin_precio"]}),
            ("categoría sin explicar", {"item_id": "P03:LT-3321", "estado": "lista_para_alta",
                                        "categoria_decidida_por": None}),
            ("categoría explicada con un dato inventado", {"item_id": "P03:LT-3324", "estado": "lista_para_alta",
                                                           "categoria_decidida_por": {"campo": "tipo", "valor": "JABON",
                                                                                      "explicacion": "Es un jabón."}}),
        ]
        for nombre, argumentos in casos_error:
            resultado = await cliente.call_tool(
                "registrar_ficha", {**base, **argumentos}, raise_on_error=False)
            chequear(nombre, resultado.is_error, True)
            if nombre in ("duplicado sin SKU", "categoría explicada con un dato inventado"):
                print(f"      lo que recibe el modelo: {resultado.content[0].text}")

        guardado = json.loads((Path(carpeta_temporal) / "resultados.json").read_text(encoding="utf-8"))
        chequear("En el archivo están solo los 3 coherentes", sorted(guardado), ["P03:LT-3303", "P03:LT-3333", "P03:LT-3447"])

        print("\n--- registrar_ficha: un ítem del PDF ---")
        fuente_206 = lhs["P07:LHS-206"]["fuente"]
        resultado = await cliente.call_tool("registrar_ficha", {
            **base, "item_id": "P07:LHS-206", "estado": "lista_para_alta",
            "fuentes": {campo: fuente_206 for campo in ficha_ejemplo}}, raise_on_error=False)
        chequear("Se registra un ítem de P07 con fuente {archivo, pagina}", resultado.is_error, False)

        print("\n--- resources: el estándar ---")
        recursos = {str(r.uri) for r in await cliente.list_resources()}
        chequear("Hay 3 resources", sorted(recursos),
                 ["estandar://ficha_de_producto", "estandar://taxonomia", "estandar://vocabulario"])
        for uri, archivo in [("estandar://ficha_de_producto", "ficha_de_producto.md"),
                             ("estandar://vocabulario", "vocabulario.yaml"),
                             ("estandar://taxonomia", "taxonomia.csv")]:
            texto = (await cliente.read_resource(uri))[0].text
            original = (CARPETA_ESTANDAR / archivo).read_text(encoding="utf-8-sig")
            chequear(f"{uri} es idéntico a {archivo} ({len(texto)} caracteres)", texto, original)

    print("\n--- fds_del_producto (casos armados, sin el servidor) ---")
    from servidor_mcp import fds_del_producto  # la función sola: no levanta el servidor
    lavandina = {"archivo": "FDS_a.pdf", "codigos": ["X-100"], "peligro_deposito": "corrosivo", "numero_onu": "1791",
                 "fuente": {"archivo": "FDS_a.pdf", "pagina": 1}, "problemas": []}
    otra = {**lavandina, "archivo": "FDS_b.pdf", "fuente": {"archivo": "FDS_b.pdf", "pagina": 1}}
    resultado = fds_del_producto("X-100", {"X-100": [lavandina, otra]})
    chequear("Código en 2 FDS: sin peligro (no se elige una)", (resultado["peligro_deposito"], resultado["fuente"]), (None, None))
    chequear("...y queda el problema con los dos archivos", "FDS_a.pdf, FDS_b.pdf" in resultado["problemas"][0], True)
    chequear("Código que ninguna FDS nombra: None", fds_del_producto("X-999", {"X-100": [lavandina]}), None)

    print("\n--- consolidar (casos armados, sin el servidor) ---")
    from servidor_mcp import consolidar  # la función sola
    MAPA_PDF = {"descripcion": "producto", "presentacion": "presentacion", "precio": "precio"}
    MAPA_EXCEL = {"descripcion": "Producto", "presentacion": "Presentación", "precio": "Precio nuevo"}
    PDF_01 = {"fecha": "2026-10-01"}

    def fila_pdf():
        """Una fila de Andes como la arma leer_filas_pdf, antes del cruce."""
        return {"fuente": {"archivo": "a.pdf", "pagina": 1},
                "original": {"producto": "Febril 1g", "presentacion": "Comp. x 10", "precio": "$ 120,52"},
                "calculado": {"contenido": 10, "unidad": "UN", "precio_costo": 120.52, "moneda": "UYU",
                              "descripcion_expandida": "FEBRIL 1G", "conflictos": [], "fuentes": {},
                              "vigencia_precio": "2026-10-01"}}

    def fila_excel(**cambios):
        """Una fila del Excel de actualización, con lo que se le cambie."""
        valores = {"Producto": "Febril 1 g", "Presentación": "Comprimidos x 10", "Precio nuevo": 130.0, **cambios}
        return {"fuente": {"archivo": "b.xlsx", "hoja": "H", "fila": 5}, "original": valores}

    fila = fila_pdf()
    consolidar(fila, fila["original"], MAPA_PDF, PDF_01, fila_excel(), MAPA_EXCEL, {"fecha": "2026-09-01"}, "UYU")
    chequear("Excel MÁS VIEJO que el PDF: rige el PDF", (fila["calculado"]["precio_costo"], fila["calculado"]["fuentes"]),
             (120.52, {}))
    fila = fila_pdf()
    consolidar(fila, fila["original"], MAPA_PDF, PDF_01, fila_excel(), MAPA_EXCEL, None, "UYU")
    chequear("Excel sin vigencia: no se decide el precio (vacío + conflicto)",
             (fila["calculado"]["precio_costo"], [c["campo"] for c in fila["calculado"]["conflictos"]]),
             (None, ["precio_costo"]))
    fila = fila_pdf()
    consolidar(fila, fila["original"], MAPA_PDF, PDF_01, fila_excel(), MAPA_EXCEL, {"fecha": "2026-10-01"}, "UYU")
    chequear("Misma vigencia y precios distintos: no se decide", fila["calculado"]["precio_costo"], None)
    fila = fila_pdf()
    consolidar(fila, fila["original"], MAPA_PDF, PDF_01, fila_excel(**{"Precio nuevo": 120.52}), MAPA_EXCEL, None, "UYU")
    chequear("Mismo precio en los dos: no hay nada que decidir (sin conflicto)", fila["calculado"]["conflictos"], [])
    fila = fila_pdf()
    consolidar(fila, fila["original"], MAPA_PDF, PDF_01, fila_excel(Producto="Febril 500 mg"), MAPA_EXCEL,
               {"fecha": "2026-10-15"}, "UYU")
    chequear("Nombre distinto (no solo espacios): conflicto de descripción",
             [c["campo"] for c in fila["calculado"]["conflictos"]], ["descripcion"])

    shutil.rmtree(carpeta_temporal, ignore_errors=True)  # borramos la carpeta temporal de las pruebas
    print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")


asyncio.run(main())