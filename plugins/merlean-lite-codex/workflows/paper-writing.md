---
name: paper-writing
description: Synthesize research notes into an assessed paper prospectus, or recursively compose and refine papers with independent faithfulness, narrative, notation, and wording reviews. Preserve source evidence and grades; synthesis requires author approval and stops at a handoff.
---

# Paper-writing

Read `workflows/common.md` and the provider adapter supplied by the installed entrypoint.
Read `workflows/paper-synthesis.md` for notes-to-prospectus synthesis and its resume/audit.
New compose/refine runs use schema version 2 and `workflows/paper-recursive-writing.md`:
an external plan, writer, and four independent checkers, with five reviewed manuscript
revisions by default. Use the existing host's subagent tools, whole-paper tasks where
practical, and parallel review within host capacity. There is no standalone model launcher.
Read `workflows/paper-audit.md` for manuscript audit-only requests. Inspect a supplied run's
recorded mode and schema version before routing resume or audit. Schema-version-1 writing
runs retain `workflows/paper-compose.md` and the legacy eight-stage protocol; do not silently
migrate their gate approvals. Shared source, preservation, reference, and evidence checks
remain binding in both versions. Claude's historical supplement applies only to legacy runs.

Synthesis needs no Lean installation, campaign graph, or LaTeX toolchain. It does not create a
manuscript. Present supported candidate contributions, pause for actual author approval of an
exact angle, then assess that angle. Stop at the decision and handoff; drafting or new research
requires a separate request. A negative assessment is a valid completed outcome, not a failed
attempt to manufacture a paper. Correctness, bounded-search novelty, and significance stay separate.

An audit stays read-only; compilation uses isolated temporary output. Refinement never
overwrites its baseline. Keep its coverage, locked main results, source registry, version
and hash checks. Main and GPT auditors default to Astra under the shared dispatch policy;
Claude keeps its configured provider model. Record independent auditor identity without
silently rewriting historical audit records.

In recursive writing, checkers assess faithfulness, narrative/structure, notation/definitions,
and wording/presentation. Faithfulness assumes the approved source mathematics is correct;
it is not a new proof audit. Collect all scheduled feedback before replanning. Completion
requires current receipt-bound passes and deterministic/build/rendered checks, not agreement
on optional taste. A limit or source/scope blocker produces an honest resumable pause.
Do not infer authority for commits, installation, publication, expanded contributions, or
research from a writing or review request.

Writing does not certify research: retain the exact recorded grade, explicit conditions,
and unresolved questions. If new mathematical gaps appear, record them and route to Heavy
only when authorized. Do not market a conditional theorem as an unconditional solution.
