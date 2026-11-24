// Pantalla Fichas: trae las fichas reales del servidor y arma la lista, los filtros y el detalle.
// Los filtros quedan en la dirección (?estado=a_revision&proveedor=P08&ficha=P08:IN7003): se puede compartir o
// llegar desde otra pantalla ya filtrado.
"use strict";

(() => {
  const { escapar, sinAcentos, chipEstado, chipFuente, direccionDelArchivo, desplegable } = Ceibo;

  const FILTROS = [
    ["todos", "Todas"], ["lista_para_alta", "Listas para alta"],
    ["duplicado", "Ya estaban en el catálogo"], ["a_revision", "Para revisar"],
  ];

  const parametros = new URLSearchParams(location.search);
  const estado = {
    fichas: [],
    filtro: FILTROS.some(([clave]) => clave === parametros.get("estado")) ? parametros.get("estado") : "todos",
    proveedor: parametros.get("proveedor") || "",
    busqueda: parametros.get("q") || "",
    elegida: parametros.get("ficha") || null,
  };

  const $lista = document.getElementById("lista-fichas");
  const $detalle = document.getElementById("detalle-ficha");
  const $filtros = document.getElementById("filtros-estado");
  const $buscar = document.getElementById("buscar");
  let selector = null;

  function visibles() {
    const buscado = sinAcentos(estado.busqueda.trim());
    return estado.fichas.filter((f) =>
      (estado.filtro === "todos" || f.estado === estado.filtro) &&
      (!estado.proveedor || f.proveedor_id === estado.proveedor) &&
      (!buscado || f.busqueda.includes(buscado)));
  }

  function guardarEnLaDireccion() {
    const p = new URLSearchParams();
    if (estado.filtro !== "todos") p.set("estado", estado.filtro);
    if (estado.proveedor) p.set("proveedor", estado.proveedor);
    if (estado.busqueda.trim()) p.set("q", estado.busqueda.trim());
    if (estado.elegida) p.set("ficha", estado.elegida);
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
  }

  function pintarFiltros() {
    // Las cantidades de cada chip respetan el proveedor y la búsqueda (no el estado: es lo que se elige acá)
    const buscado = sinAcentos(estado.busqueda.trim());
    const base = estado.fichas.filter((f) => (!estado.proveedor || f.proveedor_id === estado.proveedor) &&
      (!buscado || f.busqueda.includes(buscado)));
    $filtros.innerHTML = FILTROS.map(([clave, texto]) => {
      const cantidad = clave === "todos" ? base.length : base.filter((f) => f.estado === clave).length;
      return `<button type="button" class="chip-filtro" data-filtro="${clave}" aria-pressed="${estado.filtro === clave}">${texto}<span class="chip-filtro-cantidad">${cantidad}</span></button>`;
    }).join("");
  }

  function pintarLista(lista) {
    if (!lista.length) {
      $lista.innerHTML = `<div class="sin-resultados"><span class="sin-resultados-titulo">Ningún producto con esos filtros</span>` +
        `<button type="button" class="boton-link" id="ver-todos">Ver todos</button></div>`;
      return;
    }
    $lista.innerHTML = lista.map((f) =>
      `<button type="button" class="item-ficha" data-id="${escapar(f.id)}" aria-pressed="${f.id === estado.elegida}">` +
      `<span class="item-nombre">${escapar(f.nombre)}</span>` +
      `<span class="item-detalle">${escapar(f.proveedor)}, ${escapar(f.precio)}</span>` +
      `<span class="item-estado">${chipEstado(f.estado)}</span></button>`).join("") +
      `<p class="cantidad-mostrada">Mostrando ${lista.length} ${lista.length === 1 ? "producto" : "productos"}` +
      (lista.length < estado.fichas.length ? ` de ${estado.fichas.length}` : "") + `</p>`;
  }

  function pintarDetalle(f) {
    if (!f) {
      $detalle.innerHTML = `<p class="detalle-proveedor">Elegí un producto de la lista para ver su ficha.</p>`;
      return;
    }
    let avisos = "";
    if (f.estado === "a_revision" && f.motivos.length) {
      avisos += `<div class="aviso aviso-revisar"><span class="aviso-titulo">Por qué está para revisar</span>` +
        f.motivos.map((m) => `<span class="aviso-texto">${escapar(m)}</span>`).join("") +
        (f.sku ? `<span class="aviso-texto">Se parece a ${escapar(f.sku)}, «${escapar(f.sku_descripcion || "")}».</span>` : "") +
        `<a href="/revision?ficha=${encodeURIComponent(f.id)}">Resolverlo en Para revisar</a></div>`;
    }
    if (f.estado === "duplicado" && f.sku) {
      avisos += `<div class="aviso aviso-duplicado"><span class="aviso-titulo">Ya está en el catálogo como ${escapar(f.sku)}</span>` +
        `<span class="aviso-texto">«${escapar(f.sku_descripcion || "")}», con el mismo código de barras. No se da de alta de nuevo.</span></div>`;
    }
    const grupos = f.grupos.map((g) => `<div class="grupo"><h3 class="grupo-titulo">${escapar(g.titulo)}</h3>` +
      g.campos.map((c) => `<div class="fila-campo"><span class="campo-etiqueta">${escapar(c.etiqueta)}</span>` +
        `<span class="campo-valor${c.vacio ? " campo-vacio" : ""}">${escapar(c.valor)}</span>${chipFuente(c.fuente)}</div>`).join("") +
      `</div>`).join("");
    const abrir = f.archivo_principal
      ? `<a class="boton-secundario abrir-archivo" href="${direccionDelArchivo(f.archivo_principal)}" target="_blank" rel="noopener">Abrir el archivo del proveedor</a>`
      : "";
    $detalle.innerHTML =
      `<div class="detalle-cabeza"><div style="display: flex">${chipEstado(f.estado)}</div>` +
      `<h2 class="detalle-nombre">${escapar(f.nombre)}</h2>` +
      `<p class="detalle-proveedor">${escapar(f.proveedor)}, código ${escapar(f.codigo)}</p></div>` +
      avisos +
      `<div class="caja-categoria"><span class="caja-categoria-etiqueta">Categoría</span>` +
      `<span class="caja-categoria-valor">${escapar(f.categoria)}</span>` +
      (f.porque ? `<span class="caja-categoria-porque">${escapar(f.porque)}</span>` : "") + `</div>` +
      grupos + abrir;
  }

  function pintar() {
    const lista = visibles();
    if (!lista.some((f) => f.id === estado.elegida)) estado.elegida = lista.length ? lista[0].id : null;
    pintarFiltros();
    pintarLista(lista);
    pintarDetalle(estado.fichas.find((f) => f.id === estado.elegida));
    guardarEnLaDireccion();
  }

  function elegir(id) {
    estado.elegida = id;
    $lista.querySelectorAll(".item-ficha").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
    pintarDetalle(estado.fichas.find((f) => f.id === id));
    $detalle.scrollTop = 0;
    guardarEnLaDireccion();
  }

  $lista.addEventListener("click", (evento) => {
    const item = evento.target.closest(".item-ficha");
    if (item) { elegir(item.dataset.id); return; }
    if (evento.target.id === "ver-todos") {
      estado.filtro = "todos"; estado.proveedor = ""; estado.busqueda = "";
      $buscar.value = ""; selector.fijar("");
      pintar();
    }
  });
  $filtros.addEventListener("click", (evento) => {
    const chip = evento.target.closest(".chip-filtro");
    if (!chip) return;
    estado.filtro = chip.dataset.filtro;
    pintar();
  });
  $buscar.value = estado.busqueda;
  $buscar.addEventListener("input", () => { estado.busqueda = $buscar.value; pintar(); });

  // Descargar en Excel: lo que se está viendo, con los mismos filtros
  const $descargar = document.getElementById("descargar-excel");
  const $descargarTexto = document.getElementById("descargar-texto");
  $descargar.addEventListener("click", async () => {
    const ids = visibles().map((f) => f.id);
    if (!ids.length) return;
    $descargar.disabled = true;
    $descargarTexto.textContent = "Armando el Excel…";
    try {
      const respuesta = await fetch("/api/fichas/excel", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }),
      });
      if (!respuesta.ok) throw new Error(await respuesta.text());
      const archivo = await respuesta.blob();
      const nombre = (respuesta.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "fichas.xlsx";
      const enlace = Object.assign(document.createElement("a"), { href: URL.createObjectURL(archivo), download: nombre });
      document.body.append(enlace); enlace.click(); enlace.remove();
      setTimeout(() => URL.revokeObjectURL(enlace.href), 10000);
      $descargarTexto.textContent = "Descargar en Excel";
    } catch (error) {
      $descargarTexto.textContent = "No se pudo armar el Excel. Probá de nuevo";
      console.error(error);
    } finally {
      $descargar.disabled = false;
    }
  });

  async function arrancar() {
    $lista.innerHTML = `<p class="cantidad-mostrada">Cargando las fichas…</p>`;
    try {
      const respuesta = await fetch("/api/fichas");
      if (!respuesta.ok) throw new Error(respuesta.statusText);
      const datos = await respuesta.json();
      estado.fichas = datos.fichas;
      if (estado.proveedor && !datos.proveedores.some((p) => p.id === estado.proveedor)) estado.proveedor = "";
      selector = desplegable(document.getElementById("selector-proveedor"), {
        opciones: [{ valor: "", nombre: "Todos los proveedores", cantidad: datos.fichas.length, todas: true }]
          .concat(datos.proveedores.map((p) => ({ valor: p.id, nombre: p.nombre, cantidad: p.cantidad }))),
        valor: estado.proveedor,
        alElegir: (valor) => { estado.proveedor = valor; pintar(); },
      });
      pintar();
      // Si se llegó con una ficha elegida (?ficha=...), la lista arranca mostrándola
      const elegida = $lista.querySelector('.item-ficha[aria-pressed="true"]');
      if (elegida && parametros.get("ficha")) elegida.scrollIntoView({ block: "center" });
    } catch (error) {
      $lista.innerHTML = `<div class="sin-resultados"><span class="sin-resultados-titulo">No se pudieron cargar las fichas</span>` +
        `<span class="item-detalle">¿Sigue abierto el servidor? Recargá la página para probar de nuevo.</span></div>`;
      $detalle.innerHTML = "";
      console.error(error);
    }
  }

  arrancar();
})();
