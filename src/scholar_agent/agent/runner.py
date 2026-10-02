"""Public entry point: ResearchAgent.ask(question, mode) -> AgentResult."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from scholar_agent.agent.context import RunContext
from scholar_agent.agent.graph import build_graph
from scholar_agent.agent.schemas import Plan, Synthesis
from scholar_agent.budget.guard import BudgetGuard
from scholar_agent.budget.tracking import Ledger, QueryTracker
from scholar_agent.cache.http_cache import HttpClient
from scholar_agent.citations.evidence import Evidence, EvidenceStore
from scholar_agent.citations.formatter import UsageSummary
from scholar_agent.citations.validator import VerificationReport
from scholar_agent.config import Mode, Role, Settings
from scholar_agent.llm.factory import ModelHub
from scholar_agent.privacy.outbound_guard import OutboundGuard
from scholar_agent.retrieval.hybrid import NoteRetriever
from scholar_agent.services import Services, build_services
from scholar_agent.tools.literature.search import LiteratureSearch
from scholar_agent.tools.web import WebSearch


class IndexMissingError(RuntimeError):
    pass


@dataclass
class AgentResult:
    question: str
    mode: Mode
    plan: Plan
    markdown: str
    synthesis: Synthesis
    evidence: list[Evidence]                  # everything collected
    cited_ids: list[str]
    report: VerificationReport
    usage: UsageSummary
    query_id: str
    external_calls: int
    removed_claims: int = 0
    extra: dict = field(default_factory=dict)

    def to_vault_note(self) -> str:
        """Obsidian-compatible SIN note so answers can flow back into the user's vault."""
        title = self.question.strip().rstrip("?¿")[:80]
        notes = [e.meta.get("path") for e in self.evidence if e.kind == "note" and e.id in self.cited_ids]
        front = ("---\ntipo: síntesis\nestado: borrador\narea: investigación-asistida\n"
                 f"fecha: {date.today().isoformat()}\nfuentes: []\ntags: [respuesta-del-agente]\n---\n\n")
        return f"{front}# SIN — {title}\n\n## En una línea\n{self.question}\n\n## Desarrollo\n{self.markdown}\n" \
               + ("\n## Relaciones\n" + "\n".join(f"- **Usa** → [[{Path(p).stem}]]" for p in dict.fromkeys(n for n in notes if n)) + "\n"
                  if notes else "")


class ResearchAgent:
    def __init__(
        self,
        settings: Settings,
        services: Services | None = None,
        models: dict[Role, BaseChatModel] | None = None,
        http: HttpClient | None = None,
    ):
        if models is None:
            settings.validate_privacy()
        self.settings = settings
        self._services = services
        self._models = models
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or HttpClient(settings.cache_dir / "http.sqlite", settings.literature.http_cache_days)
        settings.index_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(settings.index_dir / "usage.sqlite")

    def close(self) -> None:
        """Release the vector store and SQLite handles (call once when done)."""
        if self._services is not None:
            self._services.close()
            self._services = None

    def _get_services(self) -> Services:
        if self._services is None:
            self._services = build_services(self.settings)
        return self._services

    def ask(
        self,
        question: str,
        mode: Mode = "hybrid",
        max_cost_usd: float | None = None,
        progress: Callable[[str], None] | None = None,
        intent: str | None = None,
    ) -> AgentResult:
        settings = self.settings
        if max_cost_usd is not None:
            settings = settings.model_copy(deep=True)
            settings.budget.max_cost_usd = max_cost_usd
        groups = list(settings.modes[mode].groups)

        services = retriever = None
        if "notes" in groups:
            services = self._get_services()
            if services.catalog.stats()["notes"] == 0:
                raise IndexMissingError("No notes indexed yet. Run: research ingest <path-to-notes>")
            retriever = NoteRetriever(services)

        tracker = QueryTracker(settings)
        evidence = EvidenceStore()
        ctx = RunContext(
            settings=settings, mode=mode, question=question, tracker=tracker,
            guard=BudgetGuard(settings.budget, tracker), evidence=evidence,
            outbound=OutboundGuard(evidence, settings.privacy.outbound_ngram), http=self.http,
            literature=LiteratureSearch(self.http, settings.literature),
            web=WebSearch(self.http, settings.web), services=services, retriever=retriever, groups=groups,
            forced_intent=intent,
        )
        hub = ModelHub(settings, tracker, self._models)
        graph = build_graph(ctx, hub, progress)
        state = graph.invoke({"messages": []}, config={"recursion_limit": 40})
        self.ledger.record(tracker, question)

        final: Synthesis = state["final_synthesis"]
        cited = list(dict.fromkeys(
            [c.id for s in final.sections for cl in s.claims for c in cl.citations]
            + [r for i in final.ai_ideas for r in i.based_on]
        ))
        return AgentResult(
            question=question, mode=mode, plan=state["plan"], markdown=state["answer"], synthesis=final,
            evidence=evidence.all(), cited_ids=cited, report=state["report"], usage=state["usage"],
            query_id=tracker.query_id, external_calls=ctx.external_calls,
            removed_claims=state.get("removed_claims", 0),
        )
