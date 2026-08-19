"""Prove-mode seeding: turn a Lean file's `sorry`/`admit` placeholders into plan
statements so the same compile-fix loop can fill them with real proofs.

Success in prove mode is mechanical: the declaration's signature is preserved and the
proof closure has no residual `sorry`/`admit`/`axiom` (not the full paper-faithfulness
check, which would also flag legitimate one-line wrapper proofs).
"""

import re
from pathlib import Path

from ._vendor.lean_parser import DependencyAnalyzer

_KIND_TO_TYPE = {
    "theorem": "Theorem", "lemma": "Lemma", "proposition": "Proposition",
    "corollary": "Corollary", "def": "Definition", "abbrev": "Definition",
    "instance": "Definition", "example": "Theorem",
}

_SORRY_RE = re.compile(r'(?<![\w.])(sorry|admit)\b')


def extract_sorry_declarations(lean_file) -> list[dict]:
    """Return [{name, kind, signature}] for each top-level declaration in `lean_file`
    whose body contains `sorry`/`admit`."""
    lean_file = Path(lean_file)
    text = lean_file.read_text(encoding="utf-8")
    da = DependencyAnalyzer(lean_file.parent)
    clean = da._remove_comments(text, for_dependency_search=True)

    out, seen = [], set()
    for name, kind, _ns in da._extract_declarations(text):
        if name in seen:
            continue
        body = da._extract_declaration_body(clean, name, kind)
        if body and _SORRY_RE.search(body):
            seen.add(name)
            out.append({"name": name, "kind": kind, "signature": _signature(text, name, kind)})
    return out


def _signature(text: str, name: str, kind: str) -> str:
    """The declaration header (up to `:=` / `where`) — the anchor the proof must preserve."""
    m = re.search(
        rf'(?ms)^([ \t]*(?:@\[[^\]]*\]\s*)?'
        rf'(?:(?:noncomputable|private|protected|partial)\s+)*'
        rf'{kind}\s+{re.escape(name)}\b.*?)(?::=|\bwhere\b)',
        text,
    )
    return m.group(1).strip() if m else f"{kind} {name}"


def seed_sorry_file(graph, lean_file, lib_dir) -> dict | None:
    """Add ONE plan statement covering all of `lean_file`'s sorry'd declarations
    (one statement = one file). Returns the node, or None if there are no sorries."""
    lean_file, lib_dir = Path(lean_file), Path(lib_dir)
    decls = extract_sorry_declarations(lean_file)
    if not decls:
        return None
    try:
        rel = lean_file.resolve().relative_to(lib_dir.resolve()).as_posix()
    except ValueError:
        rel = lean_file.name
    stem = lean_file.stem
    node = {
        "id": f"Prove_{stem}",
        "type": _KIND_TO_TYPE.get(decls[0]["kind"], "Theorem"),
        "name": stem,
        "content": (
            f"Replace the `sorry`/`admit` placeholders in {rel} with real proofs, "
            f"preserving each signature. Declarations to prove: "
            + "; ".join(d["name"] for d in decls) + "."
        ),
        "anchor": "\n\n".join(d["signature"] for d in decls),
        "lean_path": rel,
        "dependencies": [],
        "status": "pending",
        "mode": "prove",
    }
    return graph.add(node)
