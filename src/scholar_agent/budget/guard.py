"""Per-query budget enforcement. Degrades gracefully: stop researching, still answer."""

from __future__ import annotations

from dataclasses import dataclass

from scholar_agent.budget.tracking import QueryTracker
from scholar_agent.config import BudgetSpec


@dataclass
class BudgetGuard:
    spec: BudgetSpec
    tracker: QueryTracker
    iterations: int = 0
    reason: str | None = None

    def next_iteration(self) -> int:
        self.iterations += 1
        return self.iterations

    def exhausted(self) -> str | None:
        """Return why research must stop, or None. Synthesis is always allowed to run."""
        if self.tracker.cost >= self.spec.max_cost_usd * 0.8:
            return f"cost reached 80% of the ${self.spec.max_cost_usd:.3f} limit"
        if self.tracker.input_tokens >= self.spec.max_input_tokens * 0.8:
            return "input-token budget nearly used"
        if self.tracker.tool_calls >= self.spec.max_tool_calls:
            return f"tool-call limit ({self.spec.max_tool_calls}) reached"
        if self.iterations >= self.spec.max_iterations:
            return f"iteration limit ({self.spec.max_iterations}) reached"
        return None

    def check_and_mark(self) -> bool:
        """True if research may continue; records the stop reason otherwise."""
        reason = self.exhausted()
        if reason and not self.reason:
            self.reason = reason
        return reason is None
