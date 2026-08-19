from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .coverage import (
    COMPRESSION_CLASSES, MATHEMATICAL_KINDS, NON_RESULT_ENVIRONMENTS, _contains_label, _has_ref_near_label,
    _audited_style_rewrite_errors, _tex_texts, audit_refinement, lock_main_results, write_json,
)
from .critical_path import analyze, to_markdown
from .safe_extract import safe_extract
from .tex_inventory import digest_text, inventory_tex, normalize_tex
from .versioning import next_version_path, sha256_file
from .workflow import (
    GATES, claim_output, init_compose, init_refine, mark_gate, resume_point, verify_output,
    verify_source,
)


def emit(value) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False))


def _main_text_characters(inventory: dict) -> int:
    counted = {
        "section", "statement", "proof", "display", "equation", "align", "gather",
        "multline", "figure", "table", "environment", "footnote", "prose",
    }
    return sum(
        len(unit.get("raw_text") or unit.get("normalized_text") or "")
        for unit in inventory.get("units", [])
        if unit.get("kind") in counted and not unit.get("in_appendix")
    )


def cmd_next_version(args) -> None:
    destination, current, following = next_version_path(Path(args.source))
    value = {
        "source": str(Path(args.source).expanduser().absolute()),
        "input_version": current,
        "output_version": following,
        "output": str(destination),
        "collision": destination.exists(),
    }
    if args.json:
        emit(value)
    else:
        print(destination)
    if destination.exists():
        raise SystemExit(3)


def cmd_init_refine(args) -> None:
    emit(init_refine(
        Path(args.source), Path(args.work_dir) if args.work_dir else None, dry_run=args.dry_run,
    ))


def cmd_init_compose(args) -> None:
    emit(init_compose(Path(args.output), Path(args.work_dir) if args.work_dir else None))


def cmd_inventory(args) -> None:
    value = inventory_tex(Path(args.tex))
    if args.out:
        write_json(Path(args.out), value)
    emit(value if args.json or not args.out else {"out": str(Path(args.out).absolute()), "counts": value["counts"]})


def cmd_critical_path(args) -> None:
    selected = [item.strip() for item in args.select.split(",") if item.strip()] if args.select else None
    value = analyze(Path(args.graph), selected_override=selected)
    markdown = to_markdown(value)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    if args.json_out:
        write_json(Path(args.json_out), value)
    emit(value if args.json else markdown)


def cmd_lock_main(args) -> None:
    emit(lock_main_results(Path(args.state), args.label, args.unit_id))


def cmd_gate(args) -> None:
    emit(mark_gate(Path(args.state), args.name, args.status, args.evidence or []))


def cmd_resume(args) -> None:
    emit(resume_point(Path(args.state)))


def cmd_claim_output(args) -> None:
    emit(claim_output(Path(args.state)))


def _audit_references(state: dict) -> list[str]:
    errors: list[str] = []
    work = Path(state["work_dir"])
    output = Path(state["output"])
    if not output.exists():
        return [f"output is missing: {output}"]
    inventory = inventory_tex(output)
    path = work / "references-registry.json"
    if not path.exists():
        return ["references-registry.json is missing"] if inventory["citations"] else []
    registry = json.loads(path.read_text(encoding="utf-8"))
    entries = {entry.get("citation_key"): entry for entry in registry.get("references", [])}
    common_fields = (
        "title", "authors", "evidence_file", "evidence_sha256", "claim",
        "bibtex_snapshot", "bibtex_sha256", "bibliography_path", "verification_date",
    )
    def resolve_record_path(value: str) -> Path:
        path_value = Path(value).expanduser()
        return path_value if path_value.is_absolute() else output.parent / path_value
    for key in inventory["citations"]:
        entry = entries.get(key)
        if not entry:
            errors.append(f"citation lacks registry entry: {key}")
            continue
        if entry.get("status") not in {"verified", "preverified"}:
            errors.append(f"citation is not verified: {key}")
        source_type = entry.get("source_type")
        if not source_type:
            errors.append(f"citation {key} misses source_type")
        if source_type == "arxiv":
            required_fields = common_fields + (
                "arxiv_id", "abs_url", "eprint_url", "abstract_confirmed", "archive_path",
                "archive_sha256", "source_dir", "evidence_location",
            )
        elif source_type == "book":
            required_fields = common_fields + (
                "public_url", "source_file", "source_sha256", "evidence_page",
            )
        else:
            errors.append(f"citation has unsupported source_type {source_type!r}: {key}")
            required_fields = common_fields
        for field in required_fields:
            if not entry.get(field):
                errors.append(f"citation {key} misses {field}")
        if source_type == "arxiv" and entry.get("abstract_confirmed") is not True:
            errors.append(f"citation identity was not fully confirmed: {key}")
        arxiv_id = str(entry.get("arxiv_id") or "")
        if source_type == "arxiv" and arxiv_id:
            if entry.get("abs_url") != f"https://arxiv.org/abs/{arxiv_id}":
                errors.append(f"citation has noncanonical abs URL: {key}")
            if entry.get("eprint_url") != f"https://arxiv.org/e-print/{arxiv_id}":
                errors.append(f"citation has noncanonical e-print URL: {key}")
        archive = resolve_record_path(str(entry.get("archive_path") or "."))
        if entry.get("archive_path") and not archive.is_file():
            errors.append(f"citation source archive is missing: {key}")
        elif archive.is_file() and entry.get("archive_sha256") and sha256_file(archive) != entry["archive_sha256"]:
            errors.append(f"citation source archive hash changed: {key}")
        source_dir = resolve_record_path(str(entry.get("source_dir") or "."))
        if entry.get("source_dir") and not source_dir.is_dir():
            errors.append(f"citation source directory is missing: {key}")
        if source_type == "book":
            book_source = resolve_record_path(str(entry.get("source_file") or "."))
            if entry.get("source_file") and not book_source.is_file():
                errors.append(f"book source is missing: {key}")
            elif book_source.is_file() and entry.get("source_sha256") and sha256_file(book_source) != entry["source_sha256"]:
                errors.append(f"book source hash changed: {key}")
        evidence = resolve_record_path(str(entry.get("evidence_file") or "."))
        if entry.get("evidence_file") and not evidence.is_file():
            errors.append(f"citation TeX evidence file is missing: {key}")
        elif evidence.is_file():
            if source_type == "arxiv":
                try:
                    evidence.relative_to(source_dir)
                except ValueError:
                    errors.append(f"citation evidence is outside extracted source: {key}")
            if entry.get("evidence_sha256") and sha256_file(evidence) != entry["evidence_sha256"]:
                errors.append(f"citation TeX evidence hash changed: {key}")
        bibtex = resolve_record_path(str(entry.get("bibtex_snapshot") or "."))
        if entry.get("bibtex_snapshot") and not bibtex.is_file():
            errors.append(f"BibTeX export snapshot is missing: {key}")
        elif bibtex.is_file() and entry.get("bibtex_sha256") and sha256_file(bibtex) != entry["bibtex_sha256"]:
            errors.append(f"BibTeX export snapshot hash changed: {key}")
        bibliography = resolve_record_path(str(entry.get("bibliography_path") or "."))
        if entry.get("bibliography_path") and not bibliography.is_file():
            errors.append(f"candidate bibliography is missing: {key}")
        elif bibliography.is_file() and bibtex.is_file():
            exported = bibtex.read_text(encoding="utf-8").strip()
            actual = bibliography.read_text(encoding="utf-8")
            if exported not in actual:
                errors.append(f"candidate bibliography does not contain the verbatim arXiv export: {key}")
    return errors


def _basic_tex_errors(output: Path) -> list[str]:
    if not output.is_file():
        return [f"output is missing: {output}"]
    text = output.read_text(encoding="utf-8")
    errors: list[str] = []
    for token in ("\\documentclass", "\\begin{document}", "\\end{document}"):
        if token not in text:
            errors.append(f"output lacks {token}")
    inventory = inventory_tex(output)
    occurrences = inventory.get("label_occurrences", [])
    duplicates = sorted({label for label in occurrences if occurrences.count(label) > 1})
    if duplicates:
        errors.append("duplicate labels: " + ", ".join(duplicates))
    unresolved = sorted(set(inventory["references"]) - set(inventory["labels"]))
    if unresolved:
        errors.append("unresolved TeX references: " + ", ".join(unresolved[:20]))
    return errors


def _compose_artifact_errors(state: dict) -> list[str]:
    work = Path(state["work_dir"])
    required = (
        "00-run-state.json", "01-critical-path.md", "02-framework.tex", "03-main-results.md",
        "03-main-results.json",
        "04-lemmas.md", "04-compression-ledger.md", "04-compression-ledger.json",
        "05-pre-shrink-inventory.json", "05.5-deleted-steps.md", "05.5-shrink-report.json",
        "06-definition-ledger.json", "07-terminology.md", "08-release-report.md",
        "references-registry.json",
    )
    errors = [f"required artifact is missing: {name}" for name in required if not (work / name).is_file()]
    shrink_report_path = work / "05.5-shrink-report.json"
    if shrink_report_path.is_file():
        shrink_report = json.loads(shrink_report_path.read_text(encoding="utf-8"))
        for field in (
            "pages_before", "pages_after", "pages_delta", "bytes_before", "bytes_after",
            "main_text_characters_before", "main_text_characters_after",
            "main_text_characters_delta",
        ):
            if shrink_report.get(field) is None:
                errors.append(f"shrink report misses {field}")
        main_delta = shrink_report.get("main_text_characters_delta")
        if isinstance(main_delta, (int, float)) and main_delta >= 0:
            errors.append("shrink pass did not reduce the main text")
    output = Path(state["output"])
    if not output.is_file():
        return errors
    inventory = inventory_tex(output)
    candidate_by_id = {unit["id"]: unit for unit in inventory["units"]}
    main_path = work / "03-main-results.json"
    if main_path.is_file():
        main_results = json.loads(main_path.read_text(encoding="utf-8")).get("main_results", [])
        if not 2 <= len(main_results) <= 4:
            errors.append("compose mode requires two to four locked main results")
        graph_ids = [item.get("graph_node_id") for item in main_results]
        candidate_labels = [item.get("candidate_label") for item in main_results]
        if len(graph_ids) != len(set(graph_ids)) or len(candidate_labels) != len(set(candidate_labels)):
            errors.append("compose main-result lock contains duplicate graph nodes or labels")
        for result in main_results:
            absent = [
                field for field in (
                    "graph_node_id", "candidate_label", "normalized_sha256",
                    "hypothesis_surface", "novelty_status", "novelty_evidence",
                ) if not result.get(field)
            ]
            if absent:
                errors.append("compose main-result record misses " + ", ".join(absent))
                continue
            if result["novelty_status"] not in {"CLEAR", "ADJACENT"}:
                errors.append(f"compose main result has unresolved novelty status: {result['graph_node_id']}")
            matches = [unit for unit in inventory["units"] if unit.get("label") == result["candidate_label"]]
            if not matches or all(unit.get("in_appendix") for unit in matches):
                errors.append(f"compose main result is missing from the paper body: {result['candidate_label']}")
            elif not any(
                unit.get("kind") == "statement"
                and unit.get("environment") not in NON_RESULT_ENVIRONMENTS
                and not unit.get("in_appendix") for unit in matches
            ):
                errors.append(f"compose main result is not a theorem-grade statement: {result['candidate_label']}")
            elif not any(unit.get("normalized_sha256") == result["normalized_sha256"] for unit in matches):
                errors.append(f"compose main result changed after it was locked: {result['candidate_label']}")
    compression_path = work / "04-compression-ledger.json"
    if compression_path.is_file():
        compression = json.loads(compression_path.read_text(encoding="utf-8"))
        compression_ids = [entry.get("unit_id") for entry in compression.get("entries", [])]
        if len(compression_ids) != len(set(compression_ids)):
            errors.append("compression ledger has duplicate unit ids")
        entries = {entry.get("unit_id"): entry for entry in compression.get("entries", [])}
        mathematical = {
            unit["id"] for unit in inventory["units"]
            if unit["kind"] in MATHEMATICAL_KINDS
        }
        missing = sorted(mathematical - set(entries))
        unresolved = sorted(
            unit_id for unit_id in mathematical
            if entries.get(unit_id, {}).get("classification") not in COMPRESSION_CLASSES
        )
        if missing:
            errors.append(f"compression ledger misses {len(missing)} candidate mathematical unit(s)")
        if unresolved:
            errors.append(f"compression ledger leaves {len(unresolved)} unit(s) unclassified")
        snapshot_path = work / "05-pre-shrink-inventory.json"
        snapshot_math: list[dict] = []
        if snapshot_path.is_file():
            snapshot_record = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot = snapshot_record.get("inventory", {})
            snapshot_math = [
                unit for unit in snapshot.get("units", []) if unit.get("kind") in MATHEMATICAL_KINDS
            ]
            absent_snapshot = [unit["id"] for unit in snapshot_math if unit["id"] not in entries]
            if absent_snapshot:
                errors.append(
                    f"compression ledger misses {len(absent_snapshot)} pre-shrink mathematical unit(s)"
                )
            archive_path = work / "05.5-deleted-steps.md"
            archive = archive_path.read_text(encoding="utf-8") if archive_path.is_file() else ""
            for unit in snapshot_math:
                entry = entries.get(unit["id"], {})
                classification = entry.get("classification")
                if classification == "CORE_INLINE":
                    final = candidate_by_id.get(unit["id"])
                    expected_hash = unit.get("raw_sha256") if unit.get("kind") == "statement" else unit.get("normalized_sha256")
                    actual_hash = final.get("raw_sha256") if final and unit.get("kind") == "statement" else (
                        final.get("normalized_sha256") if final else None
                    )
                    if not final or actual_hash != expected_hash:
                        errors.append(f"{unit['id']}: CORE_INLINE unit changed or disappeared during shrink")
                elif classification == "LEDGER_ONLY":
                    metadata_absent = [
                        field for field in ("source", "reason", "consumer") if not entry.get(field)
                    ]
                    if metadata_absent:
                        errors.append(f"{unit['id']}: LEDGER_ONLY misses {', '.join(metadata_absent)}")
                    archived = entry.get("archived_text") or ""
                    if normalize_tex(archived) != unit.get("normalized_text"):
                        errors.append(f"{unit['id']}: archived text is not the exact pre-shrink unit")
                    if entry.get("archived_text_sha256") != digest_text(archived):
                        errors.append(f"{unit['id']}: archived text SHA-256 is missing or incorrect")
                    if not entry.get("archive_anchor") or entry["archive_anchor"] not in archive:
                        errors.append(f"{unit['id']}: deleted-step archive anchor is missing")
                    if normalize_tex(archived) and normalize_tex(archived) not in normalize_tex(archive):
                        errors.append(f"{unit['id']}: exact archived text is absent from deleted-steps Markdown")
                    archived_raw = entry.get("archived_raw_text") or ""
                    if archived_raw != unit.get("raw_text"):
                        errors.append(f"{unit['id']}: archived raw TeX is not a verbatim copy")
                    if entry.get("archived_raw_sha256") != hashlib.sha256(archived_raw.encode("utf-8")).hexdigest():
                        errors.append(f"{unit['id']}: archived raw TeX SHA-256 is missing or incorrect")
                    if archived_raw and archived_raw not in archive:
                        errors.append(f"{unit['id']}: verbatim raw TeX is absent from deleted-steps Markdown")
                    if unit.get("label") and any(
                        final.get("label") == unit.get("label") for final in inventory["units"]
                    ):
                        errors.append(f"{unit['id']}: LEDGER_ONLY labeled unit still appears in final TeX")
                elif classification == "CITED":
                    if not entry.get("citation_key") or entry["citation_key"] not in inventory["citations"]:
                        errors.append(f"{unit['id']}: CITED unit lacks a citation present in the candidate")
                    if unit.get("kind") == "statement":
                        surviving = [
                            final for final in inventory["units"]
                            if (unit.get("label") and final.get("label") == unit.get("label"))
                            or final.get("id") == unit.get("id")
                        ]
                        if surviving and not any(
                            final.get("raw_sha256") == unit.get("raw_sha256") for final in surviving
                        ):
                            errors.append(f"{unit['id']}: surviving CITED statement changed bytewise")
                elif classification == "AUDITED_STYLE":
                    errors.extend(_audited_style_rewrite_errors(
                        entry, unit, inventory["units"]
                    ))
            if shrink_report_path.is_file():
                computed_before = _main_text_characters(snapshot)
                computed_after = _main_text_characters(inventory)
                if shrink_report.get("main_text_characters_before") != computed_before:
                    errors.append("shrink report pre-shrink main-text count is inconsistent")
                if shrink_report.get("main_text_characters_after") != computed_after:
                    errors.append("shrink report post-shrink main-text count is inconsistent")
                if shrink_report.get("main_text_characters_delta") != computed_after - computed_before:
                    errors.append("shrink report main-text delta is inconsistent")
                if shrink_report.get("bytes_before") != snapshot_record.get("bytes"):
                    errors.append("shrink report pre-shrink byte count is inconsistent")
                if shrink_report.get("bytes_after") != output.stat().st_size:
                    errors.append("shrink report post-shrink byte count is inconsistent")
            def match_key(unit: dict) -> tuple[str, ...]:
                if unit.get("label"):
                    return ("labeled", unit["kind"], str(unit["label"]), str(unit.get("normalized_sha256")))
                return ("unlabeled", unit["kind"], str(unit.get("normalized_sha256")))
            snapshot_counts = Counter(match_key(unit) for unit in snapshot_math)
            final_counts = Counter(match_key(unit) for unit in inventory["units"])
            removed_counts = Counter(
                match_key(unit) for unit in snapshot_math
                if not unit.get("label")
                and entries.get(unit["id"], {}).get("classification") == "LEDGER_ONLY"
            )
            for key, removed_count in removed_counts.items():
                if final_counts[key] > max(0, snapshot_counts[key] - removed_count):
                    errors.append("an unlabeled LEDGER_ONLY unit still appears in final TeX")
        texts = _tex_texts(inventory)
        for unit in inventory["units"]:
            if unit.get("kind") != "proof" or not unit.get("in_appendix"):
                continue
            entry = entries.get(unit["id"], {})
            if entry.get("classification") != "IMPORTANT_BODY_APPENDIX":
                errors.append(f"appendix proof must be classified IMPORTANT_BODY_APPENDIX: {unit['id']}")
                continue
            body_label = entry.get("body_label")
            appendix_label = entry.get("appendix_label")
            metadata_absent = [
                field for field in ("source", "reason", "consumer") if not entry.get(field)
            ]
            if metadata_absent:
                errors.append(
                    f"{unit['id']}: IMPORTANT_BODY_APPENDIX misses {', '.join(metadata_absent)}"
                )
            if appendix_label != unit.get("label") or not body_label:
                errors.append(f"appendix proof has incomplete body/appendix label mapping: {unit['id']}")
            elif not (_contains_label(texts, body_label) and _contains_label(texts, appendix_label)):
                errors.append(f"appendix proof mapping names a missing label: {unit['id']}")
            elif not _has_ref_near_label(texts, body_label, appendix_label):
                errors.append(f"body does not refer to appendix proof: {unit['id']}")
            elif not _has_ref_near_label(texts, appendix_label, body_label):
                errors.append(f"appendix proof does not refer back to body statement: {unit['id']}")
        for unit in snapshot_math:
            entry = entries.get(unit["id"], {})
            if entry.get("classification") != "IMPORTANT_BODY_APPENDIX" or unit.get("kind") != "statement":
                continue
            body_label = entry.get("body_label")
            body_matches = [candidate for candidate in inventory["units"] if candidate.get("label") == body_label]
            if not any(
                candidate.get("raw_sha256") == unit.get("raw_sha256")
                for candidate in body_matches
            ):
                errors.append(f"{unit['id']}: body statement changed during appendix factoring")
    definitions_path = work / "06-definition-ledger.json"
    if definitions_path.is_file():
        definitions = json.loads(definitions_path.read_text(encoding="utf-8")).get("definitions", [])
        concepts = [entry.get("concept") for entry in definitions if entry.get("concept")]
        defining_ids = [entry.get("defining_unit_id") for entry in definitions if entry.get("defining_unit_id")]
        notations = [entry.get("chosen_notation") for entry in definitions if entry.get("chosen_notation")]
        if len(concepts) != len(set(concepts)):
            errors.append("definition ledger has duplicate concepts")
        if len(defining_ids) != len(set(defining_ids)):
            errors.append("definition ledger maps one defining occurrence more than once")
        if len(notations) != len(set(notations)):
            errors.append("definition ledger assigns one notation to multiple concepts")
        explicit = {unit["id"] for unit in inventory["units"] if unit.get("environment") == "definition"}
        if explicit - set(defining_ids):
            errors.append(f"definition ledger misses {len(explicit - set(defining_ids))} explicit definition(s)")
        for entry in definitions:
            absent = [
                field for field in ("concept", "defining_unit_id", "chosen_term", "first_consumer_unit_id")
                if not entry.get(field)
            ]
            if absent:
                errors.append("definition ledger entry misses " + ", ".join(absent))
                continue
            defining = candidate_by_id.get(entry["defining_unit_id"])
            consumer = candidate_by_id.get(entry["first_consumer_unit_id"])
            if not defining or not consumer:
                errors.append(f"definition ledger has unknown defining/consumer unit for {entry['concept']}")
            elif defining.get("source_file") == consumer.get("source_file") and defining.get("line", 0) >= consumer.get("line", 0):
                errors.append(f"definition appears after first consumer: {entry['concept']}")
    return errors


def cmd_audit(args) -> None:
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    before = sha256_file(Path(state["source"])) if state.get("source") else None
    verify_source(state)
    verify_output(state, require_reservation=True)
    if state.get("mode") == "refine":
        report = audit_refinement(state_path)
        report["errors"].extend(_basic_tex_errors(Path(state["output"])))
    else:
        output = Path(state["output"])
        errors = _basic_tex_errors(output)
        if args.require_all_gates:
            errors.extend(_compose_artifact_errors(state))
        report = {"pass": not errors, "errors": errors, "warnings": []}
    reference_errors = _audit_references(state)
    report["errors"].extend(reference_errors)
    report["pass"] = not report["errors"]
    report["gate_status"] = {name: state.get("gates", {}).get(name, {}).get("status", "pending") for name in GATES}
    if args.require_all_gates:
        unfinished = [name for name, status in report["gate_status"].items() if status != "pass"]
        if unfinished:
            report["errors"].append("unfinished gates: " + ", ".join(unfinished))
            report["pass"] = False
        compile_report = _compile_tex(Path(state["output"]), 180)
        report["compile"] = compile_report
        if not compile_report["pass"]:
            report["errors"].append("isolated release compilation failed")
            report["pass"] = False
        shrink_report_path = Path(state["work_dir"]) / "05.5-shrink-report.json"
        if shrink_report_path.is_file():
            shrink_report = json.loads(shrink_report_path.read_text(encoding="utf-8"))
            if shrink_report.get("pages_after") != compile_report.get("pdf_pages"):
                report["errors"].append("shrink report final page count disagrees with release compile")
                report["pass"] = False
    after = sha256_file(Path(state["source"])) if state.get("source") else None
    report["baseline_unchanged_during_audit"] = before == after
    if before != after:
        report["errors"].append("baseline changed during audit")
        report["pass"] = False
    emit(report)
    if not report["pass"]:
        raise SystemExit(4)


def _compile_tex(tex: Path, timeout: int) -> dict:
    tex = tex.expanduser().absolute()
    if not tex.is_file() or tex.suffix.lower() != ".tex":
        raise ValueError(f"expected a TeX file: {tex}")
    latexmk = shutil.which("latexmk")
    pdflatex = shutil.which("pdflatex")
    if not latexmk and not pdflatex:
        raise RuntimeError("latexmk or pdflatex is required")
    def tree_snapshot(root: Path) -> dict[str, str]:
        skipped = {".git", ".lake", ".venv", "node_modules", "__pycache__"}
        result: dict[str, str] = {}
        for candidate in sorted(root.rglob("*")):
            relative = candidate.relative_to(root)
            if any(part in skipped for part in relative.parts):
                continue
            if candidate.is_symlink():
                result[str(relative)] = "link:" + os.readlink(candidate)
            elif candidate.is_file():
                result[str(relative)] = sha256_file(candidate)
        return result

    project_before = tree_snapshot(tex.parent)
    with tempfile.TemporaryDirectory(prefix="paper-writing-build-") as temp:
        outdir = Path(temp)
        environment = os.environ.copy()
        for variable in ("TEXINPUTS", "BIBINPUTS", "BSTINPUTS"):
            existing = environment.get(variable, "")
            environment[variable] = f"{tex.parent}//:{existing}"
        if latexmk:
            command = [
                latexmk, "-pdf", "-halt-on-error", "-file-line-error",
                "-interaction=nonstopmode", "-latexoption=-no-shell-escape",
                f"-outdir={outdir}", str(tex),
            ]
            result = subprocess.run(
                command, cwd=outdir, env=environment, text=True, capture_output=True, timeout=timeout,
            )
        else:
            command = [
                pdflatex, "-no-shell-escape", "-halt-on-error", "-file-line-error",
                "-interaction=nonstopmode", f"-output-directory={outdir}", str(tex),
            ]
            first = subprocess.run(
                command, cwd=outdir, env=environment, text=True, capture_output=True, timeout=timeout,
            )
            result = first if first.returncode else subprocess.run(
                command, cwd=outdir, env=environment, text=True, capture_output=True, timeout=timeout,
            )
        log_path = outdir / f"{tex.stem}.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        bad_patterns = (
            "LaTeX Warning: There were undefined references",
            "LaTeX Warning: There were undefined citations",
            "multiply defined",
            "Rerun to get cross-references right",
        )
        warnings = [pattern for pattern in bad_patterns if pattern.lower() in log.lower()]
        pdf = outdir / f"{tex.stem}.pdf"
        project_after = tree_snapshot(tex.parent)
        changed_project_files = sorted(
            path for path in set(project_before) | set(project_after)
            if project_before.get(path) != project_after.get(path)
        )
        report = {
            "pass": result.returncode == 0 and pdf.is_file() and pdf.stat().st_size > 0 and not warnings
                    and not changed_project_files,
            "engine": Path(command[0]).name,
            "returncode": result.returncode,
            "warnings": warnings,
            "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0,
            "isolated_output": str(outdir),
            "project_changes": changed_project_files,
        }
        if result.returncode:
            report["tail"] = (result.stdout + "\n" + result.stderr)[-5000:]
        pdfinfo = shutil.which("pdfinfo")
        if pdfinfo and pdf.is_file():
            info = subprocess.run([pdfinfo, str(pdf)], text=True, capture_output=True)
            pages = next(
                (line.split(":", 1)[1].strip() for line in info.stdout.splitlines() if line.startswith("Pages:")),
                None,
            )
            report["pdf_pages"] = int(pages) if pages and pages.isdigit() else None
        return report


def cmd_compile(args) -> None:
    report = _compile_tex(Path(args.tex), args.timeout)
    emit(report)
    if not report["pass"]:
        raise SystemExit(5)


def cmd_freeze_shrink(args) -> None:
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    verify_source(state)
    verify_output(state, require_reservation=True)
    if state.get("gates", {}).get("draft", {}).get("status") != "pass":
        raise ValueError("freeze-shrink requires the draft gate to pass first")
    if state.get("gates", {}).get("compression", {}).get("status") == "pass":
        raise ValueError("compression already passed; fail/reopen it before replacing the snapshot")
    destination = Path(state["work_dir"]) / "05-pre-shrink-inventory.json"
    if destination.exists():
        raise FileExistsError(destination)
    output = Path(state["output"])
    pages = args.pages
    if pages is None:
        compile_report = _compile_tex(output, 180)
        if not compile_report["pass"] or not compile_report.get("pdf_pages"):
            raise RuntimeError("clean pre-shrink compilation with a page count is required")
        pages = compile_report["pdf_pages"]
    draft_inventory = inventory_tex(output)
    record = {
        "schema_version": 1,
        "source": str(output),
        "source_sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "characters": len(output.read_text(encoding="utf-8")),
        "main_text_characters": _main_text_characters(draft_inventory),
        "pages": pages,
        "inventory": draft_inventory,
    }
    write_json(destination, record)
    emit({"snapshot": str(destination), "sha256": record["source_sha256"], "bytes": record["bytes"], "pages": record["pages"]})


def cmd_safe_extract(args) -> None:
    safe_extract(Path(args.archive), Path(args.destination))
    emit({"archive": str(Path(args.archive).absolute()), "destination": str(Path(args.destination).absolute())})


def cmd_shrink_stats(args) -> None:
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    output = Path(state["output"])
    snapshot_path = Path(state["work_dir"]) / "05-pre-shrink-inventory.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.is_file() else None
    baseline = Path(args.baseline).expanduser().absolute() if args.baseline else None
    if snapshot:
        before_inventory = snapshot["inventory"]
        bytes_before = snapshot["bytes"]
        characters_before = snapshot.get("characters")
        baseline_name = str(snapshot_path)
        pages_before = snapshot.get("pages")
        main_text_before = snapshot.get("main_text_characters")
    elif baseline and baseline.is_file():
        before_text = baseline.read_text(encoding="utf-8")
        before_inventory = inventory_tex(baseline)
        bytes_before = baseline.stat().st_size
        characters_before = len(before_text)
        baseline_name = str(baseline)
        pages_before = None
        main_text_before = _main_text_characters(before_inventory)
    else:
        raise ValueError("shrink-stats needs paperctl freeze-shrink or an explicit --baseline")
    if not output.is_file():
        raise ValueError("shrink-stats output TeX is missing")
    after_text = output.read_text(encoding="utf-8")
    after_inventory = inventory_tex(output)
    main_text_after = _main_text_characters(after_inventory)
    pages_after = args.pages_after
    if pages_after is None:
        compile_report = _compile_tex(output, 180)
        if not compile_report["pass"] or not compile_report.get("pdf_pages"):
            raise RuntimeError("clean post-shrink compilation with a page count is required")
        pages_after = compile_report["pdf_pages"]
    report = {
        "baseline": baseline_name, "output": str(output),
        "bytes_before": bytes_before, "bytes_after": output.stat().st_size,
        "bytes_delta": output.stat().st_size - bytes_before,
        "characters_before": characters_before, "characters_after": len(after_text),
        "characters_delta": (len(after_text) - characters_before) if characters_before is not None else None,
        "pages_before": pages_before, "pages_after": pages_after,
        "pages_delta": (pages_after - pages_before) if pages_before is not None else None,
        "main_text_characters_before": main_text_before,
        "main_text_characters_after": main_text_after,
        "main_text_characters_delta": (
            main_text_after - main_text_before if main_text_before is not None else None
        ),
        "units_before": before_inventory["counts"], "units_after": after_inventory["counts"],
        "note": "A negative delta records shrinkage; it is not a release target and never authorizes semantic loss.",
    }
    write_json(Path(state["work_dir"]) / "05.5-shrink-report.json", report)
    emit(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("next-version", help="resolve the mandatory next TeX version")
    command.add_argument("source")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_next_version)

    command = sub.add_parser("init-refine", help="freeze a baseline and create its exclusive next version")
    command.add_argument("source")
    command.add_argument("--work-dir")
    command.add_argument("--dry-run", action="store_true")
    command.set_defaults(func=cmd_init_refine)

    command = sub.add_parser("init-compose", help="initialize a new-paper gated run")
    command.add_argument("--output", required=True)
    command.add_argument("--work-dir")
    command.set_defaults(func=cmd_init_compose)

    command = sub.add_parser("inventory", help="inventory TeX coverage units")
    command.add_argument("tex")
    command.add_argument("--out")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_inventory)

    command = sub.add_parser("critical-path", help="extract deepest paths from graph JSON")
    command.add_argument("graph")
    command.add_argument("--select", help="comma-separated terminal ids")
    command.add_argument("--out")
    command.add_argument("--json-out")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_critical_path)

    command = sub.add_parser("lock-main", help="freeze baseline theorem labels as main results")
    command.add_argument("--state", required=True)
    command.add_argument("--label", action="append")
    command.add_argument("--unit-id", action="append", help="lock an unlabeled baseline inventory unit")
    command.set_defaults(func=cmd_lock_main)

    command = sub.add_parser("gate", help="record one gate outcome")
    command.add_argument("--state", required=True)
    command.add_argument("--name", choices=GATES, required=True)
    command.add_argument("--status", choices=("pass", "fail", "pending"), required=True)
    command.add_argument("--evidence", action="append")
    command.set_defaults(func=cmd_gate)

    command = sub.add_parser("resume", help="report the first unpassed gate")
    command.add_argument("--state", required=True)
    command.set_defaults(func=cmd_resume)

    command = sub.add_parser("claim-output", help="adopt an intentional atomic editor save")
    command.add_argument("--state", required=True)
    command.set_defaults(func=cmd_claim_output)

    command = sub.add_parser("audit", help="read-only deterministic preservation audit")
    command.add_argument("--state", required=True)
    command.add_argument("--require-all-gates", action="store_true")
    command.set_defaults(func=cmd_audit)

    command = sub.add_parser("compile", help="compile a TeX candidate in an isolated directory")
    command.add_argument("tex")
    command.add_argument("--timeout", type=int, default=180)
    command.set_defaults(func=cmd_compile)

    command = sub.add_parser("safe-extract-arxiv", help="safely extract a downloaded arXiv source archive")
    command.add_argument("archive")
    command.add_argument("destination")
    command.set_defaults(func=cmd_safe_extract)

    command = sub.add_parser("freeze-shrink", help="freeze the complete draft before deleting or moving steps")
    command.add_argument("--state", required=True)
    command.add_argument("--pages", type=int, help="optional page count from the clean pre-shrink build")
    command.set_defaults(func=cmd_freeze_shrink)

    command = sub.add_parser("shrink-stats", help="report non-normative baseline/candidate size deltas")
    command.add_argument("--state", required=True)
    command.add_argument("--baseline", help="required for compose mode; defaults to refine source")
    command.add_argument("--pages-after", type=int, help="optional page count from the clean post-shrink build")
    command.set_defaults(func=cmd_shrink_stats)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, json.JSONDecodeError) as error:
        print(f"paperctl: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
