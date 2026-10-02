"""Qdrant-backed hybrid (dense + sparse) store. Local on-disk by default; server via URL."""

from __future__ import annotations

import functools
import gc
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient, models

from scholar_agent.indexing import sparse
from scholar_agent.ingestion.models import Chunk

DENSE, SPARSE = "dense", "lexical"
_NS = uuid.UUID("6f1c2f6e-1d3c-4a52-9a47-0b5d8a3c9e11")


def _locked(method):
    """qdrant-client local mode is not thread-safe: serialise access per store."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


@dataclass
class Hit:
    id: str
    score: float
    payload: dict[str, Any]
    vector: list[float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def point_id(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


class QdrantStore:
    def __init__(self, path: str | None = None, url: str | None = None, collection: str = "notes"):
        self.collection = collection
        self._lock = threading.RLock()
        self._path = path if not url else None
        self.client = QdrantClient(url=url) if url else QdrantClient(path=path)

    def close(self) -> None:
        self.client.close()

    # ---- schema ---------------------------------------------------------
    def ensure_collection(self, dim: int) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    def reset(self) -> None:
        """Drop all indexed chunks.

        In local mode qdrant-client ignores a failed directory removal (a locked file on Windows), and the
        stale points would reappear when the collection is recreated with another vector size. So the
        client is closed and the storage directory is removed explicitly, with retries.
        """
        if self._path is None:
            if self.client.collection_exists(self.collection):
                self.client.delete_collection(self.collection)
            return
        with self._lock:
            self.client.close()
            gc.collect()
            for attempt in range(6):
                try:
                    shutil.rmtree(self._path)
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    if attempt == 5:
                        raise
                    time.sleep(0.25)
            self.client = QdrantClient(path=self._path)

    def count(self) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, exact=True).count

    # ---- writes ---------------------------------------------------------
    @_locked
    def upsert(self, chunks: list[Chunk], dense: list[list[float]]) -> None:
        points = []
        for chunk, vec in zip(chunks, dense, strict=True):
            idx, val = sparse.document_vector(chunk.embed_text)
            points.append(
                models.PointStruct(
                    id=point_id(chunk.key),
                    vector={DENSE: vec, SPARSE: models.SparseVector(indices=idx, values=val)},
                    payload={
                        "source": chunk.source, "path": chunk.path, "index": chunk.index,
                        "title": chunk.title, "heading": chunk.heading, "text": chunk.text,
                        "line_start": chunk.line_start, "line_end": chunk.line_end,
                        "kind": chunk.kind, "lang": chunk.lang, "tags": chunk.tags,
                        "images": chunk.images, "urls": chunk.urls, **chunk.extra,
                    },
                )
            )
        for i in range(0, len(points), 256):
            self.client.upsert(self.collection, points[i : i + 256], wait=True)

    @_locked
    def delete_note(self, source: str, path: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[
                    models.FieldCondition(key="source", match=models.MatchValue(value=source)),
                    models.FieldCondition(key="path", match=models.MatchValue(value=path)),
                ])
            ),
            wait=True,
        )

    # ---- reads ----------------------------------------------------------
    @_locked
    def search(
        self,
        dense: list[float] | None,
        query_text: str,
        limit: int = 30,
        mode: str = "hybrid",
        kinds: list[str] | None = None,
        with_vectors: bool = False,
    ) -> list[Hit]:
        """mode: dense | sparse | hybrid (RRF fusion of both)."""
        flt = None
        if kinds:
            flt = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchAny(any=kinds))])
        idx, val = sparse.query_vector(query_text)
        sparse_q = models.SparseVector(indices=idx, values=val)
        want_vec: Any = [DENSE] if with_vectors else False

        if mode == "dense":
            res = self.client.query_points(
                self.collection, query=dense, using=DENSE, limit=limit, query_filter=flt,
                with_payload=True, with_vectors=want_vec,
            )
        elif mode == "sparse":
            if not idx:
                return []
            res = self.client.query_points(
                self.collection, query=sparse_q, using=SPARSE, limit=limit, query_filter=flt,
                with_payload=True, with_vectors=want_vec,
            )
        else:
            prefetch = [models.Prefetch(query=dense, using=DENSE, limit=limit, filter=flt)]
            if idx:
                prefetch.append(models.Prefetch(query=sparse_q, using=SPARSE, limit=limit, filter=flt))
            res = self.client.query_points(
                self.collection, prefetch=prefetch, query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit, with_payload=True, with_vectors=want_vec,
            )
        hits = []
        for p in res.points:
            vec = None
            if with_vectors and p.vector:
                vec = p.vector[DENSE] if isinstance(p.vector, dict) else p.vector
            hits.append(Hit(id=str(p.id), score=float(p.score), payload=p.payload or {}, vector=vec))  # type: ignore[arg-type]
        return hits

    @_locked
    def first_chunk(self, source: str, path: str) -> Hit | None:
        """Lead chunk (index 0) of a note: usually its one-line summary."""
        points, _ = self.client.scroll(
            self.collection,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(key="source", match=models.MatchValue(value=source)),
                models.FieldCondition(key="path", match=models.MatchValue(value=path)),
                models.FieldCondition(key="index", match=models.MatchValue(value=0)),
            ]),
            limit=1, with_payload=True,
        )
        return Hit(id=str(points[0].id), score=0.0, payload=points[0].payload or {}) if points else None
