"""Lean parser models — verbatim subset of src/autoinformalization/models.py
(only what lean_parser.py needs)."""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# Canonical regexes for statement filenames.
_STMT_PREFIXES = r"Def|Thm|Lem|Prop|Cor|Rem|Prelim"
_STMT_NUM_NAME_RE = re.compile(rf"^({_STMT_PREFIXES})_(\d+)_(.+)$")
_STMT_NAME_RE = re.compile(rf"^({_STMT_PREFIXES})_(.+)$")
_STMT_PREFIX_ONLY_RE = re.compile(rf"^({_STMT_PREFIXES})")

_TYPE_LABEL = {
    "Def": "Definition", "Thm": "Theorem", "Lem": "Lemma",
    "Prop": "Proposition", "Cor": "Corollary", "Rem": "Remark",
    "Prelim": "Preliminary",
}


@dataclass
class ParsedStatementName:
    """Pieces parsed from a statement filename stem."""
    type_prefix: str = ""
    stmt_num: str = ""
    stmt_name: str = ""
    stmt_id: str = ""
    stmt_type: str = ""
    display_name: str = ""

    @property
    def is_recognized(self) -> bool:
        return bool(self.type_prefix)


def parse_statement_filename(stem: str) -> ParsedStatementName:
    """Parse a Lean filename stem into statement parts.

    Handles both ``Prefix_Number_Name`` and ``Prefix_Name`` formats, and
    returns a stem-only result when no prefix is recognized.
    """
    stem_clean = re.sub(r"_?\([^)]*\)", "", stem)
    stem_clean = re.sub(r"_+", "_", stem_clean).strip("_")

    m = _STMT_NUM_NAME_RE.match(stem_clean)
    if m:
        prefix, num, name = m.group(1), m.group(2), m.group(3)
        return ParsedStatementName(
            type_prefix=prefix, stmt_num=num, stmt_name=name,
            stmt_id=f"{prefix}_{num}", stmt_type=_TYPE_LABEL.get(prefix, "Item"),
            display_name=name.replace("_", " "),
        )

    m = _STMT_NAME_RE.match(stem_clean)
    if m:
        prefix, name = m.group(1), m.group(2)
        return ParsedStatementName(
            type_prefix=prefix, stmt_num="", stmt_name=name,
            stmt_id=f"{prefix}_{name}", stmt_type=_TYPE_LABEL.get(prefix, "Item"),
            display_name=name.replace("_", " "),
        )

    return ParsedStatementName(stmt_id=stem, display_name=stem)


class LeanItemType(Enum):
    """Type of Lean item."""
    DEFINITION = "definition"
    THEOREM = "theorem"
    LEMMA = "lemma"
    PROPOSITION = "proposition"
    COROLLARY = "corollary"
    STRUCTURE = "structure"
    INDUCTIVE = "inductive"
    CLASS = "class"
    INSTANCE = "instance"
    AXIOM = "axiom"
    EXAMPLE = "example"
    NOTATION = "notation"
    ABBREV = "abbrev"


@dataclass
class LeanItem:
    """A Lean definition, theorem, or other declaration."""
    name: str
    item_type: LeanItemType
    signature: str
    body: Optional[str] = None
    docstring: Optional[str] = None
    attributes: list[str] = field(default_factory=list)
    source_file: Optional[Path] = None
    line_number: int = 0


@dataclass
class LeanFile:
    """A parsed Lean file with its items."""
    path: Path
    module_name: str
    imports: list[str] = field(default_factory=list)
    module_docstring: Optional[str] = None
    items: list[LeanItem] = field(default_factory=list)

    @property
    def parsed_name(self) -> ParsedStatementName:
        return parse_statement_filename(self.path.stem)

    @property
    def statement_id(self) -> Optional[str]:
        parsed = self.parsed_name
        return parsed.stmt_id if parsed.is_recognized else None

    @property
    def statement_type(self) -> Optional[str]:
        parsed = self.parsed_name
        return parsed.stmt_type if parsed.is_recognized else None
