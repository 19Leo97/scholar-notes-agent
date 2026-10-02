from __future__ import annotations

import pytest

from scholar_agent.cache.http_cache import HttpClient, UnsafeURLError, assert_public_url
from scholar_agent.citations.doi import titles_match
from scholar_agent.config import PrivacyError, load_settings
from scholar_agent.tools.literature.models import Paper, clean_doi
from scholar_agent.tools.literature.providers import _inverted_to_text
from scholar_agent.tools.literature.search import LiteratureSearch


def test_gemini_free_tier_is_refused():
    settings = load_settings(overrides={"privacy": {"gemini_paid_tier": False}})
    with pytest.raises(PrivacyError, match="paid"):
        settings.validate_privacy()
    load_settings(overrides={"privacy": {"gemini_paid_tier": True}}).validate_privacy()
    no_gemini = load_settings(overrides={"llm": {"synthesizer": {"provider": "groq", "model": "x"}}})
    no_gemini.validate_privacy()


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/x", "http://localhost/a", "file:///etc/passwd",
                                 "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data"])
def test_ssrf_guard_blocks_private_targets(url):
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)


def test_doi_cleaning_and_title_matching():
    assert clean_doi("https://doi.org/10.1038/NRN3192.") == "10.1038/nrn3192"
    assert clean_doi("doi:10.1/abc") is None  # too short a registrant: not a DOI
    assert titles_match("Long-term potentiation in the hippocampus", "Long term potentiation in hippocampus")
    assert not titles_match("Long-term potentiation", "Deep learning for protein folding")


def test_openalex_inverted_abstract():
    assert _inverted_to_text({"Long": [0], "term": [1], "potentiation": [2]}) == "Long term potentiation"
    assert _inverted_to_text(None) == ""


class _Stub:
    def __init__(self, name, papers):
        self.name, self._papers = name, papers

    def search(self, query, limit, year_from=None):
        if self.name == "broken":
            raise RuntimeError("503")
        return self._papers


def test_literature_search_dedupes_merges_and_survives_provider_failure(settings):
    a = Paper(title="LTP and CaMKII", doi="10.1/a", abstract="", source="openalex", sources=["openalex"], year=2012)
    a2 = Paper(title="LTP and CaMKII", doi="10.1/a", abstract="Full abstract here.", source="arxiv",
               sources=["arxiv"], venue="Nature")
    b = Paper(title="Other work", source="openalex", sources=["openalex"])
    ls = LiteratureSearch(HttpClient(), settings.literature)
    ls.providers = [_Stub("openalex", [a, b]), _Stub("arxiv", [a2]), _Stub("broken", [])]
    results = ls.search("ltp", limit=5)
    assert [p.title for p in results] == ["LTP and CaMKII", "Other work"]
    merged = results[0]
    assert merged.abstract == "Full abstract here." and merged.venue == "Nature"
    assert set(merged.sources) == {"openalex", "arxiv"} and any("broken" in e for e in ls.errors)


def test_http_cache_roundtrip(tmp_path):
    client = HttpClient(tmp_path / "c.sqlite")
    key = client._key("http://x", {"a": 1})
    client._cache_put(key, '{"ok": true}')
    assert client.get_json("http://x", {"a": 1}) == {"ok": True}  # served from cache, no network


def test_ssrf_guard_checks_every_redirect_hop():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8080/secret"})
        return httpx.Response(200, text="private data")

    client = HttpClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(UnsafeURLError):
        client.get_public_page("http://93.184.216.34/start")
