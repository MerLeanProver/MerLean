"""Deterministic synthesis contracts, not an oracle for mathematical novelty."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex.versioning import sha256_file  # noqa: E402


class SynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        from paper_writing_codex import synthesis

        self.engine = synthesis
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "notes.md"
        self.source.write_text(
            "# Synthetic test notes\n\n"
            "Lemma L: if x is a nonnegative integer, x+0=x, by the identity law.\n"
            "Theorem T: if x is a nonnegative integer, x+0+0=x, using L twice.\n"
            "These toy claims test evidence handling, not publication merit.\n",
            encoding="utf-8",
        )
        self.work = self.root / "synthesis"
        self.state_path = self.work / "state.json"

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    @staticmethod
    def read_json(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def tree_bytes(directory: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()
        }

    def cli(self, *arguments: object, expected: int = 0, no_tools: bool = False):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        if no_tools:
            environment["PATH"] = ""
        result = subprocess.run(
            [sys.executable, "-m", "paper_writing_codex.cli", *map(str, arguments)],
            cwd=self.root, env=environment, text=True, capture_output=True,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        if expected == 0:
            return json.loads(result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def initialize(self):
        return self.engine.init_synthesize([self.source], self.work)

    def inventory_and_candidates(self, *, no_candidates: bool = False) -> None:
        inventory = self.read_json(self.work / "input-inventory.json")
        source_id = next(
            entry["source_id"] for entry in inventory["sources"]
            if Path(entry["path"]) == self.source
        )
        common = {
            "hypotheses": ["x is a nonnegative integer"],
            "source_refs": [{"source_id": source_id, "location": "lines 3-4"}],
            "proof_status": "proof_available",
            "evidence": [{"path": str(self.source), "sha256": sha256_file(self.source)}],
            "unresolved_assumptions": [],
        }
        self.claims = [
            {**copy.deepcopy(common), "id": "L", "statement": "x+0=x", "dependencies": []},
            {
                **copy.deepcopy(common), "id": "T", "statement": "x+0+0=x",
                "dependencies": ["L"],
                "grade_metadata": {
                    "grade": "SILVER", "conditional": True,
                    "conditions": ["x is a nonnegative integer"],
                    "note": "Synthetic original record; synthesis does not award a grade.",
                },
            },
        ]
        self.write_json(self.work / "claim-ledger.json", {
            "schema_version": 1, "authored_by": "coordinator", "claims": self.claims,
        })
        (self.work / "claim-ledger.md").write_text(
            "# Claims\n\nBoth toy claims retain their nonnegative-integer hypothesis.\n",
            encoding="utf-8",
        )
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pass", ["Source claims inspected."])
        candidate = {
            "id": "identity-story", "title": "Synthetic identity story",
            "research_question": "How does the supplied identity lemma imply the two-step identity?",
            "contribution": "The conditional theorem T and its exact dependency L.",
            "significance": "A test-only illustration of scope-preserving handoff.",
            "main_claim_ids": ["T"], "supporting_claim_ids": ["L"],
            "limitations": ["Toy fixture: this is not a claim of research significance or novelty."],
            "excluded_material": [], "proposed_extensions": [],
        }
        self.write_json(self.work / "candidate-prospectuses.json", {
            "schema_version": 1, "authored_by": "coordinator",
            "candidates": [] if no_candidates else [candidate],
            "rationale": (
                "Only standard identities were found; there is no compelling paper."
                if no_candidates else "One coherent candidate suffices; do not pad the count."
            ),
        })
        (self.work / "candidate-prospectuses.md").write_text(
            "# Candidates\n\nSynthetic candidate selection, with no publication claim.\n",
            encoding="utf-8",
        )
        self.engine.mark_synthesis_gate(self.state_path, "candidates", "pass", ["Candidate comparison recorded."])

    def approval(self, *, via_cli: bool = False) -> dict:
        digest = self.engine.candidate_digest(self.state_path, "identity-story")
        evidence = self.root / "author-approval.json"
        self.write_json(evidence, {
            "candidate_id": "identity-story", "candidate_digest": digest,
            "input_revision": self.read_json(self.state_path)["input_revision"],
            "author": "test-author", "approved_at": "2026-09-18T00:00:00Z",
            "decision": "approve",
            "message": "I approve this exact synthetic candidate for focused assessment only.",
        })
        if via_cli:
            return self.cli("select-synthesis", "--state", self.state_path,
                            "--candidate", "identity-story", "--approval-evidence", evidence)
        return self.engine.select_synthesis(self.state_path, "identity-story", evidence)

    def record_reviews(self, *, verdict: str = "pass", novelty_code: str = "CLEAR") -> None:
        digest = self.engine.candidate_digest(self.state_path, "identity-story")
        references = self.work / "refs"
        references.mkdir(exist_ok=True)
        primary = references / "synthetic-primary.txt"
        primary.write_text(
            "Synthetic primary-source fixture. This is not an actual published article.\n"
            "For the test domain, addition has identity zero.\n", encoding="utf-8",
        )
        evidence = references / "source-comparison.md"
        evidence.write_text(
            "Synthetic comparison only: fixture scope was checked, without a global novelty claim.\n",
            encoding="utf-8",
        )
        bibliography = references / "synthetic.bib"
        bibliography.write_text(
            "@article{synthetic, author={Fixture Author}, title={Synthetic fixture}, "
            "journal={Test records}, year={2026}}\n", encoding="utf-8",
        )
        self.write_json(self.work / "references-registry.json", {
            "schema_version": 1,
            "references": [{
                "citation_key": "synthetic", "status": "verified", "source_type": "article",
                "title": "Synthetic fixture", "authors": "Fixture Author",
                "public_url": "https://example.invalid/synthetic-test-only",
                "source_file": str(primary), "source_sha256": sha256_file(primary),
                "evidence_file": str(evidence), "evidence_sha256": sha256_file(evidence),
                "evidence_page": "fixture paragraph 2", "claim": "The test-domain identity law.",
                "bibtex_snapshot": str(bibliography), "bibtex_sha256": sha256_file(bibliography),
                "bibliography_path": str(bibliography), "verification_date": "2026-09-18",
            }],
        })
        reviews = []
        for kind, reviewer in (("correctness", "correctness-reviewer"), ("novelty", "literature-reviewer")):
            review_file = self.work / f"{kind}-review.md"
            review_file.write_text(
                f"# Synthetic {kind} review\n\nScope and supplied evidence were examined by {reviewer}.\n",
                encoding="utf-8",
            )
            entry = {
                "kind": kind, "reviewer": reviewer, "candidate_digest": digest,
                "input_revision": self.read_json(self.state_path)["input_revision"],
                "verdict": verdict, "findings": "Synthetic evidence is consistent within the recorded scope.",
                "evidence": [{"path": str(review_file), "sha256": sha256_file(review_file)}],
            }
            if kind == "correctness":
                entry["covered_claim_ids"] = ["L", "T"]
            else:
                entry.update({
                    "novelty_code": novelty_code,
                    "search_scope": "Synthetic fixture corpus only; no actual novelty conclusion.",
                    "searched_at": "2026-09-18", "reference_ids": ["synthetic"],
                    "references_sha256": self.engine.references_digest(self.state_path, ["synthetic"]),
                })
            reviews.append(entry)
        self.write_json(self.work / "reviews.json", {"schema_version": 1, "reviews": reviews})

    def decision(self, outcome: str = "ready_to_draft", *, no_selection: bool = False) -> None:
        self.write_json(self.work / "decision.json", {
            "schema_version": 1, "outcome": outcome,
            "rationale": "The documented evidence supports this workflow decision, not acceptance by a journal.",
            "limitations": ["Synthetic test evidence only."],
            "next_steps": ["Await a separate author request before drafting or further research."],
            "candidate_digest": None if no_selection else self.engine.candidate_digest(
                self.state_path, "identity-story"),
            "not_applicable": {
                "selection": "No candidate warrants author selection.",
                "assessment": "No selected contribution exists to assess.",
            } if no_selection else {},
        })
        (self.work / "decision.md").write_text(
            "# Decision\n\nThe synthetic fixture decision does not launch any subsequent work.\n",
            encoding="utf-8",
        )

    def ready(self) -> dict:
        self.initialize()
        self.inventory_and_candidates()
        self.approval()
        self.record_reviews()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Both reviews recorded."])
        self.decision()
        self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Evidence-backed handoff."])
        return self.read_json(self.state_path)

    def add_scope_reviews(self, state: dict, row: dict, inventory: dict,
                          auditors: tuple[str, ...] = ("equivalence-one", "equivalence-two")) -> None:
        from paper_writing_codex.synthesis_bridge import manuscript_digest

        unit = next(unit for unit in inventory["units"] if unit.get("label") == row["candidate_label"])
        row["normalized_sha256"] = unit["normalized_sha256"]
        for auditor in auditors:
            evidence = Path(state["work_dir"]) / f"{auditor}.md"
            evidence.write_text("Synthetic scope review includes every hypothesis and macro meaning.\n",
                                encoding="utf-8")
            row["source_equivalence_audits"].append({
                "auditor": auditor, "verdict": "PASS", "findings": "Source and TeX have the same complete scope.",
                "candidate_digest": row["synthesis_candidate_digest"],
                "source_statement_sha256": row["source_statement_sha256"],
                "candidate_normalized_sha256": unit["normalized_sha256"],
                "manuscript_sha256": manuscript_digest(inventory),
                "evidence_file": str(evidence), "evidence_sha256": sha256_file(evidence),
            })

    def test_cli_initialization_accepts_multiple_notes_without_toolchains(self) -> None:
        second = self.root / "second.md"
        second.write_text("# A second supplied note\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in (self.source, second)}
        state = self.cli("init-synthesize", "--source", self.source, "--source", second,
                         "--work-dir", self.work, no_tools=True)
        self.assertEqual("synthesize", state["mode"])
        self.assertTrue(self.state_path.is_file())
        self.assertFalse(state.get("output"))
        self.assertFalse((self.work / "02-framework.tex").exists())
        self.assertFalse((self.root / "paper.tex").exists())
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        inventory = self.read_json(self.work / "input-inventory.json")
        self.assertEqual({str(path) for path in before}, set(inventory["explicit_sources"]))
        for entry in inventory["sources"]:
            snapshot = self.work / entry["snapshot"]
            self.assertEqual(entry["sha256"], sha256_file(snapshot))

    def test_local_tex_inputs_and_explicit_markdown_evidence_are_snapshotted(self) -> None:
        tex = self.root / "main.tex"
        included = self.root / "part.tex"
        included.write_text("A local lemma.\n", encoding="utf-8")
        tex.write_text("\\input{part}\n", encoding="utf-8")
        lean = self.root / "proof.lean"
        lean.write_text("theorem identity_test (x : Nat) : x = x := rfl\n", encoding="utf-8")
        table = self.root / "table.csv"
        table.write_text("n,value\n1,1\n", encoding="utf-8")
        self.source.write_text("[Proof](proof.lean) and [data](table.csv).\n", encoding="utf-8")
        self.engine.init_synthesize([self.source, tex], self.work)
        inventory = self.read_json(self.work / "input-inventory.json")
        paths = {Path(entry["path"]) for entry in inventory["sources"]}
        self.assertTrue({tex, included, self.source, lean, table}.issubset(paths))

    def test_nested_tex_inputs_resolve_against_master_document_directory(self) -> None:
        sections = self.root / "sections"
        sections.mkdir()
        main = self.root / "main.tex"
        part = sections / "part.tex"
        nested = sections / "nested.tex"
        main.write_text("\\input{sections/part}\n", encoding="utf-8")
        part.write_text("\\input{sections/nested}\n", encoding="utf-8")
        nested.write_text("Nested theorem evidence.\n", encoding="utf-8")
        self.engine.init_synthesize([main], self.work)
        entries = self.read_json(self.work / "input-inventory.json")["sources"]
        self.assertEqual({main, part, nested}, {Path(entry["path"]) for entry in entries})
        self.assertFalse(any(entry["missing"] for entry in entries))

    def test_local_package_class_and_nested_macro_sources_are_snapshotted(self) -> None:
        styles = self.root / "styles"
        styles.mkdir()
        main = self.root / "notes.tex"
        main.write_text("\\documentclass{localpaper}\n\\usepackage[option]{styles/localmath}\n", encoding="utf-8")
        sources = {
            self.root / "localpaper.cls": "\\LoadClass[11pt]{article}\n\\RequirePackage{base}\n",
            styles / "localmath.sty": "\\RequirePackageWithOptions{base}\n\\input{macros.def}\n",
            self.root / "base.sty": "\\RequirePackage{styles/localmath}\n",
            self.root / "macros.def": "\\input{more}\n",
            self.root / "more.tex": "\\newcommand{\\domain}{\\mathbb{N}}\n",
        }
        for path, content in sources.items():
            path.write_text(content, encoding="utf-8")
        self.engine.init_synthesize([main], self.work)
        entries = self.read_json(self.work / "input-inventory.json")["sources"]
        self.assertEqual({main, *sources}, {Path(entry["path"]) for entry in entries})
        self.assertFalse(any(entry["missing"] for entry in entries), "System article.cls is not a missing local dependency.")
        self.assertTrue(self.engine.audit_synthesis(self.state_path)["pass"])
        for path, content in sources.items():
            with self.subTest(source=path.name):
                path.write_text(content + "\\def\\domain{\\mathbb{R}}\n", encoding="utf-8")
                self.assertFalse(self.engine.audit_synthesis(self.state_path)["pass"])
                path.write_text(content, encoding="utf-8")

    def test_shared_include_is_explored_in_each_explicit_master_context(self) -> None:
        shared = self.root / "shared.tex"
        shared.write_text("\\input{macros}\n", encoding="utf-8")
        masters, macros = [], []
        for name in ("first", "second"):
            directory = self.root / name
            directory.mkdir()
            master = directory / "notes.tex"
            master.write_text("\\input{" + shared.as_posix() + "}\n", encoding="utf-8")
            macro = directory / "macros.tex"
            macro.write_text("\\newcommand{\\domain}{" + name + "}\n", encoding="utf-8")
            masters.append(master)
            macros.append(macro)
        self.engine.init_synthesize(masters, self.work)
        entries = self.read_json(self.work / "input-inventory.json")["sources"]
        self.assertEqual({shared, *masters, *macros}, {Path(entry["path"]) for entry in entries})
        self.assertEqual(1, sum(Path(entry["path"]) == shared for entry in entries))
        self.assertFalse(any(entry["missing"] for entry in entries))
        macros[1].write_text("\\newcommand{\\domain}{changed}\n", encoding="utf-8")
        self.assertFalse(self.engine.audit_synthesis(self.state_path)["pass"])

    def test_new_local_package_or_master_input_shadow_invalidates_intake(self) -> None:
        sections = self.root / "sections"
        sections.mkdir()
        main = self.root / "notes.tex"
        main.write_text("\\usepackage{laterlocal}\n\\input{sections/part}\n", encoding="utf-8")
        (sections / "part.tex").write_text("\\input{macros}\n", encoding="utf-8")
        (sections / "macros.tex").write_text("\\newcommand{\\domain}{\\mathbb{N}}\n", encoding="utf-8")
        self.engine.init_synthesize([main], self.work)
        self.assertTrue(self.engine.audit_synthesis(self.state_path)["pass"])
        for name in ("laterlocal.sty", "macros.tex"):
            with self.subTest(shadow=name):
                shadow = self.root / name
                shadow.write_text("\\newcommand{\\domain}{\\mathbb{R}}\n", encoding="utf-8")
                report = self.engine.audit_synthesis(self.state_path)
                self.assertFalse(report["pass"])
                self.assertIn("dependency closure changed", " ".join(report["errors"]))
                shadow.unlink()
                self.assertTrue(self.engine.audit_synthesis(self.state_path)["pass"])

    def test_symlink_source_is_rejected_before_path_resolution(self) -> None:
        linked = self.root / "linked.md"
        try:
            linked.symlink_to(self.source)
        except OSError as error:
            self.skipTest(f"File symlinks unavailable: {error}")
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            self.engine.init_synthesize([linked], self.work)
        self.assertEqual(before, self.source.read_bytes())
        self.assertFalse(self.work.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction guard")
    def test_junction_source_component_is_rejected_before_path_resolution(self) -> None:
        actual = self.root / "actual"
        actual.mkdir()
        note = actual / "note.md"
        note.write_text("Synthetic source behind a junction.\n", encoding="utf-8")
        linked = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(actual)],
                                text=True, capture_output=True)
        if result.returncode:
            self.skipTest(f"Directory junction unavailable: {result.stderr}")
        self.addCleanup(lambda: os.rmdir(linked) if linked.exists() else None)
        before = note.read_bytes()
        with self.assertRaises(ValueError):
            self.engine.init_synthesize([linked / "note.md"], self.work)
        self.assertEqual(before, note.read_bytes())
        self.assertFalse(self.work.exists())

    def test_work_directory_cannot_overwrite_existing_run(self) -> None:
        self.initialize()
        before = self.tree_bytes(self.work)
        with self.assertRaises((FileExistsError, ValueError)):
            self.initialize()
        self.assertEqual(before, self.tree_bytes(self.work))

    def test_audit_and_resume_do_not_mutate_or_compile(self) -> None:
        self.initialize()
        before = self.tree_bytes(self.work)
        with patch("paper_writing_codex.cli._compile_tex", side_effect=AssertionError("No synthesis compile")):
            self.engine.audit_synthesis(self.state_path)
            result = self.engine.resume_synthesis(self.state_path)
        self.assertEqual("inventory", result["next_gate"])
        self.assertEqual(before, self.tree_bytes(self.work))
        self.cli("resume", "--state", self.state_path, no_tools=True)
        self.assertEqual(before, self.tree_bytes(self.work))

    def test_gate_order_and_direct_selection_bypass_are_rejected(self) -> None:
        self.initialize()
        with self.assertRaises(ValueError):
            self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Skipped author."])
        self.inventory_and_candidates()
        with self.assertRaises(ValueError):
            self.engine.mark_synthesis_gate(self.state_path, "selection", "pass", ["An agent approved itself."])
        self.cli("gate", "--state", self.state_path, "--name", "selection", "--status", "pass",
                 "--evidence", "Not an author approval", expected=2)

    def test_select_cli_binds_author_evidence_and_revision(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        self.approval(via_cli=True)
        selected = self.read_json(self.work / "selected-contribution.json")
        self.assertIn(self.engine.candidate_digest(self.state_path, "identity-story"), json.dumps(selected))
        self.assertEqual("pass", self.read_json(self.state_path)["gates"]["selection"]["status"])
        self.assertEqual("assessment", self.engine.resume_synthesis(self.state_path)["next_gate"])

    def test_stale_approval_digest_is_rejected(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        self.approval()
        approval = self.root / "author-approval.json"
        record = self.read_json(approval)
        record["candidate_digest"] = "0" * 64
        self.write_json(approval, record)
        self.cli("select-synthesis", "--state", self.state_path, "--candidate", "identity-story",
                 "--approval-evidence", approval, expected=2)

    def test_no_approval_means_no_readiness_or_drafting(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        self.record_reviews()
        self.decision()
        with self.assertRaises(ValueError):
            self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["No approval exists."])
        output = self.root / "paper.tex"
        self.cli("init-compose", "--output", output, "--from-synthesis", self.state_path, expected=2)
        self.assertFalse(output.exists())

    def test_source_drift_blocks_read_only_commands_and_preserves_state(self) -> None:
        self.ready()
        before = self.tree_bytes(self.work)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "Changed source.\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.engine.resume_synthesis(self.state_path)
        self.assertFalse(self.engine.audit_synthesis(self.state_path)["pass"])
        self.cli("resume", "--state", self.state_path, expected=2)
        self.assertEqual(before, self.tree_bytes(self.work))

    def test_changed_selected_hypothesis_dependency_or_grade_invalidates_selection(self) -> None:
        self.ready()
        path = self.work / "claim-ledger.json"
        original = self.read_json(path)
        for mutation in ("hypotheses", "dependencies", "grade_metadata"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(original)
                target = next(claim for claim in changed["claims"] if claim["id"] == "T")
                target[mutation] = {"grade": "GOLD"} if mutation == "grade_metadata" else []
                self.write_json(path, changed)
                self.assertFalse(self.engine.audit_synthesis(self.state_path)["pass"])
                with self.assertRaises(ValueError):
                    self.engine.prepare_handoff(self.state_path)
                self.write_json(path, original)

    def test_refresh_preserves_history_and_requires_new_selection(self) -> None:
        self.ready()
        old = self.read_json(self.state_path)
        snapshot_bytes = {
            entry["snapshot"]: (self.work / entry["snapshot"]).read_bytes()
            for entry in self.read_json(self.work / "input-inventory.json")["sources"]
        }
        self.source.write_text(self.source.read_text(encoding="utf-8") + "New revision.\n", encoding="utf-8")
        refreshed = self.cli("refresh-synthesis", "--state", self.state_path)
        self.assertEqual(old["input_revision"] + 1, refreshed["input_revision"])
        self.assertEqual("inventory", self.engine.resume_synthesis(self.state_path)["next_gate"])
        self.assertNotEqual("pass", refreshed["gates"]["selection"]["status"])
        for relative, expected in snapshot_bytes.items():
            self.assertEqual(expected, (self.work / relative).read_bytes())
        archived = [path for path in self.work.rglob("decision.json")
                    if path != self.work / "decision.json"]
        self.assertTrue(archived, "The old decision must survive refresh in revision history.")

    def test_refresh_refuses_run_hardlink_to_source_without_writing_either(self) -> None:
        self.initialize()
        ledger = self.work / "claim-ledger.json"
        ledger.unlink()
        try:
            os.link(self.source, ledger)
        except OSError as error:
            self.skipTest(f"Hardlinks unavailable: {error}")
        before = self.tree_bytes(self.work)
        source_bytes = self.source.read_bytes()
        with self.assertRaises(ValueError):
            self.engine.refresh_synthesis(self.state_path)
        self.assertEqual(source_bytes, self.source.read_bytes())
        self.assertEqual(before, self.tree_bytes(self.work))

    def test_refresh_refuses_missing_or_corrupt_old_snapshot(self) -> None:
        self.initialize()
        entry = self.read_json(self.work / "input-inventory.json")["sources"][0]
        snapshot = self.work / entry["snapshot"]
        original = snapshot.read_bytes()
        for corruption in ("missing", "changed"):
            with self.subTest(corruption=corruption):
                if corruption == "missing":
                    snapshot.unlink()
                else:
                    snapshot.write_bytes(original + b"Corrupted snapshot")
                before = self.tree_bytes(self.work)
                with self.assertRaises(ValueError):
                    self.engine.refresh_synthesis(self.state_path)
                self.assertEqual(before, self.tree_bytes(self.work))
                snapshot.write_bytes(original)

    def test_no_story_can_complete_without_false_selection_or_assessment_pass(self) -> None:
        self.initialize()
        self.inventory_and_candidates(no_candidates=True)
        self.decision("no_compelling_paper", no_selection=True)
        self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["No supported candidate."])
        self.assertTrue(self.engine.audit_synthesis(self.state_path, require_all_gates=True)["pass"])
        self.assertEqual("complete", self.engine.resume_synthesis(self.state_path)["status"])
        state = self.read_json(self.state_path)
        for gate in ("selection", "assessment"):
            self.assertNotEqual("pass", state["gates"][gate]["status"])
        self.assertFalse(list(self.work.glob("*.tex")))

    def test_negative_assessment_can_complete_but_cannot_draft(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        self.approval()
        self.record_reviews(verdict="unresolved", novelty_code="UNRESOLVED")
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Uncertainty documented."])
        self.decision("focused_research_needed")
        self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Missing step identified."])
        self.assertTrue(self.engine.audit_synthesis(self.state_path, require_all_gates=True)["pass"])
        with self.assertRaises(ValueError):
            self.engine.prepare_handoff(self.state_path)
        self.assertEqual("complete", self.engine.resume_synthesis(self.state_path)["status"])

    def test_ready_requires_full_independent_scope_review(self) -> None:
        self.ready()
        path = self.work / "reviews.json"
        original = self.read_json(path)
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pending", ["Reopen before review edits."])
        for mutation in ("coordinator_review", "same_reviewer", "missing_dependency", "missing_novelty"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(original)
                if mutation == "coordinator_review":
                    changed["reviews"][0]["reviewer"] = "coordinator"
                elif mutation == "same_reviewer":
                    changed["reviews"][1]["reviewer"] = changed["reviews"][0]["reviewer"]
                elif mutation == "missing_dependency":
                    changed["reviews"][0]["covered_claim_ids"] = ["T"]
                else:
                    changed["reviews"] = changed["reviews"][:1]
                self.write_json(path, changed)
                with self.assertRaisesRegex(ValueError, "independently|complete proof dependency|one correctness"):
                    self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Invalid review."])
                self.write_json(path, original)

    def test_ready_rejects_unresolved_novelty(self) -> None:
        self.ready()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pending", ["Reopen bounded novelty review."])
        path = self.work / "reviews.json"
        reviews = self.read_json(path)
        reviews["reviews"][1]["novelty_code"] = "UNRESOLVED"
        self.write_json(path, reviews)
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Uncertainty recorded."])
        self.decision()
        with self.assertRaisesRegex(ValueError, "source-verified novelty"):
            self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Unsupported readiness."])
        with self.assertRaises(ValueError):
            self.engine.prepare_handoff(self.state_path)

    def test_direct_repass_of_changed_assessment_is_rejected_until_reopened(self) -> None:
        self.ready()
        path = self.work / "reviews.json"
        original = self.read_json(path)
        changed = copy.deepcopy(original)
        changed["reviews"][0]["findings"] += " A different report was substituted."
        self.write_json(path, changed)
        state_before = self.state_path.read_bytes()
        with self.assertRaises(ValueError):
            self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Attempted receipt laundering."])
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.write_json(path, original)
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pending", ["Explicitly reopen before revision."])
        self.write_json(path, changed)
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Revised review recorded."])
        self.assertEqual("pending", self.read_json(self.state_path)["gates"]["decision"]["status"])

    def test_changed_reference_even_after_reopen_requires_new_novelty_binding(self) -> None:
        self.ready()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pending", ["Reopen source comparison."])
        primary = self.work / "refs" / "synthetic-primary.txt"
        primary.write_bytes(primary.read_bytes() + b"\nChanged primary-source claim.\n")
        path = self.work / "references-registry.json"
        registry = self.read_json(path)
        registry["references"][0]["source_sha256"] = sha256_file(primary)
        self.write_json(path, registry)
        with self.assertRaisesRegex(ValueError, "reference|novelty"):
            self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Old comparison is stale."])
        reviews = self.read_json(self.work / "reviews.json")
        novelty = next(review for review in reviews["reviews"] if review["kind"] == "novelty")
        self.assertNotEqual(novelty["references_sha256"], self.engine.references_digest(self.state_path, ["synthetic"]))

    def test_readiness_rejects_unproven_dependencies_hidden_assumptions_and_unverified_formal_claims(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        ledger = self.work / "claim-ledger.json"
        original = self.read_json(ledger)
        mutations = (
            {"proof_status": "conjecture"}, {"proof_status": "numerical"},
            {"unresolved_assumptions": ["An additional unproved regularity condition is needed."]},
            {"proof_status": "formally_verified"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.engine.mark_synthesis_gate(self.state_path, "inventory", "pending", ["Revise toy evidence."])
                record = copy.deepcopy(original)
                record["claims"][0].update(mutation)
                self.write_json(ledger, record)
                self.engine.mark_synthesis_gate(self.state_path, "inventory", "pass", ["Evidence status recorded."])
                self.engine.mark_synthesis_gate(self.state_path, "candidates", "pass", ["Candidate is exploratory."])
                self.approval()
                self.record_reviews()
                self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Supplied reviewer records."])
                self.decision()
                with self.assertRaises(ValueError):
                    self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Unsupported readiness."])

    def test_unresolved_local_source_dependency_blocks_readiness(self) -> None:
        self.source.write_text(self.source.read_text(encoding="utf-8") + "[Missing proof](missing.lean)\n",
                               encoding="utf-8")
        self.initialize()
        self.inventory_and_candidates()
        self.approval()
        self.record_reviews()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Reviews supplied."])
        self.decision()
        with self.assertRaises(ValueError):
            self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Unresolved evidence."])

    def test_ready_rejects_changed_review_and_reference_bytes(self) -> None:
        self.ready()
        for path in (self.work / "correctness-review.md", self.work / "refs" / "synthetic-primary.txt"):
            with self.subTest(path=path.name):
                before = path.read_bytes()
                path.write_bytes(before + b"\nAltered evidence")
                self.assertFalse(self.engine.audit_synthesis(self.state_path)["pass"])
                with self.assertRaises(ValueError):
                    self.engine.prepare_handoff(self.state_path)
                path.write_bytes(before)

    def test_missing_and_circular_dependencies_block_candidate_gate(self) -> None:
        self.initialize()
        self.inventory_and_candidates()
        path = self.work / "claim-ledger.json"
        original = self.read_json(path)
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pending", ["Inspect dependency edits."])
        for dependencies in (["MISSING"], ["T"]):
            with self.subTest(dependencies=dependencies):
                changed = copy.deepcopy(original)
                changed["claims"][0]["dependencies"] = dependencies
                self.write_json(path, changed)
                with self.assertRaisesRegex(ValueError, "missing claim dependency|circular proof dependency"):
                    self.engine.candidate_digest(self.state_path, "identity-story")
                self.write_json(path, original)

    def test_ready_handoff_preserves_scope_and_grade_without_autopassing_compose(self) -> None:
        self.ready()
        before = self.tree_bytes(self.work)
        handoff = self.engine.prepare_handoff(self.state_path)
        self.engine.verify_handoff(handoff)
        self.assertEqual(before, self.tree_bytes(self.work))
        encoded = json.dumps(handoff)
        self.assertIn("SILVER", encoded)
        self.assertIn("x is a nonnegative integer", encoded)
        self.assertIn("proof_available", encoded)
        output = self.root / "paper.tex"
        compose_work = self.root / "compose"
        state = self.cli("init-compose", "--output", output, "--work-dir", compose_work,
                         "--from-synthesis", self.state_path)
        self.assertEqual("compose", state["mode"])
        self.assertTrue(output.is_file())
        for gate, entry in state["gates"].items():
            if gate != "preflight":
                self.assertNotEqual("pass", entry["status"], gate)
        main = self.read_json(compose_work / "03-main-results.json")["main_results"]
        self.assertEqual(1, len(main))
        self.assertEqual(before, self.tree_bytes(self.work))

    def test_handoff_rejects_changed_claim_contents(self) -> None:
        self.ready()
        handoff = self.engine.prepare_handoff(self.state_path)
        changed = copy.deepcopy(handoff)
        changed["claims"][0]["hypotheses"] = []
        with self.assertRaises(ValueError):
            self.engine.verify_handoff(changed)

    def test_import_receipt_and_origin_source_remain_binding(self) -> None:
        from paper_writing_codex.synthesis_bridge import verify_import
        from paper_writing_codex.workflow import init_compose, verify_source

        self.ready()
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        verify_import(state)
        receipt_file = Path(state["synthesis_origin"]["handoff"])
        original = receipt_file.read_bytes()
        receipt_file.write_bytes(original + b"\n")
        with self.assertRaises(ValueError):
            verify_import(state)
        receipt_file.write_bytes(original)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "Source changed.\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_source(state)

    def test_translated_main_statement_needs_two_hash_bound_equivalence_reviews(self) -> None:
        from paper_writing_codex.synthesis_bridge import audit_imported_main_results
        from paper_writing_codex.tex_inventory import inventory_tex
        from paper_writing_codex.workflow import init_compose

        self.ready()
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        compose_work = Path(state["work_dir"])
        rows = self.read_json(compose_work / "03-main-results.json")["main_results"]
        row = rows[0]
        paper = Path(state["output"])
        paper.write_text(
            "\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n\\begin{document}\n"
            "\\begin{theorem}\\label{" + row["candidate_label"] + "}\n"
            "For every nonnegative integer $x$, $x+0+0=x$.\n"
            "\\end{theorem}\n\\end{document}\n", encoding="utf-8",
        )
        inventory = inventory_tex(paper)
        unit = next(unit for unit in inventory["units"] if unit.get("label") == row["candidate_label"])
        row["normalized_sha256"] = unit["normalized_sha256"]
        self.assertTrue(audit_imported_main_results(state, rows, inventory))
        for auditor in ("equivalence-one", "equivalence-two"):
            self.add_scope_reviews(state, row, inventory, (auditor,))
            errors = audit_imported_main_results(state, rows, inventory)
            self.assertEqual(auditor == "equivalence-one", bool(errors), errors)
        row["source_equivalence_audits"][0]["auditor"] = "coordinator"
        self.assertTrue(audit_imported_main_results(state, rows, inventory))
        row["source_equivalence_audits"][0]["auditor"] = "equivalence-one"
        row["hypothesis_surface"] = "No restrictions."
        self.assertTrue(audit_imported_main_results(state, rows, inventory))

    def test_bom_author_records_preserve_scope_review_and_raw_byte_checks(self) -> None:
        from paper_writing_codex.synthesis_bridge import audit_imported_main_results
        from paper_writing_codex.tex_inventory import inventory_tex
        from paper_writing_codex.workflow import init_compose

        self.initialize()
        self.inventory_and_candidates()
        records = [self.work / name for name in ("claim-ledger.json", "candidate-prospectuses.json")]
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pending", ["Prepare BOM fixtures."])
        for path in records:
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        original = {path: path.read_bytes() for path in records}
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pass", ["BOM claims inspected."])
        self.engine.mark_synthesis_gate(self.state_path, "candidates", "pass", ["BOM candidates inspected."])
        self.approval()
        self.record_reviews()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Both reviews recorded."])
        self.decision()
        self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Evidence-backed handoff."])
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        rows = self.read_json(Path(state["work_dir"]) / "03-main-results.json")["main_results"]
        row = rows[0]
        paper = Path(state["output"])
        paper.write_text(
            "\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n\\begin{document}\n"
            "\\begin{theorem}\\label{" + row["candidate_label"] + "}\n"
            "For every nonnegative integer $x$, $x+0+0=x$.\n"
            "\\end{theorem}\n\\end{document}\n", encoding="utf-8",
        )
        inventory = inventory_tex(paper)
        self.assertTrue(audit_imported_main_results(state, rows, inventory))
        self.add_scope_reviews(state, row, inventory)
        self.assertEqual([], audit_imported_main_results(state, rows, inventory))
        row["source_equivalence_audits"][0]["auditor"] = "coordinator"
        self.assertTrue(audit_imported_main_results(state, rows, inventory))
        row["source_equivalence_audits"][0]["auditor"] = "equivalence-one"
        row["source_equivalence_audits"][0]["manuscript_sha256"] = "0" * 64
        self.assertTrue(audit_imported_main_results(state, rows, inventory))
        self.assertEqual(original, {path: path.read_bytes() for path in records})
        # Removing a BOM after approval still changes the raw-byte provenance.
        records[0].write_bytes(original[records[0]][3:])
        with self.assertRaises(ValueError):
            audit_imported_main_results(state, rows, inventory)

    def test_changed_macro_context_invalidates_unchanged_statement_scope_reviews(self) -> None:
        from paper_writing_codex.synthesis_bridge import audit_imported_main_results
        from paper_writing_codex.tex_inventory import inventory_tex
        from paper_writing_codex.workflow import init_compose

        self.ready()
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        rows = self.read_json(Path(state["work_dir"]) / "03-main-results.json")["main_results"]
        row = rows[0]
        paper = Path(state["output"])
        paper.write_text(
            "\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n"
            "\\newcommand{\\domain}{\\mathbb{N}}\n\\begin{document}\n"
            "\\begin{theorem}\\label{" + row["candidate_label"] + "}\n"
            "For $x \\in \\domain$, $x+0+0=x$.\n\\end{theorem}\n\\end{document}\n",
            encoding="utf-8",
        )
        inventory = inventory_tex(paper)
        self.add_scope_reviews(state, row, inventory)
        self.assertEqual([], audit_imported_main_results(state, rows, inventory))
        paper.write_text(paper.read_text(encoding="utf-8").replace("\\mathbb{N}", "\\mathbb{R}"),
                         encoding="utf-8")
        changed = inventory_tex(paper)
        unit = next(unit for unit in changed["units"] if unit.get("label") == row["candidate_label"])
        self.assertEqual(row["normalized_sha256"], unit["normalized_sha256"])
        self.assertTrue(audit_imported_main_results(state, rows, changed))

    def test_local_package_class_and_nested_input_context_bind_scope_reviews(self) -> None:
        from paper_writing_codex.synthesis_bridge import audit_imported_main_results
        from paper_writing_codex.tex_inventory import inventory_tex
        from paper_writing_codex.workflow import init_compose

        self.ready()
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        rows = self.read_json(Path(state["work_dir"]) / "03-main-results.json")["main_results"]
        row = rows[0]
        paper = Path(state["output"])
        styles = self.root / "styles"
        sections = self.root / "sections"
        styles.mkdir()
        sections.mkdir()
        paper.write_text(
            "\\documentclass{localpaper}\n\\usepackage{styles/localmath}\n"
            "\\newtheorem{theorem}{Theorem}\n\\begin{document}\n\\input{sections/part}\n"
            "\\begin{theorem}\\label{" + row["candidate_label"] + "}\n"
            "For $x \\in \\domain$, $x+0+0=x$.\n\\end{theorem}\n\\end{document}\n",
            encoding="utf-8",
        )
        context = {
            self.root / "localpaper.cls": "\\LoadClassWithOptions{article}\n\\RequirePackage{base}\n",
            styles / "localmath.sty": "\\RequirePackage[option]{base}\n",
            self.root / "base.sty": "\\RequirePackageWithOptions{styles/localmath}\n\\input{package-macros.def}\n",
            self.root / "package-macros.def": "\\newcommand{\\domain}{\\mathbb{N}}\n",
            sections / "part.tex": "\\input{body-macros}\n",
            self.root / "body-macros.tex": "\\renewcommand{\\domain}{\\mathbb{N}}\n",
        }
        for path, content in context.items():
            path.write_text(content, encoding="utf-8")
        # When both exist, TeX resolves this nested literal input from the master cwd.
        fallback = sections / "body-macros.tex"
        fallback.write_text("\\renewcommand{\\domain}{\\mathbb{C}}\n", encoding="utf-8")
        inventory = inventory_tex(paper)
        inventoried = {Path(entry["path"]) for entry in inventory["source_files"]}
        self.assertTrue(set(context).issubset(inventoried))
        self.assertNotIn(fallback, inventoried)
        self.assertFalse(any(entry.get("missing") for entry in inventory["source_files"]))
        self.add_scope_reviews(state, row, inventory)
        self.assertEqual([], audit_imported_main_results(state, rows, inventory))
        for path, content in context.items():
            with self.subTest(context=path.name):
                path.write_text(content + "\\def\\domain{\\mathbb{R}}\n", encoding="utf-8")
                changed = inventory_tex(paper)
                unit = next(unit for unit in changed["units"] if unit.get("label") == row["candidate_label"])
                self.assertEqual(row["normalized_sha256"], unit["normalized_sha256"])
                self.assertTrue(audit_imported_main_results(state, rows, changed))
                path.write_text(content, encoding="utf-8")

    def test_exact_tex_source_still_requires_reviews_of_separately_stored_hypotheses(self) -> None:
        from paper_writing_codex.synthesis_bridge import audit_imported_main_results
        from paper_writing_codex.tex_inventory import digest_text, inventory_tex
        from paper_writing_codex.workflow import init_compose

        label = "thm:synthesis-" + hashlib.sha256(b"T").hexdigest()[:12]
        exact_tex = "\\begin{theorem}\\label{" + label + "}\n$x+0+0=x$.\n\\end{theorem}"
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n" + exact_tex, encoding="utf-8")
        self.initialize()
        self.inventory_and_candidates()
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pending", ["Freeze supplied TeX theorem."])
        ledger = self.read_json(self.work / "claim-ledger.json")
        next(claim for claim in ledger["claims"] if claim["id"] == "T")["statement"] = exact_tex
        self.write_json(self.work / "claim-ledger.json", ledger)
        self.engine.mark_synthesis_gate(self.state_path, "inventory", "pass", ["Hypotheses remain separately explicit."])
        self.engine.mark_synthesis_gate(self.state_path, "candidates", "pass", ["Same candidate with exact source TeX."])
        self.approval()
        self.record_reviews()
        self.engine.mark_synthesis_gate(self.state_path, "assessment", "pass", ["Synthetic source reviews."])
        self.decision()
        self.engine.mark_synthesis_gate(self.state_path, "decision", "pass", ["Fixture handoff."])
        state = init_compose(self.root / "paper.tex", self.root / "compose", from_synthesis=self.state_path)
        rows = self.read_json(Path(state["work_dir"]) / "03-main-results.json")["main_results"]
        paper = Path(state["output"])
        paper.write_text("\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n"
                         "\\begin{document}\n" + exact_tex + "\n\\end{document}\n", encoding="utf-8")
        inventory = inventory_tex(paper)
        unit = next(unit for unit in inventory["units"] if unit.get("label") == label)
        self.assertEqual(digest_text(exact_tex), unit["normalized_sha256"])
        self.assertTrue(audit_imported_main_results(state, rows, inventory),
                        "Exact TeX must not bypass review of separately recorded hypotheses.")

    def test_successful_cli_audit_is_read_only_and_needs_no_toolchains(self) -> None:
        self.ready()
        before = self.tree_bytes(self.work)
        report = self.cli("audit", "--state", self.state_path, "--require-all-gates", no_tools=True)
        self.assertTrue(report["pass"])
        self.assertEqual(before, self.tree_bytes(self.work))
        self.assertEqual("complete", self.cli("resume", "--state", self.state_path)["status"])


class SemanticFixtureManifestTests(unittest.TestCase):
    def test_semantic_scenarios_are_separate_and_have_explicit_rubrics(self) -> None:
        path = ROOT / "tests" / "fixtures" / "synthesis" / "scenarios.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios = data["scenarios"]
        self.assertEqual({
            "known-only", "fatal-proof-gap", "two-unrelated-stories", "conflicting-versions",
            "known-theorem-new-consequence",
        }, {entry["id"] for entry in scenarios})
        for entry in scenarios:
            self.assertTrue(entry["notes"])
            self.assertTrue(entry["rubric"])
            self.assertTrue(entry["unacceptable"])
        self.assertIn("separate", data["evaluation"])


class SingleMainResultTests(unittest.TestCase):
    def test_one_main_result_is_accepted_without_weakening_theorem_hash_checks(self) -> None:
        from paper_writing_codex.cli import _compose_artifact_errors
        from paper_writing_codex.tex_inventory import inventory_tex
        from paper_writing_codex.workflow import init_compose

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "paper.tex"
            state = init_compose(paper, root / "compose")
            paper.write_text(
                "\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n"
                "\\begin{document}\n\\begin{theorem}\\label{thm:one}\n"
                "For every nonnegative integer $x$, $x+0=x$.\n"
                "\\end{theorem}\n\\begin{proof}By the identity law.\\end{proof}\n"
                "\\end{document}\n", encoding="utf-8",
            )
            unit = next(unit for unit in inventory_tex(paper)["units"] if unit.get("label") == "thm:one")
            record = {
                "graph_node_id": "T", "candidate_label": "thm:one",
                "normalized_sha256": unit["normalized_sha256"],
                "hypothesis_surface": "x is a nonnegative integer",
                "novelty_status": "ADJACENT",
                "novelty_evidence": "Test fixture only; a standard theorem with no publication claim.",
            }
            manifest = Path(state["work_dir"]) / "03-main-results.json"
            SynthesisTests.write_json(manifest, {"schema_version": 1, "main_results": [record]})
            errors = _compose_artifact_errors(state)
            self.assertFalse([error for error in errors if "main result" in error or "main-result" in error])
            record["normalized_sha256"] = "0" * 64
            SynthesisTests.write_json(manifest, {"schema_version": 1, "main_results": [record]})
            self.assertTrue(any("changed after it was locked" in error for error in _compose_artifact_errors(state)))


if __name__ == "__main__":
    unittest.main()
