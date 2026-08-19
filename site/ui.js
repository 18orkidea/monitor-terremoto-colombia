/* Componentes y utilidades reutilizables del sitio (window.UI).
   Un solo lugar para formateo, buscadores de tabla, tarjetas métricas,
   tooltips y la comparativa de fuentes — cargar antes del script de página. */
window.UI = (function () {
  "use strict";

  const fmt = (n, dec = 0) => n == null ? "—" :
    Number(n).toLocaleString("es-CO", { maximumFractionDigits: dec });

  /* Porcentaje con un decimal. Una proporción diminuta pero real jamás se
     redondea a «0 %»: un municipio con damnificados no puede leerse como
     municipio sin damnificados. */
  const pct = (n) => n == null ? "—"
    : (n > 0 && n < 0.05 ? "<0,1 %" : fmt(n, 1) + " %");

  /* Fecha ISO → «16-ago-2026», el formato que usa el resto del sitio. */
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"];
  const fechaEs = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return m ? `${+m[3]}-${MESES[+m[2] - 1]}-${m[1]}` : (iso || "—");
  };

  /* Estados de la capa de municipios: etiqueta, color y explicación en UN solo
     sitio (la tabla y el mapa los pintaban por separado y las etiquetas ya
     habían divergido). El orden es el de la cascada de ingest/municipios.py. */
  const ESTADO_MUNICIPIO = {
    en_aoi: ["En zona Copernicus", "--s1",
             "El municipio cae dentro de una zona con producto de daño de Copernicus"],
    evaluado_unosat: ["Evaluado por UNOSAT", "--s9",
                      "El centro satelital de la ONU evaluó allí edificio a " +
                      "edificio, fuera de toda zona de Copernicus. Es " +
                      "fotointerpretación sobre imagen de muy alta resolución, " +
                      "no validada en campo por la propia fuente"],
    intensidad_alta: ["Intensidad alta", "--warning",
                      "Intensidad percibida DYFI ≥ 6, sin producto de daño"],
    mencion_prensa: ["Mencionado en prensa", "--s2",
                     "Titulares que lo nombran, sin producto de daño ni DYFI alto"],
    solo_rud: ["Solo registro municipal (RUD)", "--s8",
               "El registro de damnificados que carga el municipio es su única " +
               "documentación del daño: ningún producto satelital ni titular lo " +
               "ha verificado de forma independiente"],
    fuera_aoi: ["Intensidad sentida", "--muted",
                "Se sintió (DYFI < 6) y ningún producto satelital ni titular lo " +
                "documenta; tampoco tiene registro en el RUD"],
  };
  const estadoMunicipio = (estado) =>
    ESTADO_MUNICIPIO[estado] || ["Sin clasificar", "--muted", ""];

  /* Salvedad de los homónimos de departamento para la intro de municipios.
     Función pura (no toca el DOM) para que el harness de node la pueda testear:
     incluye la puntuación, porque el punto pertenece a la rama —el HTML lo dejó
     fuera— y solo nombra a los que siguen siendo «solo RUD». */
  function fraseHomonimos(items) {
    const homs = (items || [])
      .filter((m) => m.homonimo_de_departamento && m.estado === "solo_rud")
      .map((m) => `${m.municipio} (${m.departamento})`);
    return homs.length
      ? `, salvo ${homs.join(" y ")}, que se llaman igual que un departamento y ` +
        `a los que el monitor no puede atribuir titulares.`
      : ".";
  }

  /* Damnificados sin una línea de prensa. La afirmación se construye sola y en
     TRES niveles, porque no todos los ceros valen lo mismo:
       - `ciertos`: topónimo sin ambigüedad Y búsqueda propia de prensa. Es el
         único nivel que AFIRMA: se preguntó y no hubo respuesta.
       - `dudosos`: su nombre exige co-mención del departamento, así que el cero
         puede ser del filtro; y de ellos, `sin_busqueda` son aquellos por los
         que el monitor ni siquiera pregunta (entraron solos desde el RUD).
       - `sin_atribucion`: se llaman igual que un departamento. No tienen cero,
         tienen ausencia de dato (R3), así que no entran en ningún total — pero
         se nombran, porque son los más invisibles de todos.
     Si un día no quedara ninguno mudo, devuelve null y el banner desaparece en
     vez de mentir (R11). */
  function silencioDePrensa(items) {
    const suma = (xs) => xs.reduce((t, m) => t + (m.rud_personas || 0), 0);
    const conRud = (items || []).filter((m) => m.rud_personas);
    const mudos = conRud.filter((m) => m.n_noticias === 0)
      .sort((a, b) => b.rud_personas - a.rud_personas);
    if (!mudos.length) return null;
    // `=== true`, no `!== false`: si el campo faltara —porque alguien llame a
    // build_municipios sin el conjunto de búsquedas, o por un JSON viejo—, los
    // municipios por los que el monitor NUNCA preguntó caerían en el nivel que
    // afirma «preguntamos y no hubo nada», que es justo la falsedad que este
    // nivel existe para impedir. La cadena entera falla cerrada.
    const ciertos = mudos.filter(
      (m) => !m.requiere_depto && !m.homonimo_de_departamento
             && m.busqueda_propia === true);
    const dudosos = mudos.filter((m) => !ciertos.includes(m));
    // el texto afirma la CAUSA («se llaman igual que un departamento»), así que
    // el filtro tiene que comprobarla, no solo el síntoma de la celda vacía
    const sinAtribucion = conRud.filter(
      (m) => m.n_noticias == null && m.homonimo_de_departamento);
    // el techo se calcula por TASA, no por número de personas: decir «hasta el
    // X %» y que otro de la propia lista lo supere sería falso
    const conTasa = ciertos.filter((m) => m.tasa_rud_pct != null);
    const techo = conTasa.length
      ? conTasa.reduce((a, b) => (b.tasa_rud_pct > a.tasa_rud_pct ? b : a))
      : null;
    return {
      mudos: mudos.length, personas: suma(mudos),
      ciertos: ciertos.map((m) => m.municipio),
      personas_ciertas: suma(ciertos),
      dudosos: dudosos.length,
      sin_busqueda: dudosos.filter((m) => m.busqueda_propia === false).length,
      sin_atribucion: sinAtribucion.length,
      personas_sin_atribucion: suma(sinAtribucion),
      techo: techo
        ? { municipio: techo.municipio, tasa_rud_pct: techo.tasa_rud_pct }
        : null,
    };
  }

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

  /* Paginador compacto compartido: ‹ 1 … p-1 p p+1 … N › (mismo aspecto en
     todas las tablas del sitio; estilos en #paginado de styles.css).
     onPage(p) se invoca con la página elegida. */
  function paginador(el, paginas, pagina, onPage) {
    if (!el) return;
    if (paginas <= 1) { el.innerHTML = ""; return; }
    const nums = [...new Set([1, 2, pagina - 1, pagina, pagina + 1,
                              paginas - 1, paginas]
      .filter((n) => n >= 1 && n <= paginas))].sort((a, b) => a - b);
    let html = `<button ${pagina === 1 ? "disabled" : ""} data-p="${pagina - 1}">‹ Anterior</button>`;
    let prev = 0;
    for (const n of nums) {
      if (n - prev > 1) html += `<span style="color:var(--muted)">…</span>`;
      html += `<button data-p="${n}" class="${n === pagina ? "actual" : ""}">${n}</button>`;
      prev = n;
    }
    html += `<button ${pagina === paginas ? "disabled" : ""} data-p="${pagina + 1}">Siguiente ›</button>`;
    el.innerHTML = html;
    // onclick (no addEventListener): el paginador se reconstruye en cada render
    el.querySelectorAll("button[data-p]").forEach((b) =>
      b.onclick = () => onPage(+b.dataset.p));
  }

  /* Comparador para una columna: los nulos SIEMPRE al final, suban o bajen —
     un municipio sin dato no puede encabezar la tabla al ordenar por esa
     columna. Empate resuelto por `desempate` para que el orden sea estable. */
  function comparador(valor, dir, desempate) {
    const vacio = (v) => v === null || v === undefined || v === "";
    return (a, b) => {
      const va = valor(a), vb = valor(b);
      if (vacio(va) && vacio(vb)) return desempate ? desempate(a, b) : 0;
      if (vacio(va)) return 1;
      if (vacio(vb)) return -1;
      let c;
      if (typeof va === "number" && typeof vb === "number") c = va - vb;
      else c = String(va).localeCompare(String(vb), "es");
      if (c !== 0) return dir === "desc" ? -c : c;
      return desempate ? desempate(a, b) : 0;
    };
  }

  /* Tabla con buscador: todas las filas quedan disponibles para la búsqueda,
     pero sin filtro solo se muestran las `top` primeras — salvo que se pase
     `paginado` (elemento), en cuyo caso la tabla se pagina entera de
     `porPagina` en `porPagina` (también los resultados de búsqueda).
     opts: tbody, input (opcional), rows, top, fila(r)->html <tr>,
           texto(r)->string indexable, nota (elemento opcional),
           notaTexto(q, visibles, total, orden)->string — `orden` es null o
             {i, dir}, para que la nota no afirme un criterio que ya no rige,
           vacio (html opcional),
           paginado (elemento opcional), porPagina (número opcional),
           filtroExtra(r)->bool (opcional; la página compone ahí sus chips y
             selects — esta función no sabe qué controles existen),
           columnas: [{th, valor(r), desempate?}] (opcional; hace clicables las
             cabeceras y ordena ANTES de paginar).
     Devuelve `pinta(o)`; con `pinta({reiniciar:true})` vuelve a la página 1,
     que es lo que necesita cualquier filtro externo al cambiar. */
  function tablaBuscable(opts) {
    const { tbody, input, rows, top, fila, texto, nota, notaTexto, vacio,
            paginado, porPagina, columnas } = opts;
    // Indexado por identidad, NO por posición: `filtroExtra` recorta las filas
    // antes de que actúe el buscador, así que desde la primera fila descartada
    // un índice posicional apuntaría al texto de otra fila.
    const idx = new Map(rows.map((r) => [r, norm(texto(r))]));
    let pagina = 1;
    let orden = null;   // {i, dir}

    const pinta = (o) => {
      if (o && o.reiniciar) pagina = 1;
      const q = norm(input ? input.value.trim() : "");
      let filtradas = rows;
      if (opts.filtroExtra) filtradas = filtradas.filter(opts.filtroExtra);
      if (q) filtradas = filtradas.filter((r) => (idx.get(r) || "").includes(q));
      if (orden && columnas) {
        const col = columnas[orden.i];
        filtradas = [...filtradas].sort(
          comparador(col.valor, orden.dir, col.desempate));
      }
      let vista;
      if (paginado) {
        const pp = porPagina || top || filtradas.length;
        const paginas = Math.max(1, Math.ceil(filtradas.length / pp));
        if (pagina > paginas) pagina = paginas;
        vista = filtradas.slice((pagina - 1) * pp, pagina * pp);
        paginador(paginado, paginas, pagina, (p) => { pagina = p; pinta(); });
      } else {
        vista = (q || opts.filtroExtra || orden)
          ? filtradas : rows.slice(0, top || rows.length);
      }
      tbody.innerHTML = vista.length ? vista.map(fila).join("") :
        `<tr><td colspan="99" style="color:var(--muted)">${vacio || "Sin coincidencias."}</td></tr>`;
      if (nota && notaTexto)
        nota.textContent = notaTexto(q, filtradas.length, rows.length, orden);
      return vista;
    };

    (columnas || []).forEach((col, i) => {
      if (!col.th) return;
      col.th.classList.add("ord");
      col.th.setAttribute("aria-sort", "none");
      // el aviso lo pone quien hace ordenable la columna, no cada página
      col.th.title = (col.th.title ? col.th.title + " " : "") + "Pulsa para ordenar.";
      col.th.tabIndex = 0;
      const alternar = () => {
        orden = (orden && orden.i === i && orden.dir === "asc")
          ? { i, dir: "desc" } : { i, dir: "asc" };
        columnas.forEach((c, j) => {
          if (!c.th) return;
          c.th.setAttribute("aria-sort", j === i
            ? (orden.dir === "asc" ? "ascending" : "descending") : "none");
        });
        pinta({ reiniciar: true });
      };
      // onclick (no addEventListener): pinta() puede ejecutarse más de una vez
      col.th.onclick = alternar;
      col.th.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alternar(); }
      };
    });

    // oninput (no addEventListener): el render puede ejecutarse más de una vez
    if (input) input.oninput = () => pinta({ reiniciar: true });
    pinta();
    return pinta;
  }

  /* Buscador sobre una tabla que YA viene escrita en el HTML desde el build.

     Es la contrapartida de tablaBuscable: aquí el JavaScript no crea ninguna
     fila, solo muestra u oculta las que el generador dejó escritas. Así la
     página sirve su contenido a quien no ejecuta JavaScript —los rastreadores
     de sistemas de IA no lo hacen— y el navegador conserva el buscador.

     Cada <tr> trae su texto normalizado en data-buscar, escrito por
     deploy/render_html.py con la misma normalización que UI.norm. */
  function tablaHidratada(opts) {
    const { tbody, input, nota, notaTexto, vacio } = opts;
    if (!tbody) return () => {};
    const filas = Array.from(tbody.rows).filter((r) => r.dataset.buscar !== undefined);
    const total = filas.length;

    let sinCoincidencias = null;
    const pinta = () => {
      const q = norm(input ? input.value.trim() : "");
      let visibles = 0;
      filas.forEach((tr) => {
        const ok = !q || tr.dataset.buscar.includes(q);
        tr.hidden = !ok;
        if (ok) visibles++;
      });
      if (!visibles && !sinCoincidencias) {
        sinCoincidencias = tbody.insertRow();
        sinCoincidencias.innerHTML =
          `<td colspan="99" style="color:var(--muted)">${vacio || "Sin coincidencias."}</td>`;
      }
      if (sinCoincidencias) sinCoincidencias.hidden = visibles > 0;
      if (nota && notaTexto) nota.textContent = notaTexto(q, visibles, total);
      return visibles;
    };
    if (input) input.oninput = pinta;
    pinta();
    return pinta;
  }

  /* Ficha de un globo del mapa — el ÚNICO constructor de popups del sitio.

     `filas` es [[etiqueta, valor], …]. Una fila cuyo valor está vacío no se
     pinta: un globo jamás debe decir «Confianza: —», porque eso hace creer
     que la fuente respondió a esa pregunta y dijo «nada». Si la fuente no
     mide algo en ese punto, la pregunta no aparece.

     Vacío es null, undefined, cadena vacía o NaN. El 0 NO es vacío: un cero
     medido es un dato, y confundirlo con una ausencia es justo el error que
     prohíbe la R3. `false` tampoco es vacío.

     Cada fuente pasa sus propias etiquetas, en el vocabulario en que ella
     publica: lo que Copernicus llama «grado de daño» y UNOSAT llama
     «confianza del análisis» no se homogeneiza a un genérico que borraría en
     qué se diferencian.

     opts: {titulo, subtitulo?, filas?, pie?, html?} — `pie` va en gris al
     final (procedencia), `html` es un bloque libre (una foto, un enlace). */
  function fichaMapa(opts) {
    const vacio = (v) => v === null || v === undefined || v === "" ||
      (typeof v === "number" && Number.isNaN(v));
    const partes = [];
    if (opts.titulo) partes.push(`<strong>${opts.titulo}</strong>`);
    if (!vacio(opts.subtitulo)) partes.push(String(opts.subtitulo));
    for (const [etiqueta, valor] of opts.filas || []) {
      if (vacio(valor)) continue;
      partes.push(vacio(etiqueta) ? String(valor)
        : `${etiqueta}: ${valor}`);
    }
    if (!vacio(opts.html)) partes.push(String(opts.html));
    if (!vacio(opts.pie))
      partes.push(`<span style="color:var(--muted)">${opts.pie}</span>`);
    return partes.join("<br>");
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
  const VAPID_PUBLIC_KEY = "BBrMEN-T86OTPOCsTn6CbJSnqaLJeOGWjaVnNbe8WB6RCwEXaDORqDVWxnD-6jhBr3g5XkD72fce-jEKQDycAwc";
  const TELEGRAM_CANAL = "https://t.me/terremotoCO2026";

  /* ---- medio de una noticia (regla compartida: página de titulares, fichas
     municipales y cualquier recuento de pluralidad).

     Tres campos que no son lo mismo y conviene no confundir:
       · `medio`          — el FEED que trajo la pieza («Google News — Nóvita»)
       · `medio_canonico` — la cabecera que la firma, según el propio RSS
       · `url`            — a dónde lleva el enlace, que en los feeds de Google
                            News NO es el medio sino news.google.com

     Cuando no consta la cabecera y el enlace pasa por Google News, no se
     inventa: se dice de dónde viene el enlace y ya. Poner ahí el nombre del
     feed daría por medio lo que es una búsqueda. */
  const viaGoogleNews = (n) => /(^|\.)news\.google\.com$/.test(hostDe(n.url || ""));

  function hostDe(url) {
    try { return new URL(url).hostname.toLowerCase(); } catch (e) { return ""; }
  }

  function medioDe(n) {
    if (n.medio_canonico) return n.medio_canonico;
    return viaGoogleNews(n) ? null : (n.medio || n.origen || null);
  }

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

  return { fmt, pct, fechaEs, estadoMunicipio, ESTADO_MUNICIPIO,
           fraseHomonimos, silencioDePrensa, comparador, norm, cssVar, esc,
           fetchJson, tablaBuscable, tablaHidratada, paginador, metricCards,
           fichaMapa,
           attachTooltip, isLiveblog, bestSnapshot, metricCount, mejorPorDia,
           medioDe, viaGoogleNews, hostDe,
           disputaDia, comparativaFuentes, OFICIALES_BASE, PUSH_BASE,
           VAPID_PUBLIC_KEY, TELEGRAM_CANAL };
})();
