"""Tests del generador de HTML estático (fichas municipales y tablas).

Estas páginas existen para que la cifra esté en el HTML servido: los crawlers
de IA no ejecutan JavaScript. Si un test de aquí falla, la página se seguiría
viendo perfecta en el navegador y estaría vacía para quien la tiene que citar
— por eso se comprueba el HTML, no el resultado en pantalla.
"""
import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "deploy"))

import render_html as R

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")


def correr_ui(expresion: str, datos="null"):
    """Evalúa una expresión sobre `window.UI` con el ui.js real.

    Testear una copia de la regla en Python sería testear nada: cuando este
    módulo replica algo que vive en JavaScript, la comparación se hace contra
    el original ejecutándolo.

    **Los datos viajan por la entrada estándar, no dentro del guion.** Hasta el
    25-ago-2026 se interpolaban en el script y este iba por `-e`, así que el
    argumento crecía con el monitor: el día que la serie pasó del límite de
    `execve` saltó `OSError [Errno 7] Argument list too long`. En Linux, que lo
    tiene mucho más bajo que macOS — verde en el portátil y rojo en el CI, y
    más rojo cuantos más datos hubiera. Es el mismo reparto que ya usaban
    `render_html.py` y `alerts.py`, con su comentario: **guion fijo por
    argumento, datos por stdin.**
    """
    script = ("global.window = {};"
              f"require({json.dumps(str(ROOT / 'site' / 'ui.js'))});"
              "const UI = window.UI;"
              "const mon = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              f"console.log(JSON.stringify({expresion}));")
    r = subprocess.run([NODE, "-e", script],
                       input=json.dumps(datos, ensure_ascii=False),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:500]}")
    return json.loads(r.stdout)


# ---------------------------------------------------- lectura del JSON-LD
# Un bloque JSON-LD no es un nodo: es un árbol, y puede ser un `@graph` con
# varios. Google valida recursivamente CUALQUIER nodo, esté a la profundidad que
# esté —de ahí que el `isPartOf` con un Dataset embebido se le exigiera como
# dataset independiente—. Estas tres funciones son la única forma de leerlo en
# los tests: mirar `ld["@type"]` del primer bloque es lo que dejó pasar el bug.

def bloques_ld(html: str) -> list:
    """Todos los bloques `application/ld+json` de un documento, ya parseados."""
    return [json.loads(crudo) for crudo in re.findall(
        r'<script type="application/ld\+json"[^>]*>(.+?)</script>', html, re.S)]


def nodos_ld(valor):
    """Cada objeto del árbol, a cualquier profundidad."""
    if isinstance(valor, dict):
        yield valor
        for v in valor.values():
            yield from nodos_ld(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from nodos_ld(v)


def tipos_ld(nodo: dict) -> list:
    """`@type` admite una cadena o una lista; se lee siempre como lista."""
    t = nodo.get("@type", [])
    return [t] if isinstance(t, str) else list(t)


def datasets_ld(html: str) -> list:
    """Los nodos `Dataset` de un documento, vengan de donde vengan."""
    return [n for bloque in bloques_ld(html) for n in nodos_ld(bloque)
            if "Dataset" in tipos_ld(n)]


def ficha_del_corpus(ctx, criterio, queja):
    """La ficha del PRIMER municipio elegible —por orden alfabético— que cumple
    el criterio, o `AssertionError` con `queja` si ya no queda ninguno.

    Nombrar un municipio a mano en un test envejece con los datos y lo hace en
    silencio, porque el test sigue pareciendo correcto: hasta el 24-ago-2026
    varios tests usaban «Cartago» como ejemplo de ficha sin evidencia, y el 23
    Cartago recibió sus siete primeros reportes ciudadanos — cuatro rojos sin
    que nadie hubiera roto nada. Alfabético para que dos corridas del mismo
    corpus elijan el mismo y el fallo sea reproducible; y si un día no queda
    candidato, el test lo cuenta como noticia en vez de dar un rojo opaco (R12).
    """
    for m in sorted(ctx["municipios"], key=lambda x: x["municipio"]):
        nombre = m["municipio"]
        if not R.es_elegible(nombre, ctx):
            continue
        d = R.datos_ficha(nombre, ctx)
        if criterio(d):
            return d
    raise AssertionError(queja)


SIN_EVIDENCIA_AGOTADA = (
    "ya no queda ningún municipio elegible SIN evidencia: el mapa cubre todas "
    "las fichas. Es una gran noticia y este test pierde su caso — "
    "replantearlo, no buscarle un municipio a mano")


SIN_RUD_FABRICADO = "Municipio sin registro (caso fabricado)"


def municipio_sin_rud(ctx: dict) -> tuple[str, dict]:
    """Un municipio elegible al que el RUD todavía NO ha llegado, y el contexto
    en el que leerlo.

    Devuelve el caso real mientras quede alguno —alfabético, como
    `ficha_del_corpus`—. **El 25-ago-2026 dejó de quedar**: la captura del 24
    llevó el registro de 251 a 347 municipios y cubrió el catálogo entero, así
    que ningún dato recorre ya la rama «la fuente calla» de R3. Es una buena
    noticia y a la vez la peor forma de perder tres guardianes: siguen verdes
    y no comprueban nada (hasta el 24 el caso era Palmira, que hoy tiene 171
    familias inscritas).

    Por eso, cuando el corpus se queda sin caso, se fabrica uno: una copia del
    primer municipio elegible por otra señal —prensa, satélite o vecinos— con
    sus cifras del RUD en blanco. Lleva «caso fabricado» en el nombre para que
    nadie lo confunda con un municipio de verdad, y en cuanto el registro
    vuelva a dejar a alguien fuera estos tests vuelven a medir sobre el dato.
    """
    reales = sorted(m["municipio"] for m in ctx["municipios"]
                    if m.get("rud_familias") is None
                    and R.es_elegible(m["municipio"], ctx))
    if reales:
        return reales[0], ctx
    for modelo in sorted(ctx["municipios"], key=lambda x: x["municipio"]):
        fabricado = {**modelo, "municipio": SIN_RUD_FABRICADO,
                     "rud_familias": None, "rud_personas": None,
                     "rud_viv_destruidas": None, "rud_viv_averiadas": None,
                     "tasa_rud_pct": None, "delta_familias": None}
        nuevo = {**ctx, "municipios": [*ctx["municipios"], fabricado],
                 "idx": {**ctx["idx"], SIN_RUD_FABRICADO: fabricado}}
        if R.es_elegible(SIN_RUD_FABRICADO, nuevo):
            return SIN_RUD_FABRICADO, nuevo
    raise AssertionError(
        "ningún municipio del corpus sigue siendo elegible sin su RUD: la "
        "ficha ya solo existe porque el registro oficial la nombra, y estos "
        "tres guardianes de R3 no tienen dónde apoyarse")


def _dias_entre(desde: str, hasta: str) -> list:
    """Todos los días, uno a uno, entre dos fechas ISO (extremos incluidos)."""
    a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


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

    def test_javascript_no_sustituye_el_documento_estatico(self):
        """La interacción se mejora con JS, pero cifras, prosa y SVG siguen en HTML.

        Nóvita tiene reportes ciudadanos y por eso carga el controlador pequeño;
        Leaflet y el JSON municipal no aparecen como recursos iniciales.
        """
        scripts = re.findall(r"<script[^>]*>", self.html)
        self.assertTrue(scripts, "debe llevar al menos el JSON-LD")
        for s in scripts:
            self.assertTrue("application/ld+json" in s or
                            'src="/ui.js' in s or 'src="/municipio.js' in s,
                            f"script inesperado en la ficha: {s}")
        self.assertIn('role="img"', self.html)
        self.assertNotIn("leaflet.css", self.html)
        self.assertNotIn("leaflet.js", self.html)

    def test_svg_valido_y_accesible(self):
        svg = re.search(r"<svg.*?</svg>", self.html, re.S)
        self.assertIsNotNone(svg, "la ficha debe llevar su mapa estático")
        ET.fromstring(svg.group(0))                      # revienta si no es XML válido
        self.assertIn('role="img"', svg.group(0))
        self.assertIn("<title", svg.group(0))
        self.assertIn("<desc", svg.group(0))

    def test_json_ld_parseable_con_divipola(self):
        """Extendido el 23-ago-2026, y por un motivo: **no cazó el bug**.

        Miraba `ld["@type"]` del primer bloque, y el fallo estaba un nivel más
        abajo — un `isPartOf` que embebía un segundo `Dataset` sin
        `description`, publicado así en las 208 fichas—. Un guardián que solo
        mira la raíz no guarda el árbol. Ahora se leen todos los bloques y se
        baja a cualquier profundidad, que es como valida Google.
        """
        datasets = datasets_ld(self.html)
        self.assertEqual(len(datasets), 1,
                         "una ficha describe UN dataset: si hay dos, alguno va "
                         "anidado dentro del otro y se validará por separado")
        ld, = datasets
        self.assertEqual(ld["spatialCoverage"]["identifier"]["value"],
                         self.ctx["idx"][self.nombre]["divipola"])
        for campo in ("name", "description"):
            self.assertTrue((ld.get(campo) or "").strip(),
                            f"el dataset de la ficha se publica sin «{campo}»")

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

    def test_historial_de_cali_conserva_cada_captura_diaria(self):
        """La ficha municipal usa el mismo histórico que la gráfica general.

        La pérdida de los cierres del 18 y 19 pasó inadvertida porque la ficha
        seguía mostrando una tabla plausible con los extremos. Lo que se vigila
        es que no falte ningún día entre el primero y el último: enumerar las
        fechas a mano solo aguantaba hasta la corrida siguiente —este test se
        cayó al llegar la captura del 21-ago— y una lista caduca no es un
        guardián, es una alarma que hay que apagar cada mañana (R12)."""
        serie = [fecha for fecha, _ in R.datos_ficha("Cali", self.ctx)["serie"]]
        self.assertGreaterEqual(len(serie), 5, "el histórico de Cali se ha encogido")
        self.assertEqual(serie[0], "2026-08-16", "la primera captura del RUD")
        self.assertEqual(serie, sorted(serie), "las capturas van en orden")
        esperadas = _dias_entre(serie[0], serie[-1])
        self.assertEqual(serie, esperadas,
                         f"faltan capturas: {sorted(set(esperadas) - set(serie))}")
        # La tabla da una fila por CAMBIO desde el 27-ago-2026, así que ya no
        # lleva escrita cada fecha; lo que no puede es perder capturas por el
        # camino. Se comprueba lo mismo con la misma fuerza: lo que la tabla
        # declara haber capturado tiene que sumar la serie entera.
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        registro = html[html.find('id="registro"'):]
        registro = registro[:registro.find("</section>")]
        declaradas = [int(n) for n in re.findall(r'<tr data-capturas="(\d+)"', registro)]
        self.assertEqual(sum(declaradas), len(serie),
                         f"la tabla declara {sum(declaradas)} capturas y la "
                         f"serie tiene {len(serie)}: alguna se perdió al agrupar")
        self.assertIn(R.fecha_corta(serie[0]), html, "falta la primera captura")
        self.assertIn(R.fecha_corta(serie[-1]), html, "falta la última captura")

    def test_duracion_municipal_se_calcula_entre_fechas(self):
        """Una captura ausente no debe acortar artificialmente el periodo.

        Con la serie recortada a sus extremos, la prosa tiene que seguir midiendo
        la distancia entre las dos fechas, no el número de puntos que le quedan.
        """
        datos = R.datos_ficha("Cali", self.ctx)
        serie = [fecha for fecha, _ in datos["serie"]]
        dias = len(_dias_entre(serie[0], serie[-1])) - 1
        html = R.render_ficha(dict(datos, serie=[datos["serie"][0], datos["serie"][-1]]))
        self.assertIn(f"en {R.fmt_prosa(dias)} días", html)
        self.assertNotIn("en un día", html)

    def test_un_salto_real_menor_de_una_decima_no_se_publica_como_cero(self):
        """Cuatro familias sobre 11.826 son un salto real del 0,03 %.

        La prosa municipal debe aplicar el mismo suelo que `pct()`: redondearlo
        a cero convertiría un cambio pequeño en ausencia de cambio."""
        primero = {"familias": 11826, "personas": 20000,
                   "viv_destruidas": 0, "viv_averiadas": 0}
        ultimo = dict(primero, familias=11830)
        pct_delta = ((ultimo["familias"] - primero["familias"])
                     / primero["familias"] * 100)
        datos = dict(
            self.datos,
            serie=[("2026-08-20", primero), ("2026-08-21", ultimo)],
            primero=primero,
            ultimo=ultimo,
            delta=4,
            pct_delta=pct_delta,
        )

        html = R.render_ficha(datos)

        self.assertTrue("un salto del &lt;0,1 % en un día" in html,
                        "el salto real pequeño no usa el suelo de pct()")
        self.assertFalse("un salto del 0 %" in html,
                         "el salto real pequeño se publicó como cero")


class TestMapaEvidencias(unittest.TestCase):
    """La segunda pestaña existe solo con puntos y no pesa hasta que se pide.

    Los municipios NO se nombran a mano: se eligen del corpus del día. Hasta el
    24-ago-2026 aquí estaba escrito «Cartago» como ejemplo de ficha sin
    evidencia, y el 23 Cartago recibió sus siete primeros reportes ciudadanos:
    cuatro tests en rojo desde entonces, sin que nadie hubiera roto nada. Un
    caso citado por su nombre envejece con los datos —la misma familia de fallo
    que las cifras escritas a mano en la prosa—, y aquí el envejecimiento es
    silencioso porque el test sigue pareciendo correcto. Elegir del corpus
    también hace que el test cuente algo cuando ya no queda candidato: que el
    mapa cubre todo lo elegible, que sería una gran noticia (R12)."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.sin_evidencia = cls._elegir(
            lambda d: not d["hay_evidencia"], SIN_EVIDENCIA_AGOTADA)
        cls.solo_ciudadana = cls._elegir(
            lambda d: (d["evidencia"]["conteos"]["ciudadanos"]
                       and not d["evidencia"]["conteos"]["satelite"]),
            "ningún municipio tiene solo evidencia ciudadana: o el satélite "
            "llegó a todas partes, o la ingesta ciudadana dejó de entrar")
        cls.solo_satelite = cls._elegir(
            lambda d: (d["evidencia"]["conteos"]["satelite"]
                       and not d["evidencia"]["conteos"]["ciudadanos"]),
            "ningún municipio tiene solo evidencia satelital: revisar si el "
            "cruce ciudadano se está aplicando donde no debe")

    @classmethod
    def _elegir(cls, criterio, queja):
        return ficha_del_corpus(cls.ctx, criterio, queja)

    def test_visible_con_cualquiera_de_las_dos_clases_de_evidencia(self):
        ciudadano, satelite = self.solo_ciudadana, self.solo_satelite
        self.assertTrue(ciudadano["evidencia"]["conteos"]["ciudadanos"])
        self.assertEqual(ciudadano["evidencia"]["conteos"]["satelite"], 0)
        self.assertTrue(ciudadano["hay_evidencia"])
        self.assertTrue(satelite["evidencia"]["conteos"]["satelite"])
        self.assertEqual(satelite["evidencia"]["conteos"]["ciudadanos"], 0)
        self.assertTrue(satelite["hay_evidencia"])
        self.assertFalse(self.sin_evidencia["hay_evidencia"])

    def test_pestanas_accesibles_y_panel_diferido(self):
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        self.assertIn('role="tablist"', html)
        self.assertIn(">Situación</button>", html)
        self.assertIn(">Mapa de evidencias</button>", html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertRegex(html, r'aria-labelledby="tab-evidencias-cali" hidden')
        self.assertIn('data-evidencia="/data/public/municipios/cali/evidencia.json"', html)
        self.assertIn('src="/municipio.js?v=dev"', html)
        self.assertNotIn("leaflet.css", html)
        self.assertNotIn("leaflet.js", html)

    def test_sin_puntos_no_hay_pestanas_ni_javascript(self):
        html = R.render_ficha(self.sin_evidencia)
        self.assertNotIn('role="tablist"', html)
        self.assertNotIn("municipio.js", html)
        scripts = re.findall(r"<script[^>]*>", html)
        self.assertTrue(all("application/ld+json" in s for s in scripts))

    def test_el_svg_solo_enlaza_a_portada_si_no_hay_mapa_de_evidencias(self):
        nombre = self.sin_evidencia["muni"]["municipio"]
        con_evidencia = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        sin_evidencia = R.render_ficha(self.sin_evidencia)
        self.assertNotIn('class="mapa-enlace"', con_evidencia)
        # el href se escapa como URL y el rótulo como HTML: son dos escapes
        # distintos sobre el mismo nombre, y el test usa los del generador
        self.assertRegex(
            sin_evidencia,
            r'<a href="/\?municipio=%s#mapa" class="mapa-enlace"[^>]*>\s*<svg'
            % re.escape(urllib.parse.quote(nombre)),
        )
        self.assertIn(
            f'aria-label="Abrir {R.e(nombre)} en el mapa interactivo"',
            sin_evidencia)

    def test_build_escribe_solo_paquetes_necesarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            R.run(raiz)
            cali = raiz / "data/public/municipios/cali/evidencia.json"
            vacio = (raiz / "data/public/municipios"
                     / self.sin_evidencia["slug"] / "evidencia.json")
            self.assertTrue(cali.exists())
            self.assertFalse(vacio.exists(),
                             f"{self.sin_evidencia['muni']['municipio']} no tiene "
                             f"evidencia y aun así se le escribió paquete")
            paquete = json.loads(cali.read_text(encoding="utf-8"))
            conteos = paquete["conteos"]
            self.assertEqual(conteos["total"], conteos["satelite"] + conteos["ciudadanos"])
            self.assertGreater(conteos["copernicus"], 0)
            self.assertGreater(conteos["sertit"], 0)
            self.assertEqual(conteos["unosat"], 0)
            self.assertTrue(all((f["properties"].get("media") or "/").startswith("/")
                                for f in paquete["capas"]["ciudadanos"]["features"]))

    def test_cache_busting_alcanza_las_fichas_generadas(self):
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        self.assertIn("/styles.css?v=dev", html)
        build = (Path(__file__).parent.parent / "deploy/build_dist.sh").read_text(
            encoding="utf-8")
        genera = build.index("python3 deploy/render_html.py dist")
        versiona = build.index("find dist -type f -name '*.html' -exec sed")
        self.assertLess(genera, versiona,
                        "el hash debe aplicarse después de escribir las fichas municipales")


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


class _Arbol(HTMLParser):
    """Recorre un fragmento de filas y anota, por cada nodo, su camino.

    Sin dependencias: la fila es HTML generado por este mismo módulo, no hay
    que tolerar marcado ajeno. Guarda (a) un camino por cada texto no vacío y
    (b) un camino por cada elemento, para poder preguntar si el CSS lo sube por
    encima del enlace estirado."""

    VACIOS = {"br", "img", "input", "meta", "link"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.textos = []      # (texto, camino)
        self.elementos = []   # (tag, attrs, camino incluido él mismo)
        self.hijos = {}       # id del padre -> nº de elementos que cuelgan de él

    def _abre(self, tag, attrs):
        nodo = (tag, dict(attrs), len(self.elementos))
        self.elementos.append((tag, dict(attrs), self.pila + [nodo]))
        # los vacíos (un <br>) no cuentan: no pueden enseñar nada al ratón
        if self.pila and tag not in self.VACIOS:
            self.hijos[self.pila[-1][2]] = self.hijos.get(self.pila[-1][2], 0) + 1
        return nodo

    def handle_starttag(self, tag, attrs):
        nodo = self._abre(tag, attrs)
        if tag not in self.VACIOS:
            self.pila.append(nodo)

    def handle_startendtag(self, tag, attrs):
        self._abre(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.pila) - 1, -1, -1):
            if self.pila[i][0] == tag:
                del self.pila[i:]
                return

    def handle_data(self, data):
        if data.strip():
            self.textos.append((data.strip(), list(self.pila)))


def _por_encima_de_la_capa(camino, clase_estirada):
    """¿Lo sube el CSS por encima del enlace estirado?

    Espejo en Python de las dos reglas de `site/styles.css`:
    `td > *:not(.fila-enlace)` y `.fila-enlace > strong`. Lo que cuelga de un
    elemento ya subido va dentro de su contexto de apilamiento, así que hereda
    la posición: basta con mirar quién es el hijo del `<td>`."""
    tags = [n[0] for n in camino]
    if "td" not in tags:
        return False
    i = tags.index("td")
    if len(camino) <= i + 1:
        return False                      # cuelga pelado del <td>
    attrs_hijo = camino[i + 1][1]
    if clase_estirada not in (attrs_hijo.get("class") or "").split():
        return True                       # td > * : subido
    # dentro del ancla estirada solo se sube el <strong> del nombre
    return len(camino) > i + 2 and camino[i + 2][0] == "strong"


class TestFilaPulsableDeMunicipios(unittest.TestCase):
    """La fila entera lleva a la ficha, sin JavaScript y con un solo href.

    El patrón —un pseudoelemento del ancla estirado sobre la fila— tiene un
    efecto colateral medido, no supuesto: en Chrome, arrastrar el ratón sobre
    «26.377» devolvía una selección vacía, y los `title` que explican estado,
    población y satélites dejaban de aparecer al pasar por encima. En una tabla
    de cifras eso es una pérdida real, así que el contenido de la fila vive por
    encima de la capa y **nada puede colgar pelado de un `<td>`**: un texto sin
    elemento no se puede subir por CSS.

    Estos tests son estructurales a propósito (M12): no miden píxeles, miden
    que ningún dato de la fila quede debajo de la capa."""

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.filas = R.filas_municipios(cls.ctx)
        cls.arbol = _Arbol()
        cls.arbol.feed(cls.filas)
        m = re.search(r"#municipios-tabla \.([\w-]+)::after\s*\{([^}]*)\}", cls.CSS)
        cls.regla_capa = m
        cls.clase = m.group(1) if m else "fila-enlace"

    def test_el_css_estira_la_misma_clase_que_escribe_el_build(self):
        """Las dos mitades del pareado. Renombrar una sola deja la fila sin
        zona de clic y **no se ve nada roto**: el enlace del nombre sigue ahí."""
        self.assertIsNotNone(self.regla_capa,
                             "no hay regla que estire ningún ancla en la tabla")
        cuerpo = self.regla_capa.group(2)
        self.assertIn("position: absolute", cuerpo)
        self.assertIn("inset: 0", cuerpo)
        clases = {c for tag, attrs, _cam in self.arbol.elementos if tag == "a"
                  for c in (attrs.get("class") or "").split()}
        self.assertIn(self.clase, clases,
                      f"el CSS estira .{self.clase} y las filas no la escriben")

    def test_el_css_sube_el_contenido_de_la_fila_por_encima_de_la_capa(self):
        """La otra mitad del mecanismo, y la que se puede borrar sin que se vea
        nada raro: sin esta regla la tabla sigue pulsable y calladamente deja de
        poder copiarse y de explicar sus columnas. `_por_encima_de_la_capa`, que
        es el modelo en Python de este selector, se queda mintiendo si la regla
        no está."""
        m = re.search(r"([^{}]*td > \*[^{}]*)\{([^}]*)\}", self.CSS)
        self.assertIsNotNone(m, "nada sube el contenido de la fila")
        selector, cuerpo = m.group(1), m.group(2)
        self.assertIn(f"#municipios-tabla tbody td > *:not(.{self.clase})", selector)
        self.assertIn(f".{self.clase} > strong", selector)
        self.assertIn("position: relative", cuerpo)
        arriba = re.search(r"z-index:\s*(-?\d+)", cuerpo)
        abajo = re.search(r"z-index:\s*(-?\d+)", self.regla_capa.group(2))
        self.assertIsNotNone(arriba, "el contenido no declara su altura")
        self.assertIsNotNone(abajo, "la capa no declara su altura")
        self.assertGreater(int(arriba.group(1)), int(abajo.group(1)),
                           "el contenido de la fila ya no está por encima de la capa")

    def test_la_fila_es_el_marco_de_la_capa(self):
        """Sin `position: relative` en el `<tr>`, la capa se estira sobre el
        primer antepasado posicionado —la tabla entera, o la ventana— y la
        página queda cubierta por un enlace invisible."""
        m = re.search(r"#municipios-tabla tbody tr\s*\{([^}]*)\}", self.CSS)
        self.assertIsNotNone(m, "la fila de municipios no declara su posición")
        self.assertIn("position: relative", m.group(1))

    def test_cada_fila_tiene_un_solo_enlace_a_la_ficha(self):
        """Estirar el ancla no es multiplicarla: sigue habiendo un href real,
        rastreable y navegable con el tabulador."""
        estirados = [a for tag, a, _ in self.arbol.elementos
                     if tag == "a" and self.clase in (a.get("class") or "").split()]
        self.assertEqual(len(estirados), len(self.ctx["municipios"]))
        for a in estirados:
            self.assertRegex(a.get("href", ""), r"^/municipio/[a-z0-9-]+/$")

    def test_ningun_valor_cuelga_pelado_de_su_celda(self):
        """El guardián de la selección: lo que cuelga directamente del `<td>`
        queda debajo de la capa y deja de poder copiarse. Cae en cuanto una
        cifra pierde su `valor_suelto()`."""
        hundidos = [t for t, camino in self.arbol.textos
                    if not _por_encima_de_la_capa(camino, self.clase)]
        self.assertEqual(hundidos[:5], [],
                         f"{len(hundidos)} textos de la tabla quedan bajo la capa "
                         f"del enlace estirado y no se pueden seleccionar")

    def test_lo_que_se_explica_o_lleva_a_otro_sitio_queda_por_encima(self):
        """Los `title` de la fila no son adorno: dicen que un guion no es un
        cero y que dos satélites no se suman. Y la columna Prensa lleva a otro
        destino. Si la capa los tapa, el lector pierde información, no un clic."""
        tapados, vistos = [], 0
        for tag, attrs, camino in self.arbol.elementos:
            if tag == "td":
                continue          # su `title` lo hereda el valor que lleva dentro
            if self.clase in (attrs.get("class") or "").split():
                continue          # el ancla estirada ES la capa
            if "title" not in attrs and "href" not in attrs:
                continue
            vistos += 1
            if not _por_encima_de_la_capa(camino, self.clase):
                tapados.append((tag, attrs.get("title", attrs.get("href"))[:40]))
        self.assertEqual(tapados[:5], [],
                         f"{len(tapados)} elementos con explicación o destino "
                         f"propio quedan debajo de la capa")
        self.assertGreater(vistos, len(self.ctx["municipios"]),
                           "el test no está mirando los títulos de la tabla")

    def test_cada_celda_con_title_lleva_dentro_algo_que_lo_pueda_ensenar(self):
        """El `title` del `<td>` de población solo se ve si el ratón llega a
        algo que esté por encima de la capa; el navegador lo busca subiendo por
        el árbol. Sin un elemento dentro, el título es letra muerta."""
        vistos = 0
        for tag, attrs, camino in self.arbol.elementos:
            if tag != "td" or "title" not in attrs:
                continue
            vistos += 1
            self.assertTrue(self.arbol.hijos.get(camino[-1][2]),
                            f"un <td title> sin ningún elemento dentro: su "
                            f"explicación no se puede leer ({attrs['title'][:40]})")
        self.assertGreater(vistos, 0, "ninguna celda con título: el test no mira nada")


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
        debe hacer lo mismo o la misma cifra se vería distinta en cada página.

        Aquí solo se fija el comportamiento de la copia en Python; que las dos
        copias digan lo mismo lo comprueba `TestEspejosDeFormatoEjecutados`
        ejecutándolas."""
        self.assertEqual(R.fmt(7.0, 1), "7")
        self.assertEqual(R.fmt(7.5, 1), "7,5")

    def test_pct_nunca_redondea_a_cero_una_proporcion_real(self):
        """Un municipio con damnificados no puede leerse como municipio sin
        damnificados."""
        self.assertEqual(R.pct(0.03), "<0,1 %")
        self.assertEqual(R.pct(None), "—")


class TestEspejosDeFormatoEjecutados(unittest.TestCase):
    """Los cuatro formateadores que viven en los dos lenguajes, comparados
    LLAMÁNDOLOS.

    Estos espejos se vigilaban leyendo el texto de `site/ui.js` con `assertIn`:
    «¿aparece "maximumFractionDigits" en el fichero?», «¿aparece "<0,1 %"?».
    Un `assertIn` sobre el código fuente pasa en verde con la condición
    invertida —la cadena sigue estando ahí— y no mira siquiera si las dos
    funciones devuelven lo mismo. Es el argumento con el que este sprint se
    retiraron otros dos guardianes, así que se aplica también aquí.

    Lo que se compara es la salida, caso por caso, con el `ui.js` real. Y no es
    teórico: al escribirlo apareció El Cerrito, con una tasa de 0,25 %, que la
    tabla estática publicaba como «0,2 %» y el mapa como «0,3 %» — `%f`
    redondea al par y `Intl` se aleja del cero (toda segunda copia
    diverge)."""

    def _comparar(self, expresiones, esperados, que):
        """Una sola llamada a node para todos los casos: arrancarlo por caso
        cuesta más que la comprobación entera."""
        js = correr_ui("[" + ",".join(expresiones) + "]")
        self.assertEqual(len(js), len(esperados))
        for expr, obtenido, esperado in zip(expresiones, js, esperados):
            with self.subTest(caso=expr):
                self.assertEqual(
                    obtenido, esperado,
                    f"{que} ha divergido entre site/ui.js y deploy/render_html.py")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_fmt_es_espejo_ejecutado_de_ui_js(self):
        """Separador de miles, coma decimal y redondeo, que son tres reglas
        distintas y las tres se publican."""
        casos = [(n, d) for n in (None, 0, 1, 7.0, 95, 1000, 26377, 1234567,
                                  0.3, 0.04, 0.05,
                                  # empates: donde `%f` y `Intl` discrepaban
                                  1.5, 0.25, 12.35, 33.75, 199.95,
                                  -1, -3.5, -0.02)
                 for d in (0, 1, 2)]
        self._comparar(
            [f"UI.fmt({json.dumps(n)}, {d})" for n, d in casos],
            [R.fmt(n, d) for n, d in casos], "fmt")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_fmt_prosa_es_espejo_ejecutado_de_ui_js(self):
        """La frontera del Libro de estilo (nueve con letras, 10 en guarismos)
        y la concordancia de género, en las dos superficies.

        Corre prisa porque las dos escriben en la MISMA página: `fmt_prosa`
        redacta el hallazgo del silencio municipal en el build y `UI.fmtProsa`
        sigue vivo dentro de `comparativaFuentes`, que el build ejecuta con node
        y publica ahí al lado."""
        casos = [(n, f) for n in (None, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
                                  95, 1.5, -1)
                 for f in (False, True)]
        self._comparar(
            [f"UI.fmtProsa({json.dumps(n)}, {json.dumps(f)})" for n, f in casos],
            [R.fmt_prosa(n, femenino=f) for n, f in casos], "fmt_prosa")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_pct_es_espejo_ejecutado_de_ui_js(self):
        """El umbral del «<0,1 %», la coma decimal es-CO y el redondeo."""
        casos = (None, 0, 0.03, 0.049, 0.05, 0.1, 0.25, 12.34, 12.35, 33.75,
                 99.95, 100, -0.02)
        self._comparar([f"UI.pct({json.dumps(n)})" for n in casos],
                       [R.pct(n) for n in casos], "pct")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_las_dos_fechas_son_espejo_ejecutado_de_ui_js(self):
        """Los doce meses uno a uno —en español y con la abreviatura de tres
        letras—, el día sin cero a la izquierda y lo que no es una fecha."""
        casos = [f"2026-{m:02d}-0{d}" for m in range(1, 13) for d in (1, 9)]
        casos += ["2026-08-18", "2026-12-31", "", None, "no es una fecha",
                  "2026-08-18T14:30:00Z"]
        self._comparar([f"UI.fechaEs({json.dumps(i)})" for i in casos],
                       [R.fecha_corta(i) for i in casos], "fecha_corta/fechaEs")
        self._comparar([f"UI.fechaLarga({json.dumps(i)})" for i in casos],
                       [R.fecha_larga(i) for i in casos], "fecha_larga/fechaLarga")


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
        """«Los satélites han mirado N municipios; la comunidad ha documentado M»
        la escribe el build desde las mismas filas de la tabla.

        Estuvo a mano en site/index.html y envejeció dos veces: primero al pasar
        el conteo satelital a incluir UNOSAT, después con las corridas diarias,
        que anunciaban 36 municipios ciudadanos con 43 en su propia tabla. Ya no
        se vigila un texto fijo: se vigila que el generador diga lo que dicen los
        datos."""
        # `n_evaluados` cuenta a los TRES satélites. Mientras esto sumó solo dos
        # columnas, el guardián daba por buena la nota que decía «9 municipios»
        # con once en su propia tabla: un guardián mal apuntado no protege nada.
        sat = len([f for f in self.filas if f["n_evaluados"]])
        ciu = len([f for f in self.filas if f["n_ciudadanos"]])
        nota = R.nota_mirada_portada(self.ctx)
        m = re.search(r"satélites han mirado (\S+) municipios; la comunidad "
                      r"ha documentado (\S+)</strong>", nota)
        self.assertIsNotNone(m, "la nota de portada ya no dice cuántos miró cada fuente")
        self.assertEqual((m.group(1), m.group(2)),
                         (R.fmt_prosa(sat), R.fmt_prosa(ciu)),
                         f"la nota de portada dice {m.group(1)}/{m.group(2)} y los "
                         f"datos dicen {sat}/{ciu}")

    def test_la_nota_de_portada_la_escribe_el_build(self):
        """El HTML del repo lleva la marca y ninguna cifra a mano: si alguien la
        vuelve a escribir, envejecerá con la siguiente corrida diaria."""
        html = (Path(__file__).parent.parent / "site/index.html").read_text(
            encoding="utf-8")
        self.assertIn('<span data-gen="mirada-portada"></span>', html)
        self.assertNotIn("han mirado", html)

    def test_sin_la_nota_la_portada_sigue_leyendose(self):
        """La raya va dentro de lo generado: si el build no inyectara, la frase
        quedaría completa y sin cifra, nunca con una raya huérfana."""
        html = (Path(__file__).parent.parent / "site/index.html").read_text(
            encoding="utf-8")
        i = html.index('<span data-gen="mirada-portada"></span>')
        self.assertTrue(html[:i].rstrip().endswith("venga de donde venga"))
        self.assertTrue(html[i:].split("</span>", 1)[1].startswith("."))
        self.assertTrue(R.nota_mirada_portada(self.ctx).startswith(" —"))

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


class TestBandaDeBrechas(unittest.TestCase):
    """La banda amarilla de la portada, escrita en el build y no en el navegador.

    Resume las brechas centrales del monitor —cuánto llevan calladas las
    fuentes oficiales abiertas y a cuántos municipios sacudidos no los ha
    mirado ningún satélite— y es, con diferencia, el texto más citable de la
    portada. Llegaba vacía a quien no ejecuta JavaScript: exactamente la
    regresión que el prerenderizado de las tablas existe para evitar."""

    MONITOR = {
        "generado": "2026-08-22",
        "brechas_oficiales": {
            "ungrd_socrata": {"hasta": "2022-12-31T00:00:00.000"},
            "ungrd_arcgis": {"max_fecha": "2024-02-17"},
            "ungrd_rud": {"municipios": 207, "familias": 100231.0,
                          "viv_destruidas": 6638.0},
        },
        "aois": [
            {"aoi": "Quibdo Centre", "resumen": {"edificios_afectados": 120},
             "cruce": {"n_oficial": None}},
            {"aoi": "Buenaventura", "resumen": {"edificios_afectados": 134},
             "cruce": {}},
            {"aoi": "Cali Center", "resumen": {"edificios_afectados": 90},
             "cruce": {"n_oficial": 42}},
            {"aoi": "Western Colombia", "resumen": {"edificios_afectados": None},
             "cruce": {}},
        ],
        "entregas": [1, 2, 3],
        "citizen": {"chatmap_total": 542},
        # sigue en monitor.json y se sigue archivando: lo que salió de la banda
        # el 25-ago-2026 es el párrafo, no la fuente. Se deja en el fixture a
        # propósito, para que el guardián de abajo compruebe que estando el dato
        # delante la banda no lo publica.
        "exposicion": {"expuesta_mmi6plus": 10487959, "en_aois_copernicus": 1040000.0,
                       "pct_cubierta": 9.9},
    }

    # Un catálogo municipal de laboratorio con las trampas dentro: un municipio
    # mirado por dos servicios (el solape que impide sumar el reparto), otro
    # evaluado con CERO edificios —mirado igual: la pregunta es si alguien miró,
    # no si encontró—, uno sacudido y sin mirar, y dos que no deben contar
    # (sacudida por debajo del umbral y sacudida sin dato).
    MUNICIPIOS = [
        {"municipio": "Ciudad Grande", "poblacion_2026": 900000, "mmi_usgs": 7.0,
         "en_aoi_copernicus": True, "sertit_edificios": 40},
        {"municipio": "Ciudad Media", "poblacion_2026": 500000, "mmi_usgs": 6.4,
         "en_aoi_copernicus": False, "unosat_edificios": 0},
        {"municipio": "Villa Sin Mirada", "poblacion_2026": 300000, "mmi_usgs": 6.0,
         "en_aoi_copernicus": False},
        {"municipio": "Pueblo Chico", "poblacion_2026": 12000, "mmi_usgs": 6.8,
         "en_aoi_copernicus": True},
        {"municipio": "Lejos", "poblacion_2026": 700000, "mmi_usgs": 4.2,
         "en_aoi_copernicus": True, "sertit_edificios": 10},
        {"municipio": "Sin Sacudida", "poblacion_2026": 50000, "mmi_usgs": None,
         "en_aoi_copernicus": False},
    ]

    @classmethod
    def setUpClass(cls):
        cls.html = R.banda_brechas({"monitor": cls.MONITOR,
                                    "municipios": cls.MUNICIPIOS})

    # ------------------------------------------------ el guardián de la regresión
    def test_la_banda_llega_escrita_al_artefacto(self):
        """Si vuelve a llegar vacía, este test cae.

        Se ejecuta el inyector de verdad sobre el index.html del repositorio,
        que es como se construye `dist/`: así también cae si alguien quita la
        marca, cambia la etiqueta del contenedor o desconecta el generador."""
        destino = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, destino, ignore_errors=True)
        shutil.copy(ROOT / "site" / "index.html", destino / "index.html")
        hechas = R.inyectar_prerenderizado(destino, R.contexto())
        self.assertIn("brechas", hechas,
                      "el inyector no reconoció la banda: llegaría vacía al artefacto")
        salida = (destino / "index.html").read_text(encoding="utf-8")
        cuerpo = re.search(r'<section[^>]*\bdata-gen="brechas"[^>]*>(.*?)</section>',
                           salida, re.S)
        self.assertTrue(cuerpo, "la banda ya no está en la portada")
        self.assertTrue(cuerpo.group(1).strip(), "la banda quedó vacía en el artefacto")
        self.assertIn("Brecha de reporte oficial", cuerpo.group(1))
        self.assertGreater(len(re.sub(r"<[^>]+>", " ", cuerpo.group(1)).split()), 80,
                           "la banda llegó recortada: ya no dice lo que se cita de ella")

    def test_el_marcador_existe_en_la_portada(self):
        """Si alguien quita la marca, el build dejaría la banda vacía en silencio."""
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-gen="brechas"', html)
        self.assertIn('id="banner-brechas"', html)

    def test_seo_check_caza_la_banda_vacia(self):
        """El verificador del artefacto vigila también las secciones de prosa.

        Antes su expresión solo miraba <tbody> y <ul>: una banda vacía habría
        pasado el control sin una línea de aviso."""
        sys.path.insert(0, str(ROOT / "ingest"))
        import seo_check
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "index.html").write_text(
            '<link rel="canonical" href="/"><section id="banner-brechas" '
            'data-gen="brechas"></section>' + "palabra " * 900, encoding="utf-8")
        res = seo_check.revisar(tmp)
        self.assertTrue(any("«brechas» quedó vacío" in f for f in res["fallos"]),
                        f"seo_check no vio la banda vacía: {res['fallos']}")

    # ---------------------------------------------- una sola fuente de redacción
    def test_el_javascript_ya_no_redacta_la_banda(self):
        """La redacción vive en Python. Dos versiones del mismo párrafo en dos
        lenguajes divergen: es la lección de los topónimos y del liveblog."""
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        for frase in ("Brecha de reporte oficial", "Exposición sin mapeo",
                      "Municipios que nadie ha mirado",
                      "La brecha empezó a cerrarse", "brechaMunicipal"):
            self.assertNotIn(frase, js, f"«{frase}» sigue escrito en app.js")
        self.assertIn("banner-brechas", js, "el JS ya no refresca los días")

    def test_el_javascript_solo_refresca_los_contadores_de_dias(self):
        """Lo único que no puede fijar el build: cuántos días lleva callada una
        fuente depende del reloj de quien lee, no de la fecha de construcción."""
        self.assertIn('data-dias-desde="2022-12-31"', self.html)
        self.assertIn('data-dias-desde="2024-02-17"', self.html)
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-dias-desde", js)

    # ------------------------------------------------------- lo que la banda dice
    def test_dice_las_brechas_centrales(self):
        self.assertIn("Brecha de reporte oficial", self.html)
        self.assertIn("Municipios que nadie ha mirado desde el aire", self.html)
        self.assertIn("31 de diciembre de 2022", self.html)      # fecha en prosa, sin abreviar
        self.assertIn(">1.330<", self.html)                      # días de silencio, locale es-CO

    def test_la_banda_no_publica_ningun_porcentaje_de_poblacion(self):
        """La decisión del 25-ago-2026, con su guardián.

        La banda publicaba «las zonas mapeadas por Copernicus cubren al 9,9 %»
        de la población expuesta que estima PAGER. Dos cifras que no se cuentan
        igual en la misma frase, y medidas con uno solo de los tres servicios.
        Su sustituto tampoco lleva porcentaje: los once municipios mirados
        reunían el 55,5 % de la población sacudida, pero Cali sola era el 58 %
        de ese «cubierto» — un porcentaje que consuela describiendo que los
        satélites miraron las ciudades. Aquí se cuentan municipios."""
        self.assertNotIn("%", self.html)
        self.assertNotIn(R.fmt(10487959), self.html)     # la exposición de PAGER
        self.assertNotIn("PAGER", self.html)

    def test_las_zonas_sin_registro_no_se_escriben_a_mano(self):
        """R11: el día que una zona entre al registro, la frase deja de
        nombrarla sola — y que se rompa la afirmación es una buena noticia."""
        self.assertIn("p. ej. Quibdó Centro y Buenaventura", self.html)
        sin_pendientes = {**self.MONITOR,
                          "aois": [{"aoi": "Cali Center",
                                    "resumen": {"edificios_afectados": 90},
                                    "cruce": {"n_oficial": 42}}]}
        otra = R.banda_brechas({"monitor": sin_pendientes})
        self.assertIn("Ya no queda ninguna zona con daño satelital sin registro", otra)
        self.assertNotIn("p. ej.", otra)

    def test_sin_datos_no_inventa_ceros(self):
        """R3: sin dato no hay cero, hay ausencia — y aquí el cero acusaría.

        La primera versión de la banda publicaba «Copernicus entregó cero
        productos» cuando faltaba la clave `entregas`: no un dato que falta, sino
        una acusación falsa a la fuente. Este test se escribió sin mirar esa
        frase y la dejó pasar; ahora comprueba la banda entera."""
        vacia = R.banda_brechas({"monitor": {}})
        self.assertNotIn("hace", vacia)
        self.assertNotIn("data-dias-desde", vacia)
        self.assertNotIn("La brecha empezó a cerrarse", vacia)
        self.assertNotIn("cero", vacia)
        self.assertNotIn("Copernicus entregó", vacia)
        self.assertNotIn("la comunidad aportó", vacia)

    def test_un_cero_medido_de_verdad_si_se_publica(self):
        """La regla es no inventar el cero, no ocultarlo: una lista vacía de
        entregas significa que Copernicus no entregó nada, y eso se cuenta."""
        banda = R.banda_brechas({"monitor": {"entregas": [], "citizen": {}}})
        self.assertIn("Copernicus entregó cero productos", banda)
        self.assertNotIn("la comunidad aportó", banda)   # chatmap_total ausente

    def test_los_dos_contadores_de_dias_cuentan_igual(self):
        """El build y el navegador daban 1.330 y 1.331 del mismo silencio.

        `Math.round` sobre una fecha ISO —medianoche UTC— sumaba un día a media
        mañana en Colombia, y la cifra cambiaba sola durante el día. Días
        completos transcurridos, en los dos lados."""
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Math.floor((Date.now() - desde) / 864e5)", js)
        self.assertNotIn("Math.round((Date.now() - desde)", js)
    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_el_navegador_y_el_build_dan_el_mismo_numero_de_dias(self):
        """Espejo ejecutado: la misma cuenta en los dos lenguajes, para el día
        de los datos. Es la comprobación que habría cazado el desfase."""
        import subprocess
        for desde in ("2022-12-31", "2024-02-17"):
            script = ("const desde = new Date(%r);"
                      "const hoy = new Date('2026-08-22T18:00:00Z');"
                      "console.log(Math.floor((hoy - desde) / 864e5));" % desde)
            salida = subprocess.run([NODE, "-"], input=script, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(int(salida.stdout), R._dias_entre(desde, "2026-08-22"),
                             f"el navegador y el build no cuentan igual desde {desde}")

    # --------------------------------------------------- espejos con el navegador
    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_los_nombres_de_zona_son_espejo_de_ui_js(self):
        self.assertEqual(correr_ui("UI.AOI_ES"), R.AOI_ES,
                         "AOI_ES ha divergido entre ui.js y render_html.py")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_las_zonas_sin_registro_son_espejo_de_ui_js(self):
        """La misma pregunta la hacen la banda (Python) y la nota del cruce
        (JavaScript): si respondieran distinto, la portada se contradiría."""
        for datos in (self.MONITOR, R._leer("monitor.json")):
            self.assertEqual(correr_ui("UI.zonasSinRegistro(mon)", datos),
                             R.zonas_sin_registro(datos))
            self.assertEqual(correr_ui("UI.ejemplosSinRegistro(mon)", datos),
                             R.ejemplos_sin_registro(datos))



class TestCoberturaSatelitalDeLosSacudidos(unittest.TestCase):
    """El párrafo que sustituyó a la exposición de PAGER (25-ago-2026).

    Publicaba «10.487.959 personas viven donde el sismo alcanzó intensidad 6 o
    más (PAGER); las zonas mapeadas por Copernicus cubren a unas 1.040.000
    (9,9 %)». Dos fallos: comparaba dos poblaciones que no se cuentan igual —la
    rejilla del USGS contra los polígonos de Copernicus— y medía la cobertura
    con uno solo de los tres servicios satelitales.

    Lo que vigila esta clase es COMPORTAMIENTO, no vocabulario: que la cifra
    publicada sea la que sale de contar el catálogo —el guardián que habría
    cazado los «36 municipios» de la portada contra los 43 de su propia tabla—,
    que mover el dato mueva la frase, y que un servicio sin municipios no se
    publique como cero (R3): acusar a un satélite de no haber mirado es tan
    falso como acusar a Copernicus de entregar «cero productos»."""

    # el mismo catálogo de laboratorio que usa la banda, con sus trampas
    MUNICIPIOS = TestBandaDeBrechas.MUNICIPIOS

    def _parrafo(self, municipios) -> str:
        """La banda entera, recortada al párrafo de la cobertura satelital."""
        html = R.banda_brechas({"monitor": {}, "municipios": municipios})
        marca = "Municipios que nadie ha mirado desde el aire:"
        return html.split(marca)[1] if marca in html else ""

    # ------------------------------------------- la cuenta es la del catálogo
    @staticmethod
    def _recuento_a_mano() -> dict:
        """Contar el catálogo publicado SIN pasar por `render_html`.

        Dos implementaciones de la misma cuenta que tienen que coincidir: si el
        generador deja de contar lo que hay —o cuenta otra cosa—, aquí se ve."""
        items = json.loads(
            (ROOT / "data/public/municipios.json").read_text("utf-8"))["items"]
        sacudidos = [m for m in items if (m.get("mmi_usgs") or 0) >= 6]

        def miro(m):
            return (bool(m.get("en_aoi_copernicus"))
                    or m.get("unosat_edificios") is not None
                    or m.get("sertit_edificios") is not None)

        sin = [m for m in sacudidos if not miro(m)]
        return {"sacudidos": len(sacudidos), "sin_mirar": len(sin),
                "mirados": len(sacudidos) - len(sin),
                "poblacion_sin_mirar": sum(m["poblacion_2026"] for m in sin)}

    def test_lo_publicado_coincide_con_contar_el_catalogo(self):
        """El guardián de «36 contra 43», sobre el catálogo real del día."""
        ctx = R.contexto()
        medido = R.cobertura_satelital_sacudidos(ctx)
        a_mano = self._recuento_a_mano()
        for clave, valor in a_mano.items():
            self.assertEqual(medido[clave], valor,
                             f"«{clave}»: el generador cuenta {medido[clave]} y el "
                             f"catálogo tiene {valor}")
        parrafo = self._parrafo(ctx["municipios"])
        self.assertTrue(parrafo, "el párrafo no llegó a publicarse")
        for clave, valor in a_mano.items():
            self.assertIn(f"<strong>{R.fmt(valor)}</strong>", parrafo,
                          f"«{clave}» ({valor}) se calcula pero no se publica")

    def test_mover_una_mirada_mueve_la_frase(self):
        """Si el párrafo se congelara en una cifra escrita a mano, esto lo caza:
        se le quita la mirada al municipio mirado más poblado y las cuentas
        tienen que moverse solas, en el dato y en el texto."""
        ctx = R.contexto()
        antes = R.cobertura_satelital_sacudidos(ctx)
        victima = max((m for m in ctx["municipios"]
                       if (m.get("mmi_usgs") or 0) >= 6 and R._mirado_por_satelite(m)),
                      key=lambda m: m["poblacion_2026"])
        ciegos = [{**m, "en_aoi_copernicus": False, "unosat_edificios": None,
                   "sertit_edificios": None} if m is victima else m
                  for m in ctx["municipios"]]
        despues = R.cobertura_satelital_sacudidos({"municipios": ciegos})
        self.assertEqual(despues["sacudidos"], antes["sacudidos"])
        self.assertEqual(despues["mirados"], antes["mirados"] - 1)
        self.assertEqual(despues["sin_mirar"], antes["sin_mirar"] + 1)
        self.assertEqual(despues["poblacion_sin_mirar"],
                         antes["poblacion_sin_mirar"] + victima["poblacion_2026"])
        parrafo = self._parrafo(ciegos)
        self.assertIn(f"<strong>{R.fmt(despues['sin_mirar'])}</strong>", parrafo)
        self.assertNotIn(f"<strong>{R.fmt(antes['sin_mirar'])}</strong>", parrafo)

    def test_las_cifras_del_catalogo_de_laboratorio_son_exactas(self):
        """Con un catálogo cuyo resultado se conoce de memoria: cuatro
        municipios sacudidos, tres mirados —uno de ellos con cero edificios
        evaluados, que está mirado igual—, uno sin mirar, y los dos de fuera
        (sacudida baja y sacudida sin dato) que no entran en ninguna cuenta."""
        d = R.cobertura_satelital_sacudidos({"municipios": self.MUNICIPIOS})
        self.assertEqual(d["sacudidos"], 4)
        self.assertEqual(d["mirados"], 3)
        self.assertEqual(d["sin_mirar"], 1)
        self.assertEqual(d["poblacion_sin_mirar"], 300000)
        self.assertEqual(d["reparto"], [("Copernicus EMS", 2), ("UNITAR-UNOSAT", 1),
                                        ("ICube-SERTIT", 1)])
        self.assertEqual(d["con_varias_miradas"], 1)
        self.assertEqual(d["cabeza_mirada"], 2)
        self.assertEqual(d["mayor_sin_mirar"]["municipio"], "Villa Sin Mirada")

    def test_el_municipio_sacudido_por_debajo_del_umbral_no_cuenta(self):
        """«Lejos» está mirado por dos servicios y tiene 700.000 habitantes: si
        el umbral de sacudida se cayera, entraría a maquillar la cobertura."""
        d = R.cobertura_satelital_sacudidos({"municipios": self.MUNICIPIOS})
        self.assertEqual(d["sacudidos"], 4)
        self.assertNotIn("Lejos", self._parrafo(self.MUNICIPIOS))

    # ------------------------------------------------------- R3: el cero
    def test_un_servicio_sin_municipios_no_se_publica_como_cero(self):
        """Que UNOSAT no tenga ningún municipio aquí no es «UNOSAT miró cero»:
        es que no le toca aparecer. El cero acusaría de una omisión inventada,
        igual que «Copernicus entregó cero productos» cuando faltaba la clave."""
        sin_unosat = [{**m, "unosat_edificios": None} for m in self.MUNICIPIOS]
        d = R.cobertura_satelital_sacudidos({"municipios": sin_unosat})
        self.assertEqual([r[0] for r in d["reparto"]],
                         ["Copernicus EMS", "ICube-SERTIT"])
        parrafo = self._parrafo(sin_unosat)
        self.assertNotIn("UNOSAT", parrafo)
        self.assertNotIn("cero", parrafo)
        self.assertNotIn(", 0", parrafo)

    def test_sin_municipios_sacudidos_no_hay_parrafo(self):
        """Donde falta el dato se calla el párrafo entero. Publicar «0
        municipios sin mirar» sin haber medido ninguno sería la buena noticia
        que nadie ha comprobado."""
        for catalogo in ([], [{"municipio": "X", "mmi_usgs": None}],
                         [{"municipio": "X", "mmi_usgs": 4.0}]):
            self.assertEqual(R.cobertura_satelital_sacudidos({"municipios": catalogo}), {})
            self.assertEqual(self._parrafo(catalogo), "")
        self.assertEqual(R.cobertura_satelital_sacudidos({}), {})

    def test_la_poblacion_solo_se_publica_si_la_tienen_todos(self):
        """Una suma a la que le faltan miembros no es la población del grupo:
        se calla la cifra, no se publica la suma coja."""
        cojo = [{**m, "poblacion_2026": None} if m["municipio"] == "Villa Sin Mirada"
                else m for m in self.MUNICIPIOS]
        d = R.cobertura_satelital_sacudidos({"municipios": cojo})
        self.assertNotIn("poblacion_sin_mirar", d)
        self.assertNotIn("personas", self._parrafo(cojo))

    def test_el_dia_que_no_quede_ninguno_la_frase_cambia_de_forma(self):
        """R11: los supuestos rotos avisan, y romperse puede ser buena noticia.
        Con todos los sacudidos mirados, «A 0 de ellos no los ha mirado ningún
        servicio» sería una cifra correcta y una frase absurda."""
        todos = [{**m, "en_aoi_copernicus": True} for m in self.MUNICIPIOS]
        d = R.cobertura_satelital_sacudidos({"municipios": todos})
        self.assertEqual(d["sin_mirar"], 0)
        self.assertNotIn("mayor_sin_mirar", d)
        parrafo = self._parrafo(todos)
        self.assertIn("A todos los ha mirado algún servicio satelital", parrafo)
        self.assertNotIn("<strong>0</strong>", parrafo)

    # ------------------------------------- el reparto no es una suma
    def test_el_reparto_avisa_de_que_no_se_suma(self):
        """5 + 5 + 4 no son 14 municipios: son 11, porque a tres los miró más de
        un servicio. Publicar el desglose sin la advertencia invita a sumarlo."""
        for catalogo in (self.MUNICIPIOS, R.contexto()["municipios"]):
            d = R.cobertura_satelital_sacudidos({"municipios": catalogo})
            suma = sum(n for _, n in d["reparto"])
            self.assertGreater(suma, d["mirados"],
                               "sin solape este test no comprueba nada")
            parrafo = self._parrafo(catalogo)
            self.assertIn("No se suman", parrafo)

    def test_un_reparto_sin_solape_no_advierte_de_nada(self):
        """La advertencia también es condicional: el día que cada municipio lo
        mire un solo servicio, el desglose SÍ se puede sumar y la frase sobra."""
        limpio = [{**m, "sertit_edificios": None} if m["municipio"] == "Ciudad Grande"
                  else m for m in self.MUNICIPIOS]
        d = R.cobertura_satelital_sacudidos({"municipios": limpio})
        self.assertEqual(d["con_varias_miradas"], 0)
        self.assertEqual(sum(n for _, n in d["reparto"]), d["mirados"])
        self.assertNotIn("No se suman", self._parrafo(limpio))

    # ------------------------------------- qué clase de municipios son los once
    def test_la_cabeza_del_ranking_sale_del_dato_y_no_de_la_mano(self):
        """«Son sobre todo los grandes» no se afirma: se deriva. Cuántos de los
        más poblados están mirados de corrido, y cuál es el primero que se
        salta la lista. Si el mayor de todos deja de estar mirado, la frase
        cambia de forma sola en vez de mentir."""
        d = R.cobertura_satelital_sacudidos({"municipios": self.MUNICIPIOS})
        parrafo = self._parrafo(self.MUNICIPIOS)
        self.assertIn("los dos municipios más poblados están entre ellos", parrafo)
        self.assertIn("Villa Sin Mirada", parrafo)
        self.assertIn("300.000 habitantes", parrafo)
        ciego = [{**m, "en_aoi_copernicus": False, "sertit_edificios": None}
                 if m["municipio"] == "Ciudad Grande" else m for m in self.MUNICIPIOS]
        otro = self._parrafo(ciego)
        self.assertIn("Ni siquiera el municipio más poblado", otro)
        self.assertNotIn("son sobre todo los grandes", otro)
        self.assertEqual(d["cabeza_mirada"], 2)

class TestSelloDeFecha(unittest.TestCase):
    """La fecha del build no es la fecha del dato.

    `rud.json` se genera el 22 con una serie que termina el 21, y el encabezado
    anunciaba «Actualizado el 22 de agosto de 2026» sobre cifras del 21 — la
    confusión escrita en HTML indexable y con permanencia de archivo. El sello
    dice las dos, cada una desde el dato (R4).

    Y lo escribe el build. Las cuatro páginas lo resolvían con
    `getElementById("generado").textContent`, **sin guarda ninguna**: quien no
    ejecuta JavaScript leía una raya, y una `TypeError` sobre `null` dentro de
    un IIFE `async` rechaza la promesa en silencio y se lleva por delante el
    resto del guion de la página."""

    PAGINAS = {"index.html": "portada-sello", "municipios.html": "municipios-sello",
               "rud.html": "rud-sello", "balances.html": "balances-sello"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        for pagina in cls.PAGINAS:
            shutil.copy(ROOT / "site" / pagina, cls.tmp / pagina)
        cls.hechas = R.inyectar_prerenderizado(cls.tmp, R.contexto())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sello_servido(self, pagina: str, clave: str) -> str:
        html = (self.tmp / pagina).read_text(encoding="utf-8")
        cuerpo = re.search(
            rf'<span id="generado"[^>]*\bdata-gen="{clave}"[^>]*>(.*?)</span>',
            html, re.S)
        self.assertTrue(cuerpo, f"{pagina}: el sello ya no está en el encabezado")
        return cuerpo.group(1)

    # ---------------------------------------------------------- el componente
    def test_dice_las_dos_fechas_con_su_rotulo_y_legibles_por_maquina(self):
        sello = R.sello_fechas("2026-08-21", "2026-08-22", "del RUD")
        self.assertIn('<time datetime="2026-08-21">21 de agosto de 2026</time>', sello)
        self.assertIn("hasta el", sello)
        self.assertIn("corrida del", sello)
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-21", "2026-08-22"])

    def test_el_sello_del_rud_no_confunde_la_corrida_con_el_ultimo_dato(self):
        """El bug que motivó el componente: las dos fechas salían del mismo
        campo. Aquí la serie termina el 20 y la corrida es del 22."""
        sello = R.sello_rud({"rud": {"generado": "2026-08-22",
                                     "serie": [{"fecha": "2026-08-19"},
                                               {"fecha": "2026-08-20"}]}})
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-20", "2026-08-22"])

    def test_el_sello_de_balances_fecha_la_ultima_busqueda_no_la_primera(self):
        """`oficiales.json` fecha cada nota con la búsqueda que la encontró; el
        rastreo llega hasta la última, y el orden del fichero no lo garantiza."""
        sello = R.sello_balances({"oficiales": {
            "generated_at": "2026-08-22T04:02:41.917Z",
            "items": [{"search_date": "2026-08-21"}, {"search_date": "2026-08-14"},
                      {"titulo": "sin fecha de búsqueda"}]}})
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-21", "2026-08-22"])
        self.assertNotIn("04:02", sello, "la marca de tiempo se cuela en la prosa")

    def test_la_corrida_se_abrevia_solo_dentro_del_mismo_mes(self):
        """«hasta el 21 de agosto de 2026 · corrida del 22» se lee; repetir mes
        y año no añade nada. En cuanto cambian, «corrida del 1» es un acertijo."""
        self.assertIn('corrida del <time datetime="2026-08-22">22</time>',
                      R.sello_fechas("2026-08-21", "2026-08-22", "del RUD"))
        self.assertIn('corrida del <time datetime="2026-09-01">1 de septiembre'
                      ' de 2026</time>',
                      R.sello_fechas("2026-08-31", "2026-09-01", "del RUD"))

    # ------------------------------------- lo que falta se calla, no se inventa
    def test_sin_fecha_del_dato_no_se_inventa_una(self):
        """La portada y los municipios están en este caso: `monitor.json` y
        `municipios.json` no publican hasta dónde llega su serie."""
        sello = R.sello_fechas(None, "2026-08-22", "del monitor")
        self.assertNotIn("hasta", sello)
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-22"])

    def test_sin_corrida_tampoco_se_inventa(self):
        sello = R.sello_fechas("2026-08-21", None, "del RUD")
        self.assertNotIn("corrida", sello)
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-21"])

    def test_sin_ninguna_fecha_lo_dice_y_jamas_devuelve_vacio(self):
        """Una cadena vacía dejaría el contenedor `data-gen` vacío, y eso
        rompe el build por `seo_check`: el silencio hay que decirlo."""
        for hasta, corrida in ((None, None), ("", ""), ("mañana", None)):
            with self.subTest(hasta=hasta, corrida=corrida):
                sello = R.sello_fechas(hasta, corrida, "del RUD")
                self.assertTrue(sello.strip(), "el sello salió vacío")
                self.assertIn("Sin ninguna captura del RUD", sello)

    # ------------------------------------------ el guardián de la regresión
    def test_los_cuatro_sellos_llegan_escritos_al_artefacto(self):
        """Se ejecuta el inyector de verdad sobre los HTML del repositorio, que
        es como se construye `dist/`: así cae también si alguien quita la marca,
        cambia la etiqueta del contenedor o desconecta el generador."""
        for pagina, clave in self.PAGINAS.items():
            with self.subTest(pagina=pagina):
                self.assertIn(clave, self.hechas,
                              f"{pagina}: el inyector no reconoció el sello")
                cuerpo = self.sello_servido(pagina, clave)
                self.assertTrue(cuerpo.strip(), f"{pagina}: el sello quedó vacío")
                self.assertIn("<time datetime=", cuerpo,
                              f"{pagina}: la fecha no es legible por máquina")

    def test_el_rud_y_los_balances_fechan_tambien_el_dato(self):
        """Las dos páginas cuyas fuentes sí saben hasta dónde llegan."""
        for pagina, clave in (("rud.html", "rud-sello"),
                              ("balances.html", "balances-sello")):
            with self.subTest(pagina=pagina):
                cuerpo = self.sello_servido(pagina, clave)
                self.assertEqual(len(re.findall(r'<time ', cuerpo)), 2,
                                 f"{pagina}: el sello dejó de decir las dos fechas")
                self.assertIn("corrida del", cuerpo)

    def test_la_portada_y_los_municipios_no_inventan_la_fecha_del_dato(self):
        """Sus fuentes no la publican, así que ese trozo se calla."""
        for pagina, clave in (("index.html", "portada-sello"),
                              ("municipios.html", "municipios-sello")):
            with self.subTest(pagina=pagina):
                cuerpo = self.sello_servido(pagina, clave)
                self.assertEqual(len(re.findall(r'<time ', cuerpo)), 1)
                self.assertNotIn("hasta el", cuerpo)


class TestElSelloYaNoLoEscribeElNavegador(unittest.TestCase):
    """Lo que se comprueba sobre las fuentes, no sobre el artefacto.

    Va en su propia clase a propósito: si el marcador de una página se rompe, el
    inyector revienta y se llevaría por delante el `setUpClass` de la otra, y
    entonces estos dos guardianes nunca llegarían a decir lo suyo."""

    PAGINAS = TestSelloDeFecha.PAGINAS

    def test_el_marcador_va_vacio_y_con_la_apertura_pegada_al_cierre(self):
        """Un salto de línea entre la apertura y el cierre y la marca no casa."""
        for pagina, clave in self.PAGINAS.items():
            with self.subTest(pagina=pagina):
                html = (ROOT / "site" / pagina).read_text(encoding="utf-8")
                self.assertIn(f'<span id="generado" data-gen="{clave}"></span>', html)

    def test_ningun_javascript_vuelve_a_escribir_el_sello(self):
        """No se le pone un `if` a la llamada sin guarda: se le quita el motivo.
        Y la redacción vive en un solo sitio, que ahora es Python."""
        for js in ("app.js", "municipios.js", "rud.js", "balances.js",
                   "common.js", "ui.js"):
            with self.subTest(js=js):
                texto = (ROOT / "site" / js).read_text(encoding="utf-8")
                # `assertFalse` y no `assertNotIn`: el fallo importa, el volcado
                # del fichero entero en el informe no
                self.assertFalse('getElementById("generado")' in texto,
                                 f"{js} vuelve a escribir el sello desde el navegador")
                self.assertFalse('"Actualizado el "' in texto,
                                 f"{js} conserva la redacción vieja del sello")

    def test_el_contador_de_capturas_no_vuelve_a_fechar_el_dato(self):
        """El sello arreglaba la confusión en el encabezado de balances y la
        misma página la repetía tres centímetros más abajo: `#balance-resumen`
        escribía «30 de 30 capturas · actualizado el 22 de agosto de 2026» con
        `generated_at`, que es la corrida y no el corte del rastreo. Dos frases
        sobre la misma fecha diciendo cosas distintas. La fecha vive en el
        sello y solo ahí; el contador cuenta capturas."""
        js = (ROOT / "site" / "balances.js").read_text(encoding="utf-8")
        cuerpo = re.search(r'resumen\.textContent\s*=(.*?);', js, re.S)
        self.assertTrue(cuerpo, "el contador de capturas cambió de forma")
        self.assertNotIn("fechaLarga", cuerpo.group(1),
                         "el contador vuelve a fechar el dato por su cuenta")
        self.assertNotIn("generated_at", cuerpo.group(1))
        self.assertIn("capturas", cuerpo.group(1))


class TestElInyectorNoSeCalla(unittest.TestCase):
    """Un contenedor `data-gen` declarado que no casa rompe el build.

    Basta un salto de línea entre la apertura y el cierre para que la expresión
    no case. Antes eso era un `continue`: una línea de menos en el informe del
    build, la página publicada con el hueco y el aviso mucho después, desde
    `seo_check`, en otro proceso y con otro nombre. Es un error de programación,
    no una fuente que falla (R13)."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def rud_con(self, destino: Path, marcador: str) -> None:
        html = (ROOT / "site" / "rud.html").read_text(encoding="utf-8")
        viejo = '<tbody data-gen="rud"></tbody>'
        assert viejo in html, "cambió el marcador de la tabla del RUD"
        (destino / "rud.html").write_text(html.replace(viejo, marcador),
                                          encoding="utf-8")

    def test_un_marcador_partido_por_un_salto_de_linea_revienta_nombrandolo(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            self.rud_con(destino, '<tbody data-gen="rud">\n</tbody>')
            with self.assertRaises(LookupError) as roto:
                R.inyectar_prerenderizado(destino, self.ctx)
        aviso = str(roto.exception)
        self.assertIn("«rud»", aviso, "el aviso no dice qué contenedor falló")
        self.assertIn("marcador", aviso)
        self.assertIn("site/rud.html", aviso, "manda a mirar el sitio equivocado")
        self.assertNotIn("ya estaba escrito", aviso,
                         "confunde el marcador partido con el marcador gastado: "
                         "el contenedor está en los dos casos, y lo que los "
                         "separa es si dentro hay algo escrito")

    def test_el_marcador_borrado_manda_a_mirar_site_y_no_el_artefacto(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            self.rud_con(destino, "<tbody></tbody>")
            with self.assertRaises(LookupError) as roto:
                R.inyectar_prerenderizado(destino, self.ctx)
        aviso = str(roto.exception)
        self.assertIn("site/rud.html", aviso)
        self.assertNotIn("ya estaba escrito", aviso)

    def test_repetir_el_paso_dice_que_ya_estaba_escrito_y_no_culpa_al_marcador(self):
        """Mismo criterio que `escribir_piezas_compartidas`: dos averías con el
        mismo síntoma, y decir la que no es manda a depurar el sitio
        equivocado. Quien refresca el artefacto a mano es quien se lo encuentra."""
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            self.rud_con(destino, '<tbody data-gen="rud"></tbody>')
            self.assertEqual(sorted(R.inyectar_prerenderizado(destino, self.ctx)),
                             ["rud", "rud-chips", "rud-dataset", "rud-grafico",
                              "rud-nota", "rud-resumen", "rud-sello"],
                             "la primera pasada ya falló")
            with self.assertRaises(LookupError) as repetida:
                R.inyectar_prerenderizado(destino, self.ctx)
        aviso = str(repetida.exception)
        self.assertIn("ya estaba escrito", aviso)
        self.assertNotIn("marcador", aviso, "sigue mandando a mirar site/*.html")
        self.assertIn("build_dist.sh", aviso, "no dice cómo salir del atolladero")

    def test_una_pagina_que_no_esta_se_sigue_saltando(self):
        """Lo que rompe es el contenedor que falta en una página que SÍ está.
        Un `dist/` parcial —el que arma `TestBandaDeBrechas`— no es una avería:
        si lo fuera, este cambio se habría llevado por delante aquel test.

        Lo que se espera no es una lista escrita a mano —envejecía con cada
        contenedor nuevo de la portada, y la fase 6 le añadió quince— sino los
        `data-gen` que la propia `site/index.html` declara. Así el guardián
        también caza la avería contraria, que hoy nadie vigila: un contenedor
        marcado en el HTML **sin generador registrado** se rellenaría solo en
        la imaginación del que lo escribió, porque el inyector recorre los
        generadores y no los marcadores."""
        declarados = sorted(set(re.findall(
            r'data-gen="([^"]+)"',
            (ROOT / "site" / "index.html").read_text(encoding="utf-8"))))
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            shutil.copy(ROOT / "site" / "index.html", destino / "index.html")
            hechas = R.inyectar_prerenderizado(destino, self.ctx)
        self.assertEqual(sorted(hechas), declarados)


class TestCifrasEnAtributos(unittest.TestCase):
    """La og:description es la superficie que se ve al compartir el enlace, y
    ahí no cabe un <span data-gen>: la cifra va marcada con {{clave}}."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.index = (Path(__file__).parent.parent / "site/index.html").read_text(
            encoding="utf-8")

    def test_la_og_description_no_lleva_la_cifra_escrita_a_mano(self):
        """Decía «430+ reportes ciudadanos» con 542 archivados, y nadie lo veía
        porque un meta no se lee en pantalla."""
        og = re.search(r'<meta property="og:description" content="([^"]*)"', self.index)
        self.assertIsNotNone(og, "la portada perdió su og:description")
        self.assertIn("{{reportes_ciudadanos}}", og.group(1))
        self.assertNotRegex(og.group(1), r"\d[\d.]* reportes",
                            "la cifra vuelve a estar escrita a mano")

    def test_el_build_escribe_la_cifra_del_dia(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            (destino / "index.html").write_text(
                '<meta content="{{reportes_ciudadanos}} reportes">', encoding="utf-8")
            hechas = R.sustituir_cifras(destino, self.ctx)
            servido = (destino / "index.html").read_text(encoding="utf-8")
        self.assertEqual(hechas, {"index.html": ["reportes_ciudadanos"]})
        self.assertIn(f'{R.fmt(len(self.ctx["chatmap"]))} reportes', servido)
        self.assertNotIn("{{", servido)

    def test_un_marcador_sin_valor_rompe_el_build_en_vez_de_publicarse(self):
        """Publicar «{{lo_que_sea}}» en la etiqueta que se comparte es peor que
        no publicar: aquí romper es la degradación elegante."""
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            (destino / "index.html").write_text("<p>{{invento}}</p>", encoding="utf-8")
            with self.assertRaises(KeyError) as caso:
                R.sustituir_cifras(destino, self.ctx)
        self.assertIn("invento", str(caso.exception))

    def test_tambien_alcanza_las_fichas_municipales(self):
        """Un marcador colado en una plantilla de ficha vive dos niveles por
        debajo de la raíz: el barrido no puede quedarse en dist/*.html."""
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            ficha = destino / "municipio" / "cali"
            ficha.mkdir(parents=True)
            (ficha / "index.html").write_text("{{reportes_ciudadanos}}", encoding="utf-8")
            hechas = R.sustituir_cifras(destino, self.ctx)
        self.assertIn("municipio/cali/index.html", hechas)


_MARCA_CIFRA = re.compile(
    r'<(b|span|strong)\b[^>]*\bdata-cifra="([^"]+)"[^>]*>(.*?)</\1>', re.S)


def cifras_declaradas(html_texto: str) -> dict:
    """{concepto: {texto publicado, …}} leído del artefacto, no del código.

    Solo mira lo que la página DECLARA con `data-cifra`. Una cifra sin marcar
    no se vigila: la marca es la promesa de que ese número es de ese concepto,
    y sin promesa no hay nada que contrastar. Un concepto marcado cuyo
    contenido no se deja leer entra con el conjunto vacío, para que el guardián
    caiga en vez de darlo por bueno."""
    fuera = {c: set() for c in re.findall(r'data-cifra="([^"]+)"', html_texto)}
    for m in _MARCA_CIFRA.finditer(html_texto):
        fuera.setdefault(m.group(2), set()).add(
            re.sub(r"<[^>]+>", "", m.group(3)).strip())
    return fuera


class TestCifrasDeclaradas(unittest.TestCase):
    """Una página no publica dos totales distintos del mismo concepto.

    El fallo que da origen a este guardián no fue una cifra mal calculada: la
    portada decía «348 municipios» en la prosa y «347» en su propia tabla
    porque cada superficie leía una fuente distinta —el acumulado histórico del
    archivo contra el último corte capturado del registro— y **nada comprobaba
    que dijeran lo mismo**. La cifra concreta se arregla en un commit; lo que
    faltaba era que volver a abrirla costara un test en rojo.

    Por eso aquí no se comprueba ningún número: se comparan **entre sí** los
    que la página publica. El día que el registro crezca, este test seguirá
    diciendo lo mismo, que es la única forma de que no caduque.
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.destino = Path(tempfile.mkdtemp())
        for pagina in sorted((ROOT / "site").glob("*.html")):
            shutil.copy(pagina, cls.destino / pagina.name)
        R.inyectar_prerenderizado(cls.destino, cls.ctx)
        cls.paginas = {f.name: f.read_text(encoding="utf-8")
                       for f in sorted(cls.destino.glob("*.html"))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.destino, ignore_errors=True)

    # -------------------------------------------------------- el guardián
    def test_ninguna_pagina_publica_dos_valores_del_mismo_concepto(self):
        for nombre, html_texto in self.paginas.items():
            for concepto, valores in cifras_declaradas(html_texto).items():
                with self.subTest(pagina=nombre, concepto=concepto):
                    self.assertEqual(
                        len(valores), 1,
                        f"{nombre} publica {sorted(valores)} para "
                        f"«{R.CIFRAS_DECLARADAS.get(concepto, concepto)}»: "
                        "dos cifras del mismo concepto en la misma página")

    def test_el_sitio_entero_dice_lo_mismo(self):
        """Y tampoco entre páginas: el sitio se construye de un solo contexto
        en una sola corrida, así que dos páginas con distinto total del mismo
        registro serían la misma avería con un salto de página en medio."""
        todos = {}
        for nombre, html_texto in self.paginas.items():
            for concepto, valores in cifras_declaradas(html_texto).items():
                todos.setdefault(concepto, {})[nombre] = sorted(valores)
        for concepto, por_pagina in sorted(todos.items()):
            with self.subTest(concepto=concepto):
                distintos = {v for vs in por_pagina.values() for v in vs}
                self.assertEqual(
                    len(distintos), 1,
                    f"«{R.CIFRAS_DECLARADAS.get(concepto, concepto)}» sale "
                    f"con varios valores por el sitio: {por_pagina}")

    def test_el_guardian_tiene_algo_que_comparar(self):
        """La lección de los guardianes que no guardan: un vigilante sobre una
        página sin marcar estaría en verde eternamente. Cada concepto que el
        generador dice vigilar tiene que salir publicado al menos DOS veces; con
        una sola superficie no hay nada que contrastar."""
        veces = {c: 0 for c in R.CIFRAS_DECLARADAS}
        for html_texto in self.paginas.values():
            for concepto in re.findall(r'data-cifra="([^"]+)"', html_texto):
                veces[concepto] = veces.get(concepto, 0) + 1
        for concepto, n in sorted(veces.items()):
            with self.subTest(concepto=concepto):
                self.assertGreaterEqual(
                    n, 2, f"«{concepto}» se publica {n} vez en todo el sitio: "
                          "el guardián no estaría comparando nada")

    def test_toda_marca_del_artefacto_esta_declarada(self):
        """Un `data-cifra` con el nombre mal escrito no compara con nadie y
        pasaría el guardián sin hacer ruido."""
        for nombre, html_texto in self.paginas.items():
            for concepto in sorted(set(
                    re.findall(r'data-cifra="([^"]+)"', html_texto))):
                with self.subTest(pagina=nombre, concepto=concepto):
                    self.assertIn(concepto, R.CIFRAS_DECLARADAS,
                                  f"{nombre} marca «{concepto}», que no está "
                                  "en CIFRAS_DECLARADAS")

    def test_cae_si_una_superficie_se_queda_con_la_cifra_vieja(self):
        """La comprobación de que el guardián muerde, con la forma REAL del bug:
        una sola de las superficies de la portada se queda con el total de la
        víspera mientras las demás ya publican el de hoy. Se prueba con todos
        los conceptos que la portada publica por más de un camino, que son
        exactamente los que pueden divergir."""
        pagina = self.paginas["index.html"]
        marcas = list(_MARCA_CIFRA.finditer(pagina))
        repetidos = [c for c in R.CIFRAS_DECLARADAS
                     if sum(1 for m in marcas if m.group(2) == c) >= 2]
        self.assertTrue(repetidos, "la portada ya no publica ningún concepto "
                        "por dos caminos: no queda avería que reproducir")
        for concepto in repetidos:
            marca = next(m for m in marcas if m.group(2) == concepto)
            mutada = pagina.replace(
                marca.group(0), marca.group(0).replace(marca.group(3), "999"), 1)
            with self.subTest(concepto=concepto):
                self.assertNotEqual(mutada, pagina, "la mutación no cambió nada")
                self.assertEqual(
                    len(cifras_declaradas(mutada)[concepto]), 2,
                    "el lector no vio las dos cifras: el guardián no cazaría "
                    "el fallo que existe para cazar")


class TestSitioEnLaRaiz(unittest.TestCase):
    """El sitio vive en la raíz del dominio, no en /site/.

    La home del dominio tenía un meta-refresh y ningún contenido: cualquier
    enlace entrante al dominio aterrizaba en una página vacía."""

    RAIZ = Path(__file__).parent.parent

    def test_ninguna_pagina_se_referencia_bajo_site(self):
        for f in (self.RAIZ / "site").glob("*.html"):
            s = f.read_text(encoding="utf-8")
            self.assertNotIn("datosdelterremoto.org/site/", s,
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
        """Ni las filas, ni el gráfico, ni los chips, ni la prosa del pie: al
        navegador le quedan el filtro, el orden, la paginación y el recuento
        vivo. Lo que se borró no se guarda comentado — el blame es el archivo."""
        js = (Path(__file__).parent.parent / "site/rud.js").read_text(encoding="utf-8")
        self.assertIn("tablaHidratada", js)
        self.assertNotIn("tablaBuscable", js)
        self.assertNotIn("<tr>", js)
        self.assertNotIn("graficoFamilias", js)
        self.assertNotIn("altasDiarias", js)
        self.assertNotIn("Object.freeze", js)
        self.assertNotIn("todavía sin evaluar", js)
        self.assertNotIn('getElementById("generado")', js)

    def test_el_marcador_existe(self):
        html = (Path(__file__).parent.parent / "site/rud.html").read_text(encoding="utf-8")
        self.assertIn('<tbody data-gen="rud"></tbody>', html)

    def test_el_grafico_explica_las_dos_series_y_la_primera_captura(self):
        html = (Path(__file__).parent.parent / "site/rud.html").read_text(encoding="utf-8")
        self.assertIn("acumulado y nuevas por día", html)
        self.assertIn("desde la captura anterior", html)
        self.assertIn("El primer día no tiene una captura", html)


class TestGraficoRud(unittest.TestCase):
    """La columna es el cambio entre capturas, nunca el acumulado repetido.

    **Portados de `tests/test_frontend.py`**, donde llamaban por `node` a
    `rud.js::graficoFamilias`. El gráfico lo dibuja ahora el build, así que las
    mismas aserciones se hacen sobre el SVG que se sirve — y dejan de estar
    bajo `@skipUnless(NODE)`: el guardián del riesgo más difícil de ver de esta
    fase —un gráfico que se dibuja y miente— ya no depende de que el runner
    tenga node."""

    SERIE = [{"fecha": "2026-08-16", "familias": 100, "municipios": 2},
             {"fecha": "2026-08-17", "familias": 130, "municipios": 3},
             {"fecha": "2026-08-18", "familias": 145, "municipios": 4}]

    @staticmethod
    def svg(serie):
        return R.grafico_rud({"rud": {"serie": serie}})

    def test_altas_son_diferencias_y_el_primer_dia_no_inventa_una(self):
        self.assertEqual(R._altas_diarias(self.SERIE), [None, 30, 15])

    def test_svg_combina_columnas_y_curva_con_valores_visibles(self):
        svg = self.svg(self.SERIE)
        self.assertIn('data-altas="30"', svg)
        self.assertIn('data-altas="15"', svg)
        self.assertNotIn('data-altas="100"', svg)
        self.assertIn(">+30</text>", svg)
        self.assertIn(">+15</text>", svg)
        self.assertIn("sin base", svg)
        self.assertIn("Total acumulado", svg)
        self.assertIn("Nuevas desde captura anterior", svg)
        self.assertIn('aria-labelledby="rud-chart-title rud-chart-desc"', svg)

    def test_una_correccion_a_la_baja_no_se_convierte_en_cero(self):
        """El más valioso del grupo: distingue «bajó» de «no hay dato». Un
        registro también se corrige a la baja, y pintarlo como cero —o no
        pintarlo— borraría la corrección (R3, R16)."""
        svg = self.svg([{"fecha": "2026-08-16", "familias": 100, "municipios": 2},
                        {"fecha": "2026-08-17", "familias": 90, "municipios": 2}])
        self.assertIn('data-altas="-10"', svg)
        self.assertIn(">-10</text>", svg)
        self.assertIn("--critical", svg)

    # ------------------------------------- lo que gana el gráfico al portarse
    def test_el_eje_no_esta_del_reves(self):
        """En SVG la `y` crece hacia abajo, así que MÁS familias es MENOS `y`.
        Un signo invertido dibuja una serie que baja mientras el registro sube
        y no lo delata ningún número: el SVG se ve perfecto y miente."""
        svg = self.svg(self.SERIE)
        ys = [float(v) for v in re.findall(
            r'<circle cx="[\d.]+" cy="([\d.]+)" r="5"', svg)]
        self.assertEqual(len(ys), len(self.SERIE), "falta algún punto de la curva")
        self.assertEqual(ys, sorted(ys, reverse=True),
                         "la curva del acumulado baja mientras las familias suben")

    def test_el_grafico_sigue_el_tema_y_no_congela_ningun_color(self):
        """`ui.cssVar()` resolvía la variable a un color literal en el momento
        de dibujar: el SVG salía con los colores del tema que hubiera puesto y
        se quedaba así. Al escribirlo el build, un color literal quedaría
        además congelado en el archivo."""
        svg = self.svg(self.SERIE)
        self.assertIn("var(--good)", svg)
        self.assertIn("var(--muted)", svg)
        self.assertEqual(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]+)"', svg), [],
                         "un color literal dentro del SVG congela el tema claro")

    def test_el_desc_narra_la_serie_entera_dia_a_dia(self):
        """Son las ~80 palabras indexables que justifican el porte: hoy solo
        existían en la memoria del navegador. Crecen solas con la serie."""
        desc = re.search(r'<desc id="rud-chart-desc">(.*?)</desc>',
                         self.svg(self.SERIE), re.S).group(1)
        for d in self.SERIE:
            self.assertIn(R.fecha_larga(d["fecha"]), desc)
        self.assertIn("sin captura anterior", desc)
        self.assertIn("acumuladas", desc)

    def test_el_desc_del_dato_real_tiene_un_dia_por_punto(self):
        serie = R.contexto()["rud"]["serie"]
        desc = re.search(r'<desc id="rud-chart-desc">(.*?)</desc>',
                         R.grafico_rud(R.contexto()), re.S).group(1)
        self.assertEqual(len(re.findall(r"\d+ de \w+ de \d{4}", desc)), len(serie))

    def test_sin_serie_no_se_dibuja_un_lienzo_vacio_ni_se_devuelve_nada(self):
        """Una cadena vacía dejaría el contenedor `data-gen` vacío y el
        build lo daría por bueno; un SVG sin puntos sería peor todavía."""
        for rud in ({"serie": []}, {}, None):
            with self.subTest(rud=rud):
                salida = R.grafico_rud({"rud": rud})
                self.assertTrue(salida.strip())
                self.assertNotIn("<svg", salida)

    def test_el_grafico_llega_dibujado_al_artefacto(self):
        """La comprobación de fondo de todo el paso: `rud.html` pasa de servir
        cero `<svg>` a servir uno."""
        html = (ROOT / "dist" / "rud.html")
        if not html.exists():
            self.skipTest("no hay dist/ construido")
        self.assertEqual(html.read_text(encoding="utf-8").count("<svg"), 1)


class TestLosDosPlegablesDelRud(unittest.TestCase):
    """La introducción se reparte entre dos plegables y no se pierde una palabra.

    La página servía cuatro párrafos —268 palabras— entre la entradilla y el
    primer dato. Se pliegan en dos: arriba, antes de la tabla, los dos que
    enseñan a LEERLA (123 palabras); al final, los dos que dicen QUÉ ES el RUD
    y qué no es (145). El reparto lo decidió el 23-ago y los dos superan su
    umbral de 120 palabras.

    Es un movimiento, no una reescritura, y este test es lo único que lo
    distingue: sin él, resumir un párrafo «para que quepa» deja la suite en
    verde y se lleva por delante prosa que ya estaba publicada."""

    PALABRAS = {"Cómo leer estas cifras": 123, "Qué es el RUD y qué no es": 145}
    UMBRAL = 120        # nada se pliega por debajo (criterio del proyecto)

    @classmethod
    def setUpClass(cls):
        html = (ROOT / "site" / "rud.html").read_text(encoding="utf-8")
        cls.bloques = re.findall(
            r'<details class="pliegue[^"]*">(.*?)</details>', html, re.S)
        cls.html = html

    @staticmethod
    def _palabras(fragmento):
        return len(re.sub(r"<[^>]+>", " ", fragmento).split())

    def test_son_dos_y_ninguno_vive_dentro_del_otro(self):
        self.assertEqual(len(self.bloques), 2, "`rud.html` tiene dos plegables")
        for b in self.bloques:
            self.assertNotIn("<details", b, "ningún plegable dentro de otro")

    def test_cada_plegable_conserva_su_mitad_de_la_introduccion(self):
        visto = {}
        for b in self.bloques:
            titulo = re.search(r"<summary>(.*?)</summary>", b, re.S).group(1).strip()
            cuerpo = re.search(r'<section class="intro">(.*?)</section>', b, re.S)
            self.assertIsNotNone(
                cuerpo, f"«{titulo}» ya no envuelve su prosa en una .intro")
            visto[titulo] = self._palabras(cuerpo.group(1))
        self.assertEqual(visto, self.PALABRAS,
                         "alguien reescribió, resumió o perdió un párrafo de la "
                         "introducción: era un movimiento, no una redacción")
        self.assertEqual(sum(visto.values()), 268,
                         "las 268 palabras de la introducción no cuadran")
        for titulo, n in visto.items():
            self.assertGreaterEqual(
                n, self.UMBRAL,
                f"«{titulo}» tiene {n} palabras: nada se pliega por debajo de "
                f"{self.UMBRAL}, porque plegar lo corto solo esconde")

    def test_el_que_ensena_a_leer_va_antes_de_la_tabla_y_el_otro_al_final(self):
        """El orden es el argumento: se explica cómo leer la tabla ANTES de la
        tabla, y qué es el RUD después, para quien siga preguntándoselo."""
        i_como = self.html.index("Cómo leer estas cifras")
        i_zona = self.html.index('<div class="zona-datos">')
        i_que = self.html.index("Qué es el RUD y qué no es")
        self.assertLess(i_como, i_zona, "el «cómo leer» quedó debajo de la tabla")
        self.assertLess(i_zona, i_que, "el «qué es» quedó por encima de la tabla")

    def test_el_plegable_no_sangra_dos_veces(self):
        """Una `.intro` dentro de `details.pliegue` recibiría DOS ejes: el suyo
        (`margin: 6px var(--margen)`) más el del contenedor. El eje lo pone el
        contenedor y solo él — mismo fallo ya corregido en `.zona-datos >
        .contenido`. Sin esta regla el texto de los dos plegables empieza más
        adentro que su propio título, y la suite seguía en verde."""
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        regla = re.search(r"details\.pliegue\s*>\s*\.intro\s*\{([^}]*)\}", css)
        self.assertIsNotNone(regla, "no está la regla que quita el segundo eje")
        for lado in ("margin-left", "margin-right"):
            self.assertRegex(regla.group(1), rf"{lado}:\s*0",
                             f"el plegable sigue sangrando por {lado}")


class TestElGraficoSeLeeEnMovil(unittest.TestCase):
    """Los rótulos crecen en pantalla estrecha, y crecen lo que caben.

    El `viewBox` mide 900 y en un móvil de 375 px el SVG se dibuja sobre 313:
    un `font-size` de 10 vale 3,5 px efectivos. La solución es la que el mapa
    estático ya usa —subir la letra con una @media, porque el texto vive dentro
    del `viewBox` y encoge con él—, pero aquí hay tres topes que un ojo no ve:
    el rótulo del eje se escribe hacia la izquierda dentro del margen, los de
    los puntos se solapan si crecen más que la separación entre puntos, y la
    esquina de abajo a la izquierda tiene cuatro rótulos disputándose 16
    unidades. La serie crece cada día: estos tests avisan (R11) el día que deje
    de caber, en vez de publicar un gráfico ilegible.

    **Se comprueban las DOS bandas**, no solo la más estrecha: entre 481 y 760
    px se aplica únicamente la primera @media, y ahí los tamaños son otros. Un
    test que mirase solo la de 480 dejaría la tableta sin vigilancia."""

    ANCHO = 0.52        # ancho medio de carácter en proporción al cuerpo
    ALTO_ARRIBA = 0.78  # de la línea base hacia arriba
    ALTO_ABAJO = 0.22   # y hacia abajo

    @classmethod
    def setUpClass(cls):
        cls.svg = R.grafico_rud(R.contexto())
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        bloques = [(int(ancho), cuerpo) for ancho, cuerpo in re.findall(
            r"@media \(max-width: (\d+)px\) \{(.*?)\n\}", css, re.S)
            if ".grafico-rud" in cuerpo]
        # Cada banda es la cascada que de verdad se aplica a esa anchura: la
        # de 480 hereda lo de 760 y solo pisa lo que redeclara.
        cls.bandas, acumulado = {}, {}
        for ancho, cuerpo in sorted(bloques, key=lambda b: -b[0]):
            acumulado = {c: dict(v) for c, v in acumulado.items()}
            for sels, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", cuerpo):
                cpo = re.search(r"font-size:\s*([\d.]+)px", decls)
                mueve = re.search(r"translate\(\s*([-\d.]+)(?:px)?\s*,"
                                  r"\s*([-\d.]+)(?:px)?\s*\)", decls)
                # `display: none` es la tercera herramienta de la cascada, y
                # sin leerla estos guardianes miden cajas que el navegador no
                # dibuja: darían por superpuestos dos rótulos de los que solo
                # se ve uno. Se lee en los dos sentidos —`none` esconde y
                # cualquier otro valor devuelve a la vista— porque la banda de
                # 480 hereda de la de 760.
                muestra = re.search(r"display:\s*([\w-]+)", decls)
                for s in sels.split(","):
                    clase = re.search(r"\.(g-[\w-]+)", s)
                    if not clase:
                        continue
                    v = acumulado.setdefault(clase.group(1), {})
                    if cpo:
                        v["tam"] = float(cpo.group(1))
                    if mueve:
                        v["dx"] = float(mueve.group(1))
                        v["dy"] = float(mueve.group(2))
                    if muestra:
                        v["oculto"] = muestra.group(1) == "none"
            cls.bandas[ancho] = acumulado

    @staticmethod
    def _clases(atrs: str) -> list:
        """TODAS las clases `g-` del rótulo, no solo la primera.

        Los rótulos adelgazados llevan dos —`class="g-total g-alterna"`—, y la
        segunda es justo la que decide si se dibujan."""
        marca = re.search(r'class="([^"]*)"', atrs)
        return [c for c in (marca.group(1).split() if marca else [])
                if c.startswith("g-")]

    def _rotulos(self, clase, banda=None, svg=None):
        """Los textos de esa clase; si se pasa una banda, solo los que en ella
        se dibujan de verdad."""
        return [t for atrs, t in re.findall(r"<text ([^>]*)>(.*?)</text>",
                                            self.svg if svg is None else svg)
                if clase in self._clases(atrs)
                and (banda is None or not self._oculto(banda, self._clases(atrs)))]

    @staticmethod
    def _oculto(banda, clases) -> bool:
        return any(banda.get(c, {}).get("oculto") for c in clases)

    def _cajas(self, banda, svg=None):
        """Cada `<text>` que esa banda dibuja, con su caja aproximada."""
        svg = self.svg if svg is None else svg
        aparte = re.search(r'<g class="g-leyenda-2">(.*?)</g>', svg, re.S)
        dx_grupo = banda.get("g-leyenda-2", {}).get("dx", 0.0)
        cajas = []
        for atrs, texto in re.findall(r"<text ([^>]*)>(.*?)</text>", svg):
            clases = self._clases(atrs)
            conocidas = [c for c in clases if "tam" in banda.get(c, {})]
            if not conocidas or self._oculto(banda, clases):
                continue
            estilo = banda[conocidas[0]]
            cuerpo = estilo["tam"]
            x = float(re.search(r'x="([-\d.]+)"', atrs).group(1))
            y = float(re.search(r'y="([-\d.]+)"', atrs).group(1)) + estilo.get("dy", 0)
            ancla = re.search(r'text-anchor="(\w+)"', atrs)
            ancho = len(texto) * self.ANCHO * cuerpo
            x0 = {"end": x - ancho, "middle": x - ancho / 2}.get(
                ancla.group(1) if ancla else "start", x) + estilo.get("dx", 0)
            if aparte and f"<text {atrs}>" in aparte.group(1):
                x0 += dx_grupo
            cajas.append((f"{conocidas[0]}:{texto}", x0, x0 + ancho,
                          y - self.ALTO_ARRIBA * cuerpo, y + self.ALTO_ABAJO * cuerpo))
        return cajas

    def test_hay_dos_bandas_y_las_dos_agrandan_los_rotulos(self):
        """Guardián de sí mismo: sin esto, las comprobaciones de abajo
        recorrerían un diccionario vacío y pasarían sin mirar nada."""
        self.assertEqual(sorted(self.bandas), [480, 760],
                         "el gráfico ya no declara sus dos bandas de @media")
        for ancho, banda in self.bandas.items():
            for clase in ("g-eje", "g-alta", "g-dia", "g-total", "g-leyenda"):
                with self.subTest(ancho=ancho, clase=clase):
                    self.assertIn(clase, banda,
                                  f"`.{clase}` no crece por debajo de {ancho}px")
                    self.assertGreater(banda[clase]["tam"], 11,
                                       f"`.{clase}` no gana nada respecto al SVG")
                    # VISIBLES en esa banda: desde que el móvil esconde uno de
                    # cada dos rótulos, «existe en el SVG» ya no basta. Un
                    # `display: none` sobre la clase entera dejaría el gráfico
                    # mudo y todo lo que estos tests miden —anchos, solapes—
                    # pasaría en verde sobre una lista vacía.
                    self.assertTrue(self._rotulos(clase, banda),
                                    f"`.{clase}` no se dibuja por debajo de "
                                    f"{ancho}px: el gráfico se quedó mudo")

    def test_el_movil_esconde_como_mucho_uno_de_cada_dos_y_nunca_el_ultimo(self):
        """El adelgazado es un peaje, no una barra libre.

        Esconder rótulos es lo único que deja agrandar la letra en un móvil,
        pero también es la forma más fácil de apagar a los guardianes de
        arriba: sin nadie que dibuje, nada se pisa. Se fija el trato —la mitad
        como mucho— y se protege el rótulo que de verdad importa, el del último
        día, que es la cifra vigente del registro. Contando la alternancia
        desde el principio, una serie de longitud par lo apagaba justo a él."""
        for largo, svg in self._las_dos_paridades():
            puntos = len(re.findall(r'<circle cx="[\d.]+" cy="[\d.]+" r="5"', svg))
            ultimo = {}
            for atrs, _t in re.findall(r"<text ([^>]*)>(.*?)</text>", svg):
                for c in self._clases(atrs):
                    if c in ("g-alta", "g-dia", "g-total"):
                        ultimo[c] = self._clases(atrs)
            for ancho, banda in self.bandas.items():
                for clase in ("g-alta", "g-dia", "g-total"):
                    with self.subTest(serie=largo, ancho=ancho, clase=clase):
                        visibles = len(self._rotulos(clase, banda, svg))
                        self.assertGreaterEqual(
                            visibles, puntos // 2,
                            f"por debajo de {ancho}px se esconden más de la "
                            f"mitad de los rótulos `.{clase}`: {visibles} de "
                            f"{puntos}")
                        self.assertFalse(
                            self._oculto(banda, ultimo.get(clase, [])),
                            f"con {largo} capturas y por debajo de {ancho}px se "
                            f"esconde el `.{clase}` del último día, que es la "
                            "cifra vigente del registro")

    def _las_dos_paridades(self):
        """El SVG de hoy y el de mañana, para que la serie tenga las dos
        longitudes posibles.

        No es celo: la alternancia se cuenta desde el final PORQUE contándola
        desde el principio el último día desaparecía en las series de longitud
        par —y hoy la serie es impar, así que un test que solo mirase la de hoy
        daría verde con ese fallo puesto."""
        serie = R.contexto()["rud"]["serie"]
        manana = [*serie, {**serie[-1], "fecha": (date.fromisoformat(
            serie[-1]["fecha"]) + timedelta(days=1)).isoformat(),
            "familias": (serie[-1].get("familias") or 0) + 1}]
        return [(len(serie), self.svg),
                (len(manana), R.grafico_rud({"rud": {"serie": manana}}))]

    def test_el_desc_narra_tambien_lo_que_el_movil_esconde(self):
        """El trato del adelgazado solo se sostiene si el dato no se pierde:
        lo que el móvil deja de rotular sigue en el `<desc>`, que es lo que lee
        un lector de pantalla, y en la tabla de debajo. Un día por punto,
        siempre, se esconda o no su rótulo."""
        puntos = len(re.findall(r'<circle cx="[\d.]+" cy="[\d.]+" r="5"', self.svg))
        desc = re.search(r'<desc id="rud-chart-desc">(.*?)</desc>', self.svg, re.S)
        self.assertEqual(len(re.findall(r"\d+ de \w+ de \d{4}", desc.group(1))),
                         puntos, "el `<desc>` dejó de narrar algún día")

    def test_el_rotulo_del_eje_no_se_sale_del_lienzo(self):
        """Va anclado por la derecha en `x = m_l - 6`, así que todo su ancho
        cae hacia la izquierda: si pasa de ahí, el SVG lo recorta."""
        hueco = min(float(x) for x in re.findall(
            r'<text x="([\d.]+)"[^>]*class="g-eje"', self.svg))
        for ancho, banda in self.bandas.items():
            for texto in self._rotulos("g-eje"):
                with self.subTest(ancho=ancho, texto=texto):
                    medida = len(texto) * self.ANCHO * banda["g-eje"]["tam"]
                    self.assertLess(medida, hueco,
                                    f"«{texto}» mide {medida:.0f} y solo hay "
                                    f"{hueco:.0f} hasta el borde: se recorta")

    def test_los_rotulos_del_grafico_caben_en_movil(self):
        """Ningún rótulo puede ser más ancho que la banda que ocupa.

        La banda es la distancia entre los rótulos de su clase QUE SE DIBUJAN,
        no la que hay entre puntos: desde que el móvil esconde uno de cada dos,
        cada rótulo visible dispone de dos bandas de día. Medirlo contra la
        separación de los puntos acusaría de solaparse a dos rótulos que no
        coinciden en pantalla. Es el aviso adelantado del test de solapes de
        abajo: este cae con el rótulo MÁS LARGO de la clase aunque hoy esté en
        un hueco ancho, así que canta el día antes de que se pisen de verdad."""
        for ancho, banda in self.bandas.items():
            for clase in ("g-alta", "g-dia", "g-total"):
                with self.subTest(ancho=ancho, clase=clase):
                    centros = sorted((x0 + x1) / 2 for n, x0, x1, _, _
                                     in self._cajas(banda)
                                     if n.startswith(clase + ":"))
                    if len(centros) < 2:
                        self.skipTest("un solo rótulo no tiene con quién chocar")
                    paso = min(b - a for a, b in zip(centros, centros[1:]))
                    largo = max((len(t) for t in self._rotulos(clase, banda)),
                                default=0)
                    medida = largo * self.ANCHO * banda[clase]["tam"]
                    self.assertLess(
                        medida, paso,
                        f"a {banda[clase]['tam']:.0f}px los rótulos `.{clase}` "
                        f"miden {medida:.0f} y su banda es de {paso:.0f}: "
                        "con la serie más larga se solapan. Baja el tamaño de "
                        f"la @media de {ancho}px o cambia la geometría de "
                        "`grafico_rud`.")

    def test_ningun_rotulo_se_pisa_en_movil(self):
        """La geometría exacta, caja por caja: es el guardián de verdad de
        esta clase, y el que se puso rojo el 25-ago-2026.

        Al crecer la letra se disputan la esquina de abajo a la izquierda el
        acumulado del primer día, el «sin base», el cero del eje y la fecha; y
        al crecer la serie se pisan también el alta y el acumulado del mismo
        día. Las @media los separan —escondiendo el «sin base», bajando el
        alta, callando uno de cada dos—; sin este test, subir un tamaño o
        deshacer un desplazamiento los vuelve a juntar y nadie se entera hasta
        que alguien abre la página en un móvil."""
        for ancho, banda in self.bandas.items():
            cajas = self._cajas(banda)
            pisados = [(a[0], b[0]) for i, a in enumerate(cajas)
                       for b in cajas[i + 1:]
                       if a[1] < b[2] and b[1] < a[2] and a[3] < b[4] and b[3] < a[4]]
            with self.subTest(ancho=ancho):
                self.assertEqual(
                    pisados, [],
                    f"rótulos superpuestos por debajo de {ancho}px: {pisados}. "
                    f"Baja el tamaño en esa @media o separa las cajas con un "
                    "`transform`.")

    def test_el_grafico_todavia_cabe_con_cinco_capturas_mas(self):
        """Avisa DÍAS antes de romperse, no el día que se rompe.

        El 25-ago-2026 la captura del RUD añadió su noveno punto y el gráfico
        pasó de caber a pisarse de un día para otro: el rojo llegó con la
        publicación encima, que es el peor momento para decidir cómo se dibuja
        un gráfico. La geometría se estrecha sola —el ancho útil es fijo y la
        serie crece— así que la pregunta no es «¿cabe hoy?» sino «¿cuánto le
        queda?».

        Se prolonga la serie cinco capturas con el crecimiento de la última y
        se exige que siga sin solapes. **No es una predicción del registro**:
        el RUD puede crecer más o menos, y da igual. Es margen: si esto cae,
        quedan días para decidir con calma —adelgazar más, cambiar la
        geometría, recortar la ventana— en vez de con la imprenta parada."""
        serie = R.contexto()["rud"]["serie"]
        if len(serie) < 2:
            self.skipTest("con un punto no hay crecimiento que prolongar")
        ultimo = (serie[-1].get("familias") or 0) - (serie[-2].get("familias") or 0)
        futura = [dict(d) for d in serie]
        for _ in range(5):
            dia = date.fromisoformat(futura[-1]["fecha"]) + timedelta(days=1)
            futura.append({"fecha": dia.isoformat(),
                           "familias": (futura[-1].get("familias") or 0) + ultimo,
                           "municipios": futura[-1].get("municipios")})
        svg = R.grafico_rud({"rud": {"serie": futura}})
        for ancho, banda in self.bandas.items():
            cajas = self._cajas(banda, svg)
            pisados = [(a[0], b[0]) for i, a in enumerate(cajas)
                       for b in cajas[i + 1:]
                       if a[1] < b[2] and b[1] < a[2] and a[3] < b[4] and b[3] < a[4]]
            with self.subTest(ancho=ancho):
                self.assertEqual(
                    pisados, [],
                    f"con cinco capturas más el gráfico se pisa por debajo de "
                    f"{ancho}px: {pisados}. Quedan días, no horas: decidir "
                    "ahora cómo se adelgaza antes de que lo decida la prisa.")

    def test_ningun_rotulo_se_sale_por_abajo(self):
        """Los desplazamientos que separan la esquina empujan hacia el pie del
        lienzo, y lo que pasa de `H` no se dibuja."""
        alto = float(re.search(r'viewBox="0 0 \d+ ([\d.]+)"', self.svg).group(1))
        for ancho, banda in self.bandas.items():
            for nombre, _, _, _, abajo in self._cajas(banda):
                with self.subTest(ancho=ancho, rotulo=nombre):
                    self.assertLessEqual(abajo, alto,
                                         f"«{nombre}» cae fuera del lienzo")


class TestChipsDelRud(unittest.TestCase):
    """El recuento del chip y la etiqueta de la fila salen del mismo predicado.

    Vivían separados —el array `CHIPS` de `site/rud.js` contaba las filas ya
    escritas, y `filas_rud` las etiquetaba con su propia copia de las
    condiciones—, así que nada impedía que «Nuevos (49)» filtrase otra cosa
   . `CHIPS_RUD` es ahora la única definición."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.chips = R.chips_rud(cls.ctx)
        cls.filas = R.filas_rud(cls.ctx)

    def test_el_recuento_del_chip_es_el_de_las_etiquetas_de_fila(self):
        """El guardián de la divergencia: cuenta lo que dice el botón y lo que
        hay escrito en las filas, y compara."""
        dichos = dict(re.findall(r'data-chip="(\w+)"[^>]*>[^<]*\((\d[\d.]*)\)</button>',
                                 self.chips))
        self.assertEqual(set(dichos), {c[0] for c in R.CHIPS_RUD},
                         "algún chip dejó de decir su recuento")
        total = len(self.ctx["rud"]["municipios"])
        for clave, dicho in dichos.items():
            with self.subTest(chip=clave):
                n = int(dicho.replace(".", ""))
                etiquetadas = (total if clave == "todos" else
                               len(re.findall(rf'data-chips="[^"]*\b{clave}\b',
                                              self.filas)))
                self.assertEqual(n, etiquetadas,
                                 f"«{clave}»: el chip dice {n} y hay {etiquetadas} "
                                 f"filas etiquetadas")

    def test_los_cuatro_chips_dicen_algo_y_ninguno_sale_a_cero_por_error(self):
        for clave, etiqueta, _, _ in R.CHIPS_RUD:
            with self.subTest(chip=clave):
                self.assertIn(f'data-chip="{clave}"', self.chips)
                self.assertIn(etiqueta, self.chips)

    def test_el_chip_declara_su_estado_de_las_dos_maneras(self):
        """`styles.css` funde `.chip.activa` y `.chip[aria-pressed="true"]` en un
        solo selector: la clase estiliza, el atributo lo anuncia el lector de
        pantalla. El build las pinta juntas y el navegador las mueve juntas."""
        self.assertIn('class="chip activa" data-chip="todos" aria-pressed="true"',
                      self.chips)
        self.assertEqual(self.chips.count('aria-pressed="false"'),
                         len(R.CHIPS_RUD) - 1)
        js = (ROOT / "site" / "rud.js").read_text(encoding="utf-8")
        self.assertIn('setAttribute("aria-pressed"', js)
        self.assertIn('classList.toggle("activa"', js)

    def test_el_javascript_ya_no_define_los_chips(self):
        """Dejar las dos definiciones es una copia condenada a divergir el día uno."""
        js = (ROOT / "site" / "rud.js").read_text(encoding="utf-8")
        self.assertNotIn("const CHIPS", js)
        # el atributo lo ESCRIBE el build; el navegador solo lee `dataset.chip`
        self.assertNotIn('data-chip="', js)
        for _, etiqueta, tip, _ in R.CHIPS_RUD:
            if tip:
                self.assertNotIn(tip, js, "la explicación del chip vuelve a "
                                          "estar en dos sitios")
            if " " in etiqueta:   # «Todos» y «Nuevos» son palabras corrientes
                self.assertNotIn(etiqueta, js,
                                 "el rótulo del chip vuelve a estar en dos sitios")


class TestEntradillaRud(unittest.TestCase):
    """La frase que resume la página, con el hallazgo que no se publicaba.

    El RUD no se está estabilizando y no crece por donde parece: la mayor parte
    del último salto es revisión al alza de municipios ya registrados, no
    municipios nuevos. Cualquier total suyo es un mínimo provisional (R16)."""

    SERIE = [{"fecha": "2026-08-20", "familias": 1000, "personas": 2000,
              "municipios": 10, "viv_destruidas": 5, "viv_averiadas": 7},
             {"fecha": "2026-08-21", "familias": 1300, "personas": 2600,
              "municipios": 12, "viv_destruidas": 8, "viv_averiadas": 9}]
    DETALLE = {
        "2026-08-20": [{"departamento": "CHOCÓ", "municipio": "QUIBDÓ", "familias": 600},
                       {"departamento": "VALLE DEL CAUCA", "municipio": "CALI",
                        "familias": 400}],
        "2026-08-21": [{"departamento": "CHOCÓ", "municipio": "QUIBDÓ", "familias": 780},
                       {"departamento": "VALLE DEL CAUCA", "municipio": "CALI",
                        "familias": 450},
                       {"departamento": "CALDAS", "municipio": "ANSERMA", "familias": 70}],
    }

    def entradilla(self, **cambios):
        rud = {"serie": self.SERIE, "detalle_diario": self.DETALLE}
        rud.update(cambios)
        return R.entradilla_rud({"rud": rud})

    def test_las_cifras_son_las_de_la_ultima_captura(self):
        texto = self.entradilla()
        for n in ("1.300", "2.600", "12", "8", "9"):
            self.assertIn(n, texto)
        self.assertIn("21 de agosto de 2026", texto,
                      "una cifra del RUD sin su corte miente en 48 horas")

    def test_el_desglose_del_salto_se_calcula_y_suma_el_salto(self):
        """230 de revisión (180 de Quibdó + 50 de Cali) y 70 de un municipio
        nuevo: 300, que es justo lo que subió la serie."""
        texto = self.entradilla()
        self.assertIn("300 familias", texto)
        self.assertIn("230", texto)
        self.assertIn("70", texto)
        self.assertIn("primera vez", texto)

    def test_el_rotulo_de_minimo_provisional_no_falta(self):
        self.assertIn("mínimo provisional", self.entradilla())

    def test_sin_segunda_captura_la_frase_del_salto_se_retira_entera(self):
        """No queda un «de las — familias»: la oración desaparece."""
        texto = self.entradilla(serie=self.SERIE[-1:])
        self.assertNotIn("De las", texto)
        self.assertNotIn("primera vez", texto)
        self.assertNotIn("—", texto.replace("—<b>", "").replace("</b>—", ""))
        self.assertIn("mínimo provisional", texto)

    def test_sin_detalle_diario_tampoco_se_inventa_el_reparto(self):
        texto = self.entradilla(detalle_diario={})
        self.assertNotIn("De las", texto)
        self.assertIn("1.300", texto)

    def test_un_desglose_que_no_cuadra_no_se_publica(self):
        """aritmética que no cierra no se imprime.

        El detalle justifica 170 (100 de revisión en Quibdó y 70 de un
        municipio nuevo) y la serie dice +300: el detalle diario y la serie ya
        no hablan del mismo corte. Las DOS mitades del contraste existen aquí a
        propósito —revisión y nuevos son mayores que cero—, para que lo único
        que pueda rechazar la frase sea la suma. La primera versión de este
        test caía antes en el otro guardián y pasaba en verde con el de la
        aritmética desconectado."""
        detalle = {"2026-08-20": self.DETALLE["2026-08-20"],
                   "2026-08-21": [{"departamento": "CHOCÓ", "municipio": "QUIBDÓ",
                                   "familias": 700},
                                  {"departamento": "VALLE DEL CAUCA",
                                   "municipio": "CALI", "familias": 400},
                                  {"departamento": "CALDAS", "municipio": "ANSERMA",
                                   "familias": 70}]}
        reparto = R._salto_del_rud({"serie": self.SERIE, "detalle_diario": detalle})
        self.assertIsNone(reparto, "un reparto que no suma su propio total")
        self.assertNotIn("De las", self.entradilla(detalle_diario=detalle))

    def test_si_el_salto_no_tiene_las_dos_mitades_no_hay_frase_que_contar(self):
        """La oración termina afirmando que lo que crece son los municipios ya
        contados. Si el salto entero viene de municipios nuevos, esa conclusión
        es falsa: la frase no se corrige, se retira."""
        detalle = {"2026-08-20": self.DETALLE["2026-08-20"],
                   "2026-08-21": self.DETALLE["2026-08-20"] +
                   [{"departamento": "CALDAS", "municipio": "ANSERMA",
                     "familias": 300}]}
        self.assertIsNone(R._salto_del_rud({"serie": self.SERIE,
                                            "detalle_diario": detalle}))
        texto = self.entradilla(detalle_diario=detalle)
        self.assertNotIn("De las", texto)
        self.assertNotIn("son los municipios ya contados", texto)

    def test_sin_ninguna_captura_lo_dice_y_jamas_devuelve_vacio(self):
        """Era el aviso que `rud.js` escribía en el navegador: quien no ejecuta
        JavaScript no lo leía nunca. Y una cadena vacía rompería el build."""
        for rud in ({"serie": []}, {}, None):
            with self.subTest(rud=rud):
                texto = R.entradilla_rud({"rud": rud})
                self.assertTrue(texto.strip())
                self.assertIn("Todavía no hay ninguna captura", texto)

    def test_una_cifra_ausente_se_calla_y_no_se_convierte_en_cero(self):
        """R3: sin viviendas cargadas no hay «0 viviendas destruidas»."""
        serie = [dict(self.SERIE[-1], viv_destruidas=None, viv_averiadas=None)]
        texto = R.entradilla_rud({"rud": {"serie": serie}})
        self.assertNotIn("viviendas", texto)
        self.assertNotIn(" 0 ", texto)
        self.assertIn("1.300", texto)

    def test_el_dato_real_cuadra_con_la_serie_publicada(self):
        """Segunda vía sobre lo que se va a publicar de verdad.

        El par de capturas NO se fija a mano —ni siquiera «el último»—: se
        recorre la serie real hacia atrás y se toma el más reciente cuyo
        reparto se publicaría. Exigir que el último cuadre es fijar un dato a
        mano con otro nombre, y quien decide si cuadra es la fuente: el
        23-ago-2026 su detalle diario sumaba 15.435 familias donde su propia
        serie decía 15.433, dos de diferencia que el monitor no inventó y que
        hacen desaparecer la frase, que es exactamente lo que debe pasar.

        Lo que se comprueba es invariante: que la prosa publica las mismas
        cifras que calculó el reparto, y que cuando el cálculo se calla la
        prosa también —ni media oración—. Si ya no cuadra ningún corte, el
        test lo cuenta como noticia (R12) en vez de dar un rojo opaco.
        """
        ctx = R.contexto()
        rud = ctx["rud"]
        serie = rud["serie"]
        par = salto = None
        for i in range(len(serie) - 1, 0, -1):
            candidato = {"serie": serie[i - 1:i + 1],
                         "detalle_diario": rud["detalle_diario"]}
            if (salto := R._salto_del_rud(candidato)):
                par = candidato
                break
        self.assertIsNotNone(
            par,
            "el detalle diario del RUD ya no cuadra con su serie en ningún "
            "corte: las dos mitades del registro dejaron de hablar del mismo "
            "día. Eso es noticia del monitor, no un test que arreglar")
        self.assertEqual(
            round(salto["nuevos"] + salto["revision"]),
            round(par["serie"][-1]["familias"] - par["serie"][0]["familias"]))
        texto = R.entradilla_rud({"rud": par})
        for cifra in ("salto", "revision", "nuevos", "municipios_nuevos"):
            self.assertIn(R.fmt(salto[cifra]), texto,
                          f"la prosa no publica el {cifra} que calculó")
        # y lo que hoy sale de verdad: si el último corte no cuadra, la
        # oración no aparece a medias en la entradilla que se publica
        hoy, entradilla = R._salto_del_rud(rud), R.entradilla_rud(ctx)
        if hoy:
            self.assertIn(R.fmt(hoy["revision"]), entradilla)
        else:
            self.assertNotIn("De las", entradilla)


class TestNotaRud(unittest.TestCase):
    """El pie de la tabla: la prosa invariante la escribe el build, el recuento
    vivo se queda en el navegador. Ni una palabra en los dos sitios."""

    def test_dice_lo_que_no_depende_de_ningun_filtro(self):
        nota = R.nota_rud(R.contexto())
        self.assertIn("La columna Δ compara con la captura anterior", nota)
        self.assertIn("Serie iniciada el", nota)
        self.assertIn("todavía sin evaluar", nota)

    def test_no_se_lleva_el_recuento_vivo(self):
        """Sabe cuántos municipios hay, pero no cuántos quedan filtrados: eso
        solo lo sabe el navegador."""
        nota = R.nota_rud(R.contexto())
        self.assertNotIn("filtros activos", nota)
        self.assertNotIn("de 15 en 15", nota)

    def test_la_advertencia_de_puntos_reconstruidos_es_condicional(self):
        """R11: el día que no quede ningún punto reconstruido, la frase
        desaparece sola. Nadie tiene que acordarse de borrarla."""
        serie = [{"fecha": "2026-08-20"}, {"fecha": "2026-08-21"}]
        self.assertNotIn("puntos huecos", R.nota_rud({"rud": {"serie": serie}}))
        con = [dict(serie[0], reconstruido=True), serie[1]]
        self.assertIn("puntos huecos", R.nota_rud({"rud": {"serie": con}}))

    def test_el_literal_no_vive_ya_en_el_javascript(self):
        """La nota duplicada era el riesgo 4 de la fase: dos redacciones de lo
        mismo, y el día que una cambiara la página diría dos cosas."""
        js = (ROOT / "site" / "rud.js").read_text(encoding="utf-8")
        self.assertNotIn("todavía sin evaluar", js)
        self.assertNotIn("Serie iniciada", js)
        self.assertNotIn("La columna Δ", js)

    def test_sin_serie_no_devuelve_vacio(self):
        for rud in ({"serie": []}, {}, None):
            with self.subTest(rud=rud):
                self.assertTrue(R.nota_rud({"rud": rud}).strip())


class TestPiezasDelRudLleganEscritas(unittest.TestCase):
    """Los cinco contenedores de `rud.html` llegan llenos al artefacto.

    Se ejecuta el inyector de verdad sobre el HTML del repositorio, que es como
    se construye `dist/`: así cae también si alguien quita la marca, mete un
    salto de línea entre la apertura y el cierre, cambia la etiqueta del
    contenedor o desconecta el generador."""

    CLAVES = ("rud-sello", "rud-resumen", "rud-grafico", "rud-chips", "rud-nota")

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "site" / "rud.html", cls.tmp / "rud.html")
        cls.hechas = R.inyectar_prerenderizado(cls.tmp, R.contexto())
        cls.html = (cls.tmp / "rud.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cuerpo(self, clave: str) -> str:
        m = re.search(rf'<(tbody|ul|span|section|p)[^>]*\bdata-gen="{clave}"[^>]*>'
                      rf'(.*?)</\1>', self.html, re.S)
        self.assertTrue(m, f"«{clave}» ya no está en site/rud.html")
        return m.group(2)

    def test_los_cinco_contenedores_llegan_no_vacios(self):
        for clave in self.CLAVES:
            with self.subTest(clave=clave):
                self.assertIn(clave, self.hechas,
                              f"el inyector no reconoció «{clave}»")
                self.assertTrue(self.cuerpo(clave).strip(),
                                f"«{clave}» quedó vacío en el artefacto")

    def test_el_grafico_es_un_svg_de_verdad(self):
        cuerpo = self.cuerpo("rud-grafico")
        self.assertIn("<svg", cuerpo)
        self.assertIn("<desc", cuerpo)

    def test_el_marcador_va_vacio_en_el_repositorio(self):
        """Todo contenedor marcado se versiona vacío, y con la apertura pegada
        al cierre: un salto de línea y la marca no casa."""
        fuente = (ROOT / "site" / "rud.html").read_text(encoding="utf-8")
        for etiqueta, clave in (("section", "rud-resumen"), ("section", "rud-grafico"),
                                ("section", "rud-chips"), ("span", "rud-nota")):
            with self.subTest(clave=clave):
                self.assertRegex(
                    fuente,
                    rf'<{etiqueta}[^>]*\bdata-gen="{clave}"[^>]*></{etiqueta}>')

    def test_el_recuento_vivo_sigue_teniendo_su_hueco_vacio(self):
        """`#rud-nota` lo escribe el navegador con cada filtro; si lo llenara el
        build, la primera pulsación lo borraría."""
        fuente = (ROOT / "site" / "rud.html").read_text(encoding="utf-8")
        self.assertIn('<p class="note" id="rud-nota"></p>', fuente)


class TestEspejoDeDiaMes(unittest.TestCase):
    """`dia_mes` es el cuarto helper de formato que vive en los dos lenguajes.

    El eje del gráfico lo rotulaba `UI.diaMes` en el navegador; ahora lo escribe
    el build. Si divergen, el mismo día se leería distinto según quién dibuje."""

    FECHAS = ("2026-08-10", "2026-01-01", "2026-12-31", "2026-09-05", "")

    def test_el_formato_es_el_esperado(self):
        self.assertEqual(R.dia_mes("2026-08-18"), "18-ago")
        self.assertEqual(R.dia_mes("2026-01-01"), "1-ene")
        self.assertEqual(R.dia_mes(None), "—")

    def test_el_eje_no_repite_el_ano_que_ya_declara_el_grafico(self):
        self.assertNotIn("2026", R.dia_mes("2026-08-18"))

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_es_espejo_ejecutado_de_ui_js(self):
        for iso in self.FECHAS:
            with self.subTest(iso=iso):
                self.assertEqual(correr_ui(f"UI.diaMes({json.dumps(iso)})"),
                                 R.dia_mes(iso),
                                 "diaMes ha divergido entre ui.js y render_html.py")


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
        # El guardián miraba el NOMBRE de la constante (`OFICIALES_BASE}/…`), y
        # esa constante ya no existe en el JavaScript: quien reintrodujera la
        # llamada al worker escribiendo la URL a mano habría pasado en verde.
        # Se vigila el destino, que es lo que de verdad importa.
        self.assertNotIn("oficiales-ai", js)
        self.assertNotIn("workers.dev", js)


class TestLosDosPlegablesDeBalances(unittest.TestCase):
    """La página de balances abre con el dato y pliega la explicación.

    Mismo criterio que el RUD (fase 3): la advertencia editorial —los dos
    párrafos que explican por qué las cifras no coinciden— se pliega ANTES de
    los datos, y el «cómo se recogen» (la presentación más la metodología
    entera) baja al final. La FAQ deja de ser un `<details>` dentro de otro:
    era la única forma de plegarla al final sin anidar plegables.

    El párrafo de la advertencia y el de la presentación son un movimiento, no
    una reescritura; el primer párrafo del plegable de arriba sí es nuevo (es
    el rótulo largo del criterio R16: máximo informado, lo rechazado se
    enseña). Los recuentos exactos son lo único que distingue mover de
    resumir."""

    PALABRAS = {"Por qué las cifras no coinciden": 168,
                "Cómo se recogen y se validan estos balances": 641}
    UMBRAL = 120        # nada se pliega por debajo (criterio del proyecto)

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site" / "balances.html").read_text(encoding="utf-8")
        cls.bloques = re.findall(
            r'<details class="pliegue[^"]*">(.*?)</details>', cls.html, re.S)

    @staticmethod
    def _palabras(fragmento):
        return len(re.sub(r"<[^>]+>", " ", fragmento).split())

    def test_son_dos_y_ninguno_vive_dentro_del_otro(self):
        self.assertEqual(len(self.bloques), 2,
                         "`balances.html` tiene dos plegables")
        for b in self.bloques:
            self.assertNotIn("<details", b, "ningún plegable dentro de otro")
        self.assertEqual(self.html.count("<details"), 2,
                         "la FAQ ya no vive en un tercer <details> anidado")

    def test_cada_plegable_conserva_su_prosa(self):
        visto = {}
        for b in self.bloques:
            titulo = re.search(r"<summary>(.*?)</summary>", b, re.S).group(1).strip()
            cuerpo = re.search(r'<section class="intro">(.*?)</section>', b, re.S)
            self.assertIsNotNone(
                cuerpo, f"«{titulo}» ya no envuelve su prosa en una .intro")
            visto[titulo] = self._palabras(cuerpo.group(1))
        self.assertEqual(visto, self.PALABRAS,
                         "alguien reescribió, resumió o perdió un párrafo: era "
                         "un movimiento, no una redacción")
        for titulo, n in visto.items():
            self.assertGreaterEqual(
                n, self.UMBRAL,
                f"«{titulo}» tiene {n} palabras: nada se pliega por debajo de "
                f"{self.UMBRAL}, porque plegar lo corto solo esconde")

    def test_la_advertencia_pliega_arriba_y_la_metodologia_al_final(self):
        """El orden es el argumento: primero el dato, la advertencia a un
        clic encima de él, y la metodología completa al final."""
        i_por_que = self.html.index("Por qué las cifras no coinciden")
        i_zona = self.html.index('<div class="zona-datos">')
        i_como = self.html.index("Cómo se recogen y se validan estos balances")
        self.assertLess(i_por_que, i_zona, "la advertencia quedó bajo los datos")
        self.assertLess(i_zona, i_como, "la metodología quedó encima de los datos")

    def test_el_plegable_de_arriba_conserva_el_lenguaje_de_r16(self):
        """R16 gobierna esta página: si el texto plegado pierde «máximo
        informado» o deja de decir que lo rechazado se enseña con su motivo,
        el marco editorial de la serie desaparece de la explicación."""
        texto = " ".join(re.sub(r"<[^>]+>", " ", self.bloques[0]).split())
        self.assertIn("máximo informado", texto)
        self.assertIn("lo que no entra en la serie se enseña con su motivo", texto)

    def test_ningun_titulo_de_plegable_lleva_emoticono(self):
        for b in self.bloques:
            titulo = re.search(r"<summary>(.*?)</summary>", b, re.S).group(1)
            self.assertFalse(
                re.search(r"[\U0001F000-\U0001FAFF☀-➿]", titulo),
                f"el título «{titulo.strip()}» lleva un emoticono")


class TestComparativaNoSeContradice(unittest.TestCase):
    """La tabla RUD contra medios y la nota que la explica dicen lo mismo.

    La nota estaba escrita a mano y afirmaba que la diferencia «mide cuánto
    falta por registrar formalmente» —o sea, que el RUD va por detrás—
    mientras la tabla que tiene justo encima publicaba 199.376 familias en el
    RUD contra 146.188 en los medios. **El RUD va por delante en familias y en
    personas desde hace días**, y la nota seguía contando el estado de otro
    día como si fuera una ley. Encima, la columna «Diferencia» escondía la
    dirección con un `abs()`: el lector no tenía ni siquiera cómo desmentir la
    nota sin restar a ojo dos columnas de seis cifras.

    Ahora las dos superficies salen del mismo `_filas_comparativa` y este
    guardián las contrasta **entre sí**, sobre el artefacto: no comprueba qué
    indicador va por delante —eso cambia cada día y un test que lo fijara
    caducaría mañana—, comprueba que la nota y la tabla no puedan decir cosas
    distintas.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "site" / "balances.html", cls.tmp / "balances.html")
        R.inyectar_prerenderizado(cls.tmp, R.contexto())
        html = (cls.tmp / "balances.html").read_text(encoding="utf-8")
        cuerpo = re.search(r'<tbody[^>]*data-gen="comparativa-filas"[^>]*>'
                           r"(.*?)</tbody>", html, re.S)
        assert cuerpo, "la tabla de la comparativa ya no está en balances.html"
        cls.filas = re.findall(r"<tr>(.*?)</tr>", cuerpo.group(1), re.S)
        nota = re.search(r'<p[^>]*data-gen="comparativa-nota"[^>]*>(.*?)</p>',
                         html, re.S)
        assert nota, "la nota de la comparativa ya no está en balances.html"
        cls.nota = nota.group(1)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _num(celda: str):
        """El número de una celda, o None si dice «no registra» o «—»."""
        texto = re.sub(r"<[^>]+>", "", celda).strip()
        crudo = texto.replace(".", "").replace(",", ".")
        try:
            return float(crudo)
        except ValueError:
            return None

    def tabla(self) -> dict:
        """{indicador en minúscula: (rud, medios, lado que dice la celda)}."""
        fuera = {}
        for fila in self.filas:
            celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
            self.assertEqual(len(celdas), 4, "la fila no tiene cuatro celdas")
            nombre = re.sub(r"<[^>]+>", "", celdas[0]).strip().lower()
            dicho = re.search(r'<span class="quien">([^<]+)</span>', celdas[3])
            fuera[nombre] = (self._num(celdas[1]), self._num(celdas[2]),
                             dicho.group(1) if dicho else None)
        return fuera

    def test_la_celda_de_diferencia_dice_de_que_lado_cae(self):
        """El `abs()` publicaba «53.188» sin decir de quién. La celda nombra
        ahora la columna que va por delante, y tiene que ser la mayor."""
        for nombre, (rud, med, dicho) in self.tabla().items():
            with self.subTest(indicador=nombre):
                if rud is None or med is None or rud == med:
                    self.assertIsNone(dicho, f"{nombre}: la celda nombra un "
                                             "lado sin dos cifras que comparar")
                    continue
                self.assertEqual(dicho, "RUD" if rud > med else "medios",
                                 f"{nombre}: la celda dice que va por delante "
                                 f"«{dicho}» con {rud} en el RUD y {med} en "
                                 "los medios")

    def test_la_celda_publica_la_distancia_completa(self):
        """Quitar el `abs()` no puede quitar la magnitud: sigue estando la
        resta, con su signo delante."""
        for nombre, (rud, med, dicho) in self.tabla().items():
            if rud is None or med is None or rud == med:
                continue
            celda = [re.findall(r"<td[^>]*>(.*?)</td>", f, re.S)[3]
                     for f in self.filas
                     if re.sub(r"<[^>]+>", "", re.findall(
                         r"<td[^>]*>(.*?)</td>", f, re.S)[0]).strip().lower()
                     == nombre][0]
            with self.subTest(indicador=nombre):
                self.assertIn(f"+{R.fmt(abs(rud - med))}", celda)

    def test_la_nota_reparte_los_mismos_indicadores_que_la_tabla(self):
        """El guardián de verdad: lo que la nota dice que va por delante en
        cada lado tiene que ser EXACTAMENTE lo que dice la tabla. Ni uno de
        más —afirmar un adelanto que la tabla no sostiene— ni uno de menos."""
        de_la_tabla = {"rud": set(), "medios": set()}
        for nombre, (rud, med, _) in self.tabla().items():
            if rud is None or med is None or rud == med:
                continue
            de_la_tabla["rud" if rud > med else "medios"].add(nombre)
        de_la_nota = {lado: set(re.split(r", | y ", lista))
                      for lado, lista in re.findall(
                          r'<span data-adelanto="([^"]+)">([^<]+)</span>',
                          self.nota)}
        for lado in ("rud", "medios"):
            with self.subTest(lado=lado):
                self.assertEqual(de_la_nota.get(lado, set()),
                                 de_la_tabla[lado],
                                 f"la nota y la tabla no reparten igual los "
                                 f"indicadores que adelanta {lado}")

    def test_el_guardian_cae_si_la_nota_se_queda_con_el_reparto_de_ayer(self):
        """Con la forma REAL de la avería: la tabla se recalcula cada día y la
        nota conserva el reparto de la víspera. Se intercambian los dos lados
        de la nota y las dos listas dejan de casar."""
        cambiada = self.nota.replace('data-adelanto="rud"', "data-adelanto=\"X\"")
        cambiada = cambiada.replace('data-adelanto="medios"',
                                    'data-adelanto="rud"')
        cambiada = cambiada.replace('data-adelanto="X"',
                                    'data-adelanto="medios"')
        self.assertNotEqual(cambiada, self.nota, "la mutación no cambió nada")
        reparto = {lado: set(re.split(r", | y ", lista))
                   for lado, lista in re.findall(
                       r'<span data-adelanto="([^"]+)">([^<]+)</span>',
                       cambiada)}
        de_la_tabla = {"rud": set(), "medios": set()}
        for nombre, (rud, med, _) in self.tabla().items():
            if rud is None or med is None or rud == med:
                continue
            de_la_tabla["rud" if rud > med else "medios"].add(nombre)
        self.assertNotEqual(reparto, de_la_tabla,
                            "la nota mutada seguiría cuadrando con la tabla: "
                            "el guardián no cazaría el fallo que existe para "
                            "cazar")


class TestPiezasDeBalancesLleganEscritas(unittest.TestCase):
    """Los nueve contenedores de `balances.html` llegan llenos al artefacto.

    Se ejecuta el inyector de verdad sobre el HTML del repositorio, que es como
    se construye `dist/`: así cae también si alguien quita la marca, mete un
    salto de línea entre la apertura y el cierre, cambia la etiqueta del
    contenedor o desconecta el generador."""

    CLAVES = ("balances-sello", "balances-resumen", "balances-tarjetas",
              "balances-grafico", "balances-capturas", "balances-datos-ld",
              "comparativa-tarjetas", "comparativa-filas",
              "comparativa-nota")

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "site" / "balances.html", cls.tmp / "balances.html")
        cls.hechas = R.inyectar_prerenderizado(cls.tmp, R.contexto())
        cls.html = (cls.tmp / "balances.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cuerpo(self, clave: str) -> str:
        m = re.search(rf'<(tbody|ul|span|section|p)[^>]*\bdata-gen="{clave}"[^>]*>'
                      rf'(.*?)</\1>', self.html, re.S)
        self.assertTrue(m, f"«{clave}» ya no está en site/balances.html")
        return m.group(2)

    def test_los_nueve_contenedores_llegan_no_vacios(self):
        for clave in self.CLAVES:
            with self.subTest(clave=clave):
                self.assertIn(clave, self.hechas,
                              f"el inyector no reconoció «{clave}»")
                self.assertTrue(self.cuerpo(clave).strip(),
                                f"«{clave}» quedó vacío en el artefacto")

    def test_el_marcador_va_vacio_en_el_repositorio(self):
        """Todo contenedor marcado se versiona vacío, y con la apertura pegada
        al cierre: un salto de línea y la marca no casa."""
        fuente = (ROOT / "site" / "balances.html").read_text(encoding="utf-8")
        for clave in self.CLAVES:
            with self.subTest(clave=clave):
                self.assertRegex(
                    fuente,
                    rf'<(tbody|span|section|p)[^>]*\bdata-gen="{clave}"[^>]*></\1>')

    def test_el_grafico_es_un_svg_servido_con_su_descripcion(self):
        """Tres paneles con escala propia, cada uno con su `<desc>`: la prosa
        que narra la serie día a día solo existía en la memoria del navegador."""
        cuerpo = self.cuerpo("balances-grafico")
        self.assertEqual(cuerpo.count("<svg"), len(R.PANELES_BALANCE))
        self.assertEqual(cuerpo.count("<desc"), len(R.PANELES_BALANCE))
        self.assertIn("máximo informado", cuerpo)

    def test_el_grafico_deja_el_color_al_tema(self):
        """`ui.cssVar()` resolvía la variable a un color literal y lo congelaba
        dentro del SVG: el gráfico salía con los colores del tema que estuviera
        puesto al dibujarlo. Servido, emite la referencia y sigue al tema."""
        cuerpo = self.cuerpo("balances-grafico")
        self.assertIn("var(--", cuerpo)
        self.assertFalse(re.search(r'(?:fill|stroke)="#[0-9a-fA-F]{3,8}"', cuerpo),
                         "el gráfico congela un color literal en vez de la variable")

    def test_las_cifras_del_navegador_ya_no_las_escribe_el_navegador(self):
        """La prosa de las tarjetas, del gráfico y de la comparativa vive
        ahora en Python. Si volviera además a `balances.js`, el día que una de
        las dos cambiara la página diría dos cosas — y solo una se leería sin
        JavaScript."""
        js = (ROOT / "site" / "balances.js").read_text(encoding="utf-8")
        for literal in ("máximo informado", "metric-card", "<svg",
                        "comparativaFuentes", "No se borran"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, js,
                                 f"balances.js vuelve a redactar «{literal}»")

    def test_las_doce_capturas_elegidas_tienen_su_fila_donde_marcarse(self):
        """Una captura son su día Y su URL, nunca la URL sola.

        La marca «✓ usada en la serie» se ponía sobre un índice por URL, y el
        mismo artículo es la captura elegida de varios días: una cobertura en
        vivo se vuelve a capturar cada mañana y un balance de El Tiempo
        representó a tres días seguidos. Con doce elegidas y siete URL
        distintas, cinco filas se quedaban sin marca y la fila que perdía el
        sitio en el índice dejaba de atender a los filtros. El pie servido dice
        cuántas alimentan la serie: si la tabla puede marcar menos, la página
        se contradice a sí misma.

        Se mide sobre el feed real —no sobre una fixture— porque el caso lo
        produce el archivo, no una hipótesis. Y no se comprueba la marca (eso
        lo pone el navegador) sino la condición sin la cual no se puede poner:
        que cada captura elegida tenga una fila propia que la identifique."""
        ctx = R.contexto()
        datos = R.consolidado_balances(ctx)
        if datos is None:                              # R14: sin node, sin regla
            self.skipTest("node no disponible: la regla del consolidado no corre")
        cuerpo = self.cuerpo("balances")
        filas = re.findall(r'<tr data-fecha="([^"]*)" data-url="([^"]*)">', cuerpo)
        self.assertEqual(len(filas), cuerpo.count("<tr "),
                         "alguna fila dejó de escribir su día o su URL")
        self.assertEqual(len(set(filas)), len(filas),
                         "dos filas comparten día y URL: la captura no se "
                         "distingue de la otra")
        elegidas = [d["item"] for d in datos["porDia"] if d.get("item")]
        claves = {(i.get("search_date") or "",
                   R.e(i.get("publication_url") or i.get("url") or "#"))
                  for i in elegidas}
        self.assertEqual(len(claves), len(elegidas),
                         "dos días eligieron la misma captura: la clave no las "
                         "separa")
        self.assertLessEqual(claves, set(filas),
                             "una captura elegida no tiene fila donde marcarse")
        # y el navegador tiene que indexar por las dos mitades, no por una
        js = (ROOT / "site" / "balances.js").read_text(encoding="utf-8")
        indice = re.search(r"new Map\(Array\.from\(tbody\.rows\)(.*?)\);", js, re.S)
        self.assertTrue(indice, "el índice de filas cambió de forma")
        self.assertIn("dataset.fecha", indice.group(1),
                      "el índice vuelve a colapsar las capturas por URL")

    def test_el_pie_de_la_tabla_no_sirve_un_estado_del_navegador(self):
        """«Cargando…» servido a quien no ejecuta JavaScript es una página que
        nunca termina de cargar. El build escribe el hecho de archivo y el
        navegador solo lo sustituye cuando hay filtros puestos."""
        self.assertNotIn("Cargando…", self.html)
        self.assertIn("capturas archivadas", self.cuerpo("balances-capturas"))
        js = (ROOT / "site" / "balances.js").read_text(encoding="utf-8")
        self.assertIn("pieServido", js,
                      "el navegador ya no devuelve la frase que sirvió el build")


class TestBalancesSinNode(unittest.TestCase):
    """R14 · Sin la regla no se publica la cifra, y se dice.

    El consolidado (R16) vive SOLO en `site/ui.js`. Si `node` falta, cada pieza
    de la página tiene que publicar su aviso en vez de una cifra calculada con
    otra regla — que es lo que hacía `alerts.py` el día que dos superficies se
    contradijeron en público. El seam es el propio caché del contexto: poner
    `None` es exactamente lo que deja `consolidado_balances` cuando node falla."""

    ITEM = {"search_date": "2026-08-18", "title": "Balance de la UNGRD",
            "publication_url": "https://ejemplo.co/balance",
            "publisher": {"name": "El Tiempo"},
            "reported_data_source": [
                {"id": "UNGRD", "name": "Unidad Nacional para la Gestión del "
                                        "Riesgo de Desastres",
                 "url": "https://portal.gestiondelriesgo.gov.co/"}]}

    def setUp(self):
        self.ctx = {"_balances_ui": None, "monitor": {},
                    "oficiales": {"items": [dict(self.ITEM)],
                                  "generated_at": "2026-08-19T04:00:00Z"}}

    def test_ninguna_pieza_publica_una_cifra_consolidada(self):
        for generador in (R.resumen_balances, R.tarjetas_balances,
                          R.grafico_balances, R.tarjetas_comparativa,
                          R.filas_comparativa):
            with self.subTest(generador=generador.__name__):
                salida = generador(self.ctx)
                self.assertNotIn("máximo informado", salida)
                self.assertIn("regla", salida,
                              "la pieza se calla en vez de decir por qué")

    def test_el_recuento_de_archivo_si_se_publica(self):
        """No todo depende de la regla: cuántas capturas hay y de cuántos
        publicadores es aritmética de archivo, y esa no se calla."""
        self.assertIn("1 balances", R.resumen_balances(self.ctx))
        self.assertIn("1 capturas archivadas", R.capturas_balances(self.ctx))
        self.assertNotIn("alimentan la serie", R.capturas_balances(self.ctx))

    def test_el_dataset_sigue_existiendo_sin_sus_cifras(self):
        """El conjunto de datos existe aunque el consolidado no se haya podido
        calcular: lo que se calla son las cifras, no el dataset."""
        nodo = json.loads(re.search(
            r"<script[^>]*>(.+?)</script>", R.marcado_balances(self.ctx), re.S).group(1))
        self.assertNotIn("variableMeasured", nodo)
        self.assertIn("creativeWorkStatus", nodo)
        self.assertEqual(nodo["dateModified"], "2026-08-18")


class TestBalancesConSerieSintetica(unittest.TestCase):
    """Las decisiones editoriales de la página, sobre una serie inventada.

    Con el feed real no se puede provocar el caso que importa —un día sin
    ninguna cifra al principio de la serie, una cifra rechazada, una disputa—,
    y un guardián que solo mira el dato de hoy deja de mirar mañana. La serie
    entra por el caché del contexto, que es la misma puerta por la que entra la
    de `ui.js`: aquí no se reimplementa la regla, se le da su resultado."""

    # tres días: el primero SIN fallecidos (R3: no es un cero, es un hueco),
    # el segundo con la primera cifra y el tercero arrastrándola
    PORDIA = [
        {"fecha": "2026-08-10", "item": None, "disputa": None, "ignoradas": [],
         "consolidado": {"fallecidos": {"valor": None}}},
        {"fecha": "2026-08-11", "disputa": None,
         "item": {"title": "Balance de la UNGRD",
                  "publication_url": "https://ejemplo.co/b1",
                  "publisher": {"name": "El Tiempo"},
                  "reported_data_source": [
                      {"id": "UNGRD", "name": "UNGRD",
                       "url": "https://portal.gestiondelriesgo.gov.co/"}]},
         "ignoradas": [{"cifra": "fallecidos", "valor": 120,
                        "motivo": "por debajo de la vigente",
                        "medio": "Diario Tardío",
                        "url": "https://ejemplo.co/tarde"}],
         "consolidado": {
             "fallecidos": {"valor": 287, "fecha": "2026-08-11",
                            "medio": "El Tiempo", "url": "https://ejemplo.co/b1"},
             "familias_afectadas": {"valor": 11132, "fecha": "2026-08-11",
                                    "medio": "El Tiempo"}}},
        {"fecha": "2026-08-12", "item": None,
         "disputa": {"fallecidos": {"min": 287, "max": 340}}, "ignoradas": [],
         "consolidado": {
             "fallecidos": {"valor": 287, "fecha": "2026-08-11",
                            "medio": "El Tiempo"},
             "familias_afectadas": {"valor": 11132, "fecha": "2026-08-11",
                                    "medio": "El Tiempo"}}},
    ]

    def setUp(self):
        items = [{"search_date": d["fecha"], "title": "t",
                  "publisher": {"name": "El Tiempo"},
                  "publication_url": f"https://ejemplo.co/{d['fecha']}",
                  "reported_data_source": [
                      {"id": "UNGRD", "name": "UNGRD",
                       "url": "https://portal.gestiondelriesgo.gov.co/"},
                      {"id": "alcaldia", "name": "Alcaldía citada en el texto",
                       "url": None}]}
                 for d in self.PORDIA]
        self.ctx = {
            "monitor": {}, "oficiales": {"items": items},
            "_balances_ui": {"porDia": copy.deepcopy(self.PORDIA),
                             "comparativa": []}}

    # ---- R3 en el gráfico
    def test_el_dia_sin_dato_no_se_dibuja_como_cero(self):
        """La línea ARRANCA en el primer día con valor. Dibujar los días
        anteriores con `|| 0` convierte una ausencia en un cero medido — la
        misma lección que los globos del mapa sin cifras."""
        svg = R.grafico_balances(self.ctx)
        panel = svg.split("</svg>")[0]                    # fallecidos y desap.
        camino = re.search(r'<path d="M ([\d.]+) ', panel)
        self.assertTrue(camino, "el panel de fallecidos perdió su línea")
        # con 3 días el primer punto cae en x≈68; arrancar en el día sin dato
        # lo pondría ~275 unidades a la izquierda
        banda = (900 - 58 - 18) / 3
        self.assertGreater(float(camino.group(1)), 58 + banda,
                           "la línea arranca en un día sin dato")

    def test_la_descripcion_calla_el_dia_entero_que_no_tiene_cifras(self):
        """El primer día no tiene ninguna de las dos cifras del panel:
        se omite de la narración, no se cuenta como una serie de ceros."""
        desc = re.search(r"<desc[^>]*>(.*?)</desc>", R.grafico_balances(self.ctx),
                         re.S).group(1)
        self.assertNotIn("10 de agosto", desc)
        self.assertIn("11 de agosto de 2026: 287 fallecidos", desc)
        self.assertIn("cifras en disputa", desc)

    def test_el_eje_deja_el_asidero_para_agrandarse_en_movil(self):
        """Esto no puede quedarse en un comentario.

        Medido en el navegador: en un teléfono de 375 px el lienzo de 900 se
        dibuja sobre 285 —escala 0,317— y un rótulo de 10 queda en 3,17 px
        efectivos, ilegible. La hoja de estilos solo puede agrandarlo si puede
        esconder uno de cada dos («21-ago» mide 33,9 unidades y la banda de un
        día son 68,7, que se estrechan cada día que entra en la serie), y solo
        puede esconderlos si el generador los distingue. La regla de CSS aún no
        existe —vive en `styles.css`, superficie compartida—: lo que este
        guardián sostiene es el asidero, para que no se pierda mientras tanto."""
        panel = R.grafico_balances(self.ctx).split("</svg>")[0]
        dias = re.findall(r'class="(g-dia[^"]*)"', panel)
        self.assertEqual(len(dias), len(self.PORDIA),
                         "el eje dejó de rotular un día")
        self.assertEqual(dias.count("g-dia g-dia-alterna"), len(self.PORDIA) // 2,
                         "el eje ya no distingue una de cada dos fechas")

    # ---- R16 en la prosa servida
    def test_las_tarjetas_conservan_el_lenguaje_de_r16(self):
        cuerpo = R.tarjetas_balances(self.ctx)
        self.assertIn("máximo informado", cuerpo)
        self.assertNotIn("cifra actual", cuerpo)

    def test_lo_rechazado_se_ensena_con_su_motivo(self):
        """R16 · Lo que no entra en la serie no se borra: se enseña, con su
        motivo, su medio y su enlace. La distancia entre lo que publica cada
        medio es lo que este monitor mide."""
        cuerpo = R.tarjetas_balances({**self.ctx,
                                      "_balances_ui": {"porDia": self.PORDIA[:2],
                                                       "comparativa": []}})
        self.assertIn("por debajo de la vigente", cuerpo)
        self.assertIn("Diario Tardío", cuerpo)
        self.assertIn("https://ejemplo.co/tarde", cuerpo)

    def test_la_entradilla_fecha_la_cifra_que_publica(self):
        """Una cifra de una fuente viva sin su corte miente en 48 horas."""
        self.assertIn("Máximo informado hasta el 12 de agosto de 2026",
                      R.resumen_balances(self.ctx))

    # ---- R3 en el marcado
    def _nodo(self, ctx=None):
        crudo = R.marcado_balances(ctx or self.ctx)
        return json.loads(re.search(r"<script[^>]*>(.+?)</script>", crudo, re.S).group(1))

    def test_la_cifra_ausente_se_omite_del_marcado_jamas_vale_cero(self):
        """Fuera de la base de datos rige la R3 igual: heridos y desaparecidos no
        tienen valor en esta serie, así que no aparecen. Un cero ahí sería el
        monitor afirmando que no hubo ninguno."""
        medidas = {m["name"]: m for m in self._nodo()["variableMeasured"]}
        self.assertEqual(sorted(medidas), ["Fallecidos", "Familias afectadas"])
        for m in medidas.values():
            self.assertNotEqual(m["value"], 0)

    def test_cada_variable_lleva_su_valor_y_su_unidad(self):
        for m in self._nodo()["variableMeasured"]:
            with self.subTest(nombre=m["name"]):
                self.assertIsInstance(m["value"], (int, float))
                self.assertTrue(m["unitText"])
                self.assertIn("Máximo informado hasta el", m["description"])
        unidades = {m["name"]: m["unitText"] for m in self._nodo()["variableMeasured"]}
        self.assertEqual(unidades["Fallecidos"], "personas")
        self.assertEqual(unidades["Familias afectadas"], "familias")

    def test_el_marcado_se_fecha_con_el_dato_y_no_con_la_corrida(self):
        """`rud.json` ya enseñó la trampa: se genera el 22 con una serie que
        termina el 21, y la página anunciaba cifras del 21 fechadas el 22."""
        nodo = self._nodo({**self.ctx,
                           "oficiales": {**self.ctx["oficiales"],
                                         "generated_at": "2026-09-30T04:00:00Z"}})
        self.assertEqual(nodo["dateModified"], "2026-08-12")
        self.assertEqual(nodo["temporalCoverage"], "2026-08-10/2026-08-12")

    def test_r9_el_monitor_compila_y_las_oficiales_se_citan(self):
        """Los dos niveles de atribución. `creator`/`publisher` son el monitor
        —que compiló el artefacto—; la UNGRD va en `citation`. Decir que la
        UNGRD publica esta página, o que el monitor produjo la cifra oficial,
        serían las dos mentiras simétricas."""
        nodo = self._nodo()
        self.assertEqual(nodo["creator"], {"@id": R.ORGANIZACION})
        self.assertEqual(nodo["publisher"], {"@id": R.ORGANIZACION})
        citados = [c["name"] for c in nodo["citation"]]
        self.assertIn("UNGRD", citados)
        self.assertNotIn("UNGRD", json.dumps(
            [nodo["creator"], nodo["publisher"]], ensure_ascii=False))

    def test_la_fuente_citada_sin_url_se_cita_sin_url_no_con_una_inventada(self):
        """Omitir es lo que significa «no la sabemos»."""
        por_nombre = {c["name"]: c for c in self._nodo()["citation"]}
        self.assertNotIn("url", por_nombre["Alcaldía citada en el texto"])
        self.assertEqual(por_nombre["UNGRD"]["url"],
                         "https://portal.gestiondelriesgo.gov.co/")

    def test_ningun_dataset_dentro_de_otro_y_toda_url_absoluta(self):
        """Los guardianes G2 y G6 sobre el bloque que escribe el build: el
        `Dataset` anidado invalidó las 208 fichas y las `DataDownload` de la
        portada llevaban `contentUrl` relativo. Aquí no se repite ninguno."""
        html = R.marcado_balances(self.ctx)
        datasets = datasets_ld(html)
        self.assertEqual(len(datasets), 1, "hay más de un Dataset en la página")
        nodo = datasets[0]
        for campo in ("name", "description"):
            self.assertTrue(str(nodo.get(campo, "")).strip())
        for clave, valor in nodo.items():
            if clave == "@type":
                continue
            self.assertEqual(
                [n for n in nodos_ld(valor) if "Dataset" in tipos_ld(n)], [],
                f"un Dataset anidado dentro de otro en «{clave}»")
        for n in nodos_ld(bloques_ld(html)[0]):
            for campo in ("contentUrl", "url", "@id"):
                v = n.get(campo)
                if isinstance(v, str):
                    partes = urllib.parse.urlparse(v)
                    self.assertTrue(partes.scheme and partes.netloc,
                                    f"«{campo}» relativo → {v}")


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

    def test_el_suelo_de_prosa_caza_la_perdida_y_no_se_queja_de_lo_sano(self):
        """El guardián del guardián: `test_el_artefacto_real_pasa` no distingue
        «no hay pérdida» de «no hay guardián», así que aquí se le enseña una
        página mutilada y otra sana, y tiene que separarlas.

        Se comprueba además lo que costó una revisión entera: que el cromo se
        descuenta POR SU MARCA. `pie_estatico()` emite `<div id="site-footer">`,
        no `<footer>`, y el patrón equivocado colaba 193 palabras de pie en las
        cinco páginas — el colchón que este medidor existe para quitar.
        """
        pagina = "balances.html"
        suelo = self.seo.PROSA_MINIMA[pagina]
        cuerpo = "palabra " * (suelo + 50)
        cabeza = '<link rel="canonical" href="/x">'
        sana = self.tmp / "suelo-ok"
        sana.mkdir(exist_ok=True)
        (sana / pagina).write_text(cabeza + f"<p>{cuerpo}</p>", encoding="utf-8")
        fallos = self.seo.revisar(sana)["fallos"]
        self.assertFalse([f for f in fallos if "prosa propia" in f],
                         "se queja de una página que no ha perdido nada")

        rota = self.tmp / "suelo-roto"
        rota.mkdir(exist_ok=True)
        (rota / pagina).write_text(
            cabeza + f"<p>{'palabra ' * (suelo - 40)}</p>", encoding="utf-8")
        fallos = self.seo.revisar(rota)["fallos"]
        self.assertTrue([f for f in fallos if "prosa propia" in f],
                        "el suelo no cazó 40 palabras perdidas")

        # y el cromo compartido no cuenta como prosa de la página
        solo_cromo = ('<nav id="site-nav">' + "enlace " * 40 + "</nav>"
                      '<div id="site-footer"><div>' + "aviso " * 150
                      + "</div></div>")
        self.assertEqual(self.seo.prosa_propia(solo_cromo), 0,
                         "la barra o el pie se están contando como prosa propia")

    def test_caza_un_contenedor_vacio(self):
        """Es exactamente la regresión que motiva el verificador."""
        (self.tmp / "municipios.html").write_text(
            '<link rel="canonical" href="/x"><table>'
            '<tbody data-gen="municipios"></tbody></table>' + "palabra " * 900,
            encoding="utf-8")
        res = self.seo.revisar(self.tmp)
        self.assertTrue(any("quedó vacío" in f for f in res["fallos"]))

    def test_caza_un_parrafo_marcado_que_llega_vacio(self):
        """El contenedor no siempre es una tabla: la nota de la comparativa es
        un `<p data-gen>`. El verificador enumera etiquetas, así que una que no
        esté en su lista pasa de largo — y el guardián nuevo se quedaría sin
        guardián: quitar el `p` del patrón no rompería nada y la nota podría
        publicarse vacía."""
        (self.tmp / "balances.html").write_text(
            '<link rel="canonical" href="/x">'
            '<p data-gen="comparativa-nota"></p>' + "palabra " * 900,
            encoding="utf-8")
        res = self.seo.revisar(self.tmp)
        self.assertTrue(
            any("comparativa-nota" in f and "quedó vacío" in f
                for f in res["fallos"]),
            "un párrafo marcado que llega vacío no lo ve nadie")

    def test_caza_la_barra_y_el_pie_vacios(self):
        """La regresión que motivó la fase: `#site-nav` y `#site-footer` no
        llevan `data-gen`, así que el chequeo de contenedores marcados no los
        veía, y las cinco páginas se servían sin un solo enlace interno."""
        (self.tmp / "rud.html").write_text(
            '<link rel="canonical" href="/x">'
            '<nav id="site-nav" aria-label="Navegación del sitio"></nav>'
            '<div id="site-footer"></div>'
            "<table>" + "<tr><td>x</td></tr>" * 60 + "</table>" + "palabra " * 700,
            encoding="utf-8")
        fallos = self.seo.revisar(self.tmp)["fallos"]
        self.assertTrue(any("barra de navegación" in f and "vacía" in f for f in fallos),
                        f"la barra vacía pasó desapercibida: {fallos}")
        self.assertTrue(any("pie de página" in f and "vacío" in f for f in fallos),
                        f"el pie vacío pasó desapercibido: {fallos}")

    def test_caza_un_sitemap_que_promete_lo_que_no_existe(self):
        (self.tmp / "sitemap.xml").write_text(
            "<urlset><url><loc>https://datosdelterremoto.org/municipio/fantasma/</loc>"
            "</url></urlset>", encoding="utf-8")
        res = self.seo.revisar(self.tmp)
        self.assertTrue(any("y no existe" in f for f in res["fallos"]))

    def test_solo_admite_el_controlador_diferido_de_la_ficha(self):
        base = ('<svg class="mapa-estatico"></svg>'
                '<div data-evidencia="/data/public/municipios/cali/evidencia.json"></div>')
        permitido = (base + '<script src="/ui.js?v=abc"></script>'
                     '<script src="/municipio.js?v=abc"></script>')
        self.assertTrue(self.seo._scripts_ficha_validos(permitido))
        self.assertFalse(self.seo._scripts_ficha_validos(
            permitido + '<script src="/rellena-la-ficha.js"></script>'))
        self.assertFalse(self.seo._scripts_ficha_validos(
            '<script src="/ui.js?v=abc"></script><script src="/municipio.js?v=abc"></script>'))

    def test_el_artefacto_real_pasa(self):
        dist = Path(__file__).parent.parent / "dist"
        if not dist.exists():
            self.skipTest("no hay dist construido")
        res = self.seo.revisar(dist)
        self.assertEqual(res["fallos"], [], "el artefacto publicado tiene fallos de SEO")

    def test_el_guardian_del_departamento_duplicado_caza_el_fallo(self):
        """Que el artefacto real pase NO demuestra que el guardián vigile.

        `test_el_artefacto_real_pasa` seguiría en verde si el patrón no cazara
        nada: no distingue «no hay fallo» de «no hay guardián». Aquí se le pone
        delante el fallo tal como estuvo publicado y se comprueba que salta —y
        que no salta con el texto ya corregido.
        """
        malos = ["Terremoto en Riosucio (Caldas) (Caldas) 2026: damnificados y daños",
                 "Terremoto de Colombia 2026 en Riosucio (Caldas), Caldas",
                 "Argelia (Cauca) (Cauca): 1 familia inscrita en el RUD"]
        for texto in malos:
            self.assertIsNotNone(self.seo.DEPTO_DUPLICADO.search(texto),
                                 f"el guardián deja pasar «{texto}»")
        buenos = ["Terremoto en Riosucio (Caldas) 2026: damnificados y daños",
                  "Terremoto de Colombia 2026 en Riosucio, Caldas",
                  "Argelia (Cauca): 1 familia inscrita en el RUD",
                  # Un paréntesis que no es el departamento no puede saltar.
                  "Copernicus (EMSR916) miró Cali (Valle del Cauca) el 12 de agosto"]
        for texto in buenos:
            self.assertIsNone(self.seo.DEPTO_DUPLICADO.search(texto),
                              f"el guardián acusa en falso a «{texto}»")

    def test_el_guardian_recorre_las_208_aunque_otro_chequeo_corte(self):
        """Los dos `break` del bucle de fichas abortan el recorrido entero.
        Este chequeo vive en su propio bucle justamente por eso: colgado del
        otro, una ficha con un script raro escondía el resto."""
        fuente = (Path(__file__).parent.parent / "ingest/seo_check.py").read_text(encoding="utf-8")
        cuerpo = fuente.split("DEPTO_DUPLICADO.search")[0]
        ultimo_for = cuerpo.rfind("for ficha in fichas:")
        self.assertGreater(ultimo_for, cuerpo.rfind("break"),
                           "el chequeo del departamento duplicado volvió a colgar "
                           "de un bucle que corta con break")


_MIRADA = re.compile(r'<span data-mirada="([^"]+)">(.*?)</span>', re.S)


class TestResumenDeLaFicha(unittest.TestCase):
    """Las dos líneas bajo el H1: dos recuentos puestos al lado, nunca una
    división de uno entre otro.

    **A1 estuvo semanas publicado con la suite entera en verde.** El resumen
    dividía los edificios que clasifica un satélite entre las viviendas que
    declara el registro y llamaba porcentaje al resultado: Cali salía «115
    edificios distintos: el 1,7 % de las 6.775 viviendas que el municipio
    declara dañadas» —que se lee como «el satélite se dejó el 98 % del daño»,
    justo lo contrario del mejor hallazgo del proyecto, que en Buenaventura vio
    134 casas destruidas donde el registro declaraba 42— y Viterbo salía con el
    113,7 %, un porcentaje imposible. Nada lo impedía porque ninguna regla lo
    prohibía: esta es la regla.

    El otro fallo que vigila es de la misma familia y también nace de no
    distinguir dos cosas: la frase «ningún satélite ha clasificado un solo
    edificio» entraba también cuando NADIE había mirado —los 276 municipios de
    hoy—, y sonaba a que alguien miró y no encontró nada. Cada frase declara en
    `data-mirada` cuál de los tres casos es, y aquí se contrasta con
    `_mirado_por_satelite`, que es quien lo sabe.
    """

    MIRADAS = {"con-edificios", "mirado-sin-marcas", "sin-mirar"}

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.resumenes, cls.cifras = {}, {}
        for m in cls.ctx["municipios"]:
            nombre = m["municipio"]
            d = R.datos_ficha(nombre, cls.ctx)
            vistos = R.satelites_con_dato(d["muni"], d["satelite"])
            n_sat = ((d.get("cruce") or {}).get("unidades")
                     or sum(n for _, n in vistos))
            vivs = [n for n in (d["muni"].get("rud_viv_destruidas"),
                                d["muni"].get("rud_viv_averiadas"))
                    if n is not None]
            cls.resumenes[nombre] = R.resumen_ficha(d)
            cls.cifras[nombre] = (n_sat, sum(vivs) if vivs else None)

    def miradas(self, nombre: str) -> list:
        return _MIRADA.findall(self.resumenes[nombre])

    # ------------------------------------------------- el cociente prohibido
    def test_ninguna_ficha_publica_el_cociente_de_edificios_entre_viviendas(self):
        """No se busca la palabra «porcentaje»: se calcula el número que salía
        de dividir y se comprueba que NO está publicado. Así cae aunque vuelva
        con otra redacción, con otro símbolo o con otro número de decimales."""
        for nombre, (n_sat, viv) in self.cifras.items():
            if not (n_sat and viv):
                continue
            frase = " ".join(t for _, t in self.miradas(nombre))
            for dec in (0, 1, 2):
                cociente = R.fmt(n_sat / viv * 100, dec)
                # Los dos recuentos SÍ se publican: si el cociente coincide con
                # uno de ellos, el número que se ve es ese y no la división.
                if cociente in (R.fmt(n_sat), R.fmt(viv)):
                    continue
                # Con fronteras de cifra: «6» vive dentro de «76» y de «1.369»,
                # y sin ellas el guardián acusaba a Quibdó de publicar un
                # cociente que no publica. Un guardián con falsos positivos se
                # acaba silenciando, que es como muere un guardián.
                suelto = re.compile(rf"(?<![\d.,]){re.escape(cociente)}(?![\d.,])")
                with self.subTest(municipio=nombre, decimales=dec):
                    self.assertIsNone(
                        suelto.search(frase),
                        f"{nombre}: la ficha publica «{cociente}», que es "
                        f"{n_sat} edificios entre {viv} viviendas. No son la "
                        "misma unidad ni cubren el mismo terreno: su cociente "
                        "no es un porcentaje de nada")

    def test_la_frase_del_satelite_no_lleva_ningun_porcentaje(self):
        """La misma regla por su forma, no por su valor: en esa frase se
        comparan dos fuentes distintas y ahí no hay proporción que publicar.
        El cociente de arriba caza el número; este caza la operación."""
        for nombre in self.cifras:
            for clase, frase in self.miradas(nombre):
                with self.subTest(municipio=nombre, mirada=clase):
                    self.assertNotIn("%", frase,
                                     f"{nombre}: la frase que cruza satélite y "
                                     f"registro vuelve a publicar un porcentaje")

    def test_los_dos_recuentos_se_publican_enteros(self):
        """Quitar el cociente no es quitar el dato: los dos números siguen
        publicados, cada uno con su fuente, que es lo que el monitor hace con
        todo lo demás."""
        for nombre, (n_sat, viv) in self.cifras.items():
            if not (n_sat and viv):
                continue
            frase = " ".join(t for _, t in self.miradas(nombre))
            with self.subTest(municipio=nombre):
                self.assertIn(R.fmt(n_sat), frase)
                self.assertIn(R.fmt(viv), frase)

    # ------------------------------------------------ quién miró y quién no
    def test_toda_mirada_declarada_es_una_de_las_tres(self):
        for nombre in self.cifras:
            for clase, _ in self.miradas(nombre):
                with self.subTest(municipio=nombre):
                    self.assertIn(clase, self.MIRADAS)

    def test_la_mirada_declarada_es_la_que_dice_el_dato(self):
        """«Nadie ha mirado» solo se publica donde de verdad no miró nadie.

        `_mirado_por_satelite` es quien lo sabe —incluye la zona de Copernicus
        sin un punto dentro—, y el resumen tiene que decir lo mismo que él."""
        por_nombre = {m["municipio"]: m for m in self.ctx["municipios"]}
        for nombre in self.cifras:
            for clase, _ in self.miradas(nombre):
                miro_alguien = R._mirado_por_satelite(por_nombre[nombre])
                with self.subTest(municipio=nombre):
                    self.assertEqual(
                        clase == "sin-mirar", not miro_alguien,
                        f"{nombre}: el resumen declara «{clase}» y los "
                        f"servicios que miraron son "
                        f"{R._servicios_que_miraron(por_nombre[nombre]) or 'ninguno'}")

    def test_el_sitio_publica_de_verdad_alguna_de_las_dos_ramas(self):
        """La lección de los guardianes que no guardan: si ningún municipio
        entrara por estas ramas, todo lo de arriba estaría en verde sin mirar
        nada."""
        clases = {c for n in self.cifras for c, _ in self.miradas(n)}
        self.assertTrue(clases & {"sin-mirar", "mirado-sin-marcas"},
                        "ninguna ficha declara su mirada satelital")
        self.assertIn("con-edificios", clases)

    # ---------------------------------- la rama que el dato de hoy no ejerce
    def _sintetica(self, **muni) -> dict:
        base = {"municipio": "Prueba", "rud_familias": None,
                "rud_personas": None, "tasa_rud_pct": None, "mmi_usgs": None,
                "rud_viv_destruidas": 16, "rud_viv_averiadas": None}
        base.update(muni)
        return {"muni": base, "satelite": 0, "cruce": {}}

    def test_mirar_y_no_marcar_no_es_lo_mismo_que_no_mirar(self):
        """Los dos municipios se diferencian en UNA cosa —si alguien miró— y
        el resumen tiene que decirlo distinto. Con el código de antes las dos
        fichas publicaban la misma frase, la que acusa al satélite de no
        encontrar nada.

        Hoy ningún municipio real entra por «miraron y no marcaron», así que la
        rama se ejerce aquí: un guardián que espera a que el dato produzca el
        caso es un guardián que no vigila."""
        nadie = self._sintetica()
        miraron = self._sintetica(en_aoi_copernicus=True)
        self.assertFalse(R._mirado_por_satelite(nadie["muni"]))
        self.assertTrue(R._mirado_por_satelite(miraron["muni"]))
        clase_nadie = _MIRADA.findall(R.resumen_ficha(nadie))
        clase_miraron = _MIRADA.findall(R.resumen_ficha(miraron))
        self.assertEqual(clase_nadie[0][0], "sin-mirar")
        self.assertEqual(clase_miraron[0][0], "mirado-sin-marcas")
        self.assertNotEqual(clase_nadie[0][1], clase_miraron[0][1],
                            "el municipio que nadie miró y el que miraron sin "
                            "marcar nada publican la misma frase")

    def test_el_resumen_y_su_nota_hablan_de_la_misma_ausencia(self):
        """Las dos frases de la cabecera declaran la MISMA mirada.

        La nota preguntaba por `satelites_con_dato` —«¿hay edificios?»— y el
        resumen por `_mirado_por_satelite` —«¿miró alguien?»—, así que un
        municipio dentro de una zona de Copernicus sin un punto dentro leía
        arriba «los satélites que miraron no marcaron ningún edificio» y dos
        renglones más abajo «nadie lo ha evaluado desde el aire».

        Hoy ningún municipio real está en ese caso, así que sobre el dato del
        día el guardián estaría en verde sin comprobar nada: se ejerce con los
        dos municipios sintéticos, que es donde la avería existe."""
        for d in (self._sintetica(), self._sintetica(en_aoi_copernicus=True),
                  # el servicio que evalúa y marca CERO: la nota preguntaba
                  # «¿hay algún servicio con valor?» y se callaba justo aquí
                  self._sintetica(unosat_edificios=0)):
            resumen = _MIRADA.findall(R.resumen_ficha(d))
            nota = _MIRADA.findall(R.nota_ausencia_satelital(d))
            with self.subTest(mirado=R._mirado_por_satelite(d["muni"])):
                self.assertTrue(nota, "la nota no declara ninguna mirada")
                self.assertEqual(resumen[0][0], nota[0][0],
                                 "el resumen y la nota de la misma cabecera "
                                 "cuentan dos ausencias distintas")

    def test_la_nota_se_calla_donde_el_satelite_si_marco_edificios(self):
        """La advertencia de la ausencia solo donde hay ausencia: emitida en
        todas por igual, Pereira afirmaba la mirada satelital arriba y la
        negaba abajo."""
        con_datos = self._sintetica(unosat_edificios=7)
        self.assertEqual(R.nota_ausencia_satelital(con_datos), "")

    def test_un_servicio_que_evalua_y_marca_cero_no_deja_la_ficha_muda(self):
        """UNOSAT puede evaluar un municipio y marcar cero edificios: entra en
        `satelites_con_dato` con un cero, y con la condición vieja —«no hay
        ningún servicio con dato»— la ficha se quedaba sin decir nada del
        satélite. Callar no es la tercera opción."""
        d = self._sintetica(unosat_edificios=0)
        clases = _MIRADA.findall(R.resumen_ficha(d))
        self.assertTrue(clases, "la ficha no dice nada del satélite")
        self.assertEqual(clases[0][0], "mirado-sin-marcas")


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

    def test_las_dos_frases_de_la_cabecera_hablan_de_la_misma_mirada(self):
        """El resumen y la nota que tiene debajo no pueden contar dos ausencias
        distintas.

        La nota preguntaba por `satelites_con_dato` —«¿hay edificios?»— y el
        resumen por `_mirado_por_satelite` —«¿miró alguien?»—, que son las dos
        preguntas que este proyecto lleva confundiendo. Con ellas, un municipio
        dentro de una zona de Copernicus sin un punto dentro leía arriba «los
        satélites que miraron no marcaron ningún edificio» y dos renglones más
        abajo «nadie lo ha evaluado desde el aire».

        Las dos frases declaran su `data-mirada` y aquí se comprueba que sea la
        misma. No se leen las palabras: se comparan las marcas."""
        for m in self.ctx["municipios"]:
            nombre = m["municipio"]
            if not R.es_elegible(nombre, self.ctx):
                continue
            html = R.render_ficha(R.datos_ficha(nombre, self.ctx))
            cabecera = "".join(
                re.search(rf'<p class="{c}">(.*?)</p>', html, re.S).group(1)
                for c in ("resumen", "nota-leer"))
            marcas = set(re.findall(r'data-mirada="([^"]+)"', cabecera))
            with self.subTest(municipio=nombre):
                self.assertLessEqual(
                    len(marcas), 1,
                    f"{nombre}: la cabecera declara {sorted(marcas)} — el "
                    "resumen y la nota hablan de dos ausencias distintas")

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
        ld, = datasets_ld(html)               # el dataset, esté en el bloque que esté
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


class TestClaveYToponimo(unittest.TestCase):
    """La clave del diccionario no es el nombre que lee una persona.

    Los homónimos se desambiguan metiendo el departamento entre paréntesis
    —«Riosucio (Caldas)», «Riosucio (Chocó)»— porque un diccionario no admite
    dos veces la misma llave. Confundir esa llave con el topónimo publicó
    «Terremoto en Riosucio (Caldas) (Caldas) 2026» en cinco fichas.

    La misma lección ya estaba aprendida en `municipal_google_news_feeds()`,
    donde buscar la clave literal daba un feed en cero para siempre. La ficha
    no la había aprendido.
    """

    CLAVE = "Riosucio (Caldas)"

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.datos = R.datos_ficha(cls.CLAVE, cls.ctx)
        cls.html = R.render_ficha(cls.datos)

    def test_toponimo_recorta_solo_el_departamento_que_sobra(self):
        self.assertEqual(R.toponimo("Riosucio (Caldas)", "Caldas"), "Riosucio")
        self.assertEqual(R.toponimo("Riosucio (Chocó)", "Chocó"), "Riosucio")
        # Un municipio sin paréntesis sale intacto.
        self.assertEqual(R.toponimo("Nóvita", "Chocó"), "Nóvita")
        # Y un paréntesis que NO es el departamento no se toca: recortar por la
        # forma y no por el contenido mutilaría un nombre propio.
        self.assertEqual(R.toponimo("Argelia (Cauca)", "Valle del Cauca"),
                         "Argelia (Cauca)")

    @unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
    def test_el_toponimo_de_ui_js_es_espejo_del_de_python(self):
        """el recorte vive en DOS lenguajes y ya divergió una vez.

        El commit que lo arregló solo tocó Python, así que las 208 fichas
        dejaron de repetir el departamento y la intro de municipios —que la
        escribe el navegador— siguió publicando «Bolívar (Cauca) (Cauca)»
        durante días. Se comparan EJECUTANDO las dos, no leyendo el código:
        dos textos parecidos pueden hacer cosas distintas.
        """
        casos = [("Riosucio (Caldas)", "Caldas"), ("Riosucio (Chocó)", "Chocó"),
                 ("Bolívar (Cauca)", "Cauca"), ("Nóvita", "Chocó"),
                 # el recorte es exacto: un paréntesis que no es EL departamento
                 # se queda, y las diferencias de mayúsculas o tildes no cuentan
                 ("Argelia (Cauca)", "Valle del Cauca"),
                 ("Balboa (Cauca)", "cauca"), ("Bogotá, D.C.", "Bogotá, D.C."),
                 ("", "Caldas")]
        js = correr_ui("[" + ",".join(
            f"UI.toponimo({json.dumps(c, ensure_ascii=False)},"
            f" {json.dumps(d, ensure_ascii=False)})" for c, d in casos) + "]")
        self.assertEqual(js, [R.toponimo(c, d) for c, d in casos],
                         "el topónimo de site/ui.js y el de deploy/render_html.py "
                         "han dejado de decir lo mismo")

    def test_el_departamento_no_se_escribe_dos_veces_en_toda_la_ficha(self):
        """En la ficha ENTERA, no solo en los metadatos.

        La primera versión de este test miraba el título, el H1 y la
        `description`, y daba verde mientras el párrafo destacado —justo el que
        citan los buscadores— seguía diciendo «Riosucio (Caldas) (Caldas) tiene
        832 familias». Lo cazó el navegador, no el test. Ahora se mira todo el
        documento: el texto visible y el marcado.
        """
        dup = re.compile(r"\(([^()]{2,40})\)(?: \(\1\)|, \1\b)")
        sin_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", self.html, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", sin_scripts)
        for superficie, texto in (("texto visible", visible), ("marcado", self.html)):
            hallado = dup.search(texto)
            self.assertIsNone(hallado, f"{superficie}: «{hallado.group(0) if hallado else ''}»")

    def test_el_parrafo_destacado_nombra_el_municipio_una_vez(self):
        """Es el párrafo que citan los buscadores y los sistemas de IA."""
        parrafo = R.parrafo_respuesta(self.datos)
        self.assertIn("Riosucio", parrafo)
        self.assertNotIn("(Caldas) (Caldas)", parrafo)

    def test_el_mapa_estatico_rotula_con_el_toponimo(self):
        """El SVG rotula al municipio sobre su propio mapa: ahí «(Caldas)» no
        desambigua nada —el mapa ya enseña dónde está— y solo mete ruido de
        base de datos en una imagen. No era el fallo publicado, pero deja el
        rótulo en espejo con el H1."""
        svg = re.search(r"<svg.*?</svg>", self.html, re.S).group(0)
        rotulos = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
        self.assertIn("Riosucio", rotulos)
        self.assertNotIn("Riosucio (Caldas)", rotulos)

    def test_el_json_ld_nombra_el_municipio_una_sola_vez(self):
        ld, = datasets_ld(self.html)
        self.assertNotIn("(Caldas) (Caldas)", ld["name"])
        self.assertEqual(ld["spatialCoverage"]["name"], "Riosucio, Caldas, Colombia")

    def test_el_enlace_al_mapa_conserva_la_clave(self):
        """El topónimo desambiguado sirve para leer; para buscar, no.

        `app.js` indexa el mapa de la portada por la llave del diccionario
        (`munLayerById[pedido]`). Si este enlace viajara con «Riosucio» a
        secas, los dos Riosucios dejarían de distinguirse y el mapa se
        quedaría quieto sin decir por qué: un fallo mudo.
        """
        import urllib.parse
        enlaces = re.findall(r'href="/\?municipio=([^"#]*)', self.html)
        self.assertTrue(enlaces, "la ficha debe enlazar al mapa de la portada")
        for crudo in enlaces:
            self.assertEqual(urllib.parse.unquote(crudo), self.CLAVE)


class TestConcordanciaDeLaFicha(unittest.TestCase):
    """«1 familias inscritas» estuvo publicado en ocho fichas, y «1 viviendas
    averiadas» en otras siete —13 fichas distintas, porque dos fallaban en las
    dos—. La revisión destapó tres frases más con el mismo defecto."""

    def test_solo_el_uno_va_en_singular(self):
        self.assertEqual(R.concuerda(1, "familia", "familias"), "familia")
        self.assertEqual(R.concuerda(2, "familia", "familias"), "familias")
        self.assertEqual(R.concuerda(0, "familia", "familias"), "familias")

    def test_una_lista_se_dice_como_se_lee_en_voz_alta(self):
        """`enumera` publica «a, b y c». Los extremos —ninguno y uno— existen:
        la nota de la comparativa los produce el día que solo un indicador
        adelante, o ninguno."""
        self.assertEqual(R.enumera([]), "")
        self.assertEqual(R.enumera(["familias"]), "familias")
        self.assertEqual(R.enumera(["familias", "personas"]),
                         "familias y personas")
        self.assertEqual(R.enumera(["familias", "personas", "viviendas"]),
                         "familias, personas y viviendas")

    def test_una_ausencia_no_es_una_unidad(self):
        """R3: el «—» conserva el plural. «— familia inscrita» afirmaría un
        recuento que nadie ha publicado."""
        self.assertEqual(R.concuerda(None, "familia", "familias"), "familias")

    def test_la_description_concuerda_con_su_cifra(self):
        ctx = R.contexto()
        vistos = 0
        for nombre in ctx["idx"]:
            m = ctx["idx"][nombre]
            if m.get("rud_familias") != 1:
                continue
            html = R.render_ficha(R.datos_ficha(nombre, ctx))
            descr = re.search(r'<meta name="description" content="([^"]*)"',
                              html).group(1)
            self.assertIn("1 familia inscrita", descr, nombre)
            self.assertNotIn("1 familias inscritas", descr, nombre)
            vistos += 1
        self.assertGreater(vistos, 0, "no hay ningún municipio con una sola familia: "
                                      "el test dejó de comprobar lo que dice")

    def test_ninguna_frase_visible_publica_uno_con_plural(self):
        """Vigila lead, resumen, comparación de viviendas y SVG accesible."""
        ctx = R.contexto()
        vistos = 0
        patron = re.compile(r"(?<![-\d])1 (?:familias|personas|viviendas)\b")
        for nombre in ctx["idx"]:
            if not R.es_elegible(nombre, ctx):
                continue
            html = R.render_ficha(R.datos_ficha(nombre, ctx))
            texto = re.sub(r"<[^>]+>", "", html)
            encontrado = patron.search(texto)
            detalle = encontrado.group(0) if encontrado else ""
            self.assertIsNone(encontrado, f"{nombre}: {detalle}")
            if any(ctx["idx"][nombre].get(campo) == 1 for campo in
                   ("rud_familias", "rud_personas", "rud_viv_destruidas",
                    "rud_viv_averiadas")):
                vistos += 1
        self.assertGreater(vistos, 0, "el corpus ya no contiene ninguna cifra igual a uno: "
                                      "el test dejó de comprobar lo que dice")

    def test_el_porcentaje_diminuto_se_escapa_en_los_tres_puntos_de_la_ficha(self):
        ctx = R.contexto()
        vistos = 0
        for nombre, m in ctx["idx"].items():
            if not (0 < (m.get("tasa_rud_pct") or 0) < 0.05):
                continue
            html = R.render_ficha(R.datos_ficha(nombre, ctx))
            self.assertEqual(html.count("<0,1 %"), 0, nombre)
            self.assertEqual(html.count("&lt;0,1 %"), 3, nombre)
            vistos += 1
        self.assertGreater(vistos, 0, "no hay porcentajes diminutos en el corpus: "
                                      "el test dejó de comprobar lo que dice")


class TestIdentidadDelSitio(unittest.TestCase):
    """La marca doble, ya decidida (docs/DECISIONES.md, 22-ago-2026): «Datos del
    terremoto de Colombia 2026» es el nombre público; «Monitor de brechas» se
    queda en la barra y en la metodología."""

    NOMBRE_PUBLICO = "Datos del terremoto de Colombia 2026"

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.render_ficha(R.datos_ficha("Nóvita", cls.ctx))
        cls.common = (ROOT / "site/common.js").read_text(encoding="utf-8")

    def test_og_site_name_en_todas_las_paginas_grandes_y_en_la_ficha(self):
        esperado = f'<meta property="og:site_name" content="{self.NOMBRE_PUBLICO}">'
        self.assertIn(esperado, self.html, "la ficha no declara og:site_name")
        # De `PAGINAS_GRANDES`, no de una lista suelta: son seis desde la fase
        # 6b y la séptima tiene que entrar aquí sola. `ESTATICAS` de
        # `TestMarcadoEstructurado` sigue escrita a mano a propósito — es el
        # cierre bidireccional, y derivarla la volvería tautológica.
        for pagina in sorted(R.PAGINAS_GRANDES):
            texto = (ROOT / "site" / pagina).read_text(encoding="utf-8")
            self.assertIn(esperado, texto, f"{pagina} no declara og:site_name")

    def test_el_pie_abre_con_el_nombre_publico(self):
        """El pie ya vive una sola vez —`pie_estatico()`, para las 213 páginas—,
        y abre por el nombre público: es por donde se busca esto."""
        apertura = f"<strong>{self.NOMBRE_PUBLICO}</strong>"
        self.assertIn(apertura, R.pie_estatico())

    def test_la_descripcion_del_pie_sigue_completa(self):
        pie = re.sub(r"\s+", " ", R.pie_estatico())
        self.assertIn("Damnificados, viviendas destruidas y daños", pie)
        self.assertIn(R.TESIS, pie)
        self.assertIn("quedó archivado.", pie)

    def test_la_barra_se_presenta_por_el_nombre_publico(self):
        """Decisión del 23-ago-2026: la barra dice «Datos del terremoto».

        Sustituye a `test_la_barra_conserva_el_nombre_interno`, que fijaba
        «Monitor de brechas» ahí. No es que aquel guardián estuviera mal: es que
        vigilaba una decisión que se ha cambiado, y una decisión cambiada se
        cambia también en su test. «Monitor de brechas» sigue siendo el nombre
        interno del proyecto en la documentación y en las migas de las fichas.

        Mira el rótulo de la marca, no el fichero entero: la primera versión de
        este test buscaba el nombre en el texto crudo de common.js y pasaba en
        verde con la barra ya rota, porque esas palabras estaban en el
        comentario que hay justo encima. Un guardián que se contenta con su
        propia documentación no guarda nada.
        """
        marca = r'class="brand"[^>]*>\s*<strong>([^<]+)</strong>'
        hallado = re.search(marca, R.nav_estatico())
        self.assertIsNotNone(hallado, "nav_estatico: no se encuentra el rótulo")
        self.assertEqual(hallado.group(1).strip(), "Datos del terremoto")
        self.assertEqual(hallado.group(1).strip(), R.MARCA,
                         "el rótulo y la constante MARCA se han separado")


def _sin_marcas(texto: str) -> str:
    """El texto como lo lee una persona: sin etiquetas, sin asteriscos de
    Markdown y con los espacios colapsados.

    Las seis copias de la tesis viven en soportes distintos —Markdown, HTML con
    un `<strong>` en medio, una cadena de Python dentro de un JSON-LD— y ninguna
    de esas envolturas es la frase. Comparar los soportes en crudo sería atar
    la redacción al formato."""
    return " ".join(re.sub(r"<[^>]+>", " ", texto).replace("**", "").split())


class TestTesisDelMonitor(unittest.TestCase):
    """La frase que dice de qué va esto, escrita una vez y repetida seis.

    Hasta el 25-ago-2026 decía «la distancia entre sus cifras es la brecha de
    reporte» y estaba escrita SEIS veces a mano, sin nada que las atara: el
    contrato del repositorio, el pie de las 353 páginas, el `Dataset` de
    municipios.html y las bajadas de la portada, de balances y de la
    referencia. Seis redacciones que podían separarse una a una sin que el
    build se enterara — que es exactamente el fallo de la copia divergente que este proyecto ya ha
    pagado con los topónimos y con los liveblogs.

    Ahora la frase vive en `R.TESIS` (y su versión larga, la de la portada, en
    `R.TESIS_LARGA`) y este guardián comprueba que las seis superficies la
    dicen **con las mismas palabras**. No comprueba QUÉ dice: eso es una
    decisión editorial y cambiarla es cambiar la constante. Comprueba que
    cambiarla en un sitio no deje a los otros cinco diciendo lo de ayer.

    La tesis vieja se retira además de las seis: se cambió porque solo era
    cierta en UNA de las cuatro comparaciones del monitor —el RUD contra los
    balances de prensa, que sí se hacen la misma pregunta—, y donde no lo era
    invitaba a restar edificios menos familias.
    """

    # La AFIRMACIÓN vieja, no el término: «brecha de reporte» sigue siendo el
    # nombre del proyecto y una palabra clave del marcado, y prohibirlo sería
    # prohibir cómo se llama esto. Lo que se retira es la tesis: que la
    # distancia ENTRE dos cifras SEA la brecha.
    VIEJA = "es la brecha de reporte"

    @classmethod
    def setUpClass(cls):
        ctx = R.contexto()
        cls.superficies = {
            "CLAUDE.md": (ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
            "el pie de las 353 páginas": R.pie_estatico(),
            "el Dataset de municipios.html": R.dataset_municipios(ctx),
            "site/balances.html":
                (ROOT / "site" / "balances.html").read_text(encoding="utf-8"),
            "site/referencia.html":
                (ROOT / "site" / "referencia.html").read_text(encoding="utf-8"),
        }
        cls.portada = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

    def test_las_cinco_superficies_cortas_dicen_la_misma_frase(self):
        for donde, texto in self.superficies.items():
            with self.subTest(superficie=donde):
                # `assertTrue` y no `assertIn`: el fallo volcaba la página
                # entera y el mensaje se perdía al final de 20.000 caracteres.
                self.assertTrue(R.TESIS in _sin_marcas(texto),
                                f"{donde} no dice la tesis, o la dice con "
                                f"otras palabras que las demás: «{R.TESIS}»")

    def test_la_portada_lleva_la_version_larga_y_entera(self):
        """La portada es la única que la desarrolla: nombra qué cuenta cada
        fuente y qué hace el monitor con ellas. Es otra frase, no otra tesis, y
        por eso tiene su propia constante y su propio guardián."""
        self.assertTrue(R.TESIS_LARGA in _sin_marcas(self.portada),
                        "la portada no dice la versión larga de la tesis, o la "
                        f"dice con otras palabras: «{R.TESIS_LARGA}»")

    def test_la_version_larga_empieza_por_la_corta(self):
        """El desarrollo no puede decir algo distinto del titular: la larga
        abre por la misma oración —con dos puntos en vez de punto, porque
        continúa— y de ahí en adelante explica."""
        cabeza = R.TESIS.split(".")[0]
        self.assertTrue(R.TESIS_LARGA.startswith(cabeza + ":"),
                        "la versión larga ya no abre por la tesis corta")

    def test_la_tesis_vieja_no_sobrevive_en_ninguna_superficie(self):
        """Se cambió una frase, no se añadió otra. Una superficie que conserve
        la vieja publica las dos tesis a la vez, que es peor que publicar la
        equivocada."""
        for donde, texto in {**self.superficies,
                             "site/index.html": self.portada}.items():
            with self.subTest(superficie=donde):
                self.assertFalse(self.VIEJA in _sin_marcas(texto),
                                 f"{donde} conserva «{self.VIEJA}»")

    def test_el_guardian_cae_si_una_sola_copia_se_desvia(self):
        """La comprobación de que muerde, con la forma REAL de la avería: se
        reescribe UNA de las seis —como haría quien mejora la frase donde la
        está leyendo— y las otras cinco se quedan como estaban."""
        for donde, texto in self.superficies.items():
            desviada = _sin_marcas(texto).replace(
                R.TESIS, "Cada fuente cuenta una parte y el monitor las junta.", 1)
            with self.subTest(superficie=donde):
                self.assertFalse(R.TESIS in desviada,
                                 f"la mutación de {donde} no cambió nada: el "
                                 f"guardián no estaría mirando esa superficie")


class TestContextoDelSismo(unittest.TestCase):
    """De qué terremoto habla el sitio: una vez por cabecera, y siempre igual.

    Vivía en la segunda línea de la barra, es decir en las 213 páginas y dentro
    de un elemento pegado que roba 13,75 px de pantalla en cada scroll de un
    móvil. Bajó al encabezado de cada página, junto al sello de fecha: el hecho
    y la fecha del dato se leen de un tirón.

    Es texto fijo escrito cinco veces —no se genera: `data-gen` es el mecanismo
    de lo que caduca con la corrida—, así que necesita un guardián que impida
    que las cinco copias se separen y que la frase se diga dos veces en la
    misma cabecera, que es lo que pasaba en la portada mientras el subtítulo
    también la llevaba.

    Las 208 fichas también la reciben, en `.fecha` bajo el H1: el prototipo
    lo midió así (24-ago). Sigue siendo `CONTEXTO_SISMO`, no una tercera
    copia. El H1 nombra el municipio; esta línea nombra el sismo."""

    PAGINAS = tuple(sorted(R.PAGINAS_GRANDES))

    @classmethod
    def setUpClass(cls):
        cls.cabeceras = {}
        for pagina in cls.PAGINAS:
            texto = (ROOT / "site" / pagina).read_text(encoding="utf-8")
            m = re.search(r"<header[^>]*>(.*?)</header>", texto, re.S)
            assert m, f"{pagina}: no se encuentra el encabezado"
            cls.cabeceras[pagina] = m.group(1)

    def test_las_cinco_cabeceras_dicen_de_que_sismo_hablan(self):
        esperado = f'<span class="contexto-sismo">{R.CONTEXTO_SISMO}</span>'
        for pagina, cabecera in self.cabeceras.items():
            self.assertIn(esperado, cabecera,
                          f"{pagina}: el encabezado no dice de qué sismo habla, "
                          f"o lo dice con otras palabras que las otras cuatro")

    def test_el_contexto_va_junto_al_sello_y_no_en_el_subtitulo(self):
        """Su sitio es `.meta`, donde está la fecha del dato. En el subtítulo
        volvería a mezclarse con lo que cada página tiene de propio."""
        for pagina, cabecera in self.cabeceras.items():
            meta = re.search(r'<div class="meta">(.*?)</div>', cabecera, re.S)
            self.assertIsNotNone(meta, f"{pagina}: no hay contenedor .meta")
            self.assertIn("contexto-sismo", meta.group(1),
                          f"{pagina}: el contexto del sismo se ha salido de .meta")

    def test_ninguna_cabecera_lo_dice_dos_veces(self):
        """La portada lo decía en el subtítulo Y en el sello: la misma frase a
        un centímetro de sí misma. Al mudarla hay que retirarla de donde estaba,
        y este test es el que se entera si vuelve."""
        for pagina, cabecera in self.cabeceras.items():
            self.assertEqual(cabecera.count("10 de agosto de 2026"), 1,
                             f"{pagina}: la fecha del sismo aparece "
                             f"{cabecera.count('10 de agosto de 2026')} veces "
                             f"en el mismo encabezado")

    def test_la_barra_ya_no_carga_con_el_dato_del_sismo(self):
        """La barra es navegación; el sismo es contexto de la página."""
        nav = R.nav_estatico()
        self.assertNotIn("10-ago-2026", nav)
        self.assertNotIn("M7.4", nav)
        marca = re.search(r'class="brand"[^>]*>(.*?)</a>', nav, re.S)
        self.assertIsNotNone(marca)
        self.assertNotIn("<span", marca.group(1),
                         "la marca ha recuperado su segunda línea")


class TestInventarioDelPie(unittest.TestCase):
    """El pie es la superficie que lleva las licencias y los datos abiertos.

    Desde que vive una sola vez —`pie_estatico()`— viaja a las 213 páginas, y
    eso vale en las dos direcciones: borrar un enlace de ahí no rompe nada, no
    deja rastro y se lleva un canal de datos **de golpe en todo el sitio**. Un
    archivo público que pierde en silencio su RSS o su CSV deja de ser
    consultable, y nadie se entera hasta que alguien lo busca.

    El inventario se fija **por destino, no por texto**: el rótulo es editorial
    y se puede reescribir cuando convenga; la URL es la promesa. Cuando falla,
    dice cuál falta."""

    # Cada línea es un compromiso público: una sección del sitio, un export
    # abierto, un canal de avisos o una atribución. Tocar esta lista es la
    # conversación que el test quiere provocar — nunca el trámite para que
    # vuelva a pasar en verde.
    DESTINOS = (
        f"{R.BASE}/index.html",
        f"{R.BASE}/municipios.html",
        f"{R.BASE}/rud.html",
        f"{R.BASE}/balances.html",
        f"{R.BASE}/noticias.html",
        f"{R.BASE}/referencia.html",
        # Fase 6b: apuntaban a `index.html#…`, dentro de un plegable de la
        # portada. La metodología y el glosario tienen página propia; los dos
        # `id` siguen en la portada para que los 220 enlaces ya publicados no
        # caigan en el vacío, pero el pie manda a donde el texto vive entero.
        f"{R.BASE}/referencia.html#glosario",
        f"{R.BASE}/referencia.html#metodologia",
        f"{R.DATOS}/crosscheck.csv",
        f"{R.DATOS}/monitor.json",
        f"{R.DATOS}/rud.json",
        f"{R.DATOS}/divipola_coords.json",
        f"{R.OFICIALES_BASE}/oficiales.rss",
        f"{R.DATOS}/alerts.rss",
        R.TELEGRAM_CANAL,
        R.REPO,
        "https://col.social/@jp",
        "https://orkidea.eu",
        "https://www.buymeacoffee.com/orkidea",
    )

    @classmethod
    def setUpClass(cls):
        cls.hrefs = re.findall(r'href="([^"]+)"', R.pie_estatico())

    def test_el_pie_no_pierde_ningun_enlace(self):
        faltan = [d for d in self.DESTINOS if d not in self.hrefs]
        self.assertEqual(faltan, [],
                         "el pie perdió enlaces que publica en las 213 páginas: "
                         + ", ".join(faltan))

    def test_el_pie_no_gana_enlaces_sin_pasar_por_aqui(self):
        """Al revés también importa: el pie no es un tablón de anuncios."""
        sobran = sorted({h for h in self.hrefs if h not in self.DESTINOS})
        self.assertEqual(sobran, [],
                         "enlaces nuevos en el pie; si son deliberados, "
                         "añádelos a DESTINOS: " + ", ".join(sobran))

    def test_el_inventario_llega_al_artefacto(self):
        """Fijar el generador no basta: lo que se publica es `dist/`, y el pie
        viaja por dos caminos distintos —`escribir_piezas_compartidas` en las cinco
        páginas grandes, `render_ficha` en las 208 fichas—."""
        dist = ROOT / "dist"
        if not dist.exists():
            self.skipTest("no hay dist construido")
        paginas = [dist / "index.html"]
        fichas = sorted(dist.glob("municipio/*/index.html"))
        self.assertTrue(fichas, "dist/ no trae fichas municipales")
        paginas.append(fichas[0])
        for pagina in paginas:
            html = pagina.read_text(encoding="utf-8")
            pie = html[html.index('<div id="site-footer"'):]
            faltan = [d for d in self.DESTINOS if f'href="{d}"' not in pie]
            self.assertEqual(faltan, [],
                             f"{pagina.relative_to(dist)}: el pie publicado no "
                             f"lleva " + ", ".join(faltan))


class TestBarraYPieUnaSolaVez(unittest.TestCase):
    """La barra y el pie los escribe el build en las 213 páginas.

    Antes vivían dos veces —`nav_estatico()`/`pie_estatico()` para las 208
    fichas y `site/common.js` para las cinco páginas grandes— y había un test de
    espejo vigilando que no divergieran. Ese espejo se quedó sin objeto el
    23-ago-2026: ahora hay una sola superficie, y lo que hace falta vigilar es
    (a) que el JavaScript no vuelva a escribirlas y (b) que lleguen escritas al
    artefacto, que es lo que lee quien no ejecuta JavaScript.
    """

    PAGINAS = tuple(sorted(R.PAGINAS_GRANDES))

    @classmethod
    def setUpClass(cls):
        cls.common = (ROOT / "site/common.js").read_text(encoding="utf-8")
        # El artefacto de mentira: los HTML de `site/` tal cual se versionan,
        # con sus contenedores vacíos, y el paso real del build encima. No
        # depende de que haya un `dist/` construido, así que vigila siempre.
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        for pagina in cls.PAGINAS:
            shutil.copy(ROOT / "site" / pagina, cls.tmp / pagina)
        cls.escritas = R.escribir_piezas_compartidas(cls.tmp)
        cls.html = {p: (cls.tmp / p).read_text(encoding="utf-8") for p in cls.PAGINAS}

    # Un contenedor vacío es literalmente `<nav …></nav>`: no hace falta
    # emparejar etiquetas anidadas para verlo, y el pie lleva tres <div> dentro.
    VACIOS = (("barra", re.compile(r'<nav id="site-nav"[^>]*>\s*</nav>'), "nav-links"),
              ("pie", re.compile(r'<div id="site-footer"[^>]*>\s*</div>'), "sf-cols"))

    def _barra(self, html):
        hallado = re.search(r'<nav id="site-nav".*?>(.*?)</nav>', html, re.S)
        self.assertIsNotNone(hallado, "no está la barra")
        return hallado.group(1)

    def test_las_cinco_paginas_traen_la_barra_y_el_pie_escritos(self):
        """La regresión que motiva todo esto: llegaban vacíos al HTML servido."""
        self.assertEqual(sorted(self.escritas), sorted(self.PAGINAS))
        for pagina in self.PAGINAS:
            html = self.html[pagina]
            for etiqueta, vacio, dentro in self.VACIOS:
                self.assertIsNone(vacio.search(html),
                                  f"{pagina}: la {etiqueta} llegó vacía")
                self.assertIn(dentro, html,
                              f"{pagina}: la {etiqueta} no trae su contenido")

    def test_cada_pagina_marca_su_propio_enlace_como_activo(self):
        """Una barra escrita en el build con la misma página activa en las cinco
        sería peor que no tenerla: diría al lector que está donde no está."""
        for pagina in self.PAGINAS:
            barra = self._barra(self.html[pagina])
            activos = re.findall(r'<a href="([^"]+)"[^>]*class="activa"', barra)
            self.assertEqual(activos, [f"/{pagina}"],
                             f"{pagina}: enlace activo {activos}")

    def test_los_botones_de_javascript_solo_en_las_cinco_paginas(self):
        """`common.js` los busca por `getElementById` y **hace `return` en
        silencio** si no están: sin ellos la portada perdería el botón de
        compartir y el de alertas sin que nada avise. Y al revés, una ficha con
        el botón puesto ofrecería un clic muerto: ahí no hay quien lo escuche."""
        for pagina in self.PAGINAS:
            for boton in ("btn-alertas", "btn-compartir"):
                self.assertIn(f'id="{boton}"', self.html[pagina],
                              f"{pagina}: falta el botón «{boton}» que common.js busca")
        ficha = R.nav_estatico("municipios.html")
        self.assertNotIn("btn-alertas", ficha, "la ficha ganó un botón sin quien lo escuche")
        self.assertNotIn("btn-compartir", ficha)
        # Y el valor por defecto es el de la ficha: quien llame sin pensar no
        # puede colar los botones en las 208 páginas que nunca los tuvieron.
        self.assertEqual(R.nav_estatico("municipios.html"),
                         R.nav_estatico("municipios.html", botones_js=False))

    def test_el_boton_de_alertas_sale_oculto_y_lo_desoculta_el_navegador(self):
        """El 🔔 nace `hidden` y solo lo enseña `common.js` cuando comprueba que
        el navegador soporta notificaciones.

        Sin ese `hidden`, el botón se ve en un navegador sin soporte, donde
        `common.js` ya hizo `return` y no hay nadie escuchando: **un clic
        muerto**, la misma avería que el test de los botones evita en las 208
        fichas. Y sin el `btn.hidden = false` de `common.js`, el botón no
        aparece nunca: cada mitad sin la otra es un fallo distinto, así que se
        fijan juntas."""
        def atributos(etiqueta):
            """Los valores entrecomillados fuera: `hidden` cuenta si es un
            atributo, no si alguien lo escribe dentro de un `title`."""
            return re.sub(r'"[^"]*"', '""', etiqueta)

        marca = re.compile(r'<button id="btn-alertas"[^>]*>')
        superficies = {"nav_estatico()": R.nav_estatico("index.html", botones_js=True)}
        superficies.update({p: self.html[p] for p in self.PAGINAS})
        for donde, texto in superficies.items():
            etiqueta = marca.search(texto)
            self.assertIsNotNone(etiqueta, f"{donde}: no está el botón de alertas")
            self.assertRegex(atributos(etiqueta.group(0)), r"\bhidden\b",
                             f"{donde}: el botón de alertas sale visible en "
                             f"navegadores sin push — un clic muerto")
        codigo = re.sub(r"/\*.*?\*/", " ", self.common, flags=re.S)
        codigo = re.sub(r"//[^\n]*", " ", codigo)
        self.assertRegex(codigo, r"btn\.hidden\s*=\s*false",
                         "nadie desoculta el botón: saldría oculto siempre")

    def test_common_js_ya_no_escribe_la_barra_ni_el_pie(self):
        """La duplicación que se acaba de fundir no puede volver por la puerta
        de atrás. Mira el código, no los comentarios: se le quitan antes de
        buscar, porque el fichero explica en prosa lo que ya no hace —y un
        guardián que se conforma con su propia documentación no guarda nada.

        Lo prohibido son **los nombres**, no la manera de llegar a ellos: la
        primera versión de este test vetaba `getElementById("site-nav")` y
        dejaba pasar `querySelector("#site-nav")`, que además sería peor que el
        bug original —el JavaScript pisaría en el navegador una barra que el
        HTML ya trae bien, y `seo_check` no lo vería, porque lee el HTML
        servido y no el DOM ejecutado—. Vetar `.innerHTML =` en bloque tampoco
        vale: el menú de compartir lo construye así con todo el derecho, y el
        guardián empezaría a dar falsos positivos por trabajo legítimo. Si
        `common.js` no tiene por qué nombrar la barra ni el pie, que no los
        nombre — con `getElementById`, con `querySelector`, con
        `insertAdjacentHTML` o con lo que se invente."""
        codigo = re.sub(r"/\*.*?\*/", " ", self.common, flags=re.S)
        codigo = re.sub(r"//[^\n]*", " ", codigo)
        for prohibido in ("site-nav", "site-footer", "sf-cols", "nav-links"):
            self.assertNotIn(prohibido, codigo,
                             f"common.js vuelve a escribir la barra o el pie: «{prohibido}»")

    def test_common_js_conserva_lo_que_solo_puede_hacer_el_navegador(self):
        """Borrar de más es la otra mitad del riesgo: compartir, alertas y la
        apertura del <details> de un ancla siguen siendo cosa del navegador."""
        for pieza in ('getElementById("btn-alertas")',
                      'getElementById("btn-compartir")',
                      "menu-compartir", "navigator.share",
                      "pushManager", "closest(\"details\")"):
            self.assertIn(pieza, self.common, f"common.js perdió «{pieza}»")

    def test_el_paso_avisa_si_alguien_borra_el_marcador(self):
        """No escribir la barra y seguir adelante publicaría la página muda."""
        mudo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, mudo, ignore_errors=True)
        (mudo / "index.html").write_text("<html><body>sin marcadores</body></html>",
                                         encoding="utf-8")
        with self.assertRaises(LookupError) as roto:
            R.escribir_piezas_compartidas(mudo)
        self.assertIn("marcador", str(roto.exception))
        self.assertNotIn("ya estaba escrita", str(roto.exception))

    def test_repetir_el_paso_dice_que_ya_estaba_escrita_y_no_culpa_al_marcador(self):
        """Correr el paso dos veces sobre el mismo `dist/` no encuentra el
        marcador —se lo gastó la primera pasada— y acusaba a `site/*.html` de
        haberlo perdido: mandaba a depurar el sitio equivocado.

        `build_dist.sh` hace `rm -rf dist` antes, así que el camino sancionado
        está a salvo; quien refresca el artefacto a mano es quien se lo
        encuentra, y a ese hay que decirle qué pasó y qué hacer."""
        repetido = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repetido, ignore_errors=True)
        for pagina in self.PAGINAS:
            shutil.copy(ROOT / "site" / pagina, repetido / pagina)
        self.assertEqual(sorted(R.escribir_piezas_compartidas(repetido)),
                         sorted(self.PAGINAS), "la primera pasada ya falló")
        with self.assertRaises(LookupError) as repetida:
            R.escribir_piezas_compartidas(repetido)
        aviso = str(repetida.exception)
        self.assertIn("ya estaba escrita", aviso)
        self.assertNotIn("marcador", aviso, "sigue mandando a mirar site/*.html")
        self.assertIn("build_dist.sh", aviso, "no dice cómo salir del atolladero")

    def test_el_artefacto_real_trae_la_barra_y_el_pie(self):
        dist = ROOT / "dist"
        if not dist.exists():
            self.skipTest("no hay dist construido")
        for pagina in self.PAGINAS:
            html = (dist / pagina).read_text(encoding="utf-8")
            for etiqueta, vacio, dentro in self.VACIOS:
                self.assertIsNone(vacio.search(html),
                                  f"dist/{pagina}: la {etiqueta} llegó vacía")
                self.assertIn(dentro, html,
                              f"dist/{pagina}: la {etiqueta} no trae su contenido")


class TestSubtituloRetirado(unittest.TestCase):
    """El subtítulo repetía el H1 y colaba el código DIVIPOLA en la portada de
    la ficha. Se retira; el código y la fecha bajan a «Fuentes y trazabilidad»,
    que es donde los busca quien los necesita — y no se pierden, porque un
    archivo que no dice de cuándo es su cifra deja de ser un archivo."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.datos = R.datos_ficha("Nóvita", cls.ctx)
        cls.html = R.render_ficha(cls.datos)

    def test_el_subtitulo_no_vuelve(self):
        self.assertNotIn("Damnificados inscritos, daños y cobertura", self.html)

    def test_divipola_sigue_publicado_en_trazabilidad(self):
        divipola = self.ctx["idx"]["Nóvita"]["divipola"]
        self.assertIn(divipola, self.html, "el código DIVIPOLA se perdió por el camino")
        tabla = self.html.split("Fuentes y trazabilidad")[1]
        self.assertIn(divipola, tabla, "DIVIPOLA no está en «Fuentes y trazabilidad»")

    def test_la_ficha_dice_las_DOS_fechas_y_no_las_confunde(self):
        """Decía «datos del 22 de agosto» con la última captura del 21, y la
        tabla de capturas de la misma página lo desmentía tres filas más
        arriba. Ahora publica el corte del dato Y la corrida, como el resto del
        sitio: no son lo mismo y confundirlas miente."""
        tabla = self.html.split("Fuentes y trazabilidad")[1]
        corrida = self.datos["generado"]
        corte = self.datos["serie"][-1][0] if self.datos.get("serie") else None
        self.assertIn(f'datetime="{corrida}"', tabla,
                      "la ficha dejó de decir cuándo se construyó")
        if corte:
            self.assertIn(f'datetime="{corte}"', tabla,
                          "la ficha dejó de decir hasta cuándo llega el dato")
            self.assertNotIn(f"datos del {R.fecha_larga(corrida)}", tabla,
                             "vuelve a fechar el dato con la corrida")


class TestMarcadoEstructurado(unittest.TestCase):
    """Los guardianes del JSON-LD, sobre las 213 páginas construidas.

    No sobre una ficha de muestra: el bug que motiva esta clase —un `isPartOf`
    que embebía un segundo `Dataset` sin `description`— se publicó en las 208
    fichas a la vez, y el test que había miraba el nodo raíz de un solo
    documento. Aquí se construye el artefacto entero y se recorre cada bloque
    JSON-LD hasta el fondo, que es como lo lee Google.

    Se valida sobre el JSON parseado, nunca sobre el texto crudo: buscar
    `"contentUrl": "/` con expresiones regulares daría falsos positivos con
    cualquier URL externa legítima que lleve una barra.
    """

    URL_ABSOLUTA = ("contentUrl", "url", "logo", "@id")
    # Escritas aquí y no leídas de `R.PAGINAS_GRANDES`: si el guardián tomara
    # su expectativa de la misma lista que vigila, una página que desapareciera
    # del build desaparecería a la vez de la comprobación y el test seguiría en
    # verde sobre cuatro páginas.
    # A MANO, y no derivada de `PAGINAS_GRANDES`: es el cierre bidireccional.
    # Derivarla la volvería tautológica y una página que se cayera del build
    # se llevaría el guardián con ella. La sexta —`referencia.html`— entró en
    # la fase 6b con la mudanza de la metodología y el glosario.
    ESTATICAS = ("index.html", "municipios.html", "rud.html",
                 "balances.html", "noticias.html", "referencia.html")

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.res = R.run(cls.tmp)                       # las 208 fichas
        for pagina in cls.ESTATICAS:                   # y las cinco grandes
            shutil.copy(ROOT / "site" / pagina, cls.tmp / pagina)
        # Los DOS pasos del build, y este orden. Sin el inyector, el guardián
        # global recorría el marcado que se versiona pero NO el que se escribe
        # en el build: medido, veía 0 nodos `Dataset` en municipios.html donde
        # hay 1. Es decir, todo el marcado que ganaron las fases 4 y 5 nacía
        # fuera del guardián que dice vigilarlo, y el agujero crecía solo con
        # cada página que estrenara el suyo. Es la misma forma del bug que
        # motivó esta clase —un guardián que recorre menos de lo que promete—
        # con otro traje.
        R.inyectar_prerenderizado(cls.tmp, R.contexto())
        R.escribir_piezas_compartidas(cls.tmp)
        cls.paginas = sorted(cls.tmp.rglob("*.html"))

    def _nombre(self, pagina: Path) -> str:
        return str(pagina.relative_to(self.tmp))

    def test_la_cobertura_es_de_verdad_las_213(self):
        """Sin esto, los guardianes de abajo podrían estar recorriendo tres
        páginas y dando verde: «la lista no está vacía» es la misma trampa con
        otro traje. El número de fichas no se escribe a mano —crece con los
        datos—: se compara con el que declara el propio build."""
        fichas = [p for p in self.paginas if p.parent.parent.name == "municipio"]
        self.assertEqual(len(fichas), self.res["fichas"])
        self.assertGreater(len(fichas), 200, "el artefacto se ha encogido")
        self.assertEqual(sorted(R.PAGINAS_GRANDES), sorted(self.ESTATICAS),
                         "el build dejó de escribir alguna de las cinco grandes")
        self.assertEqual(len(self.paginas), len(fichas) + len(self.ESTATICAS))
        # Cada una de las 213 publica su `Dataset`, y exactamente uno. Exigir
        # solo «algún bloque JSON-LD» no guardaba nada: `BLOQUE_IDENTIDAD` lo
        # escribe `escribir_piezas_compartidas` en las 213, así que el test
        # pasaba en verde con el INYECTOR DESCONECTADO —cero datasets— y G2/G6,
        # que iteran sobre los datasets, pasaban también porque el bucle no
        # llegaba a correr. Es «la lista no está vacía» con otro traje, y la
        # primera versión de este arreglo cayó justo en ella: se comprobó que el
        # guardián VE el contenido cuando está, no que EXIJA que esté.
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            nombre = self._nombre(pagina)
            self.assertTrue(bloques_ld(html), f"{nombre}: sin ningún bloque JSON-LD")
            self.assertEqual(
                len(datasets_ld(html)), 1,
                f"{nombre}: {len(datasets_ld(html))} nodos Dataset, se esperaba 1 "
                "— ¿se desconectó el prerenderizado del marcado?")

    def test_g2_ningun_dataset_sin_nombre_ni_descripcion(self):
        """G2 · A cualquier profundidad y en cualquiera de las 213.

        Google valida recursivamente CUALQUIER nodo `"@type": "Dataset"`, esté
        anidado donde esté: uno embebido dentro de otro se valida como dataset
        independiente y se le exigen sus propios campos. La forma correcta es
        referenciar por `@id`, nunca meter un dataset dentro de otro — por eso
        este test no se conforma con que existan los campos: comprueba también
        que no haya un `Dataset` colgando de otro.
        """
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            for nodo in datasets_ld(html):
                for campo in ("name", "description"):
                    valor = nodo.get(campo)
                    self.assertIsInstance(
                        valor, str,
                        f"{self._nombre(pagina)}: un Dataset sin «{campo}» "
                        f"({nodo.get('@id') or nodo.get('name') or nodo})")
                    self.assertTrue(
                        valor.strip(),
                        f"{self._nombre(pagina)}: Dataset con «{campo}» vacío")
                for clave, valor in nodo.items():
                    if clave == "@type":
                        continue
                    anidados = [n for n in nodos_ld(valor)
                                if "Dataset" in tipos_ld(n)]
                    self.assertEqual(
                        anidados, [],
                        f"{self._nombre(pagina)}: un Dataset anidado dentro de "
                        f"otro en «{clave}» — referencia por @id, no lo embebas")

    def test_g6_toda_url_del_marcado_es_absoluta(self):
        """G6 · Una ruta relativa depende de conocer la URL base del documento:
        cierto para un navegador, falso para el indexador de datasets que
        extrae el bloque JSON-LD como JSON suelto — que es justo quien lo lee.
        """
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            for bloque in bloques_ld(html):
                for nodo in nodos_ld(bloque):
                    for campo in self.URL_ABSOLUTA:
                        valor = nodo.get(campo)
                        # una lista de URLs vale; un objeto anidado (un `logo`
                        # que sea ImageObject) lo alcanza la propia recursión
                        crudas = [valor] if isinstance(valor, str) else [
                            v for v in (valor or []) if isinstance(v, str)]
                        for cruda in crudas:
                            partes = urllib.parse.urlparse(cruda)
                            self.assertTrue(
                                partes.scheme and partes.netloc,
                                f"{self._nombre(pagina)}: «{campo}» relativo "
                                f"→ {cruda}")

    def test_la_identidad_llega_identica_a_las_213(self):
        """`@id` NO resuelve entre documentos: cada URL se procesa aislada, así
        que lo que hace que las 213 hablen de la misma entidad no es la
        sintaxis, es que el valor sea el mismo. Se compara la cadena entera,
        no «contiene un #organization»."""
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            self.assertEqual(
                html.count(R.BLOQUE_IDENTIDAD), 1,
                f"{self._nombre(pagina)}: el nodo de identidad no llega igual")

    def test_la_identidad_declara_las_dos_entidades_que_se_referencian(self):
        """Un `@id` que no se define en la misma página es un cascarón vacío
        para quien lee solo esa página. Todo `@id` referenciado desde cualquier
        bloque tiene que estar definido en ese mismo documento."""
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            definidos, referenciados = set(), set()
            for bloque in bloques_ld(html):
                for nodo in nodos_ld(bloque):
                    ident = nodo.get("@id")
                    if not isinstance(ident, str):
                        continue
                    (referenciados if set(nodo) == {"@id"} else definidos).add(ident)
            self.assertLessEqual(
                referenciados, definidos,
                f"{self._nombre(pagina)}: referencia a "
                f"{sorted(referenciados - definidos)} sin definirla aquí")
            self.assertIn(R.ORGANIZACION, definidos)
            self.assertIn(R.SITIO, definidos)

    def test_el_catalogo_del_sitio_cumple_las_reglas_de_dataset(self):
        """El nodo `#site` se declara `DataCatalog`, y Google lo valida con las
        reglas de `Dataset`: le exige `description` —sin ella lo descarta de los
        resultados enriquecidos—, `license` y `creator`. Los tres faltaban, en
        las 353 páginas a la vez, y así lo enseñaba Search Console en la ficha
        de Dagua sin que el fallo tuviera nada que ver con Dagua.

        Sobre el artefacto construido, no sobre la plantilla: es el HTML que
        lee el rastreador. Y no vale «la clave está»: una `description` puesta
        a cadena vacía es exactamente lo que Google rechaza, así que se le
        exige contenido de verdad y que el `creator` apunte a una entidad
        definida en ese mismo documento."""
        vistos = 0
        for pagina in self.paginas:
            html = pagina.read_text(encoding="utf-8")
            nombre = self._nombre(pagina)
            catalogos = [n for bloque in bloques_ld(html) for n in nodos_ld(bloque)
                         if "DataCatalog" in tipos_ld(n)]
            self.assertEqual(len(catalogos), 1,
                             f"{nombre}: {len(catalogos)} nodos DataCatalog, se "
                             "esperaba 1")
            nodo = catalogos[0]
            vistos += 1
            for campo, minimo in (("name", 1), ("description", 60)):
                valor = nodo.get(campo)
                self.assertIsInstance(valor, str, f"{nombre}: catálogo sin «{campo}»")
                # el mínimo no es capricho: la trampa de este repositorio es el
                # test que se conforma con que la clave exista, y una
                # `description` a cadena vacía —o de tres palabras— es
                # exactamente lo que Google rechaza
                self.assertGreaterEqual(
                    len(valor.strip()), minimo,
                    f"{nombre}: «{campo}» del catálogo no dice nada → {valor!r}")
            self.assertEqual(nodo.get("license"), R.LICENCIA,
                             f"{nombre}: el catálogo no publica su licencia")
            for campo in ("creator", "publisher"):
                self.assertEqual(nodo.get(campo), {"@id": R.ORGANIZACION},
                                 f"{nombre}: «{campo}» del catálogo no referencia "
                                 "a la organización que ya define esta página")
        self.assertEqual(vistos, len(self.paginas), "el guardián no recorrió las 353")

    def test_la_licencia_del_sitio_se_escribe_una_sola_vez(self):
        """Seis nodos publican la misma licencia. Escrita seis veces, la que
        nadie mira es la que se queda atrás; y una licencia equivocada en el
        marcado autoriza usos que el proyecto no autoriza."""
        fuente = (ROOT / "deploy" / "render_html.py").read_text(encoding="utf-8")
        self.assertEqual(
            fuente.count('"https://creativecommons.org/licenses/by/4.0/"'), 1,
            "la URL de la licencia volvió a escribirse a mano: usa R.LICENCIA")
        for pagina in self.paginas:
            for bloque in bloques_ld(pagina.read_text(encoding="utf-8")):
                for nodo in nodos_ld(bloque):
                    licencia = nodo.get("license")
                    if licencia is not None:
                        self.assertEqual(licencia, R.LICENCIA,
                                         f"{self._nombre(pagina)}: licencia distinta "
                                         f"en {nodo.get('@id') or nodo.get('name')}")


class TestNoticiasReordenada(unittest.TestCase):
    """La página de titulares: el dato arriba y la explicación plegada (fase 4).

    Sigue el patrón que `rud.html` estrenó el 23-ago: entradilla servida bajo el
    encabezado, la introducción en un plegable antes de la lista y las preguntas
    frecuentes en otro después. Es un movimiento, no una reescritura, y los
    recuentos exactos de palabras son lo único que lo distingue: sin ellos,
    resumir un párrafo «para que quepa» deja la suite en verde y se lleva por
    delante prosa que ya estaba publicada."""

    # el reparto: la introducción entera (140) arriba, la FAQ (462) al final
    PALABRAS = {"Qué es este corpus": 140,
                "Cómo funciona y preguntas frecuentes": 462}
    UMBRAL = 120        # nada se pliega por debajo (criterio del proyecto, 23-ago)

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site" / "noticias.html").read_text(encoding="utf-8")
        cls.bloques = re.findall(
            r'<details class="pliegue[^"]*">(.*?)</details>', cls.html, re.S)

    @staticmethod
    def _palabras(fragmento):
        return len(re.sub(r"<[^>]+>", " ", fragmento).split())

    def test_son_dos_y_ninguno_vive_dentro_del_otro(self):
        self.assertEqual(len(self.bloques), 2)
        for b in self.bloques:
            self.assertNotIn("<details", b, "ningún plegable dentro de otro")

    def test_cada_plegable_conserva_sus_palabras_y_supera_el_umbral(self):
        visto = {}
        for b in self.bloques:
            titulo = re.search(r"<summary>(.*?)</summary>", b, re.S).group(1).strip()
            cuerpo = re.search(
                r'<(?:section class="intro"|ol)>(.*?)</(?:section|ol)>', b, re.S)
            self.assertIsNotNone(cuerpo, f"«{titulo}» perdió su cuerpo")
            visto[titulo] = self._palabras(cuerpo.group(1))
        self.assertEqual(visto, self.PALABRAS,
                         "alguien reescribió, resumió o perdió prosa de los "
                         "plegables: era un movimiento, no una redacción")
        for titulo, n in visto.items():
            self.assertGreaterEqual(n, self.UMBRAL,
                                    f"«{titulo}» tiene {n} palabras: nada se "
                                    f"pliega por debajo de {self.UMBRAL}")

    def test_el_orden_es_el_argumento(self):
        """Entradilla → qué es el corpus → los datos → las preguntas. El dato
        deja de tardar dos pantallas en aparecer."""
        i_entradilla = self.html.index('data-gen="noticias-resumen"')
        i_corpus = self.html.index("Qué es este corpus")
        i_zona = self.html.index('<div class="zona-datos">')
        i_faq = self.html.index("Cómo funciona y preguntas frecuentes")
        self.assertLess(i_entradilla, i_corpus)
        self.assertLess(i_corpus, i_zona)
        self.assertLess(i_zona, i_faq, "la FAQ quedó por encima de la lista")

    def test_los_hallazgos_de_la_introduccion_siguen_publicados(self):
        """Las frases más citables no pueden perderse en la mudanza."""
        self.assertIn("Istmina solo existe en", self.html)
        self.assertIn("849 titulares de otros sismos", self.html)
        faq = next(b for b in self.bloques if "preguntas frecuentes" in b)
        self.assertEqual(faq.count("<li><strong>¿"), 6,
                         "la FAQ dejó de tener sus seis preguntas")

    def test_nadie_lee_cargando_nunca_mas(self):
        """Era la única de las cinco que publicaba «Cargando…» a quien no
        ejecuta JavaScript. El recuento vivo lo escribe el navegador en
        `#resumen`, que ahora viaja vacío; lo que un lector sin JavaScript
        necesita saber de la lista lo sirve el pie `noticias-nota`."""
        self.assertNotIn("Cargando", self.html)
        self.assertIn('<p id="resumen"></p>', self.html)
        self.assertIn('<span data-gen="noticias-nota"></span>', self.html)


class TestSelloDeNoticias(unittest.TestCase):
    """El sello de titulares: la fecha del último titular no es la corrida.

    `noticias.json` se empaqueta con `generado` y una lista de ítems cuyo
    máximo de `fecha` es hasta dónde llega de verdad el corpus. La página
    escribía la corrida desde el navegador («actualizado el …» con
    `data.generado`), que es la confusión que el sello existe para deshacer."""

    def test_dice_las_dos_fechas_y_toma_el_maximo_no_el_ultimo(self):
        sello = R.sello_noticias({
            "noticias": [{"fecha": "2026-08-21T09:09:12"},
                         {"fecha": "2026-08-19T02:11:33"}],
            "noticias_generado": "2026-08-22"})
        self.assertEqual(re.findall(r'<time datetime="([^"]+)"', sello),
                         ["2026-08-21", "2026-08-22"])
        self.assertIn("hasta el", sello)
        self.assertIn("corrida del", sello)
        self.assertNotIn("09:09", sello, "la hora se cuela en la prosa")

    def test_sin_corrida_o_sin_titulares_no_se_inventa_nada(self):
        """Donde falta una fecha se calla ese trozo."""
        solo_dato = R.sello_noticias({
            "noticias": [{"fecha": "2026-08-21"}], "noticias_generado": None})
        self.assertNotIn("corrida", solo_dato)
        solo_corrida = R.sello_noticias({
            "noticias": [], "noticias_generado": "2026-08-22"})
        self.assertNotIn("hasta", solo_corrida)
        vacio = R.sello_noticias({"noticias": [], "noticias_generado": None})
        self.assertIn("Sin ninguna captura de los titulares", vacio)

    def test_el_sello_la_entradilla_y_el_pie_llegan_al_artefacto(self):
        """El inyector de verdad sobre el HTML del repositorio: cae también si
        alguien quita la marca o desconecta un generador."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy(ROOT / "site" / "noticias.html", tmp / "noticias.html")
        hechas = R.inyectar_prerenderizado(tmp, R.contexto())
        for clave in ("noticias-sello", "noticias-resumen", "noticias-nota"):
            self.assertIn(clave, hechas, f"el inyector no reconoció «{clave}»")
        html = (tmp / "noticias.html").read_text(encoding="utf-8")
        sello = re.search(r'<span id="generado"[^>]*>(.*?)</span>', html, re.S)
        self.assertTrue(sello and sello.group(1).strip())
        self.assertEqual(len(re.findall(r"<time ", sello.group(1))), 2,
                         "el sello dejó de decir las dos fechas")

    def test_noticias_js_ya_no_fecha_el_dato(self):
        """No se le pone un `if` a la fecha del navegador: se le quita el
        motivo. La redacción vive en un solo sitio, que es Python."""
        js = (ROOT / "site" / "noticias.js").read_text(encoding="utf-8")
        self.assertNotIn("fechaLarga", js,
                         "noticias.js vuelve a fechar el dato por su cuenta")
        self.assertNotIn("data.generado", js,
                         "noticias.js vuelve a leer la corrida")
        self.assertNotIn("Cargando", js)


class TestEntradillaDeNoticias(unittest.TestCase):
    """La frase servida bajo el titular, con sus cifras del build."""

    def test_la_pluralidad_se_cuenta_por_dominio_no_por_nombre(self):
        """docs/DECISIONES.md (19-ago-2026): `infobae` e `Infobae` son la misma
        cabecera; el dominio es la clave estable. Y el nombre de un feed sin
        dominio no es un medio (R3)."""
        items = [{"medio": "Infobae", "medio_dominio": "infobae.com"},
                 {"medio": "infobae", "medio_dominio": "infobae.com"},
                 {"medio": "EL PAÍS", "medio_dominio": "elpais.com"},
                 {"medio": "Google News (agregador es-CO)"}]
        self.assertEqual(R.medios_distintos(items), 2)
        entradilla = R.entradilla_noticias(
            {"noticias": items, "noticias_desde": "2026-08-10"})
        self.assertIn("<b>2 medios</b>", entradilla)
        self.assertIn("<b>4 titulares</b>", entradilla)

    def test_los_numeros_van_en_es_co(self):
        items = [{"medio_dominio": f"medio-{i}.com"} for i in range(1200)]
        entradilla = R.entradilla_noticias({"noticias": items})
        self.assertIn("<b>1.200 titulares</b>", entradilla)
        self.assertIn("<b>1.200 medios</b>", entradilla)

    def test_m10_lo_que_falta_se_calla(self):
        sin_dominios = R.entradilla_noticias(
            {"noticias": [{"medio": "un feed sin dominio"}]})
        self.assertNotIn("medios</b>", sin_dominios)
        self.assertNotIn("desde el", sin_dominios)
        vacia = R.entradilla_noticias({"noticias": []})
        self.assertTrue(vacia.strip(), "una cadena vacía rompería el build")
        self.assertNotIn("<b>", vacia, "sin corpus no hay cifra que resaltar")

    def test_r9_la_entradilla_separa_prensa_de_balance(self):
        entradilla = R.entradilla_noticias(
            {"noticias": [{"medio_dominio": "a.com"}]})
        self.assertIn("mide atención, no daño", entradilla)
        self.assertIn('href="balances.html"', entradilla)

    def test_la_fecha_de_arranque_sale_del_dato(self):
        entradilla = R.entradilla_noticias(
            {"noticias": [{"medio_dominio": "a.com"}],
             "noticias_desde": "2026-08-10"})
        self.assertIn("desde el 10 de agosto de 2026", entradilla)


class TestPieDeNoticias(unittest.TestCase):
    """El pie servido de la lista: el recorte se declara, con sus dos cifras."""

    def test_declara_el_recorte_cuando_lo_hay(self):
        nota = R.nota_noticias({"noticias": [{}] * (R.TITULARES_EN_HTML + 100)})
        self.assertIn(R.fmt(R.TITULARES_EN_HTML), nota)
        self.assertIn(R.fmt(R.TITULARES_EN_HTML + 100), nota)
        self.assertIn("más recientes", nota)

    def test_un_corpus_chico_no_presume_de_recorte(self):
        nota = R.nota_noticias({"noticias": [{}] * 5})
        self.assertNotIn("más recientes de los", nota)
        self.assertIn("5", nota)

    def test_sin_corpus_lo_dice_y_jamas_devuelve_vacio(self):
        nota = R.nota_noticias({"noticias": []})
        self.assertTrue(nota.strip())
        self.assertNotIn("0 titulares", nota, "un cero no es una lista vacía")


# =====================================================================
# municipios.html: lo que el navegador escribía y ahora escribe el build
# =====================================================================
def _ctx_municipios(items, generado="2026-08-22", satelite=None, ciudadanos=None):
    """Un contexto mínimo con lo único que leen los generadores de la página.

    No se llama a `R.contexto()`: un fixture escrito a mano es lo que permite
    fabricar el caso que NO está en los datos de hoy —cero satélites, cero
    homónimos, cero municipios— que es justo donde vive la regresión."""
    return {"municipios": items,
            "municipios_generado": generado,
            "conteo_satelite": satelite or {},
            "conteo_ciudadanos": ciudadanos or {},
            "cruce_satelital": {},
            "noticias": [], "idx": {m["municipio"]: m for m in items}}


def _municipio(nombre="Nóvita", **cambios):
    base = {"municipio": nombre, "departamento": "Chocó", "estado": "solo_rud",
            "poblacion_2026": 8000, "rud_personas": 100, "rud_familias": 30,
            "tasa_rud_pct": 1.25, "dyfi_max_cdi": None, "dyfi_respuestas": None,
            "n_noticias": 0, "en_aoi_copernicus": False, "unosat_edificios": None,
            "sertit_edificios": None, "homonimo_de_departamento": False,
            "fuentes": ["RUD"]}
    return {**base, **cambios}


class TestChipsDeMunicipios(unittest.TestCase):
    """El recuento del chip y la etiqueta de la fila salen del mismo predicado.

    Es la avería que `CHIPS_RUD` ya había tenido en la otra página: la
    condición vivía partida entre `site/municipios.js` —que contaba las filas
    ya escritas— y `filas_municipios` —que las etiquetaba—, así que el día que
    una de las dos cambiara el chip diría «Sin mirar por satélite (197)» y
    filtraría otra cosa, sin que nada avisara.
    """

    # El quinto caso es el que hace de verdad el trabajo: un municipio DENTRO
    # de una zona de Copernicus y sin un solo edificio clasificado dentro. Está
    # mirado y sigue sin dato, así que el chip —que promete «nadie ha evaluado
    # sus edificios»— tiene que contarlo. Sin él, cambiar el predicado del chip
    # por `_mirado_por_satelite` dejaba la suite entera en verde: la primera
    # versión de este fixture no lo tenía y la mutación sobrevivió.
    ITEMS = [
        _municipio("Con satélite", en_aoi_copernicus=True),
        _municipio("Sin satélite"),
        _municipio("Sin registro", rud_personas=None, rud_familias=None),
        _municipio("Con comunidad"),
        _municipio("Zona sin puntos", en_aoi_copernicus=True),
    ]

    @classmethod
    def setUpClass(cls):
        cls.ctx = _ctx_municipios(cls.ITEMS, satelite={"Con satélite": 12},
                                  ciudadanos={"Con comunidad": 3})
        cls.html = R.chips_municipios(cls.ctx)
        cls.filas = R.filas_municipios(cls.ctx)

    def _recuento(self):
        return {clave: int(n.replace(".", "")) for clave, n in
                re.findall(r'data-chip="([^"]+)"[^>]*>[^<]*\((\d[\d.]*)\)', self.html)}

    def test_el_numero_del_chip_es_el_de_las_filas_que_filtra(self):
        """Se cuenta sobre las filas REALMENTE escritas, no sobre otra pasada
        del mismo predicado: si el chip y la fila se separan, aquí se ve."""
        etiquetas = re.findall(r'data-chips="([^"]*)"', self.filas)
        self.assertEqual(len(etiquetas), len(self.ITEMS), "faltan filas")
        recuento = self._recuento()
        self.assertEqual(recuento["todos"], len(self.ITEMS))
        for clave, _, _ in R.CHIPS_MUNICIPIOS:
            if clave == "todos":
                continue
            con_la_etiqueta = sum(1 for e in etiquetas if clave in e.split())
            self.assertEqual(
                recuento[clave], con_la_etiqueta,
                f"el chip «{clave}» dice {recuento[clave]} y las filas "
                f"etiquetadas son {con_la_etiqueta}")

    def test_los_chips_cuentan_lo_que_prometen(self):
        """El fixture está escrito para que cada chip tenga una respuesta
        distinta: si el predicado se cambiara por otro, el recuento cambia."""
        self.assertEqual(self._recuento(),
                         {"todos": 5, "sin-satelite": 4, "con-rud": 4,
                          "sin-rud": 1, "con-ciudadanos": 1})

    def test_estar_en_una_zona_mirada_sin_puntos_dentro_sigue_siendo_sin_dato(self):
        """Las dos preguntas sobre el satélite no son la misma, y el chip usa
        la suya: promete «ningún producto ha evaluado sus edificios», que es
        `satelites_con_dato`, no «nadie miró», que es `_mirado_por_satelite`.
        Un municipio en zona Copernicus sin un edificio clasificado dentro está
        mirado y sin dato, y el chip lo cuenta."""
        zona = [m for m in self.ITEMS if m["municipio"] == "Zona sin puntos"][0]
        self.assertTrue(R._mirado_por_satelite(zona))
        self.assertEqual(R.satelites_con_dato(zona, 0), [])
        self.assertIn("sin-satelite", R._chips_de_municipio(zona, self.ctx))

    def test_el_chip_activo_llega_con_las_dos_mecanicas(self):
        """`.activa` estiliza y `aria-pressed` lo anuncia el lector de
        pantalla; styles.css las funde en un solo selector. Se comprueba sobre
        la tira de ESTA página, no sobre el fichero entero: un guardián que
        busca el literal en todo `render_html.py` sobrevive si el defecto queda
        en una de las dos tiras."""
        activos = re.findall(r'<button class="chip activa"[^>]*aria-pressed="true"',
                             self.html)
        self.assertEqual(len(activos), 1,
                         f"la tira de municipios no marca exactamente un chip "
                         f"activo con las dos mecánicas: {self.html[:300]}")
        self.assertIn('data-chip="todos" aria-pressed="true"', self.html)
        self.assertEqual(self.html.count('aria-pressed="false"'),
                         len(R.CHIPS_MUNICIPIOS) - 1,
                         "los chips inactivos no declaran su estado")

    def test_el_javascript_no_vuelve_a_definir_los_chips(self):
        """La lista vive en Python y solo ahí: el navegador lee `data-chip` y
        `data-chips` de lo que el build ya escribió."""
        js = (ROOT / "site/municipios.js").read_text(encoding="utf-8")
        for etiqueta in ("Sin mirar por satélite", "Con damnificados inscritos",
                         "Sin registro aún", "Con reportes de la comunidad"):
            self.assertNotIn(etiqueta, js,
                             f"«{etiqueta}» vuelve a estar escrita en el navegador")


class TestEntradillaDeMunicipios(unittest.TestCase):
    """La frase que resume la página, con la brecha dentro y su corte."""

    def test_dice_las_tres_cifras_y_la_brecha(self):
        items = [_municipio(f"M{i}") for i in range(9)]
        items[0]["en_aoi_copernicus"] = True
        items[1]["unosat_edificios"] = 4
        items[8]["rud_personas"] = None
        items[8]["rud_familias"] = None
        texto = R.entradilla_municipios(_ctx_municipios(items))
        self.assertIn("<b>9 municipios</b>", texto)   # el total
        self.assertIn("<b>8</b>", texto)              # con damnificados
        self.assertIn("<b>2</b>", texto)              # mirados por satélite
        self.assertIn("<b>6</b>", texto)              # con RUD y sin mirada
        self.assertIn("22 de agosto de 2026", texto,
                      "la cifra se cita suelta y viaja sin su corte")

    def test_sin_ningun_satelite_no_se_inventa_un_cero(self):
        """Donde falta el dato se calla el trozo. «solo 0 han sido
        mirados» sería un recuento publicado donde no hay ninguno."""
        texto = R.entradilla_municipios(_ctx_municipios([_municipio()]))
        self.assertIn("ningún satélite ha evaluado todavía a ninguno", texto)
        self.assertNotIn("<b>0</b>", texto)

    def test_sin_municipios_lo_dice_en_vez_de_quedarse_vacia(self):
        """Un contenedor `data-gen` vacío rompe el build y deja la página muda:
        la rama sin datos tiene que escribir algo verdadero."""
        texto = R.entradilla_municipios(_ctx_municipios([]))
        self.assertTrue(texto.strip())
        self.assertIn("Todavía no hay ningún municipio", texto)

    def test_sin_corrida_se_calla_la_fecha_en_vez_de_inventarla(self):
        texto = R.entradilla_municipios(
            _ctx_municipios([_municipio()], generado=None))
        self.assertNotIn("corrida", texto)
        self.assertTrue(texto.strip())


class TestNotaDeMunicipios(unittest.TestCase):
    """El pie de la tabla: la prosa invariante, y solo aquí."""

    def test_la_salvedad_de_los_homonimos_se_apaga_sola(self):
        """R11: es una leyenda de lo que hay, no un literal que alguien tenga
        que acordarse de borrar el día que no quede ninguno."""
        sin = R.nota_municipios(_ctx_municipios([_municipio()]))
        self.assertNotIn("igual que un departamento", sin)
        con = R.nota_municipios(_ctx_municipios(
            [_municipio(), _municipio("Sucre", homonimo_de_departamento=True)]))
        self.assertIn("igual que un departamento", con)
        self.assertIn("un municipio", con, "no concuerda con la cifra")

    def test_el_guion_se_explica_y_ninguna_ausencia_es_cero(self):
        nota = R.nota_municipios(_ctx_municipios([_municipio()]))
        self.assertIn("no que no haya daño", nota)
        self.assertIn("jamás un cero", nota)

    def test_el_literal_no_vuelve_a_vivir_en_el_navegador(self):
        """Vivía en `municipios.js` y en el HTML a la vez: dos copias de la
        misma frase que ya podían divergir."""
        js = (ROOT / "site/municipios.js").read_text(encoding="utf-8")
        self.assertNotIn("no que no haya daño", js)


class TestDatasetDeMunicipios(unittest.TestCase):
    """El Dataset JSON-LD de la página, que antes no existía."""

    def _ld(self, ctx):
        crudo = R.dataset_municipios(ctx)
        self.assertTrue(crudo.startswith('<script type="application/ld+json">'),
                        "el generador debe traer su propio <script>: el "
                        "contenedor de site/ es una sección, porque un bloque "
                        "ld+json vacío es JSON inválido")
        return json.loads(re.search(r">(.*)</script>$", crudo, re.S).group(1))

    def test_g2_el_nodo_tiene_nombre_y_descripcion_y_no_anida_datasets(self):
        ld = self._ld(_ctx_municipios([_municipio()]))
        for campo in ("name", "description"):
            self.assertTrue(str(ld.get(campo) or "").strip(), f"sin «{campo}»")
        anidados = [n for clave, valor in ld.items() if clave != "@type"
                    for n in nodos_ld(valor) if "Dataset" in tipos_ld(n)]
        self.assertEqual(anidados, [], "un Dataset dentro de otro: usa @id")

    def test_g6_toda_url_del_bloque_es_absoluta(self):
        ld = self._ld(_ctx_municipios([_municipio()]))
        for nodo in nodos_ld(ld):
            for campo in ("contentUrl", "url", "logo", "@id"):
                valor = nodo.get(campo)
                if not isinstance(valor, str):
                    continue
                partes = urllib.parse.urlparse(valor)
                self.assertTrue(partes.scheme and partes.netloc,
                                f"«{campo}» relativo → {valor}")

    def test_las_dos_entidades_se_referencian_y_no_se_redefinen(self):
        """`creator`, `publisher` y el catálogo van por `@id` al nodo de
        identidad que ya escribe `BLOQUE_IDENTIDAD` en esta misma página."""
        ld = self._ld(_ctx_municipios([_municipio()]))
        self.assertEqual(ld["creator"], {"@id": R.ORGANIZACION})
        self.assertEqual(ld["publisher"], {"@id": R.ORGANIZACION})
        self.assertEqual(ld["includedInDataCatalog"], {"@id": R.SITIO})

    def test_una_fuente_sin_dato_se_omite_entera_y_jamas_sale_en_cero(self):
        """R3 dentro del marcado. Con solo el RUD cargado, ni el satélite
        ni el DYFI ni la prensa tienen columna ni cita: no las hay, y un cero
        afirmaría que las fuentes miraron y no vieron nada."""
        ld = self._ld(_ctx_municipios([_municipio()]))
        nombres = [v["name"] for v in ld["variableMeasured"]]
        self.assertIn("Personas inscritas en el RUD", nombres)
        for ausente in ("UNITAR-UNOSAT", "ICube-SERTIT", "Copernicus",
                        "DYFI", "Titulares"):
            self.assertFalse([n for n in nombres if ausente in n],
                             f"«{ausente}» tiene columna sin un solo dato")
        citas = [c["name"] for c in ld["citation"]]
        self.assertEqual(len(citas), 2, f"cita fuentes que no aportaron: {citas}")
        # tres columnas exactas —población, personas del RUD y su proporción—:
        # ni una más «en cero» para las fuentes que no publicaron nada
        self.assertEqual(len(nombres), 3, f"columnas de más: {nombres}")
        self.assertEqual([t for t in ld["measurementTechnique"] if "satelital" in t],
                         [], "declara técnica satelital sin un solo dato satelital")

    def test_la_cita_del_satelite_aparece_en_cuanto_hay_dato(self):
        ld = self._ld(_ctx_municipios([_municipio(unosat_edificios=7)]))
        self.assertTrue([v for v in ld["variableMeasured"]
                         if "UNITAR-UNOSAT" in v["name"]])
        self.assertTrue([c for c in ld["citation"]
                         if "UNOSAT" in c["publisher"]["name"]])

    def test_variablemeasured_es_el_diccionario_de_columnas_y_no_las_filas(self):
        """208 ítems serían una segunda copia de la tabla; el índice para
        sistemas de IA ya lo hace llms-full.txt."""
        items = [_municipio(f"M{i}") for i in range(40)]
        ld = self._ld(_ctx_municipios(items))
        self.assertNotIn("ItemList", json.dumps(ld))
        self.assertLess(len(ld["variableMeasured"]), 15,
                        "el diccionario de columnas se volvió una lista de filas")
        for variable in ld["variableMeasured"]:
            self.assertEqual(variable["@type"], "PropertyValue")
            self.assertTrue(variable.get("unitText"), "una columna sin unidad")

    def test_sin_corrida_no_se_inventa_dateModified(self):
        ld = self._ld(_ctx_municipios([_municipio()], generado=None))
        self.assertNotIn("dateModified", ld)


class TestMarcadoDeNoticias(unittest.TestCase):
    """El JSON-LD de la página de titulares: un corpus, no una redacción.

    R9 es LA regla de esta página: el monitor compiló el corpus —eso firman
    `creator` y `publisher`— pero no produjo la prensa, y quién la produjo va
    en `citation`, por canal. Los guardianes G2/G6 (`TestMarcadoEstructurado`)
    ya recorren este bloque; aquí va lo específico de titulares.

    Se lee la página **servida**, no la del repositorio: `site/noticias.html`
    versiona el nodo de identidad como un contenedor vacío que solo llena
    `escribir_piezas_compartidas()`, y un `<script type="application/ld+json">`
    sin contenido no es JSON — leer el fuente hacía que `bloques_ld` se comiera
    el documento hasta el siguiente `</script>` y reventara al parsear. Lo que
    Google indexa es el artefacto, así que es el artefacto lo que se mira. Las
    cifras del día siguen sin sustituir a propósito: el marcador
    `{{noticias_corte}}` tiene su propio guardián más abajo."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        shutil.copy(ROOT / "site" / "noticias.html", cls.tmp / "noticias.html")
        R.escribir_piezas_compartidas(cls.tmp)
        cls.html = (cls.tmp / "noticias.html").read_text(encoding="utf-8")
        cls.bloques = bloques_ld(cls.html)
        cls.dataset = next(n for b in cls.bloques for n in nodos_ld(b)
                           if "Dataset" in tipos_ld(n))

    def test_el_dataset_referencia_la_identidad_no_la_embebe(self):
        self.assertEqual(self.dataset["@id"],
                         "https://datosdelterremoto.org/noticias.html#dataset")
        self.assertEqual(self.dataset["creator"], {"@id": R.ORGANIZACION})
        self.assertEqual(self.dataset["publisher"], {"@id": R.ORGANIZACION})
        self.assertEqual(self.dataset["includedInDataCatalog"], {"@id": R.SITIO})

    def test_r9_dos_niveles_de_atribucion_y_ningun_articulo_apropiado(self):
        """`citation` nombra los tres canales reales; ningún nodo se declara
        `author` de nada ni marca un titular como artículo propio."""
        nombres = " · ".join(c.get("name", "") for c in self.dataset["citation"])
        self.assertIn("GDACS", nombres)
        self.assertIn("Google News", nombres)
        self.assertIn("registro abierto", nombres)
        for bloque in self.bloques:
            for nodo in nodos_ld(bloque):
                self.assertNotIn("author", nodo,
                                 "el monitor no es autor de la prensa (R9)")
                self.assertNotIn("NewsArticle", tipos_ld(nodo))

    def test_sin_licencia_sobre_prensa_ajena(self):
        """A diferencia de las fichas, este Dataset no declara `license`: el
        monitor no puede licenciar titulares de terceros. Si se decide otra
        cosa, se cambia aquí y en el HTML a la vez, con su entrada en
        DECISIONES."""
        self.assertNotIn("license", self.dataset)

    def test_la_collectionpage_apunta_al_dataset(self):
        pagina = next(n for b in self.bloques for n in nodos_ld(b)
                      if "CollectionPage" in tipos_ld(n))
        self.assertEqual(pagina["mainEntity"], {"@id": self.dataset["@id"]})

    def test_el_corte_lo_escribe_el_build_y_sin_corte_revienta(self):
        """`dateModified` viaja como marcador {{noticias_corte}} porque un
        <span data-gen> no cabe en un bloque JSON-LD. Con corrida válida el
        build lo escribe; sin ella la clave no se emite y `sustituir_cifras`
        rompe el build — publicar "None" fecharía el corpus en la nada."""
        self.assertEqual(self.dataset["dateModified"], "{{noticias_corte}}")
        con = R.cifras_del_dia({"chatmap": [], "noticias_generado": "2026-08-22"})
        self.assertEqual(con["noticias_corte"], "2026-08-22")
        sin = R.cifras_del_dia({"chatmap": [], "noticias_generado": "mañana"})
        self.assertNotIn("noticias_corte", sin)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            shutil.copy(ROOT / "site" / "noticias.html", destino / "noticias.html")
            with self.assertRaises(KeyError) as roto:
                R.sustituir_cifras(destino, {"chatmap": [],
                                             "noticias_generado": None})
            self.assertIn("noticias_corte", str(roto.exception))
            R.sustituir_cifras(destino, {"chatmap": [],
                                         "noticias_generado": "2026-08-22"})
            escrito = (destino / "noticias.html").read_text(encoding="utf-8")
            self.assertIn('"dateModified":"2026-08-22"', escrito)


class TestPrerenderizadoDeMunicipios(unittest.TestCase):
    """El inyector de verdad sobre el `site/municipios.html` del repositorio.

    Es lo que separa «el generador devuelve algo» de «el artefacto lo lleva»:
    también cae si alguien quita una marca, le cambia la etiqueta al contenedor
    o desconecta un generador del registro.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        shutil.copy(ROOT / "site" / "municipios.html", cls.tmp / "municipios.html")
        cls.hechas = R.inyectar_prerenderizado(cls.tmp, R.contexto())
        # los dos pasos del build, y en su orden: el nodo de identidad al que
        # el Dataset referencia por `@id` lo escribe el segundo
        R.escribir_piezas_compartidas(cls.tmp)
        cls.html = (cls.tmp / "municipios.html").read_text(encoding="utf-8")

    def test_los_seis_contenedores_de_la_pagina_llegan_escritos(self):
        for clave in ("municipios", "mun-resumen", "mun-silencio", "mun-chips",
                      "mun-homonimos", "mun-nota", "mun-dataset"):
            with self.subTest(contenedor=clave):
                self.assertIn(clave, self.hechas)
                dentro = re.search(
                    rf'<(tbody|span|section|p)[^>]*\bdata-gen="{clave}"[^>]*>(.*?)</\1>',
                    self.html, re.S)
                self.assertTrue(dentro, f"«{clave}» ya no está en site/")
                self.assertTrue(dentro.group(2).strip(),
                                f"«{clave}» llegó vacío al artefacto")

    def test_el_dataset_viaja_como_bloque_valido_y_no_como_script_vacio(self):
        """NINGUNA de las cinco páginas versiona un `ld+json` vacío.

        Un contenedor a la espera de su relleno no puede ser un formato que
        alguien tenga que parsear: quien lea el documento antes del build —el
        `site/` de desarrollo, y los guardianes G2/G6, que construyen las 213
        páginas sin pasar por el inyector— se encuentra JSON que no parsea.
        Costó dos averías el mismo día en dos páginas distintas de la fase 4:
        el `mun-dataset` de esta y el `#site-identity` de las cinco, que ahora
        se marcan con `<div hidden>` y no con un `<script>` sin cuerpo.
        """
        for pagina in ("index", "municipios", "rud", "balances", "noticias"):
            fuente = (ROOT / "site" / f"{pagina}.html").read_text(encoding="utf-8")
            with self.subTest(pagina=pagina):
                self.assertNotRegex(
                    fuente, r'<script type="application/ld\+json"[^>]*>\s*</script>',
                    f"site/{pagina}.html versiona un ld+json vacío: usa un "
                    "contenedor que no haya que parsear")
        datasets = datasets_ld(self.html)
        self.assertEqual(len(datasets), 1, "la página no publica su Dataset")
        self.assertEqual(datasets[0]["@id"],
                         "https://datosdelterremoto.org/municipios.html#dataset")

    def test_el_hallazgo_del_silencio_de_prensa_llega_servido(self):
        """Es la cifra más citable de la página y la escribía el navegador."""
        aviso = re.search(r'<section[^>]*\bdata-gen="mun-silencio"[^>]*>(.*?)</section>',
                          self.html, re.S).group(1)
        self.assertIn("no encontró ni un titular", aviso)
        self.assertGreater(len(re.sub(r"<[^>]+>", " ", aviso).split()), 100,
                           "el aviso llegó recortado")


class TestLaMiradaSatelitalEnLasDosSuperficies(unittest.TestCase):
    """Las dos preguntas sobre «sin satélite», ejecutadas y comparadas.

    `ingest/municipios.py::sin_mirada_satelital` (la capa del mapa) exige
    además damnificados registrados; `render_html::_mirado_por_satelite` (la
    entradilla de la tabla) no. Por eso la portada publica una cifra y
    municipios.html otra, y las dos tienen razón. Lo que no puede pasar es que
    dejen de coincidir en QUÉ cuenta como mirada, y eso se comprueba
    LLAMÁNDOLAS: comparar los nombres de los campos en el texto de los dos
    ficheros pasa en verde con la condición invertida.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "ingest"))
        import municipios as M
        cls.M = M

    def _casos(self):
        for cop in (False, True):
            for uno in (None, 0, 5):
                for ser in (None, 0, 5):
                    for rud in (None, 0, 12):
                        yield {"municipio": "X", "departamento": "Chocó",
                               "en_aoi_copernicus": cop, "unosat_edificios": uno,
                               "sertit_edificios": ser, "rud_familias": rud}

    def test_la_diferencia_entre_las_dos_es_el_rud_y_nada_mas(self):
        for m in self._casos():
            with self.subTest(**m):
                self.assertEqual(
                    self.M.sin_mirada_satelital(m),
                    (not R._mirado_por_satelite(m)) and bool(m["rud_familias"]),
                    "las dos superficies dejaron de medir la misma mirada")

    def test_cero_edificios_evaluados_es_mirada_y_no_ausencia(self):
        """`is not None`, no truthiness: un servicio que evaluó el municipio y
        no encontró ni un edificio dañado SÍ lo miró, y contarlo como ausencia
        acusaría a la fuente de no haber entregado nada."""
        mirados = {"municipio": "X", "departamento": "Chocó",
                   "en_aoi_copernicus": False, "unosat_edificios": 0,
                   "sertit_edificios": None, "rud_familias": 12}
        self.assertTrue(R._mirado_por_satelite(mirados))
        self.assertFalse(self.M.sin_mirada_satelital(mirados))

    def test_los_tres_servicios_cuentan_uno_a_uno(self):
        base = {"municipio": "X", "departamento": "Chocó",
                "en_aoi_copernicus": False, "unosat_edificios": None,
                "sertit_edificios": None, "rud_familias": 12}
        self.assertFalse(R._mirado_por_satelite(base))
        for campo, valor in (("en_aoi_copernicus", True),
                             ("unosat_edificios", 3), ("sertit_edificios", 3)):
            with self.subTest(campo=campo):
                self.assertTrue(R._mirado_por_satelite({**base, campo: valor}),
                                f"{campo} dejó de contar como mirada")


class TestEnlaceSeguroEsEspejo(unittest.TestCase):
    """`enlace_seguro` (Python) y `enlaceSeguro` (noticias.js) filtran igual.

    `e()` impide salirse del atributo, pero no impide que el atributo entero
    sea `javascript:…`: escapar y validar el esquema son cosas distintas. El
    navegador filtraba desde el principio y la lista servida nació sin filtro
    —la copia que diverge, al revés: la copia nueva era la más pobre—, así que la regla se escribe
    una vez en cada lenguaje y este guardián EJECUTA las dos: el JavaScript se
    extrae de `site/noticias.js`, no se copia aquí, porque una tercera copia
    volvería a divergir en silencio.
    """

    CASOS = ("https://eltiempo.com/x", "http://eltiempo.com/x",
             "javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x",
             "vbscript:x", "", "//eltiempo.com/x", "/relativa", "ftp://x/y")

    @classmethod
    def setUpClass(cls):
        fuente = (ROOT / "site" / "noticias.js").read_text(encoding="utf-8")
        hallado = re.search(
            r"const enlaceSeguro = \(u\) => \{.*?\n  \};", fuente, re.S)
        assert hallado, "no encuentro `enlaceSeguro` en site/noticias.js"
        cls.js_real = hallado.group(0)

    def _js(self, casos):
        script = (f"{self.js_real}\n"
                  "const salida = %s.map((x) => "
                  "  enlaceSeguro(x) === '#' ? 'BLOQUEA' : 'PASA');\n"
                  "console.log(JSON.stringify(salida));" % json.dumps(list(casos)))
        r = subprocess.run(["node", "-"],
                           input="global.location={origin:"
                                 "'https://datosdelterremoto.org'};" + script,
                           capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(f"node falló: {r.stderr[:400]}")
        return json.loads(r.stdout)

    def test_las_dos_superficies_dejan_pasar_lo_mismo(self):
        en_js = self._js(self.CASOS)
        en_py = ["BLOQUEA" if R.enlace_seguro(u) == "#" else "PASA"
                 for u in self.CASOS]
        for caso, a, b in zip(self.CASOS, en_py, en_js):
            with self.subTest(url=caso):
                self.assertEqual(a, b,
                                 f"«{caso}»: Python dice {a} y noticias.js {b}")

    def test_ningun_esquema_ejecutable_llega_a_un_href(self):
        for veneno in ("javascript:alert(1)", "JAVASCRIPT:alert(1)",
                       "data:text/html;base64,x", "vbscript:x"):
            with self.subTest(url=veneno):
                self.assertEqual(R.enlace_seguro(veneno), "#")


class TestDatasetDelRud(unittest.TestCase):
    """El Dataset JSON-LD de rud.html: la página no tenía ningún marcado.

    Era la única grande sin un solo nodo estructurado —cero `Dataset` en el
    artefacto—, así que el registro oficial de damnificados, que es el dato que
    nadie más publica consolidado, no existía para quien indexa conjuntos de
    datos ni para quien cita sin ejecutar JavaScript.

    Los guardianes de esta clase son los tres de la especificación: **G1** —una
    cifra ausente se omite, jamás vale 0—, **G2** —ningún `Dataset` sin nombre
    ni descripción, ni anidado dentro de otro— y **G6** —toda URL absoluta—.
    """

    SERIE = [{"fecha": "2026-08-20", "familias": 1000.0, "personas": 2000.0,
              "municipios": 10, "viv_destruidas": 5.0, "viv_averiadas": 7.0},
             {"fecha": "2026-08-21", "familias": 1300.0, "personas": 2600.0,
              "municipios": 12, "viv_destruidas": 8.0, "viv_averiadas": 9.0}]
    MUNICIPIOS = [{"departamento": "CHOCÓ", "municipio": "QUIBDÓ",
                   "familias": 780.0, "personas": 1600.0, "viv_destruidas": 5.0,
                   "viv_averiadas": 6.0, "poblacion_2026": 130000,
                   "tasa_pct": 1.231, "delta_familias": 180.0},
                  {"departamento": "CALDAS", "municipio": "ANSERMA",
                   "familias": 70.0, "personas": 150.0, "viv_destruidas": 3.0,
                   "viv_averiadas": 3.0, "poblacion_2026": 30000,
                   "tasa_pct": 0.5, "delta_familias": None}]

    def _ld(self, **cambios):
        rud = {"serie": copy.deepcopy(self.SERIE),
               "municipios": copy.deepcopy(self.MUNICIPIOS),
               "generado": "2026-08-22"}
        rud.update(cambios)
        crudo = R.dataset_rud({"rud": rud})
        self.assertTrue(crudo.startswith('<script type="application/ld+json">'),
                        "el generador debe traer su propio <script>: el "
                        "contenedor de site/rud.html es una sección, porque un "
                        "bloque ld+json vacío es JSON inválido")
        return json.loads(re.search(r">(.*)</script>$", crudo, re.S).group(1))

    def _variables(self, ld) -> dict:
        return {v["name"]: v for v in ld.get("variableMeasured", [])}

    # ------------------------------------------------------------------ G1
    def test_g1_una_cifra_ausente_se_omite_entera_y_jamas_sale_en_cero(self):
        """R3 dentro del marcado.

        Sin viviendas destruidas en ninguna de las dos capas, la columna **no
        existe**: un `"value": 0` afirmaría que el registro evaluó y no
        encontró ninguna, que es lo contrario de lo que dice la página. El
        JSON seguiría siendo válido y Google no se quejaría — este marcado
        miente en silencio, y por eso hace falta el guardián.
        """
        serie = copy.deepcopy(self.SERIE)
        munis = copy.deepcopy(self.MUNICIPIOS)
        for d in serie:
            d["viv_destruidas"] = None
        for m in munis:
            m["viv_destruidas"] = None
        variables = self._variables(self._ld(serie=serie, municipios=munis))
        self.assertNotIn("Viviendas destruidas", variables,
                         "una columna sin un solo dato sigue en el marcado")
        for nombre, variable in variables.items():
            with self.subTest(columna=nombre):
                self.assertNotEqual(variable.get("value"), 0,
                                    "una ausencia se convirtió en un cero")

    def test_g1_el_dato_que_solo_existe_en_el_detalle_se_describe_sin_valor(self):
        """La columna que la serie no agrega —la población, la proporción, el
        delta— se describe: existe y el lector la va a encontrar en la tabla.
        Lo que no se hace es inventarle un total nacional, ni ponerlo a 0."""
        variables = self._variables(self._ld())
        for solo_columna in ("Población proyectada 2026 (DANE)",
                             "Personas del RUD sobre población 2026",
                             "Familias nuevas desde la captura anterior"):
            with self.subTest(columna=solo_columna):
                self.assertIn(solo_columna, variables)
                self.assertNotIn("value", variables[solo_columna],
                                 "se le inventó un agregado a una columna que "
                                 "la serie no suma")

    def test_g1_un_cero_medido_de_verdad_si_se_publica(self):
        """La otra mitad de R3, la que se olvida: omitir lo falsy también
        miente. Si la captura dice que el registro no ha cargado ninguna
        vivienda destruida, ese cero es el dato y se publica."""
        serie = copy.deepcopy(self.SERIE)
        serie[-1]["viv_destruidas"] = 0
        variables = self._variables(self._ld(serie=serie))
        self.assertEqual(variables["Viviendas destruidas"]["value"], 0)

    def test_las_cifras_no_arrastran_la_cola_decimal_de_la_fuente(self):
        """El RUD llega en flotantes (`1300.0`): quien cite el marcado leería
        un decimal que la fuente nunca publicó."""
        variables = self._variables(self._ld())
        self.assertEqual(variables["Familias inscritas"]["value"], 1300)
        for nombre, variable in variables.items():
            if "value" in variable:
                with self.subTest(columna=nombre):
                    self.assertIsInstance(variable["value"], int)

    # ------------------------------------------------------------------ G2
    def test_g2_el_nodo_tiene_nombre_y_descripcion_y_no_anida_datasets(self):
        ld = self._ld()
        for campo in ("name", "description"):
            self.assertTrue(str(ld.get(campo) or "").strip(), f"sin «{campo}»")
        anidados = [n for clave, valor in ld.items() if clave != "@type"
                    for n in nodos_ld(valor) if "Dataset" in tipos_ld(n)]
        self.assertEqual(anidados, [], "un Dataset dentro de otro: usa @id")

    # ------------------------------------------------------------------ G6
    def test_g6_toda_url_del_bloque_es_absoluta(self):
        for nodo in nodos_ld(self._ld()):
            for campo in ("contentUrl", "url", "logo", "@id"):
                valor = nodo.get(campo)
                if not isinstance(valor, str):
                    continue
                partes = urllib.parse.urlparse(valor)
                with self.subTest(campo=campo, valor=valor):
                    self.assertTrue(partes.scheme and partes.netloc,
                                    f"«{campo}» relativo → {valor}")

    # ------------------------------------------------------------- atribución
    def test_r9_el_monitor_compila_y_la_ungrd_se_cita(self):
        """El monitor no produce la cifra oficial: la compila. La UNGRD no
        publica esta página: publica el RUD. Confundirlo es el error editorial
        que R9 prohíbe, y aquí se ve en dos campos distintos."""
        ld = self._ld()
        self.assertEqual(ld["creator"], {"@id": R.ORGANIZACION})
        self.assertEqual(ld["publisher"], {"@id": R.ORGANIZACION})
        self.assertEqual(ld["includedInDataCatalog"], {"@id": R.SITIO})
        citados = [c["publisher"]["name"] for c in ld["citation"]]
        self.assertTrue([n for n in citados if "UNGRD" in n],
                        "el RUD es de la UNGRD y no aparece citado")
        self.assertNotIn("UNGRD", json.dumps(ld["publisher"], ensure_ascii=False))

    def test_la_cita_del_dane_entra_con_su_columna_y_no_antes(self):
        """Consultar una fuente que no aportó nada no se cita: sería atribuirle
        un dato que no puso."""
        munis = [{k: v for k, v in m.items()
                  if k not in ("poblacion_2026", "tasa_pct")}
                 for m in copy.deepcopy(self.MUNICIPIOS)]
        sin_dane = self._ld(municipios=munis)
        self.assertEqual([c["name"] for c in sin_dane["citation"]],
                         ["Registro Único de Damnificados (RUD)"])
        self.assertEqual([t for t in sin_dane["measurementTechnique"]
                          if "DANE" in t], [],
                         "declara la técnica del DANE sin un solo dato suyo")
        con_dane = self._ld()
        self.assertTrue([c for c in con_dane["citation"]
                         if "DANE" in c["publisher"]["name"]])

    def test_el_rud_no_se_publica_como_una_evaluacion_de_dano(self):
        """Que un municipio no aparezca significa «sin registro aún», no «sin
        daño». Es la salvedad central de la página y tiene que viajar en el
        marcado, que es lo que se cita sin leer la prosa."""
        ld = self._ld()
        self.assertIn("sin registro aún", ld["description"])
        tecnicas = " ".join(ld["measurementTechnique"])
        self.assertIn("No es un EDAN", tecnicas)
        variables = self._variables(ld)
        self.assertIn("sin registro aún",
                      variables["Municipios con registro en el RUD"]["description"])

    # ------------------------------------------------------------- el fechado
    def test_m7_el_marcado_se_fecha_con_el_dato_y_no_con_la_corrida(self):
        """La página distingue «datos hasta el 21» de «corrida del 22» en su
        sello; el marcado no puede publicar solo la del build, o una IA leería
        las familias del 21 fechadas el 22. La cobertura arranca el día del
        sismo y **cierra**: un extremo abierto diría que el registro sigue
        cargando hoy, que es una afirmación sobre el futuro."""
        ld = self._ld()
        self.assertEqual(ld["dateModified"], "2026-08-21")
        self.assertEqual(ld["temporalCoverage"], "2026-08-10/2026-08-21")
        self.assertNotIn("2026-08-22", json.dumps(ld, ensure_ascii=False),
                         "la fecha de la corrida se coló en el marcado")
        self.assertIn("21 de agosto de 2026",
                      self._variables(ld)["Familias inscritas"]["description"],
                      "una cifra del RUD sin su corte miente en 48 horas")

    def test_sin_ninguna_captura_no_se_inventa_ni_una_fecha_ni_una_cifra(self):
        """El día que el RUD no haya publicado nada, el conjunto de datos
        sigue existiendo y la UNGRD sigue siendo su fuente: lo que se calla
        son las cifras, no la existencia del dataset."""
        ld = self._ld(serie=[], municipios=[])
        for campo in ("dateModified", "temporalCoverage", "variableMeasured"):
            self.assertNotIn(campo, ld, f"«{campo}» inventado sin una captura")
        self.assertTrue(ld["name"] and ld["description"])
        self.assertEqual([c["name"] for c in ld["citation"]],
                         ["Registro Único de Damnificados (RUD)"])

    # --------------------------------------------------- diccionario, no filas
    def test_variablemeasured_es_el_diccionario_de_columnas_y_no_las_filas(self):
        """207 filas en un `ItemList` no disparan ningún resultado enriquecido
        y serían una segunda copia de la tabla mantenida aparte."""
        munis = [dict(self.MUNICIPIOS[0], municipio=f"M{i}") for i in range(40)]
        ld = self._ld(municipios=munis)
        self.assertNotIn("ItemList", json.dumps(ld, ensure_ascii=False))
        self.assertLess(len(ld["variableMeasured"]), 15,
                        "el diccionario de columnas se volvió una lista de filas")
        for variable in ld["variableMeasured"]:
            with self.subTest(columna=variable["name"]):
                self.assertEqual(variable["@type"], "PropertyValue")
                self.assertTrue(variable.get("unitText"), "columna sin unidad")

    def test_las_columnas_declaradas_son_las_de_la_tabla_servida(self):
        """El diccionario describe la tabla que se lee debajo: si una columna
        se fuera del HTML y siguiera aquí, el marcado prometería un dato que la
        página ya no publica. Se compara contra `COLUMNAS_RUD`, que es de
        donde salen las dos cosas.

        Se cuentan solo las columnas de cifra (`th.num`): la primera columna es
        el rótulo de la fila —el nombre del municipio, que no mide nada— y
        «Municipios con registro» no es una columna de la tabla sino la
        variable de la serie, así que se excluye de los dos lados.
        """
        cabeceras = re.findall(
            r'<th scope="col" class="num"[^>]*>(.*?)</th>',
            (ROOT / "site" / "rud.html").read_text(encoding="utf-8"))
        de_tabla = [c[1] for c in R.COLUMNAS_RUD if c[0] != "municipios"]
        self.assertEqual(
            len(cabeceras), len(de_tabla),
            f"la tabla sirve {len(cabeceras)} columnas de cifra y el marcado "
            f"describe {len(de_tabla)}: {cabeceras} · {de_tabla}")
        self.assertIn("Municipios con registro en el RUD",
                      [c[1] for c in R.COLUMNAS_RUD])

    # ------------------------------------------------------- el dato de verdad
    def test_el_dato_real_cuadra_con_la_serie_publicada(self):
        """Sobre `data/public/rud.json`, no sobre el fixture: un marcado que
        cuadre con un ejemplo inventado y no con el dato publicado no sirve."""
        ctx = R.contexto()
        crudo = R.dataset_rud(ctx)
        ld = json.loads(re.search(r">(.*)</script>$", crudo, re.S).group(1))
        ult = ctx["rud"]["serie"][-1]
        variables = self._variables(ld)
        for campo, rotulo, _, agrega in R.COLUMNAS_RUD:
            if not agrega or ult.get(campo) is None:
                continue
            with self.subTest(columna=rotulo):
                self.assertEqual(variables[rotulo]["value"], int(ult[campo]))
        self.assertEqual(ld["dateModified"], ult["fecha"])


class TestElDatasetDelRudLlegaAlArtefacto(unittest.TestCase):
    """El inyector de verdad sobre el `site/rud.html` del repositorio.

    Separa «el generador devuelve algo» de «la página lo lleva»: cae si alguien
    quita la marca, le cambia la etiqueta al contenedor o desconecta el
    generador de cualquiera de los dos registros del inyector."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        shutil.copy(ROOT / "site" / "rud.html", cls.tmp / "rud.html")
        cls.hechas = R.inyectar_prerenderizado(cls.tmp, R.contexto())
        # los dos pasos del build, y en su orden: el nodo de identidad al que
        # el Dataset referencia por `@id` lo escribe el segundo
        R.escribir_piezas_compartidas(cls.tmp)
        cls.html = (cls.tmp / "rud.html").read_text(encoding="utf-8")

    def test_el_contenedor_llega_escrito_y_no_vacio(self):
        self.assertIn("rud-dataset", self.hechas)
        dentro = re.search(
            r'<section[^>]*\bdata-gen="rud-dataset"[^>]*>(.*?)</section>',
            self.html, re.S)
        self.assertTrue(dentro, "«rud-dataset» ya no está en site/rud.html")
        self.assertTrue(dentro.group(1).strip(),
                        "«rud-dataset» llegó vacío al artefacto")

    def test_la_pagina_publica_un_dataset_y_solo_uno(self):
        datasets = datasets_ld(self.html)
        self.assertEqual(len(datasets), 1,
                         "rud.html seguía sin ningún dato estructurado")
        self.assertEqual(datasets[0]["@id"],
                         "https://datosdelterremoto.org/rud.html#dataset")

    def test_el_dataset_referencia_una_identidad_que_la_pagina_trae(self):
        """`@id` no resuelve entre documentos: la organización y el catálogo a
        los que apunta tienen que estar definidos en esta misma página."""
        definidos = {n.get("@id") for bloque in bloques_ld(self.html)
                     for n in nodos_ld(bloque) if n.get("name")}
        for referencia in (R.ORGANIZACION, R.SITIO):
            with self.subTest(id=referencia):
                self.assertIn(referencia, definidos)

    def test_el_marcador_va_vacio_en_el_repositorio(self):
        """La apertura pegada al cierre, y sin un `ld+json` a medio escribir
        dentro: es lo que el inyector busca y lo que lee quien abre `site/`
        antes del build."""
        fuente = (ROOT / "site" / "rud.html").read_text(encoding="utf-8")
        self.assertIn('<section hidden data-gen="rud-dataset"></section>', fuente)
        self.assertNotRegex(
            fuente, r'<script type="application/ld\+json"[^>]*>\s*</script>')


class TestElConsolidadoDeBalancesNoFallaEnSilencio(unittest.TestCase):
    """R11 · Un supuesto roto avisa; no se rompe en silencio.

    `TestBalancesSinNode` ya comprueba que la PÁGINA se lo dice al lector. Esto
    es la otra mitad, la que faltaba: quien construye tiene que enterarse de
    **por qué**. El `stderr` de node se perdía en un `except: pass`, así que un
    `ui.js` con un error de sintaxis y un día sin cifras eran indistinguibles
    desde el registro del build.
    """

    def _sin_cache(self):
        return {"monitor": {}, "oficiales": {"items": []}}

    def _corriendo(self, ctx, **parches):
        salida = io.StringIO()
        with contextlib.ExitStack() as pila:
            pila.enter_context(contextlib.redirect_stdout(salida))
            if parches:
                pila.enter_context(unittest.mock.patch.multiple(R, **parches))
            resultado = R.consolidado_balances(ctx)
        return resultado, salida.getvalue()

    def test_sin_node_se_dice_que_falta_node(self):
        resultado, avisos = self._corriendo(
            self._sin_cache(), shutil=unittest.mock.Mock(which=lambda _: None))
        self.assertIsNone(resultado)
        self.assertIn("::warning::", avisos, "la degradación pasó en silencio")
        self.assertIn("node", avisos)

    def test_el_stderr_de_node_llega_al_registro_del_build(self):
        """Es el caso que motiva el cambio: node existe, se ejecuta y falla.
        Sin el aviso, el porqué —un `ui.js` roto, por ejemplo— se perdía."""
        fallo = unittest.mock.Mock(returncode=1, stdout="",
                                   stderr="SyntaxError: ui.js está roto")
        resultado, avisos = self._corriendo(
            self._sin_cache(),
            subprocess=unittest.mock.Mock(run=lambda *a, **k: fallo,
                                          SubprocessError=Exception))
        self.assertIsNone(resultado)
        self.assertIn("::warning::", avisos)
        self.assertIn("SyntaxError: ui.js está roto", avisos,
                      "el stderr de node se sigue tragando")

    def test_una_corrida_sana_no_avisa_de_nada(self):
        """Un aviso que sale siempre deja de leerse: solo avisa lo que falla."""
        if not NODE:
            self.skipTest("sin node no hay corrida sana que comprobar")
        ctx = R.contexto()
        ctx.pop("_balances_ui", None)
        resultado, avisos = self._corriendo(ctx)
        self.assertIsNotNone(resultado)
        self.assertNotIn("::warning::", avisos)
class TestChipsDeLaFicha(unittest.TestCase):
    """Los chips que encienden y apagan las capas del mapa de evidencias.

    Sustituyen a `L.control.layers`, que por debajo de 560 px se colapsa en un
    icono: en el móvil, las cinco fuentes quedaban escondidas detrás de un
    símbolo que hay que descubrir. La tira la escribe el BUILD, con su rótulo y
    su recuento; el navegador solo la conecta. Construirla en el navegador sería
    una segunda copia de los recuentos y dejaría la tira vacía para quien
    lee el documento sin ejecutarlo.
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.js = (ROOT / "site" / "municipio.js").read_text(encoding="utf-8")

    def _chips(self, html: str) -> list:
        """(capa, número, texto entero) de cada chip de la tira del mapa."""
        tira = re.search(r'<div class="chips chips-mapa".*?</div>', html, re.S)
        if not tira:
            return []
        return [(m.group(1), m.group(2), m.group(0))
                for m in re.finditer(
                    r'<button[^>]*data-capa="([^"]+)"[^>]*>.*?'
                    r'<span class="n">([\d.,]+)</span>.*?</button>',
                    tira.group(0), re.S)]

    def test_hay_un_chip_por_capa_con_puntos_y_ninguno_mas(self):
        """La condición del chip es la MISMA con que `municipio.js` crea la
        capa: `features.length`. Si divergieran, la ficha publicaría un chip que
        no acciona nada —el control muerto que el criterio prohíbe— o una capa sin quien
        la apague. Se comprueba sobre las 208, no sobre una."""
        vistas = 0
        for m in self.ctx["municipios"]:
            nombre = m["municipio"]
            if not R.es_elegible(nombre, self.ctx):
                continue
            d = R.datos_ficha(nombre, self.ctx)
            capas = d["evidencia"]["capas"]
            con_puntos = {clave for clave, cap in capas.items() if cap["features"]}
            chips = {clave for clave, _, _ in self._chips(R.chips_evidencia(d))}
            self.assertEqual(chips, con_puntos,
                             f"{nombre}: chips y capas con puntos no coinciden")
            vistas += 1
        self.assertGreater(vistas, 200, "el recorrido se ha encogido")

    def test_el_numero_del_chip_es_el_de_los_puntos_de_su_capa(self):
        """El recuento se escribe sobre el mismo `evidencia.json` que el
        navegador va a dibujar, y en locale es-CO."""
        for nombre in ("Cali", "Pereira", "Nóvita", "Roldanillo"):
            d = R.datos_ficha(nombre, self.ctx)
            for clave, numero, _ in self._chips(R.chips_evidencia(d)):
                esperado = R.fmt(len(d["evidencia"]["capas"][clave]["features"]))
                self.assertEqual(numero, esperado,
                                 f"{nombre}/{clave}: el chip promete {numero}")

    def test_sin_evidencia_no_se_publica_una_tira_vacia(self):
        """Un contenedor vacío es la lección de los globos sin datos: una tira
        de chips sin un solo chip ocupa sitio y no dice nada.

        El municipio se elige del corpus, no se nombra a mano: ver
        `ficha_del_corpus`."""
        d = ficha_del_corpus(self.ctx, lambda f: not f["hay_evidencia"],
                             SIN_EVIDENCIA_AGOTADA)
        self.assertEqual(R.chips_evidencia(d), "")
        self.assertNotIn("chips-mapa", R.render_ficha(d))

    def test_un_chip_es_una_accion_y_lo_pasivo_no_lo_parece(self):
        """Las 316 pastillas que no hacían nada: todo `.chip` de una ficha
        es un `<button>` de verdad. Lo que solo
        rotula —la leyenda del mapa, el distintivo de verificación— sigue siendo
        `.badge`, que ni es pulsable ni lo aparenta."""
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        # `chip(?:\s|"|--)` y no `chip[^"]*`: el contenedor se llama `chips` y
        # empieza por las mismas cuatro letras, así que el patrón perezoso lo
        # casaba y el test fallaba contra el `<div>` que envuelve la tira.
        for etiqueta in re.findall(r'<(\w+)[^>]*class="chip(?:\s|"|--)', html):
            self.assertEqual(etiqueta, "button",
                             f"un .chip escrito como <{etiqueta}> no se puede pulsar")
        self.assertIn('class="badge"', html)
        self.assertNotIn('<button class="badge', html)

    def test_cada_chip_declara_su_estado_para_un_lector_de_pantalla(self):
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        botones = re.findall(r'<button[^>]*class="chip chip--punto"[^>]*>', html)
        self.assertTrue(botones)
        for boton in botones:
            self.assertIn('aria-pressed="true"', boton)
            self.assertIn('type="button"', boton)

    def test_la_explicacion_va_encima_del_mapa_no_debajo_de_los_chips(self):
        """El recuento corto («Este mapa reúne…») va ENCIMA de las pestañas,
        siempre visible. La nota de los chips no se genera."""
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        intro = re.search(r'<p[^>]*class="[^"]*intro-mapa[^"]*"[^>]*>', html)
        self.assertIsNotNone(intro)
        self.assertNotIn(" hidden", intro.group(0))
        resumen = html.find("Este mapa reúne")
        chips = html.find('class="chips chips-mapa"')
        vistas = html.find('class="vistas"')
        mapa = html.find('class="mapa-evidencias"')
        self.assertGreater(resumen, 0)
        self.assertLess(resumen, vistas)
        self.assertLess(vistas, chips)
        self.assertLess(chips, mapa)
        self.assertNotIn("Cada chip retira", html)
        tira = re.search(r'<div class="chips chips-mapa".*?</div>', html, re.S)
        self.assertIsNotNone(tira)
        self.assertNotIn("title=", tira.group(0))

    def test_el_desajuste_entre_la_capa_y_el_recuento_existe_en_el_dato(self):
        """En Cali, ICube-SERTIT dibuja 103 puntos y solo 94 llevan grado de
        daño. El chip cuenta puntos; la prosa, edificios. se retiró la frase
        que explicaba la distancia: no se autoescribe."""
        d = R.datos_ficha("Cali", self.ctx)
        desajustes = R.desajustes_de_capas(d)
        self.assertTrue(desajustes, "Cali dejó de tener el desajuste de SERTIT")
        rotulo, puntos, con_grado, tipos = desajustes[0]
        self.assertGreater(puntos, con_grado)
        self.assertEqual(tipos, ["Tent/shelter"])
        html = R.render_ficha(d)
        self.assertFalse(hasattr(R, "nota_chips_evidencia"))
        self.assertNotIn("Cada chip retira", html)
        self.assertNotIn("los 9 restantes", html)

    def test_un_desajuste_al_reves_no_se_publica_en_negativo(self):
        """La frase dice «los N restantes», así que solo vale si la capa trae
        MÁS puntos que edificios clasificados. Con `!=` en vez de `>`, un
        servicio que clasificara más de los que dibuja —el agregado y la capa
        se construyen por vías distintas— publicaba «los −3 restantes»."""
        d = R.datos_ficha("Cali", self.ctx)
        capas = (d.get("evidencia") or {}).get("capas") or {}
        clave = next(s["clave"] for s in R.SATELITES
                     if s["rotulo"] == R.desajustes_de_capas(d)[0][0])
        # se le quitan puntos a la capa hasta dejarla por debajo del recuento
        capas[clave]["features"] = capas[clave]["features"][:3]
        self.assertEqual(
            [x for x in R.desajustes_de_capas(d) if x[0] == "ICube-SERTIT"], [],
            "un desajuste en negativo no se publica")

    def test_sin_desajuste_no_se_cuenta_uno(self):
        """Al revés: una salvedad que no se cumple aquí no se escribe aquí.
        207 de las 208 fichas no tienen desajuste y no deben leer una frase que
        insinúe que sí."""
        d = R.datos_ficha("Roldanillo", self.ctx)
        self.assertEqual(R.desajustes_de_capas(d), [])
        self.assertNotIn("Cada chip retira", R.render_ficha(d))

    def test_todo_servicio_satelital_tiene_su_rotulo_y_su_chip(self):
        """El día que entre el cuarto servicio, su chip y su cita aparecen solos
        porque salen de `SATELITES`. Este test cae si alguien lo da de alta a
        medias: sin rótulo corto no cabe en un chip y sin publicador no se puede
        citar."""
        claves = {clave for clave, _ in R.capas_evidencia()}
        for sat in R.SATELITES:
            self.assertIn(sat["clave"], claves,
                          f"{sat['nombre']} no tiene capa en el mapa de la ficha")
            for campo in ("rotulo", "publicador"):
                self.assertTrue(sat.get(campo),
                                f"{sat['nombre']} sin `{campo}`")

    def test_el_navegador_conecta_los_chips_pero_no_los_construye(self):
        """Si `municipio.js` volviera a fabricarlos, el recuento viviría en dos
        sitios y la ficha servida perdería la tira. Y el control de capas
        de Leaflet queda como respaldo, nunca como norma."""
        self.assertIn("conectarChips", self.js)
        self.assertIn("querySelectorAll(\".chip[data-capa]\")", self.js)
        self.assertRegex(
            self.js,
            r"if \(!conectarChips\([^)]*\)\s*\n?\s*&& Object\.keys\(overlays\)",
            "`L.control.layers` dejó de ser el respaldo de los chips")
        self.assertNotIn('createElement("button")', self.js)
        self.assertNotIn('className = "chip"', self.js)
        self.assertIn('closest(".lienzo-mun")', self.js,
                      "los chips salieron del tabpanel y el conector no los busca "
                      "en el lienzo: Leaflet volvería a sacar el control colapsado")


class TestLienzoMunicipal(unittest.TestCase):
    """Panel de fuentes y mapa conviven, como en el prototipo.

    La fase 5 dejó la ficha a medias: chips y marcado, pero el dato en una
    pestaña y el mapa en otra. se rechazó el 24-ago: la organización del
    prototipo —tabla de datos a un lado, mapa al otro, en móvil y escritorio—
    ES la ficha. El panel desglosa el RUD; las tarjetas lo resumen debajo.
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.cali = R.render_ficha(R.datos_ficha("Cali", cls.ctx))
        # elegido del corpus, no escrito a mano: ver `ficha_del_corpus`
        cls.ficha_sin_evidencia = ficha_del_corpus(
            cls.ctx, lambda f: not f["hay_evidencia"], SIN_EVIDENCIA_AGOTADA)
        cls.sin_evidencia = R.render_ficha(cls.ficha_sin_evidencia)

    def _panel(self, html: str) -> str:
        m = re.search(r'<aside class="panel">(.*?)</aside>', html, re.S)
        self.assertIsNotNone(m, "la ficha se publicó sin el panel de fuentes")
        return m.group(1)

    def test_el_lienzo_pone_el_panel_y_el_mapa_como_hermanos(self):
        """Panel y marco en el mismo lienzo, el panel ANTES en el DOM (teclado,
        lector) y también en móvil: se volvió a mirar y llega primero a la
        tabla. El CSS ya no invierte con `order`."""
        html = self.cali
        self.assertIn('class="lienzo lienzo-mun"', html)
        self.assertIn('class="marco-mapa"', html)
        self.assertLess(html.find('class="panel"'), html.find('class="marco-mapa"'))
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find('class="zona-datos"'))
        # Fuera de `.contenido`: entre el H1 y el lienzo se cierra ese
        # contenedor (max-width 760 px). Destacado y tarjetas van DESPUÉS,
        # en zona-datos.
        entre = html[html.find('class="contenido contenido-ficha"'):
                     html.find('<div class="lienzo lienzo-mun"')]
        self.assertNotIn("metric-strip", entre)
        self.assertNotIn('class="destacado"', entre)
        self.assertTrue(entre.rstrip().endswith("</div>"),
                        "el lienzo quedó dentro de .contenido")
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find('class="destacado"'))
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find('class="metric-strip"'))
        self.assertLess(html.find('class="panel"'),
                        html.find('class="destacado"'))

    def test_el_encabezado_trae_fecha_resumen_y_como_leer(self):
        """El prototipo lo midió: bajo el H1 van el sismo, las dos líneas de
        cifras y la nota de «cómo leer», antes del lienzo.

        La nota NO se pliega —son menos de 120 palabras, el umbral que fija— y su advertencia sobre el satélite es CONDICIONAL: se emitía en
        las 208 por igual y Pereira, mirada por Copernicus y por ICube-SERTIT,
        afirmaba la mirada arriba y la negaba aquí. Lo vigila también
        `TestCoherenciaDeLaFicha::test_ninguna_ficha_afirma_y_niega_el_satelite`.
        """
        html = self.cali
        self.assertIn(f'class="contexto-sismo">{R.CONTEXTO_SISMO}</span>', html)
        self.assertIn('class="resumen"', html)
        self.assertIn('class="nota-leer"', html)
        self.assertIn("Cada cifra dice de quién es y de qué día", html)
        self.assertLess(html.find("<h1>"), html.find('class="resumen"'))
        self.assertLess(html.find('class="nota-leer"'),
                        html.find('class="lienzo lienzo-mun"'))
        # Cali tiene satélite: la advertencia de la ausencia no le toca
        self.assertNotIn("no significa que no haya daño", html)
        d = R.datos_ficha("Cali", self.ctx)
        m = d["muni"]
        resumen = re.search(r'<p class="resumen">(.*?)</p>', html, re.S).group(1)
        self.assertIn(R.fmt(m["rud_familias"]), resumen)
        self.assertIn(R.pct(m["tasa_rud_pct"]), resumen)
        self.assertIn(R.fmt(d["cruce"]["unidades"]), resumen)

    def test_el_destacado_se_parte_como_en_el_prototipo(self):
        """Lead visible; satélites, vecinos y prensa en el plegable amarillo,
        debajo del primer cuadro, antes de las tarjetas."""
        html = self.cali
        pliegue = re.search(
            r'<details class="pliegue denso">(.*?)</details>', html, re.S)
        self.assertIsNotNone(pliegue)
        self.assertIn("Qué más se sabe de este municipio", pliegue.group(0))
        self.assertNotIn("Cada chip retira", pliegue.group(0))
        self.assertIn("documentado por satélite", pliegue.group(0))
        dest = html.find('class="destacado"')
        self.assertGreater(dest, 0)
        self.assertLess(dest, pliegue.start())
        self.assertLess(pliegue.start(), html.find('class="metric-strip"'))
        lead = html[dest:pliegue.start()]
        self.assertIn("inscritas como damnificadas", lead)
        self.assertNotIn("documentado por satélite", lead)

    def test_el_panel_desglosa_el_rud_con_las_mismas_cifras_que_las_tarjetas(self):
        """ (24-ago): en la tabla de fuentes hacen falta las cuatro cifras
        del registro, no un resumen. Las tarjetas siguen debajo (población
        DANE y el mismo número); si una cifra del panel no es la de la
        tarjeta, hay dos verdades."""
        d = R.datos_ficha("Cali", self.ctx)
        m = d["muni"]
        panel = self._panel(self.cali)
        self.assertIn("Familias inscritas", panel)
        self.assertIn("Viviendas destruidas", panel)
        self.assertIn("Viviendas averiadas", panel)
        self.assertIn("RUD · UNGRD", panel)
        for campo in ("rud_familias", "rud_personas", "rud_viv_destruidas",
                      "rud_viv_averiadas"):
            self.assertIn(R.fmt(m[campo]), panel)
        ini = self.cali.find('class="metric-strip"')
        fin = self.cali.find("Cómo avanza el registro oficial")
        tira = self.cali[ini:fin]
        self.assertGreater(ini, 0)
        for campo in ("rud_familias", "rud_personas", "rud_viv_destruidas",
                      "rud_viv_averiadas"):
            self.assertIn(R.fmt(m[campo]), tira)
        self.assertLess(panel.find("Familias inscritas"), panel.find("Copernicus"))
        self.assertLess(panel.find("Viviendas destruidas"), panel.find("Copernicus"))
        self.assertNotIn("tarjetas de arriba", self.cali)
        self.assertNotIn("debajo del mapa", panel)

    def test_sin_rud_el_panel_no_inventa_ceros(self):
        """Un municipio al que el registro no ha llegado omite la fila, no
        publica 0 (R3). El caso se elige del corpus —hasta el 24-ago era
        Palmira, que hoy ya tiene registro—: ver `municipio_sin_rud`."""
        nombre, ctx = municipio_sin_rud(self.ctx)
        html = R.render_ficha(R.datos_ficha(nombre, ctx))
        panel = self._panel(html)
        self.assertNotIn("Familias inscritas", panel)
        self.assertNotIn("RUD · UNGRD", panel)

    def test_un_cero_medido_del_rud_si_se_publica(self):
        """Un 0 que el RUD declara es dato, no ausencia: esconderlo sería
        tratar un 0 medido como un NA (R3). El municipio sale del corpus
        —Pereira lo fue hasta que el registro le contó 1.988 viviendas
        destruidas—: el primero, alfabético, que hoy declara ese cero."""
        d = ficha_del_corpus(
            self.ctx, lambda f: f["muni"].get("rud_viv_destruidas") == 0,
            "ningún municipio declara ya 0 viviendas destruidas en el RUD: "
            "sin un cero medido, este guardián no distingue el 0 del NA — "
            "replantearlo, no buscarle un municipio a mano")
        html = R.render_ficha(d)
        panel = self._panel(html)
        self.assertRegex(
            panel,
            r'Viviendas destruidas</span><span class="f">RUD · UNGRD[^<]*</span>'
            r'</span><span class="v">0</span>')
        # y el corte viaja pegado a la cifra: la nota promete «de qué día»
        self.assertRegex(panel, r'RUD · UNGRD · \d{1,2}-\w+-\d{4}')

    def test_el_panel_cuenta_lo_que_el_mapa_pinta_y_esconde_quien_no_miro(self):
        """R3: UNOSAT no miró Cali, así que no sale una fila a cero. El
        recuento de Copernicus es el de su capa, y debajo van los grados de
        daño —la misma clasificación que colorea los puntos."""
        d = R.datos_ficha("Cali", self.ctx)
        panel = self._panel(self.cali)
        n_cop = len(d["evidencia"]["capas"]["copernicus"]["features"])
        self.assertIn(R.fmt(n_cop), panel)
        self.assertIn("Destruidos", panel)
        self.assertIn("Dañados", panel)
        self.assertNotIn("UNITAR-UNOSAT", panel)
        self.assertIn("ICube-SERTIT", panel)
        self.assertIn("Puntos dibujados en el mapa", panel)

    def test_sin_evidencia_el_panel_avisa_y_no_inventa_pestanas(self):
        """Un municipio sin puntos: el lienzo sigue existiendo —el panel es
        la tabla de datos de TODA ficha—, pero sin pestañas ni JavaScript."""
        html = self.sin_evidencia
        self.assertIn('class="lienzo lienzo-mun"', html)
        self.assertIn("Qué dice cada fuente", html)
        self.assertIn("Ningún servicio satelital ha publicado producto de daño aquí",
                      html)
        self.assertNotIn('role="tablist"', html)
        self.assertNotIn("municipio.js", html)

    def test_la_tabla_del_registro_oficial_sigue_debajo_del_lienzo(self):
        """La tabla de capturas del RUD no desaparece: es el dato citable.
        Baja a `.zona-datos`, después del lienzo, que es donde el prototipo
        la dejó para no pelear el ancho con el mapa."""
        html = self.cali
        self.assertIn("Cómo avanza el registro oficial", html)
        self.assertIn("<table>", html)
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find("Cómo avanza el registro oficial"))
        zona = html.find('class="zona-datos"')
        self.assertGreater(zona, 0)
        self.assertGreater(html.find("Cómo avanza el registro oficial"), zona)

    def test_los_chips_nacen_ocultos_en_la_fila_de_vistas(self):
        """Son un filtro de capas: en Situación no hay capas. El prototipo
        los ponía en la misma fila que las pestañas, a la derecha."""
        html = self.cali
        tira = re.search(r'<div class="chips chips-mapa"[^>]*>', html)
        self.assertIsNotNone(tira)
        self.assertIn(" hidden", tira.group(0))
        vistas = html.find('class="vistas"')
        self.assertGreater(vistas, 0)
        self.assertGreater(tira.start(), vistas)
        self.assertLess(tira.start(), html.find('id="map-mun"'))
        js = (ROOT / "site" / "municipio.js").read_text(encoding="utf-8")
        self.assertNotIn("intro.hidden", js)
        self.assertNotIn('querySelector(".intro-mapa")', js)

    def test_el_css_mantiene_el_lienzo_en_flex_y_las_pestanas_en_fila(self):
        """El prototipo midió el lado a lado con flex. Si `.lienzo` vuelve a
        ser grid (portada) y gana por especificidad, `order` deja de aplicar
        y el mapa ya no convive con el panel. El tablist anidado —los chips
        no son pestañas— tiene que ser flex o los dos botones se apilan."""
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        vivo = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertIn(".lienzo.lienzo-mun{display:flex", vivo)
        self.assertIn('.vistas [role="tablist"]{display:flex', vivo)

    def test_en_movil_la_tabla_va_antes_que_el_mapa(self):
        """ (24-ago): se llega directo a la información. El prototipo ponía
        el mapa primero con `.marco-mapa{order:1}`; producción no invierte
        el DOM. Si esa regla vuelve, este test es el que avisa."""
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        vivo = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotIn(".lienzo-mun .marco-mapa{order:1", vivo)
        self.assertIn(".lienzo.lienzo-mun .panel{order:1", vivo)
        self.assertIn(".lienzo-mun .marco-mapa{order:2", vivo)

    def test_los_chips_ocultos_no_ocupan_sitio(self):
        """`.chips { display:flex }` anula el `[hidden]` del navegador: la
        tira se veía en Situación, donde no hay capas que filtrar. El
        atributo tiene que volver a esconder."""
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.chips\[hidden\]\s*\{\s*display:\s*none")

    def test_el_encabezado_de_la_ficha_comparte_eje_con_el_lienzo(self):
        """Fuera del tubo de 760 px: si las tarjetas van centradas y el panel
        arranca en `--eje`, la página tiene dos bordes izquierdos."""
        self.assertIn('class="contenido contenido-ficha"', self.cali)
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".contenido-ficha{", css)
        self.assertIn("padding-inline:var(--eje)", css)

    def test_la_grafica_entra_despues_del_h2_y_antes_de_la_tabla(self):
        """El prototipo lo midió: forma primero, cifra citable después.
        Cali tiene más de cinco capturas; si el SVG no está, la ficha sigue
        prometiendo una gráfica que no dibuja."""
        html = self.cali
        h2 = html.find("<h2>Cómo avanza el registro oficial</h2>")
        graf = html.find('class="grafico-rud-muni"')
        tabla = html.find("<table>", h2)
        self.assertGreater(h2, 0)
        self.assertGreater(graf, h2)
        self.assertGreater(tabla, graf)
        self.assertIn('id="registro"', html[h2 - 80:h2])
        self.assertIn('class="leyenda-graf"', html[graf:tabla])
        self.assertNotIn("La gráfica de evolución aparece a partir", html)

    def test_con_menos_de_cinco_capturas_no_hay_grafica(self):
        """Dos puntos no son tendencia: la ficha lo dice y no dibuja.
        Mutar Cali a tres capturas es el caso que el umbral tiene que
        cazar; si el SVG sale igual, el umbral no vigila nada."""
        d = copy.deepcopy(R.datos_ficha("Cali", self.ctx))
        d["serie"] = d["serie"][:3]
        self.assertEqual(R.grafico_rud_municipal(d["serie"], d["slug"]), "")
        html = R.render_ficha(d)
        self.assertNotIn('class="grafico-rud-muni"', html)
        self.assertIn("La gráfica de evolución aparece a partir", html)

    def test_el_primer_dia_no_inventa_una_barra_a_cero(self):
        """R3: sin captura previa el alta no existe. Un rect de altura 0
        diría que ese día no entró nadie."""
        serie = [(f"2026-08-{d:02d}", {"familias": 100 * i})
                 for i, d in enumerate(range(16, 22), start=1)]
        svg = R.grafico_rud_municipal(serie, "prueba")
        altas = re.findall(r'data-altas="([^"]+)"', svg)
        self.assertEqual(altas, ["100", "100", "100", "100", "100"])
        self.assertIn("sin captura anterior", svg)
        self.assertNotRegex(svg, r'fill="#[0-9A-Fa-f]')

    def test_una_baja_del_registro_se_pinta_y_no_se_esconde(self):
        """El prototipo hacía max(0, …) y recortaba las correcciones a la
        baja. R16 las enseña: el consolidado no retrocede, el gráfico sí
        cuenta lo que la fuente publicó ese día."""
        serie = [(f"2026-08-{d:02d}", {"familias": n})
                 for d, n in zip(range(16, 21), (100, 200, 180, 220, 250))]
        svg = R.grafico_rud_municipal(serie, "baja")
        self.assertIn('data-altas="-20"', svg)
        self.assertIn("var(--critical)", svg)

    def test_el_esquema_de_titulos_es_el_del_prototipo_sin_saltar_niveles(self):
        """H1 → panel → registro → prensa → lagunas → trazabilidad.
        Destacado y tarjetas van DEBAJO del lienzo (24-ago, frente al
        prototipo). Ningún H3 sin H2, y el H2 del panel va antes de los de
        zona-datos."""
        html = self.cali
        niveles = [int(n) for n in re.findall(r"<h([1-6])\b", html)]
        self.assertEqual(niveles[0], 1)
        for a, b in zip(niveles, niveles[1:]):
            self.assertLessEqual(b, a + 1, f"salto de h{a} a h{b}")
        h2s = re.findall(r"<h2>(.*?)</h2>", html)
        self.assertEqual(h2s[0], "Qué dice cada fuente")
        self.assertEqual(h2s[1:], [
            "Cómo avanza el registro oficial",
            "Qué publicó la prensa sobre Cali",
            "Qué no sabemos de Cali",
            "Fuentes y trazabilidad",
        ])
        self.assertLess(html.find("<h1>"), html.find("<h2>"))
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find('class="destacado"'))
        self.assertLess(html.find('class="lienzo lienzo-mun"'),
                        html.find('class="metric-strip"'))
        self.assertLess(html.find('class="destacado"'),
                        html.find("Cómo avanza el registro oficial"))
        self.assertLess(html.find('class="metric-strip"'),
                        html.find("Cómo avanza el registro oficial"))


class TestMarcadoDeLaFicha(unittest.TestCase):
    """El `Dataset` enriquecido de las 208 fichas: cuánto, de cuándo y de quién.

    Hasta hoy la ficha publicaba sus cifras solo como prosa en español, con los
    miles separados por punto: legible para una persona y no citable por una
    máquina. `variableMeasured` las convierte en pares (nombre, valor, unidad),
    `citation` dice de quién es cada una y `measurementTechnique` impide leer
    «inscritas» como «verificadas».
    """

    @classmethod
    def setUpClass(cls):
        # el contexto trae, si hace falta, el municipio sin registro sobre el
        # que se apoyan los dos guardianes de R3 de aquí abajo
        cls.sin_rud, cls.ctx = municipio_sin_rud(R.contexto())

    def _ld(self, nombre: str) -> dict:
        """El nodo `Dataset` tal como sale al HTML de esa ficha."""
        html = R.render_ficha(R.datos_ficha(nombre, self.ctx))
        datasets = datasets_ld(html)
        assert len(datasets) == 1, f"{nombre}: {len(datasets)} nodos Dataset"
        return datasets[0]

    def _medidas(self, ld: dict) -> dict:
        return {v["name"]: v for v in ld.get("variableMeasured") or []}

    def test_g1_lo_que_la_fuente_calla_no_se_publica_como_cero(self):
        """G1 · R3, sobre las 208. La mutación que debe morir es
        `"value": m.get(campo) or 0`: el JSON seguiría siendo válido, Google no
        se quejaría y un municipio sin registro publicaría que tiene cero
        familias damnificadas cuando lo que pasa es que el RUD aún no ha
        llegado.

        No se comprueba «ninguna vale cero» —un cero medido de verdad sí se
        publica—: se comprueba que la variable EXISTE si y solo si su campo de
        origen no es nulo."""
        campos = {"Familias inscritas en el RUD": "rud_familias",
                  "Personas inscritas en el RUD": "rud_personas",
                  "Viviendas destruidas declaradas en el RUD": "rud_viv_destruidas",
                  "Viviendas averiadas declaradas en el RUD": "rud_viv_averiadas",
                  "Población proyectada 2026 (DANE)": "poblacion_2026"}
        sin_rud = 0
        for m in self.ctx["municipios"]:
            nombre = m["municipio"]
            if not R.es_elegible(nombre, self.ctx):
                continue
            d = R.datos_ficha(nombre, self.ctx)
            ld = R.dataset_ficha(d, nombre, m["departamento"], "https://x/", "d")
            medidas = self._medidas(ld)
            for etiqueta, campo in campos.items():
                if m.get(campo) is None:
                    self.assertNotIn(etiqueta, medidas,
                                     f"{nombre}: {etiqueta} publicada sin dato")
                else:
                    self.assertIn(etiqueta, medidas, f"{nombre}: falta {etiqueta}")
                    self.assertIsNotNone(medidas[etiqueta]["value"])
            if m.get("rud_familias") is None:
                sin_rud += 1
        self.assertGreater(sin_rud, 0,
                           "sin un municipio sin RUD, este guardián no vigila nada")

    def test_la_ungrd_se_cita_aunque_el_municipio_no_tenga_registro(self):
        """Consultar el RUD y no encontrar al municipio es un hecho de esa
        fuente, y es justo el hallazgo que el proyecto existe para contar. La
        cita se queda; lo que desaparece son las cifras.

        El municipio lo elige `municipio_sin_rud`: hasta el 24-ago-2026 estaba
        escrito «Palmira» aquí, y el 25 Palmira entró en el registro."""
        ld = self._ld(self.sin_rud)
        self.assertIsNone(self.ctx["idx"][self.sin_rud].get("rud_familias"))
        self.assertNotIn("Familias inscritas en el RUD", self._medidas(ld))
        citas = [c["name"] for c in ld["citation"]]
        self.assertIn("Registro Único de Damnificados (RUD)", citas)

    def test_g4_las_citas_satelitales_son_espejo_de_satelites_con_dato(self):
        """Espejo, no «contiene»: mismo contenido y mismo orden. Citar a quien
        no miró este municipio le atribuye un trabajo que no hizo; callar a
        quien sí miró es R9 al revés."""
        for nombre in ("Cali", "Pereira", "Anserma", "Roldanillo", "Nóvita"):
            d = R.datos_ficha(nombre, self.ctx)
            m = self.ctx["idx"][nombre]
            esperado = [f for f, _ in R.satelites_con_dato(m, d["satelite"])]
            ld = R.dataset_ficha(d, nombre, m["departamento"], "https://x/", "d")
            nombres_sat = {s["nombre"] for s in R.SATELITES}
            citado = [c["name"] for c in ld["citation"] if c["name"] in nombres_sat]
            self.assertEqual(citado, esperado, f"{nombre}: citas satelitales")

    def test_r9_el_monitor_compila_y_las_fuentes_se_citan(self):
        """Si `creator` apuntara a la UNGRD publicaríamos que la UNGRD firma un
        documento que mezcla tres satélites y el DANE."""
        ld = self._ld("Cali")
        self.assertEqual(ld["creator"], {"@id": R.ORGANIZACION})
        self.assertEqual(ld["publisher"], {"@id": R.ORGANIZACION})
        publicadores = [c["publisher"]["name"] for c in ld["citation"]]
        self.assertIn("Unidad Nacional para la Gestión del Riesgo de Desastres "
                      "(UNGRD)", publicadores)
        for quien in publicadores:
            self.assertNotIn("datosdelterremoto", quien.lower())
            self.assertNotIn("Monitor de brechas", quien)

    def test_measurementTechnique_distingue_inscritas_de_verificadas(self):
        """Aquí no es decorativo: es lo único que impide que un motor
        generativo lea «11.826 familias inscritas» como «11.826 familias
        verificadas»."""
        tecnicas = " ".join(self._ld("Cali")["measurementTechnique"])
        self.assertIn("inscripciones tramitadas", tecnicas)
        self.assertIn("verificación posterior", tecnicas)
        self.assertIn("no verificación de daño en campo", tecnicas)
        self.assertIn("sin validar sobre el terreno", tecnicas)

    def test_cada_variable_lleva_su_valor_y_su_unidad(self):
        for nombre in ("Cali", "Palmira", "Nóvita"):
            ld = self._ld(nombre)
            for variable in ld.get("variableMeasured") or []:
                with self.subTest(municipio=nombre, variable=variable["name"]):
                    self.assertEqual(variable["@type"], "PropertyValue")
                    self.assertIsNotNone(variable.get("value"))
                    self.assertTrue(variable.get("unitText"))

    def test_ningun_recuento_se_publica_con_decimales(self):
        """`municipios.json` trae las familias como float. «11826.0 familias»
        insinúa una precisión decimal que un recuento de personas no tiene."""
        for nombre in ("Cali", "Roldanillo", "Pereira"):
            for variable in self._ld(nombre).get("variableMeasured") or []:
                if variable["unitText"] == "%":
                    continue
                with self.subTest(municipio=nombre, variable=variable["name"]):
                    self.assertIsInstance(variable["value"], int)

    def test_g3_la_proporcion_del_marcado_es_la_de_la_tarjeta(self):
        """Publicar 1,162 aquí y 1,16 en la tarjeta serían dos verdades, y cada
        una se ve bien por separado. Y una proporción diminuta pero real jamás
        se redondea a cero: un municipio con damnificados no puede leerse como
        municipio sin damnificados (R3)."""
        etiqueta = "Personas del RUD sobre la población proyectada 2026"
        vistos, minimo = 0, 1.0
        for m in self.ctx["municipios"]:
            nombre = m["municipio"]
            if m.get("tasa_rud_pct") is None or not R.es_elegible(nombre, self.ctx):
                continue
            d = R.datos_ficha(nombre, self.ctx)
            ld = R.dataset_ficha(d, nombre, m["departamento"], "https://x/", "d")
            valor = self._medidas(ld)[etiqueta]["value"]
            if m["tasa_rud_pct"] > 0:
                self.assertGreater(valor, 0, f"{nombre}: proporción real a cero")
            self.assertEqual(R.fmt(valor, 2), R.fmt(m["tasa_rud_pct"], 2),
                             f"{nombre}: el marcado y la tarjeta no dicen lo mismo")
            # …y sobre el HTML de verdad, que es lo que lee una persona. Sin
            # esto el guardián comparaba `fmt(valor,2)` contra
            # `fmt(tasa,2)` —dos veces la misma función, los dos «0»— y no veía
            # que la ficha de Pereira publicara «0%» de damnificados teniendo
            # cuatro personas inscritas, mientras la tabla decía «<0,1 %» y el
            # marcado 0.0008. Tres verdades para la misma proporción.
            if m["tasa_rud_pct"] > 0:
                html = R.render_ficha(d)
                self.assertNotIn(">0%<", html,
                                 f"{nombre}: publica «0%» con damnificados reales")
                self.assertNotIn("0% de la población", html,
                                 f"{nombre}: publica «0% de la población»")
            vistos += 1
            minimo = min(minimo, m["tasa_rud_pct"])
        self.assertGreater(vistos, 100)
        self.assertLess(minimo, 0.005,
                        "sin una proporción diminuta, la mitad del test no vigila")

    def test_g3_las_cifras_del_marcado_estan_en_las_tarjetas(self):
        """Nada se calcula solo para el marcado: cada cifra citable está
        también escrita en la página que la publica."""
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        ini = html.find('class="metric-strip"')
        fin = html.find("Cómo avanza el registro oficial")
        self.assertGreater(ini, 0)
        tira = html[ini:fin]
        medidas = self._medidas(datasets_ld(html)[0])
        for etiqueta in ("Familias inscritas en el RUD",
                         "Personas inscritas en el RUD",
                         "Viviendas averiadas declaradas en el RUD",
                         "Población proyectada 2026 (DANE)"):
            self.assertIn(R.fmt(medidas[etiqueta]["value"]), tira,
                          f"{etiqueta} no está en la tira de tarjetas")

    def test_la_fecha_es_la_del_dato_y_la_cobertura_se_cierra_en_ella(self):
        """Una cobertura abierta con `dateModified` de la corrida invita a leer
        «100.231 familias a día de hoy» — literalmente la confusión que el sello
        corrige en la prosa de esta misma página."""
        d = R.datos_ficha("Cali", self.ctx)
        fecha = R._solo_fecha(d["generado"])
        ld = self._ld("Cali")
        self.assertEqual(ld["dateModified"], fecha)
        self.assertEqual(ld["temporalCoverage"], f"2026-08-10/{fecha}")
        # y es la misma que la ficha publica como «Fecha de las cifras»
        self.assertIn(R.fecha_larga(fecha),
                      R.render_ficha(d))

    def test_sin_fecha_del_dato_no_se_inventa_ninguna_de_las_dos(self):
        d = copy.deepcopy(R.datos_ficha("Cali", self.ctx))
        d["generado"] = ""
        ld = R.dataset_ficha(d, "Cali", "Valle del Cauca", "https://x/", "d")
        self.assertNotIn("dateModified", ld)
        self.assertEqual(ld["temporalCoverage"], "2026-08-10/..")

    def test_g2_el_dataset_de_la_ficha_no_anida_otro_ni_se_queda_sin_nombre(self):
        for nombre in ("Cali", "Palmira", "Cartago"):
            html = R.render_ficha(R.datos_ficha(nombre, self.ctx))
            datasets = datasets_ld(html)
            self.assertEqual(len(datasets), 1, f"{nombre}: Dataset anidado")
            for campo in ("name", "description"):
                self.assertTrue(datasets[0].get(campo), f"{nombre}: sin {campo}")

    def test_g6_toda_url_del_marcado_de_la_ficha_es_absoluta(self):
        """Un indexador de datasets extrae el bloque JSON-LD como JSON suelto,
        sin la URL base del documento: una ruta relativa allí no apunta a nada."""
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        for bloque in bloques_ld(html):
            for nodo in nodos_ld(bloque):
                for campo in ("contentUrl", "url", "logo", "@id", "item"):
                    valor = nodo.get(campo)
                    if isinstance(valor, str):
                        self.assertTrue(R._url_absoluta(valor),
                                        f"{campo} relativo: {valor}")

    def test_el_evidencia_json_se_ofrece_solo_donde_existe(self):
        """Anunciar una descarga que devuelve 404 es peor que no
        anunciarla. El build solo escribe `evidencia.json` donde hay puntos."""
        con = self._ld("Cali")
        sin_evidencia = ficha_del_corpus(
            self.ctx, lambda f: not f["hay_evidencia"], SIN_EVIDENCIA_AGOTADA)
        sin = self._ld(sin_evidencia["muni"]["municipio"])
        self.assertTrue(any("evidencia.json" in x["contentUrl"]
                            for x in con["distribution"]))
        self.assertFalse(any("evidencia.json" in x["contentUrl"]
                             for x in sin["distribution"]))

    def test_el_grafico_no_anade_un_dataset_ni_duplica_ids(self):
        """El SVG visualiza cifras que ya están en variableMeasured y en
        la tabla. Un Dataset extra, o un @id que apunte al title del
        gráfico, inventaría un recurso que no se puede citar. Los tres
        bloques JSON-LD de la ficha ya estaban: identidad, Dataset y
        migas."""
        html = R.render_ficha(R.datos_ficha("Cali", self.ctx))
        bloques = bloques_ld(html)
        self.assertEqual(len(bloques), 3)
        self.assertEqual(len(datasets_ld(html)), 1)
        self.assertIn("@graph", bloques[0])
        self.assertEqual(bloques[1]["@type"], "Dataset")
        self.assertEqual(bloques[2]["@type"], "BreadcrumbList")
        embebido = json.dumps(bloques, ensure_ascii=False)
        self.assertNotIn("graf-rud-", embebido)
        self.assertIn('id="graf-rud-cali-t"', html)
        self.assertIn('id="graf-rud-cali-d"', html)


class TestR5NoPrometeLoQueYaNoHace(unittest.TestCase):
    """Ninguna superficie promete la protección que R5 retiró el 24-ago-2026.

    `chatmap.py::_coordenada_publica` dejó de redondear ese día —redondear a
    ~110 m no protegía nada, porque ChatMap publica la coordenada exacta en su
    endpoint abierto, y sí engañaba a quien reporta—. Los globos de `app.js` y
    `municipio.js` siguieron diciendo «coordenada redondeada a unos 110 metros»
    durante un día, y `CONTRIBUTING.md`, `publish.py`, `verify_citizen.py` y
    `LIMITACIONES.md` un poco más. El `README.md` aguantó todavía otro repaso:
    lo decía con otras palabras y en presente, tres líneas debajo de una frase
    ya corregida.

    La lección que fija este guardián: **un cambio de regla no está terminado
    hasta que se persiguen sus literales publicados**, y son más superficies de
    las que uno recuerda. Si algún día R5 vuelve a cambiar, este test cae y
    enseña la lista entera.
    """

    SUPERFICIES = ("site/app.js", "site/municipio.js", "site/index.html",
                   "README.md", "CONTRIBUTING.md", "docs/LIMITACIONES.md",
                   "ingest/publish.py", "ingest/verify_citizen.py",
                   "ingest/sources/chatmap.py", "CLAUDE.md")

    def test_ninguna_superficie_promete_una_coordenada_redondeada(self):
        # el patrón busca la PROMESA, no la palabra: los comentarios que
        # explican por qué se retiró el redondeo tienen que poder existir.
        #
        # La cuarta alternativa se añadió después, y enseña la validación por mutación a escala
        # pequeña: las tres primeras se validaron contra las redacciones que ya
        # se conocían, y el `README.md` decía lo mismo de otra forma —«el
        # redondeo ES una capa de prudencia en la presentación»— tres líneas
        # debajo de una frase ya corregida. Ni casaba el patrón ni estaba el
        # fichero en la lista: el bloque se contradecía a sí mismo y ningún
        # guardián lo veía. Lo que se persigue aquí es el VERBO en presente —
        # afirmar que el redondeo sigue vigente—, no la palabra «redondeo», que
        # tiene que poder contarse en pasado en todas partes.
        #
        # Sigue sin cubrir una redacción futura en una quinta forma. Un patrón
        # es una red de arrastre, no una demostración: si R5 vuelve a moverse,
        # la lista de superficies se revisa a mano y este comentario dice por qué.
        promesa = re.compile(
            r"coordenada[s]?\s+(?:públicas?\s+)?redondead|"
            r"redondead\w*\s+a\s*~?\s*110|"
            r"lat_pub/lon_pub\s*\(redondead|"
            r"el\s+redondeo\s+(?:es|sigue|aporta|protege|añade)\b",
            re.I)
        for fichero in self.SUPERFICIES:
            ruta = ROOT / fichero
            if not ruta.exists():
                continue
            with self.subTest(fichero=fichero):
                hallado = promesa.search(ruta.read_text(encoding="utf-8"))
                self.assertIsNone(
                    hallado,
                    f"{fichero} sigue prometiendo una coordenada redondeada "
                    f"(«{hallado.group(0) if hallado else ''}»), y el código "
                    "dejó de redondear el 24-ago-2026")

    def test_el_codigo_de_verdad_no_reposiciona(self):
        """Y el guardián se ancla a lo que hace el código, no solo a los textos:
        si alguien vuelve a redondear, la lista de arriba deja de ser falsa y
        este test es el que avisa de que hay que revisarla entera."""
        sys.path.insert(0, str(ROOT / "ingest"))
        from sources.chatmap import _coordenada_publica
        for valor in (3.451234, -76.987654, 0.0, 10.5):
            with self.subTest(valor=valor):
                self.assertEqual(_coordenada_publica(valor), valor,
                                 "el monitor volvió a reposicionar la coordenada")


class TestLaSerieEsDeEsteMunicipioYNoDeSuVecino(unittest.TestCase):
    """El RUD nombra los municipios a su manera y la ficha tiene que emparejar
    sin equivocarse de pueblo.

    Siete fichas con cifras del RUD se publicaban sin su serie porque la
    igualdad exacta no casaba («Buga» ≠ «GUADALAJARA DE BUGA», «Riosucio
    (Caldas)» ≠ «RIOSUCIO»). Al relajar el emparejado aparecieron los dos
    errores contrarios, y son peores que la ausencia: «Atrato» se quedó con la
    serie de «EL CARMEN DE ATRATO» (277 familias donde su catálogo dice 266), y
    «Argelia (Cauca)» con la de la Argelia del Valle (851 frente a 1). Es R10
    entero: límite de palabra, la exacta manda, y el departamento desempata.
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def test_ninguna_serie_es_la_de_otro_municipio(self):
        """La prueba que de verdad importa, sobre las 208: la última cifra de
        la serie tiene que ser la que el catálogo publica para ESE municipio."""
        malos = []
        for m in self.ctx["municipios"]:
            nombre = m["municipio"]
            if not R.es_elegible(nombre, self.ctx):
                continue
            serie = R.datos_ficha(nombre, self.ctx).get("serie") or []
            if not serie:
                continue
            fam, esperado = serie[-1][1].get("familias"), m.get("rud_familias")
            if fam is not None and esperado is not None and abs(fam - esperado) > 0.5:
                malos.append(f"{nombre}: serie {fam} vs catálogo {esperado}")
        self.assertFalse(malos, "fichas con la serie de otro municipio: " + "; ".join(malos[:5]))

    def test_ninguna_ficha_con_cifras_del_rud_se_queda_sin_serie(self):
        """El silencio que motivó el arreglo: si el catálogo le da familias,
        la ficha tiene que poder contar su evolución."""
        mudas = [m["municipio"] for m in self.ctx["municipios"]
                 if R.es_elegible(m["municipio"], self.ctx) and m.get("rud_familias")
                 and not (R.datos_ficha(m["municipio"], self.ctx).get("serie"))]
        self.assertFalse(mudas, f"fichas con familias y sin serie: {mudas[:6]}")

    def test_el_nombre_corto_no_se_come_al_vecino_largo(self):
        """«Atrato» y «El Carmen de Atrato» son dos municipios del Chocó, y el
        segundo contiene al primero. La coincidencia exacta tiene que ganar."""
        # Las cifras NO se fijan a mano: se derivan del catálogo. La primera
        # versión escribió 266, 277, 206 y 10, y el snapshot del día siguiente
        # las dejó caducadas — un test que hay que actualizar cada mañana acaba
        # relajándose. Lo invariante es que la serie sea la de SU municipio.
        for nombre in ("Atrato", "El Carmen de Atrato", "Buga", "Bugalagrande"):
            with self.subTest(municipio=nombre):
                d = R.datos_ficha(nombre, self.ctx)
                serie = d.get("serie") or []
                self.assertTrue(serie, f"{nombre} se quedó sin serie")
                self.assertAlmostEqual(serie[-1][1]["familias"],
                                       d["muni"]["rud_familias"], places=1)

    def test_un_homonimo_toma_el_de_su_departamento(self):
        """«Argelia (Cauca)» tiene 1 familia y «Argelia» (Valle) 851. Sin el
        desempate por departamento, la ficha del Cauca publicaba las 851."""
        for nombre in ("Argelia (Cauca)", "Bolívar (Cauca)", "Riosucio (Chocó)",
                       "Balboa (Cauca)"):
            with self.subTest(municipio=nombre):
                d = R.datos_ficha(nombre, self.ctx)
                serie = d.get("serie") or []
                self.assertTrue(serie, f"{nombre} se quedó sin serie")
                self.assertAlmostEqual(serie[-1][1]["familias"],
                                       d["muni"]["rud_familias"], places=1)


class TestLaBrechaDiaADia(unittest.TestCase):
    """El gráfico de la portada, que dejó de ser el volumen y pasó a ser la brecha.

    Se comprueba sobre una serie inventada y no sobre el dato del día: lo que
    se vigila es la REGLA —dónde arranca el eje y qué hace la línea donde no
    hay captura—, no una cifra que se mueve cada mañana."""

    def ctx_con(self, serie_rud, entregas=(), unosat=(), reportes=()):
        """Un contexto mínimo con las tres miradas gobernadas desde el test."""
        municipios = [
            {"municipio": "Manizales", "departamento": "Caldas", "lat": 5.07,
             "lon": -75.52, "unosat_fecha_imagen": u} for u in unosat]
        return {
            "monitor": {"entregas": [{"aoi": a, "fecha": f} for a, f in entregas]},
            "municipios": municipios,
            "chatmap": [{"properties": {"time": t}, "geometry": None}
                        for t in reportes],
            "rud": {"serie": [{"fecha": f, "municipios": n} for f, n in serie_rud]},
        }

    def test_el_eje_arranca_en_la_primera_mirada_no_en_la_primera_captura(self):
        """Los satélites miraron del 11 al 14 y el monitor no capturó el RUD
        hasta el 16. Recortando la serie por el registro, la línea satelital
        salía plana en cero y desaparecía del dibujo la entrada de los tres
        servicios — que es justo lo que el gráfico existe para enseñar."""
        serie = R.serie_de_la_brecha(self.ctx_con(
            serie_rud=[("2026-08-16", 75), ("2026-08-17", 90)],
            entregas=[("Cali Center", "2026-08-12")]))
        self.assertEqual(serie[0]["fecha"], "2026-08-12",
                         "el eje empieza después de que el satélite mirara")
        self.assertEqual(serie[-1]["sat"], 1,
                         "la mirada anterior a la primera captura no se cuenta")

    def test_antes_de_la_primera_captura_el_registro_no_vale_cero(self):
        """R3 en el eje: antes de capturar no hay «cero municipios inscritos»,
        hay ausencia de dato. Un cero ahí diría que nadie estaba registrado."""
        serie = R.serie_de_la_brecha(self.ctx_con(
            serie_rud=[("2026-08-16", 75)],
            entregas=[("Cali Center", "2026-08-12")]))
        previos = [d for d in serie if d["fecha"] < "2026-08-16"]
        self.assertTrue(previos, "el fixture no cubre el tramo sin captura")
        self.assertTrue(all(d["rud"] is None for d in previos),
                        f"hay un cero inventado: {[d['rud'] for d in previos]}")

    def test_la_linea_del_registro_se_corta_en_el_hueco(self):
        """Y el dibujo tiene que decir lo mismo que la serie: la traza del RUD
        empieza donde empieza el dato. Con una `polyline` —que une todos los
        puntos— el hueco se dibujaba como una caída al suelo."""
        svg = R.grafico_brecha(self.ctx_con(
            serie_rud=[("2026-08-16", 75), ("2026-08-17", 90)],
            entregas=[("Cali Center", "2026-08-12")]))
        traza = re.search(r'<path d="([^"]+)" fill="none" stroke="var\(--s8\)"', svg)
        self.assertIsNotNone(traza, "la línea del registro ya no es una traza")
        self.assertEqual(traza.group(1).count("M"), 1,
                         "la traza no arranca una sola vez")
        # cinco días en el eje (12 a 17, sin el 15 que no tiene nada) y solo dos
        # con captura: la traza no puede tener un vértice por día
        self.assertEqual(traza.group(1).count("L"), 1,
                         "la traza une puntos que no tienen dato")

    def test_el_grafico_narra_su_serie_en_prosa(self):
        """El `<desc>` es lo único del gráfico que puede leer un lector de
        pantalla o citar un modelo. Sin él, el SVG es un dibujo mudo."""
        svg = R.grafico_brecha(self.ctx_con(
            serie_rud=[("2026-08-16", 75), ("2026-08-17", 90)],
            entregas=[("Cali Center", "2026-08-12")]))
        desc = re.search(r"<desc[^>]*>(.*?)</desc>", svg, re.S)
        self.assertIsNotNone(desc, "el gráfico no narra nada")
        texto = desc.group(1)
        self.assertIn("90 municipios con damnificados inscritos", texto)
        self.assertIn("Copernicus publica Cali", texto)
        # El invariante real: **antes de su primera captura, el registro no se
        # menciona**. Ni como 0 ni como raya: antes del 16 no vale cero, vale
        # nada (R3), y este `<desc>` es lo único del gráfico que puede leer un
        # lector de pantalla.
        #
        # Dos intentos fallidos antes de este, y los dos son la lección del
        # día: `assertNotIn("0 municipios…")` casaba dentro de «90 municipios…»
        # —R10 aplicada a un número—, y arreglarlo con un límite de dígito dejó
        # un guardián que pasaba en verde con el fallo puesto, porque con `None`
        # el texto dice «—» y no «0». Se comprueba por FRASE de día, que es
        # donde vive el invariante.
        for dia in texto.split(". "):
            if dia.startswith(("10 de agosto", "11 de agosto", "12 de agosto",
                               "13 de agosto", "14 de agosto", "15 de agosto")):
                self.assertNotIn("damnificados inscritos", dia,
                                 f"narra el registro antes de su primera "
                                 f"captura: «{dia}»")

    def test_sin_serie_del_registro_no_se_dibuja_un_lienzo_vacio(self):
        """Donde falta el dato se calla, y se dice por qué."""
        salida = R.grafico_brecha(self.ctx_con(serie_rud=[]))
        self.assertNotIn("<svg", salida)
        self.assertIn("serie", salida)


class TestPiezasDeLaPortada(unittest.TestCase):
    """Los generadores nuevos de la portada, sobre el dato real del artefacto.

    Aquí no se comprueban cifras exactas —se mueven cada corrida— sino que
    cada pieza escribe una ORACIÓN ENTERA: si algún día el dato falta, la
    portada tiene que seguir leyéndose, no quedarse con una raya huérfana."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()

    def test_la_entradilla_sin_ninguna_cifra_sigue_siendo_una_frase(self):
        vacio = dict(self.ctx, monitor={}, municipios=[])
        salida = R.entradilla_portada(vacio)
        self.assertTrue(salida.startswith("<p>") and salida.endswith("</p>"))
        self.assertNotIn("<b>", salida, "publica un hueco donde iba la cifra")
        self.assertIn("monitor", salida)

    def test_el_parrafo_de_la_brecha_publica_la_buena_noticia_si_se_cierra(self):
        """R11: que la brecha se cierre es una noticia, no un hueco. El día que
        no quede ningún municipio sin mirar, la frase dice lo contrario."""
        cerrado = dict(self.ctx, municipios=[])
        self.assertIn("se ha cerrado", R.parrafo_brecha_portada(cerrado))
        # La rama abierta no se comprueba ya por una frase —decía «es la
        # brecha», la fórmula que se retiró el 25-ago-2026— sino por lo que la
        # distingue: no anuncia el cierre y publica cuántos municipios faltan.
        abierta = R.parrafo_brecha_portada(self.ctx)
        self.assertNotIn("se ha cerrado", abierta)
        self.assertIn(R.fmt(len(R.sin_mirada_satelital(self.ctx))), abierta)

    def test_el_panel_es_un_cuadro_de_honor_y_enlaza_a_las_fichas(self):
        """Criterio de: la lista son los municipios mejor documentados, no
        un índice de los 208. Y cada fila es un ENLACE, no un botón: sin
        JavaScript, un botón prerenderizado no lleva a ninguna parte."""
        salida = R.panel_portada(self.ctx)
        self.assertIn('<ol class="lista-mun">', salida)
        self.assertNotIn("<button", salida, "publica controles muertos")
        self.assertIn('href="/municipio/', salida)
        self.assertLess(salida.count("<li>"), len(self.ctx["municipios"]),
                        "la lista es el índice completo, no un cuadro de honor")

    def test_las_cuatro_miradas_se_comparan_en_municipios(self):
        """La unidad común es el municipio: es lo único que las cuatro fuentes
        miden igual. En edificios contra familias contra reportes, la
        comparación parecía decir que Copernicus cubre más que el registro
        oficial, y es al revés."""
        salida = R.tarjetas_fuentes_portada(self.ctx)
        self.assertEqual(salida.count('class="fuente"'),
                         salida.count("</b> municipios")
                         + salida.count("fuente-nd"),
                         "hay una mirada sin su cifra en la unidad común")

    def test_las_alertas_dicen_su_nivel_con_palabras_y_no_solo_con_color(self):
        salida = R.alertas_portada(self.ctx)
        self.assertIn("<li>", salida)
        self.assertNotIn("<ul", salida, "el generador se sale de su contenedor")
        self.assertRegex(salida, r'<span class="badge"[^>]*>(alta|media|info)</span>')

    def test_la_fecha_de_las_alertas_es_absoluta(self):
        """esta página se releerá dentro de años; «hoy» no dice nada."""
        salida = R.fecha_alertas_portada(self.ctx)
        self.assertNotIn("hoy", salida.lower())
        self.assertRegex(salida, r"de \d{4}\.$")

    def test_la_rampa_de_la_ausencia_es_espejo_de_app_js(self):
        """La rampa vive en dos superficies a propósito: el mapa pinta con ella
        196 anillos en el navegador y la leyenda la necesita en el build. Se
        comparan EJECUTANDO las dos, no buscando un comentario en el fuente —
        un guardián de `assertIn` sobre el texto pasa en verde con la regla
        invertida."""
        if not NODE:
            self.skipTest("sin node no se puede ejecutar la copia del navegador")
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        cuerpo = re.search(
            r"const colorAusencia = \(mmi\) => \{(.*?)\n  \};", js, re.S)
        self.assertIsNotNone(cuerpo, "colorAusencia ya no está en app.js")
        guion = ("const css = () => 'var(--muted)';"
                 "const colorAusencia = (mmi) => {" + cuerpo.group(1) + "};"
                 "console.log(JSON.stringify([null,3,4,5,6,7,8]"
                 ".map(colorAusencia)));")
        del_navegador = json.loads(subprocess.run(
            [NODE, "-"], input=guion, capture_output=True, text=True,
            timeout=30, check=True).stdout)
        del_build = [R._color_ausencia(m) for m in (None, 3, 4, 5, 6, 7, 8)]
        self.assertEqual(del_build, del_navegador)


class TestElMarcadoDeLaPortada(unittest.TestCase):
    """Los criterios de diseño que dio sobre la portada, con su guardián.

    Un comentario en mayúsculas no es un guardián. Estas tres decisiones
    —ningún plegable dentro de otro, sin emoticonos en los títulos y el mapa a
    la altura del panel— se podían deshacer sin que nada se quejara."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

    def test_ningun_plegable_dentro_de_otro(self):
        """Dos clics para llegar al texto, y un plegable cerrado dentro de otro
        que nadie va a abrir. El sitio publicado no tiene ni un caso de
        anidamiento; la portada no puede estrenarlo."""
        # Sin los comentarios: el documento explica en uno de ellos por qué «un
        # <details> cerrado sigue estando en el HTML servido», y contar esa
        # mención como etiqueta daba un plegable abierto que no existe. El
        # guardián acusaba al HTML de un fallo que estaba en el guardián.
        marcado = re.sub(r"<!--.*?-->", " ", self.html, flags=re.S)
        profundidad, maxima = 0, 0
        for etiqueta in re.findall(r"</?details\b", marcado):
            profundidad += 1 if etiqueta == "<details" else -1
            maxima = max(maxima, profundidad)
        self.assertEqual(profundidad, 0, "hay un <details> sin cerrar")
        self.assertEqual(maxima, 1, "hay un plegable dentro de otro")

    def test_sin_emoticonos_en_los_titulos_de_seccion(self):
        """El plegable ya se anuncia con su triángulo: el icono desalinea el
        título respecto a los demás y un lector de pantalla lo lee en voz alta."""
        titulos = re.findall(r"<summary[^>]*>(.*?)</summary>", self.html, re.S)
        titulos += re.findall(r"<h([12])[^>]*>(.*?)</h\1>", self.html, re.S)
        planos = [re.sub(r"<[^>]+>", "", t if isinstance(t, str) else t[1])
                  for t in titulos]
        self.assertTrue(planos, "no se ha leído ningún título")
        for texto in planos:
            self.assertFalse(
                any(ord(c) > 0x2100 for c in texto),
                f"un título de sección lleva un pictograma: {texto.strip()[:60]}")

    def test_el_mapa_y_el_panel_son_hermanos_del_lienzo(self):
        """«El mapa a la altura del panel con todos sus datos, sin scroll
        interno» solo es posible si son hermanos de la misma rejilla. Con el
        panel dentro del mapa, o con la tabla dentro del panel, no lo es."""
        lienzo = re.search(r'<main id="mapa"([^>]*)>(.*?)</main>', self.html, re.S)
        self.assertIsNotNone(lienzo, "la portada ya no tiene su lienzo")
        self.assertIn("lienzo", lienzo.group(1), "el lienzo perdió su clase")
        self.assertIn('<div id="map">', lienzo.group(2))
        self.assertIn('data-gen="portada-panel"', lienzo.group(2))
        self.assertNotIn("<table", lienzo.group(2),
                         "la tabla ha vuelto al panel y el mapa no cabe a su lado")

    def test_app_js_ya_no_dibuja_lo_que_escribe_el_build(self):
        """dos superficies pintando lo mismo divergen. Al portar una pieza
        al build, la del navegador no se deja «por si acaso» — se borra."""
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        # `timeline` y `crono-banda` entran en la fase 6c, con la mudanza de la
        # cronología a referencia.html: eran lo último que este fichero
        # dibujaba aparte del mapa.
        for id_contenedor in ("leyenda", "fuentes-cards", "colombia-acts",
                              "alerts", "nota-rud-desde", "nota-sin-registro",
                              "chart", "timeline", "crono-banda"):
            self.assertNotIn(f'getElementById("{id_contenedor}")', js,
                             f"el navegador vuelve a rellenar #{id_contenedor}")


class TestChipsDeLaPortada(unittest.TestCase):
    """Los chips que encienden y apagan las cinco capas del mapa de la portada.

    Tres criterios del proyecto, y cada uno con su guardián porque cada uno ya se ha
    entendido al revés alguna vez:

    1. **Cuentan MUNICIPIOS, no puntos.** En edificios, Copernicus parecía
       cubrir más que el registro oficial cuando es justo al contrario.
    2. **Un chip es una acción**: `<button>` con `aria-pressed`, no una
       `.badge`, que solo rotula.
    3. **Filtran el MAPA; la lista del panel NO cambia.** El panel es un cuadro
       de honor y una puerta de entrada, no un índice.
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = R.contexto()
        cls.html = R.chips_portada(cls.ctx)
        cls.js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

    def _chips(self, html: str) -> list:
        """(capa, número escrito) de cada chip de la tira."""
        return [(m.group(1), m.group(2)) for m in re.finditer(
            r'<button[^>]*data-capa="([^"]+)"[^>]*>.*?'
            r'<span class="n">([\d.,]+)</span>', html, re.S)]

    def test_hay_un_chip_por_capa_del_mapa_y_ninguno_mas(self):
        """La tira y `app.js` son superficies espejo: el build emite un chip por
        capa con municipios y `app.js` registra esa capa con la misma clave. Si
        divergen, la portada publica un chip que no acciona nada —el control
        muerto que el criterio prohíbe— o una capa que ningún chip apaga."""
        declaradas = {c for c, _ in R.capas_portada()}
        registradas = set(re.findall(r'conChip\("([^"]+)"', self.js))
        self.assertEqual(
            declaradas, registradas,
            "las claves de `capas_portada()` y las que `app.js` registra con "
            "`conChip` han dejado de ser las mismas: uno de los dos lados "
            "publica una capa que el otro no conoce")
        cuentas = R._municipios_por_capa(self.ctx)
        self.assertEqual({c for c, _ in self._chips(self.html)},
                         {c for c in declaradas if cuentas.get(c)},
                         "hay chip donde no hay municipios, o al revés")

    def test_el_numero_del_chip_cuenta_municipios_y_no_puntos(self):
        """Criterio de. Se mide contra las DOS cifras: la de municipios tiene
        que salir y la de puntos tiene que NO salir, porque un test que solo
        comprobara la primera pasaría igual el día que alguien vuelva a contar
        edificios en un municipio con un solo punto."""
        cuentas = R._municipios_por_capa(self.ctx)
        puntos = {"copernicus": len(self.ctx["damage"]),
                  "unosat": len(self.ctx["unosat"]),
                  "sertit": len(self.ctx["sertit"]),
                  "ciudadanos": len(self.ctx["chatmap"])}
        total = len(self.ctx["municipios"])
        for capa, escrito in self._chips(self.html):
            self.assertEqual(escrito, R.fmt(cuentas[capa]),
                             f"{capa}: el chip promete {escrito}")
            self.assertLessEqual(
                cuentas[capa], total,
                f"{capa}: {cuentas[capa]} supera los {total} municipios del "
                "catálogo, así que no está contando municipios")
            if capa in puntos:
                self.assertNotEqual(
                    escrito, R.fmt(puntos[capa]),
                    f"{capa}: el chip escribe los {puntos[capa]} PUNTOS de la "
                    "capa. Debe contar municipios: es la única unidad en que "
                    "las cinco cifras se pueden comparar entre sí")

    def test_la_misma_capa_se_llama_igual_en_la_portada_y_en_la_ficha(self):
        """Las dos tiras son superficies hermanas: la de la portada y la de
        las 252 fichas. Llegaron a decir «Reportes ciudadanos» y «Reportes de la
        comunidad» de la MISMA capa, y un lector que pasa de una a otra tiene
        que reconocerla. Se comprueba sobre las claves compartidas, no sobre una
        lista escrita aquí: la portada tiene una capa que la ficha no («Solo en
        el RUD») y la ficha una que la portada no («Zonas analizadas»)."""
        portada = dict(R.capas_portada())
        ficha = dict(R.capas_evidencia())
        comunes = set(portada) & set(ficha)
        self.assertTrue(comunes, "las dos tiras han dejado de compartir capa")
        for clave in sorted(comunes):
            self.assertEqual(
                portada[clave], ficha[clave],
                f"la capa «{clave}» se llama «{portada[clave]}» en la portada y "
                f"«{ficha[clave]}» en la ficha: el mismo dato con dos nombres "
                "en dos superficies hermanas es la copia que diverge")

    def test_cada_chip_dice_con_todas_sus_palabras_lo_que_enciende(self):
        """El rótulo de una pastilla de 12 px no cabe con la salvedad, y sin
        ella «Solo en el RUD» se lee como «menos daño» cuando lo que dice es
        «nadie lo ha mirado» (R3). Cada chip lleva su `title`, y el de la
        ausencia tiene que desmentir esa lectura explícitamente."""
        for clave, _rotulo in R.capas_portada():
            self.assertIn(clave, R.QUE_ENCIENDE,
                          f"la capa «{clave}» no explica qué enciende")
        self.assertIn("nadie los ha mirado", R.QUE_ENCIENDE["ausencia"],
                      "el chip de la ausencia no desmiente la lectura de «sin "
                      "daño», que es la única que su rótulo corto permite")
        for _clave, _n in self._chips(self.html):
            pass
        self.assertEqual(
            self.html.count('title="'), len(self._chips(self.html)),
            "hay chips sin `title`: el rótulo corto se queda solo")

    def test_el_chip_de_la_ausencia_promete_los_puntos_que_el_mapa_PINTA(self):
        """La trampa de los «36 en portada, 43 en su propia tabla», otra vez.

        `municipios_mapa.json` se publica en su propia corrida y puede ir por
        detrás del catálogo: el 24-ago-2026 traía 196 municipios cuando la lista
        viva ya daba 240, porque el RUD había crecido dos días. Un chip contado
        sobre la lista viva encendía una capa de 196 puntos prometiendo 240.

        El chip cuenta lo que se PINTA. El párrafo de debajo del mapa sigue
        diciendo los 240 y hace bien: cuenta un hecho del registro, no lo
        dibujado, y la distancia entre las dos cifras es la brecha que el sitio
        existe para medir. Lo que no puede pasar es que un CONTROL del mapa
        prometa más de lo que su capa enseña.
        """
        capa = json.loads((ROOT / "data/public/municipios_mapa.json")
                          .read_text(encoding="utf-8"))
        pintados = sum(1 for m in capa["items"]
                       if m.get("lat") is not None and m.get("lon") is not None)
        chips = dict(self._chips(self.html))
        self.assertEqual(
            chips.get("ausencia"), R.fmt(pintados),
            f"el chip de la ausencia promete {chips.get('ausencia')} y el mapa "
            f"pinta {pintados} puntos")
        # y el guardián de sí mismo: si las dos cifras coincidieran por
        # casualidad, este test daría verde sin comprobar nada. Se mide contra
        # la lista viva para que la divergencia, cuando exista, se vea.
        vivos = len(R.sin_mirada_satelital(self.ctx))
        if vivos != pintados:
            self.assertNotEqual(
                chips.get("ausencia"), R.fmt(vivos),
                f"el chip volvió a contar la lista viva ({vivos}) en vez de los "
                f"{pintados} puntos que su capa dibuja")

    def test_un_chip_es_una_accion(self):
        """Criterio de: `<button>` con `aria-pressed`. Una pastilla que
        rotula y no acciona es una `.badge`."""
        self.assertTrue(self.html, "la portada se ha quedado sin chips")
        for pastilla in re.findall(r'<[a-z]+[^>]*class="chip[\s"][^>]*>', self.html):
            self.assertTrue(pastilla.startswith("<button"),
                            f"un chip que no es botón: {pastilla}")
            self.assertIn("aria-pressed=", pastilla,
                          f"un chip sin estado anunciado: {pastilla}")

    def test_los_chips_filtran_el_mapa_y_no_tocan_la_lista(self):
        """Criterio de, y se entendió al revés una vez. El manejador del clic
        solo puede hablarle al mapa: si toca `#panel`, `.lista-mun` o `#tabla`,
        el cuadro de honor deja de ser un cuadro de honor."""
        manejador = re.search(
            r'function conectarChips\(\).*?\n  \}\)\(\);', self.js, re.S)
        self.assertIsNotNone(manejador, "no se encuentra el conectador de chips")
        for prohibido in ("#panel", "lista-mun", "#tabla", "getElementById(\"panel\")"):
            self.assertNotIn(
                prohibido, manejador.group(0),
                f"el clic de un chip toca «{prohibido}»: los chips filtran el "
                "MAPA y la lista del panel no cambia")

    def test_el_marcador_de_la_tira_es_uno_de_los_que_el_inyector_reconoce(self):
        """El inyector solo rellena `<tbody>`, `<ul>`, `<span>` y `<section>`.

        Con un `<div class="chips" data-gen="portada-chips">` el build no
        encuentra el marcador y se cae — que es lo que hizo la primera vez. El
        guardián mide la etiqueta, no la presencia: `data-gen` estaba puesto y
        aun así la tira no llegaba al documento."""
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        etiqueta = re.search(r"<(\w+)[^>]*\bdata-gen=\"portada-chips\"", html)
        self.assertIsNotNone(etiqueta, "la portada perdió el marcador de la tira")
        self.assertIn(etiqueta.group(1), ("tbody", "ul", "span", "section"),
                      f"<{etiqueta.group(1)}> no es un contenedor que el "
                      "inyector sepa rellenar: la tira se quedaría vacía")
        self.assertRegex(html, r'data-gen="portada-chips"></' + etiqueta.group(1),
                         "la apertura y el cierre van pegados, sin salto")

    def test_el_chip_se_entera_de_lo_que_se_apaga_desde_el_control_de_capas(self):
        """El control de capas de Leaflet se queda en la portada —los chips
        accionan cinco de las doce capas y retirarlo escondería las otras
        siete—, así que hay dos mandos sobre las mismas capas. Si el chip solo
        se entera de sus propios clics, apagar la capa desde el control deja la
        tira publicando un estado que el mapa desmiente: el chip dice
        «encendido» sobre un mapa que ya no dibuja nada. Es la misma trampa con
        otro traje —dos mandos que divergen— y el día que alguien retire la
        línea la suite seguía en verde.

        El guardián mide las dos mitades, porque cada una falla sola: que
        `conectarChips` escuche los dos eventos, y que lo que haga al oírlos
        sea **releer el mapa** (`hasLayer`) y no repintar un estado propio,
        que es lo que ya estaría desincronizado."""
        cuerpo = re.search(r"function conectarChips\(\)(.*?)\n  \}\)\(\);",
                           self.js, re.S)
        self.assertIsNotNone(
            cuerpo, "`conectarChips` ya no es el IIFE que este test sabe leer: "
            "si se ha renombrado o reescrito, revisa que la resincronización "
            "siga existiendo antes de adaptar el guardián")
        cuerpo = cuerpo.group(1)
        for evento in ("overlayadd", "overlayremove"):
            self.assertIn(
                evento, cuerpo,
                f"`conectarChips` no escucha `{evento}`: quien apague o "
                "encienda esa capa desde el control de Leaflet dejará el chip "
                "mintiendo sobre lo que el mapa dibuja")
        self.assertIn(
            "hasLayer", cuerpo,
            "el reflejo del chip no consulta `map.hasLayer`: si repinta un "
            "estado propio, resincronizar no sincroniza nada")


class TestLaMudanzaDeLaMetodologia(unittest.TestCase):
    """La metodología y el glosario dejaron la portada (fase 6b, 25-ago-2026).

    **220 páginas publicadas enlazan `index.html#glosario` e
    `index.html#metodologia`.** Una URL publicada es un compromiso: mover el
    texto sin dejar los dos `id` donde estaban rompería todos esos enlaces de
    golpe y en silencio —el navegador se queda arriba de una página que ya no
    responde a lo que el enlace prometía—.

    Este guardián vigila las dos mitades del trato a la vez: que la portada
    conserve los dos anclajes con algo que responda, y que el texto entero
    exista de verdad en la página nueva. Cualquiera de las dos sola es una
    promesa a medias.
    """

    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        cls.ref = (ROOT / "site" / "referencia.html").read_text(encoding="utf-8")

    def test_la_portada_conserva_los_dos_anclajes_publicados(self):
        for ancla in ("metodologia", "glosario"):
            self.assertRegex(
                self.index, rf'id="{ancla}"',
                f"la portada perdió el ancla #{ancla}: 220 páginas publicadas "
                "enlazan ahí y se quedarían apuntando a ninguna parte")

    def test_lo_que_queda_en_la_portada_lleva_a_donde_esta_el_texto(self):
        """Un ancla que aterriza en un párrafo mudo es peor que un 404: parece
        que funciona. El bloque que se queda tiene que remitir a la página."""
        bloque = re.search(r'<section[^>]*id="metodologia".*?</section>',
                           self.index, re.S)
        self.assertIsNotNone(bloque, "no queda bloque de metodología en la portada")
        self.assertIn("/referencia.html", bloque.group(0),
                      "el resumen que se queda en la portada no lleva a la "
                      "página donde vive la metodología entera")

    def test_el_texto_entero_esta_en_la_pagina_nueva(self):
        """Se mide con las piezas que NADIE reescribiría por casualidad: las
        siglas del glosario y los tres ciclos de la metodología. Si el texto se
        hubiera quedado a medias en la mudanza, faltarían aquí."""
        for sigla in ("EDAN", "DIVIPOLA", "ShakeMap", "GLIDE", "SNIGRD"):
            self.assertIn(sigla, self.ref,
                          f"el glosario llegó incompleto: falta «{sigla}»")
        for pieza in ("Trazabilidad", "Reglas del cruce", "Limitaciones conocidas"):
            self.assertIn(pieza, self.ref,
                          f"la metodología llegó incompleta: falta «{pieza}»")
        self.assertNotIn("Glosario de acrónimos", self.index,
                         "el glosario sigue en la portada: se ha copiado en vez "
                         "de mudarse, y ahora hay dos que envejecen por separado")

    def test_el_pie_de_las_257_paginas_manda_a_la_pagina_nueva(self):
        """El pie es la superficie que llega a las 257 páginas. Mientras apunte
        al plegable de la portada, el enlace «Glosario» de cualquier ficha
        aterriza dentro de un `<details>` cerrado y depende de que el navegador
        lo abra al saltar al ancla."""
        pie = R.pie_estatico()
        for ancla in ("glosario", "metodologia"):
            self.assertIn(f"{R.BASE}/referencia.html#{ancla}", pie)
            self.assertNotIn(f'"{R.BASE}/index.html#{ancla}"', pie)


class TestLaPaginaDeReferencia(unittest.TestCase):
    """La sexta página grande: `referencia.html`.

    Una página nueva tiene que entrar en ONCE superficies —barra, pie,
    identidad, sello, sitemap, IndexNow, llms.txt, seo_check, y las listas de
    los tests—. Este guardián comprueba las que un olvido deja rotas en
    silencio: las demás revientan el build y se ven solas.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site" / "referencia.html").read_text(encoding="utf-8")

    @staticmethod
    def _modulo(ruta, nombre):
        """Un módulo suelto del repo, sin importarlo por paquete.

        `ingest/indexnow.py` importa `common` como hermano, así que su carpeta
        tiene que estar en la ruta antes de ejecutarlo."""
        import importlib.util
        for carpeta in ("ingest", "deploy"):
            ruta_abs = str(ROOT / carpeta)
            if ruta_abs not in sys.path:
                sys.path.insert(0, ruta_abs)
        esp = importlib.util.spec_from_file_location(nombre, ROOT / ruta)
        mod = importlib.util.module_from_spec(esp)
        esp.loader.exec_module(mod)
        return mod

    def test_entra_en_las_superficies_que_no_avisan_al_olvidarse(self):
        modulo = self._modulo
        self.assertIn("referencia.html", dict(R.PAGINAS),
                      "no sale en la barra de navegación")
        self.assertIn("referencia.html", R.PAGINAS_GRANDES,
                      "no recibe barra, pie ni identidad del sitio")
        desc = modulo("deploy/render_descubrimiento.py", "descubrimiento")
        self.assertIn("/referencia.html", [u for u, _c, _p in desc.PAGINAS],
                      "no entra en el sitemap: nadie la va a descubrir")
        seo = modulo("ingest/seo_check.py", "seo_check")
        self.assertIn("referencia.html", seo.MINIMOS,
                      "sin entrada en MINIMOS no se le comprueba NADA")
        self.assertIn("referencia.html", seo.PROSA_MINIMA,
                      "sin suelo de prosa, su texto puede desaparecer en silencio")
        idx = modulo("ingest/indexnow.py", "indexnow")
        self.assertIn("/referencia.html", idx.PAGINAS_FIJAS,
                      "no se avisa a los buscadores cuando cambia")
        llms = (ROOT / "deploy" / "root" / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("referencia.html", llms,
                      "los sistemas de IA no saben que existe")

    def test_su_dataset_cita_a_quien_produce_las_cifras(self):
        """**R9 sobre la página cuyo oficio es documentar la procedencia.**

        `creator` es el monitor —compila el artefacto— y el origen va en
        `citation`. Un `Dataset` sin `citation` en ESTA página le diría a una
        máquina que el monitor firma los datos, justo lo contrario de lo que la
        página entera explica con palabras.

        Los tres servicios satelitales se comprueban contra `SATELITES`, no
        contra una lista escrita aquí: el día que entre el cuarto, este test
        pide su cita solo."""
        ld = R.dataset_referencia(R.contexto())
        nodo = [n for b in bloques_ld(ld) for n in nodos_ld(b)
                if "Dataset" in tipos_ld(n)]
        self.assertEqual(len(nodo), 1)
        nodo = nodo[0]
        self.assertEqual(nodo["creator"], {"@id": R.ORGANIZACION},
                         "`creator` debe ser el monitor, que compila (R9)")
        publicadores = {c["publisher"]["name"] for c in nodo.get("citation") or []}
        self.assertTrue(publicadores, "el Dataset no cita a nadie: R9 roto")
        for sat in R.SATELITES:
            self.assertIn(
                sat["publicador"], publicadores,
                f"{sat['rotulo']} aporta cifras a este conjunto y no está "
                "citado: la atribución se deriva de SATELITES, así que un "
                "servicio nuevo entra solo o este test lo canta")
        for imprescindible in (R.UNGRD_ORG, R.DANE_ORG):
            self.assertIn(imprescindible, publicadores)

    def test_su_dataset_no_estrena_conjunto_sino_que_comparte_el_de_la_portada(self):
        """Mismo `@id` que el nodo de la portada: es el MISMO conjunto. Con dos
        `@id` distintos, un agregador contaría dos conjuntos donde hay uno."""
        ld = R.dataset_referencia(R.contexto())
        nodo = [n for b in bloques_ld(ld) for n in nodos_ld(b)
                if "Dataset" in tipos_ld(n)][0]
        portada = [n for n in nodos_ld(bloques_ld(
            (ROOT / "site" / "index.html").read_text(encoding="utf-8")))
            if "Dataset" in tipos_ld(n)]
        self.assertEqual(len(portada), 1, "la portada ya no declara su Dataset")
        # la portada lo declara anidado y sin `@id` propio: hereda el del sitio.
        # Lo que se exige aquí es que el de la referencia NO invente uno nuevo.
        self.assertEqual(nodo["@id"], "https://datosdelterremoto.org/#dataset")

    def test_trae_los_tres_marcadores_que_el_build_necesita(self):
        """Sin cualquiera de los tres, `escribir_piezas_compartidas` no rompe
        el build de milagro: lo rompe a propósito. Se comprueban aquí para que
        el fallo llegue con nombre y no como un `LookupError` de la corrida."""
        for marca in ("<!--site-identity-->",
                      '<nav id="site-nav" aria-label="Navegación del sitio"></nav>',
                      '<div id="site-footer"></div>'):
            self.assertIn(marca, self.html, f"falta el marcador {marca!r}")

    def test_su_suelo_de_prosa_es_el_que_de_verdad_publica(self):
        """El suelo no puede ser una cifra de deseo. Si sube por encima de lo
        que la página escribe, el build falla mañana sin que nadie haya tocado
        nada; si se queda muy por debajo, deja de proteger."""
        seo = self._modulo("ingest/seo_check.py", "seo_check")
        # Sobre el ARTEFACTO, que es lo que mide `seo_check`. Rehacerlo aquí
        # pegando la barra y el pie a mano da una cifra parecida pero distinta
        # —siete palabras—, y con ella el test acusaba al suelo de un fallo
        # suyo. Sin `dist/` no hay nada que medir y se dice, en vez de medir
        # otra cosa.
        artefacto = ROOT / "dist" / "referencia.html"
        if not artefacto.exists():
            self.skipTest("sin dist/: el suelo se mide sobre el artefacto")
        propias = seo.prosa_propia(artefacto.read_text(encoding="utf-8"))
        suelo = seo.PROSA_MINIMA["referencia.html"]
        self.assertGreaterEqual(
            propias, suelo,
            f"la página escribe {propias} palabras propias y su suelo pide "
            f"{suelo}: el build va a fallar")
        self.assertGreater(
            suelo, propias * 0.9,
            f"el suelo ({suelo}) va muy por debajo de las {propias} palabras "
            "que la página publica: dejaría pasar una mudanza a medias")


class TestLaMudanzaDeLaCronologia(unittest.TestCase):
    """La cronología dejó la portada (fase 6c, 25-ago-2026).

    Ocupaba 2.402 px —su sección más alta— delante de quien llega buscando su
    municipio, y **no era texto servido**: el `<ol id="timeline">` viajaba vacío
    y `app.js` lo montaba en el navegador, así que ningún rastreador leyó jamás
    la cronología de un proyecto que se define como archivo.

    Este guardián vigila las tres mitades del trato: que la portada la haya
    soltado, que el ancla publicada siga respondiendo Y llevando al texto, y
    que el texto exista de verdad —escrito, no prometido— en la página nueva.
    Cualquiera de las tres sola es una promesa a medias.
    """

    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        cls.ref = (ROOT / "site" / "referencia.html").read_text(encoding="utf-8")
        cls.ctx = R.contexto()
        cls.cuerpo = R.cronologia_referencia(cls.ctx)

    def test_la_portada_ya_no_monta_la_cronologia(self):
        for contenedor in ('<ol id="timeline">', 'id="crono-banda"',
                           'id="crono-filtros"'):
            self.assertNotIn(
                contenedor, self.index,
                f"la portada conserva {contenedor}: la cronología no se ha "
                "mudado, se ha copiado, y ahora hay dos que envejecen aparte")

    def test_la_portada_conserva_el_ancla_publicada_y_lleva_al_texto(self):
        """`index.html#cronologia` está publicado. Un ancla que aterriza en un
        párrafo mudo es peor que un 404: parece que funciona."""
        bloque = re.search(r'<[a-z]+[^>]*\bid="cronologia"[^>]*>.*?</[a-z]+>',
                           self.index, re.S)
        self.assertIsNotNone(bloque, "la portada perdió el ancla #cronologia")
        self.assertIn("/referencia.html#cronologia", bloque.group(0),
                      "el ancla que se queda no lleva a donde vive la cronología")

    def test_la_pagina_nueva_declara_su_seccion_y_su_contenedor(self):
        self.assertIn('id="cronologia"', self.ref)
        self.assertIn('data-gen="referencia-cronologia"', self.ref)

    def test_los_hitos_llegan_escritos_y_no_prometidos(self):
        """Lo que se ha venido a arreglar: los hitos EN el documento."""
        self.assertIn('<ol id="timeline">', self.cuerpo)
        self.assertGreaterEqual(
            self.cuerpo.count("<li "), 20,
            "la cronología servida trae menos hitos de los curados: se está "
            "quedando algo por el camino")
        self.assertIn("<svg", self.cuerpo, "la banda no se ha venido con ella")
        for filtro in ("todos", "internacional", "local", "monitor"):
            self.assertIn(f'data-filtro="{filtro}"', self.cuerpo,
                          f"falta el chip del filtro «{filtro}»")

    def test_cada_hito_lleva_la_clase_con_la_que_su_filtro_lo_busca(self):
        """El filtro trabaja con la etiqueta agrupada y el CSS colorea con el
        tipo crudo: los hitos institucionales y las entregas de Copernicus son
        los dos «internacional». Con una sola clase, el filtro que más hitos
        agrupa dejaba la lista vacía."""
        clases = re.findall(r'<li class="([^"]*)"', self.cuerpo)
        self.assertTrue(clases, "no se ha escrito ningún hito")
        for cadena in clases:
            partes = cadena.split()
            self.assertTrue(partes, "un hito sin clase no lo alcanza el filtro")
            etiqueta = R.ETIQUETA_HITO.get(partes[0])
            self.assertIsNotNone(etiqueta, f"tipo de hito desconocido: {partes[0]}")
            self.assertIn(
                etiqueta, partes,
                f"el hito «{partes[0]}» no lleva la clase «{etiqueta}» con la "
                "que su chip lo filtra: ese filtro deja la lista vacía")

    def test_los_cambios_del_monitor_se_leen_enteros_y_el_resto_por_su_resumen(self):
        """Criterio portado de `app.js::pintaCronologia`: un resumen de seis
        palabras sobre un cambio técnico no dice nada, así que los hitos del
        monitor enseñan su texto largo; los demás, el resumen."""
        curados = json.loads(
            (ROOT / "feeds" / "hitos_monitor.json").read_text(encoding="utf-8"))
        largos = [h for h in curados["hitos"] if h.get("tipo") == "monitor"
                  and h.get("resumen") and h.get("texto")
                  and h["texto"] != h["resumen"]]
        self.assertTrue(largos, "no hay hito del monitor con las dos versiones")
        visible = re.sub(r"<[^>]+>", " ", self.cuerpo)
        muestra = largos[0]["texto"][:60]
        self.assertIn(muestra.split("<")[0][:40], visible,
                      "el hito del monitor se publica resumido: se pierde el "
                      "contexto que un cambio técnico necesita")

    def test_ningun_enlace_de_la_cronologia_acaba_en_almohadilla(self):
        """19 de los 27 hitos curados apuntan a páginas de este mismo sitio.
        `enlace_seguro` solo admite http(s) —para eso existe— y los convertía
        a «#»: un enlace que no lleva a ninguna parte, en cada uno de ellos."""
        self.assertNotIn(
            'href="#"', self.cuerpo,
            "hay hitos con un enlace muerto: el filtro de esquemas se está "
            "comiendo los enlaces internos del propio sitio")

    def test_los_codigos_de_producto_se_dicen_igual_en_las_dos_superficies(self):
        """`PRODUCTO_ES`/`CATEGORIA_ES` (build) y `DICT` (app.js, que sigue
        traduciendo los globos del mapa) nombran los mismos productos y las
        mismas categorías de Copernicus. Si divergen, la cronología llama a un
        producto de una manera y el globo del mapa de otra, en el mismo sitio
       . Y ninguna de las dos puede quedarse en inglés: el catálogo de
        activaciones se publicó un rato diciendo «Flood in Cordoba, Colombia ·
        Flood» porque el build escribía la categoría cruda."""
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        for tabla in (R.PRODUCTO_ES, R.CATEGORIA_ES):
            for codigo, castellano in tabla.items():
                self.assertIn(
                    f'"{codigo}": "{castellano}"', js,
                    f"el build llama «{castellano}» a «{codigo}» y app.js lo "
                    "llama de otra manera")


class TestLaCabeceraSinMatricula(unittest.TestCase):
    """La cabecera de la portada dice qué pasó, dónde y cuándo (fase 6c).

    Llevaba encima el GLIDE del desastre, el código de la activación de
    Copernicus y el color de la alerta PAGER: matrícula de siniestro delante de
    quien llega buscando su municipio. Se va, pero **no del sitio**: cada pieza
    tiene que seguir explicada donde significa algo.
    """

    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        cls.ref = (ROOT / "site" / "referencia.html").read_text(encoding="utf-8")
        cls.cabecera = re.search(r"<header class=\"encabezado\">.*?</header>",
                                 cls.index, re.S).group(0)

    def test_la_cabecera_no_lleva_la_matricula_del_siniestro(self):
        for jerga in ("GLIDE", "PAGER", "EMSR916"):
            self.assertNotIn(
                jerga, self.cabecera,
                f"«{jerga}» ha vuelto a la cabecera de la portada: es lo "
                "primero que lee quien llega buscando su municipio")

    def test_la_cabecera_sigue_diciendo_que_pasó_donde_y_cuando(self):
        self.assertIn("M7.4", self.cabecera)
        self.assertIn("San José del Palmar", self.cabecera)
        self.assertIn('data-gen="portada-sello"', self.cabecera,
                      "la cabecera perdió la fecha del dato")

    def test_lo_que_sale_de_la_cabecera_sigue_explicado_en_la_referencia(self):
        """Nada se evapora: el código de la activación y el del desastre viven
        en el glosario, y la alerta roja del PAGER —que solo se decía en la
        cabecera— se explica ahí con lo que significa y lo que no."""
        for pieza in ("EMSR916", "EQ-2026-000146-COL"):
            self.assertIn(pieza, self.ref,
                          f"«{pieza}» salió de la portada y no está en ninguna "
                          "otra parte: se ha perdido un dato")
        pager = re.search(r"<dt>PAGER</dt><dd>(.*?)</dd>", self.ref, re.S)
        self.assertIsNotNone(pager, "el glosario perdió la entrada de PAGER")
        self.assertIn("alerta roja", pager.group(1),
                      "el nivel de alerta que emitió el USGS para ESTE sismo "
                      "solo vivía en la cabecera de la portada y no se ha "
                      "recogido en ninguna parte")

    def test_la_cabecera_deja_una_sola_descarga_y_es_la_del_cruce(self):
        botones = re.findall(r'<a class="btn" href="([^"]+)"', self.cabecera)
        self.assertEqual(
            botones, ["/data/public/crosscheck.csv"],
            "la cabecera vuelve a ser una fila de descargas: el CSV es el dato "
            "de esta página y las demás tienen su sitio en /referencia.html")

    def test_las_otras_cuatro_descargas_tienen_sitio_propio_y_no_papelera(self):
        """Esconder datos abiertos iría contra la misión. Bajan, no se van."""
        bloque = re.search(r'<section[^>]*id="descargas".*?</section>',
                           self.ref, re.S)
        self.assertIsNotNone(bloque, "no hay bloque de datos abiertos")
        for fichero in ("monitor.json", "unosat_damage.geojson",
                        "sertit_damage.geojson", "municipios_mapa.json"):
            self.assertIn(
                fichero, bloque.group(0),
                f"«{fichero}» salió de la cabecera de la portada y no aparece "
                "en el bloque de datos abiertos: se ha escondido un dato")
        self.assertIn(
            "ICube-SERTIT 2026", bloque.group(0),
            "el GeoJSON de SERTIT no lleva CC BY como el resto y su licencia "
            "no cabía en un botón: por eso baja aquí, con ella escrita")

    def test_cada_descarga_ofrecida_existe_de_verdad(self):
        """Una lista de descargas escrita a mano se descuelga sola del
        directorio que describe: basta con que un producto cambie de nombre
        para que el bloque ofrezca un 404 con aspecto de dato abierto. Se
        comprueba contra `data/public/`, que es lo que se publica."""
        bloque = re.search(r'<section[^>]*id="descargas".*?</section>',
                           self.ref, re.S).group(0)
        rutas = re.findall(r'href="/data/public/([^"]+)"', bloque)
        self.assertGreaterEqual(len(rutas), 10,
                                "el bloque de datos abiertos se ha quedado en "
                                "nada, o este test ha dejado de leerlo")
        faltan = [r for r in rutas if not (ROOT / "data" / "public" / r).exists()]
        self.assertEqual(faltan, [],
                         f"el bloque ofrece ficheros que no se publican: {faltan}")


class TestLaVigilanciaDelCatalogoCopernicus(unittest.TestCase):
    """«Otras activaciones de Copernicus en Colombia» se muda (fase 6c).

    se tachó de la portada, y no es material de lectura para quien busca su
    municipio. Pero **no es material que se tire**: el día que una de esas
    activaciones desaparezca del portal, esta lista seguirá diciendo que
    existió. Vigilar fuentes es parte de la misión, así que su sitio es la
    página que explica qué mira el monitor, no la papelera.
    """

    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        cls.ref = (ROOT / "site" / "referencia.html").read_text(encoding="utf-8")

    def test_la_portada_ya_no_la_lleva(self):
        self.assertNotIn("colombia-acts", self.index)

    def test_pero_sigue_publicandose_en_la_referencia(self):
        self.assertIn('id="colombia-acts-section"', self.ref)
        self.assertIn('data-gen="referencia-acts"', self.ref)
        cuerpo = R.activaciones_colombia(R.contexto())
        self.assertTrue(cuerpo.strip(),
                        "el generador se ha quedado sin escribir nada")

    def test_el_generador_esta_declarado_para_la_pagina_nueva(self):
        """Un generador apuntando a la página vieja no falla: escribe en un
        contenedor que ya no existe y revienta el build con `LookupError`. Se
        comprueba aquí para que el fallo llegue con nombre."""
        fuente = (ROOT / "deploy" / "render_html.py").read_text(encoding="utf-8")
        self.assertIn('"referencia-acts": "referencia"', fuente)
        self.assertNotIn('"portada-acts"', fuente,
                         "queda una declaración de la pieza vieja")


class TestElCatalogoDeActivacionesSeLeeEnEspanol(unittest.TestCase):
    """Idioma: los textos del sitio van en español (CLAUDE.md).

    El catálogo se publicaba con `app.js`, que traducía la categoría de la
    activación. Al escribirlo el build (fase 6) la traducción se quedó por el
    camino y la línea salía «Flood in Cordoba, Colombia · Flood». El nombre de
    la activación SÍ se deja en inglés a propósito: es el rótulo con que
    Copernicus la publica y con el que se busca en su portal.
    """

    def test_la_categoria_de_cada_activacion_va_traducida(self):
        cuerpo = R.activaciones_colombia(R.contexto())
        crudas = [c for c in R.CATEGORIA_ES
                  if re.search(rf"·\s*{re.escape(c)}\s*·", cuerpo)]
        self.assertEqual(
            crudas, [],
            f"el catálogo publica la categoría en inglés: {crudas}")


class TestElOrdenDeLaPortadaEsElDeLaMaqueta(unittest.TestCase):
    """A3, B5 y C1 · Primero las puertas del sitio, después la explicación.

    La portada construida había invertido esa jerarquía: la comparativa de
    fuentes estaba abierta y por delante de las tarjetas, «Qué encontrará en
    este sitio» se había fundido dentro de «Cómo leer estas cifras» arriba del
    todo, y «Cómo se construye» —la puerta que explica de dónde sale todo lo
    demás— había caído al final de la tira.

    El orden de una página es un argumento, no una maquetación: quien llega
    buscando su municipio no tiene que atravesar tres bloques de explicación, y
    quien quiere entender los encuentra donde ya sabe qué está mirando.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

    def _pos(self, aguja):
        i = self.html.find(aguja)
        self.assertNotEqual(i, -1, f"«{aguja}» ya no está en la portada")
        return i

    def test_que_encontrara_es_un_bloque_propio_y_no_vive_dentro_de_otro(self):
        """A3 · Estaba fusionado dentro de «Cómo leer estas cifras», arriba del
        todo. La prosa es la misma —se mueve, no se reescribe—: la escribe
        `nota_como_leer_portada` y sigue siendo su único inquilino."""
        bloque = re.search(
            r"<details[^>]*>\s*<summary>Qué encontrará en este sitio</summary>"
            r"(.*?)</details>", self.html, re.S)
        self.assertIsNotNone(
            bloque, "«Qué encontrará en este sitio» ha dejado de ser un plegable "
                    "propio")
        self.assertIn('data-gen="portada-comoleer"', bloque.group(1),
                      "el bloque se quedó sin su prosa: es un movimiento, no "
                      "una redacción nueva")
        self.assertNotIn("Cómo leer estas cifras", self.html,
                         "vuelve a haber dos bloques con la misma prosa: la "
                         "versión corta de la maqueta es una condensación de "
                         "estos mismos párrafos, y este sitio no escribe dos "
                         "veces las mismas cifras")

    def test_la_comparativa_de_fuentes_va_plegada_y_despues_de_las_tarjetas(self):
        """B5 · Abierta y por delante de las puertas, la comparativa obligaba a
        pasar por una explicación de cuatro tarjetas para llegar a ellas."""
        pliegue = re.search(
            r"<details[^>]*>\s*<summary>Qué mira cada fuente</summary>"
            r"(.*?)</details>", self.html, re.S)
        self.assertIsNotNone(
            pliegue, "la comparativa de fuentes vuelve a estar abierta: la "
                     "maqueta la pliega bajo «Qué mira cada fuente»")
        self.assertIn('id="fuentes-section"', pliegue.group(1))
        self.assertIn('data-gen="portada-fuentes"', pliegue.group(1))
        self.assertNotIn(
            "open", re.search(r"<details[^>]*>\s*<summary>Qué mira cada fuente",
                              self.html).group(0),
            "el plegable de la comparativa nace abierto")
        self.assertLess(
            self._pos('data-gen="portada-tarjetas"'),
            self._pos("<summary>Qué mira cada fuente</summary>"),
            "la comparativa volvió a colarse por delante de las tarjetas")

    def test_las_tres_explicaciones_van_seguidas_y_detras_de_las_puertas(self):
        """El orden de la maqueta: tarjetas, qué encontrará, qué mira cada
        fuente, alertas."""
        orden = ['data-gen="portada-tarjetas"',
                 "<summary>Qué encontrará en este sitio</summary>",
                 "<summary>Qué mira cada fuente</summary>",
                 "<summary>Alertas y silencios</summary>"]
        posiciones = [self._pos(a) for a in orden]
        self.assertEqual(posiciones, sorted(posiciones),
                         f"el orden de la portada ya no es el de la maqueta: "
                         f"{orden}")

    def test_la_primera_puerta_es_la_que_explica_de_donde_sale_todo(self):
        """C1 · «Cómo se construye» abría la tira en la maqueta y había caído al
        final. Las cifras las escribe el build; el orden, no."""
        tira = R.tarjetas_portada(R.contexto())
        titulos = re.findall(r"<strong>(.*?)</strong>", tira)
        self.assertEqual(
            titulos[0], "Cómo se construye",
            f"la tira empieza por «{titulos[0]}»: la primera puerta es la "
            "trazabilidad, no una cifra")
        self.assertEqual(
            titulos,
            ["Cómo se construye", "Municipios", "RUD", "Balances", "Titulares"],
            "el orden de las cinco puertas ya no es el de la maqueta")


class TestElRegistroQueSeDetiene(unittest.TestCase):
    """La tabla contesta «¿cuándo cambió el registro?», no «¿qué decía cada
    día?». El RUD lo cargan las alcaldías y cuando terminan cada corrida diaria
    añadía una fila idéntica a la anterior: Jamundí publicaba diez filas para
    contar dos hechos —ocho capturas clavado en 23 familias y el salto a 1.539—.

    El primer intento (26-ago) recortaba la cola plana a partir de la
    tercera captura repetida. Se descartó al medirlo (27-ago): dejaba fuera los
    153 municipios cuyo tramo plano NO está al final, hacía oscilar la tabla
    —las filas desaparecían al tercer día quieto y volvían si la fuente
    despertaba— y escondía la fecha de la última captura, que era justo el
    síntoma del que salió todo esto.
    """

    @staticmethod
    def _serie(*familias):
        return [(f"2026-08-{16 + i:02d}",
                 {"familias": f, "personas": f * 2,
                  "viv_destruidas": 1, "viv_averiadas": 2})
                for i, f in enumerate(familias)]

    def test_las_capturas_que_repiten_una_cifra_son_un_solo_tramo(self):
        tramos = R.tramos_del_registro(self._serie(23, 23, 23, 1539, 1539))
        self.assertEqual([len(f) for f, _ in tramos], [3, 2])
        self.assertEqual([fila["familias"] for _, fila in tramos], [23, 1539])

    def test_un_tramo_plano_al_PRINCIPIO_tambien_se_agrupa(self):
        """El caso Jamundí, que es el que tiró el criterio anterior: sus ocho
        filas repetidas están al principio, así que recortar la cola no le
        quitaba ni una."""
        tramos = R.tramos_del_registro(self._serie(23, 23, 23, 23, 23, 23, 23, 23,
                                                  1539, 1539))
        self.assertEqual(len(tramos), 2)
        self.assertEqual(len(tramos[0][0]), 8)

    def test_ninguna_captura_se_pierde_por_el_camino(self):
        """Agrupar no es borrar: la cuenta de fechas de todos los tramos tiene
        que dar la serie entera, o la ficha estaría publicando menos días de los
        que el monitor pidió."""
        serie = self._serie(10, 10, 20, 20, 20, 30, 30)
        fechas = [f for grupo, _ in R.tramos_del_registro(serie) for f in grupo]
        self.assertEqual(fechas, [f for f, _ in serie])

    def test_una_columna_que_se_mueve_sin_familias_abre_tramo(self):
        """La ficha publica cuatro columnas. Si el registro corrige viviendas
        averiadas sin tocar las familias, ese día trae información nueva y no
        puede fundirse con el anterior."""
        serie = self._serie(200, 200, 200)
        serie[-1][1]["viv_averiadas"] = 99
        self.assertEqual(len(R.tramos_del_registro(serie)), 2)

    def test_el_rotulo_no_repite_el_mes_ni_esconde_el_cambio_de_mes(self):
        """La celda es estrecha: «16-ago-2026 al 23-ago-2026» la desborda sin
        decir nada más. Pero un registro puede pasarse semanas quieto, y ahí
        cada extremo necesita su mes."""
        self.assertEqual(R.rotulo_de_tramo(["2026-08-18"]), "18-ago-2026")
        self.assertEqual(R.rotulo_de_tramo(["2026-08-16", "2026-08-20",
                                            "2026-08-23"]), "16 al 23-ago-2026")
        self.assertEqual(R.rotulo_de_tramo(["2026-08-28", "2026-09-03"]),
                         "28-ago-2026 al 3-sep-2026")

    def test_la_ficha_agrupa_y_dice_cuantas_capturas_cubre_cada_fila(self):
        """Sobre la ficha real, con su serie estancada a propósito: la tabla no
        repite la fila y la cuenta de capturas —que es el dato— sale escrita."""
        d = copy.deepcopy(R.datos_ficha("Cali", R.contexto()))
        ultimo = d["serie"][-1][1]
        d["serie"] = d["serie"] + [
            (f"2026-09-{n:02d}", dict(ultimo)) for n in (1, 2, 3)]
        seccion = R.render_ficha(d)
        seccion = seccion[seccion.find('id="registro"'):]
        seccion = seccion[:seccion.find("</section>")]
        filas = re.findall(r"<tr[^>]*><td>(.*?)</td>", seccion)
        self.assertEqual(filas[-1].split("<")[0], "24-ago-2026 al 3-sep-2026",
                         f"la última fila debería agrupar el tramo: {filas[-1]}")
        self.assertIn("cinco capturas, sin cambios", filas[-1])
        self.assertNotIn("01-sep-2026", seccion,
                         "las capturas repetidas no van fila a fila")

    def test_la_ficha_dice_en_voz_alta_que_el_registro_esta_parado(self):
        """La última fila lleva la fecha de la última captura, pero de un rango
        nadie deduce que seguimos preguntando cada día. Sin esta línea, un
        registro detenido y un monitor abandonado se leen igual."""
        d = copy.deepcopy(R.datos_ficha("Cali", R.contexto()))
        ultimo = d["serie"][-1][1]
        d["serie"] = d["serie"] + [
            (f"2026-09-{n:02d}", dict(ultimo)) for n in (1, 2, 3)]
        html = R.render_ficha(d)
        self.assertIn("no cambia desde el 24 de agosto de 2026", html)
        self.assertIn("capturado cuatro veces más —la última, el 3 de "
                      "septiembre de 2026— y ninguna traía una cifra nueva", html)

    def test_la_cuenta_de_capturas_concuerda_en_femenino(self):
        """«lo ha capturado un vez más»: `fmt_prosa` da el masculino por
        defecto y la apócope se coló en la primera versión publicada. Una
        captura es femenina, y esta línea sale en cientos de fichas."""
        d = copy.deepcopy(R.datos_ficha("Cali", R.contexto()))
        html = R.render_ficha(d)
        self.assertIn("capturado una vez más", html)
        self.assertNotIn("capturado un vez", html)

    def test_un_registro_vivo_no_dice_que_esta_parado(self):
        """El reverso: si la última captura trajo cifra nueva, esa línea sería
        falsa. Es la mitad que se olvida y publica una acusación al revés."""
        d = copy.deepcopy(R.datos_ficha("Cali", R.contexto()))
        d["serie"] = d["serie"][:-1]        # la última captura trajo cifra nueva
        self.assertNotIn("no cambia desde", R.render_ficha(d))

    def test_la_grafica_recibe_la_serie_entera_y_no_los_tramos(self):
        """Su eje es el tiempo. Agrupada, los ocho días quietos de Jamundí
        ocuparían lo mismo que el salto que vino después y la forma —lo único
        que aporta el dibujo— mentiría."""
        html = R.render_ficha(copy.deepcopy(R.datos_ficha("Jamundí",
                                                          R.contexto())))
        svg = html[html.find('class="grafico-rud-muni"'):]
        svg = svg[:svg.find("</svg>")]
        dias = re.findall(r'class="g-dia"[^>]*>([^<]+)<', svg)
        self.assertEqual(len(dias), 10,
                         f"el eje tiene que llevar los diez días: {dias}")
        self.assertEqual(len(re.findall(r"<circle", svg)), 10)

    def test_un_dia_de_cero_altas_se_dibuja_y_no_se_confunde_con_un_hueco(self):
        """R3 dentro del SVG. El primer día no tiene barra porque no hay
        captura anterior con la que comparar —«eso no lo sabemos»—; un día de
        cero altas es lo contrario, «ese día no entró nadie», y con el hueco
        idéntico la gráfica de Cali parecía terminar el 24 de agosto teniendo
        el 25 dibujado. Es el fallo que encontró el 26-ago-2026."""
        svg = R.grafico_rud_municipal(self._serie(100, 200, 300, 400, 400), "cero")
        self.assertIn('data-altas="0"', svg)
        self.assertIn("ni una familia nueva ese día", svg)
        self.assertEqual(len(re.findall(r"<rect", svg)), 4,
                         "cuatro barras: tres altas y la marca del cero. El "
                         "primer día sigue sin barra, que es lo correcto")
