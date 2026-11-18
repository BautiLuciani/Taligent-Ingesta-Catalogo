"""Pruebas sin IA de correr_todo.py (semana 6, paso 5). Correr: python probar_correr_todo.py

Pasos falsos (no llaman a la API ni al orquestador) y una carpeta de salida temporal: se prueba el encadenamiento,
que un Excel que no entra quede afuera con su motivo, que el costo cuente solo las llamadas pagadas en esta corrida,
y el reporte con las fichas congeladas de la semana 5.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from referencias import RUTA_RESULTADOS_SEM5
import correr_todo  # noqa: E402

errores = 0


def chequear(origen, obtenido, esperado):
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def respuesta_guardada(entrada, salida):
    """Una respuesta del modelo como la guarda llamada_guardada (con su usage)."""
    return {"stop_reason": "end_turn", "content": [], "usage": {"input_tokens": entrada, "output_tokens": salida}}


class PasosFalsos:
    """Imitan a los pasos que gastan. El orquestador falso deja lo que deja el real: las mediciones y, si lee algo
    nuevo, la respuesta guardada del modelo."""

    def __init__(self, carpeta_salida: Path, recetas: dict):
        self.salida, self.recetas, self.orquestado = carpeta_salida, recetas, None

    def recibir(self, ruta, de_nuevo):
        proveedor_id = ruta.parent.name.split("_")[0]
        ok = self.recetas.get(proveedor_id, True)
        (self.salida / "recepcion" / f"{proveedor_id}.receta_nueva.json").write_text(
            json.dumps(respuesta_guardada(10_000, 1_000)), encoding="utf-8")  # una recepción pagada en esta corrida
        return {"receta": {"hoja": "Altas"} if ok else None, "problemas": [] if ok else ["la hoja no existe"],
                "costo_usd": 0.0015}  # lo que "costó la primera vez" (no lo que se pagó ahora)

    def leer_fds(self, carpeta, de_nuevo):
        return {"fichas": [{"problemas": []}], "costo_usd": 0.003}

    def orquestar(self, proveedores, batch, de_nuevo):
        self.orquestado = list(proveedores)
        (self.salida / "medicion_lectura.json").write_text(json.dumps({"segundos": 60, "costo_usd": 0.05,
                                                                      "segundos_uno_detras_de_otro": 200}), encoding="utf-8")
        (self.salida / "extracciones" / "nueva.llamada1.json").write_text(
            json.dumps(respuesta_guardada(20_000, 2_000)), encoding="utf-8")
        (self.salida / "medicion_fichas_3.json").write_text(json.dumps({
            "costo_usd": 0.30, "costo_sin_cache_usd": 0.45, "cache_leidos": 750, "input_tokens": 1000, "frenos": [{}],
            "tandas": [{"proveedor_id": "P03", "costo_usd": 0.06}, {"proveedor_id": "P03", "costo_usd": 0.01}]}),
            encoding="utf-8")
        return 0

    def pedidos(self):
        return 0

    def acuses(self, excels):
        return ["acuse.md"]


print("== piezas")
chequear("los 9 proveedores de proveedores.csv", list(correr_todo.nombres_de_proveedores()),
         ["P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08", "P09"])
chequear("los 4 Excel de la bandeja", [r.parent.name for r in correr_todo.excel_de_la_entrada()],
         ["P02_Cosmetica_Rivera", "P04_Higiene_Total", "P06_Bebe_Feliz", "P08_Importadora_Norte"])

with tempfile.TemporaryDirectory() as temporal:
    carpeta = Path(temporal)
    (carpeta / "extracciones").mkdir()
    vieja = carpeta / "extracciones" / "vieja.llamada1.json"
    vieja.write_text(json.dumps(respuesta_guardada(999_999, 99_999)), encoding="utf-8")
    hace_rato = time.time() - 3600
    os.utime(vieja, (hace_rato, hace_rato))
    desde = time.time() - 1
    (carpeta / "extracciones" / "resultado.json").write_text(json.dumps({"productos": []}), encoding="utf-8")
    (carpeta / "extracciones" / "pagada.json").write_text(json.dumps(respuesta_guardada(1_000_000, 0)), encoding="utf-8")
    chequear("cuenta solo lo pagado desde 'desde' (no lo reusado ni los resultados): 1 M de entrada = US$ 0,10",
             correr_todo.costo_de_llamadas_nuevas(desde, [carpeta / "extracciones"]), (0.1, 1))

print("== la corrida con pasos falsos")
with tempfile.TemporaryDirectory() as temporal:
    salida = Path(temporal)
    (salida / "recepcion").mkdir()
    (salida / "extracciones").mkdir()
    pasos = PasosFalsos(salida, recetas={"P04": False})
    nombres = correr_todo.nombres_de_proveedores()
    etapas, siguen, frenados, fichas, lectura = correr_todo.correr(
        pasos, False, False, list(nombres), correr_todo.excel_de_la_entrada(), salida)
    chequear("el Excel que no entra queda afuera, con su motivo", (list(frenados), "la hoja no existe" in frenados["P04"]),
             (["P04"], True))
    chequear("al orquestador van los otros 8", pasos.orquestado, ["P01", "P02", "P03", "P05", "P06", "P07", "P08", "P09"])
    chequear("las etapas, en orden", [e["nombre"][:2] for e in etapas], ["1.", "2a", "2b", "3."])
    recepcion = etapas[0]
    chequear("recepción: se pagaron 4 llamadas nuevas (los 4 Excel se leen, también el que después no entra)",
             recepcion["llamadas_pagas"], 4)
    chequear("recepción: costo pagado = 4 × (10.000 in, 1.000 out) = US$ 0,006", recepcion["costo_usd"], 0.006)
    chequear("recepción: lo que 'costó la primera vez' queda aparte", recepcion["costo_primera_vez_usd"], 0.012)
    chequear("lectura: solo la llamada nueva del orquestador (20.000 in, 2.000 out = US$ 0,003)",
             (etapas[1]["costo_usd"], etapas[1]["llamadas_pagas"]), (0.003, 1))
    chequear("fichas: el costo de la medición del orquestador", etapas[2]["costo_usd"], 0.3)

    resultados = json.loads(RUTA_RESULTADOS_SEM5.read_text(encoding="utf-8"))
    evaluacion = correr_todo.evaluar_fichas(resultados)
    chequear("evaluador con las fichas congeladas de la semana 5: 116/116 ficha y fuente",
             (evaluacion["casos"], evaluacion["ficha"], evaluacion["fuente"]), (116, 116, 116))
    reporte = correr_todo.armar_reporte(etapas, resultados, fichas, lectura, evaluacion, nombres,
                                        {"batch": False, "de_nuevo": False})
    chequear("257 fichas y sus estados", (reporte["fichas"], reporte["estados"]),
             (257, {"lista_para_alta": 209, "duplicado": 24, "a_revision": 24}))
    chequear("costo total = lo pagado (0,006 + 0,003 + 0,30)", reporte["costo_usd"], 0.309)
    chequear("costo primera vez = con la lectura de la primera vez (0,012 + 0,05 + 0,30)", reporte["costo_primera_vez_usd"], 0.362)
    chequear("caché leído", reporte["cache_leido"], 0.75)
    litoral = next(p for p in reporte["proveedores"] if p["proveedor_id"] == "P03")
    chequear("Litoral: 50 fichas, costo de sus tandas y por ficha", (litoral["fichas"], litoral["costo_fichas_usd"],
                                                                   litoral["costo_por_ficha_usd"]), (50, 0.07, 0.0014))

print("== --help no gasta")
ayuda = subprocess.run([sys.executable, "correr_todo.py", "--help"], cwd=Path(__file__).parent,
                       capture_output=True, text=True, encoding="utf-8")
chequear("--help termina antes de la API", (ayuda.returncode, "Corrida completa" in ayuda.stdout, "--batch" in ayuda.stdout),
         (0, False, True))

print()
print("Resultado: todo OK" if errores == 0 else f"Resultado: {errores} con error")
