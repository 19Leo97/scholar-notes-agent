/* Interactive guide engine. Data comes from the data_*.js files and the generated CODEMAP/TESTMAP/STATS/FILES. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  const num = (n) => (n == null ? "—" : Number(n).toLocaleString("es"));
  const link = (path, label) => `<a href="#/codigo/${esc(path)}"><code>${esc(label || path)}</code></a>`;

  const SECTIONS = [
    { id: "inicio", t: "Visión global", i: "🧭", g: "Entender" },
    { id: "arquitectura", t: "Arquitectura", i: "🏗️", g: "Entender" },
    { id: "recorrido", t: "Recorrido de una pregunta", i: "▶️", g: "Entender" },
    { id: "codigo", t: "Mapa del código", i: "🗂️", g: "Explorar" },
    { id: "adrs", t: "Decisiones (ADRs)", i: "⚖️", g: "Explorar" },
    { id: "conceptos", t: "Conceptos clave", i: "💡", g: "Explorar" },
    { id: "evaluaciones", t: "Evaluaciones e iteraciones", i: "📊", g: "Historia" },
    { id: "ingenieria", t: "Acciones de ingeniería", i: "🛠️", g: "Historia" },
    { id: "modificar", t: "Escalar o modificar", i: "🔧", g: "Actuar" },
    { id: "referencia", t: "Referencia rápida", i: "📌", g: "Actuar" },
  ];

  const layerOf = (path) => {
    const m = MODULES[path];
    if (m && m.layer) return LAYERS.find((l) => l.id === m.layer) || LAYERS[0];
    return LAYERS.find((l) => l.match.some((p) => path === p || path.startsWith(p))) || LAYERS[LAYERS.length - 1];
  };
  const pill = (txt, cls) => `<span class="pill ${cls || ""}">${esc(txt)}</span>`;
  const costPill = (c) => pill("costo de cambio: " + c, { bajo: "good", medio: "warn", alto: "bad" }[c] || "");

  /* ------------------------------------------------------------------ navigation */
  function renderNav(cur) {
    let html = "", grp = "";
    SECTIONS.forEach((s) => {
      if (s.g !== grp) { grp = s.g; html += `<div class="grp">${esc(grp)}</div>`; }
      html += `<a href="#/${s.id}" class="${s.id === cur ? "on" : ""}">${s.i} ${esc(s.t)}</a>`;
    });
    $("#nav").innerHTML = html;
  }
  function parseHash() {
    const parts = decodeURIComponent(location.hash.replace(/^#\/?/, "")).split("/");
    const id = SECTIONS.some((s) => s.id === parts[0]) ? parts[0] : "inicio";
    return { id, param: parts.slice(1).join("/") };
  }
  function route() {
    const { id, param } = parseHash();
    renderNav(id);
    $("#nav").classList.remove("open");
    const view = { inicio, arquitectura, recorrido, codigo, adrs, conceptos, evaluaciones, ingenieria, modificar, referencia }[id];
    $("#main").innerHTML = view(param);
    bind[id] && bind[id](param);
    if (!param || id !== "codigo") window.scrollTo({ top: 0 });
    document.title = SECTIONS.find((s) => s.id === id).t + " · scholar-notes-agent";
  }

  /* ------------------------------------------------------------------ INICIO */
  function inicio() {
    const O = OVERVIEW;
    return `
<h1>${esc(O.title)}</h1>
<p class="lead">${md(O.lead)}</p>
<div class="grid g4" style="margin:18px 0">
  <div class="card stat"><b>${num(STATS.lines)}</b><span>líneas de Python en ${STATS.modules} módulos</span></div>
  <div class="card stat"><b>${num(STATS.testsCollected || STATS.testFunctions)}</b><span>pruebas automáticas (sin claves ni red)</span></div>
  <div class="card stat"><b>${ADRS.length}</b><span>decisiones de arquitectura analizadas</span></div>
  <div class="card stat"><b>${HISTORY.e1runs.length + HISTORY.vaultRuns.length + 2}</b><span>evaluaciones y pruebas reales ejecutadas</span></div>
</div>
<h2>El problema y la solución en 30 segundos</h2>
<div class="grid g3">
${O.story.map((s) => `<div class="card"><h3>${s.i} ${esc(s.t)}</h3><p>${md(s.d)}</p></div>`).join("")}
</div>
<h2>Cómo se ve una consulta</h2>
<div class="grid g2">
  <div class="card"><h3>Entrada</h3><pre><code>${esc(O.demoIn)}</code></pre><p class="small">${md(O.demoNote)}</p></div>
  <div class="card"><h3>Salida (real, recortada)</h3><pre><code>${esc(O.demoOut)}</code></pre></div>
</div>
<h2>Lo que lo hace distinto</h2>
<div class="grid g3">
${O.diffs.map((d) => `<div class="card"><h3>${d.i} ${esc(d.t)}</h3><p>${md(d.d)}</p><p class="small">${d.l ? `Ver: ${d.l}` : ""}</p></div>`).join("")}
</div>
<h2>Elige tu ruta de lectura</h2>
<div class="grid g3">
${O.paths.map((p) => `<div class="card"><h3>${p.i} ${esc(p.t)} ${pill(p.time, "acc")}</h3><p>${md(p.d)}</p><ol>${p.steps.map((s) => `<li><a href="#/${s[0]}">${esc(s[1])}</a></li>`).join("")}</ol></div>`).join("")}
</div>
<div class="callout warn"><b>Honestidad ante todo.</b> ${md(O.honest)}</div>`;
  }

  /* ------------------------------------------------------------------ ARQUITECTURA */
  function flowSvg(key) {
    const f = FLOWS[key];
    const by = Object.fromEntries(f.nodes.map((n) => [n.id, n]));
    const anchor = (n, s) => ({ l: [n.x, n.y + n.h / 2], r: [n.x + n.w, n.y + n.h / 2], t: [n.x + n.w / 2, n.y], b: [n.x + n.w / 2, n.y + n.h] }[s]);
    const labels = [];
    const edges = f.edges.map((e) => {
      const a = anchor(by[e.from], e.fs), b = anchor(by[e.to], e.ts);
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      const d = e.bend ? `M${a[0]} ${a[1]} Q${mx + e.bend[0]} ${my + e.bend[1]} ${b[0]} ${b[1]}` : `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`;
      if (e.label) {
        let x, y, anchorAt = "middle";
        if (e.bend && e.bend[0] !== 0) { x = mx + e.bend[0] / 2 + (e.bend[0] > 0 ? 7 : -7); y = my + 4; anchorAt = e.bend[0] > 0 ? "start" : "end"; }
        else if (Math.abs(a[0] - b[0]) < 1) { x = mx + 8; y = my + 4; anchorAt = "start"; }
        else { x = mx; y = my - 7; }
        labels.push(`<text class="elabel" x="${x}" y="${y}" text-anchor="${anchorAt}">${esc(e.label)}</text>`);
      }
      return `<path class="edge ${e.dash ? "dash" : ""}" d="${d}"/>`;
    }).join("");
    const nodes = f.nodes.map((n) => `
<g class="node ${n.kind}" data-id="${n.id}" tabindex="0" role="button" aria-label="${esc(n.label)}">
  <rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="10"/>
  <text x="${n.x + n.w / 2}" y="${n.y + n.h / 2 - (n.sub ? 3 : -4)}" text-anchor="middle">${esc(n.label)}</text>
  ${n.sub ? `<text class="sub" x="${n.x + n.w / 2}" y="${n.y + n.h / 2 + 13}" text-anchor="middle">${esc(n.sub)}</text>` : ""}
</g>`).join("");
    return `<svg class="flow" viewBox="${f.viewBox}" role="img" aria-label="${esc(f.title)}">
<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#7a8699"/></marker></defs>${edges}${nodes}${labels.join("")}</svg>`;
  }
  function nodePanel(key, id) {
    const n = FLOWS[key].nodes.find((x) => x.id === id);
    if (!n) return "";
    const kind = { llm: pill("usa un LLM", "llm"), code: pill("código determinista", "acc"), store: pill("almacenamiento", "warn"), guard: pill("protección transversal", "bad"), io: pill("entrada / salida", "info") }[n.kind];
    return `<div class="card"><h3>${esc(n.label)} ${kind}</h3><p>${md(n.what)}</p>
<dl class="kv">
${n.file ? `<dt>Dónde está</dt><dd>${n.file.map((f) => link(f)).join(" ")} ${n.fn ? `· <code>${esc(n.fn)}</code>` : ""}</dd>` : ""}
${n.inp ? `<dt>Recibe</dt><dd>${md(n.inp)}</dd>` : ""}${n.out ? `<dt>Entrega</dt><dd>${md(n.out)}</dd>` : ""}
${n.tokens ? `<dt>Tokens</dt><dd>${md(n.tokens)}</dd>` : ""}${n.fails ? `<dt>Falla cuando</dt><dd>${md(n.fails)}</dd>` : ""}
${n.change ? `<dt>Si lo cambias</dt><dd>${md(n.change)}</dd>` : ""}${n.adr ? `<dt>Decisión</dt><dd><a href="#/adrs/${n.adr}">${esc(n.adr)}</a></dd>` : ""}
</dl></div>`;
  }
  function arquitectura(param) {
    const tab = param || "query";
    const tabs = [["query", "Consulta (agente)"], ["ingest", "Ingesta de notas"], ["layers", "Capas y dependencias"], ["data", "Dónde viven los datos"]];
    let body = "";
    if (tab === "query" || tab === "ingest") {
      body = `<p>${md(FLOWS[tab].intro)}</p>
<div class="legend"><span><i style="background:var(--llm-soft)"></i>usa LLM</span><span><i style="background:var(--panel2)"></i>código determinista</span><span><i style="background:var(--store-soft)"></i>almacén</span><span><i style="background:var(--guard-soft)"></i>protección transversal</span><span><i style="background:var(--accent-soft)"></i>entrada/salida</span><b>Haz clic en una caja.</b></div>
${flowSvg(tab)}<div id="nodepanel" style="margin-top:12px">${nodePanel(tab, FLOWS[tab].start)}</div>`;
    } else if (tab === "layers") {
      body = `<p>${md(LAYER_INTRO)}</p><div class="grid">${LAYERS.map((l) => {
        const mods = Object.keys(CODEMAP).filter((p) => CODEMAP[p].lines > 1 && layerOf(p).id === l.id);
        return `<div class="card" style="border-left:6px solid ${l.color}"><h3>${esc(l.name)}</h3><p>${md(l.desc)}</p>
<p class="small"><b>Regla:</b> ${md(l.rule)}</p><div class="chips">${mods.map((p) => `<a class="pill" href="#/codigo/${esc(p)}">${esc(p)}</a>`).join("")}</div></div>`;
      }).join("")}</div>`;
    } else {
      body = `<p>${md(DATA_INTRO)}</p><div class="tablewrap"><table><tr><th>Dato</th><th>Dónde</th><th>Qué contiene</th><th>Quién lo escribe</th><th>Privacidad</th></tr>
${DATASTORES.map((d) => `<tr><td><b>${esc(d.name)}</b></td><td><code>${esc(d.where)}</code></td><td>${md(d.what)}</td><td>${md(d.writer)}</td><td>${md(d.privacy)}</td></tr>`).join("")}</table></div>`;
    }
    return `<h1>Arquitectura</h1><p class="lead">${md(ARCH_LEAD)}</p>
<div class="tabs">${tabs.map((t) => `<a class="tab ${t[0] === tab ? "on" : ""}" href="#/arquitectura/${t[0]}">${t[1]}</a>`).join("")}</div>${body}`;
  }

  /* ------------------------------------------------------------------ RECORRIDO */
  let stepState = { i: 0, repair: true };
  function recorrido() {
    return `<h1>Recorrido de una pregunta</h1><p class="lead">${md(STEPS_LEAD)}</p>
<div class="callout"><label><input type="checkbox" id="repairChk" ${stepState.repair ? "checked" : ""}> Simular que el modelo inventa una cita (activa el paso de reparación)</label></div>
<div class="stepper"><div class="steps" id="stepList"></div><div id="stepBody"></div></div>`;
  }
  function drawSteps() {
    const steps = STEPS.filter((s) => (!s.repairOnly || stepState.repair) && (!s.noRepair || !stepState.repair));
    if (stepState.i >= steps.length) stepState.i = steps.length - 1;
    const cur = steps[stepState.i];
    let tin = 0, tout = 0, calls = 0; const ev = []; let latest = [];
    steps.slice(0, stepState.i + 1).forEach((s, k) => {
      if (s.llm) { tin += s.tin; tout += s.tout; calls++; }
      (s.adds || []).forEach((e) => ev.push(e));
      if (k === stepState.i) latest = s.adds || [];
    });
    $("#stepList").innerHTML = steps.map((s, k) => `<button data-k="${k}" class="${k === stepState.i ? "on" : k < stepState.i ? "done" : ""}"><span class="n">${k + 1}</span>${esc(s.t)}</button>`).join("");
    $("#stepBody").innerHTML = `<div class="card"><h3>${stepState.i + 1}. ${esc(cur.t)} ${cur.llm ? pill("LLM", "llm") : pill("sin LLM", "acc")}</h3>
<p>${md(cur.d)}</p>
${cur.code ? `<h4>Qué ocurre / dato real</h4><pre><code>${esc(cur.code)}</code></pre>` : ""}
<dl class="kv"><dt>Código</dt><dd>${(cur.file || []).map((f) => link(f)).join(" ")} ${cur.fn ? `· <code>${esc(cur.fn)}</code>` : ""}</dd>
${cur.why ? `<dt>Por qué así</dt><dd>${md(cur.why)}</dd>` : ""}${cur.adr ? `<dt>Decisión</dt><dd><a href="#/adrs/${cur.adr}">${esc(cur.adr)}</a></dd>` : ""}</dl>
<h4>Estado acumulado</h4>
<div class="meter"><div>Llamadas LLM: <b>${calls}</b></div><div>Tokens entrada: <b>${num(tin)}</b></div><div>Tokens salida: <b>${num(tout)}</b></div><div>Evidencias: <b>${ev.length}</b></div></div>
<div class="chips" style="margin-top:10px">${ev.map((e) => `<span class="ev ${e.id[0] === "P" ? "p" : ""} ${latest.includes(e) ? "new" : ""}" title="${esc(e.t)}">${esc(e.id)} · ${esc(e.t)}</span>`).join("") || '<span class="small">(todavía no hay evidencias)</span>'}</div>
<p class="small" style="margin-top:10px">Valores de tokens ilustrativos, calibrados con una corrida real (6.859 entrada / 942 salida / 5 llamadas con un modelo local).</p>
<div style="margin-top:12px;display:flex;gap:8px"><button class="btn ghost" id="prevStep" ${stepState.i === 0 ? "disabled" : ""}>← Anterior</button><button class="btn" id="nextStep" ${stepState.i === steps.length - 1 ? "disabled" : ""}>Siguiente →</button></div></div>`;
    $$("#stepList button").forEach((b) => (b.onclick = () => { stepState.i = +b.dataset.k; drawSteps(); }));
    $("#prevStep").onclick = () => { stepState.i--; drawSteps(); };
    $("#nextStep").onclick = () => { stepState.i++; drawSteps(); };
  }

  /* ------------------------------------------------------------------ CÓDIGO */
  function treeHtml(filter) {
    const q = (filter || "").toLowerCase();
    const paths = Object.keys(CODEMAP).filter((p) => CODEMAP[p].lines > 1).sort();
    const dirs = {};
    paths.forEach((p) => {
      const m = CODEMAP[p];
      const hay = (p + " " + ((MODULES[p] || {}).purpose || "") + " " + m.functions.map((f) => f.name).join(" ") + " " + m.classes.map((c) => c.name).join(" ")).toLowerCase();
      if (q && !q.split(/\s+/).every((t) => hay.includes(t))) return;
      const d = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "(raíz)";
      (dirs[d] = dirs[d] || []).push(p);
    });
    return Object.keys(dirs).sort().map((d) => `<div class="dir">📁 ${esc(d)}</div>${dirs[d].map((p) => {
      const l = layerOf(p);
      return `<a class="file" data-p="${esc(p)}" href="#/codigo/${esc(p)}"><span class="layerbar" style="background:${l.color}"></span>${esc(p.split("/").pop())}<small>${CODEMAP[p].lines}</small></a>`;
    }).join("")}`).join("") || '<p class="small" style="padding:8px">Sin coincidencias.</p>';
  }
  function fnBlock(path, m) {
    const rows = [];
    m.classes.forEach((c) => {
      const key = `${path}:${c.name}`;
      const note = FN[key] || c.doc;
      rows.push(`<div class="fn ${c.private ? "priv" : ""}"><div class="sig"><b>class ${esc(c.name)}</b>${c.bases.length ? `(${esc(c.bases.join(", "))})` : ""} <span class="small">· línea ${c.line}</span></div>${note ? `<p>${md(note)}</p>` : ""}
${c.fields.length ? `<p class="small">Campos: ${c.fields.map((f) => `<code>${esc(f)}</code>`).join(" ")}</p>` : ""}
${c.methods.map((mm) => { const n = FN[`${path}:${c.name}.${mm.name}`] || mm.doc; return `<div class="fn"><div class="sig">• <b>${esc(mm.name)}</b>${esc(mm.sig)}</div>${n ? `<p>${md(n)}</p>` : ""}</div>`; }).join("")}</div>`);
    });
    m.functions.forEach((f) => {
      const n = FN[`${path}:${f.name}`] || f.doc;
      rows.push(`<div class="fn ${f.private ? "priv" : ""}"><div class="sig"><b>${esc(f.name)}</b>${esc(f.sig)} <span class="small">· línea ${f.line}${f.private ? " · interno" : ""}</span></div>${n ? `<p>${md(n)}</p>` : ""}</div>`);
    });
    return rows.join("") || '<p class="small">Sin clases ni funciones (solo marca el paquete).</p>';
  }
  function moduleDetail(path) {
    const m = CODEMAP[path];
    if (!m) return '<div class="card"><p>Elige un archivo del árbol.</p></div>';
    const mod = MODULES[path] || {};
    const l = layerOf(path);
    const tests = Object.entries(TESTMAP).filter(([, t]) => t.covers.includes(path));
    const chips = (arr) => arr.length ? `<div class="chips">${arr.map((p) => `<a class="pill" href="#/codigo/${esc(p)}">${esc(p)}</a>`).join("")}</div>` : '<span class="small">ninguno</span>';
    return `<div class="card"><h3><code>${esc(path)}</code> ${pill(l.name, "")} ${pill(m.lines + " líneas", "info")}</h3>
<p>${md(mod.purpose || m.doc || "")}</p>
<dl class="kv">
${mod.when ? `<dt>Cuándo se ejecuta</dt><dd>${md(mod.when)}</dd>` : ""}${mod.io ? `<dt>Entra → sale</dt><dd>${md(mod.io)}</dd>` : ""}
${mod.change ? `<dt>Si lo modificas</dt><dd>${md(mod.change)}</dd>` : ""}
<dt>Usa</dt><dd>${chips(m.imports)}</dd><dt>Lo usan</dt><dd>${chips(m.usedBy)}</dd>
<dt>Pruebas</dt><dd>${tests.length ? tests.map(([f, t]) => `<code>${esc(f.replace("tests/", ""))}</code> <span class="small">(${t.tests.length} funciones de prueba)</span>`).join("<br>") : '<span class="small">cubierto indirectamente por pruebas de integración</span>'}</dd></dl></div>
<h3>Clases y funciones</h3><div class="card">${fnBlock(path, m)}</div>`;
  }
  function codigo(param) {
    return `<h1>Mapa del código</h1><p class="lead">${md(CODE_LEAD)}</p>
<div class="filters"><input id="treeFilter" type="search" placeholder="Filtrar archivos o funciones…"><span class="small">Color = capa de arquitectura (ver <a href="#/arquitectura/layers">Capas</a>). Número = líneas.</span></div>
<div class="codewrap"><div class="tree" id="tree">${treeHtml("")}</div><div id="modDetail">${moduleDetail(param)}</div></div>`;
  }

  /* ------------------------------------------------------------------ ADRs */
  function adrCard(a, open) {
    return `<details class="adr" id="${a.id}" ${open ? "open" : ""}><summary><span class="num">${a.id}</span><span class="ttl">${esc(a.title)}</span>${pill(a.area, "info")}${costPill(a.cost)}<span class="one">Elegido: <b>${esc(a.chosen)}</b> — ${md(a.one)}</span></summary>
<div class="body">
<h3>Contexto</h3><p>${md(a.context)}</p>
<h3>Decisión</h3><p>${md(a.decision)}</p>
<h3>Alternativas consideradas</h3>
<div class="tablewrap"><table><tr><th>Alternativa</th><th>Qué ofrece</th><th>Por qué no se eligió</th></tr>${a.alts.map((x) => `<tr><td><b>${esc(x.n)}</b></td><td>${md(x.gives)}</td><td>${md(x.why)}</td></tr>`).join("")}</table></div>
<h3>Qué me haría replantear la decisión</h3><ul>${a.reconsider.map((r) => `<li>${md(r)}</li>`).join("")}</ul>
<h3>Opinión honesta</h3>
<div class="proscons"><div class="pros"><h4>Pros</h4><ul>${a.pros.map((r) => `<li>${md(r)}</li>`).join("")}</ul></div><div class="cons"><h4>Contras</h4><ul>${a.cons.map((r) => `<li>${md(r)}</li>`).join("")}</ul></div></div>
<p><b>Cambiarla después:</b> ${costPill(a.cost)} ${md(a.costWhy)}</p>
<p class="small">Archivos implicados: ${a.files.map((f) => link(f)).join(" ")}</p>
</div></details>`;
  }
  function adrs(param) {
    const areas = ["todas", ...new Set(ADRS.map((a) => a.area))];
    return `<h1>Decisiones de arquitectura (ADRs)</h1><p class="lead">${md(ADR_LEAD)}</p>
<h3>Vista comparativa</h3><div class="tablewrap"><table><tr><th>ADR</th><th>Decisión</th><th>Elegido</th><th>Alternativas</th><th>Cambiarla</th></tr>
${ADRS.map((a) => `<tr><td style="white-space:nowrap"><a href="#/adrs/${a.id}">${a.id}</a></td><td>${esc(a.title)}</td><td><b>${esc(a.chosen)}</b></td><td>${a.alts.map((x) => esc(x.n)).join(" · ")}</td><td>${costPill(a.cost)}</td></tr>`).join("")}</table></div>
<div class="filters" style="margin-top:18px"><input id="adrFilter" type="search" placeholder="Filtrar decisiones…">${areas.map((a, i) => `<button class="chip ${i === 0 ? "on" : ""}" data-area="${esc(a)}">${esc(a)}</button>`).join("")}
<button class="chip" id="adrAll">Expandir todas</button></div>
<div id="adrList">${ADRS.map((a) => adrCard(a, param === a.id)).join("")}</div>`;
  }

  /* ------------------------------------------------------------------ CONCEPTOS */
  function conceptos() {
    const cats = ["todos", ...new Set(GLOSSARY.map((g) => g.cat))];
    return `<h1>Conceptos clave</h1><p class="lead">${md(GLOSS_LEAD)}</p>
<div class="filters"><input id="gFilter" type="search" placeholder="Buscar concepto…">${cats.map((c, i) => `<button class="chip ${i === 0 ? "on" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("")}</div>
<div class="grid g2" id="gList">${GLOSSARY.map((g) => `<div class="card gl" data-cat="${esc(g.cat)}" data-t="${esc((g.term + " " + g.simple + " " + g.here).toLowerCase())}" id="c-${esc(g.term.replace(/\W+/g, "-").toLowerCase())}">
<h3>${esc(g.term)} ${pill(g.cat, "info")}</h3><p><b>En simple:</b> ${md(g.simple)}</p><p><b>En este proyecto:</b> ${md(g.here)}</p>
${g.where ? `<p class="small">Dónde: ${g.where.map((f) => link(f)).join(" ")}</p>` : ""}</div>`).join("")}</div>`;
  }

  /* ------------------------------------------------------------------ EVALUACIONES */
  function bars(rows, key, max, cls) {
    return rows.map((r) => `<div class="row"><span>${esc(r.cfg)}</span><div style="background:var(--panel2);border-radius:5px"><div class="bar ${cls || ""}" style="width:${(r[key] / max) * 100}%"></div></div><b>${r[key].toFixed(3)}</b></div>`).join("");
  }
  function evaluaciones() {
    const H = HISTORY;
    return `<h1>Evaluaciones e iteraciones</h1><p class="lead">${md(H.lead)}</p>
<h2>1 · Recuperación en SciFact (E1): ¿encuentra los documentos correctos?</h2>
<p>${md(H.e1intro)}</p>
<div class="grid g2">${H.e1runs.map((r) => `<div class="card bars"><h3>${esc(r.name)}</h3><p class="small">${md(r.note)}</p>
<h4>nDCG@10</h4>${bars(r.rows, "ndcg", 1, r.cls)}<h4>Recall@10</h4>${bars(r.rows, "r10", 1, "b2")}</div>`).join("")}</div>
<div class="callout good"><b>Lectura:</b> ${md(H.e1read)}</div>
<h2>2 · Agente completo sobre el vault demo (E4, modelos reales de Groq)</h2>
<p>${md(H.vaultIntro)}</p>
<div class="grid g2"><div class="card"><h3>Intentos</h3><div class="tablewrap"><table><tr><th>Intento</th><th>Resultado</th><th>Causa / acción</th></tr>${H.vaultRuns.map((r) => `<tr><td>${esc(r.n)}</td><td>${md(r.res)}</td><td>${md(r.cause)}</td></tr>`).join("")}</table></div></div>
<div class="card"><h3>Métricas (4 preguntas completadas)</h3><div class="tablewrap"><table><tr><th>Métrica</th><th>Valor</th><th>Qué significa</th></tr>${H.vaultMetrics.map((r) => `<tr><td>${md(r[0])}</td><td><b>${esc(r[1])}</b></td><td>${md(r[2])}</td></tr>`).join("")}</table></div></div></div>
<h2>3 · Pruebas con modelos locales (humo, no benchmark)</h2>
<div class="tablewrap"><table><tr><th>Prueba</th><th>Resultado</th><th>Qué se aprendió / cambió</th></tr>${H.smoke.map((r) => `<tr><td>${md(r.n)}</td><td>${md(r.res)}</td><td>${md(r.learn)}</td></tr>`).join("")}</table></div>
<h2>4 · Suite de pruebas automáticas</h2>
<div class="card bars">${H.tests.map((t) => `<div class="row"><span>${esc(t.when)}</span><div style="background:var(--panel2);border-radius:5px"><div class="bar b3" style="width:${(t.n / 60) * 100}%"></div></div><b>${t.n}</b></div><p class="small" style="margin:0 0 6px">${md(t.note)}</p>`).join("")}</div>
<h2>5 · Línea de tiempo de iteraciones</h2>
<div class="timeline">${H.timeline.map((t) => `<div class="tl ${t.k || ""}"><h4>${esc(t.t)} ${t.k === "bug" ? pill("bug", "bad") : t.k === "eval" ? pill("evaluación", "llm") : t.k === "sec" ? pill("seguridad", "warn") : ""}</h4><p>${md(t.d)}</p></div>`).join("")}</div>
<h2>6 · Lo que todavía NO se ha evaluado</h2>
<div class="callout bad"><ul>${H.notDone.map((n) => `<li>${md(n)}</li>`).join("")}</ul></div>`;
  }

  /* ------------------------------------------------------------------ INGENIERÍA */
  function ingenieria() {
    const cats = ["todas", ...new Set(ENG.map((e) => e.cat))];
    return `<h1>Acciones de ingeniería importantes</h1><p class="lead">${md(ENG_LEAD)}</p>
<div class="filters">${cats.map((c, i) => `<button class="chip ${i === 0 ? "on" : ""}" data-ecat="${esc(c)}">${esc(c)}</button>`).join("")}</div>
<div class="tablewrap"><table id="engT"><tr><th>Categoría</th><th>Qué pasó</th><th>Cómo se detectó</th><th>Qué se hizo</th><th>Lección</th></tr>
${ENG.map((e) => `<tr data-ecat="${esc(e.cat)}"><td>${pill(e.cat, { bug: "bad", seguridad: "warn", robustez: "acc", calidad: "info", rendimiento: "llm", proceso: "" }[e.cat])}</td><td><b>${esc(e.title)}</b><br>${md(e.what)}</td><td>${md(e.detect)}</td><td>${md(e.fix)}${e.files ? `<br><span class="small">${e.files.map((f) => link(f)).join(" ")}</span>` : ""}</td><td>${md(e.lesson)}</td></tr>`).join("")}</table></div>`;
  }

  /* ------------------------------------------------------------------ MODIFICAR */
  function modificar() {
    return `<h1>Escalar o modificar el proyecto</h1><p class="lead">${md(MOD_LEAD)}</p>
<h2>«Quiero…» → qué tocar y qué implica</h2>
<div class="filters"><input id="goalFilter" type="search" placeholder="Filtrar objetivos (ej. PDF, escalar, UI, embedder)…"></div>
<div id="goalList">${GOALS.map((g) => `<details class="adr goal" data-t="${esc((g.goal + " " + g.steps.join(" ") + g.implies).toLowerCase())}"><summary><span class="ttl">${esc(g.goal)}</span>${pill("esfuerzo: " + g.effort, { bajo: "good", medio: "warn", alto: "bad" }[g.effort])}${pill("riesgo: " + g.risk, { bajo: "good", medio: "warn", alto: "bad" }[g.risk])}</summary>
<div class="body"><h3>Pasos</h3><ol>${g.steps.map((s) => `<li>${md(s)}</li>`).join("")}</ol>
<p><b>Qué implica:</b> ${md(g.implies)}</p><p><b>Cómo verificar:</b> ${md(g.verify)}</p>
<p class="small">Archivos: ${g.files.map((f) => link(f)).join(" ")} ${g.adr ? `· Decisiones relacionadas: ${g.adr.map((a) => `<a href="#/adrs/${a}">${a}</a>`).join(" ")}` : ""}</p></div></details>`).join("")}</div>
<h2>Perillas de configuración</h2>
<p>Se cambian en <code>config/default.yaml</code> (o un YAML propio con <code>--config</code>). Nada de esto requiere tocar código.</p>
<div class="tablewrap"><table><tr><th>Perilla</th><th>Efecto</th><th>Si la subes</th><th>Si la bajas</th></tr>${KNOBS.map((k) => `<tr><td><code>${esc(k.k)}</code></td><td>${md(k.e)}</td><td>${md(k.up)}</td><td>${md(k.down)}</td></tr>`).join("")}</table></div>
<h2>¿Qué se rompe primero al crecer?</h2>
<div class="tablewrap"><table><tr><th>Escala</th><th>Qué pasa</th><th>Qué hacer</th></tr>${SCALE.map((s) => `<tr><td><b>${esc(s.n)}</b></td><td>${md(s.p)}</td><td>${md(s.d)}</td></tr>`).join("")}</table></div>`;
  }

  /* ------------------------------------------------------------------ REFERENCIA */
  function referencia() {
    const dirs = {};
    FILES.forEach((f) => { const d = f.includes("/") ? f.split("/").slice(0, f.startsWith("src/") ? 3 : 2).join("/") : "(raíz)"; (dirs[d] = dirs[d] || []).push(f); });
    return `<h1>Referencia rápida</h1>
<h2>Comandos</h2><div class="tablewrap"><table><tr><th>Comando</th><th>Para qué</th><th>Cuesta tokens</th></tr>${COMMANDS.map((c) => `<tr><td><code>${esc(c.c)}</code></td><td>${md(c.d)}</td><td>${esc(c.tok)}</td></tr>`).join("")}</table></div>
<h2>Variables de entorno (<code>.env</code>)</h2><div class="tablewrap"><table><tr><th>Variable</th><th>Para qué</th></tr>${ENVVARS.map((c) => `<tr><td><code>${esc(c.k)}</code></td><td>${md(c.d)}</td></tr>`).join("")}</table></div>
<h2>Estructura de archivos del repositorio</h2>
<div class="tablewrap"><table><tr><th>Carpeta</th><th>Qué contiene</th><th>Archivos</th></tr>${REPO.map((r) => `<tr><td><code>${esc(r.p)}</code></td><td>${md(r.d)}</td><td>${FILES.filter((f) => f === r.p || f.startsWith(r.p.endsWith("/") ? r.p : r.p + "/")).length}</td></tr>`).join("")}</table></div>
<details class="adr"><summary><span class="ttl">Ver los ${FILES.length} archivos</span></summary><div class="body"><pre><code>${esc(FILES.join("\n"))}</code></pre></div></details>
<h2>Limitaciones conocidas y deuda técnica</h2><div class="callout warn"><ul>${LIMITS.map((l) => `<li>${md(l)}</li>`).join("")}</ul></div>`;
  }

  /* ------------------------------------------------------------------ bindings */
  const bind = {
    arquitectura(param) {
      const key = param === "ingest" ? "ingest" : "query";
      $$(".flow .node").forEach((g) => {
        const on = () => { $$(".flow .node").forEach((x) => x.classList.remove("on")); g.classList.add("on"); $("#nodepanel").innerHTML = nodePanel(key, g.dataset.id); };
        g.addEventListener("click", on);
        g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); on(); } });
      });
    },
    recorrido() { drawSteps(); $("#repairChk").onchange = (e) => { stepState.repair = e.target.checked; stepState.i = 0; drawSteps(); }; },
    codigo(param) {
      const sel = (p) => $$("#tree .file").forEach((a) => a.classList.toggle("on", a.dataset.p === p));
      sel(param);
      $("#treeFilter").oninput = (e) => { $("#tree").innerHTML = treeHtml(e.target.value); sel(parseHash().param); };
    },
    adrs(param) {
      const apply = () => {
        const q = ($("#adrFilter").value || "").toLowerCase(); const chip = $(".chip.on[data-area]"); const area = chip ? chip.dataset.area : "todas";
        $$("#adrList details").forEach((d) => {
          const a = ADRS.find((x) => x.id === d.id);
          const hay = JSON.stringify(a).toLowerCase();
          d.classList.toggle("hide", !(hay.includes(q) && (area === "todas" || a.area === area)));
        });
      };
      $("#adrFilter").oninput = apply;
      $$(".chip[data-area]").forEach((c) => (c.onclick = () => { $$(".chip[data-area]").forEach((x) => x.classList.remove("on")); c.classList.add("on"); apply(); }));
      $("#adrAll").onclick = () => { const o = $$("#adrList details")[0].open; $$("#adrList details").forEach((d) => (d.open = !o)); };
      if (param) { const el = document.getElementById(param); if (el) { el.open = true; el.scrollIntoView(); } }
    },
    conceptos() {
      const apply = () => {
        const q = ($("#gFilter").value || "").toLowerCase(); const chip = $(".chip.on[data-cat]"); const cat = chip ? chip.dataset.cat : "todos";
        $$("#gList .gl").forEach((c) => c.classList.toggle("hide", !(c.dataset.t.includes(q) && (cat === "todos" || c.dataset.cat === cat))));
      };
      $("#gFilter").oninput = apply;
      $$(".chip[data-cat]").forEach((c) => (c.onclick = () => { $$(".chip[data-cat]").forEach((x) => x.classList.remove("on")); c.classList.add("on"); apply(); }));
      const h = parseHash().param; if (h) { const el = document.getElementById(h); if (el) el.scrollIntoView(); }
    },
    ingenieria() {
      $$(".chip[data-ecat]").forEach((c) => (c.onclick = () => {
        $$(".chip[data-ecat]").forEach((x) => x.classList.remove("on")); c.classList.add("on");
        $$("#engT tr[data-ecat]").forEach((r) => r.classList.toggle("hide", c.dataset.ecat !== "todas" && r.dataset.ecat !== c.dataset.ecat));
      }));
    },
    modificar() { $("#goalFilter").oninput = (e) => { const q = e.target.value.toLowerCase(); $$("#goalList .goal").forEach((d) => d.classList.toggle("hide", !d.dataset.t.includes(q))); }; },
  };

  /* ------------------------------------------------------------------ global search */
  let index = null;
  function buildIndex() {
    index = [];
    ADRS.forEach((a) => index.push({ k: "Decisión", t: `${a.id} · ${a.title}`, s: a.one, h: `#/adrs/${a.id}`, x: JSON.stringify(a).toLowerCase() }));
    GLOSSARY.forEach((g) => index.push({ k: "Concepto", t: g.term, s: g.simple, h: `#/conceptos/c-${g.term.replace(/\W+/g, "-").toLowerCase()}`, x: (g.term + g.simple + g.here).toLowerCase() }));
    GOALS.forEach((g) => index.push({ k: "Modificar", t: g.goal, s: g.implies, h: "#/modificar", x: (g.goal + g.steps.join(" ")).toLowerCase() }));
    ENG.forEach((e) => index.push({ k: "Ingeniería", t: e.title, s: e.what, h: "#/ingenieria", x: (e.title + e.what + e.fix).toLowerCase() }));
    Object.entries(CODEMAP).forEach(([p, m]) => {
      if (m.lines <= 1) return;
      index.push({ k: "Archivo", t: p, s: (MODULES[p] || {}).purpose || m.doc, h: `#/codigo/${p}`, x: (p + " " + ((MODULES[p] || {}).purpose || "")).toLowerCase() });
      m.functions.forEach((f) => index.push({ k: "Función", t: `${f.name}  ·  ${p}`, s: FN[`${p}:${f.name}`] || f.doc, h: `#/codigo/${p}`, x: (f.name + " " + (FN[`${p}:${f.name}`] || f.doc)).toLowerCase() }));
      m.classes.forEach((c) => index.push({ k: "Clase", t: `${c.name}  ·  ${p}`, s: FN[`${p}:${c.name}`] || c.doc, h: `#/codigo/${p}`, x: (c.name + " " + (FN[`${p}:${c.name}`] || c.doc)).toLowerCase() }));
    });
  }
  function doSearch(q) {
    const box = $("#gresults");
    q = q.trim().toLowerCase();
    if (q.length < 2) { box.hidden = true; return; }
    if (!index) buildIndex();
    const toks = q.split(/\s+/);
    const res = index.filter((i) => toks.every((t) => i.x.includes(t))).map((i) => ({ i, sc: (i.t.toLowerCase().includes(q) ? 2 : 0) + (i.t.toLowerCase().startsWith(q) ? 1 : 0) }))
      .sort((a, b) => b.sc - a.sc).slice(0, 12);
    box.innerHTML = res.length ? res.map((r) => `<a href="${esc(r.i.h)}"><b>${esc(r.i.t)}</b> <span class="pill">${r.i.k}</span><small>${esc((r.i.s || "").slice(0, 120))}</small></a>`).join("") : '<a><small>Sin resultados</small></a>';
    box.hidden = false;
  }

  /* ------------------------------------------------------------------ boot */
  function applyTheme(t) {
    if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("guide-theme", t); } catch (e) { /* storage may be blocked */ }
  }
  let theme = "auto"; try { theme = localStorage.getItem("guide-theme") || "auto"; } catch (e) { /* ignore */ }
  applyTheme(theme);
  $("#themeBtn").onclick = () => { theme = { auto: "light", light: "dark", dark: "auto" }[theme]; applyTheme(theme); $("#themeBtn").title = "Tema: " + theme; };
  $("#menuBtn").onclick = () => $("#nav").classList.toggle("open");
  const gs = $("#gsearch");
  gs.addEventListener("input", () => doSearch(gs.value));
  gs.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("#gresults").hidden = true; gs.blur(); } if (e.key === "Enter") { const a = $("#gresults a"); if (a && a.href) location.href = a.href; } });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) $("#gresults").hidden = true; else if (e.target.closest("#gresults a")) setTimeout(() => { $("#gresults").hidden = true; gs.value = ""; }, 50); });
  document.addEventListener("keydown", (e) => { if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); gs.focus(); } });
  window.addEventListener("hashchange", route);
  route();
})();
