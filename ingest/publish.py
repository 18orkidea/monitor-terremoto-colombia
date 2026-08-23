"""Genera data/public/*: los artefactos que consume el mapa y las exportaciones.

Privacidad: de citizen_reports sólo salen lat_pub/lon_pub (redondeadas) y la
URL del medio; jamás la coordenada exacta.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json

from common import (db, today, anterior_al_sismo, ARCHIVO_EN_R2,
                    DATA, FECHA_SISMO, PUBLIC)
from geo import wkt_to_geojson
from sources.community_feeds import dominio

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


def manifiesto_de_activos(conn) -> list[dict]:
    """El manifiesto auditable del bucket: objeto + sha256 + bytes.

    Los vídeos ciudadanos viven solo en R2 (no caben en git); este manifiesto
    versionado es lo que hace el bucket auditable desde el repo — si un objeto
    cambia o falta, se nota. Y desde que **autoriza a no descargar**, cada línea
    suya tiene que poder defenderse sola.

    **Los bytes de un activo son un dato del archivo, no del disco de quien
    publica.** Desde que el guardián de `chatmap.py` deja de descargar lo que ya
    está archivado, la máquina de la corrida NO tiene los vídeos: preguntarle
    solo al disco habría puesto `bytes: null` en los 77 objetos y el manifiesto
    habría perdido su columna entera en el primer commit automático. Por eso hay
    tres vías, de más a menos fuerte: el cuerpo, el registro de su descarga en
    `sources_log`, y lo que ya declaraba el manifiesto anterior.

    **Las tres van atadas al sha256 que se está escribiendo.** Un tamaño que no
    sea de ESE cuerpo es peor que no tenerlo: `bytes` es el único campo que la
    auditoría de `daily.yml` puede contrastar contra R2, así que una cifra
    desalineada o suena en falso todos los días —y un aviso falso mata la
    lectura de las alertas— o enmascara una sustitución de verdad.

    **Y el manifiesto no encoge.** Si la base llega vacía —`rebuild_db` o
    `chatmap` fallaron y R13 se lo tragó—, esta función escribiría `objetos: []`
    y el bot lo commitearía: los cuerpos seguirían en R2 pero dejarían de estar
    declarados, que es justo lo que hace auditable el bucket. Lo que ya se
    declaró archivado se arrastra, y que la base no lo reconozca lo canta
    `alerts.divergencias_del_archivo_de_activos` como el huérfano que es.
    """
    from common import ROOT as _ROOT, manifiesto_r2
    previo = manifiesto_r2()
    manifiesto = []
    for fname, msha, mlocal in conn.execute(
            "SELECT media_url, media_sha256, media_local FROM citizen_reports"
            " WHERE media_sha256 IS NOT NULL ORDER BY media_url"):
        clave = (fname or "").rsplit("/", 1)[-1]
        if not clave.lower().endswith(ARCHIVO_EN_R2):
            continue
        manifiesto.append({"objeto": clave, "sha256": msha,
                           "bytes": _bytes_del_activo(conn, _ROOT, fname, clave,
                                                      msha, mlocal, previo)})
    # el manifiesto no encoge: lo ya declarado sigue declarado
    declarados = {o["objeto"] for o in manifiesto}
    for clave, o in previo.items():
        if clave not in declarados:
            manifiesto.append({"objeto": clave, "sha256": o["sha256"],
                               "bytes": o.get("bytes")})
    manifiesto.sort(key=lambda o: o["objeto"])
    return manifiesto


def _bytes_del_activo(conn, raiz, url, clave, sha, mlocal, previo) -> int | None:
    """El tamaño de ESE cuerpo, o None. Nunca el de otro (M10: se omite)."""
    f_local = raiz / mlocal if mlocal else None
    if f_local is not None:
        try:
            cuerpo = f_local.read_bytes()
            if hashlib.sha256(cuerpo).hexdigest() == sha:
                return len(cuerpo)      # el cuerpo, que es la prueba
        except OSError:
            pass                        # no está en este clon: sigue el archivo
    fila = conn.execute(                # el registro de SU descarga
        "SELECT bytes FROM sources_log WHERE url=? AND sha256=?"
        " AND http_status=200 AND bytes>0 ORDER BY id DESC LIMIT 1",
        (url, sha)).fetchone()
    if fila:
        return fila[0]
    # y, si el log tampoco lo sabe, lo que ya declaraba el manifiesto para este
    # mismo contenido: una cifra que estuvo bien no se pierde por no remedirla
    anterior = previo.get(clave) or {}
    if anterior.get("sha256") == sha:
        return anterior.get("bytes")
    return None


def run() -> dict:
    from common import ROOT
    ROOT_FEEDS = ROOT / "feeds"
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
    # El medio sale de `news_items` cuando la pieza vino de un feed: `evidence`
    # guarda una firma, pero no distingue una cabecera declarada de un nombre
    # de feed, y la portada necesita esa diferencia para no llamar «medio» a
    # «Google News — Istmina». Las piezas del EMM de GDACS no están en
    # `news_items` (LEFT JOIN sin pareja): ahí `fuente` ya es la cabecera.
    for aoi, cita, fuente, fecha, url, propia, canonico, dom in conn.execute(
            "SELECT e.aoi_name, e.cita, e.fuente, e.fecha, e.url,"
            "       n.url IS NOT NULL, n.medio_canonico, n.medio_dominio"
            " FROM evidence e LEFT JOIN news_items n ON n.url = e.url"
            " WHERE e.tipo='prensa' AND e.snapshot_date="
            " (SELECT MAX(snapshot_date) FROM evidence WHERE tipo='prensa')"
            " ORDER BY e.fecha"):
        prensa_por_aoi.setdefault(aoi, []).append(
            {"titular": cita, "medio": fuente, "fecha": fecha, "url": url,
             "medio_canonico": canonico if propia else fuente,
             "medio_dominio": dom if propia else dominio(url or "")})

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
    # titular). El corte es el del corpus entero —FECHA_SISMO, ver common.py—:
    # antes esta serie cortaba dos días antes por su cuenta y el resto del
    # sitio no cortaba, así que el mismo titular contaba o no según la página.
    # Única diferencia con `anterior_al_sismo()`: aquí un titular sin fecha
    # tampoco entra, porque una serie diaria no tiene día donde ponerlo.
    feeds_por_dia = dict(conn.execute(
        "SELECT substr(fecha,1,10) d, COUNT(*) FROM news_items"
        " WHERE fecha >= ? GROUP BY d", (FECHA_SISMO,)))

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
        is_av = (murl or "").lower().endswith(ARCHIVO_EN_R2)
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

    (DATA / "r2_manifest.json").write_text(json.dumps(
        {"generado": snap, "bucket": "monitor-terremoto-media",
         "objetos": manifiesto_de_activos(conn)}, ensure_ascii=False, indent=1))

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

    def noticia(fecha, titulo, medio, url, origen, extra_text="", feed=None,
                medio_canonico=None, medio_dominio=None):
        # El medio canónico NO entra en el texto que se cruza con topónimos: un
        # medio llamado «El País Cali» o «Diario del Cauca» atribuiría a un
        # municipio noticias que no lo mencionan (R10 vigila lo contrario, las
        # coincidencias parciales, pero esto sería una atribución de pleno
        # derecho por el nombre de la cabecera).
        text = f"{titulo} {medio or ''} {extra_text or ''}"
        municipios = set(match_municipios_text(text))
        departamentos = set(match_departamentos_text(text, sorted(municipios)))
        if feed:
            municipios.update(feed.get("municipios") or [])
            departamentos.update(feed.get("departamentos") or [])
        return {
            "fecha": fecha, "titulo": titulo[:200], "medio": medio, "url": url,
            # `medio` es el feed que trajo la pieza; `medio_canonico` es la
            # cabecera que la firma, según el propio RSS. Contar medios por el
            # primero cuenta feeds, no periódicos.
            "medio_canonico": medio_canonico, "medio_dominio": medio_dominio,
            "origen": origen,
            "aois": match_text_to_aois(text),
            "municipios": sorted(municipios),
            "departamentos": sorted(departamentos),
        }

    # Los titulares anteriores al sismo no entran (ver FECHA_SISMO en
    # common.py). No se pierden —siguen en news_items, en los snapshots y en
    # sources_log—: dejan de contarse, porque hablan de otros sismos. El
    # descarte se cuenta y sale en el resumen de la corrida: un filtro que no
    # deja rastro de cuánto tira no es auditable.
    noticias, previas = [], 0
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "gdacs_emm.json"
        if f.exists():
            for x in json.loads(f.read_text()):
                titulo = (x.get("title") or "").strip()
                # En el EMM de GDACS el enlace es directo al medio y `source`
                # ya nombra la cabecera (en minúsculas, «theprint»): aquí el
                # medio nunca estuvo escondido. Mismo rasero que el <source>
                # del RSS: un `source` vacío es ausencia de dato, no un medio
                # llamado «» que engordaría el recuento de cabeceras.
                fecha = (x.get("pubdate") or "")[:19]
                if anterior_al_sismo(fecha):
                    previas += 1
                    continue
                noticias.append(noticia(
                    fecha, titulo, x.get("source"),
                    x.get("link"), "gdacs-emm",
                    extra_text=(x.get("description") or "")[:300],
                    feed=feeds.get("gdacs-emm"),
                    medio_canonico=(x.get("source") or "").strip() or None,
                    medio_dominio=dominio(x.get("link") or "")))
            break
    for url, fid, fecha, titulo, medio, medio_canonico, medio_dominio in conn.execute(
            "SELECT url, feed_id, fecha, titulo, medio, medio_canonico,"
            " medio_dominio FROM news_items"):
        if anterior_al_sismo(fecha):
            previas += 1
            continue
        noticias.append(noticia(
            fecha, titulo, medio, url, fid, feed=feeds.get(fid),
            medio_canonico=medio_canonico, medio_dominio=medio_dominio))
    noticias.sort(key=lambda n: n.get("fecha") or "", reverse=True)
    # `previas_al_sismo` viaja en el producto público, no solo por el stdout de
    # la corrida: los logs de Actions caducan y un filtro que no dice cuánto
    # tira desde el propio dato no es auditable.
    (PUBLIC / "noticias.json").write_text(json.dumps(
        {"generado": snap, "total": len(noticias),
         "previas_al_sismo": previas, "desde": FECHA_SISMO, "items": noticias},
        ensure_ascii=False))

    # Municipios en el área de influencia: menciones de prensa + intensidad
    # percibida + registro RUD, aunque no sean AOIs Copernicus.
    from municipios import build_municipios, _find_population, _norm as _norm_mun
    dyfi = None
    dyfi_path = PUBLIC / "dyfi_cells.geojson"
    if dyfi_path.exists():
        dyfi = json.loads(dyfi_path.read_text())
    poblacion = None
    pop_path = PUBLIC / "dane_population_2026.json"
    if pop_path.exists():
        poblacion = (json.loads(pop_path.read_text()).get("items") or {})
    divipola = None
    div_path = PUBLIC / "divipola_coords.json"
    if div_path.exists():
        divipola = (json.loads(div_path.read_text()).get("items") or {})

    # RUD en el tiempo: serie diaria agregada + detalle municipal del último día
    # (se construye antes que la capa de municipios para alimentarla)
    rud_serie = [dict(zip(["fecha", "municipios", "familias", "personas",
                           "viv_destruidas", "viv_averiadas"], r))
                 for r in conn.execute(
                     "SELECT snapshot_date, COUNT(*), SUM(familias), SUM(personas),"
                     " SUM(viv_destruidas), SUM(viv_averiadas) FROM rud_daily"
                     " GROUP BY snapshot_date ORDER BY snapshot_date")]
    # Puntos que no vienen de una captura propia (una corrida perdida, y el RUD
    # solo devuelve su estado actual): se fusionan MARCADOS, nunca en silencio.
    # Sin esto la curva saltaría el día como si el registro no hubiera crecido.
    recon_path = ROOT_FEEDS / "rud_reconstruido.json"
    if recon_path.exists():
        vistos = {r["fecha"] for r in rud_serie}
        for pt in json.loads(recon_path.read_text()).get("puntos", []):
            if pt["fecha"] in vistos:
                continue          # una captura propia siempre gana
            rud_serie.append({
                "fecha": pt["fecha"], "municipios": pt.get("municipios"),
                "familias": pt.get("familias"), "personas": pt.get("personas"),
                "viv_destruidas": pt.get("viv_destruidas"),
                "viv_averiadas": pt.get("viv_averiadas"),
                "reconstruido": True, "origen": pt.get("origen"),
                "evidencia": pt.get("evidencia"),
            })
        rud_serie.sort(key=lambda r: r["fecha"])

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
            pop = _find_population(poblacion, mun, {"departamento": dep}, divipola)
            fila["poblacion_2026"] = pop.get("poblacion_2026") if pop else None
            # 4 decimales: una persona en una capital da 0,0003 % — redondear
            # a 2 lo convertiría en 0,0 y el sitio leería «sin damnificados»
            fila["tasa_pct"] = (round(per / fila["poblacion_2026"] * 100, 4)
                                if per and fila["poblacion_2026"] else None)
            if dia_prev:
                antes = prev.get((dep, mun))
                fila["delta_familias"] = (fam or 0) - (antes or 0) if antes is not None else None
                fila["nuevo"] = (dep, mun) not in prev
            rud_municipios.append(fila)
    rud_por_mun = {(_norm_mun(f["departamento"]), _norm_mun(f["municipio"])): f
                   for f in rud_municipios}

    # Excluir el AOI regional: cubre el área de influencia completa, pero no
    # equivale a una zona urbana analizada con producto de daño.
    extents_detalle = {k: v for k, v in extents.items() if k != "Western Colombia"}
    # UNOSAT por municipio: la segunda mirada satelital entra en la capa de
    # municipios con etiqueta propia — no se funde con las cifras de
    # Copernicus, que son estadísticas revisadas por AOI y no puntos
    # fotointerpretados sin validar en campo.
    from sources.unosat import GLIDE as UNOSAT_GLIDE, paquete_vigente
    unosat_por_mun = {}
    sha_vigente = paquete_vigente(conn)
    for mun, dano, code, fecha, n in conn.execute(
            "SELECT municipio, dano, event_code, MAX(sensor_date), COUNT(*)"
            " FROM unosat_damage WHERE municipio IS NOT NULL AND paquete_sha=?"
            " GROUP BY municipio, dano, event_code", (sha_vigente,)):
        d = unosat_por_mun.setdefault(mun, {"edificios": 0, "observados": 0,
                                            "posibles": 0,
                                            "codigo_inconsistente": 0,
                                            "fecha_imagen": None})
        # El código de evento de un punto NO decide a qué terremoto pertenece:
        # lo decide el GLIDE que declara el PRODUCTO que lo publica, que es
        # donde la fuente dice de qué habla. Los cinco productos de UNOSAT
        # declaran EQ20260810COL, este terremoto.
        #
        # Dentro del shapefile, en cambio, 209 puntos —los 201 de Zarzal y 8
        # de Manizales— llevan `EQ20260822COL`, un código que implica un sismo
        # del 22-ago-2026: una fecha posterior a la imagen que los retrata (13
        # y 11 de agosto) y que, cuando esto se escribió, aún no había llegado.
        # Es un error de etiquetado en origen, y el producto que los publica lo
        # desmiente.
        #
        # Hasta el 21-ago-2026 se excluían del total. Se dejó de hacer cuando
        # la fuente publicó Zarzal: excluir 8 puntos era prudencia; excluir un
        # municipio entero que nadie más ha mirado era callar lo que la fuente
        # sí dijo. Se cuentan, y la inconsistencia se publica al lado.
        if (code or "").upper() != UNOSAT_GLIDE:
            d["codigo_inconsistente"] += n
        d["edificios"] += n
        # la fuente escribe «Damage» en unas capas y «Damaged» en otras para lo
        # mismo; «Possible Damage» es la hipótesis, no el hallazgo
        if (dano or "").lower().startswith("possible"):
            d["posibles"] += n
        elif dano:
            d["observados"] += n
        # sin grado no hay observación: ni posible ni observado (R3). Queda
        # contado en `edificios`, que es lo que UNOSAT miró.
        d["fecha_imagen"] = max(d["fecha_imagen"] or "", fecha or "") or None

    # ICube-SERTIT por municipio: la tercera mirada. No se funde con las otras
    # dos —cada servicio recortó su propia zona— y por eso viaja con el área
    # que declara haber analizado: sin ella, comparar 253 con 182 en Pereira
    # sería comparar dos ventanas distintas como si fueran la misma.
    from sources.sertit import resumen as sertit_resumen
    sertit_por_mun = {}
    for mun, d in sertit_resumen(conn).items():
        grados = d.get("por_grado") or {}
        sertit_por_mun[mun] = {
            "edificios": d.get("edificios") or 0,
            "sin_grado": d.get("sin_grado") or None,
            "destruidos": grados.get("Destroyed"),
            "danados": grados.get("Damaged"),
            "posibles": grados.get("Possibly damaged"),
            "area_km2": d.get("area_km2"),
            # literal de la fuente, en francés («Pléiades Néo acquise le
            # 11/08/2026»): se conserva tal cual y se nombra por lo que es,
            # para que nadie lo confunda con una fecha normalizada (R3)
            "imagen_literal": d.get("imagen"),
        }

    # Las búsquedas de prensa se derivan del MISMO catálogo que verá
    # `build_municipios` —curados + los que abre el RUD—, no de uno propio: si
    # se derivaran por separado, `busqueda_propia` podría afirmar de un
    # municipio lo contrario de lo que hizo la corrida (M2).
    from municipios import catalogo_municipios
    from sources.community_feeds import municipal_google_news_feeds
    catalogo = catalogo_municipios(rud_por_mun, divipola)
    con_busqueda = {f["municipio"] for f in municipal_google_news_feeds(catalogo)}
    from geo import grid_mmi_vigente
    grid_mmi = grid_mmi_vigente()
    municipios, municipios_gj = build_municipios(noticias, dyfi, extents_detalle,
                                                 poblacion, rud_por_mun, divipola,
                                                 unosat_por_mun, con_busqueda,
                                                 sertit=sertit_por_mun,
                                                 grid_mmi=grid_mmi)
    (PUBLIC / "municipios.json").write_text(json.dumps(
        {"generado": snap, "total": len(municipios), "items": municipios},
        ensure_ascii=False))
    (PUBLIC / "municipios.geojson").write_text(json.dumps(
        municipios_gj, ensure_ascii=False))

    from municipios import capa_sin_mirada
    (PUBLIC / "municipios_mapa.json").write_text(json.dumps(
        capa_sin_mirada(municipios, snap, grid_mmi), ensure_ascii=False))

    # Hitos curados (respuesta local + cambios del monitor): el fichero fuente
    # vive en feeds/ y se publica tal cual junto al resto de datos.
    hitos_src = ROOT_FEEDS / "hitos_monitor.json"
    if hitos_src.exists():
        (PUBLIC / "hitos_monitor.json").write_text(
            hitos_src.read_text(encoding="utf-8"), encoding="utf-8")

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

    # UNOSAT agregado, tal como estaba: lo consumen el sitio y los monitor.json
    # archivados, y quitarlo rompería la serie. Lo que YA NO se hace con estas
    # cifras es sumarlas para la portada — de eso se encarga ahora el bloque
    # `satelital`, que une los puntos en vez de sumar totales.
    # `posibles` viaja al lado del total porque no es lo mismo un edificio
    # observado que uno que la fuente solo cree dañado.
    unosat_totales = {
        "edificios": sum(d["edificios"] for d in unosat_por_mun.values()),
        "observados": sum(d["observados"] for d in unosat_por_mun.values()),
        "posibles": sum(d["posibles"] for d in unosat_por_mun.values()),
        "codigo_inconsistente": sum(d["codigo_inconsistente"]
                                    for d in unosat_por_mun.values()),
        "municipios": sorted(m["municipio"] for m in municipios
                             if m.get("unosat_edificios")),
        "municipios_tambien_en_aoi_copernicus": sorted(
            m["municipio"] for m in municipios
            if m.get("unosat_edificios") and m.get("en_aoi_copernicus")),
    }

    # El recuento satelital del monitor. Tres servicios miran ya el mismo país
    # y dos de ellos, las mismas ciudades: sumar sus totales contaría dos veces
    # los mismos tejados y quedarse con el mayor tiraría lo que el otro vio en
    # exclusiva. Se unen los PUNTOS, que es lo único que sabe distinguir un
    # edificio de una cifra. Ver ingest/satelites.py.
    from satelites import recuento as recuento_satelital
    satelital = recuento_satelital(PUBLIC)
    # La fecha viaja DENTRO del bloque, no solo en el fichero suelto: la
    # tarjeta de portada la lee de aquí, y sin ella se fechaba con la última
    # entrega de Copernicus —otro servicio, otra pregunta—.
    satelital["generado"] = snap
    (PUBLIC / "satelital.json").write_text(json.dumps(
        satelital, ensure_ascii=False))

    monitor = {
        # granularidad de día, no de hora: dos corridas el mismo día deben
        # producir bytes idénticos (idempotencia => sin commits espurios)
        "generado": snap, "fecha": snap,
        "evento": evento,
        "aois": sorted(aois, key=lambda a: a["numero"] or 0),
        "media_volume": media, "entregas": entregas,
        "brechas_oficiales": gaps, "exposicion": exposicion,
        "rud": {"serie": rud_serie, "municipios": rud_municipios},
        "unosat": unosat_totales,
        "satelital": satelital,
        "citizen": {"chatmap_total": len(cit_feats),
                    "en_aoi": sum(1 for f in cit_feats
                                  if f["properties"].get("aoi"))},
        "municipios": {"total": len(municipios),
                       # nombre explícito: «fuera_aoi» es además un ESTADO de
                       # la capa (con otro significado), y cruzar los dos JSON
                       # daba dos cifras para la misma clave
                       "fuera_de_aoi_copernicus": sum(1 for m in municipios
                                        if not m["en_aoi_copernicus"])},
        "activation_index": index,
        "institucional": institucional,
        "colombia_activaciones": colombia_acts,
    }
    # El feed de balances vive en un worker de cuenta ajena (ver
    # docs/LIMITACIONES.md). Ya se archiva en cada corrida, así que se publica
    # también como producto propio: el sitio deja de depender de que el worker
    # siga en pie, y el dato sobrevive el día que se apague. La copia conserva
    # de qué snapshot salió, para que no se confunda con una captura de hoy.
    ultimo = None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "oficiales_feed.json"
        if f.exists():
            ultimo = (d.name, json.loads(f.read_text()))
            break
    if ultimo:
        fecha_snap, feed = ultimo
        feed["archivado_de"] = {
            "fuente": "worker de extracción de balances (cuenta ajena)",
            "snapshot": f"data/snapshots/{fecha_snap}/oficiales_feed.json",
        }
        (PUBLIC / "oficiales.json").write_text(
            json.dumps(feed, indent=1, ensure_ascii=False))

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
            "media_dias": len(media), "noticias": len(noticias),
            "noticias_previas_al_sismo": previas}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
