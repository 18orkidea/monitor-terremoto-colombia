"""Avisa a los buscadores de qué páginas cambiaron hoy (protocolo IndexNow).

El monitor se regenera cada día, pero un buscador solo se entera cuando vuelve
a pasar — y por la cola larga de fichas municipales puede tardar semanas. Eso
es grave aquí por dos motivos: la cifra de un municipio del Chocó llega tarde a
quien la busca, y los sistemas de IA citan lo que su índice tiene, no lo que el
sitio publica. IndexNow invierte la dirección: en vez de esperar, se avisa.

**Solo se notifica lo que de verdad cambió.** El protocolo pide no avisar de
páginas intactas, y además interesa: un aviso indiscriminado de 213 URLs cada
día vale lo mismo que ninguno. Las cinco páginas fijas cambian a diario porque
las cifras cambian; de las fichas municipales se avisa solo de aquellas cuyos
datos difieren de la corrida anterior, comparando la huella guardada en
`data/indexnow_estado.json`.

La clave del protocolo no es un secreto: se publica en la raíz del sitio, en un
fichero cuyo nombre ES la clave, y sirve para demostrar que quien avisa
controla el dominio. Por eso vive en `deploy/root/` y no en la configuración:
la única copia es la publicada, y rotarla es sustituir ese fichero.

Un buscador caído no rompe la corrida (R13); la petición queda en `sources_log`
como cualquier otra (R4), con el sha256 de lo que se envió.
"""
import hashlib
import json
import re

import common

DOMINIO = "https://datosdelterremoto.org"
ENDPOINT = "https://api.indexnow.org/IndexNow"

# cambian todos los días porque las cifras cambian todos los días
PAGINAS_FIJAS = ("/", "/municipios.html", "/rud.html", "/balances.html",
                 "/noticias.html", "/referencia.html")

ESTADO = common.ROOT / "data" / "indexnow_estado.json"
RAIZ_PUBLICADA = common.ROOT / "deploy" / "root"
MUNICIPIOS = common.ROOT / "data" / "public" / "municipios.json"

# tope del protocolo por petición; muy por encima de las 213 URLs del sitio
MAX_URLS = 10_000


def clave() -> str | None:
    """La clave es el nombre del fichero que la publica, y su contenido.

    Se comprueban las dos cosas: un fichero cuyo nombre y contenido no
    coincidan haría fallar la verificación del buscador en silencio.
    """
    for f in sorted(RAIZ_PUBLICADA.glob("*.txt")):
        nombre = f.stem
        if re.fullmatch(r"[0-9a-f]{8,128}", nombre) and \
           f.read_text(encoding="utf-8").strip() == nombre:
            return nombre
    return None


def _huella(item: dict) -> str:
    """Qué se considera «la ficha cambió»: cualquier dato que la ficha publica."""
    return hashlib.sha256(
        json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _slug(nombre: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return "-".join(x for x in "".join(c if c.isalnum() else " " for c in s).split())


def urls_a_avisar(items: list[dict], estado: dict) -> tuple[list[str], dict]:
    """Devuelve (URLs que cambiaron, estado nuevo). Sin red: es testeable."""
    urls = [DOMINIO + p for p in PAGINAS_FIJAS]
    nuevo = {}
    for item in items:
        nombre = item.get("municipio") or ""
        depto = item.get("departamento") or ""
        if not nombre:
            continue
        # el slug lleva departamento cuando hay homónimos, igual que las fichas
        s = _slug(nombre)
        clave_estado = f"{s}|{_slug(depto)}"
        h = _huella(item)
        nuevo[clave_estado] = h
        if estado.get(clave_estado) != h:
            urls.append(f"{DOMINIO}/municipio/{s}/")
    return urls[:MAX_URLS], nuevo


def run(dry_run: bool = False) -> dict:
    k = clave()
    if not k:
        return {"error": "sin clave publicada en deploy/root/<clave>.txt"}
    if not MUNICIPIOS.exists():
        return {"error": "falta data/public/municipios.json; ¿corrió publish?"}

    items = json.loads(MUNICIPIOS.read_text(encoding="utf-8")).get("items", [])
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    urls, estado_nuevo = urls_a_avisar(items, estado)
    fichas = len(urls) - len(PAGINAS_FIJAS)

    if dry_run:
        return {"urls": len(urls), "fichas_cambiadas": fichas, "dry_run": True}

    status = common.notificar(
        ENDPOINT,
        {"host": DOMINIO.split("//", 1)[1], "key": k,
         "keyLocation": f"{DOMINIO}/{k}.txt", "urlList": urls},
        note=f"indexnow: {len(urls)} urls ({fichas} fichas con datos nuevos)")

    # el estado solo avanza si el aviso salió: si falló, mañana se reintenta
    # con el mismo listado y no se pierde ninguna ficha por el camino
    if status in (200, 202):
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(estado_nuevo, ensure_ascii=False,
                                     indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    return {"http": status, "urls": len(urls), "fichas_cambiadas": fichas,
            "estado_guardado": status in (200, 202)}


if __name__ == "__main__":
    import sys
    print(json.dumps(run(dry_run="--dry-run" in sys.argv), ensure_ascii=False))
