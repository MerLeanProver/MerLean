#!/usr/bin/env python3
"""Build deterministic skills-only portal archives from one Git tree, never the worktree."""

from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "lite-codex": Path("research-agent/codex"),
    "paper-writing-codex": Path("paper-writing-agent/codex"),
}
POLICY_FILES = ["PRIVACY.md", "TERMS.md", "SUPPORT.md", "SECURITY.md"]


def git(*args: str, text: bool = False) -> bytes | str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=text)


def tree_files(treeish: str) -> list[str]:
    return [line for line in git("ls-tree", "-r", "--name-only", treeish, text=True).splitlines() if line]


def blob(treeish: str, path: str) -> bytes:
    return git("show", f"{treeish}:{path}")


def write_zip(treeish: str, name: str, source: Path, output: Path) -> None:
    prefix = source.as_posix().rstrip("/") + "/"
    selected = [path for path in tree_files(treeish) if path.startswith(prefix)]
    if not selected:
        raise SystemExit(f"no tracked plugin files under {source} at {treeish}")

    entries: dict[str, bytes] = {}
    for path in selected:
        relative = path[len(prefix):]
        if relative in {".env", ".mcp.json"}:
            continue
        if any(part in {".venv", ".lake", "__pycache__", ".pytest_cache"}
               for part in Path(relative).parts):
            continue
        entries[relative] = blob(treeish, path)

    manifest_path = ".codex-plugin/plugin.json"
    manifest = json.loads(entries[manifest_path])
    manifest.pop("mcpServers", None)
    entries[manifest_path] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()

    available = set(tree_files(treeish))
    for policy in POLICY_FILES:
        if policy in available:
            entries[policy] = blob(treeish, policy)
    for logo in ["assets/merlean-logo.svg", "assets/merlean-logo.png"]:
        if logo in available:
            entries[logo] = blob(treeish, logo)

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(entries.items()):
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if relative.startswith("scripts/") else 0o644) << 16
            archive.writestr(info, data)

    print(f"built {name}: {output} ({output.stat().st_size} bytes, {len(entries)} files)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--treeish", default="HEAD")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()

    git("rev-parse", "--verify", f"{args.treeish}^{{tree}}")
    for name, source in PACKAGES.items():
        manifest = json.loads(blob(args.treeish, f"{source}/.codex-plugin/plugin.json"))
        version = manifest["version"].split("+", 1)[0]
        output = args.out / f"{name}-{version}-skills-only.zip"
        write_zip(args.treeish, name, source, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
