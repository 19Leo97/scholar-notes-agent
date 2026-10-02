"""Search clients for OpenAlex, Europe PMC, Semantic Scholar and arXiv (all free APIs)."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Any, Protocol

from scholar_agent.cache.http_cache import HttpClient, contact_email
from scholar_agent.tools.literature.models import Paper, clean_doi


class Provider(Protocol):
    name: str

    def search(self, query: str, limit: int, year_from: int | None = None) -> list[Paper]: ...


def _inverted_to_text(index: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as an inverted index {word: [positions]}."""
    if not index:
        return ""
    slots: dict[int, str] = {}
    for word, positions in index.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots))


class OpenAlex:
    name = "openalex"
    URL = "https://api.openalex.org/works"

    def __init__(self, http: HttpClient):
        self.http = http

    def _parse(self, work: dict) -> Paper:
        authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
        venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
        return Paper(
            title=(work.get("title") or work.get("display_name") or "").strip(),
            authors=[a for a in authors if a],
            year=work.get("publication_year"),
            venue=venue,
            abstract=_inverted_to_text(work.get("abstract_inverted_index")),
            doi=clean_doi(work.get("doi")),
            url=work.get("id"),
            source=self.name,
            source_id=work.get("id", ""),
            citation_count=work.get("cited_by_count"),
            sources=[self.name],
        )

    def _params(self, extra: dict) -> dict:
        params = {
            "select": "id,doi,title,display_name,publication_year,authorships,primary_location,"
            "abstract_inverted_index,cited_by_count",
            **extra,
        }
        if mail := contact_email():
            params["mailto"] = mail
        return params

    def search(self, query: str, limit: int, year_from: int | None = None) -> list[Paper]:
        extra: dict = {"search": query, "per-page": limit}
        if year_from:
            extra["filter"] = f"from_publication_date:{year_from}-01-01"
        data = self.http.get_json(self.URL, self._params(extra))
        return [self._parse(w) for w in data.get("results", []) if w.get("title")]

    def by_doi(self, doi: str) -> Paper | None:
        data = self.http.get_json(self.URL, self._params({"filter": f"doi:https://doi.org/{doi}"}))
        results = data.get("results", [])
        return self._parse(results[0]) if results else None


class EuropePMC:
    name = "europepmc"
    URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, http: HttpClient):
        self.http = http

    def search(self, query: str, limit: int, year_from: int | None = None) -> list[Paper]:
        q = query if not year_from else f"({query}) AND PUB_YEAR:[{year_from} TO 3000]"
        data = self.http.get_json(
            self.URL,
            {"query": q, "format": "json", "resultType": "core", "pageSize": limit, "sort": "RELEVANCE"},
        )
        papers = []
        for r in data.get("resultList", {}).get("result", []):
            if not r.get("title"):
                continue
            authors = [a.strip() for a in (r.get("authorString") or "").rstrip(".").split(",") if a.strip()]
            year = int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None
            abstract = re.sub(r"<[^>]+>", "", r.get("abstractText") or "")
            papers.append(
                Paper(
                    title=re.sub(r"<[^>]+>", "", r["title"]).strip().rstrip("."),
                    authors=authors,
                    year=year,
                    venue=r.get("journalTitle"),
                    abstract=abstract,
                    doi=clean_doi(r.get("doi")),
                    url=f"https://europepmc.org/article/{r.get('source', 'MED')}/{r.get('id', '')}",
                    source=self.name,
                    source_id=str(r.get("id", "")),
                    pmid=r.get("pmid"),
                    citation_count=r.get("citedByCount"),
                    sources=[self.name],
                )
            )
        return papers


class SemanticScholar:
    name = "semantic_scholar"
    URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    FIELDS = "title,abstract,year,authors,venue,externalIds,citationCount,url"

    def __init__(self, http: HttpClient):
        self.http = http

    def search(self, query: str, limit: int, year_from: int | None = None) -> list[Paper]:
        params: dict = {"query": query, "limit": limit, "fields": self.FIELDS}
        if year_from:
            params["year"] = f"{year_from}-"
        headers = {}
        if key := os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
            headers["x-api-key"] = key
        data = self.http.get_json(self.URL, params, headers)
        papers = []
        for r in data.get("data", []):
            ext = r.get("externalIds") or {}
            papers.append(
                Paper(
                    title=(r.get("title") or "").strip(),
                    authors=[a.get("name", "") for a in r.get("authors", [])],
                    year=r.get("year"),
                    venue=r.get("venue") or None,
                    abstract=r.get("abstract") or "",
                    doi=clean_doi(ext.get("DOI")),
                    url=r.get("url"),
                    source=self.name,
                    source_id=r.get("paperId", ""),
                    arxiv_id=ext.get("ArXiv"),
                    pmid=ext.get("PubMed"),
                    citation_count=r.get("citationCount"),
                    sources=[self.name],
                )
            )
        return [p for p in papers if p.title]


class Arxiv:
    name = "arxiv"
    URL = "https://export.arxiv.org/api/query"
    NS = {"a": "http://www.w3.org/2005/Atom"}

    def __init__(self, http: HttpClient):
        self.http = http

    def search(self, query: str, limit: int, year_from: int | None = None) -> list[Paper]:
        terms = " AND ".join(f"all:{w}" for w in re.findall(r"\w+", query)[:8])
        xml = self.http.get_text(
            self.URL, {"search_query": terms, "max_results": limit, "sortBy": "relevance"}
        )
        root = ET.fromstring(xml)
        papers = []
        for entry in root.findall("a:entry", self.NS):
            def text(tag: str, entry=entry) -> str:
                node = entry.find(f"a:{tag}", self.NS)
                return re.sub(r"\s+", " ", node.text or "").strip() if node is not None else ""

            abs_url = text("id")
            arxiv_id = re.sub(r"v\d+$", "", abs_url.rsplit("/abs/", 1)[-1])
            year = int(text("published")[:4]) if text("published")[:4].isdigit() else None
            if year_from and year and year < year_from:
                continue
            doi_node = entry.find("{http://arxiv.org/schemas/atom}doi")
            papers.append(
                Paper(
                    title=text("title"),
                    authors=[
                        (n.text or "").strip()
                        for n in entry.findall("a:author/a:name", self.NS)
                    ],
                    year=year,
                    venue="arXiv preprint",
                    abstract=text("summary"),
                    doi=clean_doi(doi_node.text) if doi_node is not None else f"10.48550/arxiv.{arxiv_id}".lower(),
                    url=abs_url,
                    source=self.name,
                    source_id=arxiv_id,
                    arxiv_id=arxiv_id,
                    sources=[self.name],
                )
            )
        return [p for p in papers if p.title]


def build_providers(names: Sequence[str], http: HttpClient) -> list[Provider]:
    registry: dict[str, Any] = {
        "openalex": OpenAlex, "europepmc": EuropePMC,
        "semantic_scholar": SemanticScholar, "arxiv": Arxiv,
    }
    return [registry[n](http) for n in names if n in registry]
