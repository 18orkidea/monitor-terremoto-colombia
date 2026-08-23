# Cómo contribuir

Este monitor audita el ecosistema de datos de desastres en Colombia: quién publica, quién
calla, y qué queda subestimado. Toda ayuda es bienvenida — no hace falta saber programar
para varias de las tareas más valiosas.

## Formas de contribuir

### Sin código

- **Evidencia oficial**: si encuentras un EDAN, balance de UNGRD/alcaldía/gobernación u
  otro documento oficial con cifras del terremoto de agosto de 2026, abre un issue con el
  enlace y la fecha. Es la pieza que ningún sistema automático puede aportar hoy — y la
  única que promueve una zona a «Coincide cualitativamente».
- **Reportes de terreno**: si estás en la zona, usa el
  [ChatMap de OSM Colombia](https://chatmap.hotosm.org/colombia.html) (ubicación + foto
  por WhatsApp). Este monitor lo ingiere a diario.
- **Correcciones**: ¿una cifra no cuadra con su fuente? Cada número es rastreable
  (`data/snapshots/` + tabla `sources_log`). Abre un issue con el dato y el snapshot.

### Añadir un feed de noticias (la contribución más fácil)

El monitor lee los feeds de [`feeds/registry.json`](feeds/registry.json). Para añadir un
medio local o regional que cubra las zonas afectadas:

1. Añade una entrada al registro con un PR:
   ```json
   { "id": "mi-medio", "nombre": "Mi Medio — Región", "tipo": "rss",
     "url": "https://mimedio.co/rss.xml", "idioma": "es", "activo": true,
     "nota": "Cobertura local de Chocó" }
   ```
2. Comprueba que la URL devuelve RSS/Atom válido (`curl -sL <url> | head -5`).
3. Nada más: el pipeline lo ingiere a diario, filtra por las palabras clave del evento,
   empareja por topónimo y los titulares aparecen en [la página de
   noticias](site/noticias.html). Los feeds que fallan no rompen la corrida.

Los medios pequeños de las zonas menos cubiertas (Chocó, San Juan) son los más valiosos:
Istmina tiene hoy **cero** titulares en los feeds internacionales.

Además del registro manual, el pipeline genera una búsqueda Google News por cada
municipio del catálogo: los curados en `ingest/municipios.py` **y los que abre solo el
registro oficial (RUD)**. Esa lista no se mantiene a mano — un municipio que entre hoy al
RUD tiene su búsqueda en la siguiente corrida. Si falta una ciudad afectada que el RUD no
registra, añádela en `ingest/municipios.py` con departamento, coordenada aproximada y
topónimos; la siguiente corrida buscará titulares para ese municipio y lo cruzará con
DYFI, DANE y Copernicus.

Dos municipios no reciben búsqueda automática por diseño: los que se llaman igual que un
departamento (Bolívar, Córdoba, Risaralda, Sucre) y aquellos cuyo nombre oficial no se
escribe así en un titular. Para ellos, **un feed del registro manual es la única vía**,
porque ahí el municipio lo declara una persona. Ver `docs/LIMITACIONES.md`.

### Con código

- Buenas primeras tareas: nuevas fuentes (`ingest/sources/` — un módulo por fuente, toda
  petición pasa por `common.fetch()`), mejoras del mapa (`site/`, JS sin build), o los
  datos recogidos aún sin pintar (historial de versiones/latencia de Copernicus, EDAN
  histórico completo, desglose PAGER, contraste DYFI↔EMSC).
- Extensión mayor documentada en el README: asentamientos bajo dosel (HRSL, Open
  Buildings, NISAR) y el canal Kobo estructurado.

## Reglas del proyecto (no negociables)

1. **Nada de coincidencias fabricadas**: `Coincide cualitativamente` exige evidencia
   oficial. La prensa y los reportes ciudadanos alimentan estados intermedios explícitos.
2. **Los `"NA"` no son ceros**: los valores no numéricos de las fuentes se conservan
   como NULL + literal crudo.
3. **Trazabilidad**: toda petición HTTP pasa por `common.fetch()` (log + sha256 +
   snapshot). Ninguna cifra sin fila en `sources_log`.
4. **Privacidad ciudadana**: coordenadas públicas redondeadas (~110 m), EXIF nunca
   publicado, fotos de daño material y no de personas.

## Flujo

```bash
python ingest/run_daily.py            # corrida completa local
python -m unittest discover -s tests  # toda la suite: código, supuestos de APIs, hipótesis
python3 -m http.server 8123           # ver el sitio en http://localhost:8123/site/
```

PRs con tests. Si tu cambio toca un supuesto sobre una fuente externa, añade el test en
`tests/test_supuestos_api.py` — los supuestos rotos deben avisar, no romper en silencio.
Las reglas de desarrollo completas (rigor, naming, Definition of Done) están en
[CLAUDE.md](CLAUDE.md); la arquitectura y las decisiones, en [docs/](docs/).

## Idioma

El proyecto se documenta en español (es el contexto del desastre y de sus usuarios).
El código usa identificadores en inglés cuando es idiomático; los comentarios, en español.
