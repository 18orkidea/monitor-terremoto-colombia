const KEYWORDS = [
  "terremoto", "sismo", "temblor", "movimiento sismico", "movimiento sísmico",
  "edan", "rud", "damnific", "afectad", "vivienda", "herido", "fallecid",
  "san jose del palmar", "san josé del palmar", "emergencia"
];

const EVENT_TERMS = [
  "terremoto", "sismo", "temblor", "movimiento sismico", "movimiento sísmico",
  "san jose del palmar", "san josé del palmar", "chocó", "choco"
];

const DAMAGE_TERMS = [
  "edan", "rud", "damnific", "afectad", "vivienda", "herido", "fallecid",
  "colaps", "averiad", "ayuda humanitaria", "calamidad", "emergencia"
];

const GENERIC_PAGE_TERMS = [
  "consolidado anual de emergencias",
  "emergencias anuales",
  "mapa sitio",
  "zona privada",
  "biblioteca",
  "directorio",
  "normatividad",
  "inicio transparencia"
];

const MUNICIPIOS = [
  ["Armenia", "Quindío"],
  ["Calarcá", "Quindío"],
  ["La Tebaida", "Quindío"],
  ["Montenegro", "Quindío"],
  ["Salento", "Quindío"],
  ["Zarzal", "Valle del Cauca"],
  ["Cartago", "Valle del Cauca"],
  ["Tuluá", "Valle del Cauca"],
  ["Buga", "Valle del Cauca"],
  ["Palmira", "Valle del Cauca"],
  ["Roldanillo", "Valle del Cauca"],
  ["Sevilla", "Valle del Cauca"],
  ["Caicedonia", "Valle del Cauca"],
  ["Jamundí", "Valle del Cauca"],
  ["Dagua", "Valle del Cauca"],
  ["Pereira", "Risaralda"],
  ["Dosquebradas", "Risaralda"],
  ["Santa Rosa de Cabal", "Risaralda"],
  ["Manizales", "Caldas"],
  ["Villamaría", "Caldas"],
  ["Cali", "Valle del Cauca"],
  ["Buenaventura", "Valle del Cauca"],
  ["Quibdó", "Chocó"],
  ["Istmina", "Chocó"],
  ["San José del Palmar", "Chocó"]
];

const OFFICIAL_SOURCES = [
  {
    id: "ungrd-noticias",
    name: "UNGRD - Noticias",
    level: "nacional",
    department: null,
    url: "https://portal.gestiondelriesgo.gov.co/Paginas/Noticias/",
    entrypoints: [
      {
        type: "html",
        role: "listado_sharepoint",
        url: "https://portal.gestiondelriesgo.gov.co/Paginas/Noticias/",
        note: "Listado SharePoint de noticias; los datos útiles están en /Paginas/Noticias/2026/*.aspx."
      },
      {
        type: "html",
        role: "vista_sharepoint",
        url: "https://portal.gestiondelriesgo.gov.co/paginas/forms/allitems.aspx?rootfolder=/paginas/noticias&folderctid=0x0120000d115b77361a2449a3a8cae36d6f2767",
        note: "Vista de biblioteca SharePoint; puede exponer enlaces aunque el RSS de lista falle."
      }
    ]
  },
  {
    id: "snigrd-alertas",
    name: "SNIGRD - Alertas",
    level: "nacional",
    department: null,
    url: "https://www.gestiondelriesgo.gov.co/snigrd/alertas.aspx",
    entrypoints: [
      {
        type: "html",
        role: "alertas",
        url: "https://www.gestiondelriesgo.gov.co/snigrd/alertas.aspx",
        note: "Portal SNIGRD; útil solo si enlaza alertas o páginas con evento específico."
      }
    ]
  },
  {
    id: "gob-valle-riesgo",
    name: "Gobernación del Valle - Gestión del Riesgo",
    level: "gobernacion",
    department: "Valle del Cauca",
    url: "https://www.valledelcauca.gov.co/riesgo/",
    entrypoints: [
      {
        type: "html",
        role: "riesgo",
        url: "https://www.valledelcauca.gov.co/riesgo/",
        note: "Sección de Gestión del Riesgo; puede devolver 502, se considera fuente inestable."
      },
      {
        type: "html",
        role: "noticias",
        url: "https://www.valledelcauca.gov.co/publicaciones/noticias/",
        note: "Listado de publicaciones/noticias del dominio oficial."
      }
    ]
  },
  {
    id: "gob-quindio-udegerd",
    name: "Gobierno del Quindío - UDEGERD",
    level: "gobernacion",
    department: "Quindío",
    url: "https://quindio.gov.co/unidad-departamental-para-la-gestion-del-riesgo-de-desastres-udegerd-quindio",
    entrypoints: [
      {
        type: "html",
        role: "udegerd",
        url: "https://quindio.gov.co/unidad-departamental-para-la-gestion-del-riesgo-de-desastres-udegerd-quindio",
        note: "Página UDEGERD; puede bloquear tráfico automatizado con Cloudflare."
      }
    ]
  },
  {
    id: "gob-caldas-riesgo",
    name: "Gobernación de Caldas - Gestión del Riesgo",
    level: "gobernacion",
    department: "Caldas",
    url: "https://www.caldas.gov.co/component/sppagebuilder/?Itemid=1509&id=108&view=page",
    entrypoints: [
      {
        type: "rss",
        role: "noticias_rss",
        url: "https://www.caldas.gov.co/noticias-gobernacion?format=feed&type=rss",
        note: "RSS Joomla de Noticias Gobernación; es el canal más útil para datos publicados."
      },
      {
        type: "html",
        role: "riesgo",
        url: "https://www.caldas.gov.co/component/sppagebuilder/?Itemid=1509&id=108&view=page",
        note: "Página de Gestión del Riesgo; se usa como respaldo para enlaces internos."
      }
    ]
  },
  {
    id: "gob-risaralda-noticias",
    name: "Gobernación de Risaralda - Noticias",
    level: "gobernacion",
    department: "Risaralda",
    url: "https://www.risaralda.gov.co/publicaciones/noticias/",
    entrypoints: [
      {
        type: "html",
        role: "noticias",
        url: "https://www.risaralda.gov.co/publicaciones/noticias/",
        note: "Portal oficial de noticias; puede bloquear 403 a tráfico automatizado."
      }
    ]
  },
  {
    id: "gob-choco-noticias",
    name: "Gobernación del Chocó - Noticias",
    level: "gobernacion",
    department: "Chocó",
    url: "https://www.choco.gov.co/noticias",
    entrypoints: [
      {
        type: "html",
        role: "spa_noticias",
        url: "https://www.choco.gov.co/noticias",
        note: "Sitio SPA Angular; requiere descubrir API interna desde bundles si el HTML no trae noticias."
      }
    ]
  }
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return cors(new Response(null, { status: 204 }));
    if (url.pathname === "/") return json(await publicFeed(env));
    if (url.pathname === "/oficiales.json" || url.pathname === "/api/oficiales.json") {
      return json(await publicFeed(env));
    }
    if (url.pathname === "/oficiales.rss") return rss(await publicFeed(env));
    if (url.pathname === "/internal/run" && request.method === "POST") {
      const auth = authorize(request, env);
      if (auth) return auth;
      return json(await runCollection(env));
    }
    if (url.pathname === "/internal/extract" && request.method === "POST") {
      const auth = authorize(request, env);
      if (auth) return auth;
      return json(await extractOne(request, env));
    }
    return json({ error: "not_found" }, 404);
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(runCollection(env));
  }
};

async function publicFeed(env) {
  const saved = await env.OFFICIAL_DATA.get("oficiales.json", "json");
  return saved || emptyFeed();
}

function emptyFeed() {
  return {
    generated_at: null,
    items: [],
    sources: OFFICIAL_SOURCES,
    extraction: {
      private: true,
      model: "qwen-vl-ocr-2025-11-20",
      note: "La inferencia IA no es pública; solo se publica el JSON validado."
    }
  };
}

async function runCollection(env) {
  const previous = await publicFeed(env);
  const seen = new Map(
    (previous.items || [])
      .filter((item) => isSpecificEventEvidence(`${item.title} ${item.cita} ${item.text_excerpt}`))
      .map((item) => [item.url, item])
  );
  const candidates = [];
  const sourceAnalysis = [];

  for (const source of OFFICIAL_SOURCES) {
    const discovered = await discoverSource(source);
    candidates.push(...discovered.candidates);
    sourceAnalysis.push(discovered.analysis);
  }

  for (const candidate of candidates.slice(0, 40)) {
    if (seen.has(candidate.url)) continue;
    try {
      const item = await processDocument(candidate, env);
      if (item && item.relacionado_evento && item.evidencia_evento_especifico) seen.set(item.url, item);
    } catch (error) {
      seen.set(candidate.url, {
        ...candidate,
        relacionado_evento: false,
        estado: "error_extraccion",
        error: String(error.message || error),
        captured_at: new Date().toISOString()
      });
    }
  }

  const feed = {
    generated_at: new Date().toISOString(),
    total: [...seen.values()].filter((x) => x.relacionado_evento).length,
    items: [...seen.values()]
      .filter((x) => x.relacionado_evento)
      .sort((a, b) => (b.fecha || b.captured_at || "").localeCompare(a.fecha || a.captured_at || "")),
    sources: OFFICIAL_SOURCES,
    source_analysis: sourceAnalysis,
    extraction: {
      private: true,
      model: env.QWEN_OCR_MODEL || "qwen-vl-ocr-2025-11-20",
      note: "La inferencia IA no se expone; solo se publica el feed estructurado."
    }
  };
  await env.OFFICIAL_DATA.put("oficiales.json", JSON.stringify(feed));
  await env.OFFICIAL_DATA.put("oficiales.rss", renderRss(feed));
  return { ok: true, candidates: candidates.length, total: feed.total, source_analysis: sourceAnalysis };
}

async function discoverSource(source) {
  const candidates = [];
  const entrypoints = source.entrypoints || [{ type: "html", role: "principal", url: source.url }];
  const checks = [];

  for (const entry of entrypoints) {
    const check = { role: entry.role, type: entry.type, url: entry.url, note: entry.note || null };
    try {
      const response = await fetch(entry.url, {
        headers: { "user-agent": "monitor-terremoto-colombia-oficiales/1.0" },
        signal: AbortSignal.timeout(12000)
      });
      check.http_status = response.status;
      check.ok = response.ok;
      if (!response.ok) {
        check.result = "no_usable";
        checks.push(check);
        continue;
      }
      const body = await response.text();
      const parsed = entry.type === "rss"
        ? extractFeedItems(body, entry.url)
        : extractLinks(body, entry.url);
      check.links_found = parsed.length;
      const own = sameHost(source.url);
      const selected = parsed
        .filter((link) => own(link.url))
        .filter((link) => isCandidateLink(link))
        .slice(0, 20)
        .map((link) => ({ ...link, source, discovered_from: entry.url, discovery_role: entry.role }));
      check.candidates = selected.length;
      check.result = selected.length ? "candidate_links" : "no_event_specific_links";
      candidates.push(...selected);
    } catch (error) {
      check.ok = false;
      check.result = "error";
      check.error = String(error.message || error).slice(0, 240);
    }
    checks.push(check);
  }

  return {
    candidates: dedupe(candidates, (x) => x.url),
    analysis: {
      source_id: source.id,
      source_name: source.name,
      department: source.department,
      checks
    }
  };
}

function extractLinks(html, base) {
  const out = [];
  const re = /<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  for (const match of html.matchAll(re)) {
    const href = match[1];
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) continue;
    const title = stripHtml(match[2]).trim() || href;
    try {
      out.push({ url: new URL(href, base).toString(), title });
    } catch {
      // enlace inválido: se ignora
    }
  }
  return dedupe(out, (x) => x.url);
}

function extractFeedItems(xml, base) {
  const out = [];
  const re = /<item\b[\s\S]*?<\/item>/gi;
  for (const item of xml.matchAll(re)) {
    const raw = item[0];
    const title = textBetween(raw, "title") || "";
    const link = textBetween(raw, "link") || "";
    const description = stripHtml(textBetween(raw, "description") || "");
    if (!link) continue;
    try {
      out.push({
        url: new URL(decodeXml(link.trim()), base).toString(),
        title: decodeXml(stripHtml(title)).trim(),
        summary: decodeXml(description).replace(/\s+/g, " ").trim()
      });
    } catch {
      // enlace inválido: se ignora
    }
  }
  return dedupe(out, (x) => x.url);
}

async function extractOne(request, env) {
  const body = await request.json();
  if (!body.url) return { error: "url_required" };
  const candidate = {
    url: body.url,
    title: body.title || body.url,
    source: body.source || {
      id: "manual",
      name: "Documento oficial manual",
      level: "manual",
      department: body.department || null,
      url: body.url
    }
  };
  const item = await processDocument(candidate, env);
  const feed = await publicFeed(env);
  const items = [item, ...(feed.items || []).filter((x) => x.url !== item.url)]
    .filter((x) => x.relacionado_evento);
  const next = { ...feed, generated_at: new Date().toISOString(), total: items.length, items };
  await env.OFFICIAL_DATA.put("oficiales.json", JSON.stringify(next));
  await env.OFFICIAL_DATA.put("oficiales.rss", renderRss(next));
  return item;
}

async function processDocument(candidate, env) {
  const head = await fetch(candidate.url, { method: "GET", headers: { "user-agent": "monitor-terremoto-colombia-oficiales/1.0" } });
  if (!head.ok) throw new Error(`HTTP ${head.status}`);
  const contentType = head.headers.get("content-type") || "";
  const bytes = await head.arrayBuffer();
  const hash = await sha256(bytes);
  let text = "";
  let extractionMethod = "html_text";

  if (isVisualDocument(candidate.url, contentType)) {
    text = await parseWithQwenOcr(candidate.url, env);
    extractionMethod = env.QWEN_OCR_MODEL || "qwen-vl-ocr-2025-11-20";
  } else {
    text = stripHtml(new TextDecoder().decode(bytes)).replace(/\s+/g, " ").trim();
  }

  const structured = structureOfficialText(text, candidate);
  const evidenceText = `${candidate.title} ${candidate.summary || ""} ${text}`;
  return {
    url: candidate.url,
    title: candidate.title,
    source_id: candidate.source.id,
    source_name: candidate.source.name,
    source_level: candidate.source.level,
    official: true,
    content_sha256: hash,
    captured_at: new Date().toISOString(),
    extraction_method: extractionMethod,
    discovered_from: candidate.discovered_from || null,
    discovery_role: candidate.discovery_role || null,
    text_excerpt: text.slice(0, 700),
    evidencia_evento_especifico: isSpecificEventEvidence(evidenceText),
    ...structured
  };
}

async function parseWithQwenOcr(documentUrl, env) {
  if (!env.QWEN_API_KEY) {
    throw new Error("QWEN_API_KEY no configurado");
  }
  const response = await fetch(env.QWEN_API_URL, {
    method: "POST",
    headers: {
      "authorization": `Bearer ${env.QWEN_API_KEY}`,
      "content-type": "application/json"
    },
    body: JSON.stringify({
      model: env.QWEN_OCR_MODEL || "qwen-vl-ocr-2025-11-20",
      input: {
        messages: [
          {
            role: "user",
            content: [
              {
                image: documentUrl,
                min_pixels: 3072,
                max_pixels: 8388608,
                enable_rotate: true
              }
            ]
          }
        ]
      },
      parameters: {
        ocr_options: { task: "document_parsing" }
      }
    })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Qwen OCR HTTP ${response.status}: ${JSON.stringify(data).slice(0, 300)}`);
  return data.output?.choices?.[0]?.message?.content?.[0]?.text || "";
}

function structureOfficialText(text, candidate) {
  const lower = norm(text);
  const municipios = MUNICIPIOS
    .filter(([name]) => lower.includes(norm(name)))
    .map(([name]) => name);
  const departamentos = new Set(
    MUNICIPIOS
      .filter(([name, dept]) => municipios.includes(name) || lower.includes(norm(dept)))
      .map(([, dept]) => dept)
  );
  if (candidate.source.department) departamentos.add(candidate.source.department);

  return {
    relacionado_evento: isSpecificEventEvidence(`${candidate.title} ${candidate.summary || ""} ${text}`),
    fecha: findDate(text),
    departamentos: [...departamentos].sort(),
    municipios: municipios.sort(),
    estado: classify(text),
    cifras: {
      personas_afectadas: findNumber(text, /(personas|habitantes)\s+(afectad|damnificad)/i),
      familias_afectadas: findNumber(text, /familias\s+(afectad|damnificad)/i),
      viviendas_averiadas: findNumber(text, /viviendas?\s+(averiad|afectad)/i),
      viviendas_destruidas: findNumber(text, /viviendas?\s+(destruid|colapsad)/i),
      heridos: findNumber(text, /heridos?/i),
      fallecidos: findNumber(text, /(fallecid|muert)/i)
    },
    requiere_revision_humana: true,
    confianza: confidence(text),
    cita: findQuote(text)
  };
}

function classify(text) {
  const n = norm(text);
  if (n.includes("edan") || n.includes("rud") || n.includes("damnific")) return "oficial_posible_edan_rud";
  if (n.includes("vivienda") || n.includes("afectad") || n.includes("herido") || n.includes("fallecid")) return "oficial_con_posibles_cifras";
  if (n.includes("sismo") || n.includes("terremoto") || n.includes("temblor")) return "oficial_menciona_evento";
  return "oficial_no_relacionado";
}

function confidence(text) {
  const hasOfficialDamage = /edan|rud|damnific|viviendas?|heridos?|fallecid/i.test(text);
  const hasNumber = /\d/.test(text);
  if (hasOfficialDamage && hasNumber && isSpecificEventEvidence(text)) return "media";
  if (isSpecificEventEvidence(text)) return "baja";
  return "ninguna";
}

function findQuote(text) {
  const sentences = text.split(/(?<=[.!?])\s+/).filter((s) => relevant(s));
  return (sentences[0] || text.slice(0, 240)).slice(0, 280);
}

function findDate(text) {
  const m = text.match(/\b(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(20\d{2})\b/i);
  if (!m) return null;
  const months = {
    enero: "01", febrero: "02", marzo: "03", abril: "04", mayo: "05", junio: "06",
    julio: "07", agosto: "08", septiembre: "09", octubre: "10", noviembre: "11", diciembre: "12"
  };
  const mm = months[norm(m[2])];
  return mm ? `${m[3]}-${mm}-${String(Number(m[1])).padStart(2, "0")}` : null;
}

function findNumber(text, pattern) {
  const idx = text.search(pattern);
  if (idx < 0) return null;
  const chunk = text.slice(Math.max(0, idx - 80), idx + 120);
  const m = chunk.match(/\b\d{1,3}(?:[.,]\d{3})*|\b\d+\b/);
  return m ? Number(m[0].replace(/[.,]/g, "")) : null;
}

function relevant(text) {
  const n = norm(text);
  return KEYWORDS.some((kw) => n.includes(norm(kw)));
}

function isCandidateLink(link) {
  const text = `${link.title || ""} ${link.summary || ""} ${link.url || ""}`;
  if (isGenericPage(text)) return false;
  return hasEventTerm(text) && (hasDamageTerm(text) || hasImpactedPlace(text) || hasEventDate(text));
}

function isSpecificEventEvidence(text) {
  if (isGenericPage(text)) return false;
  return hasEventTerm(text) && (hasDamageTerm(text) || hasImpactedPlace(text) || hasEventDate(text));
}

function hasEventTerm(text) {
  const n = norm(text);
  return EVENT_TERMS.some((term) => n.includes(norm(term)));
}

function hasDamageTerm(text) {
  const n = norm(text);
  return DAMAGE_TERMS.some((term) => n.includes(norm(term)));
}

function hasImpactedPlace(text) {
  const n = norm(text);
  return MUNICIPIOS.some(([name, dept]) => n.includes(norm(name)) || n.includes(norm(dept)));
}

function hasEventDate(text) {
  const n = norm(text);
  return /10\s+de\s+agosto\s+de\s+2026|agosto\s+de\s+2026|2026-08|10-ago-2026|10\/08\/2026/.test(n);
}

function isGenericPage(text) {
  const n = norm(text);
  return GENERIC_PAGE_TERMS.some((term) => n.includes(norm(term)));
}

function isVisualDocument(url, contentType) {
  return /application\/pdf|image\//i.test(contentType) || /\.(pdf|png|jpe?g|webp)(\?|$)/i.test(url);
}

function sameHost(base) {
  const host = new URL(base).host.replace(/^www\./, "");
  return (url) => new URL(url).host.replace(/^www\./, "") === host;
}

function dedupe(items, keyFn) {
  const seen = new Set();
  return items.filter((item) => {
    const key = keyFn(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function textBetween(xml, tag) {
  const match = xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return match ? match[1].replace(/^<!\[CDATA\[/, "").replace(/\]\]>$/, "") : "";
}

function decodeXml(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function norm(s) {
  return String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

async function sha256(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function authorize(request, env) {
  if (!env.INTERNAL_TOKEN) {
    return json({
      error: "internal_token_not_configured",
      detail: "Configure `wrangler secret put INTERNAL_TOKEN`."
    }, 503);
  }
  const header = request.headers.get("authorization") || "";
  const token = header.replace(/^Bearer\s+/i, "");
  return token === env.INTERNAL_TOKEN ? null : json({ error: "unauthorized" }, 401);
}

function json(value, status = 200) {
  return cors(new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": status === 200 ? "public, max-age=300" : "no-store"
    }
  }));
}

function rss(feed) {
  return cors(new Response(renderRss(feed), {
    headers: {
      "content-type": "application/rss+xml; charset=utf-8",
      "cache-control": "public, max-age=300"
    }
  }));
}

function renderRss(feed) {
  const items = (feed.items || []).slice(0, 80).map((item) => `
    <item>
      <title>${xml(item.title || item.url)}</title>
      <link>${xml(item.url)}</link>
      <guid>${xml(item.content_sha256 || item.url)}</guid>
      <description>${xml(`${item.source_name || ""} · ${item.estado || ""} · ${item.cita || ""}`)}</description>
    </item>`).join("");
  return `<?xml version="1.0" encoding="UTF-8"?>
  <rss version="2.0"><channel>
    <title>Reportes oficiales estructurados - Terremoto Colombia</title>
    <link>https://github.com/JP-infoRes/monitor-terremoto-colombia</link>
    <description>Feed generado por Worker interno con Qwen OCR; solo datos estructurados públicos.</description>
    ${items}
  </channel></rss>`;
}

function xml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function cors(response) {
  response.headers.set("access-control-allow-origin", "*");
  response.headers.set("access-control-allow-methods", "GET,POST,OPTIONS");
  response.headers.set("access-control-allow-headers", "content-type,authorization");
  return response;
}
