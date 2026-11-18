"""Prueba familias.py SIN IA, con filas armadas como las de los proveedores reales (no lee salida/).
Correr: python probar_familias.py"""
import json
import tempfile
from pathlib import Path

from familias import familias_inconsistentes, huella_de_familia, revisar

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def fila(item_id, **original):
    return {"item_id": item_id, "original": original}


def ficha(**campos):
    base = {"marca": "PEQUEÑOS PASOS", "tipo": "CREMA", "variante": "OXIDO DE ZINC", "categoria": "BEB-HIG-CRE",
            "principio_activo": None, "concentracion": None, "unidad": "G", "contenido": 120}
    return {"ficha": {**base, **campos}}


print("--- huella_de_familia: qué es el producto, sin lo que cambia entre tamaños ---")
crema_120 = {"Producto": "Crema de cambio Pequeños Pasos Oxido De Zinc", "Talle / etapa": None, "Cantidad": "120 g",
             "EAN": "7797745670423", "Precio lista": 252.88, "Precio c/desc. 8%": 232.65}
crema_60 = {**crema_120, "Cantidad": "60 g", "EAN": "7793767735416", "Precio lista": 142.23}
chequear("Bebé Feliz: las dos cremas tienen la misma huella (cambia solo cantidad, EAN y precio)",
         huella_de_familia(crema_120), huella_de_familia(crema_60))
chequear("...y la huella es el nombre del producto", huella_de_familia(crema_120),
         (("Producto", "CREMA DE CAMBIO PEQUEÑOS PASOS OXIDO DE ZINC"),))
panal_p = {"Producto": "Pañal Pequeños Pasos", "Talle / etapa": "P", "Cantidad": "30 un"}
panal_m = {**panal_p, "Talle / etapa": "M"}
chequear("El talle cuenta: pañal P y pañal M NO son la misma familia", huella_de_familia(panal_p) != huella_de_familia(panal_m), True)
chequear("Pañal P de 30 y de 48 sí son la misma familia",
         huella_de_familia(panal_p), huella_de_familia({**panal_p, "Cantidad": "48 un"}))
chequear("Un pack 'Pack Ahorro x2' no es de la familia del pañal suelto (el archivo lo escribe distinto)",
         huella_de_familia({**panal_p, "Producto": "Pañal Pequeños Pasos Pack Ahorro x2", "Cantidad": "2 x 60 un"})
         != huella_de_familia(panal_p), True)
chequear("Rivera: el contenido al final de la descripción no cuenta",
         huella_de_familia({"DESCRIPCION": "ACOND. NATIVA LISO X 200 ML", "EAN": "779-7137-44403-8", "P. COSTO": 104.24}),
         huella_de_familia({"DESCRIPCION": "ACOND. NATIVA LISO 750cc", "EAN": "7793092189062", "P. COSTO": 300.1}))
gripanil_comp = {"fila": "AN-1142 Gripanil ...", "producto": "Gripanil 500 mg + 4 mg + 10 mg", "presentacion": "Comp. x 10",
                 "condicion": "VL", "ean": "7790000000000", "precio": "$ 100"}
gripanil_sobres = {**gripanil_comp, "presentacion": "Sobres x 6"}
chequear("Andes: Gripanil en comprimidos y en sobres NO son la misma familia (la presentación dice el tipo)",
         huella_de_familia(gripanil_comp) != huella_de_familia(gripanil_sobres), True)
chequear("...pero 'Comp. x 10' y 'Comp. x 20' sí (la cantidad no cuenta)",
         huella_de_familia(gripanil_comp), huella_de_familia({**gripanil_comp, "presentacion": "Comp. x 20"}))
chequear("PDF: la fila entera (con contenido y EAN adentro) no cuenta; el nombre sí",
         huella_de_familia({"fila": "LHS-203 Limpiador ... 900 ML", "descripcion": "Limpiador Clarita Multiuso Lavanda",
                            "contenido": "900 ML", "ean": "7798367700178", "costo": "$ 143,33"}),
         (("descripcion", "LIMPIADOR CLARITA MULTIUSO LAVANDA"),))

print("--- familias_inconsistentes: la regla ---")
filas = [fila("P06:BF-527", **crema_120), fila("P06:BF-560", **crema_60),
         fila("P06:BF-506", **panal_p), fila("P06:BF-536", **{**panal_p, "Cantidad": "48 un"}),
         fila("P06:BF-518", **panal_m)]
resultados = {
    "P06:BF-527": ficha(variante="DE CAMBIO OXIDO DE ZINC"),
    "P06:BF-560": ficha(contenido=60),
    "P06:BF-506": ficha(tipo="PAÑALES", variante="P", categoria="BEB-PAN-INF", unidad="UN", contenido=30),
    "P06:BF-536": ficha(tipo="PAÑALES", variante="P", categoria="BEB-PAN-INF", unidad="UN", contenido=48),
    "P06:BF-518": ficha(tipo="PAÑALES", variante="M", categoria="BEB-PAN-INF", unidad="UN", contenido=30),
}
inconsistentes, familias, productos = familias_inconsistentes(filas, resultados)
chequear("2 familias de 2 (cremas y pañales P); el pañal M queda solo", (familias, productos), (2, 4))
chequear("Solo la crema no coincide, en la variante, con cada versión y sus productos", inconsistentes,
         [{"proveedor_id": "P06", "en_el_archivo": ["CREMA DE CAMBIO PEQUEÑOS PASOS OXIDO DE ZINC"],
           "items": ["P06:BF-527", "P06:BF-560"],
           "campos": {"variante": [{"valor": "DE CAMBIO OXIDO DE ZINC", "items": ["P06:BF-527"]},
                                   {"valor": "OXIDO DE ZINC", "items": ["P06:BF-560"]}]}}])
chequear("El contenido distinto dentro de una familia NO es inconsistencia (es lo que cambia)",
         [f for f in inconsistentes if "contenido" in f["campos"]], [])
otra = {**resultados, "P06:BF-536": ficha(tipo="PAÑALES", variante="P", categoria="BEB-PAN-TOA", unidad="UN")}
chequear("Una categoría distinta también se ve",
         [list(f["campos"]) for f in familias_inconsistentes(filas, otra)[0] if f["items"] == ["P06:BF-506", "P06:BF-536"]],
         [["categoria"]])
mezcla = filas + [fila("P02:RIV-1", **crema_120)]
chequear("Proveedores distintos con el mismo texto no son familia", familias_inconsistentes(mezcla, {**resultados,
         "P02:RIV-1": ficha(variante="OTRA")})[1], 2)
sin_ficha = {k: v for k, v in resultados.items() if k != "P06:BF-560"}
chequear("Un producto sin ficha no se compara (la crema queda sola: sin familia)",
         familias_inconsistentes(filas, sin_ficha)[1:], (1, 2))
chequear("Todo coherente: ninguna inconsistencia",
         familias_inconsistentes(filas, {**resultados, "P06:BF-527": ficha()})[0], [])

print("--- revisar: de los archivos a salida/familias.json ---")
carpeta = Path(tempfile.mkdtemp())
(carpeta / "consolidado").mkdir()
(carpeta / "consolidado" / "P06.json").write_text(json.dumps({"filas": filas}, ensure_ascii=False), encoding="utf-8")
(carpeta / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False), encoding="utf-8")
informe = revisar(carpeta / "consolidado", carpeta / "resultados.json", carpeta / "familias.json")
guardado = json.loads((carpeta / "familias.json").read_text(encoding="utf-8"))
chequear("Lo guardado es lo que devuelve, con el conteo", (guardado == informe, informe["familias"], len(informe["inconsistentes"])),
         (True, 2, 1))
chequear("Sin resultados.json no se rompe: 0 familias", revisar(carpeta / "consolidado", carpeta / "no_existe.json")["familias"], 0)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
