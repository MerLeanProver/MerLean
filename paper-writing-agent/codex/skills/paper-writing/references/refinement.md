# Refinement mode

## Version rule

Only a terminal `-vN` before `.tex` counts. `paper.tex` and `paper-v0.tex` both produce
`paper-v1.tex`; `paper-v7.tex` produces `paper-v8.tex`; `paper-v2-draft.tex` produces
`paper-v2-draft-v1.tex`. Reject leading-zero versions such as `-v01`. Derive N from the supplied
input, never siblings. Refuse a collision and never overwrite.

Initialize with:

```text
paperctl init-refine INPUT.tex
```

This creates an exact versioned copy before edits, records the input SHA-256, and builds a work
directory next to the paper under `paper-writing/<output-stem>/`.

The run records the output inode to detect path replacement. Ordinary in-place edits preserve it.
After a legitimate editor performs an atomic save, run `paperctl claim-output --state
WORK/00-run-state.json` before any gate, resume, snapshot, or audit command; investigate rather than
claim an unexpected replacement.

## Main-result preservation

After identifying every baseline main result, run one `--label` per result:

```text
paperctl lock-main --state WORK/00-run-state.json --label thm:first --label thm:second
```

Default to preserving each normalized statement and stable label exactly. If presentation requires
a mathematically equivalent rewording, record the changed statement and two independent SOL
equivalence audits in `00-main-results-lock.json`. Any change to domain, quantifier, hypothesis,
scope rider, inequality direction, constant, or conclusion is a failure. Do not move a main result
out of the paper's main-results presentation.

## Coverage dispositions

Every baseline inventory unit starts as `auto`, which passes only while normalized content remains
unchanged. A changed unit must receive exactly one disposition in `05-coverage-ledger.json`:

- `retained`: reworded in place; give a target label, reason, evidence, and two independent
  semantic PASS records for any changed mathematical statement.
- `moved`: same content elsewhere; give a target label and reason; changed mathematical wording
  needs two independent semantic PASS records.
- `merged`: faithfully subsumed/factored; give the target and reason; changed mathematical wording
  needs two independent semantic PASS records.
- `cited`: replaced by verified literature; give citation key and reason.
- `ledger-only`: elementary/unnecessary; mirror the exact omitted normalized TeX plus its hash in
  `05.5-deleted-steps.md` and the JSON record, and preserve the verbatim raw TeX (including
  comments/formatting) plus its SHA-256.
- `body-appendix`: important statement in body, proof moved with two-way labels/refs.

A baseline theorem that directly specializes a retained general theorem may be collapsed only as
`merged`, with the retained theorem as target, a compiling Lean instantiation witness, two
independent semantic `PASS` records, complete old/new consumer mapping, and exact recovery text. A
locked main result is never eligible. Record presentation-edge rewiring in `04-lemmas.md`; formal
Lean edges remain frozen unless an authorized change reopens and reruns the earlier gates.

Run `paperctl freeze-shrink` after the full draft and before applying these dispositions. The
Markdown ledger is for readers and recovery; JSON is the deterministic mirror. Preserve old and
new consumers for omissions and merges. An unclassified change is a hard failure.

## Preservation audit

Run `paperctl audit --state WORK/00-run-state.json`. It checks the baseline hash, aliases, complete
ledger, exact unchanged units, destination labels/citations, Markdown anchors, bidirectional appendix
links, main-result locks, unresolved refs, and reference registry. A SOL semantic auditor must still
check mathematical equivalence and prose-topic coverage.
