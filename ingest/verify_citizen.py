"""Verificación automática de reportes ciudadanos.

Checks aplicables a ChatMap (WhatsApp elimina EXIF, así que los checks de EXIF
sólo aplican al futuro canal Kobo):
  A. plausibilidad sísmica  — MMI en la rejilla ShakeMap ≥ 5
  B. dentro de un AOI Copernicus (verificación cruzada satélite↔suelo)
  C. temporalidad — timestamp posterior al sismo
  D. duplicados — sha256 exacto del medio
  E. tiene medio adjunto verificable

Score 0-5. Nada se marca 'validado' sin revisión humana: el score sólo ordena
la cola. La coordenada publicada siempre es la redondeada.
"""
from __future__ import annotations

import json

from common import db, snapshot_dir
from geo import MMIGrid, point_in_wkt_polygon

QUAKE_TS = "2026-08-10T12:30:00"


def _bbox_area(wkt: str) -> float:
    from geo import wkt_to_rings
    rings = wkt_to_rings(wkt or "")
    if not rings:
        return float("inf")
    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def run() -> dict:
    conn = db()
    grid = None
    p = snapshot_dir() / "usgs_mmi_grid.covjson"
    if not p.exists():
        # buscar en snapshots anteriores
        from common import SNAPSHOTS
        for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
            if (d / "usgs_mmi_grid.covjson").exists():
                p = d / "usgs_mmi_grid.covjson"
                break
    if p.exists():
        grid = MMIGrid(json.loads(p.read_text()))

    # extent por AOI: la activación guarda un extent global; los AOI extents
    # están en los snapshots crudos de Copernicus
    aoi_extents = {}
    for d in sorted((snapshot_dir().parent).iterdir(), reverse=True):
        for f in d.glob("copernicus_*.json"):
            data = json.loads(f.read_text())
            for r in data.get("results", []):
                for aoi in r.get("aois") or []:
                    aoi_extents.setdefault(aoi.get("name"), aoi.get("extent"))
        if aoi_extents:
            break

    seen_hashes = {}
    rows = conn.execute(
        "SELECT origen, id_externo, ts, lat, lon, media_sha256 FROM citizen_reports"
    ).fetchall()
    out = {"total": len(rows), "en_aoi": 0, "duplicados": 0}
    for origen, rid, ts, lat, lon, sha in rows:
        checks, score = {}, 0
        if lat is not None and lon is not None and grid:
            mmi = grid.mmi_at(lon, lat)
            checks["mmi"] = mmi
            if mmi is not None and mmi >= 5:
                score += 1
        aoi_hit = None
        if lat is not None and lon is not None:
            # el más específico gana: probar AOIs de menor a mayor área
            for name, wkt in sorted(aoi_extents.items(),
                                    key=lambda kv: _bbox_area(kv[1])):
                if wkt and point_in_wkt_polygon(lon, lat, wkt):
                    aoi_hit = name
                    break
        checks["aoi"] = aoi_hit
        if aoi_hit:
            score += 1
            out["en_aoi"] += 1
        if ts and ts >= QUAKE_TS:
            checks["posterior_al_sismo"] = True
            score += 1
        if sha:
            score += 1
            if sha in seen_hashes:
                checks["duplicado_de"] = seen_hashes[sha]
                out["duplicados"] += 1
                score -= 1
            else:
                seen_hashes[sha] = rid
                score += 1  # medio único adjunto
        estado = "coherente" if score >= 3 else "recibido"
        conn.execute(
            "UPDATE citizen_reports SET score=?, checks=?, estado="
            " CASE WHEN estado IN ('validado','publicado') THEN estado ELSE ? END"
            " WHERE origen=? AND id_externo=?",
            (score, json.dumps(checks, ensure_ascii=False), estado, origen, rid))
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
