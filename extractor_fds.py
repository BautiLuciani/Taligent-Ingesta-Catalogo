"""Extractor de FDS (fichas de datos de seguridad): qué códigos cubre cada ficha y su peligro para el depósito.

Semana 2, paso 4. Haiku encuentra las secciones y la API las cita; el CÓDIGO lee los datos del texto
CITADO (que es el documento real, no texto generado) y traduce la clase con la tabla del estándar (sección 9).
Paso 4A: la API cita la FDS de a una sección entera, y cada cita arranca con el título de su sección.
"""
import re
import unicodedata

from extractor_pdf import PATRON_CODIGO, normalizar_espacios

# Cómo arranca la cita de cada sección que nos interesa (paso 4A). La sección 2 (frases H) no está: es distractor.
TITULOS_SECCION = {
    "1": "Identificación",
    "14": "Información relativa al transporte",
}

# Estándar, sección 9: clase de transporte (sección 14 de la FDS) -> peligro_deposito
PELIGRO_POR_CLASE = {
    "2.1": "aerosol_inflamable",
    "3": "liquido_inflamable",
    "8": "corrosivo",
}


def lineas(texto: str) -> list[str]:
    """Parte un texto citado en líneas limpias: sin ligaduras ("ﬁ" -> "fi"), espacios normalizados y sin vacías."""
    texto = unicodedata.normalize("NFKC", texto)  # NFKC convierte las ligaduras del PDF en letras comunes
    return [normalizar_espacios(linea) for linea in texto.splitlines() if linea.strip()]


def secciones_citadas(contenido: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Junta las citas de la respuesta y reconoce cada sección por su título (la primera línea de la cita).

    contenido: los bloques de la respuesta, como diccionarios (model_dump()["content"]).
    Devuelve (secciones, problemas):
      - secciones: {"1": {"lineas", "pagina"}, "14": {...}}, solo las de TITULOS_SECCION.
        Las líneas y la página salen de lo que citó la API (el documento real), no de la copia de Haiku.
      - problemas: secciones que no aparecieron, o que aparecieron con textos distintos (no se elige una).
    """
    secciones = {}
    ambiguas = set()
    for bloque in contenido:
        if bloque.get("type") != "text" or not bloque.get("citations"):
            continue
        for cita in bloque["citations"]:
            texto = lineas(cita["cited_text"])
            for numero, titulo in TITULOS_SECCION.items():
                if not texto or texto[0] != titulo:  # la línea ENTERA: "Identificación de los peligros" es la sección 2
                    continue
                nueva = {"lineas": texto, "pagina": cita["start_page_number"]}
                if numero in secciones and secciones[numero] != nueva:
                    ambiguas.add(numero)
                secciones.setdefault(numero, nueva)  # repetida idéntica (varios bloques con la misma cita): no cambia nada

    problemas = [f"La sección {numero} aparece citada con textos distintos: no se elige una." for numero in sorted(ambiguas)]
    problemas += [f"No se encontró citada la sección {numero}." for numero in TITULOS_SECCION if numero not in secciones]
    return {numero: seccion for numero, seccion in secciones.items() if numero not in ambiguas}, problemas


def leer_seccion_1(lineas_seccion: list[str]) -> list[str]:
    """Los códigos comerciales que cubre la ficha. Ej.: 'Códigos comerciales: LHS-206, LHS-218' -> ['LHS-206', 'LHS-218']"""
    for linea in lineas_seccion:
        if linea.startswith("Códigos comerciales:"):
            candidatos = linea.split(":", 1)[1].replace(",", " ").split()
            return [codigo for codigo in candidatos if PATRON_CODIGO.match(codigo)]
    return []


def leer_seccion_14(lineas_seccion: list[str]) -> tuple[str | None, str | None, list[str]]:
    """El peligro para el depósito y el número ONU, según la tabla del estándar (sección 9).

    Devuelve (peligro_deposito, numero_onu, problemas). Una clase que no está en la tabla queda en None
    con su problema: no se adivina a qué sector del depósito va.
    """
    texto = " ".join(lineas_seccion)
    if "No regulado" in texto:
        return "no_peligroso", None, []

    clase = re.search(r"Clase de peligro para el transporte:\s*(\d+(?:\.\d+)?)", texto)
    onu = re.search(r"Número ONU:\s*(\d{4})", texto)
    numero_onu = onu.group(1) if onu else None
    if clase is None:
        return None, numero_onu, ["La sección 14 no dice la clase de peligro ni «No regulado»."]
    if clase.group(1) not in PELIGRO_POR_CLASE:
        return None, numero_onu, [f"Clase {clase.group(1)} fuera de la tabla del estándar (sección 9)."]
    return PELIGRO_POR_CLASE[clase.group(1)], numero_onu, []