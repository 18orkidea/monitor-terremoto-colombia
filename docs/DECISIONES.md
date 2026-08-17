# Decisiones (ADR ligero)

Historia técnica para el mantenedor: una entrada por decisión, con contexto y
consecuencia. La historia pública del monitor (hitos visibles) vive en
`feeds/hitos_monitor.json` — no duplicar.

Formato: `## AAAA-MM-DD — título` · contexto → decisión → consecuencia.

## 2026-08-16 — GitHub Pages como única vía de deploy

Contexto: existían dos pipelines divergentes (build inline en pages.yml con sitemap de
3 URLs; build_dist.sh con 5, publicando a un CF Pages que el dominio no muestra — el
CNAME de brechas.orkidea.eu apunta a 18orkidea.github.io).
Decisión: unificar en GitHub Pages; pages.yml invoca build_dist.sh; se elimina el
deploy a Cloudflare del daily. El proyecto CF Pages huérfano puede borrarse a mano en
el dashboard.
Consecuencia: un solo build, un solo sitemap; el secret CLOUDFLARE_API_TOKEN deja de
usarse para Pages.

## 2026-08-16 — sqlite fuera de git, dumps CSV versionados

Contexto: los 13 blobs del sqlite (15 MB/día, binario sin diff) eran lo más pesado del
repo (.git = 137 MB en 2 días de proyecto).
Decisión: `ingest/dump_db.py` vuelca las 12 tablas a `data/dumps/*.csv` (diffs diarios
legibles — la crónica fila a fila que un historiador puede leer con git diff) y
reconstruye el sqlite cuando falta. El daily commitea dumps, no el binario. La historia
de git NO se reescribe: lo acumulado queda como archivo.
Consecuencia: el repo deja de engordar 15 MB/día; el CI reconstruye la BD desde dumps;
los tests siguen leyendo el sqlite local.

## 2026-08-16 — Analytics se mantiene, pero declarado

Contexto: el beacon de Cloudflare Web Analytics (sin cookies) convivía sin declararse
con la regla de privacidad ciudadana — la incoherencia era lo tóxico, no el beacon.
Decisión: se mantiene y se declara en la metodología pública.
Consecuencia: coherencia editorial; el usuario puede retirarlo cuando quiera.

## 2026-08-16 — Capa social, BuyMeACoffee y aparato SEO se mantienen

Contexto: propuesta de recorte evaluada por el usuario.
Decisión: se mantienen tal cual (compartir sirve a la difusión de los datos; la
financiación mantiene servidores y scraping). El contexto secundario (sismos
históricos, índice de activaciones) se degrada a secciones colapsadas.

## 2026-08-16 — Snapshots intradía con sufijo de hash

Contexto: `fetch()` guardaba solo el primer cuerpo del día («primero del día gana»);
una segunda corrida con contenido distinto dejaba un sha256 en el log sin cuerpo
recuperable. Los binarios hacían lo contrario (sobrescribir).
Decisión: nombre de snapshot con sufijo `_<sha8>`; contenido distinto = archivo nuevo,
nunca un hash sin evidencia. Los snapshots antiguos no se migran (inmutables).
Consecuencia: la promesa «minuto a minuto» pasa de aspiracional a verificable.

## 2026-08-17 — Selección diaria de balances: estabilidad, disputa y consolidado

Contexto: el 16-ago el único snapshot no-liveblog del día fue Primicias (Ecuador) con
un corte viejo (181 fallecidos cuando el consolidado iba por 294); la regla
«no-liveblog primero» lo eligió y la serie pública retrocedió. Además, las cifras que
el ganador del día no traía desaparecían en «—».
Decisión: (1) estabilidad respecto a la víspera como PRIMER criterio — un balance
acumulado no retrocede; caídas >10 % en fallecidos/familias penalizan al candidato por
delante incluso de la marca liveblog; (2) **prensa nacional colombiana** como segundo
criterio (lista curada MEDIOS_NACIONALES en ui.js + dominios .com.co/.gov.co): los
diarios nacionales están más cerca del consolidado oficial que los medios
internacionales tardíos; (3) contradicciones >15 % entre medios del mismo día se
marcan «cifras en disputa» y se muestran — la discrepancia es información de brecha;
(4) consolidado por día: cada cifra conserva su último valor conocido con fecha de
origen marcada. Implementado en ui.js (mejorPorDia), testeado ejecutando el
JS real con node (tests/test_frontend.py) — sin réplicas en Python.
Consecuencia: los medios internacionales tardíos ya no pueden hacer retroceder la
serie ni borrar cifras; la FAQ de Balances ahora describe la regla realmente
implementada (antes prometía una estabilidad que no existía).

## 2026-08-17 — Avisos: Web Push + canal Telegram + alerts.rss, todo en free tier

Contexto: las alertas del día (RUD, balances, cambios del monitor) solo se veían
entrando al sitio.
Decisión: tres canales con un solo punto de envío y dedupe (worker nuevo
`workers/push/`, cuenta inforesidencias): (1) Web Push estándar con criptografía
vanilla WebCrypto (RFC 8291/8188/8292, ~200 líneas SIN npm) **testeada en CI contra el
vector de prueba oficial del RFC 8291 §5 ejecutando el mismo JS con node**; (2) canal
público de Telegram como camino móvil sin fricción (iOS exige PWA para Web Push);
(3) alerts.rss estático desde alerts.py (stdlib). Disparo: POST del daily con el
alerts.json fresco en el body + cron de respaldo 11:20 UTC (dedupe por sha256).
Filtrado editorial: nivel alta + rud_actualizado + balance_en_medios — titulares y
reportes diarios no queman el canal. ntfy.sh descartado: tercero sin contrato.
Consecuencia: $0/mes; límite free tier ~40 push por disparo (50 subrequests) — pasar a
Workers Paid ($5/mes) es un umbral de éxito. Segundo worker que mantener, deploy manual
documentado en su README; sin secretos configurados, todo se salta limpio.

## 2026-08-16 — Deudas anotadas (descartado hacer ahora)

- Refactor de `publish.py::run()` (236 líneas): funciona y está testado por sus
  artefactos; se partirá cuando haya que tocarlo de verdad.
- Migrar el worker de balances de la cuenta inforesidencias a una cuenta del proyecto:
  implica mover KV y secrets; mientras tanto, el snapshot diario en `feeds/balances/`
  elimina el riesgo de pérdida. Documentado en LIMITACIONES.
- SECURITY.md, plantillas de PR/issue, CHANGELOG, pre-commit hooks, dependabot,
  coverage gates: descartados — proyecto de una persona; el coste de mantenimiento no
  se paga.
