"""PDF page-count probes must tolerate localized metadata and fail closed."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex import cli


class PdfinfoEncodingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tex = self.root / "paper.tex"
        self.source = "\\documentclass{article}\n\\begin{document}Text.\\end{document}\n"
        self.tex.write_text(self.source, encoding="utf-8")
        self.source_bytes = self.tex.read_bytes()

    def probe(self, stdout, *, returncode=0, log="Clean.", compile_returncode=0,
              require_pages=False):
        def run(command, **kwargs):
            if command[0] == "/fake/pdfinfo":
                # Match subprocess's decoding behavior so text=True recreates
                # the real UTF-8-mode failure, rather than merely asserting flags.
                output = stdout
                if kwargs.get("text") and output is not None:
                    output = output.decode("utf-8")
                return subprocess.CompletedProcess(command, returncode, output, b"\xd6\xd0\xce\xc4")
            self.assertIn("-latexoption=-no-shell-escape", command)
            out = Path(kwargs["cwd"])
            self.assertNotEqual(self.tex.parent, out)
            (out / "paper.pdf").write_bytes(b"Synthetic PDF for page-count tests")
            (out / "paper.log").write_text(log, encoding="utf-8")
            return subprocess.CompletedProcess(command, compile_returncode, "", "")

        if require_pages:
            state = self.root / "state.json"
            state.write_text(json.dumps({"output": str(self.tex), "work_dir": str(self.root)}),
                             encoding="utf-8")
        with patch.object(cli.shutil, "which", side_effect=lambda name:
                          f"/fake/{name}" if name in {"latexmk", "pdfinfo"} else None), \
                patch.object(cli.subprocess, "run", side_effect=run):
            if require_pages:
                return cli.cmd_shrink_stats(SimpleNamespace(
                    state=str(state), baseline=str(self.tex), pages_after=None))
            report = cli._compile_tex(self.tex, 30)
        self.assertEqual(self.source_bytes, self.tex.read_bytes())
        self.assertEqual([], report["project_changes"])
        self.assertFalse(Path(report["isolated_output"]).exists())
        return report

    def test_normal_ascii_page_count(self):
        report = self.probe(b"Title: Example\r\nPages:          12\r\n")
        self.assertTrue(report["pass"])
        self.assertEqual(12, report["pdf_pages"])

    def test_cp936_metadata_does_not_crash_or_hide_page_count(self):
        output = "Title: 中文标题\r\nCreationDate: 星期三\r\nPages: 3\r\n".encode("cp936")
        with self.assertRaises(UnicodeDecodeError):
            output.decode("utf-8")
        report = self.probe(output)
        self.assertTrue(report["pass"])
        self.assertEqual(3, report["pdf_pages"])

    def test_invalid_or_missing_page_count_is_not_verified(self):
        for output in (None, b"", b"Title: \xff\n", b"Pages: 0\n", b"Pages: -1\n",
                       b"Pages: 2.5\n", b"Pages: 1 junk\n", b"Pages: \xff\n",
                       "Pages: ²\n".encode("utf-8")):
            with self.subTest(output=output):
                self.assertIsNone(self.probe(output)["pdf_pages"])
                with self.assertRaisesRegex(RuntimeError, "with a page count is required"):
                    self.probe(output, require_pages=True)

    def test_nonzero_probe_cannot_supply_a_verified_page_count(self):
        self.assertIsNone(self.probe(b"Pages: 9\n", returncode=1)["pdf_pages"])
        with self.assertRaisesRegex(RuntimeError, "with a page count is required"):
            self.probe(b"Pages: 9\n", returncode=1, require_pages=True)

    def test_valid_page_count_does_not_override_compile_failure_or_warning(self):
        for options in ({"compile_returncode": 1},
                        {"log": "LaTeX Warning: There were undefined references"}):
            with self.subTest(options=options):
                report = self.probe(b"Pages: 1\n", **options)
                self.assertEqual(1, report["pdf_pages"])
                self.assertFalse(report["pass"])


if __name__ == "__main__":
    unittest.main()
