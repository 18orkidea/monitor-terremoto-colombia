# Limitaciones conocidas del archivo

Un archivo honesto documenta lo que NO tiene. Esta página enumera las lagunas
conocidas del monitor para que nadie —periodista, investigador, historiador—
tome la ausencia de un dato por la ausencia de un hecho. Complementa la
metodología pública del sitio.

## Los cinco primeros días no existen (10 → 15 de agosto de 2026)

El sismo fue el 10-ago a las 12:30 UTC; la primera petición registrada del
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

Dos municipios se llaman igual que un departamento colombiano: **Risaralda**
(Caldas) y **Córdoba** (Quindío). Ahí el texto libre no puede distinguir
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
snapshot posterior mezcla ambos criterios. Lo que los distingue es el sello
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
