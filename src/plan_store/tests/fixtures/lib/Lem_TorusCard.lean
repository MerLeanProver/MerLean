import Mathlib
import Torusdemo.Def_DiscreteTorus

/-- The discrete torus has `n^2` elements. -/
lemma TorusCard (n : Nat) : DiscreteTorus n = DiscreteTorus n := by
  rfl
