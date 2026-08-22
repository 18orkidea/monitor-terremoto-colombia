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

## La serie consolidada de balances no se puede descargar entera

`data/public/alerts.json` publica el consolidado **del último día** —con la fecha, el
medio y el enlace de cada cifra, lo descartado y de qué cuerpo sale—, pero la serie
completa se calcula en el navegador y no existe como fichero. Reconstruir su histórico
exige recorrer el historial de git de `alerts.json` día a día, o volver a ejecutar
`site/ui.js` sobre cada `feeds/balances/*.json`.

Merece un export dedicado (`data/public/balance_serie.json`), como se hizo con `rud.json`
cuando surgió la misma pregunta. Mientras no exista, el dato es reconstruible pero no
está publicado.

## El despliegue del worker no deja rastro en el repositorio

El worker de balances vive en una cuenta ajena y se despliega a mano, así que **el
repositorio no sabe qué versión está viva**. La prueba está en el archivo: el sello
`cifras_desde: "texto_sin_enlaces"` se escribió y documentó en su día y **nunca llegó a
los feeds** —ningún ítem archivado entre el 16 y el 20 de agosto lo trae—, mientras
`atribucion_lugares`, del mismo fichero, sí aparece desde el 18.

Consecuencia para quien lea esto después: un ítem sin `extraccion_version` puede ser
anterior a las reglas nuevas **o** posterior al despliegue pero servido desde la caché
del worker. Al desplegar hay que anotar en `docs/DECISIONES.md` la fecha y hora UTC, que
es la única frontera fiable.

## Las cifras del balance no bajan nunca, y una de ellas debería poder bajar

Desde el 21-ago-2026 el consolidado del balance conserva el **máximo informado** de cada
cifra (R16). Es una decisión editorial, con dos consecuencias que conviene tener a la
vista:

- **Una corrección oficial a la baja queda congelada.** El 17-ago la UNGRD pasó de 294 a
  289 fallecidos; con esta regla, el sitio sigue publicando 294 y el 289 aparece entre las
  cifras descartadas del día, con su medio y su enlace.
- **Los desaparecidos no bajan aquí y sí bajan en la realidad**, cuando aparece gente
  viva. Por eso las tarjetas se rotulan «máximo informado» y no «cifras actuales»: el
  monitor no sabe cuántos siguen desaparecidos hoy, solo cuántos llegó a informar la
  prensa citando a las autoridades.

El motivo de la regla está en `docs/DECISIONES.md` (2026-08-21): sin ella, un medio tardío
citando un corte viejo hundía la serie —el 19-ago se publicaron 11.132 familias afectadas
donde el registro oficial ya llevaba 65.663—.

## La serie de balances está fechada por el día de la búsqueda, no por el del balance

`search_date` es la fecha que se le pidió al buscador, no la fecha del corte del que
habla la noticia. Por eso el mismo artículo de El Tiempo —el balance del 15 de agosto—
figura en el archivo como si fuera el del 12, el 14, el 15 y el 18, con cuatro hashes
distintos. Y por eso el 19 de agosto la serie tiene tres capturas cuyos artículos son
del 10, el 11 y el 14: ese día no llegó ningún balance nuevo.

Desde el 21-ago-2026 el worker calcula `fecha_corte` leyendo lo que el propio texto dice
de sí mismo («balance de este 15 de agosto»), y `UI.fechaCorte` la lee con dos respaldos
—la fecha de la URL y el campo `fecha`—. **La serie todavía NO se indexa por ella**:
sobre el corpus del 20-ago solo 15 de 26 capturas se pueden fechar, y las 11 restantes
desaparecerían de la página. La señal buena llega cuando el worker esté desplegado.

`tests/test_frontend.py::TestSupuestoCoberturaDeFechado` vigila la cobertura y falla
cuando supera el 80 %: ese fallo es el aviso de que ya se puede cambiar el eje y
publicar el retraso de cada medio.

## Los balances archivados antes del 21-ago-2026 traen cifras mutiladas

Hasta esa fecha, las reglas de extracción del worker perdían las víctimas escritas en
femenino («4.548 heridas») y confundían «N personas fallecidas» con personas afectadas:
del boletín de la UNGRD del 18-ago solo salió `personas_afectadas: 304`, que eran los
muertos. Los ítems ya archivados **no se reescriben** —el KV los reutiliza tal cual y el
archivo es inmutable—, así que los feeds de `feeds/balances/` mezclan ambos criterios.
Se distinguen por el sello `extraccion_version: 2` y `cifras_desde:
"texto_sin_enlaces_v2"`; los que no lo llevan son anteriores.

Del mismo periodo viene otra laguna: el `text_excerpt` archivado eran 700 caracteres, y
del boletín de la UNGRD del 18-ago solo quedaron 145, truncados a mitad de frase, porque
además el intento de descargar el post devolvió HTTP 403 (Facebook no permite
archivarlo). A partir del 21-ago se archivan 4.000 caracteres.

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

## La intensidad de la capa de la ausencia la estima un modelo, y nueve municipios no la tienen

Los municipios con registro en el Registro Único de Damnificados (RUD) y sin
evaluación satelital se pintan graduados por la intensidad que el ShakeMap del
Servicio Geológico de Estados Unidos (USGS) **estima** para su cabecera. No es la
intensidad percibida: esa es la del DYFI («Did You Feel It?», el cuestionario del
USGS), la que reporta la gente, y **al 22-ago-2026** solo existe en 23 de los 196
— demasiado poco para un mapa, y por eso se descartó pese a ser el dato preferible.

En esos 23 las dos medidas no se contradicen ni se confirman: el DYFI queda por
encima del modelo en 10 de los 23, la diferencia media es de +0,05 puntos y el
rango va de −1,5 a +1,7. No hay sesgo sistemático, pero la dispersión es real, y
conviene no leer la sacudida estimada como si fuera lo que la gente sintió.

**Al 22-ago-2026**, nueve municipios caen fuera de la cuadrícula que calcula el
ShakeMap: Acandí (Chocó) y ocho de Norte de Santander (Ábrego, Cáchira, El Tarra,
Mutiscua, Ocaña, Pamplonita, Silos y Teorama). Se pintan grises, no con la
intensidad más baja: no saber lo que se sintió no es lo mismo que saber que se
sintió poco. Todas estas cifras cambian con cada corrida —el RUD crece, el DYFI
acumula respuestas y que entre un satélite es buena noticia—, así que van fechadas
y las vigentes se leen en `municipios_mapa.json`, en los campos `total` y
`sin_mmi`.

La rejilla del ShakeMap se revisa durante semanas y la corrida del día puede no
traerla: cuando falta, se usa la del snapshot anterior. De cuál salió cada cifra
se publica en `fuente_mmi_snapshot` (día y sha256), porque un producto fechado hoy
puede llevar intensidades de días atrás.

Y «lo miró Copernicus» significa que la **cabecera** del municipio cae dentro
de una zona analizada, decidido por punto-en-polígono. Es un criterio
conservador —subestima la ausencia— y no distingue las zonas que Copernicus
recortó pero dejó sin analizar (`not_analysed.geojson`).

Además, la intensidad se calcula en la **cabecera municipal**, no en el
territorio: en municipios extensos —Chocó, sobre todo— un solo valor puede
ocultar diferencias grandes dentro del mismo municipio.

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

La capa de UNITAR-UNOSAT trae **548 edificios evaluados** en Anserma, Manizales
y Viterbo (Caldas) y en Zarzal (Valle del Cauca). **El sitio los publica todos**,
y avisa de que **209 de ellos** —8 en Manizales y los 201 de Zarzal— traen el
código de evento `EQ20260822COL` en vez de `EQ20260810COL`.

**Ese código no puede designar otro terremoto, y el monitor no afirma que lo
haga.** Los 8 de Manizales son idénticos a los otros 127 de su capa en todos
los demás campos: misma capa (`PNEO3_STD_20260811_BuildingDamageAsessment_Manizales`),
mismo sensor (Pleiades NEO), misma fecha de imagen (11-ago-2026), mismos
productos (4251, 4252, 4253) y la misma confianza «To Be Evaluated». Y el código
implica un sismo del **22 de agosto de 2026**: *posterior* a las imágenes que
retratan los daños (11 y 13-ago-2026) y posterior a la publicación de los
productos. Una imagen no puede fotografiar el daño de un sismo que aún no ha
ocurrido. Todo apunta a un **error de etiquetado en origen**. No hubo
reetiquetado: llegaron así en la única captura de cada paquete.

**Hasta el 21 de agosto de 2026 esos puntos se excluían del total.** Eran ocho sueltos y
apartarlos era prudencia: la etiqueta es de la fuente y sobrescribirla por
nuestra cuenta sería inventar, el error más grave que este proyecto puede
cometer. Ese día UNOSAT publicó Zarzal entero con el mismo código, y el mismo
filtro pasó de apartar ocho puntos a callar **el único análisis satelital que
existe de ese municipio**. Excluir ocho era prudencia; excluir un municipio
entero era silenciar lo que la fuente sí dijo.

**Cambió el criterio, no el dato**: a qué terremoto pertenece un punto lo decide
el GLIDE que declara el **producto** que lo publica —los cinco productos de
UNOSAT declaran `EQ20260810COL`, este terremoto— y no un campo interno de la
geometría que la propia fuente contradice. Los 209 cuentan, y la inconsistencia
se publica al lado (`unosat_codigo_inconsistente`), en la ficha municipal y en
el globo del mapa, para que quien audite pueda rehacer la cuenta con el criterio
contrario. Lo que no se hará nunca es **reescribir la etiqueta**: contar un dato
y enmendárselo a la fuente son cosas distintas. La decisión, con su porqué, está
en `docs/DECISIONES.md`.

Queda como limitación viva que **la fuente se contradice a sí misma** y que el
monitor ha tenido que elegir cuál de sus dos afirmaciones vale.

Tres huecos conocidos, ninguno subsanable desde este lado:

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
- **Nada de esto está validado en campo.** Los 548 puntos llevan «aún no
  validado en campo», y ninguno alcanza confianza alta: 347 dicen «pendiente de
  evaluar», 180 «incierto» y 21 «media». Son fotointerpretación sobre imagen de
  50 centímetros, no visitas. Y **443 de los 548 —cuatro de cada cinco— son «daño
  posible»**, que es una hipótesis, no un daño contado; solo 105 son daño
  observado. La cifra va siempre acompañada del reparto: un total que esconda
  cuántos son hipótesis no sería rastreable hasta su origen.

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
allí 154 edificios —hoy 108, tras la reedición de la propia fuente—: su única
noticia atribuida era un sismo de magnitud 3,1 de junio de 2024. El topónimo estaba bien; la noticia no era de este desastre.

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


## Lo que ICube-SERTIT publica, y lo que hubo que pedirle

Los cinco mapas de ICube-SERTIT —Pereira, Cali, Manizales, Roldanillo y La
Virginia, dentro de la activación 1048 de la Charter que solicitó la UNGRD— se
publican como PDF y JPG, con los símbolos de daño rasterizados dentro de la
imagen y sin rejilla de coordenadas en los bordes. Comprobado el 20-ago-2026:
del paquete público no se puede extraer un solo punto georreferenciado.

**Los vectores existen, pero no se descargan.** Se pidieron por correo el
20-ago y llegaron el 21: su web los entrega como adjunto tras un formulario con
nombre, correo y aceptación de la política de privacidad. De ahí salen los 512
edificios que hoy publica el monitor. Consecuencias que conviene tener escritas:

- **No hay URL que reclamar.** El cuerpo de cada paquete vive en
  `data/documentos/sertit/` (248 KB en total) con su sha256 en `sources_log`, y
  su fila dice por dónde entró. Es la única fuente del monitor cuyo dato no se
  puede volver a descargar, y por eso es también de la que más se archiva.
- **La cadena depende de una persona.** Si SERTIT deja de responder correos, no
  habrá productos nuevos. Lo ya recibido no se pierde; lo que viene, sí.
- **La licencia es más restrictiva que la del resto del monitor**: permite usar,
  modificar y redistribuir **salvo con fines comerciales**, obliga a citar
  «© ICube-SERTIT 2026» y, si se modifica el producto, a declarar qué se cambió
  sin sugerir que ICube-SERTIT respalda el uso. Su equipo pidió además que
  aparezca su logo. Por eso el `copyright` viaja pegado a cada punto hasta el
  geojson público en lugar de quedarse en un pie de página.

**Sus mapas impresos no cuadran con sus vectores.** El mapa de Cali rotula 86
edificios y el paquete trae 103; el de Pereira rotula 253 y trae 252. El
monitor publica lo que traen los vectores, que es lo auditable punto a punto,
pero la discrepancia queda aquí anotada porque un lector que compare el PDF con
el mapa la encontrará.

**Y sus cifras no son «el daño del municipio».** Cada servicio recortó su propia
ventana: en Pereira, SERTIT analizó 2,78 km² y Copernicus 9,8. Comparar 252 con
193 sin decir eso sería comparar dos preguntas distintas como si fueran la
misma. Por eso la capa municipal publica también el área analizada.

## Los satélites no miran la misma parte de la misma ciudad

Al cruzar los puntos de las tres miradas apareció algo que ninguna cifra
agregada dejaba ver:

- En **Cali**, Copernicus cartografió el centro-norte y SERTIT el sur. **No
  comparten ni un solo edificio**: sus 21 y sus 103 puntos son distintos.
- En **Manizales** pasa lo mismo entre UNOSAT (noreste) y SERTIT (suroeste):
  cero coincidencias.
- Solo en **Pereira** se solapan de verdad: 108 de los 252 puntos de SERTIT
  caen a menos de 20 m de uno de Copernicus. Y **en 49 de esos 108 los dos
  servicios discrepan sobre la gravedad** del mismo edificio.

Por eso el recuento del monitor dejó de sumar totales y pasó a unir puntos (ver
`docs/DECISIONES.md` y `ingest/satelites.py`). Limitación que queda viva: **el
umbral de 20 m es una decisión nuestra**, no de las fuentes. Está calibrado
contra un test de azar que la propia corrida publica —en Pereira empareja el
42,9 % frente al 1,4 % que da el azar—, pero mover ese umbral movería el total.
Quien audite la cifra debe poder mover el umbral y ver qué pasa; por eso se
publica junto al dato.

## La API de cartografía rápida de SERTIT se anunció y luego desapareció

SERTIT documenta —y ESA anunció— una API REST pública, sin clave ni registro, con cuatro
endpoints que devuelven **GeoJSON**: el catálogo de acciones, el detalle de cada una, sus
productos y el detalle de cada producto. Es exactamente lo que un tercero necesita para
reutilizar su trabajo.

A **20-ago-2026 no responde**: `https://sertit.unistra.fr/wp-json/rms/v1/actions` y las seis
variantes probadas devuelven **HTTP 404**, y el espacio de nombres `rms` ya no figura entre
los que publica el propio sitio, mientras la página que la documenta sigue en pie. Se ha
avisado a SERTIT en el mismo mensaje con que se le pidieron los datos.

Queda anotado porque es la clase de fragilidad que este archivo existe para registrar: una
interfaz pública, anunciada por una agencia espacial, que deja de existir sin nota ni aviso.
Quien lea esto dentro de años y encuentre la documentación no debe deducir que la API
funcionaba.

## Zarzal, Viterbo y una etiqueta que la propia fuente desmiente

El 21-ago-2026 UNITAR-UNOSAT publicó una evaluación de **Zarzal (Valle del
Cauca): 201 edificios**, el único análisis satelital que existe de ese
municipio. Sus 201 puntos llegan con el código de evento `EQ20260822COL` —el
mismo que ya llevaban 8 puntos de Manizales—, que implica un sismo del 22 de
agosto de 2026: una fecha **posterior a la imagen que los retrata** (13 de
agosto) y que, cuando esto se escribió, todavía no había llegado.

El monitor los cuenta. El criterio, decidido ese día, es que **a qué terremoto
pertenece un punto lo dice el producto que lo publica**, no un campo interno de
su geometría: los cinco productos de UNOSAT declaran `EQ20260810COL`. Lo que
queda como limitación es que **la fuente se contradice a sí misma** y que el
monitor ha tenido que elegir cuál de sus dos afirmaciones vale. Los 209 puntos
afectados se publican contados y marcados (`unosat_codigo_inconsistente`), para
que quien audite pueda rehacer la cuenta con el criterio contrario.

En el mismo paquete, **UNOSAT reeditó Viterbo a la baja: de 154 edificios a
108**. No es una corrección del monitor: es la fuente cambiando su propia
cifra. Se publica la vigente; la anterior sobrevive en los snapshots diarios y
en los dumps, que es lo único que permite saber que Viterbo llegó a tener 154.

Consecuencia para quien lea una cifra de UNOSAT en este archivo: **puede haber
cambiado después**, y el número que se publicó un día concreto solo se
reconstruye desde `data/snapshots/`.

Esa reedición trajo además **vocabulario nuevo**: hasta el 20-ago la capa solo
declaraba una confianza, «pendiente de evaluar»; desde el 21 aparecen
`Uncertain` (180 puntos) y `Medium` (21). El sitio no sabía traducirlas y las
habría publicado en inglés. No lo cazó ningún test —lo vio una persona leyendo
los datos— y por eso ahora hay uno
(`test_toda_confianza_de_unosat_tiene_traduccion`) que falla en cuanto la
fuente estrena una palabra. Sigue sin haber ni un punto con confianza alta.

## Los identificadores de producto se perdían al reconstruir la base

Hasta el 21-ago-2026, los volcados CSV omitían la columna `product_id` de
`unosat_products` (y habrían omitido `producto_id` de `sertit_productos`):
SQLite trata `INTEGER PRIMARY KEY` como alias de rowid y `dump_db` lo descarta
a propósito, porque el `id` de `sources_log` es un contador sin significado.

Aquí sí lo tenía. En un clon reconstruido desde los dumps, los cuatro informes
de UNOSAT pasaban a ser 1, 2, 3 y 4 en vez de 4250, 4251, 4252 y 4253 — que es
el número con el que se le puede pedir cuentas a la fuente. **Ningún dato
publicado dependía de ese identificador**, así que no hubo cifra afectada, pero
la procedencia sí quedaba rota. Corregido con `PK_DE_LA_FUENTE` en
`ingest/dump_db.py`. Los dumps anteriores al arreglo siguen sin la columna: lo
que se recupera es el presente, no el histórico de los volcados.

## Copernicus publica dos cifras suyas: 622 y 635

El servicio de emergencias de Copernicus declara en el resumen de cada zona un
total de **622 edificios afectados**, y publica **635 puntos** de daño en sus
capas vectoriales. Las dos son de la fuente; el monitor no arbitra entre ellas.

Dónde se usa cada una y por qué:

- El **recuento satelital** (`satelital.json`) usa los **puntos**, porque unir
  las miradas de varios servicios exige geometría: hay que saber si dos
  servicios señalaron el mismo tejado, y eso solo se puede preguntar a un punto.
- La **tabla por municipio** usa también los puntos, ahora atribuidos por el AOI
  que declara cada uno.
- El **resumen por zona** de cada AOI conserva la cifra declarada por
  Copernicus, tal cual la publica.

Los trece de diferencia no se han investigado: pueden ser puntos que su propio
resumen no cuenta, o un desfase entre la estadística y la capa. Lo que no se
hace es elegir una y callar la otra — desde el 21-ago-2026 la portada cita las
dos, porque el lector que sume las tres fuentes tiene que poder llegar al total.
