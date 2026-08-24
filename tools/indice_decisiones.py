"""Índice de decisiones y documentación ↔ código. Solo stdlib (R14).

`docs/DECISIONES.md` son 62 entradas y ~44.000 tokens: leerlo para saber si algo
se decidió ya es carísimo, y `grep` sobre él devuelve el párrafo suelto sin
decir a qué entrada pertenece ni si sigue en pie. Este índice contesta en ~100
tokens: qué se decidió sobre una regla, sobre un fichero o sobre una función, y
—lo que más vale— **si lo que la decisión dice del código sigue siendo cierto**.

No es un grafo de llamadas (eso es `grafo_codigo.py`, para preguntas de forma).
Aquí los nodos son DECISIONES, reglas y documentos, y las aristas son las
menciones al código que las encarna.

## Por qué la orden `punteros` NO es la que justifica esto

M4 dice que el repositorio manda sobre cualquier documento, y este proyecto ya
se ha mordido dos veces con lo mismo: una hoja de ruta que daba por abierto algo
decidido, y una línea base que envejeció en una tarde. Una decisión que cita
`funcion()` o `ruta.py` y esos ya no existen **no es historia: es una trampa**,
porque se lee como vigente. `punteros` los saca en una lista **para revisar a mano**: en un documento de
decisiones, citar un nombre viejo es legítimo cuando se está contando el
renombrado. Su primera versión, que además miraba `data/`, sacó 24 hallazgos y
los 24 eran falsos —esos ficheros los genera la corrida—. Acotada al código y
con las clases contempladas, saca dos, de los cuales uno era real. **El ahorro
de esta herramienta está en las otras tres órdenes**, no en esta.

Se construye al vuelo, como el otro: nada que versionar, nada que caduque.

Uso:
    python3 tools/indice_decisiones.py regla R8
    python3 tools/indice_decisiones.py sobre render_html.py
    python3 tools/indice_decisiones.py buscar redondeo
    python3 tools/indice_decisiones.py punteros
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = ("docs/DECISIONES.md", "docs/LIMITACIONES.md", "docs/ARQUITECTURA.md",
        "CLAUDE.md", "README.md", "CONTRIBUTING.md")
RE_REGLA = re.compile(r"\b([RM])(\d{1,2})\b")
# Las extensiones LARGAS primero: en una alternancia, `js` casa antes que `json`
# y `balances.json` se leía como `balances.js` — la herramienta que existe para
# cazar documentación falsa inventaba ficheros inexistentes. El `(?![\w.])` cierra
# el final, el `\.?` admite `.github/…` y el `(?<![/\w.])` impide morder el final
# de una URL (`datosdelterremoto.org/balances.html` daba `org/balances.html`).
RE_FICHERO = re.compile(
    r"(?<![/\w.])(\.?[\w][\w/-]*\.(?:json|html|yml|css|md|py|js|sh))(?![\w.])")
RE_FUNCION = re.compile(r"`([a-z_][\w]*)\(\)`|`[\w.]+::([\w]+)`")


def entradas(raiz: Path = RAIZ) -> list[dict]:
    """Cada `## …` de los documentos, con lo que menciona del código."""
    fuera = []
    for doc in DOCS:
        f = raiz / doc
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8")
        trozos = re.split(r"^(##+ .+)$", txt, flags=re.M)
        # trozos: [preámbulo, titulo1, cuerpo1, titulo2, cuerpo2, …]
        for i in range(1, len(trozos) - 1, 2):
            titulo, cuerpo = trozos[i].lstrip("# ").strip(), trozos[i + 1]
            fuera.append({
                "doc": doc, "titulo": titulo,
                "linea": txt[:txt.index(trozos[i])].count("\n") + 1,
                "reglas": sorted({f"{a}{int(b)}" for a, b in RE_REGLA.findall(cuerpo)}),
                "ficheros": sorted(set(RE_FICHERO.findall(cuerpo))),
                "funciones": sorted({a or b for a, b in RE_FUNCION.findall(cuerpo)}),
                "cuerpo": cuerpo})
    return fuera


def _existe_fichero(ruta: str, raiz: Path) -> bool:
    return (raiz / ruta).exists()


BUILTINS = {"bool", "int", "str", "float", "len", "print", "round", "sum",
            "min", "max", "sorted", "set", "dict", "list", "open", "range"}


def _existe_funcion(nombre: str, raiz: Path) -> bool:
    if nombre in BUILTINS:      # `bool()` en una frase no es código del proyecto
        return True
    for d in ("deploy", "ingest", "site", "tests", "tools", "workers"):
        for f in (raiz / d).rglob("*") if (raiz / d).exists() else []:
            if f.suffix in (".py", ".js") and f.is_file():
                try:
                    # `class` también: las decisiones citan clases de test por su
                    # nombre («lo vigila TestActivosDelArchivo»), y sin esto la
                    # herramienta las daba por desaparecidas — tres falsos de
                    # cuatro en la primera pasada.
                    if re.search(rf"(?:def|function|const|class)\s+{re.escape(nombre)}\b",
                                 f.read_text(encoding="utf-8")):
                        return True
                except (UnicodeDecodeError, OSError):
                    continue
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    orden = argv[1]
    todas = entradas()
    if orden == "regla" and len(argv) > 2:
        r = argv[2].upper()
        hits = [e for e in todas if r in e["reglas"]]
        print(f"{r}: {len(hits)} decisiones o secciones")
        for e in hits:
            print(f"  {e['doc']}:{e['linea']} — {e['titulo'][:78]}")
    elif orden == "sobre" and len(argv) > 2:
        clave = argv[2]
        hits = [e for e in todas
                if any(clave in x for x in e["ficheros"] + e["funciones"])]
        print(f"«{clave}»: {len(hits)} decisiones lo mencionan")
        for e in hits:
            print(f"  {e['doc']}:{e['linea']} — {e['titulo'][:78]}")
    elif orden == "buscar" and len(argv) > 2:
        t = argv[2].lower()
        hits = [e for e in todas if t in e["cuerpo"].lower() or t in e["titulo"].lower()]
        print(f"«{t}»: {len(hits)} entradas")
        for e in hits:
            print(f"  {e['doc']}:{e['linea']} — {e['titulo'][:78]}")
    elif orden == "punteros":
        # SOLO sobre código, nunca sobre `data/` ni `feeds/`: esos ficheros los
        # genera la corrida y no estar en un clon limpio es lo normal. La
        # primera versión los incluía y sacaba 24 «hallazgos», los 24 falsos
        # —`data/auditoria_r2.json` lo escribe `auditar_r2.py`, y las lagunas de
        # LIMITACIONES citan a propósito ficheros que NO existen—. Una
        # herramienta que existe para cazar documentación falsa no puede ser la
        # que grita en falso.
        # **Se revisa a mano, y con criterio.** En un documento de decisiones
        # citar un nombre viejo es LEGÍTIMO —la entrada que cuenta un renombrado
        # tiene que nombrar las dos cosas—, así que esta lista no es de errores:
        # es de sitios donde mirar si la cita está en PRESENTE. De los tres que
        # sacó la primera vez, uno era un puntero muerto de verdad, otro era
        # historia bien contada y el tercero una constante que sí existe.
        print("Documentación que nombra código ausente "
              "(revisar a mano: citar el pasado es legítimo):")
        rotas = 0
        for e in todas:
            faltan_f = [x for x in e["ficheros"]
                        if "/" in x and not _existe_fichero(x, RAIZ)
                        and x.split("/")[0] in ("deploy", "ingest", "site",
                                                "tests", "tools", "workers")]
            faltan_fn = [x for x in e["funciones"]
                         if not _existe_funcion(x, RAIZ)]
            if faltan_f or faltan_fn:
                rotas += 1
                print(f"  {e['doc']}:{e['linea']} — {e['titulo'][:60]}")
                if faltan_f:
                    print(f"      fichero: {', '.join(faltan_f[:4])}")
                if faltan_fn:
                    print(f"      función: {', '.join(faltan_fn[:6])}")
        print(f"  → {rotas} de {len(todas)} entradas apuntan a código que no está")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
