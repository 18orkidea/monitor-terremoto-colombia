# SEO y GEO del monitor — diagnóstico, plan y seguimiento

**Fecha del diagnóstico:** 18-ago-2026 · **Dominio:** `brechas.orkidea.eu` (GitHub Pages)

Este documento no busca tráfico por el tráfico. El monitor mide brechas de reporte: si
nadie lo encuentra, la brecha se mide pero no se cierra. Posicionar es, aquí, parte de la
misión — y el criterio de éxito no es «estar arriba», sino **ser la fuente que se cita
cuando alguien pregunta por una cifra municipal trazable**, tanto en un buscador clásico
como dentro de la respuesta de una IA.

---

## 1. Estado actual

### Lo que ya está bien hecho

| Elemento | Estado |
|---|---|
| `<title>` y `meta description` por página | Escritos, con intención de búsqueda y topónimos |
| Open Graph + Twitter Card + imágenes OG 1200×630 | Completo en las 5 páginas |
| JSON-LD | `WebSite` + `Event` + `Dataset` (portada), `Dataset` (balances), `CollectionPage` (noticias) |
| `robots.txt` + `sitemap.xml` con `lastmod` | Presentes y con HTTP 200 |
| `llms.txt` | Existe y está bien construido — **por delante del 99 % de los sitios** |
| Idioma y locale | `lang="es"`, `og:locale=es_CO` |
| Canonical | Declarado en las 5 páginas |
| HTTPS, PWA, manifest, favicon | Correctos |

El on-page está por encima de la media. **El problema no es el on-page.**

### Comprobación de posicionamiento real (SERP en vivo, 18-ago-2026)

Cuatro consultas objetivo lanzadas hoy: `terremoto Colombia 2026 damnificados por municipio`,
`terremoto Colombia 10 agosto 2026 cifras oficiales`, `mapa daños satélite Copernicus EMSR916`,
`terremoto Colombia datos abiertos CSV JSON`.

**El monitor no aparece en ninguna.** Quienes aparecen:

- **Prensa con autoridad de noticias**: Infobae (dominante), CNN Español, El Colombiano,
  Semana, El Tiempo, La FM, eldiario.es, Telecinco.
- **Wikipedia** — `Terremoto de Colombia de 2026`, top-3 en las cuatro consultas. Es además
  la fuente que más citan los LLM.
- **Competencia directa en el nicho de datos**:
  - `mapadelterremoto.com` — aparece en 3 de las 4 consultas. Dominio de coincidencia
    exacta, **367 páginas municipales**, contenido visible sin JavaScript, secciones
    numeradas, timestamps de actualización, metodología tipo FAQ.
  - `terremotovenezuela.com` — «Mapa de Daños».
  - `3is.org/emergenciaslatam/terremoto_choco/` — dashboard que integra EMSR916 + UNGRD + USGS.
  - `cerosetenta.uniandes.edu.co` — imágenes satelitales (Uniandes; alta autoridad).

---

## 2. Los seis bloqueadores, por impacto

### B1 · El contenido vive en `/site/` y la raíz es un `meta refresh`, no un 301

`https://brechas.orkidea.eu/` devuelve **HTTP 200** con una página vacía que hace
`<meta http-equiv="refresh">`. GitHub Pages no puede emitir un 301.

Consecuencias: la home del dominio no tiene contenido indexable, la autoridad de cualquier
enlace entrante al dominio raíz no se traslada limpiamente, y la URL que se comparte
(`/site/`) es innecesariamente fea y peor enlazada.

### B2 · El dato se pinta con JavaScript — y los crawlers de IA no ejecutan JavaScript

Palabras de texto **estático** por página (HTML servido, sin ejecutar JS):

| Página | Palabras estáticas | Qué falta |
|---|---:|---|
| `index.html` | 1.924 | tabla del cruce, cifras del día, mapa |
| `balances.html` | 701 | serie diaria, tabla de snapshots |
| `noticias.html` | 451 | los 6.080 titulares |
| `municipios.html` | **211** | las 95 filas de municipios |
| `rud.html` | **204** | el detalle municipal completo del RUD |

Googlebot renderiza, pero con retraso y presupuesto limitado. **GPTBot, ClaudeBot,
PerplexityBot, CCBot y Google-Extended no ejecutan JavaScript en absoluto.** Es decir: el
dato diferencial del monitor —el único que nadie más tiene— es literalmente invisible para
los sistemas que hoy responden preguntas. Este es el bloqueador con más consecuencia sobre
la misión, no solo sobre el tráfico.

### B3 · Cero páginas de entidad

Hay 95 municipios en `municipios.json`, el detalle municipal del RUD y ~6 AOIs Copernicus.
**Cero URLs propias.** Cada consulta real de una persona es municipal («damnificados
Quibdó», «daños en Pereira terremoto») y no hay ninguna página que pueda responderla.
El competidor tiene 367 y por eso aparece donde el monitor no.

### B4 · Peso de portada

`index.html` dispara **12 descargas de datos**, entre ellas `not_analysed.geojson` de
**2,2 MB** y `noticias.json` de 3,6 MB en la página de titulares. Cerca de 3 MB para pintar
la portada, más Leaflet desde `unpkg.com` (tercer dominio, sin `preconnect`, sin SRI).
En el móvil de la zona afectada esto es un LCP muy por encima del umbral, y Core Web Vitals
es criterio de ranking.

### B5 · La medición existe, pero está fuera de alcance de este análisis

**Corrección (18-ago-2026, tras aviso de JP):** Google Search Console **sí está configurado**
para el dominio — pero en una cuenta de Google distinta de `gestion@inforesidencias.com`, que
es la conectada a esta sesión. El conector de OpenSEO tampoco sirvió de puente: primero falló
por incompatibilidad de esquema y después el servidor devolvió `Server openseo unavailable`.

Consecuencia práctica: **este diagnóstico se hizo sin datos de primera mano.** Todo lo que hay
en él —las SERP, la competencia, el corpus de titulares— es evidencia externa. Falta lo único
que dice qué está pasando de verdad: impresiones, consultas reales, posición media y cobertura
de indexación. Cruzar el plan contra esos datos es la primera tarea, no una mejora opcional.

Cloudflare Web Analytics, que sí está activo, da visitas agregadas: no consultas, no
impresiones, no posición. No sustituye a GSC.

### B6 · Sitemap de 5 URLs con `lastmod` idéntico

Todas las URLs comparten la fecha del build. Cuando existan las páginas de entidad, el
sitemap debe generarse de los datos y llevar el `lastmod` real de cada página.

---

## 3. Demanda: qué busca la gente

**Advertencia metodológica, en el espíritu del proyecto:** no hay volúmenes de búsqueda en
este informe. El MCP de OpenSEO falló por incompatibilidad de esquema y no se pudo consultar
DataForSEO. Lo que sigue es **proxy de lenguaje mediático**, extraído del propio corpus del
monitor (6.080 titulares emparejados) más la lectura de las SERP en vivo. Es una hipótesis
razonada de demanda, no una medición. Cerrar esta laguna es la tarea 0.4 del plan.

Términos dominantes del corpus (bigramas, frecuencia):

```
1.037  terremoto colombia        300  valle cauca         265  death toll
  350  colombia earthquake       217  magnitude earthquake  204  western colombia
```

Topónimos por peso: **Cali (377) · Chocó (377) · Cauca (320) · Pereira (287) ·
Quindío/Armenia (184) · Manizales (171) · Quibdó · Buenaventura · Popayán · Istmina**.
Léxico: `terremoto` > `sismo` > `temblor`; `damnificados`, `magnitud`, `epicentro`, `daños`,
`viviendas destruidas`, `desaparecidos`.

### Los tres territorios de búsqueda

**Territorio 1 — La noticia** (`terremoto Colombia muertos`, `cuántos fallecidos`).
Volumen alto, decayendo desde el pico del 10-13 de agosto. Lo dominan Infobae, CNN y
Wikipedia con autoridad de noticias que el monitor no tendrá.
**Decisión: no competir.** Sería tiempo tirado.

**Territorio 2 — El mapa y los datos** (`mapa terremoto Colombia`, `daños satélite`,
`datos abiertos terremoto`). Volumen medio, competencia real pero batible:
`mapadelterremoto.com`, 3iS, Cerosetenta.
**Decisión: competir, diferenciando por trazabilidad.** Ellos muestran el dato; el monitor
es el único que muestra **de dónde sale cada dato y con qué hash**.

**Territorio 3 — La cifra municipal trazable** (`damnificados <municipio>`,
`viviendas destruidas <municipio>`, `qué municipios no ha mirado el satélite`,
`RUD damnificados terremoto`). Volumen individual bajo, **suma alta**, y —lo importante—
**sin dueño**. Ninguno de los competidores responde «cuántas familias registra el RUD en
Istmina y desde qué día». Es exactamente lo que el monitor sí sabe.
**Decisión: aquí se gana.** Es donde el SEO y la misión apuntan al mismo sitio.

### Consultas objetivo (las 15 que se van a seguir)

| # | Consulta | Territorio | Página que debe ganarla |
|---|---|---|---|
| 1 | damnificados terremoto Colombia por municipio | 3 | `/rud` |
| 2 | RUD damnificados terremoto Colombia | 3 | `/rud` |
| 3 | municipios afectados terremoto Colombia 2026 | 3 | `/municipios` |
| 4 | damnificados Quibdó terremoto | 3 | `/municipio/quibdo` |
| 5 | daños Pereira terremoto 2026 | 3 | `/municipio/pereira` |
| 6 | terremoto Cali daños agosto 2026 | 3 | `/municipio/cali` |
| 7 | viviendas destruidas terremoto Chocó | 3 | ficha departamental |
| 8 | mapa daños terremoto Colombia satélite | 2 | portada |
| 9 | Copernicus EMSR916 Colombia daños | 2 | portada |
| 10 | terremoto Colombia datos abiertos CSV | 2 | portada + `/datos` |
| 11 | cifras oficiales vs prensa terremoto Colombia | 2 | `/balances` |
| 12 | balance UNGRD terremoto Colombia por día | 2 | `/balances` |
| 13 | qué municipios no ha mapeado el satélite Colombia | 3 | `/municipios` |
| 14 | intensidad sentida DYFI terremoto Colombia municipios | 3 | `/municipios` |
| 15 | terremoto San José del Palmar Chocó epicentro | 2 | portada |

---

## 4. Plan de trabajo

Orden por dependencia, no por apetito. **Nada de la fase 1+ es evaluable sin la fase 0.**

### Fase 0 — Medir y arreglar la raíz · semana 1 · imprescindible

- **0.1** **Traer los datos de Search Console a la mesa.** La propiedad ya existe, en otra
  cuenta de Google. Tres caminos, de menos a más trabajo:
  1. Añadir `gestion@inforesidencias.com` como usuario (basta permiso de *lectura*) en
     GSC → Configuración → Usuarios y permisos. Es lo más limpio: deja el análisis reproducible.
  2. Conectar el MCP con la cuenta que sí es propietaria (cuando el servidor de OpenSEO vuelva).
  3. Exportar a mano y pasarme los CSV (ver §5, «qué exportar»).

  Y comprobar, en la misma sesión, cuatro cosas que cambian el plan según cómo estén:
  - Si la propiedad es de **dominio** (`brechas.orkidea.eu`) o de **prefijo de URL** — si es
    prefijo y apunta a `/site/`, el movimiento a la raíz de la tarea 0.2 dejaría de medirse.
  - Si el **sitemap está enviado** y cuántas de sus 5 URLs figuran como indexadas.
  - Si hay **impresiones** hoy: cambia si el problema es de indexación o solo de posición.
  - **Bing Webmaster Tools**: verificar ahí también — alimenta a Copilot y a ChatGPT.

  *Sin este paso, las fases 1 y 2 se ejecutan a ciegas: se harían igual, pero no se sabría si funcionan.*
- **0.2** **Mover el sitio a la raíz del dominio**: `/` en lugar de `/site/`.
  - Como GitHub Pages no emite 301, poner **Cloudflare delante del dominio** (ya se usa
    Cloudflare para Analytics y R2) y crear una **Redirect Rule 301** `/site/*` → `/$1`.
  - Ajustar en el build las rutas relativas `../data/public/` → `data/public/`.
  - Actualizar canonical, OG `url`, `sitemap.xml` y `llms.txt`.
  - **Test obligatorio**: las 5 páginas cargan sus datos desde la raíz; `/site/…` responde 301.
- **0.3** `preconnect` a `unpkg.com` o autoalojar Leaflet.
- **0.4** Cerrar la laguna de demanda: obtener volúmenes reales (arreglar el MCP de OpenSEO,
  o Keyword Planner, o Google Trends CO) y **revisar la tabla de 15 consultas con datos**.

### Fase 1 — Prerenderizar el dato · semanas 1-2 · **la palanca principal**

- **1.1** Generar en el build el HTML de las tablas que hoy pinta el JS: las 95 filas de
  `municipios.html` y el detalle municipal de `rud.html`, dentro del `<tbody>` del HTML servido.
  El JS pasa a **hidratar** (filtrar, ordenar, paginar) sobre un DOM que ya existe, en vez de crearlo.
  - Fuente única: el generador lee los mismos `data/public/*.json` que consume el frontend.
    No se duplica lógica de negocio.
  - **Test** (`tests/test_seo.py`): `municipios.html` contiene ≥ 90 `<tr>`; `rud.html` contiene
    el nombre de cada municipio registrado; ninguna celda vacía se sirve como `0` (R3).
- **1.2** Añadir a cada página un **bloque de respuesta corta** en texto plano: 2-3 frases con
  la cifra del día, su fecha y su fuente. Es la unidad que un LLM cita y la que Google usa
  para fragmentos destacados.

### Fase 2 — Páginas por municipio · semanas 2-4 · **el volumen**

- **2.1** Generar `/municipio/<slug>` para cada municipio **con alguna señal** (RUD, prensa,
  DYFI o AOI Copernicus). **Umbral explícito: sin señal, no hay página** — 95 páginas vacías
  serían thin content y penalizan al dominio entero.
  Contenido, todo derivado de datos ya existentes (cero redacción a mano):
  - `H1`: «Terremoto de Colombia 2026 en <Municipio> (<Departamento>): damnificados, daños y cobertura»
  - **Párrafo-respuesta**: familias y personas del RUD, desde qué día, % de la población DANE 2026,
    viviendas destruidas/averiadas, si está dentro de AOI Copernicus, intensidad DYFI, nº de titulares.
  - Serie diaria del registro + tabla trazable.
  - Titulares del municipio (ya emparejados por el monitor).
  - **«Qué no sabemos de este municipio»** — la sección que ningún competidor tiene y que es la
    firma del proyecto: sin registro ≠ sin daño; sin producto satelital no hay cruce (R2).
  - Enlace a la fuente y al snapshot con su `sha256`.
  - Schema: `Dataset` + `Place` + `FAQPage` con 3 preguntas reales.
  - **Guardarraíl editorial**: pasar por el agente `auditor-editorial` antes de publicar. Un
    generador que escriba «0 damnificados» donde el dato es «sin registro» rompería R3 a escala de 95 páginas.
- **2.2** Página por AOI Copernicus (~6-8 URLs) con la misma lógica.
- **2.3** Sitemap generado desde los datos, con `lastmod` real por página.
- **2.4** Enlazado interno: cada fila de `/municipios` enlaza a su ficha; cada ficha enlaza a su
  departamento, a su AOI y a la portada. Sin esto, las páginas nuevas quedan huérfanas.

### Fase 3 — GEO: ser citable por las IA · semanas 3-4

- **3.1** `llms-full.txt`: volcado completo en texto plano de las cifras del día por municipio,
  más las reglas de rigor. `llms.txt` ya existe y está bien; falta la versión extensa.
- **3.2** Declarar explícitamente en `robots.txt` el permiso para `GPTBot`, `ClaudeBot`,
  `PerplexityBot`, `Google-Extended`, `CCBot`, `Bingbot`, `Applebot-Extended`. Hoy `*` ya los
  cubre, pero declararlo es una señal inequívoca y evita que un cambio futuro los excluya sin querer.
- **3.3** **Escribir para ser citado**: cada dato en una frase autónoma con sujeto, cifra, fecha y
  fuente — «Según el RUD de la UNGRD consultado el 18-ago-2026, Quibdó registra N familias
  damnificadas». Los LLM citan frases completas, no celdas de tabla.
- **3.4** Depositar el dataset en **Zenodo** para obtener un **DOI**. Da citabilidad académica,
  un backlink de altísima autoridad y —lo que importa a la misión— permanencia del archivo.
- **3.5** **Wikipedia**: el artículo «Terremoto de Colombia de 2026» está en el top-3 de todas las
  consultas y es la fuente más citada por los LLM. Proponer el monitor como referencia/enlace
  externo, respetando las normas (aporta datos primarios trazables y verificables, no promoción).
  **Es la acción con mejor relación impacto/esfuerzo de todo el plan.**

### Fase 4 — Autoridad y enlaces · continuo

- **4.1** Alta del dataset en **HDX** (Humanitarian Data Exchange), **ReliefWeb**, el portal de
  datos de la respuesta, listas «awesome» de datos abiertos, wiki de OSM de la respuesta y
  *topics* de GitHub.
- **4.2** Prensa (070/Cerosetenta, La Silla Vacía): cuando usen los datos, **pedir enlace**, no
  solo mención. Un enlace de Uniandes o La Silla vale más que cien optimizaciones de título.
- **4.3** Publicar una nota metodológica autónoma («cómo se mide una brecha de reporte») —
  contenido enlazable por sí mismo, independiente del ciclo de la noticia.

### Fase 5 — Rendimiento · semana 4

- **5.1** No cargar `not_analysed.geojson` (2,2 MB) en el arranque: bajo demanda al activar la capa.
- **5.2** Autoalojar Leaflet o `preconnect` + SRI.
- **5.3** Paginar/segmentar `noticias.json` (3,6 MB).
- **5.4** Objetivo medible: **LCP < 2,5 s** en móvil 4G, INP < 200 ms, CLS < 0,1.

### Si solo se hacen tres cosas

1. **Fase 0.1** — dar acceso al Search Console que ya existe (10 minutos, desbloquea todo lo demás).
2. **Fases 1 + 2** — prerender + páginas por municipio (el 80 % del resultado).
3. **Fase 3.5 + 3.4** — Wikipedia y Zenodo/DOI (el mejor retorno por hora invertida).

---

## 5. Plan de seguimiento

### Cadencia

| Cuándo | Qué se mira | Umbral de alarma |
|---|---|---|
| **Semanal (lunes)** | GSC: impresiones, clics, CTR, posición media, consultas nuevas *(requiere 0.1)* | Impresiones planas 3 semanas seguidas tras publicar la fase 2 |
| **Semanal** | Cobertura: páginas indexadas ÷ páginas del sitemap | < 70 % a las 3 semanas de publicarlas |
| **Semanal (automático)** | Render sin JS: las cifras clave aparecen en el HTML servido | Cualquier fallo ⇒ alerta (una regresión de la fase 1 es invisible a simple vista) |
| **Quincenal** | Posición en las 15 consultas objetivo | Caída > 5 puestos en una consulta del territorio 3 |
| **Quincenal** | **GEO**: preguntar las 6 consultas principales a ChatGPT, Perplexity y AI Overviews, y anotar si el monitor es citado | Cero citas al cabo de 8 semanas ⇒ revisar la fase 3 |
| **Mensual** | Backlinks nuevos; qué huecos ha cubierto `mapadelterremoto.com` | El competidor publica fichas de trazabilidad ⇒ replantear diferencial |

### Qué exportar de Search Console (si el acceso se resuelve pasando ficheros)

Cuatro exportaciones, rango **desde el 10-ago-2026 hasta hoy**, filtrando por país = Colombia
en una segunda copia de las dos primeras:

1. **Rendimiento → Consultas**, con clics, impresiones, CTR y posición. Es lo que dice qué
   busca de verdad la gente que ya llega, y permite sustituir la tabla de 15 consultas
   objetivo del §3 —hoy razonada, no medida— por una lista con demanda comprobada.
2. **Rendimiento → Páginas**: revela cuál de las cinco páginas tira y cuál está muerta.
3. **Rendimiento → Consultas filtrado a posiciones 8-25** («distancia de golpeo»): son las
   que suben con poco esfuerzo y marcan por dónde empezar la fase 2.
4. **Indexación → Páginas**: cuántas indexadas, cuántas excluidas y con qué motivo. Si
   aparecen exclusiones del tipo «Rastreada, actualmente sin indexar», confirma el
   diagnóstico B2 (contenido pintado con JS) con datos de Google en vez de por inferencia.

Con eso el plan se recalibra en una sesión: puede que la fase 2 haya que priorizarla por otros
municipios, o que el cuello real sea la indexación y no la posición.

### Automatizarlo dentro del propio monitor

Coherente con la filosofía del proyecto (R11: los supuestos avisan, no rompen en silencio):

- **`ingest/seo_check.py`**, en la corrida diaria, verifica que:
  el sitemap coincide con las páginas realmente generadas; el canonical de cada página es
  correcto; cada ficha municipal contiene su cifra **en el HTML servido**; ninguna página
  generada baja de un mínimo de contenido; ningún «sin registro» se ha convertido en «0».
- Fallo ⇒ **alerta** por el canal de `ingest/alerts.py`, igual que cualquier otra fuente que calla.
- Histórico en `data/public/seo.json` → el monitor se audita también a sí mismo. Es dogfooding
  del principio del proyecto, y es publicable.

### Objetivos por hito

| Plazo | Objetivo |
|---|---|
| Semana 4 | 100+ URLs indexadas · primeras impresiones en GSC · LCP < 2,5 s |
| Semana 8 | Top-10 en ≥ 5 consultas del territorio 3 · primera cita en un LLM · DOI de Zenodo activo |
| Semana 12 | Orgánico como canal principal · ≥ 5 backlinks institucionales o de prensa · referencia en Wikipedia |

### Advertencia honesta sobre el horizonte

El tráfico de un evento decae rápido: la curva de «terremoto Colombia» ya está en descenso
desde el pico del 10-13 de agosto, y ninguna optimización revierte eso. Perseguir el pico es
perseguir algo que ya pasó.

El valor duradero del monitor no es un pico de visitas: es **ser la referencia archivística
que se cita cuando, dentro de meses o años, alguien reconstruya lo que pasó municipio a
municipio**. Por eso Wikipedia, el DOI de Zenodo, HDX y el prerender —todo lo que hace el
archivo citable y permanente— pesan más en este plan que cualquier ajuste de metadatos.
Y por eso el éxito de este plan es compatible con el éxito declarado del proyecto: quedar
felizmente obsoleto el día que lo oficial publique todo en abierto.

---

## 6. El competidor: `mapadelterremoto.com` (Naboo Intelligence)

*Análisis del 18-ago-2026. Motivo: es el único competidor que aparece sistemáticamente donde
el monitor no, y **anuncia su propio cierre**.*

### 6.1 El hecho que lo cambia todo

El sitio declara que estará **«actualizado hasta el 30 de noviembre de 2026»**, y que después
«los datos quedan publicados de forma permanente en formato abierto». Está «construido y
mantenido sin coste por Naboo Intelligence», «cedido sin coste para esta emergencia».

Es decir: **el competidor tiene fecha de caducidad, y la ha publicado.** Eso convierte el
problema de «cómo competir» en dos problemas distintos y mucho más manejables:

- **Hasta el 30-nov (≈ 15 semanas):** no se le gana en cobertura. Hay que ocupar el hueco que
  él deja vacío por diseño.
- **Desde el 1-dic:** sus 564 páginas se congelan. No desaparecen —Google no las desindexa y
  conservan autoridad— pero **dejan de responder a «qué pasa ahora»**. Ahí el monitor puede
  ser el único que siga contestando, si para entonces ya está indexado y con historial.

La consecuencia operativa es incómoda pero clara: **el plan hay que ejecutarlo antes de
noviembre, no después.** Llegar en diciembre a ocupar el hueco es llegar tarde: los buscadores
premian la continuidad demostrada, no la aparición oportunista.

### 6.2 Qué hacen mejor (sin adornos)

| Dimensión | Ellos | Nosotros |
|---|---|---|
| URLs indexables | **564** | 5 |
| Fichas municipales | **432** | 0 |
| Renderizado | Next.js **prerenderizado** (SSG en Vercel): todo el contenido en el HTML | Todo pintado con JS |
| Verticales por servicio | albergues, colegios, hospitales, vías, servicios × ciudad (≈130 URLs) | — |
| Evidencia declarada | 3.363 puntos, 7.477 evidencias, 257 fuentes | 1.578 edificios, 6.080 titulares, ~20 fuentes |
| Enlazado interno | «Por tema en X», «Municipios cerca de X» | Navegación plana entre 5 páginas |
| Intención de búsqueda del afectado | «Dónde ayudar», puntos de acopio | — |

Tres cosas suyas merecen respeto explícito:

1. **La arquitectura es SEO programático de manual**: entidad × faceta. Es exactamente lo que
   la fase 2 de este plan propone, ya construido y ya indexado.
2. **Su sección «Inteligencia» juega en nuestro terreno editorial.** Declara extracción
   determinista y auditable «en vez de modelos de lenguaje», compara lo pedido contra lo
   entregado, y publica sus propias lagunas: «128 centros de salud sin evaluar», «2.208
   ubicaciones (66 %) con una sola fuente», «68 municipios sin alternativa sanitaria». Eso es
   medir brechas. No somos los únicos que lo hacen.
3. **Tratan bien los datos ausentes**, igual que R3: los omiten en vez de escribir 0, y dicen
   por qué — «las cifras oficiales de víctimas y viviendas no aparecen aquí porque todavía no
   existen consolidadas».

### 6.3 Dónde son débiles (medido, no supuesto)

Muestreo del HTML servido de 10 fichas municipales, contando palabras reales:

| Ficha | Palabras estáticas |
|---|---:|
| `/municipio/cali` | 28.542 |
| `/municipio/pereira` | 17.458 |
| `/municipio/quibdo` | 6.745 |
| `/municipio/san-jose-del-palmar` | 2.361 |
| `/municipio/istmina` | 1.411 |
| `/municipio/condoto` | 658 |
| `/municipio/medio-atrato` | 560 |
| `/municipio/bagado` | 529 |
| `/municipio/nuqui` | 508 |
| `/municipio/litoral-del-san-juan` | **404 — la ficha no existe** |

**El patrón es inequívoco.** Su cobertura es proporcional a la cobertura mediática: donde hay
prensa (Cali, Pereira), sus fichas son enormes e inalcanzables; donde no la hay —los municipios
pequeños del Chocó y del San Juan, los que más importan— sus fichas caen a ~500 palabras
genéricas, y algunas ni existen.

Eso no es un defecto de su ejecución: es **la brecha de reporte que este monitor existe para
medir, reproducida dentro del propio competidor.** Su sitio se alimenta de fuentes públicas y
prensa; donde la prensa calla, él también.

Y lo que estructuralmente no tienen:

- **Sin descargas.** Ni CSV, ni JSON, ni API. Los datos no se pueden reutilizar.
- **Sin licencia declarada.** Dicen «formato abierto» pero no dicen cuál.
- **Sin `llms.txt`** (404) — para GEO, vamos por delante.
- **Sin archivo verificable**: citan fuentes con nombre y fecha, pero no archivan la petición.
  No hay snapshot inmutable ni hash: si el medio citado edita o borra, la evidencia se evapora.
- **Sin serie temporal.** Son una foto del presente. No responden «cuándo se registró» ni
  «cómo evolucionó».
- **Sin el RUD.** Lo dicen ellos mismos: las cifras oficiales no están porque «no existen
  consolidadas». **Ese es, literalmente, nuestro hueco ganador**, y lo han dejado por escrito.
- **Sin código abierto** ni reproducibilidad.

### 6.4 La estrategia: no imitarles, sucederles

Intentar ser ellos es perder: llegamos quince semanas tarde, con menos fuentes y sin equipo.
La jugada es ser **explícitamente lo que ellos han decidido no ser: permanente, descargable y
verificable**.

Ellos responden *«¿qué está pasando y dónde pido ayuda?»* — útil hoy, muerto en diciembre.
El monitor responde *«¿qué se registró, cuándo, quién lo dijo y qué falta todavía?»* — que es
lo que se seguirá preguntando en 2027 y en 2036.

**Cuatro movimientos, por orden:**

**M1 · Ocupar la cola larga que ellos no cubren — antes de noviembre.**
Las fichas municipales de la fase 2 se priorizan **al revés de la intuición**: primero los
municipios donde ellos son delgados y nosotros somos fuertes. Nuqui, Bagadó, Medio Atrato,
Condoto, Litoral del San Juan, Istmina, San José del Palmar — donde ellos ponen 500 palabras
de prensa, nosotros ponemos el RUD oficial con su serie diaria, la población DANE, la
cobertura satelital y qué no se ha mirado. **No competir por Cali ni por Pereira**: ahí pierden
ellos también, contra Infobae.

**M2 · Archivar al competidor antes de que se congele.**
Naboo es una fuente que ha anunciado su muerte con fecha. El principio de archivo del proyecto
exige plan de sucesión para toda fuente; **esta lo pide a gritos**. Concretamente: snapshot
diario de su sitemap y de sus fichas, con `sha256` y fila en `sources_log`, más envío a Wayback,
desde ya hasta el 30-nov. Coste bajo, valor archivístico alto, y perfectamente legítimo —es
material público, se cita y se enlaza, no se copia.

**M3 · Ofrecerles ser el custodio de sus datos abiertos.**
Han dicho que los datos quedarán «en formato abierto» pero no han dicho dónde ni con qué
licencia, y no tienen infraestructura de datos. El monitor sí: CC BY 4.0, CSV/JSON/GeoJSON,
repositorio público, snapshots con hash. Proponer a Naboo Intelligence espejar y mantener su
dataset con atribución explícita es bueno para los dos y encaja con la misión. Aunque digan que
no, la conversación abre la puerta a un enlace mutuo — y un enlace suyo vale más que cien
ajustes de metadatos.

**M4 · Contar el cierre cuando ocurra.**
El 30 de noviembre, publicar el hito: *qué se pierde cuando se apaga el mejor mapa de la
emergencia, y qué queda conservado*. Es noticia real, es enlazable, es exactamente la tesis
del proyecto —los datos de un desastre desaparecen cuando la atención se va— y llega con la
prueba en la mano. Registrar el hito en `feeds/hitos_monitor.json`.

### 6.5 Qué copiarles, y qué no

**Copiar (son buenas ideas, sin más):**
- Arquitectura **entidad × faceta** y el enlazado «municipios cerca de X».
- **Prerender estático**: su `x-nextjs-prerender: 1` es la razón de que ellos se indexen y
  nosotros no. Confirma que la fase 1 es la palanca correcta.
- **Nivel de confirmación por dato** («Confirmado por N fuentes» / «Reportado por N fuentes»):
  legible al instante y compatible con nuestros estados de cruce.
- Una sección de intención práctica. La nuestra no es «dónde ayudar» sino **«cómo reportar un
  daño»** y **«cómo verificar una cifra»** — que ya existen, pero enterradas.

**No copiar:**
- **Albergues, colegios, hospitales y vías operativas.** Es información de emergencia
  perecedera, no es nuestra misión, envejece mal y el 1 de diciembre ya no sirve. Mantenerla
  a medias sería peor que no tenerla, y rompería la promesa de trazabilidad del proyecto.
- **Cali, Pereira, Manizales como objetivo SEO.** Volumen alto, pero es territorio de medios.

### 6.6 Calendario revisado

| Plazo | Hito |
|---|---|
| **Semana 1** (hasta 25-ago) | Acceso a GSC · empezar el archivado de Naboo (M2) |
| **Semanas 1-3** | Fase 1: prerender de las tablas |
| **Semanas 3-8** (hasta ~15-oct) | Fase 2 invertida: fichas municipales, **empezando por la cola larga del Chocó** (M1) |
| **Semanas 8-12** (hasta ~15-nov) | Fase 3 (GEO, Wikipedia, Zenodo) · contacto con Naboo (M3) |
| **30-nov-2026** | Naboo se congela. El monitor debe llevar ya ≥ 6 semanas indexado y actualizándose a diario |
| **1-dic-2026** | Publicar el hito del cierre (M4) |

**El riesgo real no es Naboo: es llegar a diciembre sin las fichas indexadas.** Si el prerender
y las fichas municipales están vivos en octubre, el cierre del competidor es una oportunidad.
Si llegan en enero, es solo una noticia que contamos tarde.

---

## 7. Plan de transformación del sitio (SEO + GEO)

*Aprobado el 18-ago-2026. Este es el plan de ejecución: cada fase deja el sitio funcionando.*

**Principio rector:** el HTML es el artefacto; el JavaScript solo mejora lo que ya está escrito.
Ninguna cifra publicada puede depender de que el navegador ejecute código — ni para Google, ni
para los sistemas de IA, ni para quien entre con mala conexión desde la zona afectada.

**Dónde se genera:** todo en el build (`dist/`), nunca en `site/*.html` del repo. Un HTML que
cambia entero cada día destruiría el blame, y el dato ya está versionado en `data/public/`, así
que las páginas son reconstruibles desde cualquier commit.

### Fase A — Fichas municipales `/municipio/<slug>/`

Generador `deploy/render_html.py` (stdlib, R14). Una ficha por municipio **con alguna señal**
(RUD, prensa, DYFI, satélite o reportes ciudadanos); sin señal no hay página, para no publicar
noventa páginas vacías.

Contenido, todo derivado de `data/public/*.json`:

- Párrafo-respuesta citable: una idea por frase, cada una con cifra, fecha y fuente.
- Tarjetas con las cifras del RUD y la población DANE.
- **Mapa SVG estático** generado aquí — no Leaflet: noventa fichas con mapa interactivo harían
  impracticable el sitio, y un SVG se indexa y pesa nada. Muestra el municipio, el epicentro, las
  zonas con producto satelital y los reportes ciudadanos: cuando no hay daño que pintar, el mapa
  cuenta la ausencia.
- Serie del registro (frase del delta; la gráfica SVG entra a partir de la 5.ª captura).
- Titulares del municipio, con el medio extraído del titular.
- **«Qué no sabemos»** — la sección que ningún competidor tiene.
- Llamada a reportar por ChatMap: donde el satélite no mira, cada reporte cuenta.
- JSON-LD `Dataset` + `Place` con DIVIPOLA.

**Dos precisiones de lenguaje, no cosméticas:**

1. **«Ningún producto satelital ha reportado daño»**, no «ningún producto de Copernicus». Ya son
   dos los activos —Copernicus EMSR916 y UNITAR-UNOSAT— y pueden entrar más (NISAR, HRSL): la
   frase debe seguir siendo cierta el día que entren. R2 habla de «producto satelital», no de una
   marca. Escrita en singular caducó en cuanto llegó el segundo, y con ella caducaron las páginas
   que la copiaban.
2. **El RUD es un censo declarativo sujeto a verificación posterior.** No es una medición de daño
   ni un dato cerrado: las autoridades municipales registran, y esa inscripción se verifica después.
   Decirlo en la ficha es obligatorio — si no, la cifra se lee como un balance definitivo y estamos
   cometiendo el error que el monitor denuncia en otros.

### Fase B — `municipios.html` en HTML, con enlaces a las fichas

La tabla de los 95 municipios se genera en el build dentro del `<tbody>`, y **cada fila enlaza a
su ficha**. Sin esto las fichas quedan huérfanas y no se descubren. `tablaBuscable` deja de crear
filas y pasa a filtrar el DOM existente: una sola implementación de la presentación, en Python.

### Fase C — Tabla de la portada: solo municipios con evidencia puntual

La tabla del cruce pasa de zona (AOI) a **municipio con evidencia georreferenciada** — satélite o
reportes ciudadanos dentro del municipio. Medido hoy: **28 municipios de 95**.

El hallazgo que justifica el cambio: **el satélite ha mirado 6 municipios; la comunidad ha
documentado 26.** La portada deja de estar organizada por lo que decidió mirar el satélite y pasa
a estarlo por dónde hay prueba sobre el terreno, venga de donde venga.

Salvedad técnica documentada: no tenemos polígonos municipales, solo cabeceras, así que la
asignación es por proximidad a la cabecera más próxima (mediana de 1,8 km para satélite y 2,2 km
para ciudadanos). Los 23 reportes ciudadanos a más de 25 km de cualquier cabecera del área de
influencia se cuentan en el total pero no se atribuyen a ningún municipio. Conseguir los polígonos
DIVIPOLA convertiría la aproximación en exactitud: queda anotado en `docs/LIMITACIONES.md`.

### Fase D — El resto del prerender

`rud.html` (detalle municipal), `balances.html` (serie y tabla de snapshots) y `noticias.html`
—esta paginada: 6.080 titulares en una página no los digiere ningún crawler—.

### Fase E — Descubrimiento y verificación

- `sitemap.xml` generado de los datos, con `lastmod` real por página.
- `llms-full.txt`: el volcado en texto plano de las cifras del día por municipio.
- Permiso explícito en `robots.txt` para GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot.
- **`ingest/seo_check.py`**: verifica el `dist/` construido —cifras presentes en el HTML servido,
  cero JS ejecutable, SVG válido, sitemap coherente, y **ningún `0` donde el dato es `None`**— y
  **alerta** si falla, como cualquier fuente que calla (R11). Sin esto, una regresión del prerender
  es invisible: la página se vería perfecta en el navegador y vacía para los bots.

### Fase F — Dominio y rendimiento

**Hecho sin tocar infraestructura.** El plan original pedía un 301 desde Cloudflare, pero el
dominio está en DNS-only (`server: GitHub.com`, sin `cf-ray`): activar el proxy sobre GitHub
Pages exige cambiar el modo SSL a *Full* y arriesga tumbar el sitio, para preservar una
indexación que hoy es prácticamente nula. Se descarta.

En su lugar, el build sirve el sitio desde la raíz de `dist/` y deja en `/site/*` una
redirección de cliente con `canonical` a la URL nueva y `noindex`. No es un 301, pero Google
consolida por el canonical y ninguna URL publicada se rompe. El 301 real sigue disponible el
día que el dominio pase por Cloudflare.

Pendiente: `not_analysed.geojson` (2,2 MB) bajo demanda y Leaflet autoalojado. Objetivo
LCP < 2,5 s en móvil.

### Orden y estado

| Fase | Estado |
|---|---|
| A · fichas municipales | **hecha** — `deploy/render_html.py`, 95 fichas, 18 tests |
| B · municipios.html + enlaces | **hecha** — 95 filas y 95 enlaces en el HTML servido |
| C · portada por evidencia puntual | **hecha** — 28 municipios, sustituye la tabla por AOI |
| D · resto del prerender | pendiente |
| D1 · banda de brechas de portada | **hecha** — `banda_brechas`, prosa en el HTML servido |
| E · sitemap, llms-full, robots | **hecha** — `deploy/render_descubrimiento.py`, 8 tests |
| E2 · `ingest/seo_check.py` | pendiente |
| F1 · sitio en la raíz | **hecha** — sin tocar DNS; `/site/*` sigue vivo con canonical |
| F2 · rendimiento (peso, Leaflet) | pendiente |

Trabajo en la rama `seo-geo-fichas`.

**Deuda anotada de la fase B**: `municipios.html` sigue descargando `municipios.json`
(191 KB) para dos frases de la introducción —la cobertura satelital y la salvedad de los
homónimos—, que aún se pintan con JavaScript. Prerenderizarlas eliminaría esa descarga
por completo; requiere llevar `fraseHomonimos` a Python con su test espejo.

La banda amarilla de la portada —el resumen de las dos brechas centrales— fue la primera
pieza de **prosa** que pasó por este camino, no una tabla: el contenedor marcado es una
`<section data-gen="brechas">` y el texto lo escribe `render_html.py::banda_brechas`. Es el
párrafo más citable del sitio y solo existía en la memoria del navegador. La redacción
vive en Python y en ningún otro sitio; `site/app.js` únicamente refresca los contadores de
días, que dependen del reloj de quien lee. Queda pendiente el mismo tratamiento para las
notas cortas que aún pinta el JavaScript (`nota-rud-desde`, `nota-sin-registro`).

**Deuda anotada de `ui.js`**: conviven `tablaBuscable` (crea filas desde datos) y
`tablaHidratada` (filtra las ya escritas). Es una migración incremental: `tablaBuscable`
desaparece cuando `rud.html`, `balances.html` y `noticias.html` pasen por la fase D.

Cada fase cierra con su test, y las que tocan texto visible pasan por `auditor-editorial` antes
de commitear.

---

## 8. Diagnóstico tras la ejecución (20-ago-2026)

Mismas mediciones que el §1, sobre el artefacto construido. Todas las cifras salen de
`ingest/seo_check.py`, que ahora corre en cada despliegue.

### Lo que ve quien no ejecuta JavaScript

| página | palabras antes | ahora | filas antes | ahora |
|---|---:|---:|---:|---:|
| portada | 1.924 | **2.511** | 0 | **42** |
| municipios | 211 | **1.787** | 0 | **97** |
| RUD | 204 | **1.342** | 0 | **91** |
| balances | 701 | **1.338** | 0 | **29** |
| titulares | 451 | **6.212** | 0 | **206** |

Y **96 páginas que antes no existían**: una por municipio con señal, en
`/municipio/<slug>/`, con su párrafo citable, su mapa en SVG y su sección de lo que no
se sabe.

### Descubrimiento

| | antes | ahora |
|---|---|---|
| URLs en el sitemap | 5 | **101** |
| home del dominio | `meta refresh` sin contenido | la portada real |
| `llms.txt` | sí | sí |
| `llms-full.txt` | no | **48 KB, 96 municipios en texto plano** |
| rastreadores de IA en `robots.txt` | implícitos | **declarados uno a uno** |
| enlaces internos a las fichas | — | **123** (96 en municipios, 28 en portada) |

### Lo que sigue sin resolverse

**El peso de la portada: 3,5 MB.** Es el bloqueador B4 del diagnóstico inicial y sigue
intacto. Desglose de lo que descarga antes de ser usable:

```
not_analysed.geojson   2.173 KB   ← el 60 % del total
ungrd_sismos.geojson     307 KB
damage_points.geojson    266 KB
municipios.geojson       194 KB
unosat_damage.geojson    183 KB
… y ocho ficheros más
```

`not_analysed.geojson` es, él solo, más que todo lo demás junto. Es la capa de «zonas sin
analizar»: importa editorialmente —es la brecha dibujada— pero no hace falta para el
primer pintado. **Cargarla bajo demanda es la única tarea que queda del plan con impacto
medible en el posicionamiento**, porque los Core Web Vitals son criterio de ranking y esto
se ve en un móvil de la zona afectada.

Pendiente también: Leaflet se sirve desde `unpkg.com`, un tercer dominio sin `preconnect`
ni comprobación de integridad.

### Lo que no se puede medir todavía

Nada de esto se traduce en visitas hasta que el buscador rastree, y no hay forma de
saberlo: **sigue sin haber Search Console verificado**. Es la tarea 0.1 del plan, cuesta
media hora y es la única que no puede hacerse desde el repositorio. Hasta entonces, todo
lo anterior son mediciones de lo publicado, no de lo encontrado.

### Cómo se vigila desde ahora

`ingest/seo_check.py` corre en el despliegue y avisa —sin bloquearlo— si alguna página
baja de su mínimo de palabras o de filas, si un contenedor marcado queda vacío
—`<tbody>`, `<ul>` o `<section>`—, si el
sitemap anuncia una URL que no existe, si una ficha gana JavaScript ejecutable o cita
códigos internos de reglas, o si desaparecen `robots.txt` o los dos `llms.txt`.

La regresión que vigila es la que no se ve: si el prerenderizado se rompe, la página sigue
perfecta en el navegador y llega vacía a quien tiene que citarla.
