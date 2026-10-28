"""Pedido al proveedor (semana 2, paso 9, el extra): el mensaje listo con lo que falta para cerrar sus revisiones.

Responde la Q16 ("¿Qué le tengo que pedir a Dermalab para cerrar sus revisiones?").
Lo arma el CÓDIGO, sin IA (gratis y sin inventar), con tres cosas que ya existen:
  - resultados.json: el estado, los motivos y la ficha de cada producto (lo que registró el agente);
  - las filas del servidor: los conflictos con sus dos versiones y sus fuentes (los encontró el código);
  - el catálogo: la descripción del SKU de un posible duplicado.
Solo se piden datos que tiene que dar el proveedor (decisión 1): lo que decidimos nosotros
(categoría, descripción) no se le pide. No se manda nada: se guarda el mensaje para que lo mande una persona.

Correr: python pedido_proveedor.py        (todos los proveedores habilitados)
        python pedido_proveedor.py P05    (solo uno)
"""
import argparse
import csv
import json
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
RUTA_RESULTADOS = CARPETA_PROYECTO / "salida" / "resultados.json"
RUTA_PROVEEDORES = CARPETA_PROYECTO / "Data" / "proveedores" / "proveedores.csv"
CARPETA_PEDIDOS = CARPETA_PROYECTO / "salida" / "pedidos"

# Lo que se le puede pedir a un proveedor cuando falta, en el orden en que va en el mensaje.
# Los de medicamento solo se piden en una lista de medicamentos (la que trae condición de venta).
PEDIBLES = [
    ("precio_costo", "El precio de costo (de lista, sin IVA)."),
    ("contenido", "El contenido neto."),
    ("principio_activo", "La monodroga (principio activo)."),
    ("concentracion", "La concentración."),
    ("condicion_venta", "La condición de venta (venta libre o bajo receta)."),
]
DE_MEDICAMENTO = {"principio_activo", "concentracion", "condicion_venta"}


def fuente_texto(fuente: dict | None) -> str:
    """Una fuente en palabras: "archivo.pdf, pág. 1" / "archivo.csv, línea 5" / "archivo.xlsx, hoja H, fila 12"."""
    if not fuente:
        return "sin fuente"
    partes = [fuente["archivo"]]
    if "pagina" in fuente:
        partes.append(f"pág. {fuente['pagina']}")
    if "linea" in fuente:
        partes.append(f"línea {fuente['linea']}")
    if "hoja" in fuente:
        partes.append(f"hoja {fuente['hoja']}, fila {fuente['fila']}")
    return ", ".join(partes)


def pendientes_del_item(resultado: dict, fila: dict, catalogo_por_sku: dict) -> tuple[list[str], list[str]]:
    """Lo que hay que pedirle al proveedor para cerrar UN producto, y los motivos que no se resuelven pidiendo.

    resultado: lo que registró el agente (resultados.json). fila: la del servidor (original + calculado).
    Devuelve (pedidos, sin_pedido):
      - pedidos: frases listas para el mensaje, una por dato que falta.
      - sin_pedido: motivos de revisión que no se tradujeron en ningún pedido. No desaparecen en silencio:
        el que corre el script los ve (por ejemplo, un dato faltante que decidimos nosotros, no el proveedor).
    """
    motivos, ficha, calculado = resultado["motivos_revision"], resultado["ficha"], fila["calculado"]
    pedidos, sin_pedido = [], []

    # El código de barras
    if "gtin_invalido" in motivos:
        pedidos.append("El código de barras (EAN-13): el que figura en el archivo no es válido.")
    elif "gtin_faltante" in motivos:
        pedidos.append("El código de barras (EAN-13).")

    # Los datos obligatorios que faltan y que tiene que dar el proveedor (no los que decidimos nosotros)
    en_conflicto = {conflicto["campo"] for conflicto in calculado.get("conflictos", [])}
    es_medicamento = "condicion_venta" in calculado  # lo sabe el código: solo las listas de medicamentos la traen
    if "dato_obligatorio_faltante" in motivos:
        faltantes = [texto for campo, texto in PEDIBLES
                     if ficha.get(campo) is None and campo not in en_conflicto
                     and (campo not in DE_MEDICAMENTO or es_medicamento)]
        pedidos += faltantes
        if not faltantes:
            sin_pedido.append("dato_obligatorio_faltante")

    # Los conflictos: las dos versiones, cada una con su fuente, para que el proveedor diga cuál es la correcta
    for conflicto in calculado.get("conflictos", []):
        primera, segunda = conflicto["versiones"]
        pedidos.append(f"El {conflicto['campo'].replace('_', ' ')} no coincide entre sus archivos: "
                       f"\"{primera['valor']}\" ({fuente_texto(primera['fuente'])}) y "
                       f"\"{segunda['valor']}\" ({fuente_texto(segunda['fuente'])}). ¿Cuál es el correcto?")
    if "conflicto_entre_fuentes" in motivos and not calculado.get("conflictos"):
        sin_pedido.append("conflicto_entre_fuentes")

    # El posible duplicado: que confirme si es el mismo producto que ya tenemos
    if "posible_duplicado" in motivos:
        candidato = catalogo_por_sku.get(resultado.get("duplicado_de"))
        if candidato:
            pedidos.append(f"¿Es el mismo producto que ya tenemos cargado como \"{candidato['descripcion']}\" "
                           f"({candidato['sku']})?")
        else:
            sin_pedido.append("posible_duplicado")

    # La ficha de datos de seguridad: también en un duplicado (el depósito la necesita igual, decisión 3)
    if ficha.get("peligro_deposito") == "pendiente_fds":
        pedidos.append("La ficha de datos de seguridad (FDS).")

    return pedidos, sin_pedido


def armar_mensaje(nombre_proveedor: str, items: list[dict]) -> str:
    """El mensaje entero para un proveedor. items: [{"codigo", "descripcion", "fuente", "pedidos"}], en orden.

    Un proveedor sin nada que pedir no tiene mensaje: devuelve "" (no se le escribe para decirle que está todo bien).
    """
    if not items:
        return ""
    renglones = [
        f"Asunto: Datos pendientes para el alta de productos — {nombre_proveedor}",
        "",
        f"Hola, equipo de {nombre_proveedor}:",
        "",
        "Para terminar el alta de los productos que nos mandaron, nos faltan estos datos:",
    ]
    for item in items:
        renglones += ["", f"{item['codigo']} · {item['descripcion']} ({fuente_texto(item['fuente'])})"]
        renglones += [f"  - {pedido}" for pedido in item["pedidos"]]
    renglones += ["", "Con esto completamos las fichas y los damos de alta. ¡Muchas gracias!", ""]
    return "\n".join(renglones)


def nombres_de_proveedores() -> dict[str, str]:
    """proveedor_id -> nombre, desde proveedores.csv ("P05" -> "Dermalab S.A.")."""
    with open(RUTA_PROVEEDORES, encoding="utf-8-sig", newline="") as archivo:
        return {fila["proveedor_id"]: fila["nombre"] for fila in csv.DictReader(archivo)}


def main():
    """Arma el pedido de cada proveedor con lo que dejó la última corrida, y lo guarda en salida/pedidos/."""
    import servidor_mcp  # acá y no arriba: las pruebas de las funciones no necesitan levantar el servidor

    argumentos = argparse.ArgumentParser(description="Arma el pedido de datos pendientes para cada proveedor.")
    argumentos.add_argument("proveedor_id", nargs="?", help="Un proveedor (ej. P05). Sin nada: todos los habilitados.")
    proveedor_pedido = argumentos.parse_args().proveedor_id
    if proveedor_pedido and proveedor_pedido not in servidor_mcp.PROVEEDORES:
        raise SystemExit(f"ERROR: {proveedor_pedido} no es un proveedor habilitado ({', '.join(servidor_mcp.PROVEEDORES)})")

    resultados = json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))
    catalogo_por_sku = {producto["sku"]: producto for producto in servidor_mcp.CATALOGO}
    nombres = nombres_de_proveedores()
    CARPETA_PEDIDOS.mkdir(parents=True, exist_ok=True)

    for proveedor_id, config in servidor_mcp.PROVEEDORES.items():
        if proveedor_pedido and proveedor_id != proveedor_pedido:
            continue
        filas = servidor_mcp.leer_filas(proveedor_id, config)
        items, avisos = [], []
        for fila in filas:  # en el orden del archivo del proveedor
            resultado = resultados.get(fila["item_id"])
            if resultado is None:  # cobertura: un producto sin ficha no desaparece en silencio
                avisos.append(f"{fila['item_id']}: no está en resultados.json (¿falta correr el agente?)")
                continue
            pedidos, sin_pedido = pendientes_del_item(resultado, fila, catalogo_por_sku)
            avisos += [f"{fila['item_id']}: el motivo {motivo} no se traduce en un pedido al proveedor"
                       for motivo in sin_pedido]
            if pedidos:
                codigo = fila["item_id"].split(":", 1)[1]
                descripcion = resultado["ficha"].get("descripcion") or fila["original"].get("descripcion") or ""
                items.append({"codigo": codigo, "descripcion": descripcion, "fuente": fila["fuente"],
                              "pedidos": pedidos})

        nombre = nombres.get(proveedor_id, proveedor_id)
        mensaje = armar_mensaje(nombre, items)
        print(f"\n=== {proveedor_id} {nombre}: {len(items)} productos con datos pendientes ===")
        ruta = CARPETA_PEDIDOS / f"pedido_{proveedor_id}.md"
        if mensaje:
            ruta.write_text(mensaje, encoding="utf-8")
            print(mensaje)
            print(f"(guardado en {ruta.relative_to(CARPETA_PROYECTO)})")
        else:
            ruta.unlink(missing_ok=True)  # si antes había un pedido y ya no falta nada, no queda uno viejo
            print("Nada que pedir.")
        for aviso in avisos:
            print(f"⚠ {aviso}")


if __name__ == "__main__":
    main()