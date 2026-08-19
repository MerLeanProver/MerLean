# FINAL REPORT — lite-research DEMO: IdempotentTraceRank

**Question.** Let A be an n×n real matrix with A² = A. Prove or disprove: tr(A) = rank(A).

**Resolution: PROVED — grade GOLD** (full end-to-end Lean 4 formalization; see below).

## The theorem (natural language)

For every integer n ≥ 0 and every real n×n matrix A with A² = A, the trace of A equals
its rank: tr(A) = ι(rank A), where ι : ℤ ↪ ℝ is the canonical embedding. In particular
tr(A) is a nonnegative integer, namely rank(A), and 0 ≤ tr(A) ≤ n. No symmetry,
orthogonality, or diagonalizability is assumed; oblique idempotents are covered; the
cases n = 0, A = 0, A = I are covered without case-analysis exceptions.

## The winning representation and why it reduced complexity

**Rank factorization** (route B): A becomes a composite B∘C through ℝʳ, with
r = rank A *installed as the inner dimension* by construction (columns of B = a basis
of col A) rather than extracted by an argument. Idempotence then forces the small r×r
matrix CB to be I_r, and the theorem collapses to the trace computation
tr A = tr(BC) = tr(CB) = tr(I_r) = r·1_ℝ. The rival representation (route A, spectral:
diagonalizability from μ_A | X(X−1)) was retired undeveloped: it also survived its
kill-test, but it moves the obstruction into alg-mult = geo-mult machinery, where
route B deletes it.

## The proof: `route_B_ledger.md` — 19 rows, all closed

- Classes: 16 ROUTINE / 3 COMPUTATION / **0 CITED** — the trust base is **empty**
  (no external bibliographic roots; standard finite-dimensional linear algebra is
  invoked as ROUTINE).
- Structural audit (referee-verified twice): idempotence A² = A is consumed in
  **exactly one row** (S9: A acts as the identity on col A); characteristic 0 — and,
  for the order bound, the ordered-field structure of ℝ — in **exactly one row**
  (S17). Everything else is field-free linear algebra, which is why S16's
  characteristic-free form tr A = (rank A)·1_F holds over every field, while the
  integer claim rightly dies over 𝔽_p (tr I_p = 0 ≠ p = rank I_p).
- Status: every row `accepted`; S12 `lean-certified`.

## Debate and experiments

- Attack round 1 (full-spectrum): 0 fatal, **1 gap** — the S3 citation pointer was
  affirmatively contradicted (Horn & Johnson 2nd ed. §0.4.6 is *Rank reductions*, not
  full-rank factorization) — plus 5 nitpicks. Repaired: S3 reclassified ROUTINE with
  its embedded basis-and-coordinates construction as the proof (pre-audited by the
  skeptic, line by line).
- Attack round 2 (repair-verification + composition): all repairs VERIFIED-FIXED;
  8 new nitpicks (two of them regressions introduced by the repairs), zero fatal/gap
  ⇒ **CLOSED**, nothing conceded by exhaustion. Applied post-closure.
- Experiments (all in `scripts/`): direction probe (497 instances, SUPPORTIVE);
  route kill-tests A and B (both survived; B: max‖CB−I_r‖ = 3.0e-12 over 400 trials);
  skeptic falsification runs — S3→S15 chain replay 400/400, oblique-only 200/200,
  S13 double-sum 500/500, **idempotence-necessity probe: drop A² = A and CB ≠ I_r in
  200/200**, char-p trap confirmed for p = 2, 3, 5, 7; round-2 referee screen: 4000
  instances (2228 oblique), zero violations. Numerics kill and localize; they never
  prove — every acceptance above rests on the debate, not the samples.

## The certificate

`cert/Cert_S12.lean` — hypothesis-mode certificate of the crux row S12 (CB = I_r):
priors S3 (A = BC), S10 (AB = B), S6 (left-cancellability) enter as hypotheses of the
statement; only S12's own inference is formalized. Compiled clean on the first attempt
(27.4 s) against a Lean 4 + Mathlib workspace; `#print axioms cert_S12 =
[propext, Classical.choice, Quot.sound]` exactly (`cert/cert_S12_audit.txt`).
Triage gate: criteria (ii) (crux — an error voids the theorem) and (iii) (numerical
check was sampling). Ranked-higher S3 was deliberately left accepted-on-debate: its
residual is formalization *cost* (encoding decisions), not correctness doubt.

## Trust base

Empty. Zero CITED rows — no "modulo cited results" annotation.

## Grade: GOLD

The ledger closed at SILVER (debate + numerics + the crux certificate); the GOLD pass
then formalized the FULL theorem end to end — `cert/IdempotentTraceRank.lean`,
statement byte-identical to the faithful anchor, `clean` in 3 compile iterations,
axioms exactly `[propext, Classical.choice, Quot.sound]`
(`cert/idempotent_trace_eq_rank_audit.txt`).

Two honest notes. (1) The formal proof is glue over Mathlib's existing projection
machinery (`LinearMap.IsProj.trace`: trace of a projection = finrank of its range) —
structurally the retired route A's spectral viewpoint, not the winning ledger's
factorization route; the ledger's own route is formalized only at its crux
(`Cert_S12.lean`). Discovery and certification legitimately took different roads, and
both are recorded. (2) The anticipated costly encodings (S3's rank factorization, S8,
S5) never materialized: `Matrix.rank` is definitionally the finrank of the range of
`mulVecLin`, which is exactly what Mathlib's theorem produces.
