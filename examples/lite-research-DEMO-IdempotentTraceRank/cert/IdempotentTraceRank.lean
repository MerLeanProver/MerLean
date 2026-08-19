/- GOLD pass — full formalization of the campaign's main theorem (no hypothesis-mode
   shortcuts): a real idempotent matrix has trace equal to its rank.

   Faithful anchor for the dossier claim (integrality is carried by the ℕ-to-ℝ cast of
   `Matrix.rank`): for every n and A ∈ M_n(ℝ) with A² = A, tr A = rank A. -/
import Mathlib

theorem idempotent_trace_eq_rank (n : ℕ) (A : Matrix (Fin n) (Fin n) ℝ)
    (h : A * A = A) : A.trace = (A.rank : ℝ) := by
  -- Pass to the endomorphism `f = A.toLin'` of `Fin n → ℝ`; it is idempotent.
  have hidem : IsIdempotentElem (Matrix.toLin' A) := by
    have h' : Matrix.toLin' (A * A) = Matrix.toLin' A := by rw [h]
    rwa [Matrix.toLin'_mul, ← Module.End.mul_eq_comp] at h'
  -- An idempotent endomorphism is the projection onto its own range.
  have htr := (LinearMap.IsIdempotentElem.isProj_range _ hidem).trace
  -- `trace` of that projection is `finrank` of the range, which is exactly `Matrix.rank`.
  rw [Matrix.trace_toLin'_eq, Matrix.toLin'_apply'] at htr
  exact htr

#print axioms idempotent_trace_eq_rank
