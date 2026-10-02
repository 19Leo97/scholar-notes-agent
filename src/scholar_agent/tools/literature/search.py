"""Multi-provider literature search: parallel queries, dedup by DOI/title, rank fusion."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from scholar_agent.cache.http_cache import HttpClient
from scholar_agent.config import LiteratureSpec
from scholar_agent.tools.literature.models import Paper, clean_doi
from scholar_agent.tools.literature.providers import OpenAlex, Provider, build_providers

log = logging.getLogger(__name__)
_RRF_K = 60


class LiteratureSearch:
    def __init__(self, http: HttpClient, spec: LiteratureSpec):
        self.http = http
        self.spec = spec
        self.providers: list[Provider] = build_providers(spec.providers, http)
        self.errors: list[str] = []

    def _safe(self, provider: Provider, query: str, limit: int, year_from: int | None) -> list[Paper]:
        try:
            return provider.search(query, limit, year_from)
        except Exception as exc:  # a failing provider must not fail the whole search
            msg = f"{provider.name}: {type(exc).__name__}: {exc}"
            log.warning("literature provider failed: %s", msg)
            self.errors.append(msg)
            return []

    def search(self, query: str, limit: int = 6, year_from: int | None = None) -> list[Paper]:
        if not self.providers:
            return []
        per = self.spec.per_provider
        with ThreadPoolExecutor(max_workers=len(self.providers)) as pool:
            batches = list(pool.map(lambda p: self._safe(p, query, per, year_from), self.providers))

        merged: dict[str, Paper] = {}
        scores: dict[str, float] = {}
        for papers in batches:
            for rank, paper in enumerate(papers):
                key = paper.key
                if key in merged:
                    merged[key].merge(paper)
                else:
                    merged[key] = paper
                scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
        for key, paper in merged.items():
            if paper.abstract:  # abstracts make claims verifiable against the source text
                scores[key] += 0.004
            if paper.citation_count:
                scores[key] += min(paper.citation_count, 2000) / 2000 * 0.002
        ranked = sorted(merged, key=lambda k: scores[k], reverse=True)
        return [merged[k] for k in ranked[:limit]]

    def by_doi(self, doi: str) -> Paper | None:
        doi = clean_doi(doi) or doi
        for provider in self.providers:
            if isinstance(provider, OpenAlex):
                try:
                    return provider.by_doi(doi)
                except Exception as exc:
                    self.errors.append(f"openalex by_doi: {exc}")
        return OpenAlex(self.http).by_doi(doi)
