#!/usr/bin/env python3
"""Generate six standalone agents from one maintained source tree; never install or push."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

try:
    from catalogs import write_catalogs
except ModuleNotFoundError:
    from scripts.catalogs import write_catalogs

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ("merlean-lite", "merlean-heavy", "paper-writing")
PROVIDERS = ("claude", "codex")
VERSION = "2.0.0"
SOURCE_DIRS = ("src", "workflows", "roles", "ports", "templates", "assets")
SOURCE_FILES = (
    "LICENSE", "NOTICE", "PRIVACY.md", "SECURITY.md", "SUPPORT.md", "TERMS.md",
    "docs/trust-and-instantiation-gates.md", "docs/research-to-paper-synthesis.md", "docs/recursive-writer.md",
    "scripts/merlean", "scripts/merlean-agent",
    "scripts/paperctl", "scripts/setup.sh", "scripts/audit_research_grade.py",
    "scripts/audit-research-grade",
)
EXCLUDED_PARTS = {".git", ".venv", ".lake", "__pycache__", ".pytest_cache", "tests"}
RECEIPT = ".merlean-generated.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_entries(root: Path) -> dict[str, tuple[bytes, int]]:
    paths = [root / path for path in SOURCE_FILES]
    for directory in SOURCE_DIRS:
        paths.extend(path for path in (root / directory).rglob("*") if path.is_file())
    entries = {}
    for path in paths:
        relative = path.relative_to(root)
        if EXCLUDED_PARTS.intersection(relative.parts) or path.suffix in {".pyc", ".olean", ".ilean"}:
            continue
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise ValueError(f"source must be an in-tree regular file: {relative}")
        if path.name.startswith(".env") and relative.as_posix() != "templates/.env.example":
            raise ValueError(f"credential file refused: {relative}")
        entries[relative.as_posix()] = (path.read_bytes(), 0o755 if os.access(path, os.X_OK) else 0o644)
    return entries


def bundle_entries(provider: str, agent: str, root: Path = ROOT) -> dict[str, tuple[bytes, int]]:
    if provider not in PROVIDERS or agent not in AGENTS:
        raise ValueError("unknown provider or agent")
    entries = source_entries(root)
    name = f"{agent}-{provider}"
    description = {
        "merlean-lite": "Default NL-first mathematical research to Silver; targeted Lean checks.",
        "merlean-heavy": "Full proving and supplied-proof formalization to strictly audited Gold.",
        "paper-writing": "Synthesize research notes; compose, refine, resume, and audit papers with preserved evidence.",
    }[agent]
    manifest = {
        "name": name, "version": VERSION, "description": description,
        "author": {"name": "Jinzheng Li, Zeru Zhu, and Yuanjie Ren", "url": "https://github.com/MerLeanProver"},
        "homepage": "https://github.com/MerLeanProver/MerLean",
        "repository": "https://github.com/MerLeanProver/MerLean", "license": "Apache-2.0",
        "keywords": ["mathematics", "lean4", "formalization", "research"],
    }
    if provider == "codex":
        manifest.update({"skills": "./skills/", "interface": {
            "displayName": agent.replace("-", " ").title(), "shortDescription": description,
            "longDescription": description, "developerName": "MerLeanProver",
            "category": "Productivity", "capabilities": ["Research", "Write"],
            "websiteURL": "https://github.com/MerLeanProver/MerLean",
            "privacyPolicyURL": "https://github.com/MerLeanProver/MerLean/blob/main/PRIVACY.md",
            "termsOfServiceURL": "https://github.com/MerLeanProver/MerLean/blob/main/TERMS.md",
            "composerIcon": "./assets/merlean-logo.png", "logo": "./assets/merlean-logo.png",
            "defaultPrompt": [f"Use ${agent} for this mathematics task."],
        }})
    entries[f".{provider}-plugin/plugin.json"] = ((json.dumps(manifest, indent=2) + "\n").encode(), 0o644)
    template = (root / "workflows" / f"{agent}.md").read_text()
    if not template.startswith("---\n") or "\n---\n" not in template[4:]:
        raise ValueError(f"public agent template lacks frontmatter: {agent}")
    front, body = template[4:].split("\n---\n", 1)
    prefix = (
        f"\nProvider: `{provider}`. Resolve `<PLUGIN_ROOT>` as this installed file's third parent "
        "(`skills/<name>/SKILL.md` → package root). Read the following two files completely "
        f"before acting: `<PLUGIN_ROOT>/ports/{provider}.md` and "
        "`<PLUGIN_ROOT>/workflows/common.md`. Internal references inherit that root.\n\n"
    )
    skill = ("---\n" + front + "\n---\n" + prefix + body).replace("<provider>", provider)
    entries[f"skills/{agent}/SKILL.md"] = (skill.encode(), 0o644)
    if provider == "codex":
        ui = (
            "interface:\n"
            f"  display_name: {json.dumps(agent.replace('-', ' ').title())}\n"
            f"  short_description: {json.dumps(description[:64])}\n"
            f"  default_prompt: {json.dumps('Use $' + agent + ' for this mathematics task.')}\n"
        )
        entries[f"skills/{agent}/agents/openai.yaml"] = (ui.encode(), 0o644)
    entries["AGENTS.md"] = ((
        f"# {name}\n\nThis generated package exposes only `{agent}`. Read "
        f"`skills/{agent}/SKILL.md`, `ports/{provider}.md`, and `workflows/common.md`.\n"
        "Internal workflows and specialist roles are not additional public agents.\n"
        "Lite is the fresh research default; Heavy requires explicit selection/full formalization.\n"
        "Never push, install plugins, or change user-wide configuration without authorization.\n"
    ).encode(), 0o644)
    entries["README.md"] = ((
        f"# {name}\n\n{description}\n\n"
        f"Entrypoint: `skills/{agent}/SKILL.md`. Provider: `{provider}`.\n"
        "Generated from the shared MerLean source; edit that source, not this bundle.\n"
        "Setup: `bash scripts/setup.sh --project <Lean-project>`. For read-only plugin caches "
        "use `--runtime <writable-directory>` and the same `MERLEAN_RUNTIME` on later calls.\n"
        "Offline graph: `PLAN_OFFLINE=1 scripts/merlean --data <data> status`. "
        "Paper operations: `scripts/paperctl --help`. Grades are evidence-based, not mode labels.\n"
    ).encode(), 0o644)
    return entries


def verify_generated(path: Path) -> None:
    """Refuse to overwrite unknown outputs, local edits, credentials, or runtime state."""
    receipt_path = path / RECEIPT
    if (path.is_symlink() or not path.is_dir() or not receipt_path.is_file()
            or receipt_path.is_symlink() or receipt_path.stat().st_nlink != 1):
        raise ValueError(f"not a generated bundle: {path}")
    receipt = json.loads(receipt_path.read_text())
    expected = receipt.get("files", {})
    # The first local format omitted directory metadata. Its builder created only
    # these parents with mode 0755; refuse extra directories or altered permissions.
    legacy_dirs = {".": 0o755}
    for name in expected:
        legacy_dirs.update({parent.as_posix(): 0o755 for parent in Path(name).parents})
    expected_dirs = receipt.get("directories", legacy_dirs)
    actual_dirs = {".": path, **{p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_dir()}}
    if set(actual_dirs) != set(expected_dirs):
        raise ValueError(f"extra/missing local directories preserved: {path}")
    for name, directory in actual_dirs.items():
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != expected_dirs[name]:
            raise ValueError(f"locally modified generated directory preserved: {directory}")
    actual = {p.relative_to(path).as_posix(): p for p in path.rglob("*") if p.is_file() or p.is_symlink()}
    if set(actual) != set(expected) | {RECEIPT}:
        raise ValueError(f"extra/missing local files; preserve or move this bundle before rebuilding: {path}")
    for name, info in expected.items():
        p = actual[name]
        if p.is_symlink() or digest(p.read_bytes()) != info["sha256"] or stat.S_IMODE(p.stat().st_mode) != info["mode"]:
            raise ValueError(f"locally modified generated file preserved: {p}")


def build_bundle(provider: str, agent: str, out: Path, root: Path = ROOT) -> Path:
    """Create out/<agent>-<provider>; replace only unchanged, receipt-verified generated files."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    destination = out / f"{agent}-{provider}"
    entries = bundle_entries(provider, agent, root)
    if destination.exists() or destination.is_symlink():
        verify_generated(destination)
    with tempfile.TemporaryDirectory(prefix=".merlean-build-", dir=out) as scratch:
        stage = Path(scratch) / "next"
        stage.mkdir()
        receipt = {"schema_version": 1, "package": destination.name, "files": {}, "directories": {}}
        for name, (data, mode) in sorted(entries.items()):
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
            receipt["files"][name] = {"sha256": digest(data), "mode": mode}
        for directory in [stage, *[p for p in stage.rglob("*") if p.is_dir()]]:
            directory.chmod(0o755)
            receipt["directories"][directory.relative_to(stage).as_posix()] = 0o755
        (stage / RECEIPT).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        previous = Path(scratch) / "previous"
        if destination.exists():
            # Recheck after construction before the only replacement operation.
            verify_generated(destination)
            destination.rename(previous)
        try:
            stage.rename(destination)
        except BaseException:
            if previous.exists() and not destination.exists():
                previous.rename(destination)
            raise
    return destination


def write_archive(package: Path, output: Path) -> None:
    verify_generated(package)
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if not path.is_file():
                continue
            entry = zipfile.ZipInfo(path.relative_to(package).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
            archive.writestr(entry, path.read_bytes())
    payload = buffer.getvalue()
    if output.exists() or output.is_symlink():
        if output.is_symlink() or not output.is_file() or output.stat().st_nlink != 1:
            raise ValueError(f"unsafe existing archive preserved: {output}")
        if output.read_bytes() == payload:
            return  # identical deterministic build, no write
        raise ValueError(f"existing archive differs; choose a new output directory: {output}")
    # Exclusive publication never follows a raced symlink or truncates an existing file.
    with tempfile.TemporaryDirectory(prefix=".merlean-archive-", dir=output.parent) as temporary:
        staged = Path(temporary) / "archive.zip"
        staged.write_bytes(payload)
        os.link(staged, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "plugins")
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--catalogs", action="store_true",
                        help="generate local catalogs alongside plugins; never register or install")
    args = parser.parse_args()
    for provider in PROVIDERS:
        for agent in AGENTS:
            package = build_bundle(provider, agent, args.out)
            if args.archives:
                write_archive(package, args.archives / f"{package.name}.zip")
            print(package)
    if args.catalogs:
        for path in write_catalogs(args.out):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
