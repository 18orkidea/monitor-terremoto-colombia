"""Geometría mínima sin dependencias: WKT → GeoJSON, punto-en-polígono, MMI."""
from __future__ import annotations

import re


def wkt_to_rings(wkt: str) -> list[list[list[float]]]:
    """POLYGON ((x y, x y, ...)) o POINT (x y) → anillos [[x,y],...]."""
    if not wkt:
        return []
    nums = re.findall(r"\(([^()]+)\)", wkt)
    rings = []
    for grp in nums:
        pts = []
        for pair in grp.split(","):
            xy = pair.split()
            if len(xy) >= 2:
                pts.append([float(xy[0]), float(xy[1])])
        if pts:
            rings.append(pts)
    return rings


def wkt_to_geojson(wkt: str) -> dict | None:
    if not wkt:
        return None
    w = wkt.strip().upper()
    rings = wkt_to_rings(wkt)
    if not rings:
        return None
    if w.startswith("POINT"):
        return {"type": "Point", "coordinates": rings[0][0]}
    if w.startswith("POLYGON"):
        return {"type": "Polygon", "coordinates": rings}
    return None


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_wkt_polygon(lon: float, lat: float, wkt: str) -> bool:
    rings = wkt_to_rings(wkt)
    if not rings:
        return False
    if not point_in_ring(lon, lat, rings[0]):
        return False
    return not any(point_in_ring(lon, lat, hole) for hole in rings[1:])


class MMIGrid:
    """Lookup de intensidad sobre el covjson de ShakeMap (rejilla regular)."""

    def __init__(self, covjson: dict):
        dom = covjson["domain"]["axes"]
        self.x0, self.x1 = dom["x"]["start"], dom["x"]["stop"]
        self.nx = dom["x"]["num"]
        self.y0, self.y1 = dom["y"]["start"], dom["y"]["stop"]
        self.ny = dom["y"]["num"]
        rng = covjson["ranges"]
        key = next(iter(rng))
        self.values = rng[key]["values"]

    def mmi_at(self, lon: float, lat: float):
        fx = (lon - self.x0) / (self.x1 - self.x0) * (self.nx - 1)
        fy = (lat - self.y0) / (self.y1 - self.y0) * (self.ny - 1)
        ix, iy = round(fx), round(fy)
        if not (0 <= ix < self.nx and 0 <= iy < self.ny):
            return None
        # covjson recorre y como primer eje
        return self.values[iy * self.nx + ix]


def grid_mmi_vigente(snapshot_hoy=None):
    """El ShakeMap más reciente que exista en el archivo, o None.

    La rejilla del USGS se revisa durante semanas, así que la corrida de hoy
    puede no traerla; se cae al snapshot anterior en vez de quedarse sin dato.
    Vive aquí, y no en cada consumidor, porque ya son dos los que la necesitan:
    la verificación ciudadana y la capa de municipios sin mirada satelital.

    Esa caída hacia atrás NO puede ser silenciosa: un producto fechado hoy
    puede llevar intensidades de una rejilla de hace días, y quien lo lea dentro
    de años tiene que poder saber de cuál (principio de archivo, R4). Por eso el
    grid devuelto expone `origen`: día del snapshot y sha256 del fichero.
    """
    import hashlib
    import json

    from common import snapshot_dir, ultimo_snapshot

    candidatos = []
    if snapshot_hoy is None:
        snapshot_hoy = snapshot_dir()
    if snapshot_hoy is not None:
        candidatos.append(snapshot_hoy)
    # el resto del recorrido lo hace `ultimo_snapshot`: una sola
    # implementación de «el cuerpo vigente, sea de qué día sea» (M2)
    vigente = ultimo_snapshot("usgs_mmi_grid.covjson")
    if vigente is not None:
        candidatos.append(vigente.parent)
    for d in candidatos:
        f = d / "usgs_mmi_grid.covjson"
        if f.exists():
            crudo = f.read_bytes()
            grid = MMIGrid(json.loads(crudo))
            grid.origen = {"snapshot": d.name,
                           "sha256": hashlib.sha256(crudo).hexdigest()}
            return grid
    return None
