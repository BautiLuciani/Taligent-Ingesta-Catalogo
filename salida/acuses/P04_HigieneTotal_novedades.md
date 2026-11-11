# Acuse de recibo — HigieneTotal_novedades.xlsx

Recibido 2026-11-11 16:38:38 · Higiene Total S.A. (P04) · **PROCESADO ✅**

## Qué entendió el sistema
- **Proveedor:** P04, por la carpeta donde llegó (`P04_Higiene_Total`).
- **Hoja con los productos nuevos:** "Altas" (2 hojas en el archivo).
  - "Discontinuados": **NO ENTRA** — Productos discontinuados, dados de baja; no son productos nuevos y no se cargan.
- **Columnas** (encabezado en la fila 1; 28 productos):
  - `Item` → código del proveedor · ej. HT40003
  - `Descripcion` → descripción · ej. "ESPUMA DE AFEITAR FILO MENTOL"
  - `EAN13` → código de barras · ej. "7796370729803"
  - `Costo` → precio de costo · ej. 135.92
  - `Cont.` → contenido · ej. 300
  - `UM` → unidad · ej. "cc"
- **Contenido:** cantidad y unidad en columnas separadas · ej. fila 2: "300 cc" → 300 ML.
- **Decimales con coma** (ningún texto del archivo trae números con decimales: se toma el de español).
- **Moneda:** UYU — el archivo no menciona dólares (estándar, sección 6: sin moneda indicada es UYU).

## Resultado
- **28 productos:** 18 listos para alta · 5 duplicados · 5 a revisión.
  - HT40006 ya existe en el catálogo: **SKU100469** (GEL DE DUCHA PUREZA HIDRATANTE X 1000 ML).
  - HT40027 ya existe en el catálogo: **SKU103885** (GEL DE DUCHA AQUAVIVA HIDRATANTE X 1000 ML).
  - HT40054 ya existe en el catálogo: **SKU102261** (GEL DE DUCHA AQUAVIVA COCO X 400 ML).
  - HT40069 ya existe en el catálogo: **SKU101267** (SHAMPOO AQUAVIVA BEBE MANZANILLA X 200 ML).
  - HT40078 ya existe en el catálogo: **SKU103710** (GEL DE DUCHA AQUAVIVA HIDRATANTE X 750 ML).
  - HT40084 a revisión: sin código de barras, posible duplicado (candidato: SKU101806).
  - HT40033 a revisión: sin código de barras, posible duplicado (candidato: SKU103983).
  - HT40045 a revisión: sin código de barras, posible duplicado (candidato: SKU103087).
  - HT40063 a revisión: sin código de barras, posible duplicado (candidato: SKU102254).
  - HT40081 a revisión: sin código de barras, posible duplicado (candidato: SKU101771).
- **Inestables:** ninguna marcada.
- **Frenos de los hooks** (corrida del 2026-11-11 18:20): 0.

## Pedido al proveedor
- HT40084: El código de barras (EAN-13).
- HT40084: ¿Es el mismo producto que ya tenemos cargado como "SH. AQUAVIVA BEBE 200CC" (SKU101806)?
- HT40033: El código de barras (EAN-13).
- HT40033: ¿Es el mismo producto que ya tenemos cargado como "TOALLITAS HUMEDAS AQUAVIVA ALOE 80UNID" (SKU103983)?
- HT40045: El código de barras (EAN-13).
- HT40045: ¿Es el mismo producto que ya tenemos cargado como "GEL DE DUCHA PUREZA AVENA 750ML." (SKU103087)?
- HT40063: El código de barras (EAN-13).
- HT40063: ¿Es el mismo producto que ya tenemos cargado como "DESOD. ROLL ON AQUAVIVA S/ PERF. 50CC" (SKU102254)?
- HT40081: El código de barras (EAN-13).
- HT40081: ¿Es el mismo producto que ya tenemos cargado como "DESOD. ROLL ON AQUAVIVA MUJER 50ML." (SKU101771)?
- (mensaje completo, listo para mandar: `salida/pedidos/pedido_P04.md`)

Costo de la recepción y las FDS: US$ 0.0005 (las fichas se miden en la corrida del orquestador).
Este acuse lo armó el código con lo que ya estaba guardado: no usa IA ni agrega nada.
