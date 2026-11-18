# Acuse de recibo — BebeFeliz_altas.xlsx

Recibido 2026-11-17 22:13:42 · Bebé Feliz S.A. (P06) · **PROCESADO ✅**

## Qué entendió el sistema
- **Proveedor:** P06, por la carpeta donde llegó (`P06_Bebe_Feliz`).
- **Hoja con los productos nuevos:** "Altas" (es la única del archivo).
- **Columnas** (encabezado en la fila 2; 32 productos):
  - `Código` → código del proveedor · ej. BF-503
  - `Producto` → descripción · ej. "Leche Crecer"
  - `EAN` → código de barras · ej. "7798993880961"
  - `Precio lista` → precio de costo · ej. 707.39
  - `Cantidad` → contenido · ej. "0,4 kg"
  - `Talle / etapa` → **NO VA**: no se eligió para ningún dato del formulario
  - `Precio c/desc. 8%` → **NO VA**: no se eligió para ningún dato del formulario
- **Contenido:** en una columna, con su unidad · ej. fila 3: "0,4 kg" → 400 G.
- **Decimales con coma** (se ve en "0,4 kg").
- **Moneda:** UYU — el archivo no menciona dólares (estándar, sección 6: sin moneda indicada es UYU).

## Resultado
- **32 productos:** 26 listos para alta · 4 duplicados · 2 a revisión.
  - BF-530 ya existe en el catálogo: **SKU103304** (TOALLITAS HUMEDAS PEQUEÑOS PASOS ALOE X 80 UN).
  - BF-533 ya existe en el catálogo: **SKU102562** (LECHE INFANTIL CRECER ETAPA 3 X 400 G).
  - BF-575 ya existe en el catálogo: **SKU103794** (LECHE INFANTIL CRECER ETAPA 1 X 800 G).
  - BF-587 ya existe en el catálogo: **SKU100777** (LECHE INFANTIL CRECER ETAPA 2 X 400 G).
  - BF-593 a revisión: sin código de barras, posible duplicado (candidato: SKU102653).
  - BF-596 a revisión: sin código de barras, posible duplicado (candidato: SKU102121).
- **Inestables:** ninguna marcada.
- **Frenos de los hooks** (corrida del 2026-11-17 22:13): 0.

## Pedido al proveedor
- BF-593: El código de barras (EAN-13).
- BF-593: ¿Es el mismo producto que ya tenemos cargado como "TOALLITAS HUMEDAS PEQUEÑOS PASOS SIN PERF. 80UN" (SKU102653)?
- BF-596: El código de barras (EAN-13).
- BF-596: ¿Es el mismo producto que ya tenemos cargado como "TOALLITAS HUMEDAS PEQUEÑOS PASOS ALOE 50UNID" (SKU102121)?
- (mensaje completo, listo para mandar: `salida/pedidos/pedido_P06.md`)

Costo de la recepción y las FDS: US$ 0.0004 (las fichas se miden en la corrida del orquestador).
Este acuse lo armó el código con lo que ya estaba guardado: no usa IA ni agrega nada.
