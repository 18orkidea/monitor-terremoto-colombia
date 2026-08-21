#!/usr/bin/env bash
# Construye dist/ — LA definición del artefacto publicado (GitHub Pages lo
# invoca; también sirve para un build local). Sitio + datos públicos + fotos
# ciudadanas. Fuera: código de ingesta, snapshots crudos, sqlite y videos.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf dist
mkdir -p dist dist/data/public dist/data/media

# el sitio vive en la RAÍZ del dominio, no en /site/: la home del dominio debe
# tener contenido indexable, y una URL corta se comparte y se enlaza mejor
# Las imágenes que se comparten se regeneran ANTES de copiar el sitio: no
# pueden depender de que alguien las ejecute a mano. El 21-ago-2026 la portada
# se compartía con 1.415 edificios mientras el monitor sostenía 1.578, y su
# propio texto alternativo ya decía la cifra buena.
python3 deploy/gen_og.py

cp -R site/. dist/
cp -R data/public/. dist/data/public/
# solo imágenes (los videos quedan fuera de git y del deploy; URL remota registrada)
find data/media -maxdepth 1 \( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.webp' \) \
  -size -25M -exec cp {} dist/data/media/ \; 2>/dev/null || true

# Hash para el cache-busting. La sustitución ocurre después de generar las
# fichas: antes solo alcanzaba los HTML de site/ y dejaba las páginas municipales
# con CSS viejo en la caché del navegador.
REV=$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M)
if ! git diff --quiet || ! git diff --cached --quiet; then
  REV="${REV}-dev$(date -u +%H%M%S)"
fi

# fichas municipales: el HTML que hoy pintaría el JavaScript. Se generan aquí y
# no en site/ porque un HTML que cambia entero cada día destruiría el blame; el
# dato ya está versionado en data/public, así que son reconstruibles.
python3 deploy/render_html.py dist

# Todos los HTML que usan assets, también los recién generados dos niveles por
# debajo de la raíz, reciben la misma revisión. Así una interfaz nueva no queda
# mezclada con una hoja de estilos antigua.
find dist -type f -name '*.html' -exec sed -i.bak "s/?v=dev/?v=${REV}/g" {} +
find dist -type f -name '*.html.bak' -delete

# GitHub Pages: sin Jekyll
touch dist/.nojekyll

# Las URLs antiguas (/site/…) siguen vivas: una URL publicada es un compromiso,
# y un archivo que critica a las fuentes que desaparecen no puede romper las
# suyas. GitHub Pages no emite 301, así que se deja redirección de cliente con
# canonical a la URL nueva, que es lo que consolida en el buscador.
mkdir -p dist/site
for f in dist/*.html; do
  n=$(basename "$f")
  [ "$n" = "index.html" ] && destino="/" || destino="/$n"
  cat > "dist/site/$n" <<HTML
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=${destino}">
<link rel="canonical" href="https://brechas.orkidea.eu${destino}">
<meta name="robots" content="noindex, follow">
<title>El monitor se mudó a la raíz del dominio</title>
</head>
<body><p>Esta página ahora vive en <a href="${destino}">brechas.orkidea.eu${destino}</a>.</p></body>
</html>
HTML
done

cp deploy/root/* dist/
# sitemap y llms-full.txt: se derivan de las páginas realmente generadas y de
# los datos del día, para no anunciar nunca una URL que no existe
python3 deploy/render_descubrimiento.py dist

echo "dist listo (rev ${REV}): $(find dist -type f | wc -l | tr -d ' ') ficheros, $(du -sh dist | cut -f1)"
