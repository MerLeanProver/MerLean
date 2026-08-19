# DEMO campaign — `/lite-research` on an undergraduate linear-algebra fact

A deliberately small, complete, end-to-end record of the **research agent's lite mode**
(Claude Code version), on a textbook question:

> Let A be an n×n real matrix with A² = A. Prove or disprove: tr(A) = rank(A).

**Outcome: PROVED, grade GOLD** — full end-to-end Lean 4 formalization — in one debate cycle — and the machinery still earned
its keep on a textbook fact: the skeptic caught a genuinely wrong textbook citation
(round 1), the repair introduced two bookkeeping regressions that round 2 caught (the
classic pattern), and the crux step carries a kernel-checked certificate.

## Read it in this order

1. [`ledger.md`](ledger.md) — the campaign master log: dossier, direction probe,
   route portfolio, debate rounds, triage, grade.
2. [`pitch_A_spectral.md`](pitch_A_spectral.md) /
   [`pitch_B_factorization.md`](pitch_B_factorization.md) — the two route-scout
   pitches (assigned angles; B selected, A retired as rival).
3. [`route_B_ledger.md`](route_B_ledger.md) — the proof as a 19-row step ledger
   (every row: self-contained claim, uses, class, justification), with the repair
   record and the post-closure nitpick sweep.
4. [`FINAL_REPORT.md`](FINAL_REPORT.md) — the graded resolution.
5. [`cert/Cert_S12.lean`](cert/Cert_S12.lean) + [`cert/cert_S12_audit.txt`](cert/cert_S12_audit.txt)
   — the targeted lite-mode certificate at the crux (hypothesis mode), and
   [`cert/IdempotentTraceRank.lean`](cert/IdempotentTraceRank.lean) +
   [`cert/idempotent_trace_eq_rank_audit.txt`](cert/idempotent_trace_eq_rank_audit.txt)
   — the GOLD pass: the full theorem kernel-checked end to end, axioms exactly
   `[propext, Classical.choice, Quot.sound]`.
6. [`scripts/`](scripts) — every numerical experiment with outputs (direction probe,
   two kill-tests, skeptic falsification runs).
7. [`paper/`](paper) — the paper-writing agent's 8-step run over this campaign
   (see the top-level `paper-writing-agent/`).

## What this demo is and is not

It **is** a faithful, complete trace of the protocol at its smallest useful scale
(2 routes, 2 debate rounds, 1 targeted certificate + 1 full formalization). It is **not** a research result — the
theorem is standard undergraduate material, and the paper produced from it is a
demonstration artifact (its novelty gate records KNOWN/textbook, by design).
