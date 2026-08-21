"""Tests del generador de HTML estático (fichas municipales y tablas).

Estas páginas existen para que la cifra esté en el HTML servido: los crawlers
de IA no ejecutan JavaScript. Si un test de aquí falla, la página se seguiría
viendo perfecta en el navegador y estaría vacía para quien la tiene que citar
— por eso se comprueba el HTML, no el resultado en pantalla.
"""
import json
import re
import sys
import tempfile
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
        terreno —cualquiera de los satélites o la comunidad—: son menos que el
        área de influencia.

        Se pregunta por `n_evaluados`, que es la cifra única del municipio, y no
        por una lista de columnas escrita a mano: con dos satélites la lista se
        quedó corta el día que entró el tercero, y La Virginia —que solo mira
        ICube-SERTIT— entró en la tabla marcada como fila sin evidencia."""
        filas = R.municipios_con_evidencia_puntual(self.ctx)
        self.assertGreater(len(filas), 0)
        self.assertLess(len(filas), len(self.ctx["municipios"]))
        for f in filas:
            self.assertTrue(f["n_evaluados"] or f["n_ciudadanos"], f["municipio"])

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
        """El porcentaje de damnificados se comprobaba contra un literal
        («25,03%») que salía del RUD de aquel día. El RUD se mueve a diario,
        así que el guardián saltaba por deriva del dato y no por un fallo de
        formato: lo que vigila es el locale es-CO, no una cifra concreta.

        Las dos ramas que tocaron este test llegaron por separado a la misma
        conclusión. Se conserva la comprobación más específica del porcentaje
        —con su contexto, que lo distingue de cualquier otro— y se exige el
        punto de millar por su forma en vez de por un literal: así el test no
        depende de que ninguna cifra concreta siga estando ahí mañana."""
        self.assertRegex(self.llms, r"\(\d{1,2},\d{1,2}% de la población\)",
                         "los porcentajes del RUD han dejado de usar coma decimal")
        self.assertRegex(self.llms, r"\b\d{1,3}\.\d{3}\b",
                         "los millares van con punto")
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

    def test_la_columna_satelital_nombra_su_fuente(self):
        """Copernicus y UNOSAT miden cosas distintas —daño clasificado frente a
        edificios observados—, así que la celda las muestra por separado y con
        su fuente pegada. Sumarlas daría un número sin significado."""
        con_cop = R._celda_satelite({"unosat_edificios": None}, 335)
        self.assertIn("Copernicus", con_cop)
        con_uno = R._celda_satelite(
            {"unosat_edificios": 154, "unosat_observados": 55}, 0)
        self.assertIn("UNOSAT", con_uno)
        ambos = R._celda_satelite(
            {"unosat_edificios": 154, "unosat_observados": 55}, 335)
        self.assertIn("Copernicus", ambos)
        self.assertIn("UNOSAT", ambos)
        self.assertNotIn("489", ambos)          # 335 + 154 jamás se escribe

    def test_sin_satelite_es_un_guion_explicado(self):
        """R3: un guion no es un cero, y el título lo dice."""
        celda = R._celda_satelite({"unosat_edificios": None}, 0)
        self.assertIn("—", celda)
        self.assertIn("title=", celda)
        self.assertNotIn(">0<", celda)

    def test_las_filas_traen_los_filtros_del_rud(self):
        """Municipios usa los mismos filtros que el RUD: chips, departamento,
        orden por columna y paginación."""
        n = len(self.ctx["municipios"])
        self.assertEqual(self.html.count("data-depto="), n)
        self.assertEqual(self.html.count("data-chips="), n)
        for i in range(10):
            self.assertEqual(self.html.count(f'data-v{i}="'), n)

    def test_los_chips_cuadran_con_el_dato(self):
        # el criterio sale de `satelites_con_dato`, que recorre SATELITES: si se
        # escribe aquí a mano, el filtro «sin satélite» del navegador sigue
        # ofreciendo municipios que un satélite nuevo ya miró
        sin_sat = [m for m in self.ctx["municipios"]
                   if not R.satelites_con_dato(
                       m, self.ctx["conteo_satelite"].get(m["municipio"], 0))]
        self.assertEqual(len(re.findall(r'data-chips="[^"]*sin-satelite', self.html)),
                         len(sin_sat))

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

    @classmethod
    def _estados_de_ui(cls) -> dict:
        """Lee ESTADO_MUNICIPIO de ui.js como {clave: (etiqueta, color, explicación)}.

        Comparar solo las claves dejaba pasar lo que más se nota: que la misma
        insignia dijera una cosa en la tabla y otra en el mapa, o llevara otro
        color. El comentario de `render_html.py` prometía que este test comparaba
        ambas tablas; ahora las compara."""
        bloque = re.search(r"const ESTADO_MUNICIPIO = \{(.+?)\n  \};",
                           cls.ui, re.S)
        assert bloque, "no se pudo leer ESTADO_MUNICIPIO de ui.js"
        estados = {}
        # el «\n» extra es para que la última entrada, que queda pegada al cierre
        # del bloque, se lea como todas las demás: sin él se perdía en silencio
        entradas = re.findall(r"(\w+):\s*\[(.*?)\],\n", bloque.group(1) + "\n", re.S)
        for clave, cuerpo in entradas:
            trozos = re.findall(r'"((?:[^"\\]|\\.)*)"', cuerpo)
            etiqueta, color, explica = trozos[0], trozos[1], "".join(trozos[2:])
            estados[clave] = (etiqueta, color, explica)
        return estados

    def test_estados_de_municipio_coinciden(self):
        ui = self._estados_de_ui()
        self.assertTrue(ui, "no se pudo leer ESTADO_MUNICIPIO de ui.js")
        self.assertEqual(set(ui), set(R.ESTADO_MUNICIPIO),
                         "ESTADO_MUNICIPIO ha divergido entre ui.js y render_html.py")
        for clave, valor in R.ESTADO_MUNICIPIO.items():
            self.assertEqual(ui[clave], valor,
                             f"«{clave}» se lee distinto en la tabla y en el mapa")

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
            self.assertTrue(f["n_evaluados"] or f["n_ciudadanos"],
                            f'{f["municipio"]} está en portada sin evidencia puntual')

    def test_la_evidencia_de_unosat_tambien_entra_en_portada(self):
        """Viterbo y Anserma están evaluados edificio a edificio por el centro
        satelital de la ONU y no salían en la tabla de «evidencia sobre el
        terreno»: la portada sumaba sus edificios en la tarjeta y los negaba
        tres párrafos más abajo."""
        solo_unosat = [m["municipio"] for m in self.ctx["municipios"]
                       if m.get("unosat_edificios")
                       and not self.ctx["conteo_satelite"].get(m["municipio"])]
        if not solo_unosat:
            self.skipTest("ningún municipio lo mira solo UNOSAT")
        en_tabla = {f["municipio"] for f in self.filas}
        for nombre in solo_unosat:
            self.assertIn(nombre, en_tabla,
                          f"{nombre} tiene evidencia satelital y no está en portada")
            self.assertIn("UNOSAT", self.html,
                          "la columna satelital debe nombrar a UNOSAT")

    def test_la_nota_de_portada_no_miente_sobre_cuantos_miro_cada_fuente(self):
        """«Los satélites han mirado 11 municipios; la comunidad ha documentado
        36» está escrito a mano en site/index.html, y la primera mitad cambió
        el día que el conteo pasó a incluir UNOSAT. Si vuelve a moverse, este
        test dice el número nuevo en vez de dejar la frase envejecer sola."""
        # `n_evaluados` cuenta a los TRES satélites. Mientras esto sumó solo dos
        # columnas, el guardián daba por buena la nota que decía «9 municipios»
        # con once en su propia tabla: un guardián mal apuntado no protege nada.
        sat = len([f for f in self.filas if f["n_evaluados"]])
        ciu = len([f for f in self.filas if f["n_ciudadanos"]])
        html = (Path(__file__).parent.parent / "site/index.html").read_text(
            encoding="utf-8")
        m = re.search(r"satélites han mirado (\d+)\s*\n?\s*municipios; la comunidad "
                      r"ha documentado (\d+)", html)
        self.assertIsNotNone(m, "la nota de portada ya no dice cuántos miró cada fuente")
        self.assertEqual((int(m.group(1)), int(m.group(2))), (sat, ciu),
                         f"la nota de portada dice {m.group(1)}/{m.group(2)} y los "
                         f"datos dicen {sat}/{ciu}")

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


class TestSitioEnLaRaiz(unittest.TestCase):
    """El sitio vive en la raíz del dominio, no en /site/.

    La home del dominio tenía un meta-refresh y ningún contenido: cualquier
    enlace entrante al dominio aterrizaba en una página vacía."""

    RAIZ = Path(__file__).parent.parent

    def test_ninguna_pagina_se_referencia_bajo_site(self):
        for f in (self.RAIZ / "site").glob("*.html"):
            s = f.read_text(encoding="utf-8")
            self.assertNotIn("brechas.orkidea.eu/site/", s,
                             f"{f.name} sigue declarando su canonical bajo /site/")

    def test_las_rutas_de_datos_son_absolutas(self):
        """Relativas se romperían al cambiar la profundidad de la página; las
        fichas viven en /municipio/<slug>/, dos niveles más abajo."""
        for patron in ("*.js", "*.html"):
            for f in (self.RAIZ / "site").glob(patron):
                s = f.read_text(encoding="utf-8")
                self.assertNotIn("../data/", s, f"{f.name} usa una ruta relativa a datos")

    def test_el_sitemap_no_anuncia_urls_viejas(self):
        d = self.RAIZ / "deploy/render_descubrimiento.py"
        self.assertNotIn('"/site/', d.read_text(encoding="utf-8"))

    def test_llms_txt_apunta_a_las_urls_nuevas(self):
        s = (self.RAIZ / "deploy/root/llms.txt").read_text(encoding="utf-8")
        self.assertNotIn("orkidea.eu/site/", s)

    def test_el_build_deja_las_urls_viejas_vivas(self):
        """Una URL publicada es un compromiso: un archivo que critica a las
        fuentes que desaparecen no puede romper las suyas."""
        sh = (self.RAIZ / "deploy/build_dist.sh").read_text(encoding="utf-8")
        self.assertIn("mkdir -p dist/site", sh)
        self.assertIn("canonical", sh)
        self.assertIn("noindex", sh)   # el stub no compite con la página real


class TestEstiloDeLosNumeros(unittest.TestCase):
    """Libro de estilo de EL PAÍS, adoptado en docs/DECISIONES.md."""

    def test_del_cero_al_nueve_con_letras(self):
        """10.1: «seis reportes», pero «23 kilómetros»."""
        self.assertEqual(R.fmt_prosa(6), "seis")
        self.assertEqual(R.fmt_prosa(9), "nueve")
        self.assertEqual(R.fmt_prosa(10), "10")
        self.assertEqual(R.fmt_prosa(95), "95")

    def test_el_uno_concuerda_en_genero(self):
        self.assertEqual(R.fmt_prosa(1), "un")
        self.assertEqual(R.fmt_prosa(1, femenino=True), "una")

    def test_las_tablas_siguen_en_guarismos(self):
        """10.2: en una relación de cifras van todas en guarismos. fmt_prosa no
        sustituye a fmt: la tabla no puede decir «seis»."""
        html = R.filas_municipios(R.contexto())
        for palabra in ("seis", "siete", "ocho", "nueve"):
            self.assertNotIn(f">{palabra}<", html)

    def test_las_medidas_van_con_todas_sus_letras_en_prosa(self):
        """10.23: el símbolo solo en tablas y cuadros."""
        ctx = R.contexto()
        prosa = R.parrafo_respuesta(R.datos_ficha("Nóvita", ctx))
        self.assertIn("kilómetros", prosa)
        self.assertNotRegex(prosa, r"\d+ km\b")


class TestSatelites(unittest.TestCase):
    """Ninguna ficha puede afirmar «ningún producto satelital» cuando sí lo hay.

    El 19-ago-2026 entró UNITAR-UNOSAT como segundo satélite y las fichas seguían
    diciendo que el único activo era Copernicus: en Viterbo, evaluado por UNOSAT
    edificio a edificio, la ficha afirmaba lo contrario de lo que dice el dato.
    Estos tests existen para que el tercer satélite no repita el episodio."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def test_todo_campo_de_satelite_esta_contemplado(self):
        """Si aparece en los datos un `*_edificios` que el generador no conoce,
        este test falla antes de que 96 fichas publiquen una falsedad."""
        conocidos = {s["campo"] for s in R.SATELITES if s["campo"]}
        campos = {k for m in self.ctx["municipios"] for k in m
                  if k.endswith("_edificios")}
        self.assertTrue(campos <= conocidos,
                        f"satélite sin contemplar en SATELITES: {campos - conocidos}")

    def test_un_municipio_evaluado_solo_por_unosat_no_se_declara_sin_satelite(self):
        solo_unosat = [m for m in self.ctx["municipios"]
                       if m.get("unosat_edificios") is not None
                       and not m.get("en_aoi_copernicus")]
        if not solo_unosat:
            self.skipTest("ningún municipio evaluado solo por UNOSAT")
        d = R.datos_ficha(solo_unosat[0]["municipio"], self.ctx)
        prosa = R.parrafo_respuesta(d)
        self.assertNotIn("Ningún producto satelital", prosa)
        self.assertIn("UNITAR-UNOSAT", prosa)

    def test_llms_full_no_niega_ninguna_evidencia_satelital(self):
        """El mismo bug, en el fichero que leen los sistemas de IA.

        `llms-full.txt` decidía la cobertura satelital solo con
        `en_aoi_copernicus`, así que escribía «ningún producto satelital» sobre
        Anserma, Manizales y Viterbo —los tres municipios que aportan los
        edificios de UNOSAT— y también sobre Yumbo, que tiene 3 edificios de
        Copernicus con coordenada dentro pero ninguna zona encima. Que la ficha
        lo dijera bien no bastaba: esta superficie también afirma."""
        import importlib.util
        ruta = Path(__file__).parent.parent / "deploy" / "render_descubrimiento.py"
        spec = importlib.util.spec_from_file_location("render_descubrimiento", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # CUALQUIER evidencia satelital, venga de donde venga y esté o no
        # dentro de una zona delimitada: Yumbo tiene 3 edificios de Copernicus
        # y ninguna AOI encima, y este fichero también lo negaba.
        con_evidencia = [m["municipio"] for m in self.ctx["municipios"]
                         if m.get("unosat_edificios") is not None
                         or self.ctx["conteo_satelite"].get(m["municipio"])]
        if not con_evidencia:
            self.skipTest("ningún municipio con evidencia satelital")
        with tempfile.TemporaryDirectory() as tmp:
            mod.llms_full(Path(tmp))
            texto = (Path(tmp) / "llms-full.txt").read_text(encoding="utf-8")
        for nombre in con_evidencia:
            i = texto.find(f"### {nombre} (")
            self.assertGreater(i, -1, f"{nombre} no está en llms-full.txt")
            # hasta el encabezado siguiente: el bloque del vecino no cuenta
            fin = texto.find("\n### ", i + 1)
            bloque = texto[i:fin if fin > 0 else len(texto)]
            self.assertNotIn("ningún producto satelital", bloque,
                             f"llms-full.txt niega el satélite en {nombre}")
            self.assertTrue("UNITAR-UNOSAT" in bloque or "Copernicus" in bloque,
                            f"llms-full.txt no atribuye la evaluación de {nombre}")

    def test_la_negativa_no_nombra_un_solo_producto(self):
        """«hoy el único activo es Copernicus» caducó en cuanto entró UNOSAT: la
        frase debe nombrar a todos los que se vigilan, o a ninguno."""
        # El municipio se elige por AUSENCIA de todos los satélites de SATELITES.
        # Mientras el criterio fue «sin UNOSAT y fuera de zona Copernicus», el
        # primer candidato pasó a ser Roldanillo —77 edificios de ICube-SERTIT—,
        # así que el test que vigila la negativa buscaba la negativa en una ficha
        # que afirma. Un guardián mal apuntado no protege nada.
        sin = [m for m in self.ctx["municipios"]
               if not m.get("en_aoi_copernicus")
               and not R.satelites_con_dato(
                   m, self.ctx["conteo_satelite"].get(m["municipio"], 0))]
        prosa = R.parrafo_respuesta(R.datos_ficha(sin[0]["municipio"], self.ctx))
        self.assertIn("Ningún producto satelital", prosa)
        self.assertNotIn("el único activo", prosa)
        # y los nombra a TODOS: una negativa que se olvida de un servicio miente
        for sat in R.SATELITES:
            self.assertIn(sat["prosa"], prosa,
                          f"la negativa no nombra a {sat['nombre']}")

    def test_los_estados_de_municipio_siguen_en_espejo_con_ui(self):
        ui = (Path(__file__).parent.parent / "site/ui.js").read_text(encoding="utf-8")
        for estado in ("evaluado_unosat", "evaluado_satelite"):
            self.assertIn(estado, ui)
            self.assertIn(estado, R.ESTADO_MUNICIPIO)


class TestTablaRud(unittest.TestCase):
    """Fase D: el registro oficial, municipio a municipio, escrito en el HTML.

    Es el dato que nadie más publica: el agregador que compite con el monitor
    declara que las cifras oficiales «no existen consolidadas»."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.filas_rud(cls.ctx)
        cls.municipios = cls.ctx["rud"]["municipios"]

    def test_una_fila_por_municipio_registrado(self):
        self.assertEqual(self.html.count("<tr "), len(self.municipios))

    def test_cada_fila_lleva_lo_que_el_navegador_necesita(self):
        """Filtrar, ordenar y paginar sin volver a leer el JSON ni reconstruir
        la fila: el valor de cada columna viaja en data-v{i}."""
        n = len(self.municipios)
        self.assertEqual(self.html.count("data-buscar="), n)
        self.assertEqual(self.html.count("data-depto="), n)
        self.assertEqual(self.html.count("data-chips="), n)
        for i in range(8):
            self.assertEqual(self.html.count(f'data-v{i}="'), n,
                             f"falta el valor de la columna {i} en alguna fila")

    def test_las_etiquetas_de_los_filtros_cuadran_con_el_dato(self):
        con_destruidas = sum(1 for m in self.municipios if (m.get("viv_destruidas") or 0) > 0)
        self.assertEqual(len(re.findall(r'data-chips="[^"]*destruidas', self.html)),
                         con_destruidas)
        nuevos = sum(1 for m in self.municipios if m.get("nuevo"))
        self.assertEqual(len(re.findall(r'data-chips="[^"]*nuevos', self.html)), nuevos)

    def test_un_municipio_sin_dato_no_recibe_un_cero(self):
        """R3: «sin registro aún» no es «sin daño», y un hueco no es un cero."""
        sin = [m for m in self.municipios if m.get("poblacion_2026") is None]
        if not sin:
            self.skipTest("todos los municipios registrados tienen población")
        fila = [l for l in self.html.split("\n") if sin[0]["municipio"] in l][0]
        self.assertIn("—", fila)

    def test_el_javascript_ya_no_construye_las_filas(self):
        js = (Path(__file__).parent.parent / "site/rud.js").read_text(encoding="utf-8")
        self.assertIn("tablaHidratada", js)
        self.assertNotIn("tablaBuscable", js)
        self.assertNotIn("<tr>", js)

    def test_el_marcador_existe(self):
        html = (Path(__file__).parent.parent / "site/rud.html").read_text(encoding="utf-8")
        self.assertIn('<tbody data-gen="rud">', html)


class TestBalances(unittest.TestCase):
    """Fase D: la tabla trazable de balances citados en medios."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.filas_balances(cls.ctx)

    def test_una_fila_por_snapshot(self):
        self.assertEqual(self.html.count("<tr "),
                         len(self.ctx["oficiales"].get("items") or []))

    def test_los_liveblogs_se_marcan_en_el_html(self):
        """R8: si la marca solo la pusiera el navegador, quien lee sin
        JavaScript vería las cifras de un liveblog sin saber que lo es."""
        items = self.ctx["oficiales"]["items"]
        esperados = sum(1 for i in items if R.es_liveblog(i))
        self.assertEqual(self.html.count(">liveblog<"), esperados)
        self.assertGreater(esperados, 0, "el corpus debería traer algún liveblog")

    def test_la_deteccion_de_liveblog_es_espejo_de_ui_js_y_del_worker(self):
        """R8 dice «fuente única», pero la expresión vive en TRES lenguajes:
        ui.js, este render y el worker. Comparar término a término no bastaba:
        las tres tenían las mismas palabras y dos de ellas no llevaban límite
        de palabra, así que «directo» casaba dentro de «directorio» en el sitio
        y no en el worker. Ahora se compara la expresión entera."""
        raiz = Path(__file__).parent.parent
        alternancia = ("en vivo|directo|live[-_\\s]?news|última hora|"
                       "ultima hora|minuto a minuto|liveblog")
        ui = (raiz / "site/ui.js").read_text(encoding="utf-8")
        worker = (raiz / "workers/ai-view/src/index.js").read_text(encoding="utf-8")
        self.assertIn(f"\\b({alternancia})\\b", ui,
                      "ui.js debe llevar el límite de palabra")
        self.assertIn(f"\\b({alternancia})\\b", R._LIVEBLOG.pattern,
                      "render_html debe llevar el límite de palabra")
        # el worker escribe los términos sin tilde en «ultima hora» y con ella
        # en «última hora», igual que los otros dos
        self.assertIn("\\b(en vivo|directo|", worker,
                      "el worker debe seguir llevando el límite de palabra")

    def test_un_directorio_no_es_un_liveblog(self):
        """El falso positivo que el límite de palabra evita, comprobado sobre
        el código real de las dos superficies en Python y JavaScript."""
        self.assertFalse(R.es_liveblog({"title": "El directorio de medios"}))
        self.assertTrue(R.es_liveblog({"title": "Terremoto en directo"}))

    def test_cada_fila_dice_de_quien_es_la_cifra(self):
        """R9: no es el balance oficial, es lo que la prensa publica citándolo."""
        self.assertIn("Prensa temporal", self.html)
        self.assertEqual(self.html.count('data-url="'), self.html.count("<tr "))

    def test_el_feed_se_publica_como_producto_propio(self):
        """Vivía en un worker de cuenta ajena: si se apaga, la página se quedaba
        vacía aunque el dato estuviera archivado."""
        feed = self.ctx["oficiales"]
        self.assertIn("archivado_de", feed)
        self.assertIn("snapshots", feed["archivado_de"]["snapshot"])
        js = (Path(__file__).parent.parent / "site/balances.js").read_text(encoding="utf-8")
        self.assertIn('"/data/public/oficiales.json"', js)
        self.assertNotIn("OFICIALES_BASE}/oficiales.json", js)


class TestTitulares(unittest.TestCase):
    """Fase D: los titulares más recientes, escritos en el HTML.

    No son todos a propósito: 5.250 piezas serían megabytes que ningún
    rastreador digiere, y paginarlas en sesenta páginas casi idénticas sería
    volumen sin sustancia. Los titulares por municipio ya viven donde importan,
    en la ficha de cada municipio."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.filas_noticias(cls.ctx)

    def test_escribe_los_mas_recientes_y_no_mas(self):
        self.assertEqual(self.html.count("<li>"),
                         min(R.TITULARES_EN_HTML, len(self.ctx["noticias"])))

    def test_el_enlace_al_agregador_se_declara(self):
        """Quien lea sin JavaScript debe saber que el enlace no lleva al medio."""
        via = sum(1 for n in sorted(self.ctx["noticias"],
                                    key=lambda x: x.get("fecha") or "", reverse=True
                                    )[:R.TITULARES_EN_HTML] if R.via_google_news(n))
        self.assertEqual(self.html.count("vía Google News"), via)
        self.assertGreater(via, 0)

    def test_el_medio_es_la_cabecera_no_el_feed(self):
        """En los enlaces de Google News el campo `medio` guarda el nombre del
        feed. Sin cabecera declarada no se inventa ninguna (R3)."""
        self.assertIsNone(R.medio_de({"url": "https://news.google.com/x", "medio": "Google News — Cali"}))
        self.assertEqual(R.medio_de({"url": "https://news.google.com/x",
                                     "medio_canonico": "El Tiempo"}), "El Tiempo")
        self.assertEqual(R.medio_de({"url": "https://eltiempo.com/x", "medio": "El Tiempo"}),
                         "El Tiempo")

    def test_es_espejo_de_los_helpers_del_frontend(self):
        ui = (Path(__file__).parent.parent / "site/ui.js").read_text(encoding="utf-8")
        self.assertIn("news.google.com", ui)
        self.assertIn("medio_canonico", ui)

    def test_los_titulares_se_escapan(self):
        """Vienen de feeds ajenos: sin escapar, uno hostil rompe la página."""
        self.assertNotIn("<script>", self.html)
        self.assertNotRegex(self.html, r'<a href="[^"]*"[^>]*>[^<]*<[a-z]')

    def test_el_marcador_existe(self):
        html = (Path(__file__).parent.parent / "site/noticias.html").read_text(encoding="utf-8")
        self.assertIn('data-gen="noticias"', html)


class TestSeoCheck(unittest.TestCase):
    """El verificador que vigila que lo publicado siga siendo encontrable.

    Existe porque la regresión típica es invisible: el JavaScript rellena la
    página en el navegador y nadie nota que llegó vacía a quien no lo ejecuta."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))
        import seo_check
        cls.seo = seo_check
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)

    def test_caza_un_contenedor_vacio(self):
        """Es exactamente la regresión que motiva el verificador."""
        (self.tmp / "municipios.html").write_text(
            '<link rel="canonical" href="/x"><table>'
            '<tbody data-gen="municipios"></tbody></table>' + "palabra " * 900,
            encoding="utf-8")
        res = self.seo.revisar(self.tmp)
        self.assertTrue(any("quedó vacío" in f for f in res["fallos"]))

    def test_caza_un_sitemap_que_promete_lo_que_no_existe(self):
        (self.tmp / "sitemap.xml").write_text(
            "<urlset><url><loc>https://brechas.orkidea.eu/municipio/fantasma/</loc>"
            "</url></urlset>", encoding="utf-8")
        res = self.seo.revisar(self.tmp)
        self.assertTrue(any("y no existe" in f for f in res["fallos"]))

    def test_el_artefacto_real_pasa(self):
        dist = Path(__file__).parent.parent / "dist"
        if not dist.exists():
            self.skipTest("no hay dist construido")
        res = self.seo.revisar(dist)
        self.assertEqual(res["fallos"], [], "el artefacto publicado tiene fallos de SEO")


class TestCoherenciaDeLaFicha(unittest.TestCase):
    """Una ficha no puede afirmar y negar lo mismo en la misma pantalla.

    Ocurrió: en Viterbo, Manizales y Anserma la entradilla decía «154 edificios
    clasificados por UNITAR-UNOSAT» y dos párrafos más abajo «ningún producto
    satelital ha reportado daños aquí». Es el peor fallo posible en un proyecto
    cuya única moneda es que se pueda confiar en lo que publica."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def _texto(self, municipio):
        html = R.render_ficha(R.datos_ficha(municipio, self.ctx))
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    # La negación de la mirada satelital se busca por PATRÓN, no por lista
    # cerrada de frases. La lista cerrada ya falló: tenía las tres variantes
    # conocidas y no la cuarta —«Donde el satélite no ha mirado, cada reporte
    # cuenta», dentro del bloque de reportes ciudadanos—, así que la suite pasó
    # en verde con la contradicción publicada en seis fichas. Un guardián que
    # enumera casos solo protege de los que ya ocurrieron; este describe la
    # forma del error: una frase que habla del satélite y niega que mirara.
    NIEGA = re.compile(
        r"(?:ningún|ninguno|ningun|nadie|no)\b[^.;]{0,80}?"
        r"\b(?:ha|han)\s+(?:mirado|evaluado|reportado|clasificado|analizado|"
        r"cartografiado)"
        r"|no hay nada que cruzar", re.I)
    HABLA_DEL_SATELITE = re.compile(r"satélite|satelital|Copernicus|UNOSAT|SERTIT", re.I)

    def _niegan(self, texto: str) -> list:
        """Las frases del texto que niegan que el satélite mirara."""
        return [f.strip() for f in re.split(r"[.;]", texto)
                if self.NIEGA.search(f) and self.HABLA_DEL_SATELITE.search(f)]

    def test_ninguna_ficha_afirma_y_niega_el_satelite(self):
        for m in self.ctx["municipios"]:
            if not R.es_elegible(m["municipio"], self.ctx):
                continue
            t = self._texto(m["municipio"])
            if "documentado por satélite" not in t:
                continue
            niegan = self._niegan(t)
            self.assertFalse(niegan,
                             f"{m['municipio']}: la ficha afirma la mirada satelital "
                             f"y la niega en la misma página → {niegan}")

    def test_un_municipio_visto_solo_por_unosat_no_se_declara_sin_mirar(self):
        solo_unosat = [m for m in self.ctx["municipios"]
                       if m.get("unosat_edificios") is not None
                       and not self.ctx["conteo_satelite"].get(m["municipio"])]
        if not solo_unosat:
            self.skipTest("ningún municipio evaluado solo por UNOSAT")
        t = self._texto(solo_unosat[0]["municipio"])
        self.assertIn("UNITAR-UNOSAT", t)
        self.assertNotIn("no hay nada que cruzar", t)

    def test_la_ficha_declara_el_codigo_inconsistente_de_unosat(self):
        """Zarzal publica 201 edificios y los 201 traen un código de evento que
        el propio producto de UNOSAT contradice. La advertencia vivía solo en
        la tabla de municipios y en el globo del mapa: la ficha —la página que
        se indexa y se cita— daba la cifra desnuda. Publicar el número sin lo
        único que hace falta para juzgarlo es la mitad del dato."""
        con_marca = [m for m in self.ctx["municipios"]
                     if m.get("unosat_codigo_inconsistente")]
        if not con_marca:
            self.skipTest("ningún municipio con código de evento inconsistente")
        for m in con_marca:
            if not R.es_elegible(m["municipio"], self.ctx):
                continue
            t = self._texto(m["municipio"])
            self.assertIn("código de evento", t,
                          f"{m['municipio']}: la ficha da los edificios de UNOSAT "
                          f"sin decir que {m['unosat_codigo_inconsistente']} de "
                          f"ellos llevan una etiqueta que la fuente contradice")
            self.assertIn(R.fmt(m["unosat_codigo_inconsistente"]), t)

    def test_la_ficha_no_dice_que_los_discrepantes_queden_fuera(self):
        """INVERTIDO el 21-ago-2026: mientras esos puntos se excluían, la
        superficie correcta decía «no sumados al total». Ahora suman, y esa
        frase sería falsa: se prohíbe explícitamente para que no vuelva desde
        un copiar y pegar del texto viejo."""
        for m in self.ctx["municipios"]:
            if not m.get("unosat_codigo_inconsistente"):
                continue
            if not R.es_elegible(m["municipio"], self.ctx):
                continue
            t = self._texto(m["municipio"]).lower()
            for frase in ("no sumados al total", "no se suman al total",
                          "quedan fuera del total"):
                self.assertNotIn(frase, t,
                                 f"{m['municipio']}: la ficha dice «{frase}» y "
                                 f"esos edificios sí cuentan desde el 21-ago-2026")

    def test_la_tabla_de_fuentes_no_nombra_un_unico_satelite(self):
        """«único activo sobre el evento» caducó el día que entró el segundo."""
        for m in ("Nóvita", "Viterbo"):
            self.assertNotIn("único activo", self._texto(m))


class TestMunicipioSinCabecera(unittest.TestCase):
    """Un municipio sin coordenadas no puede tumbar el build entero.

    `municipios_dinamicos` da de alta lo que aparece en el RUD aunque el
    catálogo DIVIPOLA no traiga su cabecera —el registro oficial manda, y un
    municipio que entre mañana no puede perderse por falta de curación
    manual—, y esas filas llegan aquí con `lat`/`lon` en nulo. Hoy no hay
    ninguna: por suerte, no por diseño. El día que la hubiera,
    `asigna_a_municipios` reventaba con KeyError antes de escribir la primera
    ficha y `mapa_svg` habría dibujado el municipio en el golfo de Guinea.

    Lo que se exige no es que la ficha salga completa: es que salga, y que
    diga qué le falta (R3)."""

    NOMBRE = "Municipio Sin Cabecera"

    @classmethod
    def setUpClass(cls):
        base = R.contexto()
        modelo = base["idx"]["Nóvita"]
        fantasma = {**modelo, "municipio": cls.NOMBRE, "lat": None, "lon": None}
        cls.ctx = dict(base,
                       municipios=[*base["municipios"], fantasma],
                       idx={**base["idx"], cls.NOMBRE: fantasma})

    def test_el_reparto_de_puntos_ni_revienta_ni_le_atribuye_nada(self):
        """Sin cabecera no se le puede colgar ningún punto: queda fuera del
        reparto, que es distinto de recibir un cero."""
        conteo = R.asigna_a_municipios(self.ctx["chatmap"], self.ctx["municipios"])
        self.assertNotIn(self.NOMBRE, conteo)
        self.assertIn("__huerfanos__", conteo)

    def test_el_mapa_no_se_dibuja_en_el_cero_cero(self):
        self.assertEqual(R.mapa_svg(self.ctx["idx"][self.NOMBRE], [], []), "")

    def test_la_ficha_sale_y_cuenta_que_falta_la_coordenada(self):
        html = R.render_ficha(R.datos_ficha(self.NOMBRE, self.ctx))
        self.assertIn("no tiene la coordenada de la cabecera", html)
        self.assertNotIn("<svg", html)

    def test_el_json_ld_no_publica_una_coordenada_inventada(self):
        html = R.render_ficha(R.datos_ficha(self.NOMBRE, self.ctx))
        ld = json.loads(re.search(
            r'<script type="application/ld\+json">(.+?)</script>', html).group(1))
        self.assertIn("identifier", ld["spatialCoverage"])
        self.assertNotIn("geo", ld["spatialCoverage"])

    def test_la_tabla_de_portada_no_escribe_una_coordenada_nula(self):
        """El clic en la fila centra el mapa; `data-lat="None"` sería un NaN en
        el navegador y, peor, una coordenada con pinta de dato."""
        ctx = dict(self.ctx, conteo_ciudadanos={**self.ctx["conteo_ciudadanos"],
                                                self.NOMBRE: 3})
        html = R.filas_portada(ctx)
        self.assertIn(self.NOMBRE, html)
        self.assertNotIn('data-lat="None"', html)
