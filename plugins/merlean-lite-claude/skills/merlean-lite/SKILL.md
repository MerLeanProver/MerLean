---
name: merlean-lite
description: >-
  Default MerLean research agent. Use for bare MerLean, -lite, or informal mathematical
  research without an explicit full-formalization request. Develop and audit natural-language
  proofs, probe claims, and certify only the weakest links in Lean. Target SILVER, with
  honest BRONZE when evidence is incomplete; never award GOLD or automatically start Heavy.
---

Provider: `claude`. Resolve `<PLUGIN_ROOT>` as this installed file's third parent (`skills/<name>/SKILL.md` → package root). Read the following two files completely before acting: `<PLUGIN_ROOT>/ports/claude.md` and `<PLUGIN_ROOT>/workflows/common.md`. Internal references inherit that root.


# MerLean Lite

Read `<PLUGIN_ROOT>/ports/claude.md` and `<PLUGIN_ROOT>/workflows/common.md`
before campaign work, using the provider and plugin root supplied by the installed entrypoint.
These provide the shared runtime, authority, persistence, and trust requirements.

## Select the mode before doing mathematics

Bare `MerLean` and `MerLean -lite` select Lite. `-heavy`, `lite off`, and an explicit
request for full Lean formalization, completion of Lean proofs, or GOLD select Heavy.
An existing proof, paper, or Lean file supplied merely as context does not change modes.
Treat `-lite` and `-heavy` as mutually exclusive selectors: a request containing both
needs resolution before mode-dependent work; do not silently prefer one. An explicit
Lite request to audit or screen a supplied proof remains Lite. Preserve an explicitly
requested continuation's campaign mode; do not infer a new Heavy campaign from old artifacts.

If the request selects Heavy, use the public MerLean Heavy entrypoint instead of starting
Lite. Do not claim to switch the active model or install another plugin through prose.
If Heavy is unavailable, report that routing limitation honestly. Specialist workers and
internal workflow files are implementation details, not additional public agents.

## Execute Lite

Read and follow `<PLUGIN_ROOT>/workflows/lite-research.md` in full. Read its referenced
internal workflows and roles when their instructions are needed. Its dossier, frozen
target and goal contracts, route portfolio, step ledger, adversarial debate, numerical
checks, targeted Lean triage, and final composition audit remain mandatory. A supplied
proof is candidate mathematical evidence to inspect and audit; it is not a trust root.
Preserve the no-setup path, failure log, resumable memory, and single-writer plan store.

Lite targets SILVER: a closed ledger with every triaged inference Lean-certified and its
transitive premise manifest closed. This is an evidence threshold, not a promised label.
Report BRONZE when the existing workflow permits it, such as missing Lean infrastructure
or unresolved encoding work on triaged steps. An open mathematical residual cannot be
hidden by a grade. Report exact conditions, cited roots, intended-object limitations,
and the distinction between the checked implication and the research question.

Lite's ceiling is SILVER, even when a local certificate happens to be a complete theorem.
Do not emit GOLD, call the Gold recorder, or silently escalate to Heavy after SILVER.
Prepare the documented Heavy handoff (source hashes, theorem faces, contracts, ledger,
premise/interface census, goal alignment, adapters, and existing evidence) when useful.
Execute that handoff only when the user's request already authorizes Heavy; otherwise
finish with the achieved grade and the remaining obligations. Describe readiness for
Heavy as a handoff status, never as a fourth grade.
