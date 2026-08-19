---
name: paper-writing
description: Orchestrate writing, reorganizing, shortening, or polishing a mathematics paper from a MerLEAN/Lean dependency graph, or refine an existing LaTeX paper into the next non-destructive -vN version. Use for new-paper composition, existing-paper revision, resuming a gated paper run, novelty and reference verification, appendix factoring, terminology normalization, and preservation of the original paper's main results and coverage.
---

# Paper Writing

Run in the main context. Resolve `<PLUGIN_ROOT>` as the directory three levels above this
`SKILL.md`; use `<PLUGIN_ROOT>/scripts/paperctl` for every deterministic operation.

Read the following only when applicable:

- Read [protocol.md](references/protocol.md) for the complete eight-stage gates.
- Read [refinement.md](references/refinement.md) whenever an existing `.tex` is supplied.
- Read [references.md](references/references.md) before adding or changing a citation.
- Read [merlean.md](references/merlean.md) before extracting a dependency graph or critical path.

## Select a mode

- `compose`: write a new paper from a campaign/graph. Run `paperctl init-compose`.
- `refine`: polish or reorganize an existing paper. Run `paperctl init-refine`; never edit the
  input. An input without a terminal `-vN` is v0, so `paper.tex` produces `paper-v1.tex`.
- `resume`: run `paperctl resume --state ...` and continue at the first unpassed gate.
- `audit`: use `$paper-audit`; do not edit, download, commit, or write build products into the
  project.
- `next-version`: run `paperctl next-version INPUT.tex`; make no files.

Never infer a version from sibling files. If the required output exists, stop and tell the user to
pass that version as the new input. Never overwrite or silently skip a version.

## Preflight

1. Locate the campaign, paper project, Lean library, plan data, and graph source. Prefer an existing
   `statements.json` or `dependency-graph/graph.json`; do not rebuild a graph needlessly.
2. Snapshot `git status`. Preserve unrelated and pre-existing changes.
3. Initialize the run. In refine mode, verify the printed source/output paths before editing.
   If an editor intentionally replaces the output inode during an atomic save, immediately run
   `paperctl claim-output --state <work>/00-run-state.json`; investigate an unexplained replacement.
4. Treat `00-run-state.json` as the run checkpoint. At every gate, recheck the baseline hash.
5. In refine mode, select the baseline main theorem labels and run `paperctl lock-main`. Do not
   leave the main-result lock empty.

## Orchestration and SOL roles

Use `gpt-5.6-sol` subagents for bounded independent work. With four total slots, use at most three
children. Give each writer exclusive files; the main agent alone edits run state, coverage ledgers,
the versioned TeX, and Git. Use read-only SOL agents for:

- critical-path/certificate verification;
- literature novelty and source-content checks;
- summary-strength and main-result-equivalence audits;
- final coverage, definitions, terminology, references, and LaTeX audit.

Do not leak an intended verdict to an auditor. Require evidence and `PASS`/`FAIL`. Two independent
SOL `PASS` records are required if a locked main theorem statement is reworded.

## Execute the gated workflow

Follow [protocol.md](references/protocol.md) in order. The essential sequence is:

1. Extract and verify the theorem-grade critical paths and terminal hypothesis surfaces.
2. Compile an empty standard mathematics-paper framework.
3. Fix 2–4 main results, check current literature, and decide one title/theme. In compose mode,
   populate `03-main-results.json` for each result with `graph_node_id`, `candidate_label`, the
   frozen statement `normalized_sha256`, full `hypothesis_surface`, `novelty_status` (`CLEAR` or
   `ADJACENT`), and `novelty_evidence`.
4. Before changing candidate TeX, optimize the reader-facing proof dependencies using only Lean
   and Markdown. Use the union of the full ancestor closures of the selected main results, not only
   displayed longest paths. Collapse direct specializations of retained general results, omit
   elementary steps, and remove or sharply summarize material outside that cone. Record every
   replacement, omission, and old/new consumer in `04-lemmas.md`; if formal dependencies are
   explicitly changed, rebuild Lean and rewire the corresponding Markdown DAG before drafting.
5. Organize and complete the full draft, then run the separate compression gate:
   - run `paperctl freeze-shrink --state <work>/00-run-state.json` immediately after the draft
     gate and before deleting or relocating anything;
   - remove elementary, boring, unnecessary units from TeX only after recording their exact
     statement, source, consumers, and rationale in `05.5-deleted-steps.md`;
   - retain important routine statements in the body, move their proof/derivation to the appendix,
     and link body and appendix in both directions with unique `\label`/`\ref` pairs;
   - cite established literature instead of reproducing textbook or published proofs.
6. While drafting, introduce each definition, standing constraint, declaration, and notation
   exactly once, immediately before first technical use. Put setup shared by sections or appendices
   once in the root main TeX and refer back to it. Put unavoidable technical lemmas and lengthy
   proofs in the appendix.
7. Write title, abstract, and outlook last; then standardize field terminology and notation.
8. Run preservation, reference, isolated compile, and independent SOL gates; checkpoint locally.

Run `paperctl gate` only after storing evidence. A failed gate stays failed until repaired and
rerun. Never carry a known defect forward.

## Binding paper rules

- Keep Lean code, identifiers, and filenames out of the paper. Describe the trust model in prose
  and cite the repository once.
- State standing setup once. Put only claims in theorem statements. Itemize multi-claim results.
- Do not organize paper prose or proofs with process-numbered headings such as `Step 1`, `Step 2`,
  or `Stage 3`. When a roadmap materially helps, use an unnumbered LaTeX `itemize` list whose
  items begin with short bold mathematical summary phrases; otherwise use cohesive prose.
- Give main results coarse mathematical proofs; put workhorse detail in the appendix.
- Present a direct specialization of a retained general theorem with at most a one-sentence
  application; do not re-prove it or promote it to an independent result. Never collapse a selected
  or locked main result.
- Omit elementary proof steps from the paper narrative. Presentation omission does not authorize
  deletion of a Lean declaration that still has formal consumers.
- Remove material outside the selected critical-path cone or reduce it to one sentence unless it
  supplies a recorded scope condition, caveat, credit, trust fact, shared setup, or live paper
  consumer. Preserve every omission in the recovery ledger.
- Treat formal dependencies as frozen during paper writing. An explicitly authorized Lean
  dependency change reopens the critical-path and lemma gates, requires a clean rebuild, and must
  be reflected in both `01-critical-path.md` and `04-lemmas.md` before TeX work resumes.
- Apply compact layout only after the proof plan, Lean build, compression, definitions, and
  terminology pass. Honor a supplied journal class; otherwise use a standard mathematics-journal
  class with approximately `0.85in` margins, never below `0.75in`. Do not compress with tiny type,
  condensed line spacing, negative spacing, scaling, cropping, or overlapping floats.
- Keep every abstract/introduction/section-lead restatement weaker than or equal to the exact
  theorem; carry scope riders and quantifiers.
- Distinguish absolute kernel verification, verification modulo named literature-supported axioms,
  and named hypothesis mode.
- Preserve recorded credit splits in the same sentence as the associated claim.
- Never strengthen, weaken, demote, or silently drop a baseline main result during refinement.
- Never silently drop baseline content. Every changed unit receives exactly one coverage
  disposition and destination.

## Reference and novelty discipline

For new references, follow [references.md](references/references.md) exactly: confirm identity on
arXiv, download and safely extract the complete TeX source into project `refs/`, inspect the source
for the claimed result, and save the arXiv “Export BibTeX citation” verbatim. Reuse a cached source
only when its registry and hashes pass. If the result is absent, reject that citation and verify a
similar arXiv paper.

A novelty search can document `CLEAR`, `ADJACENT`, or `COLLISION`; it cannot prove global novelty.
A collision reopens main-result selection in compose mode. In refine mode, preserve the locked main
result and correct the novelty/title language or stop for a genuine conflict.

## Completion

Run the deterministic preservation audit and isolated compile first:

```text
<PLUGIN_ROOT>/scripts/paperctl audit --state <work>/00-run-state.json
<PLUGIN_ROOT>/scripts/paperctl compile <output-vN.tex>
```

Then dispatch two independent read-only SOL audits: semantic preservation/summary strength, and
reference/coverage/notation/LaTeX. Mark the final gate only after both pass, then run `paperctl audit
--state <work>/00-run-state.json --require-all-gates` as the release check. In a Git worktree, make
path-scoped local checkpoint commits; never push. Report the title, printed main results,
verified/total references, pages, open questions, output path, and unchanged baseline hash.
