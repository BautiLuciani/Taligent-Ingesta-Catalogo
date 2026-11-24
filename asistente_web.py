"""El asistente en la interfaz (semana 7, paso 4): el MISMO asistente de la semana 6, detrás de la pantalla.

No cambia nada del asistente: abre las conversaciones con asistente.abrir (system con el criterio y el estándar, las
4 tools de solo lectura del rol asistente) y pregunta con Conversacion.preguntar, que verifica cada fuente y cada
producto citado antes de devolver la respuesta. Lo único nuevo es dónde corre:

  - Un hilo propio con su propio loop de asyncio (MotorDelAsistente): ahí vive la conexión con el servidor MCP
    (un proceso aparte, como cuando se corre asistente.py) y las conversaciones abiertas. La pantalla le pide cosas
    desde el servidor web y espera la respuesta. Una pregunta a la vez (como en la consola).
  - Cada conversación tiene su historial (memoria in-context): "¿y cuál es el más caro?" sabe de qué se habla.
    "Nueva conversación" abre una vacía. Las conversaciones no se guardan: viven mientras el servidor está abierto.

respuesta_para_pantalla le pone a la respuesta lo que la pantalla necesita para mostrarla (el nombre y el estado de
cada producto citado, el chip de cada fuente), sin cambiar lo que contestó el asistente.
"""
import asyncio
import json
import threading
import uuid
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
RUTA_CONSULTAS = CARPETA_PROYECTO / "Data" / "consultas" / "consultas.json"
SEGUNDOS_TOPE = 180  # una pregunta que tarda más que esto se da por perdida (el asistente suele tardar 3 a 15 s)

FRASE_DEL_ESTADO = {"a_revision": "para revisar", "lista_para_alta": "listos para alta", "duplicado": "que ya estaban"}

# Las preguntas de ejemplo de la bienvenida: consultas de la consigna que el asistente contesta bien (29 de 29)
EJEMPLOS = ["¿Qué quedó a revisión de Laboratorio Andes?", "¿Qué le tengo que pedir a Dermalab para cerrar sus revisiones?",
            "¿Cuántos productos quedaron listos para alta?"]


async def abrir_conversacion_real(estado: dict):
    """Abre una conversación del asistente de verdad. La primera vez conecta con el servidor MCP y la API."""
    if "cliente_mcp" not in estado:
        import os

        import anthropic
        from dotenv import load_dotenv
        from fastmcp import Client
        from fastmcp.client.transports import PythonStdioTransport

        from agente import CARPETA_TRAZAS, RUTA_SERVIDOR
        load_dotenv(CARPETA_PROYECTO / ".env")
        modelo = os.getenv("MODELO")
        if not modelo:
            raise RuntimeError("Falta MODELO en el .env: el asistente no puede arrancar.")
        pila = AsyncExitStack()
        estado["cliente_mcp"] = await pila.enter_async_context(Client(PythonStdioTransport(str(RUTA_SERVIDOR))))
        estado.update(pila=pila, modelo=modelo, cliente_claude=anthropic.Anthropic())
        CARPETA_TRAZAS.mkdir(parents=True, exist_ok=True)
        estado["carpeta_trazas"] = CARPETA_TRAZAS
    from asistente import abrir
    ruta_traza = estado["carpeta_trazas"] / f"asistente_web_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}.jsonl"
    return await abrir(estado["cliente_claude"], estado["modelo"], estado["cliente_mcp"], ruta_traza)


class MotorDelAsistente:
    """El asistente corriendo en su propio hilo. abrir: async (estado) -> objeto con `async preguntar(texto)`."""

    def __init__(self, abrir=abrir_conversacion_real):
        self._abrir = abrir
        self._loop = None
        self._hilo = None
        self._estado: dict = {}
        self._conversaciones: dict[str, object] = {}
        self._candado = threading.Lock()
        self._turno = threading.Lock()  # una pregunta a la vez

    def _arrancar(self):
        with self._candado:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._hilo = threading.Thread(target=self._loop.run_forever, daemon=True, name="asistente")
                self._hilo.start()

    def _correr(self, corrutina, tope=SEGUNDOS_TOPE):
        self._arrancar()
        return asyncio.run_coroutine_threadsafe(corrutina, self._loop).result(timeout=tope)

    def nueva(self) -> str:
        """Abre una conversación vacía y devuelve su id."""
        with self._turno:
            conversacion = self._correr(self._abrir(self._estado))
        identificador = uuid.uuid4().hex[:12]
        self._conversaciones[identificador] = conversacion
        return identificador

    def preguntar(self, identificador: str, texto: str) -> dict:
        conversacion = self._conversaciones.get(identificador)
        if conversacion is None:
            raise KeyError("Esa conversación ya no está (¿se reinició el servidor?). Empezá una nueva.")
        with self._turno:
            return self._correr(conversacion.preguntar(texto))

    def cerrar(self):
        if self._loop and "pila" in self._estado:
            try:
                self._correr(self._estado["pila"].aclose(), tope=10)
            except Exception:
                pass


def error_en_palabras(error: Exception) -> str:
    """Lo que falló, dicho para la persona que está usando la pantalla (con el paso para arreglarlo si lo hay)."""
    nombre = type(error).__name__
    if nombre == "AuthenticationError":
        return "La key de Anthropic no es válida. Revisala con python verificar_entorno.py."
    if nombre in ("APIConnectionError", "APITimeoutError", "ConnectError"):
        return "No hay conexión con Anthropic. Revisá internet y probá de nuevo."
    if nombre == "RateLimitError":
        return "Anthropic pidió esperar un momento (límite de uso). Probá de nuevo en unos segundos."
    if nombre in ("TimeoutError", "CancelledError"):
        return "El asistente tardó demasiado en contestar. Probá de nuevo."
    return f"El asistente no pudo contestar: {error}" if str(error) else f"El asistente no pudo contestar ({nombre})."


# --- La respuesta, lista para la pantalla ---

def numero_en_palabras(valor) -> str:
    """4 -> "4"; 320.8 -> "320,80"; un texto queda tal cual."""
    if isinstance(valor, bool) or valor is None:
        return ""
    if isinstance(valor, (int, float)):
        if float(valor).is_integer():
            return f"{int(valor):,}".replace(",", ".")
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def respuesta_para_pantalla(resultado: dict, fichas_por_id: dict) -> dict:
    """Le agrega a la respuesta del asistente lo que la pantalla necesita: cada producto citado con su nombre, su
    estado y su motivo; cada fuente como chip; el valor con formato y su etiqueta. No cambia lo que contestó."""
    from presentacion import fuente_para_pantalla

    items = []
    for item_id in resultado.get("items") or []:
        ficha = fichas_por_id.get(item_id)
        if ficha is None:
            items.append({"id": item_id, "codigo": item_id.split(":", 1)[-1], "nombre": item_id, "estado": None, "detalle": ""})
            continue
        detalle = ficha["motivos"][0] if ficha["estado"] == "a_revision" and ficha["motivos"] else f"{ficha['proveedor']}, {ficha['precio']}"
        items.append({"id": item_id, "codigo": ficha["codigo"], "nombre": ficha["nombre"], "estado": ficha["estado"], "detalle": detalle})
    estados = {i["estado"] for i in items}
    valor = resultado.get("valor")
    etiqueta = ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool) and items and valor == len(items):
        etiqueta = "producto" if valor == 1 else "productos"
        if len(estados) == 1 and None not in estados:
            etiqueta += " " + FRASE_DEL_ESTADO.get(next(iter(estados)), "")
    segundos = resultado.get("segundos") or 0
    costo = resultado.get("costo_usd") or 0
    return {
        "consulta": resultado.get("consulta"), "texto": resultado.get("texto", ""),
        "valor": numero_en_palabras(valor), "etiqueta": etiqueta.strip(),
        "estado_comun": next(iter(estados)) if len(estados) == 1 and None not in estados else None,
        "items": items,
        "fuentes": [f for f in (fuente_para_pantalla(x) for x in resultado.get("fuentes") or []) if f],
        "avisos": resultado.get("avisos") or [],
        "meta": f"Contestó en {segundos:.1f} segundos y costó US$ {costo:.3f}".replace(".", ","),
        "segundos": segundos, "costo_usd": costo,
    }


def guion_de_conversaciones(ruta: Path = RUTA_CONSULTAS) -> list[list[str]]:
    """Las conversaciones de la consigna (V01 y V02), turno por turno: después de un turno se sugiere el siguiente."""
    try:
        return [c["turnos"] for c in json.loads(ruta.read_text(encoding="utf-8")).get("conversaciones", [])]
    except (OSError, json.JSONDecodeError):
        return []


def sugerencia_despues_de(pregunta: str, guiones: list[list[str]]) -> str | None:
    """Si la pregunta es un turno de una conversación de la consigna, el turno que sigue."""
    for turnos in guiones:
        for i, turno in enumerate(turnos[:-1]):
            if turno.strip().lower() == (pregunta or "").strip().lower():
                return turnos[i + 1]
    return None
