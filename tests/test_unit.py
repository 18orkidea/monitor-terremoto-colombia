"""Tests unitarios (offline): la lógica pura del pipeline.

Se ejecutan sin red y sin base de datos previa. Las expectativas vienen de la
documentación del proyecto y de las specs de las fuentes, no de mirar la
salida del código — si un test falla, el código está mal, no el test.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))

from common import FECHA_SISMO, anterior_al_sismo, to_num
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
        # R3 también en el JSON descargable: ausencia de dato, no cero
        self.assertIsNone(r["n_noticias"])
        self.assertEqual(r["estado"], "solo_rud")

    def test_dyfi_flojo_no_tapa_el_registro_oficial(self):
        """Belén de Umbría tenía 2.266 damnificados registrados y una sola
        celda DYFI de CDI 5,6 lo mandaba a «intensidad sentida» — un estado
        cuya explicación niega que nadie más lo documente. El registro oficial
        pesa más que «se sintió flojo»."""
        from municipios import build_municipios
        rud = {("risaralda", "belen de umbria"): {
            "departamento": "RISARALDA", "municipio": "BELÉN DE UMBRÍA",
            "familias": 864, "personas": 2266,
            "viv_destruidas": 48, "viv_averiadas": 502}}
        dyfi = {"features": [{
            "geometry": {"type": "Polygon", "coordinates": [[
                [-75.90, 5.16], [-75.83, 5.16], [-75.83, 5.24], [-75.90, 5.24],
                [-75.90, 5.16]]]},
            "properties": {"name": "UTM:(18N)<br>Belén de Umbría",
                           "cdi": 5.6, "nresp": 2, "dist": 140}}]}
        rows, _ = build_municipios([], dyfi, {}, None, rud)
        belen = next(r for r in rows if r["municipio"] == "Belén de Umbría")
        self.assertEqual(belen["estado"], "solo_rud")
        self.assertEqual(belen["dyfi_max_cdi"], 5.6)   # el DYFI no se pierde
        self.assertEqual(sorted(belen["fuentes"]), ["dyfi", "rud"])

    def test_municipio_dinamico_detecta_homonimo_de_departamento(self):
        # un municipio del RUD llamado como un departamento (Bolívar, Caldas)
        # nace sin poder recibir prensa por texto, aunque nadie lo cure
        from municipios import municipios_dinamicos
        divipola = {
            "bolivar|antioquia": {
                "municipio": "BOLÍVAR", "departamento": "ANTIOQUIA",
                "divipola": "05101", "lat": 5.84, "lon": -76.03},
            # el catálogo real trae los municipios DEL departamento Bolívar:
            # de ahí sale la lista de nombres de departamento
            "cartagena|bolivar": {
                "municipio": "CARTAGENA", "departamento": "BOLÍVAR",
                "divipola": "13001", "lat": 10.4, "lon": -75.5},
        }
        rud = {("antioquia", "bolivar"): {
            "departamento": "ANTIOQUIA", "municipio": "BOLÍVAR",
            "familias": 2, "personas": 5,
            "viv_destruidas": 0, "viv_averiadas": 1}}
        extras = municipios_dinamicos(rud, divipola)
        self.assertTrue(all(v["homonimo_de_departamento"] for v in extras.values()),
                        f"un homónimo de departamento nació sin marca: {extras}")

    def test_dyfi_no_atribuye_celda_de_otro_pais(self):
        """El USGS etiqueta cada celda con el topónimo más cercano del MUNDO:
        la celda «Balboa» del canal de Panamá se publicaba como intensidad
        sentida en Balboa (Risaralda), a 595 km. El nombre no basta: la celda
        tiene que estar al lado del municipio."""
        from municipios import build_municipios
        lejana = {"features": [{
            "geometry": {"type": "Polygon", "coordinates": [[
                [-79.64, 8.86], [-79.55, 8.86], [-79.55, 8.95], [-79.64, 8.95],
                [-79.64, 8.86]]]},
            "properties": {"name": "UTM:(17P 065 098 10000)<br>Balboa",
                           "cdi": 4.6, "nresp": 4, "dist": 592}}]}
        rows, _ = build_municipios([], lejana, {})
        self.assertEqual([r["municipio"] for r in rows], [],
                         "una celda a 595 km no puede dar intensidad al municipio")

        cercana = {"features": [{
            "geometry": {"type": "Polygon", "coordinates": [[
                [-76.00, 4.91], [-75.91, 4.91], [-75.91, 4.99], [-76.00, 4.99],
                [-76.00, 4.91]]]},
            "properties": {"name": "UTM:(18N)<br>Balboa",
                           "cdi": 5.2, "nresp": 3, "dist": 120}}]}
        rows2, _ = build_municipios([], cercana, {})
        balboa = next(r for r in rows2 if r["municipio"] == "Balboa")
        self.assertEqual(balboa["dyfi_max_cdi"], 5.2)

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


class TestDiaColombianoDelRud(unittest.TestCase):
    """El RUD lo cargan las alcaldías durante SU jornada, así que la serie va por
    día colombiano cerrado. Con `today()` en UTC, la captura de las 00:02 de
    Bogotá quedaba fechada al día siguiente y atribuía a un día lo que se había
    registrado en el anterior."""

    def _consolidado(self, utc_hour, utc_min=0, dia=18):
        from datetime import datetime, timezone
        from unittest import mock
        import common
        falso = datetime(2026, 8, dia, utc_hour, utc_min, tzinfo=timezone.utc)

        class DT(datetime):
            @classmethod
            def now(cls, tz=None):
                return falso
        with mock.patch.object(common, "datetime", DT):
            return common.dia_colombiano_consolidado()

    def test_la_madrugada_de_bogota_cierra_el_dia_anterior(self):
        # 00:02 de Bogotá: el día que empieza aún no tiene registro cargado
        self.assertEqual(self._consolidado(5, 2), "2026-08-17")
        # la corrida diaria (10:30 UTC = 05:30 Bogotá) cae en esa ventana
        self.assertEqual(self._consolidado(10, 30), "2026-08-17")

    def test_despues_del_corte_consolida_el_dia_en_curso(self):
        self.assertEqual(self._consolidado(16, 30), "2026-08-18")   # 11:30 Bogotá
        self.assertEqual(self._consolidado(23, 30), "2026-08-18")   # 18:30 Bogotá

    def test_no_es_lo_mismo_que_la_fecha_utc(self):
        from common import today
        self.assertNotEqual(self._consolidado(5, 2), "2026-08-18",
                            "la captura de medianoche no pertenece al día que empieza")
        self.assertIsInstance(today(), str)


class TestSerieRudReconstruida(unittest.TestCase):
    """Un punto reconstruido rellena un hueco (una corrida perdida, y el RUD
    solo devuelve su estado actual), pero JAMÁS puede tapar una captura propia
    ni confundirse con ella."""

    ROOT = Path(__file__).parent.parent

    def test_el_fichero_declara_su_evidencia(self):
        import json
        p = self.ROOT / "feeds" / "rud_reconstruido.json"
        if not p.exists():
            self.skipTest("sin puntos reconstruidos")
        for pt in json.loads(p.read_text())["puntos"]:
            with self.subTest(fecha=pt["fecha"]):
                self.assertTrue(pt.get("origen"), "un punto sin origen es un invento")
                ev = self.ROOT / pt["evidencia"]
                self.assertTrue(ev.exists(), f"falta la evidencia: {pt['evidencia']}")
                import hashlib
                self.assertEqual(hashlib.sha256(ev.read_bytes()).hexdigest(),
                                 pt["sha256"], "la evidencia no cuadra con su sha256")

    def test_la_captura_propia_gana_al_punto_reconstruido(self):
        import json
        p = self.ROOT / "data" / "public" / "rud.json"
        if not p.exists():
            self.skipTest("sin rud.json: ejecutar publish primero")
        serie = json.loads(p.read_text())["serie"]
        fechas = [d["fecha"] for d in serie]
        self.assertEqual(fechas, sorted(fechas), "la serie debe ir en orden")
        self.assertEqual(len(fechas), len(set(fechas)),
                         "un punto reconstruido duplicó un día ya capturado")
        for d in serie:
            if d.get("reconstruido"):
                self.assertTrue(d.get("origen"),
                                "un punto marcado sin origen no es auditable")


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


class TestCorpusDePrensa(unittest.TestCase):
    """El corpus público empieza el día del sismo.

    Lo destapó Viterbo (Caldas), dado de alta el 19-ago-2026 porque UNOSAT
    evaluó allí 154 edificios: su única noticia atribuida era un sismo de
    magnitud 3,1 de junio de 2024. El topónimo estaba bien; la noticia no era
    de este desastre."""

    def test_un_titular_de_otro_sismo_es_anterior(self):
        self.assertTrue(anterior_al_sismo("2024-06-06T07:00:00"))
        self.assertTrue(anterior_al_sismo("2026-08-09T23:59:59"))

    def test_el_dia_del_sismo_entra_entero(self):
        # el terremoto fue a las 12:34 UTC, pero 514 de los 849 titulares
        # previos medidos el 19-ago venían con la fecha sin hora: cortar por
        # instante descartaría titulares del propio 10-ago sin poder probarlo
        self.assertFalse(anterior_al_sismo(FECHA_SISMO))
        self.assertFalse(anterior_al_sismo("2026-08-10T07:00:00"))
        self.assertFalse(anterior_al_sismo("2026-08-18T10:38:28"))

    def test_sin_fecha_no_consta_que_sea_anterior(self):
        # R3 aplicado al corpus: la ausencia de fecha no es un juicio
        self.assertFalse(anterior_al_sismo(None))
        self.assertFalse(anterior_al_sismo(""))

    def test_no_hay_otra_frontera_de_corte_en_la_ingesta(self):
        """La serie mediática cortaba en 2026-08-08 por su cuenta: el mismo
        titular contaba o no según la página. Una sola frontera, con nombre."""
        culpables = []
        for py in (Path(__file__).parent.parent / "ingest").rglob("*.py"):
            texto = py.read_text(encoding="utf-8")
            for linea in texto.splitlines():
                if "2026-08-0" in linea and "FECHA_SISMO" not in linea:
                    culpables.append(f"{py.name}: {linea.strip()[:70]}")
        self.assertEqual(culpables, [],
                         "fecha de corte suelta en la ingesta: usar FECHA_SISMO")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ---------------------------------------------------------------------------
# UNITAR-UNOSAT: lector de shapefile y deduplicación de paquetes
# ---------------------------------------------------------------------------
import struct as _struct  # noqa: E402


def _shp_de_puntos(puntos):
    """Un .shp mínimo de tipo Point, para no depender de la red."""
    cab = _struct.pack(">iiiiiii", 9994, 0, 0, 0, 0, 0, 0) + \
        _struct.pack("<ii", 1000, 1)
    cab += _struct.pack("<dddd", 0, 0, 0, 0) + _struct.pack("<dddd", 0, 0, 0, 0)
    cuerpo = b""
    for i, (x, y) in enumerate(puntos, start=1):
        contenido = _struct.pack("<i", 1) + _struct.pack("<dd", x, y)
        cuerpo += _struct.pack(">ii", i, len(contenido) // 2) + contenido
    return cab + cuerpo


def _dbf(campos, filas):
    """Un .dbf dBase III mínimo. `campos` es [(nombre, tipo, largo)]."""
    hlen = 32 + 32 * len(campos) + 1
    rlen = 1 + sum(c[2] for c in campos)
    out = bytes([3, 126, 8, 12]) + _struct.pack("<IHH", len(filas), hlen, rlen)
    out += b"\0" * 20
    for nombre, tipo, largo in campos:
        out += nombre.encode("latin-1").ljust(11, b"\0")
        out += tipo.encode("latin-1") + b"\0" * 4
        out += bytes([largo, 0]) + b"\0" * 14
    out += b"\x0d"
    for fila in filas:
        out += b" "
        for (nombre, _t, largo), valor in zip(campos, fila):
            out += str(valor).encode("latin-1")[:largo].ljust(largo, b" ")
    return out


class TestShapefile(unittest.TestCase):
    """El lector de shapefile con solo stdlib (R14): sin GDAL ni pyshp."""

    def test_lee_puntos_y_atributos(self):
        import shapefile
        shp = _shp_de_puntos([(-75.78, 5.23), (-75.79, 5.24)])
        dbf = _dbf([("Main_Dmg", "C", 16), ("SensorDate", "C", 8)],
                   [("Damage", "20260812"), ("Possible Damage", "20260812")])
        feats = shapefile.leer(shp, dbf)
        self.assertEqual(len(feats), 2)
        self.assertEqual(feats[0]["geometry"]["type"], "Point")
        # GeoJSON exige [lon, lat] en ese orden: invertirlo pone Colombia en Kenia
        self.assertAlmostEqual(feats[0]["geometry"]["coordinates"][0], -75.78)
        self.assertAlmostEqual(feats[0]["geometry"]["coordinates"][1], 5.23)
        self.assertEqual(feats[0]["properties"]["Main_Dmg"], "Damage")

    def test_celda_vacia_es_none_nunca_cero(self):
        """R3 en el dbf: una celda numérica vacía es ausencia, no un cero."""
        import shapefile
        shp = _shp_de_puntos([(-75.0, 5.0)])
        dbf = _dbf([("Area_m2", "N", 10), ("Notes", "C", 10)],
                   [("", "")])
        feats = shapefile.leer(shp, dbf)
        self.assertIsNone(feats[0]["properties"]["Area_m2"])
        self.assertIsNone(feats[0]["properties"]["Notes"])

    def test_relleno_de_nulos_no_es_texto(self):
        """ArcGIS rellena celdas con \\x00: eso es vacío, no una cadena."""
        import shapefile
        shp = _shp_de_puntos([(-75.0, 5.0)])
        dbf = _dbf([("ImageID_Nu", "C", 8)], [("",)])
        crudo = bytearray(dbf)
        crudo[-8:] = b"\x00" * 8
        feats = shapefile.leer(shp, bytes(crudo))
        self.assertIsNone(feats[0]["properties"]["ImageID_Nu"])

    def test_proyectado_se_rechaza(self):
        """Un .prj no geográfico daría coordenadas absurdas sin fallar."""
        import shapefile
        self.assertTrue(shapefile.es_geografico('GEOGCS["GCS_WGS_1984",…]'))
        self.assertFalse(shapefile.es_geografico('PROJCS["WGS_1984_UTM_18N",…]'))

    def test_no_es_shapefile(self):
        import shapefile
        with self.assertRaises(ValueError):
            shapefile.read_shp(b"esto no es un shapefile" * 10)


class TestUnosat(unittest.TestCase):
    """Reglas propias de la fuente UNOSAT."""

    def test_anserma_no_es_ansermanuevo(self):
        """R10 en los nombres de fichero: «Anserma» es prefijo de
        «Ansermanuevo», que es otro municipio y de otro departamento."""
        from sources import unosat
        self.assertEqual(
            unosat._municipio_de_capa("PHR_20260812_BuildingDamage_Anserma"),
            "Anserma")
        self.assertEqual(
            unosat._municipio_de_capa("PHR_20260812_BuildingDamage_Ansermanuevo"),
            "Ansermanuevo")

    def test_municipio_desconocido_conserva_el_literal(self):
        """Viterbo no está entre los municipios que sigue el monitor: se
        mapea igual, con el nombre que da la fuente."""
        from sources import unosat
        self.assertEqual(
            unosat._municipio_de_capa("Pleiades_20260812_BuildingDamage_Viterbo"),
            "Viterbo")

    def test_alias_de_columnas(self):
        """Viterbo prefija con `d_` y Anserma no: leer por alias evita que
        media capa se quede sin grado de daño."""
        from sources import unosat
        self.assertEqual(
            unosat._campo({"d_Main_Dam": "Damage"}, "Main_Dmg", "d_Main_Dam"),
            "Damage")
        self.assertEqual(
            unosat._campo({"Main_Dmg": "Damaged"}, "Main_Dmg", "d_Main_Dam"),
            "Damaged")
        self.assertIsNone(
            unosat._campo({"Main_Dmg": ""}, "Main_Dmg", "d_Main_Dam"))

    def test_departamento_del_titulo(self):
        """El dbf no trae departamento; el título del producto sí."""
        import sqlite3
        from common import SCHEMA
        from sources import unosat
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO unosat_products (product_id, glide, titulo)"
                     " VALUES (?,?,?)",
                     (4251, unosat.GLIDE, "Building Damage Assessment in "
                      "Viterbo Town, Caldas Department, Colombia"))
        self.assertEqual(unosat._departamentos_de_titulos(conn),
                         {"viterbo": "Caldas"})

    def test_el_mismo_paquete_no_duplica_edificios(self):
        """Tres productos publican el MISMO zip (idéntico sha256). El
        edificio es uno solo: la clave es el paquete, no el producto."""
        import sqlite3
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        sha = "b37d2d78" * 8
        for productos in ("4251", "4251,4252", "4251,4252,4253"):
            conn.execute(
                "INSERT INTO unosat_damage (paquete_sha, capa, idx, productos,"
                " municipio, snapshot_date) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(paquete_sha, capa, idx) DO UPDATE SET"
                " productos=excluded.productos",
                (sha, "Pleiades_20260812_BuildingDamage_Viterbo", 0, productos,
                 "Viterbo", "2026-08-19"))
        filas = conn.execute("SELECT productos FROM unosat_damage").fetchall()
        self.assertEqual(len(filas), 1, "el mismo edificio se ha duplicado")
        self.assertEqual(filas[0][0], "4251,4252,4253")


class TestAlertaInstitucional(unittest.TestCase):
    """El producto de UNOSAT entraba en la cronología sin avisar a nadie."""

    def test_emisor_se_reconoce_en_el_titulo(self):
        import alerts
        self.assertEqual(
            alerts._emisor("M7.4 in Colombia - UNITAR-UNOSAT Activation"),
            "UNITAR-UNOSAT")
        self.assertEqual(
            alerts._emisor("M7.4 in Colombia - EC/ECHO daily map"), "EC/ECHO")
        self.assertEqual(alerts._emisor("otra cosa"), "Una fuente institucional")

    def test_sin_captura_previa_no_alerta(self):
        """En la primera corrida todo sería «nuevo»: siete avisos de golpe no
        informan de nada."""
        import alerts
        self.assertEqual(alerts._institucionales_nuevos("1970-01-01"), [])


class TestUnosatEnLaCapaDeMunicipios(unittest.TestCase):
    """UNOSAT cuenta como verificación satelital, con etiqueta propia.

    Decidido el 19-ago-2026: sus municipios dejan de figurar como «nadie los ha
    mirado desde fuera», pero NO se funden con Copernicus — sus puntos son
    fotointerpretación que la propia ONU marca sin validar en campo, no
    estadísticas revisadas por AOI.
    """

    UNOSAT_VITERBO = {"Viterbo": {"edificios": 154, "observados": 55,
                                  "posibles": 99, "fecha_imagen": "20260812"}}

    def test_solo_con_satelite_el_municipio_entra(self):
        """Viterbo no tiene prensa, ni DYFI, ni una fila en el RUD: sin esta
        vía se quedaría fuera de la capa pese a tener 154 edificios evaluados."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None,
                                   self.UNOSAT_VITERBO)
        vit = next(r for r in rows if r["municipio"] == "Viterbo")
        self.assertEqual(vit["estado"], "evaluado_unosat")
        self.assertEqual(vit["fuentes"], ["unosat"])
        self.assertEqual(vit["unosat_edificios"], 154)
        self.assertEqual(vit["unosat_observados"], 55)
        self.assertFalse(vit["en_aoi_copernicus"])

    def test_sin_evaluacion_no_hay_ceros(self):
        """R3: un municipio que UNOSAT no ha mirado no tiene 0 edificios —
        tiene ausencia de dato. Un 0 se leería como «miró y no vio nada»."""
        from municipios import build_municipios
        rows, _ = build_municipios([
            {"titulo": "Armenia reporta afectaciones", "medio": "m"}
        ], None, {}, None, None, None, self.UNOSAT_VITERBO)
        armenia = next(r for r in rows if r["municipio"] == "Armenia")
        self.assertIsNone(armenia["unosat_edificios"])
        self.assertIsNone(armenia["unosat_observados"])
        self.assertNotIn("unosat", armenia["fuentes"])

    def test_copernicus_manda_sobre_unosat(self):
        """Si el municipio ya está en una zona de Copernicus, ese estado gana:
        es la evidencia más fuerte y la cascada no debe degradarla."""
        from municipios import build_municipios
        # cuadro que contiene a Viterbo (5.0627, -75.8706)
        aoi = {"z": "POLYGON ((-76 5, -75.5 5, -75.5 5.2, -76 5.2, -76 5))"}
        rows, _ = build_municipios([], None, aoi, None, None, None,
                                   self.UNOSAT_VITERBO)
        vit = next(r for r in rows if r["municipio"] == "Viterbo")
        self.assertTrue(vit["en_aoi_copernicus"])
        self.assertEqual(vit["estado"], "en_aoi")
        self.assertEqual(vit["unosat_edificios"], 154,
                         "el conteo de UNOSAT se conserva aunque no dé el estado")


class TestToponimoViterbo(unittest.TestCase):
    """Viterbo entró el 19-ago-2026 y trae dos trampas de topónimo a la vez."""

    def test_viterbo_a_secas_no_es_prensa(self):
        """Es una ciudad italiana: la única mención del corpus es un titular
        en italiano que la llama «l'altra Viterbo». Sin «Caldas», no cuenta."""
        from municipios import MUNICIPIOS, _menciona_municipio
        meta = MUNICIPIOS["Viterbo"]
        self.assertFalse(_menciona_municipio(
            "Terremoto in Colombia, nell'altra Viterbo 29 feriti", meta))
        self.assertTrue(_menciona_municipio(
            "Viterbo, Caldas: 154 edificios evaluados", meta))

    def test_santa_rosa_de_viterbo_no_es_viterbo(self):
        """«Santa Rosa de Viterbo» es de Boyacá y contiene el topónimo
        entero: el límite de palabra no basta aquí (R10)."""
        from municipios import MUNICIPIOS, _menciona_municipio
        meta = MUNICIPIOS["Viterbo"]
        self.assertFalse(_menciona_municipio(
            "Santa Rosa de Viterbo estrena acueducto", meta))


class TestUnosatPaqueteVigente(unittest.TestCase):
    """Solo se publica el paquete vigente, aunque la tabla acumule varios.

    Lo cazó el archivista el 19-ago: la clave del dato incluye el sha del
    paquete, así que un ZIP recomprimido por UNOSAT entra como filas NUEVAS,
    no como actualización. Sin filtrar, el mapa pasaría de 393 puntos a 786 y
    la tabla daría Viterbo 308 — en silencio.
    """

    def _bd(self):
        import sqlite3
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        return conn

    def _paquete(self, conn, sha, creado, pid, n=3, municipio="Viterbo"):
        from sources.unosat import GLIDE
        conn.execute("INSERT INTO unosat_products (product_id, glide, created_at,"
                     " shp_sha256) VALUES (?,?,?,?)", (pid, GLIDE, creado, sha))
        for i in range(n):
            conn.execute(
                "INSERT INTO unosat_damage (paquete_sha, capa, idx, municipio,"
                " dano, event_code, lat, lon, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (sha, "capa", i, municipio, "Damage", GLIDE, 5.0, -75.8,
                 "2026-08-19"))

    def test_un_zip_recomprimido_no_duplica_lo_publicado(self):
        from sources import unosat
        conn = self._bd()
        self._paquete(conn, "sha_v1", "2026-08-14T00:00:00Z", 4251)
        self._paquete(conn, "sha_v2", "2026-08-20T00:00:00Z", 4254)
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM unosat_damage").fetchone()[0], 6,
            "la tabla debe ACUMULAR los dos paquetes: ahí está el histórico")
        self.assertEqual(unosat.paquete_vigente(conn), "sha_v2",
                         "el vigente es el del producto más reciente")
        self.assertEqual(unosat.resumen(conn), {"Viterbo": {"Damage": 3}},
                         "se publica un paquete, no la suma de los dos")

    def test_sin_ningun_paquete_no_se_publica_nada(self):
        from sources import unosat
        conn = self._bd()
        self.assertIsNone(unosat.paquete_vigente(conn))


class TestUnosatCentinelaNone(unittest.TestCase):
    """UNOSAT escribe el string 'None' cuando un producto no tiene un fichero.

    Es truthy, así que el guard ingenuo fabricaba
    `…/unosat_filesystem/4250/None`: una URL a un fichero inexistente, y
    justo para el producto del epicentro. R3 en la capa de enlaces — la
    ausencia declarada por la fuente convertida en afirmación positiva.
    """

    def test_el_literal_none_es_ausencia(self):
        from sources.unosat import _nombre_real
        for v in (None, "", "None", "none", "null", "  None  "):
            self.assertIsNone(_nombre_real(v), f"{v!r} debería ser ausencia")
        self.assertEqual(_nombre_real("informe.pdf"), "informe.pdf")

    def test_no_se_fabrica_url_a_un_fichero_inexistente(self):
        from sources.unosat import _abs
        self.assertIsNone(_abs("/unosat_filesystem/4253/None"))
        self.assertEqual(_abs("/unosat_filesystem/4253/tabla.xlsx"),
                         "https://unosat.org/unosat_filesystem/4253/tabla.xlsx")


class TestUnosatOtrosEventos(unittest.TestCase):
    """8 puntos de Manizales llegan etiquetados con OTRO evento.

    `EQ20260822COL` está fechado el 22-ago: doce días después de la imagen que
    los detecta. No se corrigen —la etiqueta es de la fuente— pero no pueden
    sumarse al terremoto ni desaparecer sin dejar rastro.
    """

    def test_no_suman_al_terremoto_pero_se_cuentan_aparte(self):
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None, {
            "Manizales": {"edificios": 127, "observados": 20, "posibles": 107,
                          "otros_eventos": 8, "fecha_imagen": "20260811"}})
        man = next(r for r in rows if r["municipio"] == "Manizales")
        self.assertEqual(man["unosat_edificios"], 127)
        self.assertEqual(man["unosat_observados"] + man["unosat_posibles"], 127)
        self.assertEqual(man["unosat_otros_eventos"], 8)

    def test_sin_discrepancia_el_campo_no_existe(self):
        """R3: cero edificios de otro evento no es un dato que enseñar."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None, {
            "Viterbo": {"edificios": 154, "observados": 55, "posibles": 99,
                        "otros_eventos": 0, "fecha_imagen": "20260812"}})
        vit = next(r for r in rows if r["municipio"] == "Viterbo")
        self.assertIsNone(vit["unosat_otros_eventos"])
