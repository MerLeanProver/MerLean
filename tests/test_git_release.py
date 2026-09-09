"""A release uses the frozen Git tree, including when maintained inside a monorepo."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.build_bundles import source_entries

ROOT = Path(__file__).resolve().parents[1]


class GitReleaseTests(unittest.TestCase):
    def test_monorepo_tree_release_ignores_dirty_worktree_and_is_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="merlean-release-test-") as temporary:
            base = Path(temporary)
            gitroot = base / "repo"
            source = gitroot / "MerLeanProver"
            source.mkdir(parents=True)
            entries = source_entries(ROOT)
            for path in ("scripts/build_bundles.py", "scripts/build_codex_release.py",
                         "scripts/audit_codex_release.py", "scripts/catalogs.py"):
                entries[path] = ((ROOT / path).read_bytes(), 0o755)
            for relative, (body, mode) in entries.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                path.chmod(mode)
            env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
                       PYTHONDONTWRITEBYTECODE="1")
            for args in [("init",), ("add", "."), ("commit", "-m", "Frozen test source")]:
                subprocess.run(["git", *args], cwd=gitroot, env=env, check=True,
                               capture_output=True, text=True)
            frozen = (source / "workflows/common.md").read_bytes()
            (source / "workflows/common.md").write_text("UNCOMMITTED: must never ship")
            hashes = []
            for i in (1, 2):
                out = base / f"release-{i}"
                run = subprocess.run([sys.executable, str(source / "scripts/build_codex_release.py"),
                                      "--treeish", "HEAD", "--out", str(out)],
                                     cwd=source, env=env, text=True, capture_output=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                archives = sorted(out.glob("*.zip"))
                self.assertEqual(len(archives), 6)
                for path in archives:
                    with zipfile.ZipFile(path) as archive:
                        self.assertEqual(archive.read("workflows/common.md"), frozen)
                hashes.append([hashlib.sha256(path.read_bytes()).hexdigest() for path in archives])
            self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
