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
wrangler deploy
```

El Worker usa KV (`OFFICIAL_DATA`) para persistir el feed público.

## Desarrollo

```bash
wrangler deploy --dry-run
wrangler dev --remote
curl -X POST "$WORKER/internal/run" -H "Authorization: Bearer $INTERNAL_TOKEN"
```
