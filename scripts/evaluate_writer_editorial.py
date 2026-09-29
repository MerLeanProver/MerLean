#!/usr/bin/env python3
"""Compare archived independent editorial judgments with coordinator-only expectations.

This utility does not invoke a model or judge the mathematical substance of evidence.
An agreeing classification needs a separate human/agent semantic assessment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROLES = {"faithfulness", "narrative", "notation", "wording"}
DEFAULT_EXPECTATIONS = (
    Path(__file__).resolve().parents[1]
    / "tests" / "fixtures" / "recursive_writer_editorial" / "expectations.json"
)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def evaluate(expectations_path: Path, reports_dir: Path) -> dict[str, Any]:
    """Read evidence without mutation and return structural/classification results."""
    errors: list[str] = []
    comparisons: list[dict[str, Any]] = []
    receipts: list[dict[str, str]] = []
    expected = _read(expectations_path)
    if expected.get("schema_version") != 1 or not isinstance(expected.get("cases"), list):
        raise ValueError("invalid expectation schema")
    cases: dict[tuple[str, str], dict[str, Any]] = {}
    for case in expected["cases"]:
        if not isinstance(case, dict):
            raise ValueError("expectation case must be an object")
        key = (case.get("role"), case.get("case_id"))
        if (key[0] not in ROLES or not _text(key[1]) or key in cases
                or case.get("expected") not in {"required_repair", "no_required_repair"}
                or not _text(case.get("reason"))):
            raise ValueError("invalid or duplicate expectation case")
        cases[key] = case
    if {key[0] for key in cases} != ROLES:
        raise ValueError("expectations must cover all four checker roles")
    if reports_dir.is_symlink() or not reports_dir.is_dir():
        raise ValueError("reports must be an existing regular directory")

    roles_seen: set[str] = set()
    reviewers: set[str] = set()
    invocations: set[str] = set()
    observed: set[tuple[str, str]] = set()
    for path in sorted(reports_dir.glob("*.json")):
        report = _read(path)
        receipts.append({"file": path.name,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        role = report.get("role")
        if role not in ROLES or role in roles_seen or report.get("schema_version") != 1:
            errors.append(f"{path.name}: unknown/duplicate role or invalid schema version")
            continue
        roles_seen.add(role)
        for field, seen in (("reviewer_id", reviewers), ("invocation_id", invocations)):
            identity = report.get(field)
            if not _text(identity) or identity in seen:
                errors.append(f"{path.name}: {field} must identify a distinct actual invocation")
            elif isinstance(identity, str):
                seen.add(identity)
        results = report.get("results")
        if not isinstance(results, list):
            errors.append(f"{path.name}: results must be a list")
            continue
        for result in results:
            if not isinstance(result, dict):
                errors.append(f"{path.name}: result must be an object")
                continue
            case_id = result.get("case_id")
            if not isinstance(case_id, str):
                errors.append(f"{path.name}: case_id must be text")
                continue
            key = (role, case_id)
            if key not in cases or key in observed:
                errors.append(f"{path.name}: unknown or duplicate case {case_id}")
                continue
            observed.add(key)
            verdict = result.get("verdict")
            if verdict not in {"PASS", "FAIL", "INCOMPLETE"}:
                errors.append(f"{role}/{case_id}: invalid verdict")
            if not _text(result.get("summary")):
                errors.append(f"{role}/{case_id}: evidence-based summary required")
            findings = result.get("findings")
            if not isinstance(findings, list):
                errors.append(f"{role}/{case_id}: findings must be a list")
                findings = []
            required = False
            for finding in findings:
                if (not isinstance(finding, dict)
                        or finding.get("severity") not in {"required", "advisory"}
                        or any(not _text(finding.get(field))
                               for field in ("location", "evidence", "resolution"))):
                    errors.append(f"{role}/{case_id}: malformed or unsupported finding")
                    continue
                required |= finding["severity"] == "required"
            if verdict == "PASS" and required:
                errors.append(f"{role}/{case_id}: PASS contains required repairs")
            if verdict == "FAIL" and not required:
                errors.append(f"{role}/{case_id}: FAIL requires a concrete required finding")
            anticipated = cases[key]["expected"]
            agrees = ((anticipated == "required_repair" and verdict == "FAIL" and required)
                      or (anticipated == "no_required_repair" and verdict == "PASS" and not required))
            comparisons.append({"role": role, "case_id": case_id, "expected": anticipated,
                                "observed_verdict": verdict, "classification_agrees": agrees,
                                "reason_for_semantic_check": cases[key]["reason"]})
    missing = sorted(set(cases) - observed)
    if missing:
        errors.append("missing cases: " + ", ".join(f"{role}/{case}" for role, case in missing))
    mismatches = [row for row in comparisons if not row["classification_agrees"]]
    return {"schema_version": 1,
            "classification_pass": not errors and not mismatches,
            "errors": errors, "cases_evaluated": len(comparisons),
            "classification_mismatches": len(mismatches), "comparisons": comparisons,
            "reports": receipts,
            "expectations_sha256": hashlib.sha256(expectations_path.read_bytes()).hexdigest(),
            "semantic_assessment": "Required separately: verify that evidence identifies the intended defect and controls have no unsupported required repairs.",
            "limitations": "Identity fields establish consistency, not authenticated independence; no model is invoked and no mathematical judgment is synthesized."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", required=True, type=Path,
                        help="Directory containing unchanged independent report JSON files")
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.expectations, args.reports)
    except (OSError, ValueError, TypeError) as exc:
        report = {"classification_pass": False, "errors": [str(exc)]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["classification_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
