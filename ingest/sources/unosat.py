"""UNITAR-UNOSAT: evaluación de daños del Centro Satelital de la ONU.

Qué aporta que no tenga nadie más: cartografía de daño **edificio a edificio**
en municipios que Copernicus EMS no cartografía. Las seis AOI de detalle de
Copernicus están en Valle del Cauca, Risaralda y Chocó; UNOSAT mira Caldas.
Es la segunda mirada satelital independiente del monitor, y por tanto la
primera vez que dos satélites pueden discrepar entre sí.

URL base: https://unosat.org — sin API documentada ni clave. Dos endpoints
que sirven JSON y que este módulo usa:
  - `our_products/`      listado de los productos MÁS RECIENTES (ver límite)
  - `our_products/<id>`  detalle, con enlaces a PDF, SHP y GDB
Los productos se agrupan por GLIDE; el del terremoto es EQ20260810COL.

Lo que la fuente NO garantiza:
  - **El listado es una ventana fija de 11 productos**, de todos los eventos
    del mundo, sin paginación ni filtro (probados `page`, `limit`, `offset`,
    `glide`, `country`: los cinco devuelven lo mismo). El día que UNOSAT
    publique 11 productos de otros eventos, el terremoto desaparece de él.
    Por eso la corrida consulta también los ids ya conocidos en la base: una
    vez visto, un producto no se pierde aunque salga de la ventana.
  - Licencia no declarada en el JSON; el pie de los productos remite a
    https://www.unitar.org/legal.
  - El shapefile es **acumulativo por evento y compartido entre productos**:
    los ZIP de 4251, 4252 y 4253 son byte a byte idénticos (mismo sha256).
    Se descargan todos —cada descarga es una fila de sources_log, y esa
    duplicación es en sí un dato sobre cómo publica la fuente— pero el
    cuerpo se archiva una sola vez: `fetch()` reconoce el sha repetido y no
    reescribe el snapshot. Los datos se deduplican por sha del paquete, así
    que un edificio declarado por tres productos es UNA fila.
  - El ZIP no contiene necesariamente lo que anuncia el producto que lo
    enlaza: el de 4253 (San José del Palmar, el epicentro) trae Anserma,
    Manizales y Viterbo, y del epicentro solo se publica el PDF.

Plan de sucesión (si unosat.org muere mañana):
  - Sobreviven en el repo los snapshots diarios del listado, del detalle de
    cada producto y del ZIP completo de shapefiles — con eso se reconstruye
    la capa entera sin la fuente.
  - Export dedicado versionado: `data/public/unosat_damage.geojson`, que es
    lo que lee el sitio y lo que un tercero puede reutilizar.
  - Merece Wayback: los PDF de evaluación son el único sitio donde vive el
    análisis del epicentro, y no se archivan aquí (son de 1,6 MB y no
    aportan geometría). Pendiente en docs/LIMITACIONES.md.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

from common import fetch, fetch_json, utcnow, today, PUBLIC
from municipios import MUNICIPIOS
import shapefile

BASE = "https://unosat.org"
LISTADO = f"{BASE}/our_products/"
GLIDE = "EQ20260810COL"

# Capas del paquete que interesan. UNOSAT nombra los ficheros
# <Sensor>_<AAAAMMDD>_<Capa>_<Municipio>, y de ahí sale el municipio: el
# campo `Settlement` del dbf viene vacío en los tres shapefiles publicados.
CAPA_DANO = "BuildingDamageAsessment"      # sic: la fuente escribe "Asessment"
# El paquete trae también capas `AnalysedArea` —el polígono que UNOSAT sí
# miró, equivalente a las «zonas sin analizar» de Copernicus— que aún no se
# ingieren: harían falta para medir su cobertura, no solo sus hallazgos.


def _municipio_de_capa(base: str) -> str | None:
    """Municipio a partir del nombre del shapefile.

    Coincidencia EXACTA contra el índice del monitor, nunca por subcadena:
    «Anserma» es un prefijo de «Ansermanuevo», que es otro municipio y de otro
    departamento (R10). Si no hay coincidencia, se devuelve el literal de la
    fuente separando CamelCase, y el municipio queda como desconocido para el
    cruce pero visible en el mapa.
    """
    cola = base.rsplit("_", 1)[-1]
    if not cola:
        return None
    for nombre in MUNICIPIOS:
        if _norm(nombre) == _norm(cola):
            return nombre
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cola)


def _norm(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower().replace(" ", "")


def _departamentos_de_titulos(conn) -> dict[str, str]:
    """{municipio: departamento} deducido de los títulos de los productos.

    UNOSAT titula «… in Viterbo Town, Caldas Department, Colombia», y ese es
    el único sitio donde declara el departamento: el dbf no lo trae. Sirve
    para los municipios que el monitor aún no sigue —Viterbo no está entre
    los 109—, sin inventar nada: si el título no lo dice, se queda en None.
    """
    out = {}
    for (titulo,) in conn.execute(
            "SELECT titulo FROM unosat_products WHERE glide=? AND titulo IS NOT NULL",
            (GLIDE,)):
        m = re.search(r"\bin\s+(.+?)\s+Town,\s*(.+?)\s+Department\b", titulo,
                      re.IGNORECASE)
        if m:
            out[_norm(m.group(1))] = m.group(2).strip()
    return out


def _campo(props: dict, *nombres):
    """Primer campo no vacío de entre varios alias.

    Los shapefiles de UNOSAT no comparten esquema: Viterbo prefija sus
    columnas con `d_` (`d_Main_Dam`) y Anserma/Manizales no (`Main_Dmg`).
    Leer por alias evita que media capa quede sin daño por un nombre.
    """
    for n in nombres:
        v = props.get(n)
        if v not in (None, ""):
            return v
    return None


def _paquete(zbytes: bytes, deptos: dict[str, str] | None = None) -> list[dict]:
    """Puntos de daño de un ZIP de shapefiles, ya normalizados."""
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    nombres = z.namelist()
    out = []
    for shp in sorted(n for n in nombres if n.lower().endswith(".shp")):
        base = shp[:-4]
        if CAPA_DANO not in base:
            continue
        dbf = next((n for n in nombres
                    if n[:-4] == base and n.lower().endswith(".dbf")), None)
        prj = next((n for n in nombres
                    if n[:-4] == base and n.lower().endswith(".prj")), None)
        if not dbf:
            continue
        if prj and not shapefile.es_geografico(z.read(prj).decode("latin-1")):
            continue          # proyectado: sin reproyectar no se puede mapear
        cpg = next((n for n in nombres
                    if n[:-4] == base and n.lower().endswith(".cpg")), None)
        enc = (z.read(cpg).decode("ascii", "ignore").strip() or "utf-8") \
            if cpg else "utf-8"
        municipio = _municipio_de_capa(base)
        for i, f in enumerate(shapefile.leer(z.read(shp), z.read(dbf),
                                             encoding=enc)):
            if f["geometry"]["type"] != "Point":
                continue
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"]
            out.append({
                "capa": base.split("/")[-1], "idx": i,
                "municipio": municipio,
                # el índice del monitor manda; si no conoce el municipio,
                # vale el departamento que la propia UNOSAT declara
                "departamento": (MUNICIPIOS.get(municipio) or {}).get(
                    "departamento")
                    or (deptos or {}).get(_norm(municipio or "")),
                "sensor": _campo(p, "SensorID", "Sensor_ID", "d_SensorID"),
                "sensor_date": _campo(p, "SensorDate"),
                "dano": _campo(p, "Main_Dmg", "d_Main_Dam", "Main_Damag"),
                "dano_agrupado": _campo(p, "Grouped_Da", "d_Grouped_"),
                "confianza": _campo(p, "Confidence", "d_Confiden"),
                "validacion_campo": _campo(p, "FieldValid", "d_FieldVal"),
                "event_code": _campo(p, "EventCode"),
                "notas": _campo(p, "Notes"),
                "lat": lat, "lon": lon,
            })
    return out


def _productos_del_evento(conn) -> list[int]:
    """Ids del evento: los del listado vivo MÁS los ya conocidos en la base.

    La unión es lo que protege el histórico: el listado solo enseña los 11
    productos más recientes del mundo, así que un producto del terremoto se
    cae de él en cuanto UNOSAT publica de otros eventos. Lo ya visto se
    vuelve a pedir por id, que sí es direccionable para siempre.
    """
    st, data = fetch_json(LISTADO, note="unosat listado",
                          snapshot_name="unosat_products.json", conn=conn)
    ids = set()
    for p in (data or {}).get("products") or []:
        m = p.get("map_event") or {}
        if (m.get("glide") or "").upper() == GLIDE and m.get("id"):
            ids.add(int(m["id"]))
    conocidos = {r[0] for r in conn.execute(
        "SELECT product_id FROM unosat_products WHERE glide=?", (GLIDE,))}
    return sorted(ids | conocidos)


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    snap = snapshot_date or today()
    out = {"productos": 0, "nuevos": 0, "paquetes": 0, "puntos": 0,
           "duplicados": 0, "sin_shapefile": []}

    ids = _productos_del_evento(conn)
    # Dos fases a propósito: primero se descarga y se registra TODO, y solo
    # después se parsean los paquetes. El departamento de un municipio que el
    # monitor no sigue sale del título de los productos, así que no puede
    # leerse hasta que estén todos guardados — en un clon nuevo, hacerlo
    # dentro del bucle dejaría a Viterbo sin departamento el primer día.
    crudos: dict[str, bytes] = {}             # sha256 del ZIP → cuerpo
    declaran: dict[str, list[int]] = {}       # sha256 del ZIP → productos

    for pid in ids:
        st, det = fetch_json(f"{BASE}/our_products/{pid}",
                             note=f"unosat producto {pid}",
                             snapshot_name=f"unosat_product_{pid}.json",
                             conn=conn)
        m = (det or {}).get("map_event") or {}
        if not m:
            continue
        out["productos"] += 1
        nuevo = conn.execute("SELECT 1 FROM unosat_products WHERE product_id=?",
                             (pid,)).fetchone() is None
        out["nuevos"] += int(nuevo)

        shp_url = (m.get("shp_link") or "").strip()
        shp_url = (BASE + shp_url) if shp_url.startswith("/") else shp_url
        shp_sha = None
        if shp_url and shp_url.lower().endswith(".zip"):
            # snapshot_name COMPARTIDO a propósito: los ZIP de varios productos
            # son idénticos y fetch() no reescribe un cuerpo con el mismo sha,
            # así que el paquete se archiva una vez y las tres descargas quedan
            # igualmente registradas en sources_log.
            st_z, body = fetch(shp_url, note=f"unosat shapefiles {pid}",
                               snapshot_name="unosat_shapefiles.zip", conn=conn)
            if st_z == 200 and body:
                shp_sha = hashlib.sha256(body).hexdigest()
                declaran.setdefault(shp_sha, []).append(pid)
                if shp_sha in crudos:
                    out["duplicados"] += 1       # mismo paquete, otro producto
                else:
                    crudos[shp_sha] = body
        else:
            out["sin_shapefile"].append(pid)

        conn.execute(
            "INSERT INTO unosat_products (product_id, glide, titulo, created_at,"
            " lat, lon, pdf_url, shp_url, gdb_url, web_url, shp_sha256,"
            " fuentes_texto, first_seen, snapshot_date)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,"
            "  COALESCE((SELECT first_seen FROM unosat_products"
            "            WHERE product_id=?), ?), ?)"
            " ON CONFLICT(product_id) DO UPDATE SET"
            "  titulo=excluded.titulo, created_at=excluded.created_at,"
            "  shp_url=excluded.shp_url, shp_sha256=excluded.shp_sha256,"
            "  snapshot_date=excluded.snapshot_date",
            (pid, (m.get("glide") or "").upper(), m.get("title"),
             m.get("created_at"), (det or {}).get("latitude"),
             (det or {}).get("longitude"),
             _abs(m.get("pdf_name") and
                  f"/static/unosat_filesystem/{pid}/{m['pdf_name']}"),
             shp_url or None, _abs(m.get("gdp_link")), m.get("wmap_link") or None,
             shp_sha, m.get("sources"), pid, utcnow(), snap))

    conn.commit()

    # ---- segunda fase: parsear los paquetes ya con los títulos disponibles
    deptos = _departamentos_de_titulos(conn)
    paquetes: dict[str, list[dict]] = {}
    for sha, body in crudos.items():
        try:
            paquetes[sha] = _paquete(body, deptos)
            out["paquetes"] += 1
        except (zipfile.BadZipFile, ValueError, KeyError, IndexError) as exc:
            paquetes[sha] = []
            out.setdefault("errores", []).append(f"{sha[:8]}: {exc}")

    # ---- puntos: una fila por edificio y paquete, no por producto
    for sha, puntos in paquetes.items():
        prods = ",".join(str(x) for x in sorted(declaran.get(sha, [])))
        for pt in puntos:
            conn.execute(
                "INSERT INTO unosat_damage (paquete_sha, capa, idx, productos,"
                " municipio, departamento, sensor, sensor_date, dano,"
                " dano_agrupado, confianza, validacion_campo, event_code, notas,"
                " lat, lon, first_seen, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "  COALESCE((SELECT first_seen FROM unosat_damage"
                "            WHERE paquete_sha=? AND capa=? AND idx=?), ?), ?)"
                # La tabla guarda el estado ACTUAL de la fuente: si UNOSAT
                # corrige un grado de daño, aquí se refleja. El estado de cada
                # día anterior no se pierde — vive en los snapshots del ZIP,
                # que son inmutables. `first_seen` sí se conserva.
                " ON CONFLICT(paquete_sha, capa, idx) DO UPDATE SET"
                "  productos=excluded.productos,"
                "  municipio=excluded.municipio,"
                "  departamento=excluded.departamento,"
                "  sensor=excluded.sensor, sensor_date=excluded.sensor_date,"
                "  dano=excluded.dano, dano_agrupado=excluded.dano_agrupado,"
                "  confianza=excluded.confianza,"
                "  validacion_campo=excluded.validacion_campo,"
                "  event_code=excluded.event_code, notas=excluded.notas,"
                "  lat=excluded.lat, lon=excluded.lon,"
                "  snapshot_date=excluded.snapshot_date",
                (sha, pt["capa"], pt["idx"], prods, pt["municipio"],
                 pt["departamento"], pt["sensor"], pt["sensor_date"],
                 pt["dano"], pt["dano_agrupado"], pt["confianza"],
                 pt["validacion_campo"], pt["event_code"], pt["notas"],
                 pt["lat"], pt["lon"],
                 sha, pt["capa"], pt["idx"], utcnow(), snap))
            out["puntos"] += 1

    conn.commit()
    out["municipios"] = sorted({p["municipio"] for ps in paquetes.values()
                                for p in ps if p["municipio"]})
    export(conn)
    if own:
        conn.close()
    return out


def _abs(path: str | None) -> str | None:
    if not path:
        return None
    return (BASE + path) if path.startswith("/") else path


def export(conn) -> int:
    """`data/public/unosat_damage.geojson` — lo que lee el mapa.

    Sale de la base, no de los paquetes en memoria: así el export sobrevive a
    una corrida en la que unosat.org no responda (R13).
    """
    feats = []
    for r in conn.execute(
            "SELECT lon, lat, municipio, departamento, dano, dano_agrupado,"
            " sensor, sensor_date, confianza, validacion_campo, event_code,"
            " notas, productos, capa FROM unosat_damage"
            " WHERE lon IS NOT NULL AND lat IS NOT NULL"
            " ORDER BY municipio, capa, idx"):
        props = {
            "municipio": r[2], "departamento": r[3],
            "dano": r[4], "dano_agrupado": r[5],
            "sensor": r[6], "sensor_date": r[7],
            "confianza": r[8], "validacion_campo": r[9],
            "event_code": r[10], "notas": r[11],
            "productos": r[12], "capa": r[13],
        }
        # Un campo sin dato NO viaja al geojson: el globo del mapa no puede
        # pintar «Confianza: —» y hacer creer que la fuente dijo algo.
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [r[0], r[1]]},
                      "properties": {k: v for k, v in props.items()
                                     if v not in (None, "")}})
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "unosat_damage.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


def resumen(conn) -> dict:
    """Conteo por municipio y grado, para el sitio y el cruce."""
    res: dict = {}
    for muni, dano, n in conn.execute(
            "SELECT municipio, dano, COUNT(*) FROM unosat_damage"
            " GROUP BY municipio, dano"):
        res.setdefault(muni or "—", {})[dano or "Sin grado"] = n
    return res


if __name__ == "__main__":
    from common import db
    c = db()
    print(json.dumps(run(c), indent=1, ensure_ascii=False))
    print(json.dumps(resumen(c), indent=1, ensure_ascii=False))
