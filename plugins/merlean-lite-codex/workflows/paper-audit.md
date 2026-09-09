# Paper Audit

Internal read-only routine of the paper-writing agent. Inherit `<PLUGIN_ROOT>` from its
public entry point. Read [audit-checklist.md](paper/audit-checklist.md), then inspect the raw source, ledgers, graph,
certificates, reference registry, and candidate. Do not trust another agent's summary.

Run `<PLUGIN_ROOT>/scripts/paperctl audit --state <state>` first. Run
`<PLUGIN_ROOT>/scripts/paperctl compile <candidate>`; it writes only to a
temporary directory. Snapshot hashes and Git status before and after and fail if the audit changed
the project.

Independently check what scripts cannot decide:

- exact mathematical equivalence of locked main results;
- coverage of rewritten, merged, cited, and ledger-only baseline content;
- summary claims are weaker than or equal to precise statements;
- definitions are once-only and just in time;
- literature source TeX actually contains each cited claim;
- terminology and notation are field-standard and collision-free.

Return `PASS` or `FAIL`, followed by concrete evidence and exact residuals. Never edit files,
download sources, update ledgers, mark gates, or commit.
