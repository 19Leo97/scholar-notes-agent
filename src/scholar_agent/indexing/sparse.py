"""Self-contained lexical (BM25-style) sparse vectors.

Hashing tokens into a fixed space keeps the index language-agnostic (ES/EN notes) and
dependency-free. IDF is applied by Qdrant at query time (`Modifier.IDF`).
"""

from __future__ import annotations

from collections import Counter

from scholar_agent.text import stable_hash, tokenize

BUCKETS = 1 << 20
_K1, _B, _AVG_LEN = 1.2, 0.75, 120.0


def _stems(text: str) -> list[str]:
    # Light normalisation: crude plural stripping helps ES/EN morphology without a stemmer
    out = []
    for t in tokenize(text):
        if len(t) > 4 and t.endswith("es"):
            t = t[:-2]
        elif len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        out.append(t)
    return out


def document_vector(text: str) -> tuple[list[int], list[float]]:
    terms = _stems(text)
    length = len(terms) or 1
    weights: dict[int, float] = {}
    for term, tf in Counter(terms).items():
        idx = stable_hash(term, BUCKETS)
        weights[idx] = weights.get(idx, 0.0) + tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * length / _AVG_LEN))
    return list(weights), list(weights.values())


def query_vector(text: str) -> tuple[list[int], list[float]]:
    idxs = sorted({stable_hash(t, BUCKETS) for t in _stems(text)})
    return idxs, [1.0] * len(idxs)
