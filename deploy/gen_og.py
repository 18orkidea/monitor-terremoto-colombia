"""Genera las imágenes Open Graph (1200x630) de las tres páginas.

Se ejecuta en el deploy (pages.yml) para que las cifras estén al día; los PNG
también se versionan como respaldo. Único requisito extra: Pillow.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OG = ROOT / "site" / "og"
W, H = 1200, 630

# paleta (modo oscuro del sitio)
BG = "#101418"
INK = "#ffffff"
INK2 = "#c3c2b7"
MUTED = "#898781"
S1, S3, S7 = "#3987e5", "#199e70", "#9085e9"
CRIT, WARN = "#e66767", "#fab219"


def font(size: int, bold: bool = False):
    candidates = [
        # macOS
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux (runners de GitHub)
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def base(titulo: str, subtitulo: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # barra de acento superior con los colores de las series
    for i, c in enumerate([CRIT, WARN, S1, S3, S7]):
        d.rectangle([i * W / 5, 0, (i + 1) * W / 5, 10], fill=c)
    d.text((70, 60), "MONITOR DE BRECHAS · TERREMOTO DE COLOMBIA M7.4",
           font=font(28), fill=MUTED)
    d.text((70, 110), titulo, font=font(64, bold=True), fill=INK)
    d.text((70, 200), subtitulo, font=font(30), fill=INK2)
    # pie
    d.text((70, H - 70), "brechas.orkidea.eu", font=font(30, bold=True), fill=S1)
    d.text((W - 70, H - 70), "datos abiertos · actualización diaria",
           font=font(24), fill=MUTED, anchor="ra")
    return img, d


def stats_row(d, stats: list[tuple[str, str, str]], y: int = 300):
    x = 70
    for valor, etiqueta, color in stats:
        d.text((x, y), valor, font=font(72, bold=True), fill=color)
        d.text((x, y + 90), etiqueta, font=font(26), fill=INK2)
        x += max(d.textlength(valor, font=font(72, bold=True)),
                 d.textlength(etiqueta, font=font(26))) + 70


def fmt(n):
    if n is None:
        return "—"
    return f"{n:,.0f}".replace(",", ".")


def main():
    OG.mkdir(parents=True, exist_ok=True)
    mon = json.loads((ROOT / "data/public/monitor.json").read_text())
    noticias = json.loads((ROOT / "data/public/noticias.json").read_text())

    # -- portada: el cruce
    # OJO: esta regla vive en DOS superficies —aquí y en site/ui.js, que pinta
    # la tarjeta de la portada—. Si tocas una, mira la otra.
    # Las dos miradas satelitales se suman porque miran municipios distintos;
    # la ingesta lo certifica y, si algún día se pisaran, esa lista no vendría
    # vacía y la portada volvería sola a contar solo Copernicus.
    uno = mon.get("unosat") or {}
    cop = sum(a["resumen"].get("edificios_afectados") or 0 for a in mon["aois"])
    suma = not uno.get("municipios_tambien_en_aoi_copernicus")
    n_uno = (uno.get("edificios") or 0) if suma else 0
    edif = cop + n_uno
    # Es la superficie más compartida del monitor y la única sin sitio para el
    # matiz: el pie lo lleva. Un total de dos fuentes que no dice de cuáles ni
    # cuántos son hipótesis se comparte solo, y ya no se puede matizar.
    pie = ([f"{fmt(cop)} de Copernicus EMSR916 + {fmt(n_uno)} de UNITAR-UNOSAT.",
            f"De los de UNOSAT, {fmt(uno.get('posibles') or 0)} son solo «daño posible», "
            f"sin validar en campo."]
           if n_uno else
           ["Clasificados uno a uno por el servicio de emergencias de Copernicus (EMSR916)."])
    img, d = base("El mapa que cruza satélite,",
                  "calle y prensa — y mide lo que las fuentes oficiales aún no publican")
    d.text((70, 245), "", font=font(30), fill=INK2)
    stats_row(d, [
        (fmt(edif), "edificios con daño (satélite)", CRIT),
        (fmt(mon["citizen"]["chatmap_total"]), "reportes ciudadanos", S7),
        (f"{mon.get('exposicion', {}).get('pct_cubierta', 0):.1f} %".replace(".", ","),
         "población expuesta con mapeo", WARN),
    ])
    for i, linea in enumerate(pie):
        d.text((70, 440 + i * 32), linea, font=font(24), fill=MUTED)
    img.save(OG / "portada.png", optimize=True)

    # -- titulares
    img, d = base("Todos los titulares,", "emparejados por zona afectada — feeds abiertos a la comunidad")
    por_origen = {}
    for n in noticias["items"]:
        por_origen[n["origen"]] = por_origen.get(n["origen"], 0) + 1
    stats_row(d, [
        (fmt(noticias["total"]), "titulares del evento", S1),
        (fmt(len(por_origen)), "fuentes de feeds", S3),
        (fmt(por_origen.get("gdacs-emm", 0)), "rescatados del feed purgado", CRIT),
    ])
    img.save(OG / "titulares.png", optimize=True)

    # -- balances: el consolidado vigente, que alerts.py publica siempre. Antes
    # se leía de la alerta del día, así que la imagen se quedaba sin cifras los
    # días en que no llegaba ningún balance nuevo. La regla es la misma que la
    # de la web: una implementación, tres consumidores.
    cifras = {}
    try:
        alerts = json.loads((ROOT / "data/public/alerts.json").read_text())
        cifras = (alerts.get("balance_consolidado") or {}).get("cifras") or {}
        if not cifras:
            for a in alerts.get("alertas", []):
                if a.get("tipo") == "balance_en_medios":
                    cifras = a.get("cifras") or {}
    except FileNotFoundError:
        pass
    img, d = base("Balances en medios", "máximo informado por medios que citan fuentes oficiales (UNGRD, SGC)")
    stats_row(d, [
        (fmt(cifras.get("fallecidos")), "fallecidos", CRIT),
        (fmt(cifras.get("desaparecidos")), "desaparecidos", WARN),
        (fmt(cifras.get("familias_afectadas")), "familias afectadas", S1),
    ])
    d.text((70, 430), "No es el balance oficial: es lo que la prensa publica citándolo.",
           font=font(24), fill=MUTED)
    img.save(OG / "balances.png", optimize=True)
    print(f"OG generadas en {OG}: portada, titulares, balances")


if __name__ == "__main__":
    main()
