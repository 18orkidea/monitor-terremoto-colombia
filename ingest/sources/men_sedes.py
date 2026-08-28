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
    categorías. No hay versión ni changelog: el snapshot diario es la única
    memoria de qué decía cada día, y por eso la tabla acumula por
    `(cod_dane, snapshot_date)` en vez de pisar el estado anterior.
  - **'No aporta información' NO significa «sin daño»**: significa que nadie ha
    verificado esa sede (8.089 de 9.273 el 28-ago). Es el mismo principio que
    los ceros del RUD: la ausencia de dato es dato, y convertirla en «bien» es
    fabricar una afirmación (R3 aplicado a un literal en vez de a un número).
  - La geometría nativa viene en Web Mercator (wkid 102100): se pide SIEMPRE
    con `outSR=4326` y lo que se guarda es lat/lon geográficos.

Los literales (`estado_fisico`, `sede_principal`, `confianza_geo`) se guardan
TAL CUAL los publica la fuente, sin normalizar: traducir «S» a «sí» o agrupar
categorías es trabajo de la capa de presentación, no del archivo.

Plan de sucesión (si la capa muere o se vacía):
  - Sobreviven los snapshots diarios paginados (`men_sedes_offset*.json`) y la
    serie en `men_sedes` / `data/dumps/men_sedes.csv` — con eso se reconstruye
    cada día visto sin la fuente.
  - Export dedicado versionado: `data/public/men_sedes.geojson` (el registro
    completo del último día) y `data/public/men_sedes_mapa.geojson` (solo lo
    que reporta afectación, que es lo que pinta el mapa).
  - El dashboard (SPA, no archivable por fetch) va a Wayback en `daily.yml`;
    el FeatureServer no lo necesita: ya lo archiva `fetch()` cada día.
"""
from __future__ import annotations

import json

from common import PUBLIC, fetch_json, to_num, today, utcnow

LAYER = ("https://services3.arcgis.com/Rv2iYa4TcJdIHIfq/arcgis/rest/services/"
         "SISE202608_Priorizadas_Final/FeatureServer/0/query")
PAGE = 2000        # maxRecordCount del servicio (5 páginas el 28-ago-2026)

# outFields explícito: fija el contrato con la fuente (si un campo desaparece,
# la corrida lo nota) y sí, tres llevan tilde — la capa los publica así.
FIELDS = ["OBJECTID", "COD_DANE", "CORREO_INS", "SEDE_PRINC", "SECTOR",
          "CONFIA_GEO", "Código_Establecimiento", "Nombre_Establecimiento",
          "Nombre_Sede", "Zona_1", "Dirección", "Teléfono", "Niveles",
          "NOM_REG", "COD_DEP", "NOM_DEP", "COD_MUN", "NOM_MUN", "CAT_MUN",
          "MUN_PDET", "MUN_ZOMAC", "COD_ETC", "NOM_ETC", "TOTAL_MATRICULA",
          "MATRICULA_PREL", "ESTADO_FISICO"]

# Los 6 literales de ESTADO_FISICO que reportan afectación — decisión editorial
# de JP trasladada al vocabulario del 28-ago-2026: al mapa va TODO lo que
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


def _texto(v):
    """Texto limpio de la fuente, o None si viene vacío. No traduce nada."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    snap = snapshot_date or today()
    offset, filas = 0, 0
    while True:
        st, page = fetch_json(LAYER, {
            "where": "1=1", "f": "json", "outFields": ",".join(FIELDS),
            "outSR": 4326, "resultOffset": offset, "resultRecordCount": PAGE,
            "orderByFields": "OBJECTID",
        }, note=f"men sedes offset={offset}", conn=conn,
            snapshot_name=f"men_sedes_offset{offset}.json")
        feats = (page or {}).get("features") or []
        if not feats:
            if offset == 0:
                conn.commit()
                if own:
                    conn.close()
                return {"error": f"MEN sedes HTTP {st} sin features: la capa "
                                 "se republica sin aviso — ver snapshots "
                                 "previos y el test de supuesto"}
            break
        for f in feats:
            at = f.get("attributes") or {}
            cod_dane = _texto(at.get("COD_DANE"))
            if not cod_dane:
                continue    # sin identificador no hay fila trazable
            geom = f.get("geometry") or {}
            conn.execute(
                "INSERT INTO men_sedes (cod_dane, snapshot_date,"
                " cod_establecimiento, nombre_establecimiento, nombre_sede,"
                " sede_principal, sector, correo_institucional, direccion,"
                " telefono, niveles, zona, cod_dep, nom_dep, cod_mun, nom_mun,"
                " cat_mun, mun_pdet, mun_zomac, nom_reg, cod_etc, nom_etc,"
                " total_matricula, matricula_prel, estado_fisico,"
                " confianza_geo, lat, lon, first_seen)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "?,?,"
                "  COALESCE((SELECT MIN(first_seen) FROM men_sedes"
                "            WHERE cod_dane=?), ?))"
                " ON CONFLICT(cod_dane, snapshot_date) DO UPDATE SET"
                "  cod_establecimiento=excluded.cod_establecimiento,"
                "  nombre_establecimiento=excluded.nombre_establecimiento,"
                "  nombre_sede=excluded.nombre_sede,"
                "  sede_principal=excluded.sede_principal,"
                "  sector=excluded.sector,"
                "  correo_institucional=excluded.correo_institucional,"
                "  direccion=excluded.direccion, telefono=excluded.telefono,"
                "  niveles=excluded.niveles, zona=excluded.zona,"
                "  cod_dep=excluded.cod_dep, nom_dep=excluded.nom_dep,"
                "  cod_mun=excluded.cod_mun, nom_mun=excluded.nom_mun,"
                "  cat_mun=excluded.cat_mun, mun_pdet=excluded.mun_pdet,"
                "  mun_zomac=excluded.mun_zomac, nom_reg=excluded.nom_reg,"
                "  cod_etc=excluded.cod_etc, nom_etc=excluded.nom_etc,"
                "  total_matricula=excluded.total_matricula,"
                "  matricula_prel=excluded.matricula_prel,"
                "  estado_fisico=excluded.estado_fisico,"
                "  confianza_geo=excluded.confianza_geo,"
                "  lat=excluded.lat, lon=excluded.lon",
                (cod_dane, snap,
                 _texto(at.get("Código_Establecimiento")),
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
                 geom.get("y"), geom.get("x"),
                 cod_dane, utcnow()))
            filas += 1
        conn.commit()    # por página: una caída a mitad no pierde lo traído
        offset += PAGE
        if len(feats) < PAGE:
            break
    out = {"snapshot_date": snap, "sedes": filas, "por_estado": resumen(conn)}
    out["export"] = export(conn)
    out["export_mapa"] = export_mapa(conn)
    if own:
        conn.close()
    return out


def _ultimo_snapshot(conn) -> str | None:
    r = conn.execute("SELECT MAX(snapshot_date) FROM men_sedes").fetchone()
    return r[0] if r else None


def resumen(conn) -> dict:
    """Conteo por estado físico del último snapshot — el orden de magnitud que
    se contrasta contra la sonda del día."""
    dia = _ultimo_snapshot(conn)
    if dia is None:
        return {}
    return {estado or "—": n for estado, n in conn.execute(
        "SELECT estado_fisico, COUNT(*) FROM men_sedes"
        " WHERE snapshot_date=? GROUP BY estado_fisico ORDER BY COUNT(*) DESC",
        (dia,))}


# Columnas del export completo. Aquí SÍ van dirección, teléfono y correo:
# son datos institucionales que la propia fuente publica en abierto, y el
# geojson completo es el registro auditable, no el producto del mapa.
_COLS = ["cod_dane", "cod_establecimiento", "nombre_establecimiento",
         "nombre_sede", "sede_principal", "sector", "correo_institucional",
         "direccion", "telefono", "niveles", "zona", "cod_dep", "nom_dep",
         "cod_mun", "nom_mun", "cat_mun", "mun_pdet", "mun_zomac", "nom_reg",
         "cod_etc", "nom_etc", "total_matricula", "matricula_prel",
         "estado_fisico", "confianza_geo"]

# Propiedades del geojson del mapa: lo mínimo que el globo necesita contar.
# Sin dirección/teléfono/correo — el mapa no es una guía telefónica; quien
# audite tiene el geojson completo y el sqlite.
_COLS_MAPA = ["cod_dane", "nombre_sede", "nombre_establecimiento", "sector",
              "zona", "nom_mun", "nom_dep", "estado_fisico",
              "total_matricula", "confianza_geo"]


def _features(conn, cols, where="", args=()) -> list[dict]:
    dia = _ultimo_snapshot(conn)
    if dia is None:
        return []
    feats = []
    for row in conn.execute(
            f"SELECT lon, lat, {', '.join(cols)} FROM men_sedes"
            f" WHERE snapshot_date=? AND lon IS NOT NULL AND lat IS NOT NULL"
            f" {where} ORDER BY cod_dane", (dia, *args)):
        # Un campo sin dato NO viaja al geojson: el globo no puede pintar
        # «Matrícula: —» y hacer creer que la fuente dijo algo (mismo criterio
        # que unosat.export).
        props = {k: v for k, v in zip(cols, row[2:]) if v not in (None, "")}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point",
                                   "coordinates": [row[0], row[1]]},
                      "properties": props})
    return feats


def export(conn) -> int:
    """`data/public/men_sedes.geojson`: TODAS las sedes del último snapshot.

    Es el registro auditable — incluye las 8.089 'No aporta información',
    porque cuántas sedes siguen sin verificar es un dato del monitor, no ruido.
    Sale de la base, no de la red: sobrevive a una corrida sin fuente (R13).
    """
    feats = _features(conn, _COLS)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "men_sedes.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


def export_mapa(conn) -> int:
    """`data/public/men_sedes_mapa.geojson`: solo lo que reporta afectación.

    El filtro es `ESTADOS_CON_DANO` — todo lo que declara daño va al mapa;
    'Sin afectación' y 'No aporta información' se quedan en el registro
    completo. Propiedades mínimas: sin dirección, teléfono ni correo.
    """
    marks = ",".join("?" * len(ESTADOS_CON_DANO))
    feats = _features(conn, _COLS_MAPA,
                      where=f"AND estado_fisico IN ({marks})",
                      args=ESTADOS_CON_DANO)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "men_sedes_mapa.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


if __name__ == "__main__":
    from common import db
    c = db()
    print(json.dumps(run(c), indent=1, ensure_ascii=False))
    c.close()
