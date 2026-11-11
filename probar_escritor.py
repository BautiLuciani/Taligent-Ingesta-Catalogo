"""Pruebas del escritor sin IA, con casos armados en una carpeta temporal. Correr: python probar_escritor.py"""
import copy
import json
import shutil
import tempfile
from pathlib import Path

import referencias  # noqa: F401 (semana 4, paso 0: extracciones congeladas; va antes que escritor)
from escritor import escribir, revisar_propuesta

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def propuesta(item_id, **cambios):
    """Una propuesta válida, como la que junta el orquestador (lo que mandó el agente a registrar_ficha)."""
    ficha = {"gtin": "7793469616846", "marca": "SONRISA", "tipo": "PASTA DENTAL", "contenido": 90, "unidad": "G"}
    return {"item_id": item_id, "estado": "lista_para_alta", "ficha": ficha,
            "fuentes": {"gtin": {"archivo": "x.csv", "linea": 2}},
            "categoria_decidida_por": {"campo": "tipo", "valor": "PASTA DENTAL", "explicacion": "Cuidado bucal."},
            **cambios}


carpeta = Path(tempfile.mkdtemp())
consolidado = carpeta / "consolidado"
consolidado.mkdir()
# Lo consolidado: qué productos TIENEN que salir (son ítems reales, para que pasen la regla del servidor)
ESPERADOS = {"P03": ["P03:LT-3303", "P03:LT-3309", "P03:LT-3315"], "P07": ["P07:LHS-206"]}
for proveedor_id, items in ESPERADOS.items():
    (consolidado / f"{proveedor_id}.json").write_text(
        json.dumps({"filas": [{"item_id": item} for item in items]}), encoding="utf-8")
ruta = carpeta / "resultados.json"
completas = {item: propuesta(item) for items in ESPERADOS.values() for item in items}

print("--- revisar_propuesta: la misma regla del servidor ---")
chequear("Una propuesta válida no tiene problemas", revisar_propuesta("P03:LT-3303", completas["P03:LT-3303"]), [])
chequear("Duplicado sin SKU: la regla del servidor la frena",
         len(revisar_propuesta("P03:LT-3303", propuesta("P03:LT-3303", estado="duplicado"))), 1)
chequear("Estado fuera del vocabulario (alguien tocó el archivo)",
         revisar_propuesta("P03:LT-3303", propuesta("P03:LT-3303", estado="aprobado")),
         ["estado fuera del vocabulario: 'aprobado'"])
chequear("Sin categoria_decidida_por", revisar_propuesta("P03:LT-3303", propuesta("P03:LT-3303", categoria_decidida_por=None)),
         ["categoria_decidida_por inválida o ausente"])
chequear("Guardada bajo otro ítem", revisar_propuesta("P03:LT-3309", completas["P03:LT-3303"]),
         ["la propuesta dice ser de 'P03:LT-3303'"])

print("--- escribir: todo completo ---")
ruta.write_text(json.dumps({"P03:LT-9000": {"viejo": True}, "P01:AN-1101": {"de_otra_corrida": True}}), encoding="utf-8")
informe = escribir(completas, ["P03", "P07"], consolidado, ruta)
archivo = json.loads(ruta.read_text(encoding="utf-8"))
chequear("Se escriben los 2 proveedores", informe["escritos"], {"P03": 3, "P07": 1})
chequear("Lo viejo de P03 se reemplaza; lo de P01 (no se procesó) queda", sorted(archivo),
         ["P01:AN-1101", "P03:LT-3303", "P03:LT-3309", "P03:LT-3315", "P07:LHS-206"])
chequear("Cada ficha tiene la misma forma que guarda registrar_ficha", sorted(archivo["P03:LT-3303"]),
         ["categoria_decidida_por", "duplicado_de", "estado", "ficha", "fuentes", "item_id", "motivos_revision"])
chequear("Queda la copia del archivo anterior", json.loads((carpeta / "resultados_anterior.json").read_text(encoding="utf-8")),
         {"P03:LT-9000": {"viejo": True}, "P01:AN-1101": {"de_otra_corrida": True}})

print("--- escribir: un proveedor incompleto NO se escribe (y no borra sus fichas anteriores) ---")
antes = ruta.read_text(encoding="utf-8")
incompletas = copy.deepcopy(completas)
del incompletas["P03:LT-3315"]                                           # falta una
incompletas["P03:LT-3309"]["estado"] = "duplicado"                       # una inválida (sin SKU)
incompletas["P07:LHS-206"]["ficha"]["marca"] = "OTRA"                    # P07 sigue válida
informe = escribir(incompletas, ["P03", "P07"], consolidado, ruta)
archivo = json.loads(ruta.read_text(encoding="utf-8"))
chequear("P03 queda frenado con sus 2 problemas", len(informe["frenados"]["P03"]), 2)
chequear("...el faltante, con su nombre", "P03:LT-3315: falta su propuesta" in informe["frenados"]["P03"], True)
chequear("...y sus fichas anteriores quedan como estaban", archivo["P03:LT-3309"], json.loads(antes)["P03:LT-3309"])
chequear("P07 se escribe igual (un proveedor no frena a otro)", (informe["escritos"], archivo["P07:LHS-206"]["ficha"]["marca"]),
         ({"P07": 1}, "OTRA"))

print("--- escribir: lo que sobra y lo que no se procesó ---")
de_mas = {**completas, "P03:LT-3999": propuesta("P03:LT-3999"), "P05:DL-0001": propuesta("P05:DL-0001")}
informe = escribir(de_mas, ["P03", "P07"], consolidado, ruta)
chequear("Un producto que no está en lo consolidado frena a su proveedor",
         informe["frenados"], {"P03": ["P03:LT-3999: sobra (no está en lo consolidado)"]})
chequear("La propuesta de un proveedor no procesado se informa (no se escribe)", informe["ignoradas"], ["P05:DL-0001"])

print("--- escribir: si no hay nada para escribir, el archivo ni se toca ---")
antes = ruta.read_text(encoding="utf-8")
informe = escribir({}, ["P03", "P07"], consolidado, ruta)
chequear("Los 2 frenados, ninguno escrito", (sorted(informe["frenados"]), informe["escritos"]), (["P03", "P07"], {}))
chequear("resultados.json igual que antes", ruta.read_text(encoding="utf-8"), antes)

print("--- escribir: la marca del detector (paso 9) ---")
marcadas = copy.deepcopy(completas)
marcadas["P03:LT-3309"]["inestable"] = {"campos": ["ficha.marca"], "otra_version": propuesta("P03:LT-3309")}
informe = escribir(marcadas, ["P03", "P07"], consolidado, ruta)
archivo = json.loads(ruta.read_text(encoding="utf-8"))
chequear("La ficha marcada se escribe igual, con su marca al lado (no adentro de la ficha)",
         (archivo["P03:LT-3309"]["inestable"]["campos"], "inestable" in archivo["P03:LT-3309"]["ficha"]), (["ficha.marca"], False))
chequear("Las que coinciden van sin marca", "inestable" in archivo["P03:LT-3303"], False)
chequear("El informe dice cuáles quedaron marcadas", informe["inestables"], ["P03:LT-3309"])

shutil.rmtree(carpeta, ignore_errors=True)
print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")