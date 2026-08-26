"""Alertas del día — solo Colombia, todas las fuentes del evento.

Cada corrida regenera alerts.json desde cero con lo que cambió HOY:
- Activaciones Copernicus nuevas DE COLOMBIA (las de otros países se ignoran)
- Cambios de versión/estado en productos EMSR916
- Reportes ciudadanos nuevos (ChatMap, últimas 24 h)
- Titulares nuevos de los feeds comunitarios (hoy)
- Balance nuevo en medios que citan fuentes oficiales (worker IA), con delta
- UNGRD: si el máximo oficial avanza (¡la brecha se cierra!) — nivel alta
"""
from __future__ import annotations

import sqlite3

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import db, fetch_json, today, PUBLIC, SNAPSHOTS

UI_JS = Path(__file__).parent.parent / "site" / "ui.js"

FEED_BALANCES = ("https://monitor-terremoto-colombia-oficiales-ai"
                 ".inforesidencias.workers.dev/oficiales.json")
UNGRD_ESTANCADO = "2024-02-17"   # si supera esto, la fuente oficial despertó

# Tres capturas seguidas repitiendo las mismas cifras: el registro no está
# lento, está parado. Es un umbral de AVISO y no toca lo que se publica — la
# tabla de las fichas agrupa los días quietos vaya el registro parado o no.
CAPTURAS_PLANAS_PARA_DETENIDO = 3

# Las columnas que se comparan para decidir si un municipio se movió: las
# mismas que publica la ficha. Espejo de `COLUMNAS_DEL_RUD` en
# deploy/render_html.py —la corrida diaria no importa el módulo de render—; si
# tocas una, mira la otra: `tests/test_unit.py::TestRudDetenido` las compara.
COLUMNAS_DEL_RUD = ("familias", "personas", "viv_destruidas", "viv_averiadas")


def capturas_sin_movimiento(capturas: list[tuple[str, dict]]) -> list[str]:
    """Las capturas del final en que NINGÚN municipio se movió.

    El RUD lo cargan las alcaldías y un día dejarán de cargarlo. Cuando eso
    pase, `rud_actualizado` simplemente dejará de aparecer — y un silencio no
    se distingue de una corrida rota. Esto lo dice en voz alta: es el detector
    de silencio de R15 aplicado al contenido, no a la disponibilidad de la
    fuente, que sigue respondiendo 200 mientras repite lo mismo.

    `capturas` va ordenada por fecha; cada una es (fecha, {municipio: cifras}).
    Un municipio nuevo cuenta como movimiento: el registro se abrió a un sitio
    donde antes no había nadie inscrito, que es justo lo que este monitor mira.
    """
    planas = []
    for i in range(len(capturas) - 1, 0, -1):
        if capturas[i][1] != capturas[i - 1][1]:
            break
        planas.append(capturas[i][0])
    planas.reverse()
    return planas


def aviso_de_estancamiento(planas: list[str]) -> dict | None:
    """La alerta que corresponde a una racha de capturas planas, o None.

    El nivel «alta» suena UNA vez: el día que se cruza el umbral. Después el
    aviso sigue publicándose en `info` para que el estado conste, pero sin
    volver a disparar el push — que se dispara con el nivel alta y se deduplica
    por el sha del texto, y este texto crece cada día («lleva 4 capturas»,
    «lleva 5»). Mantenerlo en alta sería una notificación diaria para avisar de
    que no ha pasado nada. Ver `workers/push/src/webpush.js::filtrarNotificables`.
    """
    if not planas:
        return None
    detenido = len(planas) >= CAPTURAS_PLANAS_PARA_DETENIDO
    return {
        "tipo": "rud_detenido" if detenido else "rud_sin_movimiento",
        "nivel": "alta" if len(planas) == CAPTURAS_PLANAS_PARA_DETENIDO else "info",
        "capturas_planas": len(planas), "desde": planas[0],
        "texto": (f"El RUD lleva {len(planas)} captura(s) sin mover un solo "
                  f"municipio (desde {planas[0]}). La fuente responde y repite "
                  f"las mismas cifras: no es un fallo de la corrida, es un "
                  f"registro que dejó de crecer.")}


def _capturas_del_rud(conn, cuantas: int = 6) -> list[tuple[str, dict]]:
    """Las últimas capturas del RUD, tal como quedaron archivadas."""
    dias = [r[0] for r in conn.execute(
        "SELECT DISTINCT snapshot_date FROM rud_daily"
        " ORDER BY snapshot_date DESC LIMIT ?", (cuantas,))]
    capturas = []
    for dia in sorted(dias):
        filas = {}
        for r in conn.execute(
                "SELECT departamento, municipio, familias, personas,"
                " viv_destruidas, viv_averiadas FROM rud_daily"
                " WHERE snapshot_date=?", (dia,)):
            filas[(r[0], r[1])] = tuple(r[2:])
        capturas.append((dia, filas))
    return capturas



def _sha_de_la_regla() -> str | None:
    """sha256 de site/ui.js: la regla que produjo el consolidado cambia con el
    tiempo (el techo de salto, las anclas, qué cuenta como atribución), así que
    sin esto un derivado archivado no es reconstruible aunque se conserve el
    cuerpo de entrada."""
    try:
        import hashlib
        return hashlib.sha256(UI_JS.read_bytes()).hexdigest()
    except OSError:
        return None


def _consolidado_de_la_serie(feed: dict) -> tuple[list, str]:
    """El consolidado del balance, calculado por la ÚNICA implementación de la
    regla: site/ui.js, ejecutado con node.

    Hasta el 21-ago-2026 aquí vivía una segunda regla —el máximo de fallecidos
    de cada día suelto— y las dos superficies se contradecían en público: con
    el feed del 19-ago, el push habría anunciado «180 fallecidos (-124 vs día
    anterior)», o sea 124 resucitados, mientras la web mostraba 304. El día no
    traía balance nuevo: traía tres cortes viejos.

    R13: si node no está, no se rompe la corrida — pero tampoco se publica una
    cifra calculada con otra regla. Se devuelve la lista vacía y una etiqueta
    que dice justamente eso, para que nadie lea en un JSON archivado que la
    cifra salió de un cálculo que no se hizo.
    """
    node = shutil.which("node")
    if node and UI_JS.exists():
        # El feed viaja por STDIN, no como argumento: Linux limita cada
        # argumento de execve a 128 KiB (MAX_ARG_STRLEN) y el feed ya pesa
        # ~100 KB, así que pasarlo en la línea de órdenes funcionaba en macOS
        # y habría reventado en el runner de la corrida diaria — en silencio,
        # todos los días, justo en el camino que degrada.
        script = (
            "global.window = {};"
            f"require({json.dumps(str(UI_JS))});"
            "const feed = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "const items = (feed.items || []).filter((x) => x.search_date);"
            "console.log(JSON.stringify(window.UI.mejorPorDia(items)));")
        try:
            r = subprocess.run([node, "-e", script],
                               input=json.dumps(feed, ensure_ascii=False),
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return json.loads(r.stdout), "serie_consolidada_ui_js"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return [], "sin_regla__no_se_publica"


_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_es(iso: str) -> str:
    """«2026-08-18» → «18 de agosto de 2026». El aviso lo leen personas."""
    try:
        a, m, d = iso.split("-")
        return f"{int(d)} de {_MESES_ES[int(m) - 1]} de {a}"
    except (ValueError, IndexError):
        return iso


def balance_de_medios(feed: dict, snap: str) -> tuple[list[dict], dict | None]:
    """Los avisos del balance y el consolidado que se archiva, en una sola
    función para que el artefacto se pueda REGENERAR con este mismo código.

    Vive aparte de `run()` por un motivo concreto: `data/public/alerts.json`
    está versionado y se despliega con el merge, así que un cambio de regla que
    no regenere el artefacto publica la cifra vieja hasta la corrida siguiente.
    Pasó el 21-ago-2026, y el aviso archivado anunciaba «180 fallecidos (-124
    vs día anterior)» — 124 resucitados— con la web ya diciendo 304.
    """
    serie, regla = _consolidado_de_la_serie(feed)
    if not serie:
        return ([{
            "tipo": "regla_de_balance_degradada", "nivel": "alta",
            "texto": "No se ha podido calcular la serie de balances con "
                     "site/ui.js (¿falta node?): el aviso del día se omite "
                     "en vez de publicar una cifra con otra regla."}], None)

    ultimo = serie[-1]
    valor = lambda d, k: (d["consolidado"].get(k) or {}).get("valor")
    # se publica SIEMPRE, no solo cuando hay aviso: la imagen social y
    # cualquier otro consumidor necesitan la cifra vigente también los días
    # en que no llega ningún balance nuevo
    consolidado = {
        "fecha": ultimo["fecha"], "regla": regla,
        "cifras": {k: (v or {}).get("valor")
                   for k, v in ultimo["consolidado"].items()},
        # cada cifra con su fecha, su medio y SU ENLACE: es un dato derivado, y
        # sin la url nadie puede volver dentro de años al artículo del que salió
        "origen": {k: {"fecha": (v or {}).get("fecha"),
                       "medio": (v or {}).get("medio"),
                       "url": (v or {}).get("url")}
                   for k, v in ultimo["consolidado"].items()},
        # lo descartado y por qué: la brecha (R12) también se archiva, no solo
        # se pinta en el navegador
        "ignoradas": ultimo.get("ignoradas") or [],
        # R4: un derivado tiene que decir de qué cuerpo sale y con qué versión
        # de la regla, o no se puede reconstruir
        "derivado_de": {
            "url": FEED_BALANCES,
            "snapshot": f"data/snapshots/{snap}/oficiales_feed.json",
            "items": len([i for i in feed.get("items") or []
                          if i.get("search_date")]),
            "regla_sha256": _sha_de_la_regla()}}

    if ultimo["fecha"] not in (snap, _ayer()):
        return ([], consolidado)

    c = {k: valor(ultimo, k)
         for k in ("fallecidos", "heridos", "desaparecidos",
                   "familias_afectadas", "personas_afectadas")}
    prev = serie[-2] if len(serie) > 1 else None
    antes = valor(prev, "fallecidos") if prev else None
    # el consolidado no retrocede, así que un delta 0 significa que ese día no
    # llegó ningún balance nuevo: no hay nada que avisar
    if prev is not None and c["fallecidos"] == antes:
        return ([], consolidado)

    delta = ""
    if antes is not None and c["fallecidos"] is not None:
        d_f = c["fallecidos"] - antes
        delta = f" (+{d_f} desde el balance anterior)" if d_f else ""
    mil = lambda n: f"{n:,}".replace(",", ".") if isinstance(n, int) else "?"
    return ([{
        "tipo": "balance_en_medios", "nivel": "info",
        "texto": f"Máximo informado en medios que citan fuentes oficiales "
                 f"({_fecha_es(ultimo['fecha'])}): "
                 f"{mil(c['fallecidos'])} fallecidos{delta}, "
                 f"{mil(c['heridos'])} heridos, "
                 f"{mil(c['desaparecidos'])} desaparecidos",
        "fecha_balance": ultimo["fecha"], "cifras": c,
        "regla": regla}], consolidado)


def _ayer() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


# Emisores conocidos de la cronología institucional de GDACS. El título llega
# en inglés y con el nombre del emisor dentro («… - UNITAR-UNOSAT Activation»).
EMISORES = (
    ("UNOSAT", "UNITAR-UNOSAT"),
    ("Copernicus", "Copernicus EMS"),
    ("ECHO", "EC/ECHO"),
)


def _emisor(titulo: str) -> str:
    for clave, nombre in EMISORES:
        if clave.lower() in (titulo or "").lower():
            return nombre
    return "Una fuente institucional"


def _institucional(dia: str) -> list[dict] | None:
    """Cronología institucional archivada de un día, o None si no se capturó."""
    f = SNAPSHOTS / dia / "gdacs_news_institucional.json"
    if not f.exists():
        return None
    try:
        datos = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, list) else None


def _institucionales_nuevos(snap: str) -> list[dict]:
    """Entradas que hoy están y en la última captura anterior no.

    Sin captura previa NO se alerta: en la primera corrida todo sería «nuevo»
    y siete avisos de golpe no informan de nada. La identidad es (enlace,
    fecha) porque Copernicus reutiliza la misma URL de descarga en entradas
    distintas.
    """
    hoy = _institucional(snap)
    if not hoy:
        return []
    previo = None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        if d.name >= snap:
            continue
        previo = _institucional(d.name)
        if previo is not None:
            break
    if previo is None:
        return []
    vistos = {(x.get("link"), x.get("pubdate")) for x in previo}
    return [x for x in hoy if (x.get("link"), x.get("pubdate")) not in vistos]


def codigos_de_evento_imposibles(conn, hoy: str, *, paquete: str | None = None) -> list[dict]:
    """Códigos GLIDE de UNOSAT cuya fecha implícita no puede ser cierta.

    Un `event_code` tipo `EQ20260822COL` lleva la fecha del evento dentro. Si
    esa fecha es POSTERIOR a la imagen que retrata el daño —o peor, posterior a
    hoy—, el código no puede designar un evento real: es un error de etiquetado
    en origen. Pasó de verdad (8 puntos de Manizales, ver docs/LIMITACIONES.md)
    y el monitor lo descubrió leyendo a mano, no porque nada avisara.

    R11: avisa, no rompe. Los puntos se siguen archivando con su literal.
    """
    fuera = []
    # `paquete` acota a la versión vigente de la capa. Sin él, la alerta sumaba
    # también los puntos del paquete ya superado y anunciaba 16 donde el
    # monitor publicaba 209 — dos cifras el mismo día, y la equivocada saliendo
    # por push; a la tercera reedición habría dicho 24. Es un parámetro y no
    # una consulta interna para que la lógica del detector se pueda probar sin
    # inventarse un catálogo de productos.
    where, params = "event_code IS NOT NULL", ()
    if paquete:
        where += " AND paquete_sha=?"
        params = (paquete,)
    for code, cap, sensor_date, n in conn.execute(
            "SELECT event_code, capa, MIN(sensor_date), COUNT(*)"
            f" FROM unosat_damage WHERE {where}"
            " GROUP BY event_code, capa", params):
        m = re.match(r"^[A-Z]{2}(\d{4})(\d{2})(\d{2})[A-Z]{3}$", (code or "").upper())
        if not m:
            continue
        fecha = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        img = (f"{sensor_date[:4]}-{sensor_date[4:6]}-{sensor_date[6:8]}"
               if sensor_date and len(sensor_date) == 8 else None)
        if fecha > hoy:
            motivo = f"su fecha ({fecha}) aún no ha llegado"
        elif img and fecha > img:
            motivo = f"su fecha ({fecha}) es posterior a la imagen ({img})"
        else:
            continue
        fuera.append({"code": code, "capa": cap, "n": n, "motivo": motivo,
                      "fecha": fecha, "imagen": img})
    return fuera


def cambios_en_peticiones_condicionales(conn, hoy: str) -> list[dict]:
    """¿Cambió alguna fuente su forma de contestar a `If-None-Match`?

    Desde el 24-ago-2026 el monitor pregunta antes de descargar: si ya tiene
    una copia utilizable de una URL, manda sus validadores y un 304 le ahorra
    el cuerpo entero. Que una fuente empiece a soportarlo es BUENA noticia y
    hay que verla; que deje de hacerlo cuesta megas y también.

    R11 — avisa, no rompe. Y avisa AGREGADO: el día que Copernicus empiece a
    contestar 304, serían 16 alertas idénticas, y una alerta que se repite
    dieciséis veces la acaba silenciando quien la lee.
    """
    hoy_pfx = f"{hoy}%"
    trescientos_cuatro = {r[0] for r in conn.execute(
        "SELECT DISTINCT url FROM sources_log"
        " WHERE http_status=304 AND ts LIKE ?", (hoy_pfx,))}
    antes = {r[0] for r in conn.execute(
        "SELECT DISTINCT url FROM sources_log"
        " WHERE http_status=304 AND ts NOT LIKE ?", (hoy_pfx,))}
    avisos = []

    estrenan = sorted(trescientos_cuatro - antes)
    if estrenan:
        avisos.append({
            "tipo": "fuentes_con_peticion_condicional", "nivel": "info",
            "texto": (f"{len(estrenan)} URL(s) contestaron hoy por primera vez "
                      f"«304 sin cambios»: preguntar sale gratis y el cuerpo no "
                      f"se descarga. Ejemplo: {estrenan[0]}"),
            "urls": estrenan[:10], "n": len(estrenan)})

    # Dejó de honrarlos: ayer contestaba 304 y hoy manda 200 con lo mismo. Se
    # detecta por el cuerpo, no por la cabecera: da igual qué diga el servidor
    # si acaba mandando otra vez los mismos megas.
    reincidentes = []
    for url in sorted(antes - trescientos_cuatro):
        fila = conn.execute(
            "SELECT sha256, bytes FROM sources_log WHERE url=? AND ts LIKE ?"
            " AND http_status=200 ORDER BY id DESC LIMIT 1",
            (url, hoy_pfx)).fetchone()
        if not fila or not fila[0]:
            continue
        previo = conn.execute(
            "SELECT sha256 FROM sources_log WHERE url=? AND ts NOT LIKE ?"
            " AND sha256 IS NOT NULL ORDER BY id DESC LIMIT 1",
            (url, hoy_pfx)).fetchone()
        if previo and previo[0] == fila[0]:
            reincidentes.append((url, fila[1] or 0))
    if reincidentes:
        megas = sum(b for _, b in reincidentes) / 1e6
        avisos.append({
            "tipo": "fuente_deja_de_honrar_condicionales", "nivel": "media",
            "texto": (f"{len(reincidentes)} URL(s) que antes contestaban 304 "
                      f"volvieron a mandar el cuerpo entero sin haber cambiado "
                      f"({megas:.1f} MB). Ejemplo: {reincidentes[0][0]}"),
            "urls": [u for u, _ in reincidentes[:10]],
            "n": len(reincidentes), "bytes": sum(b for _, b in reincidentes)})

    # Un 304 sin sha es un 304 que llegó sin que preguntáramos: la fuente
    # afirma «sin cambios» sobre algo que no le planteamos. No rompe nada
    # (R13) y el llamante degrada, pero es un contrato roto y se canta.
    sin_pedir = [r[0] for r in conn.execute(
        "SELECT DISTINCT url FROM sources_log WHERE http_status=304"
        " AND sha256 IS NULL AND ts LIKE ?", (hoy_pfx,))]
    if sin_pedir:
        avisos.append({
            "tipo": "trescientos_cuatro_sin_preguntar", "nivel": "media",
            "texto": (f"{len(sin_pedir)} URL(s) contestaron «304 sin cambios» a "
                      f"una petición que no llevaba validadores: no dicen nada "
                      f"sobre el cuerpo que tenemos archivado, así que ese día "
                      f"queda sin captura. Ejemplo: {sin_pedir[0]}"),
            "urls": sin_pedir[:10], "n": len(sin_pedir)})
    return avisos


def divergencias_del_archivo_de_activos(conn) -> list[dict]:
    """¿Dicen lo mismo el manifiesto de R2 y la base sobre cada vídeo?

    Desde el 24-ago-2026 el monitor NO vuelve a descargar un activo que el
    archivo ya declara suyo. Ese ahorro se apoya entero en que las dos vías del
    archivo —`citizen_reports.media_sha256` y `data/r2_manifest.json`— digan lo
    mismo, así que la que las vigila no puede ser la misma que las usa (M2).

    Dos cosas se cantan y una NO:
    - un objeto con **sha256 distinto** en cada vía: el archivo se desmiente a
      sí mismo y `activo_archivado` deja de fiarse de los dos (vuelve a
      descargar); esto explica por qué.
    - un objeto del manifiesto que **la base no conoce**: sobra en el bucket, o
      la base perdió una fila.
    - un vídeo de la base que **aún no está en el manifiesto** no se avisa: el
      manifiesto lo escribe `publish`, que corre DESPUÉS de esta función, así
      que el día que llega un vídeo nuevo esa diferencia es lo normal. Avisar
      de lo normal es la forma más rápida de que dejen de leerse las alertas.
    """
    from common import manifiesto_r2
    manifiesto = manifiesto_r2()
    if not manifiesto:
        return []           # sin manifiesto no hay nada que comparar (R13)
    try:
        base = {(u or "").rsplit("/", 1)[-1]: s for u, s in conn.execute(
            "SELECT media_url, media_sha256 FROM citizen_reports"
            " WHERE media_sha256 IS NOT NULL")}
    except sqlite3.Error:
        return []
    if not base:
        # El espejo del caso de arriba, y el que de verdad muerde: si
        # `rebuild_db` o `chatmap` fallan, R13 se los traga y la base llega
        # vacía. Sin esta guarda, los 77 objetos del manifiesto salen como
        # huérfanos y la alerta acusa al bucket de un fallo de la base. Un
        # aviso que suena en falso deja de leerse, y entonces no avisa de nada.
        return [{"tipo": "base_sin_reportes_ciudadanos", "nivel": "media",
                 "texto": ("La base no tiene ni un reporte ciudadano con sha256, "
                           "así que hoy no se puede comparar con el manifiesto de "
                           f"R2 ({len(manifiesto)} objetos). No es que sobren en "
                           "el bucket: es que falta la base — revisar si "
                           "`rebuild_db` o `chatmap` fallaron."),
                 "objetos_en_manifiesto": len(manifiesto)}]
    avisos = []
    discrepan = sorted(k for k, o in manifiesto.items()
                       if k in base and base[k] != o["sha256"])
    if discrepan:
        avisos.append({
            "tipo": "manifiesto_r2_discrepa_de_la_base", "nivel": "alta",
            "texto": (f"{len(discrepan)} vídeo(s) ciudadanos tienen un sha256 en "
                      f"la base y otro en el manifiesto de R2. Mientras dure, "
                      f"esos cuerpos se vuelven a descargar enteros: el archivo "
                      f"no autoriza a saltarse lo que él mismo desmiente. "
                      f"Ejemplo: {discrepan[0]}"),
            "objetos": discrepan[:10], "n": len(discrepan)})
    huerfanos = sorted(set(manifiesto) - set(base))
    if huerfanos:
        avisos.append({
            "tipo": "manifiesto_r2_con_objetos_sin_reporte", "nivel": "media",
            "texto": (f"{len(huerfanos)} objeto(s) del manifiesto de R2 no "
                      f"corresponden a ningún reporte ciudadano de la base: o "
                      f"sobran en el bucket o la base perdió su fila. "
                      f"Ejemplo: {huerfanos[0]}"),
            "objetos": huerfanos[:10], "n": len(huerfanos)})
    return avisos


def run(copernicus_summary: dict | None = None) -> list[dict]:
    conn = db()
    snap = today()
    alerts = []
    balance_consolidado = None

    # 1) activaciones Copernicus nuevas — SOLO Colombia
    for item in (copernicus_summary or {}).get("new", []):
        if "Colombia" not in (item.get("countries") or []):
            continue
        alerts.append({
            "tipo": "nueva_activacion", "nivel": "alta",
            "texto": f"Copernicus abrió una nueva activación en Colombia: "
                     f"{item.get('code')} — {item.get('name')}",
            **item})

    # 2) cambios en productos EMSR916 respecto al snapshot anterior
    prev = conn.execute(
        "SELECT MAX(snapshot_date) FROM products WHERE code='EMSR916'"
        " AND snapshot_date < ?", (snap,)).fetchone()[0]
    if prev:
        cur_rows = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(
            "SELECT aoi_name, ptype, monitoring_number, version_number, status_code"
            " FROM products WHERE code='EMSR916' AND snapshot_date=?", (snap,))}
        prev_rows = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(
            "SELECT aoi_name, ptype, monitoring_number, version_number, status_code"
            " FROM products WHERE code='EMSR916' AND snapshot_date=?", (prev,))}
        estados = {"W": "en espera", "I": "en producción", "F": "entregado",
                   "N": "no producido"}
        for key, (ver, st) in cur_rows.items():
            pv = prev_rows.get(key)
            if pv is None:
                alerts.append({
                    "tipo": "producto_nuevo", "nivel": "alta",
                    "texto": f"Copernicus publicó un producto nuevo para {key[0]}: "
                             f"{key[1]} v{ver} ({estados.get(st, st)})",
                    "aoi": key[0], "producto": key[1], "version": ver, "status": st})
            elif pv != (ver, st):
                alerts.append({
                    "tipo": "producto_actualizado", "nivel": "alta",
                    "texto": f"{key[0]}: {key[1]} pasó de v{pv[0]} "
                             f"({estados.get(pv[1], pv[1])}) a v{ver} "
                             f"({estados.get(st, st)})",
                    "aoi": key[0], "producto": key[1],
                    "antes": {"version": pv[0], "status": pv[1]},
                    "ahora": {"version": ver, "status": st}})

    # 2b) cronología institucional nueva (UNOSAT, ECHO, Copernicus…)
    # El feed institucional de GDACS traía el producto 4253 de UNOSAT —la
    # evaluación del epicentro— y el monitor lo publicaba en la línea de
    # tiempo sin avisar a nadie: aparecía si alguien miraba. Un producto
    # institucional nuevo es exactamente lo que este monitor existe para
    # cazar, así que va en nivel alta.
    for item in _institucionales_nuevos(snap):
        quien = _emisor(item.get("title") or "")
        alerts.append({
            "tipo": "institucional_nuevo", "nivel": "alta",
            "texto": f"{quien} publicó un producto nuevo del terremoto: "
                     f"{item.get('title') or 'sin título'}"
                     f"{(' — ' + item['link']) if item.get('link') else ''}",
            "emisor": quien, "titulo": item.get("title"),
            "url": item.get("link"), "pubdate": item.get("pubdate")})

    # 3) reportes ciudadanos nuevos (últimas 24 h, por fecha del reporte)
    n_ciud = conn.execute(
        "SELECT COUNT(*) FROM citizen_reports WHERE ts >= ?",
        (_ayer(),)).fetchone()[0]
    if n_ciud:
        alerts.append({
            "tipo": "reportes_ciudadanos", "nivel": "info",
            "texto": f"{n_ciud} reporte(s) ciudadano(s) nuevos en ChatMap "
                     f"en las últimas 24 h", "n": n_ciud})

    # 4) titulares nuevos hoy en los feeds comunitarios
    n_news = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE snapshot_date = ?",
        (snap,)).fetchone()[0]
    if n_news:
        alerts.append({
            "tipo": "titulares_nuevos", "nivel": "info",
            "texto": f"{n_news} titular(es) nuevos sobre el terremoto en los "
                     f"feeds de prensa", "n": n_news})

    # 5) balance nuevo en medios (worker IA): delta del último día vs el anterior
    st, feed = fetch_json(FEED_BALANCES, note="alerts balances", conn=conn,
                          snapshot_name="oficiales_feed.json")
    # detector de silencio: el worker corre a diario; si lleva >48 h sin
    # generar (clave caducada, cuota agotada, cron roto), avisar en alta
    gen = (feed or {}).get("generated_at")
    if not feed:
        alerts.append({
            "tipo": "worker_balances_caido", "nivel": "alta",
            "texto": f"El feed de balances no responde (HTTP {st}): revisar el "
                     f"worker en Cloudflare"})
    elif gen:
        edad_h = (datetime.now(timezone.utc)
                  - datetime.fromisoformat(gen.replace("Z", "+00:00"))
                  ).total_seconds() / 3600
        if edad_h > 48:
            alerts.append({
                "tipo": "worker_balances_silencio", "nivel": "alta",
                "texto": f"El worker de balances lleva {edad_h:.0f} h sin generar "
                         f"(última: {gen[:16]}): revisar logs en Cloudflare "
                         f"(¿clave de Firecrawl/Qwen caducada?)"})
    if feed and feed.get("items"):
        avisos, balance_consolidado = balance_de_medios(feed, snap)
        alerts.extend(avisos)

    # 6b) RUD: el registro oficial de damnificados crece — contar el delta
    # Del último corte capturado, no del acumulado de `official_events`: el
    # archivo conserva toda fila que el registro haya tenido alguna vez, y
    # contarla aquí compararía el histórico contra la captura de la víspera
    # —dos poblaciones distintas— y publicaría en la alerta un total que no
    # cuadra con el del sitio. Es la misma avería que unificó la portada.
    hoy_rud = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(familias),0) FROM rud_daily"
        " WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM rud_daily)"
    ).fetchone()
    prev_rud = None
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        if d.name >= snap:
            continue
        f = d / "rud_2026T.json"
        if f.exists():
            rows = json.loads(f.read_text())
            rows = rows if isinstance(rows, list) else rows.get("data") or []
            prev_rud = (len(rows), sum(int(r.get("familias") or 0) for r in rows))
            break
    if hoy_rud and hoy_rud[0]:
        if prev_rud is None:
            alerts.append({
                "tipo": "rud_activo", "nivel": "alta",
                "texto": f"El RUD (registro oficial de damnificados) cubre el "
                         f"evento: {hoy_rud[0]} municipios, "
                         f"{hoy_rud[1]:,.0f} familias registradas".replace(",", ".")})
        elif (hoy_rud[0], hoy_rud[1]) != prev_rud:
            d_mun = hoy_rud[0] - prev_rud[0]
            d_fam = hoy_rud[1] - prev_rud[1]
            alerts.append({
                "tipo": "rud_actualizado", "nivel": "info",
                "texto": f"RUD actualizado: {'+' if d_mun >= 0 else ''}{d_mun} "
                         f"municipios, {'+' if d_fam >= 0 else ''}{d_fam:,.0f} "
                         f"familias desde la captura anterior".replace(",", ".")})

    # 6c) ¿se detuvo el registro? El RUD no muere: sigue contestando 200 con
    # las mismas cifras cuando las alcaldías terminan de cargar. Sin esto, el
    # final del registro llegaría como la simple ausencia de `rud_actualizado`
    # —un silencio idéntico al de una corrida rota—, y es la señal que decide
    # cuándo las fichas dejan de dibujar filas planas.
    aviso = aviso_de_estancamiento(
        capturas_sin_movimiento(_capturas_del_rud(conn)))
    if aviso:
        alerts.append(aviso)

    # 6) ¿despertó la fuente oficial? (nivel alta: cambia el cruce entero)
    for d in sorted(SNAPSHOTS.iterdir(), reverse=True):
        f = d / "ungrd_arcgis_agg.json"
        if f.exists():
            raw = json.loads(f.read_text())
            at = (raw.get("features") or [{}])[0].get("attributes", {})
            maxf = at.get("maxf")
            if isinstance(maxf, (int, float)):
                fecha = datetime.fromtimestamp(
                    maxf / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                if fecha > UNGRD_ESTANCADO:
                    alerts.append({
                        "tipo": "fuente_oficial_actualizada", "nivel": "alta",
                        "texto": f"¡El registro oficial UNGRD avanzó hasta {fecha}! "
                                 f"Revisar si ya hay EDAN del terremoto para "
                                 f"promover el cruce.", "max_fecha": fecha})
            break

    # 7) UNOSAT: códigos de evento con fecha imposible. Un código fechado
    # después de la imagen que retrata el daño —o en el futuro— es un supuesto
    # roto de manual, y hasta hoy no lo cantaba nadie.
    from sources.unosat import paquete_vigente
    for x in codigos_de_evento_imposibles(conn, snap,
                                          paquete=paquete_vigente(conn)):
        alerts.append({
            "tipo": "unosat_codigo_evento_imposible", "nivel": "media",
            "texto": f"UNITAR-UNOSAT publica {x['n']} puntos con el código "
                     f"«{x['code']}» y {x['motivo']}: no puede designar un evento "
                     f"real, así que es un error de etiquetado en origen. El "
                     f"monitor los cuenta —lo decide el identificador que "
                     f"declara el producto, no la etiqueta del punto— y publica "
                     f"la discrepancia aparte. Si UNOSAT la corrige, la nota "
                     f"desaparece sola.",
            "event_code": x["code"], "capa": x["capa"], "puntos": x["n"]})

    # 8) SERTIT: un producto nuevo no llega solo. Sus vectores los manda su
    # web por correo tras un formulario, así que un producto que aparece en el
    # catálogo sin paquete asociado significa que HAY QUE ESCRIBIR UN CORREO —
    # y sin esta alerta nadie se enteraría: el dato se quedaría en el catálogo,
    # visible y sin puntos, hasta que a alguien se le ocurriera mirar.
    try:
        pendientes = conn.execute(
            "SELECT municipio, n_producto, producto_id FROM sertit_productos"
            " WHERE paquete_sha256 IS NULL ORDER BY producto_id").fetchall()
    except sqlite3.OperationalError:
        pendientes = []
    for muni, n, pid in pendientes:
        alerts.append({
            "tipo": "sertit_sin_vectores", "nivel": "alta",
            "texto": (f"ICube-SERTIT publicó un producto sin vectores en el "
                      f"monitor: {muni or 'municipio por identificar'} "
                      f"(producto {n or pid}). Sus datos no se descargan — hay "
                      f"que pedirlos a emergency-sertit@unistra.fr, como se "
                      f"hizo el 20-ago-2026."),
            "municipio": muni, "producto": pid})

    # 9) ¿cambió alguna fuente su forma de contestar a una petición
    # condicional? Un supuesto del monitor sobre sus propias fuentes: avisa,
    # no rompe (R11), y una consulta rota no puede tumbar la corrida (R13).
    try:
        alerts.extend(cambios_en_peticiones_condicionales(conn, snap))
    except sqlite3.OperationalError:
        pass

    # 10) ¿siguen diciendo lo mismo el manifiesto de R2 y la base sobre los
    # vídeos ciudadanos? El ahorro de no volver a descargarlos se apoya en que
    # sí; el día que se separen hay que verlo (R11).
    try:
        alerts.extend(divergencias_del_archivo_de_activos(conn))
    except sqlite3.Error:
        pass

    payload = {"generado": snap, "fecha": snap, "alertas": alerts}
    if balance_consolidado:
        payload["balance_consolidado"] = balance_consolidado
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "alerts.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False))
    (PUBLIC / "alerts.rss").write_text(alerts_rss(snap, alerts))
    conn.commit()
    conn.close()
    return alerts


def alerts_rss(fecha: str, alerts: list[dict]) -> str:
    """RSS 2.0 de las alertas del día (stdlib pura, R14) — simetría con el
    oficiales.rss del worker: quien no quiera push puede seguir el monitor
    desde cualquier lector RSS."""
    from email.utils import format_datetime
    from datetime import datetime, timezone
    from xml.sax.saxutils import escape
    base = "https://datosdelterremoto.org/"
    pub = format_datetime(datetime.fromisoformat(fecha + "T11:00:00+00:00")
                          if len(fecha) == 10 else datetime.now(timezone.utc))
    items = "".join(
        f"<item><title>{escape(('⚠️ ' if a.get('nivel') == 'alta' else '') + (a.get('tipo') or '').replace('_', ' '))}</title>"
        f"<description>{escape(a.get('texto') or '')}</description>"
        f"<link>{base}#alerts-section</link>"
        f"<guid isPermaLink=\"false\">{escape(fecha)}-{escape(a.get('tipo') or '')}-{i}</guid>"
        f"<pubDate>{pub}</pubDate></item>"
        for i, a in enumerate(alerts))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>Alertas del monitor — terremoto Colombia 2026</title>"
        f"<link>{base}</link>"
        "<description>Cambios diarios detectados por el monitor de brechas: "
        "RUD, balances en medios, productos Copernicus y fuentes.</description>"
        "<language>es-co</language>"
        f"<lastBuildDate>{pub}</lastBuildDate>"
        f"{items}</channel></rss>")


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
