/* Página de municipios: la tabla la escribe el build (deploy/render_html.py) y
   aquí solo se filtra. Ninguna cifra de la tabla depende ya de que el navegador
   ejecute JavaScript — que es lo que necesitan los rastreadores de sistemas de
   IA, que no lo ejecutan. */
(async function () {
  const { fmt, fmtProsa, pct, fechaLarga, fetchJson, tablaHidratada } = window.UI;

  // La tabla no necesita el JSON —viene escrita en el HTML—, pero los textos
  // derivados de la introducción sí: cambian con cada entrega.
  const data = await fetchJson("/data/public/municipios.json");
  if (!data || !data.items || !data.items.length) return;
  document.getElementById("generado").textContent =
    "Actualizado el " + fechaLarga(data.generado);

  // los homónimos tampoco se escriben a mano: si el RUD registra un tercero,
  // la salvedad debe nombrarlo sola
  const spanHom = document.getElementById("mun-homonimos");
  if (spanHom) spanHom.textContent = window.UI.fraseHomonimos(data.items);

  // derivado, no escrito a mano: la cobertura satelital cambia con cada entrega.
  // Ya son TRES los servicios que miran —Copernicus, UNOSAT e ICube-SERTIT— y
  // uno solo basta para que el municipio esté mirado: la frase pregunta por
  // cualquiera de ellos, no por el primero que llegó.
  const miradoPorSatelite = (m) => !!m.en_aoi_copernicus
    || m.unosat_edificios != null || m.sertit_edificios != null;
  // contados los dos, no restado uno: un municipio puede estar a la vez en zona
  // Copernicus y evaluado por otro servicio (Pereira y Cali lo están), y sumar
  // las coberturas contaría dos veces el mismo municipio
  const conSatelite = data.items.filter(miradoPorSatelite).length;
  const sinSatelite = data.items.filter((m) => !miradoPorSatelite(m)).length;
  const cobertura = document.getElementById("mun-cobertura");
  if (cobertura) {
    cobertura.textContent =
      `A ${fmtProsa(sinSatelite)} de los ${data.items.length} no los ha mirado ningún satélite` +
      (conSatelite ? `; los otros ${fmtProsa(conSatelite)}, sí.` : ".");
  }

  // ---- damnificados sin una línea de prensa
  // La regla vive en ui.js (silencioDePrensa) y se testea con node: es una
  // afirmación pública, no una frase de esta página. Aquí solo se redacta.
  // La cifra va sola y en corto; las salvedades —que son muchas y todas
  // importan— quedan a un clic, no delante de quien solo quiere el dato.
  const sil = window.UI.silencioDePrensa(data.items);
  const banner = document.getElementById("banner-silencio");
  if (banner && sil) {
    banner.hidden = false;
    const ciertos = sil.ciertos.length
      ? ` En ${fmtProsa(sil.ciertos.length)} el monitor sí buscó ` +
        `y no encontró nada: ${sil.ciertos.join(", ")}.`
      : "";
    const detalle = [];
    detalle.push(`<p>En total, ${fmtProsa(sil.mudos)} municipios tienen damnificados ` +
      `inscritos y ningún titular atribuido (${fmt(sil.personas)} personas). De ellos, ` +
      `${fmtProsa(sil.ciertos.length)} son afirmables: el monitor sí preguntó por su nombre ` +
      `y no obtuvo nada.</p>`);
    if (sil.dudosos)
      detalle.push(`<p>En los otros ${fmtProsa(sil.dudosos)} el cero puede ser del monitor y no de ` +
        `la prensa: su nombre es palabra común o se repite en otro departamento, así que ` +
        `solo se les atribuyen titulares que nombren también su departamento` +
        (sil.sin_busqueda
          ? `, y por ${fmtProsa(sil.sin_busqueda)} ni siquiera se lanza una búsqueda propia (entraron ` +
            `solos desde el registro oficial)`
          : "") + `.</p>`);
    if (sil.sin_atribucion)
      detalle.push(`<p>Aparte de esos ${fmtProsa(sil.mudos)}, hay ` +
        `${fmtProsa(sil.sin_atribucion)} municipios más (${fmt(sil.personas_sin_atribucion)} ` +
        `personas) que ni siquiera tienen un cero: se llaman igual que un departamento y no ` +
        `se les puede atribuir ningún titular.</p>`);
    detalle.push(`<p>El recuento sale de lo que rastrea el monitor —el sistema europeo de ` +
      `alertas GDACS, canales regionales abiertos y búsquedas municipio a municipio—, no de ` +
      `la prensa colombiana entera, y solo cuenta lo publicado desde el 10 de agosto de 2026. ` +
      `<a href="https://github.com/18orkidea/monitor-terremoto-colombia/blob/main/docs/LIMITACIONES.md" ` +
      `target="_blank" rel="noopener">Qué no puede ver esta cifra</a>.</p>`);
    // El titular lleva SOLO la cifra afirmable. Los 18 municipios «mudos»
    // incluyen 13 en los que el cero puede ser del monitor y no de la prensa:
    // publicarlos en negrita sería la ausencia leída como cero, que es
    // exactamente lo que este monitor le reprocha a las fuentes que audita.
    const ciertas = fmt(sil.personas_ciertas);
    const techo = sil.techo
      ? ` En ${window.UI.esc(sil.techo.municipio)} son el ${pct(sil.techo.tasa_rud_pct)} del municipio.`
      : "";
    banner.innerHTML =
      `<p><strong>El monitor buscó prensa en ${fmtProsa(sil.ciertos.length)} municipios ` +
      `con damnificados inscritos y no encontró ni un titular</strong> — ${ciertas} ` +
      `personas: ${sil.ciertos.join(", ")}.${techo}</p>` +
      `<p class="note">En otros ${fmtProsa(sil.dudosos)} municipios con damnificados y cero ` +
      `titulares no se puede afirmar lo mismo: el cero puede ser del monitor. ` +
      `<details><summary>Por qué, y qué no puede ver esta cifra</summary>${detalle.join("")}` +
      `</details></p>`;
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
      tip: "Ningún producto satelital ha evaluado sus edificios: ni Copernicus, ni UNOSAT, ni ICube-SERTIT" },
    { id: "con-rud", label: "Con damnificados inscritos",
      test: (tr) => chip(tr, "con-rud"),
      tip: "El municipio ya ha inscrito damnificados en el Registro Único de Damnificados (RUD)" },
    { id: "sin-rud", label: "Sin registro aún",
      test: (tr) => chip(tr, "sin-rud"),
      tip: "No hay inscripciones en el registro oficial de damnificados. Sin registro no significa sin daño: significa que las autoridades locales aún no lo han cargado" },
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
        : "ordenados por población proyectada para 2026";
      const cabeza = (q || chipActivo !== "todos" || depto)
        ? `${visibles} de ${total} municipios con señal coinciden con los filtros activos, `
        : `${total} municipios del área de influencia con señal del registro oficial de ` +
          `damnificados, la prensa, la intensidad percibida o el satélite, `;
      return cabeza + `${criterio}, de ${POR_PAGINA} en ${POR_PAGINA}. ` +
        `Un guion en la columna de satélite significa que ningún producto lo ha ` +
        `mirado, no que no haya daño.`;
    },
    vacio: "Sin coincidencias entre los municipios con señal registrada.",
  });

})();
