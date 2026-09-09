import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_research_grade import audit_manifest
import research_grade
from research_grade import (
    STRUCTURAL_CLASS_ALLOWLIST,
    TRUSTED_DATA_STRUCTURE_ALLOWLIST,
    record_audited_gold,
)
from plan_store.offline_store import OfflinePlanGraph
from plan_store.lean_sync import _gold_evidence_is_current, reconcile_status_from_lean


FIXTURES = Path(__file__).parent / "semantic_manifests"


class ResearchGradeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="merlean-grade-test-")
        self.base = Path(self.temp.name)
        self.mathlib_revision = "a" * 40
        self.lake_manifest_hash = "b" * 64
        self.mathlib_identity_patch = patch(
            "research_grade._installed_mathlib_identity",
            return_value=(self.mathlib_revision, self.lake_manifest_hash),
        )
        self.mathlib_identity_patch.start()

    def tearDown(self):
        self.mathlib_identity_patch.stop()
        self.temp.cleanup()

    def load(self, name):
        return json.loads((FIXTURES / name).read_text())

    def write(self, name, value):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, (dict, list)):
            payload = (json.dumps(value, indent=2) + "\n").encode()
        else:
            payload = str(value).encode()
        path.write_bytes(payload)
        return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}

    def attach_goal_alignment(
        self, manifest, *, target_hash, lean, adapter_decl,
        classification="sufficient_milestone", directionality="sufficient_only",
    ):
        question_source = self.write(
            "research-question.txt",
            "Decide whether the specified intended object has the requested property.\n",
        )
        goal_contract = self.write("goal-contract.json", {
            "schema_version": 2,
            "goal_id": "synthetic-research-goal",
            "question": "Decide whether the specified intended object has the requested property.",
            "question_source": question_source,
            "intended_objects": [{
                "id": "intended-target",
                "description": "The exact intended target object named by the frozen research question.",
            }],
            "goal_theorem_face_ids": ["research-answer"],
            "answer_criterion": "A theorem proving or disproving the requested property for the intended target.",
        })
        report = self.write(f"goal-alignment-{classification}.json", {
            "verdict": "passed",
            "auditor": "goal-path-auditor",
            "goal_id": "synthetic-research-goal",
            "goal_contract_sha256": goal_contract["sha256"],
            "target_signature_hash": target_hash,
            "classification": classification,
            "directionality": directionality,
            "consumer_path": ["main", "research-answer"],
            "findings": {
                "target_match": "The frozen target is compared directly with the exact research question.",
                "consumer_path": "The displayed consumer path reaches the named research-answer theorem face.",
                "directionality": "The recorded logical direction is the strongest direction established by the target.",
                "intended_objects": "The adapter declaration binds the formal target to the sole intended object.",
            },
        })
        manifest["goal_contract"] = goal_contract
        manifest["goal_alignment"] = {
            "status": "passed", "auditor": "goal-path-auditor", "report": report,
        }
        manifest["intended_model_bindings"] = [{
            "goal_object_id": "intended-target", "status": "completed",
            "binder_ids": [], "adapter_decl": adapter_decl, "lean_file": lean,
        }]

    def valid_gold(self):
        signature = "theorem Main (baseFinite : True) : True"
        target_hash = hashlib.sha256(signature.encode()).hexdigest()
        source = self.write("source.txt", signature + "\n")
        lean = self.write(
            "Gold.lean",
            "theorem PrimaryVanishes : True := by trivial\n"
            "def Stage8Adapter : True := True.intro\n"
            "theorem Main (baseFinite : True) : True := by trivial\n",
        )
        contract = self.write("target-contract.json", {
            "schema_version": 1,
            "target_signature": signature,
            "dossier_signature": signature,
            "target_signature_hash": target_hash,
            "dossier_signature_hash": target_hash,
            "source_files": [source],
            "original_premise_ids": ["baseFinite"],
            "theorem_face_ids": ["main"],
            "interface_ids": ["stage8"],
        })
        kernel_data = {
            "schema_version": 1,
            "target_signature_hash": target_hash,
            "root_declarations": [{
                "name": "Main",
                "signature": signature,
                "signature_hash": target_hash,
                "proof_status": "completed",
                "axioms": [],
                "premise_ids": ["baseFinite", "primaryVanishes"],
                "theorem_face_ids": ["main"],
                "interface_ids": ["stage8"],
                "lean_file": lean,
            }],
        }
        kernel = self.write("kernel-evidence.json", kernel_data)
        independence = self.write("definition-independence.txt", "constructed independently\n")
        report = self.write("independent-audit.txt", "PASS: target, premises, model, faces\n")
        manifest = {
            "schema_version": 1,
            "grade": "GOLD",
            "manifest_author": "formalizer",
            "target_contract": contract,
            "kernel_evidence": kernel,
            "axioms": [],
            "assumptions": [
                {
                    "id": "baseFinite", "name": "baseFinite", "kind": "original",
                    "status": "closed", "relation_to_goal": "none",
                    "source_locator": "source.txt:1",
                },
                {
                    "id": "primaryVanishes", "name": "primaryVanishes", "kind": "derived",
                    "status": "closed", "relation_to_goal": "none",
                    "proof_status": "completed", "lean_decl": "PrimaryVanishes",
                    "lean_file": lean,
                },
            ],
            "interfaces": [{
                "id": "stage8", "name": "Stage8Data",
                "intended_instance": {
                    "adapter_decl": "Stage8Adapter", "proof_status": "completed",
                    "axioms": [], "lean_file": lean,
                },
            }],
            "theorem_faces": [{
                "id": "main", "name": "main theorem", "covered": True,
                "lean_decl": "Main", "source_locator": "source.txt:1",
            }],
            "definition_independence": {"status": "verified", "evidence": independence},
            "independent_gold_audit": {
                "status": "passed", "auditor": "semantic-auditor", "report": report,
            },
        }
        return manifest, kernel_data

    def test_legacy_v1_gold_rejected(self):
        manifest, _ = self.valid_gold()
        errors = audit_manifest(manifest, self.base)
        self.assertTrue(any("SCHEMA_VERSION" in error for error in errors))

    def conditional_gold(self, *, with_boundary=False):
        binder = "hData : True"
        signature = f"theorem ConditionalMain ({binder}) : True"
        target_hash = hashlib.sha256(signature.encode()).hexdigest()
        source = self.write("source.txt", signature + "\n")
        lean = self.write(
            "Conditional.lean",
            "def IntendedTargetAdapter : True := True.intro\n" + signature + " := by trivial\n",
        )
        original_ids = []
        condition_ids = [] if with_boundary else ["hData"]
        boundary_ids = ["hData"] if with_boundary else []
        contract = self.write("target-contract.json", {
            "schema_version": 2,
            "plan_statement_id": "main",
            "result_scope": "conditional",
            "target_signature": signature,
            "dossier_signature": signature,
            "target_signature_hash": target_hash,
            "dossier_signature_hash": target_hash,
            "source_files": [source],
            "structural_binders": [],
            "data_binder_ids": [],
            "intended_model_binder_ids": [],
            "original_premise_ids": original_ids,
            "condition_premise_ids": condition_ids,
            "boundary_premise_ids": boundary_ids,
            "theorem_face_ids": ["main"],
            "interface_ids": [],
        })
        premise_id = "hData"
        kernel = self.write("kernel-evidence.json", {
            "schema_version": 2,
            "target_signature_hash": target_hash,
            "root_declarations": [{
                "name": "ConditionalMain",
                "signature": signature,
                "signature_hash": target_hash,
                "proof_status": "completed",
                "axioms": [],
                "premise_ids": [premise_id],
                "theorem_face_ids": ["main"],
                "interface_ids": [],
                "lean_file": lean,
            }],
        })
        independence = self.write("definition-independence.json", {
            "verdict": "verified", "target_signature_hash": target_hash,
            "checks": {
                "target_not_stored_as_field": True,
                "target_not_definitionally_encoded": True,
                "constructors_independent": True,
                "dependency_cone_reviewed": True,
            },
            "findings": {
                "target_not_stored_as_field": "No input field has the target type.",
                "target_not_definitionally_encoded": "The conclusion is proved by the theorem body.",
                "constructors_independent": "All constructors precede and do not depend on the root.",
                "dependency_cone_reviewed": "The dependency cone contains only the displayed helper declarations.",
            },
        })
        gold_report = self.write("gold-audit.json", {
            "verdict": "passed", "target_signature_hash": target_hash,
            "auditor": "semantic-auditor",
            "question_status": "conditional_advance",
            "research_value": "advances_question",
            "checks": {
                "target": True, "premises": True, "public_antecedents": True,
                "structural_context": True,
                "kernel_runtime": True, "interfaces": True, "theorem_faces": True,
                "definition_independence": True, "research_scope": True,
            },
            "findings": {
                "target": "The source and frozen theorem signature agree.",
                "premises": "The premise census is complete.",
                "public_antecedents": "Every proposition premise is a direct binder.",
                "structural_context": "There are no explicit instance binders.",
                "kernel_runtime": "The independently rerun Lean audit succeeded.",
                "interfaces": "There are no hidden or uninstantiated interfaces.",
                "theorem_faces": "The sole theorem face is mapped to the root.",
                "definition_independence": "The conclusion is not stored in the inputs.",
                "research_scope": "The conditional advance label matches the narrow target.",
            },
        })
        if with_boundary:
            mathlib_revision = self.mathlib_revision
            ref_payload = "Theorem 7. If True holds, then True holds.\n"
            ref_source = self.write("refs/book.txt", ref_payload)
            boundary_findings = {
                "source_match": "The quoted source span is exact.",
                "hypotheses": "The source and Lean hypotheses correspond bijectively.",
                "conclusion": "The source and Lean conclusions are identical.",
                "notation": "The notation map is complete.",
                "use_site": "The public root exposes the exact boundary binder.",
            }
            audit1 = self.write("boundary-audit-sol-1.json", {
                "verdict": "passed", "boundary_id": "hData", "auditor": "sol-a",
                "source_sha256": ref_source["sha256"], "lean_binder": binder,
                "findings": boundary_findings,
            })
            audit2 = self.write("boundary-audit-sol-2.json", {
                "verdict": "passed", "boundary_id": "hData", "auditor": "sol-b",
                "source_sha256": ref_source["sha256"], "lean_binder": binder,
                "findings": boundary_findings,
            })
            mathlib_query = "exact synthetic external theorem name and namespace"
            search_transcript = self.write(
                "boundary-mathlib-search.txt",
                f"Mathlib revision {mathlib_revision}\nquery: {mathlib_query}\nresult: no declaration found\n",
            )
            attempt_evidence1 = self.write(
                "boundary-proof-attempt-1.txt",
                "Attempted reduction to existing primitives; blocked because the external theory is absent.\n",
            )
            attempt_evidence2 = self.write(
                "boundary-proof-attempt-2.txt",
                "Attempted a direct definition-and-induction route; blocked by the same missing external infrastructure.\n",
            )
            cost_record = self.write("boundary-cost-record.json", {
                "boundary_id": "hData",
                "source_sha256": ref_source["sha256"],
                "standard_result": True,
                "mathlib_status": "not_available",
                "mathlib_revision": mathlib_revision,
                "lake_manifest_sha256": self.lake_manifest_hash,
                "mathlib_queries": [mathlib_query],
                "mathlib_search_transcript": search_transcript,
                "attempted_routes": [{
                    "route": "Reduce the use site to existing library primitives.",
                    "outcome": "Blocked by the absence of the required external theory.",
                    "evidence": attempt_evidence1,
                }, {
                    "route": "Build the theorem directly from definitions and induction.",
                    "outcome": "Blocked by missing external infrastructure larger than the local campaign.",
                    "evidence": attempt_evidence2,
                }],
                "decision": "disproportionate_to_campaign_role",
                "campaign_role": "A standard leaf used once by the synthetic campaign root.",
                "estimated_formalization_scope": "A separate external theory substantially larger than the local proof.",
                "justification": "Rebuilding that theory would dominate the campaign while adding no local argument.",
            })
            cost_findings = {
                "standardness": "The primary source and mathematical usage identify a standard external theorem.",
                "mathlib_absence": "The hashed search transcript at the recorded revision contains all declared queries.",
                "attempts": "The hashed attempt records a concrete reduction route and its exact missing dependency.",
                "relative_cost": "The estimated external formalization is disproportionate to this theorem's leaf role.",
                "boundary_appropriateness": "Deferral is appropriate only at the exact public source-matched binder.",
            }
            cost_audit1 = self.write("boundary-cost-audit-sol-1.json", {
                "verdict": "passed", "boundary_id": "hData", "auditor": "cost-sol-a",
                "source_sha256": ref_source["sha256"],
                "cost_record_sha256": cost_record["sha256"], "findings": cost_findings,
            })
            cost_audit2 = self.write("boundary-cost-audit-sol-2.json", {
                "verdict": "passed", "boundary_id": "hData", "auditor": "cost-sol-b",
                "source_sha256": ref_source["sha256"],
                "cost_record_sha256": cost_record["sha256"], "findings": cost_findings,
            })
            primary = self.write(
                "refs/primary-book-excerpt.txt",
                "===== ORIGINAL LINES 1--1 =====\nTheorem 7. If True holds, then True holds.\n",
            )
            joint_face_findings = {
                "notation": "The single source leaf and public boundary use the same proposition True.",
                "hypotheses": "The complete face has one independent leaf and no compatibility edge obligations.",
            }
            joint_face_audit1 = self.write("refs/joint-face-audit-sol-1.json", {
                "verdict": "passed", "auditor": "joint-sol-a", "boundary_id": "hData",
                "source_sha256": ref_source["sha256"], "boundary_ids": ["hData"],
                "edges": [], "findings": joint_face_findings,
            })
            joint_face_audit2 = self.write("refs/joint-face-audit-sol-2.json", {
                "verdict": "passed", "auditor": "joint-sol-b", "boundary_id": "hData",
                "source_sha256": ref_source["sha256"], "boundary_ids": ["hData"],
                "edges": [], "findings": joint_face_findings,
            })
            source_closure = self.write("refs/source-closure.json", {
                "schema_version": 1,
                "status": "self_contained",
                "primary_sources": [{
                    "id": "primary-book", "evidence": primary,
                    "exact_excerpt": True,
                    "original_full_sha256": "c" * 64,
                    "locators": ["===== ORIGINAL LINES 1--1 ====="],
                }],
                "leaves": [{
                    "id": "leaf-book-theorem", "boundary_ids": ["hData"],
                    "packet": ref_source, "primary_ids": ["primary-book"],
                    "hypothesis_checklist": [{
                        "source": "The theorem assumes the proposition True.",
                        "lean": "The direct public binder is hData : True.",
                        "status": "exact",
                    }],
                    "conclusion_checklist": [{
                        "source": "The theorem concludes the proposition True.",
                        "lean": "The source package supplies exactly True.",
                        "status": "exact",
                    }],
                }],
                "faces": [{
                    "id": "hData", "joint_source_sha256": ref_source["sha256"],
                    "boundary_ids": ["hData"],
                    "leaf_ids": ["leaf-book-theorem"],
                    "independent_leaf_ids": ["leaf-book-theorem"],
                    "compatibility_edges": [],
                    "joint_face_audits": [
                        {"auditor": "joint-sol-a", "report": joint_face_audit1},
                        {"auditor": "joint-sol-b", "report": joint_face_audit2},
                    ],
                }],
            })
            assumptions = [{
                "id": "hData", "name": "book theorem", "kind": "boundary",
                "status": "source-verified", "relation_to_goal": "none",
                "exposure": "direct_binder", "lean_binder": binder,
                "correspondence": "exact", "source_evidence": ref_source,
                "source_closure": source_closure,
                "formalization_cost": {
                    "record": cost_record,
                    "independent_decision_audits": [
                        {"auditor": "cost-sol-a", "status": "passed", "report": cost_audit1},
                        {"auditor": "cost-sol-b", "status": "passed", "report": cost_audit2},
                    ],
                },
                "source_quote": ref_payload.strip(),
                "source_locator": {"label": "Theorem 7", "line_start": 1, "line_end": 1},
                "notation_map": [{"source": "True", "lean": "True"}],
                "hypothesis_checklist": [{"source": "True holds", "lean": "hData : True", "status": "exact"}],
                "conclusion_checklist": [{"source": "True holds", "lean": "True", "status": "exact"}],
                "independent_source_audits": [
                    {"auditor": "sol-a", "status": "passed", "report": audit1},
                    {"auditor": "sol-b", "status": "passed", "report": audit2},
                ],
            }]
        else:
            assumptions = [{
                "id": "hData", "name": "input data", "kind": "condition",
                "status": "declared", "relation_to_goal": "none",
                "source_locator": "source.txt:1", "exposure": "direct_binder",
                "lean_binder": binder,
                "introduction_rationale": "This exact conditional theorem takes the input publicly.",
            }]
        manifest = {
            "schema_version": 2,
            "grade": "GOLD",
            "result_scope": "conditional",
            "question_status": "conditional_advance",
            "research_value": "advances_question",
            "manifest_author": "formalizer",
            "target_contract": contract,
            "kernel_evidence": kernel,
            "axioms": [],
            "assumptions": assumptions,
            "interfaces": [],
            "theorem_faces": [{
                "id": "main", "name": "conditional theorem", "covered": True,
                "lean_decl": "ConditionalMain", "source_locator": "source.txt:1",
                "premise_ids": ["hData"], "interface_ids": [],
            }],
            "definition_independence": {"status": "verified", "evidence": independence},
            "independent_gold_audit": {
                "status": "passed", "auditor": "semantic-auditor", "report": gold_report,
            },
        }
        self.attach_goal_alignment(
            manifest, target_hash=target_hash, lean=lean, adapter_decl="IntendedTargetAdapter",
        )
        return manifest

    def test_valid_conditional_gold(self):
        self.assertEqual(
            audit_manifest(self.conditional_gold(), self.base, kernel_runtime_verified=True), []
        )

    def test_runtime_binder_census_does_not_unfold_negated_result(self):
        signature = "theorem NegativeMain (hData : True) : ¬ False"
        target_hash = hashlib.sha256(signature.encode()).hexdigest()
        lean = self.write("NegativeMain.lean", signature + " := by simp\n")
        audit_file = self.write(
            "runtime-plan.txt",
            "The generated runtime audit checks the exact root and its declared binder prefix.\n",
        )
        contract = self.write("negative-target-contract.json", {
            "schema_version": 2,
            "result_scope": "conditional",
            "target_signature": signature,
            "dossier_signature": signature,
            "target_signature_hash": target_hash,
            "dossier_signature_hash": target_hash,
            "source_files": [],
            "structural_binders": [],
            "data_binder_ids": [],
            "intended_model_binder_ids": [],
            "original_premise_ids": [],
            "condition_premise_ids": ["hData"],
            "boundary_premise_ids": [],
            "theorem_face_ids": ["negative"],
            "interface_ids": [],
        })
        transcript = "\n".join([
            "NegativeMain (hData : True) : ¬False",
            "'NegativeMain' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_BINDER", "declaration": "NegativeMain", "index": 0,
                "name": "hData", "binderInfo": "explicit", "type": "True",
                "structure": "", "isProp": True,
            }, separators=(",", ":")),
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "NegativeMain",
                "type": "¬False", "isProp": True,
                "isNegation": True, "hasLeadingForall": True,
            }, separators=(",", ":")),
            "",
        ])
        kernel = self.write("negative-kernel.json", {
            "schema_version": 2,
            "target_signature_hash": target_hash,
            "runtime_verification": {
                "lib_dir": ".",
                "audit_file": audit_file,
                "lean_version": "Lean test version",
                "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
            },
            "root_declarations": [{
                "name": "NegativeMain", "signature": signature,
                "signature_hash": target_hash, "proof_status": "completed", "axioms": [],
                "premise_ids": ["hData"], "theorem_face_ids": ["negative"],
                "interface_ids": [], "lean_file": lean,
            }],
        })
        manifest = {
            "grade": "GOLD", "schema_version": 2,
            "kernel_evidence": kernel, "target_contract": contract, "interfaces": [],
        }

        def fake_run(args, **kwargs):
            if args[-1] == "--version":
                return subprocess.CompletedProcess(args, 0, "Lean test version\n", "")
            if args[:2] == ["lake", "build"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            generated = Path(args[-1]).read_text()
            self.assertIn("MerLean.auditBinders ``NegativeMain 1", generated)
            self.assertIn("forallBoundedTelescope info.type declaredBinderCount", generated)
            return subprocess.CompletedProcess(args, 0, transcript, "")

        with patch("research_grade.subprocess.run", side_effect=fake_run):
            self.assertEqual(research_grade.verify_kernel_runtime(manifest, self.base), [])

    def _runtime_shape_audit(self, *, target_signature, roots, transcript, contract_premises):
        target_hash = hashlib.sha256(target_signature.encode()).hexdigest()
        audit_file = self.write(
            "runtime-shape-plan.txt",
            "The generated audit checks result polarity and every root binder census.\n",
        )
        lean_payload = "\n".join(
            root["signature"] + " := by " + root.get("proof", "trivial") for root in roots
        ) + "\n"
        lean = self.write("RuntimeShape.lean", lean_payload)
        contract = self.write("runtime-shape-target-contract.json", {
            "schema_version": 2,
            "result_scope": "conditional",
            "target_signature": target_signature,
            "dossier_signature": target_signature,
            "target_signature_hash": target_hash,
            "dossier_signature_hash": target_hash,
            "source_files": [],
            "structural_binders": [],
            "data_binder_ids": [],
            "intended_model_binder_ids": [],
            "original_premise_ids": [],
            "condition_premise_ids": contract_premises,
            "boundary_premise_ids": [],
            "theorem_face_ids": ["target"],
            "interface_ids": [],
        })
        kernel_roots = []
        for root in roots:
            signature = root["signature"]
            kernel_roots.append({
                "name": root["name"], "signature": signature,
                "signature_hash": hashlib.sha256(signature.encode()).hexdigest(),
                "proof_status": "completed", "axioms": [],
                "premise_ids": root.get("premise_ids", []),
                "data_binder_ids": root.get("data_binder_ids", []),
                "structural_binders": root.get("structural_binders", []),
                "theorem_face_ids": root.get("theorem_face_ids", ["target"]),
                "interface_ids": [], "lean_file": lean,
            })
        kernel = self.write("runtime-shape-kernel.json", {
            "schema_version": 2,
            "target_signature_hash": target_hash,
            "runtime_verification": {
                "lib_dir": ".", "audit_file": audit_file,
                "lean_version": "Lean test version",
                "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
            },
            "root_declarations": kernel_roots,
        })
        manifest = {
            "grade": "GOLD", "schema_version": 2,
            "kernel_evidence": kernel, "target_contract": contract, "interfaces": [],
        }

        def fake_run(args, **kwargs):
            if args[-1] == "--version":
                return subprocess.CompletedProcess(args, 0, "Lean test version\n", "")
            if args[:2] == ["lake", "build"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, transcript, "")

        with patch("research_grade.subprocess.run", side_effect=fake_run):
            return research_grade.verify_kernel_runtime(manifest, self.base)

    def test_runtime_rejects_hidden_implication_after_result_colon(self):
        signature = "theorem HiddenArrow : True → True"
        transcript = "\n".join([
            "HiddenArrow : True → True", "'HiddenArrow' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "HiddenArrow",
                "type": "True → True", "isProp": True,
                "isNegation": False, "hasLeadingForall": True,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=signature,
            roots=[{"name": "HiddenArrow", "signature": signature, "premise_ids": []}],
            transcript=transcript, contract_premises=[],
        )
        self.assertTrue(any("KERNEL_RUNTIME_HIDDEN_RESULT_PREMISE" in e for e in errors))

    def test_runtime_accepts_parenthesized_negation_as_result(self):
        signature = "theorem ParenthesizedNegative : (¬ False)"
        transcript = "\n".join([
            "ParenthesizedNegative : ¬False",
            "'ParenthesizedNegative' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "ParenthesizedNegative",
                "type": "¬False", "isProp": True,
                "isNegation": True, "hasLeadingForall": True,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=signature,
            roots=[{"name": "ParenthesizedNegative", "signature": signature,
                    "premise_ids": [], "proof": "simp"}],
            transcript=transcript, contract_premises=[],
        )
        self.assertFalse(any("HIDDEN_RESULT_PREMISE" in e for e in errors))

    def test_runtime_named_prop_structure_uses_premise_not_data_interface_gate(self):
        signature = "theorem PropStructureMain (hData : True) : True"
        transcript = "\n".join([
            "PropStructureMain (hData : True) : True",
            "'PropStructureMain' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_BINDER", "declaration": "PropStructureMain",
                "index": 0, "name": "hData", "binderInfo": "explicit",
                "type": "True", "structure": "Campaign.CustomCondition",
                "isProp": True,
            }, separators=(",", ":")),
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "PropStructureMain",
                "type": "True", "isProp": True,
                "isNegation": False, "hasLeadingForall": False,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=signature,
            roots=[{"name": "PropStructureMain", "signature": signature,
                    "premise_ids": ["hData"]}],
            transcript=transcript, contract_premises=["hData"],
        )
        self.assertFalse(any("KERNEL_RUNTIME_STRUCTURE_UNAUDITED" in e for e in errors))

    def test_runtime_custom_data_structure_still_requires_interface(self):
        signature = "theorem DataStructureMain (carrier : Nat) : True"
        transcript = "\n".join([
            "DataStructureMain (carrier : Nat) : True",
            "'DataStructureMain' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_BINDER", "declaration": "DataStructureMain",
                "index": 0, "name": "carrier", "binderInfo": "explicit",
                "type": "Nat", "structure": "Campaign.CustomCarrier",
                "isProp": False,
            }, separators=(",", ":")),
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "DataStructureMain",
                "type": "True", "isProp": True,
                "isNegation": False, "hasLeadingForall": False,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=signature,
            roots=[{"name": "DataStructureMain", "signature": signature,
                    "premise_ids": [], "data_binder_ids": ["carrier"]}],
            transcript=transcript, contract_premises=[],
        )
        self.assertTrue(any("KERNEL_RUNTIME_STRUCTURE_UNAUDITED" in e for e in errors))

    def test_runtime_rejects_hidden_forall_after_result_colon(self):
        signature = "theorem HiddenForall : ∀ h : True, True"
        transcript = "\n".join([
            "HiddenForall : ∀ h : True, True", "'HiddenForall' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "HiddenForall",
                "type": "∀ h : True, True", "isProp": True,
                "isNegation": False, "hasLeadingForall": True,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=signature,
            roots=[{"name": "HiddenForall", "signature": signature, "premise_ids": []}],
            transcript=transcript, contract_premises=[],
        )
        self.assertTrue(any("KERNEL_RUNTIME_HIDDEN_RESULT_PREMISE" in e for e in errors))

    def test_runtime_censuses_non_target_theorem_face_root(self):
        target = "theorem RuntimeTarget (hData : True) : True"
        auxiliary = "theorem AuxiliaryFace (hidden : True) : True"
        transcript = "\n".join([
            "RuntimeTarget (hData : True) : True", "'RuntimeTarget' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_BINDER", "declaration": "RuntimeTarget", "index": 0,
                "name": "hData", "binderInfo": "explicit", "type": "True",
                "structure": "", "isProp": True,
            }, separators=(",", ":")),
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "RuntimeTarget", "type": "True",
                "isProp": True, "isNegation": False, "hasLeadingForall": False,
            }, separators=(",", ":")),
            "AuxiliaryFace (hidden : True) : True", "'AuxiliaryFace' depends on axioms: []",
            json.dumps({
                "tag": "MERLEAN_BINDER", "declaration": "AuxiliaryFace", "index": 0,
                "name": "hidden", "binderInfo": "explicit", "type": "True",
                "structure": "", "isProp": True,
            }, separators=(",", ":")),
            json.dumps({
                "tag": "MERLEAN_RESULT", "declaration": "AuxiliaryFace", "type": "True",
                "isProp": True, "isNegation": False, "hasLeadingForall": False,
            }, separators=(",", ":")), "",
        ])
        errors = self._runtime_shape_audit(
            target_signature=target,
            roots=[
                {"name": "RuntimeTarget", "signature": target,
                 "premise_ids": ["hData"], "theorem_face_ids": ["target"]},
                {"name": "AuxiliaryFace", "signature": auxiliary,
                 "premise_ids": [], "theorem_face_ids": ["auxiliary"]},
            ],
            transcript=transcript, contract_premises=["hData"],
        )
        self.assertTrue(any(
            "AuxiliaryFace proposition binders do not equal" in e for e in errors
        ))

    def test_conditional_advance_requires_goal_alignment(self):
        manifest = self.conditional_gold()
        del manifest["goal_contract"]
        del manifest["goal_alignment"]
        del manifest["intended_model_bindings"]
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("GOAL_ALIGNMENT_MISSING" in error for error in errors))
        self.assertTrue(any("INTENDED_MODEL_BINDING_MISSING" in error for error in errors))

    def test_supporting_root_cannot_claim_conditional_advance(self):
        manifest = self.conditional_gold()
        report_ref = manifest["goal_alignment"]["report"]
        report = json.loads((self.base / report_ref["path"]).read_text())
        report["classification"] = "supporting"
        report["directionality"] = "none"
        manifest["goal_alignment"]["report"] = self.write("goal-alignment-supporting.json", report)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("GOAL_ALIGNMENT_INVALID" in error for error in errors))

    def test_intended_goal_object_must_have_completed_binding(self):
        manifest = self.conditional_gold()
        manifest["intended_model_bindings"] = []
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("INTENDED_MODEL_BINDING_INCOMPLETE" in error for error in errors))

    def test_theorem_face_must_record_its_exact_premises(self):
        manifest = self.conditional_gold()
        manifest["theorem_faces"][0]["premise_ids"] = []
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("THEOREM_FACE_PREMISE_MISMATCH" in error for error in errors))

    def test_target_root_cannot_hide_extra_premise_from_contract(self):
        manifest = self.conditional_gold()
        kernel_ref = manifest["kernel_evidence"]
        kernel = json.loads((self.base / kernel_ref["path"]).read_text())
        kernel["root_declarations"][0]["premise_ids"].append("hidden")
        manifest["kernel_evidence"] = self.write("kernel-hidden-premise.json", kernel)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("ROOT_PREMISE_MISMATCH" in error for error in errors))

    def test_unenumerated_structural_binder_rejected(self):
        manifest = self.conditional_gold()
        signature = "theorem ConditionalMain [Inhabited Nat] (hData : True) : True"
        target_hash = hashlib.sha256(signature.encode()).hexdigest()
        source = self.write("structural-source.txt", signature + "\n")
        lean = self.write("Structural.lean", signature + " := by trivial\n")
        contract_ref = manifest["target_contract"]
        contract = json.loads((self.base / contract_ref["path"]).read_text())
        contract.update({
            "target_signature": signature,
            "dossier_signature": signature,
            "target_signature_hash": target_hash,
            "dossier_signature_hash": target_hash,
            "source_files": [source],
        })
        manifest["target_contract"] = self.write("structural-contract.json", contract)
        kernel_ref = manifest["kernel_evidence"]
        kernel = json.loads((self.base / kernel_ref["path"]).read_text())
        kernel["target_signature_hash"] = target_hash
        kernel["root_declarations"][0].update({
            "signature": signature, "signature_hash": target_hash, "lean_file": lean,
        })
        manifest["kernel_evidence"] = self.write("structural-kernel.json", kernel)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("STRUCTURAL_CONTEXT_MISMATCH" in error for error in errors))

    def test_nested_comment_declaration_rejected(self):
        manifest = self.conditional_gold()
        disguised = self.write(
            "CommentOnly.lean",
            "/- outer /- theorem ConditionalMain (hData : True) : True := by trivial -/ -/\n",
        )
        kernel_ref = manifest["kernel_evidence"]
        kernel = json.loads((self.base / kernel_ref["path"]).read_text())
        kernel["root_declarations"][0]["lean_file"] = disguised
        manifest["kernel_evidence"] = self.write("comment-kernel.json", kernel)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("DECLARATION_MISSING" in error for error in errors))

    def test_custom_structural_class_rejected(self):
        manifest = self.conditional_gold()
        contract_ref = manifest["target_contract"]
        contract = json.loads((self.base / contract_ref["path"]).read_text())
        signature = "theorem ConditionalMain [Secret] (hData : True) : True"
        digest = hashlib.sha256(signature.encode()).hexdigest()
        source = self.write("secret-source.txt", signature + "\n")
        contract.update({
            "target_signature": signature, "dossier_signature": signature,
            "target_signature_hash": digest, "dossier_signature_hash": digest,
            "source_files": [source], "structural_binders": ["[Secret]"],
        })
        manifest["target_contract"] = self.write("secret-contract.json", contract)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("STRUCTURAL_CONTEXT_UNAUDITED" in error for error in errors))

    def test_only_named_standard_topology_data_are_trusted(self):
        self.assertIn("TopCat", TRUSTED_DATA_STRUCTURE_ALLOWLIST)
        self.assertIn("TopCat.Hom", TRUSTED_DATA_STRUCTURE_ALLOWLIST)
        self.assertNotIn("EntanglementSpace", TRUSTED_DATA_STRUCTURE_ALLOWLIST)
        self.assertNotIn("UniversalFibration", TRUSTED_DATA_STRUCTURE_ALLOWLIST)

    def test_fintype_is_ambient_structure_but_proposition_classes_are_not(self):
        # A Fintype instance supplies finite indexing data and cannot assert a
        # hidden mathematical proposition.  Proposition-only classes remain
        # outside the ambient-structure firewall.
        self.assertIn("Fintype", STRUCTURAL_CLASS_ALLOWLIST)
        self.assertNotIn("Subsingleton", STRUCTURAL_CLASS_ALLOWLIST)
        self.assertNotIn("T2Space", STRUCTURAL_CLASS_ALLOWLIST)

    def test_valid_absolute_gold_v2(self):
        manifest = self.conditional_gold()
        signature = "theorem AbsoluteMain : True"
        target_hash = hashlib.sha256(signature.encode()).hexdigest()
        source = self.write("absolute-source.txt", signature + "\n")
        lean = self.write(
            "Absolute.lean",
            "def AbsoluteTargetAdapter : True := True.intro\n" + signature + " := by trivial\n",
        )
        manifest["result_scope"] = "unconditional"
        manifest["question_status"] = "settled"
        manifest["research_value"] = "advances_question"
        manifest["assumptions"] = []
        manifest["theorem_faces"][0]["lean_decl"] = "AbsoluteMain"
        manifest["theorem_faces"][0]["source_locator"] = "absolute-source.txt:1"
        manifest["theorem_faces"][0]["premise_ids"] = []
        contract = self.write("absolute-contract.json", {
            "schema_version": 2, "result_scope": "unconditional",
            "target_signature": signature, "dossier_signature": signature,
            "target_signature_hash": target_hash, "dossier_signature_hash": target_hash,
            "source_files": [source], "original_premise_ids": [],
            "structural_binders": [],
            "data_binder_ids": [],
            "intended_model_binder_ids": [],
            "condition_premise_ids": [], "boundary_premise_ids": [],
            "theorem_face_ids": ["main"], "interface_ids": [],
        })
        kernel = self.write("absolute-kernel.json", {
            "schema_version": 2, "target_signature_hash": target_hash,
            "root_declarations": [{
                "name": "AbsoluteMain", "signature": signature,
                "signature_hash": target_hash, "proof_status": "completed", "axioms": [],
                "premise_ids": [], "theorem_face_ids": ["main"], "interface_ids": [],
                "lean_file": lean,
            }],
        })
        independence = self.write("absolute-definition.json", {
            "verdict": "verified", "target_signature_hash": target_hash,
            "checks": {
                "target_not_stored_as_field": True, "target_not_definitionally_encoded": True,
                "constructors_independent": True, "dependency_cone_reviewed": True,
            },
            "findings": {
                "target_not_stored_as_field": "There are no input fields.",
                "target_not_definitionally_encoded": "The theorem has a proof body.",
                "constructors_independent": "There are no constructors.",
                "dependency_cone_reviewed": "The dependency cone is empty.",
            },
        })
        report = self.write("absolute-audit.json", {
            "verdict": "passed", "auditor": "semantic-auditor",
            "target_signature_hash": target_hash, "question_status": "settled",
            "research_value": "advances_question",
            "checks": {key: True for key in (
                "target", "premises", "public_antecedents", "structural_context", "kernel_runtime", "interfaces",
                "theorem_faces", "definition_independence", "research_scope",
            )},
            "findings": {
                "target": "The target signature is exact.", "premises": "There are no premises.",
                "public_antecedents": "There are no antecedents.",
                "structural_context": "There are no explicit instance binders.",
                "kernel_runtime": "The runtime evidence is complete.",
                "interfaces": "There are no interfaces.", "theorem_faces": "The face is covered.",
                "definition_independence": "The proof is independent.",
                "research_scope": "The exact absolute target is settled.",
            },
        })
        manifest["target_contract"] = contract
        manifest["kernel_evidence"] = kernel
        manifest["definition_independence"]["evidence"] = independence
        manifest["independent_gold_audit"]["report"] = report
        self.attach_goal_alignment(
            manifest, target_hash=target_hash, lean=lean, adapter_decl="AbsoluteTargetAdapter",
            classification="settles_goal", directionality="iff",
        )
        self.assertEqual(audit_manifest(manifest, self.base, kernel_runtime_verified=True), [])

    def test_valid_source_boundary_gold(self):
        self.assertEqual(
            audit_manifest(
                self.conditional_gold(with_boundary=True), self.base,
                kernel_runtime_verified=True,
            ),
            [],
        )

    def test_passed_heavy_audit_can_record_gold_on_exact_completed_lite_node(self):
        manifest = self.conditional_gold()
        manifest_ref = self.write("verification-manifest.json", manifest)
        manifest_path = self.base / manifest_ref["path"]
        manifest_bytes = manifest_path.read_bytes()
        plan_data = self.base / "plan_data"
        graph = OfflinePlanGraph(plan_data)
        graph.add({
            "id": "main", "type": "Theorem", "name": "ConditionalMain",
            "content": "The exact synthetic conditional research target.",
            "dependencies": [], "hierarchy_level": 0,
            "status": "completed", "proof_status": "completed",
            "proof": "ConditionalMain is the audited target root.",
            "anchor": manifest["target_contract"] and json.loads(
                (self.base / manifest["target_contract"]["path"]).read_text()
            )["target_signature"],
            "lean_path": str((self.base / "Conditional.lean").resolve()),
            "result_scope": "conditional", "question_status": "conditional_advance",
            "research_value": "advances_question", "boundary_axiom_ids": [],
            "open_assumptions": [], "goal_id": "synthetic-research-goal",
            "goal_role": "sufficient_milestone", "directionality": "sufficient_only",
            "consumer_path": ["main", "research-answer"],
            "evidence_closure_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        })
        graph.close()
        with patch.dict(os.environ, {"PLAN_OFFLINE": "1"}), patch(
            "research_grade.verify_kernel_runtime", return_value=[],
        ):
            self.assertEqual(
                record_audited_gold(
                    manifest, self.base, manifest_path, manifest_bytes, plan_data, "main",
                ),
                [],
            )
        reopened = OfflinePlanGraph(plan_data)
        node = reopened.get("main")
        self.assertEqual(node["verification_grade"], "GOLD")
        self.assertEqual(
            node["gold_audit"]["manifest_sha256"],
            hashlib.sha256(manifest_bytes).hexdigest(),
        )
        self.assertEqual(node["gold_audit"]["root_declaration"], "ConditionalMain")
        self.assertEqual(node["gold_audit"]["schema_version"], 2)
        self.assertTrue(node["gold_audit"]["evidence_files"])

        lean_path = self.base / "Conditional.lean"
        replay = json.loads(json.dumps(node))
        replay["statement_id"] = "other"
        self.assertFalse(_gold_evidence_is_current(
            replay, lean_path, "completed", plan_data,
        ))
        replay["gold_audit"]["plan_statement_id"] = "other"
        self.assertFalse(_gold_evidence_is_current(
            replay, lean_path, "completed", plan_data,
        ))
        corrupt = json.loads(json.dumps(node))
        corrupt["gold_audit"].update({
            "schema_version": 0, "status": "failed", "auditor": "attacker",
            "target_signature_sha256": "0" * 64,
            "root_declaration": "Other", "plan_statement_id": "other",
        })
        self.assertFalse(_gold_evidence_is_current(
            corrupt, lean_path, "completed", plan_data,
        ))

        report_ref = manifest["independent_gold_audit"]["report"]
        (self.base / report_ref["path"]).write_text("tampered after recording\n", encoding="utf-8")
        changes = reconcile_status_from_lean(reopened, self.base)
        reopened.close()
        self.assertTrue(any(
            change.get("reason") == "stale_gold_audit" for change in changes
        ))
        self.assertIsNone(OfflinePlanGraph(plan_data).get("main")["verification_grade"])

    def test_gold_record_rejects_cross_node_laundering(self):
        manifest = self.conditional_gold()
        manifest_ref = self.write("verification-manifest.json", manifest)
        manifest_path = self.base / manifest_ref["path"]
        manifest_bytes = manifest_path.read_bytes()
        plan_data = self.base / "plan_data"
        graph = OfflinePlanGraph(plan_data)
        graph.add({
            "id": "other", "type": "Theorem", "name": "Other",
            "content": "A different theorem.", "dependencies": [], "hierarchy_level": 0,
            "status": "completed", "proof_status": "completed", "proof": "Other",
            "lean_path": str((self.base / "Conditional.lean").resolve()),
            "result_scope": "conditional", "question_status": "conditional_advance",
            "research_value": "advances_question", "boundary_axiom_ids": [],
            "open_assumptions": [], "goal_id": "synthetic-research-goal",
            "goal_role": "sufficient_milestone", "directionality": "sufficient_only",
            "consumer_path": ["other", "research-answer"],
            "evidence_closure_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        })
        graph.close()
        with patch.dict(os.environ, {"PLAN_OFFLINE": "1"}), patch(
            "research_grade.verify_kernel_runtime", return_value=[],
        ):
            errors = record_audited_gold(
                manifest, self.base, manifest_path, manifest_bytes, plan_data, "other",
            )
        self.assertTrue(errors)
        self.assertIsNone(OfflinePlanGraph(plan_data).get("other")["verification_grade"])

    def test_gold_record_reruns_semantic_audit(self):
        manifest = self.conditional_gold()
        manifest["axioms"] = ["Unsafe.axiom"]
        manifest_ref = self.write("verification-manifest-invalid.json", manifest)
        manifest_path = self.base / manifest_ref["path"]
        with patch.dict(os.environ, {"PLAN_OFFLINE": "1"}), patch(
            "research_grade.verify_kernel_runtime", return_value=[],
        ):
            errors = record_audited_gold(
                manifest, self.base, manifest_path, manifest_path.read_bytes(),
                self.base / "plan_data", "main",
            )
        self.assertTrue(any("AXIOMS_OPEN" in error for error in errors))

    def test_gold_record_rejects_stale_independent_audit_evidence(self):
        manifest = self.conditional_gold()
        manifest_ref = self.write("verification-manifest-stale.json", manifest)
        manifest_path = self.base / manifest_ref["path"]
        report_ref = manifest["independent_gold_audit"]["report"]
        (self.base / report_ref["path"]).write_text("tampered\n", encoding="utf-8")
        with patch.dict(os.environ, {"PLAN_OFFLINE": "1"}), patch(
            "research_grade.verify_kernel_runtime", return_value=[],
        ):
            errors = record_audited_gold(
                manifest, self.base, manifest_path, manifest_path.read_bytes(),
                self.base / "plan_data", "main",
            )
        self.assertTrue(any("EVIDENCE_STALE" in error for error in errors))

    def test_gold_record_requires_explicit_offline_authority(self):
        manifest = self.conditional_gold()
        manifest_ref = self.write("verification-manifest-online.json", manifest)
        manifest_path = self.base / manifest_ref["path"]
        with patch.dict(os.environ, {"PLAN_OFFLINE": "0"}):
            errors = record_audited_gold(
                manifest, self.base, manifest_path, manifest_path.read_bytes(),
                self.base / "plan_data", "main",
            )
        self.assertTrue(any("requires PLAN_OFFLINE=1" in error for error in errors))

    def test_source_boundary_without_cost_decision_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        del manifest["assumptions"][0]["formalization_cost"]
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("BOUNDARY_COST_GATE" in error for error in errors))

    def test_source_boundary_without_manifest_local_closure_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        del manifest["assumptions"][0]["source_closure"]
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("source_closure" in error for error in errors))

    def test_source_closure_rejects_leaf_boundary_census_mismatch(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        closure["leaves"][0]["boundary_ids"] = ["other-boundary"]
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-wrong-boundary.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("leaf boundary census" in error for error in errors))

    def test_source_closure_rejects_ref_symlink_to_non_ref_file(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        outside = self.write("outside/source-closure.json", closure)
        link = self.base / "refs" / "linked-source-closure.json"
        link.symlink_to(self.base / outside["path"])
        manifest["assumptions"][0]["source_closure"] = {
            "path": "refs/linked-source-closure.json", "sha256": outside["sha256"],
        }
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("source closure must be under" in error for error in errors))

    def test_joint_source_closure_rejects_unaudited_compatibility_prose(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        second = dict(closure["leaves"][0])
        second["id"] = "second-leaf"
        closure["leaves"].append(second)
        face = closure["faces"][0]
        face["leaf_ids"].append("second-leaf")
        face["independent_leaf_ids"] = []
        face["compatibility_edges"] = [{
            "id": "unsupported-edge",
            "leaf_ids": ["leaf-book-theorem", "second-leaf"],
            "shared_datum": "The two leaves are asserted to share compatible source data.",
            "evidence": [],
        }]
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-unaudited-edge.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("does not bind the complete face" in error for error in errors))

    def test_source_closure_rejects_coordinated_leaf_and_face_boundary_rename(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        closure["leaves"][0]["boundary_ids"] = ["other-boundary"]
        closure["faces"][0]["boundary_ids"] = ["other-boundary"]
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-coordinated-rename.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("does not bind the complete face" in error for error in errors))

    def test_source_closure_rejects_orphan_extra_face(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        extra = dict(closure["faces"][0])
        extra["id"] = "orphan-face"
        closure["faces"].append(extra)
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-orphan-face.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("face registry is not exactly" in error for error in errors))

    def test_source_closure_rejects_manifest_author_as_joint_face_auditor(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        audit_entry = closure["faces"][0]["joint_face_audits"][0]
        report_ref = audit_entry["report"]
        report = json.loads((self.base / report_ref["path"]).read_text())
        report["auditor"] = manifest["manifest_author"]
        replacement = self.write("refs/joint-face-audit-author.json", report)
        audit_entry["auditor"] = manifest["manifest_author"]
        audit_entry["report"] = replacement
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-author-auditor.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("non-independent auditor" in error for error in errors))

    def test_source_closure_rejects_joint_face_report_reuse(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        extra = dict(closure["faces"][0])
        extra["id"] = "replayed-face"
        closure["faces"].append(extra)
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-replayed-report.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("reuses a joint-face report" in error for error in errors))

    def test_source_closure_joint_face_reports_bind_complete_edge_set(self):
        manifest = self.conditional_gold(with_boundary=True)
        closure_ref = manifest["assumptions"][0]["source_closure"]
        closure = json.loads((self.base / closure_ref["path"]).read_text())
        second = dict(closure["leaves"][0])
        second["id"] = "second-leaf"
        closure["leaves"].append(second)
        face = closure["faces"][0]
        face["leaf_ids"].append("second-leaf")
        face["independent_leaf_ids"] = []
        face["compatibility_edges"] = [{
            "id": "new-edge",
            "leaf_ids": ["leaf-book-theorem", "second-leaf"],
            "shared_datum": "Both leaf instances use the exact same proposition-valued source datum.",
        }]
        manifest["assumptions"][0]["source_closure"] = self.write(
            "refs/source-closure-unbound-edge.json", closure,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("does not bind the complete face" in error for error in errors))

    def test_source_boundary_present_in_mathlib_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["mathlib_status"] = "available"
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-record-available.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("BOUNDARY_COST_GATE" in error for error in errors))

    def test_content_free_boundary_cost_evidence_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["justification"] = "x"
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-record-empty.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("BOUNDARY_COST_GATE" in error for error in errors))

    def test_fake_mathlib_checkout_is_not_an_installed_identity(self):
        self.mathlib_identity_patch.stop()
        try:
            checkout = self.base / ".lake" / "packages" / "mathlib"
            checkout.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run([
                "git", "-C", str(checkout), "remote", "add", "origin",
                "https://github.com/leanprover-community/mathlib4.git",
            ], check=True)
            (checkout / "Mathlib.lean").write_text("-- fake\n")
            subprocess.run(["git", "-C", str(checkout), "add", "Mathlib.lean"], check=True)
            subprocess.run([
                "git", "-C", str(checkout), "-c", "user.name=MerLean Test",
                "-c", "user.email=merlean@example.invalid", "commit", "-q", "-m", "fake",
            ], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True,
            ).strip()
            (self.base / "lake-manifest.json").write_text(json.dumps({"packages": [{
                "name": "mathlib", "url": "https://github.com/leanprover-community/mathlib4.git",
                "rev": revision,
            }]}))
            self.assertIsNone(research_grade._installed_mathlib_identity(self.base))
        finally:
            self.mathlib_identity_patch.start()

    def test_single_formalization_route_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["attempted_routes"] = cost_record["attempted_routes"][:1]
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-record-one-route.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("at least two" in error for error in errors))

    def test_cost_auditor_cannot_reuse_source_auditor(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost = manifest["assumptions"][0]["formalization_cost"]
        cost["independent_decision_audits"][0]["auditor"] = "sol-a"
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("invalid auditor" in error for error in errors))

    def test_formalization_routes_cannot_reuse_evidence(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["attempted_routes"][1]["evidence"] = cost_record["attempted_routes"][0]["evidence"]
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-record-duplicate-attempt.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("reuse the same evidence" in error for error in errors))

    def test_content_free_source_audits_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        source_audits = manifest["assumptions"][0]["independent_source_audits"]
        for index, audit in enumerate(source_audits):
            report_ref = audit["report"]
            report = json.loads((self.base / report_ref["path"]).read_text())
            report["findings"] = {key: "x" for key in report["findings"]}
            audit["report"] = self.write(f"boundary-source-empty-{index}.json", report)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("BOUNDARY_AUDIT_INCOMPLETE" in error for error in errors))

    def test_auditor_whitespace_alias_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_audit = manifest["assumptions"][0]["formalization_cost"]["independent_decision_audits"][0]
        cost_audit["auditor"] = "semantic-auditor "
        report_ref = cost_audit["report"]
        report = json.loads((self.base / report_ref["path"]).read_text())
        report["auditor"] = "semantic-auditor "
        cost_audit["report"] = self.write("boundary-cost-auditor-alias.json", report)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("invalid auditor" in error for error in errors))

    def test_wrong_lake_manifest_hash_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["lake_manifest_sha256"] = "0" * 64
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-wrong-manifest.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("does not bind the campaign lake manifest" in error for error in errors))

    def test_wrong_pinned_mathlib_revision_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["mathlib_revision"] = "0" * 40
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-wrong-revision.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("revision does not match" in error for error in errors))

    def test_missing_query_from_search_transcript_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["mathlib_search_transcript"] = self.write(
            "boundary-search-without-query.txt",
            "A substantive transcript that deliberately omits the declared exact query string.\n",
        )
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-missing-query.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("queries are absent" in error for error in errors))

    def test_duplicate_normalized_route_labels_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost_ref = manifest["assumptions"][0]["formalization_cost"]["record"]
        cost_record = json.loads((self.base / cost_ref["path"]).read_text())
        cost_record["attempted_routes"][1]["route"] = (
            "  " + cost_record["attempted_routes"][0]["route"].upper() + "  "
        )
        manifest["assumptions"][0]["formalization_cost"]["record"] = self.write(
            "boundary-cost-duplicate-route.json", cost_record,
        )
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("routes are not distinct" in error for error in errors))

    def test_single_cost_auditor_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        cost = manifest["assumptions"][0]["formalization_cost"]
        cost["independent_decision_audits"] = cost["independent_decision_audits"][:1]
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("requires two independent cost-decision audits" in error for error in errors))

    def test_hidden_conditional_premise_rejected(self):
        manifest = self.conditional_gold()
        manifest["assumptions"][0]["exposure"] = "record_field"
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("HIDDEN_CONDITION" in error for error in errors))

    def test_partial_source_boundary_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        manifest["assumptions"][0]["correspondence"] = "partial"
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("BOUNDARY_NOT_EXACT" in error for error in errors))

    def test_one_source_auditor_rejected(self):
        manifest = self.conditional_gold(with_boundary=True)
        manifest["assumptions"][0]["independent_source_audits"] = manifest["assumptions"][0]["independent_source_audits"][:1]
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("requires two independent" in error for error in errors))

    def test_content_free_structured_gold_audit_rejected(self):
        manifest = self.conditional_gold()
        report_ref = manifest["independent_gold_audit"]["report"]
        report = json.loads((self.base / report_ref["path"]).read_text())
        report["findings"] = {key: "" for key in report["findings"]}
        manifest["independent_gold_audit"]["report"] = self.write("gold-audit-empty.json", report)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("GOLD_AUDIT_MISSING" in error for error in errors))

    def test_content_free_definition_audit_rejected(self):
        manifest = self.conditional_gold()
        evidence_ref = manifest["definition_independence"]["evidence"]
        evidence = json.loads((self.base / evidence_ref["path"]).read_text())
        evidence.pop("findings")
        manifest["definition_independence"]["evidence"] = self.write("definition-empty.json", evidence)
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("DEFINITION_DEPENDENCE" in error for error in errors))

    def test_interface_lemma_cannot_claim_question_advance(self):
        manifest = self.conditional_gold()
        manifest["question_status"] = "interface_lemma"
        errors = audit_manifest(manifest, self.base, kernel_runtime_verified=True)
        self.assertTrue(any("RESEARCH_SCOPE_OVERCLAIM" in error for error in errors))

    def test_empty_self_attested_gold_rejected(self):
        manifest = {
            "grade": "GOLD", "target_signature_hash": "same",
            "dossier_signature_hash": "same", "axioms": [],
            "definition_independence": True, "independent_gold_audit": True,
        }
        errors = audit_manifest(manifest, self.base)
        self.assertTrue(any("SCHEMA_MISSING" in error for error in errors))
        self.assertTrue(any("EVIDENCE_MISSING" in error for error in errors))

    def test_fake_original_rejected_against_frozen_contract(self):
        manifest, kernel_data = self.valid_gold()
        manifest["assumptions"].append({
            "id": "goalItself", "name": "goalItself", "kind": "original",
            "status": "closed", "relation_to_goal": "equivalent",
            "source_locator": "invented",
        })
        kernel_data["root_declarations"][0]["premise_ids"].append("goalItself")
        manifest["kernel_evidence"] = self.write("kernel-evidence.json", kernel_data)
        errors = audit_manifest(manifest, self.base)
        self.assertTrue(any("FAKE_ORIGINAL_PREMISE" in error for error in errors))
        self.assertTrue(any("GOAL_SHAPED_PREMISE" in error for error in errors))

    def test_fake_adapter_string_rejected(self):
        manifest, _ = self.valid_gold()
        manifest["interfaces"][0]["intended_instance"] = "any-string"
        errors = audit_manifest(manifest, self.base)
        self.assertTrue(any("NO_INTENDED_INSTANCE" in error for error in errors))

    def test_stale_evidence_rejected(self):
        manifest, _ = self.valid_gold()
        (self.base / "Gold.lean").write_text("theorem Changed : True := by trivial\n")
        errors = audit_manifest(manifest, self.base)
        self.assertTrue(any("EVIDENCE_STALE" in error for error in errors))

    def test_assumed_conclusion_rejected(self):
        errors = audit_manifest(self.load("assumed_conclusion.json"), FIXTURES)
        self.assertTrue(any("GOAL_SHAPED_PREMISE" in error for error in errors))
        self.assertTrue(any("UNRESOLVED_PREMISE" in error for error in errors))

    def test_carrier_collapse_rejected(self):
        errors = audit_manifest(self.load("carrier_collapse.json"), FIXTURES)
        self.assertTrue(any("CARRIER_COLLAPSE" in error for error in errors))

    def test_toy_only_rejected(self):
        errors = audit_manifest(self.load("toy_only.json"), FIXTURES)
        self.assertTrue(any("NO_INTENDED_INSTANCE" in error for error in errors))

    def test_stage8_residual_fields_rejected(self):
        errors = audit_manifest(self.load("stage8_rigidity.json"), FIXTURES)
        for name in ("alpha", "beta", "uniquenessLow", "gamma", "hkappa"):
            self.assertTrue(any(name in error for error in errors))

    def test_circular_definition_rejected(self):
        errors = audit_manifest(self.load("circular_definition.json"), FIXTURES)
        self.assertTrue(any("DEFINITION_DEPENDENCE" in error for error in errors))

    def test_gold_variant_rejected(self):
        errors = audit_manifest(self.load("gold_variant.json"), FIXTURES)
        self.assertTrue(any("GRADE_VARIANT" in error for error in errors))

    def test_shipped_codex_auditor_uses_same_engine(self):
        script = Path(__file__).parents[1] / "scripts/audit-research-grade"
        fixture = FIXTURES / "assumed_conclusion.json"
        result = subprocess.run(
            [sys.executable, str(script), str(fixture)], capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            [
                f"- {error}" for error in
                audit_manifest(self.load("assumed_conclusion.json"), FIXTURES)
            ],
        )


if __name__ == "__main__":
    unittest.main()
