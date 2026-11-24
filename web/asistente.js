// Pantalla Asistente: la conversación con el asistente real (el de asistente.py), con la estructura del chat de YamaSend.
// La conversación se abre recién con la primera pregunta. Si salís a otra pantalla y volvés, sigue donde estaba.
"use strict";

(() => {
  const { escapar, chipEstado, chipFuente } = Ceibo;
  const $mensajes = document.getElementById("mensajes");
  const $conversacion = document.getElementById("conversacion");
  const $sugerencias = document.getElementById("sugerencias");
  const $caja = document.getElementById("caja");
  const $pregunta = document.getElementById("pregunta");
  const $enviar = document.getElementById("enviar");
  const GUARDADO = "ceibo.asistente";

  const LOGO = (t) => `<svg aria-hidden="true" width="${t}" height="${t}" viewBox="0 0 28 28"><circle cx="14" cy="7" r="5" fill="#B4282B"></circle><circle cx="20.7" cy="11.8" r="5" fill="#B4282B"></circle><circle cx="18.1" cy="19.7" r="5" fill="#B4282B"></circle><circle cx="9.9" cy="19.7" r="5" fill="#B4282B"></circle><circle cx="7.3" cy="11.8" r="5" fill="#B4282B"></circle><circle cx="14" cy="14" r="3.4" fill="#FFFFFF"></circle></svg>`;
  const QUIEN = `<div class="respuesta-quien"><span class="avatar">${LOGO(16)}</span><span class="respuesta-nombre">Ceibo</span></div>`;
  const FLECHA = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#55625C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>';

  const estado = { id: null, mensajes: [], esperando: false, ejemplos: [], etiquetas: {}, sugerencia: null };

  // Lo que dura mientras la pestaña está abierta (puede no estar disponible: se usa solo si anda)
  function guardar() {
    try { sessionStorage.setItem(GUARDADO, JSON.stringify({ id: estado.id, mensajes: estado.mensajes, sugerencia: estado.sugerencia })); } catch { /* sin guardar */ }
  }
  function recuperar() {
    try { const g = JSON.parse(sessionStorage.getItem(GUARDADO) || "null"); if (g) Object.assign(estado, g); } catch { /* nada */ }
  }

  // ---------- Los mensajes ----------
  function tarjeta(r) {
    const filas = r.items.map((i) => `<a class="fila-producto" href="/fichas?ficha=${encodeURIComponent(i.id)}">` +
      `<span class="fila-producto-codigo">${escapar(i.codigo)}</span><span class="fila-producto-textos">` +
      `<span class="fila-producto-nombre">${escapar(i.nombre)}</span>` +
      (i.detalle ? `<span class="fila-producto-detalle">${escapar(i.detalle)}</span>` : "") + `</span>${FLECHA}</a>`).join("");
    const cabeza = r.valor || r.estado_comun
      ? `<div class="tarjeta-respuesta-cabeza"><div class="tarjeta-respuesta-valor">` +
        (r.valor ? `<span class="tarjeta-respuesta-numero">${escapar(r.valor)}</span>` : "") +
        (r.etiqueta ? `<span class="tarjeta-respuesta-etiqueta">${escapar(r.etiqueta)}</span>` : "") +
        `</div>${r.estado_comun ? chipEstado(r.estado_comun) : ""}</div>`
      : "";
    const pie = r.fuentes.length ? `<div class="tarjeta-respuesta-pie"><span class="sale-de-texto">Sale de</span>${r.fuentes.map(chipFuente).join("")}</div>` : "";
    if (!cabeza && !filas && !pie) return "";
    return `<div class="tarjeta-respuesta">${cabeza}${filas}${pie}</div>`;
  }

  function mensaje(m, nuevo) {
    const clase = nuevo ? " mensaje-nuevo" : "";
    if (m.tipo === "pregunta") return `<p class="pregunta-usuario${clase}">${escapar(m.texto)}</p>`;
    if (m.tipo === "error") {
      return `<div class="respuesta${clase}">${QUIEN}<p class="respuesta-texto respuesta-error">${escapar(m.texto)}</p></div>`;
    }
    const r = m.respuesta;
    return `<div class="respuesta${clase}">${QUIEN}<p class="respuesta-texto">${escapar(r.texto)}</p>${tarjeta(r)}` +
      r.avisos.map((a) => `<p class="respuesta-aviso">Se sacó de la respuesta algo que no se pudo comprobar: ${escapar(a)}</p>`).join("") +
      `<span class="respuesta-meta">${escapar(r.meta)}</span></div>`;
  }

  function pintar(ultimoNuevo) {
    if (!estado.mensajes.length && !estado.esperando) {
      $mensajes.innerHTML = `<div class="bienvenida mensaje-nuevo"><span class="bienvenida-logo">${LOGO(34)}</span>` +
        `<span class="bienvenida-hola">Hola 👋</span><span class="bienvenida-titulo">¿Qué querés saber del catálogo?</span>` +
        `<span class="bienvenida-texto">Contesto con lo que generó el sistema y te muestro de dónde sale cada dato. Si algo no está, te lo digo.</span></div>`;
    } else {
      $mensajes.innerHTML = estado.mensajes.map((m, i) => mensaje(m, ultimoNuevo && i === estado.mensajes.length - 1)).join("") +
        (estado.esperando ? `<div class="respuesta mensaje-nuevo" role="status" aria-label="El asistente está escribiendo">${QUIEN}` +
          `<div class="escribiendo"><span class="punto"></span><span class="punto"></span><span class="punto"></span></div></div>` : "");
    }
    const sugerencias = !estado.mensajes.length ? estado.ejemplos : (estado.sugerencia ? [estado.sugerencia] : []);
    $sugerencias.innerHTML = sugerencias.map((s) => `<button type="button" class="sugerencia" data-pregunta="${escapar(s)}"` +
      `${estado.etiquetas[s] ? ` title="${escapar(s)}"` : ""}${estado.esperando ? " disabled" : ""}>${escapar(estado.etiquetas[s] || s)}</button>`).join("");
    $enviar.disabled = estado.esperando;
    $conversacion.scrollTop = $conversacion.scrollHeight;
  }

  // ---------- Preguntar ----------
  async function preguntar(texto) {
    texto = texto.trim();
    if (!texto || estado.esperando) return;
    estado.mensajes.push({ tipo: "pregunta", texto });
    estado.esperando = true;
    estado.sugerencia = null;
    pintar(true);
    try {
      if (!estado.id) {
        const r = await fetch("/api/asistente/conversaciones", { method: "POST" });
        const datos = await r.json();
        if (!r.ok) throw new Error(datos.error || "No se pudo abrir la conversación.");
        estado.id = datos.id;
      }
      const r = await fetch(`/api/asistente/conversaciones/${encodeURIComponent(estado.id)}/preguntas`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }),
      });
      const datos = await r.json();
      if (r.status === 404) estado.id = null;  // el servidor se reinició: la próxima pregunta abre una nueva
      if (!r.ok) throw new Error(datos.error || "No se pudo contestar.");
      estado.mensajes.push({ tipo: "respuesta", respuesta: datos.respuesta });
      estado.sugerencia = datos.sugerencia;
    } catch (error) {
      estado.mensajes.push({ tipo: "error", texto: error.message || "Algo falló. Probá de nuevo." });
    } finally {
      estado.esperando = false;
      guardar();
      pintar(true);
      $pregunta.focus();
    }
  }

  $caja.addEventListener("submit", (e) => { e.preventDefault(); const t = $pregunta.value; $pregunta.value = ""; ajustarAlto(); preguntar(t); });
  $pregunta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $caja.requestSubmit(); }
  });
  function ajustarAlto() { $pregunta.style.height = "auto"; $pregunta.style.height = Math.min($pregunta.scrollHeight, 132) + "px"; }
  $pregunta.addEventListener("input", ajustarAlto);
  $sugerencias.addEventListener("click", (e) => { const b = e.target.closest(".sugerencia"); if (b && !b.disabled) preguntar(b.dataset.pregunta); });
  document.getElementById("nueva").addEventListener("click", () => {
    if (estado.esperando) return;
    Object.assign(estado, { id: null, mensajes: [], sugerencia: null });
    guardar();
    pintar(false);
    $pregunta.focus();
  });

  recuperar();
  pintar(false);
  fetch("/api/asistente").then((r) => r.json()).then((d) => { estado.ejemplos = d.ejemplos || []; estado.etiquetas = d.etiquetas || {}; pintar(false); }).catch(() => {});
})();
