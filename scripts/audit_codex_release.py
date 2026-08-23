#!/usr/bin/env python3
"""Fail closed when a tracked MerLean Codex release contains private material or loses a mode."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_SKILLS = {
    "auto-research",
    "compile-fix",
    "explore",
    "formalize",
    "formalizeproblem",
    "init-merlean",
    "lite-research",
    "nl-prover",
    "plan-graph",
    "prove",
    "route-scout",
    "skeptic",
}
PAPER_SKILLS = {"paper-audit", "paper-writing"}

FORBIDDEN_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
FORBIDDEN_PARTS = {".venv", ".lake", "__pycache__", ".pytest_cache"}
SECRET_PATTERNS = {
    "private-key block": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "OpenAI-style secret": re.compile(r"\bsk-(?!\.\.\.|your-key-here)[A-Za-z0-9_-]{12,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "absolute macOS home": re.compile(r"/" + r"Users/[^/\s]+/"),
    "absolute Linux home": re.compile(r"/" + r"home/[^/\s]+/"),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
}


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / p.decode() for p in raw.split(b"\0") if p]


def skill_names(path: Path) -> set[str]:
    return {p.parent.name for p in path.glob("*/SKILL.md")}


def main() -> int:
    failures: list[str] = []
    files = tracked_files()

    for path in files:
        rel = path.relative_to(ROOT)
        lower_parts = {part.lower() for part in rel.parts}
        name = rel.name.lower()
        if name in FORBIDDEN_NAMES or rel.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden credential filename: {rel}")
        if lower_parts & FORBIDDEN_PARTS:
            failures.append(f"generated/runtime path is tracked: {rel}")
        if not path.is_file() or path.stat().st_size > 10_000_000:
            if path.is_file() and path.stat().st_size > 10_000_000:
                failures.append(f"unexpected tracked file over 10 MB: {rel}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {rel}")

    research = skill_names(ROOT / "research-agent/codex/skills")
    paper = skill_names(ROOT / "paper-writing-agent/codex/skills")
    if research != RESEARCH_SKILLS:
        failures.append(
            "research skill mismatch: "
            f"missing={sorted(RESEARCH_SKILLS - research)} extra={sorted(research - RESEARCH_SKILLS)}"
        )
    if paper != PAPER_SKILLS:
        failures.append(
            "paper skill mismatch: "
            f"missing={sorted(PAPER_SKILLS - paper)} extra={sorted(paper - PAPER_SKILLS)}"
        )

    required = [
        ROOT / ".agents/plugins/marketplace.json",
        ROOT / "research-agent/codex/.codex-plugin/plugin.json",
        ROOT / "paper-writing-agent/codex/.codex-plugin/plugin.json",
        ROOT / "PRIVACY.md",
        ROOT / "TERMS.md",
        ROOT / "SUPPORT.md",
    ]
    for path in required:
        if not path.is_file():
            failures.append(f"missing release file: {path.relative_to(ROOT)}")

    if failures:
        print("Codex release audit: FAIL", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Codex release audit: PASS ({len(files)} tracked files; 14 skills; no secret signature)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
