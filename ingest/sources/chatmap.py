"""ChatMap (OSM Colombia + HOT): fuente primaria de daño ciudadano.

Endpoint de ACTIVACIÓN, no archivo permanente: cuando cierre puede desaparecer.
Por eso cada corrida guarda snapshot del GeoJSON y copia local de los medios
(sha256 incluido). Fotos y videos van a data/media/; los videos quedan fuera
de git (.gitignore) pero con hash y URL registrados.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from common import db, fetch, fetch_json, today, MEDIA

MAP_ID = "89319bbb-a14a-4dfd-b9a1-c83b8b55785f"
API = f"https://chatmap.hotosm.org/api/v1/map/{MAP_ID}"
EVENT_KEY = "EQ1557236"
MAX_MEDIA_BYTES = 40 * 1024 * 1024
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _round_pub(x: float) -> float:
    """~110 m de precisión pública (3 decimales)."""
    return round(x, 3)


def run(download_media: bool = True) -> dict:
    conn = db()
    snap = today()
    st, data = fetch_json(API, note="chatmap", snapshot_name="chatmap.json", conn=conn)
    if not data:
        conn.commit(); conn.close()
        return {"error": f"chatmap HTTP {st} (¿activación cerrada? ver snapshots previos)"}

    feats = data.get("features", [])
    MEDIA.mkdir(parents=True, exist_ok=True)
    days = Counter()
    n_media = 0
    for f in feats:
        p = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        rid = p.get("id") or hashlib.sha1(
            json.dumps([coords, p.get("time")]).encode()).hexdigest()[:16]
        t = p.get("time") or ""
        days[t[:10]] += 1
        murl = p.get("file") or ""
        mlocal, msha = None, None
        if murl and download_media:
            fname = murl.rsplit("/", 1)[-1]
            dest = MEDIA / fname
            if dest.exists():
                msha = hashlib.sha256(dest.read_bytes()).hexdigest()
                mlocal = str(dest.relative_to(MEDIA.parent.parent))
            else:
                mst, body = fetch(murl, note=f"chatmap media {fname}", conn=conn,
                                  retries=1, timeout=120)
                if mst == 200 and body and len(body) <= MAX_MEDIA_BYTES:
                    dest.write_bytes(body)
                    msha = hashlib.sha256(body).hexdigest()
                    mlocal = str(dest.relative_to(MEDIA.parent.parent))
                    n_media += 1
        conn.execute(
            "INSERT INTO citizen_reports (origen, id_externo, ts, lat, lon,"
            " lat_pub, lon_pub, media_url, media_local, media_sha256, mensaje,"
            " estado, snapshot_date)"
            " VALUES ('chatmap',?,?,?,?,?,?,?,?,?,?,'recibido',?)"
            " ON CONFLICT(origen, id_externo) DO UPDATE SET"
            "  media_local=COALESCE(excluded.media_local, media_local),"
            "  media_sha256=COALESCE(excluded.media_sha256, media_sha256),"
            "  snapshot_date=excluded.snapshot_date",
            (str(rid), t, lat, lon,
             _round_pub(lat) if lat is not None else None,
             _round_pub(lon) if lon is not None else None,
             murl, mlocal, msha, p.get("message") or "", snap))
        conn.commit()   # commit por fila: no retener el lock durante descargas
    days.pop("", None)
    for d, n in days.items():
        conn.execute(
            "INSERT INTO media_volume (event_key, fecha, n_noticias_emm, gdelt_vol,"
            " n_fuentes, n_chatmap, snapshot_date) VALUES (?,?,NULL,NULL,NULL,?,?)"
            " ON CONFLICT(event_key, fecha, snapshot_date)"
            " DO UPDATE SET n_chatmap=excluded.n_chatmap",
            (EVENT_KEY, d, n, snap))
    conn.commit()
    conn.close()
    return {"reportes": len(feats), "por_dia": dict(sorted(days.items())),
            "medios_nuevos": n_media}


if __name__ == "__main__":
    import sys
    print(json.dumps(run(download_media="--no-media" not in sys.argv), indent=1))
