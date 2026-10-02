# eval/

Evaluation code lives in `src/scholar_agent/evaluation/` (so it ships with the package and the CLI);
this folder only holds **results**:

* `reports/latest-<suite>.md`: most recent table per suite (embedded in the main README).
* `reports/<suite>-<timestamp>.json`: full run record (config fingerprint, prompt hash, per-item records).
* `private/` (git-ignored): put evaluations on your own notes here.

Run `research eval --help` and see `docs/evaluation.md`.
