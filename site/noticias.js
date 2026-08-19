/* Página de titulares: lista completa con filtros por zona, fuente y texto.
   Usa ui.js (fetchJson, fmt). */
(async function () {
  const { fmt, fetchJson } = window.UI;
  const data = await fetchJson("/data/public/noticias.json");
  if (!data) {
    document.getElementById("resumen").textContent =
      "Sin datos (sirve el repo por HTTP y ejecuta el pipeline).";
    return;
  }
  const items = data.items || [];
  const AOI_ES = {
    "Northern Cali": "Cali Norte", "Cali Center": "Cali Centro",
    "Quibdo Centre": "Quibdó Centro", "Western Colombia": "Occidente de Colombia",
    "Pereira": "Pereira", "Istmina": "Istmina", "Buenaventura": "Buenaventura",
  };
  const aoiEs = (n) => AOI_ES[n] || n;
  const aoiLabel = (n) => {
    const es = aoiEs(n);
    return es === n ? n : `${es} (${n})`;
  };
  const aois = [...new Set(items.flatMap((n) => n.aois || []))].sort();
  const deptos = [...new Set(items.flatMap((n) => n.departamentos || []))].sort();
  const municipios = [...new Set(items.flatMap((n) => n.municipios || []))].sort();
  const origenes = [...new Set(items.map((n) => n.origen))].sort();
  const selA = document.getElementById("f-aoi");
  const selD = document.getElementById("f-depto");
  const selM = document.getElementById("f-municipio");
  const selO = document.getElementById("f-origen");
  for (const a of aois) selA.add(new Option(aoiLabel(a), a));
  for (const d of deptos) selD.add(new Option(d, d));
  for (const m of municipios) selM.add(new Option(m, m));
  for (const o of origenes) selO.add(new Option(o, o));

  // permite enlazar directo: noticias.html#aoi=Pereira, ?q=Armenia,
  // ?depto=Quindío o ?municipio=Zarzal
  const query = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("aoi")) selA.value = hash.get("aoi");
  if (query.get("q")) document.getElementById("buscar").value = query.get("q");
  if (query.get("depto")) selD.value = query.get("depto");
  if (query.get("municipio")) selM.value = query.get("municipio");

  const lista = document.getElementById("lista");
  const resumen = document.getElementById("resumen");
  const pagEl = document.getElementById("paginado");
  const POR_PAGINA = 50;
  let pagina = 1;

  function render() {
    const q = document.getElementById("buscar").value.toLowerCase();
    const fa = selA.value, fd = selD.value, fm = selM.value, fo = selO.value;
    const hay = (n) => [
      n.titulo, n.medio, n.origen, ...(n.aois || []),
      ...(n.departamentos || []), ...(n.municipios || [])
    ].join(" ").toLowerCase();
    const sel = items.filter((n) =>
      (!q || hay(n).includes(q)) &&
      (!fa || (n.aois || []).includes(fa)) &&
      (!fd || (n.departamentos || []).includes(fd)) &&
      (!fm || (n.municipios || []).includes(fm)) &&
      (!fo || n.origen === fo));
    const paginas = Math.max(1, Math.ceil(sel.length / POR_PAGINA));
    if (pagina > paginas) pagina = paginas;
    const desde = (pagina - 1) * POR_PAGINA;
    resumen.textContent =
      `${fmt(sel.length)} de ${fmt(items.length)} titulares` +
      (paginas > 1 ? ` · página ${pagina} de ${paginas}` : "") +
      ` · actualizado ${data.generado}`;
    lista.innerHTML = sel.slice(desde, desde + POR_PAGINA).map((n) =>
      `<li><span class="meta-n">${(n.fecha || "").slice(0, 16).replace("T", " ")} · ${n.medio || n.origen}</span>` +
      (n.aois || []).map((a) => `<span class="badge" style="--bc:var(--s1)" title="${a}">${aoiEs(a)}</span>`).join("") +
      (n.departamentos || []).map((d) => `<span class="badge" style="--bc:var(--warning)">${d}</span>`).join("") +
      (n.municipios || []).map((m) => `<span class="badge" style="--bc:var(--s2)">${m}</span>`).join("") +
      `<br><a href="${n.url}" target="_blank" rel="noopener">${n.titulo}</a></li>`).join("") ||
      "<li>Nada que mostrar con estos filtros.</li>";
    window.UI.paginador(pagEl, paginas, pagina, (p) => {
      pagina = p;
      render();
      document.getElementById("filtros").scrollIntoView({ behavior: "smooth" });
    });
  }

  const filtrar = () => { pagina = 1; render(); };
  document.getElementById("buscar").addEventListener("input", filtrar);
  selA.addEventListener("change", filtrar);
  selD.addEventListener("change", filtrar);
  selM.addEventListener("change", filtrar);
  selO.addEventListener("change", filtrar);
  render();
})();
