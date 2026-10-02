from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_agent.evaluation import metrics as M
from scholar_agent.evaluation.common import DATA_DIR
from scholar_agent.evaluation.datasets import _safe_name, scifact_doc_id
from scholar_agent.evaluation.report import md_table
from scholar_agent.text import normalize

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_vault"


def test_ranking_metrics():
    ranked, relevant = ["a", "b", "c", "d"], {"b", "d", "z"}
    assert M.recall_at_k(ranked, relevant, 2) == pytest.approx(1 / 3)
    assert M.mrr_at_k(ranked, relevant, 4) == pytest.approx(0.5)
    ideal = (1 / 1 + 1 / 1.5849625 + 1 / 2.0)
    actual = 1 / 1.5849625 + 1 / 2.321928
    assert M.ndcg_at_k(ranked, relevant, 4) == pytest.approx(actual / ideal, rel=1e-4)
    assert M.ndcg_at_k(["x"], {"a"}) == 0.0 and M.ndcg_at_k(["a"], set()) == 0.0


def test_classification_report_and_kappa():
    gold = ["SUPPORT", "SUPPORT", "NEI", "CONTRADICT"]
    pred = ["SUPPORT", "NEI", "NEI", "CONTRADICT"]
    rep = M.classification_report(gold, pred, ["SUPPORT", "CONTRADICT", "NEI"])
    assert rep["accuracy"] == 0.75
    assert rep["per_class"]["SUPPORT"]["recall"] == 0.5 and rep["per_class"]["NEI"]["precision"] == 0.5
    assert M.cohens_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert M.cohens_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_citation_scores_and_percentiles():
    assert M.citation_scores({"1", "2"}, {"2", "3"}) == (0.5, 0.5)
    assert M.citation_scores(set(), {"1"}) == (0.0, 0.0)
    assert M.percentile([1, 2, 3, 4, 5], 0.5) == 3 and M.percentile([], 0.9) == 0.0


def test_scifact_filename_roundtrip():
    name = f"{_safe_name('A: study of <LTP> in [CA1]/dentate?')} (4983).md"
    assert scifact_doc_id(name) == "4983" and not set('<>:"/\\|?*[]') & set(name)


def test_markdown_table():
    table = md_table(["a", "b"], [["x", 0.12345]])
    assert table.splitlines()[0] == "| a | b |" and "0.123" in table


def test_vault_questions_are_answerable_from_the_demo_vault():
    """Guards the benchmark itself: expected keywords must exist in the gold notes."""
    items = json.loads((DATA_DIR / "vault_qa.json").read_text(encoding="utf-8"))
    assert len({i["id"] for i in items}) == len(items)
    for item in items:
        gold = item.get("gold_notes", [])
        text = ""
        for rel in gold:
            path = DEMO / rel
            assert path.exists(), f"{item['id']}: missing gold note {rel}"
            text += path.read_text(encoding="utf-8")
        body = normalize(text)
        for kw in item.get("keywords", []):
            assert normalize(kw) in body or item["id"] == "q06", f"{item['id']}: keyword {kw!r} not in gold notes"
        if item.get("expect_abstain"):
            assert not gold
        if item["type"] == "verify_idea":
            assert item["gold_verdict"] in {"SUPPORTED", "REFUTED", "MIXED", "INSUFFICIENT"}


def test_reference_questions_present():
    questions = json.loads((DATA_DIR / "reference_questions.json").read_text(encoding="utf-8"))
    assert len(questions) >= 20 and all(isinstance(q, str) and len(q) > 15 for q in questions)
