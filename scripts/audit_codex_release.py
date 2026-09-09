#!/usr/bin/env python3
"""Audit standalone MerLEAN bundles and safely smoke-test release archives."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ("merlean-lite", "merlean-heavy", "paper-writing")
PROVIDERS = ("codex", "claude")
PACKAGE_NAMES = tuple(f"{agent}-{provider}" for provider in PROVIDERS for agent in AGENTS)
RESEARCH_ARCHIVE_REQUIRED = {
    "scripts/audit-research-grade",
    "scripts/audit_research_grade.py",
    "scripts/merlean",
    "scripts/merlean-agent",
    "scripts/paperctl",
    "scripts/setup.sh",
    "src/research_grade.py",
    "src/plan_store/grade_policy.py",
    "src/cli.py",
    "src/offline_cli.py",
    "src/paper_writing_codex/__init__.py",
    "docs/trust-and-instantiation-gates.md",
    "LICENSE", "NOTICE", "PRIVACY.md", "TERMS.md", "SUPPORT.md", "SECURITY.md",
    "README.md", "AGENTS.md", "workflows/common.md",
}

FORBIDDEN_NAMES = {".env", ".netrc", ".npmrc", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
FORBIDDEN_PARTS = {".venv", ".lake", "__pycache__", ".pytest_cache", ".git"}
SECRET_PATTERNS = {
    "private-key block": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "OpenAI-style secret": re.compile(r"\bsk-(?!\.\.\.|your-key-here)[A-Za-z0-9_-]{12,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "absolute macOS home": re.compile(r"/" + r"Users/[^/\s]+/"),
    "absolute Linux home": re.compile(r"/" + r"home/[^/\s]+/"),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
}


def scan_payload(relative: str, payload: bytes) -> list[str]:
    failures: list[str] = []
    path = PurePosixPath(relative)
    lower_parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        failures.append(f"forbidden credential filename: {relative}")
    if lower_parts & FORBIDDEN_PARTS:
        failures.append(f"generated/runtime path is packaged: {relative}")
    if len(payload) > 10_000_000:
        failures.append(f"unexpected packaged file over 10 MB: {relative}")
        return failures
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return failures
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            failures.append(f"{label}: {relative}")
    return failures


def _references(entries: dict[str, bytes], manifest: dict) -> list[str]:
    """Resolve concrete local manifest and plugin-root documentation references."""
    failures = []

    def exists(value):
        value = value.removeprefix("./").rstrip("/")
        return value in entries or any(name.startswith(value + "/") for name in entries)

    def check(value):
        if isinstance(value, dict):
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
        elif isinstance(value, str) and value.startswith("./"):
            if ".." in PurePosixPath(value).parts or not exists(value):
                failures.append(f"unresolved manifest reference: {value}")

    check(manifest)
    for name, payload in entries.items():
        if not name.endswith(".md"):
            continue
        text = payload.decode("utf-8", "replace")
        if name.startswith("skills/"):
            for ref in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
                ref = ref.split("#", 1)[0]
                if not ref or ":" in ref or any(char in ref for char in "<>{}$*"):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), ref))
                if target.startswith("../") or target.startswith("/") or not exists(target):
                    failures.append(f"unresolved public skill link in {name}: {ref}")
        for ref in re.findall(r"(?:<PLUGIN_ROOT>|\$\{CLAUDE_PLUGIN_ROOT\})/([^\s`\"'<>\)\]]+)", text):
            ref = ref.rstrip(".,;:").split("#", 1)[0]
            # The installer creates these interpreters; runtime venvs must not ship.
            if ref in {".venv/bin/python", ".venv/bin/python3", ".venv/Scripts/python.exe"}:
                continue
            if any(char in ref for char in "{}*$"):
                continue
            if ".." in PurePosixPath(ref).parts or not exists(ref):
                failures.append(f"unresolved plugin reference in {name}: {ref}")
    return failures


def audit_archive(path: Path, package_name: str) -> list[str]:
    """Inspect a bundle, refusing extraction or execution after any audit failure."""
    if package_name not in PACKAGE_NAMES:
        return [f"unknown package name: {package_name}"]
    agent, provider = package_name.rsplit("-", 1)
    failures = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"cannot open archive {path}: {exc}"]
    with archive:
        entries = {}
        seen = set()
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            normalized = member.as_posix().rstrip("/")
            if (member.is_absolute() or ".." in member.parts or "\\" in info.filename
                    or re.match(r"^[A-Za-z]:", info.filename) or not normalized):
                failures.append(f"unsafe archive entry {info.filename}")
                continue
            if normalized in seen:
                failures.append(f"duplicate archive entries: {info.filename}")
                continue
            seen.add(normalized)
            if stat.S_ISLNK(info.external_attr >> 16):
                failures.append(f"unsafe archive symlink {info.filename}")
                continue
            if info.file_size > 10_000_000:
                failures.append(f"unexpected packaged file over 10 MB: {info.filename}")
                continue
            if info.is_dir():
                continue
            try:
                payload = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                failures.append(f"unreadable archive entry {info.filename}: {exc}")
                continue
            entries[normalized] = payload
            failures.extend(scan_payload(normalized, payload))
        for name in entries:
            if any(parent.as_posix() in entries for parent in PurePosixPath(name).parents):
                failures.append(f"unsafe archive file/directory collision: {name}")
        manifest_path = f".{provider}-plugin/plugin.json"
        required = RESEARCH_ARCHIVE_REQUIRED | {manifest_path, f"skills/{agent}/SKILL.md", f"ports/{provider}.md"}
        for missing in sorted(required - entries.keys()):
            failures.append(f"missing required research runtime file {missing}")
        skills = {name for name in entries if name.startswith("skills/") and name.endswith("/SKILL.md")}
        if skills != {f"skills/{agent}/SKILL.md"}:
            failures.append(f"public skill mismatch: expected only {agent}; found {sorted(skills)}")
        skill = entries.get(f"skills/{agent}/SKILL.md", b"").decode("utf-8", "replace")
        frontmatter = skill.split("---", 2)
        if not skill.startswith("---\n") or len(frontmatter) < 3:
            failures.append("public skill is missing YAML frontmatter")
        elif not re.search(r"^name:\s*[\"']?" + re.escape(agent) + r"[\"']?\s*$", frontmatter[1], re.MULTILINE):
            failures.append(f"public skill frontmatter name does not match {agent}")
        other = "claude" if provider == "codex" else "codex"
        if f".{other}-plugin/plugin.json" in entries:
            failures.append("bundle contains the other provider's manifest")
        manifest = {}
        if manifest_path in entries:
            try:
                manifest = json.loads(entries[manifest_path])
                if not isinstance(manifest, dict):
                    raise ValueError("manifest must be an object")
                if manifest.get("name") != package_name:
                    failures.append(f"manifest name does not match {package_name}")
                if provider == "codex" and manifest.get("skills") not in ("./skills", "./skills/"):
                    failures.append("Codex manifest must expose the shipped skills directory")
            except (ValueError, UnicodeDecodeError) as exc:
                failures.append(f"invalid manifest: {exc}")
                manifest = {}
        failures.extend(_references(entries, manifest))
        if agent != "paper-writing":
            workflows = [data for name, data in entries.items()
                         if name.startswith(("skills/", "workflows/")) and name.endswith(".md")]
            if not any(b"scripts/audit-research-grade" in data for data in workflows):
                failures.append("research workflows do not invoke the shipped grade auditor")
        if failures:
            return [f"{path.name}: {failure}" for failure in failures]
        with tempfile.TemporaryDirectory(prefix="merlean-release-extract-") as temp:
            extracted = Path(temp)
            archive.extractall(extracted)
            invalid = extracted / "false-gold.json"
            invalid.write_text(json.dumps({
                "grade": "GOLD", "target_signature_hash": "same", "dossier_signature_hash": "same",
                "axioms": [], "definition_independence": True, "independent_gold_audit": True,
            }), encoding="utf-8")
            try:
                smoke = subprocess.run(
                    [sys.executable, str(extracted / "scripts/audit-research-grade"), str(invalid)],
                    cwd=extracted, capture_output=True, text=True, check=False, timeout=30,
                )
                if smoke.returncode == 0:
                    failures.append("shipped grade auditor accepted false Gold")
                if "SCHEMA_MISSING" not in smoke.stdout or "EVIDENCE_MISSING" not in smoke.stdout:
                    failures.append("shipped grade auditor did not fail closed with evidence errors")
                cli = subprocess.run(
                    [sys.executable, str(extracted / "src/cli.py"), "--help"],
                    cwd=extracted, env=dict(os.environ, PLAN_OFFLINE="1"),
                    capture_output=True, text=True, check=False, timeout=30,
                )
                if cli.returncode or "plan_store (offline)" not in cli.stdout:
                    failures.append("shipped offline plan CLI failed to bootstrap")
                paper = subprocess.run(
                    [sys.executable, "-m", "paper_writing_codex.cli", "--help"],
                    cwd=extracted, env=dict(os.environ, PYTHONPATH=str(extracted / "src")),
                    capture_output=True, text=True, check=False, timeout=30,
                )
                if paper.returncode or "usage:" not in paper.stdout:
                    failures.append("shipped paper CLI failed to bootstrap")
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append(f"runtime smoke test failed: {exc}")
    return [f"{path.name}: {failure}" for failure in failures]


def _archive_name(path: Path) -> str:
    return next((name for name in PACKAGE_NAMES
                 if path.name == f"{name}.zip" or path.name.startswith(name + "-")), "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--treeish", help="audit bundles built from this exact Git tree")
    parser.add_argument("--archive", action="append", type=Path, default=[])
    args = parser.parse_args(argv)
    failures = []
    with tempfile.TemporaryDirectory(prefix="merlean-release-audit-") as temp:
        archives = args.archive
        if not archives and args.treeish:
            built = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_codex_release.py"),
                 "--treeish", args.treeish, "--out", temp],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=120,
            )
            if built.returncode:
                failures.append("archive build failed: " + (built.stderr.strip() or built.stdout.strip()))
            archives = sorted(Path(temp).glob("*.zip"))
            if len(archives) != len(PACKAGE_NAMES):
                failures.append(f"expected six archives, found {len(archives)}")
        elif not archives:
            try:
                from build_bundles import build_bundle
            except ModuleNotFoundError:
                from scripts.build_bundles import build_bundle
            archives = []
            for provider in PROVIDERS:
                for agent in AGENTS:
                    bundle = build_bundle(provider, agent, Path(temp) / "bundles", root=ROOT)
                    archive = Path(temp) / f"{agent}-{provider}.zip"
                    with zipfile.ZipFile(archive, "w") as output:
                        for source in sorted(bundle.rglob("*")):
                            if source.is_file():
                                output.write(source, source.relative_to(bundle).as_posix())
                    archives.append(archive)
        for archive in archives:
            failures.extend(audit_archive(archive, _archive_name(archive)))
        if not args.archive and {_archive_name(archive) for archive in archives} != set(PACKAGE_NAMES):
            failures.append("release must contain each of the six standalone bundles exactly once")
    if failures:
        print("MerLEAN release audit: FAIL", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("MerLEAN release audit: PASS (standalone archives inspected and smoke-tested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
