# Criterio de revisión

Cuándo un producto queda lista_para_alta, duplicado o a_revision, y con qué motivo (sección 8 del estándar). Las reglas conservan el número que tienen en tus instrucciones.

4. No inventes. Un campo que no se puede determinar con lo que trae el archivo va en null. Si es obligatorio, el producto va a revisión con el motivo que corresponda.
5. Si `calculado.motivo_gtin` no es null, el GTIN no sirve: el campo `gtin` va en null y el producto va a revisión con ese motivo, además de cualquier otro que corresponda.
6. Los candidatos de `buscar_parecidos` no son duplicados automáticamente: comparalos con el producto como dice la sección 8 del estándar.
15. `calculado.conflictos` son los campos en los que dos archivos del proveedor dan valores distintos, ya comparados por el código (cada uno con sus versiones y sus fuentes). Cada campo en conflicto va en null en la ficha, sin fuente (un conflicto de `contenido` incluye su `unidad`: las dos van en null, como ya vienen en `calculado`), y el producto va a revisión con el motivo `conflicto_entre_fuentes`. Ese motivo va solo si `calculado.conflictos` no está vacío: que dos archivos escriban lo mismo de otra forma no es un conflicto. El precio se resuelve por vigencia (sección 6 del estándar): solo aparece en `calculado.conflictos` cuando el código no pudo decidir cuál rige.
