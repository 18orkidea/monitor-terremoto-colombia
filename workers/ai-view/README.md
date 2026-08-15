# Feed oficial con lectura IA privada

Worker para recolectar canales oficiales colombianos, convertir documentos
visuales/PDF a texto estructurado con Qwen OCR y publicar solo el resultado
validado como datos.

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
wrangler deploy
```

El Worker usa KV (`OFFICIAL_DATA`) para persistir el feed público.

`FIRECRAWL_API_KEY` es opcional. Si no está configurado, el Worker sigue
revisando RSS/HTML oficiales y marca el conector Firecrawl como `missing_secret`.

## Canales analizados

- **UNGRD Noticias**: SharePoint público. La portada y la vista de biblioteca se leen bien,
  pero los datos útiles deben estar en noticias específicas `/Paginas/Noticias/2026/*.aspx`.
- **Firecrawl multicanal UNGRD**: búsqueda semántica sobre portal UNGRD, YouTube,
  Facebook, Instagram y LinkedIn oficiales. Devuelve markdown ya limpio cuando el resultado
  es accesible, y permite capturar piezas dispersas que no aparecen en la web institucional.
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

## Desarrollo

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
  -d '{"query":"site:portal.gestiondelriesgo.gov.co UNGRD terremoto sismo Chocó agosto 2026","limit":3,"sources":["web"],"scrapeOptions":{"formats":["markdown"],"onlyMainContent":true}}'
```
