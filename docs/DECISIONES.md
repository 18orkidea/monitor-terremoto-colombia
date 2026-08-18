# Decisiones (ADR ligero)

Historia técnica para el mantenedor: una entrada por decisión, con contexto y
consecuencia. La historia pública del monitor (hitos visibles) vive en
`feeds/hitos_monitor.json` — no duplicar.

Formato: `## AAAA-MM-DD — título` · contexto → decisión → consecuencia.

## 2026-08-16 — GitHub Pages como única vía de deploy

Contexto: existían dos pipelines divergentes (build inline en pages.yml con sitemap de
3 URLs; build_dist.sh con 5, publicando a un CF Pages que el dominio no muestra — el
CNAME de brechas.orkidea.eu apunta a 18orkidea.github.io).
Decisión: unificar en GitHub Pages; pages.yml invoca build_dist.sh; se elimina el
deploy a Cloudflare del daily. El proyecto CF Pages huérfano puede borrarse a mano en
el dashboard.
Consecuencia: un solo build, un solo sitemap; el secret CLOUDFLARE_API_TOKEN deja de
usarse para Pages.

## 2026-08-16 — sqlite fuera de git, dumps CSV versionados

Contexto: los 13 blobs del sqlite (15 MB/día, binario sin diff) eran lo más pesado del
repo (.git = 137 MB en 2 días de proyecto).
Decisión: `ingest/dump_db.py` vuelca las 12 tablas a `data/dumps/*.csv` (diffs diarios
legibles — la crónica fila a fila que un historiador puede leer con git diff) y
reconstruye el sqlite cuando falta. El daily commitea dumps, no el binario. La historia
de git NO se reescribe: lo acumulado queda como archivo.
Consecuencia: el repo deja de engordar 15 MB/día; el CI reconstruye la BD desde dumps;
los tests siguen leyendo el sqlite local.

## 2026-08-16 — Analytics se mantiene, pero declarado

Contexto: el beacon de Cloudflare Web Analytics (sin cookies) convivía sin declararse
con la regla de privacidad ciudadana — la incoherencia era lo tóxico, no el beacon.
Decisión: se mantiene y se declara en la metodología pública.
Consecuencia: coherencia editorial; el usuario puede retirarlo cuando quiera.

## 2026-08-16 — Capa social, BuyMeACoffee y aparato SEO se mantienen

Contexto: propuesta de recorte evaluada por el usuario.
Decisión: se mantienen tal cual (compartir sirve a la difusión de los datos; la
financiación mantiene servidores y scraping). El contexto secundario (sismos
históricos, índice de activaciones) se degrada a secciones colapsadas.

## 2026-08-16 — Snapshots intradía con sufijo de hash

Contexto: `fetch()` guardaba solo el primer cuerpo del día («primero del día gana»);
una segunda corrida con contenido distinto dejaba un sha256 en el log sin cuerpo
recuperable. Los binarios hacían lo contrario (sobrescribir).
Decisión: nombre de snapshot con sufijo `_<sha8>`; contenido distinto = archivo nuevo,
nunca un hash sin evidencia. Los snapshots antiguos no se migran (inmutables).
Consecuencia: la promesa «minuto a minuto» pasa de aspiracional a verificable.

## 2026-08-17 — Selección diaria de balances: estabilidad, disputa y consolidado

Contexto: el 16-ago el único snapshot no-liveblog del día fue Primicias (Ecuador) con
un corte viejo (181 fallecidos cuando el consolidado iba por 294); la regla
«no-liveblog primero» lo eligió y la serie pública retrocedió. Además, las cifras que
el ganador del día no traía desaparecían en «—».
Decisión: (1) estabilidad respecto a la víspera como PRIMER criterio — un balance
acumulado no retrocede; caídas >10 % en fallecidos/familias penalizan al candidato por
delante incluso de la marca liveblog; (2) **prensa nacional colombiana** como segundo
criterio (lista curada MEDIOS_NACIONALES en ui.js + dominios .com.co/.gov.co): los
diarios nacionales están más cerca del consolidado oficial que los medios
internacionales tardíos; (3) contradicciones >15 % entre medios del mismo día se
marcan «cifras en disputa» y se muestran — la discrepancia es información de brecha;
(4) consolidado por día: cada cifra conserva su último valor conocido con fecha de
origen marcada. Implementado en ui.js (mejorPorDia), testeado ejecutando el
JS real con node (tests/test_frontend.py) — sin réplicas en Python.
Consecuencia: los medios internacionales tardíos ya no pueden hacer retroceder la
serie ni borrar cifras; la FAQ de Balances ahora describe la regla realmente
implementada (antes prometía una estabilidad que no existía).

## 2026-08-17 — Avisos: Web Push + canal Telegram + alerts.rss, todo en free tier

Contexto: las alertas del día (RUD, balances, cambios del monitor) solo se veían
entrando al sitio.
Decisión: tres canales con un solo punto de envío y dedupe (worker nuevo
`workers/push/`, cuenta inforesidencias): (1) Web Push estándar con criptografía
vanilla WebCrypto (RFC 8291/8188/8292, ~200 líneas SIN npm) **testeada en CI contra el
vector de prueba oficial del RFC 8291 §5 ejecutando el mismo JS con node**; (2) canal
público de Telegram como camino móvil sin fricción (iOS exige PWA para Web Push);
(3) alerts.rss estático desde alerts.py (stdlib). Disparo: POST del daily con el
alerts.json fresco en el body + cron de respaldo 11:20 UTC (dedupe por sha256).
Filtrado editorial: nivel alta + rud_actualizado + balance_en_medios — titulares y
reportes diarios no queman el canal. ntfy.sh descartado: tercero sin contrato.
Consecuencia: $0/mes; límite free tier ~40 push por disparo (50 subrequests) — pasar a
Workers Paid ($5/mes) es un umbral de éxito. Segundo worker que mantener, deploy manual
documentado en su README; sin secretos configurados, todo se salta limpio.

## 2026-08-16 — Deudas anotadas (descartado hacer ahora)

- Refactor de `publish.py::run()` (236 líneas): funciona y está testado por sus
  artefactos; se partirá cuando haya que tocarlo de verdad.
- Migrar el worker de balances de la cuenta inforesidencias a una cuenta del proyecto:
  implica mover KV y secrets; mientras tanto, el snapshot diario en `feeds/balances/`
  elimina el riesgo de pérdida. Documentado en LIMITACIONES.
- SECURITY.md, plantillas de PR/issue, CHANGELOG, pre-commit hooks, dependabot,
  coverage gates: descartados — proyecto de una persona; el coste de mantenimiento no
  se paga.

## 2026-08-17 — La capa de municipios sigue al RUD, no al revés

Contexto: `ingest/municipios.py` tenía 25 municipios curados a mano (los que
aparecieron en prensa o DYFI). El RUD ya registraba 75 — y 72 de ellos no tienen
ni un edificio verificado por Copernicus: el registro oficial municipal es su
única fuente, y el monitor los estaba ignorando en la capa de municipios.
Decisión: (1) los 75 municipios del RUD entran curados al diccionario (58
nuevos; coordenadas del DIVIPOLA geolocalizado de datos.gov.co, dataset
`gdxc-w37w`, capturado como `data/public/divipola_coords.json` estático — R14
intacto: cero red en runtime); (2) estado nuevo `solo_rud` —última prioridad de
la cascada, solo cuando el RUD es literalmente la única señal— que NO toca
`crosscheck.py` ni R1/R2: el cruce sigue exigiendo producto satelital; (3) flujo
automático hacia adelante: si mañana el RUD registra un municipio nuevo,
`municipios_dinamicos()` lo incorpora solo con coordenadas del catálogo DIVIPOLA
completo (1.122 municipios), y un test de hipótesis AVISA si alguno no resuelve
coordenadas (R11: avisar, no romper); (4) la tabla del RUD y la de municipios
muestran población DANE 2026 y % de población registrada como damnificada — la
métrica que revela que Condoto tiene al 22 % de su población en el registro.
Consecuencia: las búsquedas municipales de Google News pasan de 25 a 81 feeds
diarios —los 83 del catálogo menos los dos homónimos de departamento, cuya
búsqueda no puede discriminar— (decisión del usuario: trato uniforme, un feed
en cero también es información, R13 cubre el fallo).

Corolario de calidad de dato (mismo día, tras revisión): ampliar la lista
multiplicó los topónimos ambiguos, así que R10 crece a dos niveles —
`requiere_depto` para nombres que son palabra común, lugar extranjero, apellido
frecuente o municipio repetido (Toro, Palestina, Marulanda, Riosucio…), y
`homonimo_de_departamento` para los que se llaman igual que un departamento
(Risaralda en Caldas, Córdoba en Quindío), que no reciben prensa por texto en
absoluto. Sin esto, 67 titulares del departamento de Risaralda se atribuían al
municipio de 11.000 habitantes y arrastraban la etiqueta «Caldas» a 60
noticias. Las entradas dinámicas nacen con `requiere_depto` por defecto: lo no
curado se trata con el criterio conservador. Cinco tests nuevos cubren la clase,
uno de ellos estructural contra el catálogo DIVIPOLA completo; otros dos cierran
la puerta de atrás del canal de feeds, que declara su municipio sin pasar por el
filtro de texto (los homónimos no generan búsqueda automática, y la frase que se
busca es el topónimo y no la clave del diccionario, para que ningún feed nazca
devolviendo cero en silencio). El DYFI, que no pasa por el filtro de texto,
gana su propio guardián: además de nombre único, proximidad de 30 km entre la
celda y el municipio — el USGS etiqueta con el topónimo más cercano del mundo y
la celda «Balboa» del canal de Panamá se estaba publicando como intensidad
sentida en Balboa (Risaralda), a 595 km. Y el registro oficial ya no queda
tapado por una celda DYFI floja: antes, un CDI de 5,6 mandaba al gris a Belén de
Umbría, con 2.266 damnificados registrados.

## 2026-08-17 — R10 llega al worker de balances (la última superficie sin guardián)

Contexto: al endurecer la atribución de topónimos en el pipeline (ver entrada
anterior) quedó fuera `workers/ai-view/src/index.js`, que corre en Cloudflare y
mantiene su propia lista de 25 municipios. Atribuía con `lower.includes(...)`,
sin límite de palabra: «California» contaba como Cali en `hasImpactedPlace()`
—que alimenta el filtro de contexto colombiano y por tanto decide si un
documento cuenta como evidencia del evento— y en `structureOfficialText()`, que
es lo que acaba publicado en `oficiales.json`. Medido sobre el balance archivado
del 16-ago: 2 de 15 ítems atribuían Cali por el nombre de archivo de una imagen
(`terremoto-cali_51341108.jpg`), sin que «Cali» apareciera en la prosa.

Decisión: helper `mentionsPlace()` con `\b` sobre el topónimo normalizado —el
mismo criterio que `ingest/municipios.py::_mentioned`— aplicado en los tres
puntos (municipios, departamentos y filtro de relevancia). Y un segundo criterio,
`sinEnlaces()`: el insumo es markdown de Firecrawl, donde el límite de palabra no
protege («terremoto-cali.jpg» y «/noticias/cali/» dejan el topónimo suelto). Se
descartan imágenes y URLs, pero **el texto de los enlaces se conserva** —
«[UNGRD confirma 12 fallecidos en Cali](url)» es prosa, y borrarlo entero
cambiaba un falso positivo por un falso negativo silencioso. De ese texto limpio
salen también las cifras: «mapa-900x601.jpg» daba «900 municipios afectados», y
una fecha o un id en la URL daban 202 y 513 — cifras fabricadas en un proyecto
cuyo contrato dice que cada una es rastreable. La cita y el `text_excerpt` siguen
sobre el crudo (R3: el literal se conserva). Frontera asumida: un nombre de
archivo suelto en la prosa sí atribuye, porque no hay forma limpia de separar
«foto terremoto-cali.jpg» de «el EDAN de Quibdó.pdf»; con test que la fija.

**No** se replican los dos niveles del pipeline (`requiere_depto`,
`homonimo_de_departamento`), y no por descuido: en la lista del worker no hay
ningún homónimo de departamento, y sus nombres coincidentes con lugares
extranjeros (Armenia, Montenegro, Sevilla, Cartago, Palmira, Salento) son
precisamente los del Eje Cafetero, que en un corpus de balances del sismo
colombiano casi siempre se refieren a los municipios colombianos — el terremoto
de 1999 fue en Armenia, Quindío. Con un solo día de balances archivados no hay
base para calibrar un segundo nivel, y el worker ya exige `hasEventTerm` +
`hasColombiaContext` antes de tratar un documento como evidencia. Si el archivo
crece y aparecen falsos positivos, se calibra entonces con datos.

Frontera del archivo: antes de desplegar se guardó el feed tal como lo producía
el criterio viejo en `feeds/balances/2026-08-17.json` (18 ítems, ninguno con
sello), capturado con `common.fetch` y por tanto con fila en `sources_log` y
snapshot en `data/snapshots/2026-08-17/oficiales_feed.json`. **La copia byte-fiel es el
snapshot**, cuyo sha256 es el que consta en `sources_log`; el fichero de
`feeds/balances/` es una re-serialización con indentación (mismo contenido
parseado, otro sha), a diferencia del resto de la serie, que el workflow guarda
tal como llega. Quien audite la serie con `shasum` debe usar el snapshot para
ese día. Sin ese «antes» el cambio de criterio quedaría a
dos días de distancia del commit. Cada ítem nuevo sella `atribucion_lugares`; su
ausencia significa criterio anterior, porque el worker reusa los ítems del KV sin
reanalizarlos y los snapshots no se reescriben (ver LIMITACIONES).

Desplegado el 17-ago-2026, versión de Cloudflare
`ab681aef-b8b5-4e0d-b604-89de6716af28`. Verificado sobre el feed vivo aplicando
los dos criterios al MISMO texto (el `text_excerpt` archivado; comparar contra
los municipios ya publicados sería inválido, porque esos se calcularon sobre el
documento completo): 4 de 18 ítems dejan de atribuir un municipio, y los cuatro
son enlaces — el slug `…colapsados-en-buenaventura-alcaldesa…` y la imagen
`terremoto-cali_51341108.jpg`. Ninguna atribución que venga de la prosa cambia.

La lista sigue duplicada porque el worker no puede importar el pipeline Python.
Lo que antes era duplicación silenciosa ahora tiene vigilancia: cuatro tests de
paridad (`tests/test_worker_toponimos.py`) comprueban que cada municipio del
worker existe en `ingest/municipios.py` con el mismo departamento (aceptando sus
alias: el worker lista «Dos Quebradas», que allí es topónimo de Dosquebradas),
que nunca se le cuele un homónimo de departamento, que ninguno esté marcado
`requiere_depto` en el pipeline —el día que se calibre Armenia habrá que decidir
la divergencia, no descubrirla— y que reconozca todos los alias del catálogo.
Los tests ejecutan el worker real con node (export nombrado añadido solo para ellos; Cloudflare usa el default), no
una réplica: testear copias es testear nada.

## 2026-08-18 — El archivo se guarda antes de verificar nada

Contexto: el 17-ago un HTTP 502 pasajero del DANE tumbó la corrida diaria. No
porque el pipeline dependiera del DANE —las otras doce fuentes funcionaron y
`publish` generó todo—, sino porque `run_daily.py` sale con código 1 si alguna
fuente falla, y el job abortó antes del paso que commitea. Coste: los snapshots
de ese día (2 archivados frente a 70 del anterior) y el punto del 17 en la serie
del RUD, irrecuperable. R13 promete que un feed caído no rompe la corrida, y a
nivel de paso se cumplía; a nivel de workflow, no.

Decisión: en `daily.yml` el orden pasa a ser **archivar primero, verificar
después**. La corrida lleva `continue-on-error` y el commit del snapshot va por
delante de los tests de hipótesis, de los supuestos de las APIs y de las reglas
en JavaScript; todos avisan sin tumbar el job, y un paso final pone el workflow
en rojo cuando algo falló, ya con el día guardado. En `pr.yml` los tests siguen
siendo fatales: ahí romper no cuesta archivo.

El porqué en una línea: un supuesto roto o una hipótesis caída son **noticia**
(R11, R12), no motivo para perder el día que los produjo. Y una fuente externa
con un 502 no puede llevarse por delante las otras doce.

## 2026-08-18 — La población DANE sale de la corrida diaria (pasa a anual)

Contexto: el DANE tumbó el monitor dos días seguidos (17-ago HTTP 502, 18-ago
timeout), y no solo desde los runners: reintentado desde local, también falla a
ratos. Pero lo que sirve son las proyecciones municipales PPED **2018-2042**, un
dato de referencia que no cambia de un día para otro y que ya está capturado en
`data/public/dane_population_2026.json`, versionado en git.

Decisión: `dane` sale de `run_daily.py` y pasa a un workflow propio
(`.github/workflows/dane.yml`) con cron anual (15 de enero) y
`workflow_dispatch` para lanzarlo a mano. Mismo criterio que
`ingest/build_divipola.py`: **la cadencia de captura la marca el dato, no la
comodidad de tenerlo todo en el mismo sitio**. Un servicio intermitente que
sirve un dato estático no puede poner el monitor en rojo a diario — un rojo
permanente deja de significar nada, y el aviso de R11 pierde su valor.

El workflow anual reintenta cinco veces espaciadas dos minutos, porque una
corrida que solo ocurre una vez al año no puede perderse por un timeout de 40
segundos.

Consecuencia para el archivo: al salir de la corrida, nada volvería a avisar si
el JSON versionado desapareciera. Tres tests de hipótesis nuevos
(`TestReferenciasEstaticas`) vigilan que la población y el catálogo DIVIPOLA
sigan disponibles y que ningún municipio publicado se quede sin población.

## 2026-08-18 — La página del RUD explica qué es el registro, no solo la cifra

Contexto: la página trataba el RUD como un marcador de damnificados, y no lo es. Lo
cargan las autoridades municipales y sirve para focalizar ayudas; **registrar a
una familia y evaluar el daño de su vivienda son dos momentos distintos**, y el
segundo llega después. Eso se comprueba en los propios datos: las cifras de
familias avanzan antes que las de viviendas.

Decisión: la intro explica ese desfase y qué mide cada columna — familias y
personas son impacto social; viviendas destruidas y averiadas son **lo que el
municipio ha cargado**, no una verificación independiente. Se dice además que un
cero en viviendas puede significar «todavía sin evaluar» (21 de 90 municipios
tienen cero destruidas), no «sin daño».

Precisión que costó una corrección: el primer texto decía «daño ya verificado» y
«visita de verificación». No es defendible — `ingest/sources/ungrd_rud.py` toma
`destruidas`/`averiadas` tal cual las carga la alcaldía, no hay ningún campo que
distinga verificado de cargado, y el propio glosario del sitio dice que el RUD
«no es un EDAN ni una verificación de daño». Describir el procedimiento
administrativo (visitas, certificados) exigía citar prensa; se optó por describir
**lo que el dato muestra** y no el trámite, que es lo que el monitor puede
sostener con su propio archivo.

Consecuencia directa: **se descarta el plan de «señales de anomalía»** que se
estaba diseñando. Interpretaba ese desfase como sospechoso cuando es el
funcionamiento normal del registro. Una revisión de datos lo confirmó por otra
vía: los ratios son log-normales y, aplicando la escala correcta, dos de las
cuatro señales marcaban 0 municipios de 90; una tercera resultó ser un detector
de municipios pequeños (log-log R²=0,236) y la cuarta medía criterio
departamental, no habitabilidad. La lista habría señalado desproporcionadamente
a Chocó y Risaralda —los dos departamentos más pobres— con un 11 % de rotación
diaria.
