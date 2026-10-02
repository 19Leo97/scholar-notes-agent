"""End-to-end graph tests with scripted models: no network, no API keys."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from fakes import ScriptedChatModel, evidence_lines, first_words
from scholar_agent.agent.runner import IndexMissingError, ResearchAgent
from scholar_agent.agent.schemas import AIIdea, Citation, Claim, Plan, Section, Synthesis
from scholar_agent.tools.literature.models import Paper
from scholar_agent.tools.literature.search import LiteratureSearch

PLAN = Plan(intent="question", language="es", sub_questions=["¿Qué detecta el NMDAR?"],
            notes_queries=["receptor NMDA coincidencia magnesio"], literature_queries=["NMDA receptor coincidence"])


def tool_call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}])


def good_synthesis(messages) -> Synthesis:
    ev_id, body = evidence_lines(messages)[0]
    return Synthesis(
        sections=[Section(title="Respuesta", claims=[
            Claim(text="Hay evidencia relevante.", citations=[Citation(id=ev_id, quote=first_words(body, 9, 2))])])],
        ai_ideas=[AIIdea(idea="Idea propia del agente.", rationale="Por analogía.", based_on=[ev_id])],
    )


def bad_synthesis(messages) -> Synthesis:
    synth = good_synthesis(messages)
    synth.sections[0].claims.append(Claim(text="Inventada.", citations=[
        Citation(id="N1", quote="el magnesio acelera la replicación del ADN mitocondrial")]))
    return synth


def models(synth_builders, agent_script=None, router=None, **kw):
    return {
        "router": ScriptedChatModel(structured={"Plan": [router or (lambda m: PLAN)]}),
        "agent": ScriptedChatModel(script=agent_script or [AIMessage(content="DONE")]),
        "synthesizer": ScriptedChatModel(structured={"Synthesis": synth_builders}, **kw),
    }


def test_notes_mode_is_cited_private_and_budgeted(settings, services):
    m = models([good_synthesis], [tool_call("search_notes", query="magnesio NMDAR", k=3),
                                  tool_call("search_papers", query="forbidden in notes mode"),
                                  AIMessage(content="DONE")])
    result = ResearchAgent(settings, services, m).ask("¿Qué detecta coincidencias en la LTP?", mode="notes")

    assert result.external_calls == 0, "notes mode must never touch external services"
    assert result.report.ok and result.removed_claims == 0
    assert "[N" in result.markdown and "💡" in result.markdown and "[IA-1]" in result.markdown
    assert "## Referencias" in result.markdown and "Notas personales" in result.markdown
    assert result.usage.llm_calls == 5 and result.usage.input_tokens > 0       # router + 3 agent + synth
    assert set(result.usage.by_role) == {"router", "agent", "synthesizer"}
    assert result.cited_ids and all(i.startswith("N") for i in result.cited_ids)
    assert settings.index_dir.joinpath("usage.sqlite").exists()


def test_repair_pass_fixes_fabricated_quote(settings, services):
    m = models([bad_synthesis, good_synthesis])
    result = ResearchAgent(settings, services, m).ask("¿Qué es la LTP?", mode="notes")
    assert len(m["synthesizer"].seen) == 2, "one repair attempt expected"
    assert "problems" in str(m["synthesizer"].seen[1][0].content)
    assert result.report.ok and result.removed_claims == 0
    assert "Inventada" not in result.markdown


def test_unrepairable_claims_are_removed_not_shown(settings, services):
    m = models([bad_synthesis])
    result = ResearchAgent(settings, services, m).ask("¿Qué es la LTP?", mode="notes")
    assert result.removed_claims == 1 and "Inventada" not in result.markdown
    assert "eliminadas por falta de respaldo" in result.markdown


def test_literature_mode_cites_papers_with_doi_and_skips_notes(settings, monkeypatch):
    paper = Paper(title="Long-lasting potentiation of synaptic transmission", authors=["Tim V. P. Bliss", "Terje Lømo"],
                  year=1973, venue="The Journal of Physiology", doi="10.1113/jphysiol.1973.sp010273",
                  abstract="Trains of high frequency stimulation produced a long-lasting increase in synaptic efficacy.",
                  sources=["openalex"])
    monkeypatch.setattr(LiteratureSearch, "search", lambda self, q, limit=6, year_from=None: [paper])

    def synth(messages):
        ev_id, body = evidence_lines(messages)[0]
        assert ev_id.startswith("P")  # no personal notes in literature mode
        return Synthesis(sections=[Section(title="Evidencia", claims=[Claim(
            text="La estimulación de alta frecuencia produjo potenciación duradera.",
            citations=[Citation(id=ev_id, quote="long-lasting increase in synaptic efficacy")])])])

    result = ResearchAgent(settings, services=None, models=models([synth])).ask("¿Qué es la LTP?", mode="literature")
    assert result.external_calls >= 1 and result.cited_ids == ["P1"]
    assert "Bliss, T. V. P." in result.markdown and "https://doi.org/10.1113/jphysiol.1973.sp010273" in result.markdown
    assert "Artículos científicos" in result.markdown and "Notas personales" not in result.markdown


def test_no_evidence_means_no_synthesis_call(settings, monkeypatch):
    monkeypatch.setattr(LiteratureSearch, "search", lambda self, q, limit=6, year_from=None: [])
    m = models([good_synthesis])
    result = ResearchAgent(settings, None, m).ask("pregunta sin resultados", mode="literature")
    assert m["synthesizer"].seen == [] and "No se encontró evidencia" in result.markdown


def test_budget_exhaustion_skips_research_but_still_answers(settings, services):
    m = models([good_synthesis], [tool_call("search_notes", query="x")], router=None)
    m["router"] = ScriptedChatModel(structured={"Plan": [lambda msgs: PLAN]}, in_tokens=2_000_000)  # ~$0.10
    result = ResearchAgent(settings, services, m).ask("¿Qué es la LTD?", mode="notes", max_cost_usd=0.05)
    assert result.usage.tool_calls == 0 and result.usage.stopped_reason
    assert "[N" in result.markdown, "seed evidence must still allow an answer"


def test_missing_index_has_actionable_error(settings):
    from scholar_agent.services import build_services

    empty = build_services(settings, with_reranker=False)
    try:
        with pytest.raises(IndexMissingError, match="research ingest"):
            ResearchAgent(settings, empty, models([good_synthesis])).ask("hola", mode="notes")
    finally:
        empty.close()


def test_verify_idea_requires_verdict_rendering(settings, services):
    plan = Plan(intent="verify_idea", language="en", notes_queries=["LTP"], literature_queries=["LTP"])

    def synth(messages):
        s = good_synthesis(messages)
        s.verdict = "MIXED"
        return s

    m = models([synth], router=lambda msgs: plan)
    result = ResearchAgent(settings, services, m).ask("LTP needs protein synthesis", mode="notes")
    assert "Verdict on the idea: **Mixed evidence**" in result.markdown
    assert "Agent ideas (not from your sources)" in result.markdown


def test_questions_are_not_treated_as_ideas_to_verify(settings, services):
    plan = Plan(intent="verify_idea", language="es", notes_queries=["NMDA"], literature_queries=["NMDA"])
    m = models([good_synthesis], router=lambda msgs: plan)
    result = ResearchAgent(settings, services, m).ask("¿Qué hace el NMDAR?", mode="notes")
    assert result.plan.intent == "question" and "Veredicto" not in result.markdown
    forced = ResearchAgent(settings, services, models([good_synthesis], router=lambda msgs: plan))
    assert forced.ask("¿Qué hace el NMDAR?", mode="notes", intent="verify_idea").plan.intent == "verify_idea"


def test_empty_synthesis_triggers_a_repair_attempt(settings, services):
    empty = lambda msgs: Synthesis(sections=[])  # noqa: E731
    m = models([empty, good_synthesis])
    result = ResearchAgent(settings, services, m).ask("¿Qué es la LTP?", mode="notes")
    assert len(m["synthesizer"].seen) == 2 and result.cited_ids
