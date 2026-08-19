# STEP 4 — supporting-lemma selection

From the dependency cones of R1/R2, the lemmas a reader needs (the harness proved 19
rows; the paper prints 4 lemmas + the theorem — everything else is absorbed as inline
one-liners or trusted-reader steps):

| # | Paper statement (arXiv style) | Ledger rows | Proof lives |
|---|---|---|---|
| L1 | Every A ∈ M_n(F) of rank r admits A = BC with B ∈ M_{n×r}(F) of rank r, C ∈ M_{r×n}(F). | S3 (+S0) | inline (basis-and-coordinates construction, 4 lines) |
| L2 | If B ∈ M_{n×r}(F) has rank r, then BX = BY implies X = Y. | S5, S6 | inline (2 lines) |
| L3 | If A² = A and A = BC as in L1, then AB = B and CB = I_r. | S7–S12 | inline (the crux; 5 lines) |
| L4 | tr(MN) = tr(NM) for M ∈ M_{n×r}(F), N ∈ M_{r×n}(F). | S13 | inline (double sum, 2 lines) |

Absorbed without statement: S1/S2/S16 (case split — handled in the theorem's proof),
S4 (audit row — not reader-facing), S14 (tr I_r = r·1_F — folded into the theorem's
proof), S17 (the hinge — stated inside the theorem's proof as the closing sentence,
and discussed in a remark).

**Definition census for Step 5.i** (union of definition-dependencies): trace; column
space and rank; idempotent; the map ι : ℤ → F (r·1_F). Four definitions, each with a
consumer; no consumer without a definition. Notation: M_{p×q}(F), I_r, e_j.

GATE 4 ✓: the census above is exactly the Step-5 definition list; every definition has
a consumer among L1–L4/R1/R2 and vice versa.
