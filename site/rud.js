/* Página del RUD: el gráfico, los chips, la tabla municipal y la prosa del pie
   los escribe el build (deploy/render_html.py). Aquí queda solo lo que el
   navegador es el único que puede hacer: filtrar, ordenar, paginar y decir
   cuántos municipios quedan a la vista. Usa los componentes de ui.js. */
(async function () {
  const { fmt, fetchJson, tablaHidratada } = window.UI;
  // rud.json: archivo dedicado (serie + detalle municipal completo día a día),
  // pensado para sobrevivir aunque la fuente original desaparezca.
  const rud = await fetchJson("/data/public/rud.json");
  // Sin serie no hay nada que hidratar, y no hay nada que avisar tampoco: la
  // entradilla, el gráfico, los chips, la tabla y el pie ya llegan escritos
  // desde el build. Antes esta rama escribía el aviso en `#rud-nota` sin
  // guarda, y con el contenedor ausente la excepción se llevaba por delante el
  // resto del guion. No se le pone un `if` a la llamada: se le quita el motivo.
  if (!rud || !rud.serie || !rud.serie.length) return;
  const serie = rud.serie;

  // ---- tabla municipal: los de más habitantes (personas) primero, buscador sobre todos
  const TOP = 15;
  const ult = serie[serie.length - 1];
  const munis = [...rud.municipios]
    .sort((a, b) => (b.personas || 0) - (a.personas || 0));
  const buscar = document.getElementById("rud-buscar");
  if (buscar) buscar.placeholder = `Buscar entre los ${munis.length} municipios registrados…`;

  // ---- filtros: chips excluyentes + departamento, combinables con el buscador
  // Los chips los pinta el build, con su recuento salido del mismo predicado
  // que etiquetó cada fila (render_html.py::CHIPS_RUD). Aquí no se repite la
  // definición: se lee `data-chip` del botón y `data-chips` de la fila, que es
  // lo que el generador ya escribió. Duplicarla en JavaScript era tener el
  // número del chip y el filtro contando cosas distintas el día que una de las
  // dos cambiara (M2).
  const enChip = (tr, id) => (tr.dataset.chips || "").split(" ").includes(id);
  const filasTabla = Array.from(
    document.querySelectorAll("#rud-tabla tbody tr[data-buscar]"));

  let chipActivo = "todos";
  let depto = "";

  const contenedorChips = document.getElementById("rud-chips");
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

  const selDepto = document.getElementById("rud-depto");
  if (selDepto) {
    const cuenta = {};
    filasTabla.forEach((tr) => {
      cuenta[tr.dataset.depto] = (cuenta[tr.dataset.depto] || 0) + 1;
    });
    selDepto.add(new Option(`Todos los departamentos (${filasTabla.length})`, ""));
    // localeCompare, no .sort() a secas: por code point CÓRDOBA caería DESPUÉS
    // de CUNDINAMARCA en cuanto el AOI crezca
    Object.keys(cuenta).sort((a, b) => a.localeCompare(b, "es")).forEach((d) =>
      selDepto.add(new Option(`${d} (${cuenta[d]})`, d)));
    selDepto.onchange = () => { depto = selDepto.value; pinta({ reiniciar: true }); };
  }

  // Las columnas llevan su propio nombre para que la nota al pie diga el
  // criterio de orden vigente sin mantener una lista paralela que se desfase.
  const COLUMNAS = (() => {
    const th = [...document.querySelectorAll("#rud-tabla thead th")];
    const porNombre = (a, b) =>
      (a.dataset.v0 || "").localeCompare(b.dataset.v0 || "", "es");
    return [
      { nombre: "municipio" },
      { nombre: "familias" },
      { nombre: "personas" },
      { nombre: "población" },
      { nombre: "% de población" },
      { nombre: "viviendas destruidas" },
      { nombre: "viviendas averiadas" },
      { nombre: "cambio del día" },
    ].map((c, i) => ({ ...c, th: th[i], desempate: i ? porNombre : undefined }));
  })();

  const pinta = tablaHidratada({
    tbody: document.querySelector("#rud-tabla tbody"),
    input: buscar,
    paginado: document.getElementById("paginado"),
    porPagina: TOP,
    filtroExtra: (tr) => (chipActivo === "todos" || enChip(tr, chipActivo)) &&
      (!depto || tr.dataset.depto === depto),
    columnas: COLUMNAS,
    nota: document.getElementById("rud-nota"),
    // SOLO el recuento vivo: lo que cambia con cada filtro y que solo el
    // navegador sabe. La prosa invariante —el criterio de la columna del
    // cambio diario, el inicio de la serie y la advertencia sobre los ceros de
    // las columnas de viviendas— la escribe render_html.py::nota_rud en
    // `#rud-pie-tabla`, y vive allí y en ningún otro sitio (M2).
    notaTexto: (q, visibles, total, orden) => {
      // el criterio lo manda la cabecera pulsada, si hay alguna: la nota no
      // puede seguir anunciando el orden inicial cuando ya no rige
      const criterio = orden
        ? `ordenados por ${COLUMNAS[orden.i].nombre} en orden ` +
          `${orden.dir === "asc" ? "ascendente" : "descendente"}`
        : "ordenados por personas damnificadas";
      const cabeza = (q || chipActivo !== "todos" || depto)
        ? `${visibles} de ${total} municipios registrados con los filtros activos, `
        : `${total} municipios registrados (${fmt(ult.familias)} familias en total), `;
      return cabeza + `${criterio}, de ${TOP} en ${TOP}.`;
    },
    vacio: `Sin coincidencias entre los municipios registrados. Que un municipio no ` +
      `aparezca significa «sin registro aún», no «sin daño».`,
  });
})();
