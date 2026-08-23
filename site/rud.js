/* Página del RUD: acumulado y altas entre capturas + tabla municipal completa
   con buscador (ordenada por personas). Usa los componentes de ui.js. */
(function (global) {
  "use strict";

  function altasDiarias(serie) {
    return serie.map((d, i) => ({
      fecha: d.fecha,
      familias: !i || d.familias == null || serie[i - 1].familias == null
        ? null
        : d.familias - serie[i - 1].familias,
    }));
  }

  function graficoFamilias(serie, ancho, ui) {
    const { fmt, fechaLarga, diaMes, cssVar, esc } = ui;
    const W = Math.max(680, Math.min(ancho || 900, 1100)), H = 230;
    const M = { t: 38, r: 70, b: 38, l: 64 };
    const altas = altasDiarias(serie);
    const cambios = altas.map((d) => d.familias).filter((v) => v != null);
    const maxTotal = Math.max(1, ...serie.map((d) => d.familias || 0), ...cambios);
    const minCambio = Math.min(0, ...cambios);
    const techo = maxTotal * 1.1;
    const piso = minCambio < 0 ? minCambio * 1.1 : 0;
    const x = (i) => serie.length === 1 ? W / 2 :
      M.l + i * (W - M.l - M.r) / (serie.length - 1);
    const y = (v) => M.t + (H - M.t - M.b) * (1 - (v - piso) / (techo - piso));
    const y0 = y(0);
    const paso = (W - M.l - M.r) / Math.max(1, serie.length - 1);
    const anchoBarra = Math.min(44, paso * 0.44);
    const descripcion = altas.map((d, i) => d.familias == null
      ? `${fechaLarga(d.fecha)}: sin captura anterior para calcular nuevas inscripciones`
      : `${fechaLarga(d.fecha)}: ${fmt(d.familias)} familias desde la captura anterior; ` +
        `${fmt(serie[i].familias)} acumuladas`).join(". ");
    const ticks = piso < 0 ? [piso, 0, techo] : [0, techo / 2, techo];

    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" ` +
      `aria-labelledby="rud-chart-title rud-chart-desc">` +
      `<title id="rud-chart-title">Familias registradas en el RUD: total acumulado y nuevas inscripciones</title>` +
      `<desc id="rud-chart-desc">${esc(descripcion)}</desc>`;
    ticks.forEach((v) => {
      const yy = y(v);
      s += `<line x1="${M.l}" x2="${W - M.r}" y1="${yy}" y2="${yy}" ` +
        `stroke="${cssVar("--grid")}"/>` +
        `<text x="${M.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" ` +
        `fill="${cssVar("--muted")}">${fmt(Math.round(v))}</text>`;
    });

    // Las barras van primero para que la curva acumulada permanezca legible encima.
    altas.forEach((d, i) => {
      const valor = d.familias;
      if (valor == null) {
        s += `<text x="${x(i)}" y="${y0 - 7}" text-anchor="middle" font-size="9" ` +
          `fill="${cssVar("--muted")}">sin base</text>`;
        return;
      }
      const yy = y(valor);
      const color = valor < 0 ? cssVar("--critical") : cssVar("--s8");
      const etiqueta = `${valor > 0 ? "+" : ""}${fmt(valor)}`;
      s += `<rect x="${x(i) - anchoBarra / 2}" y="${Math.min(yy, y0)}" ` +
        `width="${anchoBarra}" height="${Math.max(1, Math.abs(y0 - yy))}" rx="2" ` +
        `fill="${color}" fill-opacity="0.28" stroke="${color}" data-altas="${valor}">` +
        `<title>${fechaLarga(d.fecha)}: ${etiqueta} familias desde la captura anterior</title>` +
        `</rect>` +
        `<text x="${x(i)}" y="${valor < 0 ? yy + 13 : yy - 6}" text-anchor="middle" ` +
        `font-size="10" font-weight="600" fill="${color}">${etiqueta}</text>`;
    });

    const linea = serie.map((d, i) =>
      `${i ? "L" : "M"} ${x(i)} ${y(d.familias || 0)}`).join(" ");
    s += `<path d="${linea}" fill="none" stroke="${cssVar("--good")}" ` +
      `stroke-width="2.5"/>`;
    serie.forEach((d, i) => {
      // el punto reconstruido se pinta hueco: no es una captura del endpoint
      const rec = d.reconstruido;
      s += `<circle cx="${x(i)}" cy="${y(d.familias || 0)}" r="5" ` +
        `fill="${rec ? cssVar("--surface-1") : cssVar("--good")}" ` +
        `stroke="${cssVar("--good")}" stroke-width="${rec ? 2.5 : 2}"` +
        `${rec ? ' stroke-dasharray="3 2"' : ""}>` +
        `<title>${fechaLarga(d.fecha)}: ${fmt(d.familias)} familias acumuladas, ` +
        `${fmt(d.municipios)} municipios${rec ? `; punto reconstruido: ${d.origen || ""}` : ""}` +
        `</title></circle>` +
        `<text x="${x(i)}" y="${y(d.familias || 0) - 10}" text-anchor="middle" ` +
        `font-size="11" font-weight="600" fill="${cssVar("--good")}">${fmt(d.familias)}</text>` +
        `<text x="${x(i)}" y="${H - M.b + 16}" text-anchor="middle" font-size="10" ` +
        `fill="${cssVar("--muted")}">${diaMes(d.fecha)}</text>`;
    });

    const leyendaX = M.l;
    s += `<rect x="${leyendaX}" y="7" width="12" height="9" rx="2" ` +
      `fill="${cssVar("--s8")}" fill-opacity="0.28" stroke="${cssVar("--s8")}"/>` +
      `<text x="${leyendaX + 18}" y="15" font-size="10" fill="${cssVar("--ink-2")}">` +
      `Nuevas desde captura anterior</text>` +
      `<line x1="${leyendaX + 207}" x2="${leyendaX + 227}" y1="12" y2="12" ` +
      `stroke="${cssVar("--good")}" stroke-width="2.5"/>` +
      `<circle cx="${leyendaX + 217}" cy="12" r="3.5" fill="${cssVar("--good")}"/>` +
      `<text x="${leyendaX + 234}" y="15" font-size="10" fill="${cssVar("--ink-2")}">` +
      `Total acumulado</text></svg>`;
    return s;
  }

  global.RUD = Object.freeze({ altasDiarias, graficoFamilias });
})(window);

(async function () {
  const { fmt, fechaLarga, fetchJson, tablaHidratada } = window.UI;
  // rud.json: archivo dedicado (serie + detalle municipal completo día a día),
  // pensado para sobrevivir aunque la fuente original desaparezca.
  const rud = await fetchJson("/data/public/rud.json");
  if (!rud || !rud.serie || !rud.serie.length) {
    document.getElementById("rud-nota").textContent =
      "Todavía no hay ninguna captura del registro oficial de damnificados. " +
      "Vuelve a intentarlo en unos minutos.";
    return;
  }
  const serie = rud.serie;

  // ---- acumulado + altas desde la captura anterior (SVG a mano)
  const el = document.getElementById("rud-chart");
  if (el) {
    el.innerHTML = window.RUD.graficoFamilias(serie, el.clientWidth, window.UI);
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
