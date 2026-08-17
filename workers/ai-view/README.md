# Feed oficial con lectura IA privada

Worker para recolectar canales colombianos, convertir documentos visuales/PDF a
texto estructurado con Qwen OCR y publicar solo el resultado validado como datos.
Las fuentes descubiertas por búsqueda web se etiquetan como temporales hasta que
exista confirmación oficial.

Modelo OCR:

- `qwen-vl-ocr-2025-11-20`

La inferencia no queda expuesta. El público solo lee:

- `/oficiales.json`
- `/api/oficiales.json`
- `/oficiales.rss`

Las rutas internas requieren `INTERNAL_TOKEN`:

- `POST /internal/run`
- `POST /internal/extract`

## Secretos

```bash
cd workers/ai-view
wrangler secret put INTERNAL_TOKEN
wrangler secret put QWEN_API_KEY
wrangler secret put FIRECRAWL_API_KEY
npm install          # instala wrangler pineado (package.json) — reproducible
npx wrangler deploy
```

El Worker usa KV (`OFFICIAL_DATA`) para persistir el feed público.

`FIRECRAWL_API_KEY` es opcional. Si no está configurado, el Worker sigue
revisando RSS/HTML oficiales y marca el conector Firecrawl como `missing_secret`.

## Firecrawl: búsqueda diaria y scraping

El flujo diario es `search -> scrape -> extracción`:

1. Construye consultas con fecha variable, fuentes oficiales objetivo y campos objetivo:
   - `UNGRD SGC terremoto Colombia DD-MM-YYYY fallecidos heridos desaparecidos rescatados balance oficial`
   - `Gobernación Alcaldía terremoto Colombia DD-MM-YYYY personas familias viviendas municipios departamentos afectados`
   - `Presidencia Colombia UNGRD SGC terremoto DD-MM-YYYY reporte oficial afectados`
2. Llama `POST https://api.firecrawl.dev/v2/search` con `sources:["web"]`, `limit:10`,
   `scrapeOptions.formats:[]`, `maxAge:172800000` y parser `pdf`.
3. Ordena las URLs por presencia de métricas, cifras, contexto Colombia/UNGRD y tipo de fuente.
4. Toma las 3 primeras URLs únicas del día.
5. Entra a cada URL con `POST https://api.firecrawl.dev/v2/scrape` usando markdown,
   contenido principal y parser PDF.
6. Clasifica cada URL como `oficial_comunicacion`, `oficial_institucional`,
   `gobierno_local_por_verificar`,
   `temporal_prensa` o `busqueda_web_temporal`.
7. Publica las cifras extraídas, siempre con `requiere_revision_humana:true`; prensa y
   web abierta no se promueven a EDAN ni a coincidencia oficial.
8. Marca `is_liveblog:true` y `historical_reliability:"baja"` cuando la URL o el título
   indican directo/en vivo/liveblog, porque puede mezclar varias actualizaciones.

Cada ejecución conserva `search_date`, `search_query` y `snapshot_id`. Para Firecrawl el
`snapshot_id` combina fecha y URL, de modo que el mismo medio puede aparecer en varios días
y servir para reconstruir cómo evolucionaron las cifras.

Cada item conserva dos niveles de atribución:

- `publication_url`: URL exacta de la página scrapeada.
- `publisher`: canal que publicó el contenido scrapeado (`name`, `domain`, `channel`, `url`).
- `reported_data_source`: entidad citada como fuente de los datos dentro del texto, por
  ejemplo UNGRD, SGC, Presidencia, Gobernación o Alcaldía cuando aparece; incluye `url`
  cuando se puede asignar una URL canónica.

El cron de producción corre a las `23:00` de Colombia (`0 4 * * *` en UTC de
Cloudflare) para recoger el cierre informativo del día.

Ejecución manual con fecha:

```bash
curl -X POST "$WORKER/internal/run" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"15-08-2026"}'
```

Carga histórica desde el inicio del evento:

```bash
for d in 10-08-2026 11-08-2026 12-08-2026 13-08-2026 14-08-2026 15-08-2026; do
  curl -X POST "$WORKER/internal/run" \
    -H "Authorization: Bearer $INTERNAL_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"date\":\"$d\"}"
done
```

## Canales analizados

- **UNGRD Noticias**: SharePoint público. La portada y la vista de biblioteca se leen bien,
  pero los datos útiles deben estar en noticias específicas `/Paginas/Noticias/2026/*.aspx`.
- **Firecrawl búsqueda diaria**: consulta web por fecha enfocada en UNGRD, SGC,
  Presidencia, Gobernación y Alcaldía, y scrapea las 3 primeras URLs priorizadas.
  Si aparecen medios no oficiales, quedan etiquetados como temporales.
- **SNIGRD Alertas**: HTML público. Se revisa como canal de alertas, pero no se aceptan
  páginas generales como evidencia del terremoto.
- **Gobernación de Caldas**: Joomla con RSS usable en
  `/noticias-gobernacion?format=feed&type=rss`; es el canal mejor estructurado.
- **Gobernación del Valle**: las rutas revisadas pueden devolver `502`; queda reportado en
  `source_analysis` como fuente inestable.
- **Gobierno del Quindío** y **Gobernación de Risaralda**: pueden bloquear tráfico
  automatizado (`403`); no se inventan datos cuando eso ocurre.
- **Gobernación del Chocó**: SPA Angular. El HTML no trae noticias; el Worker lo marca como
  pendiente de API interna si no encuentra enlaces específicos.

El filtro exige evidencia específica del evento: término sísmico más fecha, lugar afectado o
daño. Por eso páginas genéricas como "Emergencias Anuales" o "Consolidado Anual de
Emergencias" no entran al feed aunque mencionen RUD/EDAN.

## Atribución de lugares (R10, desde el 17-ago-2026)

Los topónimos se buscan con **límite de palabra** (`mentionsPlace`), no por contención:
"California" no cuenta como Cali y "fábrica de chocolate" no cuenta como Chocó. Antes de
atribuir se quitan además URLs, enlaces markdown y nombres de archivo (`sinEnlaces`),
porque el worker analiza el documento completo y `terremoto-cali.jpg` atribuía el balance
a Cali sin que el topónimo apareciera en la prosa.

Cada ítem sella el criterio con `atribucion_lugares: "limite_palabra_sin_enlaces"`. **Un
ítem sin ese campo se etiquetó con el criterio anterior** (contención simple): el KV reusa
los ítems ya recolectados sin volver a analizarlos, así que los feeds archivados en
`feeds/balances/` mezclan ambos y el sello es lo único que los distingue.

La lista de municipios está duplicada aquí a propósito (el worker no puede importar
`ingest/municipios.py`), y `tests/test_worker_toponimos.py` vigila que no se separe de la
del pipeline: mismo municipio, mismo departamento, sin homónimos de departamento y sin
ninguno que el pipeline marque como `requiere_depto`.

## Desarrollo

Antes de cada `wrangler deploy`, el dry-run: el worker se despliega a mano y un error de
bundle no se vería hasta la corrida de las 04:00 UTC.

```bash
wrangler deploy --dry-run
wrangler dev --remote
curl -X POST "$WORKER/internal/run" -H "Authorization: Bearer $INTERNAL_TOKEN"
```

Smoke test de Firecrawl:

```bash
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"UNGRD SGC terremoto Colombia 15-08-2026 fallecidos heridos desaparecidos rescatados balance oficial","limit":10,"sources":["web"],"scrapeOptions":{"formats":[],"onlyMainContent":true,"maxAge":172800000,"parsers":["pdf"]}}'
```
