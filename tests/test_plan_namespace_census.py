"""Namespace identity regressions for both plan-store distributions.

All sync mutations target an in-memory graph and temporary Lean fixtures.
"""
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTS = (ROOT / "src",)  # One maintained engine, six generated distributions.


def load_port(index):
    name = f"_namespace_census_port_{index}"
    package = types.ModuleType(name)
    package.__path__ = [str(PORTS[index] / "plan_store")]
    sys.modules[name] = package
    return importlib.import_module(name + ".lean_sync")


class MemoryGraph:
    def __init__(self, names):
        self.nodes = {n: {"name": n, "lean_path": n + ".lean", "type": "Lemma"}
                      for n in names}

    def ids(self):
        return self.nodes

    def get(self, sid):
        return self.nodes[sid]

    def update(self, sid, **fields):
        self.nodes[sid].update(fields)

    def recompute_dependents(self):
        pass


class NamespaceCensusTests(unittest.TestCase):
    def setUp(self):
        self.ports = [load_port(i) for i in range(len(PORTS))]

    def test_dotted_nested_sections_and_ends(self):
        source = """namespace A.B
section A.B
def first := 1
end A.B
namespace C
section
def second := 2
end
end C
def third := 3
end A.B
def rootName := 4
"""
        for port in self.ports:
            records = port.DependencyAnalyzer(ROOT)._extract_declaration_records(source)
            self.assertEqual([r["full_name"] for r in records],
                             ["A.B.first", "A.B.C.second", "A.B.third", "rootName"])
            self.assertEqual([r["line"] for r in records], [3, 7, 10, 12])

    def test_qualified_names_comments_strings_and_private_locations(self):
        source = """namespace A
/- outer
/- namespace Fake -/
-/
private def x := "namespace Fake"
end A
namespace B
def x := 2
private def localName := 3
def C.y := 4
def _root_.Absolute.y := 5
def «quoted.name» := 6
end B
"""
        for port in self.ports:
            records = port.DependencyAnalyzer(ROOT)._extract_declaration_records(source)
            self.assertEqual([r["full_name"] for r in records],
                             ["A.x", "B.x", "B.localName", "B.C.y",
                              "Absolute.y", "B.«quoted.name»"])
            self.assertEqual([r["line"] for r in records], [5, 8, 9, 10, 11, 12])
            self.assertEqual([r["is_private"] for r in records],
                             [True, False, True, False, False, False])
            for record in records:
                self.assertTrue(source[record["position"]:].startswith("def "))

    def test_sync_preserves_occurrences_and_true_collisions(self):
        fixtures = {
            "First": "namespace A.B\nprivate def helper := 1\ndef x := 1\nend A.B\nnamespace C\ndef x := 2\nend C\n",
            "Second": "namespace D.E\nprivate def helper := 1\ndef x := 1\nend D.E\n",
        }
        for port in self.ports:
            with tempfile.TemporaryDirectory(prefix="namespace-census-") as tmp:
                lib = Path(tmp)
                for name, source in fixtures.items():
                    (lib / (name + ".lean")).write_text(source)
                graph = MemoryGraph(fixtures)
                port.sync_edges_from_lean(graph, lib)
                self.assertEqual(port.lint_declarations(graph)["n"], 0)
                first = graph.get("First")["declarations_defined"]
                self.assertEqual([r["full_name"] for r in first],
                                 ["First._private_.A.B.helper@2", "A.B.x", "C.x"])
                self.assertEqual([r["line"] for r in first], [2, 3, 6])
                # Same public full name in a different file must still fail.
                (lib / "Second.lean").write_text("namespace A.B\ndef x := 7\nend A.B\n")
                port.sync_edges_from_lean(graph, lib)
                result = port.lint_declarations(graph)
                self.assertEqual(result["duplicates"],
                                 [{"name": "A.B.x", "nodes": ["First", "Second"]}])
                self.assertEqual(result["n"], 1)
                # Ownership checks themselves have not been relaxed.
                graph.get("Second")["lean_path"] = "First.lean"
                self.assertTrue(port.lint_declarations(graph)["path_duplicates"])
                graph.get("Second")["lean_path"] = "other/First.lean"
                self.assertTrue(port.lint_declarations(graph)["basename_duplicates"])

    def test_repeated_private_name_keeps_exact_occurrence(self):
        source = "namespace A\nprivate def x := 1\nend A\nnamespace B\nprivate def x := 2\nend B\n"
        for port in self.ports:
            with tempfile.TemporaryDirectory(prefix="namespace-census-") as tmp:
                lib = Path(tmp)
                (lib / "One.lean").write_text(source)
                graph = MemoryGraph(["One"])
                port.sync_edges_from_lean(graph, lib)
                self.assertEqual([r["full_name"] for r in graph.get("One")["declarations_defined"]],
                                 ["One._private_.A.x@2", "One._private_.B.x@5"])

    def test_bad_named_end_fails_visibly(self):
        for port in self.ports:
            with tempfile.TemporaryDirectory(prefix="namespace-census-") as tmp:
                lib = Path(tmp)
                (lib / "Bad.lean").write_text("namespace A\ndef x := 1\nend B\n")
                with self.assertRaisesRegex(ValueError, "Mismatched scope end"):
                    port.sync_edges_from_lean(MemoryGraph(["Bad"]), lib)

    def test_distribution_parity(self):
        from scripts.build_bundles import bundle_entries, PROVIDERS
        for provider in PROVIDERS:
            shipped = bundle_entries(provider, "merlean-heavy")
            for relative in ("plan_store/lean_sync.py", "plan_store/_vendor/lean_parser.py"):
                self.assertEqual((ROOT / "src" / relative).read_bytes(), shipped["src/" + relative][0])


if __name__ == "__main__":
    unittest.main()
