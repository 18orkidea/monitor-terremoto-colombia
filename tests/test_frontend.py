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
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")

# R11: en local se puede saltar (node es opcional para el pipeline Python), pero
# en CI la ausencia de node dejaría los guardianes de JavaScript apagados en
# silencio — justo lo que estas reglas existen para evitar.
if not NODE and os.environ.get("CI"):
    raise RuntimeError(
        "node no está disponible en el runner: las reglas del monitor que viven "
        "en JavaScript no se pueden verificar. Instalar node o quitar el paso.")


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
    {"search_date": "2026-08-16", "title": "Terremoto en Colombia hoy 16",
     "publisher": {"name": "El Tiempo"}, "is_liveblog": True,
     "captured_at": "2026-08-17T04:03",
     "cifras": {"desaparecidos": 143, "familias_afectadas": 120238}},
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
        self.assertEqual(ult["item"]["publisher"]["name"], "El Tiempo",
                         "gana el diario nacional coherente, no el "
                         "internacional con cifras retrocedidas (Primicias) "
                         "ni el internacional coherente (Clarín)")
        self.assertEqual(ult["consolidado"]["fallecidos"]["valor"], 294,
                         "la serie no debe retroceder por un corte viejo")
        self.assertEqual(ult["consolidado"]["fallecidos"]["fecha"], "2026-08-15",
                         "El Tiempo del 16 no trae fallecidos: se conserva "
                         "el 294 de la víspera con su fecha de origen")

    def test_nacional_le_gana_al_internacional_coherente(self):
        # solo Clarín (internacional) y El Tiempo (nacional), ambos liveblog
        # y coherentes: debe mostrarse el diario nacional
        caso = correr_ui("UI.mejorPorDia(items.filter(x => "
                         "x.publisher.name !== 'Primicias'))")
        self.assertEqual(caso[-1]["item"]["publisher"]["name"], "El Tiempo")

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


@unittest.skipUnless(NODE, "node no disponible")
class TestConstantesPush(unittest.TestCase):
    """El botón 🔔 depende de estas constantes de ui.js: si la clave VAPID
    está mal formada, la suscripción falla en silencio en el navegador."""

    def test_push_base_y_clave_vapid(self):
        out = correr_ui(
            "({ base: UI.PUSH_BASE, clave: UI.VAPID_PUBLIC_KEY,"
            "  bytes: UI.VAPID_PUBLIC_KEY ? "
            "Buffer.from(UI.VAPID_PUBLIC_KEY.replaceAll('-','+')"
            ".replaceAll('_','/'), 'base64').length : 0 })")
        self.assertTrue(out["base"].startswith("https://"))
        if out["clave"]:  # vacía = worker aún sin desplegar (botón oculto)
            self.assertEqual(out["bytes"], 65,
                             "la clave VAPID pública debe ser P-256 sin "
                             "comprimir (65 bytes) en base64url")


@unittest.skipUnless(NODE, "node no disponible")
class TestFraseHomonimos(unittest.TestCase):
    """La salvedad de los homónimos de departamento se genera desde los datos.
    Nació partiendo la frase en dos («alcaldía. —salvo Córdoba…») porque el
    punto se quedó en el HTML: la puntuación tiene que viajar con el texto
    generado, no con la plantilla."""

    MUNS = [
        {"municipio": "Risaralda", "departamento": "Caldas",
         "homonimo_de_departamento": True, "estado": "solo_rud"},
        {"municipio": "Córdoba", "departamento": "Quindío",
         "homonimo_de_departamento": True, "estado": "solo_rud"},
        {"municipio": "Condoto", "departamento": "Chocó", "estado": "solo_rud"},
    ]

    def _frase(self, muns):
        return correr_ui(f"UI.fraseHomonimos({json.dumps(muns, ensure_ascii=False)})")

    def test_cierra_la_frase_cuando_no_hay_homonimos(self):
        self.assertEqual(self._frase([self.MUNS[2]]), ".")
        self.assertEqual(self._frase([]), ".")

    def test_enumera_los_homonimos_sin_partir_la_frase(self):
        frase = self._frase(self.MUNS)
        self.assertTrue(frase.startswith(", salvo "), frase)
        self.assertIn("Risaralda (Caldas)", frase)
        self.assertIn("Córdoba (Quindío)", frase)
        self.assertNotIn("Condoto", frase)
        self.assertTrue(frase.endswith("."), frase)
        # la costura original: punto del HTML + raya de la salvedad
        self.assertNotIn(". —", frase)

    def test_no_nombra_al_homonimo_que_dejo_de_ser_solo_rud(self):
        # si mañana tiene prensa, deja de ser excepción del párrafo que lo cita
        con_prensa = [{**self.MUNS[0], "estado": "mencion_prensa"}]
        self.assertEqual(self._frase(con_prensa), ".")


@unittest.skipUnless(NODE, "node no disponible")
class TestOrdenDeTabla(unittest.TestCase):
    """Ordenación por columna (site/ui.js::comparador). Los nulos van SIEMPRE al
    final: un municipio sin dato no puede encabezar la tabla al ordenar por esa
    columna, ni ascendente ni descendente."""

    FILAS = [
        {"n": "B", "v": 2}, {"n": "A", "v": None}, {"n": "C", "v": 1},
        {"n": "D", "v": None}, {"n": "E", "v": 3},
    ]

    def _orden(self, dir_):
        return correr_ui(
            f"[...{json.dumps(self.FILAS)}].sort("
            f"UI.comparador((r) => r.v, {json.dumps(dir_)},"
            " (a, b) => a.n.localeCompare(b.n))).map((r) => r.n)")

    def test_los_nulos_quedan_al_final_en_ambos_sentidos(self):
        self.assertEqual(self._orden("asc"), ["C", "B", "E", "A", "D"])
        self.assertEqual(self._orden("desc"), ["E", "B", "C", "A", "D"])

    def test_el_desempate_hace_el_orden_estable(self):
        empatados = [{"n": "Z", "v": 5}, {"n": "M", "v": 5}, {"n": "A", "v": 5}]
        out = correr_ui(
            f"[...{json.dumps(empatados)}].sort("
            "UI.comparador((r) => r.v, 'asc', (a, b) => a.n.localeCompare(b.n)))"
            ".map((r) => r.n)")
        self.assertEqual(out, ["A", "M", "Z"])

    def test_el_texto_se_ordena_con_criterio_espanol(self):
        # ñ y tildes: «Nóvita» va antes que «Nuquí», no después por el acento
        nombres = [{"n": "Nuquí"}, {"n": "Nóvita"}, {"n": "Ánimas"}]
        out = correr_ui(
            f"[...{json.dumps(nombres)}].sort("
            "UI.comparador((r) => r.n, 'asc')).map((r) => r.n)")
        self.assertEqual(out, ["Ánimas", "Nóvita", "Nuquí"])


@unittest.skipUnless(NODE, "node no disponible")
class TestIndiceDeBusqueda(unittest.TestCase):
    """El índice del buscador estaba precomputado POR POSICIÓN. `filtroExtra`
    recorta las filas antes de que actúe el buscador, así que desde la primera
    fila descartada el índice apuntaba al texto de otra y el buscador devolvía
    el municipio equivocado. Por eso se indexa por identidad."""

    def test_el_buscador_acierta_con_filtro_y_orden_activos(self):
        out = correr_ui("""(() => {
            const filas = [
              {m: 'Cali', d: 'Valle', pob: 2269983, nuevo: false},
              {m: 'Condoto', d: 'Chocó', pob: 12620, nuevo: true},
              {m: 'Quibdó', d: 'Chocó', pob: 8817, nuevo: true},
            ];
            let html = '';
            const tbody = { set innerHTML(v) { html = v; } };
            const input = { value: '' };
            let alternar = null;
            const th = { classList: { add() {} }, setAttribute() {}, title: '',
                         set onclick(f) { alternar = f; }, set onkeydown(f) {} };
            const pinta = UI.tablaBuscable({
              tbody, input, rows: filas, top: 10,
              texto: (r) => r.m + ' ' + r.d,
              fila: (r) => '<tr><td>' + r.m + '</td></tr>',
              filtroExtra: (r) => r.nuevo,   // descarta Cali, la PRIMERA fila
              columnas: [{ th, valor: (r) => r.pob }],
            });
            alternar();                      // y además ordena por población
            input.value = 'quibdo'; pinta({ reiniciar: true });
            const trasQuibdo = html;
            input.value = 'condoto'; pinta({ reiniciar: true });
            return { quibdo: trasQuibdo, condoto: html };
        })()""")
        self.assertIn("Quibdó", out["quibdo"])
        self.assertNotIn("Condoto", out["quibdo"])
        self.assertIn("Condoto", out["condoto"])
        self.assertNotIn("Quibdó", out["condoto"])


@unittest.skipUnless(NODE, "node no disponible")
class TestNotaConoceElOrden(unittest.TestCase):
    """La nota al pie anunciaba «ordenados por personas damnificadas» aunque el
    lector hubiera pulsado otra cabecera: decía lo contrario de lo que mostraba
    la tabla. `notaTexto` recibe el orden vigente."""

    def test_la_nota_recibe_el_orden_vigente(self):
        out = correr_ui("""(() => {
            const filas = [{m: 'Cali', pob: 2269983}, {m: 'Quibdó', pob: 8817}];
            let texto = '';
            const nota = { set textContent(v) { texto = v; } };
            let alternar = null;
            const th = { classList: { add() {} }, setAttribute() {}, title: '',
                         set onclick(f) { alternar = f; }, set onkeydown(f) {} };
            UI.tablaBuscable({
              tbody: { set innerHTML(v) {} }, rows: filas, top: 10,
              texto: (r) => r.m, fila: (r) => '<tr><td>' + r.m + '</td></tr>',
              nota, notaTexto: (q, vis, tot, orden) =>
                orden ? 'col=' + orden.i + ' dir=' + orden.dir : 'sin orden',
              columnas: [{ th, valor: (r) => r.pob }],
            });
            const inicial = texto;
            alternar();
            const asc = texto;
            alternar();
            return { inicial, asc, desc: texto };
        })()""")
        self.assertEqual(out["inicial"], "sin orden")
        self.assertEqual(out["asc"], "col=0 dir=asc")
        self.assertEqual(out["desc"], "col=0 dir=desc")

    def test_el_th_avisa_de_que_se_puede_ordenar(self):
        # el aviso lo pone ui.js: si lo escribiera cada página, unas columnas
        # lo tendrían y otras no (que es lo que pasaba)
        out = correr_ui("""(() => {
            const th = { classList: { add() {} }, setAttribute() {},
                         title: 'Familias registradas.',
                         set onclick(f) {}, set onkeydown(f) {} };
            const sinTitulo = { classList: { add() {} }, setAttribute() {},
                                title: '', set onclick(f) {}, set onkeydown(f) {} };
            UI.tablaBuscable({
              tbody: { set innerHTML(v) {} }, rows: [{v: 1}], top: 10,
              texto: (r) => '', fila: (r) => '<tr></tr>',
              columnas: [{ th, valor: (r) => r.v },
                         { th: sinTitulo, valor: (r) => r.v }],
            });
            return { conTitulo: th.title, sinTitulo: sinTitulo.title };
        })()""")
        self.assertEqual(out["conTitulo"],
                         "Familias registradas. Pulsa para ordenar.")
        self.assertEqual(out["sinTitulo"], "Pulsa para ordenar.")


@unittest.skipUnless(NODE, "node no disponible")
class TestFiltrosDeTabla(unittest.TestCase):
    """`filtroExtra` combina con el buscador y ambos reinician la paginación —
    si no, al filtrar te quedas en una página que ya no existe."""

    FILAS = [
        {"m": "Cali", "d": "Valle", "nuevo": False, "destr": 211},
        {"m": "Buenaventura", "d": "Valle", "nuevo": True, "destr": 0},
        {"m": "Condoto", "d": "Chocó", "nuevo": False, "destr": 22},
        {"m": "Quimbaya", "d": "Quindío", "nuevo": True, "destr": 0},
    ]

    def _con(self, filtro_js, busqueda=""):
        return correr_ui(f"""(() => {{
            const filas = {json.dumps(self.FILAS)};
            let html = '';
            const tbody = {{ set innerHTML(v) {{ html = v; }} }};
            const input = {{ value: {json.dumps(busqueda)} }};
            const opts = {{
              tbody, input, rows: filas, top: 10,
              texto: (r) => r.m + ' ' + r.d,
              fila: (r) => '<tr><td>' + r.m + '</td></tr>',
              filtroExtra: {filtro_js},
            }};
            UI.tablaBuscable(opts);
            return (html.match(/<td>([^<]+)/g) || []).map((x) => x.slice(4));
        }})()""")

    def test_filtra_por_nuevos(self):
        self.assertEqual(sorted(self._con("(r) => r.nuevo")),
                         ["Buenaventura", "Quimbaya"])

    def test_filtra_por_viviendas_destruidas(self):
        self.assertEqual(sorted(self._con("(r) => r.destr > 0")),
                         ["Cali", "Condoto"])

    def test_el_filtro_se_combina_con_el_buscador(self):
        # nuevos + búsqueda «buena»: solo Buenaventura
        self.assertEqual(self._con("(r) => r.nuevo", "buena"), ["Buenaventura"])
        # y un filtro que no deja nada no revienta
        self.assertEqual(self._con("(r) => r.destr > 9999"), [])

    def test_filtra_por_departamento(self):
        self.assertEqual(self._con("(r) => r.d === 'Chocó'"), ["Condoto"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestFichaMapa(unittest.TestCase):
    """Los globos del mapa no pueden inventar respuestas que la fuente no dio.

    Antes, «Western Colombia» —el área de referencia de Copernicus, que no
    trae ninguna cifra— mostraba cuatro renglones de guiones: «Población: —,
    Edificios afectados: —, Vías: — km, Interrupciones: —». Un lector razonable
    entiende que ahí se midió y salió nada, cuando lo que pasa es que nadie
    ha mirado. La etiqueta desaparece con el dato.
    """

    def test_las_filas_sin_dato_no_se_pintan(self):
        html = correr_ui(
            "UI.fichaMapa({titulo:'Occidente de Colombia',"
            " subtitulo:'No comparable 1:1',"
            " filas:[['Población',null],['Edificios afectados',undefined],"
            "        ['Vías',''],['Interrupciones',NaN]]})")
        self.assertNotIn("—", html)
        self.assertNotIn("Población", html)
        self.assertNotIn("Interrupciones", html)
        self.assertIn("Occidente de Colombia", html)
        self.assertIn("No comparable 1:1", html)

    def test_el_cero_si_se_pinta(self):
        """R3 llevada al mapa: un cero medido es un dato. «0 viviendas
        destruidas» es información; borrarlo lo convertiría en ausencia."""
        html = correr_ui(
            "UI.fichaMapa({titulo:'Anserma',"
            " filas:[['Viviendas destruidas',0],['Confianza',null]]})")
        self.assertIn("Viviendas destruidas: 0", html)
        self.assertNotIn("Confianza", html)

    def test_las_filas_con_dato_conservan_su_etiqueta(self):
        html = correr_ui(
            "UI.fichaMapa({titulo:'Buenaventura',filas:["
            "['Población','320.000'],['Vías afectadas',null]],"
            " pie:'Copernicus EMS'})")
        self.assertIn("Población: 320.000", html)
        self.assertNotIn("Vías afectadas", html)
        self.assertIn("Copernicus EMS", html)

    def test_una_fila_sin_etiqueta_es_texto_libre(self):
        """El mensaje de un reporte ciudadano no lleva etiqueta delante."""
        html = correr_ui(
            "UI.fichaMapa({titulo:'Reporte ciudadano',"
            " filas:[['','se cayó el muro'],['Intensidad estimada',null]]})")
        self.assertIn("se cayó el muro", html)
        self.assertNotIn(": se cayó el muro", html)
        self.assertNotIn("Intensidad", html)
