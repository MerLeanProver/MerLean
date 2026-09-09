import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from scripts.audit_codex_release import AGENTS, PROVIDERS, audit_archive
from scripts.build_bundles import build_bundle


ROOT = Path(__file__).parents[1]


class CodexReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="merlean-archive-test-")
        self.archive = Path(self.temp.name) / "merlean-lite-codex-test.zip"

    def tearDown(self):
        self.temp.cleanup()

    def build_fixture(self, *, omit=(), provider="codex", agent="merlean-lite"):
        bundle = build_bundle(provider, agent, Path(self.temp.name) / "bundles", root=ROOT)
        with zipfile.ZipFile(self.archive, "w") as archive:
            for source in sorted(bundle.rglob("*")):
                relative = source.relative_to(bundle).as_posix()
                if source.is_file() and relative not in omit:
                    archive.writestr(relative, source.read_bytes())

    def test_extracted_research_archive_smoke_rejects_false_gold(self):
        self.build_fixture()
        self.assertEqual(audit_archive(self.archive, "merlean-lite-codex"), [])

    def test_all_six_standalone_bundles_pass(self):
        for provider in PROVIDERS:
            for agent in AGENTS:
                with self.subTest(provider=provider, agent=agent):
                    self.build_fixture(provider=provider, agent=agent)
                    self.assertEqual(audit_archive(self.archive, f"{agent}-{provider}"), [])

    def test_missing_shipped_grade_engine_is_fatal(self):
        self.build_fixture(omit={"src/research_grade.py"})
        errors = audit_archive(self.archive, "merlean-lite-codex")
        self.assertTrue(any("missing required research runtime file" in error for error in errors))

    def test_unsafe_archive_entry_is_fatal(self):
        self.build_fixture()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("../escape", "bad")
        with patch("scripts.audit_codex_release.subprocess.run") as run:
            errors = audit_archive(self.archive, "merlean-lite-codex")
            run.assert_not_called()
        self.assertTrue(any("unsafe archive entry" in error for error in errors))

    def test_extra_public_skill_is_fatal(self):
        self.build_fixture()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("skills/extra/SKILL.md", "Extra public skill")
        errors = audit_archive(self.archive, "merlean-lite-codex")
        self.assertTrue(any("public skill mismatch" in error for error in errors))

    def test_missing_referenced_workflow_is_fatal(self):
        self.build_fixture()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("docs/broken.md", "Read <PLUGIN_ROOT>/workflows/missing.md")
        errors = audit_archive(self.archive, "merlean-lite-codex")
        self.assertTrue(any("unresolved plugin reference" in error for error in errors))

    def test_credentials_and_symlinks_are_fatal(self):
        self.build_fixture()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(".env", "credential placeholder")
            link = zipfile.ZipInfo("escape-link")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            archive.writestr(link, "../outside")
        errors = audit_archive(self.archive, "merlean-lite-codex")
        self.assertTrue(any("forbidden credential filename" in error for error in errors))
        self.assertTrue(any("unsafe archive symlink" in error for error in errors))

    def test_false_gold_acceptance_is_fatal(self):
        self.build_fixture(omit={"scripts/audit-research-grade"})
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("scripts/audit-research-grade", "print('SCHEMA_MISSING EVIDENCE_MISSING')\n")
        errors = audit_archive(self.archive, "merlean-lite-codex")
        self.assertTrue(any("accepted false Gold" in error for error in errors), errors)

    def test_offline_plan_cli_bootstraps_without_online_dependencies(self):
        env = dict(os.environ)
        env["PLAN_OFFLINE"] = "1"
        run = subprocess.run(
            [sys.executable, str(ROOT / "src/cli.py"), "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("plan_store (offline)", run.stdout)

    def test_shared_dotenv_pin_is_installable_release(self):
        requirement_files = [
            ROOT / "src/requirements.txt",
        ]
        pins = []
        for path in requirement_files:
            pins.extend(
                line for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("python-dotenv==")
            )
        self.assertEqual(pins, ["python-dotenv==1.2.1"] * len(requirement_files))


if __name__ == "__main__":
    unittest.main()
