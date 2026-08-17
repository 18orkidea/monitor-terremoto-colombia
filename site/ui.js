/* Componentes y utilidades reutilizables del sitio (window.UI).
   Un solo lugar para formateo, buscadores de tabla, tarjetas métricas,
   tooltips y la comparativa de fuentes — cargar antes del script de página. */
window.UI = (function () {
  "use strict";

  const fmt = (n, dec = 0) => n == null ? "—" :
    Number(n).toLocaleString("es-CO", { maximumFractionDigits: dec });

  const norm = (s) => (s || "").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").toLowerCase();

  const cssVar = (v) =>
    getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const esc = (s) => String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));

  async function fetchJson(path) {
    try { const r = await fetch(path); return r.ok ? await r.json() : null; }
    catch { return null; }
  }

  /* Tabla con buscador: todas las filas quedan disponibles para la búsqueda,
     pero sin filtro solo se muestran las `top` primeras.
     opts: tbody, input (opcional), rows, top, fila(r)->html <tr>,
           texto(r)->string indexable, nota (elemento opcional),
           notaTexto(q, visibles, total)->string, vacio (html opcional). */
  function tablaBuscable(opts) {
    const { tbody, input, rows, top, fila, texto, nota, notaTexto, vacio } = opts;
    const idx = rows.map((r) => norm(texto(r)));
    const pinta = () => {
      const q = norm(input ? input.value.trim() : "");
      const vista = q ? rows.filter((_, i) => idx[i].includes(q))
        : rows.slice(0, top || rows.length);
      tbody.innerHTML = vista.length ? vista.map(fila).join("") :
        `<tr><td colspan="99" style="color:var(--muted)">${vacio || "Sin coincidencias."}</td></tr>`;
      if (nota && notaTexto) nota.textContent = notaTexto(q, vista.length, rows.length);
      return vista;
    };
    // oninput (no addEventListener): el render puede ejecutarse más de una vez
    if (input) input.oninput = pinta;
    pinta();
    return pinta;
  }

  /* Tarjetas métricas: [{label, value, sub?, href?}] en un .metric-strip. */
  function metricCards(el, cards) {
    el.innerHTML = cards.map((c) => {
      const inner = `<span>${c.label}</span><strong>${c.value}</strong>` +
        (c.sub ? `<small>${c.sub}</small>` : "");
      return c.href
        ? `<a class="metric-card" href="${c.href}">${inner}</a>`
        : `<div class="metric-card">${inner}</div>`;
    }).join("");
  }

  /* Tooltip flotante compartido (SVGs, tablas). htmlFor(target)->html|null. */
  function attachTooltip(el, htmlFor) {
    const tip = document.createElement("div");
    tip.className = "tooltip"; tip.style.display = "none";
    document.body.appendChild(tip);
    el.addEventListener("mousemove", (ev) => {
      const t = ev.target.closest("[data-tip],[data-i],[data-deliv],[data-hito]");
      const html = t && htmlFor(t);
      if (!html) { tip.style.display = "none"; return; }
      tip.innerHTML = html; tip.style.display = "block";
      tip.style.left = (ev.clientX + 12) + "px";
      tip.style.top = (ev.clientY - 10) + "px";
    });
    el.addEventListener("mouseleave", () => tip.style.display = "none");
    return tip;
  }

  /* ---- feed de balances (worker externo): URL única del frontend.
     El worker guarda la copia viva; el repo archiva un snapshot diario en
     feeds/balances/. Cambiarla aquí y solo aquí. */
  const OFICIALES_BASE = "https://monitor-terremoto-colombia-oficiales-ai.inforesidencias.workers.dev";

  /* ---- worker de avisos (Web Push + Telegram). VAPID_PUBLIC_KEY vacía =
     los avisos aún no están desplegados y el botón 🔔 no se muestra.
     Al desplegar workers/push (ver su README), pegar aquí la clave pública. */
  const PUSH_BASE = "https://monitor-terremoto-colombia-push.inforesidencias.workers.dev";
  const VAPID_PUBLIC_KEY = "";
  const TELEGRAM_CANAL = "";   // p. ej. "https://t.me/brechas_terremoto"

  /* ---- balances en medios: selección del mejor snapshot (regla compartida;
     la marca is_liveblog original la pone el worker — test de paridad en
     tests/test_unit.py) */
  function isLiveblog(item) {
    const text = `${item.title || ""} ${item.publication_url || item.url || ""}`.toLowerCase();
    return item.is_liveblog ||
      /en vivo|directo|live[-_\s]?news|última hora|ultima hora|minuto a minuto|liveblog/.test(text);
  }
  const metricCount = (item) =>
    Object.values(item.cifras || {}).filter((v) => v != null).length;
  const sourceScore = (item) => {
    if (item.official && item.source_level === "oficial_institucional") return 4;
    if (item.official) return 3;
    if ((item.reported_data_source || []).length) return 2;
    return 0;
  };

  /* Estabilidad respecto a la víspera: un balance ACUMULADO no retrocede.
     Un candidato cuyas cifras ancla caen >10 % frente al mejor del día
     anterior suele ser un medio tardío citando un corte viejo (caso
     Primicias 16-ago: 181 fallecidos cuando el consolidado iba por 294) —
     se penaliza por delante incluso de la marca liveblog: un liveblog
     coherente informa mejor que un artículo estático desactualizado. */
  const ANCLAS = ["fallecidos", "familias_afectadas"];
  function retrocede(item, prev) {
    if (!prev) return false;
    const p = prev.cifras || {}, c = (item && item.cifras) || {};
    return ANCLAS.some((k) =>
      p[k] != null && c[k] != null && c[k] < p[k] * 0.9);
  }

  /* Contradicción fuerte entre los candidatos de un mismo día (>15 % entre
     mínimo y máximo): la discrepancia ES información de brecha y se muestra,
     no se suprime. Devuelve {cifra: {min, max}} o null. */
  function disputaDia(dayItems) {
    const out = {};
    for (const k of ["fallecidos", "heridos", "desaparecidos",
                     "familias_afectadas"]) {
      const vs = dayItems.map((x) => (x.cifras || {})[k])
        .filter((v) => v != null);
      if (vs.length >= 2) {
        const min = Math.min(...vs), max = Math.max(...vs);
        if (min > 0 && max > min * 1.15) out[k] = { min, max };
      }
    }
    return Object.keys(out).length ? out : null;
  }

  /* Prensa nacional colombiana: el snapshot mostrado prioriza los diarios
     nacionales — están más cerca del consolidado oficial que los medios
     internacionales, que suelen llegar tarde y con cortes viejos. Lista
     curada (nombre o dominio); ampliar aquí cuando aparezca uno nuevo. */
  const MEDIOS_NACIONALES = [
    "el tiempo", "eltiempo", "el espectador", "elespectador",
    "el colombiano", "elcolombiano", "caracol", "rcn", "semana",
    "la republica", "larepublica", "portafolio", "blu radio", "bluradio",
    "w radio", "wradio", "el heraldo", "elheraldo", "vanguardia", "pulzo",
    "la silla vacia", "lasillavacia",
  ];
  function esNacional(item) {
    const p = item.publisher || {};
    const n = norm(`${p.name || ""} ${p.domain || ""} ` +
                   `${item.publication_url || item.url || ""}`);
    return MEDIOS_NACIONALES.some((m) => n.includes(m)) ||
      n.includes(".com.co") || n.includes(".gov.co");
  }

  /* Orden de selección del día: estable respecto a la víspera (un acumulado
     no retrocede), prensa nacional colombiana, no-liveblog, el más completo,
     mejor fuente citada, y el más reciente. */
  function bestSnapshot(items, prev) {
    return [...items].sort((a, b) =>
      Number(retrocede(a, prev)) - Number(retrocede(b, prev)) ||
      Number(esNacional(b)) - Number(esNacional(a)) ||
      Number(isLiveblog(a)) - Number(isLiveblog(b)) ||
      metricCount(b) - metricCount(a) ||
      sourceScore(b) - sourceScore(a) ||
      ((b.captured_at || "").localeCompare(a.captured_at || "")))[0] || null;
  }

  /* Serie diaria con memoria: el mejor snapshot de cada día se elige con el
     día anterior como referencia de estabilidad, y cada día lleva su
     `consolidado`: el último valor conocido de CADA cifra con su fecha de
     origen — un dato no desaparece porque el mejor snapshot del día no lo
     traiga; se conserva y se marca de cuándo es.
     Devuelve [{fecha, item, disputa, consolidado: {cifra: {valor, fecha}}}] */
  function mejorPorDia(items) {
    const fechas = [...new Set(items.map((x) => x.search_date))].sort();
    let prev = null;
    let consolidado = {};
    return fechas.map((fecha) => {
      const dia = items.filter((x) => x.search_date === fecha);
      const item = bestSnapshot(dia, prev);
      if (item) prev = item;
      const c = (item && item.cifras) || {};
      consolidado = { ...consolidado };
      for (const [k, v] of Object.entries(c)) {
        if (v != null) consolidado[k] = { valor: v, fecha };
      }
      return { fecha, item, disputa: disputaDia(dia),
               consolidado: { ...consolidado } };
    });
  }

  /* Comparativa de fuentes: las cuatro miradas sobre el mismo desastre,
     con cifras homogéneas para portada (tarjetas) y balances (tabla). */
  function comparativaFuentes(mon, oficiales) {
    const out = [];
    const aois = (mon && mon.aois) || [];
    const edifDe = (z) => (z.resumen && z.resumen.edificios_afectados) || 0;
    const edificios = aois.reduce((a, z) => a + edifDe(z), 0);
    const zonas = aois.filter((z) => edifDe(z) > 0).length;
    const entregas = (mon && mon.entregas) || [];
    out.push({
      id: "satelite", nombre: "Satélite · Copernicus", href: "index.html#mapa",
      fecha: entregas.map((e) => e.fecha).sort().at(-1) || null,
      alcance: `${zonas} zonas urbanas mapeadas`,
      cifras: { edificios_dañados: edificios },
    });
    const rudSerie = mon && mon.rud && mon.rud.serie || [];
    if (rudSerie.length) {
      const u = rudSerie.at(-1);
      out.push({
        id: "rud", nombre: "RUD · registro oficial", href: "rud.html",
        fecha: u.fecha, alcance: `${fmt(u.municipios)} municipios con registro`,
        cifras: { municipios: u.municipios, familias: u.familias,
                  personas: u.personas, viv_destruidas: u.viv_destruidas,
                  viv_averiadas: u.viv_averiadas },
      });
    }
    const items = (oficiales && oficiales.items || []).filter((x) => x.search_date);
    if (items.length) {
      // serie con memoria: el último día se elige con estabilidad vs víspera,
      // y las cifras salen del consolidado (el último valor conocido de cada
      // una) — que el snapshot del día no traiga familias no las borra
      const ultimo = mejorPorDia(items).at(-1);
      const fecha = ultimo.fecha;
      const c = Object.fromEntries(Object.entries(ultimo.consolidado)
        .map(([k, v]) => [k, v.valor]));
      out.push({
        id: "medios", nombre: "Balances en medios · citan oficiales",
        href: "balances.html", fecha,
        alcance: `${fmt(c.municipios_afectados)} municipios afectados`,
        cifras: { municipios: c.municipios_afectados,
                  familias: c.familias_afectadas, personas: c.personas_afectadas,
                  viv_destruidas: c.viviendas_destruidas,
                  viv_averiadas: c.viviendas_averiadas,
                  fallecidos: c.fallecidos, heridos: c.heridos,
                  desaparecidos: c.desaparecidos },
      });
    }
    const cit = mon && mon.citizen;
    if (cit) {
      out.push({
        id: "ciudadano", nombre: "Reporte ciudadano · ChatMap",
        href: "index.html#mapa", fecha: mon.fecha || null,
        alcance: `${fmt(cit.en_aoi)} dentro de zonas mapeadas`,
        cifras: { reportes: cit.chatmap_total },
      });
    }
    return out;
  }

  return { fmt, norm, cssVar, esc, fetchJson, tablaBuscable, metricCards,
           attachTooltip, isLiveblog, bestSnapshot, metricCount, mejorPorDia,
           disputaDia, comparativaFuentes, OFICIALES_BASE, PUSH_BASE,
           VAPID_PUBLIC_KEY, TELEGRAM_CANAL };
})();
