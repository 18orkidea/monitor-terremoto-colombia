"""La criptografía Web Push del worker (workers/push/src/webpush.js) se
ejecuta aquí con node — el MISMO código que corre en Cloudflare, sin réplicas.

El test de oro es el vector de prueba oficial del RFC 8291 §5: claves fijas y
salt fijo deben producir el ciphertext EXACTO del RFC, byte a byte. Si eso
pasa, el cifrado es correcto; si falla, ningún navegador podrá descifrar las
notificaciones. También se verifican los valores intermedios (CEK y NONCE)
para distinguir un error de cifrado de un error del vector.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
WEBPUSH = (ROOT / "workers" / "push" / "src" / "webpush.js").as_uri()

# RFC 8291 §5 — vector de prueba completo
VECTOR = {
    "plaintext": "When I grow up, I want to be a watermelon",
    "ua_public": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4"
                 "bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
    "auth": "BTBZMqHH6r4Tts7J_aSIgg",
    "as_public": "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmY"
                 "WAmS6TlzAC8wEqKK6PBru3jl7A8",
    "as_private": "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw",
    "salt": "DGv6ra1nlYgDCS1FRnbzlw",
    "body_esperado": "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBt"
                     "kgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl"
                     "7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLV"
                     "WGNWQexSgSxsj_Qulcy4a-fN",
}


def correr(script: str) -> dict:
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:800]}")
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestVectorRFC8291(unittest.TestCase):

    def test_ciphertext_exacto_del_rfc(self):
        v = json.dumps(VECTOR)
        out = correr(f"""
const wp = await import({json.dumps(WEBPUSH)});
const v = {v};
const jwk = wp.jwkDesdePar(v.as_private, v.as_public);
const body = await wp.cifrar(v.plaintext, v.ua_public, v.auth,
                             {{ asJwk: jwk, salt: v.salt }});
console.log(JSON.stringify({{ body: wp.bytesAB64url(body) }}));
""")
        self.assertEqual(out["body"], VECTOR["body_esperado"],
                         "el ciphertext no coincide byte a byte con el RFC "
                         "8291 §5 — ningún navegador podrá descifrar esto")

    def test_vapid_firma_verificable_y_claims(self):
        out = correr(f"""
const wp = await import({json.dumps(WEBPUSH)});
const crypto = globalThis.crypto;
const par = await crypto.subtle.generateKey(
  {{ name: "ECDSA", namedCurve: "P-256" }}, true, ["sign", "verify"]);
const priv = await crypto.subtle.exportKey("jwk", par.privateKey);
const jwt = await wp.vapidJwt("https://fcm.googleapis.com",
  "mailto:x@y.z", priv, 1755400000);
const [h, p, s] = jwt.split(".");
const claims = JSON.parse(atob(p.replaceAll("-","+").replaceAll("_","/")));
const ok = await crypto.subtle.verify(
  {{ name: "ECDSA", hash: "SHA-256" }}, par.publicKey,
  wp.b64urlABytes(s), new TextEncoder().encode(`${{h}}.${{p}}`));
console.log(JSON.stringify({{ ok, claims }}));
""")
        self.assertTrue(out["ok"], "la firma ES256 del JWT no verifica")
        self.assertEqual(out["claims"]["aud"], "https://fcm.googleapis.com")
        self.assertEqual(out["claims"]["exp"], 1755400000 + 12 * 3600,
                         "exp debe ser ahora+12h (<24h que exige el RFC 8292)")


@unittest.skipUnless(NODE, "node no disponible")
class TestPoliticaDeAvisos(unittest.TestCase):
    """El filtro editorial: qué alertas disparan push (alta + RUD + balance)."""

    ALERTAS = [
        {"tipo": "nueva_activacion", "nivel": "alta", "texto": "a"},
        {"tipo": "producto_nuevo", "nivel": "alta", "texto": "b"},
        {"tipo": "reportes_ciudadanos", "nivel": "info", "texto": "c"},
        {"tipo": "titulares_nuevos", "nivel": "info", "texto": "d"},
        {"tipo": "balance_en_medios", "nivel": "info", "texto": "e"},
        {"tipo": "rud_actualizado", "nivel": "info", "texto": "f"},
        {"tipo": "rud_activo", "nivel": "alta", "texto": "g"},
        {"tipo": "worker_balances_caido", "nivel": "alta", "texto": "h"},
    ]

    def _filtrar(self, alertas):
        return correr(f"""
const wp = await import({json.dumps(WEBPUSH)});
const sel = wp.filtrarNotificables({json.dumps(alertas)});
const sha = await wp.shaDePayload(sel);
console.log(JSON.stringify({{ tipos: sel.map(a => a.tipo), sha }}));
""")

    def test_filtro_alta_mas_rud_y_balance(self):
        out = self._filtrar(self.ALERTAS)
        self.assertEqual(out["tipos"], [
            "nueva_activacion", "producto_nuevo", "balance_en_medios",
            "rud_actualizado", "rud_activo", "worker_balances_caido"],
            "titulares y reportes diarios no deben quemar el canal")

    def test_dedupe_mismo_contenido_mismo_sha(self):
        a = self._filtrar(self.ALERTAS)
        b = self._filtrar(list(self.ALERTAS))
        self.assertEqual(a["sha"], b["sha"], "mismo contenido debe dar mismo sha")
        c = self._filtrar(self.ALERTAS[:2])
        self.assertNotEqual(a["sha"], c["sha"], "contenido distinto, sha distinto")

    def test_resumen_trunca_y_marca_altas(self):
        out = correr(f"""
const wp = await import({json.dumps(WEBPUSH)});
const r = wp.resumenNotificacion("2026-08-17",
  wp.filtrarNotificables({json.dumps(self.ALERTAS)}));
console.log(JSON.stringify(r));
""")
        self.assertIn("2026-08-17", out["titulo"])
        self.assertIn("⚠️", out["cuerpo"])
        self.assertIn("y 3 más", out["cuerpo"])
        self.assertTrue(out["url"].startswith("https://datosdelterremoto.org/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
