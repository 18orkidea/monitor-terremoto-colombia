"""Municipios dentro del área de influencia del sismo.

No son AOIs Copernicus. Esta capa existe para no perder ciudades mencionadas
por prensa o con intensidad percibida, aunque no hayan sido mapeadas por satélite.
"""
from __future__ import annotations

import math
import re
import unicodedata

from geo import point_in_wkt_polygon


MUNICIPIOS = {
    "Armenia": {"departamento": "Quindío", "lat": 4.5339, "lon": -75.6811,
                "toponimos": ["armenia"]},
    "Calarcá": {"departamento": "Quindío", "lat": 4.5295, "lon": -75.6409,
                "toponimos": ["calarca"]},
    "La Tebaida": {"departamento": "Quindío", "lat": 4.4524, "lon": -75.7875,
                   "toponimos": ["la tebaida"]},
    "Montenegro": {"departamento": "Quindío", "lat": 4.5669, "lon": -75.7511,
                   "toponimos": ["montenegro"]},
    "Salento": {"departamento": "Quindío", "lat": 4.6375, "lon": -75.5703,
                "toponimos": ["salento"]},
    "Zarzal": {"departamento": "Valle del Cauca", "lat": 4.3946, "lon": -76.0715,
               "toponimos": ["zarzal"]},
    "Cartago": {"departamento": "Valle del Cauca", "lat": 4.7464, "lon": -75.9117,
                "toponimos": ["cartago"]},
    "Tuluá": {"departamento": "Valle del Cauca", "lat": 4.0847, "lon": -76.1954,
              "toponimos": ["tulua"]},
    "Buga": {"departamento": "Valle del Cauca", "lat": 3.9009, "lon": -76.2978,
             "toponimos": ["buga", "guadalajara de buga"]},
    "Palmira": {"departamento": "Valle del Cauca", "lat": 3.5394, "lon": -76.3036,
                "toponimos": ["palmira"]},
    "Roldanillo": {"departamento": "Valle del Cauca", "lat": 4.4126, "lon": -76.1546,
                   "toponimos": ["roldanillo"]},
    "Sevilla": {"departamento": "Valle del Cauca", "lat": 4.2643, "lon": -75.9309,
                "toponimos": ["sevilla"]},
    "Caicedonia": {"departamento": "Valle del Cauca", "lat": 4.3324, "lon": -75.8267,
                   "toponimos": ["caicedonia"]},
    "Jamundí": {"departamento": "Valle del Cauca", "lat": 3.2607, "lon": -76.5349,
                "toponimos": ["jamundi"]},
    "Dagua": {"departamento": "Valle del Cauca", "lat": 3.6569, "lon": -76.6886,
              "toponimos": ["dagua"]},
    "Pereira": {"departamento": "Risaralda", "lat": 4.8143, "lon": -75.6946,
                "toponimos": ["pereira"]},
    "Dosquebradas": {"departamento": "Risaralda", "lat": 4.8347, "lon": -75.6725,
                     "toponimos": ["dos quebradas", "dosquebradas"]},
    "Santa Rosa de Cabal": {"departamento": "Risaralda", "lat": 4.8681, "lon": -75.6214,
                            "toponimos": ["santa rosa de cabal"]},
    "Manizales": {"departamento": "Caldas", "lat": 5.0703, "lon": -75.5138,
                  "toponimos": ["manizales"]},
    "Villamaría": {"departamento": "Caldas", "lat": 5.0449, "lon": -75.5146,
                   "toponimos": ["villamaria"]},
    "Cali": {"departamento": "Valle del Cauca", "lat": 3.4516, "lon": -76.5320,
             "toponimos": ["cali"]},
    "Buenaventura": {"departamento": "Valle del Cauca", "lat": 3.8801, "lon": -77.0312,
                     "toponimos": ["buenaventura"]},
    "Quibdó": {"departamento": "Chocó", "lat": 5.6947, "lon": -76.6611,
               "toponimos": ["quibdo"]},
    "Istmina": {"departamento": "Chocó", "lat": 5.1605, "lon": -76.6830,
                "toponimos": ["istmina"]},
    "San José del Palmar": {"departamento": "Chocó", "lat": 4.9740, "lon": -76.2280,
                            "toponimos": ["san jose del palmar"]},
    # --- municipios del RUD (UNGRD) sin cobertura previa de prensa/DYFI ---
    # coordenadas: DIVIPOLA geolocalizado (datos.gov.co, dataset gdxc-w37w)
    "Anserma": {"departamento": "Caldas", "lat": 5.236471, "lon": -75.784343,
               "toponimos": ["anserma"]},
    "Aranzazu": {"departamento": "Caldas", "lat": 5.271195, "lon": -75.49129,
                "toponimos": ["aranzazu"]},
    "Belalcázar": {"departamento": "Caldas", "lat": 4.993785, "lon": -75.811918,
                  "toponimos": ["belalcazar"],
                  "requiere_depto": True},
    "Chinchiná": {"departamento": "Caldas", "lat": 4.985227, "lon": -75.607529,
                 "toponimos": ["chinchina"]},
    "Filadelfia": {"departamento": "Caldas", "lat": 5.297091, "lon": -75.562474,
                  "toponimos": ["filadelfia"],
                  "requiere_depto": True},
    "Marulanda": {"departamento": "Caldas", "lat": 5.284304, "lon": -75.259721,
                 "toponimos": ["marulanda"],
                 "requiere_depto": True},
    "Palestina": {"departamento": "Caldas", "lat": 5.017879, "lon": -75.624577,
                 "toponimos": ["palestina"],
                 "requiere_depto": True},
    "Pensilvania": {"departamento": "Caldas", "lat": 5.383281, "lon": -75.160299,
                   "toponimos": ["pensilvania"],
                   "requiere_depto": True},
    "Riosucio (Caldas)": {"departamento": "Caldas", "lat": 5.423673, "lon": -75.702104,
                         "toponimos": ["riosucio"],
                         "requiere_depto": True},
    "Risaralda": {"departamento": "Caldas", "lat": 5.164509, "lon": -75.76722,
                 "toponimos": ["risaralda"],
                 "homonimo_de_departamento": True},
    # topónimo con coma a propósito: «san jose» a secas casaría dentro de «San
    # José del Palmar» (Chocó, el epicentro), que aparece en cientos de
    # titulares. Se prefiere perder cobertura antes que atribuir el epicentro a
    # un municipio de Caldas — ver test_san_jose_no_captura_al_epicentro.
    "San José": {"departamento": "Caldas", "lat": 5.08231, "lon": -75.792063,
                "toponimos": ["san jose, caldas"],
                "requiere_depto": True},
    # Alta el 19-ago-2026: entró por UNOSAT, que evaluó allí 154 edificios (55
    # con daño observado, el mayor recuento de su paquete) sin que el municipio
    # tuviera una sola fila en el RUD ni figurara en esta capa.
    # `requiere_depto` por partida doble: «Viterbo» es una ciudad italiana —la
    # única mención del corpus es un titular en italiano que la llama «l'altra
    # Viterbo»— y además casa dentro de «Santa Rosa de Viterbo», que es de
    # Boyacá. Sin «Caldas» en el texto no se le atribuye prensa.
    "Viterbo": {"departamento": "Caldas", "lat": 5.062664, "lon": -75.87061,
               "toponimos": ["viterbo"],
               "requiere_depto": True},
    "Acandí": {"departamento": "Chocó", "lat": 8.512178, "lon": -77.279951,
              "toponimos": ["acandi"]},
    "Alto Baudó": {"departamento": "Chocó", "lat": 5.516221, "lon": -76.974373,
                  "toponimos": ["alto baudo"]},
    "Bagadó": {"departamento": "Chocó", "lat": 5.409681, "lon": -76.416063,
              "toponimos": ["bagado"]},
    "Bahía Solano": {"departamento": "Chocó", "lat": 6.222807, "lon": -77.401359,
                    "toponimos": ["bahia solano"]},
    "Bajo Baudó": {"departamento": "Chocó", "lat": 4.954576, "lon": -77.365717,
                  "toponimos": ["bajo baudo"]},
    "Condoto": {"departamento": "Chocó", "lat": 5.091003, "lon": -76.650683,
               "toponimos": ["condoto"]},
    "El Carmen de Atrato": {"departamento": "Chocó", "lat": 5.899789, "lon": -76.142112,
                           "toponimos": ["el carmen de atrato"]},
    "El Litoral del San Juan": {"departamento": "Chocó", "lat": 4.259564, "lon": -77.363702,
                               "toponimos": ["el litoral del san juan"]},
    "Lloró": {"departamento": "Chocó", "lat": 5.49789, "lon": -76.545147,
             "toponimos": ["lloro"]},
    "Medio Atrato": {"departamento": "Chocó", "lat": 5.994935, "lon": -76.783042,
                    "toponimos": ["medio atrato"]},
    "Medio Baudó": {"departamento": "Chocó", "lat": 5.192471, "lon": -76.950891,
                   "toponimos": ["medio baudo"]},
    "Medio San Juan": {"departamento": "Chocó", "lat": 5.098291, "lon": -76.694409,
                      "toponimos": ["medio san juan"]},
    "Nuquí": {"departamento": "Chocó", "lat": 5.709812, "lon": -77.265507,
             "toponimos": ["nuqui"]},
    "Nóvita": {"departamento": "Chocó", "lat": 4.956063, "lon": -76.609467,
              "toponimos": ["novita"]},
    "Riosucio (Chocó)": {"departamento": "Chocó", "lat": 7.436704, "lon": -77.113156,
                        "toponimos": ["riosucio"],
                        "requiere_depto": True},
    "Río Iró": {"departamento": "Chocó", "lat": 5.1863, "lon": -76.472925,
               "toponimos": ["rio iro"]},
    "Sipí": {"departamento": "Chocó", "lat": 4.65262, "lon": -76.643453,
            "toponimos": ["sipi"]},
    "Tadó": {"departamento": "Chocó", "lat": 5.264873, "lon": -76.558571,
            "toponimos": ["tado"]},
    "Córdoba": {"departamento": "Quindío", "lat": 4.392485, "lon": -75.687866,
               "toponimos": ["cordoba"],
               "homonimo_de_departamento": True},
    "Apía": {"departamento": "Risaralda", "lat": 5.106526, "lon": -75.942356,
            "toponimos": ["apia"]},
    "Balboa": {"departamento": "Risaralda", "lat": 4.949096, "lon": -75.958663,
              "toponimos": ["balboa"],
              "requiere_depto": True},
    "Belén de Umbría": {"departamento": "Risaralda", "lat": 5.200793, "lon": -75.868334,
                       "toponimos": ["belen de umbria"]},
    "Guática": {"departamento": "Risaralda", "lat": 5.315367, "lon": -75.799005,
               "toponimos": ["guatica"]},
    "La Celia": {"departamento": "Risaralda", "lat": 5.002787, "lon": -76.0032,
                "toponimos": ["la celia"]},
    "La Virginia": {"departamento": "Risaralda", "lat": 4.896624, "lon": -75.880394,
                   "toponimos": ["la virginia"],
                   "requiere_depto": True},
    "Marsella": {"departamento": "Risaralda", "lat": 4.935771, "lon": -75.73879,
                "toponimos": ["marsella"],
                "requiere_depto": True},
    "Mistrató": {"departamento": "Risaralda", "lat": 5.297039, "lon": -75.882886,
                "toponimos": ["mistrato"]},
    "Pueblo Rico": {"departamento": "Risaralda", "lat": 5.222043, "lon": -76.030801,
                   "toponimos": ["pueblo rico"]},
    "Quinchía": {"departamento": "Risaralda", "lat": 5.340456, "lon": -75.730431,
                "toponimos": ["quinchia"]},
    "Santuario": {"departamento": "Risaralda", "lat": 5.074911, "lon": -75.964628,
                 "toponimos": ["santuario"],
                 "requiere_depto": True},
    "Alcalá": {"departamento": "Valle del Cauca", "lat": 4.674994, "lon": -75.779792,
              "toponimos": ["alcala"],
              "requiere_depto": True},
    "Andalucía": {"departamento": "Valle del Cauca", "lat": 4.171713, "lon": -76.167925,
                 "toponimos": ["andalucia"],
                 "requiere_depto": True},
    "Ansermanuevo": {"departamento": "Valle del Cauca", "lat": 4.794984, "lon": -75.992003,
                    "toponimos": ["ansermanuevo"]},
    "Candelaria": {"departamento": "Valle del Cauca", "lat": 3.408354, "lon": -76.346519,
                  "toponimos": ["candelaria"],
                  "requiere_depto": True},
    "El Dovio": {"departamento": "Valle del Cauca", "lat": 4.510452, "lon": -76.237084,
                "toponimos": ["el dovio"]},
    "El Águila": {"departamento": "Valle del Cauca", "lat": 4.906062, "lon": -76.042779,
                 "toponimos": ["el aguila"]},
    "Ginebra": {"departamento": "Valle del Cauca", "lat": 3.724181, "lon": -76.268068,
               "toponimos": ["ginebra"],
               "requiere_depto": True},
    "Guacarí": {"departamento": "Valle del Cauca", "lat": 3.761815, "lon": -76.330911,
               "toponimos": ["guacari"]},
    "La Cumbre": {"departamento": "Valle del Cauca", "lat": 3.649268, "lon": -76.56805,
                 "toponimos": ["la cumbre"],
                 "requiere_depto": True},
    "La Victoria": {"departamento": "Valle del Cauca", "lat": 4.523603, "lon": -76.036529,
                   "toponimos": ["la victoria"],
                   "requiere_depto": True},
    "Obando": {"departamento": "Valle del Cauca", "lat": 4.575712, "lon": -75.974709,
              "toponimos": ["obando"],
              "requiere_depto": True},
    "Restrepo": {"departamento": "Valle del Cauca", "lat": 3.821351, "lon": -76.523329,
                "toponimos": ["restrepo"],
                "requiere_depto": True},
    "San Pedro": {"departamento": "Valle del Cauca", "lat": 3.995073, "lon": -76.228692,
                 "toponimos": ["san pedro"],
                 "requiere_depto": True},
    "Toro": {"departamento": "Valle del Cauca", "lat": 4.608085, "lon": -76.076859,
            "toponimos": ["toro"],
            "requiere_depto": True},
    "Ulloa": {"departamento": "Valle del Cauca", "lat": 4.703623, "lon": -75.737808,
             "toponimos": ["ulloa"],
             "requiere_depto": True},
    "Versalles": {"departamento": "Valle del Cauca", "lat": 4.575019, "lon": -76.199203,
                 "toponimos": ["versalles"],
                 "requiere_depto": True},
    "Yotoco": {"departamento": "Valle del Cauca", "lat": 3.861241, "lon": -76.382698,
              "toponimos": ["yotoco"]},
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _mentioned(text: str, tops: list[str]) -> bool:
    n = _norm(text)
    return any(re.search(rf"\b{re.escape(t)}\b", n) for t in tops)


def _menciona_municipio(text: str, meta: dict) -> bool:
    """R10 ampliada, en dos niveles.

    `requiere_depto`: topónimos que también son palabra común, lugar extranjero
    conocido, apellido frecuente o nombre repetido en dos departamentos (Toro,
    Palestina, Marulanda, Riosucio…) exigen que el texto nombre además el
    departamento. Sin ese contexto, «el ministro Restrepo» contaría como prensa
    del municipio de Restrepo, Valle.

    `homonimo_de_departamento`: cuando el municipio se llama igual que un
    departamento (Risaralda en Caldas, Córdoba en Quindío) el texto libre no
    puede distinguirlos — medido sobre el corpus, «Caldas y Risaralda» siempre
    era el departamento, y ni exigir adyacencia lo salvaba. Estos municipios NO
    reciben prensa por texto: entran por el RUD, y la vía fiable para su prensa
    es el feed municipal, que declara su municipio explícitamente."""
    if meta.get("homonimo_de_departamento"):
        return False
    if not _mentioned(text, meta["toponimos"]):
        return False
    if not meta.get("requiere_depto"):
        return True
    return _mentioned(text, [_norm(meta["departamento"])])


def match_municipios_text(text: str) -> list[str]:
    return [mun for mun, meta in MUNICIPIOS.items()
            if _menciona_municipio(text, meta)]


def match_departamentos_text(text: str, municipios: list[str] | None = None) -> list[str]:
    found = {MUNICIPIOS[m]["departamento"] for m in (municipios or [])
             if m in MUNICIPIOS}
    n = _norm(text)
    for meta in MUNICIPIOS.values():
        depto = meta["departamento"]
        if re.search(rf"\b{re.escape(_norm(depto))}\b", n):
            found.add(depto)
    return sorted(found)


def _dyfi_municipio(name: str) -> str:
    m = re.search(r"<br>([^<]+)$", name or "")
    return m.group(1).strip() if m else (name or "").strip()


# Radio máximo entre el centro de una celda DYFI y el municipio al que se le
# atribuye. Las celdas son de ~10 km y el USGS las etiqueta con el topónimo más
# cercano —de cualquier país—, así que un nombre repetido lejos es otro lugar:
# la celda «Balboa» del canal de Panamá se estaba publicando como intensidad
# sentida en Balboa (Risaralda), a 595 km. Las 36 atribuciones legítimas del
# corpus caben en 15 km.
DYFI_RADIO_KM = 30.0


def _centro_celda(feature: dict) -> tuple[float, float] | None:
    """Centro aproximado de la celda (media del anillo): basta para descartar
    otro continente, que es lo que se busca."""
    geom = (feature or {}).get("geometry") or {}
    coords = geom.get("coordinates")
    anillo = coords[0] if geom.get("type") == "Polygon" and coords else None
    if not anillo:
        return None
    puntos = [p for p in anillo if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not puntos:
        return None
    return (sum(p[1] for p in puntos) / len(puntos),
            sum(p[0] for p in puntos) / len(puntos))


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km sobre la esfera (haversine, stdlib — R14)."""
    r = 6371.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = f2 - f1
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _pop_key(municipio: str, departamento: str) -> str:
    return f"{_norm(municipio)}|{_norm(departamento)}"


def _admin_norm(s: str) -> str:
    """Nombre administrativo comparable entre catálogos.

    No se puede ampliar `_norm`: los topónimos de prensa conservan puntuación a
    propósito (por ejemplo, «san jose, caldas» evita capturar el epicentro). En
    los catálogos oficiales, en cambio, `SOTARÁ - PAISPAMBA` y
    `Sotará Paispamba` identifican la misma entidad.
    """
    return re.sub(r"[^a-z0-9]+", " ", _norm(s)).strip()


def _divipola_key(value) -> str:
    value = str(value or "").strip()
    return value.zfill(5) if value.isdigit() else value


def _find_divipola(divipola: dict | None, municipio: str,
                    departamento: str) -> dict | None:
    """Resuelve un municipio en el catálogo geográfico sin inventar alias.

    Primero conserva la ruta exacta. Si dos fuentes difieren solo en
    puntuación, acepta el resultado únicamente cuando la forma administrativa
    normalizada es única dentro del departamento.
    """
    if not divipola:
        return None
    exact = divipola.get(_pop_key(municipio, departamento))
    if exact:
        return exact
    mun_n, dep_n = _admin_norm(municipio), _admin_norm(departamento)
    candidatos = []
    for raw_key, row in divipola.items():
        key_mun, _, key_dep = raw_key.partition("|")
        row_mun = row.get("municipio") or key_mun
        row_dep = row.get("departamento") or key_dep
        if (_admin_norm(row_mun), _admin_norm(row_dep)) == (mun_n, dep_n):
            candidatos.append(row)
    return candidatos[0] if len(candidatos) == 1 else None


def _find_population(poblacion: dict | None, municipio: str, meta: dict,
                     divipola: dict | None = None) -> dict | None:
    if not poblacion:
        return None
    departamento = meta["departamento"]
    names = [municipio, *meta.get("toponimos", [])]
    for name in names:
        pop = poblacion.get(_pop_key(name, departamento))
        if pop:
            return pop
    # Los nombres oficiales también cambian: DANE aún publica «Mariquita» y
    # DIVIPOLA ya publica «San Sebastián de Mariquita». El código municipal es
    # la identidad estable que permite unirlos sin una tabla manual de alias.
    code = meta.get("divipola")
    if not code and divipola:
        div = _find_divipola(divipola, municipio, departamento)
        code = div.get("divipola") if div else None
    if code:
        code_n = _divipola_key(code)
        candidatos = [row for row in poblacion.values()
                      if _divipola_key(row.get("divipola")) == code_n]
        if len(candidatos) == 1:
            return candidatos[0]
    return None


def _find_rud(rud_municipios: dict | None, municipio: str, meta: dict) -> dict | None:
    """Fila RUD del municipio, probando nombre y topónimos (claves como
    'Riosucio (Caldas)' no existen en el RUD; su topónimo sí)."""
    if not rud_municipios:
        return None
    dep = _norm(meta["departamento"])
    for name in [municipio, *meta.get("toponimos", [])]:
        row = rud_municipios.get((dep, _norm(name)))
        if row:
            return row
    return None


_LOWER_WORDS = {"de", "del", "la", "el", "los", "las", "y"}


def _title_es(s: str) -> str:
    words = (s or "").strip().split()
    return " ".join(w.lower() if i > 0 and w.lower() in _LOWER_WORDS
                    else w.lower()[:1].upper() + w.lower()[1:]
                    for i, w in enumerate(words))


def municipios_dinamicos(rud_municipios: dict | None,
                         divipola: dict | None) -> dict[str, dict]:
    """Entradas para municipios que el RUD registra pero MUNICIPIOS no cura
    aún: el registro oficial manda — si un municipio entra al RUD mañana, no
    puede perderse por falta de mantenimiento manual. Coordenadas del catálogo
    DIVIPOLA estático; sin coordenadas la entrada sale igual (sin punto en el
    mapa) y el test de supuesto avisa."""
    if not rud_municipios:
        return {}
    cubiertos = set()
    for mun, meta in MUNICIPIOS.items():
        dep = _admin_norm(meta["departamento"])
        for name in [mun, *meta.get("toponimos", [])]:
            cubiertos.add((dep, _admin_norm(name)))
    # nombres de departamento del propio catálogo: un municipio que se llame
    # como uno de ellos nace ya marcado, sin esperar a que alguien lo cure
    deptos = {_norm(v.get("departamento")) for v in (divipola or {}).values()}
    extras = {}
    for (dep_n, mun_n), fila in rud_municipios.items():
        if (_admin_norm(dep_n), _admin_norm(mun_n)) in cubiertos:
            continue
        departamento = fila.get("departamento") or dep_n
        municipio = fila.get("municipio") or mun_n
        div = _find_divipola(divipola, municipio, departamento)
        nombre = _title_es(fila.get("municipio") or mun_n)
        key = nombre if nombre not in MUNICIPIOS and nombre not in extras \
            else f"{nombre} ({_title_es(fila.get('departamento') or dep_n)})"
        extras[key] = {
            "departamento": _title_es(departamento),
            "divipola": div.get("divipola") if div else None,
            "lat": div.get("lat") if div else None,
            "lon": div.get("lon") if div else None,
            "toponimos": [mun_n],
            # nadie ha revisado este topónimo todavía: si resulta ser palabra
            # común o apellido, exigir contexto evita atribuirle prensa ajena.
            # Al curarlo a mano se puede relajar.
            "requiere_depto": True,
            # y si además se llama como un departamento, el texto libre no
            # puede distinguirlos: no recibe prensa por texto en absoluto
            "homonimo_de_departamento": mun_n in deptos,
        }
    return extras


def build_municipios(noticias: list[dict], dyfi: dict | None,
                     aoi_extents: dict[str, str],
                     poblacion: dict | None = None,
                     rud_municipios: dict | None = None,
                     divipola: dict | None = None,
                     unosat: dict | None = None,
                     con_busqueda_propia: set[str] | None = None,
                     *, sertit: dict | None = None,
                     grid_mmi=None) -> tuple[list[dict], dict]:
    catalogo = {**MUNICIPIOS, **municipios_dinamicos(rud_municipios, divipola)}
    out = {m: {"municipio": m, **meta, "n_noticias": 0,
               "noticias_ejemplo": [], "dyfi_max_cdi": None,
               "dyfi_respuestas": 0, "dyfi_celdas": 0, "dyfi_min_dist_km": None}
           for m, meta in catalogo.items()}

    for mun, row in out.items():
        pop = _find_population(poblacion, mun, row, divipola)
        if pop:
            row["divipola"] = pop.get("divipola") or row.get("divipola")
            row["poblacion_2026"] = pop.get("poblacion_2026")
            row["cabecera_2026"] = pop.get("cabecera_2026")
            row["rural_2026"] = pop.get("rural_2026")
            row["poblacion_fuente"] = "DANE PPED municipal por área 2018-2042"
        else:
            row["divipola"] = row.get("divipola")
            row["poblacion_2026"] = None
            row["cabecera_2026"] = None
            row["rural_2026"] = None
            row["poblacion_fuente"] = None

    for n in noticias:
        text = f"{n.get('titulo') or ''} {n.get('medio') or ''}"
        for mun, meta in catalogo.items():
            if _menciona_municipio(text, meta):
                row = out[mun]
                row["n_noticias"] += 1
                if len(row["noticias_ejemplo"]) < 3:
                    row["noticias_ejemplo"].append({
                        "fecha": n.get("fecha"), "medio": n.get("medio"),
                        "titulo": n.get("titulo"), "url": n.get("url")})

    for f in (dyfi or {}).get("features", []):
        p = f.get("properties") or {}
        raw_mun = _dyfi_municipio(p.get("name"))
        key = _norm(raw_mun)
        # DYFI da el municipio sin departamento: si el nombre corresponde a
        # más de un municipio (Riosucio está en Caldas y en Chocó), no se
        # atribuye a ninguno — elegir uno por orden del diccionario sería
        # inventar la atribución.
        candidatos = [m for m, meta in catalogo.items()
                      if key in meta["toponimos"] or _norm(m) == key]
        if len(candidatos) != 1:
            continue
        mun = candidatos[0]
        # ...y el nombre tampoco basta: el USGS etiqueta con el topónimo más
        # cercano del mundo. Sin la celda al lado del municipio no hay
        # atribución (este canal no pasa por _menciona_municipio).
        centro = _centro_celda(f)
        meta = catalogo[mun]
        # sin geometría o sin coordenadas del municipio no se puede medir: se
        # atribuye por nombre (comportamiento previo), porque hoy el DYFI trae
        # siempre polígono y los 83 municipios tienen lat/lon
        if centro and meta.get("lat") is not None:
            if _km(meta["lat"], meta["lon"], *centro) > DYFI_RADIO_KM:
                continue
        row = out[mun]
        cdi, nresp, dist = p.get("cdi"), p.get("nresp"), p.get("dist")
        if isinstance(cdi, (int, float)):
            row["dyfi_max_cdi"] = max(row["dyfi_max_cdi"] or cdi, cdi)
        if isinstance(nresp, (int, float)):
            row["dyfi_respuestas"] += nresp
        if isinstance(dist, (int, float)):
            row["dyfi_min_dist_km"] = min(row["dyfi_min_dist_km"] or dist, dist)
        row["dyfi_celdas"] += 1

    features, rows = [], []
    for mun, row in out.items():
        tiene_dyfi = row["dyfi_max_cdi"] is not None
        tiene_prensa = row["n_noticias"] > 0
        rud = _find_rud(rud_municipios, mun, row)
        tiene_rud = rud is not None
        # `is not None`, NO truthiness: haber mirado y no haber encontrado
        # edificios con grado de daño es un resultado, no una ausencia de
        # evaluación (R3 leído al revés). Con `bool()`, un municipio donde
        # SERTIT solo marcó puntos sin grado —edificios = 0— figuraba como no
        # evaluado, y la capa de la ausencia llegaba a decirle al lector que
        # nadie lo había mirado. Publicar eso es peor que no publicar nada.
        uno = (unosat or {}).get(mun)
        tiene_unosat = uno is not None and uno.get("edificios") is not None
        ser = (sertit or {}).get(mun)
        tiene_sertit = ser is not None and ser.get("edificios") is not None
        # Una evaluación satelital basta para entrar en la capa aunque no haya
        # prensa, ni DYFI, ni registro oficial: es justo el caso de Viterbo, y
        # que nadie más lo mire no es motivo para que el monitor tampoco.
        if not (tiene_prensa or tiene_dyfi or tiene_rud or tiene_unosat
                or tiene_sertit):
            continue
        lon, lat = row["lon"], row["lat"]
        en_aoi = (lon is not None and lat is not None
                  and any(point_in_wkt_polygon(lon, lat, wkt)
                          for wkt in aoi_extents.values() if wkt))
        estado = "fuera_aoi"
        if en_aoi:
            estado = "en_aoi"
        elif tiene_unosat:
            # Por debajo de Copernicus y por encima de todo lo demás: es
            # verificación satelital independiente, pero de otra clase —
            # puntos fotointerpretados que la propia UNOSAT marca «aún no
            # validado en campo», no estadísticas revisadas por AOI. Lleva
            # etiqueta propia justamente para no confundirse con la anterior.
            estado = "evaluado_unosat"
        elif tiene_sertit:
            # Mismo escalón que UNOSAT y por la misma razón: verificación
            # satelital independiente, fotointerpretada y sin validar en campo.
            # Etiqueta propia porque decir «evaluado por UNOSAT» de Roldanillo
            # —que UNOSAT no ha mirado— sería falso. El día que entre una
            # cuarta mirada habrá que unificarlas en un estado genérico; con
            # dos, nombrar a cada una cuesta menos que abstraerlas mal.
            estado = "evaluado_satelite"
        elif tiene_dyfi and (row["dyfi_max_cdi"] or 0) >= 6:
            estado = "intensidad_alta"
        elif tiene_prensa:
            estado = "mencion_prensa"
        elif tiene_rud:
            # antes exigía «and not tiene_dyfi»: una sola celda DYFI de CDI 5,6
            # mandaba al gris a Belén de Umbría, con 2.266 damnificados
            # registrados. El registro oficial pesa más que «se sintió flojo».
            estado = "solo_rud"
        row["en_aoi_copernicus"] = en_aoi
        row["estado"] = estado
        # ¿el monitor llegó a preguntar por él? Solo los municipios del catálogo
        # curado generan búsqueda propia de Google News; los que entran solos
        # desde el RUD no. Sin este dato, un cero en «Prensa» no se puede leer:
        # no distingue «la prensa no publicó» de «el monitor no preguntó».
        row["busqueda_propia"] = (con_busqueda_propia is None
                                  or mun in con_busqueda_propia)
        row["fuentes"] = [x for x, ok in (("prensa", tiene_prensa),
                                          ("dyfi", tiene_dyfi),
                                          ("rud", tiene_rud),
                                          ("unosat", tiene_unosat),
                                          ("sertit", tiene_sertit)) if ok]
        # R3: sin evaluación de UNOSAT no hay ceros, hay ausencia — un 0 se
        # leería como «el satélite miró y no vio nada», que es lo contrario
        # «observados», no «confirmados»: UNOSAT marca todos sus puntos como
        # «aún no validado en campo», y confirmar es justo lo que no hace
        row["unosat_edificios"] = uno.get("edificios") if tiene_unosat else None
        row["unosat_observados"] = uno.get("observados") if tiene_unosat else None
        row["unosat_posibles"] = uno.get("posibles") if tiene_unosat else None
        row["unosat_fecha_imagen"] = uno.get("fecha_imagen") if tiene_unosat else None
        # Edificios cuyo código de evento no cuadra con el que declara su
        # propio producto (ver publish.py). Desde el 21-ago-2026 SÍ suman —lo
        # decide el GLIDE del producto, no el campo del punto— pero se publican
        # aparte: es una discrepancia de la fuente y ocultarla sería perderla.
        row["unosat_codigo_inconsistente"] = (
            uno.get("codigo_inconsistente") or None) if tiene_unosat else None
        # SERTIT: mismo criterio de R3 que UNOSAT — sin evaluación, ausencia,
        # nunca 0. Se guarda además el área que declara haber mirado, porque
        # sin ella su cifra no se puede comparar con la de Copernicus: en
        # Pereira miró 2,78 km² y Copernicus 9,8, y son dos preguntas distintas.
        row["sertit_edificios"] = ser.get("edificios") if tiene_sertit else None
        row["sertit_destruidos"] = ser.get("destruidos") if tiene_sertit else None
        row["sertit_danados"] = ser.get("danados") if tiene_sertit else None
        row["sertit_posibles"] = ser.get("posibles") if tiene_sertit else None
        # puntos que SERTIT señaló sin asignarles grado: existen y se pintan,
        # pero no son daño clasificado y no entran en el total (R3)
        row["sertit_sin_grado"] = ser.get("sin_grado") if tiene_sertit else None
        row["sertit_area_km2"] = ser.get("area_km2") if tiene_sertit else None
        row["sertit_imagen_literal"] = ser.get("imagen_literal") if tiene_sertit else None
        # R3 en el producto descargable, no solo en la tabla: para un homónimo
        # de departamento el monitor no puede atribuir titulares, y eso es
        # ausencia de dato — quien lea el JSON no debe encontrar un 0.
        if row.get("homonimo_de_departamento"):
            row["n_noticias"] = None
        row["rud_familias"] = rud.get("familias") if rud else None
        row["rud_personas"] = rud.get("personas") if rud else None
        row["rud_viv_destruidas"] = rud.get("viv_destruidas") if rud else None
        row["rud_viv_averiadas"] = rud.get("viv_averiadas") if rud else None
        # R3: sin celda DYFI atribuida no hay cero, hay ausencia de dato — en
        # topónimos ambiguos el DYFI se descarta a propósito (ver arriba), y un
        # 0 se leería como «nadie lo sintió»
        if not row["dyfi_celdas"]:
            row["dyfi_respuestas"] = None
        # Intensidad que el modelo del USGS estima para la cabecera municipal.
        # NO es la percibida: esa es dyfi_max_cdi, que solo cubre 23 de los 196
        # municipios sin mirada satelital y no alcanza para pintar un mapa. La
        # rejilla llega al 95%, y donde no llega el valor queda en None: fuera
        # de la rejilla no hay «intensidad baja», hay ausencia de dato (R3).
        mmi = (grid_mmi.mmi_at(lon, lat)
               if grid_mmi and lon is not None and lat is not None else None)
        row["mmi_usgs"] = round(mmi, 2) if mmi is not None else None
        per, pob = row["rud_personas"], row["poblacion_2026"]
        # 4 decimales: ver nota en publish.py — un 0,0003 % redondeado a
        # 0,0 se leería como «sin damnificados»
        row["tasa_rud_pct"] = round(per / pob * 100, 4) if per and pob else None
        public_row = {k: v for k, v in row.items() if k != "toponimos"}
        rows.append(public_row)
        if lon is not None and lat is not None:
            features.append({"type": "Feature",
                             "geometry": {"type": "Point", "coordinates": [lon, lat]},
                             "properties": {k: v for k, v in public_row.items()
                                            if k not in ("lat", "lon", "toponimos")}})

    rows.sort(key=lambda r: (not r["en_aoi_copernicus"],
                             -(r.get("unosat_edificios") or 0),
                             -(r["dyfi_max_cdi"] or 0),
                             -(r["n_noticias"] or 0), r["municipio"]))
    return rows, {"type": "FeatureCollection", "features": features}


def sin_mirada_satelital(m: dict) -> bool:
    """¿Municipio con damnificados registrados al que nadie miró desde el aire?

    Los tres servicios que sigue el monitor son Copernicus EMS, UNITAR-UNOSAT e
    ICube-SERTIT. Que falten los tres no significa «sin daño»: significa que la
    evidencia de este municipio es que su alcaldía inscribió damnificados en
    el RUD (el registro lo cargan las autoridades, no los damnificados).
    Tampoco significa que ningún satélite pasara por encima: solo que ninguno
    de los tres publicó un producto de daño.

    `is not None` en las miradas, y NO truthiness: cero edificios con grado es
    un resultado de haber mirado, no una ausencia de evaluación. En las familias
    sí se exige que haya alguna: un municipio inscrito con cero familias no
    tiene damnificados que contrastar, y la capa habla de los que sí los tienen.

    «Sin mirada satelital» vive en DOS superficies —si tocas una, mira la otra—:
    aquí y en `site/municipios.js::miradoPorSatelite`. **No son la misma
    pregunta y no deben dar la misma cifra**: el JS cuenta todos los municipios
    sin producto satelital (197) y esta función solo los que además tienen
    damnificados registrados (196). El que sobra es Palmira, con prensa y DYFI
    pero sin una fila en el RUD. La diferencia es legítima; lo que no se puede
    es rotular ninguna de las dos sin su condición, que fue como la portada
    llegó a prometer 196 bajo un texto que describía las 197.
    `tests/test_unit.py::TestLasDosPreguntasSobreLaMirada`
    """
    return bool(m.get("rud_familias")) and not (
        m.get("unosat_edificios") is not None
        or m.get("sertit_edificios") is not None
        or m.get("en_aoi_copernicus"))


def capa_sin_mirada(municipios: list[dict], generado: str, grid_mmi=None) -> dict:
    """La capa de la ausencia, en su fichero propio y mínimo.

    Aparte de municipios.json porque ese pesa 340 KB por los ejemplos de prensa
    que el mapa no usa hasta que se abre un globo. Y calculada aquí, no en el
    navegador: la cifra que el sitio enseña y la que pinta tienen que salir del
    mismo sitio, o vuelven a divergir como divergieron los 36 de la portada con
    los 43 de su propia tabla.
    """
    items = [m for m in municipios if sin_mirada_satelital(m)]
    return {
        "generado": generado,
        # el rótulo viaja con el dato: quien lea el JSON no tiene que adivinar
        # que la intensidad es modelada y no sentida
        "fuente_mmi": "ShakeMap del USGS (sacudida estimada por un modelo, "
                      "no medida en el terreno ni reportada por la gente)",
        "fuente_mmi_url":
            "https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2/shakemap",
        # De QUÉ rejilla salieron estas intensidades. `grid_mmi_vigente` se cae
        # al snapshot anterior cuando la corrida del día no trae ShakeMap, así
        # que sin esto un producto fechado hoy podría llevar intensidades de
        # hace días sin que nada lo dijera (R4).
        "fuente_mmi_snapshot": getattr(grid_mmi, "origen", None),
        "total": len(items),
        # cuántos se pueden pintar: el mapa dibuja por coordenada, y un rótulo
        # que prometa más puntos de los que hay es la divergencia de siempre
        "con_coordenadas": sum(1 for m in items
                               if m.get("lat") is not None and m.get("lon") is not None),
        # se publica cuántos se quedaron sin intensidad, para que la laguna se
        # pueda contar en vez de descubrirse mirando el mapa
        "sin_mmi": sum(1 for m in items if m.get("mmi_usgs") is None),
        "items": [{"municipio": m["municipio"], "departamento": m["departamento"],
                   "lat": m.get("lat"), "lon": m.get("lon"),
                   "rud_familias": m.get("rud_familias"),
                   "rud_personas": m.get("rud_personas"),
                   "mmi_usgs": m.get("mmi_usgs")}
                  for m in items],
    }
