"""Extracción de cifras y de fecha de corte en el worker de balances.

El 18-ago-2026 la UNGRD publicó «Población: 304 personas fallecidas, 4.548
heridas, 426 desaparecidas y 356 personas rescatadas». El worker guardó
`personas_afectadas: 304` —que eran los muertos— y perdió heridos, rescatados y
fallecidos: el patrón laxo de «personas» se llevaba la primera cifra, y los de
víctimas exigían masculino. Con eso, la portada publicó 304 afectados donde la
víspera declaraba 186.016.

Como en tests/test_worker_toponimos.py, estos tests ejecutan EL código del
worker con node, no una réplica en Python: testear copias es testear nada.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
WORKER = ROOT / "workers" / "ai-view" / "src" / "index.js"

if not NODE and os.environ.get("CI"):
    raise RuntimeError(
        "node no está disponible en el runner: las reglas del monitor que viven "
        "en JavaScript no se pueden verificar. Instalar node o quitar el paso.")

# El boletín real, tal como lo publica la UNGRD. Es la plantilla que repite en
# cada actualización, así que lo que falle aquí falla todos los días.
BOLETIN = ("Población: 304 personas fallecidas, 4.548 heridas, 426 desaparecidas "
           "y 356 personas rescatadas. Vivienda: 134.342 viviendas averiadas, "
           "29.554 destruidas.")


def correr_worker(expresion: str):
    """Importa el worker en node y evalúa una expresión sobre sus exports."""
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "worker.mjs"
        copia.write_bytes(WORKER.read_bytes())
        script = (f"const W = await import({json.dumps(copia.as_uri())});"
                  f"console.log(JSON.stringify({expresion}));")
        r = subprocess.run([NODE, "--input-type=module", "-"], input=script,
                           capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:600]}")
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestExtraccionDelBoletin(unittest.TestCase):

    def cifras(self, texto):
        return correr_worker(f"W.extraerCifras({json.dumps(texto)})")

    def test_el_boletin_de_la_ungrd_se_extrae_entero(self):
        c = self.cifras(BOLETIN)
        self.assertEqual(c["fallecidos"], 304)
        self.assertEqual(c["heridos"], 4548)
        self.assertEqual(c["desaparecidos"], 426)
        self.assertEqual(c["rescatados"], 356)
        self.assertEqual(c["viviendas_averiadas"], 134342)
        self.assertEqual(c["viviendas_destruidas"], 29554)

    def test_las_personas_afectadas_no_se_llevan_a_los_fallecidos(self):
        # el bug exacto: «304 personas fallecidas» daba personas_afectadas=304
        self.assertIsNone(self.cifras(BOLETIN)["personas_afectadas"],
                          "el boletín no dice cuántos afectados hay")

    def test_las_victimas_en_femenino_cuentan(self):
        c = self.cifras("Hay 4.548 heridas y 426 desaparecidas.")
        self.assertEqual(c["heridos"], 4548)
        self.assertEqual(c["desaparecidos"], 426)

    def test_la_prensa_en_masculino_sigue_funcionando(self):
        # no basta con arreglar el caso nuevo: el viejo tiene que seguir vivo
        c = self.cifras("La UNGRD reportó 294 muertos, 3.935 heridos y 320 "
                        "desaparecidos, con 54.008 familias afectadas.")
        self.assertEqual((c["fallecidos"], c["heridos"], c["desaparecidos"],
                          c["familias_afectadas"]), (294, 3935, 320, 54008))

    def test_las_personas_afectadas_se_extraen_cuando_las_hay(self):
        c = self.cifras("El sismo dejó 115.461 personas afectadas en 448 "
                        "municipios afectados de 15 departamentos afectados.")
        self.assertEqual(c["personas_afectadas"], 115461)
        self.assertEqual(c["municipios_afectados"], 448)
        self.assertEqual(c["departamentos_afectados"], 15)

    def test_un_municipio_sin_adjetivo_no_se_cuenta_como_afectado(self):
        # «448 municipios» a secas puede ser cualquier cosa —los del país, los
        # de un departamento—: la cifra necesita que el texto diga de qué habla
        c = self.cifras("El sismo se sintió en 448 municipios del occidente.")
        self.assertIsNone(c["municipios_afectados"])


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestVigilanteDeExtraccion(unittest.TestCase):

    def vigilar(self, texto):
        t = json.dumps(texto)
        return correr_worker(f"W.extraerCifrasVigiladas({t}, {t})")

    def test_un_balance_sano_no_se_reintenta(self):
        r = self.vigilar(BOLETIN)
        self.assertEqual(len(r["extraccion_intentos"]), 1)
        self.assertIsNone(r["extraccion_descartada"])

    def test_una_cifra_imposible_se_reintenta_y_se_desestima(self):
        r = self.vigilar("Reporte: 304 personas afectadas. Desaparecidos: 426.")
        self.assertEqual(len(r["extraccion_intentos"]), 2,
                         "primero se reintenta, no se descarta a la primera")
        self.assertEqual(r["extraccion_descartada"]["cifras"],
                         ["personas_afectadas"])
        self.assertIsNone(r["cifras"]["personas_afectadas"])

    def test_lo_desestimado_no_arrastra_al_resto_del_balance(self):
        r = self.vigilar("Reporte: 304 personas afectadas. Desaparecidos: 426 "
                         "y 134.342 viviendas averiadas.")
        self.assertEqual(r["cifras"]["viviendas_averiadas"], 134342)
        self.assertEqual(r["cifras"]["desaparecidos"], 426)

    def test_menos_personas_que_familias_es_imposible(self):
        rotas = correr_worker(
            'W.incoherenciasDeCifras({personas_afectadas: 117000,'
            ' familias_afectadas: 120238})')
        self.assertTrue(rotas, "una familia tiene al menos una persona")


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestFechaDeCorte(unittest.TestCase):
    """La fecha del corte es lo que convierte una lista de capturas en una
    serie temporal. La trampa es la fecha del propio terremoto: casi toda
    noticia dice «el sismo del 10 de agosto»."""

    def corte(self, texto):
        return correr_worker(f"W.findCutoffDate({json.dumps(texto)})")

    def test_el_titular_fecha_el_balance(self):
        self.assertEqual(
            self.corte("Balance oficial de la UNGRD este 15 de agosto"),
            "2026-08-15")

    def test_la_fecha_del_terremoto_no_fecha_un_balance(self):
        # EL test de la trampa: sin esto, cualquier noticia sería del 10-ago
        self.assertIsNone(
            self.corte("El terremoto del 10 de agosto dejó cientos de muertos"))

    def test_entre_la_del_evento_y_la_del_corte_gana_la_del_corte(self):
        self.assertEqual(
            self.corte("Tras el sismo del 10 de agosto, el balance del 17 de "
                       "agosto suma 289 muertos"),
            "2026-08-17")

    def test_una_noticia_sin_corte_declarado_no_se_inventa_uno(self):
        self.assertIsNone(
            self.corte("Estos son los municipios más afectados por el sismo"))

    def test_reconoce_la_formula_del_corte_administrativo(self):
        self.assertEqual(self.corte("Cifras con corte al 18 de agosto de 2026"),
                         "2026-08-18")


if __name__ == "__main__":
    unittest.main()
