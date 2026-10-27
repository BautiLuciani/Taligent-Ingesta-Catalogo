"""Pruebas de lector_excel.py con los Excel REALES del proyecto y casos armados. Correr: python probar_lector_excel.py"""
import shutil
import tempfile
from pathlib import Path

import openpyxl

from lector_excel import es_codigo, leer_tabla_excel

PROVEEDORES = Path(__file__).parent / "Data" / "proveedores"
ANDES = PROVEEDORES / "P01_Laboratorio_Andes" / "Actualizacion_precios_Andes.xlsx"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


print("--- es_codigo ---")
chequear("Código de Andes", es_codigo("AN-1124"), True)
chequear("Código con espacios alrededor", es_codigo(" HT40003 "), True)
chequear("Título de sección de Rivera", es_codigo("== CAPILAR =="), False)
chequear("Encabezado", es_codigo("Código"), False)
chequear("Un EAN como número", es_codigo(7790670659075), False)
chequear("Celda vacía", es_codigo(None), False)

print("--- Andes (el Excel de la actualización de precios) ---")
andes = leer_tabla_excel(ANDES)
chequear("Hoja y encabezado en la fila 4", (andes["hoja"], andes["fila_encabezado"]), ("Actualización", 4))
chequear("Columnas", andes["columnas"], ["Código", "Producto", "Presentación", "Precio nuevo"])
chequear("12 productos, sin problemas ni ignoradas", (len(andes["filas"]), andes["problemas"], andes["ignoradas"]),
         (12, [], []))
por_codigo = {fila["codigo"]: fila for fila in andes["filas"]}
chequear("AN-1124: fila 12 y precio 320.8 tal cual (Q01)", (por_codigo["AN-1124"]["fuente"],
         por_codigo["AN-1124"]["original"]["Precio nuevo"]),
         ({"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 12}, 320.8))
chequear("AN-1136: 'Comprimidos x 30' (el conflicto con el PDF)", por_codigo["AN-1136"]["original"]["Presentación"],
         "Comprimidos x 30")
chequear("Vigencia: 15/10/2026 desde la fila 2", andes["vigencia"], {
    "fecha": "2026-10-15", "texto": "Vigencia desde: 15/10/2026",
    "fuente": {"archivo": "Actualizacion_precios_Andes.xlsx", "hoja": "Actualización", "fila": 2}})

print("--- los otros Excel del proyecto (la misma regla para todos) ---")
dermalab = leer_tabla_excel(PROVEEDORES / "P05_Dermalab" / "Dermalab_lista_precios.xlsx")
chequear("Dermalab: encabezado fila 1, 14 productos, sin vigencia", (dermalab["fila_encabezado"], len(dermalab["filas"]),
         dermalab["vigencia"]), (1, 14, None))
chequear("Dermalab: el EAN queda número, tal cual", dermalab["filas"][0]["original"]["EAN"], 7790670659075)
rivera = leer_tabla_excel(PROVEEDORES / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx")
chequear("Rivera: encabezado fila 5 ('COD. RIV'), 50 productos", (rivera["fila_encabezado"], len(rivera["filas"])), (5, 50))
chequear("Rivera: los títulos '== ... ==' (fórmulas sin valor) se ven en ignoradas", rivera["ignoradas"],
         [{"fila": 6, "texto": "== CAPILAR =="}, {"fila": 48, "texto": "== DESODORANTES =="}])
discontinuados = leer_tabla_excel(PROVEEDORES / "P04_Higiene_Total" / "HigieneTotal_novedades.xlsx", hoja="Discontinuados")
chequear("Higiene Total: se puede pedir otra hoja (Discontinuados, 8)", (discontinuados["hoja"], len(discontinuados["filas"])),
         ("Discontinuados", 8))
norte = leer_tabla_excel(PROVEEDORES / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx")
chequear("Norte: en inglés ('Item #'), 14 productos", (norte["columnas"][0], len(norte["filas"])), ("Item #", 14))

print("--- casos armados ---")
carpeta = Path(tempfile.mkdtemp())


def armar(nombre, filas):
    """Un Excel de mentira con esas filas, para probar casos que los archivos reales no traen."""
    libro = openpyxl.Workbook()
    for fila in filas:
        libro.active.append(fila)
    ruta = carpeta / nombre
    libro.save(ruta)
    return ruta


r = leer_tabla_excel(armar("sin_codigos.xlsx", [["Código", "Precio"], ["nada", 1]]))
chequear("Sin ninguna fila con código: problema", (r["filas"], len(r["problemas"])), ([], 1))
r = leer_tabla_excel(armar("repetido.xlsx", [["Código", "Precio"], ["AN-1101", 10], ["AN-1101", 20], ["AN-1102", 5]]))
chequear("Código repetido con datos distintos: no se elige", ([f["codigo"] for f in r["filas"]], len(r["problemas"])),
         (["AN-1102"], 1))
r = leer_tabla_excel(armar("repetido_igual.xlsx", [["Código", "Precio"], ["AN-1101", 10], ["AN-1101", 10]]))
chequear("Repetido idéntico: queda una vez, sin problema", (len(r["filas"]), r["problemas"]), (1, []))
r = leer_tabla_excel(armar("dos_vigencias.xlsx", [["Vigencia desde: 01/10/2026"], ["Vigencia desde: 15/10/2026"], [],
                                                  ["Código", "Precio"], ["AN-1101", 10]]))
chequear("Dos vigencias distintas: None + problema", (r["vigencia"], len(r["problemas"])), (None, 1))
r = leer_tabla_excel(armar("celda_vacia.xlsx", [["Código", "EAN", "Precio"], ["HT40084", None, 94.34]]))
chequear("Celda vacía: queda None (no se inventa)", r["filas"][0]["original"], {"EAN": None, "Precio": 94.34})
shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")