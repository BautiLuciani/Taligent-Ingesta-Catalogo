"""Costo por ficha final (semana 5, paso 9): por proveedor, en los tres escenarios de la semana, con lo ya medido (gratis).

Los tres escenarios, con el sistema de esta semana (ficha estructurada con strict):
  A. tiempo real SIN caché: lo que habrían costado los MISMOS tokens del escenario B sin caché (el agente lo calcula en
     cada vuelta: costo_sin_cache_usd). Es la comparación justa: mismo sistema, misma corrida, solo cambia la tarifa.
  B. tiempo real CON caché: medido (paso 5, los 8 proveedores; paso 7C, Bebé Feliz).
  C. batch + caché: medido (paso 8D, la regresión final de los 9 proveedores, 116/116).
Referencia: la semana 4 medida (tiempo real, sin caché y sin la ficha estructurada, 8 proveedores).

La lectura (extractores de PDF, FDS y folleto; recepción de los Excel) se paga UNA vez por archivo: queda guardada y
se reusa en cada corrida. Va aparte, y en el total "primera vez" (lectura + fichas).

Las mediciones están congeladas en salida/experimentos/costos_sem5/ (copias de salida/medicion_fichas_*.json de cada
corrida): una corrida nueva reescribe esos archivos y este cálculo no tiene que cambiar.

Correr: python costo_por_ficha.py   (gratis; guarda salida/costo_por_ficha.json)
"""
import json
from collections import defaultdict
from pathlib import Path

CARPETA_SALIDA = Path(__file__).parent / "salida"
CARPETA_MEDICIONES = CARPETA_SALIDA / "experimentos" / "costos_sem5"
MEDICIONES = {
    "semana_4": "sem4_tiempo_real_sin_cache.json",
    "tiempo_real": ["paso5_tiempo_real_con_cache.json", "paso7_P06_tiempo_real_con_cache.json"],
    "batch": "paso8_batch_con_cache.json",
}
# Lo que se paga una vez por archivo: (proveedor, archivo de salida, cómo leer su costo)
LECTURAS = [
    ("P01", "extracciones/Lista_de_precios_octubre_2026.json"),
    ("P05", "extracciones/Dermalab_lanzamientos_2026.json"),
    ("P07", "extracciones/LHS_catalogo_nuevos_productos.json"),
    ("P07", "extracciones/fds_P07_Limpieza_Hogar_Sur.json"),
    ("P02", "extracciones/fds_P02_Cosmetica_Rivera.json"),
    ("P08", "extracciones/fds_P08_Importadora_Norte.json"),
    ("P02", "recepcion/P02_ALTAS RIVERA OCT.json"),
    ("P04", "recepcion/P04_HigieneTotal_novedades.json"),
    ("P06", "recepcion/P06_BebeFeliz_altas.json"),
    ("P08", "recepcion/P08_NorteImports_new_items_Q4.json"),
]
NOMBRES = {"P01": "Andes", "P02": "Rivera", "P03": "Litoral", "P04": "Higiene Total", "P05": "Dermalab",
           "P06": "Bebé Feliz", "P07": "LHS", "P08": "Norte", "P09": "Natural Vida"}


def por_proveedor(tandas: list[dict]) -> dict[str, dict]:
    """Suma por proveedor: fichas, costo, costo sin caché y tokens leídos del caché / de entrada."""
    suma = defaultdict(lambda: {"fichas": 0, "costo": 0.0, "sin_cache": 0.0, "leidos": 0, "entrada": 0})
    for t in tandas:
        s = suma[t["proveedor_id"]]
        s["fichas"] += t["registrados"]
        s["costo"] += t["costo_usd"]
        s["sin_cache"] += t.get("costo_sin_cache_usd", t["costo_usd"])
        s["leidos"] += t.get("cache_leidos", 0)
        s["entrada"] += t["input_tokens"]
    return dict(suma)


def costo_de_lectura(dato) -> float:
    """El costo guardado de una lectura: un número o {"total": ...}."""
    costo = dato.get("costo_usd", 0)
    return costo["total"] if isinstance(costo, dict) else costo


def calcular(carpeta_mediciones: Path = CARPETA_MEDICIONES, carpeta_salida: Path = CARPETA_SALIDA) -> dict:
    def leer(nombre):
        return json.loads((carpeta_mediciones / nombre).read_text(encoding="utf-8"))

    tiempo_real_tandas, segundos_tr = [], 0.0
    for nombre in MEDICIONES["tiempo_real"]:
        medicion = leer(nombre)
        tiempo_real_tandas += medicion["tandas"]
        segundos_tr += medicion["segundos"]  # las dos corridas fueron una después de otra
    batch = leer(MEDICIONES["batch"])
    semana_4 = leer(MEDICIONES["semana_4"])
    tr, bt, s4 = por_proveedor(tiempo_real_tandas), por_proveedor(batch["tandas"]), por_proveedor(semana_4["tandas"])

    lectura = defaultdict(float)
    for proveedor_id, ruta in LECTURAS:
        ruta_completa = carpeta_salida / ruta
        if ruta_completa.exists():
            lectura[proveedor_id] += costo_de_lectura(json.loads(ruta_completa.read_text(encoding="utf-8")))

    filas = []
    for proveedor_id in sorted(set(tr) | set(bt), key=lambda p: list(NOMBRES).index(p)):
        fichas = bt.get(proveedor_id, tr.get(proveedor_id))["fichas"]
        a = tr[proveedor_id]["sin_cache"] if proveedor_id in tr else None
        b = tr[proveedor_id]["costo"] if proveedor_id in tr else None
        c = bt[proveedor_id]["costo"] if proveedor_id in bt else None
        filas.append({"proveedor_id": proveedor_id, "nombre": NOMBRES[proveedor_id], "fichas": fichas,
                      "lectura_usd": round(lectura[proveedor_id], 6),
                      "tiempo_real_sin_cache_usd": a, "tiempo_real_con_cache_usd": b, "batch_con_cache_usd": c,
                      "semana_4_usd": s4[proveedor_id]["costo"] if proveedor_id in s4 else None})
    fichas = sum(f["fichas"] for f in filas)

    def total(clave):
        return sum(f[clave] for f in filas if f[clave] is not None)

    escenarios = {
        "tiempo_real_sin_cache": total("tiempo_real_sin_cache_usd"),
        "tiempo_real_con_cache": total("tiempo_real_con_cache_usd"),
        "batch_con_cache": total("batch_con_cache_usd"),
    }
    leidos_tr = sum(v["leidos"] for v in tr.values()) / max(1, sum(v["entrada"] for v in tr.values()))
    leidos_bt = sum(v["leidos"] for v in bt.values()) / max(1, sum(v["entrada"] for v in bt.values()))
    return {
        "fichas": fichas,
        "lectura_usd": round(total("lectura_usd"), 6),
        "escenarios_usd": {k: round(v, 6) for k, v in escenarios.items()},
        "por_ficha_usd": {k: round(v / fichas, 6) for k, v in escenarios.items()},
        "primera_vez_por_ficha_usd": {k: round((v + total("lectura_usd")) / fichas, 6) for k, v in escenarios.items()},
        "cache_leido": {"tiempo_real": round(leidos_tr, 3), "batch": round(leidos_bt, 3)},
        "segundos": {"tiempo_real": round(segundos_tr, 1), "batch": batch["segundos"]},
        "semana_4": {"fichas": sum(v["fichas"] for v in s4.values()), "usd": round(sum(v["costo"] for v in s4.values()), 6),
                     "segundos": semana_4["segundos"]},
        "proveedores": filas,
    }


def mostrar(r: dict) -> None:
    def usd(valor, n=4):
        return "-" if valor is None else f"{valor:.{n}f}"
    print(f"\n=== Costo de las fichas por proveedor (US$) · {r['fichas']} fichas, 9 proveedores")
    print(f"{'proveedor':<15}{'fichas':>7}{'lectura':>9}{'TR sin caché':>14}{'TR con caché':>14}{'batch+caché':>13}"
          f"{'por ficha (batch)':>19}")
    for f in r["proveedores"]:
        print(f"{f['nombre']:<15}{f['fichas']:>7}{usd(f['lectura_usd']):>9}{usd(f['tiempo_real_sin_cache_usd']):>14}"
              f"{usd(f['tiempo_real_con_cache_usd']):>14}{usd(f['batch_con_cache_usd']):>13}"
              f"{usd(f['batch_con_cache_usd'] / f['fichas'], 5):>19}")
    e, p, v = r["escenarios_usd"], r["por_ficha_usd"], r["primera_vez_por_ficha_usd"]
    print(f"{'TOTAL':<15}{r['fichas']:>7}{usd(r['lectura_usd']):>9}{usd(e['tiempo_real_sin_cache']):>14}"
          f"{usd(e['tiempo_real_con_cache']):>14}{usd(e['batch_con_cache']):>13}")
    base = e["tiempo_real_sin_cache"]
    print("\nPor ficha (solo las fichas; la lectura se paga una vez por archivo y queda guardada):")
    for clave, nombre in (("tiempo_real_sin_cache", "Tiempo real sin caché"), ("tiempo_real_con_cache", "Tiempo real con caché"),
                          ("batch_con_cache", "Batch + caché")):
        ahorro = "" if clave == "tiempo_real_sin_cache" else f"  ({(e[clave] / base - 1) * 100:+.0f} %)"
        print(f"   {nombre:<23} US$ {p[clave]:.5f}{ahorro} · la primera vez, con la lectura: US$ {v[clave]:.5f}")
    print(f"\nCaché leído: {r['cache_leido']['tiempo_real']:.0%} en tiempo real · {r['cache_leido']['batch']:.0%} en batch"
          f"\nTiempo de las fichas: {r['segundos']['tiempo_real'] / 60:.1f} min en tiempo real · "
          f"{r['segundos']['batch'] / 60:.1f} min en batch")
    s4 = r["semana_4"]
    print(f"Referencia, semana 4 (tiempo real, sin caché ni ficha estructurada): {s4['fichas']} fichas, US$ {s4['usd']:.4f}"
          f" = US$ {s4['usd'] / s4['fichas']:.5f} por ficha")


def main():
    resultado = calcular()
    (CARPETA_SALIDA / "costo_por_ficha.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    mostrar(resultado)
    print("\nGuardado en salida/costo_por_ficha.json")


if __name__ == "__main__":
    main()
