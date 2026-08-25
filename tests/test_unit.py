"""Tests unitarios (offline): la lógica pura del pipeline.

Se ejecutan sin red y sin base de datos previa. Las expectativas vienen de la
documentación del proyecto y de las specs de las fuentes, no de mirar la
salida del código — si un test falla, el código está mal, no el test.
"""
import json
import re
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
    def test_el_reporte_se_publica_donde_la_fuente_lo_registro(self):
        """R5 desde el 24-ago-2026. Antes esto exigía lo contrario.

        Redondear a ~110 m no protegía —ChatMap publica la coordenada exacta en
        su endpoint abierto— y movía la foto de daño a la casa de enfrente: la
        mediana de los 542 reportes estaba a 43 m de donde se tomó, y 199 a más
        de 50. Mover un punto es afirmar que el daño estaba donde no estaba."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from chatmap import _coordenada_publica
        for v in (3.9099751234, -76.55279292639023, 0.0, -0.000001):
            self.assertEqual(_coordenada_publica(v), v,
                             "la coordenada se publicó movida de sitio")


class TestSerieChatMap(unittest.TestCase):
    def test_los_dias_cerrados_sin_reportes_son_cero(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from chatmap import conteos_por_dia
        feats = [
            {"properties": {"time": "2026-08-10T13:00:00Z"}},
            {"properties": {"time": "2026-08-17T09:00:00Z"}},
        ]
        serie = conteos_por_dia(feats, "2026-08-20")
        self.assertEqual(serie["2026-08-16"], 0)
        self.assertEqual(serie["2026-08-19"], 0)
        self.assertNotIn("2026-08-20", serie,
                         "el día de la captura sigue abierto y no puede cerrarse en cero")


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

    def test_municipio_dinamico_tolera_puntuacion_del_divipola(self):
        """El RUD omite el guion de Sotará; no por eso puede caer del mapa."""
        from municipios import build_municipios
        rud = {("cauca", "sotara paispamba"): {
            "departamento": "CAUCA", "municipio": "SOTARÁ PAISPAMBA",
            "familias": 3, "personas": 9,
            "viv_destruidas": 0, "viv_averiadas": 1}}
        divipola = {"sotara - paispamba|cauca": {
            "municipio": "SOTARÁ - PAISPAMBA", "departamento": "CAUCA",
            "divipola": "19760", "lat": 2.253156, "lon": -76.613365}}
        poblacion = {"sotara paispamba|cauca": {
            "divipola": "19760", "poblacion_2026": 14806,
            "cabecera_2026": 405, "rural_2026": 14401}}
        rows, gj = build_municipios(
            [], None, {}, poblacion, rud, divipola)
        sotara = next(r for r in rows if r["municipio"] == "Sotará Paispamba")
        self.assertEqual((sotara["lat"], sotara["lon"]),
                         (2.253156, -76.613365))
        self.assertEqual(sotara["divipola"], "19760")
        self.assertIn("Sotará Paispamba",
                      [f["properties"]["municipio"] for f in gj["features"]])

    def test_poblacion_dane_por_divipola_tras_renombre(self):
        """DANE dice Mariquita y DIVIPOLA/RUD usan el nombre nuevo."""
        from municipios import build_municipios
        rud = {("tolima", "san sebastian de mariquita"): {
            "departamento": "TOLIMA",
            "municipio": "SAN SEBASTIÁN DE MARIQUITA",
            "familias": 4, "personas": 11,
            "viv_destruidas": 0, "viv_averiadas": 2}}
        divipola = {"san sebastian de mariquita|tolima": {
            "municipio": "SAN SEBASTIÁN DE MARIQUITA",
            "departamento": "TOLIMA", "divipola": "73443",
            "lat": 5.199708, "lon": -74.889276}}
        poblacion = {"mariquita|tolima": {
            "municipio": "Mariquita", "departamento": "Tolima",
            "divipola": "73443", "poblacion_2026": 40644,
            "cabecera_2026": 29925, "rural_2026": 10719}}
        rows, _ = build_municipios([], None, {}, poblacion, rud, divipola)
        mariquita = next(
            r for r in rows if r["municipio"] == "San Sebastián de Mariquita")
        self.assertEqual(mariquita["divipola"], "73443")
        self.assertEqual(mariquita["poblacion_2026"], 40644)

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


class TestNombreASecasCongelado(unittest.TestCase):
    """La identidad de una ficha no la decide quién tiene más damnificados.

    El nombre a secas de dos homónimos se repartía al PRIMERO de las filas del
    RUD, que llegan ordenadas por familias descendente: «Argelia» era la del
    Valle porque tenía más damnificados. Bastaba con que entrara un homónimo
    nuevo con más familias para que se llevara la URL ya publicada —y con ella
    el identificador del feed que archiva sus titulares—. `municipios.py`
    congela la asignación publicada; lo que la tabla no anota se reparte como
    siempre, y el test de supuesto avisa.
    """

    DIVIPOLA = {
        "argelia|cauca": {"municipio": "ARGELIA", "departamento": "CAUCA",
                          "divipola": "19050", "lat": 2.25, "lon": -77.0},
        "argelia|valle del cauca": {
            "municipio": "ARGELIA", "departamento": "VALLE DEL CAUCA",
            "divipola": "76054", "lat": 4.72, "lon": -76.11},
        "guaduas|cundinamarca": {
            "municipio": "GUADUAS", "departamento": "CUNDINAMARCA",
            "divipola": "25320", "lat": 5.07, "lon": -74.59},
        "guaduas|tolima": {"municipio": "GUADUAS", "departamento": "TOLIMA",
                           "divipola": "73999", "lat": 4.0, "lon": -75.0},
    }

    @staticmethod
    def _fila(dep, mun, familias):
        return ((dep.lower(), mun.lower()),
                {"departamento": dep, "municipio": mun, "familias": familias,
                 "personas": familias * 3, "viv_destruidas": 0,
                 "viv_averiadas": 1})

    def _rud(self, *filas):
        """Las filas en el orden en que las lee el RUD: familias descendente."""
        return dict(sorted((self._fila(*f) for f in filas),
                           key=lambda kv: -kv[1]["familias"]))

    def test_el_homonimo_nuevo_no_le_quita_la_url_al_publicado(self):
        from municipios import municipios_dinamicos
        # la del Cauca duplica hoy a la del Valle en damnificados y encabeza
        # las filas: con el reparto por orden se habría llevado /municipio/argelia/
        extras = municipios_dinamicos(
            self._rud(("CAUCA", "ARGELIA", 1800),
                      ("VALLE DEL CAUCA", "ARGELIA", 851)),
            self.DIVIPOLA)
        self.assertEqual(extras["Argelia"]["divipola"], "76054",
                         "«Argelia» a secas es la publicada (Valle del Cauca) "
                         f"desde el 18-ago-2026, gane quien gane: {extras}")
        self.assertEqual(extras["Argelia (Cauca)"]["divipola"], "19050")

    def test_la_tabla_no_decide_quien_entra_sino_quien_lleva_parentesis(self):
        """La degradación segura es «paréntesis», nunca «desaparece»."""
        from municipios import municipios_dinamicos
        extras = municipios_dinamicos(
            self._rud(("CAUCA", "ARGELIA", 1800),
                      ("VALLE DEL CAUCA", "ARGELIA", 851)),
            self.DIVIPOLA)
        self.assertEqual(sorted(extras), ["Argelia", "Argelia (Cauca)"])
        for meta in extras.values():   # las dos fichas, con su punto en el mapa
            self.assertIsNotNone(meta["lat"])

    def test_el_nombre_sin_anotar_se_reparte_como_siempre(self):
        """Sin entrada en la tabla no se rompe nada: gana el primero, como
        antes, y el supuesto de `test_hipotesis` pide anotarlo."""
        from municipios import municipios_dinamicos, NOMBRE_A_SECAS_CONGELADO
        self.assertNotIn("Guaduas", NOMBRE_A_SECAS_CONGELADO)
        extras = municipios_dinamicos(
            self._rud(("TOLIMA", "GUADUAS", 90),
                      ("CUNDINAMARCA", "GUADUAS", 10)),
            self.DIVIPOLA)
        self.assertEqual(extras["Guaduas"]["divipola"], "73999")
        self.assertIn("Guaduas (Cundinamarca)", extras)

    def test_sin_codigo_resuelto_desempata_el_departamento(self):
        """Un municipio que el catálogo geográfico escribe de otra manera se
        queda sin código. Su nombre no puede quedar a subasta por eso: el
        departamento, que el RUD siempre trae, sigue distinguiéndolos."""
        from municipios import municipios_dinamicos
        extras = municipios_dinamicos(
            self._rud(("CAUCA", "ARGELIA", 1800),
                      ("VALLE DEL CAUCA", "ARGELIA", 851)),
            None)                      # sin catálogo geográfico: cero códigos
        self.assertEqual(extras["Argelia"]["departamento"], "Valle del Cauca",
                         f"el desempate por departamento no actuó: {extras}")
        self.assertIn("Argelia (Cauca)", extras)


class TestFeedsComunitarios(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Sismo en Quibd\xc3\xb3 deja da\xc3\xb1os</title>
        <link>https://x.co/1</link><pubDate>Fri, 15 Aug 2026 10:00:00 GMT</pubDate></item>
      <item><title>Sin enlace</title></item>
    </channel></rss>"""
    ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Replica del terremoto</title>
        <link href="https://x.co/2"/><updated>2026-08-15T11:00:00Z</updated>
        <source><title>El Espectador</title></source></entry></feed>"""
    # Un feed de Google News tal cual llega: el <link> apunta al agregador y el
    # medio real solo consta en <source>.
    RSS_GOOGLE = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Temblor en Palmira - EL PA\xc3\x8dS</title>
        <link>https://news.google.com/rss/articles/CBMiabc</link>
        <pubDate>Fri, 15 Aug 2026 10:00:00 GMT</pubDate>
        <source url="https://elpais.com">EL PA\xc3\x8dS</source></item>
      <item><title>Sismo sin fuente declarada</title>
        <link>https://news.google.com/rss/articles/CBMidef</link></item>
    </channel></rss>"""

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

    def test_source_da_el_medio_real(self):
        """El <link> de Google News no lleva al medio; <source> sí lo nombra.
        Es el único sitio del feed donde la cabecera viaja limpia."""
        from community_feeds import parse_rss
        it = parse_rss(self.RSS_GOOGLE)[0]
        self.assertEqual(it["medio_canonico"], "EL PAÍS")
        self.assertEqual(it["medio_dominio"], "elpais.com")

    def test_sin_source_es_none_jamas_cadena_vacia(self):
        """R3 en el frontend igual que en las cifras: la ausencia de dato se
        dice con NULL. Un "" se colaría en un recuento de medios distintos."""
        from community_feeds import parse_rss
        sin = parse_rss(self.RSS_GOOGLE)[1]
        self.assertIsNone(sin["medio_canonico"])
        self.assertIsNone(sin["medio_dominio"])
        propio = parse_rss(self.RSS)[0]       # feed propio: no emite <source>
        self.assertIsNone(propio["medio_canonico"])

    def test_atom_tambien_declara_su_fuente(self):
        from community_feeds import parse_rss
        self.assertEqual(parse_rss(self.ATOM)[0]["medio_canonico"], "El Espectador")

    def test_dominio_normaliza_y_no_inventa(self):
        from community_feeds import dominio
        self.assertEqual(dominio("https://www.eltiempo.com/algo"), "eltiempo.com")
        self.assertEqual(dominio("https://ELPAIS.com"), "elpais.com")
        for basura in ("", "no-soy-una-url", "mailto:x@y.co"):
            self.assertIsNone(dominio(basura), f"{basura!r} no tiene host")

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

    # Catálogo DIVIPOLA mínimo: municipios reales del RUD y los nombres de
    # departamento con los que se detecta un homónimo.
    DIVIPOLA_FIXTURE = {
        "aguadas|caldas": {"municipio": "AGUADAS", "departamento": "CALDAS",
                           "divipola": "17013", "lat": 5.61, "lon": -75.45},
        "bolivar|cauca": {"municipio": "BOLÍVAR", "departamento": "CAUCA",
                          "divipola": "19100", "lat": 1.84, "lon": -76.96},
        # el homónimo se detecta contra los nombres de departamento que trae
        # el propio catálogo geográfico: sin esta fila, «Bolívar» pasaría
        "cartagena|bolivar": {"municipio": "CARTAGENA", "departamento": "BOLÍVAR",
                              "divipola": "13001", "lat": 10.39, "lon": -75.51},
    }

    def _catalogo(self, *filas):
        """El catálogo completo (curados + RUD) a partir de filas del RUD."""
        from municipios import catalogo_municipios, _norm
        rud = {(_norm(dep), _norm(mun)): {"departamento": dep, "municipio": mun}
               for dep, mun in filas}
        return catalogo_municipios(rud, self.DIVIPOLA_FIXTURE)

    def test_la_busqueda_se_deriva_del_catalogo_completo_no_del_curado(self):
        """El monitor publicaba «ni un titular» de 126 municipios a los que
        nunca preguntó: los que abre el RUD no estaban en la lista de
        búsquedas. Si esto vuelve a recorrer solo MUNICIPIOS, cae."""
        from community_feeds import municipal_google_news_feeds
        from municipios import MUNICIPIOS
        self.assertNotIn("Aguadas", MUNICIPIOS, "el fixture perdió sentido: "
                         "Aguadas ya está curado y no prueba la derivación")
        feeds = municipal_google_news_feeds(self._catalogo(("CALDAS", "AGUADAS")))
        aguadas = [f for f in feeds if f["municipio"] == "Aguadas"]
        self.assertEqual(len(aguadas), 1,
                         "un municipio que abre el RUD se queda sin búsqueda")
        self.assertIn("%22aguadas%22", aguadas[0]["url"])
        self.assertIn("%22caldas%22", aguadas[0]["url"])

    def test_el_municipio_dinamico_sin_toponimo_no_genera_consulta(self):
        """M10: si no se puede preguntar, no se pregunta. Una consulta sin
        frase (`"" "caldas"`) traería los titulares del departamento entero y el
        feed los atribuiría a un municipio, porque publish.py cree al feed."""
        from community_feeds import municipal_google_news_feeds, motivo_sin_busqueda
        catalogo = self._catalogo(("CALDAS", "AGUADAS"))
        catalogo["Aguadas"]["toponimos"] = []
        self.assertEqual(motivo_sin_busqueda(catalogo["Aguadas"]), "sin topónimo")
        self.assertEqual([f for f in municipal_google_news_feeds(catalogo)
                          if f["municipio"] == "Aguadas"], [])

    def test_el_municipio_dinamico_homonimo_de_departamento_no_genera_consulta(self):
        """Bolívar (Cauca) llega por el RUD sin que nadie lo cure: la marca de
        homónimo tiene que nacer con él, o `"bolivar" "cauca"` traería los
        titulares del departamento de Bolívar atribuidos a un municipio."""
        from community_feeds import municipal_google_news_feeds
        catalogo = self._catalogo(("CAUCA", "BOLÍVAR"))
        # la clave lleva el departamento porque el nombre a secas está
        # congelado para el Bolívar del Valle del Cauca, que es el publicado
        self.assertTrue(catalogo["Bolívar (Cauca)"]["homonimo_de_departamento"])
        declarados = {m for f in municipal_google_news_feeds(catalogo)
                      for m in (f.get("municipios") or [])}
        self.assertNotIn("Bolívar (Cauca)", declarados)
        self.assertNotIn("Bolívar", declarados)

    def test_el_toponimo_de_catalogo_administrativo_no_genera_consulta(self):
        """«sotara - paispamba» es como lo escribe el registro, no como lo
        escribe un titular: la búsqueda devolvería cero para siempre y nadie
        sabría por qué. Es la misma trampa que las claves con paréntesis."""
        from community_feeds import municipal_google_news_feeds, motivo_sin_busqueda
        catalogo = self._catalogo(("CALDAS", "AGUADAS"))
        catalogo["Aguadas"]["toponimos"] = ["sotara - paispamba"]
        self.assertIn("no buscable", motivo_sin_busqueda(catalogo["Aguadas"]) or "")
        self.assertEqual([f for f in municipal_google_news_feeds(catalogo)
                          if f["municipio"] == "Aguadas"], [])
        # la coma sí es contexto real de prensa («San José, Caldas»)
        catalogo["Aguadas"]["toponimos"] = ["san jose, caldas"]
        self.assertIsNone(motivo_sin_busqueda(catalogo["Aguadas"]))

    def test_los_municipios_sin_busqueda_se_cuentan_con_su_motivo(self):
        """Un hueco declarado no es un hueco callado: la corrida dice cuántos
        municipios no pudo preguntar y por qué."""
        from community_feeds import municipios_sin_busqueda
        sin = municipios_sin_busqueda(self._catalogo(("CAUCA", "BOLÍVAR")))
        self.assertEqual(sin.get("Bolívar (Cauca)"), "homónimo de departamento")
        self.assertNotIn("Armenia", sin)

    def test_el_catalogo_se_entrega_en_copia_y_no_reescribe_el_curado(self):
        """`MUNICIPIOS` es un literal del módulo: si el catálogo devolviera
        las mismas fichas, anotar una en el llamante reescribiría el catálogo
        curado para el resto del proceso y el fallo saldría en otro sitio."""
        from municipios import MUNICIPIOS, catalogo_municipios
        antes = dict(MUNICIPIOS["Armenia"])
        catalogo_municipios()["Armenia"]["toponimos"] = ["destrozado"]
        self.assertEqual(MUNICIPIOS["Armenia"], antes)

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


class TestPeticionesCondicionales(unittest.TestCase):
    """Preguntar sin descargar, y no archivar dos veces lo mismo.

    Medido el 24-ago-2026 sobre las 4.277 filas del log: de 283 URLs pedidas
    más de una vez, 164 devuelven SIEMPRE el mismo contenido. Las 16 capas de
    Copernicus se habían descargado 128 veces para entregar 16 cuerpos
    distintos. Lo que estos tests vigilan no es el ahorro —eso lo cuenta el
    log— sino las tres cosas que el ahorro no puede costar: que una petición
    deje de constar, que un cuerpo deje de ser recuperable, y que una URL que
    SÍ cambia deje de archivarse.
    """

    class Cabeceras(dict):
        """Las cabeceras de una respuesta, con el `.get` que usa urllib."""

    class Resp:
        def __init__(self, body, headers=None, status=200):
            self.status, self._b = status, body
            self.headers = headers if headers is not None else {}

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _no_modificado(self, headers=None):
        import urllib.error
        return urllib.error.HTTPError(
            "https://x/f", 304, "Not Modified", headers or {}, None)

    def _escenario(self, tmp, *, cuerpo=b'{"capa":1}', etag='"v1"',
                   last_mod="Sat, 15 Aug 2026 16:21:23 GMT", dia="2026-08-15"):
        """Archivo con una copia previa de https://x/f y su fila en el log.

        Devuelve (conn, ruta_relativa, sha256).
        """
        import hashlib
        import sqlite3
        import common
        conn = sqlite3.connect(":memory:")
        conn.executescript(common.SCHEMA)
        d = tmp / "snapshots" / dia
        d.mkdir(parents=True, exist_ok=True)
        (d / "capa.json").write_bytes(cuerpo)
        rel = f"snapshots/{dia}/capa.json"
        sha = hashlib.sha256(cuerpo).hexdigest()
        conn.execute(
            "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
            " snapshot_path,note,etag,last_modified)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (f"{dia}T10:30:00Z", "https://x/f", 200, sha, len(cuerpo), rel,
             "capa", etag, last_mod))
        return conn, rel, sha

    def _parche(self, tmp):
        from unittest import mock
        import common
        return (mock.patch.object(common, "ROOT", tmp),
                mock.patch.object(common, "SNAPSHOTS", tmp / "snapshots"))

    # --- lo que más preocupa: un 304 NO puede dejar de constar --------------

    def test_un_304_deja_su_fila_en_sources_log(self):
        """R4 no admite excepciones: preguntar es una petición aunque no venga
        cuerpo. Si un 304 no dejara fila, el log diría que ese día no se
        preguntó — y «no preguntamos» y «preguntamos y contestó que lo mismo»
        son hechos distintos sobre la fuente."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            antes = conn.execute("SELECT COUNT(*) FROM sources_log").fetchone()[0]
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=self._no_modificado()):
                common.fetch("https://x/f", snapshot_name="capa.json", conn=conn)
            filas = conn.execute(
                "SELECT http_status, sha256, bytes, snapshot_path FROM"
                " sources_log ORDER BY id").fetchall()
            self.assertEqual(len(filas), antes + 1,
                             "un 304 sin fila borra del archivo la prueba de "
                             "que ese día se preguntó")
            self.assertEqual(
                filas[-1], (304, sha, 0, rel),
                "la fila del 304 dice: cero bytes descargados y el cuerpo "
                "vigente es el que ya teníamos")
            conn.close()

    def test_el_304_devuelve_el_cuerpo_vigente_al_que_lo_pidio(self):
        """`copernicus_layers` reconstruye las capas públicas con el cuerpo de
        cada respuesta y hace `if not gj: continue`. Si un 304 llegara vacío,
        el día que la fuente dijera «sin cambios» el mapa perdería las 16
        capas — un ahorro que borra datos publicados no es un ahorro."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=self._no_modificado()):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            self.assertEqual((st, body), (200, b'{"capa":1}'))
            conn.close()

    def test_un_304_no_escribe_un_fichero_nuevo(self):
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=self._no_modificado()):
                common.fetch("https://x/f", snapshot_name="capa.json", conn=conn)
            hoy = tmp / "snapshots" / common.today()
            cuerpos = [f.name for f in hoy.iterdir()
                       if f.name != common.REUTILIZADOS] if hoy.exists() else []
            self.assertEqual(cuerpos, [], "un 304 no trae cuerpo que archivar")
            conn.close()

    def test_se_pregunta_con_el_validador_que_dijo_la_fuente(self):
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            vistas = {}

            def espia(req, **kw):
                vistas.update(req.headers)
                raise self._no_modificado()

            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen", side_effect=espia):
                common.fetch("https://x/f", snapshot_name="capa.json", conn=conn)
            # urllib capitaliza los nombres de cabecera al registrarlos
            claves = {k.lower(): v for k, v in vistas.items()}
            self.assertEqual(claves.get("if-none-match"), '"v1"')
            self.assertEqual(claves.get("if-modified-since"),
                             "Sat, 15 Aug 2026 16:21:23 GMT")
            conn.close()

    def test_no_se_pregunta_por_un_cuerpo_que_ya_no_esta(self):
        """El invariante que sostiene todo: solo se pregunta condicionalmente
        por lo que se puede devolver del archivo. Los vídeos ciudadanos viven
        en R2 y no en el repo; si se preguntara por ellos, un 304 dejaría al
        llamante sin cuerpo y al log con un sha sin nada detrás."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            (tmp / rel).unlink()            # el cuerpo ya no está en el repo
            vistas = {}

            def espia(req, **kw):
                vistas.update(req.headers)
                return self.Resp(b'{"capa":2}')

            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen", side_effect=espia):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            claves = {k.lower() for k in vistas}
            self.assertNotIn("if-none-match", claves)
            self.assertNotIn("if-modified-since", claves)
            self.assertEqual((st, body), (200, b'{"capa":2}'))
            conn.close()

    def test_un_cuerpo_alterado_en_disco_no_se_da_por_bueno(self):
        """Si el fichero archivado ya no cuadra con su sha, no se pregunta con
        su validador: se descarga entero. Reutilizar un cuerpo corrupto sería
        publicar como archivo algo que el archivo no dice."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            (tmp / rel).write_bytes(b'{"capa":"manipulada"}')
            p1, p2 = self._parche(tmp)
            with p1, p2:
                self.assertIsNone(common.copia_vigente("https://x/f", conn))
            conn.close()

    # --- un contenido idéntico no se archiva dos veces ----------------------

    def test_un_cuerpo_identico_no_se_archiva_dos_veces(self):
        """El caso de las capas de Copernicus si la fuente no soporta
        condicionales: 200 con el mismo cuerpo. Se deja de escribir una copia
        redundante; no se sobrescribe ni se migra nada."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self.Resp(b'{"capa":1}')]):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            hoy = tmp / "snapshots" / common.today()
            cuerpos = [f.name for f in hoy.iterdir()
                       if f.name != common.REUTILIZADOS] if hoy.exists() else []
            self.assertEqual(cuerpos, [],
                             "el mismo contenido archivado dos veces")
            self.assertEqual(
                conn.execute("SELECT http_status, snapshot_path FROM sources_log"
                             " ORDER BY id DESC LIMIT 1").fetchone(),
                (200, rel),
                "la fila tiene que apuntar a la copia que sí existe")
            self.assertEqual((st, body), (200, b'{"capa":1}'))
            conn.close()

    def test_una_url_que_cambia_sigue_archivandose(self):
        """La mutación que puede morder: de las 283 URLs repetidas, 119 SÍ
        cambian. Ni una puede dejar de archivarse por un fallo de comparación —
        el índice de la activación de Copernicus, que se ha pedido 346 veces y
        ha cambiado dos, es quien revela los productos nuevos."""
        import hashlib
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            nuevo = b'{"capa":1,"producto":"AOI07"}'
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self.Resp(nuevo)]):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            hoy = tmp / "snapshots" / common.today()
            self.assertTrue((hoy / "capa.json").exists(),
                            "un contenido nuevo TIENE que archivarse")
            self.assertEqual((hoy / "capa.json").read_bytes(), nuevo)
            fila = conn.execute(
                "SELECT http_status, sha256, bytes, snapshot_path FROM"
                " sources_log ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(fila[0], 200)
            self.assertEqual(fila[1], hashlib.sha256(nuevo).hexdigest())
            self.assertEqual(fila[2], len(nuevo))
            self.assertNotEqual(fila[3], rel,
                                "la fila señalaría el cuerpo viejo: el "
                                "producto nuevo se habría perdido")
            self.assertEqual((st, body), (200, nuevo))
            conn.close()

    def test_dos_cuerpos_distintos_el_mismo_dia_siguen_conviviendo(self):
        """La regla intradía no la deroga la reutilización: un cuerpo distinto
        el mismo día se archiva aparte con su sufijo de contenido."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self.Resp(b'{"capa":2}'),
                                 self.Resp(b'{"capa":3}')]):
                for _ in range(2):
                    common.fetch("https://x/f", snapshot_name="capa.json",
                                 conn=conn)
            hoy = tmp / "snapshots" / common.today()
            cuerpos = sorted(f.name for f in hoy.iterdir()
                             if f.name != common.REUTILIZADOS)
            self.assertEqual(len(cuerpos), 2, cuerpos)
            self.assertIn("capa.json", cuerpos)
            conn.close()

    # --- la carpeta del día se explica sola ---------------------------------

    def test_la_carpeta_del_dia_dice_lo_que_no_contiene(self):
        """Quien abra data/snapshots/2026-08-24/ y no encuentre la capa de
        Copernicus no tiene por qué saber que existe un sqlite. Cada línea de
        `reutilizados.txt` tiene que corresponder a una fila del log."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self._no_modificado(),
                                 self._no_modificado()]):
                for _ in range(2):
                    common.fetch("https://x/f", snapshot_name="capa.json",
                                 conn=conn)
            f = tmp / "snapshots" / common.today() / common.REUTILIZADOS
            lineas = [l for l in f.read_text(encoding="utf-8").splitlines()
                      if l and not l.startswith("#")]
            self.assertEqual(lineas, [f"capa.json\t{rel}\t{sha}"],
                             "una línea por cuerpo, sin repetirse en la "
                             "segunda pasada del mismo día")
            del_log = conn.execute(
                "SELECT DISTINCT snapshot_path, sha256 FROM sources_log"
                " WHERE http_status=304").fetchall()
            self.assertEqual(del_log, [(rel, sha)],
                             "el índice de la carpeta y el log tienen que "
                             "decir lo mismo")
            conn.close()

    def test_la_carpeta_del_dia_tambien_explica_el_cuerpo_identico(self):
        """El 304 no es el único caso: cuando la fuente no soporta
        condicionales y manda 200 con lo mismo, tampoco se escribe fichero, y
        la carpeta tiene que explicarlo igual."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self.Resp(b'{"capa":1}')]):
                common.fetch("https://x/f", snapshot_name="capa.json", conn=conn)
            f = tmp / "snapshots" / common.today() / common.REUTILIZADOS
            self.assertTrue(f.exists(),
                            "la capa no está en la carpeta del día y nada lo "
                            "explica: el historiador la daría por no pedida")
            lineas = [l for l in f.read_text(encoding="utf-8").splitlines()
                      if l and not l.startswith("#")]
            self.assertEqual(lineas, [f"capa.json\t{rel}\t{sha}"])
            conn.close()

    # --- R13: una fuente que contesta raro no rompe la corrida --------------

    def test_un_304_que_nadie_pidio_no_rompe_la_corrida(self):
        """Si el servidor contesta «sin cambios» a una petición que no llevaba
        validadores, no afirma nada sobre nuestro archivo: la fila consta, se
        queda sin sha y sin ruta, y el llamante degrada."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=self._no_modificado()):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            self.assertEqual((st, body), (304, b""))
            self.assertEqual(
                conn.execute("SELECT http_status, sha256, snapshot_path FROM"
                             " sources_log ORDER BY id DESC LIMIT 1").fetchone(),
                (304, None, None),
                "un 304 que no contestaba a nuestros validadores no puede "
                "certificar que el cuerpo archivado siga vigente")
            conn.close()

    def test_una_respuesta_sin_cabeceras_no_tumba_la_descarga(self):
        """R13: lo que importa es el cuerpo. Una respuesta que no declara
        validadores —o cuyas cabeceras no se dejan leer— se archiva igual."""
        import tempfile
        from unittest import mock
        import common

        class Rota:
            status = 200

            @property
            def headers(self):
                raise RuntimeError("cabeceras ilegibles")

            def read(self):
                return b'{"capa":9}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen", side_effect=[Rota()]):
                st, body = common.fetch("https://x/f", snapshot_name="capa.json",
                                        conn=conn)
            self.assertEqual((st, body), (200, b'{"capa":9}'))
            self.assertTrue(
                (tmp / "snapshots" / common.today() / "capa.json").exists())
            conn.close()

    def test_un_validador_desmesurado_no_viaja_de_vuelta(self):
        """Un ETag de 8 KB es una fuente rara, no un motivo para mandar una
        cabecera de 8 KB en cada petición."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, rel, sha = self._escenario(tmp, etag=None, last_mod=None)
            p1, p2 = self._parche(tmp)
            with p1, p2, mock.patch.object(
                    common.urllib.request, "urlopen",
                    side_effect=[self.Resp(b'{"capa":7}',
                                           {"ETag": '"' + "x" * 9000 + '"'})]):
                common.fetch("https://x/f", snapshot_name="capa.json", conn=conn)
            guardado = conn.execute(
                "SELECT etag FROM sources_log ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            self.assertEqual(len(guardado), common.MAX_VALIDADOR)
            conn.close()

    def test_los_validadores_sobreviven_al_volcado(self):
        """La base no se versiona: se reconstruye desde data/dumps/*.csv. Si
        los validadores no viajaran en el volcado, el runner amanecería cada
        día sin con qué preguntar y volvería a descargarlo todo."""
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn = sqlite3.connect(tmp / "a.sqlite")
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                " snapshot_path,note,etag,last_modified) VALUES"
                " ('2026-08-24T10:30:00Z','https://x/f',200,'abc',12,"
                " 'data/snapshots/2026-08-24/capa.json','capa','\"v1\"',"
                " 'Sat, 15 Aug 2026 16:21:23 GMT')")
            conn.commit()
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                dump_db.dump(conn)
                conn.close()
                dump_db.rebuild(tmp / "b.sqlite")
                otra = sqlite3.connect(tmp / "b.sqlite")
                self.assertEqual(
                    otra.execute("SELECT etag, last_modified FROM sources_log"
                                 ).fetchone(),
                    ('"v1"', "Sat, 15 Aug 2026 16:21:23 GMT"))
                otra.close()
            finally:
                dump_db.DUMPS = dumps_orig

    def test_un_dump_viejo_sin_validadores_se_sigue_reconstruyendo(self):
        """Los CSV versionados hasta hoy no tienen esas columnas. `rebuild`
        inserta por nombre de columna: un volcado de ayer tiene que seguir
        levantando la base sin tocar un byte del archivo."""
        import sqlite3
        import tempfile
        import dump_db
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dumps = tmp / "dumps"
            dumps.mkdir()
            (dumps / "sources_log.csv").write_text(
                "ts,url,http_status,sha256,bytes,snapshot_path,note\n"
                "2026-08-15T16:21:23Z,https://x/f,200,abc,12,"
                "data/snapshots/2026-08-15/capa.json,capa\n",
                encoding="utf-8")
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, dumps
            try:
                dump_db.rebuild(tmp / "b.sqlite")
                otra = sqlite3.connect(tmp / "b.sqlite")
                self.assertEqual(
                    otra.execute("SELECT sha256, etag, last_modified FROM"
                                 " sources_log").fetchone(),
                    ("abc", None, None))
                otra.close()
            finally:
                dump_db.DUMPS = dumps_orig


class TestElCuerpoVigenteNoEsElDeHoy(unittest.TestCase):
    """Desde que un contenido idéntico deja de archivarse dos veces, «el
    fichero de hoy» y «el cuerpo vigente» dejaron de ser lo mismo.

    Quien lea `snapshot_dir() / x` se queda sin nada el primer día que la
    fuente no cambie — y en silencio. `crosscheck` leía así los titulares de
    GDACS: sin este arreglo, el día que el feed repitiera contenido los AOI que
    solo tienen prensa habrían retrocedido a «pendiente» sin que nada avisara.
    """

    def test_el_vigente_se_encuentra_aunque_hoy_no_haya_fichero(self):
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            snaps = Path(tmp) / "snapshots"
            (snaps / "2026-08-15").mkdir(parents=True)
            (snaps / "2026-08-15" / "gdacs_emm.json").write_text('[{"a":1}]')
            (snaps / "2026-08-16").mkdir()      # día sin ese cuerpo
            with mock.patch.object(common, "SNAPSHOTS", snaps):
                self.assertEqual(common.ultimo_snapshot("gdacs_emm.json"),
                                 snaps / "2026-08-15" / "gdacs_emm.json")
                self.assertIsNone(common.ultimo_snapshot("no_existe.json"))

    def test_los_titulares_de_gdacs_no_desaparecen_el_dia_sin_cambios(self):
        import tempfile
        from unittest import mock
        import common
        from sources import gdacs
        with tempfile.TemporaryDirectory() as tmp:
            snaps = Path(tmp) / "snapshots"
            (snaps / "2026-08-15").mkdir(parents=True)
            (snaps / "2026-08-15" / "gdacs_emm.json").write_text(
                '[{"title":"Istmina","source":"El Tiempo"}]')
            (snaps / common.today()).mkdir(exist_ok=True)
            with mock.patch.object(common, "SNAPSHOTS", snaps):
                items = gdacs.emm_items()
            self.assertEqual(len(items), 1,
                             "sin titulares, crosscheck haría retroceder el "
                             "estado de los AOI que solo tienen prensa")

    def test_la_cronologia_institucional_no_se_repite_al_reutilizar(self):
        """El reverso, y la trampa de arreglar esto sin pensar: si un día sin
        fichero se resolviera con el cuerpo vigente, la comparación «hoy contra
        la captura anterior» encontraría las MISMAS entradas nuevas cada día y
        el aviso se repetiría para siempre. Sin fichero hoy significa que el
        cuerpo no cambió, y eso es exactamente cero entradas nuevas."""
        import tempfile
        from unittest import mock
        import alerts
        with tempfile.TemporaryDirectory() as tmp:
            snaps = Path(tmp) / "snapshots"
            (snaps / "2026-08-22").mkdir(parents=True)
            (snaps / "2026-08-22" / "gdacs_news_institucional.json").write_text(
                '[{"link":"https://a","pubdate":"2026-08-22"}]')
            (snaps / "2026-08-23").mkdir()
            (snaps / "2026-08-23" / "gdacs_news_institucional.json").write_text(
                '[{"link":"https://a","pubdate":"2026-08-22"},'
                ' {"link":"https://b","pubdate":"2026-08-23"}]')
            (snaps / "2026-08-24").mkdir()      # cuerpo reutilizado: sin fichero
            with mock.patch.object(alerts, "SNAPSHOTS", snaps):
                self.assertEqual(len(alerts._institucionales_nuevos("2026-08-23")), 1,
                                 "el día que sí cambió tiene que avisar")
                self.assertEqual(alerts._institucionales_nuevos("2026-08-24"), [],
                                 "el día reutilizado no trae nada nuevo: "
                                 "repetir el aviso sería anunciar dos veces "
                                 "la misma entrada")

    def test_nadie_consume_un_cuerpo_de_la_carpeta_de_hoy(self):
        """El guardián del patrón, no del caso: `snapshot_dir()` sirve para
        ESCRIBIR el snapshot del día, y eso solo lo hace `common.fetch()`.
        Cualquier otro módulo que lo use para leer un cuerpo está asumiendo que
        hoy se archivó algo, y desde hoy eso puede ser falso."""
        import re
        raiz = Path(__file__).parent.parent / "ingest"
        malos = []
        for f in sorted(raiz.rglob("*.py")):
            if f.name == "common.py":
                continue        # es quien escribe la carpeta del día
            for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"snapshot_dir\(\)\s*/", linea):
                    malos.append(f"{f.relative_to(raiz)}:{n}: {linea.strip()}")
        self.assertEqual(
            malos, [],
            "leen el cuerpo de la carpeta de hoy en vez del vigente "
            "(`common.ultimo_snapshot`): " + "; ".join(malos))


class TestAvisoDePeticionesCondicionales(unittest.TestCase):
    """R11: que una fuente empiece —o deje— de contestar 304 tiene que verse.

    Si nadie lo canta, el día que Copernicus deje de honrar los validadores el
    monitor volverá a descargar 57 MB diarios de capas que no han cambiado sin
    que nada lo diga, y el día que empiece a honrarlos nadie se enterará de la
    buena noticia.
    """

    def _conn(self):
        import sqlite3
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        return conn

    def _pedir(self, conn, url, ts, status, sha, bytes_=0, spath=None):
        conn.execute(
            "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
            " snapshot_path,note) VALUES (?,?,?,?,?,?,'capa')",
            (ts, url, status, sha, bytes_, spath))

    def test_una_fuente_que_estrena_el_304_se_canta_una_sola_vez(self):
        from alerts import cambios_en_peticiones_condicionales
        conn = self._conn()
        for i in range(16):
            u = f"https://x/capa{i}.json"
            self._pedir(conn, u, "2026-08-23T10:30:00Z", 200, "a", 2_380_000, "s/a")
            self._pedir(conn, u, "2026-08-24T10:30:00Z", 304, "a", 0, "s/a")
        avisos = cambios_en_peticiones_condicionales(conn, "2026-08-24")
        tipos = [a["tipo"] for a in avisos]
        self.assertEqual(tipos, ["fuentes_con_peticion_condicional"])
        self.assertEqual(avisos[0]["n"], 16)
        self.assertEqual(len(avisos[0]["urls"]), 10, "la alerta no lista 16")
        conn.close()

    def test_una_fuente_que_deja_de_honrarlos_se_canta_con_lo_que_cuesta(self):
        from alerts import cambios_en_peticiones_condicionales
        conn = self._conn()
        u = "https://x/capa.json"
        self._pedir(conn, u, "2026-08-22T10:30:00Z", 200, "a", 2_380_000, "s/a")
        self._pedir(conn, u, "2026-08-23T10:30:00Z", 304, "a", 0, "s/a")
        self._pedir(conn, u, "2026-08-24T10:30:00Z", 200, "a", 2_380_000, "s/a")
        avisos = cambios_en_peticiones_condicionales(conn, "2026-08-24")
        self.assertEqual([a["tipo"] for a in avisos],
                         ["fuente_deja_de_honrar_condicionales"])
        self.assertEqual(avisos[0]["bytes"], 2_380_000)
        conn.close()

    def test_una_url_que_cambia_de_verdad_no_es_una_regresion(self):
        """El falso positivo que dejaría la alerta desactivada: la fuente
        contestaba 304 porque no había cambiado; hoy manda 200 porque SÍ
        cambió. Eso es la fuente funcionando, no una regresión."""
        from alerts import cambios_en_peticiones_condicionales
        conn = self._conn()
        u = "https://x/indice.json"
        self._pedir(conn, u, "2026-08-22T10:30:00Z", 200, "a", 500, "s/a")
        self._pedir(conn, u, "2026-08-23T10:30:00Z", 304, "a", 0, "s/a")
        self._pedir(conn, u, "2026-08-24T10:30:00Z", 200, "b", 600, "s/b")
        self.assertEqual(cambios_en_peticiones_condicionales(conn, "2026-08-24"),
                         [])
        conn.close()

    def test_un_304_que_nadie_pidio_se_canta(self):
        from alerts import cambios_en_peticiones_condicionales
        conn = self._conn()
        u = "https://x/rara.json"
        self._pedir(conn, u, "2026-08-24T10:30:00Z", 304, None, 0, None)
        tipos = [a["tipo"] for a in
                 cambios_en_peticiones_condicionales(conn, "2026-08-24")]
        self.assertIn("trescientos_cuatro_sin_preguntar", tipos)
        conn.close()

    def test_un_dia_sin_novedad_no_genera_ruido(self):
        from alerts import cambios_en_peticiones_condicionales
        conn = self._conn()
        u = "https://x/capa.json"
        self._pedir(conn, u, "2026-08-23T10:30:00Z", 304, "a", 0, "s/a")
        self._pedir(conn, u, "2026-08-24T10:30:00Z", 304, "a", 0, "s/a")
        self.assertEqual(cambios_en_peticiones_condicionales(conn, "2026-08-24"),
                         [])
        conn.close()


class TestDumpSinRuidoDeRowid(unittest.TestCase):
    """Un diff diario debe contar lo que cambió, no lo que sqlite renumeró.

    `crosscheck` borra y reinserta cada día la evidencia automática, y sqlite
    reparte `id` nuevos: 27 de las 100 líneas de `evidence.csv` cambiaban de
    valor sin que cambiara un solo dato. En un repositorio que es archivo, eso
    es peor que ruido — obliga a desconfiar del diff."""

    def test_recrear_las_filas_no_mueve_el_csv(self):
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn = sqlite3.connect(tmp / "a.sqlite")
            conn.executescript(SCHEMA)

            def poblar():
                for aoi in ("Istmina", "Quibdo Centre"):
                    conn.execute(
                        "INSERT INTO evidence (aoi_name, tipo, url, fuente,"
                        " fecha, cita, capturado_por, snapshot_date) VALUES"
                        " (?,'prensa','https://x/1','El Tiempo','2026-08-16',"
                        "'titular','auto','2026-08-16')", (aoi,))
                conn.commit()

            poblar()
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                dump_db.dump(conn)
                antes = (tmp / "dumps" / "evidence.csv").read_text(encoding="utf-8")
                # la corrida siguiente: mismas filas, ids nuevos
                conn.execute("DELETE FROM evidence WHERE capturado_por='auto'")
                poblar()
                dump_db.dump(conn)
                despues = (tmp / "dumps" / "evidence.csv").read_text(encoding="utf-8")
            finally:
                dump_db.DUMPS = dumps_orig
            self.assertEqual(antes, despues,
                             "el CSV cambia sin que cambien los datos")
            self.assertNotIn("id,", antes.splitlines()[0],
                             "el alias del rowid no se vuelca")
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
            # columnas nombradas: una columna nueva no debe romper este test,
            # debe viajar en él
            origen.execute(
                "INSERT INTO news_items (url, feed_id, fecha, titulo, medio,"
                " medio_canonico, medio_dominio, snapshot_date) VALUES"
                " ('https://x/y?a=1','feed-1','2026-08-16',"
                "'Título, con \"comillas\" y\nsalto','Google News — Nóvita',"
                "'EL PAÍS','elpais.com','2026-08-16')")
            origen.execute(
                "INSERT INTO news_items (url, feed_id, medio, snapshot_date)"
                " VALUES ('https://x/z','feed-2','El Colombiano','2026-08-16')")
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


class TestDumpHistoricoRud(unittest.TestCase):
    """Una base local o una rama atrasada no pueden acortar la serie RUD."""

    @staticmethod
    def _fila(dia, municipio, familias=1.0):
        return (dia, "CHOCÓ", municipio, familias, 2.0, 0.0, 1.0, 0.0, 0.0)

    def test_rebuild_sincroniza_filas_que_faltan_en_una_bd_existente(self):
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                fuente = sqlite3.connect(tmp / "fuente.sqlite")
                fuente.executescript(SCHEMA)
                fuente.executemany(
                    "INSERT INTO rud_daily VALUES (?,?,?,?,?,?,?,?,?)",
                    [self._fila("2026-08-18", "ISTMINA"),
                     self._fila("2026-08-19", "QUIBDÓ")])
                fuente.execute(
                    "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                    "snapshot_path,note) VALUES (?,?,?,?,?,?,?)",
                    ("2026-08-19T10:45:12Z", "https://rud.example/", 200,
                     "abc", 123, "data/snapshots/rud.json", "rud 2026T"))
                fuente.commit()
                dump_db.dump(fuente)
                fuente.close()

                atrasada = sqlite3.connect(tmp / "atrasada.sqlite")
                atrasada.executescript(SCHEMA)
                atrasada.execute(
                    "INSERT INTO rud_daily VALUES (?,?,?,?,?,?,?,?,?)",
                    self._fila("2026-08-18", "ISTMINA", familias=999.0))
                atrasada.commit()
                atrasada.close()

                resultado = dump_db.rebuild(tmp / "atrasada.sqlite")
                reparada = sqlite3.connect(tmp / "atrasada.sqlite")
                fechas = [r[0] for r in reparada.execute(
                    "SELECT snapshot_date FROM rud_daily ORDER BY snapshot_date")]
                familias = reparada.execute(
                    "SELECT familias FROM rud_daily WHERE snapshot_date='2026-08-18'"
                ).fetchone()[0]
                logs = reparada.execute("SELECT COUNT(*) FROM sources_log").fetchone()[0]
                reparada.close()
                segunda = dump_db.rebuild(tmp / "atrasada.sqlite")
                comprobacion = sqlite3.connect(tmp / "atrasada.sqlite")
                logs_despues = comprobacion.execute(
                    "SELECT COUNT(*) FROM sources_log").fetchone()[0]
                comprobacion.close()
            finally:
                dump_db.DUMPS = dumps_orig
            self.assertEqual(fechas, ["2026-08-18", "2026-08-19"])
            self.assertEqual(familias, 1.0, "el dump no corrigió el valor atrasado")
            self.assertEqual(resultado["sync"]["rud_daily"], 2)
            self.assertEqual(logs, 1)
            self.assertEqual(logs_despues, 1, "la sincronización duplicó el log")
            self.assertEqual(segunda["sync"]["sources_log"], 0)

    def test_dump_rechaza_borrar_una_clave_historica(self):
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn = sqlite3.connect(tmp / "rud.sqlite")
            conn.executescript(SCHEMA)
            conn.executemany(
                "INSERT INTO rud_daily VALUES (?,?,?,?,?,?,?,?,?)",
                [self._fila("2026-08-17", "NÓVITA"),
                 self._fila("2026-08-18", "ISTMINA")])
            conn.commit()
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                dump_db.dump(conn)
                ruta = dump_db.DUMPS / "rud_daily.csv"
                antes = ruta.read_text(encoding="utf-8")
                conn.execute("DELETE FROM rud_daily WHERE snapshot_date='2026-08-18'")
                conn.commit()
                with self.assertRaisesRegex(RuntimeError, "claves históricas"):
                    dump_db.dump(conn)
                despues = ruta.read_text(encoding="utf-8")
            finally:
                dump_db.DUMPS = dumps_orig
                conn.close()
            self.assertEqual(antes, despues, "el guardián no preservó el CSV")

    def test_dump_rechaza_borrar_el_log_de_procedencia(self):
        import sqlite3
        import tempfile
        import dump_db
        from common import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn = sqlite3.connect(tmp / "rud.sqlite")
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                "snapshot_path,note) VALUES (?,?,?,?,?,?,?)",
                ("2026-08-19T10:45:12Z", "https://rud.example/", 200,
                 "abc", 123, "data/snapshots/rud.json", "rud 2026T"))
            conn.commit()
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, tmp / "dumps"
            try:
                dump_db.dump(conn)
                ruta = dump_db.DUMPS / "sources_log.csv"
                antes = ruta.read_text(encoding="utf-8")
                conn.execute("DELETE FROM sources_log")
                conn.commit()
                with self.assertRaisesRegex(RuntimeError, "sources_log"):
                    dump_db.dump(conn)
                despues = ruta.read_text(encoding="utf-8")
            finally:
                dump_db.DUMPS = dumps_orig
                conn.close()
            self.assertEqual(antes, despues, "se reescribió el log incompleto")


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

    def test_no_hay_dias_perdidos_entre_capturas(self):
        import csv
        from datetime import date, timedelta
        p = self.ROOT / "data" / "public" / "rud.json"
        serie = json.loads(p.read_text())["serie"]
        fechas = {date.fromisoformat(d["fecha"]) for d in serie}
        esperadas = {
            min(fechas) + timedelta(days=i)
            for i in range((max(fechas) - min(fechas)).days + 1)
        }
        self.assertEqual(
            fechas, esperadas,
            "la serie RUD perdió días entre capturas; restaurar desde snapshots")
        with open(self.ROOT / "data" / "dumps" / "rud_daily.csv",
                  newline="", encoding="utf-8") as f:
            fechas_dump = {
                date.fromisoformat(r["snapshot_date"])
                for r in csv.DictReader(f)
            }
        propias = {
            date.fromisoformat(d["fecha"])
            for d in serie if not d.get("reconstruido")
        }
        self.assertEqual(
            fechas_dump, propias,
            "rud.json y el detalle versionado discrepan sobre los días capturados")


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
        """La serie mediática cortaba en 2026-08-08 por su cuenta y el check de
        temporalidad ciudadana llevaba su propio 2026-08-10T12:30: el monitor
        tenía tres fechas del mismo terremoto. Una sola frontera, con nombre.

        Busca la fecha COMO LITERAL entrecomillado, que es la forma que toma un
        filtro; las que aparecen dentro de una frase son prosa de un comentario
        y no deciden nada."""
        culpables = []
        for py in (Path(__file__).parent.parent / "ingest").rglob("*.py"):
            if py.name == "common.py":
                continue          # es donde vive la frontera
            for n, linea in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"""['"]2026-08-\d\d(T[\d:]+)?['"]""", linea):
                    culpables.append(f"{py.name}:{n}: {linea.strip()[:60]}")
        self.assertEqual(culpables, [],
                         "fecha del sismo suelta en la ingesta: usar FECHA_SISMO "
                         "o INSTANTE_SISMO de common.py")

class TestBackfillMedios(unittest.TestCase):
    """El medio nunca se perdió: estaba en el archivo. Estos tests fijan que se
    recupere de ahí y que recuperarlo no toque ni un byte de lo ya capturado."""

    SNAP = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Temblor en Palmira - EL PAIS</title>
        <link>https://news.google.com/rss/articles/AAA</link>
        <source url="https://www.elpais.com.co">El Pa\xc3\xads Cali</source></item>
      <item><title>Replica en Quibdo</title>
        <link>https://news.google.com/rss/articles/BBB</link>
        <source url="https://www.eltiempo.com">El Tiempo</source></item>
      <item><title>Sin fuente declarada</title>
        <link>https://news.google.com/rss/articles/CCC</link></item>
    </channel></rss>"""

    def setUp(self):
        import sqlite3
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from common import SCHEMA
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        (raiz / "2026-08-15").mkdir()
        (raiz / "2026-08-15" / "feed_googlenews-municipio-palmira.xml").write_bytes(self.SNAP)
        self.snapshots = raiz
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        for url, medio in (("https://news.google.com/rss/articles/AAA", "Google News — Palmira"),
                           ("https://news.google.com/rss/articles/BBB", "Google News — Quibdó"),
                           ("https://news.google.com/rss/articles/CCC", "Google News — Sipí")):
            self.conn.execute(
                "INSERT INTO news_items (url, feed_id, fecha, titulo, medio,"
                " snapshot_date) VALUES (?,?,?,?,?,?)",
                (url, "googlenews-municipio-palmira", "2026-08-15T10:00:00",
                 "titular", medio, "2026-08-15"))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _run(self, **kw):
        import backfill_medios
        return backfill_medios.run(conn=self.conn, snapshots=self.snapshots, **kw)

    def _fila(self, url):
        return self.conn.execute(
            "SELECT url, medio, medio_canonico, medio_dominio FROM news_items"
            " WHERE url = ?", (url,)).fetchone()

    def test_rellena_desde_el_archivo_sin_red(self):
        r = self._run()
        self.assertEqual(r["rellenados"], 2)
        _, _, canonico, dom = self._fila("https://news.google.com/rss/articles/BBB")
        self.assertEqual(canonico, "El Tiempo")
        self.assertEqual(dom, "eltiempo.com")

    def test_la_url_capturada_no_se_toca_jamas(self):
        """R4: la URL es lo que se pidió y lo que quedó en sources_log. El
        backfill añade contexto al lado; reescribirla rompería la cadena."""
        antes = {r[0] for r in self.conn.execute("SELECT url FROM news_items")}
        self._run()
        despues = {r[0] for r in self.conn.execute("SELECT url FROM news_items")}
        self.assertEqual(antes, despues)
        self.assertTrue(all(u.startswith("https://news.google.com/") for u in despues))

    def test_el_feed_sigue_en_medio(self):
        """`medio` guarda el feed y se queda como está: es lo que se capturó."""
        self._run()
        _, medio, canonico, _ = self._fila("https://news.google.com/rss/articles/AAA")
        self.assertEqual(medio, "Google News — Palmira")
        self.assertEqual(canonico, "El País Cali")

    def test_sin_source_en_el_archivo_se_queda_sin_medio(self):
        """No hay dato que inventar: el nombre del feed no es una cabecera."""
        self._run()
        _, _, canonico, dom = self._fila("https://news.google.com/rss/articles/CCC")
        self.assertIsNone(canonico)
        self.assertIsNone(dom)

    def test_idempotente_y_sin_sobrescribir(self):
        self._run()
        self.conn.execute(
            "UPDATE news_items SET medio_canonico = 'Corregido a mano'"
            " WHERE url = 'https://news.google.com/rss/articles/BBB'")
        r = self._run()
        self.assertEqual(r["rellenados"], 0, "segunda pasada no repite trabajo")
        _, _, canonico, _ = self._fila("https://news.google.com/rss/articles/BBB")
        self.assertEqual(canonico, "Corregido a mano",
                         "un medio ya presente no se pisa")

    def test_tambien_reconstruye_desde_atom(self):
        """`parse_rss` ingiere Atom, así que la reconstrucción también debe:
        si el archivo recordara menos de lo que la ingesta supo, dejaría de ser
        un archivo fiel."""
        import backfill_medios
        (self.snapshots / "2026-08-14").mkdir()
        (self.snapshots / "2026-08-14" / "feed_atom.xml").write_bytes(
            b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
              <entry><title>t</title><link href="https://x.co/atom"/>
                <source><title>El Espectador</title>
                  <link href="https://www.elespectador.com"/></source></entry></feed>""")
        fuentes = backfill_medios.medios_archivados(self.snapshots)
        self.assertEqual(fuentes["https://x.co/atom"],
                         ("El Espectador", "elespectador.com"))

    def test_la_reconstruccion_deja_rastro_en_sources_log(self):
        """Sin fila en `sources_log`, dentro de veinte años nadie distinguiría
        un medio capturado el día del <item> de uno reconstruido después."""
        self._run()
        filas = self.conn.execute(
            "SELECT url, http_status, note FROM sources_log").fetchall()
        self.assertEqual(len(filas), 1)
        url, status, note = filas[0]
        self.assertIsNone(status, "no hubo petición: el HTTP debe quedar en NULL")
        from common import NOTA_RECONSTRUCCION, ORIGEN_ARCHIVO
        self.assertEqual(url, ORIGEN_ARCHIVO)
        self.assertIn(NOTA_RECONSTRUCCION, note)
        self.assertIn("2", note, "la nota dice cuántas noticias se rellenaron")

    def test_sin_rellenar_nada_no_ensucia_el_log(self):
        self._run()
        antes = self.conn.execute("SELECT COUNT(*) FROM sources_log").fetchone()[0]
        self._run()
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM sources_log").fetchone()[0],
            antes, "una pasada que no rellena nada no es un acontecimiento")

    def test_snapshot_corrupto_no_rompe_el_resto(self):
        """R13 a escala de fichero: un XML ilegible se salta, no aborta."""
        (self.snapshots / "2026-08-14").mkdir()
        (self.snapshots / "2026-08-14" / "feed_roto.xml").write_bytes(b"<no soy xml")
        self.assertEqual(self._run()["rellenados"], 2)


class TestRebuildDeDumpAnteriorAlEsquema(unittest.TestCase):
    """El caso que corre de verdad en el runner: los dumps versionados llevan
    las columnas del día en que se volcaron, y el esquema puede haber ganado
    alguna después. Si `rebuild` insertara por posición en vez de por nombre,
    un clon nuevo moriría al primer `git pull`."""

    def test_un_dump_sin_las_columnas_nuevas_se_reconstruye(self):
        import sqlite3
        import tempfile
        import dump_db
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dumps = tmp / "dumps"
            dumps.mkdir()
            (dumps / "news_items.csv").write_text(
                "url,feed_id,fecha,titulo,medio,snapshot_date\n"
                "https://x/y,feed-1,2026-08-16,Titular,Medio Ñandú,2026-08-16\n",
                encoding="utf-8")
            dumps_orig, dump_db.DUMPS = dump_db.DUMPS, dumps
            try:
                dump_db.rebuild(tmp / "b.sqlite")
            finally:
                dump_db.DUMPS = dumps_orig
            conn = sqlite3.connect(tmp / "b.sqlite")
            fila = conn.execute(
                "SELECT medio, medio_canonico, medio_dominio FROM news_items").fetchone()
            self.assertEqual(fila, ("Medio Ñandú", None, None),
                             "lo que el dump no traía queda en NULL, no en basura")
            conn.close()


class TestEvidenciaDePrensaSeFirmaConLaCabecera(unittest.TestCase):
    """`evidence` es el corazón de R1: una fuente de prensa llamada «Google
    News — Istmina» no nombra a nadie. Es la búsqueda que encontró la pieza,
    no quien la publicó."""

    def test_prefiere_la_cabecera_y_cae_al_feed_si_no_hay(self):
        import sqlite3
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO news_items (url, feed_id, fecha, titulo, medio,"
            " medio_canonico, snapshot_date) VALUES ('u1','f','2026-08-15',"
            "'t','Google News — Istmina','El Tiempo','2026-08-15')")
        conn.execute(
            "INSERT INTO news_items (url, feed_id, fecha, titulo, medio,"
            " snapshot_date) VALUES ('u2','f','2026-08-15','t',"
            "'Chocó 7 días','2026-08-15')")
        firmas = dict(conn.execute(
            "SELECT url, COALESCE(medio_canonico, medio) FROM news_items"))
        self.assertEqual(firmas["u1"], "El Tiempo")
        self.assertEqual(firmas["u2"], "Chocó 7 días",
                         "sin cabecera declarada, el feed propio sí es el medio")
        conn.close()


class TestMigracionColumnas(unittest.TestCase):
    """Una columna nueva tiene que llegar también a la base que ya existe:
    `CREATE TABLE IF NOT EXISTS` no toca una tabla creada meses atrás."""

    def test_alter_table_idempotente_sobre_base_vieja(self):
        import sqlite3
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
        from common import migrar
        conn = sqlite3.connect(":memory:")
        conn.executescript("""CREATE TABLE news_items (
          url TEXT PRIMARY KEY, feed_id TEXT NOT NULL,
          fecha TEXT, titulo TEXT, medio TEXT, snapshot_date TEXT NOT NULL);""")
        conn.execute("INSERT INTO news_items VALUES ('u','f','2026-08-15','t','m','2026-08-15')")
        self.assertEqual(migrar(conn), ["news_items.medio_canonico",
                                        "news_items.medio_dominio"],
                         "una tabla que no existe no se migra: la crea SCHEMA")
        self.assertEqual(migrar(conn), [], "segunda pasada no hace nada")
        fila = conn.execute(
            "SELECT medio, medio_canonico FROM news_items").fetchone()
        self.assertEqual(fila, ("m", None), "la fila vieja se conserva intacta")
        conn.close()

    def test_el_log_viejo_estrena_los_validadores_sin_perder_una_fila(self):
        """La base del runner arrastra 4.277 peticiones sin ETag ni
        Last-Modified: las columnas nuevas tienen que llegarle por ALTER, en
        NULL, sin tocar lo que ya estaba."""
        import sqlite3
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
        from common import migrar
        conn = sqlite3.connect(":memory:")
        conn.executescript("""CREATE TABLE sources_log (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL, url TEXT NOT NULL,
          http_status INTEGER, sha256 TEXT, bytes INTEGER,
          snapshot_path TEXT, note TEXT);""")
        conn.execute(
            "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
            " snapshot_path,note) VALUES ('2026-08-15T16:21:23Z','https://x/f',"
            " 200,'abc',12,'data/snapshots/2026-08-15/f.json','capa')")
        self.assertEqual(migrar(conn),
                         ["sources_log.etag", "sources_log.last_modified"])
        self.assertEqual(
            conn.execute("SELECT sha256, note, etag, last_modified"
                         " FROM sources_log").fetchone(),
            ("abc", "capa", None, None),
            "la petición de antes del cambio se conserva íntegra y sin "
            "validadores: NULL aquí significa «no se lo preguntamos»")
        conn.close()


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


class TestUnosatCodigoInconsistente(unittest.TestCase):
    """209 puntos de UNOSAT llegan con un código de evento que no cuadra.

    `EQ20260822COL` implica un sismo del 22-ago: posterior a las imágenes que
    los retratan (11 y 13-ago). En todo lo demás son idénticos a los otros
    puntos de sus capas, así que el código no designa otro terremoto — designa
    un error de la fuente.

    ESTE TEST ESTUVO INVERTIDO HASTA EL 21-AGO-2026. Se llamaba
    `TestUnosatOtrosEventos`, el campo era `unosat_otros_eventos` y exigía lo
    contrario de lo que exige ahora: que esos puntos NO sumasen al total. El
    criterio era prudente mientras eran 8 puntos sueltos de Manizales. Ese día
    UNOSAT publicó Zarzal —201 edificios, el único análisis satelital que
    existe de ese municipio— con el mismo código anómalo, y el filtro pasó de
    apartar ocho puntos a callar un municipio entero.

    El criterio nuevo: a qué terremoto pertenece un punto lo dice el GLIDE que
    declara el PRODUCTO que lo publica —los cinco de UNOSAT declaran
    `EQ20260810COL`—, no un campo interno de su geometría que la propia fuente
    contradice. Los 209 cuentan, y la inconsistencia se publica al lado en vez
    de excluirse. Queda escrito aquí, y no solo en `docs/DECISIONES.md`, para
    que quien lo lea dentro de años no crea que se relajó un guardián para que
    pasara.
    """

    def test_suman_al_terremoto_y_ademas_se_cuentan_aparte(self):
        """Antes se exigía `assertEqual(man["unosat_edificios"], 127)` con 8
        puntos fuera. Ahora los 135 de la capa son los 135 del municipio, y
        los 8 discrepantes se publican marcados, no descontados."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None, {
            "Manizales": {"edificios": 135, "observados": 21, "posibles": 114,
                          "codigo_inconsistente": 8, "fecha_imagen": "20260811"}})
        man = next(r for r in rows if r["municipio"] == "Manizales")
        self.assertEqual(man["unosat_edificios"], 135)
        self.assertEqual(man["unosat_observados"] + man["unosat_posibles"], 135)
        self.assertEqual(man["unosat_codigo_inconsistente"], 8)

    def test_un_municipio_entero_con_el_codigo_raro_entra_igual(self):
        """El caso que tumbó el criterio anterior: los 201 puntos de Zarzal
        traen todos el código anómalo. Con el filtro viejo, el municipio no
        habría existido para el monitor pese a que la fuente sí lo publicó."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None, {
            "Zarzal": {"edificios": 201, "observados": 21, "posibles": 180,
                       "codigo_inconsistente": 201, "fecha_imagen": "20260813"}})
        zar = next(r for r in rows if r["municipio"] == "Zarzal")
        self.assertEqual(zar["unosat_edificios"], 201)
        self.assertEqual(zar["unosat_codigo_inconsistente"], 201)

    def test_sin_discrepancia_el_campo_no_existe(self):
        """R3: cero edificios con código inconsistente no es un dato que
        enseñar."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, None, None, {
            "Viterbo": {"edificios": 108, "observados": 42, "posibles": 66,
                        "codigo_inconsistente": 0, "fecha_imagen": "20260812"}})
        vit = next(r for r in rows if r["municipio"] == "Viterbo")
        self.assertIsNone(vit["unosat_codigo_inconsistente"])


class TestCifrasSatelitalesEnLosTextos(unittest.TestCase):
    """Las cifras satelitales escritas a mano en los textos públicos tienen que
    cuadrar con los datos publicados.

    La portada anunciaba 622 edificios —solo Copernicus— mientras el monitor
    ya archivaba otros 385 clasificados por UNITAR-UNOSAT en Caldas. La cifra
    de la tarjeta la calcula el JavaScript desde los datos; la de la prosa, el
    `og:image:alt` y el README están escritas a mano, y sin este guardián
    vuelven a quedarse atrás en silencio. Si falla, no se toca el test: se
    reescriben los textos que nombra.
    """

    RAIZ = Path(__file__).parent.parent

    @classmethod
    def setUpClass(cls):
        mon = json.loads((cls.RAIZ / "data/public/monitor.json")
                         .read_text(encoding="utf-8"))
        cls.cop = int(sum(a["resumen"].get("edificios_afectados") or 0
                          for a in mon["aois"]))
        uno = mon.get("unosat") or {}
        cls.solapan = uno.get("municipios_tambien_en_aoi_copernicus") or []
        cls.uno = int(uno.get("edificios") or 0)
        cls.posibles = int(uno.get("posibles") or 0)
        # Desde el 21-ago-2026 el total NO se calcula sumando fuentes: se une
        # punto a punto en la ingesta y se publica ya resuelto (ver
        # ingest/satelites.py). El test lee lo publicado en vez de rehacer la
        # cuenta — si la recalculase aquí, un error de criterio pasaría los dos
        # lados a la vez y el guardián no serviría de nada.
        cls.satelital = mon.get("satelital") or {}
        cls.total = int(cls.satelital.get("total_edificios") or 0)
        # El tercer sumando. `monitor.json` no publica un agregado de SERTIT
        # —solo el total unido y el reparto por municipio—, así que se suma el
        # detalle municipal, que es exactamente de donde sale la cifra que la
        # prosa escribe a mano.
        cls.ser = int(sum(
            m.get("sertit_edificios") or 0
            for m in json.loads((cls.RAIZ / "data/public/municipios.json")
                                .read_text(encoding="utf-8"))["items"]))
        # Las DOS superficies de prosa del sitio, unidas. La fase 6b mudó a
        # `referencia.html` el párrafo que desglosa el total satelital, y con
        # `cls.index` a secas el guardián habría dado rojo por un cambio de
        # sitio, no por una cifra caducada — que es justo lo contrario de lo
        # que vigila. Lo que importa es que la cifra esté escrita en algún
        # texto público y sea la de hoy, no en cuál de los dos ficheros.
        cls.index = "\n".join(
            (cls.RAIZ / f"site/{n}").read_text(encoding="utf-8")
            for n in ("index.html", "referencia.html"))
        cls.readme = (cls.RAIZ / "README.md").read_text(encoding="utf-8")
        # llms.txt es la superficie que leen los sistemas de IA: se quedó con
        # 622 y con los 393 de la capa mientras el sitio ya publicaba otra cosa
        cls.llms = (cls.RAIZ / "deploy/root/llms.txt").read_text(encoding="utf-8")

    @staticmethod
    def _es(n: int) -> str:
        """Millares con punto, como los escribe el sitio (locale es-CO)."""
        return f"{n:,}".replace(",", ".")

    def test_donde_dos_satelites_se_pisan_el_total_no_los_suma(self):
        """Este test estuvo INVERTIDO hasta el 21-ago-2026: exigía que ninguna
        mirada satelital compartiese municipio con otra, porque esa era la
        condición que autorizaba a sumarlas. La entrada de ICube-SERTIT tumbó
        el supuesto —mira Pereira, Cali y Manizales, ya cartografiados— y con
        él la suma.

        Ahora se exige lo contrario de lo que se exigía: que el total NUNCA
        llegue a la suma de las fuentes cuando alguna se solapa. Queda escrito
        aquí, y no solo en DECISIONES.md, para que quien lo lea dentro de años
        no crea que se relajó un guardián para que pasara.
        """
        por_mun = self.satelital.get("por_municipio") or {}
        self.assertTrue(por_mun, "monitor.json no publica el recuento satelital")
        for muni, d in por_mun.items():
            fuentes = d.get("fuentes") or {}
            if len(fuentes) < 2:
                continue
            suma = sum(fuentes.values())
            self.assertLessEqual(
                d["unidades"], suma,
                f"{muni}: el recuento supera la suma de las fuentes")
            self.assertGreaterEqual(
                d["unidades"], max(fuentes.values()),
                f"{muni}: el recuento pierde edificios que una fuente sí vio")
            if d.get("coincidencias"):
                self.assertLess(
                    d["unidades"], suma,
                    f"{muni}: hay {d['coincidencias']} edificios vistos por dos "
                    f"servicios y el total los cuenta dos veces")

    def test_la_portada_escribe_el_total_de_las_dos_miradas(self):
        for donde, texto in (("site/index.html", self.index),
                             ("README.md", self.readme),
                             ("deploy/root/llms.txt", self.llms)):
            self.assertIn(self._es(self.total), texto,
                          f"{donde} no dice {self._es(self.total)}: el total "
                          f"satelital cambió y el texto se quedó atrás")

    def test_la_portada_desglosa_el_total_y_declara_el_dano_posible(self):
        """Un total compuesto sin desglose no es rastreable hasta su origen, y
        el «daño posible» de UNOSAT no puede desaparecer dentro de la suma.

        ICube-SERTIT entra aquí desde la fase 6b: es el tercer sumando del
        total y su cifra estaba escrita a mano en la prosa sin que nada la
        vigilara, igual que le pasó a Copernicus con los 622. Se deriva de
        `municipios.json`, que es de donde sale la del sitio."""
        for cifra, que in ((self.cop, "los edificios de Copernicus"),
                           (self.uno, "los edificios de UNOSAT"),
                           (self.ser, "los edificios de ICube-SERTIT"),
                           (self.posibles, "el «daño posible» de UNOSAT")):
            if not cifra:
                continue          # una fuente que aún no publica no se exige
            self.assertIn(self._es(cifra), self.index,
                          f"los textos públicos no declaran {que} "
                          f"({self._es(cifra)})")

    def test_el_total_de_unosat_cuadra_con_sus_municipios(self):
        """El agregado de portada y el detalle municipal salen de dos caminos
        distintos del mismo pipeline. Si se separan, la portada estaría
        sumando edificios de un municipio que su propia tabla no lista."""
        muns = json.loads((self.RAIZ / "data/public/municipios.json")
                          .read_text(encoding="utf-8"))["items"]
        detalle = {m["municipio"]: m["unosat_edificios"] for m in muns
                   if m.get("unosat_edificios")}
        self.assertEqual(sum(detalle.values()), self.uno,
                         "el total de UNOSAT en monitor.json no cuadra con la "
                         "suma por municipio de municipios.json")

    def test_la_capa_entera_cuenta_y_la_parte_discrepante_se_declara(self):
        """INVERTIDO el 21-ago-2026. Se llamaba
        `test_la_capa_entera_es_el_evento_mas_los_otros` y exigía
        `capa == publicados + apartados`: 393 puntos en la capa, 385 en el
        sitio, 8 fuera por traer `EQ20260822COL`.

        Ese día UNOSAT publicó Zarzal entero con el mismo código y el criterio
        cambió: manda el GLIDE que declara el producto, no el campo del punto.
        Ahora se exige lo contrario — que la capa entera sea lo publicado, sin
        resta— y que la parte discrepante siga contándose y nombrándose. Un
        total sin ese reparto no sería rastreable hasta su origen."""
        gj = json.loads((self.RAIZ / "data/public/unosat_damage.geojson")
                        .read_text(encoding="utf-8"))
        capa = len(gj["features"])
        discrepantes = sum(1 for f in gj["features"]
                           if (f["properties"].get("event_code") or "").upper()
                           != "EQ20260810COL")
        mon = json.loads((self.RAIZ / "data/public/monitor.json")
                         .read_text(encoding="utf-8"))
        uno = mon.get("unosat") or {}
        self.assertEqual(self.uno, capa,
                         "lo que se publica no es la capa entera: alguien "
                         "volvió a restar puntos por su etiqueta interna")
        self.assertEqual(uno.get("codigo_inconsistente"), discrepantes,
                         "los puntos de código inconsistente cuentan, pero "
                         "tienen que seguir declarándose aparte")
        self.assertEqual(uno.get("observados", 0) + uno.get("posibles", 0),
                         self.uno,
                         "observados + posibles debe ser el total del evento")

    def test_la_documentacion_declara_el_total_y_la_parte_discrepante(self):
        """Antes del 21-ago-2026 este test se llamaba
        `test_la_documentacion_explica_las_dos_cifras_de_unosat` y vigilaba
        que el archivo explicase por qué decía 393 en un sitio y 385 en otro.
        Ya no hay dos cifras: hay una, y dentro de ella una parte que la
        fuente etiqueta de un modo que ella misma contradice. Lo que el
        archivo tiene que declarar ahora es cuántos son y cuántos discrepan —
        sin decir «son de otro terremoto», que el dato no lo sostiene."""
        doc = (self.RAIZ / "docs/LIMITACIONES.md").read_text(encoding="utf-8")
        mon = json.loads((self.RAIZ / "data/public/monitor.json")
                         .read_text(encoding="utf-8"))
        disc = int((mon.get("unosat") or {}).get("codigo_inconsistente") or 0)
        self.assertIn(str(self.uno), doc,
                      "docs/LIMITACIONES.md no declara los edificios que el "
                      "monitor atribuye al terremoto")
        self.assertIn(str(disc), doc,
                      "docs/LIMITACIONES.md no dice cuántos puntos llevan el "
                      "código que la propia fuente contradice")
        self.assertIn("EQ20260822COL", doc,
                      "docs/LIMITACIONES.md no nombra el código inconsistente")

    def test_ninguna_superficie_afirma_que_los_ocho_sean_de_otro_terremoto(self):
        """El archivo no lo sostiene, así que nadie puede escribirlo.

        Los ocho puntos comparten capa, sensor, fecha de imagen, productos y
        confianza con los otros 127 de Manizales: lo único distinto es un
        código de evento imposible. Decir «son de otro evento» convierte un
        fallo de la fuente en un hecho del monitor — justo lo que este
        proyecto existe para no hacer."""
        prohibidas = ("de otro evento", "de otro terremoto",
                      "no son de este terremoto", "otro evento en la misma capa")
        # Desde el 21-ago-2026 los puntos con código imposible SÍ cuentan: lo
        # decide el GLIDE del producto. Estas frases afirman el criterio
        # derogado, y una de ellas seguía saliendo por RSS y push cuando se
        # cambió. Van aparte porque NO pueden prohibirse en los registros
        # fechados —un hito del 20-ago describe lo que era cierto el 20-ago, y
        # reescribirlo sería falsear la cronología—, solo en lo que el sitio
        # afirma HOY.
        derogadas = ("y no los suma", "no los suma", "no sumados al total",
                     "no suman al total")
        # docs/DECISIONES.md queda FUERA a propósito: es el registro de la
        # corrección y necesita citar la frase falsa para refutarla. No lo
        # «arregles» metiéndolo aquí.
        superficies = ["site/index.html", "site/app.js", "site/municipios.html",
                       "site/ui.js", "site/balances.js", "deploy/render_html.py",
                       "deploy/render_descubrimiento.py", "deploy/gen_og.py",
                       "deploy/root/llms.txt", "ingest/publish.py",
                       "ingest/municipios.py", "ingest/alerts.py",
                       "docs/LIMITACIONES.md", "README.md",
                       "feeds/hitos_monitor.json",
                       # Lo que sale por RSS, push y Telegram merece el mismo
                       # guardián que la portada: es lo más difícil de corregir
                       # después, porque el aviso ya se envió.
                       "data/public/alerts.json", "data/public/alerts.rss"]
        # Los registros fechados citan el criterio de su día a propósito.
        FECHADOS = {"feeds/hitos_monitor.json", "docs/DECISIONES.md"}
        for rel in superficies:
            texto = (self.RAIZ / rel).read_text(encoding="utf-8").lower()
            for frase in prohibidas:
                self.assertNotIn(frase, texto,
                                 f"{rel} afirma «{frase}», y el dato no lo sostiene")
            if rel in FECHADOS:
                continue
            for frase in derogadas:
                self.assertNotIn(
                    frase, texto,
                    f"{rel} dice «{frase}»: ese era el criterio hasta el "
                    f"21-ago-2026. Los puntos con código inconsistente cuentan")

    # La leyenda del mapa expresa la proporción de «daño posible» con una
    # fracción redonda, no con un porcentaje. Cada frase vale mientras la
    # proporción real caiga en su horquilla (el punto medio con los vecinos).
    FRACCIONES = {"dos de cada tres": (0.60, 0.70),
                  "tres de cada cuatro": (0.70, 0.775),
                  "cuatro de cada cinco": (0.775, 0.85),
                  "nueve de cada diez": (0.85, 0.95)}

    def test_la_proporcion_de_dano_posible_sigue_siendo_la_que_se_afirma(self):
        """La leyenda decía «tres de cada cuatro son solo daño posible»: 289
        de 385 la sostenían (75,1 %). El 21-ago-2026 la reedición de Viterbo
        y la entrada de Zarzal la movieron a 443 de 548 (80,8 %) y la frase
        habría seguido ahí, afirmando. El test ya no vigila una sola frase:
        vigila la que esté escrita, sea cual sea."""
        if not self.uno:
            self.skipTest("sin datos de UNOSAT")
        proporcion = self.posibles / self.uno
        escritas = [f for f in self.FRACCIONES if f in self.index]
        self.assertEqual(len(escritas), 1,
                         f"la portada debería decir exactamente una fracción "
                         f"de «daño posible» y dice {escritas or 'ninguna'}")
        lo, hi = self.FRACCIONES[escritas[0]]
        self.assertTrue(lo <= proporcion <= hi,
                        f"la portada dice «{escritas[0]}» y la proporción "
                        f"real es {proporcion:.1%}: reescribe la frase de "
                        f"site/index.html")

    def test_la_portada_atribuye_las_dos_fuentes(self):
        for donde, texto in (("la portada", self.index),
                             ("llms.txt", self.llms)):
            for fuente in ("Copernicus", "UNOSAT"):
                self.assertIn(fuente, texto,
                              f"{donde} suma {fuente} sin nombrarlo")

    def test_llms_txt_no_publica_el_total_desnudo(self):
        """El fichero que leen los sistemas de IA no puede dar el total sin el
        reparto: es la superficie donde una cifra se cita sin su contexto."""
        for cifra in (self.cop, self.uno, self.posibles):
            self.assertIn(self._es(cifra), self.llms,
                          f"llms.txt no declara {self._es(cifra)}")


class TestCifrasFechadasDelReadme(unittest.TestCase):
    """El escaparate del proyecto no puede prometer más de lo que archiva.

    El README anunciaba «430+ reportes ciudadanos» con 542 archivados y «3.000+
    noticias» con 6.304: cifras que crecen con cada corrida y que nadie vigilaba.
    No pasan por el build —un README no se genera—, así que van **fechadas**: una
    cifra con su fecha describe un momento y no envejece, solo se queda corta.

    Lo que se vigila es que no SOBREAFIRME. No hay cota por abajo a propósito:
    exigir que el README siga el ritmo del corpus lo pondría en rojo cada mañana
    sin que nada estuviera roto, que es la avería que este test evita, no la que
    provoca. Si el dato baja —una purga, un criterio nuevo—, el README pasa a
    prometer de más y aquí se entera.
    """

    RAIZ = Path(__file__).parent.parent

    @classmethod
    def setUpClass(cls):
        cls.readme = (cls.RAIZ / "README.md").read_text(encoding="utf-8")
        pub = cls.RAIZ / "data/public"
        cls.reportes = len(json.loads((pub / "chatmap.geojson")
                                      .read_text(encoding="utf-8"))["features"])
        cls.con_media = len([f for f in json.loads((pub / "chatmap.geojson")
                                                   .read_text(encoding="utf-8"))["features"]
                             if f["properties"].get("media")])
        cls.titulares = int(json.loads((pub / "noticias.json")
                                       .read_text(encoding="utf-8"))["total"])

    def _escrita(self, patron: str) -> int:
        m = re.search(patron, self.readme)
        self.assertIsNotNone(m, f"el README ya no dice «{patron}»")
        return int(m.group(1).replace(".", ""))

    def test_los_reportes_ciudadanos_no_prometen_de_mas(self):
        escrita = self._escrita(r"([\d.]+) reportes ciudadanos con coordenada")
        self.assertLessEqual(escrita, self.reportes,
                             f"el README dice {escrita} reportes ciudadanos y hay "
                             f"{self.reportes}: actualiza la cifra y su fecha")

    def test_los_reportes_con_media_no_prometen_de_mas(self):
        escrita = self._escrita(r"([\d.]+) con foto\s*\n?\s*o vídeo")
        self.assertLessEqual(escrita, self.con_media,
                             f"el README dice {escrita} reportes con foto o vídeo y hay "
                             f"{self.con_media}")

    def test_los_titulares_no_prometen_de_mas(self):
        escrita = self._escrita(r"([\d.]+) titulares del")
        self.assertLessEqual(escrita, self.titulares,
                             f"el README dice {escrita} titulares y hay {self.titulares}")

    def test_cada_cifra_que_crece_lleva_su_fecha(self):
        """Sin fecha, la cifra es una promesa sobre hoy; con fecha, un dato."""
        for patron in (r"reportes ciudadanos con coordenada", r"titulares del"):
            frase = re.search(patron + r".{0,160}", self.readme, re.S)
            self.assertIn("22-ago-2026", frase.group(0),
                          f"la cifra de «{patron}» se publica sin fecha")


class TestCodigoDeEventoImposible(unittest.TestCase):
    """R11 sobre el etiquetado de UNOSAT: un código con fecha imposible avisa.

    `EQ20260822COL` llegó el 19-ago-2026 sobre una imagen del 11-ago, fechando
    un sismo que aún no había ocurrido. Nadie lo cantó: se descubrió leyendo la
    capa a mano un día después. Un código de evento futuro en un producto ya
    publicado es un supuesto roto de manual, y ahora la corrida lo dice.
    """

    def _conn(self, filas):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE unosat_damage (event_code TEXT, capa TEXT,"
                     " sensor_date TEXT)")
        conn.executemany("INSERT INTO unosat_damage VALUES (?,?,?)", filas)
        return conn

    def _detectar(self, filas, hoy="2026-08-20"):
        import alerts
        return alerts.codigos_de_evento_imposibles(self._conn(filas), hoy)

    def test_un_codigo_fechado_en_el_futuro_avisa(self):
        fuera = self._detectar([("EQ20260822COL", "capa_manizales", "20260811")] * 8)
        self.assertEqual(len(fuera), 1)
        self.assertEqual(fuera[0]["n"], 8)
        self.assertIn("aún no ha llegado", fuera[0]["motivo"])

    def test_un_codigo_posterior_a_la_imagen_tambien_avisa(self):
        """Aunque ya haya pasado: una imagen no retrata daño de un sismo que
        todavía no había ocurrido cuando se tomó."""
        fuera = self._detectar([("EQ20260815COL", "capa_x", "20260811")],
                               hoy="2026-09-01")
        self.assertEqual(len(fuera), 1)
        self.assertIn("posterior a la imagen", fuera[0]["motivo"])

    def test_el_codigo_del_terremoto_no_avisa(self):
        self.assertEqual(
            self._detectar([("EQ20260810COL", "capa_x", "20260811")]), [])

    def test_un_codigo_que_no_sigue_el_patron_no_inventa_alarma(self):
        """R3 aplicado a la alerta: si no se puede leer la fecha, no se afirma
        que sea imposible. Un formato desconocido es ausencia, no error."""
        self.assertEqual(self._detectar([("RAROSINFECHA", "capa_x", "20260811")]), [])
        self.assertEqual(self._detectar([(None, "capa_x", "20260811")]), [])

    def test_sin_fecha_de_imagen_solo_se_juzga_contra_hoy(self):
        self.assertEqual(
            self._detectar([("EQ20260815COL", "capa_x", None)], hoy="2026-09-01"), [])
        self.assertEqual(
            len(self._detectar([("EQ20260930COL", "capa_x", None)], hoy="2026-09-01")), 1)


class TestSertitAtribucion(unittest.TestCase):
    """Cómo SERTIT nombra sus productos, y las trampas de leerlo."""

    def test_mayusculas_y_camelcase_dan_el_mismo_municipio(self):
        """De los cinco productos, cuatro escriben `COLOMBIA_PEREIRA` y uno
        `Colombia_LaVirginia`. El primer intento sin IGNORECASE se comió
        cuatro municipios en silencio: entraron con municipio nulo y su daño
        quedó sin atribuir."""
        from sources import sertit
        self.assertEqual(
            sertit._municipio_de_nombre(
                "CHARTER_CALL1202_ID1048_AOI05_COLOMBIA_PEREIRA_IMPACTMAP_2026"),
            ("Pereira", "catalogo"))
        self.assertEqual(
            sertit._municipio_de_nombre(
                "20260812_CHARTER_Call1202_ID1048_AOI15_Colombia_LaVirginia_ImpactMap"),
            ("La Virginia", "catalogo"))

    def test_anserma_no_es_ansermanuevo(self):
        """R10 también aquí: la coincidencia es exacta normalizada, nunca por
        subcadena. Anserma es prefijo de Ansermanuevo, otro municipio y de
        otro departamento."""
        from sources import sertit
        self.assertEqual(
            sertit._municipio_de_nombre("X_COLOMBIA_ANSERMA_IMPACTMAP_1")[0],
            "Anserma")
        self.assertEqual(
            sertit._municipio_de_nombre("X_COLOMBIA_ANSERMANUEVO_IMPACTMAP_1")[0],
            "Ansermanuevo")

    def test_municipio_fuera_del_catalogo_se_marca_como_tal(self):
        """Un nombre que el catálogo no reconoce se conserva, pero marcado:
        un municipio del catálogo y uno leído de un rótulo no pueden ser
        indistinguibles para quien lea el archivo dentro de años."""
        from sources import sertit
        muni, origen = sertit._municipio_de_nombre(
            "X_COLOMBIA_PuebloInventado_IMPACTMAP_1")
        self.assertEqual(origen, "texto_sertit")
        self.assertEqual(muni, "Pueblo Inventado")

    def test_sin_municipio_reconocible_no_inventa(self):
        from sources import sertit
        self.assertEqual(sertit._municipio_de_nombre("ruido_sin_forma"),
                         (None, "desconocido"))


class TestUnionEspacial(unittest.TestCase):
    """La regla que sustituyó a la suma de miradas satelitales.

    El caso que la motivó: SERTIT entró en agosto de 2026 mirando Pereira,
    Cali y Manizales, que Copernicus y UNOSAT ya cartografiaban. Sumar sus
    totales habría contado dos veces los mismos tejados.
    """

    def _p(self, fuente, lon, lat, dano=None):
        return {"fuente": fuente, "lon": lon, "lat": lat, "dano": dano}

    def test_dos_fuentes_sobre_el_mismo_edificio_cuentan_uno(self):
        from satelites import unir_danos
        r = unir_danos([self._p("copernicus", -75.6889, 4.8134),
                        self._p("sertit", -75.68891, 4.81341)], umbral_m=20)
        self.assertEqual(r["unidades"], 1)
        self.assertEqual(r["coincidencias"], 1)

    def test_la_misma_fuente_nunca_se_funde_consigo_misma(self):
        """Si un servicio marcó dos edificios pegados, es que vio dos. Fundir
        sus puntos sería corregir a la fuente, que es justo lo que no se hace."""
        from satelites import unir_danos
        r = unir_danos([self._p("sertit", -75.6889, 4.8134),
                        self._p("sertit", -75.68891, 4.81341)], umbral_m=20)
        self.assertEqual(r["unidades"], 2)
        self.assertEqual(r["coincidencias"], 0)

    def test_el_recuento_esta_entre_el_maximo_y_la_suma(self):
        from satelites import unir_danos
        pts = ([self._p("copernicus", -75.68 + i / 1000, 4.81) for i in range(5)]
               + [self._p("sertit", -75.68 + i / 1000, 4.81) for i in range(3)])
        r = unir_danos(pts, umbral_m=20)
        self.assertGreaterEqual(r["unidades"], 5)   # el máximo por fuente
        self.assertLessEqual(r["unidades"], 8)      # la suma ingenua

    def test_lejos_no_se_unen(self):
        from satelites import unir_danos
        r = unir_danos([self._p("copernicus", -75.6889, 4.8134),
                        self._p("sertit", -75.7000, 4.8200)], umbral_m=20)
        self.assertEqual(r["unidades"], 2)

    def test_sin_puntos_no_hay_cero_hay_ausencia(self):
        """R3: un 0 aquí se leería como «los satélites miraron y no vieron
        nada», que es lo contrario de «nadie ha mirado»."""
        from satelites import unir_danos
        self.assertIsNone(unir_danos([])["unidades"])

    def test_la_discrepancia_de_grado_se_cuenta(self):
        """Dos servicios sobre el mismo tejado con distinta gravedad: eso es
        un hallazgo del monitor, no un error que haya que resolver."""
        from satelites import unir_danos
        r = unir_danos([self._p("copernicus", -75.6889, 4.8134, "Destroyed"),
                        self._p("sertit", -75.68891, 4.81341, "Damaged")],
                       umbral_m=20)
        self.assertEqual(r["discrepan_de_grado"], 1)
        r2 = unir_danos([self._p("copernicus", -75.6889, 4.8134, "Damaged"),
                         self._p("sertit", -75.68891, 4.81341, "Damaged")],
                        umbral_m=20)
        self.assertEqual(r2["discrepan_de_grado"], 0)

    def test_exclusivos_por_fuente(self):
        from satelites import unir_danos
        r = unir_danos([self._p("copernicus", -75.6889, 4.8134),
                        self._p("sertit", -75.68891, 4.81341),
                        self._p("sertit", -75.7000, 4.8200)], umbral_m=20)
        self.assertEqual(r["solo_de"].get("sertit"), 1)
        self.assertIsNone(r["solo_de"].get("copernicus"))

    def test_todo_aoi_de_copernicus_con_stats_tiene_municipio(self):
        """Si Copernicus abre un AOI nuevo, sus edificios no pueden
        desaparecer del recuento en silencio por no estar mapeado."""
        from satelites import AOI_MUNICIPIO
        publicos = Path(__file__).parent.parent / "data" / "public" / "aois.geojson"
        if not publicos.exists():
            self.skipTest("sin aois.geojson")
        aois = json.loads(publicos.read_text(encoding="utf-8"))
        for f in aois.get("features", []):
            nombre = (f.get("properties") or {}).get("aoi")
            resumen = (f.get("properties") or {}).get("resumen") or {}
            if not nombre or nombre == "Western Colombia":
                continue
            if resumen.get("edificios_afectados") in (None, "", 0):
                continue
            self.assertIn(nombre, AOI_MUNICIPIO,
                          f"El AOI «{nombre}» declara edificios y no está en "
                          f"AOI_MUNICIPIO: sus daños no entrarían al recuento")


class TestAlertaSertitSinVectores(unittest.TestCase):
    """La alerta que avisa de que hay que escribir un correo.

    Los vectores de ICube-SERTIT no se descargan: su web los manda por correo
    tras un formulario. Un producto nuevo entra en el catálogo con
    `paquete_sha256` en nulo y ahí se queda —visible y sin puntos— hasta que
    una persona lo pida. Sin esta alerta, nadie se entera.

    Se comprueba contra la forma real del bug: una base donde el producto
    existe SIN paquete. Un test que solo mirase la base de hoy pasaría en
    verde sin ejercitar nunca la rama, que es exactamente cómo se cuela un
    guardián que no guarda.
    """

    def _base(self):
        import sqlite3
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        return conn

    def test_un_producto_sin_paquete_dispara_la_alerta(self):
        conn = self._base()
        conn.execute(
            "INSERT INTO sertit_productos (producto_id, municipio, n_producto,"
            " paquete_sha256, snapshot_date) VALUES (?,?,?,NULL,?)",
            (9001, "Trujillo", "06", "2026-09-01"))
        pendientes = conn.execute(
            "SELECT municipio FROM sertit_productos WHERE paquete_sha256 IS NULL"
        ).fetchall()
        self.assertEqual([r[0] for r in pendientes], ["Trujillo"],
                         "un producto sin vectores tiene que ser localizable: "
                         "es el disparador de la alerta")
        conn.close()

    def test_un_producto_con_paquete_no_la_dispara(self):
        conn = self._base()
        conn.execute(
            "INSERT INTO sertit_productos (producto_id, municipio, n_producto,"
            " paquete_sha256, snapshot_date) VALUES (?,?,?,?,?)",
            (9002, "Pereira", "01", "a" * 64, "2026-09-01"))
        pendientes = conn.execute(
            "SELECT municipio FROM sertit_productos WHERE paquete_sha256 IS NULL"
        ).fetchall()
        self.assertEqual(pendientes, [],
                         "un producto con sus vectores no puede pedir que "
                         "alguien escriba un correo que ya se escribió")
        conn.close()


class TestLaAlertaNoContaminaConPaquetesViejos(unittest.TestCase):
    """La alerta y la portada tienen que decir el mismo número.

    El 21-ago-2026 no lo decían: la alerta leía `unosat_damage` sin filtrar
    por paquete, sumaba los puntos del paquete ya superado y anunciaba 16
    donde el monitor publicaba 209. La cifra equivocada era, además, la que
    salía por RSS y por push — la más difícil de corregir después. Y empeoraba
    con cada reedición de la fuente.
    """

    def _base(self, filas):
        import sqlite3
        from common import SCHEMA
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        for sha, capa, code, idx in filas:
            conn.execute(
                "INSERT INTO unosat_damage (paquete_sha, capa, idx, event_code,"
                " sensor_date, snapshot_date) VALUES (?,?,?,?,?,?)",
                (sha, capa, idx, code, "20260811", "2026-08-21"))
        return conn

    def test_solo_cuenta_el_paquete_vigente(self):
        import alerts
        filas = ([("viejo", "capa_m", "EQ20260822COL", i) for i in range(8)]
                 + [("nuevo", "capa_m", "EQ20260822COL", i) for i in range(8)])
        conn = self._base(filas)
        sin_filtro = alerts.codigos_de_evento_imposibles(conn, "2026-08-21")
        con_filtro = alerts.codigos_de_evento_imposibles(
            conn, "2026-08-21", paquete="nuevo")
        self.assertEqual(sum(x["n"] for x in sin_filtro), 16,
                         "sin filtro se cuentan los dos paquetes: ese era el bug")
        self.assertEqual(
            sum(x["n"] for x in con_filtro), 8,
            "con el paquete vigente la alerta dice lo mismo que la portada")
        conn.close()


class TestLaImagenCompartidaNoSeQuedaAtras(unittest.TestCase):
    """La imagen Open Graph es la superficie que se comparte SIN contexto.

    El 21-ago-2026 anunciaba 1.415 edificios y 439 reportes mientras el
    monitor sostenía 1.578 y 465, y su propio texto alternativo —que sí tiene
    guardián— ya decía la cifra buena. Causa: `deploy/gen_og.py` no lo
    ejecutaba nadie, ni el build ni el workflow diario.

    Un PNG no se puede leer desde un test, así que el generador escribe al
    lado con qué cifras pintó. Si este test falla, la imagen se quedó atrás y
    hay que regenerarla — no cambiar el número esperado.
    """

    RAIZ = Path(__file__).parent.parent

    def test_la_portada_og_declara_las_cifras_publicadas(self):
        og = self.RAIZ / "site" / "og" / "portada.json"
        mon = self.RAIZ / "data" / "public" / "monitor.json"
        if not og.exists() or not mon.exists():
            self.skipTest("sin imagen generada todavía")
        pintado = json.loads(og.read_text(encoding="utf-8"))
        datos = json.loads(mon.read_text(encoding="utf-8"))
        self.assertEqual(
            pintado.get("edificios_satelite"),
            (datos.get("satelital") or {}).get("total_edificios"),
            "la imagen que se comparte anuncia un total satelital distinto del "
            "que publica el monitor: hay que regenerarla con deploy/gen_og.py")
        self.assertEqual(
            pintado.get("reportes_ciudadanos"),
            datos["citizen"]["chatmap_total"],
            "la imagen que se comparte anuncia otro número de reportes "
            "ciudadanos que el monitor")

    def test_el_build_regenera_las_imagenes(self):
        """Y que nadie vuelva a dejarlo fuera del build."""
        build = (self.RAIZ / "deploy" / "build_dist.sh").read_text(encoding="utf-8")
        self.assertIn(
            "gen_og.py", build,
            "build_dist.sh no regenera las imágenes compartidas: volverán a "
            "quedarse atrás en silencio la próxima vez que cambie una cifra")


class TestCapaDeLaAusencia(unittest.TestCase):
    """Los municipios con damnificados a los que no miró ningún satélite.

    Es la tesis del proyecto dibujada: la distancia entre lo que se ve y lo que
    se cuenta. Por eso la capa se calcula en el build y no en el navegador —la
    cifra que el sitio enseña y la que pinta tienen que salir del mismo sitio—
    y por eso «sin intensidad» no puede acabar siendo «intensidad baja».
    """

    REJILLA = {
        # 3x3 grados alrededor del epicentro, MMI decreciente hacia el borde
        "domain": {"axes": {"x": {"start": -77.0, "stop": -75.0, "num": 3},
                            "y": {"start": 4.0, "stop": 6.0, "num": 3}}},
        "ranges": {"mmi": {"values": [4.0, 4.5, 4.0,
                                      5.0, 7.5, 5.0,
                                      4.0, 4.5, 4.0]}},
    }

    def _municipios(self, **cambios):
        base = {"municipio": "Sin Mirar", "departamento": "Chocó",
                "lat": 5.0, "lon": -76.0, "rud_familias": 120,
                "rud_personas": 400, "mmi_usgs": 7.5,
                "unosat_edificios": None, "sertit_edificios": None,
                "en_aoi_copernicus": False}
        return [{**base, **cambios}]

    def test_el_municipio_que_nadie_miro_entra_en_la_capa(self):
        from municipios import capa_sin_mirada
        capa = capa_sin_mirada(self._municipios(), "2026-08-22")
        self.assertEqual(capa["total"], 1)
        self.assertEqual(capa["items"][0]["municipio"], "Sin Mirar")
        self.assertEqual(capa["items"][0]["rud_familias"], 120)

    def test_la_cifra_publicada_es_la_de_la_lista_no_una_constante(self):
        """El 196 del rótulo y los 196 puntos del mapa son el mismo recuento.

        Es la lección de la portada que decía 36 con 43 en su propia tabla: en
        cuanto la cifra se escribe aparte de la lista, las dos divergen.
        """
        from municipios import capa_sin_mirada
        muchos = [dict(m, municipio=f"M{i}")
                  for i in range(7) for m in self._municipios()]
        capa = capa_sin_mirada(muchos, "2026-08-22")
        self.assertEqual(capa["total"], len(capa["items"]))

    def test_estrenar_mirada_satelital_saca_al_municipio_de_la_capa(self):
        """R11: el día que un satélite lo mire, el municipio debe desaparecer
        solo. Si hubiera que borrarlo a mano, la capa mentiría al día siguiente.
        """
        from municipios import capa_sin_mirada
        for mirada in ("unosat_edificios", "sertit_edificios"):
            with self.subTest(mirada=mirada):
                capa = capa_sin_mirada(self._municipios(**{mirada: 30}),
                                       "2026-08-22")
                self.assertEqual(capa["total"], 0)
        capa = capa_sin_mirada(self._municipios(en_aoi_copernicus=True),
                               "2026-08-22")
        self.assertEqual(capa["total"], 0)

    def test_sin_damnificados_registrados_no_entra(self):
        """La capa habla de municipios con damnificados a los que nadie miró.
        Sin registro no hay nada que contrastar: sería ruido, no una brecha."""
        from municipios import capa_sin_mirada
        for vacio in (None, 0):
            with self.subTest(rud_familias=vacio):
                capa = capa_sin_mirada(self._municipios(rud_familias=vacio),
                                       "2026-08-22")
                self.assertEqual(capa["total"], 0)

    # dos municipios del catálogo con registro RUD: uno dentro del cuadro de la
    # rejilla de prueba (Roldanillo) y otro muy fuera (Acandí, en el Darién)
    RUD = {("valle del cauca", "roldanillo"): {
               "departamento": "VALLE DEL CAUCA", "municipio": "ROLDANILLO",
               "familias": 40, "personas": 100,
               "viv_destruidas": 0, "viv_averiadas": 0},
           ("choco", "acandi"): {
               "departamento": "CHOCÓ", "municipio": "ACANDÍ",
               "familias": 12, "personas": 30,
               "viv_destruidas": 0, "viv_averiadas": 0}}

    def test_fuera_de_la_rejilla_no_hay_intensidad_baja_hay_ausencia(self):
        """R3 en el mapa: un municipio que el ShakeMap no cubre se queda en
        None y se pinta gris. Darle el escalón más bajo sería publicar un dato
        que nadie ha medido, y encima el más tranquilizador."""
        from geo import MMIGrid
        from municipios import build_municipios
        # Acandí (8.51, -77.28) cae fuera del cuadro de la rejilla
        rows, _ = build_municipios([], None, {}, None, self.RUD,
                                   grid_mmi=MMIGrid(self.REJILLA))
        acandi = next(r for r in rows if r["municipio"] == "Acandí")
        self.assertIsNone(acandi["mmi_usgs"])

    def test_la_intensidad_sale_de_la_rejilla_del_usgs(self):
        """Dentro de la rejilla sí hay dato, y es el que da el ShakeMap."""
        from geo import MMIGrid
        from municipios import build_municipios
        # Roldanillo (4.41, -76.15) cae dentro del cuadro
        rows, _ = build_municipios([], None, {}, None, self.RUD,
                                   grid_mmi=MMIGrid(self.REJILLA))
        rold = next(r for r in rows if r["municipio"] == "Roldanillo")
        self.assertIsNotNone(rold["mmi_usgs"])
        self.assertGreaterEqual(rold["mmi_usgs"], 4.0)

    def test_sin_shakemap_la_capa_sigue_saliendo_sin_intensidad(self):
        """R13: que falte el ShakeMap no puede tumbar la capa. Se publica sin
        color graduado, no se deja de publicar."""
        from municipios import build_municipios
        rows, _ = build_municipios([], None, {}, None, self.RUD, grid_mmi=None)
        self.assertTrue(rows)
        self.assertTrue(all(r["mmi_usgs"] is None for r in rows))

    def test_la_laguna_se_cuenta_no_se_descubre_mirando_el_mapa(self):
        """Cuántos se quedaron sin intensidad se publica como cifra: un archivo
        honesto documenta lo que no tiene."""
        from municipios import capa_sin_mirada
        capa = capa_sin_mirada(self._municipios(mmi_usgs=None), "2026-08-22")
        self.assertEqual(capa["sin_mmi"], 1)

    def test_el_json_dice_que_la_intensidad_es_estimada_no_percibida(self):
        """R9: el rótulo viaja con el dato. Quien lea el JSON no tiene que
        adivinar que es un modelo y no lo que la gente sintió."""
        from municipios import capa_sin_mirada
        capa = capa_sin_mirada(self._municipios(), "2026-08-22")
        self.assertIn("estimada", capa["fuente_mmi"])
        self.assertIn("USGS", capa["fuente_mmi"])

    def test_la_capa_no_arrastra_los_titulares_que_el_mapa_no_usa(self):
        """El fichero existe aparte justamente para no pesar: si vuelve a
        llevar noticias_ejemplo, deja de tener sentido."""
        from municipios import capa_sin_mirada
        capa = capa_sin_mirada(
            self._municipios(noticias_ejemplo=[{"titulo": "x"} for _ in range(9)],
                             n_noticias=9),
            "2026-08-22")
        self.assertNotIn("noticias_ejemplo", capa["items"][0])
        self.assertNotIn("n_noticias", capa["items"][0])


class TestLaCapaNoAcusaEnFalso(unittest.TestCase):
    """Haber mirado y no encontrar nada no es no haber mirado.

    Los recuentos satelitales se comprobaban con `bool()`, así que un municipio
    donde el servicio miró y marcó cero edificios con grado de daño figuraba
    como no evaluado — y la capa de la ausencia llegaba a decirle al lector que
    nadie lo había mirado. Es R3 leído al revés: el cero convertido en ausencia.
    """

    def test_cero_edificios_evaluados_no_es_ausencia_de_evaluacion(self):
        from municipios import build_municipios
        for fuente, campo in (("unosat", "unosat_edificios"),
                              ("sertit", "sertit_edificios")):
            with self.subTest(fuente=fuente):
                paquete = {"Viterbo": {"edificios": 0}}
                rows, _ = build_municipios(
                    [], None, {}, None, None, None,
                    paquete if fuente == "unosat" else None,
                    sertit=paquete if fuente == "sertit" else None)
                vit = next(r for r in rows if r["municipio"] == "Viterbo")
                self.assertEqual(vit[campo], 0,
                                 "cero evaluados es un resultado, no un hueco")
                self.assertIn(fuente, vit["fuentes"])

    def test_el_municipio_evaluado_a_cero_no_entra_en_la_capa(self):
        """El caso completo: si SERTIT lo miró, la capa no puede afirmar que
        nadie lo hizo, por mucho que el recuento con grado sea cero."""
        from municipios import capa_sin_mirada
        mirado = {"municipio": "Mirado", "departamento": "Chocó",
                  "lat": 5.0, "lon": -76.0, "rud_familias": 120,
                  "sertit_edificios": 0, "unosat_edificios": None,
                  "en_aoi_copernicus": False}
        self.assertEqual(capa_sin_mirada([mirado], "2026-08-22")["total"], 0)

    def test_la_procedencia_de_la_rejilla_viaja_con_el_dato(self):
        """R4: `grid_mmi_vigente` se cae a snapshots anteriores en silencio, así
        que el producto tiene que decir de qué rejilla salieron sus cifras."""
        from municipios import capa_sin_mirada

        class GridFalso:
            origen = {"snapshot": "2026-08-20", "sha256": "abc123"}

        sin = {"municipio": "Sin Mirar", "departamento": "Chocó",
               "lat": 5.0, "lon": -76.0, "rud_familias": 10,
               "unosat_edificios": None, "sertit_edificios": None,
               "en_aoi_copernicus": False}
        capa = capa_sin_mirada([sin], "2026-08-22", GridFalso())
        self.assertEqual(capa["fuente_mmi_snapshot"]["snapshot"], "2026-08-20")
        self.assertIn("us6000tjl2", capa["fuente_mmi_url"])

    def test_el_rotulo_cuenta_los_que_se_pueden_pintar(self):
        """Un municipio sin coordenadas cuenta en el total y no en el mapa: si
        el rótulo usa el total, promete puntos que no existen."""
        from municipios import capa_sin_mirada
        base = {"departamento": "Chocó", "rud_familias": 10,
                "unosat_edificios": None, "sertit_edificios": None,
                "en_aoi_copernicus": False}
        capa = capa_sin_mirada(
            [{**base, "municipio": "Con", "lat": 5.0, "lon": -76.0},
             {**base, "municipio": "Sin", "lat": None, "lon": None}],
            "2026-08-22")
        self.assertEqual(capa["total"], 2)
        self.assertEqual(capa["con_coordenadas"], 1)


class TestLasDosPreguntasSobreLaMirada(unittest.TestCase):
    """«Sin satélite» se pregunta de dos maneras y las dos cifras difieren.

    `municipios.py::sin_mirada_satelital` (la capa del mapa) exige damnificados
    registrados; `render_html.py::_mirado_por_satelite` (la tabla) no. Por eso
    la portada publica 196 y municipios.html 197, y las dos tienen razón. Lo que
    no puede pasar —y pasó— es que un rótulo enuncie una y muestre la otra.
    """

    RAIZ = Path(__file__).parent.parent

    def _municipio(self, **cambios):
        base = {"municipio": "X", "departamento": "Chocó", "lat": 5.0,
                "lon": -76.0, "rud_familias": 10, "unosat_edificios": None,
                "sertit_edificios": None, "en_aoi_copernicus": False}
        return {**base, **cambios}

    def test_sin_registro_en_el_rud_queda_fuera_de_la_capa_pero_sigue_sin_satelite(self):
        """El caso Palmira: es la diferencia entre las dos cifras, y existe."""
        from municipios import capa_sin_mirada, sin_mirada_satelital
        palmira = self._municipio(municipio="Palmira", rud_familias=None,
                                  n_noticias=31, dyfi_max_cdi=4.3)
        self.assertFalse(sin_mirada_satelital(palmira))
        self.assertEqual(capa_sin_mirada([palmira], "2026-08-22")["total"], 0)
        # y sin embargo ningún satélite lo ha mirado: la otra pregunta da 1
        self.assertIsNone(palmira["unosat_edificios"])
        self.assertIsNone(palmira["sertit_edificios"])
        self.assertFalse(palmira["en_aoi_copernicus"])

    # Aquí vivían dos guardianes que comparaban los NOMBRES de los campos en el
    # texto de `site/municipios.js` y de `ingest/municipios.py`. Se retiran en la
    # fase 4, cuando la regla de la tabla se mudó al build: repuntarlos a
    # `render_html.py` los habría dejado igual de mudos, porque un `assertIn`
    # sobre el código fuente pasa en verde con la condición invertida (M1). Lo
    # que querían comprobar lo hace ahora, LLAMANDO a las dos funciones sobre 54
    # combinaciones, `test_render_html::TestLaMiradaSatelitalEnLasDosSuperficies`.

    def test_el_rotulo_del_mapa_dice_su_condicion(self):
        """El rótulo de la capa tiene que enunciar el predicado que cuenta. Sin
        «damnificados», describe las 197 y enseña 196.

        Se mira SOLO el literal del rótulo, nunca el comentario que lo precede:
        la primera versión de este test leía los 400 caracteres anteriores y
        pasaba en verde con el rótulo malo, porque la palabra estaba en el
        comentario que explica por qué hace falta. Un guardián que no guarda.
        """
        app = (self.RAIZ / "site/app.js").read_text(encoding="utf-8")
        # La capa se localiza por su CHIP, no por un detalle de cómo se
        # construye: antes se buscaba el rótulo que interpolaba
        # `conCoords.length`, y con la carga diferida esa cifra ya no se
        # escribe aquí —la pone `enciende` contando lo que ha dibujado—.
        # `conChip("ausencia")` es lo que de verdad identifica a esta capa y
        # sobrevive a cómo se construya.
        capa = re.search(r'layers\[([^\]]+)\]\s*=\s*\n?\s*conChip\("ausencia"', app)
        self.assertTrue(capa, "no se encuentra el rótulo de la capa de la ausencia")
        texto = " ".join(re.findall(r'["`]([^"`]*)["`]', capa.group(1)))
        self.assertIn("damnificados", texto,
                      f"la etiqueta omite la condición del RUD: {texto!r}")


class TestProcedenciaDeLaRejilla(unittest.TestCase):
    """`grid_mmi_vigente` se cae a snapshots anteriores; el salto debe dejar rastro."""

    def _covjson(self):
        return {"domain": {"axes": {"x": {"start": -77.0, "stop": -75.0, "num": 2},
                                    "y": {"start": 4.0, "stop": 6.0, "num": 2}}},
                "ranges": {"mmi": {"values": [4.0, 5.0, 6.0, 7.0]}}}

    def test_usa_el_snapshot_de_hoy_y_sella_su_sha256(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path as P

        import geo
        with tempfile.TemporaryDirectory() as tmp:
            hoy = P(tmp) / "2026-08-22"
            hoy.mkdir()
            crudo = json.dumps(self._covjson()).encode()
            (hoy / "usgs_mmi_grid.covjson").write_bytes(crudo)
            grid = geo.grid_mmi_vigente(hoy)
        self.assertEqual(grid.origen["snapshot"], "2026-08-22")
        self.assertEqual(grid.origen["sha256"], hashlib.sha256(crudo).hexdigest())

    def test_si_hoy_no_trae_rejilla_cae_al_anterior_y_lo_dice(self):
        """Es el caso que hace falta sellar: el dato se publica con fecha de hoy
        y viene de días atrás. Sin el sello, nadie podría saberlo (R4)."""
        import json
        import tempfile
        from pathlib import Path as P

        import geo
        with tempfile.TemporaryDirectory() as tmp:
            raiz = P(tmp)
            for dia in ("2026-08-20", "2026-08-21", "2026-08-22"):
                (raiz / dia).mkdir()
            (raiz / "2026-08-21" / "usgs_mmi_grid.covjson").write_text(
                json.dumps(self._covjson()))
            original = geo.SNAPSHOTS if hasattr(geo, "SNAPSHOTS") else None
            import common
            previo = common.SNAPSHOTS
            common.SNAPSHOTS = raiz
            try:
                grid = geo.grid_mmi_vigente(raiz / "2026-08-22")
            finally:
                common.SNAPSHOTS = previo
                del original
        self.assertIsNotNone(grid, "R13: sin rejilla de hoy se usa la anterior")
        self.assertEqual(grid.origen["snapshot"], "2026-08-21",
                         "el sello tiene que delatar que el dato no es de hoy")

    def test_sin_ninguna_rejilla_devuelve_none_sin_reventar(self):
        import tempfile
        from pathlib import Path as P

        import common
        import geo
        with tempfile.TemporaryDirectory() as tmp:
            previo = common.SNAPSHOTS
            common.SNAPSHOTS = P(tmp) / "no-existe"
            try:
                self.assertIsNone(geo.grid_mmi_vigente(P(tmp)))
            finally:
                common.SNAPSHOTS = previo


class TestActivosDelArchivo(unittest.TestCase):
    # la trajo el merge con main, cuyo método de la imagen OG la usa
    RAIZ = Path(__file__).parent.parent

    """Un activo se archiva UNA vez.

    Medido sobre `sources_log` el 24-ago-2026: de los 3.931 MB que el monitor
    había descargado en su vida, **2.648 eran 77 vídeos ciudadanos bajados una
    media de 4,8 veces cada uno**, siempre con el mismo sha256 — cero
    excepciones en 372 descargas. Uno de 59,6 MB se bajó seis veces. La causa
    no era la red: los vídeos están en `.gitignore`, la máquina de la corrida
    arranca sin uno solo, y el guardián preguntaba al disco.

    Lo que vigilan estos tests no es el ahorro —eso lo cuenta el log— sino las
    cuatro cosas que el ahorro no puede costar: que un vídeo NUEVO deje de
    bajarse, que uno CAMBIADO deje de archivarse, que un archivo ilegible tumbe
    la corrida, y que el manifiesto —lo único que hace auditable el bucket—
    pierda lo que ya sabía.
    """

    VIDEO = "https://chatmap.hotosm.org/api/v1/media/aaaa-1.mp4"
    SHA_ARCHIVADO = "e" * 64

    class SinCerrar:
        """La conexión que le damos a `chatmap.run()`: hace todo menos
        cerrarse, para que el test pueda mirar la base después."""

        def __init__(self, conn):
            self._c = conn

        def __getattr__(self, nombre):
            return getattr(self._c, nombre)

        def close(self):
            pass

    # --- andamio -----------------------------------------------------------

    def _mundo(self, tmp, *, objetos=None, manifiesto_crudo=None):
        """Un repo de mentira: data/media vacía y un manifiesto a elegir.

        Devuelve (conn, parches). `objetos` escribe un manifiesto normal;
        `manifiesto_crudo` escribe el texto tal cual (para romperlo a mano).
        """
        import sqlite3
        from unittest import mock
        import common
        (tmp / "data" / "media").mkdir(parents=True, exist_ok=True)
        manifiesto = tmp / "data" / "r2_manifest.json"
        if manifiesto_crudo is not None:
            manifiesto.write_text(manifiesto_crudo, encoding="utf-8")
        elif objetos is not None:
            manifiesto.write_text(json.dumps(
                {"generado": "2026-08-22", "bucket": "b", "objetos": objetos}))
        conn = sqlite3.connect(":memory:")
        conn.executescript(common.SCHEMA)
        parches = (mock.patch.object(common, "ROOT", tmp),
                   mock.patch.object(common, "DATA", tmp / "data"),
                   mock.patch.object(common, "MEDIA", tmp / "data" / "media"),
                   mock.patch.object(common, "SNAPSHOTS", tmp / "data" / "snapshots"),
                   mock.patch.object(common, "MANIFIESTO_R2", manifiesto))
        return conn, parches

    def _reporte_en_base(self, conn, url, sha):
        conn.execute(
            "INSERT INTO citizen_reports (origen, id_externo, ts, media_url,"
            " media_local, media_sha256, estado, snapshot_date)"
            " VALUES ('chatmap',?,'2026-08-14T10:00:00',?,?,?,'recibido',"
            "'2026-08-22')",
            (url.rsplit("/", 1)[-1], url,
             "data/media/" + url.rsplit("/", 1)[-1], sha))

    def _corre_chatmap(self, tmp, conn, parches, *, cuerpo=b"VIDEO-NUEVO"):
        """Corre `chatmap.run()` contra una API falsa. Devuelve (salida, urls).

        `urls` son las que de verdad salieron a la red: es lo que se mide.
        """
        from unittest import mock
        import common
        import sources.chatmap as chatmap
        pedidas = []
        geojson = json.dumps({"features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-76.5, 3.4]},
            "properties": {"id": "r1", "time": "2026-08-14T10:00:00",
                           "message": "", "file": self.VIDEO}}]}).encode()

        def falso(req, **kw):
            pedidas.append(req.full_url)
            return TestPeticionesCondicionales.Resp(
                geojson if "/map/" in req.full_url else cuerpo)

        with parches[0], parches[1], parches[2], parches[3], parches[4], \
                mock.patch.object(chatmap, "MEDIA", tmp / "data" / "media"), \
                mock.patch.object(chatmap, "db",
                                  lambda: self.SinCerrar(conn)), \
                mock.patch.object(common.urllib.request, "urlopen",
                                  side_effect=falso):
            salida = chatmap.run()
        return salida, pedidas

    # --- 1. un vídeo nuevo se sigue descargando ----------------------------

    def test_un_video_nuevo_si_se_descarga(self):
        """Lo primero que hay que probar de un atajo: que no atajó de más."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[])
            salida, pedidas = self._corre_chatmap(tmp, conn, parches)
            self.assertIn(self.VIDEO, pedidas,
                          "un vídeo que el archivo no conoce TIENE que pedirse")
            self.assertEqual(salida["medios_nuevos"], 1)
            self.assertTrue((tmp / "data" / "media" / "aaaa-1.mp4").exists(),
                            "y su cuerpo tiene que quedar archivado")
            import hashlib
            self.assertEqual(
                conn.execute("SELECT media_sha256 FROM citizen_reports").fetchone()[0],
                hashlib.sha256(b"VIDEO-NUEVO").hexdigest())
            conn.close()

    # --- 2. lo ya archivado no se vuelve a pedir ---------------------------

    def test_un_video_del_manifiesto_no_se_vuelve_a_pedir(self):
        """El caso de los 2.648 MB: el cuerpo está en R2, no en el clon, y el
        manifiesto versionado lo dice. Mirar el disco era decir «no lo tengo»
        sobre algo archivado y verificado por sha256 hacía días."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 4096}])
            salida, pedidas = self._corre_chatmap(tmp, conn, parches)
            self.assertNotIn(self.VIDEO, pedidas,
                             "el archivo ya tiene ese cuerpo: pedirlo otra vez "
                             "son megas por nada")
            self.assertEqual(salida["medios_ya_archivados"], 1)
            self.assertEqual(salida["medios_nuevos"], 0)
            self.assertEqual(
                conn.execute("SELECT media_sha256 FROM citizen_reports").fetchone()[0],
                self.SHA_ARCHIVADO,
                "y el reporte conserva el sha que dice el archivo, no un hueco")
            conn.close()

    def test_la_base_basta_aunque_el_manifiesto_no_este(self):
        """Las dos vías son independientes a propósito: la base se reconstruye
        de los volcados al empezar la corrida, y el manifiesto viaja en el clon.
        Perder una no puede costar el ahorro."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp)          # sin manifiesto siquiera
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            salida, pedidas = self._corre_chatmap(tmp, conn, parches)
            self.assertNotIn(self.VIDEO, pedidas)
            self.assertEqual(salida["medios_ya_archivados"], 1)
            conn.close()

    def test_si_la_base_y_el_manifiesto_se_contradicen_se_descarga(self):
        """Un archivo que se desmiente a sí mismo no autoriza a saltarse nada.
        Se vuelve a pedir el cuerpo —que es lo que restablece la verdad— y la
        contradicción se canta aparte (R11)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": "f" * 64, "bytes": 4096}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            _, pedidas = self._corre_chatmap(tmp, conn, parches)
            self.assertIn(self.VIDEO, pedidas)
            conn.close()

    def test_la_contradiccion_del_archivo_se_canta(self):
        """M3: si merece explicarse, merece salir en las alertas."""
        import tempfile
        from unittest import mock
        import alerts
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": "f" * 64, "bytes": 4096}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                avisos = alerts.divergencias_del_archivo_de_activos(conn)
            tipos = {a["tipo"] for a in avisos}
            self.assertIn("manifiesto_r2_discrepa_de_la_base", tipos)
            conn.close()

    def test_un_video_de_la_base_que_falta_en_el_manifiesto_no_es_alerta(self):
        """`publish` escribe el manifiesto DESPUÉS de `alerts`: el día que llega
        un vídeo nuevo, que la base lo conozca y el manifiesto no es lo normal.
        Avisar de lo normal es la forma más rápida de que dejen de leerse las
        alertas.

        Cierra el CONJUNTO de tipos, no la ausencia de uno: mirar solo si falta
        `manifiesto_r2_discrepa_de_la_base` no guarda nada, porque en este
        escenario ese tipo es estructuralmente imposible —base y manifiesto no
        comparten ni una clave— y un aviso nuevo cualquiera pasaría entero.
        """
        import tempfile
        import alerts
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "otro.mp4", "sha256": "a" * 64, "bytes": 1}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                avisos = alerts.divergencias_del_archivo_de_activos(conn)
            self.assertEqual(
                {a["tipo"] for a in avisos},
                {"manifiesto_r2_con_objetos_sin_reporte"},
                "el único aviso legítimo aquí es el huérfano del manifiesto: "
                "que la base conozca un vídeo que el manifiesto todavía no "
                "tiene es el estado normal de un vídeo nuevo")
            conn.close()

    def test_el_huerfano_del_manifiesto_si_es_alerta(self):
        """Lo que el test de arriba NO puede dejar de guardar: un objeto en el
        bucket que ningún reporte respalda sí se canta."""
        import tempfile
        import alerts
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "huerfano.mp4", "sha256": "a" * 64, "bytes": 1}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                avisos = alerts.divergencias_del_archivo_de_activos(conn)
            aviso = [a for a in avisos
                     if a["tipo"] == "manifiesto_r2_con_objetos_sin_reporte"]
            self.assertEqual(len(aviso), 1)
            self.assertEqual(aviso[0]["objetos"], ["huerfano.mp4"])
            conn.close()

    def test_una_base_vacia_no_acusa_al_bucket(self):
        """El espejo del «sin manifiesto no hay nada que comparar», y el que de
        verdad muerde: si `rebuild_db` o `chatmap` fallan, R13 se los traga y la
        base llega vacía. Sin guarda, los 77 objetos salen como huérfanos y la
        alerta acusa al bucket de un fallo de la base — 77 avisos falsos, que es
        la forma más rápida de que nadie vuelva a leer una alerta."""
        import tempfile
        import alerts
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 4096},
                {"objeto": "bbbb-2.mp4", "sha256": "b" * 64, "bytes": 8}])
            with parches[0], parches[4]:          # base sin un solo reporte
                avisos = alerts.divergencias_del_archivo_de_activos(conn)
            self.assertEqual({a["tipo"] for a in avisos},
                             {"base_sin_reportes_ciudadanos"},
                             "sin base no se puede acusar al bucket de nada")
            conn.close()

    # --- 3. el reverso: un cuerpo que cambia se vuelve a archivar -----------

    def test_un_cuerpo_distinto_bajo_el_mismo_nombre_no_se_pisa(self):
        """Aquí es donde esta clase de optimización falla en silencio.

        Antes, si el fichero ya estaba y llegaba OTRO cuerpo, `fetch` no
        escribía nada y la fila del log declaraba el sha256 del cuerpo nuevo
        apuntando a un fichero con el viejo dentro: la única forma de que este
        archivo mienta sin que nadie lo note. Ahora se guarda al lado, con la
        firma de su contenido, y el viejo no se toca (principio de archivo).
        """
        import hashlib
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[])
            dest = tmp / "data" / "media" / "aaaa-1.mp4"
            dest.write_bytes(b"VIEJO")
            nuevo = b"REEDITADO EN ORIGEN"
            sha_nuevo = hashlib.sha256(nuevo).hexdigest()
            with parches[0], parches[1], parches[2], parches[3], parches[4], \
                    mock.patch.object(
                        common.urllib.request, "urlopen",
                        side_effect=lambda req, **kw:
                        TestPeticionesCondicionales.Resp(nuevo)):
                common.fetch(self.VIDEO, note="chatmap media aaaa-1.mp4",
                             conn=conn, save_to=dest)
            self.assertEqual(dest.read_bytes(), b"VIEJO",
                             "el cuerpo archivado no se sobrescribe jamás")
            spath, sha = conn.execute(
                "SELECT snapshot_path, sha256 FROM sources_log"
                " ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(sha, sha_nuevo)
            cuerpo = (tmp / spath)
            self.assertTrue(cuerpo.exists(),
                            "un sha256 en el log sin cuerpo detrás no es evidencia")
            self.assertEqual(hashlib.sha256(cuerpo.read_bytes()).hexdigest(), sha,
                             "el cuerpo al que apunta la fila tiene que ser ESE")
            self.assertNotEqual(cuerpo, dest)
            conn.close()

    # --- 4. R13: el archivo ilegible degrada, no rompe ---------------------

    def test_un_manifiesto_corrupto_no_rompe_la_corrida(self):
        """R13. Y degrada del lado seguro: si no se puede leer el manifiesto,
        no se da por archivado nada — se descarga."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, manifiesto_crudo="{no es json")
            salida, pedidas = self._corre_chatmap(tmp, conn, parches)
            self.assertNotIn("error", salida)
            self.assertIn(self.VIDEO, pedidas)
            conn.close()

    def test_sin_manifiesto_y_sin_base_no_se_da_nada_por_archivado(self):
        import tempfile
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp)
            with parches[0], parches[4]:
                self.assertIsNone(common.activo_archivado(self.VIDEO, conn))
                self.assertEqual(common.manifiesto_r2(), {})
            conn.close()

    def test_una_base_sin_la_tabla_no_tumba_al_guardian(self):
        """La corrida reconstruye la base antes de empezar, pero si esa
        reconstrucción fallara el guardián no puede llevarse la ingesta por
        delante: se queda sin esa vía y sigue con el manifiesto (R13)."""
        import sqlite3
        import tempfile
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 4096}])
            vacia = sqlite3.connect(":memory:")      # sin una sola tabla
            with parches[0], parches[4]:
                ya = common.activo_archivado(self.VIDEO, vacia)
            self.assertEqual(ya["sha256"], self.SHA_ARCHIVADO)
            self.assertEqual(ya["origen"], "manifiesto")
            vacia.close()

    # --- 5. el manifiesto no puede perder lo que ya sabía -------------------

    def test_el_manifiesto_no_pierde_los_bytes_sin_el_cuerpo_delante(self):
        """La trampa de segundo orden de este cambio: como la máquina de la
        corrida ya no descarga los vídeos, preguntarle solo al disco habría
        escrito `bytes: null` en los 77 objetos y el manifiesto habría perdido
        su columna entera en el primer commit automático."""
        import tempfile
        import publish
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 4096}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                objetos = publish.manifiesto_de_activos(conn)
            self.assertEqual(objetos, [{"objeto": "aaaa-1.mp4",
                                        "sha256": self.SHA_ARCHIVADO,
                                        "bytes": 4096}])
            conn.close()

    def test_los_bytes_salen_del_log_antes_que_del_manifiesto_viejo(self):
        """El registro de la descarga es archivo de primera mano; el manifiesto
        anterior es una copia suya. Ante duda, manda el log."""
        import tempfile
        import publish
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 1}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            conn.execute(
                "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                " snapshot_path,note) VALUES"
                " ('2026-08-15T10:00:00Z',?,200,?,4096,'data/media/aaaa-1.mp4',"
                "'chatmap media aaaa-1.mp4')", (self.VIDEO, self.SHA_ARCHIVADO))
            with parches[0], parches[4]:
                objetos = publish.manifiesto_de_activos(conn)
            self.assertEqual(objetos[0]["bytes"], 4096)
            conn.close()

    def test_sin_nadie_que_lo_sepa_los_bytes_se_omiten(self):
        """M10: donde falta el dato se calla el campo, nunca se escribe 0."""
        import tempfile
        import publish
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                objetos = publish.manifiesto_de_activos(conn)
            self.assertIsNone(objetos[0]["bytes"])
            conn.close()

    def test_los_bytes_nunca_son_los_de_otro_cuerpo(self):
        """Las tres vías van atadas al sha256 que se está escribiendo.

        `bytes` es el ÚNICO campo que la auditoría puede contrastar contra R2.
        Una cifra que no sea de ese cuerpo o suena en falso todos los días —y un
        aviso falso mata la lectura de las alertas— o enmascara una sustitución
        de verdad. Aquí las tres vías tienen un tamaño a mano y las tres son de
        OTRO contenido: el manifiesto tiene que salir sin cifra (M10).
        """
        import tempfile
        import publish
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": "d" * 64, "bytes": 111}])
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            # el disco tiene un cuerpo que no es ese
            (tmp / "data" / "media" / "aaaa-1.mp4").write_bytes(b"OTRA COSA")
            # y el log guarda la descarga de un tercer contenido
            conn.execute(
                "INSERT INTO sources_log (ts,url,http_status,sha256,bytes,"
                " snapshot_path,note) VALUES"
                " ('2026-08-15T10:00:00Z',?,200,?,222,'data/media/aaaa-1.mp4','x')",
                (self.VIDEO, "c" * 64))
            with parches[0], parches[4]:
                objetos = publish.manifiesto_de_activos(conn)
            self.assertEqual(objetos[0]["sha256"], self.SHA_ARCHIVADO)
            self.assertIsNone(
                objetos[0]["bytes"],
                "ningún tamaño a la vista es de ESE cuerpo: se omite el campo, "
                "no se coge el que haya más a mano")
            conn.close()

    def test_el_manifiesto_no_encoge_si_la_base_llega_vacia(self):
        """`rebuild_db` y `chatmap` son `step()`: R13 los deja fallar sin tumbar
        la corrida. Si el manifiesto se regenerara de una base vacía escribiría
        `objetos: []` y el bot lo commitearía — los cuerpos seguirían en R2 pero
        dejarían de estar declarados, que es justo lo que hace auditable el
        bucket."""
        import tempfile
        import publish
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[
                {"objeto": "aaaa-1.mp4", "sha256": self.SHA_ARCHIVADO,
                 "bytes": 4096}])
            with parches[0], parches[4]:          # base sin un solo reporte
                objetos = publish.manifiesto_de_activos(conn)
            self.assertEqual(objetos, [{"objeto": "aaaa-1.mp4",
                                        "sha256": self.SHA_ARCHIVADO,
                                        "bytes": 4096}],
                             "lo que ya se declaró archivado sigue declarado")
            conn.close()

    def test_una_foto_que_falta_del_repo_se_vuelve_a_traer(self):
        """Las vías de la base y del manifiesto valen para cuerpos que viven
        FUERA de git. Una foto sí viaja en el clon: para ella el archivo ES el
        disco, y fiarse de la base la declararía archivada para siempre — se
        vería en rojo, pero solo se arreglaría a mano."""
        import tempfile
        import common
        FOTO = "https://chatmap.hotosm.org/api/v1/media/bbbb-2.jpg"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[])
            self._reporte_en_base(conn, FOTO, "a" * 64)
            self._reporte_en_base(conn, self.VIDEO, self.SHA_ARCHIVADO)
            with parches[0], parches[4]:
                self.assertIsNone(
                    common.activo_archivado(
                        FOTO, conn, destino=tmp / "data" / "media" / "bbbb-2.jpg"),
                    "su cuerpo va en git: si no está, hay que traerlo otra vez")
                # y el vídeo, cuyo cuerpo NO va en git, sigue resolviéndose
                self.assertIsNotNone(
                    common.activo_archivado(self.VIDEO, conn,
                                            destino=tmp / "data" / "media" / "x"))
            conn.close()

    def test_un_destino_ilegible_no_tumba_la_descarga(self):
        """R13. Si la ruta de destino existe y no se deja leer —un directorio,
        un permiso—, el cuerpo que YA está en la mano se guarda al lado en vez
        de reventar la corrida."""
        import tempfile
        from unittest import mock
        import common
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conn, parches = self._mundo(tmp, objetos=[])
            dest = tmp / "data" / "media" / "aaaa-1.mp4"
            dest.mkdir(parents=True)              # un directorio, no un fichero
            with parches[0], parches[1], parches[2], parches[3], parches[4], \
                    mock.patch.object(
                        common.urllib.request, "urlopen",
                        side_effect=lambda req, **kw:
                        TestPeticionesCondicionales.Resp(b"CUERPO")):
                st, body = common.fetch(self.VIDEO, note="chatmap media",
                                        conn=conn, save_to=dest)
            self.assertEqual((st, body), (200, b"CUERPO"))
            spath = conn.execute(
                "SELECT snapshot_path FROM sources_log ORDER BY id DESC"
                " LIMIT 1").fetchone()[0]
            self.assertTrue((tmp / spath).is_file(),
                            "el cuerpo tenía que acabar en algún sitio legible")
            conn.close()

    # --- 6. la red que este cambio quitó, repuesta -------------------------

    def _auditar(self, tmp, *, disponible, bucket=None, manifiesto=None,
                 locales=()):
        """Corre `ingest/auditar_r2.py` sobre un repo de mentira.

        Devuelve (codigo_de_salida, salida, informe_archivado).
        """
        import json as _json
        import subprocess
        import sys as _sys
        raiz = Path(__file__).parent.parent
        (tmp / "data" / "media").mkdir(parents=True, exist_ok=True)
        for nombre in locales:
            (tmp / "data" / "media" / nombre).write_bytes(b"cuerpo")
        if manifiesto is not None:
            (tmp / "data" / "r2_manifest.json").write_text(_json.dumps(
                {"generado": "2026-08-22", "bucket": "b",
                 "objetos": manifiesto}))
        listado = tmp / "r2.tsv"
        listado.write_text("\n".join(f"{k}\t{v}" for k, v in (bucket or {}).items()))
        guion = (tmp / "ingest" / "auditar_r2.py")
        guion.parent.mkdir(parents=True, exist_ok=True)
        guion.write_bytes((raiz / "ingest" / "auditar_r2.py").read_bytes())
        (tmp / "ingest" / "common.py").write_bytes(
            (raiz / "ingest" / "common.py").read_bytes())
        r = subprocess.run(
            [_sys.executable, str(guion)], capture_output=True, text=True,
            env={"R2_DISPONIBLE": "1" if disponible else "0",
                 "R2_LISTADO": str(listado), "PATH": "/usr/bin:/bin"})
        destino = tmp / "data" / "auditoria_r2.json"
        informe = _json.loads(destino.read_text()) if destino.exists() else None
        return r.returncode, r.stdout + r.stderr, informe

    OBJ = {"objeto": "aaaa-1.mp4", "sha256": "e" * 64, "bytes": 6}

    def test_un_dia_sin_credenciales_y_con_medios_nuevos_pone_la_corrida_en_rojo(self):
        """**El agujero que abría este cambio.**

        El `sync` a R2 se salta entero si falta el secreto —token rotado, un
        fork—. Ese día un vídeo nuevo existe SOLO en el workspace del runner:
        git lo ignora y el workspace se destruye al acabar. Mientras tanto
        `publish` ya escribió su sha256 en el manifiesto y en la base, así que
        desde mañana el guardián lo da por archivado y no vuelve a pedirlo
        JAMÁS. Antes la redescarga diaria lo reofrecía; esa red la quitamos
        nosotros. Si esto puede pasar en verde, no hemos arreglado nada.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, salida, informe = self._auditar(
                tmp, disponible=False, manifiesto=[self.OBJ],
                locales=["aaaa-1.mp4"])
            self.assertEqual(codigo, 1,
                             "un cuerpo que solo existe en el workspace tiene "
                             "que poner la corrida en rojo, no dejar un aviso")
            self.assertIn("::error::", salida)
            self.assertEqual(informe["cuerpos_solo_en_el_workspace"],
                             ["aaaa-1.mp4"])
            self.assertFalse(informe["auditado"])

    def test_un_dia_sin_credenciales_y_sin_medios_nuevos_no_rompe(self):
        """El reverso: no hay nada que perder, así que no hay nada que romper.
        Un rojo diario en un fork sin secrets tampoco se leería (R13)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, salida, informe = self._auditar(
                tmp, disponible=False, manifiesto=[self.OBJ])
            self.assertEqual(codigo, 0)
            self.assertIn("::warning::", salida)
            self.assertEqual(informe["cuerpos_solo_en_el_workspace"], [])

    def test_un_cuerpo_que_el_manifiesto_declara_y_r2_no_tiene_pone_en_rojo(self):
        """Sin git y sin bucket ese cuerpo es irrecuperable: es lo más grave
        que le puede pasar a este archivo y no puede quedar en un aviso."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, salida, informe = self._auditar(
                tmp, disponible=True, bucket={}, manifiesto=[self.OBJ])
            self.assertEqual(codigo, 1)
            self.assertEqual(informe["faltan_en_r2"], ["aaaa-1.mp4"])
            self.assertIn("irrecuperables", salida)

    def test_un_bucket_que_cuadra_sale_en_verde(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, _, informe = self._auditar(
                tmp, disponible=True, bucket={"aaaa-1.mp4": 6},
                manifiesto=[self.OBJ], locales=["aaaa-1.mp4"])
            self.assertEqual(codigo, 0)
            self.assertEqual(informe["objetos_en_bucket"], 1)
            self.assertEqual(informe["faltan_en_r2"], [])
            self.assertEqual(informe["cuerpos_solo_en_el_workspace"], [])

    def test_el_que_pesa_distinto_y_el_que_sobra_avisan_sin_romper(self):
        """Un tamaño que no cuadra puede ser una sustitución o un desajuste
        nuestro: se mira, no se para la corrida."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, salida, informe = self._auditar(
                tmp, disponible=True,
                bucket={"aaaa-1.mp4": 99, "intruso.mp4": 7},
                manifiesto=[self.OBJ])
            self.assertEqual(codigo, 0)
            self.assertEqual(informe["difieren_en_tamano"],
                             [{"objeto": "aaaa-1.mp4", "manifiesto": 6, "r2": 99}])
            self.assertEqual(informe["sobran_en_r2"], ["intruso.mp4"])
            self.assertNotIn("::error::", salida)

    def test_la_auditoria_se_archiva_tambien_cuando_no_se_pudo_auditar(self):
        """Los `::error::` de Actions viven fuera del repositorio y caducan a
        los 90 días: un aviso que no se archiva no cumple el principio de
        archivo. «Ese día no pudimos mirar» también es información."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _, _, informe = self._auditar(tmp, disponible=False,
                                          manifiesto=[self.OBJ])
            self.assertIsNotNone(informe, "la auditoría tiene que quedar en el "
                                          "repositorio, no solo en el log de CI")
            self.assertIn("motivo", informe)
            self.assertIn("fecha", informe)
            self.assertEqual(informe["objetos_en_bucket"], None,
                             "M10: sin listado no se inventa un recuento")

    def test_sin_manifiesto_la_auditoria_avisa_y_no_revienta(self):
        """R13: si `publish` falló, este paso no puede escupir un traceback."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            codigo, salida, informe = self._auditar(
                tmp, disponible=True, bucket={"x.mp4": 1})
            self.assertEqual(codigo, 0)
            self.assertNotIn("Traceback", salida)
            self.assertIn("::warning::", salida)
            self.assertEqual(informe["objetos_en_manifiesto"], 0)

    def test_el_workflow_mira_el_resultado_de_la_auditoria(self):
        """La auditoría corre con `continue-on-error`, así que su 1 se queda
        dentro del paso: si nadie mira su `outcome`, el día cierra en verde con
        un cuerpo perdido y nadie se entera.

        Lo que NO puede hacer es apagar la publicación. Un bucket descuadrado no
        invalida el archivo del día, y dejar la web sin salir por eso es el
        error que tuvo la portada congelada dos días (R11: los supuestos
        avisan). Así que se exige lo uno y se prohíbe lo otro."""
        wf = (self.RAIZ / ".github/workflows/daily.yml").read_text(encoding="utf-8")
        self.assertIn("steps.auditoria.outcome == 'failure'", wf,
                      "nadie mira el resultado de la auditoría")
        rojo = wf.split("Marcar la corrida en rojo")[1]
        self.assertNotIn("auditoria", rojo.split("exit 1")[0],
                         "la auditoría no puede apagar la publicación")
        self.assertIn("::error::", wf.split("Avisar si la auditoría")[1][:400],
                      "la auditoría falla sin dejar anotación visible")

    def test_lo_que_git_ignora_y_se_descarga_esta_declarado(self):
        """El barrido, convertido en guardián.

        La firma del fallo es reconocible: **decidir si hay que traer algo
        mirando el disco, cuando el disco arranca vacío**. Solo puede pasar con
        contenido que git ignora. Hoy, bajo `data/`, eso es exactamente dos
        cosas: los audiovisuales ciudadanos —que van a R2— y el sqlite, que no
        se descarga de ninguna parte: se reconstruye de `data/dumps/*.csv`.

        Se miran `data/` y `feeds/`, que son las dos carpetas donde aterriza lo
        que entra de fuera. Si mañana alguien ignora otra ruta descargable, este
        test lo para y le obliga a decidir dónde vive su archivo antes de que la
        corrida empiece a bajarla entera cada día. Es el guardián que le habría
        faltado a `data/indexnow_estado.json`, que decide si hay que avisar a
        los buscadores mirando el disco y solo sobrevive porque nadie lo ignoró.
        """
        from common import ARCHIVO_EN_R2
        raiz = Path(__file__).parent.parent
        lineas = [l.strip() for l in
                  (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.strip().startswith("#")]
        # Un patrón SIN barra interior lo aplica git a cualquier profundidad:
        # un `*.mp4` suelto ignoraría `data/media/` sin nombrarlo, y el guardián
        # que solo mirase las líneas `data/…` no lo vería pasar.
        apuntan_al_archivo, sueltos = [], []
        for l in lineas:
            cuerpo = l.lstrip("!").rstrip("/")
            if l.startswith(("data/", "feeds/")):
                apuntan_al_archivo.append(l)
            elif "/" not in cuerpo:
                sueltos.append(l)
        esperados = {f"data/media/*{ext}" for ext in ARCHIVO_EN_R2}
        esperados |= {"data/monitor.sqlite", "data/monitor.sqlite-wal",
                      "data/monitor.sqlite-shm"}
        self.assertEqual(
            set(apuntan_al_archivo), esperados,
            "una ruta de data/ o feeds/ ignorada por git arranca VACÍA en la "
            "máquina de la corrida: si su contenido se descarga, el guardián "
            "que decide si hay que traerlo no puede mirar el disco (ver "
            "docs/DECISIONES.md, 24-ago-2026)")
        # Los patrones sueltos alcanzan al archivo aunque no lo nombren, así
        # que cada uno tiene que ser algo que NUNCA es contenido descargable:
        # cachés y artefactos de herramienta, credenciales, y el material
        # temporal del rediseño. Ninguno lo trae una fuente.
        self.assertEqual(
            set(sueltos),
            {"node_modules/", "__pycache__/", "*.pyc", ".DS_Store",
             "dist/", ".pytest_cache/", ".benchmarks/",
             ".env", ".env.*", "*.pem", "*.key", "*token*",
             "!package-lock.json",
             "prototipo/", "COORDINACION-REDISENO.md", "HANDOFF*.md",
             "dist-antes-*/"},
            "un patrón sin barra se aplica a cualquier profundidad, también "
            "dentro de data/: un «*.mp4» suelto ignoraría los vídeos sin "
            "nombrarlos y este guardián no lo vería pasar. Si lo que se añade "
            "es contenido que se descarga, su guardián no puede mirar el disco")

    def test_las_extensiones_de_r2_dicen_lo_mismo_en_las_cuatro_superficies(self):
        """M2. `.avi` llevaba desde el principio en `.gitignore` y en ninguna de
        las otras tres: un vídeo con esa extensión se habría descargado, no
        habría entrado en git, no habría subido a R2 y no habría figurado en el
        manifiesto — irrecuperable en cuanto el runner se apagara."""
        from common import ARCHIVO_EN_R2
        raiz = Path(__file__).parent.parent
        gitignore = (raiz / ".gitignore").read_text(encoding="utf-8")
        flujo = (raiz / ".github" / "workflows" / "daily.yml").read_text(
            encoding="utf-8")
        sync = flujo[flujo.index("aws s3 sync data/media/"):]
        sync = sync[:sync.index("--size-only")]
        for ext in ARCHIVO_EN_R2:
            self.assertIn(f"data/media/*{ext}", gitignore,
                          f"{ext} va a R2 pero git no lo ignora")
            self.assertIn(f'--include "*{ext}"', sync,
                          f"{ext} está fuera de git y el sync no lo sube: "
                          f"su cuerpo se perdería con el runner")
        self.assertEqual(
            sync.count("--include"), len(ARCHIVO_EN_R2),
            "el sync sube extensiones que nadie declara, o al revés")
    def test_la_corrida_diaria_regenera_la_imagen_antes_de_juzgarla(self):
        """El bucle que dejó la web dos días sin publicar (23 y 24-ago-2026).

        Regenerar en el deploy no basta: allí ya se hacía, pero el resultado
        no volvía al repo, así que el fichero versionado envejecía y el test
        de arriba suspendía cada mañana — y ese suspenso apagaba el deploy,
        que era lo único que regeneraba la imagen. Para romperlo hacen falta
        las dos mitades: generar ANTES de juzgar, y commitear lo generado."""
        daily = (self.RAIZ / ".github" / "workflows" / "daily.yml").read_text(
            encoding="utf-8")
        gen = daily.find("gen_og.py")
        juicio = daily.find("tests.test_unit")
        commit = daily.find("git add -A")
        self.assertNotEqual(gen, -1,
                            "la corrida diaria ya no regenera las imágenes "
                            "sociales: volverán a envejecer hasta suspender")
        self.assertLess(
            gen, juicio,
            "la corrida regenera la imagen DESPUÉS de juzgarla: el test la "
            "seguirá encontrando vieja cada mañana")
        self.assertIn(
            "site/og/", daily[commit:commit + 120],
            "lo regenerado no entra en el commit del día: mañana el repo "
            "vuelve a traer la imagen vieja y el bucle se reabre")


class TestUnaHipotesisCaidaNoApagaLaPublicacion(unittest.TestCase):
    """R11/R12 en el único sitio donde se pagaban con la web.

    Los días 23 y 24-ago-2026 el monitor archivó su día entero y no publicó
    nada: un test de datos en rojo tumbaba la corrida diaria, y pages.yml sólo
    despliega tras un `workflow_run` en verde. Nadie decidió dejar de publicar
    — lo decidió un aviso que no debía tener ese poder. La corrida fallida sí
    debe parar el deploy: entonces puede no haber día que publicar."""

    RAIZ = Path(__file__).parent.parent

    def pasos_que_paran_la_corrida(self):
        """Los bloques del daily que terminan en `exit 1`, con su condición."""
        daily = (self.RAIZ / ".github" / "workflows" / "daily.yml").read_text(
            encoding="utf-8")
        bloques = daily.split("      - name:")
        return [b for b in bloques if "exit 1" in b]

    def test_ninguna_hipotesis_puede_apagar_la_publicacion(self):
        """Si algún día se añade un paso de auditoría, el criterio es el mismo
        y conviene extender la lista de abajo: lo que AVISA no puede apagar la
        publicación; lo que falla al ARCHIVAR el día, sí — porque entonces no
        hay día que publicar."""
        culpables = [b for b in self.pasos_que_paran_la_corrida()
                     if "hipotesis" in b]
        self.assertEqual(
            culpables, [],
            "un paso que hace `exit 1` vuelve a mirar `steps.hipotesis`: eso "
            "pone la corrida en rojo, pages.yml se salta el deploy y la web "
            "se congela con el archivo del día ya guardado. Una hipótesis "
            "avisa (R11) y su caída puede ser buena noticia (R12)")

    def test_una_corrida_fallida_si_frena_el_deploy(self):
        """La otra mitad: sin esto, «no romper» se convierte en publicar un
        día que no se llegó a archivar."""
        frenos = self.pasos_que_paran_la_corrida()
        self.assertTrue(
            any("steps.corrida.outcome == 'failure'" in b for b in frenos),
            "nada frena ya la corrida diaria: si la ingesta falla, el deploy "
            "publicaría un día sin archivar")

    def test_la_hipotesis_caida_deja_constancia(self):
        """Avisar no es callar: R11 dice que los supuestos rotos no se rompen
        en silencio, y el verde sin anotación es silencio."""
        daily = (self.RAIZ / ".github" / "workflows" / "daily.yml").read_text(
            encoding="utf-8")
        avisos = [b for b in daily.split("      - name:")
                  if "steps.hipotesis.outcome == 'failure'" in b]
        self.assertTrue(avisos, "una hipótesis caída ya no deja ningún rastro")
        self.assertTrue(
            all("::error" in b or "::warning" in b for b in avisos),
            "el paso que atiende la hipótesis caída no la anuncia: se caería "
            "en silencio, que es justo lo que R11 prohíbe")


class TestLaPrecisionDeLoQuePublicamos(unittest.TestCase):
    """Los geojson que publicamos van a un metro, no a un milímetro.

    Copernicus entrega ocho decimales. Un hueco de cobertura satelital de
    kilómetros de lado no necesita precisión de milímetro para dibujarse, y
    esos decimales engordaban `not_analysed.geojson` un 29 % sin mover un
    píxel: 2.174 KB para 48 polígonos, la mitad de todo lo que la portada
    descargaba.

    **Lo que se recorta es NUESTRA derivación, no lo que dijo la fuente.** El
    snapshot de Copernicus conserva sus ocho decimales y su sha256, y sigue
    siendo la prueba de qué entregó. Este guardián vigila las dos mitades del
    trato, porque cada una falla sola: que lo publicado se recorte de verdad, y
    que el recorte no toque nada que no sea una coordenada.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
        from sources import copernicus_layers as cl
        cls.cl = cl

    def test_las_coordenadas_publicadas_pierden_el_milimetro(self):
        crudo = {"type": "Feature", "properties": {"aoi": "x"},
                 "geometry": {"type": "Polygon", "coordinates": [[
                     [-76.12345678, 3.87654321], [-76.11111111, 3.88888888],
                     [-76.12345678, 3.87654321]]]}}
        salida = self.cl._con_precision_de_metro(crudo)
        planas = [v for anillo in salida["geometry"]["coordinates"]
                  for par in anillo for v in par]
        # Camino 1: ninguna coordenada conserva más decimales de los permitidos.
        for v in planas:
            self.assertLessEqual(
                len(str(v).split(".")[-1]), self.cl.DECIMALES_PUBLICADOS,
                f"{v} sigue publicándose con precisión de milímetro")
        # Camino 2: y son EXACTAMENTE las que salen de redondear el original,
        # no otras. Contar dos veces por vías distintas es lo que caza al
        # guardián que se conforma con «alguna cosa cambió».
        esperadas = [round(v, self.cl.DECIMALES_PUBLICADOS)
                     for anillo in crudo["geometry"]["coordinates"]
                     for par in anillo for v in par]
        self.assertEqual(planas, esperadas)

    def test_el_recorte_no_toca_nada_que_no_sea_geometria(self):
        """Las propiedades viajan intactas: ahí hay identificadores y grados de
        daño, y redondear un número que no es una coordenada sería inventarse
        el dato de la fuente."""
        crudo = {"type": "Feature",
                 "properties": {"aoi": "EMSR916", "n": 3.14159265,
                                "damage_gra": "Destroyed", "vacio": None},
                 "geometry": {"type": "Point",
                              "coordinates": [-76.12345678, 3.87654321]}}
        salida = self.cl._con_precision_de_metro(crudo)
        self.assertEqual(salida["properties"], crudo["properties"])
        self.assertEqual(salida["geometry"]["coordinates"],
                         [-76.12346, 3.87654])

    def test_un_feature_sin_geometria_no_revienta(self):
        """R13: un feature raro degrada, no rompe la corrida entera."""
        for raro in ({"type": "Feature", "properties": {}},
                     {"type": "Feature", "properties": {}, "geometry": None},
                     {"type": "Feature", "properties": {}, "geometry": {}}):
            self.assertEqual(self.cl._con_precision_de_metro(raro), raro)

    def test_lo_que_se_escribe_al_disco_pasa_por_el_recorte(self):
        """El guardián de arriba prueba la función; este prueba que alguien la
        llama. Con la función perfecta y desenchufada, el fichero publicado
        seguiría llevando los ocho decimales — que es el fallo real."""
        fuente = (Path(__file__).resolve().parents[1]
                  / "ingest" / "sources" / "copernicus_layers.py"
                  ).read_text(encoding="utf-8")
        escritura = re.search(r"for kind, fname in \(.*?ensure_ascii=False\)\)",
                              fuente, re.S)
        self.assertIsNotNone(escritura, "cambió la forma de escribir los "
                             "geojson: revisa que el recorte siga aplicándose")
        self.assertIn("_con_precision_de_metro", escritura.group(0),
                      "los geojson se escriben sin pasar por el recorte: lo "
                      "publicado volvería a los ocho decimales")
