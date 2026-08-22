"""Utilidades comunes: HTTP trazable, snapshots inmutables y base de datos.

Regla central del proyecto: toda cifra publicada debe poder rastrearse hasta
una fila de `sources_log` (URL, status, sha256 del cuerpo, timestamp). Por eso
TODA petición HTTP pasa por `fetch()` y ninguna fuente llama a la red por su
cuenta.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "monitor.sqlite"
SNAPSHOTS = DATA / "snapshots"
MEDIA = DATA / "media"
PUBLIC = DATA / "public"

USER_AGENT = "monitor-desastres-colombia/1.0 (proyecto abierto de auditoria de fuentes)"

# Nota canónica de las sondas de `tests/test_supuestos_api.py`: comprueban que
# los contratos externos siguen vivos, no alimentan ninguna cifra publicada.
# Quedan en sources_log (la petición existió) pero sin cuerpo archivado, así
# que el régimen fuerte de trazabilidad las excluye por esta constante — no por
# un prefijo de texto libre. Ninguna fuente de ingesta puede usarla.
NOTA_SONDA = "sonda de supuesto"

# El log no se reescribe: las sondas del 17-ago-2026 quedaron con las notas de
# antes del cambio de nombre y siguen exentas por lo que fueron, no por su texto.
NOTAS_SONDA = (NOTA_SONDA, "test supuesto", "test supuesto rud")

# --- Los otros dos canales por los que entra un cuerpo ------------------------
# Hasta el 21-ago-2026 `sources_log` tenía dos escritores —una petición HTTP o
# una derivación del propio archivo— y un invariante limpio: sin HTTP no hay
# hash ni cuerpo. SERTIT rompió el molde: entrega sus vectores por correo tras
# un formulario, así que hay un cuerpo real, con su sha, que nadie descargó.
# Se marca con una constante y no con texto libre, igual que las sondas: el
# test de trazabilidad exime por contrato explícito, nunca por prefijo.
NOTA_ENTREGA = "entrega fuera de banda"


# --- Corpus de prensa: dónde empieza este desastre ---------------------------
# El sismo ocurrió el 2026-08-10 a las 12:34 UTC. Un titular anterior no habla
# de este terremoto: las búsquedas municipales de Google News devuelven
# histórico y el filtro de palabras clave no puede distinguirlo, porque también
# habla de sismos —de otros sismos—. Medido el 19-ago-2026: 849 de 6.655
# titulares (12,8 %) eran previos, y los 849 llegaban por esa vía; ni uno solo
# por GDACS-EMM ni por los feeds del registro comunitario.
#
# El corte es POR DÍA a propósito: 514 de esos 849 traen la fecha sin hora
# (Google News normaliza los items sin hora a las 07:00:00), así que a nivel de
# instante no habría nada que comparar. Cortar por día no descarta ningún
# titular del propio 10-ago, que es el día que más importa.
#
# Los titulares previos NO se borran: siguen en `news_items`, en los snapshots
# y en `sources_log`. Lo que se corta es su entrada a los productos públicos.
FECHA_SISMO = "2026-08-10"

# El instante de origen, para lo que sí se puede comparar con hora: el check de
# temporalidad de los reportes ciudadanos (R7). 12:34:28 UTC es lo que dicen el
# USGS (us6000tjl2) y el EMSC; hasta el 19-ago-2026 el código llevaba 12:30:00
# redondeado a mano, y el sitio publica esa hora en su JSON-LD. Ningún reporte
# ciudadano cae en esos cuatro minutos, así que corregirlo no reclasifica nada.
INSTANTE_SISMO = f"{FECHA_SISMO}T12:34:28"


def anterior_al_sismo(fecha: str | None) -> bool:
    """¿Consta que el titular es anterior al terremoto?

    Solo se excluye lo que se puede fechar y resulta previo. Un titular sin
    fecha no se descarta: no consta que sea anterior, y tirarlo convertiría una
    ausencia de dato en un juicio (R3 aplicado al corpus, no solo a las cifras).
    """
    return bool(fecha) and str(fecha)[:10] < FECHA_SISMO
# Derivaciones: filas de sources_log que NO son peticiones. Nacen de releer el
# archivo que ya tenemos (p. ej. recuperar el medio de una noticia del
# `<source>` de su snapshot). Se registran para que dentro de veinte años se
# distinga un dato capturado el día de un dato reconstruido después, y llevan
# `http_status`, `sha256`, `bytes` y `snapshot_path` en NULL porque no hubo
# petición ni cuerpo nuevo: la fuente son los snapshots que ya constan.
# Misma disciplina que las sondas: constante, no prefijo de texto libre.
NOTA_RECONSTRUCCION = "reconstrucción de medios desde snapshots"
ORIGEN_ARCHIVO = "repo:data/snapshots/feed_*.xml"


def _ssl_context() -> ssl.SSLContext:
    """Contexto con CA bundle utilizable: certifi si existe, si no el del sistema.
    (El Python de python.org en macOS no encuentra las CAs del sistema por defecto.)"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    try:
        if not ctx.get_ca_certs() and os.path.exists("/etc/ssl/cert.pem"):
            ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    except Exception:
        pass
    return ctx


SSL_CTX = _ssl_context()


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def dia_colombiano_consolidado() -> str:
    """Día colombiano cuyo estado refleja una captura hecha AHORA.

    El RUD es un registro acumulativo que cargan las alcaldías durante su
    jornada: la foto tomada de madrugada en Bogotá no es el día que empieza —
    ese aún no tiene actividad— sino el CIERRE del que acaba de terminar. Con
    `today()` en UTC, una captura a las 00:02 de Bogotá quedaba fechada al día
    siguiente y la serie atribuía a un día lo que se registró en el anterior.

    Corte a las 06:00 de Bogotá: antes, consolida el día previo; después, el día
    en curso. La corrida diaria (10:30 UTC = 05:30 de Bogotá) cae dentro de esa
    ventana, así que fecha el día que acaba de cerrarse sin tocar el cron.
    """
    bogota = datetime.now(timezone.utc) - timedelta(hours=5)
    if bogota.hour < 6:
        bogota -= timedelta(days=1)
    return bogota.strftime("%Y-%m-%d")


def snapshot_dir(day: str | None = None) -> Path:
    d = SNAPSHOTS / (day or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources_log (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  url TEXT NOT NULL,
  http_status INTEGER,
  sha256 TEXT,
  bytes INTEGER,
  snapshot_path TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS activations (
  code TEXT NOT NULL,
  snapshot_date TEXT NOT NULL,
  name TEXT, category TEXT, sub_category TEXT,
  event_time TEXT, activation_time TEXT,
  closed INTEGER, gdacs_id TEXT, countries TEXT,
  centroid_wkt TEXT, extent_wkt TEXT,
  raw_sha256 TEXT,
  PRIMARY KEY (code, snapshot_date)
);
CREATE TABLE IF NOT EXISTS activation_index (
  code TEXT PRIMARY KEY,
  exists_public INTEGER,          -- 1 accesible, 0 hueco (sensible/no asignado)
  name TEXT, category TEXT, countries TEXT, event_time TEXT,
  first_seen TEXT, last_checked TEXT
);
CREATE TABLE IF NOT EXISTS products (
  code TEXT NOT NULL, aoi_name TEXT NOT NULL, aoi_number INTEGER,
  ptype TEXT NOT NULL, monitoring INTEGER, monitoring_number INTEGER,
  version_number INTEGER, status_code TEXT, feasible INTEGER,
  expected_delivery TEXT, delivery_time TEXT,
  download_path TEXT, snapshot_date TEXT NOT NULL,
  PRIMARY KEY (code, aoi_name, ptype, monitoring_number, version_number, snapshot_date)
);
CREATE TABLE IF NOT EXISTS stats (
  code TEXT NOT NULL, aoi_name TEXT NOT NULL,
  ptype TEXT NOT NULL, monitoring_number INTEGER, version_number INTEGER,
  category TEXT NOT NULL, subcategory TEXT NOT NULL,
  unit TEXT,
  total REAL, affected REAL,
  total_raw TEXT, affected_raw TEXT,   -- literal original: "NA" no se pierde
  snapshot_date TEXT NOT NULL,
  PRIMARY KEY (code, aoi_name, ptype, monitoring_number, version_number,
               category, subcategory, snapshot_date)
);
CREATE TABLE IF NOT EXISTS official_events (
  source TEXT NOT NULL, external_id TEXT NOT NULL,
  fecha TEXT, departamento TEXT, municipio TEXT, divipola TEXT,
  evento TEXT, muertos REAL, heridos REAL, desaparecidos REAL,
  personas REAL, familias REAL, viv_destruidas REAL, viv_averiadas REAL,
  vias REAL, acueductos REAL, centros_salud REAL, centros_educativos REAL,
  lat REAL, lon REAL,
  PRIMARY KEY (source, external_id)
);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  aoi_name TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('oficial','institucional','prensa','ciudadano')),
  url TEXT, fuente TEXT, fecha TEXT, cita TEXT,
  capturado_por TEXT NOT NULL,       -- 'auto' | 'manual'
  snapshot_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_volume (
  event_key TEXT NOT NULL, fecha TEXT NOT NULL,
  n_noticias_emm INTEGER, gdelt_vol REAL, n_fuentes INTEGER,
  n_chatmap INTEGER,
  snapshot_date TEXT NOT NULL,
  PRIMARY KEY (event_key, fecha, snapshot_date)
);
CREATE TABLE IF NOT EXISTS citizen_reports (
  origen TEXT NOT NULL, id_externo TEXT NOT NULL,
  ts TEXT, municipio TEXT, divipola TEXT, categoria_edan TEXT,
  lat REAL, lon REAL, lat_pub REAL, lon_pub REAL,
  media_url TEXT, media_local TEXT, media_sha256 TEXT,
  exif_ts TEXT, score INTEGER, checks TEXT,
  validation_status TEXT, estado TEXT,
  mensaje TEXT,
  snapshot_date TEXT NOT NULL,
  PRIMARY KEY (origen, id_externo)
);
CREATE TABLE IF NOT EXISTS news_items (
  url TEXT PRIMARY KEY,
  feed_id TEXT NOT NULL,
  fecha TEXT, titulo TEXT, medio TEXT,
  -- `medio` guarda el nombre del FEED («Google News — Nóvita»), no el del
  -- medio: contarlo como cabecera infla cualquier métrica de pluralidad. El
  -- medio real lo declara el propio RSS en <source url="...">Nombre</source>
  -- y vive en estas dos columnas. `medio` se conserva tal cual porque es lo
  -- que se capturó, y el archivo no se reescribe.
  medio_canonico TEXT, medio_dominio TEXT,
  snapshot_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rud_daily (
  snapshot_date TEXT NOT NULL,
  departamento TEXT NOT NULL, municipio TEXT NOT NULL,
  familias REAL, personas REAL,
  viv_destruidas REAL, viv_averiadas REAL,
  habitables REAL, nohabitables REAL,
  PRIMARY KEY (snapshot_date, departamento, municipio)
);
-- UNITAR-UNOSAT: la segunda mirada satelital. Los productos y sus paquetes
-- de shapefiles; el dato se indexa por sha del paquete y NO por producto,
-- porque varios productos publican el mismo ZIP y el edificio es uno solo.
CREATE TABLE IF NOT EXISTS unosat_products (
  product_id INTEGER PRIMARY KEY,
  glide TEXT, titulo TEXT,
  descripcion TEXT,                -- «SUMMARY OF FINDING»: para el epicentro es
                                   -- el único sitio donde vive el análisis
  created_at TEXT,
  lat REAL, lon REAL,
  pdf_url TEXT, shp_url TEXT, gdb_url TEXT, xlsx_url TEXT, web_url TEXT,
  shp_sha256 TEXT,                 -- qué paquete publica (identidad real)
  fuentes_texto TEXT,              -- bloque «Data sources» tal cual lo escribe
  first_seen TEXT, snapshot_date TEXT
);
CREATE TABLE IF NOT EXISTS unosat_damage (
  paquete_sha TEXT NOT NULL,       -- sha256 del ZIP que contiene el registro
  capa TEXT NOT NULL,              -- shapefile de origen, con sensor y fecha
  idx INTEGER NOT NULL,            -- nº de registro dentro de la capa
  productos TEXT,                  -- ids UNOSAT que declaran este paquete
  municipio TEXT, departamento TEXT,
  departamento_origen TEXT,        -- 'catalogo' | 'titulo_unosat': de dónde sale
                                   -- el departamento, porque uno es dato y el
                                   -- otro una inferencia sobre el título
  sensor TEXT, sensor_date TEXT,
  dano TEXT, dano_agrupado TEXT,
  confianza TEXT, validacion_campo TEXT,
  event_code TEXT,                 -- literal de la fuente, aunque contradiga
  notas TEXT,
  lat REAL, lon REAL,
  first_seen TEXT, snapshot_date TEXT NOT NULL,
  PRIMARY KEY (paquete_sha, capa, idx)
);
CREATE TABLE IF NOT EXISTS crosscheck (
  aoi_name TEXT NOT NULL, snapshot_date TEXT NOT NULL,
  estado TEXT NOT NULL,
  copernicus INTEGER, n_prensa INTEGER, n_oficial INTEGER, n_ciudadano INTEGER,
  detalle TEXT,
  PRIMARY KEY (aoi_name, snapshot_date)
);
-- ICube-SERTIT, tercera mirada satelital, vía Charter 1048 (call 1202).
-- El catálogo SÍ se descarga (la web publica sus metadatos); los VECTORES no:
-- la web los entrega por correo tras un formulario con datos personales, así
-- que el cuerpo vive en data/documentos/sertit/ y su fila de sources_log dice
-- por dónde llegó. Ver el docstring de ingest/sources/sertit.py.
CREATE TABLE IF NOT EXISTS sertit_productos (
  producto_id INTEGER PRIMARY KEY,
  accion_id INTEGER, charter TEXT,
  n_producto TEXT,                 -- '01'…'05', numeración del propio SERTIT
  nombre_base TEXT,                -- nomAnnexes: lleva AOI, escala y fecha
  municipio TEXT, departamento TEXT,
  municipio_origen TEXT,           -- 'catalogo' | 'texto_sertit': un municipio
                                   -- del catálogo y uno leído de un rótulo no
                                   -- pueden ser indistinguibles
  escala INTEGER, formato TEXT, tipo TEXT,
  imagen_principal TEXT,           -- literal: «Pléiades Néo acquise le …»
  fecha_produccion TEXT,
  url_producto TEXT,               -- su página de producto; alimenta Wayback
  url_mapa TEXT,                   -- el PDF/JPG público en el portal de la
                                   -- Charter, verificado uno a uno el 20-ago
  cifra_rotulada INTEGER,          -- lo que el MAPA dice en su leyenda, que no
                                   -- siempre cuadra con sus propios vectores
  bbox_declarado TEXT,             -- el recuadro que publica su web, en JSON
  area_analizada_km2 REAL,         -- del AreaOfInterest del paquete, no del bbox
  paquete_sha256 TEXT, paquete_ruta TEXT,
  first_seen TEXT, snapshot_date TEXT
);
CREATE TABLE IF NOT EXISTS sertit_danos (
  paquete_sha TEXT NOT NULL,       -- sha256 del ZIP: la identidad del dato
  capa TEXT NOT NULL,              -- UrbanP, PointOfInterest…
  idx INTEGER NOT NULL,
  producto_id INTEGER,
  municipio TEXT, departamento TEXT,
  dano TEXT,                       -- literal de la fuente; comparte vocabulario
                                   -- con Copernicus (Destroyed/Damaged/…)
  tipo TEXT,                       -- Residential, Public…
  sensor TEXT, sensor_date TEXT,
  metodo TEXT,                     -- 'Photo-interpretation'
  copyright TEXT,                  -- «© ICube-SERTIT 2026»: la licencia obliga
  lat REAL, lon REAL,
  first_seen TEXT, snapshot_date TEXT NOT NULL,
  PRIMARY KEY (paquete_sha, capa, idx)
);
"""


MIGRACIONES = [
    # (tabla, columna, tipo). `CREATE TABLE IF NOT EXISTS` no toca una tabla
    # que ya existe: sin esto, una columna nueva solo aparecería en las bases
    # recién creadas y faltaría en la del runner, que arrastra meses de datos.
    ("news_items", "medio_canonico", "TEXT"),
    ("news_items", "medio_dominio", "TEXT"),
]


def migrar(conn: sqlite3.Connection) -> list[str]:
    """Añade las columnas que el esquema declara y la base todavía no tiene.

    Solo añade: renombrar o borrar columnas está prohibido sin migración de los
    dumps (ver CLAUDE.md). Idempotente — se ejecuta en cada `db()`.
    """
    hechas = []
    for tabla, columna, tipo in MIGRACIONES:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}
        if columna in cols:
            continue
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
        hechas.append(f"{tabla}.{columna}")
    if hechas:
        conn.commit()
    return hechas


def db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # escritores concurrentes
    except sqlite3.OperationalError:
        pass  # otro proceso con journal clásico aún abierto; WAL entrará después
    conn.executescript(SCHEMA)
    migrar(conn)
    return conn


def registrar_derivacion(conn: sqlite3.Connection, url: str, note: str) -> None:
    """Anota en `sources_log` un dato derivado del propio archivo, sin red.

    R4 exige que toda cifra publicada tenga fila en el log; hasta ahora todas
    venían de `fetch()`. Una reconstrucción no es una petición, pero tampoco
    puede quedar sin constar: sin esta fila, un lector futuro no sabría si un
    valor se capturó o se dedujo. No hace commit — va en la transacción de
    quien deriva, para que o conste todo o no conste nada.
    """
    conn.execute(
        "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
        " snapshot_path,note) VALUES (?,?,NULL,NULL,NULL,NULL,?)",
        (utcnow(), url, note))


def registrar_entrega(conn: sqlite3.Connection, *, url: str, ruta: Path,
                      note: str) -> str:
    """Anota un cuerpo que llegó por un canal que no es HTTP (correo, mano).

    R4 exige que toda cifra publicada tenga fila en `sources_log` con su sha y
    su cuerpo recuperable. `fetch()` cubre lo que se descarga; esto cubre lo
    que un organismo ENTREGA tras una petición formal — el caso de los
    vectores de ICube-SERTIT, que su web solo manda por correo después de un
    formulario con datos personales. Sin esta fila, el dato más valioso del
    archivo sería el único sin constancia de por dónde entró.

    `note` debe decir el canal y la fecha de la petición, no solo el nombre de
    la fuente: dentro de años, «llegó por correo» es la mitad de la respuesta.
    Devuelve el sha256 del fichero. No hace commit.
    """
    body = ruta.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    conn.execute(
        "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
        " snapshot_path,note) VALUES (?,?,NULL,?,?,?,?)",
        (utcnow(), url, sha, len(body), str(ruta.relative_to(ROOT)),
         f"{NOTA_ENTREGA}: {note}"))
    return sha


def fetch(url: str, params: dict | None = None, *, note: str = "",
          snapshot_name: str | None = None, timeout: int = 60,
          retries: int = 2, retry_wait: float = 5.0,
          binary: bool = False, conn: sqlite3.Connection | None = None,
          save_to: Path | None = None, max_save_bytes: int | None = None):
    """GET con registro en sources_log y snapshot opcional.

    Devuelve (status, body_bytes). No lanza en HTTP != 200: el llamante decide
    (los huecos EMSR son normales, no errores).

    Snapshots inmutables e intradía: el primer cuerpo del día conserva el
    nombre canónico (los lectores lo esperan); un cuerpo DISTINTO el mismo día
    se archiva aparte con sufijo de contenido (_sha8) — jamás queda un sha256
    en el log sin cuerpo recuperable, jamás se sobrescribe nada. `binary` se
    conserva por compatibilidad pero ya no cambia el comportamiento.

    `save_to` persiste el cuerpo fuera de snapshots (p. ej. medios ciudadanos
    en data/media/) y lo registra como snapshot_path; `max_save_bytes` limita
    qué se guarda (lo que exceda queda logueado sin cuerpo, con nota).
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    body, status, err = b"", 0, None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                status, body = r.status, r.read()
            break
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read() or b""
            if status in (429, 500, 502, 503) and attempt < retries:
                time.sleep(retry_wait * (attempt + 1))
                continue
            break
        except Exception as e:  # red caída, timeout…
            err = str(e)
            if attempt < retries:
                time.sleep(retry_wait * (attempt + 1))
                continue
            status = -1
    sha = hashlib.sha256(body).hexdigest() if body else None
    spath = None
    if status == 200 and body:
        if save_to is not None:
            if max_save_bytes is None or len(body) <= max_save_bytes:
                save_to.parent.mkdir(parents=True, exist_ok=True)
                if not save_to.exists():
                    save_to.write_bytes(body)
                spath = str(save_to.relative_to(ROOT))
        elif snapshot_name:
            p = snapshot_dir() / snapshot_name
            if not p.exists():
                p.write_bytes(body)
            elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
                stem, dot, ext = snapshot_name.rpartition(".")
                nombre = f"{stem}_{sha[:8]}.{ext}" if dot else f"{snapshot_name}_{sha[:8]}"
                p = snapshot_dir() / nombre
                if not p.exists():
                    p.write_bytes(body)
            spath = str(p.relative_to(ROOT))
    own = conn is None
    c = conn or db()
    c.execute(
        "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,snapshot_path,note)"
        " VALUES (?,?,?,?,?,?,?)",
        (utcnow(), url, status, sha, len(body), spath, note or err),
    )
    if own:
        c.commit()
        c.close()
    return status, body


def notificar(url: str, payload: dict, *, note: str = "", timeout: int = 30,
              conn: sqlite3.Connection | None = None):
    """POST de aviso (no trae datos) con la misma trazabilidad que `fetch()`.

    R4 exige que ninguna petición HTTP quede fuera de `sources_log`, y hasta
    ahora todas eran GET de fuentes. Avisar a un buscador de que publicamos algo
    también es una petición que hicimos: se registra igual, con el sha256 del
    cuerpo ENVIADO —lo que se archiva aquí es lo que dijimos, no lo que nos
    respondieron— y sin snapshot, porque el cuerpo ya está en el propio log.

    No lanza: un buscador caído no puede tumbar una corrida diaria (R13).
    """
    cuerpo = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=cuerpo, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json; charset=utf-8"})
    status, err = 0, None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status, err = -1, str(e)
    own = conn is None
    c = conn or db()
    c.execute(
        "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,snapshot_path,note)"
        " VALUES (?,?,?,?,?,NULL,?)",
        (utcnow(), url, status, hashlib.sha256(cuerpo).hexdigest(), len(cuerpo),
         note or err),
    )
    if own:
        c.commit()
        c.close()
    return status


def fetch_json(url: str, params: dict | None = None, **kw):
    status, body = fetch(url, params, **kw)
    if status != 200 or not body:
        return status, None
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, None


def to_num(v):
    """Convierte los valores de stats de Copernicus. "NA"/None/"-" → None, nunca 0."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "NA", "-", "None", "null"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None
