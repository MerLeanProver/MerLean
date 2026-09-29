"""Deterministic evidence and lifecycle checks for research-to-paper synthesis.

This module does not extract mathematics, prove claims, authenticate a human, or
certify novelty.  It binds attributable records to the exact material reviewed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import unquote, urlsplit

from .tex_inventory import TEX_SOURCE_SUFFIXES, local_tex_dependencies
from .versioning import sha256_file


SYNTHESIS_GATES = ["intake", "inventory", "candidates", "selection", "assessment", "decision"]
GATES = SYNTHESIS_GATES
ARTIFACTS = ["input-inventory.json", "claim-ledger.json", "candidate-prospectuses.json",
             "selected-contribution.json", "reviews.json", "references-registry.json", "decision.json"]
PROOF_STATUSES = {"conjecture", "numerical", "proof_available", "independently_reviewed", "formally_verified"}
OUTCOMES = {"ready_to_draft", "focused_research_needed", "review_or_verification_needed", "no_compelling_paper"}
NOTE_SUFFIXES = {".tex", ".md", ".markdown"}
SUPPORT_SUFFIXES = NOTE_SUFFIXES | TEX_SOURCE_SUFFIXES | {".lean", ".json", ".yaml", ".yml", ".csv", ".tsv", ".txt", ".bib"}


def _safe_path(path: Path) -> Path:
    """Reject aliases before resolving them, including Windows junction parents."""
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    for component in [*reversed(path.parents), path]:
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                or getattr(component, "is_junction", lambda: False)()):
            raise ValueError(f"symlink, junction, or reparse path is unsupported: {component}")
    return path.resolve()


def _assert_mutable_run(work: Path) -> None:
    """Do not write through links into source notes or another user's files."""
    _safe_path(work)
    for path in [work, *work.rglob("*")]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(path, "is_junction", lambda: False)():
            raise ValueError(f"linked synthesis path is not a writable run artifact: {path}")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError(f"hard-linked synthesis file is not a writable run artifact: {path}")


def _write_text(path: Path, text: str) -> None:
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"refusing to overwrite a linked or non-regular artifact: {path}")
    # A same-directory atomic replacement cannot truncate a raced hardlink target.
    descriptor, name = tempfile.mkstemp(prefix=".synthesis-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)  # Only this exclusive temporary file, never source/run data.


def write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict:
    try:
        path = _safe_path(path)
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _record(path: Path) -> dict:
    value = _read(path)
    if value.get("schema_version") != 1:
        raise ValueError(f"unsupported or missing schema_version: {path}")
    return value


def _state(path: Path) -> dict:
    state = _record(path)
    if state.get("mode") != "synthesize":
        raise ValueError("operation requires a synthesis state")
    if Path(_text(state.get("work_dir"), "state work_dir")).resolve() != path.resolve().parent:
        raise ValueError("synthesis state must remain in its recorded work directory")
    if not isinstance(state.get("gates"), dict) or set(state["gates"]) != set(GATES):
        raise ValueError("synthesis state has an invalid gate map")
    if any(not isinstance(row, dict) or row.get("status") not in {"pending", "pass", "fail", "not_applicable"}
           for row in state["gates"].values()):
        raise ValueError("synthesis state has malformed gate records")
    return state


def _text(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be nonempty text")
    return value


def _strings(value: Any, description: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{description} must be a list of nonempty strings")
    return value


def _rows(value: dict, key: str) -> list[dict]:
    rows = value.get(key)
    if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
        raise ValueError(f"{key} must be a list of objects")
    return rows


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve(work: Path, value: str) -> Path:
    path = Path(_text(value, "evidence path")).expanduser()
    return _safe_path(path if path.is_absolute() else work / path)


def _linked_paths(path: Path, master_dir: Path) -> list[Path]:
    if path.suffix.lower() not in NOTE_SUFFIXES | TEX_SOURCE_SUFFIXES:
        return []
    text = path.read_text(encoding="utf-8-sig")
    targets: list[str] = []
    result = []
    if path.suffix.lower() in TEX_SOURCE_SUFFIXES:
        result.extend(_safe_path(child) for _, child, _ in local_tex_dependencies(path, master_dir))
        text = re.sub(r"(?<!\\)%[^\n]*", "", text)
        targets.extend(re.findall(r"\\(?:href|url)\{([^{}]+)\}", text))
    else:
        # Ignore fenced examples; inline and reference-style local links are explicit inputs.
        text = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
        targets.extend(re.findall(r"(?<!!)\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text))
        targets.extend(re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", text))
    for target in targets:
        target = target.strip("<>")
        parts = urlsplit(target)
        if target.startswith("#") or (parts.scheme and not re.match(r"^[A-Za-z]:[\\/]", target)):
            continue
        raw = unquote(target.split("#", 1)[0].split("?", 1)[0])
        child = Path(raw)
        if child.suffix.lower() not in SUPPORT_SUFFIXES:
            continue
        if child.is_absolute():
            target_path = _safe_path(child)
        elif path.suffix.lower() in TEX_SOURCE_SUFFIXES:
            # TeX \input is normally resolved against the master document's cwd.
            # A containing-file fallback also accommodates standalone subfiles.
            primary = _safe_path(master_dir / child)
            fallback = _safe_path(path.parent / child)
            target_path = primary if primary.exists() or not fallback.exists() else fallback
        else:
            target_path = _safe_path(path.parent / child)
        result.append(target_path)
    return result


def _collect(sources: list[Path]) -> list[dict]:
    queue = [(path, path.parent) for path in sources]
    seen: set[Path] = set()
    explored: set[tuple[Path, Path]] = set()
    entries = []
    while queue:
        raw_path, master_dir = queue.pop(0)
        path = _safe_path(raw_path)
        context = (path, master_dir)
        if context in explored:
            continue
        explored.add(context)
        if len(explored) > 10000:
            raise ValueError("explicit source dependency closure exceeds 10000 file/master contexts")
        if path.is_dir():
            raise ValueError(f"source must be a file, not a directory: {path}")
        missing = not path.is_file()
        if path not in seen:
            seen.add(path)
            entry = {"source_id": f"source-{len(entries) + 1:04d}", "path": str(path),
                     "sha256": None if missing else sha256_file(path), "missing": missing}
            entries.append(entry)
        if not missing:
            queue.extend((child, child.parent if path.suffix.lower() not in TEX_SOURCE_SUFFIXES and child.suffix.lower() in TEX_SOURCE_SUFFIXES else master_dir)
                         for child in _linked_paths(path, master_dir))
    return entries


def _snapshot_inventory(work: Path, sources: list[Path], revision: int, entries: list[dict]) -> dict:
    destination = work / "snapshots" / f"input-{revision:04d}"
    destination.mkdir(parents=True, exist_ok=False)
    for entry in entries:
        if not entry["missing"]:
            original = Path(entry["path"])
            snapshot = destination / (entry["source_id"] + original.suffix)
            shutil.copyfile(original, snapshot)
            if sha256_file(original) != entry["sha256"] or sha256_file(snapshot) != entry["sha256"]:
                raise ValueError(f"source changed while snapshotting: {original}")
            entry["snapshot"] = str(snapshot.relative_to(work))
    corpus = _digest([{k: e[k] for k in ("source_id", "path", "sha256", "missing")} for e in entries])
    inventory = {"schema_version": 1, "revision": revision, "created_at": _now(),
                 "explicit_sources": [str(p) for p in sources], "sources": entries,
                 "corpus_sha256": corpus}
    write_json(work / "input-inventory.json", inventory)
    return inventory


def _templates(work: Path) -> None:
    templates = {
        "claim-ledger.json": {"authored_by": "", "claims": []},
        "candidate-prospectuses.json": {"authored_by": "", "candidates": [], "rationale": ""},
        "selected-contribution.json": {"selection": None},
        "reviews.json": {"reviews": []},
        "references-registry.json": {"references": []},
        "decision.json": {"outcome": None, "candidate_digest": None, "rationale": "", "limitations": [],
                          "next_steps": [], "not_applicable": {}},
    }
    for name, value in templates.items():
        write_json(work / name, {"schema_version": 1, **value})
        _write_text(work / name.replace(".json", ".md"),
                    f"# {name.removesuffix('.json').replace('-', ' ').title()}\n\nPending agent-authored evidence.\n")
    _write_text(work / "input-inventory.md",
                "# Input inventory\n\nSee input-inventory.json for immutable source snapshots and hashes.\n")


def init_synthesize(sources: list[Path], work_dir: Path) -> dict:
    if not sources:
        raise ValueError("at least one explicit source is required")
    roots = list(dict.fromkeys(_safe_path(p) for p in sources))
    for source in roots:
        if not source.is_file() or source.suffix.lower() not in SUPPORT_SUFFIXES:
            raise ValueError(f"source must be an existing supported text file: {source}")
    work = _safe_path(work_dir)
    if work.exists():
        raise FileExistsError(f"refusing to overwrite work directory: {work}")
    entries = _collect(roots)
    work.mkdir(parents=True)
    inventory = _snapshot_inventory(work, roots, 1, entries)
    _templates(work)
    (work / "refs").mkdir()
    state = {"schema_version": 1, "mode": "synthesize", "work_dir": str(work),
             "created_at": _now(), "input_revision": 1, "corpus_sha256": inventory["corpus_sha256"],
             "inventory_sha256": sha256_file(work / "input-inventory.json"), "history": [],
             "gates": {g: {"status": "pending", "evidence": [], "updated_at": None} for g in GATES}}
    state["gates"]["intake"] = {"status": "pass", "evidence": ["hashed explicit source snapshots"],
                                "updated_at": _now()}
    write_json(work / "state.json", state)
    return state


def _inventory(state: dict, *, check_originals: bool = True) -> dict:
    work = Path(state["work_dir"])
    inventory = _record(work / "input-inventory.json")
    if sha256_file(work / "input-inventory.json") != state.get("inventory_sha256"):
        raise ValueError("input inventory changed; use explicit refresh-synthesis")
    if inventory.get("revision") != state.get("input_revision") or inventory.get("corpus_sha256") != state.get("corpus_sha256"):
        raise ValueError("input revision or corpus digest mismatch")
    for entry in _rows(inventory, "sources"):
        source = _safe_path(Path(entry["path"]))
        if entry.get("missing"):
            if check_originals and source.exists():
                raise ValueError(f"previously missing source now exists; refresh required: {source}")
            continue
        snapshot = _resolve(work, entry.get("snapshot", ""))
        if not _inside(snapshot, work / "snapshots"):
            raise ValueError("source snapshot is outside snapshot directory")
        for path in (source, snapshot) if check_originals else (snapshot,):
            if not path.is_file() or sha256_file(path) != entry.get("sha256"):
                raise ValueError(f"source or immutable snapshot changed: {path}; refresh required")
    if check_originals:
        current = _collect([Path(path) for path in inventory["explicit_sources"]])
        if _digest([{key: entry[key] for key in ("source_id", "path", "sha256", "missing")}
                    for entry in current]) != inventory["corpus_sha256"]:
            raise ValueError("source dependency closure changed; refresh required")
    return inventory


def _evidence(work: Path, records: Any, *, sources: set[Path] | None = None, required: bool = True) -> None:
    if not isinstance(records, list) or (required and not records):
        raise ValueError("nonempty hashed evidence list required")
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("evidence must contain path/sha256 objects")
        path = _resolve(work, item.get("path", ""))
        if not _inside(path, work) and path not in (sources or set()):
            raise ValueError(f"evidence must be a source or run-contained file: {path}")
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise ValueError(f"missing or changed evidence: {path}")


def _claims(state: dict) -> tuple[dict, dict[str, dict]]:
    work = Path(state["work_dir"])
    ledger = _record(work / "claim-ledger.json")
    _text(ledger.get("authored_by"), "claim ledger authored_by")
    inventory = _inventory(state)
    source_ids = {e["source_id"] for e in inventory["sources"] if not e.get("missing")}
    sources = {Path(e["path"]).resolve() for e in inventory["sources"] if not e.get("missing")}
    claims: dict[str, dict] = {}
    for claim in _rows(ledger, "claims"):
        ident = _text(claim.get("id"), "claim id")
        if ident in claims:
            raise ValueError(f"duplicate claim id: {ident}")
        _text(claim.get("statement"), f"claim {ident} statement")
        for key in ("hypotheses", "dependencies", "unresolved_assumptions"):
            _strings(claim.get(key), f"claim {ident} {key}")
        if claim.get("proof_status") not in PROOF_STATUSES:
            raise ValueError(f"invalid proof_status: {ident}")
        refs = claim.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"claim {ident} needs source provenance")
        for ref in refs:
            if not isinstance(ref, dict) or ref.get("source_id") not in source_ids:
                raise ValueError(f"claim {ident} refers to missing or unknown source")
            _text(ref.get("location"), f"claim {ident} source location")
        _evidence(work, claim.get("evidence"), sources=sources,
                  required=claim["proof_status"] not in {"conjecture", "numerical"})
        claims[ident] = claim
    # Missing and cyclic proof dependencies remain recordable during inventory;
    # they are rejected when a candidate's complete proof closure is frozen.
    return ledger, claims


def _closure(claims: dict[str, dict], roots: list[str]) -> list[dict]:
    done: set[str] = set()
    active: set[str] = set()
    result = []
    def visit(ident: str) -> None:
        if ident in active:
            raise ValueError(f"circular proof dependency: {ident}")
        if ident not in claims:
            raise ValueError(f"missing claim dependency: {ident}")
        if ident in done:
            return
        active.add(ident)
        for dependency in claims[ident]["dependencies"]:
            visit(dependency)
        active.remove(ident)
        done.add(ident)
        result.append(claims[ident])
    for ident in roots:
        visit(ident)
    return result


def _candidates(state: dict) -> tuple[dict, dict[str, dict]]:
    _, claims = _claims(state)
    record = _record(Path(state["work_dir"]) / "candidate-prospectuses.json")
    _text(record.get("authored_by"), "candidate authored_by")
    _text(record.get("rationale"), "candidate comparison rationale")
    candidates: dict[str, dict] = {}
    for candidate in _rows(record, "candidates"):
        ident = _text(candidate.get("id"), "candidate id")
        if ident in candidates:
            raise ValueError(f"duplicate candidate id: {ident}")
        for key in ("title", "research_question", "contribution", "significance"):
            _text(candidate.get(key), f"candidate {ident} {key}")
        for key in ("main_claim_ids", "supporting_claim_ids", "limitations", "excluded_material", "proposed_extensions"):
            _strings(candidate.get(key), f"candidate {ident} {key}")
        main = candidate["main_claim_ids"]
        if not 1 <= len(main) <= 4 or len(set(main)) != len(main):
            raise ValueError("a candidate needs one to four distinct main claims")
        for claim_id in main + candidate["supporting_claim_ids"]:
            if claim_id not in claims:
                raise ValueError(f"candidate references unknown claim: {claim_id}")
        candidates[ident] = candidate
    return record, candidates


def _candidate_payload(state: dict, candidate_id: str) -> dict:
    _, claims = _claims(state)
    _, candidates = _candidates(state)
    if candidate_id not in candidates:
        raise ValueError(f"unknown candidate: {candidate_id}")
    candidate = candidates[candidate_id]
    closure = _closure(claims, candidate["main_claim_ids"] + candidate["supporting_claim_ids"])
    return {"input_revision": state["input_revision"], "corpus_sha256": state["corpus_sha256"],
            "candidate": candidate, "claims": closure}


def candidate_digest(state_path: Path, candidate_id: str) -> str:
    return _digest(_candidate_payload(_state(state_path), candidate_id))


def _archive(state: dict, reason: str) -> str:
    work = Path(state["work_dir"])
    _gate_snapshots(state)
    if any(path.is_symlink() for path in work.rglob("*")):
        raise ValueError("cannot archive a synthesis run containing symlinks")
    directory = work / "history" / f"{len(state['history']) + 1:04d}"
    directory.mkdir(parents=True, exist_ok=False)
    # Archive all supporting files as well as authoritative JSON, without recursive history.
    for child in work.iterdir():
        if child.name in {"history", "snapshots"}:
            continue
        if child.is_symlink():
            raise ValueError(f"cannot archive symlink in synthesis run: {child}")
        if child.is_dir():
            shutil.copytree(child, directory / child.name)
        else:
            shutil.copy2(child, directory / child.name)
    state["history"].append({"path": str(directory.relative_to(work)), "reason": reason,
                             "input_revision": state["input_revision"], "created_at": _now()})
    return str(directory)


def _selection(state: dict) -> dict:
    work = Path(state["work_dir"])
    selected = _record(work / "selected-contribution.json")
    if selected.get("selection") is None and "candidate" not in selected:
        raise ValueError("no approved contribution selected")
    ident = selected.get("candidate", {}).get("id")
    current = _candidate_payload(state, ident)
    digest = _digest(current)
    if selected.get("candidate_digest") != digest:
        raise ValueError("selected contribution changed; fresh author approval is required")
    if any(selected.get(key) != value for key, value in current.items()):
        raise ValueError("selected contribution snapshot changed")
    approval = selected.get("approval", {})
    _evidence(work, [approval.get("evidence", {})])
    recorded = _read(_resolve(work, approval["evidence"]["path"]))
    _validate_approval(recorded, state, ident, digest)
    if approval.get("record") != recorded:
        raise ValueError("author approval snapshot differs from recorded approval")
    receipt = state["gates"]["selection"].get("artifact_sha256")
    if receipt != sha256_file(work / "selected-contribution.json"):
        raise ValueError("selected contribution differs from engine selection receipt")
    return selected


def _validate_approval(approval: dict, state: dict, ident: str, digest: str) -> None:
    for field in ("author", "approved_at", "message"):
        _text(approval.get(field), f"author approval {field}")
    if (approval.get("decision") != "approve" or approval.get("candidate_id") != ident
            or approval.get("candidate_digest") != digest or approval.get("input_revision") != state["input_revision"]):
        raise ValueError("author approval must bind the exact candidate digest and input revision")


def select_synthesis(state_path: Path, candidate_id: str, approval_evidence: Path) -> dict:
    state = _state(state_path)
    _assert_mutable_run(Path(state["work_dir"]))
    _inventory(state)
    _receipts(state)
    if any(state["gates"][g]["status"] != "pass" for g in GATES[:3]):
        raise ValueError("intake, inventory and candidates gates must pass before author selection")
    payload = _candidate_payload(state, candidate_id)
    digest = _digest(payload)
    approval = _read(approval_evidence)
    _validate_approval(approval, state, candidate_id, digest)
    work = Path(state["work_dir"])
    if state["gates"]["selection"]["status"] == "pass" or state["gates"]["decision"]["status"] == "pass":
        _archive(state, "author reselection")
    approval_path = work / "approvals" / f"approval-{len(state['history']) + 1:04d}-{digest[:12]}.json"
    approval_path.parent.mkdir(exist_ok=True)
    if approval_path.exists():
        if sha256_file(approval_path) != sha256_file(approval_evidence):
            raise ValueError("existing approval snapshot differs; choose a new selection revision")
    else:
        shutil.copyfile(approval_evidence, approval_path)
    selected = {"schema_version": 1, **payload, "candidate_digest": digest,
                "selected_at": _now(), "approval": {"record": approval,
                "evidence": {"path": str(approval_path.relative_to(work)), "sha256": sha256_file(approval_path)}}}
    write_json(work / "selected-contribution.json", selected)
    state["gates"]["selection"] = {"status": "pass", "evidence": [str(approval_path)], "updated_at": _now(),
                                      "artifact_sha256": sha256_file(work / "selected-contribution.json")}
    state["gates"]["selection"].update(_freeze_gate_artifacts(work, "selection"))
    for gate in ("assessment", "decision"):
        state["gates"][gate] = {"status": "pending", "evidence": [], "updated_at": None}
    write_json(work / "reviews.json", {"schema_version": 1, "reviews": []})
    write_json(work / "decision.json", {"schema_version": 1, "outcome": None, "candidate_digest": digest,
               "rationale": "", "limitations": [], "next_steps": [], "not_applicable": {}})
    write_json(state_path, state)
    return state


def refresh_synthesis(state_path: Path) -> dict:
    state = _state(state_path)
    work = Path(state["work_dir"])
    _assert_mutable_run(work)
    # A refresh permits changed originals, not a corrupted prior evidence record.
    old = _inventory(state, check_originals=False)
    _gate_snapshots(state)
    sources = [Path(p) for p in old["explicit_sources"]]
    entries = _collect(sources)
    _archive(state, "explicit source refresh")
    state["input_revision"] += 1
    inventory = _snapshot_inventory(work, sources, state["input_revision"], entries)
    _templates(work)
    state["corpus_sha256"] = inventory["corpus_sha256"]
    state["inventory_sha256"] = sha256_file(work / "input-inventory.json")
    state["gates"] = {g: {"status": "pending", "evidence": [], "updated_at": None} for g in GATES}
    state["gates"]["intake"] = {"status": "pass", "evidence": ["explicit refreshed snapshots"], "updated_at": _now()}
    write_json(state_path, state)
    return state


def _references(state: dict, required_ids: list[str]) -> list[dict]:
    work = Path(state["work_dir"])
    rows = _rows(_record(work / "references-registry.json"), "references")
    entries = {r.get("citation_key"): r for r in rows}
    if len(entries) != len(rows):
        raise ValueError("duplicate reference citation keys")
    result = []
    for ident in required_ids:
        if ident not in entries:
            raise ValueError(f"novelty reference is missing: {ident}")
        ref = entries[ident]
        for key in ("citation_key", "title", "authors", "claim", "verification_date", "bibliography_path"):
            _text(ref.get(key), f"reference {ident} {key}")
        if ref.get("status") not in {"verified", "preverified"}:
            raise ValueError(f"reference is not source-verified: {ident}")
        pairs = [("evidence_file", "evidence_sha256"), ("bibtex_snapshot", "bibtex_sha256")]
        kind = ref.get("source_type")
        if kind in {"article", "book"}:
            pairs.append(("source_file", "source_sha256"))
            for field in ("public_url", "evidence_page"):
                _text(ref.get(field), f"reference {ident} {field}")
        elif kind == "arxiv":
            pairs.append(("archive_path", "archive_sha256"))
            arxiv_id = _text(ref.get("arxiv_id"), f"reference {ident} arxiv_id")
            if ref.get("abstract_confirmed") is not True or ref.get("abs_url") != f"https://arxiv.org/abs/{arxiv_id}" or ref.get("eprint_url") != f"https://arxiv.org/e-print/{arxiv_id}":
                raise ValueError(f"reference arXiv identity is unconfirmed: {ident}")
            _text(ref.get("evidence_location"), f"reference {ident} evidence_location")
            source_dir = _resolve(work, ref.get("source_dir", ""))
            if not _inside(source_dir, work / "refs") or not source_dir.is_dir():
                raise ValueError("extracted source must be in run refs directory")
            if not _inside(_resolve(work, ref.get("evidence_file", "")), source_dir):
                raise ValueError("arXiv evidence must be inside extracted primary source")
        else:
            raise ValueError(f"unsupported reference source_type: {kind}")
        for path_key, hash_key in pairs:
            path = _resolve(work, ref.get(path_key, ""))
            if not _inside(path, work / "refs"):
                raise ValueError("reference evidence must be inside run refs directory")
            _evidence(work, [{"path": str(path), "sha256": ref.get(hash_key)}])
        bibliography = _resolve(work, ref["bibliography_path"])
        if not _inside(bibliography, work / "refs") or not bibliography.is_file():
            raise ValueError("reference bibliography must exist within run refs directory")
        exported = _resolve(work, ref["bibtex_snapshot"]).read_text(encoding="utf-8-sig").strip()
        if not exported or exported not in bibliography.read_text(encoding="utf-8-sig"):
            raise ValueError(f"reference bibliography must contain its verbatim BibTeX snapshot: {ident}")
        result.append(ref)
    return result


def _reference_digest(state: dict, references: list[dict]) -> str:
    work = Path(state["work_dir"])
    return _digest([
        {"reference": record,
         "bibliography_sha256": sha256_file(_resolve(work, record["bibliography_path"]))}
        for record in sorted(references, key=lambda record: record["citation_key"])
    ])


def references_digest(state_path: Path, reference_ids: list[str]) -> str:
    """Bind a novelty review to verified reference records and bibliography bytes."""
    state = _state(state_path)
    _inventory(state)
    _strings(reference_ids, "novelty reference_ids")
    if len(set(reference_ids)) != len(reference_ids):
        raise ValueError("novelty reference_ids must be distinct")
    return _reference_digest(state, _references(state, reference_ids))


def _reviews(state: dict, selected: dict, *, ready: bool = False) -> tuple[list[dict], list[dict]]:
    work = Path(state["work_dir"])
    ledger, _ = _claims(state)
    candidates, _ = _candidates(state)
    authors = {ledger["authored_by"], candidates["authored_by"]}
    rows = _rows(_record(work / "reviews.json"), "reviews")
    reviews = {r.get("kind"): r for r in rows}
    if len(rows) != 2 or set(reviews) != {"correctness", "novelty"}:
        raise ValueError("assessment needs one correctness and one novelty review")
    reviewers: set[str] = set()
    closure = {c["id"] for c in selected["claims"]}
    references = []
    for kind, review in reviews.items():
        reviewer = _text(review.get("reviewer"), f"{kind} reviewer")
        if reviewer in authors or reviewer in reviewers:
            raise ValueError("reviews must be independently attributed to distinct non-author reviewers")
        reviewers.add(reviewer)
        if review.get("candidate_digest") != selected["candidate_digest"] or review.get("input_revision") != state["input_revision"]:
            raise ValueError(f"stale {kind} review digest or revision")
        if review.get("verdict") not in {"pass", "fail", "unresolved"}:
            raise ValueError(f"invalid {kind} review verdict")
        _text(review.get("findings"), f"{kind} review findings")
        _evidence(work, review.get("evidence"))
        if ready and review["verdict"] != "pass":
            raise ValueError(f"ready-to-draft blocked by {kind} review")
        if kind == "correctness":
            covered = set(_strings(review.get("covered_claim_ids"), "correctness covered_claim_ids"))
            if covered != closure:
                raise ValueError("correctness review must cover the exact complete proof dependency closure")
        else:
            _text(review.get("search_scope"), "novelty search scope")
            _text(review.get("searched_at"), "novelty search date")
            code = review.get("novelty_code")
            if code not in {"CLEAR", "ADJACENT", "COLLISION", "UNRESOLVED"}:
                raise ValueError("invalid novelty code")
            ids = _strings(review.get("reference_ids"), "novelty reference_ids")
            if len(set(ids)) != len(ids):
                raise ValueError("novelty reference_ids must be distinct")
            references = _references(state, ids)
            if review.get("references_sha256") != _reference_digest(state, references):
                raise ValueError("novelty review is missing or has a stale references_sha256 binding")
            if ready and (code not in {"CLEAR", "ADJACENT"} or not ids):
                raise ValueError("ready-to-draft requires a bounded, source-verified novelty comparison")
    return rows, references


def _ready_claims(state: dict, selected: dict) -> None:
    inventory = _inventory(state)
    if any(e.get("missing") for e in inventory["sources"]):
        raise ValueError("unresolved source dependencies block readiness")
    work = Path(state["work_dir"])
    for claim in selected["claims"]:
        if claim["proof_status"] in {"conjecture", "numerical"} or claim["unresolved_assumptions"]:
            raise ValueError(f"unsupported proof or hidden assumption blocks readiness: {claim['id']}")
        if claim["proof_status"] == "formally_verified":
            verification = claim.get("verification", {})
            statement_digest = _digest({"statement": claim["statement"], "hypotheses": claim["hypotheses"]})
            if verification.get("statement_sha256") != statement_digest or verification.get("result") != "pass":
                raise ValueError(f"formal verification must bind the exact statement and hypotheses: {claim['id']}")
            for key in ("checked_at", "command"):
                _text(verification.get(key), f"formal verification {key}")
            _evidence(work, [verification.get("evidence", {})])


def _decision(state: dict) -> dict:
    work = Path(state["work_dir"])
    decision = _record(work / "decision.json")
    if decision.get("outcome") not in OUTCOMES:
        raise ValueError("invalid or incomplete synthesis decision outcome")
    _text(decision.get("rationale"), "decision rationale")
    _strings(decision.get("limitations"), "decision limitations")
    steps = _strings(decision.get("next_steps"), "decision next_steps")
    if decision["outcome"] in {"focused_research_needed", "review_or_verification_needed"} and not steps:
        raise ValueError("needs-work decision must identify actionable next steps")
    skipped = decision.get("not_applicable", {})
    if not isinstance(skipped, dict) or set(skipped) - {"selection", "assessment"}:
        raise ValueError("only selection and assessment may be explicitly not applicable")
    for gate, reason in skipped.items():
        _text(reason, f"{gate} not-applicable reason")
    for gate in GATES[:3]:
        if state["gates"][gate]["status"] != "pass":
            raise ValueError(f"decision requires passed {gate} gate")
    if state["gates"]["selection"]["status"] != "pass":
        if decision["outcome"] != "no_compelling_paper" or set(skipped) != {"selection", "assessment"}:
            raise ValueError("only a justified no-paper decision can finish without author selection")
        if decision.get("candidate_digest") is not None:
            raise ValueError("unselected no-paper decision must not claim an approved candidate digest")
        return decision
    selected = _selection(state)
    if decision.get("candidate_digest") != selected["candidate_digest"]:
        raise ValueError("decision must bind the approved candidate digest")
    if "selection" in skipped:
        raise ValueError("approved selection cannot be marked not applicable")
    if decision["outcome"] == "ready_to_draft":
        if skipped or state["gates"]["assessment"]["status"] != "pass":
            raise ValueError("ready-to-draft requires a completed assessment")
        _reviews(state, selected, ready=True)
        _ready_claims(state, selected)
    elif state["gates"]["assessment"]["status"] != "pass":
        if set(skipped) != {"assessment"}:
            raise ValueError("incomplete assessment needs an explicit not-applicable explanation")
    elif skipped:
        raise ValueError("completed assessment cannot be marked not applicable")
    return decision


def _gate_files(name: str) -> list[str]:
    return {"inventory": ["claim-ledger.json"], "candidates": ["claim-ledger.json", "candidate-prospectuses.json"],
            "selection": ["selected-contribution.json"],
            "assessment": ["reviews.json", "references-registry.json"], "decision": ["decision.json"]}.get(name, [])


def _freeze_gate_artifacts(work: Path, name: str) -> dict:
    hashes = {file: sha256_file(work / file) for file in _gate_files(name)}
    directory = work / "snapshots" / "gates" / (name + "-" + _digest(hashes))
    directory.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for file, expected in hashes.items():
        destination = directory / file
        if not destination.exists():
            # Exclusive creation never follows an attacker-created hard link.
            with destination.open("xb") as handle:
                handle.write((work / file).read_bytes())
        if sha256_file(destination) != expected or sha256_file(work / file) != expected:
            raise ValueError(f"gate artifact changed during snapshot or its snapshot is corrupt: {file}")
        snapshots[file] = str(destination.relative_to(work))
    return {"artifact_hashes": hashes, "artifact_snapshots": snapshots}


def _gate_snapshots(state: dict) -> None:
    work = Path(state["work_dir"])
    for gate, record in state["gates"].items():
        for name, snapshot in record.get("artifact_snapshots", {}).items():
            expected = record.get("artifact_hashes", {}).get(name)
            saved = _resolve(work, snapshot)
            if (not _inside(saved, work / "snapshots" / "gates") or not saved.is_file()
                    or sha256_file(saved) != expected):
                raise ValueError(f"immutable {gate} artifact snapshot is missing or corrupt: {name}")


def _receipts(state: dict, *, exclude: str | None = None) -> None:
    work = Path(state["work_dir"])
    _gate_snapshots(state)
    for gate, record in state["gates"].items():
        if gate == exclude or record.get("status") != "pass":
            continue
        for name, expected in record.get("artifact_hashes", {}).items():
            path = work / name
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"{gate} evidence changed ({name}); reopen that gate before continuing")


def mark_synthesis_gate(state_path: Path, name: str, status: str, evidence: list[str]) -> dict:
    state = _state(state_path)
    _assert_mutable_run(Path(state["work_dir"]))
    _inventory(state)
    if name not in GATES:
        raise ValueError(f"unknown synthesis gate: {name}")
    if status not in {"pass", "fail", "pending"}:
        raise ValueError("gate status must be pass, fail, or pending")
    if name in {"intake", "selection"} and status == "pass":
        raise ValueError(f"{name} can only pass through its dedicated initialization/selection command")
    if status == "pass":
        _strings(evidence, "gate evidence")
        if not evidence:
            raise ValueError("passing gate requires evidence")
        # Passing an already passed gate cannot silently replace its own receipt
        # while preserving downstream decisions. Reopen explicitly first.
        _receipts(state)
        if name != "decision":
            for previous in GATES[:GATES.index(name)]:
                if state["gates"][previous]["status"] != "pass":
                    raise ValueError(f"cannot pass {name} before {previous}")
        if name == "inventory":
            _claims(state)
        elif name == "candidates":
            _candidates(state)
        elif name == "assessment":
            _reviews(state, _selection(state))
        elif name == "decision":
            decision = _decision(state)
            for gate, reason in decision.get("not_applicable", {}).items():
                state["gates"][gate] = {"status": "not_applicable", "evidence": [reason], "updated_at": _now()}
    else:
        if state["gates"][name]["status"] == "pass":
            _archive(state, f"reopened {name}")
        for later in GATES[GATES.index(name) + 1:]:
            state["gates"][later] = {"status": "pending", "evidence": [], "updated_at": None}
    work = Path(state["work_dir"])
    state["gates"][name] = {"status": status, "evidence": evidence, "updated_at": _now(),
                             **(_freeze_gate_artifacts(work, name) if status == "pass" else {"artifact_hashes": {}})}
    write_json(state_path, state)
    return state


def audit_synthesis(state_path: Path, require_all_gates: bool = False) -> dict:
    errors = []
    state = None
    try:
        state = _state(state_path)
        _inventory(state)
        _receipts(state)
        statuses = {k: v.get("status") for k, v in state["gates"].items()}
        if statuses["inventory"] == "pass":
            _claims(state)
        if statuses["candidates"] == "pass":
            _candidates(state)
        if statuses["selection"] == "pass":
            _selection(state)
        if statuses["assessment"] == "pass":
            _reviews(state, _selection(state))
        if statuses["decision"] == "pass":
            _decision(state)
        elif any(v == "not_applicable" for v in statuses.values()):
            raise ValueError("not-applicable stages require a completed, validated decision")
        if require_all_gates and statuses["decision"] != "pass":
            raise ValueError("synthesis has not reached a terminal decision")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"mode": "synthesize", "ok": not errors, "pass": not errors, "errors": errors,
            "complete": bool(state and state["gates"]["decision"].get("status") == "pass" and not errors)}


def resume_synthesis(state_path: Path) -> dict:
    report = audit_synthesis(state_path)
    if report["errors"]:
        raise ValueError("; ".join(report["errors"]))
    state = _state(state_path)
    next_gate = next((g for g in GATES if state["gates"][g]["status"] not in {"pass", "not_applicable"}), None)
    result = {"mode": "synthesize", "next_gate": next_gate,
              "status": state["gates"][next_gate]["status"] if next_gate else "complete",
              "input_revision": state["input_revision"]}
    if state["gates"]["candidates"]["status"] == "pass":
        _, candidates = _candidates(state)
        digests, blocked = {}, {}
        for ident in candidates:
            try:
                digests[ident] = candidate_digest(state_path, ident)
            except ValueError as exc:
                blocked[ident] = str(exc)
        result["candidate_digests"] = digests
        result["blocked_candidates"] = blocked
    return result


def prepare_handoff(state_path: Path) -> dict:
    report = audit_synthesis(state_path, require_all_gates=True)
    if report["errors"]:
        raise ValueError("invalid synthesis handoff: " + "; ".join(report["errors"]))
    state = _state(state_path)
    decision = _decision(state)
    if decision["outcome"] != "ready_to_draft":
        raise ValueError("composition requires a ready-to-draft synthesis decision")
    selected = _selection(state)
    reviews, references = _reviews(state, selected, ready=True)
    work = Path(state["work_dir"])
    # Canonical absolute paths let composition copy evidence into its own workspace.
    provenance: dict[str, str] = {}
    def record(path: Path) -> None:
        provenance[str(path.resolve())] = sha256_file(path)
    for name in ARTIFACTS:
        record(work / name)
    record(state_path)
    inventory = _inventory(state)
    for source in inventory["sources"]:
        record(Path(source["path"]))
        record(_resolve(work, source["snapshot"]))
    payload = deepcopy(selected)
    for claim in payload["claims"]:
        for item in claim["evidence"]:
            item["path"] = str(_resolve(work, item["path"]))
            record(Path(item["path"]))
        if claim.get("verification"):
            item = claim["verification"].get("evidence", {})
            if item:
                item["path"] = str(_resolve(work, item["path"]))
                record(Path(item["path"]))
    reference_copy = deepcopy(references)
    for ref in reference_copy:
        for key in ("evidence_file", "bibtex_snapshot", "source_file", "archive_path", "bibliography_path", "source_dir"):
            if ref.get(key):
                path = _resolve(work, ref[key])
                ref[key] = str(path)
                if path.is_file():
                    record(path)
    review_copy = deepcopy(reviews)
    for review in review_copy:
        for item in review["evidence"]:
            item["path"] = str(_resolve(work, item["path"]))
            record(Path(item["path"]))
    approval = deepcopy(selected["approval"])
    approval["evidence"]["path"] = str(_resolve(work, approval["evidence"]["path"]))
    record(Path(approval["evidence"]["path"]))
    bundle = {"schema_version": 1, "synthesis_state": str(state_path.resolve()),
              "input_revision": state["input_revision"], "corpus_sha256": state["corpus_sha256"],
              "candidate_digest": selected["candidate_digest"], "candidate": payload["candidate"],
              "claims": payload["claims"], "main_claims": [c for c in payload["claims"] if c["id"] in payload["candidate"]["main_claim_ids"]],
              "approval": approval, "reviews": review_copy, "references": reference_copy, "decision": decision,
              "provenance_files": [{"path": p, "sha256": h} for p, h in sorted(provenance.items())]}
    bundle["handoff_sha256"] = _digest(bundle)
    return bundle


def verify_handoff(bundle: dict) -> None:
    payload = {k: v for k, v in bundle.items() if k != "handoff_sha256"}
    if bundle.get("handoff_sha256") != _digest(payload):
        raise ValueError("synthesis handoff content changed")
    for entry in bundle.get("provenance_files", []):
        path = Path(entry["path"])
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"synthesis handoff provenance changed: {path}")
    current = prepare_handoff(Path(bundle["synthesis_state"]))
    if current["handoff_sha256"] != bundle["handoff_sha256"]:
        raise ValueError("synthesis contribution or assessment changed after handoff")
