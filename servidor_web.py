"""La interfaz de Ceibo (semana 7): un servidor web chico encima del sistema que ya existe.

No agrega lógica de negocio: lee lo que el sistema dejó en salida/ (y, en los pasos siguientes, llama a las mismas
funciones que usan los comandos). Las pantallas copian el mockup del canvas "Ceibo — Interfaz para el Demo Day".

  web/base.html        el marco común: menú a la izquierda y el contenido a la derecha
  web/paginas/*.html   el contenido de cada pantalla
  web/estilos.css      colores, letra y tamaños del mockup (una sola fuente de verdad)

Starlette y uvicorn: los usa también el MCP por dentro, pero en algunas instalaciones no quedan (a Bauti le faltó
uvicorn en Windows). Van fijados en requirements.txt para no depender de eso.

Correr: python servidor_web.py              (y abrir http://localhost:8000)
        python servidor_web.py --puerto 8001
"""
import argparse
import html
import io
import json
import mimetypes
import os
from datetime import date
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import presentacion
import subir_lista

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_WEB = CARPETA_PROYECTO / "web"
# La misma variable que usa servidor_mcp.py: las pruebas la apuntan a una copia congelada.
CARPETA_SALIDA = Path(os.getenv("INGESTA_CARPETA_SALIDA", CARPETA_PROYECTO / "salida"))
RUTA_RESULTADOS = CARPETA_SALIDA / "resultados.json"
# Los archivos originales de los proveedores (solo lectura): se pueden abrir desde la fuente de cada dato
CARPETA_ARCHIVOS = CARPETA_PROYECTO / "Data" / "proveedores"

# Las 5 pantallas: dirección -> (archivo de web/paginas, título de la pestaña, texto del menú, ícono)
PANTALLAS = {
    "/": ("subir.html", "Subir una lista", "subir"),
    "/fichas": ("fichas.html", "Fichas", "fichas"),
    "/revision": ("revision.html", "Para revisar", "revisar"),
    "/asistente": ("asistente.html", "Asistente", "chat"),
    "/costos": ("costos.html", "Corridas y costos", "costos"),
}

# Lo que suma cada pantalla además de lo común: (hojas de estilo, programas)
RECURSOS = {
    "/": (["/web/subir.css"], ["/web/ceibo.js", "/web/subir.js"]),
    "/fichas": (["/web/fichas.css"], ["/web/ceibo.js", "/web/fichas.js"]),
}
TOPE_DE_SUBIDA = 30 * 1024 * 1024  # 30 MB por archivo: una lista de precios pesa mucho menos

_mesa = None


def mesa() -> subir_lista.MesaDeEntradas:
    """La mesa de entradas de la web (guarda lo subido y corre una lista a la vez). Se arma la primera vez que se usa."""
    global _mesa
    if _mesa is None:
        _mesa = subir_lista.MesaDeEntradas()
    return _mesa

ICONOS = {
    "subir": '<path d="M12 3v12"></path><path d="M7 10l5 5 5-5"></path><path d="M4 19h16"></path>',
    "fichas": '<rect x="4" y="4" width="16" height="16" rx="3"></rect><path d="M8 9h8M8 13h8M8 17h5"></path>',
    "revisar": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"></path><circle cx="12" cy="12" r="3"></circle>',
    "chat": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"></path>',
    "costos": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"></path>',
}


def leer_resultados(ruta: Path | None = None) -> dict:
    """salida/resultados.json (item_id -> resultado). Se lee en cada pedido: si el sistema vuelve a correr, se ve."""
    ruta = ruta or RUTA_RESULTADOS
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def resumen(resultados: dict) -> dict:
    """Los números que aparecen en el menú y en los encabezados, contados de las fichas reales."""
    estados = [r.get("estado") for r in resultados.values()]
    return {
        "total": len(resultados),
        "lista_para_alta": estados.count("lista_para_alta"),
        "duplicado": estados.count("duplicado"),
        "a_revision": estados.count("a_revision"),
        "proveedores": len({r["ficha"]["proveedor_id"] for r in resultados.values() if r.get("ficha")}),
    }


def icono(nombre: str) -> str:
    return ('<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONOS[nombre]}</svg>')


def enlaces_del_menu(activa: str, numeros: dict) -> str:
    """Los 5 enlaces del menú, con la pantalla actual marcada y los números reales al costado."""
    extras = {
        "/fichas": f'<span class="nav-contador">{numeros["total"]}</span>',
        "/revision": f'<span class="nav-insignia">{numeros["a_revision"]}</span>' if numeros["a_revision"] else "",
    }
    enlaces = []
    for direccion, (_, texto, ico) in PANTALLAS.items():
        es_activa = direccion == activa
        clase = "nav-link nav-activo" if es_activa else "nav-link"
        actual = ' aria-current="page"' if es_activa else ""
        enlaces.append(f'<a href="{direccion}" class="{clase}"{actual}>{icono(ico)}'
                       f'<span class="nav-texto">{texto}</span>{extras.get(direccion, "")}</a>')
    return "\n".join(enlaces)


def completar(plantilla: str, valores: dict) -> str:
    """Reemplaza cada {{clave}} de la plantilla. Los valores ya vienen escapados o son HTML armado por el código."""
    for clave, valor in valores.items():
        plantilla = plantilla.replace("{{" + clave + "}}", str(valor))
    return plantilla


def armar_pantalla(direccion: str, resultados: dict) -> str:
    archivo, titulo, _ = PANTALLAS[direccion]
    numeros = resumen(resultados)
    contenido = completar((CARPETA_WEB / "paginas" / archivo).read_text(encoding="utf-8"),
                          {clave: html.escape(str(valor)) for clave, valor in numeros.items()})
    base = (CARPETA_WEB / "base.html").read_text(encoding="utf-8")
    return completar(base, {
        "titulo": html.escape(titulo),
        "enlaces": enlaces_del_menu(direccion, numeros),
        "contenido": contenido,
        "estilos_pagina": "\n".join(f'<link rel="stylesheet" href="{ruta}">' for ruta in RECURSOS.get(direccion, ([], []))[0]),
        "scripts_pagina": "\n".join(f'<script src="{ruta}"></script>' for ruta in RECURSOS.get(direccion, ([], []))[1]),
    })


async def pantalla(request):
    return HTMLResponse(armar_pantalla(request.url.path, leer_resultados()))


async def api_resumen(request):
    return JSONResponse(resumen(leer_resultados()))


async def api_fichas(request):
    """Las fichas reales listas para la pantalla, y los proveedores con cuántas tiene cada uno."""
    fichas = presentacion.fichas_para_pantalla(leer_resultados())
    return JSONResponse({"fichas": fichas, "proveedores": presentacion.proveedores_con_cantidad(fichas)})


async def api_fichas_excel(request):
    """El Excel de las fichas que se están viendo en pantalla (la pantalla manda sus ids, en orden)."""
    try:
        pedido = await request.json()
        ids = [str(i) for i in pedido["ids"]]
    except (ValueError, KeyError, TypeError):
        return PlainTextResponse("Hace falta la lista de fichas (ids).", status_code=400)
    libro = presentacion.armar_excel(leer_resultados(), ids)
    salida = io.BytesIO()
    libro.save(salida)
    nombre = f"Ceibo_fichas_{date.today():%Y-%m-%d}.xlsx"
    return Response(salida.getvalue(), headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def proveedores_procesados(resultados: dict, proveedores: list[dict]) -> list[dict]:
    """La tabla "Listas ya procesadas": cada proveedor con fichas, qué mandó y cómo quedaron (de resultados.json)."""
    filas = []
    for proveedor in proveedores:
        suyos = [r for r in resultados.values() if r.get("item_id", "").startswith(proveedor["id"] + ":")]
        if not suyos:
            continue
        estados = [r["estado"] for r in suyos]
        filas.append({"id": proveedor["id"], "nombre": proveedor["nombre"],
                      "formato": proveedor["mando"],
                      "productos": len(suyos), "alta": estados.count("lista_para_alta"),
                      "duplicado": estados.count("duplicado"), "a_revision": estados.count("a_revision")})
    return filas


async def api_inicio(request):
    """Todo lo que necesita la pantalla Subir una lista además de la carga: los números, la tabla, el desplegable."""
    resultados = leer_resultados()
    proveedores = mesa().proveedores()
    ejemplo = mesa().corrida_de_ejemplo()
    en_curso = mesa().en_curso
    return JSONResponse({
        "numeros": resumen(resultados),
        "procesadas": proveedores_procesados(resultados, proveedores),
        "proveedores": [{k: p[k] for k in ("id", "nombre", "detalle", "habilitado")} for p in proveedores],
        "ejemplo": {"fecha": ejemplo["fecha"]} if ejemplo else None,
        "en_curso": en_curso.id if en_curso and en_curso.estado_publico()["estado"] == "corriendo" else None,
    })


async def api_subir_archivo(request):
    """Un archivo que llega del navegador (el contenido va en el cuerpo, el nombre en la dirección)."""
    nombre = request.query_params.get("nombre", "")
    contenido = await request.body()
    if len(contenido) > TOPE_DE_SUBIDA:
        return JSONResponse({"error": "El archivo pesa más de 30 MB: no parece una lista de precios."}, status_code=413)
    try:
        return JSONResponse(mesa().recibir_archivo(nombre, contenido, request.query_params.get("subida") or None))
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)


async def api_empezar(request):
    try:
        pedido = await request.json()
        corrida = mesa().empezar(str(pedido.get("subida", "")), str(pedido.get("proveedor", "")))
    except (ValueError, AttributeError) as error:
        return JSONResponse({"error": str(error) or "Pedido mal armado."}, status_code=400)
    except RuntimeError as error:
        return JSONResponse({"error": str(error)}, status_code=409)
    return JSONResponse(corrida.estado_publico())


async def api_corrida(request):
    corrida = mesa().corridas.get(request.path_params["id"])
    if corrida is None:
        return JSONResponse({"error": "No encuentro esa corrida (¿se reinició el servidor?)."}, status_code=404)
    return JSONResponse(corrida.estado_publico())


async def api_corrida_de_ejemplo(request):
    ejemplo = mesa().corrida_de_ejemplo()
    if ejemplo is None:
        return JSONResponse({"error": "Todavía no hay ninguna corrida grabada."}, status_code=404)
    return JSONResponse(ejemplo)


def indice_de_archivos(carpeta: Path | None = None) -> dict[str, Path]:
    """Nombre -> ruta de cada archivo original de los proveedores. Solo se sirve lo que está en este índice: desde el
    navegador no se puede pedir ninguna otra ruta del proyecto."""
    carpeta = carpeta or CARPETA_ARCHIVOS
    return {ruta.name: ruta for ruta in sorted(carpeta.rglob("*"))
            if ruta.is_file() and ruta.name != "proveedores.csv" and not ruta.name.startswith("~$")}


async def archivo_original(request):
    """Abre el archivo del proveedor tal cual lo mandó (un PDF se ve en el navegador; un Excel se descarga)."""
    ruta = indice_de_archivos().get(request.path_params["nombre"])
    if ruta is None:
        return PlainTextResponse("Ese archivo no está entre los de los proveedores.", status_code=404)
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    if ruta.suffix.lower() == ".txt":
        tipo = "text/plain; charset=utf-8"
    en_el_navegador = ruta.suffix.lower() in (".pdf", ".txt", ".csv")
    return FileResponse(ruta, media_type=tipo, filename=ruta.name,
                        content_disposition_type="inline" if en_el_navegador else "attachment")


def crear_app() -> Starlette:
    rutas = [Route(direccion, pantalla) for direccion in PANTALLAS]
    rutas += [
        Route("/api/resumen", api_resumen),
        Route("/api/inicio", api_inicio),
        Route("/api/subidas", api_subir_archivo, methods=["POST"]),
        Route("/api/corridas", api_empezar, methods=["POST"]),
        Route("/api/corridas/{id:str}", api_corrida),
        Route("/api/corrida_de_ejemplo", api_corrida_de_ejemplo),
        Route("/api/fichas", api_fichas),
        Route("/api/fichas/excel", api_fichas_excel, methods=["POST"]),
        Route("/archivos/{nombre:str}", archivo_original),
        Mount("/web", app=StaticFiles(directory=CARPETA_WEB), name="web"),
    ]
    return Starlette(routes=rutas)


app = crear_app()


def main():
    parser = argparse.ArgumentParser(description="La interfaz de Ceibo en el navegador.")
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    print(f"Ceibo está en http://localhost:{args.puerto}  (Ctrl+C para cerrar)")
    uvicorn.run(app, host="127.0.0.1", port=args.puerto, log_level="warning")


if __name__ == "__main__":
    main()
