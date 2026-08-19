import Mathlib

/-- A discrete torus on `n` points: the product `Fin n × Fin n`. -/
def DiscreteTorus (n : Nat) : Type := Fin n × Fin n
