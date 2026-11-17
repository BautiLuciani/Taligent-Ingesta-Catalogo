"""La ficha estructurada (semana 5, paso 2, M6): el formulario con casilleros que llena el modelo al registrar.

Hasta la semana 4, registrar_ficha recibía la ficha como un diccionario libre: la API no controlaba su forma y los
valores fuera del vocabulario los atajaban después los hooks. Con strict (M6 §2.2), la API garantiza que el modelo
llene ESTE formulario: cada lista cerrada (tipo, unidad, moneda, condición, peligro, categoría) es un enum leído del
vocabulario y la taxonomía (la única fuente de verdad, no se copian al código).

Diseño "C" (medido en el paso 1, probar_strict_diagnostico.py):
  - Todos los campos SIEMPRE presentes; el que no se pudo determinar va en null ("tipo o null" = anyOf).
    Con los campos OPCIONALES (que pueden faltar) la API no llega a compilar el formulario: 14 opcionales en un
    objeto dieron "Grammar compilation timed out"; todo presente con anyOf compila en ~3 s.
  - Las fuentes como LISTA de casilleros fijos {campo, archivo, tipo_ubicacion, numero, hoja}: strict no admite
    un objeto con claves libres ({campo: fuente}) ni conviene una unión por fuente (tope de 16 uniones por pedido).
    El CÓDIGO la convierte a la forma de la guía: {archivo, pagina} | {archivo, hoja, fila} | {archivo, linea}.

strict garantiza valores VÁLIDOS, no CORRECTOS (un shampoo con VENTA_LIBRE es válido para el formulario): el
criterio lo sigue guiando el prompt, y el GTIN, las fuentes y la coherencia los siguen garantizando los hooks y el
servidor.
"""
import csv
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cuentas import cargar_vocabulario

VOCABULARIO = cargar_vocabulario()
RUTA_TAXONOMIA = Path(__file__).parent / "Data" / "estandar" / "taxonomia.csv"
with open(RUTA_TAXONOMIA, encoding="utf-8-sig", newline="") as archivo:
    CATEGORIAS = tuple(fila["codigo"] for fila in csv.DictReader(archivo))

# CREMA y GEL están en dos familias del vocabulario: en el enum van una sola vez
TIPOS = tuple(sorted({tipo for familia in VOCABULARIO["tipos"].values() for tipo in familia}))

# Los campos de la ficha, en el orden del estándar (sección 1) + los de la ficha de datos de seguridad (sección 9)
CAMPOS_FICHA = ("gtin", "descripcion", "marca", "tipo", "variante", "contenido", "unidad", "unidades_por_envase",
                "principio_activo", "concentracion", "condicion_venta", "categoria", "precio_costo", "moneda",
                "proveedor_id", "codigo_proveedor", "peligro_deposito", "numero_onu")

Tipo = Literal[TIPOS]
Unidad = Literal[tuple(VOCABULARIO["unidades"])]
Moneda = Literal[tuple(VOCABULARIO["monedas"])]
CondicionVenta = Literal[tuple(VOCABULARIO["condicion_venta"])]
PeligroDeposito = Literal[tuple(VOCABULARIO["peligro_deposito"])]
Categoria = Literal[CATEGORIAS]
CampoFicha = Literal[CAMPOS_FICHA]


# Ojo: el docstring de cada modelo y las description de los campos VIAJAN al modelo (son parte del formulario).
# Las notas para programadores van en comentarios como este.
# Sin valores por defecto a propósito: un default convierte el campo en OPCIONAL y la API no compila el formulario.
class Ficha(BaseModel):
    """Los campos de la ficha (estándar, sección 1). Van todos; el que no se pudo determinar va en null."""
    model_config = ConfigDict(extra="forbid")  # additionalProperties: false (strict lo exige)

    gtin: Annotated[str | None, Field(description="GTIN-13 (calculado.gtin). null si el archivo no trae uno válido.")]
    descripcion: Annotated[str, Field(description="Armada como dice la sección 3 del estándar.")]
    marca: Annotated[str | None, Field(description="La marca comercial, no la razón social del proveedor.")]
    tipo: Annotated[Tipo | None, Field(description="Uno de los tipos del vocabulario.")]
    variante: Annotated[str | None, Field(description="Lo que distingue al producto dentro de su marca y tipo.")]
    contenido: Annotated[int | None, Field(description="Número entero, en la unidad de la ficha (calculado.contenido).")]
    unidad: Annotated[Unidad | None, Field(description="calculado.unidad.")]
    unidades_por_envase: Annotated[int, Field(description="1, salvo en los packs (sección 5).")]
    principio_activo: Annotated[str | None, Field(description="Solo medicamentos y suplementos; null en lo demás.")]
    concentracion: Annotated[str | None, Field(description="Solo medicamentos y suplementos; null en lo demás.")]
    condicion_venta: Annotated[CondicionVenta | None, Field(description="Solo medicamentos; null en lo demás.")]
    categoria: Annotated[Categoria | None, Field(description="Código de tercer nivel de la taxonomía.")]
    precio_costo: Annotated[float | None, Field(description="calculado.precio_costo.")]
    moneda: Annotated[Moneda | None, Field(description="calculado.moneda.")]
    proveedor_id: Annotated[str, Field(description="Ej. P03.")]
    codigo_proveedor: Annotated[str, Field(description="El código del ítem en el archivo del proveedor.")]
    peligro_deposito: Annotated[PeligroDeposito | None, Field(
        description="Solo productos de familias que llevan ficha de datos de seguridad; null en los demás.")]
    numero_onu: Annotated[str | None, Field(description="De la sección 14 de la FDS; null si no corresponde.")]


class FuenteDeCampo(BaseModel):
    """De dónde salió un campo completado de la ficha."""
    model_config = ConfigDict(extra="forbid")

    campo: Annotated[CampoFicha, Field(description="El campo de la ficha.")]
    archivo: Annotated[str, Field(description="El archivo de la fuente, tal como viene en la fila.")]
    tipo_ubicacion: Annotated[Literal["linea", "pagina", "hoja_fila"], Field(
        description="linea: CSV o mail. pagina: PDF. hoja_fila: Excel.")]
    numero: Annotated[int, Field(description="La línea, la página o la fila, según tipo_ubicacion.")]
    hoja: Annotated[str, Field(description="El nombre de la hoja si es un Excel; vacío en los demás casos.")]


def fuente_de_la_guia(fuente: dict) -> dict:
    """Un casillero -> la forma de la guía: {archivo, linea} | {archivo, pagina} | {archivo, hoja, fila}."""
    if fuente["tipo_ubicacion"] == "pagina":
        return {"archivo": fuente["archivo"], "pagina": fuente["numero"]}
    if fuente["tipo_ubicacion"] == "hoja_fila":
        return {"archivo": fuente["archivo"], "hoja": fuente["hoja"], "fila": fuente["numero"]}
    return {"archivo": fuente["archivo"], "linea": fuente["numero"]}


def fuentes_de_la_guia(fuentes: list[dict], ficha: dict) -> tuple[dict, list[str]]:
    """La lista de casilleros -> {campo: fuente de la guía}, y los problemas que el formulario no puede atajar.

    strict garantiza que cada casillero tenga la forma; esto revisa lo que depende de otros datos:
      - un campo con dos fuentes (no se elige una);
      - una fuente de un campo que quedó en null (los campos en null no llevan fuente, regla 8);
      - un casillero que no cierra: hoja escrita sin ser Excel, Excel sin hoja, número menor que 1.
    """
    convertidas, problemas = {}, []
    for fuente in fuentes:
        campo = fuente["campo"]
        if campo in convertidas:
            problemas.append(f"el campo {campo} tiene más de una fuente: va una sola por campo")
            continue
        if ficha.get(campo) is None:
            problemas.append(f"el campo {campo} está en null y tiene fuente: los campos en null no llevan fuente")
            continue
        if fuente["numero"] < 1:
            problemas.append(f"la fuente de {campo} tiene numero {fuente['numero']}: línea, página y fila empiezan en 1")
            continue
        if fuente["tipo_ubicacion"] == "hoja_fila" and not fuente["hoja"].strip():
            problemas.append(f"la fuente de {campo} es de un Excel (hoja_fila) y no dice la hoja")
            continue
        if fuente["tipo_ubicacion"] != "hoja_fila" and fuente["hoja"].strip():
            problemas.append(f"la fuente de {campo} es {fuente['tipo_ubicacion']} y trae hoja {fuente['hoja']!r}: "
                             "la hoja solo va en un Excel (hoja_fila)")
            continue
        convertidas[campo] = fuente_de_la_guia(fuente)
    return convertidas, problemas


def registro_interno(argumentos: dict) -> dict:
    """Lo que registró el modelo, con las fuentes ya en la forma de la guía (la forma de resultados.json).

    La usan el servidor (al aceptar) y los hooks (al guardar lo aceptado para el escritor): una sola conversión.
    Supone una entrada ya aceptada por el servidor; si hubiera problemas en las fuentes, esas fuentes no pasan.
    """
    ficha = argumentos.get("ficha") or {}
    fuentes = argumentos.get("fuentes")
    if isinstance(fuentes, list):
        fuentes, _ = fuentes_de_la_guia(fuentes, ficha)
    return {**argumentos, "fuentes": fuentes}