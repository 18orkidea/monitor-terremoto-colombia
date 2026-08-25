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

## Definition of Done (disciplina estricta)

Ningún cambio está terminado sin sus 6 casillas:

1. **Reglas**: conforme a R1–R16 y a idioma/naming.
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

### Cadencia por sprint (24-ago-2026, decisión de JP)

Las seis casillas no cambian; **cambia cuándo se cobran**. El test se escribe
**junto al código** —escribirlo después de un sprint grande es cuando salen
guardianes que no guardan— y la suite rápida se pasa a menudo porque es barata.
Lo que se cobra **por lote, al cierre de cada página o sprint**: la validación
por mutación (M1), la verificación en navegador y los tres revisores (una
revisión por sprint, con los hallazgos aplicados en una sola pasada). El riesgo
aceptado es rehacer en lote lo que una revisión tardía destape; es aceptable
porque **nada se publica sin la revisión de sprint** — sigue siendo bloqueante
antes del PR. El trabajo se paraleliza con agentes **solo sobre superficies
disjuntas** (cada agente dueño de su página); las superficies compartidas
(`styles.css`, `ui.js`, `common.js`, `seo_check.py`, docs) las integra la
coordinación, nunca dos manos a la vez.

## Reglas de método (M1–M10) — aprendidas a golpes, con su cicatriz

Las R son sobre **los datos**; estas son sobre **cómo se trabaja**. Cada una nace
de un error real que ya se cometió aquí. **Se citan por su número en las
revisiones**, igual que las R.

- **M1 · Un guardián se valida rompiendo el código, no leyéndolo.** Escribe el
  test, **mete el bug a propósito y comprueba que el test cae**; después deshaz.
  **Con `PYTHONDONTWRITEBYTECODE=1` (o `python3 -B`)**: dos mutaciones del mismo
  tamaño escritas en el mismo segundo reutilizan el `.pyc` cacheado y dan un
  **verde falso** — es decir, la validación de M1 puede mentir exactamente igual
  que el guardián que viene a comprobar. Cazado el 24-ago-2026, y casi colado.
  *Cicatriz: ha pasado cuatro veces. Un test buscaba una palabra que estaba en
  el comentario del propio autor. Otro comparaba conjuntos sobre el fichero
  entero y sobrevivía si el defecto quedaba en uno de los dos sitios. Dos
  guardianes «de sí mismos» comprobaban «la lista no está vacía», que es la
  misma trampa con otro traje.* **Si un test pasa con el fallo puesto, se tira y
  se empieza otro** — no se retoca.

- **M2 · Toda segunda copia diverge. Al encontrarla: fundir y poner un test que
  se rompa si vuelven a separarse.** *Cicatriz: en un solo día aparecieron dos
  URL declaradas dos veces con la copia muerta envejeciendo; un pie que vivía en
  Python y en JavaScript y llevaba meses siendo más pobre en 208 páginas sin que
  nadie lo viera; una identidad de autor con el nombre interno en un sitio y el
  público en otro.* Ninguna estaba mal el día que se escribió. **El daño no está
  en copiar: está en que nada vigile que las copias sigan diciendo lo mismo.**

- **M3 · Un comentario en mayúsculas no es un guardián.** Si una decisión merece
  explicarse, merece un test. *Cicatriz: tres decisiones del sistema visual
  estaban solo en comentarios enfáticos —la exclusión de los chips del eje entre
  ellas— y las tres se podían deshacer con la suite en verde.*

- **M4 · El repositorio manda sobre cualquier documento.** Planes, traspasos y
  hojas de ruta describen la intención; el código y `docs/DECISIONES.md`
  describen lo que hay. **Ante discrepancia, gana el repo.** *Cicatriz: un
  handoff afirmaba que el nombre del sitio «convivía sin decidirse» y estaba
  decidido en `DECISIONES.md`; y la línea base de la portada arrastraba 3.225
  palabras cuando eran 3.259.* **Una línea base se toma midiendo en el momento,
  nunca citando un documento.**

- **M5 · Verifica la premisa ANTES de convertirla en una pregunta.** Ofrecer una
  opción falsa hace que se decida sobre algo que no existe. *Cicatriz: se
  presentó «sin emoticonos, como las fichas» y las fichas los tenían. Hubo que
  volver a preguntar.* Si la premisa no está medida, se mide; y si no se puede,
  se dice que es una suposición.

- **M6 · Mide antes de retocar estética.** Cuando JP dice que algo se ve mal,
  **apunta casi siempre a algo más profundo de lo que señala**. *Cicatriz: «los
  prototipos dan un paso atrás» era que no cargaban `styles.css`; «no hace el
  zoom» era un GeoJSON de 199 KB bloqueando el vuelo; «faltan las cifras» era un
  contenedor que rellenaba el JS; «el encabezado se come la primera línea» era
  que `overflow-x:auto` convierte el otro eje en contenedor de scroll.*

- **M7 · Aritmética correcta no es procedencia rastreable.** Una cifra exacta
  cuyo snapshot no tiene fila en `sources_log` **no se publica**, o se publica
  con esa advertencia. *Cicatriz: un porcentaje verificado por dos vías salió de
  un fichero sin registro de quién lo pidió.* Y **toda cifra de una fuente viva
  lleva su corte**: el RUD pasó de 65.663 a 100.231 familias en dos días — sin
  fecha, una cifra miente en 48 horas.

- **M8 · Verifica por segunda vía lo que va a acabar impreso.** *Cicatriz: la
  segunda vía destapó un alias de topónimo —«Guadalajara de Buga» frente a
  «Buga»— que inflaba una cifra en 206 familias, y tirando de ese hilo apareció
  una fuga de trazabilidad.* La segunda vía no es desconfianza: es el método.

- **M9 · Lo temporal que importa no vive en un worktree.** Un worktree se borra
  sin ceremonia. Traspasos y hojas de ruta van junto a la memoria local, con
  entrada en su índice, **y lo que no se versiona se ignora explícitamente**.
  *Cicatriz: un `git add -A` habría publicado el documento que dice que nunca se
  publica, con la ruta local dentro.*

- **M10 · Omitir es lo que significa «no lo sabemos».** Vale para el JSON-LD,
  para el mapa y para la prosa: donde falta el dato **se calla el campo**, nunca
  se escribe 0. *Cicatriz: un cero en `geo` señalaría el golfo de Guinea; un
  «Copernicus entregó cero productos» acusaba a la fuente de no haber entregado
  nada cuando lo que faltaba era la clave.* Es la R3 fuera de la base de datos.

- **M11 · Si el cambio toma una dirección nueva, el vigilante cambia con él —
  y lo ya derivado, también.** Un guardián se escribió para defender la
  dirección anterior: cuando la decisión cambia, verlo en rojo **no es la
  prueba de que el cambio esté mal**, es la señal de que se quedó atrás. Y los
  datos que el código viejo ya generó siguen ahí, defendidos por él.
  *Cicatriz: R5 dejó de redondear las coordenadas de los reportes ciudadanos;
  al fusionar `main`, sus 719 reportes traían `lat_pub` redondeado por la
  corrida vieja y el guardián de trazabilidad —con toda la razón— gritaba que
  lo publicado no era lo que dijo la fuente. La salida no era quedarse con los
  datos viejos ni rebajar el test: era **recalcular lo derivado con el código
  nuevo** (1.437 coordenadas) y republicar.* Ante un guardián en rojo después
  de una decisión, la pregunta es **cuál de los dos se ha quedado viejo** — y
  hay una tercera respuesta que casi siempre falta: **el dato ya derivado**.

  **Lo que nunca vale es relajar el test para que pase**: subir un umbral,
  ampliar una tolerancia, quitar una comprobación, cambiar un `assertEqual` por
  un `assertIn`. Cambiar un guardián es reescribirlo para que defienda la
  dirección nueva **con la misma fuerza**, y volver a validarlo por M1. Si al
  terminar ya no caza nada, se dice en voz alta.

### Cómo crece esta lista (el autoaprendizaje)

1. **Un error que aparece por segunda vez deja de ser un error: es un patrón**, y
   se escribe aquí con su cicatriz. Una regla sin el incidente que la causó no se
   recuerda y acaba siendo decoración.
2. **Si el patrón es automatizable, la regla llega acompañada de su test** — y el
   test se valida por M1. Una regla que solo vive en prosa se incumple.
3. **Al cerrar una sesión relevante**, revisar si algo de lo ocurrido merece
   entrar aquí, y anotarlo también en la memoria local.
4. **Las revisiones citan estas reglas por su número.** «Esto incumple M2» tiene
   que ser una frase normal en un informe, igual que «esto incumple R3».
5. **Una regla que estorba se discute y se retira**, con su entrada en
   `docs/DECISIONES.md`. Lo que no se hace es ignorarla en silencio.

## Flujo de trabajo con agentes

idea → diseño (plan mode si toca >2 archivos) → implementación (sesión principal) →
revisión: **auditor-editorial** (qué se afirma y con qué atribución), **revisor-estilo**
(cómo está escrito: Libro de estilo de EL PAÍS con excepciones americanas, ver
`docs/DECISIONES.md`) y/o **archivista** (ingesta/datos/workflows), en paralelo →
**revisor-qa** (última puerta) → commit/PR.
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
bash deploy/build_dist.sh               # construir dist/ (artefacto de deploy)
python3 -m http.server -d dist 8123     # sitio como en producción: la raíz es dist/
```

El sitio **se sirve desde `dist/` como raíz**, igual que en producción: las páginas
viven en `/`, las fichas municipales en `/municipio/<slug>/` y los enlaces entre ellas
son absolutos. Servir el repositorio directamente devuelve 404 en cada ficha — `dist/`
es el artefacto publicado y el repositorio no lo es.
