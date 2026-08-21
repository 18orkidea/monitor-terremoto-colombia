"""Alertas del día — solo Colombia, todas las fuentes del evento.

Cada corrida regenera alerts.json desde cero con lo que cambió HOY:
- Activaciones Copernicus nuevas DE COLOMBIA (las de otros países se ignoran)
- Cambios de versión/estado en productos EMSR916
- Reportes ciudadanos nuevos (ChatMap, últimas 24 h)
- Titulares nuevos de los feeds comunitarios (hoy)
- Balance nuevo en medios que citan fuentes oficiales (worker IA), con delta
- UNGRD: si el máximo oficial avanza (¡la brecha se cierra!) — nivel alta
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import db, fetch_json, today, PUBLIC, SNAPSHOTS

UI_JS = Path(__file__).parent.parent / "site" / "ui.js"

FEED_BALANCES = ("https://monitor-terremoto-colombia-oficiales-ai"
                 ".inforesidencias.workers.dev/oficiales.json")
UNGRD_ESTANCADO = "2024-02-17"   # si supera esto, la fuente oficial despertó


def _sha_de_la_regla() -> str | None:
    """sha256 de site/ui.js: la regla que produjo el consolidado cambia con el
    tiempo (el techo de salto, las anclas, qué cuenta como atribución), así que
    sin esto un derivado archivado no es reconstruible aunque se conserve el
    cuerpo de entrada."""
    try:
        import hashlib
        return hashlib.sha256(UI_JS.read_bytes()).hexdigest()
    except OSError:
        return None


def _consolidado_de_la_serie(feed: dict) -> tuple[list, str]:
    """El consolidado del balance, calculado por la ÚNICA implementación de la
    regla: site/ui.js, ejecutado con node.

    Hasta el 21-ago-2026 aquí vivía una segunda regla —el máximo de fallecidos
    de cada día suelto— y las dos superficies se contradecían en público: con
    el feed del 19-ago, el push habría anunciado «180 fallecidos (-124 vs día
    anterior)», o sea 124 resucitados, mientras la web mostraba 304. El día no
    traía balance nuevo: traía tres cortes viejos.

    R13: si node no está, no se rompe la corrida — pero tampoco se publica una
    cifra calculada con otra regla. Se devuelve la lista vacía y una etiqueta
    que dice justamente eso, para que nadie lea en un JSON archivado que la
    cifra salió de un cálculo que no se hizo.
    """
    node = shutil.which("node")
    if node and UI_JS.exists():
        # El feed viaja por STDIN, no como argumento: Linux limita cada
        # argumento de execve a 128 KiB (MAX_ARG_STRLEN) y el feed ya pesa
        # ~100 KB, así que pasarlo en la línea de órdenes funcionaba en macOS
        # y habría reventado en el runner de la corrida diaria — en silencio,
        # todos los días, justo en el camino que degrada.
        script = (
            "global.window = {};"
            f"require({json.dumps(str(UI_JS))});"
            "const feed = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "const items = (feed.items || []).filter((x) => x.search_date);"
            "console.log(JSON.stringify(window.UI.mejorPorDia(items)));")
        try:
            r = subprocess.run([node, "-e", script],
                               input=json.dumps(feed, ensure_ascii=False),
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return json.loads(r.stdout), "serie_consolidada_ui_js"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return [], "sin_regla__no_se_publica"


_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_es(iso: str) -> str:
    """«2026-08-18» → «18 de agosto de 2026». El aviso lo leen personas."""
    try:
        a, m, d = iso.split("-")
        return f"{int(d)} de {_MESES_ES[int(m) - 1]} de {a}"
    except (ValueError, IndexError):
        return iso


def balance_de_medios(feed: dict, snap: str) -> tuple[list[dict], dict | None]:
    """Los avisos del balance y el consolidado que se archiva, en una sola
    función para que el artefacto se pueda REGENERAR con este mismo código.

    Vive aparte de `run()` por un motivo concreto: `data/public/alerts.json`
    está versionado y se despliega con el merge, así que un cambio de regla que
    no regenere el artefacto publica la cifra vieja hasta la corrida siguiente.
    Pasó el 21-ago-2026, y el aviso archivado anunciaba «180 fallecidos (-124
    vs día anterior)» — 124 resucitados— con la web ya diciendo 304.
    """
    serie, regla = _consolidado_de_la_serie(feed)
    if not serie:
        return ([{
            "tipo": "regla_de_balance_degradada", "nivel": "alta",
            "texto": "No se ha podido calcular la serie de balances con "
                     "site/ui.js (¿falta node?): el aviso del día se omite "
                     "en vez de publicar una cifra con otra regla."}], None)

    ultimo = serie[-1]
    valor = lambda d, k: (d["consolidado"].get(k) or {}).get("valor")
    # se publica SIEMPRE, no solo cuando hay aviso: la imagen social y
    # cualquier otro consumidor necesitan la cifra vigente también los días
    # en que no llega ningún balance nuevo
    consolidado = {
        "fecha": ultimo["fecha"], "regla": regla,
        "cifras": {k: (v or {}).get("valor")
                   for k, v in ultimo["consolidado"].items()},
        # cada cifra con su fecha, su medio y SU ENLACE: es un dato derivado, y
        # sin la url nadie puede volver dentro de años al artículo del que salió
        "origen": {k: {"fecha": (v or {}).get("fecha"),
                       "medio": (v or {}).get("medio"),
                       "url": (v or {}).get("url")}
                   for k, v in ultimo["consolidado"].items()},
        # lo descartado y por qué: la brecha (R12) también se archiva, no solo
        # se pinta en el navegador
        "ignoradas": ultimo.get("ignoradas") or [],
        # R4: un derivado tiene que decir de qué cuerpo sale y con qué versión
        # de la regla, o no se puede reconstruir
        "derivado_de": {
            "url": FEED_BALANCES,
            "snapshot": f"data/snapshots/{snap}/oficiales_feed.json",
            "items": len([i for i in feed.get("items") or []
                          if i.get("search_date")]),
            "regla_sha256": _sha_de_la_regla()}}

    if ultimo["fecha"] not in (snap, _ayer()):
        return ([], consolidado)

    c = {k: valor(ultimo, k)
         for k in ("fallecidos", "heridos", "desaparecidos",
                   "familias_afectadas", "personas_afectadas")}
    prev = serie[-2] if len(serie) > 1 else None
    antes = valor(prev, "fallecidos") if prev else None
    # el consolidado no retrocede, así que un delta 0 significa que ese día no
    # llegó ningún balance nuevo: no hay nada que avisar
    if prev is not None and c["fallecidos"] == antes:
        return ([], consolidado)

    delta = ""
    if antes is not None and c["fallecidos"] is not None:
        d_f = c["fallecidos"] - antes
        delta = f" (+{d_f} desde el balance anterior)" if d_f else ""
    mil = lambda n: f"{n:,}".replace(",", ".") if isinstance(n, int) else "?"
    return ([{
        "tipo": "balance_en_medios", "nivel": "info",
        "texto": f"Máximo informado en medios que citan fuentes oficiales "
                 f"({_fecha_es(ultimo['fecha'])}): "
                 f"{mil(c['fallecidos'])} fallecidos{delta}, "
                 f"{mil(c['heridos'])} heridos, "
                 f"{mil(c['desaparecidos'])} desaparecidos",
        "fecha_balance": ultimo["fecha"], "cifras": c,
        "regla": regla}], consolidado)


def _ayer() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


# Emisores conocidos de la cronología institucional de GDACS. El título llega
# en inglés y con el nombre del emisor dentro («… - UNITAR-UNOSAT Activation»).
EMISORES = (
    ("UNOSAT", "UNITAR-UNOSAT"),
    ("Copernicus", "Copernicus EMS"),
    ("ECHO", "EC/ECHO"),
)


def _emisor(titulo: str) -> str:
    for clave, nombre in EMISORES:
        if clave.lower() in (titulo or "").lower():
            return nombre
    return "Una fuente institucional"


def _institucional(dia: str) -> list[dict] | None:
    """Cronología institucional archivada de un día, o None si no se capturó."""
    f = SNAPSHOTS / dia / "gdacs_news_institucional.json"
    if not f.exists():
        return None
    try:
        datos = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, list) else None


def _institucionales_nuevos(snap: str) -> list[dict]:
    """Entradas que hoy están y en la última captura anterior no.

    Sin captura previa NO se alerta: en la primera corrida todo sería «nuevo»
    y siete avisos de golpe no informan de nada. La identidad es (enlace,
    fecha) porque Copernicus reutiliza la misma URL de descarga en entradas
    distintas.
    """
    hoy = _institucional(snap)
    if not hoy:
        return []
    previo = None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        if d.name >= snap:
            continue
        previo = _institucional(d.name)
        if previo is not None:
            break
    if previo is None:
        return []
    vistos = {(x.get("link"), x.get("pubdate")) for x in previo}
    return [x for x in hoy if (x.get("link"), x.get("pubdate")) not in vistos]


def codigos_de_evento_imposibles(conn, hoy: str) -> list[dict]:
    """Códigos GLIDE de UNOSAT cuya fecha implícita no puede ser cierta.

    Un `event_code` tipo `EQ20260822COL` lleva la fecha del evento dentro. Si
    esa fecha es POSTERIOR a la imagen que retrata el daño —o peor, posterior a
    hoy—, el código no puede designar un evento real: es un error de etiquetado
    en origen. Pasó de verdad (8 puntos de Manizales, ver docs/LIMITACIONES.md)
    y el monitor lo descubrió leyendo a mano, no porque nada avisara.

    R11: avisa, no rompe. Los puntos se siguen archivando con su literal.
    """
    fuera = []
    for code, cap, sensor_date, n in conn.execute(
            "SELECT event_code, capa, MIN(sensor_date), COUNT(*)"
            " FROM unosat_damage WHERE event_code IS NOT NULL"
            " GROUP BY event_code, capa"):
        m = re.match(r"^[A-Z]{2}(\d{4})(\d{2})(\d{2})[A-Z]{3}$", (code or "").upper())
        if not m:
            continue
        fecha = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        img = (f"{sensor_date[:4]}-{sensor_date[4:6]}-{sensor_date[6:8]}"
               if sensor_date and len(sensor_date) == 8 else None)
        if fecha > hoy:
            motivo = f"su fecha ({fecha}) aún no ha llegado"
        elif img and fecha > img:
            motivo = f"su fecha ({fecha}) es posterior a la imagen ({img})"
        else:
            continue
        fuera.append({"code": code, "capa": cap, "n": n, "motivo": motivo,
                      "fecha": fecha, "imagen": img})
    return fuera


def run(copernicus_summary: dict | None = None) -> list[dict]:
    conn = db()
    snap = today()
    alerts = []
    balance_consolidado = None

    # 1) activaciones Copernicus nuevas — SOLO Colombia
    for item in (copernicus_summary or {}).get("new", []):
        if "Colombia" not in (item.get("countries") or []):
            continue
        alerts.append({
            "tipo": "nueva_activacion", "nivel": "alta",
            "texto": f"Copernicus abrió una nueva activación en Colombia: "
                     f"{item.get('code')} — {item.get('name')}",
            **item})

    # 2) cambios en productos EMSR916 respecto al snapshot anterior
    prev = conn.execute(
        "SELECT MAX(snapshot_date) FROM products WHERE code='EMSR916'"
        " AND snapshot_date < ?", (snap,)).fetchone()[0]
    if prev:
        cur_rows = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(
            "SELECT aoi_name, ptype, monitoring_number, version_number, status_code"
            " FROM products WHERE code='EMSR916' AND snapshot_date=?", (snap,))}
        prev_rows = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(
            "SELECT aoi_name, ptype, monitoring_number, version_number, status_code"
            " FROM products WHERE code='EMSR916' AND snapshot_date=?", (prev,))}
        estados = {"W": "en espera", "I": "en producción", "F": "entregado",
                   "N": "no producido"}
        for key, (ver, st) in cur_rows.items():
            pv = prev_rows.get(key)
            if pv is None:
                alerts.append({
                    "tipo": "producto_nuevo", "nivel": "alta",
                    "texto": f"Copernicus publicó un producto nuevo para {key[0]}: "
                             f"{key[1]} v{ver} ({estados.get(st, st)})",
                    "aoi": key[0], "producto": key[1], "version": ver, "status": st})
            elif pv != (ver, st):
                alerts.append({
                    "tipo": "producto_actualizado", "nivel": "alta",
                    "texto": f"{key[0]}: {key[1]} pasó de v{pv[0]} "
                             f"({estados.get(pv[1], pv[1])}) a v{ver} "
                             f"({estados.get(st, st)})",
                    "aoi": key[0], "producto": key[1],
                    "antes": {"version": pv[0], "status": pv[1]},
                    "ahora": {"version": ver, "status": st}})

    # 2b) cronología institucional nueva (UNOSAT, ECHO, Copernicus…)
    # El feed institucional de GDACS traía el producto 4253 de UNOSAT —la
    # evaluación del epicentro— y el monitor lo publicaba en la línea de
    # tiempo sin avisar a nadie: aparecía si alguien miraba. Un producto
    # institucional nuevo es exactamente lo que este monitor existe para
    # cazar, así que va en nivel alta.
    for item in _institucionales_nuevos(snap):
        quien = _emisor(item.get("title") or "")
        alerts.append({
            "tipo": "institucional_nuevo", "nivel": "alta",
            "texto": f"{quien} publicó un producto nuevo del terremoto: "
                     f"{item.get('title') or 'sin título'}"
                     f"{(' — ' + item['link']) if item.get('link') else ''}",
            "emisor": quien, "titulo": item.get("title"),
            "url": item.get("link"), "pubdate": item.get("pubdate")})

    # 3) reportes ciudadanos nuevos (últimas 24 h, por fecha del reporte)
    n_ciud = conn.execute(
        "SELECT COUNT(*) FROM citizen_reports WHERE ts >= ?",
        (_ayer(),)).fetchone()[0]
    if n_ciud:
        alerts.append({
            "tipo": "reportes_ciudadanos", "nivel": "info",
            "texto": f"{n_ciud} reporte(s) ciudadano(s) nuevos en ChatMap "
                     f"en las últimas 24 h", "n": n_ciud})

    # 4) titulares nuevos hoy en los feeds comunitarios
    n_news = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE snapshot_date = ?",
        (snap,)).fetchone()[0]
    if n_news:
        alerts.append({
            "tipo": "titulares_nuevos", "nivel": "info",
            "texto": f"{n_news} titular(es) nuevos sobre el terremoto en los "
                     f"feeds de prensa", "n": n_news})

    # 5) balance nuevo en medios (worker IA): delta del último día vs el anterior
    st, feed = fetch_json(FEED_BALANCES, note="alerts balances", conn=conn,
                          snapshot_name="oficiales_feed.json")
    # detector de silencio: el worker corre a diario; si lleva >48 h sin
    # generar (clave caducada, cuota agotada, cron roto), avisar en alta
    gen = (feed or {}).get("generated_at")
    if not feed:
        alerts.append({
            "tipo": "worker_balances_caido", "nivel": "alta",
            "texto": f"El feed de balances no responde (HTTP {st}): revisar el "
                     f"worker en Cloudflare"})
    elif gen:
        edad_h = (datetime.now(timezone.utc)
                  - datetime.fromisoformat(gen.replace("Z", "+00:00"))
                  ).total_seconds() / 3600
        if edad_h > 48:
            alerts.append({
                "tipo": "worker_balances_silencio", "nivel": "alta",
                "texto": f"El worker de balances lleva {edad_h:.0f} h sin generar "
                         f"(última: {gen[:16]}): revisar logs en Cloudflare "
                         f"(¿clave de Firecrawl/Qwen caducada?)"})
    if feed and feed.get("items"):
        avisos, balance_consolidado = balance_de_medios(feed, snap)
        alerts.extend(avisos)

    # 6b) RUD: el registro oficial de damnificados crece — contar el delta
    hoy_rud = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(familias),0) FROM official_events"
        " WHERE source='ungrd_rud'").fetchone()
    prev_rud = None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        if d.name >= snap:
            continue
        f = d / "rud_2026T.json"
        if f.exists():
            rows = json.loads(f.read_text())
            rows = rows if isinstance(rows, list) else rows.get("data") or []
            prev_rud = (len(rows), sum(int(r.get("familias") or 0) for r in rows))
            break
    if hoy_rud and hoy_rud[0]:
        if prev_rud is None:
            alerts.append({
                "tipo": "rud_activo", "nivel": "alta",
                "texto": f"El RUD (registro oficial de damnificados) cubre el "
                         f"evento: {hoy_rud[0]} municipios, "
                         f"{hoy_rud[1]:,.0f} familias registradas".replace(",", ".")})
        elif (hoy_rud[0], hoy_rud[1]) != prev_rud:
            d_mun = hoy_rud[0] - prev_rud[0]
            d_fam = hoy_rud[1] - prev_rud[1]
            alerts.append({
                "tipo": "rud_actualizado", "nivel": "info",
                "texto": f"RUD actualizado: {'+' if d_mun >= 0 else ''}{d_mun} "
                         f"municipios, {'+' if d_fam >= 0 else ''}{d_fam:,.0f} "
                         f"familias desde la captura anterior".replace(",", ".")})

    # 6) ¿despertó la fuente oficial? (nivel alta: cambia el cruce entero)
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "ungrd_arcgis_agg.json"
        if f.exists():
            raw = json.loads(f.read_text())
            at = (raw.get("features") or [{}])[0].get("attributes", {})
            maxf = at.get("maxf")
            if isinstance(maxf, (int, float)):
                fecha = datetime.fromtimestamp(
                    maxf / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                if fecha > UNGRD_ESTANCADO:
                    alerts.append({
                        "tipo": "fuente_oficial_actualizada", "nivel": "alta",
                        "texto": f"¡El registro oficial UNGRD avanzó hasta {fecha}! "
                                 f"Revisar si ya hay EDAN del terremoto para "
                                 f"promover el cruce.", "max_fecha": fecha})
            break

    # 7) UNOSAT: códigos de evento con fecha imposible. Un código fechado
    # después de la imagen que retrata el daño —o en el futuro— es un supuesto
    # roto de manual, y hasta hoy no lo cantaba nadie.
    for x in codigos_de_evento_imposibles(conn, snap):
        alerts.append({
            "tipo": "unosat_codigo_evento_imposible", "nivel": "media",
            "texto": f"UNITAR-UNOSAT publica {x['n']} puntos con el código "
                     f"«{x['code']}» y {x['motivo']}: no puede designar un evento "
                     f"real, así que es un error de etiquetado en origen. El "
                     f"monitor los archiva con su literal y no los suma. Si "
                     f"UNOSAT lo corrige, entran solos.",
            "event_code": x["code"], "capa": x["capa"], "puntos": x["n"]})

    payload = {"generado": snap, "fecha": snap, "alertas": alerts}
    if balance_consolidado:
        payload["balance_consolidado"] = balance_consolidado
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "alerts.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False))
    (PUBLIC / "alerts.rss").write_text(alerts_rss(snap, alerts))
    conn.commit()
    conn.close()
    return alerts


def alerts_rss(fecha: str, alerts: list[dict]) -> str:
    """RSS 2.0 de las alertas del día (stdlib pura, R14) — simetría con el
    oficiales.rss del worker: quien no quiera push puede seguir el monitor
    desde cualquier lector RSS."""
    from email.utils import format_datetime
    from datetime import datetime, timezone
    from xml.sax.saxutils import escape
    base = "https://brechas.orkidea.eu/"
    pub = format_datetime(datetime.fromisoformat(fecha + "T11:00:00+00:00")
                          if len(fecha) == 10 else datetime.now(timezone.utc))
    items = "".join(
        f"<item><title>{escape(('⚠️ ' if a.get('nivel') == 'alta' else '') + (a.get('tipo') or '').replace('_', ' '))}</title>"
        f"<description>{escape(a.get('texto') or '')}</description>"
        f"<link>{base}#alerts-section</link>"
        f"<guid isPermaLink=\"false\">{escape(fecha)}-{escape(a.get('tipo') or '')}-{i}</guid>"
        f"<pubDate>{pub}</pubDate></item>"
        for i, a in enumerate(alerts))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>Alertas del monitor — terremoto Colombia 2026</title>"
        f"<link>{base}</link>"
        "<description>Cambios diarios detectados por el monitor de brechas: "
        "RUD, balances en medios, productos Copernicus y fuentes.</description>"
        "<language>es-co</language>"
        f"<lastBuildDate>{pub}</lastBuildDate>"
        f"{items}</channel></rss>")


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
