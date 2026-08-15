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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "monitor.sqlite"
SNAPSHOTS = DATA / "snapshots"
MEDIA = DATA / "media"
PUBLIC = DATA / "public"

USER_AGENT = "monitor-desastres-colombia/1.0 (proyecto abierto de auditoria de fuentes)"


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
  snapshot_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crosscheck (
  aoi_name TEXT NOT NULL, snapshot_date TEXT NOT NULL,
  estado TEXT NOT NULL,
  copernicus INTEGER, n_prensa INTEGER, n_oficial INTEGER, n_ciudadano INTEGER,
  detalle TEXT,
  PRIMARY KEY (aoi_name, snapshot_date)
);
"""


def db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # escritores concurrentes
    except sqlite3.OperationalError:
        pass  # otro proceso con journal clásico aún abierto; WAL entrará después
    conn.executescript(SCHEMA)
    return conn


def fetch(url: str, params: dict | None = None, *, note: str = "",
          snapshot_name: str | None = None, timeout: int = 60,
          retries: int = 2, retry_wait: float = 5.0,
          binary: bool = False, conn: sqlite3.Connection | None = None):
    """GET con registro en sources_log y snapshot opcional.

    Devuelve (status, body_bytes). No lanza en HTTP != 200: el llamante decide
    (los huecos EMSR son normales, no errores).
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
    if snapshot_name and status == 200 and body:
        p = snapshot_dir() / snapshot_name
        if not binary and not p.exists():
            p.write_bytes(body)
        elif binary:
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
