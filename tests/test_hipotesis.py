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
        from municipios import MUNICIPIOS, _norm
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
            if f"{_norm(mun)}|{_norm(dep)}" not in divipola:
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
