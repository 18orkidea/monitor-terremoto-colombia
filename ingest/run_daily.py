"""Orquestador diario: descargar → snapshot → normalizar → cruzar → publicar.

Uso:
  python run_daily.py               # corrida diaria
  python run_daily.py --backfill    # primera vez: enumeración completa + histórico
"""
from __future__ import annotations

import json
import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

RESULTS = {}


def step(name, fn, *a, **kw):
    print(f"── {name}…", flush=True)
    try:
        RESULTS[name] = fn(*a, **kw)
        print(json.dumps(RESULTS[name], ensure_ascii=False)[:300])
    except Exception:
        RESULTS[name] = {"error": traceback.format_exc(limit=3)}
        print(RESULTS[name]["error"])


def main():
    backfill = "--backfill" in sys.argv
    from sources import copernicus, copernicus_layers, usgs, gdacs, gdelt, \
        ungrd_arcgis, ungrd_socrata, ungrd_rud, chatmap, emsc, community_feeds, \
        unosat
    import dump_db, verify_citizen, crosscheck, alerts, publish

    # el sqlite no se versiona: en un clon nuevo (o en CI) se reconstruye
    # desde los dumps CSV antes de empezar
    step("rebuild_db", dump_db.rebuild)

    step("copernicus", copernicus.run, backfill=backfill)
    step("copernicus_layers", copernicus_layers.run)
    step("unosat", unosat.run)
    step("usgs", usgs.run)
    step("gdacs", gdacs.run)
    step("gdelt", gdelt.run)
    step("ungrd_arcgis", ungrd_arcgis.run, full=backfill)
    step("ungrd_socrata", ungrd_socrata.run)
    step("ungrd_rud", ungrd_rud.run)
    step("chatmap", chatmap.run)
    step("emsc", emsc.run)
    step("community_feeds", community_feeds.run)
    step("verify_citizen", verify_citizen.run)
    step("crosscheck", crosscheck.run)
    step("alerts", alerts.run, RESULTS.get("copernicus") or {})
    step("publish", publish.run)
    # al cerrar: volcar la BD a dumps CSV — lo que git versiona y diffea
    step("dump_db", dump_db.dump)

    print("\n== RESUMEN ==")
    for k, v in RESULTS.items():
        ok = "ERROR" if isinstance(v, dict) and "error" in v else "ok"
        print(f"  {k}: {ok}")
    errs = [k for k, v in RESULTS.items() if isinstance(v, dict) and "error" in v]
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
