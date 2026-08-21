/* Balances rastreados: feed público del Worker Cloudflare. Usa ui.js. */
(async function () {
  const { fmt, esc, cssVar: css, fechaEs, fechaLarga, diaMes, fetchJson,
          isLiveblog, bestSnapshot, metricCount } = window.UI;
  // El feed se lee del producto propio, no del worker que lo genera: la corrida
  // diaria lo archiva y lo publica, así que la página sigue funcionando el día
  // que ese worker —que vive en una cuenta ajena— se apague.
  const FEED = "/data/public/oficiales.json";
  const btnJson = document.querySelector(".meta a.btn");
  if (btnJson) btnJson.href = FEED;

  const NOMBRES = { fallecidos: "fallecidos", heridos: "heridos",
                    desaparecidos: "desaparecidos",
                    familias_afectadas: "familias" };
  const NOMBRES_UI = { fallecidos: "Fallecidos", heridos: "Heridos",
                       desaparecidos: "Desaparecidos",
                       familias_afectadas: "Familias afectadas" };

  const feed = await fetchJson(FEED);
  if (!feed) {
    document.getElementById("balance-resumen").textContent =
      "No se han podido cargar los balances: la fuente no respondió. " +
      "Vuelve a intentarlo en unos minutos.";
    return;
  }

  const items = (feed.items || []).filter((x) => x.search_date);
  document.getElementById("generado").textContent =
    "Actualizado el " + fechaLarga(feed.generated_at);

  const dates = [...new Set(items.map((x) => x.search_date))].sort();
  const levels = [...new Set(items.map((x) => x.source_level || "sin_nivel"))].sort();
  const selDate = document.getElementById("balance-fecha");
  const selLevel = document.getElementById("balance-nivel");
  // el valor sigue siendo la fecha ISO (es una clave); lo que se lee, no
  for (const d of dates) selDate.add(new Option(fechaEs(d), d));
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
    const mon = await fetchJson("/data/public/monitor.json");
    const fuentes = window.UI.comparativaFuentes(mon, feedOficiales);
    const por = Object.fromEntries(fuentes.map((f) => [f.id, f]));

    const principal = {
      satelite: (f) => [fmt(f.cifras.edificios_dañados),
                        "edificios con daño clasificado"],
      rud: (f) => [fmt(f.cifras.familias), "familias registradas"],
      medios: (f) => [fmt(f.cifras.familias), "familias afectadas"],
      ciudadano: (f) => [fmt(f.cifras.reportes), "reportes con foto"],
    };
    window.UI.metricCards(cardsEl, fuentes.map((f) => {
      const [valor, unidad] = principal[f.id](f);
      return { label: f.nombre, value: valor,
               sub: `${unidad} · ${f.desglose ? `${f.desglose} · ` : ""}${f.alcance}` +
                    `${f.fecha ? ` · ${fechaEs(f.fecha)}` : ""}`,
               title: f.nota, href: f.href };
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
      el.innerHTML = "<p class='note'>Todavía no hay ninguna captura.</p>";
      return;
    }
    // consolidado: el MÁXIMO informado de cada cifra, con su fecha y su medio
    // de origen. Se rotula «máximo informado» y no «cifra actual» porque una
    // cifra no baja nunca en esta serie, y algunas —los desaparecidos— sí
    // pueden bajar en la realidad cuando aparece gente viva.
    const cc = (k) => {
      const v = (consolidado || {})[k];
      if (!v) return card(NOMBRES_UI[k], "—");
      const partes = [];
      if (v.fecha !== ult.fecha) partes.push(`del ${fechaEs(v.fecha)}`);
      if (v.medio) partes.push(v.medio);
      return card(NOMBRES_UI[k], fmt(v.valor), partes.join(" · ") || null);
    };
    // lo que NO entró en la serie, con su motivo: un balance menor, sin
    // atribución o incoherente sigue siendo información de brecha
    const rechazadas = (ult.ignoradas || []).filter((g) => NOMBRES[g.cifra]);
    const notaRechazadas = rechazadas.length
      ? `<p class="note full">Este día se descartaron ` +
        `${fmt(rechazadas.length)} cifras de la serie: ` +
        rechazadas.slice(0, 4).map((g) =>
          (g.url ? `<a href="${esc(g.url)}" target="_blank" rel="noopener">` : "") +
          `${NOMBRES[g.cifra]} ${fmt(g.valor)}` +
          (g.url ? `</a>` : "") +
          (g.medio ? ` (${esc(g.medio)})` : "") + `, ${esc(g.motivo)}`).join(" · ") +
        (rechazadas.length > 4 ? ` · y ${fmt(rechazadas.length - 4)} más` : "") +
        `. No se borran: se enseñan, porque la distancia entre lo que publica ` +
        `cada medio es justamente lo que este monitor mide.</p>`
      : "";
    // disputa entre medios del día: se muestra, no se suprime — la
    // discrepancia entre fuentes ES información de brecha
    const notaDisputa = disputa
      ? `<p class="note full">⚠️ <strong>Cifras en disputa entre los medios de ` +
        `este día</strong>: ` +
        Object.entries(disputa).map(([k, v]) =>
          `${NOMBRES[k]} entre ${fmt(v.min)} y ${fmt(v.max)}`).join(" · ") +
        `. Se muestra la captura coherente con la serie: un balance acumulado ` +
        `no retrocede, y un medio que llega tarde con un corte viejo no puede ` +
        `hacerla bajar.</p>`
      : "";
    el.innerHTML =
      card("Última fecha", fechaEs(ult.fecha)) +
      cc("fallecidos") + cc("heridos") + cc("desaparecidos") +
      cc("familias_afectadas") +
      card("Capturas", `${fmt(total)} / ${fmt(nDates)} días`) +
      notaDisputa + notaRechazadas +
      // los DOS niveles de atribución de R9: un balance que la prensa cita no
      // se presenta igual que uno que publica la propia entidad. Antes, un
      // ítem oficial salía como «medio que cita fuentes oficiales» y con
      // «fuente citada: —», porque no cita a nadie: es la fuente.
      `<p class="note full">` +
      ((item.reported_data_source || []).length
        ? `Captura elegida en un medio que cita fuentes oficiales: `
        : `Captura elegida, publicada por la propia entidad oficial: `) +
      `<a href="${esc(item.publication_url || item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a> · ` +
      `publica ${esc(publisherName(item))}` +
      ((item.reported_data_source || []).length
        ? ` · fuente citada: ${sourceLinks(item)}. `
        : `. No cita fuente ajena porque es la fuente; aun así no es un EDAN. `) +
      `Cada cifra es <strong>el máximo informado hasta la fecha</strong>, no la ` +
      `última publicada: entra en la serie si supera a la vigente, si se puede ` +
      `atribuir a una fuente oficial y si es coherente con el resto del mismo ` +
      `balance. Cada tarjeta indica, debajo, de qué día y de qué medio sale su ` +
      `cifra, que no tiene por qué ser el de la captura elegida. Puede ir por ` +
      `detrás de la realidad, y los desaparecidos pueden bajar en la realidad ` +
      `sin bajar aquí: por eso se llama máximo informado.</p>`;
  }


  function card(label, value, sub) {
    return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong>` +
      (sub ? `<small>${esc(sub)}</small>` : "") + `</div>`;
  }

  function renderChart(rows, porDia) {
    const el = document.getElementById("balance-chart");
    if (!rows.length) { el.textContent = "Todavía no hay serie que dibujar."; return; }
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
        p.metrics.map(([k]) => consDe(r.search_date, k)?.valor ?? 0)));
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
        // La línea ARRANCA en el primer día con valor, no en el eje: antes,
        // los días anteriores al primer dato se dibujaban con `|| 0` y una
        // ausencia parecía un cero medido. Es la R3 en el gráfico, y la misma
        // lección que los globos del mapa sin cifras.
        const d = rows.map((r, i) => {
          const v = consDe(r.search_date, key)?.valor;
          return v == null ? null : `${x(i)} ${y(v)}`;
        }).filter(Boolean)
          .map((punto, i) => `${i ? "L" : "M"} ${punto}`).join(" ");
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
        svg += `<text x="${x(i)}" y="${H - M.b + 16}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${diaMes(r.search_date)}</text>`
      );
      svg += "</svg>";
      html += svg;
    }
    el.innerHTML = html;

    window.UI.attachTooltip(el, (dot) => {
      if (dot.dataset.i == null) return null;
      const r = rows[+dot.dataset.i];
      const c = r.cifras || {};
      return `<strong>${fechaLarga(r.search_date)}</strong><br>${esc(publisherName(r))}${isLiveblog(r) ? " · cobertura en vivo" : ""}<br>` +
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
      `${fmt(selected.length)} de ${fmt(items.length)} capturas · ` +
      `actualizado el ${fechaLarga(feed.generated_at)}`;

    // filas cuyas cifras alimentan la serie/tarjetas: el snapshot elegido de
    // cada día — marcadas para que la selección sea auditable a simple vista
    const elegidos = new Set(porDia.map((d) => d.item).filter(Boolean));
    // Las filas las escribe el build: aquí solo se muestran las que pasan los
    // filtros y se marca la elegida de cada día. Qué snapshot representa a su
    // día se decide comparando con la víspera (R8), así que esa marca —y solo
    // esa— sigue siendo cosa del navegador.
    const tbody = document.querySelector("#balance-table tbody");
    const porUrl = new Map(Array.from(tbody.rows)
      .filter((tr) => tr.dataset.url)
      .map((tr) => [tr.dataset.url, tr]));
    const visibles = new Set(selected.map((it) => it.publication_url || it.url || "#"));
    porUrl.forEach((tr, url) => {
      tr.hidden = !visibles.has(url);
      const item = selected.find((it) => (it.publication_url || it.url || "#") === url);
      const usado = item && elegidos.has(item);
      tr.style.background = usado
        ? "color-mix(in srgb, var(--good) 7%, transparent)" : "";
      const celda = tr.cells[1];
      const yaMarcada = celda.querySelector("[data-serie]");
      if (usado && !yaMarcada) {
        const b = document.createElement("span");
        b.className = "badge";
        b.dataset.serie = "1";
        b.style.setProperty("--bc", "var(--good)");
        b.title = "Esta captura es la elegida de su día: sus cifras alimentan la " +
          "serie, las tarjetas y la comparativa";
        b.textContent = "✓ usada en la serie";
        celda.insertBefore(b, celda.querySelector(".badge"));
        celda.insertBefore(document.createTextNode(" "), b.nextSibling);
      } else if (!usado && yaMarcada) {
        yaMarcada.remove();
      }
    });
  }

  function levelColor(level) {
    if (level === "oficial_institucional" || level === "oficial_comunicacion") return css("--good");
    if (level === "temporal_prensa") return css("--s1");
    if (level === "gobierno_local_por_verificar") return css("--warning");
    return css("--muted");
  }
})();
