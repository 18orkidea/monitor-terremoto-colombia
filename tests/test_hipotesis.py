"""Tests de HIPÓTESIS: las afirmaciones centrales del proyecto, contra la BD
real tras una corrida. Se saltan si aún no hay datos.

Son deliberadamente estructurales (patrones), no de cifras exactas: los feeds
purgan y las cifras crecen. Si una hipótesis deja de cumplirse, el monitor
debe contarlo — estos tests detectan cuándo la historia cambió.
"""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

DB = ROOT / "data" / "monitor.sqlite"


def q(sql, *args):
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def skip_sin_datos(tabla):
    if not DB.exists():
        return "sin base de datos: ejecutar run_daily primero"
    try:
        if not q(f"SELECT COUNT(*) FROM {tabla}")[0][0]:
            return f"tabla {tabla} vacía"
    except sqlite3.OperationalError:
        return f"tabla {tabla} no existe"
    return None


class TestHipotesisBrechaOficial(unittest.TestCase):
    """H1 (v2 desde 16-ago): los canales masivos de UNGRD siguen parados
    (Socrata 2022, ArcGIS 2024) pero el RUD sí cubre el evento — la brecha
    ahora es entre municipios registrados y sin registrar."""

    def test_canales_masivos_siguen_parados(self):
        why = skip_sin_datos("official_events")
        if why:
            self.skipTest(why)
        maxf = q("SELECT MAX(fecha) FROM official_events"
                 " WHERE source='ungrd_arcgis'")[0][0]
        if maxf and maxf >= "2026-08-10":
            self.fail(f"¡El registro ArcGIS despertó ({maxf})! Actualizar la "
                      "narrativa de brechas del monitor")

    def test_rud_cubre_el_evento(self):
        why = skip_sin_datos("official_events")
        if why:
            self.skipTest(why)
        n = q("SELECT COUNT(*) FROM official_events WHERE source='ungrd_rud'"
              " AND fecha='2026-08-10'")[0][0]
        if n == 0:
            self.skipTest("sin datos RUD aún (¿endpoint caído? ver supuestos)")
        self.assertGreater(n, 0)

    def test_todo_municipio_rud_resuelve_coordenadas(self):
        """Ningún municipio que entre al RUD puede perderse del mapa: o está
        curado en MUNICIPIOS o lo resuelve el catálogo DIVIPOLA estático.
        Si esto AVISA, hay que ampliar divipola_coords.json (no romper)."""
        why = skip_sin_datos("rud_daily")
        if why:
            self.skipTest(why)
        from municipios import MUNICIPIOS, _find_divipola, _norm
        div_path = ROOT / "data" / "public" / "divipola_coords.json"
        divipola = (json.loads(div_path.read_text()).get("items")
                    if div_path.exists() else {})
        curados = set()
        for mun, meta in MUNICIPIOS.items():
            dep = _norm(meta["departamento"])
            for name in [mun, *meta.get("toponimos", [])]:
                curados.add((dep, _norm(name)))
        sin_coords = []
        for dep, mun in q("SELECT DISTINCT departamento, municipio FROM rud_daily"):
            key = (_norm(dep), _norm(mun))
            if key in curados:
                continue
            if not _find_divipola(divipola, mun, dep):
                sin_coords.append(f"{dep}/{mun}")
        self.assertEqual(sin_coords, [],
                         f"Municipios RUD sin coordenadas (ni curados ni en "
                         f"DIVIPOLA): {sin_coords} — ampliar divipola_coords.json")


class TestReferenciasEstaticas(unittest.TestCase):
    """Datos de referencia que ya NO se piden a diario (población DANE,
    catálogo DIVIPOLA): al salir de la corrida, nada volvería a avisar si el
    fichero versionado desapareciera o se vaciara — y el sitio publicaría
    municipios sin población sin que saltara ninguna alarma."""

    def _cargar(self, nombre):
        p = ROOT / "data" / "public" / nombre
        self.assertTrue(p.exists(), f"falta {nombre}: lo genera un workflow "
                                    f"propio, no la corrida diaria")
        return json.loads(p.read_text())

    def test_la_poblacion_dane_sigue_disponible(self):
        d = self._cargar("dane_population_2026.json")
        items = d.get("items") or {}
        self.assertGreater(len(items), 1000,
                           "las proyecciones DANE cubren ~1.100 municipios")
        muestra = next(iter(items.values()))
        self.assertGreater(muestra.get("poblacion_2026") or 0, 0)

    def test_el_catalogo_divipola_sigue_disponible(self):
        d = self._cargar("divipola_coords.json")
        self.assertGreater(len(d.get("items") or {}), 1000)

    def test_los_municipios_publicados_conservan_su_poblacion(self):
        p = ROOT / "data" / "public" / "municipios.json"
        if not p.exists():
            self.skipTest("sin municipios.json")
        items = json.loads(p.read_text())["items"]
        sin_pob = [m["municipio"] for m in items if not m.get("poblacion_2026")]
        self.assertEqual(sin_pob, [],
                         f"municipios publicados sin población: {sin_pob} — "
                         f"¿se perdió el JSON del DANE?")


class TestHipotesisAtencion(unittest.TestCase):
    """H2: la atención mediática decae mientras el reporte ciudadano persiste."""

    def _serie(self, col):
        why = skip_sin_datos("media_volume")
        if why:
            self.skipTest(why)
        rows = q(f"SELECT fecha, MAX({col}) FROM media_volume"
                 " WHERE event_key='EQ1557236' AND fecha>='2026-08-10'"
                 " GROUP BY fecha ORDER BY fecha")
        return [(f, v) for f, v in rows if v is not None]

    def test_prensa_decae(self):
        s = self._serie("n_noticias_emm")
        if len(s) < 3:
            self.skipTest("serie EMM demasiado corta (feed purgado)")
        self.assertGreater(s[0][1], s[-1][1] * 2,
                           "la prensa ya no decae ×2: la historia cambió")

    def test_ciudadano_no_sigue_a_la_prensa(self):
        emm = dict(self._serie("n_noticias_emm"))
        chat = dict(self._serie("n_chatmap"))
        comunes = sorted(set(emm) & set(chat))
        if len(comunes) < 4:
            self.skipTest("series no comparables aún")
        # pico ciudadano posterior al pico de prensa
        pico_emm = max(comunes, key=lambda d: emm[d])
        pico_chat = max(comunes, key=lambda d: chat[d])
        self.assertGreater(pico_chat, pico_emm,
                           "el pico ciudadano ya no es posterior al de prensa")

    def test_entregas_en_dias_de_baja_atencion(self):
        why = skip_sin_datos("products")
        if why:
            self.skipTest(why)
        emm = dict(self._serie("n_noticias_emm"))
        if not emm:
            self.skipTest("sin serie EMM")
        pico = max(emm.values())
        entregas = [r[0][:10] for r in q(
            "SELECT delivery_time FROM products WHERE code='EMSR916'"
            " AND delivery_time IS NOT NULL AND ptype='GRA'")]
        tardias = [d for d in entregas if d in emm and emm[d] < pico * 0.5]
        self.assertTrue(tardias,
                        "ninguna entrega cayó en días de atención <50% del pico")


class TestHipotesisCruce(unittest.TestCase):
    """H3: el rigor del cruce se mantiene en los datos reales."""

    def test_ningun_coincide_sin_evidencia_oficial(self):
        why = skip_sin_datos("crosscheck")
        if why:
            self.skipTest(why)
        rows = q("SELECT c.aoi_name FROM crosscheck c WHERE c.estado='coincide'"
                 " AND NOT EXISTS (SELECT 1 FROM evidence e"
                 "  WHERE e.aoi_name=c.aoi_name AND e.tipo='oficial')")
        self.assertFalse(rows, f"AOIs en 'coincide' sin evidencia oficial: {rows}")

    def test_western_colombia_no_comparable(self):
        why = skip_sin_datos("crosscheck")
        if why:
            self.skipTest(why)
        rows = q("SELECT estado FROM crosscheck WHERE aoi_name='Western Colombia'"
                 " ORDER BY snapshot_date DESC LIMIT 1")
        if not rows:
            self.skipTest("sin fila para Western Colombia")
        estado = rows[0][0]
        # su GRM está en espera sin stats; si ya entregó, este supuesto caduca
        prod = q("SELECT status_code FROM products WHERE code='EMSR916'"
                 " AND aoi_name='Western Colombia'"
                 " ORDER BY snapshot_date DESC LIMIT 1")
        if prod and prod[0][0] == "W":
            self.assertEqual(estado, "no_comparable")


class TestHipotesisCiudadana(unittest.TestCase):
    """H4: hay reportes ciudadanos verificables y algunos validan AOIs."""

    def test_reportes_dentro_de_aois(self):
        why = skip_sin_datos("citizen_reports")
        if why:
            self.skipTest(why)
        n = q("SELECT COUNT(*) FROM citizen_reports"
              " WHERE json_extract(checks,'$.aoi') IS NOT NULL")[0][0]
        self.assertGreater(n, 0, "ningún reporte ciudadano cae en un AOI: "
                           "el cruce satélite↔suelo no está funcionando")

    def test_privacidad_coordenadas(self):
        why = skip_sin_datos("citizen_reports")
        if why:
            self.skipTest(why)
        rows = q("SELECT lat_pub, lon_pub FROM citizen_reports"
                 " WHERE lat_pub IS NOT NULL LIMIT 200")
        for lat, lon in rows:
            self.assertEqual(round(lat, 3), lat, "lat_pub sin redondear")
            self.assertEqual(round(lon, 3), lon, "lon_pub sin redondear")

    def test_publicado_no_contiene_coordenada_exacta(self):
        pub = ROOT / "data" / "public" / "chatmap.geojson"
        if not pub.exists():
            self.skipTest("sin chatmap.geojson publicado")
        gj = json.loads(pub.read_text())
        exactas = q("SELECT lat, lon FROM citizen_reports"
                    " WHERE lat IS NOT NULL AND ABS(lat-ROUND(lat,3))>1e-9 LIMIT 50")
        publicadas = {tuple(f["geometry"]["coordinates"][::-1])
                      for f in gj["features"]}
        for lat, lon in exactas:
            self.assertNotIn((lat, lon), publicadas,
                             "¡coordenada exacta filtrada al GeoJSON público!")


class TestPublicacionBienFormada(unittest.TestCase):
    """El contrato de data/public/: lo que el mapa espera encontrar."""

    def _mon(self):
        p = ROOT / "data" / "public" / "monitor.json"
        if not p.exists():
            self.skipTest("sin monitor.json")
        return json.loads(p.read_text())

    def test_media_volume_es_serie(self):
        mv = self._mon()["media_volume"]
        self.assertIsInstance(mv, list)
        for row in mv:
            self.assertIsInstance(row, dict)
            self.assertRegex(row["fecha"], r"^\d{4}-\d{2}-\d{2}$")

    def test_chatmap_publica_los_ceros_observados(self):
        mv = {d["fecha"]: d.get("chatmap")
              for d in self._mon()["media_volume"]}
        self.assertEqual(mv.get("2026-08-16"), 0)
        self.assertEqual(mv.get("2026-08-19"), 0)

    def test_aois_con_cruce_y_resumen(self):
        for a in self._mon()["aois"]:
            self.assertIn("cruce", a)
            self.assertIn(a["cruce"]["estado"],
                          {"coincide", "prensa", "ciudadano", "pendiente",
                           "no_comparable"})
            self.assertIn("poblacion", a["resumen"])

    def test_geojson_validos(self):
        for name in ("aois.geojson", "chatmap.geojson", "ungrd_sismos.geojson",
                     "municipios.geojson"):
            p = ROOT / "data" / "public" / name
            if not p.exists():
                continue
            gj = json.loads(p.read_text())
            self.assertEqual(gj["type"], "FeatureCollection", name)
            for f in gj["features"][:5]:
                self.assertIn("geometry", f, name)

    def test_municipios_resumen(self):
        mon = self._mon()
        self.assertIn("municipios", mon)
        self.assertGreaterEqual(mon["municipios"]["total"],
                                mon["municipios"]["fuera_de_aoi_copernicus"])

    def test_noticias_tienen_etiquetas_territoriales(self):
        p = ROOT / "data" / "public" / "noticias.json"
        if not p.exists():
            self.skipTest("sin noticias.json")
        data = json.loads(p.read_text())
        tagged = [n for n in data["items"]
                  if n.get("departamentos") or n.get("municipios")]
        self.assertGreater(len(tagged), 0)

    def test_ningun_titular_publicado_es_anterior_al_sismo(self):
        """El corpus público empieza el día del terremoto. Lo que se publica no
        es «prensa que menciona el municipio», es prensa de ESTE desastre: si
        un municipio aparece sin titulares, la ausencia es el dato."""
        from common import FECHA_SISMO
        p = ROOT / "data" / "public" / "noticias.json"
        if not p.exists():
            self.skipTest("sin noticias.json")
        previos = [n for n in json.loads(p.read_text())["items"]
                   if (n.get("fecha") or "")[:10]
                   and (n.get("fecha") or "")[:10] < FECHA_SISMO]
        self.assertEqual(previos[:3], [],
                         f"{len(previos)} titulares anteriores al sismo en "
                         f"noticias.json")

    def test_los_ejemplos_de_prensa_son_del_evento(self):
        """La capa de municipios y la evidencia por AOI enseñan titulares
        concretos: un titular de 2024 citado como prueba de daño es peor que
        una cifra desviada, porque se lee como una afirmación."""
        from common import FECHA_SISMO
        malos = []
        p = ROOT / "data" / "public" / "municipios.json"
        if p.exists():
            for m in json.loads(p.read_text())["items"]:
                for ej in m.get("noticias_ejemplo") or []:
                    if (ej.get("fecha") or "")[:10] < FECHA_SISMO and ej.get("fecha"):
                        malos.append(f"{m['municipio']}: {ej.get('titulo')}")
        mon = ROOT / "data" / "public" / "monitor.json"
        if mon.exists():
            for a in json.loads(mon.read_text()).get("aois", []):
                for ej in a.get("prensa_ejemplos") or []:
                    if (ej.get("fecha") or "")[:10] < FECHA_SISMO and ej.get("fecha"):
                        malos.append(f"{a['aoi']}: {ej.get('titular')}")
        self.assertEqual(malos, [])

    def test_exposicion_coherente(self):
        exp = self._mon().get("exposicion")
        if not exp:
            self.skipTest("sin exposición PAGER aún")
        self.assertGreaterEqual(exp["expuesta_mmi6plus"],
                                exp["en_aois_copernicus"],
                                "no puede haber más población en AOIs que expuesta")
        self.assertLessEqual(exp["pct_cubierta"], 100)


class TestHipotesisTrazabilidad(unittest.TestCase):
    """H5: toda cifra es rastreable (sources_log + snapshots)."""

    def test_log_con_hashes(self):
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        sin_hash = q("SELECT COUNT(*) FROM sources_log"
                     " WHERE http_status=200 AND sha256 IS NULL")[0][0]
        self.assertEqual(sin_hash, 0, "peticiones 200 sin sha256")

    def test_ninguna_pagina_publica_un_feed_como_si_fuera_un_medio(self):
        """El bug que esto habría cazado: la portada firmaba dos titulares de
        Istmina como «Google News — Istmina» mientras la página de titulares
        daba, para esas mismas URLs, «Publimetro Colombia» e «Infobae». Dos
        páginas del mismo sitio contándose distinto el mismo día en que el
        monitor anunciaba que cada titular dice de qué medio es.

        Una búsqueda no es una cabecera: lo que se publique como medio no
        puede llevar el nombre de un feed."""
        import json as _json
        # `firmas` = campos de los que puede salir el medio que ve el lector.
        # En noticias.json, `medio` guarda el feed a propósito y la página lo
        # ignora vía UI.medioDe; en prensa_ejemplos no hay tal cosa: lo que se
        # publique ahí es la firma de la evidencia y tiene que ser cabecera.
        for fichero, camino, firmas in (
                ("noticias.json", None, ("medio_canonico",)),
                ("monitor.json", ("aois", "prensa_ejemplos"),
                 ("medio_canonico", "medio"))):
            ruta = ROOT / "data" / "public" / fichero
            if not ruta.exists():
                self.skipTest(f"sin {fichero}: ejecutar publish primero")
            datos = _json.loads(ruta.read_text())
            items = ([p for a in datos[camino[0]] for p in a.get(camino[1]) or []]
                     if camino else datos["items"])
            # Que la clave EXISTA, antes de mirar su valor: así se manifestó el
            # bug de la portada — `prensa_ejemplos` no traía `medio_canonico`,
            # y una comprobación que solo mirase valores habría pasado en verde
            # sobre datos rotos, que es exactamente lo que hizo la primera
            # versión de este test.
            sin_campo = [i for i in items if "medio_canonico" not in i]
            self.assertEqual(
                len(sin_campo), 0,
                f"{fichero}: {len(sin_campo)} piezas sin la clave "
                "`medio_canonico` — la página caería al nombre del feed")
            for campo in firmas:
                colados = sorted({i[campo] for i in items
                                  if (i.get(campo) or "").startswith("Google News")})
                self.assertEqual(
                    colados, [],
                    f"{fichero} publica nombres de feed en `{campo}`: {colados[:3]}")

    def test_una_derivacion_no_finge_ser_una_peticion(self):
        """`sources_log` tiene tres escritores: `fetch()`, que pide por HTTP;
        `registrar_derivacion()`, que anota lo deducido del propio archivo; y
        `registrar_entrega()`, que anota un cuerpo llegado por otro canal. Sin
        este invariante, mañana una derivación podría registrarse con
        `http_status` 200 y colarse en el régimen fuerte de trazabilidad por la
        puerta de atrás — con sha256 de un cuerpo que nadie descargó.

        Las entregas SÍ traen sha, bytes y ruta —el fichero existe y se puede
        verificar— y por eso quedan exentas por contrato explícito, no por
        texto libre. Lo que ninguna de las dos puede hacer es fingir un
        `http_status`: eso sigue siendo exclusivo de una petición real.
        """
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        from common import NOTA_ENTREGA
        impostoras = q(
            "SELECT url, http_status, sha256, bytes, snapshot_path"
            " FROM sources_log WHERE http_status IS NULL AND ("
            "  sha256 IS NOT NULL OR bytes IS NOT NULL"
            "  OR snapshot_path IS NOT NULL)"
            " AND (note IS NULL OR note NOT LIKE ?)", NOTA_ENTREGA + "%")
        self.assertEqual(
            impostoras, [],
            "filas sin petición que traen rastro de una: si no hubo HTTP, no "
            "hay hash ni cuerpo ni snapshot propio que registrar")

        # La exención de las entregas no puede ser solo sustractiva: si se
        # limitara a sacarlas del invariante, cualquier fila podría escaparse
        # poniéndose la nota. A cambio de salir, se les exige MÁS que al resto:
        # cuerpo presente, sha coincidente y ruta dentro del archivo.
        entregas = q(
            "SELECT url, sha256, bytes, snapshot_path FROM sources_log"
            " WHERE note LIKE ?", NOTA_ENTREGA + "%")
        import hashlib
        for url, sha, bytes_, ruta in entregas:
            self.assertTrue(
                sha and bytes_ and ruta,
                f"entrega sin cuerpo verificable ({url}): una entrega existe "
                f"precisamente porque hay un fichero — si no lo hay, es una "
                f"derivación y va sin sha")
            self.assertTrue(
                ruta.startswith("data/documentos/"),
                f"{ruta}: las entregas viven en data/documentos/, no en "
                f"snapshots — un cuerpo que nadie descargó no es un snapshot")
            f = ROOT / ruta
            self.assertTrue(f.exists(), f"{ruta}: registrado y ausente")
            self.assertEqual(
                hashlib.sha256(f.read_bytes()).hexdigest(), sha,
                f"{ruta}: el cuerpo cambió desde que se registró")

    def test_un_304_apunta_a_un_cuerpo_que_sigue_estando(self):
        """Un 304 dice «lo mismo que ya tienes». Si eso que ya teníamos
        desapareciera, la fila estaría afirmando la vigencia de un cuerpo que
        nadie puede leer — y el ahorro habría costado el archivo.

        El régimen fuerte mira las filas 200 con cuerpo; este es su reverso:
        las filas SIN cuerpo que apuntan al de otro día.
        """
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        filas = q("SELECT url, snapshot_path, sha256, bytes FROM sources_log"
                  " WHERE http_status=304")
        if not filas:
            self.skipTest("ninguna fuente ha contestado 304 todavía")
        import hashlib
        rotos = []
        for url, spath, sha, bytes_ in filas:
            if bytes_:
                rotos.append(f"{url}: un 304 no trae cuerpo, y declara "
                             f"{bytes_} bytes")
            if sha is None or spath is None:
                # 304 a una petición sin validadores: R13, se registra como el
                # hecho raro que es y no afirma nada del archivo
                if sha is not None or spath is not None:
                    rotos.append(f"{url}: 304 a medias — o certifica un cuerpo "
                                 f"con su sha Y su ruta, o no certifica nada")
                continue
            f = ROOT / spath
            if not f.exists():
                rotos.append(f"{spath}: la fila del 304 lo declara vigente y "
                             f"no está")
            elif hashlib.sha256(f.read_bytes()).hexdigest() != sha:
                rotos.append(f"{spath}: el cuerpo que el 304 declaró vigente "
                             f"ya no es el que dice el log")
        self.assertFalse(rotos, "304 sin cuerpo detrás: " + "; ".join(rotos[:5]))

    def test_la_carpeta_del_dia_no_miente_sobre_lo_que_no_contiene(self):
        """`reutilizados.txt` es la copia legible de lo que dice el log: sin un
        guardián, las dos superficies divergen (M2). Cada línea tiene que
        corresponder a una fila que apunte a ese mismo cuerpo."""
        from common import REUTILIZADOS
        indices = sorted((ROOT / "data" / "snapshots").glob(f"*/{REUTILIZADOS}"))
        if not indices:
            self.skipTest("ningún día ha reutilizado un cuerpo todavía")
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        registradas = {(r[0], r[1]) for r in q(
            "SELECT snapshot_path, sha256 FROM sources_log"
            " WHERE snapshot_path IS NOT NULL AND sha256 IS NOT NULL")}
        malas = []
        for f in indices:
            for linea in f.read_text(encoding="utf-8").splitlines():
                if not linea or linea.startswith("#"):
                    continue
                partes = linea.split("\t")
                if len(partes) != 3:
                    malas.append(f"{f}: línea ilegible «{linea[:60]}»")
                    continue
                _, spath, sha = partes
                if (spath, sha) not in registradas:
                    malas.append(f"{f}: apunta a {spath} y el log no lo dice")
                elif not (ROOT / spath).exists():
                    malas.append(f"{f}: apunta a {spath}, que no está")
        self.assertFalse(malas, "; ".join(malas[:5]))

    def test_snapshot_de_copernicus_existe(self):
        snaps = list((ROOT / "data" / "snapshots").glob("*/copernicus_EMSR916.json"))
        if not DB.exists():
            self.skipTest("sin datos")
        self.assertTrue(snaps, "sin snapshot crudo de EMSR916")
        data = json.loads(snaps[-1].read_text())
        self.assertIn("results", data)

    # Desde el 17-ago rige el régimen fuerte: toda petición 200 con cuerpo
    # deja snapshot_path, el fichero existe y su sha256 coincide con el log.
    # Las filas anteriores no se exigen: su hueco está documentado en
    # docs/LIMITACIONES.md (el log también es archivo y no se retoca).
    REGIMEN_FUERTE_DESDE = "2026-08-17"

    # Los vídeos y audios ciudadanos no caben en git (580+ MB): su cuerpo se
    # archiva en el bucket R2 y el repo versiona el manifiesto auditable
    # `data/r2_manifest.json` — está en docs/LIMITACIONES.md y en .gitignore.
    # Para ellos la evidencia es estar en el manifiesto con el mismo sha256, no
    # el fichero en disco: en un clon limpio nunca está, y exigirlo hacía que el
    # test pasara en la máquina del mantenedor y fallara en CI.
    ARCHIVO_EN_R2 = (".mp4", ".mov", ".webm", ".opus", ".ogg", ".m4a")

    def _manifiesto_r2(self):
        f = ROOT / "data" / "r2_manifest.json"
        if not f.exists():
            return {}
        return {o["objeto"]: o.get("sha256")
                for o in json.loads(f.read_text()).get("objetos", [])}

    def test_todo_cuerpo_publicado_tiene_snapshot_verificable(self):
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        # las sondas de contrato (test_supuestos_api) son diagnóstico, no
        # evidencia publicada: quedan logueadas pero sin cuerpo archivado
        from common import NOTAS_SONDA
        marcas = ",".join("?" * len(NOTAS_SONDA))
        filas = q("SELECT snapshot_path, sha256 FROM sources_log"
                  f" WHERE ts >= ? AND http_status=200 AND bytes > 0"
                  f" AND (note IS NULL OR note NOT IN ({marcas}))",
                  self.REGIMEN_FUERTE_DESDE, *NOTAS_SONDA)
        if not filas:
            self.skipTest("aún no hay corridas bajo el régimen fuerte")
        import hashlib
        manifiesto = self._manifiesto_r2()
        sin_ruta, rotos = 0, []
        for spath, sha in filas:
            if not spath:
                sin_ruta += 1
                continue
            f = ROOT / spath
            if spath.lower().endswith(self.ARCHIVO_EN_R2):
                # se comprueba SIEMPRE, exista o no en disco: si solo se mirara
                # cuando falta, el manifiesto podría desfasarse durante meses en
                # la máquina donde sí están los ficheros y saltar solo en CI
                clave = spath.rsplit("/", 1)[-1]
                if clave not in manifiesto:
                    rotos.append(f"{spath}: no está en el manifiesto de R2 — "
                                 f"un cuerpo fuera de git y fuera del manifiesto "
                                 f"no es recuperable ni auditable")
                elif manifiesto[clave] != sha:
                    rotos.append(f"{spath}: el manifiesto de R2 declara otro sha256")
            elif not f.exists():
                rotos.append(f"{spath}: no existe")
            if f.exists() and hashlib.sha256(f.read_bytes()).hexdigest() != sha:
                rotos.append(f"{spath}: sha no coincide")
        self.assertEqual(sin_ruta, 0,
                         f"{sin_ruta} peticiones 200 sin snapshot_path desde "
                         f"{self.REGIMEN_FUERTE_DESDE} — un sha sin cuerpo no es evidencia")
        self.assertFalse(rotos, "snapshots rotos: " + "; ".join(rotos[:5]))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPaquetesDeSertit(unittest.TestCase):
    """Los ZIP de ICube-SERTIT son el único dato del monitor que no se puede
    volver a descargar: su web los entrega por correo. Si uno cambia o
    desaparece, la cifra publicada deja de tener respaldo — y eso hay que
    comprobarlo SIN red, porque el clon del futuro no la tendrá.
    """

    def test_los_paquetes_archivados_no_han_cambiado(self):
        import hashlib
        docs = ROOT / "data" / "documentos" / "sertit"
        if not docs.exists():
            self.skipTest("sin paquetes archivados")
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        from common import NOTA_ENTREGA
        filas = q("SELECT snapshot_path, sha256 FROM sources_log"
                  " WHERE note LIKE ? AND snapshot_path LIKE ?",
                  NOTA_ENTREGA + "%", "data/documentos/sertit/%")
        if not filas:
            self.skipTest("los paquetes aún no se han registrado")
        for ruta, sha in filas:
            f = ROOT / ruta
            self.assertTrue(f.exists(), f"{ruta}: consta y no está en disco")
            self.assertEqual(
                hashlib.sha256(f.read_bytes()).hexdigest(), sha,
                f"{ruta}: cambió de contenido desde que se registró")

    def test_ningun_cuerpo_entregado_vive_sin_su_fila(self):
        """El recorrido inverso: todo fichero de `data/documentos/` tiene fila.

        El invariante de arriba comprueba «fila ⇒ cuerpo». Sin este, un
        fichero podría entrar al repositorio sin que nada dijera de dónde
        salió ni cuándo — que es exactamente el modo de fallo que dejó un
        `sertit_catalogo_845.json` huérfano en snapshots al retirar un
        mecanismo, y que solo cazó una revisión humana.
        """
        docs = ROOT / "data" / "documentos"
        if not docs.exists():
            self.skipTest("sin entregas archivadas")
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        registrados = {r[0] for r in q(
            "SELECT snapshot_path FROM sources_log"
            " WHERE snapshot_path LIKE 'data/documentos/%'")}
        # Se comprueba fuente a fuente. Los cuerpos viajan en git y las filas
        # no —la sqlite se reconstruye—, así que en una copia con base poblada
        # donde esa fuente aún no se ha ingerido no falta ninguna fila: falta
        # la corrida. Acusar ahí sería un falso positivo, y un guardián que
        # acusa en falso acaba desactivado por quien se cansa de verlo en rojo.
        # Lo que sí es un fallo real: que unos cuerpos de la misma fuente
        # consten y otros no.
        for sub in sorted(d for d in docs.iterdir() if d.is_dir()):
            cuerpos = [f for f in sub.rglob("*") if f.is_file()]
            if not cuerpos:
                continue
            rel = [str(f.relative_to(ROOT)) for f in cuerpos]
            presentes = [r for r in rel if r in registrados]
            if not presentes:
                continue        # esta fuente no se ha ingerido en esta copia
            huerfanos = [r for r in rel if r not in registrados]
            self.assertEqual(
                huerfanos, [],
                f"{sub.name}: hay cuerpos registrados y otros no. Un fichero "
                f"que nadie registró no se puede fechar ni atribuir, y aquí no "
                f"vale la excusa de «esta fuente no se ha ingerido»: sus "
                f"hermanos sí constan")

    def test_cada_paquete_registrado_una_sola_vez(self):
        """Una entrega es un suceso, no un estado. Si se registrara en cada
        corrida, dentro de un año el log diría que SERTIT entregó cinco ZIP
        todos los días — sucesos que no ocurrieron."""
        why = skip_sin_datos("sources_log")
        if why:
            self.skipTest(why)
        from common import NOTA_ENTREGA
        filas = q("SELECT sha256, COUNT(*) FROM sources_log"
                  " WHERE note LIKE ? GROUP BY sha256", NOTA_ENTREGA + "%")
        repetidas = [(sha, n) for sha, n in filas if n > 1]
        self.assertEqual(
            repetidas, [],
            "el mismo cuerpo registrado como entrega más de una vez: el log "
            "estaría afirmando entregas que no ocurrieron")

    def test_los_puntos_sin_grado_no_cuentan_como_dano_clasificado(self):
        """Nueve puntos de SERTIT en Cali llegan con `Not Applicable`: la
        fuente los señaló y no les asignó grado. Se pintan, pero no entran en
        un total que se anuncia como daño clasificado."""
        import json as _json
        pub = ROOT / "data" / "public"
        if not (pub / "sertit_damage.geojson").exists():
            self.skipTest("sin capa de SERTIT")
        capa = _json.loads((pub / "sertit_damage.geojson").read_text(encoding="utf-8"))
        sin_grado = [f for f in capa["features"]
                     if (f["properties"].get("dano") or "").lower().startswith("not applicable")]
        mon = _json.loads((pub / "monitor.json").read_text(encoding="utf-8"))
        sat = mon.get("satelital") or {}
        if not sat:
            self.skipTest("sin recuento satelital")
        fuentes = sum(d["fuentes"].get("sertit", 0)
                      for d in sat["por_municipio"].values())
        self.assertEqual(
            fuentes, len(capa["features"]) - len(sin_grado),
            "el recuento satelital cuenta puntos que la fuente no clasificó")


class TestVocabularioDeLasFuentes(unittest.TestCase):
    """Una fuente que estrena una palabra no puede pasar desapercibida.

    El 21-ago-2026, al reeditar Viterbo y publicar Zarzal, UNOSAT empezó a
    declarar confianzas que su capa nunca había usado —`Uncertain` y
    `Medium`—. El sitio solo sabía traducir `To Be Evaluated`, así que las
    nuevas se habrían publicado en inglés sin que nadie se enterase. Nadie lo
    cazó: lo vio una persona leyendo los datos.

    Que este test falle es buena noticia (R11): significa que la fuente ha
    dicho algo que no decía, y eso hay que mirarlo antes de publicarlo.
    """

    def test_toda_confianza_de_unosat_tiene_traduccion(self):
        import json as _json
        import re as _re
        capa = ROOT / "data" / "public" / "unosat_damage.geojson"
        app = ROOT / "site" / "app.js"
        if not capa.exists() or not app.exists():
            self.skipTest("sin capa de UNOSAT")
        valores = {(f["properties"] or {}).get("confianza")
                   for f in _json.loads(capa.read_text(encoding="utf-8"))["features"]}
        valores.discard(None)
        dicc = app.read_text(encoding="utf-8")
        bloque = dicc[dicc.index("const UNOSAT_ES"):dicc.index("};", dicc.index("const UNOSAT_ES"))]
        conocidos = set(_re.findall(r'"([^"]+)":', bloque))
        huerfanos = sorted(valores - conocidos)
        self.assertEqual(
            huerfanos, [],
            f"UNOSAT declara confianzas que el sitio no sabe traducir: "
            f"{huerfanos}. Se publicarían en inglés, y peor: nadie habría "
            f"decidido qué significan para el lector")


class TestSupuestoBusquedaMunicipal(unittest.TestCase):
    """R11: a todo municipio que el RUD registra hay que haberle preguntado.

    El monitor publicaba «ni un titular» de 114 municipios y en 104 de ellos
    nunca había llegado a preguntar: la lista de búsquedas recorría el
    catálogo curado a mano, no el que abre el propio registro oficial. Una
    celda vacía por «no hemos buscado» y otra por «no hay nada» se veían
    exactamente igual.

    Que este test falle es la señal de que hay trabajo, no de que algo va mal:
    significa que el RUD estrenó un municipio al que el monitor no sabe
    preguntar. Se mira, se decide y se anota aquí —nunca se amplía la lista de
    excepciones sin mirar el municipio—.
    """

    # Municipios que NO pueden tener búsqueda propia, uno a uno y por su
    # nombre: todos se llaman igual que un departamento colombiano, así que
    # `"bolivar" "cauca"` casaría con los titulares del departamento y el feed,
    # que declara su municipio, colaría esa atribución por la puerta de atrás.
    # Su prensa solo puede venir de un feed del registro comunitario.
    # Las claves son las que reparte `municipios_dinamicos`: el nombre a secas
    # va al primero de dos homónimos por familias registradas, así que
    # «Bolívar» es hoy el del Valle del Cauca y el del Cauca lleva su
    # departamento entre paréntesis.
    SIN_BUSQUEDA_ESPERADOS = {
        "Bolívar",            # Valle del Cauca
        "Bolívar (Cauca)",
        "Córdoba",            # Quindío
        "Risaralda",          # Caldas
        "Sucre",              # Cauca
    }

    def test_todo_municipio_del_rud_recibe_su_busqueda_de_prensa(self):
        why = skip_sin_datos("rud_daily")
        if why:
            self.skipTest(why)
        from municipios import catalogo_vigente
        sys.path.insert(0, str(ROOT / "ingest" / "sources"))
        from community_feeds import municipal_google_news_feeds, motivo_sin_busqueda
        catalogo = catalogo_vigente()
        con_busqueda = {f["municipio"] for f in municipal_google_news_feeds(catalogo)}
        # el catálogo vigente ES el del RUD más los curados: lo que interesa
        # aquí es que nadie se quede fuera de la pregunta
        sin = {mun: motivo_sin_busqueda(meta) for mun, meta in catalogo.items()
               if mun not in con_busqueda}
        nuevos = {m: v for m, v in sin.items()
                  if m not in self.SIN_BUSQUEDA_ESPERADOS}
        self.assertEqual(
            nuevos, {},
            f"Municipios del catálogo sin búsqueda propia de prensa: {nuevos}. "
            f"El sitio dirá de ellos «ni un titular» sin haber preguntado — "
            f"mirar el motivo y, si es legítimo, anotarlo en "
            f"SIN_BUSQUEDA_ESPERADOS con su porqué")
        # y al revés: si un homónimo deja de serlo (o desaparece del RUD), la
        # excepción sobra y hay que quitarla — una lista de excepciones que
        # nadie poda acaba tapando huecos de verdad
        sobran = self.SIN_BUSQUEDA_ESPERADOS - set(sin)
        self.assertEqual(sobran, set(),
                         f"excepciones que ya no hacen falta: {sobran}")

    def test_el_catalogo_de_las_busquedas_es_el_que_se_publica(self):
        """M2: `catalogo_vigente()` (de donde salen las búsquedas y los
        identificadores de sus feeds) y el catálogo que arma `publish.py` para
        las fichas tienen que dar las MISMAS claves.

        No es una formalidad: `municipios_dinamicos` reparte el nombre a secas
        al primero de dos homónimos —«Argelia» al Cauca y «Argelia (Valle del
        Cauca)» al otro—, así que el orden de las filas del RUD decide las
        claves, y de las claves cuelgan la URL de la ficha y el id del feed.
        Leerlas en otro orden publicaría un municipio con el nombre del otro.
        """
        why = skip_sin_datos("rud_daily")
        if why:
            self.skipTest(why)
        from municipios import catalogo_municipios, catalogo_vigente, _norm
        div_path = ROOT / "data" / "public" / "divipola_coords.json"
        divipola = (json.loads(div_path.read_text()).get("items")
                    if div_path.exists() else {})
        ult = q("SELECT MAX(snapshot_date) FROM rud_daily")[0][0]
        # espejo literal de la consulta de ingest/publish.py::run
        filas = q("SELECT departamento, municipio FROM rud_daily"
                  " WHERE snapshot_date=? ORDER BY familias DESC", ult)
        rud = {(_norm(dep), _norm(mun)): {"departamento": dep, "municipio": mun}
               for dep, mun in filas}
        self.assertEqual(
            set(catalogo_municipios(rud, divipola)), set(catalogo_vigente()),
            "el catálogo de las búsquedas y el de las fichas dan nombres "
            "distintos: los feeds municipales dejarían de casar con las fichas")
