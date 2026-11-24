// Pantalla Corridas y costos: los números de la última corrida real y el botón para correr todo de nuevo (con aviso
// de cuánto tarda y cuánto cuesta antes de arrancar).
"use strict";

(() => {
  const { escapar } = Ceibo;
  const $costos = document.getElementById("costos");
  const estado = { datos: null, corrida: { estado: "quieta" }, modo: "ahora", confirmando: false, error: "", reloj: null };

  function caja(titulo, id, contenido, clase = "caja-blanca caja-columna") {
    return `<section class="${clase}" aria-labelledby="${id}"><h2 class="caja-titulo-2" id="${id}">${titulo}</h2>${contenido}</section>`;
  }

  function correrTodo() {
    const d = estado.datos, c = estado.corrida;
    if (c.estado === "corriendo") {
      const porcentaje = c.total ? Math.min(100, Math.round(100 * c.hechas / c.total)) : 0;
      return caja("Correr todo de nuevo", "t-correr",
        `<div class="avance-corrida" role="status"><span class="avance-numero"><strong>${c.hechas}</strong> de ${c.total} fichas armadas</span>` +
        `<div class="avance-riel" aria-hidden="true"><div class="avance-lleno" style="width: ${porcentaje}%"></div></div>` +
        `<p class="avance-nota">Corriendo ${c.lote ? "por lote" : "ahora"} hace ${escapar(c.tiempo || "")}. Podés seguir usando Ceibo mientras tanto; ` +
        `para subir una lista, esperá a que termine.</p></div>`);
    }
    if (!d.opciones_de_corrida) return "";
    const modos = d.opciones_de_corrida.map((o) => `<label class="modo"><input type="radio" name="modo" value="${o.clave}"` +
      `${estado.modo === o.clave ? " checked" : ""}><span class="modo-textos"><span class="modo-titulo">${escapar(o.titulo)}</span>` +
      `<span class="modo-detalle">${escapar(o.detalle)}</span></span></label>`).join("");
    const elegido = d.opciones_de_corrida.find((o) => o.clave === estado.modo);
    const final = c.estado === "lista" ? `<p class="resultado-corrida resultado-bien" role="status">${escapar(c.texto)}</p>`
      : c.estado === "problema" ? `<p class="resultado-corrida resultado-mal" role="alert">${escapar(c.motivo)}</p>` : "";
    const accion = estado.confirmando
      ? `<div class="confirmar" role="alertdialog" aria-labelledby="texto-confirmar"><p class="confirmar-texto" id="texto-confirmar">` +
        `Va a correr los ${d.cantidad_proveedores || 9} proveedores de punta a punta con la IA: ${escapar(elegido.detalle.charAt(0).toLowerCase() + elegido.detalle.slice(1))}. ` +
        `Las fichas se vuelven a armar y reemplazan a las actuales. ¿Seguimos?</p>` +
        `<div class="confirmar-botones"><button type="button" class="boton-primario" id="si-correr">Sí, correr</button>` +
        `<button type="button" class="boton-secundario" id="no-correr">Cancelar</button></div></div>`
      : `<button type="button" class="boton-primario boton-correr" id="correr">Correr los ${d.cantidad_proveedores || 9} proveedores</button>`;
    return caja("Correr todo de nuevo", "t-correr",
      `<fieldset class="modos"${estado.confirmando ? " disabled" : ""}><legend class="solo-lectores">Cómo correrlo</legend>${modos}</fieldset>` +
      accion + final + (estado.error ? `<p class="resultado-corrida resultado-mal" role="alert">${escapar(estado.error)}</p>` : ""));
  }

  function pintar() {
    const d = estado.datos;
    if (!d.hay_corrida) {
      $costos.innerHTML = `<div class="sin-corrida">Todavía no hay ninguna corrida completa: se corre con el botón de abajo o con python correr_todo.py.</div>` +
        `<div class="costos-cuerpo"><aside class="costos-costado">${correrTodo()}</aside></div>`;
      return;
    }
    const etapas = d.etapas.map((e) => `<li class="etapa-fila"><div class="etapa-datos"><span class="etapa-nombre">${escapar(e.titulo)}</span>` +
      `<span class="etapa-tiempo">${escapar(e.tiempo)}</span><span class="etapa-costo">${escapar(e.costo)}</span></div>` +
      `<div class="riel" aria-hidden="true"><div class="riel-lleno" style="width: ${e.ancho}%"></div></div></li>`).join("");
    const filas = d.proveedores.map((p) => `<tr><td class="nombre">${escapar(p.nombre)}</td><td class="derecha">${p.fichas}</td>` +
      `<td class="celda-barra"><div class="barra-costo"><div class="barra-costo-riel" aria-hidden="true"><div class="barra-costo-lleno" style="width: ${p.ancho}%"></div></div>` +
      `<span class="barra-costo-valor">${escapar(p.costo)}</span></div></td><td class="por-ficha">${escapar(p.por_ficha)}</td></tr>`).join("");
    const ev = d.evaluador, cq = d.consultas;
    const calidad = (ev ? `<div class="calidad-dato"><span class="calidad-valor">${ev.ficha} de ${ev.casos}</span><span class="calidad-texto">fichas controladas a mano salieron idénticas. ` +
        `${ev.fuente === ev.casos ? `Las ${ev.casos}` : `${ev.fuente} de ${ev.casos}`} citan el lugar correcto del archivo.</span></div>` : "") +
      (cq ? `<div class="calidad-dato"><span class="calidad-valor">${cq.bien} de ${cq.total}</span><span class="calidad-texto">preguntas de prueba bien contestadas por el asistente, a ${escapar(cq.por_consulta)} cada una.</span></div>` : "");
    const ahorro = d.por_ficha_escenarios ? `<section class="caja-ahorro" aria-labelledby="t-ahorro"><h2 class="caja-titulo-2" id="t-ahorro">Cuánto cuesta cada ficha</h2>` +
      d.por_ficha_escenarios.map((x) => `<div class="ahorro-fila"><span>${escapar(x.titulo)}</span><span class="${x.mejor ? "ahorro-mejor" : "ahorro-valor"}">${escapar(x.valor)}</span></div>`).join("") +
      (d.cache != null ? `<p class="ahorro-nota">Ceibo guarda las instrucciones y el estándar para no pagarlos en cada paso: el ${d.cache} % de lo que lee sale de esa memoria.</p>` : "") +
      `</section>` : "";
    $costos.innerHTML =
      `<div class="datos"><div class="dato"><span class="dato-valor">${d.fichas}</span><span class="dato-texto">fichas armadas</span></div>` +
      `<div class="dato"><span class="dato-valor">${escapar(d.tiempo)}</span><span class="dato-texto">de punta a punta</span></div>` +
      `<div class="dato"><span class="dato-valor">${escapar(d.costo)}</span><span class="dato-texto">toda la corrida</span></div>` +
      `<div class="dato"><span class="dato-valor">${escapar(d.por_ficha)}</span><span class="dato-texto">por ficha</span></div></div>` +
      `<div class="costos-cuerpo"><div class="costos-principal">` +
      `<section class="caja-blanca" aria-labelledby="t-etapas"><h2 class="caja-titulo-2" id="t-etapas">En qué se fue el tiempo</h2>` +
      `<p class="caja-bajada">Última corrida: ${escapar(d.fecha)}, ${escapar(d.modo)}.</p><ol class="etapas-lista">${etapas}</ol></section>` +
      `<section class="caja-tabla" aria-labelledby="t-prov"><h2 class="caja-titulo-2" id="t-prov">Cuánto costó cada proveedor</h2>` +
      `<div class="tabla-marco-costos"><table class="tabla-costos"><thead><tr><th scope="col">Proveedor</th><th scope="col" class="derecha">Fichas</th>` +
      `<th scope="col">Costo</th><th scope="col" class="derecha">Por ficha</th></tr></thead><tbody>${filas}</tbody></table></div></section></div>` +
      `<aside class="costos-costado">${correrTodo()}` + (calidad ? caja("Qué tan bien salió", "t-calidad", calidad) : "") + ahorro + `</aside></div>`;
  }

  async function cargar() {
    const r = await fetch("/api/costos");
    if (!r.ok) throw new Error(r.statusText);
    const d = await r.json();
    estado.datos = d.datos;
    estado.corrida = d.corrida;
    pintar();
    if (estado.corrida.estado === "corriendo") seguir();
  }

  function seguir() {
    clearInterval(estado.reloj);
    estado.reloj = setInterval(async () => {
      try {
        const r = await fetch("/api/costos/corrida");
        const c = await r.json();
        const termino = estado.corrida.estado === "corriendo" && c.estado !== "corriendo";
        estado.corrida = c;
        if (termino) { clearInterval(estado.reloj); await cargar(); return; }
        pintar();
      } catch { /* se reintenta en la próxima vuelta */ }
    }, 1000);
  }

  $costos.addEventListener("change", (e) => { if (e.target.name === "modo") { estado.modo = e.target.value; } });
  $costos.addEventListener("click", async (e) => {
    if (e.target.closest("#correr")) { estado.confirmando = true; estado.error = ""; pintar(); document.getElementById("si-correr").focus(); return; }
    if (e.target.closest("#no-correr")) { estado.confirmando = false; pintar(); return; }
    if (e.target.closest("#si-correr")) {
      estado.confirmando = false;
      try {
        const r = await fetch("/api/costos/corrida", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lote: estado.modo === "lote" }) });
        const datos = await r.json();
        if (!r.ok) throw new Error(datos.error || "No se pudo arrancar.");
        estado.corrida = datos;
        pintar();
        seguir();
      } catch (error) { estado.error = error.message; pintar(); }
    }
  });

  cargar().catch(() => { $costos.innerHTML = `<div class="sin-corrida">No se pudieron cargar los números. ¿Sigue abierto el servidor?</div>`; });
})();
