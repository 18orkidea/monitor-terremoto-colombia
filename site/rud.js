/* Página del RUD: curva diaria de familias registradas + tabla municipal
   completa con buscador (ordenada por personas). Usa los componentes de ui.js. */
(async function () {
  const { fmt, pct, fechaEs, fetchJson, tablaBuscable, cssVar } = window.UI;
  // rud.json: archivo dedicado (serie + detalle municipal completo día a día),
  // pensado para sobrevivir aunque la fuente original desaparezca.
  const rud = await fetchJson("../data/public/rud.json");
  if (!rud || !rud.serie || !rud.serie.length) {
    document.getElementById("rud-nota").textContent =
      "Sin datos del RUD todavía: ejecuta primero python ingest/run_daily.py.";
    return;
  }
  document.getElementById("generado").textContent = "Actualizado " + rud.generado;
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
      s += `<circle cx="${x(i)}" cy="${y(d.familias || 0)}" r="5" fill="${rec ? cssVar("--surface-1") : cssVar("--good")}" stroke="${cssVar("--good")}" stroke-width="${rec ? 2.5 : 2}"${rec ? ' stroke-dasharray="3 2"' : ""}><title>${d.fecha}: ${fmt(d.familias)} familias, ${fmt(d.municipios)} municipios${rec ? ` — punto reconstruido: ${d.origen || ""}` : ""}</title></circle>` +
        `<text x="${x(i)}" y="${y(d.familias || 0) - 10}" text-anchor="middle" font-size="11" font-weight="600" fill="${cssVar("--good")}">${fmt(d.familias)}</text>` +
        `<text x="${x(i)}" y="${H - M.b + 14}" text-anchor="middle" font-size="10" fill="${cssVar("--muted")}">${d.fecha.slice(5)}</text>`;
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
  tablaBuscable({
    tbody: document.querySelector("#rud-tabla tbody"),
    input: buscar,
    rows: munis,
    paginado: document.getElementById("paginado"),
    porPagina: TOP,
    texto: (m) => `${m.municipio} ${m.departamento}`,
    fila: (m) =>
      `<tr><td><strong>${m.municipio}</strong>${m.nuevo ? ' <span class="badge" style="--bc:var(--good)">nuevo</span>' : ""}<br><span style="color:var(--muted)">${m.departamento}</span></td>` +
      `<td class="num">${fmt(m.familias)}</td><td class="num">${fmt(m.personas)}</td>` +
      `<td class="num">${m.poblacion_2026 == null ? "—" : fmt(m.poblacion_2026)}</td>` +
      `<td class="num">${pct(m.tasa_pct)}</td>` +
      `<td class="num">${fmt(m.viv_destruidas)}</td><td class="num">${fmt(m.viv_averiadas)}</td>` +
      `<td class="num">${m.delta_familias == null ? "—" : (m.delta_familias >= 0 ? "+" : "") + fmt(m.delta_familias)}</td></tr>`,
    nota: document.getElementById("rud-nota"),
    notaTexto: (q, visibles, total) => (q
      ? `${visibles} de ${total} municipios registrados coinciden con la búsqueda. `
      : `${total} municipios registrados (${fmt(ult.familias)} familias en total), ` +
        `ordenados por personas damnificadas, de ${TOP} en ${TOP}. `) +
      `La columna Δ compara con el día anterior de la serie; «nuevo» marca municipios que ` +
      `entraron al registro hoy. Serie iniciada el ${fechaEs(serie[0].fecha)}.` +
      (serie.some((d) => d.reconstruido)
        ? ` Los puntos huecos de la curva no son capturas del RUD: se reconstruyeron ` +
          `desde otra evidencia archivada porque ese día se perdió la corrida, y de ` +
          `ellos solo se conoce el total, no el detalle municipal.`
        : ""),
    vacio: `Sin coincidencias entre los municipios registrados. Que un municipio no ` +
      `aparezca significa «sin registro aún», no «sin daño».`,
  });
})();
