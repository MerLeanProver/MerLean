"""Make the stored graph equal the real dependency graph of all Lean files.

For each statement's `.lean` file, derive the actual edges via symbol-level usage
analysis (vendored DependencyAnalyzer — the same engine the predecessor plan store's
dependency_browser uses), map used declarations back to the statement that
defines them, and write those edges (+ declarations/imports/source lines) onto
the node. Lean-derived edges are authoritative.
"""

import re
import subprocess
from pathlib import Path

from ._vendor.lean_parser import DependencyAnalyzer

# Same keyword filter DependencyAnalyzer.find_declaration_dependencies uses, to
# avoid treating common tactics/combinators as cross-file dependencies.
LEAN_KEYWORDS = {
    'have', 'let', 'show', 'suffices', 'assume', 'this', 'that',
    'apply', 'exact', 'intro', 'intros', 'cases', 'induction',
    'simp', 'rfl', 'trivial', 'sorry', 'ring', 'omega', 'decide',
    'constructor', 'ext', 'funext', 'congr', 'subst', 'rw', 'rewrite',
    'calc', 'obtain', 'rcases', 'rintro', 'push_neg', 'contrapose',
    'by_contra', 'exfalso', 'absurd', 'native_decide',
    'zero', 'one', 'id', 'comp', 'map', 'pure', 'bind', 'seq',
    'add', 'mul', 'neg', 'sub', 'div', 'inv', 'pow', 'smul', 'vadd',
    'on', 'of', 'in', 'is', 'at', 'to', 'for', 'or', 'and', 'not',
    'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'mk', 'val', 'get', 'set',
}


def _safe_filename(name: str) -> str:
    """Statement.filename logic (kept in sync with the vendored Statement)."""
    safe = name or ""
    for ch in r'/<>:|?"*\\':
        safe = safe.replace(ch, "_")
    safe = safe.replace(" ", "_").replace("-", "_")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return f"{safe.strip('_').replace('.', '/')}.lean"


def lean_file_for(node: dict, lib_dir: Path) -> Path:
    """Resolve a node's on-disk .lean path from `lean_path` + `name`."""
    lp = node.get("lean_path")
    if lp and str(lp).endswith(".lean"):
        return Path(lib_dir) / lp
    fname = _safe_filename(node.get("name", ""))
    return Path(lib_dir) / lp / fname if lp else Path(lib_dir) / fname


def sync_edges_from_lean(graph, lib_dir) -> dict:
    """Rewrite each node's dependencies (+ Lean detail) from the real .lean files.

    Returns a summary dict: {statement_id: {"dependencies": [...], "file": str, "found": bool}}.
    """
    lib_dir = Path(lib_dir)
    analyzer = DependencyAnalyzer(lib_dir)
    analyzer.build_registry(lib_dir)

    from .store import _is_meta
    sids = [sid for sid in graph.ids() if not _is_meta(graph.get(sid))]

    # filename -> statement_id (only files that belong to a statement)
    fn2sid: dict[str, str] = {}
    node_file: dict[str, Path] = {}
    for sid in sids:
        f = lean_file_for(graph.get(sid), lib_dir)
        node_file[sid] = f
        fn2sid[f.name] = sid

    summary: dict[str, dict] = {}
    for sid in sids:
        f = node_file[sid]
        if not f.exists():
            summary[sid] = {"file": str(f), "found": False, "dependencies": graph.get(sid).get("dependencies", [])}
            continue

        content = f.read_text(encoding="utf-8")

        # Declarations from the robust line-anchored extractor (the same one that
        # builds the registry / edges); line numbers via an anchored search.
        decls = []
        lines = []
        for dname, dtype in analyzer.file_to_declarations.get(f.name, []):
            m = re.search(
                rf'(?m)^\s*(?:(?:noncomputable|private|protected|partial)\s+)*'
                rf'{re.escape(dtype)}\s+{re.escape(dname)}\b',
                content,
            )
            line = content[:m.start()].count("\n") + 1 if m else None
            if line is not None:
                lines.append(line)
            decls.append({"name": dname, "type": dtype, "line": line})

        imports = re.findall(r'^import\s+(\S+)', content, re.MULTILINE)
        content_clean = analyzer._remove_comments(content, for_dependency_search=True)
        self_decls = {d[0] for d in analyzer.file_to_declarations.get(f.name, [])}

        used_files: set[str] = set()
        # symbol-level usage: any other file's declaration referenced in this file
        for _key, info in analyzer.registry.items():
            if info["file"] == f.name:
                continue
            short = info["short_name"]
            if short in self_decls or len(short) <= 2:
                continue
            if short.lower() in LEAN_KEYWORDS or short in LEAN_KEYWORDS:
                continue
            if re.search(rf'(?<![.\w]){re.escape(short)}\b', content_clean):
                used_files.add(info["file"])
        # explicit imports of sibling statement files
        for imp in imports:
            stem = imp.replace("«", "").replace("»", "").split(".")[-1]
            for fn in analyzer.file_to_declarations:
                if Path(fn).stem == stem:
                    used_files.add(fn)

        dep_sids = sorted({fn2sid[fn] for fn in used_files
                           if fn in fn2sid and fn2sid[fn] != sid})

        graph.update(
            sid,
            dependencies=dep_sids,
            declarations_defined=decls,
            imports=imports,
            source_start=min(lines) if lines else None,
            source_end=max(lines) if lines else None,
        )
        summary[sid] = {"file": str(f), "found": True, "dependencies": dep_sids}

    graph.recompute_dependents()
    return summary


def _strip_comments(content: str) -> str:
    """Drop Lean block comments `/- … -/` (incl. doc comments `/-- … -/`) and `--` line comments,
    so a `sorry` inside a docstring isn't mistaken for an unfilled proof."""
    content = re.sub(r"/-.*?-/", " ", content, flags=re.DOTALL)
    content = re.sub(r"--[^\n]*", " ", content)
    return content


def _module_name(node: dict) -> str | None:
    lp = node.get("lean_path")
    if not lp or not str(lp).endswith(".lean"):
        return None
    return str(lp)[:-5].replace("/", ".").replace("\\", ".")


def _module_builds(node: dict, lib_dir: Path) -> bool:
    """Run `lake build <module>` in the lakefile dir; True iff it returns 0 (compiles, no errors)."""
    mod = _module_name(node)
    if not mod:
        return False
    try:
        r = subprocess.run(["lake", "build", mod], cwd=str(lib_dir),
                           capture_output=True, text=True, timeout=600)
        return r.returncode == 0
    except Exception:
        return False


def reconcile_status_from_lean(graph, lib_dir, build: bool = False) -> list[dict]:
    """Re-derive each node's `status` from its `.lean` file (the ground truth), healing drift in
    the Mem0-g store.

    Rules (per non-meta node):
      * file has no `sorry`/`admit` (comments stripped)  → `completed`
        (`completed_axiom` if the file also declares an `axiom`; with `build=True`, additionally
        require `lake build <module>` to succeed);
      * file still has a placeholder → if currently marked done, downgrade to `in_progress`
        (a false-complete), else leave the workflow state (`pending`/`in_progress`) untouched;
      * no file yet (a planned, not-yet-scaffolded node) → leave `pending`; downgrade a stray
        `completed`/`completed_axiom` back to `pending`.

    Only writes when the status actually changes. Returns the list of `{id, from, to}` changes.
    """
    from .store import COMPLETED_STATES, _is_meta
    lib_dir = Path(lib_dir)
    changes: list[dict] = []
    for sid in graph.ids():
        node = graph.get(sid)
        if _is_meta(node):
            continue
        old = node.get("status")
        f = lean_file_for(node, lib_dir)
        if not f.exists():
            new = "pending" if old in COMPLETED_STATES else old
        else:
            body = _strip_comments(f.read_text(encoding="utf-8"))
            has_hole = re.search(r"\b(?:sorry|admit)\b", body) is not None
            has_axiom = re.search(r"(?m)^\s*axiom\s", body) is not None
            if has_hole:
                new = "in_progress" if old in COMPLETED_STATES else old
            elif build and not _module_builds(node, lib_dir):
                new = "in_progress" if old in COMPLETED_STATES else old
            else:
                new = "completed_axiom" if has_axiom else "completed"
        if new != old:
            graph.set_status(sid, new)
            changes.append({"id": sid, "from": old, "to": new})
    return changes


def lint_declarations(graph) -> dict:
    """Flag top-level declaration names defined by MORE THAN ONE node.

    A name owned by two nodes is ambiguous in any file that imports both (Lean keeps both
    declarations; an unqualified reference then fails to resolve) — a latent build break and a
    faithfulness hazard (a proof may silently bind the wrong one). Uses `declarations_defined`,
    which `sync_edges_from_lean` populates, so run `sync-lean` first for accurate results.

    Returns `{"duplicates": [{"name", "nodes": [sid, ...]}], "n": int}` (empty `duplicates` is clean).
    """
    from .store import _is_meta
    owners: dict[str, list[str]] = {}
    for sid in graph.ids():
        node = graph.get(sid)
        if _is_meta(node):
            continue
        for d in (node.get("declarations_defined") or []):
            name = d.get("name") if isinstance(d, dict) else d
            if not name:
                continue
            owners.setdefault(name, [])
            if sid not in owners[name]:
                owners[name].append(sid)
    dups = sorted(
        ({"name": name, "nodes": sorted(sids)} for name, sids in owners.items() if len(sids) > 1),
        key=lambda x: x["name"],
    )
    return {"duplicates": dups, "n": len(dups)}
