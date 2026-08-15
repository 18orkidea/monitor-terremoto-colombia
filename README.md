# Monitor de brechas de reporte de desastres — Colombia

Monitor histórico y diario del terremoto M7.4 del 10-ago-2026 (San José del Palmar, Chocó)
y del ecosistema de datos de desastres en Colombia. No produce datos nuevos: **audita los
que existen** — quién publica, quién calla, cuándo llega cada cifra y qué queda subestimado.

## Las tres brechas que mide

1. **Brecha de reporte oficial** — Copernicus entrega daño verificado por satélite en días;
   las fuentes oficiales abiertas de Colombia (UNGRD en datos.gov.co: parado en 2022;
   registro ArcGIS UNGRD: parado en feb-2024; SNIGRD: sin API pública) no cubren el evento.
2. **Brecha de atención** — la cobertura mediática cae ~92 % en 5 días y toca mínimo el día
   en que se publican los datos de daño (Quibdó e Istmina, 14-ago).
3. **Brecha de cobertura** — población expuesta (PAGER/ShakeMap) fuera de las zonas
   mapeadas por satélite y sin reporte de ningún tipo.

## Uso

```bash
python ingest/run_daily.py --backfill   # primera vez (enumera EMSR673+ e histórico UNGRD)
python ingest/run_daily.py              # corrida diaria (GitHub Actions la hace sola)
python -m http.server -d . 8000         # ver el mapa: http://localhost:8000/site/
```

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
| [UNGRD ArcGIS](https://services2.arcgis.com/YVLx8xYoDXKccDfJ/arcgis/rest/services/REGISTRO_DE_EMERGENCIAS_EN_COLOMBIA/FeatureServer/0) | 85k emergencias EDAN 1914→2024 (línea base) | Público |
| [Socrata `wwkg-r6te`](https://www.datos.gov.co/Ambiente-y-Desarrollo-Sostenible/Emergencias-UNGRD-/wwkg-r6te) | El mismo registro hasta 2022 (métrica de brecha) | Público |
| [ChatMap OSM Colombia](https://chatmap.hotosm.org/colombia.html) ([uMap](https://umap.hotosm.org/en/map/colombia-m-74-earthquake-10-ago-2026_3482), [proyecto HOT](https://www.hotosm.org/en/projects/2026-colombia-earthquake-response/)) | 430+ reportes ciudadanos con foto (WhatsApp→mapa) | Endpoint de activación: puede cerrar; medios copiados localmente |
| [EMSC seismicportal](https://www.seismicportal.eu/) | 1.339 felt reports (contraste con DYFI) | Público |

Sin acceso programático (documentado, no usado): [SNIGRD](https://sni.gestiondelriesgo.gov.co/)/geoportal
UNGRD (Keycloak), [SGC Sismo Sentido](https://sismosentido2.sgc.gov.co/) (SPA sin API),
[UNITAR-UNOSAT](https://unosat.org/products/4250) (sin API), ReliefWeb (requiere appname).

## Reglas de rigor

- **`Coincide cualitativamente` exige evidencia oficial** (EDAN/entidad estatal). Prensa y
  reportes ciudadanos alimentan estados intermedios explícitos; nunca promueven solos.
- Los `"NA"` de Copernicus se conservan como NULL + literal crudo — jamás se convierten en 0.
- Coordenadas ciudadanas publicadas redondeadas a ~110 m; el EXIF nunca se publica.
- Toda cifra es rastreable: `sources_log` (URL, HTTP, sha256, timestamp) + snapshot inmutable
  en `data/snapshots/YYYY-MM-DD/`.

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
  monitor.sqlite  # series + procedencia
  snapshots/      # respuestas crudas por día (inmutables)
  media/          # fotos ciudadanas (videos fuera de git, hash registrado)
  public/         # artefactos que consume el mapa
site/             # Leaflet sin build: index.html + app.js + styles.css
tests/            # ciegos: unit (código), supuestos (APIs), hipótesis (datos)
```
