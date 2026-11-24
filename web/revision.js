// Pantalla Para revisar: los productos que Ceibo no pudo resolver solo, la evidencia y la decisión de la persona.
// La decisión se guarda aparte (salida/decisiones.json): la ficha no cambia.
"use strict";

(() => {
  const { escapar, chipFuente } = Ceibo;
  const $grupos = document.getElementById("grupos");
  const $evidencia = document.getElementById("evidencia");
  const parametros = new URLSearchParams(location.search);

  const CHEVRON = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#55625C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg>';
  const MARCAS = {
    si: '<span role="img" aria-label="Coincide" class="marca-coincide"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1E7F55" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg></span>',
    nombre: '<span role="img" aria-label="Coincide (está dentro del nombre del catálogo)" class="marca-coincide"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1E7F55" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg></span>',
    falta: '<span role="img" aria-label="Falta" class="marca-falta"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A5B00" stroke-width="3" stroke-linecap="round"><path d="M12 7v6M12 17h.01"></path></svg></span>',
    no: '<span role="img" aria-label="No coincide" class="marca-no"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#B4282B" stroke-width="3" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"></path></svg></span>',
  };
  const TILDE = (color) => `<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg>`;

  const estado = { datos: null, elegido: parametros.get("ficha"), abierto: null, verPedido: false, guardando: false, error: "" };

  function todos() { return estado.datos.grupos.flatMap((g) => g.productos); }
  function elegido() { return todos().find((p) => p.id === estado.elegido); }

  // ---------- La lista, por grupo ----------
  function pintarGrupos() {
    const d = estado.datos;
    if (!d.total) {
      $grupos.innerHTML = `<div class="sin-pendientes">No hay productos para revisar: todo lo que llegó se resolvió solo.</div>`;
      return;
    }
    $grupos.innerHTML = d.grupos.map((g) => {
      const cabeza = `<span class="grupo-textos"><span class="grupo-nombre">${escapar(g.titulo)}</span><span class="grupo-detalle">${escapar(g.detalle)}</span></span>` +
        `<span class="grupo-cantidad">${g.productos.length}</span>`;
      if (g.clave !== estado.abierto) {
        return `<button type="button" class="grupo-cerrado" data-grupo="${g.clave}" aria-expanded="false">${cabeza}${CHEVRON}</button>`;
      }
      return `<div class="grupo-abierto"><div class="grupo-cabeza">${cabeza}</div>` + g.productos.map((p) =>
        `<button type="button" class="item-revisar" data-id="${escapar(p.id)}"${p.id === estado.elegido ? ' aria-current="true"' : ""}>` +
        `<span class="item-revisar-nombre">${escapar(p.nombre)}</span>` +
        `<span class="item-revisar-detalle">${escapar(p.proveedor_corto)}, código ${escapar(p.codigo)}</span>` +
        (p.decision ? `<span class="item-revisar-decision">${TILDE("#155C3D")}${escapar(p.decision.titulo)}</span>` : "") +
        `</button>`).join("") + `</div>`;
    }).join("") +
      `<p class="revision-avance">${d.decididos ? `Decidiste ${d.decididos} de ${d.total}.` : `${d.total} esperan una decisión.`}</p>`;
  }

  // ---------- La evidencia del producto elegido ----------
  function tablaComparacion(p) {
    const filas = p.comparacion.map((c) => `<tr><th scope="row">${escapar(c.campo)}</th>` +
      `<td${c.coincide === "falta" ? ' class="falta"' : ""}>${escapar(c.nuevo)}</td><td>${escapar(c.viejo)}</td>` +
      `<td class="centro">${MARCAS[c.coincide] || ""}</td></tr>`).join("");
    return `<div class="tabla-comparar-marco"><table class="tabla-comparar"><thead><tr><th scope="col"></th>` +
      `<th scope="col">Lo que mandó ${escapar(p.proveedor_corto)}</th>` +
      `<th scope="col">Lo que ya tenemos (${escapar(p.catalogo.sku)})</th><th scope="col" style="text-align: center">¿Coincide?</th>` +
      `</tr></thead><tbody>${filas}</tbody></table></div>` +
      `<div class="sale-de"><span class="sale-de-texto">Sale de</span>${chipFuente(p.fuente)}` +
      `<span class="sale-de-texto">y del catálogo actual,</span>${chipFuente(p.catalogo.fuente)}` +
      `<span class="sale-de-texto">«${escapar(p.catalogo.descripcion)}»</span></div>`;
  }

  function versiones(p) {
    return `<div class="versiones">` + p.versiones.map((v, i) =>
      `<div class="version"><span class="version-etiqueta">${i === 0 ? "Un archivo dice" : "El otro dice"}</span>` +
      `<span class="version-valor">${escapar(v.valor)}</span>${chipFuente(v.fuente)}</div>`).join("") + `</div>`;
  }

  function evidenciaDelGrupo(p) {
    if (p.grupo === "posible_duplicado" && p.comparacion) return tablaComparacion(p);
    if (p.grupo === "conflicto_entre_fuentes" && p.versiones) return versiones(p);
    if (p.grupo === "gtin_invalido" && p.codigo_de_barras) {
      return `<div class="codigo-mandado"><span class="version-etiqueta">El código que mandó</span>` +
        `<span class="codigo-mandado-valor">${escapar(p.codigo_de_barras)}</span></div>` +
        `<div class="sale-de"><span class="sale-de-texto">Sale de</span>${chipFuente(p.fuente)}</div>`;
    }
    return `<div class="sale-de"><span class="sale-de-texto">Sale de</span>${chipFuente(p.fuente)}</div>`;
  }

  function decidir(p) {
    const decision = p.decision;
    const botones = p.opciones.map((o, i) => {
      const principal = decision ? decision.clave === o.clave : i === 0;
      const marca = decision && decision.clave === o.clave ? TILDE("#FFFFFF") : "";
      return `<button type="button" class="opcion-decision${principal ? " principal" : ""}" data-decision="${escapar(o.clave)}"` +
        `${decision && decision.clave === o.clave ? ' aria-pressed="true"' : ' aria-pressed="false"'}${estado.guardando ? " disabled" : ""}>` +
        `<span class="opcion-decision-titulo">${marca}${escapar(o.titulo)}</span><span class="opcion-decision-detalle">${escapar(o.detalle)}</span></button>`;
    }).join("");
    const anotado = decision
      ? `<div class="anotado" role="status"><span>Anotado el ${escapar(formatoFecha(decision.fecha))}. La ficha no cambia: la decisión queda guardada para el alta.</span>` +
        `<button type="button" class="boton-deshacer" id="deshacer">Deshacer</button></div>`
      : "";
    return `<div class="decidir"><h3 class="decidir-titulo">¿Qué hacemos?</h3>` +
      `<div class="opciones-decision${p.opciones.length === 2 ? " de-a-dos" : ""}">${botones}</div>${anotado}` +
      (estado.error ? `<p class="otros-motivos" role="alert">${escapar(estado.error)}</p>` : "") + `</div>`;
  }

  function formatoFecha(texto) {
    const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2})/.exec(texto || "");
    return m ? `${m[3]}/${m[2]} a las ${m[4]}` : texto;
  }

  function cajaPedido(p) {
    const pedido = estado.datos.pedidos[p.proveedor_id];
    if (!pedido) return "";
    const otros = pedido.productos - 1;
    const resumen = otros > 0
      ? `Incluye lo de este producto y de ${otros === 1 ? "otro producto" : `otros ${otros} productos`} de ${escapar(p.proveedor_corto)}. Lo copiás y se lo mandás.`
      : "Incluye lo de este producto. Lo copiás y se lo mandás.";
    const lista = p.pedido.length ? `<ul class="caja-pedido-lista">${p.pedido.map((x) => `<li>${escapar(x)}</li>`).join("")}</ul>` : "";
    return `<div class="caja-pedido"><span class="caja-pedido-titulo">El pedido a ${escapar(p.proveedor)} ya está armado</span>` +
      `<span class="caja-pedido-texto">${resumen}</span>` +
      (lista ? `<span class="caja-pedido-texto">De este producto le pide:</span>${lista}` : "") +
      (estado.verPedido
        ? `<pre class="mensaje-pedido" id="mensaje-pedido">${escapar(pedido.mensaje)}</pre>` +
          `<div class="acciones-pedido"><button type="button" class="boton-secundario boton-chico" id="copiar-pedido">Copiar el pedido</button>` +
          `<button type="button" class="boton-ver-pedido" id="ver-pedido">Ocultar</button></div>`
        : `<button type="button" class="boton-ver-pedido" id="ver-pedido">Ver el pedido</button>`) + `</div>`;
  }

  function pintarEvidencia() {
    const p = elegido();
    if (!p) { $evidencia.innerHTML = estado.datos.total ? `<p class="evidencia-proveedor">Elegí un producto de la lista.</p>` : ""; $evidencia.hidden = !estado.datos.total; return; }
    $evidencia.hidden = false;
    $evidencia.innerHTML =
      `<div class="evidencia-cabeza"><p class="evidencia-proveedor">${escapar(p.proveedor)}, código ${escapar(p.codigo)}</p>` +
      `<h2 class="evidencia-pregunta" id="titulo-evidencia">${escapar(p.pregunta)}</h2>` +
      `<p class="evidencia-nombre">${escapar(p.nombre)}</p>` +
      `<p class="evidencia-explicacion">${escapar(p.explicacion)}</p>` +
      (p.otros_motivos.length ? `<p class="otros-motivos">También: ${p.otros_motivos.map(escapar).join("; ")}.</p>` : "") + `</div>` +
      evidenciaDelGrupo(p) + decidir(p) + cajaPedido(p);
  }

  function pintar() {
    pintarGrupos();
    pintarEvidencia();
    const p = new URLSearchParams();
    if (estado.elegido) p.set("ficha", estado.elegido);
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
  }

  function elegir(id) {
    estado.elegido = id;
    estado.verPedido = false;
    estado.error = "";
    const p = elegido();
    if (p) estado.abierto = p.grupo;
    pintar();
    $evidencia.scrollTop = 0;
  }

  // ---------- Eventos ----------
  $grupos.addEventListener("click", (e) => {
    const item = e.target.closest(".item-revisar");
    if (item) { elegir(item.dataset.id); return; }
    const grupo = e.target.closest(".grupo-cerrado");
    if (grupo) {
      const g = estado.datos.grupos.find((x) => x.clave === grupo.dataset.grupo);
      if (g && g.productos.length) elegir(g.productos[0].id);
    }
  });

  $evidencia.addEventListener("click", async (e) => {
    if (e.target.closest("#ver-pedido")) { estado.verPedido = !estado.verPedido; pintarEvidencia(); return; }
    if (e.target.closest("#copiar-pedido")) {
      const boton = e.target.closest("#copiar-pedido");
      try { await navigator.clipboard.writeText(document.getElementById("mensaje-pedido").textContent); boton.textContent = "Copiado"; }
      catch { const r = document.createRange(); r.selectNodeContents(document.getElementById("mensaje-pedido")); getSelection().removeAllRanges(); getSelection().addRange(r); boton.textContent = "Seleccionado: Ctrl+C para copiar"; }
      return;
    }
    const opcion = e.target.closest(".opcion-decision");
    const deshacer = e.target.closest("#deshacer");
    if (!opcion && !deshacer) return;
    const p = elegido();
    await guardar(p, deshacer ? null : opcion.dataset.decision);
  });

  async function guardar(p, clave) {
    estado.guardando = true; estado.error = ""; pintarEvidencia();
    try {
      const respuesta = await fetch("/api/decisiones", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item: p.id, decision: clave }),
      });
      const datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || "No se pudo guardar.");
      p.decision = datos.decision;
      estado.datos.decididos = todos().filter((x) => x.decision).length;
    } catch (error) {
      estado.error = "No se pudo guardar la decisión: " + error.message;
    } finally {
      estado.guardando = false;
      pintar();
    }
  }

  async function arrancar() {
    $grupos.innerHTML = `<p class="revision-avance">Cargando…</p>`;
    try {
      const respuesta = await fetch("/api/revision");
      if (!respuesta.ok) throw new Error(respuesta.statusText);
      estado.datos = await respuesta.json();
      const lista = todos();
      if (!lista.some((p) => p.id === estado.elegido)) estado.elegido = lista.length ? lista[0].id : null;
      const p = elegido();
      estado.abierto = p ? p.grupo : null;
      pintar();
      const actual = $grupos.querySelector('.item-revisar[aria-current="true"]');
      if (actual && parametros.get("ficha")) actual.scrollIntoView({ block: "center" });
    } catch (error) {
      $grupos.innerHTML = `<div class="sin-pendientes">No se pudieron cargar los productos. ¿Sigue abierto el servidor? Recargá la página.</div>`;
      $evidencia.hidden = true;
    }
  }

  arrancar();
})();
