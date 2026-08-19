from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from .tex_inventory import digest_text, inventory_tex, normalize_tex
from .versioning import sha256_file


ALLOWED_DISPOSITIONS = {
    "auto", "retained", "moved", "merged", "cited", "ledger-only", "body-appendix",
}
MAIN_ALLOWED = {"auto", "retained"}
COMPRESSION_CLASSES = {
    "CORE_INLINE", "IMPORTANT_BODY_APPENDIX", "CITED", "LEDGER_ONLY", "AUDITED_STYLE",
}
NON_RESULT_ENVIRONMENTS = {"definition", "remark", "example", "assumption", "axiom", "proof"}
MATHEMATICAL_KINDS = {
    "statement", "proof", "display", "equation", "align", "gather", "multline",
    "figure", "table", "environment",
}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_matches(unit: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if unit["kind"] == "citation":
        return unit["label"] in candidate["citations"]
    if unit["kind"] == "include":
        return unit["title"] in candidate["includes"]
    if unit.get("label"):
        matching = [item for item in candidate["units"] if item.get("label") == unit["label"]]
        return any(item["normalized_sha256"] == unit["normalized_sha256"] for item in matching)
    if unit["kind"] == "section":
        return any(
            item["kind"] == "section" and item["title"] == unit["title"]
            for item in candidate["units"]
        )
    return any(
        item["kind"] == unit["kind"] and item["normalized_sha256"] == unit["normalized_sha256"]
        for item in candidate["units"]
    )


def _match_key(unit: dict[str, Any]) -> tuple[str, ...]:
    if unit["kind"] == "citation":
        return ("citation", str(unit.get("label")))
    if unit["kind"] == "include":
        return ("include", str(unit.get("title")))
    if unit.get("label"):
        return (
            "labeled", unit["kind"], str(unit["label"]), str(unit["normalized_sha256"]),
        )
    if unit["kind"] == "section":
        return ("section", str(unit.get("level")), str(unit.get("title")))
    return ("unlabeled", unit["kind"], str(unit["normalized_sha256"]))


def _tex_texts(inventory: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for entry in inventory.get("source_files", []):
        path = Path(entry.get("path", ""))
        if entry.get("kind") in {"tex", "input", "include", "subfile"} and path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    return texts


def _contains_label(candidate_texts: list[str], label: str) -> bool:
    return any(f"\\label{{{label}}}" in text for text in candidate_texts)


def _has_ref_near_label(candidate_texts: list[str], label: str, target: str, radius: int = 1500) -> bool:
    marker = f"\\label{{{label}}}"
    for candidate_text in candidate_texts:
        index = candidate_text.find(marker)
        if index < 0:
            continue
        window = candidate_text[max(0, index - radius): index + radius]
        if any(f"\\{command}{{{target}}}" in window for command in ("ref", "eqref", "pageref", "autoref", "cref", "Cref")):
            return True
    return False


def _two_semantic_passes(entry: dict[str, Any]) -> bool:
    passes = [
        audit for audit in entry.get("semantic_audits", [])
        if audit.get("verdict") == "PASS" and audit.get("evidence")
    ]
    return len({audit.get("auditor") for audit in passes if audit.get("auditor")}) >= 2


def _audited_style_rewrite_errors(
    entry: dict[str, Any],
    original_unit: dict[str, Any] | None,
    candidate_units: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    unit_id = entry.get("unit_id") or "<unknown>"
    if not original_unit or original_unit.get("kind") != "proof":
        errors.append(f"{unit_id}: AUDITED_STYLE is allowed only for a frozen proof unit")
        return errors
    absent = [field for field in ("reason", "source", "consumer") if not entry.get(field)]
    if absent:
        errors.append(f"{unit_id}: AUDITED_STYLE misses {', '.join(absent)}")
    if not _two_semantic_passes(entry):
        errors.append(f"{unit_id}: AUDITED_STYLE needs two independent semantic PASS audits")
    replacement_label = entry.get("replacement_label")
    replacement_unit_id = entry.get("replacement_unit_id")
    if not replacement_label and not replacement_unit_id:
        errors.append(f"{unit_id}: AUDITED_STYLE needs a replacement label or unit id")
        return errors
    matches = [
        unit for unit in candidate_units
        if unit.get("kind") == "proof"
        and (
            (replacement_label and unit.get("label") == replacement_label)
            or (replacement_unit_id and unit.get("id") == replacement_unit_id)
        )
    ]
    if not matches:
        errors.append(f"{unit_id}: audited proof-style replacement is missing")
    return errors


def _main_text_characters(inventory: dict[str, Any]) -> int:
    counted = {
        "section", "statement", "proof", "display", "equation", "align", "gather",
        "multline", "figure", "table", "environment", "footnote", "prose",
    }
    return sum(
        len(unit.get("raw_text") or unit.get("normalized_text") or "")
        for unit in inventory.get("units", [])
        if unit.get("kind") in counted and not unit.get("in_appendix")
    )


def audit_refinement(state_path: Path) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    source = Path(state["source"])
    candidate_path = Path(state["output"])
    work = Path(state["work_dir"])
    if not source.exists():
        errors.append(f"baseline source is missing: {source}")
    elif sha256_file(source) != state.get("source_sha256"):
        errors.append("baseline source hash changed")
    if not candidate_path.exists():
        errors.append(f"candidate is missing: {candidate_path}")
        return {"pass": False, "errors": errors, "warnings": warnings}
    if source.exists():
        try:
            if source.samefile(candidate_path):
                errors.append("candidate aliases the baseline source")
        except FileNotFoundError:
            pass

    baseline = json.loads((work / "00-baseline-inventory.json").read_text(encoding="utf-8"))
    ledger = json.loads((work / "05-coverage-ledger.json").read_text(encoding="utf-8"))
    compression = json.loads((work / "04-compression-ledger.json").read_text(encoding="utf-8"))
    main_lock = json.loads((work / "00-main-results-lock.json").read_text(encoding="utf-8"))
    candidate = inventory_tex(candidate_path)
    candidate_texts = _tex_texts(candidate)

    for source_entry in baseline.get("source_files", []):
        source_path = Path(source_entry.get("path", ""))
        expected_hash = source_entry.get("sha256")
        if source_entry.get("missing"):
            continue
        if not source_path.is_file():
            errors.append(f"baseline source-tree file is missing: {source_path}")
        elif expected_hash and sha256_file(source_path) != expected_hash:
            errors.append(f"baseline source-tree file changed: {source_path}")

    baseline_by_id = {item["id"]: item for item in baseline["units"]}
    entries = ledger.get("entries", [])
    ledger_ids = [entry.get("unit_id") for entry in entries]
    if len(ledger_ids) != len(set(ledger_ids)):
        errors.append("coverage ledger has duplicate unit ids")
    missing_ledger = sorted(set(baseline_by_id) - set(ledger_ids))
    extra_ledger = sorted(set(ledger_ids) - set(baseline_by_id))
    if missing_ledger:
        errors.append(f"coverage ledger misses {len(missing_ledger)} baseline unit(s)")
    if extra_ledger:
        errors.append(f"coverage ledger has {len(extra_ledger)} unknown unit(s)")

    entry_by_id = {entry.get("unit_id"): entry for entry in entries}
    compression_by_id = {entry.get("unit_id"): entry for entry in compression.get("entries", [])}
    available_matches = Counter(_match_key(unit) for unit in candidate["units"])
    if state.get("gates", {}).get("compression", {}).get("status") == "pass":
        compression_ids = [entry.get("unit_id") for entry in compression.get("entries", [])]
        if len(compression_ids) != len(set(compression_ids)):
            errors.append("compression ledger has duplicate unit ids")
        shrink_path = work / "05-pre-shrink-inventory.json"
        shrink_record: dict[str, Any] = {}
        if not shrink_path.is_file():
            errors.append("pre-shrink inventory is missing; run paperctl freeze-shrink after the full draft")
            shrink_inventory = {"units": []}
        else:
            shrink_record = json.loads(shrink_path.read_text(encoding="utf-8"))
            shrink_inventory = shrink_record.get("inventory", {})
        shrink_report_path = work / "05.5-shrink-report.json"
        if not shrink_report_path.is_file():
            errors.append("shrink report is missing; run paperctl shrink-stats after compression")
        else:
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
            computed_before = _main_text_characters(shrink_inventory)
            computed_after = _main_text_characters(candidate)
            if shrink_report.get("main_text_characters_before") != computed_before:
                errors.append("shrink report pre-shrink main-text count is inconsistent")
            if shrink_report.get("main_text_characters_after") != computed_after:
                errors.append("shrink report post-shrink main-text count is inconsistent")
            if shrink_report.get("main_text_characters_delta") != computed_after - computed_before:
                errors.append("shrink report main-text delta is inconsistent")
            if shrink_report.get("bytes_before") != shrink_record.get("bytes"):
                errors.append("shrink report pre-shrink byte count is inconsistent")
            if shrink_report.get("bytes_after") != candidate_path.stat().st_size:
                errors.append("shrink report post-shrink byte count is inconsistent")
        shrink_math = [
            unit for unit in shrink_inventory.get("units", []) if unit.get("kind") in MATHEMATICAL_KINDS
        ]
        compression_units = dict(baseline_by_id)
        compression_units.update({unit["id"]: unit for unit in shrink_math})
        missing_shrink_records = sorted(
            unit["id"] for unit in shrink_math if unit["id"] not in compression_by_id
        )
        if missing_shrink_records:
            errors.append(
                f"compression ledger misses {len(missing_shrink_records)} pre-shrink mathematical unit(s)"
            )
        for unit_id, entry in compression_by_id.items():
            classification = entry.get("classification")
            if classification not in COMPRESSION_CLASSES:
                errors.append(f"{unit_id}: compression class is unresolved: {classification!r}")
        exact_candidate = Counter(_match_key(unit) for unit in candidate["units"])
        deleted_archive_path = work / "05.5-deleted-steps.md"
        deleted_archive = (
            deleted_archive_path.read_text(encoding="utf-8") if deleted_archive_path.is_file() else ""
        )
        for unit_id, entry in compression_by_id.items():
            classification = entry.get("classification")
            original_unit = compression_units.get(unit_id)
            if classification == "CORE_INLINE" and original_unit:
                if original_unit.get("kind") == "statement":
                    candidates = [
                        unit for unit in candidate["units"]
                        if unit.get("id") == original_unit.get("id")
                    ]
                    if not any(
                        unit.get("raw_sha256") == original_unit.get("raw_sha256") for unit in candidates
                    ):
                        errors.append(f"{unit_id}: CORE_INLINE statement changed bytewise or disappeared")
                else:
                    key = _match_key(original_unit)
                    if exact_candidate[key] <= 0:
                        errors.append(f"{unit_id}: CORE_INLINE unit changed or disappeared during shrink")
                    else:
                        exact_candidate[key] -= 1
            elif classification == "CITED":
                citation_key = entry.get("citation_key")
                if not citation_key or citation_key not in candidate.get("citations", []):
                    errors.append(f"{unit_id}: CITED unit lacks a citation present in the candidate")
                if not entry.get("reason") or not entry.get("source"):
                    errors.append(f"{unit_id}: CITED unit needs source and reason")
                if original_unit and original_unit.get("kind") == "statement":
                    surviving = [
                        unit for unit in candidate["units"]
                        if (original_unit.get("label") and unit.get("label") == original_unit.get("label"))
                        or unit.get("id") == original_unit.get("id")
                    ]
                    if surviving and not any(
                        unit.get("raw_sha256") == original_unit.get("raw_sha256") for unit in surviving
                    ):
                        errors.append(f"{unit_id}: surviving CITED statement changed bytewise")
            elif classification == "LEDGER_ONLY":
                if not original_unit:
                    errors.append(f"{unit_id}: LEDGER_ONLY record has no pre-shrink/baseline unit")
                    continue
                required = (
                    "archive_anchor", "reason", "source", "consumer",
                    "archived_text", "archived_text_sha256",
                    "archived_raw_text", "archived_raw_sha256",
                )
                absent = [field for field in required if not entry.get(field)]
                if absent:
                    errors.append(f"{unit_id}: compression record misses {', '.join(absent)}")
                    continue
                archived_text = entry["archived_text"]
                if normalize_tex(archived_text) != original_unit.get("normalized_text"):
                    errors.append(f"{unit_id}: archived text is not the exact pre-shrink unit")
                if entry.get("archived_text_sha256") != digest_text(archived_text):
                    errors.append(f"{unit_id}: archived text SHA-256 is missing or incorrect")
                archived_raw = entry.get("archived_raw_text") or ""
                if archived_raw != original_unit.get("raw_text"):
                    errors.append(f"{unit_id}: archived raw TeX is not a verbatim copy of the omitted unit")
                if entry.get("archived_raw_sha256") != hashlib.sha256(archived_raw.encode("utf-8")).hexdigest():
                    errors.append(f"{unit_id}: archived raw TeX SHA-256 is missing or incorrect")
                if entry["archive_anchor"] not in deleted_archive:
                    errors.append(f"{unit_id}: compression archive anchor is missing from Markdown")
                if normalize_tex(archived_text) not in normalize_tex(deleted_archive):
                    errors.append(f"{unit_id}: exact archived text is absent from deleted-steps Markdown")
                if archived_raw and archived_raw not in deleted_archive:
                    errors.append(f"{unit_id}: verbatim raw TeX is absent from deleted-steps Markdown")
                if original_unit.get("label") and any(
                    unit.get("label") == original_unit.get("label") for unit in candidate["units"]
                ):
                    errors.append(f"{unit_id}: LEDGER_ONLY labeled unit still appears in final TeX")
            elif classification == "IMPORTANT_BODY_APPENDIX":
                metadata_absent = [
                    field for field in ("reason", "source", "consumer") if not entry.get(field)
                ]
                if metadata_absent:
                    errors.append(
                        f"{unit_id}: IMPORTANT_BODY_APPENDIX misses {', '.join(metadata_absent)}"
                    )
                body_label = entry.get("body_label")
                appendix_label = entry.get("appendix_label")
                if not body_label or not appendix_label:
                    errors.append(f"{unit_id}: IMPORTANT_BODY_APPENDIX needs body_label and appendix_label")
                elif not (_contains_label(candidate_texts, body_label) and _contains_label(candidate_texts, appendix_label)):
                    errors.append(f"{unit_id}: body or appendix label is missing")
                else:
                    body_units = [unit for unit in candidate["units"] if unit.get("label") == body_label]
                    appendix_units = [unit for unit in candidate["units"] if unit.get("label") == appendix_label]
                    if not body_units or all(unit.get("in_appendix") for unit in body_units):
                        errors.append(f"{unit_id}: body statement label is not in the body")
                    if not appendix_units or not any(unit.get("in_appendix") for unit in appendix_units):
                        errors.append(f"{unit_id}: appendix proof label is not in an appendix")
                    if not _has_ref_near_label(candidate_texts, body_label, appendix_label):
                        errors.append(f"{unit_id}: body does not refer to appendix proof")
                    if not _has_ref_near_label(candidate_texts, appendix_label, body_label):
                        errors.append(f"{unit_id}: appendix proof does not refer back to body statement")
                    if original_unit and original_unit.get("kind") == "statement":
                        body_matches = [
                            unit for unit in body_units
                            if unit.get("raw_sha256") == original_unit.get("raw_sha256")
                        ]
                        if not body_matches:
                            errors.append(f"{unit_id}: body statement changed during appendix factoring")
            elif classification == "AUDITED_STYLE":
                errors.extend(_audited_style_rewrite_errors(
                    entry, original_unit, candidate["units"]
                ))
        snapshot_key_counts = Counter(_match_key(unit) for unit in shrink_math)
        candidate_key_counts = Counter(_match_key(unit) for unit in candidate["units"])
        ledger_only_key_counts = Counter(
            _match_key(compression_units[unit_id])
            for unit_id, entry in compression_by_id.items()
            if entry.get("classification") == "LEDGER_ONLY"
            and unit_id in compression_units
            and not compression_units[unit_id].get("label")
        )
        for key, removed_count in ledger_only_key_counts.items():
            # A refinement may remove a baseline unit while producing the complete draft,
            # before the separate shrink snapshot is frozen.  Such a key has snapshot count
            # zero; its permitted final multiplicity is zero, not a negative number.
            allowed = max(0, snapshot_key_counts[key] - removed_count)
            if candidate_key_counts[key] > allowed:
                errors.append("an unlabeled LEDGER_ONLY unit still appears in final TeX")
        appendix_proof_labels = {
            entry.get("appendix_label") for entry in compression_by_id.values()
            if entry.get("classification") == "IMPORTANT_BODY_APPENDIX" and entry.get("appendix_label")
        }
        for candidate_unit in candidate["units"]:
            if candidate_unit.get("kind") == "proof" and candidate_unit.get("in_appendix"):
                label = candidate_unit.get("label")
                if not label:
                    errors.append(f"appendix proof at {candidate_unit.get('source_file')}:{candidate_unit.get('line')} needs a label")
                elif label not in appendix_proof_labels:
                    errors.append(f"orphan appendix proof is absent from compression ledger: {label}")
        # A unit introduced after the frozen full draft must itself be classified. This
        # forces the compression pass to be rerun instead of silently growing new math.
        shrink_matches = Counter(_match_key(unit) for unit in shrink_math)
        untracked_candidate: list[str] = []
        for candidate_unit in candidate["units"]:
            if candidate_unit.get("kind") not in MATHEMATICAL_KINDS:
                continue
            key = _match_key(candidate_unit)
            if shrink_matches[key] > 0:
                shrink_matches[key] -= 1
            elif candidate_unit.get("id") in compression_by_id:
                continue
            elif candidate_unit.get("label") in appendix_proof_labels:
                continue
            else:
                untracked_candidate.append(candidate_unit["id"])
        if untracked_candidate:
            errors.append(
                f"candidate has {len(untracked_candidate)} post-draft mathematical unit(s) absent from compression ledger"
            )
    for unit_id, unit in baseline_by_id.items():
        entry = entry_by_id.get(unit_id)
        if entry is None:
            continue
        disposition = entry.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            errors.append(f"{unit_id}: invalid disposition {disposition!r}")
            continue
        if disposition == "auto":
            key = _match_key(unit)
            if available_matches[key] <= 0:
                errors.append(f"{unit_id}: changed or missing but still classified auto")
            else:
                available_matches[key] -= 1
        elif disposition == "retained":
            target = entry.get("target_label") or unit.get("label")
            if target and not _contains_label(candidate_texts, target):
                errors.append(f"{unit_id}: retained target label is missing: {target}")
            if not entry.get("evidence") or not entry.get("reason"):
                errors.append(f"{unit_id}: retained rewritten unit needs evidence and reason")
            targets = [item for item in candidate["units"] if target and item.get("label") == target]
            changed_statement = unit.get("kind") == "statement" and not any(
                item.get("normalized_sha256") == unit.get("normalized_sha256") for item in targets
            )
            if changed_statement and not _two_semantic_passes(entry):
                errors.append(f"{unit_id}: rewritten statement needs two independent semantic PASS audits")
        elif disposition in {"moved", "merged"}:
            if not entry.get("target_label") or not entry.get("reason"):
                errors.append(f"{unit_id}: {disposition} needs target_label and reason")
            elif not _contains_label(candidate_texts, entry["target_label"]):
                errors.append(f"{unit_id}: target label {entry['target_label']} is missing")
            targets = [
                item for item in candidate["units"] if item.get("label") == entry.get("target_label")
            ]
            changed_statement = unit.get("kind") == "statement" and not any(
                item.get("normalized_sha256") == unit.get("normalized_sha256") for item in targets
            )
            if changed_statement and not _two_semantic_passes(entry):
                errors.append(f"{unit_id}: rewritten statement needs two independent semantic PASS audits")
        elif disposition == "cited":
            if not entry.get("citation_key") or not entry.get("reason"):
                errors.append(f"{unit_id}: cited needs citation_key and reason")
            elif entry["citation_key"] not in candidate["citations"]:
                errors.append(f"{unit_id}: citation {entry['citation_key']} is absent")
            comp = compression_by_id.get(unit_id)
            if comp and comp.get("classification") != "CITED":
                errors.append(f"{unit_id}: cited disposition/classification disagree")
        elif disposition == "ledger-only":
            comp = compression_by_id.get(unit_id)
            if not comp:
                errors.append(f"{unit_id}: ledger-only item is absent from compression ledger")
            else:
                required = (
                    "archive_anchor", "reason", "source", "consumer",
                    "archived_text", "archived_text_sha256",
                    "archived_raw_text", "archived_raw_sha256",
                )
                absent = [field for field in required if not comp.get(field)]
                if absent:
                    errors.append(f"{unit_id}: compression record misses {', '.join(absent)}")
                archive_path = work / "05.5-deleted-steps.md"
                archive = archive_path.read_text(encoding="utf-8") if archive_path.is_file() else ""
                if comp.get("archive_anchor") and comp["archive_anchor"] not in archive:
                    errors.append(f"{unit_id}: compression archive anchor is missing from Markdown")
                archived_text = comp.get("archived_text") or ""
                if normalize_tex(archived_text) != unit.get("normalized_text"):
                    errors.append(f"{unit_id}: archived text is not the exact omitted baseline unit")
                if comp.get("archived_text_sha256") != digest_text(archived_text):
                    errors.append(f"{unit_id}: archived text SHA-256 is missing or incorrect")
                archived_raw = comp.get("archived_raw_text") or ""
                if archived_raw != unit.get("raw_text"):
                    errors.append(f"{unit_id}: archived raw TeX is not a verbatim copy of the omitted unit")
                if comp.get("archived_raw_sha256") != hashlib.sha256(archived_raw.encode("utf-8")).hexdigest():
                    errors.append(f"{unit_id}: archived raw TeX SHA-256 is missing or incorrect")
                if normalize_tex(archived_text) and normalize_tex(archived_text) not in normalize_tex(archive):
                    errors.append(f"{unit_id}: exact archived text is absent from deleted-steps Markdown")
                if archived_raw and archived_raw not in archive:
                    errors.append(f"{unit_id}: verbatim raw TeX is absent from deleted-steps Markdown")
                if comp.get("classification") != "LEDGER_ONLY":
                    errors.append(f"{unit_id}: ledger-only disposition/classification disagree")
        elif disposition == "body-appendix":
            comp = compression_by_id.get(unit_id)
            if not comp:
                errors.append(f"{unit_id}: body-appendix item is absent from compression ledger")
                continue
            body_label = comp.get("body_label")
            appendix_label = comp.get("appendix_label")
            if not body_label or not appendix_label:
                errors.append(f"{unit_id}: body-appendix needs body_label and appendix_label")
            elif not (_contains_label(candidate_texts, body_label) and _contains_label(candidate_texts, appendix_label)):
                errors.append(f"{unit_id}: body or appendix label is missing")
            else:
                body_units = [item for item in candidate["units"] if item.get("label") == body_label]
                appendix_units = [item for item in candidate["units"] if item.get("label") == appendix_label]
                if not body_units or all(item.get("in_appendix") for item in body_units):
                    errors.append(f"{unit_id}: body statement label is not in the body")
                if not appendix_units or not any(item.get("in_appendix") for item in appendix_units):
                    errors.append(f"{unit_id}: appendix proof label is not in an appendix")
                if not _has_ref_near_label(candidate_texts, body_label, appendix_label):
                    errors.append(f"{unit_id}: body does not refer to appendix proof")
                if not _has_ref_near_label(candidate_texts, appendix_label, body_label):
                    errors.append(f"{unit_id}: appendix proof does not refer back to body statement")
            if comp.get("classification") != "IMPORTANT_BODY_APPENDIX":
                errors.append(f"{unit_id}: body-appendix disposition/classification disagree")

    locked = main_lock.get("main_results", [])
    if not locked:
        errors.append("main-results lock is empty")
    for item in locked:
        unit_id = item.get("unit_id")
        unit = baseline_by_id.get(unit_id)
        if not unit:
            errors.append(f"main-result lock references unknown unit: {unit_id}")
            continue
        if unit.get("kind") != "statement" or unit.get("environment") in NON_RESULT_ENVIRONMENTS:
            errors.append(f"main-result lock contains a non-theorem unit: {unit_id}")
            continue
        disposition = entry_by_id.get(unit_id, {}).get("disposition")
        if disposition not in MAIN_ALLOWED:
            errors.append(f"main result {unit_id} has forbidden disposition {disposition!r}")
        if compression_by_id.get(unit_id, {}).get("classification") in {"CITED", "LEDGER_ONLY"}:
            errors.append(f"main result {unit_id} cannot be cited away or ledger-only")
        target_label = item.get("label") or item.get("candidate_label")
        if target_label:
            matches = [candidate_unit for candidate_unit in candidate["units"]
                       if candidate_unit.get("label") == target_label]
        else:
            matches = [
                candidate_unit for candidate_unit in candidate["units"]
                if candidate_unit.get("normalized_sha256") == item.get("normalized_sha256")
                and candidate_unit.get("environment") == item.get("environment")
            ]
        if not matches:
            errors.append(f"main result label is missing: {item.get('label')}")
            continue
        if all(match.get("in_appendix") for match in matches):
            errors.append(f"main result {unit_id} was moved out of the paper body")
        exact_statement = any(match["normalized_sha256"] == item.get("normalized_sha256") for match in matches)
        exact_context = any(
            match.get("semantic_context_sha256") == item.get("semantic_context_sha256")
            for match in matches
        )
        if not exact_statement or not exact_context:
            passes = [
                audit for audit in item.get("equivalence_audits", [])
                if audit.get("verdict") == "PASS" and audit.get("evidence")
            ]
            names = {audit.get("auditor") for audit in passes if audit.get("auditor")}
            if len(names) < 2:
                errors.append(f"main result {unit_id} changed without two independent equivalence PASS audits")
        candidate_sections = {tuple(match.get("section_path", [])) for match in matches if not match.get("in_appendix")}
        baseline_section = tuple(item.get("section_path", []))
        if candidate_sections and baseline_section not in candidate_sections:
            passes = [
                audit for audit in item.get("prominence_audits", [])
                if audit.get("verdict") == "PASS" and audit.get("evidence")
            ]
            names = {audit.get("auditor") for audit in passes if audit.get("auditor")}
            if len(names) < 2:
                errors.append(f"main result {unit_id} moved sections without two prominence PASS audits")

    label_occurrences = candidate.get("label_occurrences", candidate["labels"])
    duplicate_labels = sorted({label for label in label_occurrences if label_occurrences.count(label) > 1})
    if duplicate_labels:
        errors.append("duplicate labels: " + ", ".join(duplicate_labels))
    unresolved = sorted(set(candidate["references"]) - set(candidate["labels"]))
    if unresolved:
        errors.append("unresolved TeX references: " + ", ".join(unresolved[:20]))

    if state.get("gates", {}).get("draft", {}).get("status") == "pass":
        definitions_path = work / "06-definition-ledger.json"
        if not definitions_path.is_file():
            errors.append("definition ledger is missing")
        else:
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
            candidate_by_id = {unit["id"]: unit for unit in candidate["units"]}
            explicit_definitions = {
                unit["id"] for unit in candidate["units"] if unit.get("environment") == "definition"
            }
            missing_definitions = sorted(explicit_definitions - set(defining_ids))
            if missing_definitions:
                errors.append(f"definition ledger misses {len(missing_definitions)} explicit definition(s)")
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
    return {
        "pass": not errors,
        "errors": errors,
        "warnings": warnings,
        "baseline_units": len(baseline_by_id),
        "candidate_units": len(candidate["units"]),
        "main_results": len(locked),
    }


def markdown_coverage(inventory: dict[str, Any]) -> str:
    lines = [
        "# Baseline coverage ledger", "",
        "Every row must remain `auto` only while its normalized content is unchanged.",
        "Otherwise classify it in `05-coverage-ledger.json` and give its target and reason.", "",
        "| Unit | Kind | Label/title | Disposition |", "|---|---|---|---|",
    ]
    for unit in inventory["units"]:
        label = unit.get("label") or unit.get("title") or "—"
        lines.append(f"| `{unit['id']}` | {unit['kind']} | {label.replace('|', '/')} | auto |")
    lines.append("")
    return "\n".join(lines)


def lock_main_results(
    state_path: Path,
    labels: list[str] | None = None,
    unit_ids: list[str] | None = None,
) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    work = Path(state["work_dir"])
    inventory = json.loads((work / "00-baseline-inventory.json").read_text(encoding="utf-8"))
    by_label = {item.get("label"): item for item in inventory["units"] if item.get("label")}
    by_id = {item["id"]: item for item in inventory["units"]}
    labels = labels or []
    unit_ids = unit_ids or []
    missing = [label for label in labels if label not in by_label]
    if missing:
        raise ValueError("unknown baseline label(s): " + ", ".join(missing))
    missing_ids = [unit_id for unit_id in unit_ids if unit_id not in by_id]
    if missing_ids:
        raise ValueError("unknown baseline unit id(s): " + ", ".join(missing_ids))
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for unit in [by_label[label] for label in labels] + [by_id[unit_id] for unit_id in unit_ids]:
        if unit.get("kind") != "statement" or unit.get("environment") in NON_RESULT_ENVIRONMENTS:
            raise ValueError(f"main results must be theorem-grade statement units: {unit['id']}")
        if unit["id"] not in seen_ids:
            seen_ids.add(unit["id"])
            selected.append(unit)
    if not selected:
        raise ValueError("lock-main requires at least one --label or --unit-id")
    result = {
        "schema_version": 1,
        "source": state["source"],
        "source_sha256": state["source_sha256"],
        "main_results": [
            {
                "unit_id": unit["id"],
                "label": unit.get("label"),
                "environment": unit.get("environment"),
                "title": unit.get("title"),
                "normalized_sha256": unit["normalized_sha256"],
                "normalized_statement": unit["normalized_text"],
                "semantic_context_sha256": unit.get("semantic_context_sha256"),
                "section_path": unit.get("section_path", []),
                "candidate_label": None,
                "equivalence_audits": [],
                "prominence_audits": [],
            }
            for unit in selected
        ],
    }
    write_json(work / "00-main-results-lock.json", result)
    lines = ["# Baseline main-results lock", ""]
    for item in result["main_results"]:
        lines.extend([
            f"## `{item.get('label') or item['unit_id']}`", "",
            f"- Unit: `{item['unit_id']}`",
            f"- Environment: `{item.get('environment')}`",
            f"- Normalized SHA-256: `{item['normalized_sha256']}`",
            "", item["normalized_statement"], "",
        ])
    (work / "00-main-results-lock.md").write_text("\n".join(lines), encoding="utf-8")
    return result
