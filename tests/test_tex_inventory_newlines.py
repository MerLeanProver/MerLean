"""Paragraph coverage must preserve byte evidence across source line endings."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paper_writing_codex.coverage import audit_refinement, lock_main_results
from paper_writing_codex.tex_inventory import inventory_tex
from paper_writing_codex.workflow import init_refine


class TexInventoryNewlineTests(unittest.TestCase):
    def source_text(self, endings, trailing=""):
        lines = [r"\documentclass{article}", r"\newtheorem{theorem}{Theorem}",
                 r"\begin{document}", r"\section{Introduction}",
                 "First explanatory line", "continues here.", "",
                 "Only for $n>0$.", "",
                 r"\begin{theorem}\label{thm:main}",
                 "$n=n$. % exact comment bytes", r"\end{theorem}",
                 r"\end{document}"]
        return "".join(line + trailing + endings[index % len(endings)]
                       for index, line in enumerate(lines))

    def variants(self):
        for endings in (("\n",), ("\r\n",), ("\r\n", "\n")):
            for trailing in ("", " \t"):
                yield endings, trailing

    def test_paragraphs_lines_and_verbatim_hashes_preserve_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            for endings, trailing in self.variants():
                with self.subTest(endings=endings, trailing=trailing):
                    text = self.source_text(endings, trailing)
                    data = text.encode("utf-8")
                    source.write_bytes(data)
                    inventory = inventory_tex(source)
                    prose = [unit for unit in inventory["units"] if unit["kind"] == "prose"]
                    self.assertEqual(["First explanatory line continues here.", "Only for $n>0$."],
                                     [unit["normalized_text"] for unit in prose])
                    self.assertEqual([5, 8], [unit["line"] for unit in prose])
                    expected_raw = "First explanatory line" + trailing + endings[4 % len(endings)] + "continues here."
                    self.assertEqual(expected_raw, prose[0]["raw_text"])
                    self.assertEqual("Only for $n>0$.", prose[1]["raw_text"])
                    statement = next(unit for unit in inventory["units"] if unit["kind"] == "statement")
                    start = text.index(r"\begin{theorem}")
                    end = text.index(r"\end{theorem}") + len(r"\end{theorem}")
                    self.assertEqual(text[start:end], statement["raw_text"])
                    self.assertEqual(10, statement["line"])
                    for unit in [*prose, statement]:
                        self.assertEqual(hashlib.sha256(unit["raw_text"].encode("utf-8")).hexdigest(),
                                         unit["raw_sha256"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), inventory["source_sha256"])
                    self.assertEqual(data, source.read_bytes())

    def test_caveat_removal_fails_its_own_prose_coverage_obligation(self):
        for endings, trailing in self.variants():
            with self.subTest(endings=endings, trailing=trailing), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "paper.tex"
                text = self.source_text(endings, trailing)
                data = text.encode("utf-8")
                source.write_bytes(data)
                caveat = next(unit for unit in inventory_tex(source)["units"]
                              if unit["kind"] == "prose" and unit["normalized_text"] == "Only for $n>0$.")
                state = init_refine(source)
                state_path = Path(state["work_dir"]) / "00-run-state.json"
                lock_main_results(state_path, ["thm:main"])
                self.assertTrue(audit_refinement(state_path)["pass"])
                Path(state["output"]).write_bytes(text.replace("Only for $n>0$.", "").encode("utf-8"))
                report = audit_refinement(state_path)
                self.assertFalse(report["pass"])
                self.assertIn(f"{caveat['id']}: changed or missing but still classified auto", report["errors"])
                self.assertEqual(data, source.read_bytes())

    def test_final_paragraph_without_document_wrapper_or_blank_line(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fragment.tex"
            for ending in ("", "\n", "\r\n", " \t\r\n"):
                with self.subTest(ending=ending):
                    source.write_bytes(("Only for $n>0$." + ending).encode("utf-8"))
                    prose = [unit for unit in inventory_tex(source)["units"] if unit["kind"] == "prose"]
                    self.assertEqual(["Only for $n>0$."], [unit["raw_text"] for unit in prose])


if __name__ == "__main__":
    unittest.main()
