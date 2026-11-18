"""Prueba costo_por_ficha.py SIN IA, con mediciones armadas a mano (no lee salida/).
Correr: python probar_costo_por_ficha.py"""
import json
import tempfile
from pathlib import Path

import costo_por_ficha
from costo_por_ficha import calcular, costo_de_lectura, por_proveedor

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def tanda(proveedor_id, fichas, costo, sin_cache=None, leidos=0, entrada=100):
    t = {"proveedor_id": proveedor_id, "registrados": fichas, "costo_usd": costo, "input_tokens": entrada,
         "cache_leidos": leidos}
    if sin_cache is not None:
        t["costo_sin_cache_usd"] = sin_cache
    return t


print("--- por_proveedor y costo_de_lectura ---")
suma = por_proveedor([tanda("P03", 10, 0.01, 0.02, 50), tanda("P03", 5, 0.005, 0.01, 30), tanda("P07", 4, 0.004)])
chequear("Suma por proveedor fichas, costo y costo sin caché",
         (suma["P03"]["fichas"], round(suma["P03"]["costo"], 6), round(suma["P03"]["sin_cache"], 6)), (15, 0.015, 0.03))
chequear("Sin costo_sin_cache (semana 4), el sin caché es el costo", suma["P07"]["sin_cache"], 0.004)
chequear("La lectura: un número", costo_de_lectura({"costo_usd": 0.0129}), 0.0129)
chequear("...o {'total': ...} (los PDF con varias llamadas)", costo_de_lectura({"costo_usd": {"total": 0.0189}}), 0.0189)
chequear("...o nada (0)", costo_de_lectura({}), 0)

print("--- calcular: los tres escenarios ---")
carpeta = Path(tempfile.mkdtemp())
mediciones, salida = carpeta / "mediciones", carpeta / "salida"
mediciones.mkdir()
(salida / "recepcion").mkdir(parents=True)


def guardar(nombre, tandas, segundos):
    (mediciones / nombre).write_text(json.dumps({"tandas": tandas, "segundos": segundos}), encoding="utf-8")


guardar("sem4_tiempo_real_sin_cache.json", [tanda("P03", 10, 0.020)], 100)
guardar("paso5_tiempo_real_con_cache.json", [tanda("P03", 10, 0.015, 0.025, 75)], 200)
guardar("paso7_P06_tiempo_real_con_cache.json", [tanda("P06", 10, 0.010, 0.020, 70)], 50)
guardar("paso8_batch_con_cache.json", [tanda("P03", 10, 0.008, 0.012, 80), tanda("P06", 10, 0.005, 0.010, 80)], 900)
(salida / "recepcion" / "P06_BebeFeliz_altas.json").write_text(json.dumps({"costo_usd": 0.002}), encoding="utf-8")
r = calcular(mediciones, salida)
chequear("20 fichas de 2 proveedores (P06 entra por su corrida aparte)", (r["fichas"], [f["proveedor_id"] for f in r["proveedores"]]),
         (20, ["P03", "P06"]))
chequear("Tiempo real sin caché = los mismos tokens sin caché (0,025 + 0,020)", r["escenarios_usd"]["tiempo_real_sin_cache"], 0.045)
chequear("Tiempo real con caché, medido (0,015 + 0,010)", r["escenarios_usd"]["tiempo_real_con_cache"], 0.025)
chequear("Batch + caché, medido (0,008 + 0,005)", r["escenarios_usd"]["batch_con_cache"], 0.013)
chequear("Por ficha (batch: 0,013 / 20)", r["por_ficha_usd"]["batch_con_cache"], 0.00065)
chequear("La lectura aparte y en 'la primera vez' ((0,013 + 0,002) / 20)",
         (r["lectura_usd"], r["primera_vez_por_ficha_usd"]["batch_con_cache"]), (0.002, 0.00075))
chequear("Los tiempos de las dos corridas en tiempo real se suman; el batch tal cual", r["segundos"], {"tiempo_real": 250, "batch": 900})
chequear("Caché leído: 145 de 200 en tiempo real, 160 de 200 en batch", r["cache_leido"], {"tiempo_real": 0.725, "batch": 0.8})
chequear("La referencia de la semana 4", r["semana_4"], {"fichas": 10, "usd": 0.02, "segundos": 100})
chequear("Las lecturas reales están en la lista (las 10 que se pagan una vez)", len(costo_por_ficha.LECTURAS), 10)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
