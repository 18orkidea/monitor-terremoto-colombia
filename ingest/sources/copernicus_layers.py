"""Capas vectoriales de daño de Copernicus (el detalle que las stats resumen).

Por cada AOI, del producto más reciente:
  builtUpP             → puntos de edificios con damage_gra (Destroyed/Damaged/…)
  ancillaryCrisisInfoP → puntos de interrupciones / info de crisis
  transportationL      → tramos de vía afectados
  notAnalysedA         → zonas SIN analizar (la brecha de cobertura, literal)

Salida: data/public/damage_points.geojson, damage_lines.geojson,
not_analysed.geojson — cada feature lleva `aoi` y `layer` para mapa y tabla.
"""
from __future__ import annotations

import json
from collections import Counter

from common import db, fetch_json, SNAPSHOTS, PUBLIC
from satelites import AOI_MUNICIPIO

CODE = "EMSR916"
LAYER_KINDS = {
    "builtUpP": "points",
    "ancillaryCrisisInfoP": "points",
    "transportationL": "lines",
    "notAnalysedA": "areas",
}


def _latest_snapshot_activation():
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / f"copernicus_{CODE}.json"
        if f.exists():
            data = json.loads(f.read_text())
            if data.get("results"):
                return data["results"][0]
    return None


def _best_product(aoi: dict):
    prods = [p for p in aoi.get("products") or [] if p.get("layers")]
    if not prods:
        return None
    return max(prods, key=lambda p: (p.get("monitoringNumber") or 0,
                                     (p.get("version") or {}).get("number") or 0))


def run() -> dict:
    act = _latest_snapshot_activation()
    if not act:
        return {"error": "sin snapshot de la activación"}
    conn = db()
    out = {"capas": 0, "features": {}}
    buckets = {"points": [], "lines": [], "areas": []}

    for aoi in act.get("aois") or []:
        p = _best_product(aoi)
        if not p:
            continue
        for layer in p.get("layers") or []:
            name = layer.get("name", "")
            jurl = layer.get("json")
            kind = next((k for key, k in LAYER_KINDS.items() if key in name), None)
            if not jurl or not kind:
                continue
            fname = name.split("/")[-1].replace("_VT", "") + ".json"
            st, gj = fetch_json(jurl, note=f"capa {fname}",
                                snapshot_name=f"layer_{fname}", conn=conn)
            if not gj:
                continue
            out["capas"] += 1
            layer_key = next(key for key in LAYER_KINDS if key in name)
            for f in gj.get("features") or []:
                f.setdefault("properties", {})
                # la red de transporte viene completa: quedarnos solo con lo
                # afectado (el resto son 10k tramos "No visible damage")
                if layer_key == "transportationL" and \
                        f["properties"].get("damage_gra") in (
                            "No visible damage", "Not Analysed", None):
                    continue
                f["properties"]["aoi"] = aoi.get("name")
                f["properties"]["layer"] = layer_key
                # El municipio lo dice el AOI, no la geometría. Sin esto, cada
                # superficie tenía que adivinarlo por proximidad a la cabecera
                # y tres puntos del AOI «Northern Cali» acababan atribuidos a
                # Yumbo, que Copernicus no ha cartografiado. Viaja en el dato
                # publicado para que el mapa, la tabla y las fichas respondan
                # todos lo mismo.
                muni = AOI_MUNICIPIO.get(aoi.get("name") or "")
                if muni:
                    f["properties"]["municipio"] = muni
                buckets[kind].append(f)

    PUBLIC.mkdir(parents=True, exist_ok=True)
    for kind, fname in (("points", "damage_points.geojson"),
                        ("lines", "damage_lines.geojson"),
                        ("areas", "not_analysed.geojson")):
        (PUBLIC / fname).write_text(json.dumps(
            {"type": "FeatureCollection",
             "features": [_con_precision_de_metro(f) for f in buckets[kind]]},
            ensure_ascii=False))
        out["features"][kind] = len(buckets[kind])
    conn.commit()
    conn.close()
    return out


# Copernicus entrega las coordenadas con ocho decimales, que son milímetros.
# Un hueco de cobertura satelital de kilómetros de lado no se dibuja con
# precisión de milímetro: 143.438 de las 159.510 coordenadas de
# `not_analysed.geojson` la traían, y eso engorda el fichero un 29 % sin mover
# un píxel en pantalla. Cinco decimales son ~1,1 m en el ecuador, más fino que
# el píxel del producto del que salen estos trazados.
#
# Esto toca LO QUE PUBLICAMOS NOSOTROS, no lo que dijo la fuente: el snapshot
# de Copernicus sigue intacto con sus ocho decimales y su sha256, y es el que
# demuestra qué entregó. Aquí se corrige nuestra derivación, que es la capa
# que el contrato del proyecto sí permite arreglar.
DECIMALES_PUBLICADOS = 5


def _con_precision_de_metro(feature: dict) -> dict:
    """El mismo feature con las coordenadas redondeadas a `DECIMALES_PUBLICADOS`.

    Recorre la geometría sea cual sea su anidamiento (Point, LineString,
    Polygon, MultiPolygon…) sin tener que conocer su tipo: lo que no es una
    pareja de números se deja como está.
    """
    def recorta(x):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return round(x, DECIMALES_PUBLICADOS)
        if isinstance(x, list):
            return [recorta(v) for v in x]
        return x

    geom = feature.get("geometry")
    if not isinstance(geom, dict) or "coordinates" not in geom:
        return feature
    return {**feature,
            "geometry": {**geom, "coordinates": recorta(geom["coordinates"])}}


def counts_by_aoi() -> dict:
    """Conteos por AOI y grado, para la tabla: {aoi: {grado|categoria: n}}."""
    res: dict = {}
    p = PUBLIC / "damage_points.geojson"
    if p.exists():
        for f in json.loads(p.read_text())["features"]:
            pr = f["properties"]
            aoi = pr.get("aoi")
            if pr.get("layer") == "builtUpP":
                key = pr.get("damage_gra") or "Sin grado"
            else:
                key = "Interrupciones/crisis"
            res.setdefault(aoi, Counter())[key] += 1
    l = PUBLIC / "damage_lines.geojson"
    if l.exists():
        for f in json.loads(l.read_text())["features"]:
            pr = f["properties"]
            res.setdefault(pr.get("aoi"), Counter())["Vías dañadas"] += 1
    return {a: dict(c) for a, c in res.items()}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
    print(json.dumps(counts_by_aoi(), indent=1, ensure_ascii=False))
