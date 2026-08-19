"""statements.json interop: import an existing plan into the graph and export
the graph back to the statements.json / progress.json shapes.

Used for verification (round-trip fidelity) and to migrate existing projects.
"""

import json
from pathlib import Path

# Fields always emitted; optional ones only when set (matches statements.json).
_REQUIRED = ["type", "name", "content", "dependencies", "hierarchy_level"]
_OPTIONAL = ["proof", "anchor", "mathlib_types", "lean_path", "corrections"]


def import_statements_json(graph, path) -> int:
    """Load statements.json (+ sibling progress/corrections) into the graph."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    stmts = data.get("statements", data) if isinstance(data, dict) else data

    completed: set[str] = set()
    pf = path.parent / "progress.json"
    if pf.exists():
        completed = set(json.loads(pf.read_text(encoding="utf-8")).get("completed", []))

    corrections: dict = {}
    cf = path.parent / "corrections.json"
    if cf.exists():
        corrections = json.loads(cf.read_text(encoding="utf-8"))

    dni_by_sid: dict[str, list] = {}
    if isinstance(data, dict):
        for e in data.get("do_not_import", []) or []:
            dni_by_sid.setdefault(e.get("statement_id"), []).append(e.get("import_path"))

    n = 0
    for s in stmts:
        sid = s["id"]
        node = dict(s)
        node["status"] = "completed" if sid in completed else "pending"
        if sid in corrections:
            node["corrections"] = corrections[sid]
        if sid in dni_by_sid:
            node["do_not_import"] = dni_by_sid[sid]
        graph.add(node)
        n += 1
    return n


def export_statements_json(graph) -> tuple[dict, dict]:
    """Return (statements_json_dict, progress_json_dict) — delegates to the store."""
    return graph.export()
