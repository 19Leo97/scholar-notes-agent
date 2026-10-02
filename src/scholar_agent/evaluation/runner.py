"""Dispatch `research eval <suite>`."""

from __future__ import annotations

from rich.console import Console

from scholar_agent.config import Settings

SUITES = ("retrieval", "retrieval-es", "verification", "pubmedqa", "vault", "references")


def run_suite(suite: str, settings: Settings, limit: int | None, console: Console, judge: bool = False,
              cache: bool = True, offline: bool = False) -> dict:
    if suite not in SUITES:
        raise SystemExit(f"Unknown suite {suite!r}. Choose one of: {', '.join(SUITES)}")
    if suite in ("retrieval", "retrieval-es"):
        from scholar_agent.evaluation import retrieval

        return retrieval.run(settings, limit, console, cross_lingual=suite == "retrieval-es")

    from scholar_agent.evaluation import agentic
    from scholar_agent.evaluation.common import enable_llm_cache

    settings.validate_privacy()
    if cache:
        enable_llm_cache(settings, console)
    runners = {"verification": agentic.run_verification, "pubmedqa": agentic.run_pubmedqa,
               "vault": agentic.run_vault, "references": agentic.run_references}
    return runners[suite](settings, limit, console, judge=judge, offline=offline)
