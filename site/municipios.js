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



  // La tabla ya viene escrita en el HTML desde el build (deploy/render_html.py):
  // aquí solo se filtra. Ninguna cifra de esta página depende de que el navegador
  // ejecute JavaScript, que es lo que necesitan los rastreadores de sistemas de IA.
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

})();
