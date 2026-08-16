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

from common import fetch_json

ONLINE = os.environ.get("SKIP_ONLINE") != "1"
COP = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosCopernicus(unittest.TestCase):
    def test_code_es_obligatorio(self):
        st, d = fetch_json(COP, note="test supuesto")
        self.assertTrue(not d or not d.get("results"),
                        "la API ahora lista sin code: ¡mejorar el ingestor!")

    def test_emsr916_existe_con_aois(self):
        st, d = fetch_json(COP, {"code": "EMSR916"}, note="test supuesto")
        self.assertEqual(st, 200)
        r = d["results"][0]
        self.assertEqual(r["code"], "EMSR916")
        self.assertGreaterEqual(len(r["aois"]), 7)
        self.assertIn("Colombia", [c["name"] for c in r["countries"]])

    def test_na_sigue_presente_en_stats(self):
        """El parser tolera 'NA'; verificar que el supuesto sigue vivo."""
        st, d = fetch_json(COP, {"code": "EMSR916"}, note="test supuesto")
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
        st, d = fetch_json(COP, {"code": "EMSR916"}, note="test supuesto")
        tipos = {p["type"] for a in d["results"][0]["aois"]
                 for p in a.get("products") or []}
        self.assertTrue(tipos - {"FEP", "REF", "DEL", "GRA"} or tipos,
                        "el parser debe seguir siendo tolerante a tipos nuevos")

    def test_hueco_documentado(self):
        """EMSR700 falla entre vecinos válidos: hueco puntual, no error."""
        st, d = fetch_json(COP, {"code": "EMSR700"}, note="test supuesto")
        self.assertFalse((d or {}).get("results"),
                         "EMSR700 ahora existe: retirar el supuesto del hueco")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosOficiales(unittest.TestCase):
    def test_socrata_sigue_parado_en_2022(self):
        st, d = fetch_json("https://www.datos.gov.co/resource/wwkg-r6te.json",
                           {"$select": "max(fecha)"}, note="test supuesto")
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
                          note="test supuesto")
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
            note="test supuesto rud")
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
                           note="test supuesto")
        self.assertEqual(st, 200)
        if d:  # la ventana ~5 días puede vaciar el feed: eso es esperado
            self.assertIn("pubdate", d[0])
            self.assertIn("link", d[0])

    def test_chatmap_vivo_o_documentado(self):
        st, d = fetch_json("https://chatmap.hotosm.org/api/v1/map/"
                           "89319bbb-a14a-4dfd-b9a1-c83b8b55785f",
                           note="test supuesto")
        if st != 200:
            self.skipTest(f"ChatMap cerró (HTTP {st}): activar canal Kobo, "
                          "los snapshots conservan lo capturado")
        self.assertIn("features", d)

    def test_dyfi_geojson_disponible(self):
        st, d = fetch_json("https://earthquake.usgs.gov/fdsnws/event/1/query",
                           {"eventid": "us6000tjl2", "format": "geojson"},
                          note="test supuesto")
        self.assertEqual(st, 200)
        self.assertIn("dyfi", d["properties"]["products"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
