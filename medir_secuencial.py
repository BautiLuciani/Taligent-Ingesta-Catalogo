"""Mide la versión SECUENCIAL del sistema: lectura de archivos + fichas, todo uno detrás del otro.

Es la línea de base de la semana 3: contra este tiempo se compara la versión en paralelo.
Usa los scripts que ya existen, sin tocarlos: los corre tal cual los correrías en la terminal.

Correr: python medir_secuencial.py
Cuesta ~US$ 0,22 (vuelve a hacer las lecturas con IA y corre el agente en los 4 proveedores).
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
CARPETA_EXTRACCIONES = CARPETA_SALIDA / "extracciones"
PROVEEDORES = CARPETA_PROYECTO / "Data" / "proveedores"

# Cada paso: (etapa, nombre, argumentos del script, archivo donde queda su costo)
# --de-nuevo: los extractores vuelven a llamar a Haiku. Si reusaran lo guardado, la lectura daría 0 s (trampa).
PASOS = [
    ("lectura", "PDF de LHS",
     ["extractor_pdf.py", str(PROVEEDORES / "P07_Limpieza_Hogar_Sur" / "LHS_catalogo_nuevos_productos.pdf"), "--de-nuevo"],
     CARPETA_EXTRACCIONES / "LHS_catalogo_nuevos_productos.json"),
    ("lectura", "PDF de Andes",
     ["extractor_pdf.py", str(PROVEEDORES / "P01_Laboratorio_Andes" / "Lista_de_precios_octubre_2026.pdf"), "--de-nuevo"],
     CARPETA_EXTRACCIONES / "Lista_de_precios_octubre_2026.json"),
    ("lectura", "FDS de LHS",
     ["extractor_fds.py", str(PROVEEDORES / "P07_Limpieza_Hogar_Sur" / "fichas_de_seguridad"), "--de-nuevo"],
     CARPETA_EXTRACCIONES / "fds_P07_Limpieza_Hogar_Sur.json"),
    ("lectura", "Folleto de Dermalab",
     ["extractor_folleto.py", str(PROVEEDORES / "P05_Dermalab" / "Dermalab_lanzamientos_2026.pdf"), "--de-nuevo"],
     CARPETA_EXTRACCIONES / "Dermalab_lanzamientos_2026.json"),
    ("fichas", "Agente P03 Litoral", ["agente.py", "P03"], CARPETA_SALIDA / "corrida_P03.json"),
    ("fichas", "Agente P07 LHS", ["agente.py", "P07"], CARPETA_SALIDA / "corrida_P07.json"),
    ("fichas", "Agente P01 Andes", ["agente.py", "P01"], CARPETA_SALIDA / "corrida_P01.json"),
    ("fichas", "Agente P05 Dermalab", ["agente.py", "P05"], CARPETA_SALIDA / "corrida_P05.json"),
]


def costo_del_paso(ruta: Path) -> float:
    """Lee lo que costó un paso del archivo que dejó (los extractores y el agente ya guardan su costo)."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if "costo_total_usd" in datos:            # reporte del agente (corrida_Pxx.json)
        return datos["costo_total_usd"]
    costo = datos["costo_usd"]                 # extractores: un número, o un detalle por llamada con su "total"
    return costo["total"] if isinstance(costo, dict) else costo


def main():
    print(f"Versión secuencial: {len(PASOS)} pasos, uno detrás del otro\n")
    pasos_medidos = []
    inicio_total = time.perf_counter()

    for etapa, nombre, argumentos, ruta_costo in PASOS:
        print(f"▶ {nombre} ...", flush=True)
        inicio = time.perf_counter()
        # sys.executable = el mismo Python del .venv que está corriendo este script.
        # Sin capture_output: el hijo escribe directo en la consola, como si lo corrieras a mano.
        # (Si lo capturamos por un "caño", Python en Windows escribe en cp1252 y caracteres como → lo hacen caer.)
        proceso = subprocess.run([sys.executable, *argumentos], cwd=CARPETA_PROYECTO)
        segundos = time.perf_counter() - inicio

        if proceso.returncode != 0:
            # Si un paso falla, frenamos: su error ya quedó en pantalla, y no tiene sentido cronometrar una corrida rota
            sys.exit(f"✖ Falló '{nombre}' (código {proceso.returncode}). Se frena la medición.")

        costo = costo_del_paso(ruta_costo)
        pasos_medidos.append({"etapa": etapa, "paso": nombre, "segundos": round(segundos, 1), "costo_usd": round(costo, 6)})
        print(f"  ✔ {segundos:6.1f} s · US$ {costo:.4f}")

    segundos_total = time.perf_counter() - inicio_total
    por_etapa = {
        etapa: round(sum(p["segundos"] for p in pasos_medidos if p["etapa"] == etapa), 1)
        for etapa in ("lectura", "fichas")
    }
    costo_total = sum(p["costo_usd"] for p in pasos_medidos)

    medicion = {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "modo": "secuencial",
        "segundos_total": round(segundos_total, 1),
        "segundos_por_etapa": por_etapa,
        "costo_total_usd": round(costo_total, 4),
        "pasos": pasos_medidos,
    }
    ruta = CARPETA_SALIDA / "medicion_secuencial.json"
    ruta.write_text(json.dumps(medicion, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Secuencial: {segundos_total:.0f} s ({segundos_total / 60:.1f} min)"
          f" · lectura {por_etapa['lectura']:.0f} s · fichas {por_etapa['fichas']:.0f} s"
          f" · US$ {costo_total:.4f} · guardado en salida/{ruta.name}")


if __name__ == "__main__":
    main()