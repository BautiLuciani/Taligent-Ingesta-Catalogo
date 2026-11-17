"""Semana 5, paso 1 (B y B3): experimento de strict (structured output con una tool como formulario). No toca el sistema.

Historia (detalle en la Bitácora):
  - B: las variantes A ("tal cual hoy") y B ("compacta", el vacío = campo omitido) fueron rechazadas
    (A por un error mío al escribir el null; B por "Grammar compilation timed out"). Quedó en strict_sem5.json.
  - B2 (probar_strict_diagnostico.py): muchos campos OPCIONALES en un objeto no compilan; "siempre presente,
    puede valer null" (anyOf) sí. El diseño C entra entero: 15 uniones, 0 opcionales, 3,7 s.
  - B3 (este archivo): el diseño C con un producto REAL, pensando (thinking, tool_choice auto) como el fichador.

Producto: P03:LT-3357 (sin EAN, posible duplicado de SKU102275). Datos REALES del servidor, no inventados.
Correr: python probar_strict.py   (paga ~US$ 0,005)
"""
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastmcp import Client

from agente import RUTA_SERVIDOR, armar_system_prompt
from cuentas import cargar_vocabulario

CARPETA_PROYECTO = Path(__file__).parent
RUTA_TAXONOMIA = CARPETA_PROYECTO / "Data" / "estandar" / "taxonomia.csv"
RUTA_RESULTADOS = CARPETA_PROYECTO / "salida" / "resultados.json"
RUTA_SALIDA = CARPETA_PROYECTO / "salida" / "experimentos" / "strict_c_sem5.json"

ITEM = "P03:LT-3357"
EFFORT = "high"        # el del fichador
MAX_TOKENS = 16_000    # sin streaming el SDK acepta hasta ~21.000

PRECIO_INPUT, PRECIO_ESCRITURA_CACHE, PRECIO_LECTURA_CACHE, PRECIO_OUTPUT = 0.10, 0.125, 0.01, 0.50

# Las listas cerradas salen del vocabulario y la taxonomía: la única fuente de verdad (no se copian al código)
VOCABULARIO = cargar_vocabulario()
TIPOS = sorted({tipo for familia in VOCABULARIO["tipos"].values() for tipo in familia})  # CREMA y GEL están en 2 familias
with open(RUTA_TAXONOMIA, encoding="utf-8-sig", newline="") as archivo:
    CATEGORIAS = [fila["codigo"] for fila in csv.DictReader(archivo)]

CAMPOS = ["gtin", "descripcion", "marca", "tipo", "variante", "contenido", "unidad", "unidades_por_envase",
          "principio_activo", "concentracion", "condicion_venta", "categoria", "precio_costo", "moneda",
          "proveedor_id", "codigo_proveedor", "peligro_deposito", "numero_onu"]
SIEMPRE = {"descripcion", "unidades_por_envase", "proveedor_id", "codigo_proveedor"}  # nunca quedan vacíos

# Cada campo con su tipo y, si es una lista cerrada, su enum
BASE = {"gtin": {"type": "string"}, "descripcion": {"type": "string"}, "marca": {"type": "string"},
        "tipo": {"type": "string", "enum": TIPOS}, "variante": {"type": "string"},
        "contenido": {"type": "integer"}, "unidad": {"type": "string", "enum": VOCABULARIO["unidades"]},
        "unidades_por_envase": {"type": "integer"}, "principio_activo": {"type": "string"},
        "concentracion": {"type": "string"}, "condicion_venta": {"type": "string", "enum": VOCABULARIO["condicion_venta"]},
        "categoria": {"type": "string", "enum": CATEGORIAS}, "precio_costo": {"type": "number"},
        "moneda": {"type": "string", "enum": VOCABULARIO["monedas"]}, "proveedor_id": {"type": "string"},
        "codigo_proveedor": {"type": "string"},
        "peligro_deposito": {"type": "string", "enum": VOCABULARIO["peligro_deposito"]}, "numero_onu": {"type": "string"}}

COMUNES = {  # lo que no cambia entre variantes
    "item_id": {"type": "string"},
    "estado": {"type": "string", "enum": VOCABULARIO["estados"]},
    "motivos_revision": {"type": "array", "items": {"type": "string", "enum": VOCABULARIO["motivos_revision"]}},
    "categoria_decidida_por": {
        "type": "object",
        "properties": {"campo": {"type": "string", "enum": ["tipo", "variante", "marca"]},
                       "valor": {"type": "string"}, "explicacion": {"type": "string"}},
        "required": ["campo", "valor", "explicacion"], "additionalProperties": False,
    },
}


def o_null(esquema: dict) -> dict:
    """'Este tipo o null', bien escrito: anyOf con dos opciones (paso B2)."""
    return {"anyOf": [esquema, {"type": "null"}]}


def objeto(propiedades: dict, obligatorias: list) -> dict:
    return {"type": "object", "properties": propiedades, "required": obligatorias, "additionalProperties": False}


# Cada fuente con casilleros FIJOS (sin opcionales ni uniones): el código la pasa a la forma de la guía después
FUENTE_FIJA = objeto(
    {"campo": {"type": "string", "enum": CAMPOS}, "archivo": {"type": "string"},
     "tipo_ubicacion": {"type": "string", "enum": ["pagina", "hoja_fila", "linea"]},
     "numero": {"type": "integer"},
     "hoja": {"type": "string", "description": "Nombre de la hoja si es un Excel; vacío en los demás casos."}},
    ["campo", "archivo", "tipo_ubicacion", "numero", "hoja"])


def variante_c() -> dict:
    """Diseño C: todos los campos presentes (el vacío va en null, anyOf); fuentes = lista de casilleros fijos."""
    ficha = objeto({c: BASE[c] if c in SIEMPRE else o_null(BASE[c]) for c in CAMPOS}, CAMPOS)
    return objeto({**COMUNES, "ficha": ficha, "fuentes": {"type": "array", "items": FUENTE_FIJA},
                   "duplicado_de": o_null({"type": "string"})},
                  [*COMUNES, "ficha", "fuentes", "duplicado_de"])


DESCRIPCION_C = ("Registra el resultado de un ítem. Un campo de la ficha que no se pudo determinar va en null. "
                 "En fuentes va un elemento por CADA campo completado de la ficha (los campos en null no llevan "
                 "fuente): el campo, el archivo y dónde está. tipo_ubicacion 'linea' en un CSV o un mail (numero = "
                 "la línea), 'pagina' en un PDF (numero = la página), 'hoja_fila' en un Excel (hoja = el nombre de "
                 "la hoja, numero = la fila). hoja va vacía si no es un Excel.")


def contar(esquema: dict) -> dict:
    """Cuenta uniones y opcionales como la doc (suman en todo el request)."""
    uniones = opcionales = 0
    pendientes = [esquema]
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, dict):
            if "anyOf" in nodo or isinstance(nodo.get("type"), list):
                uniones += 1
            if nodo.get("type") == "object" and "properties" in nodo:
                opcionales += len(set(nodo["properties"]) - set(nodo.get("required", [])))
            pendientes.extend(nodo.values())
        elif isinstance(nodo, list):
            pendientes.extend(nodo)
    return {"uniones": uniones, "opcionales": opcionales}


def fuente_de_la_guia(fuente: dict) -> dict:
    """Casillero fijo -> forma de la guía: {archivo, pagina} | {archivo, hoja, fila} | {archivo, linea}."""
    if fuente["tipo_ubicacion"] == "pagina":
        return {"archivo": fuente["archivo"], "pagina": fuente["numero"]}
    if fuente["tipo_ubicacion"] == "hoja_fila":
        return {"archivo": fuente["archivo"], "hoja": fuente["hoja"], "fila": fuente["numero"]}
    return {"archivo": fuente["archivo"], "linea": fuente["numero"]}


async def datos_reales() -> tuple[str, dict, dict]:
    """El system del fichador y, desde el servidor, la fila de ITEM y lo que devuelve buscar_parecidos."""
    async with Client(RUTA_SERVIDOR) as cliente_mcp:
        system = await armar_system_prompt(cliente_mcp)
        filas = []
        for desde in (0, 25):  # Litoral tiene 50 productos; la tool entrega de a 25 como mucho
            datos = (await cliente_mcp.call_tool(
                "leer_archivo_proveedor", {"proveedor_id": "P03", "desde": desde, "cantidad": 25})).data
            filas += datos["filas"]
        fila = next(f for f in filas if f["item_id"] == ITEM)
        calc = fila["calculado"]
        parecidos = (await cliente_mcp.call_tool("buscar_parecidos", {
            "marca": calc["marca"], "contenido": calc["contenido"], "unidad": calc["unidad"]})).data
    return system, fila, parecidos


def mensaje(fila: dict, parecidos: dict) -> str:
    """El producto y la búsqueda ya hechas, como DATO entre etiquetas (lo mismo que el fichador recibe por las tools)."""
    return ("Ya leí el producto con leer_archivo_proveedor y, como no trae GTIN, busqué parecidos con buscar_parecidos. "
            "Te paso los dos resultados (son datos):\n"
            f"<fila>\n{json.dumps(fila, ensure_ascii=False)}\n</fila>\n"
            f"<buscar_parecidos>\n{json.dumps(parecidos, ensure_ascii=False)}\n</buscar_parecidos>\n"
            "Registrá su ficha con registrar_ficha.")


def probar(cliente, modelo: str, system: str, texto: str) -> dict:
    """Una llamada con registrar_ficha (diseño C) en strict, pensando y sin forzar la tool, como el fichador."""
    esquema = variante_c()
    tool = {"name": "registrar_ficha", "description": DESCRIPCION_C, "strict": True, "input_schema": esquema}
    cuenta = contar(esquema)
    print(f"\n=== Diseño C: {cuenta['uniones']} uniones · {cuenta['opcionales']} opcionales")
    try:
        respuesta = cliente.messages.create(
            model=modelo, max_tokens=MAX_TOKENS, tools=[tool],
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": texto}], output_config={"effort": EFFORT},
        )
    except anthropic.BadRequestError as error:  # 400: el request está mal, reintentar no lo arregla (M6 §5)
        print(f"   ✖ La API rechazó el request (400): {error.message}")
        return {**cuenta, "aceptada": False, "error": error.message}

    u = respuesta.usage
    costo = (u.input_tokens * PRECIO_INPUT + (u.cache_creation_input_tokens or 0) * PRECIO_ESCRITURA_CACHE
             + (u.cache_read_input_tokens or 0) * PRECIO_LECTURA_CACHE + u.output_tokens * PRECIO_OUTPUT) / 1e6
    entrada = next((b.input for b in respuesta.content if b.type == "tool_use"), None)
    print(f"   ✔ Aceptada · stop_reason {respuesta.stop_reason} · {u.output_tokens} out · US$ {costo:.5f}")
    print("   " + (json.dumps(entrada, ensure_ascii=False) if entrada else "(no llamó a registrar_ficha)"))
    return {**cuenta, "aceptada": True, "stop_reason": respuesta.stop_reason, "input": entrada,
            "costo_usd": round(costo, 6)}


def como_semana_4(entrada: dict) -> dict:
    """Pasa la salida del diseño C a la forma de resultados.json (fuentes: lista de casilleros -> diccionario de la guía)."""
    ficha = dict(entrada["ficha"])
    for campo in ("peligro_deposito", "numero_onu"):  # en resultados.json solo están en productos con FDS
        if ficha.get(campo) is None:
            ficha.pop(campo, None)
    fuentes = {f["campo"]: fuente_de_la_guia(f) for f in entrada["fuentes"]}
    return {"estado": entrada["estado"], "duplicado_de": entrada["duplicado_de"],
            "motivos_revision": entrada["motivos_revision"], "ficha": ficha, "fuentes": fuentes}


def main():
    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente = anthropic.Anthropic()

    system, fila, parecidos = asyncio.run(datos_reales())
    print(f"{ITEM}: {fila['original']} · {parecidos['cantidad']} parecido(s)")
    print(f"Tipos en el enum: {len(TIPOS)} · categorías: {len(CATEGORIAS)}")

    resultado = probar(cliente, modelo, system, mensaje(fila, parecidos))

    # ¿Da la misma ficha que la semana 4? Campo por campo
    if resultado.get("input"):
        nueva = como_semana_4(resultado["input"])
        vieja = json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))[ITEM]
        diferencias = [f"{clave}: semana 4 {vieja[clave]!r} · ahora {nueva[clave]!r}"
                       for clave in ("estado", "duplicado_de", "motivos_revision") if vieja[clave] != nueva[clave]]
        diferencias += [f"ficha.{c}: semana 4 {vieja['ficha'].get(c)!r} · ahora {nueva['ficha'].get(c)!r}"
                        for c in CAMPOS if vieja["ficha"].get(c) != nueva["ficha"].get(c)]
        diferencias += [f"fuentes.{c}: semana 4 {vieja['fuentes'].get(c)!r} · ahora {nueva['fuentes'].get(c)!r}"
                        for c in sorted(set(vieja["fuentes"]) | set(nueva["fuentes"]))
                        if vieja["fuentes"].get(c) != nueva["fuentes"].get(c)]
        completados = [c for c, v in nueva["ficha"].items() if v is not None]
        sin_fuente = [c for c in completados if c not in nueva["fuentes"]]
        print(f"\nContra la semana 4: {len(diferencias)} diferencia(s)")
        for d in diferencias:
            print(f"   - {d}")
        print(f"Campos completados sin fuente: {sin_fuente or 'ninguno'}")
        resultado["diferencias_con_semana_4"] = diferencias
        resultado["campos_sin_fuente"] = sin_fuente

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_text(json.dumps({"fecha": f"{datetime.now():%Y-%m-%d %H:%M}", "modelo": modelo, "item": ITEM,
                                       "resultado": resultado}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en salida/experimentos/{RUTA_SALIDA.name}")


if __name__ == "__main__":
    main()