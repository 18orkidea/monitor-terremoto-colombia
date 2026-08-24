"""Verifica que lo publicado se puede encontrar y citar.

Una regresión del prerenderizado es invisible a simple vista: la página se ve
perfecta en el navegador —el JavaScript la rellena— y llega vacía a quien no lo
ejecuta, que es todo rastreador de sistemas de IA. Este módulo mira el artefacto
construido, no el navegador, y avisa (R11) en vez de romper.

Se ejecuta sobre `dist/`, después de `deploy/build_dist.sh`.

Solo stdlib (R14).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mínimos por página: no son objetivos de estilo, son el umbral por debajo del
# cual la página deja de decir nada a quien la lee sin ejecutar JavaScript.
MINIMOS = {
    "index.html": {"palabras": 800, "filas": 10},
    "municipios.html": {"palabras": 800, "filas": 50},
    "rud.html": {"palabras": 600, "filas": 50},
    "balances.html": {"palabras": 600, "filas": 10},
    "noticias.html": {"palabras": 1000, "filas": 100},
}

# Suelo de prosa propia: lo que cada página aporta descontando su tabla, la
# barra y el pie (ver `prosa_propia`). **Es el contrato «ninguna baja»**, y hace
# el trabajo que los MINIMOS de arriba no pueden hacer: son absolutos y una
# tabla de 208 filas los cuadruplica ella sola, así que `rud.html` podría perder
# su introducción entera con el build en verde.
#
# **El suelo lleva margen a propósito, y no es holgura para descuidarse.** Buena
# parte de esta prosa es CONDICIONAL: existe solo si el dato del día la trae —la
# disputa entre medios (~55 palabras), lo descartado (~72), la captura elegida
# (~29), el aviso de silencio de prensa de municipios (~170)—. Un día sin
# disputa no ha perdido ni una palabra escrita, y un día en que la prensa cubre
# por fin a los municipios mudos es una BUENA noticia: sin margen, el guardián
# se dispararía precisamente ahí, y la salida cómoda sería bajar el suelo, que
# es como muere un guardián. Lo que vigila es la regresión de código —una pieza
# que deja de escribirse, una sección que se cae del build—, no el vaivén del
# dato.
#
# Medido el 24-ago-2026 sobre `dist/` al cerrar la fase 4. Se sube cuando una
# fase deja la página mejor, y se anota aquí con su fecha; **no se baja para que
# pase un build** sin entrada en `docs/DECISIONES.md`.
MARGEN_CONDICIONAL = {"balances.html": 160, "municipios.html": 200}
PROSA_MINIMA = {
    "index.html": 2727,        # la portada la reordena la fase 6
    "municipios.html": 507,    # fase 4: 707 medidas − 200 de aviso condicional
    "rud.html": 578,           # fase 3
    "balances.html": 1404,     # fase 4: 1.564 medidas − 160 condicionales
    "noticias.html": 827,      # fase 4; su prosa no depende del dato del día
}
MAX_KB_PAGINA = 400          # por encima, los rastreadores truncan

# «Riosucio (Caldas) (Caldas)»: el departamento escrito dos veces porque se
# confundió la CLAVE del diccionario —que desambigua los homónimos metiendo el
# departamento entre paréntesis— con el TOPÓNIMO que lee una persona. Estuvo
# publicado en cinco fichas hasta el 23-ago-2026.
#
# Vigila SOLO esa duplicación. NO vigila la longitud del título: que 77 de 208
# pasen de 60 caracteres es una laguna conocida, fechada y decidida
# (docs/LIMITACIONES.md), y un guardián que falla desde el primer día contra
# una decisión tomada es ruido, no vigilancia.
DEPTO_DUPLICADO = re.compile(r"\(([^()]{2,40})\)(?: \(\1\)|, \1\b)")
MIN_FICHAS = 50
SCRIPTS_FICHA = {"/ui.js", "/municipio.js"}

# La barra y el pie no llevan `data-gen` —no son datos del día, son la
# navegación del sitio—, así que el chequeo de contenedores marcados no los ve.
# Hasta el 23-ago-2026 llegaban vacíos a las cinco páginas grandes y los
# rellenaba `site/common.js` en el navegador: quien no ejecuta JavaScript veía
# una página sin un solo enlace interno y sin el pie que dice de qué va esto.
# Es **fallo y no aviso**, por el mismo criterio que un contenedor `data-gen`
# vacío: es determinista, no depende de ninguna fuente que pueda fallar (R13) y
# deja la página sin la única red de enlaces que la conecta con las otras 212.
CONTENEDORES_DEL_SITIO = (
    ("la barra de navegación", "vacía",
     re.compile(r'<nav id="site-nav"[^>]*>\s*</nav>'), "nav-links"),
    ("el pie de página", "vacío",
     re.compile(r'<div id="site-footer"[^>]*>\s*</div>'), "sf-cols"),
)


def _entre(patron: str, html: str) -> str | None:
    """El primer grupo de `patron`, o None si no aparece."""
    hallado = re.search(patron, html, re.S)
    return hallado.group(1) if hallado else None


def _texto(html: str) -> str:
    limpio = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", limpio)


def prosa_propia(html: str) -> int:
    """Palabras que esta página aporta, sin lo que aportan la tabla y el marco.

    El total de una página con 208 filas no vigila nada: la tabla sola cuadruplica
    el mínimo, así que `rud.html` podía perder su introducción entera con el build
    en verde. Y barra y pie son **216 palabras idénticas en las 213 páginas**:
    contarlas le regala a cada una un colchón que oculta justo la pérdida que el
    suelo vigila. Se descuentan los tres.

    Nace de una cicatriz de método (M4): la línea base del rediseño se llevaba en
    un documento, envejeció en una tarde y ninguna definición razonable
    reproducía sus cifras. Un suelo se mide con un medidor que esté en el
    repositorio, o no es verificable por nadie.
    """
    limpio = re.sub(r"<(script|style|svg).*?</\1>", " ", html, flags=re.S)
    # El cromo se descuenta POR SU MARCA, no por su etiqueta: `pie_estatico()`
    # emite `<div id="site-footer">`, así que un patrón `<footer>` no casaba
    # nada y colaba las 193 palabras del pie en las cinco páginas — justo el
    # colchón que este medidor existe para quitar, y encima uno que se mueve a
    # la vez en las cinco cada vez que se edita el pie.
    #
    # Y `<header>` NO se descuenta: en este sitio no es cromo, es el encabezado
    # propio de la página —su `<h1>`, su bajada y su sello, 51 palabras en
    # balances—, o sea contenido publicado que el suelo tiene que vigilar.
    for patron in (r"<tbody\b.*?</tbody>", r'<ul id="lista".*?</ul>',
                   r'<nav id="site-nav".*?</nav>',
                   r'<div id="site-footer".*?</div>\s*</div>'):
        limpio = re.sub(patron, " ", limpio, flags=re.S | re.I)
    return len(_texto(limpio).split())


def _scripts_ficha_validos(html: str) -> bool:
    """Solo admite la mejora progresiva del mapa, nunca datos escritos por JS.

    Las cifras, la prosa y el SVG deben seguir en el documento. Los dos scripts
    permitidos son el constructor compartido de globos y el controlador que
    descarga Leaflet después de activar la pestaña. Un tercero, un inline o una
    ficha sin su contenido estático vuelven a ser una regresión SEO.
    """
    ejecutables = []
    for atributos in re.findall(r"<script\b([^>]*)>", html):
        if "application/ld+json" in atributos:
            continue
        src = re.search(r'\bsrc=["\']([^"\']+)', atributos)
        if not src:
            return False
        ruta = src.group(1).split("?", 1)[0]
        if ruta not in SCRIPTS_FICHA:
            return False
        ejecutables.append(ruta)
    if not ejecutables:
        return True
    return (set(ejecutables) == SCRIPTS_FICHA
            and 'class="mapa-estatico"' in html
            and 'data-evidencia="/data/public/municipios/' in html)


def revisar(dist: Path) -> dict:
    fallos, avisos, datos = [], [], {}

    for pagina, minimo in MINIMOS.items():
        f = dist / pagina
        if not f.exists():
            fallos.append(f"{pagina}: no existe en el artefacto")
            continue
        html = f.read_text(encoding="utf-8")
        palabras = len(_texto(html).split())
        propia = prosa_propia(html)
        filas = len(re.findall(r"<tr[ >]", html)) + len(re.findall(r"<li>", html))
        kb = len(html.encode()) / 1024
        datos[pagina] = {"palabras": palabras, "prosa_propia": propia,
                         "filas": filas, "kb": round(kb)}

        if palabras < minimo["palabras"]:
            fallos.append(f"{pagina}: {palabras} palabras servidas, mínimo {minimo['palabras']}")
        suelo = PROSA_MINIMA.get(pagina)
        if suelo is not None and propia < suelo:
            fallos.append(
                f"{pagina}: {propia} palabras de prosa propia, suelo {suelo} "
                f"(faltan {suelo - propia}). Es contenido publicado que "
                "desaparece: se recupera, o se baja el suelo a mano con su "
                "porqué en docs/DECISIONES.md")
        if filas < minimo["filas"]:
            fallos.append(f"{pagina}: {filas} filas en el HTML, mínimo {minimo['filas']}"
                          " — ¿se ha roto el prerenderizado?")
        if kb > MAX_KB_PAGINA:
            avisos.append(f"{pagina}: {kb:.0f} KB, por encima de {MAX_KB_PAGINA}")

        # un contenedor marcado y vacío es exactamente la regresión que se vigila:
        # una tabla, una lista, la cifra escrita dentro de un párrafo o la banda
        # de brechas de la portada, que es una <section> de prosa entera
        for m in re.finditer(
                r'<(tbody|ul|span|section)([^>]*\bdata-gen="([^"]+)")[^>]*>(.*?)</\1>',
                html, re.S):
            if not m.group(4).strip():
                fallos.append(f"{pagina}: el contenedor «{m.group(3)}» quedó vacío")

        # la barra y el pie, que no llevan data-gen y por eso se les mira aparte
        for etiqueta, adjetivo, vacio, dentro in CONTENEDORES_DEL_SITIO:
            if vacio.search(html):
                fallos.append(f"{pagina}: {etiqueta} llegó {adjetivo} al HTML servido"
                              " — ¿volvió a escribirlo el JavaScript?")
            elif dentro not in html:
                fallos.append(f"{pagina}: no se encuentra {etiqueta}")

        # un marcador {{clave}} sin sustituir es una cifra que se iba a publicar
        # cruda en el HTML servido; el build debería haber roto antes
        for marcador in set(re.findall(r"\{\{\w+\}\}", html)):
            fallos.append(f"{pagina}: el marcador «{marcador}» llegó sin sustituir")

        if "<link rel=\"canonical\"" not in html:
            fallos.append(f"{pagina}: sin canonical")
        # R3 en el HTML servido: un cero donde el dato no existe
        if re.search(r'<td class="num">\s*0,00\s*%?</td>', html):
            avisos.append(f"{pagina}: hay celdas con «0,00» — ¿un dato ausente convertido en cero?")

    fichas = sorted((dist / "municipio").glob("*/index.html"))
    datos["fichas"] = len(fichas)
    if len(fichas) < MIN_FICHAS:
        fallos.append(f"fichas municipales: {len(fichas)}, mínimo {MIN_FICHAS}")
    for ficha in fichas:
        html = ficha.read_text(encoding="utf-8")
        if not _scripts_ficha_validos(html):
            fallos.append(f"{ficha.parent.name}: la ficha lleva JavaScript ejecutable inesperado")
            break
        if re.search(r"\(R\d+\)", _texto(html)):
            avisos.append(f"{ficha.parent.name}: cita códigos internos de reglas")
            break


    # Bucle propio, y no dentro del anterior: aquel corta con `break` en cuanto
    # ve un script inesperado o una cita de regla, para no repetir el mismo
    # aviso 208 veces. Colgado de él, este chequeo dejaba de mirar las 207
    # fichas restantes en cuanto otra cosa saltara primero.
    for ficha in fichas:
        html = ficha.read_text(encoding="utf-8")
        # El documento entero, no solo los metadatos: el fallo vivía también en
        # el JSON-LD, en las migas y en el párrafo destacado —el que citan los
        # buscadores—, y una comprobación limitada al <title> los dejaba pasar.
        for etiqueta, texto in (("título", _entre(r"<title>(.*?)</title>", html)),
                                ("H1", _entre(r"<h1[^>]*>(.*?)</h1>", html)),
                                ("description",
                                 _entre(r'<meta name="description" content="([^"]*)"', html)),
                                ("documento", html)):
            hallado = DEPTO_DUPLICADO.search(texto or "")
            if hallado:
                fallos.append(f"{ficha.parent.name}: el {etiqueta} repite el departamento "
                              f"«{hallado.group(0)}» — es la clave del diccionario "
                              f"usada como topónimo")
                break

    # el sitemap no puede prometer lo que no existe
    sm = dist / "sitemap.xml"
    if not sm.exists():
        fallos.append("sitemap.xml: no existe")
    else:
        urls = re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
        datos["urls_sitemap"] = len(urls)
        for u in urls:
            ruta = u.split("datosdelterremoto.org", 1)[-1]
            destino = dist / (ruta.lstrip("/") or "index.html")
            if destino.is_dir():
                destino = destino / "index.html"
            if not destino.exists():
                fallos.append(f"sitemap: anuncia {ruta} y no existe")
        if len(urls) < MIN_FICHAS:
            fallos.append(f"sitemap: solo {len(urls)} URLs")

    for fichero, obligado in (("robots.txt", "GPTBot"), ("llms.txt", "brechas"),
                              ("llms-full.txt", "registro progresivo")):
        f = dist / fichero
        if not f.exists():
            fallos.append(f"{fichero}: no existe")
        elif obligado not in f.read_text(encoding="utf-8"):
            avisos.append(f"{fichero}: falta «{obligado}»")

    return {"fallos": fallos, "avisos": avisos, "datos": datos}


def run(dist: Path | None = None) -> dict:
    res = revisar(dist or ROOT / "dist")
    for f in res["fallos"]:
        print(f"::error::seo_check: {f}")
    for a in res["avisos"]:
        print(f"::warning::seo_check: {a}")
    return res


if __name__ == "__main__":
    r = run(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(json.dumps(r["datos"], indent=1, ensure_ascii=False))
    sys.exit(1 if r["fallos"] else 0)
