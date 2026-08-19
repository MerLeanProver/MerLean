# lite-research — IdempotentTraceRank (DEMO campaign)

**QUESTION** (verbatim): *Let A be an n×n real matrix with A² = A. Prove or disprove:
tr(A) = rank(A).*

**Run parameters**: `ROUTES=2`, `DEBATE_ROUNDS=2`, `LIB_DIR` = an external Lean 4 + Mathlib
workspace (certs compiled by the copy-in pattern), `DATA_DIR` = this folder. This is a
deliberately small demonstration campaign: an undergraduate-textbook fact, run through the
full lite-research machinery end to end.

## Problem dossier (Phase L0.1)

- **Objects**: `A ∈ M_n(ℝ)`, `n ≥ 0` a natural number.
- **Hypotheses**: `A * A = A` (idempotence). No symmetry, no diagonalizability assumed.
- **Exact claim**: `Matrix.trace A = Matrix.rank A`, where the trace is a real number and
  the rank a natural number — so the claim includes, implicitly, that the trace of a real
  idempotent is a nonnegative integer.
- **Quantifier shape**: ∀ n, ∀ A (A² = A → tr A = rank A). No existentials.
- **Degenerate cases**: n = 0 (empty matrix: tr = 0, rank = 0 — holds, must not be
  excluded); A = 0 (tr 0 = 0 = rank 0); A = I (tr = n = rank). Non-symmetric idempotents
  (oblique projections, e.g. [[1,1],[0,0]]) are in scope — the claim is NOT restricted to
  orthogonal projections.
- **What counts as an answer**: a proof over ℝ for all n, or a single verified
  counterexample. Field caveat: over 𝔽_p the statement is false as stated (trace lands in
  the field: I₂ over 𝔽₂ has tr = 0, rank = 2), so the proof must genuinely use char 0 /
  the reals; this is a planted trap for the debate to keep routes honest.

## Direction probe (Phase L0.2) — see `scripts/probe_direction.py` / `.out`

**Verdict: SUPPORTIVE of tr = rank over ℝ ⇒ direction = PROVE.**
497 valid instances (100 orthogonal projections QQᵀ, 100 oblique B(CB)⁻¹C with
cond(CB) < 1e6, 297 perturb-and-reproject counterexample-hunt trials via the Newton map
X ↦ 3X² − 2X³ and adversarial eigen-rounding); max |tr − rank| = 1.95e-12; degenerate
cases (n=0, 0, I₅, [[1,1],[0,0]], [[0,1],[0,1]]) all exact. Caveat banked: evidence is
ℝ-only; over 𝔽_p the claim fails as stated (tr(I_p) = 0 ≠ p = rank), so routes must be
genuinely char-0.

## Phase L1 — route portfolio

Two scouts, assigned angles: A = spectral/minimal-polynomial (`pitch_A_spectral.md`),
B = rank-factorization + trace identity (`pitch_B_factorization.md`).
Kill-tests both RUN and SURVIVED (`scripts/kill_test_A_spectral.py|.out`,
`scripts/kill_test_B_cb.py|.out`; A: 400/400 rank = geo = alg with discriminating
control; B: max‖CB−I_r‖ = 3.0e-12 over 400 trials).

⇄ **Selected: favorite = B, rival = A.** Ranking per protocol: B's representation
*installs* the rank as an inner dimension (the obstruction is deleted, not moved), its
weakest step is bookkeeping rather than load-bearing theory, and it avoids route A's
alg-mult = geo-mult machinery entirely. A stays live as the rival until B's ledger
closes.

## Phase L2 — develop + adversarial debate (route B)

- **L2.1 develop**: `route_B_ledger.md`, 19 rows S0–S18 (nl-prover). Dependency audit:
  idempotence consumed in exactly one row (S9), char-0 in exactly one row (S17).
- **L2.2 attack round 1** (skeptic, full-spectrum): ⚔ **0 fatal, 1 gap, 5 nitpicks**.
  The gap is real and bibliographic: the S3 CITED pointer (H&J 2nd ed. "§0.4.6
  full-rank factorization") is contradicted — §0.4.6 is *Rank reductions*
  (Wedderburn); resolution = the prover's own pre-declared fallback (reclassify S3
  ROUTINE, embedded construction as proof — pre-audited complete by the skeptic).
  Accepted outright: S1,S2,S4,S6–S14,S16,S17. S17's reading question **resolved,
  not conceded** (the dossier text demands integrality). S8 confirmed load-bearing.
- **L2.3 experiment pass** (skeptic falsification runs, `scripts/skeptic_falsify_round1.py`):
  🔬 S3→S15 chain replayed on 400 idempotents — 0 failures; oblique-only rerun 200 —
  0 failures; S13 double sum 500 pairs incl. n=0/r=0 — 0 failures; **S9 necessity
  probe: strip A²=A ⟹ CB ≠ I_r in 200/200** (idempotence works exactly where
  claimed); char-p trap confirmed for p = 2,3,5,7; n=0 edge holds.
- **L2.4 repair round 1**: all 6 objections closed by content edits (S3 → ROUTINE with
  its embedded construction as proof; class census after repair: 16 ROUTINE /
  3 COMPUTATION / **0 CITED** — no external bibliographic trust roots).
- **L2.2 attack round 2 + composition pass** (skeptic, lens = repair-verification +
  composition): ⚔ all 6 repairs VERIFIED-FIXED; 8 NEW nitpicks (N1–N8, two of them
  regressions introduced by the repairs — the classic pattern), **zero fatal, zero
  gap** ⇒ ⚖ **LEDGER CLOSED**; none conceded-by-exhaustion. Full-DAG acyclicity
  check, header audit claims independently re-verified (idempotence in exactly S9;
  char-0/order in exactly S17), dossier match exact, referee's own 4000-instance
  numerical screen (2228 oblique) — zero violations. Nitpicks applied post-closure
  (see the ledger's sweep record).

## Phase L3 — weakest-link triage → targeted Lean

Residual-uncertainty ranking (round-2 referee): S3 > S8 > S5 > S6 > S17(d)/S18 —
formalization risk, not mathematical doubt (round 2: "mathematical uncertainty is near
zero throughout").

⛏ **Fired: 1 certificate — `cert/Cert_S12.lean`** (row S12, the crux `CB = I_r`).
Gate justification: criterion (ii) — S12 is the row the entire trace chain S15 hangs
on, an error there voids the theorem — plus (iii) — its numerical check was sampling,
not exhaustive. Hypothesis mode: priors S3 (`A = BC`), S10 (`AB = B`), S6
(cancellation) enter as hypotheses of the statement, never as axioms.
**Result: `clean` on the first attempt (27.4 s); `#print axioms cert_S12` =
`[propext, Classical.choice, Quot.sound]` exactly** (`cert/cert_S12_audit.txt`).
S12: `accepted → lean-certified`.

Not fired: S3 (ranked #1) — accepted on debate: its construction was line-audited by
the referee in both rounds; its residual uncertainty is formalization *cost* (the
`Matrix.rank` vs `finrank` encoding decision), which is exactly what the GOLD pass
absorbs, not a correctness doubt the certificate budget should chase.

## Phase L4 — assemble, grade, report

- Composition pass: folded into attack round 2 (whole-ledger DAG + interfaces +
  dossier match) — CLOSED.
- Grade at ledger close: SILVER (ledger closed on debate + numerics; the single
  triaged row lean-certified). Trust base: **empty** (zero CITED rows).
- **GOLD pass executed** (per the house default: full Lean 4 verification): the
  complete theorem formalized end to end in `cert/IdempotentTraceRank.lean` —
  status `clean`, 3 compile iterations, `#print axioms idempotent_trace_eq_rank` =
  `[propext, Classical.choice, Quot.sound]` exactly
  (`cert/idempotent_trace_eq_rank_audit.txt`). Mathlib's projection-trace theorem
  (`LinearMap.IsProj.trace`) carried it, so the anticipated costly encoding work
  (S3/S8/S5) never materialized and no textbook-boundary exception was needed.
  Honest note: the formal proof runs through the projection machinery — closer in
  spirit to the retired route A than to the winning ledger's factorization route;
  the ledger's own route remains formalized only at its crux (S12).
- **Grade: GOLD.**
- Route A (spectral): retired unexplored as the standing rival — never developed,
  never killed; its pitch and surviving kill-test remain banked (`pitch_A_spectral.md`).

**Final report: `FINAL_REPORT.md`.**
