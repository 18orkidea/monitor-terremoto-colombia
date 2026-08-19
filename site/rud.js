/* Página del RUD: curva diaria de familias registradas + tabla municipal
   completa con buscador (ordenada por personas). Usa los componentes de ui.js. */
(async function () {
  const { fmt, pct, fechaLarga, diaMes, fetchJson, tablaHidratada, cssVar } = window.UI;
  // rud.json: archivo dedicado (serie + detalle municipal completo día a día),
  // pensado para sobrevivir aunque la fuente original desaparezca.
  const rud = await fetchJson("/data/public/rud.json");
  if (!rud || !rud.serie || !rud.serie.length) {
    document.getElementById("rud-nota").textContent =
      "Todavía no hay ninguna captura del registro oficial de damnificados. " +
      "Vuelve a intentarlo en unos minutos.";
    return;
  }
  document.getElementById("generado").textContent =
    "Actualizado el " + fechaLarga(rud.generado);
  const serie = rud.serie;

  // ---- curva de familias registradas (SVG a mano, mismo estilo que la portada)
  const el = document.getElementById("rud-chart");
  if (el) {
    const W = Math.max(680, Math.min(el.clientWidth || 900, 1100)), H = 200;
    const M = { t: 26, r: 70, b: 34, l: 64 };
    const maxY = Math.max(...serie.map((d) => d.familias || 0)) * 1.1;
    const x = (i) => serie.length === 1 ? W / 2 :
      M.l + i * (W - M.l - M.r) / (serie.length - 1);
    const y = (v) => M.t + (H - M.t - M.b) * (1 - v / maxY);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Familias registradas en el RUD por día">`;
    for (const t of [0, 0.5, 1]) {
      const v = Math.round(maxY * t), yy = y(v);
      s += `<line x1="${M.l}" x2="${W - M.r}" y1="${yy}" y2="${yy}" stroke="${cssVar("--grid")}"/>` +
        `<text x="${M.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${cssVar("--muted")}">${fmt(v)}</text>`;
    }
    const linea = serie.map((d, i) => `${i ? "L" : "M"} ${x(i)} ${y(d.familias || 0)}`).join(" ");
    s += `<path d="${linea}" fill="none" stroke="${cssVar("--good")}" stroke-width="2.5"/>`;
    serie.forEach((d, i) => {
      // el punto reconstruido se pinta hueco: no es una captura del endpoint
      const rec = d.reconstruido;
      s += `<circle cx="${x(i)}" cy="${y(d.familias || 0)}" r="5" fill="${rec ? cssVar("--surface-1") : cssVar("--good")}" stroke="${cssVar("--good")}" stroke-width="${rec ? 2.5 : 2}"${rec ? ' stroke-dasharray="3 2"' : ""}><title>${fechaLarga(d.fecha)}: ${fmt(d.familias)} familias, ${fmt(d.municipios)} municipios${rec ? ` — punto reconstruido: ${d.origen || ""}` : ""}</title></circle>` +
        `<text x="${x(i)}" y="${y(d.familias || 0) - 10}" text-anchor="middle" font-size="11" font-weight="600" fill="${cssVar("--good")}">${fmt(d.familias)}</text>` +
        `<text x="${x(i)}" y="${H - M.b + 14}" text-anchor="middle" font-size="10" fill="${cssVar("--muted")}">${diaMes(d.fecha)}</text>`;
    });
    s += `<text x="${M.l}" y="14" font-size="11" fill="${cssVar("--ink-2")}">Familias registradas (acumulado por día de captura)</text></svg>`;
    el.innerHTML = s;
  }

  // ---- tabla municipal: los de más habitantes (personas) primero, buscador sobre todos
  const TOP = 15;
  const ult = serie[serie.length - 1];
  const munis = [...rud.municipios]
    .sort((a, b) => (b.personas || 0) - (a.personas || 0));
  const buscar = document.getElementById("rud-buscar");
  if (buscar) buscar.placeholder = `Buscar entre los ${munis.length} municipios registrados…`;

  // ---- filtros: chips excluyentes + departamento, combinables con el buscador
  const CHIPS = [
    { id: "todos", label: "Todos", test: () => true },
    { id: "nuevos", label: "Nuevos", test: (tr) => chip(tr, "nuevos"),
      tip: "Municipios que aparecieron por primera vez en la última captura" },
    { id: "crecieron", label: "Crecieron en la última captura",
      test: (tr) => chip(tr, "crecieron"),
      tip: "Su registro subió respecto a la captura anterior: siguen registrando" },
    { id: "destruidas", label: "Con viviendas destruidas",
      test: (tr) => chip(tr, "destruidas"),
      tip: "El municipio ya ha cargado viviendas destruidas. Que un municipio no salga aquí puede ser que aún no las haya evaluado" },
  ];
  // Los filtros leen las etiquetas que el generador escribió en cada fila.
  const chip = (tr, id) => (tr.dataset.chips || "").split(" ").includes(id);
  const filasTabla = Array.from(
    document.querySelectorAll("#rud-tabla tbody tr[data-buscar]"));

  let chipActivo = "todos";
  let depto = "";

  const contenedorChips = document.getElementById("rud-chips");
  if (contenedorChips) {
    contenedorChips.innerHTML = CHIPS.map((c) => {
      const n = filasTabla.filter(c.test).length;
      return `<button class="chip${c.id === chipActivo ? " activa" : ""}" data-chip="${c.id}"` +
        `${c.tip ? ` title="${c.tip}"` : ""}>${c.label} (${n})</button>`;
    }).join("");
    contenedorChips.onclick = (ev) => {
      const b = ev.target.closest("[data-chip]");
      if (!b) return;
      chipActivo = b.dataset.chip;
      contenedorChips.querySelectorAll("[data-chip]").forEach((x) =>
        x.classList.toggle("activa", x.dataset.chip === chipActivo));
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

  const chipDe = (id) => CHIPS.find((c) => c.id === id) || CHIPS[0];

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
    filtroExtra: (tr) => chipDe(chipActivo).test(tr) && (!depto || tr.dataset.depto === depto),
    columnas: COLUMNAS,
    nota: document.getElementById("rud-nota"),
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
      return cabeza + `${criterio}, de ${TOP} en ${TOP}. ` +
        `La columna Δ compara con la captura anterior; «nuevo» marca los municipios que ` +
        `aparecieron por primera vez el ${fechaLarga(ult.fecha)}. Serie iniciada el ` +
        `${fechaLarga(serie[0].fecha)}. Un cero en las columnas de viviendas puede significar ` +
        `«todavía sin evaluar», no «sin daño».` +
        (serie.some((d) => d.reconstruido)
          ? ` Los puntos huecos de la curva no son capturas del RUD: se reconstruyeron ` +
            `desde otra evidencia archivada porque ese día se perdió la corrida, y de ` +
            `ellos solo se conoce el total, no el detalle municipal.`
          : "");
    },
    vacio: `Sin coincidencias entre los municipios registrados. Que un municipio no ` +
      `aparezca significa «sin registro aún», no «sin daño».`,
  });
})();
