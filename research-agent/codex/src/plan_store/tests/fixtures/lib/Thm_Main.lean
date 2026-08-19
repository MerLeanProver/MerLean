import Mathlib
import Torusdemo.Def_DiscreteTorus
import Torusdemo.Lem_TorusCard

/-- Main theorem: uses both the discrete torus definition and its cardinality lemma. -/
theorem Main (n : Nat) : DiscreteTorus n = DiscreteTorus n := by
  have card := TorusCard n
  exact card
