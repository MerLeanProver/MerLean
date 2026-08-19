---
name: auto-research
description: Auto-research mode — take an OPEN QUESTION in informal natural language and resolve it end-to-end in Lean 4, SELF-CONTAINED — formalize it into a faithful statement `:= by sorry`, then RELENTLESSLY prove or disprove it. FULLY AUTONOMOUS (never asks the user; ambiguous formalizations decided by canonical reading, loudly documented and banked), no axioms ever, direction pivots only on independently verified counter-evidence. Races a PORTFOLIO of 2–3 genuinely different routes in parallel (a disproof route included when direction is uncertain), killing and replacing dead routes. Dispatches background compile-fix + explore subagents at defined moments, manages its own concurrency and RAM (kill stale jobs, refill free slots), and uses the plan graph (formal nodes + informal Notes) as persistent memory across sessions. Run in the MAIN context. Use when asked to "research / settle / formalize-and-prove" an informal mathematical question or conjecture.
---

# auto-research — resolve an informal question, end to end

Input: an informal question. Output: a **kernel-checked, axiom-clean resolution** — the
question proved, or disproved, in Lean. **Resolution** means the main theorem node is
`completed` axiom-clean for `P` or for `¬P`; a counterexample is an equally complete answer.
This skill is self-contained: everything from translation to the final axiom gate is here.

**The five pillars** (each has a section; they run concurrently, not in sequence):
1. **RELENTLESS** — until resolved you decompose, rephrase, probe, pivot. No axioms, no
   stopping at hard sub-theorems, and **you never ask the user anything** — every decision
   is yours to make, document, and bank. The user can interrupt you; you never interrupt
   yourself. (§A3, §B5–B7)
2. **TWO SUBAGENTS, RIGHT MOMENTS** — `compile-fix` proves one file; `explore` answers
   questions about the world. Fire each exactly when its trigger fires, in the background,
   and act on every completion immediately. (§S)
3. **THE GRAPH IS YOUR MEMORY** — formal nodes = proof state, informal Notes = everything
   learned. Search before you research, bank before you move on, resume instead of
   restarting. It is what survives context compaction. (§M)
4. **YOU OWN THE MACHINE** — census the fleet, kill stale jobs, RAM-gate every dispatch,
   refill free slots, sweep orphans, repair the workspace. (§R)
5. **ROUTE PORTFOLIO** — 2–3 genuinely different routes raced in parallel so no single dead
   road can trap the run. Kill and replace routes; first route to close wins. (§B1)

## Inputs
- `QUESTION` — the informal question/conjecture, verbatim (required).
- `LIB_DIR` — the Lean workspace root where `lake build` runs (the lakefile dir).
  Default: the repo root (a Lake workspace after `/init_merlean`).
- `QUESTION_NAME` — *optional* CamelCase name; if omitted, propose one from the question.
- `SOURCE` — *optional* supporting material (paper, problem statement, link).

**Derived:**
- `FILE` = `<LIB_DIR>/<QuestionName>.lean` — the root file holding the main theorem; it
  imports the helper node modules. Helper nodes live in `<LIB_DIR>/<QuestionName>/`.
- `DATA_DIR` = `<LIB_DIR>/<QuestionName>_data/` — graph/progress/analytics. Pass
  `--data <DATA_DIR>` to every CLI call (`.venv/bin/python src/cli.py --data <DATA_DIR> …`)
  and to every subagent.

**Resume, don't restart:** if `DATA_DIR` exists, this run is a CONTINUATION — do §M's resume
procedure and rejoin the loop where the graph says you left off.

## Progress reporting (stream it clearly)
```
▶ <phase/id>                 ← starting a phase or obligation
   · <step in progress> …    ← one short line per step
   ✓ <result>                ← good outcome (type-checks, clean build, axiom-clean)
   ✗ <problem> → <action>    ← bad outcome + what you do next (never a stop)
   ⚡ <fleet/RAM action>      ← killed a stale job, held a slot for RAM, refilled slots
   ⇄ <route event>           ← route opened / killed (+why) / replaced / WON
```
Tag Phase-B obligations with their route (`[viaA] Lem_KeyStep`). Show the dashboard
(`… status`) at the start of Phase B, after each banked node, and at the end; finish with
`analytics --plain`. Terse lines — current status, not a transcript.

## §S The two subagents — what each is, when each fires
- **`compile-fix`** (the prover; background). ONE job: make one `.lean` file build clean
  without weakening its statement. Fire one per READY node — `status: pending` with all
  dependency files scaffolded. Prompt contract: `FILE` (relative to `LIB_DIR`),
  `STATEMENT_ID`, `DATA_DIR`, `LIB_DIR`, `AXIOM_POLICY=strict`, plus the goal signature, a
  proof ROUTE sketch, and the dependency lemmas' signatures. Tell it: if isolated outside
  `LIB_DIR` (worktree), copy `LIB_DIR` in, build the copy, return a unified diff. It returns
  `clean | needs_update (+ proposed decomposition) | failed | infra_failure` — act per §B4.
- **`explore`** (the scout; background, read-only, RAM-cheap). Fire when the question is
  about the WORLD, not this Lean file:
  (a) **Phase A**: unfamiliar terminology, known results, how the field states the claim;
  (b) **direction probes** (§A6) — numerically test the claim before committing cycles;
  (c) **witness verification** (§B6) — re-check any counterexample by an independent code
      path before believing it (sampling artifacts and capped-search lies are real);
  (d) **stuck nodes** (§B5) — after ~2 distinct failed strategies: "how is this classically
      proved / what is the standard route";
  (e) **route seeding** (§B1) — "what are the known approaches to this kind of result";
  (f) **plausibility checks** on a sub-lemma you suspect is false, BEFORE more proof rounds.
  **Always `search --kind informal` first** — a banked Note may already answer it; **bank
  every explore summary as a Note on arrival** (§M). Never re-research what the graph knows.
Both run in the background and return short summaries; the fleet rules (§R) govern slots.

---

## Phase A — formalize the question (autonomous, faithful)

### A1. Understand before any Lean
Pin down: objects, hypotheses, the exact claim, intended generality, what counts as an
answer. Hunt the implicit — this is where mistranslations are born: ambient conventions
("number"=ℕ/ℤ/ℝ? "positive" strict? is 0 natural?), degenerate cases (n=0/1, empty set —
included or excluded, and why), quantifier shape (∀∃ vs ∃∀; "the" hiding uniqueness),
determine-style problems ("find all X" has no theorem until an answer shape is fixed —
formalize the characterization `∀ x, P x ↔ x ∈ <answer set>`, or the explicit value when A6's
evidence pins it).

### A2. Research the encoding
`lean_leansearch` (natural language), `lean_leanfinder` (concept), `lean_loogle` (type
pattern). Prefer existing Mathlib structures (`Polynomial`, `SimpleGraph`,
`MeasureTheory.Measure`, …) over ad-hoc encodings — the encoding determines whether the
statement means what the question means. Unfamiliar territory → `explore` (§S a), after
checking memory (§M).

### A3. Ambiguity — decide, never ask
Where inequivalent faithful readings exist, pick the **most canonical**: the standard
literature convention, the reading the phrasing most directly supports (`explore` for how
the field states it, if unsure). Make the choice LOUD — report the chosen signature next to
the rejected alternatives and why — and **bank it as a Note** (alternatives included). If a
later contradiction reveals the reading was wrong (not just hard), that is a Phase-A defect:
fix the anchor, bank why, invalidate the downstream cone (`cone` → reset + delete files),
continue.

### A4. Draft and type-check the anchor
Scaffold `FILE`: `import Mathlib`, a namespace, the main statement `:= by sorry` (Mathlib
style: ≤100 chars, explicit types, `fun x ↦ …`; standard math names, no project token).
Iterate `lean_diagnostic_messages` on the **signature** until `sorry` is the only
diagnostic. A statement that does not elaborate is not a formalization. Do not start proving.

### A5. Faithfulness gate (all four)
- **Back-translate**: restate the Lean from the code alone; compare clause-by-clause with
  the question — nothing added, dropped, narrowed, or reordered.
- **Vacuity**: exhibit (or argue) an instance satisfying the hypotheses — contradictory
  hypotheses make the theorem vacuously true and the run worthless.
- **Small-instance sanity**: where computable, `#eval`/`decide` a tiny case that should HOLD
  and a perturbed one that should FAIL — catches wrong direction and off-by-ones.
- **Degenerate re-check**: the A1 edge-case decision against the final signature.

### A6. Direction — on evidence, not hope
Known/strongly expected → set the direction and go. Genuinely open → `explore` probe (small
exhaustive cases, random instances). Strong positive → attempt `P`. Verified counterexample →
the target is `¬P` **from the start** (formalizing the witness is usually the fastest
resolution). Ambiguous → attempt `P` AND make one portfolio route the disproof (§B1). Bank
the probe outcome (§M).

### A7. Record the anchor
```
… add --json '{"id":"Thm_<Name>","type":"Theorem","name":"<Name>",
   "content":"<the question, faithfully restated>","anchor":"<exact Lean signature>",
   "lean_path":"<QuestionName>.lean","dependencies":[]}'
```
Wire the build (a `[[lean_lib]]` entry for `<QuestionName>` in `<LIB_DIR>/lakefile.toml` if
missing; `FILE` compiles with the lone `sorry`). `cycles` must be `[]`;
`visualize --lib-dir <LIB_DIR>`. Bank Phase A's convention decisions (§M).

---

## Phase B — the resolution loop

### B1. Open the route portfolio (2–3 routes; keep it at 2–3)
Each route is a **genuinely different core idea** — different main structural lemma,
different encoding, induction vs explicit construction, direct vs contrapositive — not
variations of one idea. Seed from A6's evidence, memory (§M), and an `explore` known-
approaches hunt (§S e). Direction uncertain → **one route IS the disproof** (counterexample
hunt + `¬P` formalization as first-class work).
- **Mechanics**: each route `R` gets a route-head node `Thm_<Name>_via<R>` with the SAME
  statement as the anchor and its own helper subtree; a lemma two routes need is ONE shared
  node (`search` before every `add`). The main theorem completes the moment the FIRST
  route-head does — its file just applies the winner. Bank each route's idea + status as
  `Note_route_<R>`.
- **Review every scheduling round**: per route — distance to close, failure density, new
  obstacles. **Kill a route** only on a structural obstacle (core lemma false or provably
  unreachable, encoding can't express the step) or sustained all-node stalling: bank the
  cause (that is the road-that-never-succeeds data point), delete/freeze its unshared cone,
  **spawn a replacement** so the portfolio stays at 2–3 until the endgame. Never let it
  silently collapse to one route.
- **Endgame**: a route-head completes → prove the main node through it → delete losing
  routes' unshared nodes and files (`cone` + `delete` + remove files) → `sync-lean` → §Done.

### B2. Decompose each route into nodes
One node = one lemma = one file. Per node: id `Prefix_Name`, `content` (informal claim),
`anchor` (Lean signature when fixed), `lean_path`, `dependencies`. `search` before every
`add` (reuse, never duplicate); after ANY plan edit: `cycles` (must be `[]`), `sync-lean`,
`visualize`; `summarize` after significant growth.

### B3. Scaffold early — signature-locked parallelism
Each node file: `import Mathlib` + `import <QuestionName>.<dep module>` per dependency + the
declaration `:= by sorry`. A proof needs only its dependencies' **signatures**, not their
completed proofs — so scaffold files early and dispatch any node whose dependency files are
scaffolded, including downstream glue *before* its dependencies are proved (proving glue
early validates the interfaces). The global soundness gate (§Done) catches anything left.

### B4. The dispatch loop (every scheduling round, every completion notification)
1. `levels` / `status` → the READY nodes (pending + deps scaffolded), per route.
2. Run §R (census, stale-kill, RAM gate) and §B1's portfolio review.
3. Dispatch `compile-fix` (§S) per ready node up to the slot cap, `set-status <id>
   in_progress`, **background** — never block; keep working (scaffold next files, grow the
   plan, run probes). Never two subagents on one file; spread slots across routes (§R.5).
4. **On every completion, bank immediately** (finished-but-unbanked work is lost work):
   - apply its returned patch (worktree case) to the real checkout;
   - **verify faithfulness in main context**: the declaration proves the ORIGINAL claim —
     exact or stronger, no narrowed quantifiers/hypotheses, no placeholder/trivialized
     definitions, no disguised axioms;
   - `sync-lean <LIB_DIR>` then **`reconcile <LIB_DIR>`** (re-derive status from the files —
     self-healing; prefer over `set-status completed`, which the store can silently revert;
     `get <id>` to confirm it stuck), `record <id> --role compile-fix --json '{…}'`,
     `visualize`;
   - route the outcome: `clean` → next ready node. `needs_update` with a `decomposition:` →
     adopt it (B2: `search` each helper, add, scaffold, re-dispatch parent when ready).
     `failed` → §B5. `infra_failure` → §R.7.
5. Refill free slots (§R.5). Repeat until a route-head closes (§B1 endgame).

### B5. Difficulty ladder (per node, inside its route — never an identical retry)
(1) a different decomposition — prefer the subagent's proposal; (2) `search` both memory
groups — a dead-end Note or existing helper may reroute; (3) `explore` for the classical
route (§S d); (4) rephrase with a different Mathlib encoding (helper anchors are yours to
rephrase; the main anchor changes only via §A3-defect or §B6); (5) a weaker intermediate +
bridge lemma. **Bank each dead end BEFORE moving on** — no-identical-retries has memory only
if you write to it. Obstacle = the route's core idea itself → route death (§B1); the other
routes are still moving — a stuck node never stalls the problem.

### B6. The pivot gate — direction flips on verified evidence only
Triggers: a sub-goal unprovable *because false*; a probe or small-instance check
contradicting the claim; a counterexample candidate from anywhere. Then: (1) `explore`
verifies the witness independently (§S c). (2) **Verified** → bank the Note (witness,
method, confidence), update the main anchor to `¬P` (or witness-existence form), invalidate
the cone, continue the same loop — the disproof route becomes the favorite. (3) **Refuted**
→ bank the refutation so the suspicion cannot silently recur; return to `P`. The QUESTION
never changes; only the direction, only through this gate, and loudly.

### B7. No walls
A major missing sub-theorem is normal work — decompose through it (bank a Note recording the
scale). A Mathlib gap is built from what Mathlib does have. Axioms: **never** — there is no
consent path. Asking: **never**. Deterministic timeouts, pathological builds, stale locks:
§R. The loop ends at resolution or user interruption, nothing else.

---

## §M Memory — the graph is your mind across compactions
- **Resume procedure** (entry with existing `DATA_DIR`): `status` + `levels` (proof state);
  `list --kind informal` + `search --kind informal "<current obstacle>"` (knowledge state —
  `Note_route_*` rebuilds the portfolio: which routes live, which died and why). Rejoin the
  loop. Never re-derive what the graph holds, never redo a banked dead end, never reopen a
  killed route on the same idea.
- **Bank as informal Notes** (plan-graph skill "Informal notes"; you are the only writer):
  every explore answer; every dead end / failed strategy; route ideas, statuses, deaths with
  causes; verified counterexamples and refuted suspicions; pivots with evidence;
  encoding/convention decisions; measured thresholds. One Note per fact; `content` IS the
  claim; fill `confidence/source/method/related`.
- **Search before you research**: `informal` group before any explore dispatch or
  re-derivation; `formal` group before any `add`.
- **Correct on conflict**: kernel-checked results beat Notes — `update` (old belief →
  `corrections`) or `delete`, including when a compile-fix summary reports the contradiction.
- **Hygiene**: `sync-lean` after every Lean change; `cycles` stays `[]`; `summarize` +
  `visualize` after significant plan growth.

## §R Resources — you own the fleet and the machine
Every scheduling round and every completion notification:
1. **Census**: the running background subagents — who, which node, which route, since when.
2. **Peek before you trust**: check long-runners' output. STALE = no forward progress —
   same-error loop, ~15+ min silent, pathological build.
3. **Kill stale jobs**: stop the subagent (harness task-stop), `set-status` its node back to
   `pending`, bank a Note (what it stuck on — that's data), re-dispatch DIFFERENTLY or
   decompose. A freed slot beats a zombie.
4. **RAM-gate every dispatch**: `free -g` first — each compile-fix drives `lake`/`lean`
   processes holding several GB. Dispatch only with ~4 GB+ available per new job and no
   heavy swapping; when tight, run fewer than the cap; when swapping, kill the
   newest/least-progressed job and hold its slot.
5. **Refill free slots**: **≤ 4 background subagents total** (compile-fix + explore), never
   two on one file. Spread across live routes — every route with ready work advances each
   round; spare capacity to the most promising. Never idle with ready work and RAM-cleared
   capacity; never dispatch past the RAM gate.
6. **Orphan sweep** after kills/crashes: `pgrep -af "lake build"` — kill leftover build
   processes under `LIB_DIR` belonging to no live subagent. **Never** touch the lean-lsp
   MCP server's processes.
7. **Workspace repair** (a subagent reports `infra_failure`, or builds fail on corrupt
   state): fix it yourself — clear stale `.lake` locks / bad `.olean`s, `lake exe cache get`
   / rebuild, then re-dispatch. Transient `.olean`-lock errors from parallel builds just
   need a rebuild, not repair. Never hand-edit `.git`.

---

## §Done — the gates and the report
- **Proved**: losing routes already cleaned (§B1 endgame). Then: `#print axioms
  <Thm full name>` = `[propext, Classical.choice, Quot.sound]` exactly (no `sorryAx`, no
  axioms); after a final `sync-lean`, `lint` reports `"n": 0`; no residual `sorry`/`admit`
  anywhere in the imported cone. Report: the final Lean statement, that it faithfully
  formalizes the question (Phase A trail), **proved**, the winning route (and what killed
  the others), helper lemmas, key tactics.
- **Disproved**: the same gate on the `¬P` / counterexample theorem — a settled "no" is a
  complete research result. Report the witness and the §B6 evidence trail.
- **Interrupted by the user** (the only unresolved ending): faithful state — `status`, the
  proven subtree, the precise obstacle, ladder/portfolio position, and the Notes a resumed
  session will find.
Show the final `status` + `analytics --plain`.

## Notes
- **Self-contained**: this skill does not depend on `/prove`, `/formalize`, or
  `/formalizeproblem` — those remain separate entry points for their own use cases (a
  `.lean` file with sorries; a paper; interactive translation-only).
- The plan graph IS the proof plan AND the research memory: helpers are nodes, edges are
  uses, one node = one file, knowledge is Notes.
- Keep the main context lean: rely on subagent summaries; pull detail with
  `get`/`list`/`search` on demand; the full work lives in the subagents and the graph.
