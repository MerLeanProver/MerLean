/- lite-research targeted certificate (hypothesis mode) — DEMO IdempotentTraceRank.

   Certifies ledger row S12 (CB = I_r), the route's crux, from its accepted prior
   rows entering as HYPOTHESES of the statement (never as axioms):
     h3  = S3   (A = BC, the rank factorization, existence accepted on debate)
     h10 = S10  (AB = B)
     h6  = S6   (left-cancellability of B, instantiated at m = r)
   Only S11+S12's own inference — the associativity chain B(CB) = (BC)B = AB = B = B·I_r
   followed by cancellation — is formalized here.

   Triage justification (L3 gate, criterion ii): S12 is the row the entire trace chain
   S15 hangs on; an error here voids the theorem; its numerical check was sampling,
   not exhaustive. -/
import Mathlib

theorem cert_S12 (n r : ℕ)
    (A : Matrix (Fin n) (Fin n) ℝ)
    (B : Matrix (Fin n) (Fin r) ℝ)
    (C : Matrix (Fin r) (Fin n) ℝ)
    (h3 : A = B * C)
    (h10 : A * B = B)
    (h6 : ∀ X Y : Matrix (Fin r) (Fin r) ℝ, B * X = B * Y → X = Y) :
    C * B = 1 := by
  apply h6
  rw [Matrix.mul_one, ← Matrix.mul_assoc, ← h3, h10]

#print axioms cert_S12
