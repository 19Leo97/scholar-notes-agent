from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from scholar_agent.config import Settings, load_settings  # noqa: E402
from scholar_agent.ingestion.pipeline import ingest  # noqa: E402
from scholar_agent.services import build_services  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_vault"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return load_settings(overrides={
        "embeddings": {"provider": "hash"},
        "paths": {"index_dir": str(tmp_path / "index"), "cache_dir": str(tmp_path / "cache"),
                  "sqlite": str(tmp_path / "index" / "catalog.sqlite")},
        "privacy": {"gemini_paid_tier": True},
        "literature": {"verify_dois": False},
    })


@pytest.fixture()
def services(settings: Settings):
    svc = build_services(settings, with_reranker=False)
    ingest(DEMO, "demo", svc.embedder, svc.store, svc.catalog)
    yield svc
    svc.close()
