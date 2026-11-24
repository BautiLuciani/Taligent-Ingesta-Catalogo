"""Pruebas sin IA de presentacion.py (semana 7, paso 1): cómo se muestra cada ficha en la pantalla de Fichas y el Excel.

Sobre las 257 fichas CONGELADAS del cierre de la semana 5 (referencias_sem6/). Los valores esperados salen de los
archivos de los proveedores y del estándar, no de copiar lo que devuelve la función.
"""
import io
import json

import openpyxl

import referencias
import presentacion as p

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


resultados = json.loads(referencias.RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8"))
fichas = p.fichas_para_pantalla(resultados)
por_id = {f["id"]: f for f in fichas}


def campo(item_id, etiqueta):
    for grupo in por_id[item_id]["grupos"]:
        for c in grupo["campos"]:
            if c["etiqueta"] == etiqueta:
                return c
    return None


# --- Formatos ---
probar("precio: UYU 88,04", p.formato_precio(88.04, "UYU") == "UYU 88,04")
probar("precio con miles: UYU 1.101,14", p.formato_precio(1101.14, "UYU") == "UYU 1.101,14")
probar("precio en dólares: USD 5,17", p.formato_precio(5.17, "USD") == "USD 5,17")
probar("sin precio: None", p.formato_precio(None, "UYU") is None)
probar("contenido: 2000 ML", p.formato_contenido({"contenido": 2000, "unidad": "ML", "unidades_por_envase": 1}) == "2000 ML")
probar("contenido de un pack: 60 UN, pack de 2",
       p.formato_contenido({"contenido": 60, "unidad": "UN", "unidades_por_envase": 2}) == "60 UN, pack de 2")
probar("sin contenido: None", p.formato_contenido({"contenido": None, "unidad": None}) is None)
probar("ubicación: página, línea y fila", (p.ubicacion({"pagina": 1}), p.ubicacion({"linea": 46}), p.ubicacion({"hoja": "H", "fila": 8}))
       == ("pág. 1", "línea 46", "fila 8"))
fuente = p.fuente_para_pantalla({"archivo": "ALTAS RIVERA OCT.xlsx", "hoja": "Altas", "fila": 8})
probar("fuente de Excel: tipo Excel, nombre real, fila y la hoja en el detalle",
       fuente["tipo"] == "Excel" and fuente["archivo"] == "ALTAS RIVERA OCT.xlsx" and fuente["ubicacion"] == "fila 8"
       and fuente["detalle"] == "ALTAS RIVERA OCT.xlsx, hoja Altas, fila 8")
probar("fuente del mail: tipo Mail", p.fuente_para_pantalla({"archivo": "Mail_NaturalVida_altas.txt", "linea": 4})["tipo"] == "Mail")
probar("sin fuente: None", p.fuente_para_pantalla(None) is None)
probar("buscar sin acentos ni mayúsculas", p.sin_acentos("Jabón pañal") == "JABON PANAL")

# --- Las 257 fichas ---
probar("257 fichas", len(fichas) == 257)
probar("todas con nombre, proveedor y estado en palabras",
       all(f["nombre"] and f["proveedor"] and f["estado_texto"] for f in fichas))
probar("ninguna ficha cambia: el nombre es la descripción tal cual (en mayúsculas)",
       all(f["nombre"] == resultados[f["id"]]["ficha"]["descripcion"] for f in fichas))
probar("todo dato con valor tiene su fuente, y todo vacío dice «Sin dato» sin fuente (o «No corresponde»)",
       all((c["vacio"] and c["fuente"] is None and c["valor"] in (p.SIN_DATO, p.NO_CORRESPONDE))
           or (not c["vacio"] and c["fuente"] is not None)
           for f in fichas for g in f["grupos"] for c in g["campos"]))
proveedores = p.proveedores_con_cantidad(fichas)
probar("9 proveedores en el desplegable, con su nombre de proveedores.csv",
       len(proveedores) == 9 and proveedores[0] == {"id": "P01", "nombre": "Laboratorio Andes S.A.", "cantidad": 26})
probar("las cantidades por proveedor suman 257", sum(x["cantidad"] for x in proveedores) == 257)
probar("Norte tiene 14", next(x for x in proveedores if x["id"] == "P08")["cantidad"] == 14)

# LHS-206: lavandina, del catálogo PDF; lo de depósito sale de su ficha de seguridad
f = por_id["P07:LHS-206"]
probar("LHS-206: nombre tal cual", f["nombre"] == "LAVANDINA CLARITA CONCENTRADA X 2000 ML")
probar("LHS-206: categoría con sus 3 niveles", f["categoria"] == "Hogar y limpieza, Limpieza, Desinfectantes y lavandinas")
probar("LHS-206: la explicación de la categoría es la del sistema", f["porque"].startswith("La lavandina"))
probar("LHS-206: lleva el grupo Depósito", [g["titulo"] for g in f["grupos"]] == ["El producto", "Precio", "Depósito"])
probar("LHS-206: se guarda como Corrosivo, según su FDS",
       campo("P07:LHS-206", "Cómo se guarda")["valor"] == "Corrosivo"
       and campo("P07:LHS-206", "Cómo se guarda")["fuente"]["archivo"] == "FDS_Clarita_lavandina.pdf")
probar("LHS-206: ONU 1791", campo("P07:LHS-206", "Número ONU")["valor"] == "1791")
probar("LHS-206: el archivo para abrir es el catálogo, en la página del dato",
       f["archivo_principal"]["archivo"] == "LHS_catalogo_nuevos_productos.pdf" and f["archivo_principal"]["pagina"] == 1)

# AN-1124: medicamento; el precio sale de la actualización (Excel), el resto del PDF
probar("AN-1124: lleva principio activo y condición de venta",
       campo("P01:AN-1124", "Principio activo")["valor"] == "HIDROCORTISONA"
       and campo("P01:AN-1124", "Condición de venta")["valor"] == "Venta libre")
probar("AN-1124: el precio sale de la actualización, fila 12",
       campo("P01:AN-1124", "Precio de costo")["fuente"]["archivo"] == "Actualizacion_precios_Andes.xlsx"
       and campo("P01:AN-1124", "Precio de costo")["fuente"]["ubicacion"] == "fila 12")
probar("AN-1124: sin variante -> «Sin dato»", campo("P01:AN-1124", "Variante")["valor"] == "Sin dato")

# NV-212: suplemento (declara principio activo, pero no es medicamento)
probar("NV-212: muestra el principio activo declarado", campo("P09:NV-212", "Principio activo")["valor"] == "VITAMINA C")
probar("NV-212: la condición de venta no corresponde (no es un medicamento)",
       campo("P09:NV-212", "Condición de venta")["valor"] == p.NO_CORRESPONDE)
probar("una ficha de cuidado personal no lleva filas de medicamento", campo("P07:LHS-206", "Principio activo") is None)

# BF-509: pack
probar("BF-509: 60 UN, pack de 2", campo("P06:BF-509", "Contenido")["valor"] == "60 UN, pack de 2")
probar("BF-509: precio con miles", por_id["P06:BF-509"]["precio"] == "UYU 1.101,14")

# Los que están para revisar
probar("AN-1103: falta el principio activo, en palabras",
       por_id["P01:AN-1103"]["motivos"] == ["Falta un dato obligatorio: principio activo"])
probar("DL-103: sin código y sin precio",
       por_id["P05:DL-103"]["motivos"] == ["Vino sin código de barras", "Falta un dato obligatorio: precio de costo, moneda"])
probar("DL-103: en la lista dice «sin precio»", por_id["P05:DL-103"]["precio"] == "sin precio")
probar("AN-1133: los dos archivos no coinciden", por_id["P01:AN-1133"]["motivos"] == ["Los dos archivos dicen cosas distintas"])
probar("RIV-1203: código de barras inválido", por_id["P02:RIV-1203"]["motivos"] == ["El código de barras que mandó no es válido"])
f = por_id["P03:LT-3447"]
probar("LT-3447: sin código y posible duplicado", f["motivos"] == ["Vino sin código de barras", "Podría ser uno que ya tenemos"])
probar("LT-3447: el candidato con su descripción del catálogo", f["sku"] == "SKU100889" and f["sku_descripcion"] == "JABON PUREZA ANTIBAC. 90GRS")
probar("LT-3447: la fuente es el CSV, línea 46",
       campo("P03:LT-3447", "Descripción")["fuente"]["tipo"] == "CSV" and campo("P03:LT-3447", "Descripción")["fuente"]["ubicacion"] == "línea 46")
probar("los 24 para revisar tienen al menos un motivo en palabras",
       all(f["motivos"] and all("_" not in m for m in f["motivos"]) for f in fichas if f["estado"] == "a_revision"))
probar("una ficha lista para alta no tiene motivos", por_id["P07:LHS-206"]["motivos"] == [])

# Un duplicado
f = por_id["P02:RIV-1206"]
probar("RIV-1206: ya estaba como SKU100714, con la descripción del catálogo",
       f["estado"] == "duplicado" and f["sku"] == "SKU100714" and f["sku_descripcion"] == "ACONDICIONADOR BRISA COLOR X 400 ML")
probar("los 24 duplicados tienen su SKU y su descripción del catálogo",
       all(f["sku"] and f["sku_descripcion"] for f in fichas if f["estado"] == "duplicado"))

# Búsqueda
probar("se encuentra por marca, por código y por código de barras",
       "CLARITA" in por_id["P07:LHS-206"]["busqueda"] and "LHS-206" in por_id["P07:LHS-206"]["busqueda"]
       and "7790840033469" in por_id["P07:LHS-206"]["busqueda"])
probar("«jabon» encuentra los JABÓN/JABON", sum("JABON" in f["busqueda"] for f in fichas) >= 3)

# --- El Excel ---
ids = [f["id"] for f in fichas]
libro = p.armar_excel(resultados, ids)
hoja, hoja_fuentes = libro["Fichas"], libro["Fuentes"]
probar("Excel: hoja Fichas con 257 filas + títulos", hoja.max_row == 258)
probar("Excel: una fila por fuente en la hoja Fuentes",
       hoja_fuentes.max_row == 1 + sum(len(r.get("fuentes") or {}) for r in resultados.values()))
titulos = [c.value for c in hoja[1]]
fila_lhs = next(fila for fila in hoja.iter_rows(min_row=2, values_only=True) if fila[titulos.index("Código del proveedor")] == "LHS-206")
probar("Excel: LHS-206 tal cual la ficha (descripción, precio como número, peligro)",
       fila_lhs[titulos.index("Descripción")] == "LAVANDINA CLARITA CONCENTRADA X 2000 ML"
       and fila_lhs[titulos.index("Precio de costo")] == 88.04 and fila_lhs[titulos.index("Peligro en depósito")] == "corrosivo")
probar("Excel: el código de barras como texto (no 7,79E+12)",
       hoja.cell(row=2, column=titulos.index("Código de barras") + 1).number_format == "@")
probar("Excel: el estado en palabras", fila_lhs[titulos.index("Estado")] == "Lista para alta")
solo_dos = p.armar_excel(resultados, ["P08:IN7003", "P01:AN-1103", "NO:EXISTE"])["Fichas"]
probar("Excel: solo las pedidas, en ese orden, y una que no existe se saltea",
       solo_dos.max_row == 3 and solo_dos.cell(row=2, column=titulos.index("Código del proveedor") + 1).value == "IN7003")
salida = io.BytesIO()
libro.save(salida)
probar("Excel: se guarda y se vuelve a abrir", openpyxl.load_workbook(io.BytesIO(salida.getvalue()))["Fichas"].max_row == 258)

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
