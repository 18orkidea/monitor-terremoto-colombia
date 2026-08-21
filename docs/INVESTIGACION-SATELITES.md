# Quién miró Colombia desde el aire — inventario satelital del terremoto del 10-ago-2026

**Investigación cerrada el 20 de agosto de 2026.** Toda afirmación de este documento se
comprobó ese día contra la fuente que se cita; donde la comprobación es una consulta a una
API, se deja la consulta para que cualquiera la repita. Es un documento de investigación:
no cambia código ni cifras publicadas.

**Pregunta de partida**: ¿qué satélites miraron el terremoto, quién publicó qué a partir de
ellos, y qué de todo eso puede entrar en el monitor sin romper sus reglas?

---

## 1. Lo que hay que saber en un minuto

- **Al menos 495 escenas satelitales** de doce misiones distintas se adquirieron para este
  terremoto a través de la Charter Internacional (activación **1048**, solicitada por la
  **UNGRD**). El monitor no las tiene ni puede tenerlas: son datos para el respondiente,
  no públicos.
- Lo que **sí es público** son los productos derivados. Hay **15 descargables sin
  autenticación** en el servidor de la Charter, de cuatro equipos distintos: Copernicus EMS,
  UNITAR-UNOSAT, el **INGV** italiano y el **SERTIT** francés, más un análisis de
  **UN-SPIDER**. El monitor solo ingiere hoy los dos primeros.
- **Dos municipios con conteo de daño satelital no están en el monitor**: **Roldanillo**
  (Valle del Cauca, 77 edificios) y **La Virginia** (Risaralda, 49 edificios), ambos
  cartografiados por el SERTIT con Pléiades el 12 y 13 de agosto.
- **Tres «mapas proxy de daño» del INGV** (Cali, Pereira, Buenaventura) hechos con
  Sentinel-1 son una **tercera mirada satelital independiente**, de método distinto (radar,
  no fotointerpretación) sobre municipios que el monitor ya cubre. Sirven para contrastar.
- **Copernicus prometió públicamente un producto de movimiento del terreno y luego lo
  declaró no producible.** La noticia pública sigue anunciándolo; el backend dice, desde el
  17-ago, `"Because of remote sensing limitations"`. Esto lo tenemos archivado nosotros.
- **NASA e ISRO sí tasquearon NISAR** en modo respuesta urgente sobre el occidente
  colombiano (11 y 13 de agosto) y hay **un interferograma que abarca el sismo**, público y
  descargable sin cuenta. Es el dato satelital abierto más potente que nadie ha explotado.
- **Maxar, Umbra y Capella no abrieron datos para este terremoto**, aunque los abrieron para
  otros desastres recientes —incluido el terremoto de Venezuela de junio de 2026—.
  Verificado en sus catálogos, no en sus notas de prensa.
- **La cadena oficial colombiana declara 166 imágenes procesadas y sobrevuelos en
  85 municipios. Nada de eso está publicado.** Es la mayor brecha satelital del caso.

---

## 2. Lo que el monitor ya tiene

| Fuente | Qué aporta | Estado |
|---|---|---|
| Copernicus EMS `EMSR916` | 7 AOI con vectores de daño y estadísticas | Ingerido, activación **cerrada** |
| UNITAR-UNOSAT | 548 edificios en Anserma, Manizales, Viterbo y Zarzal | Ingerido |
| VIIRS (luces nocturnas) | Corte de energía por píxel | Ingerido |

Estadísticas de Copernicus tal como las devuelve su backend (snapshot del 19-ago-2026):

| AOI | Municipio | Edificios afectados | Población estimada | Imagen post-evento |
|---|---|---|---|---|
| 01 | Cali norte | 7 (de 11.788 residenciales) | 340.000 | Pléiades, 11-ago 15:31 |
| 02 | Pereira | 182 + 11 vías bloqueadas | 190.000 | Pléiades, 11-ago 15:31 |
| 03 | Cali centro | 14 | 94.000 | Pléiades, 11-ago 15:31 |
| 04 | Quibdó centro | 74 (de 8.817) | 73.000 | SkySat + Pléiades Neo, 13-ago |
| 05 | Istmina | 10 (de 4.883) | 23.000 | Pléiades Neo, 13-ago 15:41 |
| 06 | Buenaventura | 335 (322 viviendas + 11 otros + 2 escuelas) | 320.000 | Pléiades Neo, 13-ago (monitoreo) |
| 00 | Occidente de Colombia | **producto no entregado** | — | Sentinel-1, 14-ago 10:48 |

La activación declara 622 edificios identificados en total. Los mapas de Copernicus
advierten en su propia leyenda que el análisis «se complementó con redes sociales» —dato
relevante para un monitor que también verifica material ciudadano—.

**El desglose por grado de daño solo está dentro de los PDF**, no en el backend que
ingerimos, que publica un único total de «afectados». Extraído de las tablas de los mapas:

| AOI | Destruidos | Dañados | Posiblemente dañados | Total |
|---|---|---|---|---|
| 01 Cali norte | 2 | 3 | 2 | 7 |
| 03 Cali centro | 8 | 3 | 3 | 14 |
| 06 Buenaventura (versión inicial, viviendas) | 109 | 113 | 24 | 246 |
| 02 Pereira | 76 | 85 | … | 182 |

Importa porque un «afectado» de Cali centro y uno de Buenaventura no son lo mismo: en
Buenaventura hay 109 edificios destruidos, casi la mitad de todo lo que Copernicus vio
destruido en el país. Recuperarlo exigiría leer los PDF, no la API.

---

## 3. El producto que Copernicus prometió y no entregó

La noticia pública de Copernicus EMS sobre `EMSR916` dice que, además de los siete productos
de daño, «se entregará en los próximos días un producto de evaluación de movimiento del
terreno». En nuestros snapshots del backend se ve el ciclo completo:

| Snapshot | Estado del producto GRM (AOI00) | Entrega prevista |
|---|---|---|
| 15-ago | `statusCode: W` (esperando) | 16-ago 13:48 |
| 16-ago | `statusCode: W` | 16-ago 13:48 |
| 18-ago | `statusCode: N`, motivo: `"Because of remote sensing limitations"` | anulada |
| 19-ago | igual | anulada |

Esto no lo ha contado nadie: la búsqueda web del 20-ago no devuelve ninguna pieza que lo
recoja, y la noticia oficial sigue anunciando el producto. **La distancia entre lo prometido
y lo entregado es exactamente el objeto de este monitor.**

Y hay una explicación física, no una desidia: el sismo fue a **110 km de profundidad**. Un
terremoto tan profundo deforma la superficie de forma suave y extensa, muy difícil de aislar
de la señal atmosférica; encima, la banda C de Sentinel-1 pierde coherencia sobre selva
húmeda en cuestión de días. Lo comprobamos mirando el interferograma NISAR (§6): sobre el
Pacífico solo hay ruido, y sobre tierra la fase está dominada por estructuras amplias que
exigen corrección troposférica antes de poder decir nada.

---

## 4. Los satélites que sí miraron: la activación 1048 de la Charter

La **UNGRD activó la Charter Internacional** el 10-ago a las 17:08. Es la activación
**nº 1048**, y su *call* de valor añadido es la **1202**. El equipo declarado incluye a la
propia UNGRD (Jorge Armando Alpala como gestor), el **SGC** (Carlos Laverde, Luis Antonio
Barrera), la **ABAE venezolana**, el **SERTIT**, **UNITAR**, **UN-SPIDER** (Alexander Ariza)
y el **INGV** (Christian Bignami).

El visor de la Charter enumera las escenas adquiridas. Agrupadas por misión:

| Misión / operador | Escenas | Fechas | Tipo |
|---|---|---|---|
| CBERS-4 (INPE/China) | 145 | 15-ago | óptico medio |
| Landsat 8 y 9 (USGS) | 132 | 15-jul → 19-ago | óptico medio |
| Planet (identificadores PT01) | 117 | 24-jul → 13-ago | óptico alta res. |
| Pléiades 1A / 1B (CNES–Airbus) | 41 | 12 → 19-ago | óptico muy alta res. |
| RADARSAT Constellation (CSA) | 13 | 12 → 14-ago | **radar** |
| Pléiades Neo 3 y 4 | 12 | agosto | óptico muy alta res. |
| IRS (ISRO) | 8 | agosto | óptico |
| BlackSky | 8 | 10 → 13-ago | óptico alta res. |
| Gaofen-3 (CNSA) | 7 | 17-ago | **radar** |
| AMAZONIA-1 (INPE) | 5 | agosto | óptico medio |
| DLR (TerraSAR-X/TanDEM-X, id. C637) | 4 | 12-ago | **radar** |
| KOMPSAT-3 (KARI) | 3 | **9-ago** | óptico (pre-evento) |

Dos detalles que valen por sí solos: **KOMPSAT-3 tomó imágenes el día antes del terremoto**
—material de referencia que ninguna comparación «antes/después» pública ha usado— y
**cuatro operadores aportaron radar**, que es lo único que atraviesa la nube del Chocó.

Estas escenas **no son accesibles** para el monitor: la Charter las entrega a los
respondientes autorizados. Lo que sí es accesible son los productos derivados.

---

## 5. El catálogo de productos de daño (lo directamente aprovechable)

Los 15 archivos publicados en la Charter se descargan **sin autenticación** desde
`https://disasterscharter.org/cos-api/api/file/public/37686205/vap-1202-<n>-product.<pdf|jpg>`
(comprobado uno a uno el 20-ago: HTTP 200, entre 1,6 y 12 MB). Identificados:

| Producto | Autor | Cobertura | Cifra publicada | Imagen base | ¿En el monitor? |
|---|---|---|---|---|---|
| Grading AOI01/02/03/06 | Copernicus EMS (e-GEOS, CLS, Telespazio) | Cali ×2, Pereira, Buenaventura | ver §2 | Pléiades / Pléiades Neo | **Sí** (vectores) |
| Damage assessment Viterbo (1:20.000) | UNOSAT | Viterbo (Caldas), ~28 km² | 55 dañados + 99 posibles | Pléiades 12-ago 50 cm; previa WorldView-3 29-dic-2025 | **Sí** |
| Damage assessment Viterbo (1:7.000) | UNOSAT | Viterbo casco, ~2 km² | 42 dañados + 66 posibles | ídem | **Sí** |
| Damage assessment San José del Palmar | UNOSAT | **el epicentro** | «daño estructural observado»; evaluación completa | WorldView-2 del **11-ago-2026**, comparado con WorldView-2 del **16-feb-2017** | Solo el texto: **sin vectores** |
| **Impact map Roldanillo** | **ICube-SERTIT** | **Roldanillo (Valle)** | **77 edificios** | Pléiades-HR 13-ago 15:15, 0,5 m | **No** |
| **Impact map La Virginia** | **ICube-SERTIT** | **La Virginia (Risaralda)** | **49 edificios** | Pléiades-HR 12-ago 15:22, 0,5 m | **No** |
| Impact map Pereira | ICube-SERTIT | Pereira | — | Pléiades Neo | **No** (Copernicus ya la cubre) |
| **Damage proxy map Cali** | **INGV** | Cali | puntos «probablemente destruidos o muy dañados» | **Sentinel-1** asc. 48: pre 26-jul y 7-ago, post 13-ago | **No** |
| **Damage proxy map Pereira** | **INGV** | Pereira | ídem | **Sentinel-1** desc. 142: pre 2 y 8-ago, post 14-ago | **No** |
| **Damage proxy map Buenaventura** | **INGV** | Buenaventura | ídem | **Sentinel-1** | **No** |
| **Derrumbes vía Buga–Loboguerrero–Buenaventura** | **UN-SPIDER (UNOOSA)** | corredor vial | zonas de derrumbe delimitadas | **Sentinel-2** L2A 10-ago, 10 m | **No** |

Notas de rigor sobre esta tabla:

- Los mapas del INGV llevan escrito **«no se ha realizado ninguna validación»** y se generan
  «por procedimientos semiautomáticos, mejor esfuerzo». Su propio crédito remite al
  procesado bajo demanda de la **Alaska Satellite Facility**. Son una hipótesis de daño, no
  un conteo: entrarían al monitor con el mismo cuidado con que hoy se trata el «daño
  posible» de UNOSAT.
- Los mapas del SERTIT declaran «impacto potencial» y distinguen destruido / dañado /
  posiblemente dañado, igual que Copernicus.
- Los cuatro equipos usan **imágenes distintas y métodos distintos sobre los mismos
  municipios**. Que sus cifras no coincidan no es un error: es medible, y es justo lo que
  este proyecto existe para medir.
- **Todos estos productos son PDF o JPG.** Ninguno publica vectores. Un conteo por municipio
  es transcribible con atribución; una geometría, no.

**Lo más accionable**: Roldanillo y La Virginia son dos municipios con cifra de daño vista
desde el aire que hoy el monitor no puede mostrar como verificados por satélite.

Un apunte sobre el epicentro que merece contarse: la única evaluación de San José del Palmar
compara la imagen del 11-ago-2026 con **una de febrero de 2017**. Nueve años y medio de
diferencia. En los demás municipios la referencia previa es de meses (Viterbo, diciembre de
2025) o de días (Pereira y Buenaventura, julio de 2026). Al lugar donde ocurrió el sismo se
le mira con la fotografía más vieja del expediente — y eso, además de explicar por qué de
ahí no salen vectores, es en sí un dato sobre a quién se mira con cuánto cuidado.

---

## 6. NISAR: la mirada que nadie ha usado

NISAR (NASA–ISRO, radar de banda L) empezó a publicar datos en abierto el 20-jul-2026.
Comprobaciones del 20-ago sobre el catálogo público de la NASA (CMR) para la caja
−77,5/2,0 → −75,0/5,6:

- **Adquisiciones en modo respuesta urgente (`NISAR_UR_*`) el 11 y el 13 de agosto**:
  productos RSLC, GSLC y GCOV. NASA e ISRO **tasquearon el satélite para este terremoto**.
- **Tres interferogramas `GUNW` cuyo par abarca el sismo**: referencia 18-jul-2026,
  secundaria **11-ago-2026**, órbita ascendente 148. Uno de ellos cubre el epicentro,
  Quibdó y Buenaventura en la misma escena.
- **Se descargan sin cuenta**: la vista rápida en PNG del interferograma bajó en la
  comprobación (3,1 MB, 1401×1376 px, HTTP 200 siguiendo la redirección firmada). El HDF5
  completo son 23 MB por la misma vía.

Lectura honesta de esa imagen: el Pacífico aparece como ruido puro —era de esperar sobre
agua— y la parte terrestre muestra estructuras amplias que **no permiten afirmar que sean
deformación cosísmica** sin corrección troposférica. Es material de investigación, no una
cifra publicable. Pero su existencia sí es publicable, y contrasta con el producto que
Copernicus canceló.

Falta lo que aún no existe: **ningún interferograma NISAR con las dos imágenes posteriores
al sismo**, que es lo que mediría el desplazamiento limpio. A 20-ago no está publicado.

---

## 7. Lo que no pasó (y en otros desastres sí pasa)

Comprobado en los catálogos, no en notas de prensa:

| Programa | Comprobación | Resultado |
|---|---|---|
| **Maxar Open Data** | catálogo STAC en AWS, 55 eventos | **Ningún evento de Colombia 2026.** Sí hay Myanmar 2025, Turquía 2023, Marruecos 2023… |
| **Umbra Open Data** | 81 tareas en su bucket | Ninguna del terremoto. Sí existe `Venezuela_Earthquake_Support` (junio 2026) |
| **Capella Open Data** | su bucket llega hasta junio de 2026 | Nada de agosto |
| **Planet Disaster Data** | publica en Source Cooperative | Hay publicación abierta para el terremoto de Venezuela del 24-jun-2026; **no se ha localizado ninguna para Colombia** |
| **Copernicus Risk & Recovery Mapping** | buscador de activaciones | **Ninguna activación para Colombia.** El mapeo de la *recuperación* —el que mediría la reconstrucción— no se ha pedido |

Los tres operadores comerciales sí aportaron imágenes **a través de la Charter** (Planet y
BlackSky están en la lista del §4). La diferencia es de licencia: entraron al circuito
cerrado del respondiente, no al dominio público. Para el terremoto de Venezuela de junio,
dos de ellos abrieron datos. Para este, no. **La comparación entre ambos eventos es una
pieza periodística en sí misma**, y conviene volver a comprobarlo dentro de unas semanas:
estos catálogos se llenan tarde.

---

## 8. Lo que Colombia declara y no publica

La cadena oficial está documentada por la propia UNGRD (14-ago) y replicada por Semana, El
Nuevo Siglo, Infobae y Radio Santa Fe:

- **166 imágenes satelitales de alta definición procesadas.**
- Participan **IGAC**, **Fuerza Aeroespacial Colombiana**, **PNUD**, **Indra**, el sistema
  **DRCS de la NASA** y la Charter, bajo la «Mesa Geomática» de la UNGRD.
- **Airbus entregó imágenes de ultra detalle** de Cali, Cartago, Manizales y Pereira.
- Se priorizó **fotografía aérea tripulada y no tripulada en 85 municipios**; a 14-ago
  había **13 municipios sobrevolados** en Valle del Cauca, Chocó, Risaralda, Caldas y
  Quindío.
- **Indra** analiza imágenes de satélite **con inteligencia artificial** desde Colombia y
  España, y desplegó cuatro pilotos de dron en el Valle del Cauca.

Ninguno de esos productos se ha publicado. La comprobación del 20-ago sobre los 904
servicios geográficos publicados por el IGAC en su organización ArcGIS no devuelve **ni una
sola capa** del terremoto: son catastrales. Cartago, cubierta por Airbus según la UNGRD, no
aparece en ningún producto público de daño.

Es la brecha satelital central del caso: **el país tiene 166 imágenes procesadas y 85
municipios fotografiados desde el aire, y el ciudadano ve seis áreas de Copernicus y tres
pueblos de UNOSAT.**

---

## 9. Por qué el Chocó no se puede vigilar con óptico (medido)

El monitor ya sabía esto por las luces nocturnas (2 noches útiles de 109). El catálogo de
Copernicus lo confirma por otra vía. Todas las pasadas de Sentinel-2 sobre el epicentro
desde el 1 de julio:

| Fecha | Nubosidad |
|---|---|
| 18-ago | 26,7 % |
| 13-ago | 44,3 % |
| **10-ago (día del sismo)** | **59,2 %** |
| 8-ago | 76,0 % |
| 3-ago | 99,4 % |
| 31-jul | 95,1 % |
| 24-jul | 36,3 % |
| … | … |

**Mediana: 76 % de nube. Trece pasadas, ninguna por debajo del 20 %.** Por eso los cuatro
operadores de radar del §4 importan, por eso Copernicus tuvo que ir a por Pléiades en
ventanas concretas, y por eso el epicentro solo tiene un PDF.

Del lado abierto y libre sí hay material sobre el AOI en las fechas críticas: **68 productos
Sentinel-1** (S1C y S1D, con pares utilizables el 8 y el 13-14 de agosto) y **6 escenas
Landsat**, una de ellas con solo 14 % de nube el 13-ago.

---

## 10. Factibilidad para el monitor, fuente por fuente

Criterios del proyecto: R4 (todo pasa por `fetch()` con snapshot y sha256), R14 (solo
stdlib), plan de sucesión, y que la fuente diga algo que las demás no dicen.

| Fuente | Qué añade | Acceso | Formato | Dificultad | Recomendación |
|---|---|---|---|---|---|
| **Productos SERTIT (Roldanillo, La Virginia)** | **dos municipios nuevos con cifra de daño** | HTTP público, sin clave | PDF | Baja para el PDF y el conteo; los vectores no existen | **Hacerlo ya** |
| **Índice de la activación Charter 1048** | quién adquirió qué y cuándo; los 15 productos | HTML público (Next.js, «cargar más» pagina) | HTML → parseo | Media: el HTML es frágil, conviene snapshot íntegro | **Hacerlo**: es el «quién miró» que hoy falta |
| **Mapas proxy INGV** | tercera mirada, método radar independiente | HTTP público | PDF | Baja para archivar; alta para extraer puntos | **Archivar y citar**, no convertir en cifra |
| **UN-SPIDER (derrumbes)** | deslizamientos en el corredor a Buenaventura | HTTP público | JPG | Baja | Archivar; es otra capa de daño (vías) |
| **NISAR (ASF/CMR)** | interferometría banda L abierta; prueba de que NASA tasqueó | API CMR pública + descarga sin cuenta | JSON + PNG/HDF5 | Baja para metadatos y PNG; muy alta para procesar | **Metadatos sí**; el procesado, no (exige librerías que R14 prohíbe) |
| **Catálogo Sentinel-1/2 (Copernicus Data Space)** | medir cuántas veces se pudo mirar y con cuánta nube | OData público sin clave para consultar | JSON | Baja | **Muy recomendable**: convierte «no se ve» en una cifra |
| **Landsat (STAC USGS)** | óptico libre con nubosidad por escena | STAC público | JSON | Baja | Opcional, complementa lo anterior |
| **Maxar / Umbra / Capella / Planet abiertos** | hoy, la ausencia | catálogos públicos | JSON/XML | Baja | **Sonda de ausencia**: comprobar cada día y avisar si aparecen (R11) |
| Escenas de la Charter | — | restringido | — | — | Inaccesible por diseño; documentarlo |
| IGAC / FAC / Indra | 166 imágenes y 85 municipios | **no publicado** | — | — | **Pedirlo y registrar el silencio** (R15) |

Advertencias antes de tocar nada:

1. **Ningún producto nuevo trae geometría.** Un conteo de PDF no es un vector: si entra,
   entra como cifra atribuida a su autor, nunca como capa de puntos ni como algo que pueda
   ascender a «coincide» (R1, R2).
2. **Sumar miradas distintas exige comprobar que no se pisan.** Copernicus, UNOSAT y SERTIT
   miran municipios distintos, pero el INGV mira **los mismos** que Copernicus (Cali,
   Pereira, Buenaventura): ahí no se suma, se contrasta.
3. **Los mapas del INGV y del SERTIT no están validados en campo**, y el INGV lo dice en el
   propio mapa. Mismo tratamiento que el «daño posible» de UNOSAT.
4. **La página de la Charter pagina con «cargar más»**: de los 15 productos, el HTML inicial
   solo trae 8. El resto se alcanza por los archivos numerados; la numeración tiene huecos
   (falta el 1, el 4, el 10, el 17), así que el descubrimiento no puede asumir una serie
   continua.

---

## 11. Lo que este documento deja sin cerrar

- **No se han identificado los 15 productos de la Charter, sino 14**, y de esos, tres por
  inferencia del listado web y no por lectura del archivo (los mapas de Buenaventura del
  INGV y el de Pereira del SERTIT).
- **No se ha confirmado el crédito de las imágenes que publicó CNN**: su web devuelve un
  bloqueo legal desde Europa.
- **No se ha comprobado el portal de mapas de la NASA** (`maps.disasters.nasa.gov`): los
  puntos de entrada conocidos devolvieron 404. Que el DRCS aparezca citado por la UNGRD y
  que no se le encuentre producto público es una pista, no una conclusión.
- **No se ha buscado en fuentes no públicas** ni se ha pedido nada a nadie: esto es
  observación del exterior.
- **Los catálogos abiertos se llenan tarde.** «Maxar no publicó» significa «a 20-ago-2026 no
  había publicado». Merece una sonda que lo vigile en vez de una afirmación congelada.

---

## 12. Qué haría yo primero

1. **Roldanillo y La Virginia**, con su cifra y su atribución al SERTIT: dos municipios más
   vistos desde el aire, hoy invisibles en el monitor.
2. **Una ficha de la activación 1048**: quién la pidió, quién participó, cuántas escenas,
   de qué misiones. Contesta «quién miró», que es media tesis del proyecto.
3. **La sonda de nubosidad de Sentinel-2** sobre las AOI: convierte «el satélite no puede
   ver el Chocó» en una serie numérica que se defiende sola.
4. **La sonda de ausencia** sobre Maxar, Umbra, Capella y Planet: hoy dice que nadie abrió
   datos; el día que uno lo haga, el monitor lo cuenta el mismo día.
5. **El caso del producto cancelado de Copernicus**: ya está archivado, no cuesta nada
   contarlo, y es exclusivo.

---

## Fuentes consultadas

Institucionales y de datos:

- [Copernicus EMS — EMSR916 (noticia)](https://mapping.emergency.copernicus.eu/news/earthquake-in-colombia-emsr916/) · [activación](https://mapping.emergency.copernicus.eu/activations/EMSR916/)
- [Charter Internacional — activación 1048](https://disasterscharter.org/activations/earthquake-in-colombia-activation-1048-) · [visor de adquisiciones](https://cgt.disasterscharter.org/en/1048/1202)
- [Copernicus Data Space (catálogo OData de Sentinel-1 y 2)](https://catalogue.dataspace.copernicus.eu/odata/v1/Products)
- [NASA CMR — colecciones y granules de NISAR](https://cmr.earthdata.nasa.gov/search/collections.json?keyword=NISAR) · [datos NISAR en ASF](https://asf.alaska.edu/notices/jpl-releases-over-100k-new-nisar-data-product-files/)
- [STAC de Landsat (USGS)](https://landsatlook.usgs.gov/stac-server/search)
- [Maxar Open Data en AWS](https://registry.opendata.aws/maxar-open-data/) · [Planet Disaster Data](https://www.planet.com/disasterdata/)
- [Copernicus Risk and Recovery Mapping](https://riskandrecovery.emergency.copernicus.eu/search/)
- [UNOSAT](https://unosat.org/products/4250) · [CopernicusLAC Panamá](https://www.copernicuslac-panama.eu/news/from-crisis-response-to-proactive-resilience-how-copernicuslac-is-transforming-seismic-risk-management/)
- [UN-SPIDER (UNOOSA)](https://www.unoosa.org/oosa/en/ourwork/un-spider/index.html)

Fuente oficial colombiana y prensa:

- [UNGRD — «Con tecnología satelital UNGRD fortalece evaluación de los daños»](https://portal.gestiondelriesgo.gov.co/Paginas/Noticias/2026/Con-tecnologia-satelital-UNGRD-fortalece-evaluacion-de-los-danos-causados-por-el-terremoto-en-el-occidente-del-pais.aspx)
- [Semana — «UNGRD activó protocolo internacional…»](https://www.semana.com/economia/empresas/articulo/ungrd-activo-protocolo-internacional-que-revelara-impactantes-imagenes-satelitales-tras-el-terremoto-en-colombia/202651/) · [«Copernicus: la red de satélites…»](https://www.semana.com/tecnologia/articulo/copernicus-la-red-de-satelites-que-permite-dimensionar-la-destruccion-tras-el-terremoto-en-colombia/202617/)
- [Infobae — «La evaluación de daños… 166 imágenes»](https://www.infobae.com/colombia/2026/08/14/evaluacion-de-danos-causados-por-el-terremoto-se-esta-haciendo-con-tecnologia-satelital-ya-se-han-procesado-166-imagenes-de-alta-definicion/) · [«Indra ayuda… drones e IA»](https://www.infobae.com/america/agencias/2026/08/14/indra-ayuda-tras-el-terremoto-de-colombia-con-drones-conectividad-satelital-y-el-analisis-de-imagenes-con-ia/)
- [Cerosetenta — «Imágenes satelitales de los daños a estructuras»](https://cerosetenta.uniandes.edu.co/imagenes-satelitales-terremoto-colombia/)
- [El Nuevo Siglo](https://www.elnuevosiglo.com.co/nacion/con-tecnologia-satelital-la-ungrd-evalua-afectaciones-por-sismo) · [Radio Santa Fe](https://www.radiosantafe.com/2026/08/14/con-tecnologia-satelital-ungrd-se-evaluan-los-danos-causados-por-el-terremoto-en-el-occidente-del-pais/)
- [USGS — evento M7.4](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2/executive) · [Wikipedia (en)](https://en.wikipedia.org/wiki/2026_Colombia_earthquake)
