"""Pruebas sin IA de las consultas del asistente (semana 6, paso 2). Correr: python probar_consultas.py

1) Las funciones de consultas.py contra las fichas congeladas del cierre de la semana 5 (referencias_sem6):
   cada respuesta esperada de evaluacion/consultas_esperadas.json tiene que poder salir de estas tools.
2) Contra el servidor real: las 4 tools existen, el asistente ve SOLO esas (no registrar_ficha) y el fichador
   sigue viendo las suyas.
"""
import asyncio
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from referencias import (CARPETA_PEDIDOS_SEM5, CARPETA_REFERENCIAS_SEM6, ENTORNO_PRUEBAS,  # va antes que el servidor
                         RUTA_RESULTADOS_SEM5)
import consultas  # noqa: E402
import servidor_mcp  # noqa: E402
from agente import RUTA_SERVIDOR, obtener_tools  # noqa: E402

RESULTADOS = consultas.cargar_resultados(RUTA_RESULTADOS_SEM5)
FILAS = servidor_mcp.FILAS_POR_ITEM
CATALOGO = servidor_mcp.CATALOGO_POR_SKU
NO_ENTRARON = servidor_mcp.NO_ENTRARON

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def ficha(codigo):
    return consultas.ver_ficha(codigo, RESULTADOS, FILAS, CATALOGO, NO_ENTRARON)


def buscar(**filtros):
    return consultas.buscar_fichas(RESULTADOS, **filtros)


def ids(respuesta):
    return [item["item_id"] for item in respuesta["items"]]


print("== resolver el código")
chequear("con proveedor", consultas.resolver_codigo("P01:AN-1124", RESULTADOS), "P01:AN-1124")
chequear("sin proveedor", consultas.resolver_codigo("AN-1124", RESULTADOS), "P01:AN-1124")
chequear("en minúscula y con espacios", consultas.resolver_codigo("  an-1124 ", RESULTADOS), "P01:AN-1124")
chequear("un código que no existe", consultas.resolver_codigo("AN-9999", RESULTADOS), None)
chequear("un pedazo de código no alcanza (AN-112 no es AN-1124)", consultas.resolver_codigo("AN-112", RESULTADOS), None)
chequear("repetido en dos proveedores -> no se elige",
         consultas.resolver_codigo("X-1", ["P01:X-1", "P02:X-1"]), None)

print("== ver_ficha")
q01 = ficha("AN-1124")
chequear("Q01 precio de AN-1124", q01["ficha"]["precio_costo"], 320.8)
chequear("Q01 fuente: el Excel de actualización, fila 12", q01["fuentes"]["precio_costo"],
         {"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12})
chequear("Q01 la fila original es la del PDF", q01["archivo_original"]["fuente"],
         {"archivo": "Lista_de_precios_octubre_2026.pdf", "pagina": 1})
chequear("Q01 vigencia del precio", q01["vigencia_precio"], "2026-10-15")
chequear("Q02 EAN de DL-109 desde la lista", (ficha("DL-109")["ficha"]["gtin"], ficha("DL-109")["fuentes"]["gtin"]["archivo"]),
         ("7790670659075", "Dermalab_lista_precios.xlsx"))
q03 = ficha("IN7003")
chequear("Q03 IN7003: 142 ML y el archivo decía 4.8 fl oz",
         (q03["ficha"]["contenido"], q03["ficha"]["unidad"], q03["archivo_original"]["original"]["Size"]), (142, "ML", "4.8 fl oz"))
chequear("Q05 LHS-206: FDS de la lavandina", (ficha("LHS-206")["ficha"]["peligro_deposito"], ficha("LHS-206")["fds"]["fuente"]),
         ("corrosivo", {"archivo": "FDS_Clarita_lavandina.pdf", "pagina": 1}))
q07 = ficha("LT-3447")
chequear("Q07 LT-3447: motivos y SKU candidato con su descripción",
         (q07["motivos_revision"], q07["producto_del_catalogo"]["sku"], q07["producto_del_catalogo"]["descripcion"]),
         (["gtin_faltante", "posible_duplicado"], "SKU100889", "JABON PUREZA ANTIBAC. 90GRS"))
q08 = ficha("AN-1133")
chequear("Q08 AN-1133: conflicto de contenido con sus dos versiones",
         [(v["valor"], v["fuente"]) for v in q08["conflictos"][0]["versiones"]],
         [("20 G", {"archivo": "Lista_de_precios_octubre_2026.pdf", "pagina": 1}),
          ("30 G", {"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 6})])
q09 = ficha("RIV-1203")
chequear("Q09 RIV-1203: GTIN inválido y el EAN que mandó",
         (q09["motivo_gtin"], q09["ficha"]["gtin"], q09["archivo_original"]["original"]["EAN"]),
         ("gtin_invalido", None, "7793092189062"))
chequear("Q10 RIV-1206: duplicado de SKU100714", (ficha("RIV-1206")["estado"], ficha("RIV-1206")["duplicado_de"]),
         ("duplicado", "SKU100714"))
q11 = ficha("HT32855")
chequear("Q11 HT32855: no tiene ficha, no entró", (q11["encontrado"], "no_entro" in q11), (False, True))
chequear("Q11 su fuente: hoja Discontinuados, fila 2", q11["no_entro"]["fuente"],
         {"archivo": "HigieneTotal_novedades.xlsx", "hoja": "Discontinuados", "fila": 2})
chequear("Q11 el motivo dice discontinuado", "discontinuad" in q11["explicacion"].lower(), True)
q12 = ficha("NV-203")
chequear("Q12 NV-203: sin EAN y lo que decía el mail",
         (q12["motivos_revision"], q12["archivo_original"]["original"]["ean"], q12["archivo_original"]["fuente"]["linea"]),
         (["gtin_faltante"], "se lo paso la semana que viene", 10))
chequear("Q13 AN-1103: falta el principio activo",
         (ficha("AN-1103")["motivos_revision"], ficha("AN-1103")["ficha"]["principio_activo"],
          ficha("AN-1103")["archivo_original"]["original"]["monodroga"]), (["dato_obligatorio_faltante"], None, None))
inexistente = ficha("XX-999")
chequear("un código que no está en nada", (inexistente["encontrado"], "no_entro" in inexistente), (False, False))

print("== buscar_fichas")
chequear("Q14 corrosivos de LHS", sorted(ids(buscar(proveedor_id="P07", peligro_deposito="corrosivo"))),
         ["P07:LHS-206", "P07:LHS-218", "P07:LHS-263", "P07:LHS-269"])
chequear("Q15 pendientes de FDS", sorted(ids(buscar(peligro_deposito="pendiente_fds"))),
         ["P02:RIV-1212", "P07:LHS-221", "P07:LHS-248", "P07:LHS-266"])
chequear("Q16 Dermalab a revisión", sorted(ids(buscar(proveedor_id="P05", estado="a_revision"))),
         ["P05:DL-103", "P05:DL-106", "P05:DL-151", "P05:DL-154"])
chequear("Q17 packs de Bebé Feliz", sorted(ids(buscar(proveedor_id="P06", en_pack=True))),
         ["P06:BF-509", "P06:BF-521", "P06:BF-548"])
q17 = buscar(proveedor_id="P06", en_pack=True)
chequear("Q17 cada ítem trae la fuente de sus unidades por envase",
         q17["items"][0]["fuentes"]["unidades_por_envase"]["archivo"], "BebeFeliz_altas.xlsx")
q18 = buscar(estado="lista_para_alta", cantidad=10)
chequear("Q18 listos para alta: el total, aunque la página traiga 10", (q18["total"], len(q18["items"]), q18["siguiente"]),
         (209, 10, 10))
chequear("Q18 conteo por estado de todo", buscar()["conteo_por_estado"],
         {"lista_para_alta": 209, "duplicado": 24, "a_revision": 24})
v01 = buscar(proveedor_id="P08", moneda="USD", ordenar_por="precio_costo_desc")
chequear("V01 los 14 de Norte en dólares", v01["total"], 14)
chequear("V01 el más caro primero: IN7012, USD 10,66",
         (v01["items"][0]["item_id"], v01["items"][0]["precio_costo"], v01["items"][0]["fuentes"]["precio_costo"]),
         ("P08:IN7012", 10.66, {"archivo": "NorteImports_new_items_Q4.xlsx", "hoja": "New items", "fila": 5}))
chequear("V02 Andes a revisión", sorted(ids(buscar(proveedor_id="P01", estado="a_revision"))),
         ["P01:AN-1103", "P01:AN-1106", "P01:AN-1133", "P01:AN-1136"])
chequear("V02 de esos, por conflicto entre archivos",
         sorted(ids(buscar(proveedor_id="P01", motivo="conflicto_entre_fuentes"))), ["P01:AN-1133", "P01:AN-1136"])
chequear("texto sin acentos ni mayúsculas ('pañal' encuentra PAÑALES)",
         buscar(texto="panal")["total"] == buscar(texto="PAÑAL")["total"] > 0, True)
mas_barato = buscar(proveedor_id="P05", ordenar_por="precio_costo_asc", cantidad=50)
chequear("orden ascendente: los sin precio van al final, no como 'los más baratos'",
         all(item["precio_costo"] is None for item in mas_barato["items"][-4:]) and mas_barato["items"][0]["precio_costo"] is not None, True)
chequear("cantidad de más se recorta a 50", len(buscar(cantidad=999)["items"]), 50)

print("== pedido al proveedor")
p05 = consultas.pedido_del_proveedor("P05", CARPETA_PEDIDOS_SEM5)
chequear("Q16 el pedido a Dermalab pide confirmar los dos SKU",
         (p05["hay_pedido"], "SKU100910" in p05["mensaje"], "SKU101785" in p05["mensaje"]), (True, True, True))
with tempfile.TemporaryDirectory() as vacia:
    chequear("sin pedido armado -> hay_pedido false", consultas.pedido_del_proveedor("P08", Path(vacia))["hay_pedido"], False)

print("== fuentes conocidas (para verificar lo que cite el asistente)")
conocidas = consultas.fuentes_conocidas(RESULTADOS, FILAS, NO_ENTRARON)
chequear("conoce la fila 12 del Excel de Andes (con la fila como texto también)",
         consultas.clave_fuente({"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": "12"}) in conocidas, True)
chequear("conoce la versión del Excel de un conflicto (fila 6)",
         consultas.clave_fuente({"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 6}) in conocidas, True)
chequear("conoce la hoja Discontinuados, fila 2",
         consultas.clave_fuente({"archivo": "HigieneTotal_novedades.xlsx", "hoja": "Discontinuados", "fila": 2}) in conocidas, True)
chequear("conoce la línea 27 del mail? no (ningún dato sale de la PD)",
         consultas.clave_fuente({"archivo": "Mail_NaturalVida_altas.txt", "linea": 27}) in conocidas, False)
chequear("una página inventada no está",
         consultas.clave_fuente({"archivo": "Lista_de_precios_octubre_2026.pdf", "pagina": 7}) in conocidas, False)


print("== contra el servidor real: tools y permisos")


async def con_el_servidor():
    entorno = {**ENTORNO_PRUEBAS, "INGESTA_CARPETA_SALIDA": str(CARPETA_REFERENCIAS_SEM6)}
    async with Client(PythonStdioTransport(str(RUTA_SERVIDOR), env=entorno)) as cliente:
        del_asistente = sorted(t["name"] for t in await obtener_tools(cliente, "asistente"))
        chequear("el asistente ve SOLO sus 4 tools", del_asistente,
                 ["buscar_fichas", "ver_ficha", "ver_lo_que_no_entro", "ver_pedido_al_proveedor"])
        del_fichador = sorted(t["name"] for t in await obtener_tools(cliente, "fichador"))
        chequear("el fichador sigue viendo las suyas (y ninguna del asistente)", del_fichador,
                 ["buscar_parecidos", "buscar_por_gtin", "leer_archivo_proveedor", "registrar_ficha"])
        respuesta = await cliente.call_tool("ver_ficha", {"codigo": "AN-1124"})
        chequear("ver_ficha por el servidor (lee los resultados congelados)",
                 respuesta.structured_content["ficha"]["precio_costo"], 320.8)
        respuesta = await cliente.call_tool("buscar_fichas", {"estado": "lista_para_alta", "cantidad": 1})
        chequear("buscar_fichas por el servidor", respuesta.structured_content["total"], 209)
        respuesta = await cliente.call_tool("ver_lo_que_no_entro", {"proveedor_id": "P04"})
        chequear("ver_lo_que_no_entro: los 8 discontinuados de Higiene Total", respuesta.structured_content["total"], 8)
        respuesta = await cliente.call_tool("ver_pedido_al_proveedor", {"proveedor_id": "P05"})
        chequear("ver_pedido_al_proveedor por el servidor", respuesta.structured_content["hay_pedido"], True)
        respuesta = await cliente.call_tool("buscar_fichas", {"estado": "aprobado"}, raise_on_error=False)
        chequear("un estado fuera del vocabulario lo rechaza el schema (enum)", respuesta.is_error, True)


asyncio.run(con_el_servidor())

print()
print("Resultado: todo OK" if errores == 0 else f"Resultado: {errores} con error")
