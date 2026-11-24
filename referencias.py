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

# Semana 5, paso 2A: las 225 fichas del cierre de la semana 4 (commit bcb0b9b, evaluador 100/101), congeladas aparte
# en referencias_sem5/. Son la vara para la ficha estructurada: ninguna puede quedar rechazada por el formulario nuevo.
CARPETA_REFERENCIAS_SEM5 = Path(__file__).parent / "salida" / "experimentos" / "referencias_sem5"
RUTA_RESULTADOS_SEM4 = CARPETA_REFERENCIAS_SEM5 / "resultados_sem4.json"

# Semana 6, paso 2: las 257 fichas del cierre de la semana 5 (commit 6ba619b, evaluador 116/116) y los pedidos al
# proveedor de ese commit, congelados en referencias_sem6/. Son lo que consulta el asistente en las pruebas
# (las respuestas esperadas de las 29 consultas se verificaron contra estas fichas).
CARPETA_REFERENCIAS_SEM6 = Path(__file__).parent / "salida" / "experimentos" / "referencias_sem6"
RUTA_RESULTADOS_SEM5 = CARPETA_REFERENCIAS_SEM6 / "resultados.json"
CARPETA_PEDIDOS_SEM5 = CARPETA_REFERENCIAS_SEM6 / "pedidos"

# Semana 7, paso 2: el consolidado de Norte (lo que vieron los fichadores, del commit 59aaf13), congelado en
# referencias_sem7/. Es lo que usa la tabla "Así entendimos el archivo" en las pruebas de Subir una lista.
CARPETA_REFERENCIAS_SEM7 = Path(__file__).parent / "salida" / "experimentos" / "referencias_sem7"

# Para ESTE proceso: los imports de servidor_mcp que hagan las pruebas leen las copias congeladas.
os.environ["INGESTA_CARPETA_EXTRACCIONES"] = str(CARPETA_REFERENCIAS_SEM4 / "extracciones")
os.environ["INGESTA_CARPETA_RECEPCION"] = str(CARPETA_RECEPCION_REFERENCIA)

# Para los servidores que levantan las pruebas: son OTROS procesos y fastmcp los arranca con un entorno limpio
# (no heredan os.environ), así que las variables se les pasan explícitas en env.
VARIABLES_DE_CARPETAS = ("INGESTA_CARPETA_EXTRACCIONES", "INGESTA_CARPETA_RECEPCION")
ENTORNO_PRUEBAS = {variable: os.environ[variable] for variable in VARIABLES_DE_CARPETAS}
