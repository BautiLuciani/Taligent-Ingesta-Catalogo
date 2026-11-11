"""Pruebas del acuse de recibo (semana 4, paso 9C) sin IA. Correr: python probar_acuse.py

Usan los 3 Excel reales de Data/ (de solo lectura) y las recepciones congeladas en
salida/experimentos/referencias_sem4/recepcion/: no dependen de la última corrida. Los resultados, los hooks y los
pedidos son chicos y armados acá, para probar cada caso (duplicado, revisión, inestable, otra corrida).
"""
import json
import shutil
import tempfile
from pathlib import Path

from acuse import (armar_acuse, ejemplo_de_contenido, el_pedido, el_resultado, guardar_acuse, lo_que_entendio,
                   resultado_de_recepcion)
from lector_excel import leer_tabla_excel

CARPETA = Path(__file__).parent
DATA = CARPETA / "Data" / "proveedores"
RECEPCION_CONGELADA = CARPETA / "salida" / "experimentos" / "referencias_sem4" / "recepcion"
RIVERA = DATA / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx"
HIGIENE = DATA / "P04_Higiene_Total" / "HigieneTotal_novedades.xlsx"
NORTE = DATA / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def entendio(ruta, proveedor_id):
    return "\n".join(lo_que_entendio(ruta, proveedor_id, resultado_de_recepcion(ruta, proveedor_id, RECEPCION_CONGELADA)))


print("--- 9A-1 · qué entendió el sistema (con los 3 Excel reales) ---")
texto = entendio(RIVERA, "P02")
chequear("Rivera: la hoja Altas, la única", '"Altas" (es la única del archivo)' in texto, True)
chequear("Rivera: el código con su ejemplo real", "`COD. RIV` → código del proveedor · ej. RIV-1203" in texto, True)
chequear("Rivera: OBS no va, con su motivo", "`OBS` → **NO VA**" in texto, True)
chequear("Rivera: decimal con coma, con la evidencia que encontró el código", 'coma** (se ve en "TRAT. CAP. ALBORADA NUTRICION 0,5 KG")' in texto, True)
chequear("Rivera: UYU porque no menciona dólares (estándar §6)", "UYU — el archivo no menciona dólares" in texto, True)
chequear("Rivera: las filas de sección no desaparecen en silencio",
         'fila 6 "== CAPILAR ==", fila 48 "== DESODORANTES =="' in texto, True)
texto = entendio(HIGIENE, "P04")
chequear("Higiene Total (Q11): Discontinuados NO ENTRA, con el motivo", '"Discontinuados": **NO ENTRA**' in texto, True)
chequear("Higiene Total: la columna del código no aparece como 'no va' (es el código)",
         ("`Item` → código del proveedor" in texto, "`Item` → **NO VA**" in texto), (True, False))
chequear("Higiene Total: cantidad y unidad separadas, con un ejemplo convertido", '"300 cc" → 300 ML' in texto, True)
texto = entendio(NORTE, "P08")
chequear("Norte (Q03): 4.8 fl oz → 142 ML", 'fila 2: "4.8 fl oz" → 142 ML' in texto, True)
chequear("Norte (V01): USD, y dónde lo dice el archivo", 'USD — lo dice el archivo: "Unit cost (USD)"' in texto, True)
chequear("Norte: Origin no va", "`Origin` → **NO VA**" in texto, True)
chequear("Norte: no inventa filas ignoradas", "no son productos" in texto, False)

print("--- 9A-1 · el ejemplo de contenido es el primero donde el código convirtió algo ---")
receta = resultado_de_recepcion(RIVERA, "P02", RECEPCION_CONGELADA)["receta"]
filas = leer_tabla_excel(RIVERA, "Altas")["filas"]
chequear("Rivera: saltea 'X 200 ML' (no hubo que convertir) y toma '400 CC' → 400 ML",
         ejemplo_de_contenido(filas, receta)[1:], (8, 400, "ML"))
chequear("Si ninguno necesitó conversión, el primero", ejemplo_de_contenido(filas[:1], receta)[1:], (7, 200, "ML"))


def ficha(item, estado, motivos=(), duplicado_de=None, inestable=None):
    r = {"item_id": item, "estado": estado, "motivos_revision": list(motivos), "duplicado_de": duplicado_de,
         "ficha": {"descripcion": f"PRODUCTO {item}"}}
    if inestable:
        r["inestable"] = inestable
    return r


RESULTADOS = {r["item_id"]: r for r in [
    ficha("P02:RIV-1", "lista_para_alta"), ficha("P02:RIV-2", "lista_para_alta"),
    ficha("P02:RIV-3", "duplicado", duplicado_de="SKU100714"),
    ficha("P02:RIV-4", "a_revision", ["gtin_faltante", "posible_duplicado"], "SKU101806"),
    ficha("P02:RIV-5", "lista_para_alta", inestable={"campos": ["ficha.descripcion", "ficha.variante"]}),
    ficha("P04:HT-1", "a_revision", ["gtin_invalido"]),
]}

print("--- 9A-2 · el resultado sale de resultados.json, solo del proveedor ---")
texto = "\n".join(el_resultado("P02", RESULTADOS, {}))
chequear("Cuenta los 5 de P02 por estado (no el de P04)", "**5 productos:** 3 listos para alta · 1 duplicados · 1 a revisión." in texto, True)
chequear("El duplicado, con el SKU que ya existe", "RIV-3 ya existe en el catálogo: **SKU100714**" in texto, True)
chequear("La revisión, con los motivos en castellano y el candidato",
         "RIV-4 a revisión: sin código de barras, posible duplicado (candidato: SKU101806)." in texto, True)
chequear("La inestable, con los campos que no coinciden", "RIV-5: no coinciden en descripcion, variante." in texto, True)
chequear("Sin hooks de esta corrida: no dice nada de frenos (no mezcla corridas)", "Frenos" in texto, False)
hooks = {"fecha": "2026-11-11 18:20", "proveedores": ["P02"], "frenos": [
    {"hook": "al_terminar", "item_id": "P02:RIV-1", "motivo": "campos sin fuente", "corregido": True},
    {"hook": "al_terminar", "item_id": "P04:HT-1", "motivo": "x", "corregido": False}]}
chequear("Con hooks de una corrida donde estuvo: sus frenos (no los de otro proveedor)",
         "Frenos de los hooks** (corrida del 2026-11-11 18:20): 1, 1 corregido(s) por el modelo." in "\n".join(el_resultado("P02", RESULTADOS, hooks)), True)
chequear("Un proveedor sin fichas lo dice", el_resultado("P08", RESULTADOS, {}), ["- No hay fichas escritas de este proveedor."])

print("--- 9A-2 · el pedido es el que ya armó pedido_proveedor.py ---")
temporal = Path(tempfile.mkdtemp())
chequear("Sin archivo de pedido: nada que pedir", el_pedido("P08", temporal)[0].startswith("- Nada que pedir"), True)
(temporal / "pedido_P02.md").write_text(
    "Asunto: Datos pendientes\n\nRIV-4 · SHAMPOO X (ALTAS RIVERA OCT.xlsx, hoja Altas, fila 9)\n"
    "  - El código de barras (EAN-13).\n  - ¿Es el mismo producto que SKU101806?\n", encoding="utf-8")
pedido = el_pedido("P02", temporal)
chequear("Con pedido: un renglón por dato, con su producto",
         pedido[:2], ["- RIV-4: El código de barras (EAN-13).", "- RIV-4: ¿Es el mismo producto que SKU101806?"])

print("--- 9A-3 · el acuse entero, según cómo terminó ---")
registro = {"estado": "procesado", "proveedor_id": "P02", "fecha": "2026-11-11 16:37:35", "costo_recepcion_y_fds_usd": 0.002}
texto = armar_acuse(RIVERA, registro, RESULTADOS, {}, RECEPCION_CONGELADA, temporal)
chequear("Procesado: encabezado con el nombre del proveedor y el estado",
         "Recibido 2026-11-11 16:37:35 · Cosmética Rivera S.A. (P02) · **PROCESADO ✅**" in texto, True)
chequear("...con las 3 secciones, en orden",
         [texto.index(s) for s in ("## Qué entendió", "## Resultado", "## Pedido")] == sorted(texto.index(s) for s in ("## Qué entendió", "## Resultado", "## Pedido")), True)
chequear("...el costo y que no usa IA", ("US$ 0.0020" in texto, "no usa IA" in texto), (True, True))
texto = armar_acuse(CARPETA / "entrada" / "Varios" / "lista.xlsx",
                    {"estado": "rechazado", "proveedor_id": None, "fecha": "x",
                     "motivo": "la carpeta 'Varios' no es de ningún proveedor de proveedores.csv"}, RESULTADOS, {})
chequear("Rechazado: proveedor desconocido, el motivo, y ninguna sección de resultado",
         ("proveedor desconocido" in texto, "**RECHAZADO ⛔**" in texto, "no es de ningún proveedor" in texto, "## Resultado" in texto),
         (True, True, True, False))
chequear("...y aclara que no se cargó nada", "No se cargó ninguna ficha de este archivo" in texto, True)
no_entro = Path(tempfile.mkdtemp())
(no_entro / "P08_NorteImports_new_items_Q4.json").write_text(json.dumps({
    "receta": None, "avisos": [], "problemas": ["La columna de precio no tiene números"],
    "controles": [{"control": "El formulario vino completo", "ok": True, "detalle": ""},
                  {"control": "La columna del precio tiene precios", "ok": False, "detalle": "0 de 14 filas"}]}), encoding="utf-8")
texto = armar_acuse(NORTE, {"estado": "no_entro", "proveedor_id": "P08", "fecha": "x", "motivo": "la receta no entró en la recepción",
                            "problemas": ["La columna de precio no tiene números"]}, RESULTADOS, {}, no_entro, temporal)
chequear("No entró: muestra el control del código que falló (y no los que pasaron)",
         ("✘ Control del código: La columna del precio tiene precios (0 de 14 filas)" in texto, "El formulario vino completo" in texto),
         (True, False))
chequear("...sin una receta, no inventa qué entendió", "## Qué había entendido" in texto, False)

print("--- 9A-3 · dónde se guarda ---")
acuses = Path(tempfile.mkdtemp())
chequear("Uno por archivo: <proveedor>_<archivo>.md", guardar_acuse(RIVERA, registro, "x", acuses).name, "P02_ALTAS RIVERA OCT.md")
chequear("Sin proveedor: SIN_PROVEEDOR_<archivo>.md", guardar_acuse(Path("lista.xlsx"), {"proveedor_id": None}, "x", acuses).name,
         "SIN_PROVEEDOR_lista.md")
for carpeta in (temporal, no_entro, acuses):
    shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
