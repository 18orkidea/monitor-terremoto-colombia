"""Sedes educativas MEN (SISE): el estado físico de cada colegio, sede a sede.

Qué aporta que no tenga nadie más: `official_events.centros_educativos` es un
AGREGADO por municipio (cuántos centros afectados declara el EDAN); esta capa
es la primera fuente oficial que baja al detalle de la SEDE, con nombre,
coordenada propia, matrícula y un estado físico declarado tras el sismo. Donde
aquello dice «12 centros educativos», esto dice cuáles, dónde y cómo están.

Fuente: capa ArcGIS pública del Ministerio de Educación Nacional (SISE),
sin autenticación. El dashboard que la enseña:
https://mineducacion.maps.arcgis.com/apps/dashboards/5e47f09f3b374396a5b3be15e8e96192

Lo que la fuente NO garantiza (medido, no supuesto):
  - **La capa se republica y muta en horas.** El 28-ago-2026 entre las 20:07 y
    las 23:15 pasó de ~50.000 filas y 7 categorías de estado a 9.273 filas y 8
    categorías. No hay versión ni changelog: la comprobación diaria es la
    única memoria de qué decía cada día.
  - **'No aporta información' NO significa «sin daño»**: significa que nadie ha
    verificado esa sede (8.089 de 9.273 el 28-ago). Es el mismo principio que
    los ceros del RUD: la ausencia de dato es dato, y convertirla en «bien» es
    fabricar una afirmación (R3 aplicado a un literal en vez de a un número).
  - La geometría nativa viene en Web Mercator (wkid 102100): se pide SIEMPRE
    con `outSR=4326` y lo que se guarda es lat/lon geográficos.

**Se comprueba a diario; se archiva solo lo que cambia.** La corrida completa
pesa ~6 MB y el 87 % de las filas repite 'No aporta información': acumular la
foto entera cada día serían ~180 MB/mes de copias casi idénticas — justo lo
que el principio de archivo prohíbe («nada que no cambia se archiva dos
veces»). El diseño reparte el trabajo en dos capas, cada una con su criterio
de «idéntico»:

  - **Snapshots (byte a byte, lo hace `common.fetch`)**: si una página llega
    con el mismo sha256 que la copia vigente, la fila de `sources_log` apunta
    al snapshot ya existente y no se escribe fichero nuevo. La fila diaria
    con su sha real es la prueba de que ESE día se comprobó — de ella se
    alimenta el detector de silencio (R15). Un cuerpo distinto se archiva
    entero, como siempre.
  - **Tabla (campo a campo, lo hace este módulo)**: la primera corrida real
    carga la línea base completa (las 9.273, para que el conteo de 'No aporta
    información' siga siendo consultable); después solo entra una fila cuando
    ALGÚN campo de la sede cambió respecto a su fila vigente. Precedente del
    proyecto: la tabla del RUD en las fichas — una fila por cambio, no por
    día. El corte vigente de una sede es su última fila.

  El caso perverso —mismo contenido, otro orden de features— queda repartido
  entre las dos capas a propósito: el snapshot SÍ se escribe (la fuente dijo
  literalmente otra cosa, y eso es un hecho sobre la fuente), la tabla NO
  recibe filas (ninguna sede cambió). Comparar la tabla por bytes habría
  fabricado 9.273 «cambios» de un reordenamiento.

  Lo que este diseño no registra (laguna conocida, en docs/LIMITACIONES.md):
  una sede que DESAPAREZCA de la capa conserva su última fila como vigente y
  no deja fila propia de desaparición — la capa ya perdió ~40.000 filas de un
  día para otro antes de nuestra línea base, así que no es hipotético.

La tabla guarda como mucho una fila por sede y día: si la capa se republica
dos veces en el mismo día con contenidos distintos, la fila del día se
actualiza (ON CONFLICT) y ambos cuerpos sobreviven en los snapshots (sufijo
`_sha8` intradía de `common.fetch`). Y si la republicación pilla a la corrida
entre dos páginas, el diff por `cod_dane` absorbe el duplicado — el riesgo
residual (una sede que se pierda en ese instante) está documentado.

Los literales (`estado_fisico`, `sede_principal`, `confianza_geo`) se guardan
TAL CUAL los publica la fuente, sin normalizar: traducir «S» a «sí» o agrupar
categorías es trabajo de la capa de presentación, no del archivo.

Plan de sucesión (si la capa muere o se vacía):
  - Sobreviven los snapshots paginados (`men_sedes_offset*.json`, uno por
    contenido distinto visto) y la serie de cambios en `men_sedes` /
    `data/dumps/men_sedes.csv` — con eso se reconstruye el corte de cualquier
    día sin la fuente.
  - Export dedicado versionado: `data/public/men_sedes_mapa.geojson` — solo
    las sedes que reportan afectación, que es lo que publica el mapa. El
    registro completo no necesita un tercer formato: ya es auditable por
    snapshot + tabla + su CSV de dumps.
  - El dashboard (SPA, no archivable por fetch) va a Wayback en `daily.yml`;
    el FeatureServer no lo necesita: ya lo archiva `fetch()` cuando cambia.
"""
from __future__ import annotations

import json

from common import PUBLIC, fetch_json, to_num, today, utcnow

LAYER = ("https://services3.arcgis.com/Rv2iYa4TcJdIHIfq/arcgis/rest/services/"
         "SISE202608_Priorizadas_Final/FeatureServer/0/query")
PAGE = 2000        # tamaño de página SOLICITADO; la capa sirve lo que quiera

# outFields explícito: fija el contrato con la fuente (si un campo desaparece,
# la corrida lo nota) y sí, tres llevan tilde — la capa los publica así.
FIELDS = ["OBJECTID", "COD_DANE", "CORREO_INS", "SEDE_PRINC", "SECTOR",
          "CONFIA_GEO", "Código_Establecimiento", "Nombre_Establecimiento",
          "Nombre_Sede", "Zona_1", "Dirección", "Teléfono", "Niveles",
          "NOM_REG", "COD_DEP", "NOM_DEP", "COD_MUN", "NOM_MUN", "CAT_MUN",
          "MUN_PDET", "MUN_ZOMAC", "COD_ETC", "NOM_ETC", "TOTAL_MATRICULA",
          "MATRICULA_PREL", "ESTADO_FISICO"]

# Los 6 literales de ESTADO_FISICO que reportan afectación — decisión
# editorial trasladada al vocabulario del 28-ago-2026: al mapa va TODO lo que
# reporta afectación; fuera 'Sin afectación' y 'No aporta información'.
# CONTRATO: la mitad de presentación importa esta constante por nombre y módulo
# (test espejo del coder de site/); no renombrar sin tocar las dos mitades.
ESTADOS_CON_DANO = (
    "Colapso total",
    "Riesgo inminente de colapso",
    "Colapso parcial",
    "Afectación parcial",
    "Afectación menor",
    "Reporta afectación sin definir el impacto",
)

# El vocabulario completo observado el 28-ago-2026. Si la fuente publica un
# literal nuevo, el guardián de test_hipotesis AVISA (R11): una categoría
# desconocida no se ignora ni se descarta — obliga a decidir si reporta daño.
ESTADOS_CONOCIDOS = ESTADOS_CON_DANO + ("Sin afectación", "No aporta información")

# Los tres estados críticos: los que el guardián de coordenadas no perdona.
ESTADOS_CRITICOS = ("Colapso total", "Riesgo inminente de colapso",
                    "Colapso parcial")

# Las columnas de CONTENIDO de una sede, en el orden del INSERT: todas menos
# las de archivo (cod_dane, snapshot_date, first_seen). Definen qué es un
# «cambio»: una fila nueva entra solo si esta tupla difiere de la vigente.
_COLS_CONTENIDO = [
    "cod_establecimiento", "nombre_establecimiento", "nombre_sede",
    "sede_principal", "sector", "correo_institucional", "direccion",
    "telefono", "niveles", "zona", "cod_dep", "nom_dep", "cod_mun", "nom_mun",
    "cat_mun", "mun_pdet", "mun_zomac", "nom_reg", "cod_etc", "nom_etc",
    "total_matricula", "matricula_prel", "estado_fisico", "confianza_geo",
    "lat", "lon"]

# El corte vigente: la última fila de cada sede. Es la subconsulta que
# comparten resumen(), export_mapa() y los guardianes de hipótesis.
SQL_VIGENTE = ("snapshot_date=(SELECT MAX(snapshot_date) FROM men_sedes"
               " WHERE cod_dane=m.cod_dane)")


def _texto(v):
    """Texto limpio de la fuente, o None si viene vacío. No traduce nada."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _contenido(at: dict, geom: dict) -> tuple:
    """La tupla de contenido de una sede, en el orden de _COLS_CONTENIDO."""
    return (_texto(at.get("Código_Establecimiento")),
            _texto(at.get("Nombre_Establecimiento")),
            _texto(at.get("Nombre_Sede")),
            _texto(at.get("SEDE_PRINC")), _texto(at.get("SECTOR")),
            _texto(at.get("CORREO_INS")), _texto(at.get("Dirección")),
            _texto(at.get("Teléfono")), _texto(at.get("Niveles")),
            _texto(at.get("Zona_1")), _texto(at.get("COD_DEP")),
            _texto(at.get("NOM_DEP")), _texto(at.get("COD_MUN")),
            _texto(at.get("NOM_MUN")), _texto(at.get("CAT_MUN")),
            _texto(at.get("MUN_PDET")), _texto(at.get("MUN_ZOMAC")),
            _texto(at.get("NOM_REG")), _texto(at.get("COD_ETC")),
            _texto(at.get("NOM_ETC")),
            # R3: «NA»/vacío → NULL + nada de ceros fabricados
            to_num(at.get("TOTAL_MATRICULA")),
            to_num(at.get("MATRICULA_PREL")),
            _texto(at.get("ESTADO_FISICO")),
            _texto(at.get("CONFIA_GEO")),
            geom.get("y"), geom.get("x"))


def _vigentes(conn) -> dict[str, tuple]:
    """{cod_dane: tupla de contenido} del corte vigente de la tabla."""
    cols = ", ".join(_COLS_CONTENIDO)
    return {r[0]: tuple(r[1:]) for r in conn.execute(
        f"SELECT cod_dane, {cols} FROM men_sedes m WHERE {SQL_VIGENTE}")}


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    snap = snapshot_date or today()
    vigentes = _vigentes(conn)
    linea_base = not vigentes
    offset = descargadas = nuevas = cambiadas = 0
    while True:
        st, page = fetch_json(LAYER, {
            "where": "1=1", "f": "json", "outFields": ",".join(FIELDS),
            "outSR": 4326, "resultOffset": offset, "resultRecordCount": PAGE,
            "orderByFields": "OBJECTID",
        }, note=f"men sedes offset={offset}", conn=conn,
            snapshot_name=f"men_sedes_offset{offset}.json")
        # ArcGIS devuelve errores con HTTP 200 y un {"error": {...}} en el
        # cuerpo (throttling, capa despublicada). Un fallo A MITAD de serie
        # no es un fin normal: dejarlo pasar publicaría media foto del día
        # como si fuera entera. Lo ya insertado son cambios reales observados
        # y se queda (commit por página); la corrida se rotula de error.
        if st != 200 or not page or page.get("error"):
            conn.commit()
            if own:
                conn.close()
            return {"error": f"MEN sedes HTTP {st} en offset={offset} "
                             f"({(page or {}).get('error') or 'sin cuerpo'}): "
                             f"descarga incompleta ({descargadas} sedes "
                             "comprobadas) — la capa se republica sin aviso, "
                             "ver snapshots previos y el test de supuesto"}
        feats = page.get("features") or []
        if not feats:
            if page.get("exceededTransferLimit"):
                # «no hay filas pero hay más por traer» es un contrato roto,
                # no un final: cortar aquí truncaría en silencio.
                conn.commit()
                if own:
                    conn.close()
                return {"error": f"MEN sedes offset={offset}: página vacía "
                                 "con exceededTransferLimit — contrato de "
                                 f"paginación roto ({descargadas} sedes "
                                 "comprobadas)"}
            if offset == 0:
                conn.commit()
                if own:
                    conn.close()
                return {"error": "MEN sedes: la capa respondió sin features — "
                                 "se republica sin aviso, ver snapshots "
                                 "previos y el test de supuesto"}
            break
        for f in feats:
            at = f.get("attributes") or {}
            cod_dane = _texto(at.get("COD_DANE"))
            if not cod_dane:
                continue    # sin identificador no hay fila trazable
            descargadas += 1
            contenido = _contenido(at, f.get("geometry") or {})
            previo = vigentes.get(cod_dane)
            if previo == contenido:
                continue    # sin cambio: la comprobación queda en sources_log
            conn.execute(
                "INSERT INTO men_sedes (cod_dane, snapshot_date, "
                + ", ".join(_COLS_CONTENIDO) + ", first_seen)"
                " VALUES (?,?," + ",".join("?" * len(_COLS_CONTENIDO)) + ","
                "  COALESCE((SELECT MIN(first_seen) FROM men_sedes"
                "            WHERE cod_dane=?), ?))"
                " ON CONFLICT(cod_dane, snapshot_date) DO UPDATE SET "
                + ", ".join(f"{c}=excluded.{c}" for c in _COLS_CONTENIDO),
                (cod_dane, snap, *contenido, cod_dane, utcnow()))
            # actualizar el corte en memoria: si la misma sede reaparece en
            # otra página de ESTA corrida (republicación a mitad de descarga),
            # se compara contra lo recién visto y no se duplica
            vigentes[cod_dane] = contenido
            if previo is None:
                nuevas += 1
            else:
                cambiadas += 1
        conn.commit()    # por página: una caída a mitad no pierde lo traído
        # Por lo RECIBIDO, no por PAGE: maxRecordCount es un ajuste de
        # publicación de la capa y puede bajar en cualquier republicación —
        # si mañana sirve páginas de 1.000, avanzar de 2.000 en 2.000
        # saltaría la mitad de las sedes. El corte de bucle es solo la
        # página vacía de arriba: `len(feats) < PAGE` como señal de final
        # truncaba en silencio con el mismo cambio de ajuste.
        offset += len(feats)
    out = {"snapshot_date": snap, "sedes_comprobadas": descargadas,
           "linea_base": linea_base, "nuevas": nuevas, "cambiadas": cambiadas,
           "sin_cambios": not (nuevas or cambiadas),
           "por_estado": resumen(conn)}
    # el export se regenera siempre (es idempotente y barato): así un clon
    # nuevo lo tiene aunque el día no traiga cambios (R13)
    out["export_mapa"] = export_mapa(conn)
    if own:
        conn.close()
    return out


def resumen(conn) -> dict:
    """Conteo por estado físico del corte vigente (última fila por sede) —
    el orden de magnitud que se contrasta contra la sonda del día."""
    return {estado or "—": n for estado, n in conn.execute(
        f"SELECT estado_fisico, COUNT(*) FROM men_sedes m WHERE {SQL_VIGENTE}"
        " GROUP BY estado_fisico ORDER BY COUNT(*) DESC")}


# Propiedades del geojson del mapa: lo mínimo que el globo necesita contar.
# Sin dirección/teléfono/correo — el mapa no es una guía telefónica; quien
# audite tiene los snapshots, la tabla y su CSV de dumps.
_COLS_MAPA = ["cod_dane", "nombre_sede", "nombre_establecimiento", "sector",
              "zona", "nom_mun", "nom_dep", "estado_fisico",
              "total_matricula", "confianza_geo"]


def export_mapa(conn) -> int:
    """`data/public/men_sedes_mapa.geojson`: solo lo que reporta afectación.

    Sobre el corte vigente (última fila por sede) y filtrado por
    `ESTADOS_CON_DANO`: todo lo que declara daño va al mapa; 'Sin afectación'
    y 'No aporta información' se quedan en el registro (tabla + dumps +
    snapshots). Sale de la base, no de la red: sobrevive a una corrida sin
    fuente (R13). Es el ÚNICO geojson de la fuente: publicar además el
    registro completo eran ~6 MB republicados a diario sin lector.
    """
    marks = ",".join("?" * len(ESTADOS_CON_DANO))
    feats = []
    for row in conn.execute(
            f"SELECT lon, lat, {', '.join(_COLS_MAPA)} FROM men_sedes m"
            f" WHERE {SQL_VIGENTE} AND lon IS NOT NULL AND lat IS NOT NULL"
            f" AND estado_fisico IN ({marks}) ORDER BY cod_dane",
            ESTADOS_CON_DANO):
        # Un campo sin dato NO viaja al geojson: el globo no puede pintar
        # «Matrícula: —» y hacer creer que la fuente dijo algo (mismo criterio
        # que unosat.export).
        props = {k: v for k, v in zip(_COLS_MAPA, row[2:])
                 if v not in (None, "")}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point",
                                   "coordinates": [row[0], row[1]]},
                      "properties": props})
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "men_sedes_mapa.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


if __name__ == "__main__":
    from common import db
    c = db()
    print(json.dumps(run(c), indent=1, ensure_ascii=False))
    c.close()
