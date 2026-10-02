"""Per-query runtime context shared by the tools and graph nodes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scholar_agent.budget.guard import BudgetGuard
from scholar_agent.budget.tracking import QueryTracker
from scholar_agent.cache.http_cache import HttpClient
from scholar_agent.citations.evidence import EvidenceStore
from scholar_agent.config import Mode, Settings
from scholar_agent.privacy.outbound_guard import OutboundGuard
from scholar_agent.retrieval.hybrid import NoteRetriever
from scholar_agent.services import Services
from scholar_agent.tools.literature.search import LiteratureSearch
from scholar_agent.tools.web import WebSearch


@dataclass
class RunContext:
    settings: Settings
    mode: Mode
    question: str
    tracker: QueryTracker
    guard: BudgetGuard
    evidence: EvidenceStore
    outbound: OutboundGuard
    http: HttpClient
    literature: LiteratureSearch
    web: WebSearch
    services: Services | None = None
    retriever: NoteRetriever | None = None
    groups: Sequence[str] = field(default_factory=list)
    external_calls: int = 0           # literature/web calls made (must stay 0 in notes mode)
    forced_intent: str | None = None  # evaluation harnesses can pin the intent (e.g. verify_idea)

    def source_root(self, source: str) -> Path | None:
        if self.services is None:
            return None
        value = self.services.catalog.get_meta("root:" + source)
        return Path(value) if value else None
