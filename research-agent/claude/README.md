# Research agent — Claude Code version

This version **lives at the repository root**, not here:

- [`../../.claude/`](../../.claude) — skills (`lite-research`, `auto-research`,
  `formalize`, `prove`, `formalizeproblem`, `plan-graph`, `init_merlean`,
  `write-paper`) and subagent roles (`compile-fix`, `explore`, `route-scout`,
  `nl-prover`, `skeptic`).
- [`../../src/`](../../src) — the shared plan-graph engine (`plan_store`) and its CLI.

It is kept at the root deliberately, so the repository is **install-ready as checked
out**: clone, start `claude`, run `/init_merlean`, and the agent is live. This folder
exists only so the version matrix is visible in one place next to
[`../codex/`](../codex).
