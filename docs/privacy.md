# Privacy model

The goal: the agent reads your notes and searches the open web, **without your notes being used to train
anyone's models**.

| Data | Where it goes | Policy / control |
|---|---|---|
| Note files, chunks, embeddings, index | Your disk only (`.index/`, git-ignored) | Embeddings are computed locally (Ollama `bge-m3` or fastembed) |
| Question + selected note excerpts | The configured LLM provider, per query | Groq and **paid** Gemini API: API data is not used for training. Free-tier Gemini may use prompts for product improvement, so the app **refuses to start** with Gemini unless `GEMINI_PAID_TIER=true` |
| Search queries | OpenAlex, Europe PMC, arXiv, Crossref/DataCite, Tavily or DuckDuckGo | `OutboundGuard` blocks queries that copy ≥ 8 consecutive words from a note the model has seen; the tool tells the model to rewrite as generic keywords |
| URLs fetched by the agent | The target site | SSRF guard: only public `http(s)` hosts; `localhost`, private ranges, link-local and `file://` are refused |
| Usage ledger | Local SQLite (`.index/usage.sqlite`) | Stores token counts, cost and the first 200 characters of each question |

Fully offline operation: set every role to `provider: ollama` and `modes` to notes only; nothing leaves the machine.

Always check the current data-usage terms of each provider; they can change. This repository ships with
no notes, no keys and no indexes: `.gitignore` excludes `data/`, `.index/`, `.cache/`, `.env` and `eval/private/`.

## Untrusted content

Web pages, abstracts and even notes can contain text that tries to steer the model (prompt injection). The agent has
no write or execution tools, tool results are labelled as untrusted data in the prompts, answers are structured and
machine-verified, and fetches are SSRF-guarded (every redirect hop is checked). This reduces but does not remove the
risk; do not point the agent at pages you would not open yourself.
