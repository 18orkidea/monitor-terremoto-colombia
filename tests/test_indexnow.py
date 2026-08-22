"""Aviso a buscadores: qué se notifica, qué no, y qué pasa si el aviso falla.

El riesgo de este módulo no es que se caiga —eso se ve— sino que avise de más
o de menos sin que nadie lo note: avisar de las 213 URLs cada día equivale a no
avisar de ninguna, y perderse la ficha que sí cambió deja la cifra de un
municipio fuera del índice durante semanas.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "ingest"))

import indexnow  # noqa: E402


def item(nombre, depto="Chocó", **extra):
    return {"municipio": nombre, "departamento": depto, "rud_familias": 10, **extra}


class TestQueSeAvisa(unittest.TestCase):

    def test_la_primera_vez_se_avisa_de_todo(self):
        urls, estado = indexnow.urls_a_avisar([item("Quibdó"), item("Istmina")], {})
        self.assertIn("https://datosdelterremoto.org/municipio/quibdo/", urls)
        self.assertIn("https://datosdelterremoto.org/municipio/istmina/", urls)
        self.assertEqual(len(estado), 2)

    def test_sin_cambios_solo_se_avisa_de_las_paginas_diarias(self):
        """Lo que evita que el aviso se convierta en ruido: si la ficha no
        cambió, no se toca. Las cinco fijas sí, porque sus cifras cambian."""
        items = [item("Quibdó"), item("Istmina")]
        _, estado = indexnow.urls_a_avisar(items, {})
        urls, _ = indexnow.urls_a_avisar(items, estado)
        self.assertEqual(len(urls), len(indexnow.PAGINAS_FIJAS))
        self.assertNotIn("https://datosdelterremoto.org/municipio/quibdo/", urls)

    def test_se_avisa_de_la_ficha_cuyo_dato_cambio(self):
        items = [item("Quibdó"), item("Istmina")]
        _, estado = indexnow.urls_a_avisar(items, {})
        items[1]["rud_familias"] = 41  # Istmina registra nuevas familias
        urls, _ = indexnow.urls_a_avisar(items, estado)
        self.assertIn("https://datosdelterremoto.org/municipio/istmina/", urls)
        self.assertNotIn("https://datosdelterremoto.org/municipio/quibdo/", urls)

    def test_el_slug_de_la_url_es_el_de_la_ficha_publicada(self):
        """Si el slug no coincide, se avisa de una URL que da 404 y la ficha
        real nunca se indexa. San José del Palmar es el epicentro."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "deploy"))
        import render_html
        for nombre in ("San José del Palmar", "Quibdó", "Bogotá, D.C."):
            self.assertEqual(indexnow._slug(nombre), render_html.slug(nombre))

    def test_nunca_se_pasa_del_tope_del_protocolo(self):
        muchos = [item(f"Municipio {i}") for i in range(indexnow.MAX_URLS + 500)]
        urls, _ = indexnow.urls_a_avisar(muchos, {})
        self.assertLessEqual(len(urls), indexnow.MAX_URLS)


class TestClavePublicada(unittest.TestCase):

    def test_la_clave_del_repo_es_valida_y_coincide_con_su_fichero(self):
        """El buscador descarga ese fichero para comprobar que somos nosotros:
        si el nombre y el contenido no coinciden, el aviso se rechaza."""
        k = indexnow.clave()
        self.assertIsNotNone(k, "no hay clave publicada en deploy/root/")
        publicado = (indexnow.RAIZ_PUBLICADA / f"{k}.txt").read_text(encoding="utf-8")
        self.assertEqual(publicado.strip(), k)

    def test_un_fichero_de_texto_cualquiera_no_pasa_por_clave(self):
        """En deploy/root/ conviven llms.txt y robots.txt: no son claves."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "robots.txt").write_text("User-agent: *\n")
            with mock.patch.object(indexnow, "RAIZ_PUBLICADA", Path(d)):
                self.assertIsNone(indexnow.clave())


class TestDegradacionElegante(unittest.TestCase):

    def test_si_el_aviso_falla_el_estado_no_avanza(self):
        """R13: el buscador caído no rompe la corrida. Y sobre todo: mañana se
        vuelve a avisar de lo mismo, en vez de dar por notificado lo que no."""
        with tempfile.TemporaryDirectory() as d:
            estado = Path(d) / "estado.json"
            with mock.patch.object(indexnow, "ESTADO", estado), \
                 mock.patch.object(indexnow.common, "notificar", return_value=-1):
                r = indexnow.run()
            self.assertFalse(estado.exists())
            self.assertFalse(r["estado_guardado"])

    def test_el_aviso_aceptado_guarda_el_estado(self):
        with tempfile.TemporaryDirectory() as d:
            estado = Path(d) / "estado.json"
            with mock.patch.object(indexnow, "ESTADO", estado), \
                 mock.patch.object(indexnow.common, "notificar", return_value=200):
                r = indexnow.run()
            self.assertTrue(estado.exists())
            self.assertTrue(r["estado_guardado"])
            self.assertGreater(len(json.loads(estado.read_text())), 100)

    def test_el_dry_run_no_toca_la_red(self):
        with mock.patch.object(indexnow.common, "notificar") as n:
            indexnow.run(dry_run=True)
            n.assert_not_called()


if __name__ == "__main__":
    unittest.main()
