"""Pruebas de catalogo_viejo.py (sin IA: la parte 2 con un Claude falso). Correr: python probar_catalogo_viejo.py"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from catalogo_viejo import (RUTA_CATALOGO, clasificar, descripcion_estandar, duplicados_internos, etapa_ia, guardar,
                            inconsistencias, leer_catalogo, normalizar, validar_variante)

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


antes = huella(RUTA_CATALOGO)  # la huella del catálogo ANTES de todo: al final tiene que ser idéntica
catalogo = {fila["sku"]: fila for fila in leer_catalogo()}

print("--- descripcion_estandar: los formatos de la sección 3 ---")
base = {"marca": "", "tipo": "", "variante": "", "principio_activo": "", "concentracion": "", "condicion_venta": "",
        "contenido": 0, "unidad": "UN", "unidades_por_envase": 1}
chequear("Medicamento", descripcion_estandar({**base, "marca": "DOLOREX", "concentracion": "400 MG", "tipo": "COMPRIMIDOS",
                                               "condicion_venta": "VENTA_LIBRE", "principio_activo": "IBUPROFENO",
                                               "contenido": 20}), "DOLOREX 400 MG COMPRIMIDOS X 20 UN")
chequear("Suplemento", descripcion_estandar({**base, "marca": "NATURAL VIDA", "principio_activo": "CITRATO DE MAGNESIO",
                                              "concentracion": "400 MG", "tipo": "CAPSULAS", "contenido": 60}),
         "NATURAL VIDA CITRATO DE MAGNESIO 400 MG CAPSULAS X 60 UN")
chequear("Lo demás", descripcion_estandar({**base, "tipo": "SHAMPOO", "marca": "BRISA", "variante": "ANTICASPA",
                                            "contenido": 400, "unidad": "ML"}), "SHAMPOO BRISA ANTICASPA X 400 ML")
chequear("Pack", descripcion_estandar({**base, "tipo": "PAÑALES", "marca": "PEQUEÑOS PASOS", "variante": "M",
                                        "contenido": 36, "unidades_por_envase": 2}), "PAÑALES PEQUEÑOS PASOS M X 36 UN PACK 2")

print("--- clasificar: qué hace el código con productos reales del catálogo ---")
dolorex = clasificar(catalogo["SKU100021"])
chequear("SKU100021 'DOLOREX 600 MG COMP. 10UN': lo arregla el código", dolorex["estado"], "codigo")
chequear("...descripción armada sin abreviaturas", dolorex["cambios"][-1]["propuesto"], "DOLOREX 600 MG COMPRIMIDOS X 10 UN")
colageno = clasificar(catalogo["SKU100056"])
chequear("SKU100056: la unidad GR pasa a G", [(c["campo"], c["actual"], c["propuesto"]) for c in colageno["cambios"]][0],
         ("unidad", "GR", "G"))
shampoo = clasificar(catalogo["SKU100007"])
chequear("SKU100007 'SH. BRISA COLOR 400ML.': necesita criterio por 'COLOR'", (shampoo["estado"], shampoo["palabras_de_mas"]),
         ("criterio", ["COLOR"]))
chequear("...igual el código ya propone la unidad (ML. -> ML), pero no la descripción (depende de la variante)",
         [c["campo"] for c in shampoo["cambios"]], ["unidad"])
chequear("SKU101386 'ALCOHOL CLARITA 96 % 500CC': el 96 no es el contenido, es lo que lo distingue",
         clasificar(catalogo["SKU101386"])["palabras_de_mas"], ["96"])
chequear("SKU100014 (ya según el estándar): nada que hacer", clasificar(catalogo["SKU100014"])["estado"], "ok")
chequear("SKU100420 'LECHE INFANTIL SUAVIT ETAPA 1': el 1 es de la etapa (no es pack: no es 'unidades por envase')",
         clasificar(catalogo["SKU100420"])["palabras_de_mas"], ["ETAPA", "1"])
reparacion = clasificar(catalogo["SKU103990"])
chequear("SKU103990 'REP/CION': abreviatura fuera del vocabulario -> revisar (no va a la IA)",
         (reparacion["estado"], reparacion["cambios"][-1]["campo"]), ("revisar", "revisar"))
chequear("Todos los productos quedan en uno de los 4 estados",
         {clasificar(fila)["estado"] for fila in catalogo.values()} <= {"ok", "codigo", "criterio", "revisar"}, True)

print("--- duplicados_internos: el mismo producto escrito distinto ---")
uno = normalizar({**catalogo["SKU100014"], "sku": "A"})
otro = normalizar({**catalogo["SKU100014"], "sku": "B", "descripcion": "TOALLITAS BELLAFLOR S/ PERF. 80UNID", "unidad": "UNID"})
distinto = normalizar({**catalogo["SKU100014"], "sku": "C", "contenido": "50"})
chequear("A y B son el mismo producto (unidad vieja y otra descripción); C tiene otro contenido",
         duplicados_internos([uno, otro, distinto]), [["A", "B"]])

print("--- blast radius: el catálogo NO se toca ---")
carpeta = Path(tempfile.mkdtemp())
analisis = [clasificar(fila) for fila in catalogo.values()]
guardar(analisis, [], carpeta)
chequear("Escribe solo en su carpeta (propuestas.csv y propuestas.json)", sorted(p.name for p in carpeta.iterdir()),
         ["propuestas.csv", "propuestas.json"])
chequear("El CSV abre en Excel (UTF-8 con BOM, separado por ;)",
         (carpeta / "propuestas.csv").read_bytes()[:3] == b"\xef\xbb\xbf" and ";" in (carpeta / "propuestas.csv").read_text(encoding="utf-8-sig").splitlines()[0],
         True)
chequear("catalogo_actual.csv idéntico al de antes (misma huella)", huella(RUTA_CATALOGO), antes)
shutil.rmtree(carpeta, ignore_errors=True)

print("--- validar_variante: el modelo propone, el código revisa ---")
shampoo = clasificar(catalogo["SKU100007"])
chequear("COLOR (está en la descripción): válida", validar_variante(shampoo, {"variante": "COLOR"}), None)
chequear("null (no es variante): válida", validar_variante(shampoo, {"variante": None}), None)
chequear("COLORACION (no está en la descripción): inventada", validar_variante(shampoo, {"variante": "COLORACION"}),
         "la variante 'COLORACION' usa palabras que no están en la descripción: ['COLORACION']")
alcohol = clasificar(catalogo["SKU101386"])
chequear("'96 %' en el alcohol: válida (el % acompaña al número)", validar_variante(alcohol, {"variante": "96 %"}), None)
medicamento = {**shampoo, "normal": {**shampoo["normal"], "condicion_venta": "VENTA_LIBRE"}}
chequear("En un medicamento la variante va vacía", validar_variante(medicamento, {"variante": "COLOR"}),
         "es un medicamento: la variante va vacía (propuso 'COLOR')")


class ClaudeFalso:
    """Imita messages.create sin IA: contesta según una regla, y anota qué SKU le pidieron en cada llamada."""

    def __init__(self, responder):
        self.responder, self.pedidos, self.messages = responder, [], self

    def create(self, **opciones):
        skus = [json.loads(linea)["sku"] for linea in opciones["messages"][0]["content"].splitlines()[1:]]
        self.pedidos.append(skus)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.responder(skus, len(self.pedidos)))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


print("--- etapa_ia con un Claude falso (sin gastar) ---")
de_prueba = [clasificar(catalogo[sku]) for sku in ("SKU100007", "SKU100049", "SKU101386", "SKU100021")]


def responde_bien(skus, _):
    variantes = {"SKU100007": "COLOR", "SKU100049": "AVENA", "SKU101386": "96 %"}
    return "Listo:\n" + json.dumps([{"sku": s, "variante": variantes[s], "por_que": "x"} for s in skus])


carpeta = Path(tempfile.mkdtemp())
falso = ClaudeFalso(responde_bien)
resumen = etapa_ia(falso, "falso", de_prueba, carpeta)
chequear("Solo van a la IA los 3 'criterio' (el DOLOREX lo arregla el código)", sorted(falso.pedidos[0]),
         ["SKU100007", "SKU100049", "SKU101386"])
chequear("Los 3 con variante decidida", (resumen["con_propuesta"], [p["estado"] for p in de_prueba]),
         (3, ["ia", "ia", "ia", "codigo"]))
cambios = {c["campo"]: c["propuesto"] for c in de_prueba[0]["cambios"]}
chequear("SKU100007: variante COLOR y la descripción armada", (cambios["variante"], cambios["descripcion"]),
         ("COLOR", "SHAMPOO BRISA COLOR X 400 ML"))
chequear("SKU101386: 'ALCOHOL CLARITA 96 % X 500 ML'",
         [c["propuesto"] for c in de_prueba[2]["cambios"] if c["campo"] == "descripcion"], ["ALCOHOL CLARITA 96 % X 500 ML"])
chequear("Los cambios de la IA dicen que son de la IA", {c["origen"] for c in de_prueba[0]["cambios"] if c["campo"] != "unidad"},
         {"ia"})
chequear("La respuesta cruda queda guardada (la evidencia)", len(list((carpeta / "llamadas").glob("*.json"))), 1)


def inventa_y_se_olvida(skus, llamada):
    if llamada == 1:  # 1ª: inventa una variante para uno y se olvida de otro
        return json.dumps([{"sku": "SKU100007", "variante": "COLORACION"}, {"sku": "SKU100049", "variante": "AVENA"}])
    return json.dumps([{"sku": s, "variante": "COLOR" if s == "SKU100007" else "OTRA"} for s in skus])


de_prueba = [clasificar(catalogo[sku]) for sku in ("SKU100007", "SKU100049", "SKU101386")]
falso = ClaudeFalso(inventa_y_se_olvida)
resumen = etapa_ia(falso, "falso", de_prueba, carpeta)
chequear("El 2º intento pide SOLO lo que volvió mal (no la tanda entera)", sorted(falso.pedidos[1]), ["SKU100007", "SKU101386"])
chequear("Tope de intentos: no hay un 3er pedido", len(falso.pedidos), 2)
chequear("SKU100007 se arregló en el 2º intento; SKU101386 inventó dos veces y queda sin propuesta",
         [p["estado"] for p in de_prueba], ["ia", "ia", "sin_propuesta"])
chequear("...y queda el motivo", "no están en la descripción" in de_prueba[2]["problemas"][0], True)
de_prueba = [clasificar(catalogo["SKU100007"])]
resumen = etapa_ia(ClaudeFalso(lambda skus, n: "No sé."), "falso", de_prueba, carpeta)
chequear("Una respuesta sin JSON: sin propuesta, con el motivo",
         (de_prueba[0]["estado"], de_prueba[0]["problemas"]), ("sin_propuesta", ["la respuesta no trae un JSON que se pueda leer"]))

print("--- inconsistencias: la misma palabra decidida distinto en productos del mismo tipo ---")
repelentes = [clasificar(catalogo[sku]) for sku in ("SKU100539", "SKU100567", "SKU102282")]
for producto, variante in zip(repelentes, ("CREMA", "CREMA", None)):
    producto["estado"] = "ia"
    if variante:
        producto["cambios"].append({"campo": "variante", "propuesto": variante, "origen": "ia"})
encontradas = inconsistencias(repelentes)
chequear("CREMA: variante en 2 repelentes y en 1 no -> se detecta",
         [(i["palabra"], i["la_incluyen"], i["no_la_incluyen"]) for i in encontradas],
         [("CREMA", ["SKU100539", "SKU100567"], ["SKU102282"])])
chequear("...y los 3 quedan 'revisar'", [p["estado"] for p in repelentes], ["revisar"] * 3)
chequear("catalogo_actual.csv sigue idéntico", huella(RUTA_CATALOGO), antes)
shutil.rmtree(carpeta, ignore_errors=True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
