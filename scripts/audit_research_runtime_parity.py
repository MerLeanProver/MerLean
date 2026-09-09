#!/usr/bin/env python3
"""Audit semantic safeguards and exact shared-source parity across all six distributions."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from build_bundles import AGENTS, PROVIDERS, ROOT, build_bundle, source_entries, write_archive
except ModuleNotFoundError:
    from scripts.build_bundles import AGENTS, PROVIDERS, ROOT, build_bundle, source_entries, write_archive

MARKERS = {
    "lite": ["HYPOTHESIS FIREWALL", "CLASS-VS-CARRIER GATE", "INTENDED-MODEL GATE", "GOAL-PATH / INTENDED-BINDING GATE", "intended_model_bindings", "premise_ids", "open-residual", "target-contract.json"],
    "auto": ["HYPOTHESIS FIREWALL", "THEOREM-FACE CLOSURE", "INTENDED-MODEL GATE", "GOAL-PATH / INTENDED-BINDING GATE", "intended_model_bindings", "premise_ids", "necessary, not sufficient", "target-contract.json", "plan_statement_id", "verification-manifest.json", "formalization_cost", "PLAN_OFFLINE=1"],
    "formalize": ["HYPOTHESIS", "INTENDED-MODEL GATE", "necessary, not sufficient", "formalization_cost", "COST-OF-FORMALIZATION GATE", "PLAN_OFFLINE=1"],
    "formalizeproblem": ["HYPOTHESIS FIREWALL", "INTENDED-MODEL GATE", "toy replacement"],
    "prove": ["HYPOTHESIS FIREWALL", "THEOREM-FACE CLOSURE", "necessary, not sufficient", "COST-OF-FORMALIZATION GATE", "PLAN_OFFLINE=1"],
    "skeptic": ["HYPOTHESIS FIREWALL", "CLASS-VS-CARRIER", "INTENDED-MODEL"],
    "nl-prover": ["assumptions-added", "open-residual", "Subsingleton"],
    "route-scout": ["assumption-census.md", "ORIGINAL/PROVED/exact-CITED"],
    "compile-fix": ["goal_equivalent_premises", "definition_independence", "intended_model_status"],
}

PATHS = {
    "lite": "workflows/lite-research.md", "auto": "workflows/auto-research.md",
    "formalize": "workflows/formalize.md", "formalizeproblem": "workflows/formalizeproblem.md",
    "prove": "workflows/prove.md",
    **{role: f"roles/{role}.md" for role in ("skeptic", "nl-prover", "route-scout", "compile-fix")},
}


def audit(root: Path = ROOT) -> list[str]:
    errors = []
    # Retain the former semantic omission checks, now on one maintained source.
    for key, relative in PATHS.items():
        body = (root / relative).read_text()
        for marker in MARKERS[key]:
            if marker not in body:
                errors.append(f"{relative}: missing safeguard {marker}")
    # Equality is now whole-file, not merely selected paragraphs in hand-maintained ports.
    shared = source_entries(root)
    with tempfile.TemporaryDirectory(prefix="merlean-parity-") as temp:
        for provider in PROVIDERS:
            for agent in AGENTS:
                package = build_bundle(provider, agent, Path(temp), root=root)
                for relative, (body, mode) in shared.items():
                    if (package / relative).read_bytes() != body:
                        errors.append(f"{package.name}: shared source drift: {relative}")
                public = list(package.glob("skills/*/SKILL.md"))
                if len(public) != 1 or public[0].parent.name != agent:
                    errors.append(f"{package.name}: public-agent inventory mismatch")
                elif f"ports/{provider}.md" not in public[0].read_text():
                    errors.append(f"{package.name}: missing provider binding")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--treeish")
    args = parser.parse_args()
    if args.treeish:
        with tempfile.TemporaryDirectory(prefix="merlean-parity-release-") as temp:
            run = subprocess.run([sys.executable, str(ROOT / "scripts/build_codex_release.py"),
                                  "--treeish", args.treeish, "--out", temp], check=False)
            return run.returncode
    errors = audit()
    print("FAIL" if errors else "PASS: six bundles share the exact runtime, workflows, roles, and strict semantic gates")
    for error in errors:
        print("- " + error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
