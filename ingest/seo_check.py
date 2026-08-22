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
MAX_KB_PAGINA = 400          # por encima, los rastreadores truncan
MIN_FICHAS = 50
SCRIPTS_FICHA = {"/ui.js", "/municipio.js"}


def _texto(html: str) -> str:
    limpio = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", limpio)


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
        filas = len(re.findall(r"<tr[ >]", html)) + len(re.findall(r"<li>", html))
        kb = len(html.encode()) / 1024
        datos[pagina] = {"palabras": palabras, "filas": filas, "kb": round(kb)}

        if palabras < minimo["palabras"]:
            fallos.append(f"{pagina}: {palabras} palabras servidas, mínimo {minimo['palabras']}")
        if filas < minimo["filas"]:
            fallos.append(f"{pagina}: {filas} filas en el HTML, mínimo {minimo['filas']}"
                          " — ¿se ha roto el prerenderizado?")
        if kb > MAX_KB_PAGINA:
            avisos.append(f"{pagina}: {kb:.0f} KB, por encima de {MAX_KB_PAGINA}")

        # un contenedor marcado y vacío es exactamente la regresión que se vigila.
        # No solo tablas y listas: la banda de brechas de la portada es una
        # <section> de prosa, y es el texto más citable del sitio.
        for m in re.finditer(
                r'<(tbody|ul|section)([^>]*\bdata-gen="([^"]+)")[^>]*>(.*?)</\1>',
                html, re.S):
            if not m.group(4).strip():
                fallos.append(f"{pagina}: el contenedor «{m.group(3)}» quedó vacío")

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
