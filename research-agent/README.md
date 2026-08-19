# The research agent

The MerLean **research agent** takes mathematics in — a paper, a stubbed `sorry`, or an
informal open question — and drives it to a resolved, machine-checked (or
machine-screened) result. It has two verification budgets:

- **Full formalization** (`auto-research`, with `formalize` / `prove` /
  `formalizeproblem` as entry points): every step kernel-checked in Lean 4 + Mathlib,
  sorry-free and axiom-clean, over a route portfolio raced in parallel.
- **Lite mode** (`lite-research`): natural-language proof first — parallel
  representation-hunting routes, a graded step ledger under adversarial skeptic debate
  and Python experiments, with Lean fired **only at the triaged weakest links**
  (hypothesis-mode certificates). Grades BRONZE / SILVER / GOLD.

## Versions

| Runtime | Where | Notes |
|---|---|---|
| **Claude Code** | the repository root's [`.claude/`](../.claude) | The canonical version. It lives at the root — not in this folder — so the repo is install-ready as checked out: clone, run `claude`, run `/init_merlean`. Skills in `.claude/skills/`, subagent roles in `.claude/agents/`, shared plan-graph engine in [`src/`](../src). |
| **Codex** | [`codex/`](codex) | Standalone Codex-native port: same modes and roles as Codex skills (`SKILL.md` + `agents/openai.yaml`), its own copy of the plan-graph engine with an additional deterministic offline mode (`PLAN_OFFLINE=1`), CLI at `codex/scripts/merlean`. See [`codex/README.md`](codex/README.md). |
| *(future)* | `opencode/`, … | Ports to other agent runtimes follow the same pattern: one folder per runtime, same modes, same plan-graph contract. |

## The pieces, whichever runtime you use

- **Modes**: `init-merlean` (setup), `formalize`, `prove`, `auto-research`,
  `formalizeproblem`, `lite-research`, `plan-graph`.
- **Roles** (subagents in Claude Code; inline/child skills in Codex): `compile-fix`
  (one Lean file to a clean build), `explore` (evidence-backed world research),
  `route-scout` / `nl-prover` / `skeptic` (the lite-mode debate trio).
- **Memory**: the Mem0-g plan graph — formal statement nodes + informal research notes,
  semantic search, `sync-lean` keeping edges equal to the real Lean dependency graph.

Worked campaign records live in [`../examples/`](../examples).
