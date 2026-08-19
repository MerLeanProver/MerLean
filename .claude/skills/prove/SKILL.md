---
name: prove
description: Prove mode — fill the `sorry`/`admit` placeholders in an existing Lean file with real proofs, using the Mem0-g plan graph + compile-fix subagent. Run in the MAIN context. Use when asked to "prove the sorries", complete unfinished declarations, or formalize a stubbed Lean file. Success is mechanical: clean build with no residual sorry/admit/axiom.
---

# prove — decompose a sorry into a plan, then prove it node by node

The proof obligation already exists as a typed Lean declaration. **Do NOT hand the whole theorem
to one compile-fix.** First DECOMPOSE it into a proof-plan graph — helper lemmas + the main
theorem, each a tracked node = one file — then prove the nodes **one at a time in dependency
order**, each via a `compile-fix` **subagent**. You run in the **main context** and own the
decomposition (you are the update agent). Use the `plan-graph` skill for the CLI.

## Core principle — prove mode is RELENTLESS (never stop, never ask)
Prove mode **never halts at a difficulty and never asks the user how to proceed.** Every
`needs_update`/`failed` a compile-fix subagent returns is not a dead end — it is the trigger to
**grow the plan**: you (the update agent, main context) **decompose** the stuck node into helper
lemmas, or **rephrase** it, then continue the loop. The plan only grows toward provable leaves;
recurse on whatever is still too hard. The run ends in exactly one way: the **main theorem node
is `completed`** (§4). A genuine Mathlib gap is something to *decompose through*, not a reason to
stop — see §3b.

**NEVER ask the user a question — under any circumstance.** Do not pause for scope, cost,
feasibility, axiom policy, or "how should I proceed" decisions; do not call `AskUserQuestion`, do
not present options, do not wait for confirmation. The moment you finish §1's research, you commit
to the **full relentless formalization** and start proving — that decision is already made and is
not the user's to re-make. In particular:
- A **deep / foundational Mathlib gap** (a missing *major* theorem — e.g. Brouwer's fixed point
  theorem, Sperner's lemma, a missing representation/structure theorem) is **NOT special**: it is
  decomposed through exactly like any other gap, all the way down to the primitives Mathlib *does*
  have, no matter how many helper lemmas or levels that takes. "This is a famous hard theorem to
  formalize" and "this could be thousands of lines / may not converge in one session" are **not**
  reasons to stop or ask — they are the expected shape of the work. Keep growing the plan and
  proving leaves; partial progress across a session is fine.
- **No axioms, ever** (`AXIOM_POLICY=strict`). Do not offer to admit a missing theorem as an axiom
  and do not ask whether the user would accept one. The only finish line is a fully proved main
  theorem whose `#print axioms` shows just `[propext, Classical.choice, Quot.sound]` (§4).
- Do not narrow, weaken, or restrict the target statement to dodge a gap, and do not ask to. The
  main theorem's `anchor` is fixed; you reach it by building the missing machinery, not by
  shrinking the goal.

So when research reveals the proof needs a big missing theorem, the correct action is to **plan
its decomposition and begin** (§1/§3b) — silently and immediately — never to surface the gap as a
question.

## Inputs
- `FILE` — the target `.lean` file containing `sorry`/`admit` (inside a Lean workspace).
- `LIB_DIR` — the **Lean workspace root** where `lake build` runs (the lakefile dir).

The data folder is **derived from the file**: `<FILE.parent>/<FILE.stem>_data/`. Step 1 prints it
as `data_dir`; capture that as `<DATA_DIR>` and pass `--data <DATA_DIR>` to every later CLI call
and to the subagent. All graph/progress/analytics for this proof live in that folder.

## Progress reporting (stream it clearly)
Narrate each step on its own line so the user can follow live, using this exact shape:
```
▶ <id> (<type>)                  ← starting the obligation
   · <step in progress> …        ← one short line per step (seeding / compiling / verifying)
   ✓ <result>                    ← good outcome (e.g. "clean build", "0 residual sorry")
   ✗ <problem> → <action>        ← bad outcome + what you do next (escalate / retry)
```
Show the **dashboard** at the start and end, and after the subagent returns:
`.venv/bin/python src/cli.py --data <DATA_DIR> status` (the plan-graph CLI).
Finish with `analytics --plain` for the run summary (tokens / tool calls / time per subagent).
Keep these lines terse — the user wants the *current status*, not a transcript.

## Steps

`seed-sorries <FILE> --lib-dir <LIB_DIR>` first to fix `<DATA_DIR>` (it derives + prints it) and
record the original target signature as an `anchor`. Then **delete that single node** (or just
ignore it) and build the real plan in §1 — seed-sorries alone is NOT the plan.

### 1. Plan — decompose into a proof-plan graph (MAIN context = update agent)
`Read "<FILE>"`, study the target, and search Mathlib for the hard pieces with **`lean_leansearch`**
(the lean-lsp tools are available in this context too). Decide the **helper lemmas** the proof
needs (its natural sub-steps) plus the **main theorem**. For EACH (helpers first): **`search`
the plan for what it claims first** (`search "<the claim>"`, plan-graph CLI) — if a
matching node already exists, depend on it instead of duplicating; only if none matches do you
`add` a graph node:
```
… src/cli.py --data <DATA_DIR> add --json '{"id":"Lem_<Name>","type":"Lemma","name":"<Name>",
   "content":"<what it claims>","anchor":"<exact Lean signature>",
   "lean_path":"<dir>/<Name>.lean","dependencies":[<helper ids it uses>]}'
```
The **main theorem** node keeps the original `<FILE>` as its `lean_path` and depends on the
helpers (one node = one file; the main proof is filled LAST, using the proven helpers). Run
`cycles` (must be `[]`) and show the plan: `status`, then `visualize --lib-dir <LIB_DIR>` to render
`graph.png`. Then `summarize` to store the plan's searchable `Summary` node — and re-run both
whenever you re-plan. **Whenever the plan (`statements.json`) changes — every `add`/`update`/`delete`/
`set-status`/`sync-lean` — re-run `visualize` so the graph image stays current.**

### 2. Scaffold the files
For each helper node create `<lean_path>`: `import Mathlib`, the shared namespace/`open`, the
`import`s of its dependency helper modules, and the lemma signature with `:= by sorry`. Wire the
library root / lakefile so every module builds. Leave the main file's statement as `sorry` until
§3 reaches it.

### 3. Prove loop — dispatch compile-fix subagents in the BACKGROUND (≤ 4 in parallel), bank on each completion
Run the proof loop **asynchronously**. Dispatch each `compile-fix` as a **background** subagent
(`run_in_background: true`) and **never block** waiting for it — keep **≤ 4 compile-fix subagents
running concurrently** (the hard cap); queue the rest and dispatch as slots free. While subagents
prove files, the main context (you, the update agent) keeps making progress — scaffolding new
files, decomposing hard nodes (§3b), proving tractable glue, researching Mathlib. In this harness,
subagents may be placed in isolated git worktrees: for untracked Lean workspaces (common in
benchmark challenges), the subagent must copy `LIB_DIR` into its worktree, prove/build there, and
return a unified diff; the orchestrator applies that patch to the real checkout and runs the
authoritative build/reconcile. The run ends when the **main theorem node is `completed`** (§4).

**Bank immediately on every completion notification.** When a background subagent finishes, apply
its returned patch (if any), verify + bank (§3a) or decompose (§3b), `record` its metrics, and
dispatch whatever it unblocked — never let finished-but-unbanked work pile up; banked work is the
recoverability boundary if the session is interrupted.

**Signature-locked parallelism — the key rule.** A node's PROOF only needs its dependencies'
**signatures** (their scaffolded `anchor`s), NOT their completed proofs: `compile-fix` proves one
file against the *types* of the lemmas it imports, and those types exist the moment the dependency
files are scaffolded (§2). So **any node whose dependency files are scaffolded can be dispatched
immediately** — including "glue"/assembly nodes, even the **main theorem**, *before* their leaves
are proven. This breaks the strict level barrier: you do NOT have to finish a level before starting
the next. A glue node proven against still-`sorry` dependencies builds clean in ITS OWN file (the
`sorry` lives in the dependency's file, not the glue's), and a clean glue proof **validates the
dependency interfaces** early — if a signature is wrong, the subagent reports it before you sink
effort into the leaf. The global soundness gate is the final `#print axioms` check (§4), which
catches any leaf left unfilled.

Each round:
- `levels` / `status` (plan-graph CLI) to see what is scaffolded vs `pending`.
- Pick `pending` nodes whose **dependency files are scaffolded** (signatures locked — they need
  NOT be `completed`). For each: `set-status <id> in_progress`, then dispatch a **background**
  `compile-fix` (`run_in_background: true`) with `FILE=<node.lean_path>, STATEMENT_ID=<id>,
  DATA_DIR, LIB_DIR, AXIOM_POLICY=strict`, and explicitly tell it: if isolated outside `LIB_DIR`,
  copy `LIB_DIR` into its worktree, prove/build the copy, and return a unified diff. It proves
  **only its own file**. Dispatch independent ready nodes together (parallel Task calls in one
  message), but keep **≤ 4 running concurrently** (the hard cap) and **never two that could touch
  the same file**; queue the rest and dispatch as slots free.
- **Do not idle while subagents run.** Use the main context for *non-overlapping* work: scaffold
  the next files, decompose a known-hard node (§3b), prove easy glue yourself, or research
  Mathlib. **NEVER edit a file a running subagent owns.**
- On each completion notification: apply any returned patch to the real checkout, then `clean` →
  §3a (verify + bank: `sync-lean` + `reconcile`). `needs_update`/`failed` → **§3b (decompose or
  rephrase, then continue — never stop, never ask the user)**, using the subagent's suggested
  split. Never admit an axiom under strict. `record <id> --role compile-fix --json
  '{tokens,tool_uses,duration_ms}'` per node. Then dispatch the newly-ready nodes.
Repeat until no `pending`/`in_progress` nodes remain and the main theorem is `completed`.

#### 3a. Verify + commit the node (mechanical — no faithfulness check in prove mode)
- clean build: `cd <LIB_DIR> && lake build <Module>` → 0 errors, 0 warnings;
- no residual `sorry`/`admit`/`axiom` in the node's file (`Grep`);
- `sync-lean <LIB_DIR>` (edges/decls), then **`reconcile <LIB_DIR>`** — re-derives status from the
  files (the now-`sorry`-free node becomes `completed`) and self-heals any drifted statuses.
  **Prefer `reconcile` over a bare `set-status <id> completed`**: the Mem0-g store can silently
  revert a written status (a later full-node write, even `sync-lean`, locks the stale value in).
  Then **verify it stuck** (`get <id>` reads `completed`) and `visualize`. Show `status`. Back to the loop.

#### 3b. On difficulty: decompose or rephrase, then CONTINUE (the update agent — never stop)
A `needs_update`/`failed` is the signal to **grow the plan**, not to halt. compile-fix escalates a
hard/complex node **early** (rather than sinking time into a giant single file) and usually returns
a proposed `decomposition:` — splitting clusters into small leaf nodes keeps each proof tractable
AND lets the loop (§3) prove the pieces **in parallel** (≤ 4 running at a time). You
handle it in the main context and keep the loop running — you never stop to ask the user. Once the
new leaves are scaffolded, the stuck parent (glue) can itself be re-dispatched immediately against
their signatures (signature-locked parallelism), without waiting for the leaves to be proved. Pick
one:
- **Decompose** (default): split the stuck node into the helper lemmas its proof needs — **prefer
  the compile-fix subagent's proposed `decomposition:`** (each helper already comes with a clean
  signature, its deps, and a filename). **`search` the plan for each proposed helper first** — reuse an
  existing node if one matches; otherwise `add` it as a new
  node, make the stuck node depend on them, scaffold the new files (§2), set the stuck node back
  to `pending`, run `cycles`/`sync-lean`/`summarize`/`visualize`, then re-run `levels` and continue — the new
  leaves become the next level. **Recurse:** a helper that is itself too hard gets decomposed
  again. A real Mathlib gap (e.g. a missing representation theorem) is decomposed down to the
  pieces Mathlib *does* have and rebuilt from them.
- **Rephrase**: if the node is already atomic and cannot be usefully split, restate it with better
  Mathlib types or a different but equivalent formulation Mathlib can reach, then retry. The
  `anchor` of the *original target* (the main theorem) is fixed; helper anchors you introduced may
  be rephrased freely.
**Make progress every round** — never re-dispatch an identical failed attempt. Vary the strategy:
a different decomposition, different Mathlib lemmas, a weaker intermediate. If a split does not
reduce difficulty (the helper just restates its parent), rephrase instead. The plan grows only
toward provable leaves; the loop runs until the main theorem node is `completed`.
**Bank durable conclusions as informal Notes** (plan-graph skill, "Informal notes"): an approach
proven dead, a helper found false (with the counterexample), a decisive Mathlib gap. `search`'s
`informal` group then warns every later round — and the retry rule above has memory across
sessions. Before choosing a strategy, check that group for prior dead ends on this node.

### 4. Done
When the **main theorem** node is `completed`, run the whole-proof checks:
- **Soundness gate:** `#print axioms <Main full name>` (or `lean_verify`) must show only
  `[propext, Classical.choice, Quot.sound]` — no `sorryAx`, no added axioms.
- **No duplicate declarations:** after a final `sync-lean`, run `… src/cli.py --data <DATA_DIR> lint`;
  it must report `"n": 0`. Two nodes defining the same top-level name is a latent clash (the name
  is ambiguous in any file importing both, and a proof can silently bind the wrong one); if `lint`
  flags one, rename/relocate the duplicate, rebuild, and re-lint.
Show the final `status` + `analytics --plain`, and report the helper lemmas, the tactics used, and
zero residual placeholders.

## Notes
- The plan graph IS the proof plan: helpers are nodes, edges are which lemma uses which; each
  node is one file, proved independently in dependency order — never the whole theorem at once.
- Signatures/anchors are preserved; compile-fix fills proof bodies only.
- If a helper turns out to be the wrong shape, re-plan it (§1) — that is the update agent at work.
