const KEYWORDS = [
  "terremoto", "sismo", "temblor", "movimiento sismico", "movimiento sísmico",
  "edan", "rud", "damnific", "afectad", "vivienda", "herido", "fallecid",
  "san jose del palmar", "san josé del palmar", "emergencia"
];

const EVENT_TERMS = [
  "terremoto", "sismo", "temblor", "movimiento sismico", "movimiento sísmico"
];

/* Topónimos que también valen como señal de evento. Van aparte porque exigen
   límite de palabra: con includes(), «chocó» hacía que «fábrica de chocolate»
   contara como evidencia del terremoto (R10). Los términos de arriba sí se
   buscan por contención, a propósito: así «sismos» y «temblores» cuentan. */
const EVENT_PLACES = [
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

/* Países de OTROS eventos sísmicos, buscados por CONTENCIÓN a propósito (al
   revés que EVENT_PLACES): así «chilena», «peruano» o «japonés» también cuentan
   para descartar el documento. Un falso positivo aquí solo descarta un
   candidato, no publica una cifra. */
const UNRELATED_EVENT_TERMS = [
  "indonesia", "peru", "mexico", "chile", "japon", "japón", "rusia", "turquia", "turquía"
];

const FIRECRAWL_DAILY_QUERY_TEMPLATES = [
  {
    label: "UNGRD SGC balance oficial por fecha",
    query: "UNGRD SGC terremoto Colombia {date_dmy} fallecidos heridos desaparecidos rescatados balance oficial"
  },
  {
    label: "Gobernacion Alcaldia afectacion por fecha",
    query: "Gobernación Alcaldía terremoto Colombia {date_dmy} personas familias viviendas municipios departamentos afectados"
  },
  {
    label: "Presidencia reporte oficial por fecha",
    query: "Presidencia Colombia UNGRD SGC terremoto {date_dmy} reporte oficial afectados"
  }
];

/* Versión del código que produce cada feed: sin esto no hay forma de saber qué
   criterios generaron un ítem archivado (deploy manual, KV fuera de git). Subir
   al cambiar cualquier regla de interpretación. */
const WORKER_VERSION = "2026-08-17-r10";

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
  // alias del pipeline (municipios.py lo lista como topónimo): con límite de
  // palabra, «Dos Quebradas» no casa dentro de «Dosquebradas»
  ["Dos Quebradas", "Risaralda"],
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
    id: "firecrawl-busqueda-diaria",
    name: "Firecrawl - búsqueda diaria por fecha",
    level: "busqueda_web_temporal",
    department: null,
    url: "https://api.firecrawl.dev/v2/search",
    entrypoints: [
      {
        type: "firecrawl_search",
        role: "busqueda_diaria_fecha",
        url: "https://api.firecrawl.dev/v2/search",
        note: "Search por fecha variable orientado a UNGRD, SGC, Gobernación, Presidencia y Alcaldía; scrapea las 3 primeras URLs priorizadas.",
        queries: FIRECRAWL_DAILY_QUERY_TEMPLATES,
        limit: 10,
        scrape_limit: 3
      }
    ]
  },
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
      const body = await safeJson(request);
      return json(await runCollection(env, { date: body?.date }));
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

async function runCollection(env, options = {}) {
  const runDate = normalizeRunDate(options.date) || todayInBogota();
  const previous = await publicFeed(env);
  const seen = new Map(
    (previous.items || [])
      .filter((item) => item.source_id !== "ungrd-firecrawl-multicanal")
      .filter((item) => item.source_id !== "firecrawl-busqueda-diaria" || (item.search_date && item.search_date !== runDate))
      .filter((item) => isSpecificEventEvidence(`${item.title} ${item.cita} ${item.text_excerpt}`))
      .map((item) => [itemKey(item), item])
  );
  const candidates = [];
  const sourceAnalysis = [];

  for (const source of OFFICIAL_SOURCES) {
    const discovered = await discoverSource(source, env, runDate);
    candidates.push(...discovered.candidates);
    sourceAnalysis.push(discovered.analysis);
  }

  for (const candidate of candidates.slice(0, 40)) {
    const key = itemKey(candidate);
    if (seen.has(key)) continue;
    try {
      const item = await processDocument(candidate, env);
      if (item && item.relacionado_evento && item.evidencia_evento_especifico) seen.set(itemKey(item), item);
    } catch (error) {
      seen.set(key, {
        ...candidate,
        snapshot_id: key,
        relacionado_evento: false,
        estado: "error_extraccion",
        error: String(error.message || error),
        captured_at: new Date().toISOString()
      });
    }
  }

  const feed = {
    generated_at: new Date().toISOString(),
    run_date: runDate,
    total: [...seen.values()].filter((x) => x.relacionado_evento).length,
    items: [...seen.values()]
      .filter((x) => x.relacionado_evento)
      .sort((a, b) => (b.fecha || b.captured_at || "").localeCompare(a.fecha || a.captured_at || "")),
    sources: OFFICIAL_SOURCES,
    source_analysis: sourceAnalysis,
    extraction: {
      private: true,
      model: env.QWEN_OCR_MODEL || "qwen-vl-ocr-2025-11-20",
      version: WORKER_VERSION,
      criterios: {
        lugares: "limite_palabra_sin_enlaces",
        cifras: "texto_sin_enlaces"
      },
      note: "La inferencia IA no se expone; solo se publica el feed estructurado."
    }
  };
  await env.OFFICIAL_DATA.put("oficiales.json", JSON.stringify(feed));
  await env.OFFICIAL_DATA.put("oficiales.rss", renderRss(feed));
  return { ok: true, run_date: runDate, candidates: candidates.length, total: feed.total, source_analysis: sourceAnalysis };
}

async function discoverSource(source, env, runDate) {
  const candidates = [];
  const entrypoints = source.entrypoints || [{ type: "html", role: "principal", url: source.url }];
  const checks = [];

  for (const entry of entrypoints) {
    const check = { role: entry.role, type: entry.type, url: entry.url, note: entry.note || null };
    try {
      if (entry.type === "firecrawl_search") {
        const selected = await discoverWithFirecrawl(entry, source, env, runDate);
        check.ok = selected.result !== "missing_secret";
        check.http_status = selected.result === "missing_secret" ? null : 200;
        check.links_found = selected.links_found;
        check.candidates = selected.candidates.length;
        check.credits_used = selected.credits_used;
        check.jobs = selected.jobs;
        check.result = selected.result;
        candidates.push(...selected.candidates);
        checks.push(check);
        continue;
      }
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

async function discoverWithFirecrawl(entry, source, env, runDate) {
  if (!env.FIRECRAWL_API_KEY) {
    return {
      candidates: [],
      links_found: 0,
      credits_used: 0,
      jobs: [],
      result: "missing_secret"
    };
  }

  const candidates = [];
  const jobs = [];
  let credits = 0;
  const topResults = [];
  const dateDmy = toDmy(runDate);

  for (const q of entry.queries || []) {
    const query = q.query.replace("{date_dmy}", dateDmy).replace("{date_iso}", runDate);
    const response = await fetch(env.FIRECRAWL_API_URL || "https://api.firecrawl.dev/v2/search", {
      method: "POST",
      headers: {
        "authorization": `Bearer ${env.FIRECRAWL_API_KEY}`,
        "content-type": "application/json"
      },
      body: JSON.stringify({
        query,
        limit: entry.limit || 4,
        sources: ["web"],
        includeDomains: q.includeDomains || undefined,
        country: "CO",
        timeout: 45000,
        ignoreInvalidURLs: true,
        scrapeOptions: {
          formats: [],
          onlyMainContent: true,
          maxAge: 172800000,
          parsers: ["pdf"],
          timeout: 30000
        }
      })
    });
    const data = await response.json().catch(() => ({}));
    jobs.push({
      label: q.label,
      ok: response.ok && data.success !== false,
      http_status: response.status,
      id: data.id || null,
      query,
      results: data.data?.web?.length || 0,
      warning: data.warning || null
    });
    credits += data.creditsUsed || 0;
    if (!response.ok || data.success === false) continue;

    for (const result of data.data?.web || []) {
      topResults.push({ ...result, query_label: q.label, query, firecrawl_job_id: data.id || null });
    }
  }

  const rankedResults = dedupe(topResults, (x) => x.url)
    .sort((a, b) => scoreSearchResult(b) - scoreSearchResult(a));

  for (const result of rankedResults.slice(0, entry.scrape_limit || 3)) {
    const scraped = await scrapeWithFirecrawl(result.url, env);
    credits += scraped.credits_used || 0;
    const text = `${result.title || ""} ${result.description || ""} ${scraped.text || ""}`;
    const sourceLevel = classifySourceLevel(result.url, text);
    const candidateSource = {
      ...source,
      level: sourceLevel,
      name: sourceLevel === "oficial_comunicacion"
        ? "Firecrawl - fuente oficial encontrada"
        : sourceLevel === "oficial_institucional"
          ? "Firecrawl - fuente institucional oficial encontrada"
        : sourceLevel === "temporal_prensa"
          ? "Firecrawl - prensa temporal encontrada"
          : source.name
    };
    candidates.push({
      url: result.url,
      title: result.title || scraped.title || result.url,
      summary: result.description || scraped.description || "",
      prefetched_text: scraped.text || result.description || result.title || "",
      source: candidateSource,
      publisher: inferPublisher(result.url, result, scraped),
      is_liveblog: isLiveblog(result.url, text),
      original_source_level: sourceLevel,
      search_date: runDate,
      search_query: result.query,
      discovered_from: `firecrawl:${result.query_label}`,
      discovery_role: entry.role,
      extraction_method: scraped.ok ? "firecrawl_search_then_scrape" : "firecrawl_search_snippet",
      published_time: scraped.publishedTime || null,
      firecrawl_job_id: result.firecrawl_job_id,
      firecrawl_scrape_status: scraped.status,
      firecrawl_scrape_error: scraped.error || null,
      temporal_source_policy: sourceLevel === "oficial_comunicacion"
        ? "comunicacion_oficial_no_edan"
        : sourceLevel === "oficial_institucional"
          ? "institucion_oficial_no_edan"
        : "fuente_temporal_no_oficial_requiere_verificacion"
    });
  }

  return {
    candidates: dedupe(candidates, (x) => x.url),
    links_found: jobs.reduce((sum, job) => sum + job.results, 0),
    credits_used: credits,
    jobs,
    result: candidates.length ? "candidate_links" : "no_event_specific_links"
  };
}

async function scrapeWithFirecrawl(url, env) {
  const response = await fetch(env.FIRECRAWL_SCRAPE_API_URL || "https://api.firecrawl.dev/v2/scrape", {
    method: "POST",
    headers: {
      "authorization": `Bearer ${env.FIRECRAWL_API_KEY}`,
      "content-type": "application/json"
    },
    body: JSON.stringify({
      url,
      formats: ["markdown"],
      onlyMainContent: true,
      onlyCleanContent: true,
      removeBase64Images: true,
      blockAds: true,
      maxAge: 172800000,
      parsers: ["pdf"],
      timeout: 30000
    })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    return {
      ok: false,
      status: response.status,
      credits_used: data.creditsUsed || 0,
      text: "",
      error: data.error || data.message || `HTTP ${response.status}`
    };
  }
  const payload = data.data || data;
  return {
    ok: true,
    status: response.status,
    credits_used: data.creditsUsed || 0,
    title: payload.metadata?.title || payload.title || "",
    siteName: payload.metadata?.siteName || payload.metadata?.["og:site_name"] || "",
    description: payload.metadata?.description || "",
    // Fecha de PUBLICACIÓN declarada por el propio medio. Es el dato de fecha
    // más fiable que pasa por aquí y se estaba descartando: sin él, la única
    // fecha del ítem era `search_date`, que es la que se le pidió al buscador
    // y no dice nada de cuándo se publicó el balance ni de qué corte habla.
    publishedTime: payload.metadata?.publishedTime ||
      payload.metadata?.["article:published_time"] ||
      payload.metadata?.["og:published_time"] ||
      payload.metadata?.datePublished || null,
    text: payload.markdown || payload.content || payload.text || ""
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
  let bytes;
  let contentType = "";
  let text = "";
  let extractionMethod = candidate.extraction_method || "html_text";

  if (candidate.prefetched_text) {
    text = candidate.prefetched_text;
    bytes = new TextEncoder().encode(text).buffer;
  } else {
    const head = await fetch(candidate.url, { method: "GET", headers: { "user-agent": "monitor-terremoto-colombia-oficiales/1.0" } });
    if (!head.ok) throw new Error(`HTTP ${head.status}`);
    contentType = head.headers.get("content-type") || "";
    bytes = await head.arrayBuffer();
  }
  const hash = await sha256(bytes);

  if (!candidate.prefetched_text && isVisualDocument(candidate.url, contentType)) {
    text = await parseWithQwenOcr(candidate.url, env);
    extractionMethod = env.QWEN_OCR_MODEL || "qwen-vl-ocr-2025-11-20";
  } else if (!candidate.prefetched_text) {
    text = stripHtml(new TextDecoder().decode(bytes)).replace(/\s+/g, " ").trim();
  }

  const structured = structureOfficialText(text, candidate);
  const evidenceText = `${candidate.title} ${candidate.summary || ""} ${text}`;
  return {
    url: candidate.url,
    publication_url: candidate.url,
    title: candidate.title,
    snapshot_id: itemKey(candidate),
    search_date: candidate.search_date || null,
    search_query: candidate.search_query || null,
    publisher: candidate.publisher || inferPublisher(candidate.url, candidate, {}),
    reported_data_source: inferReportedDataSource(`${candidate.title} ${candidate.summary || ""} ${text}`),
    is_liveblog: candidate.is_liveblog || isLiveblog(candidate.url, evidenceText),
    historical_reliability: (candidate.is_liveblog || isLiveblog(candidate.url, evidenceText)) ? "baja" : "media",
    source_id: candidate.source.id,
    source_name: candidate.source.name,
    source_level: candidate.source.level,
    official: candidate.source.level === "oficial_comunicacion" ||
      candidate.source.level === "oficial_institucional" ||
      candidate.source.level === "nacional" ||
      candidate.source.level === "gobernacion" ||
      candidate.source.level === "gobierno_local_por_verificar",
    temporal_source_policy: candidate.temporal_source_policy || null,
    original_source_level: candidate.original_source_level || candidate.source.level,
    content_sha256: hash,
    captured_at: new Date().toISOString(),
    extraction_method: extractionMethod,
    firecrawl_job_id: candidate.firecrawl_job_id || null,
    firecrawl_scrape_status: candidate.firecrawl_scrape_status || null,
    firecrawl_scrape_error: candidate.firecrawl_scrape_error || null,
    discovered_from: candidate.discovered_from || null,
    discovery_role: candidate.discovery_role || null,
    // 700 caracteres no bastaban ni para fechar ni para extraer: la fecha de
    // corte del boletín suele ir en el cuerpo («con corte a las 6:00 a. m.
    // del 18 de agosto»), y lo que se archivaba del boletín de la UNGRD eran
    // 145 caracteres truncados. El texto es la evidencia, no un adorno.
    text_excerpt: text.slice(0, 4000),
    publicado_en: candidate.published_time || null,
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
  // Un solo texto limpio para todo lo que interpreta: las URLs no solo
  // atribuían municipios, también ofrecían números — «mapa-900x601.jpg» daba
  // «900 municipios afectados», y esa cifra SÍ se pinta (site/balances.js la
  // enfrenta al RUD). La cita y el text_excerpt siguen sobre el crudo: son
  // literales de archivo (R3).
  const limpio = sinEnlaces(text);
  const lower = norm(limpio);
  const municipios = MUNICIPIOS
    .filter(([name]) => mentionsPlace(lower, name))
    .map(([name]) => name);
  const departamentos = new Set(
    MUNICIPIOS
      .filter(([name, dept]) => municipios.includes(name) || mentionsPlace(lower, dept))
      .map(([, dept]) => dept)
  );
  if (candidate.source.department) departamentos.add(candidate.source.department);

  const vigilada = extraerCifrasVigiladas(limpio, text);
  return {
    relacionado_evento: isSpecificEventEvidence(`${candidate.title} ${candidate.summary || ""} ${limpio}`),
    fecha: findDate(limpio),
    fecha_corte: findCutoffDate(limpio),
    departamentos: [...departamentos].sort(),
    municipios: municipios.sort(),
    estado: classify(limpio),
    cifras: vigilada.cifras,
    extraccion_intentos: vigilada.extraccion_intentos,
    extraccion_descartada: vigilada.extraccion_descartada,
    requiere_revision_humana: true,
    confianza: confidence(limpio),
    cita: findQuote(text),
    // sello del criterio de atribución: los ítems SIN este campo se etiquetaron
    // con el `includes()` anterior al 17-ago-2026 (podían atribuir un municipio
    // por el nombre de archivo de una imagen). El KV reusa ítems viejos tal
    // cual, así que los feeds archivados mezclan ambos criterios: sin el sello
    // no habría forma de distinguirlos dentro de veinte años.
    atribucion_lugares: "limite_palabra_sin_enlaces",
    // sello del criterio de EXTRACCIÓN, por el mismo motivo que el de lugares:
    // hasta la v2 (21-ago-2026) las reglas perdían las víctimas en femenino
    // («4.548 heridas») y confundían «N personas fallecidas» con afectadas.
    // Los ítems archivados antes conservan esas cifras: no se reescriben.
    cifras_desde: "texto_sin_enlaces_v2",
    extraccion_version: 2
  };
}

/* Vigilante de extracción (decisión de 21-ago-2026). Las cifras salen de
   reglas de texto, y una regla puede equivocarse de casilla: el boletín de la
   UNGRD del 18-ago dejó «304 personas fallecidas» guardado como 304 personas
   AFECTADAS, y con eso la portada publicó 304 afectados donde la víspera
   declaraba 186.016.

   Antes de publicar nada se comprueban relaciones que no pueden romperse sin
   que la extracción esté mal. Si se rompen, se REINTENTA sobre el texto crudo
   —otra entrada, no la misma dos veces, que daría el mismo resultado—; si
   vuelve a fallar, se desestima la cifra culpable y se conserva el resto del
   balance, que suele estar bien. Nada se borra en silencio: el ítem viaja con
   el registro de sus intentos, y el sitio conserva el último máximo bueno. */
const RELACIONES_CIFRAS = [
  ["personas_afectadas", "familias_afectadas"],
  ["personas_afectadas", "fallecidos"],
  ["personas_afectadas", "heridos"],
  ["personas_afectadas", "desaparecidos"]
];

function incoherenciasDeCifras(cifras) {
  const rotas = [];
  for (const [mayor, menor] of RELACIONES_CIFRAS) {
    const a = cifras[mayor], b = cifras[menor];
    if (a != null && b != null && a < b) rotas.push(`${mayor} < ${menor}`);
  }
  return rotas;
}

function extraerCifras(texto) {
  return {
    departamentos_afectados: findMetricNumber(texto, "departamentos"),
    municipios_afectados: findMetricNumber(texto, "municipios"),
    personas_afectadas: findMetricNumber(texto, "personas"),
    familias_afectadas: findMetricNumber(texto, "familias"),
    viviendas_averiadas: findMetricNumber(texto, "viviendas_averiadas"),
    viviendas_destruidas: findMetricNumber(texto, "viviendas_destruidas"),
    heridos: findMetricNumber(texto, "heridos"),
    fallecidos: findMetricNumber(texto, "fallecidos"),
    desaparecidos: findMetricNumber(texto, "desaparecidos"),
    rescatados: findMetricNumber(texto, "rescatados")
  };
}

function extraerCifrasVigiladas(limpio, crudo) {
  const intentos = [];
  const primera = extraerCifras(limpio);
  const rotas = incoherenciasDeCifras(primera);
  intentos.push({ intento: 1, sobre: "texto_sin_enlaces", incoherencias: rotas });
  if (!rotas.length) {
    return { cifras: primera, extraccion_intentos: intentos,
             extraccion_descartada: null };
  }
  const segunda = extraerCifras(crudo);
  const rotasSegunda = incoherenciasDeCifras(segunda);
  intentos.push({ intento: 2, sobre: "texto_crudo", incoherencias: rotasSegunda });
  if (!rotasSegunda.length) {
    return { cifras: segunda, extraccion_intentos: intentos,
             extraccion_descartada: null };
  }
  const culpables = [...new Set(
    rotas.concat(rotasSegunda).map((r) => r.split(" < ")[0]))];
  const cifras = { ...primera };
  for (const k of culpables) cifras[k] = null;
  return { cifras, extraccion_intentos: intentos,
           extraccion_descartada: { cifras: culpables, motivo: rotasSegunda } };
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

/* Fecha del CORTE del que habla el balance, que no es la fecha en que se
   publicó ni el día en que lo encontramos. Es la pieza que convierte una lista
   de capturas en una serie temporal: sin ella, el mismo artículo de El Tiempo
   figuraba como el balance del 12, el 14, el 15 y el 18 de agosto, según el
   día que se le pidiera al buscador.

   La trampa que hay que esquivar es la fecha del propio terremoto: casi toda
   noticia dice «el sismo del 10 de agosto», y aceptarla convertiría cualquier
   artículo en un corte del día del desastre. Es la misma trampa que R10 con
   los topónimos —una coincidencia de texto que parece un dato— y se cierra
   igual: mirando el contexto y no solo la coincidencia. */
const MESES_ES = {
  enero: "01", febrero: "02", marzo: "03", abril: "04", mayo: "05",
  junio: "06", julio: "07", agosto: "08", septiembre: "09", octubre: "10",
  noviembre: "11", diciembre: "12"
};
const HABLA_DE_CORTE = /balance|corte|reporte|consolidado|actualiz|cifras|informe/i;
const HABLA_DEL_EVENTO = /(sismo|terremoto|temblor|magnitud|epicentro)[^.]{0,24}$/i;

function findCutoffDate(text, anioPorDefecto = "2026") {
  const re = new RegExp(
    `\\b(\\d{1,2})\\s+de\\s+(${Object.keys(MESES_ES).join("|")})` +
    `(?:\\s+de\\s+(20\\d{2}))?\\b`, "gi");
  for (const m of text.matchAll(re)) {
    const antes = text.slice(Math.max(0, m.index - 70), m.index);
    // «el terremoto del 10 de agosto» no fecha ningún balance
    if (HABLA_DEL_EVENTO.test(antes)) continue;
    const cerca = antes + m[0] + text.slice(m.index + m[0].length, m.index + m[0].length + 45);
    if (!HABLA_DE_CORTE.test(cerca)) continue;
    const dia = String(m[1]).padStart(2, "0");
    return `${m[3] || anioPorDefecto}-${MESES_ES[m[2].toLowerCase()]}-${dia}`;
  }
  return null;
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

/* La UNGRD publica así sus boletines: «Población: 304 personas fallecidas,
   4.548 heridas, 426 desaparecidas y 356 personas rescatadas». Tres trampas en
   una sola línea, y las tres costaban cifras el 18-ago-2026:
   - el sustantivo va DELANTE del adjetivo («N personas fallecidas»), así que
     un patrón `N\s+fallecid` no casa nada;
   - el género es femenino, y `heridos?` no encuentra «heridas»;
   - en el segundo y el tercer término se elide «personas».
   Se prueban en este orden para que la forma más específica gane. */
function victimas(number, raiz) {
  return [
    new RegExp(`${number}\\s+personas?\\s+${raiz}[oa]s?\\b`, "i"),
    new RegExp(`${number}\\s+${raiz}[oa]s?\\b`, "i"),
    new RegExp(`${raiz}[oa]s?\\s*[:;\\-–]\\s*${number}`, "i")
  ];
}

function findMetricNumber(text, metric) {
  const number = "(\\d{1,3}(?:[.,]\\d{3})*|\\d+)";
  const patterns = {
    departamentos: [
      new RegExp(`${number}\\s+departamentos?\\s+afectad`, "i"),
      new RegExp(`departamentos?\\s+afectad\\w*\\D{0,30}${number}`, "i")
    ],
    municipios: [
      new RegExp(`${number}\\s+municipios?\\s+afectad`, "i"),
      new RegExp(`municipios?\\s+afectad\\w*\\D{0,30}${number}`, "i")
    ],
    personas: [
      new RegExp(`${number}\\s+(personas|habitantes)\\s+(afectad|damnificad)`, "i"),
      new RegExp(`(personas|habitantes)\\s+(afectad|damnificad)\\w*\\D{0,40}${number}`, "i"),
      // el laxo va el último y NO puede llevarse una víctima detrás: el
      // boletín del 18-ago-2026 decía «304 personas fallecidas» y esto lo
      // guardaba como 304 personas AFECTADAS, que eran los muertos
      new RegExp(`${number}\\s+(personas|habitantes)(?!\\s+(?:fallecid|muert|herid|desaparecid|rescatad|damnificad))(?:\\W|$)`, "i")
    ],
    familias: [
      new RegExp(`${number}\\s+familias?\\s+(afectad|damnificad)?`, "i"),
      new RegExp(`familias?\\s+(afectad|damnificad)\\w*\\D{0,40}${number}`, "i")
    ],
    viviendas_averiadas: [
      new RegExp(`${number}\\s+viviendas?\\s+(averiad|afectad)`, "i"),
      new RegExp(`viviendas?\\s+(averiad|afectad)\\w*\\D{0,40}${number}`, "i"),
      // «134.342 viviendas averiadas, 29.554 destruidas»: en el segundo
      // término se elide «viviendas», así que se ancla a la mención anterior
      // dentro de la misma frase en vez de aceptar un adjetivo suelto
      new RegExp(`viviendas?[^.]{0,80}?${number}\\s+(averiad|afectad)[oa]s?\\b`, "i")
    ],
    viviendas_destruidas: [
      new RegExp(`${number}\\s+viviendas?\\s+(destruid|colapsad)`, "i"),
      new RegExp(`viviendas?\\s+(destruid|colapsad)\\w*\\D{0,40}${number}`, "i"),
      new RegExp(`viviendas?[^.]{0,80}?${number}\\s+(destruid|colapsad)[oa]s?\\b`, "i")
    ],
    heridos: victimas(number, "herid"),
    fallecidos: victimas(number, "(?:fallecid|muert)"),
    desaparecidos: victimas(number, "desaparecid"),
    rescatados: victimas(number, "rescatad")
  };
  for (const pattern of patterns[metric] || []) {
    const match = text.match(pattern);
    if (!match) continue;
    const value = match.slice(1).find((part) => part && /^\d/.test(part)) ||
      match[0].match(/\d{1,3}(?:[.,]\d{3})*|\d+/)?.[0];
    if (value) return Number(value.replace(/[.,]/g, ""));
  }
  return null;
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

function scoreSearchResult(result) {
  const text = norm(`${result.title || ""} ${result.description || ""} ${result.url || ""}`);
  const wanted = [
    "fallecid", "muert", "herid", "desaparecid", "rescatad",
    "personas afectad", "familias afectad", "viviendas",
    "municipios afectad", "departamentos afectad", "balance", "reporte"
  ];
  let score = wanted.reduce((sum, term) => sum + (text.includes(norm(term)) ? 2 : 0), 0);
  if (/\d/.test(text)) score += 2;
  if (hasColombiaContext(text)) score += 3;
  if (isOfficialUngrChannel(result.url, text) || isOfficialInstitutionChannel(result.url, text)) score += 4;
  if (classifySourceLevel(result.url, text) === "temporal_prensa") score += 1;
  if (hasUnrelatedEventContext(text)) score -= 20;
  if (isLiveblog(result.url, text)) score -= 6;
  return score;
}

function isLiveblog(url, text) {
  const n = norm(`${url || ""} ${text || ""}`);
  return /\b(en vivo|directo|live[-_\s]?news|ultima hora|última hora|minuto a minuto|liveblog)\b/i.test(n);
}

function isOfficialUngrChannel(url, text) {
  const u = String(url || "").toLowerCase();
  const n = norm(text);
  if (u.includes("portal.gestiondelriesgo.gov.co") || u.includes("gestiondelriesgo.gov.co")) return true;
  if (u.includes("facebook.com/gestionungrd")) return true;
  if (u.includes("instagram.com/ungrd_oficial")) return true;
  if (u.includes("linkedin.com/company/ungrd")) return true;
  if (u.includes("youtube.com") || u.includes("youtu.be")) {
    return /uploaded by.{0,80}(ungrd|unidad nacional para la gestion del riesgo)/i.test(n) ||
      /channel\/[^)\s]+ungrd|@ungrd/i.test(u);
  }
  return false;
}

function classifySourceLevel(url, text) {
  const u = String(url || "").toLowerCase();
  const n = norm(text);
  if (
    u.includes("gestiondelriesgo.gov.co") ||
    u.includes("facebook.com/gestionungrd") ||
    u.includes("instagram.com/ungrd_oficial") ||
    u.includes("linkedin.com/company/ungrd") ||
    isOfficialUngrChannel(url, text)
  ) {
    return "oficial_comunicacion";
  }
  if (isOfficialInstitutionChannel(url, text)) {
    return "oficial_institucional";
  }
  if (
    u.includes(".gov.co") ||
    u.includes("gov.co/")
  ) {
    return "gobierno_local_por_verificar";
  }
  if (
    /\b(eltiempo|elespectador|semana|larepublica|bluradio|rcnradio|caracol|wradio|infobae|france24|elpais|qhubo|diariooccidente|cronicadelquindio|eldiario|latarde|choco7dias)\b/i.test(u)
  ) {
    return "temporal_prensa";
  }
  return "busqueda_web_temporal";
}

function isOfficialInstitutionChannel(url, text) {
  const u = String(url || "").toLowerCase();
  return (
    u.includes("sgc.gov.co") ||
    u.includes("presidencia.gov.co") ||
    u.includes("presidencia.gov") ||
    u.includes(".gov.co") ||
    u.includes("gov.co/")
  );
}

function inferPublisher(url, result = {}, scraped = {}) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    parsed = { hostname: "" };
  }
  const domain = parsed.hostname.replace(/^www\./, "");
  const platform = inferChannel(url);
  return {
    name: scraped.siteName || result.siteName || scraped.title || result.source || publisherNameFromDomain(domain),
    domain,
    channel: platform,
    url
  };
}

function publisherNameFromDomain(domain) {
  const known = {
    "eltiempo.com": "El Tiempo",
    "elespectador.com": "El Espectador",
    "semana.com": "Semana",
    "bluradio.com": "Blu Radio",
    "rcnradio.com": "RCN Radio",
    "caracol.com.co": "Caracol Radio",
    "wradio.com.co": "W Radio",
    "portal.gestiondelriesgo.gov.co": "UNGRD",
    "gestiondelriesgo.gov.co": "UNGRD",
    "sgc.gov.co": "Servicio Geológico Colombiano",
    "presidencia.gov.co": "Presidencia de Colombia"
  };
  return known[domain] || domain || null;
}

function inferChannel(url) {
  const u = String(url || "").toLowerCase();
  if (u.includes("youtube.com") || u.includes("youtu.be")) return "youtube";
  if (u.includes("facebook.com")) return "facebook";
  if (u.includes("instagram.com")) return "instagram";
  if (u.includes("linkedin.com")) return "linkedin";
  if (u.includes("x.com") || u.includes("twitter.com")) return "x_twitter";
  if (/\.pdf($|\?)/i.test(u)) return "pdf";
  return "web";
}

function inferReportedDataSource(text) {
  const n = norm(text);
  const sources = [];
  if (n.includes("ungrd") || n.includes("unidad nacional para la gestion del riesgo")) {
    sources.push({
      id: "UNGRD",
      name: "Unidad Nacional para la Gestión del Riesgo de Desastres",
      type: "oficial_nacional",
      url: "https://portal.gestiondelriesgo.gov.co/"
    });
  }
  if (n.includes("servicio geologico colombiano") || /\bsgc\b/i.test(text)) {
    sources.push({
      id: "SGC",
      name: "Servicio Geológico Colombiano",
      type: "oficial_nacional",
      url: "https://www.sgc.gov.co/"
    });
  }
  if (n.includes("presidencia de la republica") || n.includes("presidencia de colombia")) {
    sources.push({
      id: "presidencia",
      name: "Presidencia de Colombia",
      type: "oficial_nacional",
      url: "https://www.presidencia.gov.co/"
    });
  }
  if (n.includes("gobernacion")) {
    sources.push({
      id: "gobernacion",
      name: "Gobernación citada en el texto",
      type: "oficial_departamental_por_verificar",
      url: null
    });
  }
  if (n.includes("alcaldia")) {
    sources.push({
      id: "alcaldia",
      name: "Alcaldía citada en el texto",
      type: "oficial_municipal_por_verificar",
      url: null
    });
  }
  return dedupe(sources, (x) => x.id);
}

function isSpecificEventEvidence(text) {
  if (isGenericPage(text)) return false;
  if (hasUnrelatedEventContext(text)) return false;
  return hasEventTerm(text) && hasColombiaContext(text) && (hasDamageTerm(text) || hasImpactedPlace(text) || hasEventDate(text));
}

function hasEventTerm(text) {
  // también sin enlaces: un documento cuyo único anclaje colombiano fuese la URL
  // de una imagen entraba al feed como evidencia del evento
  const n = norm(sinEnlaces(text));
  return EVENT_TERMS.some((term) => n.includes(norm(term))) ||
    EVENT_PLACES.some((place) => mentionsPlace(n, place));
}

function hasDamageTerm(text) {
  const n = norm(text);
  return DAMAGE_TERMS.some((term) => n.includes(norm(term)));
}

function hasImpactedPlace(text) {
  const n = norm(sinEnlaces(text));
  return MUNICIPIOS.some(([name, dept]) =>
    mentionsPlace(n, name) || mentionsPlace(n, dept));
}

function hasColombiaContext(text) {
  const n = norm(text);
  return n.includes("colombia") || n.includes("ungrd") || n.includes("sgc") || hasImpactedPlace(text);
}

function hasUnrelatedEventContext(text) {
  const n = norm(text).slice(0, 500);
  return UNRELATED_EVENT_TERMS.some((term) => n.includes(norm(term))) &&
    !n.includes("colombia") &&
    !n.includes("ungrd");
}

function hasEventDate(text) {
  const n = norm(text);
  return /10\s+de\s+agosto\s+de\s+2026|15\s+de\s+agosto\s+de\s+2026|agosto\s+de\s+2026|2026-08|10-ago-2026|10\/08\/2026|15-08-2026|15\/08\/2026/.test(n);
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

function itemKey(item) {
  if (item.source_id === "firecrawl-busqueda-diaria" || item.source?.id === "firecrawl-busqueda-diaria") {
    return `${item.search_date || "sin-fecha"}:${item.url}`;
  }
  return item.url;
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

async function safeJson(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

function normalizeRunDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  let m = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = raw.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
  if (m) return `${m[3]}-${String(Number(m[2])).padStart(2, "0")}-${String(Number(m[1])).padStart(2, "0")}`;
  return null;
}

function todayInBogota() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

function toDmy(isoDate) {
  const [year, month, day] = String(isoDate || "").split("-");
  return `${day}-${month}-${year}`;
}

function norm(s) {
  return String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/* R10 («Cali» no es «California»): los topónimos se buscan con límite de
   palabra, igual que en ingest/municipios.py::_mentioned. Con includes() a
   secas, un artículo sobre California pasaba el filtro de contexto colombiano.
   Nombre en inglés como sus hermanos (hasImpactedPlace, hasEventTerm): buscar
   una cadena es infraestructura de texto; el dominio son municipio y balance.
   `n` ya viene normalizado. */
function mentionsPlace(n, nombre) {
  const t = norm(nombre).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${t}\\b`).test(n);
}

/* El límite de palabra no basta contra las URLs: en «terremoto-cali.jpg» o
   «/noticias/cali/portada.webp» el guion y la barra SON frontera, así que el
   nombre de archivo de una imagen atribuía el balance a Cali sin que el
   topónimo apareciera en la prosa (2 de 15 ítems del 16-ago), y sus números
   llegaban a findMetricNumber como cifras de daño («900x601» → 900 municipios
   afectados). El pipeline no sufre esto porque atribuye sobre titulares; el
   worker lee el documento entero.

   Lo que Firecrawl entrega es markdown, así que el texto ENLAZADO es prosa
   —«[UNGRD confirma 12 fallecidos en Cali](url)» es justo donde aparece el
   municipio— y solo se descarta la URL. De las imágenes se va todo, alt
   incluido: son pies de foto y créditos, no balance. Un «Quibdó.pdf» suelto en
   la prosa se conserva a propósito: nombrar un documento oficial es nombrar el
   municipio. */
function sinEnlaces(text) {
  return String(text || "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")      // imagen: fuera alt y URL
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")    // enlace: se queda el texto
    .replace(/https?:\/\/\S+/g, " ")            // URL desnuda
    .replace(/\/\S*\.(?:jpe?g|png|webp|gif|svg|pdf|mp4|avif)\b/gi, " ");
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
    <link>https://github.com/18orkidea/monitor-terremoto-colombia</link>
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

/* Exportado solo para los tests (Cloudflare usa únicamente el default):
   tests/test_worker_toponimos.py ejecuta esta misma función con node, para no
   testear una copia — la lección de crosscheck aplica también aquí. */
export { MUNICIPIOS, EVENT_PLACES, mentionsPlace, sinEnlaces,
         hasEventTerm, hasImpactedPlace, structureOfficialText,
         findMetricNumber, extraerCifras, extraerCifrasVigiladas,
         incoherenciasDeCifras, findCutoffDate };
