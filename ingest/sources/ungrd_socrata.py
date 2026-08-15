"""Socrata datos.gov.co (wwkg-r6te): sólo métricas de brecha.

El dataset para en 2022-12-31; no se descargan sus 25k filas — su valor aquí
es documentar hasta cuándo publica la vía oficial 'datos abiertos'.
"""
from __future__ import annotations

import json

from common import db, fetch_json

API = "https://www.datos.gov.co/resource/wwkg-r6te.json"


def run() -> dict:
    conn = db()
    st, data = fetch_json(API, {
        "$select": "count(*) as n, min(fecha) as desde, max(fecha) as hasta"},
        note="socrata brecha", snapshot_name="ungrd_socrata_agg.json", conn=conn)
    conn.commit()
    conn.close()
    if data:
        row = data[0]
        return {"total": row.get("n"), "desde": row.get("desde"),
                "hasta": row.get("hasta")}
    return {"error": f"HTTP {st}"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
