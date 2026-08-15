"""EMSC seismicportal: felt reports (segunda fuente de intensidad percibida)."""
from __future__ import annotations

import json

from common import db, fetch_json

UNID = "20260810_0000177"
API = "https://www.seismicportal.eu/testimonies-ws/api/search"


def run() -> dict:
    conn = db()
    st, data = fetch_json(API, {"unids": UNID}, note="emsc testimonies",
                          snapshot_name="emsc_testimonies.json", conn=conn)
    conn.commit()
    conn.close()
    feats = (data or {}).get("features") or []
    if feats:
        p = feats[0].get("properties", {})
        return {"feltreport_count": p.get("feltreportCount"),
                "last_update": p.get("last_update")}
    return {"error": f"HTTP {st}"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
