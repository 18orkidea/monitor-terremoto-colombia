/* Comportamiento compartido por todas las páginas del sitio.

   La barra y el pie YA NO se inyectan aquí: los escribe el build
   (`deploy/render_html.py::nav_estatico` / `pie_estatico`, y el paso
   `escribir_piezas_compartidas`), que es la fuente única de las 213 páginas. Vivían
   dos veces —aquí y allí— y había que sincronizarlas a mano; además, inyectadas
   por JavaScript llegaban vacías a quien lee el sitio sin ejecutarlo.

   Lo que sigue aquí es lo que solo puede pasar en el navegador: abrir el
   <details> de un ancla, las notificaciones del botón 🔔 y el menú de compartir
   del botón ↗. Esos dos botones los emite `nav_estatico(botones_js=True)`, y
   solo en las cinco páginas grandes. Los bloques que los manejan se callan si
   no los encuentran, así que **un botón que se pierda no da error, desaparece
   sin más**: por eso lo vigila un test —`TestBarraYPieUnaSolaVez`— y no la
   consola.
*/
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

/* Notificaciones push: botón 🔔 con tres estados (activar / activadas / no
   soportado). Solo aparece si el worker de avisos está desplegado (la clave
   VAPID pública en ui.js). En iOS sin PWA instalada, explica cómo instalarla. */
(function () {
  const btn = document.getElementById("btn-alertas");
  const { PUSH_BASE, VAPID_PUBLIC_KEY } = window.UI || {};
  if (!btn || !VAPID_PUBLIC_KEY) return;   // avisos aún no desplegados
  const soporta = "serviceWorker" in navigator && "PushManager" in window &&
    "Notification" in window;
  const esIosSinApp = /iphone|ipad|ipod/i.test(navigator.userAgent) &&
    !window.navigator.standalone;
  if (!soporta && !esIosSinApp) return;    // navegador sin push: no molestar
  btn.hidden = false;

  const claveBytes = () => {
    const s = VAPID_PUBLIC_KEY.replaceAll("-", "+").replaceAll("_", "/");
    return Uint8Array.from(atob(s.padEnd(Math.ceil(s.length / 4) * 4, "=")),
      (c) => c.charCodeAt(0));
  };

  async function estadoActual() {
    if (!soporta) return "sin-soporte";
    const reg = await navigator.serviceWorker.getRegistration("sw.js");
    const sub = reg && await reg.pushManager.getSubscription();
    return sub ? "activadas" : "desactivadas";
  }

  async function pinta() {
    const e = await estadoActual();
    btn.textContent = e === "activadas" ? "🔔 Alertas ✓" : "🔔 Alertas";
    btn.title = e === "activadas"
      ? "Alertas activadas — clic para desactivarlas"
      : "Recibir las alertas del día como notificación";
  }

  btn.addEventListener("click", async () => {
    if (esIosSinApp) {
      alert("En iPhone/iPad las notificaciones requieren instalar el " +
        "monitor como app: toca Compartir → «Añadir a pantalla de inicio» " +
        "y actívalas desde ahí.");
      return;
    }
    try {
      const reg = await navigator.serviceWorker.register("sw.js");
      const previa = await reg.pushManager.getSubscription();
      if (previa) {
        // clic con alertas activas = desactivar
        await fetch(`${PUSH_BASE}/desuscribir`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: previa.endpoint }) });
        await previa.unsubscribe();
        await pinta();
        return;
      }
      const permiso = await Notification.requestPermission();
      if (permiso !== "granted") return;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: claveBytes() });
      const r = await fetch(`${PUSH_BASE}/suscribir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub.toJSON()) });
      if (!r.ok) throw new Error(`suscripción HTTP ${r.status}`);
      await pinta();
    } catch (e) {
      console.warn("alertas push:", e);
      btn.textContent = "🔔 Error";
      setTimeout(pinta, 2500);
    }
  });
  pinta();
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

/* Filtro de la cronología (referencia.html). Los hitos YA vienen escritos por
   el build (deploy/render_html.py::cronologia_referencia): aquí solo se
   muestran u ocultan, así que sin JavaScript se lee la cronología entera —el
   filtro ordena la lectura, no la revela—. «Todos» no oculta nada, y el hito
   del sismo se ve siempre: es el origen de la serie, no una categoría más.
   Se calla si no encuentra sus chips, como el resto de bloques de este
   fichero: una página sin cronología no da error, no hace nada. */
(function () {
  const chips = document.querySelectorAll("#crono-filtros .chip-crono");
  const hitos = document.querySelectorAll("#timeline li");
  if (!chips.length || !hitos.length) return;
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
      const filtro = chip.dataset.filtro;
      hitos.forEach((li) => {
        li.hidden = !(filtro === "todos" || li.classList.contains(filtro)
                      || li.classList.contains("evento"));
      });
    });
  });
})();
