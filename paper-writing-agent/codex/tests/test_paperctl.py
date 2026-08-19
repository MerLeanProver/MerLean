from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from paper_writing_codex.cli import _compose_artifact_errors, _compile_tex  # noqa: E402
from paper_writing_codex.coverage import (  # noqa: E402
    _audited_style_rewrite_errors, audit_refinement, lock_main_results,
)
from paper_writing_codex.critical_path import analyze  # noqa: E402
from paper_writing_codex.safe_extract import safe_extract  # noqa: E402
from paper_writing_codex.tex_inventory import digest_text, inventory_tex  # noqa: E402
from paper_writing_codex.versioning import exclusive_copy, next_version_path, sha256_file  # noqa: E402
from paper_writing_codex.workflow import (  # noqa: E402
    claim_output, init_compose, init_refine, mark_gate, verify_output,
)


SAMPLE = r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\section{Introduction}
This paper proves the central result and records enough explanatory prose for coverage inventory.

\begin{theorem}[Main result]\label{thm:main}
For every integer $n$, one has $n=n$.
\end{theorem}
\begin{proof}\label{proof:main}
This follows by reflexivity; see the statement in Theorem~\ref{thm:main}.
\end{proof}
\end{document}
"""


class VersioningTests(unittest.TestCase):
    def test_suffix_cases_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {
                "paper.tex": "paper-v1.tex",
                "paper-v0.tex": "paper-v1.tex",
                "paper-v9.tex": "paper-v10.tex",
                "paper-v2-draft.tex": "paper-v2-draft-v1.tex",
                "sudden death of non-Gaussianity in fermionic system.tex":
                    "sudden death of non-Gaussianity in fermionic system-v1.tex",
            }
            for incoming, expected in cases.items():
                source = root / incoming
                source.write_text(SAMPLE, encoding="utf-8")
                self.assertEqual(next_version_path(source)[0].name, expected)

    def test_reject_leading_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper-v01.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            with self.assertRaises(ValueError):
                next_version_path(source)

    def test_init_is_exclusive_and_source_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper with spaces.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            before = sha256_file(source)
            state = init_refine(source)
            output = Path(state["output"])
            self.assertTrue(output.is_file())
            self.assertEqual(before, sha256_file(source))
            self.assertEqual(before, sha256_file(output))
            with self.assertRaises(FileExistsError):
                init_refine(source, Path(directory) / "another-work")
            self.assertEqual(before, sha256_file(source))

    def test_failed_copy_does_not_delete_raced_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            destination = root / "paper-v1.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            real_write = os.write
            fired = False

            def hostile_write(fd, data):
                nonlocal fired
                if not fired:
                    fired = True
                    destination.write_text("replacement", encoding="utf-8")
                    raise OSError("simulated copy failure")
                return real_write(fd, data)

            with patch("paper_writing_codex.versioning.os.write", side_effect=hostile_write):
                with self.assertRaises(OSError):
                    exclusive_copy(source, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "replacement")

    def test_publish_race_preserves_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            destination = root / "paper-v1.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            from paper_writing_codex import versioning
            real_publish = versioning.atomic_rename_noreplace

            def race_publish(staging, target):
                target.write_text("competitor", encoding="utf-8")
                return real_publish(staging, target)

            with patch("paper_writing_codex.versioning.atomic_rename_noreplace", side_effect=race_publish):
                with self.assertRaises(FileExistsError):
                    exclusive_copy(source, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "competitor")

    def test_init_detects_intervening_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            from paper_writing_codex import workflow
            original = workflow.exclusive_copy

            def copy_then_mutate(source_path, destination_path):
                record = original(source_path, destination_path)
                source_path.write_text(SAMPLE + "% raced change\n", encoding="utf-8")
                return record

            with patch("paper_writing_codex.workflow.exclusive_copy", side_effect=copy_then_mutate):
                with self.assertRaises(RuntimeError):
                    init_refine(source)

    def test_compose_reserves_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "paper.tex"
            state = init_compose(output)
            self.assertTrue(output.is_file())
            self.assertEqual(state["output"], str(output))
            with self.assertRaises(FileExistsError):
                init_compose(output, Path(directory) / "other-work")

    def test_compose_rejects_replaced_output_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "paper.tex"
            state = init_compose(output)
            replacement = root / "replacement.tex"
            replacement.write_text(SAMPLE, encoding="utf-8")
            output.unlink()
            output.symlink_to(replacement)
            with self.assertRaises(ValueError):
                verify_output(state)

    def test_output_inode_replacement_requires_explicit_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "paper.tex"
            state = init_compose(output)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            replacement = root / "replacement.tex"
            replacement.write_text(SAMPLE, encoding="utf-8")
            os.replace(replacement, output)
            with self.assertRaises(ValueError):
                verify_output(state, require_reservation=True)
            claim_output(state_path)
            refreshed = json.loads(state_path.read_text(encoding="utf-8"))
            verify_output(refreshed, require_reservation=True)

    def test_refine_rejects_missing_included_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE.replace("\\end{document}", "\\input{later}\\end{document}"), encoding="utf-8")
            with self.assertRaises(ValueError):
                init_refine(source)


class CoverageTests(unittest.TestCase):
    def test_audited_style_rewrite_requires_two_passes_and_a_proof_target(self) -> None:
        original = {"id": "proof:p", "kind": "proof", "label": "p"}
        candidate = [{"id": "proof:p", "kind": "proof", "label": "p"}]
        entry = {
            "unit_id": "proof:p",
            "classification": "AUDITED_STYLE",
            "reason": "Replace process-numbered headings with unnumbered list summaries.",
            "source": "frozen proof",
            "consumer": "thm:main",
            "replacement_label": "p",
            "semantic_audits": [
                {"auditor": "one", "verdict": "PASS", "evidence": "equations unchanged"},
            ],
        }
        self.assertTrue(_audited_style_rewrite_errors(entry, original, candidate))
        entry["semantic_audits"].append(
            {"auditor": "two", "verdict": "PASS", "evidence": "logic unchanged"}
        )
        self.assertEqual([], _audited_style_rewrite_errors(entry, original, candidate))
        replacement_label = entry.pop("replacement_label")
        self.assertTrue(_audited_style_rewrite_errors(entry, original, candidate))
        entry["replacement_label"] = replacement_label
        statement = {"id": "statement:t", "kind": "statement", "label": "t"}
        self.assertTrue(_audited_style_rewrite_errors(entry, statement, candidate))

    def test_itemize_inside_proof_is_not_double_counted_as_math(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            itemized = SAMPLE.replace(
                "This follows by reflexivity; see the statement in Theorem~\\ref{thm:main}.",
                "\\begin{itemize}\n"
                "\\item \\textbf{Reflexivity.} This follows by reflexivity; "
                "see Theorem~\\ref{thm:main}.\n"
                "\\end{itemize}",
            )
            source.write_text(itemized, encoding="utf-8")
            inventory = inventory_tex(source)
            self.assertFalse(any(
                unit.get("kind") == "environment" and unit.get("environment") == "itemize"
                for unit in inventory["units"]
            ))
            self.assertEqual(
                1,
                sum(unit.get("kind") == "proof" for unit in inventory["units"]),
            )

    def test_standalone_itemize_remains_covered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            roadmap = (
                "\\begin{itemize}\n"
                "\\item \\textbf{Local control.} Bound every interaction shell.\n"
                "\\item \\textbf{Global conclusion.} Sum the convergent expansion.\n"
                "\\end{itemize}\n"
            )
            source = Path(directory) / "paper.tex"
            source.write_text(
                SAMPLE.replace("\\end{document}", roadmap + "\\end{document}"),
                encoding="utf-8",
            )
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(SAMPLE, encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("classified auto" in error for error in report["errors"]))

    def test_exact_copy_passes_after_main_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            report = audit_refinement(state_path)
            self.assertTrue(report["pass"], report["errors"])
            self.assertEqual(sha256_file(source), state["source_sha256"])

    def test_changed_main_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(SAMPLE.replace("$n=n$", "$n=0$"), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertFalse(report["pass"])
            self.assertTrue(any("main result" in error or "classified auto" in error for error in report["errors"]))

    def test_main_lock_rejects_proof_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            with self.assertRaises(ValueError):
                lock_main_results(state_path, ["proof:main"])

    def test_duplicate_label_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(SAMPLE.replace("\\end{document}", "\\label{thm:main}\n\\end{document}"), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("duplicate labels" in error for error in report["errors"]))

    def test_recursive_include_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            appendix = root / "appendix.tex"
            appendix.write_text("\\section{Details}\nA substantive included appendix paragraph that must stay frozen.\n", encoding="utf-8")
            source = root / "paper.tex"
            source.write_text(SAMPLE.replace("\\end{document}", "\\appendix\n\\input{appendix}\n\\end{document}"), encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            appendix.write_text("changed", encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("source-tree file changed" in error for error in report["errors"]))

    def test_main_result_cannot_move_to_appendix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(SAMPLE.replace("\\begin{theorem}", "\\appendix\n\\begin{theorem}"), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("moved out of the paper body" in error for error in report["errors"]))

    def test_split_appendix_two_way_links_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            work = Path(state["work_dir"])
            state_path = work / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(SAMPLE.replace(
                "\\begin{proof}\\label{proof:main}\nThis follows by reflexivity; see the statement in Theorem~\\ref{thm:main}.\n\\end{proof}",
                "The proof is in Appendix~\\ref{proof:main:appendix}.\n\\appendix\n\\input{appendix-v1}",
            ), encoding="utf-8")
            (root / "appendix-v1.tex").write_text(
                "\\begin{proof}\\label{proof:main:appendix}\n"
                "This proves Theorem~\\ref{thm:main} by reflexivity.\n\\end{proof}\n",
                encoding="utf-8",
            )
            ledger_path = work / "05-coverage-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            proof_entry = next(entry for entry in ledger["entries"] if entry["unit_id"] == "proof:proof:main")
            proof_entry["disposition"] = "body-appendix"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            compression_path = work / "04-compression-ledger.json"
            compression = json.loads(compression_path.read_text(encoding="utf-8"))
            comp = next(entry for entry in compression["entries"] if entry["unit_id"] == "proof:proof:main")
            comp.update({
                "classification": "IMPORTANT_BODY_APPENDIX",
                "body_label": "thm:main",
                "appendix_label": "proof:main:appendix",
            })
            compression_path.write_text(json.dumps(compression), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(report["pass"], report["errors"])

    def test_identical_unlabeled_units_do_not_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repeated = "\\begin{lemma}The same routine fact.\\end{lemma}\n"
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE.replace("\\end{document}", repeated + repeated + "\\end{document}"), encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(SAMPLE.replace("\\end{document}", repeated + "\\end{document}"), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("classified auto" in error for error in report["errors"]))

    def test_macro_change_affecting_main_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            macro_sample = SAMPLE.replace(
                "\\newtheorem{theorem}{Theorem}",
                "\\newtheorem{theorem}{Theorem}\n\\newcommand{\\criticalconstant}{1}",
            ).replace("$n=n$", "$n=\\criticalconstant$")
            source.write_text(macro_sample, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(macro_sample.replace(
                "\\newcommand{\\criticalconstant}{1}", "\\newcommand{\\criticalconstant}{2}"
            ), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("equivalence PASS" in error for error in report["errors"]))

    def test_body_local_macro_change_affecting_main_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            macro_sample = SAMPLE.replace(
                "\\section{Introduction}",
                "\\section{Introduction}\n\\def\\criticalconstant{1}",
            ).replace("$n=n$", "$n=\\criticalconstant$")
            source.write_text(macro_sample, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(
                macro_sample.replace("\\def\\criticalconstant{1}", "\\def\\criticalconstant{2}"),
                encoding="utf-8",
            )
            report = audit_refinement(state_path)
            self.assertTrue(any("equivalence PASS" in error for error in report["errors"]))

    def test_short_scope_caveat_cannot_disappear_silently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            scoped = SAMPLE.replace("\\begin{theorem}", "Only for $n>0$.\n\n\\begin{theorem}")
            source.write_text(scoped, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(SAMPLE, encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("changed or missing but still classified auto" in error for error in report["errors"]))

    def test_post_draft_math_requires_compression_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            work = Path(state["work_dir"])
            state_path = work / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            first = "\\begin{lemma}First drafted lemma.\\end{lemma}\n"
            second = "\\begin{lemma}Late untracked lemma.\\end{lemma}\n"
            output.write_text(SAMPLE.replace("\\end{document}", first + "\\end{document}"), encoding="utf-8")
            snapshot_inventory = inventory_tex(output)
            (work / "05-pre-shrink-inventory.json").write_text(json.dumps({
                "schema_version": 1, "source": str(output), "source_sha256": sha256_file(output),
                "bytes": output.stat().st_size, "pages": None, "inventory": snapshot_inventory,
            }), encoding="utf-8")
            compression_path = work / "04-compression-ledger.json"
            compression = json.loads(compression_path.read_text(encoding="utf-8"))
            by_id = {entry["unit_id"]: entry for entry in compression["entries"]}
            for unit in snapshot_inventory["units"]:
                if unit["kind"] in {"statement", "proof", "display", "equation", "align", "gather", "multline", "figure", "table", "environment"}:
                    by_id.setdefault(unit["id"], {"unit_id": unit["id"]})["classification"] = "CORE_INLINE"
            compression["entries"] = list(by_id.values())
            compression_path.write_text(json.dumps(compression), encoding="utf-8")
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            state_data["gates"]["draft"]["status"] = "pass"
            state_data["gates"]["compression"]["status"] = "pass"
            state_path.write_text(json.dumps(state_data), encoding="utf-8")
            output.write_text(
                SAMPLE.replace("\\end{document}", first + second + "\\end{document}"), encoding="utf-8"
            )
            report = audit_refinement(state_path)
            self.assertTrue(any("post-draft mathematical" in error for error in report["errors"]))

    def test_ledger_only_requires_exact_archived_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            work = Path(state["work_dir"])
            state_path = work / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            baseline = json.loads((work / "00-baseline-inventory.json").read_text(encoding="utf-8"))
            (work / "05-pre-shrink-inventory.json").write_text(json.dumps({
                "schema_version": 1, "inventory": baseline, "bytes": source.stat().st_size,
                "pages": None, "source": str(source), "source_sha256": sha256_file(source),
            }), encoding="utf-8")
            Path(state["output"]).write_text(SAMPLE.replace(
                "\\begin{proof}\\label{proof:main}\n"
                "This follows by reflexivity; see the statement in Theorem~\\ref{thm:main}.\n"
                "\\end{proof}\n", "",
            ), encoding="utf-8")
            coverage_path = work / "05-coverage-ledger.json"
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            proof_coverage = next(item for item in coverage["entries"] if item["unit_id"] == "proof:proof:main")
            proof_coverage["disposition"] = "ledger-only"
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            compression_path = work / "04-compression-ledger.json"
            compression = json.loads(compression_path.read_text(encoding="utf-8"))
            for entry in compression["entries"]:
                entry["classification"] = "CORE_INLINE"
            proof_entry = next(item for item in compression["entries"] if item["unit_id"] == "proof:proof:main")
            proof_entry.update({
                "classification": "LEDGER_ONLY", "archive_anchor": "proof-main", "reason": "routine",
                "source": "v0", "consumer": "thm:main", "archived_text": "A different proof.",
                "archived_text_sha256": digest_text("A different proof."),
            })
            compression_path.write_text(json.dumps(compression), encoding="utf-8")
            (work / "05.5-deleted-steps.md").write_text("# proof-main\n\nA different proof.\n", encoding="utf-8")
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            state_data["gates"]["draft"]["status"] = "pass"
            state_data["gates"]["compression"]["status"] = "pass"
            state_path.write_text(json.dumps(state_data), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("archived text is not the exact" in error for error in report["errors"]))

    def test_baseline_unit_removed_before_shrink_has_zero_allowed_multiplicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            routine = "\\begin{proof}\nA routine unlabeled derivation.\n\\end{proof}\n"
            source_text = SAMPLE.replace("\\end{document}", routine + "\\end{document}")
            source.write_text(source_text, encoding="utf-8")
            state = init_refine(source)
            work = Path(state["work_dir"])
            state_path = work / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            output = Path(state["output"])
            output.write_text(source_text.replace(routine, ""), encoding="utf-8")
            baseline = json.loads((work / "00-baseline-inventory.json").read_text(encoding="utf-8"))
            proof = next(
                unit for unit in baseline["units"]
                if unit["kind"] == "proof" and not unit.get("label")
            )
            snapshot = inventory_tex(output)
            (work / "05-pre-shrink-inventory.json").write_text(json.dumps({
                "schema_version": 1, "inventory": snapshot, "bytes": output.stat().st_size,
                "main_text_characters": 1, "pages": 1, "source": str(output),
                "source_sha256": sha256_file(output),
            }), encoding="utf-8")
            (work / "05.5-shrink-report.json").write_text(json.dumps({
                "pages_before": 1, "pages_after": 1, "pages_delta": 0,
                "bytes_before": output.stat().st_size, "bytes_after": output.stat().st_size,
                "main_text_characters_before": 1, "main_text_characters_after": 0,
                "main_text_characters_delta": -1,
            }), encoding="utf-8")
            coverage_path = work / "05-coverage-ledger.json"
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            coverage_entry = next(
                entry for entry in coverage["entries"] if entry["unit_id"] == proof["id"]
            )
            coverage_entry.update({"disposition": "ledger-only", "reason": "routine"})
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            compression_path = work / "04-compression-ledger.json"
            compression = json.loads(compression_path.read_text(encoding="utf-8"))
            for entry in compression["entries"]:
                entry["classification"] = "CORE_INLINE"
            proof_entry = next(
                entry for entry in compression["entries"] if entry["unit_id"] == proof["id"]
            )
            proof_entry.update({
                "classification": "LEDGER_ONLY", "archive_anchor": "proof-main",
                "reason": "routine", "source": "baseline", "consumer": "thm:main",
                "archived_text": proof["normalized_text"],
                "archived_text_sha256": proof["normalized_sha256"],
                "archived_raw_text": proof["raw_text"],
                "archived_raw_sha256": proof["raw_sha256"],
            })
            compression_path.write_text(json.dumps(compression), encoding="utf-8")
            (work / "05.5-deleted-steps.md").write_text(
                "# proof-main\n\n" + proof["normalized_text"] + "\n\n" + proof["raw_text"],
                encoding="utf-8",
            )
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            state_data["gates"]["draft"]["status"] = "pass"
            state_data["gates"]["compression"]["status"] = "pass"
            state_path.write_text(json.dumps(state_data), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertFalse(any(
                "unlabeled LEDGER_ONLY unit still appears" in error for error in report["errors"]
            ), report["errors"])
            output.write_text(source_text, encoding="utf-8")
            reintroduced = audit_refinement(state_path)
            self.assertTrue(any(
                "unlabeled LEDGER_ONLY unit still appears" in error
                for error in reintroduced["errors"]
            ), reintroduced["errors"])

    def test_custom_theorem_environment_is_inventoried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            custom = SAMPLE.replace(
                "\\newtheorem{theorem}{Theorem}", "\\newtheorem{maintheorem}{Main Theorem}"
            ).replace("\\begin{theorem}", "\\begin{maintheorem}").replace(
                "\\end{theorem}", "\\end{maintheorem}"
            )
            source = Path(directory) / "paper.tex"
            source.write_text(custom, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(custom.replace(
                "\\begin{maintheorem}[Main result]\\label{thm:main}\nFor every integer $n$, one has $n=n$.\n\\end{maintheorem}\n",
                "",
            ), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("main result label is missing" in error for error in report["errors"]))

    def test_retained_rewrite_needs_reason_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lemma = "\\begin{lemma}\\label{lem:support}Support fact.\\end{lemma}\n"
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE.replace("\\end{document}", lemma + "\\end{document}"), encoding="utf-8")
            state = init_refine(source)
            work = Path(state["work_dir"])
            state_path = work / "00-run-state.json"
            lock_main_results(state_path, ["thm:main"])
            Path(state["output"]).write_text(SAMPLE.replace(
                "\\end{document}", lemma.replace("Support fact.", "Rewritten support fact.") + "\\end{document}"
            ), encoding="utf-8")
            ledger_path = work / "05-coverage-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            entry = next(item for item in ledger["entries"] if item["unit_id"] == "statement:lem:support")
            entry.update({"disposition": "retained", "target_label": "lem:support"})
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            report = audit_refinement(state_path)
            self.assertTrue(any("needs evidence and reason" in error for error in report["errors"]))


class GraphTests(unittest.TestCase):
    def test_tied_paths(self) -> None:
        data = {
            "statements": [
                {"id": "A", "type": "Lemma", "name": "A", "content": "A", "dependencies": []},
                {"id": "B", "type": "Lemma", "name": "B", "content": "B", "dependencies": []},
                {"id": "T", "type": "Theorem", "name": "T", "content": "T", "dependencies": ["A", "B"]},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            graph = Path(directory) / "graph.json"
            graph.write_text(json.dumps(data), encoding="utf-8")
            report = analyze(graph, ["T"])
            self.assertEqual({tuple(path) for path in report["terminals"][0]["paths"]}, {("A", "T"), ("B", "T")})
            self.assertEqual(
                {(edge["source"], edge["target"]) for edge in report["theorem_edges"]},
                {("A", "T"), ("B", "T")},
            )

    def test_cycle_and_missing_node_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            graph = Path(directory) / "cycle.json"
            graph.write_text(json.dumps({"statements": [
                {"id": "A", "type": "Lemma", "dependencies": ["B"]},
                {"id": "B", "type": "Lemma", "dependencies": ["A"]},
            ]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze(graph, ["A"])
            graph.write_text(json.dumps({"statements": [
                {"id": "A", "type": "Lemma", "dependencies": ["MISSING"]},
            ]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze(graph, ["A"])


class ExtractionTests(unittest.TestCase):
    def test_extract_normal_tar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar"
            payload = b"\\documentclass{article}"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("paper/main.tex")
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))
            destination = root / "refs" / "1234_5678"
            safe_extract(archive, destination)
            self.assertEqual((destination / "paper" / "main.tex").read_bytes(), payload)

    def test_reject_traversal_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traversal = root / "bad.tar"
            with tarfile.open(traversal, "w") as bundle:
                info = tarfile.TarInfo("../escape.tex")
                info.size = 1
                bundle.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(ValueError):
                safe_extract(traversal, root / "out")
            self.assertFalse((root / "escape.tex").exists())
            self.assertFalse((root / "out").exists())
            self.assertTrue(any(root.glob(".out.staging-*")))

            link = root / "link.tar"
            with tarfile.open(link, "w") as bundle:
                info = tarfile.TarInfo("paper/link")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../escape"
                bundle.addfile(info)
            with self.assertRaises(ValueError):
                safe_extract(link, root / "out-link")

    def test_existing_destination_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("main.tex")
                info.size = 1
                bundle.addfile(info, io.BytesIO(b"x"))
            destination = root / "refs"
            destination.mkdir()
            marker = destination / "keep"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                safe_extract(archive, destination)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_concurrent_destination_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("main.tex")
                info.size = 1
                bundle.addfile(info, io.BytesIO(b"x"))
            destination = root / "refs"
            from paper_writing_codex import safe_extract as extractor
            real_extract = extractor._extract_tar

            def extract_then_race(source_archive, staging):
                real_extract(source_archive, staging)
                destination.mkdir()
                (destination / "keep").write_text("competitor", encoding="utf-8")

            with patch("paper_writing_codex.safe_extract._extract_tar", side_effect=extract_then_race):
                with self.assertRaises(FileExistsError):
                    safe_extract(archive, destination)
            self.assertEqual((destination / "keep").read_text(encoding="utf-8"), "competitor")

    def test_staging_path_swap_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("main.tex")
                info.size = 1
                bundle.addfile(info, io.BytesIO(b"x"))
            destination = root / "refs"
            outside = root / "outside"
            outside.mkdir()
            from paper_writing_codex import safe_extract as extractor
            real_mkdtemp = extractor.tempfile.mkdtemp
            real_extract = extractor._extract_tar
            created: dict[str, Path] = {}

            def tracked_mkdtemp(*args, **kwargs):
                value = Path(real_mkdtemp(*args, **kwargs))
                created["path"] = value
                return str(value)

            def swap_then_extract(source_archive, staging_fd):
                staging = created["path"]
                moved = staging.with_name(staging.name + "-moved")
                staging.rename(moved)
                staging.symlink_to(outside, target_is_directory=True)
                real_extract(source_archive, staging_fd)

            with patch("paper_writing_codex.safe_extract.tempfile.mkdtemp", side_effect=tracked_mkdtemp), patch(
                "paper_writing_codex.safe_extract._extract_tar", side_effect=swap_then_extract,
            ):
                with self.assertRaises(RuntimeError):
                    safe_extract(archive, destination)
            self.assertFalse((outside / "main.tex").exists())
            self.assertFalse(destination.exists())


class ManifestTests(unittest.TestCase):
    def test_plugin_and_skills_have_no_placeholders(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        # The plugin's registered name is stable; the folder is the runtime slot
        # (paper-writing-agent/codex) after the two-agents-x-runtimes reorganization.
        self.assertEqual(manifest["name"], "paper-writing-codex")
        self.assertEqual(manifest["skills"], "./skills/")
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            self.assertNotIn("[TODO:", skill.read_text(encoding="utf-8"))

    def test_gates_cannot_be_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            state = init_refine(source)
            state_path = Path(state["work_dir"]) / "00-run-state.json"
            with self.assertRaises(ValueError):
                mark_gate(state_path, "framework", "pass", ["compiled"])
            mark_gate(state_path, "critical-path", "pass", ["certificate checked"])
            mark_gate(state_path, "framework", "pass", ["compiled"])

    def test_compose_orphan_appendix_proof_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "paper.tex"
            state = init_compose(output)
            output.write_text(
                "\\documentclass{article}\n\\newtheorem{theorem}{Theorem}\n\\begin{document}\n"
                "\\begin{theorem}\\label{thm:x}X.\\end{theorem}\n\\appendix\n"
                "\\begin{proof}\\label{proof:x}Proof of Theorem~\\ref{thm:x}.\\end{proof}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            inventory = inventory_tex(output)
            work = Path(state["work_dir"])
            (work / "05-pre-shrink-inventory.json").write_text(json.dumps({
                "schema_version": 1, "inventory": inventory, "bytes": output.stat().st_size,
                "pages": None, "source": str(output), "source_sha256": sha256_file(output),
            }), encoding="utf-8")
            entries = [
                {"unit_id": unit["id"], "classification": "CORE_INLINE"}
                for unit in inventory["units"] if unit["kind"] in {
                    "statement", "proof", "display", "equation", "align", "gather", "multline",
                    "figure", "table", "environment",
                }
            ]
            (work / "04-compression-ledger.json").write_text(
                json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8"
            )
            errors = _compose_artifact_errors(state)
            self.assertTrue(any("appendix proof must be classified" in error for error in errors))

    @unittest.skipUnless(shutil.which("latexmk") or shutil.which("pdflatex"), "LaTeX unavailable")
    def test_compile_disables_shell_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            victim = root / "victim.txt"
            victim.write_text("sentinel", encoding="utf-8")
            tex = root / "hostile paper.tex"
            tex.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\immediate\\write18{makeindex probe.idx -o victim.txt}\nSafe.\n\\end{document}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(ROOT / "scripts" / "paperctl"), "compile", str(tex)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(victim.read_text(encoding="utf-8"), "sentinel")

    @unittest.skipUnless(shutil.which("latexmk") or shutil.which("pdflatex"), "LaTeX unavailable")
    def test_compile_rejects_undefined_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tex = Path(directory) / "broken.tex"
            tex.write_text(
                "\\documentclass{article}\\begin{document}\\DefinitelyUndefined\\end{document}",
                encoding="utf-8",
            )
            self.assertFalse(_compile_tex(tex, 60)["pass"])


if __name__ == "__main__":
    unittest.main()
