"""Genera data/public/*: los artefactos que consume el mapa y las exportaciones.

Privacidad: de citizen_reports sólo salen lat_pub/lon_pub (redondeadas) y la
URL del medio; jamás la coordenada exacta.
"""
from __future__ import annotations

import csv
import io
import json

from common import db, today, utcnow, DATA, PUBLIC, snapshot_dir
from geo import wkt_to_geojson

ESTADO_LABEL = {
    "coincide": "Coincide cualitativamente",
    "prensa": "Reportado en prensa, sin validación oficial",
    "ciudadano": "Reportado por ciudadanos, sin eco oficial ni satelital validado",
    "pendiente": "Pendiente de validar",
    "no_comparable": "No comparable 1:1",
}


def latest_products(conn, code="EMSR916"):
    """Producto más reciente por AOI (mayor monitoring_number, luego versión)."""
    snap = conn.execute(
        "SELECT MAX(snapshot_date) FROM products WHERE code=?", (code,)).fetchone()[0]
    rows = conn.execute(
        "SELECT aoi_name, aoi_number, ptype, monitoring_number, version_number,"
        " status_code, feasible, expected_delivery, delivery_time, download_path"
        " FROM products WHERE code=? AND snapshot_date=?"
        " ORDER BY aoi_number, monitoring_number DESC, version_number DESC",
        (code, snap)).fetchall()
    best, all_products = {}, {}
    for r in rows:
        aoi = r[0]
        all_products.setdefault(aoi, []).append(r)
        if aoi not in best:
            best[aoi] = r
    return snap, best, all_products


def aoi_stats(conn, code, aoi, ptype, mon_n, ver_n, snap):
    rows = conn.execute(
        "SELECT category, subcategory, unit, total, affected, total_raw, affected_raw"
        " FROM stats WHERE code=? AND aoi_name=? AND ptype=? AND monitoring_number=?"
        " AND version_number=? AND snapshot_date=?",
        (code, aoi, ptype, mon_n, ver_n, snap)).fetchall()
    out = {}
    for cat, sub, unit, total, aff, traw, araw in rows:
        out.setdefault(cat, {})[sub] = {
            "unit": unit, "total": total, "affected": aff,
            "total_raw": json.loads(traw) if traw else None,
            "affected_raw": json.loads(araw) if araw else None}
    return out


def resumen_aoi(stats: dict) -> dict:
    """Cifras clave al estilo del análisis original."""
    pob = None
    edif = vias = interrupciones = 0.0
    has_edif = has_vias = has_int = False
    for cat, subs in stats.items():
        for sub, v in subs.items():
            if cat == "Estimated population" and v.get("total") is not None:
                pob = v["total"]
            elif cat == "Built-up" and v.get("affected") is not None:
                edif += v["affected"]; has_edif = True
            elif cat == "Transportation" and v.get("affected") is not None:
                vias += v["affected"]; has_vias = True
            elif cat == "Blocked road / interruption" and v.get("affected") is not None:
                interrupciones += v["affected"]; has_int = True
    return {"poblacion": pob,
            "edificios_afectados": edif if has_edif else None,
            "vias_afectadas_km": round(vias, 2) if has_vias else None,
            "interrupciones_viales": interrupciones if has_int else None}


def aoi_extents_from_snapshots(code="EMSR916") -> dict:
    from common import SNAPSHOTS
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / f"copernicus_{code}.json"
        if f.exists():
            data = json.loads(f.read_text())
            for r in data.get("results", []):
                return {a.get("name"): a.get("extent") for a in r.get("aois") or []}
    return {}


def run() -> dict:
    conn = db()
    snap = today()
    PUBLIC.mkdir(parents=True, exist_ok=True)

    snap_prod, best, all_prods = latest_products(conn)
    extents = aoi_extents_from_snapshots()
    cross = {r[0]: {"estado": r[1], "n_prensa": r[2], "n_oficial": r[3],
                    "n_ciudadano": r[4]}
             for r in conn.execute(
                 "SELECT aoi_name, estado, n_prensa, n_oficial, n_ciudadano"
                 " FROM crosscheck WHERE snapshot_date="
                 " (SELECT MAX(snapshot_date) FROM crosscheck)")}

    from sources.copernicus_layers import counts_by_aoi
    detecciones = counts_by_aoi()

    # titulares de prensa guardados como evidencia (hasta 3 por AOI)
    prensa_por_aoi: dict = {}
    for r in conn.execute(
            "SELECT aoi_name, cita, fuente, fecha, url FROM evidence"
            " WHERE tipo='prensa' AND snapshot_date="
            " (SELECT MAX(snapshot_date) FROM evidence WHERE tipo='prensa')"
            " ORDER BY fecha"):
        prensa_por_aoi.setdefault(r[0], []).append(
            {"titular": r[1], "medio": r[2], "fecha": r[3], "url": r[4]})

    aois, features = [], []
    for aoi, r in best.items():
        _, aoi_num, ptype, mon_n, ver_n, status, feas, exp, deliv, dl = r
        stats = aoi_stats(conn, "EMSR916", aoi, ptype, mon_n, ver_n, snap_prod)
        cc = cross.get(aoi, {"estado": "pendiente"})
        entry = {
            "aoi": aoi, "numero": aoi_num,
            "producto": {"tipo": ptype, "monitoreo": mon_n, "version": ver_n,
                         "status": status, "entrega": deliv, "descarga": dl},
            "resumen": resumen_aoi(stats), "stats": stats,
            "detecciones": detecciones.get(aoi) or {},
            "prensa_ejemplos": prensa_por_aoi.get(aoi) or [],
            "cruce": {**cc, "etiqueta": ESTADO_LABEL.get(cc["estado"], cc["estado"])},
            "n_productos": len(all_prods.get(aoi, [])),
        }
        aois.append(entry)
        gj = wkt_to_geojson(extents.get(aoi) or "")
        if gj:
            features.append({"type": "Feature", "geometry": gj,
                             "properties": {"aoi": aoi, "estado": cc["estado"],
                                            "etiqueta": entry["cruce"]["etiqueta"],
                                            **entry["resumen"]}})
    (PUBLIC / "aois.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}, ensure_ascii=False))

    # serie de los feeds abiertos del monitor (por fecha de publicación del
    # titular; >= 2026-08-08 para excluir artículos históricos que el filtro
    # de palabras clave atrapa en los RSS)
    feeds_por_dia = dict(conn.execute(
        "SELECT substr(fecha,1,10) d, COUNT(*) FROM news_items"
        " WHERE fecha >= '2026-08-08' GROUP BY d"))

    media = [dict(zip(["fecha", "emm", "gdelt", "fuentes", "chatmap"], r))
             for r in conn.execute(
                 "SELECT fecha, MAX(n_noticias_emm), MAX(gdelt_vol), MAX(n_fuentes),"
                 " MAX(n_chatmap) FROM media_volume WHERE event_key='EQ1557236'"
                 " GROUP BY fecha ORDER BY fecha")]
    vistos = {m["fecha"] for m in media}
    for d in sorted(set(feeds_por_dia) - vistos):   # días solo presentes en feeds
        media.append({"fecha": d, "emm": None, "gdelt": None,
                      "fuentes": None, "chatmap": None})
    media.sort(key=lambda m: m["fecha"])
    for m in media:
        m["feeds"] = feeds_por_dia.get(m["fecha"])
    entregas = [{"aoi": r[0], "fecha": (r[1] or "")[:10], "producto": r[2],
                 "version": r[3]}
                for r in conn.execute(
                    "SELECT aoi_name, delivery_time, ptype, version_number"
                    " FROM products WHERE code='EMSR916' AND delivery_time IS NOT NULL"
                    " AND snapshot_date=?", (snap_prod,))]

    cit_feats = []
    for r in conn.execute(
            "SELECT id_externo, ts, lat_pub, lon_pub, media_url, media_local,"
            " media_sha256, score, checks, estado, mensaje FROM citizen_reports"
            " WHERE lat_pub IS NOT NULL"):
        rid, ts, lat, lon, murl, mlocal, msha, score, checks, estado, msg = r
        # verificación de lo publicado: el fichero local debe coincidir con el
        # sha256 registrado en la BD; discrepancia = warning, nunca rotura
        if mlocal and msha:
            import hashlib
            from common import ROOT as _ROOT
            f_local = _ROOT / mlocal
            if f_local.exists() and hashlib.sha256(
                    f_local.read_bytes()).hexdigest() != msha:
                print(f"::warning::medio {mlocal} no coincide con su sha256 "
                      f"registrado — posible corrupción del archivo")
        # imágenes: copia local en git. Videos/audio: archivo permanente en R2
        # (ChatMap es un endpoint de activación sin política de retención).
        R2_BASE = "https://pub-ca7861342f67400d94b3cb8ae8300a58.r2.dev/"
        is_img = bool(mlocal) and mlocal.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp"))
        is_av = (murl or "").lower().endswith((".mp4", ".mov", ".webm", ".opus",
                                               ".ogg", ".m4a"))
        if is_img:
            media_ref = "../" + mlocal
        elif is_av:
            media_ref = R2_BASE + murl.rsplit("/", 1)[-1]
        else:
            media_ref = murl
        cit_feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [lon, lat]},
                          "properties": {"id": rid, "time": ts, "media": media_ref,
                                         "score": score, "estado": estado,
                                         "aoi": (json.loads(checks or "{}")).get("aoi"),
                                         "mmi": (json.loads(checks or "{}")).get("mmi"),
                                         "mensaje": (msg or "")[:280]}})
    (PUBLIC / "chatmap.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": cit_feats}, ensure_ascii=False))

    # Manifest de R2: los videos ciudadanos viven solo en el bucket (no caben
    # en git); este manifiesto versionado (clave + sha256 + bytes) hace el
    # bucket auditable desde el repo — si un objeto cambia o falta, se nota.
    from common import ROOT as _ROOT
    manifest = []
    for fname, msha, mlocal in conn.execute(
            "SELECT media_url, media_sha256, media_local FROM citizen_reports"
            " WHERE media_sha256 IS NOT NULL ORDER BY media_url"):
        clave = (fname or "").rsplit("/", 1)[-1]
        if not clave.lower().endswith((".mp4", ".mov", ".webm", ".opus",
                                       ".ogg", ".m4a")):
            continue
        f_local = _ROOT / mlocal if mlocal else None
        manifest.append({"objeto": clave, "sha256": msha,
                         "bytes": f_local.stat().st_size
                         if f_local and f_local.exists() else None})
    (DATA / "r2_manifest.json").write_text(json.dumps(
        {"generado": snap, "bucket": "monitor-terremoto-media",
         "objetos": manifest}, ensure_ascii=False, indent=1))

    sismos = []
    for r in conn.execute(
            "SELECT fecha, municipio, departamento, muertos, heridos,"
            " viv_destruidas, viv_averiadas, lat, lon FROM official_events"
            " WHERE source='ungrd_arcgis' AND UPPER(evento) LIKE '%SISMO%'"
            " AND lat IS NOT NULL AND lon IS NOT NULL"):
        sismos.append({"type": "Feature",
                       "geometry": {"type": "Point", "coordinates": [r[8], r[7]]},
                       "properties": {"fecha": r[0], "municipio": r[1],
                                      "departamento": r[2], "muertos": r[3],
                                      "heridos": r[4], "viv_destruidas": r[5],
                                      "viv_averiadas": r[6]}})
    (PUBLIC / "ungrd_sismos.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": sismos}, ensure_ascii=False))

    gaps = {}
    from common import SNAPSHOTS
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "ungrd_socrata_agg.json"
        if f.exists():
            row = json.loads(f.read_text())[0]
            gaps["ungrd_socrata"] = {"total": row.get("n"),
                                     "desde": row.get("desde"),
                                     "hasta": row.get("hasta")}
            break
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "ungrd_arcgis_agg.json"
        if f.exists():
            raw = json.loads(f.read_text())
            at = (raw.get("features") or [{}])[0].get("attributes", {})
            maxf = at.get("maxf")
            if isinstance(maxf, (int, float)):
                from datetime import datetime, timezone
                maxf = datetime.fromtimestamp(
                    maxf / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            gaps["ungrd_arcgis"] = {"max_fecha": maxf, "total": at.get("n")}
            break

    # RUD: la fuente oficial que SÍ cubre el evento (por municipio)
    rud = conn.execute(
        "SELECT COUNT(*), SUM(familias), SUM(personas), SUM(viv_destruidas),"
        " SUM(viv_averiadas) FROM official_events WHERE source='ungrd_rud'"
    ).fetchone()
    if rud and rud[0]:
        gaps["ungrd_rud"] = {
            "municipios": rud[0], "familias": rud[1], "personas": rud[2],
            "viv_destruidas": rud[3], "viv_averiadas": rud[4],
            "fuente": "https://rud.gestiondelriesgo.gov.co/"}

    # Exposición no mapeada: población expuesta (PAGER, MMI>=6) vs población
    # dentro de AOIs Copernicus. El déficit son los asentamientos sin mirar.
    exposicion = None
    from common import SNAPSHOTS
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "usgs_pager_exposures.json"
        if f.exists():
            exp = json.loads(f.read_text())
            pe = exp.get("population_exposure") or exp
            mmis = pe.get("mmi") or []
            aggr = pe.get("aggregated_exposure") or pe.get("exposure") or []
            expuesta_6 = sum(v for m, v in zip(mmis, aggr)
                             if isinstance(v, (int, float)) and m >= 6)
            pob_aoi = sum(a["resumen"]["poblacion"] or 0 for a in aois)
            if expuesta_6:
                exposicion = {
                    "expuesta_mmi6plus": expuesta_6,
                    "en_aois_copernicus": pob_aoi,
                    "sin_mapeo_satelital": max(0, expuesta_6 - pob_aoi),
                    "pct_cubierta": round(100 * pob_aoi / expuesta_6, 1),
                    "fuente": "USGS PAGER exposures + Copernicus Estimated population",
                    "nota": ("Aproximación: bandas MMI y AOIs no son geometrías"
                             " equivalentes; ver README para la extensión con"
                             " HRSL/Open Buildings."),
                }
            break

    index = [dict(zip(["code", "name", "category", "countries", "event_time"], r))
             for r in conn.execute(
                 "SELECT code, name, category, countries, event_time"
                 " FROM activation_index WHERE exists_public=1 ORDER BY code")]

    # cronología institucional (feed GDACS: UNOSAT, ECHO, Copernicus…)
    institucional = []
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "gdacs_news_institucional.json"
        if f.exists():
            institucional = [
                {"fecha": x.get("pubdate"), "titulo": x.get("title"),
                 "url": x.get("link")}
                for x in json.loads(f.read_text())]
            break

    # todas las activaciones Copernicus de Colombia (detalle si lo tenemos)
    colombia_acts = []
    for code, name, cat, ev_time in conn.execute(
            "SELECT code, name, category, event_time FROM activation_index"
            " WHERE countries LIKE '%Colombia%' ORDER BY code"):
        det = conn.execute(
            "SELECT closed, COUNT(DISTINCT p.aoi_name), COUNT(*)"
            " FROM activations a LEFT JOIN products p ON p.code=a.code"
            "  AND p.snapshot_date=a.snapshot_date"
            " WHERE a.code=? AND a.snapshot_date="
            "  (SELECT MAX(snapshot_date) FROM activations WHERE code=?)",
            (code, code)).fetchone()
        colombia_acts.append({
            "code": code, "name": name, "category": cat, "event_time": ev_time,
            "closed": bool(det[0]) if det and det[0] is not None else None,
            "n_aois": det[1] if det else 0, "n_productos": det[2] if det else 0,
            "visor": f"https://rapidmapping.emergency.copernicus.eu/{code}/"})

    evento = {"codigo": "EMSR916", "usgs_id": "us6000tjl2",
              "gdacs": "EQ1557236", "glide": "EQ-2026-000146-COL"}
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "usgs_us6000tjl2.json"
        if f.exists():
            ev = json.loads(f.read_text())
            evento["coordinates"] = ev.get("geometry", {}).get("coordinates")
            evento["mag"] = ev.get("properties", {}).get("mag")
            evento["place"] = ev.get("properties", {}).get("place")
            evento["felt"] = ev.get("properties", {}).get("felt")
            break

    # página de titulares: EMM completo + feeds comunitarios, con AOIs y
    # territorio emparejados para filtros por departamento/municipio.
    from crosscheck import match_text_to_aois
    from municipios import match_departamentos_text, match_municipios_text
    from sources.community_feeds import feed_index
    feeds = feed_index()

    def noticia(fecha, titulo, medio, url, origen, extra_text="", feed=None):
        text = f"{titulo} {medio or ''} {extra_text or ''}"
        municipios = set(match_municipios_text(text))
        departamentos = set(match_departamentos_text(text, sorted(municipios)))
        if feed:
            municipios.update(feed.get("municipios") or [])
            departamentos.update(feed.get("departamentos") or [])
        return {
            "fecha": fecha, "titulo": titulo[:200], "medio": medio, "url": url,
            "origen": origen,
            "aois": match_text_to_aois(text),
            "municipios": sorted(municipios),
            "departamentos": sorted(departamentos),
        }

    noticias = []
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "gdacs_emm.json"
        if f.exists():
            for x in json.loads(f.read_text()):
                titulo = (x.get("title") or "").strip()
                noticias.append(noticia(
                    (x.get("pubdate") or "")[:19], titulo, x.get("source"),
                    x.get("link"), "gdacs-emm",
                    extra_text=(x.get("description") or "")[:300],
                    feed=feeds.get("gdacs-emm")))
            break
    for url, fid, fecha, titulo, medio in conn.execute(
            "SELECT url, feed_id, fecha, titulo, medio FROM news_items"):
        noticias.append(noticia(
            fecha, titulo, medio, url, fid, feed=feeds.get(fid)))
    noticias.sort(key=lambda n: n.get("fecha") or "", reverse=True)
    (PUBLIC / "noticias.json").write_text(json.dumps(
        {"generado": snap, "total": len(noticias), "items": noticias},
        ensure_ascii=False))

    # Municipios en el área de influencia: menciones de prensa + intensidad
    # percibida, aunque no sean AOIs Copernicus.
    from municipios import build_municipios
    dyfi = None
    dyfi_path = PUBLIC / "dyfi_cells.geojson"
    if dyfi_path.exists():
        dyfi = json.loads(dyfi_path.read_text())
    poblacion = None
    pop_path = PUBLIC / "dane_population_2026.json"
    if pop_path.exists():
        poblacion = (json.loads(pop_path.read_text()).get("items") or {})
    # Excluir el AOI regional: cubre el área de influencia completa, pero no
    # equivale a una zona urbana analizada con producto de daño.
    extents_detalle = {k: v for k, v in extents.items() if k != "Western Colombia"}
    municipios, municipios_gj = build_municipios(noticias, dyfi, extents_detalle,
                                                 poblacion)
    (PUBLIC / "municipios.json").write_text(json.dumps(
        {"generado": snap, "total": len(municipios), "items": municipios},
        ensure_ascii=False))
    (PUBLIC / "municipios.geojson").write_text(json.dumps(
        municipios_gj, ensure_ascii=False))

    # Hitos curados (respuesta local + cambios del monitor): el fichero fuente
    # vive en feeds/ y se publica tal cual junto al resto de datos.
    from common import ROOT
    hitos_src = ROOT / "feeds" / "hitos_monitor.json"
    if hitos_src.exists():
        (PUBLIC / "hitos_monitor.json").write_text(
            hitos_src.read_text(encoding="utf-8"), encoding="utf-8")

    # RUD en el tiempo: serie diaria agregada + detalle municipal del último día
    rud_serie = [dict(zip(["fecha", "municipios", "familias", "personas",
                           "viv_destruidas", "viv_averiadas"], r))
                 for r in conn.execute(
                     "SELECT snapshot_date, COUNT(*), SUM(familias), SUM(personas),"
                     " SUM(viv_destruidas), SUM(viv_averiadas) FROM rud_daily"
                     " GROUP BY snapshot_date ORDER BY snapshot_date")]
    ult_dia = rud_serie[-1]["fecha"] if rud_serie else None
    dia_prev = rud_serie[-2]["fecha"] if len(rud_serie) > 1 else None
    rud_municipios = []
    if ult_dia:
        prev = {}
        if dia_prev:
            prev = {(r[0], r[1]): r[2] for r in conn.execute(
                "SELECT departamento, municipio, familias FROM rud_daily"
                " WHERE snapshot_date=?", (dia_prev,))}
        for dep, mun, fam, per, dest, aver in conn.execute(
                "SELECT departamento, municipio, familias, personas,"
                " viv_destruidas, viv_averiadas FROM rud_daily"
                " WHERE snapshot_date=? ORDER BY familias DESC", (ult_dia,)):
            fila = {"departamento": dep, "municipio": mun, "familias": fam,
                    "personas": per, "viv_destruidas": dest, "viv_averiadas": aver}
            if dia_prev:
                antes = prev.get((dep, mun))
                fila["delta_familias"] = (fam or 0) - (antes or 0) if antes is not None else None
                fila["nuevo"] = (dep, mun) not in prev
            rud_municipios.append(fila)

    # rud.json aparte: archivo dedicado y versionado con TODO el histórico
    # municipal día a día — si el RUD desaparece, esto sobrevive en el repo.
    rud_detalle: dict[str, list] = {}
    for r in conn.execute(
            "SELECT snapshot_date, departamento, municipio, familias, personas,"
            " viv_destruidas, viv_averiadas, habitables, nohabitables FROM rud_daily"
            " ORDER BY snapshot_date, familias DESC"):
        rud_detalle.setdefault(r[0], []).append(dict(zip(
            ["departamento", "municipio", "familias", "personas",
             "viv_destruidas", "viv_averiadas", "habitables", "nohabitables"], r[1:])))
    (PUBLIC / "rud.json").write_text(json.dumps({
        "generado": snap,
        "fuente": "https://rud.gestiondelriesgo.gov.co/",
        "descripcion": "Registro Único de Damnificados (UNGRD), capturado a diario "
                       "por el monitor. serie = agregado por día de captura; "
                       "detalle_diario = filas municipales de cada captura; "
                       "municipios = detalle del último día con deltas.",
        "serie": rud_serie, "municipios": rud_municipios,
        "detalle_diario": rud_detalle,
    }, ensure_ascii=False))

    monitor = {
        # granularidad de día, no de hora: dos corridas el mismo día deben
        # producir bytes idénticos (idempotencia => sin commits espurios)
        "generado": snap, "fecha": snap,
        "evento": evento,
        "aois": sorted(aois, key=lambda a: a["numero"] or 0),
        "media_volume": media, "entregas": entregas,
        "brechas_oficiales": gaps, "exposicion": exposicion,
        "rud": {"serie": rud_serie, "municipios": rud_municipios},
        "citizen": {"chatmap_total": len(cit_feats),
                    "en_aoi": sum(1 for f in cit_feats
                                  if f["properties"].get("aoi"))},
        "municipios": {"total": len(municipios),
                       "fuera_aoi": sum(1 for m in municipios
                                        if not m["en_aoi_copernicus"])},
        "activation_index": index,
        "institucional": institucional,
        "colombia_activaciones": colombia_acts,
    }
    (PUBLIC / "monitor.json").write_text(
        json.dumps(monitor, indent=1, ensure_ascii=False))

    # exportación CSV del cruce
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["aoi", "estado", "etiqueta", "poblacion", "edificios_afectados",
                "vias_afectadas_km", "interrupciones_viales", "n_prensa",
                "n_ciudadano", "n_oficial", "entrega_producto", "fuente"])
    for a in monitor["aois"]:
        w.writerow([a["aoi"], a["cruce"]["estado"], a["cruce"]["etiqueta"],
                    a["resumen"]["poblacion"], a["resumen"]["edificios_afectados"],
                    a["resumen"]["vias_afectadas_km"],
                    a["resumen"]["interrupciones_viales"],
                    a["cruce"].get("n_prensa"), a["cruce"].get("n_ciudadano"),
                    a["cruce"].get("n_oficial"), a["producto"]["entrega"],
                    "Copernicus EMSR916 + GDACS EMM + ChatMap"])
    (PUBLIC / "crosscheck.csv").write_text(buf.getvalue())

    conn.close()
    return {"aois": len(aois), "citizen": len(cit_feats), "sismos_hist": len(sismos),
            "media_dias": len(media), "noticias": len(noticias)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
