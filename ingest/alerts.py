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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common import db, fetch_json, today, PUBLIC, SNAPSHOTS, HUECOS_RUD_CONOCIDOS

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



def huecos_de_captura(conn, *, tabla: str = "rud_daily",
                      col_fecha: str = "snapshot_date",
                      conocidos: dict[str, str] | None = None) -> list[dict]:
    """Días que faltan en una serie diaria consolidada, ya explicados o no.

    Escrito para `rud_daily` — la única tabla cuya fecha sale de un cálculo
    (`dia_colombiano_consolidado`) que puede desincronizarse del reloj si el
    cron se retrasa (ver su docstring y el hueco del 26-ago-2026 en
    docs/DECISIONES.md). `tabla`/`col_fecha` generalizan la comprobación a
    cualquier tabla con una columna de fecha diaria por si hiciera falta
    después, pero HOY solo se llama con `rud_daily`: no hay otra tabla en el
    monitor con este mismo patrón de "un día, una fila consolidada", así que
    generalizar de verdad (más allá de estos dos parámetros) se deja para
    cuando aparezca una segunda candidata.

    Un hueco NUEVO (no en `conocidos`) sale en nivel alta: es justo el
    síntoma que destapó esto. Uno ya anotado en HUECOS_RUD_CONOCIDOS sale en
    info — sigue siendo verdad todos los días, pero ya no hay nada que
    decidir (R11: el supuesto roto avisa; uno ya explicado no vuelve a pedir
    que alguien lo investigue)."""
    conocidos = HUECOS_RUD_CONOCIDOS if conocidos is None else conocidos
    dias = sorted(r[0] for r in conn.execute(
        f"SELECT DISTINCT {col_fecha} FROM {tabla} WHERE {col_fecha} IS NOT NULL"))
    if len(dias) < 2:
        return []
    ini, fin = date.fromisoformat(dias[0]), date.fromisoformat(dias[-1])
    esperados = {(ini + timedelta(days=i)).isoformat()
                 for i in range((fin - ini).days + 1)}
    faltan = sorted(esperados - set(dias))
    avisos = []
    nuevos = [d for d in faltan if d not in conocidos]
    if nuevos:
        avisos.append({
            "tipo": "hueco_de_captura", "nivel": "alta",
            "texto": f"{tabla} tiene {len(nuevos)} día(s) sin captura sin "
                     f"explicar: {', '.join(nuevos)}. Si es legítimo (corrida "
                     f"perdida, cron retrasado), anotarlo en "
                     f"HUECOS_RUD_CONOCIDOS (common.py) con su porqué.",
            "tabla": tabla, "dias": nuevos})
    documentados = [d for d in faltan if d in conocidos]
    if documentados:
        avisos.append({
            "tipo": "hueco_de_captura_documentado", "nivel": "info",
            "texto": f"{tabla}: {len(documentados)} día(s) sin captura, ya "
                     f"explicados — " + "; ".join(
                         f"{d}: {conocidos[d]}" for d in documentados),
            "tabla": tabla, "dias": documentados})
    return avisos


def colision_de_etiquetado_rud(conn) -> list[dict]:
    """¿Dos corridas de días distintos etiquetaron la MISMA captura del RUD?

    `dia_colombiano_consolidado()` ya se blinda contra el salto hacia
    adelante (cron tardío que se come un día), pero el blindaje abre una
    colisión hacia atrás: si HOY el cron dispara tarde y consolida 'D' (en
    vez de 'D-1', porque ya pasó el corte), y MAÑANA dispara a su hora y
    también calcula 'D' (porque resta un día desde 'D+1'), las dos corridas
    escriben `rud_daily` bajo el mismo `snapshot_date`. `INSERT OR REPLACE`
    hace que la segunda pise a la primera —es la captura más reciente, y ya
    es como se comporta hoy `ungrd_rud.py`—; nada se rompe (R13). Pero la
    pisada es muda: sin esto, nadie se entera de que una captura entera
    desapareció sin dejar rastro de que existió. Esto solo lo dice en voz
    alta (R11), en info porque no hay nada que decidir en caliente — la regla
    ya es "la segunda gana".

    La señal: `sources_log` registra un fetch por corrida (con su propio
    `ts`), así que contar los DÍAS DE FETCH distintos y compararlos contra
    los `snapshot_date` distintos de `rud_daily` descubre la colisión sin
    necesitar un vínculo explícito entre una fila de `sources_log` y la fila
    de `rud_daily` que produjo — que hoy no existe."""
    fetch_dias = {r[0][:10] for r in conn.execute(
        "SELECT ts FROM sources_log WHERE note='rud 2026T' AND http_status=200")}
    rud_dias = {r[0] for r in conn.execute(
        "SELECT DISTINCT snapshot_date FROM rud_daily")}
    if len(fetch_dias) <= len(rud_dias):
        return []
    return [{
        "tipo": "colision_etiquetado_rud", "nivel": "info",
        "texto": (f"sources_log registra capturas del RUD en {len(fetch_dias)} "
                  f"días distintos, pero rud_daily solo tiene "
                  f"{len(rud_dias)} snapshot_date: al menos una etiqueta se "
                  f"repitió (dos corridas calcularon el mismo día "
                  f"consolidado). La más reciente pisó a la anterior "
                  f"(INSERT OR REPLACE) — esto solo lo deja dicho."),
        "dias_de_fetch": len(fetch_dias), "dias_en_rud_daily": len(rud_dias)}]


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


def _men_sedes_capa_viva(snap: str) -> bool | None:
    """¿La capa SISE del MEN respondió con datos hoy, o sigue inaccesible?

    None si la corrida de hoy aún no dejó snapshot que mirar (no ha llegado a
    ese paso, o falló antes de archivar nada). El snapshot existe SIEMPRE que
    hubo un HTTP 200 con cuerpo —incluido el cuerpo de error que ArcGIS
    contesta con 200—, así que `fetch()` lo archiva igual (R4) y esto solo lo
    lee, sin red propia.
    """
    f = SNAPSHOTS / snap / "men_sedes_offset0.json"
    if not f.exists():
        return None
    try:
        datos = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    return bool(datos.get("features"))


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
    mismo, así que la que las vigila no puede ser la misma que las usa.

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


HDX_SEARCH = "https://data.humdata.org/api/3/action/package_search"
# Varios términos en OR, nunca uno solo: un dataset puede etiquetarse "sismo"
# y no "earthquake", o al revés — fijar la búsqueda a uno perdería al otro.
HDX_TERMINOS = ("terremoto", "sismo", "earthquake")
HDX_PAIS = "col"          # grupo de país en HDX: ISO3 en minúsculas


def _primera_corrida_del_watcher(conn, watcher: str) -> bool:
    """¿Es la primera vez que este watcher corre?

    Sin esto, la primera corrida convertiría en «alerta nueva» cada dataset o
    tablero que la fuente YA tenía publicado antes de que el monitor empezara
    a mirar —de HDX salen varios el primer día de prueba (30-ago-2026)—, que
    es ruido y no noticia. Mismo patrón que `_institucionales_nuevos`: sin
    captura previa no se alerta, se siembra la línea base en silencio.
    """
    return conn.execute(
        "SELECT 1 FROM fuentes_watch WHERE watcher=? LIMIT 1", (watcher,)
    ).fetchone() is None


def _watcher_silencioso(conn, watcher: str, nota: str, nombre_fuente: str) -> dict | None:
    """¿Lleva este vigilante más de 48 h sin una respuesta 200? (R15)

    Sin esto, un watcher que deja de funcionar —clave rotada, user-agent
    bloqueado, endpoint movido— degrada en silencio para siempre: R13 permite
    que la corrida no se rompa, pero nada obligaba a que alguien se enterase
    de que dejó de mirar. Mismo patrón que `worker_balances_silencio` (bloque
    5 de `run()`), aplicado a los dos watchers nuevos en vez de duplicarlo.
    """
    ultimo_ok = conn.execute(
        "SELECT MAX(ts) FROM sources_log WHERE note=? AND http_status=200",
        (nota,)).fetchone()[0]
    if ultimo_ok is None:
        return None        # nunca respondió bien: no hay «desde cuándo» que contar
    edad_h = (datetime.now(timezone.utc)
              - datetime.fromisoformat(ultimo_ok.replace("Z", "+00:00"))
              ).total_seconds() / 3600
    if edad_h <= 48:
        return None
    return {
        "tipo": f"{watcher}_watcher_silencio", "nivel": "alta",
        "texto": f"El vigilante de {nombre_fuente} lleva {edad_h:.0f} h sin "
                 f"una respuesta 200: revisar si la fuente cambió su "
                 f"contrato o bloqueó al monitor.",
        "watcher": watcher, "horas": round(edad_h)}


def datasets_hdx_nuevos(conn, snap: str) -> list[dict]:
    """Datasets nuevos o revisados en HDX (data.humdata.org) sobre el terremoto.

    HDX es el catálogo humanitario donde las organizaciones publican sin que
    el monitor las busque una a una: así habría cantado los datos de Microsoft
    el 12-ago-2026, que hoy solo se encuentran leyendo a mano. La búsqueda
    combina el grupo de país (Colombia) con varios términos en OR.

    Sin clave: `package_search` de CKAN es pública. R4: la petición entera pasa
    por `fetch_json`, con su snapshot del listado del día.
    """
    primera = _primera_corrida_del_watcher(conn, "hdx")
    q = " OR ".join(HDX_TERMINOS)
    st, d = fetch_json(HDX_SEARCH, {
        "q": q, "fq": f"groups:{HDX_PAIS}", "sort": "metadata_modified desc",
        "rows": 30,
    }, note="watcher hdx", snapshot_name="hdx_search.json", conn=conn)
    if st != 200 or not d or not d.get("success"):
        aviso = _watcher_silencioso(conn, "hdx", "watcher hdx", "HDX/CKAN")
        return [aviso] if aviso else []
    avisos = []
    for r in (((d.get("result") or {}).get("results")) or []):
        ext_id = r.get("id")
        if not ext_id:
            continue
        titulo = r.get("title") or r.get("name") or ext_id
        org = ((r.get("organization") or {}).get("title")
               or "organización sin identificar")
        url = f"https://data.humdata.org/dataset/{r.get('name') or ext_id}"
        modif = r.get("metadata_modified")
        previa = conn.execute(
            "SELECT modificado FROM fuentes_watch"
            " WHERE watcher='hdx' AND external_id=?", (ext_id,)).fetchone()
        if not primera:
            if previa is None:
                avisos.append({
                    "tipo": "hdx_dataset_nuevo", "nivel": "alta",
                    "texto": f"Fuente nueva en HDX: «{titulo}» ({org}) — {url}",
                    "titulo": titulo, "organizacion": org, "url": url})
            elif modif and previa[0] != modif:
                avisos.append({
                    "tipo": "hdx_dataset_revisado", "nivel": "info",
                    "texto": f"HDX revisó «{titulo}» ({org}) — {url}",
                    "titulo": titulo, "organizacion": org, "url": url})
        conn.execute(
            "INSERT INTO fuentes_watch (watcher, external_id, titulo,"
            " organizacion, url, modificado, first_seen, last_seen)"
            " VALUES ('hdx',?,?,?,?,?,?,?)"
            " ON CONFLICT(watcher, external_id) DO UPDATE SET"
            " titulo=excluded.titulo, organizacion=excluded.organizacion,"
            " url=excluded.url, modificado=excluded.modificado,"
            " last_seen=excluded.last_seen",
            (ext_id, titulo, org, url, modif, snap, snap))
    return avisos


ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search"
# Cuatro señales combinadas para no fijar la búsqueda a un único término: el
# tablero puede llamarse por su sigla (ERES), por su nombre completo
# («establecimientos de salud»), por quien lo publica (MinSalud, MSPS, o la
# propia cuenta oficial sispro_geo) o por el evento (sismo/terremoto/
# Colombia). Medido el 30-ago-2026: sin la segunda cláusula de entidad, la
# búsqueda libre de arcgis.com confunde «ERES» con el pronombre español
# —cualquier texto que contenga la palabra «eres» entra—; sin la tercera trae
# tableros reales de MinSalud que no tienen nada que ver con el terremoto
# (COVID-19, vacunación, zoonosis). Las cuatro juntas no garantizan cero
# falsos positivos —el buscador de arcgis.com no es exacto—, así que la
# alerta se redacta como candidato a revisar, no como hallazgo confirmado.
ARCGIS_QUERY = (
    '(ERES OR "establecimientos de salud" OR "evaluación de establecimientos'
    ' de salud") AND (MinSalud OR MSPS OR OPS OR owner:sispro_geo)'
    ' AND (sismo OR terremoto OR Colombia)')


def tablero_arcgis_eres(conn, snap: str) -> list[dict]:
    """¿Apareció el tablero ArcGIS ERES/MinSalud de establecimientos de salud?

    La OPS está ayudando a construirlo junto al Ministerio de Salud; el
    30-ago-2026 no existe todavía en el catálogo público de arcgis.com. El día
    que se publique, alguien tiene que enterarse sin ir a buscarlo a mano.

    Solo se alerta la PRIMERA vez que se ve un item, no en cada revisión: a
    diferencia de HDX, un tablero ArcGIS se edita todo el tiempo mientras se
    construye, y avisar de cada `modified` sería una alerta diaria mientras
    dure la obra.
    """
    primera = _primera_corrida_del_watcher(conn, "arcgis_eres")
    st, d = fetch_json(ARCGIS_SEARCH, {
        "q": ARCGIS_QUERY, "f": "json", "num": 20,
        "sortField": "modified", "sortOrder": "desc",
    }, note="watcher arcgis eres", snapshot_name="arcgis_eres_search.json",
        conn=conn)
    if st != 200 or not d or d.get("error"):
        aviso = _watcher_silencioso(conn, "arcgis_eres", "watcher arcgis eres",
                                    "arcgis.com (tablero ERES/MinSalud)")
        return [aviso] if aviso else []
    avisos = []
    for r in d.get("results") or []:
        ext_id = r.get("id")
        if not ext_id:
            continue
        ya_visto = conn.execute(
            "SELECT 1 FROM fuentes_watch"
            " WHERE watcher='arcgis_eres' AND external_id=?",
            (ext_id,)).fetchone()
        titulo = r.get("title") or ext_id
        owner = r.get("owner") or "propietario sin identificar"
        url = f"https://www.arcgis.com/home/item.html?id={ext_id}"
        if not primera and not ya_visto:
            tipo = r.get("type") or "item"
            avisos.append({
                # "media", no "alta": la búsqueda libre de arcgis.com no es
                # exacta y esto es un candidato a revisar, no un hallazgo
                # confirmado (ver ARCGIS_QUERY) — "alta" dispararía push y
                # Telegram a todos los suscriptores por algo que un humano
                # aún no confirmó. Sigue publicado en alerts.json/RSS, visible
                # para quien lo lea. Nivel a confirmar con criterio editorial
                # (docs/DECISIONES.md, 2026-08-30).
                "tipo": "arcgis_eres_candidato", "nivel": "media",
                "texto": f"Posible tablero ERES/MinSalud en ArcGIS: «{titulo}»"
                         f" ({tipo}, {owner}) — revisar si es el que construye"
                         f" la OPS: {url}",
                "titulo": titulo, "item_type": tipo, "owner": owner, "url": url})
        conn.execute(
            "INSERT INTO fuentes_watch (watcher, external_id, titulo,"
            " organizacion, url, modificado, first_seen, last_seen)"
            " VALUES ('arcgis_eres',?,?,?,?,?,?,?)"
            " ON CONFLICT(watcher, external_id) DO UPDATE SET"
            " titulo=excluded.titulo, organizacion=excluded.organizacion,"
            " url=excluded.url, modificado=excluded.modificado,"
            " last_seen=excluded.last_seen",
            (ext_id, titulo, owner, url, r.get("modified"), snap, snap))
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

    # 6d) ¿se perdió algún día entre capturas, o dos corridas etiquetaron la
    # misma? Ver docs/DECISIONES.md (hueco del 26-ago-2026) y el docstring de
    # `dia_colombiano_consolidado`.
    alerts.extend(huecos_de_captura(conn))
    alerts.extend(colision_de_etiquetado_rud(conn))

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

    # 11) HDX/CKAN: datasets nuevos o revisados sobre el terremoto. Un feed que
    # falla no rompe la corrida (R13) — es la fuente misma de una vigilancia,
    # así que su propio silencio no puede ser fatal.
    try:
        alerts.extend(datasets_hdx_nuevos(conn, snap))
    except sqlite3.Error:
        pass

    # 12) ArcGIS: ¿nació el tablero ERES/MinSalud de establecimientos de salud
    # que la OPS ayuda a construir? Mientras no exista, esto no encuentra nada
    # que avisar — el día que aparezca, es justo la noticia que este vigilante
    # existe para cazar.
    try:
        alerts.extend(tablero_arcgis_eres(conn, snap))
    except sqlite3.Error:
        pass

    # 13) OPS: sitrep nuevo sin transcribir (la OPS no tiene API — cada sitrep
    # hay que verlo, descubrir su tabla y transcribirla a mano) y silencio
    # prolongado de la serie (R15, umbral propio: 15 días, más laxo que el
    # general porque la propia serie ya dejó pasar 7 días naturales entre dos
    # sitrep sin haber cerrado).
    from sources import ops_salud
    for n in ops_salud.sitreps_nuevos(conn):
        alerts.append({
            "tipo": "ops_sitrep_nuevo_sin_transcribir", "nivel": "alta",
            "texto": (f"La OPS publicó el Informe de Situación {n} sobre el "
                      f"terremoto y el monitor no lo ha transcrito todavía: "
                      f"revisar su tabla de establecimientos de salud y "
                      f"añadirla a data/documentos/ops_salud/."),
            "sitrep": n})
    dias = ops_salud.dias_desde_ultimo_sitrep(snap)
    if dias is not None and dias > 15 and not ops_salud.SERIE_CERRADA:
        alerts.append({
            "tipo": "ops_serie_silenciosa", "nivel": "media",
            "texto": (f"La OPS lleva {dias} día(s) sin publicar un sitrep "
                      f"nuevo del terremoto. Puede haber cerrado la serie sin "
                      f"anunciarlo — si se confirma, marcar "
                      f"ops_salud.SERIE_CERRADA con la fecha y el porqué."),
            "dias": dias})

    # 14) MEN/SISE: la capa de sedes educativas (y el ítem del tablero
    # público que la enseñaba) quedaron inaccesibles en ArcGIS el
    # 31-ago-2026 (docs/DECISIONES.md). Se certifica INACCESIBILIDAD, no
    # intención — por eso la corrida sigue preguntando cada día y esto vigila
    # los dos sentidos: mientras siga muda, un aviso "info" nombra la causa
    # conocida para que el estado conste sin ensordecer el resto (R11: ya
    # explicado no vuelve a pedir que alguien lo investigue); si vuelve a
    # responder con datos, "alta" — un regreso también es noticia.
    from common import CAPA_RETIRADA_DESDE
    viva = _men_sedes_capa_viva(snap)
    if viva is False:
        alerts.append({
            "tipo": "men_sedes_capa_inaccesible", "nivel": "info",
            "texto": (f"La capa de sedes educativas del MEN (SISE) sigue "
                      f"inaccesible en ArcGIS desde el {CAPA_RETIRADA_DESDE} "
                      f"— el ítem del tablero público también lo está. El "
                      f"monitor conserva el corte del 30-ago-2026 y pregunta "
                      f"a diario por si reaparece.")})
    elif viva is True:
        alerts.append({
            "tipo": "men_sedes_capa_reaparecida", "nivel": "alta",
            "texto": (f"La capa de sedes educativas del MEN (SISE) volvió a "
                      f"responder con datos, tras estar inaccesible desde el "
                      f"{CAPA_RETIRADA_DESDE}. Revisar si es la misma capa u "
                      f"otra, y reanudar la serie.")})

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
