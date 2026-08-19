# Route pitch A — spectral / minimal-polynomial angle (route-scout, angle-assigned)

**representation.** A becomes a *diagonalizable operator on ℝⁿ with spectrum in {0,1}*:
ℝⁿ = E₁ ⊕ E₀ (the two eigenspaces). The obstruction — computing the rank of an arbitrary
non-symmetric idempotent — shrinks because rank stops being a column-space computation and
becomes the single integer r = dim E₁, which simultaneously reads off as the multiplicity
of eigenvalue 1 in the characteristic polynomial; the oblique/non-normal character of A
affects only the *angle* between E₁ and E₀, never their dimensions.

**skeleton.**

1. **im(A) = ker(A − I) = E₁.** ROUTINE. ⊆: y = Ax ⟹ Ay = y. ⊇: Ax = x ⟹ x ∈ im(A).
   Uses only A² = A. (Numerics: (A−I)A = 0 to 1e-16 on 400 samples.)
2. **Every eigenvalue λ satisfies λ² = λ, so Spec(A) ⊆ {0,1}.** ROUTINE.
3. **A is diagonalizable over ℝ.** CITED — endomorphism diagonalizable iff minimal
   polynomial splits into pairwise distinct linear factors; μ_A | X(X−1). *Elementary
   substitute*: x = Ax + (x − Ax) with A(x − Ax) = 0, plus E₁ ∩ E₀ = 0, gives
   ℝⁿ = E₁ ⊕ E₀ in three lines, degrading gracefully at n = 0.
4. **char poly = Xⁿ⁻ʳ(X − 1)ʳ, r = dim E₁.** ROUTINE given 3 (alg mult = geo mult).
5. **tr(A) = r·1_ℝ.** CITED — trace = sum of char-poly roots with multiplicity (Vieta).
   Deliberately routed through the char poly, NOT through tr(P⁻¹AP) = tr(A), to stay
   disjoint from route B's tr(XY) = tr(YX) tool.
6. **rank(A) = r and r·1_ℝ = r.** ROUTINE + the char-0 hinge: injectivity of ℤ → ℝ.
   Steps 1–5 are valid verbatim over 𝔽_p; only this step breaks there. Route needs
   char 0 only; no ordering/completeness/inner product.

**weakest-step.** Step 3 — but the soft spots are (i) n = 0 (minimal polynomial = 1;
convention-dependent — fix: make the elementary splitting 3′ primary, the citation a
remark), and (ii) step 4's alg = geo, where diagonalizability's weight is actually spent
(Spec ⊆ {0,1} alone admits [[1,1],[0,1]]-shaped non-idempotents). Secondary: step 5's
Vieta needs the char poly to split over ℝ (it does: roots 0,1 — state it).

**kill-test (≤5 min).** On random oblique idempotents A = V(WᵀV)⁻¹Wᵀ (incl. r=0, r=n,
ill-conditioned WᵀV): assert rank(A) = geo mult of 1 = alg mult of 1 and (A−I)A ≈ 0.
Any sample with alg > geo kills the route. Control: [[1,1],[0,1]] must FAIL alg=geo.
Symbolic leg: over GF(p) on I_p, steps 1–5 pass, step 6 fails (verified p = 2,3,5) —
the char-0 dependency is isolated to one row.

**viability.** Viable — three elementary lemmas + one standard citation (itself
replaceable), uniform over n = 0, A = 0, A = I, oblique idempotents.
