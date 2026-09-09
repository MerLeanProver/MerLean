#!/usr/bin/env python3
"""Compatibility release command: build all six agents from a committed Git tree, not worktree."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from audit_codex_release import audit_archive
except ModuleNotFoundError:
    from scripts.audit_codex_release import audit_archive

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = {"src", "workflows", "roles", "ports", "templates", "assets", "scripts", "docs"}
SOURCE_FILES = {"LICENSE", "NOTICE", "PRIVACY.md", "SECURITY.md", "SUPPORT.md", "TERMS.md"}
FORBIDDEN = {".git", ".venv", ".lake", "__pycache__", ".pytest_cache", "tests"}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def materialize(treeish: str, destination: Path) -> None:
    # Works in a standalone checkout and in a nested monorepo.
    prefix = git("rev-parse", "--show-prefix").decode().strip().rstrip("/")
    tree = git("rev-parse", "--verify", f"{treeish}:{prefix}" if prefix else f"{treeish}^{{tree}}").decode().strip()
    records = git("ls-tree", "--full-tree", "-rz", tree).split(b"\0")
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        relative = Path(raw_path.decode())
        if relative.parts[0] not in SOURCE_DIRS and relative.as_posix() not in SOURCE_FILES:
            continue
        if FORBIDDEN.intersection(relative.parts) or relative.suffix in {".pyc", ".olean", ".ilean"}:
            continue
        if any(part.startswith(".env") for part in relative.parts) and relative.as_posix() != "templates/.env.example":
            raise ValueError(f"credential source refused: {relative}")
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError(f"release source must be a regular Git blob: {relative}")
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git("cat-file", "blob", oid))
        path.chmod(0o755 if mode == "100755" else 0o644)
    if not (destination / "scripts/build_bundles.py").is_file():
        raise ValueError("selected Git tree predates the six-agent source layout; use the new local worktree builder until committed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--treeish", default="HEAD")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    output = args.out.resolve()
    with tempfile.TemporaryDirectory(prefix="merlean-git-release-") as temp:
        snapshot = Path(temp) / "source"
        snapshot.mkdir()
        materialize(args.treeish, snapshot)
        subprocess.run([sys.executable, str(snapshot / "scripts/build_bundles.py"),
                        "--out", str(Path(temp) / "plugins"), "--archives", str(output)],
                       cwd=snapshot, check=True)
    expected = [f"{agent}-{provider}" for provider in ("claude", "codex")
                for agent in ("merlean-lite", "merlean-heavy", "paper-writing")]
    errors = []
    for name in expected:
        path = output / f"{name}.zip"
        if not path.is_file():
            errors.append(f"missing archive: {name}")
        else:
            errors.extend(f"{name}: {error}" for error in audit_archive(path, name))
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: six audited archives from Git tree {args.treeish}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
