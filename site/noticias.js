/* Página de titulares: lista completa con filtros por zona, fuente y texto.
   Usa ui.js (fetchJson, fmt). */
(async function () {
  // Solo http(s) ABSOLUTA llega al atributo href: un `javascript:` en un canal
  // ajeno se convertiría en código al pulsar el titular. Y la URL tiene que
  // traer su host: resolviéndola contra `location.origin` —como hacía la
  // primera versión— una ruta relativa se convertía en un enlace a nuestro
  // propio dominio con aspecto de titular externo. Ninguno de los 6.304
  // titulares del corpus es relativo, así que exigirlo no pierde ni uno.
  // Espejo EXACTO de `render_html.py::enlace_seguro`, con test que ejecuta los
  // dos —si tocas una, mira la otra—.
  const enlaceSeguro = (u) => {
    try {
      const url = new URL(u);
      return /^https?:$/.test(url.protocol) && url.host ? String(u) : "#";
    } catch (e) { return "#"; }
  };

  const { fmt, fechaEs, fetchJson, medioDe, viaGoogleNews, esc } = window.UI;
  const data = await fetchJson("/data/public/noticias.json");
  if (!data) {
    document.getElementById("resumen").textContent =
      "No se han podido cargar los titulares. Vuelve a intentarlo en unos minutos.";
    return;
  }
  const items = data.items || [];
  const aoiEs = window.UI.aoiEs;   // los nombres de zona los pone ui.js
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
      n.titulo, n.medio, n.medio_canonico, n.origen, ...(n.aois || []),
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
    // Solo el recuento vivo del filtro: la fecha del dato la sirve el build en
    // el sello del encabezado. Repetirla aquí con la corrida del JSON volvería
    // a vestir el empaquetado de fecha del dato (la copia que diverge, y el bug que motivó el sello).
    resumen.textContent =
      `${fmt(sel.length)} de ${fmt(items.length)} titulares` +
      (paginas > 1 ? ` · página ${pagina} de ${paginas}` : "");
    // etiqueta de lista: forma corta (9.8), nunca la ISO cruda
    const fechaDe = (n) => {
      const iso = n.fecha || "";
      return fechaEs(iso) + (iso.length >= 16 ? `, ${iso.slice(11, 16)}` : "");
    };
    lista.innerHTML = sel.slice(desde, desde + POR_PAGINA).map((n) =>
      `<li><span class="meta-n">${fechaDe(n)}` +
      `${medioDe(n) ? ` · ${esc(medioDe(n))}` : ""}` +
      (viaGoogleNews(n)
        ? ` · <span class="via" title="Google News recopila titulares de otros medios. El enlace que publica su feed lleva ahí, no a la página del medio.">vía Google News</span>`
        : "") + `</span>` +
      // `.etiqueta`, no `.chip`: un chip es una acción y estas no lo son.
      // Espejo de deploy/render_html.py, que pinta las mismas en el build —
      // si tocas una, mira la otra (tests/test_frontend.py::TestChipsSonAcciones).
      (n.aois || []).map((a) => `<span class="etiqueta" title="${esc(a)}">${esc(aoiEs(a))}</span>`).join("") +
      (n.departamentos || []).map((d) => `<span class="etiqueta dep">${esc(d)}</span>`).join("") +
      (n.municipios || []).map((m) => `<span class="etiqueta mun">${esc(m)}</span>`).join("") +
      // titular y enlace vienen de canales ajenos: sin escapar, un titular con
      // una etiqueta dentro ejecutaría lo que quisiera quien lo publicó
      `<br><a href="${esc(enlaceSeguro(n.url))}" target="_blank" rel="noopener nofollow">` +
      `${esc(n.titulo)}</a></li>`).join("") ||
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
