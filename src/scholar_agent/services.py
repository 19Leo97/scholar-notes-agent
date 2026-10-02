"""Dependency container: builds embedder, vector store, catalog and reranker from Settings."""

from __future__ import annotations

from dataclasses import dataclass

from scholar_agent.config import Settings
from scholar_agent.indexing.catalog import Catalog
from scholar_agent.indexing.embedder import Embedder, build_embedder
from scholar_agent.indexing.reranker import Reranker, build_reranker
from scholar_agent.indexing.vectorstore import QdrantStore


@dataclass
class Services:
    settings: Settings
    embedder: Embedder
    store: QdrantStore
    catalog: Catalog
    reranker: Reranker | None

    def close(self) -> None:
        self.store.close()
        self.catalog.close()


def build_services(settings: Settings, with_reranker: bool = True) -> Services:
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    return Services(
        settings=settings,
        embedder=build_embedder(settings.embeddings),
        store=QdrantStore(path=str(settings.index_dir / "qdrant")),
        catalog=Catalog(settings.sqlite_path),
        reranker=build_reranker(settings.reranker) if with_reranker else None,
    )
