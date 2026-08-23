# Arquitectura del monitor

Mapa técnico del proyecto. La misión y las reglas viven en [CLAUDE.md](../CLAUDE.md);
las decisiones fechadas en [DECISIONES.md](DECISIONES.md); las lagunas conocidas en
[LIMITACIONES.md](LIMITACIONES.md).

## Flujo de datos

```
13 fuentes externas ──► ingest/sources/*.py ──► sqlite (12 tablas) ──► ingest/publish.py
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
- **`ingest/run_daily.py`** orquesta: cada fuente es un `step()` que puede fallar sin
  tumbar la corrida (R13).
- **`ingest/crosscheck.py`** aplica la cadena de estados por AOI:
  `no_comparable → coincide → prensa → ciudadano → pendiente` (R1/R2).
- **`ingest/publish.py`** genera todos los artefactos públicos de `data/public/`
  (solo coordenadas redondeadas `lat_pub/lon_pub` — R5). Entre ellos
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
  puede hacer el navegador: compartir, alertas push y abrir el `<details>` de un
  ancla) y un JS por página. **La barra y el pie no los escribe el navegador**:
  los escribe el build en las 213 páginas (`render_html.py::nav_estatico` /
  `pie_estatico`, con el paso `escribir_piezas_compartidas` para las cinco
  grandes). Ese mismo paso escribe el **nodo de identidad JSON-LD**
  (`BLOQUE_IDENTIDAD`): quién publica el sitio, byte a byte igual en las 213,
  porque `@id` no resuelve entre documentos y solo la constante única lo
  garantiza. En `municipios.html` la **fila entera es pulsable sin JavaScript**:
  el ancla del nombre (`.fila-enlace`) estira un pseudoelemento sobre la fila, y
  de ahí sale una regla al escribirla —**nada de texto pelado colgando de un
  `<td>`**, cada valor en su elemento (`valor_suelto()`)—, porque lo que queda
  debajo de esa capa deja de poder seleccionarse y pierde su `title`.

## Modelo de datos (sqlite, 16 tablas)

Esquema completo en `ingest/common.py::SCHEMA`. Resumen:

| Tabla | Clave | Qué guarda |
|---|---|---|
| `sources_log` | id | Trazabilidad: ts, url, http_status, sha256, bytes, snapshot_path de CADA petición y de cada derivación del propio archivo (estas últimas sin HTTP ni cuerpo: los cuatro campos en NULL) |
| `activations` | (code, snapshot_date) | Activaciones Copernicus con geometría WKT, por día |
| `activation_index` | code | Catálogo completo EMSR673+ (vigilancia de nuevas activaciones) |
| `products` | (code, aoi, ptype, …, snapshot_date) | Productos Copernicus por AOI: tipo, versión, estado, entrega |
| `stats` | (code, aoi, …, category, snapshot_date) | Estadísticas de daño; `total_raw/affected_raw` conservan el literal («NA» no se pierde) |
| `official_events` | (source, external_id) | EDAN histórico UNGRD (85k registros) + eventos oficiales |
| `evidence` | id | Evidencia por AOI con tipo ∈ {oficial, institucional, prensa, ciudadano} — el corazón de R1 |
| `media_volume` | (event_key, fecha, snapshot_date) | Series diarias: EMM, GDELT, feeds propios, ChatMap |
| `citizen_reports` | (origen, id_externo) | Reportes ChatMap: coordenada exacta + `lat_pub/lon_pub`, sha256 del medio, score y checks |
| `news_items` | url | Titulares de todos los feeds (registro abierto). `medio` guarda el FEED que trajo la pieza; `medio_canonico`/`medio_dominio`, la cabecera que la firma según el `<source>` del propio RSS |
| `rud_daily` | (snapshot_date, departamento, municipio) | RUD por municipio y día de captura — la serie oficial |
| `unosat_products` | product_id | Productos UNITAR-UNOSAT del evento: título, enlaces a PDF/SHP/GDB y `shp_sha256`, que es la identidad real del paquete |
| `unosat_damage` | (paquete_sha, capa, idx) | Edificios evaluados por UNOSAT. La clave es el **paquete**, no el producto: tres productos publican el mismo ZIP y el edificio es uno solo |
| `sertit_productos` | producto_id | Los cinco mapas de ICube-SERTIT: escala, sensor, área analizada y el sha del paquete de vectores que les corresponde |
| `sertit_danos` | (paquete_sha, capa, idx) | Edificios de SERTIT. Clave por **paquete** como en UNOSAT: la identidad del dato es el ZIP recibido, no el id del producto, porque la fuente reedita sin cambiar el id |
| `crosscheck` | (aoi_name, snapshot_date) | Resultado del cruce por zona y día |

## Los tres ciclos automáticos

1. **23:00 Colombia** (`workers/ai-view`, cron Cloudflare): balances en medios que
   citan fuentes oficiales — Firecrawl + extracción IA → KV → `/oficiales.json`.
2. **05:30 Colombia** (`.github/workflows/daily.yml`): corrida completa de ingesta →
   tests contra datos frescos → sync de vídeos a R2 → Wayback del RUD → snapshot del
   feed de balances → commit del bot → (dispara el deploy).
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
