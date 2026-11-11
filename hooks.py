"""Hooks del loop del agente (semana 4, paso 5): lo que tiene que pasar SIEMPRE lo garantiza el código, no el prompt.

Es el mismo concepto que los hooks de Claude Code del módulo 5 (PreToolUse, PostToolUse, Stop), pero en NUESTRO loop:
  - antes_de_tool:   corre antes de ejecutar cada tool. Si frena, la tool NO se ejecuta y el modelo recibe el motivo
                     como error (is_error), igual que el "exit 2 + stderr" de Claude Code.
  - despues_de_tool: corre después de cada tool. Es la memoria de la conversación: qué fichas quedaron aceptadas.
  - al_terminar:     corre cuando el modelo dice que terminó. Si frena, el modelo recibe el motivo y tiene que seguir.

El criterio de revisión (prompt MCP, paso 4) GUÍA al modelo; estos hooks GARANTIZAN. El servidor valida la coherencia
del resultado (estado, motivos, SKU); el contenido de la ficha lo validan acá: el GTIN que escribió el modelo, los
valores del vocabulario y que cada campo completado tenga su fuente.
Las listas salen de vocabulario.yaml y taxonomia.csv: la única fuente de verdad (no se copian al código).
"""
import csv
import json
from pathlib import Path

from cuentas import calcular_digito_verificador, cargar_vocabulario

VOCABULARIO = cargar_vocabulario()
RUTA_TAXONOMIA = Path(__file__).parent / "Data" / "estandar" / "taxonomia.csv"
with open(RUTA_TAXONOMIA, encoding="utf-8-sig", newline="") as archivo:
    CATEGORIAS = {fila["codigo"] for fila in csv.DictReader(archivo)}

# Campo de la ficha -> los valores que puede tener (listas cerradas del estándar). null siempre vale: "no se pudo
# determinar" es un valor legítimo (estándar, sección 8); si era obligatorio, lo resuelve el criterio de revisión.
VALORES_PERMITIDOS = {
    "tipo": {tipo for tipos in VOCABULARIO["tipos"].values() for tipo in tipos},
    "unidad": set(VOCABULARIO["unidades"]),
    "moneda": set(VOCABULARIO["monedas"]),
    "condicion_venta": set(VOCABULARIO["condicion_venta"]),
    "peligro_deposito": set(VOCABULARIO["peligro_deposito"]),
    "categoria": CATEGORIAS,
}

TOPE_FRENOS_AL_TERMINAR = 2  # M4 §1.5: tope de intentos. Después, lo que siga mal no se acepta (no se insiste sin fin)


# --- Las reglas (funciones puras: las usan los hooks y también el escritor, que vuelve a revisar antes de guardar) ---

def problema_del_gtin(gtin) -> str | None:
    """Un GTIN completado tiene que tener 13 dígitos y el dígito verificador correcto (estándar, sección 1)."""
    if gtin is None:
        return None
    texto = str(gtin)
    if not (texto.isdigit() and len(texto) == 13):
        return f"gtin {gtin!r} no tiene 13 dígitos"
    esperado = calcular_digito_verificador(texto[:12])
    if int(texto[-1]) != esperado:
        return f"gtin {gtin} tiene el dígito verificador inválido (con esos 12 primeros dígitos, termina en {esperado})"
    return None


def problemas_de_la_ficha(ficha: dict) -> list[str]:
    """Lo que nunca puede tener una ficha: un GTIN inválido o un valor fuera de las listas cerradas del estándar."""
    problemas = [p for p in [problema_del_gtin(ficha.get("gtin"))] if p]
    for campo, permitidos in VALORES_PERMITIDOS.items():
        valor = ficha.get(campo)
        if valor is not None and valor not in permitidos:
            donde = "la taxonomía" if campo == "categoria" else "el vocabulario"
            problemas.append(f"{campo} {valor!r} no está en {donde}")
    return problemas


def es_fuente(fuente) -> bool:
    """¿Tiene la forma de una fuente de la guía? {archivo, pagina} | {archivo, hoja, fila} | {archivo, linea}"""
    if not isinstance(fuente, dict) or not fuente.get("archivo"):
        return False
    return "pagina" in fuente or "linea" in fuente or ("hoja" in fuente and "fila" in fuente)


def campos_sin_fuente(ficha: dict, fuentes: dict) -> list[str]:
    """Los campos completados (no null) que no dicen de dónde salieron (guía, sección 4: no se negocia)."""
    fuentes = fuentes if isinstance(fuentes, dict) else {}
    return [campo for campo, valor in ficha.items() if valor is not None and not es_fuente(fuentes.get(campo))]


# --- Los hooks: una libreta por conversación (por tanda) ---

class HooksDeLaTanda:
    """Los 3 hooks de UNA conversación del fichador, con su memoria: qué se aceptó y qué se frenó.

    esperados: los item_id de la tanda (los sabe el código, no el modelo).
    permitidas: las tools que puede usar este agente (semana 4, paso 6, permisos.py). None = no se controla.
    """

    def __init__(self, esperados: list[str], permitidas: set[str] | None = None):
        self.esperados = list(esperados)
        self.permitidas = permitidas
        self.aceptadas: dict[str, dict] = {}  # item_id -> lo que registró el modelo y el servidor aceptó (la última)
        self.frenos: list[dict] = []          # cada freno: hook, item_id, motivo
        self.frenos_al_terminar = 0

    def _frenar(self, hook: str, item_id: str | None, motivo: str) -> None:
        self.frenos.append({"hook": hook, "item_id": item_id, "motivo": motivo})

    def antes_de_tool(self, nombre: str, argumentos: dict) -> str | None:
        """Antes de ejecutar una tool. Devuelve el motivo si frena (la tool no se ejecuta), o None si pasa."""
        if self.permitidas is not None and nombre not in self.permitidas:  # paso 6: permisos por agente (candado 2)
            self._frenar("permisos", argumentos.get("item_id") if isinstance(argumentos, dict) else None,
                         f"la tool {nombre!r} no está permitida para este agente")
            return (f"[permisos] La tool {nombre!r} no está permitida para este agente. Solo podés usar: "
                    f"{', '.join(sorted(self.permitidas))}.")
        if nombre != "registrar_ficha":
            return None
        ficha = argumentos.get("ficha")
        if not isinstance(ficha, dict):
            return None  # una ficha mal armada la rechaza el servidor con su validación (no es tarea de este hook)
        problemas = problemas_de_la_ficha(ficha)
        if not problemas:
            return None
        item_id = argumentos.get("item_id")
        motivo = (f"[hook antes de registrar_ficha] No se registró {item_id}: " + "; ".join(problemas) +
                  ". Corregilo y volvé a registrarlo.")
        self._frenar("antes_de_tool", item_id, "; ".join(problemas))
        return motivo

    def despues_de_tool(self, nombre: str, argumentos: dict, resultado: dict) -> None:
        """Después de cada tool: anota la ficha que el servidor aceptó (la última de cada ítem reemplaza a la anterior)."""
        if nombre == "registrar_ficha" and not resultado["is_error"]:
            item_id = json.loads(resultado["content"])["registrado"]
            self.aceptadas[item_id] = argumentos

    def al_terminar(self) -> str | None:
        """Cuando el modelo dice que terminó. Devuelve el motivo si no lo deja terminar, o None si pasa.

        Frena si falta registrar algún producto de la tanda o si una ficha aceptada tiene un campo completado sin
        fuente. Como mucho TOPE_FRENOS_AL_TERMINAR veces: después, las fichas sin fuente se DESCARTAN (no se aceptan)
        y la conversación termina; el escritor verá que faltan y no escribirá ese proveedor a medias.
        """
        faltan = [item for item in self.esperados if item not in self.aceptadas]
        sin_fuente = {item: campos for item, registro in self.aceptadas.items()
                      if (campos := campos_sin_fuente(registro.get("ficha") or {}, registro.get("fuentes")))}
        if not faltan and not sin_fuente:
            return None
        self.frenos_al_terminar += 1
        if self.frenos_al_terminar > TOPE_FRENOS_AL_TERMINAR:
            for item, campos in sin_fuente.items():
                del self.aceptadas[item]
                self._frenar("al_terminar", item, f"descartada después de {TOPE_FRENOS_AL_TERMINAR} avisos: "
                                                  f"sigue sin fuente en {', '.join(campos)}")
            return None
        partes = []
        if faltan:
            partes.append(f"te faltó registrar {', '.join(faltan)}")
            self.frenos += [{"hook": "al_terminar", "item_id": item, "motivo": "faltó registrarlo"} for item in faltan]
        for item, campos in sin_fuente.items():
            partes.append(f"{item} tiene campos completados sin fuente: {', '.join(campos)}")
            self._frenar("al_terminar", item, f"campos sin fuente: {', '.join(campos)}")
        return ("[hook al terminar] Todavía no terminaste: " + "; ".join(partes) +
                ". Registralos (cada campo completado con su fuente) y después terminá.")

    def resumen_de_frenos(self) -> list[dict]:
        """Cada freno con si se corrigió: el ítem terminó aceptado y su ficha final ya cumple las reglas."""
        resumen = []
        for freno in self.frenos:
            registro = self.aceptadas.get(freno["item_id"])
            corregido = registro is not None and not problemas_de_la_ficha(registro.get("ficha") or {}) \
                and not campos_sin_fuente(registro.get("ficha") or {}, registro.get("fuentes"))
            resumen.append({**freno, "corregido": corregido})
        return resumen
