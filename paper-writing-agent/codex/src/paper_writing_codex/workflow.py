from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import subprocess
from typing import Any

from .coverage import markdown_coverage, write_json
from .tex_inventory import inventory_tex
from .versioning import exclusive_copy, next_version_path, sha256_file


GATES = [
    "preflight", "critical-path", "framework", "main-results", "lemmas",
    "draft", "compression", "final-matter", "terminology", "preservation", "final",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_snapshot(directory: Path) -> dict[str, Any]:
    try:
        root = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", root, "status", "--short"],
            text=True, capture_output=True, check=True,
        ).stdout.splitlines()
        return {"root": root, "status": status}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"root": None, "status": []}


def default_work_dir(output: Path) -> Path:
    return output.parent / "paper-writing" / output.stem


def _write_common_artifacts(work: Path) -> None:
    (work / "01-critical-path.md").write_text(
        "# Critical path\n\nPending graph extraction and certificate audit.\n", encoding="utf-8")
    (work / "02-framework.tex").write_text(
        """\\documentclass[11pt]{article}
\\begin{document}
\\section{Introduction} % Context, question, results, related work, outline.
\\section{Preliminaries and setup} % Definitions and notation, inserted just in time.
\\section{Main results} % Replace by mathematics-facing cluster names.
\\section{Verification} % Trust model and formalization scope.
\\section{Outlook} % Open questions and known surface.
\\appendix
\\section{Technical arguments} % Lengthy proofs and important routine derivations.
\\section*{References} % Bibliography inserted after reference verification.
\\end{document}
""", encoding="utf-8")
    (work / "02-section-map.md").write_text(
        "# Baseline section map\n\nMap every baseline section/topic to its proposed destination.\n",
        encoding="utf-8",
    )
    (work / "03-main-results.md").write_text(
        "# Main results, novelty, title, and theme\n\nPending selection and fresh literature audit.\n", encoding="utf-8")
    write_json(work / "03-main-results.json", {"schema_version": 1, "main_results": []})
    (work / "04-lemmas.md").write_text(
        "# Supporting lemmas\n\nRecord statement, dependencies, consumers, and destination.\n", encoding="utf-8")
    (work / "04-compression-ledger.md").write_text(
        "# Compression ledger\n\n"
        "Classify every mathematical unit after the full draft is frozen.\n", encoding="utf-8")
    write_json(work / "04-compression-ledger.json", {"schema_version": 1, "entries": []})
    (work / "05.5-deleted-steps.md").write_text(
        "# Deleted steps archive\n\n"
        "For every ledger-only step, add its archive anchor and exact normalized TeX statement, "
        "then record its source, consumers, and rationale in the JSON ledger.\n",
        encoding="utf-8",
    )
    write_json(work / "06-definition-ledger.json", {"schema_version": 1, "definitions": []})
    write_json(work / "references-registry.json", {"schema_version": 1, "references": []})
    (work / "07-terminology.md").write_text(
        "# Terminology and notation\n\n| Concept | Chosen term | Chosen notation | Rejected variants |\n"
        "|---|---|---|---|\n", encoding="utf-8")
    (work / "08-main-result-diff.md").write_text(
        "# Main-result preservation diff\n\nCompare every locked baseline theorem to the candidate.\n",
        encoding="utf-8",
    )
    (work / "08-release-report.md").write_text(
        "# Release report\n\nPending final gates, hashes, references, pages, and open questions.\n",
        encoding="utf-8",
    )


def init_refine(source: Path, work_dir: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    destination, current, following = next_version_path(source)
    source = source.expanduser().absolute()
    work = (work_dir or default_work_dir(destination)).expanduser().absolute()
    report = {
        "mode": "refine",
        "source": str(source),
        "output": str(destination),
        "input_version": current,
        "output_version": following,
        "work_dir": str(work),
        "source_sha256": sha256_file(source),
    }
    if dry_run:
        return report
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite next version: {destination}")
    if work.exists():
        raise FileExistsError(f"refusing to overwrite work directory: {work}")
    work.mkdir(parents=True, exist_ok=False)
    try:
        copy_record = exclusive_copy(source, destination)
        report["source_sha256"] = str(copy_record["sha256"])
        report["snapshot"] = copy_record
        inventory = inventory_tex(source)
        missing_dependencies = [
            entry["path"] for entry in inventory.get("source_files", []) if entry.get("missing")
        ]
        if missing_dependencies:
            raise ValueError(
                "baseline has unresolved included TeX/Bib dependencies: "
                + ", ".join(missing_dependencies[:10])
            )
        if inventory["source_sha256"] != report["source_sha256"]:
            raise RuntimeError("source changed between snapshot and inventory")
        if sha256_file(source) != report["source_sha256"] or sha256_file(destination) != report["source_sha256"]:
            raise RuntimeError("source or destination changed during preflight")
        write_json(work / "00-baseline-inventory.json", inventory)
        (work / "00-baseline-source.sha256").write_text(report["source_sha256"] + "\n", encoding="utf-8")
        write_json(work / "00-main-results-lock.json", {
            "schema_version": 1, "source": str(source), "source_sha256": report["source_sha256"],
            "main_results": [],
        })
        (work / "00-main-results-lock.md").write_text(
            "# Baseline main-results lock\n\nPending selection of every main theorem label.\n",
            encoding="utf-8",
        )
        ledger = {
            "schema_version": 1,
            "source": str(source),
            "candidate": str(destination),
            "entries": [
                {
                    "unit_id": unit["id"], "disposition": "auto", "target_label": None,
                    "citation_key": None, "reason": None, "consumer": None, "evidence": None,
                    "semantic_audits": [],
                }
                for unit in inventory["units"]
            ],
        }
        write_json(work / "05-coverage-ledger.json", ledger)
        (work / "05-coverage-ledger.md").write_text(markdown_coverage(inventory), encoding="utf-8")
        _write_common_artifacts(work)
        mathematical_kinds = {
            "statement", "proof", "display", "equation", "align", "gather", "multline",
            "figure", "table", "environment",
        }
        compression_entries = [
            {
                "unit_id": unit["id"], "classification": "UNCLASSIFIED",
                "archive_anchor": None, "reason": None, "source": None, "consumer": None,
                "body_label": None, "appendix_label": None,
                "citation_key": None,
                "archived_text": None, "archived_text_sha256": None,
                "archived_raw_text": None, "archived_raw_sha256": None,
                "semantic_audits": [],
            }
            for unit in inventory["units"] if unit["kind"] in mathematical_kinds
        ]
        write_json(work / "04-compression-ledger.json", {
            "schema_version": 1, "entries": compression_entries,
        })
        state = {
            "schema_version": 1, **report, "created_at": _now(),
            "git_preflight": _git_snapshot(source.parent),
            "gates": {gate: {"status": "pending", "evidence": [], "updated_at": None} for gate in GATES},
        }
        state["output_reservation"] = {
            "dev": copy_record["destination_dev"], "ino": copy_record["destination_ino"],
            "sha256": copy_record["sha256"],
        }
        state["gates"]["preflight"] = {
            "status": "pass", "evidence": ["exclusive versioned copy", "baseline SHA-256 recorded"],
            "updated_at": _now(),
        }
        write_json(work / "00-run-state.json", state)
        verify_output(state, require_reservation=True, require_content=True)
        return state
    except Exception:
        # Do not remove a successfully exclusive-created candidate: preserving a visibly staged
        # version is safer than deleting user data. The state of partial initialization is clear.
        raise


def init_compose(output: Path, work_dir: Path | None = None) -> dict[str, Any]:
    output = output.expanduser().absolute()
    if output.suffix.lower() != ".tex":
        raise ValueError("compose output must be .tex")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite compose output: {output}")
    work = (work_dir or default_work_dir(output)).expanduser().absolute()
    if work.exists():
        raise FileExistsError(f"refusing to overwrite work directory: {work}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("% Reserved by paper-writing-codex; compose into this file at the draft gate.\n")
        handle.flush()
        os.fsync(handle.fileno())
        reserved = os.fstat(handle.fileno())
    work.mkdir(parents=True)
    _write_common_artifacts(work)
    state = {
        "schema_version": 1, "mode": "compose", "source": None, "source_sha256": None,
        "output": str(output), "work_dir": str(work), "created_at": _now(),
        "git_preflight": _git_snapshot(output.parent),
        "gates": {gate: {"status": "pending", "evidence": [], "updated_at": None} for gate in GATES},
        "output_reservation": {
            "dev": reserved.st_dev, "ino": reserved.st_ino, "sha256": sha256_file(output),
        },
    }
    state["gates"]["preflight"] = {"status": "pass", "evidence": ["output absent"], "updated_at": _now()}
    write_json(work / "00-run-state.json", state)
    verify_output(state, require_reservation=True, require_content=True)
    return state


def verify_output(
    state: dict[str, Any], *, require_reservation: bool = False, require_content: bool = False,
) -> None:
    output = Path(state["output"])
    try:
        output_stat = os.lstat(output)
    except FileNotFoundError as error:
        raise ValueError(f"output is missing: {output}") from error
    if not stat.S_ISREG(output_stat.st_mode):
        raise ValueError(f"output is not a regular non-symlink file: {output}")
    if output_stat.st_nlink != 1:
        raise ValueError(f"output must have exactly one hard link: {output}")
    source_value = state.get("source")
    if source_value:
        try:
            if os.path.samefile(source_value, output):
                raise ValueError("output aliases the immutable baseline source")
        except FileNotFoundError:
            pass
    if require_reservation:
        reservation = state.get("output_reservation") or {}
        if (output_stat.st_dev, output_stat.st_ino) != (reservation.get("dev"), reservation.get("ino")):
            raise ValueError("reserved output path was replaced during initialization")
        if require_content and reservation.get("sha256") and sha256_file(output) != reservation["sha256"]:
            raise ValueError("reserved output contents changed during initialization")


def claim_output(state_path: Path) -> dict[str, Any]:
    """Adopt a legitimate editor replacement while keeping the path fail-closed.

    Call explicitly after an editor performs an atomic save that changes the inode.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    verify_source(state)
    verify_output(state)
    output = Path(state["output"])
    output_stat = os.lstat(output)
    state["output_reservation"] = {
        "dev": output_stat.st_dev,
        "ino": output_stat.st_ino,
        "sha256": sha256_file(output),
        "claimed_at": _now(),
    }
    write_json(state_path, state)
    verify_output(state, require_reservation=True)
    return state["output_reservation"]


def verify_source(state: dict[str, Any]) -> None:
    if state.get("mode") != "refine":
        return
    source = Path(state["source"])
    if not source.exists() or sha256_file(source) != state.get("source_sha256"):
        raise ValueError("baseline source is missing or has changed")
    inventory_path = Path(state["work_dir"]) / "00-baseline-inventory.json"
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        for entry in inventory.get("source_files", []):
            if entry.get("missing"):
                path = Path(entry.get("path", ""))
                if path.exists():
                    raise ValueError(f"baseline dependency appeared after initialization: {path}")
                raise ValueError(f"baseline inventory contains an unresolved dependency: {path}")
            path = Path(entry.get("path", ""))
            if not path.is_file() or (entry.get("sha256") and sha256_file(path) != entry["sha256"]):
                raise ValueError(f"baseline source-tree file is missing or changed: {path}")


def mark_gate(state_path: Path, name: str, status: str, evidence: list[str]) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    verify_source(state)
    verify_output(state, require_reservation=True)
    if name not in GATES:
        raise ValueError(f"unknown gate: {name}")
    if status not in {"pass", "fail", "pending"}:
        raise ValueError("gate status must be pass, fail, or pending")
    if status == "pass" and not evidence:
        raise ValueError("a passing gate requires evidence")
    gate_index = GATES.index(name)
    if status == "pass":
        unfinished = [
            gate for gate in GATES[:gate_index]
            if state.get("gates", {}).get(gate, {}).get("status") != "pass"
        ]
        if unfinished:
            raise ValueError("cannot pass a gate before earlier gates: " + ", ".join(unfinished))
    state["gates"][name] = {"status": status, "evidence": evidence, "updated_at": _now()}
    if status != "pass":
        for later in GATES[gate_index + 1:]:
            state["gates"][later] = {"status": "pending", "evidence": [], "updated_at": _now()}
    write_json(state_path, state)
    return state


def resume_point(state_path: Path) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    verify_source(state)
    verify_output(state, require_reservation=True)
    for gate in GATES:
        entry = state.get("gates", {}).get(gate, {})
        if entry.get("status") != "pass":
            return {"mode": state["mode"], "next_gate": gate, "status": entry.get("status", "pending")}
    return {"mode": state["mode"], "next_gate": None, "status": "complete"}
