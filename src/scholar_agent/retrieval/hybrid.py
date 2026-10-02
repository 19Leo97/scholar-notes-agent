"""Notes retrieval: hybrid search -> optional rerank -> MMR diversity -> wikilink expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from scholar_agent.indexing.vectorstore import Hit
from scholar_agent.services import Services


@dataclass
class NoteHit:
    source: str
    path: str
    title: str
    heading: str
    text: str
    line_start: int
    line_end: int
    kind: str
    lang: str
    score: float
    via: str = "search"                # search | graph
    relation: str | None = None        # e.g. "Parte de" when found through the link graph
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end}"


def _to_hit(h: Hit, via: str = "search", relation: str | None = None) -> NoteHit:
    p = h.payload
    return NoteHit(
        source=p["source"], path=p["path"], title=p["title"], heading=p.get("heading", ""),
        text=p["text"], line_start=p["line_start"], line_end=p["line_end"], kind=p.get("kind", "note"),
        lang=p.get("lang", "und"), score=h.score, via=via, relation=relation,
        tags=p.get("tags", []), images=p.get("images", []), urls=p.get("urls", []),
        extra={k: p[k] for k in ("doi", "año", "fuentes") if k in p},
    )


def mmr_select(hits: list[Hit], k: int, lam: float) -> list[Hit]:
    """Maximal Marginal Relevance on dense vectors; relevance comes from the incoming rank."""
    if len(hits) <= k or any(h.vector is None for h in hits):
        return hits[:k]
    vectors = np.array([h.vector for h in hits], dtype=float)
    relevance = np.linspace(1.0, 0.0, num=len(hits), endpoint=False)
    selected = [0]
    remaining = list(range(1, len(hits)))
    while remaining and len(selected) < k:
        sims = vectors[remaining] @ vectors[selected].T
        scores = lam * relevance[remaining] - (1 - lam) * sims.max(axis=1)
        best = remaining[int(np.argmax(scores))]
        selected.append(best)
        remaining.remove(best)
    return [hits[i] for i in selected]


class NoteRetriever:
    def __init__(self, services: Services):
        self.svc = services
        self.cfg = services.settings.retrieval

    def search(
        self,
        query: str,
        k: int | None = None,
        mode: str = "hybrid",
        rerank: bool = True,
        graph: bool | None = None,
        kinds: list[str] | None = None,
    ) -> list[NoteHit]:
        k = k or self.cfg.top_k
        dense = self.svc.embedder.embed_query(query) if mode != "sparse" else None
        use_rerank = rerank and self.svc.reranker is not None
        hits = self.svc.store.search(
            dense, query, limit=self.cfg.candidates, mode=mode, kinds=kinds,
            with_vectors=not use_rerank and mode != "sparse",
        )
        if use_rerank:
            hits = self.svc.reranker.rerank(query, hits, top_n=self.cfg.candidates)  # type: ignore[union-attr]
        selected = mmr_select(hits, k, self.cfg.mmr_lambda)
        results = [_to_hit(h) for h in selected]
        if (self.cfg.graph_expand if graph is None else graph) and results:
            results.extend(self._expand(results))
        return results

    def _expand(self, results: list[NoteHit]) -> list[NoteHit]:
        """Add the lead chunk of notes directly linked to the best hits (1 hop)."""
        seen = {(r.source, r.path) for r in results}
        floor = min(r.score for r in results) * 0.5
        extra: list[NoteHit] = []
        for top in results[:3]:
            added = 0
            for nb in self.svc.catalog.neighbours(top.source, top.path, limit=8):
                if added >= self.cfg.graph_neighbours:
                    break
                key = (nb["source"], nb["path"])
                if key in seen:
                    continue
                lead = self.svc.store.first_chunk(nb["source"], nb["path"])
                if lead is None:
                    continue
                seen.add(key)
                relation = nb["label"] or ("enlaza a esta nota" if nb["direction"] == "in" else "enlazada")
                extra.append(_to_hit(lead, via="graph", relation=f"{relation} ({top.title})"))
                extra[-1].score = floor
                added += 1
        return extra
