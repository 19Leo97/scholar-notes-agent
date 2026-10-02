"""Provider-independent representation of a scientific paper."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scholar_agent.text import normalize


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str = ""
    doi: str | None = None
    url: str | None = None
    source: str = ""                 # provider that returned it (openalex, europepmc, ...)
    source_id: str = ""
    arxiv_id: str | None = None
    pmid: str | None = None
    citation_count: int | None = None
    sources: list[str] = field(default_factory=list)  # every provider that returned it

    @property
    def key(self) -> str:
        if self.doi:
            return "doi:" + self.doi
        return "title:" + normalize(self.title)[:120]

    @property
    def link(self) -> str | None:
        if self.doi:
            return f"https://doi.org/{self.doi}"
        if self.arxiv_id:
            return f"https://arxiv.org/abs/{self.arxiv_id}"
        return self.url

    def merge(self, other: Paper) -> None:
        """Fill gaps from a duplicate returned by another provider."""
        for name in ("year", "venue", "doi", "url", "arxiv_id", "pmid", "citation_count"):
            if getattr(self, name) in (None, "") and getattr(other, name) not in (None, ""):
                setattr(self, name, getattr(other, name))
        if len(other.abstract) > len(self.abstract):
            self.abstract = other.abstract
        if len(other.authors) > len(self.authors):
            self.authors = other.authors
        for s in other.sources or [other.source]:
            if s not in self.sources:
                self.sources.append(s)


_DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


def clean_doi(value: str | None) -> str | None:
    """Normalise 'https://doi.org/10.x/y' / 'doi:10.x/y' to lowercase '10.x/y'."""
    if not value:
        return None
    match = _DOI.search(value)
    return match.group(0).rstrip(".,;)").lower() if match else None
