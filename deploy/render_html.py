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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"

EPICENTRO = (4.8436, -76.2422)          # San José del Palmar (Chocó)
CHATMAP = "https://chatmap.hotosm.org/colombia.html"
BASE = ""                               # el sitio vive en la raíz del dominio
DATOS = "/data/public"                  # exportes públicos, fuera de site/
MIN_CAPTURAS_GRAFICA = 5                # antes de eso, una recta entre dos puntos no es tendencia
RADIO_MUNICIPIO_M = 25000               # más allá, un punto no se atribuye a ninguna cabecera

# Nombres de las zonas que recortó Copernicus, en español: la fuente los publica
# en inglés. Espejo de `UI.AOI_ES` en site/ui.js — si tocas uno, mira el otro;
# `tests/test_render_html.py` compara los dos.
AOI_ES = {
    "Northern Cali": "Cali Norte", "Cali Center": "Cali Centro",
    "Quibdo Centre": "Quibdó Centro", "Western Colombia": "Occidente de Colombia",
    "Pereira": "Pereira", "Istmina": "Istmina", "Buenaventura": "Buenaventura",
}


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


def valor_suelto(x) -> str:
    """Envuelve una cifra pelada de la tabla de municipios en su propio <span>.

    No es decoración: es lo que permite subirla por encima del enlace estirado
    que hace pulsable la fila entera (`site/styles.css`, «la fila entera de
    municipios.html»). Un texto sin elemento no se puede subir por CSS, y la
    capa se lo traga: medido, arrastrar el ratón sobre «26.377» devolvía una
    selección vacía y el `title` de la columna dejaba de aparecer. Cuesta 13
    bytes por celda; la alternativa era publicar una tabla de cifras que no se
    pueden copiar."""
    return f"<span>{x}</span>"


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


# Fechas: UN solo criterio en todo el sitio (Libro de estilo, 9.6 y 9.8).
#   · En prosa la fecha NO se abrevia nunca: `fecha_larga` → «18 de agosto de
#     2026». Es lo que lee quien llega de un buscador, y estas páginas se
#     releerán dentro de años.
#   · En tablas, cuadros y etiquetas de gráfico, donde el espacio manda, se
#     admite la forma corta: `fecha_corta` → «18-ago-2026».
#   · La forma ISO (2026-08-18) es un valor, no un texto: vale como atributo
#     `data-*` o clave de ordenación, nunca como algo que se lee.
# Espejo exacto de `UI.fechaEs` y `UI.fechaLarga` en site/ui.js: si tocas una,
# mira la otra.
_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")
_MESES_LARGOS = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre",
                 "diciembre")
_FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def fecha_corta(iso: str) -> str:
    """«18-ago-2026»: tablas, cuadros y etiquetas de gráfico."""
    m = _FECHA.match(iso or "")
    return f"{int(m[3])}-{_MESES[int(m[2]) - 1]}-{m[1]}" if m else (iso or "—")


def fecha_larga(iso: str) -> str:
    """«18 de agosto de 2026»: todo lo que se lee dentro de una frase."""
    m = _FECHA.match(iso or "")
    return (f"{int(m[3])} de {_MESES_LARGOS[int(m[2]) - 1]} de {m[1]}"
            if m else (iso or "—"))


def dia_mes(iso: str) -> str:
    """«18-ago»: solo para ejes de gráfico, donde no cabe ni la forma corta.

    El año lo declara el propio gráfico, así que repetirlo en cada punto del eje
    roba el sitio que necesitan las etiquetas. Espejo exacto de `UI.diaMes` en
    site/ui.js — si tocas una, mira la otra; `tests/test_render_html.py` las
    ejecuta y compara."""
    m = _FECHA.match(iso or "")
    return f"{int(m[3])}-{_MESES[int(m[2]) - 1]}" if m else (iso or "—")


def _solo_fecha(iso):
    """La parte «AAAA-MM-DD» de un ISO, o None si no la hay.

    `rud.json` fecha la corrida con la fecha pelada y `oficiales.json` con marca
    de tiempo completa (`2026-08-22T04:02:41.917Z`). El sello tiene que poder
    compararlas y escribirlas igual, así que primero las iguala."""
    m = _FECHA.match(iso or "")
    return m[0] if m else None


def sello_fechas(hasta, corrida, que: str) -> str:
    """El sello del encabezado: hasta cuándo llega el dato y cuándo se construyó.

    No son lo mismo, y confundirlas miente: `rud.json` se genera el 22 con una
    serie que termina el 21, y la página anunciaba «Actualizado el 22 de agosto
    de 2026» sobre cifras del 21. Las dos fechas salen del dato, ninguna se
    escribe a mano (R4), y viajan en un `<time datetime>` legible por máquina.

    Cuando las dos caen en el mismo mes, la corrida se dice solo con su día
    —«hasta el 21 de agosto de 2026 · corrida del 22»—: repetir mes y año no
    añade nada. En cuanto cambian, se escribe entera; ahí «corrida del 1» sería
    un acertijo.

    **M10**: donde falta una fecha se calla ESE trozo, nunca se inventa la otra.
    Y si faltan las dos, lo dice con todas las letras: devolver una cadena vacía
    dejaría el contenedor `data-gen` vacío y rompería el build."""
    hasta, corrida = _solo_fecha(hasta), _solo_fecha(corrida)
    if not hasta and not corrida:
        return f"Sin ninguna captura {que} todavía"
    if not hasta:
        return f'Corrida del <time datetime="{corrida}">{fecha_larga(corrida)}</time>'
    dato = (f'Datos {que} hasta el '
            f'<time datetime="{hasta}">{fecha_larga(hasta)}</time>')
    if not corrida:
        return dato
    mismo_mes = hasta[:7] == corrida[:7]
    dicha = str(int(corrida[8:10])) if mismo_mes else fecha_larga(corrida)
    return f'{dato} · corrida del <time datetime="{corrida}">{dicha}</time>'


def e(s) -> str:
    """Escapa TODO lo que venga de fuera: los titulares son texto de terceros."""
    return html.escape(str(s), quote=True)


def aoi_es(nombre) -> str:
    """Espejo de `UI.aoiEs`: la zona con el nombre que se lee, no el de la fuente."""
    return AOI_ES.get(nombre, nombre)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "-".join(x for x in "".join(c if c.isalnum() else " " for c in s).split())


def toponimo(clave: str, depto: str) -> str:
    """El nombre que se lee, a partir de la clave que desambigua.

    Las claves de `MUNICIPIOS` resuelven los homónimos metiendo el departamento
    entre paréntesis —«Riosucio (Caldas)», «Riosucio (Chocó)»— porque un
    diccionario no admite dos veces la misma llave. Ese paréntesis pertenece a
    la clave, no al topónimo: nadie llama a ese pueblo «Riosucio (Caldas)».

    Cuando la ficha ya escribe el departamento por su cuenta, repetirlo produce
    «Riosucio (Caldas) (Caldas)», que es lo que estuvo publicado en cinco
    fichas. Se recorta solo el paréntesis final que coincide EXACTAMENTE con el
    departamento: así un municipio que algún día lleve paréntesis de verdad en
    su nombre no se queda mutilado.

    Es la misma lección que ya aprendió `municipal_google_news_feeds()`, donde
    buscar la clave literal daba un feed en cero para siempre.
    """
    sufijo = f" ({depto})"
    return clave[: -len(sufijo)] if clave.endswith(sufijo) else clave


def concuerda(n, singular: str, plural: str) -> str:
    """Sustantivo concordado con la cifra que lo precede.

    Solo el uno va en singular. El «—» de un dato ausente (R3) conserva el
    plural: una ausencia no es una unidad, y «— familia inscrita» afirmaría un
    recuento que nadie ha publicado.
    """
    return singular if n == 1 else plural


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
    aproximación a exactitud.

    Un municipio sin cabecera no entra en el reparto. `municipios_dinamicos` da
    de alta lo que aparece en el RUD aunque DIVIPOLA no traiga sus coordenadas,
    y esas filas llegan aquí con `lat`/`lon` en nulo: quedarse fuera es lo
    correcto —no se le puede atribuir ningún punto— y es preferible a colocarlo
    en el (0, 0), que le regalaría los puntos de medio mundo.

    Cuando el punto declara su AOI, manda el AOI y no la proximidad. Copernicus
    dice a qué zona pertenece cada edificio, y esa es la respuesta de la fuente;
    la cabecera más próxima es solo nuestra aproximación. La diferencia no era
    teórica: tres puntos del AOI «Northern Cali» caen más cerca de la cabecera
    de Yumbo que de la de Cali, así que el sitio publicaba un municipio con daño
    satelital que Copernicus nunca cartografió, y la portada contaba once
    municipios mirados donde el recuento contaba diez.
    """
    conocidos = {m["municipio"] for m in municipios}
    cabeceras = [(m["municipio"], m["lat"], m["lon"]) for m in municipios
                 if m.get("lat") is not None and m.get("lon") is not None]
    conteo: dict[str, int] = {}
    huerfanos = 0
    for f in features:
        geom = f.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        declarado = (f.get("properties") or {}).get("municipio")
        if declarado and declarado in conocidos:
            conteo[declarado] = conteo.get(declarado, 0) + 1
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
    fuera de toda zona analizada.

    Y cuando ni siquiera hay cabecera que situar —los municipios que entran por
    el RUD sin coordenadas en DIVIPOLA— devuelve cadena vacía: la ficha lo dice
    con palabras en vez de dibujar un mapa centrado en el (0, 0)."""
    if muni.get("lat") is None or muni.get("lon") is None:
        return ""
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

    # El rótulo del mapa nombra al municipio, no a la llave con que se guarda.
    nombre = toponimo(muni["municipio"], muni["departamento"])
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
# **Fuente única de la barra y del pie de las 213 páginas del sitio.** Hasta el
# 23-ago-2026 vivían dos veces: aquí, para las 208 fichas, y en `site/common.js`,
# que las inyectaba en el navegador en las cinco páginas grandes. Dos copias que
# había que sincronizar a mano y que ya habían divergido en tres sitios —los
# emoticonos de los enlaces, dos enlaces del pie y el rótulo de la marca—.
# Ahora las cinco páginas también se escriben en el build: se leen con el
# JavaScript apagado y hay un solo texto que mantener.
#
# Los enlaces van SIN emoticono (decisión de JP, 23-ago-2026): los llevaban tanto
# la barra del navegador como estas fichas, y el prototipo aprobado no. El 📍 del
# botón «Reportar daño» se queda, porque ahí el icono señala una acción.
PAGINAS = [("index.html", "Mapa"), ("municipios.html", "Municipios"),
           ("rud.html", "RUD"), ("balances.html", "Balances"),
           ("noticias.html", "Titulares")]
REPO = "https://github.com/18orkidea/monitor-terremoto-colombia"
# Las dos URLs que antes solo existían en `site/ui.js`. Se traen aquí porque el
# pie ya no lo escribe el navegador: sin ellas, las cinco páginas perderían dos
# enlaces que hoy publican. En `ui.js` ya no están —eran una copia sin lector, y
# se borró el 23-ago-2026—: el pie manda desde el build. La URL del worker sigue
# repartida por el repo; el inventario, en docs/LIMITACIONES.md.
OFICIALES_BASE = ("https://monitor-terremoto-colombia-oficiales-ai"
                  ".inforesidencias.workers.dev")
TELEGRAM_CANAL = "https://t.me/terremotoCO2026"

# ------------------------------------------------------- identidad publicadora
# Quién publica esto, idéntico en las 213 páginas. La constante única no es
# manía de estilo: **`@id` NO resuelve entre documentos**. Dentro de una misma
# página un parser fusiona los bloques y resuelve las referencias; entre páginas
# distintas, no —cada URL se procesa aislada—, así que un `{"@id": "…#organization"}`
# en la ficha de Cali no va a buscar su definición a la portada. Lo que hace que
# las 213 hablen de la misma entidad no es la sintaxis: es que el valor sea el
# mismo en las 213. De ahí una constante y un solo camino para escribirla (M2),
# con `TestMarcadoEstructurado` comprobando que llega igual a las 213.
#
# `WebSite` y `DataCatalog` en un solo nodo —JSON-LD admite `@type` como lista—
# para no inventar una tercera entidad: esto es a la vez el sitio y el catálogo
# que contiene los 208 datasets municipales.
ORGANIZACION = "https://datosdelterremoto.org/#organization"
SITIO = "https://datosdelterremoto.org/#site"
IDENTIDAD = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "Organization", "@id": ORGANIZACION,
         "name": "Datos del terremoto de Colombia 2026",
         "url": "https://datosdelterremoto.org/",
         "logo": "https://datosdelterremoto.org/icons/icono-512.png",
         "sameAs": [REPO]},
        {"@type": ["WebSite", "DataCatalog"], "@id": SITIO,
         "name": "Datos del terremoto de Colombia 2026",
         "url": "https://datosdelterremoto.org/",
         "inLanguage": "es",
         "publisher": {"@id": ORGANIZACION}},
    ]}
# Serializado una sola vez: así «idéntico en las 213» es un hecho del código y
# no una intención. El `id` sobrevive a la escritura a propósito — es lo que
# permite a `escribir_piezas_compartidas()` distinguir el marcador perdido del
# marcador ya gastado.
BLOQUE_IDENTIDAD = ('<script type="application/ld+json" id="site-identity">'
                    + json.dumps(IDENTIDAD, ensure_ascii=False) + '</script>')


# Cómo se llama el sitio a sí mismo en su barra: el nombre público, corto.
#
# Hasta el 23-ago-2026 la barra decía «Monitor de brechas» sobre una segunda
# línea con «Terremoto de Colombia M7.4 · 10-ago-2026». Las dos cosas cambian a
# la vez y por el mismo motivo: el nombre interno describe lo que el monitor
# HACE y nadie lo busca; el dato del sismo no es navegación, es contexto de la
# página, y pagaba su sitio en la barra pegada de las 213 —13,75 px en cada
# scroll de un móvil de 375 px, el 15,9 % de la altura de la propia barra—.
# «Monitor de brechas» sigue siendo el nombre interno en la documentación y en
# las migas de las fichas; lo que cambia es cómo se presenta el sitio.
MARCA = "Datos del terremoto"

# El contexto del sismo, que salió de la barra y ahora encabeza cada página
# junto al sello de fecha. Es un hecho fijo —no caduca con la corrida—, así que
# se escribe en el HTML de cada página y NO se genera: `data-gen` es el
# mecanismo de lo que cambia cada día. Vive aquí porque una frase escrita cinco
# veces necesita una fuente única aunque no la inyecte nadie: la ata a las
# cinco páginas `tests/test_render_html.py::TestContextoDelSismo` (M2).
CONTEXTO_SISMO = "M7.4 · 10 de agosto de 2026 · San José del Palmar (Chocó)"


def nav_estatico(activa: str = "municipios.html", botones_js: bool = False) -> str:
    """La barra del sitio.

    `botones_js` emite los dos controles que solo sirven de algo con JavaScript:
    🔔 alertas (se muestra sola si hay clave VAPID) y ↗ compartir. Por defecto NO
    salen: las 208 fichas nunca los han tenido y `common.js` los busca por
    `getElementById` y **se calla si no están**, así que una ficha con el botón
    puesto y sin quien lo escuche ofrecería un clic muerto. Las cinco páginas
    grandes sí los piden.
    """
    def enlace(href: str, txt: str) -> str:
        cls = ' class="activa"' if href == activa else ""
        return f'<a href="{BASE}/{href}"{cls}>{txt}</a>'

    enlaces = "".join(enlace(h, t) for h, t in PAGINAS)
    botones = (
        '<button id="btn-alertas" hidden '
        'title="Recibir las alertas del día como notificación">🔔 Alertas</button>'
        '<button id="btn-compartir" title="Compartir esta página">↗ Compartir</button>'
    ) if botones_js else ""
    return (f'<nav id="site-nav" aria-label="Navegación del sitio">'
            f'<a class="brand" href="{BASE}/"><strong>{MARCA}</strong></a>'
            f'<div class="nav-links">{enlaces}'
            f'<a href="{CHATMAP}" target="_blank" rel="noopener" class="nav-cta">'
            f'📍 Reportar daño</a>'
            f'{botones}'
            f'<a href="{REPO}" target="_blank" rel="noopener" '
            f'title="Código y datos abiertos">GitHub</a>'
            f'<a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener" '
            f'title="Apoya los servidores y la recolección de datos">☕</a>'
            f'</div></nav>')


def pie_estatico() -> str:
    return (
        '<div id="site-footer"><div class="sf-cols">'
        # Abre con el nombre público, no con el interno: es la marca doble ya
        # decidida (docs/DECISIONES.md, 22-ago-2026). «Monitor de brechas»
        # sigue en la barra y en la metodología; aquí manda cómo se busca esto.
        '<div><strong>Datos del terremoto de Colombia 2026</strong><br>'
        'Damnificados, viviendas destruidas y daños <strong>municipio a municipio</strong> '
        'tras el terremoto de magnitud 7,4 del 10 de agosto de 2026, con epicentro en '
        'San José del Palmar (Chocó). Cruza el registro oficial de damnificados (RUD de '
        'la UNGRD), las evaluaciones de daño por satélite (Copernicus EMS, UNITAR-UNOSAT '
        'e ICube-SERTIT), los reportes de la comunidad y los balances de la prensa. '
        '<strong>La distancia entre sus cifras es la brecha de reporte.</strong> '
        'Cada dato dice de dónde sale, de qué día es y con qué huella quedó archivado.</div>'
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
        f'<a href="{DATOS}/divipola_coords.json" target="_blank">Catálogo de municipios '
        f'(DIVIPOLA)</a><br>'
        f'<a href="{OFICIALES_BASE}/oficiales.rss" target="_blank" rel="noopener">'
        f'RSS de balances</a> · '
        f'<a href="{DATOS}/alerts.rss" target="_blank" rel="noopener">RSS de alertas</a><br>'
        f'<a href="{TELEGRAM_CANAL}" target="_blank" rel="noopener">Canal de Telegram</a><br>'
        f'<a href="{REPO}" target="_blank" rel="noopener">Repositorio y copias archivadas'
        f'</a></div>'
        '</div>'
        '<p class="sf-line">🇨🇴 ❤️ Mantenido por '
        '<a href="https://col.social/@jp" target="_blank" rel="me noopener">@jp@col.social</a> '
        'con apoyo de <a href="https://orkidea.eu" target="_blank" rel="noopener">Orkidea</a>. '
        'Las <a href="https://www.buymeacoffee.com/orkidea" target="_blank" rel="noopener">'
        'donaciones ☕</a> mantienen los servidores y la recolección diaria de datos. '
        'Código MIT · datos derivados CC BY 4.0 · los datos crudos conservan la licencia '
        'de cada fuente.</p></div>')


# ------------------------------------------------------- datos de una ficha
def evidencia_municipal(nombre: str, muni: dict, ctx: dict) -> dict:
    """Paquete pequeño que carga el mapa interactivo de una sola ficha.

    La portada necesita todos los GeoJSON nacionales; una ficha no. El build
    recorta las cuatro capas puntuales al municipio y conserva únicamente los
    polígonos Copernicus a los que pertenecen sus puntos. Así, abrir «Situación»
    no descarga nada y pedir «Mapa de evidencias» no arrastra megabytes ajenos.

    Los reportes ciudadanos se atribuyen con el mismo radio de 12 km que la
    prosa de la ficha. Su ruta de medio se vuelve absoluta porque el consumidor
    vive dos niveles por debajo de la portada.
    """
    copernicus = [f for f in ctx["damage"]
                  if (f.get("properties") or {}).get("municipio") == nombre]
    unosat = [f for f in ctx["unosat"]
              if (f.get("properties") or {}).get("municipio") == nombre]
    sertit = [f for f in ctx["sertit"]
              if (f.get("properties") or {}).get("municipio") == nombre]

    ciudadanos = []
    if muni.get("lat") is not None and muni.get("lon") is not None:
        for f in ctx["chatmap"]:
            geom = f.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            lon, lat = geom["coordinates"][:2]
            if distancia_m((muni["lat"], muni["lon"]), (lat, lon)) >= 12000:
                continue
            propiedades = dict(f.get("properties") or {})
            if propiedades.get("media"):
                propiedades["media"] = f"/data/media/{Path(propiedades['media']).name}"
            ciudadanos.append({"type": "Feature", "geometry": geom,
                                "properties": propiedades})

    aois = {(f.get("properties") or {}).get("aoi") for f in copernicus}
    zonas = [f for f in ctx["aois"] if (f.get("properties") or {}).get("aoi") in aois]
    capas = {"copernicus": copernicus, "unosat": unosat, "sertit": sertit,
             "ciudadanos": ciudadanos, "zonas": zonas}
    conteos = {clave: len(capas[clave]) for clave in
               ("copernicus", "unosat", "sertit", "ciudadanos")}
    return {
        "municipio": {"nombre": nombre, "departamento": muni["departamento"],
                      "lat": muni.get("lat"), "lon": muni.get("lon")},
        "generado": ctx["rud"].get("generado", ""),
        "conteos": {**conteos,
                    "satelite": conteos["copernicus"] + conteos["unosat"]
                    + conteos["sertit"],
                    "total": sum(conteos.values())},
        "capas": {clave: {"type": "FeatureCollection", "features": features}
                  for clave, features in capas.items()},
    }


def datos_ficha(nombre: str, ctx: dict) -> dict:
    muni = ctx["idx"][nombre]
    clave = nombre.upper()

    serie = []
    for fecha in sorted(ctx["rud"]["detalle_diario"]):
        fila = next((x for x in ctx["rud"]["detalle_diario"][fecha]
                     if x["municipio"].upper() == clave), None)
        if fila:
            serie.append((fecha, fila))

    # Sin cabecera no hay distancias que calcular: ni zonas próximas ni reportes
    # «del entorno». La ficha sale igual y lo cuenta; reventar aquí dejaría sin
    # publicar las 95 restantes.
    tiene_coords = muni.get("lat") is not None and muni.get("lon") is not None

    zonas = []
    for f in (ctx["aois"] if tiene_coords else []):
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
    for f in (ctx["chatmap"] if tiene_coords else []):
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

    evidencia = evidencia_municipal(nombre, muni, ctx)
    return {
        "muni": muni, "serie": serie, "zonas": zonas, "ciudadanos": ciudadanos,
        "con_medio": sum(1 for *_, p in ciudadanos if p.get("media")),
        "mmis": [p["mmi"] for *_, p in ciudadanos if p.get("mmi") is not None],
        "titulares": titulares, "ultimo": ultimo, "primero": primero,
        "delta": delta, "pct_delta": pct_delta,
        "satelite": ctx["conteo_satelite"].get(nombre, 0),
        "cruce": ctx["cruce_satelital"].get(nombre) or {},
        "tiene_coords": tiene_coords,
        "generado": ctx["rud"].get("generado", ""),
        "slug": slug(nombre), "evidencia": evidencia,
        "hay_evidencia": bool(evidencia["conteos"]["total"]),
    }


# Productos satelitales de daño que cubren el evento. Añadir uno es añadir una
# entrada aquí: `tests/test_render_html.py::TestSatelites` falla si aparece en
# los datos un campo `*_edificios` que esta tabla no contemple, para que ninguna
# ficha vuelva a afirmar «ningún producto satelital» cuando sí lo hay.
# `prosa` es cómo se nombra cada servicio dentro de una frase, con su oficio:
# quien lee «ICube-SERTIT» por primera vez necesita saber qué es antes que sus
# siglas. `url` es dónde lo publica su dueño, para la tabla de trazabilidad.
SATELITES = (
    {"clave": "copernicus", "nombre": "Copernicus EMS (EMSR916)",
     "campo": None,           # se cuenta por puntos dentro del municipio
     "prosa": "el servicio de emergencias de Copernicus",
     "url": "https://rapidmapping.emergency.copernicus.eu/EMSR916/",
     "naturaleza": "evaluación satelital de daño, sin validar en campo"},
    {"clave": "unosat", "nombre": "UNITAR-UNOSAT",
     "campo": "unosat_edificios",
     "prosa": "UNITAR-UNOSAT, el centro satelital de la ONU",
     "url": "https://unosat.org/products/4253",
     "naturaleza": "evaluación satelital de daño, sin validar en campo"},
    {"clave": "sertit", "nombre": "ICube-SERTIT (Charter 1048)",
     "campo": "sertit_edificios",
     "prosa": "ICube-SERTIT, el servicio de cartografía rápida de la Universidad "
              "de Estrasburgo activado por la Carta Internacional del Espacio",
     "url": "https://sertit.unistra.fr/cartographie-rapide/cartoaction/845/",
     # su licencia obliga a citar y prohíbe el uso comercial: la condición viaja
     # pegada al dato hasta la ficha, no escondida en un pie de página
     "naturaleza": "evaluación satelital de daño, sin validar en campo · "
                   "© ICube-SERTIT 2026, uso no comercial"},
)


def satelites_con_dato(m: dict, n_copernicus: int) -> list:
    """Qué productos satelitales han reportado daño en este municipio.

    Se recorre SATELITES, no una lista de fuentes escrita a mano: el día que
    entre el cuarto servicio, esta función lo cuenta sola."""
    vistos = []
    for sat in SATELITES:
        if sat["campo"] is None:                        # Copernicus, por puntos
            if n_copernicus:
                vistos.append((sat["nombre"], n_copernicus))
        elif m.get(sat["campo"]) is not None:
            vistos.append((sat["nombre"], m[sat["campo"]]))
    return vistos


def filas_fuentes_satelitales(m: dict, n_copernicus: int) -> str:
    """Las filas satelitales de la tabla «Fuentes y trazabilidad» de una ficha.

    Nombran a quien miró ESTE municipio. Encabezar la trazabilidad de Roldanillo
    con la activación EMSR916 sería atribuir a Copernicus un dato que publicó
    otro servicio (R9). Cuando no ha mirado ninguno, la fila los nombra a los
    tres y dice justamente eso."""
    vistos = {nombre for nombre, _ in satelites_con_dato(m, n_copernicus)}
    activos = [sat for sat in SATELITES if sat["nombre"] in vistos]
    if not activos:
        enlaces = ", ".join(f'<a href="{sat["url"]}" target="_blank" rel="noopener">'
                            f'{e(sat["nombre"])}</a>' for sat in SATELITES)
        return (f'<tr><td>Daño en edificios</td><td>{enlaces}</td>'
                f'<td>ninguno ha evaluado este municipio</td></tr>')
    return "".join(
        f'<tr><td>Daño en edificios</td>'
        f'<td><a href="{sat["url"]}" target="_blank" rel="noopener">{e(sat["nombre"])}</a></td>'
        f'<td>{e(sat["naturaleza"])}</td></tr>' for sat in activos)


def evaluados_unicos(m: dict, ctx: dict) -> int:
    """Edificios evaluados desde el aire en un municipio, contado cada uno una vez.

    Cuando dos servicios miran el mismo sitio, la cifra del municipio no es la
    suma de las suyas: en Pereira, 108 de los edificios que ve Copernicus son los mismos
    que ve SERTIT. Quién es el mismo edificio lo decide `ingest/satelites.py`
    —dos puntos de servicios distintos a menos de 20 m— y llega ya resuelto en
    monitor.json. Donde no hay cruce publicado porque solo ha mirado un
    servicio, vale la mayor de las cifras, que es justamente la de ese servicio.

    Sirve para ordenar «cuánto se ha mirado» en las tablas. Sumar no es una
    opción en ninguno de los dos casos."""
    nombre = m["municipio"]
    cruce = ctx["cruce_satelital"].get(nombre) or {}
    if cruce.get("unidades"):
        return cruce["unidades"]
    return max(ctx["conteo_satelite"].get(nombre, 0),
               m.get("unosat_edificios") or 0,
               m.get("sertit_edificios") or 0)


def parrafo_respuesta(d: dict) -> str:
    """El párrafo que citan los buscadores y los sistemas de IA: una idea por
    frase, cada una con su cifra, su fecha y su fuente."""
    m = d["muni"]
    # El topónimo, no la clave: este párrafo es el que citan los buscadores y
    # los sistemas de IA, y estuvo publicando «Riosucio (Caldas) (Caldas) tiene
    # 832 familias».
    depto = m["departamento"]
    nombre = toponimo(m["municipio"], depto)
    partes = []
    if m.get("rud_familias"):
        partes.append(
            f"{e(nombre)} ({e(depto)}) tiene <strong>{fmt(m['rud_familias'])} familias "
            f"({fmt(m['rud_personas'])} personas)</strong> inscritas como damnificadas en el "
            f"Registro Único de Damnificados (RUD) de la Unidad Nacional para la Gestión del "
            f"Riesgo de Desastres (UNGRD), el <strong>{fmt(m['tasa_rud_pct'], 2)}%</strong> de sus "
            f"{fmt(m['poblacion_2026'])} habitantes proyectados para 2026 por el Departamento "
            f"Administrativo Nacional de Estadística (DANE). "
            f"El registro municipal declara {fmt(m['rud_viv_destruidas'])} "
            f"{concuerda(m['rud_viv_destruidas'], 'vivienda destruida', 'viviendas destruidas')} "
            f"y {fmt(m['rud_viv_averiadas'])} "
            f"{concuerda(m['rud_viv_averiadas'], 'averiada', 'averiadas')}. <strong>El RUD es un registro progresivo "
            f"que cargan las autoridades municipales y está sujeto a verificación posterior</strong>: mide inscripciones tramitadas, no daño comprobado.")
    else:
        partes.append(
            f"{e(nombre)} ({e(depto)}) <strong>no tiene inscripciones en el Registro Único de "
            f"Damnificados (RUD) de la Unidad Nacional para la Gestión del Riesgo de Desastres "
            f"(UNGRD)</strong> en la última captura del monitor. Sin registro no significa sin "
            f"daño: significa que las autoridades municipales aún no lo han cargado. Su población "
            f"proyectada para 2026 por el Departamento Administrativo Nacional de Estadística "
            f"(DANE) es de {fmt(m['poblacion_2026'])} habitantes.")
    # La afirmación se construye desde SATELITES, no desde una fuente concreta:
    # el día que entre otro producto, la frase sigue siendo cierta sola.
    vistos = satelites_con_dato(m, d["satelite"])
    if vistos:
        detalle = "; ".join(f"{fmt(n)} edificios clasificados por {fuente}"
                            for fuente, n in vistos)
        partes.append(f"El daño está documentado por satélite: <strong>{detalle}</strong>.")
        # La inconsistencia de etiquetado de UNOSAT vivía solo en la tabla y en
        # el globo del mapa. En Zarzal la traen los 201 puntos —todos—, así que
        # una ficha que no la nombrase estaría publicando la cifra sin lo único
        # que hay que saber para juzgarla.
        raros = m.get("unosat_codigo_inconsistente")
        if raros:
            cuantos = (f"Los {fmt(raros)} edificios que evaluó UNOSAT llegan"
                       if raros == m.get("unosat_edificios")
                       else f"De esos edificios, <strong>{fmt(raros)}</strong> llegan")
            partes.append(
                f"{cuantos} con un <strong>código de evento que no coincide con el que "
                f"declara su propio producto</strong>, y fechado después de la imagen que "
                f"los retrata: la fuente se contradice a sí misma. Cuentan —a qué terremoto "
                f"pertenece un punto lo dice el identificador del producto que lo publica—, "
                f"y la discrepancia se publica aquí en vez de resolverse por nuestra cuenta.")
        # El hallazgo de tener tres miradas no es el total: es lo que pasa donde
        # dos se superponen. Vivía solo en el título de una celda, que ni se
        # indexa ni se lee en el móvil.
        cruce = d.get("cruce") or {}
        if len(cruce.get("fuentes") or {}) > 1:
            if cruce.get("coincidencias"):
                discrepan = cruce.get("discrepan_de_grado") or 0
                desacuerdo = (f", y en {fmt(discrepan)} de ellos <strong>no coinciden en la "
                              f"gravedad</strong> que le asignan al mismo tejado"
                              if discrepan else "")
                partes.append(
                    f"No son dos versiones de la misma medición: "
                    f"<strong>{fmt(cruce['coincidencias'])} de esos edificios los vieron dos "
                    f"servicios</strong>{desacuerdo}; el resto lo vio uno solo. Contando cada "
                    f"edificio una sola vez, {e(nombre)} tiene "
                    f"<strong>{fmt(cruce.get('unidades'))} edificios evaluados desde el "
                    f"aire</strong>.")
            else:
                partes.append(
                    f"Los servicios cartografiaron zonas distintas del mismo municipio y no "
                    f"comparten ni un edificio, así que sus cifras no se suman ni se comparan "
                    f"entre sí: son dos ventanas sobre trozos distintos de {e(nombre)}.")
    else:
        cerca = (f" La zona analizada más próxima es {e(d['zonas'][0][0])}, a "
                 f"{fmt(d['zonas'][0][2] / 1000, 0)} kilómetros." if d["zonas"] else "")
        # Se nombran TODOS los servicios vigilados, y salen de SATELITES: la
        # frase «ni Copernicus ni UNOSAT» caducó en cuanto entró el tercero, y
        # una negativa que se olvida de una fuente es una negativa falsa.
        ninguno = ", ni ".join(sat["prosa"] for sat in SATELITES)
        partes.append(
            f"<strong>Ningún producto satelital de daño ha reportado daños en {e(nombre)}"
            f"</strong>: no han evaluado sus edificios ni {ninguno}.{cerca}")
    if d["ciudadanos"]:
        partes.append(
            f"La comunidad sí lo ha documentado: <strong>{fmt_prosa(len(d['ciudadanos']))} reportes "
            f"ciudadanos</strong> georreferenciados en el entorno, {fmt_prosa(d['con_medio'])} con foto o vídeo.")
    medios = {medio_de_titular(t) for t in d["titulares"]} - {None}
    if d["titulares"]:
        n_piezas, n_medios = len(d["titulares"]), len(medios)
        partes.append(f"La prensa recogida por el monitor suma "
                      f"{fmt_prosa(n_piezas, femenino=True)} "
                      f"pieza{'s' if n_piezas != 1 else ''} sobre {e(nombre)}, de "
                      f"{fmt_prosa(n_medios)} medio{'s' if n_medios != 1 else ''} "
                      f"identificado{'s' if n_medios != 1 else ''}.")
    return " ".join(partes)


# ------------------------------------------------------------- contexto único
def contexto() -> dict:
    """Carga una sola vez todo lo que comparten las fichas y las tablas."""
    municipios_json = _leer("municipios.json")
    municipios = municipios_json["items"]
    noticias_json = _leer("noticias.json")
    noticias = noticias_json
    if isinstance(noticias_json, dict):
        noticias = noticias_json.get("items") or noticias_json.get("noticias") or []
    damage = _leer("damage_points.geojson")["features"]
    unosat = _leer("unosat_damage.geojson")["features"]
    sertit = _leer("sertit_damage.geojson")["features"]
    chatmap = _leer("chatmap.geojson")["features"]
    # Cuántos edificios ÚNICOS tiene cada municipio cuando dos servicios miran
    # el mismo sitio. No se calcula aquí: la regla vive en `ingest/satelites.py`
    # y viaja resuelta en monitor.json, con su umbral y su criterio.
    monitor = _leer("monitor.json")
    satelital = monitor.get("satelital") or {}
    return {
        "monitor": monitor,          # la banda de portada lo lee entero
        "municipios": municipios,
        "idx": {m["municipio"]: m for m in municipios},
        # la corrida de municipios.json, que el sello de esa página necesita y
        # que se perdía al quedarnos solo con `items`
        "municipios_generado": municipios_json.get("generado"),
        "rud": _leer("rud.json"),
        "aois": _leer("aois.geojson")["features"],
        "damage": damage,
        "unosat": unosat,
        "sertit": sertit,
        "chatmap": chatmap,
        "noticias": noticias,
        # la corrida y el arranque del corpus de titulares, que el sello, la
        # entradilla y el dateModified de esa página necesitan y que se perdían
        # al quedarnos solo con `items` (mismo caso que municipios_generado)
        "noticias_generado": (noticias_json.get("generado")
                              if isinstance(noticias_json, dict) else None),
        "noticias_desde": (noticias_json.get("desde")
                           if isinstance(noticias_json, dict) else None),
        "zonas_con_producto": {f["properties"].get("aoi") for f in damage},
        "conteo_satelite": asigna_a_municipios(damage, municipios),
        "cruce_satelital": satelital.get("por_municipio") or {},
        "conteo_ciudadanos": asigna_a_municipios(chatmap, municipios),
        "oficiales": _leer("oficiales.json") if (PUBLIC / "oficiales.json").exists() else {},
    }


def municipios_con_evidencia_puntual(ctx: dict) -> list:
    """Municipios con prueba georreferenciada dentro: satélite o comunidad.

    Es el criterio de la tabla de portada. Deja de organizarse por lo que el
    satélite decidió mirar y pasa a organizarse por dónde hay evidencia sobre
    el terreno, venga de donde venga.

    «Satélite» son los tres: Copernicus, UNITAR-UNOSAT e ICube-SERTIT. Mientras
    solo contó el primero, Viterbo y Anserma —evaluados edificio a edificio por
    el centro satelital de la ONU— no salían en esta tabla, y Manizales salía
    con un guion en la columna satelital pese a tener 127 edificios
    clasificados. La portada llegó a anunciar un total de las dos miradas que su
    propia tabla desmentía. Con el tercero se repetiría el episodio en Roldanillo
    y La Virginia, los dos municipios que solo ha mirado SERTIT.

    El orden lo marcan los edificios únicos, no la suma de las tres cifras."""
    sat, ciu = ctx["conteo_satelite"], ctx["conteo_ciudadanos"]
    # Aquí el cero SÍ se colapsa, y es deliberado: esta tabla promete
    # «municipios con prueba sobre el terreno», así que un municipio evaluado
    # con cero edificios con grado no tiene sitio en ella —saldría como una
    # fila con guiones en todas las columnas, que es la lección de los globos
    # sin datos en formato tabla, y rompería el invariante de
    # `test_render_html.py::…n_evaluados or n_ciudadanos`.
    # Es la diferencia con `ingest/municipios.py::sin_mirada_satelital`, donde
    # el mismo cero sí se distingue porque allí la pregunta es otra: si alguien
    # miró, no si encontró. Si algún día un servicio publica un municipio a
    # cero, hay que decidir qué enseña esa fila antes de dejarla entrar.
    uno = {m["municipio"]: m["unosat_edificios"] for m in ctx["municipios"]
           if m.get("unosat_edificios")}
    ser = {m["municipio"]: m["sertit_edificios"] for m in ctx["municipios"]
           if m.get("sertit_edificios")}
    nombres = {k for k in (set(sat) | set(ciu) | set(uno) | set(ser))
               if not k.startswith("__")}
    filas = []
    for n in nombres:
        m = ctx["idx"][n]
        filas.append({**m, "n_satelite": sat.get(n, 0), "n_ciudadanos": ciu.get(n, 0),
                      "n_unosat": uno.get(n, 0), "n_sertit": ser.get(n, 0),
                      "n_evaluados": evaluados_unicos(m, ctx)})
    filas.sort(key=lambda f: (f["n_evaluados"] + f["n_ciudadanos"]), reverse=True)
    return filas


# ------------------------------------------------------------------ la ficha
def render_ficha(d: dict) -> str:
    """HTML completo de una ficha municipal.

    Usa los componentes compartidos de styles.css (.destacado, .aviso,
    .metric-strip, .mapa-estatico…): una misma idea se ve igual en cualquier
    página del sitio."""
    m = d["muni"]
    # `clave` es la llave del diccionario y solo sirve para buscar —el mapa de
    # la portada indexa por ella—; `nombre` es lo que lee una persona. Confundir
    # las dos publicaba «Riosucio (Caldas) (Caldas)» en cinco fichas.
    clave, depto = m["municipio"], m["departamento"]
    nombre = toponimo(clave, depto)
    url = f"https://datosdelterremoto.org/municipio/{d['slug']}/"
    titulo = f"Terremoto en {nombre} ({depto}) 2026: damnificados y daños"
    descr = (f"{nombre} ({depto}): {fmt(m['rud_familias'])} "
             f"{concuerda(m['rud_familias'], 'familia inscrita', 'familias inscritas')} "
             f"en el RUD, {fmt(m['rud_viv_averiadas'])} "
             f"{concuerda(m['rud_viv_averiadas'], 'vivienda averiada', 'viviendas averiadas')} y "
             f"{'sin' if not satelites_con_dato(m, d['satelite']) else 'con'} "
             f"evaluación satelital de daño. "
             f"Cada cifra con su fuente y su fecha.")
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "@id": f"{url}#dataset", "url": url,
        "name": f"Damnificados y cobertura del terremoto de 2026 en {nombre} ({depto})",
        "description": descr, "inLanguage": "es", "temporalCoverage": "2026-08-10/..",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        # R9 en el marcado: quien compiló ESTE documento —el cruce de RUD,
        # satélites y DANE para este municipio— es el monitor, no la fuente. Si
        # `creator` apuntara a la UNGRD publicaríamos que la UNGRD firma un
        # documento que mezcla tres satélites y el DANE. La atribución de origen
        # vive en otro campo (`citation`), que llega con la ficha.
        "creator": {"@id": ORGANIZACION},
        "publisher": {"@id": ORGANIZACION},
        "spatialCoverage": {
            "@type": "Place", "name": f"{nombre}, {depto}, Colombia",
            "identifier": {"@type": "PropertyValue", "propertyID": "DIVIPOLA",
                           "value": m["divipola"]},
            # Sin cabecera en DIVIPOLA el campo se omite: en JSON-LD, omitir es
            # lo que significa «no lo sabemos»; un cero significaría el golfo de
            # Guinea (R3).
            **({"geo": {"@type": "GeoCoordinates", "latitude": m["lat"],
                        "longitude": m["lon"]}} if d["tiene_coords"] else {})},
        # Dos referencias por `@id`, nunca un nodo dentro de otro: Google valida
        # recursivamente CUALQUIER nodo `"@type": "Dataset"`, esté donde esté
        # anidado, así que el `isPartOf` que embebía un segundo Dataset se
        # validaba como dataset independiente —sin `description`— en las 208
        # fichas. No se parchea añadiéndole el campo que le falta: se cambia la
        # forma, para que no quede un Dataset dentro de otro que nadie pueda
        # copiar mañana. Quién es `#site` lo dice `BLOQUE_IDENTIDAD`, en esta
        # misma página. G2 lo vigila a cualquier profundidad.
        "isPartOf": {"@id": SITIO},
        "includedInDataCatalog": {"@id": SITIO}}
    migas = [("Monitor de brechas", f"{BASE}/"),
             ("Municipios", f"{BASE}/municipios.html"),
             (nombre, None)]
    ld_migas = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": txt,
             **({"item": f"https://datosdelterremoto.org{href}"} if href else {})}
            for i, (txt, href) in enumerate(migas)]}
    scripts_mapa = (
        f'<script src="{BASE}/ui.js?v=dev" defer></script>\n'
        f'<script src="{BASE}/municipio.js?v=dev" defer></script>'
        if d["hay_evidencia"] else "")

    o = ['<!DOCTYPE html>', '<html lang="es">', '<head>', '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>{e(titulo)}</title>',
         f'<meta name="description" content="{e(descr)}">',
         '<meta name="robots" content="index, follow">',
         f'<link rel="canonical" href="{url}">',
         f'<meta property="og:url" content="{url}">',
         '<meta property="og:type" content="article">',
         '<meta property="og:locale" content="es_CO">',
         # El nombre público, el mismo que `WebSite.name` de la portada: la
         # marca doble ya decidida (docs/DECISIONES.md, 22-ago-2026). No
         # existía en ninguna página; aquí había ausencia, no conflicto.
         '<meta property="og:site_name" content="Datos del terremoto de Colombia 2026">',
         f'<meta property="og:title" content="{e(titulo)}">',
         f'<meta property="og:description" content="{e(descr)}">',
         f'<meta property="og:image" content="https://datosdelterremoto.org{BASE}/og/portada.png">',
         '<meta name="twitter:card" content="summary_large_image">',
         BLOQUE_IDENTIDAD,
         f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>',
         f'<script type="application/ld+json">{json.dumps(ld_migas, ensure_ascii=False)}</script>',
         f'<link rel="stylesheet" href="{BASE}/styles.css?v=dev">',
         f'<link rel="icon" type="image/png" href="{BASE}/icons/favicon.png">',
         scripts_mapa,
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
         # El subtítulo decía en otras palabras lo que ya dice el H1, y lo que
         # prometía —damnificados, daños, cobertura— lo cumple la tira de
         # cifras una línea más abajo. El código DIVIPOLA y la fecha de la
         # corrida no se pierden: bajan a «Fuentes y trazabilidad», que es
         # donde los busca quien los necesita.
         '</div></header>',
         '<main>',
         f'<p class="destacado">{parrafo_respuesta(d)}</p>']

    tarjetas = [("Familias inscritas", fmt(m["rud_familias"]), "RUD · UNGRD · registro"),
                ("Personas", fmt(m["rud_personas"]),
                 f'{fmt(m["tasa_rud_pct"], 2)}% de la población'),
                ("Viviendas averiadas", fmt(m["rud_viv_averiadas"]),
                 f'{fmt(m["rud_viv_destruidas"])} '
                 f'{concuerda(m["rud_viv_destruidas"], "destruida", "destruidas")}'),
                ("Población 2026", fmt(m["poblacion_2026"]), "proyección DANE")]
    o.append('<div class="metric-strip">')
    for etiqueta, valor, sub in tarjetas:
        o.append(f'<div class="metric-card"><span>{etiqueta}</span><strong>{valor}</strong>'
                 f'<small>{sub}</small></div>')
    o.append('</div>')

    # ---- mapa de situación
    o.append('<section class="page-section">')
    o.append(f'<h2>Dónde está {e(nombre)} y qué ha mirado el satélite</h2>')
    # El SVG sigue siendo la respuesta inmediata, indexable y sin JavaScript.
    # Solo las fichas con puntos de evidencia reciben dos pestañas. El segundo
    # panel nace vacío: municipio.js pide Leaflet y el JSON recortado al primer
    # clic, nunca durante la lectura de «Situación».
    # La clave, no el topónimo: `app.js` indexa el mapa de la portada por la
    # llave del diccionario (`munLayerById[pedido]`), así que los dos Riosucios
    # solo se distinguen aquí. Con el topónimo, el enlace no encuentra la capa
    # y el mapa se queda quieto sin decir por qué.
    destino = f"/?municipio={urllib.parse.quote(clave)}#mapa"
    svg = mapa_svg(m, [(z, c) for z, c, _ in d["zonas"]], d["ciudadanos"])
    if svg:
        if d["hay_evidencia"]:
            situacion_id = f"situacion-{d['slug']}"
            evidencia_id = f"evidencias-{d['slug']}"
            o.append('<div class="mapa-tabs" data-mapa-tabs>')
            o.append(f'<div class="mapa-tabs__lista" role="tablist" '
                     f'aria-label="Vistas del mapa de {e(nombre)}">'
                     f'<button type="button" role="tab" id="tab-{situacion_id}" '
                     f'aria-controls="{situacion_id}" aria-selected="true">Situación</button>'
                     f'<button type="button" role="tab" id="tab-{evidencia_id}" '
                     f'aria-controls="{evidencia_id}" aria-selected="false" '
                     f'tabindex="-1">Mapa de evidencias</button></div>')
            o.append(f'<div id="{situacion_id}" role="tabpanel" '
                     f'aria-labelledby="tab-{situacion_id}">')
        else:
            o.append(f'<a href="{destino}" class="mapa-enlace" '
                     f'aria-label="Abrir {e(nombre)} en el mapa interactivo">')
        o.append(svg)
        if not d["hay_evidencia"]:
            o.append('</a>')
        o.append('<p class="leyenda">'
                 f'<span class="badge" style="--bc:var(--s8)">{e(nombre)}</span>'
                 '<span class="badge" style="--bc:var(--good)">zona con producto satelital</span>'
                 '<span class="badge" style="--bc:var(--s7)">reporte ciudadano</span>'
                 '<span class="badge" style="--bc:var(--critical)">epicentro</span></p>')
        if d["hay_evidencia"]:
            conteos = d["evidencia"]["conteos"]
            partes = []
            if conteos["satelite"]:
                partes.append(f'{fmt(conteos["satelite"])} puntos publicados por los '
                              'servicios satelitales')
            if conteos["ciudadanos"]:
                partes.append(f'{fmt(conteos["ciudadanos"])} '
                              f'{concuerda(conteos["ciudadanos"], "reporte ciudadano", "reportes ciudadanos")}')
            resumen = " y ".join(partes)
            o.append('</div>')
            o.append(f'<div id="{evidencia_id}" role="tabpanel" '
                     f'aria-labelledby="tab-{evidencia_id}" hidden>')
            o.append(f'<p class="sub mapa-evidencias__resumen">Este mapa reúne {resumen} '
                     f'en el entorno de {e(nombre)}. Cada fuente permanece en su propia capa.</p>')
            o.append(f'<div class="mapa-evidencias" id="mapa-evidencias-{d["slug"]}" '
                     f'data-evidencia="{DATOS}/municipios/{d["slug"]}/evidencia.json" '
                     f'data-destino="{destino}" aria-label="Mapa interactivo de evidencias '
                     f'en {e(nombre)}" aria-busy="false">'
                     '<div class="mapa-evidencias__placeholder" role="status">'
                     '<span aria-hidden="true"></span><p>El mapa se cargará al abrir esta '
                     'pestaña.</p></div></div>')
            o.append('<p class="note">Las capas de diferentes servicios pueden observar el '
                     'mismo edificio. El mapa las muestra por separado y no las suma como si '
                     'fueran casos distintos.</p></div></div>')
            o.append(f'<noscript><p class="note">Para explorar estos puntos necesitas '
                     f'JavaScript. <a href="{destino}">Abrir {e(nombre)} en el mapa '
                     f'interactivo de la portada</a>.</p></noscript>')
    else:
        # El municipio entró por el registro oficial y el catálogo DIVIPOLA no
        # trae su cabecera. Sin coordenada no hay mapa, ni distancia a las zonas
        # analizadas, ni reportes «del entorno»: la ficha lo dice en vez de
        # dibujar un punto que no sabemos dónde está.
        o.append(f'<p class="note">El monitor <strong>no tiene la coordenada de la cabecera '
                 f'de {e(nombre)}</strong>: entró por el registro de damnificados y el '
                 f'catálogo oficial de la División Político-Administrativa (DIVIPOLA) no la '
                 f'publica. Sin ella no se puede situar en el mapa ni medir su distancia a '
                 f'las zonas que ha analizado el satélite, ni atribuirle reportes ciudadanos '
                 f'del entorno. Las cifras del registro de esta ficha no dependen de eso.</p>')
    vistos_mapa = satelites_con_dato(m, d["satelite"])
    if not vistos_mapa:
        cerca = (f' La más próxima, {e(d["zonas"][0][0])}, está a '
                 f'{fmt(d["zonas"][0][2] / 1000, 0)} kilómetros.' if d["zonas"] else "")
        o.append(f'<p class="note">{e(nombre)} queda fuera de toda zona analizada por el '
                 f'servicio de emergencias de Copernicus.{cerca} Ningún otro satélite ha '
                 f'evaluado sus edificios, así que no hay nada que cruzar: el registro '
                 f'municipal y los reportes de la comunidad son la única evidencia disponible.</p>')
    elif not d["satelite"]:
        # el mapa dibuja las zonas de Copernicus, así que aquí queda fuera; pero
        # otro satélite sí lo miró y la nota no puede decir que no lo miró nadie
        fuentes = ", ".join(f for f, _ in vistos_mapa)
        o.append(f'<p class="note">{e(nombre)} queda fuera de las zonas que analizó el servicio '
                 f'de emergencias de Copernicus, que son las que dibuja este mapa. Sus edificios '
                 f'sí los ha evaluado {e(fuentes)}.</p>')
    o.append('</section>')

    # ---- comunidad
    if d["ciudadanos"]:
        rango = (f' con intensidad percibida de {fmt(min(d["mmis"]), 1)} a '
                 f'{fmt(max(d["mmis"]), 1)} en la escala de Mercalli modificada'
                 if d["mmis"] else "")
        # Por qué esta frase es condicional: «Donde el satélite no ha mirado,
        # cada reporte cuenta» se emitía siempre, así que seis fichas —Pereira,
        # Cali, Quibdó, Manizales, Buenaventura y Roldanillo— afirmaban arriba
        # que el satélite había clasificado sus edificios y lo negaban aquí, en
        # la misma pantalla. Donde el satélite SÍ miró, el argumento no es que
        # no haya mirado: es que fotointerpreta tejados desde el aire y no
        # comprueba nada en el suelo.
        porque = ('Donde el satélite no ha mirado, cada reporte cuenta. '
                  if not satelites_con_dato(m, d["satelite"]) else
                  'El satélite clasifica tejados desde el aire y no comprueba nada sobre '
                  'el terreno: tu reporte es la mirada que le falta. ')
        o.append(f'<div class="aviso aviso--accion">'
                 f'<p><strong>{fmt_prosa(len(d["ciudadanos"]))} reportes ciudadanos</strong> '
                 f'georreferenciados en el entorno de {e(nombre)}, {fmt_prosa(d["con_medio"])} '
                 f'con foto o vídeo{rango}. <span class="badge">verificación automática superada · '
                 f'pendientes de revisión humana</span></p>'
                 f'<p>{porque}'
                 f'¿Estás en {e(nombre)}? <a href="{CHATMAP}" target="_blank" rel="noopener">'
                 f'<strong>Reporta daños con tu ubicación y foto por WhatsApp</strong></a> '
                 f'(ChatMap, de OpenStreetMap Colombia, UN Mappers y el Equipo Humanitario de '
                 f'OpenStreetMap). Tu reporte se publica en el punto exacto que registres '
                 f'en ChatMap, sin los datos ocultos de la foto y sin datos personales.</p></div>')
    else:
        o.append(f'<div class="aviso aviso--accion"><p>Todavía <strong>no hay reportes '
                 f'ciudadanos</strong> georreferenciados en {e(nombre)}. '
                 f'{"Y ningún satélite ha evaluado sus edificios: " if not satelites_con_dato(m, d["satelite"]) else ""}'
                 f'si estás en el municipio, tu reporte puede ser la primera evidencia sobre el '
                 f'terreno. <a href="{CHATMAP}" target="_blank" rel="noopener"><strong>Reporta '
                 f'daños con tu ubicación y foto por WhatsApp</strong></a> (ChatMap, de '
                 f'OpenStreetMap Colombia, UN Mappers y el Equipo Humanitario de '
                 f'OpenStreetMap).</p></div>')
    # ---- evolución del registro
    if d["serie"]:
        o.append('<section class="page-section">')
        o.append("<h2>Cómo avanza el registro oficial</h2>")
        if d["delta"] is not None:
            # Es la distancia entre las fechas, no el número de intervalos
            # observados. Si una captura diaria falta, decir «en dos días» para
            # un periodo del 16 al 20 convertiría una laguna de datos en prosa
            # falsa y además ocultaría el problema al lector.
            dias = (date.fromisoformat(d["serie"][-1][0])
                    - date.fromisoformat(d["serie"][0][0])).days
            o.append(f'<p>Las familias inscritas en {e(nombre)} pasaron de '
                     f'<strong>{fmt(d["primero"]["familias"])}</strong> a '
                     f'<strong>{fmt(d["ultimo"]["familias"])}</strong> entre el '
                     f'{e(fecha_larga(d["serie"][0][0]))} y el '
                     f'{e(fecha_larga(d["serie"][-1][0]))}: un salto del '
                     f'{fmt(d["pct_delta"], 0)}% en {fmt_prosa(dias)} '
                     f'{"día" if dias == 1 else "días"}. El RUD no mide cuánto se rompió '
                     f'el municipio: mide a qué velocidad las autoridades locales alcanzan a '
                     f'registrarlo, y ese registro se verifica después. Por eso <strong>que un municipio '
                     f'no aparezca no significa «sin daño», significa «sin registro aún»</strong>.</p>')
        o.append('<div class="tabla-scroll"><table>')
        o.append('<thead><tr><th>Captura</th><th class="num">Familias</th>'
                 '<th class="num">Personas</th><th class="num">Viv. destruidas</th>'
                 '<th class="num">Viv. averiadas</th></tr></thead><tbody>')
        for fecha, fila in d["serie"]:
            o.append(f'<tr><td>{e(fecha_corta(fecha))}</td>'
                     f'<td class="num">{fmt(fila["familias"])}</td>'
                     f'<td class="num">{fmt(fila["personas"])}</td>'
                     f'<td class="num">{fmt(fila["viv_destruidas"])}</td>'
                     f'<td class="num">{fmt(fila["viv_averiadas"])}</td></tr>')
        o.append("</tbody></table></div>")
        if len(d["serie"]) < MIN_CAPTURAS_GRAFICA:
            o.append(f'<p class="note">La gráfica de evolución aparece a partir de la '
                     f'{MIN_CAPTURAS_GRAFICA}.ª captura diaria: con '
                     f'{fmt_prosa(len(d["serie"]), femenino=True)} solo '
                     f'dibujaría una recta entre dos puntos, no una tendencia.</p>')
        o.append("</section>")

    # ---- prensa
    if d["titulares"]:
        medios = {medio_de_titular(t) for t in d["titulares"]} - {None}
        o.append('<section class="page-section">')
        o.append(f"<h2>Qué publicó la prensa sobre {e(nombre)}</h2>")
        n_piezas, n_medios = len(d["titulares"]), len(medios)
        o.append(f'<p>El monitor ha recogido {fmt_prosa(n_piezas, femenino=True)} '
                 f'pieza{"s" if n_piezas != 1 else ""} de prensa sobre {e(nombre)}, de '
                 f'{fmt_prosa(n_medios)} medio{"s" if n_medios != 1 else ""} '
                 f'identificado{"s" if n_medios != 1 else ""}. La prensa nunca equivale a un '
                 f'balance oficial: aquí consta quién publicó y cuándo, no qué se verificó.</p>')
        o.append('<div class="tabla-scroll"><table>')
        o.append('<thead><tr><th>Fecha</th><th>Titular</th><th>Medio</th></tr></thead><tbody>')
        for t in d["titulares"][:40]:
            medio = medio_de_titular(t)
            titular = t.get("titulo") or ""
            if medio:
                titular = titular.rsplit(" - ", 1)[0]
            o.append(f'<tr><td>{e(fecha_corta((t.get("fecha") or "")[:10]))}</td>'
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
                 f'respondido desde {e(nombre)} el cuestionario de intensidad percibida del '
                 f'Servicio Geológico de Estados Unidos (USGS), así que falta la '
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
                 'superado la verificación automática —intensidad plausible, dentro de la zona, '
                 'fecha coherente con el sismo y sin copias repetidas del mismo archivo—, pero '
                 'nada se marca como validado sin revisión humana.</li>')
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
             + filas_fuentes_satelitales(m, d["satelite"]) +
             f'<tr><td>Reportes ciudadanos</td><td><a href="{CHATMAP}" target="_blank" '
             'rel="noopener">ChatMap · OSM Colombia</a></td>'
             "<td>comunidad, sin validación humana</td></tr>"
             "<tr><td>Titulares</td><td>feeds abiertos del monitor y Google News municipal</td>"
             "<td>prensa · nunca equivale a balance oficial</td></tr>"
             # El código DIVIPOLA y la fecha de la corrida bajaron aquí desde el
             # subtítulo: son trazabilidad, no portada de ficha. La fecha no
             # podía perderse por el camino — un archivo que no dice de cuándo
             # es su cifra deja de ser un archivo.
             f'<tr><td>Identificador del municipio</td>'
             f'<td>DIVIPOLA (División Político-Administrativa) · DANE</td>'
             f'<td>código oficial {e(m["divipola"])}, catálogo nacional de '
             f'municipios</td></tr>'
             # «Fecha de las cifras», no «de esta página»: el valor sale de
             # `ctx["rud"]["generado"]`, que es cuándo se capturó el RUD. Mientras
             # las dos corridas van juntas coinciden, pero el día que la página se
             # genere sin RUD nuevo, «actualizada» afirmaría más de lo que sabemos.
             f'<tr><td>Fecha de las cifras</td><td>captura diaria del RUD</td>'
             f'<td>datos del {e(fecha_larga(d["generado"]))}</td></tr>'
             "</tbody></table></div>")
    o.append('<p class="note">Cada petición queda registrada con su dirección, su código de '
             "respuesta, su huella digital (sha256) y su fecha; la copia original de lo que "
             "devolvió cada fuente se archiva sin tocarla en el repositorio público, así que "
             "cualquier cifra de esta página puede reconstruirse y rebatirse.</p>")
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
                or m.get("en_aoi_copernicus")
                or any(m.get(sat["campo"]) is not None for sat in SATELITES if sat["campo"])
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
        if d["hay_evidencia"]:
            datos = destino / "data" / "public" / "municipios" / d["slug"]
            datos.mkdir(parents=True, exist_ok=True)
            (datos / "evidencia.json").write_text(
                json.dumps(d["evidencia"], ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8")
        escritas.append(d["slug"])
    return {"fichas": len(escritas), "omitidas": len(omitidas),
            "sin_senal": omitidas, "slugs": sorted(escritas)}


# ---------------------------------------------- tabla de municipios (fase B)
# Espejo de ESTADO_MUNICIPIO en site/ui.js. Vive en dos superficies porque el
# mapa (app.js) lo sigue necesitando en el navegador: si tocas una, mira la otra.
# `TestEspejoConElFrontend::test_estados_de_municipio_coinciden` compara las dos
# tablas enteras —clave, etiqueta, color y explicación— y falla si divergen.
ESTADO_MUNICIPIO = {
    "en_aoi": ("En zona Copernicus", "--s1",
               "El municipio cae dentro de una zona que el satélite del servicio "
               "de emergencias de Copernicus analizó y para la que publicó un "
               "mapa de daños"),
    "evaluado_unosat": ("Evaluado por UNOSAT", "--s9",
                        "El centro satelital de la ONU evaluó allí edificio a "
                        "edificio, fuera de toda zona de Copernicus. Es lectura "
                        "de imágenes de muy alta resolución, no comprobada sobre "
                        "el terreno por la propia fuente"),
    "evaluado_satelite": ("Evaluado por satélite", "--s9",
                         "Un servicio de cartografía rápida evaluó allí edificio a edificio, "
                         "fuera de toda zona de Copernicus. Es lectura de imágenes de muy "
                         "alta resolución, no comprobada sobre el terreno"),
    "intensidad_alta": ("Intensidad alta", "--warning",
                        "La población declaró una intensidad de 6 o más en el "
                        "cuestionario del Servicio Geológico de Estados Unidos, "
                        "y ningún satélite ha publicado mapa de daños"),
    "mencion_prensa": ("Mencionado en prensa", "--s2",
                       "Titulares que lo nombran, sin mapa de daños por satélite "
                       "ni intensidad percibida alta"),
    "solo_rud": ("Solo registro municipal (RUD)", "--s8",
                 "El registro de damnificados que carga el municipio es su única "
                 "documentación del daño: ningún producto satelital ni titular lo "
                 "ha verificado de forma independiente"),
    "fuera_aoi": ("Intensidad sentida", "--muted",
                  "Se sintió, con intensidad percibida por debajo de 6, y ningún "
                  "satélite ni titular lo documenta; tampoco tiene damnificados "
                  "inscritos en el registro oficial"),
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
        # El segundo destino de la fila, y el único que no es la ficha. Va en
        # su propio elemento —como todo lo demás de la celda— para que el CSS
        # pueda subirlo por encima del enlace estirado; si no, la capa que
        # hace pulsable la fila entera se lo tragaría.
        return (f'<a href="noticias.html?municipio={urllib.parse.quote(m["municipio"])}"'
                f' style="color:var(--s1)">{fmt(m["n_noticias"])}</a>')
    if m.get("requiere_depto"):
        return (f'<span title="Su nombre es palabra común, lugar extranjero o se repite '
                f'en otro departamento: solo se le atribuyen titulares que nombren también '
                f'{e(m["departamento"])}. Puede haber prensa que el monitor no pueda '
                f'asignarle.">0</span>')
    return valor_suelto(fmt(0))


def _celda_satelite(m: dict, n_copernicus: int, cruce: dict | None = None) -> str:
    """Lo que han visto los satélites: una línea por servicio, nunca sumadas.

    Cada servicio elige qué trozo de ciudad mira y con qué imagen. Copernicus
    cuenta edificios a los que ha clasificado un grado de daño dentro de las
    zonas que delimitó; UNOSAT, los que ha observado uno a uno sobre imagen de
    muy alta resolución; ICube-SERTIT, los de su propio recorte para la Carta
    Internacional. En Pereira, Copernicus clasificó 193 edificios sobre 9,8 km²
    y SERTIT 252 sobre 2,78 km²: **dos ventanas distintas sobre la misma ciudad,
    no dos versiones de la misma cifra**. Sumar 193 y 252 daría un número que no
    significa nada, y quedarse con la mayor sería elegir por la fuente.

    Cuando dos servicios coinciden sobre un municipio, la celda añade cuántos
    edificios vieron los dos —y cuántos de esos ven con distinta gravedad—, o
    dice que no comparten ninguno. Esa cuenta no se hace aquí: la resuelve
    `ingest/satelites.py` y llega hecha en monitor.json.

    Donde ninguno ha mirado no hay cero, hay ausencia (R3)."""
    cruce = cruce or {}
    partes = []
    if n_copernicus:
        partes.append(
            f'<span title="Edificios con daño clasificado uno a uno por lectura de imágenes '
            f'de satélite del servicio de emergencias de Copernicus (activación EMSR916), cuya coordenada '
            f'cae en este municipio, dentro de las zonas que Copernicus delimitó para '
            f'analizar.">{fmt(n_copernicus)} '
            f'<span style="color:var(--muted)">Copernicus</span></span>')
    if m.get("unosat_edificios") is not None:
        otros = ""
        if m.get("unosat_codigo_inconsistente"):
            otros = (f' <span title="De esos edificios, los que UNOSAT publica con un código '
                     f'de evento distinto del que declara su propio producto, y fechado '
                     f'después de la imagen que los retrata: la fuente se contradice a sí '
                     f'misma. Entran en la cifra —a qué terremoto pertenece un punto lo dice '
                     f'el identificador del producto que lo publica— y se señalan aquí para '
                     f'que la discrepancia no se pierda dentro del total. El monitor no '
                     f'reescribe la etiqueta ni les atribuye ningún otro sismo, porque el '
                     f'dato no lo sostiene." '
                     f'style="color:var(--warning)">⚠ {fmt(m["unosat_codigo_inconsistente"])} '
                     f'con código inconsistente</span>')
        partes.append(
            f'<span title="Edificios evaluados por UNITAR-UNOSAT, el centro satelital de la '
            f'ONU, sobre imagen de muy alta resolución. Entre paréntesis, los que la propia '
            f'fuente da por observados; el resto son hipótesis suyas. No está validado en '
            f'campo.">{fmt(m["unosat_edificios"])} '
            f'<span style="color:var(--muted)">({fmt(m["unosat_observados"])}) UNOSAT</span>'
            f'</span>{otros}')
    if m.get("sertit_edificios") is not None:
        # El recorte va en el título: es lo que convierte «252» en una cifra
        # legible. Sin saber sobre cuánta superficie mira cada servicio, dos
        # cifras en la misma celda parecen competir por ser la verdadera.
        # «ventana», no «recorte del municipio»: es un recuadro propio del
        # servicio, que en La Virginia cubre más superficie que el municipio.
        recorte = (f' sobre una ventana de {fmt(m["sertit_area_km2"], 2)} km²'
                   if m.get("sertit_area_km2") is not None else "")
        # Aquí el «+» sí es un más: son puntos que la capa trae y el recuento
        # NO incluye, al revés que el ⚠ de UNOSAT, que marca una parte de la
        # cifra ya contada. La diferencia entre los puntos de la capa y los que
        # se cuentan tiene que verse: en Cali, 94 clasificados de 103 puntos era
        # una resta que no se explicaba en ninguna parte.
        sin_grado = ""
        if m.get("sertit_sin_grado"):
            sin_grado = (f' <span title="Puntos que ICube-SERTIT marcó en este municipio y '
                         f'para los que no asignó grado de daño («Not Applicable»). No se '
                         f'cuentan como daño clasificado —afirmarlo sería decir lo que la '
                         f'fuente no dijo— ni se descartan: siguen pintados en el mapa." '
                         f'style="color:var(--warning)">+{fmt(m["sertit_sin_grado"])}</span>')
        partes.append(
            f'<span title="Edificios evaluados por ICube-SERTIT (laboratorio ICube, '
            f'Universidad de Estrasburgo) para la activación 1048 de la Carta Internacional '
            f'del Espacio y las Grandes Catástrofes, sobre imagen Pléiades{recorte}. Entre '
            f'paréntesis, los que da por destruidos; el resto son daños y daños posibles. '
            f'Fotointerpretación, sin validar en campo. © ICube-SERTIT 2026.'
            f'">{fmt(m["sertit_edificios"])} '
            f'<span style="color:var(--muted)">({fmt(m["sertit_destruidos"])}) SERTIT</span>'
            f'</span>{sin_grado}')
    if len(partes) > 1:
        comunes = cruce.get("coincidencias")
        if comunes:
            discrepan = cruce.get("discrepan_de_grado") or 0
            grado = (f' En {fmt(discrepan)} de ellos los servicios no coinciden en la '
                     f'gravedad que le asignan al mismo edificio.' if discrepan else "")
            partes.append(
                f'<span style="color:var(--muted)" title="Edificios que aparecen en dos '
                f'productos a la vez: dos puntos de servicios distintos a menos de '
                f'{fmt(cruce.get("umbral_m"))} metros se toman por el mismo edificio.{grado} '
                f'El resto de cada cifra solo lo vio ese servicio. Por eso las cifras no se '
                f'suman: el municipio tiene {fmt(cruce.get("unidades"))} edificios evaluados, '
                f'contando cada uno una sola vez.">{fmt(comunes)} en común</span>')
        elif cruce:
            partes.append(
                '<span style="color:var(--muted)" title="Los servicios cartografiaron zonas '
                'distintas del mismo municipio y no comparten ni un edificio. No hay nada que '
                'comparar entre las dos cifras ni motivo para sumarlas: son dos ventanas sobre '
                'trozos distintos de la ciudad.">sin edificios en común</span>')
    if not partes:
        return ('<span title="Ningún producto satelital de daño ha mirado este municipio. '
                'Un guion no es un cero: es ausencia de evaluación.">—</span>')
    return "<br>".join(partes)



def filas_municipios(ctx: dict) -> str:
    """Las filas de la tabla de municipios, ya escritas en el HTML.

    La primera celda enlaza a la ficha del municipio: sin este enlace las fichas
    quedan huérfanas y solo se descubren por el sitemap, que es un canal mucho
    más débil que un enlace real desde una página del sitio.

    Ese enlace es también el que se estira sobre la fila entera desde el CSS,
    así que la fila se escribe con una regla: **nada de texto pelado colgando
    de un `<td>`**. Cada valor va dentro de un elemento —`valor_suelto()` para
    las cifras, un `<span title>` para lo que se explica, el `<a>` de prensa
    para el segundo destino— porque solo un elemento se puede subir por encima
    de la capa. Un texto sin envoltorio deja de poder copiarse y su título deja
    de poder leerse."""
    filas = []
    for m in sorted(ctx["municipios"], key=lambda x: x.get("poblacion_2026") or 0,
                    reverse=True):
        etiqueta, color, explica = ESTADO_MUNICIPIO.get(m.get("estado"), SIN_CLASIFICAR)
        enlace = f"/municipio/{slug(m['municipio'])}/" if es_elegible(m["municipio"], ctx) else None
        nombre = f"<strong>{e(m['municipio'])}</strong>"
        # `fila-enlace` es la mitad de un pareado: la otra vive en
        # `site/styles.css` y estira este ancla sobre la fila entera. Si se
        # renombra aquí, la fila deja de ser pulsable sin que se vea nada roto;
        # por eso el nombre de la clase tiene su test espejo (M2).
        celda = (f'<a class="fila-enlace" href="{enlace}" style="color:inherit">{nombre}</a>'
                 if enlace else nombre)
        buscar = norm_busqueda(f'{m["municipio"]} {m["departamento"]}')
        n_cop = ctx["conteo_satelite"].get(m["municipio"], 0)
        n_ciu = ctx["conteo_ciudadanos"].get(m["municipio"], 0)
        etiquetas = []
        if not satelites_con_dato(m, n_cop):
            etiquetas.append("sin-satelite")
        if m.get("rud_personas"):
            etiquetas.append("con-rud")
        else:
            etiquetas.append("sin-rud")
        if n_ciu:
            etiquetas.append("con-ciudadanos")
        # clave de orden de la columna satelital: los edificios únicos del
        # municipio, cada uno contado una vez aunque lo hayan visto dos
        # servicios. Sirve para ordenar «cuánto se ha mirado»; las cifras NO se
        # suman ni en la celda ni aquí, porque miden trozos distintos de ciudad.
        v_sat = evaluados_unicos(m, ctx)
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
            f'<td class="num" title="Población proyectada para 2026 por el Departamento '
            f'Administrativo Nacional de Estadística (DANE), por municipio y área">'
            f'{valor_suelto(fmt(m.get("poblacion_2026")))}</td>'
            f'<td class="num">{_celda_satelite(m, n_cop, ctx["cruce_satelital"].get(m["municipio"]))}</td>'
            f'<td class="num">{valor_suelto(fmt(m.get("rud_personas")))}</td>'
            f'<td class="num">{valor_suelto(pct(m.get("tasa_rud_pct")))}</td>'
            f'<td class="num">{valor_suelto(fmt(m.get("dyfi_max_cdi"), 1))}</td>'
            f'<td class="num">{valor_suelto(fmt(m.get("dyfi_respuestas")))}</td>'
            f'<td class="num">{_celda_prensa(m)}</td>'
            f'<td>{valor_suelto(e(", ".join(m.get("fuentes") or [])) or "—")}</td>'
            "</tr>")
    return "\n".join(filas)


# --------------------------------------------- la banda de brechas (portada)
def zonas_sin_registro(mon: dict) -> list:
    """Zonas con edificios afectados por satélite y todavía sin registro oficial.

    Espejo de `UI.zonasSinRegistro` en site/ui.js. No se escriben a mano en
    ningún texto: el día que una de ellas entre al registro, la frase que la
    nombraba debe dejar de nombrarla sola (R11)."""
    vistas = []
    for a in mon.get("aois") or []:
        if not (a.get("resumen") or {}).get("edificios_afectados"):
            continue
        if (a.get("cruce") or {}).get("n_oficial"):
            continue
        nombre = aoi_es(a.get("aoi"))
        if nombre not in vistas:
            vistas.append(nombre)
    return vistas


def ejemplos_sin_registro(mon: dict) -> str:
    """El inciso que nombra un par de esas zonas dentro de una frase.

    Espejo de `UI.ejemplosSinRegistro`. Dos como mucho: los textos citan
    ejemplos, no un inventario."""
    zonas = zonas_sin_registro(mon)
    # escapado como todo lo demás del módulo: los nombres vienen de Copernicus,
    # así que el riesgo es nulo hoy, pero la disciplina no admite excepciones
    # por lo improbable de la fuente
    return f" (p. ej. {' y '.join(e(z) for z in zonas[:2])})" if zonas else ""


def _dias_entre(iso: str, referencia: str):
    """Días enteros entre dos fechas ISO. R3: sin fecha no hay cero, hay nada."""
    desde, hasta = _FECHA.match(iso or ""), _FECHA.match(referencia or "")
    if not (desde and hasta):
        return None
    return (date(int(hasta[1]), int(hasta[2]), int(hasta[3]))
            - date(int(desde[1]), int(desde[2]), int(desde[3]))).days


def _silencio(iso: str, referencia: str) -> str:
    """«(hace 1.330 días)», con la fecha dentro para que el navegador la refresque.

    El número se escribe contra la fecha de los datos, no contra el reloj del
    build; `site/app.js` lo recalcula al abrir la página, porque quien lee puede
    hacerlo semanas después desde una caché. Si no hay fecha, no hay paréntesis:
    una cuenta de días sin origen no se publica."""
    dias = _dias_entre(iso, referencia)
    if dias is None:
        return ""
    return f' (hace <span data-dias-desde="{e(iso[:10])}">{fmt(dias)}</span> días)'


def banda_brechas(ctx: dict) -> str:
    """El resumen de las dos brechas centrales, escrito en el build.

    Es el párrafo más citable de la portada y hasta este cambio solo existía en la
    memoria del navegador: quien no ejecuta JavaScript —todo rastreador de
    sistemas de IA— leía una sección vacía, justo lo contrario de lo que
    persigue el prerenderizado de las tablas.

    La redacción vive AQUÍ y en ningún otro sitio. `site/app.js` se limita a
    refrescar los contadores de días.

    Nada se escribe a mano: si el registro oficial se pone al día, o si toda
    zona con daño satelital acaba registrada, las frases dejan de afirmarlo
    solas (R11) — y romperse, aquí, sería una buena noticia."""
    mon = ctx["monitor"]
    hoy = mon.get("generado") or ""
    g = mon.get("brechas_oficiales") or {}
    soc, arc = g.get("ungrd_socrata") or {}, g.get("ungrd_arcgis") or {}
    rud, exposicion = g.get("ungrd_rud"), mon.get("exposicion")

    partes = [
        "<strong>Brecha de reporte oficial:</strong> lo que la Unidad Nacional para la "
        "Gestión del Riesgo de Desastres (UNGRD) publica en el portal datos.gov.co llega "
        f"hasta el <strong>{fecha_larga(soc.get('hasta'))}</strong>"
        f"{_silencio(soc.get('hasta'), hoy)}; su otro registro público, el de ArcGIS, "
        f"hasta el <strong>{fecha_larga(arc.get('max_fecha'))}</strong>"
        f"{_silencio(arc.get('max_fecha'), hoy)}. El sistema nacional de información del "
        "riesgo (SNIGRD, 2026) no ofrece ninguna vía de consulta automática. "
    ]
    if rud:
        # la frase completa es condicional, no solo el paréntesis: el día que
        # toda zona con daño satelital tenga registro municipal, afirmar la
        # brecha sería falso
        ejemplos = ejemplos_sin_registro(mon)
        cierre = (f"La brecha ahora es municipal: donde las autoridades locales aún no "
                  f"registran{ejemplos}, el satélite sigue siendo la única evidencia. "
                  if ejemplos else
                  "Ya no queda ninguna zona con daño satelital sin registro municipal. ")
        partes.append(
            "<br><strong>La brecha empezó a cerrarse:</strong> el "
            '<a href="https://rud.gestiondelriesgo.gov.co/" target="_blank" '
            'rel="noopener">RUD</a> (Registro Único de Damnificados) ya cubre el evento — '
            f"<strong>{fmt(rud.get('municipios'))}</strong> municipios con "
            f"<strong>{fmt(rud.get('familias'))}</strong> familias y "
            f"{fmt(rud.get('viv_destruidas'))} viviendas destruidas registradas. " + cierre)
    # R3, y aquí duele especialmente: si falta la clave, «Copernicus entregó cero
    # productos» no es un dato que falta, es una acusación falsa a la fuente. Un
    # cero medido de verdad —una lista vacía— sí se publica; una clave ausente
    # retira la afirmación entera.
    medidas = []
    entregas = mon.get("entregas")
    if entregas is not None:
        medidas.append(f"Copernicus entregó {fmt_prosa(len(entregas))} productos")
    reportes = (mon.get("citizen") or {}).get("chatmap_total")
    if reportes is not None:
        medidas.append(f"la comunidad aportó {fmt(reportes)} reportes con foto")
    if medidas:
        frase = " y ".join(medidas)
        partes.append(frase[0].upper() + frase[1:] + ". ")
    if exposicion:
        partes.append(
            "<br><strong>Exposición sin mapeo:</strong> unas "
            f"{fmt(exposicion.get('expuesta_mmi6plus'))} personas viven donde el sismo "
            "alcanzó una intensidad de 6 o más en la escala de Mercalli modificada, según "
            "la estimación rápida del Servicio Geológico de Estados Unidos (PAGER); las "
            "zonas mapeadas por Copernicus cubren a unas "
            f"{fmt(exposicion.get('en_aois_copernicus'))} "
            f"({pct(exposicion.get('pct_cubierta'))}). "
            "El resto es población que nadie ha mirado de cerca.")
    return "".join(partes)


def filas_portada(ctx: dict) -> str:
    """La tabla de la portada: municipios con evidencia sobre el terreno.

    Deja de organizarse por lo que el satélite decidió mirar (las AOI de la
    activación) y pasa a organizarse por dónde hay prueba georreferenciada,
    venga del satélite o de la comunidad. El hallazgo que lo justifica lo
    escribe `nota_mirada_portada` con las cifras del día, para que ni el texto
    del sitio ni este comentario envejezcan por su cuenta.

    Cada fila lleva su coordenada para que el clic siga centrando el mapa.
    El detalle por AOI —vías, interrupciones, fecha de entrega— no cabe en una
    tabla municipal y sigue publicado en crosscheck.csv."""
    filas = []
    for m in municipios_con_evidencia_puntual(ctx):
        etiqueta, color, explica = ESTADO_MUNICIPIO.get(m.get("estado"), SIN_CLASIFICAR)
        sat = m["n_satelite"]
        ciu = m["n_ciudadanos"]
        cruce = ctx["cruce_satelital"].get(m["municipio"])
        ficha = f"/municipio/{slug(m['municipio'])}/"
        filas.append(
            f'<tr data-lat="{"" if m["lat"] is None else m["lat"]}"'
            f' data-lon="{"" if m["lon"] is None else m["lon"]}"'
            f' data-buscar="{e(norm_busqueda(m["municipio"] + " " + m["departamento"]))}">'
            f'<td><a href="{ficha}" style="color:inherit"><strong>{e(m["municipio"])}</strong></a>'
            f'<br><span style="color:var(--muted)">{e(m["departamento"])}</span></td>'
            f'<td><span class="badge" style="--bc:var({color})" title="{e(explica)}">'
            f'{e(etiqueta)}</span></td>'
            f'<td class="num" title="Proyección DANE 2026">{fmt(m.get("poblacion_2026"))}</td>'
            f'<td class="num">{_celda_satelite(m, sat, cruce)}</td>'
            f'<td class="num">{fmt(ciu) if ciu else "—"}</td>'
            f'<td class="num">{fmt(m.get("rud_personas"))}</td>'
            f'<td class="num">{_celda_prensa(m)}</td>'
            "</tr>")
    return "\n".join(filas)


def nota_mirada_portada(ctx: dict) -> str:
    """Cuántos municipios ha mirado cada fuente, escrito en el build.

    La frase vivía a mano en `site/index.html` y envejecía sola: cada corrida
    diaria mueve el recuento ciudadano, y llegó a anunciar 36 municipios con 43
    en su propia tabla, tres párrafos más abajo. Sale de las mismas filas que la
    tabla —`municipios_con_evidencia_puntual`—, así que texto y tabla no pueden
    contradecirse.

    Devuelve la oración entera, raya incluida: si algún día no se inyecta, la
    portada queda con una frase correcta y sin la cifra, nunca con un hueco."""
    filas = municipios_con_evidencia_puntual(ctx)
    sat = len([m for m in filas if m["n_evaluados"]])
    ciu = len([m for m in filas if m["n_ciudadanos"]])
    return (f" —<strong>los satélites han mirado {fmt_prosa(sat)} municipios; "
            f"la comunidad ha documentado {fmt_prosa(ciu)}</strong>")


# ------------------------------------------------ los filtros rápidos del RUD
# Los cuatro chips, con su rótulo, su explicación y su predicado, en UN solo
# sitio. Antes vivían partidos: `site/rud.js` traía el array `CHIPS` con las
# condiciones para contar las filas ya escritas, y `filas_rud` traía aquí su
# propia copia de esas mismas condiciones para etiquetar cada fila. Dos
# definiciones de lo mismo en dos lenguajes (M2): el día que una cambiara, el
# chip diría «Nuevos (49)» y filtraría otra cosa, y nada lo habría avisado.
# Ahora el recuento del chip y la etiqueta de la fila salen del mismo
# predicado, y `tests/test_render_html.py::TestChipsDelRud` los compara.
CHIPS_RUD = (
    ("todos", "Todos", None, lambda m: True),
    ("nuevos", "Nuevos",
     "Municipios que aparecieron por primera vez en la última captura",
     lambda m: bool(m.get("nuevo"))),
    ("crecieron", "Crecieron en la última captura",
     "Su registro subió respecto a la captura anterior: siguen registrando",
     lambda m: (m.get("delta_familias") or 0) > 0),
    ("destruidas", "Con viviendas destruidas",
     "El municipio ya ha cargado viviendas destruidas. Que un municipio no salga "
     "aquí puede ser que aún no las haya evaluado",
     lambda m: (m.get("viv_destruidas") or 0) > 0),
)


def _chips_de(m: dict) -> list:
    """Los filtros a los que pertenece un municipio.

    «todos» no etiqueta nada: es el chip que no filtra, y escribirlo en cada
    fila sería ruido en 207 atributos."""
    return [clave for clave, _, _, cumple in CHIPS_RUD
            if clave != "todos" and cumple(m)]


def chips_rud(ctx: dict) -> str:
    """La tira de filtros de la tabla del RUD, con su recuento.

    El número entre paréntesis lo contaba el navegador sobre las filas ya
    escritas; ahora lo cuenta el build sobre el mismo dato del que salen las
    etiquetas. Quien no ejecuta JavaScript leía cuatro botones sin números —o
    ninguno, si algo antes había fallado— y ahora lee la composición del
    registro sin pulsar nada.

    `aria-pressed` acompaña a la clase `activa`: son las dos mecánicas del
    mismo estado y `styles.css` las funde en un solo selector; el navegador
    sigue moviendo las dos al pulsar."""
    munis = (ctx["rud"] or {}).get("municipios") or []
    botones = []
    for clave, etiqueta, tip, cumple in CHIPS_RUD:
        activo = clave == "todos"
        botones.append(
            f'<button class="chip{" activa" if activo else ""}"'
            f' data-chip="{clave}" aria-pressed="{"true" if activo else "false"}"'
            + (f' title="{e(tip)}"' if tip else "")
            + f'>{e(etiqueta)} ({fmt(sum(1 for m in munis if cumple(m)))})</button>')
    return "".join(botones)


def _salto_del_rud(rud: dict):
    """Cómo se reparte el último salto de familias del RUD.

    La pregunta editorial no es cuánto creció, sino POR DÓNDE: un registro que
    crece porque aparecen municipios nuevos se está acercando a su cobertura
    final; uno que crece porque los municipios ya contados suben sus cifras no
    se está estabilizando, y cualquier total suyo es un mínimo provisional
    (R16). Se calcula recorriendo `detalle_diario` municipio a municipio, con
    la clave `(departamento, municipio)` y nunca por nombre normalizado: unir
    por nombre es el error de 206 familias que ya se cazó con «Guadalajara de
    Buga» (R10, M8).

    Devuelve None —y la frase desaparece entera— si no hay con qué compararse o
    si el reparto no cuadra con el salto de la serie. Un desglose que no suma
    su propio total no se publica (M7): es aritmética, y si falla es que el
    detalle diario y la serie ya no hablan del mismo corte."""
    serie = rud.get("serie") or []
    detalle = rud.get("detalle_diario") or {}
    if len(serie) < 2:
        return None
    hoy, ayer = serie[-1].get("fecha"), serie[-2].get("fecha")
    if hoy not in detalle or ayer not in detalle:
        return None
    antes = {(x.get("departamento"), x.get("municipio")): (x.get("familias") or 0)
             for x in detalle[ayer]}
    nuevos = revision = 0.0
    municipios_nuevos = 0
    for x in detalle[hoy]:
        clave = (x.get("departamento"), x.get("municipio"))
        familias = x.get("familias") or 0
        if clave in antes:
            revision += familias - antes[clave]
        else:
            nuevos += familias
            municipios_nuevos += 1
    salto = (serie[-1].get("familias") or 0) - (serie[-2].get("familias") or 0)
    if round(nuevos + revision) != round(salto):
        # R11: el supuesto roto avisa, no rompe la corrida (R13) ni publica un
        # desglose que no cuadra.
        print(f"AVISO: el desglose del salto del RUD ({nuevos + revision:.0f}) no "
              f"cuadra con la serie ({salto:.0f}); la frase no se publica")
        return None
    if nuevos <= 0 or revision <= 0 or municipios_nuevos <= 0:
        # La oración que se construye con esto termina afirmando que lo que
        # crece son los municipios ya contados. Si al salto le falta una de sus
        # dos mitades, esa conclusión deja de ser cierta: la frase no se
        # corrige con un cero, se retira entera (M10).
        return None
    return {"salto": salto, "nuevos": nuevos, "revision": revision,
            "municipios_nuevos": municipios_nuevos}


def entradilla_rud(ctx: dict) -> str:
    """La frase que resume la página bajo el titular, con el hallazgo dentro.

    Todo sale de `serie[-1]` y de `detalle_diario`; ni una cifra se escribe a
    mano. Va en `fmt` y no en `fmt_prosa` a propósito: la oración existe para
    el contraste entre 16.155 y 3.179, y las letras lo disuelven.

    **M10**: donde falta el dato se calla ese trozo. Si no hay ni una captura,
    lo dice con palabras — devolver cadena vacía rompería el build, y era
    además el mensaje que `rud.js` escribía en el navegador cuando el JSON no
    llegaba: quien no ejecuta JavaScript no lo leía nunca."""
    rud = ctx["rud"] or {}
    serie = rud.get("serie") or []
    if not serie:
        return ("<p>Todavía no hay ninguna captura del registro oficial de "
                "damnificados. La serie y el detalle municipal se publican en "
                "cuanto la UNGRD abra el primer corte.</p>")
    ult = serie[-1]
    familias, personas = ult.get("familias"), ult.get("personas")
    if familias is not None and personas is not None:
        sujeto = (f'<b>{fmt(familias)} familias</b> damnificadas '
                  f'—<b>{fmt(personas)} personas</b>—')
    elif familias is not None:
        sujeto = f'<b>{fmt(familias)} familias</b> damnificadas'
    elif personas is not None:
        sujeto = f'<b>{fmt(personas)} personas</b> damnificadas'
    else:
        sujeto = None
    municipios = ult.get("municipios")
    if sujeto and municipios is not None:
        cabeza = f'El registro oficial suma {sujeto} en <b>{fmt(municipios)} municipios</b>'
    elif sujeto:
        cabeza = f'El registro oficial suma {sujeto}'
    elif municipios is not None:
        cabeza = f'El registro oficial cubre <b>{fmt(municipios)} municipios</b>'
    else:
        cabeza = None

    destruidas, averiadas = ult.get("viv_destruidas"), ult.get("viv_averiadas")
    if destruidas is not None and averiadas is not None:
        viviendas = (f'<b>{fmt(destruidas)} viviendas destruidas</b> y '
                     f'<b>{fmt(averiadas)} averiadas</b>')
    elif destruidas is not None:
        viviendas = f'<b>{fmt(destruidas)} viviendas destruidas</b>'
    elif averiadas is not None:
        viviendas = f'<b>{fmt(averiadas)} viviendas averiadas</b>'
    else:
        viviendas = None

    frases = []
    if cabeza:
        # La fecha del corte viaja DENTRO de la frase: es el párrafo que se cita
        # suelto, lejos del sello del encabezado, y una cifra del RUD sin su
        # corte miente en 48 horas (M7).
        corte = (f', en la captura del {fecha_larga(ult["fecha"])}'
                 if ult.get("fecha") else "")
        frases.append(cabeza + (f', con {viviendas}' if viviendas else "") + corte + ".")
    elif viviendas:
        frases.append(f'El registro oficial ha cargado {viviendas}.')
    frases.append("Es un <b>mínimo provisional</b>, no un balance cerrado.")

    salto = _salto_del_rud(rud)
    if salto:
        frases.append(
            f'De las {fmt(salto["salto"])} familias que entraron en la última '
            f'captura, <b>{fmt(salto["revision"])} son revisión al alza de '
            f'municipios que ya estaban registrados</b> y solo '
            f'{fmt(salto["nuevos"])} llegan de los '
            f'{fmt(salto["municipios_nuevos"])} que aparecieron por primera vez: '
            f'lo que crece no es la cola del registro, son los municipios ya '
            f'contados.')
    return "<p>" + " ".join(frases) + "</p>"


def nota_rud(ctx: dict) -> str:
    """El pie de la tabla: la prosa que no depende de ningún filtro.

    El recuento vivo —«15 de 207 municipios con los filtros activos»— se queda
    en el navegador, que es el único que sabe qué hay filtrado. Aquí vive lo
    que vale igual con la página recién abierta o con tres filtros puestos, y
    vive SOLO aquí: si el literal siguiera además en `rud.js`, el día que uno
    cambiara la página diría dos cosas (M2)."""
    rud = ctx["rud"] or {}
    serie = rud.get("serie") or []
    partes = ["La columna Δ compara con la captura anterior"]
    if serie and serie[-1].get("fecha"):
        partes[0] += ('; «nuevo» marca los municipios que aparecieron por primera '
                      f'vez el {fecha_larga(serie[-1]["fecha"])}')
    partes[0] += "."
    if serie and serie[0].get("fecha"):
        partes.append(f'Serie iniciada el {fecha_larga(serie[0]["fecha"])}.')
    partes.append("Un cero en las columnas de viviendas puede significar «todavía "
                  "sin evaluar», no «sin daño».")
    # R11: la advertencia se apaga sola el día que no quede ningún punto
    # reconstruido. No es un literal que alguien tenga que acordarse de borrar.
    if any(d.get("reconstruido") for d in serie):
        partes.append("Los puntos huecos de la curva no son capturas del RUD: se "
                      "reconstruyeron desde otra evidencia archivada porque ese día "
                      "se perdió la corrida, y de ellos solo se conoce el total, no "
                      "el detalle municipal.")
    return " ".join(partes)


def _n(v) -> str:
    """Un número dentro del SVG, sin la cola decimal que no aporta nada.

    Las familias del RUD llegan como flotantes (`21275.0`), y un
    `data-altas="19334.0"` no es lo que nadie escribiría a mano ni lo que
    espera quien lea el atributo."""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")


def _altas_diarias(serie: list) -> list:
    """Lo que entró desde la captura anterior, día a día.

    El primer día no inventa un alta: sin captura previa el dato no existe, y
    un 0 diría «ese día no entró nadie» (R3)."""
    altas = []
    for i, d in enumerate(serie):
        previo = serie[i - 1].get("familias") if i else None
        altas.append(None if not i or d.get("familias") is None or previo is None
                     else d["familias"] - previo)
    return altas


def grafico_rud(ctx: dict) -> str:
    """El gráfico de familias del RUD, SVG estático escrito en el build.

    Porte de `rud.js::graficoFamilias`, con el precedente de `mapa_svg()`: lo
    dibujaba el navegador, así que la página servía un `<div>` vacío y su
    `<desc>` —ochenta y tantas palabras que narran la serie día a día, la única
    prosa del sitio que crece sola con el dato— no lo leía nadie más que quien
    ejecutaba JavaScript.

    Las dos dependencias del navegador MEJORAN al portarse:

    · `ui.cssVar()` resolvía la variable CSS a un color literal y lo congelaba
      dentro del SVG: el gráfico salía siempre con los colores del tema que
      estuviera puesto al dibujarlo. Aquí se emite `var(--…)`, que es lo que la
      hoja de estilos espera, y el gráfico sigue el tema oscuro como el resto.
    · `clientWidth` medía la caja para elegir el ancho; el `viewBox` ya hace el
      SVG fluido, así que el lienzo es 900 fijo y el ancho lo pone el CSS.

    **No se tocan los colores**: `--s8` significa hoy dos cosas —SERTIT y RUD—
    y unificar la clave de color va en su propia fase. Lo que sí cambia es que
    a partir de ahora esa ambigüedad queda escrita en el artefacto."""
    serie = (ctx["rud"] or {}).get("serie") or []
    if not serie:
        # M10: sin serie no hay gráfico que dibujar, y un lienzo vacío sería
        # peor que decirlo. La entradilla ya cuenta lo mismo con más detalle.
        return ("<p class=\"note\">Sin ninguna captura del RUD todavía no hay "
                "serie que dibujar.</p>")
    W, H = 900, 230
    m_t, m_r, m_b, m_l = 38, 70, 38, 64
    altas = _altas_diarias(serie)
    cambios = [v for v in altas if v is not None]
    max_total = max([1] + [d.get("familias") or 0 for d in serie] + cambios)
    min_cambio = min([0] + cambios)
    techo = max_total * 1.1
    piso = min_cambio * 1.1 if min_cambio < 0 else 0

    def x(i):
        return W / 2 if len(serie) == 1 else m_l + i * (W - m_l - m_r) / (len(serie) - 1)

    def y(v):
        return m_t + (H - m_t - m_b) * (1 - (v - piso) / (techo - piso))

    y0 = y(0)
    paso = (W - m_l - m_r) / max(1, len(serie) - 1)
    ancho_barra = min(44, paso * 0.44)
    descripcion = ". ".join(
        f'{fecha_larga(d.get("fecha"))}: sin captura anterior para calcular '
        f'nuevas inscripciones' if altas[i] is None else
        f'{fecha_larga(d.get("fecha"))}: {fmt(altas[i])} familias desde la '
        f'captura anterior; {fmt(d.get("familias"))} acumuladas'
        for i, d in enumerate(serie))
    ticks = [piso, 0, techo] if piso < 0 else [0, techo / 2, techo]

    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg"'
         f' role="img" class="grafico-rud"'
         f' aria-labelledby="rud-chart-title rud-chart-desc">',
         '<title id="rud-chart-title">Familias registradas en el RUD: total '
         'acumulado y nuevas inscripciones</title>',
         f'<desc id="rud-chart-desc">{e(descripcion)}</desc>']
    for v in ticks:
        yy = y(v)
        o.append(f'<line x1="{_n(m_l)}" x2="{_n(W - m_r)}" y1="{_n(yy)}" '
                 f'y2="{_n(yy)}" stroke="var(--grid)"/>'
                 f'<text x="{_n(m_l - 6)}" y="{_n(yy + 4)}" text-anchor="end" '
                 f'class="g-eje" font-size="10" fill="var(--muted)">'
                 f'{fmt(round(v))}</text>')

    # Las barras van primero para que la curva acumulada permanezca legible encima.
    for i, valor in enumerate(altas):
        if valor is None:
            o.append(f'<text x="{_n(x(i))}" y="{_n(y0 - 7)}" text-anchor="middle" '
                     f'class="g-vacio" font-size="9" fill="var(--muted)">'
                     f'sin base</text>')
            continue
        yy = y(valor)
        # Una corrección a la baja NO es un cero ni un hueco: se pinta con el
        # color de alarma y con su signo, porque el registro también se corrige
        # hacia abajo y eso es información (R3, R16).
        color = "var(--critical)" if valor < 0 else "var(--s8)"
        etiqueta = ("+" if valor > 0 else "") + fmt(valor)
        o.append(
            f'<rect x="{_n(x(i) - ancho_barra / 2)}" y="{_n(min(yy, y0))}" '
            f'width="{_n(ancho_barra)}" height="{_n(max(1, abs(y0 - yy)))}" rx="2" '
            f'fill="{color}" fill-opacity="0.28" stroke="{color}" '
            f'data-altas="{_n(valor)}">'
            f'<title>{e(fecha_larga(serie[i].get("fecha")))}: {etiqueta} familias '
            f'desde la captura anterior</title></rect>'
            f'<text x="{_n(x(i))}" y="{_n(yy + 13 if valor < 0 else yy - 6)}" '
            f'text-anchor="middle" class="g-alta" font-size="10" '
            f'font-weight="600" fill="{color}">{etiqueta}</text>')

    linea = " ".join(f'{"L" if i else "M"} {_n(x(i))} {_n(y(d.get("familias") or 0))}'
                     for i, d in enumerate(serie))
    o.append(f'<path d="{linea}" fill="none" stroke="var(--good)" stroke-width="2.5"/>')
    for i, d in enumerate(serie):
        # el punto reconstruido se pinta hueco: no es una captura del endpoint
        rec = d.get("reconstruido")
        cy = y(d.get("familias") or 0)
        discontinua = ' stroke-dasharray="3 2"' if rec else ""
        origen = (e("; punto reconstruido: " + str(d.get("origen") or ""))
                  if rec else "")
        o.append(
            f'<circle cx="{_n(x(i))}" cy="{_n(cy)}" r="5" '
            f'fill="{"var(--surface-1)" if rec else "var(--good)"}" '
            f'stroke="var(--good)" stroke-width="{2.5 if rec else 2}"'
            f'{discontinua}>'
            f'<title>{e(fecha_larga(d.get("fecha")))}: {fmt(d.get("familias"))} '
            f'familias acumuladas, {fmt(d.get("municipios"))} municipios'
            f'{origen}</title></circle>'
            f'<text x="{_n(x(i))}" y="{_n(cy - 10)}" text-anchor="middle" '
            f'class="g-total" font-size="11" font-weight="600" fill="var(--good)">'
            f'{fmt(d.get("familias"))}</text>'
            f'<text x="{_n(x(i))}" y="{_n(H - m_b + 16)}" text-anchor="middle" '
            f'class="g-dia" font-size="10" fill="var(--muted)">'
            f'{dia_mes(d.get("fecha"))}</text>')

    lx = m_l
    o.append(
        f'<rect x="{_n(lx)}" y="7" width="12" height="9" rx="2" fill="var(--s8)" '
        f'fill-opacity="0.28" stroke="var(--s8)"/>'
        f'<text x="{_n(lx + 18)}" y="15" class="g-leyenda" font-size="10" '
        f'fill="var(--ink-2)">Nuevas desde captura anterior</text>'
        # La segunda entrada viaja en su propio grupo porque en pantalla
        # estrecha la letra CRECE (ver `.grafico-rud` en styles.css) y la
        # primera entrada —29 caracteres— se le echaría encima. Desplazarla
        # con una @media es lo único que deja escalar también la leyenda.
        f'<g class="g-leyenda-2">'
        f'<line x1="{_n(lx + 207)}" x2="{_n(lx + 227)}" y1="12" y2="12" '
        f'stroke="var(--good)" stroke-width="2.5"/>'
        f'<circle cx="{_n(lx + 217)}" cy="12" r="3.5" fill="var(--good)"/>'
        f'<text x="{_n(lx + 234)}" y="15" class="g-leyenda" font-size="10" '
        f'fill="var(--ink-2)">Total acumulado</text></g></svg>')
    return "".join(o)


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
        # el MISMO predicado que cuenta el chip de arriba: si la etiqueta de la
        # fila y el número del chip salieran de dos sitios, divergirían (M2)
        etiquetas = _chips_de(m)
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
    # con límite de palabra, igual que ui.js y el worker: «directo» casaba
    # dentro de «directorio». R10 aplicada a R8.
    r"\b(en vivo|directo|live[-_\s]?news|última hora|ultima hora|minuto a minuto|liveblog)\b",
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
    depende de comparar cada captura con el consolidado acumulado, que se
    calcula recorriendo la serie entera."""
    feed = ctx.get("oficiales") or {}
    filas = []
    for item in sorted(feed.get("items") or [],
                       key=lambda x: x.get("search_date") or "", reverse=True):
        c = item.get("cifras") or {}
        url = item.get("publication_url") or item.get("url") or "#"
        pub = item.get("publisher") or {}
        etiqueta, color = NIVELES.get(item.get("source_level"),
                                      (item.get("source_level") or "Sin nivel", "--muted"))
        # el término inglés lo explica la propia página; el título lo traduce
        # también aquí, para quien llega directo a la tabla
        marca_lb = ('<span class="badge" style="--bc:var(--warning)" title="Cobertura en '
                    'vivo, minuto a minuto: se muestra, pero pesa menos en la serie porque '
                    'sus cifras cambian durante el día">liveblog</span> '
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
            f'<td>{e(fecha_corta(item.get("search_date") or ""))}</td>'
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
        # etiqueta de una lista: cabe la forma corta (9.8), nunca la ISO cruda
        iso = n.get("fecha") or ""
        fecha = fecha_corta(iso[:10]) + (f", {iso[11:16]}" if len(iso) >= 16 else "")
        via = ('  <span class="via" title="Google News recopila titulares de otros medios. '
               'El enlace que publica su feed lleva ahí, no a la página del medio.">'
               'vía Google News</span>' if via_google_news(n) else "")
        etiquetas = "".join(
            # `.etiqueta`: espejo de site/noticias.js — un chip es una acción
            f'<span class="etiqueta mun">{e(m)}</span>' for m in (n.get("municipios") or []))
        salida.append(
            f'<li><span class="meta-n">{e(fecha)}'
            f'{f" · {e(medio)}" if medio else ""}{" · " + via if via else ""}</span>'
            f'{etiquetas}'
            f'<br><a href="{e(n.get("url") or "#")}" target="_blank" rel="noopener nofollow">'
            f'{e(n.get("titulo") or "")}</a></li>')
    return "\n".join(salida)


def medios_distintos(noticias: list) -> int:
    """Cuántas cabeceras distintas hay detrás del corpus, contadas por dominio.

    Por dominio y no por nombre (docs/DECISIONES.md, 19-ago-2026): los nombres
    llegan con dos convenciones —`infobae` en los slugs del EMM, `Infobae` en
    las cabeceras del RSS— y contarlos infla el total con duplicados por
    mayúsculas; el dominio es la clave estable. Quien no trae dominio no se
    cuenta: el nombre de un feed no es un medio (R3)."""
    return len({n["medio_dominio"] for n in noticias if n.get("medio_dominio")})


def entradilla_noticias(ctx: dict) -> str:
    """La frase que resume la página de titulares bajo el titular.

    Las cifras salen del corpus en cada build; ninguna se escribe a mano — la
    portada ya publicó «36 municipios ciudadanos» con 43 en su propia tabla, y
    esa clase de prosa envejece igual aquí. **M10**: donde falta el dato se
    calla ese trozo, y sin corpus se dice con palabras, porque una cadena
    vacía rompería el build.

    R9 en la entradilla: esto es prensa, y la segunda frase lo dice antes de
    que nadie confunda volumen de titulares con balance oficial."""
    noticias = ctx["noticias"] or []
    if not noticias:
        return ("<p>Todavía no hay ningún titular archivado. La lista se "
                "publica en cuanto la primera corrida recorra los feeds.</p>")
    frase = f"El archivo reúne <b>{fmt(len(noticias))} titulares</b>"
    medios = medios_distintos(noticias)
    if medios:
        frase += f" de <b>{fmt(medios)} medios</b> distintos"
    if ctx.get("noticias_desde"):
        frase += f" desde el {fecha_larga(ctx['noticias_desde'])}"
    return ("<p>" + frase + ", emparejados con el municipio o la zona que "
            "mencionan. El volumen de prensa mide atención, no daño: las "
            "cifras que los medios publican citando fuentes oficiales van en "
            '<a href="balances.html">Balances</a>.</p>')


def nota_noticias(ctx: dict) -> str:
    """El pie de la lista de titulares: lo que vale igual sin JavaScript.

    El recuento vivo —«212 de 6.304 titulares · página 2 de 5»— se queda en el
    navegador, que es el único que sabe qué hay filtrado; el paginador también,
    porque sus botones son estado y `noticias.html?p=2` no existe como URL.
    Aquí vive lo que un lector sin JavaScript necesita saber de la lista de
    arriba: que es un recorte, de cuánto, y por dónde sigue. Y vive SOLO aquí:
    si el literal siguiera además en `noticias.js`, el día que uno cambiara la
    página diría dos cosas (M2)."""
    total = len(ctx["noticias"] or [])
    if not total:
        return "Sin titulares archivados todavía, la lista de arriba va vacía."
    if total <= TITULARES_EN_HTML:
        return (f"La lista trae los {fmt(total)} titulares del corpus, del más "
                f"reciente al más antiguo.")
    return (f"La lista trae los {fmt(TITULARES_EN_HTML)} titulares más "
            f"recientes de los {fmt(total)} del corpus, del más reciente al "
            f"más antiguo. El buscador y los filtros de arriba recorren, con "
            f"JavaScript, el corpus completo, que también puede descargarse "
            f"entero con el botón JSON del encabezado.")


# ------------------------------------------------- el sello de fecha, por página
# Un componente y cuatro fuentes, no cuatro redacciones (M2). Lo escribía el
# navegador en las cuatro páginas —`getElementById("generado").textContent`, sin
# guarda ninguna—, así que quien no ejecuta JavaScript leía una raya y una
# excepción en una sola de las cuatro llamadas se llevaba por delante el resto
# del guion. Al servirlo desde el build, esas cuatro llamadas se quedan sin
# motivo y desaparecen.
def sello_portada(ctx: dict) -> str:
    """Portada: solo corrida. `monitor.json` no publica hasta dónde llega la
    serie —son muchas fuentes con cortes distintos—, y M10 prohíbe inventarla."""
    return sello_fechas(None, (ctx["monitor"] or {}).get("generado"), "del monitor")


def sello_municipios(ctx: dict) -> str:
    """Municipios: solo corrida, por lo mismo que la portada."""
    return sello_fechas(None, ctx.get("municipios_generado"), "de los municipios")


def sello_rud(ctx: dict) -> str:
    """RUD: las dos fechas. Es la página donde la confusión se veía."""
    rud = ctx["rud"] or {}
    serie = rud.get("serie") or []
    return sello_fechas(serie[-1].get("fecha") if serie else None,
                        rud.get("generado"), "del RUD")


def sello_balances(ctx: dict) -> str:
    """Balances: las dos también. `oficiales.json` fecha cada nota con la
    búsqueda que la encontró (`search_date`) y el fichero entero con
    `generated_at`; la última búsqueda es hasta dónde llega el rastreo."""
    oficiales = ctx.get("oficiales") or {}
    buscadas = [i.get("search_date") for i in (oficiales.get("items") or [])
                if i.get("search_date")]
    return sello_fechas(max(buscadas) if buscadas else None,
                        oficiales.get("generated_at"), "de los balances")


def sello_noticias(ctx: dict) -> str:
    """Titulares: las dos fechas también. El corte del dato es la fecha del
    último titular archivado —el máximo, porque nada garantiza que los ítems
    lleguen ordenados—, no la corrida que empaquetó el JSON. Era la única de
    las cinco páginas que publicaba «Cargando…» a quien no ejecuta JavaScript,
    y la fecha la escribía `noticias.js` con `data.generado`: la corrida
    vestida de fecha del dato, la confusión que el sello existe para deshacer."""
    fechas = [n["fecha"] for n in (ctx["noticias"] or []) if n.get("fecha")]
    return sello_fechas(max(fechas) if fechas else None,
                        ctx.get("noticias_generado"), "de los titulares")


# --------------------------------- piezas compartidas de las cinco páginas
# Qué enlace va marcado en cada página. Explícito, y no derivado del nombre del
# fichero, porque `nav_estatico()` decide por el `href` y una página que no
# estuviera en `PAGINAS` se quedaría sin marca sin que nada lo dijera.
PAGINAS_GRANDES = {"index.html": "index.html", "municipios.html": "municipios.html",
                   "rud.html": "rud.html", "balances.html": "balances.html",
                   "noticias.html": "noticias.html"}
_MARCA_NAV = re.compile(r'<nav id="site-nav"[^>]*></nav>')
_MARCA_PIE = re.compile(r'<div id="site-footer"[^>]*></div>')
# El contenedor a secas —vacío o ya lleno—. Sirve para distinguir las dos
# averías que comparten síntoma: el marcador borrado y el marcador ya gastado.
_CONTENEDOR_NAV = re.compile(r'<nav id="site-nav"[^>]*>')
_CONTENEDOR_PIE = re.compile(r'<div id="site-footer"[^>]*>')
# El nodo de identidad va en el <head>, y ahí el contenedor vacío es un
# <script> sin cuerpo. Repetir el literal en las cinco páginas habría sido la
# sexta copia de algo cuya única virtud es ser idéntico (M2): se escribe desde
# la misma constante que usan las 208 fichas.
_MARCA_LD = re.compile(
    r'<script type="application/ld\+json" id="site-identity"></script>')
_CONTENEDOR_LD = re.compile(r'<script type="application/ld\+json" id="site-identity">')


def escribir_piezas_compartidas(destino: Path) -> dict:
    """Escribe la identidad, la barra y el pie en las cinco páginas de `dist/`.

    Paso propio y no un generador de `data-gen`: aquel empareja un generador con
    UNA página, lo llama sin argumentos y solo acepta `tbody|ul|span|section`.
    Aquí hacen falta cinco páginas con `activa` distinto y la etiqueta `nav`. Y
    sobre todo, `data-gen` es el mecanismo de los datos del día —lo que caduca
    con la corrida—, y ni una barra de navegación ni el nodo de identidad lo son:
    el de identidad, justo al revés, vale porque no cambia nunca.

    Se hace sobre el artefacto y nunca sobre `site/*.html`, igual que el resto
    del prerenderizado: los marcadores vacíos son lo que se versiona.
    """
    hechas = {}
    for pagina, activa in PAGINAS_GRANDES.items():
        f = destino / pagina
        if not f.exists():
            continue
        html = f.read_text(encoding="utf-8")
        for etiqueta, marca, contenedor, pieza in (
                ("identidad", _MARCA_LD, _CONTENEDOR_LD, BLOQUE_IDENTIDAD),
                ("barra", _MARCA_NAV, _CONTENEDOR_NAV,
                 nav_estatico(activa, botones_js=True)),
                ("pie", _MARCA_PIE, _CONTENEDOR_PIE, pie_estatico())):
            html, sustituciones = marca.subn(lambda _m, p=pieza: p, html, count=1)
            if not sustituciones:
                # Callarse aquí es publicar la página sin barra ni pie y no
                # enterarse: es un error de programación, no una fuente que
                # falla (R13), así que rompe el build. Pero son dos averías
                # distintas con el mismo síntoma, y decir la que no es manda a
                # depurar el sitio equivocado: si el contenedor sigue ahí y no
                # está vacío, el marcador no se ha perdido — se gastó en una
                # pasada anterior. Este paso no es idempotente a propósito (lo
                # escrito ya no deja marcador donde agarrarse); `build_dist.sh`
                # borra `dist/` antes, así que el camino sancionado no llega
                # aquí y quien refresca el artefacto a mano, sí.
                if contenedor.search(html):
                    raise LookupError(
                        f"{pagina}: la {etiqueta} ya estaba escrita — este paso "
                        f"no se puede repetir sobre el mismo dist/; "
                        f"reconstruye desde cero con bash deploy/build_dist.sh")
                raise LookupError(
                    f"{pagina}: no se encuentra el contenedor de la {etiqueta} "
                    f"— ¿se editó el marcador en site/{pagina}?")
        f.write_text(html, encoding="utf-8")
        hechas[pagina] = activa
    return hechas


def inyectar_prerenderizado(destino: Path, ctx: dict) -> dict:
    """Rellena en `dist/` los contenedores marcados con data-gen.

    Ya no son solo tablas —de ahí el nombre—: una cifra escrita dentro de un
    párrafo envejece igual que una fila, y la banda de brechas de la portada es
    prosa entera, probablemente el texto más citable del sitio. El contenedor
    puede ser un <tbody>, un <ul>, un <span> o un <section>.

    Se hace sobre el artefacto, nunca sobre site/*.html: un HTML que cambiara
    entero cada día destruiría el blame, y el dato ya está versionado.

    **Un contenedor declarado que no aparece rompe el build**, con los dos
    mensajes distinguidos de `escribir_piezas_compartidas`: marcador perdido o
    marcador ya gastado. Antes seguía adelante en silencio y la página salía con
    el hueco; el aviso llegaba mucho después, desde `seo_check` y con otro
    nombre."""
    hechas = {}
    generadores = {"municipios": filas_municipios, "portada": filas_portada,
                   "rud": filas_rud, "balances": filas_balances,
                   "noticias": filas_noticias,
                   "mirada-portada": nota_mirada_portada,
                   "brechas": banda_brechas,
                   "portada-sello": sello_portada,
                   "municipios-sello": sello_municipios,
                   "rud-sello": sello_rud,
                   "balances-sello": sello_balances,
                   "noticias-sello": sello_noticias,
                   "rud-resumen": entradilla_rud,
                   "rud-grafico": grafico_rud,
                   "rud-chips": chips_rud,
                   "rud-nota": nota_rud,
                   "noticias-resumen": entradilla_noticias,
                   "noticias-nota": nota_noticias}
    # explícito a propósito: un generador nuevo sin su página revienta aquí en
    # vez de no escribir nada y dejar el contenedor vacío en silencio
    paginas = {"municipios": "municipios", "portada": "index", "rud": "rud",
               "balances": "balances", "noticias": "noticias",
               "mirada-portada": "index", "brechas": "index",
               "portada-sello": "index", "municipios-sello": "municipios",
               "rud-sello": "rud", "balances-sello": "balances",
               "noticias-sello": "noticias",
               "rud-resumen": "rud", "rud-grafico": "rud",
               "rud-chips": "rud", "rud-nota": "rud",
               "noticias-resumen": "noticias", "noticias-nota": "noticias"}
    for nombre, generador in generadores.items():
        pagina = destino / f"{paginas[nombre]}.html"
        if not pagina.exists():
            continue
        html = pagina.read_text(encoding="utf-8")
        # el contenedor puede ser una tabla, una lista, un trozo de prosa dentro
        # de un párrafo o una sección entera, y llevar otros atributos
        marca = re.compile(
            rf'<(tbody|ul|span|section)([^>]*\bdata-gen="{re.escape(nombre)}"[^>]*)></\1>')
        # El contenedor con lo que lleve dentro, para separar las dos averías que
        # comparten síntoma, igual que en `escribir_piezas_compartidas`. No basta
        # con mirar si el contenedor está: en el fallo MÁS probable —un salto de
        # línea entre la apertura y el cierre— el contenedor está y sigue vacío,
        # y acusar ahí al artefacto manda a reconstruir `dist/` cuando lo que hay
        # que mirar es `site/`. Lo que distingue una avería de la otra es si
        # dentro hay algo escrito.
        contenedor = re.compile(
            rf'<(tbody|ul|span|section)[^>]*\bdata-gen="{re.escape(nombre)}"[^>]*>'
            rf'(.*?)</\1>', re.S)
        m = marca.search(html)
        if not m:
            # Callarse aquí publicaba el contenedor vacío y una línea de menos en
            # el informe del build: el fallo aparecía después, en `seo_check`, en
            # otro proceso y con otro nombre. Es un error de programación, no una
            # fuente que falla (R13).
            hay = contenedor.search(html)
            if hay and hay.group(2).strip():
                raise LookupError(
                    f"{pagina.name}: el contenedor «{nombre}» ya estaba escrito "
                    f"— este paso no se puede repetir sobre el mismo dist/; "
                    f"reconstruye desde cero con bash deploy/build_dist.sh")
            raise LookupError(
                f"{pagina.name}: no se encuentra el marcador de «{nombre}» — "
                f"míralo en site/{pagina.name}: la apertura y el cierre van "
                f"pegados, sin un salto de línea entre ellos")
        cuerpo = generador(ctx)
        # la prosa se pega sin saltos de línea: dentro de un párrafo, un salto
        # es un espacio, y la raya quedaría separada de la palabra anterior
        salto = "" if m.group(1) == "span" else "\n"
        html = (html[:m.start()]
                + f"<{m.group(1)}{m.group(2)}>{salto}{cuerpo}{salto}</{m.group(1)}>"
                + html[m.end():])
        pagina.write_text(html, encoding="utf-8")
        # un texto no tiene filas, pero tampoco puede contarse como cero: sería
        # indistinguible de un contenedor que se quedó vacío
        hechas[nombre] = (cuerpo.count("<tr ") + cuerpo.count("<tr>")
                          + cuerpo.count("<li>")) or 1
    return hechas


# ------------------------------------------------- cifras dentro de atributos
# Un <span data-gen> no cabe dentro de un atributo, y ahí también hay cifras que
# se mueven a diario: la og:description de la portada —lo que se ve al compartir
# el enlace— anunciaba «430+ reportes ciudadanos» con 542 archivados. Para esos
# casos el HTML lleva un marcador {{clave}} y el build escribe el dato del día.
def cifras_del_dia(ctx: dict) -> dict:
    """Lo que vale hoy cada marcador {{clave}} de los HTML del sitio."""
    cifras = {"reportes_ciudadanos": fmt(len(ctx["chatmap"]))}
    # El corte del corpus de titulares, para el `dateModified` del Dataset en
    # el <head> de noticias.html: va por marcador porque un <span data-gen> no
    # cabe dentro de un bloque JSON-LD. Si la corrida falta o no es una fecha,
    # la clave NO se emite y el build revienta con «marcador sin valor»:
    # escribir "None" fecharía el corpus en la nada (M10).
    corte = _solo_fecha(ctx.get("noticias_generado"))
    if corte:
        cifras["noticias_corte"] = corte
    return cifras


def sustituir_cifras(destino: Path, ctx: dict) -> dict:
    """Escribe en `dist/` las cifras marcadas con {{clave}}.

    Un marcador sin valor **rompe el build a propósito**: no es una fuente que
    falla (R13), es un error de programación, y publicar «{{reportes_ciudadanos}}»
    en la etiqueta que ve quien comparte el enlace es peor que no publicar."""
    cifras, hechas = cifras_del_dia(ctx), {}
    # todo el artefacto, también las fichas municipales dos niveles abajo: un
    # marcador que se cuele en una plantilla no puede publicarse crudo
    for pagina in sorted(destino.rglob("*.html")):
        html = pagina.read_text(encoding="utf-8")
        claves = set(re.findall(r"\{\{(\w+)\}\}", html))
        if not claves:
            continue
        desconocidas = claves - set(cifras)
        if desconocidas:
            raise KeyError(f"{pagina.name}: marcador sin valor {sorted(desconocidas)}"
                           f" — añádelo a cifras_del_dia() o quítalo del HTML")
        for clave in claves:
            html = html.replace("{{" + clave + "}}", cifras[clave])
        pagina.write_text(html, encoding="utf-8")
        hechas[str(pagina.relative_to(destino))] = sorted(claves)
    return hechas


if __name__ == "__main__":
    import sys
    salida = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    res = run(salida)
    print(f"fichas municipales: {res['fichas']} escritas, {res['omitidas']} sin señal")
    for pagina, activa in escribir_piezas_compartidas(salida).items():
        print(f"identidad, barra y pie en {pagina}: enlace activo «{activa}»")
    ctx = contexto()
    for nombre, piezas in inyectar_prerenderizado(salida, ctx).items():
        print(f"prerenderizado: {nombre} con {piezas} pieza(s)")
    for pagina, claves in sustituir_cifras(salida, ctx).items():
        print(f"cifras del día en {pagina}: {', '.join(claves)}")
