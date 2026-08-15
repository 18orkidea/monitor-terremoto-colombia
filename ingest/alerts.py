"""Alertas: qué cambió respecto al snapshot anterior.

- Activaciones EMSR nuevas (cualquier país; Colombia destacada)
- Cambios de versión o statusCode en productos EMSR916
- Cambios en el máximo de fecha de las fuentes oficiales (¡si UNGRD despierta!)
"""
from __future__ import annotations

import json

from common import db, today, utcnow, PUBLIC


def run(copernicus_summary: dict | None = None) -> list[dict]:
    conn = db()
    snap = today()
    alerts = []

    for item in (copernicus_summary or {}).get("new", []):
        level = "alta" if "Colombia" in (item.get("countries") or []) else "info"
        alerts.append({"tipo": "nueva_activacion", "nivel": level, **item})

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
        for key, (ver, st) in cur_rows.items():
            pv = prev_rows.get(key)
            if pv is None:
                alerts.append({"tipo": "producto_nuevo", "nivel": "alta",
                               "aoi": key[0], "producto": key[1],
                               "version": ver, "status": st})
            elif pv != (ver, st):
                alerts.append({"tipo": "producto_actualizado", "nivel": "alta",
                               "aoi": key[0], "producto": key[1],
                               "antes": {"version": pv[0], "status": pv[1]},
                               "ahora": {"version": ver, "status": st}})
    payload = {"generado": snap, "fecha": snap, "alertas": alerts}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "alerts.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False))
    conn.close()
    return alerts


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
