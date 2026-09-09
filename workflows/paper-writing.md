---
name: paper-writing
description: Compose, refine, resume, or read-only audit a mathematics paper with preserved theorem statements, source-checked citations, and versioned LaTeX. Does not prove new mathematical gaps or promote research grades.
---

# Paper-writing

Read `workflows/common.md` and the provider adapter supplied by the installed entrypoint.
Read `workflows/paper-compose.md` for compose/refine/resume/next-version; read
`workflows/paper-audit.md` for audit-only requests. They share `scripts/paperctl` and the
eight-stage, preservation, reference, and refinement checks under `workflows/paper/`.
Claude composition additionally reads `workflows/paper-claude-protocol.md` for its retained
presentation guidance; shared preservation/source gates apply to both providers.

An audit stays read-only; compilation uses isolated temporary output. Refinement never
overwrites its baseline. Keep its coverage, locked main results, source registry, version
and hash checks. Main and GPT auditors default to Astra under the shared dispatch policy;
Claude keeps its configured provider model. Record independent auditor identity without
silently rewriting historical audit records.

Writing does not certify research: retain the exact recorded grade, explicit conditions,
and unresolved questions. If new mathematical gaps appear, record them and route to Heavy
only when authorized. Do not market a conditional theorem as an unconditional solution.
