"""DOI verification against Crossref (then DataCite for preprints/datasets)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from scholar_agent.cache.http_cache import HttpClient, contact_email
from scholar_agent.text import tokenize

Status = Literal["verified", "mismatch", "not_found", "unreachable"]


@dataclass
class DoiCheck:
    status: Status
    registry: str = ""
    registered_title: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "verified"


def titles_match(a: str, b: str) -> bool:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.7


def _lookup(http: HttpClient, url: str, params: dict | None = None) -> dict | None:
    try:
        return http.get_json(url, params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def verify_doi(http: HttpClient, doi: str, expected_title: str) -> DoiCheck:
    """Confirm that the DOI resolves in a registry and that its title matches the cited paper."""
    params = {"mailto": contact_email()} if contact_email() else None
    try:
        data = _lookup(http, f"https://api.crossref.org/works/{doi}", params)
        if data:
            titles = data.get("message", {}).get("title") or []
            title = titles[0] if titles else None
            if title is None or titles_match(title, expected_title):
                return DoiCheck("verified", "Crossref", title)
            return DoiCheck("mismatch", "Crossref", title)
        data = _lookup(http, f"https://api.datacite.org/dois/{doi}")
        if data:
            titles = data.get("data", {}).get("attributes", {}).get("titles") or []
            title = titles[0].get("title") if titles else None
            if title is None or titles_match(title, expected_title):
                return DoiCheck("verified", "DataCite", title)
            return DoiCheck("mismatch", "DataCite", title)
        return DoiCheck("not_found")
    except Exception:
        return DoiCheck("unreachable")
