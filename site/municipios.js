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
    if (m.n_noticias)
      return `<a href="noticias.html?municipio=${encodeURIComponent(m.municipio)}" style="color:var(--s1)">${fmt(m.n_noticias)}</a>`;
    // Un cero en un municipio que exige departamento no es «nadie habló de él»:
    // puede haber titulares con su nombre que el monitor no se atreve a
    // atribuirle. Viterbo es el caso: existe un artículo italiano que lo
    // nombra, pero sin «Caldas» en el texto no cuenta.
    if (m.requiere_depto)
      return `<span title="Su nombre es palabra común, lugar extranjero o se ` +
        `repite en otro departamento: solo se le atribuyen titulares que ` +
        `nombren también ${m.departamento}. Puede haber prensa que el monitor ` +
        `no pueda asignarle.">0</span>`;
    return fmt(0);
  };

  // UNOSAT: donde no ha mirado no hay cero, hay ausencia (R3). El desglose
  // separa lo que la fuente da por observado de lo que marca como hipótesis.
  const unosatCelda = (m) => {
    if (m.unosat_edificios == null) return "—";
    const otros = m.unosat_otros_eventos
      ? ` <span title="UNOSAT los incluye en la misma capa pero los etiqueta ` +
        `con otro código de evento, así que no se suman al terremoto." ` +
        `style="color:var(--warning)">+${fmt(m.unosat_otros_eventos)}</span>`
      : "";
    return `${fmt(m.unosat_edificios)} <span style="color:var(--muted)">` +
      `(${fmt(m.unosat_observados)})</span>${otros}`;
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
        `<td class="num">${unosatCelda(m)}</td>` +
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
