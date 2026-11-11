"""Pruebas de la bandeja de entrada (semana 4, pasos 7 y 9B) sin IA: pasos falsos y una bandeja temporal.
Correr: python probar_vigilar.py"""
import json
import shutil
import tempfile
from pathlib import Path

import vigilar
from vigilar import archivos_de_la_bandeja, huella_del_archivo, procesar, una_vuelta

PROVEEDORES = Path(__file__).parent / "Data" / "proveedores"
NORTE = PROVEEDORES / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx"
RIVERA = PROVEEDORES / "P02_Cosmetica_Rivera" / "ALTAS RIVERA OCT.xlsx"

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


class PasosFalsos:
    """Los pasos de la bandeja sin IA: anotan qué se llamó y contestan lo que se les pide."""
    def __init__(self, receta_entra=True, problemas_fds=None, codigo_fichar=0, escritas=(14, 14), explota=False,
                 acuse_explota=False):
        self.llamadas, self.acuses = [], []
        self.receta_entra, self.problemas_fds, self.codigo_fichar = receta_entra, problemas_fds or [], codigo_fichar
        self.escritas, self.explota, self.acuse_explota = escritas, explota, acuse_explota

    def recibir(self, ruta):
        self.llamadas.append(("recibir", ruta.name))
        if self.explota:
            raise RuntimeError("se cortó la conexión")
        return {"receta": {"hoja": "x"} if self.receta_entra else None, "costo_usd": 0.0005,
                "problemas": [] if self.receta_entra else ["La moneda coincide con lo que dice el archivo"]}

    def leer_fds(self, carpeta):
        self.llamadas.append(("leer_fds", carpeta.parent.name))
        return {"costo_usd": 0.0015, "fichas": [{"archivo": "FDS_x.pdf", "problemas": self.problemas_fds}]}

    def fichar(self, proveedor_id):
        self.llamadas.append(("fichar", proveedor_id))
        return self.codigo_fichar

    def fichas_escritas(self, proveedor_id):
        return self.escritas

    def pedir(self, proveedor_id):
        self.llamadas.append(("pedir", proveedor_id))
        return 0

    def acusar(self, ruta, registro):
        self.llamadas.append(("acusar", ruta.name))
        if self.acuse_explota:
            raise ValueError("no se pudo leer resultados.json")
        self.acuses.append((ruta.parent.name, registro["estado"], registro["huella"]))
        return ruta.parent / f"acuse_{ruta.stem}.md"


def bandeja_con(*archivos) -> tuple[Path, Path]:
    """Una bandeja temporal con esos archivos: [(carpeta del proveedor, nombre, archivo de origen)]."""
    base = Path(tempfile.mkdtemp())
    for carpeta, nombre, origen in archivos:
        (base / "entrada" / carpeta).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, base / "entrada" / carpeta / nombre)
    return base / "entrada", base / "bandeja.json"


print("--- 7C · qué hay en la bandeja ---")
entrada, registro = bandeja_con(("P08_Importadora_Norte", "NorteImports_new_items_Q4.xlsx", NORTE))
(entrada / "P08_Importadora_Norte" / "fichas_de_seguridad").mkdir()
shutil.copyfile(NORTE, entrada / "P08_Importadora_Norte" / "fichas_de_seguridad" / "FDS_x.pdf")
shutil.copyfile(NORTE, entrada / "P08_Importadora_Norte" / "~$NorteImports_new_items_Q4.xlsx")
chequear("Solo el Excel del proveedor: ni las FDS de la subcarpeta ni el temporal de Excel (~$)",
         [r.name for r in archivos_de_la_bandeja(entrada)], ["NorteImports_new_items_Q4.xlsx"])
chequear("Sin carpeta de entrada: nada (no explota)", archivos_de_la_bandeja(entrada.parent / "no_existe"), [])
chequear("La huella sale del contenido: dos copias del mismo archivo tienen la misma",
         huella_del_archivo(NORTE) == huella_del_archivo(entrada / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx"), True)

print("--- 7C · una_vuelta: espera a que termine de copiarse, procesa una sola vez ---")
pasos, tamanios = PasosFalsos(), {}
chequear("1ª mirada: recién llegó, solo mide el tamaño (nada procesado)", una_vuelta(pasos, entrada, registro, tamanios), [])
hechos = una_vuelta(pasos, entrada, registro, tamanios)
chequear("2ª mirada: mismo tamaño -> lo procesa", [(h["proveedor_id"], h["estado"]) for h in hechos], [("P08", "procesado")])
chequear("En orden: recepción, FDS (tiene la carpeta), fichas, pedido y, al final, el acuse", pasos.llamadas,
         [("recibir", "NorteImports_new_items_Q4.xlsx"), ("leer_fds", "P08_Importadora_Norte"), ("fichar", "P08"), ("pedir", "P08"),
          ("acusar", "NorteImports_new_items_Q4.xlsx")])
chequear("9B · el acuse recibe lo que quedó anotado (estado y huella del registro)", pasos.acuses,
         [("P08_Importadora_Norte", "procesado", huella_del_archivo(NORTE))])
chequear("9B · y la bandeja devuelve dónde quedó el acuse", hechos[0]["acuse"].name, "acuse_NorteImports_new_items_Q4.md")
anotado = json.loads(registro.read_text(encoding="utf-8"))
clave = next(iter(anotado))
chequear("Queda anotado en el registro, con su huella", (anotado[clave]["estado"], anotado[clave]["huella"]),
         ("procesado", huella_del_archivo(NORTE)))
chequear("3ª mirada: el mismo archivo no se vuelve a procesar", una_vuelta(pasos, entrada, registro, tamanios), [])
archivo = entrada / "P08_Importadora_Norte" / "NorteImports_new_items_Q4.xlsx"
shutil.copyfile(RIVERA, archivo)  # el proveedor manda una versión nueva con el mismo nombre
chequear("Si el archivo cambia: primero se espera (el tamaño cambió)", una_vuelta(pasos, entrada, registro, tamanios), [])
chequear("...y en la siguiente mirada se procesa de nuevo (otra huella)",
         [h["estado"] for h in una_vuelta(pasos, entrada, registro, tamanios)], ["procesado"])
shutil.rmtree(entrada.parent, ignore_errors=True)

print("--- 7C · procesar: lo que no se procesa, con su motivo ---")
entrada, registro = bandeja_con(("Varios", "lista.xlsx", NORTE), ("P06_Bebe_Feliz", "BebeFeliz_altas.xlsx", NORTE),
                                ("P07_Limpieza_Hogar_Sur", "nuevos.pdf", NORTE), ("P04_Higiene_Total", "novedades.xlsx", NORTE))
pasos = PasosFalsos()
r = procesar(entrada / "Varios" / "lista.xlsx", pasos)
chequear("Carpeta que no es de ningún proveedor: rechazado (no se adivina de quién es)",
         (r["estado"], "no es de ningún proveedor" in r["motivo"]), ("rechazado", True))
r = procesar(entrada / "P06_Bebe_Feliz" / "BebeFeliz_altas.xlsx", pasos)
chequear("Bebé Feliz: rechazado, está apartado", (r["estado"], r["proveedor_id"], "apartado" in r["motivo"]),
         ("rechazado", "P06", True))
r = procesar(entrada / "P07_Limpieza_Hogar_Sur" / "nuevos.pdf", pasos)
chequear("Un PDF: formato todavía no soportado por la bandeja (no se procesa a ciegas)", r["estado"], "formato_no_soportado")
chequear("...en ninguno de los 3 se llamó a nada (ni a la API)", pasos.llamadas, [])
r = procesar(entrada / "P04_Higiene_Total" / "novedades.xlsx", PasosFalsos(receta_entra=False))
chequear("La receta no entra: se detiene ahí, con los problemas de la recepción",
         (r["estado"], r["problemas"]), ("no_entro", ["La moneda coincide con lo que dice el archivo"]))
falsos = PasosFalsos()
procesar(entrada / "P04_Higiene_Total" / "novedades.xlsx", falsos)
chequear("Sin carpeta fichas_de_seguridad no se leen FDS", [n for n, _ in falsos.llamadas], ["recibir", "fichar", "pedir"])
(entrada / "P04_Higiene_Total" / "fichas_de_seguridad").mkdir()
r = procesar(entrada / "P04_Higiene_Total" / "novedades.xlsx", PasosFalsos(problemas_fds=["no se pudo citar la sección 14"]))
chequear("Una FDS mal leída: frenado antes de las fichas", (r["estado"], r["problemas"]),
         ("frenado", ["FDS_x.pdf: no se pudo citar la sección 14"]))
r = procesar(entrada / "P04_Higiene_Total" / "novedades.xlsx", PasosFalsos(codigo_fichar=1))
chequear("El orquestador termina con error: se informa", r["estado"], "error")
falsos = PasosFalsos(escritas=(0, 28))
r = procesar(entrada / "P04_Higiene_Total" / "novedades.xlsx", falsos)
chequear("El escritor no escribió el proveedor (le faltaba una ficha): frenado, y no se arma el pedido",
         (r["estado"], ("pedir", "P04") in falsos.llamadas), ("frenado", False))

print("--- 7C · un error inesperado en un archivo no tira abajo a los demás ---")
pasos, tamanios = PasosFalsos(explota=True), {}
una_vuelta(pasos, entrada, registro, tamanios)
hechos = {Path(h["archivo"]).parent.name: h for h in una_vuelta(pasos, entrada, registro, tamanios)}
chequear("Se miraron los 4 archivos", sorted(hechos), ["P04_Higiene_Total", "P06_Bebe_Feliz", "P07_Limpieza_Hogar_Sur", "Varios"])
chequear("El que explotó queda como error, con el motivo", (hechos["P04_Higiene_Total"]["estado"],
         "se cortó la conexión" in hechos["P04_Higiene_Total"]["motivo"]), ("error", True))
chequear("Los demás, cada uno con su estado", [hechos[c]["estado"] for c in ("P06_Bebe_Feliz", "P07_Limpieza_Hogar_Sur", "Varios")],
         ["rechazado", "formato_no_soportado", "rechazado"])
chequear("Todos quedan en el registro (no se reintentan cada 5 s; si el archivo cambia, sí)",
         len(json.loads(registro.read_text(encoding="utf-8"))), 4)
chequear("9B · los 4 tienen acuse, también los rechazados y el que explotó",
         sorted((carpeta, estado) for carpeta, estado, _ in pasos.acuses),
         [("P04_Higiene_Total", "error"), ("P06_Bebe_Feliz", "rechazado"), ("P07_Limpieza_Hogar_Sur", "formato_no_soportado"),
          ("Varios", "rechazado")])
shutil.rmtree(entrada.parent, ignore_errors=True)

print("--- 9B · si el acuse falla, lo procesado queda igual y la bandeja sigue ---")
entrada, registro = bandeja_con(("P08_Importadora_Norte", "NorteImports_new_items_Q4.xlsx", NORTE),
                                ("Varios", "lista.xlsx", NORTE))
pasos, tamanios = PasosFalsos(acuse_explota=True), {}
una_vuelta(pasos, entrada, registro, tamanios)
hechos = {Path(h["archivo"]).parent.name: h for h in una_vuelta(pasos, entrada, registro, tamanios)}
chequear("Los dos archivos se procesaron igual, cada uno con su estado",
         (hechos["P08_Importadora_Norte"]["estado"], hechos["Varios"]["estado"]), ("procesado", "rechazado"))
chequear("...sin acuse (None), pero anotados en el registro",
         ([h["acuse"] for h in hechos.values()], len(json.loads(registro.read_text(encoding="utf-8")))), ([None, None], 2))
chequear("...y no se reprocesan en la próxima mirada", una_vuelta(pasos, entrada, registro, tamanios), [])
shutil.rmtree(entrada.parent, ignore_errors=True)

chequear("La bandeja real es entrada/, al lado del proyecto", vigilar.CARPETA_ENTRADA.name, "entrada")

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
