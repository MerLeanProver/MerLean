---
name: formalize
description: Orchestrate formalizing a paper (or filling sorries) into verified Lean 4, using the Mem0-g plan graph as the statement store. Run this in the MAIN context. It dispatches compile-fix as a SUBAGENT (separate context) and performs plan edits (the update agent) plus all faithfulness/paper checks IN the main context. Use when asked to formalize a paper, build a Lean library from a plan, or drive the statement plan to completion.
---

# formalize — main-context orchestrator

You are the orchestrator. You drive the per-statement loop in the **main context** and keep
it small by delegating heavy work to subagents that return only short summaries. Use the
`plan-graph` skill for every plan read/write. The **lean-lsp** tools are available throughout
(`lean_leansearch` for Mathlib search when planning; `lean_diagnostic_messages` for a quick
check); `lake build` remains the authoritative final verification.

## Context discipline (required)
- **Subagents (separate context — you only see their summary):** `compile-fix`. Launch it with
  the Task tool. Never inline its work.
- **Main context (you do it directly):** everything else — the **update agent** (all edits to
  the plan graph: cold-start extraction, corrections, rephrase/decompose), the **checks** (§4),
  the escalation decisions (§3 `failed`), and the plan-edit review (§6). You read the
  paper/issues and call the `plan_store` CLI yourself; you do NOT spawn subagents for these.

## Inputs
- `DATA_DIR` — the plan data folder (`<file>_data` / `<lib>/datas`, next to the target). All
  plan state (graph, statements.json, progress.json, analytics.json) lives here. Pass it to
  every CLI call and every subagent.
- `LIB_DIR` — the writable Lean+Mathlib workspace dir where `.lean` files are built
  (`lake build` runs there). (Phase 3 sets this up; required before any compile-fix.)
- `LEAN_LIB` — the Lean library namespace for imports (e.g. `Torusdemo`).

## Progress reporting (stream it clearly)
The user wants to follow progress live and see the current status. Narrate each step on its own
line, using this exact shape:
```
▶ [<i>/<N>] <id> (<type>)         ← starting a statement (i of N in topo order)
   · <step in progress> …         ← one short line per step (scaffold / compile-fix / check / sync)
   ✓ <result>                     ← good outcome (clean build, FAITHFULNESS: PASS, completed)
   ✗ <problem> → <action>         ← bad outcome + what you do next (escalate / retry / update plan)
```
Show the **dashboard** at the start, after every statement, and at the end:
`.venv/bin/python src/cli.py --data <DATA_DIR> status` (the plan-graph CLI).
At the end also run `analytics --plain` for the per-statement token/time summary. Keep the lines
terse (current status, not a transcript); the subagents' full work stays in their own context.
- `PAPER` — path to the paper `.tex`/`.pdf` (omit for prove-mode / plan already built).
- `AXIOM_POLICY` — `strict` (default: no axioms, no sorry) or `selective`.

## 0. Ensure a plan exists (update agent, main context)
`.venv/bin/python src/cli.py --data <DATA_DIR> list`. If empty and a PAPER is given,
**build the plan yourself** (INIT): read the paper, extract its result path as a
dependency-ordered set of statements (Definitions → Lemmas → Theorems), and `add` each node
(`id` `Prefix_Name`, `type`, `name`, `content`, `proof` sketch, `dependencies`) — **`search`
each before adding** (`search "<the claim>"`, plan-graph CLI) to reuse an existing node
rather than duplicating. Then run
`cycles` (must be `[]`), then `summarize` to store the plan's `Summary` node, then `visualize` to
render `graph.png`. If you already have a `statements.json`, `import-json` it instead.
**Whenever the plan (`statements.json`) changes — any `add`/`update`/`delete`/`set-status`/`sync-lean`
— re-run `visualize` so the graph image stays in sync.**

## 1. Schedule — dispatch compile-fix subagents in the BACKGROUND (≤ 4 in parallel), bank on each completion
Run the schedule **asynchronously**. Dispatch each `compile-fix` as a **background** subagent
(`run_in_background: true`) and **never block** waiting for it — keep **≤ 4 compile-fix subagents
running concurrently** (the hard cap); queue the rest and dispatch as slots free. While subagents
formalize files, the main context (you, the update agent) keeps working — scaffolding more files,
editing the plan, dispatching more work. In this harness, subagents may be placed in isolated git
worktrees: for untracked Lean workspaces, the subagent must copy `LIB_DIR` into its worktree,
prove/build there, and return a unified diff; the orchestrator applies that patch to the real
checkout and then runs the authoritative build/reconcile.

**Bank immediately on every completion notification.** When a background subagent finishes, apply
its returned patch (if any), run its checks (§4) and commit (§4a), `record` its metrics, and
dispatch the newly-ready statements — never let finished-but-unbanked work pile up; banked work is
the recoverability boundary if the session is interrupted.

**Signature-locked parallelism — the key rule.** A statement's proof only needs its dependencies'
**signatures** (their scaffolded declarations), NOT their completed proofs: `compile-fix` proves one
file against the *types* it imports, and those types exist the moment the dependency files are
scaffolded (§2). So **scaffold files early and dispatch any statement whose dependency files are
scaffolded** — including downstream / "glue" statements *before* their dependencies are proved. You
do NOT have to finish a level before starting the next. A file proven against still-unfilled
dependencies builds clean in ITS OWN file (the gap lives in the dependency's file), and proving a
downstream statement early **validates the dependency interfaces**. The global soundness gate is
§5's whole-library check, which catches any statement left unproved.

Each round:
- `levels` / `status` (plan-graph CLI) to see what is scaffolded vs `pending`.
- Pick `pending` statements whose **dependency files are scaffolded** (signatures locked — they
  need NOT be `completed`/`completed_axiom`). Scaffold each (§2), `set-status <id> in_progress`,
  and dispatch a **background** `compile-fix` (`run_in_background: true`) — §3 per statement. Tell
  it explicitly: if isolated outside `LIB_DIR`, copy `LIB_DIR` into its worktree, prove/build the
  copy, and return a unified diff. Dispatch independent ready statements together (parallel Task
  calls in one message), but keep **≤ 4 running concurrently** and **never two that could touch
  the same file**; queue the rest and dispatch as slots free.
- **Do not idle while subagents run.** Use the main context for *non-overlapping* work: scaffold
  the next files, edit/grow the plan, research Mathlib. **NEVER edit a file a running subagent
  owns.**
- On each completion notification: apply any returned patch to the real checkout, then §4
  (faithfulness checks, main context) → §4a (commit) and `record` its
  metrics. Route any `needs_update`/`failed` per §3 for that one
  statement, then dispatch the newly-ready statements.
- Repeat until no `pending`/`in_progress` remain, then go to §5.

## 2. Scaffold the file (per statement, before its compile-fix)
Resolve the target path from the node's `lean_path`/`name` (see plan-graph). Create a minimal
`.lean`: `import Mathlib`, `import <LEAN_LIB>.<each dependency's module>`, and the statement as a
declaration with the proof to be filled. Keep it small — compile-fix writes the real proof.

## 3. Compile-fix (subagent — one per statement; background, up to 4 in parallel per §1)
Task → `compile-fix` with `FILE, STATEMENT_ID=<id>, DATA_DIR, LIB_DIR, AXIOM_POLICY`. Read its summary
(then `record <id> --role compile-fix --json '{tokens,tool_uses,duration_ms}'` from its usage):
- `clean` → go to §4.
- `needs_update` → go to §6 (update agent in main context) with its `escalation`.
- `infra_failure` → stop and report; the workspace needs repair.
- `failed` → decide the escalation yourself (main context): search Mathlib hard for the blocking
  fact (`lean_leansearch`, else `Grep ".lake/packages/mathlib"`) and `search` the plan for a node
  that already provides (or should own) it — check the `informal` group too: a banked note may
  already say this approach is dead or name the working route. Then pick: `RETRY` (re-run
  compile-fix with the named lemma), `DECOMPOSE` (→ §6 rephrase into tracked helpers), or
  `AXIOM` (only if `AXIOM_POLICY=selective`; a genuinely external, well-cited result — re-run
  compile-fix allowing that one cited axiom, then continue).

## 4. Check (main context)
Check faithfulness yourself (always): pull the statement (`get <id>`), `Read` the built `.lean`,
and verify the declaration **proves the original claim** — exact or strictly stronger, no
narrowed quantifiers/hypotheses, no placeholder/trivialized definitions, no disguised axioms;
`#print axioms` must match `AXIOM_POLICY`. If `PAPER` is set, also cross-check against the
paper passage (axioms-in-disguise, disconnected specs, weakened claims, undocumented deviations).
- Both pass → §4a.
- FAIL on a placeholder / strength / wrapper issue → re-run §3 compile-fix, passing the
  ISSUES so it fixes the proof. (Cap at a few rounds.)
- FAIL because it needs better upstream types → work out (main context) which upstream
  definitions should use better Mathlib types to unblock it, then go to §6 with those updates.

### 4a. Commit the statement
`sync-lean <LIB_DIR>` (reconcile this node's edges to the real Lean), then **`reconcile <LIB_DIR>`**
(re-derive status from the `.lean` files — self-healing; a `sorry`-free node becomes `completed`,
an `axiom` one `completed_axiom`). **Prefer `reconcile` over a bare `set-status <id> completed`**,
which the Mem0-g store can silently revert. Go to §1.

## 5. Done
All statements `completed`. Optionally `export-json --out` for a `statements.json` view, and
report: counts of clean / axiom / failed, and any open escalations.

## 6. Update agent — edit the plan (MAIN context, then self-review)
You perform the edit directly (do not spawn a subagent for it):
1. Read the trigger context (the compile-fix `escalation`, check ISSUES, or alignment updates)
   and the relevant paper passage.
2. Edit the plan via `plan_store`: `update`/`add`/`delete` statements — fix a `content`
   (correction), or split a stuck statement into tracked helper lemmas with proper
   `dependencies` (rephrase/decompose). **Before `add`-ing any helper, `search` the plan for it** and
   reuse a matching node instead of duplicating. Keep ids `Prefix_Name`; never introduce a cycle.
   **Bank the *why* as an informal Note** (plan-graph skill, "Informal notes") when the trigger
   revealed a durable conclusion — an approach proven dead, a lemma false with counterexample,
   a measured threshold, an `explore` answer — so later rounds and subagents surface it in
   `search`. If a kernel-checked result contradicts an existing note (e.g. compile-fix reports
   it), correct or delete the note — the formal result always wins.
3. Review the edit before accepting it: `cycles` must be `[]` and every `dependencies` id must
   exist; the diff must actually address the trigger; no statement's `content` may be silently
   weakened (dropped conjunct, weaker bound, one-direction iff) beyond what the trigger
   justifies. If the edit fails review, fix it and re-check; if it cannot be made to pass,
   stop and surface it.
4. On pass: invalidate the downstream cone — `cone <changed ids>`, then for each id in the
   cone set `status pending` and delete its `.lean` file. Run `cycles` (`[]`), `sync-lean`,
   `summarize` (the plan changed — refresh the `Summary` node), and `visualize` (refresh `graph.png`).
5. Return to §1 (the loop re-picks from the now-updated, re-ordered plan).

## Notes
- Every plan mutation is followed by `sync-lean` so the stored graph stays equal to the real
  Lean dependency graph.
- Keep the main context lean: rely on subagent summaries; pull plan detail with `get`/`list`
  on demand rather than holding it all in context.
