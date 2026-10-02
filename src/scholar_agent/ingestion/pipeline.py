"""Incremental ingestion: scan -> parse -> chunk -> embed -> index. Unchanged notes are skipped."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from scholar_agent.indexing.catalog import Catalog
from scholar_agent.indexing.embedder import Embedder
from scholar_agent.indexing.vectorstore import QdrantStore
from scholar_agent.ingestion import loaders  # noqa: F401  (registers loaders)
from scholar_agent.ingestion.chunker import chunk_document
from scholar_agent.ingestion.loaders.base import get_loader
from scholar_agent.ingestion.models import Chunk

SKIP_DIRS = {".obsidian", ".git", ".trash", ".claude", "node_modules", "__pycache__", ".venv"}
EMBED_BATCH_CHUNKS = 64


@dataclass
class IngestReport:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0


def iter_note_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or get_loader(path) is None:
            continue
        rel_parts = path.relative_to(root).parts[:-1]
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        yield path


def ingest(
    root: Path,
    source: str,
    embedder: Embedder,
    store: QdrantStore,
    catalog: Catalog,
    max_tokens: int = 450,
    min_tokens: int = 40,
    rebuild: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> IngestReport:
    start = time.time()
    root = root.resolve()
    report = IngestReport()

    stored = catalog.get_meta("embedder")
    if rebuild:
        store.reset()
        catalog.reset()
        stored = None
    elif stored and stored != embedder.name:
        raise RuntimeError(
            f"The index was built with {stored!r} but the config uses {embedder.name!r}. "
            "Re-run with --rebuild to re-embed everything."
        )
    catalog.set_meta("root:" + source, str(root))
    if stored is None:
        catalog.set_meta("embedder", embedder.name)
    store.ensure_collection(len(embedder.embed_query("dimension probe")))

    known = catalog.hashes(source)
    files = list(iter_note_files(root))
    seen: set[str] = set()
    pending: list[Chunk] = []

    def flush() -> None:
        if not pending:
            return
        vectors = embedder.embed_documents([c.embed_text for c in pending])
        store.upsert(pending, vectors)
        report.chunks += len(pending)
        pending.clear()

    for i, file in enumerate(files, 1):
        report.scanned += 1
        if progress:
            progress(i, len(files), file.name)
        try:
            doc = get_loader(file).load(source, root, file)  # type: ignore[union-attr]
        except Exception as exc:  # one broken file must not stop a 3000-note run
            report.errors.append(f"{file.name}: {exc}")
            continue
        seen.add(doc.path)
        if known.get(doc.path) == doc.content_hash:
            report.unchanged += 1
            continue
        if doc.path in known:
            store.delete_note(source, doc.path)
            report.updated += 1
        else:
            report.added += 1
        chunks = chunk_document(doc, max_tokens, min_tokens)
        catalog.upsert_note(doc, len(chunks))
        pending.extend(chunks)
        if len(pending) >= EMBED_BATCH_CHUNKS:
            flush()
    flush()

    for path in set(known) - seen:  # notes deleted from disk
        store.delete_note(source, path)
        catalog.delete_note(source, path)
        report.removed += 1

    report.seconds = time.time() - start
    return report
