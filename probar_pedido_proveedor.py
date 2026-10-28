"""Pruebas de pedido_proveedor.py con los resultados REALES del paso 8. Correr: python probar_pedido_proveedor.py"""
import copy
import json
from pathlib import Path

import servidor_mcp
from pedido_proveedor import armar_mensaje, fuente_texto, pendientes_del_item

RESULTADOS = json.loads((Path(__file__).parent / "salida" / "resultados.json").read_text(encoding="utf-8"))
CATALOGO_POR_SKU = {producto["sku"]: producto for producto in servidor_mcp.CATALOGO}
FILAS = {fila["item_id"]: fila for proveedor_id, config in servidor_mcp.PROVEEDORES.items()
         for fila in servidor_mcp.leer_filas(proveedor_id, config)}

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def pendientes(item_id):
    return pendientes_del_item(RESULTADOS[item_id], FILAS[item_id], CATALOGO_POR_SKU)


EAN = "El código de barras (EAN-13)."
PRECIO = "El precio de costo (de lista, sin IVA)."
FDS = "La ficha de datos de seguridad (FDS)."

print("--- fuente_texto ---")
chequear("PDF", fuente_texto({"archivo": "a.pdf", "pagina": 1}), "a.pdf, pág. 1")
chequear("CSV", fuente_texto({"archivo": "a.csv", "linea": 5}), "a.csv, línea 5")
chequear("Excel", fuente_texto({"archivo": "a.xlsx", "hoja": "Lista", "fila": 2}), "a.xlsx, hoja Lista, fila 2")

print("\n--- Dermalab (Q16) ---")
chequear("DL-151: EAN, precio y confirmar el duplicado (con nuestra descripción y el SKU)", pendientes("P05:DL-151"), ([
    EAN, PRECIO,
    "¿Es el mismo producto que ya tenemos cargado como \"CREMA DERMALAB HYDRA PLUS 50CC\" (SKU100910)?"], []))
chequear("DL-103: EAN y precio (Q19: con el EAN solo, sigue faltando el precio)", pendientes("P05:DL-103"), ([EAN, PRECIO], []))
chequear("DL-106: EAN y precio, sin duplicado (el agente rechazó el candidato)", pendientes("P05:DL-106"), ([EAN, PRECIO], []))
chequear("DL-154: EAN, precio y confirmar el agua micelar del catálogo", pendientes("P05:DL-154")[0][2],
         "¿Es el mismo producto que ya tenemos cargado como \"AGUA MICELAR DERMALAB SENSITIVE 400ML\" (SKU101785)?")
chequear("DL-109 (lista para alta): nada que pedir", pendientes("P05:DL-109"), ([], []))
chequear("Dermalab no es lista de medicamentos: no se le pide monodroga", any("monodroga" in p for p in pendientes("P05:DL-151")[0]), False)

print("\n--- Andes ---")
chequear("AN-1103: la monodroga (no la categoría: esa la decidimos nosotros)", pendientes("P01:AN-1103"),
         (["La monodroga (principio activo)."], []))
chequear("AN-1136: el conflicto, con las dos versiones y sus fuentes", pendientes("P01:AN-1136"), ([
    "El contenido no coincide entre sus archivos: \"20 UN\" (Lista_de_precios_octubre_2026.pdf, pág. 1) y "
    "\"30 UN\" (Actualizacion_precios_Andes.xlsx, hoja Actualización, fila 5). ¿Cuál es el correcto?"], []))
chequear("AN-1136: el contenido en conflicto NO se pide además como faltante", len(pendientes("P01:AN-1136")[0]), 1)

print("\n--- LHS y Litoral ---")
chequear("LHS-221 (duplicado sin FDS): se pide la FDS igual", pendientes("P07:LHS-221"), ([FDS], []))
chequear("LHS-275: EAN y confirmar el duplicado; tiene FDS, no se pide", pendientes("P07:LHS-275")[0][0], EAN)
chequear("LHS-275: no se pide la FDS (la tiene)", FDS in pendientes("P07:LHS-275")[0], False)
chequear("LT-3450: EAN y confirmar los hisopos del catálogo", len(pendientes("P03:LT-3450")[0]), 2)

print("\n--- todos los productos: nada queda sin pedido ---")
sin_pedido = {i: pendientes(i)[1] for i in RESULTADOS if i in FILAS and pendientes(i)[1]}
chequear("Ningún motivo de revisión queda sin traducirse en un pedido", sin_pedido, {})
a_revision = [i for i, r in RESULTADOS.items() if r["estado"] == "a_revision" and i in FILAS]
chequear("Todo producto a revisión tiene algo que pedir", [i for i in a_revision if not pendientes(i)[0]], [])

print("\n--- casos armados ---")
resultado = copy.deepcopy(RESULTADOS["P01:AN-1103"])
resultado["ficha"]["principio_activo"] = "IBUPROFENO"  # el faltante es algo que decidimos nosotros, no el proveedor
chequear("Un dato faltante que no se le pide al proveedor: queda avisado, no desaparece",
         pendientes_del_item(resultado, FILAS["P01:AN-1103"], CATALOGO_POR_SKU), ([], ["dato_obligatorio_faltante"]))
resultado = copy.deepcopy(RESULTADOS["P05:DL-151"])
resultado["duplicado_de"] = "SKU999999"
chequear("Un SKU que no está en el catálogo: no se inventa la pregunta",
         pendientes_del_item(resultado, FILAS["P05:DL-151"], CATALOGO_POR_SKU), ([EAN, PRECIO], ["posible_duplicado"]))

print("\n--- armar_mensaje ---")
mensaje = armar_mensaje("Dermalab S.A.", [{"codigo": "DL-103", "descripcion": "GEL LIMPIADOR DERMALAB PURIFY X 300 ML",
                                           "fuente": {"archivo": "f.pdf", "pagina": 1}, "pedidos": [EAN, PRECIO]}])
chequear("El asunto nombra al proveedor", mensaje.splitlines()[0], "Asunto: Datos pendientes para el alta de productos — Dermalab S.A.")
chequear("Cada producto con su código, descripción y de dónde sale", "DL-103 · GEL LIMPIADOR DERMALAB PURIFY X 300 ML (f.pdf, pág. 1)" in mensaje, True)
chequear("Cada pedido en su renglón", "  - El precio de costo (de lista, sin IVA)." in mensaje, True)
chequear("Sin nada que pedir no hay mensaje", armar_mensaje("X", []), "")

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")