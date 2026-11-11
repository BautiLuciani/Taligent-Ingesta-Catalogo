"""Pruebas del servidor leyendo los Excel nuevos con su receta (semana 4, paso 3). Sin IA. Correr: python probar_servidor_excel.py

Las recetas se arman acá desde las respuestas CONGELADAS de la corrida 6 del recepcionista (salida/experimentos/
recepcion_v6/), no desde salida/recepcion/, que el sistema reescribe (lección del paso 0).
"""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from referencias import ENTORNO_PRUEBAS  # extracciones y recepción congeladas; va antes que servidor_mcp
import servidor_mcp  # noqa: E402
from recepcion import propuesta_de_la_respuesta, resumen_del_excel, verificar_receta  # noqa: E402

PROVEEDORES = Path(__file__).parent / "Data" / "proveedores"
CORRIDA_6 = Path(__file__).parent / "salida" / "experimentos" / "recepcion_v6"
ARCHIVOS = {
    "P02": (PROVEEDORES / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx", "ALTAS RIVERA"),
    "P04": (PROVEEDORES / "P04_Higiene_Total" / "HigieneTotal_novedades.xlsx", "HigieneTotal"),
    "P08": (PROVEEDORES / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx", "NorteImports"),
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


def filas_de(proveedor_id: str) -> dict[str, dict]:
    """Las filas que arma el servidor para ese proveedor, por código, con la receta de la corrida 6."""
    ruta, prefijo = ARCHIVOS[proveedor_id]
    respuesta = json.loads(next(CORRIDA_6.glob(f"{prefijo}*.receta_*.json")).read_text(encoding="utf-8"))
    receta = verificar_receta(resumen_del_excel(ruta), propuesta_de_la_respuesta(respuesta), ruta)["receta"]
    filas = servidor_mcp.leer_filas_excel(proveedor_id, {"formato": "excel", "archivo": ruta, "receta": receta})
    return {fila["item_id"].split(":", 1)[1]: fila for fila in filas}


print("--- 3A · Rivera (P02): contenido dentro de la descripción, EAN con guiones ---")
rivera = filas_de("P02")
chequear("50 productos (los títulos de sección no son productos)", len(rivera), 50)
chequear("La misma forma que las filas del CSV y del PDF", sorted(rivera["RIV-1206"]), ["calculado", "fuente", "item_id", "original"])
chequear("item_id = proveedor:código", rivera["RIV-1206"]["item_id"], "P02:RIV-1206")
chequear("Fuente {archivo, hoja, fila} (la que pide la guía para un Excel)", rivera["RIV-1206"]["fuente"],
         {"archivo": "ALTAS RIVERA OCT.xlsx", "hoja": "Altas", "fila": 8})
chequear("RIV-1206: EAN con guiones normalizado (Q10, duplicado de SKU100714)", rivera["RIV-1206"]["calculado"]["gtin"],
         "7797137444038")
chequear("RIV-1203: dígito verificador malo -> gtin_invalido y sin GTIN (Q09)",
         (rivera["RIV-1203"]["calculado"]["gtin"], rivera["RIV-1203"]["calculado"]["motivo_gtin"]), (None, "gtin_invalido"))
chequear("RIV-1275: '0,5 KG' al final de la descripción -> 500 G",
         (rivera["RIV-1275"]["calculado"]["contenido"], rivera["RIV-1275"]["calculado"]["unidad"]), (500, "G"))
chequear("RIV-1215: '750cc' -> 750 ML", (rivera["RIV-1215"]["calculado"]["contenido"], rivera["RIV-1215"]["calculado"]["unidad"]),
         (750, "ML"))
chequear("Las abreviaturas se expanden (SH. -> SHAMPOO)", rivera["RIV-1215"]["calculado"]["descripcion_expandida"],
         "SHAMPOO NATIVA COLOR 750CC")
chequear("Precio como número y moneda de la receta (UYU)",
         (rivera["RIV-1206"]["calculado"]["precio_costo"], rivera["RIV-1206"]["calculado"]["moneda"]), (147.76, "UYU"))
chequear("La marca no va en calculado (la decide el agente, como en los PDF)", "marca" in rivera["RIV-1206"]["calculado"], False)
chequear("OBS llega en original, tal cual (el agente decide que no va a la ficha)", rivera["RIV-1218"]["original"]["OBS"],
         "PACK PROMO CON NECESER")
chequear("Las 50 con contenido calculado", sum(1 for f in rivera.values() if f["calculado"]["contenido"] is None), 0)

print("--- 3A · Higiene Total (P04): solo la hoja Altas, contenido en dos columnas ---")
higiene = filas_de("P04")
chequear("28 productos: los de Altas", len(higiene), 28)
chequear("Ningún discontinuado entra (HT32855 está en Discontinuados, Q11)", "HT32855" in higiene, False)
chequear("HT40006: 1 + 'Lts' -> 1000 ML", (higiene["HT40006"]["calculado"]["contenido"], higiene["HT40006"]["calculado"]["unidad"]),
         (1000, "ML"))
chequear("HT40003: 300 + 'cc' -> 300 ML", (higiene["HT40003"]["calculado"]["contenido"], higiene["HT40003"]["calculado"]["unidad"]),
         (300, "ML"))
chequear("Los 5 sin EAN -> gtin_faltante (los de nuestras notas)",
         sorted(c for c, f in higiene.items() if f["calculado"]["motivo_gtin"] == "gtin_faltante"),
         ["HT40033", "HT40045", "HT40063", "HT40081", "HT40084"])
chequear("Fuente en la hoja Altas", higiene["HT40006"]["fuente"], {"archivo": "HigieneTotal_novedades.xlsx", "hoja": "Altas", "fila": 3})

print("--- 3A · Norte (P08): en inglés, UPC, onzas y dólares ---")
norte = filas_de("P08")
chequear("14 productos", len(norte), 14)
chequear("IN7003: 4.8 fl oz -> 142 ML (Q03)", (norte["IN7003"]["calculado"]["contenido"], norte["IN7003"]["calculado"]["unidad"]),
         (142, "ML"))
chequear("IN7003: UPC de 12 dígitos -> GTIN-13 con un 0 adelante", norte["IN7003"]["calculado"]["gtin"], "0229962606567")
chequear("IN7003: USD 5.17, sin convertir (estándar, sección 6)",
         (norte["IN7003"]["calculado"]["precio_costo"], norte["IN7003"]["calculado"]["moneda"]), (5.17, "USD"))
chequear("IN7009: 8 oz (onza de PESO) -> 227 G", (norte["IN7009"]["calculado"]["contenido"], norte["IN7009"]["calculado"]["unidad"]),
         (227, "G"))
chequear("IN7012: 120 ct -> 120 UN", (norte["IN7012"]["calculado"]["contenido"], norte["IN7012"]["calculado"]["unidad"]), (120, "UN"))
chequear("Los 14 GTIN válidos", sum(1 for f in norte.values() if f["calculado"]["motivo_gtin"]), 0)

print("--- 3B · los proveedores que entran SOLOS (desde las recetas congeladas del commit d52a7cc) ---")
habilitados = servidor_mcp.PROVEEDORES
chequear("P02, P04 y P08 quedan habilitados sin configuración a mano",
         sorted(p for p in habilitados if p not in servidor_mcp.PROVEEDORES_A_MANO), ["P02", "P04", "P08"])
chequear("Los de las semanas 1 a 3 siguen igual (los escritos a mano)",
         all(habilitados[p] is servidor_mcp.PROVEEDORES_A_MANO[p] for p in servidor_mcp.PROVEEDORES_A_MANO), True)
chequear("Bebé Feliz (P06) nunca: está apartado", "P06" in habilitados, False)
chequear("P04: Excel con su receta, sin FDS (no tiene esa carpeta)",
         (habilitados["P04"]["formato"], habilitados["P04"]["receta"]["hoja"], "fds" in habilitados["P04"]), ("excel", "Altas", False))
chequear("P02 y P08: van a buscar sus FDS donde las deja extractor_fds.py",
         (habilitados["P02"]["fds"].name, habilitados["P08"]["fds"].name),
         ("fds_P02_Cosmetica_Rivera.json", "fds_P08_Importadora_Norte.json"))
chequear("P08: la moneda sale de su receta", habilitados["P08"]["moneda"], "USD")

print("--- 3B · chequeo entre etapas: lo incompleto no se procesa ---")
for proveedor_id, cantidad in (("P02", 50), ("P04", 28), ("P08", 14)):
    chequear(f"{proveedor_id}: lectura completa, sin problemas", servidor_mcp.problemas_de_lectura(habilitados[proveedor_id]), [])
    chequear(f"{proveedor_id}: el servidor da sus {cantidad} filas", len(servidor_mcp.leer_filas(proveedor_id, habilitados[proveedor_id])),
             cantidad)
sin_fds = {**habilitados["P02"], "fds": Path(tempfile.mkdtemp()) / "fds_P02_Cosmetica_Rivera.json"}  # como antes de la 3C
chequear("Si faltan sus FDS leídas: problema con el motivo", "primero hay que correr extractor_fds.py" in
         servidor_mcp.problemas_de_lectura(sin_fds)[0], True)
chequear("...y no da ninguna fila (nunca 50 'pendiente_fds' por no haber corrido el extractor)",
         servidor_mcp.leer_filas("P02", sin_fds), [])

print("--- 3C · las FDS de Rivera y Norte (leídas el 11/11 con extractor_fds.py tal cual), cruzadas por código ---")
filas_p02 = {f["item_id"].split(":")[1]: f for f in servidor_mcp.leer_filas("P02", habilitados["P02"])}
filas_p08 = {f["item_id"].split(":")[1]: f for f in servidor_mcp.leer_filas("P08", habilitados["P08"])}
aerosol = ("aerosol_inflamable", "1950")
desaer = ["RIV-1209", "RIV-1248", "RIV-1284", "RIV-1290", "RIV-1296", "RIV-1332", "RIV-1347"]
chequear("Los 7 desodorantes de FDS_Brisa_Frescor_desaer: aerosol inflamable, ONU 1950",
         [(filas_p02[c]["calculado"]["fds"]["peligro_deposito"], filas_p02[c]["calculado"]["fds"]["numero_onu"]) for c in desaer],
         [aerosol] * 7)
chequear("...con la fuente de SU FDS (archivo y página de la sección 14)", filas_p02["RIV-1209"]["calculado"]["fds"]["fuente"],
         {"archivo": "FDS_Brisa_Frescor_desaer.pdf", "pagina": 1})
chequear("Las 3 lacas de FDS_Brisa_laca", [filas_p02[c]["calculado"]["fds"]["fuente"]["archivo"] for c in
                                           ("RIV-1218", "RIV-1266", "RIV-1320")], ["FDS_Brisa_laca.pdf"] * 3)
chequear("RIV-1212 (aerosol) no figura en ninguna FDS -> sin FDS (el agente pondrá pendiente_fds)",
         filas_p02["RIV-1212"]["calculado"]["fds"], None)
chequear("RIV-1293 (barra) tampoco: no lleva FDS", filas_p02["RIV-1293"]["calculado"]["fds"], None)
chequear("Rivera: 10 productos con FDS, ni uno más", sum(1 for f in filas_p02.values() if f["calculado"]["fds"]), 10)
chequear("Norte: IN7015 (gel de afeitar) e IN7003 (shampoo en seco), aerosoles con su FDS",
         [(filas_p08[c]["calculado"]["fds"]["fuente"]["archivo"], filas_p08[c]["calculado"]["fds"]["peligro_deposito"])
          for c in ("IN7015", "IN7003")],
         [("FDS_PureCare_in_afe.pdf", "aerosol_inflamable"), ("FDS_PureCare_in_sec.pdf", "aerosol_inflamable")])
chequear("Norte: solo esos 2 con FDS", sum(1 for f in filas_p08.values() if f["calculado"]["fds"]), 2)
chequear("Higiene Total no tiene FDS: ninguno con ficha", sum(1 for f in servidor_mcp.leer_filas("P04", habilitados["P04"])
                                                             if f["calculado"]["fds"]), 0)

carpeta = Path(tempfile.mkdtemp())
resultado = json.loads((servidor_mcp.CARPETA_RECEPCION / "HigieneTotal_novedades.json").read_text(encoding="utf-8"))
(carpeta / "HigieneTotal_novedades.json").write_text(json.dumps(
    {**resultado, "receta": None, "problemas": ["La moneda coincide con lo que dice el archivo"]}), encoding="utf-8")
recibidos = servidor_mcp.proveedores_recibidos(carpeta)
chequear("Una receta que NO entró: el proveedor figura igual (no desaparece en silencio)", list(recibidos), ["P04"])
chequear("...y el chequeo lo frena con el motivo de la recepción",
         "la receta no entró" in servidor_mcp.problemas_de_lectura(recibidos["P04"])[0], True)
chequear("...y no da filas", servidor_mcp.leer_filas("P04", recibidos["P04"]), [])
chequear("Sin recepciones, nadie entra solo", servidor_mcp.proveedores_recibidos(Path(tempfile.mkdtemp())), {})
shutil.rmtree(carpeta, ignore_errors=True)

print("--- 3B · de punta a punta: la tool leer_archivo_proveedor, como la usa el fichador ---")


async def por_la_tool():
    transporte = PythonStdioTransport(Path(__file__).parent / "servidor_mcp.py", env=ENTORNO_PRUEBAS)
    async with Client(transporte) as cliente:
        p04 = (await cliente.call_tool("leer_archivo_proveedor", {"proveedor_id": "P04", "desde": 0, "cantidad": 3})).data
        p02 = (await cliente.call_tool("leer_archivo_proveedor", {"proveedor_id": "P02", "desde": 0, "cantidad": 25})).data
        p06 = await cliente.call_tool("leer_archivo_proveedor", {"proveedor_id": "P06"}, raise_on_error=False)
        return p04, p02, p06


p04, p02, p06 = asyncio.run(por_la_tool())
chequear("P04 por la tool: 28 en total, de a tandas", (p04["total"], len(p04["filas"]), p04["siguiente"]), (28, 3, 3))
chequear("P04 por la tool: la misma fila que arma el lector (fuente de Excel)", p04["filas"][1]["fuente"],
         {"archivo": "HigieneTotal_novedades.xlsx", "hoja": "Altas", "fila": 3})
chequear("P02 por la tool: 50 en total, y RIV-1218 (la laca, 4ª fila) llega con su FDS",
         (p02["total"], p02["filas"][3]["item_id"], p02["filas"][3]["calculado"]["fds"]["peligro_deposito"]),
         (50, "P02:RIV-1218", "aerosol_inflamable"))
chequear("P06 por la tool: rechazado (no es un proveedor habilitado)", p06.is_error, True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
