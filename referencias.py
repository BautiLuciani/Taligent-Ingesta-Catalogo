"""Referencias congeladas para las pruebas sin IA (semana 4, paso 0).

El sistema reescribe salida/extracciones/ en cada lectura y salida/resultados.json en cada corrida. Una prueba que
compara contra esos archivos se rompe (o, peor, pasa sin deber) según cómo salió la última corrida. Por eso las
pruebas leen una copia CONGELADA del commit 043a3aa (fin de la semana 3): salida/experimentos/referencias_sem3/.

Uso: en cada prueba, importar este módulo ANTES que servidor_mcp (o que algo que lo importe), porque el servidor
decide de dónde lee en el momento en que se importa.
"""
import os
from pathlib import Path

CARPETA_REFERENCIAS = Path(__file__).parent / "salida" / "experimentos" / "referencias_sem3"
RUTA_RESULTADOS_REFERENCIA = CARPETA_REFERENCIAS / "resultados.json"
# Semana 4, paso 3: lo nuevo, congelado aparte en referencias_sem4/:
#   - recepcion/: los resultados del recepcionista (las recetas de Rivera, Higiene Total y Norte), del commit d52a7cc;
#   - extracciones/: las 4 de la semana 3 (copiadas tal cual) + las FDS de Rivera y Norte leídas el 11/11.
CARPETA_REFERENCIAS_SEM4 = Path(__file__).parent / "salida" / "experimentos" / "referencias_sem4"
CARPETA_RECEPCION_REFERENCIA = CARPETA_REFERENCIAS_SEM4 / "recepcion"

# Para ESTE proceso: los imports de servidor_mcp que hagan las pruebas leen las copias congeladas.
os.environ["INGESTA_CARPETA_EXTRACCIONES"] = str(CARPETA_REFERENCIAS_SEM4 / "extracciones")
os.environ["INGESTA_CARPETA_RECEPCION"] = str(CARPETA_RECEPCION_REFERENCIA)

# Para los servidores que levantan las pruebas: son OTROS procesos y fastmcp los arranca con un entorno limpio
# (no heredan os.environ), así que las variables se les pasan explícitas en env.
VARIABLES_DE_CARPETAS = ("INGESTA_CARPETA_EXTRACCIONES", "INGESTA_CARPETA_RECEPCION")
ENTORNO_PRUEBAS = {variable: os.environ[variable] for variable in VARIABLES_DE_CARPETAS}
