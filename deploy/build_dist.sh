#!/usr/bin/env bash
# Construye dist/ — LA definición del artefacto publicado (GitHub Pages lo
# invoca; también sirve para un build local). Sitio + datos públicos + fotos
# ciudadanas. Fuera: código de ingesta, snapshots crudos, sqlite y videos.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf dist
mkdir -p dist/site dist/data/public dist/data/media

cp -R site/. dist/site/
cp -R data/public/. dist/data/public/
# solo imágenes (los videos quedan fuera de git y del deploy; URL remota registrada)
find data/media -maxdepth 1 \( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.webp' \) \
  -size -25M -exec cp {} dist/data/media/ \; 2>/dev/null || true

# cache-busting: en el repo los assets van con ?v=dev; el build lo sustituye
# por el hash corto del commit (un solo lugar, nunca más a mano)
REV=$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M)
sed -i.bak "s/?v=dev/?v=${REV}/g" dist/site/*.html && rm -f dist/site/*.html.bak

# GitHub Pages: sin Jekyll
touch dist/.nojekyll

# raíz → /site/ (redirección relativa: vale para brechas.orkidea.eu y para
# 18orkidea.github.io/monitor-…/)
cat > dist/index.html <<'HTML'
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=./site/">
<link rel="canonical" href="https://brechas.orkidea.eu/site/">
<title>Monitor de brechas — Terremoto de Colombia 2026</title>
</head>
<body><a href="./site/">Ir al monitor →</a></body>
</html>
HTML

cp deploy/root/* dist/
HOY=$(date -u +%F)
cat > dist/sitemap.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://brechas.orkidea.eu/site/</loc><changefreq>daily</changefreq><lastmod>$HOY</lastmod><priority>1.0</priority></url>
  <url><loc>https://brechas.orkidea.eu/site/noticias.html</loc><changefreq>daily</changefreq><lastmod>$HOY</lastmod><priority>0.8</priority></url>
  <url><loc>https://brechas.orkidea.eu/site/balances.html</loc><changefreq>daily</changefreq><lastmod>$HOY</lastmod><priority>0.8</priority></url>
  <url><loc>https://brechas.orkidea.eu/site/municipios.html</loc><changefreq>daily</changefreq><lastmod>$HOY</lastmod><priority>0.7</priority></url>
  <url><loc>https://brechas.orkidea.eu/site/rud.html</loc><changefreq>daily</changefreq><lastmod>$HOY</lastmod><priority>0.7</priority></url>
</urlset>
XML

echo "dist listo (rev ${REV}): $(find dist -type f | wc -l | tr -d ' ') ficheros, $(du -sh dist | cut -f1)"
