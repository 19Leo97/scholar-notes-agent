"""EvidenceStore: every piece of text the model may cite gets a stable ID.

IDs: N1.. (personal notes), P1.. (papers), W1.. (web pages). The agent can only cite IDs that
exist here, which is what makes hallucinated references structurally impossible.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from urllib.parse import urlparse

from scholar_agent.citations.doi import DoiCheck
from scholar_agent.retrieval.hybrid import NoteHit
from scholar_agent.text import approx_tokens, truncate_tokens
from scholar_agent.tools.literature.models import Paper

Kind = Literal["note", "paper", "web"]
_PREFIX = {"note": "N", "paper": "P", "web": "W"}


@dataclass
class Evidence:
    id: str
    kind: Kind
    title: str
    text: str                       # grounding text: quotes must be found here
    meta: dict[str, Any] = field(default_factory=dict)
    rank: int = 0                   # position within the tool call that produced it (0 = best)
    deep_read: bool = False         # the agent explicitly opened it (get_note / fetch_url / details)
    doi_check: DoiCheck | None = None

    def header(self) -> str:
        m = self.meta
        if self.kind == "note":
            where = f"{m['path']}:{m['line_start']}-{m['line_end']}"
            tag = " (user's own hypothesis)" if m.get("own_idea") else ""
            sec = f" > {m['heading']}" if m.get("heading") else ""
            return f"[{self.id}] NOTE {self.title}{sec} ({where}, type={m.get('note_kind')}){tag}"
        if self.kind == "paper":
            authors = ", ".join(m.get("authors", [])[:3]) + (" et al." if len(m.get("authors", [])) > 3 else "")
            return f"[{self.id}] PAPER {self.title} ({authors}, {m.get('year')}, {m.get('venue') or 'n/a'})"
        return f"[{self.id}] WEB {self.title} ({m.get('url')})"


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._index: dict[str, str] = {}      # dedup key -> id
        self._counters = {"note": 0, "paper": 0, "web": 0}
        self._lock = threading.RLock()

    # ---- writes ---------------------------------------------------------
    def _new_id(self, kind: Kind) -> str:
        self._counters[kind] += 1
        return f"{_PREFIX[kind]}{self._counters[kind]}"

    def _put(self, kind: Kind, key: str, make: Evidence, deep: bool = False) -> Evidence:
        with self._lock:
            if key in self._index:
                existing = self._items[self._index[key]]
                existing.deep_read = existing.deep_read or deep
                return existing
            make.id = self._new_id(kind)
            make.deep_read = deep
            self._items[make.id] = make
            self._index[key] = make.id
            return make

    def add_note(self, hit: NoteHit, rank: int = 0, deep: bool = False) -> Evidence:
        key = f"note:{hit.source}:{hit.path}:{hit.line_start}-{hit.line_end}"
        ev = Evidence(
            id="", kind="note", title=hit.title, text=hit.text, rank=rank,
            meta={
                "source": hit.source, "path": hit.path, "line_start": hit.line_start,
                "line_end": hit.line_end, "heading": hit.heading, "note_kind": hit.kind,
                "own_idea": hit.kind == "hypothesis", "via": hit.via, "relation": hit.relation,
                "images": hit.images, "urls": hit.urls, **hit.extra,
            },
        )
        return self._put("note", key, ev, deep)

    def add_paper(self, paper: Paper, rank: int = 0, deep: bool = False) -> Evidence:
        body = f"{paper.title}. {paper.abstract}".strip()
        ev = Evidence(
            id="", kind="paper", title=paper.title, text=body, rank=rank,
            meta={
                "authors": paper.authors, "year": paper.year, "venue": paper.venue,
                "doi": paper.doi, "url": paper.link, "sources": paper.sources,
                "citation_count": paper.citation_count, "has_abstract": bool(paper.abstract),
            },
        )
        stored = self._put("paper", paper.key, ev, deep)
        if len(body) > len(stored.text):  # a later lookup brought the abstract
            stored.text = body
            stored.meta["has_abstract"] = bool(paper.abstract)
        return stored

    def add_web(self, url: str, title: str, text: str, rank: int = 0, deep: bool = False) -> Evidence:
        ev = Evidence(
            id="", kind="web", title=title or url, text=text, rank=rank,
            meta={
                "url": url, "site": (urlparse(url).hostname or "").removeprefix("www."),
                "accessed": date.today().isoformat(),
            },
        )
        stored = self._put("web", "web:" + url, ev, deep)
        if len(text) > len(stored.text):
            stored.text = text
        return stored

    # ---- reads ----------------------------------------------------------
    def get(self, evidence_id: str) -> Evidence | None:
        return self._items.get(evidence_id)

    def all(self) -> list[Evidence]:
        return list(self._items.values())

    def by_kind(self, kind: Kind) -> list[Evidence]:
        return [e for e in self._items.values() if e.kind == kind]

    def __len__(self) -> int:
        return len(self._items)

    # ---- context packing ------------------------------------------------
    def pack(self, each_tokens: int, total_tokens: int) -> list[Evidence]:
        """Choose which evidence the synthesizer sees, within a total token budget.

        Deeply-read items first, then by retrieval rank, interleaving kinds so that one
        source type (e.g. 30 note chunks) cannot starve the others.
        """
        groups: dict[str, list[Evidence]] = {}
        for ev in self._items.values():
            groups.setdefault(ev.kind, []).append(ev)
        for items in groups.values():
            items.sort(key=lambda e: (not e.deep_read, e.rank))
        chosen: list[Evidence] = []
        used = 0
        cursors = {k: 0 for k in groups}
        progress = True
        while progress:
            progress = False
            for kind in ("note", "paper", "web"):
                items = groups.get(kind, [])
                if cursors.get(kind, 0) >= len(items):
                    continue
                ev = items[cursors[kind]]
                cursors[kind] += 1
                progress = True
                cost = min(approx_tokens(ev.text), each_tokens) + 30
                if used + cost > total_tokens:
                    continue
                chosen.append(ev)
                used += cost
        order = {"note": 0, "paper": 1, "web": 2}
        chosen.sort(key=lambda e: (order[e.kind], int(e.id[1:])))
        return chosen

    @staticmethod
    def render_block(items: list[Evidence], each_tokens: int) -> str:
        parts = []
        for ev in items:
            parts.append(f"{ev.header()}\n{truncate_tokens(ev.text, each_tokens)}")
        return "\n\n".join(parts)
