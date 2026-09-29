"""Import an assessed prospectus without treating it as a verified manuscript.

The source run remains authoritative. Local evidence copies make the handoff inspectable,
while receipts prevent an edited import from silently changing the selected contribution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .coverage import write_json
from .versioning import sha256_file


def hypothesis_surface(claim: dict[str, Any]) -> str:
    return "\n".join(claim["hypotheses"]) or "No additional hypotheses beyond the frozen statement."


def manuscript_digest(inventory: dict[str, Any]) -> str:
    """Include root macros, included definitions, and standing hypotheses in a review."""
    return hashlib.sha256(json.dumps(inventory["source_files"], sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def import_handoff(bundle: dict[str, Any], work: Path) -> dict[str, Any]:
    """Copy validated evidence into an already exclusively created compose workspace."""
    from .synthesis import verify_handoff
    verify_handoff(bundle)
    target = work / "synthesis"
    target.mkdir(exist_ok=False)
    write_json(target / "handoff.json", bundle)
    evidence_map: dict[str, str] = {}
    for record in bundle["provenance_files"]:
        source = Path(record["path"])
        if not source.is_file() or source.is_symlink() or sha256_file(source) != record["sha256"]:
            raise ValueError(f"synthesis evidence changed during import: {source}")
        # Content-addressed copies avoid path traversal and basename collisions.
        destination = target / "evidence" / (record["sha256"] + source.suffix)
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            with destination.open("xb") as handle:
                handle.write(source.read_bytes())
        if sha256_file(destination) != record["sha256"]:
            raise ValueError(f"synthesis evidence changed while copying: {source}")
        evidence_map[str(source)] = str(destination)
    write_json(target / "evidence-map.json", evidence_map)

    main_ids = bundle["candidate"]["main_claim_ids"]
    graph = {
        "schema_version": 1,
        "selected_main_results": main_ids,
        "nodes": [
            {
                "id": claim["id"], "kind": "theorem", "content": claim["statement"],
                "hypothesis_surface": hypothesis_surface(claim),
                "proof_status": claim["proof_status"],
                "grade_metadata": claim.get("grade_metadata"),
                # A paper import never manufactures a research grade.
                "grade": "UNVERIFIED", "source_refs": claim["source_refs"],
            }
            for claim in bundle["claims"]
        ],
        "edges": [
            {"source": parent, "target": claim["id"]}
            for claim in bundle["claims"] for parent in claim["dependencies"]
        ],
    }
    write_json(target / "graph.json", graph)
    novelty = next(review for review in bundle["reviews"] if review["kind"] == "novelty")
    main_results = []
    lines = ["# Approved synthesis contribution", "", bundle["candidate"]["title"], "",
             "The exact source statements below are frozen. Review the imported dependency graph;",
             "do not repeat broad topic selection. TeX statement locks and equivalence checks remain pending.", ""]
    for claim in bundle["main_claims"]:
        label = "thm:synthesis-" + hashlib.sha256(claim["id"].encode()).hexdigest()[:12]
        main_results.append({
            "graph_node_id": claim["id"], "candidate_label": label,
            "normalized_sha256": None,
            "hypothesis_surface": hypothesis_surface(claim),
            "novelty_status": novelty["novelty_code"],
            "novelty_evidence": novelty["findings"],
            "synthesis_candidate_digest": bundle["candidate_digest"],
            "source_statement_sha256": hashlib.sha256(claim["statement"].encode()).hexdigest(),
            "source_equivalence_audits": [],
        })
        lines.extend([f"## {claim['id']}", "", claim["statement"], "",
                      "Hypotheses: " + hypothesis_surface(claim), "",
                      "Proof status: " + claim["proof_status"], ""])
    write_json(work / "03-main-results.json", {"schema_version": 1, "main_results": main_results})
    (work / "03-main-results.md").write_text("\n".join(lines), encoding="utf-8")

    registry = {"schema_version": 1, "references": []}
    bibliography_parts: list[str] = []
    bibliography = target / "references.bib"
    for reference in bundle["references"]:
        entry = dict(reference)
        for key, value in entry.items():
            if isinstance(value, str) and value in evidence_map:
                entry[key] = evidence_map[value]
        if entry.get("bibtex_snapshot"):
            bibliography_parts.append(Path(entry["bibtex_snapshot"]).read_text(encoding="utf-8"))
        entry["bibliography_path"] = str(bibliography)
        # For arXiv, the imported exact TeX excerpts are all in this copied evidence directory.
        if entry.get("source_type") == "arxiv":
            entry["source_dir"] = str(target / "evidence")
        registry["references"].append(entry)
    bibliography.write_text("\n\n".join(bibliography_parts), encoding="utf-8")
    write_json(work / "references-registry.json", registry)
    verify_handoff(bundle)
    frozen_files = [*sorted(path for path in target.rglob("*") if path.is_file())]
    return {
        "state": bundle["synthesis_state"],
        "candidate_digest": bundle["candidate_digest"],
        "handoff": str(target / "handoff.json"),
        "files": [{"path": str(path), "sha256": sha256_file(path)} for path in frozen_files],
    }


def verify_import(state: dict[str, Any]) -> dict[str, Any] | None:
    origin = state.get("synthesis_origin")
    if not origin:
        return None
    target = Path(state["work_dir"]).resolve() / "synthesis"
    records = origin.get("files", [])
    if not records:
        raise ValueError("synthesis import lacks its evidence receipt")
    paths = set()
    for record in records:
        path = Path(record["path"])
        if not path.resolve().is_relative_to(target) or path.is_symlink():
            raise ValueError("synthesis receipt escapes the imported evidence directory")
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"imported synthesis evidence is missing or changed: {path}")
        paths.add(str(path.resolve()))
    handoff = Path(origin["handoff"])
    if str(handoff.resolve()) not in paths:
        raise ValueError("synthesis handoff is not covered by the receipt")
    bundle = json.loads(handoff.read_text(encoding="utf-8"))
    if bundle["candidate_digest"] != origin["candidate_digest"]:
        raise ValueError("imported synthesis candidate changed")
    from .synthesis import verify_handoff
    verify_handoff(bundle)
    return bundle


def audit_imported_main_results(state: dict[str, Any], results: list[dict], inventory: dict) -> list[str]:
    """Bind the final TeX locks to the original approved mathematical content."""
    bundle = verify_import(state)
    if bundle is None:
        return []
    errors: list[str] = []
    claims = {claim["id"]: claim for claim in bundle["main_claims"]}
    context_digest = manuscript_digest(inventory)
    source_work = Path(bundle["synthesis_state"]).parent
    authors = {
        json.loads((source_work / filename).read_text(encoding="utf-8-sig"))["authored_by"]
        for filename in ("claim-ledger.json", "candidate-prospectuses.json")
    }
    if {row.get("graph_node_id") for row in results} != set(claims):
        errors.append("compose main results differ from the approved synthesis selection")
    for row in results:
        claim = claims.get(row.get("graph_node_id"))
        if not claim:
            continue
        claim_id = claim["id"]
        source_hash = hashlib.sha256(claim["statement"].encode()).hexdigest()
        if (row.get("hypothesis_surface") != hypothesis_surface(claim)
                or row.get("synthesis_candidate_digest") != bundle["candidate_digest"]
                or row.get("source_statement_sha256") != source_hash):
            errors.append(f"synthesis source statement or hypotheses changed: {claim_id}")
        units = [unit for unit in inventory["units"] if unit.get("label") == row.get("candidate_label")
                 and unit.get("kind") == "statement" and not unit.get("in_appendix")]
        if len(units) != 1:
            continue  # Ordinary compose checks explain missing/duplicate statements.
        unit = units[0]
        # Exact TeX alone is insufficient: hypotheses and macro meanings can live elsewhere.
        reviewers = set()
        for audit in row.get("source_equivalence_audits", []):
            if (audit.get("verdict") != "PASS" or not audit.get("findings")
                    or audit.get("candidate_digest") != bundle["candidate_digest"]
                    or audit.get("source_statement_sha256") != source_hash
                    or audit.get("manuscript_sha256") != context_digest
                    or audit.get("candidate_normalized_sha256") != unit["normalized_sha256"]):
                continue
            evidence = Path(str(audit.get("evidence_file") or "."))
            if not evidence.is_absolute():
                evidence = Path(state["work_dir"]) / evidence
            if (evidence.is_file() and not evidence.is_symlink()
                    and evidence.resolve().is_relative_to(Path(state["work_dir"]).resolve())
                    and sha256_file(evidence) == audit.get("evidence_sha256")
                    and audit.get("auditor") and audit["auditor"] not in authors):
                reviewers.add(audit["auditor"])
        if len(reviewers) < 2:
            errors.append(f"synthesis main result needs two hash-bound scope/equivalence reviews: {claim_id}")
    return errors
