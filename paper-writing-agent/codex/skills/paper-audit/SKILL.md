---
name: paper-audit
description: Read-only audit of a new or revised mathematics paper for main-result fidelity, baseline coverage, compression-ledger integrity, definition placement, terminology consistency, arXiv source and BibTeX verification, summary strength, appendix cross-references, and clean isolated LaTeX compilation. Use after paper drafting/refinement or when asked to assess whether a versioned TeX paper preserved the original.
---

# Paper Audit

Remain read-only. Resolve `<PLUGIN_ROOT>` as the directory three levels above this file. Read
[audit-checklist.md](references/audit-checklist.md), then inspect the raw source, ledgers, graph,
certificates, reference registry, and candidate. Do not trust another agent's summary.

Run `paperctl audit --state <state>` first. Run `paperctl compile <candidate>`; it writes only to a
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
