"""Microsoft AI for Good Lab: daño edificio a edificio, vía HDX.

Qué aporta que no tenga nadie más: la única capa que evalúa daño sobre **el
parque de edificios completo** de Cali y Pereira —no un recorte ni una
muestra— cruzando dos fuentes de huellas independientes (Google Open
Buildings y Overture Maps) contra imagen posterior al sismo. Donde SERTIT y
UNOSAT fotointerpretan a mano un área acotada, este modelo de IA clasifica
cada polígono del catálogo entero. Pereira tiene además una segunda entrega
—«Extended»— con revisión humana encima del modelo (`review_status`), que es
la primera vez que el monitor ve una fuente corregirse a sí misma con
verificación de campo declarada.

Origen: HDX (Humanitarian Data Exchange), organización
`microsoft-ai4g-lab`, tres datasets:
  - `2026-colombia-earthquake` (Cali, imagen Airbus del 10-ago-2026)
  - `colombia-2026-earthquake-pereira` (imagen Vantor del 12-ago-2026)
  - `colombia-2026-earthquake-pereira-extended` (13-ago-2026: reedición con
    revisión humana; NO sustituye a la anterior, la complementa — ver más
    abajo)
Sin API key. La lista de recursos de cada dataset se lee de
`package_show` (API CKAN pública) EN CADA CORRIDA — nunca se asume una URL
fija de fichero, porque HDX reindexa sus recursos y la URL de descarga
firmada cambia. Ese es el supuesto que vigila
`tests/test_supuestos_api.py::TestSupuestosMSFT`.

## Qué hay dentro de cada recurso (comprobado abriendo los gpkg, no adivinado)

Cada GeoPackage es una base SQLite (`sqlite3` lo abre tal cual, R14) con una
tabla de polígonos `MULTIPOLYGON`. **El SRS NO es el mismo en los siete**
(comprobado abriendo cada uno, no asumido de uno solo): los cuatro gpkg base
—Cali×2, Pereira×2— declaran **EPSG:32618** (UTM zona 18N); los tres de
Pereira Extended declaran **EPSG:4326** (WGS84 directo). Asumir un único SRS
fijo habría reproyectado coordenadas que ya estaban en grados y puesto el pin
de 12.928 edificios de Pereira Extended en el (0, -79) — se cazó probando
contra los siete gpkg reales, no contra uno solo, antes de escribir el
esquema final. `centroide_de_wkb_gpkg()` lee el SRS del propio blob (nunca lo
asume) y `_lon_lat()` decide cómo convertir según lo que declare: directo si
es 4326, `_utm_a_wgs84()` (fórmula de Snyder, puro `math`) si es una zona UTM
norte. `centroide_de_wkb_gpkg()` decodifica el WKB con `struct` y calcula el
centroide por el método del área con signo (shoelace), tomando el polígono de
mayor área del multipolígono y su anillo exterior — los huecos y las partes
secundarias no alteran de forma perceptible dónde cae el pin en el mapa.

Las columnas varían por fichero (avisado por el PM, confirmado abriendo los
siete): los cuatro gpkg base (Cali×2, Pereira×2) traen `damage_pct_0m/10m/20m`,
`built_pct_0m`, `damaged`, `unknown_pct`. Los tres de Pereira Extended añaden
`confidence`, `area_in_meters`, `review_status`
(''/confirmed/ground_truth/rejected/unsure), `damage_from`, `vantor_pct`,
`prior_status`; el de footprints propios de Microsoft añade además `subtype`
y `origin` ('google'|'msft': de qué huella salió CADA polígono, porque el
conjunto «msft» no es homogéneo por dentro). Todo NULL es NULL real en el
gpkg (comprobado con `typeof()`), nunca cadena vacía: R3 no exige limpieza
aquí, ya viene limpio.

## `conjunto_huellas`: tres variantes del MISMO producto, jamás se suman

Google, Overture y (en Pereira Extended) el propio Microsoft publican huellas
de edificio distintas sobre la MISMA ciudad: 97.351 edificios en el Overture
de Cali contra 320.791 en el Google de Cali, sobre el mismo terremoto. Sumar
"edificios dañados" entre conjuntos contaría el mismo edificio dos o tres
veces. `conjunto_huellas` se lee del nombre/descripción del recurso HDX
('overture' | 'google' | 'msft', en ese orden de prioridad porque el fichero
`msft_footprint…plus_google_dam…` contiene las dos palabras y el conjunto es
el de Microsoft, no el de Google).

## `msft_danos` NO es un espejo 1:1 del gpkg — decisión de escala

**882.805 edificios** en los siete gpkg; el daño real es un 0,3%-0,5% de eso.
Guardar una fila por edificio —como hacen `sertit_danos`/`unosat_damage`—
generaría ~150-200 MB de CSV versionado en `data/dumps/`, más que el resto de
`data/dumps/` junto, para un archivo que ya vive byte a byte en R2 con su
sha256 en `sources_log`. Decisión editorial (30-ago-2026, ver
`docs/DECISIONES.md`): `msft_danos` guarda SOLO lo informativo —
`damaged=1`, o `review_status` no vacío (incluye 'rejected': un rechazo
humano también informa), o `unknown_pct >= UMBRAL_NUBE` (0,5: la mitad o más
del edificio tapado por nube/niebla/humo, así que el veredicto "sin daño" no
es fiable)—. El censo completo, con sus totales, vive agregado en
`msft_recursos` (`total_edificios`, `total_danados`, `total_revisados`,
`total_desconocidos`), para que cualquier tasa se pueda calcular sin el
censo fila a fila. Quien audite y vea menos filas que edificios reales: el
resto está en el gpkg archivado, no ha desaparecido.

## Dónde vive cada byte (decisión editorial, 30-ago-2026)

Los `.geojson` (máscaras, cientos de bytes a un par de KB) van a git, como
las fotos ciudadanas. Los siete `.gpkg` y los dos `.tif` (268 MB) van a R2
(`ARCHIVO_EN_R2` en `common.py`), como los vídeos: se descargan, se
parsean UNA vez —antes de que `daily.yml` los suba, para que la corrida no
dependa de volver a bajar 240 MB— y su sha256 queda en `sources_log` y en
`msft_recursos.sha256` igual que si vivieran en git. Los datos son estáticos
desde el 21-ago-2026 (última reedición de HDX): `run()` no reprocesa un
recurso cuyo sha256 ya tiene fila en `msft_recursos`.

## Lo que la fuente NO garantiza

- **No es validación en campo** salvo donde `review_status` lo diga
  explícitamente (`ground_truth`, `confirmed`): el resto es predicción de un
  modelo de IA sobre imagen de satélite, igual que SERTIT y UNOSAT.
- **`unknown_pct` no es opcional de ignorar**: 17.588 edificios del
  Pereira Extended-msft (14% del total) tienen algo de nube encima: los que
  superan el umbral entran a `msft_danos` marcados como tales, no como "sin
  daño".
- Sin licencia declarada en el JSON de HDX más allá de `cc-by` (Creative
  Commons Attribution): exige atribuir a «Microsoft AI for Good Lab», menos
  restrictiva que SERTIT.

## Plan de sucesión (si data.humdata.org muere mañana)

- **Sobrevive todo**: las máscaras en git, los gpkg/tif en R2 con manifiesto
  versionado (`data/r2_manifest.json`) que viaja en el clon y que
  `ingest/auditar_r2.py` audita a diario contra el bucket real — la misma
  red que protege a los vídeos ciudadanos.
- **Snapshot diario del catálogo** (`package_show` de los tres datasets):
  aunque HDX caiga, queda la serie de qué recursos declaraba cada día — sirve
  además de sonda de vida si Microsoft publica una reedición nueva.
  Wayback no aporta nada sobre esto: no hay HTML público que archivar aparte
  de los propios bytes, que ya están aquí.
- **Export dedicado**: `data/public/msft_damage.geojson`, el subconjunto
  informativo con lat/lon en WGS84.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import struct

from common import (ARCHIVO_EN_R2, MEDIA, PUBLIC, ROOT, activo_archivado,
                     fetch, fetch_json, manifiesto_r2, today, utcnow)

CKAN_PACKAGE_SHOW = "https://data.humdata.org/api/3/action/package_show"

DATASETS = {
    "cali": {"ckan_id": "2026-colombia-earthquake",
             "municipio": "Cali", "departamento": "Valle del Cauca"},
    "pereira": {"ckan_id": "colombia-2026-earthquake-pereira",
                "municipio": "Pereira", "departamento": "Risaralda"},
    "pereira_extended": {"ckan_id": "colombia-2026-earthquake-pereira-extended",
                          "municipio": "Pereira", "departamento": "Risaralda"},
}

# La mitad o más del edificio tapado por nube/niebla/humo: el modelo no pudo
# juzgarlo, así que "sin daño" no es un veredicto fiable y la fila entra a
# msft_danos aunque damaged=0 y no haya revisión humana. Ver docstring y
# docs/DECISIONES.md (30-ago-2026) — lo fija este número, no un test aparte.
UMBRAL_NUBE = 0.5

assert {".gpkg", ".tif"} <= set(ARCHIVO_EN_R2), (
    "msft.py asume que .gpkg/.tif viven en R2 (ver docs/DECISIONES.md, "
    "30-ago-2026); common.ARCHIVO_EN_R2 ya no los declara")


# --- Geometría: WKB de GeoPackage → centroide en WGS84, sin dependencias ----

def _utm_a_wgs84(easting: float, northing: float, zona: int = 18) -> tuple[float, float]:
    """UTM (WGS84) → (lon, lat), fórmula de Snyder. Los gpkg de Microsoft
    vienen en EPSG:32618 (UTM 18N, la zona de Cali y Pereira); el mapa
    necesita WGS84 y el proyecto no puede instalar pyproj (R14)."""
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    e2 = f * (2 - f)
    e_p2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = easting - 500000.0
    m = northing / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
            + (151 * e1**3 / 96) * math.sin(6 * mu)
            + (1097 * e1**4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = e_p2 * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3*t1 + 10*c1 - 4*c1**2 - 9*e_p2) * d**4 / 24
        + (61 + 90*t1 + 298*c1 + 45*t1**2 - 252*e_p2 - 3*c1**2) * d**6 / 720)
    lon = (d
           - (1 + 2*t1 + c1) * d**3 / 6
           + (5 - 2*c1 + 28*t1 - 3*c1**2 + 8*e_p2 + 24*t1**2) * d**5 / 120) / math.cos(phi1)
    meridiano_central = zona * 6 - 183
    return math.degrees(lon) + meridiano_central, math.degrees(lat)


def _leer_anillo(buf: bytes, off: int, endian: str) -> tuple[list[tuple[float, float]], int]:
    (n,) = struct.unpack_from(endian + "I", buf, off)
    off += 4
    pts = []
    for _ in range(n):
        x, y = struct.unpack_from(endian + "dd", buf, off)
        pts.append((x, y))
        off += 16
    return pts, off


def _leer_poligono(buf: bytes, off: int, endian: str) -> tuple[list[list[tuple[float, float]]], int]:
    (n,) = struct.unpack_from(endian + "I", buf, off)
    off += 4
    anillos = []
    for _ in range(n):
        pts, off = _leer_anillo(buf, off, endian)
        anillos.append(pts)
    return anillos, off


def _centroide_de_anillo(puntos: list[tuple[float, float]]) -> tuple[tuple[float, float], float]:
    """Centroide y área con signo de un anillo (shoelace). Si el anillo es
    degenerado (área cero: una línea, tres puntos duplicados), se cae al
    promedio simple de vértices en vez de dividir por cero."""
    a2 = cx = cy = 0.0
    for i in range(len(puntos) - 1):
        x0, y0 = puntos[i]
        x1, y1 = puntos[i + 1]
        cruce = x0 * y1 - x1 * y0
        a2 += cruce
        cx += (x0 + x1) * cruce
        cy += (y0 + y1) * cruce
    if a2 == 0:
        xs = [p[0] for p in puntos]
        ys = [p[1] for p in puntos]
        return (sum(xs) / len(xs), sum(ys) / len(ys)), 0.0
    return (cx / (3 * a2), cy / (3 * a2)), abs(a2 / 2)


def centroide_de_wkb_gpkg(blob: bytes) -> tuple[float, float, int]:
    """Centroide (x, y, srs_id) de una geometría POLYGON o MULTIPOLYGON en
    formato binario de GeoPackage.

    El binario de GeoPackage antepone su propia cabecera (magia 'GP',
    versión, flags con el orden de bytes, SRS id y el tamaño del envelope) al
    WKB estándar — no es WKB a secas, por eso ningún parser de WKB genérico
    lo lee sin saltarse esta parte primero (spec OGC GeoPackage §2.1.3).
    De un MULTIPOLYGON se toma el polígono de MAYOR área y su anillo
    exterior: los huecos y las partes secundarias no cambian de forma
    perceptible dónde cae el pin de un edificio en el mapa.

    **El SRS se lee del propio blob, nunca se asume.** Los cuatro gpkg base
    (Cali×2, Pereira×2) declaran EPSG:32618 (UTM 18N); los tres de Pereira
    Extended declaran EPSG:4326 (WGS84 directo) — comprobado abriendo los
    siete, no es un detalle menor: asumir un SRS fijo para todos habría
    reproyectado coordenadas que ya estaban en grados, produciendo un pin en
    el (0, -79) en vez de Pereira. Quien llama decide qué hacer con cada SRS.
    """
    if blob[0:2] != b"GP":
        raise ValueError("no es un blob de geometría GeoPackage (falta 'GP')")
    flags = blob[3]
    header_endian = "<" if flags & 0x1 else ">"
    (srs_id,) = struct.unpack_from(header_endian + "i", blob, 4)
    env_bytes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 0x7]
    off = 8 + env_bytes
    endian = "<" if blob[off] == 1 else ">"
    (tipo,) = struct.unpack_from(endian + "I", blob, off + 1)
    off += 5
    tipo_base = tipo % 1000       # descarta los bits Z/M de EWKB si los hay
    poligonos = []
    if tipo_base == 3:             # POLYGON
        anillos, off = _leer_poligono(blob, off, endian)
        poligonos.append(anillos)
    elif tipo_base == 6:           # MULTIPOLYGON
        (npoly,) = struct.unpack_from(endian + "I", blob, off)
        off += 4
        for _ in range(npoly):
            e2 = "<" if blob[off] == 1 else ">"
            off += 5               # su propio byte de orden + tipo (ignorado: ya sabemos que es POLYGON)
            anillos, off = _leer_poligono(blob, off, e2)
            poligonos.append(anillos)
    else:
        raise ValueError(f"tipo de geometría no soportado: {tipo}")
    mejor = None
    for anillos in poligonos:
        centro, area = _centroide_de_anillo(anillos[0])
        if mejor is None or area > mejor[1]:
            mejor = (centro, area)
    return mejor[0][0], mejor[0][1], srs_id


def _lon_lat(x: float, y: float, srs_id: int) -> tuple[float, float] | tuple[None, None]:
    """(x, y) del gpkg, en SU srs, a (lon, lat) WGS84 — o (None, None) si el
    SRS no es uno de los dos que estos gpkg usan de verdad (ver docstring de
    `centroide_de_wkb_gpkg`): sin pin es mejor que un pin en el sitio
    equivocado."""
    if srs_id == 4326:
        return x, y
    if 32601 <= srs_id <= 32660:      # UTM norte, WGS84: 326xx = zona xx
        return _utm_a_wgs84(x, y, zona=srs_id - 32600)
    return None, None


# --- Catálogo HDX -------------------------------------------------------

def _conjunto_de(nombre: str, descripcion: str) -> str | None:
    """'overture' | 'google' | 'msft', del nombre/descripción del recurso.

    Orden de prioridad importante: el fichero de Pereira Extended
    `…msft_footprint_reviewed_plus_google_dam_vantor_reviewed.gpkg` contiene
    las palabras «msft» Y «google» a la vez, y el conjunto de huellas es el
    de Microsoft (así lo declara HDX: «Damage assessment on Microsoft
    released building footprints»), no el de Google.
    """
    texto = f"{nombre} {descripcion}".lower()
    if "overture" in texto:
        return "overture"
    if "msft" in texto or "microsoft" in texto:
        return "msft"
    if "google" in texto:
        return "google"
    return None


def _recursos_del_dataset(conn, clave: str, meta: dict) -> list[dict] | None:
    st, data = fetch_json(
        f"{CKAN_PACKAGE_SHOW}?id={meta['ckan_id']}",
        note=f"msft ckan {clave}",
        snapshot_name=f"msft_ckan_{clave}.json", conn=conn)
    resultado = (data or {}).get("result")
    if st != 200 or not resultado:
        return None
    out = []
    for r in resultado.get("resources") or []:
        url = r.get("download_url") or r.get("url")
        if not url:
            continue
        nombre = url.rsplit("/", 1)[-1]
        out.append({
            "resource_id": r.get("id"),
            "dataset_id": resultado.get("id"),
            "nombre": nombre,
            "descripcion": r.get("description") or "",
            "formato": r.get("format"),
            "bytes": r.get("size"),
            "download_url": url,
            "conjunto_huellas": _conjunto_de(nombre, r.get("description") or ""),
        })
    return out


# --- Parseo del gpkg a filas informativas -------------------------------

def _filas_informativas(ruta, resource_id: str, dataset: str, conjunto: str,
                        municipio: str, departamento: str, snap: str):
    """Lee el gpkg fila a fila y devuelve (filas_para_insertar, totales).

    Solo entran a `msft_danos` las filas informativas — ver el docstring del
    módulo para el porqué de escala. El resto del censo solo cuenta.
    """
    conn = sqlite3.connect(str(ruta))
    tabla = conn.execute(
        "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        " LIMIT 1").fetchone()
    if not tabla:
        conn.close()
        return [], {"total_edificios": 0, "total_danados": 0,
                    "total_revisados": 0, "total_desconocidos": 0}
    tabla = tabla[0]
    cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")')}

    def col(nombre):
        return nombre if nombre in cols else None

    campos = ["fid", "geom", "id", "damage_pct_0m", "damage_pct_10m",
              "damage_pct_20m", "built_pct_0m", "damaged", "unknown_pct",
              "confidence", "subtype", "area_in_meters", "review_status",
              "origin", "damage_from", "vantor_pct", "prior_status"]
    seleccion = ", ".join(col(c) or "NULL" for c in campos)
    filas, tot = [], {"total_edificios": 0, "total_danados": 0,
                      "total_revisados": 0, "total_desconocidos": 0}
    for row in conn.execute(f'SELECT {seleccion} FROM "{tabla}"'):
        (fid, geom, huella_id, p0, p10, p20, construido, danado, desconocido,
         confianza, subtipo, area_m2, revision, origen, procedencia,
         pct_vantor, previo) = row
        tot["total_edificios"] += 1
        danado_b = bool(danado)
        revisado_b = revision not in (None, "")
        desconocido_b = desconocido is not None and desconocido >= UMBRAL_NUBE
        if danado_b:
            tot["total_danados"] += 1
        if revisado_b:
            tot["total_revisados"] += 1
        if desconocido_b:
            tot["total_desconocidos"] += 1
        if not (danado_b or revisado_b or desconocido_b):
            continue
        lon = lat = None
        if geom:
            try:
                x, y, srs_id = centroide_de_wkb_gpkg(geom)
                lon, lat = _lon_lat(x, y, srs_id)
            except (ValueError, struct.error):
                pass          # sin geometría legible: la fila entra sin pin
        filas.append((
            resource_id, fid, dataset, conjunto, municipio, departamento,
            str(huella_id) if huella_id is not None else None,
            danado, p0, p10, p20, construido, desconocido, confianza,
            subtipo, area_m2, revision, origen, procedencia, pct_vantor,
            previo, lat, lon, utcnow(), snap))
    conn.close()
    return filas, tot


def _insertar_filas(conn, filas: list[tuple]) -> None:
    for f in filas:
        conn.execute(
            "INSERT INTO msft_danos (resource_id, fid, dataset,"
            " conjunto_huellas, municipio, departamento, huella_id, dano,"
            " pct_dano_0m, pct_dano_10m, pct_dano_20m, pct_construido_0m,"
            " pct_desconocido, confianza, subtipo, area_m2, estado_revision,"
            " origen_geometria, procedencia_dano, pct_vantor, estado_previo,"
            " lat, lon, first_seen, snapshot_date)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(resource_id, fid) DO UPDATE SET"
            "  dano=excluded.dano, pct_dano_0m=excluded.pct_dano_0m,"
            "  pct_dano_10m=excluded.pct_dano_10m,"
            "  pct_dano_20m=excluded.pct_dano_20m,"
            "  pct_construido_0m=excluded.pct_construido_0m,"
            "  pct_desconocido=excluded.pct_desconocido,"
            "  confianza=excluded.confianza, subtipo=excluded.subtipo,"
            "  area_m2=excluded.area_m2,"
            "  estado_revision=excluded.estado_revision,"
            "  origen_geometria=excluded.origen_geometria,"
            "  procedencia_dano=excluded.procedencia_dano,"
            "  pct_vantor=excluded.pct_vantor,"
            "  estado_previo=excluded.estado_previo,"
            "  lat=excluded.lat, lon=excluded.lon,"
            "  snapshot_date=excluded.snapshot_date", f)


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    snap = snapshot_date or today()
    out = {"recursos": 0, "nuevos": 0, "gpkg_parseados": 0,
           "edificios_totales": 0, "filas_informativas": 0, "errores": []}

    manifiesto = manifiesto_r2()
    for clave, meta in DATASETS.items():
        recursos = _recursos_del_dataset(conn, clave, meta)
        if recursos is None:
            out["errores"].append(f"{clave}: catálogo CKAN no disponible")
            continue
        for r in recursos:
            out["recursos"] += 1
            destino = MEDIA / r["nombre"]
            ya = activo_archivado(r["download_url"], conn, destino=destino,
                                  manifiesto=manifiesto)
            if ya:
                sha, ruta = ya["sha256"], ya["ruta"]
            else:
                st, body = fetch(
                    r["download_url"], note=f"msft {clave} {r['nombre']}",
                    conn=conn, retries=1, timeout=180,
                    save_to=destino, condicional=False)
                if st != 200 or not body:
                    out["errores"].append(f"{r['nombre']}: HTTP {st}")
                    continue
                sha = hashlib.sha256(body).hexdigest()
                ruta = str(destino.relative_to(ROOT))
                out["nuevos"] += 1

            ya_parseado = conn.execute(
                "SELECT total_edificios FROM msft_recursos"
                " WHERE resource_id=? AND sha256=?",
                (r["resource_id"], sha)).fetchone()
            es_gpkg = r["nombre"].lower().endswith(".gpkg")
            tot = {"total_edificios": None, "total_danados": None,
                  "total_revisados": None, "total_desconocidos": None}
            if es_gpkg and not ya_parseado:
                try:
                    filas, tot = _filas_informativas(
                        destino, r["resource_id"], clave,
                        r["conjunto_huellas"] or "desconocido",
                        meta["municipio"], meta["departamento"], snap)
                except (sqlite3.DatabaseError, struct.error, ValueError) as exc:
                    out["errores"].append(f"{r['nombre']}: parseo roto ({exc})")
                else:
                    _insertar_filas(conn, filas)
                    out["gpkg_parseados"] += 1
                    out["edificios_totales"] += tot["total_edificios"]
                    out["filas_informativas"] += len(filas)
            elif ya_parseado:
                tot = {"total_edificios": ya_parseado[0]}

            conn.execute(
                "INSERT INTO msft_recursos (resource_id, dataset, dataset_id,"
                " municipio, departamento, nombre, formato, conjunto_huellas,"
                " ubicacion, ruta, sha256, bytes, download_url,"
                " total_edificios, total_danados, total_revisados,"
                " total_desconocidos, first_seen, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "  COALESCE((SELECT first_seen FROM msft_recursos"
                "            WHERE resource_id=?), ?), ?)"
                " ON CONFLICT(resource_id) DO UPDATE SET"
                "  sha256=excluded.sha256, ruta=excluded.ruta,"
                "  bytes=excluded.bytes,"
                "  total_edificios=COALESCE(excluded.total_edificios,"
                "                           msft_recursos.total_edificios),"
                "  total_danados=COALESCE(excluded.total_danados,"
                "                         msft_recursos.total_danados),"
                "  total_revisados=COALESCE(excluded.total_revisados,"
                "                           msft_recursos.total_revisados),"
                "  total_desconocidos=COALESCE(excluded.total_desconocidos,"
                "                              msft_recursos.total_desconocidos),"
                "  snapshot_date=excluded.snapshot_date",
                (r["resource_id"], clave, r["dataset_id"], meta["municipio"],
                 meta["departamento"], r["nombre"], r["formato"],
                 r["conjunto_huellas"],
                 "r2" if r["nombre"].lower().endswith(ARCHIVO_EN_R2) else "git",
                 ruta, sha, r["bytes"], r["download_url"],
                 tot.get("total_edificios"), tot.get("total_danados"),
                 tot.get("total_revisados"), tot.get("total_desconocidos"),
                 r["resource_id"], utcnow(), snap))
            conn.commit()

    out["exportados"] = export(conn)
    if own:
        conn.close()
    return out


def export(conn) -> int:
    """`data/public/msft_damage.geojson` — el subconjunto informativo."""
    feats = []
    for r in conn.execute(
            "SELECT lon, lat, dataset, conjunto_huellas, municipio,"
            " departamento, dano, pct_desconocido, confianza, subtipo,"
            " estado_revision, procedencia_dano"
            " FROM msft_danos WHERE lon IS NOT NULL AND lat IS NOT NULL"
            " ORDER BY dataset, conjunto_huellas, fid"):
        props = {
            "dataset": r[2], "conjunto_huellas": r[3], "municipio": r[4],
            "departamento": r[5], "dano": r[6], "pct_desconocido": r[7],
            "confianza": r[8], "subtipo": r[9], "estado_revision": r[10],
            "procedencia_dano": r[11],
        }
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [r[0], r[1]]},
                      "properties": {k: v for k, v in props.items()
                                     if v not in (None, "")}})
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "msft_damage.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


def resumen(conn) -> dict:
    """Totales por dataset y conjunto de huellas, para los agregados de publish."""
    res: dict = {}
    for dataset, conjunto, total, danados, desconocidos in conn.execute(
            "SELECT dataset, conjunto_huellas, total_edificios,"
            " total_danados, total_desconocidos FROM msft_recursos"
            " WHERE total_edificios IS NOT NULL"):
        res.setdefault(dataset, {})[conjunto] = {
            "edificios": total, "danados": danados,
            "desconocidos": desconocidos}
    return res


if __name__ == "__main__":
    from common import db
    c = db()
    print(json.dumps(run(c), indent=1, ensure_ascii=False))
    print(json.dumps(resumen(c), indent=1, ensure_ascii=False))
