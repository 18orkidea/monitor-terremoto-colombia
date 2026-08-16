/* Componente compartido: barra de navegación y pie de sitio.
   Se inyecta en <nav id="site-nav"> y <div id="site-footer"> de cada página —
   un solo lugar que mantener para todo el sitio. */
(function () {
  const PAGES = [
    { href: "index.html", label: "🗺️ Mapa" },
    { href: "municipios.html", label: "🏘️ Municipios" },
    { href: "rud.html", label: "🏛️ RUD" },
    { href: "balances.html", label: "📊 Balances" },
    { href: "noticias.html", label: "📰 Titulares" },
  ];
  const actual = (location.pathname.split("/").pop() || "index.html");

  const nav = document.getElementById("site-nav");
  if (nav) {
    nav.innerHTML =
      `<a class="brand" href="index.html"><strong>Monitor de brechas</strong>` +
      `<span>Terremoto de Colombia M7.4 · 10-ago-2026</span></a>` +
      `<div class="nav-links">` +
      PAGES.map((p) =>
        `<a href="${p.href}"${p.href === actual ? ' class="activa"' : ""}>${p.label}</a>`
      ).join("") +
      `<a href="https://chatmap.hotosm.org/colombia.html" target="_blank" rel="noopener" class="nav-cta">📍 Reportar daño</a>` +
      `<button id="btn-compartir" title="Compartir esta página">↗ Compartir</button>` +
      `<a href="https://github.com/18orkidea/monitor-terremoto-colombia" target="_blank" rel="noopener" title="Código y datos abiertos">GitHub</a>` +
      `<a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener" title="Apoya los servidores y la recolección de datos">☕</a>` +
      `</div>`;
  }

  const foot = document.getElementById("site-footer");
  if (foot) {
    foot.innerHTML =
      `<div class="sf-cols">` +
      `<div><strong>Monitor de brechas de reporte</strong><br>` +
      `Observatorio abierto del terremoto M7.4 de Colombia (10-ago-2026). ` +
      `Cruza satélite, reporte ciudadano, prensa y fuentes oficiales — con cada cifra ` +
      `rastreable a su origen.</div>` +
      `<div><strong>Secciones</strong><br>` +
      `<a href="index.html">Mapa y cruce por zona</a><br>` +
      `<a href="municipios.html">Municipios del área de influencia</a><br>` +
      `<a href="rud.html">RUD: registro oficial día a día</a><br>` +
      `<a href="balances.html">Balances en medios y comparativa</a><br>` +
      `<a href="noticias.html">Titulares por zona</a><br>` +
      `<a href="index.html#glosario">Glosario</a> · <a href="index.html#metodologia">Metodología</a></div>` +
      `<div><strong>Datos abiertos (CC BY 4.0)</strong><br>` +
      `<a href="../data/public/crosscheck.csv" download>CSV del cruce</a><br>` +
      `<a href="../data/public/monitor.json" target="_blank">JSON del monitor</a><br>` +
      `<a href="${window.UI.OFICIALES_BASE}/oficiales.rss" target="_blank" rel="noopener">RSS de balances</a><br>` +
      `<a href="https://github.com/18orkidea/monitor-terremoto-colombia" target="_blank" rel="noopener">Repositorio y snapshots</a></div>` +
      `</div>` +
      `<p class="sf-line">🇨🇴 ❤️ Mantenido por <a href="https://col.social/@jp" target="_blank" rel="me noopener">@jp@col.social</a> ` +
      `con apoyo de <a href="https://orkidea.eu" target="_blank" rel="noopener">Orkidea</a>. ` +
      `Las <a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener">donaciones ☕</a> ` +
      `mantienen servidores, scraping y recolección diaria de datos. ` +
      `Código MIT · datos derivados CC BY 4.0 · los datos crudos conservan la licencia de cada fuente.</p>`;
  }
})();

/* al navegar a un ancla que vive dentro de un <details> cerrado, abrirlo
   (Chrome/Firefox lo hacen solos; Safari no) */
(function () {
  function abrirDestino() {
    if (!location.hash) return;
    let t = null;
    try { t = document.querySelector(location.hash); } catch { return; }
    const d = t && t.closest("details");
    if (d) d.open = true;
  }
  window.addEventListener("hashchange", abrirDestino);
  abrirDestino();
})();

/* Cloudflare Web Analytics (sin cookies): un solo punto para las tres páginas */
(function () {
  var s = document.createElement("script");
  s.src = "https://static.cloudflareinsights.com/beacon.min.js";
  s.defer = true;
  s.setAttribute("data-cf-beacon", '{"token": "32d0d392db2240d88939d6278eaebd41"}');
  document.head.appendChild(s);
})();

/* Compartir: nativo (móvil) o menú de redes (escritorio) */
(function () {
  const btn = document.getElementById("btn-compartir");
  if (!btn) return;
  const datos = () => ({
    title: document.title,
    text: document.querySelector('meta[name="description"]')?.content || document.title,
    url: document.querySelector('link[rel="canonical"]')?.href || location.href,
  });
  let menu = null;
  function cerrarMenu() { if (menu) { menu.remove(); menu = null; } }
  btn.addEventListener("click", async () => {
    const d = datos();
    if (navigator.share) {
      try { await navigator.share(d); } catch { /* usuario canceló */ }
      return;
    }
    if (menu) { cerrarMenu(); return; }
    const u = encodeURIComponent(d.url), t = encodeURIComponent(d.title);
    const redes = [
      ["WhatsApp", `https://wa.me/?text=${t}%20${u}`],
      ["Telegram", `https://t.me/share/url?url=${u}&text=${t}`],
      ["X", `https://twitter.com/intent/tweet?url=${u}&text=${t}`],
      ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${u}`],
      ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${u}`],
      ["Bluesky", `https://bsky.app/intent/compose?text=${t}%20${u}`],
    ];
    menu = document.createElement("div");
    menu.id = "menu-compartir";
    menu.innerHTML = redes.map(([n, h]) =>
      `<a href="${h}" target="_blank" rel="noopener">${n}</a>`).join("") +
      `<a href="#" data-copiar>📋 Copiar enlace</a>`;
    const r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 6) + "px";
    menu.style.right = Math.max(8, window.innerWidth - r.right) + "px";
    document.body.appendChild(menu);
    menu.querySelector("[data-copiar]").addEventListener("click", async (ev) => {
      ev.preventDefault();
      try { await navigator.clipboard.writeText(d.url); ev.target.textContent = "✓ Copiado"; }
      catch { ev.target.textContent = d.url; }
      setTimeout(cerrarMenu, 900);
    });
    setTimeout(() => document.addEventListener("click", function fuera(e) {
      if (!menu || menu.contains(e.target) || e.target === btn) return;
      cerrarMenu(); document.removeEventListener("click", fuera);
    }), 0);
  });
})();
