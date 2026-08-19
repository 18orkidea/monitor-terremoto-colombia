"""Dumps CSV de la base de datos — el sqlite fuera de git, la crónica dentro.

El binario data/monitor.sqlite no se versiona (15 MB/día sin diff legible);
en su lugar, cada corrida vuelca las tablas a data/dumps/*.csv, que sí se
versionan: el `git diff` diario muestra fila a fila qué cambió — legible para
un historiador sin más herramienta que un editor de texto. `rebuild()` hace el
camino inverso para un clon nuevo o para el runner de CI.

Convenciones del formato (¡no cambiar sin migrar los dumps existentes!):
  - NULL se escribe como el centinela \\N (convención de dumps de MySQL/Postgres);
    todo lo demás es su str(). La afinidad de tipos de sqlite reconvierte
    números al reinsertar.
  - Filas ordenadas por clave primaria (o rowid) → diffs deterministas.
  - El alias del rowid (`id INTEGER PRIMARY KEY`) NO se vuelca: lo reparte
    sqlite al insertar y lo vuelve a repartir si las filas se recrean, así que
    en el CSV solo generaba diffs falsos. `rebuild` lo regenera. Los dumps
    anteriores a esta convención se siguen leyendo tal cual: la inserción es
    por nombre de columna, así que un CSV que traiga `id` conserva el suyo.

Uso:
  python ingest/dump_db.py dump      # sqlite → data/dumps/*.csv
  python ingest/dump_db.py rebuild   # data/dumps/*.csv → sqlite (si no existe)
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, DB_PATH, SCHEMA

DUMPS = DATA / "dumps"
NULO = "\\N"

TABLAS = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)


def _es_rowid(info: list) -> str | None:
    """Nombre de la columna que es alias del rowid, si la tabla tiene una.

    Un `id INTEGER PRIMARY KEY` no es un dato: es el número que sqlite reparte
    al insertar, y lo reparte otra vez si las filas se recrean. `evidence` lo
    hace cada día (`crosscheck` borra y reinserta la evidencia automática del
    día), así que 27 de sus 100 líneas cambiaban de valor sin que cambiara
    nada real. En un repositorio que es archivo, un diff que miente sobre lo
    que pasó cuesta más que la columna que ahorra.
    """
    for _, nombre, tipo, _, _, pk in info:
        if pk == 1 and (tipo or "").upper() == "INTEGER":
            return nombre
    return None


def _columnas(conn: sqlite3.Connection, tabla: str) -> tuple[list[str], list[str]]:
    """Columnas a volcar y orden del volcado.

    El alias del rowid se omite: no se vuelca y `rebuild` deja que sqlite lo
    reparta de nuevo al insertar, en el mismo orden. Los dumps anteriores al
    cambio siguen reconstruyéndose sin tocar nada, porque `rebuild` inserta por
    nombre de columna: si el CSV trae `id`, se respeta.
    """
    info = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
    cols = [r[1] for r in info]
    pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
    rowid = _es_rowid(info)
    if rowid:
        cols = [c for c in cols if c != rowid]
    return cols, pk


def dump(conn: sqlite3.Connection | None = None) -> dict:
    propia = conn is None
    if propia:
        conn = sqlite3.connect(DB_PATH)
    DUMPS.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for tabla in TABLAS:
        cols, pk = _columnas(conn, tabla)
        orden = ", ".join(pk) if pk else "rowid"
        filas = conn.execute(f"SELECT {', '.join(cols)} FROM {tabla} ORDER BY {orden}")
        with open(DUMPS / f"{tabla}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            n = 0
            for fila in filas:
                w.writerow([NULO if v is None else str(v) for v in fila])
                n += 1
        resumen[tabla] = n
    if propia:
        conn.close()
    return resumen


def _tiene_tablas(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        n = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        return n > 0
    except sqlite3.Error:
        return False


def rebuild(db_path: Path | None = None) -> dict:
    """Reconstruye el sqlite desde los dumps. Solo si la BD no existe o está
    vacía (sqlite3.connect crea un fichero vacío con solo abrirlo — p. ej. un
    test que consulta antes de reconstruir): la BD viva nunca se pisa."""
    destino = Path(db_path) if db_path else DB_PATH
    if destino.exists() and _tiene_tablas(destino):
        return {"skip": f"{destino.name} ya existe; no se pisa"}
    destino.unlink(missing_ok=True)
    if not DUMPS.exists():
        return {"skip": "sin data/dumps/; nada que reconstruir"}
    conn = sqlite3.connect(destino)
    conn.executescript(SCHEMA)
    resumen = {}
    for tabla in TABLAS:
        ruta = DUMPS / f"{tabla}.csv"
        if not ruta.exists():
            continue
        # convertir números en Python, no en sqlite: el parser texto→float de
        # sqlite puede diferir en 1 ulp del de Python y corromper el archivo
        tipos = {r[1]: (r[2] or "").upper()
                 for r in conn.execute(f"PRAGMA table_info({tabla})")}

        def valor(col: str, v: str):
            if v == NULO:
                return None
            t = tipos.get(col, "")
            if "INT" in t:
                try:
                    return int(v)
                except ValueError:
                    pass
            if "INT" in t or "REAL" in t or "FLOA" in t or "DOUB" in t:
                try:
                    return float(v)
                except ValueError:
                    pass
            return v

        with open(ruta, newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            cols = next(lector, None)
            if not cols:
                continue
            marcas = ", ".join("?" * len(cols))
            n = 0
            for fila in lector:
                conn.execute(
                    f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})",
                    [valor(c, v) for c, v in zip(cols, fila)])
                n += 1
        resumen[tabla] = n
    conn.commit()
    conn.close()
    return resumen


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if modo == "dump":
        print({"dump": dump()})
    elif modo == "rebuild":
        print({"rebuild": rebuild()})
    else:
        sys.exit(f"modo desconocido: {modo} (usa dump|rebuild)")


if __name__ == "__main__":
    main()
