"""Copernicus EMS Rapid Mapping: enumeración de códigos y detalle por activación.

La API exige `code` (no hay listado). Rango público medido en 2026-08-15:
EMSR673 → adelante, con huecos puntuales (p. ej. EMSR700, EMSR880) que son
normales: activaciones sensibles o códigos no asignados.
"""
from __future__ import annotations

import json
import time

from common import db, fetch_json, today, to_num, utcnow

BASE = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"
BACKFILL_START = 673
PAUSE = 0.4          # cortesía con el backend
GAP_TOLERANCE = 25   # huecos consecutivos antes de asumir fin de códigos asignados


def fetch_activation(code: str, conn):
    status, data = fetch_json(BASE, {"code": code}, note=f"copernicus {code}",
                              snapshot_name=f"copernicus_{code}.json", conn=conn)
    results = (data or {}).get("results") or []
    return status, (results[0] if results else None)


def store_index(conn, code: str, act: dict | None):
    now = utcnow()
    if act is None:
        conn.execute(
            "INSERT INTO activation_index (code, exists_public, first_seen, last_checked)"
            " VALUES (?,0,?,?)"
            " ON CONFLICT(code) DO UPDATE SET last_checked=excluded.last_checked",
            (code, now, now))
        return
    countries = ",".join(c.get("name", "") for c in act.get("countries") or [])
    conn.execute(
        "INSERT INTO activation_index (code, exists_public, name, category, countries,"
        " event_time, first_seen, last_checked) VALUES (?,1,?,?,?,?,?,?)"
        " ON CONFLICT(code) DO UPDATE SET exists_public=1, name=excluded.name,"
        " category=excluded.category, countries=excluded.countries,"
        " event_time=excluded.event_time, last_checked=excluded.last_checked",
        (code, act.get("name"), act.get("category"), countries,
         act.get("eventTime"), now, now))


def store_detail(conn, act: dict):
    """Detalle completo (AOIs, productos, stats) — se guarda para Colombia."""
    snap = today()
    code = act["code"]
    countries = ",".join(c.get("name", "") for c in act.get("countries") or [])
    conn.execute(
        "INSERT OR REPLACE INTO activations (code, snapshot_date, name, category,"
        " sub_category, event_time, activation_time, closed, gdacs_id, countries,"
        " centroid_wkt, extent_wkt, raw_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, snap, act.get("name"), act.get("category"), act.get("subCategory"),
         act.get("eventTime"), act.get("activationTime"),
         1 if act.get("closed") else 0, act.get("gdacsId"), countries,
         act.get("centroid"), act.get("extent"), None))
    for aoi in act.get("aois") or []:
        for p in aoi.get("products") or []:
            v = p.get("version") or {}
            mon_n = p.get("monitoringNumber") or 0
            ver_n = v.get("number") or 0
            conn.execute(
                "INSERT OR REPLACE INTO products (code, aoi_name, aoi_number, ptype,"
                " monitoring, monitoring_number, version_number, status_code, feasible,"
                " expected_delivery, delivery_time, download_path, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code, aoi.get("name"), aoi.get("number"), p.get("type"),
                 1 if p.get("monitoring") else 0, mon_n, ver_n,
                 v.get("statusCode"), 1 if p.get("feasible") else 0,
                 p.get("expectedDelivery"), v.get("deliveryTime"),
                 p.get("downloadPath"), snap))
            for cat, subs in (p.get("stats") or {}).items():
                if not isinstance(subs, dict):
                    continue
                for sub, vals in subs.items():
                    if not isinstance(vals, dict):
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO stats (code, aoi_name, ptype,"
                        " monitoring_number, version_number, category, subcategory,"
                        " unit, total, affected, total_raw, affected_raw, snapshot_date)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (code, aoi.get("name"), p.get("type"), mon_n, ver_n,
                         cat, sub, vals.get("unit"),
                         to_num(vals.get("total")), to_num(vals.get("affected")),
                         json.dumps(vals.get("total")), json.dumps(vals.get("affected")),
                         snap))


def is_colombia(act: dict) -> bool:
    return any((c.get("name") or "").lower() == "colombia"
               for c in act.get("countries") or [])


def run(backfill: bool = False, watch_codes: list[str] | None = None) -> dict:
    """Modo diario: refresca activaciones Colombia conocidas + sondea códigos nuevos.
    Modo backfill: enumera desde EMSR673."""
    conn = db()
    summary = {"checked": 0, "colombia": [], "new": [], "gaps": []}

    if backfill:
        codes = [f"EMSR{n}" for n in range(BACKFILL_START, 3000)]
    else:
        known = [r[0] for r in conn.execute(
            "SELECT code FROM activation_index WHERE exists_public=1"
            " AND countries LIKE '%Colombia%'")]
        maxn = conn.execute(
            "SELECT MAX(CAST(SUBSTR(code,5) AS INTEGER)) FROM activation_index"
            " WHERE exists_public=1").fetchone()[0] or BACKFILL_START
        probe = [f"EMSR{n}" for n in range(maxn + 1, maxn + 1 + GAP_TOLERANCE)]
        codes = sorted(set(known + (watch_codes or []) + probe),
                       key=lambda c: int(c[4:]))

    consecutive_missing = 0
    for code in codes:
        status, act = fetch_activation(code, conn)
        summary["checked"] += 1
        if status not in (200,):
            # 403 = fuera de retención pública; cuenta como hueco en backfill
            act = None
        known_before = conn.execute(
            "SELECT exists_public FROM activation_index WHERE code=?",
            (code,)).fetchone()
        store_index(conn, code, act)
        if act is None:
            summary["gaps"].append(code)
            consecutive_missing += 1
            if backfill and consecutive_missing >= GAP_TOLERANCE:
                break
        else:
            consecutive_missing = 0
            if known_before is None or not known_before[0]:
                summary["new"].append({"code": code, "name": act.get("name"),
                                       "countries": [c.get("name") for c in
                                                     act.get("countries") or []]})
            if is_colombia(act):
                store_detail(conn, act)
                summary["colombia"].append(code)
        conn.commit()
        time.sleep(PAUSE)
    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    import sys
    print(json.dumps(run(backfill="--backfill" in sys.argv), indent=1))
