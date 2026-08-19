# STEP 8 — done

Final checks:
- latexmk clean: `paper.pdf`, 4 pages, 0 errors/undefined references.
- Gate artifacts present: 01-critical-path, 02-framework (compiles), 03-main-results,
  04-lemmas, 05-draft, 05.5-shrink, 06-audit (rounds 1–3, final PASS/PASS),
  07-terminology, this file. No `deleted-steps.md` (shrink deleted nothing).
- Campaign record updated: grade GOLD; both certificates + audits deposited.

Report:
- **Title**: Trace and Rank of Real Idempotent Matrices.
- **Main results as printed**: Theorem (tr A = rank A over ℝ, with integrality,
  uniqueness, and 0 ≤ tr A ≤ n) and Proposition (characteristic-free form
  tr A = (rank A)·1_F over any field).
- **References**: 0 external citations (deliberate — see 05-draft.md); 1 repository
  citation on the title page (the repo's verified origin remote).
- **Length**: 4 pages.
- **Verification**: displayed identity of the theorem kernel-checked end to end
  (standard three axioms, independent route); printed factorization route certified
  at its crux; everything else adversarially audited.
- **Open items**: formalize the printed factorization route beyond its crux;
  formalize the characteristic-free proposition over a general field.
- **Recorded deviations from the protocol** (all disclosed in the step artifacts):
  novelty gate = deliberate COLLISION (demonstration artifact, user-directed);
  reference standard not exercised (zero citations); the summary-layer audit ran as
  one combined post-Step-6 pass instead of at gate 5, then twice more after repairs.

STOP — awaiting user review before any further iteration.
