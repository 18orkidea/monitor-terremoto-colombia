/* Monitor de brechas — frontend sin build. Lee data/public/*. Usa ui.js. */
(async function () {
  const css = window.UI.cssVar;
  const ESTADO_COLOR = {
    coincide: css("--good"), prensa: css("--s1"), ciudadano: css("--s7"),
    pendiente: css("--warning"), no_comparable: css("--muted"),
  };
  const fmt = (n) => window.UI.fmt(n, 1);

  // ---- traducción de etiquetas que llegan en inglés desde las fuentes.
  // El nombre original se conserva (title/paréntesis) para poder identificarlo
  // en los productos de Copernicus.
  const AOI_ES = {
    "Northern Cali": "Cali Norte", "Cali Center": "Cali Centro",
    "Quibdo Centre": "Quibdó Centro", "Western Colombia": "Occidente de Colombia",
    "Pereira": "Pereira", "Istmina": "Istmina", "Buenaventura": "Buenaventura",
  };
  const aoiEs = (n) => AOI_ES[n] || n;
  const aoiLabel = (n) => {
    const es = aoiEs(n);
    return es === n ? n : `${es} <span style="color:var(--muted)">(${n})</span>`;
  };
  const DICT = {
    // tipos de objeto (capas Copernicus)
    "Residential": "Residencial", "Residential Buildings": "Edificios residenciales",
    "11-Residential Buildings": "Edificios residenciales",
    "Main roads": "Vías principales", "Local Road": "Vía local",
    "Secondary Road": "Vía secundaria", "Primary Road": "Vía primaria",
    "211-Highways, Streets and Roads": "Autopistas, calles y carreteras",
    "21120-Primary Road": "Vía primaria", "21130-Secondary Road": "Vía secundaria",
    "21140-Local Road": "Vía local",
    "Building point": "Punto de edificio", "Photo-interpretation": "Fotointerpretación",
    "Not Applicable": "No aplica", "Unknown": "Desconocido",
    "Destroyed": "Destruido", "Damaged": "Dañado",
    "Possibly damaged": "Posiblemente dañado",
    "GRA": "Evaluación de daños", "GRM": "Seguimiento de daños",
    "DEL": "Delineación", "REF": "Referencia", "FEP": "Primera estimación",
    // categorías de activación (índice Copernicus)
    "Earthquake": "Terremoto", "Flood": "Inundación", "Wildfire": "Incendio forestal",
    "Storm": "Tormenta", "Landslide": "Deslizamiento",
    "Volcanic eruption": "Erupción volcánica",
  };
  const t = (s) => DICT[s] || s;
  // hitos del feed institucional GDACS (patrones)
  const tHito = (s) => (s || "")
    .replace(/UNITAR-UNOSAT Activation/i, "Activación UNITAR-UNOSAT")
    .replace(/EC\/ECHO daily map/i, "Mapa diario EC/ECHO")
    .replace(/Copernicus EMS activation/i, "Activación Copernicus EMS")
    .replace(/^M7\.4 in Colombia/i, "M7.4 en Colombia");

  const j = window.UI.fetchJson;
  const base = "../data/public/";
  const OFFICIAL_FEED = "https://monitor-terremoto-colombia-oficiales-ai.inforesidencias.workers.dev/oficiales.json";
  const [mon, aois, municipios, chat, dyfi, sismos, shake, alerts,
         dmgPts, dmgLines, notAnalysed, oficiales, hitosCurados] = await Promise.all([
    j(base + "monitor.json"), j(base + "aois.geojson"), j(base + "municipios.geojson"),
    j(base + "chatmap.geojson"),
    j(base + "dyfi_cells.geojson"), j(base + "ungrd_sismos.geojson"),
    j(base + "shakemap_mmi.geojson"), j(base + "alerts.json"),
    j(base + "damage_points.geojson"), j(base + "damage_lines.geojson"),
    j(base + "not_analysed.geojson"), j(OFFICIAL_FEED),
    j(base + "hitos_monitor.json"),
  ]);
  if (!mon) {
    document.getElementById("banner-brechas").innerHTML =
      !/^https?:$/.test(location.protocol)
        ? "<strong>Página abierta como fichero (file://):</strong> el navegador " +
          "bloquea la carga de datos por seguridad. Sirve el repo por HTTP — " +
          "desde la carpeta del proyecto: <code>python3 -m http.server 8123</code> " +
          "y abre <code>http://localhost:8123/site/</code>."
        : "Sin datos: ejecuta primero <code>python ingest/run_daily.py</code>.";
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
    (g.ungrd_rud ? `<br><strong>La brecha empezó a cerrarse:</strong> el ` +
      `<a href="https://rud.gestiondelriesgo.gov.co/" target="_blank" rel="noopener">RUD</a> ` +
      `(registro oficial de damnificados) ya cubre el evento — ` +
      `<strong>${fmt(g.ungrd_rud.municipios)}</strong> municipios con ` +
      `<strong>${fmt(g.ungrd_rud.familias)}</strong> familias y ` +
      `${fmt(g.ungrd_rud.viv_destruidas)} viviendas destruidas registradas. ` +
      `La brecha ahora es municipal: donde las autoridades locales aún no registran ` +
      `(p. ej. Pereira y Buenaventura), el satélite sigue siendo la única evidencia. ` : "") +
    `Copernicus entregó ${mon.entregas.length} productos y la comunidad ` +
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
  const munLayerById = {};
  if (aois) {
    layers["Zonas Copernicus (AOI)"] = L.geoJSON(aois, {
      style: (f) => ({
        color: ESTADO_COLOR[f.properties.estado] || css("--muted"),
        weight: 2, fillOpacity: 0.12,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        aoiLayerById[p.aoi] = l;
        l.bindPopup(`<strong>${aoiLabel(p.aoi)}</strong><br>${p.etiqueta}<br>` +
          `Población: ${fmt(p.poblacion)} · Edificios afectados: ${fmt(p.edificios_afectados)}<br>` +
          `Vías: ${fmt(p.vias_afectadas_km)} km · Interrupciones: ${fmt(p.interrupciones_viales)}`);
      },
    }).addTo(map);
    map.fitBounds(layers["Zonas Copernicus (AOI)"].getBounds().pad(0.15));
  } else { map.setView([4.5, -76.3], 8); }

  // ---- detecciones de daño de Copernicus (la faceta punto a punto)
  const GRADO_COLOR = {
    "Destroyed": css("--critical"), "Damaged": "#ec835a",
    "Possibly damaged": css("--warning"),
  };
  const GRADO_ES = { "Destroyed": "Destruido", "Damaged": "Dañado",
                     "Possibly damaged": "Posiblemente dañado" };
  if (dmgPts && dmgPts.features.length) {
    const edificios = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer === "builtUpP") };
    const crisis = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer !== "builtUpP") };
    layers[`Edificios dañados — satélite (${edificios.features.length})`] =
      L.geoJSON(edificios, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: 5.5, weight: 1.5, color: "#fff", fillOpacity: 0.9,
          fillColor: GRADO_COLOR[f.properties.damage_gra] || css("--muted"),
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          const objeto = p.simplified || p.obj_type || "";
          const metodo = p.det_method || "";
          l.bindPopup(`<strong>${GRADO_ES[p.damage_gra] || t(p.damage_gra)}</strong>` +
            ` · ${t(objeto)}${objeto && t(objeto) !== objeto ? ` <span style="color:var(--muted)">(${objeto})</span>` : ""}` +
            `<br>${aoiLabel(p.aoi)} · ` +
            `<span style="color:var(--muted)">${t(metodo)}${metodo && t(metodo) !== metodo ? ` (${metodo})` : ""} · Copernicus</span>`);
        },
      }).addTo(map);
    if (crisis.features.length) {
      layers[`Interrupciones / crisis (${crisis.features.length})`] =
        L.geoJSON(crisis, {
          pointToLayer: (f, ll) => L.circleMarker(ll, {
            radius: 6, weight: 2, color: css("--critical"),
            fillColor: "#fff", fillOpacity: 0.9,
          }),
          onEachFeature: (f, l) => {
            const obj = f.properties.obj_type || "Interrupción";
            l.bindPopup(
              `<strong>${t(obj)}</strong>${t(obj) !== obj ? ` <span style="color:var(--muted)">(${obj})</span>` : ""}<br>` +
              `${aoiLabel(f.properties.aoi)} · <span style="color:var(--muted)">Copernicus</span>`);
          },
        }).addTo(map);
    }
  }
  if (dmgLines && dmgLines.features.length) {
    layers[`Vías dañadas — satélite (${dmgLines.features.length})`] =
      L.geoJSON(dmgLines, {
        style: () => ({ color: css("--critical"), weight: 4, opacity: 0.85 }),
        onEachFeature: (f, l) => l.bindPopup(
          `<strong>Vía dañada</strong> · ${t(f.properties.info || f.properties.obj_type || "")}` +
          `<br>${aoiLabel(f.properties.aoi)} · <span style="color:var(--muted)">Copernicus</span>`),
      }).addTo(map);
  }
  if (notAnalysed && notAnalysed.features.length) {
    layers[`Zonas sin analizar (${notAnalysed.features.length})`] =
      L.geoJSON(notAnalysed, {
        style: () => ({ color: css("--muted"), weight: 1, dashArray: "3 4",
                        fillColor: css("--muted"), fillOpacity: 0.18 }),
        onEachFeature: (f, l) => l.bindTooltip(
          `Sin analizar (${aoiEs(f.properties.aoi)}) — hueco de cobertura`),
      });
  }

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
        radius: 5, color: css("--s7"), weight: 1.5,
        fillColor: css("--s7"), fillOpacity: 0.55,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        const media = p.media && /\.(jpg|jpeg|png|webp)$/i.test(p.media)
          ? `<a href="${p.media}" target="_blank" rel="noopener"><img src="${p.media}" loading="lazy" alt="foto ciudadana"></a>`
          : (p.media ? `<a href="${p.media}" target="_blank" rel="noopener">ver medio</a>` : "");
        l.bindPopup(`<strong>Reporte ciudadano</strong> · ${p.time || ""}<br>` +
          `${p.aoi ? "Dentro de AOI: " + aoiLabel(p.aoi) + "<br>" : ""}` +
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
  if (municipios && municipios.features.length) {
    const MUN_COLOR = {
      en_aoi: css("--s1"), intensidad_alta: css("--warning"),
      mencion_prensa: css("--s2"), fuera_aoi: css("--muted"),
    };
    layers[`Municipios mencionados / intensidad (${municipios.features.length})`] =
      L.geoJSON(municipios, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: f.properties.en_aoi_copernicus ? 6 : 5,
          color: "#fff", weight: 1.5,
          fillColor: MUN_COLOR[f.properties.estado] || css("--muted"),
          fillOpacity: 0.85,
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          munLayerById[p.municipio] = l;
          l.bindPopup(`<strong>${p.municipio}</strong> (${p.departamento})<br>` +
            `${p.en_aoi_copernicus ? "Dentro de AOI Copernicus" : "Fuera de AOI Copernicus"}<br>` +
            `Población DANE 2026: ${fmt(p.poblacion_2026)} ` +
            `<span style="color:var(--muted)">cabecera ${fmt(p.cabecera_2026)} · rural ${fmt(p.rural_2026)}</span><br>` +
            `DYFI: ${fmt(p.dyfi_max_cdi)} · respuestas: ${fmt(p.dyfi_respuestas)}<br>` +
            `Prensa: ${fmt(p.n_noticias)} · fuentes: ${(p.fuentes || []).join(", ") || "—"}<br>` +
            `<span style="color:var(--muted)">No equivale a daño satelital ni EDAN oficial.</span>`);
        },
      }).addTo(map);
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
    const det = a.detecciones || {};
    const grados = ["Destroyed", "Damaged", "Possibly damaged"];
    const detTotal = grados.reduce((s, g) => s + (det[g] || 0), 0);
    const detTxt = detTotal
      ? `<strong>${fmt(detTotal)}</strong> <span style="color:var(--muted)">(${grados.map((g) => det[g] || 0).join("·")})</span>`
      : "—";
    tr.innerHTML =
      `<td><strong>${aoiLabel(a.aoi)}</strong></td>` +
      `<td><span class="badge" style="--bc:${ESTADO_COLOR[c.estado] || css("--muted")}">${c.etiqueta || c.estado}</span></td>` +
      `<td class="num">${fmt(a.resumen.poblacion)}</td>` +
      `<td class="num" title="Destruidos · Dañados · Posiblemente dañados (puntos Copernicus)">${detTxt}</td>` +
      `<td class="num">${fmt(det["Vías dañadas"])}</td>` +
      `<td class="num">${fmt(det["Interrupciones/crisis"])}</td>` +
      `<td class="num">${(c.n_prensa && a.prensa_ejemplos.length)
        ? `<a href="#" class="prensa-toggle" title="Ver titulares de ejemplo">${fmt(c.n_prensa)} ▾</a>`
        : fmt(c.n_prensa)}</td>` +
      `<td class="num">${fmt(c.n_ciudadano)}</td>` +
      `<td>${(a.producto.entrega || "—").slice(0, 10)} <span style="color:var(--muted)">${t(a.producto.tipo)} (${a.producto.tipo}) v${a.producto.version}${a.producto.status !== "F" ? " · " + ({ W: "en espera", I: "en producción", N: "no producido" }[a.producto.status] || a.producto.status) : ""}</span></td>`;
    tr.addEventListener("click", (ev) => {
      if (ev.target.closest(".prensa-toggle")) {
        ev.preventDefault();
        const next = tr.nextElementSibling;
        if (next && next.classList.contains("prensa-detalle")) { next.remove(); return; }
        const dtr = document.createElement("tr");
        dtr.className = "prensa-detalle";
        dtr.innerHTML = `<td colspan="9"><strong>Titulares de ejemplo (EMM/feeds):</strong><ul>` +
          a.prensa_ejemplos.map((n) =>
            `<li>${(n.fecha || "").slice(0, 10)} · <em>${n.medio || "?"}</em> — ` +
            `<a href="${n.url}" target="_blank" rel="noopener">${n.titular}</a></li>`).join("") +
          `</ul><a href="noticias.html#aoi=${encodeURIComponent(a.aoi)}">Ver todos los titulares de ${aoiEs(a.aoi)} →</a></td>`;
        tr.after(dtr);
        return;
      }
      const l = aoiLayerById[a.aoi];
      if (l) { map.fitBounds(l.getBounds().pad(0.3)); l.openPopup(); irAlMapa(); }
    });
    tbody.appendChild(tr);
  }

  // subir al mapa al elegir una zona/municipio desde las tablas
  function irAlMapa() {
    document.getElementById("map").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- tooltips propios para las cabeceras: instantáneos y visibles también
  // en táctil (el title nativo tarda ~1 s y en móvil no existe)
  (function cabecerasConTooltip() {
    const tip = document.createElement("div");
    tip.className = "tooltip th-tip";
    tip.style.display = "none";
    document.body.appendChild(tip);
    let fijado = null;
    const mostrar = (th) => {
      tip.textContent = th.dataset.tip;
      tip.style.display = "block";
      const r = th.getBoundingClientRect();
      const w = Math.min(340, window.innerWidth - 24);
      tip.style.maxWidth = w + "px";
      let x = r.left;
      if (x + w > window.innerWidth - 12) x = window.innerWidth - w - 12;
      tip.style.left = Math.max(12, x) + "px";
      tip.style.top = (r.bottom + 6) + "px";
    };
    const ocultar = () => { tip.style.display = "none"; fijado = null; };
    for (const th of document.querySelectorAll("th[title]")) {
      th.dataset.tip = th.getAttribute("title");
      th.removeAttribute("title");   // evitar el tooltip nativo duplicado
      th.addEventListener("mouseenter", () => mostrar(th));
      th.addEventListener("mouseleave", () => { if (fijado !== th) ocultar(); });
      th.addEventListener("click", () => {   // táctil: tocar fija/oculta
        if (fijado === th) { ocultar(); } else { fijado = th; mostrar(th); }
      });
    }
    window.addEventListener("scroll", ocultar, { passive: true });
  })();

  // ---- cronología unificada: respuesta internacional + local + hitos del monitor
  //      (feed institucional GDACS + entregas Copernicus + fichero curado + derivados)
  const ETIQUETA_TIPO = { institucional: "internacional", entrega: "internacional",
                          evento: "evento", local: "local", monitor: "monitor" };
  const hitos = [
    ...(mon.institucional || []).map((h) => ({
      fecha: h.fecha, texto: tHito(h.titulo), url: h.url, tipo: "institucional" })),
    ...(mon.entregas || []).map((e) => ({
      fecha: e.fecha, tipo: "entrega",
      texto: `Copernicus entrega datos de daño: ${aoiEs(e.aoi)} (${t(e.producto)} / ${e.producto} v${e.version})` })),
    ...((hitosCurados && hitosCurados.hitos) || []).map((h) => ({
      fecha: h.fecha, texto: h.texto, url: h.url, tipo: h.tipo })),
  ].filter((h) => h.fecha).sort((x, y) => y.fecha.localeCompare(x.fecha));
  // hitos automáticos, derivados de los propios datos (sin curación manual):
  // primer balance en medios, alta del RUD y purga de la serie EMM.
  {
    const fechas = ((oficiales && oficiales.items) || [])
      .map((x) => x.search_date).filter(Boolean).sort();
    if (fechas.length) hitos.push({
      fecha: fechas[0], tipo: "local", url: "balances.html",
      texto: "Primer balance en medios citando fuentes oficiales (UNGRD/SGC) rastreado por el monitor" });
    const rudSerie = (mon.rud && mon.rud.serie) || [];
    if (rudSerie.length) hitos.push({
      fecha: rudSerie[0].fecha, tipo: "local", url: "rud.html",
      texto: `El RUD de la UNGRD cubre el evento: primera fuente oficial abierta ` +
        `(${fmt(rudSerie[0].municipios)} municipios, ${fmt(rudSerie[0].familias)} familias registradas)` });
    const mv = mon.media_volume || [];
    const ultEmm = mv.map((d, i) => d.emm != null ? i : -1).filter((i) => i >= 0).at(-1);
    if (ultEmm != null && ultEmm < mv.length - 1) hitos.push({
      fecha: mv[ultEmm + 1].fecha, tipo: "monitor",
      texto: `GDACS purga la serie global de noticias EMM (último dato: ${mv[ultEmm].fecha}); ` +
        `sobrevive solo en los snapshots del monitor, que sigue midiendo con sus feeds abiertos` });
    hitos.sort((x, y) => y.fecha.localeCompare(x.fecha));
  }
  const timelineEl = document.getElementById("timeline");
  const chipsEl = document.getElementById("crono-filtros");
  const FILTROS = [["todos", "Todos"], ["internacional", "🌍 Internacional"],
                   ["local", "🇨🇴 Local/oficial"], ["monitor", "🔧 Monitor"]];
  function pintaCronologia(filtro) {
    const vista = hitos.filter((h) => filtro === "todos" ||
      ETIQUETA_TIPO[h.tipo] === filtro || h.tipo === "evento");
    timelineEl.innerHTML = vista.map((h) =>
      `<li class="${h.tipo}"><span class="t-fecha">${h.fecha.slice(0, 16).replace("T", " ")}</span> ` +
      `<span class="t-tipo">${ETIQUETA_TIPO[h.tipo] || h.tipo}</span>` +
      (h.url ? `<a href="${h.url}" target="_blank" rel="noopener">${h.texto}</a>` : h.texto) +
      `</li>`).join("") || "<li>Sin hitos registrados aún.</li>";
  }
  if (chipsEl) {
    chipsEl.innerHTML = FILTROS.map(([k, label], i) =>
      `<button class="chip${i ? "" : " activa"}" data-filtro="${k}">${label}</button>`).join("");
    chipsEl.addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      chipsEl.querySelectorAll(".chip").forEach((c) => c.classList.toggle("activa", c === b));
      pintaCronologia(b.dataset.filtro);
    });
  }
  pintaCronologia("todos");

  // ---- otras activaciones Copernicus en Colombia
  const actsEl = document.getElementById("colombia-acts");
  const acts = (mon.colombia_activaciones || []).filter((x) => x.code !== "EMSR916");
  actsEl.innerHTML = acts.length
    ? acts.map((x) =>
      `<p><a href="${x.visor}" target="_blank" rel="noopener"><strong>${x.code}</strong></a> — ` +
      `${x.name} · ${t(x.category)}${t(x.category) !== x.category ? ` (${x.category})` : ""} · ${(x.event_time || "").slice(0, 10)} · ` +
      `${x.n_aois} zona(s) analizadas` +
      `${x.closed === false ? ' · <span class="badge" style="--bc:var(--warning)">activación abierta</span>' : ""}</p>`).join("") +
      `<p class="note">Índice completo vigilado: ${(mon.activation_index || []).length} activaciones` +
      ` públicas (todas las emergencias mapeadas por Copernicus desde jul-2023, cualquier país)` +
      ` — disponible en <a href="../data/public/monitor.json" target="_blank">monitor.json</a>.</p>`
    : "<p class='note'>Ninguna otra activación de Colombia en el rango público.</p>";
  document.getElementById("leyenda").innerHTML = Object.entries({
    coincide: "Coincide (evidencia oficial)", prensa: "Reportado en prensa",
    ciudadano: "Reportado por ciudadanos", pendiente: "Pendiente de validar",
    no_comparable: "No comparable 1:1",
  }).map(([k, v]) =>
    `<span class="badge" style="--bc:${ESTADO_COLOR[k]}">${v}</span>`).join("");

  // ---- gráfico temporal (volumen) + banda de hitos aparte, misma escala de fechas
  drawChart(mon.media_volume || []);
  drawCronoBanda(mon.media_volume || [], hitos);
  renderFuentes();

  // ---- alertas
  const ul = document.getElementById("alerts");
  const items = (alerts && alerts.alertas) || [];
  const h2a = document.querySelector("#alerts-section h2");
  if (h2a && alerts && alerts.fecha) h2a.textContent = `Alertas de hoy (${alerts.fecha})`;
  ul.innerHTML = items.length
    ? items.map((a) => `<li>${a.nivel === "alta" ? "⚠️ " : ""}` +
        `${a.texto || (a.tipo || "").replaceAll("_", " ")}</li>`).join("")
    : "<li>Sin novedades de Colombia en la corrida de hoy.</li>";

  // eje X compartido entre la gráfica de volumen y la banda de hitos
  function ejeX(el, media) {
    const W = Math.max(680, Math.min(el.clientWidth || 900, 1100));
    const M = { t: 28, r: 16, b: 40, l: 48 };
    const x = (i) => M.l + (i + 0.5) * (W - M.l - M.r) / media.length;
    return { W, M, x };
  }

  function drawChart(media) {
    const el = document.getElementById("chart");
    if (!media.length) { el.textContent = "Sin serie temporal todavía."; return; }
    const { W, M, x } = ejeX(el, media), H = 260;
    const maxY = Math.max(...media.map((d) => Math.max(d.emm || 0, d.feeds || 0, d.chatmap || 0)));
    const bw = Math.min(34, (W - M.l - M.r) / media.length * 0.55);
    const y = (v) => M.t + (H - M.t - M.b) * (1 - v / maxY);

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
    });
    // feeds abiertos del monitor: la serie que sigue viva tras la purga de EMM
    const lineF = media.filter((d) => d.feeds != null);
    if (lineF.length) {
      const pf = media.map((d, i) => d.feeds == null ? null : `${x(i)},${y(d.feeds)}`)
        .map((p, i, arr) => p == null ? null : `${arr.slice(0, i).some(q => q != null) ? "L" : "M"} ${p.replace(",", " ")}`)
        .filter(Boolean).join(" ");
      s += (`<path d="${pf}" fill="none" stroke="${css("--s3")}" stroke-width="2" stroke-dasharray="1 0"/>`);
      media.forEach((d, i) => {
        if (d.feeds == null) return;
        s += (`<circle data-i="${i}" cx="${x(i)}" cy="${y(d.feeds)}" r="4" fill="${css("--s3")}" stroke="${css("--surface-1")}" stroke-width="2"/>`);
      });
    }
    const line = media.map((d, i) => `${i ? "L" : "M"} ${x(i)} ${y(d.chatmap || 0)}`).join(" ");
    s += `<path d="${line}" fill="none" stroke="${css("--s7")}" stroke-width="2"/>`;
    media.forEach((d, i) => {
      s += `<circle data-i="${i}" cx="${x(i)}" cy="${y(d.chatmap || 0)}" r="4" fill="${css("--s7")}" stroke="${css("--surface-1")}" stroke-width="2"/>`;
    });

    s += `<g font-size="11">` +
      `<rect x="${M.l}" y="4" width="10" height="10" rx="2" fill="${css("--s1")}"/><text x="${M.l + 14}" y="13" fill="${css("--ink-2")}">Noticias EMM (global, purgado)</text>` +
      `<circle cx="${M.l + 205}" cy="9" r="5" fill="${css("--s3")}"/><text x="${M.l + 214}" y="13" fill="${css("--ink-2")}">Feeds abiertos del monitor</text>` +
      `<circle cx="${M.l + 385}" cy="9" r="5" fill="${css("--s7")}"/><text x="${M.l + 394}" y="13" fill="${css("--ink-2")}">Reportes ciudadanos (ChatMap)</text></g>`;
    s += `</svg>`;
    el.innerHTML = s;

    window.UI.attachTooltip(el, (t) => {
      if (t.dataset.i == null) return null;
      const d = media[+t.dataset.i];
      return `<strong>${d.fecha}</strong><br>Noticias EMM (global): ${fmt(d.emm)}<br>` +
        `Feeds abiertos: ${fmt(d.feeds)}<br>` +
        `ChatMap: ${fmt(d.chatmap)}<br>GDELT vol: ${d.gdelt ?? "—"}` +
        `${d.fuentes ? "<br>Medios distintos: " + fmt(d.fuentes) : ""}`;
    });
  }

  /* Banda de cronología: los hitos separados del volumen, misma escala de fechas.
     Tres carriles (internacional / local-oficial / monitor); ▲ = entrega Copernicus. */
  function drawCronoBanda(media, hitosCrono) {
    const el = document.getElementById("crono-banda");
    if (!el || !media.length) return;
    const { W, M, x } = ejeX(el, media);
    const LANES = [
      { key: "internacional", emoji: "🌍", nombre: "Respuesta internacional", color: css("--s1") },
      { key: "local", emoji: "🇨🇴", nombre: "Respuesta local/oficial", color: css("--good") },
      { key: "monitor", emoji: "🔧", nombre: "Cambios del monitor", color: css("--warning") },
    ];
    const laneDe = (h) => h.tipo === "institucional" || h.tipo === "entrega" ? 0 :
      (h.tipo === "local" || h.tipo === "evento" ? 1 : 2);
    const LH = 26, H = 6 + LANES.length * LH + 18;
    const dayIdx = Object.fromEntries(media.map((d, i) => [d.fecha, i]));
    // agrupar por carril+día para repartir los marcadores del mismo día
    const grupos = {};
    for (const h of (hitosCrono || [])) {
      const i = dayIdx[(h.fecha || "").slice(0, 10)];
      if (i != null) (grupos[`${laneDe(h)}|${i}`] ||= []).push(h);
    }
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Hitos de la respuesta por día y por tipo">`;
    // rejilla vertical por día (misma posición que las barras de arriba)
    media.forEach((d, i) => {
      s += `<line x1="${x(i)}" x2="${x(i)}" y1="4" y2="${H - 16}" stroke="${css("--grid")}" stroke-width="1" stroke-dasharray="2 3"/>` +
        `<text x="${x(i)}" y="${H - 4}" text-anchor="middle" font-size="9" fill="${css("--muted")}">${d.fecha.slice(5)}</text>`;
    });
    LANES.forEach((lane, li) => {
      const yy = 6 + li * LH + LH / 2;
      s += `<text x="${M.l - 8}" y="${yy + 4}" text-anchor="end" font-size="12">${lane.emoji}<title>${lane.nombre}</title></text>`;
      if (li) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${6 + li * LH}" y2="${6 + li * LH}" stroke="${css("--grid")}" stroke-width="0.5"/>`;
    });
    for (const [clave, dia] of Object.entries(grupos)) {
      const [li, i] = clave.split("|").map(Number);
      const yy = 6 + li * LH + LH / 2;
      dia.forEach((h, k) => {
        const xx = x(i) + (k - (dia.length - 1) / 2) * 11;
        const texto = `${h.fecha.slice(0, 10)} · ${(ETIQUETA_TIPO[h.tipo] || h.tipo)} · ` +
          h.texto.replaceAll('"', "&quot;");
        const color = h.tipo === "evento" ? css("--critical") : LANES[li].color;
        s += h.tipo === "entrega"
          ? `<path data-hito="${texto}" d="M ${xx - 5} ${yy - 4} l 10 0 l -5 9 z" fill="${css("--critical")}"/>`
          : h.tipo === "evento"
            ? `<text data-hito="${texto}" x="${xx}" y="${yy + 5}" text-anchor="middle" font-size="13" fill="${color}">★</text>`
            : `<circle data-hito="${texto}" cx="${xx}" cy="${yy}" r="5" fill="${color}" stroke="${css("--surface-1")}" stroke-width="1.5"/>`;
      });
    }
    s += `</svg>`;
    el.innerHTML = s;
    window.UI.attachTooltip(el, (t) =>
      t.dataset.hito ? `<strong>Hito</strong><br>${t.dataset.hito}` : null);
  }

  /* Tarjetas de la comparativa de fuentes (portada resumen). */
  function renderFuentes() {
    const el = document.getElementById("fuentes-cards");
    if (!el) return;
    const fuentes = window.UI.comparativaFuentes(mon, oficiales);
    const fmt0 = (n) => window.UI.fmt(n, 0);
    const principal = {
      satelite: (f) => [fmt0(f.cifras.edificios_dañados), "edificios dañados vistos por satélite"],
      rud: (f) => [fmt0(f.cifras.familias), "familias registradas oficialmente"],
      medios: (f) => [fmt0(f.cifras.familias), "familias afectadas según medios"],
      ciudadano: (f) => [fmt0(f.cifras.reportes), "reportes ciudadanos con foto"],
    };
    window.UI.metricCards(el, fuentes.map((f) => {
      const [valor, unidad] = principal[f.id](f);
      return { label: f.nombre, value: valor,
               sub: `${unidad} · ${f.alcance}${f.fecha ? ` · ${f.fecha}` : ""}`,
               href: f.href };
    }));
  }
})();
