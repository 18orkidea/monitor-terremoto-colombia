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
                                        "news_items.medio_dominio"])
        self.assertEqual(migrar(conn), [], "segunda pasada no hace nada")
        fila = conn.execute(
            "SELECT medio, medio_canonico FROM news_items").fetchone()
        self.assertEqual(fila, ("m", None), "la fila vieja se conserva intacta")
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
        cls.index = (cls.RAIZ / "site/index.html").read_text(encoding="utf-8")
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
        el «daño posible» de UNOSAT no puede desaparecer dentro de la suma."""
        for cifra, que in ((self.cop, "los edificios de Copernicus"),
                           (self.uno, "los edificios de UNOSAT"),
                           (self.posibles, "el «daño posible» de UNOSAT")):
            self.assertIn(self._es(cifra), self.index,
                          f"la portada no declara {que} ({self._es(cifra)})")

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
