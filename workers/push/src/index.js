/* Worker de avisos del monitor: Web Push + Telegram.
 *
 * Un solo punto de envío con dedupe: recibe las alertas del día (POST del
 * workflow diario con el alerts.json fresco en el body, o el cron de
 * respaldo que lee la URL pública ya deployada), filtra las notificables
 * (nivel alta + rud_actualizado + balance_en_medios), y si el contenido no
 * se envió ya hoy, lo empuja a cada suscripción Web Push (KV) y al canal de
 * Telegram. Las suscripciones muertas (404/410) se borran solas.
 *
 * Rutas públicas:  POST /suscribir · POST /desuscribir · GET /stats
 * Ruta interna:    POST /internal/enviar (Authorization: Bearer INTERNAL_TOKEN)
 * Cron:            20 11 * * * (respaldo; el dedupe lo hace idempotente)
 *
 * Secretos (wrangler secret put): INTERNAL_TOKEN, VAPID_PRIVATE_JWK,
 * TELEGRAM_BOT_TOKEN (opcional: sin él, solo Web Push).
 * Vars públicas (wrangler.jsonc): VAPID_PUBLIC_KEY, ALERTS_URL, TELEGRAM_CHAT.
 */
import { enviarPush, filtrarNotificables, shaDePayload,
         resumenNotificacion, b64urlABytes } from "./webpush.js";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (obj, status = 200) => new Response(
  JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...CORS } });

async function shaEndpoint(endpoint) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function suscripcionValida(sub) {
  try {
    return sub && typeof sub.endpoint === "string" &&
      new URL(sub.endpoint).protocol === "https:" &&
      sub.keys && b64urlABytes(sub.keys.p256dh).length === 65 &&
      b64urlABytes(sub.keys.auth).length === 16;
  } catch { return false; }
}

/* Envío del día: filtra, dedupe, empuja. Devuelve el resumen (auditable). */
async function enviarAlertas(env, payloadAlertas) {
  let data = payloadAlertas;
  if (!data) {
    const r = await fetch(env.ALERTS_URL, { cf: { cacheTtl: 0 } });
    if (!r.ok) return { error: `alerts.json HTTP ${r.status}` };
    data = await r.json();
  }
  const fecha = data.fecha || new Date().toISOString().slice(0, 10);
  const notificables = filtrarNotificables(data.alertas);
  if (!notificables.length) return { fecha, enviado: false, motivo: "sin alertas notificables" };

  const sha = await shaDePayload(notificables);
  const clave = `envio:${fecha}`;
  if (await env.PUSH_SUBS.get(clave) === sha) {
    return { fecha, enviado: false, motivo: "ya enviado hoy (dedupe)", sha };
  }

  const resumen = resumenNotificacion(fecha, notificables);
  const salida = { fecha, sha, alertas: notificables.length,
                   push: { ok: 0, borradas: 0, error: 0 }, telegram: null };

  // Web Push a cada suscripción (lotes ≤40: 50 subrequests/invocación en free)
  const lista = await env.PUSH_SUBS.list({ prefix: "sub:", limit: 40 });
  for (const k of lista.keys) {
    const sub = await env.PUSH_SUBS.get(k.name, "json");
    if (!sub) continue;
    try {
      const st = await enviarPush(sub, JSON.stringify(resumen), env);
      if (st === 404 || st === 410) {
        await env.PUSH_SUBS.delete(k.name);
        salida.push.borradas++;
      } else if (st >= 200 && st < 300) {
        salida.push.ok++;
      } else {
        salida.push.error++;
      }
    } catch { salida.push.error++; }
  }
  if (!lista.list_complete) salida.push.pendientes = true;

  // Telegram (opcional): canal público como camino móvil sin fricción
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT) {
    const texto = `<b>${resumen.titulo}</b>\n` +
      notificables.map((a) => `${a.nivel === "alta" ? "⚠️ " : "· "}${a.texto}`).join("\n") +
      `\n\n<a href="${resumen.url}">Ver el monitor</a>`;
    const r = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT, text: texto.slice(0, 4000),
                               parse_mode: "HTML", disable_web_page_preview: true }),
      });
    salida.telegram = r.ok ? "ok" : `HTTP ${r.status}`;
  }

  await env.PUSH_SUBS.put(clave, sha, { expirationTtl: 7 * 86400 });
  salida.enviado = true;
  return salida;
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (url.pathname === "/suscribir" && req.method === "POST") {
      const sub = await req.json().catch(() => null);
      if (!suscripcionValida(sub)) return json({ error: "suscripción inválida" }, 400);
      await env.PUSH_SUBS.put(`sub:${await shaEndpoint(sub.endpoint)}`,
        JSON.stringify(sub));
      return json({ ok: true });
    }

    if (url.pathname === "/desuscribir" && req.method === "POST") {
      const { endpoint } = await req.json().catch(() => ({}));
      if (!endpoint) return json({ error: "falta endpoint" }, 400);
      await env.PUSH_SUBS.delete(`sub:${await shaEndpoint(endpoint)}`);
      return json({ ok: true });
    }

    if (url.pathname === "/stats") {
      const lista = await env.PUSH_SUBS.list({ prefix: "sub:", limit: 1000 });
      return json({ suscriptores: lista.keys.length,
                    parcial: !lista.list_complete });
    }

    if (url.pathname === "/internal/enviar" && req.method === "POST") {
      const auth = req.headers.get("Authorization") || "";
      if (!env.INTERNAL_TOKEN || auth !== `Bearer ${env.INTERNAL_TOKEN}`) {
        return json({ error: "no autorizado" }, 401);
      }
      const body = await req.json().catch(() => null);
      return json(await enviarAlertas(env, body));
    }

    return json({
      servicio: "avisos del monitor de brechas (terremoto Colombia 2026)",
      rutas: ["POST /suscribir", "POST /desuscribir", "GET /stats"],
      sitio: "https://datosdelterremoto.org/",
    });
  },

  async scheduled(event, env, ctx) {
    // respaldo diario: si el POST del workflow falló, este cron reintenta
    // leyendo la URL pública (Pages ya deployó); el dedupe evita duplicados
    ctx.waitUntil(enviarAlertas(env, null));
  },
};
