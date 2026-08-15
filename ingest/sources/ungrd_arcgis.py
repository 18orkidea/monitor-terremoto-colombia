"""UNGRD ArcGIS FeatureServer: línea base histórica EDAN (1914 → 2024-02).

85.664 registros paginados de 2.000 en 2.000 (maxRecordCount del servicio).
Es la fuente oficial más completa disponible — y su fecha máxima ES la brecha.
"""
from __future__ import annotations

import json

from common import db, fetch_json

LAYER = ("https://services2.arcgis.com/YVLx8xYoDXKccDfJ/arcgis/rest/services/"
         "REGISTRO_DE_EMERGENCIAS_EN_COLOMBIA/FeatureServer/0/query")
FIELDS = ["OBJECTID_1", "FECHA", "DEPARTAMEN", "MUNICIPIO", "DIVIPOLA", "EVENTO",
          "MUERTOS", "HERIDOS", "DESAPA_", "PERSONAS", "FAMILIAS",
          "VIV_DESTRU", "VIV_AVER_", "VIAS", "ACUED_", "C__SALUD", "C_EDUCAT_",
          "XCOORD", "YCOORD"]
PAGE = 2000


def _ts_to_date(ms):
    if not isinstance(ms, (int, float)):
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def run(full: bool = False) -> dict:
    """full=True descarga todo (backfill). En diario basta comprobar max(FECHA):
    si no cambió (lleva parado desde feb-2024), no hay nada nuevo que traer."""
    conn = db()
    st, agg = fetch_json(LAYER, {
        "where": "1=1", "f": "json",
        "outStatistics": json.dumps([
            {"statisticType": "max", "onStatisticField": "FECHA",
             "outStatisticFieldName": "maxf"},
            {"statisticType": "count", "onStatisticField": "OBJECTID_1",
             "outStatisticFieldName": "n"}]),
    }, note="ungrd arcgis agregados", snapshot_name="ungrd_arcgis_agg.json", conn=conn)
    out = {}
    if agg and agg.get("features"):
        a = agg["features"][0]["attributes"]
        out = {"max_fecha": _ts_to_date(a.get("maxf")), "total": a.get("n")}

    have = conn.execute(
        "SELECT COUNT(*) FROM official_events WHERE source='ungrd_arcgis'").fetchone()[0]
    if full and have < (out.get("total") or 0):
        offset, stored = 0, 0
        while True:
            st, page = fetch_json(LAYER, {
                "where": "1=1", "f": "json", "outFields": ",".join(FIELDS),
                "resultOffset": offset, "resultRecordCount": PAGE,
                "orderByFields": "OBJECTID_1",
            }, note=f"ungrd arcgis offset={offset}", conn=conn)
            feats = (page or {}).get("features") or []
            if not feats:
                break
            for f in feats:
                at = f.get("attributes", {})
                conn.execute(
                    "INSERT OR REPLACE INTO official_events (source, external_id,"
                    " fecha, departamento, municipio, divipola, evento, muertos,"
                    " heridos, desaparecidos, personas, familias, viv_destruidas,"
                    " viv_averiadas, vias, acueductos, centros_salud,"
                    " centros_educativos, lat, lon)"
                    " VALUES ('ungrd_arcgis',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(at.get("OBJECTID_1")), _ts_to_date(at.get("FECHA")),
                     at.get("DEPARTAMEN"), at.get("MUNICIPIO"), at.get("DIVIPOLA"),
                     at.get("EVENTO"), at.get("MUERTOS"), at.get("HERIDOS"),
                     at.get("DESAPA_"), at.get("PERSONAS"), at.get("FAMILIAS"),
                     at.get("VIV_DESTRU"), at.get("VIV_AVER_"), at.get("VIAS"),
                     at.get("ACUED_"), at.get("C__SALUD"), at.get("C_EDUCAT_"),
                     at.get("YCOORD"), at.get("XCOORD")))
            stored += len(feats)
            offset += PAGE
            conn.commit()
            if len(feats) < PAGE:
                break
        out["descargados"] = stored
    out["en_bd"] = conn.execute(
        "SELECT COUNT(*) FROM official_events WHERE source='ungrd_arcgis'").fetchone()[0]
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(run(full="--full" in sys.argv), indent=1))
