"""GDACS: metadatos del evento + feeds de noticias (institucional y EMM).

Los feeds traen ventana datefrom/dateto (~5 días): las noticias se purgan.
El snapshot diario es la única forma de conservar la serie completa.
"""
from __future__ import annotations

import json
from collections import Counter

from common import db, fetch_json, today

EVENT_TYPE, EVENT_ID = "EQ", "1557236"
EVENT_KEY = f"{EVENT_TYPE}{EVENT_ID}"
BASE = "https://www.gdacs.org/gdacsapi/api"


def run() -> dict:
    conn = db()
    out = {}
    snap = today()

    st, ev = fetch_json(f"{BASE}/events/geteventdata",
                        {"eventtype": EVENT_TYPE, "eventid": EVENT_ID},
                        note="gdacs event", snapshot_name="gdacs_event.json", conn=conn)
    if ev:
        p = ev.get("properties", {})
        out["event"] = {"alertlevel": p.get("alertlevel"), "glide": p.get("glide"),
                        "name": p.get("name"), "datemodified": p.get("datemodified")}

    st, inst = fetch_json(f"{BASE}/news/getnewsbygdacskey",
                          {"eventtype": EVENT_TYPE, "eventid": EVENT_ID},
                          note="gdacs institucional",
                          snapshot_name="gdacs_news_institucional.json", conn=conn)
    out["institucional"] = [
        {"pubdate": x.get("pubdate"), "title": x.get("title"), "link": x.get("link")}
        for x in inst or []
    ]

    st, emm = fetch_json(f"{BASE}/emm/getemmnewsbykey",
                         {"eventtype": EVENT_TYPE, "eventid": EVENT_ID},
                         note="gdacs emm", snapshot_name="gdacs_emm.json", conn=conn)
    emm = emm or []
    days = Counter((x.get("pubdate") or "")[:10] for x in emm)
    days.pop("", None)
    srcs = {d: set() for d in days}
    for x in emm:
        d = (x.get("pubdate") or "")[:10]
        if d in srcs:
            srcs[d].add(x.get("source"))
    for d, n in sorted(days.items()):
        conn.execute(
            "INSERT OR REPLACE INTO media_volume (event_key, fecha, n_noticias_emm,"
            " gdelt_vol, n_fuentes, n_chatmap, snapshot_date)"
            " VALUES (?,?,?,"
            "  COALESCE((SELECT gdelt_vol FROM media_volume WHERE event_key=? AND fecha=? AND snapshot_date=?), NULL),"
            "  ?,"
            "  COALESCE((SELECT n_chatmap FROM media_volume WHERE event_key=? AND fecha=? AND snapshot_date=?), NULL),"
            "  ?)",
            (EVENT_KEY, d, n, EVENT_KEY, d, snap, len(srcs[d]),
             EVENT_KEY, d, snap, snap))
    out["emm"] = {"total": len(emm), "por_dia": dict(sorted(days.items()))}
    conn.commit()
    conn.close()
    return out


def emm_items():
    """Items EMM del último snapshot (para el emparejamiento por topónimo)."""
    from common import snapshot_dir
    p = snapshot_dir() / "gdacs_emm.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False)[:1500])
