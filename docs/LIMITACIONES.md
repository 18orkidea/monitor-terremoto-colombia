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
texto**: entran a la capa por el RUD y su columna «Prensa» queda en cero.
Tampoco se les genera búsqueda automática de Google News, porque esa búsqueda
(`"risaralda" "caldas"`) devolvería justo los titulares del departamento y el
feed los atribuiría al municipio saltándose el filtro. La única vía para su
prensa es un feed del registro comunitario, donde una persona declara a qué
municipio pertenece el medio en lugar de deducirlo del titular.

Veinticuatro de los municipios del RUD tienen nombres que son además palabra común
(Toro), lugar extranjero conocido (Versalles, Palestina, Ginebra, Filadelfia),
apellido frecuente (Restrepo, Marulanda) o nombre repetido en dos departamentos
(Riosucio, en Caldas y en Chocó). Para ellos, un titular solo cuenta como
prensa del municipio si menciona también el departamento, y la intensidad DYFI
—que llega sin departamento— no se atribuye cuando el nombre corresponde a más
de un municipio. Consecuencia: se pierde algún titular legítimo que no nombre
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
