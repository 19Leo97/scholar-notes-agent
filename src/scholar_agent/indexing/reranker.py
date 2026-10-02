"""Optional cross-encoder reranking (fastembed/ONNX, CPU only)."""

from __future__ import annotations

from typing import Protocol

from scholar_agent.config import RerankerSpec
from scholar_agent.indexing.vectorstore import Hit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[Hit], top_n: int) -> list[Hit]: ...


class FastEmbedReranker:
    def __init__(self, model: str):
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the extra: pip install -e .[rerank]") from exc
        self._model = TextCrossEncoder(model_name=model)

    def rerank(self, query: str, hits: list[Hit], top_n: int) -> list[Hit]:
        if not hits:
            return hits
        docs = [f"{h.payload.get('title', '')}\n{h.payload.get('text', '')}" for h in hits]
        scores = list(self._model.rerank(query, docs))
        ranked = sorted(zip(hits, scores, strict=True), key=lambda p: p[1], reverse=True)
        out = []
        for hit, score in ranked[:top_n]:
            hit.meta["fused_score"] = hit.score
            hit.score = float(score)
            out.append(hit)
        return out


def build_reranker(spec: RerankerSpec) -> Reranker | None:
    if spec.provider == "fastembed":
        return FastEmbedReranker(spec.model)
    return None
