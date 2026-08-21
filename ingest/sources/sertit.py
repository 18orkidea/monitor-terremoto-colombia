"""ICube-SERTIT: la tercera mirada satelital, y la primera que discrepa.

Qué aporta que no tenga nadie más: **puntos de daño en municipios que ningún
otro servicio miró** —Roldanillo y La Virginia— y, en Pereira, Cali y
Manizales, una segunda cartografía del MISMO terremoto sobre las mismas
ciudades. Ahí está lo valioso: donde dos servicios se superponen, se puede
medir cuánto ve uno que el otro no. Comparte vocabulario de daño con
Copernicus (Destroyed / Damaged / Possibly damaged), así que las dos capas se
leen con la misma leyenda.

Origen: servicio francés de cartografía rápida del laboratorio ICube
(Universidad de Estrasburgo), activado dentro de la **Charter Internacional
del Espacio y las Grandes Catástrofes**, activación 1048 / call 1202, la que
solicitó la propia UNGRD el 10-ago-2026.

## Cómo entra el dato (dos canales, y conviene no confundirlos)

1. **El catálogo, por HTTP**: `cartographie-rapide/cartoaction/845/` publica en
   un JSON embebido los cinco productos con su escala, su sensor, su fecha de
   producción y el recuadro que declaran. Se descarga a diario con `fetch()`
   (R4), que lo archiva como cualquier otro cuerpo, y su sha es además la sonda
   de vida: si publican un producto nuevo o reeditan uno, el HTML cambia.

   (Este módulo llegó a archivar solo el catálogo extraído, con el argumento de
   que el HTML traía un token de formulario variable. Era falso: dieciséis
   peticiones del 21-ago-2026 y tres comprobaciones seguidas devuelven el mismo
   sha256. Se archiva el cuerpo servido, que es lo único contra lo que se puede
   contrastar el parseo el día que el regex de `js_data` falle.)
2. **Los vectores, por correo**: su web NO los sirve por URL. Hay un formulario
   —nombre, correo y aceptación de la política de privacidad— y el ZIP llega
   como adjunto. Se pidieron el 20-ago-2026 y llegaron el 21. Por eso los
   cuerpos viven en `data/documentos/sertit/` y se registran con
   `common.registrar_entrega()`, que deja en `sources_log` el sha, el cuerpo y
   el canal por el que entró. Un dato que no se puede volver a descargar tiene
   que constar mejor, no peor.

## Licencia: esta capa viaja con condiciones propias

Las condiciones que acompañan al fichero permiten usar, copiar, modificar y
redistribuir **para cualquier fin salvo comercial**, obligan a citar
`© ICube-SERTIT 2026` y, si se modifica el producto, a declarar qué se cambió
sin sugerir que ICube-SERTIT respalda el uso. Su equipo pidió además que
aparezca su logo. Es **más restrictiva que el resto del monitor**: por eso el
`copyright` viaja pegado a cada punto hasta el geojson público, y no se pierde
en un pie de página. Ver `docs/LIMITACIONES.md`.

## Lo que la fuente NO garantiza

- **Las cifras de sus mapas impresos no cuadran con sus vectores**: el mapa de
  Cali rotula 86 edificios y el paquete trae 103; el de Pereira rotula 253 y
  trae 252. El monitor publica **lo que traen los vectores**, que es lo
  auditable, y lo dice.
- **No cubren el municipio, sino un recorte**: en Pereira miraron 2,78 km²
  frente a los 9,8 km² de Copernicus. Ninguna de las dos cifras es «el daño de
  Pereira»; son dos ventanas distintas sobre la misma ciudad.
- **No hay validación en campo.** Es fotointerpretación sobre imagen de 0,3 m
  (`PROCESSING: Photo-interpretation`), como la de Copernicus.
- El catálogo web no versiona de forma legible: si reeditan un producto, el id
  no cambia. Lo que cambia es el sha del ZIP, y por eso la clave del dato es el
  sha del paquete y no el id del producto.

## Plan de sucesión (si sertit.unistra.fr muere mañana)

- **Sobrevive todo lo que se publica**: los cinco ZIP están en el repo con su
  sha en `sources_log`, y de ellos sale cada punto. La fuente puede cerrar sin
  que el monitor pierda un solo dato — es la posición de archivo más fuerte de
  todas sus fuentes, precisamente porque el dato cabe en git (248 KB).
- **Snapshot diario** del catálogo: aunque la web caiga, queda la serie de lo
  que declaraba cada día.
- **Export dedicado**: `data/public/sertit_damage.geojson`, que es lo que lee
  el sitio y lo que un tercero puede reutilizar.
- **Wayback**: la página de la acción, la de cada producto y —sobre todo— el
  mapa público de cada uno en el portal de la Charter (`url_mapa`), que es el
  artefacto donde se lee la cifra rotulada. Los vectores son lo único sin URL
  que archivar en un tercero: llegaron por correo y solo existen aquí.
- Precedente ya vivido: su **API REST pública, documentada y anunciada por la
  ESA, devolvía 404** cuando se consultó el 20-ago-2026. Una fuente que ya
  perdió una interfaz puede perder otra.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from common import DATA, PUBLIC, fetch, registrar_entrega, today, utcnow
from municipios import MUNICIPIOS

BASE = "https://sertit.unistra.fr"
ACCION = 845                       # «Séisme en Colombie» en su catálogo
ACCION_URL = f"{BASE}/cartographie-rapide/cartoaction/{ACCION}/"
DOCUMENTOS = DATA / "documentos" / "sertit"

# Capa de edificios. El paquete trae además AreaOfInterest (lo que miraron),
# ImageFootprint (la huella de la imagen), ObservedEventP (eventos observados)
# y PointOfInterest (hospitales, colegios). Hoy se ingiere el daño en edificios
# y el área analizada; las otras quedan en el ZIP archivado, disponibles el día
# que hagan falta.
CAPA_DANO = "UrbanP"
CAPA_AOI = "AreaOfInterest"

# El mapa público de cada producto, en el portal de la Charter, y la cifra que
# ese mapa ROTULA en su leyenda. Se comprobaron uno a uno el 20-ago-2026 (HTTP
# 200, sin autenticación). La cifra rotulada no siempre cuadra con los vectores
# del mismo producto —Cali rotula 86 y su paquete trae 103— y por eso se guarda
# con su procedencia en vez de quedar como afirmación del autor en un docstring.
CHARTER_BUNDLE = "https://disasterscharter.org/cos-api/api/file/public/37686205"
MAPAS_CHARTER = {
    "Pereira":     ("vap-1202-1-product.jpg", 253),
    "Manizales":   ("vap-1202-2-product.jpg", 31),
    "Cali":        ("vap-1202-3-product.jpg", 86),
    "La Virginia": ("vap-1202-11-product.pdf", 49),
    "Roldanillo":  ("vap-1202-13-product.jpg", 77),
}


def _norm(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower().replace(" ", "")


def _municipio_de_nombre(base: str) -> tuple[str | None, str]:
    """Municipio a partir del nombre del fichero, y de dónde salió.

    SERTIT nombra sus productos `…_COLOMBIA_<MUNICIPIO>_IMPACTMAP_…`. La
    coincidencia contra el catálogo es EXACTA normalizada, nunca por subcadena
    (R10): «Anserma» es prefijo de «Ansermanuevo», que es otro municipio y de
    otro departamento. Si no casa, se devuelve el literal de la fuente marcado
    como tal, para que nadie lo confunda con un municipio del catálogo.
    """
    # Sin IGNORECASE no casaría: la fuente escribe `COLOMBIA_PEREIRA` en unos
    # productos y `Colombia_LaVirginia` en otros, y de los cinco solo uno lleva
    # capitalización mixta. El primer intento se comió cuatro municipios.
    m = re.search(r"colombia_([A-Za-z]+)_impact", base, re.IGNORECASE)
    if not m:
        return None, "desconocido"
    cola = m.group(1)
    for nombre in MUNICIPIOS:
        if _norm(nombre) == _norm(cola):
            return nombre, "catalogo"
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cola), "texto_sertit"


def productos_de_pagina(body: bytes) -> list[dict]:
    """Los cinco productos, del JSON que su web embebe en el HTML.

    Se lee el bloque `js_data` en vez de raspar etiquetas: es el mismo objeto
    que alimenta su propio mapa, así que si cambia el maquetado seguimos
    leyendo, y si cambia el contrato el test de supuesto lo canta.
    """
    m = re.search(rb"var js_data = (\{.*?\});\s*\n", body, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1).decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return []
    accion = data.get("itemAction") or {}
    productos = accion.get("produits") or {}
    out = []
    for pid, p in productos.items():
        muni, origen = _municipio_de_nombre(p.get("nomAnnexes") or "")
        out.append({
            "producto_id": int(pid),
            "accion_id": int(accion.get("id") or ACCION),
            "charter": accion.get("charte"),
            "n_producto": p.get("nProduit"),
            "nombre_base": p.get("nomAnnexes"),
            "municipio": muni, "municipio_origen": origen,
            "escala": p.get("echelle"),
            "formato": p.get("formatImpression"),
            "tipo": p.get("type"),
            "imagen_principal": p.get("imgPrincipale"),
            "fecha_produccion": (p.get("dateProduction") or "")[:10] or None,
            # La página del producto, que es de donde se descargó el mapa y por
            # donde se pidió el paquete. Va a la base para que el paso de
            # Wayback la archive: es la URL pública que sostiene la afirmación
            # «el mapa rotula 86 y el paquete trae 103».
            "url_producto": f"{BASE}/cartographie-rapide/cartoproduct/{pid}/",
            "url_mapa": (f"{CHARTER_BUNDLE}/{MAPAS_CHARTER[muni][0]}?version=1.0"
                         if muni in MAPAS_CHARTER else None),
            "cifra_rotulada": MAPAS_CHARTER[muni][1] if muni in MAPAS_CHARTER else None,
            "bbox_declarado": json.dumps(p.get("coordinates_square"),
                                         ensure_ascii=False)
            if p.get("coordinates_square") else None,
        })
    return sorted(out, key=lambda x: x["producto_id"])


def _capa(nombre: str) -> str:
    """`…_ICube-SERTIT_en_UrbanP.geojson` → `UrbanP`."""
    return re.sub(r"\.geojson$", "", nombre).rsplit("_", 1)[-1]


def paquete(body: bytes) -> dict:
    """Puntos de daño y área analizada de un ZIP de vectores.

    Se leen los `.geojson` del paquete y no los shapefiles: SERTIT publica
    ambos y el GeoJSON ya viene en WGS84, así que no hace falta reproyectar ni
    parsear un formato binario para obtener exactamente el mismo dato.
    """
    puntos: list[dict] = []
    area_km2 = None
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for nombre in sorted(z.namelist()):
            if not nombre.lower().endswith(".geojson"):
                continue
            capa = _capa(Path(nombre).name)
            try:
                fc = json.loads(z.read(nombre).decode("utf-8", "replace"))
            except (json.JSONDecodeError, KeyError):
                continue
            feats = fc.get("features") or []
            if capa == CAPA_AOI and feats:
                ha = (feats[0].get("properties") or {}).get("AREA_HA")
                # AREA_HA es la superficie que SERTIT declara haber mirado. Se
                # prefiere a calcularla del polígono: es su cifra, no la nuestra.
                area_km2 = round(ha / 100, 2) if isinstance(ha, (int, float)) else None
            if capa != CAPA_DANO:
                continue
            for i, f in enumerate(feats):
                g = f.get("geometry") or {}
                if g.get("type") != "Point":
                    continue
                lon, lat = (g.get("coordinates") or [None, None])[:2]
                p = f.get("properties") or {}
                puntos.append({
                    "capa": capa, "idx": i,
                    "lon": lon, "lat": lat,
                    "dano": p.get("DAMAGE"),
                    "tipo": p.get("TYPE"),
                    "sensor": p.get("SOURCE"),
                    "sensor_date": p.get("SRC_DATE"),
                    "metodo": p.get("PROCESSING"),
                    "copyright": p.get("COPYRIGHT"),
                })
    return {"puntos": puntos, "area_km2": area_km2}


def _paquetes_archivados() -> list[Path]:
    """Los ZIP depositados a mano en `data/documentos/sertit/`.

    Depositar es un rito manual —los vectores llegan por correo— y por eso
    conviene decir en voz alta cómo se hace: se guarda el adjunto TAL CUAL, sin
    renombrar, porque su nombre lleva el AOI, la escala y la fecha, y eso es
    información. Si un día llega una reedición con el mismo nombre, NO se pisa
    el fichero anterior: se deposita junto al viejo con un sufijo, y el módulo
    los verá los dos. El archivo no se sobrescribe (principio de archivo);
    `paquetes_vigentes()` decide cuál se publica.
    """
    if not DOCUMENTOS.exists():
        return []
    return sorted(DOCUMENTOS.glob("*.zip"))


def run(conn=None, *, snapshot_date=None, **_op) -> dict:
    own = conn is None
    if own:
        from common import db
        conn = db()
    snap = snapshot_date or today()
    out = {"productos": 0, "paquetes": 0, "puntos": 0,
           "sin_vectores": [], "catalogo": 0}

    # ---- 1. el catálogo, por HTTP (R4): metadatos y sonda de vida
    st, body = fetch(ACCION_URL, note=f"sertit acción {ACCION}",
                     snapshot_name=f"sertit_cartoaction_{ACCION}.html", conn=conn)
    if st != 200 or not body:
        # Una caída de red NO es un silencio de la fuente. Antes esto seguía
        # adelante con el catálogo vacío y lo archivaba como «0 productos»: el
        # archivo habría afirmado que SERTIT dejó de publicar el día que
        # fallara la red. En un proyecto que mide silencios, confundir los dos
        # es el peor error posible (R3 aplicado al archivo).
        out["error_catalogo"] = st
        conn.commit()
        if own:
            conn.close()
        return out
    catalogo = productos_de_pagina(body)
    out["catalogo"] = len(catalogo)
    if not catalogo:
        # El cuerpo llegó y no se pudo leer: cambió el contrato. El HTML queda
        # archivado igual —arriba— para poder comparar contra él.
        out["error_catalogo"] = "js_data ilegible"

    # ---- 2. los vectores, del archivo: cada ZIP con su fila de entrega
    por_nombre = {p["nombre_base"]: p for p in catalogo if p.get("nombre_base")}
    for ruta in _paquetes_archivados():
        base = ruta.name.replace("_vectors.zip", "")
        meta = por_nombre.get(base)
        if meta is None:
            # El nombre del ZIP y el del catálogo pueden divergir (la fuente
            # renombra); se casa por municipio antes de darlo por huérfano.
            muni, _ = _municipio_de_nombre(base)
            meta = next((p for p in catalogo if p["municipio"] == muni), None)
        # La entrega se registra UNA vez, no cada día. Si se re-registrara en
        # cada corrida, dentro de un año el log afirmaría que SERTIT entregó
        # cinco ZIP todos los días —sucesos que no ocurrieron— con una nota que
        # sigue diciendo «entrega 2026-08-21». Comprobar a diario que el cuerpo
        # sigue íntegro es trabajo del test, no del log.
        import hashlib
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        ya = conn.execute(
            "SELECT 1 FROM sources_log WHERE sha256=? AND snapshot_path=?",
            (sha, str(ruta.relative_to(DATA.parent)))).fetchone()
        if not ya:
            sha = registrar_entrega(
                conn, url=(meta or {}).get("url_producto")
                or f"{BASE}/cartographie-rapide/cartoaction/{ACCION}/",
                ruta=ruta,
                note="vectores de ICube-SERTIT recibidos por correo el"
                     " 2026-08-21, tras solicitud del 2026-08-20")
        datos = paquete(ruta.read_bytes())
        out["paquetes"] += 1
        muni = (meta or {}).get("municipio") or _municipio_de_nombre(base)[0]
        depto = MUNICIPIOS.get(muni, {}).get("departamento") if muni else None
        for pt in datos["puntos"]:
            conn.execute(
                "INSERT INTO sertit_danos (paquete_sha, capa, idx, producto_id,"
                " municipio, departamento, dano, tipo, sensor, sensor_date,"
                " metodo, copyright, lat, lon, first_seen, snapshot_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "  COALESCE((SELECT first_seen FROM sertit_danos"
                "            WHERE paquete_sha=? AND capa=? AND idx=?), ?), ?)"
                " ON CONFLICT(paquete_sha, capa, idx) DO UPDATE SET"
                "  municipio=excluded.municipio,"
                "  departamento=excluded.departamento,"
                "  producto_id=excluded.producto_id,"
                "  snapshot_date=excluded.snapshot_date",
                (sha, pt["capa"], pt["idx"], (meta or {}).get("producto_id"),
                 muni, depto, pt["dano"], pt["tipo"], pt["sensor"],
                 pt["sensor_date"], pt["metodo"], pt["copyright"],
                 pt["lat"], pt["lon"],
                 sha, pt["capa"], pt["idx"], utcnow(), snap))
            out["puntos"] += 1
        if meta is not None:
            meta["paquete_sha256"] = sha
            meta["paquete_ruta"] = str(ruta.relative_to(DATA.parent))
            meta["area_analizada_km2"] = datos["area_km2"]

    # ---- 3. el catálogo a la base, ya con el paquete que le corresponde
    for p in catalogo:
        if "paquete_sha256" not in p:
            out["sin_vectores"].append(p.get("municipio") or p["producto_id"])
        depto = MUNICIPIOS.get(p["municipio"], {}).get("departamento") \
            if p.get("municipio") else None
        conn.execute(
            "INSERT INTO sertit_productos (producto_id, accion_id, charter,"
            " n_producto, nombre_base, municipio, departamento, municipio_origen,"
            " escala, formato, tipo, imagen_principal, fecha_produccion,"
            " url_producto, url_mapa, cifra_rotulada,"
            " bbox_declarado, area_analizada_km2, paquete_sha256, paquete_ruta,"
            " first_seen, snapshot_date)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "  COALESCE((SELECT first_seen FROM sertit_productos"
            "            WHERE producto_id=?), ?), ?)"
            " ON CONFLICT(producto_id) DO UPDATE SET"
            "  nombre_base=excluded.nombre_base, escala=excluded.escala,"
            # La atribución del municipio también se actualiza: si mañana se
            # afina el criterio, la fila vieja no puede quedarse con el
            # resultado del criterio viejo sin que nadie lo note.
            "  municipio=excluded.municipio, departamento=excluded.departamento,"
            "  municipio_origen=excluded.municipio_origen,"
            "  imagen_principal=excluded.imagen_principal,"
            "  fecha_produccion=excluded.fecha_produccion,"
            "  url_producto=excluded.url_producto, url_mapa=excluded.url_mapa,"
            "  cifra_rotulada=excluded.cifra_rotulada,"
            "  bbox_declarado=excluded.bbox_declarado,"
            "  area_analizada_km2=COALESCE(excluded.area_analizada_km2,"
            "                              sertit_productos.area_analizada_km2),"
            "  paquete_sha256=COALESCE(excluded.paquete_sha256,"
            "                          sertit_productos.paquete_sha256),"
            "  paquete_ruta=COALESCE(excluded.paquete_ruta,"
            "                        sertit_productos.paquete_ruta),"
            "  snapshot_date=excluded.snapshot_date",
            (p["producto_id"], p["accion_id"], p["charter"], p["n_producto"],
             p["nombre_base"], p["municipio"], depto, p["municipio_origen"],
             p["escala"], p["formato"], p["tipo"], p["imagen_principal"],
             p["fecha_produccion"], p.get("url_producto"), p.get("url_mapa"),
             p.get("cifra_rotulada"), p["bbox_declarado"],
             p.get("area_analizada_km2"), p.get("paquete_sha256"),
             p.get("paquete_ruta"), p["producto_id"], utcnow(), snap))
        out["productos"] += 1

    conn.commit()
    out["exportados"] = export(conn)
    if own:
        conn.close()
    return out


def paquetes_vigentes(conn) -> set[str]:
    """El sha del paquete que hoy representa a cada producto.

    La fuente reedita sin cambiar el id del producto: lo que cambia es el ZIP.
    Sin este filtro, el día de la primera reedición el geojson publicaría la
    versión vieja y la nueva a la vez y el mapa contaría dos veces los mismos
    tejados. Los paquetes anteriores se quedan en la base como histórico —el
    archivo no pierde nada— pero no se publican. Mismo criterio que
    `unosat.paquete_vigente()`.
    """
    return {sha for (sha,) in conn.execute(
        "SELECT paquete_sha256 FROM sertit_productos"
        " WHERE paquete_sha256 IS NOT NULL")}


def export(conn) -> int:
    """`data/public/sertit_damage.geojson` — lo que lee el mapa.

    Sale de la base y no del ZIP en memoria, para que el export sobreviva a una
    corrida en la que sertit.unistra.fr no responda (R13). El `copyright` viaja
    en cada punto porque la licencia obliga a atribuir allí donde se publique
    el dato, no solo en el pie del sitio.
    """
    vigentes = paquetes_vigentes(conn)
    if not vigentes:
        return 0
    marcas = ",".join("?" * len(vigentes))
    feats = []
    for r in conn.execute(
            "SELECT lon, lat, municipio, departamento, dano, tipo, sensor,"
            " sensor_date, metodo, copyright, producto_id, capa"
            " FROM sertit_danos WHERE lon IS NOT NULL AND lat IS NOT NULL"
            f" AND paquete_sha IN ({marcas})"
            " ORDER BY municipio, capa, idx", tuple(vigentes)):
        props = {
            "municipio": r[2], "departamento": r[3], "dano": r[4],
            "tipo": r[5], "sensor": r[6], "sensor_date": r[7],
            "metodo": r[8], "copyright": r[9],
            "producto_id": r[10], "capa": r[11],
        }
        # Un campo sin dato no viaja: el globo del mapa no puede pintar un
        # guion y hacer creer que la fuente dijo algo.
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [r[0], r[1]]},
                      "properties": {k: v for k, v in props.items()
                                     if v not in (None, "")}})
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "sertit_damage.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    return len(feats)


def resumen(conn) -> dict:
    """Conteo por municipio y grado, para los agregados de publish."""
    res: dict = {}
    vigentes = paquetes_vigentes(conn)
    if not vigentes:
        return res
    marcas = ",".join("?" * len(vigentes))
    for muni, dano, n in conn.execute(
            "SELECT municipio, dano, COUNT(*) FROM sertit_danos"
            f" WHERE paquete_sha IN ({marcas})"
            " GROUP BY municipio, dano", tuple(vigentes)):
        if not muni:
            continue
        d = res.setdefault(muni, {"edificios": 0, "sin_grado": 0,
                                  "por_grado": {}})
        # `Not Applicable` es un punto que SERTIT marcó y NO clasificó. Contarlo
        # como «daño clasificado» sería afirmar lo que la fuente no dijo — el
        # mismo cuidado que se tuvo con los 8 puntos de código imposible de
        # UNOSAT. Se cuenta aparte, no se descarta: el punto existe y se pinta.
        if (dano or "").lower().startswith("not applicable"):
            d["sin_grado"] += n
        else:
            d["edificios"] += n
        d["por_grado"][dano or "sin grado"] = n
    for muni, area, fecha in conn.execute(
            "SELECT municipio, area_analizada_km2, imagen_principal"
            " FROM sertit_productos WHERE municipio IS NOT NULL"):
        if muni in res:
            res[muni]["area_km2"] = area
            res[muni]["imagen"] = fecha
    return res
