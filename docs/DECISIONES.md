# Decisiones (ADR ligero)

Historia técnica para el mantenedor: una entrada por decisión, con contexto y
consecuencia. La historia pública del monitor (hitos visibles) vive en
`feeds/hitos_monitor.json` — no duplicar.

Formato: `## AAAA-MM-DD — título` · contexto → decisión → consecuencia.

## 2026-08-21 — El RUD separa el total acumulado de las altas entre capturas

Contexto: la curva solo mostraba el total acumulado. Permitía saber cuánto llevaba el
registro, pero ocultaba el ritmo: el lector tenía que restar dos etiquetas para descubrir
cuántas familias habían entrado desde la víspera.

Decisión: el mismo gráfico conserva la línea acumulada y añade columnas con la diferencia
neta frente a la captura anterior. Ambas usan la misma escala. Cada columna escribe su valor
con signo y mantiene forma y texto propios para no depender del color. La primera captura no
se convierte en un alta diaria: se marca «sin base», porque no existe un cierre anterior y
atribuir sus 21.275 familias al 16 de agosto inventaría una precisión que la fuente no da.
Una corrección a la baja conserva su signo y se distingue como tal, nunca se reemplaza por
cero.

Consecuencia: en una sola lectura se ven el volumen total y el ritmo de incorporación al
RUD. El SVG explica las dos series en texto accesible y la página declara cómo se calcula la
columna.

## 2026-08-21 — El histórico del RUD es acumulativo y no puede encogerse

Contexto: las capturas de los cierres del 18 y 19 de agosto seguían archivadas, pero sus
filas desaparecieron de `rud_daily.csv`. Un merge con una rama atrasada retiró 218 claves;
después, un SQLite local que no había incorporado el último dump sustituyó el día 19 por el
20. El gráfico no ocultaba puntos: el producto público ya recibía una serie amputada.

Decisión: se restauran las filas municipales desde los cuerpos archivados, sin interpolar
cifras. Al abrir una base existente, `rebuild` reincorpora las claves acumulativas que le
falten; antes de escribir un dump, se rechaza cualquier operación que retire una clave
histórica del RUD o una entrada de su registro de procedencia. Un test exige además
continuidad entre la primera y la última captura.

Consecuencia: una base local atrasada falla de forma visible en vez de reescribir el archivo,
y un merge que vuelva a perder un día rompe CI. Los cierres recuperados son 18-ago: 51.827
familias en 106 municipios; 19-ago: 65.663 familias en 120 municipios.

## 2026-08-21 — Dos vistas municipales, con el mapa pesado bajo demanda

Contexto: cada ficha municipal ofrecía un SVG pequeño que explicaba la posición del
municipio, el epicentro, las zonas de Copernicus y los reportes próximos. El SVG enlazaba
a la portada para explorar los puntos, lo que sacaba al lector de la ficha. Incorporar el
mapa nacional completo en cada una de las fichas habría obligado a descargar Leaflet y
varios GeoJSON de alcance nacional aunque nadie pidiera esa exploración.

Decisión: las fichas que tienen al menos un punto satelital o ciudadano ofrecen dos vistas:
**Situación**, el SVG estático e indexable que queda activo por defecto, y **Mapa de
evidencias**, un Leaflet que solo se inicia al abrir su pestaña. El build genera un JSON por
municipio con sus puntos Copernicus, UNITAR-UNOSAT, ICube-SERTIT y ChatMap, además de los
polígonos Copernicus directamente relacionados. Las fuentes son capas separadas porque
pueden señalar el mismo edificio y no se deben sumar. Las fichas sin puntos no muestran
pestañas ni cargan JavaScript ejecutable; en ellas, el SVG conserva el enlace al mapa de la
portada. En las fichas con evidencias, el SVG deja de ser enlace porque la exploración está
en la pestaña contigua. Sin JavaScript, la situación completa permanece visible y se ofrece
un enlace alternativo al mapa de la portada.

Se descarta por ahora una tercera vista de imágenes satelitales: los tres servicios publican
productos y evidencias derivadas, pero no entregan de manera uniforme una escena raster
georreferenciada y redistribuible. Llamarla imagen o superponer un PDF/JPG cartográfico como
si fuera una capa introduciría una precisión falsa.

Consecuencia: la ficha conserva su peso y su lectura documental inicial, pero permite
explorar sus evidencias sin abandonar la página. La coordenada ciudadana sigue siendo la
redondeada para publicación; la atribución y el vocabulario propio de cada servicio viajan
hasta cada globo del mapa.

## 2026-08-21 — El balance no retrocede, y cada cifra dice de quién es

Contexto: el sitio publicaba **11.132 familias afectadas** donde el RUD registraba
65.663, y se contradecía consigo mismo entre dos páginas. Cuatro fallos encadenados,
todos con el mismo origen: **la serie estaba fechada por `search_date`, que es la fecha
que se le pidió al buscador, no la del balance**. El mismo artículo de El Tiempo figuraba
como el corte del 12, el 14, el 15 y el 18 de agosto. El 19-ago entraron tres capturas y
las tres eran viejas —del 10, el 11 y el 14—: ese día no hubo balance nuevo, y el sitio
estaba obligado a enseñar uno. Sucede a la decisión de 2026-08-17, cuya regla resultó
insuficiente por comparar contra el ítem de la víspera y no contra el consolidado.

Decisión, en cinco piezas:

1. **Monotonía total**: ninguna cifra del balance baja, y una cifra entra solo si supera
   a la vigente, tiene atribución oficial trazable, es coherente con el resto de su
   balance y no da un salto mayor de ×5. Lo rechazado **se enseña con su motivo**: la
   discrepancia es brecha (R12), no un error que ocultar.
2. **Se rotula «máximo informado»**, no «cifra actual». Los desaparecidos SÍ bajan en la
   realidad cuando aparece gente viva; con monotonía total —decisión explícita— llamarlos
   «actuales» sería afirmar algo que el monitor no sabe. El corolario asumido es que una
   corrección oficial a la baja (294 → 289 fallecidos el 17-ago) queda congelada y
   aparece entre las cifras descartadas.
3. **El techo de salto es obligatorio, no un adorno**: con monotonía, un error de
   extracción al alza sería permanente, y el worker ya produjo un «900 municipios» desde
   el nombre de una imagen. Se marca, no se descarta en silencio.
4. **La marca de liveblog baja por debajo de la atribución oficial**. R8 dice que se
   marcan y pesan menos, no que pierdan siempre: un liveblog que cita a la UNGRD y al SGC
   informa mejor que un estático mudo. Sigue penalizado entre iguales.
5. **Vigilante de extracción con reintento** en el worker: si las cifras rompen una
   relación imposible se reintenta sobre el texto crudo —otra entrada, no la misma dos
   veces— y al segundo fallo se desestima la cifra culpable, conservando el resto.

Dos decisiones de diseño que conviene no deshacer sin leer esto:

- **La vitrina y lo publicado se acumulan por separado.** `maximos` recoge todo lo visto
  y sirve para detectar el corte viejo; `consolidado` es lo que se publica y exige
  atribución. Fundirlos deja sin referencia los días en que ninguna fuente es atribuible,
  que es exactamente como entró el 11.132.
- **El consolidado se compone por cifra, no por ítem ganador.** Las 134.342 viviendas
  averiadas del boletín oficial del 18-ago se perdían si solo se miraba al ganador.

Consecuencia: con el corpus real, el 18-ago pasa a publicar 123.789 familias y 304
fallecidos —lo que el push ya venía anunciando por su cuenta—, y el 19-ago conserva el
consolidado en vez de hundirlo. `alerts.py` deja de tener su propia regla: llama a
`site/ui.js` con node, porque con la suya habría anunciado «180 fallecidos (-124 vs día
anterior)», o sea 124 resucitados. Si node falta, no se publica cifra con otra regla: se
avisa (R11, R13).

**Fronteras de despliegue:** el worker con las reglas nuevas se desplegó el
**2026-08-21 a las 09:06:28 UTC**, versión de Cloudflare
`20277ba9-9609-4554-86ca-a9efef8cdb68`. La corrida de las 09:17 UTC ya produjo ítems
con `extraccion_version: 2`, `fecha_corte` y `publicado_en`, pero destapó que la cabecera
global aún se rotulaba `2026-08-17-r10` y declaraba el criterio anterior. El sello se
corrigió y se redesplegó a las **09:19:36 UTC**, versión
`a156e546-cf4a-49e5-8cca-73c503a11077`, con cabecera
`2026-08-21-balance-v2` y `texto_sin_enlaces_v2`. Los ítems anteriores a la primera
frontera no deben atribuirse a estas reglas solo por la fecha del feed.

Pendiente declarado: **la serie sigue indexada por `search_date`**. Fecharla por corte
exige que el worker desplegado calcule `fecha_corte`; hoy solo 15 de 26 capturas se
pueden fechar y las 11 restantes desaparecerían de la página. Un test de supuesto vigila
la cobertura y falla al superar el 80 % — romperse ahí es buena noticia.

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

Corolario del 21-ago-2026: **el nombre no es la identidad entre catálogos
administrativos**. El RUD escribió `SOTARÁ PAISPAMBA` donde DIVIPOLA conserva
`SOTARÁ - PAISPAMBA`; y el RUD/DIVIPOLA ya usan `San Sebastián de Mariquita`
mientras la proyección de población del DANE aún dice `Mariquita`. La primera
diferencia se resuelve con una normalización exclusiva para catálogos que ignora
puntuación —sin tocar `_norm`, porque la puntuación protege topónimos de prensa—;
la segunda, uniendo por el código DIVIPOLA estable (`19760` y `73443`). Solo se
aceptan coincidencias únicas. Los JSON derivados no reciben alias manuales: dos
tests unitarios fijan ambas clases y los guardianes estructurales llaman al mismo
resolvedor que producción.

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

## 2026-08-18 · El manual de estilo es el de EL PAÍS, con excepciones americanas

Contexto: el sitio empieza a generar textos por código (fichas municipales), así
que el estilo deja de ser algo que se cuida a mano página por página y pasa a
replicarse noventa y cinco veces. Hacía falta una referencia externa y comprobable
en lugar del criterio de quien escriba ese día.

Decisión: se adopta el **Libro de estilo de EL PAÍS** (11.ª edición) como
referencia de redacción, gramática, números y siglas, y se crea el agente
`revisor-estilo` que lo aplica citando la norma por su número. El manual **no se
commitea** —es material con derechos—: en el repositorio solo viven las reglas
destiladas, que son normas de uso, no texto ajeno.

Excepciones deliberadas, porque el manual es español de España de 1996 y este
monitor se escribe para Colombia:

1. **«sismo», no «seísmo».** El manual prefiere «seísmo» de forma expresa. Es un
   españolismo: en América se dice «sismo», y es lo que publica el Servicio
   Geológico Colombiano, que es nuestra fuente. Escribir «seísmo» distanciaría el
   texto de las personas de las que trata.
2. **Comillas angulares «».** El manual las prohíbe y exige las inglesas. El sitio
   ya usa angulares en todas partes y son el estándar tipográfico del español: se
   mantienen, y no se reformatea lo existente (el blame también es archivo).
3. **Intensidad en escala de Mercalli modificada (MMI) con decimales**, no MSK 1964
   en números romanos, porque MMI es la que publica el USGS de donde viene el dato.
4. **Léxico institucional colombiano** sin adaptar: alcaldía, gobernación,
   damnificado, corregimiento, vereda, cabecera municipal.

Dos normas del manual se incorporan como obligación y no como recomendación,
porque tocan el rigor y no solo la forma:

- **El condicional del rumor queda prohibido** (12.37): nada de «habrían sido
  registradas» ni «podría estar afectado». Además de galicismo, resta credibilidad
  — y en un monitor cuya única moneda es la trazabilidad, decir quién lo afirma y
  cuándo es siempre posible.
- **Ninguna sigla sin su enunciado completo la primera vez** (9.19). Es la norma que
  el sitio más incumplía: RUD, UNGRD, DIVIPOLA, EDAN, AOI, DYFI y MMI aparecían sin
  desarrollar en páginas que un lector puede abrir directamente desde un buscador.

Reparto de competencias entre agentes: `revisor-estilo` se ocupa de cómo está
escrito; `auditor-editorial` sigue siendo el único que juzga si una cifra puede
publicarse y con qué atribución. Cuando una norma de estilo choque con una regla
del proyecto (R1–R15), manda el proyecto.
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

## 2026-08-19 — UNOSAT entra como fuente, con el paquete (no el producto) como clave

Contexto: el producto 4253 de UNITAR-UNOSAT —la evaluación del epicentro— entró el
18-ago en la cronología institucional que ya ingiere `gdacs.py`, y el monitor lo
publicó en la línea de tiempo sin avisar a nadie: `alerts.py` tenía siete detectores
y ninguno miraba esa cronología. Se descubrió mirando a mano. Además el feed
institucional de GDACS **se saltó el producto 4252**: por esa vía, el monitor nunca
habría sabido de él.

Decisión, en dos piezas separables:

1. **Detector `institucional_nuevo`** en `alerts.py`, nivel alta, comparando la
   cronología archivada de hoy con la última captura anterior. Sin captura previa no
   alerta: en la primera corrida, siete avisos de golpe no informan de nada.
2. **Fuente propia** `ingest/sources/unosat.py` contra `our_products/`, que sí trae
   los cuatro productos del evento. Los shapefiles se leen con un lector propio de
   stdlib (`ingest/shapefile.py`), porque R14 prohíbe dependencias en runtime y el
   formato ESRI es público y estable desde 1998.

La decisión de diseño que importa: **la clave del dato es el sha256 del paquete, no
el id del producto**. Los ZIP de 4251, 4252 y 4253 son byte a byte idénticos —UNOSAT
publica un paquete acumulativo por evento y lo replica en cada carpeta— así que
indexar por producto habría triplicado los 393 edificios a 1.179. Las tres descargas
sí quedan en `sources_log` (esa duplicación es un dato sobre cómo publica la fuente),
pero el cuerpo se archiva una sola vez: `fetch()` no reescribe un snapshot cuyo sha
coincide, así que el `snapshot_name` compartido basta y no hubo que tocar el archivo.

Consecuencia: el monitor tiene por primera vez **dos satélites que pueden discrepar
entre sí**, y una discrepancia inmediata que no es un error de nadie — en el
epicentro, UNOSAT ve un edificio dañado (WorldView-2, 50 cm, «within the cloud-free
areas») donde el RUD registra 626 familias, 19 viviendas destruidas y 170 averiadas (corte del 19-ago). Es la misma
brecha que dejaron las luces nocturnas: sobre el Chocó, el satélite no puede vigilar.

## 2026-08-19 — Un globo del mapa no enseña lo que su fuente no midió

Contexto: los popups se construían concatenando `fmt(valor)`, que devuelve «—» para
null. El resultado era que «Western Colombia» —el área de referencia de Copernicus,
que no trae ninguna cifra— mostraba cuatro renglones de guiones: «Población: —,
Edificios afectados: —, Vías: — km, Interrupciones: —». Un lector razonable entiende
que ahí se midió y salió nada, cuando lo que pasa es que nadie ha mirado.

Decisión: un único constructor de globos, `UI.fichaMapa` (fuente única en `ui.js`,
como `isLiveblog`), que **omite la fila entera cuando el valor está vacío**. El 0 no
es vacío: un cero medido es un dato, y confundirlo con una ausencia es justo el error
que prohíbe la R3. Cada fuente pasa además sus propias etiquetas, en el vocabulario
en que ella publica —UNOSAT gradúa «confianza del análisis» y «validación en campo»,
distinciones que Copernicus no hace— en vez de homogeneizarlas a un genérico que
borraría en qué se diferencian.

Consecuencia: se corrigió de paso una etiqueta que mentía. El globo de municipio
mostraba «fuentes: prensa, rud» bajo el rótulo «Medios»; ni «rud» es un medio ni
aquello eran medios, sino las clases de fuente que documentan el municipio. Ahora
dice «Documentado por: prensa, registro municipal (RUD)».

## 2026-08-19 — UNOSAT cuenta como satélite, pero con etiqueta propia

Contexto: con la fuente ya ingerida quedaban dos decisiones abiertas. La capa de
municipios clasificaba a Anserma, Manizales y Viterbo como si nadie los hubiera
mirado desde fuera, y eso había dejado de ser verdad.

Decisión (JP, 19-ago): **UNOSAT habilita verificación satelital, sin fundirse con
Copernicus.** Estado nuevo `evaluado_unosat` en la cascada de
`ingest/municipios.py`, por debajo de `en_aoi` y por encima de todo lo demás, con
color y explicación propios en `UI.ESTADO_MUNICIPIO`. La razón de no fundirlos:
Copernicus entrega estadísticas revisadas por AOI y UNOSAT entrega puntos
fotointerpretados que la propia ONU marca «aún no validado en campo». Sumarlos en
una cifra única diría que algo está más comprobado de lo que está.

**R1 y R2 no se tocan.** El cruce opera sobre las AOI de Copernicus
(`crosscheck.py`), y los municipios de UNOSAT no son AOI: el corazón del monitor
sigue exigiendo lo mismo para llegar a «coincide».

Decisión gemela: **alta de Viterbo** como municipio del monitor (109 → 110 del
catálogo estático). Entró con `requiere_depto` por dos motivos medidos contra el
corpus, no supuestos: «Viterbo» es una ciudad italiana —la única mención en 6.615
titulares es un artículo en italiano— y casa dentro de «Santa Rosa de Viterbo»,
que es de Boyacá.

Consecuencia: aparece la columna «Edif. UNOSAT (observado)» en la tabla de
municipios, y con ella dos contrastes que antes no se podían leer juntos —Anserma
con 21 edificios de daño observado frente a 3 personas registradas en el RUD, y
Viterbo con 154 evaluados y ninguna fila oficial. Hubo que corregir además dos
textos que la decisión volvía falsos: la frase de cobertura de `municipios.js`
(«al resto no lo ha mirado ningún producto satelital») y el pie del globo de
municipio, que afirmaba «no equivale a daño satelital» también donde ya sí lo hay.

## 2026-08-19 — El corpus de prensa empieza el día del sismo

Contexto: 849 de 6.655 titulares (12,8 %) eran anteriores al 10-ago-2026. Los
849 llegaban por las búsquedas municipales de Google News, que devuelven
histórico; ninguno por GDACS-EMM ni por los feeds del registro comunitario. El
filtro de palabras clave no podía verlos porque hablan de sismos —de otros
sismos—. El caso que lo destapó fue Viterbo (Caldas): entró en la capa el mismo
día porque UNOSAT evaluó allí 154 edificios, y su única noticia atribuida era un
sismo de magnitud 3,1 de junio de 2024.

Se midió antes de tocar nada, reconstruyendo la capa de municipios dos veces:
**cambia la columna «Prensa» en 67 de los 109 municipios que la capa tenía en ese
momento** (Calarcá 30→2, Jamundí 49→4, La Tebaida 40→5, frente a Cali 686→652);
**ocho pasan de «mención en prensa» a «solo RUD»** y ninguno desaparece de la
capa, porque todos tienen registro oficial detrás. Al aplicarlo, ya con UNOSAT
fusionado, la cifra publicada es **68 de 116**: el municipio que faltaba es
Viterbo, que entró con UNOSAT y perdió su único titular, el de 2024. Las dos
mediciones son la misma, sobre una capa que creció entre medias; la que va al
hito público es la segunda. En el cruce por AOI baja `n_prensa` en los siete, pero
**ningún AOI cambia de estado**. En la gráfica de volumen mediático el efecto es
de dos puntos: la serie ya cortaba por su cuenta en 2026-08-08.

Decisión (de JP, sobre tres opciones medidas): **los titulares anteriores al
sismo se excluyen de todo producto público** —páginas, JSON descargables,
conteos y ejemplos—, no solo se marcan. Siguen íntegros en `news_items`, en los
snapshots y en `sources_log`: el principio de archivo se cumple en la capa que
le toca, la de captura, no en la de publicación. Cada corrida deja escrito cuántos
descartó, y no solo en su log: `noticias.json` publica `previas_al_sismo` y
`desde` junto al total, porque los logs de Actions caducan y un filtro que no
dice cuánto tira **desde el propio dato** no es auditable.

Se descartaron: (a) marcar y seguir mostrándolos con etiqueta —el recuento de la
página dejaría de ser «titulares del terremoto» y la marca no impide el
malentendido—; (b) dejar de ingerirlos, única opción que sí rompe el principio de
archivo, porque lo no capturado no se recupera y perderíamos la medida de cuánto
histórico devuelve Google News.

Segunda decisión, del mismo tirón: **una sola frontera**. La serie de volumen
mediático cortaba en 2026-08-08 y el resto del sitio no cortaba, así que el mismo
titular contaba o no según la página. Ahora todo pasa por `FECHA_SISMO`
(`ingest/common.py`) y un test falla si reaparece otra fecha suelta en `ingest/`.

Por qué el corte es **por día** y no por el instante del terremoto (12:34 UTC):
514 de los 849 titulares previos traían la fecha sin hora, porque Google News
normaliza a las 07:00:00 los items que publica sin ella. A nivel de instante no
habría nada que comparar en la mayoría de los casos.

Hallazgo colateral de la medición: el AOI de Istmina publicaba como evidencia de
prensa un titular de agosto de 2024 sobre la muerte de un menor, sin relación con
el sismo. Una cita fechada es una afirmación, no una cifra desviada; desapareció
con el mismo cambio.

## 2026-08-19 — El silencio se publica, en tres niveles

Con el corpus ya limpio de prensa anterior al sismo, el silencio informativo se
puede por fin medir sin confundirlo con titulares de otros sismos: **33 de los
116 municipios vigilados tienen personas registradas en el RUD y cero titulares
atribuidos** —12.129 personas—. Es exactamente la brecha que el monitor existe
para medir, y JP decidió publicarlo como hallazgo.

Decisión sobre CÓMO: la afirmación se publica **en tres niveles**, no como un
número redondo, porque no todos los ceros valen lo mismo. Publicar «33 municipios
sin cobertura» sería justo el tipo de afirmación que este proyecto existe para no
hacer.

1. **Se afirma** el cero de **cinco**: Quinchía, Bagadó, Guática, Mistrató y
   Guacarí (5.297 personas registradas; en Bagadó son el 8,8 % de su población).
   El criterio es **doble** y las dos mitades importan: topónimo sin ambigüedad
   **y** búsqueda propia de prensa. Es decir, el monitor preguntó y no obtuvo
   nada.
2. **No se afirma** el de **28**: su nombre exige que el titular nombre también
   el departamento, así que el cero puede ser del filtro. Y de esos, por **23**
   el monitor **ni siquiera pregunta**.
3. **No tienen cero, tienen ausencia de dato**: los **tres** homónimos de
   departamento (Bolívar, Córdoba y Risaralda, 2.105 personas). Se nombran igual,
   porque son los más invisibles de todos y quedarse fuera del recuento los
   dejaba también fuera del relato.

La regla vive en `site/ui.js::silencioDePrensa`, no en la página, porque es una
afirmación pública y se testea con node como el resto de reglas editoriales que
viven en JavaScript. Devuelve `null` cuando nadie queda mudo: el día que todos
tengan prensa, el banner desaparece en vez de mentir (R11). Y el nivel que afirma
**falla cerrado**: exige `busqueda_propia === true`, no «distinto de false», para
que un campo ausente aguas arriba no ascienda a nadie al nivel que afirma.

Hallazgo de la medición que quedó documentado en `docs/LIMITACIONES.md`: **23 de
los 33 no tienen búsqueda propia de Google News**, porque `municipal_google_news_feeds()`
solo recorre el catálogo curado y no los municipios que entran solos desde el RUD.
Su silencio es, en parte, silencio del monitor. Los cinco del primer nivel sí la
tienen —los cinco—, y entre ellos hay dos situaciones distintas: en Bagadó,
Guática y Mistrató la búsqueda no ha devuelto nunca nada, y en Quinchía y Guacarí
solo devolvió titulares anteriores al sismo, que ya no cuentan.
## 2026-08-19 — Los dumps dejan de volcar el `id` que sqlite reparte

Contexto: `data/dumps/evidence.csv` cambiaba 27 de sus 100 líneas en cada corrida
sin que cambiara un solo dato. La causa no es un error: `crosscheck` borra y
reinserta cada día la evidencia automática de prensa (`match_news_to_aois`), y
sqlite reparte `id` nuevos al reinsertar. Como el dump volcaba esa columna, el
`git diff` diario mostraba movimiento donde no había noticia.

Decisión: `dump_db` no vuelca el alias del rowid (`id INTEGER PRIMARY KEY`).
`rebuild` deja que sqlite lo reparta de nuevo al insertar, en el mismo orden.
Afecta a `evidence` y a `sources_log`; la segunda solo crece por el final, así
que ahí el cambio es una reescritura única sin efecto posterior.

Por qué se puede: ese número no es un dato. Nadie lo referencia —no hay claves
foráneas en el esquema— y no identifica nada que no identifiquen ya las columnas
reales. Lo que sí es dato (qué se pidió, cuándo, con qué sha256) sigue entero.

Compatibilidad: los dumps anteriores se siguen reconstruyendo tal cual, porque
`rebuild` inserta por nombre de columna — un CSV que traiga `id` conserva el
suyo. No hay migración que hacer ni snapshot que tocar.

Se descartó arreglarlo por la causa (que `crosscheck` hiciera UPSERT en vez de
DELETE+INSERT): habría exigido un índice único nuevo sobre `evidence`, la tabla
que sostiene R1, con más riesgo que el que se quería evitar.

Queda anotado lo que NO se hizo: el resultado de cada corrida (`RESULTS` de
`run_daily`) sigue viviendo solo en los logs de GitHub Actions, con 90 días de
retención. Dentro de dos años nadie podrá saber qué fuente falló un día
cualquiera ni por qué falta un snapshot. Se decidió dejarlo así por ahora.
## 2026-08-19 — El medio se lee del archivo, no del enlace ni del titular

Contexto: 3.243 de 6.450 noticias (el 50,3 %) tenían por `url` un enlace de
`news.google.com/rss/articles/CBMi…`, y el campo `medio` no guardaba el medio,
sino el nombre del feed («Google News — Nóvita»). Cualquier recuento de «medios
distintos» contaba feeds: Palmira figuraba con 304 noticias de 7 «medios».

Lo que se comprobó antes de decidir nada:

- **La URL real del artículo no es recuperable de forma limpia.** El base64 del
  segmento `CBMi…` es el formato posterior a 2024: lleva un token opaco
  (`AU_yqL…`), no la URL: de las 2.920 enlazadas así el día del diagnóstico
  (17-ago-2026), ninguna la traía dentro. Seguir la redirección acaba en otra
  URL de `news.google.com`: la resolución final la hace JavaScript en el
  navegador. Cruzar por titular normalizado con las noticias de URL directa
  recuperaba 22 de aquellas 2.920 (el 0,8 %).
- **El nombre del medio sí estaba, y en casa.** Cada `<item>` de los snapshots
  lleva `<source url="https://elpais.com">EL PAÍS</source>`. Cruzando por
  `<link>` se recuperan 3.202 de 3.243 (el 98,7 %) **sin una sola petición de
  red**.

Decisión: `news_items` gana `medio_canonico` y `medio_dominio` por `ALTER TABLE`
(la migración vive en `common.migrar`, idempotente, porque `CREATE TABLE IF NOT
EXISTS` no toca una tabla que ya existe). El campo `medio` se queda **tal cual**:
es lo que se capturó, y renombrar columnas está prohibido sin migrar los dumps.
`url` tampoco se toca — es la petición que consta en `sources_log` (R4).

Se descartó la API interna de Google (`/_/DotsSplashUi/data/batchexecute`): son
3.243 peticiones a un endpoint no documentado que se rompe el día que Google lo
cambie, y dejaría el archivo dependiendo de algo que nadie puede reconstruir.
El archivo propio ya tenía la respuesta.

Consecuencia medible: Palmira pasa de 7 «medios» —que eran feeds— a **30
medios reales**, y el archivo entero suma **926**. La pluralidad se cuenta por
`medio_dominio`, no por el nombre: los nombres llegan con dos convenciones (el
EMM de GDACS aporta slugs en minúscula, `infobae`; el RSS aporta cabeceras,
`Infobae`) y contarlos sin normalizar da 987 con siete duplicados por
mayúsculas. El dominio es clave estable y ningún medio con nombre se quedó sin
él.

Queda además identificable lo que no es cobertura periodística: 164 ítems son de
Volcano Discovery (alertas sísmicas automáticas) y 86 tienen por dominio
`facebook.com`. Etiquetarlos o filtrarlos es decisión editorial pendiente, no
técnica: por ahora se ven, con su nombre.

Un efecto que había que decidir aparte: **`sources_log` deja de registrar solo
peticiones**. R4 la definió como el log de cada petición HTTP, y una
reconstrucción no lo es; pero si no consta, un lector futuro no puede saber si
un medio se capturó el día del `<item>` o se dedujo meses después releyendo el
archivo. Así que la reconstrucción escribe su fila con `http_status`, `sha256`,
`bytes` y `snapshot_path` en NULL —no hubo petición ni cuerpo nuevo— y un
invariante en `tests/test_hipotesis.py` impide que una derivación finja lo
contrario. La nota va por constante (`NOTA_RECONSTRUCCION`), como las sondas,
para que se pueda filtrar sin adivinar la redacción.

Nota para quien lea `evidence` dentro de unos años: las filas de prensa
anteriores a esta fecha están firmadas con el nombre del feed («Google News —
Istmina»); a partir de aquí, con la cabecera. Son dos convenciones de la misma
columna, no dos fuentes distintas.

El sitio etiqueta ese enlace **«vía Google News»**: lleva al agregador, no al
medio, y decirlo es más honesto que dejar que el lector lo descubra al hacer
clic. Cuando no consta la cabecera y el enlace pasa por Google News, no se pone
nada en su lugar — el nombre del feed no es un medio (R3 aplicado al frontend).


## 2026-08-20 — El total satelital de portada suma las dos miradas

La portada anunciaba **622 edificios** y la tarjeta se llamaba «Satélite ·
Copernicus». Desde el 19 de agosto el monitor archivaba además **385 edificios**
clasificados por UNITAR-UNOSAT en Anserma, Manizales y Viterbo. La cifra pública
publicaba menos de lo que el propio archivo tenía: no era una cautela, era una
omisión.

**Se suman. El total pasa a 1.007 edificios con daño clasificado por satélite.**

La condición que lo autoriza no es de método, es de geografía: **ninguna de las
dos miradas entra en el municipio de la otra**. Copernicus cartografía el eje
Cali–Pereira–Chocó; UNOSAT, tres municipios de Caldas donde Copernicus no ha
mirado nada. Sin municipio compartido no hay tejado contado dos veces.

Esa condición no se da por sabida: `ingest/publish.py` la publica en
`monitor.json` como `unosat.municipios_tambien_en_aoi_copernicus`. Hoy la lista
está vacía; el día que deje de estarlo, `site/ui.js` **deja de sumar sola** y la
tarjeta vuelve a nombrar solo a Copernicus. Un test lo comprueba en los dos
sentidos (`tests/test_frontend.py::TestTotalSatelital`).

**Por qué esto no contradice la regla de la celda municipal.** La columna
«Edif. satélite» sigue sin sumar dentro de un municipio, y el test que lo
impide (`test_la_columna_satelital_nombra_su_fuente`) queda intacto. Son dos
operaciones distintas: dentro de un municipio las dos fuentes medirían **los
mismos edificios con métodos distintos** —Copernicus, daño clasificado sobre
estadística revisada por AOI; UNOSAT, fotointerpretación edificio a edificio sin
validar en campo—, y sumarlas sería contar dos veces. Entre municipios disjuntos
se suman **edificios distintos**, y no sumarlos sería esconder daño observado.

**Qué se dice al sumar.** El total no se publica desnudo: la tarjeta lleva el
desglose (622 + 385) y declara que **289 de los 385 de UNOSAT son «daño
posible»**, hipótesis de la fuente. Un total compuesto que no dice de qué se
compone deja de ser rastreable hasta su origen, que es la promesa del proyecto.

**Efecto colateral que había que arreglar en el mismo cambio.** La tabla de
portada «municipios con evidencia sobre el terreno» solo miraba los puntos de
Copernicus: Viterbo y Anserma, evaluados edificio a edificio, **no salían**, y
Manizales salía con un guion en la columna satelital pese a tener 127 edificios
clasificados. La portada iba a anunciar un total que su propia tabla desmentía.
Ahora la evidencia satelital son las dos fuentes, y la columna las nombra.

**Las cifras escritas a mano.** El total de la tarjeta lo calcula el JavaScript
desde los datos, pero la prosa de la portada, el `og:image:alt` y el README las
llevan escritas. En vez de montar una inyección de texto en el build —que
haría cambiar el HTML entero cada día y destruiría el blame—, se añade un
guardián: `tests/test_unit.py::TestCifrasSatelitalesEnLosTextos` compara lo
escrito con `data/public/monitor.json` y falla nombrando el texto que hay que
reescribir. R11 aplicado a la prosa: el supuesto roto avisa.

### De dónde sale cada sumando (comprobado, no heredado)

**385 o 393 (UNOSAT): decisión abierta, redacción cerrada.** La capa publica
**393** puntos; el sitio publica **385**. La diferencia son ocho puntos de
Manizales que traen el código `EQ20260822COL` en lugar de `EQ20260810COL`.

Durante esta sesión se escribió que «son de otro evento». **Es falso, y el
archivo lo desmiente.** Los ocho son idénticos a los otros 127 de Manizales en
todos los demás campos —misma capa, mismo sensor Pleiades NEO, misma fecha de
imagen (11-ago-2026), mismos productos 4251/4252/4253, misma confianza «To Be
Evaluated»—, y el código implica un sismo del **22-ago-2026**: doce días
posterior a la imagen que retrata el daño, y posterior a la publicación del
producto. Ninguna imagen fotografía el daño de un sismo que aún no ha ocurrido.
Lo que consta es un **error de etiquetado en origen**, no un segundo terremoto.
Tampoco hubo reetiquetado: llegaron así en la única captura del paquete
(19-ago-2026), como se ve en `unosat_damage`.

**Lo que se cierra hoy es la redacción, no el conteo.** En ninguna superficie
—ficha, mapa, tabla, README, `llms.txt`, `docs/`— vuelve a decirse «son de otro
terremoto». Se dice lo que consta: *código de evento inconsistente, fechado
después de la imagen que los retrata*. Convertir un fallo de la fuente en un
hecho propio es exactamente lo que este monitor existe para no hacer.

**Lo que queda abierto, para decisión de JP:**

- *Contarlos (393).* Salen de la misma capa, la misma imagen y el mismo producto
  que los 385, y el código que los separa no puede ser cierto. Excluirlos deja
  fuera ocho edificios que UNOSAT sí evaluó por este sismo.
- *No contarlos (385, lo que hay hoy).* La etiqueta es de la fuente y
  sobrescribirla es inventar. Excluir es reversible —si UNOSAT corrige el
  código, los ocho entran solos y el total pasa a 393—; reetiquetar, no.

Se mantiene 385 mientras no se decida, porque es la opción que no escribe nada
que la fuente no diga. El coste está acotado y declarado: ocho edificios de 393,
el 2 %, visibles en la ficha de Manizales y en el globo del mapa.

> **Cerrada el 21-ago-2026** (ver «Zarzal» más abajo): se cuentan. El coste dejó
> de estar acotado el día que UNOSAT publicó un municipio entero con ese código.
> Este bloque se conserva tal cual porque es el estado en que se tomó la
> decisión, no una descripción de cómo funciona hoy el monitor.

**622 (Copernicus).** Sale de las estadísticas por AOI del último snapshot de
productos (2026-08-18), eligiendo por AOI el mayor número de monitoreo y, a
igualdad, la mayor versión: 7 (Cali norte, GRA 00 v2) + 182 (Pereira) + 14
(Cali centro) + 74 (Quibdó) + 10 (Istmina) + 335 (**Buenaventura, GRA 01 v2**)
= 622. Buenaventura es el caso que había que mirar: su primer producto declara
256 edificios y el monitoreo 01 los eleva a 335. El monitor se queda con el
monitoreo, no con el número heredado. El AOI regional «Western Colombia» no
aporta estadística de edificios (`NA` ⇒ NULL, R3), y por eso no suma ni resta.

### Lo que encontró la revisión (y por qué importa más que el cambio)

Sumar la cifra fue lo fácil. Lo que la auditoría destapó es que **el total vivía
en más sitios de los que parecía**, y que las superficies derivadas —las que no
se miran— eran justo las que mentían:

- `llms-full.txt`, el fichero que leen los sistemas de IA, decidía la cobertura
  satelital solo con `en_aoi_copernicus`: escribía «ningún producto satelital ha
  reportado daños» sobre Anserma, Manizales y Viterbo, **los tres municipios que
  aportan los 385**. Es el mismo error que ya se había cerrado en las fichas
  municipales, reabierto en otra salida del mismo dato.
- `llms.txt` seguía anunciando 622 y 393.
- La imagen Open Graph —la superficie más compartida— publicaba el total sin
  decir de qué dos fuentes salía ni cuántos eran hipótesis. Ahora lleva pie.
- El desglose vivía solo en el `title` de la tarjeta: en un teléfono no hay
  hover, así que el «daño posible» era inalcanzable. Pasó a la línea visible.

Lección para la próxima fuente: **una cifra pública no está actualizada hasta que
lo están sus superficies derivadas** (llms.txt, llms-full.txt, OG, metadatos). Y
`tests/test_render_html.py`, que las vigila, solo corría en local: entra en el CI
de PR con este cambio.

**Un guardián cazó un error de esta misma sesión.** Al tocar la nota de portada
se cambió «la comunidad ha documentado 26» por 27, contando municipios que la
tabla excluye (los reportes huérfanos, que no se cuelgan de ningún municipio).
El test nuevo que compara la frase con los datos lo devolvió a 26 antes de
publicarlo. Los satélites sí pasaron de 6 a 9.

### Un código de evento imposible ahora avisa (R11)

El error de etiquetado se descubrió **leyendo la capa a mano**, un día después
de publicarla. Nada en el pipeline lo cantó, y eso es lo que hay que arreglar:
`ingest/alerts.py::codigos_de_evento_imposibles` compara la fecha que va dentro
del código GLIDE (`EQ`+`AAAAMMDD`+`COL`) con la fecha de la imagen y con hoy. Si
el código es posterior a la imagen que retrata el daño, o está fechado en el
futuro, la corrida emite una alerta de nivel medio. Avisa, no rompe (R11): los
puntos se siguen archivando con su literal.

Si el código no sigue el patrón, **no se afirma nada**: un formato desconocido
es ausencia de dato, no un error detectado (R3 aplicado a la alerta).

### Lo que destapó el QA: la pregunta estaba mal formulada

El revisor encontró que `llms-full.txt` seguía negando el satélite en **Yumbo**,
que tiene 3 edificios clasificados por Copernicus con coordenada dentro pero
**ninguna AOI encima**. La ficha del municipio decía 3, la tabla de portada
decía 3, y el fichero que leen los sistemas de IA decía que ninguno.

La causa no era UNOSAT: era **la pregunta**. Ese fichero resolvía la cobertura
con «¿está dentro de una zona que Copernicus delimitó?», y la pregunta correcta
es «¿hay evidencia satelital dentro del municipio?» — que es la que usan las
tablas y las fichas. Ahora usa la misma atribución punto→municipio
(`asigna_a_municipios`) que el resto del sitio, así que hay **una sola forma de
contar el daño de Copernicus** en todas las superficies. El guardián se amplió
en consecuencia: ya no vigila «los municipios de UNOSAT», vigila **cualquier
municipio con evidencia satelital, venga de donde venga**.

Es la misma lección de la sesión, una vuelta más adentro: un cambio de cifra
obliga a revisar no solo dónde se escribe, sino **con qué pregunta se calcula**
en cada sitio.

Pendiente anotado, no resuelto aquí: la tarjeta dice «622 Copernicus» (suma de
`resumen.edificios_afectados` por AOI) mientras la columna de la tabla suma 635
por atribución punto→municipio. Son dos denominadores legítimos y distintos, y
la discrepancia es anterior a este cambio, pero el desglose nuevo la vuelve
confrontable de un vistazo. Merece nota de método o un test que fije la
relación.

Y con el mismo pendiente va la **enumeración**: la portada dice «622 edificios
de Copernicus en Cali, Pereira, Quibdó, Istmina y Buenaventura» —los cinco de
las AOI, coherente con ese denominador— pero el sitio atribuye además 3
edificios de Copernicus a **Yumbo** en tres superficies. Quien abra Yumbo ve un
sexto municipio que la frase no nombra. Ninguna prueba vigila esa lista, a
diferencia del «9 municipios». Cuando se resuelva el denominador, que la
solución cubra las dos cosas: el número y la enumeración.

## 21-ago-2026 · Alta de ICube-SERTIT: los satélites dejan de sumarse

**Decisión**: entra una tercera fuente satelital, ICube-SERTIT, con 512
edificios georreferenciados en cinco municipios; y el recuento del monitor deja
de sumar totales por fuente para **unir puntos**.

**Por qué el cambio de criterio.** Copernicus y UNOSAT se sumaban porque miraban
municipios disjuntos: 622 + 385 = 1.007. SERTIT rompe esa premisa —cartografió
Pereira, Cali y Manizales, ya cubiertos— y sumar habría contado dos veces los
mismos tejados. Se descartó también quedarse con la cifra mayor de cada
municipio: tirar lo que el otro servicio vio en exclusiva es perder dato. Lo que
se hace es unir los puntos (`ingest/satelites.py`): dos puntos de servicios
distintos a menos de 20 m son el mismo edificio; dos del mismo servicio, nunca.
El total pasa a **1.415 edificios únicos**.

**El umbral es nuestro, y por eso se publica.** 20 m sale del experimento del
18-ago (los daños de Copernicus tienen mediana de 25 m al vecino más próximo) y
se valida contra un test de azar en cada corrida: en Pereira empareja el 42,9 %
frente al 1,4 % del azar. La cifra depende del umbral, así que el umbral viaja
dentro de `satelital.json` junto al resultado. Un número que no se puede auditar
es un número inventado con decimales.

**Lo que la unión hace visible**, y no se podía ni preguntar antes: en Cali y
Manizales los servicios cartografiaron zonas distintas de la misma ciudad y no
comparten ni un edificio; en Pereira coinciden en 108 y **discrepan sobre la
gravedad en 49 de ellos**.

**Sobre el canal de entrega.** Los vectores no se descargan: SERTIT los manda
por correo tras un formulario. Se añadió `common.registrar_entrega()` para que
un cuerpo que no llega por HTTP tenga igualmente fila en `sources_log` con su
sha, su ruta y el canal por el que entró. R4 pide constancia de dónde sale cada
cifra, no que todo venga de una petición GET; el dato que no se puede volver a
pedir es el que más necesita constar.

**Sobre el estado nuevo `evaluado_satelite`.** Roldanillo y La Virginia no
podían quedarse como «evaluado por UNOSAT» —UNOSAT no los ha mirado— ni caer a
«mención en prensa» teniendo evaluación satelital. Se añade un estado propio en
el mismo escalón que `evaluado_unosat`. Con dos servicios fuera de Copernicus,
nombrar a cada uno cuesta menos que abstraerlos mal; **el día que entre un
cuarto, hay que unificarlos en un estado genérico** en vez de seguir añadiendo.

**Lo que NO se tocó**: R1 y R2. Una evaluación de SERTIT no habilita «coincide»,
igual que no lo hace una de UNOSAT — el cruce sigue operando sobre las AOI de
Copernicus con estadísticas. Con vectores propios el debate se puede reabrir,
pero no como efecto colateral de un alta de fuente.

**Pendiente que este cambio hereda y no resuelve**: los dos denominadores de
Copernicus (622 declarado por AOI frente a 635 por atribución punto→municipio).
La unión espacial usa los **puntos**, porque unir exige geometría, así que en
Pereira compara 252 de SERTIT con 193 de Copernicus mientras la tarjeta de
portada sigue diciendo 182. Son tres números legítimos y distintos que hoy
conviven declarados; unificarlos es trabajo propio.

### Cerrado de paso: los tres puntos de Yumbo y los dos denominadores

La entrada del 20-ago dejó anotado un pendiente: la portada decía «622 edificios
de Copernicus» (suma de las estadísticas por AOI) mientras la tabla sumaba 635
por atribución punto→municipio, y tres de esos puntos iban a **Yumbo**, un
municipio que Copernicus nunca cartografió.

La causa era que cada superficie adivinaba el municipio de un punto por
**proximidad a la cabecera**, con radio de 25 km: tres edificios del AOI
«Northern Cali» caen más cerca de la cabecera de Yumbo que de la de Cali. La
fuente, sin embargo, sí dice a qué zona pertenece cada edificio.

Se resuelve haciendo que el municipio **viaje en el dato publicado**:
`copernicus_layers` escribe `municipio` en cada punto a partir de la tabla
curada `satelites.AOI_MUNICIPIO`, y las superficies lo leen en vez de
recalcularlo. La proximidad sigue existiendo como respaldo para los puntos que
no declaran AOI. Efectos: Yumbo deja de figurar con daño satelital que nadie vio
allí, la tabla pasa de 635 a 622 —el mismo denominador que la portada— y el
recuento de municipios mirados por satélite baja de 11 a 10, que es lo que
publica `satelital.por_municipio`.

Se descartó importar `satelites.py` desde `deploy/`: habría acoplado la capa de
render a la de ingesta para resolver algo que es un atributo del dato. Un punto
que no sabe de qué municipio es obliga a que cada superficie lo adivine, y tres
superficies adivinando dan tres respuestas.

### Ajuste del mismo día: 1.424 → 1.415

El primer cálculo contaba los 512 puntos de SERTIT como «daño clasificado», y
nueve de ellos —todos en Cali— llegan con `DAMAGE: Not Applicable`: la fuente
los señaló y **no les asignó grado**. Contarlos en un total que se anuncia como
clasificado sería afirmar lo que la fuente no dijo. Se apartan igual que los
ocho puntos de código imposible de UNOSAT: **no se descartan** —el edificio
está marcado y se pinta en el mapa— pero no entran en el recuento, y salen
declarados en `sertit_sin_grado`.

Lo cazó la revisión de archivo, no un test. De ahí sale un test nuevo.

### El código de evento lo decide el producto, no el punto (21-ago-2026)

**Decisión de JP**: un punto de UNOSAT pertenece a este terremoto si el
**producto que lo publica** declara su GLIDE, no si lo declara el campo
`event_code` de la geometría.

Contexto: hasta hoy se excluían del total los puntos cuyo `event_code` no
cuadraba —8 en Manizales, con `EQ20260822COL`, una fecha que ni siquiera había
llegado—. Al reparar los volcados apareció que UNOSAT ha publicado un producto
nuevo, **Zarzal (201 edificios)**, y que sus 201 puntos llevan ese mismo código.
El filtro dejaba fuera un municipio entero que **ningún otro servicio ha
mirado**, y el monitor habría callado el único análisis satelital que existe de
Zarzal.

Lo que inclina la balanza es que los **cinco productos declaran
`EQ20260810COL`** en sus metadatos: la fuente dice, en el sitio donde se dice,
que todo eso es de este terremoto. El campo interno del shapefile la contradice
y está fechado once días después de la imagen que retrata. Entre dos
afirmaciones de la misma fuente, manda la que hace el producto.

Excluir 8 puntos era prudencia; excluir 201 era callar. Los 209 se cuentan y la
inconsistencia se publica al lado, en `unosat_codigo_inconsistente` — que
cambió de nombre porque cambió de significado: ya no es «no suman», es «suman y
su etiqueta no cuadra».

**Total satelital: 1.578 edificios en 11 municipios.**

### UNOSAT reeditó Viterbo a la baja: 154 → 108

En el mismo paquete, la evaluación de Viterbo pasa de 154 edificios a 108. No
es un error del monitor ni una corrección nuestra: **la fuente cambió su propia
cifra**, y el monitor publica la vigente y deja constancia de la anterior. Es
exactamente el tipo de movimiento que este archivo existe para registrar — sin
los snapshots diarios, nadie sabría que Viterbo llegó a tener 154.

### La clave de la fuente no se puede repartir de nuevo

Al volcar `sertit_productos` apareció que `dump_db` omitía la columna
`producto_id`: SQLite trata `INTEGER PRIMARY KEY` como alias de rowid, y el
volcado lo descarta a propósito porque el `id` de `sources_log` no significa
nada. Aquí sí significa: es el número con el que la fuente publica cada informe.
Al reconstruir, sqlite repartía 1..N y **el producto 3244 pasaba a ser el 1**.

El fallo **no lo introdujo este cambio**: `unosat_products.product_id` llevaba
igual desde su alta, y sus cuatro informes se reconstruían como 1, 2, 3 y 4 —
perdiendo el identificador con el que se le puede reclamar un producto a UNOSAT.
Se corrige con `PK_DE_LA_FUENTE` en `ingest/dump_db.py`, una lista explícita de
las claves que son de la fuente y no contadores nuestros.

### Una exención retirada por falsa (21-ago-2026)

Este módulo llegó a archivar solo el catálogo extraído del HTML de SERTIT, en
vez del cuerpo servido, con el argumento de que la página traía un token de
formulario que cambiaba en cada visita y que archivarla serían ~46 MB al año de
ruido. Se creó para eso una constante de exención, `NOTA_VOLATIL`.

**La premisa era falsa y nadie la había comprobado.** Las dieciséis peticiones
registradas ese día devuelven el mismo sha256, y tres comprobaciones seguidas
también. El token no cambia. La exención se retiró entera —constante, función y
excepción en el test— y el HTML se archiva como cualquier otro cuerpo.

Queda escrito porque el error no fue archivar de menos: fue **justificar una
excepción al principio de archivo con una afirmación que no se verificó**. Lo
caza cualquiera que mire el log; no lo cazó nadie hasta la revisión de archivo.

### El canal de entrada no decide el carril del hito (21-ago-2026)

Los vectores de ICube-SERTIT llegaron por correo tras una solicitud manual. La
cronología los pintaba como cambio del monitor porque su feed curado solo
distinguía evento, respuesta local y monitor. Eso mezclaba dos preguntas: quién
actuó y cómo conocimos la actuación.

Se separan los dos hechos. La entrega de SERTIT es una respuesta internacional,
aunque no venga por GDACS ni por el catálogo de Copernicus. La integración de
esa fuente y el cambio del recuento satelital sí son un hito del monitor. El
feed conserva ambos y añade un resumen breve para la portada sin recortar el
texto archivado.

### Un día ausente en una captura acumulativa puede ser cero

ChatMap devuelve todos los reportes de la activación. Las capturas posteriores
al 16 y al 19 de agosto contienen reportes de los días anteriores y posteriores,
pero ninguno de esos dos días. Por tanto son ceros observados, no días sin
captura. La ingesta ahora completa con cero los días cerrados que no aparecen y
mantiene abierto el día de la corrida, que todavía puede recibir reportes.
