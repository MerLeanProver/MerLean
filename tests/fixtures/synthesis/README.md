# Synthesis evaluation fixtures

`scenarios.json` contains public, synthetic semantic evaluation scenarios. They
contain no project notes, private paths, or unpublished research results.

These are not golden mathematical judgments to be inferred from JSON validation.
A separate reviewer should read each scenario, inspect a synthesis run, and report
which rubric items are supported by its evidence and which unacceptable behaviors
occurred. In particular, a deterministic test cannot establish significance,
proof correctness, actual independence of reviewers, or global novelty.

The automated synthesis tests use toy records to exercise provenance, immutable
input handling, approval binding, workflow decisions, and handoff safety. Passing
those tests says nothing about whether a toy statement merits publication.
