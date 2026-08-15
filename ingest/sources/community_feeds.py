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

from common import db, fetch, today, ROOT

REGISTRY = ROOT / "feeds" / "registry.json"


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


def run() -> dict:
    if not REGISTRY.exists():
        return {"error": "sin feeds/registry.json"}
    reg = json.loads(REGISTRY.read_text())
    kws = [k.lower() for k in reg.get("palabras_clave", [])]
    pat = re.compile("|".join(re.escape(k) for k in kws)) if kws else None
    conn = db()
    snap = today()
    out = {}
    for feed in reg.get("feeds", []):
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
            if pat and not pat.search(it["titulo"].lower()):
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
