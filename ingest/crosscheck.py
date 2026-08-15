"""Cruce Copernicus ↔ oficial ↔ prensa ↔ ciudadano por AOI.

Estados (de menos a más confirmado):
  no_comparable          — producto sin stats (p. ej. GRM en espera)
  pendiente              — Copernicus detecta daño; nadie más lo respalda aún  [DEFECTO]
  ciudadano              — además hay reportes ciudadanos verificados dentro del AOI
  prensa                 — además hay noticias que mencionan el AOI (URL + fecha)
  coincide               — existe evidencia OFICIAL. Nunca se asigna sin ella.

Regla dura: 'coincide' exige una fila evidence tipo='oficial'. Con UNGRD parado
en 2024, ningún AOI de 2026 puede llegar ahí automáticamente.
"""
from __future__ import annotations

import json
import re
import unicodedata

from common import db, today

# topónimo → variantes con límite de palabra (evita 'California' por 'Cali')
AOI_TOPONYMS = {
    "Northern Cali": ["cali"],
    "Cali Center": ["cali"],
    "Pereira": ["pereira"],
    "Quibdo Centre": ["quibdo"],
    "Istmina": ["istmina"],
    "Buenaventura": ["buenaventura"],
    "Western Colombia": ["choco", "san jose del palmar"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def match_news_to_aois(emm_items: list[dict], conn, snap: str) -> dict[str, int]:
    counts = {a: 0 for a in AOI_TOPONYMS}
    conn.execute("DELETE FROM evidence WHERE capturado_por='auto' AND tipo='prensa'"
                 " AND snapshot_date=?", (snap,))
    for it in emm_items:
        text = _norm((it.get("title") or "") + " " + (it.get("description") or ""))
        for aoi, tops in AOI_TOPONYMS.items():
            if any(re.search(rf"\b{re.escape(t)}\b", text) for t in tops):
                counts[aoi] += 1
                if counts[aoi] <= 3:  # guardar sólo ejemplos como evidencia
                    conn.execute(
                        "INSERT INTO evidence (aoi_name, tipo, url, fuente, fecha,"
                        " cita, capturado_por, snapshot_date)"
                        " VALUES (?,?,?,?,?,?,'auto',?)",
                        (aoi, "prensa", it.get("link"), it.get("source"),
                         it.get("pubdate"), (it.get("title") or "")[:200], snap))
    return counts


def run(emm_items: list[dict] | None = None) -> dict:
    conn = db()
    snap = today()
    if emm_items is None:
        from sources.gdacs import emm_items as _load
        emm_items = _load()
    press = match_news_to_aois(emm_items or [], conn, snap)

    aois = [r[0] for r in conn.execute(
        "SELECT DISTINCT aoi_name FROM products WHERE code='EMSR916'")]
    out = {}
    for aoi in aois:
        has_stats = conn.execute(
            "SELECT COUNT(*) FROM stats WHERE code='EMSR916' AND aoi_name=?"
            " AND affected IS NOT NULL", (aoi,)).fetchone()[0] > 0
        n_of = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE aoi_name=? AND tipo='oficial'",
            (aoi,)).fetchone()[0]
        n_pr = press.get(aoi, 0)
        n_ci = conn.execute(
            "SELECT COUNT(*) FROM citizen_reports WHERE estado IN"
            " ('coherente','validado','publicado')"
            " AND json_extract(checks,'$.aoi')=?", (aoi,)).fetchone()[0]
        if n_of > 0:
            estado = "coincide"
        elif not has_stats:
            estado = "no_comparable"
        elif n_pr > 0:
            estado = "prensa"
        elif n_ci > 0:
            estado = "ciudadano"
        else:
            estado = "pendiente"
        detalle = {"noticias": n_pr, "ciudadanos_en_aoi": n_ci,
                   "evidencia_oficial": n_of, "stats": has_stats}
        conn.execute(
            "INSERT OR REPLACE INTO crosscheck (aoi_name, snapshot_date, estado,"
            " copernicus, n_prensa, n_oficial, n_ciudadano, detalle)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (aoi, snap, estado, 1 if has_stats else 0, n_pr, n_of, n_ci,
             json.dumps(detalle, ensure_ascii=False)))
        out[aoi] = estado
    conn.commit()
    conn.close()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
