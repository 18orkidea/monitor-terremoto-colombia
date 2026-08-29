/* Monitor de brechas — frontend sin build. Lee data/public/*. Usa ui.js. */
(async function () {
  const css = window.UI.cssVar;
  const ESTADO_COLOR = {
    coincide: css("--good"), prensa: css("--s1"), ciudadano: css("--s7"),
    pendiente: css("--warning"), no_comparable: css("--muted"),
  };
  const fmt = (n) => window.UI.fmt(n, 1);
  const ficha = window.UI.fichaMapa;   // único constructor de globos (ui.js)
  /* Cada servicio satelital fecha sus imágenes a su manera —UNOSAT en
     AAAAMMDD, ICube-SERTIT en «AAAA/MM/DD HH:MM UTC»— y el sitio escribe las
     fechas de una sola manera (UI.fechaEs). La hora se conserva cuando la
     fuente la da: dos pasadas del mismo día no retratan lo mismo. */
  const fechaImagen = (s) => {
    const m = /^(\d{4})[/-]?(\d{2})[/-]?(\d{2})(?:[ T](\d{2}:\d{2}))?\s*(UTC)?/
      .exec(String(s || ""));
    if (!m) return s || null;
    const dia = window.UI.fechaEs(`${m[1]}-${m[2]}-${m[3]}`);
    return m[4] ? `${dia}, ${m[4]}${m[5] ? " UTC" : ""}` : dia;
  };

  // ---- traducción de etiquetas que llegan en inglés desde las fuentes.
  // El nombre original se conserva (title/paréntesis) para poder identificarlo
  // en los productos de Copernicus. Los nombres de zona los pone ui.js: los
  // leen también los titulares y el prerenderizado del build.
  const aoiEs = window.UI.aoiEs;
  const aoiLabel = (n) => {
    const es = aoiEs(n);
    return es === n ? n : `${es} <span style="color:var(--muted)">(${n})</span>`;
  };
  const DICT = {
    // tipos de objeto (capas Copernicus)
    "Residential": "Residencial", "Residential Buildings": "Edificios residenciales",
    "11-Residential Buildings": "Edificios residenciales",
    "Main roads": "Vías principales", "Local Road": "Vía local",
    "Secondary Road": "Vía secundaria", "Primary Road": "Vía primaria",
    "211-Highways, Streets and Roads": "Autopistas, calles y carreteras",
    "21120-Primary Road": "Vía primaria", "21130-Secondary Road": "Vía secundaria",
    "21140-Local Road": "Vía local",
    "Building point": "Punto de edificio", "Photo-interpretation": "Fotointerpretación",
    "Not Applicable": "No aplica", "Unknown": "Desconocido",
    "Destroyed": "Destruido", "Damaged": "Dañado",
    "Possibly damaged": "Posiblemente dañado",
    "GRA": "Evaluación de daños", "GRM": "Seguimiento de daños",
    "DEL": "Delineación", "REF": "Referencia", "FEP": "Primera estimación",
    // categorías de activación (índice Copernicus)
    "Earthquake": "Terremoto", "Flood": "Inundación", "Wildfire": "Incendio forestal",
    "Storm": "Tormenta", "Landslide": "Deslizamiento",
    "Volcanic eruption": "Erupción volcánica",
  };
  /* Clases de fuente que documentan un municipio (no son medios: son las
     miradas que lo han registrado). */
  const FUENTE_ES = { prensa: "prensa", rud: "registro municipal (RUD)",
                      dyfi: "intensidad percibida (DYFI)",
                      unosat: "evaluación satelital (UNOSAT)",
                      sertit: "evaluación satelital (ICube-SERTIT)" };
  const t = (s) => DICT[s] || s;
  /* Término traducido conservando entre paréntesis el original: es el que
     aparece en los productos descargables de la fuente, y sin él no se puede
     localizar allí lo que el mapa está enseñando. */
  const conOriginal = (s) => t(s) === s ? t(s)
    : `${t(s)} <span style="color:var(--muted)">(${s})</span>`;
  const j = window.UI.fetchJson;
  const base = "/data/public/";
  /* AL ABRIR SE PIDEN DOS FICHEROS Y NI UNO MÁS.
     La portada bajaba 4.219 KB en trece peticiones para dibujar 163: las doce
     capas del mapa se descargaban enteras y solo una se encendía —desde que la
     portada abre por la ausencia, el resto llega apagado—. `not_analysed.geojson`
     pesa él solo 2.174 KB, la mitad del total, y no se dibuja al abrir. Este
     sitio se lee sobre todo en móvil y en Colombia: descargarlo era cobrarle a
     quien lee un mapa que nadie le ha pedido.
     Desde aquí cada capa pide su fichero cuando el lector la enciende —da igual
     si desde su chip o desde el control de Leaflet— y lo ya pedido no se vuelve
     a pedir: la caché es la promesa, no el resultado, así que dos clics
     seguidos comparten una sola descarga en vuelo.
     `alerts.json` ya no se pide: las alertas las escribe el build (fase 6), y
     pedirlo aquí era descargarlo para no usarlo. `oficiales.json` y
     `hitos_monitor.json` tampoco: solo alimentaban la cronología, que desde la
     fase 6c la escribe el build en referencia.html. */
  const pedidos = {};
  const pide = (fichero) => (pedidos[fichero] =
    pedidos[fichero] || j(base + fichero));
  /* La capa que abre encendida —la ausencia— se adelanta EN PARALELO con el
     monitor y por la misma caché que todas las demás: cuando el bloque de
     arranque la encienda, su fichero ya estará en el aire y no le costará un
     viaje de red entero por detrás del primero. */
  pide("municipios_mapa.json");
  const mon = await pide("monitor.json");
  // ---- banda de brechas oficiales
  // La banda YA VIENE ESCRITA desde el build (deploy/render_html.py::banda_brechas).
  // Es el resumen más citable de la portada y llegaba vacía a quien no ejecuta
  // JavaScript, que es todo rastreador de sistemas de IA. La redacción vive allí
  // y en ningún otro sitio; aquí solo se refresca lo que depende del reloj de
  // quien lee y no de la fecha del build: cuántos días lleva callada cada fuente.
  // Va antes de comprobar los datos porque no los necesita: aunque el monitor no
  // cargue, la cuenta de días del silencio oficial sigue siendo cierta y actual.
  // floor, NO round: una fecha ISO sin hora se interpreta a medianoche UTC, así
  // que a media mañana en Colombia el cociente cruza el medio día y `round`
  // sumaba uno. La banda daba entonces dos cifras del mismo silencio —1.330 en
  // el HTML servido, 1.331 en pantalla— y la de pantalla cambiaba sola durante
  // el día. Con floor son días completos transcurridos, que es lo que dice la
  // frase y lo que cuenta `_dias_entre` en el build.
  for (const span of document.querySelectorAll("#banner-brechas [data-dias-desde]")) {
    const desde = new Date(span.dataset.diasDesde);
    if (!isNaN(desde.getTime())) {
      span.textContent = fmt(Math.floor((Date.now() - desde) / 864e5));
    }
  }

  if (!mon) {
    // El aviso se antepone y NO borra la banda: el resumen de brechas ya viene
    // escrito desde el build y sigue siendo cierto aunque el mapa no cargue. Por
    // eso nombra QUÉ ha fallado y avala lo de abajo: un «no se han podido cargar
    // los datos» a secas, en la misma caja amarilla y encima de las cifras,
    // invita a leerlas como sospechosas.
    document.getElementById("banner-brechas").insertAdjacentHTML("afterbegin",
      !/^https?:$/.test(location.protocol)
        ? "<p role=\"status\"><strong>Esta página está abierta como un archivo del " +
          "disco:</strong> el navegador bloquea la carga de datos por seguridad. " +
          "Ábrela en <a href=\"https://datosdelterremoto.org/\">datosdelterremoto.org</a>. " +
          "El resumen de aquí abajo sí se lee: viaja escrito en la página.</p>"
        : "<p role=\"status\"><strong>No se han podido cargar el mapa ni las " +
          "tablas:</strong> vuelve a intentarlo en unos minutos. El resumen de aquí " +
          "abajo se escribió en la última actualización del monitor y sigue siendo " +
          "válido.</p>");
    return;
  }

  // ---- mapa
  const map = L.map("map");
  window.__monitorMap = map;   // depuración y extensiones
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "© OpenStreetMap", maxZoom: 18 }).addTo(map);

  /* Colombia entera al abrir, y una sola capa encendida: la ausencia.
     Es una decisión EDITORIAL, no un encuadre cómodo. Abrir ajustado a las
     zonas que analizó Copernicus, con las cinco capas puestas, contesta «dónde
     han mirado los satélites»; abrir con el país entero y solo «Solo en el
     RUD» contesta «a cuánta gente no ha mirado nadie», que es la tesis de este
     monitor. **La ausencia se lee antes que la evidencia**, y las otras cuatro
     miradas las enciende el lector cuando quiere compararlas. */
  const VISTA_NACIONAL = { centro: [4.6, -74.3], zoom: 6 };

  /* ---- una capa se pide cuando el lector la enciende, no antes ------------
     Cada capa del mapa es una RANURA: un grupo vacío de Leaflet que existe
     desde el primer momento —para que el control y los chips puedan
     accionarla— y un fichero que solo se pide la primera vez que alguien la
     enciende.

     El grupo NO cambia de identidad al llenarse, y eso es lo que deja intacto
     el reflejo de los chips: `capas.some((c) => map.hasLayer(c))` sigue
     queriendo decir lo mismo que antes —esta capa está puesta en el mapa—,
     tenga ya sus rasgos dentro o los esté esperando. Si en su lugar la capa se
     construyera al llegar el fichero, `hasLayer` diría «no» durante toda la
     descarga y la resincronización de `overlayadd`/`overlayremove` apagaría el
     chip que el lector acaba de encender.

     Se escucha el alta DEL GRUPO y no el clic del chip: las dos maneras de
     encender una capa —el chip y el control de Leaflet— pasan así por el mismo
     sitio, y ninguna se queda sin descargar. */
  const RANURAS = [];
  const ranuraDe = new Map();          // capa del mapa → su ranura
  let refrescaChips = () => {};        // lo enchufa `conectarChips`, más abajo
  const diferida = (fichero, construye, opciones) => {
    const o = opciones || {};
    const grupo = L.layerGroup();
    const r = {
      grupo, fichero, construye, clave: null, base: null, rotulo: null,
      promesa: null, viva: true,
      // Tres rótulos no llevan cifra hoy y no van a estrenarla por la puerta
      // de atrás: el número solo aparece donde ya estaba.
      cifra: o.cifra !== false,
      // La ausencia es el contexto sobre el que se lee la evidencia: al llegar
      // se va al fondo para no taparla.
      fondo: !!o.fondo,
    };
    RANURAS.push(r);
    ranuraDe.set(grupo, r);
    grupo.on("add", () => { enciende(r); });
    return grupo;
  };

  /* Que una capa viene en camino tiene que VERSE. Pulsar un chip y quedarse dos
     segundos con la pantalla quieta se lee como una avería, y quien no sabe que
     está descargando vuelve a pulsar. Se dice en dos sitios porque hay dos
     maneras de encenderla: en el chip, con `aria-busy` —que un lector de
     pantalla anuncia— y el pulso que le pone la hoja de estilos; y en un aviso
     sobre el mapa, que es lo único que ve quien la encendió desde el control de
     Leaflet. El mismo aviso cuenta después el fallo de red, que es la otra cosa
     que no puede pasar en silencio (R13). */
  const enVuelo = new Set();
  let fallo = "";
  let cajaAviso = null;
  const pintaAviso = () => {
    if (!cajaAviso) {
      const marco = document.querySelector(".marco-mapa");
      if (!marco) return;
      cajaAviso = document.createElement("p");
      cajaAviso.className = "aviso-capas";
      cajaAviso.setAttribute("role", "status");
      cajaAviso.setAttribute("aria-live", "polite");
      marco.appendChild(cajaAviso);
    }
    const viajando = [...enVuelo];
    const texto = viajando.length === 1 ? `Cargando «${viajando[0]}»…`
      : viajando.length ? `Cargando ${fmt(viajando.length)} capas…`
      : fallo;
    cajaAviso.textContent = texto;
    cajaAviso.hidden = !texto;
    cajaAviso.classList.toggle("aviso-capas--fallo", !viajando.length && !!fallo);
  };
  const avisa = (texto, esFallo) => { fallo = esFallo ? texto : ""; pintaAviso(); };
  const marcarCarga = (r, si) => {
    if (si) enVuelo.add(r.base); else enVuelo.delete(r.base);
    // Un chip manda sobre VARIAS capas —«Copernicus» son seis—: sigue ocupado
    // mientras alguna de las suyas viaje, no solo mientras viaje esta.
    const chip = r.clave && document.querySelector(
      `.chip[data-capa="${r.clave}"]`);
    if (chip) {
      const suyas = (porCapa[r.clave] || []).map((c) => ranuraDe.get(c));
      chip.setAttribute("aria-busy", String(
        suyas.some((x) => x && enVuelo.has(x.base))));
    }
    pintaAviso();
  };

  /* Una ranura que se retira no puede dejar rastro en ninguna de las tres
     superficies que la accionaban: el control, el mapa y su chip. Es la misma
     regla que ya gobernaba al chip huérfano —«un chip sin capa se retira antes
     que quedarse como control muerto»—, aplicada ahora también cuando la capa
     resulta estar vacía DESPUÉS de haberla pedido, que es lo único que se
     puede saber sin descargarla. */
  const retira = (r, motivo) => {
    r.viva = false;
    map.removeLayer(r.grupo);
    for (const clave of Object.keys(porCapa)) {
      const i = porCapa[clave].indexOf(r.grupo);
      // `splice` y no un array nuevo: `conectarChips` se guardó ESTE array.
      if (i >= 0) porCapa[clave].splice(i, 1);
    }
    pintarControl();
    refrescaChips();
    avisa(motivo, true);
  };

  /* Lo que pasa entre el clic y el dibujo, que es lo que antes no pasaba nunca.
     `r.promesa` es la caché: dos clics seguidos sobre el mismo chip descargan
     UNA vez, y encender, apagar y volver a encender no vuelve a pedir nada.
     Cuando el fichero no llega, la ranura se limpia entera —promesa y
     petición— para que el reintento vuelva a pedirlo de verdad, y la capa sale
     del mapa: un chip en `aria-pressed="true"` sobre una capa que no existe es
     el control mintiendo. */
  async function enciende(r) {
    if (!r.viva || r.promesa) return r.promesa;
    r.promesa = (async () => {
      marcarCarga(r, true);
      const datos = await pide(r.fichero);
      marcarCarga(r, false);
      if (!datos) {
        r.promesa = null;
        delete pedidos[r.fichero];
        map.removeLayer(r.grupo);
        avisa(`No se ha podido cargar «${r.base}»: vuelve a encenderla en unos `
              + "minutos. El resto del mapa no depende de ella.", true);
        return;
      }
      const capa = r.construye(datos);
      const n = capa && capa.getLayers ? capa.getLayers().length : 0;
      if (!n) { retira(r, `«${r.base}» no trae ningún dato que dibujar.`); return; }
      r.grupo.addLayer(capa);
      if (r.fondo && capa.bringToBack) capa.bringToBack();
      // La cifra del rótulo cuenta lo que se PINTA, no lo que trae el fichero:
      // por eso no se puede escribir antes de haberlo dibujado.
      if (r.cifra) { r.rotulo = `${r.base} (${fmt(n)})`; pintarControl(); }
      avisa("", false);
    })();
    return r.promesa;
  }

  const layers = {};
  /* Las mismas capas, indexadas por la CLAVE con que el build escribe cada chip
     en `data-capa`. `layers` sigue existiendo porque es la declaración del
     control de capas —su orden y su rótulo sin cifra, que `pintarControl` lee—,
     y ese control aquí NO se retira: el mapa de la portada tiene trece capas y
     los chips accionan cinco. Los chips son el atajo a las cinco que cuentan la
     historia, y el control sigue guardando el resto.
     Una clave apunta a VARIAS capas: «Copernicus» son sus edificios, sus
     interrupciones, sus vías, las zonas que recortó y los huecos que dejó sin
     analizar: seis capas de Leaflet y un solo servicio que mirar o dejar de
     mirar. **Un chip manda sobre TODA su fuente**: si apagar «Copernicus»
     dejara sus polígonos en pantalla, el control estaría mintiendo. */
  const porCapa = {};
  const conChip = (clave, capa) => {
    (porCapa[clave] = porCapa[clave] || []).push(capa);
    // La ranura recuerda a qué chip pertenece: mientras su fichero viaja, ese
    // chip es el que tiene que decir que algo está pasando.
    const r = ranuraDe.get(capa);
    if (r) r.clave = clave;
    return capa;
  };
  /* Y la contraria: una capa que NO cuelga de ningún chip tiene que decir por
     qué, aquí y por escrito. Los cinco chips son las cinco miradas al DAÑO de
     este terremoto; lo que queda fuera es contexto (el terreno sísmico), otro
     evento (los sismos históricos) o un compuesto de varias fuentes que ningún
     chip puede reclamar como suyo. Todo eso sigue accionable desde el control
     de capas de Leaflet, que por esto mismo no se retira. Lo que no vale es que
     una capa quede fuera por descuido: `sinChip` obliga a escribir el motivo y
     su guardián lo comprueba (`tests/test_frontend.py::TestCadaCapaTieneChipOMotivo`). */
  const fueraDeChip = [];
  const sinChip = (motivo, capa) => {
    fueraDeChip.push({ motivo, capa });
    return capa;
  };
  layers["Intensidad estimada por el USGS"] = sinChip(
    "Modelo del USGS: no es una mirada al daño, es el terreno sísmico sobre "
    + "el que se leen todas las demás. Ningún chip la reclama porque no "
    + "documenta un municipio: lo contextualiza.",
    diferida("shakemap_mmi.geojson", (shake) => L.geoJSON(shake, {
      style: (f) => ({ color: "#8a5a00", weight: 1, opacity: 0.5, dashArray: "4 3" }),
      onEachFeature: (f, l) => l.bindTooltip(
        `Intensidad ${f.properties.value ?? "—"} en la escala de Mercalli modificada`),
    }), { cifra: false }));
  /* La capa de la ausencia: municipios con damnificados registrados sobre los
     que ninguno de los tres servicios que sigue el monitor —Copernicus EMS,
     UNITAR-UNOSAT e ICube-SERTIT— ha publicado un producto de daño. NO dice
     que ningún satélite pasara por encima, que es lo que nadie puede saber.
     Es la tesis del proyecto dibujada —la distancia entre lo que se ve y lo
     que se cuenta—, así que va encendida de entrada y al fondo (bringToBack):
     la ausencia es contexto, no puede tapar la evidencia que sí existe.
     El rojo lo gradúa la intensidad que el modelo del USGS estima para la
     cabecera: es SACUDIDA ESTIMADA, no daño observado — precisamente aquí
     nadie ha medido daño, y sin ese aviso 196 anillos rojos se leen como un
     mapa de destrucción. Donde el ShakeMap no llega, gris: fuera de su
     cuadrícula no hay «intensidad baja», hay ausencia de dato, y pintarla del
     rojo más pálido sería un cero disfrazado, además del más tranquilizador
     (R3). */
  const colorAusencia = (mmi) => {
    if (mmi == null) return css("--muted");
    const t = Math.max(0, Math.min(1, (mmi - 3.5) / 4));
    return `hsl(${Math.round(8 - 8 * t)},${Math.round(45 + 35 * t)}%,${
      Math.round(74 - 34 * t)}%)`;
  };
  /* Y el TAMAÑO gradúa las familias inscritas en el RUD, que es la única
     evidencia que tienen estos municipios: con radio fijo, el que registró
     2.313 familias y el que registró una eran el mismo punto, y el mapa
     escondía el orden de magnitud de lo que nadie miró desde el aire.
     Raíz cuadrada, no proporción directa: el ojo compara áreas, y con el radio
     proporcional el mayor saldría 2.313 veces más grande que el menor.
     `Number.isFinite`, y no el `|| 9` con el que esto se prototipó: rellenar
     con nueve familias al municipio que no trae cifra es inventarse el dato —el
     cero disfrazado que prohíbe R3, hermano del rojo pálido que aquí arriba se
     descartó para la sacudida—. Sin cifra, el anillo se va POR DEBAJO de la
     escala en vez de a su primer peldaño: así no se lee como «pocas familias»
     sino como fuera de la cuenta, y el globo lo dice además con palabras. Un
     cero SÍ es una cifra y se queda en el suelo de la escala, no en el limbo.
     Hoy no debería ocurrir nunca —la capa exige familias registradas:
     `ingest/municipios.py::sin_mirada_satelital`—, y por eso mismo se escribe:
     si la fuente cambia, tiene que verse, no rellenarse. */
  const BASE_SIN_CIFRA = 1.8;
  const baseAusencia = (familias) => {
    if (!Number.isFinite(familias)) return BASE_SIN_CIFRA;
    return Math.min(4 + Math.sqrt(Math.max(0, familias)) / 4, 16) / 1.6;
  };
  /* Los `circleMarker` de Leaflet miden en PÍXELES, no en metros: sin reescalar,
     la misma marca se ve igual a zoom 6 que a zoom 15 y acercarse no aporta
     nada. Crece con el zoom —suave, no exponencial— y con TOPE.
     Una sola fórmula para TODAS las marcas del mapa, con el tope como
     parámetro: la primera copia de esto vivió solo en el anillo de la ausencia
     y los edificios se quedaron con radio fijo, que es exactamente cómo
     divergen dos versiones de la misma regla.
     Dos topes, porque las dos marcas dicen cosas distintas: el anillo de un
     MUNICIPIO señala un sitio y no dibuja su extensión —sin tope, a zoom 16
     pasaba de 6 a 46 px y se comía la manzana entera—, mientras que el punto de
     un EDIFICIO sí tiene que ganar detalle al acercarse, pero cabiendo en el
     tejado que retrata: por eso se queda en 11.
     El suelo (2) queda por debajo de `BASE_SIN_CIFRA` a propósito: si recortara
     ahí, el anillo sin cifra volvería de puntillas a la escala de la que se le
     acaba de sacar. */
  const TOPE_AUSENCIA = 18;
  const TOPE_PUNTO = 11;
  const radioZoom = (base, tope) => {
    // Al construirse las marcas el mapa todavía no tiene vista —el encuadre va
    // más abajo— y `getZoom()` no devuelve número: se pintan con el radio base y
    // el reescalado las ajusta en cuanto hay encuadre.
    const z = map.getZoom();
    const factor = 1 + Math.max(0, (Number.isFinite(z) ? z : 7) - 7) * 0.42;
    return Math.min(tope, Math.max(2, base * factor));
  };
  // El radio de un edificio o de un reporte de la comunidad: base fija —lo que
  // cambia entre capas es el peso visual de la marca, no su significado— y el
  // tope corto.
  const radioPunto = (base) => radioZoom(base, TOPE_PUNTO);
  const radioAusencia = (familias) => {
    return radioZoom(baseAusencia(familias), TOPE_AUSENCIA);
  };
  /* Qué capas se reescalan y CÓMO: cada una registra la función que da el radio
     de cada uno de sus círculos. Con esto el zoom deja de agrandar solo la
     ausencia. Una capa que no se registra aquí conserva radio fijo, y eso es
     una decisión que se escribe donde se toma. */
  const conRadio = [];
  const conZoom = (radio, capa) => {
    conRadio.push({ capa, radio });
    return capa;
  };
  const reescalar = () => {
    for (const { capa, radio } of conRadio) {
      capa.eachLayer((l) => l.setRadius && l.setRadius(radio(l)));
    }
  };
  // Al primer encuadre y en cada zoom: las marcas nacen antes de que el mapa
  // tenga vista, con lo que llegan a su radio base y sin este primer repaso se
  // quedarían ahí.
  map.whenReady(reescalar);
  map.on("zoomend", reescalar);
  /* «con damnificados» NO es adorno: sin esa condición el rótulo enuncia un
     predicado que da 197, y municipios.html publica justo ese —Palmira no
     tiene registro en el RUD y sí entra en su cuenta—. Dos páginas del mismo
     sitio con dos cifras del mismo hecho es el fallo de los «36 y 43».
     La cifra del rótulo la pone `enciende` contando los rasgos DIBUJADOS, que
     es lo mismo que contaba aquí `conCoords.length`: si algún municipio llegara
     sin coordenadas, la etiqueta no puede prometer más puntos de los que hay. */
  layers["Municipios con damnificados y sin producto de daño satelital"] =
    conChip("ausencia", diferida("municipios_mapa.json", (sinMirada) => {
    const conCoords = (sinMirada.items || [])
      .filter((m) => m.lat != null && m.lon != null);
    return conZoom(
      (l) => radioAusencia(l.feature.properties.rud_familias), L.geoJSON({
      type: "FeatureCollection",
      features: conCoords
        .map((m) => ({ type: "Feature", properties: m,
                       geometry: { type: "Point", coordinates: [m.lon, m.lat] } })),
    }, {
      // Anillo punteado y relleno muy tenue: hueco por dentro, porque eso es
      // lo que dice el dato. Con relleno sólido estos 196 competían con los
      // municipios que SÍ tienen evidencia y el mapa dejaba de distinguir
      // «mirado» de «no mirado», que es justo lo que viene a enseñar.
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: radioAusencia(f.properties.rud_familias),
        weight: 1.5, opacity: 0.75, fillOpacity: 0.12,
        dashArray: "2 2",
        color: colorAusencia(f.properties.mmi_usgs),
        fillColor: colorAusencia(f.properties.mmi_usgs),
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindPopup(ficha({
          // la clave del catálogo desambigua («Bolívar (Cauca)»); con el
          // departamento ya de subtítulo, repetirla duplicaba el paréntesis
          titulo: window.UI.esc(window.UI.toponimo(p.municipio, p.departamento)),
          subtitulo: window.UI.esc(p.departamento),
          filas: [
            // por fmt(): el millar del sitio es es-CO («1.234»), nunca el crudo
            ["Familias registradas en el RUD", p.rud_familias == null
              ? null : fmt(p.rud_familias)],
            ["Personas registradas en el RUD", p.rud_personas == null
              ? null : fmt(p.rud_personas)],
            // sin dato se dice, no se rellena con un número que no existe.
            // Con la escala: el mismo emisor publica dos intensidades en este
            // mapa —esta y la percibida del DYFI— y el número solo no distingue
            ["Sacudida estimada (modelo ShakeMap)",
             p.mmi_usgs == null ? "sin dato"
               : `${fmt(p.mmi_usgs)} en la escala de Mercalli modificada`],
          ],
          pie: "Familias y personas: RUD de la UNGRD, inscripciones que carga "
            + "el municipio, no una evaluación de daños · Sacudida: modelo "
            + "ShakeMap del USGS, ni medida en el terreno ni reportada por la "
            + "gente · Sin producto de daño de Copernicus EMS, UNOSAT ni "
            + "ICube-SERTIT",
        }));
      },
    }));
  }, { fondo: true }));

  const munLayerById = {};
  // Las zonas que Copernicus recortó son Copernicus, así que cuelgan de su
  // chip: apagarlo dejaba estos polígonos en pantalla y el control publicaba
  // un estado que el mapa desmentía (B2 de la auditoría del 25-ago).
  layers["Zonas que analizó Copernicus"] = conChip("copernicus",
    diferida("aois.geojson", (aois) => L.geoJSON(aois, {
      style: (f) => ({
        color: ESTADO_COLOR[f.properties.estado] || css("--muted"),
        weight: 2, fillOpacity: 0.12,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        // «Western Colombia» es el área de referencia y no trae ninguna cifra:
        // su globo se queda en el título y la etiqueta, sin cuatro renglones
        // de guiones que parecerían ceros.
        l.bindPopup(ficha({
          titulo: aoiLabel(p.aoi), subtitulo: p.etiqueta,
          filas: [
            ["Población", p.poblacion == null ? null : fmt(p.poblacion)],
            ["Edificios afectados", p.edificios_afectados == null ? null
              : fmt(p.edificios_afectados)],
            ["Vías afectadas", p.vias_afectadas_km == null ? null
              : `${fmt(p.vias_afectadas_km)} km`],
            ["Interrupciones viales", p.interrupciones_viales == null ? null
              : fmt(p.interrupciones_viales)],
          ],
          pie: "Copernicus EMS",
        }));
      },
    }), { cifra: false }));

  // ---- detecciones de daño de Copernicus (la faceta punto a punto)
  /* Vocabulario de daño compartido: Copernicus e ICube-SERTIT gradúan con las
     mismas tres palabras, así que el color lo pone UNA tabla. SERTIT añade
     edificios que dibujó sin asignarles grado. */
  const GRADO_COLOR = {
    "Destroyed": css("--critical"), "Damaged": "#ec835a",
    "Possibly damaged": css("--warning"), "Not Applicable": css("--muted"),
  };
  const GRADO_ES = { "Destroyed": "Destruido", "Damaged": "Dañado",
                     "Possibly damaged": "Posiblemente dañado" };
  /* Dos capas salen del MISMO fichero, y cada una es su propia ranura: la
     caché de `pide` hace que compartan una sola descarga, así que separarlas
     no cuesta una petición de más y sí permite encender los edificios sin las
     interrupciones. */
  layers["Edificios dañados — satélite"] = conChip("copernicus", diferida(
    "damage_points.geojson", (dmgPts) => {
    const edificios = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer === "builtUpP") };
    return conZoom(() => radioPunto(5.5), L.geoJSON(edificios, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: radioPunto(5.5), weight: 1.5, color: "#fff", fillOpacity: 0.9,
          fillColor: GRADO_COLOR[f.properties.damage_gra] || css("--muted"),
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          const objeto = p.simplified || p.obj_type || "";
          const metodo = p.det_method || "";
          l.bindPopup(ficha({
            titulo: GRADO_ES[p.damage_gra] || t(p.damage_gra) || "Edificio evaluado",
            filas: [
              ["Tipo de objeto", objeto ? conOriginal(objeto) : null],
              ["Zona", p.aoi ? aoiLabel(p.aoi) : null],
              ["Método de detección", metodo ? conOriginal(metodo) : null],
            ],
            pie: "Copernicus EMS",
          }));
        },
      }));
  }));
  layers["Interrupciones / crisis"] = conChip("copernicus", diferida(
    "damage_points.geojson", (dmgPts) => {
    const crisis = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer !== "builtUpP") };
    return conZoom(() => radioPunto(6), L.geoJSON(crisis, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: radioPunto(6), weight: 2, color: css("--critical"),
        fillColor: "#fff", fillOpacity: 0.9,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        const obj = p.obj_type || "Interrupción";
        l.bindPopup(ficha({
          titulo: conOriginal(obj),
          filas: [["Zona", p.aoi ? aoiLabel(p.aoi) : null]],
          pie: "Copernicus EMS",
        }));
      },
    }));
  }));
  layers["Vías dañadas — satélite"] = conChip("copernicus",
    diferida("damage_lines.geojson", (dmgLines) => L.geoJSON(dmgLines, {
        style: () => ({ color: css("--critical"), weight: 4, opacity: 0.85 }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          const via = p.info || p.obj_type || "";
          l.bindPopup(ficha({
            titulo: "Vía dañada",
            filas: [["Tramo", via ? conOriginal(via) : null],
                    ["Zona", p.aoi ? aoiLabel(p.aoi) : null]],
            pie: "Copernicus EMS",
          }));
        },
      })));
  // ---- UNITAR-UNOSAT: la segunda mirada satelital, en municipios que
  // Copernicus no cartografía. Vocabulario propio: UNOSAT gradúa entre daño
  // observado y daño posible, y declara aparte si el punto se ha validado en
  // campo — una distinción que Copernicus no publica y que no se homogeneiza.
  const UNOSAT_ES = {
    "Damage": "Daño observado", "Damaged": "Daño observado",
    "Possible Damage": "Daño posible", "Destroyed": "Destruido",
    "Damaged Buildings": "Edificios dañados",
    "To Be Evaluated": "pendiente de evaluar",
    /* Vocabulario que UNOSAT estrenó el 21-ago-2026, al reeditar Viterbo y
       publicar Zarzal: hasta entonces su capa solo usaba «To Be Evaluated», y
       ningún punto declaraba una confianza distinta. */
    "Uncertain": "incierta", "Medium": "media", "High": "alta", "Low": "baja",
    "Not yet field validated": "aún no validado en campo",
    "Field validated": "validado en campo",
  };
  /* Igual que `conOriginal` para Copernicus: el término inglés es el que
     aparece en el shapefile descargable, y sin él no se puede localizar allí
     lo que el mapa enseña. */
  const uno = (s) => UNOSAT_ES[s] || s;
  const unoConOriginal = (s) => !s || uno(s) === s ? uno(s)
    : `${uno(s)} <span style="color:var(--muted)">(${s})</span>`;
  layers["Edificios evaluados — satélite UNOSAT"] = conChip("unosat", diferida(
    "unosat_damage.geojson", (unosat) => {
    const UNOSAT_COLOR = {
      "Damage": "#ec835a", "Damaged": "#ec835a",
      "Possible Damage": css("--warning"), "Destroyed": css("--critical"),
    };
    return conZoom(() => radioPunto(5.5), L.geoJSON(unosat, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: radioPunto(5.5), weight: 1.5, color: "#2b2b2b", fillOpacity: 0.9,
          fillColor: UNOSAT_COLOR[f.properties.dano] || css("--muted"),
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          // El código de evento solo se enseña cuando NO es el del terremoto:
          // 8 registros de Manizales vienen con EQ20260822COL, fechado DESPUÉS
          // de la imagen que los retrata. Se conserva el literal de la fuente
          // y se señala como inconsistencia, no se corrige por nuestra cuenta
          // ni se afirma que pertenezcan a otro sismo.
          const otroEvento = p.event_code && p.event_code !== "EQ20260810COL"
            ? `${p.event_code} — inconsistente: no es el que declara su producto`
            : null;
          l.bindPopup(ficha({
            titulo: unoConOriginal(p.dano) || "Edificio evaluado",
            subtitulo: [p.municipio, p.departamento].filter(Boolean).join(", ")
              || null,
            filas: [
              ["Imagen", [p.sensor, fechaImagen(p.sensor_date)]
                .filter(Boolean).join(", ") || null],
              ["Confianza del análisis", p.confianza
                ? unoConOriginal(p.confianza) : null],
              ["Validación en campo", p.validacion_campo
                ? unoConOriginal(p.validacion_campo) : null],
              ["Observaciones", p.notas || null],
              ["Código de evento", otroEvento],
            ],
            pie: "UNITAR-UNOSAT" +
              (p.productos ? ` · producto ${p.productos.split(",")[0]}` : ""),
          }));
        },
      }));
  }));

  // ---- ICube-SERTIT: la tercera mirada satelital. Servicio de cartografía
  // rápida de la Universidad de Estrasburgo, que evalúa edificio a edificio
  // con imágenes Pléiades. Gradúa el daño con el mismo vocabulario que
  // Copernicus —por eso comparte la tabla de colores—, pero no mira las mismas
  // ventanas: en Pereira dibuja sobre 2,78 km² donde Copernicus cubre 9,8, y
  // en Roldanillo y La Virginia es el único que ha mirado.
  const SERTIT_ES = {
    // lo que el vocabulario de Copernicus (DICT) no cubre
    "Not Applicable": "Sin grado de daño asignado",
    "Tent/shelter": "Carpa o refugio", "Industrial": "Industrial",
    "Religious": "Religioso", "Hospital": "Hospital",
    "Educational": "Educativo", "Transportation": "Transporte",
    "Sport hall": "Polideportivo",
  };
  /* Igual que `conOriginal` para Copernicus y `unoConOriginal` para UNOSAT: el
     término inglés es el que aparece en el producto descargable, y sin él no
     se puede localizar allí lo que el mapa enseña. Lo que SERTIT nombra igual
     que Copernicus se traduce una sola vez, en DICT. */
  const ser = (s) => SERTIT_ES[s] || DICT[s] || s;
  const serConOriginal = (s) => !s || ser(s) === s ? ser(s)
    : `${ser(s)} <span style="color:var(--muted)">(${s})</span>`;
  layers["Edificios evaluados — satélite ICube-SERTIT"] = conChip("sertit",
    diferida("sertit_damage.geojson", (sertit) =>
      conZoom(() => radioPunto(5.5), L.geoJSON(sertit, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: radioPunto(5.5), weight: 1.5, color: "#fff", dashArray: "2 3",
          fillOpacity: 0.9,
          fillColor: GRADO_COLOR[f.properties.dano] || css("--muted"),
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          l.bindPopup(ficha({
            titulo: serConOriginal(p.dano) || "Edificio evaluado",
            subtitulo: [p.municipio, p.departamento].filter(Boolean).join(", ")
              || null,
            filas: [
              ["Tipo de edificio", p.tipo ? serConOriginal(p.tipo) : null],
              ["Imagen", [p.sensor, fechaImagen(p.sensor_date)]
                .filter(Boolean).join(", ") || null],
              ["Método de detección", p.metodo ? serConOriginal(p.metodo) : null],
            ],
            // El crédito no es adorno: la licencia de SERTIT obliga a atribuir
            // el dato allí donde se publique, y aquí se publica punto a punto.
            pie: (p.copyright || "ICube-SERTIT") +
              (p.producto_id ? ` · producto ${p.producto_id}` : ""),
          }));
        },
      }))));

  // ---- Sedes educativas del MEN: la primera mirada OFICIAL sede a sede.
  // No es un satélite: es el seguimiento administrativo del Ministerio de
  // Educación Nacional (SISE), cargado por las secretarías de educación. Su
  // vocabulario ya viene en español y es el que se enseña tal cual — no hay
  // diccionario ESTADO_FISICO_ES a propósito: un diccionario identidad sería
  // una segunda copia sin información, y una superficie más que vigilar.
  // El fichero solo trae las sedes CON afectación declarada: «Sin afectación»
  // y «No aporta información» quedan en el archivo del monitor (snapshots y
  // volcados), no en un geojson público — miles de sedes sin verificar no son
  // sedes sanas (R3), y pintarlas ahogaría a las ~987 que sí reportan daño.
  /* Colores en la rampa de gravedad que ya usan las capas de daño: colapso
     total lleva el rojo de «Destruido» y el resto baja hacia el ámbar; la
     afectación sin definir va en gris —sin definir no es leve (R3)—. Espejo
     de `deploy/render_html.py::_ESTADOS_MEN` y de la tabla de
     `site/municipio.js`; las tres superficies las compara
     `tests/test_render_html.py::TestEstadosDelMen`. */
  layers["Sedes educativas afectadas — MEN"] = conChip("sedes_men", diferida(
    "men_sedes_mapa.geojson", (sedes) => {
    const ESTADO_FISICO_COLOR = {
      "Colapso total": css("--critical"),
      "Riesgo inminente de colapso": "#e0552d",
      "Colapso parcial": "#ec835a",
      "Afectación parcial": css("--warning"),
      "Afectación menor": "#f7d46b",
      "Reporta afectación sin definir el impacto": css("--muted"),
    };
    /* Las sedes sin geolocalización resuelta viajan con `geometry` null:
       Leaflet las salta al construir la capa y el rótulo del control cuenta
       lo DIBUJADO (`enciende`), así que la cifra del mapa es la de los
       puntos que se ven. El total con las no pintables lo da la prosa de la
       portada, con las dos cifras y sus nombres. */
    return conZoom(() => radioPunto(5.5), L.geoJSON(sedes, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: radioPunto(5.5), weight: 1.5, color: "#fff", fillOpacity: 0.9,
          // categoría desconocida → color de reserva, nunca romper: si el MEN
          // estrena un estado, el punto se pinta gris y el supuesto avisa
          fillColor: ESTADO_FISICO_COLOR[f.properties.estado_fisico]
            || css("--muted"),
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          l.bindPopup(ficha({
            // el literal crudo del MEN es el título: ya está en español y es
            // lo que hay que buscar en su tablero para encontrar esta sede
            titulo: window.UI.esc(p.estado_fisico) || "Sede educativa evaluada",
            subtitulo: window.UI.esc(p.nombre_sede) || null,
            filas: [
              ["Establecimiento", p.nombre_establecimiento
                ? window.UI.esc(p.nombre_establecimiento) : null],
              ["Municipio", [p.nom_mun, p.nom_dep].filter(Boolean)
                .map(window.UI.esc).join(", ") || null],
              ["Sector y zona", [p.sector, p.zona].filter(Boolean)
                .map(window.UI.esc).join(" · ") || null],
              ["Matrícula total", p.total_matricula == null ? null
                : fmt(p.total_matricula)],
              ["Confianza de la geolocalización", p.confianza_geo
                ? window.UI.esc(p.confianza_geo) : null],
            ],
            pie: "Ministerio de Educación Nacional (SISE) · reporte "
              + "administrativo de las secretarías de educación, no una "
              + "evaluación estructural en campo",
          }));
        },
      }));
  }));

  // El hueco de cobertura es un producto de Copernicus tanto como el edificio
  // que sí clasificó: dice dónde recortó y no miró. Bajo su chip. Y es el
  // fichero más pesado del mapa —2.174 KB para 48 polígonos—, así que es el
  // que más se nota que ya no se baja hasta que alguien lo pide.
  layers["Zonas sin analizar"] = conChip("copernicus", diferida("not_analysed.geojson",
    (notAnalysed) => L.geoJSON(notAnalysed, {
      style: () => ({ color: css("--muted"), weight: 1, dashArray: "3 4",
                      fillColor: css("--muted"), fillOpacity: 0.18 }),
      onEachFeature: (f, l) => l.bindTooltip(
        `Sin analizar (${aoiEs(f.properties.aoi)}) — hueco de cobertura`),
    })));

  /* La estrella del epicentro no es una capa temática y por eso no entra ni en
     los chips ni en el control: no es una FUENTE mirando el desastre, es el
     desastre. Se queda siempre encendida porque es el ancla de la vista
     nacional con la que abre el mapa —sin ella, un país entero de anillos no
     dice dónde empezó todo—. */
  if (mon.evento && mon.evento.coordinates) {
    const [elon, elat] = mon.evento.coordinates;
    L.marker([elat, elon], {
      icon: L.divIcon({
        className: "", iconSize: [26, 26], iconAnchor: [13, 13],
        html: `<div style="font-size:22px;line-height:26px;text-align:center;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))">★</div>`,
      }),
    }).addTo(map).bindPopup(ficha({
      titulo: `Epicentro M${mon.evento.mag}`,
      subtitulo: mon.evento.place,
      filas: [["Reportes «lo sentí»", mon.evento.felt == null ? null
        : fmt(mon.evento.felt)]],
      pie: "USGS",
    }));
  }
  layers["Reportes ciudadanos ChatMap"] = conChip("ciudadanos",
    diferida("chatmap.geojson", (chat) =>
      conZoom(() => radioPunto(5), L.geoJSON(chat, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: radioPunto(5), color: css("--s7"), weight: 1.5,
        fillColor: css("--s7"), fillOpacity: 0.55,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        const media = p.media && /\.(jpg|jpeg|png|webp)$/i.test(p.media)
          ? `<a href="${p.media}" target="_blank" rel="noopener"><img src="${p.media}" loading="lazy" alt="foto ciudadana"></a>`
          : (p.media ? `<a href="${p.media}" target="_blank" rel="noopener">ver medio</a>` : "");
        l.bindPopup(ficha({
          titulo: "Reporte ciudadano",
          subtitulo: p.time || null,
          filas: [
            ["Dentro de zona analizada por Copernicus", p.aoi ? aoiLabel(p.aoi) : null],
            ["Intensidad estimada (escala de Mercalli)", p.mmi == null ? null : fmt(p.mmi)],
            ["", p.mensaje || null],
          ],
          html: media || null,
          pie: "ChatMap · en el punto que registró la fuente" +
            (p.score == null ? "" : ` · puntuación de la verificación automática: ${p.score}`),
        }));
      },
    }))));
  layers["Intensidad que sintió la población"] = sinChip(
    "Cuestionario del USGS: mide lo que la gente SINTIÓ, no lo que se dañó. "
    + "Es la otra cara de la sacudida estimada y comparte su motivo: "
    + "contexto sísmico, no una mirada al daño de un municipio.",
    diferida("dyfi_cells.geojson", (dyfi) => L.geoJSON(dyfi, {
      style: (f) => {
        const c = f.properties.cdi || 0;
        const op = Math.min(0.65, 0.08 + c * 0.07);
        return { color: css("--s1"), weight: 0.5, fillColor: css("--s1"), fillOpacity: op };
      },
      onEachFeature: (f, l) => l.bindTooltip(
        `Intensidad percibida ${f.properties.cdi} · ` +
        `${f.properties.nresp} respuestas ciudadanas`),
    }), { cifra: false }));
  layers["Sismos históricos UNGRD"] = sinChip(
    "Registro histórico de sismicidad de la UNGRD: eventos anteriores al 10 "
    + "de agosto. Ningún chip puede reclamarlos, porque los cinco cuentan "
    + "quién ha mirado el daño de ESTE terremoto.",
    diferida("ungrd_sismos.geojson", (sismos) => L.geoJSON(sismos, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: 3, color: css("--muted"), weight: 1, fillOpacity: 0.4,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindTooltip(`${p.fecha ?? "?"} · ${p.municipio ?? ""} (${p.departamento ?? ""})`);
      },
    })));
  layers["Municipios con señal: RUD, prensa o intensidad"] =
    sinChip(
      "COMPUESTO de varias fuentes a la vez —RUD, prensa, intensidad "
      + "percibida y las tres miradas satelitales—, no la representación de "
      + "ninguna: su color es el ESTADO DEL CRUCE, que solo existe después de "
      + "juntarlas. Ningún chip puede reclamarla sin mentir, porque apagar "
      + "«Copernicus» no borra el municipio que además tiene RUD y prensa. Por "
      + "eso llega apagada y vive en el control de capas: quien la enciende "
      + "sabe que está mirando el cruce, no una fuente. Y su radio se queda "
      + "fijo —solo distingue si el municipio cae dentro de una zona de "
      + "Copernicus—: aquí el tamaño ya significa otra cosa.",
      diferida("municipios.geojson", (municipios) => {
    // colores desde la tabla única de ui.js (misma etiqueta que la tabla)
    const MUN_COLOR = Object.fromEntries(
      Object.entries(window.UI.ESTADO_MUNICIPIO)
        .map(([k, [, v]]) => [k, css(v)]));
    return L.geoJSON(municipios, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: f.properties.en_aoi_copernicus ? 6 : 5,
          color: "#fff", weight: 1.5,
          fillColor: MUN_COLOR[f.properties.estado] || css("--muted"),
          fillOpacity: 0.85,
        }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          munLayerById[p.municipio] = l;
          // Cada renglón es una fuente distinta hablando de este municipio.
          // La que no lo haya mirado no deja renglón: un «DYFI: —» sugiere
          // que la intensidad se midió y salió nula, cuando lo que pasa es
          // que nadie respondió el cuestionario ahí.
          const desglose = (p.cabecera_2026 != null || p.rural_2026 != null)
            ? ` <span style="color:var(--muted)">cabecera ${fmt(p.cabecera_2026)}` +
              ` · rural ${fmt(p.rural_2026)}</span>` : "";
          l.bindPopup(ficha({
            // la clave desambigua, el título no la repite: el globo decía
            // «Riosucio (Caldas) (Caldas)» en los cinco municipios homónimos
            titulo: `${window.UI.toponimo(p.municipio, p.departamento)}`
                    + ` (${p.departamento})`,
            subtitulo: p.en_aoi_copernicus
              ? "Dentro de zona mapeada por Copernicus"
              : "Fuera de toda zona mapeada por Copernicus",
            filas: [
              ["Población DANE 2026", p.poblacion_2026 == null ? null
                : fmt(p.poblacion_2026) + desglose],
              ["Intensidad percibida (cuestionario ciudadano del USGS)",
                p.dyfi_max_cdi == null ? null
                : `${fmt(p.dyfi_max_cdi)} · ${fmt(p.dyfi_respuestas)} respuestas`],
              ["Titulares que lo nombran", p.homonimo_de_departamento
                ? "no atribuibles: se llama igual que un departamento"
                : (p.n_noticias || null)],
              ["Documentado por", (p.fuentes || []).map(
                (x) => FUENTE_ES[x] || x).join(", ") || null],
              ["Edificios evaluados por UNOSAT", p.unosat_edificios == null
                ? null
                : `${fmt(p.unosat_edificios)}, de los que ` +
                  `${fmt(p.unosat_observados)} con daño observado`],
              ["Con código de evento inconsistente", p.unosat_codigo_inconsistente == null
                ? null
                : `${fmt(p.unosat_codigo_inconsistente)}, contados igual`],
              // los destruidos solo se nombran si la fuente los declara: un
              // «0 destruidos» donde SERTIT no asignó grado sería un cero
              // inventado (R3)
              ["Edificios evaluados por ICube-SERTIT", p.sertit_edificios == null
                ? null
                : fmt(p.sertit_edificios) + (p.sertit_destruidos == null ? ""
                  : `, de los que ${fmt(p.sertit_destruidos)} ` +
                    `destruido${p.sertit_destruidos === 1 ? "" : "s"}`)],
              ["Damnificados en el RUD", p.rud_personas == null ? null
                : `${fmt(p.rud_personas)} personas` +
                  (p.tasa_rud_pct != null
                    ? ` (${window.UI.pct(p.tasa_rud_pct)} de la población proyectada 2026)`
                    : "")],
            ],
            // La advertencia depende de lo que este municipio tenga: donde un
            // servicio satelital sí ha evaluado edificios, decir «no equivale a
            // daño satelital» sería falso — lo que les falta es la
            // verificación oficial. Se pregunta por CUALQUIERA de las miradas:
            // con una sola condición, los municipios que solo vio SERTIT
            // leerían lo contrario de lo que la propia ficha acaba de afirmar.
            pie: p.unosat_edificios == null && p.sertit_edificios == null
              ? "No equivale a daño visto por satélite ni a una evaluación oficial " +
                "de daños en el terreno (EDAN)."
              : "Evaluación satelital sin comprobar sobre el terreno; no equivale a " +
                "una evaluación oficial de daños (EDAN).",
          }));
        },
      });
  }));

  /* Cada ranura aprende su rótulo del único sitio donde está escrito: la clave
     con la que se declaró su capa. Copiarlo a mano en la llamada a `diferida`
     serían dos versiones del mismo nombre a diez líneas de distancia, que es
     como divergen. La cifra se la añade `enciende` cuando la sepa. */
  for (const [nombre, capa] of Object.entries(layers)) {
    const r = ranuraDe.get(capa);
    if (r) { r.base = nombre; r.rotulo = nombre; }
  }

  /* EL CONTROL DE CAPAS DE LEAFLET SE QUEDA, y ahora tiene que ofrecer capas
     que todavía no se han pedido. Es la única puerta a las cuatro que ningún
     chip gobierna —el terreno sísmico, la intensidad percibida, los sismos
     históricos y el compuesto del cruce—, y esconderlas hasta que alguien las
     descargue sería esconderlas para siempre: nadie descarga lo que no ve. Así
     que las lista todas desde el primer momento, y cada una RESPONDE: al
     marcarla se pide su fichero y se dibuja.
     Lo que no hace es prometer una cifra que aún no tiene. El rótulo de una
     capa sin pedir se queda en su nombre, y su cifra aparece cuando el fichero
     ha llegado y se ha dibujado; un «(…)» o un «(0)» de relleno serían
     el cero disfrazado que prohíbe R3, justo en el sitio donde más se parece a
     un dato. Y la capa que llega vacía se retira: un control que ofrece algo y
     no responde es peor que no ofrecerlo.
     Se repinta ENTERO y siempre en el orden de declaración, porque
     `addOverlay` añade al final: renombrar una sola entrada quitándola y
     poniéndola otra vez la mandaría al fondo de la lista, y la lista bailaría
     bajo el ratón cada vez que llegara un fichero. */
  const control = L.control.layers(null, null, { collapsed: true }).addTo(map);
  const pintarControl = () => {
    for (const capa of Object.values(layers)) control.removeLayer(capa);
    for (const [nombre, capa] of Object.entries(layers)) {
      const r = ranuraDe.get(capa);
      if (r && !r.viva) continue;
      control.addOverlay(capa, (r && r.rotulo) || nombre);
    }
  };
  pintarControl();

  /* Un solo sitio decide QUÉ se ve al abrir, y decide lo mismo que el build
     escribe en los chips: Colombia entera y la ausencia sola. Repartido en
     doce altas sueltas, el estado inicial no se podía leer ni comprobar, y por
     eso llegó a abrir con cinco capas puestas más otras tres que ningún chip
     gobernaba.
     El encuadre va DESPUÉS de construir las capas, no antes: así el primer
     `reescalar` de `whenReady` encuentra ya todo registrado y las marcas nacen
     con el radio del zoom real. */
  map.setView(VISTA_NACIONAL.centro, VISTA_NACIONAL.zoom);
  for (const capa of porCapa.ausencia || []) {
    // Encender es pedir: el alta del grupo dispara la descarga de su fichero.
    // Al fondo va la capa de dentro, cuando llegue —la ausencia es el contexto
    // sobre el que se leerá la evidencia que el lector encienda después, y no
    // puede taparla—: lo hace `enciende` con la marca `fondo`, porque un
    // `LayerGroup` vacío no tiene nada que mandar al fondo todavía.
    capa.addTo(map);
  }

  /* Los chips de capa, que el build ya dejó escritos con su rótulo y su
     recuento. No se construyen aquí: los cuenta `render_html.py::chips_portada`
     sobre los mismos datos que este mapa dibuja, y construirlos en el navegador
     sería una segunda copia de esos recuentos y dejaría la tira vacía para
     quien lee el documento sin ejecutarlo.

     Filtran el MAPA. La lista del panel NO se toca: es un cuadro de honor y una
     puerta de entrada, no un índice — el índice filtrable es /municipios.html.

     A diferencia de la ficha municipal, aquí el control de capas de Leaflet se
     queda: los chips accionan cinco de las doce capas, y retirarlo escondería
     las otras siete. Por eso hay que oírlo: si alguien apaga una capa desde el
     control, su chip tiene que enterarse, o la tira publicaría un estado que el
     mapa desmiente. */
  (function conectarChips() {
    const tira = document.getElementById("capas-mapa");
    if (!tira) return;
    const suyas = {};
    for (const chip of tira.querySelectorAll(".chip[data-capa]")) {
      const capas = porCapa[chip.dataset.capa];
      // Un chip sin capa no puede accionar nada: se retira antes que quedarse
      // como control muerto. No debería pasar —el build emite chip donde hay
      // municipios y `app.js` crea capa donde hay puntos—, pero el día que las
      // dos condiciones se separen, el lector no se queda pulsando en vano.
      if (!capas || !capas.length) { chip.remove(); continue; }
      suyas[chip.dataset.capa] = capas;
      /* El reflejo NO cambia de significado con la carga diferida: la capa que
         se está descargando ya está puesta en el mapa —es su grupo, vacío
         todavía—, así que un chip encendido sigue queriendo decir «esta fuente
         está en el mapa». Lo que la descarga añade es el `aria-busy` que pone
         `marcarCarga`, que dice otra cosa: «y además viene en camino».
         Lo que sí es nuevo es la segunda muerte de un chip: una capa que se
         pide y llega vacía se retira de `porCapa`, y entonces el chip se queda
         sin nada que accionar. Es el mismo control muerto que se retira arriba
         al engancharlo, un rato más tarde. */
      const refleja = () => {
        if (!capas.length) { chip.remove(); return; }
        chip.setAttribute(
          "aria-pressed", String(capas.some((c) => map.hasLayer(c))));
      };
      refleja();
      chip.addEventListener("click", () => {
        const encendido = chip.getAttribute("aria-pressed") === "true";
        for (const c of capas) {
          if (encendido) map.removeLayer(c); else c.addTo(map);
        }
        chip.setAttribute("aria-pressed", String(!encendido));
      });
      chip._refleja = refleja;
    }
    if (!Object.keys(suyas).length) { tira.remove(); return; }
    const resincronizar = () => {
      for (const chip of tira.querySelectorAll(".chip[data-capa]")) {
        if (chip._refleja) chip._refleja();
      }
    };
    map.on("overlayadd overlayremove", resincronizar);
    // Y `retira` también tiene que poder llamarlo: una capa que muere después
    // de pedirse no pasa por `overlayremove` de nadie.
    refrescaChips = resincronizar;
  })();

  /* El grid asienta su tamaño tarde: hay que avisar a Leaflet cuando el
     contenedor cambie de ancho. Se reencuadra a la vista nacional, que es la de
     partida — pero SOLO mientras el lector no haya movido el mapa: reencuadrar
     a quien acaba de acercarse a su municipio, porque el navegador cambió de
     tamaño o se giró el teléfono, es arrebatarle lo que estaba mirando. */
  let sinTocar = true;
  map.on("zoomstart movestart", () => { sinTocar = false; });
  let lastW = map.getSize().x;
  new ResizeObserver(() => {
    const w = document.getElementById("map").clientWidth;
    if (Math.abs(w - lastW) > 4) {
      lastW = w;
      map.invalidateSize();
      if (sinTocar) {
        map.setView(VISTA_NACIONAL.centro, VISTA_NACIONAL.zoom);
        sinTocar = true;      // el reencuadre propio no cuenta como toque
      }
    }
  }).observe(document.getElementById("map"));

  // ---- tabla de portada
  // Las filas las escribe el build (deploy/render_html.py::filas_portada): aquí
  // solo se engancha el clic que centra el mapa. Cada fila trae su coordenada en
  // data-lat/data-lon, así que no hace falta reconstruir nada.
  const tbody = document.querySelector("#tabla tbody");
  if (tbody) {
    tbody.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;          // los enlaces a la ficha mandan
      const tr = ev.target.closest("tr[data-lat]");
      if (!tr) return;
      const lat = parseFloat(tr.dataset.lat);
      const lon = parseFloat(tr.dataset.lon);
      if (Number.isNaN(lat) || Number.isNaN(lon)) return;
      map.setView([lat, lon], 12);
      irAlMapa();
    });
  }

  // subir al mapa al elegir una zona/municipio desde las tablas
  function irAlMapa() {
    document.getElementById("map").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Las fichas municipales enlazan aquí con ?municipio=…: su mapa es una imagen
  // estática y el interactivo se carga solo cuando el lector lo pide.
  const pedido = new URLSearchParams(location.search).get("municipio");
  if (pedido) {
    /* La única capa que se pide sin que nadie la encienda, y solo cuando la
       dirección la reclama: `munLayerById` lo escribe el compuesto del cruce
       al dibujarse, y sin su fichero este enlace no sabría dónde está el
       municipio. Se enciende la ranura, no la capa: el mapa sigue abriendo por
       la ausencia y el compuesto sigue apagado, igual que antes. */
    for (const r of RANURAS) {
      if (r.fichero === "municipios.geojson") await enciende(r);
    }
    const capa = munLayerById[pedido];
    if (capa) {
      map.setView(capa.getLatLng ? capa.getLatLng() : capa.getBounds().getCenter(), 11);
      capa.openPopup();
      irAlMapa();
    }
  }

  // ---- tooltips propios para las cabeceras: instantáneos y visibles también
  // en táctil (el title nativo tarda ~1 s y en móvil no existe)
  (function cabecerasConTooltip() {
    const tip = document.createElement("div");
    tip.className = "tooltip th-tip";
    tip.style.display = "none";
    document.body.appendChild(tip);
    let fijado = null;
    const mostrar = (th) => {
      tip.textContent = th.dataset.tip;
      tip.style.display = "block";
      const r = th.getBoundingClientRect();
      const w = Math.min(340, window.innerWidth - 24);
      tip.style.maxWidth = w + "px";
      let x = r.left;
      if (x + w > window.innerWidth - 12) x = window.innerWidth - w - 12;
      tip.style.left = Math.max(12, x) + "px";
      tip.style.top = (r.bottom + 6) + "px";
    };
    const ocultar = () => { tip.style.display = "none"; fijado = null; };
    for (const th of document.querySelectorAll("th[title]")) {
      th.dataset.tip = th.getAttribute("title");
      th.removeAttribute("title");   // evitar el tooltip nativo duplicado
      th.addEventListener("mouseenter", () => mostrar(th));
      th.addEventListener("mouseleave", () => { if (fijado !== th) ocultar(); });
      th.addEventListener("click", () => {   // táctil: tocar fija/oculta
        if (fijado === th) { ocultar(); } else { fijado = th; mostrar(th); }
      });
    }
    window.addEventListener("scroll", ocultar, { passive: true });
  })();


  /* La comparativa de fuentes, el gráfico de la brecha, la leyenda, las
     alertas, el catálogo de activaciones y las dos notas del cruce los
     escribe ahora el build (deploy/render_html.py, fase 6): eran seis
     contenedores que viajaban VACÍOS en el HTML y solo existían para quien
     ejecuta JavaScript. Dibujarlos aquí otra vez sería una segunda copia
     de la misma regla, que es como divergen. Con la cronología —que se
     mudó a referencia.html en la fase 6c y que ahora escribe
     render_html.py::cronologia_referencia— lo ÚNICO que sigue dibujando el
     navegador en esta página es el mapa, que es exploración y no archivo. */
})();
