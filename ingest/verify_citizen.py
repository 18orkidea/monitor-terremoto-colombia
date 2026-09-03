"""Verificación automática de reportes ciudadanos.

Checks aplicables a ChatMap (WhatsApp elimina EXIF, así que los checks de EXIF
sólo aplican al futuro canal Kobo):
  A. plausibilidad sísmica  — MMI en la rejilla ShakeMap ≥ 5
  B. dentro de un AOI Copernicus (verificación cruzada satélite↔suelo)
  C. temporalidad — timestamp posterior al sismo
  D. duplicados — sha256 exacto del medio
  E. tiene medio adjunto verificable

Score 0-5. Nada se marca 'validado' sin revisión humana: el score sólo ordena
la cola. La coordenada publicada es la que registró la fuente (R5, 24-ago-2026):
el monitor no reposiciona nada.
"""
from __future__ import annotations

import json
from pathlib import Path

from common import INSTANTE_SISMO, db, snapshot_dir
from geo import grid_mmi_vigente, point_in_wkt_polygon

# el instante vive en common.py: el monitor no puede tener dos fechas del
# mismo terremoto (ver FECHA_SISMO)
QUAKE_TS = INSTANTE_SISMO


def _bbox_area(wkt: str) -> float:
    from geo import wkt_to_rings
    rings = wkt_to_rings(wkt or "")
    if not rings:
        return float("inf")
    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def extents_de_aoi_archivados(raiz: Path) -> dict:
    """Extent (WKT) de cada AOI de Copernicus, leído de TODOS los snapshots
    archivados, del más reciente al más antiguo; para un mismo nombre gana
    el más reciente.

    Hasta el 3-sep-2026 se leía solo la carpeta más reciente que tuviera
    algún AOI. El 2-sep Copernicus abrió EMSR928 —una tormenta en
    Lombardía— y el daily la archivó como archiva toda activación nueva: la
    carpeta del día solo tenía AOIs italianos, y el cruce satélite↔suelo
    pasó de 745 reportes ciudadanos dentro de un AOI a cero, dos días
    seguidos, sin que nadie lo dijera (R11). Los AOIs colombianos no
    caducan porque otro desastre abra los suyos: se leen todos."""
    extents = {}
    if not raiz.is_dir():
        return extents
    for d in sorted(raiz.iterdir(), reverse=True):
        for f in sorted(d.glob("copernicus_*.json")):
            try:
                data = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for r in data.get("results", []):
                for aoi in r.get("aois") or []:
                    if aoi.get("name") and aoi.get("extent"):
                        extents.setdefault(aoi["name"], aoi["extent"])
    return extents


def run() -> dict:
    conn = db()
    grid = grid_mmi_vigente(snapshot_dir())

    # extent por AOI: la activación guarda un extent global; los AOI extents
    # están en los snapshots crudos de Copernicus
    aoi_extents = extents_de_aoi_archivados(snapshot_dir().parent)

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
