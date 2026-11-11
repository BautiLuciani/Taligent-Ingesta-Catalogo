"""Permisos por agente (semana 4, paso 6): qué tools puede usar cada agente, escrito en el CÓDIGO, no en el prompt.

Es el "tools" de los subagents de Claude Code (módulo 5, §7.4): a cada agente se le da solo lo que su tarea necesita.
Lo que no está en su lista no lo puede hacer, diga lo que diga el prompt o el archivo que está leyendo (M4 §7.2:
blast radius; el que lee contenido de proveedores no tiene que tener tools de más).

Cómo se hace cumplir, según el agente:
  - "servidor": usa tools del servidor MCP. Dos candados en agente.py: (1) obtener_tools le pasa al modelo SOLO las de
    su lista; (2) el hook antes_de_tool frena cualquier pedido de una tool que no esté en la lista (aunque la invente).
  - "forzada": una sola llamada con su propio formulario y tool_choice forzado; el código acepta solo ese formulario.
  - "sin_tools": una llamada sin tools (solo citas o texto); el código lee lo citado o lo valida.
"""

PERMISOS = {
    "fichador": {
        "tools": {"leer_archivo_proveedor", "buscar_por_gtin", "buscar_parecidos", "registrar_ficha"},
        "como": "servidor",
        "por_que": "Lee los productos de su tanda, busca en el catálogo y propone fichas. registrar_ficha va en modo "
                   "propuesta: valida, pero no escribe resultados.json (lo escribe el escritor, que es código).",
    },
    "recepcionista": {
        "tools": {"entregar_receta"},
        "como": "forzada",
        "por_que": "Solo propone la receta de un Excel nuevo; el código la verifica con todas las filas (recepcion.py).",
    },
    "extractor_pdf": {
        "tools": {"entregar_campos"},
        "como": "forzada",
        "por_que": "Llamada 1: copia filas con citas (sin tools). Llamada 2: separa columnas con su formulario.",
    },
    "extractor_folleto": {
        "tools": set(),
        "como": "sin_tools",
        "por_que": "Una llamada con citas; los campos los separa el código.",
    },
    "extractor_fds": {
        "tools": set(),
        "como": "sin_tools",
        "por_que": "Una llamada con citas por FDS; el código lee el texto citado de las secciones 1 y 14.",
    },
    "catalogo_viejo": {
        "tools": set(),
        "como": "sin_tools",
        "por_que": "Propone variantes en texto; el código valida cada una y no toca el catálogo.",
    },
}


def tools_permitidas(rol: str) -> set[str]:
    """Las tools que puede usar ese agente. Un rol que no está en la tabla no tiene permiso para nada (falla)."""
    if rol not in PERMISOS:
        raise ValueError(f"El agente {rol!r} no está en la tabla de permisos (permisos.py): no tiene ninguna tool.")
    return set(PERMISOS[rol]["tools"])
