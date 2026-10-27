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

    shutil.rmtree(carpeta_temporal, ignore_errors=True)  # borramos la carpeta temporal de las pruebas
    print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")


asyncio.run(main())