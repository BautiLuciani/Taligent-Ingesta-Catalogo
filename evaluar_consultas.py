"""El evaluador del asistente (semana 6, paso 4): las 29 consultas contra las respuestas esperadas.

Uso:
    python evaluar_consultas.py               # le pregunta TODO al asistente y califica (PAGA, ~US$ 0,06, ~4 min)
    python evaluar_consultas.py --solo Q07 V01  # solo esas
    python evaluar_consultas.py --guardadas   # vuelve a calificar las últimas respuestas guardadas (gratis)

La métrica es la de la guía (sección 5, "acierto de consultas"): una consulta está bien si los productos y el valor
coinciden, las fuentes que corresponden están entre las citadas y, cuando algo no está en lo generado, el asistente lo
dice en vez de contestar igual. Las sueltas van cada una en una conversación nueva; cada conversación (V01, V02), con
sus 3 turnos en la MISMA conversación (se mide que sostenga el hilo).

Calificar es código puro (sin IA, determinista, M1): primero se guardan las respuestas y después se califican, así un
cambio en el evaluador no obliga a volver a pagar.
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from agente import CARPETA_PROYECTO, CARPETA_TRAZAS, RUTA_SERVIDOR

RUTA_ESPERADAS = CARPETA_PROYECTO / "evaluacion" / "consultas_esperadas.json"
CARPETA_CONSULTAS = CARPETA_PROYECTO / "salida" / "consultas"
RUTA_RESPUESTAS = CARPETA_CONSULTAS / "respuestas.json"
RUTA_EVALUACION = CARPETA_CONSULTAS / "evaluacion.json"

# Cómo se puede decir cada motivo o estado en el texto (el prompt le pide al asistente palabras, no nombres internos).
# Sirve solo para reconocer el VALOR esperado cuando el asistente lo escribe con palabras.
SINONIMOS = {
    "gtin_faltante": ["gtin faltante", "sin ean", "sin codigo de barras", "no trae ean", "no tiene ean", "no informa"],
    "gtin_invalido": ["gtin invalido", "digito verificador", "ean invalido", "codigo invalido"],
    "dato_obligatorio_faltante": ["dato obligatorio faltante", "obligatorio", "principio activo"],
    "conflicto_entre_fuentes": ["conflicto entre fuentes", "conflicto", "no coinciden", "dicen contenidos distintos",
                                "valores distintos", "dicen distinto"],
    "discontinuado": ["discontinuad"],
    "lista_para_alta": ["lista para alta", "listo para alta", "lista para el alta"],
    "a_revision": ["a revision", "en revision", "sigue a revision", "queda a revision"],
    "duplicado": ["duplicado"],
}


# --- Calificar: código puro ---

def normalizar(texto) -> str:
    """Minúsculas, sin acentos, guiones bajos como espacios y espacios simples."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower().replace("_", " ")
    return re.sub(r"\s+", " ", texto).strip()


def numeros_del_texto(texto: str) -> list[float]:
    """Los números escritos en un texto, leídos con coma o punto decimal ("320,80", "10.66", "1.234,5")."""
    numeros = []
    for crudo in re.findall(r"\d+(?:[.,]\d+)*", texto or ""):
        candidatos = {crudo.replace(".", "").replace(",", "."), crudo.replace(",", "")}
        for candidato in candidatos:
            try:
                numeros.append(float(candidato))
            except ValueError:
                pass
    return numeros


def valor_coincide(esperado, respuesta: dict) -> bool:
    """¿El valor esperado está en la respuesta? Un número: en 'valor' o escrito en el texto (tolerancia 0,01). Un texto
    (código, SKU, estado o motivo): en 'valor' o en el texto, también dicho con palabras (SINONIMOS)."""
    if esperado is None:
        return True
    if isinstance(esperado, (int, float)):
        en_valor = numeros_del_texto(str(respuesta.get("valor"))) if respuesta.get("valor") is not None else []
        return any(abs(n - esperado) < 0.01 for n in en_valor + numeros_del_texto(respuesta.get("texto", "")))
    formas = [normalizar(esperado)] + [normalizar(s) for s in SINONIMOS.get(esperado, [])]
    donde = normalizar(respuesta.get("valor")) + " | " + normalizar(respuesta.get("texto"))
    return any(forma in donde for forma in formas)


def menciona(respuesta: dict, requisito) -> bool:
    """Un texto que tiene que aparecer, o una lista de alternativas (alcanza con una)."""
    alternativas = requisito if isinstance(requisito, list) else [requisito]
    texto = normalizar(respuesta.get("texto"))
    return any(normalizar(a) in texto for a in alternativas)


def clave_fuente(fuente: dict) -> tuple:
    if "linea" in fuente:
        return (fuente["archivo"], "linea", int(fuente["linea"]))
    if "pagina" in fuente:
        return (fuente["archivo"], "pagina", int(fuente["pagina"]))
    return (fuente["archivo"], "hoja", fuente.get("hoja"), "fila", int(fuente["fila"]))


def calificar(esperada: dict, respuesta: dict) -> dict:
    """Los chequeos de una consulta. 'ok' = todos bien (el acierto de consultas de la guía)."""
    chequeos = {}
    if esperada.get("no_esta"):
        # Lo que no está: tiene que decirlo (esta_en_lo_generado false) y no dar un valor. Puede nombrar un dato
        # relacionado que sí existe (Q23: el precio de costo), así que productos y fuentes no se exigen vacíos.
        chequeos["dice_que_no_esta"] = respuesta.get("esta_en_lo_generado") is False
        chequeos["no_inventa_valor"] = respuesta.get("valor") is None
    else:
        chequeos["esta_en_lo_generado"] = respuesta.get("esta_en_lo_generado") is True
        chequeos["productos"] = sorted(respuesta.get("items", [])) == sorted(esperada["items"])
        chequeos["valor"] = valor_coincide(esperada.get("valor"), respuesta)
        citadas = {clave_fuente(f) for f in respuesta.get("fuentes", [])}
        chequeos["fuentes"] = all(clave_fuente(f) in citadas for f in esperada.get("fuentes", []))
        for requisito in esperada.get("debe_mencionar", []):
            nombre = "menciona " + (requisito if isinstance(requisito, str) else requisito[0])
            chequeos[nombre] = menciona(respuesta, requisito)
    return {"ok": all(chequeos.values()), "chequeos": chequeos}


def casos(esperadas: dict, solo: set[str] | None) -> list[tuple[str, list[dict]]]:
    """(id, turnos): una suelta es una conversación de un turno; V01 y V02, de tres."""
    lista = [(c["id"], [c]) for c in esperadas["consultas"]]
    lista += [(v["id"], v["turnos"]) for v in esperadas["conversaciones"]]
    return [(id_, turnos) for id_, turnos in lista if not solo or id_ in solo]


def id_del_turno(id_caso: str, indice: int, cantidad: int) -> str:
    return id_caso if cantidad == 1 else f"{id_caso}.{indice + 1}"


def informe(esperadas: dict, respuestas: dict, solo: set[str] | None) -> dict:
    """Califica todo lo guardado y arma el informe (por turno, totales y costo)."""
    detalle, bien, total = [], 0, 0
    for id_caso, turnos in casos(esperadas, solo):
        for indice, esperada in enumerate(turnos):
            id_turno = id_del_turno(id_caso, indice, len(turnos))
            respuesta = respuestas.get(id_turno)
            if respuesta is None:
                continue
            nota = calificar(esperada, respuesta)
            total += 1
            bien += nota["ok"]
            detalle.append({"id": id_turno, "pregunta": esperada["texto"], **nota,
                            "fallan": [k for k, v in nota["chequeos"].items() if not v],
                            "costo_usd": respuesta.get("costo_usd", 0), "segundos": respuesta.get("segundos", 0)})
    costo = sum(d["costo_usd"] for d in detalle)
    return {"bien": bien, "total": total, "costo_usd": round(costo, 4),
            "costo_por_consulta_usd": round(costo / total, 5) if total else 0,
            "segundos": round(sum(d["segundos"] for d in detalle), 1), "detalle": detalle}


def mostrar_informe(datos: dict) -> None:
    for d in datos["detalle"]:
        marca = "OK " if d["ok"] else "MAL"
        extra = "" if d["ok"] else f"  <- falla: {', '.join(d['fallan'])}"
        print(f"[{marca}] {d['id']:<6} {d['pregunta'][:70]}{extra}")
    print(f"\nAcierto de consultas: {datos['bien']}/{datos['total']}"
          f" = {100 * datos['bien'] / datos['total']:.0f}%" if datos["total"] else "\nNada para calificar")
    print(f"Costo: US$ {datos['costo_usd']:.4f} (US$ {datos['costo_por_consulta_usd']:.5f} por consulta) · "
          f"{datos['segundos']} s de respuestas")


# --- Preguntar (paga) ---

async def preguntar_todo(esperadas: dict, solo: set[str] | None) -> dict:
    import asistente  # acá adentro: --guardadas no necesita ni la API ni el servidor

    load_dotenv(CARPETA_PROYECTO / ".env")
    modelo = os.getenv("MODELO")
    if not modelo:
        sys.exit("ERROR: falta MODELO en el .env")
    cliente_claude = anthropic.Anthropic()
    CARPETA_TRAZAS.mkdir(parents=True, exist_ok=True)
    ruta_traza = CARPETA_TRAZAS / f"evaluar_consultas_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    respuestas = {}
    async with Client(PythonStdioTransport(str(RUTA_SERVIDOR))) as cliente_mcp:
        for id_caso, turnos in casos(esperadas, solo):
            conversacion = await asistente.abrir(cliente_claude, modelo, cliente_mcp, ruta_traza)  # una nueva por caso
            for indice, esperada in enumerate(turnos):
                id_turno = id_del_turno(id_caso, indice, len(turnos))
                print(f"\n== {id_turno}: {esperada['texto']}")
                respuestas[id_turno] = await conversacion.preguntar(esperada["texto"])
    return respuestas


def main():
    argumentos = argparse.ArgumentParser(description="Evaluador del asistente de consultas (semana 6).")
    argumentos.add_argument("--guardadas", action="store_true", help="Califica las respuestas guardadas (gratis).")
    argumentos.add_argument("--solo", nargs="+", metavar="ID", help="Solo esos casos (Q01..Q23, V01, V02).")
    args = argumentos.parse_args()
    esperadas = json.loads(RUTA_ESPERADAS.read_text(encoding="utf-8"))
    solo = set(args.solo) if args.solo else None

    if args.guardadas:
        if not RUTA_RESPUESTAS.exists():
            sys.exit(f"No hay respuestas guardadas en {RUTA_RESPUESTAS.relative_to(CARPETA_PROYECTO)}: corré sin --guardadas.")
        respuestas = json.loads(RUTA_RESPUESTAS.read_text(encoding="utf-8"))
    else:
        inicio = time.perf_counter()
        respuestas = asyncio.run(preguntar_todo(esperadas, solo))
        print(f"\n(tiempo total: {time.perf_counter() - inicio:.0f} s)")
        CARPETA_CONSULTAS.mkdir(parents=True, exist_ok=True)
        if solo and RUTA_RESPUESTAS.exists():  # con --solo se actualizan esas y se conservan las demás
            respuestas = {**json.loads(RUTA_RESPUESTAS.read_text(encoding="utf-8")), **respuestas}
        RUTA_RESPUESTAS.write_text(json.dumps(respuestas, ensure_ascii=False, indent=2), encoding="utf-8")

    datos = informe(esperadas, respuestas, solo)
    print()
    mostrar_informe(datos)
    if not solo:
        RUTA_EVALUACION.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
