"""Polite HTTP client: SQLite response cache, per-host rate limiting, retries, SSRF guard."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

USER_AGENT = "scholar-notes-agent/0.1 (open-source research tool)"

# Minimum seconds between requests per host (public APIs are shared resources)
_MIN_INTERVAL = {
    "api.openalex.org": 0.12,
    "api.crossref.org": 0.1,
    "export.arxiv.org": 3.0,       # arXiv asks for one request every 3 seconds
    "api.semanticscholar.org": 1.1,
    "www.ebi.ac.uk": 0.15,
}


class TransientHTTPError(Exception):
    """Retryable failure (429 / 5xx / network)."""


class UnsafeURLError(ValueError):
    """The URL points somewhere an agent must never fetch (localhost, private network, file://)."""


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError(f"Only http(s) URLs are allowed: {url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Cannot resolve host: {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError(f"Refusing to fetch a non-public address: {parsed.hostname}")


class HttpClient:
    def __init__(self, cache_path: Path | None = None, ttl_days: float = 7.0, timeout: float = 25.0):
        self._client = httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self._ttl = ttl_days * 86400
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(cache_path, check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS http_cache (key TEXT PRIMARY KEY, ts REAL, body TEXT)"
            )

    # ---- cache ----------------------------------------------------------
    @staticmethod
    def _key(url: str, params: dict | None) -> str:
        raw = url + "?" + json.dumps(params or {}, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> str | None:
        if not self._db:
            return None
        with self._lock:
            row = self._db.execute("SELECT ts, body FROM http_cache WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] < self._ttl:
            return row[1]
        return None

    def _cache_put(self, key: str, body: str) -> None:
        if self._db:
            with self._lock:
                self._db.execute(
                    "INSERT OR REPLACE INTO http_cache(key, ts, body) VALUES (?,?,?)",
                    (key, time.time(), body),
                )
                self._db.commit()

    # ---- requests -------------------------------------------------------
    def _throttle(self, host: str) -> None:
        interval = _MIN_INTERVAL.get(host, 0.0)
        if not interval:
            return
        with self._lock:
            wait = self._last.get(host, 0.0) + interval - time.monotonic()
            self._last[host] = time.monotonic() + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    @retry(
        retry=retry_if_exception_type(TransientHTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch(self, url: str, params: dict | None, headers: dict | None) -> str:
        self._throttle(urlparse(url).hostname or "")
        try:
            resp = self._client.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            raise TransientHTTPError(str(exc)) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientHTTPError(f"HTTP {resp.status_code} from {url}")
        resp.raise_for_status()
        return resp.text

    def get_text(
        self, url: str, params: dict | None = None, headers: dict | None = None, use_cache: bool = True
    ) -> str:
        key = self._key(url, params)
        if use_cache and (hit := self._cache_get(key)) is not None:
            return hit
        body = self._fetch(url, params, headers)
        if use_cache:
            self._cache_put(key, body)
        return body

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        return json.loads(self.get_text(url, params, headers))

    def get_public_page(self, url: str, max_bytes: int = 2_000_000, max_redirects: int = 5) -> str:
        """Fetch an arbitrary page chosen by the model (never cached).

        Every hop is checked by the SSRF guard, redirects included: a public page must not be able to
        bounce the agent to localhost or the private network.
        """
        for _ in range(max_redirects + 1):
            assert_public_url(url)
            with self._client.stream("GET", url, follow_redirects=False) as resp:
                location = resp.headers.get("location")
                if resp.is_redirect and location:
                    url = str(httpx.URL(url).join(location))
                    continue
                resp.raise_for_status()
                chunks, size = [], 0
                for part in resp.iter_bytes():
                    chunks.append(part)
                    size += len(part)
                    if size > max_bytes:
                        break
                return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        raise UnsafeURLError(f"Too many redirects: {url}")


def contact_email() -> str | None:
    return os.environ.get("CONTACT_EMAIL") or None
