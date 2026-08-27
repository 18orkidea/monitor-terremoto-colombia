"""Grafo de llamadas del monitor, para preguntas de FORMA. Solo stdlib (R14).

Responde barato lo que `grep` responde caro o no responde: qué se rompe si
cambio esta función, por qué camino llega A hasta B, quién llama a quién.
Medido sobre este repositorio: «¿qué depende de `fmt`?» son ~3.800 tokens de
`grep` frente a ~140 por aquí, y el camino de `render_ficha` a `pct` pasa de
nueve líneas sueltas a tres cadenas concretas.

**No se versiona el grafo, se construye al vuelo** (medio segundo sobre el repo
entero). Un índice guardado caduca en silencio, y un índice caducado que
responde con seguridad es peor que no tenerlo: es un documento que contradice
al repositorio, con otro traje.

## Lo que este grafo NO ve, y hay que saberlo antes de creerle

1. **Resuelve las llamadas por NOMBRE**, así que dos funciones homónimas en
   ficheros distintos se confunden: `gen_og.fmt` y `render_html.fmt` son
   distintas y el grafo las emparenta. Da falsos positivos de impacto.
2. **No ve el despacho dinámico**, que es el mecanismo central de este build:
   los generadores de `inyectar_prerenderizado` se llaman desde un diccionario,
   no por su nombre, así que el grafo los cree huérfanos. Para cobertura real
   hay que EJECUTAR: medido, las 95 funciones públicas de `render_html` se
   ejecutan en la suite, y este grafo declaraba once sin test.
3. **No indexa cadenas.** Para «¿dónde se publica este texto?», `grep`, siempre.

Y la lección que costó la primera versión: **la clase forma parte de la
identidad**. Sin ella, los cuarenta `setUpClass` del fichero de tests colapsan
en un nodo y el grafo contesta con seguridad sobre un método que no es el que
se le preguntó — la misma trampa que un merge que fusiona clases homónimas.

Uso:
    python3 tools/grafo_codigo.py impacto render_html.fmt
    python3 tools/grafo_codigo.py camino render_html.render_ficha render_html.pct
    python3 tools/grafo_codigo.py llaman render_html.satelites_con_dato
"""
from __future__ import annotations

import ast
import re
import sys
from collections import deque
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES_PY = ("deploy", "ingest", "tests")


def _clave(modulo: str, clase: str | None, nombre: str) -> str:
    return f"{modulo}.{clase + '.' if clase else ''}{nombre}"


def construir(raiz: Path = RAIZ) -> tuple[dict, list]:
    """Nodos (funciones) y aristas (llamadas) de todo el repositorio."""
    nodos: dict[str, dict] = {}
    crudas: list[tuple[str, str]] = []
    ficheros = [f for d in FUENTES_PY for f in sorted((raiz / d).rglob("*.py"))]
    for fichero in ficheros:
        try:
            arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        modulo = fichero.stem
        padre = {id(h): c.name for c in ast.walk(arbol)
                 if isinstance(c, ast.ClassDef) for h in c.body
                 if isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for n in ast.walk(arbol):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            k = _clave(modulo, padre.get(id(n)), n.name)
            nodos[k] = {"fichero": str(fichero.relative_to(raiz)),
                        "linea": n.lineno, "nombre": n.name,
                        "clase": padre.get(id(n))}
            for h in ast.walk(n):
                if isinstance(h, ast.Call):
                    f = h.func
                    llamada = (f.id if isinstance(f, ast.Name)
                               else f.attr if isinstance(f, ast.Attribute) else None)
                    if llamada:
                        crudas.append((k, llamada))
    for f in sorted((raiz / "site").glob("*.js")):
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(
                r"^\s*(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:\([^)]*\)|\w+)\s*=>)",
                txt, re.M):
            nombre = m.group(1) or m.group(2)
            nodos[f"{f.stem}.{nombre}"] = {
                "fichero": str(f.relative_to(raiz)), "clase": None,
                "linea": txt[:m.start()].count("\n") + 1, "nombre": nombre}
    por_nombre: dict[str, list[str]] = {}
    for k, v in nodos.items():
        por_nombre.setdefault(v["nombre"], []).append(k)
    aristas = [(o, d) for o, nombre in crudas
               for d in por_nombre.get(nombre, []) if d != o]
    return nodos, aristas


def _entrantes(aristas):
    r: dict[str, list[str]] = {}
    for o, d in aristas:
        r.setdefault(d, []).append(o)
    return r


def _salientes(aristas):
    r: dict[str, list[str]] = {}
    for o, d in aristas:
        r.setdefault(o, []).append(d)
    return r


def impacto(clave: str, nodos: dict, aristas: list) -> dict[str, int]:
    """Qué depende de `clave`, con su distancia en saltos."""
    ent, visto, cola = _entrantes(aristas), {}, deque([(clave, 0)])
    while cola:
        n, d = cola.popleft()
        if n in visto:
            continue
        visto[n] = d
        for p in ent.get(n, []):
            cola.append((p, d + 1))
    visto.pop(clave, None)
    return visto


def camino(origen: str, destino: str, aristas: list, tope: int = 3) -> list[list[str]]:
    """Hasta `tope` cadenas de llamadas de `origen` a `destino`."""
    sal, cola, hallados = _salientes(aristas), deque([[origen]]), []
    while cola and len(hallados) < tope:
        ruta = cola.popleft()
        if ruta[-1] == destino:
            hallados.append(ruta)
            continue
        if len(ruta) > 6:
            continue
        for n in sal.get(ruta[-1], []):
            if n not in ruta:
                cola.append(ruta + [n])
    return hallados


def _corto(k: str) -> str:
    return k.split(".")[-1]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    nodos, aristas = construir()
    orden, objetivo = argv[1], argv[2]
    if objetivo not in nodos:
        parecidos = [k for k in nodos if _corto(k) == objetivo.split(".")[-1]]
        print(f"no conozco «{objetivo}»." +
              (f" ¿Querías {parecidos[:5]}?" if parecidos else ""))
        return 1
    if orden == "impacto":
        dep = impacto(objetivo, nodos, aristas)
        prod = {k: d for k, d in dep.items()
                if not nodos[k]["fichero"].startswith("tests")}
        print(f"«{objetivo}»: {len(dep)} dependientes "
              f"({len(prod)} de producción, {len(dep) - len(prod)} de tests)")
        for salto in sorted(set(prod.values())):
            cuales = sorted(_corto(k) for k, d in prod.items() if d == salto)
            print(f"  a {salto} salto(s): {', '.join(cuales)}")
        print(f"  ficheros: {sorted({nodos[k]['fichero'] for k in prod})}")
    elif orden == "camino":
        for r in camino(objetivo, argv[3], aristas) or [["(sin camino)"]]:
            print("  " + " → ".join(_corto(x) for x in r))
    elif orden == "llaman":
        ent = _entrantes(aristas).get(objetivo, [])
        print(f"«{objetivo}» lo llaman {len(ent)}:")
        for k in sorted(ent):
            print(f"  {k}  ({nodos[k]['fichero']}:{nodos[k]['linea']})")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
