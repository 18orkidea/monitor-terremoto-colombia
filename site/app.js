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
  // hitos del feed institucional GDACS (patrones)
  const tHito = (s) => (s || "")
    .replace(/UNITAR-UNOSAT Activation/i, "Activación UNITAR-UNOSAT")
    .replace(/EC\/ECHO daily map/i, "Mapa diario EC/ECHO")
    .replace(/Copernicus EMS activation/i, "Activación Copernicus EMS")
    .replace(/^M7\.4 in Colombia/i, "M7.4 en Colombia");

  const j = window.UI.fetchJson;
  const base = "/data/public/";
  // La MISMA fuente que balances.html: el producto propio, no el worker en
  // vivo. Leyendo cada página de un sitio distinto, la portada enseñaba el
  // corte del worker y balances.html el archivado, y las dos podían dar
  // cifras y fechas distintas del mismo día. Además el sitio deja de depender
  // de que un worker en cuenta ajena siga en pie.
  const OFFICIAL_FEED = `${base}oficiales.json`;
  // `alerts.json` ya no se pide: las alertas las escribe el build (fase 6), y
  // pedirlo aquí era descargarlo para no usarlo.
  const [mon, aois, municipios, chat, dyfi, sismos, shake,
         dmgPts, dmgLines, notAnalysed, unosat, sertit, oficiales,
         hitosCurados, sinMirada] = await Promise.all([
    j(base + "monitor.json"), j(base + "aois.geojson"), j(base + "municipios.geojson"),
    j(base + "chatmap.geojson"),
    j(base + "dyfi_cells.geojson"), j(base + "ungrd_sismos.geojson"),
    j(base + "shakemap_mmi.geojson"),
    j(base + "damage_points.geojson"), j(base + "damage_lines.geojson"),
    j(base + "not_analysed.geojson"), j(base + "unosat_damage.geojson"),
    j(base + "sertit_damage.geojson"),
    j(OFFICIAL_FEED),
    j(base + "hitos_monitor.json"),
    j(base + "municipios_mapa.json"),
  ]);
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

  const layers = {};
  if (shake) {
    layers["Intensidad estimada por el USGS"] = L.geoJSON(shake, {
      style: (f) => ({ color: "#8a5a00", weight: 1, opacity: 0.5, dashArray: "4 3" }),
      onEachFeature: (f, l) => l.bindTooltip(
        `Intensidad ${f.properties.value ?? "—"} en la escala de Mercalli modificada`),
    }).addTo(map);
  }
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
  if (sinMirada && sinMirada.items && sinMirada.items.length) {
    // El rótulo cuenta lo que se PINTA, no lo que trae el fichero: si algún
    // municipio llegara sin coordenadas, la etiqueta prometería más puntos de
    // los que hay. Es la divergencia de los «36 en portada, 43 en la tabla».
    const conCoords = sinMirada.items.filter((m) => m.lat != null && m.lon != null);
    const capa = L.geoJSON({
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
        radius: 7, weight: 1.5, opacity: 0.75, fillOpacity: 0.12,
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
    }).addTo(map);
    capa.bringToBack();
    // «con damnificados» NO es adorno: sin esa condición el rótulo enuncia un
    // predicado que da 197, y municipios.html publica justo ese —Palmira no
    // tiene registro en el RUD y sí entra en su cuenta—. Dos páginas del mismo
    // sitio con dos cifras del mismo hecho es el fallo de los «36 y 43».
    layers[`Municipios con damnificados y sin producto de daño satelital `
           + `(${fmt(conCoords.length)})`] = capa;
  }

  const aoiLayerById = {};
  const munLayerById = {};
  if (aois) {
    layers["Zonas que analizó Copernicus"] = L.geoJSON(aois, {
      style: (f) => ({
        color: ESTADO_COLOR[f.properties.estado] || css("--muted"),
        weight: 2, fillOpacity: 0.12,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        aoiLayerById[p.aoi] = l;
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
    }).addTo(map);
    map.fitBounds(layers["Zonas que analizó Copernicus"].getBounds().pad(0.15));
  } else { map.setView([4.5, -76.3], 8); }

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
  if (dmgPts && dmgPts.features.length) {
    const edificios = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer === "builtUpP") };
    const crisis = { type: "FeatureCollection",
      features: dmgPts.features.filter((f) => f.properties.layer !== "builtUpP") };
    layers[`Edificios dañados — satélite (${edificios.features.length})`] =
      L.geoJSON(edificios, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: 5.5, weight: 1.5, color: "#fff", fillOpacity: 0.9,
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
      }).addTo(map);
    if (crisis.features.length) {
      layers[`Interrupciones / crisis (${crisis.features.length})`] =
        L.geoJSON(crisis, {
          pointToLayer: (f, ll) => L.circleMarker(ll, {
            radius: 6, weight: 2, color: css("--critical"),
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
        }).addTo(map);
    }
  }
  if (dmgLines && dmgLines.features.length) {
    layers[`Vías dañadas — satélite (${dmgLines.features.length})`] =
      L.geoJSON(dmgLines, {
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
      }).addTo(map);
  }
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
  if (unosat && unosat.features.length) {
    const UNOSAT_COLOR = {
      "Damage": "#ec835a", "Damaged": "#ec835a",
      "Possible Damage": css("--warning"), "Destroyed": css("--critical"),
    };
    layers[`Edificios evaluados — satélite UNOSAT (${unosat.features.length})`] =
      L.geoJSON(unosat, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: 5.5, weight: 1.5, color: "#2b2b2b", fillOpacity: 0.9,
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
      }).addTo(map);
  }

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
  if (sertit && sertit.features.length) {
    layers[`Edificios evaluados — satélite ICube-SERTIT (${sertit.features.length})`] =
      L.geoJSON(sertit, {
        pointToLayer: (f, ll) => L.circleMarker(ll, {
          radius: 5.5, weight: 1.5, color: "#fff", dashArray: "2 3",
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
      }).addTo(map);
  }

  if (notAnalysed && notAnalysed.features.length) {
    layers[`Zonas sin analizar (${notAnalysed.features.length})`] =
      L.geoJSON(notAnalysed, {
        style: () => ({ color: css("--muted"), weight: 1, dashArray: "3 4",
                        fillColor: css("--muted"), fillOpacity: 0.18 }),
        onEachFeature: (f, l) => l.bindTooltip(
          `Sin analizar (${aoiEs(f.properties.aoi)}) — hueco de cobertura`),
      });
  }

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
  if (chat) {
    layers[`Reportes ciudadanos ChatMap (${chat.features.length})`] = L.geoJSON(chat, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: 5, color: css("--s7"), weight: 1.5,
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
    }).addTo(map);
  }
  if (dyfi) {
    layers["Intensidad que sintió la población"] = L.geoJSON(dyfi, {
      style: (f) => {
        const c = f.properties.cdi || 0;
        const op = Math.min(0.65, 0.08 + c * 0.07);
        return { color: css("--s1"), weight: 0.5, fillColor: css("--s1"), fillOpacity: op };
      },
      onEachFeature: (f, l) => l.bindTooltip(
        `Intensidad percibida ${f.properties.cdi} · ` +
        `${f.properties.nresp} respuestas ciudadanas`),
    });
  }
  if (sismos) {
    layers[`Sismos históricos UNGRD (${sismos.features.length})`] = L.geoJSON(sismos, {
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        radius: 3, color: css("--muted"), weight: 1, fillOpacity: 0.4,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindTooltip(`${p.fecha ?? "?"} · ${p.municipio ?? ""} (${p.departamento ?? ""})`);
      },
    });
  }
  if (municipios && municipios.features.length) {
    // colores desde la tabla única de ui.js (misma etiqueta que la tabla)
    const MUN_COLOR = Object.fromEntries(
      Object.entries(window.UI.ESTADO_MUNICIPIO)
        .map(([k, [, v]]) => [k, css(v)]));
    layers[`Municipios con señal: RUD, prensa o intensidad (${municipios.features.length})`] =
      L.geoJSON(municipios, {
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
      }).addTo(map);
  }
  L.control.layers(null, layers, { collapsed: true }).addTo(map);

  // el grid asienta su tamaño tarde: reencuadrar cuando el contenedor cambie
  const aoiBounds = layers["Zonas que analizó Copernicus"] &&
    layers["Zonas que analizó Copernicus"].getBounds();
  let lastW = map.getSize().x;
  new ResizeObserver(() => {
    const w = document.getElementById("map").clientWidth;
    if (Math.abs(w - lastW) > 4) {
      lastW = w;
      map.invalidateSize();
      if (aoiBounds && aoiBounds.isValid()) map.fitBounds(aoiBounds.pad(0.15));
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

  // ---- cronología unificada: respuesta internacional + local + hitos del monitor
  //      (feed institucional GDACS + entregas Copernicus + fichero curado + derivados)
  const ETIQUETA_TIPO = { institucional: "internacional", entrega: "internacional",
                          internacional: "internacional", evento: "evento",
                          local: "local", monitor: "monitor" };
  const hitos = [
    ...(mon.institucional || []).map((h) => ({
      fecha: h.fecha, texto: tHito(h.titulo), url: h.url, tipo: "institucional" })),
    ...(mon.entregas || []).map((e) => ({
      fecha: e.fecha, tipo: "entrega",
      texto: `Copernicus entrega datos de daño: ${aoiEs(e.aoi)} (${t(e.producto)} / ${e.producto} v${e.version})` })),
    ...((hitosCurados && hitosCurados.hitos) || []).map((h) => ({
      fecha: h.fecha, texto: h.texto, resumen: h.resumen,
      url: h.url, tipo: h.tipo })),
  ].filter((h) => h.fecha).sort((x, y) => y.fecha.localeCompare(x.fecha));
  // hitos automáticos, derivados de los propios datos (sin curación manual):
  // primer balance en medios, alta del RUD y purga de la serie EMM.
  {
    const fechas = ((oficiales && oficiales.items) || [])
      .map((x) => x.search_date).filter(Boolean).sort();
    if (fechas.length) hitos.push({
      fecha: fechas[0], tipo: "local", url: "balances.html",
      texto: "Primer balance en medios que cita fuentes oficiales —la UNGRD y el Servicio " +
        "Geológico Colombiano— rastreado por el monitor" });
    const rudSerie = (mon.rud && mon.rud.serie) || [];
    if (rudSerie.length) hitos.push({
      fecha: rudSerie[0].fecha, tipo: "local", url: "rud.html",
      texto: `El RUD de la UNGRD cubre el evento: primera fuente oficial abierta ` +
        `(${fmt(rudSerie[0].municipios)} municipios, ${fmt(rudSerie[0].familias)} familias registradas)` });
    const mv = mon.media_volume || [];
    const ultEmm = mv.map((d, i) => d.emm != null ? i : -1).filter((i) => i >= 0).at(-1);
    if (ultEmm != null && ultEmm < mv.length - 1) hitos.push({
      fecha: mv[ultEmm + 1].fecha, tipo: "monitor",
      resumen: "GDACS purga su serie global de noticias; el monitor conserva la copia.",
      texto: `El sistema europeo de alertas GDACS borra su serie global de noticias ` +
        `(último dato: ${window.UI.fechaLarga(mv[ultEmm].fecha)}); solo sobrevive en las ` +
        `copias que archiva el monitor, que sigue midiendo con sus canales abiertos` });
    hitos.sort((x, y) => y.fecha.localeCompare(x.fecha));
  }
  const timelineEl = document.getElementById("timeline");
  const chipsEl = document.getElementById("crono-filtros");
  const FILTROS = [["todos", "Todos"], ["internacional", "🌍 Internacional"],
                   ["local", "🇨🇴 Local/oficial"], ["monitor", "🔧 Monitor"]];
  function pintaCronologia(filtro) {
    const vista = hitos.filter((h) => filtro === "todos" ||
      ETIQUETA_TIPO[h.tipo] === filtro || h.tipo === "evento");
    timelineEl.innerHTML = vista.map((h) => {
      // El resumen sirve en la banda gráfica; en la cronología los cambios del
      // monitor necesitan contexto y el CSS ya limita su lectura a cuatro líneas.
      const visible = h.tipo === "monitor" ? h.texto : (h.resumen || h.texto);
      const contenido = h.url
        ? `<a href="${window.UI.esc(h.url)}" target="_blank" rel="noopener" ` +
          `title="${window.UI.esc(h.texto)}">${window.UI.esc(visible)}</a>`
        : `<span title="${window.UI.esc(h.texto)}">${window.UI.esc(visible)}</span>`;
      return `<li class="${h.tipo}"><span class="t-fecha">${window.UI.fechaEs(h.fecha)}` +
        `${h.fecha.length >= 16 ? `, ${h.fecha.slice(11, 16)}` : ""}</span> ` +
        `<span class="t-tipo">${ETIQUETA_TIPO[h.tipo] || h.tipo}</span>` +
        `<span class="t-texto">${contenido}</span></li>`;
    }).join("") || "<li>Sin hitos registrados aún.</li>";
  }
  if (chipsEl) {
    chipsEl.innerHTML = FILTROS.map(([k, label], i) =>
      `<button class="chip${i ? "" : " activa"}" data-filtro="${k}">${label}</button>`).join("");
    chipsEl.addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      chipsEl.querySelectorAll(".chip").forEach((c) => c.classList.toggle("activa", c === b));
      pintaCronologia(b.dataset.filtro);
    });
  }
  pintaCronologia("todos");

  // Las activaciones de Colombia, las dos notas del cruce y la leyenda del
  // mapa las escribe el build desde la fase 6 (render_html.py::
  // activaciones_colombia, nota_rud_desde, nota_sin_registro y
  // leyenda_portada). La rampa de color de la ausencia sigue aquí porque el
  // mapa pinta con ella 196 anillos; su espejo en Python está declarado en
  // render_html.py::_color_ausencia.

  // ---- banda de hitos: la única serie que sigue dibujando el navegador
  const fechaEvento = (hitos.find((h) => h.tipo === "evento") || {}).fecha;
  const mediaGrafico = window.UI.serieDesde(mon.media_volume || [], fechaEvento);
  drawCronoBanda(mediaGrafico, hitos);

  // eje X de la banda de hitos. Lo compartía con la gráfica de volumen, que
  // ya no existe: el gráfico de la portada es la brecha y lo escribe el build.
  function ejeX(el, media) {
    const W = Math.max(680, Math.min(el.clientWidth || 900, 1100));
    const M = { t: 28, r: 16, b: 40, l: 48 };
    const x = (i) => M.l + (i + 0.5) * (W - M.l - M.r) / media.length;
    return { W, M, x };
  }

  /* Banda de cronología: los hitos separados del volumen, misma escala de fechas.
     Tres carriles (internacional / local-oficial / monitor); ▲ = entrega Copernicus. */
  function drawCronoBanda(media, hitosCrono) {
    const el = document.getElementById("crono-banda");
    if (!el || !media.length) return;
    const { W, M, x } = ejeX(el, media);
    const LANES = [
      { key: "internacional", emoji: "🌍", nombre: "Respuesta internacional", color: css("--s1") },
      { key: "local", emoji: "🇨🇴", nombre: "Respuesta local/oficial", color: css("--good") },
      { key: "monitor", emoji: "🔧", nombre: "Cambios del monitor", color: css("--warning") },
    ];
    const laneDe = (h) => h.tipo === "institucional" || h.tipo === "entrega" ||
      h.tipo === "internacional" ? 0 :
      (h.tipo === "local" || h.tipo === "evento" ? 1 : 2);
    const LH = 26, H = 6 + LANES.length * LH + 18;
    const dayIdx = Object.fromEntries(media.map((d, i) => [d.fecha, i]));
    // agrupar por carril+día para repartir los marcadores del mismo día
    const grupos = {};
    for (const h of (hitosCrono || [])) {
      const i = dayIdx[(h.fecha || "").slice(0, 10)];
      if (i != null) (grupos[`${laneDe(h)}|${i}`] ||= []).push(h);
    }
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Hitos de la respuesta por día y por tipo">`;
    // rejilla vertical por día (misma posición que las barras de arriba)
    media.forEach((d, i) => {
      s += `<line x1="${x(i)}" x2="${x(i)}" y1="4" y2="${H - 16}" stroke="${css("--grid")}" stroke-width="1" stroke-dasharray="2 3"/>` +
        `<text x="${x(i)}" y="${H - 4}" text-anchor="middle" font-size="9" fill="${css("--muted")}">${window.UI.diaMes(d.fecha)}</text>`;
    });
    LANES.forEach((lane, li) => {
      const yy = 6 + li * LH + LH / 2;
      s += `<text x="${M.l - 8}" y="${yy + 4}" text-anchor="end" font-size="12">${lane.emoji}<title>${lane.nombre}</title></text>`;
      if (li) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${6 + li * LH}" y2="${6 + li * LH}" stroke="${css("--grid")}" stroke-width="0.5"/>`;
    });
    for (const [clave, dia] of Object.entries(grupos)) {
      const [li, i] = clave.split("|").map(Number);
      const yy = 6 + li * LH + LH / 2;
      dia.forEach((h, k) => {
        const xx = x(i) + (k - (dia.length - 1) / 2) * 11;
        const texto = `${window.UI.fechaLarga(h.fecha)} · ${(ETIQUETA_TIPO[h.tipo] || h.tipo)} · ` +
          (h.resumen || h.texto).replaceAll('"', "&quot;");
        const color = h.tipo === "evento" ? css("--critical") : LANES[li].color;
        s += h.tipo === "entrega"
          ? `<path data-hito="${texto}" d="M ${xx - 5} ${yy - 4} l 10 0 l -5 9 z" fill="${css("--critical")}"/>`
          : h.tipo === "evento"
            ? `<text data-hito="${texto}" x="${xx}" y="${yy + 5}" text-anchor="middle" font-size="13" fill="${color}">★</text>`
            : `<circle data-hito="${texto}" cx="${xx}" cy="${yy}" r="5" fill="${color}" stroke="${css("--surface-1")}" stroke-width="1.5"/>`;
      });
    }
    s += `</svg>`;
    el.innerHTML = s;
    window.UI.attachTooltip(el, (t) =>
      t.dataset.hito ? `<strong>Hito</strong><br>${t.dataset.hito}` : null);
  }

  /* La comparativa de fuentes, el gráfico de la brecha, la leyenda, las
     alertas, el catálogo de activaciones y las dos notas del cruce los
     escribe ahora el build (deploy/render_html.py, fase 6): eran seis
     contenedores que viajaban VACÍOS en el HTML y solo existían para quien
     ejecuta JavaScript. Dibujarlos aquí otra vez sería una segunda copia
     de la misma regla, que es como divergen (M2). Lo único que sigue
     dibujando el navegador en esta página es el mapa y la banda de
     cronología, que son exploración y no archivo. */
})();
