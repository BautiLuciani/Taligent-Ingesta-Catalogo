// Pantalla Subir una lista: elegir el archivo, decir de qué proveedor es, ver el avance real y el resultado.
// El servidor hace todo el trabajo (subir_lista.py); esta pantalla solo muestra lo que él cuenta.
"use strict";

(() => {
  const { escapar, desplegable } = Ceibo;
  const $zona = document.getElementById("zona-carga");
  const $archivos = document.getElementById("elegir-archivos");
  const MEDIO_SEGUNDO = 500;

  const ICONO_ARCHIVO = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#B4282B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M12 18v-6"></path><path d="M9 15l3-3 3 3"></path></svg>';
  const ICONO_RECIBIDO = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1E7F55" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M9 13l2 2 4-4"></path></svg>';
  const FLECHA = '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3F4B46" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg>';
  const GIRANDO = (color) => `<svg class="girando" aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-9-9"></path></svg>`;
  const TILDE = (tamanio, grosor) => `<svg aria-hidden="true" width="${tamanio}" height="${tamanio}" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="${grosor}" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg>`;
  const EXCLAMACION = (tamanio) => `<svg aria-hidden="true" width="${tamanio}" height="${tamanio}" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round"><path d="M12 7v6"></path><path d="M12 17v.5"></path></svg>`;

  const estado = {
    fase: "vacio",
    error: "",
    proveedores: [],
    ejemplo: null,
    subida: null,          // lo que devolvió el servidor al subir: {subida, excel, fds, sugerido}
    proveedor: "",
    errorEmpezar: "",
    corrida: null,         // el estado que cuenta el servidor (o el de la grabación, en el plan B)
    reloj: null,
  };

  // ---------- Los números del costado y la tabla de abajo ----------
  function pintarInicio(datos) {
    const n = datos.numeros;
    const poner = (id, valor) => { const el = document.getElementById(id); if (el) el.textContent = valor; };
    poner("numero-total", n.total); poner("numero-proveedores", n.proveedores);
    poner("numero-alta", n.lista_para_alta); poner("numero-dup", n.duplicado); poner("numero-rev", n.a_revision);
    poner("aviso-revisar-numero", n.a_revision);
    const barra = document.getElementById("barra");
    barra.setAttribute("aria-label", `${n.lista_para_alta} listos para alta, ${n.duplicado} ya estaban en el catálogo, ${n.a_revision} para revisar`);
    const [alta, dup, rev] = barra.children;
    alta.style.flex = n.lista_para_alta; dup.style.flex = n.duplicado; rev.style.flex = n.a_revision;
    document.getElementById("aviso-revisar").hidden = !n.a_revision;
    document.getElementById("filas-procesadas").innerHTML = datos.procesadas.map((p) =>
      `<tr><td class="celda-nombre">${escapar(p.nombre)}</td><td class="celda-formato">${escapar(p.formato)}</td>` +
      `<td class="celda-numero">${p.productos}</td><td><div class="chips-resultado">` +
      `<span class="chip-resultado chip-alta">${p.alta} listos</span>` +
      (p.duplicado ? `<span class="chip-resultado chip-dup">${p.duplicado} ya estaban</span>` : "") +
      (p.a_revision ? `<span class="chip-resultado chip-rev">${p.a_revision} para revisar</span>` : "") +
      `</div></td></tr>`).join("");
  }

  async function cargarInicio() {
    const respuesta = await fetch("/api/inicio");
    if (!respuesta.ok) throw new Error("no se pudo cargar el inicio");
    const datos = await respuesta.json();
    estado.proveedores = datos.proveedores;
    estado.ejemplo = datos.ejemplo;
    pintarInicio(datos);
    return datos;
  }

  // ---------- Estado vacío ----------
  function pintarVacio() {
    $zona.innerHTML =
      `<div class="zona" id="zona">` +
      `<div class="zona-icono" aria-hidden="true">${ICONO_ARCHIVO}</div>` +
      `<div class="zona-textos"><p class="zona-titulo">Soltá acá la lista del proveedor</p>` +
      `<p class="zona-texto">Un Excel, como te lo mandaron (y sus fichas de seguridad en PDF, si las trae). No hace falta acomodarlo: Ceibo se da cuenta de cómo está armado.</p></div>` +
      `<button type="button" class="boton-primario boton-grande" id="boton-elegir">Elegir archivo</button>` +
      (estado.error ? `<p class="zona-error" role="alert">${escapar(estado.error)}</p>` : "") +
      `</div>` +
      `<p class="plan-b">¿Sin conexión o sin un archivo a mano? <button type="button" class="boton-texto" id="ver-ejemplo">Ver una corrida de ejemplo</button></p>`;
    const $z = document.getElementById("zona");
    document.getElementById("boton-elegir").addEventListener("click", () => $archivos.click());
    document.getElementById("ver-ejemplo").addEventListener("click", verEjemplo);
    $z.addEventListener("dragover", (e) => { e.preventDefault(); $z.classList.add("zona-arrastrando"); });
    $z.addEventListener("dragleave", () => $z.classList.remove("zona-arrastrando"));
    $z.addEventListener("drop", (e) => {
      e.preventDefault(); $z.classList.remove("zona-arrastrando");
      if (e.dataTransfer.files.length) subir([...e.dataTransfer.files]);
    });
  }

  $archivos.addEventListener("change", () => {
    const elegidos = [...$archivos.files];
    $archivos.value = "";
    if (elegidos.length) subir(elegidos);
  });

  async function subir(archivos) {
    estado.error = "";
    const excels = archivos.filter((a) => a.name.toLowerCase().endsWith(".xlsx"));
    if (excels.length !== 1) {
      estado.error = excels.length ? "Elegí un solo Excel: la lista del proveedor." : "Falta el Excel con la lista. Por ahora Ceibo recibe las listas en Excel (.xlsx).";
      pintarVacio();
      return;
    }
    $zona.querySelector("#boton-elegir").disabled = true;
    $zona.querySelector("#boton-elegir").textContent = "Subiendo…";
    let subida = null;
    try {
      for (const archivo of [excels[0], ...archivos.filter((a) => a !== excels[0])]) {
        const direccion = "/api/subidas?nombre=" + encodeURIComponent(archivo.name) + (subida ? "&subida=" + subida.subida : "");
        const respuesta = await fetch(direccion, { method: "POST", body: archivo, headers: { "Content-Type": "application/octet-stream" } });
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.error || "No se pudo subir el archivo.");
        subida = datos;
      }
    } catch (error) {
      estado.error = error.message || "No se pudo subir el archivo.";
      pintarVacio();
      return;
    }
    if (subida.problema) { estado.error = subida.problema; pintarVacio(); return; }
    estado.subida = subida;
    estado.proveedor = subida.sugerido || "";
    estado.errorEmpezar = "";
    estado.fase = "proveedor";
    pintar();
  }

  // ---------- ¿De qué proveedor es? ----------
  function pintarProveedor() {
    const s = estado.subida;
    const fds = s.fds.length ? `, con ${s.fds.length} ${s.fds.length === 1 ? "ficha" : "fichas"} de seguridad` : "";
    $zona.innerHTML =
      `<div class="tarjeta tarjeta-alta tarjeta-proveedor">` +
      `<div class="archivo-recibido"><div class="archivo-icono" aria-hidden="true">${ICONO_RECIBIDO}</div>` +
      `<div class="archivo-textos"><span class="archivo-nombre">${escapar(s.excel)}</span>` +
      `<span class="archivo-detalle">Excel recibido${fds}, todavía no se procesó</span></div>` +
      `<button type="button" class="boton-subrayado" id="otro-archivo">Elegir otro archivo</button></div>` +
      `<div class="pregunta-proveedor"><label class="pregunta-titulo" id="etiqueta-proveedor">¿De qué proveedor es?</label>` +
      `<p class="pregunta-texto">Así Ceibo sabe con qué datos cruzarlo. El resto (cómo está armado, en qué moneda, en qué unidades) lo entiende solo.</p>` +
      `<div class="desplegable desplegable-grande" id="selector-proveedor">` +
      `<button type="button" class="desplegable-boton" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="etiqueta-proveedor">` +
      `<span class="desplegable-texto">Elegí un proveedor</span>${FLECHA}</button></div></div>` +
      `<div class="acciones-proveedor"><button type="button" class="boton-primario boton-grande" id="armar"${estado.proveedor ? "" : " disabled"}>Armar las fichas</button>` +
      `<span class="nota" id="nota-armar">${escapar(estado.errorEmpezar) || "Tarda un par de minutos."}</span></div></div>`;
    const $texto = $zona.querySelector(".desplegable-texto");
    desplegable(document.getElementById("selector-proveedor"), {
      opciones: estado.proveedores.map((p) => ({ valor: p.id, nombre: p.nombre, detalle: p.detalle, deshabilitada: !p.habilitado })),
      valor: estado.proveedor,
      alElegir: (valor) => {
        estado.proveedor = valor;
        document.getElementById("armar").disabled = !valor;
        $texto.classList.remove("desplegable-texto-vacio");
      },
    });
    if (!estado.proveedor) { $texto.textContent = "Elegí un proveedor"; $texto.classList.add("desplegable-texto-vacio"); }
    document.getElementById("otro-archivo").addEventListener("click", reiniciar);
    document.getElementById("armar").addEventListener("click", empezar);
  }

  async function empezar() {
    const $armar = document.getElementById("armar");
    $armar.disabled = true;
    try {
      const respuesta = await fetch("/api/corridas", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subida: estado.subida.subida, proveedor: estado.proveedor }),
      });
      const datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || "No se pudo empezar.");
      seguirCorrida(datos);
    } catch (error) {
      estado.errorEmpezar = error.message;
      const $nota = document.getElementById("nota-armar");
      $nota.textContent = error.message; $nota.setAttribute("role", "alert");
      $armar.disabled = false;
    }
  }

  // ---------- Procesando: se le pregunta al servidor cada medio segundo ----------
  function seguirCorrida(primera) {
    pararReloj();
    estado.corrida = primera;
    estado.fase = primera.estado === "listo" ? "listo" : primera.estado === "problema" ? "problema" : "procesando";
    pintar();
    if (estado.fase !== "procesando") return;
    estado.reloj = setInterval(async () => {
      try {
        const respuesta = await fetch("/api/corridas/" + encodeURIComponent(primera.id));
        if (!respuesta.ok) throw new Error((await respuesta.json()).error);
        actualizar(await respuesta.json());
      } catch (error) {
        pararReloj();
        actualizar({ ...estado.corrida, estado: "problema", problema: { titulo: "Se perdió la conexión con el servidor", detalle: [error.message || "¿Sigue abierto python servidor_web.py?"] } });
      }
    }, MEDIO_SEGUNDO);
  }

  function actualizar(corrida) {
    estado.corrida = corrida;
    if (corrida.estado === "listo" || corrida.estado === "problema") {
      pararReloj();
      estado.fase = corrida.estado;
      pintar();
      if (!corrida.ejemplo) cargarInicio().catch(() => {});  // los números de la derecha y la tabla, ya con esta lista
      return;
    }
    pintarProcesando(true);
  }

  function pararReloj() { if (estado.reloj) { clearInterval(estado.reloj); clearTimeout(estado.reloj); estado.reloj = null; } }

  function cabezaDeArchivo(c, conEstado) {
    const detalle = c.total ? `${escapar(c.proveedor)}, ${c.total} ${c.total === 1 ? "producto" : "productos"}` : escapar(c.proveedor);
    return `<div class="archivo-recibido"><div class="archivo-icono" aria-hidden="true">${ICONO_RECIBIDO}</div>` +
      `<div class="archivo-textos"><span class="archivo-nombre">${escapar(c.archivo)}</span>` +
      `<span class="archivo-detalle">${detalle}</span>` +
      (c.ejemplo ? `<span class="insignia-ejemplo">Corrida de ejemplo, grabada el ${escapar(c.grabada || "")}</span>` : "") +
      `</div>${conEstado ? `<span role="status" class="trabajando">${GIRANDO("currentColor")}Trabajando</span>` : ""}</div>`;
  }

  function etapas(c) {
    return `<ol class="etapas" aria-label="Etapas">` + c.pasos.map((p) => {
      const marca = p.estado === "hecho" ? `<span aria-label="Listo" role="img" class="marca-hecho">${TILDE(14, 3)}</span>`
        : p.estado === "actual" ? `<span aria-label="En curso" role="img" class="marca-actual">${GIRANDO("#17211D")}</span>`
        : p.estado === "error" ? `<span aria-label="Se frenó acá" role="img" class="marca-error">${EXCLAMACION(14)}</span>`
        : `<span aria-label="Pendiente" role="img" class="marca-pendiente"></span>`;
      return `<li class="etapa${p.estado === "pendiente" ? " etapa-pendiente" : ""}"><div class="etapa-marca">${marca}</div>` +
        `<div class="etapa-textos"><span class="etapa-titulo">${escapar(p.titulo)}</span><span class="etapa-linea">${escapar(p.linea)}</span></div></li>`;
    }).join("") + `</ol>`;
  }

  function pintarProcesando(soloCambios) {
    const c = estado.corrida;
    const total = c.total ?? "…";
    const cuadros = c.productos.map((p) => `<div class="tile tile-${p.estado}" title="${escapar(p.codigo + ": " + p.descripcion)}">` +
      (p.estado === "hecho" ? TILDE(18, 3) : "") + `</div>`).join("");
    const html = cabezaDeArchivo(c, true) +
      `<div class="procesando-cuerpo">${etapas(c)}` +
      `<div class="cuadros"><p class="cuadros-cuenta"><span class="cuadros-numero">${c.hechas}</span> de ${total} fichas armadas</p>` +
      `<div role="img" class="grilla-cuadros" aria-label="${c.hechas} de ${total} fichas armadas">${cuadros}</div>` +
      `<p class="cuadros-ahora">${escapar(c.ahora)}</p></div></div>`;
    const $tarjeta = $zona.querySelector(".tarjeta-procesando");
    if (soloCambios && $tarjeta) { if ($tarjeta.dataset.html !== html) { $tarjeta.innerHTML = html; $tarjeta.dataset.html = html; } return; }
    $zona.innerHTML = `<div class="tarjeta tarjeta-alta tarjeta-procesando">${html}</div>`;
    $zona.querySelector(".tarjeta-procesando").dataset.html = html;
  }

  // ---------- Listo ----------
  function pintarListo() {
    const c = estado.corrida, r = c.resultado;
    const numero = (valor, texto, clase) => `<div class="listo-numero${valor ? " " + clase : ""}"><span class="listo-numero-valor">${valor}</span><span class="listo-numero-texto">${texto}</span></div>`;
    const filas = r.columnas.map((col) => `<tr><td class="columna-archivo">${escapar(col.columna)}</td>` +
      `<td class="${col.usa ? "dato-usa" : "dato-no-usa"}">${escapar(col.dato)}</td><td>${escapar(col.ejemplo)}</td></tr>`).join("");
    $zona.innerHTML =
      `<div class="tarjeta">` +
      (c.ejemplo ? `<span class="insignia-ejemplo" style="margin-top: 0">Corrida de ejemplo, grabada el ${escapar(c.grabada || "")}</span>` : "") +
      `<div class="listo-cabeza"><div class="listo-icono" aria-hidden="true">${TILDE(24, 2.6)}</div>` +
      `<div class="listo-textos"><h2 class="listo-titulo">${escapar(r.titulo)}</h2><p class="listo-bajada">${escapar(r.bajada)}</p></div></div>` +
      `<div class="listo-numeros">${numero(r.alta, "Listos para alta", "listo-numero-alta")}` +
      `${numero(r.duplicado, "Ya estaban en el catálogo", "listo-numero-dup")}${numero(r.a_revision, "Para revisar", "listo-numero-rev")}</div>` +
      (filas ? `<div class="entendido"><h3 class="entendido-titulo">Así entendimos el archivo</h3><div class="tabla-marco"><table class="tabla-entendido">` +
        `<thead><tr><th scope="col">Columna del archivo</th><th scope="col">Para Ceibo es</th><th scope="col">Ejemplo de la fila ${escapar(r.fila_ejemplo ?? "")}</th></tr></thead>` +
        `<tbody>${filas}</tbody></table></div></div>` : "") +
      `<div class="listo-pie"><div class="listo-botones">` +
      `<a href="/fichas?proveedor=${encodeURIComponent(c.proveedor_id)}" class="boton-primario">Ver las ${r.total} fichas</a>` +
      `<a href="/asistente" class="boton-secundario">Preguntarle al asistente</a></div>` +
      `<div class="listo-linea"><span class="listo-tiempo">${escapar(r.tiempo_y_costo)}${c.ejemplo ? " (cuando se grabó)" : ""}</span>` +
      `<button type="button" class="boton-otra" id="subir-otra">Subir otra lista</button></div></div></div>`;
    document.getElementById("subir-otra").addEventListener("click", reiniciar);
  }

  // ---------- Algo no salió ----------
  function pintarProblema() {
    const c = estado.corrida, p = c.problema || { titulo: "La lista no entró", detalle: [] };
    $zona.innerHTML =
      `<div class="tarjeta">` + cabezaDeArchivo(c, false) +
      `<div class="listo-cabeza"><div class="listo-icono listo-icono-problema" aria-hidden="true">${EXCLAMACION(24)}</div>` +
      `<div class="listo-textos"><h2 class="listo-titulo">${escapar(p.titulo)}</h2>` +
      `<p class="listo-bajada">No se guardó ninguna ficha de esta lista: las que ya estaban quedan como estaban.</p></div></div>` +
      etapas(c) +
      (p.detalle.length ? `<ul class="problema-detalle" role="alert">${p.detalle.map((d) => `<li>${escapar(d)}</li>`).join("")}</ul>` : "") +
      `<div class="listo-linea"><button type="button" class="boton-otra" id="subir-otra">Subir otra lista</button></div></div>`;
    document.getElementById("subir-otra").addEventListener("click", reiniciar);
  }

  // ---------- Plan B: la última corrida que terminó bien, tal cual pasó ----------
  async function verEjemplo() {
    let grabacion;
    try {
      if (!estado.ejemplo) throw new Error("sin grabación");
      const respuesta = await fetch("/api/corrida_de_ejemplo");
      if (!respuesta.ok) throw new Error((await respuesta.json()).error);
      grabacion = await respuesta.json();
    } catch (error) {
      estado.error = "Todavía no hay ninguna corrida grabada: se graba sola la primera vez que una lista termina bien.";
      pintarVacio();
      return;
    }
    const estados = grabacion.estados.map((e) => ({ ...e, ejemplo: true, grabada: grabacion.fecha }));
    pararReloj();
    estado.error = "";
    estado.corrida = estados[0];
    estado.fase = "procesando";
    pintar();
    let i = 0;
    const siguiente = () => {
      i += 1;
      if (i >= estados.length) return;
      const espera = Math.max(0, (estados[i].t - estados[i - 1].t) * 1000);
      estado.reloj = setTimeout(() => { actualizar(estados[i]); if (estado.fase === "procesando") siguiente(); }, espera);
    };
    siguiente();
  }

  function reiniciar() {
    pararReloj();
    Object.assign(estado, { fase: "vacio", error: "", subida: null, proveedor: "", errorEmpezar: "", corrida: null });
    pintar();
  }

  function pintar() {
    if (estado.fase === "vacio") pintarVacio();
    else if (estado.fase === "proveedor") pintarProveedor();
    else if (estado.fase === "procesando") pintarProcesando(false);
    else if (estado.fase === "listo") pintarListo();
    else pintarProblema();
  }

  // Al abrir la pantalla: los números y, si había una lista procesándose (se recargó la página), se sigue mirando
  pintar();
  cargarInicio().then(async (datos) => {
    if (!datos.en_curso) return;
    const respuesta = await fetch("/api/corridas/" + encodeURIComponent(datos.en_curso));
    if (respuesta.ok) seguirCorrida(await respuesta.json());
  }).catch(() => {
    estado.error = "No se pudo hablar con el servidor. ¿Sigue abierto python servidor_web.py?";
    pintarVacio();
  });
})();
