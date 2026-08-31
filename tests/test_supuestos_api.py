"""Tests de SUPUESTOS (online): los contratos externos sobre los que se
construyó el proyecto. Si uno falla, no es un bug del código — es que el mundo
cambió y hay que revisar la fuente correspondiente.

Saltar con: SKIP_ONLINE=1 python -m unittest tests/test_supuestos_api.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))

from common import CAPA_RETIRADA_DESDE, NOTA_SONDA, fetch_json

ONLINE = os.environ.get("SKIP_ONLINE") != "1"
COP = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosCopernicus(unittest.TestCase):
    def test_code_es_obligatorio(self):
        st, d = fetch_json(COP, note=NOTA_SONDA)
        self.assertTrue(not d or not d.get("results"),
                        "la API ahora lista sin code: ¡mejorar el ingestor!")

    def test_emsr916_existe_con_aois(self):
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        r = d["results"][0]
        self.assertEqual(r["code"], "EMSR916")
        self.assertGreaterEqual(len(r["aois"]), 7)
        self.assertIn("Colombia", [c["name"] for c in r["countries"]])

    def test_na_sigue_presente_en_stats(self):
        """El parser tolera 'NA'; verificar que el supuesto sigue vivo."""
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        raws = []
        for aoi in d["results"][0]["aois"]:
            for p in aoi.get("products") or []:
                for cat in (p.get("stats") or {}).values():
                    for v in cat.values():
                        raws += [v.get("total"), v.get("affected")]
        self.assertIn("NA", [str(x) for x in raws],
                      "ya no hay 'NA' en stats: revisar si cambió el esquema")

    def test_tipos_fuera_de_spec(self):
        """La spec OpenAPI lista FEP/REF/DEL/GRA; la realidad incluye GRM."""
        st, d = fetch_json(COP, {"code": "EMSR916"}, note=NOTA_SONDA)
        tipos = {p["type"] for a in d["results"][0]["aois"]
                 for p in a.get("products") or []}
        self.assertTrue(tipos - {"FEP", "REF", "DEL", "GRA"} or tipos,
                        "el parser debe seguir siendo tolerante a tipos nuevos")

    def test_hueco_documentado(self):
        """EMSR700 falla entre vecinos válidos: hueco puntual, no error."""
        st, d = fetch_json(COP, {"code": "EMSR700"}, note=NOTA_SONDA)
        self.assertFalse((d or {}).get("results"),
                         "EMSR700 ahora existe: retirar el supuesto del hueco")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosOficiales(unittest.TestCase):
    def test_socrata_sigue_parado_en_2022(self):
        st, d = fetch_json("https://www.datos.gov.co/resource/wwkg-r6te.json",
                           {"$select": "max(fecha)"}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        maxf = d[0].get("max_fecha", "")
        # si esto falla, ¡buena noticia! — el monitor debe celebrarlo, no ocultarlo
        self.assertLessEqual(maxf[:4], "2026",
                             "fecha imposible: revisar parseo")
        if maxf[:10] > "2022-12-31":
            print(f"\n*** SUPUESTO ROTO (bien): Socrata ya llega a {maxf} ***")

    def test_arcgis_ungrd_responde_con_edan(self):
        L = ("https://services2.arcgis.com/YVLx8xYoDXKccDfJ/arcgis/rest/services/"
             "REGISTRO_DE_EMERGENCIAS_EN_COLOMBIA/FeatureServer/0/query")
        st, d = fetch_json(L, {"where": "1=1", "f": "json", "resultRecordCount": 1,
                               "outFields": "MUERTOS,VIV_DESTRU,MUNICIPIO"},
                          note=NOTA_SONDA)
        self.assertEqual(st, 200)
        at = d["features"][0]["attributes"]
        for campo in ("MUERTOS", "VIV_DESTRU", "MUNICIPIO"):
            self.assertIn(campo, at, f"campo EDAN {campo} desapareció")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosMEN(unittest.TestCase):
    """La capa SISE del MEN se republica sin aviso y muta de tamaño y
    vocabulario en horas (el 28-ago-2026 pasó de ~50.000 filas a 9.273 entre
    dos sondas). Este supuesto vigila que siga viva y con sus campos clave.

    Desde el 31-ago-2026 la capa (y el ítem del tablero público que la
    enseñaba) quedaron inaccesibles en ArcGIS — certificado por dos vías
    independientes, docs/DECISIONES.md. Se certifica INACCESIBILIDAD, no
    intención: si un mantenimiento la devuelve, este supuesto lo celebra en
    vez de fallar en rojo cada día por algo ya diagnosticado.
    """

    def test_arcgis_men_responde_con_estado_fisico(self):
        L = ("https://services3.arcgis.com/Rv2iYa4TcJdIHIfq/arcgis/rest/services/"
             "SISE202608_Priorizadas_Final/FeatureServer/0/query")
        st, d = fetch_json(L, {"where": "1=1", "f": "json", "resultRecordCount": 1,
                               "outFields": "COD_DANE,ESTADO_FISICO,NOM_MUN"},
                          note=NOTA_SONDA)
        err = (d or {}).get("error") if isinstance(d, dict) else None
        if (st == 200 and isinstance(err, dict) and err.get("code") == 400
                and "invalid url" in str(err.get("message", "")).lower()):
            self.skipTest(
                f"la capa SISE sigue inaccesible en ArcGIS, como certificado "
                f"desde {CAPA_RETIRADA_DESDE} (docs/DECISIONES.md, "
                "common.py::CAPA_RETIRADA_DESDE). Si esto deja de saltarse, "
                "¡es la reaparición! — revisar "
                "alerts.py::men_sedes_capa_reaparecida")
        self.assertEqual(
            st, 200,
            f"la capa MEN falla con algo DISTINTO a la inaccesibilidad ya "
            f"certificada ({err}): esto sí es un supuesto nuevo por revisar")
        at = d["features"][0]["attributes"]
        for campo in ("COD_DANE", "ESTADO_FISICO", "NOM_MUN"):
            self.assertIn(campo, at, f"campo {campo} desapareció de la capa "
                                     "SISE: revisar ingest/sources/men_sedes.py")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosRUD(unittest.TestCase):
    """El RUD es un endpoint interno no documentado: si cambia, avisar."""

    def test_rud_responde_con_esquema(self):
        st, d = fetch_json(
            "https://rud.gestiondelriesgo.gov.co/home/json.php?temp=2026T",
            note=NOTA_SONDA)
        if st != 200:
            self.fail(f"RUD HTTP {st}: el endpoint cambió o cayó — revisar "
                      "ingest/sources/ungrd_rud.py y buscar el reemplazo")
        rows = d if isinstance(d, list) else (d or {}).get("data") or []
        self.assertTrue(rows, "RUD respondió vacío")
        for campo in ("departamento", "municipio", "fecha_evento", "familias"):
            self.assertIn(campo, rows[0], f"campo {campo} desapareció del RUD")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosFeeds(unittest.TestCase):
    def test_gdacs_emm_con_fechas(self):
        st, d = fetch_json("https://www.gdacs.org/gdacsapi/api/emm/getemmnewsbykey",
                           {"eventtype": "EQ", "eventid": "1557236"},
                           note=NOTA_SONDA)
        self.assertEqual(st, 200)
        if d:  # la ventana ~5 días puede vaciar el feed: eso es esperado
            self.assertIn("pubdate", d[0])
            self.assertIn("link", d[0])

    def test_chatmap_vivo_o_documentado(self):
        st, d = fetch_json("https://chatmap.hotosm.org/api/v1/map/"
                           "89319bbb-a14a-4dfd-b9a1-c83b8b55785f",
                           note=NOTA_SONDA)
        if st != 200:
            self.skipTest(f"ChatMap cerró (HTTP {st}): activar canal Kobo, "
                          "los snapshots conservan lo capturado")
        self.assertIn("features", d)

    def test_dyfi_geojson_disponible(self):
        st, d = fetch_json("https://earthquake.usgs.gov/fdsnws/event/1/query",
                           {"eventid": "us6000tjl2", "format": "geojson"},
                          note=NOTA_SONDA)
        self.assertEqual(st, 200)
        self.assertIn("dyfi", d["properties"]["products"])

    def test_celdas_dyfi_siguen_siendo_poligonos(self):
        """El filtro de proximidad de 30 km (municipios.py::DYFI_RADIO_KM) mide
        desde el centro del polígono de la celda. Si el USGS pasara a puntos,
        _centro_celda devolvería None y el filtro se abriría EN SILENCIO,
        volviendo a publicar la celda «Balboa» de Panamá como intensidad de
        Balboa (Risaralda). Este supuesto avisa antes de que eso pase."""
        ruta = Path(__file__).parent.parent / "data" / "public" / "dyfi_cells.geojson"
        if not ruta.exists():
            self.skipTest("sin dyfi_cells.geojson: ejecutar run_daily primero")
        import json as _json
        tipos = {(f.get("geometry") or {}).get("type")
                 for f in _json.loads(ruta.read_text()).get("features", [])}
        self.assertEqual(tipos, {"Polygon"},
                         f"las celdas DYFI ya no son solo polígonos ({tipos}): "
                         "revisar el filtro de proximidad de municipios.py")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestoFuenteEnGoogleNews(unittest.TestCase):
    """El nombre del medio de la mitad del corpus depende de un contrato ajeno:
    que el RSS de Google News siga declarando `<source url="…">Nombre</source>`.

    Es el único sitio donde ese dato viaja: el `<link>` apunta al agregador y
    el sufijo del titular no es fiable. Si Google deja de emitir la etiqueta,
    las noticias nuevas entrarían con `medio_canonico` en NULL y el sitio
    dejaría de nombrar medios sin que nadie se entere — R11 existe para que
    eso avise en vez de degradarse en silencio. Romperse aquí no es un bug:
    es la señal de que hay que buscar el medio por otra vía."""

    URL = ("https://news.google.com/rss/search?q=%22terremoto%22+%22colombia%22"
           "&hl=es-CO&gl=CO&ceid=CO:es")

    def test_el_rss_sigue_declarando_source_con_url(self):
        import xml.etree.ElementTree as ET
        from common import fetch
        sys.path.insert(0, str(Path(__file__).parent.parent / "ingest" / "sources"))
        from community_feeds import parse_rss

        st, body = fetch(self.URL, note=NOTA_SONDA)
        self.assertEqual(st, 200, "Google News no responde: sonda inconcluyente")
        items = list(ET.fromstring(body).iter("item"))
        self.assertTrue(items, "el feed llegó sin items: revisar la búsqueda")
        con_fuente = [i for i in items if i.find("source") is not None]
        self.assertEqual(
            len(con_fuente), len(items),
            "Google News dejó de declarar <source> en algún item: el medio de "
            "las noticias nuevas se queda sin recuperar (ver docs/DECISIONES.md, "
            "2026-08-19) — hay que buscar otra vía antes de que el hueco crezca")
        self.assertTrue(
            all(i.find("source").get("url") for i in con_fuente),
            "<source> ya no trae atributo url: medio_dominio se queda en NULL")
        self.assertTrue(
            parse_rss(body)[0]["medio_canonico"],
            "el parseo del proyecto ya no extrae el medio de este feed")

    def test_el_enlace_sigue_sin_llevar_al_medio(self):
        """El reverso del supuesto anterior, y una buena noticia si se rompe:
        el día que el feed publique la URL del medio, `url` dejará de apuntar
        al agregador y la limitación documentada desaparecerá."""
        from common import fetch
        st, body = fetch(self.URL, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        import xml.etree.ElementTree as ET
        enlaces = [(i.findtext("link") or "") for i in ET.fromstring(body).iter("item")]
        directos = [u for u in enlaces if "news.google.com" not in u]
        self.assertFalse(
            directos,
            f"¡el feed ya publica enlaces al medio ({directos[:2]})! Revisar "
            "docs/LIMITACIONES.md: la URL original ha dejado de perderse")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosWatcherHDX(unittest.TestCase):
    """HDX/CKAN (data.humdata.org): el catálogo que `alerts.datasets_hdx_nuevos`
    vigila. `package_search` es la acción pública de CKAN. Este supuesto no
    pregunta por el terremoto —eso cambia cada día, y el día que no haya
    ningún dataset del evento no es un fallo, es buena noticia— sino por la
    FORMA de la respuesta, que es lo que el parser del watcher asume."""

    def test_package_search_responde_con_el_esquema_esperado(self):
        st, d = fetch_json(
            "https://data.humdata.org/api/3/action/package_search",
            {"fq": "groups:col", "rows": 1}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        self.assertTrue(d.get("success"),
                        "package_search dejó de responder success=true")
        resultado = d.get("result") or {}
        self.assertIn("results", resultado, "la respuesta perdió 'result.results'")
        self.assertTrue(resultado["results"],
                        "Colombia sin ni un dataset en HDX: revisar el grupo 'col'")
        r = resultado["results"][0]
        for campo in ("id", "metadata_modified", "organization"):
            self.assertIn(campo, r, f"HDX dejó de traer '{campo}' en cada resultado")
        self.assertIn("title", r.get("organization") or {},
                      "el objeto organization ya no trae 'title'")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosWatcherArcGIS(unittest.TestCase):
    """arcgis.com/sharing/rest/search: el buscador público que
    `alerts.tablero_arcgis_eres` vigila esperando el tablero ERES/MinSalud.
    Como el tablero AÚN NO EXISTE (30-ago-2026), este supuesto no puede
    pedirlo por su nombre — vigila la FORMA de la respuesta del buscador con
    una consulta genérica que siempre trae resultados, no la consulta real
    del watcher."""

    def test_el_buscador_responde_con_el_esquema_esperado(self):
        st, d = fetch_json(
            "https://www.arcgis.com/sharing/rest/search",
            {"q": "Colombia", "f": "json", "num": 1}, note=NOTA_SONDA)
        self.assertEqual(st, 200)
        self.assertNotIn("error", d or {},
                         "arcgis.com/sharing/rest/search devolvió un error")
        self.assertIn("results", d, "la respuesta perdió 'results'")
        self.assertTrue(d["results"],
                        "una búsqueda genérica de 'Colombia' no trajo ni un "
                        "item: revisar el endpoint")
        r = d["results"][0]
        for campo in ("id", "title", "type", "owner", "modified"):
            self.assertIn(campo, r, f"arcgis.com dejó de traer '{campo}' en cada resultado")


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosUnosat(unittest.TestCase):
    """UNITAR-UNOSAT: el Centro Satelital de la ONU (https://unosat.org).

    No hay API documentada: estos supuestos describen los dos endpoints JSON
    que sirven a la web y de los que cuelga la capa de daño del monitor.
    """

    LISTADO = "https://unosat.org/our_products/"
    GLIDE = "EQ20260810COL"

    def test_el_listado_sigue_sirviendo_json(self):
        st, d = fetch_json(self.LISTADO, note=NOTA_SONDA)
        if st != 200 or not d:
            self.skipTest(
                f"UNOSAT no responde (HTTP {st}): la capa sobrevive con los "
                f"snapshots de data/snapshots/*/unosat_shapefiles.zip; si el "
                f"cierre es definitivo, congelar la fuente y documentarlo en "
                f"docs/LIMITACIONES.md")
        self.assertIn("products", d, "el listado cambió de forma")
        self.assertTrue(all("map_event" in p for p in d["products"]))

    def test_el_listado_sigue_sin_paginar(self):
        """El módulo consulta también los ids ya conocidos PORQUE el listado
        es una ventana fija sin filtros. Si algún día acepta paginación o
        filtro por GLIDE, la fuente puede simplificarse — sería buena noticia
        (R11): el histórico dejaría de depender de lo ya visto."""
        st, base = fetch_json(self.LISTADO, note=NOTA_SONDA)
        if st != 200 or not base:
            self.skipTest("UNOSAT no responde")
        st2, filtrado = fetch_json(self.LISTADO, {"glide": self.GLIDE},
                                   note=NOTA_SONDA)
        if st2 != 200 or not filtrado:
            self.skipTest("UNOSAT no responde al filtro")
        self.assertEqual(
            [p["map_event"]["id"] for p in base["products"]],
            [p["map_event"]["id"] for p in filtrado["products"]],
            "¡el listado ahora filtra por GLIDE! Simplificar "
            "unosat._productos_del_evento(): ya no hace falta consultar los "
            "ids conocidos para no perder el histórico")

    def test_el_detalle_trae_los_enlaces_de_descarga(self):
        st, d = fetch_json("https://unosat.org/our_products/4253",
                           note=NOTA_SONDA)
        if st != 200 or not d:
            self.skipTest(f"UNOSAT no responde (HTTP {st})")
        m = d["map_event"]
        self.assertEqual(m["glide"], self.GLIDE)
        for campo in ("shp_link", "pdf_name", "created_at", "title"):
            self.assertIn(campo, m, f"el detalle ya no trae {campo}")
        self.assertIn("latitude", d)

    def test_el_paquete_de_shapefiles_sigue_siendo_uno_solo(self):
        """Los productos 4251, 4252 y 4253 publican el MISMO zip. La fuente
        deduplica por sha256 contando con ello; si un día divergen, cada uno
        aportará datos propios y habrá MÁS cobertura, no menos — hay que
        revisar el resumen de la corrida, no arreglar nada a la carrera."""
        import hashlib
        from common import fetch
        shas = {}
        for pid in (4251, 4253):
            st, body = fetch(
                f"https://unosat.org/static/unosat_filesystem/{pid}/"
                f"EQ20260810COL_SHP.zip", note=NOTA_SONDA)
            if st != 200 or not body:
                self.skipTest(f"el paquete de {pid} no responde (HTTP {st})")
            shas[pid] = hashlib.sha256(body).hexdigest()
        self.assertEqual(
            shas[4251], shas[4253],
            "los paquetes de UNOSAT ya NO son idénticos: cada producto "
            "aporta datos propios. Revisar el conteo de unosat.run() — "
            "puede haber cobertura nueva que antes se descartaba por duplicada")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosSertit(unittest.TestCase):
    """ICube-SERTIT (https://sertit.unistra.fr), vía Charter 1048.

    Dos supuestos de naturaleza distinta. El catálogo se descarga y por tanto
    puede romperse como cualquier API. Los vectores NO: llegaron por correo y
    viven en el repo, así que ninguna caída de la fuente puede quitárnoslos —
    lo que este test vigila del lado de los datos es que sigan ahí y sigan
    siendo los mismos bytes.

    La sonda NO descarga los ZIP ni los mapas: son megas por corrida para
    releer lo que ya está archivado. Verificar el archivo es trabajo del
    módulo, no de la sonda.
    """

    ACCION = "https://sertit.unistra.fr/cartographie-rapide/cartoaction/845/"

    def test_el_catalogo_sigue_publicando_los_productos(self):
        """El catálogo vive en un JSON embebido en el HTML. Si SERTIT cambia
        el maquetado, esto avisa antes de que el monitor deje de ver
        productos nuevos sin enterarse."""
        from common import fetch
        from sources.sertit import productos_de_pagina
        st, body = fetch(self.ACCION, note=NOTA_SONDA)
        if st != 200 or not body:
            self.skipTest(
                "sertit.unistra.fr no responde. Plan de sucesión: los cinco "
                "paquetes de vectores están en data/documentos/sertit/ con su "
                "sha en sources_log, así que la capa publicada no depende de "
                "esta web. Lo que se pierde es descubrir productos nuevos.")
        productos = productos_de_pagina(body)
        self.assertGreaterEqual(
            len(productos), 5,
            "la acción 845 declaraba 5 productos: si ahora hay menos, la "
            "fuente los retiró; si el parseo devuelve 0, cambió el contrato "
            "del bloque js_data y hay que revisar productos_de_pagina()")
        for p in productos:
            self.assertTrue(p["nombre_base"],
                            "un producto sin nomAnnexes no se puede casar con "
                            "su paquete de vectores")

    def test_la_api_rest_documentada_sigue_caida(self):
        """SERTIT documenta —y la ESA anunció— una API REST pública que
        devolvía GeoJSON. El 20-ago-2026 daba 404 y se les avisó.

        Que este test falle sería una BUENA noticia (R11): significaría que la
        repusieron y que el monitor puede dejar de depender de un HTML.
        """
        from common import fetch
        st, _ = fetch("https://sertit.unistra.fr/wp-json/rms/v1/actions",
                      note=NOTA_SONDA)
        self.assertEqual(
            st, 404,
            "¡La API REST de SERTIT vuelve a responder! Sustituir el parseo "
            "del HTML por los endpoints documentados en "
            "/en/api-rest-for-icube-sertits-rapid-mapping-resources/ y "
            "actualizar el docstring de ingest/sources/sertit.py")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosOpsSalud(unittest.TestCase):
    """OPS/OMS: los Informes de Situación en paho.org, sin API — cada sitrep es
    un PDF que hay que descubrir desde su página, y el índice de la serie vive
    en el hub de Naciones Unidas en Colombia (otro dominio, otra fuente).
    """

    def test_la_url_numerica_del_hub_sigue_dando_404(self):
        """El hub de la ONU exige el slug completo: /es/320793 a secas no
        resuelve. Si esto empezara a dar 200, el detector de serie nueva
        podría simplificarse a la URL corta — comprobado el 30-ago-2026."""
        from common import fetch
        st, _ = fetch("https://colombia.un.org/es/320793", note=NOTA_SONDA)
        self.assertEqual(
            st, 404,
            "la URL numérica sola del hub ya no da 404: revisar si "
            "ops_salud.HUB_URL puede simplificarse")

    def test_el_hub_sigue_enlazando_los_sitrep_conocidos(self):
        """El hub es el índice barato del detector de serie nueva
        (`ops_salud.sitreps_en_hub`). No exige un número exacto —solo que
        siga enlazando AL MENOS los 5 sitrep que el monitor ya transcribió—:
        un número mayor sería una BUENA noticia (sitrep nuevo, R11), no un
        fallo de este supuesto."""
        from common import fetch
        from sources.ops_salud import HUB_URL, sitreps_en_hub, _transcripciones
        st, body = fetch(HUB_URL, note=NOTA_SONDA)
        if st != 200 or not body:
            self.skipTest(
                f"el hub de la ONU no responde (HTTP {st}). Plan de "
                "sucesión: los 5 sitrep ya transcritos están archivados en "
                "data/documentos/ops_salud/ con su sha256 en sources_log, así "
                "que la serie cargada no depende de este hub — solo se "
                "pierde la detección automática de un sitrep nuevo.")
        conocidos = set(_transcripciones())
        encontrados = set(sitreps_en_hub(body))
        self.assertTrue(
            conocidos <= encontrados,
            f"el hub dejó de enlazar sitrep ya transcritos: "
            f"{conocidos - encontrados}. Revisar si cambió el maquetado del "
            f"hub o si la ONU retiró un enlace")

    def test_cada_pagina_de_sitrep_sigue_publicando_el_boton_descargar(self):
        """El enlace al PDF se descubre SIEMPRE desde el
        `<div class="download-button">`, nunca adivinando el nombre del
        fichero — entre los 5 sitrep conocidos hay tres convenciones de
        nombre distintas. Si este selector deja de aparecer, hay que revisar
        `ops_salud.pdf_link_de_pagina` antes que cualquier otra cosa."""
        from common import fetch
        from sources.ops_salud import PAGINAS, pdf_link_de_pagina
        rotas = []
        for n, url in PAGINAS.items():
            st, body = fetch(url, note=NOTA_SONDA)
            if st != 200 or not body:
                continue    # R13: una página caída no tumba el supuesto entero
            if not pdf_link_de_pagina(body):
                rotas.append(n)
        self.assertFalse(
            rotas,
            f"la(s) página(s) de sitrep {rotas} ya no traen el "
            f"'<div class=\"download-button\">': cambió el maquetado de "
            f"paho.org y hay que revisar pdf_link_de_pagina()")


@unittest.skipUnless(ONLINE, "SKIP_ONLINE=1")
class TestSupuestosMSFT(unittest.TestCase):
    """Microsoft AI for Good Lab, vía HDX (CKAN público de data.humdata.org).

    No hay URL de fichero fija: `ingest/sources/msft.py` lee la lista de
    recursos de `package_show` EN CADA CORRIDA porque HDX reindexa y la URL
    de descarga es firmada y caduca. Este supuesto vigila que esa API siga
    respondiendo con la forma que el parser espera.

    La sonda NO descarga ningún gpkg/tif (240+ MB por corrida, y ya viven
    archivados en R2 con su sha256): solo el JSON de metadatos, igual que
    hace `TestSupuestosSertit` con el catálogo.
    """

    CKAN = "https://data.humdata.org/api/3/action/package_show"
    DATASETS = ("2026-colombia-earthquake",
               "colombia-2026-earthquake-pereira",
               "colombia-2026-earthquake-pereira-extended")

    def test_los_tres_datasets_siguen_publicados(self):
        for ds in self.DATASETS:
            st, d = fetch_json(f"{self.CKAN}?id={ds}", note=NOTA_SONDA)
            if st != 200 or not (d or {}).get("success"):
                self.skipTest(
                    f"{ds} no responde (HTTP {st}): la capa sobrevive con lo "
                    f"ya archivado — los gpkg/tif viven en R2 y las máscaras "
                    f"en git, todos con su sha256 en msft_recursos. Lo que se "
                    f"pierde es enterarse de una reedición nueva.")
            self.assertTrue(
                (d["result"].get("resources") or []),
                f"{ds} ya no declara recursos: HDX vació el dataset")

    def test_cali_sigue_trayendo_sus_cuatro_recursos(self):
        st, d = fetch_json(f"{self.CKAN}?id=2026-colombia-earthquake",
                           note=NOTA_SONDA)
        if st != 200 or not (d or {}).get("success"):
            self.skipTest("HDX no responde")
        recursos = d["result"]["resources"]
        formatos = sorted((r.get("format") or "").lower() for r in recursos)
        self.assertEqual(
            formatos, ["geojson", "geopackage", "geopackage", "geotiff"],
            "Cali cambió de forma: revisar msft._recursos_del_dataset() y el "
            "docstring de ingest/sources/msft.py")
        for r in recursos:
            self.assertTrue(
                r.get("download_url") or r.get("url"),
                f"{r.get('name')} no trae URL de descarga: no se puede archivar")

    def test_pereira_extended_sigue_siendo_una_reedicion_no_un_reemplazo(self):
        """Pereira Extended es un dataset CKAN aparte del Pereira original,
        no una versión nueva del mismo — si HDX lo fusionara algún día,
        `msft.DATASETS` tendría que dejar de tratarlos como dos entradas."""
        st_a, a = fetch_json(
            f"{self.CKAN}?id=colombia-2026-earthquake-pereira", note=NOTA_SONDA)
        st_b, b = fetch_json(
            f"{self.CKAN}?id=colombia-2026-earthquake-pereira-extended",
            note=NOTA_SONDA)
        if st_a != 200 or st_b != 200 or not (a or {}).get("success") \
                or not (b or {}).get("success"):
            self.skipTest("HDX no responde a uno de los dos datasets")
        self.assertNotEqual(a["result"]["id"], b["result"]["id"],
                            "Pereira y Pereira Extended ya son el mismo "
                            "dataset CKAN: simplificar msft.DATASETS")
