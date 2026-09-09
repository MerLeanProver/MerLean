"""Adversarial tests for exact finite-qudit theorem binder auditing.

Mocked cases exercise rejection logic; the opt-in live case runs generated Lean
against an existing authorized project, never a mocked successful prover.
"""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import research_grade as rg


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class GCPBinderCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="merlean-gcp-binders-")
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def evidence(self, name, value):
        content = json.dumps(value, indent=2) + "\n" if isinstance(value, (dict, list)) else value
        (self.base / name).write_text(content)
        return {"path": name, "sha256": digest(content)}

    def fixture(self, *, head="DecidableEq", typ="DecidableEq α",
                source_binder="[DecidableEq α]", prop=False, mappings=None,
                pi_domains=None, context=None, prop_args=None):
        signature = f"theorem GCPBinderTest (α : Type) {source_binder} (h : True) : True"
        rows = [
            {"index": 0, "name": "α", "binderInfo": "explicit", "type": "Type",
             "structure": "", "isProp": False, "terminalHead": "", "piDomainProps": [],
             "terminalIsProp": False, "terminalPropArgs": []},
            {"index": 1, "name": "_binder1", "binderInfo": "instImplicit", "type": typ,
             "structure": "", "isProp": prop, "terminalHead": head,
             "piDomainProps": pi_domains or [], "terminalIsProp": prop,
             "terminalPropArgs": [False] if prop_args is None else prop_args},
            {"index": 2, "name": "h", "binderInfo": "explicit", "type": "True",
             "structure": "", "isProp": True, "terminalHead": "True", "piDomainProps": [],
             "terminalIsProp": True, "terminalPropArgs": []},
        ]
        mappings = [] if mappings is None else mappings
        premises = ["h"] + [m["premise_id"] for m in mappings]
        transcript = "\n".join([
            "GCPBinderTest", "'GCPBinderTest' depends on axioms: []",
            *[json.dumps({"tag": "MERLEAN_BINDER", "declaration": "GCPBinderTest", **r},
                         separators=(",", ":")) for r in rows],
            json.dumps({"tag": "MERLEAN_RESULT", "declaration": "GCPBinderTest",
                        "type": "True", "isProp": True, "isNegation": False,
                        "hasLeadingForall": False}, separators=(",", ":")), "",
        ])
        lean = self.evidence("GCPBinderTest.lean", signature + " := by exact h\n")
        plan = self.evidence("audit-plan.txt", "Generate and verify the exact finite-qudit binder census.\n")
        common = {
            "instance_premises": mappings, "instance_binder_types": [typ],
            "structural_binders": [source_binder],
        }
        if context is not None:
            common.update(elaboration_context=context,
                          elaboration_context_sha256=digest(json.dumps(context, sort_keys=True,
                                                                       separators=(",", ":"))))
        contract = {
            "schema_version": 2, "result_scope": "conditional",
            "target_signature": signature, "dossier_signature": signature,
            "target_signature_hash": digest(signature), "dossier_signature_hash": digest(signature),
            "source_files": [], "data_binder_ids": ["α"], "intended_model_binder_ids": [],
            "original_premise_ids": premises, "condition_premise_ids": [],
            "boundary_premise_ids": [], "theorem_face_ids": ["finite-data"], "interface_ids": [],
            **common,
        }
        root = {"name": "GCPBinderTest", "signature": signature, "signature_hash": digest(signature),
                "proof_status": "completed", "axioms": [], "premise_ids": premises,
                "data_binder_ids": ["α"], "theorem_face_ids": ["finite-data"],
                "interface_ids": [], "lean_file": lean, **common}
        kernel = {
            "schema_version": 2, "target_signature_hash": digest(signature),
            "runtime_verification": {"lib_dir": ".", "audit_file": plan,
                                     "lean_version": "Lean test version",
                                     "transcript_sha256": digest(transcript)},
            "root_declarations": [root],
        }
        manifest = {"schema_version": 2, "grade": "GOLD", "interfaces": []}
        return manifest, contract, kernel, transcript

    def run_fixture(self, bundle):
        manifest, contract, kernel, transcript = bundle
        manifest["target_contract"] = self.evidence("target.json", contract)
        manifest["kernel_evidence"] = self.evidence("kernel.json", kernel)
        def fake_run(args, **kwargs):
            if args[-1] == "--version":
                output = "Lean test version\n"
            elif args[:2] == ["lake", "build"]:
                output = ""
            else:
                output = transcript
            return subprocess.CompletedProcess(args, 0, output, "")
        with patch("research_grade.subprocess.run", side_effect=fake_run):
            return rg.verify_kernel_runtime(manifest, self.base)

    def assert_rejected(self, bundle):
        self.assertTrue(self.run_fixture(bundle), "malformed or unaudited binder was accepted")

    def test_standard_decidable_eq(self):
        self.assertEqual(self.run_fixture(self.fixture()), [])

    def test_standard_hilbert_structures(self):
        for head in ("NormedAddCommGroup", "InnerProductSpace"):
            typ = head + (" ℂ α" if head == "InnerProductSpace" else " α")
            with self.subTest(head=head):
                self.assertEqual(self.run_fixture(self.fixture(
                    head=head, typ=typ, source_binder=f"[{typ}]")), [])
                self.assertEqual(self.run_fixture(self.fixture(
                    head=head, typ=f"(q : α) → {typ}",
                    source_binder=f"[∀ q : α, {typ}]", pi_domains=[False])), [])

    def test_hilbert_lookalikes_and_extensions_are_rejected(self):
        for head in ("Spoof.NormedAddCommGroup", "Spoof.InnerProductSpace",
                     "CustomHilbertWithTarget", "InnerProductSpaceable"):
            with self.subTest(head=head):
                self.assert_rejected(self.fixture(head=head, typ=head + " α",
                    source_binder=f"[{head} α]"))

    def test_hilbert_heads_cannot_hide_proofs(self):
        for head in ("NormedAddCommGroup", "InnerProductSpace"):
            with self.subTest(head=head):
                self.assert_rejected(self.fixture(head=head, typ=f"True → {head} α",
                    source_binder=f"[True → {head} α]", pi_domains=[True]))
                self.assert_rejected(self.fixture(head=head, typ=f"{head} (PLift False)",
                    source_binder=f"[{head} (PLift False)]", prop_args=[True]))
                self.assert_rejected(self.fixture(head=head, typ=f"{head} α",
                    source_binder=f"[{head} α]", prop=True))

    def test_hilbert_compatibility_does_not_allow_custom_axioms(self):
        bundle = self.fixture(head="NormedAddCommGroup", typ="NormedAddCommGroup α",
            source_binder="[NormedAddCommGroup α]")
        bundle[2]["root_declarations"][0]["axioms"] = ["Forged.target"]
        self.assert_rejected(bundle)

    def test_named_standard_decidable_eq(self):
        self.assertEqual(self.run_fixture(self.fixture(source_binder="[dec : DecidableEq α]")), [])

    def test_dependent_fintype_family(self):
        self.assertEqual(self.run_fixture(self.fixture(
            head="Fintype", typ="(q : α) → Fintype α",
            source_binder="[∀ q : α, Fintype α]", pi_domains=[False])), [])

    def test_dependent_decidable_eq_family(self):
        self.assertEqual(self.run_fixture(self.fixture(
            typ="(q : α) → DecidableEq α",
            source_binder="[∀ q : α, DecidableEq α]", pi_domains=[False])), [])

    def test_namespace_spoof_is_rejected(self):
        for head in ("Spoof.DecidableEq", "Spoof.Fintype"):
            with self.subTest(head=head):
                self.assert_rejected(self.fixture(head=head, typ=head + " α",
                                                  source_binder="[" + head + " α]"))

    def test_pi_family_cannot_hide_proposition_domain(self):
        self.assert_rejected(self.fixture(head="Fintype", typ="True → Fintype α",
                                          source_binder="[True → Fintype α]", pi_domains=[True]))

    def test_unmapped_nonempty_is_rejected(self):
        self.assert_rejected(self.fixture(head="Nonempty", typ="Nonempty α",
                                          source_binder="[Nonempty α]", prop=True))

    def test_mapped_nonempty_is_public_not_structural(self):
        mapping = [{"binder_index": 1, "binder_type": "Nonempty α", "premise_id": "hNonempty"}]
        self.assertEqual(self.run_fixture(self.fixture(head="Nonempty", typ="Nonempty α",
            source_binder="[Nonempty α]", prop=True, mappings=mapping)), [])

    def test_stale_mapping_index_and_type(self):
        for index, typ in ((0, "Nonempty α"), (1, "Nonempty Bool")):
            self.assert_rejected(self.fixture(head="Nonempty", typ="Nonempty α",
                source_binder="[Nonempty α]", prop=True,
                mappings=[{"binder_index": index, "binder_type": typ, "premise_id": "hNonempty"}]))

    def test_mapping_not_on_consumer_face(self):
        bundle = self.fixture(head="Nonempty", typ="Nonempty α", source_binder="[Nonempty α]",
            prop=True, mappings=[{"binder_index": 1, "binder_type": "Nonempty α",
                                  "premise_id": "hNonempty"}])
        bundle[2]["root_declarations"][0]["premise_ids"] = ["h"]
        self.assert_rejected(bundle)

    def test_data_instance_cannot_be_mapped_as_premise(self):
        self.assert_rejected(self.fixture(mappings=[
            {"binder_index": 1, "binder_type": "DecidableEq α", "premise_id": "hFake"}]))

    def test_mapping_cannot_alias_an_actual_named_premise(self):
        bundle = self.fixture(head="Fact", typ="Fact False", source_binder="[Fact False]",
            prop=True, mappings=[{"binder_index": 1, "binder_type": "Fact False",
                                  "premise_id": "h"}])
        bundle[2]["root_declarations"][0]["premise_ids"] = ["h"]
        self.assert_rejected(bundle)

    def test_proof_bearing_prop_carrier_is_not_structural(self):
        self.assert_rejected(self.fixture(head="Inhabited", typ="Inhabited False",
            source_binder="[Inhabited False]", prop_args=[True]))

    def test_command_injection_in_context_is_rejected(self):
        self.assert_rejected(self.fixture(context={
            "universes": ["u\naxiom forged : False"], "open_namespaces": [], "open_scopes": []}))

    def test_context_hash_mismatch_is_rejected(self):
        bundle = self.fixture(context={"universes": [], "open_namespaces": [], "open_scopes": []})
        bundle[2]["root_declarations"][0]["elaboration_context_sha256"] = "0" * 64
        self.assert_rejected(bundle)


@unittest.skipUnless(os.environ.get("MERLEAN_LEAN_TEST_PROJECT"),
                     "set MERLEAN_LEAN_TEST_PROJECT to a built Mathlib project for actual Lean tests")
class GCPLiveBinderTests(unittest.TestCase):
    def test_actual_lean_classifies_structural_families_and_hidden_proofs(self):
        tree = ast.parse(inspect.getsource(rg.verify_kernel_runtime))
        support = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                       if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "audit_support" for t in node.targets))
        source = "import Mathlib\n" + support + '''
namespace MerLeanLiveRegression
universe u v
theorem safe (Q : Type u) [Fintype Q] [DecidableEq Q]
    (d : Q → Type v) [∀ q, Fintype (d q)] [∀ q, DecidableEq (d q)]
    [∀ q, Nonempty (d q)] : True := True.intro
theorem piProof (d : False → Type u) [∀ h : False, Fintype (d h)] : True := True.intro
theorem proofLift [Inhabited (PLift False)] : True := True.intro
theorem proofSubtype [Inhabited (Subtype (fun _ : Nat => False))] : True := True.intro
theorem hilbert (H : Type u) [NormedAddCommGroup H] [InnerProductSpace ℂ H] : True := True.intro
namespace Spoof
class Fintype (Q : Type u) where
  token : Nat
  hidden : False
class InnerProductSpace (Q : Type u) where
  token : Nat
  hidden : False
class NormedAddCommGroup (Q : Type u) where
  token : Nat
  hidden : False
end Spoof
theorem spoof (Q : Type u) [Spoof.Fintype Q] : True := True.intro
theorem spoofHilbert (Q : Type u) [Spoof.NormedAddCommGroup Q]
    [Spoof.InnerProductSpace Q] : True := True.intro
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``safe 7
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``piProof 2
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``proofLift 1
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``proofSubtype 1
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``spoof 2
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``hilbert 3
run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``spoofHilbert 3
end MerLeanLiveRegression
'''
        result = subprocess.run(["lake", "env", "lean", "--stdin"], input=source,
            cwd=os.environ["MERLEAN_LEAN_TEST_PROJECT"], capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()
                if line.startswith("{") and '"MERLEAN_BINDER"' in line]
        def row(decl, index):
            return next(r for r in rows if r["declaration"] == "MerLeanLiveRegression." + decl
                        and r["index"] == index)
        self.assertEqual(row("safe", 2)["terminalHead"], "DecidableEq")
        self.assertEqual(row("safe", 4)["terminalHead"], "Fintype")
        self.assertEqual(row("safe", 4)["piDomainProps"], [False])
        self.assertEqual(row("safe", 5)["terminalHead"], "DecidableEq")
        self.assertTrue(row("safe", 6)["isProp"])
        self.assertEqual(row("piProof", 1)["piDomainProps"], [True])
        self.assertIn(True, row("proofLift", 0)["terminalPropArgs"])
        self.assertIn(True, row("proofSubtype", 0)["terminalPropArgs"])
        self.assertEqual(row("spoof", 1)["terminalHead"], "MerLeanLiveRegression.Spoof.Fintype")
        self.assertEqual(row("hilbert", 1)["terminalHead"], "NormedAddCommGroup")
        self.assertEqual(row("hilbert", 2)["terminalHead"], "InnerProductSpace")
        self.assertFalse(row("hilbert", 2)["terminalIsProp"])
        self.assertEqual(row("spoofHilbert", 1)["terminalHead"],
                         "MerLeanLiveRegression.Spoof.NormedAddCommGroup")
        self.assertEqual(row("spoofHilbert", 2)["terminalHead"],
                         "MerLeanLiveRegression.Spoof.InnerProductSpace")


if __name__ == "__main__":
    unittest.main()
