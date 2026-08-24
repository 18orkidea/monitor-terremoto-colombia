# Decisiones (ADR ligero)

Historia técnica para el mantenedor: una entrada por decisión, con contexto y
consecuencia. La historia pública del monitor (hitos visibles) vive en
`feeds/hitos_monitor.json` — no duplicar.

Formato: `## AAAA-MM-DD — título` · contexto → decisión → consecuencia.

## 2026-08-24 — Encabezado del prototipo; sin nota autoescrita de los chips

JP lo marcó al comparar ficha y prototipo. Bajo el H1 vuelven la línea del
sismo (`CONTEXTO_SISMO`), el resumen corto de cifras y «Cómo leer esta
ficha». El recuento «Este mapa reúne…» se ve siempre, encima de Situación
y Mapa, sin esperar a que se pida el mapa. La nota «Cada chip retira…»
(y el desajuste de SERTIT) no se genera: JP la retiró.

## 2026-08-24 — El panel desglosa el RUD; en móvil la tabla va antes que el mapa

JP lo pidió sobre la tabla «Qué dice cada fuente»: hacen falta las cuatro
cifras del registro (familias inscritas, personas, viviendas destruidas,
viviendas averiadas), no solo satélites y vecinos. El prototipo ya las
traía; se habían dejado fuera para no duplicar las tarjetas. Con la tabla
primero, esconderlas ahí era esconder el dato oficial detrás del mapa.

Las tarjetas siguen debajo (resumen visual + población DANE). La cifra es
la misma columna: un test se rompe si panel y tarjetas se separan (M2).
Un municipio sin RUD (Palmira) no publica ceros; un cero medido (Pereira,
0 viviendas destruidas) sí.

En móvil el CSS deja de poner el mapa encima: tabla, luego mapa. El
destacado y las tarjetas siguen bajo el lienzo. Los dos párrafos del mapa
siguen encima del lienzo, no debajo de los chips.

## 2026-08-24 — En la ficha, el mapa va primero; el destacado y las tarjetas, debajo

JP lo marcó sobre el móvil frente al prototipo: los dos párrafos del mapa
(«Este mapa reúne…», «Cada chip…») tienen que ir **encima del lienzo**, no
debajo de los chips —en pantalla estrecha la tira envuelve y esos textos
quedaban entre los filtros y el mapa—. El recuadro amarillo (destacado) y
las tarjetas del RUD bajan **debajo del mapa y del panel** «Qué dice cada
fuente». Eso retracta, en la ficha, dejar el lead y las cifras arriba del
lienzo (23-ago / entrada de esta misma fecha sobre el gráfico): el prototipo
ya tenía esa jerarquía; lo que no se porta es duplicar las tarjetas también
en el panel.

## 2026-08-24 — El gráfico del RUD municipal entra junto a la tabla, no en su lugar

La ficha prometía la gráfica «a partir de la 5.ª captura» y no la dibujaba.
El prototipo la midió: forma primero (barras de altas y línea de acumulado),
tabla después (dato citable). Producción añade lo que el prototipo escondía:
el primer día no inventa un alta a cero (R3) y una corrección a la baja se
pinta, no se recorta (R16). El umbral de cinco capturas se mantiene: dos
puntos no son tendencia.

**El destacado largo se queda bajo el H1** (lead periodístico) y las
tarjetas siguen arriba (decisión del 23-ago). El prototipo inventó un
resumen corto para ese hueco porque el splice dejó el destacado en
zona-datos; esa duplicación no se porta. El esquema de títulos de la
ficha es H1 → qué dice cada fuente → cómo avanza el registro → prensa →
qué no sabemos → fuentes, sin saltar niveles.

## 2026-08-24 — La ficha municipal es panel + mapa, no dos pestañas

La fase 5 dejó las 208 fichas a medias: chips y marcado estructurado, pero el
dato en una pestaña y el mapa en otra. El prototipo ya había resuelto lo
contrario —panel de fuentes a un lado, mapa al otro, mapa primero en móvil—
y JP lo rechazó al verlo: «falta la tabla de datos y la organización entre
el mapa y la tabla».

**Se porta el lienzo del prototipo.** Las tarjetas de métricas se conservan
(decisión del 23-ago). El panel no las duplica: empieza en satélites y
vecinos. El recuento satelital es el de la capa que el mapa pinta; si
diverge del de edificios clasificados, la nota de los chips lo explica. Un
servicio que no miró no sale con un cero (R3). El lienzo vive fuera de
`.contenido` porque 760 px no caben panel y mapa lado a lado.

## 2026-08-24 — Un grafo de llamadas para las preguntas de forma, construido al vuelo

**Contexto.** Las fases 4 y 5 gastaron mucho en preguntas que `grep` contesta
mal: «si cambio esto, ¿qué se rompe?», «¿por qué esta función afecta a aquella?»,
«¿este guardián pasa de verdad por donde creo?». Medido sobre este repositorio:
«¿qué depende de `fmt`?» son **~3.800 tokens** de `grep` —154 líneas sueltas, sin
la cadena— frente a **~140** por el grafo, que además dice a cuántos saltos está
cada cosa y qué ficheros toca. La pregunta que costó una revisión entera —si
`TestMarcadoEstructurado` pasaba por el inyector— el grafo la contesta en 0,04 s.

**Decisión.** `tools/grafo_codigo.py`, 60 líneas de `ast` + `re`, **solo
stdlib**. Vive en `tools/` y no en `ingest/`: R14 protege el runtime y esto es
análisis, no producción. **El grafo NO se versiona: se construye al vuelo**,
medio segundo sobre el repo entero. Un índice guardado caduca en silencio, y un
índice caducado que responde con seguridad es la cicatriz M4 —el documento que
contradice al repo— con otro traje.

**Lo que se decide que NO haga, y es la mitad del valor.** No ofrece cobertura
de tests: el build despacha sus generadores por diccionario, así que el grafo
los cree huérfanos —declaraba once funciones sin test cuando, medido
ejecutando, las 95 públicas de `render_html` se ejecutan en la suite—. No indexa
cadenas: para «¿dónde se publica este texto?», `grep`, siempre. Y resuelve las
llamadas por nombre, así que empareja homónimos de ficheros distintos.
**Los tres límites están en el docstring y hay un test que los vigila**, porque
el riesgo de esta herramienta no es equivocarse: es sonar segura.

**Consecuencia, y de dónde sale la lección.** La primera versión afirmó con
total seguridad que el guardián global sí pasaba por el inyector. No modelaba
las clases, así que fusionaba los cuarenta `setUpClass` del fichero de tests en
un solo nodo — **el mismo error que un merge que fusiona clases homónimas**, que
también costó lo suyo esta semana. Corregido el modelo, la respuesta se
invirtió. De ahí el primer test: la clase forma parte de la identidad.

## 2026-08-24 — Un espejo se comprueba ejecutando las dos copias, nunca leyendo una

Cuatro formateadores (`fmt`, `fmt_prosa`, `pct`, `fecha_corta`/`fecha_larga`) se
declaraban «espejo exacto» de su gemela de `site/ui.js` y los vigilaba un
`assertIn` sobre el **texto** del fichero. Un `assertIn` sobre el código fuente
pasa en verde con la condición invertida y no mira si las dos funciones
devuelven lo mismo: es el mismo argumento con el que este sprint se retiraron
otros dos guardianes (M1). Pasan a compararse **llamando a ambas** con el
`ui.js` real.

**El cambio destapó lo que el guardián viejo no podía ver:** `%f` redondea al
par y `Intl` se aleja del cero, así que 0,25 salía «0,2 %» desde el build y
«0,3 %» desde el navegador. **El Cerrito (Valle del Cauca) lo sufría hoy, en
producción**: la misma tasa, dos cifras, según por dónde se mirara el sitio. En
un barrido de 0 a 200 con paso 0,01 habrían divergido 1.000 de 20.001 valores;
sobre el corpus real, uno. **Se adopta el criterio de `Intl` en Python**, porque
es el del locale es-CO y porque `ui.js` es la superficie que el build no puede
tocar. Es corrección de la capa de presentación, no del archivo: lo que dijo la
fuente no cambia.

**Y un escalón más adentro, el mismo error otra vez:** `round()` de Python
también redondea al par, así que el `Dataset` de la ficha de Alcalá publicaba
12,74 donde la tarjeta de al lado imprimía 12,75. Lo cazó el guardián G3 de la
ficha **al fusionarse las dos ramas**, no antes. De ahí `redondea_como_se_lee`:
**redondear y formatear tienen que usar una sola regla, o el sitio publica dos
verdades.**

**Nota de método, ya en `CLAUDE.md`:** la validación por mutación necesita
`PYTHONDONTWRITEBYTECODE=1`. Dos mutaciones del mismo tamaño en el mismo segundo
reutilizan el `.pyc` y dan un verde falso — la comprobación que existe para
descubrir guardianes mudos puede volverse muda ella misma.

## 2026-08-24 — El `Dataset` de `rud.html` publica sus totales, y los fecha con el dato

`rud.html` era la única página grande sin un solo nodo estructurado. Su marcado
sigue el patrón de página-tabla ya fijado en `municipios.html`:
**`variableMeasured` es el diccionario de columnas, nunca un `ItemList`** — 207
filas no disparan ningún resultado enriquecido y serían una segunda copia de la
tabla mantenida aparte (M2).

**Se decide, además, que las columnas que la serie agrega lleven su total
nacional con su fecha**, siguiendo el precedente de `marcado_balances` y no la
letra de la especificación del rediseño, que las dejaba sin valor. El motivo es
que la cifra por la que se cita esta página **es** el total del RUD, y publicarla
en el marcado es lo que hace exigible el resto: `temporalCoverage` cerrado y
`dateModified` en la fecha del dato, no en la de la corrida. Fecharlo con el
build publicaría «100.231 familias a 22 de agosto», que es la confusión que el
sello ya corrige en la prosa de al lado (M7). Las columnas que solo existen
municipio a municipio —la población del DANE y la proporción— se describen **sin
valor**: describir una columna no obliga a inventarle un agregado.

Contra el error editorial grave: **el RUD no es un EDAN**, y que un municipio no
aparezca significa «sin registro aún», no «sin daño». Esa frase viaja en el
`description` del dataset y en el de la variable «Municipios con registro»,
porque **el marcado es lo que se cita sin leer la página**. R9 en dos campos
distintos: `creator`/`publisher` son el monitor, que compila el artefacto; el RUD
es de la UNGRD y va en `citation`, y el DANE entra solo con su columna.

## 2026-08-24 — La ficha: chips que accionan, cifras que se pueden citar

**Chips en vez del control de capas.** El mapa de evidencias repartía sus cinco
fuentes con `L.control.layers`, que por debajo de 560 px se colapsa en un icono:
en el móvil había que **descubrir** que los puntos eran separables. La tira la
escribe el build —rótulo, color y recuento— y `municipio.js` solo la conecta;
construirla en el navegador sería una segunda copia de los recuentos y dejaría
la tira vacía para quien lee el documento sin ejecutarlo. Leaflet queda como
respaldo, no como norma.

**«Los chips cuentan municipios, no puntos» no se aplica aquí, y se dice por
qué.** Ese criterio nació en la tabla de municipios, donde la misma pastilla
podía prometer las dos cosas. En una ficha solo hay un municipio: lo único
contable son los puntos de cada capa. En vez de dejar un número suelto ambiguo,
**el rótulo nombra la unidad** («Copernicus EMS · 193 puntos») y la línea de
debajo lo explica. Ningún chip lleva `title`: la explicación va en prosa, que el
móvil sí enseña y un rastreador sí indexa.

**Y de ahí salió un hallazgo que ya estaba publicado.** En Cali, ICube-SERTIT
dibuja **103 puntos** y la ficha cuenta **94 edificios clasificados**: los nueve
de diferencia son carpas y refugios que la propia fuente deja en «Not
Applicable». Es el único desajuste de las 208. La ficha publica **las dos cifras
con su motivo** en vez de elegir una — enseñar la distancia entre dos números es
el oficio de esta página, y esconderla dentro de una etiqueta de capa era
publicar dos verdades en la misma pantalla.

**El marcado de la ficha pasa de existir a ser citable.** Sus cifras vivían solo
como prosa en español con los miles separados por punto. Ahora cada una es un
par (nombre, valor, unidad) en `variableMeasured`; `citation` dice de quién es
cada una —la tesis del proyecto en formato de máquina—; `dateModified` la fecha
con la fecha del dato; y `measurementTechnique` impide leer «11.826 familias
inscritas» como «verificadas». **R3/M10 con un matiz que importa**: un municipio
sin registro no publica «0 familias» —publicaría que el RUD dice que no hay
damnificados, cuando lo que dice es que aún no ha llegado—, pero **sí sigue
citando a la UNGRD**: consultar una fuente y no encontrarse en ella es un hecho
de esa fuente.

## 2026-08-24 — Dos superficies prometían una protección que el código ya no da

**Contexto.** R5 cambió el 24-ago: el reporte se publica en el punto que
registró la fuente, porque redondear a ~110 m no protegía nada —ChatMap publica
la coordenada exacta en su endpoint abierto— y sí engañaba por partida doble: al
lector, porque una foto de daño a 110 m señala la casa de enfrente; y a quien
reporta, porque se le prometía una protección que la fuente no le estaba dando.
`chatmap.py` dejó de redondear ese mismo día. **Los globos de `site/app.js` y
`site/municipio.js` siguieron diciendo «coordenada redondeada a unos 110
metros».**

**Decisión.** Las dos superficies dicen ahora «en el punto que registró la
fuente», y se mueven **a la vez**, que es la única manera de mover una pareja
M2. Queda pendiente revisar los mismos literales en `verify_citizen.py`,
`publish.py` y `LIMITACIONES.md`, que describen el mecanismo interno y no lo que
se publica.

**Consecuencia.** Es el defecto más grave que ha encontrado el rediseño hasta
ahora, y no lo trajo ningún encargo: apareció al mirar de cerca una superficie
por otro motivo. **Un cambio de regla no está terminado hasta que se persiguen
sus literales publicados** — el contrato lo dice y aquí no se cumplió durante un
día.

**Coda del día siguiente: la décima superficie, y por qué el guardián no la vio.**
Con las nueve superficies ya corregidas y `TestR5NoPrometeLoQueYaNoHace` en
verde, el `README.md` seguía diciendo, **en presente**, «el redondeo es una capa
de prudencia en la presentación, no un secreto» — tres líneas debajo de una
frase que ya explicaba que no se redondea. El bloque se contradecía a sí mismo
en la página que más se lee del proyecto.

El guardián no lo vio por dos motivos, y el segundo es el que enseña: el
`README.md` no estaba en `SUPERFICIES`, **y aunque hubiera estado, el patrón
tampoco habría casado**. Las tres alternativas se escribieron mirando las
redacciones que ya se conocían —«coordenada redondeada», «redondeada a ~110»,
«lat_pub/lon_pub (redondeadas)»— y esta decía lo mismo con otras palabras. Es
**M1 a escala pequeña: un guardián validado contra el bug que ya se tenía
delante mide la memoria de quien lo escribe, no el riesgo.**

**Decisión.** El bloque del `README` se reescribe en pasado y pone delante la
mitad de R5 que de verdad protege —el EXIF no se publica jamás, no sale ningún
dato personal—, que es lo que había que decir con fuerza desde el principio.
El guardián suma `README.md` a `SUPERFICIES` y una cuarta alternativa que
persigue **el verbo en presente** (`el redondeo es|sigue|aporta|protege|añade`),
no la palabra «redondeo», que tiene que poder contarse en pasado en todas
partes. Validado por mutación en dos direcciones: la frase vieja del `README`
hace caer el test por la alternativa nueva, y un «coordenada redondeada» metido
en el mismo fichero lo hace caer por las viejas —lo segundo prueba que el
fichero entró en la lista, y no solo que el patrón creció—. Con
`PYTHONDONTWRITEBYTECODE=1`: sin eso, dos mutaciones seguidas dan un verde falso.

**Lo que queda escrito en el propio test**: un patrón es una red de arrastre, no
una demostración. No cubre una quinta redacción que nadie ha escrito todavía. Si
R5 vuelve a moverse, la lista de superficies se revisa a mano, y el comentario
del guardián dice por qué.

## 2026-08-24 — El guardián global del marcado recorría menos de lo que prometía

`TestMarcadoEstructurado` —los G1/G2/G6 sobre las 213 páginas— copiaba
`site/*.html` y llamaba a `escribir_piezas_compartidas`, **pero nunca pasaba por
`inyectar_prerenderizado`**. Medido: veía **0** nodos `Dataset` en
`municipios.html`, donde hay 1. Es decir, **todo el marcado que ganaron las
fases 4 y 5 nacía fuera del guardián que dice vigilarlo**, y el agujero crecía
solo con cada página que estrenara el suyo.

Es exactamente la forma del bug que motivó esa clase —un guardián que recorre
menos de lo que promete— con otro traje: entonces era un test que miraba el nodo
raíz de un solo documento; ahora, uno que recorre las 213 páginas pero solo en
su versión sin construir. **Lección que se queda: cuando un guardián dice «sobre
todas las páginas», hay que preguntarle sobre qué VERSIÓN de cada página.**
Validado por mutación con las dos ramas de la fase 5 puestas.

## 2026-08-24 — El suelo de prosa se mide con un medidor del repositorio, no con un documento

**Contexto.** El contrato del rediseño era «ninguna baja» de palabras, y el
suelo vivía en un documento de coordinación. Envejeció en una tarde: al cerrar
la fase 4, **ninguna definición razonable reproducía sus cifras** —para
`noticias`, tres formas de contar daban 891, 824 y 680 donde el documento decía
667—. Además los `MINIMOS` absolutos de `seo_check` no vigilaban lo que
importaba: una tabla de 208 filas los cuadruplica ella sola, así que `rud.html`
podía perder su introducción entera con el build en verde.

**Decisión.** `seo_check.prosa_propia()` mide lo que una página aporta
descontando su tabla o lista, la barra y el pie —un colchón idéntico en las 213
páginas que oculta justo la pérdida que el suelo vigila—, y `PROSA_MINIMA`
guarda el suelo por página, fechado, medido sobre `dist/`. Se sube cuando una
fase deja la página mejor; bajarlo exige mano y entrada aquí.

**Dónde muerde, y por qué ahí.** En `pr.yml`, que ahora construye el artefacto:
en un PR se revisa **código**, y una pieza que deja de escribirse es un error
nuestro que tiene que doler. En `pages.yml` sigue con `continue-on-error`
**a propósito** —publicar tarde es peor que publicar con un aviso (R11)—, y esa
política no la cambia este suelo. Antes de esto el guardián no mordía en ningún
camino automático: `dist/` está en `.gitignore`, así que sin construirlo el test
que lo mira se saltaba solo, y un guardián que se salta solo no es un guardián.

**El suelo lleva margen, y el margen es la decisión fina.** Parte de esta prosa
es condicional: existe solo si el dato del día la trae —la disputa entre medios,
lo descartado, el aviso de silencio de prensa—. Un día sin disputa no ha perdido
una palabra escrita, y un día en que la prensa cubre por fin a los municipios
mudos es una **buena** noticia. Sin margen, el guardián se dispararía justo ahí
y la salida cómoda sería bajar el suelo, que es como muere un guardián. Vigila
la regresión de código, no el vaivén del dato.

**Consecuencia.** El contrato deja de ser una promesa entre dos y pasa a ser
verificable por cualquiera. Es **M4** aplicado: una línea base se toma midiendo
en el momento, con un medidor que esté en el repositorio — y el propio medidor
lo demostró al nacer, porque descontaba `<footer>` cuando el pie se emite como
`<div id="site-footer">` y en cambio se comía el `<header>`, que aquí no es
cromo sino el encabezado propio de la página. **El cromo se descuenta por su
marca, no por su etiqueta.** Con guardián del guardián:
`test_el_suelo_de_prosa_caza_la_perdida_y_no_se_queja_de_lo_sano`.

## 2026-08-24 — Un contenedor a la espera de su relleno no puede ser un formato que haya que parsear

**Contexto.** Dos páginas distintas de la fase 4 se averiaron el mismo día por
la misma causa, descubierta por dos vías independientes. Un
`<script type="application/ld+json">` vacío —el contenedor natural para un
bloque que rellena el build— **es JSON inválido** para todo el que lea el
documento antes de la inyección: el `site/` de desarrollo, y los guardianes
G2/G6, que construyen las 213 páginas sin pasar por el inyector. El caso de
`municipios` era su `Dataset` nuevo; el otro era `#site-identity`, vacío en las
**cinco** páginas desde antes del sprint.

**Decisión.** El marcador del nodo de identidad es un **comentario HTML**
(`<!--site-identity-->`) y el `<script>` entero viaja dentro de la pieza
generada; el `Dataset` de una página lo lleva una `<section hidden>` en el
`<body>`. La regla, general: **un contenedor a la espera de su relleno es prosa,
marcado o comentario, nunca un formato que alguien tenga que parsear.** Se
aplica también al defecto preexistente, no solo al caso que lo destapó.
Corolario para `variableMeasured` de las páginas-tabla: es el **diccionario de
columnas**, no un `ItemList` con las 208 filas, que sería una segunda copia de
la tabla (M2) — el índice para sistemas de IA ya lo hace `llms-full.txt`.

**Un `<div>` no servía, y el porqué merece quedarse escrito**: dentro de
`<head>`, un `<div>` lo cierra implícitamente por el algoritmo de construcción
del árbol, y el `manifest`, los iconos y **`styles.css`** —que iban detrás—
pasan a `<body>`. `dist/` no llegó a verse afectado porque allí el marcador ya
está sustituido, pero `site/*.html` sí, y es la cicatriz **M6** rondando otra
vez («los prototipos daban un paso atrás» era que no cargaban `styles.css`). Un
comentario es válido en `<head>` y no toca el árbol: permutar una invalidez por
otra no es arreglar.

**Consecuencia.** El bloque publicado no cambia un byte (verificado por sha256
del contenido de identidad en `dist/` antes y después). El guardián se
generaliza a las cinco páginas. `_CONTENEDOR_LD` acepta las dos formas —marcador
y bloque escrito— porque aquí la pieza cambia de etiqueta: sin eso, repetir el
paso sobre un `dist/` ya construido volvería a acusar a `site/*.html` de haber
perdido el marcador.

## 2026-08-24 — Balances: el marcado estructurado también caduca con la corrida

La página de balances servía 2.202 palabras y ninguna era una cifra del balance.
Se prerenderiza igual que el RUD, con dos decisiones propias.

**El consolidado se pide, no se replica.** La regla de R16 vive solo en
`site/ui.js`. `render_html.py` la ejecuta con node —patrón de
`alerts.py::_consolidado_de_la_serie`— y escribe lo que devuelve. Si node falta,
cada pieza publica su aviso; lo que sí se publica sin él es el recuento de
archivo, que no depende de la regla. Reimplementarla en Python habría sido la
tercera copia de la única regla que decide qué cifra ve el público.

**El `Dataset` baja del `<head>` al `<body>` y lo escribe el build.** Sus dos
campos más útiles —`variableMeasured` y `dateModified`— son datos del día, y a
mano envejecen igual que una cifra a mano: el bloque estático fechaba la
cobertura con «..» y no publicaba ni una cifra. **R9 en el marcado**:
`creator`/`publisher` son el monitor, que compiló el artefacto; la UNGRD va en
`citation`. Decir que la UNGRD publica esta página, o que el monitor produjo la
cifra oficial, son las dos mentiras simétricas.

**Un rótulo que se cae cuando falta un dato ajeno a él no es un rótulo.** El
«máximo informado» de R16 viajaba dentro del párrafo de la captura elegida. Un
día en que el consolidado arrastra el máximo sin captura nueva —justo cuando más
falta hace la advertencia— la página habría publicado las cifras sin ella. Va
siempre y en su propio párrafo.

**Una captura son su día Y su URL.** El mismo artículo es la captura elegida de
varios días. El índice por URL colapsaba doce elegidas en siete filas: seis se
quedaban sin la marca «✓ usada en la serie» y la fila desplazada dejaba de
atender a los filtros. Lo destapó el pie servido, que dice cuántas alimentan la
serie y contradecía a la tabla — **un dato servido audita al navegador, no solo
al rastreador**.

## 2026-08-24 — El corpus de titulares se declara ajeno: `Dataset` con dos niveles de atribución

La página de titulares publica su corpus como `Dataset` en JSON-LD, y R9 decide
cómo se firma. `creator` y `publisher` son el monitor **porque el monitor
compiló este corpus** —el emparejado por topónimo, con su
`measurementTechnique`—, nunca porque haya escrito un titular. Quién produjo la
prensa va en `citation`, por canal: GDACS-EMM, el registro abierto de feeds y
Google News. Ningún nodo se declara `author` de nada y ningún titular se marca
como `NewsArticle`: sería apropiarse de obra ajena, y es lo que vigila
`TestMarcadoDeNoticias`.

**Sin `license`**, a diferencia de los datasets municipales: el monitor no puede
licenciar titulares de terceros. Cambiarlo exige tocar el HTML y el guardián a
la vez, y volver aquí.

`dateModified` viaja como marcador `{{noticias_corte}}` y lo escribe el build:
un `<span data-gen>` no cabe dentro de un bloque JSON-LD. Si la corrida falta o
no es una fecha, la clave no se emite y el build revienta con «marcador sin
valor» — publicar `"None"` fecharía el corpus en la nada (M10).

**El paginador no se prerenderiza.** `noticias.html?p=2` no existe como URL: sus
botones son estado del navegador, y servirlos publicaría enlaces muertos. Lo que
un lector sin JavaScript necesita saber de la lista —que es un recorte, de
cuánto y por dónde sigue— vive en un pie servido, `nota_noticias()`, y **solo
ahí**: si el literal siguiera además en `noticias.js`, el día que uno cambiara
la página diría dos cosas (M2).

## 2026-08-24 — Un guardián que se muda de superficie se repunta o se retira, nunca se relaja

**Contexto.** La regla de «mirado por satélite» de la tabla de municipios pasó
del navegador al build en la fase 4, y tres guardianes seguían apuntando a
`site/municipios.js`.

**Decisión.** Dos de ellos comparaban los **nombres** de los campos en el texto
de los ficheros: repuntarlos a `render_html.py` los habría dejado igual de
mudos, porque un `assertIn` sobre el código fuente pasa en verde con la
condición invertida. **Se retiran**, y lo que querían decir lo dice ahora
`TestLaMiradaSatelitalEnLasDosSuperficies` **llamando a las dos funciones** sobre
54 combinaciones y afirmando que la única diferencia entre ellas es la condición
del RUD. El tercero pierde la entrada de `municipios.js` del diccionario `TIRAS`,
con su cobertura real anotada: la vigilan los tests por ejecución.

**Consecuencia.** Es **M1** como criterio de mantenimiento, no solo de escritura:
cuando un guardián deja de alcanzar lo que vigilaba, la pregunta no es «¿a dónde
lo repunto?» sino «¿esto guardaba algo?». Se corrigen de paso los dos punteros
que mandaban a leer una función que ya no existe.

## 2026-08-24 — La revisión se cobra por sprint; el trabajo se paraleliza por superficies disjuntas

**Contexto.** Hasta hoy cada cambio pagaba su Definition of Done completa al
momento: mutaciones M1, tres revisores y navegador por encargo. Con el
andamiaje del rediseño puesto (sistema CSS, prerenderizado probado en
`rud.html` y las 208 fichas), las fases 4–6 son aplicar un patrón conocido a
varias páginas independientes, y la puerta por-cambio consumía más trabajo que
el cambio mismo.

**Decisión (JP).** El test se sigue escribiendo junto al código y la suite
rápida se pasa a menudo (20 s: es gratis). La validación por mutación, la
verificación en navegador y los tres revisores pasan a cobrarse **por lote al
cierre de página o sprint**, con los hallazgos aplicados en una sola pasada. El
trabajo se paraleliza con agentes **solo sobre superficies disjuntas**; lo
compartido lo integra la coordinación. Riesgo aceptado: rehacer en lote lo que
una revisión tardía destape — aceptable porque nada se publica sin la revisión
de sprint, que sigue siendo bloqueante antes del PR.

**Consecuencia.** La sección «Cadencia por sprint» entra en el Definition of
Done de `CLAUDE.md`. Primer sprint bajo el esquema: la fase 4 del rediseño
(`municipios.html`, `balances.html`, `noticias.html`), tres agentes en
paralelo, uno por página.

## 2026-08-24 — El nombre a secas de los homónimos se congela: una URL publicada no se subasta

**Contexto.** `municipios_dinamicos()` repartía el nombre a secas al **primero**
de dos municipios homónimos, y `publish.py` le pasa las filas del RUD ordenadas
por familias **descendente**: «Argelia» era la del Valle del Cauca porque tenía
más damnificados. De la clave cuelgan la URL de la ficha (`/municipio/argelia/`)
y el identificador del feed de prensa, así que **bastaba con que entrara un
homónimo nuevo con más familias para que una URL publicada pasara a ser otro
municipio** sin que nadie lo decidiera. Doce URLs estaban expuestas así — y el
último día entraron 49 municipios de golpe. Los criterios «neutros» no
salvaban: DIVIPOLA ascendente, departamento A–Z y población descendente
intercambian HOY los casos publicados (el prefijo 19 del Cauca gana siempre por
código bajo, y el Cauca es el que hoy pierde siempre).

**Decisión.** `ingest/municipios.py::NOMBRE_A_SECAS_CONGELADO`: una tabla
versionada que fija **qué código DIVIPOLA se queda con cada nombre a secas**,
congelada sobre lo publicado el 18-ago-2026. La tabla **no decide quién entra:
solo quién se queda el nombre corto** — el municipio nuevo entra igual, con su
ficha y su búsqueda, pero nace desambiguado («X (Departamento)») en vez de robar
un nombre. Sin entrada en la tabla se cae al reparto de siempre y el test de
supuesto (`TestSupuestoNombreASecas`) avisa de que nació un homónimo que hay que
anotar — mismo patrón que `SIN_BUSQUEDA_ESPERADOS`: fallar es la señal de que
hay trabajo. El guardián vigila bajas **y altas**, como el inventario del pie.
La identidad es el DIVIPOLA; sin código resuelto desempata el departamento; la
degradación segura es «paréntesis», nunca «desaparece».

**Lo que la decisión NO hace, a propósito:** no corrige la asignación
discutible. «Argelia» es hoy el pueblo de 5.538 habitantes y «Argelia (Cauca)»
el de 27.853; es feo, **pero es lo publicado**. Corregirlo es una decisión
editorial distinta que exige su propia entrada, migración y redirecciones — no
viene de contrabando dentro de un arreglo de estabilidad.

**Consecuencia.** Ninguna URL de `dist/municipio/` cambió (208 idénticas,
verificado antes/después del build). Los guardianes se validaron por mutación
(M1): entrada que falta, entrada que sobra y reparto que ignora la tabla — los
tres caen. Se corrigieron además dos docstrings que afirmaban lo contrario de lo
publicado («Argelia» del Cauca), justo donde alguien iría a leer la regla.

## 2026-08-24 — `toponimo` llega a `ui.js`: la clave desambigua, el texto no la repite

**Contexto.** `municipios.html` publicaba «…salvo Bolívar (Valle del Cauca) y
**Bolívar (Cauca) (Cauca)** y Córdoba (Quindío)…». Dos defectos en la misma
frase: el departamento duplicado —el mismo bug que `179edef` arregló en las 208
fichas con `toponimo()` en Python, y del que `ui.js` **nunca se enteró** (M2)— y
la enumeración «A y B y C», que no es español, cuando diez líneas más abajo el
mismo fichero ya tenía `enumeraEs` bien hecha.

**Decisión.** `toponimo(clave, depto)` se escribe en `site/ui.js` como **espejo
exacto** de `deploy/render_html.py::toponimo`, con test de espejo
(`test_el_toponimo_de_ui_js_es_espejo_del_de_python`) que cae si divergen — la
lección de M2 completa: al fundir, un test que se rompa si vuelven a separarse.
Las enumeraciones sueltas (`fraseHomonimos`, lista de UNOSAT en
`comparativaFuentes`) pasan por `enumeraEs`, que queda como la única de la casa.
Los dos globos del mapa que titulan con la clave del catálogo (`app.js`: la capa
de municipios con señal y la capa de la ausencia, esta última cazada por el
auditor editorial) dejan de escribir «Riosucio (Caldas) (Caldas)».

**Consecuencia.** Guardianes nuevos en `test_frontend` y `test_render_html`,
validados por mutación: reintroducir el departamento duplicado, el «a y b y c» y
la divergencia del espejo tumba los tests. `seo_check.DEPTO_DUPLICADO` no veía
esta frase porque solo recorre las fichas y esta la escribía el navegador: otro
motivo para el prerenderizado de la fase 4.

## 2026-08-24 — Un activo se archiva una vez: el guardián pregunta al archivo, no al disco

**Contexto (medido sobre `sources_log`, 15 a 22-ago-2026).** De los **3.931 MB**
que el monitor ha descargado en su vida, **2.648 son 77 vídeos ciudadanos
bajados una media de 4,8 veces cada uno** — dos tercios de todo el tráfico del
proyecto para reescribir bytes que ya estaban archivados y verificados. Uno de
59,6 MB se descargó seis veces. Las 372 descargas de esos 77 objetos devolvieron
**siempre el mismo sha256: cero excepciones**. Las 434 descargas de fotos, en
cambio, fueron 434 fotos distintas: ni una repetida.

La causa no estaba en la red. Los `.mp4` y demás audiovisuales están en
`.gitignore` —630 MB no caben en el repo—, así que **la máquina que corre el
proceso diario arranca con `data/media/` sin un solo vídeo**, mientras que las
459 fotos sí llegan en el clon. Y el guardián que decidía si había que descargar
miraba el sistema de ficheros (`chatmap.py`, `if dest.exists()`). En el runner
nunca existía. Por eso el desperdicio caía entero del lado de los vídeos: el
mismo código acertaba con las fotos, porque de las fotos sí hay copia en git.

Las peticiones condicionales que se estrenaron el mismo día **no lo arreglaban**:
`copia_vigente()` solo pregunta con validadores por un cuerpo que se pueda servir
del archivo local, y estos no están ahí. Es su invariante, y es correcto.

**Y no era un problema de almacenamiento.** El bucket guarda cada vídeo una vez
y va por 630 MB de 10 GB; el `aws s3 sync --size-only` ya se saltaba lo que
estaba subido. La fuga era de una sola dirección: tráfico y tiempo de bajada.

**La distinción que faltaba: dato frente a activo.** Un cuerpo que puede cambiar
es un **dato**: preguntar cada día es la única forma de saberlo, y eso lo
resuelven las condicionales. Un vídeo ciudadano no: nace con una dirección
propia —un UUID que ChatMap acuña al subirlo— y su contenido es el que es. Es un
**activo**, y un activo se archiva una vez. En palabras de JP: «nada que sea
contenido que no cambia se archiva más de una vez: es un activo, no un dato
archivable».

**Decisión.**

1. **El guardián pregunta al archivo.** `common.activo_archivado(url)` responde
   por tres vías, de más a menos fuerte: **el cuerpo en disco** (es la prueba,
   no un registro de la prueba), **`citizen_reports.media_sha256`** —la base
   viva, que `run_daily` reconstruye entera desde `data/dumps/` antes de
   empezar— y **`data/r2_manifest.json`**, el manifiesto versionado que viaja
   en el clon aunque la base se pierda.
2. **Si la base y el manifiesto se contradicen, no vale ninguna de las dos.**
   Devuelve `None`, el cuerpo se vuelve a descargar —que es lo que restablece la
   verdad— y la contradicción sale en las alertas
   (`alerts.divergencias_del_archivo_de_activos`, R11). Medido hoy: **0 casos**
   sobre 77 objetos; las dos vías coinciden objeto a objeto y sha a sha.
3. **Lo que NO se avisa, a propósito**: que la base conozca un vídeo que el
   manifiesto todavía no tiene. `publish` escribe el manifiesto DESPUÉS de
   `alerts`, así que el día que llega un vídeo nuevo esa diferencia es lo
   normal, y avisar de lo normal es la forma más rápida de que dejen de leerse
   las alertas.
4. **El reverso, que es donde esto falla en silencio.** Si llega un cuerpo
   distinto bajo un nombre ya archivado, `fetch(save_to=…)` lo guarda **al
   lado**, con la firma de su contenido (`_sha8`), y no toca el viejo — la misma
   política que los snapshots intradía, ahora con una sola implementación
   (`_nombre_con_contenido`, M2). Antes no escribía nada y la fila del log
   declaraba el sha256 del cuerpo nuevo apuntando a un fichero con el viejo
   dentro: **la única forma de que este archivo mienta sin que nadie lo note**.
   El camino era inalcanzable desde ChatMap por el propio `dest.exists()`; al
   quitarlo dejaba de serlo.
5. **El manifiesto no puede perder lo que ya sabía.** Los bytes de un activo
   salen del cuerpo si está, del registro de su descarga en `sources_log` si no,
   y de lo que ya declaraba el manifiesto anterior en último término (M10: si
   nadie lo sabe, se omite el campo; jamás un 0). Sin esto, la primera corrida
   con el guardián nuevo habría escrito `bytes: null` en los 77 objetos —
   comprobado sobre un clon limpio— y el commit automático se habría llevado por
   delante la columna que hace auditable el bucket.
6. **La red de seguridad que desaparecía, repuesta — y no con un aviso.**
   Mientras el runner se bajaba los vídeos cada día, el `sync` los volvía a
   ofrecer y cualquier objeto que faltara en R2 se curaba solo al día siguiente.
   Ya no, y eso abría el camino por el que **un cuerpo se pierde para siempre
   con la corrida en verde**: el `sync` se salta entero si falta el secreto
   —token rotado, un fork—, y ese día un vídeo nuevo existe solo en el
   workspace del runner, que git ignora y que se destruye al acabar, mientras
   `publish` ya escribió su sha256 en el manifiesto y en la base. Desde el día
   siguiente el guardián lo da por archivado y no vuelve a pedirlo jamás.
   `ingest/auditar_r2.py` lista el bucket y **sale 1** —no avisa: falla— cuando
   el manifiesto declara un cuerpo que R2 no tiene, o cuando hay un A/V que solo
   existe en el workspace. El workflow mira su `outcome` en el paso que pone la
   corrida en rojo, y como la auditoría corre antes del commit, el archivo del
   día se guarda igual. La auditoría compara presencia y tamaño, no sha256: R2
   no publica el hash de sus objetos y el `ETag` de una subida multiparte no es
   un md5 del cuerpo. Es lo que se puede comprobar desde fuera, y se dice.
7. **Y el resultado de la auditoría se archiva.** Los `::error::` de Actions
   viven fuera del repositorio y caducan a los 90 días: **un aviso que no se
   archiva no cumple el principio de archivo**. Cada corrida deja
   `data/auditoria_r2.json` —fecha, objetos en bucket y en manifiesto, y las
   listas de lo que falta, lo que difiere y lo que sobra—, que el commit del bot
   versiona. También los días en que no se pudo auditar: «ese día no pudimos
   mirar» es información, igual que un 304.
8. **Cada línea del manifiesto se defiende sola.** Las tres vías del tamaño van
   atadas al sha256 que se está escribiendo —el fichero se verifica antes de
   medirlo, el `SELECT` lleva `AND sha256=?`, y el manifiesto anterior solo vale
   si declaraba ESE contenido—. `bytes` es el único campo que la auditoría puede
   contrastar contra R2: una cifra desalineada o suena en falso todos los días
   —y un aviso falso mata la lectura de las alertas— o enmascara una sustitución
   real. Si ninguna vía sabe el tamaño de ese cuerpo, se omite (M10).
9. **El manifiesto no encoge.** `rebuild_db` y `chatmap` son `step()`: R13 los
   deja fallar. Con la base vacía, el manifiesto se habría regenerado como
   `objetos: []` y el bot lo habría commiteado — los cuerpos seguirían en R2
   pero **dejarían de estar declarados**, que es exactamente lo que hace
   auditable el bucket. Lo ya declarado se arrastra, y que la base no lo
   reconozca se canta como el huérfano que es.
10. **Y las alertas no acusan al bucket de un fallo de la base.** El espejo del
    mismo problema: con `citizen_reports` vacía, los 77 objetos del manifiesto
    salían como huérfanos. Ahora eso es un aviso distinto —«falta la base»— y no
    77 dedos apuntando a R2.

**El barrido, porque el patrón importa más que el caso.** Se revisaron las **72
apariciones** de `.exists()`, `glob`, `iterdir` e `isfile` de `ingest/` —50 son
`.exists()`, repartidas sobre todo por `publish.py` (23) y `common.py` (10)—,
cruzadas con `.gitignore`. Bajo `data/`, git ignora exactamente dos cosas: los
audiovisuales de `data/media/` —que van a R2— y `data/monitor.sqlite`, que no se
descarga de ninguna parte: se reconstruye de `data/dumps/*.csv`. Ningún otro
guardián decide una descarga mirando el disco: los demás `.exists()` leen el
propio archivo (snapshots, dumps, `data/public/`, los ZIP de SERTIT) o `dist/`,
que se construye. **El patrón no se repite en ningún otro sitio.** Queda un test
que lo vigila hacia adelante: si mañana alguien ignora otra ruta descargable, se
para y le obliga a decidir dónde vive su archivo.

**Lo que el barrido sí encontró.** `.avi` llevaba desde el principio en
`.gitignore` y **en ninguna de las otras tres superficies** que declaran qué vive
en el bucket: ni en el `aws s3 sync`, ni en el manifiesto, ni en el test de
trazabilidad. Un vídeo con esa extensión se habría descargado, no habría entrado
en git, no habría subido a R2 y no habría figurado en el manifiesto —
irrecuperable en cuanto se apagara el runner, y sin una sola línea roja. Nunca
llegó ninguno. Ahora la lista es una (`common.ARCHIVO_EN_R2`, con `.avi`
dentro) y hay un guardián que compara las cuatro superficies (M2).

**Consecuencia, medida sobre un clon limpio con la base reconstruida de los
volcados:** de 536 medios, **536 se resuelven del archivo y 0 se piden** — 459
fotos por su copia en git y los 77 vídeos por la base. **630,2 MB que dejan de
viajar cada día.** El manifiesto que genera esa corrida es byte a byte el mismo
que el versionado.

**El alcance del guardián, acotado.** Las vías de la base y del manifiesto valen
solo para cuerpos que viven FUERA de git (`ARCHIVO_EN_R2`). Para una foto, que sí
viaja en el clon, **el archivo es el disco**: si falta, se vuelve a traer. Sin esa
distinción, borrar una imagen del repositorio la habría condenado a no recuperarse
nunca — se vería en rojo, pero solo se arreglaría a mano.

**Y el manifiesto se puede verificar desde un clon pelado.** Estaba demostrada la
ida (toda petición A/V figura en el manifiesto con su sha); desde que el manifiesto
**autoriza a no descargar**, hace falta la vuelta: cada objeto suyo tiene que tener
una petición que lo explique. Se comprueba leyendo solo el manifiesto y
`data/dumps/sources_log.csv` —sin base y sin bucket—, que es lo que lo hace
autoverificable. Se cumple 77/77.

**Lo que este cambio NO hace, y hay que saberlo.** Un vídeo cuyo contenido
cambiara en origen manteniendo su URL ya no se detectaría el mismo día: el
archivo dice que es nuestro y no se vuelve a preguntar. Es una consecuencia
directa de tratarlo como activo, no un descuido — y está en
`docs/LIMITACIONES.md` con lo que sí lo detectaría el día que ocurra. Se valoró
revalidar con un `HEAD` diario por objeto; se descarta por ahora porque añade un
método nuevo a `fetch()` y es otra decisión.

**Revisión.** El archivista y el revisor-qa lo rechazaron en su primera pasada, y
los dos encontraron cosas que esta sesión no podía verse sola: **el camino por el
que un cuerpo se pierde en verde** (el archivista) y **un test que pasaba con el
fallo puesto** — `test_un_video_de_la_base_que_falta_en_el_manifiesto_no_es_alerta`
comprobaba la ausencia de un tipo de aviso que en su escenario era imposible, así
que un aviso nuevo cualquiera pasaba entero. Se tiró y se escribió otro que cierra
el conjunto (M1: si pasa con el fallo puesto, no se retoca). **Treinta y dos
mutaciones; ninguna sobrevivió.**

## 2026-08-24 — Se pregunta antes de descargar, y un contenido idéntico no se archiva dos veces

**Contexto (medido sobre las 4.277 filas de `sources_log`, 15 a 23-ago-2026).**
`fetch()` descargaba el cuerpo entero siempre: ni `If-None-Match`, ni
`If-Modified-Since`, ni manejo de 304. El coste:

- `data/snapshots/` ocupa 205 MB, de los que **63,7 MB (31 %) son contenido
  byte-idéntico repetido**: 1.512 ficheros para 1.327 cuerpos distintos.
- De **283 URLs pedidas más de una vez, 164 devuelven siempre lo mismo**. No es
  un caso raro: es más de la mitad del archivo diario.
- El peor caso son las **16 capas vectoriales de Copernicus: 128 descargas para
  16 cuerpos**, 57,4 MB tirados. Ninguna ha cambiado nunca.

**Y la separación que lo hace seguro, que está en el código y no en una
intuición.** El **índice** de la activación (`public-activations/?code=EMSR916`)
se ha pedido 346 veces y ha devuelto **2 contenidos distintos**: cambia, y es
quien revela los productos nuevos. Las **capas** no cambian porque Copernicus
**versiona en la URL** — `..._notAnalysedA_v2.json` —: un producto revisado no
muta de contenido, **aparece como URL nueva**, y quien la revela es el índice.
Dejar de descargar dos veces una capa ya archivada no puede costar un producto.

**Decisión.**

1. **Peticiones condicionales.** Si el archivo tiene una copia utilizable de esa
   URL, `fetch()` manda sus validadores. Un 304 no trae cuerpo: **cero bytes**.
2. **Un 304 no es «no hubo petición».** Deja su fila en `sources_log` con
   `http_status` 304, `bytes` 0 y el `sha256`/`snapshot_path` de la copia
   vigente. Un historiador tiene que poder ver que **ese día preguntamos y la
   fuente contestó que lo mismo** — que es información, no ausencia (R4).
3. **Al llamante le llega el cuerpo vigente con su 200.** `copernicus_layers`
   reconstruye las capas públicas con el cuerpo de cada respuesta y hace
   `if not gj: continue`: un 304 vacío habría borrado del mapa las 16 capas el
   primer día que la fuente dijera «sin cambios». El 304 es un hecho de la red y
   vive en el log, que es donde el archivo guarda la verdad de la red.
4. **Solo se pregunta condicionalmente por lo que se puede servir del archivo.**
   `copia_vigente()` exige fichero en disco **y** sha256 que cuadre con el log.
   Es el invariante que sostiene todo: sin él, un 304 podría dejar al llamante
   sin cuerpo o al log con un sha sin nada detrás.
5. **Un contenido idéntico no se archiva dos veces.** Cuando la fuente no
   soporta condicionales y manda 200 con un cuerpo ya archivado, la fila apunta
   a la copia existente y no se escribe fichero nuevo. **La regla es por
   contenido y por URL, jamás una lista de fuentes «estáticas»**: de las 283
   URLs repetidas, 119 sí cambian, y una fuente quieta hoy puede moverse mañana.

**Dónde viven los validadores: dos columnas en `sources_log`, no una tabla
aparte.** El ETag es *lo que dijo esa respuesta*, igual que `sha256` o `bytes`:
pertenece a la fila. Una tabla de estado por URL sería una segunda copia de algo
que el log ya sabe, y toda segunda copia diverge (M2). Se añaden por
`MIGRACIONES` (nacen en NULL sobre las 4.277 filas viejas: un NULL ahí significa
exactamente «ese día no se lo preguntamos»), viajan solas en el volcado —`dump`
vuelca lo que declara `PRAGMA table_info`— y **no entran en la clave de
deduplicación de `dump_db.CLAVES_ACUMULATIVAS`**, que sigue siendo la tupla de
siete columnas: meterlas ahí habría reventado el primer `dump()` contra el CSV
versionado, que aún no las tiene. Un dump de ayer se sigue reconstruyendo tal
cual, porque `rebuild` inserta por nombre de columna.
`test_unit.py::test_un_dump_viejo_sin_validadores_se_sigue_reconstruyendo`

**Esto no cruza el Principio de archivo.** Nada se sobrescribe y nada se migra:
deja de escribirse una copia redundante de algo que ya está archivado, con su
sha256 y su fila. Es el principio dicho de otra manera — *un contenido que no
cambia es un activo, no un dato archivable*.

**Consecuencia visible, y cómo se lee.** Quien abra `data/snapshots/2026-08-24/`
ya no encontrará ahí la capa de Copernicus: la copia viva es la del 15. Lo
explican dos superficies, con un test que impide que se separen (M2):
`sources_log` (índice completo, versionado en `data/dumps/sources_log.csv`) y un
**`reutilizados.txt` en la propia carpeta del día** —nombre que habría tenido,
ruta de la copia vigente, sha256—, porque el índice no puede exigir que el
lector del futuro sepa que existe un sqlite.

**Lo que casi cuesta el cambio, y se arregló de paso.** Dos sitios leían el
cuerpo de la carpeta de HOY en vez del vigente. Uno era inocuo; el otro,
`gdacs.emm_items()`, alimenta el emparejamiento por topónimo de `crosscheck`: el
primer día que GDACS repitiera su feed se habría quedado sin un solo titular y
**los AOI que solo tienen prensa habrían retrocedido a «pendiente» en silencio**.
Se añade `common.ultimo_snapshot(nombre)` —una sola implementación de «el cuerpo
vigente, sea de qué día sea», que `geo.grid_mmi_vigente` ya hacía por su cuenta
(M2)— y un test estructural que recorre todo `ingest/` buscando el patrón, no el
caso. El reverso también está pinchado: la cronología institucional NO puede
resolver un día reutilizado con el cuerpo vigente, o repetiría el mismo aviso
cada día.

**Lo que avisa (R11).** `alerts.py::cambios_en_peticiones_condicionales` canta,
**agregado**, tres cambios: una fuente que **estrena** el 304 (buena noticia),
una que **deja de honrarlo** y vuelve a mandar los mismos megas, y una que
contesta 304 **sin que le preguntáramos** —contrato roto: esa fila se queda sin
sha y sin ruta, porque no afirma nada sobre nuestro archivo (R13)—. Agregado a
propósito: 16 alertas idénticas el día que Copernicus empiece a contestar 304 se
las salta quien las lee.

**Lo que NO se sabe todavía, y se sabrá solo.** Cuántas fuentes soportan
condicionales no se puede comprobar sin red y no se ha comprobado. Lo que sí
consta: las capas —el mayor sumando, 57,4 MB— las sirve
`rapidmapping-viewer.s3.eu-west-1.amazonaws.com`, un bucket S3, que devuelve
ETag y Last-Modified por contrato. Desde la próxima corrida, la respuesta deja
de ser una conjetura y pasa a ser una consulta:
`SELECT url, etag IS NOT NULL FROM sources_log WHERE ts LIKE '<día>%'`.

**Números.** En los ocho días medidos, con las fuentes honrando los validadores
se habrían evitado **223,9 MB** de descarga (75,0 de la ingesta diaria y 148,9
de las sondas de contrato, que reinterrogan las mismas URLs). Independientemente
de eso —y aunque ninguna fuente soporte el 304— dejan de escribirse **213
ficheros y 83,2 MB** de copias: en un día de corrida completa, 31 de 137
snapshots. El 2.647 MB restante del archivo es otra cosa y no la arregla este
mecanismo: son los vídeos ciudadanos, que se rebajan en R2 y no viajan en git,
así que en el runner nunca están en disco y se vuelven a descargar enteros.
Anotado en `docs/LIMITACIONES.md`. **Resuelto el mismo día, arriba: «Un activo se
archiva una vez».**

## 2026-08-23 — La barra dice «Datos del terremoto»; el sismo baja al encabezado

Contexto: la barra de las 213 páginas se presentaba con «Monitor de brechas» sobre una
segunda línea, «Terremoto de Colombia M7.4 · 10-ago-2026». La entrada «El sitio se
presenta por su nombre público, y la marca sigue siendo doble» (más abajo, del mismo
día) dejó escrito que el nombre interno **se quedaba** en la barra y en la metodología.
Dos hechos la desbordan. El primero: en la metodología no estaba —`grep` de «Monitor de
brechas» en `site/*.html` da manifest, un comentario de `app.js` y el título por defecto
de las notificaciones, y ninguna de las tres es la metodología—, así que la marca doble
se sostenía sobre una sola pata. El segundo: JP decide que la barra diga el nombre
público corto.

Decisión: la marca de la barra pasa a **«Datos del terremoto»** (`render_html.MARCA`) y
**pierde su segunda línea**. Esto **cambia** la decisión anterior, no la aplica; queda
aquí dicho para que nadie la lea como una regresión. «Monitor de brechas» sigue siendo
el nombre interno del proyecto en la documentación, y sigue publicado en las migas de
las 208 fichas, en el `manifest.json` de la aplicación instalable y en el título de las
notificaciones. **Que las migas digan un nombre y la barra otro, en la misma página, es
una decisión editorial pendiente de JP** — no se ha tocado aquí porque cambiar la
primera miga cambia también el `BreadcrumbList` de 208 páginas.

El dato del sismo no se pierde: se muda al encabezado de cada una de las cinco páginas
grandes, en su propio renglón encima del sello de fecha, con una sola redacción
(`render_html.CONTEXTO_SISMO`, «M7.4 · 10 de agosto de 2026 · San José del Palmar
(Chocó)») y un test que ata las cinco copias (`TestContextoDelSismo`). Va escrito y no
generado: es un hecho fijo, y `data-gen` es el mecanismo de lo que caduca con la
corrida. Donde ya lo decía el subtítulo —portada, municipios, RUD— se retira de ahí: la
portada llegó a decirlo dos veces en el mismo encabezado.

**Las 208 fichas no lo reciben.** Su H1 ya dice «Terremoto de Colombia 2026 en X», su
mapa de situación rotula el epicentro con la magnitud y el pie de las 213 páginas lo
escribe entero. Añadirles una línea de contexto sería devolver el subtítulo que se
retiró el mismo día.

Consecuencia medida: la barra pegada baja de 86,30 a 72,55 px en un móvil de 375 px
—13,75 px menos, el **15,9 %** de la propia barra— y de 54,75 a 50,55 px en escritorio.
Es altura recuperada en cada scroll de cada página, que era lo que la segunda línea
costaba.

## 2026-08-23 — La fila entera de municipios lleva a la ficha, y el dato sigue copiable

Contexto: en `municipios.html` solo el nombre del municipio enlazaba a su ficha: un
objetivo de una palabra en una fila de diez columnas, y en móvil, donde se lee este
monitor, un blanco diminuto.

Decisión: **enlace estirado, sin JavaScript**. La fila es `position: relative` y el ancla
del nombre extiende un pseudoelemento sobre ella. Sigue habiendo **un solo `<a href>`
real** —rastreable, enfocable con el tabulador y con su destino en la barra de estado—;
lo que crece es la zona de clic.

Y el efecto colateral del patrón, **medido y no supuesto**: con la capa puesta y nada
más, arrastrar el ratón sobre «26.377» devuelve una selección vacía, y los `title` que
explican estado, población y satélites dejan de aparecer. En una tabla de cifras que la
gente copia eso es una pérdida real. Por eso el contenido de la fila se sube por encima
de la capa, y de ahí sale la regla que gobierna cómo se escribe: **nada cuelga pelado de
un `<td>`** —un texto sin elemento no se puede subir por CSS—, así que cada cifra viaja
en su `<span>` (`valor_suelto()`). Contrastado en el navegador: sin esa regla la misma
selección devuelve cadena vacía; con ella devuelve el texto de la fila.

El reparto que resulta, medido y no estimado: los renglones escritos ocupan el **14 %**
de la superficie de la fila, y preguntando punto a punto quién recibiría el clic, el
**85 %** de la fila lleva a la ficha (22.592 puntos sobre las tres filas más altas de la
tabla, que son las que más texto llevan). Pulsar
exactamente sobre una cifra no abre la ficha —ahí manda el dato: se selecciona y enseña
su explicación—; pulsar en cualquier otro punto, sí. El nombre del municipio es la
excepción y no renuncia a nada: está dentro del ancla, así que se puede seleccionar y
sigue navegando.

Consecuencia: `municipios.html` pasa de 273 a 293 KB (unos 1.450 `<span>`), lejos del
aviso de 400 KB de `seo_check`; ninguna fila se pierde. El foco se percibe en la fila
—`tr:focus-within` la tiñe— sin apagar nunca el anillo del navegador sobre el enlace.
Fuera de alcance por decisión de JP: la tabla de `rud.html`, cuyas filas no tienen
ningún enlace y cuyo cruce con el catálogo curado es el que ya falló con «Guadalajara de
Buga» (R10, M8); eso lo escribe la ingesta en la fase 4.

## 2026-08-24 — Un error en cómo mostramos el dato se corrige; el cambio lo documenta git

Contexto: al revisar qué se versiona apareció que `data/dumps/citizen_reports.csv` lleva
la coordenada exacta de los 542 reportes ciudadanos, mientras el sitio promete publicarla
redondeada a ~110 m. Al discutir cómo arreglarlo se invocó la inmutabilidad de los
snapshots como argumento para no tocar lo ya publicado — y ahí se vio que estábamos
mezclando dos capas distintas.

Decisión de JP: **si encontramos un error en la manera en que mostramos los datos, se
corrige, y eso manda sobre conservar la versión equivocada.** Los cambios no se archivan:
se documentan en git, que es su sitio, y los datos se arreglan para que correspondan.

La distinción que queda escrita en `CLAUDE.md`: **lo que la fuente dijo es intocable**
—el snapshot, su sha256 y su fila en `sources_log`—; **lo que nosotros hicimos con lo que
dijo es responsabilidad nuestra y se corrige**. Un dato mal derivado, mal redondeado o
mal rotulado no es archivo histórico: es un error, y dejarlo puesto para «no tocar el
pasado» publica una falsedad con aspecto de registro. Las dos trazas se conservan: el
snapshot demuestra qué dijo la fuente, el commit demuestra qué corregimos y cuándo.

Consecuencia: las correcciones retroactivas de lo publicado dejan de necesitar
justificación caso a caso. Lo que sigue necesitándola es tocar un snapshot, que no se
hace nunca.

## 2026-08-23 — Reglas de método (M1–M10): las cicatrices se escriben en el contrato

Contexto: en una sola jornada de rediseño aparecieron cuatro errores del mismo tipo, y
ninguno era un error el día que se escribió. Dos URL declaradas dos veces con la copia
muerta envejeciendo. Un pie que vivía en Python y en JavaScript y llevaba meses siendo
más pobre en 208 páginas sin que nadie lo viera. Un plegable estilado por sus cuatro
ubicaciones en vez de por lo que es, con una víctima ya publicada. Una identidad de autor
con el nombre interno en un sitio y el público en otro. Se estropearon solos, después,
porque nada vigilaba que las copias siguieran diciendo lo mismo.

En la misma jornada, cuatro tests escritos para cazar un bug **pasaron en verde con el
bug puesto**: uno buscaba una palabra que estaba en el comentario de su propio autor,
otro comparaba conjuntos sobre el fichero entero y sobrevivía si el defecto quedaba en
uno de los dos sitios, y dos guardianes «de sí mismos» comprobaban «la lista no está
vacía». Y una pregunta al mantenedor se hizo sobre una premisa falsa —«sin emoticonos,
como las fichas», cuando las fichas los tenían—, así que hubo que volver a preguntar.

Decisión: `CLAUDE.md` gana una sección de **reglas de método M1–M10**, hermana de las
reglas de rigor R1–R16. Las R son sobre los datos; las M, sobre cómo se trabaja. Cada M
lleva **la cicatriz que la causó**: una regla sin el incidente que la originó no se
recuerda y acaba siendo decoración. Se citan por su número en las revisiones —«esto
incumple M2»— igual que las R.

Y un mecanismo para que la lista crezca sola: un error que aparece por **segunda** vez
deja de ser un error y pasa a ser un patrón; se escribe con su cicatriz y, si es
automatizable, llega acompañado de su test, validado por M1.

Consecuencia: las revisiones tienen vocabulario para nombrar fallos de método, no solo de
datos. M1 (validar rompiendo) y M2 (toda segunda copia diverge) ya han cambiado tres
commits de este rediseño: el chip que deducía su maqueta de sus hijos, el inventario del
pie fijado por destino, y el marcado estructurado, donde se descubrió que `@id` **no
resuelve entre documentos** y que por tanto una identidad repetida en 213 páginas solo la
sostiene un test, nunca la sintaxis.

Una regla que estorbe se discute y se retira, con su entrada aquí. Lo que no se hace es
ignorarla en silencio.

## 2026-08-22 — Un chip es una acción; lo que no se pulsa, no es un chip

Contexto: la misma pastilla `.chip` hacía dos oficios. En los filtros de la portada, del
RUD y de municipios es un `<button>` que enciende una capa o filtra una tabla. En la lista
de titulares es un `<span>` con la zona, el departamento y el municipio que menciona la
noticia. El CSS ya reconocía la duplicidad en un comentario y la resolvía a medias: daba
`cursor: pointer` y resalte solo al botón, pero **en reposo las dos eran idénticas** —mismo
borde, mismo radio de pastilla, mismo fondo—. El resultado es que `noticias.html` sirve
**316 pastillas con aspecto de control que no hacen nada**: quien aprende en la portada que
un chip se pulsa, se encuentra 316 que no.

Decisión: `.chip` queda reservado a lo que se pulsa y declara `cursor: pointer` en la clase
base. Lo pasivo pasa a `.etiqueta`, que deja de parecer un control: sin borde, sin radio de
pastilla, fondo tenue y tipografía de metadato. Sigue agrupando visualmente —es la zona o
el municipio del titular— pero ya no promete un clic que no existe. El marcado no cambia de
elemento: ya era `<span>` frente a `<button>`, así que la semántica era correcta y lo que
fallaba era solo el aspecto.

Vive en DOS superficies, y las dos se tocan a la vez: `site/noticias.js` las pinta en el
navegador y `deploy/render_html.py` las escribe en el build. Si divergen, la misma etiqueta
se ve de dos maneras según se ejecute o no el JavaScript.

Consecuencia: `tests/test_frontend.py::TestChipsSonAcciones` cae si un `<span>` recupera la
clase de acción, si las dos superficies dejan de pintar la misma, si dejan de nombrarse
mutuamente en el código, o si `.etiqueta` vuelve a copiar el borde, el cursor o el radio de
pastilla del chip —renombrar sin cambiar el aspecto no habría arreglado nada—. Validado por
mutación: al reintroducir `class="chip"` en el span, caen dos.

## 2026-08-22 — El mapa enseña los 196 municipios que nadie miró desde el aire

Contexto: el mapa de portada solo podía pintar evidencia — zonas de Copernicus, puntos de
UNOSAT y de ICube-SERTIT, reportes ciudadanos. Todo lo que enseñaba era, por construcción,
lo que alguien había mirado. Pero la tesis del monitor es la contraria: la distancia entre
lo que se ve y lo que se cuenta. Había 196 municipios con familias inscritas en el RUD a
los que no ha mirado ninguno de los tres satélites, y en el mapa eran exactamente igual de
invisibles que un municipio sin daño. La ausencia no se leía porque no se dibujaba.

Decisión: entra la capa de la ausencia, encendida de entrada y al fondo (`bringToBack`), con
anillo punteado y relleno tenue — la evidencia que sí existe tiene que seguir mandando. El
rojo lo grada la intensidad que el ShakeMap del USGS estima para la cabecera municipal,
derivada con `MMIGrid`, que ya existía en `ingest/geo.py` para la verificación ciudadana; la
búsqueda del snapshot vigente se sube a `geo.py::grid_mmi_vigente` porque ya son dos los
consumidores. Se descartó la intensidad **percibida** (`dyfi_max_cdi`, el DYFI del USGS): es
lo que la gente sintió y sería el dato preferible, pero solo cubre 23 de los 196 y con él el
mapa quedaba en blanco. La rejilla llega a 187 de los 196 (al 22-ago-2026; las cifras vigentes están en `municipios_mapa.json`). Los nueve restantes caen fuera del ShakeMap y se
pintan grises: fuera de la rejilla no hay «intensidad baja», hay ausencia de dato, y el rojo
más pálido habría sido un cero disfrazado, además del más tranquilizador (R3).

La capa va en `data/public/municipios_mapa.json`, un fichero propio de 30 KB, porque
`municipios.json` pesa 340 KB por los ejemplos de prensa que el mapa no usa hasta que se
abre un globo. Y el filtro se aplica en el build, no en el navegador: la cifra que el sitio
enseña y los puntos que pinta salen del mismo recuento, que es justo lo que faltaba el día
que la portada decía 36 municipios con 43 en su propia tabla.

Dos cifras del mismo hecho, y las dos ciertas: la portada publica 196 y
`municipios.html` 197. La diferencia es Palmira, que no tiene producto satelital pero
tampoco fila en el RUD, y sale de que las dos páginas hacen preguntas distintas
(`municipios.py::sin_mirada_satelital` exige damnificados registrados;
`site/municipios.js::miradoPorSatelite` no). Legítimo; lo que no lo era es lo que se
publicó primero: un rótulo que enunciaba el predicado sin su condición —«municipios sin
producto de daño satelital»— sobre el recuento que sí la aplica. Ahora ambas superficies
dicen «con damnificados y sin producto de daño satelital», y se nombran mutuamente en el
código, como manda el patrón de R8 y R10 para una regla que vive en dos idiomas.

Consecuencia: el rótulo del dato viaja dentro del JSON (`fuente_mmi`), para que quien lo
descargue no confunda un modelo con una medición, y también se publica cuántos se quedaron
sin intensidad (`sin_mmi`), porque una laguna que se cuenta es mejor que una que se descubre
mirando el mapa. `tests/test_unit.py::TestCapaDeLaAusencia` cae si un municipio que estrena
mirada satelital no desaparece solo de la capa (R11), si uno sin registro entra, si el
recuento publicado deja de coincidir con la lista, o si un municipio fuera de la rejilla
recibe el escalón más bajo en vez de ausencia, si el rótulo de la capa deja de enunciar
su condición, o si las dos superficies de la regla dejan de nombrarse.

De paso salió un error más viejo, en código compartido: los recuentos satelitales se
comprobaban con `bool()`, así que un municipio evaluado con cero edificios con grado de
daño figuraba como no evaluado. Antes eso era un estado impreciso; con esta capa pasaba a
ser una afirmación falsa publicada —«nadie ha mirado aquí»— sobre un municipio que sí se
había mirado. Corregido a `is not None` en `municipios.py` y en la comparativa de
`render_html.py`. Hoy no hay ningún municipio a cero, así que no cambia ninguna cifra: es
una trampa desarmada antes de que se dispare.

## 2026-08-22 — La banda de brechas se escribe en el build, no en el navegador

Contexto: la portada prerenderiza sus tablas con `deploy/render_html.py` desde que se
descubrió que los rastreadores de sistemas de IA no ejecutan JavaScript. La banda amarilla
—el resumen de las dos brechas centrales: cuánto llevan calladas las fuentes oficiales
abiertas y cuánta población expuesta queda fuera de las zonas mapeadas por satélite— se
había quedado fuera de ese trabajo. Era una `<section>` vacía en el HTML servido y su
contenido lo inyectaba `site/app.js` al abrirse la página. Es, con diferencia, el párrafo
más citable del sitio: quien lo tiene que citar era precisamente quien no lo veía.

Decisión: la banda pasa por el mismo camino que las tablas. El contenedor lleva
`data-gen="brechas"`, el texto lo escribe `render_html.py::banda_brechas` durante el build
y el inyector —renombrado a `inyectar_prerenderizado`, porque ya no rellena solo tablas—
acepta también `<section>`. La redacción vive en Python **y en ningún otro sitio**: el
JavaScript de portada dejó de construir el párrafo y se limita a refrescar los contadores
de días, lo único que depende del reloj de quien lee y no de la fecha de construcción. Van
en `<span data-dias-desde="AAAA-MM-DD">`, con «hace» y «días» fuera del span para que la
prosa tampoco se escriba dos veces. Los helpers que ambos lados necesitan se centralizan en
`site/ui.js` (`aoiEs`, `zonasSinRegistro`, `ejemplosSinRegistro` — el diccionario de zonas
estaba duplicado en `app.js` y `noticias.js`) y `render_html.py` los replica con test de
espejo ejecutado con node contra el `monitor.json` real. El aviso de datos no cargados deja
de sobrescribir la banda y se antepone: el resumen sigue siendo cierto aunque el mapa falle.

Consecuencia: la portada sirve 3.225 palabras en vez de 3.055, y las dos brechas se leen sin
ejecutar una línea de JavaScript. `ingest/seo_check.py` vigila ahora también las secciones
marcadas, no solo `<tbody>` y `<ul>`, y `tests/test_render_html.py::TestBandaDeBrechas` cae
si la banda vuelve a llegar vacía al artefacto —por marca retirada, generador desconectado o
contenedor no reconocido—. De paso, el porcentaje de cobertura satelital pasa por `pct()` y
se publica «9,9 %» en vez del «9.9 %» con punto que imprimía el número crudo del JSON.
## 2026-08-22 — Las cifras de atributos las escribe el build; las del README van fechadas

Contexto: el diagnóstico que siguió a la nota de portada encontró el mismo patrón en dos
superficies más. La `og:description` de la portada —lo que se ve al compartir el enlace—
anunciaba «430+ reportes ciudadanos» con 542 archivados, y el README, «430+ reportes» y
«3.000+ noticias» con 6.304 titulares. El «+» las salvaba de ser falsas, pero subestimaban
a la mitad y nadie las vigilaba. Ninguna de las dos admite la solución de la portada: en un
atributo `content` no cabe un `<span data-gen>`, y un README no pasa por el build.

Decisión: dos caminos según la superficie.

- **En el HTML**, marcador `{{clave}}` y `deploy/render_html.py::sustituir_cifras` escribe
  el dato del día sobre todo `dist/`, fichas municipales incluidas. Un marcador sin valor
  **rompe el build a propósito**: no es una fuente que falla (R13), es un error de
  programación, y publicar «{{reportes_ciudadanos}}» en la etiqueta que se comparte es peor
  que no publicar. `ingest/seo_check.py` lo vigila además en el artefacto.
- **En el README**, cifras **fechadas** («542 reportes ciudadanos … al 22-ago-2026»): una
  cifra con su fecha describe un momento y no envejece, solo se queda corta. El guardián
  (`tests/test_unit.py::TestCifrasFechadasDelReadme`) exige que no sobreafirme y **no pone
  cota por abajo a propósito**: obligar al README a seguir el ritmo del corpus lo dejaría en
  rojo cada mañana sin que nada estuviera roto, que es justo la avería que se evita.

Consecuencia: quedan tres reglas según cómo se comporte la cifra. Si se mueve y va en el
HTML servido, la escribe el build. Si se mueve y vive fuera del build, va fechada y con
guardián de no-sobreafirmación. Si describe un hecho pasado —«UNOSAT reeditó Viterbo de 154
a 108»—, no se toca: ya lleva su momento dentro.

## 2026-08-22 — La cifra que va dentro de un párrafo también la escribe el build

Contexto: la nota de portada anunciaba a mano «los satélites han mirado 11 municipios; la
comunidad ha documentado 36» mientras su propia tabla, tres párrafos más abajo, listaba 43
municipios con reportes ciudadanos. No es un descuido aislado: el recuento ciudadano se
mueve con cada corrida diaria, así que la frase envejece sola. Ya había pasado antes —el
día que el conteo satelital incorporó a UNOSAT— y entonces se arregló volviéndola a
escribir a mano. La tabla que la desmiente sí se genera en el build desde el dato del día.

Decisión: la frase se genera en `deploy/render_html.py::nota_mirada_portada`, a partir de
las mismas filas que ordenan la tabla (`municipios_con_evidencia_puntual`), y se inyecta
en `dist/` por la puerta que ya existía para las tablas, ampliada de `<tbody>`/`<ul>` a
`<span>`: una cifra escrita dentro de un párrafo envejece igual que una fila. El generador
devuelve la oración entera, raya incluida, para que un build que no la inyecte deje una
frase correcta sin cifra y nunca una raya huérfana. `ingest/seo_check.py` vigila también el
contenedor de prosa vacío, y el test que comparaba el texto del repo con los datos pasa a
comparar el generador con los datos, más otro que exige que en `site/index.html` no quede
ninguna cifra escrita a mano.

Consecuencia: el texto del sitio y su propia tabla no pueden contradecirse, y el mecanismo
queda disponible para cualquier otra cifra que hoy viva dentro de un párrafo. El HTML del
repositorio conserva el blame: sigue sin cambiar cada día.

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

### El monitor se muda a dominio propio (22-ago-2026)

`brechas.orkidea.eu` colgaba de un dominio personal: si esa renovación falla, se
lleva por delante un archivo que promete ser reconstruible dentro de veinte años.
El monitor pasa a **`datosdelterremoto.org`**, registrado aparte y con el DNS en
Cloudflare, donde ya viven el worker, R2 y las analíticas.

Se eligió `.org` sobre `.co` por dos razones que pesan más que la señal local:
renovación estable y barata para un archivo de décadas, y una lectura no comercial
que separa al monitor de los agregadores de subsidios que ocupan las búsquedas de
«consultar damnificados». Como en Colombia lo oficial es `.gov.co`, el `.org`
también desactiva por sí solo la lectura de que esto sea un portal del Estado.

**El dominio viejo no se abandona: se redirige con 301 permanente, indefinidamente.**
Hay URLs publicadas en prensa, en el archivo y en consumidores automáticos de los
JSON y el CSV. Por eso las URL autorreferenciales de los hitos pasaron a rutas
relativas: el hecho archivado es el hito, no el host desde el que se sirvió, y así
no vuelven a caducar en la próxima mudanza.

Lo que **no** se reescribe: `docs/` y los snapshots. Son archivo fechado, y
cambiarles el dominio falsearía lo que se dijo entonces.

### Los títulos dejan de firmar y pasan a responder (22-ago-2026)

Los `<title>` medían entre 95 y 124 caracteres y terminaban en `| Monitor de
brechas`. Google corta cerca de los 60: las palabras que importan quedaban fuera de
la pantalla de resultados, y los 22 caracteres finales los gastaba una marca que
nadie busca. El nombre del sitio se declara ahora en el JSON-LD (`WebSite.name`),
que es de donde el buscador lo toma.

Se corrigió además el nombre de la fuente: es **Registro Único de Damnificados**,
no «oficial» ni «unificado». Un monitor que audita a otros no puede equivocarse en
cómo se llama lo que audita — y además esa es la forma con la que se busca.

La marca sigue siendo doble a propósito: «Monitor de brechas» describe lo que el
sitio hace y vive en la navegación y en la metodología; «Datos del terremoto de
Colombia 2026» es el nombre público, alineado con el dominio.

### Avisar en vez de esperar: IndexNow en cada corrida (22-ago-2026)

El sitio se regenera a diario, pero un buscador solo se entera cuando vuelve a
pasar, y por la cola larga de fichas municipales eso son semanas. Justo ahí —el
municipio pequeño del Chocó que nadie más publica— es donde el monitor aporta y
donde llegar tarde equivale a no llegar. Desde hoy, cada corrida avisa por
IndexNow de lo que cambió.

**Se avisa solo de lo que cambió, y eso exige recordar lo de ayer.** Las cinco
páginas fijas entran siempre, porque sus cifras cambian a diario; de las 208
fichas entran las que difieren de la corrida anterior, comparando la huella
sha256 de sus datos guardada en `data/indexnow_estado.json`. Avisar de las 213
cada día sería equivalente a no avisar de ninguna.

**El estado solo avanza si el aviso se aceptó.** Si el buscador falla, mañana se
reintenta el mismo listado: se prefiere avisar dos veces a perder la ficha que
sí cambió.

La clave del protocolo no es un secreto —se publica en la raíz, en un fichero
cuyo nombre es la clave— y por eso vive en `deploy/root/`, no en configuración:
la única copia es la publicada y rotarla es sustituir ese fichero. Un test
comprueba que el nombre y el contenido coinciden, porque si no el buscador
rechaza el aviso sin decir por qué.

Se añadió `common.notificar()` para no romper R4: un POST de aviso no trae datos,
pero sigue siendo una petición que hicimos, y queda en `sources_log` con el
sha256 del cuerpo **enviado** —lo que se archiva es lo que dijimos—.

Se descartó, de momento, Crawler Hints de Cloudflare, que hace lo mismo con un
interruptor: exige tener el proxy delante y decide él qué notificar. Esto es
determinista, queda en el archivo y sobrevive a un cambio de proveedor.

Y se declararon explícitamente `OAI-SearchBot` y `ChatGPT-User` en `robots.txt`.
Ya estaban permitidos por el comodín, pero el fichero declara uno a uno a los
rastreadores de IA para que un cambio futuro no los excluya sin querer, y esos
dos —no GPTBot, que solo entrena— son los que deciden si ChatGPT cita el sitio.

### La clave que desambigua no es el nombre que se lee (23-ago-2026)

Colombia tiene municipios homónimos: hay un Riosucio en Caldas y otro en Chocó,
y tres nombres más repetidos —Argelia, Balboa y Bolívar—, cada uno en dos
departamentos entre Cauca, Valle del Cauca y Risaralda. El monitor los distingue
en su diccionario poniendo el departamento entre paréntesis —`Riosucio
(Caldas)`—, porque una llave no puede repetirse.

Esa llave se estaba publicando como si fuera el topónimo. Cinco fichas salían
tituladas **«Terremoto en Riosucio (Caldas) (Caldas) 2026»**, con el
departamento escrito dos veces en el `<title>`, el H1, la `description`, el
JSON-LD y las migas. El repositorio ya había aprendido esta lección en
`municipal_google_news_feeds()`, donde buscar la clave literal daba un feed en
cero para siempre; la ficha no la había aprendido.

`toponimo(clave, depto)` recorta **solo el paréntesis final que coincide
exactamente con el departamento**, no cualquier paréntesis: un municipio que
algún día lleve uno de verdad en su nombre no puede salir mutilado. Y el
enlace al mapa de la portada **sigue viajando con la clave**, porque `app.js`
indexa por ella (`munLayerById[pedido]`) y es lo único que distingue los dos
Riosucios; con el topónimo, el mapa se quedaría quieto sin decir por qué.

Se corrige en el mismo sitio la concordancia. En la `description` eran 13
fichas —15 frases, porque dos fallaban en las dos— que decían «1 familias
inscritas» o «1 viviendas averiadas». La revisión destapó tres sitios más con el
mismo defecto, y entran en la misma corrección: «1 destruidas» en la tarjeta de
viviendas, «1 reportes ciudadanos» en el resumen de evidencia y «1 viviendas
destruidas y 1 averiadas» en el párrafo de respuesta. `concuerda()` pone el
singular solo en el uno; el «—» de un dato ausente conserva el plural, porque
una ausencia no es una unidad (R3).

**El guardián vigila la duplicación, no la longitud.** `seo_check.py` devuelve
código 1 si el título, el H1 o la `description` de una ficha repiten el
departamento —bloquea al ejecutarlo a mano; en el despliegue avisa sin frenarlo,
porque el flujo lo corre con `continue-on-error` (R11)—. Vive en su propio
bucle: el que ya recorría las fichas corta con `break` para no repetir el mismo
aviso 208 veces, y colgado de él este chequeo dejaba de mirar el resto. No comprueba que el título quepa en 60 caracteres, aunque 77 de
los 208 no quepan: eso está decidido y documentado como laguna
(`LIMITACIONES.md`), y un guardián que falla desde el primer día contra una
decisión tomada es ruido, no vigilancia.

### El sitio se presenta por su nombre público, y la marca sigue siendo doble (23-ago-2026)

No es una decisión nueva: es aplicar la del 22 de agosto de 2026, que ya había
separado los dos nombres. Faltaban dos piezas.

`og:site_name` **no existía en ninguna página** —ni en las cinco ni en las 208
fichas—: ahí no había un conflicto entre dos marcas, había una ausencia. Se
declara con el nombre público, el mismo que ya llevaba `WebSite.name`.

Y el pie abría con «Monitor de brechas de reporte», el nombre interno, que no
busca nadie. Ahora abre con «Datos del terremoto de Colombia 2026» y despliega
qué cruza el sitio con el léxico del corpus, siguiendo `SEO-GEO.md`: no competir
en el territorio de la noticia, sino en el del dato municipal trazable. El
texto vivía **en dos superficies espejo** —`site/common.js` para las cinco
páginas y `pie_estatico()` para las 208 fichas—. Ya no: las dos se fundieron el
mismo 23 de agosto (ver la entrada siguiente) y hoy hay una sola.

«Monitor de brechas» **se queda** en la barra y en la metodología. Quitarlo de
ahí no sería aplicar la decisión, sería cambiarla.

**El subtítulo de la ficha se retira**: decía en otras palabras lo que ya dice
el H1, y lo que prometía —damnificados, daños, cobertura— lo cumple la tira de
cifras una línea más abajo. El código DIVIPOLA y la fecha de la corrida no
desaparecen con él: bajan a «Fuentes y trazabilidad». La fecha estuvo a punto
de perderse en el camino —el prototipo se llevaba el subtítulo entero— y un
archivo que no dice de cuándo es su cifra deja de ser un archivo.

### La barra y el pie se escriben una sola vez, en el build (23-ago-2026)

Contexto: el sitio tiene 213 páginas y su navegación estaba escrita **dos
veces**. Las 208 fichas municipales la traían en el HTML desde el build
(`nav_estatico()` / `pie_estatico()`); las cinco páginas grandes la recibían del
navegador (`site/common.js`), y por tanto **llegaban sin barra y sin pie a quien
no ejecuta JavaScript**: ni un enlace interno, ni el pie que dice de qué va esto.
Dos copias del mismo texto en dos lenguajes, sincronizadas a mano y vigiladas por
un test de espejo. Ya habían divergido en tres sitios: los emoticonos de los
enlaces, dos enlaces del pie (el RSS de balances y el canal de Telegram) y el
destino del rótulo de la marca.

Decisión: **`deploy/render_html.py` es la fuente única**. Un paso propio del
build, `escribir_barra_y_pie()`, las escribe también en las cinco páginas. No se
reutilizó el mecanismo de `data-gen` a propósito: aquel empareja un generador con
una sola página y sirve para los **datos del día** —lo que caduca con la
corrida—, y una barra de navegación no es eso.

Tres consecuencias visibles:

- **Los enlaces pierden el emoticono** (🗺️ 🏘️ 🏛️ 📊 📰), como el prototipo
  aprobado. Lo llevaban las dos superficies, así que también lo pierden las 208
  fichas. **El 📍 de «Reportar daño» se queda**: ahí el icono señala una acción,
  no decora una etiqueta.
- **Los dos controles que solo sirven con JavaScript** —🔔 alertas y ↗ compartir—
  los emite ahora `nav_estatico(botones_js=True)`, y **solo en las cinco
  páginas**. Es la trampa del cambio: `common.js` los busca por `getElementById`
  y **hace `return` en silencio** si no están, así que olvidarlos habría quitado
  el botón de compartir de la portada sin que nada avisara. El valor por defecto
  del parámetro es el de las fichas, que nunca los tuvieron.
- **El pie de las fichas gana los dos enlaces que le faltaban** (RSS de balances
  y canal de Telegram). Se omitían para no duplicar en Python dos URLs que vivían
  en `site/ui.js`; con una sola superficie esa razón desaparece, y el pie del
  sitio pasa a ser el mismo en las 213 páginas.

El test de espejo se quedó sin objeto y **se sustituye por el guardián que ahora
hace falta**: que las cinco páginas del artefacto traigan `#site-nav` y
`#site-footer` escritos, con su propio enlace marcado como activo, y que
`common.js` no vuelva a escribirlos. `ingest/seo_check.py` lo mira además sobre
`dist/` y lo trata como **fallo, no aviso**: por el mismo criterio que un
contenedor `data-gen` vacío —es determinista, no depende de ninguna fuente que
pueda fallar (R13) y deja la página sin la única red de enlaces que la conecta
con las otras 212—. Estos dos contenedores no llevan `data-gen`, así que el
chequeo que ya existía no los veía.

Consecuencia medida sobre `dist/`: las cinco páginas ganan **216 palabras cada
una** en el HTML servido (index 3.259 → 3.475 · municipios 3.552 → 3.768 · rud
2.603 → 2.819 · balances 1.880 → 2.096 · noticias 6.277 → 6.493), sin perder
ninguna fila.

### Un `Dataset` no vive dentro de otro: la identidad se referencia (23-ago-2026)

Contexto: las 208 fichas municipales publicaban su tarjeta legible por máquina
—el `Dataset` de schema.org que dice qué contiene la página— con una línea que
decía «esto forma parte del sitio» **embebiendo un segundo `Dataset` completo**:

```json
"isPartOf": {"@type": "Dataset", "name": "Datos del terremoto de Colombia 2026",
             "url": "https://datosdelterremoto.org/"}
```

Google valida **recursivamente cualquier nodo `"@type": "Dataset"`**, esté a la
profundidad que esté. Ese nodo anidado no es un enlace: es un dataset
independiente al que se le exigen sus propios campos, y no tenía `description`.
Un dataset inválido en las 208 fichas, en producción. El test que debía cazarlo
—`test_json_ld_parseable_con_divipola`— **miraba solo el nodo raíz** y llevaba
meses en verde: otro guardián que no guarda (M1).

Decisión, en tres partes:

1. **No se parchea añadiendo el campo que falta: se cambia la forma.** El nodo
   anidado desaparece y quedan dos referencias por `@id`, `isPartOf` e
   `includedInDataCatalog`, que no son nodos que validar sino punteros. Así
   nadie puede copiar mañana el patrón malo, que es lo que un `description`
   añadido habría dejado intacto.
2. **Un nodo de identidad, idéntico en las 213 páginas**, con la `Organization`
   que publica y un nodo `["WebSite", "DataCatalog"]` —JSON-LD admite `@type`
   como lista, y esto es a la vez el sitio y el catálogo de los 208 datasets
   municipales—. Vive en **una sola constante**, `render_html.py::IDENTIDAD`,
   serializada una vez en `BLOQUE_IDENTIDAD`.
3. **Las cinco páginas grandes lo reciben del build, no del copiar y pegar.**
   `escribir_barra_y_pie()` pasa a llamarse **`escribir_piezas_compartidas()`**
   y escribe una tercera pieza en el `<head>` de las cinco, con el mismo
   mecanismo de marcador vacío que la barra y el pie. Repetir el literal en
   `site/*.html` habría creado seis copias de algo **cuya única virtud es ser
   idéntico**: la definición de M2.

El porqué del punto 3 no es de estilo. **`@id` NO resuelve entre documentos**:
dentro de una página un parser fusiona los bloques y resuelve las referencias,
pero entre páginas distintas cada URL se procesa aislada, y un
`{"@id": "…#organization"}` en la ficha de Cali **no** va a buscar su definición
a la portada. Lo que hace que las 213 hablen de la misma entidad no es la
sintaxis: es que el valor sea el mismo en las 213. Eso solo lo garantiza una
constante única **más un test que lo compruebe**.

De paso, tres correcciones de la misma familia:

- Las cuatro descargas de la portada declaraban `contentUrl` **relativo**
  (`/data/public/crosscheck.csv`). Una ruta relativa depende de conocer la URL
  base del documento: cierto para un navegador, **falso para el indexador de
  datasets que extrae el bloque JSON-LD como JSON suelto**, que es justo quien
  lo lee. Lo mismo en `balances.html`.
- El `creator` de la portada decía «Monitor de brechas de reporte de
  desastres» —el nombre interno— y pasa a referenciar la identidad compartida.
  Es la misma avería de identidad doble que ya se corrigió en el pie.
- El `isPartOf` de `noticias.html` embebía otro `WebSite` con nombre y URL.
  Con el nodo de identidad en la página serían **dos entidades sitio en el
  mismo documento**: pasa a referenciar `#site` por `@id`.

Consecuencia: `TestMarcadoEstructurado` construye las 213 páginas y las recorre
enteras. **G2**: ningún `Dataset`, a cualquier profundidad, sin `name` y
`description` no vacíos — y ninguno anidado dentro de otro. **G6**: toda URL de
`contentUrl`/`url`/`logo`/`@id` es absoluta, comprobado **sobre el JSON
parseado y no sobre el texto crudo**, para no dar falsos positivos con URLs
externas legítimas. Los nueve bugs que se le metieron a propósito mueren, el
de hoy incluido (M1). El HTML visible no cambia: las cinco páginas conservan
sus palabras exactas (3.475 · 3.768 · 2.819 · 2.096 · 6.493), porque
`seo_check` descarta los `<script>`.

**Lo que NO entra en esta pasada**, y queda para la ficha: `variableMeasured`
con valor y unidad, `citation` con las fuentes que de verdad tienen dato, y
`measurementTechnique` —el campo que impide que una IA confunda «familias
**inscritas**» con «**verificadas**»—. Con `variableMeasured` llega su guardián
G1: ningún `value: 0` donde el origen es `None`, que es la R3 en el marcado.

## 2026-08-23 — El sello de fecha: la corrida no es la fecha del dato

Contexto: las cuatro páginas con encabezado escribían «Actualizado el 22 de agosto de
2026» desde el navegador, con `getElementById("generado").textContent`. En `rud.html` esa
frase era falsa: `rud.json` se genera el 22 con una serie que **termina el 21**, así que
la página fechaba en el 22 unas cifras del 21 — y lo hacía en HTML indexable y con
permanencia de archivo, que es donde una confusión se queda a vivir (M7: toda cifra de
una fuente viva lleva su corte).

Las cuatro llamadas iban además **sin guarda**. Quien no ejecuta JavaScript —los
rastreadores de sistemas de IA— leía una raya; y una `TypeError` sobre `null` dentro de un
IIFE `async` **rechaza la promesa en silencio**, así que un cambio en el encabezado se
habría llevado por delante el resto del guion de la página sin un aviso.

Decisión: un componente, `render_html.py::sello_fechas(hasta, corrida, que)`, y cuatro
generadores que lo alimentan desde cuatro fuentes distintas —`monitor.json`,
`municipios.json`, `rud.json` y `oficiales.json`—. Se sirve desde el build por el
mecanismo `data-gen`, como las tablas y la banda de brechas. Ninguna fecha se escribe a
mano (R4) y las dos viajan en un `<time datetime>` legible por máquina.

- **El RUD y los balances dicen las dos**: «Datos del RUD hasta el 21 de agosto de 2026 ·
  corrida del 22». En los balances el corte del dato es la **última** `search_date`, no la
  del fichero. Cuando las dos fechas caen en el mismo mes, la corrida se dice solo con su
  día; en cuanto cambia el mes se escribe entera, porque «corrida del 1» sería un acertijo.
- **La portada y los municipios dicen solo la corrida**: sus fuentes no publican hasta
  dónde llega la serie, y **M10 prohíbe inventar la otra** — donde falta el dato se calla
  ese trozo. Si faltasen las dos, el sello lo dice con todas las letras: devolver una
  cadena vacía dejaría el contenedor `data-gen` vacío y eso rompe el build.
- **A las cuatro llamadas del navegador no se les pone un `if`: se les quita el motivo.**
  `app.js`, `municipios.js`, `rud.js` y `balances.js` dejan de tocar `#generado`.

Consecuencia: `TestSelloDeFecha` ejecuta el inyector real sobre los cuatro HTML del
repositorio y exige sello no vacío con `<time>`; `TestElSelloYaNoLoEscribeElNavegador`
vigila el marcador en `site/` y que ningún JS vuelva a redactarlo. Las once mutaciones
—las dos fechas salidas del mismo campo, la cadena vacía, la fecha inventada, la
abreviatura cruzando de mes, la primera búsqueda en vez de la última, el generador
desconectado, el marcador con un carácter de menos, el marcador partido, el JS
reinstalado— caen todas (M1). Palabras servidas: index 3.475 → 3.481 · municipios
3.768 → 3.774 · rud 2.819 → 2.832 · balances 2.096 → 2.110 · noticias sin sello, 6.493.

## 2026-08-23 — `inyectar_prerenderizado` deja de callarse: `continue` → `raise`

Contexto: si un contenedor `data-gen` declarado no casaba con la expresión, el inyector
hacía `continue`. **Basta un salto de línea entre la apertura y el cierre** para que no
case. Consecuencia medida rompiéndolo a propósito: el build termina en verde, el informe
imprime **una línea menos** —que nadie echa de menos entre once— y la avería sale mucho
después, desde `seo_check`, en otro proceso y **con otro nombre** (el del atributo mal
escrito, no el del generador declarado). Es un error de programación, no una fuente que
falla: la degradación elegante de R13 no aplica.

Decisión: rompe el build, con los **dos mensajes distinguidos** que ya usaba
`escribir_piezas_compartidas` — marcador perdido frente a marcador ya gastado.

Y una corrección que solo apareció al validar por mutación (M1): **mirar si el contenedor
está presente no separa las dos averías**. En el fallo más probable —el salto de línea—
el contenedor está y sigue vacío, y el mensaje acusaba al artefacto, mandando a
reconstruir `dist/` cuando lo que hay que mirar es `site/`. Lo que las separa es **si
dentro hay algo escrito**, no si el contenedor existe.

Consecuencia: `TestElInyectorNoSeCalla`, con las tres averías y el caso que **no** es
avería — un `dist/` parcial, como el que arma `TestBandaDeBrechas` con solo la portada:
una página que no está se sigue saltando. Lo que rompe es el contenedor que falta en una
página que sí está.

## 2026-08-23 — Las cifras del RUD y su gráfico pasan al build

Contexto: `rud.html` servía un `<div>` vacío donde el navegador dibujaba el gráfico, una
tira de chips vacía, y ninguna cifra en prosa. Quien no ejecuta JavaScript —todo
rastreador de sistemas de IA— leía la tabla y nada más. Dentro de aquel gráfico vivía un
`<desc>` de 77 palabras que narra la serie día a día, la única prosa del sitio que crece
sola con el dato, **y no la leía nadie**.

Decisión: cuatro generadores nuevos por el mecanismo `data-gen` (`rud-resumen`,
`rud-grafico`, `rud-chips`, `rud-nota`), y ninguna etiqueta de sitio cambia de sitio —el
reorden de la página es un paso aparte—.

- **La entradilla publica el hallazgo que no estaba en ninguna parte.** De las 19.334
  familias del último salto, **16.155 son revisión al alza de municipios ya registrados y
  solo 3.179 vienen de los 49 nuevos**: el RUD no crece por la cola, crecen los ya
  contados. Se calcula recorriendo `detalle_diario` con la clave `(departamento,
  municipio)` —nunca por nombre normalizado, que es el error de 206 familias de
  «Guadalajara de Buga» (R10, M8)— y el total se rotula **«mínimo provisional»** (R16).
  El desglose **no se publica si no suma su propio salto** (M7) ni si le falta una de sus
  dos mitades: la oración termina afirmando que lo que crece son los municipios ya
  contados, y con el salto entero en municipios nuevos esa conclusión sería falsa (M10).
- **Los predicados de los chips salen a `CHIPS_RUD` + `_chips_de(m)`, compartidos con
  `filas_rud`.** Vivían partidos —el array `CHIPS` de `rud.js` contaba filas, `filas_rud`
  las etiquetaba con su propia copia—, así que nada impedía que «Nuevos (49)» filtrase
  otra cosa (M2). La definición **desaparece de `rud.js`**: dejar las dos era M2 el día uno.
- **La nota del pie se parte por lo que es invariante, no por lo que es cómodo.** La
  prosa —qué compara la columna Δ, cuándo empezó la serie, que un cero puede ser
  «todavía sin evaluar»— la escribe el build; **el recuento vivo se queda en el
  navegador**, que es el único que sabe qué hay filtrado. Cero literales duplicados.
- **El gráfico se porta a Python** con el precedente de `mapa_svg()`. Las dos
  dependencias del navegador mejoran al portarse: `ui.cssVar()` resolvía la variable a un
  color literal y **congelaba el tema claro dentro del SVG**, y ahora se emite
  `var(--…)`, así que el gráfico sigue el tema oscuro; `clientWidth` pasa a 900 fijo
  porque el `viewBox` ya lo hace fluido. **Los colores no se tocan**: `--s8` significa hoy
  dos cosas —SERTIT y RUD— y unificar la clave de color va en su propia fase; lo que
  cambia es que a partir de ahora esa ambigüedad queda escrita en el artefacto.
- **El contador de balances deja de fechar el dato.** `#balance-resumen` decía «30 de 30
  capturas · actualizado el 22 de agosto de 2026» desde `generated_at` —la corrida, no el
  corte del rastreo—: la misma confusión que el sello acababa de separar tres centímetros
  más arriba, en la misma página. La fecha vive en el sello y solo ahí (M2).

Consecuencia: los tres tests de `TestGraficoRud` **se portan a Python sin perder una
aserción** —incluido el de la corrección a la baja (`data-altas="-10"`, `--critical`),
que distingue «bajó» de «no hay dato»— y de paso dejan de estar bajo `@skipUnless(NODE)`.
Se suman `TestChipsDelRud`, `TestEntradillaRud`, `TestNotaRud`,
`TestPiezasDelRudLleganEscritas` y `TestEspejoDeDiaMes` (`dia_mes` es el cuarto helper de
formato que vive en dos lenguajes). 555 → 588 tests. Las catorce mutaciones caen (M1);
**una decimoquinta sobrevivió y su test se tiró y se rehizo**: el desglose que no cuadra
se rechazaba antes por el otro guardián, así que el de la aritmética estaba sin vigilar.
`rud.html` pasa de **0 a 1 `<svg>`** servido y de 2.832 a **3.210 palabras**; las otras
cuatro páginas, sin mover una.

Laguna medida y no corregida aquí: a 375 px los rótulos del gráfico caen de un efectivo
**4,57 px a 3,46 px** al fijar el lienzo en 900. Los dos son ilegibles y el problema es
anterior, pero **el porte lo empeora un 24 %**. La solución conocida está al lado —las
media queries de `.mapa-estatico`, que hacen CRECER la letra en pantalla estrecha— y es
un cambio visible: va con el reorden de la página, no colado aquí.

## 2026-08-23 — `rud.html` se reordena: el dato arriba, la metodología plegada

Contexto: la página abría con cuatro párrafos de introducción —268 palabras— entre la
entradilla y el primer gráfico. Medido a 375 × 812, había que bajar **más de una pantalla
entera** antes de ver una cifra, y la página entera medía **4,71 pantallas**. Es la
primera de las cinco que se reordena y **la única parte de la fase que se ve**.

Decisión: **mover, no reescribir.** Los cuatro párrafos se reparten literales entre dos
plegables, con el reparto que dio JP:

- Arriba, entre la entradilla y la tabla, `<details class="pliegue">` **«Cómo leer estas
  cifras»** con los dos párrafos que enseñan a leerla (80 + 43 = **123 palabras**). Van
  antes de la tabla porque es lo que explican.
- Al final, `<details class="pliegue denso">` **«Qué es el RUD y qué no es»** con los dos
  que definen la fuente (46 + 99 = **145**). 123 + 145 = **268**: ni una palabra menos.
- En medio, una `<div class="zona-datos">` con el gráfico y la tabla, que suben.

Tres decisiones de forma, con su porqué:

- **El `<h2>` y el `<p class="sub">` del gráfico se quedan en el HTML**, no pasan al
  generador: es lo que deja pasar sin relajarlo a
  `TestTablaRud::test_el_grafico_explica_las_dos_series_y_la_primera_captura`.
- **Una línea de CSS nueva**, `details.pliegue > .intro { margin-left: 0; margin-right: 0 }`:
  una `.intro` dentro del plegable recibiría **dos ejes**, el suyo y el del contenedor.
  Es el mismo fallo ya corregido en `.zona-datos > .contenido`, y ahora tiene test.
- **El plegable es el componente, no el `<details>` desnudo del navegador**: los dos
  llevan `class="pliegue"`, que es para lo que se declaró en el lote 3.

Se cierra además la laguna que dejó abierta la entrada anterior: **la legibilidad del SVG
a 375 px**. Se aplica el patrón de `.mapa-estatico` —la letra CRECE en pantalla estrecha,
porque el texto vive dentro del `viewBox` y encoge con él— con clases por tipo de rótulo
(`g-eje`, `g-alta`, `g-dia`, `g-total`, `g-vacio`, `g-leyenda`) y el `font-size` del SVG
como base, de modo que **el gráfico de escritorio no cambia un píxel**. Los rótulos de
dato pasan de **3,46 a 8,3-9,0 px efectivos**. Tres topes son geométricos, no estéticos, y
por eso llevan test en vez de comentario:

1. El rótulo del eje se escribe **hacia la izquierda** dentro de las 58 unidades del
   margen: por encima de 15 px el SVG lo recorta (5,2 px efectivos, el único que no se
   arregla sin cambiar la geometría).
2. Los rótulos de los puntos no pueden ser más anchos que la separación entre puntos.
   Hoy sobra —87 unidades de 153— pero **la serie crece cada día**, así que el margen se
   estrecha solo y el test avisa (R11) antes de que se pisen.
3. La segunda entrada de la leyenda **se aparta a la derecha** con un `transform` en la
   propia @media; sin eso, las dos entradas se solapan en cuanto la letra crece.

Son **dos bandas de @media y no una** —760 y 480—, porque el SVG no encoge de golpe:
entre 481 y 760 px se dibuja sobre 400-680 y el salto de la banda estrecha lo dejaría
más grande que en escritorio. Medido en las dos: 6,0-7,0 px efectivos a 481 px (el punto
más flojo, justo por encima del corte), 11,1-12,0 a 480 y 9,9-11,4 a 760. El test
reconstruye la cascada de las dos bandas: mirar solo la de 480 dejaba la tableta sin
vigilar, y ahí sí había rótulos superpuestos.

Y una renuncia medida: el **«sin base»** del primer día se queda pequeño. Cuatro rótulos
se disputan la esquina de abajo a la izquierda —con `piso` en 0, la línea del cero y el
pie del lienzo distan 16 unidades— y es el único de los cuatro que el `<p class="sub">`
de encima ya explica con todas sus letras.

Consecuencia: `rud.html` baja de **4,71 a 3,78 pantallas** a 375 px y el primer dato pasa
de estar a más de una pantalla a estar **a 310 px**; el gráfico entero cabe en la primera
pantalla (809 px de 812). **No llega a las 2,9 pantallas que preveía el plan, y no puede
llegar moviendo prosa**: cerrados los dos plegables, lo que queda son 90 px de barra, 206
de encabezado, 289 de entradilla, 1.658 de datos y **691 de pie** — el pie solo son 0,85
pantallas. Bajar de ahí es paginar la tabla de otra manera o adelgazar el pie, y las dos
cosas son otra decisión. `seo_check` da **+12 palabras exactas** en `rud.html` (3.210 →
3.222) y **cero** en las otras cuatro: las 12 son los dos `<summary>` nuevos, lo único
que se escribe en todo el paso. 588 → **597 tests**; **doce mutaciones caen** (M1) —
quitar un párrafo del plegable, romper la línea del doble eje, anidar un plegable en otro,
retirar cada @media, cada `transform` y cada clase del SVG—. **Una decimotercera
sobrevive y se deja escrito por qué**: subir `.g-total` a 26 px en la banda de 760 no
rompe ningún test porque no se sale ni se pisa con nada. Los guardianes son de
**geometría, no de gusto**; que quede claro es mejor que un test que finge cubrirlo.

## 2026-08-23 — La búsqueda de prensa se deriva del catálogo y crece sola

Contexto: `municipal_google_news_feeds()` recorría `MUNICIPIOS`, el catálogo
curado a mano. Pero el catálogo que el monitor observa es
`{**MUNICIPIOS, **municipios_dinamicos(rud, divipola)}` — los que abre el propio
registro oficial según crece. Medido el 22-ago-2026 sobre `municipios.json`: de
**207** municipios con damnificados inscritos, **81** tenían búsqueda propia; de
los **119** sin un solo titular, solo **10** la tenían. **El monitor publicaba
que 119 municipios no tienen ni un titular y en 109 de ellos nunca llegó a
preguntar.** Una celda vacía por «no hemos buscado» y otra por «no hay nada» se
veían exactamente igual — justo el tipo de afirmación que este proyecto existe
para no hacer.

Decisión: la lista **se deriva del catálogo completo en cada corrida y no se
mantiene a mano en ningún sitio**. `catalogo_municipios()` es la definición
única —de ella cuelgan la ficha municipal y la búsqueda de prensa, que tienen
que decir lo mismo (M2)— y `catalogo_vigente()` la deriva del archivo (último
día del RUD + DIVIPOLA) para quien no tiene el registro a mano. Un municipio que
el RUD estrene hoy tiene su búsqueda hoy, sin que nadie toque un fichero. De
**82 a 203** búsquedas.

Los dos cuidados que ya vivían en el docstring se convierten en código con
nombre, `motivo_sin_busqueda()`, porque ahora los topónimos no los escribe una
persona: llegan del registro oficial tal como el registro los escriba.

1. **La frase buscada es el topónimo, no la clave**: `"riosucio (caldas)"` no
   aparece en ningún titular — un feed que devuelve cero para siempre y nadie
   sabe por qué. Se añade el caso hermano que solo puede llegar por la vía
   dinámica: un nombre de catálogo administrativo («sotará - paispamba»).
2. **Los homónimos de departamento no generan feed**, ni curados ni dinámicos:
   `"bolivar" "cauca"` casa con los titulares del departamento y, como el feed
   declara su municipio, colaría por la puerta de atrás la atribución que
   `_menciona_municipio` rechaza (publish.py cree lo que el feed declara).

Cuando no se puede construir una consulta segura **no se construye ninguna y se
dice cuántos son** (M10): el resumen de la corrida lleva
`_busquedas_municipales` con el recuento y el motivo de cada exclusión. Hoy son
**cinco**, los cinco homónimos de departamento: Bolívar (Valle del Cauca),
Bolívar (Cauca), Córdoba (Quindío), Risaralda (Caldas) y Sucre (Cauca).

Coste medido, que es real: ~121 peticiones HTTP más por corrida, cada una con su
snapshot y su fila en `sources_log` (R4). Al ritmo observado en `sources_log`
—0,35-0,74 s por petición en las cinco últimas tandas— la tanda pasa de ~45 s
a **~2 min**; los snapshots de estas búsquedas pasan de 7,3 MB a **entre 12 y
18 MB al día** (el feed más pequeño de hoy pesa 6,6 KB y la mediana 83 KB),
sobre los 19 MB diarios que ya se archivan, y **se versionan en git**. Nunca se
ha registrado un 429 de Google News, pero la primera tanda (15-ago, 50
peticiones) fue a 11,4 s por petición: a ese ritmo, 203 peticiones son 38 min y
el `timeout-minutes: 45` de `daily.yml` queda al borde. No se pone un límite
arbitrario: se deja el dato escrito y, si aparece, R13 ya degrada feed a feed
sin romper la corrida.

Hallazgo del camino, que no se buscaba: **el orden de las filas del RUD decide
los nombres del catálogo**. `municipios_dinamicos` reparte el nombre a secas al
primero de dos homónimos y el paréntesis al segundo, así que «Argelia» es la del
Valle del Cauca (851 familias) y «Argelia (Cauca)» la del Cauca (1 familia)
**porque `publish.py` lee las filas por familias descendentes**. La primera
versión de `catalogo_vigente()` las leía sin ordenar y salían al revés: los
identificadores de los feeds municipales habrían dejado de casar con los
titulares ya archivados y con las URL de las fichas. Se deja el mismo `ORDER BY`
—escrito y explicado— y un test que compara las dos derivaciones. Queda apuntado
lo que no se toca aquí: la identidad de una ficha municipal depende hoy de una
cifra que cambia todos los días, y si mañana el Cauca adelanta al Valle, la URL
`/municipio/argelia/` pasaría a ser otro municipio. Eso es otra decisión.

Guardián (R11): `tests/test_hipotesis.py::TestSupuestoBusquedaMunicipal` compara
los municipios del catálogo con los que tienen búsqueda y **falla en cuanto
aparece uno sin cubrir que no esté en la lista de excepciones escrita a mano** —
y también si sobra una excepción. Que se rompa es la señal de que hay trabajo,
no de que algo va mal. Siete mutaciones caen (M1): volver a recorrer solo el
catálogo curado, quitar cada uno de los tres guardianes de consulta segura,
buscar la clave en vez del topónimo, devolver el catálogo sin copiar y leer las
filas del RUD sin ordenar.

**El dato publicado no cambia hasta que pase una corrida real**: `busqueda_propia`
seguirá diciendo lo de hoy hasta que el flujo diario vuelva a ejecutarse. Los tres
niveles del banner de silencio (`site/ui.js::silencioDePrensa`) no se tocan aquí:
cuando la corrida limpia pase, el segundo nivel se quedará casi vacío por sí solo
y ese texto es otra decisión.
