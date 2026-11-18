"""Pruebas del criterio de revisión servido como prompt MCP (semana 4, paso 4). Sin IA. Correr: python probar_criterio.py

La idea del paso: MISMO contenido, OTRO lugar. Las reglas 4, 5, 6 y 15 pasan de prompt_sistema.md al servidor, textuales
y con su número. Se compara contra prompt_sistema.md tal como estaba al cierre de la semana 3 (congelado en
salida/experimentos/referencias_sem4/prompt_sistema_sem3.md).

Semana 4, paso 8: las reglas 3, 13 y 14 cambian A PROPÓSITO (abreviaturas que el vocabulario no tiene; suplementos:
el componente declarado es el principio activo; tipos de varias palabras). Esas dos se comparan aparte: lo que decían antes sigue estando, solo se agregó.

Semana 5, paso 2D: las reglas 7 y 8 cambian A PROPÓSITO por la ficha estructurada (strict): la 7 dice que peligro y ONU
van en null en los productos sin FDS (el formulario lleva siempre los 18 campos) y la 8 nombra las fuentes del mail y
del Excel (pendiente 1 de la semana 4). Se comparan exacto: lo de antes + solo ese cambio.
"""
import asyncio
import re
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from referencias import ENTORNO_PRUEBAS  # carpetas congeladas; va antes que el servidor
from agente import RUTA_SERVIDOR, armar_system_prompt  # noqa: E402

CARPETA = Path(__file__).parent
PROMPT_ANTES = (CARPETA / "salida" / "experimentos" / "referencias_sem4" / "prompt_sistema_sem3.md").read_text(encoding="utf-8")
PROMPT_AHORA = (CARPETA / "prompt_sistema.md").read_text(encoding="utf-8")
CRITERIO = (CARPETA / "criterio_de_revision.md").read_text(encoding="utf-8")
DEL_CRITERIO = (4, 5, 6, 15)
CAMBIADAS_PASO_8 = (3, 13, 14)  # semana 4, paso 8: se agregó texto, no se quitó nada
CAMBIADAS_SEM5 = (7, 8, 14)      # semana 5: 7 y 8 en el paso 2D (la ficha estructurada); 14 en el paso 8C
# Semana 5, paso 8C: la regla 14 tenía dos frases que se contradecían ("no se descarta nada" y "el nombre del tipo no se
# repite"); la segunda opinión lo mostró (salida/segunda_opinion.json). Se aclara cuál manda, con estos dos reemplazos.
REGLA_14_SEM5 = [
    ("aunque parezca repetir el tipo (por ejemplo, la línea «Sun» de un protector solar).",
     "aunque parezca repetir el tipo (por ejemplo, la línea «Sun» de un protector solar: una línea o un nombre de "
     "fantasía es del producto, no del nombre del tipo)."),
    ("sin agregar CORPORAL ni FACIAL a la variante.",
     "sin agregar CORPORAL ni FACIAL a la variante. El nombre del tipo es cómo el archivo llama a esa clase de producto, "
     "aunque use más palabras que el vocabulario: «crema para manos» es tipo CREMA y PARA MANOS no va a la variante. "
     "Esto manda sobre «no se descarta nada»: lo que nombra la clase de producto es el tipo; lo que distingue al producto "
     "dentro de esa clase (línea, uso, ingrediente, talle, FPS) va en la variante."),
]

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


def reglas(texto: str) -> dict[int, str]:
    """Las reglas numeradas de un texto: {número: la regla entera (con sus sub-ítems)}."""
    partes = re.split(r"^(\d+)\. ", texto, flags=re.MULTILINE)
    resultado = {}
    for numero, cuerpo in zip(partes[1::2], partes[2::2]):
        renglones = cuerpo.split("\n")
        # La regla sigue mientras los renglones estén sangrados (sub-ítems, como en la 12); termina en el primero que no
        largo = next((i for i, r in enumerate(renglones[1:], 1) if r.strip() and not r.startswith(" ")), len(renglones))
        resultado[int(numero)] = "\n".join(renglones[:largo]).strip()
    return resultado


print("--- los archivos: mover sin cambiar ---")
antes, ahora, criterio = reglas(PROMPT_ANTES), reglas(PROMPT_AHORA), reglas(CRITERIO)
chequear("Antes había 15 reglas", sorted(antes), list(range(1, 16)))
chequear("El criterio trae las reglas 4, 5, 6 y 15", sorted(criterio), list(DEL_CRITERIO))
chequear("...textuales, letra por letra", all(criterio[n] == antes[n] for n in DEL_CRITERIO), True)
chequear("prompt_sistema.md ya no las tiene", sorted(ahora), [n for n in range(1, 16) if n not in DEL_CRITERIO])
chequear("...y las otras 8 quedaron letra por letra",
         all(ahora[n] == antes[n] for n in ahora if n not in CAMBIADAS_PASO_8 + CAMBIADAS_SEM5), True)
chequear("Paso 8: la regla 3 dice lo mismo que antes y suma al final", ahora[3].startswith(antes[3]) and ahora[3] != antes[3], True)
chequear("Paso 8: la regla 13 dice lo mismo que antes y suma al final", ahora[13].startswith(antes[13]) and ahora[13] != antes[13], True)
regla_14_sem4 = ahora[14]  # la regla 14 como estaba antes del paso 8C: deshaciendo los dos reemplazos
for viejo, nuevo in REGLA_14_SEM5:
    chequear(f"Semana 5, paso 8C: la regla 14 tiene el texto nuevo («{nuevo[-40:]}»)", ahora[14].count(nuevo), 1)
    regla_14_sem4 = regla_14_sem4.replace(nuevo, viejo)
chequear("Paso 8: la regla 14 conserva todos sus renglones (solo pasa de 'Dos casos' a 'Tres casos') y suma uno",
         [r for r in antes[14].replace("Dos casos:", "Tres casos:").split("\n") if r not in regla_14_sem4.split("\n")], [])
chequear("...exactamente un renglón más", len(regla_14_sem4.split("\n")) - len(antes[14].split("\n")), 1)
chequear("Semana 5: la regla 7 dice lo mismo que antes y suma que peligro y ONU van en null sin FDS",
         ahora[7], antes[7] + " En los demás productos, esos dos campos van en null.")
chequear("Semana 5: la regla 8 solo cambia el paréntesis de las fuentes (suma el mail y el Excel)",
         ahora[8], antes[8].replace("(archivo y línea en un CSV, archivo y página en un PDF)",
                                    "(archivo y línea en un CSV o un mail, archivo y página en un PDF, "
                                    "archivo, hoja y fila en un Excel)"))
chequear("prompt_sistema.md avisa dónde están (en <criterio_de_revision>)", "<criterio_de_revision>" in PROMPT_AHORA, True)


async def desde_el_servidor():
    async with Client(PythonStdioTransport(RUTA_SERVIDOR, env=ENTORNO_PRUEBAS)) as cliente:
        prompts = await cliente.list_prompts()
        servido = await cliente.get_prompt("criterio_de_revision")
        system = await armar_system_prompt(cliente)
        return prompts, servido, system


print("--- el servidor lo sirve como prompt MCP ---")
prompts, servido, system = asyncio.run(desde_el_servidor())
chequear("El servidor ofrece el prompt 'criterio_de_revision'", [p.name for p in prompts], ["criterio_de_revision"])
chequear("...con una descripción (para quien lo descubra con list_prompts)", bool(prompts[0].description), True)
chequear("Llega idéntico al archivo", servido.messages[0].content.text, CRITERIO)

print("--- el system prompt del fichador ---")
chequear("Lleva el criterio entre etiquetas", f"<criterio_de_revision>\n{CRITERIO}\n</criterio_de_revision>" in system, True)
vigentes = {n: criterio[n] if n in DEL_CRITERIO else ahora[n] for n in range(1, 16)}  # cada regla como está hoy
for n in range(1, 16):
    regla = vigentes[n]
    if system.count(regla) != 1:
        chequear(f"La regla {n} aparece una sola vez", system.count(regla), 1)
chequear("Las 15 reglas aparecen una sola vez cada una (ni duplicadas ni perdidas)",
         [system.count(vigentes[n]) for n in range(1, 16)], [1] * 15)
chequear("Sigue trayendo el estándar, el vocabulario y la taxonomía (los resources)",
         [f"<{e}>" in system for e in ("estandar_ficha_de_producto", "vocabulario", "taxonomia")], [True, True, True])


class ServidorSinCriterio:
    """Un servidor que no ofrece el prompt: el fichador no tiene que arrancar con un criterio inventado."""
    async def get_prompt(self, nombre):
        raise RuntimeError(f"Unknown prompt: {nombre}")


try:
    asyncio.run(armar_system_prompt(ServidorSinCriterio()))
    chequear("Sin el prompt en el servidor, el fichador no arranca", "arrancó", "no arrancó")
except RuntimeError as error:
    chequear("Sin el prompt en el servidor, el fichador no arranca (no hay copia de respaldo)", "Unknown prompt" in str(error), True)

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
