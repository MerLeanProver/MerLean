# STEP 7 — terminology and notation table

| Concept | The one term used | Rejected synonyms |
|---|---|---|
| A with A² = A | idempotent (matrix) | projection matrix (kept only in the intro's parenthetical "matrices of (generally oblique) projections", introduced as gloss, never as the term), projector |
| dim of column space | rank | — |
| Σ diagonal entries | trace | — |
| ℤ → F, m ↦ m·1_F | the (unique ring homomorphism / canonical embedding) ι | characteristic map |
| BC with inner dim r | rank factorization | full-rank factorization (the ledger's older name — standardized here) |
| tr(MN) = tr(NM) | trace commutation | cyclicity (rejected: cyclic property is the 3-factor form) |

Notation index (collision check): M_{p×q}(F), I_r, e_j, ι, tr, col, rank — each used
for exactly one thing; no symbol reused. n (size) vs r (rank) distinct throughout.

GATE 7: grep audit over `paper.tex` — "projector": 0; "full-rank": 0; "cyclic": 1 hit
= "acyclicity" (the graph property in §Verification; unrelated word, not the trace
synonym); "projection(s)" survives only in the intro's explicit gloss. Two genuine
slips found by this audit and fixed: "the projection matrices" (intro, → "the
mathematics") and "oblique projections" (remark, → "oblique idempotents"). No
unresolved synonyms; no notation collisions.
