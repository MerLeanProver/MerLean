# Paper Audit

Internal read-only routine of the paper-writing agent. Inherit `<PLUGIN_ROOT>` from its
public entry point. Inspect the run mode and schema version before choosing a checklist.
For schema-version-2 compose/refine runs, read [recursive writing](paper-recursive-writing.md):
audit the writing contract, immutable dependency snapshots, current role/rubric receipts,
required findings, source/claim/reference preservation, additional equivalence reviews,
isolated build, and final rendered inspection. Do not apply the legacy negative-shrink or
rigid definition-placement checks. Old schema-version-1 manuscript runs retain
[audit-checklist.md](paper/audit-checklist.md). Inspect raw sources and evidence rather than
trusting another agent's summary.

First inspect the run mode. For `synthesize`, use [paper-synthesis.md](paper-synthesis.md)
instead of the manuscript checklist: run the mode-aware `paperctl audit`, inspect source and
claim evidence, selection approval, reviews, and decision, and never compile or require TeX.
An audit-only request cannot select a candidate, refresh sources, download literature, or mark gates.

Run `<PLUGIN_ROOT>/scripts/paperctl audit --state <state>` first. Run
`<PLUGIN_ROOT>/scripts/paperctl compile <candidate>`; it writes only to a
temporary directory. Snapshot hashes and Git status before and after and fail if the audit changed
the project.

For legacy schema-version-1 audits, independently check what scripts cannot decide:

- exact mathematical equivalence of locked main results;
- coverage of rewritten, merged, cited, and ledger-only baseline content;
- summary claims are weaker than or equal to precise statements;
- definitions are once-only and just in time;
- literature source TeX actually contains each cited claim;
- terminology and notation are field-standard and collision-free.

Return `PASS` or `FAIL`, followed by concrete evidence and exact residuals. Never edit files,
download sources, update ledgers, mark gates, or commit.
