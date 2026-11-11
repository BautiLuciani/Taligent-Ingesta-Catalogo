"""Acuse de recibo (semana 4, paso 9, extra): por cada archivo que entra por la bandeja, un informe legible de lo que
el sistema entendió y decidió solo.

Lo arma el CÓDIGO, sin IA: no cuesta nada y no puede inventar. Solo junta lo que ya decidieron la recepción, el
lector, el escritor y el pedido al proveedor, cada cosa con su evidencia (un ejemplo real del archivo).

Partes:
  9A-1 · lo_que_entendio: proveedor, hoja, columna -> campo con un ejemplo real, contenido, decimal, moneda y filas
         que no son productos.
  9A-2 · el_resultado + el_pedido: cuántas fichas quedaron en cada estado (con el porqué de cada revisión), las
         inestables, los frenos de los hooks y lo que se le pide al proveedor.
  9A-3 · armar_acuse + guardar_acuse + main: el acuse entero según cómo terminó el archivo (también si NO entró o
         lo rechazaron: es cuando más importa enterarse) y guardado en salida/acuses/.

Correr: python acuse.py "entrada/P02_Cosmetica_Rivera/ALTAS RIVERA OCT.xlsx"   (lo regenera gratis, desde lo guardado)
"""
import argparse
import json
import sys
from pathlib import Path

import openpyxl

from lector_excel import leer_tabla_excel
from pedido_proveedor import nombres_de_proveedores
from recepcion import CARPETA_PROYECTO, CARPETA_RECEPCION, contenido_de_la_fila, proveedor_de_la_ruta, ruta_relativa

RUTA_RESULTADOS = CARPETA_PROYECTO / "salida" / "resultados.json"
RUTA_HOOKS = CARPETA_PROYECTO / "salida" / "hooks.json"
CARPETA_PEDIDOS = CARPETA_PROYECTO / "salida" / "pedidos"
RUTA_REGISTRO = CARPETA_PROYECTO / "salida" / "bandeja.json"  # lo que anotó la bandeja de cada archivo
CARPETA_ACUSES = CARPETA_PROYECTO / "salida" / "acuses"

COMO_TERMINO = {"procesado": "PROCESADO ✅", "no_entro": "NO ENTRÓ ⛔", "rechazado": "RECHAZADO ⛔",
                "formato_no_soportado": "FORMATO NO SOPORTADO ⛔", "frenado": "FRENADO ⛔", "error": "ERROR ⛔"}

NOMBRE_DEL_CAMPO = {"descripcion": "descripción", "ean": "código de barras", "precio": "precio de costo",
                    "contenido": "contenido", "unidad": "unidad"}
MOTIVOS = {"gtin_faltante": "sin código de barras", "gtin_invalido": "código de barras inválido",
           "dato_obligatorio_faltante": "falta un dato obligatorio", "conflicto_entre_fuentes": "dos archivos no coinciden",
           "posible_duplicado": "posible duplicado"}
COMO_VIENE_EL_CONTENIDO = {
    "dentro_de_la_descripcion": "dentro de la descripción",
    "cantidad_y_unidad_separadas": "cantidad y unidad en columnas separadas",
    "columna_con_unidad": "en una columna, con su unidad",
}


def resultado_de_recepcion(ruta: Path, proveedor_id: str, carpeta: Path = CARPETA_RECEPCION) -> dict | None:
    """Lo que guardó la recepción para este archivo (salida/recepcion/<proveedor>_<archivo>.json), o None."""
    archivo = carpeta / f"{proveedor_id}_{ruta.stem}.json"
    return json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else None


def primer_valor(filas: list[dict], columna: str) -> str:
    """El primer valor escrito de una columna, tal cual: el ejemplo real que muestra el acuse."""
    valor = next((f["original"][columna] for f in filas
                  if f["original"].get(columna) is not None and str(f["original"][columna]).strip()), None)
    return f'"{valor}"' if isinstance(valor, str) else str(valor)


def ejemplo_de_contenido(filas: list[dict], receta: dict) -> tuple | None:
    """(texto del archivo, fila, contenido, unidad) del primer producto donde el código CONVIRTIÓ algo
    (ej. "4.8 fl oz" -> 142 ML, "0,5 KG" -> 500 G); si no hubo que convertir nada, el primer producto."""
    campos, forma = receta["campos"], receta["contenido_en"]
    columnas = [campos[c] for c in ("contenido", "unidad") if campos.get(c)] or [campos["descripcion"]]
    candidatos = []
    for fila in filas:
        cantidad, unidad = contenido_de_la_fila(fila["original"], forma, campos, receta["separador_decimal"])
        if cantidad is None:
            continue
        texto = " ".join(str(fila["original"][c]) for c in columnas if fila["original"].get(c) is not None)
        candidatos.append((texto, fila["fuente"]["fila"], cantidad, unidad))
        if f"{cantidad}{unidad}" not in texto.upper().replace(" ", ""):  # "400 CC" -> 400 ML: hubo conversión
            return candidatos[-1]
    return candidatos[0] if candidatos else None


def lo_que_entendio(ruta: Path, proveedor_id: str, recepcion: dict) -> list[str]:
    """La sección "Qué entendió el sistema", en renglones de Markdown. Todo sale de lo que ya está guardado."""
    receta, decisiones = recepcion["receta"], recepcion["receta"]["decisiones"]
    tabla = leer_tabla_excel(ruta, receta["hoja"])
    filas = tabla["filas"]
    renglones = [f"- **Proveedor:** {proveedor_id}, por la carpeta donde llegó (`{ruta.parent.name}`)."]

    hojas = openpyxl.load_workbook(ruta, read_only=True).sheetnames
    otras = {h["hoja"]: h["motivo"] for h in decisiones["hojas_que_no_entran"]}
    renglones.append(f"- **Hoja con los productos nuevos:** \"{receta['hoja']}\""
                     + (" (es la única del archivo)." if len(hojas) == 1 else f" ({len(hojas)} hojas en el archivo)."))
    for hoja in hojas:
        if hoja != receta["hoja"]:
            renglones.append(f"  - \"{hoja}\": **NO ENTRA** — {otras.get(hoja, 'no es la hoja de productos nuevos')}")

    renglones.append(f"- **Columnas** (encabezado en la fila {tabla['fila_encabezado']}; {len(filas)} productos):")
    columna_codigo = next((c for c in tabla["columnas"] if filas and c not in filas[0]["original"]), None)
    if columna_codigo:
        renglones.append(f"  - `{columna_codigo}` → código del proveedor · ej. {filas[0]['codigo']}")
    usadas = set()
    for campo, columna in receta["campos"].items():
        usadas.add(columna)
        renglones.append(f"  - `{columna}` → {NOMBRE_DEL_CAMPO.get(campo, campo)} · ej. {primer_valor(filas, columna)}")
    for no_va in decisiones["columnas_que_no_van"]:
        if no_va["columna"] not in usadas and no_va["columna"] != columna_codigo:
            renglones.append(f"  - `{no_va['columna']}` → **NO VA**: {no_va['motivo']}")

    ejemplo = ejemplo_de_contenido(filas, receta)
    linea = f"- **Contenido:** {COMO_VIENE_EL_CONTENIDO.get(receta['contenido_en'], receta['contenido_en'])}"
    if ejemplo:
        linea += f" · ej. fila {ejemplo[1]}: \"{ejemplo[0]}\" → {ejemplo[2]} {ejemplo[3]}"
    renglones.append(linea + ".")
    separador = "coma" if receta["separador_decimal"] == "," else "punto"
    renglones.append(f"- **Decimales con {separador}**" + (f" (se ve en \"{decisiones['evidencia_separador']}\")."
                                                         if decisiones.get("evidencia_separador") else
                                                         " (ningún texto del archivo trae números con decimales: se toma el de español)."))
    renglones.append(f"- **Moneda:** {receta['moneda']} — "
                     + (f"lo dice el archivo: \"{decisiones['evidencia_moneda']}\"." if decisiones.get("evidencia_moneda")
                        else "el archivo no menciona dólares (estándar, sección 6: sin moneda indicada es UYU)."))
    if tabla["ignoradas"]:
        renglones.append("- **Filas escritas que no son productos** (no se cargan): "
                         + ", ".join(f"fila {i['fila']} \"{i['texto']}\"" for i in tabla["ignoradas"]) + ".")
    for aviso in recepcion.get("avisos") or []:
        renglones.append(f"- ⚠ {aviso}")
    return renglones


def leer_json(ruta: Path, si_no_existe):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else si_no_existe


def el_resultado(proveedor_id: str, resultados: dict, hooks: dict) -> list[str]:
    """La sección "Resultado": lo que escribió el escritor para este proveedor (resultados.json), no lo que se cree."""
    suyos = {item: r for item, r in resultados.items() if item.startswith(f"{proveedor_id}:")}
    if not suyos:
        return ["- No hay fichas escritas de este proveedor."]
    por_estado = {e: [r for r in suyos.values() if r["estado"] == e] for e in ("lista_para_alta", "duplicado", "a_revision")}
    renglones = [f"- **{len(suyos)} productos:** {len(por_estado['lista_para_alta'])} listos para alta · "
                 f"{len(por_estado['duplicado'])} duplicados · {len(por_estado['a_revision'])} a revisión."]
    for r in por_estado["duplicado"]:
        renglones.append(f"  - {r['item_id'].split(':', 1)[1]} ya existe en el catálogo: **{r['duplicado_de']}** "
                         f"({r['ficha']['descripcion']}).")
    for r in por_estado["a_revision"]:
        motivos = ", ".join(MOTIVOS.get(m, m) for m in r["motivos_revision"])
        candidato = f" (candidato: {r['duplicado_de']})" if r.get("duplicado_de") else ""
        renglones.append(f"  - {r['item_id'].split(':', 1)[1]} a revisión: {motivos}{candidato}.")
    inestables = [r for r in suyos.values() if r.get("inestable")]
    if inestables:
        renglones.append(f"- ⚠ **{len(inestables)} inestable(s)** (dos corridas no coincidieron; mirar antes del alta):")
        for r in inestables:
            campos = ", ".join(c.split(".")[-1] for c in r["inestable"].get("campos", []))
            renglones.append(f"  - {r['item_id'].split(':', 1)[1]}: no coinciden en {campos or 'sin segunda opinión'}.")
    else:
        renglones.append("- **Inestables:** ninguna marcada.")
    if proveedor_id in hooks.get("proveedores", []):  # hooks.json es de la ÚLTIMA corrida: solo si este proveedor estuvo
        frenos = [f for f in hooks.get("frenos", []) if str(f.get("item_id", "")).startswith(f"{proveedor_id}:")]
        corregidos = sum(1 for f in frenos if f.get("corregido"))
        renglones.append(f"- **Frenos de los hooks** (corrida del {hooks.get('fecha')}): {len(frenos)}"
                         + (f", {corregidos} corregido(s) por el modelo." if frenos else "."))
    return renglones


def el_pedido(proveedor_id: str, carpeta: Path = CARPETA_PEDIDOS) -> list[str]:
    """La sección "Pedido al proveedor": lo que ya armó pedido_proveedor.py (si no hay archivo, no falta nada)."""
    ruta = carpeta / f"pedido_{proveedor_id}.md"
    if not ruta.exists():
        return ["- Nada que pedir: todo lo que hacía falta estaba en el archivo."]
    renglones, actual = [], None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if " · " in linea and not linea.startswith(" "):        # "RIV-1203 · ACONDICIONADOR ... (archivo, fila 7)"
            actual = linea.split(" · ", 1)[0]
        elif linea.startswith("  - ") and actual:                # "  - El código de barras (EAN-13)..."
            renglones.append(f"- {actual}: {linea[4:]}")
    return renglones + [f"- (mensaje completo, listo para mandar: `{ruta_relativa(ruta)}`)"]


def por_que_no_entro(registro: dict, recepcion: dict | None) -> list[str]:
    """Para un archivo que no terminó: el motivo que anotó la bandeja y, si la recepción no lo dejó entrar, cada
    control del código que falló (el modelo propuso, el código verificó: acá se ve qué no cerró)."""
    renglones = [f"- **Motivo:** {registro.get('motivo') or 'sin motivo anotado'}."]
    renglones += [f"  - {problema}" for problema in registro.get("problemas") or []]
    if registro.get("estado") == "no_entro" and recepcion:
        fallados = [c for c in recepcion.get("controles", []) if not c["ok"]]
        renglones += [f"- ✘ Control del código: {c['control']}" + (f" ({c['detalle']})" if c["detalle"] else "")
                      for c in fallados]
    renglones.append("- No se cargó ninguna ficha de este archivo: lo que había antes quedó como estaba.")
    return renglones


def armar_acuse(ruta: Path, registro: dict, resultados: dict, hooks: dict,
                carpeta_recepcion: Path = CARPETA_RECEPCION, carpeta_pedidos: Path = CARPETA_PEDIDOS) -> str:
    """El acuse entero, en Markdown. registro: lo que anotó la bandeja de este archivo (salida/bandeja.json).
    Las carpetas se pueden cambiar para probar con datos congelados (probar_acuse.py)."""
    proveedor_id, estado = registro.get("proveedor_id"), registro.get("estado")
    nombre = nombres_de_proveedores().get(proveedor_id, "proveedor desconocido") if proveedor_id else "proveedor desconocido"
    renglones = [f"# Acuse de recibo — {ruta.name}", "",
                 f"Recibido {registro.get('fecha', '¿?')} · {nombre}" + (f" ({proveedor_id})" if proveedor_id else "")
                 + f" · **{COMO_TERMINO.get(estado, estado)}**", ""]
    recepcion = resultado_de_recepcion(ruta, proveedor_id, carpeta_recepcion) if proveedor_id else None
    if estado != "procesado":
        renglones += ["## Por qué no se procesó", *por_que_no_entro(registro, recepcion)]
        if recepcion and recepcion.get("receta") and ruta.exists():  # entró a la recepción y se frenó después
            renglones += ["", "## Qué había entendido el sistema", *lo_que_entendio(ruta, proveedor_id, recepcion)]
        return "\n".join(renglones) + "\n"
    renglones += ["## Qué entendió el sistema", *lo_que_entendio(ruta, proveedor_id, recepcion), "",
                  "## Resultado", *el_resultado(proveedor_id, resultados, hooks), "",
                  "## Pedido al proveedor", *el_pedido(proveedor_id, carpeta_pedidos), ""]
    costo = registro.get("costo_recepcion_y_fds_usd")
    if costo is not None:
        renglones.append(f"Costo de la recepción y las FDS: US$ {costo:.4f} (las fichas se miden en la corrida del orquestador).")
    renglones.append("Este acuse lo armó el código con lo que ya estaba guardado: no usa IA ni agrega nada.")
    return "\n".join(renglones) + "\n"


def guardar_acuse(ruta: Path, registro: dict, texto: str, carpeta: Path = CARPETA_ACUSES) -> Path:
    """salida/acuses/<proveedor>_<archivo>.md (uno por archivo: si el archivo vuelve a entrar, se reemplaza)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{registro.get('proveedor_id') or 'SIN_PROVEEDOR'}_{ruta.stem}.md"
    destino.write_text(texto, encoding="utf-8")
    return destino


def main():
    argumentos = argparse.ArgumentParser(description="Arma (o regenera) el acuse de recibo de un archivo de la bandeja. Gratis.")
    argumentos.add_argument("archivo", type=Path, help='Ej. "entrada/P08_Importadora_Norte/NorteImports_new_items_Q4.xlsx"')
    ruta = argumentos.parse_args().archivo
    registro = leer_json(RUTA_REGISTRO, {}).get(ruta_relativa(ruta))
    if registro is None:
        raise SystemExit(f"{ruta_relativa(ruta)} no pasó por la bandeja (no está en salida/bandeja.json): no hay nada que acusar.")
    texto = armar_acuse(ruta, registro, leer_json(RUTA_RESULTADOS, {}), leer_json(RUTA_HOOKS, {}))
    destino = guardar_acuse(ruta, registro, texto)
    print(texto)
    print(f"(guardado en {destino.relative_to(CARPETA_PROYECTO).as_posix()})")


if __name__ == "__main__":
    main()
