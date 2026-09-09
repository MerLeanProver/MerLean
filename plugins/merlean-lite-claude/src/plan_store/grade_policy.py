"""Write policy for semantic verification grades stored on plan nodes."""

from __future__ import annotations

import math
from typing import Any, Mapping


GOLD_INVALIDATING_FIELDS = {
    "type", "name", "content", "dependencies", "proof", "anchor", "mathlib_types",
    "lean_path", "corrections", "do_not_import", "declarations_defined", "imports",
    "source_start", "source_end", "status", "proof_status", "claim_scope", "result_scope",
    "condition_ids", "boundary_axiom_ids", "question_status", "research_value",
    "evidence_closure_sha256", "trust_roots", "open_assumptions", "intended_instance",
    "source_locators", "goal_id", "goal_role", "consumer_path", "directionality",
    "goal_contract_sha256", "goal_alignment_sha256", "intended_model_bindings",
}


def reject_untrusted_gold(fields: Mapping[str, Any]) -> None:
    """Reject Gold claims outside the dedicated audited-grade path.

    Ordinary CRUD remains suitable for BRONZE/SILVER workflow metadata.  Gold and its
    evidence are protected because accepting them through ``add``/``update``/JSON import
    would turn the semantic audit into an optional convention.  ``None`` is allowed so
    reconciliation can invalidate stale evidence.
    """
    if fields.get("verification_grade") == "GOLD":
        raise ValueError(
            "verification_grade=GOLD is audit-controlled; run the research grade auditor"
        )
    if fields.get("gold_audit") is not None:
        raise ValueError("gold_audit is audit-controlled and cannot be set by generic CRUD")


def _same_json_value(left: Any, right: Any) -> bool:
    """Compare JSON metadata without Python's bool/int equality coercion.

    Unsupported values fail closed; dictionary order is immaterial, list order is not.
    """
    kind = type(left)
    if kind is not type(right):
        return False
    if kind in (str, bool, int, type(None)):
        return left == right
    if kind is float:
        return math.isfinite(left) and math.isfinite(right) and left == right
    if kind is list:
        return len(left) == len(right) and all(
            _same_json_value(a, b) for a, b in zip(left, right)
        )
    if kind is dict:
        return (
            all(type(key) is str for key in left)
            and all(type(key) is str for key in right)
            and left.keys() == right.keys()
            and all(_same_json_value(left[key], right[key]) for key in left)
        )
    return False


def invalidate_gold_for_mutation(node: Mapping[str, Any], fields: Mapping[str, Any]) -> dict[str, Any]:
    """Return an update payload that clears Gold after a semantic mutation."""
    updated = dict(fields)
    if (
        node.get("verification_grade") == "GOLD"
        and any(
            key not in node or not _same_json_value(node[key], fields[key])
            for key in GOLD_INVALIDATING_FIELDS.intersection(fields)
        )
    ):
        updated["verification_grade"] = None
        updated["gold_audit"] = None
    return updated
