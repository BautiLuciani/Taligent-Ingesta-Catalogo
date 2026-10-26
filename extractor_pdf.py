"""Extractor de PDF: saca los productos de un PDF con citations y verifica cada dato por código.

Semana 2. El modelo extrae y la API dice la página; el CÓDIGO verifica que lo extraído
esté de verdad en la fila del producto dentro del texto citado (paso 1: la cita de una
tabla trae la tabla entera, así que verificar contra la cita completa no alcanza).
"""
import re


def normalizar_espacios(texto: str) -> str:
    """Deja un solo espacio común entre palabras, sin espacios al principio ni al final.

    El PDF trae espacios "raros": \\xa0 (espacio que no se corta, entre el $ y el número)
    y saltos de línea \\r\\n. Sin esto, "$\\xa088,04" y "$ 88,04" no serían iguales para Python.
    """
    return re.sub(r"\s+", " ", texto).strip()  # \s también atrapa el \xa0


def buscar_fila(cited_text: str, codigo: str) -> str | None:
    """Busca en el texto citado la fila de UN producto: la línea que empieza con su código.

    La cita de una tabla trae la tabla entera, una fila por línea (paso 1).
    Compara la primera palabra entera: "LHS-26" no encuentra la fila de "LHS-263".
    Devuelve la fila ya normalizada, o None si no está o si aparece en más de una línea
    (ambiguo: no se adivina).
    """
    encontradas = []
    for linea in cited_text.splitlines():
        fila = normalizar_espacios(linea)
        if fila.split(" ", 1)[0] == codigo:
            encontradas.append(fila)
    return encontradas[0] if len(encontradas) == 1 else None


def valor_en_fila(valor, fila: str) -> bool:
    """¿El valor aparece en la fila como dato completo (salvo diferencias de espacios)?

    Es la verificación anti-invento: el EAN de otra fila de la tabla NO está en esta fila.
    "Completo" quiere decir que no es un pedazo de otro dato:
    "200" no está en "2000 ML" y "88" no está en "$ 88,04".
    """
    valor = normalizar_espacios(str(valor))
    if not valor:
        return False
    # Antes del valor: ni letra/número, ni "número + coma/punto". Después: ni letra/número, ni "coma/punto + número"
    patron = r"(?<!\w)(?<!\d[.,])" + re.escape(valor) + r"(?!\w)(?![.,]\d)"
    return re.search(patron, normalizar_espacios(fila)) is not None


def filas_verificadas(contenido: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Convierte los bloques de una respuesta con citations en filas verificadas, una por código.

    contenido: los bloques de la respuesta, como diccionarios (respuesta.model_dump()["content"]).
    Devuelve (filas, problemas):
      - filas: {codigo: {"codigo", "pagina", "fila"}} solo con lo que se pudo verificar.
        La página sale de la API (start_page_number), no de lo que diga el modelo.
      - problemas: lo que no se pudo verificar, con su motivo. Nada se descarta en silencio.
    """
    filas = {}
    problemas = []
    ambiguos = set()  # códigos que aparecieron en dos lugares distintos: quedan afuera

    for bloque in contenido:
        if bloque.get("type") != "text" or not bloque.get("citations"):
            continue  # sin cita no es evidencia (por ejemplo, el resumen que escribe Haiku)
        copia = normalizar_espacios(bloque["text"])
        if not copia:
            continue
        codigo = copia.split(" ", 1)[0]

        # Un bloque puede traer varias citas: usamos la primera que contenga la fila de este código
        cita, fila = None, None
        for cita_candidata in bloque["citations"]:
            fila = buscar_fila(cita_candidata["cited_text"], codigo)
            if fila is not None:
                cita = cita_candidata
                break

        if fila is None:
            problemas.append(f"{codigo}: no está como fila en el texto citado (copia: {copia!r}).")
            continue
        if copia != fila:
            problemas.append(f"{codigo}: la copia de Haiku no coincide con la fila del PDF "
                             f"(copia: {copia!r} · fila: {fila!r}).")
            continue
        if codigo in ambiguos:
            continue  # ya quedó afuera por ambiguo

        nueva = {"codigo": codigo, "pagina": cita["start_page_number"], "fila": fila}
        if codigo in filas and filas[codigo] != nueva:
            problemas.append(f"{codigo}: aparece en dos lugares distintos del PDF (págs. "
                             f"{filas[codigo]['pagina']} y {nueva['pagina']}): no se elige uno.")
            del filas[codigo]
            ambiguos.add(codigo)
            continue

        filas[codigo] = nueva  # nueva, o repetida idéntica (no cambia nada)

    return filas, problemas