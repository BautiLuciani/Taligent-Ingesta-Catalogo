"""Semana 4, paso 1: ¿qué entiende SOLO lector_excel.py de los 3 Excel nuevos? Sin IA, no gasta nada.

Para cada hoja muestra: en qué fila encontró el encabezado, qué columnas, cuántos productos, qué filas ignoró
y dos ejemplos tal cual. Sirve para ver qué falta decidir para que un archivo nuevo entre sin intervención.
Bebé Feliz (P06) NO está: es el proveedor apartado hasta la semana 5.
Correr: python explorar_excel_nuevos.py
"""
from pathlib import Path

import openpyxl

from lector_excel import leer_tabla_excel

CARPETA_PROVEEDORES = Path(__file__).parent / "Data" / "proveedores"
ARCHIVOS = [
    CARPETA_PROVEEDORES / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx",
    CARPETA_PROVEEDORES / "P04_Higiene_Total" / "HigieneTotal_novedades.xlsx",
    CARPETA_PROVEEDORES / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx",
]

for ruta in ARCHIVOS:
    hojas = openpyxl.load_workbook(ruta, read_only=True).sheetnames
    print(f"\n=== {ruta.parent.name} / {ruta.name} — hojas: {hojas}")
    for hoja in hojas:
        tabla = leer_tabla_excel(ruta, hoja)
        print(f"\n  Hoja {hoja!r}: encabezado en la fila {tabla['fila_encabezado']}, {len(tabla['filas'])} productos")
        print(f"    columnas:  {tabla['columnas']}")
        print(f"    ignoradas: {tabla['ignoradas'] or 'ninguna'}")
        print(f"    vigencia:  {tabla['vigencia']}   problemas: {tabla['problemas'] or 'ninguno'}")
        for fila in tabla["filas"][:2]:
            print(f"    ej. fila {fila['fuente']['fila']}: {fila['original']}")