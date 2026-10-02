from __future__ import annotations

from scholar_agent.agent.schemas import AIIdea, Citation, Claim, Section, Synthesis
from scholar_agent.budget.guard import BudgetGuard
from scholar_agent.budget.tracking import QueryTracker, cost_usd
from scholar_agent.citations import validator
from scholar_agent.citations.evidence import EvidenceStore
from scholar_agent.citations.formatter import UsageSummary, render_answer
from scholar_agent.privacy.outbound_guard import OutboundGuard
from scholar_agent.retrieval.hybrid import NoteHit
from scholar_agent.tools.literature.models import Paper

NOTE_TEXT = ("El receptor NMDA solo permite el paso de calcio cuando coinciden la liberación "
             "presináptica de glutamato y la despolarización postsináptica.")


def make_store() -> EvidenceStore:
    store = EvidenceStore()
    store.add_note(NoteHit("demo", "plasticidad/CON — NMDA.md", "CON — NMDA", "Desarrollo", NOTE_TEXT,
                           9, 11, "concept", "es", 1.0))
    store.add_paper(Paper(title="LTP in the hippocampus", authors=["Tim Bliss", "Terje Lømo"], year=1973,
                          abstract="Long-lasting potentiation of synaptic transmission was observed.",
                          doi="10.1113/jphysiol.1973.sp010273", venue="J Physiol"))
    return store


def test_ids_are_stable_and_deduplicated():
    store = make_store()
    again = store.add_note(NoteHit("demo", "plasticidad/CON — NMDA.md", "CON — NMDA", "Desarrollo",
                                   NOTE_TEXT, 9, 11, "concept", "es", 1.0))
    assert again.id == "N1" and store.get("P1").kind == "paper" and len(store) == 2


def test_quote_matching_tolerates_small_edits_but_not_inventions():
    q = validator.quote_in_text
    assert q("solo permite el paso de calcio cuando coinciden", NOTE_TEXT)
    assert q("SOLO permite el paso de CALCIO cuando coinciden", NOTE_TEXT)
    assert q("solo permite el paso de calcio ... cuando coinciden la liberación", NOTE_TEXT)
    assert not q("el receptor NMDA bloquea el paso de sodio en reposo", NOTE_TEXT)
    assert not q("", NOTE_TEXT)


def test_verify_flags_unknown_ids_missing_citations_and_fake_quotes():
    store = make_store()
    synth = Synthesis(sections=[Section(title="x", claims=[
        Claim(text="ok", citations=[Citation(id="N1", quote="paso de calcio cuando coinciden")]),
        Claim(text="no cite", citations=[]),
        Claim(text="ghost", citations=[Citation(id="P9", quote="whatever")]),
        Claim(text="fake quote", citations=[Citation(id="N1", quote="el magnesio nunca bloquea nada")]),
    ])], ai_ideas=[AIIdea(idea="i", rationale="r", based_on=["N1", "N7"])])
    report = validator.verify(synth, store, "question")
    kinds = sorted(i.kind for i in report.issues)
    assert kinds == ["idea_unknown_id", "no_citation", "quote_not_found", "unknown_id"]

    pruned = validator.prune(synth, store, report)
    claims = [c.text for s in pruned.sections for c in s.claims]
    assert claims == ["ok"] and report.removed_claims == 3
    assert pruned.ai_ideas[0].based_on == ["N1"]


def test_verdict_only_for_verify_idea():
    store = make_store()
    claim = Claim(text="ok", citations=[Citation(id="N1", quote="paso de calcio cuando coinciden")])
    synth = Synthesis(sections=[Section(title="x", claims=[claim])], verdict="SUPPORTED")
    assert not validator.verify(synth, store, "question").ok
    assert validator.verify(synth, store, "verify_idea").ok


def test_empty_answer_with_available_evidence_is_flagged():
    report = validator.verify(Synthesis(sections=[]), make_store(), "question")
    assert [i.kind for i in report.issues] == ["empty_answer"]
    assert validator.verify(Synthesis(sections=[]), EvidenceStore(), "question").ok


def test_render_labels_ai_ideas_and_groups_references():
    store = make_store()
    synth = Synthesis(
        sections=[Section(title="Mecanismo", claims=[Claim(
            text="El NMDAR detecta coincidencias.",
            citations=[Citation(id="N1", quote="paso de calcio cuando coinciden")])])],
        ai_ideas=[AIIdea(idea="Quizá el Mg2+ module la metaplasticidad.", rationale="Por analogía.",
                         based_on=["N1"])],
    )
    usage = UsageSummary(1200, 300, 0.0123, 3, 2, {})
    md = render_answer(synth, store, "es", "question", "gemini-2.5-flash", usage)
    assert "[N1]" in md and "[IA-1]" in md
    assert "Ideas del agente" in md and "Notas personales" in md
    assert "plasticidad/CON — NMDA.md:9-11" in md and "[[CON — NMDA#Desarrollo]]" in md
    assert "P1" not in md.split("## Referencias")[1]  # uncited papers are not listed
    assert "1,200 in / 300 out" in md and "$0.0123" in md


def test_outbound_guard_blocks_pasted_note_text_only():
    store = make_store()
    guard = OutboundGuard(store, ngram=8)
    assert guard.check("NMDAR LTP calcium").allowed
    assert guard.check("receptor NMDA solo permite el paso").allowed
    leak = guard.check("papers about el receptor NMDA solo permite el paso de calcio cuando coinciden la liberación")
    assert not leak.allowed and "N1" in leak.reason


def test_budget_guard_degrades_gracefully(settings):
    tracker = QueryTracker(settings)
    guard = BudgetGuard(settings.budget, tracker)
    assert guard.check_and_mark()
    tracker.tool_calls = settings.budget.max_tool_calls
    assert not guard.check_and_mark() and "tool-call" in guard.reason


def test_cost_from_pricing(settings):
    usd = cost_usd(settings, "gemini-2.5-flash", 1_000_000, 1_000_000)
    assert usd == settings.pricing["gemini-2.5-flash"]["input"] + settings.pricing["gemini-2.5-flash"]["output"]
    assert cost_usd(settings, "llama3.2", 5000, 5000) == 0.0


def test_pack_interleaves_kinds_within_budget():
    store = EvidenceStore()
    for i in range(10):
        store.add_note(NoteHit("d", f"n{i}.md", f"N{i}", "", "texto " * 200, 1, 5, "concept", "es", 1.0), rank=i)
    store.add_paper(Paper(title="Paper", abstract="abstract " * 100, doi="10.1/x"))
    packed = store.pack(each_tokens=100, total_tokens=500)
    assert any(e.kind == "paper" for e in packed) and len(packed) < 11
