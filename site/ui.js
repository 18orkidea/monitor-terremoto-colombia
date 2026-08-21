/* Componentes y utilidades reutilizables del sitio (window.UI).
   Un solo lugar para formateo, buscadores de tabla, tarjetas métricas,
   tooltips y la comparativa de fuentes — cargar antes del script de página. */
window.UI = (function () {
  "use strict";

  const fmt = (n, dec = 0) => n == null ? "—" :
    Number(n).toLocaleString("es-CO", { maximumFractionDigits: dec });

  /* Cifra tal como se escribe DENTRO de una frase: del cero al nueve con
     letras, de 10 en adelante en guarismos (Libro de estilo, 10.1). En tablas y
     cuadros las cifras van siempre en guarismos (10.2), así que esto no
     sustituye a fmt. Espejo de `fmt_prosa` en deploy/render_html.py. */
  const LETRAS = ["cero", "una", "dos", "tres", "cuatro", "cinco",
                  "seis", "siete", "ocho", "nueve"];
  const fmtProsa = (n, femenino) => {
    if (n == null) return "—";
    const entero = Math.trunc(n);
    if (entero !== n || entero < 0 || entero > 9) return fmt(n);
    if (entero === 1) return femenino ? "una" : "un";
    return LETRAS[entero];
  };

  /* Porcentaje con un decimal. Una proporción diminuta pero real jamás se
     redondea a «0 %»: un municipio con damnificados no puede leerse como
     municipio sin damnificados. */
  const pct = (n) => n == null ? "—"
    : (n > 0 && n < 0.05 ? "<0,1 %" : fmt(n, 1) + " %");

  /* Fechas: UN solo criterio en todo el sitio (Libro de estilo, 9.6 y 9.8).

       · En prosa la fecha NO se abrevia nunca: `fechaLarga` → «16 de agosto
         de 2026». Es lo que lee quien llega de un buscador, y estas páginas
         se releerán dentro de años.
       · En tablas, ejes de gráfico, chips y desplegables, donde el espacio
         manda, se admite la forma corta: `fechaEs` → «16-ago-2026».
       · La forma ISO (2026-08-16) es un valor, no un texto: vale como
         `value` de un <option> o clave de datos, nunca como algo que se lee.

     Espejo exacto de `fecha_corta` y `fecha_larga` en deploy/render_html.py:
     si tocas una, mira la otra. */
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"];
  const MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                        "julio", "agosto", "septiembre", "octubre", "noviembre",
                        "diciembre"];
  const partesFecha = (iso) => /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  const fechaEs = (iso) => {
    const m = partesFecha(iso);
    return m ? `${+m[3]}-${MESES[+m[2] - 1]}-${m[1]}` : (iso || "—");
  };
  const fechaLarga = (iso) => {
    const m = partesFecha(iso);
    return m ? `${+m[3]} de ${MESES_LARGOS[+m[2] - 1]} de ${m[1]}` : (iso || "—");
  };
  /* Solo para ejes de gráfico, donde no cabe ni la forma corta entera: la
     misma abreviatura sin el año, que la propia gráfica ya declara. */
  const diaMes = (iso) => {
    const m = partesFecha(iso);
    return m ? `${+m[3]}-${MESES[+m[2] - 1]}` : (iso || "—");
  };

  /* Estados de la capa de municipios: etiqueta, color y explicación en UN solo
     sitio (la tabla y el mapa los pintaban por separado y las etiquetas ya
     habían divergido). El orden es el de la cascada de ingest/municipios.py. */
  const ESTADO_MUNICIPIO = {
    en_aoi: ["En zona Copernicus", "--s1",
             "El municipio cae dentro de una zona que el satélite del servicio " +
             "de emergencias de Copernicus analizó y para la que publicó un " +
             "mapa de daños"],
    evaluado_unosat: ["Evaluado por UNOSAT", "--s9",
                      "El centro satelital de la ONU evaluó allí edificio a " +
                      "edificio, fuera de toda zona de Copernicus. Es lectura " +
                      "de imágenes de muy alta resolución, no comprobada sobre " +
                      "el terreno por la propia fuente"],
    intensidad_alta: ["Intensidad alta", "--warning",
                      "La población declaró una intensidad de 6 o más en el " +
                      "cuestionario del Servicio Geológico de Estados Unidos, " +
                      "y ningún satélite ha publicado mapa de daños"],
    mencion_prensa: ["Mencionado en prensa", "--s2",
                     "Titulares que lo nombran, sin mapa de daños por satélite " +
                     "ni intensidad percibida alta"],
    solo_rud: ["Solo registro municipal (RUD)", "--s8",
               "El registro de damnificados que carga el municipio es su única " +
               "documentación del daño: ningún producto satelital ni titular lo " +
               "ha verificado de forma independiente"],
    fuera_aoi: ["Intensidad sentida", "--muted",
                "Se sintió, con intensidad percibida por debajo de 6, y ningún " +
                "satélite ni titular lo documenta; tampoco tiene damnificados " +
                "inscritos en el registro oficial"],
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
    const { tbody, input, nota, notaTexto, vacio, paginado, porPagina,
            columnas, filtroExtra } = opts;
    if (!tbody) return () => {};
    const filas = Array.from(tbody.rows).filter((r) => r.dataset.buscar !== undefined);
    const total = filas.length;
    let pagina = 1;
    let orden = null;   // {i, dir}

    // El valor de cada columna viaja en data-v{i}, escrito por el generador:
    // ordenar no obliga a volver a leer el JSON ni a reconstruir la fila.
    const valorDe = (tr, i) => {
      const v = tr.dataset["v" + i];
      if (v === undefined || v === "") return null;
      const n = Number(v);
      return Number.isNaN(n) ? v : n;
    };

    let sinCoincidencias = null;
    const pinta = (o) => {
      if (o && o.reiniciar) pagina = 1;
      const q = norm(input ? input.value.trim() : "");
      let visibles = filas.filter((tr) =>
        (!filtroExtra || filtroExtra(tr)) && (!q || tr.dataset.buscar.includes(q)));

      if (orden && columnas) {
        const col = columnas[orden.i];
        visibles = [...visibles].sort(comparador(
          (tr) => valorDe(tr, orden.i), orden.dir,
          col && col.desempate ? (a, b) => col.desempate(a, b) : undefined));
        // reordenar el DOM, no reconstruirlo: las filas son las mismas
        visibles.forEach((tr) => tbody.appendChild(tr));
      }

      let vista = visibles;
      if (paginado) {
        const pp = porPagina || visibles.length || 1;
        const paginas = Math.max(1, Math.ceil(visibles.length / pp));
        if (pagina > paginas) pagina = paginas;
        vista = visibles.slice((pagina - 1) * pp, pagina * pp);
        paginador(paginado, paginas, pagina, (p) => { pagina = p; pinta(); });
      }
      const enVista = new Set(vista);
      filas.forEach((tr) => { tr.hidden = !enVista.has(tr); });

      if (!vista.length && !sinCoincidencias) {
        sinCoincidencias = tbody.insertRow();
        sinCoincidencias.innerHTML =
          `<td colspan="99" style="color:var(--muted)">${vacio || "Sin coincidencias."}</td>`;
      }
      if (sinCoincidencias) sinCoincidencias.hidden = vista.length > 0;
      if (nota && notaTexto) nota.textContent = notaTexto(q, visibles.length, total, orden);
      return vista;
    };

    (columnas || []).forEach((col, i) => {
      if (!col.th) return;
      col.th.classList.add("ord");
      col.th.setAttribute("aria-sort", "none");
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
      col.th.onclick = alternar;
      col.th.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alternar(); }
      };
    });

    if (input) input.oninput = () => pinta({ reiniciar: true });
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

  /* Tarjetas métricas: [{label, value, sub?, title?, href?}] en un .metric-strip. */
  function metricCards(el, cards) {
    el.innerHTML = cards.map((c) => {
      const inner = `<span>${c.label}</span><strong>${c.value}</strong>` +
        (c.sub ? `<small>${c.sub}</small>` : "");
      // el title es opcional y va en el contenedor: una cifra compuesta debe
      // poder decir de qué está compuesta sin abandonar la tarjeta
      const t = c.title ? ` title="${esc(c.title)}"` : "";
      return c.href
        ? `<a class="metric-card" href="${c.href}"${t}>${inner}</a>`
        : `<div class="metric-card"${t}>${inner}</div>`;
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

  /* Estabilidad respecto al CONSOLIDADO (no respecto al mejor de ayer): un
     balance acumulado no retrocede. Comparar contra el ítem de la víspera
     dejaba el guardarraíl ciego el día siguiente a un ganador sin cifras —el
     18-ago ganó un post sin anclas y el 19 entró un corte del día 10 sin
     oposición, publicando 11.132 familias donde el RUD registraba 65.663. */
  const ANCLAS = ["fallecidos", "familias_afectadas"];

  /* Las diez cifras del balance, TODAS acumulativas por decisión editorial
     (docs/DECISIONES.md, 21-ago-2026): ninguna baja nunca. Incluye
     `desaparecidos`, que en la realidad SÍ puede bajar —cuando aparece gente
     viva, que es una buena noticia—; por eso el sitio las rotula «máximo
     informado» con su fecha y no «cifras actuales». Si el worker añade una
     métrica nueva, el test la obliga a declararse aquí. */
  const CIFRAS_BALANCE = ["departamentos_afectados", "municipios_afectados",
    "personas_afectadas", "familias_afectadas", "viviendas_averiadas",
    "viviendas_destruidas", "heridos", "fallecidos", "desaparecidos",
    "rescatados"];

  /* Techo de salto. Con monotonía, un error de extracción AL ALZA se queda
     para siempre: el worker ya produjo «900 municipios afectados» desde el
     nombre de una imagen (mapa-900x601.jpg). Un salto mayor que este factor no
     entra, pero NO se descarta en silencio: se registra y se muestra, porque un
     salto real —Clarín, 54.008 → 120.238 el 16-ago, ×2,2— es noticia. */
  const TECHO_SALTO = 5;

  const valorDe = (celda) => (celda && typeof celda === "object")
    ? celda.valor : celda;

  /* Atribución oficial trazable: o el medio cita a una entidad oficial, o la
     publica la propia entidad. Necesaria, pero NO suficiente: medido sobre el
     corpus, los cortes viejos citan a UNGRD y SGC igual de bien que los
     frescos —de eso se encarga la monotonía—. Lo que descarta es la cifra que
     no se puede atribuir a nadie. */
  function atribucionOficial(item) {
    return !!(item && (item.official ||
      (item.reported_data_source || []).length));
  }

  /* Coherencia interna: relaciones que no pueden romperse sin que la
     extracción esté mal. Una familia tiene al menos una persona; un fallecido
     es una persona afectada. En todas, `personas_afectadas` es el lado que
     falla, así que es la cifra que queda en cuarentena — las demás del mismo
     ítem siguen sirviendo. Cazó el «personas_afectadas: 304» del boletín del
     18-ago, que eran en realidad los fallecidos. */
  function incoherencias(item) {
    const c = (item && item.cifras) || {};
    const p = c.personas_afectadas;
    if (p == null) return [];
    const rotas = [];
    if (c.familias_afectadas != null && p < c.familias_afectadas)
      rotas.push("personas_afectadas < familias_afectadas");
    for (const k of ["fallecidos", "heridos", "desaparecidos"])
      if (c[k] != null && p < c[k]) rotas.push("personas_afectadas < " + k);
    return rotas;
  }
  const esCoherente = (item) => incoherencias(item).length === 0;
  const enCuarentena = (item) =>
    incoherencias(item).length ? ["personas_afectadas"] : [];

  /* Un candidato sin NINGUNA cifra ancla no puede considerarse estable: no
     retrocede porque no trae con qué. Es el fallo que dejó ganar el 18-ago a
     un post con tres cifras frente a uno con diez. */
  const sinAnclas = (item) =>
    ANCLAS.every((k) => ((item && item.cifras) || {})[k] == null);

  function retrocede(item, consolidado) {
    const c = (item && item.cifras) || {};
    const cons = consolidado || {};
    return ANCLAS.some((k) => {
      const prev = valorDe(cons[k]);
      return prev != null && c[k] != null && c[k] < prev * 0.9;
    });
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

  /* Prensa nacional colombiana: los diarios nacionales suelen estar más cerca
     del consolidado oficial que los internacionales tardíos. Criterio TARDÍO
     —por detrás de la atribución y de la marca liveblog—: cuando pesaba antes,
     un `.com.co` cualquiera adelantaba a un medio con mejor dato, y eso decidió
     el 19-ago a favor de un liveblog del día 10. */
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

  /* Orden de selección del día: estable frente al consolidado, con cifras
     ancla, coherente, con atribución oficial, no-liveblog, prensa nacional, el
     más completo y el más reciente. La marca liveblog va por DEBAJO de la
     atribución (R8 dice «se marcan y pesan menos», no «pierden siempre»): un
     liveblog que cita UNGRD y SGC informa mejor que un estático mudo. */
  function cmpCandidatos(consolidado) {
    return (a, b) =>
      Number(retrocede(a, consolidado)) - Number(retrocede(b, consolidado)) ||
      Number(sinAnclas(a)) - Number(sinAnclas(b)) ||
      Number(!esCoherente(a)) - Number(!esCoherente(b)) ||
      sourceScore(b) - sourceScore(a) ||
      Number(isLiveblog(a)) - Number(isLiveblog(b)) ||
      Number(esNacional(b)) - Number(esNacional(a)) ||
      metricCount(b) - metricCount(a) ||
      ((b.captured_at || "").localeCompare(a.captured_at || ""));
  }
  function bestSnapshot(items, consolidado) {
    return [...items].sort(cmpCandidatos(consolidado))[0] || null;
  }

  /* Consolidado del día: para CADA cifra por separado se recorren los
     candidatos en el orden de bestSnapshot y se toma el primer valor que
     cumpla las cuatro condiciones. Por cifra y no por ítem ganador, para no
     perder un dato que el ganador no trae —las 134.342 viviendas averiadas del
     boletín oficial del 18-ago se perderían si solo mirásemos al ganador—.
     Lo rechazado no desaparece: sale en `ignoradas` con su motivo, porque la
     discrepancia es brecha (R12), no un error a ocultar. */
  function consolidarDia(previo, dia, fecha, orden) {
    const consolidado = { ...previo };
    const ignoradas = [];
    for (const k of CIFRAS_BALANCE) {
      const vigente = valorDe(consolidado[k]);
      for (const item of orden) {
        const v = ((item && item.cifras) || {})[k];
        if (v == null) continue;
        const medio = (item.publisher || {}).name ||
          (item.publisher || {}).domain || null;
        const url = item.publication_url || item.url || null;
        const rechaza = (motivo) => ignoradas.push(
          { cifra: k, valor: v, motivo, medio, url });
        if (enCuarentena(item).includes(k)) {
          rechaza("cifra incoherente con el resto del mismo balance");
          continue;
        }
        if (!atribucionOficial(item)) {
          rechaza("sin atribución oficial trazable");
          continue;
        }
        if (vigente != null && v <= vigente) {
          if (v < vigente) rechaza("retrocede sobre el máximo informado");
          continue;
        }
        if (vigente != null && vigente > 0 && v > vigente * TECHO_SALTO) {
          rechaza(`salto mayor de ×${TECHO_SALTO} sobre el máximo informado`);
          continue;
        }
        consolidado[k] = { valor: v, fecha, medio, url };
        break;
      }
    }
    return { consolidado, ignoradas };
  }

  /* Serie diaria con memoria: cada día lleva su mejor captura y el
     `consolidado`, que es el MÁXIMO informado de cada cifra con su fecha y su
     medio de origen. Ninguna cifra baja (decisión editorial de 21-ago-2026): un
     medio tardío citando un corte viejo ya no puede hacer retroceder la serie.
     Devuelve [{fecha, item, disputa, consolidado, ignoradas}] */
  function mejorPorDia(items) {
    const fechas = [...new Set(items.map((x) => x.search_date))].sort();
    // Dos acumuladores con oficios distintos, y conviene no confundirlos:
    // `maximos` es todo lo visto —con atribución o sin ella— y sirve para
    // detectar el corte viejo en la VITRINA; `consolidado` es lo que se
    // PUBLICA, y por eso exige atribución oficial. Si fueran el mismo, un día
    // sin ninguna fuente atribuible dejaría el guardarraíl sin referencia y
    // volvería a colarse un corte de hace nueve días.
    let maximos = {};
    let consolidado = {};
    return fechas.map((fecha) => {
      const dia = items.filter((x) => x.search_date === fecha);
      const orden = [...dia].sort(cmpCandidatos(maximos));
      const item = orden[0] || null;
      const paso = consolidarDia(consolidado, dia, fecha, orden);
      consolidado = paso.consolidado;
      for (const x of dia) {
        for (const k of ANCLAS) {
          const v = (x.cifras || {})[k];
          if (v != null && (maximos[k] == null || v > maximos[k])) maximos[k] = v;
        }
      }
      return { fecha, item, disputa: disputaDia(dia),
               consolidado: { ...consolidado }, ignoradas: paso.ignoradas };
    });
  }

  /* Comparativa de fuentes: las cuatro miradas sobre el mismo desastre,
     con cifras homogéneas para portada (tarjetas) y balances (tabla). */
  function comparativaFuentes(mon, oficiales) {
    const out = [];
    const aois = (mon && mon.aois) || [];
    const edifDe = (z) => (z.resumen && z.resumen.edificios_afectados) || 0;
    const copernicus = aois.reduce((a, z) => a + edifDe(z), 0);
    const zonas = aois.filter((z) => edifDe(z) > 0).length;
    const entregas = (mon && mon.entregas) || [];
    // OJO: esta regla vive en DOS superficies —aquí y en deploy/gen_og.py, que
    // pinta la imagen que se comparte—. Si tocas una, mira la otra.
    // Las dos miradas satelitales se suman porque miran municipios distintos:
    // Copernicus, las zonas urbanas del eje Cali-Pereira-Chocó; UNOSAT, tres
    // municipios de Caldas donde Copernicus no ha cartografiado nada. Si un
    // día se pisaran, la ingesta lo dice en `municipios_tambien_en_aoi_copernicus`
    // y la portada deja de sumar sola: contar dos veces el mismo tejado sería
    // peor que quedarse corto. Los `posibles` de UNOSAT viajan aparte para que
    // el sitio pueda decir cuántos de esos edificios son hipótesis.
    const uno = (mon && mon.unosat) || null;
    const solapan = !!(uno && (uno.municipios_tambien_en_aoi_copernicus || []).length);
    const unosat = uno && !solapan ? (uno.edificios || 0) : 0;
    const munsUnosat = unosat ? (uno.municipios || []) : [];
    const munUnosat = munsUnosat.length;
    // los municipios se nombran, no se cuentan: son tres y decir cuáles vale
    // más que decir cuántos. Enumeración española: «a, b y c».
    const listaUnosat = munsUnosat.length > 1
      ? `${munsUnosat.slice(0, -1).join(", ")} y ${munsUnosat.at(-1)}`
      : munsUnosat.join("");
    out.push({
      id: "satelite",
      nombre: unosat ? "Satélite · Copernicus y UNOSAT" : "Satélite · Copernicus",
      href: "index.html#mapa",
      fecha: entregas.map((e) => e.fecha).sort().at(-1) || null,
      alcance: unosat
        ? `${fmt(zonas)} zonas urbanas y ${fmt(munUnosat)} municipios evaluados`
        : `${fmt(zonas)} zonas urbanas mapeadas`,
      cifras: { edificios_dañados: copernicus + unosat,
                edificios_copernicus: copernicus,
                edificios_unosat: unosat || null,
                edificios_unosat_posibles: unosat ? (uno.posibles || 0) : null },
      // Resumen corto para la línea visible de la tarjeta. El `title` explica;
      // esto se lee sin hover, que es como se lee en un teléfono.
      desglose: unosat
        ? `${fmt(copernicus)} Copernicus + ${fmt(unosat)} UNOSAT, `
          + `${fmt(uno.posibles || 0)} solo «daño posible»`
        : null,
      nota: unosat
        ? `El servicio de emergencias de Copernicus (activación EMSR916) ha `
          + `clasificado ${fmt(copernicus)} edificios en ${fmt(zonas)} zonas `
          + `urbanas; UNITAR-UNOSAT, ${fmt(unosat)} en ${listaUnosat}, `
          + `donde Copernicus no ha cartografiado nada. De esos ${fmt(unosat)}, `
          + `${fmt(uno.posibles || 0)} son «daño posible»: una hipótesis de la `
          + `fuente, sin validar en campo. Se suman porque ninguna de las dos `
          + `mira el municipio de la otra: no hay edificio contado dos veces.`
        : `Edificios con daño clasificado por el servicio de emergencias de `
          + `Copernicus (activación EMSR916) en ${fmt(zonas)} zonas urbanas.`,
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

  return { fmt, fmtProsa, pct, fechaEs, fechaLarga, diaMes,
           estadoMunicipio, ESTADO_MUNICIPIO,
           fraseHomonimos, silencioDePrensa, comparador, norm, cssVar, esc,
           fetchJson, tablaBuscable, tablaHidratada, paginador, metricCards,
           fichaMapa,
           attachTooltip, isLiveblog, bestSnapshot, metricCount, mejorPorDia,
           medioDe, viaGoogleNews, hostDe,
           retrocede, sinAnclas, esCoherente, incoherencias, atribucionOficial,
           esNacional, CIFRAS_BALANCE, TECHO_SALTO,
           disputaDia, comparativaFuentes, OFICIALES_BASE, PUSH_BASE,
           VAPID_PUBLIC_KEY, TELEGRAM_CANAL };
})();
