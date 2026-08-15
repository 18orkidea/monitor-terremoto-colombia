/* Monitor de brechas — frontend sin build. Lee data/public/*. */
(async function () {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const ESTADO_COLOR = {
    coincide: css("--good"), prensa: css("--s1"), ciudadano: css("--s7"),
    pendiente: css("--warning"), no_comparable: css("--muted"),
  };
  const fmt = (n) => n == null ? "—" :
    Number(n).toLocaleString("es-CO", { maximumFractionDigits: 1 });

  async function j(path) {
    try { const r = await fetch(path); return r.ok ? await r.json() : null; }
    catch { return null; }
  }
  const base = "../data/public/";
  const [mon, aois, chat, dyfi, sismos, shake, alerts] = await Promise.all([
    j(base + "monitor.json"), j(base + "aois.geojson"), j(base + "chatmap.geojson"),
    j(base + "dyfi_cells.geojson"), j(base + "ungrd_sismos.geojson"),
    j(base + "shakemap_mmi.geojson"), j(base + "alerts.json"),
  ]);
  if (!mon) {
    document.getElementById("banner-brechas").textContent =
      "Sin datos: ejecuta primero `python ingest/run_daily.py` (o sirve el repo con `python -m http.server`).";
    return;
  }
  document.getElementById("generado").textContent = "Actualizado " + mon.generado;

  // ---- banda de brechas oficiales
  const g = mon.brechas_oficiales || {};
  const soc = g.ungrd_socrata || {}, arc = g.ungrd_arcgis || {};
  const dias = (d) => d ? Math.round((Date.now() - new Date(d)) / 864e5) : null;
  document.getElementById("banner-brechas").innerHTML =
    `<strong>Brecha de reporte oficial:</strong> UNGRD en datos.gov.co llega hasta ` +
    `<strong>${(soc.hasta || "?").slice(0, 10)}</strong> (hace ${fmt(dias(soc.hasta))} días); ` +
    `el registro ArcGIS de UNGRD hasta <strong>${arc.max_fecha || "?"}</strong> ` +
    `(hace ${fmt(dias(arc.max_fecha))} días). El SNIGRD (2026) no expone API pública. ` +
    `Mientras tanto, Copernicus entregó ${mon.entregas.length} productos y la comunidad ` +
    `aportó ${mon.citizen.chatmap_total} reportes con foto.` +
    (mon.exposicion ? `<br><strong>Exposición sin mapeo:</strong> ~${fmt(mon.exposicion.expuesta_mmi6plus)} ` +
      `personas expuestas a MMI≥6 (PAGER); las zonas mapeadas por Copernicus cubren ` +
      `~${fmt(mon.exposicion.en_aois_copernicus)} (${mon.exposicion.pct_cubierta} %). ` +
      `El resto es población que nadie ha mirado de cerca.` : "");

  // ---- mapa
  const map = L.map("map");
  window.__monitorMap = map;   // depuración y extensiones
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "© OpenStreetMap", maxZoom: 18 }).addTo(map);

  const layers = {};
  if (shake) {
    layers["Intensidad ShakeMap"] = L.geoJSON(shake, {
      style: (f) => ({ color: "#8a5a00", weight: 1, opacity: 0.5, dashArray: "4 3" }),
      onEachFeature: (f, l) => l.bindTooltip("MMI " + (f.properties.value ?? "")),
    }).addTo(map);
  }
  const aoiLayerById = {};
  if (aois) {
    layers["Zonas Copernicus (AOI)"] = L.geoJSON(aois, {
      style: (f) => ({
        color: ESTADO_COLOR[f.properties.estado] || css("--muted"),
        weight: 2, fillOpacity: 0.12,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        aoiLayerById[p.aoi] = l;
        l.bindPopup(`<strong>${p.aoi}</strong><br>${p.etiqueta}<br>` +
          `Población: ${fmt(p.poblacion)} · Edificios afectados: ${fmt(p.edificios_afectados)}<br>` +
          `Vías: ${fmt(p.vias_afectadas_km)} km · Interrupciones: ${fmt(p.interrupciones_viales)}`);
      },
    }).addTo(map);
    map.fitBounds(layers["Zonas Copernicus (AOI)"].getBounds().pad(0.15));
  } else { map.setView([4.5, -76.3], 8); }

  if (mon.evento && mon.evento.coordinates) {
    const [elon, elat] = mon.evento.coordinates;
    L.marker([elat, elon], {
      icon: L.divIcon({
        className: "", iconSize: [26, 26], iconAnchor: [13, 13],
        html: `<div style="font-size:22px;line-height:26px;text-align:center;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))">★</div>`,
      }),
    }).addTo(map).bindPopup(
      `<strong>Epicentro M${mon.evento.mag}</strong><br>${mon.evento.place}<br>` +
      `${fmt(mon.evento.felt)} reportes «lo sentí» (USGS DYFI)`);
  }
  if (chat) {
    layers[`Reportes ciudadanos ChatMap (${chat.features.length})`] = L.geoJSON(chat, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: 5, color: css("--s2"), weight: 1.5,
        fillColor: css("--s2"), fillOpacity: 0.55,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        const media = p.media && /\.(jpg|jpeg|png|webp)$/i.test(p.media)
          ? `<a href="${p.media}" target="_blank" rel="noopener"><img src="${p.media}" loading="lazy" alt="foto ciudadana"></a>`
          : (p.media ? `<a href="${p.media}" target="_blank" rel="noopener">ver medio</a>` : "");
        l.bindPopup(`<strong>Reporte ciudadano</strong> · ${p.time || ""}<br>` +
          `${p.aoi ? "Dentro de AOI: " + p.aoi + "<br>" : ""}` +
          `${p.mmi != null ? "MMI estimado: " + fmt(p.mmi) + "<br>" : ""}` +
          `${(p.mensaje || "")}<br>${media}` +
          `<br><span style="color:var(--muted)">coordenada redondeada ~110 m · score ${p.score ?? "?"}</span>`);
      },
    }).addTo(map);
  }
  if (dyfi) {
    layers["Intensidad percibida DYFI"] = L.geoJSON(dyfi, {
      style: (f) => {
        const c = f.properties.cdi || 0;
        const op = Math.min(0.65, 0.08 + c * 0.07);
        return { color: css("--s1"), weight: 0.5, fillColor: css("--s1"), fillOpacity: op };
      },
      onEachFeature: (f, l) => l.bindTooltip(
        `CDI ${f.properties.cdi} · ${f.properties.nresp} respuestas`),
    });
  }
  if (sismos) {
    layers[`Sismos históricos UNGRD (${sismos.features.length})`] = L.geoJSON(sismos, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: 3, color: css("--muted"), weight: 1, fillOpacity: 0.4,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindTooltip(`${p.fecha ?? "?"} · ${p.municipio ?? ""} (${p.departamento ?? ""})`);
      },
    });
  }
  L.control.layers(null, layers, { collapsed: true }).addTo(map);

  // el grid asienta su tamaño tarde: reencuadrar cuando el contenedor cambie
  const aoiBounds = layers["Zonas Copernicus (AOI)"] &&
    layers["Zonas Copernicus (AOI)"].getBounds();
  let lastW = map.getSize().x;
  new ResizeObserver(() => {
    const w = document.getElementById("map").clientWidth;
    if (Math.abs(w - lastW) > 4) {
      lastW = w;
      map.invalidateSize();
      if (aoiBounds && aoiBounds.isValid()) map.fitBounds(aoiBounds.pad(0.15));
    }
  }).observe(document.getElementById("map"));

  // ---- tabla
  const tbody = document.querySelector("#tabla tbody");
  for (const a of mon.aois) {
    const tr = document.createElement("tr");
    const c = a.cruce || {};
    tr.innerHTML =
      `<td><strong>${a.aoi}</strong></td>` +
      `<td><span class="badge" style="--bc:${ESTADO_COLOR[c.estado] || css("--muted")}">${c.etiqueta || c.estado}</span></td>` +
      `<td class="num">${fmt(a.resumen.poblacion)}</td>` +
      `<td class="num">${fmt(a.resumen.edificios_afectados)}</td>` +
      `<td class="num">${fmt(a.resumen.vias_afectadas_km)}</td>` +
      `<td class="num">${fmt(c.n_prensa)}</td>` +
      `<td class="num">${fmt(c.n_ciudadano)}</td>` +
      `<td>${(a.producto.entrega || "—").slice(0, 10)} <span style="color:var(--muted)">${a.producto.tipo} v${a.producto.version}${a.producto.status !== "F" ? " · " + ({ W: "en espera", I: "en producción", N: "no producido" }[a.producto.status] || a.producto.status) : ""}</span></td>`;
    tr.addEventListener("click", () => {
      const l = aoiLayerById[a.aoi];
      if (l) { map.fitBounds(l.getBounds().pad(0.3)); l.openPopup(); }
    });
    tbody.appendChild(tr);
  }
  document.getElementById("leyenda").innerHTML = Object.entries({
    coincide: "Coincide (evidencia oficial)", prensa: "Reportado en prensa",
    ciudadano: "Reportado por ciudadanos", pendiente: "Pendiente de validar",
    no_comparable: "No comparable 1:1",
  }).map(([k, v]) =>
    `<span class="badge" style="--bc:${ESTADO_COLOR[k]}">${v}</span>`).join("");

  // ---- gráfico temporal (SVG a mano; un solo eje: nº de items/día)
  drawChart(mon.media_volume || [], mon.entregas || []);

  // ---- alertas
  const ul = document.getElementById("alerts");
  const items = (alerts && alerts.alertas) || [];
  ul.innerHTML = items.length
    ? items.map((a) => `<li><strong>${a.tipo.replaceAll("_", " ")}</strong> — ${a.aoi || a.code || ""} ${a.producto ? "· " + a.producto : ""} ${a.name ? "· " + a.name : ""} ${a.nivel === "alta" ? "⚠️" : ""}</li>`).join("")
    : "<li>Sin cambios desde la última corrida.</li>";

  function drawChart(media, entregas) {
    const el = document.getElementById("chart");
    if (!media.length) { el.textContent = "Sin serie temporal todavía."; return; }
    const W = Math.max(680, Math.min(el.clientWidth || 900, 1100)), H = 260;
    const M = { t: 28, r: 16, b: 40, l: 48 };
    const days = media.map((d) => d.fecha);
    const maxY = Math.max(...media.map((d) => Math.max(d.emm || 0, d.chatmap || 0)));
    const x = (i) => M.l + (i + 0.5) * (W - M.l - M.r) / days.length;
    const bw = Math.min(34, (W - M.l - M.r) / days.length * 0.55);
    const y = (v) => M.t + (H - M.t - M.b) * (1 - v / maxY);
    const delivByDay = {};
    for (const e of entregas) (delivByDay[e.fecha] ||= []).push(e);

    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Noticias y reportes ciudadanos por día">`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      const v = Math.round(maxY * t), yy = y(v);
      s += `<line x1="${M.l}" x2="${W - M.r}" y1="${yy}" y2="${yy}" stroke="${css("--grid")}" stroke-width="1"/>` +
        `<text x="${M.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${v.toLocaleString("es-CO")}</text>`;
    }
    media.forEach((d, i) => {
      const v = d.emm || 0, xx = x(i) - bw / 2, yy = y(v);
      s += `<rect data-i="${i}" x="${xx}" y="${yy}" width="${bw}" height="${Math.max(0, H - M.b - yy)}" rx="3" fill="${css("--s1")}"/>`;
      if (v) s += `<text x="${x(i)}" y="${yy - 4}" text-anchor="middle" font-size="10" fill="${css("--ink-2")}">${v.toLocaleString("es-CO")}</text>`;
      s += `<text x="${x(i)}" y="${H - M.b + 14}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${d.fecha.slice(5)}</text>`;
      if (delivByDay[d.fecha]) {
        const names = delivByDay[d.fecha].map((e) => e.aoi).join(", ");
        s += `<g data-deliv="${names.replaceAll('"', "")}"><path d="M ${x(i) - 5} ${M.t - 8} l 10 0 l -5 8 z" fill="${css("--critical")}"/></g>`;
      }
    });
    const line = media.map((d, i) => `${i ? "L" : "M"} ${x(i)} ${y(d.chatmap || 0)}`).join(" ");
    s += `<path d="${line}" fill="none" stroke="${css("--s2")}" stroke-width="2"/>`;
    media.forEach((d, i) => {
      s += `<circle data-i="${i}" cx="${x(i)}" cy="${y(d.chatmap || 0)}" r="4" fill="${css("--s2")}" stroke="${css("--surface-1")}" stroke-width="2"/>`;
    });
    s += `<g font-size="11">` +
      `<rect x="${M.l}" y="4" width="10" height="10" rx="2" fill="${css("--s1")}"/><text x="${M.l + 14}" y="13" fill="${css("--ink-2")}">Noticias (GDACS EMM)</text>` +
      `<circle cx="${M.l + 190}" cy="9" r="5" fill="${css("--s2")}"/><text x="${M.l + 200}" y="13" fill="${css("--ink-2")}">Reportes ciudadanos (ChatMap)</text>` +
      `<path d="M ${M.l + 420} 4 l 10 0 l -5 8 z" fill="${css("--critical")}"/><text x="${M.l + 434}" y="13" fill="${css("--ink-2")}">Entrega de producto Copernicus</text></g>`;
    s += `</svg>`;
    el.innerHTML = s;

    const tip = document.createElement("div");
    tip.className = "tooltip"; tip.style.display = "none";
    document.body.appendChild(tip);
    el.addEventListener("mousemove", (ev) => {
      const t = ev.target.closest("[data-i],[data-deliv]");
      if (!t) { tip.style.display = "none"; return; }
      let html = "";
      if (t.dataset.deliv) html = `<strong>Entrega Copernicus</strong><br>${t.dataset.deliv}`;
      else {
        const d = media[+t.dataset.i];
        html = `<strong>${d.fecha}</strong><br>Noticias EMM: ${fmt(d.emm)}<br>` +
          `ChatMap: ${fmt(d.chatmap)}<br>GDELT vol: ${d.gdelt ?? "—"}` +
          `${d.fuentes ? "<br>Medios distintos: " + fmt(d.fuentes) : ""}`;
      }
      tip.innerHTML = html; tip.style.display = "block";
      tip.style.left = (ev.clientX + 12) + "px";
      tip.style.top = (ev.clientY - 10) + "px";
    });
    el.addEventListener("mouseleave", () => tip.style.display = "none");
  }
})();
