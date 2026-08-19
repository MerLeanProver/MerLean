---
name: formalizeproblem
description: Turn an INFORMAL mathematical problem into faithful, type-checking Lean 4 statement(s) with `:= by sorry` — translation only, no proving. Careful with ill-posed problems — it surfaces inequivalent readings and asks before committing. Run in the MAIN context. Use when asked to "formalize this problem", "translate this statement to Lean", "state this in Lean", or to prepare a statement for prove mode.
---

# formalizeproblem — informal problem → faithful Lean statement(s) with `sorry`

The deliverable is a `.lean` file whose declarations **elaborate cleanly with `sorry` as the
only diagnostic** and **say exactly what the informal problem says**. Success is faithful
translation, NOT provability: never bend a statement toward what Mathlib can reach, never
"fix" a claim that looks false — if the natural reading seems wrong, formalize it anyway and
say so (that is a finding, not a translation error). No proving happens here; the output is
exactly what `/prove` or `/auto-research` Phase B picks up.

## Inputs
- `PROBLEM` — the informal problem (text, or a path/source to read).
- `FILE` (optional) — target `.lean` path; default `<ProblemName>.lean` in the workspace root.
- `LIB_DIR` (optional) — the Lean workspace; default the repo's root workspace.

## 1. Understand the problem — before any Lean
Pin down in prose: the objects, the hypotheses, the exact claim, the intended generality, and
what counts as an answer. Then hunt for what the text leaves implicit — this is where
mistranslations are born:
- **Ambient conventions**: "number" (ℕ/ℤ/ℝ? is 0 a natural?), "positive" (>0 or ≥0),
  "between" (strict?), division/`sub` on ℕ, "polynomial" (which coefficients?), "graph"
  (simple? loops?), implicit nonemptiness/finiteness.
- **Degenerate cases**: does the problem silently exclude n = 0/1, the empty set, the trivial
  group? Decide whether the formal statement includes or excludes them — and record why.
- **Quantifier shape**: "for all … there is" vs "there is … for all"; is a claimed object
  unique? Is "the" hiding an existence-and-uniqueness assertion?
- **Determine-style problems** ("find all X", "compute the value"): these have no theorem
  until an answer is fixed. Either the user supplies/confirms the expected answer (state
  `f = <answer>`), or formalize the characterization shape (`∀ x, P x ↔ x ∈ <answer set>`).
  Ask which — this is always load-bearing.

## 2. Choose the reading — ask only when it is load-bearing
- **One canonical faithful reading** → proceed silently; record every convention you chose in
  the final report.
- **Two or more mathematically inequivalent faithful readings** (or an ill-posed fragment: an
  undefined term, a claim that needs a missing convention to even parse) → **ask the user**
  (`AskUserQuestion`), presenting 2–4 candidate **Lean signatures** as options (use option
  `preview`s to show the actual signatures; recommend one). Never silently pick between
  inequivalent readings — a wrong pick wastes everything built on it.
- The problem being *hard* or *probably false* is NOT ill-posedness — translate it as stated.

## 3. Research the Mathlib encoding
Find the types that express the objects faithfully: `lean_leansearch` (natural language),
`lean_leanfinder` (concept), `lean_loogle` (type pattern). Prefer existing Mathlib structures
(`Polynomial`, `SimpleGraph`, `MeasureTheory.Measure`, …) over ad-hoc encodings — the encoding
determines whether the statement means what the problem means. For unfamiliar terminology or
context (a named competition problem, a conjecture's standard statement), dispatch an
**`explore` subagent** — and if a plan graph (`<DATA_DIR>`) is in play, `search` its
`informal` group first for prior encoding decisions.

## 4. Write the statement(s)
- One declaration per claim: parts (a)/(b) become separate theorems; a needed new concept
  becomes a real `def` (a genuine definition — never a placeholder, `True`-field structure, or
  a def whose only content is the theorem). Shared hypotheses can live in `variable`s.
- Every body is `:= by sorry` (a `def` for a determine-problem answer may be `:= sorry` only
  if the user asked for that shape). `import Mathlib`, a namespace, Mathlib style (≤ 100
  chars, explicit types, `fun x ↦ …`).
- Name declarations by standard math content, not by the project token.

## 5. Type-check — a statement that does not elaborate is not a formalization
Run `lean_diagnostic_messages` (or `lake build`) and fix **signature** errors until the only
remaining diagnostics are the `declaration uses 'sorry'` warnings. Do not start proving.

## 6. Faithfulness self-check (the gate — run ALL of these)
- **Back-translate**: restate each Lean declaration in English from the code alone, then
  compare clause-by-clause with the original. Every hypothesis, quantifier, strictness, and
  conjunct must match; nothing added, dropped, narrowed, or reordered.
- **Vacuity check**: are the hypotheses satisfiable? Exhibit (or at least argue) a concrete
  instance meeting them — contradictory hypotheses make the theorem vacuously true and the
  translation worthless. Watch for the `∃ x, True` shape and for a hypothesis that secretly
  implies the conclusion.
- **Small-instance sanity**: where the objects are computable, test tiny cases — an
  `example`/`#eval`/`decide` on an instance where the claim should HOLD, and a perturbed one
  (reversed inequality, off-by-one) where it should FAIL. This catches wrong direction and
  boundary errors that back-translation misses. Delete the probes afterwards (or keep them as
  `example`s only if they elaborate without `sorry`).
- **Degenerate cases**: re-check the n = 0 / empty-set decision from §1 against the final
  signature — did an `n : ℕ` sneak in where the problem means `n ≥ 1`?

## 7. Report
Show the final statement(s) **verbatim**, then: the conventions chosen and why, any
ambiguity resolved (and how — user answer vs canonical reading), the vacuity/sanity evidence
from §6, and anything still caveated. If a plan graph is in play, bank load-bearing
convention decisions as informal Notes (plan-graph skill, "Informal notes"). Point at the
next step: the file is prove-ready (`/prove FILE`), or `/auto-research` if the user wants it
settled.

## Notes
- Siblings: `/formalize` = paper → proven library; `/auto-research` = fully autonomous
  end-to-end resolution (it implements its own never-ask formalization inline — this skill
  stays the interactive, translation-only entry point).
- Translation only: no proof attempts, no plan decomposition, no status churn. The one
  Lean-facing success criterion is §5's clean elaboration.
