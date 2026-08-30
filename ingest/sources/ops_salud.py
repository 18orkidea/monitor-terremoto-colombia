"""OPS/OMS: los Informes de Situación (sitrep) sobre establecimientos de salud.

Qué aporta que no tenga nadie más: la OPS es el ÚNICO organismo que compila,
sitrep a sitrep, lo que dicen TRES autores distintos sobre el mismo universo
—establecimientos de salud dañados— sin fundirlos en una sola cifra: UNGRD
(«reportados»), el Ministerio de Salud vía sus Centros Reguladores de
Urgencias y Emergencias («verificados») y el propio Ministerio («priorizados»
para atención). Las tres crecen a ritmos distintos y NUNCA se suman entre sí:
son tres preguntas distintas sobre el mismo universo, no tres medidas de lo
mismo (R3 aplicado a la propia arquitectura de la fuente, no solo a sus «NA»).

## No hay API: cada sitrep es un PDF, y cada uno trae SU PROPIA tabla

No existe un endpoint. La OPS publica un PDF por sitrep, sin patrón estable de
nombre de fichero (`sitrep1-terremoto-colombia-agosto-20260.pdf` frente a
`sitrep5colombiasismo18082026.pdf`) — el enlace se descubre SIEMPRE desde el
`<div class="download-button"><a href="*.pdf">Descargar</a></div>` de la
página del documento, nunca adivinando el nombre.

Y la tabla que trae cada sitrep es distinta, no una serie con columnas fijas:

- **Sitreps 1-3**: `Tabla 1`, detalle por INSTITUCIÓN — nombre, municipio,
  nivel de complejidad, observación. 24 instituciones el 10-ago (13:30), 31
  el mismo día (19:30) y las mismas 31 el 11-ago: la lista se congeló ahí.
- **Sitrep 4** (13-ago): `Tabla 2`, matriz departamento × nivel de complejidad
  (1-4). Un solo autor (MSPS + secretarías), total 59. La cifra de UNGRD (109)
  solo aparece en prosa, repitiendo el valor del sitrep 3 sin aclarar si se
  actualizó.
- **Sitrep 5** (18-ago): `Tabla 2`, departamento × DOS cifras de DOS autores
  —verificadas vía CRUE (192) y priorizadas (50), ambas del MSPS—. La cifra de
  UNGRD (303) vuelve a ser SOLO prosa, sin desglose departamental en ningún
  lugar del documento.

**El detalle por institución no reapareció.** 24 nombres con municipio el
10-ago; 192 establecimientos «verificados» sin un solo nombre el 18-ago. No es
un fallo de esta transcripción: es un hecho sobre cómo publica la fuente
(`docs/LIMITACIONES.md`).

## Por qué DOS tablas y formato LARGO, no columnas fijas

`ops_salud_ips` (detalle) y `ops_salud_cifras` (agregados) son cosas de
granularidad distinta y fusionarlas habría fabricado NULL estructurales.
Dentro de `ops_salud_cifras`, cada sitrep trae una tabla con columnas
distintas — la respuesta es el formato LARGO: una fila, una cifra, un
concepto, un autor. Un sitrep 6 con otra forma no muta el esquema, solo añade
filas. «Una cifra, un concepto» llevado a su extremo: nunca se funden bajo el
mismo `concepto` dos series de autores distintos aunque cuenten algo parecido
(`ips_reportadas_ungrd` y `ips_reportadas_monitoreo_ops` son conceptos
DISTINTOS aunque las dos midan "establecimientos con daño reportado", porque
las cuenta gente distinta con método distinto).

## Trazabilidad: el PDF es un ACTIVO, la transcripción está atada a su sha256

Los PDF de la serie no cambian una vez publicados: son contenido que no
cambia (`common.activo_archivado`), se traen UNA vez y no se vuelven a
descargar en cada corrida. La tabla de cada PDF se transcribió A MANO a
`data/documentos/ops_salud/sitrep_N.json`, con el sha256 del PDF de origen
dentro del propio JSON — `tests/test_unit.py::TestOpsSalud` comprueba que ese
sha256 es el que de verdad quedó en `sources_log` tras archivar el PDF: si
alguien edita el JSON sin volver a archivar el PDF correcto, o el PDF
cambiara de contenido, el test lo canta en vez de publicar una transcripción
que ya no corresponde a su fuente.

## Detector de serie nueva

El hub de Naciones Unidas en Colombia (`HUB_URL`) enlaza los sitrep publicados
y sirve de índice barato: si aparece un número de sitrep mayor que el último
transcrito, `sitreps_nuevos()` lo dice y `alerts.py` avisa («sitrep OPS nuevo
sin transcribir», R11) en vez de quedarse muda. Nota de infraestructura: la
URL numérica sola (`/es/320793`) da 404 — el hub exige el slug completo
(`test_supuestos_api.py` lo vigila).

## Plan de sucesión

Si la OPS deja de publicar la serie: sobreviven los 5 PDF archivados en el
repo (cada uno < 1.1 MB, caben en git igual que los de SERTIT) con su sha256
en `sources_log`, y la tabla `ops_salud_cifras`/`ops_salud_ips` sale de ahí,
no de la red. El detector de silencio (R15) avisa a partir de 15 días sin un
sitrep nuevo — más laxo que el general (48 h) porque la propia serie llevó
hasta 7 días naturales entre sitreps (13-ago → 19-ago) sin que eso significara
que la OPS dejó de cubrir el evento.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from common import DATA, fetch, registrar_entrega, to_num, utcnow

DOCUMENTOS = DATA / "documentos" / "ops_salud"

BASE = "https://www.paho.org"

# Metadatos de cada sitrep: n -> página del documento. El PDF NO se declara
# aquí — se descubre en pdf_link_de_pagina() a partir de esta página, porque
# el nombre del fichero no sigue un patrón estable entre sitreps.
PAGINAS = {
    1: f"{BASE}/es/documentos/informe-situacion-1-colombia-terremoto-agosto-2026-10-agosto-2026",
    2: f"{BASE}/es/documentos/informe-situacion-2-colombia-terremoto-agosto-2026-10-agosto-2026",
    3: f"{BASE}/es/documentos/informe-situacion-3-colombia-terremoto-agosto-2026-11-agosto-2026",
    4: f"{BASE}/es/documentos/informe-situacion-4-colombia-terremoto-agosto-2026-13-agosto-2026",
    5: f"{BASE}/es/documentos/informe-situacion-5-colombia-terremoto-agosto-2026-19-agosto-2026",
}

# El hub de Naciones Unidas en Colombia enlaza los sitrep de la OPS y sirve de
# índice para el detector de serie nueva. El slug completo es obligatorio: la
# URL numérica sola (/es/320793) responde 404 (comprobado 30-ago-2026).
HUB_URL = ("https://colombia.un.org/es/320793-informaci%C3%B3n-y-"
          "actualizaciones-sobre-el-terremoto-en-colombia")

# Los conceptos que expone esta fuente, cada uno con SU autor — nunca se
# funden dos autores bajo el mismo concepto (ver docstring del módulo). El
# rotulado público final (cómo se llaman de cara al lector) queda pendiente
# de decisión editorial; este mapa documenta con qué concepto se compone
# cada pieza del titular fijo
# «reportadas (UNGRD) · verificadas (MinSalud) · priorizadas (MinSalud)»
# (docs/DECISIONES.md, 30-ago-2026):
CONCEPTO_REPORTADAS = "ips_reportadas_ungrd"          # → "reportadas (UNGRD)"
CONCEPTO_VERIFICADAS = "ips_verificadas_crue"         # → "verificadas (MinSalud)"
CONCEPTO_PRIORIZADAS = "ips_priorizadas"              # → "priorizadas (MinSalud)"
# Conceptos históricos/superados, fuera del titular fijo pero conservados para
# la serie temporal completa: la cifra conjunta OPS+secretarías de los
# sitreps 1-2 (antes de que UNGRD publicara la suya) y la matriz por nivel de
# complejidad del sitrep 4 (MSPS+secretarías, sin equivalente en CRUE).
CONCEPTO_MONITOREO_OPS = "ips_reportadas_monitoreo_ops"
CONCEPTO_IDENTIFICADAS_MSPS = "ips_identificadas_msps"

# Cambiar a True el día que la OPS anuncie el cierre de la serie (con la
# fecha y el porqué en un comentario aquí mismo, y en docs/DECISIONES.md):
# a partir de entonces `alerts.py` deja de avisar por silencio prolongado,
# porque dejar de publicar sitrep ya no sería una anomalía sino el final
# esperado de la serie.
SERIE_CERRADA = False


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def _slug(s: str) -> str:
    """Espejo de `deploy/render_html.py::slug` — dos superficies, mismo
    algoritmo (R8/R10): las fichas municipales enlazan por este slug y no
    puede haber dos formas de calcularlo."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "-".join(x for x in "".join(c if c.isalnum() else " " for c in s).split())


def pdf_link_de_pagina(body: bytes) -> str | None:
    """El enlace de descarga de la página de un sitrep.

    Se lee el `<div class="download-button">`, NO el nombre del fichero: entre
    los 5 sitrep conocidos hay tres convenciones de nombre distintas
    (`sitrep1-terremoto-colombia-agosto-20260.pdf`, `sitrep-2-colombiasismo.pdf`,
    `sitrep5colombiasismo18082026.pdf`), así que adivinar el patrón habría roto
    con el propio sitrep 2. Confirmado en las 5 páginas el 30-ago-2026.
    """
    m = re.search(
        rb'<div class="download-button">\s*<a href="([^"]+\.pdf)"', body)
    if not m:
        return None
    href = m.group(1).decode("utf-8", "replace")
    return href if href.startswith("http") else f"{BASE}{href}"


def sitreps_en_hub(body: bytes) -> list[int]:
    """Los números de sitrep que el hub de Naciones Unidas enlaza hoy.

    Es el índice para el detector de serie nueva: si aparece un número mayor
    que el último transcrito, hay un sitrep sin procesar. No exige que el
    número aparezca en orden ni sin huecos — el hub es de la ONU, no de la
    OPS, y puede tardar en enlazar uno nuevo.
    """
    return sorted({int(n) for n in re.findall(
        rb"informe-situaci[o\xc3\xb3]n-(\d+)-colombia-terremoto-agosto-2026",
        body)})


def _transcripciones() -> dict[int, dict]:
    """Los JSON de transcripción disponibles en el repo, por número de sitrep."""
    out = {}
    if not DOCUMENTOS.exists():
        return out
    for p in sorted(DOCUMENTOS.glob("sitrep_*.json")):
        try:
            datos = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        n = datos.get("sitrep_n")
        if isinstance(n, int):
            out[n] = datos
    return out


def sitreps_nuevos(conn=None) -> list[int]:
    """Sitrep publicados en el hub y sin transcribir todavía.

    R13: si el hub no responde, la lista vuelve vacía — no hay nada que
    avisar sin evidencia, y el detector de silencio (R15) ya cubre el caso de
    que la fuente calle.
    """
    st, body = fetch(HUB_URL, note="ops_salud hub ONU", conn=conn,
                     snapshot_name="ops_salud_hub_onu.html")
    if st != 200 or not body:
        return []
    conocidos = set(_transcripciones())
    return sorted(n for n in sitreps_en_hub(body) if n not in conocidos)


def dias_desde_ultimo_sitrep(hoy: str | None = None) -> int | None:
    """Días naturales desde el `fecha_publicacion` del último sitrep
    transcrito, o None si aún no hay ninguno. Sale de los JSON del repo, no de
    la red: sobrevive a que la OPS o el hub estén caídos (R13) — es la base
    del aviso de silencio prolongado (R15) en `alerts.py`.
    """
    from common import today
    fechas = [m.get("fecha_publicacion") for m in _transcripciones().values()
              if m.get("fecha_publicacion")]
    if not fechas:
        return None
    from datetime import date
    ultimo = max(fechas)
    hoy = hoy or today()
    return (date.fromisoformat(hoy) - date.fromisoformat(ultimo)).days


def resolver_municipio(departamento_literal: str, municipio_literal: str,
                       catalogo: dict) -> tuple[str | None, str | None]:
    """(slug, nombre_canónico) del municipio, o (None, None) si no hay match
    seguro. Nunca adivina (R10): exige que el departamento normalizado
    coincida además del nombre, para no confundir homónimos («Riosucio
    (Caldas)» vs «Riosucio (Chocó)» — las claves de MUNICIPIOS ya los
    distinguen así). Un municipio que el catálogo no cubre (p. ej. Popayán,
    fuera del área que este monitor observa) devuelve (None, None) — el
    literal de la fuente se conserva igual en `ops_salud_ips`.

    Limitación conocida (no introducida aquí, heredada del sitio): el NOMBRE
    CANÓNICO sí distingue los homónimos, pero el SLUG no — `_slug()` quita el
    paréntesis del departamento antes de calcularlo, igual que
    `deploy/render_html.py::slug`, así que «Riosucio (Caldas)» y «Riosucio
    (Chocó)» comparten slug «riosucio». Ninguno de los 5 sitrep transcritos
    hasta hoy (30-ago-2026) menciona un municipio homónimo, así que
    `instituciones_por_municipio()` no ha fusionado todavía dos pueblos
    distintos bajo una misma clave — pero lo haría el día que uno aparezca. No
    se resuelve en este módulo porque la solución (si hace falta) es del
    sitio, no de la ingesta: cambiar `slug()` en dos superficies (R8) el día
    que un homónimo real lo requiera.
    """
    dep_n = _norm(departamento_literal or "")
    mun_n = _norm(municipio_literal or "")
    if not mun_n:
        return None, None
    candidatos = []
    for clave, meta in catalogo.items():
        base = re.sub(r"\s*\([^)]*\)\s*$", "", clave)
        if _norm(base) == mun_n and _norm(meta.get("departamento") or "") == dep_n:
            candidatos.append(clave)
    if len(candidatos) != 1:
        return None, None
    clave = candidatos[0]
    return _slug(re.sub(r"\s*\([^)]*\)\s*$", "", clave)), clave


def _archivar_pdf(conn, n: int, meta: dict) -> dict:
    """Descarga el PDF de un sitrep (o reconoce que ya lo tiene) y comprueba
    su sha256 contra el declarado en la transcripción.

    Se llama a `fetch()` cada corrida, como cualquier otra fuente — no hay
    bypass propio del principio de archivo aquí: `fetch()` YA implementa las
    dos mitades («nada que no cambia se archiva dos veces» vía sus peticiones
    condicionales y su dedupe por sha256; una fila real en `sources_log` cada
    vez, nunca `http_status` NULL con un sha detrás). Inventar un segundo
    camino que se salte la petición HTTP habría producido una fila con rastro
    de descarga sin haber descargado nada —justo lo que
    `test_hipotesis.py::test_una_derivacion_no_finge_ser_una_peticion`
    prohíbe—, y el PDF pesa menos de 1,1 MB: preguntar a diario no cuesta
    nada que el mecanismo no absorba ya.
    """
    destino = DOCUMENTOS / f"sitrep{n}.pdf"
    esperado = meta.get("pdf_sha256")
    st, body = fetch(meta["pdf_url"], note=f"ops_salud sitrep {n} pdf",
                     conn=conn, save_to=destino)
    if st != 200 or not body:
        return {"error": f"PDF del sitrep {n} no responde (HTTP {st})"}
    import hashlib
    sha = hashlib.sha256(body).hexdigest()
    if esperado and sha != esperado:
        # La fuente cambió el contenido de un PDF ya publicado — no debería
        # pasar nunca (R11: si pasa, es un hallazgo, no un bug de este módulo).
        return {"error": f"sitrep {n}: el PDF archivado (sha256 {sha[:12]}…) "
                         f"ya NO coincide con el de la transcripción "
                         f"({esperado[:12]}…) — revisar si la OPS republicó "
                         f"el documento"}
    return {"sha256": sha}


def _registrar_transcripcion(conn, ruta: Path, n: int, pdf_sha256: str) -> None:
    """Anota en `sources_log` el propio fichero de transcripción, una vez.

    No llega por HTTP, así que no puede pasar por `fetch()` — pero es un
    cuerpo real de `data/documentos/`, verificable por su sha256, y ese es
    exactamente el contrato de `common.registrar_entrega()` (mismo criterio
    que usa `sertit.py` para sus vectores): un `http_status` NULL con un sha
    detrás solo se admite si la fila se anota así, no por texto libre —
    `test_hipotesis.py::test_una_derivacion_no_finge_ser_una_peticion` lo
    exige. Se registra solo la primera vez (por sha256 + ruta) para no
    repetir la misma fila cada corrida.
    """
    import hashlib
    spath_check = str(ruta.relative_to(DATA.parent))
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    ya = conn.execute(
        "SELECT 1 FROM sources_log WHERE sha256=? AND snapshot_path=?",
        (sha, spath_check)).fetchone()
    if ya:
        return
    registrar_entrega(
        conn, url=PAGINAS[n], ruta=ruta,
        note=f"transcripción a mano de la tabla del sitrep {n} de la OPS, "
             f"leída del PDF ya archivado (sha256 {pdf_sha256[:12]}…)")


def _upsert_cifra(conn, n: int, idx: int, fila: dict, fecha_corte_default) -> None:
    conn.execute(
        "INSERT INTO ops_salud_cifras (sitrep_n, idx, fecha_corte, ambito,"
        " concepto, valor, valor_raw, nivel_complejidad, autor, fuente_citada,"
        " nota, first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,"
        "  COALESCE((SELECT first_seen FROM ops_salud_cifras"
        "            WHERE sitrep_n=? AND idx=?), ?))"
        " ON CONFLICT(sitrep_n, idx) DO UPDATE SET"
        "  fecha_corte=excluded.fecha_corte, ambito=excluded.ambito,"
        "  concepto=excluded.concepto, valor=excluded.valor,"
        "  valor_raw=excluded.valor_raw,"
        "  nivel_complejidad=excluded.nivel_complejidad, autor=excluded.autor,"
        "  fuente_citada=excluded.fuente_citada, nota=excluded.nota",
        (n, idx, fila.get("fecha_corte") or fecha_corte_default, fila["ambito"],
         fila["concepto"], to_num(fila.get("valor")), fila.get("valor_raw"),
         fila.get("nivel_complejidad"), fila["autor"], fila.get("fuente_citada"),
         fila.get("nota"), n, idx, utcnow()))


def _upsert_ips(conn, n: int, idx: int, fila: dict, fecha_corte: str,
                catalogo: dict) -> str | None:
    slug, canonico = resolver_municipio(
        fila.get("departamento_literal"), fila.get("municipio_literal"), catalogo)
    conn.execute(
        "INSERT INTO ops_salud_ips (sitrep_n, idx, fecha_corte,"
        " departamento_literal, municipio_literal, municipio_slug, nombre_ips,"
        " nivel_complejidad, observacion, first_seen) VALUES (?,?,?,?,?,?,?,?,?,"
        "  COALESCE((SELECT first_seen FROM ops_salud_ips"
        "            WHERE sitrep_n=? AND idx=?), ?))"
        " ON CONFLICT(sitrep_n, idx) DO UPDATE SET"
        "  fecha_corte=excluded.fecha_corte,"
        "  departamento_literal=excluded.departamento_literal,"
        "  municipio_literal=excluded.municipio_literal,"
        "  municipio_slug=excluded.municipio_slug,"
        "  nombre_ips=excluded.nombre_ips,"
        "  nivel_complejidad=excluded.nivel_complejidad,"
        "  observacion=excluded.observacion",
        (n, idx, fecha_corte, fila.get("departamento_literal"),
         fila.get("municipio_literal"), slug, fila.get("nombre_ips"),
         fila.get("nivel_complejidad"), fila.get("observacion"), n, idx, utcnow()))
    return slug


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    from municipios import catalogo_vigente
    catalogo = catalogo_vigente()

    transcripciones = _transcripciones()
    out = {"sitreps_cargados": 0, "cifras": 0, "instituciones": 0,
          "instituciones_resueltas": 0, "errores": [], "pdfs": {}}

    for n, meta in sorted(transcripciones.items()):
        # 1) la página (snapshot diario barato: es HTML, pesa poco y confirma
        # que el selector de descarga sigue vivo si algún día hace falta
        # reprocesar)
        st, _ = fetch(meta["pagina_url"], note=f"ops_salud sitrep {n} pagina",
                      conn=conn, snapshot_name=f"ops_salud_pagina_{n}.html")
        if st != 200:
            out["errores"].append(f"sitrep {n}: página HTTP {st}")

        # 2) el PDF, como activo (se archiva una vez)
        r = _archivar_pdf(conn, n, meta)
        out["pdfs"][n] = r
        if "error" in r:
            out["errores"].append(r["error"])
            continue    # sin PDF verificado no se cargan sus cifras (R11)

        # 2b) la propia transcripción: no llega por HTTP ni es una entrega
        # fuera de banda (la escribió el propio monitor, leyendo el PDF), pero
        # es un cuerpo de `data/documentos/` y tiene que constar igual que su
        # PDF de origen (R4) — sin esta fila, `test_hipotesis.py::
        # test_ningun_cuerpo_entregado_vive_sin_su_fila` no podría distinguir
        # un JSON huérfano de uno trazable, y un lector futuro no sabría
        # cuándo se transcribió ni contra qué sha256 de PDF.
        _registrar_transcripcion(conn, DOCUMENTOS / f"sitrep_{n}.json", n, r["sha256"])

        # 3) las cifras transcritas, en formato largo
        for idx, fila in enumerate(meta.get("cifras") or []):
            _upsert_cifra(conn, n, idx, fila, meta.get("fecha_publicacion"))
            out["cifras"] += 1

        # 4) el detalle por institución, con resolución de municipio
        for idx, fila in enumerate(meta.get("instituciones") or []):
            fc = fila.get("fecha_corte") or meta.get("fecha_publicacion")
            slug = _upsert_ips(conn, n, idx, fila, fc, catalogo)
            out["instituciones"] += 1
            if slug:
                out["instituciones_resueltas"] += 1

        out["sitreps_cargados"] += 1

    # 5) detector de serie nueva
    nuevos = sitreps_nuevos(conn)
    if nuevos:
        out["sitreps_sin_transcribir"] = nuevos

    conn.commit()
    if own:
        conn.close()
    return out


def cifras_por_ambito(conn) -> dict[str, dict[str, dict]]:
    """La última cifra de cada (ámbito, concepto), con su fecha, autor y
    fuente. Es el contrato que consume la sección «Lo que declara el
    departamento» de las fichas: `{ambito: {concepto: {valor, fecha_corte,
    autor, fuente_citada, sitrep_n, nota}}}`.

    Solo mira las filas con `nivel_complejidad IS NULL` — el total del
    concepto para ese ámbito — porque un ámbito puede tener además hasta 4
    filas de desglose por nivel de complejidad (la matriz del sitrep 4) que no
    son «la cifra», son su detalle. Quien necesite ese desglose consulta
    `ops_salud_cifras` directamente filtrando por `nivel_complejidad`.

    «Última» es por `sitrep_n` (el orden de publicación), no por
    `fecha_corte`: dos sitrep pueden compartir fecha de corte (el 5 publica el
    19-ago con corte al 18-ago) y el más reciente PUBLICADO es el que manda.
    """
    out: dict[str, dict[str, dict]] = {}
    for (ambito, concepto, valor, valor_raw, autor, fuente, nota, sitrep_n,
        fecha_corte) in conn.execute(
            "SELECT ambito, concepto, valor, valor_raw, autor, fuente_citada,"
            " nota, sitrep_n, fecha_corte FROM ops_salud_cifras"
            " WHERE nivel_complejidad IS NULL ORDER BY sitrep_n"):
        out.setdefault(ambito, {})[concepto] = {
            "valor": valor, "valor_raw": valor_raw, "autor": autor,
            "fuente_citada": fuente, "nota": nota, "sitrep_n": sitrep_n,
            "fecha_corte": fecha_corte}
    return out


def instituciones_por_municipio(conn) -> dict[str, list[dict]]:
    """El detalle por institución, agrupado por `municipio_slug` (excluidas
    las que no resolvieron municipio). Contrato para las fichas municipales:
    `{slug: [{sitrep_n, fecha_corte, nombre_ips, nivel_complejidad,
    observacion, municipio_literal, departamento_literal}, …]}`, en el orden
    en que se transcribieron (sitrep, idx).
    """
    out: dict[str, list[dict]] = {}
    for (slug, sitrep_n, fecha_corte, nombre, nivel, obs, mun_lit,
        dep_lit) in conn.execute(
            "SELECT municipio_slug, sitrep_n, fecha_corte, nombre_ips,"
            " nivel_complejidad, observacion, municipio_literal,"
            " departamento_literal FROM ops_salud_ips"
            " WHERE municipio_slug IS NOT NULL ORDER BY sitrep_n, idx"):
        out.setdefault(slug, []).append({
            "sitrep_n": sitrep_n, "fecha_corte": fecha_corte,
            "nombre_ips": nombre, "nivel_complejidad": nivel,
            "observacion": obs, "municipio_literal": mun_lit,
            "departamento_literal": dep_lit})
    return out


if __name__ == "__main__":
    from common import db
    c = db()
    print(json.dumps(run(c), indent=1, ensure_ascii=False))
    c.close()
