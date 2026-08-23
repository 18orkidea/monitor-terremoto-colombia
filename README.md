# Monitor de brechas de reporte de desastres — Colombia

**🌐 [datosdelterremoto.org](https://datosdelterremoto.org/)** · terremoto M7.4 · 10-ago-2026 · San José del Palmar (Chocó)

Observatorio abierto del terremoto más fuerte registrado en Colombia en más de un siglo — y
del ecosistema de datos que lo rodea. No produce cifras nuevas: **audita las que existen** —
quién publica, quién calla, cuándo llega cada dato y qué queda subestimado. Todo con
actualización diaria automática y cada cifra rastreable hasta su petición de origen.

## Qué contiene

- **[Mapa interactivo](https://datosdelterremoto.org/)** — daño satelital punto a punto
  (1.578 edificios en 11 municipios con daño clasificado por tres servicios satelitales,
  contando una sola vez los que dos de ellos vieron a la vez: no es una suma de fuentes, es una unión de
  puntos —ver [DECISIONES](docs/DECISIONES.md)—), zonas
  de interés (AOI) con estado del cruce, intensidad
  ShakeMap, 542 reportes ciudadanos con coordenada recogidos por WhatsApp —536 con foto
  o vídeo— (ChatMap, al 22-ago-2026), municipios del área de influencia con población
  DANE, y 1.173 sismos históricos de contexto.
- **Fichas municipales** — cada municipio conserva un mapa de situación estático y, cuando
  tiene puntos satelitales o ciudadanos, ofrece un mapa de evidencias dentro de la misma
  página. Leaflet y el paquete recortado al municipio se cargan solo al abrir esa vista.
- **[Titulares](https://datosdelterremoto.org/noticias.html)** — 6.304 titulares del
  evento (al 22-ago-2026) emparejados por zona, desde GDACS-EMM y un **registro abierto
  de feeds**
  ([`feeds/registry.json`](feeds/registry.json)) al que cualquiera puede sumar un medio
  con un PR. Los medios regionales cambian el cruce: Istmina solo existe en la prensa del Chocó.
- **[Balances en medios](https://datosdelterremoto.org/balances.html)** — un worker con IA
  (Firecrawl + Qwen, cron diario) rastrea los balances publicados en prensa que citan
  fuentes oficiales (UNGRD, SGC, gobernaciones), extrae las cifras con su evidencia y las
  presenta como lo que son: *prensa que cita lo oficial*, nunca EDAN.
- **Cronología de la respuesta internacional** — UNOSAT, ECHO, Copernicus y entregas de
  producto en un solo hilo temporal.
- **Exportaciones** — CSV del cruce, GeoJSON por capa, JSON completo, feed RSS de balances.

## Las tres brechas que mide

1. **Brecha de reporte oficial** — Copernicus entrega daño clasificado por satélite en días;
   las fuentes oficiales abiertas de Colombia (UNGRD en datos.gov.co: parado en 2022;
   registro ArcGIS UNGRD: parado en feb-2024; SNIGRD: sin API pública) no cubren el evento — pero desde el 16-ago el RUD sí: la brecha pasó a ser municipal (municipios registrados vs sin registrar).
2. **Brecha de atención** — la cobertura mediática cae ~92 % en 5 días y toca mínimo el día
   en que se publican los datos de daño (Quibdó e Istmina, 14-ago), mientras el reporte
   ciudadano sigue subiendo.
3. **Brecha de cobertura** — población expuesta (PAGER/ShakeMap) fuera de las zonas
   mapeadas por satélite y sin reporte de ningún tipo: ~11,9 M de personas a MMI≥6, de las
   que las zonas mapeadas cubren el 8,7 %.

## Uso

```bash
python ingest/run_daily.py --backfill   # primera vez (enumera EMSR673+ e histórico UNGRD)
python ingest/run_daily.py              # corrida diaria (GitHub Actions la hace sola)
python -m http.server -d . 8000         # ver el mapa: http://localhost:8000/site/
```

Extracción privada de documentos oficiales con IA:

```bash
cd workers/ai-view
wrangler secret put INTERNAL_TOKEN
wrangler secret put QWEN_API_KEY
wrangler deploy
```

Ese Worker no expone inferencia pública: usa Qwen OCR para leer PDFs/imagenes oficiales,
guarda el resultado en KV y publica solo `/oficiales.json` y `/oficiales.rss`.

Tests (ciegos: verifican código, supuestos e hipótesis por separado):

```bash
python -m unittest tests.test_unit -v            # lógica pura, offline
python -m unittest tests.test_supuestos_api -v   # contratos de las APIs externas
python -m unittest tests.test_hipotesis -v       # afirmaciones del proyecto vs BD real
```

## Fuentes (todas verificadas con peticiones reales el 15-ago-2026)

| Fuente | Qué aporta | Acceso |
|---|---|---|
| [Copernicus EMS `public-activations`](https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR916) ([visor EMSR916](https://rapidmapping.emergency.copernicus.eu/EMSR916/)) | AOIs, productos, stats de daño, versiones, capas vectoriales | Público; `code` obligatorio; retención ≈ jul-2023→hoy; huecos puntuales normales |
| [USGS FDSN `us6000tjl2`](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2) | [ShakeMap](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2/shakemap/intensity) (rejilla+contornos MMI), [PAGER](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2/pager) (exposición), [DYFI](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2/dyfi/intensity) | Público |
| [GDACS EQ1557236](https://www.gdacs.org/report.aspx?eventid=1557236&episodeid=1724218&eventtype=EQ) | Evento, [feed EMM](https://www.gdacs.org/gdacsapi/api/emm/getemmnewsbykey?eventtype=EQ&eventid=1557236) (2.911 noticias), [feed institucional](https://www.gdacs.org/gdacsapi/api/news/getnewsbygdacskey?eventtype=EQ&eventid=1557236) | Público; ventana ~5 días → snapshot diario obligatorio |
| [GDELT 2.0 DOC](https://www.gdeltproject.org/) | Serie de volumen mediático | Público; máx. 1 petición/5 s |
| [Google News RSS](https://news.google.com/) | Búsqueda general del evento y búsquedas generadas por municipio de influencia | Público; agregador, se guarda snapshot por búsqueda |
| [UNGRD ArcGIS](https://services2.arcgis.com/YVLx8xYoDXKccDfJ/arcgis/rest/services/REGISTRO_DE_EMERGENCIAS_EN_COLOMBIA/FeatureServer/0) | 85k emergencias EDAN 1914→2024 (línea base) | Público |
| [Socrata `wwkg-r6te`](https://www.datos.gov.co/Ambiente-y-Desarrollo-Sostenible/Emergencias-UNGRD-/wwkg-r6te) | El mismo registro hasta 2022 (métrica de brecha) | Público |
| [DANE proyecciones municipales](https://www.dane.gov.co/index.php/estadisticas-por-tema-2/demografia-y-poblacion/proyecciones-de-poblacion) | Población municipal 2026 total, cabecera y rural (serie por área 2018-2042) | Público; XLSX oficial. Referencia estática: se captura una vez al año (workflow `dane.yml`), no en la corrida diaria — el servicio es intermitente y el dato no cambia |
| [DIVIPOLA geolocalizado `gdxc-w37w`](https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-municipios/gdxc-w37w) | Centroide y código de los 1.122 municipios: cualquier municipio que entre al RUD resuelve coordenadas sin curación manual | Público (Socrata, `$limit` explícito); referencia estática — se regenera a mano con `ingest/build_divipola.py`, no en la corrida diaria |
| [ChatMap OSM Colombia](https://chatmap.hotosm.org/colombia.html) ([uMap](https://umap.hotosm.org/en/map/colombia-m-74-earthquake-10-ago-2026_3482), [proyecto HOT](https://www.hotosm.org/en/projects/2026-colombia-earthquake-response/)) | 542 reportes ciudadanos con coordenada, 536 con foto o vídeo (WhatsApp→mapa; al 22-ago-2026) | Endpoint de activación: puede cerrar; medios copiados localmente |
| [UNGRD RUD](https://rud.gestiondelriesgo.gov.co/) (`/home/json.php?temp=2026T`) | **La primera fuente oficial que cubre el evento**: damnificados por municipio (familias, personas, viviendas), cargado por autoridades locales | Público de lectura, NO documentado (descubierto 16-ago); vigilado por test de supuesto |
| [UNITAR-UNOSAT](https://unosat.org/products/4253) (`/our_products/`, `/our_products/<id>`) | **La segunda mirada satelital**: 548 edificios evaluados uno a uno en Anserma, Manizales y Viterbo (Caldas) y en Zarzal (Valle del Cauca), donde Copernicus no cartografía nada —443 de ellos son «daño posible», hipótesis de la fuente sin validar en campo—. De esos 548, 209 traen un código de evento que no coincide con el que declara su propio producto y que está fechado después de la imagen que los retrata: la fuente se contradice a sí misma. Cuentan —manda el identificador del producto— y se publican marcados en `unosat_codigo_inconsistente`, nunca reescritos ([por qué](docs/LIMITACIONES.md)). Viterbo pasó de 154 edificios a 108 porque UNOSAT reeditó su propia evaluación: se publica la vigente y la anterior sobrevive en los snapshots. Shapefiles leídos con stdlib | Público, sin clave ni API documentada; licencia no declarada ([UNITAR legal](https://www.unitar.org/legal)). El listado es una ventana fija de 11 productos sin paginar: el módulo consulta también los ids ya vistos para no perder el histórico |
| [ICube-SERTIT](https://sertit.unistra.fr/cartographie-rapide/cartoaction/845/) (catálogo por HTTP; vectores por correo) | **La tercera mirada satelital**: 512 puntos en Pereira (252), Cali (103), Roldanillo (77), La Virginia (49) y Manizales (31), de los que **503 traen grado de daño** — los otros 9, todos en Cali, la fuente los señaló sin clasificarlos y no cuentan como daño clasificado, dentro de la activación 1048 de la Charter que pidió la UNGRD. **Roldanillo y La Virginia no los ha mirado ningún otro servicio.** Comparte vocabulario de daño con Copernicus, así que las dos capas se leen con la misma leyenda | Los mapas son públicos como PDF/JPG; **los vectores no se descargan**: su web los manda por correo tras un formulario. Se pidieron el 20-ago-2026 y se recibieron el 21, y viven en `data/documentos/sertit/` con su sha256. Licencia **no comercial** con atribución obligatoria «© ICube-SERTIT 2026» y logo — más restrictiva que el resto del monitor ([por qué](docs/LIMITACIONES.md)) |
| [EMSC seismicportal](https://www.seismicportal.eu/) | 1.339 felt reports (contraste con DYFI) | Público |
| Worker interno `monitor-terremoto-colombia-oficiales-ai` | Monitoreo de canales oficiales y extracción estructurada de documentos con `qwen-vl-ocr-2025-11-20` | Privado para inferencia; público solo JSON/RSS estructurado |

Sin acceso programático (documentado, no usado): [SNIGRD](https://sni.gestiondelriesgo.gov.co/)/geoportal
UNGRD (Keycloak), [SGC Sismo Sentido](https://sismosentido2.sgc.gov.co/) (SPA sin API),
ReliefWeb (requiere appname).

## Recibir alertas

Tres canales, mismo contenido (cambios del RUD, balances en medios y del propio
monitor — nivel alta y pulso diario), con un solo punto de envío y dedupe:

- **🔔 Notificaciones del navegador**: botón «Alertas» en la barra del sitio
  (Web Push estándar; en iPhone/iPad requiere instalar la PWA: Compartir →
  «Añadir a pantalla de inicio»). Criptografía propia testeada contra el vector
  del RFC 8291 — sin terceros.
- **Canal de Telegram**: enlace en el pie del sitio.
- **RSS**: [`alerts.rss`](https://datosdelterremoto.org/data/public/alerts.rss)
  (alertas del día) y el RSS de balances del worker.

Detalles de operación en [workers/push/README.md](workers/push/README.md).

## Acrónimos básicos

- **AOI**: área de interés definida por Copernicus.
- **CDI/DYFI**: intensidad ciudadana calculada por USGS a partir de reportes "Did You Feel It?".
- **DANE/PPED**: proyecciones oficiales de población usadas para población municipal 2026.
- **DIVIPOLA**: codificación oficial colombiana de departamentos y municipios.
- **EDAN**: Evaluación de Daños y Análisis de Necesidades; es la evidencia oficial exigida para declarar coincidencia.
- **EMM/GDACS**: rastreador de noticias y sistema global de alertas/coordinación de desastres.
- **MMI/ShakeMap/PAGER**: intensidad estimada, mapa de sacudida y exposición/pérdidas probables de USGS.
- **OCR/Qwen**: reconocimiento y parsing de documentos visuales; se usa solo como extracción asistida, no como fuente oficial.
- **RSS/Atom**: formatos de feeds abiertos usados para ingerir medios y agregadores.

## Reglas de rigor

- **`Coincide cualitativamente` exige evidencia oficial** (EDAN/entidad estatal). Prensa y
  reportes ciudadanos alimentan estados intermedios explícitos; nunca promueven solos.
- Los `"NA"` de Copernicus se conservan como NULL + literal crudo — jamás se convierten en 0.
- Los reportes ciudadanos se sitúan **en el punto que registró ChatMap**, sin reposicionar:
  el redondeo anterior a ~110 m movía la foto a la casa de enfrente. El EXIF nunca se publica
  (verificado: 0 de 355 fotos traen EXIF — WhatsApp lo elimina). Nota de transparencia:
  la base `data/monitor.sqlite` y los snapshots crudos conservan la coordenada original
  de ChatMap porque son el registro de trazabilidad — el mismo dato que la fuente
  (chatmap.hotosm.org) ya publica en abierto; el redondeo es una capa de prudencia en la
  presentación, no un secreto.
- Toda cifra es rastreable: `sources_log` (URL, HTTP, sha256, timestamp) + snapshot inmutable
  en `data/snapshots/YYYY-MM-DD/`.

## Quién mira desde el aire, y quién no

`docs/INVESTIGACION-SATELITES.md` inventaria las miradas satelitales del
terremoto: las 495 escenas de doce misiones que movilizó la Charter
Internacional, los quince productos públicos que salieron de ellas —de los que
el monitor ingiere los de tres equipos—, el producto de movimiento del terreno
que Copernicus prometió y acabó declarando no producible, el interferograma
NISAR abierto que nadie ha explotado, y los operadores comerciales que abrieron
datos para otros desastres y no para este. Es la base probatoria de lo que este
repositorio afirma sobre la cobertura satelital.

## Extensión documentada: asentamientos bajo dosel

Para señalar población invisible al mapeo óptico (ríos de Chocó bajo selva): HRSL de Meta
(densidad ~30 m, [descarga HDX](https://data.humdata.org/dataset/2f865527-b7bf-466c-b620-c12b8d07a053)),
[Google Open Buildings v3](https://sites.research.google/gr/open-buildings/) (huellas de
edificios a 50 cm, cubre Colombia) y SAR banda L ([NISAR](https://science.nasa.gov/mission/nisar/data/),
datos abriéndose en 2026). El LiDAR "arqueológico" bajo dosel denso sigue siendo
aerotransportado y no hay cobertura pública de Chocó.

## Estructura

```
ingest/           # pipeline (solo stdlib de Python)
  sources/        # un módulo por fuente; toda petición pasa por common.fetch()
  crosscheck.py   # las 5 categorías del cruce
  verify_citizen.py, alerts.py, publish.py, run_daily.py
data/
  monitor.sqlite  # series + procedencia (NO versionado: se reconstruye de dumps/)
  dumps/          # los CSV que sí van a git: de aquí renace la base en un clon
  documentos/     # cuerpos entregados fuera de banda (ICube-SERTIT, por correo)
  snapshots/      # respuestas crudas por día (inmutables)
  media/          # fotos ciudadanas (videos en R2, hash registrado)
  public/         # artefactos que consume el mapa
site/             # Leaflet sin build: index.html + app.js + styles.css
workers/ai-view/ # Worker privado: lee documentos oficiales con Qwen OCR y publica JSON/RSS
tests/            # ciegos: unit (código), supuestos (APIs), hipótesis (datos)
```
