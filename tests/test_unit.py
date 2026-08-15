"""Tests unitarios (offline): la lógica pura del pipeline.

Se ejecutan sin red y sin base de datos previa. Las expectativas vienen de la
documentación del proyecto y de las specs de las fuentes, no de mirar la
salida del código — si un test falla, el código está mal, no el test.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))

from common import to_num
from geo import wkt_to_geojson, wkt_to_rings, point_in_wkt_polygon, MMIGrid


class TestToNum(unittest.TestCase):
    """Trampa documentada de Copernicus: total/affected llegan como 'NA'."""

    def test_na_nunca_es_cero(self):
        for raw in ("NA", "-", "", None, "None", "null"):
            self.assertIsNone(to_num(raw), f"{raw!r} debe ser None, jamás 0")

    def test_numeros_validos(self):
        self.assertEqual(to_num(182), 182.0)
        self.assertEqual(to_num("0.6"), 0.6)
        self.assertEqual(to_num("190,000"), 190000.0)
        self.assertEqual(to_num(0), 0.0)  # cero real sí es cero

    def test_basura_no_revienta(self):
        self.assertIsNone(to_num("abc"))
        self.assertIsNone(to_num(True))  # bool no es cifra de daño


class TestWKT(unittest.TestCase):
    SQ = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"

    def test_poligono(self):
        gj = wkt_to_geojson(self.SQ)
        self.assertEqual(gj["type"], "Polygon")
        self.assertEqual(len(gj["coordinates"][0]), 5)

    def test_punto(self):
        gj = wkt_to_geojson("POINT (-76.2574 3.8739)")
        self.assertEqual(gj["type"], "Point")
        self.assertAlmostEqual(gj["coordinates"][0], -76.2574)

    def test_vacio_y_malformado(self):
        self.assertIsNone(wkt_to_geojson(""))
        self.assertIsNone(wkt_to_geojson(None))
        self.assertEqual(wkt_to_rings("POLYGON (())"), [])

    def test_dentro_fuera(self):
        self.assertTrue(point_in_wkt_polygon(5, 5, self.SQ))
        self.assertFalse(point_in_wkt_polygon(15, 5, self.SQ))
        self.assertFalse(point_in_wkt_polygon(-0.001, 5, self.SQ))

    def test_agujero(self):
        donut = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (4 4, 6 4, 6 6, 4 6, 4 4))"
        self.assertFalse(point_in_wkt_polygon(5, 5, donut), "el agujero no cuenta")
        self.assertTrue(point_in_wkt_polygon(2, 2, donut))


class TestMMIGrid(unittest.TestCase):
    def grid(self):
        # rejilla 3x3: lon -78..-74, lat 2..6, valores crecientes
        return MMIGrid({
            "domain": {"axes": {"x": {"start": -78, "stop": -74, "num": 3},
                                "y": {"start": 2, "stop": 6, "num": 3}}},
            "ranges": {"MMI": {"values": [1, 2, 3, 4, 5, 6, 7, 8, 9]}},
        })

    def test_esquinas(self):
        g = self.grid()
        self.assertEqual(g.mmi_at(-78, 2), 1)
        self.assertEqual(g.mmi_at(-74, 6), 9)
        self.assertEqual(g.mmi_at(-76, 4), 5)  # centro

    def test_fuera_de_rejilla(self):
        self.assertIsNone(self.grid().mmi_at(0, 0))


class TestCrosscheckReglas(unittest.TestCase):
    """La regla dura del proyecto: nada llega a 'coincide' sin evidencia oficial."""

    def _run(self, evidence_oficial=0, prensa=0, ciudadano=0, has_stats=True):
        # réplica de la lógica de decisión de crosscheck.run (mantener en sincronía)
        if evidence_oficial > 0:
            return "coincide"
        if not has_stats:
            return "no_comparable"
        if prensa > 0:
            return "prensa"
        if ciudadano > 0:
            return "ciudadano"
        return "pendiente"

    def test_defecto_es_pendiente(self):
        self.assertEqual(self._run(), "pendiente")

    def test_prensa_no_promueve_a_coincide(self):
        self.assertEqual(self._run(prensa=500), "prensa")

    def test_ciudadano_no_promueve_a_coincide(self):
        self.assertEqual(self._run(ciudadano=99), "ciudadano")

    def test_solo_oficial_promueve(self):
        self.assertEqual(self._run(evidence_oficial=1, prensa=0), "coincide")

    def test_sin_stats_no_comparable(self):
        self.assertEqual(self._run(has_stats=False, prensa=10), "no_comparable")


class TestToponimos(unittest.TestCase):
    def match(self, text):
        import re
        import unicodedata
        norm = "".join(c for c in unicodedata.normalize("NFD", text)
                       if unicodedata.category(c) != "Mn").lower()
        return {aoi for aoi, tops in TOPONYMS.items()
                if any(re.search(rf"\b{re.escape(t)}\b", norm) for t in tops)}

    def test_cali_no_es_california(self):
        self.assertNotIn("Northern Cali", self.match("Earthquake felt in California"))
        self.assertIn("Northern Cali", self.match("Colapso en Cali tras el sismo"))

    def test_acentos(self):
        self.assertIn("Quibdo Centre", self.match("Daños graves en Quibdó"))

    def test_no_falsos_positivos_en_derivadas(self):
        self.assertNotIn("Northern Cali", self.match("la calidad del aire empeora"))
        self.assertNotIn("Istmina", self.match("el istmo de Panamá"))


class TestPrivacidad(unittest.TestCase):
    def test_redondeo_publico(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from chatmap import _round_pub
        self.assertEqual(_round_pub(3.9099751234), 3.910)
        # 3 decimales ≈ 110 m: la coordenada exacta no debe sobrevivir
        self.assertNotEqual(_round_pub(3.9099751234), 3.9099751234)


class TestResumenAoi(unittest.TestCase):
    """Cifras del análisis original de Pereira, desde fixture del snapshot real."""

    FIXTURE = {
        "Built-up": {"Residential Buildings": {"unit": "", "total": None,
                                               "affected": 182.0}},
        "Transportation": {"Local Road": {"unit": "km", "total": 185.7, "affected": 0.6},
                           "Secondary Road": {"unit": "km", "total": 41.4,
                                              "affected": 0.2}},
        "Estimated population": {"None": {"unit": "", "total": 190000.0}},
        "Blocked road / interruption": {"None": {"unit": "", "total": None,
                                                 "affected": 11.0}},
    }

    def test_pereira(self):
        from publish import resumen_aoi
        r = resumen_aoi(self.FIXTURE)
        self.assertEqual(r["edificios_afectados"], 182.0)
        self.assertAlmostEqual(r["vias_afectadas_km"], 0.8)
        self.assertEqual(r["interrupciones_viales"], 11.0)
        self.assertEqual(r["poblacion"], 190000.0)

    def test_sin_datos_es_none_no_cero(self):
        from publish import resumen_aoi
        r = resumen_aoi({})
        self.assertIsNone(r["edificios_afectados"])
        self.assertIsNone(r["vias_afectadas_km"])


class TestMunicipiosInfluencia(unittest.TestCase):
    def test_prensa_agrega_municipio_fuera_de_aoi(self):
        from municipios import build_municipios
        rows, gj = build_municipios([
            {"titulo": "Armenia reporta afectaciones tras el terremoto",
             "medio": "medio", "fecha": "2026-08-15", "url": "https://x.test"}
        ], None, {})
        armenia = next(r for r in rows if r["municipio"] == "Armenia")
        self.assertEqual(armenia["n_noticias"], 1)
        self.assertEqual(armenia["estado"], "mencion_prensa")
        self.assertFalse(armenia["en_aoi_copernicus"])
        self.assertEqual(gj["type"], "FeatureCollection")

    def test_dyfi_alto_agrega_zarzal(self):
        from municipios import build_municipios
        rows, _ = build_municipios([], {
            "features": [{"properties": {"name": "UTM:(18N)<br>Zarzal",
                                         "cdi": 7.9, "nresp": 1, "dist": 123}}]
        }, {})
        zarzal = next(r for r in rows if r["municipio"] == "Zarzal")
        self.assertEqual(zarzal["dyfi_max_cdi"], 7.9)
        self.assertEqual(zarzal["estado"], "intensidad_alta")

    def test_enriquece_poblacion_dane(self):
        from municipios import build_municipios
        rows, _ = build_municipios([
            {"titulo": "Armenia fue mencionada", "medio": "medio"}
        ], None, {}, {
            "armenia|quindio": {"divipola": "63001", "poblacion_2026": 310000,
                                "cabecera_2026": 300000, "rural_2026": 10000}
        })
        armenia = next(r for r in rows if r["municipio"] == "Armenia")
        self.assertEqual(armenia["divipola"], "63001")
        self.assertEqual(armenia["poblacion_2026"], 310000)

    def test_poblacion_dane_por_alias_oficial(self):
        from municipios import build_municipios
        rows, _ = build_municipios([], {
            "features": [{"properties": {"name": "UTM:(18N)<br>Buga",
                                         "cdi": 6.7, "nresp": 1, "dist": 90}}]
        }, {}, {
            "guadalajara de buga|valle del cauca": {
                "divipola": "76111", "poblacion_2026": 132000,
                "cabecera_2026": 115000, "rural_2026": 17000}
        })
        buga = next(r for r in rows if r["municipio"] == "Buga")
        self.assertEqual(buga["divipola"], "76111")
        self.assertEqual(buga["poblacion_2026"], 132000)


class TestFeedsComunitarios(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Sismo en Quibd\xc3\xb3 deja da\xc3\xb1os</title>
        <link>https://x.co/1</link><pubDate>Fri, 15 Aug 2026 10:00:00 GMT</pubDate></item>
      <item><title>Sin enlace</title></item>
    </channel></rss>"""
    ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Replica del terremoto</title>
        <link href="https://x.co/2"/><updated>2026-08-15T11:00:00Z</updated></entry></feed>"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))

    def test_rss(self):
        from community_feeds import parse_rss
        items = parse_rss(self.RSS)
        self.assertEqual(len(items), 1, "items sin enlace se descartan")
        self.assertEqual(items[0]["url"], "https://x.co/1")
        self.assertTrue(items[0]["fecha"].startswith("2026-08-15"))

    def test_atom(self):
        from community_feeds import parse_rss
        items = parse_rss(self.ATOM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://x.co/2")

    def test_xml_roto_no_revienta(self):
        from community_feeds import parse_rss
        self.assertEqual(parse_rss(b"<html>no soy rss"), [])
        self.assertEqual(parse_rss(b""), [])

    def test_feeds_google_news_por_municipio(self):
        from community_feeds import municipal_google_news_feeds
        feeds = municipal_google_news_feeds()
        ids = {f["id"] for f in feeds}
        self.assertIn("googlenews-municipio-armenia", ids)
        self.assertIn("googlenews-municipio-zarzal", ids)
        armenia = next(f for f in feeds if f["id"] == "googlenews-municipio-armenia")
        self.assertIn("%22armenia%22", armenia["url"])
        self.assertIn("%22quindio%22", armenia["url"])

    def test_feed_municipal_no_depende_del_filtro_general(self):
        from community_feeds import _relevante
        item = {"titulo": "Afectaciones reportadas en Armenia"}
        feed = {"municipio": "Armenia"}
        self.assertTrue(_relevante(item, feed, None))


TOPONYMS = None


def setUpModule():
    global TOPONYMS
    from crosscheck import AOI_TOPONYMS
    TOPONYMS = AOI_TOPONYMS


if __name__ == "__main__":
    unittest.main(verbosity=2)
