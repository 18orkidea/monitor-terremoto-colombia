"""El sitio se publica bajo un solo dominio, y solo uno.

La mudanza a dominio propio (22-ago-2026) dejó el host repartido en literales
por veintiséis ficheros: canonical, OG, sitemap, llms.txt, robots, el worker de
avisos y los feeds. Olvidar uno no rompe nada visible — la página se ve igual —
pero publica una URL canónica que apunta al dominio muerto, y eso sí lo leen
los buscadores y quien nos cita. De ahí que se compruebe por fichero.

Los documentos de `docs/` y los snapshots quedan fuera a propósito: son archivo
fechado, y reescribirlos falsearía lo que se dijo entonces.
"""
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "deploy"))

import render_descubrimiento as D  # noqa: E402

# dominios bajo los que el monitor se publicó antes y que ya no son canónicos
DOMINIOS_RETIRADOS = ("brechas.orkidea.eu",)

SUFIJOS = {".py", ".js", ".jsonc", ".json", ".html", ".txt", ".xml", ".csv",
           ".rss", ".sh", ".yml", ".yaml", ".md"}

# superficie viva: lo que se publica o lo que genera lo que se publica
RAICES = ("site", "deploy", "ingest", "workers", "feeds", ".github/workflows")
SUELTOS = ("README.md",)


def _ficheros():
    for r in RAICES:
        for f in (RAIZ / r).rglob("*"):
            if f.is_file() and f.suffix in SUFIJOS and "node_modules" not in f.parts:
                yield f
    for nombre in SUELTOS:
        yield RAIZ / nombre
    for f in (RAIZ / "data" / "public").glob("*"):
        if f.is_file() and f.suffix in SUFIJOS:
            yield f


class TestDominioCanonico(unittest.TestCase):

    def test_ningun_fichero_vivo_menciona_un_dominio_retirado(self):
        for f in _ficheros():
            texto = f.read_text(encoding="utf-8", errors="ignore")
            # este propio test nombra los dominios retirados: es su cometido
            if f.name == Path(__file__).name:
                continue
            for viejo in DOMINIOS_RETIRADOS:
                if viejo in texto:
                    linea = next(i for i, l in enumerate(texto.splitlines(), 1)
                                 if viejo in l)
                    # se falla a mano: assertNotIn volcaría el fichero entero
                    self.fail(f"{f.relative_to(RAIZ)}:{linea} sigue publicando "
                              f"{viejo}; esa URL apunta al dominio muerto")

    def test_el_canonical_de_cada_pagina_usa_el_dominio_del_sitemap(self):
        """Si el sitemap y el canonical discrepan, el buscador indexa uno y
        cita el otro. El sitemap manda: es la lista que se envía."""
        host = D.DOMINIO
        for f in (RAIZ / "site").glob("*.html"):
            for url in re.findall(r'<link rel="canonical" href="([^"]+)"', f.read_text(encoding="utf-8")):
                self.assertTrue(
                    url.startswith(host + "/"),
                    f"{f.name} declara canonical en {url}, fuera de {host}")


if __name__ == "__main__":
    unittest.main()
