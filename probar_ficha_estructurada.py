"""Pruebas de la ficha estructurada (semana 5, paso 2A) sin IA. Correr: python probar_ficha_estructurada.py"""
import copy
import json

from pydantic import ValidationError

from referencias import RUTA_RESULTADOS_SEM4  # carpetas congeladas: va antes que cualquier import del servidor
from ficha_estructurada import (CAMPOS_FICHA, CATEGORIAS, TIPOS, Ficha, FuenteDeCampo,  # noqa: E402
                                casilleros_de_las_fuentes, formulario_de, fuente_de_la_guia, fuentes_de_la_guia,
                                registro_interno)

# Las 225 fichas del cierre de la semana 4 (evaluador 100/101), congeladas: el formulario nuevo no puede rechazar ninguna
RESULTADOS = json.loads(RUTA_RESULTADOS_SEM4.read_text(encoding="utf-8"))
JABON = RESULTADOS["P03:LT-3357"]   # CSV, sin EAN, posible duplicado (el del experimento del paso 1)
LAVANDINA = RESULTADOS["P07:LHS-206"]  # PDF + FDS
RIVERA = RESULTADOS["P02:RIV-1206"]    # Excel

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def ficha_completa(ficha: dict) -> dict:
    """Una ficha de resultados.json con los 18 campos (peligro y ONU solo están en los productos con FDS)."""
    return {campo: ficha.get(campo) for campo in CAMPOS_FICHA}


def rechaza(ficha: dict) -> bool:
    try:
        Ficha.model_validate(ficha)
        return False
    except ValidationError:
        return True


print("--- Lo más importante: las 225 fichas de la semana 4 entran en el formulario nuevo ---")
chequear("Son las 225 del cierre de la semana 4", len(RESULTADOS), 225)
chequear("Ninguna rechazada por el modelo Ficha (0 rechazos falsos)",
         [k for k, r in RESULTADOS.items() if rechaza(ficha_completa(r["ficha"]))], [])
chequear("Ninguna fuente de las 225 queda fuera de los casilleros (ida y vuelta idéntica)",
         [k for k, r in RESULTADOS.items()
          if fuentes_de_la_guia(casilleros_de_las_fuentes(r["fuentes"]), r["ficha"]) != (r["fuentes"], [])], [])
chequear("Las 3 formas de la guía aparecen (CSV/mail, PDF, Excel)",
         sorted({tuple(sorted(f)) for r in RESULTADOS.values() for f in r["fuentes"].values()}),
         [("archivo", "fila", "hoja"), ("archivo", "linea"), ("archivo", "pagina")])

print("--- Las listas cerradas salen del vocabulario y la taxonomía ---")
chequear("42 tipos, sin repetir (CREMA y GEL están en 2 familias)", (len(TIPOS), len(set(TIPOS))), (42, 42))
chequear("50 categorías de la taxonomía", len(CATEGORIAS), 50)
chequear("Un tipo que no existe: rechazado", rechaza({**ficha_completa(JABON["ficha"]), "tipo": "JABÓN DE TOCADOR"}), True)
chequear("Una unidad vieja (GRS): rechazada", rechaza({**ficha_completa(JABON["ficha"]), "unidad": "GRS"}), True)
chequear("Una categoría inventada: rechazada", rechaza({**ficha_completa(JABON["ficha"]), "categoria": "CUI-HIG-XXX"}), True)
chequear("La condición abreviada (VL): rechazada", rechaza({**ficha_completa(JABON["ficha"]), "condicion_venta": "VL"}), True)
chequear("Un campo de más: rechazado (no hay claves libres)", rechaza({**ficha_completa(JABON["ficha"]), "color": "AZUL"}), True)
sin_marca = ficha_completa(JABON["ficha"])
del sin_marca["marca"]
chequear("Un campo que falta (en vez de null): rechazado (van todos)", rechaza(sin_marca), True)
chequear("Un campo en null: vale", rechaza({**ficha_completa(JABON["ficha"]), "variante": None}), False)

print("--- El formulario que va a ver la API (lo que compiló en el paso 1) ---")
esquema_ficha, esquema_fuente = Ficha.model_json_schema(), FuenteDeCampo.model_json_schema()
for nombre, esquema in (("Ficha", esquema_ficha), ("FuenteDeCampo", esquema_fuente)):
    chequear(f"{nombre}: 0 opcionales (todos obligatorios)", set(esquema["properties"]) - set(esquema["required"]), set())
    chequear(f"{nombre}: sin claves libres (additionalProperties false)", esquema["additionalProperties"], False)
    chequear(f"{nombre}: ningún valor por defecto", [c for c, p in esquema["properties"].items() if "default" in p], [])
chequear("Ficha: 14 uniones (los campos que pueden quedar en null)",
         sum(1 for p in esquema_ficha["properties"].values() if "anyOf" in p), 14)
chequear("FuenteDeCampo: 0 uniones", sum(1 for p in esquema_fuente["properties"].values() if "anyOf" in p), 0)

print("--- fuente_de_la_guia: casillero -> forma de la guía ---")
chequear("CSV: linea", fuente_de_la_guia({"campo": "marca", "archivo": "a.csv", "tipo_ubicacion": "linea", "numero": 20,
                                          "hoja": ""}), {"archivo": "a.csv", "linea": 20})
chequear("PDF: pagina", fuente_de_la_guia({"campo": "marca", "archivo": "a.pdf", "tipo_ubicacion": "pagina",
                                           "numero": 2, "hoja": ""}), {"archivo": "a.pdf", "pagina": 2})
chequear("Excel: hoja y fila", fuente_de_la_guia({"campo": "marca", "archivo": "a.xlsx", "tipo_ubicacion": "hoja_fila",
                                                  "numero": 12, "hoja": "Altas"}),
         {"archivo": "a.xlsx", "hoja": "Altas", "fila": 12})

print("--- fuentes_de_la_guia: lo que el formulario no puede atajar ---")
base = casilleros_de_las_fuentes(JABON["fuentes"])
marca = next(f for f in base if f["campo"] == "marca")
chequear("Sin problemas: la del jabón tal cual", fuentes_de_la_guia(base, JABON["ficha"]), (JABON["fuentes"], []))
_, problemas = fuentes_de_la_guia(base + [{**marca, "numero": 21}], JABON["ficha"])
chequear("Un campo con dos fuentes: problema (no se elige una)", problemas,
         ["el campo marca tiene más de una fuente: va una sola por campo"])
_, problemas = fuentes_de_la_guia(base + [{**marca, "campo": "gtin"}], JABON["ficha"])  # el jabón no trae GTIN
chequear("Fuente de un campo en null: problema", problemas,
         ["el campo gtin está en null y tiene fuente: los campos en null no llevan fuente"])
_, problemas = fuentes_de_la_guia([{**marca, "numero": 0}], JABON["ficha"])
chequear("Número 0: problema", problemas, ["la fuente de marca tiene numero 0: línea, página y fila empiezan en 1"])
_, problemas = fuentes_de_la_guia([{**marca, "tipo_ubicacion": "hoja_fila"}], JABON["ficha"])
chequear("Excel sin hoja: problema", problemas, ["la fuente de marca es de un Excel (hoja_fila) y no dice la hoja"])
_, problemas = fuentes_de_la_guia([{**marca, "hoja": "Altas"}], JABON["ficha"])
chequear("Hoja escrita en una línea de CSV: problema", problemas,
         ["la fuente de marca es linea y trae hoja 'Altas': la hoja solo va en un Excel (hoja_fila)"])

print("--- registro_interno: lo que guardan el servidor y los hooks (la forma de resultados.json) ---")
for nombre, r in (("CSV (LT-3357)", JABON), ("PDF + FDS (LHS-206)", LAVANDINA), ("Excel (RIV-1206)", RIVERA)):
    entrada = {"item_id": r["item_id"], "estado": r["estado"], "ficha": ficha_completa(r["ficha"]),
               "fuentes": casilleros_de_las_fuentes(r["fuentes"]), "motivos_revision": r["motivos_revision"],
               "duplicado_de": r["duplicado_de"], "categoria_decidida_por": r["categoria_decidida_por"]}
    interno = registro_interno(copy.deepcopy(entrada))
    chequear(f"{nombre}: las fuentes vuelven a la forma de la guía", interno["fuentes"], r["fuentes"])
    chequear(f"{nombre}: el resto queda igual", {k: v for k, v in interno.items() if k != "fuentes"},
             {k: v for k, v in entrada.items() if k != "fuentes"})
chequear("Fuentes que ya estaban en la forma de la guía: no se tocan",
         registro_interno({"ficha": JABON["ficha"], "fuentes": JABON["fuentes"]})["fuentes"], JABON["fuentes"])

print("--- formulario_de: un registro armado a mano (como antes) -> argumentos del formulario nuevo ---")
parcial = {"item_id": "P03:LT-3303", "estado": "lista_para_alta", "ficha": {"marca": "SONRISA", "contenido": 90},
           "fuentes": {"marca": {"archivo": "a.csv", "linea": 2}}}
nuevo = formulario_de(parcial)
chequear("Completa los 18 campos (los que faltaban, en null)", (list(nuevo["ficha"]), nuevo["ficha"]["gtin"]),
         (list(CAMPOS_FICHA), None))
chequear("Pasa las fuentes a casilleros", nuevo["fuentes"],
         [{"campo": "marca", "archivo": "a.csv", "tipo_ubicacion": "linea", "numero": 2, "hoja": ""}])
chequear("Completa motivos_revision y duplicado_de (ahora obligatorios)",
         (nuevo["motivos_revision"], nuevo["duplicado_de"]), ([], None))
chequear("Una ficha que no es diccionario queda igual (la rechaza el servidor)", formulario_de({"ficha": None})["ficha"], None)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")