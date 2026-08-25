"""R10 en el worker de balances: «Cali» no es «California».

El worker (workers/ai-view/src/index.js) atribuía municipios con includes() a
secas hasta el 17-ago-2026, la única superficie del monitor que se quedó sin el
guardián. Estos tests ejecutan SU código con node —no una réplica en Python—
porque testear copias es testear nada: es la misma lección que en la selección
diaria de balances (tests/test_frontend.py).

El worker es ESM y su package.json no declara "type": "module", así que se copia
a un .mjs temporal para que node lo importe. Se copia, no se reescribe: el
contenido ejecutado es byte a byte el que se despliega.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
NODE = shutil.which("node")
WORKER = ROOT / "workers" / "ai-view" / "src" / "index.js"

# R11: en local se puede saltar (node es opcional para el pipeline Python), pero
# en CI la ausencia de node dejaría los guardianes de JavaScript apagados en
# silencio — justo lo que estas reglas existen para evitar.
if not NODE and os.environ.get("CI"):
    raise RuntimeError(
        "node no está disponible en el runner: las reglas del monitor que viven "
        "en JavaScript no se pueden verificar. Instalar node o quitar el paso.")



def correr_worker(expresion: str):
    """Importa el worker en node y evalúa una expresión sobre sus exports."""
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "worker.mjs"
        copia.write_bytes(WORKER.read_bytes())
        script = (
            f"const W = await import({json.dumps(copia.as_uri())});"
            "const norm = (s) => String(s || '').normalize('NFD')"
            "  .replace(/[\\u0300-\\u036f]/g, '').toLowerCase();"
            f"console.log(JSON.stringify({expresion}));"
        )
        r = subprocess.run([NODE, "--input-type=module", "-"], input=script,
                           capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló: {r.stderr[:600]}")
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "node no disponible (el CI de PR sí lo tiene)")
class TestR10EnElWorker(unittest.TestCase):

    def test_cali_no_es_california(self):
        self.assertFalse(correr_worker(
            "W.mentionsPlace(norm('Earthquake felt in California'), 'Cali')"))
        self.assertTrue(correr_worker(
            "W.mentionsPlace(norm('Colapso en Cali tras el sismo'), 'Cali')"))

    def test_no_atribuye_por_nombre_de_archivo_ni_por_url(self):
        """Caso real del balance del 16-ago: «Cali» solo aparecía dentro de
        «terremoto-cali_51341108.jpg», la URL de una imagen. Atribuir un
        municipio por eso deja la auditoría sin nada que enseñar.

        Ojo con el falso alivio: el límite de palabra rechaza esa variante solo
        porque «_» es carácter de palabra. Con guion o barra («terremoto-cali.jpg»,
        «/noticias/cali/») el topónimo SÍ queda suelto, y de ahí sinEnlaces()."""
        def municipios(texto):
            return correr_worker(
                f"W.structureOfficialText({json.dumps(texto)},"
                " { title: '', summary: '', source: { department: null } }).municipios")
        for texto in ("terremoto-cali_51341108_20260812133441.jpg",
                      "https://ejemplo.com/noticias/cali/sismo",
                      "![imagen](https://x.co/cali-2026.webp)",
                      "ver /media/900x601/terremoto-cali_51.jpg aquí",
                      "![foto](https://cdn.co/2026/08/quibdo-danos.mp4)"):
            with self.subTest(texto=texto):
                self.assertEqual(municipios(texto), [],
                                 "un enlace no es una mención en la prosa")
        self.assertEqual(municipios("Colapso en Cali tras el sismo"), ["Cali"])

    def test_frontera_del_nombre_de_archivo_suelto(self):
        """Frontera asumida, no descuido: un nombre de archivo con extensión
        SUELTO en la prosa (sin URL ni ruta) sí atribuye. No hay forma limpia de
        distinguir «foto terremoto-cali.jpg» —ruido— de «el EDAN de Quibdó.pdf»
        —una referencia legítima al documento de un municipio—, y en el markdown
        de Firecrawl las imágenes llegan siempre como ![alt](url), que sí se
        descarta. Se prefiere conservar la referencia al documento.

        Si algún día aparecen falsos positivos reales por esta vía, se calibra
        con el corpus, como se hizo con los homónimos de departamento."""
        def municipios(texto):
            return correr_worker(
                f"W.structureOfficialText({json.dumps(texto)},"
                " { title: '', summary: '', source: { department: null } }).municipios")
        self.assertEqual(municipios("foto terremoto-cali.jpg"), ["Cali"])
        self.assertEqual(municipios("El EDAN de Quibdó.pdf recoge 300 familias."),
                         ["Quibdó"])

    def test_choco_no_es_chocolate(self):
        """«chocó» estaba en EVENT_TERMS, que se buscan por contención para
        capturar «sismos»/«temblores» — así que una fábrica de chocolate contaba
        como evidencia del terremoto, y hasEventTerm gatea el campo
        relacionado_evento que se publica."""
        self.assertFalse(correr_worker(
            "W.hasEventTerm('Feria del chocolate en Colombia')"))
        self.assertTrue(correr_worker("W.hasEventTerm('Emergencia en Chocó')"))
        # los términos temáticos siguen capturando plurales, a propósito
        self.assertTrue(correr_worker("W.hasEventTerm('Los sismos continúan')"))

    def test_las_cifras_no_salen_de_las_urls(self):
        """Las URLs no solo atribuían municipios: también ofrecían números.
        «mapa-900x601.jpg» daba «900 municipios afectados», y esa cifra sí se
        pinta (site/balances.js la enfrenta al RUD)."""
        def cifras(texto):
            return correr_worker(
                f"W.structureOfficialText({json.dumps(texto)},"
                " { title: '', summary: '', source: { department: null } }).cifras")
        sucio = cifras("Municipios afectados ![f](https://x.co/mapa-900x601.jpg) según la UNGRD")
        self.assertIsNone(sucio["municipios_afectados"],
                          "una dimensión de imagen no es una cifra de daño")
        # una fecha en la URL y un id de artículo tampoco son cifras de daño
        self.assertIsNone(
            cifras("Reporte de familias afectadas en https://ej.com/2026/08/14/nota")
            ["familias_afectadas"])
        self.assertIsNone(
            cifras("Balance de personas afectadas: https://ej.com/n/51341108")
            ["personas_afectadas"])
        limpio = cifras("La UNGRD reporta 75 municipios afectados")
        self.assertEqual(limpio["municipios_afectados"], 75,
                         "la limpieza no puede comerse las cifras de la prosa")

    def test_sinenlaces_no_se_come_la_prosa(self):
        """El insumo es markdown de Firecrawl, así que el texto ENLAZADO es prosa:
        «[UNGRD confirma 12 fallecidos en Cali](url)» es justo donde aparece el
        municipio. Mi primera versión borraba el enlace entero y cambiaba un
        falso positivo por un falso negativo silencioso."""
        def municipios(texto):
            return correr_worker(
                f"W.structureOfficialText({json.dumps(texto)},"
                " { title: '', summary: '', source: { department: null } }).municipios")
        casos = [
            ("## [UNGRD confirma 12 fallecidos en Cali](https://ungrd.gov.co/x)", ["Cali"]),
            ("La [Alcaldía de Quibdó](https://quibdo.gov.co) reportó 300 familias.", ["Quibdó"]),
            # nombrar un documento oficial es nombrar el municipio
            ("El EDAN de Quibdó.pdf recoge 300 familias.", ["Quibdó"]),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto[:40]):
                self.assertEqual(municipios(texto), esperado)
        # y las cifras de la prosa enlazada tampoco se pierden
        cifras = correr_worker(
            "W.structureOfficialText('[La UNGRD](https://u.co) reporta 294 fallecidos',"
            " { title: '', summary: '', source: { department: null } }).cifras")
        self.assertEqual(cifras["fallecidos"], 294)

    def test_los_portones_de_relevancia_no_entran_por_una_url(self):
        """hasEventTerm y hasImpactedPlace deciden si un documento cuenta como
        evidencia del evento: con la URL de una imagen como único anclaje
        colombiano, un artículo de otro país entraba al feed."""
        self.assertFalse(correr_worker(
            "W.hasImpactedPlace('Terremoto en Ecuador. foto:"
            " https://x.co/noticias/cali/portada.jpg')"))
        self.assertFalse(correr_worker(
            "W.hasEventTerm('Feria de dulces https://x.co/choco/2026')"))

    def test_el_item_publicado_sella_su_criterio(self):
        """Sin el sello, los feeds archivados mezclan la atribución nueva con la
        de los ítems que el KV reusa tal cual, sin forma de distinguirlas."""
        out = correr_worker(
            "W.structureOfficialText('Balance en Cali',"
            " { title: '', summary: '', source: { department: null } })")
        self.assertEqual(out["atribucion_lugares"], "limite_palabra_sin_enlaces")
        self.assertEqual(out["cifras_desde"], "texto_sin_enlaces_v2")
        self.assertEqual(out["extraccion_version"], 2,
                         "el sello de extracción distingue los ítems anteriores "
                         "a las reglas de 21-ago-2026, que perdían las víctimas "
                         "en femenino y confundían personas con fallecidos")

    def test_la_cabecera_del_feed_sella_el_mismo_criterio_que_cada_item(self):
        """La cabecera no puede anunciar la versión anterior mientras los ítems
        ya salen con la extracción v2: el daily archivaría una frontera falsa."""
        out = correr_worker(
            "({version: W.WORKER_VERSION, criterios: W.EXTRACTION_CRITERIA, "
            "item: W.structureOfficialText('Balance en Cali', "
            "{ title: '', summary: '', source: { department: null } })})")
        self.assertEqual(out["version"], "2026-08-21-balance-v2")
        self.assertEqual(out["criterios"]["lugares"],
                         out["item"]["atribucion_lugares"])
        self.assertEqual(out["criterios"]["cifras"],
                         out["item"]["cifras_desde"])

    def test_acentos_y_derivadas(self):
        self.assertTrue(correr_worker(
            "W.mentionsPlace(norm('Daños graves en Quibdó'), 'Quibdó')"))
        self.assertFalse(correr_worker(
            "W.mentionsPlace(norm('el istmo de Panamá'), 'Istmina')"))
        self.assertFalse(correr_worker(
            "W.mentionsPlace(norm('la calidad del aire empeora'), 'Cali')"))

    def test_el_filtro_de_contexto_no_cuela_california(self):
        """hasImpactedPlace alimenta hasColombiaContext, que decide si un
        documento cuenta como evidencia del evento: un falso positivo aquí hacía
        pasar un artículo sobre California como balance colombiano."""
        self.assertFalse(correr_worker(
            "W.hasImpactedPlace('Earthquake damage reported in California, USA')"))
        self.assertTrue(correr_worker("W.hasImpactedPlace('Daños en Cali')"))
        self.assertTrue(correr_worker(
            "W.hasImpactedPlace('Emergencia en el Valle del Cauca')"))

    def test_la_atribucion_publicada_respeta_el_limite(self):
        """structureOfficialText es lo que acaba en oficiales.json: se comprueba
        la salida real, no solo el helper."""
        out = correr_worker(
            "W.structureOfficialText('Sismo en California; foto terremoto-cali_51.jpg',"
            " { title: '', summary: '', source: { department: null } })")
        self.assertEqual(out["municipios"], [],
                         "ni «California» ni el nombre de archivo son Cali")
        out2 = correr_worker(
            "W.structureOfficialText('Balance UNGRD: daños en Cali y Pereira',"
            " { title: '', summary: '', source: { department: null } })")
        self.assertEqual(out2["municipios"], ["Cali", "Pereira"])
        self.assertIn("Valle del Cauca", out2["departamentos"])


@unittest.skipUnless(NODE, "node no disponible")
class TestParidadMunicipiosWorker(unittest.TestCase):
    """El worker mantiene su propia lista de municipios porque corre en
    Cloudflare, aislado del pipeline Python: no puede importar municipios.py.
    La duplicación es deliberada, pero silenciosa si nadie la vigila — mismo
    patrón que TestParidadLiveblog."""

    def test_los_municipios_del_worker_existen_en_el_catalogo(self):
        from municipios import MUNICIPIOS as CATALOGO, _norm
        del_worker = correr_worker("W.MUNICIPIOS")
        # claves y alias: el worker lista «Dos Quebradas», que en el catálogo es
        # un topónimo de Dosquebradas y no una entrada propia
        curados = {}
        for m, meta in CATALOGO.items():
            for nombre in [m, *meta.get("toponimos", [])]:
                curados[_norm(nombre)] = meta["departamento"]
        for nombre, depto in del_worker:
            with self.subTest(municipio=nombre):
                self.assertIn(_norm(nombre), curados,
                              f"{nombre} está en el worker pero no en "
                              f"ingest/municipios.py: una de las dos listas se movió")
                self.assertEqual(_norm(curados[_norm(nombre)]), _norm(depto),
                                 f"{nombre} tiene otro departamento en el worker")

    def test_ningun_municipio_del_worker_exige_departamento(self):
        """La decisión de no replicar el segundo nivel en el worker se sostiene
        porque hoy NINGUNO de sus 25 municipios lo exige en el pipeline. El día
        que se marque Armenia o Sevilla al calibrar (anunciado en
        docs/LIMITACIONES.md), las dos superficies divergirían en silencio: este
        test obliga a decidirlo entonces, en vez de descubrirlo después."""
        from municipios import MUNICIPIOS as CATALOGO, _norm
        exigen = {_norm(m) for m, meta in CATALOGO.items()
                  if meta.get("requiere_depto")}
        del_worker = {_norm(n) for n, _ in correr_worker("W.MUNICIPIOS")}
        coinciden = exigen & del_worker
        self.assertEqual(coinciden, set(),
                         f"el pipeline exige departamento para {coinciden} y el "
                         f"worker no: replicarlo allí o documentar la divergencia")

    def test_el_worker_reconoce_los_alias_del_catalogo(self):
        """El pipeline lista «dos quebradas» como topónimo de Dosquebradas; con
        límite de palabra, esa variante de dos palabras NO casa dentro de
        «Dosquebradas». Un documento que la use lo atribuía el pipeline y no el
        worker: dos atribuciones distintas del mismo texto, sin registro."""
        from municipios import MUNICIPIOS as CATALOGO, _norm
        del_worker = {_norm(n) for n, _ in correr_worker("W.MUNICIPIOS")}
        faltan = []
        for mun, meta in CATALOGO.items():
            if _norm(mun) not in del_worker:
                continue
            for alias in meta.get("toponimos", []):
                reconocido = correr_worker(
                    f"W.MUNICIPIOS.some(([n]) => W.mentionsPlace("
                    f"{json.dumps(_norm(alias))}, n))")
                if not reconocido:
                    faltan.append(f"{mun} → «{alias}»")
        self.assertEqual(faltan, [],
                         f"alias que el pipeline atribuye y el worker no: {faltan}")

    def test_el_worker_no_incluye_homonimos_de_departamento(self):
        """Risaralda (Caldas) y Córdoba (Quindío) no reciben prensa por texto en
        el pipeline (docs/LIMITACIONES.md). Si alguien los añadiera al worker,
        volverían por esa puerta con la atribución que el resto rechaza."""
        from municipios import MUNICIPIOS as CATALOGO, _norm
        homonimos = {_norm(m) for m, meta in CATALOGO.items()
                     if meta.get("homonimo_de_departamento")}
        del_worker = {_norm(n) for n, _ in correr_worker("W.MUNICIPIOS")}
        self.assertEqual(homonimos & del_worker, set(),
                         "el worker atribuiría un homónimo de departamento")


if __name__ == "__main__":
    unittest.main(verbosity=2)
