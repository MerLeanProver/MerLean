from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex.writing_snapshot import (  # noqa: E402
    diff_snapshots, snapshot_sources, verify_snapshot,
)


class WritingSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()

    def write(self, relative: str, content: str | bytes) -> Path:
        path = self.sources / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def snapshot(self, roots: list[Path], name: str = "snapshot") -> dict:
        return snapshot_sources(roots, self.root / name)

    def test_complete_tex_closure_without_toolchain_or_execution(self) -> None:
        paper = self.write("paper.tex", r"""\documentclass{custom}
\usepackage{amsmath,local}
\graphicspath{{figures/}}
\input{section}
\begin{document}
\includegraphics{plot}
\includepdf{appendix}
\lstinputlisting{code.py}
\bibliography{references}
\bibliographystyle{house}
\end{document}
""")
        data = {
            "custom.cls": r"\LoadClass{article}",
            "local.sty": r"\input{macros.def}",
            "macros.def": r"\newcommand{\capvalue}{3}",
            "section.tex": r"\input{nested/detail}",
            "nested/detail.tex": "A theorem with conditions.",
            "references.bib": "@article{a,title={A}}",
            "house.bst": "ENTRY {} {} {}",
            "figures/plot.png": b"\x89PNG\x00test",
            "figures/plot.pdf": b"%PDF-test\x00",
            "appendix.pdf": b"%PDF-test\x00",
            "code.py": "raise AssertionError('must never execute')",
        }
        for name, content in data.items():
            self.write(name, content)
        before = {path: path.read_bytes() for path in self.sources.rglob("*") if path.is_file()}
        snapshot = self.snapshot([paper])
        self.assertEqual({row["relative"] for row in snapshot["files"]}, {"paper.tex", *data})
        self.assertEqual(verify_snapshot(snapshot, check_originals=True), [])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_markdown_explicit_evidence_links_and_no_repository_scan(self) -> None:
        notes = self.write("notes.md", """# Notes
[proof](proof.lean) ![figure](figure.png)
[table][data]
[other](<other note.md>)
[remote](https://example.org/not-downloaded.tex)
[anchor](#result)
[data]: table.csv
```python
[example](missing.py)
```
""")
        for name in ("proof.lean", "figure.png", "table.csv", "other note.md", "unrelated.secret"):
            self.write(name, "evidence")
        snapshot = self.snapshot([notes])
        self.assertEqual({row["relative"] for row in snapshot["files"]}, {"notes.md", "proof.lean", "figure.png", "table.csv", "other note.md"})

    def test_relative_sibling_dependencies_remain_usable(self) -> None:
        root = self.write("paper/main.tex", r"\input{../shared/macros}")
        self.write("shared/macros.tex", "Shared assumptions")
        snapshot = self.snapshot([root])
        frozen_root = Path(snapshot["roots"][0]["snapshot"])
        self.assertEqual((frozen_root.parent / "../shared/macros.tex").read_text(), "Shared assumptions")
        self.assertEqual(verify_snapshot(snapshot), [])

    def test_digest_is_independent_of_source_and_snapshot_locations(self) -> None:
        root = self.write("paper.tex", r"\input{child}")
        self.write("child.tex", "A result")
        first = self.snapshot([root], "first")
        relocated = self.root / "relocated"
        shutil.copytree(self.sources, relocated)
        second = self.snapshot([relocated / "paper.tex"], "second")
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(diff_snapshots(first, second)["changes"], [])

    def test_missing_dependencies_fail_before_publication(self) -> None:
        for text in (r"\input{absent}", r"\usepackage{local/absent}", r"\includegraphics{absent}", r"\bibliography{absent}"):
            with self.subTest(text=text):
                root = self.write("paper.tex", text)
                with self.assertRaisesRegex(ValueError, "missing local dependency"):
                    self.snapshot([root])
                self.assertFalse((self.root / "snapshot").exists())

    def test_dynamic_and_absolute_dependencies_fail_closed(self) -> None:
        other = self.write("other.tex", "existing file")
        for target in (r"\macro/name", "#1", str(other).replace("\\", "/")):
            with self.subTest(target=target):
                root = self.write("paper.tex", "\\input{" + target + "}")
                with self.assertRaises(ValueError):
                    self.snapshot([root])

    def test_nested_dynamic_dependency_syntax_cannot_silently_disappear(self) -> None:
        for text in (r"\input{\makepath{source}}", r"\includegraphics{\image{plot}}", r"\graphicspath{\customdirs}"):
            with self.subTest(text=text):
                root = self.write("paper.tex", text)
                with self.assertRaisesRegex(ValueError, "unsupported dependency syntax"):
                    self.snapshot([root])

    def test_extra_assets_change_digest_and_binary_not_in_diff(self) -> None:
        root = self.write("paper.tex", r"\includegraphics{image.png}")
        self.write("image.png", b"\x89PNG\x00first")
        first = self.snapshot([root], "first")
        self.write("image.png", b"\x89PNG\x00second")
        second = self.snapshot([root], "second")
        self.assertNotEqual(first["digest"], second["digest"])
        result = diff_snapshots(first, second)
        self.assertEqual(result["modified"], ["image.png"])
        self.assertEqual(result["text_diffs"], {})

    def test_diff_has_added_removed_and_modified_utf8_text(self) -> None:
        root = self.write("paper.tex", "\\input{old}\nFirst text.\n")
        self.write("old.tex", "Old supporting result.\n")
        first = self.snapshot([root], "first")
        self.write("paper.tex", "\\input{new}\nRevised text.\n")
        self.write("new.tex", "New supporting result.\n")
        second = self.snapshot([root], "second")
        diff = diff_snapshots(first, second)
        self.assertEqual(diff["added"], ["new.tex"])
        self.assertEqual(diff["removed"], ["old.tex"])
        self.assertEqual(diff["modified"], ["paper.tex"])
        self.assertIn("-First text.", diff["text_diffs"]["paper.tex"])
        self.assertIn("+Revised text.", diff["text_diffs"]["paper.tex"])

    def test_original_drift_is_optional_but_snapshot_drift_is_always_rejected(self) -> None:
        root = self.write("notes.md", "Original")
        snapshot = self.snapshot([root])
        root.write_text("New source", encoding="utf-8")
        self.assertEqual(verify_snapshot(snapshot), [])
        self.assertTrue(any("original content changed" in error for error in verify_snapshot(snapshot, True)))
        Path(snapshot["roots"][0]["snapshot"]).write_text("Tampered snapshot", encoding="utf-8")
        self.assertTrue(any("snapshot content changed" in error for error in verify_snapshot(snapshot)))

    def test_dependency_macro_change_visible_even_if_root_unchanged(self) -> None:
        root = self.write("paper.tex", r"\usepackage{local}\begin{document}$n\ge\value$\end{document}")
        self.write("local.sty", r"\newcommand{\value}{2}")
        first = self.snapshot([root], "first")
        self.write("local.sty", r"\newcommand{\value}{3}")
        second = self.snapshot([root], "second")
        self.assertEqual(diff_snapshots(first, second)["modified"], ["local.sty"])

    def test_new_local_package_shadowing_installed_package_is_source_drift(self) -> None:
        root = self.write("paper.tex", r"\documentclass{article}\usepackage{amsmath}")
        snapshot = self.snapshot([root])
        self.write("amsmath.sty", "A newly introduced local package")
        self.assertEqual(verify_snapshot(snapshot), [])
        self.assertTrue(any("closure changed" in error for error in verify_snapshot(snapshot, True)))

    def test_existing_destination_is_untouched(self) -> None:
        root = self.write("notes.md", "Original")
        destination = self.root / "snapshot"
        destination.mkdir()
        marker = destination / "user-data"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.snapshot([root])
        self.assertEqual(marker.read_text(), "keep")

    def test_racing_destination_is_preserved(self) -> None:
        root = self.write("notes.md", "Original")
        destination = self.root / "snapshot"

        def race(source: Path, target: Path) -> None:
            target.mkdir()
            (target / "user-data").write_text("keep", encoding="utf-8")
            raise FileExistsError(target)

        primitive = "os.rename" if os.name == "nt" else "atomic_rename_noreplace"
        with patch("paper_writing_codex.writing_snapshot." + primitive, side_effect=race):
            with self.assertRaises(FileExistsError):
                self.snapshot([root])
        self.assertEqual((destination / "user-data").read_text(), "keep")
        self.assertFalse(list(self.root.glob(".snapshot.snapshot-*")))

    def test_symlink_source_and_parent_rejected(self) -> None:
        root = self.write("notes.md", "Original")
        link = self.root / "link.md"
        try:
            link.symlink_to(root)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.snapshot([link])
        parent = self.root / "linked-directory"
        parent.symlink_to(self.sources, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.snapshot([parent / "notes.md"])

    def test_unreceipted_file_or_unsafe_manifest_is_rejected(self) -> None:
        root = self.write("notes.md", "Original")
        snapshot = self.snapshot([root])
        (Path(snapshot["destination"]) / "content" / "new.sty").write_text("malicious macro", encoding="utf-8")
        self.assertTrue(any("unreceipted" in error for error in verify_snapshot(snapshot)))
        bad = copy.deepcopy(snapshot)
        bad["files"][0]["relative"] = "../notes.md"
        self.assertTrue(any("unsafe" in error for error in verify_snapshot(bad)))

    def test_snapshot_hardlinks_are_rejected(self) -> None:
        root = self.write("notes.md", "Original")
        snapshot = self.snapshot([root])
        try:
            os.link(snapshot["roots"][0]["snapshot"], self.root / "external-link.md")
        except OSError as exc:
            self.skipTest(f"hard link creation unavailable: {exc}")
        self.assertTrue(any("hard link" in error for error in verify_snapshot(snapshot)))

    def test_directory_source_is_not_recursively_ingested(self) -> None:
        self.write("notes.md", "A note")
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            self.snapshot([self.sources])

    def test_cycles_are_bounded_and_all_files_preserved(self) -> None:
        root = self.write("first.tex", r"\input{second}")
        self.write("second.tex", r"\input{first}")
        snapshot = self.snapshot([root])
        self.assertEqual(len(snapshot["files"]), 2)
        self.assertEqual(len(snapshot["edges"]), 2)

    def test_tex_links_and_comments(self) -> None:
        root = self.write("paper.tex", r"""% \input{missing}
\href{evidence.json}{Data}
\href{https://example.org/absent}{Online}
""")
        self.write("evidence.json", '{"status":"proof_available"}')
        snapshot = self.snapshot([root])
        self.assertEqual(len(snapshot["files"]), 2)

    def test_graphicspath_defined_in_local_package(self) -> None:
        root = self.write("paper.tex", r"\usepackage{local}\includegraphics{plot}")
        self.write("local.sty", r"\graphicspath{{images/}}")
        self.write("images/plot.png", b"\x89PNG\x00")
        self.assertEqual(len(self.snapshot([root])["files"]), 3)

    def test_empty_sources_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.snapshot([])


if __name__ == "__main__":
    unittest.main()
