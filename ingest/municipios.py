"""Municipios dentro del área de influencia del sismo.

No son AOIs Copernicus. Esta capa existe para no perder ciudades mencionadas
por prensa o con intensidad percibida, aunque no hayan sido mapeadas por satélite.
"""
from __future__ import annotations

import re
import unicodedata

from geo import point_in_wkt_polygon


MUNICIPIOS = {
    "Armenia": {"departamento": "Quindío", "lat": 4.5339, "lon": -75.6811,
                "toponimos": ["armenia"]},
    "Calarcá": {"departamento": "Quindío", "lat": 4.5295, "lon": -75.6409,
                "toponimos": ["calarca"]},
    "La Tebaida": {"departamento": "Quindío", "lat": 4.4524, "lon": -75.7875,
                   "toponimos": ["la tebaida"]},
    "Montenegro": {"departamento": "Quindío", "lat": 4.5669, "lon": -75.7511,
                   "toponimos": ["montenegro"]},
    "Salento": {"departamento": "Quindío", "lat": 4.6375, "lon": -75.5703,
                "toponimos": ["salento"]},
    "Zarzal": {"departamento": "Valle del Cauca", "lat": 4.3946, "lon": -76.0715,
               "toponimos": ["zarzal"]},
    "Cartago": {"departamento": "Valle del Cauca", "lat": 4.7464, "lon": -75.9117,
                "toponimos": ["cartago"]},
    "Tuluá": {"departamento": "Valle del Cauca", "lat": 4.0847, "lon": -76.1954,
              "toponimos": ["tulua"]},
    "Buga": {"departamento": "Valle del Cauca", "lat": 3.9009, "lon": -76.2978,
             "toponimos": ["buga", "guadalajara de buga"]},
    "Palmira": {"departamento": "Valle del Cauca", "lat": 3.5394, "lon": -76.3036,
                "toponimos": ["palmira"]},
    "Roldanillo": {"departamento": "Valle del Cauca", "lat": 4.4126, "lon": -76.1546,
                   "toponimos": ["roldanillo"]},
    "Sevilla": {"departamento": "Valle del Cauca", "lat": 4.2643, "lon": -75.9309,
                "toponimos": ["sevilla"]},
    "Caicedonia": {"departamento": "Valle del Cauca", "lat": 4.3324, "lon": -75.8267,
                   "toponimos": ["caicedonia"]},
    "Jamundí": {"departamento": "Valle del Cauca", "lat": 3.2607, "lon": -76.5349,
                "toponimos": ["jamundi"]},
    "Dagua": {"departamento": "Valle del Cauca", "lat": 3.6569, "lon": -76.6886,
              "toponimos": ["dagua"]},
    "Pereira": {"departamento": "Risaralda", "lat": 4.8143, "lon": -75.6946,
                "toponimos": ["pereira"]},
    "Dosquebradas": {"departamento": "Risaralda", "lat": 4.8347, "lon": -75.6725,
                     "toponimos": ["dos quebradas", "dosquebradas"]},
    "Santa Rosa de Cabal": {"departamento": "Risaralda", "lat": 4.8681, "lon": -75.6214,
                            "toponimos": ["santa rosa de cabal"]},
    "Manizales": {"departamento": "Caldas", "lat": 5.0703, "lon": -75.5138,
                  "toponimos": ["manizales"]},
    "Villamaría": {"departamento": "Caldas", "lat": 5.0449, "lon": -75.5146,
                   "toponimos": ["villamaria"]},
    "Cali": {"departamento": "Valle del Cauca", "lat": 3.4516, "lon": -76.5320,
             "toponimos": ["cali"]},
    "Buenaventura": {"departamento": "Valle del Cauca", "lat": 3.8801, "lon": -77.0312,
                     "toponimos": ["buenaventura"]},
    "Quibdó": {"departamento": "Chocó", "lat": 5.6947, "lon": -76.6611,
               "toponimos": ["quibdo"]},
    "Istmina": {"departamento": "Chocó", "lat": 5.1605, "lon": -76.6830,
                "toponimos": ["istmina"]},
    "San José del Palmar": {"departamento": "Chocó", "lat": 4.9740, "lon": -76.2280,
                            "toponimos": ["san jose del palmar"]},
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _mentioned(text: str, tops: list[str]) -> bool:
    n = _norm(text)
    return any(re.search(rf"\b{re.escape(t)}\b", n) for t in tops)


def match_municipios_text(text: str) -> list[str]:
    return [mun for mun, meta in MUNICIPIOS.items()
            if _mentioned(text, meta["toponimos"])]


def match_departamentos_text(text: str, municipios: list[str] | None = None) -> list[str]:
    found = {MUNICIPIOS[m]["departamento"] for m in (municipios or [])
             if m in MUNICIPIOS}
    n = _norm(text)
    for meta in MUNICIPIOS.values():
        depto = meta["departamento"]
        if re.search(rf"\b{re.escape(_norm(depto))}\b", n):
            found.add(depto)
    return sorted(found)


def _dyfi_municipio(name: str) -> str:
    m = re.search(r"<br>([^<]+)$", name or "")
    return m.group(1).strip() if m else (name or "").strip()


def _pop_key(municipio: str, departamento: str) -> str:
    return f"{_norm(municipio)}|{_norm(departamento)}"


def _find_population(poblacion: dict | None, municipio: str, meta: dict) -> dict | None:
    if not poblacion:
        return None
    departamento = meta["departamento"]
    names = [municipio, *meta.get("toponimos", [])]
    for name in names:
        pop = poblacion.get(_pop_key(name, departamento))
        if pop:
            return pop
    return None


def build_municipios(noticias: list[dict], dyfi: dict | None,
                     aoi_extents: dict[str, str],
                     poblacion: dict | None = None) -> tuple[list[dict], dict]:
    out = {m: {"municipio": m, **meta, "n_noticias": 0,
               "noticias_ejemplo": [], "dyfi_max_cdi": None,
               "dyfi_respuestas": 0, "dyfi_celdas": 0, "dyfi_min_dist_km": None}
           for m, meta in MUNICIPIOS.items()}

    for mun, row in out.items():
        pop = _find_population(poblacion, mun, row)
        if pop:
            row["divipola"] = pop.get("divipola")
            row["poblacion_2026"] = pop.get("poblacion_2026")
            row["cabecera_2026"] = pop.get("cabecera_2026")
            row["rural_2026"] = pop.get("rural_2026")
            row["poblacion_fuente"] = "DANE PPED municipal por área 2018-2042"
        else:
            row["divipola"] = None
            row["poblacion_2026"] = None
            row["cabecera_2026"] = None
            row["rural_2026"] = None
            row["poblacion_fuente"] = None

    for n in noticias:
        text = f"{n.get('titulo') or ''} {n.get('medio') or ''}"
        for mun, meta in MUNICIPIOS.items():
            if _mentioned(text, meta["toponimos"]):
                row = out[mun]
                row["n_noticias"] += 1
                if len(row["noticias_ejemplo"]) < 3:
                    row["noticias_ejemplo"].append({
                        "fecha": n.get("fecha"), "medio": n.get("medio"),
                        "titulo": n.get("titulo"), "url": n.get("url")})

    for f in (dyfi or {}).get("features", []):
        p = f.get("properties") or {}
        raw_mun = _dyfi_municipio(p.get("name"))
        key = _norm(raw_mun)
        mun = next((m for m, meta in MUNICIPIOS.items()
                    if key in meta["toponimos"] or _norm(m) == key), None)
        if not mun:
            continue
        row = out[mun]
        cdi, nresp, dist = p.get("cdi"), p.get("nresp"), p.get("dist")
        if isinstance(cdi, (int, float)):
            row["dyfi_max_cdi"] = max(row["dyfi_max_cdi"] or cdi, cdi)
        if isinstance(nresp, (int, float)):
            row["dyfi_respuestas"] += nresp
        if isinstance(dist, (int, float)):
            row["dyfi_min_dist_km"] = min(row["dyfi_min_dist_km"] or dist, dist)
        row["dyfi_celdas"] += 1

    features, rows = [], []
    for mun, row in out.items():
        tiene_dyfi = row["dyfi_max_cdi"] is not None
        tiene_prensa = row["n_noticias"] > 0
        if not tiene_prensa and not tiene_dyfi:
            continue
        lon, lat = row["lon"], row["lat"]
        en_aoi = any(point_in_wkt_polygon(lon, lat, wkt)
                     for wkt in aoi_extents.values() if wkt)
        estado = "fuera_aoi"
        if en_aoi:
            estado = "en_aoi"
        elif tiene_dyfi and (row["dyfi_max_cdi"] or 0) >= 6:
            estado = "intensidad_alta"
        elif tiene_prensa:
            estado = "mencion_prensa"
        row["en_aoi_copernicus"] = en_aoi
        row["estado"] = estado
        row["fuentes"] = [x for x, ok in (("prensa", tiene_prensa),
                                          ("dyfi", tiene_dyfi)) if ok]
        public_row = {k: v for k, v in row.items() if k != "toponimos"}
        rows.append(public_row)
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": {k: v for k, v in public_row.items()
                                        if k not in ("lat", "lon", "toponimos")}})

    rows.sort(key=lambda r: (not r["en_aoi_copernicus"],
                             -(r["dyfi_max_cdi"] or 0),
                             -r["n_noticias"], r["municipio"]))
    return rows, {"type": "FeatureCollection", "features": features}
