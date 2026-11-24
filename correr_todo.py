"""Todo con un comando (semana 6, paso 5): los 9 proveedores de punta a punta, con su costo y su tiempo.

Uso:
    python correr_todo.py              # tiempo real (PAGA ~US$ 0,38, ~11 min): reusa lo ya leído de cada archivo
    python correr_todo.py --batch      # las fichas por la Batch API (PAGA ~US$ 0,21, ~35 min)
    python correr_todo.py --de-nuevo   # además vuelve a leer TODO con IA: PDF, FDS y recepción (~US$ 0,05 más)

No hay lógica nueva acá: encadena las piezas de las semanas 1 a 5, cada una con su chequeo, y junta el reporte.
  1. Recepción: cada Excel de entrada/ pasa por el recepcionista (receta) y, si trae FDS, por extractor_fds.py.
     Un Excel cuya receta no entra queda afuera de esta corrida, con su motivo (no se procesa a ciegas).
  2. Lectura + consolidación + fichas + único escritor: el orquestador (lectores en paralelo, fichadores con hooks y
     permisos, caché; con --batch, por la Batch API), en un proceso aparte para que el servidor arranque viendo la
     recepción recién hecha (como la bandeja).
  3. Después del escritor (código, gratis): el pedido a cada proveedor y el acuse de recibo de cada Excel.
  4. El evaluador de fichas (código, gratis): los 116 casos verificados por una persona.
  5. El reporte: tiempo y costo por etapa, fichas y costo por proveedor, costo por ficha. En salida/corrida_completa.json.

La lectura se paga UNA vez por archivo: sin --de-nuevo se reusan las respuestas guardadas (mismo archivo, mismo
pedido = misma respuesta) y esa etapa cuesta ~0. El costo por ficha "primera vez" (con la lectura) está en el reporte.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_SALIDA = CARPETA_PROYECTO / "salida"
CARPETA_ENTRADA = CARPETA_PROYECTO / "entrada"
CARPETA_EVALUACION = CARPETA_PROYECTO / "evaluacion"
RUTA_REPORTE = CARPETA_SALIDA / "corrida_completa.json"
RUTA_PROVEEDORES = CARPETA_PROYECTO / "Data" / "proveedores" / "proveedores.csv"


# --- Piezas sin IA (se prueban en probar_correr_todo.py) ---

def nombres_de_proveedores(ruta: Path = RUTA_PROVEEDORES) -> dict[str, str]:
    with ruta.open(encoding="utf-8-sig") as archivo:
        return {fila["proveedor_id"]: fila["nombre"] for fila in csv.DictReader(archivo)}


def excel_de_la_entrada(carpeta: Path = CARPETA_ENTRADA) -> list[Path]:
    """Los Excel de entrada/<carpeta del proveedor>/ (sin los temporales de Excel ni lo de fichas_de_seguridad/)."""
    if not carpeta.is_dir():
        return []
    return sorted(ruta for ruta in carpeta.glob("*/*.xlsx") if not ruta.name.startswith("~$"))


CARPETAS_DE_LLAMADAS = (CARPETA_SALIDA / "recepcion", CARPETA_SALIDA / "extracciones")


def costo_de_llamadas_nuevas(desde: float, carpetas=CARPETAS_DE_LLAMADAS) -> tuple[float, int]:
    """Lo que se PAGÓ de verdad en lecturas desde 'desde': el costo de cada respuesta del modelo guardada en esta corrida.

    Las lecturas reusadas no se pagan, pero la recepción y los extractores devuelven el costo que tuvieron la primera
    vez: sumar eso diría que se gastó lo que no se gastó. Cada llamada paga se guarda entera (con su usage) en
    llamada_guardada; los resultados (sin usage) no cuentan.
    """
    from extractor_pdf import costo_usd
    costo, cantidad = 0.0, 0
    for carpeta in carpetas:
        if not carpeta.is_dir():
            continue
        for ruta in carpeta.rglob("*.json"):
            if ruta.stat().st_mtime < desde:
                continue
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(datos, dict) and "usage" in datos and "stop_reason" in datos:
                costo += costo_usd(datos)
                cantidad += 1
    return round(costo, 6), cantidad


def medicion_mas_nueva(carpeta: Path, desde: float) -> Path | None:
    """El medicion_fichas_*.json que escribió el orquestador en ESTA corrida (modificado después de 'desde')."""
    candidatos = [r for r in carpeta.glob("medicion_fichas_*.json") if r.stat().st_mtime >= desde]
    return max(candidatos, key=lambda r: r.stat().st_mtime) if candidatos else None


def evaluar_fichas(resultados: dict, carpeta: Path = CARPETA_EVALUACION) -> dict:
    """Los casos verificados de los 9 proveedores contra resultados.json, con la MISMA comparación de evaluar.py."""
    from evaluar import comparar_caso
    por_archivo, fichas_ok, fuentes_ok, total = {}, 0, 0, 0
    for ruta in sorted(carpeta.glob("casos_*.json")):
        casos = json.loads(ruta.read_text(encoding="utf-8"))
        ok_ficha = ok_fuente = 0
        for caso in casos:
            errores, errores_fuente, _ = comparar_caso(caso["esperado"], resultados.get(caso["item_id"]))
            ok_ficha += not errores
            ok_fuente += not errores_fuente
        por_archivo[ruta.stem.removeprefix("casos_")] = {"casos": len(casos), "ficha": ok_ficha, "fuente": ok_fuente}
        fichas_ok, fuentes_ok, total = fichas_ok + ok_ficha, fuentes_ok + ok_fuente, total + len(casos)
    return {"casos": total, "ficha": fichas_ok, "fuente": fuentes_ok, "por_archivo": por_archivo}


def por_proveedor(resultados: dict, medicion: dict | None, nombres: dict[str, str]) -> list[dict]:
    """Fichas, estados y costo de las fichas de cada proveedor (el costo, sumando sus tandas de la medición)."""
    filas = []
    for proveedor_id, nombre in sorted(nombres.items()):
        suyas = [r for item_id, r in resultados.items() if item_id.startswith(f"{proveedor_id}:")]
        tandas = [t for t in (medicion or {}).get("tandas", []) if t.get("proveedor_id") == proveedor_id]
        costo = sum(t.get("costo_usd") or 0 for t in tandas)
        estados = {}
        for r in suyas:
            estados[r["estado"]] = estados.get(r["estado"], 0) + 1
        filas.append({"proveedor_id": proveedor_id, "nombre": nombre, "fichas": len(suyas), "estados": estados,
                      "costo_fichas_usd": round(costo, 6),
                      "costo_por_ficha_usd": round(costo / len(suyas), 6) if suyas and tandas else None})
    return filas


def armar_reporte(etapas: list[dict], resultados: dict, medicion_fichas: dict | None, medicion_lectura: dict | None,
                  evaluacion: dict, nombres: dict[str, str], opciones: dict) -> dict:
    """Junta todo: tiempo y costo por etapa (y total), fichas, estados, costo por ficha y el evaluador."""
    costo_total = sum(e.get("costo_usd") or 0 for e in etapas)
    segundos = sum(e.get("segundos") or 0 for e in etapas)
    estados = {}
    for r in resultados.values():
        estados[r["estado"]] = estados.get(r["estado"], 0) + 1
    fichas = len(resultados)
    return {
        "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
        "opciones": opciones,
        "segundos": round(segundos, 1),
        "costo_usd": round(costo_total, 6),
        "fichas": fichas,
        "costo_por_ficha_usd": round(costo_total / fichas, 6) if fichas else None,
        # lo que habría costado leyendo cada archivo por primera vez (la lectura se paga una vez por archivo)
        "costo_primera_vez_usd": round(costo_total - sum(e.get("costo_usd") or 0 for e in etapas if "costo_primera_vez_usd" in e)
                                       + sum(e["costo_primera_vez_usd"] for e in etapas if "costo_primera_vez_usd" in e), 6),
        "estados": estados,
        "etapas": etapas,
        "cache_leido": (round(medicion_fichas["cache_leidos"] / medicion_fichas["input_tokens"], 3)
                        if medicion_fichas and medicion_fichas.get("input_tokens") else None),
        "costo_fichas_sin_cache_usd": (medicion_fichas or {}).get("costo_sin_cache_usd"),
        "frenos_de_hooks": len((medicion_fichas or {}).get("frenos", [])),
        "lectura_en_paralelo": ({"segundos": medicion_lectura.get("segundos"),
                                 "uno_detras_de_otro": medicion_lectura.get("segundos_uno_detras_de_otro")}
                                if medicion_lectura else None),
        "proveedores": por_proveedor(resultados, medicion_fichas, nombres),
        "evaluador": evaluacion,
    }


def minutos(segundos: float) -> str:
    return f"{int(segundos // 60)} min {int(segundos % 60):02d} s" if segundos >= 60 else f"{segundos:.0f} s"


def mostrar_reporte(reporte: dict) -> None:
    print("\n" + "=" * 78)
    print(f"CORRIDA COMPLETA · {reporte['fecha']} · " + ("Batch API" if reporte["opciones"]["batch"] else "tiempo real")
          + (" · lectura desde cero" if reporte["opciones"]["de_nuevo"] else ""))
    print("=" * 78)
    print(f"{'etapa':<44}{'tiempo':>14}{'costo US$':>14}")
    for etapa in reporte["etapas"]:
        print(f"{etapa['nombre']:<44}{minutos(etapa['segundos']):>14}{etapa['costo_usd']:>14.4f}")
    print(f"{'TOTAL':<44}{minutos(reporte['segundos']):>14}{reporte['costo_usd']:>14.4f}")
    print(f"\n{'proveedor':<34}{'fichas':>7}{'alta':>6}{'dup.':>6}{'rev.':>6}{'US$ fichas':>12}")
    for p in reporte["proveedores"]:
        e = p["estados"]
        print(f"{p['proveedor_id'] + ' ' + p['nombre']:<34}{p['fichas']:>7}{e.get('lista_para_alta', 0):>6}"
              f"{e.get('duplicado', 0):>6}{e.get('a_revision', 0):>6}{p['costo_fichas_usd']:>12.4f}")
    e = reporte["estados"]
    print(f"{'TOTAL':<34}{reporte['fichas']:>7}{e.get('lista_para_alta', 0):>6}{e.get('duplicado', 0):>6}"
          f"{e.get('a_revision', 0):>6}")
    print(f"\nCosto por ficha: US$ {reporte['costo_por_ficha_usd']:.5f}"
          + (f" · caché leído {reporte['cache_leido']:.0%}" if reporte["cache_leido"] is not None else "")
          + (f" · sin caché las fichas habrían costado US$ {reporte['costo_fichas_sin_cache_usd']:.4f}"
             if reporte["costo_fichas_sin_cache_usd"] else ""))
    if fichas_ := reporte["fichas"]:
        print(f"Con la lectura de cada archivo por primera vez: US$ {reporte['costo_primera_vez_usd']:.4f}"
              f" = US$ {reporte['costo_primera_vez_usd'] / fichas_:.5f} por ficha")
    ev = reporte["evaluador"]
    print(f"Evaluador: {ev['ficha']}/{ev['casos']} ficha entera · {ev['fuente']}/{ev['casos']} fuente · "
          f"frenos de los hooks: {reporte['frenos_de_hooks']}")
    if reporte.get("frenados"):
        print(f"Con frenos: el reporte quedó en salida/corrida_completa_con_problemas.json "
              f"(salida/{RUTA_REPORTE.name} sigue siendo el de la última corrida que salió bien)")
    else:
        print(f"Reporte guardado en salida/{RUTA_REPORTE.name}")


# --- Los pasos que gastan (separados para poder probar el flujo sin IA) ---

class Pasos:
    def __init__(self):
        import anthropic  # recién acá: las pruebas usan pasos falsos
        from dotenv import load_dotenv
        load_dotenv(CARPETA_PROYECTO / ".env")
        self.modelo = os.getenv("MODELO")
        if not self.modelo:
            sys.exit("ERROR: falta MODELO en el .env")
        self.cliente = anthropic.Anthropic()

    def recibir(self, ruta: Path, de_nuevo: bool) -> dict:
        from recepcion import recibir
        return recibir(self.cliente, self.modelo, ruta, de_nuevo)

    def leer_fds(self, carpeta: Path, de_nuevo: bool) -> dict:
        from extractor_fds import extraer_fds
        return extraer_fds(self.cliente, self.modelo, carpeta, de_nuevo)

    def orquestar(self, proveedores: list[str], batch: bool, de_nuevo: bool) -> int:
        """El orquestador en un proceso aparte, escribiendo en la consola (se ve el avance en vivo)."""
        comando = [sys.executable, "orquestador.py", "--fichas", "--proveedores", *proveedores]
        comando += ["--batch"] if batch else []
        comando += ["--de-nuevo"] if de_nuevo else []
        return subprocess.run(comando, cwd=CARPETA_PROYECTO).returncode

    def pedidos(self) -> int:
        """pedido_proveedor.py para todos. Su salida (los mensajes enteros) no se muestra: quedan en salida/pedidos/."""
        return subprocess.run([sys.executable, "pedido_proveedor.py"], cwd=CARPETA_PROYECTO,
                              stdout=subprocess.DEVNULL).returncode

    def acuses(self, excels: list[Path]) -> list[str]:
        """Regenera el acuse de recibo de cada Excel que pasó por la bandeja (con las fichas de esta corrida)."""
        from acuse import RUTA_HOOKS, RUTA_REGISTRO, RUTA_RESULTADOS, armar_acuse, guardar_acuse, leer_json
        from recepcion import ruta_relativa
        registro, hechos = leer_json(RUTA_REGISTRO, {}), []
        for ruta in excels:
            anotado = registro.get(ruta_relativa(ruta))
            if anotado is None:
                continue  # no pasó por la bandeja: no hay acuse que regenerar
            texto = armar_acuse(ruta, anotado, leer_json(RUTA_RESULTADOS, {}), leer_json(RUTA_HOOKS, {}))
            hechos.append(guardar_acuse(ruta, anotado, texto).name)
        return hechos


def correr(pasos, batch: bool, de_nuevo: bool, proveedores_todos: list[str], excels: list[Path],
           carpeta_salida: Path = CARPETA_SALIDA) -> tuple:
    """Las etapas 1 a 3. Devuelve (etapas con tiempo y costo, proveedores que siguieron, frenados con su motivo,
    la medición de las fichas y la de la lectura que dejó el orquestador)."""
    etapas, frenados = [], {}

    # 1. Recepción de los Excel + sus FDS
    inicio, inicio_reloj, costo_primera_vez = time.perf_counter(), time.time(), 0.0
    for ruta in excels:
        proveedor_id = ruta.parent.name.split("_")[0]
        print(f"📥 Recepción: {ruta.parent.name}/{ruta.name}")
        recepcion = pasos.recibir(ruta, de_nuevo)
        costo_primera_vez += recepcion.get("costo_usd") or 0
        if recepcion.get("receta") is None:
            frenados[proveedor_id] = "su receta no entró en la recepción: " + "; ".join(recepcion.get("problemas", []))
            continue
        carpeta_fds = ruta.parent / "fichas_de_seguridad"
        if carpeta_fds.is_dir():
            fds = pasos.leer_fds(carpeta_fds, de_nuevo)
            costo_primera_vez += fds.get("costo_usd") or 0
            problemas = [p for ficha in fds.get("fichas", []) for p in ficha.get("problemas", [])]
            if problemas:
                frenados[proveedor_id] = "la lectura de sus FDS quedó con problemas: " + "; ".join(problemas[:3])
    carpetas = (carpeta_salida / "recepcion", carpeta_salida / "extracciones")
    pagado, llamadas = costo_de_llamadas_nuevas(inicio_reloj, carpetas)
    etapas.append({"nombre": "1. Recepción de los Excel y sus FDS", "segundos": round(time.perf_counter() - inicio, 1),
                   "costo_usd": pagado, "llamadas_pagas": llamadas, "costo_primera_vez_usd": round(costo_primera_vez, 6)})
    siguen = [p for p in proveedores_todos if p not in frenados]
    for proveedor_id, motivo in frenados.items():
        print(f"⛔ {proveedor_id} queda afuera de esta corrida: {motivo}")

    # 2. El orquestador: lectura, consolidación, fichas y el único escritor
    inicio_reloj, inicio = time.time(), time.perf_counter()
    codigo = pasos.orquestar(siguen, batch, de_nuevo)
    segundos = round(time.perf_counter() - inicio, 1)
    lectura = _leer(carpeta_salida / "medicion_lectura.json") if codigo == 0 else None
    ruta_fichas = medicion_mas_nueva(carpeta_salida, inicio_reloj) if codigo == 0 else None
    fichas = _leer(ruta_fichas) if ruta_fichas else None
    costo_lectura, llamadas = costo_de_llamadas_nuevas(inicio_reloj, carpetas)  # las de la lectura (las fichas no se guardan ahí)
    costo_fichas = (fichas or {}).get("costo_usd") or 0
    segundos_lectura = (lectura or {}).get("segundos") or 0
    etapas.append({"nombre": "2a. Lectura en paralelo (PDF, FDS, folleto)", "segundos": segundos_lectura,
                   "costo_usd": costo_lectura, "llamadas_pagas": llamadas,
                   "costo_primera_vez_usd": round((lectura or {}).get("costo_usd") or 0, 6)})
    etapas.append({"nombre": "2b. Fichas" + (" por batch" if batch else " (3 fichadores)") + " + escritor",
                   "segundos": round(max(segundos - segundos_lectura, 0), 1), "costo_usd": round(costo_fichas, 6)})
    if codigo != 0:
        frenados["orquestador"] = f"terminó con error (código {codigo}): ver su salida arriba"
    # Semana 7, paso 6: el orquestador termina bien aunque el escritor no haya escrito un proveedor (por ejemplo, sin
    # conexión con Anthropic ninguna tanda arma su ficha). Eso también frena la corrida, con la causa en palabras
    from presentacion import causa_conocida
    causa = causa_conocida(" ".join((fichas or {}).get("tandas_con_problemas") or []))
    for proveedor_id, problemas in ((fichas or {}).get("escritor") or {}).get("frenados", {}).items():
        frenados[proveedor_id] = (f"sus fichas no se escribieron ({len(problemas)} problema(s); las anteriores quedan "
                                  "como estaban)" + (f": {causa}" if causa else ""))

    # 3. Después del escritor: pedidos y acuses (código, gratis)
    inicio = time.perf_counter()
    if pasos.pedidos() != 0:
        frenados["pedidos"] = "pedido_proveedor.py terminó con error"
    hechos = pasos.acuses(excels)
    etapas.append({"nombre": f"3. Pedidos a proveedores + {len(hechos)} acuses", "segundos": round(time.perf_counter() - inicio, 1),
                   "costo_usd": 0.0})
    return etapas, siguen, frenados, fichas, lectura


def _leer(ruta: Path) -> dict | None:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta and ruta.exists() else None


def main():
    argumentos = argparse.ArgumentParser(description="Los 9 proveedores de punta a punta, con costo y tiempo (PAGA).")
    argumentos.add_argument("--batch", action="store_true", help="Las fichas por la Batch API (más barato, más lento).")
    argumentos.add_argument("--de-nuevo", action="store_true", help="Vuelve a leer todo con IA (PDF, FDS, recepción).")
    opciones = argumentos.parse_args()  # con --help termina acá: nunca llega a la API

    nombres = nombres_de_proveedores()
    excels = excel_de_la_entrada()
    print(f"Corrida completa: {len(nombres)} proveedores ({', '.join(nombres)}), {len(excels)} Excel en entrada/, "
          + ("fichas por la Batch API" if opciones.batch else "fichas en tiempo real") + "\n")
    pasos = Pasos()
    etapas, siguen, frenados, fichas, lectura = correr(pasos, opciones.batch, opciones.de_nuevo, list(nombres), excels)

    resultados = _leer(CARPETA_SALIDA / "resultados.json") or {}
    inicio = time.perf_counter()
    evaluacion = evaluar_fichas(resultados)
    etapas.append({"nombre": "4. Evaluador de fichas (casos verificados)", "segundos": round(time.perf_counter() - inicio, 1),
                   "costo_usd": 0.0})
    reporte = armar_reporte(etapas, resultados, fichas, lectura, evaluacion, nombres,
                            {"batch": opciones.batch, "de_nuevo": opciones.de_nuevo})
    reporte["siguieron"], reporte["frenados"] = siguen, frenados
    # Una corrida con frenos no pisa el reporte de la última que salió bien (es el que muestra la pantalla de costos):
    # queda aparte, en corrida_completa_con_problemas.json, con sus motivos
    ruta = RUTA_REPORTE.with_name("corrida_completa_con_problemas.json") if frenados else RUTA_REPORTE
    ruta.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    mostrar_reporte(reporte)  # ya con sus frenos: dice dónde quedó el reporte
    for donde, motivo in frenados.items():
        print(f"⛔ {donde}: {motivo}")
    if frenados:
        sys.exit(1)


if __name__ == "__main__":
    main()
