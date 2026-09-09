"""Make the stored graph equal the real dependency graph of all Lean files.

For each statement's `.lean` file, derive the actual edges via symbol-level usage
analysis (vendored DependencyAnalyzer — the same engine the predecessor plan store's
dependency_browser uses), map used declarations back to the statement that
defines them, and write those edges (+ declarations/imports/source lines) onto
the node. Lean-derived edges are authoritative.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import subprocess
from pathlib import Path

from ._vendor.lean_parser import DependencyAnalyzer

COMPLETED_STATES = {"completed", "completed_axiom"}


def _is_meta(node: dict) -> bool:
    """Recognize non-proof nodes without importing an online store backend."""
    return node.get("type") in {"Summary", "Note"} or node.get("kind") == "summary"


def _gold_evidence_is_current(
    node: dict, lean_file: Path, proof_status: str, plan_data: Path | None = None,
) -> bool:
    """Return whether a stored Gold audit still names the exact completed source."""
    if node.get("verification_grade") != "GOLD":
        return True
    audit = node.get("gold_audit")
    if proof_status != "completed" or not isinstance(audit, dict):
        return False
    source_hash = audit.get("lean_file_sha256")
    manifest_hash = audit.get("manifest_sha256")
    manifest_path = audit.get("manifest_path")
    evidence_files = audit.get("evidence_files")
    evidence_set_hash = audit.get("evidence_set_sha256")
    statement_id = node.get("statement_id") or node.get("id")
    if (
        audit.get("schema_version") != 2
        or audit.get("status") != "passed"
        or audit.get("auditor") != "merlean-research-grade"
        or not isinstance(statement_id, str)
        or audit.get("plan_statement_id") != statement_id
        or plan_data is None
        or audit.get("plan_data_path") != str(Path(plan_data).resolve())
    ):
        return False
    if not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (source_hash, manifest_hash)
    ):
        return False
    if not isinstance(audit.get("auditor_version"), int) or audit["auditor_version"] < 2:
        return False
    if not isinstance(manifest_path, str) or not Path(manifest_path).is_absolute():
        return False
    if not isinstance(evidence_files, list) or not isinstance(evidence_set_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_set_hash):
        return False
    try:
        actual = hashlib.sha256(lean_file.read_bytes()).hexdigest()
        manifest = Path(manifest_path)
        manifest_payload = manifest.read_bytes()
        actual_manifest = hashlib.sha256(manifest_payload).hexdigest()
        manifest_data = json.loads(manifest_payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if actual != source_hash or actual_manifest != manifest_hash:
        return False

    root = manifest.parent.resolve()

    def load_top_json(reference):
        if not isinstance(reference, dict):
            return None
        relative = reference.get("path")
        digest = reference.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        lexical = Path(relative)
        if lexical.is_absolute() or ".." in lexical.parts:
            return None
        path = (root / lexical).resolve()
        if path != root and root not in path.parents:
            return None
        try:
            payload = path.read_bytes()
            value = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if hashlib.sha256(payload).hexdigest() != digest or not isinstance(value, dict):
            return None
        return value

    target = load_top_json(manifest_data.get("target_contract"))
    kernel = load_top_json(manifest_data.get("kernel_evidence"))
    target_hash = audit.get("target_signature_sha256")
    anchor = node.get("anchor")
    if (
        manifest_data.get("schema_version") != 2
        or manifest_data.get("grade") != "GOLD"
        or node.get("evidence_closure_sha256") != manifest_hash
        or target is None
        or kernel is None
        or target.get("plan_statement_id") != statement_id
        or target.get("target_signature_hash") != target_hash
        or not isinstance(anchor, str)
        or target.get("target_signature") != anchor
        or hashlib.sha256(anchor.encode()).hexdigest() != target_hash
    ):
        return False
    matching_roots = [
        item for item in kernel.get("root_declarations", [])
        if isinstance(item, dict)
        and item.get("name") == audit.get("root_declaration")
        and item.get("signature_hash") == target_hash
        and isinstance(item.get("lean_file"), dict)
        and item["lean_file"].get("sha256") == source_hash
    ] if isinstance(kernel.get("root_declarations"), list) else []
    if len(matching_roots) != 1:
        return False
    root_ref = matching_roots[0]["lean_file"]
    root_lean_path = (root / Path(root_ref.get("path", ""))).resolve()
    if root_lean_path != lean_file.resolve() or root_ref.get("sha256") != source_hash:
        return False

    expected: dict[str, str] = {}
    visited: set[tuple[str, str]] = set()

    def walk(value, context_dir: Path = root) -> bool:
        if isinstance(value, list):
            return all(walk(item, context_dir) for item in value)
        if not isinstance(value, dict):
            return True
        relative = value.get("path")
        digest = value.get("sha256")
        if isinstance(relative, str) and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            lexical = Path(relative)
            if lexical.is_absolute() or ".." in lexical.parts:
                return False
            candidates = [(root / lexical).resolve(), (context_dir / lexical).resolve()]
            matches: list[tuple[Path, bytes]] = []
            for candidate in dict.fromkeys(candidates):
                if candidate != root and root not in candidate.parents:
                    continue
                try:
                    candidate_payload = candidate.read_bytes()
                except OSError:
                    continue
                if hashlib.sha256(candidate_payload).hexdigest() == digest:
                    matches.append((candidate, candidate_payload))
            if not matches:
                return False
            for path, payload in matches:
                canonical = path.relative_to(root).as_posix()
                if canonical in expected and expected[canonical] != digest:
                    return False
                expected[canonical] = digest
                key = (canonical, digest)
                if key not in visited:
                    visited.add(key)
                    try:
                        nested = json.loads(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        nested = None
                    if nested is not None and not walk(nested, path.parent):
                        return False
        return all(walk(item, context_dir) for item in value.values())

    if not walk(manifest_data, root):
        return False
    snapshot = [{"path": path, "sha256": expected[path]} for path in sorted(expected)]
    if evidence_files != snapshot:
        return False
    canonical_bytes = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()
    return hashlib.sha256(canonical_bytes).hexdigest() == evidence_set_hash

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

        # Identity and source location belong to the occurrence, not a registry
        # reverse lookup: namespace-local and private names can repeat legitimately.
        decls = []
        lines = []
        try:
            module_name = ".".join(f.relative_to(lib_dir).with_suffix("").parts)
        except ValueError:
            module_name = str(f.with_suffix(""))
        for record in analyzer.file_to_declaration_records.get(f.name, []):
            line = record["line"]
            lines.append(line)
            full_name = record["full_name"]
            if record["is_private"]:
                # Synthetic ownership key, not Lean's elaborated private name.
                full_name = f'{module_name}._private_.{full_name}@{line}'
            decls.append({
                "name": record["name"],
                "full_name": full_name,
                "type": record["type"],
                "line": line,
            })

        imports = re.findall(r'^import\s+(\S+)', content, re.MULTILINE)
        imported_stems = {
            imp.replace("«", "").replace("»", "").split(".")[-1]
            for imp in imports
        }
        content_clean = analyzer._remove_comments(content, for_dependency_search=True)
        self_decls = {d[0] for d in analyzer.file_to_declarations.get(f.name, [])}

        used_files: set[str] = set()
        # symbol-level usage: any other file's declaration referenced in this file
        for _key, info in analyzer.registry.items():
            if info["file"] == f.name:
                continue
            # A short identifier is meaningful as a dependency candidate only
            # when its defining module was explicitly imported.  Searching the
            # whole project registry fabricates edges whenever unrelated modules
            # reuse ordinary local/private names.
            if Path(info["file"]).stem not in imported_stems:
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

    This is primarily syntactic proof-status reconciliation. It records `proof_status` and
    never manufactures a semantic grade. A stored Gold is cleared if its audited Lean-file
    digest is missing/stale or the proof is no longer clean. Returns status/grade changes.
    """
    lib_dir = Path(lib_dir)
    changes: list[dict] = []
    for sid in graph.ids():
        node = graph.get(sid)
        if _is_meta(node):
            continue
        gold_was_present = node.get("verification_grade") == "GOLD"
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
        gold_is_current = _gold_evidence_is_current(
            node, f, new, getattr(graph, "data_dir", None),
        )
        if new != old:
            graph.set_status(sid, new)
            changes.append({"id": sid, "from": old, "to": new})
        if node.get("proof_status") != new:
            graph.update(sid, proof_status=new)
        if gold_was_present and not gold_is_current:
            graph.update(sid, verification_grade=None, gold_audit=None)
            changes.append({
                "id": sid, "from": old, "to": new,
                "grade_from": "GOLD", "grade_to": None,
                "reason": "stale_gold_audit",
            })
    return changes


def lint_declarations(graph) -> dict:
    """Reject declaration and physical-file ownership collisions.

    Distinct nodes must not claim the same declaration or resolve to the same Lean file.  The
    one-node-one-file invariant prevents one focus from overwriting another and makes proof
    status and Gold evidence attach to an unambiguous source artifact.
    """
    owners: dict[str, list[str]] = {}
    file_keys: list[tuple[str, str, str]] = []
    for sid in graph.ids():
        node = graph.get(sid)
        if _is_meta(node):
            continue
        for d in (node.get("declarations_defined") or []):
            name = (d.get("full_name") or d.get("name")) if isinstance(d, dict) else d
            if not name:
                continue
            owners.setdefault(name, [])
            if sid not in owners[name]:
                owners[name].append(sid)
        lp = (node.get("lean_path") or "").strip()
        nm = node.get("name") or ""
        if lp.endswith(".lean"):
            rel = lp
        elif lp:
            rel = f"{lp.rstrip('/')}/{_safe_filename(nm)}"
        elif nm:
            rel = _safe_filename(nm)
        else:
            rel = ""
        if rel:
            full_key = posixpath.normpath(rel).lstrip("/")
            file_keys.append((sid, full_key, posixpath.basename(full_key)))

    path_owners: dict[str, list[str]] = {}
    base_paths: dict[str, set[str]] = {}
    base_owners: dict[str, list[str]] = {}
    for sid, full_key, base in file_keys:
        path_owners.setdefault(full_key, []).append(sid)
        base_paths.setdefault(base, set()).add(full_key)
        base_owners.setdefault(base, []).append(sid)

    dups = sorted(
        ({"name": name, "nodes": sorted(sids)}
         for name, sids in owners.items() if len(sids) > 1),
        key=lambda x: x["name"],
    )
    path_dups = sorted(
        ({"path": path, "nodes": sorted(sids)}
         for path, sids in path_owners.items() if len(sids) > 1),
        key=lambda x: x["path"],
    )
    base_dups = sorted(
        ({"basename": base, "nodes": sorted(base_owners[base])}
         for base, paths in base_paths.items() if len(paths) > 1),
        key=lambda x: x["basename"],
    )
    return {
        "duplicates": dups,
        "path_duplicates": path_dups,
        "basename_duplicates": base_dups,
        "n": len(dups) + len(path_dups) + len(base_dups),
    }
