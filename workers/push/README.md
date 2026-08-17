# Worker de avisos — Web Push + Telegram

Empuja las alertas diarias del monitor (nivel `alta` + `rud_actualizado` +
`balance_en_medios`) a las suscripciones Web Push del navegador y a un canal
público de Telegram. Un solo punto de envío con dedupe por sha256 del
contenido: el POST del workflow diario y el cron de respaldo (11:20 UTC) son
idempotentes entre sí.

La criptografía Web Push (RFC 8291/8188/8292) está en `src/webpush.js`,
vanilla WebCrypto sin dependencias, y se testea en CI contra el **vector de
prueba oficial del RFC 8291 §5** (`tests/test_webpush.py` la ejecuta con node
— el mismo código que corre aquí).

## Puesta en marcha (manual, una vez)

```bash
cd workers/push
npm install                      # wrangler pineado

# 1. Namespace KV para suscripciones y dedupe
npx wrangler kv namespace create PUSH_SUBS
#    → pegar el id en wrangler.jsonc (kv_namespaces[0].id)

# 2. Par de claves VAPID (la pública va a wrangler.jsonc y a site/ui.js;
#    la privada, como secreto)
node --input-type=module -e '
const par = await crypto.subtle.generateKey(
  { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const pub = new Uint8Array(await crypto.subtle.exportKey("raw", par.publicKey));
const b64u = (b) => btoa(String.fromCharCode(...b))
  .replaceAll("+","-").replaceAll("/","_").replaceAll("=","");
console.log("VAPID_PUBLIC_KEY =", b64u(pub));
console.log("VAPID_PRIVATE_JWK =",
  JSON.stringify(await crypto.subtle.exportKey("jwk", par.privateKey)));'
#    → VAPID_PUBLIC_KEY en wrangler.jsonc Y en site/ui.js (UI.VAPID_PUBLIC_KEY)

# 3. Secretos (nunca en git ni en el chat)
npx wrangler secret put INTERNAL_TOKEN     # token largo aleatorio propio
npx wrangler secret put VAPID_PRIVATE_JWK  # el JSON del paso 2
npx wrangler secret put TELEGRAM_BOT_TOKEN # opcional (paso 4)

# 4. Telegram (opcional, 5 min):
#    a) Crear un canal PÚBLICO en Telegram (p. ej. @brechas_terremoto)
#    b) @BotFather → /newbot → copiar el token → paso 3
#    c) Añadir el bot como administrador del canal (permiso: publicar)
#    d) Poner "@tu_canal" en TELEGRAM_CHAT de wrangler.jsonc

# 5. Deploy
npx wrangler deploy

# 6. GitHub → Settings → Secrets → Actions → PUSH_INTERNAL_TOKEN
#    (el mismo valor del paso 3; sin él, el paso del daily se salta limpio)
```

## Rutas

| Ruta | Método | Qué hace |
|---|---|---|
| `/suscribir` | POST | Guarda una PushSubscription (validada) en KV |
| `/desuscribir` | POST | Borra por endpoint |
| `/stats` | GET | `{suscriptores: N}` — transparencia |
| `/internal/enviar` | POST + Bearer | Filtra → dedupe → envía (body opcional = alerts.json fresco) |

## Límites (free tier, documentados en docs/LIMITACIONES.md)

50 subrequests por invocación → lotes de ≤40 suscripciones por disparo. Si el
monitor supera ~40 suscriptores, pasar a Workers Paid ($5/mes, 1.000
subrequests) — es un umbral de éxito, no un problema de hoy.

## Probar en local

```bash
npx wrangler dev   # KV local
curl -X POST http://localhost:8787/internal/enviar \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data-binary @../../data/public/alerts.json
# segunda vez → {"enviado": false, "motivo": "ya enviado hoy (dedupe)"}
```
