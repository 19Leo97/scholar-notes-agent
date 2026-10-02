"""Evaluation metrics. Pure functions, unit-tested; no model calls."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence


def dcg(relevances: Sequence[float]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int = 10) -> float:
    gains = [1.0 if d in relevant else 0.0 for d in ranked[:k]]
    ideal = dcg([1.0] * min(len(relevant), k))
    return dcg(gains) / ideal if ideal else 0.0


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int = 10) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr_at_k(ranked: Sequence[str], relevant: set[str], k: int = 10) -> float:
    for i, d in enumerate(ranked[:k], 1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def confusion(gold: Sequence[str], pred: Sequence[str]) -> Counter:
    return Counter(zip(gold, pred, strict=True))


def classification_report(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict:
    """Accuracy, per-class precision/recall/F1 and macro-F1."""
    conf = confusion(gold, pred)
    per_class = {}
    for label in labels:
        tp = conf[(label, label)]
        fp = sum(conf[(g, label)] for g in labels if g != label)
        fn = sum(conf[(label, p)] for p in labels if p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    correct = sum(1 for g, p in zip(gold, pred, strict=True) if g == p)
    return {
        "accuracy": correct / len(gold) if gold else 0.0,
        "macro_f1": sum(c["f1"] for c in per_class.values()) / len(labels) if labels else 0.0,
        "per_class": per_class,
        "n": len(gold),
    }


def citation_scores(cited: set[str], gold: set[str]) -> tuple[float, float]:
    """(precision, recall) of cited source IDs against gold source IDs (ALCE-style)."""
    if not cited:
        return 0.0, 0.0
    hits = len(cited & gold)
    return hits / len(cited), (hits / len(gold) if gold else 0.0)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Inter-rater agreement, used to check the LLM judge against human labels."""
    n = len(a)
    if n == 0:
        return 0.0
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
