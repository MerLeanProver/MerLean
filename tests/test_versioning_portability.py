from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex.versioning import (  # noqa: E402
    _set_owned_staging_times, atomic_rename_noreplace, exclusive_copy,
)


class VersioningPortabilityTests(unittest.TestCase):
    def test_exclusive_copy_preserves_bytes_timestamp_and_permission_bits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.tex"
            destination = Path(directory) / "paper-v1.tex"
            data = b"\\documentclass{article}\r\n% retain CRLF and \x1a byte\r\n"
            source.write_bytes(data)
            stamp = 1700000000123456700
            os.utime(source, ns=(stamp, stamp))
            source_info = source.stat()
            receipt = exclusive_copy(source, destination)
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(destination.read_bytes(), data)
            self.assertEqual(receipt["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(destination.stat().st_mtime_ns, source_info.st_mtime_ns)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), stat.S_IMODE(source_info.st_mode))

    def test_timestamp_path_fallback_operates_only_on_owned_inode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor, name = tempfile.mkstemp(dir=directory)
            try:
                path = Path(name)
                stamp = 1700000000000000000
                with patch("paper_writing_codex.versioning.os.supports_fd", set()):
                    _set_owned_staging_times(descriptor, path, (stamp, stamp))
                self.assertEqual(path.stat().st_mtime_ns, stamp)
                other = Path(directory) / "unowned"
                other.write_bytes(b"user data")
                before = other.stat().st_mtime_ns
                with patch("paper_writing_codex.versioning.os.supports_fd", set()):
                    with self.assertRaisesRegex(RuntimeError, "owned snapshot"):
                        _set_owned_staging_times(descriptor, other, (stamp, stamp))
                self.assertEqual(other.read_bytes(), b"user data")
                self.assertEqual(other.stat().st_mtime_ns, before)
            finally:
                os.close(descriptor)

    def test_no_replace_rename_preserves_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "staging"
            destination = Path(directory) / "published"
            source.write_bytes(b"new")
            destination.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                atomic_rename_noreplace(source, destination)
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(destination.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
