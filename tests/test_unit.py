"""Tests unitarios (offline): la lógica pura del pipeline.

Se ejecutan sin red y sin base de datos previa. Las expectativas vienen de la
documentación del proyecto y de las specs de las fuentes, no de mirar la
salida del código — si un test falla, el código está mal, no el test.
"""
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
    """La regla dura del proyecto: nada llega a 'coincide' sin evidencia
    oficial. Se testea la función REAL (crosscheck.decidir_estado), no una
    réplica — si la regla cambia en el código, estos tests lo notan."""

    def _run(self, evidence_oficial=0, prensa=0, ciudadano=0, has_stats=True):
        from crosscheck import decidir_estado
        return decidir_estado(has_stats, evidence_oficial, prensa, ciudadano)

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

    def test_oficial_sin_satelite_tampoco_compara(self):
        # RUD puede tener registro donde Copernicus aún no entregó producto
        self.assertEqual(self._run(has_stats=False, evidence_oficial=1),
                         "no_comparable")


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

    def test_solo_rud_incluye_municipio_sin_prensa_ni_dyfi(self):
        from municipios import build_municipios
        rud = {("choco", "condoto"): {
            "departamento": "CHOCÓ", "municipio": "CONDOTO",
            "familias": 969, "personas": 2811,
            "viv_destruidas": 22, "viv_averiadas": 22}}
        rows, gj = build_municipios([], None, {}, {
            "condoto|choco": {"divipola": "27205", "poblacion_2026": 12620,
                              "cabecera_2026": 9000, "rural_2026": 3620}
        }, rud)
        condoto = next(r for r in rows if r["municipio"] == "Condoto")
        self.assertEqual(condoto["estado"], "solo_rud")
        self.assertIn("rud", condoto["fuentes"])
        self.assertEqual(condoto["rud_personas"], 2811)
        self.assertAlmostEqual(condoto["tasa_rud_pct"], 22.27, places=2)
        # R3: sin celda DYFI atribuida no hay cero, hay ausencia de dato
        self.assertIsNone(condoto["dyfi_respuestas"])
        self.assertEqual(condoto["dyfi_celdas"], 0)

    def test_rud_no_sube_el_estado_de_municipio_con_prensa(self):
        # el RUD añade datos pero no puede escalar el estado por encima
        # de la cascada existente (espíritu de R2 fuera del cruce)
        from municipios import build_municipios
        rud = {("quindio", "armenia"): {
            "departamento": "QUINDÍO", "municipio": "ARMENIA",
            "familias": 5, "personas": 12,
            "viv_destruidas": 0, "viv_averiadas": 1}}
        rows, _ = build_municipios([
            {"titulo": "Armenia reporta afectaciones", "medio": "medio"}
        ], None, {}, None, rud)
        armenia = next(r for r in rows if r["municipio"] == "Armenia")
        self.assertEqual(armenia["estado"], "mencion_prensa")
        self.assertIn("rud", armenia["fuentes"])
        self.assertEqual(armenia["rud_personas"], 12)

    def test_municipio_rud_desconocido_entra_via_divipola(self):
        # si mañana el RUD registra un municipio fuera de la lista curada,
        # entra solo con coordenadas del catálogo DIVIPOLA — no se pierde
        from municipios import build_municipios
        rud = {("antioquia", "medellin"): {
            "departamento": "ANTIOQUIA", "municipio": "MEDELLÍN",
            "familias": 10, "personas": 25,
            "viv_destruidas": 1, "viv_averiadas": 2}}
        divipola = {"medellin|antioquia": {
            "municipio": "MEDELLÍN", "departamento": "ANTIOQUIA",
            "divipola": "05001", "lat": 6.2466, "lon": -75.5818}}
        rows, gj = build_municipios([], None, {}, None, rud, divipola)
        med = next(r for r in rows if r["municipio"] == "Medellín")
        self.assertEqual(med["estado"], "solo_rud")
        self.assertEqual(med["lat"], 6.2466)
        self.assertEqual(len(gj["features"]), 1)

    def test_tasa_diminuta_no_se_redondea_a_cero(self):
        # una persona registrada en una capital es 0,0003 % — redondear a dos
        # decimales lo volvía 0,0 y el sitio lo leía como «sin damnificados»
        from municipios import build_municipios
        rud = {("quindio", "armenia"): {
            "departamento": "QUINDÍO", "municipio": "ARMENIA",
            "familias": 1, "personas": 1,
            "viv_destruidas": 0, "viv_averiadas": 0}}
        rows, _ = build_municipios([], None, {}, {
            "armenia|quindio": {"divipola": "63001", "poblacion_2026": 307103,
                                "cabecera_2026": 298815, "rural_2026": 8288}
        }, rud)
        armenia = next(r for r in rows if r["municipio"] == "Armenia")
        self.assertGreater(armenia["tasa_rud_pct"], 0,
                           "una proporción real jamás debe publicarse como 0")

    def test_toponimo_ambiguo_exige_departamento(self):
        # «Toro», «Palestina», «Restrepo» son municipios reales, pero también
        # palabra común, territorio y apellido: sin el departamento no cuentan
        from municipios import build_municipios, match_municipios_text
        self.assertEqual(match_municipios_text("El ministro Restrepo viajó"), [])
        self.assertEqual(match_municipios_text("Ayuda para Palestina"), [])
        self.assertIn("Toro", match_municipios_text(
            "Toro, Valle del Cauca, reporta viviendas averiadas"))
        rows, _ = build_municipios([
            {"titulo": "Corrida de toros suspendida", "medio": "medio"}
        ], None, {})
        self.assertNotIn("Toro", [r["municipio"] for r in rows])

    def test_toponimo_igual_a_departamento_exige_contexto(self):
        """Risaralda es un municipio de Caldas de 11.000 habitantes Y el nombre
        de un departamento entero: sin esta marca, los 67 titulares del
        departamento se atribuían al municipio (y contaminaban la etiqueta
        departamental de las noticias). Se comprueba la CLASE completa contra
        el catálogo DIVIPOLA, no solo el caso conocido."""
        import json
        from municipios import MUNICIPIOS, _norm, match_municipios_text
        div = Path(__file__).parent.parent / "data" / "public" / "divipola_coords.json"
        if not div.exists():
            self.skipTest("sin catálogo DIVIPOLA: correr ingest/build_divipola.py")
        deptos = {_norm(v["departamento"])
                  for v in json.loads(div.read_text())["items"].values()}
        sin_marca = [m for m, meta in MUNICIPIOS.items()
                     if not meta.get("homonimo_de_departamento")
                     and any(t in deptos for t in meta["toponimos"])]
        self.assertEqual(sin_marca, [],
                         f"topónimos que también nombran un departamento y "
                         f"aceptan prensa por texto: {sin_marca}")
        # ni con el departamento al lado: «Caldas y Risaralda» es el departamento
        self.assertEqual(match_municipios_text("Terremoto en Risaralda"), [])
        self.assertEqual(
            match_municipios_text("Sismo en municipios de Caldas y Risaralda"), [])

    def test_municipio_dinamico_nace_exigiendo_departamento(self):
        # las entradas no curadas son las que más necesitan el criterio
        # conservador: nadie ha revisado si su nombre es palabra común
        from municipios import municipios_dinamicos
        rud = {("santander", "bolivar"): {
            "departamento": "SANTANDER", "municipio": "BOLÍVAR",
            "familias": 3, "personas": 8,
            "viv_destruidas": 0, "viv_averiadas": 1}}
        extras = municipios_dinamicos(rud, None)
        self.assertTrue(all(v.get("requiere_depto") for v in extras.values()),
                        f"entradas dinámicas sin requiere_depto: {extras}")

    def test_homonimo_de_departamento_viaja_al_frontend(self):
        """El sitio necesita el flag para pintar «—» en Prensa en vez de «0»:
        que el monitor no pueda atribuir titulares no es que no existan."""
        from municipios import build_municipios
        rud = {("caldas", "risaralda"): {
            "departamento": "CALDAS", "municipio": "RISARALDA",
            "familias": 150, "personas": 419,
            "viv_destruidas": 2, "viv_averiadas": 10}}
        rows, _ = build_municipios([
            {"titulo": "Sismo en municipios de Caldas y Risaralda", "medio": "medio"}
        ], None, {}, None, rud)
        r = next(x for x in rows if x["municipio"] == "Risaralda")
        self.assertTrue(r["homonimo_de_departamento"])
        self.assertEqual(r["n_noticias"], 0)
        self.assertEqual(r["estado"], "solo_rud")

    def test_san_jose_no_captura_al_epicentro(self):
        """«San José» (Caldas) usa topónimo con coma porque «san jose» a secas
        casa dentro de «San José del Palmar», el epicentro. Cuesta cobertura
        —los titulares que digan «San José (Caldas)» no cuentan— pero jamás
        atribuye el epicentro a un municipio de otro departamento."""
        from municipios import match_municipios_text
        epicentro = match_municipios_text(
            "San José del Palmar, Chocó: el epicentro del sismo")
        self.assertEqual(epicentro, ["San José del Palmar"])
        self.assertIn("San José",
                      match_municipios_text("San José, Caldas: casas averiadas"))

    def test_dyfi_no_atribuye_municipio_duplicado(self):
        # Riosucio existe en Caldas y en Chocó: DYFI no trae departamento,
        # así que la intensidad no se atribuye a ninguno de los dos
        from municipios import build_municipios
        rows, _ = build_municipios([], {
            "features": [{"properties": {"name": "UTM:(18N)<br>Riosucio",
                                         "cdi": 7.2, "nresp": 3, "dist": 60}}]
        }, {})
        conintensidad = [r["municipio"] for r in rows
                         if r["dyfi_max_cdi"] is not None]
        self.assertEqual(conintensidad, [])

    def test_municipio_rud_sin_coordenadas_no_se_pierde(self):
        # sin DIVIPOLA no hay punto en el mapa, pero la fila sobrevive
        from municipios import build_municipios
        rud = {("antioquia", "medellin"): {
            "departamento": "ANTIOQUIA", "municipio": "MEDELLÍN",
            "familias": 10, "personas": 25,
            "viv_destruidas": 1, "viv_averiadas": 2}}
        rows, gj = build_municipios([], None, {}, None, rud, None)
        med = next(r for r in rows if r["municipio"] == "Medellín")
        self.assertEqual(med["estado"], "solo_rud")
        self.assertIsNone(med["lat"])
        self.assertEqual(len(gj["features"]), 0)


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

    def test_feed_municipal_busca_el_toponimo_no_la_clave(self):
        """Las claves desambiguadas llevan paréntesis («Riosucio (Caldas)»):
        buscar la clave literal daría un feed que devuelve cero para siempre,
        y un cero silencioso es peor que no tener el feed."""
        from urllib.parse import unquote_plus
        from community_feeds import municipal_google_news_feeds
        for f in municipal_google_news_feeds():
            q = unquote_plus(f["url"].split("q=")[1].split("&")[0])
            frase = q.split('"')[3]   # ("terremoto" OR …) "frase" "depto"
            self.assertNotIn("(", frase,
                             f"{f['id']} busca la clave del diccionario, no el "
                             f"topónimo: la frase «{frase}» no existe en prensa")
        rio = next(f for f in municipal_google_news_feeds()
                   if f["id"] == "googlenews-municipio-riosucio-caldas")
        self.assertIn("%22riosucio%22", rio["url"])
        self.assertIn("%22caldas%22", rio["url"])

    def test_sin_feed_automatico_para_homonimos_de_departamento(self):
        """La búsqueda «risaralda» + «caldas» casa con los titulares del
        DEPARTAMENTO de Risaralda, y como el feed declara su municipio, la
        atribución que _menciona_municipio rechaza volvería por la puerta de
        atrás (publish.py confía en lo que el feed declara)."""
        from community_feeds import municipal_google_news_feeds
        from municipios import MUNICIPIOS
        homonimos = {m for m, meta in MUNICIPIOS.items()
                     if meta.get("homonimo_de_departamento")}
        self.assertTrue(homonimos, "el fixture perdió sentido: no hay homónimos")
        declarados = {m for f in municipal_google_news_feeds()
                      for m in (f.get("municipios") or [])}
        self.assertEqual(homonimos & declarados, set(),
                         f"feed automático que atribuye prensa a un homónimo de "
                         f"departamento: {homonimos & declarados}")

    def test_feed_municipal_no_depende_del_filtro_general(self):
        from community_feeds import _relevante
        import re
        pat = re.compile("sismo|terremoto|temblor")
        item = {"titulo": "Sismo deja afectaciones reportadas en Armenia"}
        feed = {"municipio": "Armenia"}
        self.assertTrue(_relevante(item, feed, pat))
        self.assertFalse(_relevante({"titulo": "Pico y placa en Armenia"}, feed, pat))

    def test_etiqueta_municipios_y_departamentos_en_texto(self):
        from municipios import match_departamentos_text, match_municipios_text
        municipios = match_municipios_text("Sismo en Zarzal y Armenia")
        self.assertEqual(municipios, ["Armenia", "Zarzal"])
        self.assertEqual(match_departamentos_text("", municipios),
                         ["Quindío", "Valle del Cauca"])


TOPONYMS = None


def setUpModule():
    global TOPONYMS
    from crosscheck import AOI_TOPONYMS
    TOPONYMS = AOI_TOPONYMS


class TestSnapshotsIntradia(unittest.TestCase):
    """Los snapshots son inmutables e intradía: el primer cuerpo del día
    conserva el nombre canónico; un cuerpo distinto el mismo día se archiva
    con sufijo _sha8. Jamás un sha256 en el log sin cuerpo recuperable."""

    def test_dos_cuerpos_distintos_dos_snapshots(self):
        import sqlite3
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn = sqlite3.connect(":memory:")
            conn.executescript(common.SCHEMA)

            class Resp:
                def __init__(self, b): self.status, self._b = 200, b
                def read(self): return self._b
                def __enter__(self): return self
                def __exit__(self, *a): return False

            cuerpos = [b'{"a":1}', b'{"a":1}', b'{"a":2}']
            with mock.patch.object(common, "ROOT", tmp), \
                 mock.patch.object(common, "SNAPSHOTS", tmp / "snapshots"), \
                 mock.patch.object(common.urllib.request, "urlopen",
                                   side_effect=[Resp(b) for b in cuerpos]):
                for _ in cuerpos:
                    common.fetch("https://x/f", snapshot_name="fuente.json",
                                 conn=conn)
            dia = tmp / "snapshots" / common.today()
            nombres = sorted(p.name for p in dia.iterdir())
            self.assertEqual(len(nombres), 2, nombres)  # canónico + _sha8
            self.assertIn("fuente.json", nombres)
            self.assertTrue(any("_" in n and n != "fuente.json" for n in nombres))
            # cada fila del log apunta a un cuerpo cuyo sha coincide
            import hashlib
            for spath, sha in conn.execute(
                    "SELECT snapshot_path, sha256 FROM sources_log"):
                self.assertIsNotNone(spath, "fila con cuerpo sin snapshot_path")
                cuerpo = (tmp / spath).read_bytes()
                self.assertEqual(hashlib.sha256(cuerpo).hexdigest(), sha,
                                 "el snapshot no corresponde al sha del log")
            conn.close()


class TestDumpRoundtrip(unittest.TestCase):
    """El sqlite no se versiona; los dumps CSV sí. Si el ciclo dump→rebuild
    perdiera un solo valor (un NULL vuelto cero, una tilde rota), el archivo
    histórico quedaría corrupto en silencio — este test lo impide."""

    def test_ida_y_vuelta_fiel(self):
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            origen = sqlite3.connect(tmp / "a.sqlite")
            origen.executescript(SCHEMA)
            # muestras con lo traicionero: NULL, 0, tildes, comas, comillas, saltos
            origen.execute(
                "INSERT INTO rud_daily VALUES ('2026-08-16','CHOCÓ','ISTMINA',"
                "969.0,2811.0,NULL,0.0,NULL,22.0)")
            origen.execute(
                "INSERT INTO news_items VALUES ('https://x/y?a=1','feed-1',"
                "'2026-08-16','Título, con \"comillas\" y\nsalto','Medio Ñandú',"
                "'2026-08-16')")
            origen.execute(
                "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                "snapshot_path,note) VALUES ('2026-08-16T00:00:00Z','u',200,"
                "NULL,0,NULL,'NA no es cero')")
            origen.commit()
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                dump_db.dump(origen)
                dump_db.rebuild(tmp / "b.sqlite")
                copia = sqlite3.connect(tmp / "b.sqlite")
                for tabla in dump_db.TABLAS:
                    cols = [r[1] for r in origen.execute(
                        f"PRAGMA table_info({tabla})")]
                    sel = f"SELECT {', '.join(cols)} FROM {tabla} ORDER BY {cols[0]}"
                    self.assertEqual(
                        origen.execute(sel).fetchall(),
                        copia.execute(sel).fetchall(),
                        f"la tabla {tabla} no sobrevivió al ciclo dump→rebuild")
                copia.close()
            finally:
                dump_db.DUMPS = dumps_orig
            origen.close()


class TestAlertsRss(unittest.TestCase):
    """El RSS de alertas debe ser XML válido con escape correcto: los textos
    de alerta traen &, <, comillas y emoji — un feed roto es peor que no
    tener feed."""

    def test_xml_valido_y_escapado(self):
        import xml.etree.ElementTree as ET
        from alerts import alerts_rss
        alertas = [
            {"tipo": "rud_actualizado", "nivel": "info",
             "texto": "RUD: 75 municipios & <familias> \"nuevas\""},
            {"tipo": "balance_en_medios", "nivel": "info",
             "texto": "294 fallecidos (+0 vs día anterior)"},
            {"tipo": "rud_activo", "nivel": "alta", "texto": "⚠️ cubre el evento"},
        ]
        xml_texto = alerts_rss("2026-08-17", alertas)
        raiz = ET.fromstring(xml_texto)  # lanza si el XML está roto
        items = raiz.findall(".//item")
        self.assertEqual(len(items), 3, "un item por alerta")
        descripciones = [i.findtext("description") for i in items]
        self.assertIn('RUD: 75 municipios & <familias> "nuevas"', descripciones)
        titulos = [i.findtext("title") for i in items]
        self.assertTrue(any(t.startswith("⚠️") for t in titulos),
                        "las de nivel alta llevan marca")
        guids = [i.findtext("guid") for i in items]
        self.assertEqual(len(guids), len(set(guids)), "guids únicos")

    def test_sin_alertas_es_feed_vacio_valido(self):
        import xml.etree.ElementTree as ET
        from alerts import alerts_rss
        raiz = ET.fromstring(alerts_rss("2026-08-17", []))
        self.assertEqual(len(raiz.findall(".//item")), 0)


class TestParidadLiveblog(unittest.TestCase):
    """La regla editorial «liveblog» vive en dos lenguajes: el worker la marca
    en origen (workers/ai-view) y el frontend la reaplica (site/ui.js). Si los
    términos divergen, una cobertura «en vivo» podría pesar distinto según
    quién la mire — este test compara los términos de ambas regex."""

    ROOT = Path(__file__).parent.parent

    def _terminos(self, texto: str) -> set[str]:
        import re
        # la alternancia siempre empieza en «en vivo» y termina en «liveblog»
        m = re.search(r"en vivo\|[^\n/]*?liveblog", texto)
        self.assertIsNotNone(m, "no se encontró la regex de liveblog")
        crudo = m.group(0).replace("\\b", "").replace("(", "").replace(")", "")
        return {t.strip() for t in crudo.split("|") if t.strip()}

    def test_worker_y_frontend_marcan_los_mismos_terminos(self):
        ui = (self.ROOT / "site" / "ui.js").read_text(encoding="utf-8")
        worker = (self.ROOT / "workers" / "ai-view" / "src" / "index.js").read_text(
            encoding="utf-8")
        self.assertEqual(
            self._terminos(ui), self._terminos(worker),
            "los términos de liveblog divergieron entre site/ui.js y el worker "
            "— unificar antes de publicar (regla R8)")


class TestExencionDeSondas(unittest.TestCase):
    """La única nota exenta del régimen fuerte de trazabilidad es la de las
    sondas de contrato. Si una fuente de ingesta la usara, publicaría cifras
    sin cuerpo archivado saltándose el test de trazabilidad."""

    ROOT = Path(__file__).parent.parent

    def test_ninguna_fuente_de_ingesta_usa_la_nota_de_sonda(self):
        from common import NOTAS_SONDA
        culpables = []
        for py in (self.ROOT / "ingest").rglob("*.py"):
            if py.name == "common.py":
                continue
            texto = py.read_text(encoding="utf-8")
            if any(n in texto for n in NOTAS_SONDA):
                culpables.append(str(py.relative_to(self.ROOT)))
        self.assertEqual(culpables, [],
                         f"la nota exenta de trazabilidad aparece en ingesta: "
                         f"{culpables} — usar una nota propia")


if __name__ == "__main__":
    unittest.main(verbosity=2)
