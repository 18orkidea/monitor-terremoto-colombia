"""RUD — Registro Único de Damnificados (UNGRD).

LA fuente que faltaba: la primera oficial que cubre el evento de 2026, con
datos por municipio (familias, personas, viviendas). Endpoint público de
lectura descubierto el 16-ago-2026; no es una API documentada, así que el
parser es tolerante y su test de supuesto vigilará que siga vivo.

Matiz importante: el RUD lo cargan las autoridades municipales — que un
municipio no aparezca no significa "sin daño", significa "sin registro aún".
Esa asimetría es en sí misma una brecha que el monitor muestra.
"""
from __future__ import annotations

import json

from common import db, fetch_json, today

URL = "https://rud.gestiondelriesgo.gov.co/home/json.php?temp=2026T"


def _fecha_iso(f: str) -> str | None:
    try:
        d, m, a = (f or "").split("/")
        return f"{a}-{m}-{d}"
    except ValueError:
        return None


def _n(v):
    try:
        return int(str(v).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def run() -> dict:
    conn = db()
    status, data = fetch_json(URL, note="rud 2026T",
                              snapshot_name="rud_2026T.json", conn=conn)
    if not data:
        conn.commit(); conn.close()
        return {"error": f"RUD HTTP {status} (endpoint no documentado: "
                         "puede haber cambiado — ver snapshots previos)"}
    rows = data if isinstance(data, list) else data.get("data") or []
    n = 0
    for r in rows:
        dep = (r.get("departamento") or "").strip()
        mun = (r.get("municipio") or "").strip()
        fecha = _fecha_iso(r.get("fecha_evento"))
        if not mun or not fecha:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO official_events (source, external_id, fecha,"
            " departamento, municipio, evento, personas, familias,"
            " viv_destruidas, viv_averiadas)"
            " VALUES ('ungrd_rud',?,?,?,?,?,?,?,?,?)",
            (f"{dep}|{mun}|{fecha}", fecha, dep, mun, r.get("evento"),
             _n(r.get("personas")), _n(r.get("familias")),
             _n(r.get("destruidas")), _n(r.get("averiadas"))))
        conn.execute(
            "INSERT OR REPLACE INTO rud_daily (snapshot_date, departamento,"
            " municipio, familias, personas, viv_destruidas, viv_averiadas,"
            " habitables, nohabitables) VALUES (?,?,?,?,?,?,?,?,?)",
            (today(), dep, mun, _n(r.get("familias")), _n(r.get("personas")),
             _n(r.get("destruidas")), _n(r.get("averiadas")),
             _n(r.get("habitables")), _n(r.get("nohabitables"))))
        n += 1
    conn.commit()
    tot = conn.execute(
        "SELECT COUNT(*), SUM(familias), SUM(personas), SUM(viv_destruidas),"
        " SUM(viv_averiadas) FROM official_events WHERE source='ungrd_rud'"
    ).fetchone()
    conn.close()
    return {"registros": n, "municipios_en_bd": tot[0],
            "familias": tot[1], "personas": tot[2],
            "viv_destruidas": tot[3], "viv_averiadas": tot[4]}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
