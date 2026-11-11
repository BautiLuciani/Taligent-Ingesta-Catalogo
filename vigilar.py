"""La bandeja de entrada (semana 4, paso 7): un archivo nuevo se procesa SIN intervención.

Se deja el archivo de un proveedor en entrada/<carpeta del proveedor>/ (la misma de Data/proveedores, ej.
entrada/P08_Importadora_Norte/NorteImports_new_items_Q4.xlsx; si trae FDS, en entrada/P08_.../fichas_de_seguridad/)
y este programa hace todo solo, sin tocar código ni configuración:

  1. espera a que el archivo termine de copiarse (su tamaño no cambia entre dos miradas);
  2. reconoce el proveedor por la carpeta (proveedores.csv). Desconocido o apartado: no se procesa;
  3. recepcionista: la receta (el modelo propone, el código verifica). Si no entra, se detiene con el motivo;
  4. si trae FDS, las lee extractor_fds.py;
  5. fichas + único escritor: el orquestador, solo para ese proveedor (con los hooks y los permisos del módulo 5);
  6. el pedido al proveedor;
  7. lo anota en salida/bandeja.json con la huella del contenido: el mismo archivo no se procesa dos veces, pero si
     cambia (otra huella), sí.

Hoy entra solo un Excel: es lo que sabe recibir el recepcionista. Un PDF, CSV o mail de un proveedor nuevo
necesitaría su propio recepcionista (queda anotado como "formato no soportado", no se procesa a ciegas).

Correr: python vigilar.py              (queda mirando la bandeja; Ctrl+C para salir)
        python vigilar.py --una-vez    (procesa lo pendiente y termina)
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from recepcion import APARTADOS, proveedor_de_la_ruta, ruta_relativa

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_ENTRADA = Path(os.getenv("INGESTA_CARPETA_ENTRADA", CARPETA_PROYECTO / "entrada"))
RUTA_REGISTRO = CARPETA_PROYECTO / "salida" / "bandeja.json"
SEGUNDOS_ENTRE_MIRADAS = 5
FORMATOS = (".xlsx",)  # lo que sabe recibir el recepcionista


def huella_del_archivo(ruta: Path) -> str:
    """12 letras que salen del CONTENIDO: si el archivo cambia, cambia la huella (y se vuelve a procesar)."""
    return hashlib.sha1(ruta.read_bytes()).hexdigest()[:12]


def archivos_de_la_bandeja(carpeta: Path) -> list[Path]:
    """Los archivos que dejaron en la bandeja: entrada/<carpeta>/<archivo>. No entra lo de las subcarpetas (las FDS
    van en fichas_de_seguridad/ y se leen con su Excel) ni los temporales de Excel (~$archivo.xlsx)."""
    if not carpeta.is_dir():
        return []
    return sorted(ruta for ruta in carpeta.glob("*/*") if ruta.is_file() and not ruta.name.startswith("~$"))


class Pasos:
    """Los pasos que gastan o tardan, separados para poder probar la bandeja sin IA (las pruebas los cambian)."""

    def __init__(self):
        import anthropic  # recién acá: las pruebas usan pasos falsos y no necesitan la API
        from dotenv import load_dotenv
        load_dotenv(CARPETA_PROYECTO / ".env")
        self.modelo = os.getenv("MODELO")
        if not self.modelo:
            sys.exit("ERROR: falta MODELO en el .env")
        self.cliente = anthropic.Anthropic()

    def recibir(self, ruta: Path) -> dict:
        from recepcion import mostrar, recibir
        resultado = recibir(self.cliente, self.modelo, ruta)
        mostrar(resultado)
        return resultado

    def leer_fds(self, carpeta: Path) -> dict:
        from extractor_fds import extraer_fds, mostrar_resultado
        resultado = extraer_fds(self.cliente, self.modelo, carpeta)
        mostrar_resultado(resultado)
        return resultado

    def fichar(self, proveedor_id: str) -> int:
        """El orquestador en un proceso aparte (carga el servidor desde cero: ve la recepción y las FDS recién hechas).
        Sin capturar la salida: escribe directo en la consola (lección de la semana 3 con los caracteres en Windows)."""
        return subprocess.run([sys.executable, "orquestador.py", "--fichas", "--proveedores", proveedor_id],
                              cwd=CARPETA_PROYECTO).returncode

    def pedir(self, proveedor_id: str) -> int:
        return subprocess.run([sys.executable, "pedido_proveedor.py", proveedor_id], cwd=CARPETA_PROYECTO).returncode

    def fichas_escritas(self, proveedor_id: str) -> tuple[int, int]:
        """(cuántas fichas del proveedor quedaron en resultados.json, cuántos productos tenía que tener)."""
        carpeta_salida = CARPETA_PROYECTO / "salida"
        consolidado = json.loads((carpeta_salida / "consolidado" / f"{proveedor_id}.json").read_text(encoding="utf-8"))
        resultados = json.loads((carpeta_salida / "resultados.json").read_text(encoding="utf-8"))
        esperados = [fila["item_id"] for fila in consolidado["filas"]]
        return sum(1 for item in esperados if item in resultados), len(esperados)


def procesar(ruta: Path, pasos) -> dict:
    """Un archivo de la bandeja, de punta a punta. Devuelve lo que pasó (estado + detalle): nunca lanza una excepción
    por un problema del archivo; lo informa."""
    proveedor_id = proveedor_de_la_ruta(ruta)
    if ruta.suffix.lower() not in FORMATOS:
        return {"estado": "formato_no_soportado", "proveedor_id": proveedor_id,
                "motivo": f"{ruta.suffix or 'sin extensión'}: por ahora la bandeja recibe solo Excel (.xlsx)"}
    if proveedor_id is None:
        return {"estado": "rechazado", "proveedor_id": None,
                "motivo": f"la carpeta {ruta.parent.name!r} no es de ningún proveedor de proveedores.csv"}
    if proveedor_id in APARTADOS:
        return {"estado": "rechazado", "proveedor_id": proveedor_id,
                "motivo": f"{proveedor_id} es el proveedor apartado hasta la semana 5"}

    recepcion = pasos.recibir(ruta)
    if recepcion["receta"] is None:
        return {"estado": "no_entro", "proveedor_id": proveedor_id, "motivo": "la receta no entró en la recepción",
                "problemas": recepcion["problemas"], "costo_usd": recepcion["costo_usd"]}
    costo = recepcion["costo_usd"]

    carpeta_fds = ruta.parent / "fichas_de_seguridad"
    if carpeta_fds.is_dir():
        fds = pasos.leer_fds(carpeta_fds)
        costo += fds["costo_usd"]
        problemas = [f"{ficha['archivo']}: {p}" for ficha in fds["fichas"] for p in ficha["problemas"]]
        if problemas:  # chequeo entre etapas: una FDS mal leída no pasa a las fichas (el orquestador la frenaría igual)
            return {"estado": "frenado", "proveedor_id": proveedor_id, "motivo": "la lectura de sus FDS quedó con problemas",
                    "problemas": problemas, "costo_usd": round(costo, 6)}

    if pasos.fichar(proveedor_id) != 0:
        return {"estado": "error", "proveedor_id": proveedor_id, "motivo": "el orquestador terminó con error",
                "costo_usd": round(costo, 6)}
    escritas, esperadas = pasos.fichas_escritas(proveedor_id)
    if escritas != esperadas:
        return {"estado": "frenado", "proveedor_id": proveedor_id,
                "motivo": f"el escritor no escribió el proveedor ({escritas} de {esperadas} fichas): ver su salida",
                "costo_usd": round(costo, 6)}
    pasos.pedir(proveedor_id)
    return {"estado": "procesado", "proveedor_id": proveedor_id, "fichas": escritas, "costo_recepcion_y_fds_usd": round(costo, 6)}


def leer_registro(ruta: Path = RUTA_REGISTRO) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def una_vuelta(pasos, carpeta: Path = CARPETA_ENTRADA, ruta_registro: Path = RUTA_REGISTRO,
               tamanios: dict | None = None) -> list[dict]:
    """Una mirada a la bandeja: procesa los archivos nuevos (o cambiados) que ya terminaron de copiarse.

    tamanios: lo que midió la mirada anterior ({ruta: tamaño}). Un archivo se procesa recién cuando su tamaño es el
    mismo en dos miradas seguidas (si no, en Windows se podría leer un Excel a medio copiar). Se actualiza acá.
    """
    tamanios = {} if tamanios is None else tamanios
    registro = leer_registro(ruta_registro)
    hechos = []
    for ruta in archivos_de_la_bandeja(carpeta):
        clave = ruta_relativa(ruta)
        tamanio = ruta.stat().st_size
        anterior, tamanios[clave] = tamanios.get(clave), tamanio
        if anterior != tamanio or tamanio == 0:
            continue  # recién llegó o se está copiando: se mira de nuevo en la próxima vuelta
        huella = huella_del_archivo(ruta)
        if registro.get(clave, {}).get("huella") == huella:
            continue  # ya procesado, y no cambió
        print(f"\n📥 Llegó {clave} (huella {huella})")
        try:
            resultado = procesar(ruta, pasos)
        except Exception as error:  # algo inesperado: se informa y se anota; la bandeja sigue con los demás
            resultado = {"estado": "error", "proveedor_id": proveedor_de_la_ruta(ruta), "motivo": f"{type(error).__name__}: {error}"}
        registro[clave] = {"huella": huella, "fecha": f"{datetime.now():%Y-%m-%d %H:%M:%S}", **resultado}
        ruta_registro.parent.mkdir(parents=True, exist_ok=True)
        ruta_registro.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{'✅' if resultado['estado'] == 'procesado' else '⛔'} {clave}: {resultado['estado']}"
              + (f" — {resultado['motivo']}" if resultado.get("motivo") else ""))
        hechos.append({"archivo": clave, **resultado})
    return hechos


def main():
    argumentos = argparse.ArgumentParser(description="La bandeja de entrada: procesa solo cada archivo que llega a entrada/.")
    argumentos.add_argument("--una-vez", action="store_true", help="Procesa lo pendiente y termina (si no, queda mirando).")
    opciones = argumentos.parse_args()  # con --help termina acá: nunca llega a la API
    CARPETA_ENTRADA.mkdir(exist_ok=True)
    pasos = Pasos()
    tamanios = {}
    print(f"Mirando {CARPETA_ENTRADA} cada {SEGUNDOS_ENTRE_MIRADAS} s"
          + (" (una vez)" if opciones.una_vez else " (Ctrl+C para salir)"))
    try:
        una_vuelta(pasos, tamanios=tamanios)  # la primera mirada mide los tamaños
        while True:
            time.sleep(SEGUNDOS_ENTRE_MIRADAS)
            una_vuelta(pasos, tamanios=tamanios)
            if opciones.una_vez:
                break
    except KeyboardInterrupt:
        print("\nBandeja cerrada.")


if __name__ == "__main__":
    main()
