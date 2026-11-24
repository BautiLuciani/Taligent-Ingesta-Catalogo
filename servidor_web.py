"""La interfaz de Ceibo (semana 7): un servidor web chico encima del sistema que ya existe.

No agrega lógica de negocio: lee lo que el sistema dejó en salida/ (y, en los pasos siguientes, llama a las mismas
funciones que usan los comandos). Las pantallas copian el mockup del canvas "Ceibo — Interfaz para el Demo Day".

  web/base.html        el marco común: menú a la izquierda y el contenido a la derecha
  web/paginas/*.html   el contenido de cada pantalla
  web/estilos.css      colores, letra y tamaños del mockup (una sola fuente de verdad)

Starlette y uvicorn ya vienen instalados con fastmcp: no hay dependencias nuevas.

Correr: python servidor_web.py              (y abrir http://localhost:8000)
        python servidor_web.py --puerto 8001
"""
import argparse
import html
import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_WEB = CARPETA_PROYECTO / "web"
# La misma variable que usa servidor_mcp.py: las pruebas la apuntan a una copia congelada.
CARPETA_SALIDA = Path(os.getenv("INGESTA_CARPETA_SALIDA", CARPETA_PROYECTO / "salida"))
RUTA_RESULTADOS = CARPETA_SALIDA / "resultados.json"

# Las 5 pantallas: dirección -> (archivo de web/paginas, título de la pestaña, texto del menú, ícono)
PANTALLAS = {
    "/": ("subir.html", "Subir una lista", "subir"),
    "/fichas": ("fichas.html", "Fichas", "fichas"),
    "/revision": ("revision.html", "Para revisar", "revisar"),
    "/asistente": ("asistente.html", "Asistente", "chat"),
    "/costos": ("costos.html", "Corridas y costos", "costos"),
}

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
        "estilos_pagina": "",
        "scripts_pagina": "",
    })


async def pantalla(request):
    return HTMLResponse(armar_pantalla(request.url.path, leer_resultados()))


async def api_resumen(request):
    return JSONResponse(resumen(leer_resultados()))


def crear_app() -> Starlette:
    rutas = [Route(direccion, pantalla) for direccion in PANTALLAS]
    rutas += [
        Route("/api/resumen", api_resumen),
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
