---
name: nueva-fuente
description: Checklist completa para dar de alta una fuente de datos en el monitor (la operación recurrente del proyecto). Usar siempre que se añada una fuente nueva — API, feed, scraping o dataset — o se modifique sustancialmente una existente.
---

# Alta de una fuente de datos

Toda fuente entra al monitor con TODAS las piezas del día uno. Una fuente sin plan de
sucesión es un hueco de archivo esperando a pasar. Sigue los pasos en orden.

## 1. Módulo de ingesta

- Crear `ingest/sources/<nombre>.py` con docstring de módulo en español: qué aporta,
  URL base, condiciones de acceso, y qué NO garantiza la fuente (retención, licencia).
- **Firma canónica**: `def run(conn, *, snapshot_date=None, **opciones) -> dict` —
  recibe la conexión sqlite, devuelve un resumen dict (contadores) para run_daily.
  (Las fuentes antiguas tienen firmas variadas; las nuevas usan esta.)
- **Todo HTTP por `common.fetch()`** (R4) con `snapshot_name` explícito — jamás
  urllib directo. Números por `common.to_num` (R3: NA ≠ 0).
- Registrar el paso en `ingest/run_daily.py` dentro de `step()` (R13: si falla, avisa
  pero no tumba la corrida).

## 2. Verificación de trazabilidad (tras la primera corrida)

```bash
sqlite3 data/monitor.sqlite "SELECT url, http_status, sha256, snapshot_path
  FROM sources_log WHERE url LIKE '%<dominio>%' ORDER BY ts DESC LIMIT 5;"
ls data/snapshots/$(date +%F)/ | grep <nombre>
```

Toda fila debe tener sha256 Y snapshot_path no nulo, y el archivo debe existir.

## 3. Test de supuesto

Añadir clase en `tests/test_supuestos_api.py`: qué contrato asume el monitor (campos,
formatos, rangos). El mensaje de fallo debe explicar qué significa que se rompa y qué
hacer — recordando que romperse puede ser buena noticia (R11). Si la fuente puede
morir, el test debe degradar con `skipTest("<fuente> cerró: <plan>")`.

## 4. Plan de sucesión (obligatorio decidir, no opcional)

Responder por escrito en el docstring del módulo:
- Si la fuente muere mañana, ¿qué sobrevive en el repo? (snapshots diarios cuentan.)
- ¿Merece export dedicado versionado (como `data/public/rud.json`)?
- ¿Merece archivo externo en Wayback (paso en daily.yml)?
- ¿Merece snapshot del feed completo (como `feeds/balances/`)?

## 5. Documentación y alta pública

- Fila en la tabla de fuentes del `README.md`: URL, qué aporta, acceso, licencia.
- Si es un feed de prensa: alta en `feeds/registry.json` (ver CONTRIBUTING).
- `docs/ARQUITECTURA.md` si añade tabla al sqlite (y la tabla al `SCHEMA` de
  `ingest/common.py` — nunca renombrar columnas existentes sin migración).
- Si el público la ve: hito tipo `monitor` en `feeds/hitos_monitor.json` («Alta de
  <fuente>: …») — la cronología documenta cómo evoluciona el monitor.

## 6. Revisión y cierre

- Lanzar el agente **archivista** (checklist de archivo) y corregir lo que señale.
- Lanzar el agente **revisor-qa** (suite + sitio si cambió).
- Commit con el porqué editorial («Alta de X: la primera fuente que cubre Y»).
- Anotar en la memoria local cualquier decisión no derivable del código.
