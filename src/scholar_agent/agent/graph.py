"""The LangGraph state machine: plan -> seed -> research loop -> synthesize -> verify -> render."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from scholar_agent.agent.context import RunContext
from scholar_agent.agent.schemas import Plan, Synthesis
from scholar_agent.citations import validator
from scholar_agent.citations.formatter import UsageSummary, render_answer
from scholar_agent.llm.factory import ModelHub, invoke_structured
from scholar_agent.text import detect_language
from scholar_agent.tools.registry import build_tools, search_notes_core, search_papers_core

PROMPTS = Path(__file__).parent / "prompts"

MODE_NOTES = {
    "notes": "Only the user's personal notes are available; no external source is consulted.",
    "literature": "Only external sources (scientific literature and the web) are available; the "
    "user's personal notes are NOT consulted.",
    "hybrid": "Personal notes and external literature/web are both available: contrast them.",
}


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    plan: Plan
    synthesis: Synthesis
    report: validator.VerificationReport
    needs_repair: bool
    repair_attempts: int
    answer: str
    removed_claims: int
    final_synthesis: Synthesis
    usage: UsageSummary


def build_graph(ctx: RunContext, hub: ModelHub, progress: Callable[[str], None] | None = None):
    emit = progress or (lambda _msg: None)
    settings, budget = ctx.settings, ctx.settings.budget
    tools = build_tools(ctx)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    bound: dict[str, Any] = {}

    # ------------------------------------------------------------------ plan
    def plan_node(state: AgentState) -> dict:
        emit("planning")
        try:
            plan = invoke_structured(
                hub, "router", Plan,
                [SystemMessage(_prompt("plan")), HumanMessage(f"Question: {ctx.question}")],
            )
        except Exception:
            plan = Plan(intent="question", language="en" if detect_language(ctx.question) == "en" else "es")
        if ctx.forced_intent:
            plan.intent = ctx.forced_intent  # type: ignore[assignment]
        elif plan.intent == "verify_idea" and ctx.question.strip().endswith("?"):
            plan.intent = "question"  # small routers over-trigger verify_idea on plain questions
        plan.sub_questions = plan.sub_questions[:3]
        plan.notes_queries = [q for q in plan.notes_queries if q.strip()][:2] or [ctx.question]
        plan.literature_queries = [q for q in plan.literature_queries if q.strip()][:2] or [ctx.question]
        return {"plan": plan}

    # ------------------------------------------------------------------ seed
    def seed_node(state: AgentState) -> dict:
        emit("retrieving seed evidence")
        plan = state["plan"]
        def notes_job(q: str) -> str:
            return f"NOTES for '{q}':\n" + search_notes_core(ctx, q, k=5, snippet_tokens=60)

        def papers_job(q: str) -> str:
            return f"PAPERS for '{q}':\n" + search_papers_core(ctx, q, limit=5, snippet_tokens=50)

        jobs: list[tuple[Callable[[str], str], str]] = []
        if "notes" in ctx.groups and ctx.retriever is not None:
            jobs += [(notes_job, q) for q in plan.notes_queries]
        if "literature" in ctx.groups:
            jobs += [(papers_job, q) for q in plan.literature_queries]
        with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
            blocks = list(pool.map(lambda job: job[0](job[1]), jobs))
        subs = "\n".join(f"- {s}" for s in plan.sub_questions)
        content = (f"Question: {ctx.question}\nIntent: {plan.intent}\nSub-questions:\n{subs or '- (none)'}\n\n"
                   "SEED EVIDENCE\n" + "\n\n".join(blocks))
        return {"messages": [HumanMessage(content)]}

    # ------------------------------------------------------------- research
    def agent_node(state: AgentState) -> dict:
        if not ctx.guard.check_and_mark():
            return {"messages": [AIMessage(content="DONE")]}
        ctx.guard.next_iteration()
        emit(f"research step {ctx.guard.iterations}")
        if "agent" not in bound:
            bound["agent"] = hub.model("agent").bind_tools(tools)
        system = _prompt("research").format(mode=ctx.mode, mode_note=MODE_NOTES[ctx.mode])
        reply = bound["agent"].invoke([SystemMessage(system), *state["messages"]], config=hub.config("agent"))
        return {"messages": [reply]}

    def after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and ctx.guard.check_and_mark():
            return "tools"
        return "synthesize"

    # ----------------------------------------------------------- synthesize
    def synthesize_node(state: AgentState) -> dict:
        plan = state["plan"]
        packed = ctx.evidence.pack(budget.evidence_tokens_each, budget.evidence_tokens_total)
        if not packed:
            emit("no evidence found")
            return {"synthesis": Synthesis(sections=[], gaps=[]), "needs_repair": False}
        emit("synthesizing")
        repair = ""
        if state.get("needs_repair") and state.get("report"):
            repair = ("\nYour previous attempt had problems. Fix them: cite only existing IDs and copy "
                      "quotes verbatim, or drop the claim.\n" + state["report"].feedback())
        system = _prompt("synthesize").format(
            language="Spanish" if plan.language == "es" else "English", intent=plan.intent,
            mode=ctx.mode, mode_note=MODE_NOTES[ctx.mode], repair=repair,
        )
        subs = "; ".join(plan.sub_questions)
        human = (f"Question: {ctx.question}\nSub-questions: {subs or 'n/a'}\n\nEVIDENCE\n"
                 + ctx.evidence.render_block(packed, budget.evidence_tokens_each))
        synthesis = invoke_structured(hub, "synthesizer", Synthesis, [SystemMessage(system), HumanMessage(human)])
        return {"synthesis": synthesis}

    # --------------------------------------------------------------- verify
    def verify_node(state: AgentState) -> dict:
        emit("verifying citations")
        report = validator.verify(state["synthesis"], ctx.evidence, state["plan"].intent)
        attempts = state.get("repair_attempts", 0)
        affordable = ctx.tracker.cost < budget.max_cost_usd * 0.9
        needs_repair = (not report.ok) and attempts < 1 and affordable
        return {"report": report, "needs_repair": needs_repair,
                "repair_attempts": attempts + (1 if needs_repair else 0)}

    def after_verify(state: AgentState) -> str:
        return "synthesize" if state.get("needs_repair") else "render"

    # --------------------------------------------------------------- render
    def render_node(state: AgentState) -> dict:
        emit("rendering")
        report = state["report"]
        final = validator.prune(state["synthesis"], ctx.evidence, report)
        if settings.literature.verify_dois:
            validator.verify_cited_dois(final, ctx.evidence, ctx.http)
        usage = UsageSummary(
            input_tokens=ctx.tracker.input_tokens, output_tokens=ctx.tracker.output_tokens,
            cost_usd=ctx.tracker.cost, llm_calls=ctx.tracker.llm_calls,
            tool_calls=ctx.tracker.tool_calls, by_role=ctx.tracker.by_role(),
            stopped_reason=ctx.guard.reason,
        )
        answer = render_answer(
            final, ctx.evidence, state["plan"].language, state["plan"].intent,
            settings.llm["synthesizer"].model, usage, removed_claims=report.removed_claims,
        )
        return {"answer": answer, "final_synthesis": final, "usage": usage,
                "removed_claims": report.removed_claims}

    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("seed", seed_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node)
    graph.add_node("render", render_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "seed")
    graph.add_edge("seed", "agent")
    graph.add_conditional_edges("agent", after_agent, {"tools": "tools", "synthesize": "synthesize"})
    graph.add_edge("tools", "agent")
    graph.add_edge("synthesize", "verify")
    graph.add_conditional_edges("verify", after_verify, {"synthesize": "synthesize", "render": "render"})
    graph.add_edge("render", END)
    return graph.compile()
