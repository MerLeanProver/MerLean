# Independent editorial evaluation

The synthetic cases in `tests/fixtures/recursive_writer_editorial/` test reviewer judgment
separately from deterministic state-engine tests. They use elementary mathematics, not private
research. Each role has a separate `inputs.json` with neutral case IDs; `expectations.json`
is a coordinator-only answer key. Never supply the answer key, another reviewer's verdict,
or the expected outcome when dispatching an evaluator.

Dispatch one independent invocation per role with its maintained role file and only that
role's input. The cases are miniature independent papers, not sections of one manuscript.
Store each actual returned report unchanged in a run directory outside the fixtures. Required
finding means a material repair is needed; harmless alternative wording may be advisory.

Each report is JSON with `schema_version: 1`, `role`, actual `reviewer_id`, actual
`invocation_id`, and a `results` array. Each result gives `case_id`, `verdict` (`PASS`, `FAIL`,
or `INCOMPLETE`), a substantive `summary`, and `findings`. Each finding has `severity`
(`required` or `advisory`), `location`, `evidence`, and a testable `resolution`. A FAIL needs
a concrete required finding. PASS must not contain one. These evaluation reports are not
paperctl manuscript-review receipts and cannot authorize a manuscript release.

After all four reports are archived, compare them to the answer key:

```text
python scripts/evaluate_writer_editorial.py --reports /private/evaluation/reports
```

The directory must contain one report JSON per role. The utility verifies report structure,
distinct invocation/reviewer identities, exact case coverage, and expected required-repair
decisions. It prints JSON containing report hashes and classification mismatches. Exit code
zero means all expected decisions agree; it does not prove that the explanations are sound.
The coordinator must separately inspect evidence to ensure each defect was detected for the
right reason and that required repairs are not imposed on positive controls. Record this
semantic assessment alongside the untouched reviewer reports.

The utility never invokes a model, creates a reviewer verdict, rewrites reports, or treats the
presence of fixtures as a passed evaluation. `INCOMPLETE` never counts as success. If a reviewer
misclassifies a case, retain that report and the failed comparison. A later rerun belongs in
a separate directory with fresh invocation identities; do not edit the old evidence.
