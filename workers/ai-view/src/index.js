const MODELS = {
  qwen: {
    id: "@cf/qwen/qwq-32b",
    label: "Qwen QwQ 32B",
    note: "razonamiento; útil para hipótesis y brechas"
  },
  deepseek: {
    id: "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
    label: "DeepSeek R1 Distill Qwen 32B",
    note: "razonamiento; contraste independiente"
  },
  kimi: {
    id: "@cf/moonshotai/kimi-k2.6",
    label: "Moonshot Kimi K2.6",
    note: "contexto largo; síntesis narrativa"
  }
};

const DEFAULT_QUESTION =
  "Identifica municipios subrepresentados y explica qué evidencia falta para convertir señales en reporte oficial colombiano.";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return cors(new Response(null, { status: 204 }));
    if (url.pathname === "/") return html();
    if (url.pathname === "/api/models") return json({ models: MODELS });
    if (url.pathname === "/api/analyze" && request.method === "POST") {
      const auth = authorize(request, env);
      if (auth) return auth;
      return analyze(request, env);
    }
    return json({ error: "not_found" }, 404);
  }
};

function authorize(request, env) {
  if (!env.ACCESS_TOKEN) {
    return json({
      error: "access_token_not_configured",
      detail: "Configure el secreto ACCESS_TOKEN con `wrangler secret put ACCESS_TOKEN`."
    }, 503);
  }
  const header = request.headers.get("authorization") || "";
  const token = header.replace(/^Bearer\s+/i, "");
  if (!token || token !== env.ACCESS_TOKEN) {
    return json({ error: "unauthorized" }, 401);
  }
  return null;
}

async function analyze(request, env) {
  let body = {};
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const selected = MODELS[body.model] || MODELS.qwen;
  const data = await loadData(env.DATA_BASE_URL);
  const prompt = buildPrompt(data, body.question || DEFAULT_QUESTION);
  const started = Date.now();

  const result = await env.AI.run(selected.id, {
    messages: [
      {
        role: "system",
        content:
          "Eres un analista de gestión del riesgo. Responde en español, con cautela metodológica. " +
          "No conviertas prensa, DYFI o Copernicus en EDAN oficial. Separa señal, evidencia satelital y fuente oficial colombiana."
      },
      { role: "user", content: prompt }
    ],
    max_tokens: 900,
    temperature: 0.2
  });

  return json({
    model: selected,
    ms: Date.now() - started,
    generated_at: new Date().toISOString(),
    answer: normalizeAnswer(result),
    usage: result.usage || null,
    data_summary: summarizeData(data)
  });
}

async function loadData(base) {
  const [monitor, municipios, noticias] = await Promise.all([
    fetchJson(`${base}/monitor.json`),
    fetchJson(`${base}/municipios.json`),
    fetchJson(`${base}/noticias.json`)
  ]);
  return { monitor, municipios, noticias };
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: { "user-agent": "monitor-terremoto-colombia-ai-view/1.0" }
  });
  if (!response.ok) throw new Error(`HTTP ${response.status} ${url}`);
  return response.json();
}

function summarizeData(data) {
  const municipios = data.municipios?.items || [];
  const noticias = data.noticias?.items || [];
  const departamentos = {};
  for (const n of noticias) {
    for (const d of n.departamentos || []) departamentos[d] = (departamentos[d] || 0) + 1;
  }
  return {
    generado: data.monitor?.generado || data.municipios?.generado,
    total_municipios: municipios.length,
    fuera_aoi: municipios.filter((m) => !m.en_aoi_copernicus).length,
    total_noticias: noticias.length,
    noticias_por_departamento: departamentos
  };
}

function buildPrompt(data, question) {
  const municipios = (data.municipios?.items || [])
    .slice()
    .sort((a, b) =>
      Number(a.en_aoi_copernicus) - Number(b.en_aoi_copernicus) ||
      (b.dyfi_max_cdi || 0) - (a.dyfi_max_cdi || 0) ||
      (b.n_noticias || 0) - (a.n_noticias || 0)
    )
    .slice(0, 18)
    .map((m) => ({
      municipio: m.municipio,
      departamento: m.departamento,
      poblacion_2026: m.poblacion_2026,
      en_aoi_copernicus: m.en_aoi_copernicus,
      estado: m.estado,
      dyfi_max_cdi: m.dyfi_max_cdi,
      dyfi_respuestas: m.dyfi_respuestas,
      n_noticias: m.n_noticias,
      fuentes: m.fuentes
    }));

  const aois = (data.monitor?.aois || []).map((a) => ({
    aoi: a.aoi,
    estado_cruce: a.cruce?.estado,
    prensa: a.cruce?.n_prensa,
    ciudadano: a.cruce?.n_ciudadano,
    edificios_afectados: a.resumen?.edificios_afectados,
    vias_afectadas_km: a.resumen?.vias_afectadas_km
  }));

  return [
    `Pregunta: ${question}`,
    "",
    "Datos disponibles, resumidos desde el monitor:",
    JSON.stringify(
      {
        evento: data.monitor?.evento,
        resumen: summarizeData(data),
        aois,
        municipios
      },
      null,
      2
    ),
    "",
    "Devuelve: 1) hallazgos, 2) municipios subrepresentados, 3) límites de inferencia, 4) qué fuente oficial colombiana faltaría."
  ].join("\n");
}

function normalizeAnswer(result) {
  if (typeof result === "string") return result;
  if (result.response) return result.response;
  if (result.choices?.[0]?.message?.content) return result.choices[0].message.content;
  return JSON.stringify(result);
}

function html() {
  return new Response(PAGE, {
    headers: { "content-type": "text/html; charset=utf-8" }
  });
}

function json(value, status = 200) {
  return cors(
    new Response(JSON.stringify(value), {
      status,
      headers: { "content-type": "application/json; charset=utf-8" }
    })
  );
}

function cors(response) {
  response.headers.set("access-control-allow-origin", "*");
  response.headers.set("access-control-allow-methods", "GET,POST,OPTIONS");
  response.headers.set("access-control-allow-headers", "content-type");
  return response;
}

const PAGE = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vista IA - Monitor terremoto Colombia</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f7f8fa;color:#17202a}
main{max-width:980px;margin:0 auto;padding:28px 18px}
h1{font-size:28px;margin:0 0 6px} p{color:#52606d}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
select,textarea,button{font:inherit;border:1px solid #c9d1da;border-radius:6px;background:white}
select,button{padding:9px 12px} textarea{width:100%;min-height:90px;padding:10px;box-sizing:border-box}
button{background:#1155cc;color:white;border-color:#1155cc;cursor:pointer}
button:disabled{opacity:.65;cursor:wait}
pre{white-space:pre-wrap;background:white;border:1px solid #dde3ea;border-radius:8px;padding:14px;line-height:1.45}
.meta{font-size:13px;color:#6b7280}
</style>
</head>
<body>
<main>
<h1>Vista con modelos chinos - Workers AI</h1>
<p>Contrasta el monitor con Qwen, DeepSeek o Kimi. La salida es análisis asistido, no fuente oficial.</p>
<input id="token" type="password" placeholder="Token de acceso" style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9d1da;border-radius:6px;margin:8px 0 10px">
<textarea id="q">${DEFAULT_QUESTION}</textarea>
<div class="bar">
<select id="model">
<option value="qwen">Qwen QwQ 32B</option>
<option value="deepseek">DeepSeek R1 Distill Qwen 32B</option>
<option value="kimi">Moonshot Kimi K2.6</option>
</select>
<button id="run">Analizar</button>
</div>
<p class="meta" id="meta"></p>
<pre id="out">Listo.</pre>
</main>
<script>
const out=document.getElementById('out'), meta=document.getElementById('meta'), btn=document.getElementById('run');
btn.onclick=async()=>{
  btn.disabled=true; out.textContent='Consultando Workers AI...'; meta.textContent='';
  try{
    const token=document.getElementById('token').value;
    const r=await fetch('/api/analyze',{method:'POST',headers:{'content-type':'application/json','authorization':'Bearer '+token},body:JSON.stringify({model:document.getElementById('model').value,question:document.getElementById('q').value})});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||r.status);
    meta.textContent=j.model.label+' · '+j.ms+' ms · municipios '+j.data_summary.total_municipios+' · noticias '+j.data_summary.total_noticias;
    out.textContent=j.answer;
  }catch(e){out.textContent='Error: '+e.message}
  btn.disabled=false;
};
</script>
</body>
</html>`;
