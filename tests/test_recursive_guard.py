from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex.recursive_writer import (  # noqa: E402
    _archive, _read, _receipt, _write,
)


class RecursiveArtifactGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_normal_reads_receipts_and_atomic_write(self) -> None:
        path = self.root / "state.json"
        _write(path, {"round": 1}, exclusive=True)
        self.assertEqual(_read(path), {"round": 1})
        self.assertEqual(_receipt(path)["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        _write(path, {"round": 2})
        self.assertEqual(_read(path), {"round": 2})
        self.assertFalse(list(self.root.glob(".*.pending-*")))

    def test_interrupted_fixed_pending_does_not_block_fresh_write(self) -> None:
        path = self.root / "state.json"
        orphan = path.with_name(path.name + ".pending")
        orphan.write_text("unknown older interrupted data", encoding="utf-8")
        _write(path, {"round": 1})
        self.assertEqual(_read(path), {"round": 1})
        self.assertEqual(orphan.read_text(), "unknown older interrupted data")

    def test_exclusive_existing_write_preserves_user_bytes(self) -> None:
        path = self.root / "state.json"
        path.write_bytes(b"user data")
        with self.assertRaises(FileExistsError):
            _write(path, {"round": 1}, exclusive=True)
        self.assertEqual(path.read_bytes(), b"user data")

    def test_write_failure_preserves_previous_state_and_cleans_only_owned_stage(self) -> None:
        path = self.root / "state.json"
        _write(path, {"round": 1})
        before = path.read_bytes()
        with patch("paper_writing_codex.recursive_writer.os.fsync", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                _write(path, {"round": 2})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".*.pending-*")))

    def test_concurrent_mutation_during_write_is_preserved(self) -> None:
        path = self.root / "state.json"
        _write(path, {"round": 1})

        def concurrent_write(descriptor: int) -> None:
            path.write_bytes(b"user concurrent change")

        with patch("paper_writing_codex.recursive_writer.os.fsync", side_effect=concurrent_write):
            with self.assertRaisesRegex(ValueError, "changed during"):
                _write(path, {"round": 2})
        self.assertEqual(path.read_bytes(), b"user concurrent change")

    def test_concurrent_creation_does_not_get_overwritten(self) -> None:
        path = self.root / "state.json"

        def concurrent_write(descriptor: int) -> None:
            path.write_bytes(b"user-created file")

        with patch("paper_writing_codex.recursive_writer.os.fsync", side_effect=concurrent_write):
            with self.assertRaises(FileExistsError):
                _write(path, {"round": 1})
        self.assertEqual(path.read_bytes(), b"user-created file")

    def test_hardlinked_artifacts_are_rejected_for_reads_receipts_writes_and_archives(self) -> None:
        path = self.root / "state.json"
        path.write_text('{"value": 1}', encoding="utf-8")
        try:
            os.link(path, self.root / "other.json")
        except OSError as exc:
            self.skipTest(str(exc))
        operations = [lambda: _read(path), lambda: _receipt(path),
                      lambda: _write(path, {"value": 2}),
                      lambda: _archive(self.root / "work", "reviews", path)]
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "unlinked regular"):
                    operation()
        self.assertEqual(json.loads(path.read_text()), {"value": 1})

    def test_symlink_parent_rejected_for_reads_receipts_writes_and_archives(self) -> None:
        owned = self.root / "owned"
        owned.mkdir()
        source = owned / "source.json"
        source.write_text('{"summary": "review"}', encoding="utf-8")
        linked = self.root / "linked"
        try:
            linked.symlink_to(owned, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        for operation in (lambda: _read(linked / source.name),
                          lambda: _receipt(linked / source.name),
                          lambda: _write(linked / "new.json", {"x": 1}),
                          lambda: _archive(linked, "reviews", source)):
            with self.assertRaisesRegex(ValueError, "symlink"):
                operation()
        self.assertEqual(list(owned.iterdir()), [source])

    def test_archive_is_content_addressed_preserves_source_and_emits_readable_view(self) -> None:
        source = self.root / "review.json"
        payload = {"role": "wording", "verdict": "FAIL", "reviewer_id": "independent-1",
                   "summary": "Use consistent terminology.", "findings": [
                       {"id": "W-1", "severity": "required", "location": "Section 1",
                        "evidence": "Two terms name the same concept.", "resolution": "Choose one term."}]}
        source.write_text(json.dumps(payload), encoding="utf-8")
        before = source.read_bytes()
        receipt = _archive(self.root / "work", "reviews", source)
        self.assertEqual(_read(Path(receipt["path"])), payload)
        self.assertEqual(source.read_bytes(), before)
        human = Path(receipt["path"]).with_suffix(".report.md")
        self.assertIn("W-1", human.read_text())
        self.assertIn("Use consistent terminology.", human.read_text())
        self.assertEqual(_archive(self.root / "work", "reviews", source), receipt)

    def test_archive_unsafe_category_or_corrupt_existing_blob_rejected(self) -> None:
        source = self.root / "evidence.txt"
        source.write_text("source evidence", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "category"):
            _archive(self.root / "work", "../outside", source)
        receipt = _archive(self.root / "work", "reviews", source)
        target = Path(receipt["path"])
        target.write_text("tampered archive", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed during archival"):
            _archive(self.root / "work", "reviews", source)
        self.assertEqual(target.read_text(), "tampered archive")


if __name__ == "__main__":
    unittest.main()
