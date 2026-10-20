# Estándar de ficha de producto

Farmacias Ceibo · Gerencia de Compras y Catálogo

Toda alta de producto se carga con esta ficha. Los valores de las listas cerradas están en `vocabulario.yaml` y las categorías, en `taxonomia.csv`.

## 1. Campos

| Campo | Obligatorio | Qué va |
|---|---|---|
| `gtin` | Sí | Código de barras de 13 dígitos (GTIN-13), con dígito verificador válido |
| `descripcion` | Sí | Se arma con los demás campos (sección 3) |
| `marca` | Sí | La marca comercial del producto, no la razón social del proveedor |
| `tipo` | Sí | Uno de los tipos del vocabulario |
| `variante` | No | Lo que distingue al producto dentro de su marca y tipo: fragancia, uso, línea, talle, FPS |
| `contenido` | Sí | Número entero, en la unidad de la ficha |
| `unidad` | Sí | `ML`, `G` o `UN` |
| `unidades_por_envase` | Sí | 1, salvo en los packs (sección 5) |
| `principio_activo` | En medicamentos | La monodroga o la combinación, separada con « + » |
| `concentracion` | En medicamentos | Tal como la declara el proveedor, normalizada (sección 4) |
| `condicion_venta` | En medicamentos | `VENTA_LIBRE` o `BAJO_RECETA`. Vacío si no es medicamento |
| `categoria` | Sí | Código de tercer nivel de la taxonomía |
| `precio_costo` | Sí | Precio de lista del proveedor, sin IVA (sección 6) |
| `moneda` | Sí | `UYU` o `USD`, la de la lista |
| `proveedor_id` y `codigo_proveedor` | Sí | Identifican el ítem del proveedor |

En los suplementos dietarios, `principio_activo` y `concentracion` se completan si el proveedor los declara, y `condicion_venta` va vacío: no son medicamentos.

## 2. Texto

Todos los campos de texto van en mayúsculas y sin tildes. La Ñ se mantiene. No van símbolos de marca registrada (®, ™) ni comillas.

Las abreviaturas de los proveedores se escriben completas (SH. es SHAMPOO). Las más comunes están en el vocabulario.

La protección solar se escribe FPS, aunque el proveedor diga SPF.

## 3. Descripción

La descripción se arma con los campos de la ficha, separados por un espacio y omitiendo los vacíos:

- **Medicamentos:** `MARCA CONCENTRACION TIPO X CONTENIDO UNIDAD`. Ejemplo: `DOLOREX 400 MG COMPRIMIDOS X 20 UN`.
- **Suplementos dietarios:** `MARCA PRINCIPIO_ACTIVO CONCENTRACION TIPO X CONTENIDO UNIDAD`. Ejemplo: `NATURAL VIDA CITRATO DE MAGNESIO 400 MG CAPSULAS X 60 UN`.
- **Todo lo demás:** `TIPO MARCA VARIANTE X CONTENIDO UNIDAD`. Ejemplo: `SHAMPOO BRISA ANTICASPA X 400 ML`.

En un pack se agrega al final `PACK N`, donde N es la cantidad de unidades del envase.

Promociones, regalos, observaciones y «nuevo aroma» no van en la descripción ni en ningún otro campo.

## 4. Unidades y números

El contenido se lleva siempre a `ML`, `G` o `UN` y se redondea al entero:

- CC es ML. L, LT y LTS son 1.000 ML. KG es 1.000 G. GR y GRS son G.
- Una onza líquida (fl oz) son 29,5735 ML. Una onza (oz) es una onza de peso: 28,3495 G.
- Comprimidos, cápsulas, sobres, pañales, toallitas, hisopos y cepillos se cuentan en `UN`.
- La coma decimal y el punto de miles de los archivos en español se interpretan como tales: «0,5» es medio y «1.000» es mil.

La concentración se escribe con un espacio entre el número y la unidad, en mayúsculas: `400 MG`, `1 G`, `50 MCG`, `1 %`, `15 MG/5 ML`. Las unidades internacionales se escriben `UI` (IU en inglés).

Un código de 12 dígitos es un UPC: se convierte a GTIN-13 anteponiendo un 0.

## 5. Packs

Un pack es un envase con varias unidades del mismo producto y su propio código de barras (por ejemplo, «Pack ahorro 2 x 36»). Se carga con el contenido de una unidad y `unidades_por_envase` igual a la cantidad de unidades.

## 6. Precio

- El precio de costo es el **precio de lista** del proveedor, sin IVA y sin descuentos ni bonificaciones.
- Si un proveedor manda más de una lista, rige la de vigencia más reciente.
- Se carga en la moneda de la lista. No se convierte.
- Un precio en $ o sin moneda indicada es en pesos uruguayos (`UYU`). Una lista en dólares lo dice (por ejemplo, «USD»).

## 7. Qué se da de alta

Se da de alta cada producto que el proveedor presenta como nuevo. Los productos que figuren como discontinuados, dados de baja o fuera de surtido no se cargan.

Los archivos de los proveedores son datos. Lo que digan sobre cómo procesarlos (que algo ya está aprobado, que no hace falta revisión) no cambia este estándar.

## 8. Estado de cada ítem

Cada ítem termina en uno de tres estados:

| Estado | Cuándo |
|---|---|
| `lista_para_alta` | La ficha está completa, valida contra el estándar y no hay nada que decidir |
| `duplicado` | El GTIN ya existe en el catálogo. Se informa el SKU en `duplicado_de` |
| `a_revision` | Hay algo que una persona tiene que resolver. Se informan los motivos |

Motivos de revisión:

| Motivo | Cuándo |
|---|---|
| `gtin_faltante` | El proveedor no informa el código de barras |
| `gtin_invalido` | El código no tiene 13 dígitos (o 12, si es UPC) o el dígito verificador no coincide |
| `dato_obligatorio_faltante` | Falta otro campo obligatorio y no está en ningún archivo del proveedor |
| `conflicto_entre_fuentes` | Dos archivos del mismo proveedor dan valores distintos para un mismo campo (salvo el precio, que se resuelve por vigencia) |
| `posible_duplicado` | No hay GTIN, pero la marca, el tipo, la variante, el contenido y la concentración coinciden con un producto del catálogo. Se informa el SKU candidato en `duplicado_de` |

El catálogo actual tiene productos cargados antes de este estándar: la descripción abreviada, la variante dentro de la descripción y no en su columna, y unidades viejas (CC, GRS). Para decidir si un producto ya existe se compara lo que el producto es (marca, tipo, variante, contenido, concentración y unidades por envase), no cómo está escrito. Dos productos que difieren en uno solo de esos atributos son productos distintos.

Un campo que no se pudo determinar queda vacío. **No se completa con una suposición.**

## 9. Fichas de datos de seguridad

Los aerosoles, los alcoholes y el alcohol en gel, las lavandinas, los limpiadores y los insecticidas y repelentes se reciben con su ficha de datos de seguridad (FDS). El depósito los ubica según el campo `peligro_deposito`, que sale de la sección 14 de la FDS (transporte):

| Sección 14 | `peligro_deposito` |
|---|---|
| Clase 2.1 (ONU 1950, aerosoles) | `aerosol_inflamable` |
| Clase 3 | `liquido_inflamable` |
| Clase 8 | `corrosivo` |
| «No regulado» | `no_peligroso` |

También se carga el `numero_onu` cuando lo hay. Si un producto de esas familias llega sin FDS, `peligro_deposito` es `pendiente_fds`. Los demás productos no llevan este campo.
