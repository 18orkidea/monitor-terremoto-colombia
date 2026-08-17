/* Balances rastreados: feed público del Worker Cloudflare. Usa ui.js. */
(async function () {
  const { fmt, esc, cssVar: css, fetchJson, isLiveblog, bestSnapshot,
          metricCount } = window.UI;
  const FEED = `${window.UI.OFICIALES_BASE}/oficiales.json`;
  const btnJson = document.querySelector(".meta a.btn");
  if (btnJson) btnJson.href = FEED;

  const feed = await fetchJson(FEED);
  if (!feed) {
    document.getElementById("balance-resumen").textContent =
      "No se pudo cargar el feed de balances (el worker no respondió).";
    return;
  }

  const items = (feed.items || []).filter((x) => x.search_date);
  document.getElementById("generado").textContent = "Actualizado " + (feed.generated_at || "—");

  const dates = [...new Set(items.map((x) => x.search_date))].sort();
  const levels = [...new Set(items.map((x) => x.source_level || "sin_nivel"))].sort();
  const selDate = document.getElementById("balance-fecha");
  const selLevel = document.getElementById("balance-nivel");
  for (const d of dates) selDate.add(new Option(d, d));
  for (const l of levels) selLevel.add(new Option(labelLevel(l), l));

  // serie con memoria: cada día se elige con el anterior como referencia de
  // estabilidad (un acumulado no retrocede), se detectan las disputas y el
  // consolidado conserva el último valor conocido de cada cifra
  const porDia = window.UI.mejorPorDia(items);
  const best = porDia.map((d) => d.item);
  renderCards(porDia.at(-1), items.length, dates.length);
  renderChart(best, porDia);
  renderTable();
  renderComparativa(feed);

  document.getElementById("balance-buscar").addEventListener("input", renderTable);
  selDate.addEventListener("change", renderTable);
  selLevel.addEventListener("change", renderTable);

  /* Comparativa de fuentes: tarjetas (una por mirada) + tabla RUD vs medios.
     Los datos del RUD/satélite/ciudadano vienen de monitor.json. */
  async function renderComparativa(feedOficiales) {
    const cardsEl = document.getElementById("comparativa-cards");
    const tbody = document.querySelector("#comparativa-tabla tbody");
    if (!cardsEl || !tbody) return;
    const mon = await fetchJson("../data/public/monitor.json");
    const fuentes = window.UI.comparativaFuentes(mon, feedOficiales);
    const por = Object.fromEntries(fuentes.map((f) => [f.id, f]));

    const principal = {
      satelite: (f) => [fmt(f.cifras.edificios_dañados), "edificios dañados"],
      rud: (f) => [fmt(f.cifras.familias), "familias registradas"],
      medios: (f) => [fmt(f.cifras.familias), "familias afectadas"],
      ciudadano: (f) => [fmt(f.cifras.reportes), "reportes con foto"],
    };
    window.UI.metricCards(cardsEl, fuentes.map((f) => {
      const [valor, unidad] = principal[f.id](f);
      return { label: f.nombre, value: valor,
               sub: `${unidad} · ${f.alcance}${f.fecha ? ` · ${f.fecha}` : ""}`,
               href: f.href };
    }));

    const rud = por.rud && por.rud.cifras || {};
    const med = por.medios && por.medios.cifras || {};
    const filas = [
      ["Municipios afectados", rud.municipios, med.municipios],
      ["Familias", rud.familias, med.familias],
      ["Personas", rud.personas, med.personas],
      ["Viviendas destruidas", rud.viv_destruidas, med.viv_destruidas],
      ["Viviendas averiadas", rud.viv_averiadas, med.viv_averiadas],
      ["Fallecidos", null, med.fallecidos],
      ["Heridos", null, med.heridos],
      ["Desaparecidos", null, med.desaparecidos],
    ];
    tbody.innerHTML = filas.map(([nombre, r, m]) => {
      const diff = (r != null && m != null) ? Math.abs(m - r) : null;
      return `<tr><td>${nombre}</td>` +
        `<td class="num">${r == null ? '<span style="color:var(--muted)" title="El RUD no registra este indicador">no registra</span>' : fmt(r)}</td>` +
        `<td class="num">${fmt(m)}</td>` +
        `<td class="num">${diff == null ? "—" : fmt(diff)}</td></tr>`;
    }).join("");
  }

  function labelLevel(level) {
    return {
      oficial_comunicacion: "Oficial comunicación",
      oficial_institucional: "Oficial institucional",
      gobierno_local_por_verificar: "Gobierno local por verificar",
      temporal_prensa: "Prensa temporal",
      busqueda_web_temporal: "Web temporal"
    }[level] || level || "Sin nivel";
  }

  function sourceLinks(item) {
    return (item.reported_data_source || []).map((s) =>
      s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.id)}</a>` : esc(s.id)
    ).join(", ") || "—";
  }

  function publisherName(item) {
    const p = item.publisher || {};
    return p.name || p.domain || "—";
  }

  function renderCards(ult, total, nDates) {
    const { item, disputa, consolidado } = ult || {};
    const el = document.getElementById("balance-cards");
    if (!item) {
      el.innerHTML = "<p class='note'>Sin snapshots.</p>";
      return;
    }
    // consolidado: el último valor conocido de cada cifra, con su fecha de
    // origen marcada cuando no es del propio día — un dato no desaparece
    // porque el snapshot del día no lo traiga
    const cc = (k) => {
      const v = (consolidado || {})[k];
      if (!v) return card(NOMBRES_UI[k], "—");
      const origen = v.fecha !== ult.fecha ? `del ${v.fecha.slice(5)}` : null;
      return card(NOMBRES_UI[k], fmt(v.valor), origen);
    };
    // disputa entre medios del día: se muestra, no se suprime — la
    // discrepancia entre fuentes ES información de brecha
    const notaDisputa = disputa
      ? `<p class="note full">⚠️ <strong>Cifras en disputa entre los medios de ` +
        `este día</strong>: ` +
        Object.entries(disputa).map(([k, v]) =>
          `${NOMBRES[k]} entre ${fmt(v.min)} y ${fmt(v.max)}`).join(" · ") +
        `. Se muestra el snapshot coherente con la serie (un balance acumulado ` +
        `no retrocede); los medios tardíos con cortes viejos se penalizan.</p>`
      : "";
    el.innerHTML =
      card("Última fecha", ult.fecha) +
      cc("fallecidos") + cc("heridos") + cc("desaparecidos") +
      cc("familias_afectadas") +
      card("Snapshots", `${fmt(total)} / ${fmt(nDates)} días`) +
      notaDisputa +
      `<p class="note full">Snapshot seleccionado en medio que cita fuentes oficiales: <a href="${esc(item.publication_url || item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a> · ` +
      `publica ${esc(publisherName(item))} · fuente citada: ${sourceLinks(item)}. ` +
      `Las cifras marcadas «del MM-DD» conservan el último valor conocido cuando ` +
      `el snapshot del día no las trae.</p>`;
  }

  const NOMBRES = { fallecidos: "fallecidos", heridos: "heridos",
                    desaparecidos: "desaparecidos",
                    familias_afectadas: "familias" };
  const NOMBRES_UI = { fallecidos: "Fallecidos", heridos: "Heridos",
                       desaparecidos: "Desaparecidos",
                       familias_afectadas: "Familias afectadas" };

  function card(label, value, sub) {
    return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong>` +
      (sub ? `<small>${esc(sub)}</small>` : "") + `</div>`;
  }

  function renderChart(rows, porDia) {
    const el = document.getElementById("balance-chart");
    if (!rows.length) { el.textContent = "Sin serie."; return; }
    const disputaDe = (fecha) =>
      (porDia || []).find((d) => d.fecha === fecha)?.disputa || null;
    // consolidado del día: {valor, fecha de origen} — la línea no cae a cero
    // cuando el snapshot del día no trae una cifra
    const consDe = (fecha, k) =>
      (porDia || []).find((d) => d.fecha === fecha)?.consolidado[k] || null;
    const W = Math.max(760, Math.min(el.clientWidth || 980, 1160));
    const M = { t: 24, r: 18, b: 40, l: 58 };
    // paneles con escala propia: mezclar familias (~54.000) con fallecidos
    // (~300) en un solo eje aplasta la serie que más importa
    const paneles = [
      // fallecidos y desaparecidos comparten magnitud (~300): emparejados se
      // comparan entre sí, que es la lectura que importa
      { titulo: "Fallecidos y desaparecidos", alto: 200, metrics: [
        ["fallecidos", "Fallecidos", css("--critical")],
        ["desaparecidos", "Desaparecidos", css("--warning")],
      ]},
      { titulo: "Heridos", alto: 150, metrics: [
        ["heridos", "Heridos", css("--s2")],
      ]},
      { titulo: "Familias afectadas", alto: 150, metrics: [
        ["familias_afectadas", "Familias", css("--s1")],
      ]},
    ];
    const x = (i) => M.l + (i + 0.5) * (W - M.l - M.r) / rows.length;
    let html = "";
    for (const p of paneles) {
      const H = p.alto;
      const maxY = Math.max(1, ...rows.flatMap((r) =>
        p.metrics.map(([k]) => consDe(r.search_date, k)?.valor || 0)));
      const y = (v) => M.t + (H - M.t - M.b) * (1 - v / maxY);
      let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${p.titulo} por día">`;
      // banda ámbar en los días con cifras en disputa entre medios
      rows.forEach((r, i) => {
        if (disputaDe(r.search_date)) {
          const bw2 = (W - M.l - M.r) / rows.length;
          svg += `<rect x="${x(i) - bw2 / 2}" y="${M.t}" width="${bw2}" height="${H - M.t - M.b}" fill="${css("--warning")}" opacity="0.10"/>`;
        }
      });
      for (const t of [0, 0.5, 1]) {
        const v = Math.round(maxY * t), yy = y(v);
        svg += `<line x1="${M.l}" x2="${W - M.r}" y1="${yy}" y2="${yy}" stroke="${css("--grid")}" />` +
          `<text x="${M.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${fmt(v)}</text>`;
      }
      p.metrics.forEach(([key, label, color], mi) => {
        const d = rows.map((r, i) =>
          `${i ? "L" : "M"} ${x(i)} ${y(consDe(r.search_date, key)?.valor || 0)}`).join(" ");
        svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.2" />`;
        rows.forEach((r, i) => {
          const cv = consDe(r.search_date, key);
          if (!cv) return;
          // punto sólido solo si el dato es fresco de ese día; el valor
          // arrastrado mantiene la línea sin fingir un reporte nuevo
          if (cv.fecha === r.search_date) {
            svg += `<circle data-i="${i}" data-k="${key}" cx="${x(i)}" cy="${y(cv.valor)}" r="4" fill="${color}" stroke="${css("--surface-1")}" stroke-width="2" />`;
          }
        });
        // etiqueta directa sobre el último valor: se lee sin ir a la leyenda
        const last = rows[rows.length - 1];
        const lv = consDe(last.search_date, key)?.valor;
        if (lv != null) svg += `<text x="${W - M.r - 2}" y="${Math.max(12, y(lv) - 7)}" text-anchor="end" font-size="10" font-weight="600" fill="${color}">${fmt(lv)}</text>`;
        svg += `<circle cx="${M.l + mi * 148}" cy="9" r="5" fill="${color}" />` +
          `<text x="${M.l + 10 + mi * 148}" y="13" fill="${css("--ink-2")}" font-size="11">${label}</text>`;
      });
      rows.forEach((r, i) =>
        svg += `<text x="${x(i)}" y="${H - M.b + 16}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${r.search_date.slice(5)}</text>`
      );
      svg += "</svg>";
      html += svg;
    }
    el.innerHTML = html;

    window.UI.attachTooltip(el, (dot) => {
      if (dot.dataset.i == null) return null;
      const r = rows[+dot.dataset.i];
      const c = r.cifras || {};
      return `<strong>${r.search_date}</strong><br>${esc(publisherName(r))}${isLiveblog(r) ? " · liveblog" : ""}<br>` +
        `Fallecidos: ${fmt(c.fallecidos)} · Heridos: ${fmt(c.heridos)}<br>` +
        `Desaparecidos: ${fmt(c.desaparecidos)} · Familias: ${fmt(c.familias_afectadas)}` +
        (disputaDe(r.search_date)
          ? `<br>⚠️ Cifras en disputa entre medios este día` : "");
    });
  }

  function renderTable() {
    const q = document.getElementById("balance-buscar").value.toLowerCase();
    const fd = selDate.value;
    const fl = selLevel.value;
    const selected = items.filter((item) => {
      const text = [
        item.title, item.source_level, publisherName(item),
        ...(item.reported_data_source || []).map((s) => `${s.id} ${s.name}`)
      ].join(" ").toLowerCase();
      return (!q || text.includes(q)) &&
        (!fd || item.search_date === fd) &&
        (!fl || item.source_level === fl);
    }).sort((a, b) =>
      (b.search_date || "").localeCompare(a.search_date || "") ||
      metricCount(b) - metricCount(a));

    document.getElementById("balance-resumen").textContent =
      `${selected.length.toLocaleString("es-CO")} de ${items.length.toLocaleString("es-CO")} snapshots · actualizado ${feed.generated_at || "—"}`;

    document.querySelector("#balance-table tbody").innerHTML = selected.map((item) => {
      const c = item.cifras || {};
      const pub = item.publisher || {};
      const viviendas = [c.viviendas_averiadas, c.viviendas_destruidas]
        .filter((v) => v != null).map(fmt).join(" / ") || "—";
      return `<tr>` +
        `<td>${esc(item.search_date)}</td>` +
        `<td><strong>${esc(publisherName(item))}</strong><br>` +
        `<span class="badge" style="--bc:${levelColor(item.source_level)}">${esc(labelLevel(item.source_level))}</span> ` +
        `${isLiveblog(item) ? `<span class="badge" style="--bc:${css("--warning")}">liveblog</span> ` : ""}` +
        `<span class="note">${sourceLinks(item)}</span></td>` +
        `<td class="num">${fmt(c.fallecidos)}</td>` +
        `<td class="num">${fmt(c.heridos)}</td>` +
        `<td class="num">${fmt(c.desaparecidos)}</td>` +
        `<td class="num">${fmt(c.familias_afectadas)}</td>` +
        `<td class="num">${fmt(c.personas_afectadas)}</td>` +
        `<td class="num" title="Averiadas / destruidas">${viviendas}</td>` +
        `<td><a href="${esc(item.publication_url || item.url)}" target="_blank" rel="noopener">publicación</a>` +
        `${pub.url && pub.url !== (item.publication_url || item.url) ? ` · <a href="${esc(pub.url)}" target="_blank" rel="noopener">canal</a>` : ""}` +
        `<br><span class="note">${esc((item.title || "").slice(0, 90))}</span></td>` +
        `</tr>`;
    }).join("") || "<tr><td colspan='9'>Nada que mostrar con estos filtros.</td></tr>";
  }

  function levelColor(level) {
    if (level === "oficial_institucional" || level === "oficial_comunicacion") return css("--good");
    if (level === "temporal_prensa") return css("--s1");
    if (level === "gobierno_local_por_verificar") return css("--warning");
    return css("--muted");
  }
})();
