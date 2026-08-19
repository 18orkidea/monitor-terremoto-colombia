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
CREATE TABLE IF NOT EXISTS crosscheck (
  aoi_name TEXT NOT NULL, snapshot_date TEXT NOT NULL,
  estado TEXT NOT NULL,
  copernicus INTEGER, n_prensa INTEGER, n_oficial INTEGER, n_ciudadano INTEGER,
  detalle TEXT,
  PRIMARY KEY (aoi_name, snapshot_date)
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
