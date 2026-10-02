"""Command line interface: research ingest | ask | search | usage | doctor | eval."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from scholar_agent.config import Mode, load_settings

app = typer.Typer(
    help="Research agent over your personal notes and the scientific literature.",
    no_args_is_help=True, add_completion=False,
)
console = Console()

ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c", help="YAML overriding config/default.yaml")]


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def _main() -> None:
    _utf8()


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="Folder with .md / .txt notes (e.g. an Obsidian vault)")],
    source: Annotated[str | None, typer.Option(help="Name for this collection (default: folder name)")] = None,
    rebuild: Annotated[bool, typer.Option(help="Drop the index and re-embed everything")] = False,
    config: ConfigOpt = None,
) -> None:
    """Index a folder of notes. Incremental: unchanged files are skipped."""
    from scholar_agent.ingestion.pipeline import ingest as run_ingest
    from scholar_agent.services import build_services

    settings = load_settings(config)
    if not path.is_dir():
        raise typer.BadParameter(f"Not a directory: {path}")
    svc = build_services(settings, with_reranker=False)
    try:
        with console.status("Indexing notes...") as status:
            report = run_ingest(
                path, source or path.resolve().name, svc.embedder, svc.store, svc.catalog,
                settings.chunking.max_tokens, settings.chunking.min_tokens, rebuild,
                progress=lambda i, n, name: status.update(f"Indexing {i}/{n}: {name[:50]}"),
            )
    finally:
        svc.close()
    table = Table("scanned", "added", "updated", "unchanged", "removed", "chunks", "errors", "seconds")
    table.add_row(*(str(x) for x in (report.scanned, report.added, report.updated, report.unchanged,
                                     report.removed, report.chunks, len(report.errors),
                                     f"{report.seconds:.1f}")))
    console.print(table)
    for err in report.errors[:10]:
        console.print(f"[yellow]skipped:[/yellow] {err}")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Your question, or an idea you want checked")],
    mode: Annotated[Mode, typer.Option("--mode", "-m", help="notes | literature | hybrid")] = "hybrid",
    budget: Annotated[float | None, typer.Option(help="Max USD for this query (overrides config)")] = None,
    save: Annotated[bool, typer.Option(help="Save the answer as an Obsidian SIN note")] = False,
    save_dir: Annotated[Path | None, typer.Option(help="Where to save (default: <index>/answers)")] = None,
    show_evidence: Annotated[bool, typer.Option(help="Also list everything collected, not only what was cited")] = False,
    intent: Annotated[str | None, typer.Option(help="Force: question | verify_idea | lookup (default: auto)")] = None,
    config: ConfigOpt = None,
) -> None:
    """Answer a question or check an idea, with every statement referenced."""
    from scholar_agent.agent.runner import IndexMissingError, ResearchAgent
    from scholar_agent.config import PrivacyError
    from scholar_agent.llm.factory import MissingKeyError

    settings = load_settings(config)
    try:
        agent = ResearchAgent(settings)
        with console.status("Thinking...") as status:
            result = agent.ask(question, mode, budget, intent=intent,
                               progress=lambda m: status.update(f"[bold]{m}[/bold]..."))
    except (PrivacyError, MissingKeyError, IndexMissingError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        if "agent" in locals():
            agent.close()
    console.print(Markdown(result.markdown))
    if show_evidence:
        console.print("\n[bold]Collected evidence[/bold]")
        for ev in result.evidence:
            mark = "*" if ev.id in result.cited_ids else " "
            console.print(f" {mark} {ev.header()}", highlight=False)
    if save:
        out_dir = save_dir or (settings.index_dir / "answers")
        out_dir.mkdir(parents=True, exist_ok=True)
        name = re.sub(r'[\\/:*?"<>|\[\]#^]', "", question).strip()[:80]
        target = out_dir / f"SIN — {name}.md"
        target.write_text(result.to_vault_note(), encoding="utf-8")
        console.print(f"\n[green]Saved:[/green] {target}")


@app.command()
def search(
    query: Annotated[str, typer.Argument()],
    k: Annotated[int, typer.Option("-k")] = 8,
    method: Annotated[str, typer.Option(help="dense | sparse | hybrid")] = "hybrid",
    rerank: Annotated[bool, typer.Option(help="Use the cross-encoder if configured")] = True,
    config: ConfigOpt = None,
) -> None:
    """Retrieval only (zero LLM tokens): see what the agent would find in your notes."""
    from scholar_agent.retrieval.hybrid import NoteRetriever
    from scholar_agent.services import build_services

    svc = build_services(load_settings(config))
    try:
        hits = NoteRetriever(svc).search(query, k=k, mode=method, rerank=rerank)
    finally:
        svc.close()
    table = Table("#", "score", "note", "section", "lines", "via")
    for i, h in enumerate(hits, 1):
        table.add_row(str(i), f"{h.score:.3f}", h.title[:48], h.heading[:30],
                      f"{h.line_start}-{h.line_end}", h.via if h.via == "search" else f"graph: {h.relation}")
    console.print(table)


@app.command()
def usage(
    days: Annotated[float, typer.Option(help="Look-back window")] = 30,
    config: ConfigOpt = None,
) -> None:
    """Token and cost report from the persistent ledger."""
    from scholar_agent.budget.tracking import Ledger

    settings = load_settings(config)
    ledger = Ledger(settings.index_dir / "usage.sqlite")
    rows = ledger.summary(days)
    table = Table("model", "role", "calls", "input tok", "output tok", "USD")
    for r in rows:
        table.add_row(r["model"], r["role"], str(r["calls"]), f"{r['input']:,}", f"{r['output']:,}", f"{r['usd']:.4f}")
    console.print(table)
    total = sum(r["usd"] for r in rows)
    console.print(f"{ledger.queries(days)} queries · total ${total:.4f} in the last {days:g} days")


@app.command()
def doctor(config: ConfigOpt = None) -> None:
    """Diagnose messy notes: empty, duplicated, orphaned notes and broken wikilinks (no LLM)."""
    from scholar_agent.services import build_services

    svc = build_services(load_settings(config), with_reranker=False)
    try:
        stats, issues = svc.catalog.stats(), svc.catalog.doctor()
    finally:
        svc.close()
    console.print(f"[bold]{stats['notes']}[/bold] notes · {stats['chunks']} chunks · {stats['links']} links")
    console.print(f"by type: {stats['by_kind']} · by language: {stats['by_lang']}")
    for name, items in issues.items():
        console.print(f"\n[bold]{name.replace('_', ' ')}[/bold]: {len(items)}")
        for item in items[:8]:
            console.print(f"  - {item}", highlight=False)


@app.command(name="eval")
def evaluate(
    suite: Annotated[str, typer.Argument(
        help="retrieval | retrieval-es | verification | pubmedqa | vault | references")],
    limit: Annotated[int | None, typer.Option(help="Use only N examples (cheap smoke runs)")] = None,
    judge: Annotated[bool, typer.Option(help="Add LLM-judge faithfulness/relevance scores (extra cost)")] = False,
    cache: Annotated[bool, typer.Option(help="Cache LLM responses so re-runs are free")] = True,
    offline: Annotated[bool, typer.Option(help="Skip items that need live literature/web APIs")] = False,
    config: ConfigOpt = None,
) -> None:
    """Run an evaluation suite and write a report to eval/reports/."""
    from scholar_agent.config import PrivacyError
    from scholar_agent.evaluation.runner import run_suite
    from scholar_agent.llm.factory import MissingKeyError

    try:
        run_suite(suite, load_settings(config), limit, console, judge=judge, cache=cache, offline=offline)
    except (PrivacyError, MissingKeyError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
