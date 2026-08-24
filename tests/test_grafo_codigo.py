"""El grafo de llamadas responde preguntas de forma, y hay que poder creerle.

Su valor es que contesta barato lo que `grep` contesta caro; su riesgo es que
contesta con seguridad. La primera versión afirmó que el guardián global del
marcado pasaba por el inyector cuando no lo hacía, porque no modelaba las
clases y fusionaba los cuarenta `setUpClass` del fichero de tests en un nodo.
Estos tests fijan lo que hace bien y, sobre todo, **lo que no puede hacer**:
una herramienta con límites escritos se usa bien; una que promete de más se
cree en el momento malo (M1, M4).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import grafo_codigo as G


class TestGrafoDeLlamadas(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.nodos, cls.aristas = G.construir()

    def test_la_clase_forma_parte_de_la_identidad(self):
        """Sin la clase, todos los `setUpClass` colapsan en un nodo y el grafo
        responde sobre un método que no es el preguntado. Es el mismo error que
        un merge que fusiona dos clases homónimas: la respuesta suena firme."""
        setups = [k for k in self.nodos
                  if k.endswith(".setUpClass")
                  and self.nodos[k]["fichero"] == "tests/test_render_html.py"]
        self.assertGreater(len(setups), 5,
                           "los setUpClass se están fusionando en un solo nodo")
        self.assertTrue(all(self.nodos[k]["clase"] for k in setups))

    def test_el_impacto_incluye_lo_transitivo_y_no_solo_lo_directo(self):
        """Es la pregunta que justifica la herramienta: `grep` da las llamadas
        directas y calla la cadena."""
        dep = G.impacto("render_html.fmt", self.nodos, self.aristas)
        self.assertIn("render_html.render_ficha", dep)
        self.assertTrue(any(d >= 2 for d in dep.values()),
                        "solo encuentra llamadas directas: eso ya lo hace grep")

    def test_el_camino_explica_por_que_una_funcion_afecta_a_otra(self):
        rutas = G.camino("render_html.render_ficha", "render_html.pct", self.aristas)
        self.assertTrue(rutas, "no encuentra cómo llega `pct` a la ficha")
        for r in rutas:
            self.assertEqual(r[0], "render_html.render_ficha")
            self.assertEqual(r[-1], "render_html.pct")

    def test_el_docstring_declara_los_tres_limites_conocidos(self):
        """M3 al revés: aquí el comentario SÍ es la barrera, porque el riesgo de
        esta herramienta es que se le crea de más. Si alguien retira una
        advertencia, este test lo para."""
        doc = G.__doc__ or ""
        for limite in ("NOMBRE", "despacho dinámico", "No indexa cadenas"):
            with self.subTest(limite=limite):
                self.assertIn(limite, doc)

    def test_no_promete_cobertura_de_tests(self):
        """Medido: las 95 funciones públicas de `render_html` se ejecutan en la
        suite, y este grafo declara once huérfanas porque el build las despacha
        por diccionario. La cobertura se mide EJECUTANDO, y la herramienta no
        debe ofrecer una orden que insinúe lo contrario."""
        self.assertNotIn("cobertura", (G.main.__doc__ or "").lower())
        self.assertNotIn("sin-test", G.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
