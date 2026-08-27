/* Fichas municipales: pestañas accesibles y mapa de evidencias bajo demanda. */
(function () {
  "use strict";

  document.documentElement.classList.add("js-activo");

  const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  let leafletPromise;

  function cargarLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((resolve, reject) => {
      if (!document.getElementById("leaflet-css-municipio")) {
        const link = document.createElement("link");
        link.id = "leaflet-css-municipio";
        link.rel = "stylesheet";
        link.href = LEAFLET_CSS;
        document.head.appendChild(link);
      }
      const script = document.createElement("script");
      script.src = LEAFLET_JS;
      script.onload = () => resolve(window.L);
      script.onerror = () => {
        leafletPromise = undefined;
        script.remove();
        reject(new Error("No se pudo cargar Leaflet"));
      };
      document.head.appendChild(script);
    });
    return leafletPromise;
  }

  const esc = (valor) => window.UI.esc(valor);
  const css = (nombre) => window.UI.cssVar(nombre);
  const ficha = (opciones) => window.UI.fichaMapa(opciones);

  function fechaImagen(valor) {
    const m = /^(\d{4})[/-]?(\d{2})[/-]?(\d{2})(?:[ T](\d{2}:\d{2}))?\s*(UTC)?/
      .exec(String(valor || ""));
    if (!m) return valor || null;
    const dia = window.UI.fechaEs(`${m[1]}-${m[2]}-${m[3]}`);
    return m[4] ? `${dia}, ${m[4]}${m[5] ? " UTC" : ""}` : dia;
  }

  function gradoCopernicus(valor) {
    return ({ Destroyed: "Destruido", Damaged: "Dañado",
      "Possibly damaged": "Posiblemente dañado" })[valor] || valor || "Punto evaluado";
  }

  function colorGrado(valor) {
    return ({ Destroyed: css("--critical"), Damaged: "#ec835a",
      "Possibly damaged": css("--warning"),
      "Possible Damage": css("--warning"), Damage: "#ec835a" })[valor]
      || css("--muted");
  }

  function sumarBounds(bounds, capa) {
    const otros = capa.getBounds && capa.getBounds();
    if (otros && otros.isValid()) bounds.extend(otros);
  }

  /* Los chips que el build ya dejó escritos en la ficha, atados a sus capas.
     No se construyen aquí: el HTML servido los trae con su rótulo y su recuento
     —los cuenta el build sobre el mismo `evidencia.json` que este mapa dibuja—,
     y este código se limita a conectarlos. Construirlos en el navegador sería
     una segunda copia de los recuentos y volvería a dejar la tira vacía para
     quien lee el documento sin ejecutarlo.

     Devuelve `true` si encontró chips: es lo que le dice a quien llama que NO
     hace falta el control de capas de Leaflet. Un chip cuya capa no existe no
     puede accionar nada, así que se retira en vez de quedarse como control
     muerto — pero eso no debería pasar nunca: el build emite un chip por capa
     con puntos, la misma condición con que aquí se crea. */
  function conectarChips(contenedor, map, porCapa) {
    // Los chips viven en la fila `.vistas`, hermana del tabpanel, no dentro
    // del mapa: buscarlos en el tabpanel los perdía y Leaflet sacaba el
    // control de capas colapsado que los chips venían a sustituir.
    const raiz = contenedor.closest(".lienzo-mun")
      || contenedor.closest('[role="tabpanel"]') || document;
    const tira = raiz.querySelector(".chips-mapa");
    if (!tira) return false;
    let vivos = 0;
    for (const chip of tira.querySelectorAll(".chip[data-capa]")) {
      const capa = porCapa[chip.dataset.capa];
      if (!capa) {
        chip.remove();
        continue;
      }
      vivos += 1;
      chip.setAttribute("aria-pressed", String(map.hasLayer(capa)));
      chip.addEventListener("click", () => {
        const encendido = chip.getAttribute("aria-pressed") === "true";
        if (encendido) map.removeLayer(capa);
        else capa.addTo(map);
        chip.setAttribute("aria-pressed", String(!encendido));
      });
    }
    if (!vivos) tira.remove();
    return vivos > 0;
  }

  function construirMapa(contenedor, datos) {
    const L = window.L;
    const capas = datos.capas || {};
    const municipio = datos.municipio || {};
    const bounds = L.latLngBounds([]);
    const overlays = {};
    // Las mismas capas, indexadas por la clave con que viajan en evidencia.json
    // —que es la que el build escribe en `data-capa` de cada chip—. El objeto
    // `overlays` sigue existiendo porque es el que entiende `L.control.layers`,
    // el respaldo de cuando la ficha no trae chips.
    const porCapa = {};

    contenedor.replaceChildren();
    const map = L.map(contenedor, { scrollWheelZoom: false });
    contenedor._leafletMap = map;
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap", maxZoom: 18,
    }).addTo(map);

    if (municipio.lat != null && municipio.lon != null) {
      const centro = L.circleMarker([municipio.lat, municipio.lon], {
        radius: 7, color: css("--surface-1"), weight: 2,
        fillColor: css("--s8"), fillOpacity: 1,
      }).addTo(map).bindPopup(ficha({
        titulo: esc(municipio.nombre), subtitulo: esc(municipio.departamento),
        pie: "Cabecera municipal · DIVIPOLA",
      }));
      bounds.extend(centro.getLatLng());
    }

    const zonas = capas.zonas;
    if (zonas && zonas.features.length) {
      const capa = L.geoJSON(zonas, {
        style: () => ({ color: css("--good"), weight: 2, fillOpacity: 0.1 }),
        onEachFeature: (f, layer) => {
          const p = f.properties || {};
          layer.bindPopup(ficha({
            titulo: esc(p.aoi || "Zona analizada"),
            filas: [["Edificios afectados", p.edificios_afectados],
              ["Estado del cruce", esc(p.etiqueta || "")]],
            pie: "Copernicus EMS",
          }));
        },
      }).addTo(map);
      overlays[`Zonas analizadas (${zonas.features.length})`] = capa;
      porCapa.zonas = capa;
      sumarBounds(bounds, capa);
    }

    const copernicus = capas.copernicus;
    if (copernicus && copernicus.features.length) {
      const capa = L.geoJSON(copernicus, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: 5.5, weight: 1.5, color: css("--surface-1"), fillOpacity: 0.92,
          fillColor: colorGrado((f.properties || {}).damage_gra),
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties || {};
          layer.bindPopup(ficha({
            titulo: esc(gradoCopernicus(p.damage_gra)),
            filas: [["Tipo", esc(p.simplified || p.obj_type || "")],
              ["Zona", esc(p.aoi || "")],
              ["Método", esc(p.det_method || "")]],
            pie: "Copernicus EMS",
          }));
        },
      }).addTo(map);
      overlays[`Copernicus (${copernicus.features.length})`] = capa;
      porCapa.copernicus = capa;
      sumarBounds(bounds, capa);
    }

    const unosat = capas.unosat;
    if (unosat && unosat.features.length) {
      const capa = L.geoJSON(unosat, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: 5.5, weight: 1.5, color: css("--ink"), fillOpacity: 0.9,
          fillColor: colorGrado((f.properties || {}).dano),
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties || {};
          const dano = ({ Damage: "Daño observado", Damaged: "Daño observado",
            "Possible Damage": "Daño posible", Destroyed: "Destruido" })[p.dano]
            || p.dano || "Edificio evaluado";
          layer.bindPopup(ficha({
            titulo: esc(dano),
            filas: [["Imagen", esc([p.sensor, fechaImagen(p.sensor_date)]
              .filter(Boolean).join(", "))],
              ["Confianza", esc(p.confianza || "")],
              ["Validación en campo", esc(p.validacion_campo || "")]],
            pie: "UNITAR-UNOSAT",
          }));
        },
      }).addTo(map);
      overlays[`UNOSAT (${unosat.features.length})`] = capa;
      porCapa.unosat = capa;
      map.attributionControl.addAttribution("UNITAR-UNOSAT");
      sumarBounds(bounds, capa);
    }

    const sertit = capas.sertit;
    if (sertit && sertit.features.length) {
      const capa = L.geoJSON(sertit, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: 5.5, weight: 1.5, color: css("--surface-1"), dashArray: "2 3",
          fillOpacity: 0.9, fillColor: colorGrado((f.properties || {}).dano),
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties || {};
          layer.bindPopup(ficha({
            titulo: esc(gradoCopernicus(p.dano)),
            filas: [["Tipo", esc(p.tipo || "")],
              ["Imagen", esc([p.sensor, fechaImagen(p.sensor_date)]
                .filter(Boolean).join(", "))],
              ["Método", esc(p.metodo || "")]],
            pie: `${esc(p.copyright || "© ICube-SERTIT 2026")}` +
              (p.producto_id ? ` · producto ${esc(p.producto_id)}` : ""),
          }));
        },
      }).addTo(map);
      overlays[`ICube-SERTIT (${sertit.features.length})`] = capa;
      porCapa.sertit = capa;
      map.attributionControl.addAttribution("© ICube-SERTIT 2026");
      sumarBounds(bounds, capa);
    }

    const ciudadanos = capas.ciudadanos;
    if (ciudadanos && ciudadanos.features.length) {
      const capa = L.geoJSON(ciudadanos, {
        pointToLayer: (_f, latlng) => L.circleMarker(latlng, {
          radius: 5, color: css("--s7"), weight: 1.5,
          fillColor: css("--s7"), fillOpacity: 0.55,
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties || {};
          const esImagen = p.media && /\.(jpg|jpeg|png|webp)$/i.test(p.media);
          const medio = esImagen
            ? `<a href="${esc(p.media)}" target="_blank" rel="noopener"><img ` +
              `src="${esc(p.media)}" loading="lazy" alt="Foto ciudadana"></a>`
            : (p.media ? `<a href="${esc(p.media)}" target="_blank" ` +
              `rel="noopener">Ver medio</a>` : null);
          layer.bindPopup(ficha({
            titulo: "Reporte ciudadano", subtitulo: esc(p.time || ""),
            filas: [["Intensidad estimada (Mercalli)", p.mmi],
              ["", esc(p.mensaje || "")]],
            html: medio,
            pie: "ChatMap · en el punto que registró la fuente" +
              (p.score == null ? "" : ` · verificación automática: ${esc(p.score)}`),
          }));
        },
      }).addTo(map);
      overlays[`Reportes ciudadanos (${ciudadanos.features.length})`] = capa;
      porCapa.ciudadanos = capa;
      map.attributionControl.addAttribution("ChatMap · OSM Colombia");
      sumarBounds(bounds, capa);
    }

    if (!conectarChips(contenedor, map, porCapa)
        && Object.keys(overlays).length > 1) {
      // Respaldo, no norma: solo si la página no trajo chips. `L.control.layers`
      // se colapsa en un icono de capas por debajo de 560 px, así que en el
      // móvil —donde se lee la mitad de esto— las cinco fuentes quedaban
      // escondidas detrás de un símbolo que hay que descubrir.
      L.control.layers(null, overlays, {
        collapsed: matchMedia("(max-width: 560px)").matches,
      }).addTo(map);
    }
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), { maxZoom: 16 });
    else map.setView([municipio.lat, municipio.lon], 13);
    setTimeout(() => map.invalidateSize(), 0);
    // El mapa mide lo que mide el panel de al lado. Si el panel crece (grados
    // de daño, aviso), el mapa tiene que estirarse con él: si no, queda un
    // hueco o un mapa más bajo que sus datos. `invalidateSize` a mitad de una
    // animación la corta, así que solo se llama cuando el panel ya cambió.
    const panel = contenedor.closest(".lienzo-mun")?.querySelector(".panel");
    if (panel && window.ResizeObserver) {
      new ResizeObserver(() => map.invalidateSize()).observe(panel);
    }
  }

  async function cargarMapa(contenedor) {
    if (contenedor.dataset.estado === "listo") {
      contenedor._leafletMap.invalidateSize();
      return;
    }
    if (contenedor.dataset.estado === "cargando") return;
    contenedor.dataset.estado = "cargando";
    contenedor.setAttribute("aria-busy", "true");
    contenedor.innerHTML = '<div class="mapa-evidencias__placeholder" role="status">' +
      '<span aria-hidden="true"></span><p>Cargando mapa y evidencias…</p></div>';
    try {
      const [_, datos] = await Promise.all([
        cargarLeaflet(), window.UI.fetchJson(contenedor.dataset.evidencia),
      ]);
      if (!datos) throw new Error("No se pudo cargar el paquete municipal");
      construirMapa(contenedor, datos);
      contenedor.dataset.estado = "listo";
      contenedor.setAttribute("aria-busy", "false");
    } catch (_error) {
      contenedor.dataset.estado = "error";
      contenedor.setAttribute("aria-busy", "false");
      contenedor.innerHTML = '<div class="mapa-evidencias__error" role="alert">' +
        '<strong>No se pudo cargar el mapa.</strong><p>Puedes intentarlo de nuevo o ' +
        `<a href="${esc(contenedor.dataset.destino)}">abrir el mapa de la portada</a>.` +
        '</p><button type="button">Reintentar</button></div>';
      contenedor.querySelector("button").addEventListener("click", () => {
        contenedor.dataset.estado = "";
        cargarMapa(contenedor);
      });
    }
  }

  function activar(tab, enfocar) {
    const lista = tab.closest('[role="tablist"]');
    const caja = lista.closest("[data-mapa-tabs]");
    for (const otro of lista.querySelectorAll('[role="tab"]')) {
      const activo = otro === tab;
      otro.setAttribute("aria-selected", String(activo));
      otro.tabIndex = activo ? 0 : -1;
      document.getElementById(otro.getAttribute("aria-controls")).hidden = !activo;
    }
    if (enfocar) tab.focus();
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    const mapa = panel.querySelector(".mapa-evidencias");
    if (mapa) cargarMapa(mapa);
    const tira = caja.querySelector(".chips-mapa");
    if (tira) tira.hidden = !mapa;
    caja.dataset.vista = mapa ? "evidencias" : "situacion";
  }

  for (const lista of document.querySelectorAll("[data-mapa-tabs] [role=tablist]")) {
    const tabs = [...lista.querySelectorAll('[role="tab"]')];
    tabs.forEach((tab) => tab.addEventListener("click", () => activar(tab, false)));
    lista.addEventListener("keydown", (evento) => {
      const actual = tabs.indexOf(document.activeElement);
      if (actual < 0) return;
      let siguiente = null;
      if (evento.key === "ArrowRight") siguiente = (actual + 1) % tabs.length;
      if (evento.key === "ArrowLeft") siguiente = (actual - 1 + tabs.length) % tabs.length;
      if (evento.key === "Home") siguiente = 0;
      if (evento.key === "End") siguiente = tabs.length - 1;
      if (siguiente == null) return;
      evento.preventDefault();
      activar(tabs[siguiente], true);
    });
  }
})();
