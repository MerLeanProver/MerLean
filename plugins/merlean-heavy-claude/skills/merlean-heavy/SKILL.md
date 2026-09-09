---
name: merlean-heavy
description: >-
  MerLean Heavy, selected by -heavy, lite off, an explicit GOLD request, or a request
  for full Lean formalization or proof completion. Resolve open questions, formalize
  supplied natural-language proofs and papers, or complete Lean stubs under the same
  strict semantic and kernel gates. Also handles explicit statement-translation-only
  requests without proving or awarding a research grade.
---

Provider: `claude`. Resolve `<PLUGIN_ROOT>` as this installed file's third parent (`skills/<name>/SKILL.md` → package root). Read the following two files completely before acting: `<PLUGIN_ROOT>/ports/claude.md` and `<PLUGIN_ROOT>/workflows/common.md`. Internal references inherit that root.


# MerLean Heavy

Read `<PLUGIN_ROOT>/ports/claude.md` and `<PLUGIN_ROOT>/workflows/common.md`
before campaign work, using the provider and plugin root supplied by the installed entrypoint.
Heavy means Lite is off. Bare MerLean defaults to Lite; selecting this entrypoint does not
make Heavy the global default. Treat simultaneous `-lite` and `-heavy` as a conflicting
selection requiring resolution. User scope and explicit stop/translation instructions
take precedence over internal routines' autonomous research defaults.

## Choose the internal work from the requested outcome

Read the selected internal workflow in full before executing it. These are capabilities
of Heavy, not separately advertised public agents.

| User's requested outcome | Internal workflow |
| --- | --- |
| Resolve an open informal question, or continue a research campaign to GOLD | `workflows/auto-research.md` |
| Turn a supplied natural-language proof or paper into verified Lean | `workflows/formalize.md` |
| Fill `sorry`/`admit` or complete existing typed Lean declarations | `workflows/prove.md` |
| State/translate the claim in Lean only, with no proof requested | `workflows/formalizeproblem.md` |

Resolve every path above relative to `<PLUGIN_ROOT>`. Use `workflows/plan-graph.md`
for graph operations and `workflows/init-merlean.md` when setup is needed. An attached
artifact alone does not override the requested outcome: screening a paper under explicit
Lite stays Lite. A request to formalize an existing proof means complete formalization;
a request to translate only its statement means the translation-only branch.

## Supplied-proof formalization

Use the supplied proof as the initial route and extract its definitions, lemmas, dependencies,
and proof sketches into the plan. For a standalone natural-language proof, apply the paper
workflow's extraction and faithfulness checks directly to that proof; a PDF is not required.
Verify the source-to-Lean match, hidden hypotheses, citations, degenerate cases, and every
consumed intermediate claim. Proof availability may reduce discovery work; it does not
reduce any proof obligation or semantic gate, and encoding/library gaps may still be hard.

Do not force a fresh 2–3-route research portfolio merely because Heavy was selected when
there is an adequate supplied proof. Follow the formalization schedule, proving its entire
dependency cone. If a gap requires discovery, use the research difficulty ladder and a
portfolio for that gap, keeping the frozen target intact. Report defects and repairs with
provenance. Never treat the manuscript's assertion, an accepted Lite row, or a natural-language
proof as an original hypothesis. Do not assume a missing lemma, weaken the result, or
change the question to make formalization appear complete.

## Common initialization and completion for every proof-producing branch

In addition to the selected workflow, read `workflows/auto-research.md` in full and apply
its Phase A faithfulness, hypothesis-firewall, intended-model, definition-independence,
goal-path, and target-freezing requirements plus its entire `§Done` procedure. These gates
apply to paper/proof formalization and Lean-stub completion just as to open-question research.
They do not require rerunning discovery when the proof or faithful typed anchor already exists.
Read `workflows/common.md` for the common completion and auditor binding requirements.

Freeze exact source hashes, theorem faces and signatures, original premises, intended objects,
and the separate goal contract before proving. Preserve an existing faithful Lean anchor;
record any genuine source/translation defect and invalidate affected evidence before repair.
Resume an existing campaign from its contracts, graph, failure log, and banked notes.
Heavy can start directly: prior Lite execution or SILVER is not a prerequisite. Create the
exact target plan node and campaign contracts when absent, and bind the auditor and recorder
to that node; do not fabricate a prior Lite result or reuse an unrelated node.

A clean node, successful build, completed plan status, or checkpoint is progress. Completion
requires the requested theorem's entire imported proof cone, root axiom audit, duplicate lint,
faithfulness, flattened premise and structural/data-binder census, exact theorem-face coverage,
definition independence, intended-model adapters, and goal alignment. Every proof-producing
branch must pass the same schema-v2, hashed-evidence, independent-audit, and live Lean runtime
checks in the common completion gate before reporting GOLD. Invoke the grade auditor using
the installed provider's documented path, never a guessed campaign-relative script. Persist
GOLD only through the audited recorder, under its explicit offline binding, on the exact node.

Strict proof mode forbids project axioms, `sorryAx`, `sorry`, and `admit` in the completed
proof cone. Conditional GOLD certifies only the exact frozen implication: every introduced
condition must be a direct public antecedent propagated to every consumer, with no hidden
or open residual. The source-boundary and formalization-cost exceptions retain every check
from `auto-research.md` and the shared trust gate, including exact hashed local primary text,
independent source/use-site and cost audits, and source-package closure/compatibility. A custom
source record is not an intended-model adapter. A public condition is not thereby discharged.

Keep grade separate from `result_scope`, `question_status`, and `research_value`. A supporting
or interface theorem does not settle the original question, and cannot end an authorized
question-resolution campaign while a safe in-scope goal obligation remains. Never invent
alternate Gold grades. If evidence fails, retain honest progress and continue the required
proof or audit work; selecting Heavy does not itself earn GOLD.

## Translation-only exception

An explicit statement-only request uses `formalizeproblem.md` to produce faithful statements
that elaborate with `sorry` as the only diagnostic. Preserve its back-translation, hypothesis,
intended-model, vacuity, and small-instance checks and its handling of load-bearing ambiguity,
subject to the user's existing instructions. Do not prove, decompose a proof plan, run a Gold
completion/recording process, or assign BRONZE/SILVER/GOLD to this deliverable. Report that the
statements are translated and unproved. Stop at the requested translation; this is a completed
translation task, not a completed research proof.
