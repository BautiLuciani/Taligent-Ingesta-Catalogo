"""Corridas y costos (semana 7, paso 5): los números de la última corrida completa y el botón para correr todo de nuevo.

Lo que se muestra sale de lo que ya dejó el sistema, sin calcular nada nuevo:
  - salida/corrida_completa.json: el reporte de correr_todo.py (tiempo y costo pagado por etapa y por proveedor, el
    evaluador de fichas, el caché);
  - salida/costo_por_ficha.json: el costo por ficha en los 3 escenarios (costo_por_ficha.py);
  - salida/consultas/evaluacion.json: las 29 consultas del asistente (evaluar_consultas.py).

"Correr los 9 proveedores" corre python correr_todo.py (o con --batch) en un proceso aparte, como si se escribiera en
la consola, con lo que imprime guardado en salida/web/registros/. Mientras corre, el avance de las fichas sale de las
trazas de los fichadores (igual que en Subir una lista). Al terminar, la pantalla vuelve a leer el reporte nuevo.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from subir_lista import mirar_trazas, tiempo_en_palabras

CARPETA_PROYECTO = Path(__file__).parent
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]

# Cada etapa del reporte, en palabras (por cómo empieza su nombre en correr_todo.py)
ETAPAS = [("1.", "Recibir los Excel y sus fichas de seguridad"), ("2a.", "Leer los PDF, el folleto y las fichas de seguridad"),
          ("2b.", "Armar las {fichas} fichas y guardarlas"), ("3.", "Pedidos a proveedores y acuses de recibo")]


def leer(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    except json.JSONDecodeError:
        return None


def fecha_en_palabras(fecha: str) -> str:
    """"2026-11-18 20:51" -> "18 de noviembre a las 20:51"."""
    try:
        momento = datetime.strptime(fecha, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return fecha or ""
    return f"{momento.day} de {MESES[momento.month - 1]} a las {momento:%H:%M}"


def minutos_redondos(segundos: float) -> str:
    """653 -> "11 minutos"; 1958 -> "33 minutos"; 40 -> "menos de un minuto"."""
    minutos = round(segundos / 60)
    return "menos de un minuto" if minutos < 1 else ("1 minuto" if minutos == 1 else f"{minutos} minutos")


def dolares(valor: float, decimales: int) -> str:
    """0.0453, 3 -> "US$ 0,045", con un espacio que no se corta (el monto nunca queda partido en dos renglones)."""
    return "US$\u00a0" + f"{valor:.{decimales}f}".replace(".", ",")


def datos_de_costos(carpeta: Path) -> dict:
    """Todo lo que muestra la pantalla, desde los 3 archivos. Lo que falta queda en None (la pantalla lo dice)."""
    reporte = leer(carpeta / "corrida_completa.json")
    por_ficha = leer(carpeta / "costo_por_ficha.json")
    consultas = leer(carpeta / "consultas" / "evaluacion.json")
    datos = {"hay_corrida": reporte is not None}
    if reporte:
        fichas = reporte.get("fichas") or 0
        etapas, maximo = [], max((e.get("segundos") or 0) for e in reporte.get("etapas", [])) or 1
        for prefijo, titulo in ETAPAS:
            etapa = next((e for e in reporte.get("etapas", []) if e.get("nombre", "").startswith(prefijo)), None)
            if etapa is None:
                continue
            segundos, costo = etapa.get("segundos") or 0, etapa.get("costo_usd") or 0
            reusado = prefijo == "2a." and costo == 0 and segundos < 1
            etapas.append({"titulo": titulo.format(fichas=fichas),
                           "tiempo": "0 s, ya estaban leídos" if reusado else tiempo_en_palabras(segundos),
                           "costo": "US$ 0" if costo == 0 else dolares(costo, 3),
                           "ancho": round(max(100 * segundos / maximo, 1), 1)})
        proveedores = reporte.get("proveedores", [])
        maximo_costo = max((p.get("costo_fichas_usd") or 0) for p in proveedores) if proveedores else 1
        datos.update({
            "fichas": fichas,
            "tiempo": tiempo_en_palabras(reporte.get("segundos") or 0),
            "costo": dolares(reporte.get("costo_usd") or 0, 2),
            "por_ficha": dolares(reporte.get("costo_por_ficha_usd") or 0, 4),
            "fecha": fecha_en_palabras(reporte.get("fecha")),
            "modo": "por lote" if (reporte.get("opciones") or {}).get("batch") else "en el momento",
            "etapas": etapas,
            "proveedores": [{"nombre": p["nombre"], "fichas": p["fichas"], "costo": dolares(p.get("costo_fichas_usd") or 0, 3),
                             "por_ficha": dolares(p.get("costo_por_ficha_usd") or 0, 4),
                             "ancho": round(100 * (p.get("costo_fichas_usd") or 0) / (maximo_costo or 1))} for p in proveedores],
            "evaluador": reporte.get("evaluador"),
            "cache": round(100 * reporte["cache_leido"]) if reporte.get("cache_leido") is not None else None,
            "cantidad_proveedores": len(proveedores),
            "frenados": reporte.get("frenados") or {},
        })
    if por_ficha:
        escenarios, segundos = por_ficha.get("por_ficha_usd", {}), por_ficha.get("segundos", {})
        totales = por_ficha.get("escenarios_usd", {})
        datos["por_ficha_escenarios"] = [
            {"titulo": "Sin memoria de lo ya leído", "valor": dolares(escenarios.get("tiempo_real_sin_cache", 0), 4)},
            {"titulo": "Reusando lo ya leído", "valor": dolares(escenarios.get("tiempo_real_con_cache", 0), 4)},
            {"titulo": "Por lote, reusando", "valor": dolares(escenarios.get("batch_con_cache", 0), 4), "mejor": True},
        ]
        datos["opciones_de_corrida"] = [
            {"clave": "ahora", "titulo": "Ahora",
             "detalle": f"Unos {minutos_redondos(segundos.get('tiempo_real', 0))}, cerca de {dolares(totales.get('tiempo_real_con_cache', 0), 2)}"},
            {"clave": "lote", "titulo": "Por lote, más barato",
             "detalle": f"Unos {minutos_redondos(segundos.get('batch', 0))}, cerca de {dolares(totales.get('batch_con_cache', 0), 2)}"},
        ]
    if consultas:
        datos["consultas"] = {"bien": consultas.get("bien"), "total": consultas.get("total"),
                              "por_consulta": dolares(consultas.get("costo_por_consulta_usd") or 0, 3)}
    return datos


class CorridaCompleta:
    """python correr_todo.py en un proceso aparte, una a la vez. comando: lo que se corre (las pruebas ponen otro)."""

    def __init__(self, carpeta_salida: Path, comando=None):
        self.carpeta_salida = carpeta_salida
        self.comando = comando or (lambda lote: [sys.executable, "correr_todo.py"] + (["--batch"] if lote else []))
        self._candado = threading.Lock()
        self.estado = {"estado": "quieta"}
        self.inicio = None
        self._proceso = None

    def corriendo(self) -> bool:
        return self.estado.get("estado") == "corriendo"

    def empezar(self, lote: bool, total_fichas: int):
        with self._candado:
            if self.corriendo():
                raise RuntimeError("Ya hay una corrida completa en marcha.")
            self.inicio = time.time()
            self.estado = {"estado": "corriendo", "lote": lote, "total": total_fichas, "hechas": 0, "segundos": 0}
        ruta_log = self.carpeta_salida / "web" / "registros" / f"{datetime.now():%Y%m%d_%H%M%S}_corrida_completa.log"
        ruta_log.parent.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._trabajar, args=(lote, ruta_log), daemon=True, name="corrida_completa").start()

    def _trabajar(self, lote: bool, ruta_log: Path):
        desde = self.inicio - 1
        entorno = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            with open(ruta_log, "w", encoding="utf-8") as log:
                proceso = subprocess.Popen(self.comando(lote), cwd=CARPETA_PROYECTO, stdout=log, stderr=subprocess.STDOUT, env=entorno)
                self._proceso = proceso
                while proceso.poll() is None:
                    self._mirar(desde)
                    time.sleep(1)
                codigo = proceso.returncode
        except OSError as error:
            self.estado = {**self.estado, "estado": "problema", "motivo": f"No se pudo arrancar la corrida: {error}"}
            return
        self._mirar(desde)
        segundos = time.time() - self.inicio
        if codigo == 0:
            self.estado = {**self.estado, "estado": "lista", "segundos": round(segundos, 1),
                           "texto": f"Terminó en {tiempo_en_palabras(segundos)}. Los números de abajo ya son los de esta corrida."}
        else:
            from presentacion import causa_conocida
            # con frenos, correr_todo.py deja su reporte aparte (el de la última corrida buena no se pisa)
            reporte = leer(self.carpeta_salida / "corrida_completa_con_problemas.json") or {}
            de_esta_corrida = (reporte.get("fecha") or "") >= f"{datetime.fromtimestamp(self.inicio):%Y-%m-%d %H:%M}"
            frenados = (reporte.get("frenados") or {}) if de_esta_corrida else {}
            impreso = ruta_log.read_text(encoding="utf-8", errors="replace") if ruta_log.exists() else ""
            causa = causa_conocida(" ".join(frenados.values())) or causa_conocida(impreso)
            detalle = f"El detalle quedó en salida/web/registros/{ruta_log.name}."
            if causa:
                motivo = f"{causa} Los números de abajo siguen siendo los de la última corrida que salió bien."
            elif frenados:
                motivo = "; ".join(f"{donde}: {texto}" for donde, texto in frenados.items()) + ". " + detalle
            else:
                motivo = f"correr_todo.py terminó con error (código {codigo}). {detalle}"
            self.estado = {**self.estado, "estado": "problema", "segundos": round(segundos, 1), "motivo": motivo}

    def _mirar(self, desde: float):
        try:
            registradas, _ = mirar_trazas(self.carpeta_salida / "trazas", desde)
        except OSError:
            return
        self.estado = {**self.estado, "hechas": len(registradas), "segundos": round(time.time() - self.inicio, 1)}

    def estado_publico(self) -> dict:
        estado = dict(self.estado)
        if estado.get("estado") == "corriendo":
            estado["segundos"] = round(time.time() - self.inicio, 1)
        if "segundos" in estado:
            estado["tiempo"] = tiempo_en_palabras(estado["segundos"])
        return estado
