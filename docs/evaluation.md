# Evaluation

Design rule: **evaluate on external data first**. None of the suites below touches the author's notes;
a private suite on real notes is a later, local-only step (`eval/private/` is git-ignored).

| Suite | Command | Data | Measures |
|---|---|---|---|
| E1 retrieval | `research eval retrieval` | SciFact (5,183 abstracts, 188 dev claims with evidence), indexed through the real ingestion pipeline | nDCG@10, Recall@5/10, MRR@10, latency; ablation: BM25 / dense / hybrid RRF / + cross-encoder |
| E1b cross-lingual | `research eval retrieval-es` | same claims translated to Spanish by the router model (cached) | does a Spanish query find English evidence (your real situation) |
| E2 idea verification | `research eval verification --limit 45` | SciFact dev claims, stratified SUPPORT / CONTRADICT / NEI, corpus used as the "notes" | accuracy, macro-F1, citation precision/recall against gold evidence documents |
| E3 QA with citations | `research eval pubmedqa --limit 40` | PubMedQA (pqa-labeled), abstracts as notes plus distractors | accuracy vs majority baseline, gold-abstract citation recall/precision, optional judge faithfulness |
| E4 end-to-end | `research eval vault` | `examples/demo_vault` (synthetic, bilingual, messy) + 15 questions | gold-note recall, keyword coverage, verdict accuracy, correct abstention, DOI / own-hypothesis tagging, **mode compliance**, `[IA-n]` labelling, pre-pruning claim support rate |
| E5 references | `research eval references` | 20 neuroscience questions, live APIs | share of cited DOIs verified by Crossref/DataCite, mismatches, duplicates |

Flags: `--limit N` (cheap smoke runs), `--judge` (LLM-as-judge faithfulness/relevance), `--offline`
(skip live-API items), `--no-cache`. Every run writes `eval/reports/<suite>-<timestamp>.json` (config
fingerprint, prompt hash, per-item records) and `eval/reports/latest-<suite>.md`.

## Reading the numbers honestly

* "Raw claim support rate (before pruning)" is the share of claims the synthesizer got right on the first
  attempt. The final answer is always 100 % supported because unsupported claims are deleted; the raw rate is
  the real measure of the model.
* SciFact dev numbers are not directly comparable to published BEIR (test split) figures.
* An LLM judge is a proxy. `metrics.cohens_kappa` is provided to measure judge/human agreement on a hand-labelled sample.
* Small `--limit` values have wide confidence intervals; treat them as smoke tests.
* Cached LLM responses keep their token counts, so a cached re-run reports the cost a live run would have had.

## CI

`pytest` runs without keys: the agent graph is tested end-to-end with a scripted chat model
(`tests/fakes.py`), and the benchmark data is validated (`tests/unit/test_evaluation.py`).
