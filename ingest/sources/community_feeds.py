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
from urllib.parse import quote_plus, urlparse

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


def dominio(url: str) -> str | None:
    """Host de una URL, sin `www.`. Sin host no hay dato: NULL, nunca "" (R3)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    host = host.removeprefix("www.")
    return host or None


def _fuente_rss(it) -> tuple[str | None, str | None]:
    """El medio que el propio feed declara en `<source url="…">Nombre</source>`.

    Es el único sitio donde el medio real viaja limpio: en los feeds de Google
    News el `<link>` apunta a news.google.com y el nombre solo aparece como
    sufijo del titular, que es frágil. Los feeds propios de los medios (El
    Colombiano, Q'hubo, La Patria) no emiten `<source>`: ahí no hay dato, y no
    tenerlo se dice con NULL.
    """
    src = it.find("source")
    if src is None:
        return None, None
    nombre = (src.text or "").strip() or None
    return nombre, dominio(src.get("url") or "")


def _dominio_atom(entry, ns) -> str | None:
    """Dominio de `<source><link href="…">` en un feed Atom."""
    link = entry.find("atom:source/atom:link", ns)
    return dominio(link.get("href") or "") if link is not None else None


def parse_rss(body: bytes) -> list[dict]:
    """RSS 2.0 y Atom, con tolerancia a namespaces."""
    items = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.iter("item"):                      # RSS 2.0
        medio_canonico, medio_dominio = _fuente_rss(it)
        items.append({
            "titulo": (it.findtext("title") or "").strip(),
            "url": (it.findtext("link") or "").strip(),
            "fecha": _parse_date(it.findtext("pubDate") or ""),
            "resumen": (it.findtext("description") or "").strip(),
            "medio_canonico": medio_canonico,
            "medio_dominio": medio_dominio,
        })
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):   # Atom
        link = it.find("atom:link", ns)
        url = (link.get("href") if link is not None else "").strip()
        items.append({
            "titulo": (it.findtext("atom:title", default="", namespaces=ns) or "").strip(),
            "url": url,
            "fecha": (it.findtext("atom:updated", default="", namespaces=ns) or "")[:19],
            "resumen": (it.findtext("atom:summary", default="", namespaces=ns) or "").strip(),
            # Atom envuelve la fuente en <source><title>: otro árbol, mismo
            # dato, y el dominio cuelga de <source><link href>.
            "medio_canonico": (it.findtext("atom:source/atom:title", default="",
                                           namespaces=ns) or "").strip() or None,
            "medio_dominio": _dominio_atom(it, ns),
        })
    return [i for i in items if i["url"] and i["titulo"]]


def _slug(s: str) -> str:
    from municipios import _norm
    return re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")


def municipal_google_news_feeds() -> list[dict]:
    """Búsquedas Google News por municipio observado en el área de influencia.

    Dos cuidados que no son cosméticos:

    - La frase buscada es el TOPÓNIMO, no la clave del diccionario: claves
      desambiguadas como «Riosucio (Caldas)» producirían la frase literal
      `"riosucio (caldas)"`, que no aparece en ningún titular — un feed que
      devuelve cero para siempre y nadie sabe por qué.
    - Los municipios homónimos de un departamento (Risaralda en Caldas,
      Córdoba en Quindío) NO generan feed: su búsqueda `"risaralda" "caldas"`
      casa con los titulares del departamento, y como el feed declara su
      municipio, se colaría por la puerta de atrás la atribución que
      `_menciona_municipio` rechaza. Su prensa solo puede venir de un feed del
      registro comunitario, donde el municipio lo declara una persona.
    """
    from municipios import _norm
    feeds = []
    for municipio, meta in MUNICIPIOS.items():
        if meta.get("homonimo_de_departamento"):
            continue
        depto = meta["departamento"]
        frase = meta["toponimos"][0]
        query = f'("terremoto" OR "sismo" OR "temblor") "{frase}" "{_norm(depto)}"'
        feeds.append({
            "id": f"googlenews-municipio-{_slug(municipio)}",
            "nombre": f"Google News — {municipio}",
            "tipo": "rss",
            "url": f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=es-CO&gl=CO&ceid=CO:es",
            "idioma": "es",
            "activo": True,
            "municipio": municipio,
            "municipios": [municipio],
            "departamentos": [depto],
            "nota": "Búsqueda generada desde la lista de municipios de influencia.",
        })
    return feeds


def iter_feeds(reg: dict) -> list[dict]:
    feeds = list(reg.get("feeds", []))
    if reg.get("busquedas_municipales_google_news", True):
        feeds.extend(municipal_google_news_feeds())
    return feeds


def feed_index(reg: dict | None = None) -> dict[str, dict]:
    if reg is None:
        reg = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    return {feed["id"]: feed for feed in iter_feeds(reg)}


def _relevante(item: dict, feed: dict, pat: re.Pattern | None) -> bool:
    text = f"{item.get('titulo') or ''} {item.get('resumen') or ''}".lower()
    if feed.get("municipio"):
        return not pat or bool(pat.search(text))
    return not pat or bool(pat.search(text))


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
                " medio_canonico, medio_dominio, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?)"
                # Rellena el medio si faltaba, pero nunca lo reescribe: un item
                # ya archivado conserva lo que se capturó el día que se capturó.
                " ON CONFLICT(url) DO UPDATE SET"
                "   medio_canonico = COALESCE(medio_canonico, excluded.medio_canonico),"
                "   medio_dominio  = COALESCE(medio_dominio,  excluded.medio_dominio)",
                (it["url"], fid, it["fecha"], it["titulo"][:300],
                 feed.get("nombre", fid), it.get("medio_canonico"),
                 it.get("medio_dominio"), snap))
            kept += 1
        out[fid] = {"items_feed": len(items), "relevantes": kept}
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
