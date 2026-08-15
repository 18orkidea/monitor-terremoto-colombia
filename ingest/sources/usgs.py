"""USGS FDSN: evento, ShakeMap (rejilla MMI), PAGER y DYFI agregado."""
from __future__ import annotations

import json

from common import db, fetch_json, PUBLIC

EVENT_ID = "us6000tjl2"
DETAIL = f"https://earthquake.usgs.gov/fdsnws/event/1/query?eventid={EVENT_ID}&format=geojson"


def run() -> dict:
    conn = db()
    out = {}
    status, ev = fetch_json(DETAIL, note="usgs detail",
                            snapshot_name=f"usgs_{EVENT_ID}.json", conn=conn)
    if not ev:
        conn.commit(); conn.close()
        return {"error": f"usgs detail HTTP {status}"}

    props = ev.get("properties", {})
    prods = props.get("products", {})
    out["event"] = {
        "id": EVENT_ID,
        "mag": props.get("mag"), "place": props.get("place"),
        "time_ms": props.get("time"), "alert": props.get("alert"),
        "felt": props.get("felt"), "cdi": props.get("cdi"), "mmi": props.get("mmi"),
        "coordinates": ev.get("geometry", {}).get("coordinates"),
        "url": props.get("url"),
    }

    sm = (prods.get("shakemap") or [{}])[0]
    contents = sm.get("contents", {})

    def grab(name, snapshot):
        c = contents.get(name)
        if not c:
            return None
        st, data = fetch_json(c["url"], note=f"usgs {name}",
                              snapshot_name=snapshot, conn=conn)
        return data

    # Rejilla MMI para verify_citizen + contornos para el mapa
    cov = grab("download/coverage_mmi_low_res.covjson", "usgs_mmi_grid.covjson")
    cont = grab("download/cont_mmi.json", "usgs_mmi_contours.json")
    if cont:
        (PUBLIC / "shakemap_mmi.geojson").write_text(json.dumps(cont))
    out["shakemap"] = {"maxmmi": sm.get("properties", {}).get("maxmmi"),
                      "grid": bool(cov), "contours": bool(cont)}

    pager = (prods.get("losspager") or [{}])[0]
    lp = pager.get("properties", {})
    out["pager"] = {"alertlevel": lp.get("alertlevel"), "maxmmi": lp.get("maxmmi")}
    # Exposición poblacional por banda MMI: la base de la métrica de
    # "población expuesta sin mapeo satelital" (asentamientos que nadie mira).
    exp_c = pager.get("contents", {}).get("json/exposures.json")
    if exp_c:
        st, exp = fetch_json(exp_c["url"], note="usgs pager exposures",
                             snapshot_name="usgs_pager_exposures.json", conn=conn)
        if exp:
            out["pager"]["exposure"] = exp.get("population_exposure") or exp

    dyfi = (prods.get("dyfi") or [{}])[0]
    dyfi_contents = dyfi.get("contents", {})
    cell = dyfi_contents.get("dyfi_geo_10km.geojson")
    if cell:
        st, cells = fetch_json(cell["url"], note="usgs dyfi 10km",
                               snapshot_name="usgs_dyfi_10km.geojson", conn=conn)
        if cells:
            (PUBLIC / "dyfi_cells.geojson").write_text(json.dumps(cells))
            out["dyfi"] = {"nresponses": dyfi.get("properties", {}).get("numResp"),
                           "cells": len(cells.get("features", []))}
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
