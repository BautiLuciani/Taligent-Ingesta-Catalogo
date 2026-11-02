"""Pruebas del orquestador sin IA: lectores falsos que tardan (y uno que falla). Correr: python probar_orquestador.py"""
import time

import orquestador

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def lector_falso(segundos, costo):
    """Un lector que tarda como si llamara a la API y devuelve un resultado con su costo (no escribe nada)."""
    def leer(cliente, modelo, ruta, de_nuevo):
        time.sleep(segundos)
        return {"costo_usd": costo}
    return leer


def lector_que_falla(cliente, modelo, ruta, de_nuevo):
    time.sleep(0.2)
    raise RuntimeError("no quedó ninguna fila")


print("--- etapa_lectura: los trabajos a la vez (fan-out) ---")
originales = dict(orquestador.LECTORES)
orquestador.LECTORES.update({"pdf": lector_falso(0.5, {"total": 0.01}), "fds": lector_falso(0.4, 0.005),
                             "folleto": lector_falso(0.3, 0.004)})
try:
    etapa = orquestador.etapa_lectura(None, "modelo", de_nuevo=True)
finally:
    orquestador.LECTORES.update(originales)
chequear("4 trabajos de 0,3 a 0,5 s: a la vez tardan lo que el más lento (~0,5 s), no la suma (1,7 s)",
         (etapa["segundos"] < 0.9, etapa["segundos_uno_detras_de_otro"] >= 1.6), (True, True))
chequear("...todos empiezan juntos (carriles en paralelo)", all(l["inicio"] < 0.2 for l in etapa["lecturas"]), True)
chequear("...el costo suma el de cada uno (número o detalle con 'total')", etapa["costo_usd"], 0.029)
chequear("...y con las lecturas limpias, siguen los 4 proveedores", (etapa["siguen"], etapa["frenados"]),
         (["P03", "P07", "P01", "P05"], {}))

print("--- un lector que falla: se anota, no tira abajo a los demás (fan-in) ---")
orquestador.LECTORES.update({"pdf": lector_falso(0.3, {"total": 0.01}), "fds": lector_falso(0.3, 0.005),
                             "folleto": lector_que_falla})
try:
    etapa = orquestador.etapa_lectura(None, "modelo", de_nuevo=True)
finally:
    orquestador.LECTORES.update(originales)
folleto = next(l for l in etapa["lecturas"] if l["tipo"] == "folleto")
chequear("El error del folleto queda anotado, con su tipo", folleto["error"], "RuntimeError: no quedó ninguna fila")
chequear("...Dermalab (P05) queda frenado con ese motivo",
         etapa["frenados"], {"P05": ["Dermalab_lanzamientos_2026.pdf: RuntimeError: no quedó ninguna fila"]})
chequear("...y los otros 3 siguen igual", etapa["siguen"], ["P03", "P07", "P01"])

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")