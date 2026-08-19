/* Página de municipios: la tabla la escribe el build (deploy/render_html.py) y
   aquí solo se filtra. Ninguna cifra de la tabla depende ya de que el navegador
   ejecute JavaScript — que es lo que necesitan los rastreadores de sistemas de
   IA, que no lo ejecutan. */
(async function () {
  const { fmt, pct, fetchJson, tablaHidratada } = window.UI;

  // La tabla no necesita el JSON —viene escrita en el HTML—, pero los textos
  // derivados de la introducción sí: cambian con cada entrega.
  const data = await fetchJson("/data/public/municipios.json");
  if (!data || !data.items || !data.items.length) return;
  document.getElementById("generado").textContent = "Actualizado " + data.generado;

  // derivado, no escrito a mano: la cobertura satelital cambia con cada entrega
  const enAoi = data.items.filter((m) => m.en_aoi_copernicus).length;
  // los homónimos tampoco se escriben a mano: si el RUD registra un tercero,
  // la salvedad debe nombrarlo sola
  const spanHom = document.getElementById("mun-homonimos");
  if (spanHom) spanHom.textContent = window.UI.fraseHomonimos(data.items);

  // Desde el 19-ago-2026 hay un segundo satélite y la frase no puede seguir
  // diciendo que al resto «no lo ha mirado ninguno»: a tres sí, y ninguno de
  // ellos está en zona Copernicus.
  const enUnosat = data.items.filter((m) => m.unosat_edificios != null).length;
  // contado, no restado: un municipio puede estar a la vez en zona Copernicus y
  // evaluado por UNOSAT (lo contempla test_copernicus_manda_sobre_unosat), y la
  // resta mentiría en silencio el día que ocurra
  const sinSatelite = data.items.filter(
    (m) => !m.en_aoi_copernicus && m.unosat_edificios == null).length;
  const cobertura = document.getElementById("mun-cobertura");
  if (cobertura) {
    cobertura.textContent = `Solo ${enAoi} de los ${data.items.length} tienen su ` +
      `cabecera dentro de una zona con producto de daño de Copernicus` +
      (enUnosat
        ? `, y otros ${enUnosat} los ha evaluado UNITAR-UNOSAT edificio a edificio. ` +
          `A los ${sinSatelite} restantes no los ha mirado ningún producto ` +
          `satelital de daño.`
        : `: al resto no lo ha mirado ningún producto satelital de daño.`);
  }

  // ---- damnificados sin una línea de prensa
  // la regla vive en ui.js (silencioDePrensa) y se testea con node: es una
  // afirmación pública, no una frase de esta página. Aquí solo se redacta —y la
  // salvedad viaja pegada a la cifra, no escondida en la metodología.
  const sil = window.UI.silencioDePrensa(data.items);
  const banner = document.getElementById("banner-silencio");
  if (banner && sil) {
    banner.hidden = false;
    banner.innerHTML =
      `<strong>Damnificados sin un solo titular:</strong> ${sil.mudos} de los ` +
      `${data.items.length} municipios con señal tienen personas registradas en el RUD ` +
      `y <strong>cero titulares atribuidos</strong> — ${fmt(sil.personas)} personas.` +
      (sil.ciertos.length
        ? ` En ${sil.ciertos.length} de ellos el monitor sí preguntó —tienen búsqueda ` +
          `propia de prensa y su nombre no admite duda— y no obtuvo nada: ` +
          `${sil.ciertos.join(", ")}, ${fmt(sil.personas_ciertas)} personas registradas` +
          (sil.techo
            ? `, y en ${sil.techo.municipio} son el ${pct(sil.techo.tasa_rud_pct)} ` +
              `de su población.`
            : ".")
        : "") +
      (sil.dudosos
        ? ` En los otros ${sil.dudosos} el cero puede ser del monitor y no de la prensa: ` +
          `su nombre es palabra común o se repite en otro departamento, así que solo ` +
          `se les atribuyen titulares que nombren también su departamento` +
          (sil.sin_busqueda
            ? `, y por ${sil.sin_busqueda} el monitor ni siquiera lanza una búsqueda ` +
              `propia (entraron solos desde el RUD)`
            : "") + `.`
        : "") +
      (sil.sin_atribucion
        ? ` Y otros ${sil.sin_atribucion} ni siquiera tienen cero ` +
          `(${fmt(sil.personas_sin_atribucion)} personas): se llaman igual que un ` +
          `departamento y el monitor no puede atribuirles ningún titular.`
        : "") +
      ` El recuento es del corpus del monitor —GDACS-EMM, feeds regionales abiertos y ` +
      `búsquedas municipales—, no de la prensa colombiana entera, y solo cuenta lo ` +
      `publicado desde el 10 de agosto de 2026. ` +
      `<a href="https://github.com/18orkidea/monitor-terremoto-colombia/blob/main/docs/LIMITACIONES.md" ` +
      `target="_blank" rel="noopener">Qué no puede ver esta cifra</a>.`;
  }


  // etiquetas, colores y explicación vienen de ui.js: la tabla y el mapa deben
  // decir lo mismo del mismo estado



  // ---- filtros: los mismos que la página del RUD, leyendo lo que el
  // generador escribió en cada fila. Los chips están elegidos para enseñar las
  // brechas, no para adornar: dónde no ha mirado nadie y quién no está inscrito.
  const filasTabla = Array.from(
    document.querySelectorAll("#municipios-tabla tbody tr[data-buscar]"));
  const chip = (tr, id) => (tr.dataset.chips || "").split(" ").includes(id);
  const CHIPS = [
    { id: "todos", label: "Todos", test: () => true },
    { id: "sin-satelite", label: "Sin mirar por satélite",
      test: (tr) => chip(tr, "sin-satelite"),
      tip: "Ningún producto satelital ha evaluado sus edificios: ni Copernicus ni UNOSAT" },
    { id: "con-rud", label: "Con damnificados inscritos",
      test: (tr) => chip(tr, "con-rud"),
      tip: "El municipio ya ha registrado damnificados en el RUD de la UNGRD" },
    { id: "sin-rud", label: "Sin registro aún",
      test: (tr) => chip(tr, "sin-rud"),
      tip: "No hay inscripciones en el RUD. Sin registro no significa sin daño: significa que las autoridades locales aún no han censado" },
    { id: "con-ciudadanos", label: "Con reportes de la comunidad",
      test: (tr) => chip(tr, "con-ciudadanos"),
      tip: "Hay reportes ciudadanos georreferenciados dentro del municipio" },
  ];
  let chipActivo = "todos";
  let depto = "";

  const cont = document.getElementById("mun-chips");
  if (cont) {
    cont.innerHTML = CHIPS.map((c) => {
      const n = filasTabla.filter(c.test).length;
      return `<button class="chip${c.id === chipActivo ? " activa" : ""}" data-chip="${c.id}"` +
        `${c.tip ? ` title="${c.tip}"` : ""}>${c.label} (${n})</button>`;
    }).join("");
    cont.onclick = (ev) => {
      const b = ev.target.closest("[data-chip]");
      if (!b) return;
      chipActivo = b.dataset.chip;
      cont.querySelectorAll("[data-chip]").forEach((x) =>
        x.classList.toggle("activa", x.dataset.chip === chipActivo));
      pinta({ reiniciar: true });
    };
  }

  const selDepto = document.getElementById("mun-depto");
  if (selDepto) {
    const cuenta = {};
    filasTabla.forEach((tr) => {
      cuenta[tr.dataset.depto] = (cuenta[tr.dataset.depto] || 0) + 1;
    });
    selDepto.add(new Option(`Todos los departamentos (${filasTabla.length})`, ""));
    // localeCompare, no .sort() a secas: por code point CÓRDOBA caería después
    // de CUNDINAMARCA
    Object.keys(cuenta).sort((a, b) => a.localeCompare(b, "es")).forEach((d) =>
      selDepto.add(new Option(`${d} (${cuenta[d]})`, d)));
    selDepto.onchange = () => { depto = selDepto.value; pinta({ reiniciar: true }); };
  }

  const chipDe = (id) => CHIPS.find((c) => c.id === id) || CHIPS[0];

  // El nombre de cada columna viaja aquí para que la nota diga el criterio de
  // orden vigente sin mantener una lista paralela que se desfase.
  const COLUMNAS = (() => {
    const th = [...document.querySelectorAll("#municipios-tabla thead th")];
    const porNombre = (a, b) =>
      (a.dataset.v0 || "").localeCompare(b.dataset.v0 || "", "es");
    return [
      { nombre: "municipio" }, { nombre: "estado" }, { nombre: "población" },
      { nombre: "edificios evaluados por satélite" }, { nombre: "damnificados del RUD" },
      { nombre: "% de población" }, { nombre: "intensidad percibida" },
      { nombre: "respuestas al cuestionario" }, { nombre: "titulares" },
      { nombre: "fuentes" },
    ].map((c, i) => ({ ...c, th: th[i], desempate: i ? porNombre : undefined }));
  })();

  const POR_PAGINA = 20;

  // La tabla ya viene escrita en el HTML desde el build: aquí solo se filtra,
  // ordena y pagina. Ninguna cifra depende de que el navegador ejecute
  // JavaScript, que es lo que necesitan los rastreadores de sistemas de IA.
  const pinta = tablaHidratada({
    tbody: document.querySelector("#municipios-tabla tbody"),
    input: document.getElementById("mun-buscar"),
    paginado: document.getElementById("mun-paginado"),
    porPagina: POR_PAGINA,
    filtroExtra: (tr) => chipDe(chipActivo).test(tr) && (!depto || tr.dataset.depto === depto),
    columnas: COLUMNAS,
    nota: document.getElementById("mun-nota"),
    notaTexto: (q, visibles, total, orden) => {
      const criterio = orden
        ? `ordenados por ${COLUMNAS[orden.i].nombre} en orden ` +
          `${orden.dir === "asc" ? "ascendente" : "descendente"}`
        : "ordenados por población DANE 2026";
      const cabeza = (q || chipActivo !== "todos" || depto)
        ? `${visibles} de ${total} municipios con señal coinciden con los filtros activos, `
        : `${total} municipios del área de influencia con señal del RUD, prensa, ` +
          `intensidad percibida o satélite, `;
      return cabeza + `${criterio}, de ${POR_PAGINA} en ${POR_PAGINA}. ` +
        `Un guion en la columna de satélite significa que ningún producto lo ha ` +
        `mirado, no que no haya daño.`;
    },
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });

})();
