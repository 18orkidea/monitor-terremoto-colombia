"""Tests del generador de HTML estático (fichas municipales y tablas).

Estas páginas existen para que la cifra esté en el HTML servido: los crawlers
de IA no ejecutan JavaScript. Si un test de aquí falla, la página se seguiría
viendo perfecta en el navegador y estaría vacía para quien la tiene que citar
— por eso se comprueba el HTML, no el resultado en pantalla.
"""
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "deploy"))

import render_html as R


class TestFormato(unittest.TestCase):
    """R3: los «NA» de las fuentes son NULL + literal, jamás 0."""

    def test_none_nunca_es_cero(self):
        self.assertEqual(R.fmt(None), "—")
        self.assertEqual(R.fmt(None, 2), "—")
        self.assertNotEqual(R.fmt(None), "0")

    def test_cero_real_se_imprime(self):
        """Un 0 medido sí es un 0: la regla es no inventarlo, no ocultarlo."""
        self.assertEqual(R.fmt(0), "0")

    def test_locale_es_co(self):
        """Punto de miles, coma decimal — sin depender de `locale` del sistema."""
        self.assertEqual(R.fmt(1072), "1.072")
        self.assertEqual(R.fmt(2269983), "2.269.983")
        self.assertEqual(R.fmt(25.03, 2), "25,03")

    def test_slug_sin_tildes_ni_parentesis(self):
        self.assertEqual(R.slug("Nóvita"), "novita")
        self.assertEqual(R.slug("San José del Palmar"), "san-jose-del-palmar")
        self.assertEqual(R.slug("Riosucio (Chocó)"), "riosucio-choco")


class TestEscapado(unittest.TestCase):
    """Los titulares son texto de terceros: si no se escapan, rompen la página."""

    def test_titular_hostil_no_inyecta(self):
        sucio = '<script>alert(1)</script> "comillas" & ampersand'
        limpio = R.e(sucio)
        self.assertNotIn("<script>", limpio)
        self.assertIn("&lt;script&gt;", limpio)
        self.assertIn("&quot;", limpio)

    def test_medio_se_extrae_del_titular(self):
        """En Google News el campo `medio` guarda el feed, no el medio: el medio
        real va al final del titular tras « - ». Sin sufijo, no hay dato."""
        self.assertEqual(
            R.medio_de_titular({"titulo": "Réplica de 4,6 en Nóvita - El Colombiano"}),
            "El Colombiano")
        self.assertIsNone(R.medio_de_titular({"titulo": "Titular sin medio"}))


class TestFicha(unittest.TestCase):
    """Una ficha real, generada de los datos publicados."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.nombre = "Nóvita"
        cls.datos = R.datos_ficha(cls.nombre, cls.ctx)
        cls.html = R.render_ficha(cls.datos)

    def test_las_cifras_estan_en_el_html_servido(self):
        """El corazón del asunto: sin JavaScript, la cifra debe estar escrita."""
        m = self.ctx["idx"][self.nombre]
        for valor in (m["rud_familias"], m["rud_personas"], m["poblacion_2026"]):
            self.assertIn(R.fmt(valor), self.html,
                          f"la cifra {valor} no está en el HTML servido")

    def test_sin_javascript_ejecutable(self):
        scripts = re.findall(r"<script[^>]*>", self.html)
        self.assertTrue(scripts, "debe llevar al menos el JSON-LD")
        for s in scripts:
            self.assertIn("application/ld+json", s,
                          "las fichas no pueden llevar JS: los crawlers de IA no lo ejecutan")

    def test_svg_valido_y_accesible(self):
        svg = re.search(r"<svg.*?</svg>", self.html, re.S)
        self.assertIsNotNone(svg, "la ficha debe llevar su mapa estático")
        ET.fromstring(svg.group(0))                      # revienta si no es XML válido
        self.assertIn('role="img"', svg.group(0))
        self.assertIn("<title", svg.group(0))
        self.assertIn("<desc", svg.group(0))

    def test_json_ld_parseable_con_divipola(self):
        crudo = re.search(r'application/ld\+json">(.*?)</script>', self.html, re.S).group(1)
        ld = json.loads(crudo)
        self.assertEqual(ld["@type"], "Dataset")
        self.assertEqual(ld["spatialCoverage"]["identifier"]["value"],
                         self.ctx["idx"][self.nombre]["divipola"])

    def test_el_rud_se_describe_como_registro_progresivo(self):
        """El vocabulario lo fija docs/LIMITACIONES.md: «registro progresivo,
        NO un censo», y lo cargan las autoridades municipales — los damnificados
        no se autorregistran. Además hay verificación posterior, así que la cifra
        no puede leerse como un balance cerrado.

        Este test existe porque la primera versión de la ficha decía «censo
        declarativo»: contradecía el contrato del proyecto en las dos cosas."""
        self.assertIn("registro progresivo", self.html)
        self.assertIn("verificación posterior", self.html)
        self.assertIn("autoridades municipales", self.html)
        self.assertIn("sin registro aún", self.html)
        self.assertNotIn("censo", self.html.lower())

    def test_la_ausencia_satelital_se_dice_en_generico(self):
        """«Ningún producto satelital», no «ningún producto de Copernicus»:
        pueden entrar otros (UNOSAT, NISAR, HRSL) y la frase debe seguir siendo
        cierta el día que entren."""
        self.assertEqual(self.datos["satelite"], 0, "Nóvita no tiene producto satelital")
        self.assertIn("Ningún producto satelital de daño ha reportado daños", self.html)

    def test_seccion_de_lagunas_presente(self):
        self.assertIn("Qué no sabemos", self.html)
        self.assertIn("aviso--laguna", self.html)

    def test_usa_los_componentes_compartidos(self):
        """Homogeneidad: la ficha no inventa estilos, usa los del sitio."""
        for clase in ("destacado", "metric-strip", "metric-card", "migas", "note"):
            self.assertIn(clase, self.html, f"falta el componente .{clase}")

    def test_enlaza_de_vuelta_a_municipios(self):
        """Sin enlace de vuelta la ficha queda huérfana y no se descubre."""
        self.assertIn("municipios.html", self.html)


class TestSeleccion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def test_sin_senal_no_hay_ficha(self):
        """Noventa páginas vacías penalizarían al dominio entero."""
        fantasma = dict(self.ctx["idx"]["Nóvita"], municipio="Fantasma", rud_familias=None,
                        n_noticias=0, dyfi_respuestas=None, en_aoi_copernicus=False)
        ctx = dict(self.ctx, idx=dict(self.ctx["idx"], Fantasma=fantasma))
        self.assertFalse(R.es_elegible("Fantasma", ctx))

    def test_evidencia_puntual_es_subconjunto_estricto(self):
        """La tabla de portada muestra solo municipios con prueba sobre el
        terreno (satélite o comunidad): son menos que el área de influencia."""
        filas = R.municipios_con_evidencia_puntual(self.ctx)
        self.assertGreater(len(filas), 0)
        self.assertLess(len(filas), len(self.ctx["municipios"]))
        for f in filas:
            self.assertTrue(f["n_satelite"] or f["n_ciudadanos"])

    def test_los_huerfanos_no_se_atribuyen_a_nadie(self):
        """Sin polígonos municipales atribuimos por proximidad a la cabecera:
        un punto lejos de toda cabecera no se le cuelga al municipio más cercano."""
        conteo = self.ctx["conteo_ciudadanos"]
        self.assertIn("__huerfanos__", conteo)
        self.assertNotIn("__huerfanos__",
                         {f["municipio"] for f in R.municipios_con_evidencia_puntual(self.ctx)})


if __name__ == "__main__":
    unittest.main()


class TestDescubrimiento(unittest.TestCase):
    """Sitemap y llms-full.txt: lo que hace que las páginas se encuentren.

    Se generan en un directorio temporal: un test no puede depender de que
    alguien haya corrido el build antes."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile

        sys.path.insert(0, str(Path(__file__).parent.parent / "deploy"))
        import render_descubrimiento as D

        cls.D = D
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.res = R.run(cls.tmp)
        D.sitemap(cls.tmp)
        D.llms_full(cls.tmp)
        cls.xml = (cls.tmp / "sitemap.xml").read_text(encoding="utf-8")
        cls.llms = (cls.tmp / "llms-full.txt").read_text(encoding="utf-8")

    def test_sitemap_lista_todas_las_fichas(self):
        for slug in self.res["slugs"]:
            self.assertIn(f"/municipio/{slug}/", self.xml, f"falta {slug} en el sitemap")

    def test_sitemap_no_anuncia_nada_inexistente(self):
        """Un sitemap que promete páginas que no existen quema presupuesto de
        rastreo y resta confianza."""
        for slug in re.findall(r"/municipio/([^/]+)/", self.xml):
            self.assertTrue((self.tmp / "municipio" / slug / "index.html").exists(),
                            f"el sitemap anuncia /municipio/{slug}/ y no existe")

    def test_sitemap_es_xml_valido(self):
        ET.fromstring(self.xml)

    def test_lastmod_es_la_fecha_del_dato(self):
        """No la del build: si la corrida no trajo nada nuevo, anunciar una fecha
        fresca sería mentirle al buscador."""
        esperada = json.loads(
            (Path(__file__).parent.parent / "data/public/monitor.json").read_text()
        )["generado"][:10]
        self.assertIn(f"<lastmod>{esperada}</lastmod>", self.xml)

    def test_llms_full_lleva_las_cifras_en_locale_es_co(self):
        self.assertIn("25,03%", self.llms)          # coma decimal
        self.assertIn("10.016", self.llms)          # punto de millar
        self.assertNotRegex(self.llms, r"\d+\.\d{4}%",
                            "un porcentaje sin formatear se ha colado (p. ej. 21.5722%)")

    def test_llms_full_explica_como_leer_las_cifras(self):
        """Un sistema de IA que cite este archivo debe poder citar también las
        salvedades, o publicará el dato como si fuera un balance cerrado."""
        for frase in ("registro progresivo", "verificación posterior",
                      "sin registro aún", "nunca equivale a un balance oficial"):
            self.assertIn(frase, self.llms)

    def test_llms_full_enlaza_cada_ficha(self):
        self.assertEqual(self.llms.count("/municipio/"), len(self.res["slugs"]))


class TestRobots(unittest.TestCase):

    def test_permite_a_los_rastreadores_de_ia(self):
        """El proyecto quiere ser citado: el permiso va explícito para que un
        cambio futuro no los excluya sin querer."""
        robots = (Path(__file__).parent.parent / "deploy/root/robots.txt").read_text()
        for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"):
            self.assertIn(bot, robots, f"{bot} no está declarado en robots.txt")
        self.assertNotIn("Disallow: /", robots)


class TestTablaMunicipios(unittest.TestCase):
    """Fase B: la tabla de municipios, escrita en el HTML y con enlace a cada ficha."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.filas_municipios(cls.ctx)

    def test_una_fila_por_municipio(self):
        self.assertEqual(self.html.count("<tr "), len(self.ctx["municipios"]))

    def test_cada_fila_enlaza_a_su_ficha(self):
        """Sin este enlace las fichas quedan huérfanas: solo se descubrirían por
        el sitemap, que es un canal mucho más débil que un enlace del propio sitio."""
        enlaces = re.findall(r'href="(/municipio/[^"]+)"', self.html)
        self.assertEqual(len(enlaces), len(self.ctx["municipios"]))
        for url in enlaces:
            self.assertRegex(url, r"^/municipio/[a-z0-9-]+/$",
                             "el enlace a la ficha debe ser absoluto desde la raíz")
        self.assertIn('href="/municipio/novita/"', self.html)
        # relativo resolvería a /site/municipio/... desde /site/municipios.html
        self.assertNotIn('href="municipio/', self.html)

    def test_data_buscar_permite_filtrar_sin_reconstruir(self):
        self.assertEqual(self.html.count("data-buscar="), len(self.ctx["municipios"]))
        self.assertIn('data-buscar="cali valle del cauca"', self.html)

    def test_homonimo_de_departamento_no_recibe_prensa(self):
        """R10: no es que no haya prensa, es que no se puede afirmar cuál le
        corresponde. Ausencia de dato, nunca un cero."""
        hom = [m for m in self.ctx["municipios"] if m.get("homonimo_de_departamento")]
        if not hom:
            self.skipTest("no hay homónimos de departamento en los datos actuales")
        fila = R._celda_prensa(hom[0])
        self.assertIn("—", fila)
        self.assertNotIn(">0<", fila)

    def test_los_titulares_se_escapan(self):
        """La celda de prensa construye una URL con el nombre del municipio."""
        celda = R._celda_prensa({"municipio": 'A "B" & C', "n_noticias": 3})
        self.assertNotIn('"B"', celda.split("</a>")[0].split(">")[-1])


class TestEspejoConElFrontend(unittest.TestCase):
    """El formato y las etiquetas viven en dos lenguajes: Python los escribe en
    el build, JavaScript los sigue necesitando para el mapa. Si divergen, la
    misma cifra se leería distinta en la tabla y en el mapa — R10 aplicada al
    formato. Estos tests comparan ambas superficies."""

    @classmethod
    def setUpClass(cls):
        cls.ui = (Path(__file__).parent.parent / "site/ui.js").read_text(encoding="utf-8")

    def test_estados_de_municipio_coinciden(self):
        codigos_js = set(re.findall(r"^\s{4}(\w+): \[", self.ui, re.M))
        self.assertTrue(codigos_js, "no se pudo leer ESTADO_MUNICIPIO de ui.js")
        self.assertEqual(codigos_js, set(R.ESTADO_MUNICIPIO),
                         "ESTADO_MUNICIPIO ha divergido entre ui.js y render_html.py")

    def test_etiquetas_de_estado_coinciden(self):
        for codigo, (etiqueta, _, _) in R.ESTADO_MUNICIPIO.items():
            self.assertIn(f'"{etiqueta}"', self.ui,
                          f"la etiqueta de {codigo} no coincide con la de ui.js")

    def test_fmt_no_imprime_decimales_a_cero(self):
        """`UI.fmt` usa maximumFractionDigits: «7», no «7,0». El espejo en Python
        debe hacer lo mismo o la misma cifra se vería distinta en cada página."""
        self.assertIn("maximumFractionDigits", self.ui)
        self.assertEqual(R.fmt(7.0, 1), "7")
        self.assertEqual(R.fmt(7.5, 1), "7,5")

    def test_pct_nunca_redondea_a_cero_una_proporcion_real(self):
        """Un municipio con damnificados no puede leerse como municipio sin
        damnificados."""
        self.assertIn("<0,1 %", self.ui)
        self.assertEqual(R.pct(0.03), "<0,1 %")
        self.assertEqual(R.pct(None), "—")


class TestInyeccion(unittest.TestCase):

    def test_el_marcador_existe_en_el_repo(self):
        """Si alguien quita la marca, el build dejaría la tabla vacía en silencio."""
        html = (Path(__file__).parent.parent / "site/municipios.html").read_text()
        self.assertIn('<tbody data-gen="municipios">', html)

    def test_el_javascript_ya_no_construye_filas(self):
        """La presentación de la fila vive en un solo sitio: Python."""
        js = (Path(__file__).parent.parent / "site/municipios.js").read_text()
        self.assertIn("tablaHidratada", js)
        self.assertNotIn("tablaBuscable", js)
        self.assertNotIn("<tr>", js)


class TestTablaPortada(unittest.TestCase):
    """Fase C: la portada deja de organizarse por lo que el satélite decidió
    mirar y pasa a organizarse por dónde hay evidencia sobre el terreno."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.filas_portada(cls.ctx)
        cls.filas = R.municipios_con_evidencia_puntual(cls.ctx)

    def test_solo_municipios_con_evidencia_puntual(self):
        self.assertEqual(self.html.count("<tr "), len(self.filas))
        self.assertLess(len(self.filas), len(self.ctx["municipios"]),
                        "la portada debe mostrar menos que el área de influencia entera")

    def test_toda_fila_tiene_satelite_o_ciudadanos(self):
        for f in self.filas:
            self.assertTrue(f["n_satelite"] or f["n_ciudadanos"],
                            f'{f["municipio"]} está en portada sin evidencia puntual')

    def test_cada_fila_lleva_su_coordenada_para_el_mapa(self):
        """El clic en la fila centra el mapa; sin data-lat/data-lon el JavaScript
        tendría que volver a buscar el municipio en el JSON."""
        self.assertEqual(self.html.count("data-lat="), len(self.filas))
        self.assertEqual(self.html.count("data-lon="), len(self.filas))

    def test_cada_fila_enlaza_a_su_ficha(self):
        self.assertEqual(len(re.findall(r'href="/municipio/[^"]+"', self.html)),
                         len(self.filas))
        self.assertNotIn('href="municipio/', self.html)   # relativo daría 404

    def test_la_ausencia_de_evidencia_es_raya_no_cero(self):
        """R3: un municipio sin reportes ciudadanos no tiene «0 ciudadanos», tiene
        ausencia de dato en esa columna."""
        solo_sat = [f for f in self.filas if f["n_satelite"] and not f["n_ciudadanos"]]
        if not solo_sat:
            self.skipTest("no hay municipios con satélite y sin ciudadanos")
        fila = [l for l in self.html.split("\n") if solo_sat[0]["municipio"] in l][0]
        self.assertIn("—", fila)

    def test_el_marcador_existe_en_la_portada(self):
        html = (Path(__file__).parent.parent / "site/index.html").read_text()
        self.assertIn('<tbody data-gen="portada">', html)

    def test_el_javascript_ya_no_construye_la_tabla(self):
        js = (Path(__file__).parent.parent / "site/app.js").read_text()
        self.assertIn('tr[data-lat]', js)
        self.assertNotIn("for (const a of mon.aois)", js)

    def test_el_detalle_por_aoi_sigue_disponible(self):
        """Las columnas que solo existen por zona —vías, interrupciones, entrega—
        no caben en una tabla municipal, pero no se pierden: siguen en el CSV."""
        html = (Path(__file__).parent.parent / "site/index.html").read_text()
        self.assertIn("crosscheck.csv", html)
