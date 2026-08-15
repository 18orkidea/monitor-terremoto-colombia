"""GDELT 2.0 DOC API: serie de volumen mediático. Límite duro: 1 petición / 5 s."""
from __future__ import annotations

import json
import time

from common import db, fetch_json, today

EVENT_KEY = "EQ1557236"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = "(terremoto OR sismo OR earthquake) Colombia"
START = "20260808000000"


def run() -> dict:
    conn = db()
    snap = today()
    time.sleep(5)  # respeto preventivo del rate limit compartido
    st, data = fetch_json(API, {
        "query": QUERY, "mode": "timelinevol",
        "startdatetime": START, "format": "json",
    }, note="gdelt timelinevol", snapshot_name="gdelt_timeline.json",
        conn=conn, retries=2, retry_wait=6)
    out = {"points": 0}
    if data:
        for tl in data.get("timeline", []):
            for p in tl.get("data", []):
                d = p.get("date", "")[:8]
                fecha = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else None
                if not fecha:
                    continue
                conn.execute(
                    "INSERT INTO media_volume (event_key, fecha, n_noticias_emm,"
                    " gdelt_vol, n_fuentes, n_chatmap, snapshot_date) VALUES (?,?,NULL,?,NULL,NULL,?)"
                    " ON CONFLICT(event_key, fecha, snapshot_date)"
                    " DO UPDATE SET gdelt_vol=excluded.gdelt_vol",
                    (EVENT_KEY, fecha, p.get("value"), snap))
                out["points"] += 1
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
