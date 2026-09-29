"""Receipt-bound recursive writing. This module never launches a model.

The cooperative host coordinator owns mutations; workers return attributed artifacts.
PASS means faithful presentation of accepted sources, not a new mathematical grade.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .versioning import sha256_file
from .writing_snapshot import snapshot_sources, verify_snapshot, diff_snapshots

ROLES = ("faithfulness", "narrative", "notation", "wording")
# Keep saved runs' required acceptance wording intact, including author extensions.
LEGACY_CHECKPOINTS = {
    "faithfulness": [
        "Preserve statements, domains, hypotheses, quantifiers and conclusions.",
        "Preserve proof reasoning and dependency use; justify elementary reformulations.",
        "Supply necessary definitions and results or precise appropriate citations.",
        "Keep abstract, introduction and informal summaries within supported scope.",
        "Preserve source provenance, proof statuses, grades and reference boundaries.",
        "Check changed assumptions, macros and affected unchanged consumers.",
        "Account for every approved claim and recoverable omitted supporting unit.",
        "Escalate source contradictions, new arguments and stronger contributions.",
    ],
    "narrative": [
        "Motivate the problem, obstacle, contribution and consequences.",
        "Organize sections with visible purpose and logical transitions.",
        "Explain central ideas adequately and give routine material proportionate space.",
        "Make main results prominent with useful examples and interpretation.",
        "Respect the approved audience and contribution; do not silently enlarge scope.",
    ],
    "notation": [
        "Introduce only useful notation and explain its motivation.",
        "Define objects precisely with domains and scope available before use.",
        "Maintain stable symbols and avoid collisions across the whole paper.",
        "Use field conventions and approved registry, not rigid universal typography.",
        "Use one authoritative definition while allowing helpful introductions and reminders.",
    ],
    "wording": [
        "Use plain, clean and precise sentences rather than inflated literary wording.",
        "Use symmetric consistent terminology for the same concept.",
        "Remove unnecessary repetition without deleting scope or helpful reminders.",
        "Avoid unsupported rhetorical claims and unnecessary sentence burden.",
        "Display long, referenced or central formulas when it improves readability.",
        "Number equations when referenced or required; preserve necessary technical detail.",
    ],
}
LEGACY_CHECKPOINTS = MappingProxyType({role: tuple(rows) for role, rows in LEGACY_CHECKPOINTS.items()})
V2_CHECKPOINTS = {role: list(checkpoints) for role, checkpoints in LEGACY_CHECKPOINTS.items()}
V2_CHECKPOINTS["faithfulness"][2] = (
    "Supply necessary definitions and results or precise appropriate citations. For every "
    "nontrivial numbered claim, locate a reader-visible proof, precise external citation, "
    "explicit internal proof pointer, or identified deduction. Distinguish a missing "
    "justification from weak discoverability of an existing one; do not reprove accepted "
    "source mathematics. PASS evidence identifies each claim and its locatable justification route."
)
V2_CHECKPOINTS["narrative"][1] = (
    "Organize sections with visible purpose and logical transitions. Explain the purpose "
    "of supporting lemmas and technical blocks before the technical detour; one introduction "
    "may orient a whole block. PASS evidence locates each substantial block's introduction "
    "and explains its role in the argument."
)
V2_CHECKPOINTS["narrative"][2] = (
    "Explain central ideas adequately and give routine material proportionate space. "
    "Important nonstandard definitions have a reader-visible interpretation and reason "
    "for introduction before or immediately alongside the formal definition. PASS evidence "
    "locates these explanations for each important definition."
)
V2_CHECKPOINTS["notation"][0] = (
    "Introduce only useful notation. For each important nonstandard definition, explain "
    "what the quantity measures or concept means and why it is introduced before or "
    "immediately alongside its formal definition. Do not require motivation for every "
    "routine symbol. PASS evidence identifies each important definition and locates its "
    "interpretation and purpose."
)
V2_CHECKPOINTS["wording"][2] = (
    "Remove unnecessary repetition without deleting scope or helpful reminders. Keep "
    "formal statements focused on mathematical content, with motivation and proof "
    "navigation in adjacent prose where clearer; preserve every hypothesis, quantifier "
    "and qualification. PASS evidence locates statements checked and any relevant adjacent prose."
)
V2_CHECKPOINTS = MappingProxyType({role: tuple(rows) for role, rows in V2_CHECKPOINTS.items()})

# Historical v3 wording remains frozen for saved runs.
V3_CHECKPOINTS = {role: list(checkpoints) for role, checkpoints in V2_CHECKPOINTS.items()}
V3_CHECKPOINTS["narrative"][1] = (
    "Organize sections with visible purpose and logical transitions. Explain the purpose "
    "of supporting lemmas and technical blocks before the technical detour, including the "
    "later step they enable. Identify local blocks by changes of mathematical object or "
    "argumentative purpose, not merely section boundaries. Explain distinct ingredients' "
    "roles and their connection to the next step; a generic announcement of useful tools "
    "or an eventual output is insufficient. One introduction may orient a whole block; "
    "do not repeat a purpose already evident locally. Judge orientation using evidence "
    "available before or at entry: later proofs, applications, or reviewer reconstruction "
    "cannot supply missing introductory explanation. PASS evidence identifies each "
    "substantial block and quotes a short exact introductory passage with its location "
    "and the question it answers, or states an explicit short inference from local context. "
    "Distinguish that evidence from explanations available only later or reconstructed by "
    "the reviewer. Missing orientation is required when the reader must await later material "
    "or reconstruct a nontrivial argument to understand the detour; identify the unanswered "
    "question and entry point. If a short local inference supplies the rationale, extra "
    "explanation is advisory; absence of a stock phrase or separate preamble is not a defect."
)
V3_CHECKPOINTS["narrative"][2] = (
    "Explain central ideas adequately and give routine material proportionate space. "
    "Important nonstandard definitions have a reader-visible interpretation and reason "
    "for introduction before or immediately alongside the formal definition. Distinguish "
    "intended purpose from the conceptual reason for consequential, non-obvious branches, "
    "thresholds, corrections, or competing terms; a functional label alone does not explain "
    "that structure. Require conceptual orientation, not a preliminary proof or a derivation "
    "of every constant. Exempt routine symbols, standard formulas, transparent rewritings, "
    "and evident cases. Judge introductory adequacy from evidence available before or at "
    "entry; later proofs, applications, or reviewer reconstruction cannot supply missing "
    "introductory explanation. PASS evidence identifies each important definition and quotes "
    "a short exact introductory passage with its location and the question it answers, or "
    "states an explicit short inference from local context, covering interpretation, purpose, "
    "and consequential non-obvious form. Distinguish local evidence from explanations available "
    "only later or reconstructed by the reviewer. Missing orientation is required when the "
    "reader must await later material or reconstruct a nontrivial argument to understand a "
    "central definition's form or purpose; identify the unanswered question at entry. If a "
    "short local inference supplies the rationale, extra explanation is advisory; absence "
    "of a stock phrase is not itself a defect."
)
V3_CHECKPOINTS["notation"][0] = (
    "Introduce only useful notation. For each important nonstandard definition, explain "
    "what the quantity measures or concept means and why it is introduced before or "
    "immediately alongside its formal definition. Distinguish intended purpose from the "
    "conceptual reason for consequential, non-obvious branches, thresholds, correction terms, "
    "or competing terms; calling a quantity a bound, penalty, or auxiliary variable does not "
    "by itself explain its chosen structure. Require conceptual orientation, not a preliminary "
    "proof or a derivation of every constant. Exempt routine symbols, standard formulas, "
    "transparent rewritings, and evident cases; do not add boilerplate where local context "
    "suffices. Judge introductory adequacy from evidence available before or at entry; later "
    "proofs, applications, or reviewer reconstruction cannot supply missing introductory "
    "explanation. PASS evidence identifies each important definition and quotes a short exact "
    "introductory passage with its location and the question it answers, or states an explicit "
    "short inference from local context, covering interpretation, purpose, and consequential "
    "non-obvious form. Distinguish local evidence from explanations available only later or "
    "reconstructed by the reviewer. Missing orientation is required when the reader must await "
    "later material or reconstruct a nontrivial argument to understand a central definition's "
    "form or purpose; identify the unanswered question at entry. If a short local inference "
    "supplies the rationale, extra explanation is advisory; absence of a stock phrase is not "
    "an actual reader obstacle."
)
V3_CHECKPOINTS = MappingProxyType({role: tuple(rows) for role, rows in V3_CHECKPOINTS.items()})

# New runs use v4; saved rubric files retain their declared baseline and exact bytes.
DEFAULT_RUBRIC_VERSION = 4
CHECKPOINTS = {role: list(checkpoints) for role, checkpoints in V3_CHECKPOINTS.items()}
CHECKPOINTS["narrative"][1] = (
    "Organize sections with visible purpose and logical transitions. Explain the purpose "
    "of supporting lemmas and technical blocks before the technical detour, including the "
    "later step they enable. Distinguish result content (what it computes) from argumentative "
    "purpose (why it is needed now). Identify local blocks by changes of mathematical object "
    "or argumentative purpose, not merely section boundaries; check why that family, "
    "comparison, or quantity is introduced, not just its type. Explain distinct ingredients' "
    "roles and their connection to the next step; a generic announcement of useful tools "
    "or an eventual output is insufficient. Naming a count, bound, calculation, "
    "or tool, or paraphrasing the conclusion alone, is not purpose evidence. One introduction "
    "may orient a whole block; do not repeat a purpose already evident locally. Judge "
    "orientation using evidence available before or at entry: later proofs, applications, "
    "or reviewer reconstruction cannot supply missing introductory explanation. PASS evidence "
    "identifies each substantial block and quotes a short exact introductory passage with "
    "its location and the question it answers, or states an explicit short inference from "
    "local context. To credit that inference, identify an already introduced question or "
    "next-step objective, the ingredient's contribution, and its immediate connection to "
    "that objective; quote the local evidence for the objective and the ingredient. The "
    "objective cannot be invented from later applications. Distinguish "
    "that evidence from explanations available only later or reconstructed by the reviewer. "
    "Missing orientation is required for a substantial block when the reader must discover "
    "its intended use or choice from later material, even if its mathematics and retrospective "
    "connection are elementary; identify the unanswered question and entry point. An already "
    "explicit local goal plus a transparent inference needs no extra preamble, forward theorem "
    "number, or stock phrase; extra explanation is advisory. Routine intermediate proof steps "
    "are not substantial detours, and a simple calculation does not require added prose merely "
    "because it is simple or lacks a separate preamble."
)
CHECKPOINTS = MappingProxyType({role: tuple(rows) for role, rows in CHECKPOINTS.items()})
CHECKPOINTS_BY_VERSION = MappingProxyType({1: LEGACY_CHECKPOINTS, 2: V2_CHECKPOINTS,
                                         3: V3_CHECKPOINTS,
                                         DEFAULT_RUBRIC_VERSION: CHECKPOINTS})


def _safe_artifact_path(path: Path) -> Path:
    from .writing_snapshot import _safe_path
    path = _safe_path(path)
    if path.exists():
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f"expected unlinked regular evidence: {path}")
    return path


def _artifact_bytes(path: Path) -> bytes:
    from .writing_snapshot import _read as coherent_read
    path = _safe_artifact_path(path)
    data = coherent_read(path)
    _safe_artifact_path(path)
    return data


def _read(path: Path) -> Any:
    return json.loads(_artifact_bytes(path).decode("utf-8-sig"))


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _publish_artifact(path: Path, data: bytes, *, exclusive: bool) -> None:
    from .versioning import atomic_rename_noreplace
    path = _safe_artifact_path(path)
    initial = None
    if path.exists():
        if exclusive:
            raise FileExistsError(path)
        info = path.stat()
        initial = (info.st_dev, info.st_ino, hashlib.sha256(_artifact_bytes(path)).hexdigest())
    path.parent.mkdir(parents=True, exist_ok=True)
    _safe_artifact_path(path)
    # Unique owned staging avoids turning an interrupted write into an enduring
    # '.pending' lock. Never remove or replace an unowned staging artifact.
    temporary = path.with_name(f".{path.name}.pending-{uuid.uuid4().hex}")
    owned = None
    try:
        with temporary.open("xb") as handle:
            staged = os.fstat(handle.fileno())
            owned = (staged.st_dev, staged.st_ino)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _safe_artifact_path(temporary)
        staged = temporary.stat()
        if (staged.st_dev, staged.st_ino) != owned or _artifact_bytes(temporary) != data:
            raise ValueError("owned staging evidence changed before publication")
        _safe_artifact_path(path)
        if initial is None:
            atomic_rename_noreplace(temporary, path)
        else:
            info = path.stat()
            current = (info.st_dev, info.st_ino, hashlib.sha256(_artifact_bytes(path)).hexdigest())
            if current != initial:
                raise ValueError("artifact changed during coordinator write; refusing replacement")
            os.replace(temporary, path)
        published = _safe_artifact_path(path).stat()
        if (published.st_dev, published.st_ino) != owned or _artifact_bytes(path) != data:
            raise ValueError("published evidence does not match the owned artifact")
    finally:
        if owned is not None and temporary.exists():
            try:
                checked = _safe_artifact_path(temporary)
                info = checked.stat()
                if (info.st_dev, info.st_ino) == owned:
                    checked.unlink()
            except (OSError, ValueError):
                pass  # Preserve unexpected paths; never clean up someone else's file.


def _write(path: Path, value: Any, *, exclusive: bool = False) -> None:
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _publish_artifact(path, data, exclusive=exclusive)


def _receipt(path: Path) -> dict:
    path = _safe_artifact_path(path)
    return {"path": str(path), "sha256": hashlib.sha256(_artifact_bytes(path)).hexdigest()}


def _check_receipt(record: dict) -> None:
    if _receipt(Path(record["path"])) != record:
        raise ValueError(f"evidence changed: {record['path']}")


def _archive(work: Path, category: str, source: Path) -> dict:
    if not category or Path(category).name != category or category in {".", ".."} or "\\" in category or ":" in category:
        raise ValueError("archive category must be one local directory name")
    source = _safe_artifact_path(source)
    data = _artifact_bytes(source)
    receipt = {"sha256": hashlib.sha256(data).hexdigest()}
    target = work / "writer" / category / (receipt["sha256"] + source.suffix)
    target = _safe_artifact_path(target)
    if not target.exists():
        _publish_artifact(target, data, exclusive=True)
    if _receipt(target)["sha256"] != receipt["sha256"]:
        raise ValueError("evidence changed during archival")
    if source.suffix.lower() == ".json":
        try:
            value = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and (value.get("summary") or value.get("objective")):
            lines = ["# " + ("Review" if "verdict" in value else "Writing plan"), "",
                     f"Authoritative evidence: `{target.name}`", ""]
            for key in ("revision_id", "role", "reviewer_id", "planner_id", "verdict", "objective", "summary"):
                if value.get(key):
                    lines.extend([f"{key.replace('_', ' ').capitalize()}: {value[key]}", ""])
            for finding in value.get("findings", []):
                if isinstance(finding, dict):
                    lines.extend([f"- {finding.get('id', '')} ({finding.get('severity', '')}), {finding.get('location', '')}: "
                                  f"{finding.get('evidence', '')} Resolution: {finding.get('resolution', '')}", ""])
            readable = target.with_suffix(".report.md")
            report_bytes = ("\n".join(lines) + "\n").encode("utf-8")
            if not readable.exists():
                _publish_artifact(readable, report_bytes, exclusive=True)
            elif _artifact_bytes(readable) != report_bytes:
                raise ValueError("human-readable archive view changed; preserving conflicting file")
    return _receipt(target)


def _load(state_path: Path) -> tuple[dict, dict, Path]:
    state = _read(state_path)
    if state.get("schema_version") != 2 or "writer" not in state:
        raise ValueError("recursive writing requires a new schema-version-2 run")
    from .workflow import verify_source, verify_output
    verify_source(state)
    verify_output(state, require_reservation=True)
    writer = state["writer"]
    errors = verify_snapshot(writer["sources"], check_originals=True)
    if errors:
        raise ValueError("source snapshot/drift: " + "; ".join(errors))
    _check_receipt(writer["source_claims"])
    if writer.get("contract"):
        for receipt in writer["contract"].values():
            _check_receipt(receipt)
    for plan in writer["plans"]:
        _check_receipt(plan["receipt"])
    for revision in writer["revisions"]:
        for record in [*revision["reviews"], *revision["layouts"]]:
            _check_receipt(record["receipt"])
            _check_receipt(record["packet"])
    for receipt in writer["extensions"]:
        _check_receipt(receipt)
    return state, writer, Path(state["work_dir"])


def initialize(state_path: Path, sources: list[Path], brief: Path | None,
               max_review_rounds: int = 5) -> dict:
    if max_review_rounds < 1:
        raise ValueError("review allowance must be positive")
    state = _read(state_path)
    if "writer" in state or state.get("mode") not in {"compose", "refine"}:
        raise ValueError("initialize a new compose/refine run only")
    # A failed upgrade of a newly reserved run must not silently resume as legacy.
    state["schema_version"] = 2
    state["writer_initialization"] = "incomplete"
    _write(state_path, state)
    work = Path(state["work_dir"])
    target = work / "writer"
    target.mkdir(exist_ok=False)
    if state.get("source"):
        sources = [Path(state["source"]), *sources]
    bundle = None
    if state.get("synthesis_origin"):
        from .synthesis_bridge import verify_import
        bundle = verify_import(state)
        # All imported provenance is immutable and already source-verified.
        sources += [Path(row["path"]) for row in state["synthesis_origin"]["files"]]
    sources = list(dict.fromkeys(path.expanduser().absolute() for path in sources))
    if not sources:
        raise ValueError("recursive compose requires --source or --from-synthesis")
    snapshot = snapshot_sources(sources, target / "sources")
    claims = []
    if bundle:
        claims = [dict(claim, main=claim["id"] in bundle["candidate"]["main_claim_ids"])
                  for claim in bundle["claims"]]
    else:
        from .tex_inventory import inventory_tex
        seen = set()
        for row in snapshot["roots"]:
            if Path(row["original"]).suffix.lower() in {".md", ".markdown"}:
                # A document-level source unit is provisional, not a theorem claim.
                # The brief/claim map locates the selected statement within it, and
                # independent faithfulness reviewers inspect the complete context.
                claims.append({"id": "source-" + _hash(row["original"])[:16], "main": False,
                               "statement": Path(row["snapshot"]).read_text(encoding="utf-8-sig"),
                               "hypotheses": [], "dependencies": [],
                               "proof_status": "accepted_source_not_independently_verified",
                               "grade_metadata": None, "kind": "document",
                               "source_refs": [{"path": row["original"], "line": 1}]})
                continue
            if Path(row["original"]).suffix.lower() != ".tex":
                continue
            for unit in inventory_tex(Path(row["original"]))["units"]:
                if unit["kind"] not in {"statement", "proof"}:
                    continue
                identity = (unit["source_file"], unit["id"])
                if identity in seen:
                    continue
                seen.add(identity)
                claims.append({"id": "source-" + _hash(identity)[:16], "main": False,
                               "statement": unit.get("raw_text", unit.get("normalized_text", "")),
                               "hypotheses": [], "dependencies": [],
                               "proof_status": "accepted_source_not_independently_verified",
                               "grade_metadata": None, "source_refs": [{"path": unit["source_file"],
                                   "line": unit.get("line"), "unit_id": unit["id"]}],
                               "kind": unit["kind"], "source_label": unit.get("label")})
    _write(target / "source-claims.json", {"claims": claims,
           "note": "Source context remains authoritative; empty extracted fields do not waive hypotheses."})
    if brief:
        brief_value = _read(brief)
    else:
        brief_value = {"audience": "", "question": "", "contribution": "", "scope": "",
                       "main_claim_ids": [], "exclusions": [], "approval_evidence": None}
    _write(target / "brief.json", brief_value)
    _write(target / "registry.json", {"concepts": []})
    for role, prefix in zip(ROLES, ("F", "N", "D", "W")):
        _write(target / "rubrics" / (role + ".json"), {"role": role, "version": DEFAULT_RUBRIC_VERSION,
               "defaults_version": DEFAULT_RUBRIC_VERSION,
               "checkpoints": [{"id": f"{prefix}{i:02}", "severity": "required", "acceptance": text}
                               for i, text in enumerate(CHECKPOINTS[role], 1)]})
    state["schema_version"] = 2
    state.pop("writer_initialization", None)
    state["writer"] = {"protocol": "recursive-writer-1", "sources": snapshot,
                       "source_claims": _receipt(target / "source-claims.json"),
                       "contract": None, "plans": [], "revisions": [], "extensions": [],
                       "max_review_rounds": max_review_rounds,
                       "source_assumption": "accepted mathematics; writing does not award grades",
                       "baseline_only": state["mode"] == "refine" and len(sources) == 1}
    _write(state_path, state)
    return state


def _contract(writer: dict, work: Path) -> dict:
    brief_path = work / "writer" / "brief.json"
    brief = _read(brief_path)
    for field in ("audience", "question", "contribution", "scope", "main_claim_ids", "approval_evidence"):
        if not brief.get(field):
            raise ValueError(f"approved brief requires {field}")
    if not isinstance(brief["main_claim_ids"], list) or not 1 <= len(brief["main_claim_ids"]) <= 4:
        raise ValueError("brief must select one to four main claims")
    claims = _read(Path(writer["source_claims"]["path"]))["claims"]
    if not set(brief["main_claim_ids"]).issubset({row["id"] for row in claims}):
        raise ValueError("brief selects unknown source claims")
    imported_main = {row["id"] for row in claims if row.get("main")}
    if imported_main and set(brief["main_claim_ids"]) != imported_main:
        raise ValueError("brief changes approved synthesis main claims")
    approval = Path(brief["approval_evidence"])
    if not approval.is_absolute():
        approval = work / approval
    if not approval.is_file() or not approval.read_text(encoding="utf-8-sig").strip():
        raise ValueError("actual author approval evidence is required")
    return {"brief": _receipt(brief_path), "approval": _archive(work, "approvals", approval)}


def record_plan(state_path: Path, plan_path: Path) -> dict:
    state, writer, work = _load(state_path)
    plan = _read(plan_path)
    for field in ("planner_id", "writer_id", "objective", "outline", "claim_map"):
        if not plan.get(field):
            raise ValueError(f"writing plan requires {field}")
    current = writer["revisions"][-1] if writer["revisions"] else None
    if plan.get("base_revision") != (current["id"] if current else None):
        raise ValueError("writing plan has stale base_revision")
    if current:
        pending, _ = _review_state(writer, work, current)
        if pending:
            raise ValueError("collect all scheduled reviews before replanning: " + ", ".join(pending))
    contract = writer.get("contract") or _contract(writer, work)
    claims = _read(Path(writer["source_claims"]["path"]))["claims"]
    mapped = {row.get("claim_id"): row for row in plan["claim_map"]}
    if len(mapped) != len(plan["claim_map"]) or set(mapped) != {row["id"] for row in claims}:
        raise ValueError("claim_map must account for every source claim exactly once")
    main_ids = set(_read(Path(contract["brief"]["path"]))["main_claim_ids"])
    for claim_id, row in mapped.items():
        if row.get("disposition") not in {"retained", "cited", "archived"} or not row.get("location") or not row.get("reason"):
            raise ValueError("claim disposition needs retained/cited/archived, location and reason")
        if claim_id in main_ids and (row["disposition"] != "retained" or not row.get("candidate_label")):
            raise ValueError("every approved main result must remain explicitly labeled in the main paper")
    if current:
        required = _required_findings(current)
        repairs = {row.get("finding_id"): row for row in plan.get("repairs", [])}
        if not required.issubset(repairs):
            raise ValueError("repair plan must address every required finding")
        if any(not row.get("action") or not row.get("reason") for row in repairs.values()):
            raise ValueError("repair actions require reasons; planner cannot downgrade required findings")
    writer["contract"] = contract
    record = {"receipt": _archive(work, "plans", plan_path), "base_revision": plan.get("base_revision")}
    writer["plans"].append(record)
    _write(state_path, state)
    return record


def _rubrics(work: Path) -> dict:
    result = {}
    for role in ROLES:
        path = work / "writer" / "rubrics" / (role + ".json")
        rubric = _read(path)
        # `version` also counts author extensions in saved runs. An absent baseline
        # marker therefore means the original defaults, even if version exceeds 1.
        defaults_version = rubric.get("defaults_version", 1)
        if type(defaults_version) is not int or defaults_version not in CHECKPOINTS_BY_VERSION:
            raise ValueError(f"unsupported {role} rubric defaults_version")
        ids = [row.get("id") for row in rubric.get("checkpoints", [])]
        if rubric.get("role") != role or not ids or len(ids) != len(set(ids)):
            raise ValueError(f"invalid {role} rubric")
        if any(not row.get("acceptance") or row.get("severity") not in {"required", "advisory"}
               for row in rubric["checkpoints"]):
            raise ValueError("rubric checkpoints need acceptance conditions and severity")
        prefix = {"faithfulness": "F", "narrative": "N", "notation": "D", "wording": "W"}[role]
        by_id = {row["id"]: row for row in rubric["checkpoints"]}
        for index, acceptance in enumerate(CHECKPOINTS_BY_VERSION[defaults_version][role], 1):
            row = by_id.get(f"{prefix}{index:02}", {})
            if row.get("severity") != "required" or row.get("acceptance") != acceptance:
                raise ValueError("default required checkpoints cannot be deleted or weakened; add author-approved extensions")
        result[role] = _receipt(path)
    return result


def _bindings(writer: dict, work: Path, revision: dict, role: str) -> dict:
    role_file = Path(__file__).resolve().parents[2] / "roles" / ("paper-" + role + ".md")
    return {"manuscript": revision["snapshot"]["digest"], "sources": writer["sources"]["digest"],
            "claims": writer["source_claims"]["sha256"], "contract": _hash(writer["contract"]),
            "plan": revision["plan"]["sha256"],
            "registry": sha256_file(work / "writer" / "registry.json"),
            "references": sha256_file(work / "references-registry.json"),
            "rubric": _rubrics(work)[role]["sha256"], "role": sha256_file(role_file)}


def _valid_reports(writer: dict, work: Path, revision: dict, role: str) -> list[dict]:
    expected = _bindings(writer, work, revision, role)
    reports = []
    for record in revision["reviews"]:
        _check_receipt(record["receipt"])
        report = _read(Path(record["receipt"]["path"]))
        if report["role"] == role and report.get("review_kind", "content") == "content" and report["bindings"] == expected:
            reports.append(report)
    return reports


def _review_state(writer: dict, work: Path, revision: dict) -> tuple[list, list]:
    pending, failed = [], []
    for role in ROLES:
        reports = _valid_reports(writer, work, revision, role)
        needed = 2 if role == "faithfulness" and revision["two_faithfulness"] else 1
        # Last report from an invocation is authoritative; old FAIL remains history.
        by_reviewer = {report["reviewer_id"]: report for report in reports}
        complete = [r for r in by_reviewer.values() if r["verdict"] != "INCOMPLETE"]
        tracks = {r.get("review_track", "primary") for r in complete}
        if len(complete) < needed or "primary" not in tracks or (needed == 2 and "secondary" not in tracks):
            pending.append(role)
        if any(r["verdict"] == "FAIL" for r in complete):
            failed.append(role)
    return pending, failed


def _required_findings(revision: dict) -> set[str]:
    findings = set()
    for record in [*revision["reviews"], *revision["layouts"]]:
        _check_receipt(record["receipt"])
        report = _read(Path(record["receipt"]["path"]))
        findings.update(row["id"] for row in report.get("findings", []) if row["severity"] == "required")
    return findings


def freeze_revision(state_path: Path) -> dict:
    state, writer, work = _load(state_path)
    if not writer["plans"] or not writer.get("contract"):
        raise ValueError("record an approved writing contract and plan first")
    if len(writer["revisions"]) >= writer["max_review_rounds"]:
        raise ValueError("review revision limit reached; explicit author continuation required")
    previous = writer["revisions"][-1] if writer["revisions"] else None
    plan_record = writer["plans"][-1]
    if plan_record["base_revision"] != (previous["id"] if previous else None):
        raise ValueError("record a repair plan against the current revision first")
    if previous and _review_state(writer, work, previous)[0]:
        raise ValueError("collect all scheduled reviews before another manuscript revision")
    plan = _read(Path(plan_record["receipt"]["path"]))
    revision_id = f"r{len(writer['revisions']) + 1:03}"
    # Unique attempt paths make interruption and rejected unchanged snapshots recoverable.
    snapshot = snapshot_sources([Path(state["output"])], work / "writer" / "revisions" / revision_id / ("manuscript-" + uuid.uuid4().hex[:12]))
    if previous and snapshot["digest"] == previous["snapshot"]["digest"]:
        raise ValueError("manuscript unchanged; rereview the current revision rather than spending another round")
    # Any refinement transformation receives the established second equivalence audit.
    two = bool(state.get("synthesis_origin") or state["mode"] == "refine")
    record = {"id": revision_id, "snapshot": snapshot, "plan": plan_record["receipt"],
              "two_faithfulness": two, "full_faithfulness": bool(plan.get("full_faithfulness")),
              "reviews": [], "builds": [], "layouts": [], "context_records": {}}
    # This is the coordinator's acceptance receipt, not a manufactured worker review.
    # A returned worker artifact can additionally be attached by the host in its plan.
    record["writer_task_receipt"] = {
        "writer_id": plan["writer_id"], "base_revision": previous["id"] if previous else None,
        "plan": plan_record["receipt"], "accepted_manuscript_sha256": snapshot["digest"],
        "changes": diff_snapshots(previous["snapshot"], snapshot) if previous else None,
        "mathematical_change_account": plan.get("mathematical_change_account",
                                                  "No worker account supplied; independent faithfulness review remains required."),
    }
    _rubrics(work)
    writer["revisions"].append(record)
    _write(state_path, state)
    return record


def _prior_reports(writer: dict, role: str, before: str | None = None,
                   track: str = "primary", kind: str = "content") -> list[tuple[dict, dict]]:
    records = []
    for revision in writer["revisions"]:
        if revision["id"] == before:
            break
        for record in revision["layouts" if kind == "layout" else "reviews"]:
            _check_receipt(record["receipt"])
            report = _read(Path(record["receipt"]["path"]))
            if report["role"] == role and report.get("review_track", "primary") == track:
                records.append((revision, report))
    return records


def _validate_review_dispositions(report: Any) -> None:
    """Reject malformed evidence before it can close an existing obligation."""
    if not isinstance(report, dict):
        raise ValueError("review report must be a JSON object")
    dispositions = report.get("previous_findings", {})
    if not isinstance(dispositions, dict):
        raise ValueError("review previous_findings must be a JSON object")
    for finding_id, disposition in dispositions.items():
        if not isinstance(finding_id, str) or not finding_id.strip():
            raise ValueError("prior finding disposition requires a nonempty finding id")
        if not isinstance(disposition, dict):
            raise ValueError("prior finding dispositions must be JSON objects with evidence")
        if disposition.get("status") not in ("resolved", "persisting", "regressed", "retained"):
            raise ValueError("invalid prior finding disposition")
        evidence = disposition.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("prior finding dispositions require nonempty text evidence")


def _open_findings(writer: dict, role: str, track: str, kind: str,
                   current_id: str, reviewer_id: str) -> list[dict]:
    """Carry every prior branch, but never disclose a peer's current verdict.

Within the current revision a checker sees only its own retries. Across revisions
the role/track's unresolved obligations are external memory, not just prior[-1].
    """
    opened = {}
    for revision in writer["revisions"]:
        for record in revision["layouts" if kind == "layout" else "reviews"]:
            report = _read(Path(record["receipt"]["path"]))
            _validate_review_dispositions(report)
            if report["role"] != role or report.get("review_track", "primary") != track:
                continue
            if revision["id"] == current_id and report["reviewer_id"] != reviewer_id:
                continue
            for finding_id, disposition in report.get("previous_findings", {}).items():
                if disposition.get("status") == "resolved" and disposition.get("evidence"):
                    opened.pop(finding_id, None)
            for finding in report.get("findings", []):
                if finding["severity"] == "required":
                    opened[finding["id"]] = finding
    return list(opened.values())


def review_packet(state_path: Path, role: str, reviewer_id: str) -> dict:
    state, writer, work = _load(state_path)
    if role not in (*ROLES, "layout", "faithfulness-secondary") or not reviewer_id:
        raise ValueError("unknown review role or missing independent invocation identity")
    if not writer["revisions"]:
        raise ValueError("freeze a manuscript revision first")
    revision = writer["revisions"][-1]
    errors = verify_snapshot(revision["snapshot"])
    if errors:
        raise ValueError("frozen manuscript changed: " + "; ".join(errors))
    plan = _read(Path(revision["plan"]["path"]))
    authors = {p.get(key) for record in writer["plans"] for p in [_read(Path(record["receipt"]["path"]))]
               for key in ("planner_id", "writer_id")}
    if state.get("synthesis_origin"):
        bundle = _read(Path(state["synthesis_origin"]["handoff"]))
        source_work = Path(bundle["synthesis_state"]).parent
        for filename in ("claim-ledger.json", "candidate-prospectuses.json"):
            authors.add(_read(source_work / filename).get("authored_by"))
    if reviewer_id in authors:
        raise ValueError("reviewer must be independent of planners and writers")
    actual_role = "wording" if role == "layout" else "faithfulness" if role == "faithfulness-secondary" else role
    track = "secondary" if role == "faithfulness-secondary" else "primary"
    kind = "layout" if role == "layout" else "content"
    prior = _prior_reports(writer, actual_role, revision["id"], track, kind)
    previous = prior[-1] if prior else None
    bindings = _bindings(writer, work, revision, actual_role)
    baseline = next(((rev, report) for rev, report in reversed(prior)
                     if report["verdict"] == "PASS" and all(report["bindings"].get(key) == bindings[key]
                     for key in ("sources", "claims", "contract", "rubric", "role", "registry", "references"))
                     and _role_passed_historically(rev, actual_role, report["bindings"])), None)
    full = not baseline or revision["full_faithfulness"]
    if baseline and actual_role == "faithfulness":
        changes = diff_snapshots(baseline[0]["snapshot"], revision["snapshot"])
        # Changed non-root dependencies may alter unchanged theorem meanings.
        roots = {r["relative"] for r in revision["snapshot"]["roots"]}
        if (set(changes.get("modified", [])) | set(changes.get("added", [])) | set(changes.get("removed", []))) - roots:
            full = True
    packet = {"role": actual_role, "review_kind": "layout" if role == "layout" else "content",
              "reviewer_id": reviewer_id, "review_track": track, "revision_id": revision["id"], "bindings": bindings,
              "manuscript": revision["snapshot"], "brief": _read(Path(writer["contract"]["brief"]["path"])),
              "rubric": _read(work / "writer" / "rubrics" / (actual_role + ".json")),
              "registry": _read(work / "writer" / "registry.json"),
              "role_file": str(Path(__file__).resolve().parents[2] / "roles" / ("paper-" + actual_role + ".md")),
              "previous_report": previous[1] if previous else None,
              "unresolved_findings": _open_findings(writer, actual_role, track, kind, revision["id"], reviewer_id),
              "previous_diff": diff_snapshots(previous[0]["snapshot"], revision["snapshot"]) if previous else None,
              "scope": "comprehensive" if actual_role != "faithfulness" or full else "incremental",
              "last_pass_revision": baseline[0]["id"] if baseline else None,
              "cumulative_diff": diff_snapshots(baseline[0]["snapshot"], revision["snapshot"]) if baseline else None}
    if actual_role == "faithfulness":
        packet.update(sources=writer["sources"], source_claims=_read(Path(writer["source_claims"]["path"])),
                      claim_map=plan["claim_map"], two_independent_reviews=revision["two_faithfulness"])
    # Same-invocation retries must explicitly address their own earlier findings.
    # Do not expose another current checker invocation's report.
    current_own = [r for r in revision["layouts" if kind == "layout" else "reviews"]
                   if (lambda v: v["role"] == actual_role and v["reviewer_id"] == reviewer_id
                       and v.get("review_kind", "content") == packet["review_kind"])(_read(Path(r["receipt"]["path"])))]
    if current_own:
        packet["previous_report"] = _read(Path(current_own[-1]["receipt"]["path"]))
    if role == "layout":
        if not revision["builds"]:
            raise ValueError("compile the frozen revision before rendered inspection")
        _check_receipt(revision["builds"][-1])
        packet["build"] = _read(Path(revision["builds"][-1]["path"]))
        if not packet["build"].get("pass"):
            raise ValueError("rendered inspection requires a successful frozen build")
        build = packet["build"]
        if build.get("revision_id") != revision["id"] or build.get("manuscript_sha256") != revision["snapshot"]["digest"]:
            raise ValueError("rendered inspection build does not match the frozen revision")
        for artifact, checksum in (("retained_pdf", "pdf_sha256"), ("retained_log", "log_sha256")):
            if not build.get(artifact) or not build.get(checksum):
                raise ValueError(f"rendered inspection requires a retained, hash-bound {artifact}")
            _check_receipt({"path": build[artifact], "sha256": build[checksum]})
        if type(build.get("pdf_pages")) is not int or build["pdf_pages"] < 1:
            raise ValueError("rendered inspection requires a verified positive PDF page count")
    packet["packet_id"] = _hash(packet)
    return packet


def _role_passed_historically(revision: dict, role: str, bindings: dict) -> bool:
    latest = {}
    for record in revision["reviews"]:
        report = _read(Path(record["receipt"]["path"]))
        if report["role"] == role and report["bindings"] == bindings:
            latest[report["reviewer_id"]] = report
    needed = 2 if role == "faithfulness" and revision["two_faithfulness"] else 1
    tracks = {r.get("review_track", "primary") for r in latest.values()}
    return (len(latest) >= needed and "primary" in tracks and (needed != 2 or "secondary" in tracks)
            and all(r["verdict"] == "PASS" for r in latest.values()))


def record_review(state_path: Path, report_path: Path) -> dict:
    state, writer, work = _load(state_path)
    report = _read(report_path)
    _validate_review_dispositions(report)
    role = report.get("role")
    kind = report.get("review_kind", "content")
    track = report.get("review_track", "primary")
    packet_role = "layout" if kind == "layout" else "faithfulness-secondary" if role == "faithfulness" and track == "secondary" else role
    packet = review_packet(state_path, packet_role, report.get("reviewer_id", ""))
    if track != packet["review_track"]:
        raise ValueError("invalid review track")
    for key in ("packet_id", "revision_id", "bindings"):
        if report.get(key) != packet[key]:
            raise ValueError(f"stale or mismatched review {key}")
    verdict = report.get("verdict")
    if verdict not in {"PASS", "FAIL", "INCOMPLETE"}:
        raise ValueError("review verdict must be PASS, FAIL or INCOMPLETE")
    if not report.get("summary"):
        raise ValueError("review requires an evidence-based summary")
    revision = writer["revisions"][-1]
    for record in revision["reviews"]:
        other = _read(Path(record["receipt"]["path"]))
        if other["reviewer_id"] == report["reviewer_id"] and (other["role"] != role or other.get("review_track", "primary") != track):
            raise ValueError("checker roles need separate independent invocations")
    findings = report.get("findings", [])
    ids = set()
    for finding in findings:
        for field in ("id", "severity", "location", "evidence", "resolution"):
            if not finding.get(field):
                raise ValueError(f"finding requires {field}")
        if finding["id"] in ids or finding["severity"] not in {"required", "advisory"}:
            raise ValueError("duplicate finding or invalid severity")
        ids.add(finding["id"])
    if verdict == "PASS" and any(f["severity"] == "required" for f in findings):
        raise ValueError("PASS cannot contain unresolved required findings")
    known_prior = {f["id"] for f in packet["unresolved_findings"]}
    known_prior.update(f["id"] for f in (packet.get("previous_report") or {}).get("findings", []))
    if not set(report.get("previous_findings", {})).issubset(known_prior):
        raise ValueError("review cannot dispose of findings absent from its packet")
    if packet["unresolved_findings"]:
        required = {f["id"] for f in packet["unresolved_findings"]}
        resolutions = report.get("previous_findings", {})
        if not required.issubset(resolutions):
            raise ValueError("review must explicitly resolve or retain previous required findings")
        current_required = {f["id"] for f in findings if f["severity"] == "required"}
        for finding_id in required:
            resolution = resolutions[finding_id]
            if not isinstance(resolution, dict) or not resolution.get("evidence"):
                raise ValueError("prior finding dispositions require evidence")
            if resolution.get("status") not in {"resolved", "persisting", "regressed", "retained"}:
                raise ValueError("invalid prior finding disposition")
            if resolution["status"] != "resolved" and finding_id not in current_required:
                raise ValueError("unresolved prior required finding must be carried forward as required")
        if verdict == "PASS" and any(resolutions[key].get("status") != "resolved" or not resolutions[key].get("evidence") for key in required):
            raise ValueError("PASS requires evidence resolving previous required findings")
    if kind == "layout":
        if role != "wording" or report.get("pdf_sha256") != packet["build"].get("pdf_sha256"):
            raise ValueError("layout inspection must bind the compiled PDF")
        pages = report.get("pages_inspected")
        page_count = packet["build"]["pdf_pages"]
        if (not isinstance(pages, list) or not pages
                or any(type(page) is not int or not 1 <= page <= page_count for page in pages)
                or len(pages) != len(set(pages))):
            raise ValueError("layout inspection requires distinct, in-range page coverage")
        if verdict == "PASS" and sorted(pages) != list(range(1, page_count + 1)):
            raise ValueError("layout PASS requires inspection of every PDF page")
    elif verdict != "INCOMPLETE":
        coverage = {row.get("checkpoint_id"): row for row in report.get("coverage", [])}
        for checkpoint in packet["rubric"]["checkpoints"]:
            row = coverage.get(checkpoint["id"], {})
            if checkpoint["severity"] == "required" and (not row.get("evidence") or row.get("status") not in {"PASS", "FAIL"}):
                raise ValueError("complete review must cover every required checkpoint with evidence")
            if verdict == "PASS" and checkpoint["severity"] == "required" and row.get("status") != "PASS":
                raise ValueError("PASS requires all required checkpoints to pass")
        if role == "faithfulness":
            expected = {row["id"] for row in packet["source_claims"]["claims"]}
            mapped = {row.get("claim_id"): row for row in report.get("claim_reviews", [])}
            if set(mapped) != expected or any(not row.get("evidence") for row in mapped.values()):
                raise ValueError("faithfulness review must account for every source claim including inherited coverage")
            if report.get("scope") != packet["scope"]:
                raise ValueError("faithfulness coverage must honor comprehensive/incremental packet scope")
            if verdict == "PASS" and any(row.get("status") not in {"faithful", "inherited"} for row in mapped.values()):
                raise ValueError("faithfulness PASS contains unsupported claim coverage")
            if packet["scope"] == "comprehensive" and any(row.get("status") == "inherited" for row in mapped.values()):
                raise ValueError("comprehensive review cannot inherit claim coverage")
    record = {"receipt": _archive(work, "reviews", report_path)}
    revision["layouts" if kind == "layout" else "reviews"].append(record)
    # Archive the exact packet, including rubric and registry versions, for attribution.
    packet_path = work / "writer" / "packets" / (packet["packet_id"] + ".json")
    if not packet_path.exists():
        _write(packet_path, packet, exclusive=True)
    record["packet"] = _receipt(packet_path)
    _write(state_path, state)
    return record


def continue_writing(state_path: Path, approval_evidence: Path, additional_rounds: int) -> dict:
    state, writer, work = _load(state_path)
    if additional_rounds < 1 or not approval_evidence.read_text(encoding="utf-8-sig").strip():
        raise ValueError("positive extension and actual author approval evidence required")
    receipt = _archive(work, "approvals", approval_evidence)
    if receipt in writer["extensions"]:
        raise ValueError("this continuation approval has already been consumed")
    writer["extensions"].append(receipt)
    writer["max_review_rounds"] += additional_rounds
    _write(state_path, state)
    return {"max_review_rounds": writer["max_review_rounds"], "reviewed_revisions": len(writer["revisions"])}


def compile_revision(state_path: Path, timeout: int = 180) -> dict:
    state, writer, work = _load(state_path)
    if not writer["revisions"]:
        raise ValueError("freeze a manuscript revision first")
    revision = writer["revisions"][-1]
    errors = verify_snapshot(revision["snapshot"])
    if errors:
        raise ValueError("frozen manuscript drift: " + "; ".join(errors))
    from .cli import _compile_tex
    target = work / "writer" / "builds" / f"{revision['id']}-{len(revision['builds']) + 1}"
    result = _compile_tex(Path(revision["snapshot"]["roots"][0]["snapshot"]), timeout, retain_dir=target)
    result.update(revision_id=revision["id"], manuscript_sha256=revision["snapshot"]["digest"])
    path = target / "build.json"
    _write(path, result, exclusive=True)
    revision["builds"].append(_receipt(path))
    _write(state_path, state)
    return result


def audit_writing(state_path: Path, require_complete: bool = False) -> dict:
    errors, pending, failed = [], [], []
    status = "needs_plan"
    try:
        state, writer, work = _load(state_path)
        for revision in writer["revisions"]:
            errors.extend(verify_snapshot(revision["snapshot"]))
            _check_receipt(revision["plan"])
            for record in [*revision["reviews"], *revision["layouts"]]:
                _check_receipt(record["receipt"])
                _check_receipt(record["packet"])
                _validate_review_dispositions(_read(Path(record["receipt"]["path"])))
        if writer["revisions"]:
            revision = writer["revisions"][-1]
            # Source and working-copy drift block completion; do not refresh silently.
            errors.extend(verify_snapshot(revision["snapshot"], check_originals=True))
            pending, failed = _review_state(writer, work, revision)
            status = "reviewing" if pending else "needs_revision" if failed else "needs_release_checks"
            if not pending and failed and len(writer["revisions"]) >= writer["max_review_rounds"]:
                status = "limit_pause"
            from .cli import _audit_references, _basic_tex_errors
            errors.extend(_basic_tex_errors(Path(state["output"])))
            errors.extend(_audit_references(state))
            plan = _read(Path(revision["plan"]["path"]))
            from .tex_inventory import inventory_tex
            inventory = inventory_tex(Path(revision["snapshot"]["roots"][0]["snapshot"]))
            main_ids = _read(Path(writer["contract"]["brief"]["path"]))["main_claim_ids"]
            for row in plan["claim_map"]:
                if row["claim_id"] in main_ids:
                    matches = [u for u in inventory["units"] if u.get("label") == row.get("candidate_label") and u["kind"] == "statement" and not u.get("in_appendix")]
                    if len(matches) != 1:
                        errors.append(f"approved main claim missing/duplicated/outside main paper: {row['claim_id']}")
            build = None
            if revision["builds"]:
                _check_receipt(revision["builds"][-1])
                build = _read(Path(revision["builds"][-1]["path"]))
                if build.get("revision_id") != revision["id"] or build.get("manuscript_sha256") != revision["snapshot"]["digest"]:
                    errors.append("build receipt does not match the current frozen revision")
                if build.get("pass"):
                    for artifact, checksum in (("retained_pdf", "pdf_sha256"), ("retained_log", "log_sha256")):
                        if not build.get(artifact) or not build.get(checksum):
                            errors.append(f"successful build lacks retained, hash-bound {artifact}")
                        else:
                            _check_receipt({"path": build[artifact], "sha256": build[checksum]})
                    if type(build.get("pdf_pages")) is not int or build["pdf_pages"] < 1:
                        errors.append("successful release build requires a verified positive PDF page count")
            layout_ok = False
            latest_layouts = {}
            for record in revision["layouts"]:
                report = _read(Path(record["receipt"]["path"]))
                if build and report["bindings"] == _bindings(writer, work, revision, "wording") and report.get("pdf_sha256") == build.get("pdf_sha256"):
                    latest_layouts[report["reviewer_id"]] = report
            layout_ok = bool(latest_layouts) and all(r["verdict"] == "PASS" for r in latest_layouts.values())
            if any(r["verdict"] == "FAIL" for r in latest_layouts.values()):
                failed.append("layout")
                if not pending:
                    status = "limit_pause" if len(writer["revisions"]) >= writer["max_review_rounds"] else "needs_revision"
            # Recompute open obligations on audit as well as on registration. Old
            # accepted PASS records are not a substitute for the current invariant.
            open_ids = set()
            for role, track, kind in [(r, "primary", "content") for r in ROLES] + [
                    ("faithfulness", "secondary", "content"), ("wording", "primary", "layout")]:
                open_ids.update(f["id"] for f in _open_findings(writer, role, track, kind, "", ""))
            if open_ids:
                errors.append("unresolved required findings: " + ", ".join(sorted(open_ids)))
            ready = not pending and not failed and build and build.get("pass") and layout_ok and not errors
            if ready:
                status = "complete"
            if require_complete:
                if pending:
                    errors.append("pending current independent reviews: " + ", ".join(pending))
                if failed:
                    errors.append("required repairs: " + ", ".join(failed))
                if not build or not build.get("pass"):
                    errors.append("successful frozen-revision compilation required")
                if not layout_ok:
                    errors.append("current rendered-document inspection required")
        elif require_complete:
            errors.append("no frozen reviewed manuscript")
        if errors:
            status = "blocked" if not pending and not failed else status
        return {"pass": not errors, "status": status, "errors": errors, "pending_roles": pending,
                "failed_roles": failed, "reviewed_revisions": len(writer["revisions"]),
                "max_review_rounds": writer["max_review_rounds"],
                "meaning": "Writing contract only; no new mathematical grade or novelty certification."}
    except (ValueError, OSError, KeyError, TypeError) as error:
        return {"pass": False, "status": "blocked", "errors": [str(error)]}


def resume_writing(state_path: Path) -> dict:
    result = audit_writing(state_path)
    result["next_action"] = {"needs_plan": "record-writing-plan", "reviewing": "review-packet",
                             "needs_revision": "record-writing-plan", "limit_pause": "author_direction",
                             "needs_release_checks": "compile_and_rendered_inspection",
                             "complete": None, "blocked": "resolve_reported_blocker"}[result["status"]]
    return result


def mark_writing_gate(state_path: Path, name: str, status: str, evidence: list[str]) -> dict:
    if name != "final" or status != "pass":
        raise ValueError("recursive gates are derived from writing artifacts; use the writing commands")
    report = audit_writing(state_path, require_complete=True)
    if not report["pass"] or report["status"] != "complete":
        raise ValueError("cannot pass final: " + "; ".join(report["errors"]))
    state, _, _ = _load(state_path)
    state["gates"]["final"] = {"status": "pass", "evidence": evidence, "protocol": "recursive-writer-1"}
    _write(state_path, state)
    return state
