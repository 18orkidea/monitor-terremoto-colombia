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
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
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


# fixture reducida del feed real del 17-ago (cifras textuales). Todos los ítems
# llevan `reported_data_source`, como en el feed real: una cifra sin atribución
# oficial trazable no entra en el consolidado.
CITA = [{"id": "UNGRD", "type": "oficial_nacional"}]
FIXTURE = [
    {"search_date": "2026-08-15", "title": "Balance oficial de la UNGRD",
     "publisher": {"name": "El Tiempo"}, "is_liveblog": False,
     "reported_data_source": CITA,
     "captured_at": "2026-08-16T04:00",
     "cifras": {"fallecidos": 294, "heridos": 3935, "desaparecidos": 320,
                "familias_afectadas": 54008}},
    {"search_date": "2026-08-16", "title": "Gobierno alista declaratoria",
     "publisher": {"name": "Primicias"}, "is_liveblog": False,
     "reported_data_source": CITA,
     "captured_at": "2026-08-17T04:03",
     "cifras": {"fallecidos": 181, "heridos": 668, "desaparecidos": 195}},
    {"search_date": "2026-08-16", "title": "todas las noticias del sismo",
     "publisher": {"name": "Clarín"}, "is_liveblog": True,
     "reported_data_source": CITA,
     "captured_at": "2026-08-17T04:03",
     "cifras": {"fallecidos": 294, "heridos": 4000, "desaparecidos": 143,
                "familias_afectadas": 120238}},
    {"search_date": "2026-08-16", "title": "Terremoto en Colombia hoy 16",
     "publisher": {"name": "El Tiempo"}, "is_liveblog": True,
     "reported_data_source": CITA,
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
class TestSerieGraficoPortada(unittest.TestCase):
    def test_la_presentacion_empieza_el_dia_del_sismo(self):
        serie = correr_ui(
            "UI.serieDesde([{fecha:'2026-08-08'},{fecha:'2026-08-09'},"
            "{fecha:'2026-08-10'},{fecha:'2026-08-11'}], '2026-08-10')"
            ".map((d)=>d.fecha)")
        self.assertEqual(serie, ["2026-08-10", "2026-08-11"])


class TestCronologiaPortada(unittest.TestCase):
    def setUp(self):
        self.hitos = json.loads(
            (ROOT / "feeds" / "hitos_monitor.json").read_text(encoding="utf-8"))

    def test_sertit_es_respuesta_internacional_fuera_de_banda(self):
        sertit = [h for h in self.hitos["hitos"]
                  if h.get("tipo") == "internacional"
                  and "SERTIT" in h.get("texto", "")]
        self.assertEqual(len(sertit), 1)
        self.assertEqual(sertit[0]["fecha"], "2026-08-21")

    def test_cada_hito_del_monitor_tiene_un_resumen_breve(self):
        monitor = [h for h in self.hitos["hitos"] if h.get("tipo") == "monitor"]
        sin_resumen = [h["fecha"] for h in monitor if not h.get("resumen")]
        largos = [(h["fecha"], len(h.get("resumen", ""))) for h in monitor
                  if len(h.get("resumen", "")) > 90]
        self.assertEqual(sin_resumen, [])
        self.assertEqual(largos, [],
                         "los resúmenes deben seguir siendo breves para la banda gráfica")

    def test_cronologia_muestra_el_texto_completo_del_monitor_en_cuatro_lineas(self):
        app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('h.tipo === "monitor" ? h.texto', app)
        self.assertIn("-webkit-line-clamp: 4", css)
        self.assertIn("#timeline {", css)
        self.assertIn("max-width: none; width: 100%", css)

    def test_bloques_explicativos_de_portada_son_fluidos(self):
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        for selector in (r"\.sub", r"\.intro p", r"#metodologia-box p"):
            self.assertIsNotNone(
                re.search(selector + r"[^\{]*\{[^\}]*max-width:\s*none", css),
                f"{selector} conserva un ancho de lectura fijo")
        self.assertRegex(css, r"#alerts-section > ul \{ max-width: none; \}")
        self.assertIn("#panel > .note,", css)
        self.assertIn("#balance-hero .note,", css)
        self.assertIn("#banner-silencio p,", css)
        self.assertIn("#banner-silencio ol { max-width: none; }", css)


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
            "reported_data_source:[{id:'UNGRD'}],"
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
            "reported_data_source:[{id:'UNGRD'}],"
            "cifras:{fallecidos:280,familias_afectadas:54008}}]))")
        self.assertEqual(caso[-1]["item"]["cifras"]["fallecidos"], 280)


def correr_con(items: list, expresion: str):
    """Como correr_ui, pero con una fixture propia: los tests de abajo
    construyen el dato mínimo que viola la propiedad que afirman, en vez de
    copiar el corpus observado (un fixture que fija el comportamiento no
    vigila nada)."""
    # El corpus viaja por STDIN, no como argumento: Linux limita cada
    # argumento de execve a 128 KiB (MAX_ARG_STRLEN) y `oficiales.json` lo
    # cruzó el 23-ago-2026. macOS no tiene ese límite, así que incrustarlo en
    # la línea de órdenes salía verde en local y reventaba en el runner —
    # apagando en silencio los dos guardianes que más importan aquí. Mismo
    # patrón que ingest/alerts.py::_consolidado_de_la_serie.
    script = (
        "global.window = {};"
        f"require({json.dumps(str(ROOT / 'site' / 'ui.js'))});"
        "const UI = window.UI;"
        "const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"console.log(JSON.stringify({expresion}));"
    )
    r = subprocess.run([NODE, "-e", script],
                       input=json.dumps(items, ensure_ascii=False),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:500]}")
    return json.loads(r.stdout)


def captura(fecha, nombre, cifras, **extra):
    """Una captura de balance con lo mínimo que el feed real siempre trae."""
    it = {"search_date": fecha, "title": f"balance {nombre}",
          "publisher": {"name": nombre, "domain": f"{nombre.lower()}.com"},
          "is_liveblog": False, "captured_at": f"{fecha}T04:00",
          "reported_data_source": [{"id": "UNGRD"}], "cifras": cifras}
    it.update(extra)
    return it


# límite de Linux por argumento de execve. macOS no lo tiene: por eso el bug
# del 23-ago-2026 sólo se veía en el runner.
MAX_ARG_STRLEN = 128 * 1024


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestElCorpusNoViajaEnLaLineaDeOrdenes(unittest.TestCase):
    """El guardián que se rompe por su propio peso no guarda nada.

    El 23-ago-2026 `oficiales.json` cruzó los 128 KiB y los dos tests que le
    pasan el corpus entero a node empezaron a morir con `OSError: [Errno 7]
    Argument list too long` — entre ellos el de paridad alertas↔web (R8/R16).
    En el CI (Linux) llevaban dos días apagados; en macOS seguían en verde,
    que es la peor forma de estar roto. Este test vigila la mecánica, no la
    regla: que el tamaño del corpus no llegue nunca a `argv`."""

    def corpus_pasado_del_limite(self):
        """Un corpus deliberadamente mayor que MAX_ARG_STRLEN, con la forma
        mínima que `UI.fechaCorte` sabe leer."""
        items = [{"fecha": "2026-08-14", "relleno": "x" * 300}
                 for _ in range(600)]
        assert len(json.dumps(items).encode()) > MAX_ARG_STRLEN
        return items

    def test_un_corpus_mayor_que_el_limite_de_execve_no_revienta(self):
        items = self.corpus_pasado_del_limite()
        self.assertEqual(correr_con(items, "items.length"), len(items),
                         "el corpus real ya no cabe en la línea de órdenes")

    def test_ningun_argumento_crece_con_el_corpus(self):
        """La comprobación que falla en cualquier sistema, no sólo en Linux:
        si el corpus vuelve a incrustarse en el script, este argumento pasa
        del límite y aquí se ve — en macOS también."""
        medido = {}
        real = subprocess.run

        def espia(cmd, **kw):
            medido["mayor"] = max(len(a.encode()) for a in cmd)
            return real(cmd, **kw)

        with unittest.mock.patch.object(subprocess, "run", espia):
            correr_con(self.corpus_pasado_del_limite(), "items.length")
        self.assertLess(
            medido["mayor"], MAX_ARG_STRLEN,
            "el corpus volvió a viajar como argumento de node: en el runner "
            "de Linux esto es OSError [Errno 7] y el guardián se apaga solo. "
            "Pasarlo por STDIN, como ingest/alerts.py")


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestConsolidadoMonotono(unittest.TestCase):
    """El caso real que motivó la regla (19-ago-2026): el sitio publicaba
    11.132 familias afectadas donde el RUD registraba 65.663, porque un
    liveblog del día 10 ganó el día y el consolidado adoptó su cifra."""

    def test_ninguna_cifra_del_balance_retrocede(self):
        # todas las cifras bajan de golpe al día siguiente: ninguna debe caer
        altas = {"departamentos_afectados": 15, "municipios_afectados": 450,
                 "personas_afectadas": 186016, "familias_afectadas": 120328,
                 "viviendas_averiadas": 127557, "viviendas_destruidas": 26945,
                 "heridos": 4187, "fallecidos": 294, "desaparecidos": 426,
                 "rescatados": 356}
        bajas = {k: max(1, v // 10) for k, v in altas.items()}
        serie = correr_con(
            [captura("2026-08-18", "Bueno", altas),
             captura("2026-08-19", "CorteViejo", bajas)],
            "UI.mejorPorDia(items)")
        cons = serie[-1]["consolidado"]
        for cifra, alto in altas.items():
            self.assertEqual(cons[cifra]["valor"], alto,
                             f"{cifra} retrocedió: un acumulado no baja")
            self.assertEqual(cons[cifra]["fecha"], "2026-08-18",
                             f"{cifra} debe declarar de qué día es el máximo")

    def test_la_cifra_rechazada_se_registra_no_se_borra(self):
        # la discrepancia es brecha (R12): lo que no entra queda con su motivo
        serie = correr_con(
            [captura("2026-08-18", "Bueno", {"familias_afectadas": 120328}),
             captura("2026-08-19", "Viejo", {"familias_afectadas": 11132})],
            "UI.mejorPorDia(items)")
        ignoradas = serie[-1]["ignoradas"]
        self.assertTrue(any(g["cifra"] == "familias_afectadas"
                            and g["valor"] == 11132 for g in ignoradas),
                        "la cifra rechazada debe verse, no desaparecer")
        self.assertTrue(any("retrocede" in g["motivo"] for g in ignoradas))

    def test_cada_cifra_declara_su_medio_de_origen(self):
        # una tarjeta que arrastra un valor tiene que decir de quién es
        serie = correr_con(
            [captura("2026-08-18", "Caracol", {"familias_afectadas": 120328})],
            "UI.mejorPorDia(items)")
        celda = serie[-1]["consolidado"]["familias_afectadas"]
        self.assertEqual(celda["medio"], "Caracol")
        self.assertIn("fecha", celda)

    def test_un_salto_desmedido_se_marca_y_no_entra(self):
        # con monotonía, un error de extracción al alza sería permanente:
        # el worker ya produjo «900 municipios» desde mapa-900x601.jpg
        serie = correr_con(
            [captura("2026-08-18", "Bueno", {"familias_afectadas": 120328}),
             captura("2026-08-19", "Disparate",
                     {"familias_afectadas": 120328 * 9})],
            "UI.mejorPorDia(items)")
        self.assertEqual(
            serie[-1]["consolidado"]["familias_afectadas"]["valor"], 120328)
        self.assertTrue(any("salto" in g["motivo"] for g in serie[-1]["ignoradas"]),
                        "el salto se marca; no se descarta en silencio")

    def test_un_salto_grande_pero_plausible_si_entra(self):
        # Clarín pasó de 54.008 a 120.238 familias el 16-ago (×2,2): es real
        serie = correr_con(
            [captura("2026-08-15", "ElTiempo", {"familias_afectadas": 54008}),
             captura("2026-08-16", "Clarin", {"familias_afectadas": 120238})],
            "UI.mejorPorDia(items)")
        self.assertEqual(
            serie[-1]["consolidado"]["familias_afectadas"]["valor"], 120238)

    def test_sin_atribucion_oficial_la_cifra_no_se_publica(self):
        # R9: lo que no se puede atribuir a nadie no alimenta la serie
        anon = captura("2026-08-19", "Anonimo", {"familias_afectadas": 999999})
        anon["reported_data_source"] = []
        serie = correr_con(
            [captura("2026-08-18", "Bueno", {"familias_afectadas": 120328}),
             anon], "UI.mejorPorDia(items)")
        self.assertEqual(
            serie[-1]["consolidado"]["familias_afectadas"]["valor"], 120328)
        self.assertTrue(any("atribución" in g["motivo"]
                            for g in serie[-1]["ignoradas"]))

    def test_la_comunicacion_oficial_directa_si_cuenta(self):
        # el boletín lo publica la propia UNGRD: no cita a nadie porque ES
        # la fuente. `official` vale como atribución.
        propio = captura("2026-08-18", "UNGRD", {"viviendas_averiadas": 134342})
        propio["reported_data_source"] = []
        propio["official"] = True
        serie = correr_con([propio], "UI.mejorPorDia(items)")
        self.assertEqual(
            serie[-1]["consolidado"]["viviendas_averiadas"]["valor"], 134342)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestSeleccionDelDia(unittest.TestCase):

    def test_un_candidato_sin_anclas_no_gana_el_dia(self):
        # el 18-ago ganó un post con tres cifras y ninguna ancla, por delante
        # de uno con diez: `retrocede` no lo frenaba porque no traía con qué
        mudo = captura("2026-08-18", "Mudo",
                       {"desaparecidos": 426, "viviendas_averiadas": 134342})
        rico = captura("2026-08-18", "Rico",
                       {"fallecidos": 304, "familias_afectadas": 123789,
                        "personas_afectadas": 292043})
        serie = correr_con([mudo, rico], "UI.mejorPorDia(items)")
        self.assertEqual(serie[-1]["item"]["publisher"]["name"], "Rico",
                         "gana quien trae las cifras ancla")

    def test_el_guardarrail_no_se_desactiva_tras_un_dia_mudo(self):
        # EL test del 11.132: día 1 bueno, día 2 sin anclas, día 3 corte viejo.
        # Si la referencia fuera el ítem de la víspera, el día 3 pasaría.
        mudo = captura("2026-08-19", "Mudo", {"desaparecidos": 426})
        serie = correr_con(
            [captura("2026-08-18", "Bueno",
                     {"fallecidos": 304, "familias_afectadas": 123789}),
             mudo,
             captura("2026-08-20", "Viejo",
                     {"fallecidos": 180, "familias_afectadas": 11132})],
            "UI.mejorPorDia(items)")
        self.assertEqual(
            serie[-1]["consolidado"]["familias_afectadas"]["valor"], 123789,
            "un día sin anclas no puede dejar ciego al guardarraíl")

    def test_un_liveblog_que_cita_oficiales_gana_a_un_estatico_mudo(self):
        # R8 dice «se marcan y pesan menos», no «pierden siempre»
        estatico = captura("2026-08-18", "Estatico", {"desaparecidos": 426})
        vivo = captura("2026-08-18", "EnVivo",
                       {"fallecidos": 304, "familias_afectadas": 123789},
                       is_liveblog=True)
        serie = correr_con([estatico, vivo], "UI.mejorPorDia(items)")
        self.assertEqual(serie[-1]["item"]["publisher"]["name"], "EnVivo")

    def test_entre_iguales_el_liveblog_sigue_pesando_menos(self):
        # la penalización de R8 sigue viva cuando lo demás empata
        quieto = captura("2026-08-18", "Quieto", {"fallecidos": 304})
        vivo = captura("2026-08-18", "EnVivo", {"fallecidos": 304},
                       is_liveblog=True)
        serie = correr_con([vivo, quieto], "UI.mejorPorDia(items)")
        self.assertEqual(serie[-1]["item"]["publisher"]["name"], "Quieto")

    def test_un_dia_entero_de_cortes_viejos_conserva_el_consolidado(self):
        # el 19-ago real: tres capturas, todas de días anteriores
        serie = correr_con(
            [captura("2026-08-18", "Bueno",
                     {"fallecidos": 304, "familias_afectadas": 123789,
                      "personas_afectadas": 292043}),
             captura("2026-08-19", "ViejoA",
                     {"fallecidos": 180, "personas_afectadas": 181}),
             captura("2026-08-19", "ViejoB", {"familias_afectadas": 11132}),
             captura("2026-08-19", "ViejoC", {"familias_afectadas": 7})],
            "UI.mejorPorDia(items)")
        cons = serie[-1]["consolidado"]
        self.assertEqual(cons["familias_afectadas"]["valor"], 123789)
        self.assertEqual(cons["fallecidos"]["valor"], 304)
        self.assertEqual(cons["familias_afectadas"]["fecha"], "2026-08-18",
                         "la serie declara que el dato sigue siendo del 18")


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestCoherenciaDeCifras(unittest.TestCase):
    """El boletín del 18-ago publicó «304 personas fallecidas»; la extracción
    lo guardó como `personas_afectadas: 304`. Ninguna relación lo comprobaba."""

    def test_menos_personas_que_desaparecidos_es_imposible(self):
        rotas = correr_con(
            [captura("2026-08-18", "X",
                     {"personas_afectadas": 304, "desaparecidos": 426})],
            "UI.incoherencias(items[0])")
        self.assertTrue(rotas, "304 afectados con 426 desaparecidos no puede ser")

    def test_menos_personas_que_familias_es_imposible(self):
        rotas = correr_con(
            [captura("2026-08-16", "X",
                     {"personas_afectadas": 117000,
                      "familias_afectadas": 120238})],
            "UI.incoherencias(items[0])")
        self.assertTrue(rotas, "una familia tiene al menos una persona")

    def test_un_balance_coherente_no_se_marca(self):
        rotas = correr_con(
            [captura("2026-08-18", "X",
                     {"personas_afectadas": 292043, "familias_afectadas": 123789,
                      "fallecidos": 304, "heridos": 4548})],
            "UI.incoherencias(items[0])")
        self.assertEqual(rotas, [])

    def test_la_cifra_rota_no_arrastra_a_las_sanas_del_mismo_balance(self):
        # el boletín oficial traía mal `personas` y bien `viviendas`: se
        # aprovecha lo bueno en vez de tirar el balance entero
        malo = captura("2026-08-18", "UNGRD",
                       {"personas_afectadas": 304, "desaparecidos": 426,
                        "viviendas_averiadas": 134342})
        serie = correr_con([malo], "UI.mejorPorDia(items)")
        cons = serie[-1]["consolidado"]
        self.assertEqual(cons["viviendas_averiadas"]["valor"], 134342,
                         "la cifra sana del mismo balance sí se publica")
        self.assertNotIn("personas_afectadas", cons,
                         "la cifra incoherente queda fuera")
        self.assertTrue(any("incoherente" in g["motivo"]
                            for g in serie[-1]["ignoradas"]))

    def test_toda_cifra_que_emite_el_worker_esta_clasificada(self):
        # si el worker añade una métrica y nadie la declara aquí, entraría en
        # el consolidado sin regla de monotonía y en silencio
        worker = (ROOT / "workers" / "ai-view" / "src" / "index.js").read_text()
        bloque = worker[worker.index("function extraerCifras(texto) {"):]
        bloque = bloque[:bloque.index("\n}")]
        emitidas = set(re.findall(r"^\s*(\w+): findMetricNumber", bloque, re.M))
        self.assertTrue(emitidas, "no se han podido leer las cifras del worker")
        declaradas = set(correr_con([], "UI.CIFRAS_BALANCE"))
        self.assertEqual(emitidas - declaradas, set(),
                         "cifra del worker sin clasificar en CIFRAS_BALANCE")


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

    # Las claves del catálogo desambiguan los homónimos con el departamento
    # entre paréntesis. Estas dos son las que se publicaron el 23-ago-2026 en
    # la frase real de municipios.html.
    CON_PARENTESIS = [
        {"municipio": "Bolívar (Cauca)", "departamento": "Cauca",
         "homonimo_de_departamento": True, "estado": "solo_rud"},
        {"municipio": "Sucre", "departamento": "Cauca",
         "homonimo_de_departamento": True, "estado": "solo_rud"},
    ]

    def test_el_departamento_no_se_escribe_dos_veces(self):
        """La frase publicada decía «Bolívar (Cauca) (Cauca)»: es la clave del
        diccionario usada como topónimo, el mismo fallo que `toponimo()` ya
        había corregido en las 208 fichas y del que esta copia no se enteró
        (M2). El patrón es el de `ingest/seo_check.py::DEPTO_DUPLICADO`, que
        casa con este texto pero no lo ve: solo recorre las fichas del build, y
        esta frase la escribe el navegador."""
        frase = self._frase(self.CON_PARENTESIS)
        dup = re.compile(r"\(([^()]{2,40})\)(?: \(\1\)|, \1\b)")
        hallado = dup.search(frase)
        self.assertIsNone(hallado,
                          f"el departamento se repite: «{hallado.group(0) if hallado else ''}»"
                          f" en «{frase}»")
        self.assertIn("Bolívar (Cauca)", frase)   # sigue desambiguado una vez

    def _enumerados(self, muns):
        """Solo el tramo que enumera, sin el resto de la frase."""
        frase = self._frase(muns)
        return frase.split(", salvo ", 1)[1].split(", que se llaman", 1)[0]

    def test_la_enumeracion_es_espanola(self):
        """«A y B y C y D y E» no es español, y es lo que se publicó el
        23-ago-2026 con cinco homónimos: la lista lleva comas y UNA sola
        conjunción. La regla ya vivía en `UI.enumeraEs`, en este mismo fichero;
        esta copia no la usaba (M2)."""
        self.assertEqual(
            self._enumerados(self.MUNS + self.CON_PARENTESIS),
            "Risaralda (Caldas), Córdoba (Quindío), Bolívar (Cauca) "
            "y Sucre (Cauca)")
        # con dos no hay coma que valga, y con uno no hay conjunción
        self.assertEqual(self._enumerados(self.CON_PARENTESIS),
                         "Bolívar (Cauca) y Sucre (Cauca)")
        self.assertEqual(self._enumerados(self.MUNS[:1]), "Risaralda (Caldas)")

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
                   "codigo_inconsistente": 8,
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


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestFechaDeCorte(unittest.TestCase):
    """`search_date` es la fecha que se le pidió al buscador, no la del
    balance: el mismo artículo de El Tiempo figuraba como el corte del 12, el
    14, el 15 y el 18 de agosto. `fechaCorte` es la pieza que convierte la
    lista de capturas en una serie temporal de verdad."""

    def test_manda_lo_que_el_texto_dice_de_si_mismo(self):
        r = correr_con([{"fecha_corte": "2026-08-15",
                         "publication_url": "https://x.com/2026/08/18/a",
                         "fecha": "2026-08-11"}],
                       "UI.fechaCorte(items[0])")
        self.assertEqual(r, {"fecha": "2026-08-15", "senal": "texto"})

    def test_sin_texto_vale_la_url(self):
        r = correr_con([{"publication_url": "https://x.com/2026/08/11/a",
                         "fecha": "2026-08-18"}],
                       "UI.fechaCorte(items[0])")
        self.assertEqual(r, {"fecha": "2026-08-11", "senal": "url"})

    def test_sin_texto_ni_url_vale_el_campo(self):
        r = correr_con([{"fecha": "2026-08-14"}], "UI.fechaCorte(items[0])")
        self.assertEqual(r, {"fecha": "2026-08-14", "senal": "campo"})

    def test_sin_ninguna_senal_no_se_inventa_una_fecha(self):
        # el search_date NO sirve de respaldo: es justamente el dato que
        # fechaba mal la serie
        r = correr_con([{"search_date": "2026-08-19"}], "UI.fechaCorte(items[0])")
        self.assertIsNone(r)

    def test_el_retraso_mide_del_corte_a_la_publicacion(self):
        dias = correr_con([{"fecha_corte": "2026-08-10",
                            "publicado_en": "2026-08-19T10:00:00Z"}],
                          "UI.retrasoDelBalance(items[0])")
        self.assertEqual(dias, 9, "un balance del 10 publicado el 19")

    def test_sin_fecha_de_publicacion_no_hay_retraso_inventado(self):
        self.assertIsNone(correr_con([{"fecha_corte": "2026-08-10"}],
                                     "UI.retrasoDelBalance(items[0])"))


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestSupuestoCoberturaDeFechado(unittest.TestCase):
    """R11: el supuesto avisa, y romperse aquí es BUENA noticia.

    La serie sigue indexada por `search_date` porque hoy no hay con qué
    fecharla mejor: la señal fiable —lo que el texto dice de su propio corte—
    la calcula el worker, y hasta que esté desplegado el corpus solo trae la
    fecha de la URL y el campo `fecha`. Cuando la cobertura suba del umbral,
    este test falla y toca cambiar el eje de la serie a la fecha de corte."""

    UMBRAL = 0.80

    def test_avisa_cuando_ya_se_puede_fechar_por_corte(self):
        feed = json.loads(
            (ROOT / "data/public/oficiales.json").read_text(encoding="utf-8"))
        items = [i for i in feed.get("items", []) if i.get("search_date")]
        if not items:
            self.skipTest("el feed archivado no trae capturas")
        fechados = correr_con(
            items, "items.filter((x) => UI.fechaCorte(x)).length")
        cobertura = fechados / len(items)
        self.assertLess(
            cobertura, self.UMBRAL,
            f"{fechados} de {len(items)} capturas ({cobertura:.0%}) ya tienen "
            f"fecha de corte: toca indexar la serie por ella en vez de por "
            f"`search_date`, y publicar el retraso de cada medio. Ver "
            f"docs/LIMITACIONES.md.")


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestParidadAlertasYSitio(unittest.TestCase):
    """El push, el Telegram, el RSS y la imagen social salen de alerts.py; la
    web, de site/ui.js. Hasta el 21-ago-2026 cada uno aplicaba su propia regla
    y se contradecían en público: con el feed del 19-ago, el aviso habría dicho
    «180 fallecidos (-124 vs día anterior)» —124 resucitados— mientras la web
    mostraba 304. Ahora alerts.py llama a ui.js, y este test lo vigila."""

    def test_las_alertas_leen_la_misma_regla_que_la_web(self):
        import sys
        sys.path.insert(0, str(ROOT / "ingest"))
        import alerts

        feed = json.loads(
            (ROOT / "data/public/oficiales.json").read_text(encoding="utf-8"))
        serie_py, regla = alerts._consolidado_de_la_serie(feed)
        self.assertEqual(regla, "serie_consolidada_ui_js",
                         "con node disponible no debe degradar a otra regla")
        items = [i for i in feed.get("items", []) if i.get("search_date")]
        serie_js = correr_con(items, "UI.mejorPorDia(items)")
        self.assertEqual(len(serie_py), len(serie_js))
        for dia_py, dia_js in zip(serie_py, serie_js):
            self.assertEqual(dia_py["fecha"], dia_js["fecha"])
            self.assertEqual(dia_py["consolidado"], dia_js["consolidado"],
                             f"el {dia_py['fecha']} las alertas y la web "
                             f"publicarían cifras distintas")

    def test_sin_node_no_se_publica_una_cifra_con_otra_regla(self):
        """R13: la corrida no se rompe, pero tampoco se inventa un aviso con
        una regla distinta — se avisa de que la regla no se pudo aplicar."""
        import sys
        sys.path.insert(0, str(ROOT / "ingest"))
        import alerts
        from unittest import mock

        with mock.patch.object(alerts.shutil, "which", return_value=None):
            serie, regla = alerts._consolidado_de_la_serie({"items": []})
        self.assertEqual(serie, [])
        self.assertEqual(regla, "sin_regla__no_se_publica",
                         "la etiqueta no puede nombrar una regla que no se "
                         "aplicó: quien lea el JSON archivado creería que la "
                         "cifra salió de un cálculo que no se hizo")


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestDisputaEntreMedios(unittest.TestCase):

    def test_dos_medios_validos_que_discrepan_son_disputa(self):
        serie = correr_con(
            [captura("2026-08-18", "Alto", {"familias_afectadas": 123789}),
             captura("2026-08-18", "Bajo", {"familias_afectadas": 54008})],
            "UI.mejorPorDia(items)")
        self.assertEqual(serie[-1]["disputa"]["familias_afectadas"],
                         {"min": 54008, "max": 123789})

    def test_una_extraccion_rota_no_es_una_disputa(self):
        # el 19-ago la página anunciaba «fallecidos entre 18 y 180» mientras
        # publicaba 304: no era un desacuerdo entre medios, eran dos
        # extracciones mal hechas
        roto = captura("2026-08-19", "Roto",
                       {"personas_afectadas": 181, "fallecidos": 180,
                        "heridos": 1595})
        serie = correr_con(
            [roto, captura("2026-08-19", "Sano", {"fallecidos": 304})],
            "UI.mejorPorDia(items)")
        self.assertIsNone(serie[-1]["disputa"],
                          "una cifra imposible no discrepa: está mal")

    def test_un_medio_sin_atribucion_no_crea_disputa(self):
        anon = captura("2026-08-18", "Anon", {"familias_afectadas": 999})
        anon["reported_data_source"] = []
        serie = correr_con(
            [anon, captura("2026-08-18", "Serio", {"familias_afectadas": 123789})],
            "UI.mejorPorDia(items)")
        self.assertIsNone(serie[-1]["disputa"])


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestPuenteANodeAguantaElFeed(unittest.TestCase):
    """El feed entero viaja hasta node. Pasarlo como argumento funcionaba en
    macOS y habría reventado en el runner de la corrida diaria: Linux limita
    cada argumento de execve a 128 KiB (MAX_ARG_STRLEN) y el feed real ya pesa
    ~100 KB. El fallo habría sido silencioso, diario, y justo en el camino que
    degrada — publicando la imagen social sin cifras y un aviso de nivel alta
    por push todos los días."""

    def test_un_feed_mayor_que_el_limite_de_argumento_se_procesa(self):
        import sys
        sys.path.insert(0, str(ROOT / "ingest"))
        import alerts

        # 400 capturas con texto largo: bastante más que MAX_ARG_STRLEN
        relleno = "x" * 4000
        items = [{
            "search_date": f"2026-08-{10 + (i % 10):02d}",
            "title": f"balance {i}", "text_excerpt": relleno,
            "publisher": {"name": f"Medio {i}", "domain": f"m{i}.co"},
            "reported_data_source": [{"id": "UNGRD"}],
            "is_liveblog": False, "captured_at": "2026-08-20T04:00",
            "cifras": {"fallecidos": 300 + i, "familias_afectadas": 120000 + i},
        } for i in range(400)]
        feed = {"items": items}
        self.assertGreater(len(json.dumps(feed)), 140_000,
                           "la fixture debe superar el límite que se vigila")

        serie, regla = alerts._consolidado_de_la_serie(feed)
        self.assertEqual(regla, "serie_consolidada_ui_js",
                         "el feed grande no puede tumbar el puente a node")
        self.assertTrue(serie)
        self.assertIsNotNone(
            (serie[-1]["consolidado"].get("fallecidos") or {}).get("valor"))


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestEspejoDeCoherencia(unittest.TestCase):
    """La regla de coherencia vive en DOS superficies: el worker la aplica al
    capturar (para reintentar y descartar) y ui.js al consolidar (para no
    publicar). Nada impedía que dejaran de coincidir al tocar una — que es
    exactamente como `directo` acabó casando dentro de `directorio`.

    Las relaciones se descubren EJECUTANDO cada regla contra un caso que la
    violaría, no leyendo su código: un test que busca nombres fijados solo caza
    las divergencias que ya imaginó quien lo escribió."""

    CIFRAS = ["departamentos_afectados", "municipios_afectados",
              "personas_afectadas", "familias_afectadas", "viviendas_averiadas",
              "viviendas_destruidas", "heridos", "fallecidos", "desaparecidos",
              "rescatados"]

    def relaciones_de_ui(self):
        casos = [{"cifras": {a: 1, b: 100}} for a in self.CIFRAS
                 for b in self.CIFRAS if a != b]
        marcados = correr_con(
            casos, "items.map((x) => UI.incoherencias(x).length > 0)")
        pares = [(a, b) for a in self.CIFRAS for b in self.CIFRAS if a != b]
        return {par for par, roto in zip(pares, marcados) if roto}

    def relaciones_del_worker(self):
        pares = [(a, b) for a in self.CIFRAS for b in self.CIFRAS if a != b]
        casos = json.dumps([{a: 1, b: 100} for a, b in pares])
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "worker.mjs"
            copia.write_bytes(
                (ROOT / "workers/ai-view/src/index.js").read_bytes())
            script = (f"const W = await import({json.dumps(copia.as_uri())});"
                      f"const casos = {casos};"
                      "console.log(JSON.stringify(casos.map((c) => "
                      "W.incoherenciasDeCifras(c).length > 0)));")
            r = subprocess.run([NODE, "--input-type=module", "-e", script],
                               capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise AssertionError(f"node falló: {r.stderr[:400]}")
        return {par for par, roto in zip(pares, json.loads(r.stdout)) if roto}

    def test_las_dos_superficies_marcan_lo_mismo(self):
        ui, worker = self.relaciones_de_ui(), self.relaciones_del_worker()
        self.assertTrue(ui, "ui.js no marca ninguna incoherencia")
        self.assertEqual(
            ui, worker,
            "el worker y ui.js comprueban relaciones distintas: una cifra "
            "imposible podría pasar por una superficie y no por la otra.\n"
            f"  solo en ui.js : {sorted(ui - worker)}\n"
            f"  solo en worker: {sorted(worker - ui)}")


@unittest.skipUnless(NODE, "node no disponible")
class TestTotalSatelitalTresServicios(unittest.TestCase):
    """Con tres servicios mirando, el sitio deja de calcular el total.

    Hasta el 20-ago-2026 la portada sumaba Copernicus + UNOSAT con una guarda de
    solape, y esa aritmética bastaba porque las dos miraban municipios
    distintos. ICube-SERTIT rompe el supuesto: mira Pereira y Cali, que ya
    miraba Copernicus, y en Pereira 108 de sus edificios son los mismos que ya
    estaban contados. Decidir cuáles exige geometría, así que la decisión se
    toma una sola vez en la ingesta (`ingest/satelites.py`, que publica
    `monitor.satelital`) y el sitio la LEE. Este test vigila que la lea: si
    alguien vuelve a sumar aquí, el total dejará de cuadrar con el que publica
    el resto del monitor.
    """

    MON = {
        "fecha": "2026-08-21",
        # las AOIs siguen ahí, y su suma (622) NO es la cifra de la tarjeta:
        # si alguien vuelve a calcular, el test lo ve
        "aois": [{"resumen": {"edificios_afectados": 400}},
                 {"resumen": {"edificios_afectados": 222}}],
        "entregas": [{"fecha": "2026-08-18"}],
        "unosat": {"edificios": 385, "observados": 96, "posibles": 289,
                   "municipios": ["Anserma", "Manizales", "Viterbo"],
                   "municipios_tambien_en_aoi_copernicus": []},
        "satelital": {
            "total_edificios": 1424, "umbral_m": 20,
            "criterio": "Cada edificio se cuenta una vez.",
            "por_municipio": {
                "Pereira": {"unidades": 337,
                            "fuentes": {"copernicus": 193, "sertit": 252},
                            "coincidencias": 108, "discrepan_de_grado": 49},
                "Roldanillo": {"unidades": 77, "fuentes": {"sertit": 77},
                               "coincidencias": 0, "discrepan_de_grado": 0},
                "Anserma": {"unidades": 104, "fuentes": {"unosat": 104},
                            "coincidencias": 0, "discrepan_de_grado": 0},
            },
        },
    }

    def _satelite(self, mon):
        fuentes = correr_ui("UI.comparativaFuentes("
                            f"{json.dumps(mon, ensure_ascii=False)}, null)")
        return next(f for f in fuentes if f["id"] == "satelite")

    def test_lee_el_total_de_la_ingesta_en_vez_de_calcularlo(self):
        sat = self._satelite(self.MON)
        self.assertEqual(sat["cifras"]["edificios_dañados"], 1424,
                         "el total sale de monitor.satelital, no de sumar fuentes")

    def test_un_total_que_cambia_en_la_ingesta_cambia_en_la_portada(self):
        """Si el sitio calculara, este monitor daría el mismo número que el
        anterior. Leerlo significa obedecerlo, aunque sea absurdo."""
        mon = {**self.MON, "satelital": {**self.MON["satelital"],
                                         "total_edificios": 7}}
        self.assertEqual(self._satelite(mon)["cifras"]["edificios_dañados"], 7)

    def test_nombra_los_tres_servicios(self):
        sat = self._satelite(self.MON)
        for servicio in ("Copernicus", "UNOSAT", "ICube-SERTIT"):
            self.assertIn(servicio, sat["nombre"],
                          f"la tarjeta calla {servicio}")

    def test_declara_el_solape_y_el_desacuerdo(self):
        """Una cifra que descarta duplicados sin decir cuántos no es
        rastreable: los 108 edificios que dos servicios vieron a la vez —y los
        49 en los que no coinciden— son el hallazgo, no un detalle técnico."""
        sat = self._satelite(self.MON)
        self.assertEqual(sat["cifras"]["edificios_vistos_por_dos"], 108)
        self.assertEqual(sat["cifras"]["edificios_en_desacuerdo"], 49)
        self.assertIn("108", sat["nota"])
        self.assertIn("49", sat["nota"])
        self.assertIn("Pereira", sat["nota"],
                      "el municipio donde discrepan se nombra, no se cuenta")

    def test_no_dice_que_suma_ni_que_corrige_a_nadie(self):
        """El monitor no arbitra entre satélites: mide la distancia entre
        ellos. Ni la tarjeta suma fuentes ni proclama que una enmiende a otra."""
        sat = self._satelite(self.MON)
        texto = " ".join(str(sat.get(k) or "")
                         for k in ("nombre", "alcance", "desglose", "nota"))
        for palabra in ("suma", "corrige", "desmiente"):
            self.assertNotIn(palabra, texto.lower(),
                             f"la tarjeta dice «{palabra}»")

    def test_un_monitor_sin_bloque_satelital_no_revienta(self):
        """El archivo guarda monitor.json anteriores a este bloque: deben
        seguir pintándose con las miradas que tuvieran entonces."""
        mon = {k: v for k, v in self.MON.items() if k != "satelital"}
        sat = self._satelite(mon)
        self.assertEqual(sat["cifras"]["edificios_dañados"], 1007,
                         "respaldo: 622 de Copernicus + 385 de UNOSAT")


class TestChipsSonAcciones(unittest.TestCase):
    """Un chip se pulsa; lo que no se pulsa no es un chip.

    Las dos cosas compartían la clase `.chip` y solo se distinguían por el
    cursor: en reposo eran idénticas, así que la lista de titulares servía 316
    pastillas con aspecto de control que no hacían nada. Quien aprende que un
    chip se pulsa se encontraba 316 que no.

    La regla vive en DOS superficies —si tocas una, mira la otra—:
    `site/noticias.js` y `deploy/render_html.py`, que pintan las mismas
    etiquetas, una en el navegador y otra en el build.
    """

    JS = (ROOT / "site" / "noticias.js").read_text(encoding="utf-8")
    PY_ = (ROOT / "deploy" / "render_html.py").read_text(encoding="utf-8")
    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

    def test_ningun_span_lleva_la_clase_de_accion(self):
        """El marcado pasivo es `<span>`; si lleva `.chip`, promete un clic."""
        for nombre, fuente in (("site/noticias.js", self.JS),
                               ("deploy/render_html.py", self.PY_)):
            with self.subTest(fuente=nombre):
                spans = re.findall(r'<span class="chip[^"]*"', fuente)
                self.assertEqual(spans, [], f"{nombre}: etiqueta con clase de acción")

    def test_las_dos_superficies_pintan_la_misma_clase(self):
        """El prerenderizado y el navegador tienen que coincidir: si divergen,
        la misma etiqueta se ve de dos maneras según se ejecute o no el JS."""
        self.assertIn('class="etiqueta mun"', self.JS)
        self.assertIn('class="etiqueta mun"', self.PY_)

    def test_cada_superficie_nombra_a_la_otra(self):
        """R8/R10: una regla en dos idiomas se documenta cruzada o se olvida."""
        self.assertIn("render_html", self.JS)
        self.assertIn("noticias.js", self.PY_)

    def test_la_etiqueta_no_se_disfraza_de_boton(self):
        """No basta con renombrar: si `.etiqueta` copia la pastilla del chip,
        el lector sigue viendo un control donde no lo hay."""
        m = re.search(r"^\.etiqueta\s*\{([^}]*)\}", self.CSS, re.M | re.S)
        self.assertIsNotNone(m, "falta la regla .etiqueta en styles.css")
        cuerpo = " ".join(m.group(1).split())
        self.assertNotIn("border:", cuerpo, "una etiqueta con borde parece un botón")
        self.assertNotIn("cursor: pointer", cuerpo)
        self.assertNotIn("999px", cuerpo, "el radio de pastilla es del chip")

    def test_el_chip_si_declara_que_se_pulsa(self):
        m = re.search(r"^\.chip\s*\{([^}]*)\}", self.CSS, re.M | re.S)
        self.assertIsNotNone(m)
        self.assertIn("cursor: pointer", " ".join(m.group(1).split()))


def _css_sin_comentarios(css):
    """Borra los comentarios CONSERVANDO los desplazamientos del archivo.

    Cada comentario se sustituye por tantos espacios como ocupaba, de modo que
    un índice medido sobre el texto crudo —el del cabezal del rediseño, que
    vive dentro de un comentario— sigue valiendo sobre el texto limpio. Con un
    `re.sub` normal, el cabezal desaparecería y con él la frontera entre la
    hoja vieja y el sistema nuevo.
    """
    return re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), css, flags=re.S)


def _reglas(css_limpio):
    """Cada regla de una hoja ya sin comentarios: (selectores, declaraciones).

    Los selectores llegan sueltos y normalizados a un espacio, y las reglas de
    dentro de un `@media` entran como cualquier otra —el `[^{}]` no cruza
    llaves, así que lo que se recoge es la regla interna y no el `@media`—.
    """
    fuera = []
    for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css_limpio):
        if "@" in selector:
            continue
        sels = [" ".join(s.split()) for s in selector.split(",") if s.strip()]
        decls = [" ".join(d.split()) for d in cuerpo.split(";") if d.strip()]
        if sels:
            fuera.append((sels, decls))
    return fuera


def _sujeto(selector):
    """El compuesto FINAL de un selector: el elemento que la regla ESTILA.

    `.chip .n` estila el `.n`, que está dentro; `.chip:has(.punto)` estila el
    CHIP. Esa diferencia es justo la que separa la parte de un componente de
    una deducción sobre el componente entero.
    """
    return re.split(r"[\s>+~]+", selector.strip())[-1]


# Propiedades que mueven cajas. Un color de más se ve y se corrige; una caja
# que cambia de `display` remaqueta la tira entera y arrastra a sus vecinas.
_MAQUETA = (
    "display", "position", "float", "clear", "overflow", "inset", "order",
    "width", "height", "min-width", "min-height", "max-width", "max-height",
    "margin", "padding", "gap", "flex", "grid", "columns", "white-space",
    "align-", "justify-", "place-", "top", "right", "bottom", "left",
)


def _es_maqueta(declaracion):
    return declaracion.split(":", 1)[0].strip().startswith(_MAQUETA)


class TestSistemaDelRedisenoNoPisaLaHojaVieja(unittest.TestCase):
    """El `:root` del final no puede redeclarar ni un token de los de arriba.

    Es la única barrera contra el fallo que el propio cabezal de `styles.css`
    describe: las variantes oscuras de esta hoja viven en un
    `@media (prefers-color-scheme: dark)` que va ARRIBA, así que un `:root`
    plano añadido ABAJO gana también en tema oscuro. El síntoma no sería un
    color raro: sería tinta casi negra sobre fondo casi negro en las cinco
    páginas y en las 208 fichas. Por eso el bloque nuevo solo puede contener
    alias (`var(...)`, que se resuelven al usarse y recogen solos el tema
    activo) y tokens que no existían.

    La revisión de la fase 2 comprobó a mano —y una sola vez— que la
    intersección era vacía. Este test la comprueba en cada corrida.
    """

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
    MARCA = "SISTEMA DEL REDISEÑO 2026"

    # Mirar solo los `:root` dejaba fuera la mitad del peligro. Un token no se
    # pisa únicamente desde la raíz: se pisa desde CUALQUIER bloque que alcance
    # a todo el documento. `body { --ink: #333 }` al final de la hoja no compite
    # con `:root` por especificidad —hereda a todos sus descendientes y les gana
    # en los dos temas—, y pasaba en verde viéndose perfectamente.
    ALCANCE_GLOBAL = re.compile(r"^(?::root|html|body|\*)(?![\w-])")

    # `html` a secas es la única excepción, y no por costumbre: `:root` vale
    # (0,1,0) y `html` (0,0,1) sobre EL MISMO elemento, así que `:root` gana
    # pase donde pase en la hoja. Redeclarar ahí es una declaración muerta, no
    # un fallo visible. Cualquier cosa más específica —`html.tema`,
    # `html[data-tema]`— sí gana, y por eso la excepción es un literal exacto
    # y no un prefijo.
    INOCUOS = {"html"}

    def _roots(self, texto):
        """Los tokens declarados en cada bloque `:root` de un tramo de hoja."""
        return [set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", cuerpo))
                for cuerpo in re.findall(r":root\s*\{([^{}]*)\}", texto)]

    def _globales(self, texto):
        """(selector, tokens) de cada bloque que redefine para TODO el documento.

        Global es el selector de UN SOLO compuesto anclado en la raíz o en un
        ancestro de todo: `body .aviso { --ac: … }` no lo es —solo alcanza a
        `.aviso`, y acotar un token a un componente es scoping legítimo—, ni lo
        es `#site-nav .nav-links > *`, que ya vive en esta hoja.
        """
        fuera = []
        for sels, decls in _reglas(texto):
            tokens = {m.group(1) for m in
                      (re.match(r"(--[a-zA-Z0-9_-]+)\s*:", d) for d in decls) if m}
            if not tokens:
                continue
            for s in sels:
                if s == _sujeto(s) and self.ALCANCE_GLOBAL.match(s):
                    fuera.append((s, tokens))
        return fuera

    def setUp(self):
        self.assertIn(self.MARCA, self.CSS,
                      "el cabezal del rediseño es la frontera: sin él no hay test")
        corte = self.CSS.index(self.MARCA)
        limpio = _css_sin_comentarios(self.CSS)
        self.arriba = self._roots(limpio[:corte])
        self.abajo = self._roots(limpio[corte:])
        self.globales_arriba = self._globales(limpio[:corte])
        self.globales_abajo = self._globales(limpio[corte:])

    def test_el_bloque_nuevo_declara_tokens_y_los_de_arriba_siguen_ahi(self):
        """Guardián de sí mismo: si el parseo no encuentra nada, el test de
        abajo pasaría en verde sin haber mirado nada."""
        self.assertEqual(len(self.abajo), 1,
                         "el sistema del rediseño abre UN solo `:root`; si son "
                         "dos, el segundo también gana en tema oscuro")
        self.assertTrue(self.abajo[0], "el `:root` del rediseño no declara nada")
        self.assertGreaterEqual(
            len(self.arriba), 2,
            "arriba tienen que seguir estando al menos el `:root` inicial y el "
            "del bloque oscuro")
        self.assertIn("@media (prefers-color-scheme: dark)", self.CSS)
        self.assertGreaterEqual(
            len(self.globales_arriba), 2,
            "el analizador de alcance global no reconoce ni los `:root` de "
            "arriba: el test de abajo no vigilaría nada")
        self.assertEqual(
            {s for s, _ in self.globales_arriba}, {":root"},
            "arriba, los tokens solo se declaran en `:root`; si aparece otro "
            "bloque global declarándolos, la frontera de esta clase cambia")
        self.assertIn(
            "--ink", set().union(*(t for _s, t in self.globales_arriba)),
            "el analizador no ve ni `--ink` entre los tokens de arriba")

    def test_el_root_del_final_no_redeclara_ningun_token_de_arriba(self):
        previos = set().union(*self.arriba)
        repetidos = sorted(self.abajo[0] & previos)
        self.assertEqual(
            repetidos, [],
            "el `:root` del final redeclara " + ", ".join(repetidos) + ": un "
            "`:root` plano al final de la hoja gana TAMBIÉN en tema oscuro, "
            "donde el valor correcto lo pone el `@media (prefers-color-scheme: "
            "dark)` de arriba. Si de verdad hay que cambiar ese token, se "
            "cambia donde vive, con su pareja clara y oscura.")

    def test_ningun_bloque_de_alcance_global_pisa_un_token_heredado(self):
        """La red ancha: `:root` no es el único sitio desde el que se pisa un
        token. `body { --ink: #333 }` al final de la hoja no compite con
        `:root` por especificidad —está POR DEBAJO, hereda a todo lo visible y
        le gana por proximidad—, y lo mismo hace `*`. El síntoma sería el de
        siempre: tinta casi negra sobre fondo casi negro en las cinco páginas y
        en las 208 fichas, sin que ningún `:root` nuevo aparezca en el diff."""
        previos = set().union(*self.arriba)
        for sel, tokens in self.globales_abajo:
            if sel in self.INOCUOS:
                continue
            repetidos = sorted(tokens & previos)
            with self.subTest(selector=sel):
                self.assertEqual(
                    repetidos, [],
                    f"`{sel}` redeclara " + ", ".join(repetidos) + ": alcanza a "
                    "todo el documento y se aplica DESPUÉS de los tokens de "
                    "arriba, así que gana también en tema oscuro, donde el "
                    "valor correcto lo pone el `@media (prefers-color-scheme: "
                    "dark)`. Si de verdad hay que cambiar ese token, se cambia "
                    "donde vive, con su pareja clara y oscura.")


class TestPlegableLegadoYComponenteNoDivergen(unittest.TestCase):
    """Los cuatro selectores viejos del plegable y `.pliegue` dicen lo mismo.

    Conviven a propósito: el componente `.pliegue` es la regla nueva y los
    cuatro selectores de sitio (`#como-leer`, `.intro details`,
    `.aviso details`, `#alerts-section > details`) quedan como ALIAS para que
    nada de lo publicado cambie de aspecto hoy. La retirada está escrita en el
    comentario del lote 3: cuando ninguna página dependa de los alias, los
    cuatro se van EN UN COMMIT PROPIO, de aquí y del bloque de arriba.

    Mientras dure la convivencia, un ajuste hecho en un bloque y no en el otro
    los hace divergir EN SILENCIO: el aspecto cambiaría según qué plegable
    lleve ya la clase nueva. Este test empareja cada regla legada con su espejo
    del componente y exige declaraciones idénticas.
    """

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
    LEGADOS = ("#como-leer", ".intro details", ".aviso details",
               "#alerts-section > details")
    # Las parejas que hay hoy, contadas el 23-ago-2026. Es un número a mano
    # a propósito: mientras dure la convivencia, el plegable no crece ni
    # mengua solo. Si cambia, cambia con un commit que lo explique.
    PAREJAS = 8

    @classmethod
    def setUpClass(cls):
        limpio = _css_sin_comentarios(cls.CSS)
        cls.legado, cls.componente, cls.contaminadas = {}, {}, []
        for sels, decls in _reglas(limpio):
            pliegues = [s for s in sels if ".pliegue" in s]
            # `#como-leer.pliegue` empieza por un selector legado y además
            # lleva la clase nueva: es el componente igualando especificidad
            # con el id, no un alias. Cuenta como `.pliegue`.
            alias = [s for s in sels
                     if s.startswith(cls.LEGADOS) and ".pliegue" not in s]
            ajenos = [s for s in sels if s not in pliegues and s not in alias]
            if not alias:
                # O no habla del plegable, o es una regla del componente sin
                # alias que emparejar (`details.pliegue`), o es una lista de
                # otro lote que incluye `details.pliegue` —la del eje—.
                continue
            if ajenos:
                cls.contaminadas.append((sels, ajenos))
                continue
            destino = cls.componente if pliegues else cls.legado
            destino[tuple(alias)] = decls

    def test_los_dos_bloques_del_plegable_siguen_conviviendo(self):
        """Guardián de sí mismo, y por eso CUENTA en vez de preguntar si hay
        algo. «No vacío» era exactamente el hueco: añadiendo un selector ajeno
        a los DOS bloques, las dos reglas dejan de parsearse a la vez, salen
        del emparejamiento, los diccionarios siguen sin estar vacíos y a partir
        de ahí los dos bloques pueden divergir en verde. Es encogimiento
        silencioso. Si los alias se retiraron de verdad, este test se retira
        con ellos en ese mismo commit —que es justo el cambio verificable que
        pide el lote 3—."""
        self.assertEqual(
            len(self.legado), self.PAREJAS,
            f"hay {len(self.legado)} reglas con los selectores viejos y se "
            f"esperaban {self.PAREJAS}: o se retiraron alias, o alguna se cayó "
            "del análisis y ya no se compara con nada.")
        self.assertEqual(
            len(self.componente), self.PAREJAS,
            f"hay {len(self.componente)} reglas de `.pliegue` con alias "
            f"colgando y se esperaban {self.PAREJAS}.")

    def test_ninguna_regla_del_plegable_se_cae_del_emparejamiento(self):
        """La forma exacta del encogimiento: basta con colar un selector ajeno
        en una regla del plegable para que se salga del análisis SIN QUE NADA
        FALLE. Se detecta aquí, en vez de descartarla en silencio."""
        self.assertEqual(
            [(sels, ajenos) for sels, ajenos in self.contaminadas], [],
            "una regla del plegable mezcla selectores que no son ni alias ni "
            f"`.pliegue`: {self.contaminadas}. Así sale del emparejamiento y "
            "los dos bloques pueden divergir sin que ningún test se entere. Si "
            "ese selector tiene que ir ahí, se le da su propia regla.")

    def test_cada_regla_legada_tiene_su_espejo_en_el_componente(self):
        huerfanas = sorted(set(self.legado) - set(self.componente))
        sobrantes = sorted(set(self.componente) - set(self.legado))
        self.assertEqual(
            (huerfanas, sobrantes), ([], []),
            "una regla del plegable existe en un bloque y no en el otro: "
            f"solo arriba {huerfanas}, solo abajo {sobrantes}")

    def test_las_declaraciones_de_ambos_bloques_son_identicas(self):
        for clave in sorted(set(self.legado) & set(self.componente)):
            with self.subTest(regla=", ".join(clave)):
                self.assertEqual(
                    self.legado[clave], self.componente[clave],
                    "los dos bloques del plegable dicen cosas distintas para el "
                    "mismo selector: se tocó uno y no el otro, y el aspecto de "
                    "un plegable pasa a depender de si ya lleva `class=pliegue`")


class TestNingunTokenSeUsaSinRespaldo(unittest.TestCase):
    """Un `var(--x)` sin declaración no se degrada: borra la propiedad entera.

    Los tokens que el marcado emite EN LÍNEA —`--bc` en `.badge`, `--ac` en
    `.aviso`, `--fc` en las tarjetas de fuente y en los chips de cronología—
    no existen hasta que un elemento los trae puestos. Si la hoja los usa sin
    valor por defecto, la declaración que los consume es INVÁLIDA en tiempo de
    cómputo: `border-top: 3px solid var(--fc)` no da un filete gris, devuelve
    `border-top-style` a `none` y el filete DESAPARECE.

    Un caso así no se ve venir leyendo el CSS ni se nota en el navegador
    mientras la regla case con cero elementos: aparece el día que una fase
    pinta el primer elemento sin el token en línea. De ahí el guardián.

    Las dos formas válidas de respaldo, ambas en uso en esta hoja:
    `var(--bc, var(--muted))` en el punto de uso (`:199`) y `--ac: var(--muted)`
    en la regla base del componente (`:495`; `--fc` sigue este segundo patrón).
    """

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

    # La única regla que usa un token en línea sin declararlo: lo HEREDA de su
    # contenedor. Se escribe con su ascendiente porque el test comprueba que
    # ese ascendiente sí lo declara; una herencia que no se puede nombrar es
    # una herencia que no se puede verificar.
    HEREDAN = {".fuente-muns b": ".comparativa .fuente"}

    @classmethod
    def setUpClass(cls):
        limpio = _css_sin_comentarios(cls.CSS)
        cls.limpio = limpio
        cls.reglas = []          # (selector normalizado, declarados, usados sin respaldo)
        for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", limpio):
            sel = " ".join(selector.split())
            declarados = set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", cuerpo))
            # `var(--x)` a secas: sin coma no hay respaldo en el punto de uso.
            pelados = set(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*\)", cuerpo))
            cls.reglas.append((sel, declarados, pelados))
        cls.de_root = set()
        for cuerpo in re.findall(r":root\s*\{([^{}]*)\}", limpio):
            cls.de_root |= set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", cuerpo))

    def test_ningun_token_se_usa_sin_declararlo_en_ningun_sitio(self):
        """La red gruesa: un token que no se declara en NINGUNA parte de la
        hoja. Es el estado en que estaba `--fc` —el único— antes del lote."""
        declarados = set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", self.limpio))
        con_respaldo = set(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*,", self.limpio))
        usados = set(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)", self.limpio))
        self.assertTrue(usados, "el analizador no encontró ni un token: no mira nada")
        huerfanos = sorted(usados - declarados - con_respaldo)
        self.assertEqual(huerfanos, [], f"tokens sin declarar en toda la hoja: {huerfanos}")

    def test_cada_regla_que_gasta_un_token_de_marcado_le_pone_defecto(self):
        """La red fina, que es la que hace falta: los tokens que NINGÚN `:root`
        declara solo pueden llegar desde el marcado, así que el defecto tiene
        que estar en CADA componente que los gasta. Que otro componente lo
        declare no salva al vecino: `--fc` en `.comparativa .fuente` no llega a
        `.chip-crono`, que no está dentro.
        """
        de_marcado = set()
        for _sel, _decl, pelados in self.reglas:
            de_marcado |= {t for t in pelados if t not in self.de_root}
        self.assertTrue(de_marcado, "ningún token de marcado: el analizador no mira nada")

        for sel, declarados, pelados in self.reglas:
            for token in sorted(pelados & de_marcado):
                if token in declarados:
                    continue
                with self.subTest(regla=sel, token=token):
                    padre = self.HEREDAN.get(sel)
                    self.assertIsNotNone(
                        padre,
                        f"`{sel}` usa `{token}` sin declararle un valor por "
                        "defecto. O se lo declara en su propia regla base, o "
                        "se anota en HEREDAN de quién lo hereda.")
                    hereda = [d for s, d, _ in self.reglas if s == padre]
                    self.assertTrue(hereda, f"el ascendiente `{padre}` no existe")
                    self.assertTrue(
                        any(token in d for d in hereda),
                        f"`{sel}` hereda `{token}` de `{padre}`, pero `{padre}` "
                        "ya no lo declara: la herencia se quedó sin origen.")


class TestElChipDeclaraLoQueEsYNoLoDeduce(unittest.TestCase):
    """Un componente declara su tipo; no lo adivina por sus hijos.

    `.chip` está vivo en tres páginas publicadas —`site/app.js` y
    `site/municipios.js` pintan dos de las tiras de filtros en el navegador, y
    `deploy/render_html.py::chips_rud` pinta la del RUD en el build desde la
    fase 3— y `.punto` es un nombre genérico y apetecible. El lote 4 llegó a decir
    `.chip:has(.punto) { display: inline-flex; … }`: casaba con cero elementos,
    cierto, pero dejaba el `display` de las tres tiras a merced de que alguien
    metiera algún día un `.punto` dentro de un chip por cualquier otro motivo.
    La tira se habría remaquetado sola sin que nadie tocase el CSS.

    Ninguno de estos invariantes tenía guardián: en la fase 2, borrar
    `.chip.activa`, ensanchar la regla del punto a `.chip` entera o meter
    `.chips` en la lista del eje dejaban los 511 tests en verde. Un comentario
    en mayúsculas no es un guardián.
    """

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
    MARCA = "SISTEMA DEL REDISEÑO 2026"
    # Las superficies que pintan un chip activo en el sitio publicado, y el
    # patrón con que cada una lo escribe. Las tiras del RUD (fase 3) y de
    # municipios (fase 4) se mudaron al build: ya no las construye su JS, así
    # que la plantilla es de Python. Ojo con la cobertura que da esta lista: la
    # entrada de `render_html.py` sobreviviría hoy aunque `chips_municipios`
    # perdiera el `.activa`, porque `chips_rud` casa el mismo literal. Lo que de
    # verdad guarda cada tira generada es su test POR EJECUCIÓN —
    # `TestChipsDelRud` y `TestChipsDeMunicipios`—, sobre la salida de su
    # generador y no sobre el fichero entero.
    TIRAS = {"site/app.js": r'class="chip\$\{[^`]*?\bactiva\b',
             "deploy/render_html.py": r'class="chip\{" activa" if\b'}

    @classmethod
    def setUpClass(cls):
        limpio = _css_sin_comentarios(cls.CSS)
        cls.reglas = _reglas(limpio)
        # Sin cabezal no hay frontera: se deja el tramo nuevo vacío y que lo
        # cuente el guardián de sí mismo, en vez de reventar en el setUpClass
        # con un ValueError que no explica nada.
        corte = cls.CSS.find(cls.MARCA)
        cls.nuevas = _reglas(limpio[corte:]) if corte >= 0 else []

    def test_el_analizador_mira_algo(self):
        """Guardián de sí mismo: con un parseo vacío, o sin ninguna propiedad
        de maqueta reconocida, los tests de abajo pasarían sin mirar nada."""
        self.assertIn(self.MARCA, self.CSS, "el cabezal es la frontera")
        self.assertGreater(len(self.reglas), 100, "no parsea la hoja")
        self.assertGreater(len(self.nuevas), 20, "no parsea el sistema nuevo")
        chips = [s for sels, _ in self.reglas for s in sels if ".chip" in s]
        self.assertGreater(len(chips), 10, "no encuentra ni las reglas del chip")
        # El filtro se comprueba contra ejemplos, no contando cuántos pasan:
        # quitarle `display` lo dejaba medio ciego sin que nada bajara de cero.
        for decl in ("display: inline-flex", "padding-left: var(--eje)",
                     "gap: 7px", "margin: 16px var(--margen)"):
            self.assertTrue(_es_maqueta(decl), f"`{decl}` es maqueta y no lo ve")
        for decl in ("color: var(--ink)", "font-weight: 700",
                     "border-radius: 999px", "background: var(--surface-1)"):
            self.assertFalse(_es_maqueta(decl), f"`{decl}` no es maqueta")
        # Y el sujeto, que es donde vive toda la diferencia entre estilar una
        # PARTE del componente y remaquetar el componente ENTERO.
        for selector, sujeto in ((".chip .n", ".n"),
                                 ("details.pliegue > summary", "summary"),
                                 (".chips-mapa .chip", ".chip"),
                                 (".chip:has(.punto)", ".chip:has(.punto)"),
                                 ("#site-nav .nav-links > *", "*")):
            self.assertEqual(_sujeto(selector), sujeto,
                             f"el sujeto de `{selector}` es `{sujeto}`")

    def test_ninguna_regla_deduce_la_maqueta_de_un_componente_de_sus_hijos(self):
        """`:has()` no está prohibido por feo: está prohibido para decidir
        CAJAS. Un selector que mira dentro y cambia el `display` del padre
        convierte a cualquier hijo futuro en el dueño de la maqueta."""
        culpables = [
            (s, [d for d in decls if _es_maqueta(d)])
            for sels, decls in self.reglas for s in sels
            if ":has(" in s and any(_es_maqueta(d) for d in decls)]
        self.assertEqual(
            culpables, [],
            "una regla deduce la maqueta de un componente de sus hijos: "
            f"{culpables}. El tipo de un componente se DECLARA con un "
            "modificador en el marcado; si se infiere, el día que aparezca un "
            "hijo con ese nombre por otro motivo la caja se remaqueta sola.")

    def test_el_sistema_nuevo_no_remaqueta_chip_ni_chips_a_pelo(self):
        """Regla 1 del cabezal, y promesa literal del lote 4: «`.chips` y
        `.chip` NO se tocan». Lo aditivo entra con nombre propio.

        «A pelo» quiere decir SIN NINGUNA CALIFICACIÓN: `.chips-mapa .chip`
        —que vive en este mismo tramo— alcanza solo a los chips de un
        contenedor que alguien escribió a mano, y eso es alcance declarado. Lo
        que no puede pasar es que una regla nueva alcance a TODOS los chips del
        sitio, que son las tres tiras de filtros publicadas.
        """
        for sels, decls in self.nuevas:
            for s in sels:
                clases = set(re.findall(r"\.([A-Za-z_][\w-]*)", s))
                if _sujeto(s) not in (".chip", ".chips"):
                    continue
                if clases - {"chip", "chips"} or "#" in s or "[" in s:
                    continue
                self.fail(
                    f"la regla `{', '.join(sels)}` estila `{_sujeto(s)}` a pelo "
                    "desde el sistema del rediseño: alcanza a los chips de "
                    "todo el sitio, o sea a las tres tiras de filtros "
                    "publicadas. Lo nuevo entra como modificador con nombre "
                    f"propio. Declara: {decls}")

    def test_el_punto_del_chip_cuelga_de_un_modificador_declarado(self):
        """Las dos mitades del componente —la caja y el punto— viven en el
        mismo sitio: `.chip--punto`. Fuera de él, un `.punto` suelto dentro de
        un chip no se pinta ni se coloca, que es lo que debe pasar."""
        caja = [decls for sels, decls in self.nuevas if sels == [".chip--punto"]]
        self.assertEqual(len(caja), 1,
                         "falta (o sobra) la regla del modificador `.chip--punto`")
        self.assertIn("display: inline-flex", caja[0],
                      "el modificador existe pero no es quien maqueta el chip")
        self.assertTrue(
            [1 for sels, _ in self.nuevas if ".chip--punto .punto" in sels],
            "el punto no cuelga del modificador")
        sueltas = [", ".join(sels) for sels, _ in self.reglas
                   if ".chip .punto" in sels]
        self.assertEqual(
            sueltas, [],
            f"`.chip .punto` vuelve a estar en la hoja ({sueltas}): el punto se "
            "pinta dentro del componente que lo declara, no en cualquier chip "
            "que resulte contener un `.punto`.")

    def test_el_estado_activo_del_chip_conserva_las_dos_mecanicas(self):
        """El sitio marca el chip activo con `.activa` y el sistema del
        rediseño con `aria-pressed`. Las dos van FUNDIDAS en un selector: si
        se cae `.chip.activa`, las tres tiras publicadas pierden el estado
        activo —y ningún test se enteraba—; si se cae `aria-pressed`, lo pierde
        todo lo que llegue del rediseño y además el lector de pantalla."""
        for archivo, patron in self.TIRAS.items():
            with self.subTest(fuente=archivo):
                fuente = (ROOT / archivo).read_text(encoding="utf-8")
                self.assertRegex(
                    fuente, patron,
                    f"{archivo} ya no pinta el chip activo con `.activa`: si de "
                    "verdad se pasó a `aria-pressed`, este test y la hoja se "
                    "actualizan juntos")
        fundidas = [sels for sels, _ in self.reglas
                    if ".chip.activa" in sels
                    and '.chip[aria-pressed="true"]' in sels]
        self.assertEqual(
            len(fundidas), 1,
            "`.chip.activa` y `.chip[aria-pressed=\"true\"]` tienen que compartir "
            "una sola regla. O falta una de las dos mecánicas, o el estilo se "
            "escribió dos veces y ya pueden divergir.")


class TestElEjeUnicoNoEntraDosVeces(unittest.TestCase):
    """La tira de chips queda fuera del eje, y eso es un test, no un comentario.

    `.chips` es la única exclusión de la lista del lote 5 y la única de esas
    clases con elementos en el marcado publicado: tres tiras de filtros que ya
    reciben su sangrado lateral de la `.page-section` que las contiene.
    Sumarles el eje las metería dos veces hacia adentro y dejarían de alinearse
    con el H2 de su propia sección. El comentario lo decía EN MAYÚSCULAS y aun
    así meter `.chips` en la lista dejaba los 511 tests en verde.
    """

    CSS = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
    MARCA = "SISTEMA DEL REDISEÑO 2026"

    @classmethod
    def setUpClass(cls):
        limpio = _css_sin_comentarios(cls.CSS)
        cls.reglas = _reglas(limpio)
        cls.eje = [sels for sels, decls in cls.reglas
                   if "padding-left: var(--eje)" in decls]

    def _clases(self, selector):
        return set(re.findall(r"\.([A-Za-z_][\w-]*)", selector))

    def test_hay_una_sola_regla_del_eje_y_lleva_los_dos_lados(self):
        """Guardián de sí mismo: si el analizador no encuentra la regla, el
        test de abajo comprobaría que `.chips` no está en una lista vacía."""
        self.assertEqual(len(self.eje), 1,
                         "el eje se aplica en una sola regla, o deja de ser único")
        self.assertGreaterEqual(len(self.eje[0]), 5,
                                "la lista del eje se ha quedado en nada")
        for imprescindible in ("details.pliegue", ".zona-datos"):
            self.assertIn(imprescindible, self.eje[0],
                          "no es la regla del eje que este test cree mirar")
        decls = [decls for sels, decls in self.reglas if sels == self.eje[0]][0]
        self.assertIn("padding-right: var(--eje)", decls,
                      "el eje sangra por los dos lados o no es un eje")

    def test_la_tira_de_chips_queda_fuera_de_la_lista_del_eje(self):
        dentro = [s for s in self.eje[0] if "chips" in self._clases(s)]
        self.assertEqual(
            dentro, [],
            f"`.chips` ha entrado en la lista del eje ({dentro}): ya recibe su "
            "sangrado de la `.page-section` que la contiene, así que el eje la "
            "mete DOS veces hacia adentro y las tres tiras de filtros "
            "publicadas dejan de alinearse con el H2 de su sección. Vuelve a "
            "la lista el día que los chips salgan de las `.page-section`, y "
            "ese día este test se retira con el cambio que lo justifica.")

    def test_ninguna_otra_regla_le_da_el_eje_a_los_chips(self):
        """Por la puerta de atrás cuenta igual: `.chips { padding-left:
        var(--eje) }` en su propia regla sangra dos veces lo mismo."""
        culpables = [", ".join(sels) for sels, decls in self.reglas
                     if any("var(--eje)" in d for d in decls)
                     and any("chips" in self._clases(s) or "chip" in self._clases(s)
                             for s in sels)]
        self.assertEqual(culpables, [],
                         f"una regla le da el eje a los chips: {culpables}")
