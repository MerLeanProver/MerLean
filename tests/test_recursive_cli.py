"""Public recursive-writer routing and build receipt regression tests.

State-machine/semantic evidence tests live with the recursive engine. These
tests deliberately use an injected engine to keep CLI compatibility independent
of the implementation's artifact schema.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex import cli
from paper_writing_codex.workflow import init_compose, init_refine, mark_gate, resume_point


SAMPLE = r"""\documentclass{article}
\begin{document}
A short unchanged baseline.
\end{document}
"""


class RecursiveCliTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> dict:
        args = cli.build_parser().parse_args(list(arguments))
        with redirect_stdout(io.StringIO()) as output:
            args.func(args)
        return json.loads(output.getvalue())

    def engine(self, **functions):
        module = types.ModuleType("paper_writing_codex.recursive_writer")
        for name, function in functions.items():
            setattr(module, name, function)
        return patch.dict(sys.modules, {module.__name__: module})

    def test_public_init_defaults_recursive_and_explicit_legacy_is_supported(self):
        with patch.object(cli, "init_compose", return_value={}) as initialize:
            self.invoke("init-compose", "--output", "paper.tex", "--source", "one.md",
                        "--source", "two.tex", "--brief", "brief.json")
            self.assertEqual(2, initialize.call_args.kwargs["workflow_version"])
            self.assertEqual([Path("one.md"), Path("two.tex")],
                             initialize.call_args.kwargs["authoritative_sources"])
            self.assertEqual(5, initialize.call_args.kwargs["max_review_rounds"])
            self.invoke("init-compose", "--output", "paper.tex", "--legacy-workflow")
            self.assertEqual(1, initialize.call_args.kwargs["workflow_version"])

    def test_refine_keeps_positional_baseline_distinct_from_authoritative_sources(self):
        with patch.object(cli, "init_refine", return_value={}) as initialize:
            self.invoke("init-refine", "paper-v1.tex", "--source", "notes.md",
                        "--brief", "brief.json", "--max-review-rounds", "7")
            self.assertEqual(Path("paper-v1.tex"), initialize.call_args.args[0])
            self.assertEqual([Path("notes.md")], initialize.call_args.kwargs["authoritative_sources"])
            self.assertEqual(7, initialize.call_args.kwargs["max_review_rounds"])

    def test_python_initializers_keep_legacy_default_and_preserve_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            before = source.read_bytes()
            refined = init_refine(source)
            composed = init_compose(root / "other.tex")
            self.assertEqual(1, refined["schema_version"])
            self.assertEqual(1, composed["schema_version"])
            self.assertEqual(before, source.read_bytes())

    def test_recursive_initialization_preserves_reservations_before_handoff(self):
        records = []

        def initialize(state_path, sources, brief, max_review_rounds):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("output_reservation", state)
            self.assertTrue(Path(state["output"]).is_file())
            records.append((sources, brief, max_review_rounds))
            return {"schema_version": 2}

        with tempfile.TemporaryDirectory() as directory, self.engine(initialize=initialize):
            root = Path(directory)
            source = root / "paper.tex"
            source.write_text(SAMPLE, encoding="utf-8")
            refined = init_refine(source, workflow_version=2)
            composed = init_compose(root / "other.tex", workflow_version=2,
                                    authoritative_sources=[source], brief=root / "brief.json",
                                    max_review_rounds=3)
            self.assertEqual(2, refined["schema_version"])
            self.assertEqual(2, composed["schema_version"])
            self.assertEqual(([source], None, 5), records[0])
            self.assertEqual(([source], root / "brief.json", 3), records[1])

    def test_new_commands_dispatch_only_the_requested_engine_operation(self):
        cases = [
            ("record-writing-plan", ["--plan", "plan.json"], "record_plan",
             (Path("state.json"), Path("plan.json"))),
            ("freeze-revision", [], "freeze_revision", (Path("state.json"),)),
            ("review-packet", ["--role", "faithfulness", "--reviewer-id", "independent-1"],
             "review_packet", (Path("state.json"), "faithfulness", "independent-1")),
            ("review-packet", ["--role", "faithfulness-secondary", "--reviewer-id", "independent-2"],
             "review_packet", (Path("state.json"), "faithfulness-secondary", "independent-2")),
            ("record-review", ["--report", "report.json"], "record_review",
             (Path("state.json"), Path("report.json"))),
            ("continue-writing", ["--approval-evidence", "author.txt", "--additional-rounds", "2"],
             "continue_writing", (Path("state.json"), Path("author.txt"), 2)),
        ]
        for name, arguments, function_name, expected in cases:
            with self.subTest(command=name):
                function = Mock(return_value={"operation": name})
                with self.engine(**{function_name: function}):
                    self.assertEqual({"operation": name},
                                     self.invoke(name, "--state", "state.json", *arguments))
                function.assert_called_once_with(*expected)

    def test_mode_routing_does_not_invoke_legacy_gate_or_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps({"schema_version": 2, "mode": "refine"}), encoding="utf-8")
            before = state_path.read_bytes()
            resume = Mock(return_value={"status": "reviewing"})
            audit = Mock(return_value={"pass": True, "errors": [], "status": "reviewing"})
            gate = Mock(return_value={"status": "pending"})
            with self.engine(resume_writing=resume, audit_writing=audit, mark_writing_gate=gate), \
                    patch.object(cli, "_compile_tex", side_effect=AssertionError("audit compiled")):
                self.assertEqual({"status": "reviewing"}, resume_point(state_path))
                self.assertEqual({"status": "pending"}, mark_gate(state_path, "final", "pending", []))
                self.invoke("audit", "--state", str(state_path), "--require-all-gates")
            self.assertEqual(before, state_path.read_bytes())
            audit.assert_called_once_with(state_path, require_complete=True)
            gate.assert_called_once_with(state_path, "final", "pending", [])

    def test_compile_state_and_path_are_mutually_exclusive(self):
        function = Mock(return_value={"pass": True})
        with self.engine(compile_revision=function):
            self.invoke("compile", "--state", "state.json", "--timeout", "17")
            function.assert_called_once_with(Path("state.json"), timeout=17)
            with self.assertRaisesRegex(ValueError, "not both"):
                self.invoke("compile", "paper.tex", "--state", "state.json")
            with self.assertRaisesRegex(ValueError, "requires"):
                self.invoke("compile")

    def test_invalid_review_budget_is_rejected_before_reserving_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "paper.tex"
            with self.assertRaisesRegex(ValueError, "positive"):
                init_compose(output, workflow_version=2, max_review_rounds=0)
            self.assertFalse(output.exists())


class RetainedCompilationTests(unittest.TestCase):
    def test_tex_search_paths_use_native_separator_and_portable_slashes(self):
        with tempfile.TemporaryDirectory() as directory:
            tex = Path(directory) / "paper.tex"
            tex.write_text(SAMPLE, encoding="utf-8")
            for separator in (";", ":"):
                with self.subTest(separator=separator):
                    environments = []

                    def run(command, **kwargs):
                        environments.append(kwargs["env"])
                        out = Path(kwargs["cwd"])
                        (out / "paper.pdf").write_bytes(b"synthetic PDF")
                        (out / "paper.log").write_text("Clean.", encoding="utf-8")
                        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

                    with patch.object(cli.shutil, "which", side_effect=lambda name: "/fake/pdflatex"
                                      if name == "pdflatex" else None), \
                            patch.object(cli.os, "pathsep", separator), \
                            patch.dict(cli.os.environ, {key: "prior-search" for key in
                                                       ("TEXINPUTS", "BIBINPUTS", "BSTINPUTS")}), \
                            patch.object(cli.subprocess, "run", side_effect=run):
                        self.assertTrue(cli._compile_tex(tex, 30)["pass"])
                    for environment in environments:
                        for variable in ("TEXINPUTS", "BIBINPUTS", "BSTINPUTS"):
                            self.assertEqual(f"{tex.parent.as_posix()}//{separator}prior-search",
                                             environment[variable])

    def test_latexmk_disables_user_and_project_rc_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            tex = Path(directory) / "paper.tex"
            tex.write_text(SAMPLE, encoding="utf-8")
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                out = Path(kwargs["cwd"])
                (out / "paper.pdf").write_bytes(b"synthetic PDF")
                (out / "paper.log").write_text("Clean.", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(cli.shutil, "which", side_effect=lambda name: "/fake/latexmk"
                              if name == "latexmk" else None), \
                    patch.object(cli.subprocess, "run", side_effect=run):
                self.assertTrue(cli._compile_tex(tex, 30)["pass"])
            self.assertEqual(1, len(commands))
            self.assertIn("-norc", commands[0])
            self.assertIn("-latexoption=-no-shell-escape", commands[0])

    def test_retained_pdf_and_log_are_exclusive_hash_bound_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tex = root / "paper.tex"
            tex.write_text(SAMPLE, encoding="utf-8")
            baseline = tex.read_bytes()
            retain = root / "review-build"

            def run(command, **kwargs):
                out = Path(kwargs["cwd"])
                (out / "paper.pdf").write_bytes(b"test PDF")
                (out / "paper.log").write_text("Clean compilation.", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(cli.shutil, "which", side_effect=lambda name: "/fake/pdflatex"
                              if name == "pdflatex" else None), \
                    patch.object(cli.subprocess, "run", side_effect=run):
                report = cli._compile_tex(tex, 30, retain_dir=retain)
                self.assertTrue(report["pass"], report)
                self.assertEqual(cli.sha256_file(retain / "paper.pdf"), report["pdf_sha256"])
                self.assertEqual(cli.sha256_file(retain / "paper.log"), report["log_sha256"])
                self.assertEqual(str(retain / "paper.pdf"), report["retained_pdf"])
                self.assertEqual(str(retain / "paper.log"), report["retained_log"])
                self.assertFalse(Path(report["isolated_output"]).exists())
                with self.assertRaises(FileExistsError):
                    cli._compile_tex(tex, 30, retain_dir=retain)
            self.assertEqual(baseline, tex.read_bytes())


if __name__ == "__main__":
    unittest.main()
