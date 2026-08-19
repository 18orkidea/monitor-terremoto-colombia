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
class TestSilencioDePrensa(unittest.TestCase):
    """«Damnificados y ni un titular» es una afirmación pública, y no todos los
    ceros la sostienen igual. Solo afirma el nivel donde el monitor SÍ preguntó:
    topónimo sin ambigüedad y búsqueda propia de prensa. El resto se cuenta,
    pero se cuenta diciendo qué lo hace incierto."""

    MUNS = [
        # nombre sin ambigüedad y búsqueda propia: su cero SÍ se puede afirmar
        {"municipio": "Quinchía", "departamento": "Risaralda", "rud_personas": 2390,
         "n_noticias": 0, "tasa_rud_pct": 8.5196, "busqueda_propia": True},
        {"municipio": "Bagadó", "departamento": "Chocó", "rud_personas": 1133,
         "n_noticias": 0, "tasa_rud_pct": 8.7585, "busqueda_propia": True},
        # exige departamento: cuenta en el total, pero no se afirma
        {"municipio": "Andalucía", "departamento": "Valle del Cauca",
         "rud_personas": 1494, "n_noticias": 0, "requiere_depto": True,
         "tasa_rud_pct": 5.95, "busqueda_propia": True},
        # entró solo desde el RUD: el monitor ni siquiera pregunta por él
        {"municipio": "Tello", "departamento": "Huila", "rud_personas": 232,
         "n_noticias": 0, "requiere_depto": True, "tasa_rud_pct": 1.83,
         "busqueda_propia": False},
        # homónimo de departamento: no tiene cero, tiene ausencia de dato
        {"municipio": "Risaralda", "departamento": "Caldas", "rud_personas": 867,
         "n_noticias": None, "homonimo_de_departamento": True},
        # con prensa del evento: no es silencio
        {"municipio": "Pereira", "departamento": "Risaralda", "rud_personas": 5000,
         "n_noticias": 432, "busqueda_propia": True},
        # sin registro oficial: no hay damnificados que contrastar
        {"municipio": "Salento", "departamento": "Quindío", "n_noticias": 0,
         "busqueda_propia": True},
    ]

    def _sil(self, muns):
        return correr_ui(f"UI.silencioDePrensa({json.dumps(muns, ensure_ascii=False)})")

    def test_solo_cuentan_los_que_tienen_damnificados_y_cero_titulares(self):
        sil = self._sil(self.MUNS)
        self.assertEqual(sil["mudos"], 4)   # Quinchía, Bagadó, Andalucía, Tello
        self.assertEqual(sil["personas"], 2390 + 1133 + 1494 + 232)

    def test_solo_afirma_donde_el_monitor_pregunto(self):
        sil = self._sil(self.MUNS)
        self.assertEqual(sil["ciertos"], ["Quinchía", "Bagadó"])
        self.assertEqual(sil["personas_ciertas"], 2390 + 1133)
        self.assertEqual(sil["dudosos"], 2)

    def test_sin_busqueda_propia_no_se_afirma_aunque_el_nombre_sea_claro(self):
        # el caso que motivó el nivel: 23 municipios que entraron solos desde el
        # RUD nunca han tenido búsqueda de prensa. Su cero es del monitor.
        claro_sin_feed = {"municipio": "Sipí", "departamento": "Chocó",
                          "rud_personas": 400, "n_noticias": 0,
                          "tasa_rud_pct": 9.9, "busqueda_propia": False}
        sil = self._sil([*self.MUNS, claro_sin_feed])
        self.assertNotIn("Sipí", sil["ciertos"])
        self.assertEqual(sil["sin_busqueda"], 2)

    def test_si_falta_el_dato_de_la_busqueda_no_se_afirma(self):
        """El nivel que afirma falla CERRADO. Si el campo no viniera —un JSON
        viejo, o alguien llamando a build_municipios sin el conjunto de
        búsquedas—, un municipio por el que nunca se preguntó pasaría a «sí
        preguntamos y no hubo nada». Prefiere no afirmar nada."""
        sin_campo = [{k: v for k, v in m.items() if k != "busqueda_propia"}
                     for m in self.MUNS]
        self.assertEqual(self._sil(sin_campo)["ciertos"], [])

    def test_solo_se_nombra_aparte_al_homonimo_de_departamento(self):
        # el texto afirma la causa, así que el filtro la comprueba: una celda
        # vacía por cualquier otro motivo no puede colarse en ese nivel
        raro = {"municipio": "Sin causa", "departamento": "X", "rud_personas": 10,
                "n_noticias": None}
        sil = self._sil([*self.MUNS, raro])
        self.assertEqual(sil["sin_atribucion"], 1)
        self.assertEqual(sil["personas_sin_atribucion"], 867)

    def test_el_techo_es_el_mayor_porcentaje_de_verdad(self):
        """El banner dice «hasta el X %». Si otro de la lista lo supera, el
        banner miente: el techo se calcula por tasa, no por número de personas
        (Bagadó tiene menos damnificados que Quinchía y más proporción)."""
        sil = self._sil(self.MUNS)
        self.assertEqual(sil["techo"]["municipio"], "Bagadó")
        tasas = [m["tasa_rud_pct"] for m in self.MUNS
                 if m["municipio"] in sil["ciertos"]]
        self.assertEqual(sil["techo"]["tasa_rud_pct"], max(tasas))

    def test_el_homonimo_se_nombra_aparte_y_no_entra_en_el_total(self):
        # su celda es ausencia de dato (None), no un cero: R3. Pero es el más
        # invisible de todos y el banner lo dice en su propio nivel.
        sil = self._sil(self.MUNS)
        self.assertNotIn("Risaralda", sil["ciertos"])
        self.assertEqual(sil["personas"], 5249)
        self.assertEqual(sil["sin_atribucion"], 1)
        self.assertEqual(sil["personas_sin_atribucion"], 867)

    def test_si_nadie_queda_mudo_no_hay_afirmacion(self):
        # R11: el día que todos tengan prensa, el banner desaparece
        self.assertIsNone(self._sil([self.MUNS[5]]))
        self.assertIsNone(self._sil([]))


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



@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestMedioDeUnaNoticia(unittest.TestCase):
    """El campo `medio` guarda el FEED, no la cabecera. La regla que distingue
    uno de otro vive en ui.js y la comparten la página de titulares y las
    fichas municipales: si se duplicara, una de las dos contaría feeds."""

    def _medio(self, noticia):
        return correr_ui(f"UI.medioDe({json.dumps(noticia, ensure_ascii=False)})")

    def _via(self, noticia):
        return correr_ui(f"UI.viaGoogleNews({json.dumps(noticia, ensure_ascii=False)})")

    def test_manda_la_cabecera_no_el_feed(self):
        self.assertEqual(self._medio({
            "medio": "Google News — Palmira", "medio_canonico": "El Tiempo",
            "url": "https://news.google.com/rss/articles/AAA"}), "El Tiempo")

    def test_sin_cabecera_no_se_pone_el_feed_en_su_lugar(self):
        """«Google News — Nóvita» no es un medio: dar ese nombre por cabecera es
        lo que hacía falsa la métrica de pluralidad."""
        self.assertIsNone(self._medio({
            "medio": "Google News — Nóvita", "medio_canonico": None,
            "url": "https://news.google.com/rss/articles/BBB"}))

    def test_en_feed_propio_el_nombre_del_feed_si_es_el_medio(self):
        self.assertEqual(self._medio({
            "medio": "El Colombiano", "medio_canonico": None,
            "url": "https://www.elcolombiano.com/algo"}), "El Colombiano")

    def test_via_google_news_solo_cuando_el_enlace_va_al_agregador(self):
        self.assertTrue(self._via({"url": "https://news.google.com/rss/articles/AAA"}))
        self.assertFalse(self._via({"url": "https://www.eltiempo.com/algo"}))
        self.assertFalse(self._via({}))

    def test_un_dominio_que_solo_parece_google_news_no_cuela(self):
        """Mismo cuidado que R10 con los topónimos, aquí con los hosts:
        `news.google.com.ejemplo.co` es otro sitio."""
        self.assertFalse(self._via({"url": "https://news.google.com.ejemplo.co/x"}))
        self.assertFalse(self._via({"url": "https://fakenews.google.common.co/x"}))

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


@unittest.skipUnless(NODE, "node no disponible")
class TestTotalSatelital(unittest.TestCase):
    """El total de la portada suma las DOS miradas satelitales.

    Hasta el 20-ago-2026 la tarjeta anunciaba «Satélite · Copernicus» con 622
    edificios y callaba los 385 que UNITAR-UNOSAT había clasificado en Caldas:
    la portada publicaba menos de lo que el propio monitor tenía archivado.
    Sumarlas solo es lícito porque miran municipios distintos, así que la
    condición viaja con el dato y el test la vigila en los dos sentidos: que
    sume cuando no se pisan y que deje de sumar cuando se pisen.
    """

    MON = {
        "fecha": "2026-08-20",
        "aois": [{"resumen": {"edificios_afectados": 400}},
                 {"resumen": {"edificios_afectados": 222}},
                 {"resumen": {"edificios_afectados": None}}],
        "entregas": [{"fecha": "2026-08-18"}],
        "unosat": {"edificios": 385, "observados": 96, "posibles": 289,
                   "otros_eventos": 8,
                   "municipios": ["Anserma", "Manizales", "Viterbo"],
                   "municipios_tambien_en_aoi_copernicus": []},
        "citizen": {"chatmap_total": 439, "en_aoi": 100},
    }

    def _satelite(self, mon):
        fuentes = correr_ui("UI.comparativaFuentes("
                            f"{json.dumps(mon, ensure_ascii=False)}, null)")
        return next(f for f in fuentes if f["id"] == "satelite")

    def test_suma_las_dos_miradas_cuando_no_se_pisan(self):
        sat = self._satelite(self.MON)
        self.assertEqual(sat["cifras"]["edificios_dañados"], 1007,
                         "622 de Copernicus + 385 de UNOSAT")
        self.assertEqual(sat["cifras"]["edificios_copernicus"], 622)
        self.assertEqual(sat["cifras"]["edificios_unosat"], 385)
        self.assertIn("UNOSAT", sat["nombre"],
                      "la tarjeta que suma dos fuentes debe nombrarlas")
        self.assertIn("Copernicus", sat["nombre"])

    def test_la_nota_declara_de_que_esta_hecha_la_cifra(self):
        """Una cifra compuesta que no dice de qué se compone no es rastreable:
        el "daño posible" de UNOSAT no puede desaparecer dentro del total."""
        nota = self._satelite(self.MON)["nota"]
        for pieza in ("622", "385", "289", "Copernicus", "UNOSAT"):
            self.assertIn(pieza, nota, f"la nota calla {pieza}")

    def test_si_las_dos_miran_el_mismo_municipio_deja_de_sumar(self):
        """Doble conteo del mismo tejado: peor que quedarse corto. La ingesta
        publica la lista de municipios compartidos y el sitio la obedece."""
        mon = {**self.MON, "unosat": {**self.MON["unosat"],
                                      "municipios_tambien_en_aoi_copernicus": ["Pereira"]}}
        sat = self._satelite(mon)
        self.assertEqual(sat["cifras"]["edificios_dañados"], 622)
        self.assertIsNone(sat["cifras"]["edificios_unosat"])
        self.assertNotIn("UNOSAT", sat["nombre"])

    def test_un_monitor_sin_unosat_no_revienta(self):
        """El archivo histórico tiene monitor.json anteriores a UNOSAT: la
        portada debe seguir pintándose con la única mirada que haya."""
        mon = {k: v for k, v in self.MON.items() if k != "unosat"}
        sat = self._satelite(mon)
        self.assertEqual(sat["cifras"]["edificios_dañados"], 622)
        self.assertIn("zonas urbanas", sat["alcance"])
