"""El índice de decisiones contesta barato lo que leer los documentos cuesta caro.

`docs/DECISIONES.md` son ~44.000 tokens en 62 entradas. La herramienta existe
para no tener que leerlo, así que su riesgo es el de siempre: contestar mal con
seguridad. Estos tests fijan lo que acierta y, sobre todo, los dos bugs que tuvo
al nacer —y que son ejemplares, porque los dos hacían que **la herramienta que
caza documentación falsa fuera la que gritaba en falso**.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import indice_decisiones as I


class TestIndiceDeDecisiones(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.entradas = I.entradas()

    def test_indexa_las_entradas_de_los_documentos(self):
        docs = {e["doc"] for e in self.entradas}
        self.assertIn("docs/DECISIONES.md", docs)
        self.assertIn("CLAUDE.md", docs)
        self.assertGreater(len(self.entradas), 100)

    def test_la_extension_larga_gana_a_la_corta(self):
        """`balances.json` se leía como `balances.js` porque en la alternancia
        `js` iba antes que `json`: la herramienta inventaba ficheros que no
        existen y luego los denunciaba como documentación caducada."""
        casos = {"data/public/balances.json": "data/public/balances.json",
                 ".github/workflows/daily.yml": ".github/workflows/daily.yml",
                 "deploy/render_html.py": "deploy/render_html.py"}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(I.RE_FICHERO.findall(texto), [esperado])

    def test_una_url_no_es_una_ruta_del_repositorio(self):
        """`https://datosdelterremoto.org/balances.html` daba `org/balances.html`,
        y de ahí «este fichero no existe»."""
        self.assertEqual(
            I.RE_FICHERO.findall("https://datosdelterremoto.org/balances.html"), [])

    def test_una_clase_de_test_citada_cuenta_como_existente(self):
        """Las decisiones nombran sus guardianes («lo vigila TestX»). Sin buscar
        `class`, la herramienta los daba por desaparecidos: tres falsos de
        cuatro en la primera pasada."""
        self.assertTrue(I._existe_funcion("TestActivosDelArchivo", ROOT))
        self.assertFalse(I._existe_funcion("FuncionQueNadieHaEscritoJamas", ROOT))

    def test_encuentra_las_decisiones_de_una_regla(self):
        conR16 = [e for e in self.entradas if "R16" in e["reglas"]]
        self.assertTrue(conR16, "R16 no aparece en ninguna decisión")

    def test_el_docstring_avisa_de_que_punteros_se_revisa_a_mano(self):
        """El límite conceptual que no se puede automatizar: en un documento de
        decisiones, citar un nombre viejo es correcto cuando se cuenta el
        renombrado. La orden lista sitios donde mirar, no errores."""
        doc = I.__doc__ or ""
        self.assertIn("revisar a mano", doc)
        self.assertIn("legítimo", doc)


if __name__ == "__main__":
    unittest.main()
