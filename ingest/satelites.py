"""Cómo se cuenta un edificio cuando lo miran dos satélites.

Hasta el 21-ago-2026 el monitor sumaba las miradas satelitales porque cubrían
municipios disjuntos: 622 de Copernicus + 385 de UNOSAT. Con la entrada de
ICube-SERTIT eso deja de valer — mira Pereira, Cali y Manizales, que ya
estaban cartografiados— y sumar contaría dos veces los mismos tejados.

La respuesta no es quedarse con la cifra mayor: **es unir los puntos**. Dos
puntos de FUENTES DISTINTAS a menos del umbral son el mismo edificio y se
cuentan una vez, con las dos atribuciones; dos puntos de la MISMA fuente nunca
se funden, porque si un servicio marcó dos edificios es que vio dos. El
recuento resultante está siempre entre el máximo y la suma, y de paso responde
preguntas que una cifra agregada no puede: cuántos edificios vio un servicio y
el otro no, y en cuántos discrepan sobre la gravedad.

El umbral no es una constante elegida a ojo. Sale del experimento del
18-ago-2026 (memoria del proyecto, `cruce-espacial-umbrales`): los daños de
Copernicus tienen **mediana de 25 m al vecino más próximo**, y contra un test
de azar **a 15 m la coincidencia fortuita es del 0,8 %** mientras que a 250 m
llega al 48 %. Por debajo de 25 m hay señal; por encima de 100 m, ruido
indistinguible del azar. `tasa_de_azar()` deja repetir esa medición sobre los
datos de cada día, y la corrida la publica: un umbral que no se puede auditar
es un número inventado con decimales.
"""
from __future__ import annotations

import math
import random

# 20 m: dentro de la zona de señal y por debajo de la mediana al vecino más
# próximo. Medido sobre los datos reales de Pereira el 21-ago-2026, une 108 de
# los 252 puntos de SERTIT con uno de Copernicus —el 42,9 %— frente al 1,4 %
# que empareja un punto lanzado al azar en la misma caja: treinta veces por
# encima. Si algún día esa distancia deja de separar señal de ruido, el test de
# hipótesis lo cantará antes que nadie.
UMBRAL_M = 20

# Qué municipio cartografía cada AOI de Copernicus. Curado a mano y no
# deducido de la geometría: `Northern Cali` NO contiene la cabecera de Cali, y
# una asignación automática por proximidad perdería sus 7 edificios sin que
# nadie se enterase. `Western Colombia` no está porque no declara estadística
# de edificios — es el AOI del producto de movimiento del terreno que
# Copernicus acabó no entregando.
AOI_MUNICIPIO = {
    "Northern Cali": "Cali",
    "Cali Center": "Cali",
    "Pereira": "Pereira",
    "Quibdo Centre": "Quibdó",
    "Istmina": "Istmina",
    "Buenaventura": "Buenaventura",
}


def distancia_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metros entre dos (lon, lat). Plano local: a estas distancias sobra."""
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat),
                      (a[1] - b[1]) * 110570)


def unir_danos(puntos: list[dict], *, umbral_m: float = UMBRAL_M) -> dict:
    """Une los daños de varias fuentes en edificios únicos.

    `puntos`: dicts con `fuente`, `lon`, `lat` y opcionalmente `dano`.
    Devuelve el recuento de unidades, cuántas vio cada fuente en exclusiva,
    cuántas coinciden y en cuántas las fuentes discrepan de grado.

    Sin puntos no devuelve 0 unidades como si se hubiera mirado y no hubiera
    nada: devuelve `unidades: None` (R3). Un cero aquí se leería como «los
    satélites miraron y no vieron daño», que es lo contrario de la verdad.
    """
    puntos = [p for p in puntos
              if p.get("lon") is not None and p.get("lat") is not None]
    if not puntos:
        return {"unidades": None, "fuentes": {}, "solo_de": {},
                "coincidencias": 0, "discrepan_de_grado": 0,
                "umbral_m": umbral_m}

    # Unión por cercanía SOLO entre fuentes distintas. Se recorre en orden
    # estable para que el resultado no dependa del orden de llegada.
    orden = sorted(range(len(puntos)),
                   key=lambda i: (puntos[i].get("fuente") or "",
                                  puntos[i]["lon"], puntos[i]["lat"]))
    grupo: list[int | None] = [None] * len(puntos)
    unidades: list[list[int]] = []
    for i in orden:
        p = puntos[i]
        destino = None
        for u, miembros in enumerate(unidades):
            fuentes_u = {puntos[j].get("fuente") for j in miembros}
            if p.get("fuente") in fuentes_u:
                continue           # misma fuente: jamás se funden
            if any(distancia_m((p["lon"], p["lat"]),
                               (puntos[j]["lon"], puntos[j]["lat"])) < umbral_m
                   for j in miembros):
                destino = u
                break
        if destino is None:
            unidades.append([i])
            grupo[i] = len(unidades) - 1
        else:
            unidades[destino].append(i)
            grupo[i] = destino

    por_fuente: dict[str, int] = {}
    for p in puntos:
        f = p.get("fuente") or "?"
        por_fuente[f] = por_fuente.get(f, 0) + 1

    solo_de: dict[str, int] = {}
    coincidencias = 0
    discrepan = 0
    for miembros in unidades:
        fuentes_u = {puntos[j].get("fuente") for j in miembros}
        if len(fuentes_u) == 1:
            f = miembros and puntos[miembros[0]].get("fuente") or "?"
            solo_de[f] = solo_de.get(f, 0) + 1
        else:
            coincidencias += 1
            grados = {(puntos[j].get("dano") or "").lower() for j in miembros}
            if len(grados - {""}) > 1:
                discrepan += 1

    return {"unidades": len(unidades), "fuentes": por_fuente,
            "solo_de": solo_de, "coincidencias": coincidencias,
            "discrepan_de_grado": discrepan, "umbral_m": umbral_m}


def puntos_publicados(public_dir) -> list[dict]:
    """Los puntos de daño de las tres miradas, leídos de lo ya publicado.

    Se leen los geojson públicos y no las tablas: así el recuento se calcula
    sobre exactamente lo que ve el lector del mapa, y no sobre una consulta
    paralela que podría divergir sin que nadie lo notase.
    """
    import json
    out: list[dict] = []
    for fichero, fuente in (("damage_points.geojson", "copernicus"),
                            ("unosat_damage.geojson", "unosat"),
                            ("sertit_damage.geojson", "sertit")):
        ruta = public_dir / fichero
        if not ruta.exists():
            continue
        for f in json.loads(ruta.read_text(encoding="utf-8")).get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") != "Point":
                continue
            p = f.get("properties") or {}
            dano = p.get("dano") or p.get("damage_gra")
            # Un punto que la fuente marcó pero NO clasificó no es «daño
            # clasificado»: los 9 `Not Applicable` de SERTIT en Cali se pintan
            # en el mapa —el edificio está señalado— pero no entran en un total
            # que se anuncia como clasificado. Mismo cuidado que con los 8 de
            # código imposible de UNOSAT: apartar, no descartar.
            if (dano or "").lower().startswith("not applicable"):
                continue
            muni = p.get("municipio") or AOI_MUNICIPIO.get(p.get("aoi") or "")
            lon, lat = (g.get("coordinates") or [None, None])[:2]
            out.append({"fuente": fuente, "lon": lon, "lat": lat,
                        "municipio": muni, "dano": dano})
    return out


def recuento(public_dir, *, umbral_m: float = UMBRAL_M) -> dict:
    """El recuento satelital del monitor, municipio a municipio.

    Devuelve el total de edificios únicos y, por municipio, qué vio cada
    servicio, cuántos coinciden y cuántos son exclusivos de uno. Los
    municipios que solo mira un servicio salen igual: ahí unir no cambia nada
    y el dato sigue siendo su cifra.
    """
    puntos = puntos_publicados(public_dir)
    por_mun: dict[str, list[dict]] = {}
    sin_municipio = 0
    for p in puntos:
        if not p.get("municipio"):
            sin_municipio += 1
            continue
        por_mun.setdefault(p["municipio"], []).append(p)

    detalle = {}
    total = 0
    for muni, pts in sorted(por_mun.items()):
        u = unir_danos(pts, umbral_m=umbral_m)
        if len(u["fuentes"]) > 1:
            u["azar_pct"] = tasa_de_azar(pts, sorted(u["fuentes"])[0],
                                         umbral_m=umbral_m)
        detalle[muni] = u
        total += u["unidades"] or 0
    return {"total_edificios": total, "umbral_m": umbral_m,
            "sin_municipio": sin_municipio, "por_municipio": detalle,
            "criterio": (
                "Cada edificio se cuenta una vez. Dos puntos de servicios "
                "distintos a menos de {} m son el mismo edificio; dos puntos "
                "del mismo servicio, nunca. No se suman las cifras de dos "
                "satélites sobre el mismo municipio ni se elige la mayor."
            ).format(int(umbral_m))}


def tasa_de_azar(puntos: list[dict], fuente_diana: str, *,
                 umbral_m: float = UMBRAL_M, muestras: int = 500,
                 semilla: int = 42) -> float:
    """Qué porcentaje emparejaría un punto lanzado al azar en la misma caja.

    Es el control del experimento: si la coincidencia real no supera con
    claridad a esta tasa, el emparejamiento no es evidencia de nada, solo
    densidad urbana. Determinista por semilla, para que el número publicado
    hoy pueda reproducirse mañana.
    """
    diana = [p for p in puntos if p.get("fuente") == fuente_diana
             and p.get("lon") is not None]
    if not diana or len(puntos) == len(diana):
        return 0.0
    lons = [p["lon"] for p in puntos if p.get("lon") is not None]
    lats = [p["lat"] for p in puntos if p.get("lat") is not None]
    rnd = random.Random(semilla)
    aciertos = 0
    for _ in range(muestras):
        q = (rnd.uniform(min(lons), max(lons)), rnd.uniform(min(lats), max(lats)))
        if any(distancia_m(q, (p["lon"], p["lat"])) < umbral_m for p in diana):
            aciertos += 1
    return round(100 * aciertos / muestras, 1)
