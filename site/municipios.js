/* Página de municipios: tabla completa del área de influencia con buscador,
   ordenada por población (DANE 2026). Usa los componentes de ui.js. */
(async function () {
  const { fmt, pct, fetchJson, tablaBuscable } = window.UI;
  const base = "../data/public/";
  const data = await fetchJson(base + "municipios.json");
  if (!data || !data.items || !data.items.length) {
    document.getElementById("mun-nota").textContent =
      "Sin datos: ejecuta primero python ingest/run_daily.py (o sirve el repo por HTTP).";
    return;
  }
  document.getElementById("generado").textContent = "Actualizado " + data.generado;

  // derivado, no escrito a mano: la cobertura satelital cambia con cada entrega
  const enAoi = data.items.filter((m) => m.en_aoi_copernicus).length;
  // los homónimos tampoco se escriben a mano: si el RUD registra un tercero,
  // la salvedad debe nombrarlo sola
  const homs = data.items.filter((m) => m.homonimo_de_departamento)
    .map((m) => `${m.municipio} (${m.departamento})`);
  const spanHom = document.getElementById("mun-homonimos");
  if (spanHom) {
    spanHom.textContent = homs.length
      ? ` —salvo ${homs.join(" y ")}, que se llaman igual que un departamento y a ` +
        `los que el monitor no puede atribuir titulares.`
      : "";
  }

  const cobertura = document.getElementById("mun-cobertura");
  if (cobertura) {
    cobertura.textContent = `Solo ${enAoi} de los ${data.items.length} tienen su ` +
      `cabecera dentro de una zona con producto de daño de Copernicus: al resto no lo ` +
      `ha mirado ningún producto satelital de daño.`;
  }

  const rows = [...data.items].sort((a, b) =>
    (b.poblacion_2026 || 0) - (a.poblacion_2026 || 0));

  // etiquetas, colores y explicación vienen de ui.js: la tabla y el mapa deben
  // decir lo mismo del mismo estado
  const estadoDe = (m) => window.UI.estadoMunicipio(m.estado);

  // Prensa: los homónimos de un departamento no reciben atribución por texto,
  // así que su celda es ausencia de dato, no un cero (R3)
  const prensaCelda = (m) => {
    if (m.homonimo_de_departamento) {
      return `<span title="Se llama igual que un departamento: el monitor no le ` +
        `atribuye titulares, porque no puede distinguir el municipio del ` +
        `departamento. No es que no haya prensa — es que no se puede afirmar ` +
        `cuál le corresponde.">—</span>`;
    }
    return m.n_noticias
      ? `<a href="noticias.html?municipio=${encodeURIComponent(m.municipio)}" style="color:var(--s1)">${fmt(m.n_noticias)}</a>`
      : fmt(0);
  };

  tablaBuscable({
    tbody: document.querySelector("#municipios-tabla tbody"),
    input: document.getElementById("mun-buscar"),
    rows,
    top: rows.length,   // la lista es corta: se muestran todos y el buscador filtra
    texto: (m) => `${m.municipio} ${m.departamento}`,
    fila: (m) => {
      const [estado, color, explica] = estadoDe(m);
      return `<tr>` +
        `<td><a href="index.html#mapa" style="color:inherit;text-decoration:none"><strong>${m.municipio}</strong></a>` +
        `<br><span style="color:var(--muted)">${m.departamento}</span></td>` +
        `<td><span class="badge" style="--bc:var(${color})" title="${explica}">${estado}</span></td>` +
        `<td class="num" title="DANE PPED municipal por área, 2026">${fmt(m.poblacion_2026)}</td>` +
        `<td class="num">${m.rud_personas == null ? "—" : fmt(m.rud_personas)}</td>` +
        `<td class="num">${pct(m.tasa_rud_pct)}</td>` +
        `<td class="num">${fmt(m.dyfi_max_cdi, 1)}</td>` +
        `<td class="num">${fmt(m.dyfi_respuestas)}</td>` +
        `<td class="num">${prensaCelda(m)}</td>` +
        `<td>${(m.fuentes || []).join(", ") || "—"}</td></tr>`;
    },
    nota: document.getElementById("mun-nota"),
    notaTexto: (q, visibles, total) => q
      ? `${visibles} de ${total} municipios con señal coinciden con la búsqueda.`
      : `${total} municipios del área de influencia con señal del RUD, prensa o ` +
        `intensidad percibida, ordenados por población DANE 2026.`,
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });
})();
