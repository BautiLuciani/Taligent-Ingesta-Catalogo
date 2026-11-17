"""La ventanilla de la Batch API (semana 5, paso 6, M6 §7): los fichadores preguntan como siempre, pero van en batch.

Opción A (aprobada): cada vuelta de TODAS las tandas va en un batch. El fichador (agente.correr_loop) usa este cliente
igual que el de Anthropic, con cliente.messages.stream(...) y get_final_message(). Por dentro:
  1. el pedido queda en la ventanilla y el fichador espera (su hilo se frena, como con la llamada en tiempo real);
  2. cuando TODAS las conversaciones que tienen que preguntar dejaron su pedido (las activas y las que están por
     arrancar: el orquestador avisa cuántas son con planificar), o pasaron ESPERA_JUNTAR segundos desde el primero
     (para que una tanda lenta no trabe a las demás), la ventanilla los manda juntos en un solo batch;
  3. consulta el estado hasta que termina (el consumo es asíncrono: no hay aviso, M6 §7.2);
  4. le entrega a cada fichador SU respuesta por el custom_id, nunca por la posición (vuelven desordenadas: paso 1);
  5. el fichador ejecuta sus tools en local, con sus hooks y permisos de siempre, y deja el pedido siguiente.
El agente no se entera de que va por batch (como no se entera de si el archivo era CSV o PDF).

Lo que resuelve la ventanilla (M6 §7.2: "completado" no es "todo salió bien"):
  - succeeded: la respuesta va a su fichador;
  - errored reintentable (el servidor falló), expired o sin resultado: SOLO ese pedido se reencola en el batch
    siguiente, como mucho REINTENTOS veces; un error del pedido (invalid_request_error, etc.) no se reintenta: reenviar
    lo mismo da lo mismo (M6 §5);
  - si no se puede, el fichador recibe BatchFallido: su tanda falla con el motivo y el escritor no escribe ese
    proveedor a medias (semana 3);
  - cancelar(): cancela el batch en curso (Ctrl + C); lo que ya terminó igual vuelve, pero no se reencola nada.
Caché: TTL de 1 hora (entre vuelta y vuelta pasan minutos; la doc lo recomienda para batch). Costo: las tarifas de batch
(la mitad), que el agente lee de cliente.tarifas. Cada batch queda anotado (id, tiempos, estados) en el registro: los
resultados viven ~29 días en Anthropic y con el id se pueden volver a bajar.
"""
import itertools
import json
import threading
import time
from collections import Counter
from concurrent.futures import Future
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# USD por millón de tokens con batch: la mitad de todo (M6 §7.1). La escritura del caché de 1 hora cuesta 2x la
# entrada (M6 §3.4: 0,20 en tiempo real) -> 0,10 en batch. Calculado con los multiplicadores de la doc.
TARIFAS_BATCH = {"input": 0.05, "escritura_cache": 0.10, "lectura_cache": 0.005, "output": 0.25}
TTL_CACHE = "1h"
ESPERA_CONSULTA = 15   # segundos entre una consulta de estado y la siguiente
ESPERA_JUNTAR = 20     # segundos: si no llegaron todos los pedidos de la vuelta, se manda igual con los que hay
REINTENTOS = 2         # por pedido (M4 §1.5: tope de intentos)
AVISO_CADA = 4         # consultas: cada cuántas se imprime "sigue procesando" (4 x 15 s = 1 minuto)
# Errores del pedido: reintentarlo igual da lo mismo (M6 §5.1). Los demás (api_error, overloaded_error) sí.
ERRORES_SIN_REINTENTO = {"invalid_request_error", "authentication_error", "permission_error", "not_found_error",
                         "request_too_large"}


class BatchFallido(RuntimeError):
    """El pedido no se pudo resolver por batch (error del pedido, se agotaron los reintentos o se canceló)."""


def a_json(valor):
    """El pedido como JSON puro: el historial trae objetos del SDK (las respuestas de Haiku, con su thinking) y el batch
    viaja como JSON. Se pasan EXACTAMENTE como los pasa el SDK en tiempo real (anthropic/_utils/_json.py,
    openapi_model_dump): solo los campos que vinieron en la respuesta (exclude_unset), con sus nombres de la API y sin
    los de __api_exclude__. Así el thinking vuelve intacto, con su firma (M2), y el pedido es el mismo que hoy anda."""
    if hasattr(valor, "model_dump"):
        return valor.model_dump(mode="json", by_alias=True, exclude_unset=True,
                                exclude=getattr(valor, "__api_exclude__", None))
    if isinstance(valor, dict):
        return {clave: a_json(v) for clave, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [a_json(v) for v in valor]
    return valor


def con_ttl(valor, ttl: str):
    """Cada marca de caché (cache_control) con el TTL dado. Todas iguales: la API pide que las más largas vayan antes."""
    if isinstance(valor, dict):
        return {clave: ({**v, "ttl": ttl} if clave == "cache_control" and isinstance(v, dict) else con_ttl(v, ttl))
                for clave, v in valor.items()}
    if isinstance(valor, list):
        return [con_ttl(v, ttl) for v in valor]
    return valor


class _Pedido:
    def __init__(self, custom_id: str, params: dict):
        self.custom_id, self.params, self.futuro, self.intentos = custom_id, params, Future(), 0


class _Espera:
    """Lo que devuelve stream(): se usa con "with" y get_final_message() espera la respuesta (como el stream real)."""
    def __init__(self, futuro: Future):
        self.futuro = futuro

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return self.futuro.result()  # frena el hilo del fichador hasta que su batch vuelve (o lanza BatchFallido)


class ClienteBatch:
    """Para el fichador, un cliente de Anthropic más (cliente.messages.stream). Por dentro, la ventanilla de batches."""
    tarifas = TARIFAS_BATCH

    def __init__(self, api, carpeta_registro: Path, espera_consulta: float = ESPERA_CONSULTA,
                 espera_juntar: float = ESPERA_JUNTAR, reintentos: int = REINTENTOS, ttl: str = TTL_CACHE, avisar=None):
        self.api, self.messages = api, self  # self.messages: para que ande cliente.messages.stream(...)
        self.espera_consulta, self.espera_juntar, self.reintentos, self.ttl = espera_consulta, espera_juntar, reintentos, ttl
        self.avisar = avisar or (lambda texto: print(texto, flush=True))
        self.registro: list[dict] = []
        carpeta_registro.mkdir(parents=True, exist_ok=True)
        self.ruta_registro = carpeta_registro / f"batches_{datetime.now():%Y%m%d_%H%M%S}.json"
        self._cond = threading.Condition()
        self._activos = 0           # conversaciones (tandas) en curso
        self._por_empezar = 0       # conversaciones que todavía no arrancaron (las avisa planificar)
        self._a_la_vez = float("inf")  # cuántas pueden estar en curso a la vez (los fichadores)
        self._pendientes: list[_Pedido] = []
        self._primero = None        # cuándo llegó el primer pedido que espera
        self._en_curso = None       # id del batch que se está procesando
        self._cancelado = False
        self._ids = itertools.count(1)
        threading.Thread(target=self._despachar, daemon=True, name="ventanilla").start()

    # --- Lo que usa el fichador ---

    def stream(self, **params):
        """Deja el pedido en la ventanilla y devuelve con qué esperar la respuesta."""
        pedido = _Pedido(f"pedido_{next(self._ids):04d}", con_ttl(a_json(params), self.ttl))
        with self._cond:
            if self._cancelado:
                pedido.futuro.set_exception(BatchFallido("la corrida se canceló"))
            else:
                self._pendientes.append(pedido)
                self._primero = self._primero or time.monotonic()
                self._cond.notify_all()
        return _Espera(pedido.futuro)

    def planificar(self, conversaciones: int, a_la_vez: int) -> None:
        """El orquestador avisa cuántas tandas van a correr y cuántas a la vez. Sin esto, la primera tanda que llega
        a preguntar sale sola en un batch, porque las otras todavía no arrancaron (los hilos no empiezan juntos)."""
        with self._cond:
            self._por_empezar, self._a_la_vez = conversaciones, a_la_vez

    @contextmanager
    def conversacion(self):
        """Una conversación (una tanda) en curso: la ventanilla espera su pedido antes de mandar el batch de la vuelta."""
        with self._cond:
            self._activos += 1
            self._por_empezar = max(0, self._por_empezar - 1)
        try:
            yield
        finally:
            with self._cond:
                self._activos -= 1
                self._cond.notify_all()

    def cancelar(self) -> None:
        """Cancela el batch en curso y lo que espera (Ctrl + C, M6 §7.2). Lo que ya terminó igual vuelve."""
        with self._cond:
            self._cancelado = True
            en_curso, esperando, self._pendientes = self._en_curso, self._pendientes, []
        for pedido in esperando:
            pedido.futuro.set_exception(BatchFallido("la corrida se canceló"))
        if en_curso:
            self.api.messages.batches.cancel(en_curso)
            self.avisar(f"   ✖ batch {en_curso} cancelado")

    # --- La ventanilla (su propio hilo) ---

    def _listo_para_mandar(self) -> bool:
        if not self._pendientes or self._cancelado:
            return False
        esperados = min(self._activos + self._por_empezar, self._a_la_vez)
        if len(self._pendientes) >= esperados:  # dejaron su pedido todas las que tienen que preguntar
            return True
        return time.monotonic() - self._primero >= self.espera_juntar  # una tanda lenta no traba a las demás

    def _despachar(self) -> None:
        while True:
            with self._cond:
                while not self._listo_para_mandar():
                    self._cond.wait(timeout=0.2)
                lote, self._pendientes, self._primero = self._pendientes, [], None
            try:
                self._mandar(lote)
            except Exception as error:  # el batch entero no se pudo crear o consultar: cada fichador recibe el motivo
                with self._cond:
                    self._en_curso = None
                for pedido in lote:
                    if not pedido.futuro.done():
                        pedido.futuro.set_exception(BatchFallido(f"el batch falló: {type(error).__name__}: {error}"))

    def _mandar(self, lote: list[_Pedido]) -> None:
        por_id = {pedido.custom_id: pedido for pedido in lote}
        batch = self.api.messages.batches.create(
            requests=[{"custom_id": pedido.custom_id, "params": pedido.params} for pedido in lote])
        with self._cond:
            self._en_curso = batch.id
        inicio, creado = time.monotonic(), datetime.now()
        self.avisar(f"   📦 batch {batch.id}: {len(lote)} pedido(s)")
        consultas = 0
        while True:  # M6 §7.2: se consulta el estado hasta que termina
            estado = self.api.messages.batches.retrieve(batch.id)
            if estado.processing_status == "ended":
                break
            consultas += 1
            if consultas % AVISO_CADA == 0:
                self.avisar(f"   ⏳ batch {batch.id}: {time.monotonic() - inicio:.0f} s, "
                            f"procesando {estado.request_counts.processing}")
            time.sleep(self.espera_consulta)
        segundos = time.monotonic() - inicio

        # Primero se decide qué le toca a cada pedido; se entrega al final, después de anotar el batch en el registro
        # (así, cuando un fichador sigue, su batch ya quedó anotado).
        estados, reencolar, entregas = Counter(), [], []
        for resultado in self.api.messages.batches.results(batch.id):
            pedido = por_id.pop(resultado.custom_id, None)
            if pedido is None:
                continue  # no es de este lote (no debería pasar): no se le entrega a nadie
            tipo = resultado.result.type
            estados[tipo] += 1
            if tipo == "succeeded":
                entregas.append((pedido, resultado.result.message))
                continue
            if tipo == "errored":
                error = resultado.result.error.error
                motivo, reintentable = f"errored ({error.type}): {error.message}", error.type not in ERRORES_SIN_REINTENTO
            else:  # expired o canceled
                motivo, reintentable = tipo, True
            self._reintentar_o_fallar(pedido, motivo, reintentable, reencolar, entregas)
        for pedido in por_id.values():  # el resultado no vino en el archivo
            estados["sin_resultado"] += 1
            self._reintentar_o_fallar(pedido, "no vino en los resultados", True, reencolar, entregas)

        with self._cond:
            self._en_curso = None
            if reencolar:  # van primero en el batch siguiente
                self._pendientes = reencolar + self._pendientes
                self._primero = self._primero or time.monotonic()
            self._cond.notify_all()
        self.registro.append({"batch_id": batch.id, "creado": f"{creado:%Y-%m-%d %H:%M:%S}", "pedidos": len(lote),
                              "segundos": round(segundos, 1), "estados": dict(estados), "reencolados": len(reencolar)})
        self.ruta_registro.write_text(json.dumps(self.registro, ensure_ascii=False, indent=2), encoding="utf-8")
        resumen = ", ".join(f"{cantidad} {tipo}" for tipo, cantidad in estados.items())
        self.avisar(f"   ✔ batch {batch.id}: {segundos:.0f} s · {resumen}"
                    + (f" · {len(reencolar)} reencolado(s)" if reencolar else ""))
        for pedido, salida in entregas:  # la respuesta, o el BatchFallido con el motivo
            if isinstance(salida, BatchFallido):
                pedido.futuro.set_exception(salida)
            else:
                pedido.futuro.set_result(salida)

    def _reintentar_o_fallar(self, pedido: _Pedido, motivo: str, reintentable: bool, reencolar: list,
                             entregas: list) -> None:
        if reintentable and not self._cancelado and pedido.intentos < self.reintentos:
            pedido.intentos += 1
            pedido.custom_id = f"{pedido.custom_id.split('_r')[0]}_r{pedido.intentos}"  # otro nombre, mismo pedido
            reencolar.append(pedido)
        else:
            detalle = "" if not reintentable or self._cancelado else f" (después de {pedido.intentos} reintento(s))"
            entregas.append((pedido, BatchFallido(f"{pedido.custom_id}: {motivo}{detalle}")))
