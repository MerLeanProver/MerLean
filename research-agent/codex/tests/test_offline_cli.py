"""End-to-end tests for the explicit PLAN_OFFLINE=1 backend.

Every runtime artifact is created below ``TemporaryDirectory``; no repository or user
plan directory is read, reset, or modified by these tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MERLEAN = ROOT / "scripts" / "merlean"


class OfflineCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="merlean-offline-test-")
        # Canonicalize macOS /var -> /private/var: reset intentionally rejects every
        # symlink component in the user-supplied destructive target.
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / "plan_data"
        self.lib = self.root / "LeanLib"
        self.lib.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            "PLAN_OFFLINE": "1",
            "OPENAI_API_KEY": "offline-test-key-must-not-be-used",
            "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
        })

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, data: Path | None = None,
                check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [str(MERLEAN)]
        if data is not False:
            command.extend(["--data", str(data or self.data)])
        command.extend(str(arg) for arg in args)
        return subprocess.run(
            command, cwd=ROOT, env=self.env, text=True,
            capture_output=True, check=check, timeout=30,
        )

    def run_json(self, *args: str, data: Path | None = None):
        result = self.run_cli(*args, data=data)
        return json.loads(result.stdout)

    def add(self, payload: dict, data: Path | None = None):
        return self.run_json("add", "--json", json.dumps(payload), data=data)

    def seed_graph(self) -> None:
        self.add({
            "id": "BaseNode", "type": "Lemma", "name": "BaseFact",
            "content": "A foundational fact about a discrete torus.",
            "lean_path": "BaseFact.lean", "dependencies": [],
            "hierarchy_level": 0,
        })
        self.add({
            "id": "GoalNode", "type": "Theorem", "name": "GoalFact",
            "content": "The exact cardinality theorem for the finite torus.",
            "lean_path": "GoalFact.lean", "dependencies": ["BaseNode"],
            "hierarchy_level": 1,
        })
        self.add({
            "id": "Note_Enumeration", "type": "Note", "name": "enumeration",
            "content": "Exhaustive enumeration found no cardinality counterexample.",
            "confidence": "high", "source": "test fixture",
            "evidence": "deterministic enumeration", "related": ["GoalNode"],
        })

    def test_crud_graph_search_dashboard_summary_and_persistence(self) -> None:
        self.seed_graph()

        listed = self.run_json("list")
        self.assertEqual([item["id"] for item in listed], [
            "BaseNode", "GoalNode", "Note_Enumeration",
        ])
        self.assertEqual(self.run_json("topo"), ["BaseNode", "GoalNode"])
        self.assertEqual(self.run_json("cone", "BaseNode"), ["BaseNode", "GoalNode"])
        self.assertEqual(self.run_json("cycles"), [])
        levels = self.run_json("levels")
        self.assertEqual([item["id"] for item in levels["0"]], ["BaseNode"])
        self.assertEqual([item["id"] for item in levels["1"]], ["GoalNode"])

        update = self.run_json(
            "update", "GoalNode", "--json", json.dumps({"proof": "by exact BaseFact"}),
        )
        self.assertEqual(update["proof"], "by exact BaseFact")
        status = self.run_json("set-status", "BaseNode", "completed")
        self.assertEqual(status["status"], "completed")
        invalid = self.run_cli("set-status", "GoalNode", "typo", check=False)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("invalid status", invalid.stderr)
        self.assertEqual(self.run_json("get", "GoalNode")["status"], "pending")
        invalid_update = self.run_cli(
            "update", "GoalNode", "--json", json.dumps({"status": "also_bad"}),
            check=False,
        )
        self.assertNotEqual(invalid_update.returncode, 0)
        invalid_add = self.run_cli(
            "add", "--json", json.dumps({"id": "BadStatus", "status": "bad"}),
            check=False,
        )
        self.assertNotEqual(invalid_add.returncode, 0)
        self.assertIn("unknown BadStatus", self.run_json("get", "BadStatus")["error"])
        self.run_json(
            "record", "GoalNode", "--role", "compile-fix", "--json",
            json.dumps({"tokens": 23, "tool_uses": 2, "duration_ms": 50}),
        )
        analytics = self.run_json("analytics")
        self.assertEqual(
            analytics["per_statement"]["GoalNode"]["subagents"][0]["tokens"], 23,
        )
        self.assertIn("1/2 done", self.run_cli("status").stdout)
        self.assertIn("tokens:       23", self.run_cli("analytics", "--plain").stdout)

        search = self.run_json("search", "finite torus cardinality", "--top-k", "2")
        self.assertEqual(search["formal"][0]["statement_id"], "GoalNode")
        self.assertIsInstance(search["formal"][0]["embed_score"], float)
        self.assertIsNone(search["formal"][0]["rerank_score"])
        informal = self.run_json(
            "search", "enumeration counterexample", "--kind", "informal", "--top-k", "1",
        )
        self.assertEqual(informal["informal"][0]["statement_id"], "Note_Enumeration")
        self.assertEqual(informal["formal"], [])

        summary = self.run_cli("summarize").stdout
        self.assertIn("## Proof architecture", summary)
        self.assertTrue((self.data / "summary.md").is_file())
        self.assertEqual(self.run_json("get", "Summary")["type"], "Summary")
        self.assertEqual(
            [item["id"] for item in self.run_json("list", "--kind", "informal")],
            ["Note_Enumeration", "Summary"],
        )

        visual = self.run_json("visualize", "--format", "svg")
        self.assertTrue(Path(visual["dot"]).is_file())
        self.assertTrue((self.data / ".merlean-offline.json").is_file())
        # A fresh process reloaded the authoritative offline store for every assertion above.

        exported = self.run_json("export-json")
        self.assertEqual(exported["n"], 2)
        materialized = json.loads((self.data / "statements.json").read_text())
        self.assertEqual([item["id"] for item in materialized["statements"]], [
            "BaseNode", "GoalNode",
        ])
        self.assertNotIn("Note_Enumeration", json.dumps(materialized))

        weighted_data = self.root / "weighted_data"
        self.add({
            "id": "ProofOnly", "name": "unrelated", "content": "",
            "proof": "rarekeyword", "dependencies": [],
        }, data=weighted_data)
        self.add({
            "id": "NameHit", "name": "rarekeyword", "content": "",
            "dependencies": [],
        }, data=weighted_data)
        weighted = self.run_json("search", "rarekeyword", data=weighted_data)
        self.assertEqual(weighted["formal"][0]["statement_id"], "NameHit")
        self.assertGreater(
            weighted["formal"][0]["embed_score"],
            weighted["formal"][1]["embed_score"],
        )

        self.run_json("delete", "Note_Enumeration")
        self.assertIn("unknown Note_Enumeration", self.run_json("get", "Note_Enumeration")["error"])

    def test_cycles_sync_reconcile_lint_and_seed_sorries(self) -> None:
        self.seed_graph()
        self.run_json(
            "update", "BaseNode", "--json", json.dumps({"dependencies": ["GoalNode"]}),
        )
        cycles = self.run_json("cycles")
        self.assertEqual(set(cycles[0]), {"BaseNode", "GoalNode"})
        self.run_json(
            "update", "BaseNode", "--json", json.dumps({"dependencies": []}),
        )

        (self.lib / "BaseFact.lean").write_text(
            "theorem BaseFact : True := by trivial\n", encoding="utf-8",
        )
        (self.lib / "GoalFact.lean").write_text(
            "import BaseFact\n\ntheorem GoalFact : True := by exact BaseFact\n",
            encoding="utf-8",
        )
        synced = self.run_json("sync-lean", str(self.lib))
        self.assertEqual(synced["synced"]["GoalNode"]["dependencies"], ["BaseNode"])
        self.assertEqual(self.run_json("get", "BaseNode")["dependents"], ["GoalNode"])

        reconciled = self.run_json("reconcile", str(self.lib))
        self.assertEqual(reconciled["n"], 2)
        self.assertEqual(self.run_json("get", "BaseNode")["status"], "completed")
        self.assertEqual(self.run_json("get", "GoalNode")["status"], "completed")

        duplicate = [{"name": "DuplicateDecl", "type": "theorem", "line": 1}]
        self.run_json(
            "update", "BaseNode", "--json", json.dumps({"declarations_defined": duplicate}),
        )
        self.run_json(
            "update", "GoalNode", "--json", json.dumps({"declarations_defined": duplicate}),
        )
        linted = self.run_json("lint")
        self.assertEqual(linted["n"], 1)
        self.assertEqual(linted["duplicates"][0]["nodes"], ["BaseNode", "GoalNode"])

        seed = self.lib / "Seed.lean"
        seed.write_text("theorem SeedResult : True := by sorry\n", encoding="utf-8")
        seeded = self.run_json(
            "seed-sorries", str(seed), "--lib-dir", str(self.lib), data=False,
        )
        seed_data = self.lib / "Seed_data"
        self.assertEqual(Path(seeded["data_dir"]), seed_data)
        self.assertEqual(seeded["node"]["statement_id"], "Prove_Seed")
        self.assertTrue((seed_data / ".merlean-offline.json").is_file())

    def test_import_bootstrap_and_safe_reset(self) -> None:
        fixture_dir = self.root / "fixture"
        fixture_dir.mkdir()
        source = fixture_dir / "statements.json"
        source.write_text(json.dumps({
            "statements": [
                {
                    "id": "Imported", "type": "Lemma", "name": "Imported",
                    "content": "imported result", "dependencies": [],
                    "hierarchy_level": 0,
                }
            ]
        }), encoding="utf-8")
        (fixture_dir / "progress.json").write_text(
            json.dumps({"completed": ["Imported"]}), encoding="utf-8",
        )
        imported_data = self.root / "imported_data"
        result = self.run_json("import-json", str(source), data=imported_data)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(self.run_json("get", "Imported", data=imported_data)["status"], "completed")

        # Removing only the offline authority demonstrates bootstrap from online-compatible views.
        (imported_data / ".merlean-offline.json").unlink()
        self.assertEqual(self.run_json("topo", data=imported_data), ["Imported"])
        self.assertTrue((imported_data / ".merlean-offline.json").is_file())

        reset = self.run_json("reset", data=imported_data)
        self.assertTrue(reset["ok"])
        self.assertFalse(imported_data.exists())

        unrelated = self.root / "unrelated_data"
        unrelated.mkdir()
        sentinel = unrelated / "do-not-delete.txt"
        sentinel.write_text("keep", encoding="utf-8")
        refused = self.run_cli("reset", data=unrelated, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("no valid MerLEAN store", refused.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

        broad = self.run_cli("reset", data=self.root, check=False)
        self.assertNotEqual(broad.returncode, 0)
        self.assertTrue(self.root.exists())

        linked = self.root / "linked_data"
        linked.mkdir()
        (linked / "statements.json").write_text(
            json.dumps({"statements": []}), encoding="utf-8",
        )
        outside = self.root / "outside.txt"
        outside.write_text("preserve", encoding="utf-8")
        (linked / "outside-link").symlink_to(outside)
        refused_link = self.run_cli("reset", data=linked, check=False)
        self.assertNotEqual(refused_link.returncode, 0)
        self.assertIn("symbolic link", refused_link.stderr)
        self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")

        disguised = self.root / "photos_data"
        disguised.mkdir()
        (disguised / "statements.json").write_text(
            json.dumps({"statements": []}), encoding="utf-8",
        )
        family = disguised / "family.jpg"
        family.write_text("preserve", encoding="utf-8")
        refused_disguised = self.run_cli("reset", data=disguised, check=False)
        self.assertNotEqual(refused_disguised.returncode, 0)
        self.assertIn("unexpected entries", refused_disguised.stderr)
        self.assertEqual(family.read_text(encoding="utf-8"), "preserve")

        empty = self.root / "empty_data"
        empty.mkdir()
        self.assertTrue(self.run_json("reset", data=empty)["ok"])
        self.assertFalse(empty.exists())

    def test_online_backend_remains_default(self) -> None:
        env = self.env.copy()
        env.pop("PLAN_OFFLINE", None)
        result = subprocess.run(
            [str(MERLEAN), "--help"], cwd=ROOT, env=env, text=True,
            capture_output=True, check=True, timeout=30,
        )
        self.assertNotIn("(offline)", result.stdout)

    def test_parallel_cli_mutations_are_serialized(self) -> None:
        concurrent_data = self.root / "concurrent_data"
        ids = [f"Concurrent{index}" for index in range(6)]
        for sid in ids:
            self.add({
                "id": sid, "name": sid, "content": sid, "dependencies": [],
            }, data=concurrent_data)

        processes = []
        for sid in ids:
            processes.append(subprocess.Popen(
                [
                    str(MERLEAN), "--data", str(concurrent_data),
                    "set-status", sid, "completed",
                ],
                cwd=ROOT, env=self.env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ))
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, msg=f"{stdout}\n{stderr}")

        nodes = self.run_json("list", data=concurrent_data)
        self.assertEqual({node["id"] for node in nodes}, set(ids))
        self.assertTrue(all(node["status"] == "completed" for node in nodes))


if __name__ == "__main__":
    unittest.main()
