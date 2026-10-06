# Plan — Agente de investigación con notas personales + literatura científica (RAG + tool calling)

## Contexto

Quieres un agente que responda preguntas, verifique ideas y consulte información de neurociencia teórica combinando tres fuentes: (1) tus notas personales (+3000, desordenadas, Obsidian `.md` y `.txt` sin formato, ES/EN, con imágenes y enlaces), (2) artículos científicos, (3) web general. El agente busca por su cuenta. Requisitos clave:

- **Todo referenciado**: notas (con ubicación exacta), papers (DOI verificado), web (URL + fecha) y **las ideas propias de la IA etiquetadas como tales**.
- **Modos**: solo notas / solo literatura / híbrido.
- **Privacidad**: tus datos no se usan para entrenar modelos (Groq + Gemini **pago**; tier gratuito de Gemini bloqueado).
- **Control y eficiencia de tokens** medibles.
- **Evaluación rigurosa, primero con datos externos**, no con tus notas.
- Código escalable, usable por cualquiera que clone el repo, presentable en GitHub para perfil de AI Engineer.

El directorio del proyecto está vacío; se construye desde cero. Se reutiliza el conocimiento del formato de tu vault (`Obsidian vaults/Neuro/.claude/skills/obsidian/vault-format/SKILL.md`): prefijos `CON/HIP/PRG/RES/SIN/MAPA —`, frontmatter (`tipo, estado, area, fuentes, doi, año, tags`), sección `## Relaciones` con wikilinks semánticos, embeds `![[img.png]]`.

Decisiones tomadas: **LangGraph**, interfaz **CLI (Typer)**, notas en **Markdown Obsidian + .txt plano**, LLM **Groq (roles baratos) + Gemini pago (síntesis)**. Todo el código, nombres y prompts en inglés; documentación del repo en inglés (con README en ES opcional).

---

## Stack

| Capa | Elección | Por qué |
|---|---|---|
| Paquetes | `uv`, Python 3.11+, `pyproject.toml` | reproducible, rápido |
| Orquestación | LangGraph | grafo explícito, control por nodo |
| LLM | `langchain-groq`, `langchain-google-genai`, `langchain-ollama` (opcional, 100% local) | multi‑proveedor por rol |
| Embeddings | **local**: `bge-m3` vía Ollama (multilingüe, cross‑lingual ES↔EN), fallback `fastembed` | notas nunca salen para indexarse; CPU, <16 GB |
| Sparse/BM25 | `fastembed` `Qdrant/bm25` | siglas técnicas (LTP, NMDAR) |
| Vector DB | **Qdrant modo local** (en disco, sin Docker) → URL de servidor por config | híbrido dense+sparse con fusión RRF; escala sin cambiar código |
| Reranker | `fastembed` `jina-reranker-v2-base-multilingual` (ONNX, CPU) | sin torch, multilingüe |
| Catálogo/ledger/caché | SQLite | metadatos de notas, gasto de tokens, caché HTTP/LLM |
| Literatura | OpenAlex, Semantic Scholar, Europe PMC (PubMed), arXiv; Crossref para verificar DOI | gratuitas, cobertura neuro |
| Web | Tavily (free tier) con fallback `ddgs`; extracción con `trafilatura` | |
| Calidad | ruff, mypy, pytest, GitHub Actions | |

IDs de modelos **solo en config** (se verifican al implementar): router/juez Groq pequeño (p. ej. `llama-3.1-8b-instant`), agente con tool calling Groq grande (p. ej. `openai/gpt-oss-120b`), síntesis Gemini Flash pago.

---

## Estructura del repo (nombre propuesto: `scholar-notes-agent`)

```
pyproject.toml  .env.example  Makefile  README.md
config/default.yaml        # modes, budgets, top_k, chunking, providers per role
config/pricing.yaml        # USD per 1M tokens per model
src/scholar_agent/
  config.py                # pydantic-settings; validates privacy rules
  cli.py                   # ingest | ask | search | usage | eval | doctor
  llm/factory.py           # get_chat_model(role) -> router|agent|synthesizer|judge
  ingestion/
    loaders/base.py        # Loader Protocol + registry (by extension)
    loaders/obsidian.py    # frontmatter, wikilinks, embeds, callouts, URLs, headings
    loaders/plaintext.py   # .txt without structure
    chunker.py             # heading-aware split; paragraph split for .txt; contextual header "title > section"
    pipeline.py            # incremental (content hash), language detection, metadata inference
  indexing/
    embedder.py            # Embedder Protocol: OllamaEmbedder, FastEmbedEmbedder
    vectorstore.py         # VectorStore Protocol: QdrantStore (dense+sparse)
    reranker.py  catalog.py (SQLite: notes, links graph, chunks)
  retrieval/
    hybrid.py              # dense+BM25 -> RRF -> rerank
    graph_expand.py        # 1-hop over wikilinks ("Parte de", "Relacionada con")
    packer.py              # MMR + per-evidence and total token budget
  tools/
    registry.py            # tools per mode (notes / literature / hybrid)
    notes.py               # search_notes, get_note, follow_links
    literature/{openalex,semantic_scholar,europepmc,arxiv,crossref}.py
    web.py                 # web_search, fetch_url
  citations/
    evidence.py            # EvidenceStore: stable ids N1.., P1.., W1.., IA-1..
    validator.py           # every claim cited, ids exist, quote grounding, DOI verified
    formatter.py           # APA for papers, [[wikilink#section]] + path:lines for notes
  agent/
    state.py  graph.py  schemas.py (Pydantic structured outputs)
    nodes/{plan,research,synthesize,verify,render}.py
    prompts/*.md           # versioned prompts
  budget/{ledger,guard,pricing}.py
  privacy/outbound_guard.py
  cache/{http_cache,llm_cache}.py
eval/
  datasets/{scifact,pubmedqa,demo_vault}.py
  metrics/{retrieval,citation,verification,judge}.py
  runners/  reports/  (versioned results: config hash + metrics + cost)
examples/demo_vault/       # public synthetic vault (ES/EN, messy .txt, images, links)
tests/unit  tests/integration   # fake chat model, no API keys needed
docs/{architecture.md (mermaid), privacy.md, evaluation.md, token-efficiency.md}
.github/workflows/ci.yml
```

`.gitignore` excluye `data/`, `.index/`, `.cache/`, `.env`, `eval/private/` → tus notas e índices **nunca** se suben.

Escalabilidad: cada pieza intercambiable es un `Protocol` + registro (loaders, embedders, vector stores, herramientas de literatura, proveedores LLM); añadir PDF, otra API o pgvector = un archivo nuevo + una línea de config. I/O de APIs asíncrono con rate limiting.

---

## Ingesta (notas desordenadas)

- Recorre carpeta(s) configuradas; `.md` y `.txt`. Indexación **incremental** por hash (re‑ingestar 3000 notas solo procesa las cambiadas).
- Metadatos inferidos si faltan: título (frontmatter → primer `#` → nombre de archivo sin hash), tipo por prefijo (`HIP —` ⇒ hipótesis propia), idioma, fecha (mtime), tags.
- Wikilinks → grafo de notas en SQLite (para expansión 1‑hop y para citar relaciones).
- Imágenes: se registran como metadato del chunk (nombre + texto circundante) y se citan si el chunk se usa; sin OCR en v1 (extensible vía loader).
- URLs dentro de notas: guardadas como metadato; el agente puede abrirlas con `fetch_url`.
- Chunks ~350–500 tokens, por encabezado; cada chunk guarda `path`, `heading`, `line_start/line_end` → cita exacta.
- `research doctor`: reporte determinista (sin LLM) de notas vacías, duplicadas, links rotos — útil dado el desorden.

## Grafo del agente (LangGraph)

```
plan ──► seed_retrieval ──► research (ReAct tool loop, budget-guarded) ──► synthesize ──► verify ──► render
                                   ▲                                                      │ fail (1 repair max)
                                   └──────────────────────────────────────────────────────┘
```

1. **plan** (Groq pequeño, salida estructurada): intención (`question | verify_idea | lookup`), sub‑preguntas, consultas en ES **y** EN (literatura es en inglés), herramientas necesarias. Respeta el modo.
2. **seed_retrieval** (sin LLM): búsqueda híbrida en notas y/o 1 ronda de literatura en paralelo → evita iteraciones del agente.
3. **research** (Groq grande, tool calling): decide si necesita más: `search_notes`, `get_note`, `follow_links`, `search_papers`, `get_paper_details`, `web_search`, `fetch_url`. Herramientas filtradas por modo (en `--mode notes` las externas ni siquiera se registran). Toda salida de herramienta entra al `EvidenceStore` con ID estable y se devuelve **compacta** (título, año, DOI, fragmento recortado), nunca JSON crudo.
4. **synthesize** (Gemini pago): salida Pydantic — `claims[{text, citations[ids], quotes[]}]`, `ai_ideas[{id: IA-n, idea, rationale, based_on[ids]}]`, para `verify_idea`: veredicto `SUPPORTED | REFUTED | MIXED | INSUFFICIENT`, y `gaps`. Responde en el idioma de la pregunta.
5. **verify** (determinista primero): cada afirmación tiene ≥1 cita; IDs existen; cada cita trae una cita textual corta que debe aparecer en la evidencia (grounding barato por coincidencia de cadena); DOIs resueltos y título coincidente vía Crossref/OpenAlex (referencias alucinadas = 0). Si falla: 1 pasada de reparación; lo que siga sin respaldo se elimina o se marca.
6. **render**: Markdown con citas en línea `[N3] [P2] [W1] [IA-1]` y bibliografía agrupada:
   - **Notas personales**: `[[CON — Captura sináptica#Desarrollo]]` · `plasticidad sinaptica/CON — Captura sináptica.md:14-16`
   - **Artículos**: APA completo + `https://doi.org/...` + ✔ verificado (fuente de metadatos)
   - **Web**: título, sitio, URL, fecha de acceso
   - **Ideas del agente**: `IA-1 — Propuesta del agente (modelo, fecha), basada en [N3][P2]; no verificada en literatura`
   - Pie: tokens in/out por rol, costo USD, nº de llamadas a herramientas.
   - Opción `--save` escribe la respuesta como nota `SIN —` compatible con tu vault.

CLI: `research ask "¿...?" --mode notes|literature|hybrid --budget 0.02 --save`, `research ingest <path>`, `research search "..."` (solo retrieval, 0 tokens LLM), `research usage --last 30d`, `research eval <suite>`.

## Control de tokens

- **TokenLedger**: callback de LangChain captura `usage_metadata` por nodo/modelo → costo con `pricing.yaml` → SQLite; resumen tras cada respuesta y `research usage`.
- **BudgetGuard**: límites por consulta (`max_cost_usd`, `max_input_tokens`, `max_tool_calls`, `max_iterations`); al acercarse fuerza ir a `synthesize` con la evidencia actual en vez de fallar.
- **Ruteo por rol**: modelo pequeño para plan/juez, grande solo donde agrega calidad.
- **Empaquetado de contexto**: rerank + MMR + presupuesto por evidencia y total (p. ej. 6k tokens); abstracts primero, texto completo solo si el agente lo pide.
- **Cachés**: respuestas HTTP de APIs (SQLite), embeddings por hash, respuestas LLM en evaluación (re‑ejecutar evals no cuesta), prefijo de sistema estable para aprovechar caché implícita de Gemini.
- La evaluación reporta **calidad vs costo** por configuración (curva de Pareto) → evidencia de “buena respuesta con buen uso de tokens”.

## Privacidad

- Embeddings e índice **locales**. A los proveedores solo llegan la pregunta y los fragmentos seleccionados.
- `config.py` valida: Gemini requiere `gemini.paid_tier: true` explícito (tier gratuito entrena con datos → se rehúsa arrancar); Groq documentado (no entrena con datos de clientes). `provider: ollama` = modo totalmente offline.
- **OutboundGuard**: las consultas a APIs de búsqueda/web se revisan contra los chunks de notas (solapamiento de n‑gramas); si contienen texto literal de tus notas se bloquean/reescriben → tus notas no se filtran a buscadores.
- `docs/privacy.md` con tabla “qué sale, a dónde, con qué política”.

---

## Evaluación (primero externa)

Todas las suites corren con `research eval <suite>`, guardan config + hash de prompts + métricas + costo en `eval/reports/`, y la tabla resumen va al README.

| Suite | Datos (externos) | Qué mide | Métricas |
|---|---|---|---|
| **E1 Retrieval** | BEIR **SciFact** (5k abstracts, claims de test) + claims **traducidos al español** (una vez, cacheados) | recuperación mono y cross‑lingual (como tus notas ES vs literatura EN) | nDCG@10, Recall@k, MRR; ablaciones dense / BM25 / híbrido / +rerank / +graph / tamaño de chunk |
| **E2 Verificación de ideas** | SciFact labels SUPPORT/CONTRADICT/NEI, corpus usado como “notas” | modo `verify_idea` | accuracy, macro‑F1, precisión de citas vs documentos gold |
| **E3 QA con citas** | **PubMedQA** (pqa‑labeled) | respuesta + grounding | accuracy yes/no/maybe, faithfulness, citation precision/recall (estilo ALCE) |
| **E4 End‑to‑end vault** | `examples/demo_vault` (sintético, licencia abierta, ES/EN, desordenado) + preguntas generadas y revisadas | sistema completo por modo | % afirmaciones citadas (objetivo 100%), etiquetado correcto de IA‑n, **cumplimiento de modo** (modo notas ⇒ 0 llamadas externas), tokens/costo/latencia |
| **E5 Validez de referencias** | ~30 preguntas de neurociencia en modo literatura | anti‑alucinación | % DOIs que resuelven y coinciden (objetivo 100%), duplicados |

- Métricas deterministas donde se pueda; juez LLM (Groq, familia distinta al generador) solo para faithfulness/relevancia, con prompts versionados y **acuerdo juez‑humano** reportado sobre ~30 casos etiquetados a mano.
- Modo `--limit N` para smoke tests baratos; CI corre E1 en un subconjunto y E4 con modelo falso (sin claves).
- Fase posterior (privada, `eval/private/`, ignorada por git): ~50 preguntas sobre tus notas reales.

---

## Fases de implementación

1. **F0 Scaffolding**: uv, config, `.env.example`, `.gitignore` protector, CI (ruff/mypy/pytest), ledger de tokens básico.
2. **F1 Ingesta + índice**: loaders Obsidian/txt, chunker, Qdrant híbrido, reranker, grafo de links, `ingest`/`search`/`doctor`; crear `examples/demo_vault`.
3. **F2 Eval E1**: baseline de retrieval y ablaciones **antes** de construir el agente.
4. **F3 Herramientas externas**: literatura (OpenAlex/S2/EuropePMC/arXiv), Crossref, web, caché HTTP, OutboundGuard.
5. **F4 Agente**: grafo LangGraph, EvidenceStore, salidas estructuradas, verify/render, modos, BudgetGuard, `ask`.
6. **F5 Eval E2–E5**: runners, juez, reportes, curva calidad‑costo.
7. **F6 Portafolio**: README (diagrama, tabla de resultados, GIF de terminal), docs, luego indexar tus notas reales y eval privada.

## Verificación

- `uv sync && make lint test` — unit tests (parsers de wikilinks/frontmatter, chunker con números de línea, validator de citas, guard de presupuesto, filtro de herramientas por modo) e integración con fake LLM, sin claves.
- `research ingest examples/demo_vault && research search "captura sináptica"` → resultados con path y líneas, 0 tokens LLM.
- `research ask "..." --mode notes` → solo citas `N*`, ledger muestra 0 llamadas externas.
- `research ask "..." --mode literature` → solo `P*`/`W*`, todos los DOI con ✔.
- `research ask "Mi idea: ..." --mode hybrid` → veredicto + `IA-n` etiquetadas + pie de costo dentro del `--budget`.
- `research eval scifact-retrieval --limit 50` y `research eval demo-vault` → reportes en `eval/reports/` con métricas y costo.
