# Limitaciones conocidas del archivo

Un archivo honesto documenta lo que NO tiene. Esta página enumera las lagunas
conocidas del monitor para que nadie —periodista, investigador, historiador—
tome la ausencia de un dato por la ausencia de un hecho. Complementa la
metodología pública del sitio.

## Los cinco primeros días no existen (10 → 15 de agosto de 2026)

El sismo fue el 10-ago a las 12:34 UTC; la primera petición registrada del
monitor es del 15-ago a las 16:21 UTC. De esos cinco días solo existe lo que
las fuentes retuvieran retroactivamente (y el feed EMM de GDACS, que cubría
ese periodo, fue purgado por su emisor el 16-ago — su serie sobrevive
únicamente en nuestros snapshots). No hay snapshots crudos ni sources_log de
la semana del sismo. Por eso el paso diario de Wayback existe: que no vuelva
a pasar.

## Trazabilidad incompleta en los dos primeros días de operación

Hasta el 16-ago, el registro de peticiones (`sources_log`) tenía filas sin
`snapshot_path`: la mayoría, descargas de medios ciudadanos cuyo cuerpo sí se
conservó en `data/media/` pero sin enlazar desde el log; algunas, segundas
corridas del mismo día cuyo cuerpo distinto no se guardaba («el primero del
día ganaba»). Desde el 17-ago ambas cosas están corregidas (snapshots
intradía con sufijo de contenido; medios registrados en el log). Las filas
antiguas no se retocan: el log también es archivo.

## Los vídeos ciudadanos no están en git

580+ MB de vídeo viven en el bucket R2 `monitor-terremoto-media` y en el
disco del mantenedor; en git solo van las fotos, el `sha256` de cada medio y
el manifiesto auditable `data/r2_manifest.json` (objeto + hash + bytes). Si
el bucket desapareciera, los vídeos serían irrecuperables desde el repo — el
manifiesto permitiría al menos saber qué se perdió y verificar cualquier
copia que aparezca.

Por eso, para estos cuerpos, `test_todo_cuerpo_publicado_tiene_snapshot_verificable`
no exige el fichero en disco —en un clon limpio nunca está— sino que **cada
petición A/V del `sources_log` figure en el manifiesto con el mismo sha256**.
Se comprueba siempre, también donde los ficheros sí están: si solo se mirara
cuando faltan, el manifiesto podría desfasarse durante meses en la máquina del
mantenedor y saltar únicamente en CI. Un cuerpo fuera de git y fuera del
manifiesto no es recuperable ni auditable, y el test lo trata como roto.

## El feed de balances depende de un worker en cuenta ajena

El worker de balances (`monitor-terremoto-colombia-oficiales-ai`) corre en la
cuenta Cloudflare `inforesidencias`, no en una cuenta del proyecto, y su
almacenamiento vivo (KV) no está en git. Mitigación: desde el 16-ago cada
corrida diaria guarda el feed completo en `feeds/balances/AAAA-MM-DD.json` —
la serie es reconstruible desde el repo aunque el worker muera. La migración
a una cuenta propia está anotada como deuda en DECISIONES.md.

## Cobertura satelital parcial por diseño

Las zonas mapeadas por Copernicus cubren ~8,7 % de la población expuesta a
MMI≥6. Todo lo que el monitor dice del daño satelital aplica solo a esas
zonas; el resto es población que ningún producto de daño ha mirado de cerca
(extensión documentada en el README: HRSL, Open Buildings, NISAR).

## Los avisos push tienen límites de plataforma

Las notificaciones Web Push funcionan con un clic en Android y escritorio; en
iPhone/iPad, Apple exige instalar el sitio como app (Compartir → «Añadir a
pantalla de inicio», iOS 16.4+) antes de poder activarlas. El plan gratuito de
Cloudflare Workers limita cada disparo a ~40 suscripciones; superarlo requiere
el plan de $5/mes. El canal de Telegram es un tercero: si desapareciera, el
archivo no pierde nada — los avisos son derivados y su fuente (`alerts.json` y
`alerts.rss`) vive en el repo.

## El RUD es un registro progresivo, no un censo

Que un municipio no aparezca en el RUD significa «sin registro aún», no «sin
daño». Las diferencias entre el RUD y los balances citados en medios miden
cuánto falta por registrar formalmente — no errores de nadie.

## El estado «solo registro municipal (RUD)» no tiene verificación independiente

Desde el 17-ago la capa de municipios incluye los 75 municipios del RUD, aunque
72 de ellos no tienen verificación satelital. El motivo no es que Copernicus
haya producido pocas estadísticas, sino que satélite y registro apuntan a
municipios distintos: solo Cali, Quibdó e Istmina están **a la vez** en el RUD
y dentro de una zona con producto de daño. Pereira y Buenaventura tienen
estadísticas satelitales (182 y 335 edificios afectados) pero ningún registro
municipal, y los otros 72 tienen registro sin que nadie los haya mirado desde
el aire. Esa disociación **es** la brecha. En esos municipios la única fuente es lo que las autoridades municipales
cargan al RUD —no los damnificados, que no se autorregistran—: el monitor lo
muestra con el estado explícito «solo registro municipal (RUD)» y nunca lo
promueve a «coincide» (regla R2). El porcentaje de población
registrada como damnificada se calcula sobre proyecciones DANE 2026 — es una
proporción indicativa, no una medición de daño físico.

## Las sondas de contrato quedan logueadas sin cuerpo archivado

`tests/test_supuestos_api.py` consulta cada API externa para comprobar que su
contrato sigue vivo. Esas peticiones se registran en `sources_log` (constaron,
con URL, sha256 y estado) pero no archivan el cuerpo: son diagnóstico del
monitor, no evidencia de ninguna cifra publicada. El test de trazabilidad las
exime mediante la constante `NOTA_SONDA` de `ingest/common.py` —un contrato
explícito, no un prefijo de texto— y un test unitario verifica que ninguna
fuente de ingesta pueda usar esa nota. Consecuencia asumida: si un contrato
externo se rompe, la respuesta que lo evidenció no queda archivada; lo que sí
queda es la fila de log y el test en rojo.

## Topónimos ambiguos: prensa atribuida solo con departamento

Hay municipios que se llaman igual que un departamento colombiano: hoy
**Risaralda** (Caldas), **Córdoba** (Quindío) y **Bolívar** (Valle del Cauca).
La marca es automática —`municipios_dinamicos` la pone sola al detectar el
nombre—, así que la lista puede crecer sin que nadie la cure. Ahí el texto
libre no puede distinguir
municipio de departamento —medido sobre los 5.017 titulares del corpus, todas
las apariciones de «Caldas y Risaralda» hablaban del departamento, y exigir
adyacencia tampoco lo salvaba— así que **no reciben prensa por coincidencia de
texto**: entran a la capa por el RUD y su columna «Prensa» queda vacía («—»),
nunca en cero — que el monitor no pueda atribuir un titular no significa que no
exista, y el JSON publica `null`, no 0.
Tampoco se les genera búsqueda automática de Google News, porque esa búsqueda
(`"risaralda" "caldas"`) devolvería justo los titulares del departamento y el
feed los atribuiría al municipio saltándose el filtro. La única vía para su
prensa sería un feed del registro comunitario, donde una persona declara a qué
municipio pertenece el medio en lugar de deducirlo del titular — vía prevista y
todavía no implementada: hoy `n_noticias` se calcula solo por texto, así que su
celda seguirá vacía aunque alguien añada ese feed.

Veinticuatro de los municipios del RUD tienen nombres que son además palabra común
(Toro), lugar extranjero conocido (Versalles, Palestina, Ginebra, Filadelfia),
apellido frecuente (Restrepo, Marulanda) o nombre repetido en dos departamentos
(Riosucio, en Caldas y en Chocó). Para ellos, un titular solo cuenta como
prensa del municipio si menciona también el departamento, y la intensidad DYFI
—que llega sin departamento— no se atribuye cuando el nombre corresponde a más
de un municipio. Con el DYFI hay una segunda cautela: el USGS etiqueta cada
celda con el topónimo más cercano **del mundo**, así que además del nombre se
exige proximidad (30 km entre el centro de la celda y el municipio). Sin esa
cota, la celda «Balboa» del canal de Panamá se publicaba como intensidad
sentida en Balboa (Risaralda), a 595 km. Consecuencia: se pierde algún titular legítimo que no nombre
el departamento, a cambio de no inflar el conteo con noticias ajenas. Los
municipios curados antes del 17-ago (Armenia, Montenegro, Sevilla, Cartago,
Palmira, Buga) no llevan esta marca todavía: revisarlos exige recontar prensa
ya publicada y se hará como cambio propio.

Efecto lateral visible: la columna «Prensa» de la tabla de municipios cuenta
solo las menciones que pasan este filtro, mientras que la página de titulares
etiqueta además por el municipio que declara cada feed municipal. Un municipio
con topónimo ambiguo puede mostrar «0» en la tabla y tener titulares en
[Titulares](https://brechas.orkidea.eu/site/noticias.html) — son dos preguntas
distintas: «cuántos titulares nombran al municipio con su departamento» y «qué
publicó el feed de ese municipio». El desajuste entre ambos conteos es
preexistente (también en Cali) y no se corrige aquí.

Laguna emparentada, hoy invisible: la página de titulares se etiqueta con
`match_municipios_text`, que recorre solo el catálogo curado, mientras la tabla
de municipios cuenta prensa sobre el catálogo **más** los municipios que entran
solos desde el RUD. El día que uno de esos nuevos tenga titulares, su enlace
«Prensa» llevará a una búsqueda sin resultados — y tampoco tendrá búsqueda
municipal de Google News hasta que se cure a mano. Se arreglará cuando aparezca
el primer caso real.

## Los balances archivados mezclan dos criterios de atribución de lugares

Hasta el 17-ago-2026 el worker de balances atribuía municipios y departamentos
buscando el topónimo por contención, sin límite de palabra: «California» contaba
como Cali, y el nombre de archivo de una imagen (`terremoto-cali.jpg`) bastaba
para atribuir un balance a un municipio que no aparecía en la prosa. Medido sobre
`feeds/balances/2026-08-16.json`, 2 de sus 15 ítems tienen ese defecto.

El worker reusa los ítems ya recolectados tal cual —no los vuelve a analizar—,
así que **esos ítems conservarán su atribución vieja indefinidamente** y cada
snapshot posterior mezcla ambos criterios. Y el reparto puede no ser «unos
pocos»: al desplegar el criterio nuevo (17-ago) el feed tenía 18 ítems, ninguno
con fecha de búsqueda de ese día, porque la prensa ya había dejado de publicar
balances nuevos del sismo. Mientras no entren ítems nuevos, **el feed vivo entero
sigue con la atribución vieja**, y el sello no aparece por ningún lado.

Reanalizar lo archivado no es una salida: en KV solo queda un extracto de 700
caracteres por ítem, no el documento completo, así que reprocesar daría un
resultado *peor* —perdería municipios que sí estaban en la prosa del documento
entero— y habría que volver a descargar fuentes que a estas alturas pueden
devolver 404. Medido sobre el feed vivo aplicando los dos criterios al mismo
extracto: 4 de 18 ítems dejan de atribuir un municipio, y los cuatro por un
enlace (un slug de URL y el nombre de archivo de una imagen), no por prosa. Lo que los distingue es el sello
`atribucion_lugares` que llevan los ítems nuevos: si el campo falta, la
atribución es la anterior. No se reprocesa el histórico: los snapshots son
inmutables (principio de archivo), y reescribirlos para «arreglar» el pasado
sería peor que documentarlo.

Mitigante: el campo `municipios` de cada ítem no se pinta hoy en el sitio —
`site/balances.js` usa las cifras, no la atribución territorial—, así que el
efecto es de archivo, no de portada.

## El snapshot diario de balances no pasa por la cadena trazada

`.github/workflows/daily.yml` archiva `feeds/balances/${HOY}.json` con un `curl`
directo al worker: sin fila en `sources_log`, sin `snapshot_path` y con el
`sha256sum` solo en el log de Actions, que caduca. El feed que sostiene toda la
sucesión del worker depende hoy de una petición no trazada, en contra de R4. Y
una segunda corrida el mismo día lo sobrescribe, en contra de la política de
sufijo intradía que sí aplica a `data/snapshots/`. El snapshot frontera del
17-ago se capturó a mano con `common.fetch` precisamente para no repetirlo, pero
el workflow sigue como estaba.

Tampoco hay forma de saber qué versión del worker produjo un feed archivado: el
deploy es manual, el KV vive fuera de git y el bloque `extraction` no registra
commit ni versión. El sello `atribucion_lugares` cubre solo el criterio de
atribución de lugares, no el resto del código.

## El 17 de agosto de 2026 casi no tiene archivo (HTTP 502 del DANE)

La corrida del 17 (10:30 UTC) ingirió las trece fuentes sin problema salvo el
DANE, que devolvió **HTTP 502**. `run_daily.py` termina con `sys.exit(1)` si
cualquier fuente falla, y eso abortó el job de GitHub Actions **antes del paso
que commitea**: la corrida había funcionado —el RUD subió a 81 municipios y
`publish` generó los artefactos— pero nada de eso se guardó. El runner se
destruye al terminar.

Resultado: del 17 quedan **2 snapshots** en el repo (el catálogo DIVIPOLA y el
feed de balances, ambos capturados a mano ese día), frente a 70 del 16 y 303 del
15. La serie de `rud_daily` se quedó sin el punto de esa corrida.

**Cerrado el 18-ago**: el hueco no llegó a publicarse. Al adoptar el fechado por
día colombiano consolidado, la captura de las 00:02 de Bogotá —que es el cierre
del 17— quedó archivada como día 17, y con datos mejores que los del log: 90
municipios y 36.982 familias, frente a los 81 y 27.181 que la corrida abortada
había visto a media mañana. Lo que sí se perdió para siempre son los snapshots
de las trece fuentes de aquella corrida.

Qué sobrevive y qué no:

- **Sobrevive** el log de la corrida, archivado en
  `data/snapshots/2026-08-17/corrida_fallida_95362286090.log` con su sha256 en
  `sources_log`. De él consta lo que la corrida vio del RUD ese día: 81
  municipios, 27.181 familias, 62.701 personas, 2.130 viviendas destruidas y
  8.507 averiadas.
- **No es recuperable** el desglose municipal de ese día, ni los cuerpos de las
  respuestas. El RUD es acumulativo y solo devuelve su estado actual; la Wayback
  Machine tiene una única captura del endpoint, del 16-ago a las 17:12 UTC, y
  ninguna del 17 (el paso que la solicita corre después del que abortó).
- **No se inventa el punto que falta.** Los totales del log permitirían dibujar
  el 17 en la curva, pero serían una cifra sin cuerpo archivado que la respalde,
  contra el principio de archivo (R4). Un hueco documentado es mejor que un dato
  de segunda mano indistinguible del resto.

Corregido el mismo día (18-ago) en `.github/workflows/daily.yml`: el archivo se
commitea **antes** de cualquier verificación, y la corrida y los tests avisan al
final sin abortar el job. Ver `docs/DECISIONES.md`.

## El RUD mide lo que cada alcaldía carga, no daño verificado

La cifra de familias del RUD cuenta **a quién ha registrado la alcaldía**, no
quién tiene el daño comprobado por un tercero. Registrar a una familia y evaluar
su vivienda son momentos distintos, y en los datos se ve: el campo de familias
avanza antes que el de viviendas.

Consecuencias para leer estas cifras:

- Un municipio con muchas familias y pocas viviendas dañadas casi siempre está a
  mitad de proceso, no ocultando ni inflando nada.
- **Un cero en viviendas destruidas o averiadas puede significar «todavía sin
  evaluar», no «sin daño»**: 21 de los 90 municipios registrados tienen cero
  destruidas, y 6 tienen cero en ambas columnas.
- El avance depende de la capacidad de cada alcaldía: la velocidad del registro
  mide tanto capacidad administrativa como daño.
- El campo `personas` llega incompleto en algunos municipios (a veces una sola
  persona por familia), lo que hace que su porcentaje de población salga
  artificialmente bajo.
- No existe una cifra nacional única con la que comparar: el mismo día, los
  medios que citan fuentes oficiales publican totales que difieren entre sí
  —entre 44.936 y 120.328 familias el 17-ago—, así que la página no elige una:
  remite a la comparativa de fuentes, donde cada cifra lleva su publicador.

## UNOSAT: lo que se archiva y lo que no

La capa de UNITAR-UNOSAT trae 393 edificios evaluados en Anserma, Manizales y
Viterbo. Tres huecos conocidos, ninguno subsanable desde este lado:

- **Del epicentro no hay vectores.** El producto 4253 va de San José del Palmar,
  pero el ZIP que enlaza contiene Caldas: de San José del Palmar no se publica
  ni un punto. El texto del hallazgo sí se conserva —`unosat_products.descripcion`
  guarda el «SUMMARY OF FINDING» completo, y sale en el dump versionado— pero
  **el mapa del informe solo existe dentro del PDF**, que el monitor no archiva
  (1,6 MB de imagen sin geometría). Va al paso de Wayback de la corrida diaria,
  que es una copia en un tercero, no en este repo.
- **El listado no permite mirar hacia atrás.** `our_products/` devuelve una
  ventana fija de 11 productos de todo el mundo, sin paginación ni filtro. El
  monitor no puede descubrir productos anteriores a su primera corrida: los
  cuatro del terremoto entraron porque aún estaban en la ventana el 19-ago-2026.
  Si UNOSAT hubiera publicado once productos de otros eventos antes, se habrían
  perdido sin dejar rastro.
- **Nada de esto está validado en campo.** Los 393 puntos llevan «aún no
  validado en campo», y los 239 que traen el campo de confianza dicen todos
  «pendiente de evaluar» (los 154 de Viterbo no lo traen siquiera): son
  fotointerpretación sobre imagen de 50 cm, no visitas. Y **296 de los 393 —tres
  de cada cuatro— son «daño posible»**, que es una hipótesis, no un daño contado.
  Solo 97 son daño observado.

**Viterbo entró en la capa el 19-ago-2026 y el satélite es su única fuente
sobre este terremoto.** No tiene una sola fila en el RUD. Su único titular
atribuido —«Sismo de magnitud 3.1 tuvo como epicentro a Viterbo (Caldas)», de
La Patria— es de **junio de 2024** y habla de otro sismo: la atribución es
correcta (nombra el municipio y el departamento, como exige `requiere_depto`),
pero la noticia no es de este desastre. Ver más abajo: no es un problema de
Viterbo, es del corpus entero.

El artículo italiano que llama a Viterbo «l'altra Viterbo» **no** se le
atribuye, y está bien: no nombra Caldas, y el topónimo casa además dentro de
«Santa Rosa de Viterbo», que es de Boyacá.

Que su celda del RUD esté vacía **no significa que allí no haya damnificados**:
significa que la alcaldía no ha cargado ninguno. Distinguir esas dos cosas es
justo lo que este monitor existe para hacer.

## El corpus de titulares empieza el día del terremoto

Corregido el 19-ago-2026. Hasta ese día el corpus arrastraba **849 de 6.655
titulares (12,8 %) anteriores al 10-ago-2026**, el día del sismo: 249 de 2026
previos al terremoto, 178 de 2025, 167 de 2024 y 255 anteriores a 2024, hasta un
sismo de 1974. Llegaban
**íntegramente por las búsquedas municipales de Google News**, que devuelven
histórico y pasan el filtro de palabras clave porque hablan de sismos —de otros
sismos—. Ni un solo titular de GDACS-EMM ni de los feeds del registro
comunitario era previo.

Lo destapó Viterbo (Caldas), dado de alta ese mismo día porque UNOSAT evaluó
allí 154 edificios: su única noticia atribuida era un sismo de magnitud 3,1 de
junio de 2024. El topónimo estaba bien; la noticia no era de este desastre.

Desde entonces **ningún producto público cuenta prensa anterior al sismo**
(`FECHA_SISMO`, en `ingest/common.py`). La columna «Prensa» de la capa de
municipios, el `n_prensa` del cruce por AOI, los titulares de ejemplo, la página
de titulares y la serie de volumen mediático usan la misma frontera —antes esa
serie cortaba dos días antes por su cuenta y el resto del sitio no cortaba, así
que el mismo titular contaba o no según la página—. Los titulares previos **no
se han borrado**: siguen en `news_items`, en los snapshots y en `sources_log`.
Lo que se cortó es su entrada a lo publicado, y cada corrida deja escrito
cuántos descartó.

Lo que queda como limitación:

- **El corte es por día, no por instante.** El terremoto fue a las 12:34 UTC del
  10-ago, pero 514 de aquellos 849 titulares traían la fecha sin hora (Google
  News normaliza a las 07:00:00 los items que publica sin ella), así que a nivel
  de instante no habría nada que comparar. Del propio 10-ago se publica todo,
  incluida cualquier noticia de esa mañana ajena al sismo.
- **Un titular sin fecha no se descarta**: no consta que sea anterior, y tirarlo
  convertiría una ausencia de dato en un juicio (R3). Hoy no hay ninguno en el
  corpus, pero la puerta está abierta a propósito.
- **Ocho municipios se quedaron sin ningún titular** —Alcalá, Argelia,
  Candelaria, Ginebra, Guacarí, Obando, Quinchía y Trujillo— y pasaron de
  «mención en prensa» a «solo registro municipal (RUD)». Los ceros no valen
  todos lo mismo: en **Guacarí y Quinchía** el nombre no admite duda y el
  monitor lanza una búsqueda propia, así que ahí el cero es el dato. En los
  otros seis solo se atribuyen titulares que nombren también el departamento, y
  **Argelia y Trujillo** ni siquiera tienen búsqueda propia (ver la sección
  siguiente): su cero es en parte silencio del monitor.

## Los municipios que entran solos por el RUD no tienen búsqueda propia de prensa

`municipal_google_news_feeds()` genera una búsqueda de Google News por cada
municipio del catálogo curado de `ingest/municipios.py`. Los que entran solos
desde el RUD (`municipios_dinamicos`) **no la generan**: su prensa solo puede
llegar si un titular de otro feed los nombra junto a su departamento, porque
nacen con `requiere_depto`.

Medido el 19-ago-2026: de los 33 municipios con damnificados registrados y cero
titulares atribuidos, **23 no tienen búsqueda propia**. Su silencio es, en parte,
silencio del monitor. Por eso el banner de la página de municipios separa tres
niveles y solo afirma el cero de los municipios que cumplen las dos condiciones:
topónimo sin ambigüedad **y** búsqueda propia de prensa.

De los 10 que sí tienen búsqueda propia, **tres no han devuelto ni un titular
desde que la búsqueda existe** —Bagadó (Chocó), Guática y Mistrató (Risaralda)—.
Conviene medir la afirmación: esas búsquedas nacieron el 18-ago-2026 y llevan
cinco peticiones registradas en `sources_log`, no meses. Y desde el 19-ago ese
cero histórico ya **no se puede comprobar desde `noticias.json`**, precisamente
porque este cambio sacó del producto público lo anterior al sismo: consta en la
base local y en los snapshots.

Laguna emparentada, ya descrita más arriba: la tabla de municipios cuenta solo
las menciones que pasan el filtro de topónimo, mientras que la página de
titulares atribuye además por el municipio que declara el feed. Un municipio con
búsqueda propia puede mostrar «0» en la tabla y tener titulares en su página de
prensa (Andalucía y Obando son los casos vivos).
## La URL original de la mitad de los titulares se perdió en el origen

De las noticias que llegan por búsquedas de Google News —cerca de la mitad del
corpus—, el feed no publica el enlace del medio, sino uno propio del agregador
(`news.google.com/rss/articles/CBMi…`). **Ese enlace es lo que se capturó y lo
que se conserva**: el segmento en base64 lleva un token opaco, no la dirección
(comprobado sobre las 2.920 enlazadas así el 17 de agosto de 2026: ninguna
la traía dentro), y la
resolución final la ejecuta JavaScript en el navegador, así que seguir la
redirección tampoco llega al medio. Se descartó la API interna no documentada de
Google, que resolvería el enlace hoy y dejaría de resolverlo el día que Google
la cambie, sin que nadie pudiera reconstruir después lo que devolvió.

Consecuencia para quien lea el archivo dentro de años: en esas piezas se sabe
**qué medio publicó qué titular y cuándo** —eso sí lo declara el RSS y está
archivado—, pero el enlace lleva al agregador. Si el artículo ya no existe, la
combinación medio + titular + fecha es lo que queda para buscarlo.

El nombre de la cabecera se recuperó releyendo los snapshots: 3.202 de 3.243.
Quedan 226 noticias sin cabecera declarada por el propio feed: **41 de Google
News** (su snapshot no llegó a archivarse o el `<item>` no declaraba `<source>`)
y **185 de feeds propios de los medios**, que no emiten esa etiqueta. En esos
casos `medio_canonico` queda en `null`, nunca con el nombre del feed. En los
primeros el sitio no muestra medio alguno; en los segundos el enlace va directo
al medio y basta con el nombre del feed, que ahí sí es una cabecera.

