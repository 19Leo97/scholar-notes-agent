"""E1 - retrieval quality on SciFact (external scientific data), with ablations.

Configs: lexical BM25 | dense | hybrid (RRF) | hybrid + cross-encoder rerank. The cross-lingual
variant queries with Spanish claims against the English corpus, mirroring Spanish notes vs English papers.
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from rich.console import Console

from scholar_agent.budget.tracking import QueryTracker
from scholar_agent.config import Settings
from scholar_agent.evaluation import metrics as M
from scholar_agent.evaluation.common import eval_cache, eval_services
from scholar_agent.evaluation.datasets import (
    SciFactClaim,
    load_scifact_claims,
    materialize_scifact,
    scifact_doc_id,
)
from scholar_agent.evaluation.report import md_table, write_report
from scholar_agent.llm.factory import ModelHub, invoke_structured
from scholar_agent.services import Services


class Translations(BaseModel):
    items: list[str]


def load_or_make_translations(settings: Settings, claims: list[SciFactClaim], console: Console) -> dict[int, str]:
    path = eval_cache(settings) / "scifact_dev_es.json"
    cached: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    missing = [c for c in claims if str(c.id) not in cached]
    if missing:
        console.print(f"Translating {len(missing)} claims to Spanish with the router model (cached afterwards)...")
        hub = ModelHub(settings, QueryTracker(settings))
        for i in range(0, len(missing), 10):
            batch = missing[i : i + 10]
            payload = json.dumps([c.claim for c in batch], ensure_ascii=False)
            out = invoke_structured(
                hub, "router", Translations,
                [SystemMessage("Translate each scientific claim to Spanish, keeping technical terms and "
                               "acronyms. Return the same number of items in the same order."),
                 HumanMessage(payload)],
            )
            if len(out.items) != len(batch):
                raise RuntimeError("Translation batch returned a different number of items")
            cached.update({str(c.id): t for c, t in zip(batch, out.items, strict=True)})
            path.write_text(json.dumps(cached, ensure_ascii=False, indent=1), encoding="utf-8")
    return {c.id: cached[str(c.id)] for c in claims}


def _rank_docs(hits) -> list[str]:
    seen: list[str] = []
    for h in hits:
        doc = scifact_doc_id(h.payload["path"])
        if doc not in seen:
            seen.append(doc)
    return seen


def evaluate(svc: Services, dense_ok: bool, claims: list[SciFactClaim], queries: dict[int, str]) -> dict:
    configs = [("bm25 (lexical)", "sparse", False)]
    if dense_ok:
        configs += [("dense", "dense", False), ("hybrid (RRF)", "hybrid", False)]
        if svc.reranker is not None:
            configs.append(("hybrid + rerank", "hybrid", True))
    cand = svc.settings.retrieval.candidates
    results: dict[str, dict] = {}
    for name, mode, rerank in configs:
        scores: dict[str, list[float]] = {"ndcg@10": [], "recall@10": [], "recall@5": [], "mrr@10": []}
        latencies = []
        for claim in claims:
            query = queries[claim.id]
            t0 = time.perf_counter()
            dense = svc.embedder.embed_query(query) if mode != "sparse" else None
            hits = svc.store.search(dense, query, limit=cand, mode=mode)
            if rerank and svc.reranker is not None:
                hits = svc.reranker.rerank(query, hits, top_n=cand)
            ranked = _rank_docs(hits)
            latencies.append((time.perf_counter() - t0) * 1000)
            scores["ndcg@10"].append(M.ndcg_at_k(ranked, claim.gold_docs, 10))
            scores["recall@10"].append(M.recall_at_k(ranked, claim.gold_docs, 10))
            scores["recall@5"].append(M.recall_at_k(ranked, claim.gold_docs, 5))
            scores["mrr@10"].append(M.mrr_at_k(ranked, claim.gold_docs, 10))
        results[name] = {k: M.mean(v) for k, v in scores.items()} | {"ms_per_query": M.mean(latencies)}
    return results


def run(settings: Settings, limit: int | None, console: Console, cross_lingual: bool = False) -> dict:
    cache = eval_cache(settings)
    notes = materialize_scifact(cache)
    svc, dense_ok = eval_services(settings, notes, "scifact", console, allow_hash_fallback=not cross_lingual)
    try:
        claims = [c for c in load_scifact_claims(cache) if c.label != "NEI"]
        claims = claims[:limit] if limit else claims
        queries = (load_or_make_translations(settings, claims, console)
                   if cross_lingual else {c.id: c.claim for c in claims})
        results = evaluate(svc, dense_ok, claims, queries)
        embedder_name = svc.embedder.name
    finally:
        svc.close()
    suite = "retrieval-es" if cross_lingual else "retrieval"
    headers = ["config", "nDCG@10", "Recall@5", "Recall@10", "MRR@10", "ms/query"]
    rows = [[n, r["ndcg@10"], r["recall@5"], r["recall@10"], r["mrr@10"], f"{r['ms_per_query']:.0f}"]
            for n, r in results.items()]
    table = md_table(headers, rows)
    summary = {"queries": len(claims), "corpus_docs": 5183, "embedder": embedder_name,
               "cross_lingual": cross_lingual, "results": results}
    path = write_report(suite, settings, summary, table)
    console.print(f"\n[bold]{suite}[/bold] · {len(claims)} claims · SciFact dev · embedder {embedder_name}")
    console.print(table)
    console.print(f"[green]Report:[/green] {path}")
    return summary
