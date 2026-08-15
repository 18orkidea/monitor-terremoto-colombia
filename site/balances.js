/* Balances rastreados: feed público del Worker Cloudflare. */
(async function () {
  const FEED = "https://monitor-terremoto-colombia-oficiales-ai.inforesidencias.workers.dev/oficiales.json";
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (n) => n == null ? "—" : Number(n).toLocaleString("es-CO", { maximumFractionDigits: 0 });
  const esc = (s) => String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));

  async function getJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  let feed;
  try {
    feed = await getJson(FEED);
  } catch (err) {
    document.getElementById("balance-resumen").textContent =
      `No se pudo cargar el feed de balances: ${err.message || err}`;
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

  const best = dates.map((date) => bestSnapshot(items.filter((x) => x.search_date === date)));
  renderCards(best.at(-1), items.length, dates.length);
  renderChart(best);
  renderTable();

  document.getElementById("balance-buscar").addEventListener("input", renderTable);
  selDate.addEventListener("change", renderTable);
  selLevel.addEventListener("change", renderTable);

  function metricCount(item) {
    return Object.values(item.cifras || {}).filter((v) => v != null).length;
  }

  function sourceScore(item) {
    if (item.official && item.source_level === "oficial_institucional") return 4;
    if (item.official) return 3;
    if ((item.reported_data_source || []).length) return 2;
    return 0;
  }

  function isLiveblog(item) {
    const text = `${item.title || ""} ${item.publication_url || item.url || ""}`.toLowerCase();
    return item.is_liveblog || /en vivo|directo|live[-_\s]?news|última hora|ultima hora|minuto a minuto|liveblog/.test(text);
  }

  function bestSnapshot(dayItems) {
    return [...dayItems].sort((a, b) =>
      Number(isLiveblog(a)) - Number(isLiveblog(b)) ||
      metricCount(b) - metricCount(a) ||
      sourceScore(b) - sourceScore(a) ||
      ((b.captured_at || "").localeCompare(a.captured_at || "")))[0];
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

  function renderCards(item, total, nDates) {
    const el = document.getElementById("balance-cards");
    if (!item) {
      el.innerHTML = "<p class='note'>Sin snapshots.</p>";
      return;
    }
    const c = item.cifras || {};
    el.innerHTML =
      card("Última fecha", item.search_date) +
      card("Fallecidos", fmt(c.fallecidos)) +
      card("Heridos", fmt(c.heridos)) +
      card("Desaparecidos", fmt(c.desaparecidos)) +
      card("Familias afectadas", fmt(c.familias_afectadas)) +
      card("Snapshots", `${fmt(total)} / ${fmt(nDates)} días`) +
      `<p class="note full">Snapshot seleccionado en medio que cita fuentes oficiales: <a href="${esc(item.publication_url || item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a> · ` +
      `publica ${esc(publisherName(item))} · fuente citada: ${sourceLinks(item)}.</p>`;
  }

  function card(label, value) {
    return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function renderChart(rows) {
    const el = document.getElementById("balance-chart");
    if (!rows.length) { el.textContent = "Sin serie."; return; }
    const W = Math.max(760, Math.min(el.clientWidth || 980, 1160));
    const H = 310;
    const M = { t: 22, r: 18, b: 44, l: 58 };
    const metrics = [
      ["fallecidos", "Fallecidos", css("--critical")],
      ["heridos", "Heridos", css("--s2")],
      ["desaparecidos", "Desaparecidos", css("--warning")],
      ["familias_afectadas", "Familias", css("--s1")]
    ];
    const maxY = Math.max(1, ...rows.flatMap((r) => metrics.map(([k]) => r.cifras?.[k] || 0)));
    const x = (i) => M.l + (i + 0.5) * (W - M.l - M.r) / rows.length;
    const y = (v) => M.t + (H - M.t - M.b) * (1 - v / maxY);
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Evolución de balances">`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      const v = Math.round(maxY * t), yy = y(v);
      svg += `<line x1="${M.l}" x2="${W - M.r}" y1="${yy}" y2="${yy}" stroke="${css("--grid")}" />` +
        `<text x="${M.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${fmt(v)}</text>`;
    }
    metrics.forEach(([key, label, color], mi) => {
      const d = rows.map((r, i) => `${i ? "L" : "M"} ${x(i)} ${y(r.cifras?.[key] || 0)}`).join(" ");
      svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.2" />`;
      rows.forEach((r, i) => {
        const val = r.cifras?.[key];
        if (val != null) svg += `<circle data-i="${i}" data-k="${key}" cx="${x(i)}" cy="${y(val)}" r="4" fill="${color}" stroke="${css("--surface-1")}" stroke-width="2" />`;
      });
      svg += `<circle cx="${M.l + mi * 148}" cy="9" r="5" fill="${color}" />` +
        `<text x="${M.l + 10 + mi * 148}" y="13" fill="${css("--ink-2")}" font-size="11">${label}</text>`;
    });
    rows.forEach((r, i) =>
      svg += `<text x="${x(i)}" y="${H - M.b + 16}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${r.search_date.slice(5)}</text>`
    );
    svg += "</svg>";
    el.innerHTML = svg;

    const tip = document.createElement("div");
    tip.className = "tooltip"; tip.style.display = "none";
    document.body.appendChild(tip);
    el.addEventListener("mousemove", (ev) => {
      const dot = ev.target.closest("[data-i]");
      if (!dot) { tip.style.display = "none"; return; }
      const r = rows[+dot.dataset.i];
      const c = r.cifras || {};
      tip.innerHTML = `<strong>${r.search_date}</strong><br>${esc(publisherName(r))}${isLiveblog(r) ? " · liveblog" : ""}<br>` +
        `Fallecidos: ${fmt(c.fallecidos)} · Heridos: ${fmt(c.heridos)}<br>` +
        `Desaparecidos: ${fmt(c.desaparecidos)} · Familias: ${fmt(c.familias_afectadas)}`;
      tip.style.display = "block";
      tip.style.left = (ev.clientX + 12) + "px";
      tip.style.top = (ev.clientY - 10) + "px";
    });
    el.addEventListener("mouseleave", () => tip.style.display = "none");
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
