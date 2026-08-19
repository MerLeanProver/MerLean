# STEP 1 — the critical path

**Graph source** (recorded per protocol): this is a lite campaign — the dependency
structure is derived from the closed step ledger (`../route_B_ledger.md`, 19 rows, uses
lists verified acyclic by the round-2 composition pass) + the certificate's audit output
(`../cert/cert_S12_audit.txt`). No Mem0-g store was used in this bare run.

## Theorem-grade DAG (terminal: S18)

```
S0 (conventions/col-span/rank-range)
 ├─ S1 (case r = 0) ──────────────────────────────┐
 ├─ S2 (case split r ≥ 1)                          │
 ├─ S3 (rank factorization A = BC, rank B = r)     │
 │    ├─ S5 → S6 (left-cancellation of B)          │
 │    ├─ S7 → S8 (col A = col B)                   │
 │    └─ S10 (AB = B)  [uses S8, S9]               │
 ├─ S9 (A = id on col A — THE idempotence row)     │
 ├─ S11 (B(CB) = B·I_r) → S12 (CB = I_r) ★cert     │
 ├─ S13 (tr(BC) = tr(CB)), S14 (tr I_r = ι(r))     │
 ├─ S15 (case r ≥ 1: tr A = ι(r))                  │
 ├─ S16 (all r: tr A = ι(rank A)) ←────────────────┘
 └─ S17 (char-0/ordered-field hinge) → S18 (THEOREM)
```

Defense artifacts (not theorem-grade, listed separately for §Verification): S4 (audit
row, orphaned in the DAG by design), the kill-tests, falsification scripts, and the
direction probe.

## THE critical path

S0 → S3 → S10 → S11 → S12★ → S15 → S16 → S17 → S18 (depth 8; the longest chain to the
terminal; S12 is the certified crux).

## Terminal node

- **S18** — for every integer n ≥ 0 and A ∈ M_n(ℝ) with A² = A: tr A = ι(rank A);
  tr A is a nonnegative integer, namely rank A; 0 ≤ tr A ≤ n.
- **Grade**: debate-accepted (round-2 CLOSED), with the crux S12 kernel-certified in
  hypothesis mode (axioms exactly `[propext, Classical.choice, Quot.sound]`). In the
  dossier's three-tier language: *named-hypothesis tier* for the ledger as a whole
  (hypotheses = the accepted prior rows), kernel-checked at the certified row.
- **Hypothesis surface**: `A ∈ M_n(ℝ)`, `A² = A` — nothing else (no symmetry, no
  diagonalizability); the ordered-field structure of ℝ is consumed at S17 only.

GATE 1 ✓: the terminal's grade and hypothesis surface verified against
`cert/Cert_S12.lean` + `cert/cert_S12_audit.txt` (the files, not the ledger prose):
the cert's hypotheses are exactly rows S3/S10/S6, its axiom line is the standard three,
and no other row claims a certificate.
