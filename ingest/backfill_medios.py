"""Reconstruye el medio de cada noticia releyendo los snapshots archivados.

Durante meses `news_items.medio` guardó el nombre del FEED («Google News —
Nóvita»), no el del medio, y en la mitad de las filas la `url` apunta a
news.google.com, no a la cabecera. El nombre real nunca se perdió: viajaba en
cada `<item>` del RSS, en `<source url="…">Nombre</source>`, y los snapshots
son inmutables — están todos en `data/snapshots/`.

Así que esto no descarga nada. Abre el archivo que ya tenemos, cruza por
`<link>` y rellena `medio_canonico` / `medio_dominio` donde estaban vacías.
Reconstrucción desde el propio archivo: exactamente lo que el archivo existe
para permitir. Ninguna columna se sobrescribe y `url` no se toca (R4).

Relee el archivo entero en cada corrida, a propósito. Medido sobre los 423
snapshots de feeds de agosto de 2026: 0,31 s, ruido frente a las trece fuentes
que la corrida pide por HTTP. Acotarlo a los snapshots del día ahorraría
centésimas y abriría un hueco silencioso — cualquier fila que quedara sin medio
(una corrida interrumpida, un dump reconstruido a medias) no se recuperaría
jamás, porque nada avisa de ella. Si algún día el archivo pesa lo suficiente
como para que esto se note, se acota con la medida delante.

Uso:
  python ingest/backfill_medios.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "sources"))

from common import (NOTA_RECONSTRUCCION, ORIGEN_ARCHIVO, ROOT, db,  # noqa: E402
                    registrar_derivacion)
from sources.community_feeds import _dominio_atom, _fuente_rss  # noqa: E402

SNAPSHOTS = ROOT / "data" / "snapshots"
ATOM = {"atom": "http://www.w3.org/2005/Atom"}


def medios_archivados(snapshots: Path | None = None) -> dict[str, tuple[str, str | None]]:
    """`{link: (nombre, dominio)}` a partir de los feeds ya archivados.

    Gana el snapshot más antiguo: es el que estaba más cerca de la publicación.
    Lee RSS y Atom, las dos formas que `parse_rss` sabe ingerir — si la ingesta
    viva reconoce una fuente, la reconstrucción tiene que reconocerla también,
    o el archivo recordaría menos de lo que supo en su día.
    """
    raiz = snapshots or SNAPSHOTS
    fuentes: dict[str, tuple[str, str | None]] = {}
    if not raiz.exists():
        return fuentes

    def anota(link: str, nombre: str | None, dom: str | None) -> None:
        if link and nombre and link not in fuentes:
            fuentes[link] = (nombre, dom)

    for dia in sorted(p for p in raiz.iterdir() if p.is_dir()):
        for xml in sorted(dia.glob("feed_*.xml")):
            try:
                root = ET.fromstring(xml.read_bytes())
            except ET.ParseError:
                continue          # un snapshot corrupto no rompe el resto
            for it in root.iter("item"):                       # RSS 2.0
                nombre, dom = _fuente_rss(it)
                anota((it.findtext("link") or "").strip(), nombre, dom)
            for it in root.iter("{http://www.w3.org/2005/Atom}entry"):   # Atom
                link = it.find("atom:link", ATOM)
                nombre = (it.findtext("atom:source/atom:title", default="",
                                      namespaces=ATOM) or "").strip() or None
                anota((link.get("href") if link is not None else "").strip(),
                      nombre, _dominio_atom(it, ATOM))
    return fuentes


def pendientes(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE medio_canonico IS NULL").fetchone()[0]


def run(conn: sqlite3.Connection | None = None,
        snapshots: Path | None = None) -> dict:
    """Rellena el medio de las noticias que aún no lo tienen.

    Hay un suelo que no bajará de ahí: los feeds propios de los medios (El
    Colombiano, Q'hubo, La Patria) no emiten `<source>`, así que sus items
    constarán como pendientes para siempre. No es un hueco por rellenar; es un
    dato que esa fuente nunca publicó, y decirlo con NULL es lo correcto (R3).
    """
    propia = conn is None
    conn = conn or db()
    try:
        faltan = pendientes(conn)
        if not faltan:
            return {"pendientes": 0, "rellenados": 0,
                    "nota": "nada que reconstruir"}
        fuentes = medios_archivados(snapshots)
        rellenados = 0
        for url, in conn.execute(
                "SELECT url FROM news_items WHERE medio_canonico IS NULL").fetchall():
            dato = fuentes.get(url)
            if not dato:
                continue
            nombre, dom = dato
            # Solo donde está vacío: el backfill rellena huecos, no reescribe.
            conn.execute(
                "UPDATE news_items SET medio_canonico = ?, medio_dominio = ?"
                " WHERE url = ? AND medio_canonico IS NULL", (nombre, dom, url))
            rellenados += 1
        if rellenados:
            # Que dentro de veinte años se pueda distinguir un medio capturado
            # el día del <item> de uno reconstruido después. Lo que no consta,
            # no ocurrió.
            registrar_derivacion(
                conn, ORIGEN_ARCHIVO,
                f"{NOTA_RECONSTRUCCION}: {rellenados} de {faltan} noticias"
                f" sin cabecera")
        conn.commit()
        return {"pendientes": faltan, "rellenados": rellenados,
                "sin_medio_en_archivo": faltan - rellenados,
                "links_en_snapshots": len(fuentes)}
    finally:
        if propia:
            conn.close()


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
