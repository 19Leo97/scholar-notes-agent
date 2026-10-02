"""Persist evaluation runs: a JSON record for provenance and a Markdown table for the README."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from scholar_agent.config import PACKAGE_ROOT, Settings


def prompts_hash() -> str:
    """Fingerprint of all prompt files, so results can be tied to the exact prompts used."""
    digest = hashlib.sha1()
    for path in sorted((PACKAGE_ROOT / "src" / "scholar_agent" / "agent" / "prompts").glob("*.md")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def config_fingerprint(settings: Settings) -> dict:
    return {
        "llm": {role: f"{s.provider}:{s.model}" for role, s in settings.llm.items()},
        "embeddings": f"{settings.embeddings.provider}:{settings.embeddings.model}",
        "reranker": settings.reranker.provider,
        "retrieval": settings.retrieval.model_dump(),
        "chunking": settings.chunking.model_dump(),
        "budget": settings.budget.model_dump(),
        "prompts_hash": prompts_hash(),
    }


def reports_dir() -> Path:
    path = Path.cwd() / "eval" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_report(suite: str, settings: Settings, summary: dict, table_md: str, records: list | None = None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    payload: dict[str, Any] = {"suite": suite, "timestamp": stamp, "config": config_fingerprint(settings),
               "summary": summary, "records": records or []}
    out = reports_dir()
    json_path = out / f"{suite}-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out / f"latest-{suite}.md").write_text(
        f"# {suite}\n\n_{stamp} · config `{payload['config']['llm']}` · embeddings "
        f"`{payload['config']['embeddings']}` · prompts `{payload['config']['prompts_hash']}`_\n\n{table_md}\n",
        encoding="utf-8",
    )
    return json_path


def md_table(headers: list[str], rows: list[list]) -> str:
    def cell(v) -> str:
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)
