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

# Días en que `rud_daily` no tiene fila propia, con su porqué — mismo patrón
# que `municipios.py::NOMBRE_A_SECAS_CONGELADO`: una lista mantenida a mano
# porque decide un hecho, no una regla derivable del dato. El 26-ago-2026 el
# cron de GitHub disparó con 3.5 h de retraso y `dia_colombiano_consolidado()`
# etiquetó esa captura como 27-ago (ver su docstring y docs/DECISIONES.md); la
# decisión editorial fue dejar el hueco implícito en la serie, no reconstruirlo
# sin evidencia (R11/R16). `tests/test_unit.py::test_no_hay_dias_perdidos_entre_capturas`
# y `ingest/alerts.py` leen esto para no tratar un hueco ya explicado como uno
# nuevo por descubrir.
HUECOS_RUD_CONOCIDOS = {
    "2026-08-26": "cron de GitHub retrasado 3.5 h el 27-ago; la captura de "
                  "ese día se etiquetó '27-ago' en vez de '26-ago' — blindado "
                  "en dia_colombiano_consolidado(), hueco dejado implícito "
                  "por decisión editorial (docs/DECISIONES.md, 28-ago-2026)",
}


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


def dia_colombiano_consolidado(conn: sqlite3.Connection | None = None) -> str:
    """Día colombiano cuyo estado refleja una captura hecha AHORA.

    El RUD es un registro acumulativo que cargan las alcaldías durante su
    jornada: la foto tomada de madrugada en Bogotá no es el día que empieza —
    ese aún no tiene actividad— sino el CIERRE del que acaba de terminar. Con
    `today()` en UTC, una captura a las 00:02 de Bogotá quedaba fechada al día
    siguiente y la serie atribuía a un día lo que se registró en el anterior.

    Corte a las 06:00 de Bogotá: antes, consolida el día previo; después, el día
    en curso. La corrida diaria (10:17 UTC ≈ 05:17 de Bogotá, `daily.yml`) cae
    dentro de esa ventana, así que fecha el día que acaba de cerrarse sin
    tocar el cron.

    Blindaje (28-ago-2026): esto asume que la corrida siempre se ejecuta
    dentro de esa ventana. El 27-ago GitHub disparó el cron con 3.5 h de
    retraso (14:11 UTC = 09:11 Bogotá, ya pasado el corte); la hora de reloj
    ya no restaba un día y la captura que debía consolidar el 26-ago se
    etiquetó como 27-ago — el 26 quedó sin fila en `rud_daily`, un hueco
    documentado en docs/DECISIONES.md y HUECOS_RUD_CONOCIDOS (ver
    `test_no_hay_dias_perdidos_entre_capturas`).

    Segunda vuelta (28-ago-2026, revisión de archivista): la primera versión
    de este blindaje corregía CUALQUIER salto de más de un día saltando
    directo a "último capturado + 1", sin mirar si la corrida de hoy llegó
    tarde o a su hora. Eso rompía el caso de una corrida enteramente
    perdida (GitHub caído un día completo, no solo tarde): la corrida
    SIGUIENTE, a su hora, calcula bien "ayer" por sí sola —lleva la hora
    correcta, no la firma del cron tardío— y no hace falta tocarla. Forzarla
    a "último+1" le habría robado la fecha real a una captura verdadera y
    dejado un hueco MUDO que ni `huecos_de_captura` ni
    `colision_de_etiquetado_rud` (`ingest/alerts.py`) detectan, porque la
    serie queda contigua — solo que mintiendo sobre qué día es cada fila.

    La corrección ahora exige DOS condiciones: que la corrida lleve la firma
    del cron tardío (hora de Bogotá ≥ 6, la que causó el hueco del 26-ago) Y
    que el salto contra `MAX(snapshot_date)` sea de más de un día. Cuando
    las dos se cumplen, retrocede COMO MUCHO un día desde lo que propuso el
    reloj —nunca varios de golpe—: si detrás de ese único día sigue
    faltando más (una corrida perdida antes de esta), lo que queda es un
    hueco real, y se deja que `huecos_de_captura` lo avise en alta en vez
    de rellenarlo en silencio."""
    bogota = datetime.now(timezone.utc) - timedelta(hours=5)
    tarde = bogota.hour >= 6
    if not tarde:
        bogota -= timedelta(days=1)
    dia = bogota.strftime("%Y-%m-%d")
    if conn is not None and tarde:
        fila = conn.execute("SELECT MAX(snapshot_date) FROM rud_daily").fetchone()
        ultimo = fila[0] if fila else None
        if ultimo:
            ultimo_d = datetime.strptime(ultimo, "%Y-%m-%d").date()
            propuesto_d = datetime.strptime(dia, "%Y-%m-%d").date()
            if (propuesto_d - ultimo_d).days > 1:
                dia = (propuesto_d - timedelta(days=1)).strftime("%Y-%m-%d")
    return dia


def snapshot_dir(day: str | None = None) -> Path:
    d = SNAPSHOTS / (day or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


def ultimo_snapshot(nombre: str) -> Path | None:
    """El cuerpo vigente de un snapshot con ese nombre, sea de qué día sea.

    Desde que un contenido idéntico deja de archivarse dos veces, «el fichero
    de hoy» y «el cuerpo vigente» dejaron de ser lo mismo: si la fuente devolvió
    lo de ayer, hoy no hay fichero. Quien lea `snapshot_dir() / x` en vez de
    esto se queda con las manos vacías el primer día que la fuente no cambie —y
    en silencio, que es lo peor. `data/snapshots/` está ordenado por día, así
    que el vigente es el primero al recorrerlo al revés.
    """
    if not SNAPSHOTS.exists():
        return None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / nombre
        if f.exists():
            return f
    return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources_log (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  url TEXT NOT NULL,
  http_status INTEGER,
  sha256 TEXT,
  bytes INTEGER,
  snapshot_path TEXT,
  note TEXT,
  -- Validadores de caché que declaró la RESPUESTA de ese día. Viven aquí, y no
  -- en una tabla de estado aparte, porque son parte de lo que dijo el servidor
  -- —igual que `sha256` o `bytes`— y una segunda tabla sería una segunda copia
  -- que diverge. De ellos sale el `If-None-Match` / `If-Modified-Since`
  -- de la petición siguiente; leerlos es una consulta por URL, no un estado.
  etag TEXT,
  last_modified TEXT
);
-- La petición condicional busca la última copia archivada DE ESA URL en cada
-- fetch: sin índice, cada descarga recorre el log entero (4.277 filas y
-- subiendo). No afecta a los volcados: `dump_db.TABLAS` solo mira CREATE TABLE.
CREATE INDEX IF NOT EXISTS ix_sources_log_url ON sources_log(url, id);
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
-- Sedes educativas MEN (SISE): estado físico sede a sede tras el sismo.
-- UNA tabla y no dos (precedente rud_daily, no UNOSAT/SERTIT): aquí no hay
-- «producto» con identidad propia que publique paquetes — hay un registro que
-- se republica entero y sin versión. La serie es POR CAMBIOS, no por días:
-- línea base completa en la primera corrida y después una fila solo cuando
-- algún campo de la sede cambió (el 87 % repite 'No aporta información' a
-- diario y acumular la foto entera serían ~180 MB/mes de copias). El corte
-- vigente de una sede es su última fila; la comprobación diaria sin cambios
-- queda en sources_log. Los literales de la fuente (estado_fisico,
-- sede_principal, confianza_geo) se guardan tal cual.
CREATE TABLE IF NOT EXISTS men_sedes (
  cod_dane TEXT NOT NULL,            -- identificador DANE de la sede (único hoy)
  snapshot_date TEXT NOT NULL,
  cod_establecimiento TEXT,
  nombre_establecimiento TEXT, nombre_sede TEXT,
  sede_principal TEXT,               -- literal 'S'/'N': traducir es presentación
  sector TEXT,                       -- OFICIAL / NO OFICIAL
  correo_institucional TEXT, direccion TEXT, telefono TEXT,
  niveles TEXT, zona TEXT,
  cod_dep TEXT, nom_dep TEXT, cod_mun TEXT, nom_mun TEXT, cat_mun TEXT,
  mun_pdet TEXT, mun_zomac TEXT, nom_reg TEXT,
  cod_etc TEXT, nom_etc TEXT,        -- entidad territorial certificada
  total_matricula REAL, matricula_prel REAL,
  estado_fisico TEXT,                -- literal: 'No aporta información' ≠ sin daño
  confianza_geo TEXT,                -- literal: '2 - MEDIA', etc.
  lat REAL, lon REAL,                -- pedidos en outSR=4326 (nativa: 102100)
  first_seen TEXT,
  PRIMARY KEY (cod_dane, snapshot_date)
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
    # Validadores de caché HTTP (24-ago-2026). La base del runner arrastra
    # 4.277 filas sin ellos: las columnas nacen en NULL y se van llenando desde
    # la primera respuesta que las traiga. Un NULL aquí significa exactamente
    # «ese día no se lo preguntamos, o no lo dijo», que es dato, no hueco.
    ("sources_log", "etag", "TEXT"),
    ("sources_log", "last_modified", "TEXT"),
]


def migrar(conn: sqlite3.Connection) -> list[str]:
    """Añade las columnas que el esquema declara y la base todavía no tiene.

    Solo añade: renombrar o borrar columnas está prohibido sin migración de los
    dumps (ver CLAUDE.md). Idempotente — se ejecuta en cada `db()`.
    """
    hechas = []
    for tabla, columna, tipo in MIGRACIONES:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}
        if not cols:
            continue    # tabla que aún no existe: la crea SCHEMA, no ALTER
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


# --- Activos: contenido que no cambia ----------------------------------------
# Un cuerpo que se vuelve a pedir cada día es un DATO: puede haber cambiado y
# preguntar es la única forma de saberlo. Un vídeo ciudadano no: nace con una
# dirección propia —un UUID que ChatMap acuña al subirlo— y su contenido es el
# que es. Eso es un ACTIVO, y un activo se archiva una vez.
#
# La distinción no es cosmética: medido sobre `sources_log` el 24-ago-2026, de
# los 3.931 MB que el monitor ha descargado en su vida, 2.648 son 77 vídeos
# bajados una media de 4,8 veces cada uno, siempre con el mismo sha256 (cero
# excepciones en 372 descargas). No cabían en git, así que el runner arrancaba
# sin ellos y el guardián, que miraba el disco, nunca los encontraba.
MANIFIESTO_R2 = DATA / "r2_manifest.json"

# Las extensiones cuyo cuerpo NO cabe en git y por tanto vive en el bucket.
# Vive en CUATRO superficies y hay un guardián que las compara
# (`TestActivosDelArchivo::test_las_extensiones_de_r2_dicen_lo_mismo_
#  en_las_cuatro_superficies`):
# aquí, en `.gitignore`, en el `aws s3 sync` de `daily.yml` y en el test de
# trazabilidad. Que se separen no es un descuido teórico: `.avi` llevaba desde
# el principio en `.gitignore` y en ninguna de las otras tres, así que un vídeo
# con esa extensión se habría descargado, no habría entrado en git, no habría
# subido a R2 y no habría figurado en el manifiesto — irrecuperable en cuanto
# el runner se apagara, y sin una sola línea roja.
ARCHIVO_EN_R2 = (".mp4", ".mov", ".avi", ".webm", ".opus", ".ogg", ".m4a")


def manifiesto_r2(ruta: Path | None = None) -> dict[str, dict]:
    """El manifiesto versionado del bucket, como {objeto: {sha256, bytes}}.

    Es la copia del archivo que VIAJA CON EL CLON: la base de datos se
    reconstruye de los volcados y puede no estar todavía, pero este fichero
    está en git desde el primer `git clone`. Si no se puede leer, devuelve {}
    y quien pregunte se queda sin esa vía — nunca rompe la corrida (R13).
    """
    try:
        datos = json.loads((ruta or MANIFIESTO_R2).read_text(encoding="utf-8"))
        return {o["objeto"]: o for o in datos.get("objetos", [])
                if o.get("objeto") and o.get("sha256")}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def activo_archivado(url: str, conn: sqlite3.Connection | None = None, *,
                     destino: Path | None = None,
                     manifiesto: dict | None = None) -> dict | None:
    """¿Este activo ya está en el archivo? Devuelve su sha256 y su ruta, o None.

    Pregunta AL ARCHIVO, no al sistema de ficheros, porque el sistema de
    ficheros de la máquina que corre el proceso arranca vacío de todo lo que
    git ignora. Tres vías, en orden de fuerza de la evidencia:

    1. **El cuerpo en disco.** Es la prueba, no un registro de la prueba.
    2. **`citizen_reports.media_sha256`.** La base viva, que `run_daily`
       reconstruye entera desde `data/dumps/` antes de empezar la corrida.
    3. **`data/r2_manifest.json`.** El manifiesto versionado, que sobrevive a
       la pérdida de la base porque viaja en el clon.

    **Las vías 2 y 3 solo valen para cuerpos que viven FUERA de git**, es decir
    `ARCHIVO_EN_R2`. Para una foto, que sí viaja en el clon, el archivo ES el
    disco: si falta, hay que volver a traerla, y fiarse de la base la declararía
    archivada para siempre. Antes de esta distinción, borrar una imagen del repo
    la condenaba a no recuperarse nunca — se vería en rojo (el régimen fuerte lo
    caza) pero solo se arreglaría a mano.

    **Si la base y el manifiesto se contradicen, devuelve None**: un archivo
    que se desmiente a sí mismo no autoriza a saltarse nada, así que se vuelve
    a descargar y se restablece la verdad. La contradicción se canta aparte
    (`alerts.divergencias_del_archivo_de_activos`), porque es un hallazgo.
    """
    clave = (url or "").rsplit("/", 1)[-1]
    if not clave:
        return None
    if destino is not None:
        try:
            cuerpo = destino.read_bytes()
            return {"sha256": hashlib.sha256(cuerpo).hexdigest(),
                    "ruta": str(destino.relative_to(ROOT)),
                    "bytes": len(cuerpo), "origen": "disco"}
        except OSError:
            pass            # no está: sigue preguntando al archivo
    if not clave.lower().endswith(ARCHIVO_EN_R2):
        return None         # su cuerpo viaja en git: si no está, se trae otra vez
    en_base = None
    if conn is not None:
        try:
            fila = conn.execute(
                "SELECT media_sha256, media_local FROM citizen_reports"
                " WHERE media_url=? AND media_sha256 IS NOT NULL"
                " ORDER BY snapshot_date DESC LIMIT 1", (url,)).fetchone()
            if fila:
                en_base = {"sha256": fila[0],
                           "ruta": fila[1] or f"data/media/{clave}",
                           "bytes": None, "origen": "base"}
        except sqlite3.Error:
            en_base = None   # base antigua o rota: R13, se degrada a la otra vía
    mani = manifiesto_r2() if manifiesto is None else manifiesto
    obj = mani.get(clave)
    en_manifiesto = ({"sha256": obj["sha256"], "ruta": f"data/media/{clave}",
                      "bytes": obj.get("bytes"), "origen": "manifiesto"}
                     if obj else None)
    if en_base and en_manifiesto and en_base["sha256"] != en_manifiesto["sha256"]:
        return None
    return en_base or en_manifiesto


def copia_vigente(url: str, conn: sqlite3.Connection | None = None) -> dict | None:
    """La última copia archivada de esa URL cuyo cuerpo se puede servir HOY.

    Es la memoria del archivo, no una caché: sale de `sources_log`, que es el
    índice de todo lo que se ha pedido. Devuelve sha256, ruta, validadores y el
    cuerpo ya leído, o None si no hay copia utilizable.

    El cuerpo se verifica contra su sha256 antes de darlo por bueno. Si el
    fichero falta (los vídeos ciudadanos viven en R2, no en el repo) o su
    contenido ya no cuadra con lo que dice el log, esta función devuelve None y
    `fetch()` vuelve al régimen de siempre: descarga entera. **Es el invariante
    que hace segura toda la mecánica: solo se pregunta condicionalmente por lo
    que se puede devolver del archivo**, así que un 304 nunca deja al llamante
    con las manos vacías ni deja en el log un sha sin cuerpo detrás.
    """
    propia = conn is None
    c = conn or db()
    try:
        filas = c.execute(
            "SELECT sha256, snapshot_path, etag, last_modified FROM sources_log"
            " WHERE url=? AND sha256 IS NOT NULL AND snapshot_path IS NOT NULL"
            " ORDER BY id DESC LIMIT 3", (url,)).fetchall()
    except sqlite3.OperationalError:
        return None      # base antigua sin las columnas: R13, no se rompe nada
    finally:
        if propia:
            c.close()
    for sha, spath, etag, last_mod in filas:
        f = ROOT / spath
        try:
            cuerpo = f.read_bytes()
        except OSError:
            continue     # cuerpo fuera del repo (R2) o borrado: no hay copia
        if hashlib.sha256(cuerpo).hexdigest() != sha:
            continue     # el archivo no cuadra con el log: mejor volver a pedir
        return {"sha256": sha, "snapshot_path": spath, "etag": etag,
                "last_modified": last_mod, "cuerpo": cuerpo}
    return None


# Cabeceras de validación que soporta el mecanismo. Se recortan al guardarlas:
# un servidor puede devolver un ETag absurdo y no vamos a mandarlo de vuelta.
MAX_VALIDADOR = 256


def _validadores(resp) -> tuple[str | None, str | None]:
    """ETag y Last-Modified de una respuesta, si los declara.

    Defensivo a propósito (R13): una respuesta sin cabeceras —o con cabeceras
    que no se dejan leer— no puede tumbar una descarga que sí funcionó.
    """
    try:
        cab = resp.headers
        etag = cab.get("ETag")
        last_mod = cab.get("Last-Modified")
    except Exception:
        # Leer una cabecera no puede convertir una descarga que funcionó en un
        # fallo de red: el cuerpo ya está aquí y es lo que importa.
        return None, None
    return ((etag or None) and etag[:MAX_VALIDADOR],
            (last_mod or None) and last_mod[:MAX_VALIDADOR])


# Índice legible de lo que un día NO contiene. Ver `_anotar_reutilizado`.
REUTILIZADOS = "reutilizados.txt"
CABECERA_REUTILIZADOS = (
    "# Cuerpos que este día no se volvieron a archivar: la fuente devolvió lo\n"
    "# mismo que ya teníamos, así que la copia viva es la de otro día. Una\n"
    "# línea por cuerpo: nombre que habría tenido aquí, copia vigente, sha256.\n"
    "# El índice completo de peticiones es data/dumps/sources_log.csv.\n")


def _ocupado_por_otro_cuerpo(ruta: Path, sha: str) -> bool:
    """¿Hay ya algo ahí que NO es este cuerpo?

    Defensivo a propósito (R13): si la ruta existe y no se deja leer —un
    directorio, un permiso—, se responde que sí, y el cuerpo nuevo se escribe al
    lado en vez de reventar una corrida que ya tenía los bytes en la mano.
    """
    try:
        return hashlib.sha256(ruta.read_bytes()).hexdigest() != sha
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _nombre_con_contenido(nombre: str, sha: str) -> str:
    """`capa.json` + sha → `capa_1a2b3c4d.json`. Una sola implementación.

    El archivo no se sobrescribe nunca: cuando llega un cuerpo distinto bajo un
    nombre que ya está ocupado, se guarda al lado con la firma de su contenido.
    Lo usan los snapshots intradía y los cuerpos que van a `save_to`.
    """
    stem, punto, ext = nombre.rpartition(".")
    return f"{stem}_{sha[:8]}.{ext}" if punto else f"{nombre}_{sha[:8]}"


def _anotar_reutilizado(nombre: str, spath: str, sha: str) -> None:
    """Deja en la carpeta del día constancia del cuerpo que no está en ella.

    `sources_log` ya lo dice, pero un historiador que abra
    `data/snapshots/2026-08-24/` y no encuentre la capa de Copernicus no tiene
    por qué saber que existe una base de datos: la carpeta se explica sola.
    Idempotente y aditivo — nunca reescribe una línea existente.
    """
    try:
        f = snapshot_dir() / REUTILIZADOS
        linea = f"{nombre}\t{spath}\t{sha}\n"
        previo = f.read_text(encoding="utf-8") if f.exists() else CABECERA_REUTILIZADOS
        if linea not in previo:
            f.write_text(previo + linea, encoding="utf-8")
    except OSError:
        pass     # el índice es una cortesía; su fallo no puede costar un dato


def fetch(url: str, params: dict | None = None, *, note: str = "",
          snapshot_name: str | None = None, timeout: int = 60,
          retries: int = 2, retry_wait: float = 5.0,
          binary: bool = False, conn: sqlite3.Connection | None = None,
          save_to: Path | None = None, max_save_bytes: int | None = None,
          condicional: bool = True):
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

    **Peticiones condicionales** (`condicional=True`): si el archivo ya tiene
    una copia utilizable de esa URL, se manda `If-None-Match` con su ETag y/o
    `If-Modified-Since` con su Last-Modified. Un 304 no descarga cuerpo y deja
    igualmente SU FILA en `sources_log`, con `http_status` 304, `bytes` 0 y el
    `sha256`/`snapshot_path` de la copia que ya teníamos: dentro de veinte años
    esa fila dice «ese día preguntamos y la fuente contestó que lo mismo», que
    es información, no ausencia. **Al llamante le llega el cuerpo vigente con
    su 200**: para quien pide un dato, la respuesta es el contenido, y el 304 es
    un hecho de la red que vive en el log. Sin esto, un 304 haría desaparecer
    del mapa las 16 capas de Copernicus el día que la fuente dijera «sin
    cambios». `condicional=False` desactiva el mecanismo para una fuente
    concreta.

    **Un contenido idéntico no se archiva dos veces**: si el servidor no
    soporta condicionales y manda 200 con un cuerpo que ya está archivado, la
    fila apunta a la copia existente y no se escribe un fichero nuevo. No se
    sobrescribe ni se migra nada — simplemente deja de escribirse una copia
    redundante, y la carpeta del día lo explica en `reutilizados.txt`.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    previa = copia_vigente(url, conn) if condicional else None
    cabeceras = {"User-Agent": USER_AGENT}
    if previa:
        if previa["etag"]:
            cabeceras["If-None-Match"] = previa["etag"]
        if previa["last_modified"]:
            cabeceras["If-Modified-Since"] = previa["last_modified"]
    preguntamos_condicional = len(cabeceras) > 1
    req = urllib.request.Request(url, headers=cabeceras)
    body, status, err = b"", 0, None
    etag = last_mod = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                status, body = r.status, r.read()
                etag, last_mod = _validadores(r)
            break
        except urllib.error.HTTPError as e:
            # urllib entrega el 304 por aquí: es un «error» de status, no de red
            status, body = e.code, (e.read() or b"") if e.code != 304 else b""
            etag, last_mod = _validadores(e)
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
    # Los validadores de la copia previa se arrastran si la respuesta no trae
    # los suyos: un 304 puede venir sin ETag y perderlo dejaría al día
    # siguiente sin con qué preguntar.
    if status == 304 and previa:
        etag = etag or previa["etag"]
        last_mod = last_mod or previa["last_modified"]
    if status == 200 and body:
        # ¿es este cuerpo el mismo que ya guardamos para esta URL? Se decide
        # por sha256 y por URL, nunca por una lista de fuentes «estáticas»: una
        # fuente que hoy no cambia puede cambiar mañana y el mecanismo se entera
        # solo — la comparación es de contenido.
        reusable = previa if previa and previa["sha256"] == sha else None
        if save_to is not None:
            if max_save_bytes is None or len(body) <= max_save_bytes:
                if reusable and not save_to.exists():
                    spath = reusable["snapshot_path"]
                else:
                    save_to.parent.mkdir(parents=True, exist_ok=True)
                    destino = save_to
                    if _ocupado_por_otro_cuerpo(save_to, sha):
                        # Mismo nombre, contenido DISTINTO. Antes esto no
                        # escribía nada y la fila del log declaraba un sha256
                        # apuntando a un fichero con OTRO cuerpo: la única
                        # forma de que este archivo mienta sin que nadie lo
                        # note. Copia aparte, jamás encima — la misma política
                        # que los snapshots intradía, aquí abajo.
                        destino = save_to.with_name(
                            _nombre_con_contenido(save_to.name, sha))
                    if not destino.exists():
                        destino.write_bytes(body)
                    spath = str(destino.relative_to(ROOT))
        elif snapshot_name:
            p = snapshot_dir() / snapshot_name
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == sha:
                spath = str(p.relative_to(ROOT))        # ya archivado hoy
            elif reusable:
                spath = reusable["snapshot_path"]       # activo, no dato nuevo
                _anotar_reutilizado(snapshot_name, spath, sha)
            elif not p.exists():
                p.write_bytes(body)
                spath = str(p.relative_to(ROOT))
            else:
                # mismo día, contenido DISTINTO: copia aparte, jamás encima
                p = snapshot_dir() / _nombre_con_contenido(snapshot_name, sha)
                if not p.exists():
                    p.write_bytes(body)
                spath = str(p.relative_to(ROOT))
    elif status == 304 and previa and preguntamos_condicional:
        # R4: la petición existió y deja su fila, apuntando al cuerpo vigente.
        # Solo si de verdad preguntamos: un 304 a una petición que no llevaba
        # validadores no afirma nada sobre nuestro archivo, así que esa fila se
        # queda sin sha y sin ruta —y `alerts.py` la canta (R11/R13).
        sha, spath = previa["sha256"], previa["snapshot_path"]
        if snapshot_name:
            _anotar_reutilizado(snapshot_name, spath, sha)
    own = conn is None
    c = conn or db()
    c.execute(
        "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,snapshot_path,"
        " note,etag,last_modified) VALUES (?,?,?,?,?,?,?,?,?)",
        (utcnow(), url, status, sha, len(body), spath, note or err,
         etag, last_mod),
    )
    if own:
        c.commit()
        c.close()
    if status == 304:
        # Un 304 sin copia que servir solo puede pasar si la fuente contesta
        # «sin cambios» a algo que no le preguntamos (R13): no se inventa un
        # cuerpo, se devuelve el 304 tal cual y el llamante degrada.
        if previa and preguntamos_condicional:
            return 200, previa["cuerpo"]
        return status, body
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
