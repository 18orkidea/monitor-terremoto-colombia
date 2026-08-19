/* Página de municipios: la tabla la escribe el build (deploy/render_html.py) y
   aquí solo se filtra. Ninguna cifra de la tabla depende ya de que el navegador
   ejecute JavaScript — que es lo que necesitan los rastreadores de sistemas de
   IA, que no lo ejecutan. */
(async function () {
  const { fetchJson, tablaHidratada } = window.UI;

  tablaHidratada({
    tbody: document.querySelector("#municipios-tabla tbody"),
    input: document.getElementById("mun-buscar"),
    nota: document.getElementById("mun-nota"),
    notaTexto: (q, visibles, total) => q
      ? `${visibles} de ${total} municipios con señal coinciden con la búsqueda.`
      : `${total} municipios del área de influencia con señal del RUD, prensa o ` +
        `intensidad percibida, ordenados por población DANE 2026.`,
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });

  // Los dos textos derivados de la intro siguen viniendo del JSON: cambian con
  // cada entrega y aún no se prerenderizan (pendiente en docs/SEO-GEO.md).
  const data = await fetchJson("../data/public/municipios.json");
  if (!data || !data.items || !data.items.length) return;

  document.getElementById("generado").textContent = "Actualizado " + data.generado;

  const spanHom = document.getElementById("mun-homonimos");
  if (spanHom) spanHom.textContent = window.UI.fraseHomonimos(data.items);

  const cobertura = document.getElementById("mun-cobertura");
  if (cobertura) {
    const enAoi = data.items.filter((m) => m.en_aoi_copernicus).length;
    cobertura.textContent = `Solo ${enAoi} de los ${data.items.length} tienen su ` +
      `cabecera dentro de una zona con producto de daño de Copernicus: al resto no lo ` +
      `ha mirado ningún producto satelital de daño.`;
  }
})();
