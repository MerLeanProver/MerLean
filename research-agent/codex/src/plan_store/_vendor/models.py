"""Statement model — verbatim subset of src/autoformalization/models.py."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StatementType(Enum):
    """Type of mathematical statement."""
    DEFINITION = "Definition"
    THEOREM = "Theorem"
    LEMMA = "Lemma"
    PROPOSITION = "Proposition"
    COROLLARY = "Corollary"
    PRELIMINARY = "Preliminary"
    REMARK = "Remark"


@dataclass
class Statement:
    """A mathematical statement extracted from a paper."""
    id: str  # e.g., "Def_ChainComplex", "Thm_KunnethFormula"
    type: StatementType
    name: str  # Descriptive name
    content: str  # The informal statement in LaTeX
    dependencies: list[str] = field(default_factory=list)  # IDs of dependencies
    proof: Optional[str] = None  # Detailed proof for theorems/lemmas/propositions
    anchor: Optional[str] = None  # Lean 4 declaration with sorry — the formalization target
    corrections: Optional[list[str]] = None  # Documented paper errors/corrections
    mathlib_types: Optional[list[str]] = None  # Mathlib types/lemmas to build on (from preparation)
    lean_path: Optional[str] = None  # Library path for the .lean file (e.g., "Valuation/Basic")
    hierarchy_level: int = 0  # 0 = original/think, +1 per rephrase generation, same for correction

    @property
    def filename(self) -> str:
        """Generate a Lean-module-safe relative filename for this statement."""
        safe_name = self.name
        for char in r'/<>:|?"*\\':
            safe_name = safe_name.replace(char, '_')
        safe_name = safe_name.replace(" ", "_").replace("-", "_")
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")
        # Lean import names split on dots, so a statement named `A.b` must
        # live at `A/b.lean`, not at a literal `A.b.lean` filename.
        return f"{safe_name.strip('_').replace('.', '/')}.lean"

    @property
    def folder(self) -> str:
        """Get the folder path for this statement. Uses lean_path if set, else flat."""
        return self.lean_path or ""


# Map type-string (as stored in JSON) -> StatementType, tolerant of case.
STATEMENT_TYPE_MAP = {t.value: t for t in StatementType}
STATEMENT_TYPE_MAP.update({t.value.lower(): t for t in StatementType})
