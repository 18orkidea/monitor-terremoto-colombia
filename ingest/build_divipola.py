"""Construye el catálogo estático de coordenadas municipales (DIVIPOLA).

Referencia geográfica, no serie temporal: la división político-administrativa
cambia cada varios años, no cada día — por eso NO va en la corrida diaria. Se
ejecuta a mano cuando el test `test_todo_municipio_rud_resuelve_coordenadas`
avisa de un municipio sin coordenadas (o cuando el DANE publique una
actualización), y su salida se commitea.

Existe para que ningún municipio que entre al RUD se pierda del mapa por falta
de mantenimiento manual de la lista curada de `municipios.py`.

Uso: python ingest/build_divipola.py
"""
from __future__ import annotations

import json

from common import PUBLIC, db, fetch_json, today

# Socrata pagina de 1.000 en 1.000 por defecto: el $limit explícito es parte
# de la petición reproducible, no un detalle de implementación.
URL = "https://www.datos.gov.co/resource/gdxc-w37w.json"
PARAMS = {"$limit": 5000}
DEST = PUBLIC / "divipola_coords.json"


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _coord(v: str | None) -> float | None:
    """El dataset publica coordenadas con coma decimal ('-75,581775')."""
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def run() -> dict:
    conn = db()
    status, data = fetch_json(URL, params=PARAMS, note="divipola municipios",
                              snapshot_name="divipola_gdxc_w37w.json", conn=conn)
    conn.commit()
    conn.close()
    if not data:
        return {"error": f"DIVIPOLA HTTP {status}: no se reescribe el catálogo"}

    items, sin_coords = {}, []
    for r in data:
        mun, dep = r.get("nom_mpio"), r.get("dpto")
        lat, lon = _coord(r.get("latitud")), _coord(r.get("longitud"))
        if not mun or not dep:
            continue
        if lat is None or lon is None:
            sin_coords.append(f"{dep}/{mun}")
        items[f"{_norm(mun)}|{_norm(dep)}"] = {
            "municipio": mun, "departamento": dep,
            "divipola": r.get("cod_mpio"), "lat": lat, "lon": lon,
        }

    DEST.write_text(json.dumps({
        "fuente": URL + "?%24limit=5000",
        "dataset": "DIVIPOLA — Códigos de municipios geolocalizados (DANE, "
                   "publicado en datos.gov.co como gdxc-w37w)",
        "capturado": today(),
        "generado_por": "ingest/build_divipola.py",
        "descripcion": "Centroide (lat/lon) y código DIVIPOLA de cada municipio "
                       "de Colombia, indexado por 'municipio|departamento' sin "
                       "tildes. Referencia estática: permite que un municipio "
                       "que entre al RUD sin entrada curada en municipios.py "
                       "resuelva coordenadas y no se pierda del mapa. El cuerpo "
                       "crudo de la petición queda en data/snapshots/ con su "
                       "sha256 en sources_log.",
        "items": items,
    }, ensure_ascii=False))
    return {"municipios": len(items), "sin_coordenadas": sin_coords}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
