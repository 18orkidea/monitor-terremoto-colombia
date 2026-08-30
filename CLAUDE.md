# CLAUDE.md — contrato operativo del monitor

Este archivo es la puerta de entrada de cada sesión de trabajo. Si un cambio
contradice algo de aquí, el cambio está mal o este archivo debe actualizarse
primero (y esa decisión se anota en `docs/DECISIONES.md`).

## Misión

Observatorio abierto del terremoto M7.4 de Colombia (10-ago-2026) y del ecosistema
de datos que lo rodea. **No produce cifras: audita y cruza las que existen** — quién
publica, quién calla, cuándo llega cada dato y qué queda subestimado. **Cada cifra es
rastreable hasta su petición de origen.** Ninguna fuente lo cuenta todo, y ninguna
cuenta lo mismo que otra. **La brecha es lo que queda fuera de todas.** El proyecto es un
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
- **R5** Privacidad ciudadana: **el reporte se publica en el punto que la fuente
  registró; el monitor no reposiciona nada.** ChatMap ya publica la coordenada exacta
  en su endpoint abierto, así que redondearla no protegía nada y sí engañaba: una foto
  de daño a 110 m señala la casa de enfrente. **EXIF jamás publicado, sin PII** — esa
  mitad no cambia y es la que el guardián vigila.
  `ingest/sources/chatmap.py` · `test_hipotesis.py::test_privacidad*`
- **R6** Nada se marca `validado` sin revisión humana; el score solo ordena la cola.
  `ingest/verify_citizen.py`
- **R7** Checks de verificación ciudadana A-E (MMI, AOI, temporalidad, duplicado sha256,
  medio). `verify_citizen.py:71-101`
- **R8** Liveblogs se marcan y **pesan menos, no pierden siempre**: la marca desempata
  por debajo de la atribución oficial, porque un liveblog que cita UNGRD+SGC informa
  mejor que un estático mudo. Vive en TRES superficies con `\b` —si tocas una, mira las
  otras—: `site/ui.js::isLiveblog`, `deploy/render_html.py::es_liveblog` y
  `workers/ai-view::isLiveblog`. Selección y consolidado en `site/ui.js::bestSnapshot` /
  `mejorPorDia` (fuente única de la regla; `alerts.py` la invoca con node).
  `tests/test_render_html.py::test_la_deteccion_de_liveblog_es_espejo_de_ui_js_y_del_worker`
- **R9** Prensa/web nunca se promueven a EDAN; dos niveles de atribución (publicador vs
  fuente citada). `workers/ai-view/`
- **R10** Topónimos con límite de palabra (`\b`): Cali ≠ California. Vive en TRES
  superficies —si tocas una, mira las otras—: `crosscheck.py:47` (AOIs),
  `municipios.py::_mentioned` (+ dos niveles: `requiere_depto` y
  `homonimo_de_departamento`, y la exención revisada a mano
  `TOPONIMO_REVISADO_SIN_DEPTO`, por DIVIPOLA) y `workers/ai-view::mentionsPlace`
  (+ `sinEnlaces`,
  porque el worker lee documentos con URLs dentro).
  `test_unit.py::test_cali_no_es_california` · `test_worker_toponimos.py`
- **R11** Los supuestos rotos AVISAN, no rompen en silencio — y romperse puede ser buena
  noticia. `tests/test_supuestos_api.py` · `ingest/alerts.py`
- **R12** Los tests de hipótesis son estructurales, no de cifras exactas; si una
  hipótesis cae, el monitor lo cuenta. `tests/test_hipotesis.py`
- **R13** Un feed que falla no rompe la corrida (degradación elegante).
  `ingest/run_daily.py::step`
- **R14** **Solo stdlib de Python en runtime** (urllib + sqlite3). Dev-tools en CI están
  bien; dependencias en `ingest/` no. **Única excepción: `node`**, para ejecutar reglas
  que ya viven en `site/ui.js` y no replicarlas en un segundo lenguaje —nunca para pedir
  red ni para transformar datos por su cuenta—. Si falta, se degrada avisando y no se
  publica la cifra. `ingest/alerts.py::_consolidado_de_la_serie` · `daily.yml`
- **R15** Detector de silencio: fuente que calla >48 h ⇒ alerta. `ingest/alerts.py`
- **R16** El balance consolidado **no retrocede**: una cifra entra si supera a la
  vigente, tiene atribución oficial trazable, es coherente con su balance y no supera el
  techo de salto. Se rotula «máximo informado» —los desaparecidos pueden bajar en la
  realidad— y lo rechazado se enseña con su motivo.
  `site/ui.js::consolidarDia` · `tests/test_frontend.py::TestConsolidadoMonotono`

## Principio de archivo

**Nada se publica sin snapshot + sha256 + fila en `sources_log`. Los snapshots son
inmutables: no se sobrescriben ni se migran.** Y **nada que sea contenido que no
cambia se archiva más de una vez: es un activo, no un dato archivable** — quien
decide si hay que traer algo pregunta al archivo, nunca al sistema de ficheros,
que en la máquina de la corrida arranca vacío de todo lo que git ignora.
`ingest/common.py::activo_archivado` · `test_unit.py::TestActivosDelArchivo`

### Dos capas, y solo una es inmutable

Lo de arriba habla de **lo que la fuente dijo**: eso no se toca nunca. **Cómo lo
enseñamos nosotros es otra capa, y esa sí se corrige.**

> **Si encontramos un error en la manera en que mostramos los datos, se corrige.
> Esto manda sobre conservar la versión equivocada. Los cambios no se archivan:
> se documentan en git, que es su sitio — y los datos se arreglan para que
> correspondan.**

Un dato mal derivado, mal redondeado o mal rotulado **no es archivo histórico:
es un error nuestro**, y dejarlo puesto para «no tocar el pasado» publica una
falsedad con aspecto de registro. El snapshot original sigue ahí para demostrar
qué dijo la fuente; el commit demuestra qué corregimos y cuándo. **Las dos
trazas se conservan; lo que se arregla es lo publicado.**

Confundir las dos capas es fácil y ya pasó: se llegó a defender un redondeo
equivocado apelando a la inmutabilidad de los snapshots, que no tenían nada que
ver. **Ante la duda: ¿esto es lo que dijo la fuente, o lo que hicimos nosotros
con lo que dijo?** Lo primero es intocable. Lo segundo es responsabilidad
nuestra y se corrige.

Toda fuente nueva necesita, desde el día uno: snapshot diario, test de supuesto y
plan de sucesión (¿qué pasa si muere? ¿merece Wayback? ¿hay export dedicado tipo
`rud.json`?). Las lagunas conocidas se documentan en `docs/LIMITACIONES.md` — un
archivo honesto documenta lo que no tiene.

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

## Definition of Done

Ningún cambio está terminado sin sus casillas:

1. **Reglas**: conforme a R1–R16 y a idioma/naming.
2. **Test**: comportamiento nuevo ⇒ test nuevo (unit/hipótesis/supuesto según
   capa); bug corregido ⇒ el test que lo habría cazado. Suite en verde:
   `python3 -m unittest discover -s tests`. **Ningún test fija a mano una
   fecha o una cifra de una serie viva** (RUD, titulares, balances — todo lo
   que el snapshot diario de mañana puede mover): prueba comportamiento sobre
   un fixture sintético propio, o afirma una propiedad estructural del dato
   real («para todo X, existe Y»). Lo fijado a mano solo vale si está atado a
   un snapshot inmutable por su sha256 (docs/DECISIONES.md, 30-ago-2026).
3. **Documentación**: README/`docs/ARQUITECTURA.md`/CONTRIBUTING si cambió el
   comportamiento; `docs/DECISIONES.md` si hubo decisión; hito en
   `feeds/hitos_monitor.json` si es visible al público.
4. **Trazabilidad**: dato nuevo ⇒ snapshot + sha256 + `sources_log`.
5. **Verificación**: suite en verde y las páginas comprobadas en navegador si
   se tocó `site/`.

El método de trabajo —cómo se valida un test, cómo se reparte un sprint, qué
revisiones pasa un cambio antes de entrar— vive en `documentos/METODO.md`,
que no se versiona.

## Comandos

```bash
python ingest/run_daily.py              # corrida diaria completa
python3 -m unittest discover -s tests   # toda la suite
bash deploy/build_dist.sh               # construir dist/ (artefacto de deploy)
python3 -m http.server -d dist 8123     # sitio como en producción: la raíz es dist/
```

El sitio **se sirve desde `dist/` como raíz**, igual que en producción: las páginas
viven en `/`, las fichas municipales en `/municipio/<slug>/` y los enlaces entre ellas
son absolutos. Servir el repositorio directamente devuelve 404 en cada ficha — `dist/`
es el artefacto publicado y el repositorio no lo es.
