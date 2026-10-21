# Ingesta de Catálogo — Agente con MCP

Proyecto final del **Taligent AI Spring Camp** (Curso de Agentes V2). Caso asignado: **Ingesta de Catálogo** para *Farmacias Ceibo*, una cadena ficticia.

> Los archivos de `Data/` son material del camp, provisto por Taligent y publicado con su permiso.

---

## 🧩 El problema

Los proveedores mandan sus productos nuevos en formatos distintos: CSV, Excel, PDF, mails. Hoy una persona de Compras los copia a mano, corrige los errores, elige la categoría y se fija si el producto ya estaba cargado. Es lento, y un catálogo con errores degrada todo lo que se apoya en él.

Este sistema lee los archivos de cada proveedor y arma la **ficha estándar** de cada producto, con uno de tres estados:

| Estado | Cuándo |
|---|---|
| `lista_para_alta` | La ficha está completa y cumple el estándar |
| `duplicado` | El código de barras (GTIN) ya está en el catálogo. Se informa el SKU |
| `a_revision` | Hay algo que tiene que resolver una persona. Se informa el motivo |

Cada dato de la ficha dice **de dónde salió**: archivo y línea.

---

## ✅ Estado: semana 1 (módulos 1 y 2)

El agente procesa los 50 productos de **Distribuidora Litoral** (CSV) con tools de un **servidor MCP propio**.

| Métrica | Resultado |
|---|---|
| Estados correctos | **50 / 50** (40 para alta, 7 duplicados, 3 a revisión) |
| Evaluador: acierto de ficha entera | **13 / 13 = 100%** |
| Evaluador: acierto de fuente | **13 / 13 = 100%** |
| Costo | **US$ 0,064 la corrida = US$ 0,00128 por ficha** |
| Tiempo | ~3,5 minutos para los 50 productos |
| Pruebas sin IA | 81 (41 de cuentas + 32 del servidor + 8 del agente) |

**Proveedor apartado:** *Bebé Feliz* (P06). No se usa para ajustar el sistema hasta la semana 5, y está **bloqueado por código**: el servidor rechaza cualquier pedido para leerlo.

---

## 🏗️ Cómo funciona

```
Claude Haiku 5.5  ◀── API ──▶  agente.py  ◀── MCP (stdio) ──▶  servidor_mcp.py  ──▶  Data/ (lee)
   decide qué pedir             el loop                         4 tools              salida/ (escribe)
                                                                3 resources
                                                                usa cuentas.py
```

1. `agente.py` arma el *system prompt* con `prompt_sistema.md` y los 3 resources del servidor.
2. Le pide a Haiku que procese una tanda de productos.
3. Haiku pide tools (`tool_use`), el agente las ejecuta en el servidor y le devuelve los resultados (`tool_result`).
4. Se repite hasta que Haiku registra todos los productos de la tanda.

Una forma simple de pensarlo es un restaurante:

- **El agente es el mozo.** Decide qué pedir y cuándo, pero nunca entra a la cocina: no toca los archivos.
- **El servidor MCP es la cocina.** Es el único que lee los datos y el único que escribe los resultados.
- **Las tools son la carta.** Si el mozo pide algo que no está en la carta, la cocina le dice que no.

---

## 📁 Estructura

| Archivo | Qué es |
|---|---|
| `cuentas.py` | Las reglas fijas del estándar en Python puro, sin IA: dígito verificador, GTIN, números con coma, unidades y abreviaturas |
| `servidor_mcp.py` | El servidor MCP (FastMCP, stdio): 4 tools y 3 resources |
| `prompt_sistema.md` | Las instrucciones del agente (rol, tarea, reglas, señal de fin) |
| `agente.py` | El agente: el loop del módulo 2 conectado al servidor, de a tandas |
| `evaluar.py` | El evaluador: compara contra casos verificados a mano y da el % de acierto |
| `evaluacion/casos_litoral.json` | Los 13 casos con la ficha correcta, verificados a mano |
| `probar_cuentas.py` · `probar_servidor.py` · `probar_agente.py` | Pruebas sin IA (gratis) |
| `verificar_entorno.py` | Chequea Python, `.env`, datos y API antes de empezar |
| `salida/resultados.json` | Las fichas de la última corrida |
| `salida/corrida.json` | El reporte de la última corrida: costo, tokens y tiempo |
| `Data/` | Proveedores, catálogo actual, estándar y consultas (solo lectura) |

### Las 4 tools y los 3 resources del servidor

| Tool | Qué hace | ¿Escribe? |
|---|---|---|
| `leer_archivo_proveedor` | Devuelve las filas de a tandas, cada una con su fuente (archivo y línea), el valor `original` y el `calculado` por `cuentas.py` | No |
| `buscar_por_gtin` | ¿Este GTIN ya está en el catálogo? Búsqueda exacta | No |
| `buscar_parecidos` | Para productos **sin** GTIN: trae candidatos con la misma marca, contenido y unidad. El modelo decide si es el mismo producto | No |
| `registrar_ficha` | Guarda el resultado. **Antes valida** que sea coherente y, si no lo es, no guarda y le explica al modelo qué corregir | **Sí, es la única** |

| Resource | Archivo |
|---|---|
| `estandar://ficha_de_producto` | `Data/estandar/ficha_de_producto.md` |
| `estandar://vocabulario` | `Data/estandar/vocabulario.yaml` |
| `estandar://taxonomia` | `Data/estandar/taxonomia.csv` |

---

## ▶️ Cómo correrlo

Necesitás **Python 3.14** y una API key de Anthropic.

```powershell
# 1. Entorno virtual e instalación
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Crear el archivo .env (nunca se sube a Git)
#    ANTHROPIC_API_KEY=sk-ant-...
#    MODELO=claude-haiku-5-5

# 3. Verificar que todo esté listo
python verificar_entorno.py

# 4. Pruebas sin IA (gratis)
python probar_cuentas.py
python probar_servidor.py
python probar_agente.py

# 5. Procesar Litoral con el agente (~US$ 0,06)
python agente.py

# 6. Evaluar el resultado (gratis)
python evaluar.py
```

---

## 🧠 Decisiones y su porqué

### Entorno
- **El código está separado de los datos.** `Data/` es de solo lectura, y todo lo que genera el sistema va a `salida/`.
- **La API key nunca va en el código ni en Git:** va en `.env`. El modelo también va en `.env`, para poder cambiarlo sin tocar código.
- **Las versiones están fijas en `requirements.txt`,** para que el proyecto se pueda reproducir.
- **`.gitattributes` con `Data/** -text`,** para que Git no toque los fines de línea de los archivos originales (el CSV de Litoral usa CRLF).

### Lo que resuelve el código (`cuentas.py`)
- **"El modelo extrae, el código computa"** (módulo 3). Todo lo que tiene una sola respuesta correcta lo hace Python: dígito verificador, conversión de unidades, números, abreviaturas. Es gratis, instantáneo y no se equivoca.
- **Errores de programación → `raise`. Datos malos del proveedor → se devuelve el motivo de revisión.** Un GTIN inválido es un caso normal del negocio, no un error del programa.
- **Nunca se inventa un valor.** Lo que no se puede determinar queda vacío, como pide el estándar.
- **Las conversiones salen de una tabla** (`UNIDADES`) y no de muchos `if`: sumar una unidad nueva es agregar una línea.
- **El redondeo es `int(valor + 0.5)` y no `round()`,** porque `round()` de Python es "bancario" (12,5 → 12).
- **El parámetro `separador_decimal`** existe porque hay una planilla en inglés: si no, "4.8" se leería como 48.
- **El vocabulario es la única fuente de verdad.** Abreviaturas, estados y motivos se leen de `vocabulario.yaml`, no se copian al código.
- **Las abreviaturas solo se reemplazan como palabra completa** (regex con lookbehind). Así `REP/CION` no se toca por la abreviatura `P/`.

### El servidor MCP
- **Lo exacto lo hace el código y el juicio, el modelo.** Que un GTIN esté o no en el catálogo es una búsqueda exacta. Que *"JABON PUREZA ANTIBAC. 90GRS"* sea el mismo producto que *"JABON ANTIBAC. PUREZA 90 GR"* necesita criterio: el código trae los candidatos y el modelo compara.
- **`buscar_parecidos` solo se usa cuando no hay GTIN.** El estándar define el *posible duplicado* únicamente sin GTIN. En Litoral, 27 de los 50 productos tienen "parecidos" que no son el mismo producto.
- **Un solo escritor que valida antes de guardar.** `registrar_ficha` revisa la coherencia: que el ítem exista, que el estado y los motivos sean del vocabulario, que un duplicado traiga un SKU que exista y que una revisión traiga un motivo. Lo que manda el modelo es input no confiable (módulo 2).
- **Lo que tiene que pasar siempre lo garantiza el código, no el prompt:** P06 bloqueado con `Literal`, GTIN de 13 dígitos, unidades ML/G/UN.
- **El estándar va como resource, no como tool.** Lo necesita cada ficha y es corto (unos 4.000 tokens). En la semana 5 se cachea.
- **Paginación de a 25 como máximo,** para que ninguna respuesta llene el contexto.
- **La escritura es segura:** primero se escribe un archivo temporal y después se renombra, así `resultados.json` nunca queda roto.
- **Sin adelantar semanas:** las validaciones del *contenido* de la ficha (GTIN válido, valores del vocabulario) quedan para los hooks de la semana 4.

### El agente
- **Tandas de 10 productos por conversación.** Lo fijo (prompt + estándar + tools) son **9.780 tokens**, medidos con `count_tokens` antes de gastar. Con tandas de 10, una conversación llega a ~28.000 tokens, muy lejos de los 100.000, donde la tarifa se multiplica por 5. Además, si falla una tanda, las otras siguen.
- **`effort: high`, fijo.** La documentación de Haiku 5.5 lo recomienda para *"seguir instrucciones al pie de la letra"*. No se cambia dentro de una conversación.
- **Streaming,** porque el SDK no permite más de ~21.000 tokens de salida sin streaming.
- **Tools en paralelo:** Haiku pide varias juntas y el código las ejecuta **de a una, en orden**, así sigue habiendo un solo escritor. Todos los resultados vuelven en un solo mensaje y sin texto agregado.
- **El loop del módulo 2:** la respuesta va entera al historial (con el thinking), los errores vuelven como `is_error` y nunca se lanzan, hay timeout por tool y se maneja cada `stop_reason`.
- **Topes de seguridad:** 30 vueltas por conversación y freno a los 80.000 tokens de entrada.
- **Chequeo por código:** si al terminar una tanda falta registrar algún producto, se le manda **un** recordatorio.
- **Traza de todo** en `salida/trazas/`: qué pensó, qué pidió, qué recibió y cuántos tokens usó. Sin traza, debuggear es adivinar.
- **`fastmcp.Client`:** envuelve el `ClientSession` del módulo 2 y trae timeout por llamada.

### El evaluador
- **Es código puro, sin IA y determinista** (módulo 1). Mide el acierto de ficha entera, el acierto de fuente y, como diagnóstico, los campos con error.
- **Un campo que debía quedar vacío y se completó es error,** porque inventar es peor que dejar vacío.
- **13 casos elegidos para cubrir lo difícil:** los 3 estados, abreviaturas, conversiones, los 3 sin GTIN, un "parecido" trampa y los cepillos de 2 unidades.

### El extra
- **Cada ficha dice qué dato decidió su categoría** (`categoria_decidida_por`: campo, valor y una frase). Le ahorra a Compras revisar la clasificación a ciegas.
- **Se pide la *evidencia*, no el razonamiento.** La documentación avisa que pedir "el razonamiento paso a paso" en un parámetro puede terminar en un rechazo.
- **El código verifica que el dato citado sea real.** Una explicación que no coincide con la ficha no se guarda.
- **Cada corrida deja su reporte** (`salida/corrida.json`) con costo por ficha y tiempo, para comparar corridas.

---

## 🔬 De 85% a 100%: el evaluador en acción

1. **La primera corrida** dio 50/50 estados correctos, pero el evaluador marcó **11/13 = 85%**.
2. **El thinking en la traza mostró la causa:** Haiku trataba distinto los cepillos de "2 UN". A veces los cargaba como un pack de 2 y a veces no. El prompt dejaba una ambigüedad y cada conversación la resolvía distinto.
3. **Se cambió una sola cosa:** una regla general en el prompt (*"un pack solo si el archivo lo dice explícitamente"*), apoyada en la sección 5 del estándar. No es un parche para los cepillos de Litoral.
4. **Resultado: 13/13 = 100%,** confirmado en dos corridas seguidas con **cero diferencias** en las 50 fichas.

Y en una de esas corridas, Haiku mandó un SKU mal escrito. `registrar_ficha` lo rechazó con el motivo, Haiku lo corrigió en la vuelta siguiente y **no llegó nada roto** al resultado.

---

## 🗺️ Próximas semanas

| Semana | Qué se suma |
|---|---|
| 2 · M3 | PDFs con la página de cada dato, datos que cruzan archivos y el peligro para el depósito (FDS) |
| 3 · M4 | Varios agentes leyendo en paralelo, consolidados por código |
| 4 · M5 | Un archivo nuevo se procesa sin intervención: criterio como prompt MCP, hooks y permisos por agente |
| 5 · M6 | Salida estructurada, caché y Batch API. Se abre el proveedor apartado |
| 6 | Todo con un comando, y el asistente de consultas |
| 7 | Demo Day |
