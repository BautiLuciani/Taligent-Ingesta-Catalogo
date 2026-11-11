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

# Para ESTE proceso: los imports de servidor_mcp que hagan las pruebas leen la copia congelada.
os.environ["INGESTA_CARPETA_EXTRACCIONES"] = str(CARPETA_REFERENCIAS / "extracciones")

# Para los servidores que levantan las pruebas: son OTROS procesos y fastmcp los arranca con un entorno limpio
# (no heredan os.environ), así que la variable se les pasa explícita en env.
ENTORNO_PRUEBAS = {"INGESTA_CARPETA_EXTRACCIONES": os.environ["INGESTA_CARPETA_EXTRACCIONES"]}
