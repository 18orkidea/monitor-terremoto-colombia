/* Página de municipios: tabla completa del área de influencia con buscador,
   ordenada por población (DANE 2026). Usa los componentes de ui.js. */
(async function () {
  const { fmt, fetchJson, tablaBuscable } = window.UI;
  const base = "../data/public/";
  const data = await fetchJson(base + "municipios.json");
  if (!data || !data.items || !data.items.length) {
    document.getElementById("mun-nota").textContent =
      "Sin datos: ejecuta primero python ingest/run_daily.py (o sirve el repo por HTTP).";
    return;
  }
  document.getElementById("generado").textContent = "Actualizado " + data.generado;

  const rows = [...data.items].sort((a, b) =>
    (b.poblacion_2026 || 0) - (a.poblacion_2026 || 0));

  const estadoDe = (m) => m.en_aoi_copernicus ? ["En AOI Copernicus", "--s1"] :
    ((m.dyfi_max_cdi || 0) >= 6 ? ["Fuera de AOI · intensidad alta", "--warning"] :
      (m.n_noticias ? ["Fuera de AOI · mencionado", "--s2"] :
        ["Fuera de AOI · intensidad sentida", "--s2"]));

  tablaBuscable({
    tbody: document.querySelector("#municipios-tabla tbody"),
    input: document.getElementById("mun-buscar"),
    rows,
    top: rows.length,   // la lista es corta: se muestran todos y el buscador filtra
    texto: (m) => `${m.municipio} ${m.departamento}`,
    fila: (m) => {
      const [estado, color] = estadoDe(m);
      return `<tr>` +
        `<td><a href="index.html#mapa" style="color:inherit;text-decoration:none"><strong>${m.municipio}</strong></a>` +
        `<br><span style="color:var(--muted)">${m.departamento}</span></td>` +
        `<td><span class="badge" style="--bc:var(${color})">${estado}</span></td>` +
        `<td class="num" title="DANE PPED municipal por área, 2026">${fmt(m.poblacion_2026)}</td>` +
        `<td class="num">${fmt(m.dyfi_max_cdi, 1)}</td>` +
        `<td class="num">${fmt(m.dyfi_respuestas)}</td>` +
        `<td class="num">${m.n_noticias ? `<a href="noticias.html?municipio=${encodeURIComponent(m.municipio)}" style="color:var(--s1)">${fmt(m.n_noticias)}</a>` : "—"}</td>` +
        `<td>${(m.fuentes || []).join(", ") || "—"}</td></tr>`;
    },
    nota: document.getElementById("mun-nota"),
    notaTexto: (q, visibles, total) => q
      ? `${visibles} de ${total} municipios con señal coinciden con la búsqueda.`
      : `${total} municipios del área de influencia con señal de prensa, intensidad o ` +
        `satélite, ordenados por población DANE 2026.`,
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });
})();
