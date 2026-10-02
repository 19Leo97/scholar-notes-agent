"""General web search (Tavily or DuckDuckGo) and page fetching with trafilatura."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from scholar_agent.cache.http_cache import HttpClient
from scholar_agent.config import WebSpec
from scholar_agent.text import truncate_tokens


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str

    @property
    def site(self) -> str:
        return (urlparse(self.url).hostname or "").removeprefix("www.")


class WebSearch:
    def __init__(self, http: HttpClient, spec: WebSpec):
        self.http = http
        self.spec = spec

    def _provider(self) -> str:
        if self.spec.provider != "auto":
            return self.spec.provider
        return "tavily" if os.environ.get("TAVILY_API_KEY") else "ddgs"

    def search(self, query: str, n: int | None = None) -> list[WebResult]:
        n = n or self.spec.results
        if self._provider() == "tavily":
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"query": query, "max_results": n, "search_depth": "basic"},
                headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                timeout=30,
            )
            resp.raise_for_status()
            return [
                WebResult(r.get("title", ""), r["url"], r.get("content", ""))
                for r in resp.json().get("results", [])
            ]
        from ddgs import DDGS

        rows = DDGS().text(query, max_results=n)
        return [WebResult(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in rows]

    def fetch(self, url: str, max_tokens: int | None = None) -> tuple[str, str]:
        """Return (title, main text) for a public page. Raises UnsafeURLError for private hosts."""
        import trafilatura

        html = self.http.get_public_page(url)
        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        meta = trafilatura.extract_metadata(html)
        title = (meta.title if meta and meta.title else "") or urlparse(url).hostname or url
        return title, truncate_tokens(text, max_tokens or self.spec.fetch_tokens)
