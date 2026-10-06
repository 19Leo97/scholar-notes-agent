# scholar-notes-agent

A research agent that answers questions and **checks your ideas** against three sources at once: your own
notes (Markdown / Obsidian / plain text), the scientific literature, and the open web. It was built for
theoretical neuroscience but nothing in it is domain specific.

What makes it different:

* **Everything is referenced.** Personal notes are cited with file, line range and `[[wikilink#section]]`;
  papers with APA reference + DOI checked against Crossref/DataCite; web pages with URL and access date.
  Each claim carries a verbatim quote that is string-matched against the source; claims that fail are removed.
* **The agent's own ideas are labelled as such** (`[IA-1]`, with the evidence that inspired them) and kept
  apart from sourced claims. Your own `HIP —` notes are tagged "your hypothesis", never passed off as fact.
* **Choose the sources**: `--mode notes` (only your notes, zero external calls, enforced by construction),
  `--mode literature` (papers + web only), or `--mode hybrid`.
* **Private by design**: embeddings and index are local; only the question and selected excerpts reach the
  LLM provider; the app refuses free-tier Gemini; queries that copy text from your notes are blocked from
  leaving the machine. See [docs/privacy.md](docs/privacy.md).
* **Token-aware**: per-query budgets, role-based model routing, compact tool outputs, caches, and a ledger.
  Every answer prints its token and USD cost. See [docs/token-efficiency.md](docs/token-efficiency.md).
* **Evaluated on external data first** (SciFact, PubMedQA), not on the author's notes.
  See [docs/evaluation.md](docs/evaluation.md).

Real output on the bundled demo vault, produced by a **3B local model** (`config/local.yaml`, no API keys;
larger hosted models should write better, but they have not been benchmarked here yet; the referencing machinery is the same):

```
$ research ask "¿Por qué el receptor NMDA actúa como detector de coincidencia?" --mode notes

Funcionamiento del receptor NMDA como detector de coincidencia
El receptor NMDA solo permite el paso de calcio cuando coinciden la liberación presináptica de
glutamato y la despolarización postsináptica. [N1]

💡 Ideas del agente (no provienen de tus fuentes)
 • [IA-1] ... (basada en: especulativa, sin evidencia de apoyo)

Referencias
Notas personales
 • [N1] CON — Receptor NMDA como detector de coincidencia —
   plasticidad/CON — Receptor NMDA como detector de coincidencia.md:11-12 ·
   [[CON — Receptor NMDA como detector de coincidencia#En una línea]] · concept
   ▌ “El receptor NMDA solo permite el paso de calcio cuando coinciden la liberación presináptica ...”
Ideas del agente (no provienen de tus fuentes)
 • [IA-1] Propuesta del agente (llama3.2:3b, 2026-10-01) — basada en: especulativa, sin evidencia de apoyo
-------------------------------------------------------------------------------
Uso: 6,859 in / 942 out tokens · ~$0.0000 · 5 LLM calls · 1 tool calls
```

**New here?** Open the interactive visual guide, [docs/guide.html](docs/guide.html) (download it and open it in a browser; no server needed). It explains the architecture, every file and function, the design decisions with their alternatives, and every evaluation run. Rebuild it with `python docs/build_guide.py`.

## Quickstart

Requires Python ≥ 3.11 and, for local embeddings, [Ollama](https://ollama.com).

```bash
git clone <this repo> && cd scholar-notes-agent
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                       # add GROQ_API_KEY (and GOOGLE_API_KEY if you use Gemini)
ollama pull bge-m3                                         # multilingual embeddings, runs on CPU

research ingest examples/demo_vault --source demo          # public demo vault (ES/EN, messy)
research search "receptor NMDA coincidencia"               # retrieval only, 0 LLM tokens
research ask "¿Por qué el receptor NMDA actúa como detector de coincidencia?" --mode notes
research ask "Does LTP require protein synthesis?" --mode literature
research ask "La metaplasticidad estabiliza engramas" --mode hybrid --budget 0.03 --save
```

**First-run cost on CPU.** Embedding is the slow part of ingestion. Measured on a CPU-only laptop,
`nomic-embed-text` indexed ~5,200 abstracts in roughly 35-40 minutes (about 2 chunks/s); `bge-m3` is a larger
model and will be several times slower, so a first ingestion of thousands of notes can take hours. Try a subfolder
first, pick a smaller embedder in `config/default.yaml` if needed, and remember later runs only embed what changed.

Point it at your own notes with `research ingest "C:/path/to/vault"`. It indexes `.md` and `.txt`
(frontmatter, wikilinks with relation labels, embeds, URLs, Notion-export hashes, legacy encodings),
incrementally, so re-running over thousands of notes only processes what changed.

No API keys yet? Everything except the LLM calls works: `ingest`, `search`, `doctor`, `usage`, the test-suite
and the retrieval evaluation. For a fully offline setup use `provider: ollama` for every role in a config file
passed with `--config`.

### Commands

| Command | Purpose |
|---|---|
| `research ingest PATH` | Index notes (incremental, `--rebuild` to re-embed) |
| `research ask "..." --mode notes\|literature\|hybrid` | Answer / verify an idea; `--budget USD`, `--save` (writes an Obsidian `SIN —` note), `--show-evidence` |
| `research search "..."` | Retrieval only: dense / sparse / hybrid, no LLM cost |
| `research doctor` | Empty, duplicate and orphan notes; broken wikilinks |
| `research usage` | Tokens and USD by model and role from the ledger |
| `research eval <suite>` | `retrieval`, `retrieval-es`, `verification`, `pubmedqa`, `vault`, `references` |

## How it works

`plan → seed retrieval → research loop (tool calling) → synthesize → verify → render`, implemented as a
LangGraph state machine. Details and a diagram in [docs/architecture.md](docs/architecture.md).

* Retrieval: heading-aware chunks with exact line ranges → Qdrant hybrid search (dense `bge-m3` + hashed
  BM25 with IDF, fused by RRF) → optional cross-encoder → MMR → 1-hop wikilink expansion.
* Tools: `search_notes`, `get_note`, `follow_links`, `search_papers` (OpenAlex, Europe PMC, arXiv,
  Semantic Scholar), `get_paper_details`, `web_search` (Tavily / DuckDuckGo), `fetch_url`.
* Models: router and judge on a small Groq model, tool-calling agent on a larger Groq model, final synthesis on
  paid Gemini Flash. All configurable per role in [config/default.yaml](config/default.yaml).

## Results

### E1 · Retrieval ablation (measured)

SciFact dev: 188 claims with gold evidence, 5,183 abstracts indexed through the real ingestion pipeline,
`nomic-embed-text` embeddings on CPU (`research eval retrieval`, report in `eval/reports/`).

| config | nDCG@10 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| BM25 (hashed lexical, IDF) | 0.821 | 0.880 | 0.933 | 0.789 |
| dense | 0.844 | 0.899 | 0.966 | 0.816 |
| **hybrid (RRF)** | **0.867** | **0.920** | **0.976** | **0.840** |

Fusing both rankings beats each component, which is why hybrid is the default. These are dev-split
numbers on this implementation, not comparable to published BEIR test-split figures.

### E2 – E5 · Agent-level suites (implemented, not yet run with live models)

`verification` (SciFact claims → SUPPORTED / REFUTED / INSUFFICIENT), `pubmedqa` (QA with citations),
`vault` (end-to-end on the demo vault, mode compliance, abstention) and `references` (DOI validity) need LLM
API keys and are budget-capped (`--limit`, response cache). The harness, metrics and benchmark data are
unit-tested and the whole agent graph is covered by scripted-model integration tests; the live numbers will be
added here once they are run. See [docs/evaluation.md](docs/evaluation.md).

## Project layout

```
src/scholar_agent/   ingestion/ indexing/ retrieval/ tools/ citations/ agent/ budget/ privacy/ evaluation/
config/              default.yaml, pricing.yaml
examples/demo_vault/ public synthetic notes (ES/EN, .md and messy .txt, images, wikilinks)
tests/               unit + integration (scripted chat model: no keys, no network)
eval/reports/        saved evaluation runs
docs/                architecture, privacy, evaluation, token efficiency
```

`make check` runs lint, type-check and tests.

## Limitations

* Images inside notes are recorded as metadata (name, surrounding text) and cited, not read; OCR / vision is an extension point (`Loader`).
* Literature text is limited to abstracts and metadata; full-text retrieval is not implemented.
* Claim verification is lexical (quotes must appear in the source); it catches fabricated or misattributed quotes, not subtle misreadings. The optional LLM judge covers faithfulness at extra cost.
* Qdrant local mode is single-process; use a Qdrant server (`QdrantStore(url=...)`) for concurrent access.
* Model prices in `config/pricing.yaml` are editable estimates; verify them against the providers' pricing pages.

## License

MIT
