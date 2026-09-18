"""RUD — Registro Único de Damnificados (UNGRD).

LA fuente que faltaba: la primera oficial que cubre el evento de 2026, con
datos por municipio (familias, personas, viviendas). Endpoint público de
lectura descubierto el 16-ago-2026; no es una API documentada, así que el
parser es tolerante y su test de supuesto vigilará que siga vivo.

Matiz importante: el RUD lo cargan las autoridades municipales — que un
municipio no aparezca no significa "sin daño", significa "sin registro aún".
Esa asimetría es en sí misma una brecha que el monitor muestra.

## Captura cerrada (17-sep-2026)

La captura diaria se detuvo por decisión editorial: desde el 13-sep el
registro repetía las mismas cifras en los 409 municipios, y cada captura
nueva solo alargaba las gráficas con puntos planos. `CAPTURA_CERRADA` lo
declara, y mientras esté puesto `run()` no hace ninguna petición: no hay
fila en `sources_log` ni snapshot, y `rud.json` lo dice para que el sitio
pueda contarlo. La sonda de contrato (`test_supuestos_api.py`) también se
salta: parada total es parada total, y una sonda diaria contra el endpoint
sería justo la opción intermedia que se descartó.

Lo que se pierde, y se asumió al decidirlo (docs/DECISIONES.md): el RUD solo
sirve su estado actual, así que un día sin capturar no se recupera nunca, y
si las alcaldías vuelven a cargar nadie se entera sin mirar a mano. El test de supuesto queda escrito y se
reactiva con la captura.
"""
from __future__ import annotations

import json

from common import db, dia_colombiano_consolidado, fetch_json

URL = "https://rud.gestiondelriesgo.gov.co/home/json.php?temp=2026T"

# None para reanudar la captura diaria — pero reanudar NO es solo esto: los
# días cerrados aparecerían como huecos sin explicar (`alerts.py`,
# `test_no_hay_dias_perdidos_entre_capturas`), así que el intervalo cerrado
# hay que anotarlo en `common.HUECOS_RUD_CONOCIDOS` con su porqué.
#
# `ultima_captura` es la etiqueta de `rud_daily` de la última corrida que
# capturó —la del 18-sep, que consolida el día colombiano 17-sep— y no se
# escribe a ojo: `test_unit.py::TestCapturaDelRudCerrada` la compara con la
# fecha máxima de `data/dumps/rud_daily.csv`, para que una parada que llegue
# tarde (un cron de por medio) se vea en rojo en vez de publicar una fecha
# falsa.
CAPTURA_CERRADA = {
    "fecha": "2026-09-18",
    "ultima_captura": "2026-09-17",
    "ultima_corrida": "2026-09-18",
    "motivo": ("el registro repetía las mismas cifras en todos los municipios "
               "desde el 13-sep-2026"),
}


def _fecha_iso(f: str) -> str | None:
    try:
        d, m, a = (f or "").split("/")
        return f"{a}-{m}-{d}"
    except ValueError:
        return None


def _n(v):
    try:
        return int(str(v).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def run() -> dict:
    if CAPTURA_CERRADA:
        # Sin petición: que la fuente callara aquí no es un fallo (R13), es
        # la decisión documentada arriba.
        return {"captura_cerrada": CAPTURA_CERRADA}
    conn = db()
    status, data = fetch_json(URL, note="rud 2026T",
                              snapshot_name="rud_2026T.json", conn=conn)
    if not data:
        conn.commit(); conn.close()
        return {"error": f"RUD HTTP {status} (endpoint no documentado: "
                         "puede haber cambiado — ver snapshots previos)"}
    rows = data if isinstance(data, list) else data.get("data") or []
    # la serie va por día colombiano cerrado, no por día UTC: lo que cargan las
    # alcaldías el día D se ve completo justo después de su medianoche.
    # `conn` deja que el cálculo se blinde contra un cron retrasado (ver
    # docs/DECISIONES.md, hueco del 26-ago-2026).
    dia = dia_colombiano_consolidado(conn)
    n = 0
    for r in rows:
        dep = (r.get("departamento") or "").strip()
        mun = (r.get("municipio") or "").strip()
        fecha = _fecha_iso(r.get("fecha_evento"))
        if not mun or not fecha:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO official_events (source, external_id, fecha,"
            " departamento, municipio, evento, personas, familias,"
            " viv_destruidas, viv_averiadas)"
            " VALUES ('ungrd_rud',?,?,?,?,?,?,?,?,?)",
            (f"{dep}|{mun}|{fecha}", fecha, dep, mun, r.get("evento"),
             _n(r.get("personas")), _n(r.get("familias")),
             _n(r.get("destruidas")), _n(r.get("averiadas"))))
        conn.execute(
            "INSERT OR REPLACE INTO rud_daily (snapshot_date, departamento,"
            " municipio, familias, personas, viv_destruidas, viv_averiadas,"
            " habitables, nohabitables) VALUES (?,?,?,?,?,?,?,?,?)",
            (dia, dep, mun, _n(r.get("familias")), _n(r.get("personas")),
             _n(r.get("destruidas")), _n(r.get("averiadas")),
             _n(r.get("habitables")), _n(r.get("nohabitables"))))
        n += 1
    conn.commit()
    tot = conn.execute(
        "SELECT COUNT(*), SUM(familias), SUM(personas), SUM(viv_destruidas),"
        " SUM(viv_averiadas) FROM official_events WHERE source='ungrd_rud'"
    ).fetchone()
    conn.close()
    return {"dia_consolidado": dia, "registros": n, "municipios_en_bd": tot[0],
            "familias": tot[1], "personas": tot[2],
            "viv_destruidas": tot[3], "viv_averiadas": tot[4]}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
