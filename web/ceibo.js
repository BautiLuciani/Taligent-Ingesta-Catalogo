// Piezas compartidas de las pantallas de Ceibo: escapar texto, chips de estado y de fuente, y el desplegable.
"use strict";

const Ceibo = (() => {
  function escapar(texto) {
    return String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Para buscar sin que importen mayúsculas ni acentos (lo mismo que hace el servidor con el texto de cada ficha)
  function sinAcentos(texto) {
    return String(texto || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase();
  }

  const ESTADOS = {
    lista_para_alta: { texto: "Lista para alta", clase: "chip-alta", color: "#155C3D", trazo: '<path d="M5 12l5 5 9-10"></path>' },
    duplicado: { texto: "Ya estaba en el catálogo", clase: "chip-dup", color: "#2D4675",
      trazo: '<rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>' },
    a_revision: { texto: "Para revisar", clase: "chip-rev", color: "#7A4800",
      trazo: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"></path><circle cx="12" cy="12" r="3"></circle>' },
  };

  function chipEstado(estado) {
    const e = ESTADOS[estado];
    if (!e) return "";
    return `<span class="chip-estado ${e.clase}"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${e.color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${e.trazo}</svg>${e.texto}</span>`;
  }

  // El archivo original del proveedor (los PDF se abren en la página del dato)
  function direccionDelArchivo(fuente) {
    return "/archivos/" + encodeURIComponent(fuente.archivo) + (fuente.pagina ? "#page=" + fuente.pagina : "");
  }

  function chipFuente(fuente) {
    if (!fuente) return "";
    return `<a class="chip-fuente" href="${direccionDelArchivo(fuente)}" target="_blank" rel="noopener" title="${escapar(fuente.detalle)} (abrir el archivo)">` +
      `<span class="chip-fuente-tipo" style="color: ${fuente.color}; background: ${fuente.fondo}">${escapar(fuente.tipo)}</span>` +
      `<span class="chip-fuente-nombre">${escapar(fuente.archivo)}</span><span class="chip-fuente-lugar">${escapar(fuente.ubicacion)}</span></a>`;
  }

  const MARCA_ELEGIDA = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#B4282B" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg>';

  // El desplegable con el diseño de la app. opciones: [{valor, nombre, cantidad?, detalle?, deshabilitada?, todas?}]
  function desplegable(contenedor, { opciones, valor, alElegir }) {
    const boton = contenedor.querySelector(".desplegable-boton");
    const texto = contenedor.querySelector(".desplegable-texto");
    let actual = valor;
    let abierto = false;

    function cerrar(devolverFoco) {
      abierto = false;
      boton.setAttribute("aria-expanded", "false");
      contenedor.querySelectorAll(".desplegable-fondo, .desplegable-lista").forEach((n) => n.remove());
      if (devolverFoco) boton.focus();
    }

    function abrir() {
      abierto = true;
      boton.setAttribute("aria-expanded", "true");
      const fondo = document.createElement("button");
      fondo.type = "button";
      fondo.className = "desplegable-fondo";
      fondo.setAttribute("aria-label", "Cerrar la lista");
      fondo.tabIndex = -1;
      fondo.addEventListener("click", () => cerrar(false));
      const lista = document.createElement("div");
      lista.className = "desplegable-lista";
      lista.setAttribute("role", "listbox");
      lista.setAttribute("aria-label", boton.getAttribute("aria-label") || "Opciones");
      lista.innerHTML = opciones.map((op, i) => {
        const elegida = op.valor === actual;
        return `<button type="button" role="option" class="opcion${op.todas ? " opcion-todas" : ""}" data-i="${i}" aria-selected="${elegida}"${op.deshabilitada ? " disabled" : ""}>` +
          `<span class="opcion-nombre">${escapar(op.nombre)}${op.detalle ? `<span class="opcion-detalle">${escapar(op.detalle)}</span>` : ""}</span>` +
          (op.cantidad != null ? `<span class="opcion-cantidad">${escapar(op.cantidad)}</span>` : "") +
          `<span class="opcion-marca">${elegida ? MARCA_ELEGIDA : ""}</span></button>`;
      }).join("");
      lista.addEventListener("click", (evento) => {
        const opcion = evento.target.closest(".opcion");
        if (!opcion || opcion.disabled) return;
        elegir(opciones[Number(opcion.dataset.i)].valor);
        cerrar(true);
      });
      lista.addEventListener("keydown", (evento) => {
        const botones = [...lista.querySelectorAll(".opcion:not([disabled])")];
        const i = botones.indexOf(document.activeElement);
        if (evento.key === "ArrowDown") { evento.preventDefault(); botones[Math.min(i + 1, botones.length - 1)].focus(); }
        if (evento.key === "ArrowUp") { evento.preventDefault(); botones[Math.max(i - 1, 0)].focus(); }
      });
      contenedor.append(fondo, lista);
      (lista.querySelector('.opcion[aria-selected="true"]') || lista.querySelector(".opcion:not([disabled])")).focus();
    }

    function elegir(nuevo) {
      actual = nuevo;
      const op = opciones.find((o) => o.valor === nuevo);
      texto.textContent = op ? op.nombre : "";
      alElegir(nuevo);
    }

    boton.addEventListener("click", () => (abierto ? cerrar(false) : abrir()));
    contenedor.addEventListener("keydown", (evento) => { if (evento.key === "Escape" && abierto) cerrar(true); });
    const inicial = opciones.find((o) => o.valor === actual);
    if (inicial) texto.textContent = inicial.nombre;

    return {
      cambiarOpciones(nuevas) { opciones = nuevas; },
      valor: () => actual,
      fijar(nuevo) { actual = nuevo; const op = opciones.find((o) => o.valor === nuevo); texto.textContent = op ? op.nombre : ""; },
    };
  }

  return { escapar, sinAcentos, chipEstado, chipFuente, direccionDelArchivo, desplegable };
})();
