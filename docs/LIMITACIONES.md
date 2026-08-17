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

## El RUD es un registro progresivo, no un censo

Que un municipio no aparezca en el RUD significa «sin registro aún», no «sin
daño». Las diferencias entre el RUD y los balances citados en medios miden
cuánto falta por registrar formalmente — no errores de nadie.
