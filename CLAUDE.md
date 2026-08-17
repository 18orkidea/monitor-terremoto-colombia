# CLAUDE.md — contrato operativo del monitor

Este archivo es la puerta de entrada de cada sesión de trabajo. Si un cambio
contradice algo de aquí, el cambio está mal o este archivo debe actualizarse
primero (y esa decisión se anota en `docs/DECISIONES.md`).

## Misión

Observatorio abierto del terremoto M7.4 de Colombia (10-ago-2026) y del ecosistema
de datos que lo rodea. **No produce cifras: audita y cruza las que existen** — quién
publica, quién calla, cuándo llega cada dato y qué queda subestimado. **Cada cifra es
rastreable hasta su petición de origen.** Que los números de las fuentes no coincidan
no es un error: **la distancia entre ellos ES la brecha de reporte**. El proyecto es un
**archivo vivo**: dentro de años, un historiador debe poder reconstruir minuto a minuto
lo que sucedió, con todas las fuentes. El día que lo oficial publique todo en abierto,
este monitor quedará **felizmente obsoleto** — ese es el éxito.

## Reglas de rigor (no negociables — con su código y su test)

- **R1** «Coincide» exige evidencia oficial (EDAN/entidad estatal) Y producto satelital
  con stats; prensa y ciudadanos solo alcanzan estados intermedios.
  `ingest/crosscheck.py:142` · `tests/test_unit.py::TestCrosscheckReglas`
- **R2** Sin producto satelital no hay cruce, aunque haya oficial. `crosscheck.py:143`
- **R3** Los «NA» de las fuentes son NULL + literal crudo, jamás 0.
  `ingest/common.py::to_num` · `test_unit.py::test_na_nunca_es_cero`
- **R4** Toda petición HTTP pasa por `common.fetch()` → `sources_log` (URL, HTTP,
  sha256, ts) + snapshot inmutable. Ninguna fuente llama a la red por su cuenta.
- **R5** Privacidad ciudadana: coordenadas públicas ~110 m (`lat_pub/lon_pub`), EXIF
  jamás publicado, sin PII. `ingest/sources/chatmap.py` · `test_hipotesis.py::test_privacidad*`
- **R6** Nada se marca `validado` sin revisión humana; el score solo ordena la cola.
  `ingest/verify_citizen.py`
- **R7** Checks de verificación ciudadana A-E (MMI, AOI, temporalidad, duplicado sha256,
  medio). `verify_citizen.py:71-101`
- **R8** Liveblogs se marcan y pesan menos; la serie elige el mejor snapshot no-liveblog.
  `site/ui.js::isLiveblog/bestSnapshot` (fuente única en el frontend)
- **R9** Prensa/web nunca se promueven a EDAN; dos niveles de atribución (publicador vs
  fuente citada). `workers/ai-view/`
- **R10** Topónimos con límite de palabra (`\b`): Cali ≠ California. Vive en TRES
  superficies —si tocas una, mira las otras—: `crosscheck.py:47` (AOIs),
  `municipios.py::_mentioned` (+ dos niveles: `requiere_depto` y
  `homonimo_de_departamento`) y `workers/ai-view::mentionsPlace` (+ `sinEnlaces`,
  porque el worker lee documentos con URLs dentro).
  `test_unit.py::test_cali_no_es_california` · `test_worker_toponimos.py`
- **R11** Los supuestos rotos AVISAN, no rompen en silencio — y romperse puede ser buena
  noticia. `tests/test_supuestos_api.py` · `ingest/alerts.py`
- **R12** Los tests de hipótesis son estructurales, no de cifras exactas; si una
  hipótesis cae, el monitor lo cuenta. `tests/test_hipotesis.py`
- **R13** Un feed que falla no rompe la corrida (degradación elegante).
  `ingest/run_daily.py::step`
- **R14** **Solo stdlib de Python en runtime** (urllib + sqlite3). Dev-tools en CI están
  bien; dependencias en `ingest/` no.
- **R15** Detector de silencio: fuente que calla >48 h ⇒ alerta. `ingest/alerts.py`

## Principio de archivo

**Nada se publica sin snapshot + sha256 + fila en `sources_log`. Los snapshots son
inmutables: no se sobrescriben ni se migran.** Toda fuente nueva necesita, desde el
día uno: snapshot diario, test de supuesto y plan de sucesión (¿qué pasa si muere?
¿merece Wayback? ¿hay export dedicado tipo `rud.json`?). Las lagunas conocidas se
documentan en `docs/LIMITACIONES.md` — un archivo honesto documenta lo que no tiene.

## Idioma y naming

- Docs, comentarios, mensajes de commit y textos del sitio: **español** (con tildes).
- Identificadores: **inglés para infraestructura genérica** (`fetch`, `run`, `parse`,
  `build`), **español para el dominio del desastre** (`municipio`, `familias`, `brecha`,
  `balance`, `hito`, `supuesto`). Este criterio aplica solo hacia adelante: **prohibido
  renombrar columnas de las tablas sqlite sin migración** — no compensa.
- Números en el sitio: locale `es-CO` vía `UI.fmt` (nunca `toLocaleString` a mano).

## Commits

Primera línea en español: **qué + porqué editorial** (ej.: «rud.json dedicado: el
histórico del RUD sobrevive aunque la fuente muera»). El porqué técnico va al cuerpo.
No formatear código en masa: el blame también es archivo.

## Definition of Done (disciplina estricta)

Ningún cambio está terminado sin sus 6 casillas:

1. **Reglas**: conforme a R1–R15 y a idioma/naming.
2. **Test**: comportamiento nuevo ⇒ test nuevo (unit/hipótesis/supuesto según capa);
   bug corregido ⇒ el test que lo habría cazado. Suite en verde:
   `python3 -m unittest discover -s tests`.
3. **Documentación**: README/`docs/ARQUITECTURA.md`/CONTRIBUTING si cambió el
   comportamiento; `docs/DECISIONES.md` si hubo decisión; hito en
   `feeds/hitos_monitor.json` si es visible al público.
4. **Trazabilidad**: dato nuevo ⇒ snapshot + sha256 + `sources_log` (revisa el agente
   archivista).
5. **Verificación**: agente revisor-qa en verde (tests + las 5 páginas en navegador si
   se tocó `site/`).
6. **Memoria**: anotación en la memoria local si hubo decisión o hallazgo no derivable
   del código.

## Flujo de trabajo con agentes

idea → diseño (plan mode si toca >2 archivos) → implementación (sesión principal) →
revisión: **auditor-editorial** (textos/cifras visibles) y/o **archivista** (ingesta/
datos/workflows), en paralelo → **revisor-qa** (última puerta) → commit/PR.
Alta de fuente nueva: usar la skill `nueva-fuente` (checklist completa).

## Memoria de trabajo (solo este ordenador)

Las notas, decisiones de sesión y anotaciones personales viven en la memoria local de
Claude (`~/.claude/projects/-Users-jpcorrea-Proyectos-Mapa-terremoto-Colombia/memory/`),
como grafo: un archivo por nota, enlaces `[[nombre]]`, índice en `MEMORY.md`.
**Nunca se commitean notas personales al repo público.** En `.claude/` solo se
versionan `launch.json`, `agents/` y `skills/`.

## Comandos

```bash
python ingest/run_daily.py              # corrida diaria completa
python3 -m unittest discover -s tests   # toda la suite
python -m http.server -d . 8123         # sitio en http://localhost:8123/site/
bash deploy/build_dist.sh               # construir dist/ (artefacto de deploy)
```
