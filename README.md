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

Cada dato de la ficha dice **de dónde salió**: archivo y línea en un CSV, archivo y página en un PDF, archivo, hoja y fila en un Excel.

---

## ✅ Estado: semana 2 (módulo 3)

El agente procesa **4 proveedores con 4 formatos distintos**, y cada dato cita su archivo, página, hoja o fila.

| Proveedor | Formato | Fichas | Evaluador (ficha / fuente) | Costo | Por ficha | Alta · Dup. · Rev. |
|---|---|---|---|---|---|---|
| P03 Distribuidora Litoral | CSV | 50 | 13/13 · 13/13 | US$ 0,069 | US$ 0,0014 | 40 · 7 · 3 |
| P07 Limpieza Hogar Sur | PDF (tabla) + 7 FDS | 25 | 12/12 · 12/12 | US$ 0,050 | US$ 0,0020 | 20 · 3 · 2 |
| P01 Laboratorio Andes | PDF + Excel posterior | 26 | 12/12 · 12/12 | US$ 0,051 | US$ 0,0020 | 22 · 0 · 4 |
| P05 Dermalab | Folleto en prosa (PDF) + lista Excel | 18 | 12/12 · 12/12 | US$ 0,033 | US$ 0,0019 | 14 · 0 · 4 |
| **Total** | **4 formatos** | **119** | **49/49 = 100%** | **US$ 0,20** | **US$ 0,0017** | 96 · 10 · 13 |

- **Consistencia:** Andes dio 100% en dos corridas seguidas con **0 diferencias** en sus 26 fichas. Después de los cambios de prompt de la semana, las 50 fichas de Litoral siguen **idénticas** a las de la semana 1 y las 25 de LHS, idénticas a las de antes.
- **Tiempo:** ~11 minutos para las 119 fichas.
- **Extracción de los PDF:** se paga **una sola vez por archivo** y queda guardada (LHS US$ 0,003 · 7 FDS US$ 0,005 · Andes US$ 0,009 · Dermalab US$ 0,004).
- **401 pruebas sin IA:** 87 de cuentas, 23 del lector de Excel, 78 del extractor de PDF, 28 del de FDS, 42 del de folletos, 106 del servidor, 13 del agente y 24 del pedido al proveedor.
- **El extra:** el **pedido al proveedor**, armado por el código, sin IA (ver más abajo).

**Proveedor apartado:** *Bebé Feliz* (P06). No se usa para ajustar el sistema hasta la semana 5, y está **bloqueado por código**: el servidor rechaza cualquier pedido para leerlo.

<details>
<summary>Semana 1 (módulos 1 y 2)</summary>

Litoral (CSV) con el servidor MCP propio: 50/50 estados correctos, evaluador 13/13 = 100% de ficha y de fuente, US$ 0,00128 por ficha.
</details>

---

## 🏗️ Cómo funciona

```
1) Extraer (una vez por PDF, con citations)
   PDF con tabla ──▶ extractor_pdf.py     ─┐
   Folleto       ──▶ extractor_folleto.py ─┼──▶ salida/extracciones/   (cada dato con su página)
   FDS           ──▶ extractor_fds.py     ─┘

2) Procesar (cada corrida)
   Claude Haiku 5.5 ◀── API ──▶ agente.py ◀── MCP ──▶ servidor_mcp.py ──▶ salida/resultados.json
                                                     (lee CSV, Excel y las extracciones)

3) Pedir (sin IA)
   salida/resultados.json ──▶ pedido_proveedor.py ──▶ salida/pedidos/
```

1. `agente.py` arma el *system prompt* con `prompt_sistema.md` y los 3 resources del servidor.
2. Le pide a Haiku que procese una tanda de productos.
3. Haiku pide tools (`tool_use`), el agente las ejecuta en el servidor y le devuelve los resultados (`tool_result`).
4. Se repite hasta que Haiku registra todos los productos de la tanda.

Un PDF no se lee en cada corrida: se **extrae una vez**, con *citations* (la API dice de qué página sale cada texto), y el código verifica lo extraído. El servidor lo sirve con la **misma forma** que una fila de CSV: el agente no se entera del formato, solo cambia la fuente.

Una forma simple de pensarlo es un restaurante:

- **El agente es el mozo.** Decide qué pedir y cuándo, pero nunca entra a la cocina: no toca los archivos.
- **El servidor MCP es la cocina.** Es el único que lee los datos y el único que escribe los resultados.
- **Las tools son la carta.** Si el mozo pide algo que no está en la carta, la cocina le dice que no.

---

## 📁 Estructura

| Archivo | Qué es |
|---|---|
| `cuentas.py` | Las reglas fijas del estándar en Python puro, sin IA: dígito verificador, GTIN, números con coma, unidades, abreviaturas, precios, fechas y presentaciones |
| `extractor_pdf.py` | Extrae los PDF con **tablas** (LHS, Andes): filas armadas por el código con el texto citado, campos verificados, vigencia |
| `extractor_folleto.py` | Extrae los **folletos en prosa** (Dermalab): cada producto es lo que hay entre dos códigos, con la página de cada campo |
| `extractor_fds.py` | Lee las **fichas de datos de seguridad**: qué códigos cubre cada una (sección 1) y su peligro para el depósito (sección 14) |
| `lector_excel.py` | Lee cualquier Excel: encuentra el encabezado, cada fila con su fuente (hoja y fila) y la vigencia de arriba |
| `servidor_mcp.py` | El servidor MCP (FastMCP, stdio): 4 tools y 3 resources. Cruza los archivos de cada proveedor por código |
| `prompt_sistema.md` | Las instrucciones del agente (rol, tarea, reglas, señal de fin) |
| `agente.py` | El agente: el loop del módulo 2 conectado al servidor, de a tandas |
| `evaluar.py` | El evaluador: compara contra casos verificados a mano y da el % de acierto |
| `pedido_proveedor.py` | El extra: el mensaje para cada proveedor con lo que falta para cerrar sus revisiones, sin IA |
| `evaluacion/casos_*.json` | Los casos con la ficha correcta, armados desde los archivos: Litoral 13, LHS 12, Andes 12, Dermalab 12 |
| `probar_*.py` | Pruebas sin IA (gratis), una por archivo. `probar_citas*.py` son los experimentos con la API (cuestan centavos) |
| `verificar_entorno.py` | Chequea Python, `.env`, datos y API antes de empezar |
| `salida/resultados.json` | Las fichas de la última corrida |
| `salida/corrida_P0x.json` | El reporte de la última corrida de cada proveedor: costo, tokens y tiempo |
| `salida/extracciones/` | Lo que se extrajo de cada PDF (y la llamada guardada, para no volver a pagarla) |
| `salida/experimentos/` | Las respuestas de los experimentos con citations que definieron el diseño |
| `salida/pedidos/` | Los pedidos a cada proveedor |
| `Data/` | Proveedores, catálogo actual, estándar y consultas (solo lectura) |

### Las 4 tools y los 3 resources del servidor

| Tool | Qué hace | ¿Escribe? |
|---|---|---|
| `leer_archivo_proveedor` | Devuelve las filas de a tandas, cada una con su fuente, el valor `original` y el `calculado` por el código: cuentas, el cruce con los otros archivos del proveedor (precio por vigencia, conflictos, fuentes aparte) y su FDS | No |
| `buscar_por_gtin` | ¿Este GTIN ya está en el catálogo? Búsqueda exacta | No |
| `buscar_parecidos` | Para productos **sin** GTIN: trae candidatos con la misma marca, contenido y unidad. El modelo decide si es el mismo producto | No |
| `registrar_ficha` | Guarda el resultado. **Antes valida** que sea coherente (también con los conflictos que encontró el código) y, si no lo es, no guarda y le explica al modelo qué corregir | **Sí, es la única** |

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

# 5. Extraer los PDF (una sola vez; reusa la llamada guardada si ya existe)
python extractor_pdf.py                                              # LHS
python extractor_pdf.py "Data/proveedores/P01_Laboratorio_Andes/Lista_de_precios_octubre_2026.pdf"
python extractor_folleto.py                                          # Dermalab
python extractor_fds.py                                              # las 7 FDS de LHS

# 6. Procesar cada proveedor con el agente (~US$ 0,002 por ficha)
python agente.py P03      # Litoral · también P07 (LHS), P01 (Andes), P05 (Dermalab)

# 7. Evaluar (gratis)
python evaluar.py                                   # Litoral
python evaluar.py evaluacion/casos_dermalab.json    # o casos_lhs / casos_andes

# 8. Armar los pedidos a los proveedores (gratis)
python pedido_proveedor.py
```

> Las extracciones ya están en `salida/extracciones/`: el paso 5 solo hace falta si cambia un PDF (`--de-nuevo` vuelve a llamar a la API).

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

### Semana 2: los PDF y la página de cada dato
- **Experimentar antes de diseñar.** Antes de escribir cada extractor se miró qué cita la API (`probar_citas*.py`). Cada hallazgo cambió el diseño: en una tabla la API cita **la tabla entera**, en una FDS **la sección entera**, y en el folleto cada cita trae **el final de un producto y el principio del siguiente**.
- **La página la da la API, no el modelo** (*citations*). Y **el código lee el texto citado,** que es el documento real, no la copia de Haiku.
- **El código verifica lo extraído:** cada campo tiene que estar en **su** fila (un valor de otra fila no vale), las partes juntas tienen que formar la fila y **ningún código desaparece** (cobertura). Lo ambiguo **no se elige**: queda como problema.
- **Dos llamadas en las tablas** porque *citations* y una forma fija no van juntas: la 1 cita, la 2 es una tool forzada que llena el formulario.
- **El folleto de Dermalab no es una tabla.** El renglón del código no termina en punto y la API lo pega al nombre del producto **siguiente**: armar "código + lo de su cita" le daba a 17 de 18 productos el nombre del siguiente, sin ningún error. Por eso se pide **una cita por producto**: lo que queda **entre dos códigos** es un producto, y lo prueba el texto citado (17 de 17 pares). Sin esa prueba, el código no arma nada: sería adivinar el orden.
- **Fuente por campo.** DL-136 tiene el nombre al pie de la página 1 y el resto en la 2: la marca y la variante citan la página 1, lo demás la 2.
- **Sin Files API:** no baja el costo en tokens y los PDF son de 1 o 2 páginas. Guardar la extracción en JSON ahorra más y es más simple.

### Semana 2: datos que cruzan archivos
- **Lo que cruza archivos lo consolida el código,** por código de producto: el producto con su FDS, la lista con su actualización, el folleto con su lista de precios.
- **El precio rige por vigencia** (leída del archivo, con su cita). Si falta una vigencia, o es la misma y los precios difieren, **no se decide**: el precio queda vacío y va como conflicto.
- **Un conflicto se detecta comparando valores ya normalizados,** no cómo están escritos: *"Comp. x 20"* y *"Comp. rec. x 20"* son lo mismo; *"x 20"* y *"x 30"* no. El campo queda vacío y van las dos versiones con su fuente.
- **Completar no es un conflicto:** si el folleto no trae EAN ni precio y la lista sí, se toman de la lista, con su fuente.
- **`registrar_ficha` garantiza los conflictos:** no guarda `conflicto_entre_fuentes` donde el código no encontró ninguno, ni un producto con conflicto que no vaya a revisión.
- **FDS:** el peligro para el depósito sale de la sección 14, traducido con la tabla del estándar. Un producto de esas familias sin FDS queda `pendiente_fds`, también si es un duplicado.

### El extra
- **Cada ficha dice qué dato decidió su categoría** (`categoria_decidida_por`: campo, valor y una frase). Le ahorra a Compras revisar la clasificación a ciegas.
- **Se pide la *evidencia*, no el razonamiento.** La documentación avisa que pedir "el razonamiento paso a paso" en un parámetro puede terminar en un rechazo.
- **El código verifica que el dato citado sea real.** Una explicación que no coincide con la ficha no se guarda.
- **Cada corrida deja su reporte** (`salida/corrida_P0x.json`) con costo por ficha y tiempo, para comparar corridas.

### El extra de la semana 2: el pedido al proveedor
- **Responde la Q16** (*"¿qué le tengo que pedir a Dermalab?"*): por proveedor, un mensaje listo con lo que falta para cerrar sus revisiones.
- **Lo arma el código, sin IA:** gratis y sin inventar. Usa lo que registró el agente, los conflictos que encontró el código (con sus dos versiones y dónde está cada una) y el catálogo (para preguntar por un posible duplicado).
- **Solo pide lo que tiene que dar el proveedor:** EAN, precio, contenido y, en medicamentos, la monodroga. A Andes no se le pide la categoría: la decidimos nosotros cuando llegue la monodroga.
- **No manda nada:** deja `salida/pedidos/pedido_P0x.md` para que lo mande una persona.

---

## 🔬 De 85% a 100%: el evaluador en acción

1. **La primera corrida** dio 50/50 estados correctos, pero el evaluador marcó **11/13 = 85%**.
2. **El thinking en la traza mostró la causa:** Haiku trataba distinto los cepillos de "2 UN". A veces los cargaba como un pack de 2 y a veces no. El prompt dejaba una ambigüedad y cada conversación la resolvía distinto.
3. **Se cambió una sola cosa:** una regla general en el prompt (*"un pack solo si el archivo lo dice explícitamente"*), apoyada en la sección 5 del estándar. No es un parche para los cepillos de Litoral.
4. **Resultado: 13/13 = 100%,** confirmado en dos corridas seguidas con **cero diferencias** en las 50 fichas.

Y en una de esas corridas, Haiku mandó un SKU mal escrito. `registrar_ficha` lo rechazó con el motivo, Haiku lo corrigió en la vuelta siguiente y **no llegó nada roto** al resultado.

---

## 🔬 Semana 2: de 58% a 100% en Andes

| Corrida | Andes | Dermalab | Qué cambió |
|---|---|---|---|
| 1 (línea base) | 58% | 75% | — |
| 2 | 83% | 100% | Regla 14: en los medicamentos la forma farmacéutica no es variante; en un folleto la variante sale del nombre; no se descarta la línea («Sun»). Regla 15: un conflicto de contenido incluye la unidad |
| 3 | 100% | — | Regla 3: un archivo posterior solo cuenta para lo que cruzó el código. Regla 13: sin principio activo, la categoría no se adivina |
| 4 | 100% | 100% | Nada: prueba de consistencia (0 diferencias en las 26 fichas de Andes) |

- **Reglas generales, no parches por producto,** como en la semana 1. Con la misma idea, en LHS el evaluador pasó de 75% a 100% con dos reglas (el % de un no medicamento va en la variante y no se descarta nada de la variante).
- **El evaluador también corrige al que arma los casos.** En la corrida 1, el agente dejó sin categoría dos medicamentos sin monodroga, y tenía razón: deducirla del nombre comercial es una suposición, y el estándar dice que no se completa con suposiciones. Se corrigieron esos dos casos, no el agente.
- **Medir dos veces importa:** AN-1106 quedó sin categoría en una corrida y con categoría en la otra. Esa diferencia mostró que la regla no estaba clara.

---

## 🗺️ Próximas semanas

| Semana | Qué se suma |
|---|---|
| 2 · M3 ✅ | PDFs con la página de cada dato, datos que cruzan archivos y el peligro para el depósito (FDS) |
| 3 · M4 | Varios agentes leyendo en paralelo, consolidados por código |
| 4 · M5 | Un archivo nuevo se procesa sin intervención: criterio como prompt MCP, hooks y permisos por agente |
| 5 · M6 | Salida estructurada, caché y Batch API. Se abre el proveedor apartado |
| 6 | Todo con un comando, y el asistente de consultas |
| 7 | Demo Day |