# Token control and efficiency

## Measuring

* Every chat completion reports `usage_metadata`; a LangChain callback (`budget/tracking.py`) attributes it to
  a **role** (router, agent, synthesizer, judge) and a model, converts it to USD with `config/pricing.yaml`
  and appends it to a SQLite ledger.
* Each answer ends with a footer: input/output tokens, estimated USD, LLM calls, tool calls, and whether research
  was cut short by the budget. `research usage --days 30` aggregates by model and role.

## Limiting

`config/default.yaml → budget` (overridable per query with `--budget`):

| Limit | Effect when reached |
|---|---|
| `max_cost_usd` | At 80 % research stops; the synthesizer still runs on the evidence already collected |
| `max_input_tokens` | same |
| `max_tool_calls` / `max_iterations` | tools answer "TOOL BUDGET EXHAUSTED", the loop moves to synthesis |
| `evidence_tokens_each` / `evidence_tokens_total` | each evidence item is truncated; total context handed to the synthesizer is capped |

The system degrades gracefully: it never fails for lack of budget, it answers with less evidence and says so.

## Saving

1. **Role routing**: a small model plans; only the final synthesis uses the stronger model.
2. **Seed retrieval without an LLM**: notes and papers are searched in parallel before the agent starts, so most questions need 0–2 tool calls.
3. **Compact tool outputs**: one line per hit with a ~60–90-token snippet; full text enters the evidence store, not the agent's context.
4. **Context packing**: deep-read items first, then by rank, interleaving note/paper/web so one source type cannot flood the prompt.
5. **No LLM where code suffices**: citation verification, DOI checks, de-duplication, ledger and diagnostics are deterministic.
6. **No evidence → no synthesis call.**
7. **Caches**: HTTP responses (7 days) and, in evaluations, LLM responses.
8. **One repair pass at most** for failed citations, and only if cost is below 90 % of the budget.

The evaluation reports tokens and USD per answer next to every quality metric, so any change (chunk size,
`top_k`, a cheaper synthesizer) can be judged on the quality/cost trade-off instead of on quality alone.
