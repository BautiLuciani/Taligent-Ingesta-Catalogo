"""Detector de familias (semana 5, paso 8A): "lo que el archivo escribe igual, la ficha lo tiene que decir igual".

El hallazgo de Bebé Feliz (paso 7): "Crema de cambio Pequeños Pasos Oxido De Zinc" viene dos veces en el archivo
(120 g y 60 g) y cada una cayó en otra tanda. Una salió con variante "DE CAMBIO OXIDO DE ZINC" y la otra con
"OXIDO DE ZINC", y en dos corridas pasó igual. El detector A/B (semana 3, paso 9) no lo ve: corre cada tanda dos veces
y cada tanda es coherente consigo misma. La contradicción está ENTRE tandas.

La regla, sin IA: dos productos del mismo proveedor que el archivo escribe igual SALVO el contenido, el EAN y el precio
son una "familia" (el mismo producto en otro tamaño). En la ficha tienen que coincidir marca, tipo, variante,
categoría, principio activo, concentración y unidad. Si no coinciden, una de las dos fichas está mal (o el criterio
es ambiguo): se informa con cada versión y sus productos. NO cambia ninguna ficha: decide una persona (paso 8,
decisión de Bauti; el estándar no tiene un motivo de revisión para "inconsistente").

Lo que se compara de cada fila (la "huella de familia") son los textos del archivo, sin lo que cambia entre tamaños:
  - no entran el código, el EAN, el precio ni la fila entera de un PDF (traen el contenido y el EAN adentro);
  - un texto que es solo un contenido ("0,4 kg", "x 50", "2 x 60 un") no entra;
  - a un texto que TERMINA en un contenido se le saca ("ACOND. NATIVA LISO X 200 ML" -> "ACOND. NATIVA LISO";
    "Comp. rec. x 20" -> "Comp. rec."): así Gripanil en comprimidos y en sobres siguen siendo distintos.

Correr: python familias.py   (gratis: lee salida/consolidado/ y salida/resultados.json; guarda salida/familias.json)
"""
import json
import re
from datetime import datetime
from pathlib import Path

from cuentas import separar_contenido, separar_contenido_del_final

CARPETA_SALIDA = Path(__file__).parent / "salida"
# Lo que tiene que coincidir dentro de una familia (lo que cambia entre tamaños: contenido, gtin, precio, descripción)
CAMPOS_DE_FAMILIA = ["marca", "tipo", "variante", "categoria", "principio_activo", "concentracion", "unidad"]
# Columnas del archivo que no son "cómo se llama el producto": cambian entre tamaños o traen todo junto
COLUMNAS_QUE_NO_CUENTAN = {"fila", "bloque", "problemas_extraccion", "codigo", "ean", "precio", "costo"}


def huella_de_familia(original: dict) -> tuple:
    """Los textos de la fila que dicen QUÉ es el producto, sin lo que cambia entre tamaños.

    Ej. Bebé Feliz: {"Producto": "Crema de cambio Pequeños Pasos Oxido De Zinc", "Cantidad": "120 g", "EAN": ...,
    "Precio lista": 252.88} -> (("Producto", "CREMA DE CAMBIO PEQUEÑOS PASOS OXIDO DE ZINC"),)
    """
    partes = []
    for columna, valor in original.items():
        if columna.lower() in COLUMNAS_QUE_NO_CUENTAN or not isinstance(valor, str) or not valor.strip():
            continue  # los números (precio, contenido de Excel) no son texto: no entran
        texto = " ".join(valor.split())
        if separar_contenido(texto)[0] is not None:  # es solo un contenido: "0,4 kg", "x 50", "2 x 60 un"
            continue
        if re.fullmatch(r"[\d\s-]+", texto) or "$" in texto:  # un código de barras o un precio escrito
            continue
        texto = separar_contenido_del_final(texto)[2] or ""  # "ACOND. NATIVA LISO X 200 ML" -> "ACOND. NATIVA LISO"
        texto = re.sub(r"\s*\bx\s*\d[\d.,]*\s*[A-Za-z]*$", "", texto, flags=re.IGNORECASE).strip()  # "Comp. rec. x 20"
        if texto:
            partes.append((columna, texto.upper()))
    return tuple(partes)


def familias_inconsistentes(filas: list[dict], resultados: dict) -> tuple[list[dict], int, int]:
    """Agrupa las filas consolidadas por proveedor + huella y compara sus fichas.

    filas: las de salida/consolidado/*.json (con item_id y original). resultados: item_id -> {ficha, ...}.
    Devuelve (las familias que no coinciden, cuántas familias de 2 o más hay, cuántos productos tienen).
    Una fila sin ficha en resultados no se compara (no hay qué comparar).
    """
    grupos: dict[tuple, list[str]] = {}
    for fila in filas:
        if fila["item_id"] in resultados:
            clave = (fila["item_id"].split(":")[0], huella_de_familia(fila["original"]))
            grupos.setdefault(clave, []).append(fila["item_id"])
    familias = [(clave, items) for clave, items in grupos.items() if len(items) >= 2 and clave[1]]
    inconsistentes = []
    for (proveedor_id, huella), items in familias:
        campos = {}
        for campo in CAMPOS_DE_FAMILIA:
            por_valor: dict[str, list[str]] = {}
            for item_id in items:
                por_valor.setdefault(json.dumps(resultados[item_id]["ficha"].get(campo), ensure_ascii=False), []).append(item_id)
            if len(por_valor) > 1:  # la familia no dice lo mismo en este campo
                campos[campo] = [{"valor": json.loads(valor), "items": ids} for valor, ids in por_valor.items()]
        if campos:
            inconsistentes.append({"proveedor_id": proveedor_id, "en_el_archivo": [texto for _, texto in huella],
                                   "items": items, "campos": campos})
    return inconsistentes, len(familias), sum(len(items) for _, items in familias)


def revisar(carpeta_consolidado: Path, ruta_resultados: Path, ruta_salida: Path | None = None) -> dict:
    """Lee lo consolidado y las fichas escritas, busca las familias que no coinciden y (si se pide) lo guarda."""
    resultados = json.loads(ruta_resultados.read_text(encoding="utf-8")) if ruta_resultados.exists() else {}
    filas = [fila for ruta in sorted(carpeta_consolidado.glob("*.json"))
             for fila in json.loads(ruta.read_text(encoding="utf-8"))["filas"]]
    inconsistentes, familias, productos = familias_inconsistentes(filas, resultados)
    informe = {"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "familias": familias, "productos_en_familias": productos,
               "inconsistentes": inconsistentes}
    if ruta_salida:
        ruta_salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    return informe


def mostrar(informe: dict) -> None:
    print(f"\n=== Familias: {informe['familias']} familia(s) de 2 o más productos ({informe['productos_en_familias']}"
          f" productos) · {len(informe['inconsistentes'])} no coinciden"
          + (" (detalle en salida/familias.json; no se cambia ninguna ficha: decide una persona)"
             if informe["inconsistentes"] else ""))
    for familia in informe["inconsistentes"]:
        print(f"   ≠ {familia['proveedor_id']} «{' · '.join(familia['en_el_archivo'])}»")
        for campo, versiones in familia["campos"].items():
            detalle = " vs ".join(f"{v['valor']!r} ({', '.join(i.split(':')[1] for i in v['items'])})" for v in versiones)
            print(f"       {campo}: {detalle}")


def main():
    informe = revisar(CARPETA_SALIDA / "consolidado", CARPETA_SALIDA / "resultados.json", CARPETA_SALIDA / "familias.json")
    mostrar(informe)


if __name__ == "__main__":
    main()
