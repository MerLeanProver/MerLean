"""Dual-port regression of real sync and fail-closed receipt reconciliation.

Synthetic receipts live only in temporary stores; no Lean/semantic award is made.
"""
import hashlib
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTS = (ROOT / "src",)  # Shared verbatim by both providers; bundle parity is tested separately.


def load_port(index, source):
    name = f"gold_noop_port_{index}"
    package = types.ModuleType(name)
    package.__path__ = [str(source / "plan_store")]
    sys.modules[name] = package
    return tuple(importlib.import_module(f"{name}.{module}") for module in
                 ("offline_store", "lean_sync", "grade_policy"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return {"path": path.name, "sha256": digest(path)}


class GoldNoopSyncTests(unittest.TestCase):
    def fixture(self, index, source, root):
        store, sync, policy = load_port(index, source)
        (root / "Dep.lean").write_text("theorem dep : True := by trivial\n")
        lean = root / "Root.lean"
        signature = "theorem root : True"
        lean.write_text("import Dep\n" + signature + " := by exact dep\n")
        graph = store.OfflinePlanGraph(root / "plan")
        for sid in ("Dep", "Root"):
            graph.add({"id": sid, "name": sid, "type": "Theorem",
                       "lean_path": f"{sid}.lean", "status": "completed",
                       "proof_status": "completed"})
        sync.sync_edges_from_lean(graph, root)
        signature_hash = hashlib.sha256(signature.encode()).hexdigest()
        target_ref = write_json(root / "target.json", {
            "plan_statement_id": "Root", "target_signature": signature,
            "target_signature_hash": signature_hash})
        root_ref = {"path": "Root.lean", "sha256": digest(lean)}
        kernel_ref = write_json(root / "kernel.json", {"root_declarations": [{
            "name": "root", "signature_hash": signature_hash,
            "lean_file": root_ref}]})
        leaf_ref = write_json(root / "leaf.json", {"source_finding": "original"})
        manifest = root / "manifest.json"
        write_json(manifest, {"schema_version": 2, "grade": "GOLD",
                             "target_contract": target_ref,
                             "kernel_evidence": kernel_ref, "source": leaf_ref})
        snapshot = sorted([target_ref, kernel_ref, root_ref, leaf_ref],
                          key=lambda item: item["path"])
        snapshot_hash = hashlib.sha256(json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        receipt = {"schema_version": 2, "status": "passed",
                   "auditor": "merlean-research-grade", "auditor_version": 2,
                   "manifest_path": str(manifest), "manifest_sha256": digest(manifest),
                   "lean_file_sha256": digest(lean), "evidence_files": snapshot,
                   "evidence_set_sha256": snapshot_hash,
                   "target_signature_sha256": signature_hash,
                   "root_declaration": "root", "plan_statement_id": "Root",
                   "plan_data_path": str((root / "plan").resolve())}
        graph.update("Root", anchor=signature, evidence_closure_sha256=digest(manifest))
        graph._record_audited_gold("Root", receipt)
        self.assertTrue(sync._gold_evidence_is_current(
            graph.get("Root"), lean, "completed", graph.data_dir))
        self.addCleanup(graph.close)
        return graph, sync, policy, receipt

    def test_noop_sync_preserves_receipt_and_real_metadata_change_clears(self):
        for index, source in enumerate(PORTS):
            with self.subTest(port=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                graph, sync, _, receipt = self.fixture(index, source, root)
                sync.sync_edges_from_lean(graph, root)
                sync.sync_edges_from_lean(graph, root)
                self.assertEqual(graph.get("Root")["verification_grade"], "GOLD")
                self.assertEqual(graph.get("Root")["gold_audit"], receipt)
                self.assertEqual(sync.reconcile_status_from_lean(graph, root), [])
                # Remove an actual import/dependency, retaining a clean proof.
                (root / "Root.lean").write_text("theorem root : True := by trivial\n")
                sync.sync_edges_from_lean(graph, root)
                self.assertEqual(graph.get("Root")["dependencies"], [])
                self.assertIsNone(graph.get("Root")["gold_audit"])
                self.assertIsNone(graph.get("Root")["verification_grade"])
                graph.close()

    def test_stale_source_or_transitive_evidence_still_clears_on_reconcile(self):
        for index, source in enumerate(PORTS):
            for tamper in ("source", "leaf", "manifest", "anchor", "plan_identity"):
                with self.subTest(port=source, tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    graph, sync, _, _ = self.fixture(index, source, root)
                    if tamper == "source":
                        # Same declarations/imports/source positions: only bytes change.
                        with (root / "Root.lean").open("a") as handle:
                            handle.write("-- changed proof source digest\n")
                    elif tamper in ("leaf", "manifest"):
                        with (root / f"{tamper}.json").open("a") as handle:
                            handle.write("\n")
                    elif tamper == "anchor":
                        graph.get("Root")["anchor"] += " "
                    else:
                        graph.get("Root")["gold_audit"]["plan_data_path"] = str(root / "other")
                    sync.sync_edges_from_lean(graph, root)
                    changes = sync.reconcile_status_from_lean(graph, root)
                    self.assertTrue(any(change.get("reason") == "stale_gold_audit"
                                        for change in changes))
                    self.assertIsNone(graph.get("Root")["gold_audit"])
                    graph.close()

    def test_type_changes_and_unsupported_values_fail_closed(self):
        pairs = [(1, True), (0, False), (1, 1.0), ([1], [True]),
                 ({"rank": 1}, {"rank": True}), ({"rank": [1]}, {"rank": [1.0]}),
                 ({1: "value"}, {1: "value"}), ((1,), (1,)),
                 (float("inf"), float("inf")), (float("nan"), float("nan"))]
        for index, source in enumerate(PORTS):
            with self.subTest(port=source), tempfile.TemporaryDirectory() as temporary:
                graph, _, policy, receipt = self.fixture(index, source, Path(temporary))
                for left, right in pairs:
                    node = {"verification_grade": "GOLD", "gold_audit": receipt,
                            "intended_model_bindings": left}
                    result = policy.invalidate_gold_for_mutation(
                        node, {"intended_model_bindings": right})
                    self.assertIsNone(result["gold_audit"], (left, right))
                # Actual store update must not treat nested JSON bool/int changes as a no-op.
                graph.get("Root")["intended_model_bindings"] = [{"rank": 1}]
                graph.update("Root", intended_model_bindings=[{"rank": True}])
                self.assertIsNone(graph.get("Root")["gold_audit"])
                self.assertTrue(policy._same_json_value(
                    {"a": [1, True, None, 1.5], "b": "x"},
                    {"b": "x", "a": [1, True, None, 1.5]}))
                self.assertFalse(policy._same_json_value([1, 2], [2, 1]))
                self.assertFalse(policy._same_json_value(object(), object()))
                graph.close()

    def test_all_real_field_changes_invalidate_and_crud_stays_protected(self):
        for index, source in enumerate(PORTS):
            with self.subTest(port=source), tempfile.TemporaryDirectory() as temporary:
                graph, _, policy, receipt = self.fixture(index, source, Path(temporary))
                for field in policy.GOLD_INVALIDATING_FIELDS:
                    node = {"verification_grade": "GOLD", "gold_audit": receipt,
                            field: ["original"]}
                    same = policy.invalidate_gold_for_mutation(node, {field: ["original"]})
                    self.assertNotIn("gold_audit", same, field)
                    changed = policy.invalidate_gold_for_mutation(node, {field: ["changed"]})
                    self.assertIsNone(changed["gold_audit"], field)
                    absent = policy.invalidate_gold_for_mutation(
                        {"verification_grade": "GOLD"}, {field: None})
                    self.assertIsNone(absent["verification_grade"], field)
                for fields in ({"verification_grade": "GOLD"}, {"gold_audit": receipt}):
                    with self.assertRaises(ValueError):
                        graph.update("Root", **fields)
                    with self.assertRaises(ValueError):
                        graph.add({"id": "Forged", **fields})
                self.assertEqual(graph.get("Root")["gold_audit"], receipt)
                graph.close()


if __name__ == "__main__":
    unittest.main()
