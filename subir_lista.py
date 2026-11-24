"""Subir una lista desde la interfaz (semana 7, paso 2): el mismo camino que la bandeja, con el avance a la vista.

No agrega lógica de negocio. Corre vigilar.procesar (recepción → fichas de seguridad → orquestador → escritor →
pedido) con los MISMOS pasos de la bandeja (vigilar.Pasos), envueltos en PasosConAvance: cada paso, al empezar y al
terminar, anota en la Corrida qué está pasando, con palabras para una persona que no conoce el sistema.

  - El archivo se guarda en entrada/<carpeta del proveedor>/ (y sus fichas de seguridad, si vienen, en
    entrada/<carpeta>/fichas_de_seguridad/), como si lo hubieran dejado en la bandeja.
  - A diferencia de la bandeja, se procesa aunque ya se haya procesado antes (la persona lo pidió): la recepción y las
    fichas de seguridad reusan lo ya leído si el archivo es el mismo (no se pagan de nuevo); las fichas se vuelven a
    armar (eso sí se paga). Después se anota en salida/bandeja.json con su huella, igual que la bandeja.
  - El avance de las fichas sale de las trazas que escriben los fichadores (salida/trazas/paralelo_*/): cada
    registrar_ficha aceptado es una ficha armada.
  - Una corrida que termina bien se graba (salida/web/corrida_de_ejemplo.json): es el plan B de la demo, "Ver una
    corrida de ejemplo", que la vuelve a mostrar tal cual pasó, sin gastar nada.
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_DATA = CARPETA_PROYECTO / "Data"
RUTA_PROVEEDORES_CSV = CARPETA_DATA / "proveedores" / "proveedores.csv"

TITULOS_DE_PASOS = [
    ("Recibimos el archivo", "Vamos a ver qué trae la lista."),
    ("Entendimos cómo está armado", "Vamos a ver qué columna es cada dato."),
    ("Leímos las fichas de seguridad", "Si trae fichas de seguridad, las leemos."),
    ("Armamos las fichas", "Una ficha por producto, con la fuente de cada dato."),
    ("Controlamos y guardamos", "Ningún dato se guarda sin verificar."),
]
RECIBIR, ENTENDER, FDS, FICHAS, GUARDAR = range(5)

NOMBRE_DEL_DATO = {"descripcion": "Nombre del producto", "ean": "Código de barras", "precio": "Precio de costo",
                   "contenido": "Contenido", "unidad": "Unidad"}
PELIGROS = {"aerosol_inflamable": "aerosol inflamable", "liquido_inflamable": "líquido inflamable",
            "corrosivo": "corrosivo", "no_peligroso": "no peligroso"}
NUMEROS = {1: "Un", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco", 6: "Seis", 7: "Siete", 8: "Ocho", 9: "Nueve"}
SEGUNDOS_ENTRE_MIRADAS = 0.7  # cada cuánto se miran las trazas mientras se arman las fichas


# --- Los proveedores, para el desplegable ---

def que_mando(archivos: str) -> str:
    """Lo que mandó un proveedor, en palabras, desde la columna archivos de proveedores.csv: "PDF y Excel",
    "Excel y 2 fichas de seguridad", "Planilla CSV"."""
    nombres = [a.strip() for a in archivos.split("|") if a.strip()]
    fds = sum(1 for n in nombres if n.startswith("fichas_de_seguridad/"))
    partes = []
    for nombre in nombres:
        if nombre.startswith("fichas_de_seguridad/"):
            continue
        tipo = {"pdf": "PDF", "xlsx": "Excel", "csv": "Planilla CSV", "txt": "Mail"}.get(nombre.rsplit(".", 1)[-1].lower(), "Archivo")
        if tipo not in partes:
            partes.append(tipo)
    if fds:
        partes.append(f"{fds} {'ficha' if fds == 1 else 'fichas'} de seguridad")
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def proveedores_a_mano() -> set[str]:
    """Los proveedores configurados a mano en servidor_mcp.py (PDF, CSV y mail de las semanas 1 a 3): no entran por
    la bandeja, porque el recepcionista sabe armar la receta de un Excel, no la de otros formatos."""
    import servidor_mcp  # recién acá: tarda un par de segundos en cargar
    return set(servidor_mcp.PROVEEDORES_A_MANO)


def proveedores_para_subir(a_mano: set[str] | None = None, ruta: Path = RUTA_PROVEEDORES_CSV) -> list[dict]:
    """Los 9 proveedores para el desplegable: los que mandan Excel se pueden elegir; los demás, apagados con el motivo."""
    a_mano = proveedores_a_mano() if a_mano is None else a_mano
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    return [{"id": f["proveedor_id"], "nombre": f["nombre"], "carpeta": f["carpeta"],
             "habilitado": f["proveedor_id"] not in a_mano,
             "archivos": [a.strip().rsplit("/", 1)[-1] for a in f["archivos"].split("|") if a.strip()],
             "mando": que_mando(f["archivos"]),
             "detalle": que_mando(f["archivos"]) if f["proveedor_id"] not in a_mano
             else f"{que_mando(f['archivos'])}: todavía no se puede subir desde acá"}
            for f in filas]


def sugerir_proveedor(nombre_archivo: str, proveedores: list[dict]) -> str | None:
    """Si el nombre del archivo es uno de los que ese proveedor ya mandó (proveedores.csv), se lo sugiere. Solo
    sugiere: la persona confirma (el nombre de un archivo es una pista, no una prueba)."""
    for proveedor in proveedores:
        if proveedor["habilitado"] and nombre_archivo in proveedor["archivos"]:
            return proveedor["id"]
    return None


# --- Formatos para la pantalla ---

def tiempo_en_palabras(segundos: float) -> str:
    """95 -> "1 min 35 s"; 42 -> "42 s"."""
    segundos = int(round(segundos))
    minutos, resto = divmod(segundos, 60)
    return f"{minutos} min {resto} s" if minutos else f"{resto} s"


def costo_en_palabras(costo: float) -> str:
    """0.0214 -> "US$ 0,021"; 0.38 -> "US$ 0,38"."""
    decimales = 3 if costo < 0.1 else 2
    return "US$ " + f"{costo:.{decimales}f}".replace(".", ",")


def numero(n: int) -> str:
    return NUMEROS.get(n, str(n))


# --- Lo que se dice al terminar cada paso ---

def linea_de_recepcion(recepcion: dict, tabla: dict, ejemplo: tuple | None) -> str:
    """Paso 2 terminado: cuántos productos, la moneda y, si hubo que convertir unidades, un ejemplo real."""
    productos = len(tabla["filas"])
    partes = [f"Una hoja con {productos} {'producto' if productos == 1 else 'productos'}."]
    partes.append("Precios en dólares, sin convertir." if recepcion["receta"]["moneda"] == "USD" else "Precios en pesos.")
    if ejemplo and f"{ejemplo[2]}{ejemplo[3]}" not in str(ejemplo[0]).upper().replace(" ", ""):
        partes.append(f"Tamaños como «{ejemplo[0]}», que pasamos a {ejemplo[2]} {ejemplo[3]}.")
    return " ".join(partes)


def linea_de_fds(fds: dict, codigos_de_la_lista: set[str], viejas: int) -> str:
    """Paso 3 terminado: qué dicen las fichas de seguridad, contado por producto de ESTA lista (una FDS puede cubrir
    varios códigos, y algunos pueden no estar en la lista)."""
    por_peligro: dict[str, set[str]] = {}
    for ficha in fds.get("fichas", []):
        if ficha.get("peligro_deposito"):
            cubiertos = {c for c in ficha.get("codigos") or [] if c in codigos_de_la_lista}
            por_peligro.setdefault(ficha["peligro_deposito"], set()).update(cubiertos)
    leidas = len(fds.get("fichas", []))
    frases = [f"{numero(len(c))} {'producto va' if len(c) == 1 else 'productos van'} al depósito como {PELIGROS.get(p, p)}."
              for p, c in por_peligro.items() if c]
    texto = " ".join(frases) or f"{numero(leidas)} {'ficha leída' if leidas == 1 else 'fichas leídas'}: ningún producto de la lista es peligroso."
    if viejas:
        texto += " (Una ya la había mandado antes.)" if viejas == 1 else f" ({numero(viejas)} ya las había mandado antes.)"
    return texto


# --- El avance de las fichas, desde las trazas de los fichadores ---

def mirar_trazas(carpeta_trazas: Path, desde: float) -> tuple[set[str], set[str]]:
    """(fichas registradas, fichas en una tanda que todavía no terminó), de las trazas escritas después de 'desde'.

    Lee las trazas de las carpetas paralelo_* nuevas. Una línea a medio escribir (el fichador la está agregando) se
    saltea: se lee entera en la próxima mirada.
    """
    registradas, en_curso = set(), set()
    if not carpeta_trazas.is_dir():
        return registradas, en_curso
    for carpeta in carpeta_trazas.glob("paralelo_*"):
        if not carpeta.is_dir() or carpeta.stat().st_mtime < desde:
            continue
        for traza in carpeta.glob("*.jsonl"):
            esperados, terminada = [], False
            for renglon in traza.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    evento = json.loads(renglon)
                except json.JSONDecodeError:
                    continue
                if evento.get("evento") == "inicio_tanda":
                    esperados = evento.get("esperados") or []
                elif evento.get("evento") == "fin_tanda":
                    terminada = True
                elif (evento.get("evento") == "tool_result" and evento.get("tool") == "registrar_ficha"
                      and not evento.get("is_error")):
                    item = registrado_en(evento.get("content", ""))
                    if item:
                        registradas.add(item)
            if not terminada:
                en_curso.update(item for item in esperados if item not in registradas)
    return registradas, en_curso - registradas


def registrado_en(contenido: str) -> str | None:
    """El ítem que devolvió registrar_ficha ({"registrado": "P08:IN7003", ...})."""
    try:
        return json.loads(contenido).get("registrado")
    except (json.JSONDecodeError, AttributeError):
        encontrado = re.search(r'"registrado"\s*:\s*"([^"]+)"', contenido or "")
        return encontrado.group(1) if encontrado else None


# --- El resumen final ---

def columnas_entendidas(recepcion: dict, tabla: dict, consolidado: dict | None) -> tuple[list[dict], int | None]:
    """La tabla "Así entendimos el archivo": cada columna del Excel, qué dato es para Ceibo y el ejemplo del primer
    producto (con la cuenta que hizo el código, si hizo alguna). Devuelve (columnas, fila del ejemplo)."""
    receta = recepcion["receta"]
    if not tabla["filas"]:
        return [], None
    primera = tabla["filas"][0]
    calculado = ((consolidado or {}).get("filas") or [{}])[0].get("calculado", {}) if consolidado else {}
    columnas = []
    columna_codigo = next((c for c in tabla["columnas"] if c not in primera["original"]), None)
    dato_de = {}  # columna del archivo -> el primer dato que es para Ceibo (el contenido con su unidad: una sola fila)
    for dato, columna in receta["campos"].items():
        dato_de.setdefault(columna, dato)
    for columna in tabla["columnas"]:  # en el orden del archivo, como lo ve la persona que lo abre
        valor = primera["original"].get(columna)
        ejemplo = "" if valor is None else str(valor)
        if columna == columna_codigo:
            columnas.append({"columna": columna, "dato": "Código del proveedor", "ejemplo": primera["codigo"], "usa": True})
            continue
        dato = dato_de.get(columna)
        if dato is None:
            columnas.append({"columna": columna, "dato": "No se usa", "ejemplo": ejemplo, "usa": False})
            continue
        separadas = receta["campos"].get("unidad") not in (None, receta["campos"].get("contenido"))
        if dato == "contenido" and not separadas and calculado.get("contenido") is not None:
            convertido = f"{calculado['contenido']} {calculado.get('unidad') or ''}".strip()
            if convertido.replace(" ", "") not in ejemplo.upper().replace(" ", ""):
                ejemplo += f", que son {convertido}"
        if dato == "unidad" and separadas and calculado.get("unidad") and ejemplo.upper().strip(". ") != calculado["unidad"]:
            ejemplo += f", que pasa a {calculado['unidad']}"
        if dato == "ean" and calculado.get("gtin") and ejemplo and calculado["gtin"] != ejemplo and len(ejemplo) == 12:
            ejemplo += ", completado a 13 dígitos"
        if dato == "precio" and receta.get("moneda") == "USD":
            ejemplo += " dólares, sin convertir"
        columnas.append({"columna": columna, "dato": NOMBRE_DEL_DATO.get(dato, dato), "ejemplo": ejemplo, "usa": True})
    return columnas, primera["fuente"].get("fila")


def resumen_del_proveedor(proveedor_id: str, nombre: str, resultados: dict, hay_pedido: bool) -> dict:
    """El título y los números de la tarjeta "Listo", con lo que escribió el escritor (resultados.json)."""
    suyos = [r for r in resultados.values() if r.get("item_id", "").startswith(f"{proveedor_id}:")]
    alta = sum(1 for r in suyos if r["estado"] == "lista_para_alta")
    dup = sum(1 for r in suyos if r["estado"] == "duplicado")
    rev = sum(1 for r in suyos if r["estado"] == "a_revision")
    total = len(suyos)
    if total and alta == total:
        titulo = f"Los {total} productos de {nombre} están listos para dar de alta"
        bajada = "Ninguno estaba ya en el catálogo y no hay nada que pedirle al proveedor." if not hay_pedido else \
            "Ninguno estaba ya en el catálogo."
    else:
        titulo = f"Listas las {total} fichas de {nombre}"
        partes = []
        if alta:
            partes.append(f"{alta} para dar de alta")
        if dup:
            partes.append(f"{dup} ya {'estaba' if dup == 1 else 'estaban'} en el catálogo")
        if rev:
            partes.append(f"{rev} {'espera' if rev == 1 else 'esperan'} que lo{'' if rev == 1 else 's'} mires")
        bajada = (", ".join(partes[:-1]) + " y " + partes[-1] if len(partes) > 1 else (partes[0] if partes else "")).capitalize() + "."
        if hay_pedido:
            bajada += " El pedido al proveedor ya está armado."
    return {"titulo": titulo, "bajada": bajada, "total": total, "alta": alta, "duplicado": dup, "a_revision": rev}


# --- La corrida: el estado que ve la pantalla ---

class Corrida:
    """Lo que está pasando con una lista subida. La pantalla la pide cada medio segundo (estado_publico).
    Todo cambio pasa por _cambiar, que además lo graba con su segundo (para el plan B)."""

    def __init__(self, archivo: str, proveedor: dict, fds_nuevas: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.inicio = time.time()
        self._candado = threading.Lock()
        self._estado = {
            "id": self.id, "archivo": archivo, "proveedor_id": proveedor["id"], "proveedor": proveedor["nombre"],
            "fds_nuevas": fds_nuevas, "estado": "corriendo", "ejemplo": False, "grabada": None,
            "pasos": [{"titulo": t, "linea": p, "estado": "pendiente"} for t, p in TITULOS_DE_PASOS],
            "productos": [], "hechas": 0, "total": None, "ahora": "Preparando los productos…",
            "resultado": None, "problema": None, "t": 0.0,
        }
        self.grabacion: list[dict] = []
        self._grabar()

    def _grabar(self):
        self._estado["t"] = round(time.time() - self.inicio, 1)
        self.grabacion.append(json.loads(json.dumps(self._estado)))

    def _cambiar(self, **cambios):
        with self._candado:
            self._estado.update(cambios)
            self._grabar()

    def estado_publico(self) -> dict:
        with self._candado:
            self._estado["t"] = round(time.time() - self.inicio, 1)
            return json.loads(json.dumps(self._estado))

    def paso(self, indice: int, estado: str, linea: str | None = None):
        with self._candado:
            paso = self._estado["pasos"][indice]
            paso["estado"] = estado
            if linea is not None:
                paso["linea"] = linea
            self._grabar()

    def productos(self, filas: list[dict], proveedor_id: str, columna_descripcion: str | None):
        """Un cuadradito por producto, con su descripción tal cual el Excel (se ve al pasar el mouse)."""
        self._cambiar(productos=[{"id": f"{proveedor_id}:{f['codigo']}", "codigo": f["codigo"],
                                  "descripcion": str(f["original"].get(columna_descripcion) or f["codigo"]),
                                  "estado": "pendiente"} for f in filas],
                      total=len(filas))

    def avance(self, registradas: set[str], en_curso: set[str]):
        with self._candado:
            cambio = False
            for producto in self._estado["productos"]:
                nuevo = "hecho" if producto["id"] in registradas else ("actual" if producto["id"] in en_curso else "pendiente")
                if producto["estado"] != nuevo:
                    producto["estado"], cambio = nuevo, True
            hechas = sum(1 for p in self._estado["productos"] if p["estado"] == "hecho")
            faltan = (self._estado["total"] or 0) - hechas
            if faltan <= 0:
                ahora = f"Controlando las {self._estado['total']} fichas antes de guardarlas…"
            elif en_curso:
                ahora = f"Ahora: {len(en_curso)} {'ficha' if len(en_curso) == 1 else 'fichas'} en preparación, " \
                        f"en tandas que trabajan a la vez."
            else:
                ahora = "Preparando las tandas de fichas…"
            if cambio or hechas != self._estado["hechas"] or ahora != self._estado["ahora"]:
                self._estado.update(hechas=hechas, ahora=ahora)
                self._grabar()

    def terminar(self, resultado: dict):
        self._cambiar(estado="listo", resultado=resultado, ahora="")

    def fallar(self, titulo: str, detalle: list[str], paso: int | None = None):
        with self._candado:
            if paso is None:  # se frenó en el paso que estaba en curso
                paso = next((i for i, p in enumerate(self._estado["pasos"]) if p["estado"] == "actual"), None)
            if paso is not None:
                self._estado["pasos"][paso]["estado"] = "error"
                self._estado["pasos"][paso]["linea"] = "Acá se frenó: el motivo está abajo."
                for siguiente in self._estado["pasos"][paso + 1:]:
                    siguiente["estado"] = "pendiente"
            self._estado.update(estado="problema", problema={"titulo": titulo, "detalle": detalle}, ahora="")
            self._grabar()


class PasosConAvance:
    """Los pasos reales de la bandeja (vigilar.Pasos), con el avance anotado en la corrida. No cambian qué hace cada
    paso: solo avisan cuándo empieza y cómo terminó."""

    def __init__(self, pasos, corrida: Corrida, carpeta_trazas: Path, proveedor: dict, ruta_log: Path | None = None):
        self.pasos, self.corrida, self.carpeta_trazas, self.proveedor = pasos, corrida, carpeta_trazas, proveedor
        self.ruta_log = ruta_log
        self.recepcion = None
        self.tabla = None
        self.fds_leidas = False
        self.fds_viejas = 0

    def recibir(self, ruta: Path) -> dict:
        from acuse import ejemplo_de_contenido
        from lector_excel import leer_tabla_excel
        self.corrida.paso(ENTENDER, "actual")
        recepcion = self.pasos.recibir(ruta)
        self.recepcion = recepcion
        if recepcion.get("receta") is None:
            return recepcion  # procesar lo informa como "no_entro"; la corrida lo muestra con sus motivos
        self.tabla = leer_tabla_excel(ruta, recepcion["receta"]["hoja"])
        try:
            ejemplo = ejemplo_de_contenido(self.tabla["filas"], recepcion["receta"])
        except Exception:
            ejemplo = None
        self.corrida.productos(self.tabla["filas"], self.proveedor["id"], recepcion["receta"]["campos"].get("descripcion"))
        self.corrida.paso(ENTENDER, "hecho", linea_de_recepcion(recepcion, self.tabla, ejemplo))
        return recepcion

    def leer_fds(self, carpeta: Path) -> dict:
        self.corrida.paso(FDS, "actual")
        fds = self.pasos.leer_fds(carpeta)
        self.fds_leidas = True
        problemas = [p for ficha in fds.get("fichas", []) for p in ficha.get("problemas", [])]
        if not problemas:
            codigos = {f["codigo"] for f in (self.tabla or {}).get("filas", [])}
            self.corrida.paso(FDS, "hecho", linea_de_fds(fds, codigos, self.fds_viejas))
        return fds

    def fichar(self, proveedor_id: str) -> int:
        if not self.fds_leidas:
            self.corrida.paso(FDS, "hecho", "Este proveedor no mandó fichas de seguridad.")
        self.corrida.paso(FICHAS, "actual")
        desde = time.time() - 1
        terminar = threading.Event()

        def mirar():
            while not terminar.wait(SEGUNDOS_ENTRE_MIRADAS):
                try:
                    self.corrida.avance(*mirar_trazas(self.carpeta_trazas, desde))
                except OSError:
                    pass

        hilo = threading.Thread(target=mirar, daemon=True)
        hilo.start()
        try:
            codigo = self.pasos.fichar(proveedor_id)
        finally:
            terminar.set()
            hilo.join(timeout=5)
        self.corrida.avance(*mirar_trazas(self.carpeta_trazas, desde))
        estado = self.corrida.estado_publico()
        hechas = sum(1 for p in estado["productos"] if p["estado"] == "hecho")
        if codigo == 0 and hechas >= (estado["total"] or 0):  # si faltó alguna, el escritor no escribe: lo dice el paso siguiente
            self.corrida.paso(FICHAS, "hecho", linea_de_fichas(estado["total"] or 0))
            self.corrida.paso(GUARDAR, "actual")
        return codigo

    def fichas_escritas(self, proveedor_id: str):
        return self.pasos.fichas_escritas(proveedor_id)

    def pedir(self, proveedor_id: str) -> int:
        return self.pasos.pedir(proveedor_id)

    def acusar(self, ruta: Path, registro: dict) -> Path:
        return self.pasos.acusar(ruta, registro)


class PasosDeLaWeb:
    """vigilar.Pasos con una diferencia: lo que imprimen el orquestador y el pedido va a un archivo de registro
    (salida/web/registros/), en UTF-8, en vez de a la consola del servidor. El resto, igual que la bandeja."""

    def __init__(self, ruta_log: Path):
        import vigilar
        self._pasos = vigilar.Pasos()
        self.ruta_log = ruta_log
        ruta_log.parent.mkdir(parents=True, exist_ok=True)

    def _correr(self, *comando: str) -> int:
        import os
        entorno = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        with open(self.ruta_log, "a", encoding="utf-8") as log:
            log.write(f"\n$ {' '.join(comando)}\n")
            log.flush()
            return subprocess.run([sys.executable, *comando], cwd=CARPETA_PROYECTO, stdout=log, stderr=subprocess.STDOUT,
                                  env=entorno).returncode

    def recibir(self, ruta):
        return self._pasos.recibir(ruta)

    def leer_fds(self, carpeta):
        return self._pasos.leer_fds(carpeta)

    def fichar(self, proveedor_id):
        self._pasos.desde_fichar = time.time()  # para saber si el escritor escribió en esta corrida (vigilar.Pasos)
        return self._correr("orquestador.py", "--fichas", "--proveedores", proveedor_id)

    def pedir(self, proveedor_id):
        return self._correr("pedido_proveedor.py", proveedor_id)

    def fichas_escritas(self, proveedor_id):
        return self._pasos.fichas_escritas(proveedor_id)

    def acusar(self, ruta, registro):
        return self._pasos.acusar(ruta, registro)


def linea_de_fichas(total: int) -> str:
    return f"Las {total} fichas, cada dato con el archivo y el lugar de donde sale."


# --- Por qué no entró, en palabras ---

def detalle_del_problema(resultado: dict) -> tuple[str, list[str], int | None]:
    """(título, renglones, paso donde se frenó) de una corrida que no terminó bien, con lo que dijo vigilar.procesar."""
    estado = resultado.get("estado")
    if estado == "no_entro":
        renglones = [f"No se cumplió: {p[:1].lower()}{p[1:]}" + ("" if p.endswith(".") else ".")
                     for p in resultado.get("problemas") or [] if p]
        return ("No pudimos entender cómo está armada esta lista",
                (renglones or ["La receta no pasó los controles."])
                + ["Ceibo no adivina: si algo no cierra, el archivo no entra y queda el motivo en el acuse."], ENTENDER)
    if estado == "frenado" and "FDS" in (resultado.get("motivo") or ""):
        return ("Una ficha de seguridad no se pudo leer bien", list(resultado.get("problemas") or [resultado["motivo"]]), FDS)
    if estado == "frenado":
        return ("Las fichas no se guardaron", [resultado.get("motivo", "")], GUARDAR)
    if estado == "error":
        return ("Algo falló mientras se procesaba la lista", [resultado.get("motivo", "")], None)
    return ("La lista no entró", [resultado.get("motivo") or estado or ""], RECIBIR)


# --- Correr una lista de punta a punta ---

def correr_lista(corrida: Corrida, ruta_excel: Path, pasos, proveedor: dict, *, carpeta_trazas: Path,
                 ruta_registro: Path, ruta_resultados: Path, carpeta_pedidos: Path, carpeta_consolidado: Path,
                 carpeta_salida: Path, ruta_grabacion: Path | None, fds_viejas: int = 0) -> dict:
    """Corre la lista con vigilar.procesar y deja el final en la corrida. Devuelve el registro de la bandeja."""
    import vigilar
    from correr_todo import costo_de_llamadas_nuevas, medicion_mas_nueva
    from recepcion import ruta_relativa

    con_avance = PasosConAvance(pasos, corrida, carpeta_trazas, proveedor)
    con_avance.fds_viejas = fds_viejas
    desde = corrida.inicio - 1
    try:
        resultado = vigilar.procesar(ruta_excel, con_avance)
    except Exception as error:  # algo inesperado: se informa en pantalla y se anota, como hace la bandeja
        resultado = {"estado": "error", "proveedor_id": proveedor["id"], "motivo": f"{type(error).__name__}: {error}"}

    registro = {"huella": vigilar.huella_del_archivo(ruta_excel), "fecha": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                **resultado}
    anotado = json.loads(ruta_registro.read_text(encoding="utf-8")) if ruta_registro.exists() else {}
    try:
        clave = ruta_relativa(ruta_excel)
    except ValueError:
        clave = str(ruta_excel)
    anotado[clave] = registro
    ruta_registro.parent.mkdir(parents=True, exist_ok=True)
    ruta_registro.write_text(json.dumps(anotado, ensure_ascii=False, indent=2), encoding="utf-8")
    try:  # el acuse informa; si falla, lo procesado ya está anotado
        pasos.acusar(ruta_excel, registro)
    except Exception:
        pass

    if resultado.get("estado") != "procesado":
        from presentacion import causa_conocida
        ruta_log = getattr(pasos, "ruta_log", None)
        impreso = ruta_log.read_text(encoding="utf-8", errors="replace") if ruta_log and ruta_log.exists() else ""
        causa = causa_conocida(resultado.get("motivo")) or causa_conocida(impreso)
        if causa:  # no es la lista: es la conexión con Anthropic (o el .env). Las fichas de antes no se tocaron
            corrida.fallar("No se pudo hablar con Anthropic", [causa])  # el subtítulo ya dice que no se guardó nada
            return registro
        titulo, renglones, paso = detalle_del_problema(resultado)
        corrida.fallar(titulo, [r for r in renglones if r], paso)
        return registro

    segundos = time.time() - corrida.inicio
    costo_lecturas, _ = costo_de_llamadas_nuevas(desde, (carpeta_salida / "recepcion", carpeta_salida / "extracciones"))
    medicion = medicion_mas_nueva(carpeta_salida, desde)
    costo_fichas = json.loads(medicion.read_text(encoding="utf-8")).get("costo_usd", 0.0) if medicion else 0.0
    costo = round(costo_lecturas + costo_fichas, 6)
    resultados = json.loads(ruta_resultados.read_text(encoding="utf-8")) if ruta_resultados.exists() else {}
    hay_pedido = (carpeta_pedidos / f"pedido_{proveedor['id']}.md").exists()
    ruta_consolidado = carpeta_consolidado / f"{proveedor['id']}.json"
    consolidado = json.loads(ruta_consolidado.read_text(encoding="utf-8")) if ruta_consolidado.exists() else None
    columnas, fila_ejemplo = columnas_entendidas(con_avance.recepcion, con_avance.tabla, consolidado)
    resumen = resumen_del_proveedor(proveedor["id"], proveedor["nombre"], resultados, hay_pedido)
    corrida.paso(FICHAS, "hecho", linea_de_fichas(sum(1 for k in resultados if k.split(":")[0] == proveedor["id"])))
    corrida.paso(GUARDAR, "hecho", "Todo controlado y guardado." + (" El pedido al proveedor ya está armado." if hay_pedido else ""))
    corrida.terminar({**resumen, "columnas": columnas, "fila_ejemplo": fila_ejemplo, "segundos": round(segundos, 1),
                      "costo_usd": costo,
                      "tiempo_y_costo": f"Tardó {tiempo_en_palabras(segundos)} y costó {costo_en_palabras(costo)}",
                      "fecha": f"{datetime.now():%d/%m}"})
    if ruta_grabacion:
        ruta_grabacion.parent.mkdir(parents=True, exist_ok=True)
        ruta_grabacion.write_text(json.dumps({"fecha": f"{datetime.now():%d/%m}", "estados": corrida.grabacion},
                                             ensure_ascii=False), encoding="utf-8")
    return registro


# --- La mesa de entradas de la web: subidas y corridas ---

def contenido_que_no_es(nombre: str, extension: str, contenido: bytes) -> str | None:
    """Si lo que llegó no es lo que dice su extensión (un .xls renombrado, un archivo dañado o a medio bajar), el
    motivo en palabras; si está bien, None. Se mira antes de guardar: un archivo roto no llega a la recepción."""
    import io
    import zipfile
    if extension == "pdf":
        return None if contenido.lstrip()[:5] == b"%PDF-" else f"{nombre} no es un PDF que se pueda abrir."
    if contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # el formato viejo de Excel (.xls) o un Excel con contraseña
        return (f"{nombre} está en el formato viejo de Excel o tiene contraseña. Abrilo en Excel y guardalo como "
                "«Libro de Excel (.xlsx)», sin contraseña.")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            if "xl/workbook.xml" in libro.namelist():
                return None
    except zipfile.BadZipFile:
        pass
    return f"{nombre} no es un Excel que se pueda abrir (puede estar dañado o a medio bajar)."


class MesaDeEntradas:
    """Guarda los archivos que llegan desde el navegador y lanza una corrida a la vez (en un hilo aparte)."""

    def __init__(self, carpeta_proyecto: Path = CARPETA_PROYECTO, carpeta_entrada: Path | None = None,
                 fabrica_de_pasos=None, a_mano: set[str] | None = None):
        import vigilar
        self.carpeta_salida = carpeta_proyecto / "salida"
        self.carpeta_entrada = carpeta_entrada or vigilar.CARPETA_ENTRADA
        self.carpeta_web = self.carpeta_salida / "web"
        self.carpeta_subidas = self.carpeta_web / "subidas"
        self.ruta_grabacion = self.carpeta_web / "corrida_de_ejemplo.json"
        self.fabrica_de_pasos = fabrica_de_pasos or (lambda ruta_log: PasosDeLaWeb(ruta_log))
        self._a_mano = a_mano
        self._proveedores = None
        self._candado = threading.Lock()
        self.corridas: dict[str, Corrida] = {}
        self.en_curso: Corrida | None = None
        self.otro_trabajo = lambda: None  # si hay otra cosa corriendo que no puede ir a la vez (la corrida completa), su motivo

    def proveedores(self) -> list[dict]:
        if self._proveedores is None:
            self._proveedores = proveedores_para_subir(self._a_mano)
        return self._proveedores

    def recibir_archivo(self, nombre: str, contenido: bytes, subida: str | None = None) -> dict:
        """Guarda un archivo que llegó del navegador en salida/web/subidas/<subida>/. Todavía no lo procesa."""
        nombre = Path(nombre.replace("\\", "/")).name.strip()
        if not nombre or nombre.startswith(".") or nombre.startswith("~$"):
            raise ValueError("El archivo no tiene un nombre válido.")
        extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        if extension not in ("xlsx", "pdf"):
            raise ValueError("Por ahora Ceibo recibe la lista en Excel (.xlsx) y, si las trae, sus fichas de seguridad en PDF.")
        if not contenido:
            raise ValueError(f"{nombre} llegó vacío.")
        problema = contenido_que_no_es(nombre, extension, contenido)
        if problema:
            raise ValueError(problema)
        if subida and not re.fullmatch(r"[0-9a-f]{12}", subida):
            raise ValueError("La subida no es válida.")
        subida = subida or uuid.uuid4().hex[:12]
        carpeta = self.carpeta_subidas / subida
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(contenido)
        archivos = sorted(p.name for p in carpeta.iterdir() if p.is_file())
        excels = [a for a in archivos if a.lower().endswith(".xlsx")]
        return {"subida": subida, "archivos": archivos, "excel": excels[0] if len(excels) == 1 else None,
                "fds": [a for a in archivos if a.lower().endswith(".pdf")],
                "sugerido": sugerir_proveedor(excels[0], self.proveedores()) if len(excels) == 1 else None,
                "problema": "Elegí un solo Excel: la lista del proveedor." if len(excels) > 1 else
                ("Falta el Excel con la lista." if not excels else None)}

    def empezar(self, subida: str, proveedor_id: str) -> Corrida:
        """Pasa lo subido a entrada/<carpeta del proveedor>/ y lanza la corrida en un hilo. Una sola a la vez."""
        if not re.fullmatch(r"[0-9a-f]{12}", subida or ""):
            raise ValueError("La subida no es válida.")
        carpeta = self.carpeta_subidas / subida
        if not carpeta.is_dir():
            raise ValueError("No encuentro ese archivo: volvé a elegirlo.")
        proveedor = next((p for p in self.proveedores() if p["id"] == proveedor_id), None)
        if proveedor is None:
            raise ValueError("Ese proveedor no está en proveedores.csv.")
        if not proveedor["habilitado"]:
            raise ValueError(f"{proveedor['nombre']} todavía no se puede subir desde acá: su lista se lee con una "
                             "configuración hecha a mano para sus archivos (por ahora, desde acá entran las listas en Excel).")
        excels = [p for p in carpeta.iterdir() if p.suffix.lower() == ".xlsx"]
        if len(excels) != 1:
            raise ValueError("Hace falta un solo Excel con la lista.")
        with self._candado:
            if self.en_curso and self.en_curso.estado_publico()["estado"] == "corriendo":
                raise RuntimeError("Ya se está procesando otra lista: esperá a que termine.")
            ocupado = self.otro_trabajo()
            if ocupado:
                raise RuntimeError(ocupado)
            destino = self.carpeta_entrada / proveedor["carpeta"]
            destino.mkdir(parents=True, exist_ok=True)
            fds_nuevas = sorted(p.name for p in carpeta.iterdir() if p.suffix.lower() == ".pdf")
            carpeta_fds = destino / "fichas_de_seguridad"
            fds_viejas = len([p for p in carpeta_fds.glob("*.pdf") if p.name not in fds_nuevas]) if carpeta_fds.is_dir() else 0
            if fds_nuevas:
                carpeta_fds.mkdir(exist_ok=True)
                for nombre in fds_nuevas:
                    shutil.copyfile(carpeta / nombre, carpeta_fds / nombre)
            ruta_excel = destino / excels[0].name
            shutil.copyfile(excels[0], ruta_excel)
            corrida = Corrida(ruta_excel.name, proveedor, fds_nuevas)
            total_fds = len(fds_nuevas) + fds_viejas
            corrida.paso(RECIBIR, "hecho", f"Un Excel de {proveedor['nombre']}"
                         + (f", con {total_fds} {'ficha' if total_fds == 1 else 'fichas'} de seguridad." if total_fds
                            else ("" if proveedor["nombre"].endswith(".") else ".")))
            self.corridas[corrida.id] = corrida
            self.en_curso = corrida
        ruta_log = self.carpeta_web / "registros" / f"{datetime.now():%Y%m%d_%H%M%S}_{proveedor['id']}.log"

        def trabajar():
            try:
                pasos = self.fabrica_de_pasos(ruta_log)
            except BaseException as error:  # sin .env o sin MODELO: vigilar.Pasos corta con SystemExit
                from presentacion import causa_conocida
                corrida.fallar("No se pudo arrancar", [causa_conocida(str(error)) or str(error)
                                                       or "Falta la configuración del .env (MODELO y la key)."], ENTENDER)
                return
            try:
                correr_lista(corrida, ruta_excel, pasos, proveedor, carpeta_trazas=self.carpeta_salida / "trazas",
                             ruta_registro=self.carpeta_salida / "bandeja.json",
                             ruta_resultados=self.carpeta_salida / "resultados.json",
                             carpeta_pedidos=self.carpeta_salida / "pedidos",
                             carpeta_consolidado=self.carpeta_salida / "consolidado",
                             carpeta_salida=self.carpeta_salida, ruta_grabacion=self.ruta_grabacion,
                             fds_viejas=fds_viejas)
            except Exception as error:
                corrida.fallar("Algo falló mientras se procesaba la lista", [f"{type(error).__name__}: {error}"])

        threading.Thread(target=trabajar, daemon=True, name=f"corrida_{corrida.id}").start()
        return corrida

    def corrida_de_ejemplo(self) -> dict | None:
        """La última corrida que terminó bien, grabada (el plan B)."""
        if not self.ruta_grabacion.exists():
            return None
        try:
            return json.loads(self.ruta_grabacion.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
