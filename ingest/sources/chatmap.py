"""ChatMap (OSM Colombia + HOT): fuente primaria de daño ciudadano.

Endpoint de ACTIVACIÓN, no archivo permanente: cuando cierre puede desaparecer.
Por eso cada corrida guarda snapshot del GeoJSON y copia local de los medios
(sha256 incluido). Fotos y videos van a data/media/; los videos quedan fuera
de git (.gitignore) pero con hash y URL registrados, y su cuerpo vive en R2.

Un medio ya archivado NO se vuelve a pedir: es un activo, no un dato. Quien lo
decide es `common.activo_archivado`, que pregunta al archivo —la base y el
manifiesto de R2— y no al sistema de ficheros, que en la máquina de la corrida
arranca sin un solo vídeo. Ver docs/DECISIONES.md (24-ago-2026).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, timedelta

from common import (db, fetch, fetch_json, today, activo_archivado,
                    manifiesto_r2, FECHA_SISMO, MEDIA)

MAP_ID = "89319bbb-a14a-4dfd-b9a1-c83b8b55785f"
API = f"https://chatmap.hotosm.org/api/v1/map/{MAP_ID}"
EVENT_KEY = "EQ1557236"
MAX_MEDIA_BYTES = 300 * 1024 * 1024   # el archivo vive en R2 (10 GB gratis)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _round_pub(x: float) -> float:
    """~110 m de precisión pública (3 decimales)."""
    return round(x, 3)


def conteos_por_dia(feats: list[dict], snapshot_date: str) -> Counter:
    """Serie diaria de una captura acumulativa de ChatMap.

    La API devuelve todos los reportes de la activación, no un corte diario.
    Por eso, una fecha cerrada que no aparece en una captura posterior es un
    cero observado. Antes solo se escribían los días con reportes y el gráfico
    confundía esos ceros con días sin captura, dejando huecos el 16 y el 19 de
    agosto. El día de la corrida queda abierto: todavía puede recibir reportes.
    """
    days = Counter()
    for f in feats:
        t = (f.get("properties") or {}).get("time") or ""
        if len(t) >= 10:
            days[t[:10]] += 1

    try:
        cursor = date.fromisoformat(FECHA_SISMO)
        ultimo_cerrado = date.fromisoformat(snapshot_date) - timedelta(days=1)
    except ValueError:
        return days
    while cursor <= ultimo_cerrado:
        days.setdefault(cursor.isoformat(), 0)
        cursor += timedelta(days=1)
    return days


def run(download_media: bool = True) -> dict:
    conn = db()
    snap = today()
    st, data = fetch_json(API, note="chatmap", snapshot_name="chatmap.json", conn=conn)
    if not data:
        conn.commit(); conn.close()
        return {"error": f"chatmap HTTP {st} (¿activación cerrada? ver snapshots previos)"}

    feats = data.get("features", [])
    MEDIA.mkdir(parents=True, exist_ok=True)
    days = conteos_por_dia(feats, snap)
    # el manifiesto se lee UNA vez por corrida, no 542 veces: es un fichero
    # versionado que no cambia mientras dura la ingesta
    manifiesto = manifiesto_r2()
    n_media = n_reutilizados = 0
    for f in feats:
        p = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        rid = p.get("id") or hashlib.sha1(
            json.dumps([coords, p.get("time")]).encode()).hexdigest()[:16]
        t = p.get("time") or ""
        murl = p.get("file") or ""
        mlocal, msha = None, None
        if murl and download_media:
            fname = murl.rsplit("/", 1)[-1]
            dest = MEDIA / fname
            # El guardián pregunta AL ARCHIVO, no al disco: los vídeos están en
            # .gitignore y la máquina de la corrida arranca sin uno solo, así
            # que mirar el disco era decir «no lo tengo» sobre cuerpos que
            # llevaban días archivados en R2 con su sha256. Ver
            # `common.activo_archivado` y docs/DECISIONES.md (24-ago-2026).
            ya = activo_archivado(murl, conn, destino=dest,
                                  manifiesto=manifiesto)
            if ya:
                msha, mlocal = ya["sha256"], ya["ruta"]
                n_reutilizados += 1
            else:
                # save_to: fetch persiste el medio y lo registra como
                # snapshot_path — la fila del log siempre apunta a un cuerpo
                mst, body = fetch(murl, note=f"chatmap media {fname}", conn=conn,
                                  retries=1, timeout=120,
                                  save_to=dest, max_save_bytes=MAX_MEDIA_BYTES)
                if mst == 200 and body and len(body) <= MAX_MEDIA_BYTES:
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
            "medios_nuevos": n_media, "medios_ya_archivados": n_reutilizados}


if __name__ == "__main__":
    import sys
    print(json.dumps(run(download_media="--no-media" not in sys.argv), indent=1))
