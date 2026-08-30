# Arquitectura del monitor

Mapa técnico del proyecto. La misión y las reglas viven en [CLAUDE.md](../CLAUDE.md);
las decisiones fechadas en [DECISIONES.md](DECISIONES.md); las lagunas conocidas en
[LIMITACIONES.md](LIMITACIONES.md).

## Flujo de datos

```
14 fuentes externas ──► ingest/sources/*.py ──► sqlite (17 tablas) ──► ingest/publish.py
  (todas vía                  │                      │                        │
   common.fetch())      snapshots crudos      cruce + verificación      data/public/*
                        data/snapshots/       (crosscheck.py,          (JSON/CSV/GeoJSON)
                        YYYY-MM-DD/ + sha256   verify_citizen.py,             │
                        en sources_log         alerts.py)                site/*.html+js
                                                                        (frontend sin build)

worker aparte: workers/ai-view (Cloudflare, cron 23:00 Col) ──► KV ──► /oficiales.json
  balances en medios: las cifras se extraen con reglas de texto deterministas,
  no con un modelo de lenguaje —el modelo solo hace OCR de documentos
  escaneados—; snapshot diario al repo en feeds/balances/

worker aparte: workers/push (Cloudflare) ──► Web Push cifrado + canal Telegram
  el daily le manda alerts.json fresco (POST con Bearer); cron 11:20 UTC de
  respaldo; dedupe por sha256; suscripciones en KV PUSH_SUBS; alerts.rss
  estático como tercer canal (generado por alerts.py)
```

- **`ingest/common.py`** es el corazón: `fetch()` (única puerta a la red: log +
  sha256 + snapshot), esquema sqlite, `to_num` (NA≠0).
  - **Pregunta antes de descargar.** Si el archivo ya tiene una copia utilizable
    de esa URL, `fetch()` manda `If-None-Match` con su ETag y `If-Modified-Since`
    con su Last-Modified (guardados en `sources_log.etag` / `.last_modified`).
    Un **304 no descarga cuerpo y deja igualmente su fila**, con `http_status`
    304, `bytes` 0 y el `sha256`/`snapshot_path` de la copia vigente: preguntar
    y que contesten «lo mismo» es un hecho sobre la fuente, y se archiva como
    tal. Al llamante le llega el cuerpo vigente con su 200 — si un 304 llegara
    vacío, el día que Copernicus dijera «sin cambios» el mapa perdería sus 16
    capas. `common.py::copia_vigente` · `test_unit.py::TestPeticionesCondicionales`
  - **Solo se pregunta condicionalmente por lo que se puede servir del archivo**:
    `copia_vigente()` exige que el fichero esté en disco y que su sha256 cuadre
    con el log. Es el invariante que impide que un 304 deje al llamante sin
    cuerpo o al log con un sha sin nada detrás. Los vídeos ciudadanos viven en
    R2 y no en el repo, así que por ellos no se pregunta — y por eso necesitan
    el mecanismo de abajo, que es otro.
  - **Un activo se archiva una vez.** `activo_archivado()` responde «¿este
    cuerpo ya es nuestro?» preguntando **al archivo** —el cuerpo en disco, si
    está; `citizen_reports.media_sha256`; `data/r2_manifest.json`— y no al
    sistema de ficheros, que en la máquina de la corrida arranca vacío de todo
    lo que git ignora. Si la base y el manifiesto se contradicen **devuelve
    None**: un archivo que se desmiente a sí mismo no autoriza a saltarse nada,
    y la contradicción se canta (`alerts.divergencias_del_archivo_de_activos`).
    La distinción es dato/activo: un cuerpo que puede cambiar se pregunta cada
    día; un vídeo con URL propia —un UUID que ChatMap acuña al subirlo— no. Y
    solo alcanza a lo que git NO versiona (`ARCHIVO_EN_R2`): para una foto, que
    viaja en el clon, el archivo es el disco y si falta se vuelve a traer.
    `common.py::activo_archivado` · `test_unit.py::TestActivosDelArchivo`
  - **Un contenido idéntico no se archiva dos veces.** Si la fuente no soporta
    condicionales y manda 200 con un cuerpo que ya está archivado, la fila
    apunta a la copia existente y **no se escribe un fichero nuevo**. Nada se
    sobrescribe ni se migra: deja de escribirse una copia redundante. La regla
    es **por contenido y por URL, nunca por una lista de fuentes «estáticas»** —
    una fuente que hoy no cambia puede cambiar mañana y el mecanismo se entera
    solo.
- **`ingest/run_daily.py`** orquesta: cada fuente es un `step()` que puede fallar sin
  tumbar la corrida (R13).
- **`ingest/crosscheck.py`** aplica la cadena de estados por AOI:
  `no_comparable → coincide → prensa → ciudadano → pendiente` (R1/R2).
- **`ingest/publish.py`** genera todos los artefactos públicos de `data/public/`
  (`lat_pub/lon_pub` son la coordenada tal como llega, sin reposicionar — R5). Entre ellos
  `municipios_mapa.json`, la capa de la ausencia: los municipios con registro
  en el RUD y sin ninguna evaluación satelital, con la intensidad estimada del USGS.
  Va aparte de `municipios.json` porque el mapa no necesita los titulares que
  ese arrastra, y se filtra aquí y no en el navegador para que la cifra que se
  publica y los puntos que se pintan salgan del mismo recuento
  (`municipios.py::capa_sin_mirada`).
- **`ingest/geo.py`** geometría sin dependencias: WKT, punto-en-polígono y
  `MMIGrid` sobre el ShakeMap del USGS. `grid_mmi_vigente()` localiza la rejilla
  más reciente del archivo y la comparten la verificación ciudadana y la capa de
  municipios.
- **`site/`** es frontend estático sin build: `ui.js` (componentes compartidos:
  `fmt`, `norm`, `tablaBuscable`, `metricCards`, `attachTooltip`,
  `comparativaFuentes`, `isLiveblog`/`bestSnapshot`), `common.js` (lo que solo
  puede hacer el navegador: compartir, alertas push, abrir el `<details>` de un
  ancla y filtrar la cronología de `referencia.html`) y un JS por página.
  **En la portada, `app.js` ya solo dibuja el mapa**: desde la fase 6c la
  cronología también la escribe el build
  (`render_html.py::cronologia_referencia`), y lo vigila
  `test_render_html.py::test_app_js_ya_no_dibuja_lo_que_escribe_el_build`.
  Ese mapa **abre con Colombia entera y una sola capa encendida**, la de la
  ausencia (`app.js::VISTA_NACIONAL`), porque la ausencia se lee antes que la
  evidencia. Sus trece capas entran por una de dos puertas: `conChip(clave,
  capa)`, que las pone bajo uno de los cinco chips —y un chip manda sobre TODA
  su fuente: los polígonos de zona de Copernicus y sus huecos sin analizar son
  suyos—, o `sinChip(motivo, capa)`, que obliga a escribir por qué una capa no
  tiene chip y la deja en el control de capas de Leaflet, que por eso no se
  retira. El estado que el build escribe en los chips
  (`render_html.py::ENCENDIDAS_AL_ABRIR`) y el que `app.js` enciende son la
  misma decisión en dos superficies; sus guardianes son
  `test_frontend.py::TestElMapaAbreConLaAusenciaSola` y
  `TestCadaCapaTieneChipOMotivo`.
  **Y cada capa se pide cuando el lector la enciende, no antes**: al abrir solo
  viajan `monitor.json` y `municipios_mapa.json` —163 KB en dos peticiones,
  frente a los 4.219 KB en trece de antes—. Cada capa es una ranura
  (`app.js::diferida`): un `LayerGroup` vacío que ya existe, para que el control
  y los chips puedan accionarlo, y un fichero que baja al primer alta del grupo
  (`grupo.on("add")`, el punto por el que pasan tanto el chip como el control).
  La caché es la promesa, así que dos clics no descargan dos veces; un fallo de
  red saca la capa del mapa y avisa (R13), y la que llega vacía se retira del
  control. El rótulo del control estrena su cifra al dibujarse y no antes: R3
  también ahí. Lo ejecuta y lo vigila
  `test_frontend.py::TestElMotorDeCargaDiferida` y lo cuenta por dos caminos
  `TestCadaCapaSePideAlEncenderse`; el porqué, en
  `docs/DECISIONES.md` (25-ago).
  **La barra y el pie no los escribe el navegador**:
  los escribe el build en las 213 páginas (`render_html.py::nav_estatico` /
  `pie_estatico`, con el paso `escribir_piezas_compartidas` para las **seis**
  grandes — la sexta, `referencia.html`, entró el 25-ago con la mudanza de la
  metodología y el glosario; la lista única es `PAGINAS_GRANDES`). Ese mismo paso escribe el **nodo de identidad JSON-LD**
  (`BLOQUE_IDENTIDAD`): quién publica el sitio, byte a byte igual en las 213,
  porque `@id` no resuelve entre documentos y solo la constante única lo
  garantiza. En `municipios.html` la **fila entera es pulsable sin JavaScript**:
  el ancla del nombre (`.fila-enlace`) estira un pseudoelemento sobre la fila, y
  de ahí sale una regla al escribirla —**nada de texto pelado colgando de un
  `<td>`**, cada valor en su elemento (`valor_suelto()`)—, porque lo que queda
  debajo de esa capa deja de poder seleccionarse y pierde su `title`.
  **Una cifra vigilada declara de qué concepto es**: quien la imprime la envuelve
  en un `data-cifra="<concepto>"` y el concepto vive en un solo sitio,
  `render_html.py::CIFRAS_DECLARADAS`. Existe porque la portada llegó a publicar
  dos totales del mismo registro —348 municipios en la prosa contra 347 en su
  propia tabla— sin que nada lo impidiera; con la marca puesta,
  `test_render_html.py::TestCifrasDeclaradas` recorre el artefacto construido y
  compara **entre sí** las cifras publicadas, que es lo único que no caduca con
  la corrida del día siguiente. La marca envuelve solo el número, nunca la
  palabra que lo acompaña: qué va en negrita es estilo, y no lo decide este
  mecanismo.
  **Una frase que afirma algo comprobable lo declara igual.** El resumen de cada
  ficha marca con `data-mirada` cuál de los tres casos publica —`con-edificios`,
  `mirado-sin-marcas` o `sin-mirar`— y la nota de la comparativa marca con
  `data-adelanto` qué indicadores adelanta cada columna. Son la misma idea que
  `data-cifra` un paso más allá: sin la marca, el guardián tendría que leer
  prosa —y un test que busca palabras en un texto se queda en verde en cuanto la
  frase se reescribe—. Con ella, `TestResumenDeLaFicha` contrasta las 347 fichas
  contra `_mirado_por_satelite` y `TestComparativaNoSeContradice` contrasta la
  nota contra su propia tabla, sin fijar ninguna cifra.
  **Y la tesis del proyecto vive en `render_html.py::TESIS`**, no en las seis
  superficies que la publican (`CLAUDE.md`, el pie, el `Dataset` de
  `municipios.html` y las bajadas de portada, balances y referencia):
  `TestTesisDelMonitor` es su espejo.

## Cómo se lee `data/snapshots/<día>/`

La carpeta de un día contiene **los cuerpos que ese día llegaron nuevos**, no
todo lo que ese día se pidió. Desde el 24-ago-2026, un cuerpo que la fuente
devuelve idéntico al que ya teníamos no se vuelve a escribir: la copia viva es
la del día en que apareció.

Eso lo dicen dos superficies, y un test vigila que no se separen:

1. **`sources_log` es el índice completo** — toda petición tiene su fila, con
   `snapshot_path` apuntando al cuerpo vigente aunque sea de otro día. Es lo que
   se consulta para responder «¿qué se pidió el 24 de agosto?»:

   ```sql
   SELECT ts, url, http_status, bytes, snapshot_path
     FROM sources_log WHERE ts LIKE '2026-08-24%';
   ```

   Versionado y legible sin sqlite en `data/dumps/sources_log.csv`.

2. **`reutilizados.txt`, dentro de la propia carpeta del día** — una línea por
   cuerpo que no está ahí: nombre que habría tenido, ruta de la copia vigente y
   sha256. Existe porque quien abra `data/snapshots/2026-08-24/` dentro de
   veinte años y no encuentre la capa de Copernicus **no tiene por qué saber que
   existe una base de datos**: la carpeta se explica sola.
   `test_hipotesis.py::test_la_carpeta_del_dia_no_miente_sobre_lo_que_no_contiene`

**Consecuencia para quien lee el archivo desde el código**: «el fichero de hoy»
y «el cuerpo vigente» dejaron de ser lo mismo. Para leer un snapshot se usa
`common.ultimo_snapshot(nombre)`, nunca `snapshot_dir() / nombre` —eso último es
para escribir, y solo lo hace `fetch()`—. Hay un test estructural que lo vigila
en todo `ingest/`: `test_unit.py::test_nadie_consume_un_cuerpo_de_la_carpeta_de_hoy`.

Lo que **no** cambia: nada se sobrescribe ni se migra. Un cuerpo distinto el
mismo día sigue archivándose aparte con su sufijo `_<sha8>`, y un cuerpo nuevo
siempre se escribe.

## Modelo de datos (sqlite, 19 tablas)

Esquema completo en `ingest/common.py::SCHEMA`. Resumen:

| Tabla | Clave | Qué guarda |
|---|---|---|
| `sources_log` | id | Trazabilidad: ts, url, http_status, sha256, bytes, snapshot_path de CADA petición y de cada derivación del propio archivo (estas últimas sin HTTP ni cuerpo: los cuatro campos en NULL). Más `etag`/`last_modified`: los validadores que declaró esa respuesta, de los que sale la petición condicional del día siguiente |
| `activations` | (code, snapshot_date) | Activaciones Copernicus con geometría WKT, por día |
| `activation_index` | code | Catálogo completo EMSR673+ (vigilancia de nuevas activaciones) |
| `products` | (code, aoi, ptype, …, snapshot_date) | Productos Copernicus por AOI: tipo, versión, estado, entrega |
| `stats` | (code, aoi, …, category, snapshot_date) | Estadísticas de daño; `total_raw/affected_raw` conservan el literal («NA» no se pierde) |
| `official_events` | (source, external_id) | EDAN histórico UNGRD (85k registros) + eventos oficiales. **Acumula y nunca retira**: es el archivo, no el estado de hoy — lo que el sitio publica del RUD sale de `rud_daily` |
| `evidence` | id | Evidencia por AOI con tipo ∈ {oficial, institucional, prensa, ciudadano} — el corazón de R1 |
| `media_volume` | (event_key, fecha, snapshot_date) | Series diarias: EMM, GDELT, feeds propios, ChatMap |
| `citizen_reports` | (origen, id_externo) | Reportes ChatMap: coordenada exacta + `lat_pub/lon_pub`, sha256 del medio, score y checks |
| `news_items` | url | Titulares de todos los feeds (registro abierto). `medio` guarda el FEED que trajo la pieza; `medio_canonico`/`medio_dominio`, la cabecera que la firma según el `<source>` del propio RSS |
| `rud_daily` | (snapshot_date, departamento, municipio) | RUD por municipio y día de captura — la serie oficial, y **la única fuente de los totales que se publican** (su último corte) |
| `men_sedes` | (cod_dane, snapshot_date) | Sedes educativas MEN (SISE) con estado físico, matrícula y coordenada. **Una tabla y no dos** (precedente `rud_daily`) y **serie por cambios, no por días**: línea base completa el primer día y después una fila solo cuando la sede cambió — el corte vigente es la última fila por sede; la comprobación diaria sin cambios queda en `sources_log` |
| `unosat_products` | product_id | Productos UNITAR-UNOSAT del evento: título, enlaces a PDF/SHP/GDB y `shp_sha256`, que es la identidad real del paquete |
| `unosat_damage` | (paquete_sha, capa, idx) | Edificios evaluados por UNOSAT. La clave es el **paquete**, no el producto: tres productos publican el mismo ZIP y el edificio es uno solo |
| `sertit_productos` | producto_id | Los cinco mapas de ICube-SERTIT: escala, sensor, área analizada y el sha del paquete de vectores que les corresponde |
| `sertit_danos` | (paquete_sha, capa, idx) | Edificios de SERTIT. Clave por **paquete** como en UNOSAT: la identidad del dato es el ZIP recibido, no el id del producto, porque la fuente reedita sin cambiar el id |
| `crosscheck` | (aoi_name, snapshot_date) | Resultado del cruce por zona y día |
| `fuentes_watch` | (watcher, external_id) | Estado de los vigilantes de fuentes que aún no existen: `hdx` (datasets nuevos en data.humdata.org) y `arcgis_eres` (el tablero ERES/MinSalud). Una fila por item ya visto — decide «nuevo» vs «ya conocido» en `ingest/alerts.py` |

## Los tres ciclos automáticos

1. **23:00 Colombia** (`workers/ai-view`, cron Cloudflare): balances en medios que
   citan fuentes oficiales — Firecrawl + extracción IA → KV → `/oficiales.json`.
2. **05:30 Colombia** (`.github/workflows/daily.yml`): corrida completa de ingesta →
   tests contra datos frescos → sync de vídeos a R2 → **auditoría del bucket
   (`ingest/auditar_r2.py`)** → Wayback del RUD → snapshot del feed de balances →
   commit del bot → (dispara el deploy).
   La auditoría no es adorno ni es un aviso: **sale 1**. Mientras el runner se
   bajaba los 77 vídeos cada día, el `sync` los volvía a ofrecer y un objeto que
   faltara en R2 se curaba solo al día siguiente. Desde que no se descarga lo ya
   archivado, ese remiendo no existe, y si la subida no ocurre —secreto
   caducado, un fork— un vídeo nuevo vive solo en el workspace, que se destruye
   al acabar, mientras el manifiesto ya declara su sha256. Por eso falla el día
   en que un cuerpo solo existe aquí o el manifiesto declara algo que R2 no
   tiene. Corre **antes** del commit, así que el archivo del día se guarda igual,
   y deja su informe en `data/auditoria_r2.json`, versionado: los `::error::` de
   Actions caducan a los 90 días y viven fuera del repositorio.
3. **En cada push a main** (`.github/workflows/pages.yml`): regenera OG, construye
   `dist/` con `deploy/build_dist.sh` y publica en **GitHub Pages** (única vía de
   deploy; el dominio datosdelterremoto.org apunta ahí por CNAME).

## Deploy

`deploy/build_dist.sh` es LA definición del artefacto: copia `site/` + `data/public/`
+ fotos, genera redirect raíz, robots/llms y el sitemap (5 URLs). Lo invocan tanto el
workflow de Pages como cualquier build local. No hay otra vía de publicación.

## Tests (3 capas)

- `tests/test_unit.py` — lógica pura, offline.
- `tests/test_supuestos_api.py` — contratos de las fuentes externas (red real;
  un supuesto roto AVISA — puede ser buena noticia, R11).
- `tests/test_hipotesis.py` — las afirmaciones del proyecto contra la BD real.
