"""Deterministic verification of a Synthesis against the EvidenceStore (no LLM calls)."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from scholar_agent.agent.schemas import AIIdea, Citation, Claim, Section, Synthesis
from scholar_agent.cache.http_cache import HttpClient
from scholar_agent.citations.doi import verify_doi
from scholar_agent.citations.evidence import EvidenceStore
from scholar_agent.text import normalize


@dataclass
class Issue:
    kind: str          # no_citation | unknown_id | quote_not_found | idea_unknown_id | verdict_without_idea
    detail: str


@dataclass
class VerificationReport:
    issues: list[Issue] = field(default_factory=list)
    removed_claims: int = 0
    removed_citations: int = 0
    claims_total: int = 0
    claims_supported: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues

    def feedback(self) -> str:
        return "\n".join(f"- [{i.kind}] {i.detail}" for i in self.issues[:12])


def quote_in_text(quote: str, text: str) -> bool:
    """Normalised containment, tolerating small edits (ellipses, punctuation, a dropped word)."""
    q, t = normalize(quote), normalize(text)
    if not q:
        return False
    if q in t:
        return True
    qt, tt = q.split(), t.split()
    if len(qt) < 4:
        return False
    run = SequenceMatcher(None, qt, tt, autojunk=False).find_longest_match(0, len(qt), 0, len(tt)).size
    coverage = sum(1 for w in qt if w in set(tt)) / len(qt)
    return run / len(qt) >= 0.6 and coverage >= 0.85


def _citation_ok(c: Citation, store: EvidenceStore, issues: list[Issue], where: str) -> bool:
    ev = store.get(c.id.strip())
    if ev is None:
        issues.append(Issue("unknown_id", f"{where}: cites {c.id}, which does not exist"))
        return False
    if not quote_in_text(c.quote, ev.text):
        issues.append(Issue("quote_not_found", f"{where}: quote not found verbatim in {c.id}: {c.quote[:80]!r}"))
        return False
    return True


def verify(synthesis: Synthesis, store: EvidenceStore, intent: str) -> VerificationReport:
    report = VerificationReport()
    for section in synthesis.sections:
        for claim in section.claims:
            report.claims_total += 1
            where = f"claim {claim.text[:50]!r}"
            if not claim.citations:
                report.issues.append(Issue("no_citation", f"{where}: has no citations"))
                continue
            valid = [_citation_ok(c, store, report.issues, where) for c in claim.citations]
            if any(valid):  # a claim survives pruning if at least one citation checks out
                report.claims_supported += 1
    if not synthesis.sections and len(store):
        report.issues.append(Issue("empty_answer", "no claims were produced although evidence is available"))
    for idea in synthesis.ai_ideas:
        for ref in idea.based_on:
            if store.get(ref.strip()) is None:
                report.issues.append(Issue("idea_unknown_id", f"AI idea {idea.idea[:40]!r} references {ref}"))
    if synthesis.verdict and intent != "verify_idea":
        report.issues.append(Issue("verdict_without_idea", "verdict given although intent is not verify_idea"))
    return report


def prune(synthesis: Synthesis, store: EvidenceStore, report: VerificationReport) -> Synthesis:
    """Drop whatever cannot be verified. The final answer never contains unsupported claims."""
    sections: list[Section] = []
    for section in synthesis.sections:
        claims: list[Claim] = []
        for claim in section.claims:
            kept = []
            for c in claim.citations:
                ev = store.get(c.id.strip())
                if ev is not None and quote_in_text(c.quote, ev.text):
                    kept.append(Citation(id=ev.id, quote=c.quote))
                else:
                    report.removed_citations += 1
            if kept:
                claims.append(Claim(text=claim.text, citations=kept))
            else:
                report.removed_claims += 1
        if claims:
            sections.append(Section(title=section.title, claims=claims))
    ideas = [
        AIIdea(idea=i.idea, rationale=i.rationale, based_on=[r.strip() for r in i.based_on if store.get(r.strip())])
        for i in synthesis.ai_ideas
    ]
    return Synthesis(sections=sections, ai_ideas=ideas, verdict=synthesis.verdict, gaps=synthesis.gaps)


def verify_cited_dois(synthesis: Synthesis, store: EvidenceStore, http: HttpClient) -> None:
    """Attach a Crossref/DataCite check to every cited paper that has a DOI."""
    cited = {c.id for s in synthesis.sections for cl in s.claims for c in cl.citations}
    for ev_id in sorted(cited):
        ev = store.get(ev_id)
        if ev and ev.kind == "paper" and ev.meta.get("doi") and ev.doi_check is None:
            ev.doi_check = verify_doi(http, ev.meta["doi"], ev.title)
