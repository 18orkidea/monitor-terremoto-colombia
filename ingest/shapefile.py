"""Lector de shapefile (.shp + .dbf) con solo stdlib — R14.

El formato ESRI es público y estable desde 1998, así que leerlo no necesita
GDAL ni pyshp: `struct` para la geometría y un parser de dBase III para la
tabla de atributos. Se soporta lo que publican los productos de emergencia
—puntos, polilíneas y polígonos, con o sin Z/M— y nada más: un tipo de
geometría desconocido se devuelve como `None` en vez de inventar una forma.

Devuelve geometrías GeoJSON ya en el orden [lon, lat], que es el que espera
Leaflet. NO reproyecta: quien llame debe comprobar que el .prj es geográfico
(WGS84), porque un shapefile en UTM daría coordenadas absurdas en el mapa
sin fallar.

R3 vive aquí: una celda vacía de un campo numérico devuelve None, jamás 0,
y el literal original se conserva para que el llamante pueda archivarlo.
"""
from __future__ import annotations

import struct

# Tipos ESRI agrupados por familia. Las variantes Z (10-19) y M (20-29)
# repiten la cabecera XY de su tipo base, así que se leen igual y se ignoran
# las alturas: el monitor mapea en 2D.
PUNTOS = (1, 11, 21)
LINEAS = (3, 13, 23)
POLIGONOS = (5, 15, 25)


def _geom(buf: bytes, off: int):
    """Una geometría desde `off`. Devuelve dict GeoJSON o None."""
    (styp,) = struct.unpack_from("<i", buf, off)
    if styp == 0:                      # Null shape: ausencia declarada
        return None
    if styp in PUNTOS:
        x, y = struct.unpack_from("<dd", buf, off + 4)
        return {"type": "Point", "coordinates": [x, y]}
    if styp in LINEAS + POLIGONOS:
        nparts, npts = struct.unpack_from("<ii", buf, off + 36)
        pbase = off + 44
        partes = list(struct.unpack_from(f"<{nparts}i", buf, pbase))
        xybase = pbase + nparts * 4
        pts = [list(struct.unpack_from("<dd", buf, xybase + 16 * k))
               for k in range(npts)]
        anillos = [pts[a:b] for a, b in
                   zip(partes, list(partes[1:]) + [npts]) if b > a]
        if not anillos:
            return None
        if styp in LINEAS:
            return ({"type": "LineString", "coordinates": anillos[0]}
                    if len(anillos) == 1
                    else {"type": "MultiLineString", "coordinates": anillos})
        # Polígono: el primer anillo es el exterior y los siguientes, huecos.
        # No se separan multipolígonos por sentido de giro — para dibujar en
        # el mapa basta, y adivinarlo mal partiría geometrías válidas.
        return {"type": "Polygon", "coordinates": anillos}
    return None


def read_shp(buf: bytes) -> list[dict | None]:
    """Geometrías de un .shp, en orden de registro (paralelo al .dbf)."""
    if len(buf) < 100 or struct.unpack_from(">i", buf, 0)[0] != 9994:
        raise ValueError("no es un .shp (falta el file code 9994)")
    out, n = [], 100
    while n + 8 <= len(buf):
        _num, clen = struct.unpack_from(">ii", buf, n)
        cuerpo = n + 8
        fin = cuerpo + clen * 2
        if fin > len(buf):
            break                      # registro truncado: se descarta entero
        out.append(_geom(buf, cuerpo))
        n = fin
    return out


def _limpia(s: str) -> str | None:
    """Texto de una celda dBase. Los bytes nulos de relleno que dejan algunos
    exportadores ArcGIS no son texto: la celda está vacía, y vacío es None."""
    s = s.replace("\x00", "").strip()
    return s or None


def read_dbf(buf: bytes, encoding: str = "utf-8") -> tuple[list[dict], list[dict]]:
    """(campos, filas) de un .dbf. Los campos numéricos vacíos son None (R3).

    Cada fila lleva los valores ya convertidos; los campos numéricos añaden
    además `<nombre>__raw` con el literal original cuando no está vacío, para
    que el literal de la fuente pueda archivarse sin reinterpretación.
    """
    nrec, hlen, rlen = struct.unpack_from("<IHH", buf, 4)
    campos, off = [], 32
    while off < len(buf) and buf[off] != 0x0D:
        nombre = buf[off:off + 11].split(b"\0")[0].decode("latin-1")
        campos.append({"nombre": nombre, "tipo": chr(buf[off + 11]),
                       "largo": buf[off + 16], "decimales": buf[off + 17]})
        off += 32

    filas = []
    for i in range(nrec):
        p = hlen + i * rlen
        if p + rlen > len(buf):
            break
        if buf[p:p + 1] == b"*":       # marcado como borrado: no es un dato
            continue
        p += 1
        fila = {}
        for c in campos:
            crudo = buf[p:p + c["largo"]]
            p += c["largo"]
            try:
                txt = crudo.decode(encoding)
            except UnicodeDecodeError:
                txt = crudo.decode("latin-1")
            val = _limpia(txt)
            if c["tipo"] in ("N", "F") and val is not None:
                fila[c["nombre"] + "__raw"] = val
                try:
                    val = float(val)
                except ValueError:
                    val = None         # "NA" y compañía: NULL, nunca 0
            elif c["tipo"] == "L":
                val = {"Y": True, "T": True, "N": False, "F": False}.get(
                    (val or "").upper()[:1])
            fila[c["nombre"]] = val
        filas.append(fila)
    return campos, filas


def es_geografico(prj: str) -> bool:
    """¿El .prj declara coordenadas geográficas (grados)? Un shapefile
    proyectado necesitaría reproyección y aquí se rechaza antes de publicar
    coordenadas sin sentido."""
    return prj.strip().upper().startswith("GEOGCS")


def leer(shp: bytes, dbf: bytes, *, encoding: str = "utf-8") -> list[dict]:
    """Features GeoJSON de un par .shp/.dbf. Descarta los registros sin
    geometría legible: un atributo sin punto no se puede mapear."""
    geoms = read_shp(shp)
    _campos, filas = read_dbf(dbf, encoding)
    out = []
    for i, fila in enumerate(filas):
        g = geoms[i] if i < len(geoms) else None
        if g is None:
            continue
        out.append({"type": "Feature", "geometry": g, "properties": fila})
    return out
