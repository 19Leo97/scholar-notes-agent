"""Helpers shared by the evaluation suites."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

from scholar_agent.cache.llm_cache import SQLiteLLMCache
from scholar_agent.config import Settings
from scholar_agent.indexing.embedder import HashEmbedder
from scholar_agent.ingestion.pipeline import ingest
from scholar_agent.services import Services, build_services

DATA_DIR = Path(__file__).parent / "data"


def eval_cache(settings: Settings) -> Path:
    path = settings.cache_dir / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def enable_llm_cache(settings: Settings, console: Console) -> SQLiteLLMCache:
    from langchain_core.globals import set_llm_cache

    cache = SQLiteLLMCache(eval_cache(settings) / "llm_cache.sqlite")
    set_llm_cache(cache)
    console.print("[dim]LLM response cache enabled: identical prompts are not paid twice.[/dim]")
    return cache


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def eval_services(settings: Settings, notes_dir: Path, name: str, console: Console,
                  allow_hash_fallback: bool = False) -> tuple[Services, bool]:
    """Index `notes_dir` with the real ingestion pipeline into an isolated, cached index.

    Returns (services, dense_available). If the configured embedder is unreachable and
    `allow_hash_fallback` is set, a hash embedder is used so lexical retrieval can still be evaluated.
    """
    emb = settings.embeddings
    isolated = settings.model_copy(deep=True)
    isolated.paths.index_dir = str(eval_cache(settings) / f"{name}_{slug(emb.provider + '-' + emb.model)}")
    isolated.paths.sqlite = str(Path(isolated.paths.index_dir) / "catalog.sqlite")
    svc = build_services(isolated)
    dense_ok = True
    try:
        svc.embedder.embed_query("probe")
    except RuntimeError as exc:
        if not allow_hash_fallback:
            raise
        console.print(f"[yellow]Dense embedder unavailable ({str(exc)[:90]}). Lexical-only evaluation.[/yellow]")
        svc.close()
        isolated.embeddings.provider = "hash"
        isolated.paths.index_dir = str(eval_cache(settings) / f"{name}_hash")
        isolated.paths.sqlite = str(Path(isolated.paths.index_dir) / "catalog.sqlite")
        svc = build_services(isolated)
        dense_ok = False
    with console.status(f"Indexing {name} (cached after the first run)...") as status:
        report = ingest(
            notes_dir, name, svc.embedder, svc.store, svc.catalog,
            isolated.chunking.max_tokens, isolated.chunking.min_tokens,
            progress=lambda i, n, f: status.update(f"Indexing {name}: {i}/{n}"),
        )
    console.print(f"[dim]{name}: {report.added + report.updated} notes (re)indexed, {report.unchanged} cached, "
                  f"embedder {svc.embedder.name}[/dim]")
    return svc, dense_ok


def hash_embedder_name() -> str:
    return HashEmbedder().name
