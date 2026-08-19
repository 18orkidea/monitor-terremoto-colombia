"""Genera el HTML que hoy pinta el JavaScript: fichas municipales y tablas.

Por qué existe: los buscadores de IA (GPTBot, ClaudeBot, PerplexityBot) no
ejecutan JavaScript, y Google lo renderiza tarde y con presupuesto limitado.
Si la cifra no está en el HTML servido, para ellos no existe. Este módulo pone
el dato dentro del HTML; el JS del sitio pasa a filtrar y ordenar lo que ya
está escrito, en vez de crearlo.

Se ejecuta en el build (escribe en `dist/`), nunca sobre `site/*.html`: un HTML
que cambiase entero cada día destruiría el blame, y el dato ya está versionado
en `data/public/`, así que estas páginas son reconstruibles desde cualquier
commit.

Solo stdlib (R14).
"""
from __future__ import annotations

import html
import json
import math
import re
import unicodedata
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"

EPICENTRO = (4.8436, -76.2422)          # San José del Palmar (Chocó)
CHATMAP = "https://chatmap.hotosm.org/colombia.html"
BASE = ""                               # el sitio vive en la raíz del dominio
DATOS = "/data/public"                  # exportes públicos, fuera de site/
MIN_CAPTURAS_GRAFICA = 5                # antes de eso, una recta entre dos puntos no es tendencia
RADIO_MUNICIPIO_M = 25000               # más allá, un punto no se atribuye a ninguna cabecera


# --------------------------------------------------------------- utilidades
def fmt(n, dec: int = 0) -> str:
    """Formato es-CO sin `locale` (depende del sistema y en CI no está).

    Espejo exacto de `UI.fmt` en site/ui.js, que usa `toLocaleString` con
    `maximumFractionDigits`: los decimales a cero NO se imprimen («7», no «7,0»).
    Si tocas uno, mira el otro — `tests/test_render_html.py` compara ambos.

    R3: la ausencia de dato es «—», jamás 0."""
    if n is None:
        return "—"
    s = f"{float(n):,.{dec}f}"
    if dec:                                   # maximumFractionDigits: quita los ceros
        s = s.rstrip("0").rstrip(".")
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# Libro de estilo, 10.1: del cero al nueve con letras, de 10 en adelante en
# guarismos. Vale para la prosa; en tablas y cuadros van siempre en guarismos
# (10.2), así que esta función no sustituye a fmt().
_LETRAS = ("cero", "una", "dos", "tres", "cuatro", "cinco",
           "seis", "siete", "ocho", "nueve")


def fmt_prosa(n, femenino: bool = False) -> str:
    """Cifra tal como se escribe dentro de una frase."""
    if n is None:
        return "—"
    entero = int(n)
    if entero != n or not 0 <= entero <= 9:
        return fmt(n)
    if entero == 1:
        return "una" if femenino else "un"
    return _LETRAS[entero]


def pct(n) -> str:
    """Porcentaje con un decimal, espejo de `UI.pct`.

    Una proporción diminuta pero real jamás se redondea a «0 %»: un municipio con
    damnificados no puede leerse como municipio sin damnificados. El espacio antes
    del signo es el uso de la RAE y el que ya emplea todo el sitio."""
    if n is None:
        return "—"
    if 0 < n < 0.05:
        return "<0,1 %"
    return fmt(n, 1) + " %"


def e(s) -> str:
    """Escapa TODO lo que venga de fuera: los titulares son texto de terceros."""
    return html.escape(str(s), quote=True)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "-".join(x for x in "".join(c if c.isalnum() else " " for c in s).split())


def norm_busqueda(s: str) -> str:
    """Espejo de `UI.norm`: NFD, fuera los diacríticos, minúsculas.

    Va escrita en cada fila como `data-buscar` para que el filtro del navegador
    trabaje sobre el DOM ya renderizado en vez de reconstruirlo."""
    d = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in d if not unicodedata.combining(c)).lower()


def distancia_m(a: tuple, b: tuple) -> float:
    """Haversine en metros."""
    r = 6371000
    la1, lo1 = map(math.radians, a)
    la2, lo2 = map(math.radians, b)
    return 2 * r * math.asin(math.sqrt(
        math.sin((la2 - la1) / 2) ** 2 +
        math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def medio_de_titular(item: dict) -> str | None:
    """En los feeds de Google News el campo `medio` guarda el feed, no el medio:
    el medio real va al final del titular tras « - ». Sin sufijo, no hay dato (R3)."""
    titulo = item.get("titulo") or ""
    if " - " in titulo:
        return titulo.rsplit(" - ", 1)[1].strip()[:40]
    return None


def _leer(nombre: str):
    return json.loads((PUBLIC / nombre).read_text(encoding="utf-8"))


# ------------------------------------------------- atribución de puntos
def asigna_a_municipios(features: list, municipios: list) -> dict:
    """Atribuye cada punto a la cabecera municipal más próxima.

    Salvedad documentada: no tenemos polígonos municipales, solo cabeceras, así
    que esto es proximidad, no contención. Los puntos a más de RADIO_MUNICIPIO_M
    de cualquier cabecera del área de influencia no se atribuyen a nadie: cuentan
    en el total, pero no en la tabla. Con los polígonos DIVIPOLA esto pasaría de
    aproximación a exactitud."""
    cabeceras = [(m["municipio"], m["lat"], m["lon"]) for m in municipios]
    conteo: dict[str, int] = {}
    huerfanos = 0
    for f in features:
        geom = f.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        mejor, mejor_d = None, float("inf")
        for nombre, mlat, mlon in cabeceras:
            d = distancia_m((lat, lon), (mlat, mlon))
            if d < mejor_d:
                mejor_d, mejor = d, nombre
        if mejor_d > RADIO_MUNICIPIO_M:
            huerfanos += 1
        else:
            conteo[mejor] = conteo.get(mejor, 0) + 1
    conteo["__huerfanos__"] = huerfanos
    return conteo


# --------------------------------------------------------------- mapa (SVG)
def mapa_svg(muni: dict, zonas: list, ciudadanos: list, ancho=680, alto=430) -> str:
    """Mapa estático del municipio frente a las zonas con producto satelital.

    SVG generado aquí, no Leaflet: se indexa, se lee sin JavaScript y pesa unos
    pocos KB. Noventa fichas con mapa interactivo y sus geojson harían el sitio
    impracticable justo cuando estamos arreglando el peso.

    Cuando no hay daño que pintar, el mapa cuenta la ausencia: se ve el municipio
    fuera de toda zona analizada."""
    lat0, lon0 = muni["lat"], muni["lon"]
    puntos = [(lat0, lon0), EPICENTRO] + [(la, lo) for la, lo, _ in ciudadanos]
    for _, coords in zonas:
        puntos += [(y, x) for x, y in coords]
    lats = [p[0] for p in puntos]
    lons = [p[1] for p in puntos]
    dlat = (max(lats) - min(lats)) or 0.1
    dlon = (max(lons) - min(lons)) or 0.1
    caja = (min(lats) - dlat * .22, max(lats) + dlat * .22,
            min(lons) - dlon * .22, max(lons) + dlon * .22)
    k = math.cos(math.radians(lat0))                      # longitud se acorta con la latitud
    escala = min(ancho / ((caja[3] - caja[2]) * k), alto / (caja[1] - caja[0]))
    ox = (ancho - (caja[3] - caja[2]) * k * escala) / 2
    oy = (alto - (caja[1] - caja[0]) * escala) / 2

    def proyecta(lat, lon):
        return (ox + (lon - caja[2]) * k * escala, oy + (caja[1] - lat) * escala)

    nombre = muni["municipio"]
    # `mapa-estatico` es la clase compartida de styles.css: de ella salen el ancho
    # fluido, el halo de los rótulos y los tamaños que crecen en pantalla estrecha
    o = [f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg" role="img"'
         f' aria-labelledby="mapa-t mapa-d" class="mapa-estatico">',
         f'<title id="mapa-t">Situación de {e(nombre)} frente a las zonas con producto'
         f' satelital de daño</title>',
         f'<desc id="mapa-d">Mapa de situación: {e(nombre)}, el epicentro del sismo, las zonas'
         f' con producto satelital de daño más próximas y los reportes ciudadanos'
         f' georreferenciados del entorno.</desc>',
         f'<rect width="{ancho}" height="{alto}" fill="var(--surface-1)"/>']
    for i in range(1, 5):
        o.append(f'<line x1="0" y1="{alto*i/5:.0f}" x2="{ancho}" y2="{alto*i/5:.0f}"'
                 f' stroke="var(--grid)" stroke-width="1"/>')
        o.append(f'<line x1="{ancho*i/5:.0f}" y1="0" x2="{ancho*i/5:.0f}" y2="{alto}"'
                 f' stroke="var(--grid)" stroke-width="1"/>')
    # Colocación de rótulos: dos textos sobre el mismo punto no los salva ni el
    # halo. Se reservan primero los sitios que no se pueden mover —el epicentro,
    # la chincheta del municipio y su nombre, que es el rótulo que da sentido a
    # la ficha— y las zonas colocan los suyos donde quede hueco.
    ex, ey = proyecta(*EPICENTRO)
    mx, my = proyecta(lat0, lon0)
    ty = my - 28
    etiquetas: list[tuple[float, float]] = [(ex, ey + 26), (mx, my), (mx, ty)]

    def libre(x: float, y: float) -> bool:
        return not any(abs(lx - x) < 110 and abs(ly - y) < 30 for lx, ly in etiquetas)

    for zona, coords in zonas:
        d = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % proyecta(y, x)
                     for i, (x, y) in enumerate(coords)) + " Z"
        cx, cy = proyecta(sum(y for _, y in coords) / len(coords),
                          sum(x for x, _ in coords) / len(coords))
        pts = [proyecta(y, x) for x, y in coords]
        ancho_px = max(px for px, _ in pts) - min(px for px, _ in pts)
        alto_px = max(py for _, py in pts) - min(py for _, py in pts)
        o.append(f'<path d="{d}" fill="var(--good)" fill-opacity="0.16"'
                 f' stroke="var(--good)" stroke-width="1.5"/>')
        minusculo = max(ancho_px, alto_px) < 14
        if minusculo:
            o.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="9" fill="var(--good)"'
                     f' fill-opacity="0.18" stroke="var(--good)" stroke-width="1.5"/>')
        # el rótulo va debajo del anillo cuando la zona es un punto, y centrado
        # cuando el polígono tiene superficie para sostenerlo
        # escalera de posiciones: dos AOI de la misma ciudad caen casi en el mismo
        # píxel, así que hacen falta más peldaños que arriba/abajo
        saltos = (26, -42, 60, -76, 94, -110) if minusculo else (0, 30, -46, 64, -80)
        opciones = [(cy - 6 + dy, cy + 12 + dy) for dy in saltos]
        y1, y2 = next((par for par in opciones
                       if libre(cx, par[0]) and libre(cx, par[1])), opciones[0])
        o.append(f'<text x="{cx:.0f}" y="{y1:.0f}" class="m-lbl" text-anchor="middle">{e(zona)}</text>')
        o.append(f'<text x="{cx:.0f}" y="{y2:.0f}" class="m-sub" text-anchor="middle">'
                 f'con producto satelital</text>')
        etiquetas += [(cx, y1), (cx, y2)]
    o.append(f'<path d="M{ex:.0f} {ey-9:.0f} l2.6 5.8 6.4.7-4.8 4.3 1.4 6.2-5.6-3.2-5.6 3.2'
             f' 1.4-6.2-4.8-4.3 6.4-.7Z" fill="var(--critical)"/>')
    o.append(f'<text x="{ex:.0f}" y="{ey+26:.0f}" class="m-sub" text-anchor="middle">'
             f'epicentro M7,4</text>')
    for la, lo, _ in ciudadanos:
        x, y = proyecta(la, lo)
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="var(--s7)" fill-opacity="0.75"/>')
    o.append(f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="17" fill="var(--s8)" fill-opacity="0.16"/>')
    o.append(f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="6.5" fill="var(--s8)"'
             f' stroke="var(--surface-1)" stroke-width="2"/>')
    o.append(f'<text x="{mx:.0f}" y="{ty:.0f}" class="m-name" text-anchor="middle">{e(nombre)}</text>')
    o.append(barra_escala(escala, ancho, alto))
    o.append("</svg>")
    return "\n".join(o)


def barra_escala(escala: float, ancho: int, alto: int) -> str:
    """Barra de escala del mapa.

    Sin ella «a 23 km» es una cifra sin traducción visual: quien mira no puede
    juzgar si el municipio está al lado de la zona analizada o a un día de
    camino. Se elige el escalón redondo cuya barra mida al menos 70 px."""
    px_por_m = escala / 111320.0                       # 1° de latitud ≈ 111,32 km
    km = next((v for v in (1, 2, 5, 10, 20, 50, 100, 200)
               if v * 1000 * px_por_m >= 70), 200)
    largo = km * 1000 * px_por_m
    x0, y0 = 16, alto - 18
    x1 = x0 + largo
    t = ('stroke="var(--ink-2)" stroke-width="1.6" stroke-linecap="square"')
    return (f'<g aria-hidden="true">'
            f'<line x1="{x0}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y0:.0f}" {t}/>'
            f'<line x1="{x0}" y1="{y0-5:.0f}" x2="{x0}" y2="{y0+5:.0f}" {t}/>'
            f'<line x1="{x1:.0f}" y1="{y0-5:.0f}" x2="{x1:.0f}" y2="{y0+5:.0f}" {t}/>'
            f'<text x="{(x0 + x1) / 2:.0f}" y="{y0-10:.0f}" class="m-sub"'
            f' text-anchor="middle">{fmt(km)} km</text></g>')


# ------------------------------------------- cabecera y pie compartidos
# `common.js` los inyecta en las páginas del sitio; aquí se escriben en el HTML
# porque una ficha tiene que leerse con el JavaScript apagado. Mismas clases
# (#site-nav, #site-footer) y mismos estilos: es la misma barra, no una copia
# parecida. Los botones que solo existen con JS (🔔 alertas, ↗ compartir) no
# aparecen; tampoco los dos enlaces cuya URL vive en `site/ui.js`, para no
# duplicar constantes entre dos lenguajes sin nada que vigile la copia.
PAGINAS = [("index.html", "🗺️ Mapa"), ("municipios.html", "🏘️ Municipios"),
           ("rud.html", "🏛️ RUD"), ("balances.html", "📊 Balances"),
           ("noticias.html", "📰 Titulares")]
REPO = "https://github.com/18orkidea/monitor-terremoto-colombia"


def nav_estatico(activa: str = "municipios.html") -> str:
    def enlace(href: str, txt: str) -> str:
        cls = ' class="activa"' if href == activa else ""
        return f'<a href="{BASE}/{href}"{cls}>{txt}</a>'

    enlaces = "".join(enlace(h, t) for h, t in PAGINAS)
    return (f'<nav id="site-nav" aria-label="Navegación del sitio">'
            f'<a class="brand" href="{BASE}/"><strong>Monitor de brechas</strong>'
            f'<span>Terremoto de Colombia M7.4 · 10-ago-2026</span></a>'
            f'<div class="nav-links">{enlaces}'
            f'<a href="{CHATMAP}" target="_blank" rel="noopener" class="nav-cta">'
            f'📍 Reportar daño</a>'
            f'<a href="{REPO}" target="_blank" rel="noopener" '
            f'title="Código y datos abiertos">GitHub</a>'
            f'<a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener" '
            f'title="Apoya los servidores y la recolección de datos">☕</a>'
            f'</div></nav>')


def pie_estatico() -> str:
    return (
        '<div id="site-footer"><div class="sf-cols">'
        '<div><strong>Monitor de brechas de reporte</strong><br>'
        'Observatorio abierto del terremoto M7.4 de Colombia (10-ago-2026). '
        'Cruza satélite, reporte ciudadano, prensa y fuentes oficiales — con cada cifra '
        'rastreable a su origen.</div>'
        '<div><strong>Secciones</strong><br>'
        f'<a href="{BASE}/index.html">Mapa y cruce por zona</a><br>'
        f'<a href="{BASE}/municipios.html">Municipios del área de influencia</a><br>'
        f'<a href="{BASE}/rud.html">RUD: registro oficial día a día</a><br>'
        f'<a href="{BASE}/balances.html">Balances en medios y comparativa</a><br>'
        f'<a href="{BASE}/noticias.html">Titulares por zona</a><br>'
        f'<a href="{BASE}/index.html#glosario">Glosario</a> · '
        f'<a href="{BASE}/index.html#metodologia">Metodología</a></div>'
        '<div><strong>Datos abiertos (CC BY 4.0)</strong><br>'
        f'<a href="{DATOS}/crosscheck.csv" download>CSV del cruce</a><br>'
        f'<a href="{DATOS}/monitor.json" target="_blank">JSON del monitor</a><br>'
        f'<a href="{DATOS}/rud.json" target="_blank">Histórico del RUD</a> · '
        f'<a href="{DATOS}/divipola_coords.json" target="_blank">Catálogo DIVIPOLA</a><br>'
        f'<a href="{DATOS}/alerts.rss" target="_blank" rel="noopener">RSS de alertas</a><br>'
        f'<a href="{REPO}" target="_blank" rel="noopener">Repositorio y snapshots</a></div>'
        '</div>'
        '<p class="sf-line">🇨🇴 ❤️ Mantenido por '
        '<a href="https://col.social/@jp" target="_blank" rel="me noopener">@jp@col.social</a> '
        'con apoyo de <a href="https://orkidea.eu" target="_blank" rel="noopener">Orkidea</a>. '
        'Las <a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener">'
        'donaciones ☕</a> mantienen servidores, scraping y recolección diaria de datos. '
        'Código MIT · datos derivados CC BY 4.0 · los datos crudos conservan la licencia '
        'de cada fuente.</p></div>')


# ------------------------------------------------------- datos de una ficha
def datos_ficha(nombre: str, ctx: dict) -> dict:
    muni = ctx["idx"][nombre]
    clave = nombre.upper()

    serie = []
    for fecha in sorted(ctx["rud"]["detalle_diario"]):
        fila = next((x for x in ctx["rud"]["detalle_diario"][fecha]
                     if x["municipio"].upper() == clave), None)
        if fila:
            serie.append((fecha, fila))

    zonas = []
    for f in ctx["aois"]:
        zona = f["properties"].get("aoi")
        if zona not in ctx["zonas_con_producto"]:
            continue                                    # R2: sin producto no hay cruce
        coords = f["geometry"]["coordinates"][0]
        centro = (sum(y for _, y in coords) / len(coords),
                  sum(x for x, _ in coords) / len(coords))
        d = distancia_m((muni["lat"], muni["lon"]), centro)
        if d < 90000:
            zonas.append((zona, coords, d))
    zonas.sort(key=lambda t: t[2])

    ciudadanos = []
    for f in ctx["chatmap"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        if distancia_m((muni["lat"], muni["lon"]), (lat, lon)) < 12000:
            ciudadanos.append((lat, lon, f["properties"]))

    titulares = sorted((x for x in ctx["noticias"] if nombre in (x.get("municipios") or [])),
                       key=lambda x: x.get("fecha") or "", reverse=True)

    ultimo = serie[-1][1] if serie else {}
    primero = serie[0][1] if serie else {}
    delta = pct_delta = None
    if len(serie) > 1 and primero.get("familias"):
        delta = ultimo["familias"] - primero["familias"]
        pct_delta = delta / primero["familias"] * 100

    return {
        "muni": muni, "serie": serie, "zonas": zonas, "ciudadanos": ciudadanos,
        "con_medio": sum(1 for *_, p in ciudadanos if p.get("media")),
        "mmis": [p["mmi"] for *_, p in ciudadanos if p.get("mmi") is not None],
        "titulares": titulares, "ultimo": ultimo, "primero": primero,
        "delta": delta, "pct_delta": pct_delta,
        "satelite": ctx["conteo_satelite"].get(nombre, 0),
        "generado": ctx["rud"].get("generado", ""),
        "slug": slug(nombre),
    }


# Productos satelitales de daño que cubren el evento. Añadir uno es añadir una
# entrada aquí: `tests/test_render_html.py::TestSatelites` falla si aparece en
# los datos un campo `*_edificios` que esta tabla no contemple, para que ninguna
# ficha vuelva a afirmar «ningún producto satelital» cuando sí lo hay.
SATELITES = (
    {"clave": "copernicus", "nombre": "Copernicus EMS (EMSR916)",
     "campo": None},          # se cuenta por puntos dentro del municipio
    {"clave": "unosat", "nombre": "UNITAR-UNOSAT",
     "campo": "unosat_edificios"},
)


def satelites_con_dato(m: dict, n_copernicus: int) -> list:
    """Qué productos satelitales han reportado daño en este municipio."""
    vistos = []
    if n_copernicus:
        vistos.append(("Copernicus EMS (EMSR916)", n_copernicus))
    if m.get("unosat_edificios") is not None:
        vistos.append(("UNITAR-UNOSAT", m["unosat_edificios"]))
    return vistos


def parrafo_respuesta(d: dict) -> str:
    """El párrafo que citan los buscadores y los sistemas de IA: una idea por
    frase, cada una con su cifra, su fecha y su fuente."""
    m = d["muni"]
    nombre, depto = m["municipio"], m["departamento"]
    partes = []
    if m.get("rud_familias"):
        partes.append(
            f"{e(nombre)} ({e(depto)}) tiene <strong>{fmt(m['rud_familias'])} familias "
            f"({fmt(m['rud_personas'])} personas)</strong> inscritas como damnificadas en el "
            f"RUD de la UNGRD, el <strong>{fmt(m['tasa_rud_pct'], 2)}%</strong> de sus "
            f"{fmt(m['poblacion_2026'])} habitantes proyectados por el DANE para 2026. "
            f"El registro municipal declara {fmt(m['rud_viv_destruidas'])} viviendas destruidas "
            f"y {fmt(m['rud_viv_averiadas'])} averiadas. <strong>El RUD es un registro progresivo "
            f"que cargan las autoridades municipales y está sujeto a verificación posterior</strong>: mide inscripciones tramitadas, no daño comprobado.")
    else:
        partes.append(
            f"{e(nombre)} ({e(depto)}) <strong>no tiene inscripciones en el RUD de la UNGRD</strong> "
            f"en la última captura del monitor. Sin registro no significa sin daño: significa que "
            f"las autoridades municipales aún no han censado. Su población proyectada por el DANE "
            f"para 2026 es de {fmt(m['poblacion_2026'])} habitantes.")
    # La afirmación se construye desde SATELITES, no desde una fuente concreta:
    # el día que entre otro producto, la frase sigue siendo cierta sola.
    vistos = satelites_con_dato(m, d["satelite"])
    if vistos:
        detalle = "; ".join(f"{fmt(n)} edificios clasificados por {fuente}"
                            for fuente, n in vistos)
        partes.append(f"El daño está documentado por satélite: <strong>{detalle}</strong>.")
    else:
        cerca = (f" La zona analizada más próxima es {e(d['zonas'][0][0])}, a "
                 f"{fmt(d['zonas'][0][2] / 1000, 0)} kilómetros." if d["zonas"] else "")
        partes.append(
            f"<strong>Ningún producto satelital de daño ha reportado daños en {e(nombre)}"
            f"</strong>: ni el servicio de emergencias de Copernicus ni UNITAR-UNOSAT han "
            f"evaluado sus edificios.{cerca}")
    if d["ciudadanos"]:
        partes.append(
            f"La comunidad sí lo ha documentado: <strong>{fmt_prosa(len(d['ciudadanos']))} reportes "
            f"ciudadanos</strong> georreferenciados en el entorno, {fmt_prosa(d['con_medio'])} con foto o vídeo.")
    medios = {medio_de_titular(t) for t in d["titulares"]} - {None}
    if d["titulares"]:
        partes.append(f"La prensa recogida por el monitor suma {fmt_prosa(len(d['titulares']))} piezas "
                      f"sobre {e(nombre)}, de {fmt_prosa(len(medios))} medios identificados.")
    return " ".join(partes)


# ------------------------------------------------------------- contexto único
def contexto() -> dict:
    """Carga una sola vez todo lo que comparten las fichas y las tablas."""
    municipios = _leer("municipios.json")["items"]
    noticias = _leer("noticias.json")
    if isinstance(noticias, dict):
        noticias = noticias.get("items") or noticias.get("noticias") or []
    damage = _leer("damage_points.geojson")["features"]
    chatmap = _leer("chatmap.geojson")["features"]
    return {
        "municipios": municipios,
        "idx": {m["municipio"]: m for m in municipios},
        "rud": _leer("rud.json"),
        "aois": _leer("aois.geojson")["features"],
        "chatmap": chatmap,
        "noticias": noticias,
        "zonas_con_producto": {f["properties"].get("aoi") for f in damage},
        "conteo_satelite": asigna_a_municipios(damage, municipios),
        "conteo_ciudadanos": asigna_a_municipios(chatmap, municipios),
        "oficiales": _leer("oficiales.json") if (PUBLIC / "oficiales.json").exists() else {},
    }


def municipios_con_evidencia_puntual(ctx: dict) -> list:
    """Municipios con prueba georreferenciada dentro: satélite o comunidad.

    Es el criterio de la tabla de portada. Deja de organizarse por lo que el
    satélite decidió mirar y pasa a organizarse por dónde hay evidencia sobre
    el terreno, venga de donde venga."""
    sat, ciu = ctx["conteo_satelite"], ctx["conteo_ciudadanos"]
    nombres = {k for k in (set(sat) | set(ciu)) if not k.startswith("__")}
    filas = []
    for n in nombres:
        m = ctx["idx"][n]
        filas.append({**m, "n_satelite": sat.get(n, 0), "n_ciudadanos": ciu.get(n, 0)})
    filas.sort(key=lambda f: (f["n_satelite"] + f["n_ciudadanos"]), reverse=True)
    return filas


# ------------------------------------------------------------------ la ficha
def render_ficha(d: dict) -> str:
    """HTML completo de una ficha municipal.

    Usa los componentes compartidos de styles.css (.destacado, .aviso,
    .metric-strip, .mapa-estatico…): una misma idea se ve igual en cualquier
    página del sitio."""
    m = d["muni"]
    nombre, depto = m["municipio"], m["departamento"]
    url = f"https://brechas.orkidea.eu/municipio/{d['slug']}/"
    titulo = (f"Terremoto de Colombia 2026 en {nombre} ({depto}): damnificados, "
              f"daños y cobertura")
    descr = (f"{nombre} ({depto}): {fmt(m['rud_familias'])} familias inscritas en el RUD, "
             f"{fmt(m['rud_viv_averiadas'])} viviendas averiadas y "
             f"{'sin' if not d['satelite'] else 'con'} evaluación satelital de daño. "
             f"Cada cifra con su fuente y su fecha.")
    ld = {
        "@context": "https://schema.org", "@type": "Dataset", "url": url,
        "name": f"Damnificados y cobertura del terremoto de 2026 en {nombre} ({depto})",
        "description": descr, "inLanguage": "es", "temporalCoverage": "2026-08-10/..",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "spatialCoverage": {
            "@type": "Place", "name": f"{nombre}, {depto}, Colombia",
            "identifier": {"@type": "PropertyValue", "propertyID": "DIVIPOLA",
                           "value": m["divipola"]},
            "geo": {"@type": "GeoCoordinates", "latitude": m["lat"], "longitude": m["lon"]}},
        "isPartOf": {"@type": "Dataset", "name": "Monitor de brechas — Terremoto de Colombia 2026",
                     "url": "https://brechas.orkidea.eu/"}}
    migas = [("Monitor de brechas", f"{BASE}/"),
             ("Municipios", f"{BASE}/municipios.html"),
             (nombre, None)]
    ld_migas = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": txt,
             **({"item": f"https://brechas.orkidea.eu{href}"} if href else {})}
            for i, (txt, href) in enumerate(migas)]}

    o = ['<!DOCTYPE html>', '<html lang="es">', '<head>', '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>{e(titulo)} | Monitor de brechas</title>',
         f'<meta name="description" content="{e(descr)}">',
         '<meta name="robots" content="index, follow">',
         f'<link rel="canonical" href="{url}">',
         f'<meta property="og:url" content="{url}">',
         '<meta property="og:type" content="article">',
         '<meta property="og:locale" content="es_CO">',
         f'<meta property="og:title" content="{e(titulo)}">',
         f'<meta property="og:description" content="{e(descr)}">',
         f'<meta property="og:image" content="https://brechas.orkidea.eu{BASE}/og/portada.png">',
         '<meta name="twitter:card" content="summary_large_image">',
         f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>',
         f'<script type="application/ld+json">{json.dumps(ld_migas, ensure_ascii=False)}</script>',
         f'<link rel="stylesheet" href="{BASE}/styles.css">',
         f'<link rel="icon" type="image/png" href="{BASE}/icons/favicon.png">',
         '<meta name="theme-color" content="#101418">',
         '</head>', '<body>',
         nav_estatico(),
         '<div class="contenido">',
         '<nav class="migas" aria-label="Ruta"><ol>' + "".join(
             f'<li><a href="{href}">{e(txt)}</a></li>' if href
             else f'<li aria-current="page">{e(txt)}</li>'
             for txt, href in migas) + '</ol></nav>',
         '<header><div>',
         f'<h1>Terremoto de Colombia 2026 en {e(nombre)}, {e(depto)}</h1>',
         f'<p class="sub">Damnificados inscritos, daños y cobertura de cada fuente · '
         f'DIVIPOLA {e(m["divipola"])} · actualizado {e(d["generado"][:16])}</p>',
         '</div></header>',
         '<main>',
         f'<p class="destacado">{parrafo_respuesta(d)}</p>']

    tarjetas = [("Familias inscritas", fmt(m["rud_familias"]), "RUD · UNGRD · registro"),
                ("Personas", fmt(m["rud_personas"]),
                 f'{fmt(m["tasa_rud_pct"], 2)}% de la población'),
                ("Viviendas averiadas", fmt(m["rud_viv_averiadas"]),
                 f'{fmt(m["rud_viv_destruidas"])} destruidas'),
                ("Población 2026", fmt(m["poblacion_2026"]), "proyección DANE")]
    o.append('<div class="metric-strip">')
    for etiqueta, valor, sub in tarjetas:
        o.append(f'<div class="metric-card"><span>{etiqueta}</span><strong>{valor}</strong>'
                 f'<small>{sub}</small></div>')
    o.append('</div>')

    # ---- mapa de situación
    o.append('<section class="page-section">')
    o.append(f'<h2>Dónde está {e(nombre)} y qué ha mirado el satélite</h2>')
    # El SVG lleva al mapa interactivo de la portada, centrado en el municipio.
    # Es un enlace, no una carga: la ficha sigue sin descargar Leaflet ni los
    # geojson, que son megabytes que la mayoría de lectores no va a necesitar.
    destino = f"/?municipio={urllib.parse.quote(nombre)}#mapa"
    o.append(f'<a href="{destino}" class="mapa-enlace"'
             f' aria-label="Abrir {e(nombre)} en el mapa interactivo">')
    o.append(mapa_svg(m, [(z, c) for z, c, _ in d["zonas"]], d["ciudadanos"]))
    o.append("</a>")
    o.append('<p class="leyenda">'
             f'<span class="badge" style="--bc:var(--s8)">{e(nombre)}</span>'
             '<span class="badge" style="--bc:var(--good)">zona con producto satelital</span>'
             '<span class="badge" style="--bc:var(--s7)">reporte ciudadano</span>'
             '<span class="badge" style="--bc:var(--critical)">epicentro</span></p>')
    if not d["satelite"]:
        cerca = (f' La más próxima, {e(d["zonas"][0][0])}, está a '
                 f'{fmt(d["zonas"][0][2] / 1000, 0)} kilómetros.' if d["zonas"] else "")
        o.append(f'<p class="note">{e(nombre)} queda fuera de toda zona con producto satelital '
                 f'de daño.{cerca} Sin evaluación satelital no hay nada que cruzar: el registro '
                 f'municipal y los reportes de la comunidad son la única evidencia disponible.</p>')
    o.append('</section>')

    # ---- comunidad
    if d["ciudadanos"]:
        rango = (f' con intensidad percibida de {fmt(min(d["mmis"]), 1)} a '
                 f'{fmt(max(d["mmis"]), 1)} (MMI)' if d["mmis"] else "")
        o.append(f'<div class="aviso aviso--accion">'
                 f'<p><strong>{fmt_prosa(len(d["ciudadanos"]))} reportes ciudadanos</strong> '
                 f'georreferenciados en el entorno de {e(nombre)}, {d["con_medio"]} con foto '
                 f'o vídeo{rango}. <span class="badge">verificación automática superada · '
                 f'pendientes de revisión humana</span></p>'
                 f'<p>Donde el satélite no ha mirado, cada reporte cuenta. '
                 f'¿Estás en {e(nombre)}? <a href="{CHATMAP}" target="_blank" rel="noopener">'
                 f'<strong>Reporta daños con tu ubicación y foto por WhatsApp</strong></a> '
                 f'(ChatMap · OSM Colombia + UN Mappers + HOT). Tu reporte se publica con la '
                 f'coordenada redondeada a ~110 m, sin EXIF y sin datos personales.</p></div>')
    else:
        o.append(f'<div class="aviso aviso--accion"><p>Todavía <strong>no hay reportes '
                 f'ciudadanos</strong> georreferenciados en {e(nombre)}. '
                 f'{"Y ningún producto satelital ha reportado daños aquí: " if not d["satelite"] else ""}'
                 f'si estás en el municipio, tu reporte puede ser la primera evidencia sobre el '
                 f'terreno. <a href="{CHATMAP}" target="_blank" rel="noopener"><strong>Reporta '
                 f'daños con tu ubicación y foto por WhatsApp</strong></a> (ChatMap · OSM '
                 f'Colombia + UN Mappers + HOT).</p></div>')
    # ---- evolución del registro
    if d["serie"]:
        o.append('<section class="page-section">')
        o.append("<h2>Cómo avanza el registro oficial</h2>")
        if d["delta"] is not None:
            o.append(f'<p>Entre el {e(d["serie"][0][0])} y el {e(d["serie"][-1][0])}, las familias '
                     f'inscritas en {e(nombre)} pasaron de <strong>{fmt(d["primero"]["familias"])}'
                     f'</strong> a <strong>{fmt(d["ultimo"]["familias"])}</strong>: un salto del '
                     f'{fmt(d["pct_delta"], 0)}% en {len(d["serie"]) - 1} '
                     f'{"día" if len(d["serie"]) == 2 else "días"}. El RUD no mide cuánto se rompió '
                     f'el municipio: mide a qué velocidad las autoridades locales alcanzan a '
                     f'registrarlo, y ese registro se verifica después. Por eso <strong>que un municipio '
                     f'no aparezca no significa «sin daño», significa «sin registro aún»</strong>.</p>')
        o.append('<div class="tabla-scroll"><table>')
        o.append('<thead><tr><th>Captura</th><th class="num">Familias</th>'
                 '<th class="num">Personas</th><th class="num">Viv. destruidas</th>'
                 '<th class="num">Viv. averiadas</th></tr></thead><tbody>')
        for fecha, fila in d["serie"]:
            o.append(f'<tr><td>{e(fecha)}</td><td class="num">{fmt(fila["familias"])}</td>'
                     f'<td class="num">{fmt(fila["personas"])}</td>'
                     f'<td class="num">{fmt(fila["viv_destruidas"])}</td>'
                     f'<td class="num">{fmt(fila["viv_averiadas"])}</td></tr>')
        o.append("</tbody></table></div>")
        if len(d["serie"]) < MIN_CAPTURAS_GRAFICA:
            o.append(f'<p class="note">La gráfica de evolución aparece a partir de la '
                     f'{MIN_CAPTURAS_GRAFICA}.ª captura diaria: con {len(d["serie"])} solo '
                     f'dibujaría una recta entre dos puntos, no una tendencia.</p>')
        o.append("</section>")

    # ---- prensa
    if d["titulares"]:
        medios = {medio_de_titular(t) for t in d["titulares"]} - {None}
        o.append('<section class="page-section">')
        o.append(f"<h2>Qué publicó la prensa sobre {e(nombre)}</h2>")
        o.append(f'<p>{fmt(len(d["titulares"]))} piezas recogidas por el monitor, de '
                 f'{len(medios)} medios identificados. La prensa nunca equivale a un balance '
                 f'oficial: aquí consta quién publicó y cuándo, no qué se verificó.</p>')
        o.append('<div class="tabla-scroll"><table>')
        o.append('<thead><tr><th>Fecha</th><th>Titular</th><th>Medio</th></tr></thead><tbody>')
        for t in d["titulares"][:40]:
            medio = medio_de_titular(t)
            titular = t.get("titulo") or ""
            if medio:
                titular = titular.rsplit(" - ", 1)[0]
            o.append(f'<tr><td>{e((t.get("fecha") or "")[:10])}</td>'
                     f'<td><a href="{e(t.get("url") or "#")}" target="_blank" '
                     f'rel="noopener nofollow">{e(titular[:130])}</a></td>'
                     f'<td>{e(medio) if medio else "—"}</td></tr>')
        o.append("</tbody></table></div>")
        if len(d["titulares"]) > 40:
            o.append(f'<p class="note">Se muestran los 40 titulares más recientes de '
                     f'{fmt(len(d["titulares"]))}. El resto, en '
                     f'<a href="{BASE}/noticias.html">Titulares</a>.</p>')
        o.append("</section>")

    # ---- lo que no sabemos: la sección que ningún agregador tiene
    o.append('<section class="page-section">')
    o.append(f"<h2>Qué no sabemos de {e(nombre)}</h2>")
    o.append('<div class="aviso aviso--laguna"><ul>')
    if not satelites_con_dato(m, d["satelite"]):
        o.append(f'<li><strong>No hay evaluación satelital de daño.</strong> Ningún producto '
                 f'satelital ha clasificado los edificios de {e(nombre)}. No se puede afirmar '
                 f'cuántos están destruidos: solo cuántos declaró el registro municipal.</li>')
    if not m.get("dyfi_respuestas"):
        o.append(f'<li><strong>No hay reportes de intensidad percibida.</strong> Nadie ha '
                 f'respondido el cuestionario DYFI del USGS desde {e(nombre)}, así que falta la '
                 f'medida independiente de cuánto se sintió el sismo.</li>')
    if m.get("rud_familias"):
        o.append('<li><strong>El registro es progresivo y sigue abierto.</strong> Lo cargan las autoridades municipales —los damnificados no se autorregistran— y recoge '
                 'inscripciones de damnificados que se verifican después: son un mínimo conocido '
                 'sujeto a comprobación, no un balance cerrado ni una medición de daño.</li>')
    else:
        o.append(f'<li><strong>{e(nombre)} no está en el RUD todavía.</strong> Eso no dice nada '
                 f'sobre su daño: dice que el registro municipal aún no ha llegado.</li>')
    if d["ciudadanos"]:
        o.append('<li><strong>Los reportes ciudadanos no están validados a mano.</strong> Han '
                 'superado la verificación automática (intensidad plausible, dentro de zona, '
                 'temporalidad, duplicados por hash), pero nada se marca como validado sin '
                 'revisión humana.</li>')
    o.append("</ul></div></section>")

    # ---- trazabilidad
    o.append('<section class="page-section">')
    o.append("<h2>Fuentes y trazabilidad</h2>")
    o.append('<div class="tabla-scroll"><table><thead><tr><th>Dato</th><th>Fuente</th>'
             "<th>Naturaleza</th></tr></thead><tbody>"
             '<tr><td>Familias, personas y viviendas</td><td><a href="https://rud.gestiondelriesgo.gov.co/"'
             ' target="_blank" rel="noopener">RUD · UNGRD</a></td>'
             "<td>registro progresivo, verificación posterior</td></tr>"
             "<tr><td>Población 2026</td><td>DANE · proyecciones municipales por área</td>"
             "<td>estadística oficial</td></tr>"
             '<tr><td>Daño en edificios</td><td><a href="https://rapidmapping.emergency.copernicus.eu/EMSR916/"'
             ' target="_blank" rel="noopener">Copernicus EMS · EMSR916</a></td>'
             "<td>producto satelital (único activo sobre el evento)</td></tr>"
             f'<tr><td>Reportes ciudadanos</td><td><a href="{CHATMAP}" target="_blank" '
             'rel="noopener">ChatMap · OSM Colombia</a></td>'
             "<td>comunidad, sin validación humana</td></tr>"
             "<tr><td>Titulares</td><td>feeds abiertos del monitor y Google News municipal</td>"
             "<td>prensa · nunca equivale a balance oficial</td></tr>"
             "</tbody></table></div>")
    o.append('<p class="note">Cada petición queda registrada con su URL, su código HTTP, su '
             "huella sha256 y su fecha; los snapshots crudos se versionan en el repositorio "
             "público, así que cualquier cifra de esta página puede reconstruirse y rebatirse.</p>")
    o.append("</section>")
    o.append(f'<p class="note nota-pie"><a href="{BASE}/municipios.html">← Todos los '
             f'municipios del área de influencia</a></p>')
    o.append("</main></div>")
    o.append(pie_estatico())
    o.append("</body></html>")
    return "\n".join(o)


def es_elegible(nombre: str, ctx: dict) -> bool:
    """Solo hay ficha si el municipio tiene alguna señal.

    Sin señal no hay página: noventa páginas vacías serían contenido pobre y
    penalizarían al dominio entero."""
    m = ctx["idx"][nombre]
    return bool(m.get("rud_familias") or m.get("n_noticias") or m.get("dyfi_respuestas")
                or m.get("en_aoi_copernicus") or m.get("unosat_edificios") is not None
                or ctx["conteo_satelite"].get(nombre) or ctx["conteo_ciudadanos"].get(nombre))


def run(destino: Path) -> dict:
    """Genera todas las fichas elegibles en `destino/municipio/<slug>/index.html`."""
    ctx = contexto()
    escritas, omitidas = [], []
    for m in ctx["municipios"]:
        nombre = m["municipio"]
        if not es_elegible(nombre, ctx):
            omitidas.append(nombre)
            continue
        d = datos_ficha(nombre, ctx)
        carpeta = destino / "municipio" / d["slug"]
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "index.html").write_text(render_ficha(d), encoding="utf-8")
        escritas.append(d["slug"])
    return {"fichas": len(escritas), "omitidas": len(omitidas),
            "sin_senal": omitidas, "slugs": sorted(escritas)}


# ---------------------------------------------- tabla de municipios (fase B)
# Espejo de ESTADO_MUNICIPIO en site/ui.js. Vive en dos superficies porque el
# mapa (app.js) lo sigue necesitando en el navegador: si tocas una, mira la otra.
# `tests/test_render_html.py::TestEstadosEspejo` compara ambas y falla si divergen.
ESTADO_MUNICIPIO = {
    "en_aoi": ("En zona Copernicus", "--s1",
               "El municipio cae dentro de una zona con producto de daño de Copernicus"),
    "evaluado_unosat": ("Evaluado por UNOSAT", "--s9",
                        "El centro satelital de la ONU evaluó allí edificio a "
                        "edificio, fuera de toda zona de Copernicus. Es "
                        "fotointerpretación sobre imagen de muy alta resolución, "
                        "no validada en campo por la propia fuente"),
    "intensidad_alta": ("Intensidad alta", "--warning",
                        "Intensidad percibida DYFI ≥ 6, sin producto de daño"),
    "mencion_prensa": ("Mencionado en prensa", "--s2",
                       "Titulares que lo nombran, sin producto de daño ni DYFI alto"),
    "solo_rud": ("Solo registro municipal (RUD)", "--s8",
                 "El registro de damnificados que carga el municipio es su única "
                 "documentación del daño: ningún producto satelital ni titular lo "
                 "ha verificado de forma independiente"),
    "fuera_aoi": ("Intensidad sentida", "--muted",
                  "Se sintió (DYFI < 6) y ningún producto satelital ni titular lo "
                  "documenta; tampoco tiene registro en el RUD"),
}
SIN_CLASIFICAR = ("Sin clasificar", "--muted", "")


def _celda_prensa(m: dict) -> str:
    """R10: un municipio homónimo de un departamento no recibe atribución por
    texto. Su celda es ausencia de dato, no un cero."""
    if m.get("homonimo_de_departamento"):
        return ('<span title="Se llama igual que un departamento: el monitor no le '
                'atribuye titulares, porque no puede distinguir el municipio del '
                'departamento. No es que no haya prensa — es que no se puede afirmar '
                'cuál le corresponde.">—</span>')
    if m.get("n_noticias"):
        return (f'<a href="noticias.html?municipio={urllib.parse.quote(m["municipio"])}"'
                f' style="color:var(--s1)">{fmt(m["n_noticias"])}</a>')
    if m.get("requiere_depto"):
        return (f'<span title="Su nombre es palabra común, lugar extranjero o se repite '
                f'en otro departamento: solo se le atribuyen titulares que nombren también '
                f'{e(m["departamento"])}. Puede haber prensa que el monitor no pueda '
                f'asignarle.">0</span>')
    return fmt(0)


def _celda_satelite(m: dict, n_copernicus: int) -> str:
    """Lo que han visto los satélites, con la fuente pegada a cada cifra.

    **No se suman**: Copernicus cuenta edificios a los que ha clasificado un
    grado de daño; UNOSAT, los que ha observado uno a uno sobre imagen de muy
    alta resolución. Son mediciones distintas de cosas distintas, y sumarlas
    daría un número que no significa nada.

    Donde ninguno ha mirado no hay cero, hay ausencia (R3)."""
    partes = []
    if n_copernicus:
        partes.append(
            f'<span title="Edificios con daño clasificado uno a uno por fotointerpretación '
            f'del servicio de emergencias de Copernicus (activación EMSR916), cuya coordenada '
            f'cae en este municipio.">{fmt(n_copernicus)} '
            f'<span style="color:var(--muted)">Copernicus</span></span>')
    if m.get("unosat_edificios") is not None:
        otros = ""
        if m.get("unosat_otros_eventos"):
            otros = (f' <span title="UNOSAT los incluye en la misma capa pero los etiqueta '
                     f'con otro código de evento, así que no son de este terremoto." '
                     f'style="color:var(--warning)">+{fmt(m["unosat_otros_eventos"])}</span>')
        partes.append(
            f'<span title="Edificios evaluados por UNITAR-UNOSAT, el centro satelital de la '
            f'ONU, sobre imagen de muy alta resolución. Entre paréntesis, los que la propia '
            f'fuente da por observados; el resto son hipótesis suyas. No está validado en '
            f'campo.">{fmt(m["unosat_edificios"])} '
            f'<span style="color:var(--muted)">({fmt(m["unosat_observados"])}) UNOSAT</span>'
            f'</span>{otros}')
    if not partes:
        return ('<span title="Ningún producto satelital de daño ha mirado este municipio. '
                'Un guion no es un cero: es ausencia de evaluación.">—</span>')
    return "<br>".join(partes)



def filas_municipios(ctx: dict) -> str:
    """Las 95 filas, ya escritas en el HTML.

    La primera celda enlaza a la ficha del municipio: sin este enlace las fichas
    quedan huérfanas y solo se descubren por el sitemap, que es un canal mucho
    más débil que un enlace real desde una página del sitio."""
    filas = []
    for m in sorted(ctx["municipios"], key=lambda x: x.get("poblacion_2026") or 0,
                    reverse=True):
        etiqueta, color, explica = ESTADO_MUNICIPIO.get(m.get("estado"), SIN_CLASIFICAR)
        enlace = f"/municipio/{slug(m['municipio'])}/" if es_elegible(m["municipio"], ctx) else None
        nombre = f"<strong>{e(m['municipio'])}</strong>"
        celda = (f'<a href="{enlace}" style="color:inherit">{nombre}</a>' if enlace
                 else nombre)
        buscar = norm_busqueda(f'{m["municipio"]} {m["departamento"]}')
        n_cop = ctx["conteo_satelite"].get(m["municipio"], 0)
        n_ciu = ctx["conteo_ciudadanos"].get(m["municipio"], 0)
        etiquetas = []
        if not n_cop and m.get("unosat_edificios") is None:
            etiquetas.append("sin-satelite")
        if m.get("rud_personas"):
            etiquetas.append("con-rud")
        else:
            etiquetas.append("sin-rud")
        if n_ciu:
            etiquetas.append("con-ciudadanos")
        # clave de orden de la columna satelital: el total evaluado desde el
        # aire, venga de donde venga. Sirve para ordenar «cuánto se ha mirado»;
        # las cifras NO se suman en la celda, porque miden cosas distintas.
        v_sat = n_cop + (m.get("unosat_edificios") or 0)
        valores = [m["municipio"], etiqueta, m.get("poblacion_2026"), v_sat or None,
                   m.get("rud_personas"), m.get("tasa_rud_pct"), m.get("dyfi_max_cdi"),
                   m.get("dyfi_respuestas"),
                   None if m.get("homonimo_de_departamento") else m.get("n_noticias"),
                   ", ".join(m.get("fuentes") or [])]
        datos = " ".join(f'data-v{i}="{e("" if v is None else v)}"'
                         for i, v in enumerate(valores))
        filas.append(
            f'<tr data-buscar="{e(buscar)}" data-depto="{e(m["departamento"])}"'
            f' data-chips="{e(" ".join(etiquetas))}" {datos}>'
            f'<td>{celda}<br><span style="color:var(--muted)">{e(m["departamento"])}</span></td>'
            f'<td><span class="badge" style="--bc:var({color})" title="{e(explica)}">'
            f"{e(etiqueta)}</span></td>"
            f'<td class="num" title="DANE PPED municipal por área, 2026">'
            f'{fmt(m.get("poblacion_2026"))}</td>'
            f'<td class="num">{_celda_satelite(m, ctx["conteo_satelite"].get(m["municipio"], 0))}</td>'
            f'<td class="num">{fmt(m.get("rud_personas"))}</td>'
            f'<td class="num">{pct(m.get("tasa_rud_pct"))}</td>'
            f'<td class="num">{fmt(m.get("dyfi_max_cdi"), 1)}</td>'
            f'<td class="num">{fmt(m.get("dyfi_respuestas"))}</td>'
            f'<td class="num">{_celda_prensa(m)}</td>'
            f'<td>{e(", ".join(m.get("fuentes") or [])) or "—"}</td>'
            "</tr>")
    return "\n".join(filas)


def filas_portada(ctx: dict) -> str:
    """La tabla de la portada: municipios con evidencia sobre el terreno.

    Deja de organizarse por lo que el satélite decidió mirar (las AOI de la
    activación) y pasa a organizarse por dónde hay prueba georreferenciada,
    venga del satélite o de la comunidad. El hallazgo que lo justifica: el
    satélite ha mirado 6 municipios; la comunidad ha documentado 26.

    Cada fila lleva su coordenada para que el clic siga centrando el mapa.
    El detalle por AOI —vías, interrupciones, fecha de entrega— no cabe en una
    tabla municipal y sigue publicado en crosscheck.csv."""
    filas = []
    for m in municipios_con_evidencia_puntual(ctx):
        etiqueta, color, explica = ESTADO_MUNICIPIO.get(m.get("estado"), SIN_CLASIFICAR)
        sat = m["n_satelite"]
        ciu = m["n_ciudadanos"]
        ficha = f"/municipio/{slug(m['municipio'])}/"
        filas.append(
            f'<tr data-lat="{m["lat"]}" data-lon="{m["lon"]}"'
            f' data-buscar="{e(norm_busqueda(m["municipio"] + " " + m["departamento"]))}">'
            f'<td><a href="{ficha}" style="color:inherit"><strong>{e(m["municipio"])}</strong></a>'
            f'<br><span style="color:var(--muted)">{e(m["departamento"])}</span></td>'
            f'<td><span class="badge" style="--bc:var({color})" title="{e(explica)}">'
            f'{e(etiqueta)}</span></td>'
            f'<td class="num" title="Proyección DANE 2026">{fmt(m.get("poblacion_2026"))}</td>'
            f'<td class="num">{fmt(sat) if sat else "—"}</td>'
            f'<td class="num">{fmt(ciu) if ciu else "—"}</td>'
            f'<td class="num">{fmt(m.get("rud_personas"))}</td>'
            f'<td class="num">{_celda_prensa(m)}</td>'
            "</tr>")
    return "\n".join(filas)


def filas_rud(ctx: dict) -> str:
    """El registro oficial municipio a municipio, escrito en el HTML.

    Es el dato que nadie más publica: el agregador que compite con el monitor
    dice por escrito que las cifras oficiales «no existen consolidadas».

    Cada fila lleva en `data-*` lo que el navegador necesita para filtrar,
    ordenar y paginar sin reconstruirla: el texto normalizado, el departamento,
    las etiquetas de los filtros rápidos y el valor numérico de cada columna."""
    rud = ctx["rud"]
    filas = []
    for m in sorted(rud["municipios"], key=lambda x: x.get("personas") or 0, reverse=True):
        nombre, depto = m["municipio"], m["departamento"]
        etiquetas = []
        if m.get("nuevo"):
            etiquetas.append("nuevos")
        if (m.get("delta_familias") or 0) > 0:
            etiquetas.append("crecieron")
        if (m.get("viv_destruidas") or 0) > 0:
            etiquetas.append("destruidas")
        # valor por columna, en el mismo orden que el <thead>: permite ordenar
        # sobre el DOM sin volver a leer el JSON
        valores = [nombre, m.get("familias"), m.get("personas"), m.get("poblacion_2026"),
                   m.get("tasa_pct"), m.get("viv_destruidas"), m.get("viv_averiadas"),
                   m.get("delta_familias")]
        datos = " ".join(f'data-v{i}="{e("" if v is None else v)}"'
                         for i, v in enumerate(valores))
        marca = (' <span class="badge" style="--bc:var(--good)">nuevo</span>'
                 if m.get("nuevo") else "")
        delta = m.get("delta_familias")
        delta_txt = "—" if delta is None else ("+" if delta >= 0 else "") + fmt(delta)
        filas.append(
            f'<tr data-buscar="{e(norm_busqueda(nombre + " " + depto))}"'
            f' data-depto="{e(depto)}" data-chips="{e(" ".join(etiquetas))}" {datos}>'
            f'<td><strong>{e(nombre)}</strong>{marca}'
            f'<br><span style="color:var(--muted)">{e(depto)}</span></td>'
            f'<td class="num">{fmt(m.get("familias"))}</td>'
            f'<td class="num">{fmt(m.get("personas"))}</td>'
            f'<td class="num">{fmt(m.get("poblacion_2026"))}</td>'
            f'<td class="num">{pct(m.get("tasa_pct"))}</td>'
            f'<td class="num">{fmt(m.get("viv_destruidas"))}</td>'
            f'<td class="num">{fmt(m.get("viv_averiadas"))}</td>'
            f'<td class="num">{delta_txt}</td></tr>')
    return "\n".join(filas)


# Espejo de `UI.isLiveblog` (site/ui.js). Es la única parte de R8 que se replica
# aquí: la marca tiene que estar en el HTML servido, o un lector sin JavaScript
# vería las cifras de un liveblog sin la advertencia de que lo es. La lógica
# compleja —qué snapshot representa el día— sigue viviendo solo en el frontend.
# `tests/test_render_html.py::TestBalances` compara ambas expresiones.
_LIVEBLOG = re.compile(
    r"en vivo|directo|live[-_\s]?news|última hora|ultima hora|minuto a minuto|liveblog",
    re.I)

NIVELES = {
    "oficial_comunicacion": ("Oficial comunicación", "--good"),
    "oficial_institucional": ("Oficial institucional", "--good"),
    "gobierno_local_por_verificar": ("Gobierno local por verificar", "--warning"),
    "temporal_prensa": ("Prensa temporal", "--s1"),
    "busqueda_web_temporal": ("Web temporal", "--muted"),
}


def es_liveblog(item: dict) -> bool:
    texto = f'{item.get("title") or ""} {item.get("publication_url") or item.get("url") or ""}'
    return bool(item.get("is_liveblog") or _LIVEBLOG.search(texto))


def filas_balances(ctx: dict) -> str:
    """La tabla trazable de balances: qué publicó cada medio, cuándo y citando a quién.

    R9: esto NO es el balance oficial, es lo que la prensa publica citándolo. La
    tabla lo dice en cada fila con el nivel de la fuente y el enlace a la
    publicación. La marca «usada en la serie» la sigue poniendo el navegador:
    depende de comparar cada snapshot con el del día anterior."""
    feed = ctx.get("oficiales") or {}
    filas = []
    for item in sorted(feed.get("items") or [],
                       key=lambda x: x.get("search_date") or "", reverse=True):
        c = item.get("cifras") or {}
        url = item.get("publication_url") or item.get("url") or "#"
        pub = item.get("publisher") or {}
        etiqueta, color = NIVELES.get(item.get("source_level"),
                                      (item.get("source_level") or "Sin nivel", "--muted"))
        marca_lb = ('<span class="badge" style="--bc:var(--warning)">liveblog</span> '
                    if es_liveblog(item) else "")
        viviendas = " / ".join(fmt(v) for v in (c.get("viviendas_averiadas"),
                                                c.get("viviendas_destruidas"))
                               if v is not None) or "—"
        citadas = ", ".join(
            (f'<a href="{e(f["url"])}" target="_blank" rel="noopener nofollow">{e(f.get("id") or "fuente")}</a>'
             if f.get("url") else e(f.get("id") or "fuente"))
            for f in (item.get("reported_data_source") or [])) or "—"
        filas.append(
            f'<tr data-fecha="{e(item.get("search_date") or "")}"'
            f' data-url="{e(url)}">'
            f'<td>{e(item.get("search_date") or "—")}</td>'
            f'<td><strong>{e(pub.get("name") or pub.get("domain") or "—")}</strong><br>'
            f'{marca_lb}<span class="badge" style="--bc:var({color})">{e(etiqueta)}</span> '
            f'<span class="note">{citadas}</span></td>'
            f'<td class="num">{fmt(c.get("fallecidos"))}</td>'
            f'<td class="num">{fmt(c.get("heridos"))}</td>'
            f'<td class="num">{fmt(c.get("desaparecidos"))}</td>'
            f'<td class="num">{fmt(c.get("familias_afectadas"))}</td>'
            f'<td class="num">{fmt(c.get("personas_afectadas"))}</td>'
            f'<td class="num" title="Averiadas / destruidas">{viviendas}</td>'
            f'<td><a href="{e(url)}" target="_blank" rel="noopener nofollow">publicación</a>'
            f'<br><span class="note">{e((item.get("title") or "")[:90])}</span></td>'
            "</tr>")
    return "\n".join(filas)


# Cuántos titulares se escriben en el HTML. No son todos a propósito: 5.250
# piezas serían megabytes que ningún rastreador digiere, y paginarlas en sesenta
# páginas casi idénticas sería volumen sin sustancia. Los titulares por municipio
# ya están donde importan: en la ficha de cada municipio.
TITULARES_EN_HTML = 200


def via_google_news(n: dict) -> bool:
    """Espejo de `UI.viaGoogleNews`: el enlace lleva al agregador, no al medio."""
    host = urllib.parse.urlparse(n.get("url") or "").hostname or ""
    return host.lower().endswith("news.google.com")


def medio_de(n: dict):
    """Espejo de `UI.medioDe`: la cabecera que firma, no el feed que la trajo.

    Sin medio declarado no se inventa ninguno: en los enlaces de Google News el
    campo `medio` guarda el nombre del feed, que no es el medio (R3)."""
    if n.get("medio_canonico"):
        return n["medio_canonico"]
    if via_google_news(n):
        return None
    return n.get("medio") or n.get("origen") or None


def filas_noticias(ctx: dict) -> str:
    """Los titulares más recientes, escritos en el HTML.

    R9: esto es prensa, no balance oficial. Cada pieza lleva su fecha, el medio
    que la firma y el aviso de si el enlace va al agregador en vez de al medio."""
    noticias = sorted(ctx["noticias"], key=lambda x: x.get("fecha") or "", reverse=True)
    salida = []
    for n in noticias[:TITULARES_EN_HTML]:
        medio = medio_de(n)
        fecha = (n.get("fecha") or "")[:16].replace("T", " ")
        via = ('  <span class="via" title="Google News recopila titulares de otros medios. '
               'El enlace que publica su feed lleva ahí, no a la página del medio.">'
               'vía Google News</span>' if via_google_news(n) else "")
        etiquetas = "".join(
            f'<span class="chip mun">{e(m)}</span>' for m in (n.get("municipios") or []))
        salida.append(
            f'<li><span class="meta-n">{e(fecha)}'
            f'{f" · {e(medio)}" if medio else ""}{" · " + via if via else ""}</span>'
            f'{etiquetas}'
            f'<br><a href="{e(n.get("url") or "#")}" target="_blank" rel="noopener nofollow">'
            f'{e(n.get("titulo") or "")}</a></li>')
    return "\n".join(salida)


def inyectar_tablas(destino: Path, ctx: dict) -> dict:
    """Rellena en `dist/` los <tbody> marcados con data-gen.

    Se hace sobre el artefacto, nunca sobre site/*.html: un HTML que cambiara
    entero cada día destruiría el blame, y el dato ya está versionado."""
    hechas = {}
    generadores = {"municipios": filas_municipios, "portada": filas_portada,
                   "rud": filas_rud, "balances": filas_balances,
                   "noticias": filas_noticias}
    for nombre, generador in generadores.items():
        archivo = "index" if nombre == "portada" else nombre
        pagina = destino / f"{archivo}.html"
        if not pagina.exists():
            continue
        html = pagina.read_text(encoding="utf-8")
        # el contenedor puede ser una tabla o una lista, y llevar otros atributos
        marca = re.compile(
            rf'<(tbody|ul)([^>]*\bdata-gen="{re.escape(nombre)}"[^>]*)></\1>')
        m = marca.search(html)
        if not m:
            continue
        cuerpo = generador(ctx)
        html = (html[:m.start()] + f"<{m.group(1)}{m.group(2)}>\n{cuerpo}\n</{m.group(1)}>"
                + html[m.end():])
        pagina.write_text(html, encoding="utf-8")
        hechas[nombre] = (cuerpo.count("<tr ") + cuerpo.count("<tr>")
                          + cuerpo.count("<li>"))
    return hechas


if __name__ == "__main__":
    import sys
    salida = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    res = run(salida)
    print(f"fichas municipales: {res['fichas']} escritas, {res['omitidas']} sin señal")
    tablas = inyectar_tablas(salida, contexto())
    for nombre, filas in tablas.items():
        print(f"tabla prerenderizada: {nombre} con {filas} filas")
