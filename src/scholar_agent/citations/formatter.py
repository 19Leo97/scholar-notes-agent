"""Render the verified synthesis as Markdown with inline citations and a grouped bibliography."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from scholar_agent.agent.schemas import Synthesis
from scholar_agent.citations.evidence import Evidence, EvidenceStore

LABELS: dict[str, dict[str, Any]] = {
    "es": {
        "ideas": "Ideas del agente (no provienen de tus fuentes)",
        "ideas_note": "Propuestas del modelo a partir de la evidencia; no están verificadas en la literatura.",
        "gaps": "Vacíos e incertidumbres",
        "refs": "Referencias",
        "notes": "Notas personales",
        "papers": "Artículos científicos",
        "web": "Fuentes web",
        "ia_by": "Propuesta del agente",
        "based": "basada en",
        "speculative": "especulativa, sin evidencia de apoyo",
        "verdict": "Veredicto sobre la idea",
        "verified": "DOI verificado",
        "unverified": "DOI no verificado",
        "mismatch": "el DOI existe pero el título no coincide: revisar",
        "own": "tu hipótesis",
        "accessed": "Accedido",
        "usage": "Uso",
        "pruned": "afirmaciones eliminadas por falta de respaldo",
        "stopped": "Investigación detenida por presupuesto",
        "no_answer": "No se encontró evidencia suficiente para responder con referencias.",
        "verdicts": {
            "SUPPORTED": "Respaldada por la evidencia",
            "REFUTED": "Contradicha por la evidencia",
            "MIXED": "Evidencia mixta",
            "INSUFFICIENT": "Evidencia insuficiente",
        },
    },
    "en": {
        "ideas": "Agent ideas (not from your sources)",
        "ideas_note": "Model proposals derived from the evidence; not verified in the literature.",
        "gaps": "Gaps and uncertainties",
        "refs": "References",
        "notes": "Personal notes",
        "papers": "Scientific papers",
        "web": "Web sources",
        "ia_by": "Agent proposal",
        "based": "based on",
        "speculative": "speculative, no supporting evidence",
        "verdict": "Verdict on the idea",
        "verified": "DOI verified",
        "unverified": "DOI not verified",
        "mismatch": "DOI exists but the title does not match: check",
        "own": "your hypothesis",
        "accessed": "Accessed",
        "usage": "Usage",
        "pruned": "claims removed for lack of support",
        "stopped": "Research stopped by budget",
        "no_answer": "Not enough evidence was found to answer with references.",
        "verdicts": {
            "SUPPORTED": "Supported by the evidence",
            "REFUTED": "Contradicted by the evidence",
            "MIXED": "Mixed evidence",
            "INSUFFICIENT": "Insufficient evidence",
        },
    },
}


@dataclass
class UsageSummary:
    input_tokens: int
    output_tokens: int
    cost_usd: float
    llm_calls: int
    tool_calls: int
    by_role: dict
    stopped_reason: str | None = None


def _surname_initials(name: str) -> str:
    parts = name.replace(",", " ").split()
    if len(parts) < 2:
        return name
    initials = " ".join(p[0] + "." for p in parts[:-1] if p)
    return f"{parts[-1]}, {initials}"


def _authors(authors: list[str]) -> str:
    if not authors:
        return "Anon."
    names = [_surname_initials(a) for a in authors[:6]]
    return ", ".join(names) + (", et al." if len(authors) > 6 else "")


def _anchor(heading: str) -> str:
    return heading.split(" > ")[-1] if heading else ""


def format_reference(ev: Evidence, quotes: list[str], lang: str) -> str:
    L = LABELS[lang]
    m = ev.meta
    quote_txt = "".join(f"\n    > “{q[:180]}”" for q in quotes[:2])
    if ev.kind == "note":
        stem = m["path"].rsplit("/", 1)[-1].removesuffix(".md")
        anchor = _anchor(m.get("heading", ""))
        link = f"[[{stem}#{anchor}]]" if anchor else f"[[{stem}]]"
        own = f" · **{L['own']}**" if m.get("own_idea") else ""
        doi = f" · DOI: https://doi.org/{m['doi'].removeprefix('https://doi.org/')}" if m.get("doi") else ""
        return (f"**[{ev.id}]** {ev.title} — `{m['path']}:{m['line_start']}-{m['line_end']}` · "
                f"{link} · {m.get('note_kind')}{own}{doi}{quote_txt}")
    if ev.kind == "paper":
        year = m.get("year") or "n.d."
        venue = f" *{m['venue']}*." if m.get("venue") else ""
        link = f" https://doi.org/{m['doi']}" if m.get("doi") else (f" {m['url']}" if m.get("url") else "")
        status = ""
        if ev.doi_check is not None:
            if ev.doi_check.status == "verified":
                status = f" — ✔ {L['verified']} ({ev.doi_check.registry})"
            elif ev.doi_check.status == "mismatch":
                status = f" — ⚠ {L['mismatch']}"
            else:
                status = f" — ⚠ {L['unverified']}"
        return f"**[{ev.id}]** {_authors(m.get('authors', []))} ({year}). {ev.title}.{venue}{link}{status}{quote_txt}"
    return (f"**[{ev.id}]** {ev.title}. {m.get('site', '')}. {m.get('url')} "
            f"({L['accessed']}: {m.get('accessed')}){quote_txt}")


def render_answer(
    synthesis: Synthesis,
    store: EvidenceStore,
    lang: str,
    intent: str,
    synth_model: str,
    usage: UsageSummary,
    removed_claims: int = 0,
) -> str:
    L = LABELS.get(lang, LABELS["en"])
    out: list[str] = []
    cited_order: list[str] = []
    quotes: dict[str, list[str]] = {}

    if synthesis.verdict and intent == "verify_idea":
        out.append(f"## {L['verdict']}: **{L['verdicts'][synthesis.verdict]}**\n")

    for section in synthesis.sections:
        out.append(f"### {section.title}\n")
        paragraph = []
        for claim in section.claims:
            marks = ""
            for c in claim.citations:
                marks += f"[{c.id}]"
                if c.id not in cited_order:
                    cited_order.append(c.id)
                quotes.setdefault(c.id, []).append(c.quote.strip())
            paragraph.append(f"{claim.text.strip()} {marks}")
        out.append(" ".join(paragraph) + "\n")

    if not synthesis.sections:
        out.append(f"_{L['no_answer']}_\n")

    ia_refs: list[str] = []
    if synthesis.ai_ideas:
        out.append(f"### 💡 {L['ideas']}\n_{L['ideas_note']}_\n")
        for n, idea in enumerate(synthesis.ai_ideas, 1):
            basis = ", ".join(f"[{r}]" for r in idea.based_on) or L["speculative"]
            out.append(f"- **[IA-{n}]** {idea.idea.strip()} — {idea.rationale.strip()} ({L['based']}: {basis})")
            for r in idea.based_on:
                if r not in cited_order:
                    cited_order.append(r)
            ia_refs.append(f"**[IA-{n}]** {L['ia_by']} ({synth_model}, {date.today().isoformat()}) — "
                           f"{L['based']}: {basis}")
        out.append("")

    if synthesis.gaps:
        out.append(f"### {L['gaps']}\n" + "\n".join(f"- {g}" for g in synthesis.gaps) + "\n")

    # Bibliography: only what was cited, grouped by source type, in order of first use
    groups: dict[str, list[str]] = {"note": [], "paper": [], "web": []}
    for ev_id in cited_order:
        ev = store.get(ev_id)
        if ev:
            groups[ev.kind].append(format_reference(ev, quotes.get(ev_id, []), lang))
    out.append(f"## {L['refs']}\n")
    for kind, title in (("note", L["notes"]), ("paper", L["papers"]), ("web", L["web"])):
        if groups[kind]:
            out.append(f"**{title}**\n" + "\n".join(f"- {r}" for r in groups[kind]) + "\n")
    if ia_refs:
        out.append(f"**{L['ideas']}**\n" + "\n".join(f"- {r}" for r in ia_refs) + "\n")

    foot = (f"{L['usage']}: {usage.input_tokens:,} in / {usage.output_tokens:,} out tokens · "
            f"~${usage.cost_usd:.4f} · {usage.llm_calls} LLM calls · {usage.tool_calls} tool calls")
    if removed_claims:
        foot += f" · {removed_claims} {L['pruned']}"
    if usage.stopped_reason:
        foot += f" · {L['stopped']}: {usage.stopped_reason}"
    out.append("---\n_" + foot + "_")
    return "\n".join(out)
