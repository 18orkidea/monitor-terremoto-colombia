"""La regla editorial de selección diaria de balances vive en JavaScript
(site/ui.js). Estos tests la ejecutan con node — la MISMA lógica que corre en
el navegador, sin réplicas en Python (la lección de crosscheck aplica también
aquí: testear copias es testear nada).

Caso real que motivó la regla de estabilidad (16-ago-2026): Primicias
(Ecuador), único no-liveblog del día, publicó 181 fallecidos cuando el
consolidado iba por 294 — y la selección antigua lo eligió como «mejor del
día», haciendo retroceder la serie pública.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")

# fixture reducida del feed real del 17-ago (cifras textuales)
FIXTURE = [
    {"search_date": "2026-08-15", "title": "Balance oficial de la UNGRD",
     "publisher": {"name": "El Tiempo"}, "is_liveblog": False,
     "captured_at": "2026-08-16T04:00",
     "cifras": {"fallecidos": 294, "heridos": 3935, "desaparecidos": 320,
                "familias_afectadas": 54008}},
    {"search_date": "2026-08-16", "title": "Gobierno alista declaratoria",
     "publisher": {"name": "Primicias"}, "is_liveblog": False,
     "captured_at": "2026-08-17T04:03",
     "cifras": {"fallecidos": 181, "heridos": 668, "desaparecidos": 195}},
    {"search_date": "2026-08-16", "title": "todas las noticias del sismo",
     "publisher": {"name": "Clarín"}, "is_liveblog": True,
     "captured_at": "2026-08-17T04:03",
     "cifras": {"fallecidos": 294, "heridos": 4000, "desaparecidos": 143,
                "familias_afectadas": 120238}},
]


def correr_ui(expresion: str) -> dict:
    """Carga site/ui.js en node y evalúa una expresión sobre window.UI."""
    script = (
        "global.window = {};"
        f"require({json.dumps(str(ROOT / 'site' / 'ui.js'))});"
        "const UI = window.UI;"
        f"const items = {json.dumps(FIXTURE, ensure_ascii=False)};"
        f"console.log(JSON.stringify({expresion}));"
    )
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                       timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:500]}")
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestSeleccionDiariaBalances(unittest.TestCase):

    def test_el_corte_viejo_no_gana_el_dia(self):
        serie = correr_ui("UI.mejorPorDia(items)")
        ult = serie[-1]
        self.assertEqual(ult["fecha"], "2026-08-16")
        self.assertEqual(ult["item"]["publisher"]["name"], "Clarín",
                         "el liveblog coherente debe ganarle al no-liveblog "
                         "con cifras retrocedidas (caso Primicias)")
        self.assertEqual(ult["item"]["cifras"]["fallecidos"], 294,
                         "la serie no debe retroceder por un corte viejo")

    def test_la_disputa_se_detecta_y_se_reporta(self):
        serie = correr_ui("UI.mejorPorDia(items)")
        disputa = serie[-1]["disputa"]
        self.assertIsNotNone(disputa, "181 vs 294 fallecidos es disputa")
        self.assertEqual(disputa["fallecidos"]["min"], 181)
        self.assertEqual(disputa["fallecidos"]["max"], 294)

    def test_sin_vispera_no_hay_penalizacion(self):
        # el primer día de la serie no tiene referencia: rige la regla clásica
        primero = correr_ui("UI.mejorPorDia(items.slice(0, 1))")[0]
        self.assertEqual(primero["item"]["publisher"]["name"], "El Tiempo")

    def test_el_dato_no_desaparece_si_el_dia_no_lo_trae(self):
        # el día 16 gana Clarín (sí trae familias); pero si el ganador no
        # trajera una cifra, el consolidado conserva el último valor conocido
        # con su fecha de origen
        caso = correr_ui(
            "UI.mejorPorDia(items.slice(0,1).concat([{search_date:'2026-08-16',"
            "publisher:{name:'X'},is_liveblog:false,captured_at:'2026-08-17',"
            "cifras:{fallecidos:300}}]))")
        cons = caso[-1]["consolidado"]
        self.assertEqual(cons["familias_afectadas"]["valor"], 54008,
                         "familias no debe desaparecer del consolidado")
        self.assertEqual(cons["familias_afectadas"]["fecha"], "2026-08-15",
                         "el valor arrastrado declara su fecha de origen")
        self.assertEqual(cons["fallecidos"]["fecha"], "2026-08-16",
                         "el dato fresco lleva la fecha del día")

    def test_una_correccion_oficial_leve_no_se_penaliza(self):
        # -5% respecto a la víspera es corrección plausible, no corte viejo
        caso = correr_ui(
            "UI.mejorPorDia(items.slice(0,1).concat([{search_date:'2026-08-16',"
            "publisher:{name:'X'},is_liveblog:false,captured_at:'2026-08-17',"
            "cifras:{fallecidos:280,familias_afectadas:54008}}]))")
        self.assertEqual(caso[-1]["item"]["cifras"]["fallecidos"], 280)


if __name__ == "__main__":
    unittest.main(verbosity=2)
