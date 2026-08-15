/* Página de titulares: lista completa con filtros por zona, fuente y texto. */
(async function () {
  let data;
  try {
    const r = await fetch("../data/public/noticias.json");
    data = await r.json();
  } catch {
    document.getElementById("resumen").textContent =
      "Sin datos (sirve el repo por HTTP y ejecuta el pipeline).";
    return;
  }
  const items = data.items || [];
  const AOI_ES = {
    "Northern Cali": "Cali Norte", "Cali Center": "Cali Centro",
    "Quibdo Centre": "Quibdó Centro", "Western Colombia": "Occidente de Colombia",
    "Pereira": "Pereira", "Istmina": "Istmina", "Buenaventura": "Buenaventura",
  };
  const aoiEs = (n) => AOI_ES[n] || n;
  const aoiLabel = (n) => {
    const es = aoiEs(n);
    return es === n ? n : `${es} (${n})`;
  };
  const aois = [...new Set(items.flatMap((n) => n.aois || []))].sort();
  const origenes = [...new Set(items.map((n) => n.origen))].sort();
  const selA = document.getElementById("f-aoi");
  const selO = document.getElementById("f-origen");
  for (const a of aois) selA.add(new Option(aoiLabel(a), a));
  for (const o of origenes) selO.add(new Option(o, o));

  // permite enlazar directo: noticias.html#aoi=Pereira
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("aoi")) selA.value = hash.get("aoi");

  const lista = document.getElementById("lista");
  const resumen = document.getElementById("resumen");
  const MAX = 400;

  function render() {
    const q = document.getElementById("buscar").value.toLowerCase();
    const fa = selA.value, fo = selO.value;
    const sel = items.filter((n) =>
      (!q || (n.titulo || "").toLowerCase().includes(q)) &&
      (!fa || (n.aois || []).includes(fa)) &&
      (!fo || n.origen === fo));
    resumen.textContent =
      `${sel.length.toLocaleString("es-CO")} de ${items.length.toLocaleString("es-CO")} titulares` +
      (sel.length > MAX ? ` — mostrando los ${MAX} más recientes` : "") +
      ` · actualizado ${data.generado}`;
    lista.innerHTML = sel.slice(0, MAX).map((n) =>
      `<li><span class="meta-n">${(n.fecha || "").slice(0, 16).replace("T", " ")} · ${n.medio || n.origen}</span>` +
      (n.aois || []).map((a) => `<span class="chip" title="${a}">${aoiEs(a)}</span>`).join("") +
      `<br><a href="${n.url}" target="_blank" rel="noopener">${n.titulo}</a></li>`).join("") ||
      "<li>Nada que mostrar con estos filtros.</li>";
  }
  document.getElementById("buscar").addEventListener("input", render);
  selA.addEventListener("change", render);
  selO.addEventListener("change", render);
  render();
})();
