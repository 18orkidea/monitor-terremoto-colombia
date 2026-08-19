"""Tests de SUPUESTOS (online): los contratos externos sobre los que se
construyó el proyecto. Si uno falla, no es un bug del código — es que el mundo
cambió y hay que revisar la fuente correspondiente.

Saltar con: SKIP_ONLINE=1 python -m unittest tests/test_supuestos_api.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))

from common import NOTA_SONDA, fetch_json

ONLINE = os.environ.get("SKIP_ONLINE") != "1"
COP = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosCopernicus(unittest.TestCase):
    def test_code_es_obligatorio(self):
        st, d = fetch_json(COP, note=NOTA_SONDA)
        self.assertTrue(not d or not d.get("results"),
                        "la API ahora lista sin code: ¡mejorar el ingestor!")

    def test_emsr916_existe_con_aois(self):
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        r = d["results"][0]
        self.assertEqual(r["code"], "EMSR916")
        self.assertGreaterEqual(len(r["aois"]), 7)
        self.assertIn("Colombia", [c["name"] for c in r["countries"]])

    def test_na_sigue_presente_en_stats(self):
        """El parser tolera 'NA'; verificar que el supuesto sigue vivo."""
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        raws = []
        for aoi in d["results"][0]["aois"]:
            for p in aoi.get("products") or []:
                for cat in (p.get("stats") or {}).values():
                    for v in cat.values():
                        raws += [v.get("total"), v.get("affected")]
        self.assertIn("NA", [str(x) for x in raws],
                      "ya no hay 'NA' en stats: revisar si cambió el esquema")

    def test_tipos_fuera_de_spec(self):
        """La spec OpenAPI lista FEP/REF/DEL/GRA; la realidad incluye GRM."""
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        tipos = {p["type"] for a in d["results"][0]["aois"]
                 for p in a.get("products") or []}
        self.assertTrue(tipos - {"FEP", "REF", "DEL", "GRA"} or tipos,
                        "el parser debe seguir siendo tolerante a tipos nuevos")

    def test_hueco_documentado(self):
        """EMSR700 falla entre vecinos válidos: hueco puntual, no error."""
        st, d = fetch_json(COP, {"code": "EMSR700"}, note=NOTA_SONDA)
        self.assertFalse((d or {}).get("results"),
                         "EMSR700 ahora existe: retirar el supuesto del hueco")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosOficiales(unittest.TestCase):
    def test_socrata_sigue_parado_en_2022(self):
        st, d = fetch_json("https://www.datos.gov.co/resource/wwkg-r6te.json",
                           {"$select": "max(fecha)"}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        maxf = d[0].get("max_fecha", "")
        # si esto falla, ¡buena noticia! — el monitor debe celebrarlo, no ocultarlo
        self.assertLessEqual(maxf[:4], "2026",
                             "fecha imposible: revisar parseo")
        if maxf[:10] > "2022-12-31":
            print(f"\n*** SUPUESTO ROTO (bien): Socrata ya llega a {maxf} ***")

    def test_arcgis_ungrd_responde_con_edan(self):
        L = ("https://services2.arcgis.com/YVLx8xYoDXKccDfJ/arcgis/rest/services/"
             "REGISTRO_DE_EMERGENCIAS_EN_COLOMBIA/FeatureServer/0/query")
        st, d = fetch_json(L, {"where": "1=1", "f": "json", "resultRecordCount": 1,
                               "outFields": "MUERTOS,VIV_DESTRU,MUNICIPIO"},
                          note=NOTA_SONDA)
        self.assertEqual(st, 200)
        at = d["features"][0]["attributes"]
        for campo in ("MUERTOS", "VIV_DESTRU", "MUNICIPIO"):
            self.assertIn(campo, at, f"campo EDAN {campo} desapareció")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosRUD(unittest.TestCase):
    """El RUD es un endpoint interno no documentado: si cambia, avisar."""

    def test_rud_responde_con_esquema(self):
        st, d = fetch_json(
            "https://rud.gestiondelriesgo.gov.co/home/json.php?temp=2026T",
            note=NOTA_SONDA)
        if st != 200:
            self.fail(f"RUD HTTP {st}: el endpoint cambió o cayó — revisar "
                      "ingest/sources/ungrd_rud.py y buscar el reemplazo")
        rows = d if isinstance(d, list) else (d or {}).get("data") or []
        self.assertTrue(rows, "RUD respondió vacío")
        for campo in ("departamento", "municipio", "fecha_evento", "familias"):
            self.assertIn(campo, rows[0], f"campo {campo} desapareció del RUD")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosFeeds(unittest.TestCase):
    def test_gdacs_emm_con_fechas(self):
        st, d = fetch_json("https://www.gdacs.org/gdacsapi/api/emm/getemmnewsbykey",
                           {"eventtype": "EQ", "eventid": "1557236"},
                           note=NOTA_SONDA)
        self.assertEqual(st, 200)
        if d:  # la ventana ~5 días puede vaciar el feed: eso es esperado
            self.assertIn("pubdate", d[0])
            self.assertIn("link", d[0])

    def test_chatmap_vivo_o_documentado(self):
        st, d = fetch_json("https://chatmap.hotosm.org/api/v1/map/"
                           "89319bbb-a14a-4dfd-b9a1-c83b8b55785f",
                           note=NOTA_SONDA)
        if st != 200:
            self.skipTest(f"ChatMap cerró (HTTP {st}): activar canal Kobo, "
                          "los snapshots conservan lo capturado")
        self.assertIn("features", d)

    def test_dyfi_geojson_disponible(self):
        st, d = fetch_json("https://earthquake.usgs.gov/fdsnws/event/1/query",
                           {"eventid": "us6000tjl2", "format": "geojson"},
                          note=NOTA_SONDA)
        self.assertEqual(st, 200)
        self.assertIn("dyfi", d["properties"]["products"])

    def test_celdas_dyfi_siguen_siendo_poligonos(self):
        """El filtro de proximidad de 30 km (municipios.py::DYFI_RADIO_KM) mide
        desde el centro del polígono de la celda. Si el USGS pasara a puntos,
        _centro_celda devolvería None y el filtro se abriría EN SILENCIO,
        volviendo a publicar la celda «Balboa» de Panamá como intensidad de
        Balboa (Risaralda). Este supuesto avisa antes de que eso pase."""
        ruta = Path(__file__).parent.parent / "data" / "public" / "dyfi_cells.geojson"
        if not ruta.exists():
            self.skipTest("sin dyfi_cells.geojson: ejecutar run_daily primero")
        import json as _json
        tipos = {(f.get("geometry") or {}).get("type")
                 for f in _json.loads(ruta.read_text()).get("features", [])}
        self.assertEqual(tipos, {"Polygon"},
                         f"las celdas DYFI ya no son solo polígonos ({tipos}): "
                         "revisar el filtro de proximidad de municipios.py")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestoFuenteEnGoogleNews(unittest.TestCase):
    """El nombre del medio de la mitad del corpus depende de un contrato ajeno:
    que el RSS de Google News siga declarando `<source url="…">Nombre</source>`.

    Es el único sitio donde ese dato viaja: el `<link>` apunta al agregador y
    el sufijo del titular no es fiable. Si Google deja de emitir la etiqueta,
    las noticias nuevas entrarían con `medio_canonico` en NULL y el sitio
    dejaría de nombrar medios sin que nadie se entere — R11 existe para que
    eso avise en vez de degradarse en silencio. Romperse aquí no es un bug:
    es la señal de que hay que buscar el medio por otra vía."""

    URL = ("https://news.google.com/rss/search?q=%22terremoto%22+%22colombia%22"
           "&hl=es-CO&gl=CO&ceid=CO:es")

    def test_el_rss_sigue_declarando_source_con_url(self):
        import xml.etree.ElementTree as ET
        from common import fetch
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from community_feeds import parse_rss

        st, body = fetch(self.URL, note=NOTA_SONDA)
        self.assertEqual(st, 200, "Google News no responde: sonda inconcluyente")
        items = list(ET.fromstring(body).iter("item"))
        self.assertTrue(items, "el feed llegó sin items: revisar la búsqueda")
        con_fuente = [i for i in items if i.find("source") is not None]
        self.assertEqual(
            len(con_fuente), len(items),
            "Google News dejó de declarar <source> en algún item: el medio de "
            "las noticias nuevas se queda sin recuperar (ver docs/DECISIONES.md, "
            "2026-08-19) — hay que buscar otra vía antes de que el hueco crezca")
        self.assertTrue(
            all(i.find("source").get("url") for i in con_fuente),
            "<source> ya no trae atributo url: medio_dominio se queda en NULL")
        self.assertTrue(
            parse_rss(body)[0]["medio_canonico"],
            "el parseo del proyecto ya no extrae el medio de este feed")

    def test_el_enlace_sigue_sin_llevar_al_medio(self):
        """El reverso del supuesto anterior, y una buena noticia si se rompe:
        el día que el feed publique la URL del medio, `url` dejará de apuntar
        al agregador y la limitación documentada desaparecerá."""
        from common import fetch
        st, body = fetch(self.URL, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        import xml.etree.ElementTree as ET
        enlaces = [(i.findtext("link") or "") for i in ET.fromstring(body).iter("item")]
        directos = [u for u in enlaces if "news.google.com" not in u]
        self.assertFalse(
            directos,
            f"¡el feed ya publica enlaces al medio ({directos[:2]})! Revisar "
            "docs/LIMITACIONES.md: la URL original ha dejado de perderse")


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosUnosat(unittest.TestCase):
    """UNITAR-UNOSAT: el Centro Satelital de la ONU (https://unosat.org).

    No hay API documentada: estos supuestos describen los dos endpoints JSON
    que sirven a la web y de los que cuelga la capa de daño del monitor.
    """

    LISTADO = "https://unosat.org/our_products/"
    GLIDE = "EQ20260810COL"

    def test_el_listado_sigue_sirviendo_json(self):
        st, d = fetch_json(self.LISTADO, note=NOTA_SONDA)
        if st != 200 or not d:
            self.skipTest(
                f"UNOSAT no responde (HTTP {st}): la capa sobrevive con los "
                f"snapshots de data/snapshots/*/unosat_shapefiles.zip; si el "
                f"cierre es definitivo, congelar la fuente y documentarlo en "
                f"docs/LIMITACIONES.md")
        self.assertIn("products", d, "el listado cambió de forma")
        self.assertTrue(all("map_event" in p for p in d["products"]))

    def test_el_listado_sigue_sin_paginar(self):
        """El módulo consulta también los ids ya conocidos PORQUE el listado
        es una ventana fija sin filtros. Si algún día acepta paginación o
        filtro por GLIDE, la fuente puede simplificarse — sería buena noticia
        (R11): el histórico dejaría de depender de lo ya visto."""
        st, base = fetch_json(self.LISTADO, note=NOTA_SONDA)
        if st != 200 or not base:
            self.skipTest("UNOSAT no responde")
        st2, filtrado = fetch_json(self.LISTADO, {"glide": self.GLIDE},
                                   note=NOTA_SONDA)
        if st2 != 200 or not filtrado:
            self.skipTest("UNOSAT no responde al filtro")
        self.assertEqual(
            [p["map_event"]["id"] for p in base["products"]],
            [p["map_event"]["id"] for p in filtrado["products"]],
            "¡el listado ahora filtra por GLIDE! Simplificar "
            "unosat._productos_del_evento(): ya no hace falta consultar los "
            "ids conocidos para no perder el histórico")

    def test_el_detalle_trae_los_enlaces_de_descarga(self):
        st, d = fetch_json("https://unosat.org/our_products/4253",
                           note=NOTA_SONDA)
        if st != 200 or not d:
            self.skipTest(f"UNOSAT no responde (HTTP {st})")
        m = d["map_event"]
        self.assertEqual(m["glide"], self.GLIDE)
        for campo in ("shp_link", "pdf_name", "created_at", "title"):
            self.assertIn(campo, m, f"el detalle ya no trae {campo}")
        self.assertIn("latitude", d)

    def test_el_paquete_de_shapefiles_sigue_siendo_uno_solo(self):
        """Los productos 4251, 4252 y 4253 publican el MISMO zip. La fuente
        deduplica por sha256 contando con ello; si un día divergen, cada uno
        aportará datos propios y habrá MÁS cobertura, no menos — hay que
        revisar el resumen de la corrida, no arreglar nada a la carrera."""
        import hashlib
        from common import fetch
        shas = {}
        for pid in (4251, 4253):
            st, body = fetch(
                f"https://unosat.org/static/unosat_filesystem/{pid}/"
                f"EQ20260810COL_SHP.zip", note=NOTA_SONDA)
            if st != 200 or not body:
                self.skipTest(f"el paquete de {pid} no responde (HTTP {st})")
            shas[pid] = hashlib.sha256(body).hexdigest()
        self.assertEqual(
            shas[4251], shas[4253],
            "los paquetes de UNOSAT ya NO son idénticos: cada producto "
            "aporta datos propios. Revisar el conteo de unosat.run() — "
            "puede haber cobertura nueva que antes se descartaba por duplicada")
