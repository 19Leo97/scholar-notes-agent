"""Token accounting: pricing, per-query tracker (LangChain callback) and persistent ledger."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from scholar_agent.config import Settings


def cost_usd(settings: Settings, model: str, input_tokens: int, output_tokens: int) -> float:
    price = settings.pricing.get(model)
    if not price:
        return 0.0  # local / unknown models: tokens are still counted
    return (input_tokens * price.get("input", 0.0) + output_tokens * price.get("output", 0.0)) / 1e6


@dataclass
class Usage:
    role: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class QueryTracker:
    """Accumulates usage for one agent run. Thread-safe (tools may run in parallel)."""

    settings: Settings
    query_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    records: list[Usage] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, role: str, model: str, input_tokens: int, output_tokens: int) -> Usage:
        usage = Usage(role, model, input_tokens, output_tokens,
                      cost_usd(self.settings, model, input_tokens, output_tokens))
        with self._lock:
            self.records.append(usage)
            self.llm_calls += 1
        return usage

    def count_tool_call(self) -> int:
        with self._lock:
            self.tool_calls += 1
            return self.tool_calls

    @property
    def input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    @property
    def cost(self) -> float:
        return sum(r.cost_usd for r in self.records)

    def by_role(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in self.records:
            row = out.setdefault(r.role, {"model": r.model, "calls": 0, "in": 0, "out": 0, "usd": 0.0})
            row["calls"] += 1
            row["in"] += r.input_tokens
            row["out"] += r.output_tokens
            row["usd"] += r.cost_usd
        return out


class UsageCallback(BaseCallbackHandler):
    """Reads usage_metadata from every chat completion and reports it to the tracker."""

    def __init__(self, tracker: QueryTracker):
        self.tracker = tracker
        self._meta: dict[Any, dict] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        self._meta[run_id] = metadata or {}

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):
        self._meta.setdefault(run_id, metadata or {})

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs):
        meta = self._meta.pop(run_id, {})
        in_tok = out_tok = 0
        for gens in response.generations:
            for gen in gens:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if usage:
                    in_tok += int(usage.get("input_tokens", 0))
                    out_tok += int(usage.get("output_tokens", 0))
        if not (in_tok or out_tok):
            raw = (response.llm_output or {}).get("token_usage") or {}
            in_tok = int(raw.get("prompt_tokens", 0))
            out_tok = int(raw.get("completion_tokens", 0))
        self.tracker.add(meta.get("role", "unknown"), meta.get("model", "unknown"), in_tok, out_tok)


class Ledger:
    """Persistent usage log (SQLite) so spend can be audited across sessions."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS usage (ts REAL, query_id TEXT, question TEXT, role TEXT, "
            "model TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)"
        )

    def record(self, tracker: QueryTracker, question: str) -> None:
        rows = [
            (time.time(), tracker.query_id, question[:200], r.role, r.model,
             r.input_tokens, r.output_tokens, r.cost_usd)
            for r in tracker.records
        ]
        self._db.executemany("INSERT INTO usage VALUES (?,?,?,?,?,?,?,?)", rows)
        self._db.commit()

    def summary(self, days: float = 30.0) -> list[dict]:
        since = time.time() - days * 86400
        cur = self._db.execute(
            "SELECT model, role, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd) "
            "FROM usage WHERE ts >= ? GROUP BY model, role ORDER BY SUM(cost_usd) DESC",
            (since,),
        )
        return [
            {"model": m, "role": r, "calls": n, "input": i or 0, "output": o or 0, "usd": c or 0.0}
            for m, r, n, i, o, c in cur.fetchall()
        ]

    def queries(self, days: float = 30.0) -> int:
        since = time.time() - days * 86400
        return self._db.execute(
            "SELECT COUNT(DISTINCT query_id) FROM usage WHERE ts >= ?", (since,)
        ).fetchone()[0]
