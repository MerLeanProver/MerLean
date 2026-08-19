# Route pitch B — rank factorization + trace identity (route-scout, angle-assigned)

**representation.** A stops being an n×n array whose rank must be computed and becomes a
*composite of two maps through an r-dimensional space*: A = B∘C with C: ℝⁿ ↠ ℝʳ
surjective, B: ℝʳ ↪ ℝⁿ injective, r = rank A **installed as the inner dimension** by the
factorization (columns of B = a basis of col A). Idempotence is then forced to say
something about the small r×r matrix CB (namely CB = I_r), and the whole problem
collapses to a trace computation in dimension r — no eigenvalue, minimal polynomial, or
diagonalizability anywhere.

**skeleton.**

1. **[CITED]** Rank factorization exists: A ∈ M_n(F) of rank r has A = BC with
   B ∈ M_{n×r}, C ∈ M_{r×n}, rank B = rank C = r. Horn & Johnson, *Matrix Analysis*
   2nd ed., §0.4.6 (full-rank factorization). Constructive: B = any basis of col(A);
   C = the coefficient columns. (r = 0: B is n×0, C is 0×n, BC = 0.)
2. **[ROUTINE]** B left-cancellable (rank B = r ⟹ ker B = 0), C right-cancellable
   (C surjective). Field only.
3. **[ROUTINE]** AB = B: every column b of B lies in col A, so b = Ay, Ab = A²y = b.
   Pure idempotence.
4. **[ROUTINE]** CB = I_r: B(CB) = (BC)B = AB = B = B·I_r, left-cancel B.
   (Backup not needing 3: BCBC = BC, cancel B left and C right.)
5. **[CITED]** tr(BC) = tr(CB) for rectangular B, C — both equal Σᵢⱼ BᵢⱼCⱼᵢ.
   Horn & Johnson §0.4.5; any commutative ring; Mathlib `Matrix.trace_mul_comm`.
6. **[COMPUTATION, char-0]** tr A = tr(BC) = tr(CB) = tr(I_r) = r·1_ℝ = r. char ℝ = 0
   identifies r·1_ℝ with the natural number r.

**weakest-step.** (a) Step 4's cancellation — airtight via injectivity of x ↦ Bx (NOT
via (BᵀB)⁻¹Bᵀ, which is ℝ-specific); the fragility is bookkeeping: step 1 must deliver
rank B = r AND rank C = r, and the AB = B route only consumes B's half — demote C's full
rank to a remark. (b) Step 6 is the ONLY char-0 use: steps 1–5 hold over any field
(step 5 over any commutative ring), so the route proves the characteristic-free
tr A = (rank A)·1_F for every field, and the 𝔽_p trap is diagnosed exactly (ℕ → 𝔽_p not
injective) rather than dodged. (c) r = 0 / n = 0 empty-matrix conventions stated once —
where a Lean pass would burn its time.

**kill-test — RUN, PASSED.** 400 trials, n ≤ 8, all 0 ≤ r ≤ n: oblique idempotents
A = X(YX)⁻¹Y; independent rank factorization from pivoted QR; results
max‖BC−A‖ = 1.1e−13, max‖CB−I_r‖ = 3.0e−12, max‖AB−B‖ = 1.5e−11, max|tr−r| = 2.0e−12.
Reproduction script: `scripts/kill_test_B_cb.py`.

**viability.** Viable — five short steps, one cited existence theorem, no spectral
machinery, oblique idempotents free of charge, char-0 isolated to one final equality.
