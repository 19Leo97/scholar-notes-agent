"""Evaluation suites that run the complete agent (E2 verification, E3 PubMedQA, E4 vault, E5 references).

These suites call real LLMs and therefore cost money: every suite has a small default `--limit`, uses the
LLM response cache, and reports tokens and USD next to quality so cost-quality trade-offs are visible.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console

from scholar_agent.agent.runner import AgentResult, ResearchAgent
from scholar_agent.budget.tracking import QueryTracker
from scholar_agent.config import PACKAGE_ROOT, Settings
from scholar_agent.evaluation import metrics as M
from scholar_agent.evaluation.common import DATA_DIR, eval_cache, eval_services
from scholar_agent.evaluation.datasets import (
    PubMedQAItem,
    load_pubmedqa,
    load_scifact_claims,
    materialize_pubmedqa,
    materialize_scifact,
    scifact_doc_id,
)
from scholar_agent.evaluation.judge import extract_decision, score_answer
from scholar_agent.evaluation.report import md_table, write_report
from scholar_agent.llm.factory import ModelHub
from scholar_agent.text import normalize

VERDICT_TO_LABEL = {"SUPPORTED": "SUPPORT", "REFUTED": "CONTRADICT", "INSUFFICIENT": "NEI", "MIXED": "NEI"}


# ----------------------------------------------------------------------------- shared
def _run_items(items: list, fn: Callable[[Any], dict], console: Console, desc: str) -> list[dict]:
    records = []
    for i, item in enumerate(items, 1):
        t0 = time.perf_counter()
        try:
            rec = fn(item)
            rec["error"] = None
        except Exception as exc:  # one failing item (rate limit, parse error) must not abort the suite
            rec = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        rec["seconds"] = time.perf_counter() - t0
        records.append(rec)
        console.print(f"[dim]{desc} {i}/{len(items)}  {rec['seconds']:.1f}s"
                      f"{'  ERROR ' + rec['error'] if rec['error'] else ''}[/dim]")
    return records


def _cost_summary(records: list[dict]) -> dict:
    ok = [r for r in records if not r.get("error")]
    return {
        "items": len(records), "errors": len(records) - len(ok),
        "usd_total": sum(r.get("usd", 0.0) for r in ok),
        "usd_per_item": M.mean([r.get("usd", 0.0) for r in ok]),
        "tokens_in_per_item": M.mean([r.get("tokens_in", 0) for r in ok]),
        "tokens_out_per_item": M.mean([r.get("tokens_out", 0) for r in ok]),
        "tool_calls_per_item": M.mean([r.get("tool_calls", 0) for r in ok]),
        "latency_p50_s": M.percentile([r["seconds"] for r in ok], 0.5),
        "latency_p95_s": M.percentile([r["seconds"] for r in ok], 0.95),
    }


def _cost_rows(cost: dict) -> list[list]:
    return [["items evaluated / errors", f"{cost['items']} / {cost['errors']}"],
            ["USD per item (total)", f"${cost['usd_per_item']:.4f} (${cost['usd_total']:.3f})"],
            ["tokens in / out per item", f"{cost['tokens_in_per_item']:.0f} / {cost['tokens_out_per_item']:.0f}"],
            ["tool calls per item", f"{cost['tool_calls_per_item']:.1f}"],
            ["latency p50 / p95", f"{cost['latency_p50_s']:.1f}s / {cost['latency_p95_s']:.1f}s"]]


def _base_record(result: AgentResult) -> dict:
    return {"usd": result.usage.cost_usd, "tokens_in": result.usage.input_tokens,
            "tokens_out": result.usage.output_tokens, "tool_calls": result.usage.tool_calls,
            "llm_calls": result.usage.llm_calls, "external_calls": result.external_calls,
            "claims_total": result.report.claims_total, "claims_supported_raw": result.report.claims_supported,
            "removed_claims": result.removed_claims}


def _cited_note_paths(result: AgentResult) -> set[str]:
    return {e.meta["path"] for e in result.evidence if e.kind == "note" and e.id in result.cited_ids}


def _answer_body(result: AgentResult) -> str:
    return re.split(r"\n## (?:Referencias|References)", result.markdown)[0]


def _finish(suite: str, settings: Settings, console: Console, headers: list[str], rows: list[list],
            cost: dict, summary: dict, records: list[dict]) -> dict:
    table = md_table(headers, rows) + "\n\n" + md_table(["cost / latency", "value"], _cost_rows(cost))
    summary["cost"] = cost
    path = write_report(suite, settings, summary, table, records)
    console.print(f"\n[bold]{suite}[/bold]")
    console.print(table)
    console.print(f"[green]Report:[/green] {path}")
    return summary


def _sample_stratified(claims: list, per_class: int, seed: int = 7) -> list:
    rng = random.Random(seed)
    by_label: dict[str, list] = {}
    for c in claims:
        by_label.setdefault(c.label, []).append(c)
    picked = []
    for label in sorted(by_label):
        group = by_label[label][:]
        rng.shuffle(group)
        picked += group[:per_class]
    rng.shuffle(picked)
    return picked


# ------------------------------------------------------------------ E2 idea verification
def run_verification(settings: Settings, limit: int | None, console: Console, judge: bool = False,
                     offline: bool = False) -> dict:
    cache = eval_cache(settings)
    svc, _ = eval_services(settings, materialize_scifact(cache), "scifact", console)
    try:
        claims = _sample_stratified(load_scifact_claims(cache), max(1, (limit or 45) // 3))
        agent = ResearchAgent(settings, svc)

        def one(claim) -> dict:
            result = agent.ask(f"Idea to verify: {claim.claim}", mode="notes", intent="verify_idea")
            verdict = result.synthesis.verdict
            cited = {scifact_doc_id(p) for p in _cited_note_paths(result)}
            prec, rec = M.citation_scores(cited, claim.gold_docs)
            return {"id": claim.id, "gold": claim.label, "pred": VERDICT_TO_LABEL.get(verdict or "INSUFFICIENT"),
                    "verdict": verdict, "cited": sorted(cited), "gold_docs": sorted(claim.gold_docs),
                    "cite_precision": prec, "cite_recall": rec, **_base_record(result)}

        records = _run_items(claims, one, console, "verify")
    finally:
        svc.close()
    ok = [r for r in records if not r["error"]]
    rep = M.classification_report([r["gold"] for r in ok], [r["pred"] for r in ok], ["SUPPORT", "CONTRADICT", "NEI"])
    with_evidence = [r for r in ok if r["gold"] != "NEI"]
    rows: list[list] = [["accuracy", rep["accuracy"]], ["macro-F1", rep["macro_f1"]]]
    rows += [[f"F1 {lab}", c["f1"]] for lab, c in rep["per_class"].items()]
    rows += [["citation precision (gold-evidence claims)", M.mean([r["cite_precision"] for r in with_evidence])],
             ["citation recall (gold-evidence claims)", M.mean([r["cite_recall"] for r in with_evidence])],
             ["raw claim support rate (before pruning)",
              M.mean([r["claims_supported_raw"] / r["claims_total"] for r in ok if r["claims_total"]])]]
    return _finish("verification", settings, console, ["metric (SciFact dev, notes mode)", "value"], rows,
                   _cost_summary(records), {"classification": rep, "n": len(ok)}, records)


# ------------------------------------------------------------------------ E3 PubMedQA
def run_pubmedqa(settings: Settings, limit: int | None, console: Console, judge: bool = False,
                 offline: bool = False) -> dict:
    cache = eval_cache(settings)
    n = limit or 40
    items = load_pubmedqa(cache)
    rng = random.Random(7)
    rng.shuffle(items)
    questions, distractors = items[:n], items[n : n + max(3 * n, 100)]
    notes = materialize_pubmedqa(questions + distractors, cache, f"pubmedqa_notes_{n}")
    svc, _ = eval_services(settings, notes, f"pubmedqa{n}", console)
    judge_tracker = QueryTracker(settings)
    hub = ModelHub(settings, judge_tracker)
    try:
        agent = ResearchAgent(settings, svc)

        def one(item: PubMedQAItem) -> dict:
            result = agent.ask(item.question, mode="notes", intent="question")
            gold_path = f"PMID {item.pmid}.md"
            cited = _cited_note_paths(result)
            decision = extract_decision(hub, item.question, result.markdown) if result.cited_ids else "maybe"
            rec = {"pmid": item.pmid, "gold": item.decision, "pred": decision,
                   "gold_cited": gold_path in cited,
                   "cite_precision": (1.0 if gold_path in cited and len(cited) == 1 else
                                      (1 / len(cited) if gold_path in cited else 0.0)) if cited else 0.0,
                   **_base_record(result)}
            if judge and result.cited_ids:
                ev = "\n\n".join(e.text for e in result.evidence if e.id in result.cited_ids)
                score = score_answer(hub, item.question, _answer_body(result), ev)
                rec |= {"faithfulness": score.faithfulness, "relevance": score.relevance}
            return rec

        records = _run_items(questions, one, console, "pubmedqa")
    finally:
        svc.close()
    ok = [r for r in records if not r["error"]]
    rep = M.classification_report([r["gold"] for r in ok], [r["pred"] for r in ok], ["yes", "no", "maybe"])
    majority = Counter(r["gold"] for r in ok).most_common(1)[0][1] / len(ok) if ok else 0.0
    rows = [["accuracy (yes/no/maybe)", rep["accuracy"]], ["majority-class baseline", majority],
            ["macro-F1", rep["macro_f1"]],
            ["gold abstract cited (recall)", M.mean([1.0 if r["gold_cited"] else 0.0 for r in ok])],
            ["citation precision", M.mean([r["cite_precision"] for r in ok])],
            ["raw claim support rate (before pruning)",
             M.mean([r["claims_supported_raw"] / r["claims_total"] for r in ok if r["claims_total"]])]]
    if judge:
        scored = [r for r in ok if "faithfulness" in r]
        rows += [["judge faithfulness (1-5)", M.mean([r["faithfulness"] for r in scored])],
                 ["judge relevance (1-5)", M.mean([r["relevance"] for r in scored])]]
    cost = _cost_summary(records)
    cost["judge_usd"] = judge_tracker.cost
    return _finish("pubmedqa", settings, console, ["metric (PubMedQA, notes mode)", "value"], rows, cost,
                   {"classification": rep, "n": len(ok), "judge_usd": judge_tracker.cost}, records)


# ----------------------------------------------------------------------- E4 demo vault
def _demo_vault() -> Path:
    for base in (Path.cwd(), PACKAGE_ROOT):
        if (base / "examples" / "demo_vault").is_dir():
            return base / "examples" / "demo_vault"
    raise FileNotFoundError("examples/demo_vault not found; run from the repository root")


def run_vault(settings: Settings, limit: int | None, console: Console, judge: bool = False,
              offline: bool = False) -> dict:
    items = json.loads((DATA_DIR / "vault_qa.json").read_text(encoding="utf-8"))
    if offline:
        items = [i for i in items if not i.get("network")]
    items = items[:limit] if limit else items
    svc, _ = eval_services(settings, _demo_vault(), "demo_vault", console)
    judge_tracker = QueryTracker(settings)
    hub = ModelHub(settings, judge_tracker)
    try:
        agent = ResearchAgent(settings, svc)

        def one(item: dict) -> dict:
            result = agent.ask(item["question"], mode=item["mode"],
                               intent="verify_idea" if item["type"] == "verify_idea" else None)
            body = normalize(_answer_body(result))
            full = normalize(result.markdown)
            cited = _cited_note_paths(result)
            gold = set(item.get("gold_notes", []))
            rec: dict = {"id": item["id"], "type": item["type"], "mode": item["mode"],
                         "cited": sorted(cited), **_base_record(result)}
            rec["gold_recall"] = M.citation_scores(cited, gold)[1] if gold else None
            rec["keyword_hit"] = (M.mean([1.0 if normalize(k) in body else 0.0 for k in item["keywords"]])
                                  if item.get("keywords") else None)
            rec["expect_in_answer"] = (all(normalize(s) in full for s in item["expect_in_answer"])
                                       if item.get("expect_in_answer") else None)
            rec["verdict_correct"] = ((result.synthesis.verdict == item["gold_verdict"])
                                      if item.get("gold_verdict") else None)
            rec["abstained"] = (not result.cited_ids or result.synthesis.verdict == "INSUFFICIENT") \
                if item.get("expect_abstain") else None
            rec["mode_compliant"] = (result.external_calls == 0) if item["mode"] == "notes" else True
            kinds = {e.kind for e in result.evidence if e.id in result.cited_ids}
            rec["kinds_ok"] = set(item["expect_kinds"]) <= kinds if item.get("expect_kinds") else None
            ideas = result.synthesis.ai_ideas
            rec["ia_labeled"] = all(f"[IA-{n}]" in result.markdown for n in range(1, len(ideas) + 1))
            if judge and result.cited_ids:
                ev = "\n\n".join(e.text for e in result.evidence if e.id in result.cited_ids)
                rec["faithfulness"] = score_answer(hub, item["question"], _answer_body(result), ev).faithfulness
            return rec

        records = _run_items(items, one, console, "vault")
    finally:
        svc.close()
    ok = [r for r in records if not r["error"]]

    def avg(key: str, only_type: str | None = None) -> float | str:
        vals = [r[key] for r in ok if r.get(key) is not None and (only_type is None or r["type"] == only_type)]
        return M.mean([float(v) for v in vals]) if vals else "n/a"

    rows: list[list] = [["gold-note citation recall", avg("gold_recall")], ["keyword coverage", avg("keyword_hit")],
            ["verdict accuracy (verify_idea)", avg("verdict_correct")],
            ["correct abstention (out-of-vault questions)", avg("abstained")],
            ["answer shows required reference (DOI / own-hypothesis tag)", avg("expect_in_answer")],
            ["mode compliance (notes mode = 0 external calls)", avg("mode_compliant")],
            ["AI ideas labelled [IA-n]", avg("ia_labeled")],
            ["raw claim support rate (before pruning)",
             M.mean([r["claims_supported_raw"] / r["claims_total"] for r in ok if r["claims_total"]])],
            ["claims removed by the verifier (per answer)", M.mean([r["removed_claims"] for r in ok])]]
    if judge:
        rows.append(["judge faithfulness (1-5)", avg("faithfulness")])
    cost = _cost_summary(records)
    return _finish("vault", settings, console, ["metric (demo vault, end-to-end)", "value"], rows, cost,
                   {"n": len(ok), "judge_usd": judge_tracker.cost}, records)


# ------------------------------------------------------------------ E5 reference validity
def run_references(settings: Settings, limit: int | None, console: Console, judge: bool = False,
                   offline: bool = False) -> dict:
    questions = json.loads((DATA_DIR / "reference_questions.json").read_text(encoding="utf-8"))
    questions = questions[:limit] if limit else questions[:10]
    settings = settings.model_copy(deep=True)
    settings.literature.verify_dois = True
    agent = ResearchAgent(settings, None)

    def one(question: str) -> dict:
        result = agent.ask(question, mode="literature")
        papers = [e for e in result.evidence if e.kind == "paper" and e.id in result.cited_ids]
        statuses = Counter((e.doi_check.status if e.doi_check else ("no_doi" if not e.meta.get("doi") else "unchecked"))
                           for e in papers)
        titles = [normalize(e.title) for e in papers]
        return {"question": question, "papers_cited": len(papers), "statuses": dict(statuses),
                "duplicates": len(titles) - len(set(titles)), "with_abstract": sum(bool(e.meta.get("has_abstract")) for e in papers),
                **_base_record(result)}

    records = _run_items(questions, one, console, "references")
    ok = [r for r in records if not r["error"]]
    total = sum(r["papers_cited"] for r in ok)
    status: Counter[str] = Counter()
    for r in ok:
        status.update(r["statuses"])
    rate = lambda key: (status[key] / total) if total else 0.0  # noqa: E731
    rows = [["papers cited (total)", total], ["DOI verified (Crossref/DataCite)", rate("verified")],
            ["DOI title mismatch", rate("mismatch")], ["DOI not found", rate("not_found")],
            ["registry unreachable", rate("unreachable")], ["no DOI (e.g. some preprints)", rate("no_doi")],
            ["duplicate references", sum(r["duplicates"] for r in ok)],
            ["cited papers with abstract available", (sum(r["with_abstract"] for r in ok) / total) if total else 0.0],
            ["raw claim support rate (before pruning)",
             M.mean([r["claims_supported_raw"] / r["claims_total"] for r in ok if r["claims_total"]])]]
    return _finish("references", settings, console, ["metric (literature mode, live APIs)", "value"], rows,
                   _cost_summary(records), {"n": len(ok), "statuses": dict(status)}, records)
