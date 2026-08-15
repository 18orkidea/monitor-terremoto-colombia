# Vista IA con Workers AI

Worker experimental para contrastar el monitor con modelos disponibles en
Cloudflare Workers AI:

- `@cf/qwen/qwq-32b`
- `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b`
- `@cf/moonshotai/kimi-k2.6`

La vista no reemplaza fuentes oficiales. Es una ayuda de lectura para formular
hipótesis sobre municipios subrepresentados, límites de inferencia y evidencia
oficial faltante.

## Seguridad

`/api/analyze` exige un secreto `ACCESS_TOKEN`. Si el secreto no existe, el
Worker responde `503` y no ejecuta inferencia.

```bash
cd workers/ai-view
wrangler secret put ACCESS_TOKEN
wrangler deploy
```

El uso de `/api/analyze` consume Workers AI. No desplegar sin token.

## Desarrollo

```bash
wrangler deploy --dry-run
wrangler dev --remote
```
