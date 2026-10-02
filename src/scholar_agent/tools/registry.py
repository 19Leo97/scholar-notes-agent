"""Agent tools. Each returns compact text and registers what it shows in the EvidenceStore.

Tools are filtered by mode: in `notes` mode the external tools are never even registered, so the
model cannot call them (enforced by construction, not by instruction).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from scholar_agent.cache.http_cache import UnsafeURLError
from scholar_agent.ingestion.chunker import chunk_document
from scholar_agent.ingestion.loaders.base import get_loader
from scholar_agent.retrieval.hybrid import NoteHit
from scholar_agent.text import normalize, truncate_tokens

if TYPE_CHECKING:
    from scholar_agent.agent.context import RunContext


def _oneline(text: str, tokens: int) -> str:
    return truncate_tokens(re.sub(r"\s+", " ", text).strip(), tokens)


# --------------------------------------------------------------------------------------
# Core operations (also used directly by the seeding step, without going through the LLM)
# --------------------------------------------------------------------------------------
def search_notes_core(ctx: RunContext, query: str, k: int = 5, snippet_tokens: int = 90) -> str:
    assert ctx.retriever is not None, "notes tools need an index"
    hits = ctx.retriever.search(query, k=min(max(k, 1), 8))
    lines = []
    for rank, hit in enumerate(hits):
        ev = ctx.evidence.add_note(hit, rank=rank)
        where = f" > {hit.heading}" if hit.heading else ""
        via = f", linked: {hit.relation}" if hit.via == "graph" else ""
        lines.append(f"[{ev.id}] {hit.title}{where} (L{hit.line_start}-{hit.line_end}, {hit.kind}{via}): "
                     f"{_oneline(hit.text, snippet_tokens)}")
    return "\n".join(lines) or "No matching notes."


def search_papers_core(ctx: RunContext, query: str, limit: int = 6, year_from: int | None = None,
                       snippet_tokens: int = 70) -> str:
    verdict = ctx.outbound.check(query)
    if not verdict.allowed:
        return f"BLOCKED: {verdict.reason}"
    ctx.external_calls += 1
    papers = ctx.literature.search(query, limit=min(max(limit, 1), 10), year_from=year_from or None)
    lines = []
    for rank, paper in enumerate(papers):
        ev = ctx.evidence.add_paper(paper, rank=rank)
        authors = ", ".join(paper.authors[:2]) + (" et al." if len(paper.authors) > 2 else "")
        cites = f", cited {paper.citation_count}x" if paper.citation_count else ""
        abstract = _oneline(paper.abstract, snippet_tokens) if paper.abstract else "(no abstract available)"
        lines.append(f"[{ev.id}] {paper.title} ({authors}, {paper.year}, {paper.venue or 'n/a'}{cites}) "
                     f"doi:{paper.doi or 'n/a'}: {abstract}")
    return "\n".join(lines) or "No papers found (providers may be temporarily unavailable)."


# --------------------------------------------------------------------------------------
# Tool argument schemas
# --------------------------------------------------------------------------------------
class SearchNotesArgs(BaseModel):
    query: str = Field(description="Keyword query (Spanish or English) for the user's personal notes.")
    k: int = Field(5, description="Number of note chunks to return (1-8).")


class GetNoteArgs(BaseModel):
    name: str = Field(description="Note title (as in [[wikilinks]]) or relative path.")
    heading: str = Field("", description="Optional section heading to read only that part.")


class FollowLinksArgs(BaseModel):
    name: str = Field(description="Note title or path whose linked neighbours should be listed.")


class SearchPapersArgs(BaseModel):
    query: str = Field(description="Short ENGLISH keyword query for scientific literature. No full sentences.")
    year_from: int = Field(0, description="Only papers published from this year on (0 = any).")
    limit: int = Field(6, description="Number of papers (1-10).")


class PaperDetailsArgs(BaseModel):
    ref: str = Field(description="Evidence ID such as P2, or a DOI, to read the full abstract and metadata.")


class WebSearchArgs(BaseModel):
    query: str = Field(description="Short web search query. Never paste text from the user's notes.")


class FetchUrlArgs(BaseModel):
    url: str = Field(description="Public http(s) URL to read (an item from web_search or a paper link).")


def build_tools(ctx: RunContext) -> list[StructuredTool]:
    budget = ctx.settings.budget
    groups = set(ctx.groups)
    tools: list[StructuredTool] = []

    def counted(fn):
        """Count the call and refuse politely once the tool budget is spent."""
        def wrapper(*args, **kwargs) -> str:
            n = ctx.tracker.count_tool_call()
            if n > budget.max_tool_calls:
                return "TOOL BUDGET EXHAUSTED: stop searching and finish with the evidence already collected."
            try:
                return fn(*args, **kwargs)
            except UnsafeURLError as exc:
                return f"BLOCKED: {exc}"
            except Exception as exc:
                return f"ERROR: {type(exc).__name__}: {exc}"
        wrapper.__name__ = fn.__name__
        return wrapper

    # ---- notes ----------------------------------------------------------
    if "notes" in groups and ctx.retriever is not None:
        def search_notes(query: str, k: int = 5) -> str:
            return search_notes_core(ctx, query, k)

        def _resolve(name: str):
            return ctx.services.catalog.find_note(name)  # type: ignore[union-attr]

        def get_note(name: str, heading: str = "") -> str:
            row = _resolve(name)
            if row is None:
                return f"Note not found: {name}. Use search_notes to find the exact title."
            root = ctx.source_root(row["source"])
            file = (root / row["path"]) if root else None
            loader = get_loader(file) if file else None
            if not (file and file.exists() and loader):
                return "The note file is no longer on disk; re-run ingestion."
            doc = loader.load(row["source"], root, file)  # type: ignore[arg-type]
            chunks = chunk_document(doc, ctx.settings.chunking.max_tokens, ctx.settings.chunking.min_tokens)
            if heading:
                wanted = normalize(heading)
                chunks = [c for c in chunks if wanted in normalize(c.heading)] or chunks
            cap = budget.evidence_tokens_each * 3
            picked: list[Any] = []
            used = 0.0
            for c in chunks:
                cost = len(c.text) / 3.6
                if picked and used + cost > cap:
                    break
                picked.append(c)
                used += cost
            hit = NoteHit(
                source=doc.source, path=doc.path, title=doc.title,
                heading=picked[0].heading if len(picked) == 1 else "",
                text="\n\n".join(c.text for c in picked), line_start=picked[0].line_start,
                line_end=picked[-1].line_end, kind=doc.kind, lang=doc.lang, score=1.0,
                tags=doc.tags, images=sorted({i for c in picked for i in c.images}),
                urls=sorted({u for c in picked for u in c.urls}),
                extra={k: doc.frontmatter[k] for k in ("doi", "año") if k in doc.frontmatter},
            )
            ev = ctx.evidence.add_note(hit, deep=True)
            more = f"\n(note continues: {len(chunks) - len(picked)} more sections; pass heading=...)" \
                if len(picked) < len(chunks) else ""
            return f"{ev.header()}\n{truncate_tokens(hit.text, budget.evidence_tokens_each * 3)}{more}"

        def follow_links(name: str) -> str:
            row = _resolve(name)
            if row is None:
                return f"Note not found: {name}."
            lines = []
            for rank, nb in enumerate(ctx.services.catalog.neighbours(row["source"], row["path"], 8)):  # type: ignore[union-attr]
                lead = ctx.services.store.first_chunk(nb["source"], nb["path"])  # type: ignore[union-attr]
                if lead is None:
                    continue
                label = nb["label"] or ("links here" if nb["direction"] == "in" else "linked")
                hit = NoteHit(
                    source=lead.payload["source"], path=lead.payload["path"], title=lead.payload["title"],
                    heading=lead.payload.get("heading", ""), text=lead.payload["text"],
                    line_start=lead.payload["line_start"], line_end=lead.payload["line_end"],
                    kind=lead.payload.get("kind", "note"), lang=lead.payload.get("lang", "und"),
                    score=0.0, via="graph", relation=label,
                )
                ev = ctx.evidence.add_note(hit, rank=rank)
                lines.append(f"[{ev.id}] {hit.title} ({label}): {_oneline(hit.text, 70)}")
            return "\n".join(lines) or "No linked notes."

        tools += [
            StructuredTool.from_function(
                counted(search_notes), name="search_notes", args_schema=SearchNotesArgs,
                description="Search the user's personal notes (hybrid semantic + keyword). Returns cited snippets."),
            StructuredTool.from_function(
                counted(get_note), name="get_note", args_schema=GetNoteArgs,
                description="Read a specific personal note (or one section) in more depth."),
            StructuredTool.from_function(
                counted(follow_links), name="follow_links", args_schema=FollowLinksArgs,
                description="List notes linked to/from a note via [[wikilinks]], with relation labels."),
        ]

    # ---- literature -----------------------------------------------------
    if "literature" in groups:
        def search_papers(query: str, year_from: int = 0, limit: int = 6) -> str:
            return search_papers_core(ctx, query, limit, year_from)

        def get_paper_details(ref: str) -> str:
            ref = ref.strip()
            ev = ctx.evidence.get(ref.upper())
            if ev is None or ev.kind != "paper":
                paper = ctx.literature.by_doi(ref)
                if paper is None:
                    return f"Paper not found: {ref}"
                ctx.external_calls += 1
                ev = ctx.evidence.add_paper(paper, deep=True)
            ev.deep_read = True
            m = ev.meta
            return (f"{ev.header()}\nDOI: {m.get('doi') or 'n/a'} | cited {m.get('citation_count')}x | "
                    f"sources: {', '.join(m.get('sources', []))}\n"
                    f"{truncate_tokens(ev.text, budget.evidence_tokens_each * 2)}")

        tools += [
            StructuredTool.from_function(
                counted(search_papers), name="search_papers", args_schema=SearchPapersArgs,
                description="Search scientific literature (OpenAlex, Europe PMC, arXiv). Returns titles, years, DOIs, abstracts."),
            StructuredTool.from_function(
                counted(get_paper_details), name="get_paper_details", args_schema=PaperDetailsArgs,
                description="Read the full abstract/metadata of a paper by evidence ID (P#) or DOI."),
        ]

    # ---- web ------------------------------------------------------------
    if "web" in groups:
        def web_search(query: str) -> str:
            verdict = ctx.outbound.check(query)
            if not verdict.allowed:
                return f"BLOCKED: {verdict.reason}"
            ctx.external_calls += 1
            lines = []
            for rank, r in enumerate(ctx.web.search(query)):
                ev = ctx.evidence.add_web(r.url, r.title, r.snippet, rank=rank)
                lines.append(f"[{ev.id}] {r.title} ({r.site}) {r.url}: {_oneline(r.snippet, 70)}")
            return "\n".join(lines) or "No web results."

        def fetch_url(url: str) -> str:
            verdict = ctx.outbound.check(url)
            if not verdict.allowed:
                return f"BLOCKED: {verdict.reason}"
            ctx.external_calls += 1
            title, text = ctx.web.fetch(url)
            if not text:
                return "The page has no extractable text."
            ev = ctx.evidence.add_web(url, title, text, deep=True)
            return f"{ev.header()}\n{_oneline(text, 350)}"

        tools += [
            StructuredTool.from_function(
                counted(web_search), name="web_search", args_schema=WebSearchArgs,
                description="General web search for context that is not in the literature or notes."),
            StructuredTool.from_function(
                counted(fetch_url), name="fetch_url", args_schema=FetchUrlArgs,
                description="Fetch and read the main text of a public web page."),
        ]
    return tools
