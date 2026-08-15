"""Feeds de noticias aportados por la comunidad (feeds/registry.json).

Cualquier voluntario puede añadir un feed RSS/Atom con un PR: una entrada en el
registro basta. Los items se filtran por las palabras clave del evento y entran
en el mismo circuito que el resto de noticias (página de titulares + cruce por
topónimo). Un feed caído nunca rompe la corrida: se registra y se sigue.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

from common import db, fetch, today, ROOT
from municipios import MUNICIPIOS

REGISTRY = ROOT / "feeds" / "registry.json"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def _parse_date(s: str) -> str:
    if not s:
        return ""
    try:
        return parsedate_to_datetime(s).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return s[:19]


def parse_rss(body: bytes) -> list[dict]:
    """RSS 2.0 y Atom, con tolerancia a namespaces."""
    items = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.iter("item"):                      # RSS 2.0
        items.append({
            "titulo": (it.findtext("title") or "").strip(),
            "url": (it.findtext("link") or "").strip(),
            "fecha": _parse_date(it.findtext("pubDate") or ""),
        })
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):   # Atom
        link = it.find("atom:link", ns)
        items.append({
            "titulo": (it.findtext("atom:title", default="", namespaces=ns) or "").strip(),
            "url": (link.get("href") if link is not None else "").strip(),
            "fecha": (it.findtext("atom:updated", default="", namespaces=ns) or "")[:19],
        })
    return [i for i in items if i["url"] and i["titulo"]]


def _slug(s: str) -> str:
    from municipios import _norm
    return re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")


def municipal_google_news_feeds() -> list[dict]:
    """Búsquedas Google News por municipio observado en el área de influencia."""
    from municipios import _norm
    feeds = []
    for municipio, meta in MUNICIPIOS.items():
        depto = meta["departamento"]
        query = f'("terremoto" OR "sismo" OR "temblor") "{_norm(municipio)}" "{_norm(depto)}"'
        feeds.append({
            "id": f"googlenews-municipio-{_slug(municipio)}",
            "nombre": f"Google News — {municipio}",
            "tipo": "rss",
            "url": f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=es-CO&gl=CO&ceid=CO:es",
            "idioma": "es",
            "activo": True,
            "municipio": municipio,
            "nota": "Búsqueda generada desde la lista de municipios de influencia.",
        })
    return feeds


def iter_feeds(reg: dict) -> list[dict]:
    feeds = list(reg.get("feeds", []))
    if reg.get("busquedas_municipales_google_news", True):
        feeds.extend(municipal_google_news_feeds())
    return feeds


def _relevante(item: dict, feed: dict, pat: re.Pattern | None) -> bool:
    title = item["titulo"].lower()
    if feed.get("municipio"):
        return True
    return not pat or bool(pat.search(title))


def run() -> dict:
    if not REGISTRY.exists():
        return {"error": "sin feeds/registry.json"}
    reg = json.loads(REGISTRY.read_text())
    kws = [k.lower() for k in reg.get("palabras_clave", [])]
    pat = re.compile("|".join(re.escape(k) for k in kws)) if kws else None
    conn = db()
    snap = today()
    out = {}
    for feed in iter_feeds(reg):
        if not feed.get("activo") or feed.get("tipo") != "rss":
            continue  # los 'builtin' (GDACS EMM) los ingesta su propio módulo
        fid = feed["id"]
        status, body = fetch(feed["url"], note=f"feed comunitario {fid}",
                             snapshot_name=f"feed_{fid}.xml", conn=conn, retries=1)
        if status != 200 or not body:
            out[fid] = {"error": f"HTTP {status}"}
            continue
        items = parse_rss(body)
        kept = 0
        for it in items:
            if not _relevante(it, feed, pat):
                continue
            conn.execute(
                "INSERT INTO news_items (url, feed_id, fecha, titulo, medio,"
                " snapshot_date) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(url) DO NOTHING",
                (it["url"], fid, it["fecha"], it["titulo"][:300],
                 feed.get("nombre", fid), snap))
            kept += 1
        out[fid] = {"items_feed": len(items), "relevantes": kept}
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
