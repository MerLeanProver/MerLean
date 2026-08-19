# The paper-writing agent

The MerLean **paper-writing agent** turns a finished research campaign — its dependency
graph, certificates, and ledger — into a publishable mathematics paper, through a gated
8-step protocol:

1. **Critical path** — the theorem-grade DAG and the deepest chains to the strongest results.
2. **Empty framework** — the compilable section skeleton.
3. **Main-result selection** — 2–4 results forming one through-line, each passing a fresh
   arXiv novelty sweep (verdicts CLEAR / ADJACENT / COLLISION, evidence from source TeX).
4. **Supporting-lemma selection** — only what a reader needs; definition census derived.
5. **Draft** — definitions once and just-in-time; textbook steps cited, never re-proved;
   long proofs to the appendix with two-way references; the locked-bib reference standard
   (arXiv TeX downloaded, read, and verified before any commitment to cite).
   **5½. Shrink** — delete boring steps (preserved in a ledger), move boring-but-important
   proofs to the appendix; statements must stay byte-identical.
6. **Abstract last** + outlook, under the summary-layer rule (a restatement is always
   weaker-or-equal to the precise statement).
7. **Terminology standardization** — one field-standard term per concept, notation
   collision audit.
8. **Done** — all gates green, artifacts committed.

Every step produces a named artifact and is gated: a step's exit checklist must pass
before the next opens.

## Versions

| Runtime | Where | Notes |
|---|---|---|
| **Claude Code** | [`claude/AGENT.md`](claude/AGENT.md) | The canonical protocol, executed in the main context with subordinate scout/verifier/drafting dispatches. Invoked via the `/write-paper` skill in the root [`.claude/`](../.claude). |
| **Codex** | [`codex/`](codex) | Standalone Codex plugin: the same gated protocol plus a non-destructive **refine mode** for existing papers (`-vN` versioning, hash-locked baselines, main-result locks, coverage ledgers), deterministic safeguards via `codex/scripts/paperctl`, and a read-only `paper-audit` skill. See [`codex/README.md`](codex/README.md). |
| *(future)* | `opencode/`, … | Same pattern: one folder per runtime, same gates, same artifacts. |

A complete worked run on a small example lives in
[`../examples/`](../examples) (see the linear-algebra demo campaign's `paper/` folder).
