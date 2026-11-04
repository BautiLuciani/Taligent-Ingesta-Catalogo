"""Escritor (semana 3, paso 6): el ÚNICO que escribe resultados.json. Es código, sin IA.

Los fichadores proponen (salida/propuestas.json); el escritor decide qué se guarda:
  1. Por proveedor, que no falte ni sobre ningún producto: lo esperado es lo consolidado (salida/consolidado/).
  2. Vuelve a validar cada propuesta con la MISMA regla del servidor (problemas_del_registro) y el vocabulario.
     No confía en que ya se validó: entre el servidor y acá la propuesta pasó por un archivo (M4 §7.3).
  3. Un proveedor con algún problema NO se escribe: sus fichas anteriores quedan intactas y se informa por qué
     (una corrida mala nunca borra fichas buenas, como el chequeo del paso 1b). Los demás se escriben igual.
  4. Escribe una sola vez, en el orden del archivo de cada proveedor, con copia en resultados_anterior.json.
  5. Paso 9 (detector): si la propuesta viene marcada "inestable" (las dos corridas no coincidieron), la marca se
     escribe al lado de la ficha, no adentro: la ficha sigue siendo la del estándar y la marca avisa que hay que mirarla.
"""
import json
import shutil
from pathlib import Path

from pydantic import ValidationError

from servidor_mcp import VOCABULARIO, CategoriaDecididaPor, armar_resultado, problemas_del_registro


def items_esperados(carpeta_consolidado: Path, proveedor_id: str) -> list[str]:
    """Los productos que TIENEN que salir de un proveedor, en el orden de su archivo (el contrato del paso 4)."""
    filas = json.loads((carpeta_consolidado / f"{proveedor_id}.json").read_text(encoding="utf-8"))["filas"]
    return [fila["item_id"] for fila in filas]


def revisar_propuesta(item_id: str, propuesta: dict) -> list[str]:
    """Lo mismo que revisa registrar_ficha, ahora sobre la propuesta guardada. Vacío = se puede escribir."""
    problemas = []
    if propuesta.get("item_id") != item_id:
        problemas.append(f"la propuesta dice ser de {propuesta.get('item_id')!r}")
    estado = propuesta.get("estado")
    if estado not in VOCABULARIO["estados"]:
        problemas.append(f"estado fuera del vocabulario: {estado!r}")
    motivos = propuesta.get("motivos_revision", [])
    if not isinstance(motivos, list) or any(m not in VOCABULARIO["motivos_revision"] for m in motivos):
        problemas.append(f"motivos fuera del vocabulario: {motivos!r}")
    if not isinstance(propuesta.get("ficha"), dict) or not isinstance(propuesta.get("fuentes"), dict):
        problemas.append("le falta la ficha o sus fuentes")
    try:
        categoria = CategoriaDecididaPor.model_validate(propuesta.get("categoria_decidida_por"))
    except ValidationError:
        problemas.append("categoria_decidida_por inválida o ausente")
    if problemas:  # con la forma rota, la regla del estándar no se puede aplicar
        return problemas
    return problemas_del_registro(item_id, estado, propuesta["ficha"], categoria, motivos, propuesta.get("duplicado_de"))


def revisar_proveedor(proveedor_id: str, esperados: list[str], propuestas: dict) -> tuple[list[dict], list[str]]:
    """Devuelve (sus resultados listos para guardar, en orden; sus problemas). Con algún problema, no se escribe."""
    propias = {item_id: p for item_id, p in propuestas.items() if item_id.startswith(f"{proveedor_id}:")}
    problemas = [f"{item_id}: falta su propuesta" for item_id in esperados if item_id not in propias]
    problemas += [f"{item_id}: sobra (no está en lo consolidado)" for item_id in propias if item_id not in esperados]
    resultados = []
    for item_id in esperados:
        if item_id not in propias:
            continue
        propuesta = propias[item_id]
        encontrados = revisar_propuesta(item_id, propuesta)
        if encontrados:
            problemas += [f"{item_id}: {problema}" for problema in encontrados]
            continue
        resultado = armar_resultado(
            item_id, propuesta["estado"], propuesta["ficha"], propuesta["fuentes"],
            CategoriaDecididaPor.model_validate(propuesta["categoria_decidida_por"]),
            propuesta.get("motivos_revision", []), propuesta.get("duplicado_de"))
        if propuesta.get("inestable"):  # paso 9: el detector la marcó (las dos corridas no coincidieron)
            resultado["inestable"] = propuesta["inestable"]
        resultados.append(resultado)
    return resultados, problemas


def escribir(propuestas: dict, proveedores: list[str], carpeta_consolidado: Path, ruta_resultados: Path) -> dict:
    """Revisa y escribe. Devuelve el informe: qué proveedores se escribieron, cuáles no y por qué."""
    nuevos, escritos, frenados = {}, {}, {}
    for proveedor_id in proveedores:
        resultados, problemas = revisar_proveedor(
            proveedor_id, items_esperados(carpeta_consolidado, proveedor_id), propuestas)
        if problemas:
            frenados[proveedor_id] = problemas
        else:
            nuevos[proveedor_id] = resultados
            escritos[proveedor_id] = len(resultados)
    # Propuestas de un proveedor que no se procesó en esta corrida: no se escriben, pero se avisa (no se esconden)
    ignoradas = sorted(item_id for item_id in propuestas if item_id.split(":")[0] not in proveedores)

    anteriores = json.loads(ruta_resultados.read_text(encoding="utf-8")) if ruta_resultados.exists() else {}
    archivo = {item_id: r for item_id, r in anteriores.items() if item_id.split(":")[0] not in nuevos}
    for proveedor_id in proveedores:
        for resultado in nuevos.get(proveedor_id, []):
            archivo[resultado["item_id"]] = resultado

    if nuevos:  # si no hay nada para escribir, el archivo ni se toca
        ruta_resultados.parent.mkdir(parents=True, exist_ok=True)
        if ruta_resultados.exists():
            shutil.copyfile(ruta_resultados, ruta_resultados.with_name("resultados_anterior.json"))
        temporal = ruta_resultados.with_suffix(".tmp")  # temporal + renombrar: nunca queda un archivo a medias
        temporal.write_text(json.dumps(archivo, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(ruta_resultados)
    inestables = [r["item_id"] for resultados in nuevos.values() for r in resultados if r.get("inestable")]
    return {"escritos": escritos, "frenados": frenados, "ignoradas": ignoradas, "inestables": inestables,
            "total_en_archivo": len(archivo)}


def mostrar(informe: dict) -> None:
    """Imprime qué se escribió y qué no."""
    print("\n=== Escritor (el único que escribe resultados.json)")
    for proveedor_id, cantidad in informe["escritos"].items():
        print(f"✔ {proveedor_id}: {cantidad} fichas escritas")
    for proveedor_id, problemas in informe["frenados"].items():
        print(f"✖ {proveedor_id} NO se escribió (sus fichas anteriores quedan como estaban), {len(problemas)} problema(s):")
        for problema in problemas[:5]:
            print(f"    - {problema}")
    if informe["ignoradas"]:
        print(f"⚠ Propuestas de proveedores que no se procesaron (no se escriben): {informe['ignoradas']}")
    if informe.get("inestables"):
        print(f"⚠ {len(informe['inestables'])} ficha(s) escrita(s) con la marca \"inestable\" (mirarlas antes de dar de alta):"
              f" {', '.join(informe['inestables'])}")
    print(f"resultados.json: {informe['total_en_archivo']} fichas en total")