/* Cifrado Web Push sin dependencias (WebCrypto puro).
 *
 * Implementa lo justo de los tres RFC:
 *  - RFC 8291: derivación de claves (ECDH P-256 + HKDF) para Web Push
 *  - RFC 8188: formato de contenido aes128gcm (cabecera + un registro)
 *  - RFC 8292: VAPID (JWT ES256 en la cabecera Authorization)
 *
 * Todas las funciones son puras y exportadas: tests/test_webpush.py las
 * ejecuta con node contra el vector de prueba oficial del RFC 8291 §5 —
 * la MISMA rutina que corre en el worker, sin réplicas.
 */

const subtle = globalThis.crypto.subtle;
const te = new TextEncoder();

/* ---- base64url ---- */
export function b64urlABytes(s) {
  const b64 = s.replaceAll("-", "+").replaceAll("_", "/")
    .padEnd(Math.ceil(s.length / 4) * 4, "=");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export function bytesAB64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function concat(...arrs) {
  const total = arrs.reduce((n, a) => n + a.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const a of arrs) { out.set(a, off); off += a.length; }
  return out;
}

/* JWK de clave privada P-256 a partir de d y de la pública sin comprimir
   (65 bytes: 0x04 || x || y). Lo usa el vector de prueba del RFC. */
export function jwkDesdePar(d_b64url, pub_b64url) {
  const pub = b64urlABytes(pub_b64url);
  return {
    kty: "EC", crv: "P-256", d: d_b64url,
    x: bytesAB64url(pub.slice(1, 33)), y: bytesAB64url(pub.slice(33, 65)),
  };
}

async function hkdf(saltBytes, ikmBytes, infoBytes, longitud) {
  const key = await subtle.importKey("raw", ikmBytes, "HKDF", false, ["deriveBits"]);
  const bits = await subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt: saltBytes, info: infoBytes },
    key, longitud * 8);
  return new Uint8Array(bits);
}

/* Cifra un payload para una suscripción (RFC 8291 + RFC 8188, aes128gcm).
 * ua_public_b64 = subscription.keys.p256dh · auth_b64 = subscription.keys.auth
 * opciones.asJwk / opciones.salt: SOLO para el vector de prueba (determinismo);
 * en producción se generan efímeros y aleatorios. Devuelve el body completo. */
export async function cifrar(plaintext, ua_public_b64, auth_b64, opciones = {}) {
  const uaPublic = b64urlABytes(ua_public_b64);
  const authSecret = b64urlABytes(auth_b64);

  let asPrivKey, asPublic;
  if (opciones.asJwk) {
    asPrivKey = await subtle.importKey("jwk", opciones.asJwk,
      { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
    const { d, ...pubJwk } = opciones.asJwk;
    const pk = await subtle.importKey("jwk", { ...pubJwk, key_ops: [] },
      { name: "ECDH", namedCurve: "P-256" }, true, []);
    asPublic = new Uint8Array(await subtle.exportKey("raw", pk));
  } else {
    const par = await subtle.generateKey(
      { name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    asPrivKey = par.privateKey;
    asPublic = new Uint8Array(await subtle.exportKey("raw", par.publicKey));
  }

  const uaKey = await subtle.importKey("raw", uaPublic,
    { name: "ECDH", namedCurve: "P-256" }, false, []);
  const ecdh = new Uint8Array(await subtle.deriveBits(
    { name: "ECDH", public: uaKey }, asPrivKey, 256));

  // RFC 8291: IKM = HKDF(auth, ecdh, "WebPush: info"||0x00||ua_public||as_public)
  const keyInfo = concat(te.encode("WebPush: info"), new Uint8Array([0]),
                         uaPublic, asPublic);
  const ikm = await hkdf(authSecret, ecdh, keyInfo, 32);

  const salt = opciones.salt ? b64urlABytes(opciones.salt)
    : crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm,
    concat(te.encode("Content-Encoding: aes128gcm"), new Uint8Array([0])), 16);
  const nonce = await hkdf(salt, ikm,
    concat(te.encode("Content-Encoding: nonce"), new Uint8Array([0])), 12);

  // RFC 8188: un solo registro = AES-128-GCM(plaintext || 0x02)
  const gcmKey = await subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const conDelimitador = concat(
    typeof plaintext === "string" ? te.encode(plaintext) : plaintext,
    new Uint8Array([2]));
  const cifrado = new Uint8Array(await subtle.encrypt(
    { name: "AES-GCM", iv: nonce }, gcmKey, conDelimitador));

  // cabecera: salt(16) || rs(4) || idlen(1)=65 || keyid(as_public)
  const rs = new Uint8Array(4);
  new DataView(rs.buffer).setUint32(0, 4096);
  return concat(salt, rs, new Uint8Array([asPublic.length]), asPublic, cifrado);
}

/* VAPID (RFC 8292): JWT ES256 con aud = origen del push service. */
export async function vapidJwt(aud, sub, privJwk, ahoraSegundos) {
  const ahora = ahoraSegundos ?? Math.floor(Date.now() / 1000);
  const enc = (obj) => bytesAB64url(te.encode(JSON.stringify(obj)));
  const sinFirma = `${enc({ typ: "JWT", alg: "ES256" })}.` +
    enc({ aud, exp: ahora + 12 * 3600, sub });
  const clave = await subtle.importKey("jwk", privJwk,
    { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const firma = await subtle.sign({ name: "ECDSA", hash: "SHA-256" },
    clave, te.encode(sinFirma));
  return `${sinFirma}.${bytesAB64url(firma)}`;
}

/* Cabeceras del POST al push service. */
export function cabecerasPush(jwt, vapidPublic_b64, ttlSegundos = 86400) {
  return {
    "TTL": String(ttlSegundos),
    "Content-Encoding": "aes128gcm",
    "Content-Type": "application/octet-stream",
    "Urgency": "normal",
    "Authorization": `vapid t=${jwt}, k=${vapidPublic_b64}`,
  };
}

/* Envía una notificación a una suscripción. Devuelve el status HTTP
   (201 = aceptada; 404/410 = suscripción muerta, borrarla). */
export async function enviarPush(subscription, payload, env) {
  const { endpoint, keys } = subscription;
  const body = await cifrar(payload, keys.p256dh, keys.auth);
  const aud = new URL(endpoint).origin;
  const priv = JSON.parse(env.VAPID_PRIVATE_JWK);
  const jwt = await vapidJwt(aud, env.VAPID_SUB || "mailto:gestion@inforesidencias.com", priv);
  const r = await fetch(endpoint, {
    method: "POST",
    headers: cabecerasPush(jwt, env.VAPID_PUBLIC_KEY),
    body,
  });
  return r.status;
}

/* ---- selección y dedupe de alertas (política editorial del push) ---- */

/* Qué alertas disparan aviso: todas las de nivel alta + el pulso diario del
   RUD y del balance en medios. Titulares/reportes (info) no queman el canal. */
export function filtrarNotificables(alertas) {
  return (alertas || []).filter((a) =>
    a.nivel === "alta" ||
    ["rud_actualizado", "balance_en_medios"].includes(a.tipo));
}

export async function shaDePayload(alertas) {
  const bytes = te.encode(JSON.stringify(alertas.map((a) => [a.tipo, a.texto])));
  return bytesAB64url(await subtle.digest("SHA-256", bytes));
}

/* Texto de la notificación: título fijo + primeras alertas resumidas. */
export function resumenNotificacion(fecha, alertas) {
  const lineas = alertas.map((a) =>
    `${a.nivel === "alta" ? "⚠️ " : ""}${a.texto}`);
  const cuerpo = lineas.slice(0, 3).join("\n");
  const extra = lineas.length > 3 ? `\n… y ${lineas.length - 3} más` : "";
  return {
    titulo: `Monitor de brechas · ${fecha}`,
    cuerpo: (cuerpo + extra).slice(0, 500),
    url: "https://brechas.orkidea.eu/site/#alerts-section",
  };
}
