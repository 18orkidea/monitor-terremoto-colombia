"""Municipios dentro del área de influencia del sismo.

No son AOIs Copernicus. Esta capa existe para no perder ciudades mencionadas
por prensa o con intensidad percibida, aunque no hayan sido mapeadas por satélite.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
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


def _capitaliza_palabra(w: str) -> str:
    """Primera letra de la palabra en mayúscula — y de CADA segmento si la
    palabra lleva siglas con punto interno («D.C.»). Sin esto, capitalizar
    solo la primera letra del conjunto deja «d.c.» → «D.c.»: el punto no
    separa palabras para `str.split()`, así que «D.C.» nunca pasaba por su
    propio segmento. Bogotá, D.C. lo publicaba así hasta el 30-ago-2026."""
    return ".".join(seg[:1].upper() + seg[1:] for seg in w.lower().split("."))


def _title_es(s: str) -> str:
    words = (s or "").strip().split()
    return " ".join(w.lower() if i > 0 and w.lower() in _LOWER_WORDS
                    else _capitaliza_palabra(w)
                    for i, w in enumerate(words))


# Quién se queda el nombre a secas cuando dos municipios se llaman igual.
# Congelado el 24-ago-2026 sobre LO PUBLICADO el 18-ago-2026 (el día que las
# claves dinámicas entraron a `data/public/municipios.json`), y verificado
# contra ese fichero: la clave manda sobre la URL de la ficha y sobre el
# identificador del feed de prensa que ya archivó titulares con ella.
#
# La razón de existir es que sin esta tabla el dueño lo decidía el ORDEN de las
# filas del RUD —familias descendente—, así que «Argelia» era la del Valle
# porque tenía más damnificados: un municipio homónimo nuevo con más familias
# se llevaba el nombre corto y cambiaba una URL publicada sin que nadie lo
# decidiera. El día del congelado eran 20 nombres del catálogo repetidos en la
# DIVIPOLA nacional; 12 estaban expuestos de verdad y a los otros 8 los anclaba
# `MUNICIPIOS`. La lista crece con el registro —cada alta puede estrenar
# homonimia— y quien avisa es `TestSupuestoNombreASecas`, no una revisión
# manual: por eso las tandas posteriores van fechadas más abajo.
#
# NO se aprovecha para corregir asignaciones discutibles: «Argelia» es hoy el
# pueblo de 5.538 habitantes y «Argelia (Cauca)» el de 27.853, y es feo, pero
# es lo publicado. Cambiarlo es una decisión editorial distinta, con su
# migración y sus redirecciones (docs/DECISIONES.md).
#
# La identidad es el código DIVIPOLA; el departamento va al lado porque es lo
# que un humano lee y la única vía de desempate si un día la fila no resuelve
# su código.
NOMBRE_A_SECAS_CONGELADO = {
    # decididos por el orden del RUD hasta hoy (los expuestos de verdad)
    "Argelia": {"divipola": "76054", "departamento": "Valle del Cauca"},
    "Bolívar": {"divipola": "76100", "departamento": "Valle del Cauca"},
    "Buenavista": {"divipola": "63111", "departamento": "Quindío"},
    "El Tambo": {"divipola": "19256", "departamento": "Cauca"},
    "La Unión": {"divipola": "76400", "departamento": "Valle del Cauca"},
    "La Vega": {"divipola": "19397", "departamento": "Cauca"},
    "Morales": {"divipola": "19473", "departamento": "Cauca"},
    "Salamina": {"divipola": "17653", "departamento": "Caldas"},
    "San Luis": {"divipola": "73678", "departamento": "Tolima"},
    "Santa María": {"divipola": "41676", "departamento": "Huila"},
    "Sucre": {"divipola": "19785", "departamento": "Cauca"},
    "Suárez": {"divipola": "19780", "departamento": "Cauca"},
    # estrenaron homonimia con el RUD del 23-ago-2026 (capturado el 24): el
    # registro los dio de alta y ninguno tiene todavía a su homónimo dentro,
    # así que hoy publican el nombre a secas. Se congela lo publicado —el
    # DIVIPOLA que ya llevan en `data/public/municipios.json`—, no la
    # asignación que uno elegiría de cero: «Florencia» es la de 2.000
    # habitantes del Cauca y no la capital del Caquetá, y «Granada» y «San
    # Francisco» son las de Antioquia, a cientos de kilómetros del epicentro,
    # porque son las que el RUD registró y las que tienen URL viva.
    "Florencia": {"divipola": "19290", "departamento": "Cauca"},
    "Granada": {"divipola": "05313", "departamento": "Antioquia"},
    "Páez": {"divipola": "19517", "departamento": "Cauca"},
    "San Francisco": {"divipola": "05652", "departamento": "Antioquia"},
    "Santa Rosa": {"divipola": "19701", "departamento": "Cauca"},
    # estrenaron homonimia con el RUD del 24-ago-2026 (capturado el 25): el
    # registro pasó de 251 a 347 municipios en una sola captura —el salto más
    # grande de la serie— y con él entraron catorce nombres a secas que la
    # DIVIPOLA nacional repite. Doce son de Antioquia, Cundinamarca o Norte de
    # Santander, a cientos de kilómetros del epicentro: el RUD alcanza hoy a
    # damnificados que estaban lejos del sismo, y son inscripciones de una o
    # dos decenas de familias, no municipios devastados.
    #
    # Mismo criterio que la tanda anterior: se congela LO PUBLICADO —el
    # DIVIPOLA que ya llevan en `data/public/municipios.json`, del que cuelga
    # la URL viva de la ficha y el identificador de su feed de prensa—, no la
    # asignación que uno elegiría de cero. «Caldas» es el municipio de
    # Antioquia y no el de Boyacá; «Nariño», el de Antioquia y no el de
    # Cundinamarca ni el de su propio departamento homónimo.
    "Barbosa": {"divipola": "05079", "departamento": "Antioquia"},
    "Betulia": {"divipola": "05093", "departamento": "Antioquia"},
    "Cabrera": {"divipola": "25120", "departamento": "Cundinamarca"},
    "Caldas": {"divipola": "05129", "departamento": "Antioquia"},
    "Concordia": {"divipola": "05209", "departamento": "Antioquia"},
    "Jericó": {"divipola": "05368", "departamento": "Antioquia"},
    "Nariño": {"divipola": "05483", "departamento": "Antioquia"},
    "Rionegro": {"divipola": "05615", "departamento": "Antioquia"},
    "San Bernardo": {"divipola": "25649", "departamento": "Cundinamarca"},
    "San Carlos": {"divipola": "05649", "departamento": "Antioquia"},
    "San Cayetano": {"divipola": "54673", "departamento": "Norte de Santander"},
    "Santa Bárbara": {"divipola": "05679", "departamento": "Antioquia"},
    "Toledo": {"divipola": "54820", "departamento": "Norte de Santander"},
    "Venecia": {"divipola": "05861", "departamento": "Antioquia"},
    # estrenaron homonimia con el RUD del 27-ago-2026, cuando el registro llegó
    # a 365 municipios. Mismo criterio: se congela LO PUBLICADO. Medido contra
    # el corpus de titulares antes de anotar (sin misatribución posible: los
    # tres homónimos de cada nombre están en departamentos ajenos al sismo, y
    # `requiere_depto` —puesto por defecto en todo municipio dinámico sin
    # revisar— ya exige que el titular nombre el departamento):
    # «Sabanalarga» tiene 3 titulares reales, los tres del sismo cerca de
    # Sabanalarga, Antioquia — coincide con lo publicado. «Belén» tiene 11
    # menciones en el corpus y ninguna es del municipio: son «Belén de Umbría»
    # (otro municipio, Risaralda) y el barrio Belén de Manizales — la
    # homonimia interna, no con Belén (Boyacá). «Valparaíso» no tiene ninguna
    # mención. Ningún caso silencia ni infla una brecha visible.
    "Belén": {"divipola": "52083", "departamento": "Nariño"},
    "Sabanalarga": {"divipola": "05628", "departamento": "Antioquia"},
    "Valparaíso": {"divipola": "05856", "departamento": "Antioquia"},
    # anclados por `MUNICIPIOS` (el reparto no los toca), anotados igual: si
    # algún día uno sale del catálogo curado, el nombre no puede quedar a subasta
    "Armenia": {"divipola": "63001", "departamento": "Quindío"},
    "Balboa": {"divipola": "66075", "departamento": "Risaralda"},
    "Candelaria": {"divipola": "76130", "departamento": "Valle del Cauca"},
    "Córdoba": {"divipola": "63212", "departamento": "Quindío"},
    "La Victoria": {"divipola": "76403", "departamento": "Valle del Cauca"},
    "Palestina": {"divipola": "17524", "departamento": "Caldas"},
    "Restrepo": {"divipola": "76606", "departamento": "Valle del Cauca"},
    "San Pedro": {"divipola": "76670", "departamento": "Valle del Cauca"},
}


def _dueno_del_nombre(dueno: dict, div: dict | None, departamento: str) -> bool:
    """¿Es esta fila la que tiene congelado el nombre a secas?

    Por código DIVIPOLA, que es la identidad estable. Si la fila no lo resuelve
    —nombre que el catálogo geográfico escribe de otra manera—, desempata el
    departamento; y sin ninguna de las dos vías el municipio se publica con el
    paréntesis. La degradación segura es «paréntesis», nunca «desaparece».
    """
    code = _divipola_key((div or {}).get("divipola"))
    if code:
        return code == _divipola_key(dueno.get("divipola"))
    return _admin_norm(departamento) == _admin_norm(dueno.get("departamento"))


# Topónimos ya revisados a mano: municipios a los que NO se les exige el
# departamento al lado para contarles un titular.
#
# Todo municipio que abre el registro oficial nace con `requiere_depto` puesto,
# porque nadie ha mirado aún si su nombre es además palabra común, apellido o
# lugar extranjero. La precaución es sensata y sale cara: la prensa colombiana
# escribe «el norte del Valle» o «la Gobernadora del Valle», casi nunca «Valle
# del Cauca», así que el municipio se queda sin sus titulares. La ficha de
# Argelia publicaba «ni un titular» de un pueblo del que EL PAÍS de Cali había
# titulado «Sismo en Argelia, más del 90 % del municipio afectado».
#
# Estar en esta tabla significa que alguien miró UNO A UNO los titulares que
# ese municipio perdía y comprobó que todos eran suyos. El criterio: se exime
# el topónimo que no sea palabra común, ni apellido frecuente, ni nombre de
# departamento, ni nombre compartido con otro municipio del área del sismo, y
# que además, medido contra el archivo entero de titulares —7.928 textos, con
# los anteriores al sismo que el corpus descarta—, no traiga ni un solo titular
# ajeno. Ante la duda, la precaución se queda puesta: publicar de menos es un
# fallo, atribuirle a un municipio prensa que no es suya es una mentira.
#
# La tabla exime a UN municipio, no a un nombre, y por eso la clave es el
# código DIVIPOLA: «Argelia» la del Valle sí —los titulares hablan de ella— y
# sus homónimas del Cauca y de Antioquia siguen con la precaución puesta.
#
# Lo que se dejó fuera importa tanto como lo que entró. Con razón: «Victoria»
# (Caldas) solo cazaba titulares de La Victoria (Valle); «Santa Rosa» (Cauca),
# de Santa Rosa de Cabal (Risaralda); «Balboa» (Cauca), de Balboa (Risaralda);
# «La Unión» (Antioquia), de La Unión (Valle); «Giraldo» (Antioquia), once
# titulares sobre un muerto apellidado Giraldo; «Florida» (Valle), la ayuda que
# salía de Miami; «Une» (Cundinamarca), el verbo unir; «Colombia» (Huila),
# 4.154 titulares del país entero. Y por duda razonable, aunque hoy acierten:
# «Aguadas» y «Salamina» (Caldas) ganaban un titular cada una, pero «aguadas»
# es adjetivo corriente y Salamina es también municipio del Magdalena; «El
# Santuario» (Antioquia) acierta dos veces y aun así «el santuario» nombra
# cualquier templo; «Quimbaya» (Quindío) arrastra la cultura arqueológica del
# mismo nombre; «Ibagué» (Tolima) cazaba un titular sobre Planadas por el
# nombre de la emisora que lo firma.
#
# No escala —cada municipio nuevo del RUD nacerá otra vez con la precaución
# puesta— y es a propósito: se prefiere revisar a mano antes que relajar la
# regla general (R10, docs/DECISIONES.md).
TOPONIMO_REVISADO_SIN_DEPTO = {
    # revisados el 25-ago-2026 contra el corpus de titulares
    "76054": {"municipio": "Argelia", "departamento": "Valle del Cauca",
              "porque": "«Argelia» es también el país, y por eso nació con la "
                        "precaución. Los nueve titulares del archivo que la "
                        "nombran son del municipio del norte del Valle —el "
                        "S.O.S. junto a El Cairo, los recorridos de la "
                        "gobernadora, el 90 % del casco afectado—, ninguno de "
                        "Argel. Las Argelias del Cauca y de Antioquia no están "
                        "en esta tabla: los mismos titulares no son suyos."},
    "76246": {"municipio": "El Cairo", "departamento": "Valle del Cauca",
              "porque": "«El Cairo» es la capital de Egipto en español, pero "
                        "los diecisiete titulares del archivo son del municipio "
                        "vallecaucano que el sismo dejó «80 % en ruinas». Si un "
                        "terremoto egipcio entra algún día al corpus, esta "
                        "línea se revisa."},
    "19585": {"municipio": "Puracé", "departamento": "Cauca",
              "porque": "Nombre único en el país. Los siete titulares hablan "
                        "del volcán Puracé, que está dentro del municipio: el "
                        "SGC descartando que el sismo lo activara y la alerta "
                        "naranja del cráter."},
    "63272": {"municipio": "Filandia", "departamento": "Quindío",
              "porque": "Nombre único —no es Finlandia—. Los siete titulares "
                        "son del pueblo: las fiestas del Canasto suspendidas, "
                        "el agua cortada, los pueblos turísticos golpeados."},
    "76126": {"municipio": "Calima", "departamento": "Valle del Cauca",
              "porque": "El municipio es Calima El Darién y así lo escribe la "
                        "prensa. Los cinco titulares son suyos, entre ellos el "
                        "de los niños muertos por el colapso de una pared."},
    "73555": {"municipio": "Planadas", "departamento": "Tolima",
              "porque": "Nombre único. Los cuatro titulares cuentan lo mismo: "
                        "las 18 toneladas de ayuda que Planadas mandó a "
                        "Istmina y Sipí."},
    "19698": {"municipio": "Santander de Quilichao", "departamento": "Cauca",
              "porque": "Nombre compuesto e inequívoco: «Santander» a secas no "
                        "lo activa. Los dos titulares son del municipio."},
    "41551": {"municipio": "Pitalito", "departamento": "Huila",
              "porque": "Nombre único y lejos del sismo: el único titular del "
                        "archivo es «Pitalito se solidariza con Istmina, "
                        "Chocó», que es exactamente lo que cuenta de él."},
    "76892": {"municipio": "Yumbo", "departamento": "Valle del Cauca",
              "porque": "Nombre único. El único titular es el de los daños en "
                        "Dapa, corregimiento de Yumbo."},
}


def _toponimo_revisado(municipio: str, div: dict | None,
                       departamento: str) -> bool:
    """¿Está este municipio en la tabla de topónimos revisados a mano?

    Por código DIVIPOLA, que es la identidad estable y lo único que distingue a
    la Argelia del Valle de las otras dos. Si la fila no resuelve su código
    —nombre que el catálogo geográfico escribe de otra manera—, desempata el
    par nombre+departamento; y sin ninguna de las dos vías el municipio se
    queda con la precaución puesta, que es la degradación segura.
    """
    code = _divipola_key((div or {}).get("divipola"))
    if code:
        return code in TOPONIMO_REVISADO_SIN_DEPTO
    return any(_admin_norm(municipio) == _admin_norm(f["municipio"])
               and _admin_norm(departamento) == _admin_norm(f["departamento"])
               for f in TOPONIMO_REVISADO_SIN_DEPTO.values())


def municipios_dinamicos(rud_municipios: dict | None,
                         divipola: dict | None) -> dict[str, dict]:
    """Entradas para municipios que el RUD registra pero MUNICIPIOS no cura
    aún: el registro oficial manda — si un municipio entra al RUD mañana, no
    puede perderse por falta de mantenimiento manual. Coordenadas del catálogo
    DIVIPOLA estático; sin coordenadas la entrada sale igual (sin punto en el
    mapa) y el test de supuesto avisa.

    El nombre a secas de los homónimos lo decide `NOMBRE_A_SECAS_CONGELADO`, no
    el orden de las filas. Objeción obvia: es mantenimiento manual, justo lo que
    esta función existe para evitar. No lo es, porque **la tabla no decide quién
    entra: solo quién se queda el nombre corto.** El municipio nuevo entra
    igual, con su ficha, su búsqueda y su punto en el mapa; lo único que cambia
    es que nace desambiguado —«X (Departamento)»— en vez de robarle la URL a
    otro. Sin entrada en la tabla se cae al reparto de siempre (el primero se lo
    lleva) y un test de supuesto avisa de que ha nacido un homónimo que hay que
    anotar.
    """
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
        libre = nombre not in MUNICIPIOS and nombre not in extras
        dueno = NOMBRE_A_SECAS_CONGELADO.get(nombre)
        if dueno:
            libre = libre and _dueno_del_nombre(dueno, div, departamento)
        key = nombre if libre \
            else f"{nombre} ({_title_es(fila.get('departamento') or dep_n)})"
        extras[key] = {
            "departamento": _title_es(departamento),
            "divipola": div.get("divipola") if div else None,
            "lat": div.get("lat") if div else None,
            "lon": div.get("lon") if div else None,
            "toponimos": [mun_n],
            # nadie ha revisado este topónimo todavía: si resulta ser palabra
            # común o apellido, exigir contexto evita atribuirle prensa ajena.
            # Los que sí se han revisado a mano —uno a uno, contra el corpus—
            # viven en `TOPONIMO_REVISADO_SIN_DEPTO` y entran aquí sin la
            # precaución: sin eso, la ficha de Argelia publicaba «ni un
            # titular» de un municipio con el 90 % del casco afectado.
            "requiere_depto": not _toponimo_revisado(municipio, div,
                                                     departamento),
            # y si además se llama como un departamento, el texto libre no
            # puede distinguirlos: no recibe prensa por texto en absoluto
            "homonimo_de_departamento": mun_n in deptos,
        }
    return extras


def catalogo_municipios(rud_municipios: dict | None = None,
                        divipola: dict | None = None) -> dict[str, dict]:
    """El catálogo que el monitor observa: los curados a mano MÁS los que abre
    el registro oficial.

    Una sola definición porque de ella cuelgan dos cosas que tienen que decir
    lo mismo: la ficha que se publica de cada municipio y la búsqueda de prensa
    que se le hace. Cuando se separaron, 126 de los 207 municipios con
    damnificados se quedaron sin búsqueda y el sitio publicaba de ellos «ni un
    titular» sin haber preguntado nunca.
    """
    # Copia de cada ficha: el catálogo se entrega para leerlo y anotarlo, y
    # `MUNICIPIOS` es un literal del módulo — un `catalogo[m]["toponimos"] = …`
    # de cualquier llamante reescribiría el catálogo curado para el resto del
    # proceso, y el fallo aparecería en otro sitio.
    return {mun: dict(meta) for mun, meta in
            {**MUNICIPIOS,
             **municipios_dinamicos(rud_municipios, divipola)}.items()}


def _rud_ultimo_dia(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """Municipios del último día capturado del RUD, con la misma clave
    normalizada que usa `publish.py` para cruzarlos con el catálogo.

    El `ORDER BY familias DESC` es el espejo literal de la consulta de
    `publish.py`: las dos leen las mismas filas en el mismo orden porque de las
    claves cuelgan la URL de la ficha y el identificador del feed de prensa.
    De los nombres a secas ya no decide el orden —los homónimos publicados los
    congela `NOMBRE_A_SECAS_CONGELADO`, y por eso «Argelia» es la del Valle del
    Cauca y la del Cauca lleva su departamento entre paréntesis—, pero el que
    estrene homonimia sin entrada en la tabla sí se reparte por aquí: leer en
    otro orden le cambiaría el nombre.
    """
    fila = conn.execute("SELECT MAX(snapshot_date) FROM rud_daily").fetchone()
    dia = fila[0] if fila else None
    if not dia:
        return {}
    return {(_norm(dep), _norm(mun)): {"departamento": dep, "municipio": mun}
            for dep, mun in conn.execute(
                "SELECT departamento, municipio FROM rud_daily"
                " WHERE snapshot_date=? ORDER BY familias DESC", (dia,))}


def catalogo_vigente() -> dict[str, dict]:
    """El catálogo de HOY, leído del archivo, para quien no tiene el RUD a mano.

    Existe para que la lista de municipios observados no se mantenga a mano en
    ningún sitio: el que entra hoy al registro oficial entra hoy al catálogo.
    Si el archivo aún no está (clon nuevo, CI antes del `rebuild`), devuelve
    los curados y sigue — un dato que falta degrada la cobertura, no la
    corrida (R13).
    """
    from common import DB_PATH, PUBLIC        # local: esta capa es de dominio
    rud: dict[tuple[str, str], dict] = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH, timeout=60)
        try:
            rud = _rud_ultimo_dia(conn)
        except sqlite3.Error:
            rud = {}
        finally:
            conn.close()
    div_path = PUBLIC / "divipola_coords.json"
    divipola = None
    if div_path.exists():
        try:
            divipola = json.loads(div_path.read_text()).get("items") or {}
        except (OSError, json.JSONDecodeError):
            divipola = None
    return catalogo_municipios(rud, divipola)


def build_municipios(noticias: list[dict], dyfi: dict | None,
                     aoi_extents: dict[str, str],
                     poblacion: dict | None = None,
                     rud_municipios: dict | None = None,
                     divipola: dict | None = None,
                     unosat: dict | None = None,
                     con_busqueda_propia: set[str] | None = None,
                     *, sertit: dict | None = None,
                     grid_mmi=None) -> tuple[list[dict], dict]:
    catalogo = catalogo_municipios(rud_municipios, divipola)
    out = {m: {"municipio": m, **meta, "n_noticias": 0,
               "n_prensa_recogida": 0,
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
        # SOLO el titular. `medio` no es la cabecera que firma la pieza: es la
        # etiqueta del feed que la trajo («Google News — Medio Atrato»), y
        # cruzarla atribuía el municipio del buscador a cualquier titular que
        # devolviese. Medido sobre el corpus: 1.577 atribuciones en 69
        # municipios entraban por ahí y no por el titular, y 15 de ellas se le
        # regalaban a OTRO municipio cuyo nombre va dentro del suyo —«Atrato»
        # recibía titulares del feed «Medio Atrato», que es otro pueblo—. Que
        # la búsqueda municipal encontró la pieza no se pierde: viaja declarado
        # en `noticias.json` (`publish.py::noticia`, vía `feed["municipios"]`)
        # y de ahí salen los titulares de cada ficha. `n_noticias` cuenta otra
        # cosa, más estrecha y comprobable: quién sale nombrado en el titular.
        text = n.get("titulo") or ""
        for mun, meta in catalogo.items():
            if _menciona_municipio(text, meta):
                row = out[mun]
                row["n_noticias"] += 1
                if len(row["noticias_ejemplo"]) < 3:
                    row["noticias_ejemplo"].append({
                        "fecha": n.get("fecha"), "medio": n.get("medio"),
                        "titulo": n.get("titulo"), "url": n.get("url")})
        # La otra cifra, la ancha: piezas que el monitor recogió PARA este
        # municipio según la atribución declarada de `noticias.json` —las que
        # lo nombran en el titular MÁS las que trajo su búsqueda municipal sin
        # nombrarlo—. Es la que llena la lista de titulares de cada ficha, y
        # existe para que el cero de `n_noticias` no se pueda leer como «el
        # monitor preguntó y no hubo nada» cuando sí hubo: El Dovio tiene 0
        # titulares que lo nombren y 21 piezas recogidas. Sin ella, sacar el
        # nombre del feed del texto cruzado cambiaba un error por el contrario.
        for mun in n.get("municipios") or []:
            if mun in out:
                out[mun]["n_prensa_recogida"] += 1

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
    aquí y en `deploy/render_html.py::_mirado_por_satelite`, que es donde la
    regla de la tabla quedó al prerenderizarse en la fase 4. **No son la misma
    pregunta y no deben dar la misma cifra**: la de la tabla cuenta todos los
    municipios sin producto satelital (197) y esta función solo los que además tienen
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
