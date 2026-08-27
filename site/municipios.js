/* Página de municipios: la tabla, la entradilla, los chips con su recuento,
   el aviso del silencio de prensa, la salvedad de los homónimos y la prosa del
   pie los escribe el build (deploy/render_html.py). Aquí queda solo lo que el
   navegador es el único que puede hacer: filtrar, ordenar, paginar y decir
   cuántos municipios quedan a la vista. Usa los componentes de ui.js. */
(function () {
  const { tablaHidratada } = window.UI;

  // Los chips los pinta el build, con su recuento salido del mismo predicado
  // que etiquetó cada fila (render_html.py::CHIPS_MUNICIPIOS). Aquí no se
  // repite la definición: se lee `data-chip` del botón y `data-chips` de la
  // fila, que es lo que el generador ya escribió. Duplicarla en JavaScript era
  // tener el número del chip y el filtro contando cosas distintas el día que
  // una de las dos cambiara.
  const enChip = (tr, id) => (tr.dataset.chips || "").split(" ").includes(id);
  const filasTabla = Array.from(
    document.querySelectorAll("#municipios-tabla tbody tr[data-buscar]"));

  let chipActivo = "todos";
  let depto = "";

  const contenedorChips = document.getElementById("mun-chips");
  if (contenedorChips) {
    contenedorChips.onclick = (ev) => {
      const b = ev.target.closest("[data-chip]");
      if (!b) return;
      chipActivo = b.dataset.chip;
      // las dos mecánicas del mismo estado, igual que las pinta el build: la
      // clase que estiliza el sitio y el aria-pressed que anuncia el lector de
      // pantalla. styles.css las funde en un solo selector.
      contenedorChips.querySelectorAll("[data-chip]").forEach((x) => {
        const activo = x.dataset.chip === chipActivo;
        x.classList.toggle("activa", activo);
        x.setAttribute("aria-pressed", activo ? "true" : "false");
      });
      pinta({ reiniciar: true });
    };
  }

  const selDepto = document.getElementById("mun-depto");
  if (selDepto) {
    const cuenta = {};
    filasTabla.forEach((tr) => {
      cuenta[tr.dataset.depto] = (cuenta[tr.dataset.depto] || 0) + 1;
    });
    selDepto.add(new Option(`Todos los departamentos (${filasTabla.length})`, ""));
    // localeCompare, no .sort() a secas: por code point CÓRDOBA caería después
    // de CUNDINAMARCA
    Object.keys(cuenta).sort((a, b) => a.localeCompare(b, "es")).forEach((d) =>
      selDepto.add(new Option(`${d} (${cuenta[d]})`, d)));
    selDepto.onchange = () => { depto = selDepto.value; pinta({ reiniciar: true }); };
  }

  // El nombre de cada columna viaja aquí para que la nota diga el criterio de
  // orden vigente sin mantener una lista paralela que se desfase.
  const COLUMNAS = (() => {
    const th = [...document.querySelectorAll("#municipios-tabla thead th")];
    const porNombre = (a, b) =>
      (a.dataset.v0 || "").localeCompare(b.dataset.v0 || "", "es");
    return [
      { nombre: "municipio" }, { nombre: "estado" }, { nombre: "población" },
      { nombre: "edificios evaluados por satélite" }, { nombre: "damnificados del RUD" },
      { nombre: "% de población" }, { nombre: "intensidad percibida" },
      { nombre: "respuestas al cuestionario" }, { nombre: "titulares" },
      { nombre: "fuentes" },
    ].map((c, i) => ({ ...c, th: th[i], desempate: i ? porNombre : undefined }));
  })();

  const POR_PAGINA = 20;

  // La tabla ya viene escrita en el HTML desde el build: aquí solo se filtra,
  // ordena y pagina. Ninguna cifra depende de que el navegador ejecute
  // JavaScript, que es lo que necesitan los rastreadores de sistemas de IA.
  const pinta = tablaHidratada({
    tbody: document.querySelector("#municipios-tabla tbody"),
    input: document.getElementById("mun-buscar"),
    paginado: document.getElementById("mun-paginado"),
    porPagina: POR_PAGINA,
    filtroExtra: (tr) => (chipActivo === "todos" || enChip(tr, chipActivo)) &&
      (!depto || tr.dataset.depto === depto),
    columnas: COLUMNAS,
    nota: document.getElementById("mun-nota"),
    // SOLO el recuento vivo: lo que cambia con cada filtro y que solo el
    // navegador sabe. La prosa invariante —el guion de la columna satelital,
    // la celda de prensa de los homónimos, la ausencia que jamás es cero—
    // vive escrita en `#mun-pie-tabla`, y solo ahí.
    notaTexto: (q, visibles, total, orden) => {
      const criterio = orden
        ? `ordenados por ${COLUMNAS[orden.i].nombre} en orden ` +
          `${orden.dir === "asc" ? "ascendente" : "descendente"}`
        : "ordenados por población proyectada para 2026";
      const cabeza = (q || chipActivo !== "todos" || depto)
        ? `${visibles} de ${total} municipios con señal coinciden con los filtros activos, `
        : `${total} municipios del área de influencia con señal del registro oficial de ` +
          `damnificados, la prensa, la intensidad percibida o el satélite, `;
      return cabeza + `${criterio}, de ${POR_PAGINA} en ${POR_PAGINA}.`;
    },
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });
})();
