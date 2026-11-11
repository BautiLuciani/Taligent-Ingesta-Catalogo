# Acuse de recibo — ALTAS RIVERA OCT.xlsx

Recibido 2026-11-11 16:37:35 · Cosmética Rivera S.A. (P02) · **PROCESADO ✅**

## Qué entendió el sistema
- **Proveedor:** P02, por la carpeta donde llegó (`P02_Cosmetica_Rivera`).
- **Hoja con los productos nuevos:** "Altas" (es la única del archivo).
- **Columnas** (encabezado en la fila 5; 50 productos):
  - `COD. RIV` → código del proveedor · ej. RIV-1203
  - `DESCRIPCION` → descripción · ej. "ACOND. NATIVA LISO X 200 ML"
  - `EAN` → código de barras · ej. "7793092189062"
  - `P. COSTO` → precio de costo · ej. 104.24
  - `OBS` → **NO VA**: Observaciones libres (por ejemplo, 'PACK PROMO CON NECESER'); no es un dato del formulario.
- **Contenido:** dentro de la descripción · ej. fila 8: "ACONDICIONADOR BRISA COLOR 400 CC" → 400 ML.
- **Decimales con coma** (se ve en "TRAT. CAP. ALBORADA NUTRICION 0,5 KG").
- **Moneda:** UYU — el archivo no menciona dólares (estándar, sección 6: sin moneda indicada es UYU).
- **Filas escritas que no son productos** (no se cargan): fila 6 "== CAPILAR ==", fila 48 "== DESODORANTES ==".

## Resultado
- **50 productos:** 44 listos para alta · 5 duplicados · 1 a revisión.
  - RIV-1206 ya existe en el catálogo: **SKU100714** (ACONDICIONADOR BRISA COLOR X 400 ML).
  - RIV-1215 ya existe en el catálogo: **SKU102128** (SHAMPOO NATIVA COLOR X 750 ML).
  - RIV-1311 ya existe en el catálogo: **SKU103605** (TRATAMIENTO CAPILAR NATIVA REPARACION X 250 G).
  - RIV-1341 ya existe en el catálogo: **SKU101316** (SHAMPOO NATIVA RIZOS X 400 ML).
  - RIV-1212 ya existe en el catálogo: **SKU101925** (DESODORANTE AEROSOL BRISA HOMBRE X 150 ML).
  - RIV-1203 a revisión: código de barras inválido.
- **Inestables:** ninguna marcada.
- **Frenos de los hooks** (corrida del 2026-11-11 18:20): 0.

## Pedido al proveedor
- RIV-1203: El código de barras (EAN-13): el que figura en el archivo no es válido.
- RIV-1212: La ficha de datos de seguridad (FDS).
- (mensaje completo, listo para mandar: `salida/pedidos/pedido_P02.md`)

Costo de la recepción y las FDS: US$ 0.0020 (las fichas se miden en la corrida del orquestador).
Este acuse lo armó el código con lo que ya estaba guardado: no usa IA ni agrega nada.
