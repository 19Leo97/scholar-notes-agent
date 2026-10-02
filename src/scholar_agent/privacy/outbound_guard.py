"""Prevents verbatim text from the user's notes leaking into external search queries.

The model only knows what it was shown, so it is enough to compare outgoing queries against
the note evidence collected during the current run.
"""

from __future__ import annotations

from dataclasses import dataclass

from scholar_agent.citations.evidence import EvidenceStore
from scholar_agent.text import normalize


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""


class OutboundGuard:
    def __init__(self, store: EvidenceStore, ngram: int = 8):
        self.store = store
        self.n = max(3, ngram)
        self.blocked = 0

    @staticmethod
    def _grams(words: list[str], n: int) -> set[str]:
        return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}

    def check(self, query: str) -> GuardResult:
        words = normalize(query).split()
        if len(words) < self.n:
            return GuardResult(True)  # short keyword queries cannot reproduce a passage
        query_grams = self._grams(words, self.n)
        for ev in self.store.by_kind("note"):
            text_grams = self._grams(normalize(ev.text).split(), self.n)
            if query_grams & text_grams:
                self.blocked += 1
                return GuardResult(
                    False,
                    f"Query copies {self.n}+ consecutive words from a private note ({ev.id}). "
                    "Rewrite it as a short generic keyword query without quoting the note.",
                )
        return GuardResult(True)
