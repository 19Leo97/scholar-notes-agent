"""Embedding backends behind one protocol. Embeddings are computed locally by default."""

from __future__ import annotations

import math
import os
from typing import Protocol

import httpx

from scholar_agent.config import EmbeddingSpec
from scholar_agent.text import stable_hash, tokenize

# Asymmetric-prompt conventions of popular embedding models: (query prefix, document prefix)
_PREFIXES = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
    "multilingual-e5": ("query: ", "passage: "),
}


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _prefixes(model: str) -> tuple[str, str]:
    for key, value in _PREFIXES.items():
        if key in model:
            return value
    return "", ""


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class OllamaEmbedder:
    def __init__(self, model: str, batch_size: int = 32, host: str | None = None):
        self.name = f"ollama:{model}"
        self.model = model
        self.batch_size = batch_size
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self._q, self._d = _prefixes(model)
        self._client = httpx.Client(timeout=300)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self._client.post(
                f"{self.host}/api/embed", json={"model": self.model, "input": texts, "truncate": True}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama embedding failed ({exc}). Is Ollama running and the model pulled? "
                f"Try: ollama pull {self.model}"
            ) from exc
        return [_normalize(v) for v in resp.json()["embeddings"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._embed([self._d + t for t in texts[i : i + self.batch_size]]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._q + text])[0]


class FastEmbedEmbedder:
    def __init__(self, model: str, batch_size: int = 32):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the extra: pip install -e .[rerank]") from exc
        self.name = f"fastembed:{model}"
        self._model = TextEmbedding(model_name=model)
        self._q, self._d = _prefixes(model)
        self.batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.embed([self._d + t for t in texts], batch_size=self.batch_size)
        return [_normalize([float(x) for x in v]) for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        vec = next(iter(self._model.embed([self._q + text])))
        return _normalize([float(x) for x in vec])


class HashEmbedder:
    """Deterministic feature-hashing embedder: offline, instant, lexical only (tests/CI)."""

    def __init__(self, dim: int = 256):
        self.name = f"hash:{dim}"
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = tokenize(text)
        bigrams = [a + "_" + b for a, b in zip(tokens, tokens[1:], strict=False)]
        for tok in tokens + bigrams:
            h = stable_hash(tok, self.dim * 2)
            vec[h % self.dim] += 1.0 if h < self.dim else -1.0
        return _normalize(vec)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def build_embedder(spec: EmbeddingSpec) -> Embedder:
    if spec.provider == "ollama":
        return OllamaEmbedder(spec.model, spec.batch_size)
    if spec.provider == "fastembed":
        return FastEmbedEmbedder(spec.model, spec.batch_size)
    return HashEmbedder()
