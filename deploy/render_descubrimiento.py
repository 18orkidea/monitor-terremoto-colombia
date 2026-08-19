"""Genera lo que hace que el sitio se encuentre: sitemap y llms-full.txt.

Va aparte de `render_html.py` porque no produce páginas: produce los índices que
leen buscadores y sistemas de IA. El sitemap se construye a partir de lo que
realmente hay en `dist/`, no de una lista escrita a mano — así nunca anuncia una
página que no existe ni omite una que sí.

Solo stdlib (R14).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_html import fmt, slug          # noqa: E402  (mismo locale es-CO que las fichas)

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"
DOMINIO = "https://brechas.orkidea.eu"

# páginas fijas del sitio, con su prioridad y cadencia declarada
PAGINAS = [
    ("/", "daily", "1.0"),
    ("/municipios.html", "daily", "0.9"),
    ("/rud.html", "daily", "0.8"),
    ("/balances.html", "daily", "0.8"),
    ("/noticias.html", "daily", "0.7"),
]


def _fecha_datos() -> str:
    """La fecha del dato, no la del build: si la corrida no trajo nada nuevo,
    anunciar un `lastmod` fresco sería mentirle al buscador."""
    try:
        return json.loads((PUBLIC / "monitor.json").read_text())["generado"][:10]
    except Exception:
        return ""


def sitemap(destino: Path) -> int:
    hoy = _fecha_datos()
    urls = [(DOMINIO + ruta, cad, pri) for ruta, cad, pri in PAGINAS]
    for ficha in sorted((destino / "municipio").glob("*/index.html")):
        urls.append((f"{DOMINIO}/municipio/{ficha.parent.name}/", "daily", "0.6"))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, cad, pri in urls:
        out.append(f"  <url><loc>{loc}</loc><changefreq>{cad}</changefreq>"
                   f"<lastmod>{hoy}</lastmod><priority>{pri}</priority></url>")
    out.append("</urlset>")
    (destino / "sitemap.xml").write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(urls)


def llms_full(destino: Path) -> int:
    """Volcado en texto plano de la cifra municipal del día.

    `llms.txt` dice qué es el monitor; este dice qué sabe hoy. Los sistemas de IA
    no ejecutan JavaScript: si el dato no está escrito, para ellos no existe."""
    municipios = json.loads((PUBLIC / "municipios.json").read_text())
    rud = json.loads((PUBLIC / "rud.json").read_text())
    generado = municipios.get("generado", "")

    L = [f"# Monitor de brechas — Terremoto de Colombia 2026: datos por municipio",
         "",
         f"Actualizado: {generado}. Licencia CC BY 4.0. Fuente de cada cifra al final.",
         "",
         "Terremoto de magnitud 7,4 del 10 de agosto de 2026, con epicentro en San José del",
         "Palmar (Chocó, Colombia). Este archivo recoge, municipio a municipio, lo que cada",
         "fuente sabe y lo que ninguna sabe.",
         "",
         "## Cómo leer estas cifras",
         "",
         "- El RUD (Registro Único de Damnificados, de la UNGRD) es un registro progresivo",
         "  que cargan las autoridades municipales y está sujeto a verificación posterior:",
         "  mide inscripciones tramitadas, no daño comprobado.",
         "- Que un municipio no aparezca en el RUD significa «sin registro aún», nunca",
         "  «sin daño».",
         "- Un municipio sin producto satelital de daño no ha sido evaluado desde el aire:",
         "  su ausencia de cifra satelital no es un cero.",
         "- La prensa nunca equivale a un balance oficial.",
         "",
         "## Municipios",
         ""]

    items = sorted(municipios["items"],
                   key=lambda m: (m.get("rud_personas") or 0), reverse=True)
    for m in items:
        nombre, depto = m["municipio"], m["departamento"]
        partes = [f"### {nombre} ({depto})", f"DIVIPOLA {m['divipola']}. "
                  f"Población proyectada 2026 (DANE): {fmt(m['poblacion_2026'])} habitantes."]
        if m.get("rud_familias"):
            partes.append(
                f"RUD: {fmt(m['rud_familias'])} familias y {fmt(m['rud_personas'])} personas "
                f"inscritas como damnificadas ({fmt(m['tasa_rud_pct'], 2)}% de la población); "
                f"{fmt(m['rud_viv_destruidas'])} viviendas destruidas y "
                f"{fmt(m['rud_viv_averiadas'])} averiadas.")
        else:
            partes.append("RUD: sin inscripciones en la última captura. Sin registro aún "
                          "no significa sin daño.")
        partes.append("Cobertura satelital: dentro de una zona con producto de daño."
                      if m.get("en_aoi_copernicus") else
                      "Cobertura satelital: ningún producto satelital de daño ha reportado "
                      "daños en el municipio.")
        if m.get("dyfi_max_cdi"):
            partes.append(f"Intensidad percibida (DYFI/USGS): hasta {fmt(m['dyfi_max_cdi'], 1)} "
                          f"en escala de Mercalli modificada, con {fmt(m['dyfi_respuestas'])} "
                          f"respuestas ciudadanas.")
        else:
            partes.append("Intensidad percibida: sin respuestas al cuestionario DYFI del USGS.")
        if m.get("n_noticias"):
            partes.append(f"Prensa: {fmt(m['n_noticias'])} piezas recogidas por el monitor.")
        partes.append(f"Ficha completa: {DOMINIO}/municipio/{slug(nombre)}/")
        L.append(partes[0])                       # encabezado del municipio
        L.append(" ".join(partes[1:]))            # el resto, en prosa corrida
        L.append("")

    L += ["## Fuentes",
          "",
          "- RUD (Registro Único de Damnificados), UNGRD: https://rud.gestiondelriesgo.gov.co/",
          "- Proyecciones de población municipal 2026, DANE",
          "- Copernicus Emergency Management Service, activación EMSR916",
          "- USGS ShakeMap y DYFI («Did You Feel It?»)",
          "- ChatMap · OpenStreetMap Colombia (reportes ciudadanos)",
          "- Feeds abiertos de prensa del propio monitor",
          "",
          f"Datos completos: {DOMINIO}/data/public/monitor.json",
          f"Código y snapshots: https://github.com/18orkidea/monitor-terremoto-colombia",
          f"Serie diaria del RUD: {len(rud.get('detalle_diario', {}))} capturas archivadas.",
          ""]
    texto = "\n".join(L)
    (destino / "llms-full.txt").write_text(texto, encoding="utf-8")
    return len(items)


if __name__ == "__main__":
    import sys
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    n_urls = sitemap(destino)
    n_mun = llms_full(destino)
    print(f"descubrimiento: sitemap con {n_urls} URLs · llms-full.txt con {n_mun} municipios")
