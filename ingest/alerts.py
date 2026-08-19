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
from datetime import datetime, timedelta, timezone

from common import db, fetch_json, today, PUBLIC, SNAPSHOTS

FEED_BALANCES = ("https://monitor-terremoto-colombia-oficiales-ai"
                 ".inforesidencias.workers.dev/oficiales.json")
UNGRD_ESTANCADO = "2024-02-17"   # si supera esto, la fuente oficial despertó


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


def run(copernicus_summary: dict | None = None) -> list[dict]:
    conn = db()
    snap = today()
    alerts = []

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
        por_dia = {}
        for it in feed["items"]:
            d = it.get("search_date")
            c = it.get("cifras") or {}
            if d and c.get("fallecidos") is not None:
                mejor = por_dia.get(d)
                if not mejor or (c.get("fallecidos") or 0) > (mejor.get("fallecidos") or 0):
                    por_dia[d] = c
        dias = sorted(por_dia)
        if dias and dias[-1] in (snap, _ayer()):
            ult, c = dias[-1], por_dia[dias[-1]]
            delta = ""
            if len(dias) > 1:
                prev_c = por_dia[dias[-2]]
                if prev_c.get("fallecidos") is not None:
                    d_f = (c.get("fallecidos") or 0) - (prev_c.get("fallecidos") or 0)
                    delta = f" ({'+' if d_f >= 0 else ''}{d_f} vs día anterior)"
            alerts.append({
                "tipo": "balance_en_medios", "nivel": "info",
                "texto": f"Balance en medios citando fuentes oficiales ({ult}): "
                         f"{c.get('fallecidos')} fallecidos{delta}, "
                         f"{c.get('heridos') or '?'} heridos, "
                         f"{c.get('desaparecidos') or '?'} desaparecidos",
                "fecha_balance": ult, "cifras": c})

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
                         f"familias vs snapshot anterior".replace(",", ".")})

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

    payload = {"generado": snap, "fecha": snap, "alertas": alerts}
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
    base = "https://brechas.orkidea.eu/site/"
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
