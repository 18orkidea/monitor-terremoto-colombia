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
# mismo locale es-CO y el mismo criterio de fechas que las fichas
from render_html import (asigna_a_municipios, fecha_larga, fmt, slug,  # noqa: E402
                         _leer)

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"
DOMINIO = "https://datosdelterremoto.org"

# páginas fijas del sitio, con su prioridad y cadencia declarada
PAGINAS = [
    ("/", "daily", "1.0"),
    ("/municipios.html", "daily", "0.9"),
    ("/rud.html", "daily", "0.8"),
    ("/balances.html", "daily", "0.8"),
    ("/noticias.html", "daily", "0.7"),
    # No cambia a diario: es la página de cómo se construye el monitor, no de
    # lo que publicó hoy. Declarar «daily» donde el texto es estable gasta
    # rastreo en una página que casi nunca ha cambiado.
    ("/referencia.html", "monthly", "0.6"),
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
    for ficha in sorted((destino / "departamento").glob("*/index.html")):
        urls.append((f"{DOMINIO}/departamento/{ficha.parent.name}/", "daily", "0.6"))
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

    L = ["# Monitor de brechas — Terremoto de Colombia 2026: datos por municipio",
         "",
         f"Actualizado el {fecha_larga(generado)}. Licencia CC BY 4.0. Fuente de cada cifra",
         "al final.",
         "",
         "Terremoto de magnitud 7,4 del 10 de agosto de 2026, con epicentro en San José del",
         "Palmar (Chocó, Colombia). Este archivo recoge, municipio a municipio, lo que cada",
         "fuente sabe y lo que ninguna sabe.",
         "",
         "## Cómo leer estas cifras",
         "",
         "- El RUD (Registro Único de Damnificados), que lleva la Unidad Nacional para la",
         "  Gestión del Riesgo de Desastres (UNGRD), es un registro progresivo que cargan las",
         "  autoridades municipales y está sujeto a verificación posterior: mide inscripciones",
         "  tramitadas, no daño comprobado.",
         "- Que un municipio no aparezca en el RUD significa «sin registro aún», nunca",
         "  «sin daño».",
         "- Un municipio sin producto satelital de daño no ha sido evaluado desde el aire:",
         "  su ausencia de cifra satelital no es un cero.",
         "- La prensa nunca equivale a un balance oficial.",
         "- Siglas que se repiten abajo: DANE es el Departamento Administrativo Nacional de",
         "  Estadística, de donde salen las proyecciones de población; DIVIPOLA es la División",
         "  Político-Administrativa de Colombia, el código oficial de cada municipio; y DYFI",
         "  («Did You Feel It?») es el cuestionario con el que el Servicio Geológico de Estados",
         "  Unidos (USGS) mide cuánto sintió el sismo la población.",
         "",
         "## Municipios",
         ""]

    items = sorted(municipios["items"],
                   key=lambda m: (m.get("rud_personas") or 0), reverse=True)
    # misma atribución punto→municipio que usan las tablas y las fichas: una
    # sola forma de contar el daño de Copernicus en todo el sitio
    conteo_copernicus = asigna_a_municipios(
        (_leer("damage_points.geojson") or {}).get("features") or [],
        municipios["items"])
    for m in items:
        nombre, depto = m["municipio"], m["departamento"]
        partes = [f"### {nombre} ({depto})", f"Código DIVIPOLA {m['divipola']}. "
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
        # Los TRES satélites, y por EVIDENCIA, no por pertenencia a una zona.
        # Mientras esto miró una sola fuente, este fichero —el que leen los
        # sistemas de IA— afirmaba que «ningún producto satelital» había mirado
        # Anserma, Manizales y Viterbo, los municipios que entonces aportaban
        # los 385 edificios de UNOSAT (hoy son 548 y son cuatro, con Zarzal). Y mientras Copernicus se resolvió por AOI, lo
        # afirmaba también de Yumbo, que tiene 3 edificios clasificados con
        # coordenada dentro pero ninguna AOI encima: la ficha del municipio y
        # la tabla de portada decían 3, y este fichero decía que ninguno.
        # La pregunta correcta no es «¿está en una zona?» sino «¿hay evidencia
        # satelital dentro?», que es la que usan las tablas.
        # Con ICube-SERTIT el episodio se repetiría en Roldanillo y La Virginia,
        # que no ha mirado ningún otro servicio: este fichero diría de los dos
        # que nadie evaluó sus edificios mientras la ficha publica 77 y 49.
        satelital = []
        n_cop = conteo_copernicus.get(nombre, 0)
        if n_cop:
            satelital.append(
                f"{fmt(n_cop)} edificios con daño clasificado uno a uno por el servicio "
                f"de emergencias de Copernicus (activación EMSR916), con coordenada dentro "
                f"del municipio" + ("" if m.get("en_aoi_copernicus")
                                    else ", aunque el municipio queda fuera de las zonas "
                                         "que Copernicus delimitó para el análisis"))
        elif m.get("en_aoi_copernicus"):
            satelital.append("dentro de una zona con mapa de daños publicado por el "
                             "servicio de emergencias de Copernicus (activación EMSR916)")
        if m.get("unosat_edificios") is not None:
            satelital.append(
                f"{fmt(m['unosat_edificios'])} edificios evaluados uno a uno por "
                f"UNITAR-UNOSAT, el centro satelital de la ONU, de los que "
                f"{fmt(m['unosat_observados'])} son daño observado y el resto, «daño "
                f"posible»; ninguno validado en campo")
        if m.get("sertit_edificios") is not None:
            # «ventana», no «recorte del municipio»: lo que miran es un recuadro
            # propio, que en La Virginia es más grande que el municipio entero.
            ventana = (f", sobre una ventana de {fmt(m['sertit_area_km2'], 2)} km²"
                       if m.get("sertit_area_km2") is not None else "")
            # Sin cifra de destruidos no se escribe un cero ni un guion en prosa:
            # simplemente no se afirma nada sobre ellos (R3).
            destruidos = (f", de los que da por destruidos {fmt(m['sertit_destruidos'])}"
                          if m.get("sertit_destruidos") is not None else "")
            satelital.append(
                f"{fmt(m['sertit_edificios'])} edificios evaluados por ICube-SERTIT "
                f"(Universidad de Estrasburgo) para la activación 1048 de la Carta "
                f"Internacional del Espacio y las Grandes Catástrofes{ventana}"
                f"{destruidos}; fotointerpretación sobre imagen Pléiades, sin validar "
                f"en campo (© ICube-SERTIT 2026)")
        # Cada servicio mira su propio recorte: dos cifras sobre el mismo
        # municipio son dos ventanas distintas, no dos versiones de la misma
        # medida. Quien lea esto sin la advertencia las sumaría.
        if len(satelital) > 1:
            satelital.append(
                "cada servicio cartografió su propio recorte del municipio, así que sus "
                "cifras no son versiones de una misma medición ni se suman: para el total "
                "de edificios únicos, contando una sola vez los que vieron dos servicios, "
                f"está el bloque «satelital» de {DOMINIO}/data/public/monitor.json")
        partes.append("Cobertura satelital: " + "; ".join(satelital) + "."
                      if satelital else
                      "Cobertura satelital: ningún producto satelital de daño ha reportado "
                      "daños en el municipio.")
        if m.get("dyfi_max_cdi"):
            partes.append(f"Intensidad percibida (cuestionario DYFI del USGS): hasta "
                          f"{fmt(m['dyfi_max_cdi'], 1)} en la escala de Mercalli modificada, "
                          f"con {fmt(m['dyfi_respuestas'])} respuestas ciudadanas.")
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
          "- Servicio de gestión de emergencias de Copernicus (EMS), activación EMSR916",
          "- UNITAR-UNOSAT, centro satelital de la ONU: https://unosat.org/products/4253",
          "- ICube-SERTIT (Universidad de Estrasburgo), Carta Internacional del Espacio y",
          "  las Grandes Catástrofes, activación 1048: © ICube-SERTIT 2026, uso no comercial",
          "- Servicio Geológico de Estados Unidos (USGS): mapa de intensidad ShakeMap y",
          "  cuestionario ciudadano DYFI («Did You Feel It?», ¿lo sintió usted?)",
          "- ChatMap · OpenStreetMap Colombia (reportes ciudadanos)",
          "- Canales de prensa abiertos que sigue el propio monitor",
          "",
          f"Datos completos: {DOMINIO}/data/public/monitor.json",
          "Código y copias archivadas: https://github.com/18orkidea/monitor-terremoto-colombia",
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
