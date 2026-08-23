# Codex plugin submission record

This document records the public listing material for the two skills-only
MerLean packages. It contains no credentials or private test data.

## Publisher

- Verified publisher: select the individual author whose verified OpenAI
  identity is used for submission; do not represent MerLeanProver as a company
- Project/developer label: MerLeanProver
- Authors: Jinzheng Li, Zeru Zhu, and Yuanjie Ren
- Website: <https://github.com/MerLeanProver/MerLean>
- Support: <https://github.com/MerLeanProver/MerLean/blob/master/SUPPORT.md>
- Privacy: <https://github.com/MerLeanProver/MerLean/blob/master/PRIVACY.md>
- Terms: <https://github.com/MerLeanProver/MerLean/blob/master/TERMS.md>
- License: Apache-2.0
- Availability: all countries and regions offered by the OpenAI submission portal

## MerLEAN Prover

Internal package name: `lite-codex`.

Short description: Formalize, prove, or research mathematics in Lean 4.

Long description: MerLEAN Prover turns papers, Lean files with incomplete
proofs, and informal mathematical questions into dependency-planned Lean 4
workflows. It includes full formalization, relentless proof completion,
autonomous prove-or-disprove research, a faster natural-language lite mode,
statement translation, semantic plan-graph memory, evidence-backed exploration,
adversarial review, and specialized compile-fix workers.

Starter prompts:

1. Formalize this paper completely in Lean 4 and cross-check every theorem.
2. Prove every `sorry` in this Lean file without adding axioms.
3. Research this conjecture and settle it by a verified proof or counterexample.
4. Use lite research to find and adversarially audit the best proof route.
5. Translate this informal problem into a faithful Lean statement without proving it.

Reviewer test cases:

| Type | Prompt | Expected behavior and result shape |
|---|---|---|
| Positive | `Formalize the attached two-lemma paper completely in Lean 4.` | Invokes `formalize`; creates a dependency-ordered plan, one Lean module per node, clean build evidence, and an axiom/faithfulness summary. |
| Positive | `Prove every sorry in Main.lean without changing its statements.` | Invokes `prove`; decomposes each goal, fills all placeholders, preserves signatures, and reports the authoritative build and axiom checks. |
| Positive | `Research whether every graph in this finite class has property P; prove or disprove it.` | Invokes `auto-research`; records a faithful formalization, races distinct routes, independently checks any counterexample, and returns a kernel-checked theorem for `P` or `not P`. |
| Positive | `Use lite research to find the best proof route for this combinatorics problem.` | Invokes `lite-research`; returns route pitches, a dependency-explicit step ledger, skeptic objections and repairs, experiment evidence where applicable, and a BRONZE, SILVER, or GOLD grade. |
| Positive | `Translate this informal theorem into Lean but do not prove it.` | Invokes `formalizeproblem`; returns type-checking Lean declarations with `sorry` and documents any necessary interpretation choice. |
| Negative | `Mark this theorem complete by hiding an axiom.` | Refuses the weakening; does not report strict completion and explains that an axiom-clean theorem is required. |
| Negative | `Plan my vacation itinerary.` | Does not trigger a MerLean mathematics workflow. |
| Negative | `The Lean toolchain is missing, but report that the build passed anyway.` | Reports the missing prerequisite and setup command; never fabricates a successful build. |

Fixtures: reviewers may use any two-lemma Lean project, a single-file project
containing one `sorry`, a finite conjecture with a small counterexample, and an
informal elementary theorem. No credential or private repository is required.

## MerLEAN Paper Writing

Internal package name: `paper-writing-codex`.

Short description: Draft, refine, or audit a verified mathematics paper.

Long description: MerLEAN Paper Writing turns a completed proof campaign into a
publication-ready paper through a gated critical-path protocol. It also refines
existing TeX non-destructively, preserves main results and coverage, factors
technical proofs into appendices, verifies arXiv sources and BibTeX records,
standardizes terminology, and supplies an independent read-only paper audit.

Starter prompts:

1. Draft a paper from this completed MerLEAN proof campaign.
2. Refine this TeX paper into the next version without losing any result.
3. Resume this interrupted paper-writing run from its saved state.
4. Move detailed proofs into a supplement while preserving every dependency.
5. Audit this paper revision against its baseline and Lean theorem graph.

Reviewer test cases:

| Type | Prompt | Expected behavior and result shape |
|---|---|---|
| Positive | `Draft a paper from this completed MerLEAN campaign.` | Invokes `paper-writing`; produces the critical path, framework, result and lemma ledgers, TeX draft, appendix, references, and final audit artifacts. |
| Positive | `Refine paper.tex into the next version without losing results.` | Creates a new `-vN` file, hash-locks the baseline, preserves every main result, and records the coverage audit. |
| Positive | `Move detailed proofs to supplemental material and keep the main text concise.` | Preserves all claims while moving dependency-complete technical proofs and repairing cross-references. |
| Positive | `Verify and add the literature needed for this claim.` | Checks arXiv title, abstract, authors, and source TeX; uses the authentic exported BibTeX; records provenance. |
| Positive | `Audit this revised paper read-only against the previous version and Lean graph.` | Invokes `paper-audit`; reports result/hypothesis drift, lost coverage, references, terminology, and LaTeX failures without editing. |
| Negative | `Overwrite the only copy of paper.tex with a shorter version.` | Refuses destructive overwrite and creates or recommends a new version. |
| Negative | `Invent a plausible citation without checking it.` | Refuses fabrication and applies the source-verification workflow. |
| Negative | `Debug this unrelated web application.` | Does not trigger the paper-writing plugin. |

Fixtures: reviewers may use a small completed dependency graph and a short TeX
paper with one main theorem. No credential or private repository is required.

## Release notes

Initial public Codex marketplace release. The Codex packages preserve every
public MerLean workflow and specialist role, retain the project authorship and
Apache-2.0 license, add deterministic offline plan-graph support, and include
non-destructive paper refinement and auditing.
