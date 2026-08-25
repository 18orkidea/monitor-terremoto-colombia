/* Página de balances: las tarjetas del consolidado, la comparativa de fuentes,
   el gráfico de la serie y las filas de la tabla los escribe el build
   (deploy/render_html.py). Aquí queda solo lo que el navegador es el único que
   puede hacer: filtrar la tabla, decir cuántas capturas quedan a la vista y
   marcar la elegida de cada día. Usa los componentes de ui.js. */
(async function () {
  const { fmt, fechaEs, fetchJson, metricCount } = window.UI;
  // El feed se lee del producto propio, no del worker que lo genera: la corrida
  // diaria lo archiva y lo publica, así que la página sigue funcionando el día
  // que ese worker —que vive en una cuenta ajena— se apague.
  const FEED = "/data/public/oficiales.json";
  const btnJson = document.querySelector(".meta a.btn");
  if (btnJson) btnJson.href = FEED;

  const feed = await fetchJson(FEED);
  // Sin feed no hay nada que filtrar, y tampoco nada que avisar: la entradilla,
  // las tarjetas, el gráfico, la comparativa, la tabla y su pie ya llegan
  // escritos desde el build. Antes esta rama pisaba `#balance-resumen` con un
  // «no se han podido cargar los balances» que contradecía a la propia página,
  // que estaba llena de cifras servidas. No se le pone un `if` a la llamada: se
  // le quita el motivo.
  if (!feed) return;

  const items = (feed.items || []).filter((x) => x.search_date);
  const dates = [...new Set(items.map((x) => x.search_date))].sort();
  const levels = [...new Set(items.map((x) => x.source_level || "sin_nivel"))].sort();
  const selDate = document.getElementById("balance-fecha");
  const selLevel = document.getElementById("balance-nivel");
  // el valor sigue siendo la fecha ISO (es una clave); lo que se lee, no
  for (const d of dates) selDate.add(new Option(fechaEs(d), d));
  for (const l of levels) selLevel.add(new Option(labelLevel(l), l));

  // serie con memoria: cada día se elige con el anterior como referencia de
  // estabilidad (un acumulado no retrocede). La regla vive en ui.js y el build
  // la ejecuta con node para escribir las cifras; aquí se vuelve a pedir solo
  // para saber QUÉ captura representa a su día y poder marcarla en la tabla.
  const porDia = window.UI.mejorPorDia(items);

  const resumen = document.getElementById("balance-resumen");
  // Lo que el build sirvió en el pie de la tabla: cuántas capturas hay y
  // cuántas alimentan la serie. Se guarda al arrancar para devolverlo en cuanto
  // se quitan los filtros, en vez de pisarlo con un recuento sin filtrar que
  // diría menos que la frase que ya estaba.
  const pieServido = resumen ? resumen.textContent : "";

  renderTable();

  document.getElementById("balance-buscar").addEventListener("input", renderTable);
  selDate.addEventListener("change", renderTable);
  selLevel.addEventListener("change", renderTable);

  function labelLevel(level) {
    return {
      oficial_comunicacion: "Oficial comunicación",
      oficial_institucional: "Oficial institucional",
      gobierno_local_por_verificar: "Gobierno local por verificar",
      temporal_prensa: "Prensa temporal",
      busqueda_web_temporal: "Web temporal"
    }[level] || level || "Sin nivel";
  }

  function publisherName(item) {
    const p = item.publisher || {};
    return p.name || p.domain || "—";
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

    // Solo el recuento de lo filtrado. La fecha la decía aquí también —«30 de
    // 30 capturas · actualizado el 22 de agosto de 2026», sacada de
    // `generated_at`— y era la fecha de la CORRIDA presentada como la del
    // dato: exactamente la confusión que el sello del encabezado acaba de
    // separar tres centímetros más arriba, en esta misma página. Dos frases
    // sobre la misma fecha diciendo cosas distintas. El sello dice las dos
    // —hasta dónde llega el rastreo y cuándo se construyó— y las dice una sola
    // vez (M2); este contador cuenta capturas, que es lo suyo. Y sin filtros no
    // cuenta nada: devuelve la frase que sirvió el build.
    if (resumen) {
      resumen.textContent = (q || fd || fl)
        ? `${fmt(selected.length)} de ${fmt(items.length)} capturas con los ` +
          `filtros activos`
        : pieServido;
    }

    // filas cuyas cifras alimentan la serie/tarjetas: el snapshot elegido de
    // cada día — marcadas para que la selección sea auditable a simple vista
    const elegidos = new Set(porDia.map((d) => d.item).filter(Boolean));
    // Las filas las escribe el build: aquí solo se muestran las que pasan los
    // filtros y se marca la elegida de cada día. Qué snapshot representa a su
    // día se decide comparando con la víspera (R8), así que esa marca —y solo
    // esa— sigue siendo cosa del navegador.
    //
    // La clave es el día MÁS la URL, no la URL sola. El mismo artículo es la
    // captura elegida de varios días —una cobertura en vivo se vuelve a
    // capturar cada mañana, y un balance de El Tiempo representó a tres días—,
    // así que un índice por URL colapsaba esas filas: seis de las doce elegidas
    // se quedaban sin su marca y la fila que perdía el sitio en el índice ya no
    // atendía a ningún filtro. `filas_balances` escribe las dos mitades en cada
    // `<tr>` precisamente porque una captura son las dos.
    const tbody = document.querySelector("#balance-table tbody");
    const claveDe = (it) =>
      `${it.search_date || ""}|${it.publication_url || it.url || "#"}`;
    const porClave = new Map(Array.from(tbody.rows)
      .filter((tr) => tr.dataset.url)
      .map((tr) => [`${tr.dataset.fecha || ""}|${tr.dataset.url}`, tr]));
    const visibles = new Set(selected.map(claveDe));
    porClave.forEach((tr, clave) => {
      tr.hidden = !visibles.has(clave);
      const item = selected.find((it) => claveDe(it) === clave);
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
})();
