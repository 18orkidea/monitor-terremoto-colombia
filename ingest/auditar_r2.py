"""El manifiesto contra la realidad: ¿está en R2 lo que decimos que está?

Desde el 24-ago-2026 un vídeo ciudadano ya archivado no se vuelve a descargar
(`common.activo_archivado`). Ese ahorro quitó una red que nadie había escrito a
propósito: mientras el runner se bajaba los 77 vídeos cada día, el `aws s3 sync`
los volvía a ofrecer y **un objeto que faltara en el bucket se curaba solo**.

Sin esa red aparece un camino por el que un cuerpo se pierde para siempre y en
verde: si la subida no ocurre —token rotado, secreto caducado, un fork sin
secrets—, un vídeo nuevo existe **solo en el workspace del runner**, que git
ignora y que se destruye al acabar; y `publish` ya escribió su sha256 en el
manifiesto y en la base, así que desde mañana el guardián lo da por archivado y
no vuelve a pedirlo. Queda un sha256 sin cuerpo en ninguna parte.

Por eso esto **no avisa: falla** (sale 1) cuando hay un cuerpo que solo existe
aquí. El paso corre antes del commit, así que el archivo del día se guarda
igual y el rojo lo pone el último paso del workflow.

Y el resultado **se archiva**: los `::error::` de Actions viven fuera del
repositorio y caducan a los 90 días. Un aviso que no se archiva no cumple el
principio de archivo, así que cada corrida deja `data/auditoria_r2.json`, que el
commit del bot versiona — incluidos los días en que no se pudo auditar, porque
«ese día no pudimos mirar» también es información.

Solo stdlib (R14). Se invoca desde `.github/workflows/daily.yml` con
`R2_DISPONIBLE` y `R2_LISTADO` en el entorno.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFIESTO = ROOT / "data" / "r2_manifest.json"
MEDIA = ROOT / "data" / "media"
DESTINO = ROOT / "data" / "auditoria_r2.json"

# La misma lista que el resto del monitor; se importa para no abrir una quinta
# superficie que se separe de las otras cuatro.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ARCHIVO_EN_R2, today            # noqa: E402


def listado_del_bucket(ruta: Path) -> dict[str, int]:
    """`aws s3api ... --output text` → {clave: bytes}. Ilegible ⇒ {}."""
    real: dict[str, int] = {}
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return real
    for linea in lineas:
        partes = linea.split("\t")
        if len(partes) == 2 and partes[0]:
            try:
                real[partes[0]] = int(partes[1])
            except ValueError:
                continue
    return real


def cuerpos_en_el_workspace() -> list[str]:
    """Los A/V que están AQUÍ y que git no versiona: si no suben, se pierden."""
    try:
        return sorted(f.name for f in MEDIA.iterdir()
                      if f.name.lower().endswith(ARCHIVO_EN_R2))
    except OSError:
        return []


def auditar(manifiesto: list[dict], real: dict[str, int], locales: list[str],
            disponible: bool) -> dict:
    declarados = {o["objeto"]: o for o in manifiesto if o.get("objeto")}
    if disponible:
        faltan = sorted(k for k in declarados if k not in real)
        # Un cuerpo que está aquí y no en el bucket es el caso grave, esté o no
        # declarado: el workspace se destruye y git no lo guarda.
        solo_aqui = sorted(k for k in locales if k not in real)
        difieren = []
        for k in sorted(declarados):
            declarado = declarados[k].get("bytes")
            # Al revés: si no consta el tamaño, no se acusa a nadie
            if k in real and declarado is not None and real[k] != declarado:
                difieren.append({"objeto": k, "manifiesto": declarado,
                                 "r2": real[k]})
        sobran = sorted(set(real) - set(declarados))
    else:
        # Sin listado no se puede afirmar nada del bucket. Lo que SÍ se sabe es
        # que estos cuerpos están aquí y aquí no se quedan.
        faltan, difieren, sobran = [], [], []
        solo_aqui = list(locales)
    return {"fecha": today(), "auditado": disponible,
            "objetos_en_bucket": len(real) if disponible else None,
            "objetos_en_manifiesto": len(declarados),
            "faltan_en_r2": faltan,
            "difieren_en_tamano": difieren,
            "sobran_en_r2": sobran,
            "cuerpos_solo_en_el_workspace": solo_aqui}


def main() -> int:
    disponible = os.environ.get("R2_DISPONIBLE") == "1"
    listado = Path(os.environ.get("R2_LISTADO") or "/tmp/r2.tsv")
    try:
        manifiesto = json.loads(
            MANIFIESTO.read_text(encoding="utf-8")).get("objetos") or []
    except (OSError, ValueError, TypeError):
        # R13: si `publish` falló y no hay manifiesto, esto no puede reventar —
        # pero tampoco puede callar, porque sin manifiesto nadie declara nada.
        print("::warning::No se pudo leer data/r2_manifest.json: hoy no hay "
              "nada declarado contra lo que auditar el bucket")
        manifiesto = []
    real = listado_del_bucket(listado) if disponible else {}
    informe = auditar(manifiesto, real, cuerpos_en_el_workspace(), disponible)

    if not disponible:
        informe["motivo"] = "sin listado del bucket (¿credenciales R2?)"
        print("::warning::Sin listado del bucket: hoy no se puede afirmar nada "
              "sobre lo que R2 tiene. Queda archivado que no se pudo mirar")
    try:
        DESTINO.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    except OSError as e:
        print(f"::warning::No se pudo archivar la auditoría: {e}")

    if informe["faltan_en_r2"]:
        print(f"::error::{len(informe['faltan_en_r2'])} cuerpo(s) que el "
              f"manifiesto declara archivados NO están en R2 y no están en git: "
              f"son irrecuperables. "
              f"{', '.join(informe['faltan_en_r2'][:5])}")
    if informe["cuerpos_solo_en_el_workspace"]:
        print(f"::error::{len(informe['cuerpos_solo_en_el_workspace'])} "
              f"cuerpo(s) existen SOLO en el workspace de esta corrida: git no "
              f"los versiona y no consta que estén en R2. Cuando el runner se "
              f"apague se pierden, y el guardián los dará por archivados. "
              f"{', '.join(informe['cuerpos_solo_en_el_workspace'][:5])}")
    for d in informe["difieren_en_tamano"][:5]:
        print(f"::warning::{d['objeto']} pesa {d['r2']} en R2 y el manifiesto "
              f"declara {d['manifiesto']}")
    if informe["sobran_en_r2"]:
        print(f"::warning::{len(informe['sobran_en_r2'])} objeto(s) en R2 fuera "
              f"del manifiesto: {', '.join(informe['sobran_en_r2'][:5])}")
    print(f"Auditoría R2 ({informe['fecha']}): "
          f"{informe['objetos_en_bucket']} objetos en el bucket, "
          f"{informe['objetos_en_manifiesto']} en el manifiesto. "
          f"Archivada en data/auditoria_r2.json.")
    return 1 if (informe["faltan_en_r2"]
                 or informe["cuerpos_solo_en_el_workspace"]) else 0


if __name__ == "__main__":
    sys.exit(main())
