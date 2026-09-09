"""Observable mode dispatch and generated-bundle preservation, without launching models."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_bundles import AGENTS, PROVIDERS, build_bundle, bundle_entries, verify_generated, write_archive, write_catalogs

ROOT = Path(__file__).resolve().parents[1]


class AgentModesTests(unittest.TestCase):
    def select(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/merlean-agent"), *args],
                              capture_output=True, text=True, check=False)

    def test_default_lite_explicit_heavy_and_paper(self):
        for flags, agent, grade in [
            ((), "merlean-lite", "SILVER"), (("-lite",), "merlean-lite", "SILVER"),
            (("-heavy",), "merlean-heavy", "GOLD"),
            (("--task", "formalize"), "merlean-heavy", "GOLD"),
            (("--task", "prove"), "merlean-heavy", "GOLD"),
            (("--task", "translate-only"), "merlean-heavy", None),
            (("--paper-writing",), "paper-writing", None),
            (("--resume-mode", "heavy"), "merlean-heavy", "GOLD"),
        ]:
            with self.subTest(flags=flags):
                run = self.select(*flags)
                self.assertEqual(run.returncode, 0, run.stderr)
                data = json.loads(run.stdout)
                self.assertEqual((data["agent"], data["grade_target"]), (agent, grade))
                self.assertFalse(data["launches_model"])

    def test_conflicting_mode_and_task_are_rejected(self):
        for flags in [("-lite", "-heavy"), ("-lite", "--task", "formalize"),
                      ("-lite", "--resume-mode", "heavy"), ("-heavy", "--task", "paper")]:
            self.assertNotEqual(self.select(*flags).returncode, 0)

    def test_six_bundles_one_public_agent_and_identical_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            bundles = [build_bundle(p, a, Path(temp)) for p in PROVIDERS for a in AGENTS]
            self.assertEqual(len(bundles), 6)
            for bundle in bundles:
                self.assertEqual(len(list(bundle.glob("skills/*/SKILL.md"))), 1)
                for relative in ("src/research_grade.py", "src/plan_store/grade_policy.py",
                                 "src/plan_store/lean_sync.py", "workflows/common.md"):
                    self.assertEqual((bundle / relative).read_bytes(), (ROOT / relative).read_bytes())
                verify_generated(bundle)

    def test_rebuild_refuses_user_edits_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            bundle = build_bundle("codex", "merlean-lite", out)
            build_bundle("codex", "merlean-lite", out)  # unchanged regeneration is safe
            user_file = bundle / "personal-notes.md"
            user_file.write_text("preserve this")
            with self.assertRaises(ValueError):
                build_bundle("codex", "merlean-lite", out)
            self.assertEqual(user_file.read_text(), "preserve this")
            user_file.unlink()  # temporary test-owned artifact only
            source = bundle / "workflows/common.md"
            source.write_text("local edit")
            with self.assertRaises(ValueError):
                build_bundle("codex", "merlean-lite", out)
            self.assertEqual(source.read_text(), "local edit")

    def test_unknown_provider_agent_and_symlink_output_refused(self):
        with self.assertRaises(ValueError):
            bundle_entries("unknown", "merlean-lite")
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target = base / "preserve"
            target.mkdir()
            (base / "merlean-lite-codex").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                build_bundle("codex", "merlean-lite", base)
            self.assertTrue(target.is_dir())

    def test_installed_provider_is_inferred_and_mismatch_not_mislabeled(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = build_bundle("claude", "merlean-lite", Path(temp))
            for flags, expected_provider, has_entry in [
                ((), "claude", True), (("--provider", "codex"), "codex", False),
            ]:
                run = subprocess.run([sys.executable, str(bundle / "scripts/merlean-agent"), *flags],
                                     check=True, capture_output=True, text=True)
                data = json.loads(run.stdout)
                self.assertEqual(data["provider"], expected_provider)
                self.assertEqual(data["entrypoint"] is not None, has_entry)

    def test_archive_never_overwrites_unrelated_files_or_links(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            package = build_bundle("codex", "merlean-lite", out / "packages")
            unrelated = out / "unrelated.txt"
            unrelated.write_text("USER CONTENT")
            archive = out / "output.zip"
            archive.symlink_to(unrelated)
            with self.assertRaises(ValueError):
                write_archive(package, archive)
            self.assertEqual(unrelated.read_text(), "USER CONTENT")
            archive.unlink()  # own temporary test link
            archive.write_text("USER ARCHIVE")
            with self.assertRaises(ValueError):
                write_archive(package, archive)
            self.assertEqual(archive.read_text(), "USER ARCHIVE")
            safe = out / "safe.zip"
            write_archive(package, safe)
            before = safe.read_bytes()
            write_archive(package, safe)
            self.assertEqual(safe.read_bytes(), before)

    def test_receipt_links_empty_user_directories_and_permissions_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            bundle = build_bundle("codex", "merlean-lite", out)
            receipt = bundle / ".merlean-generated.json"
            external = out / "external-receipt.json"
            receipt.rename(external)
            receipt.symlink_to(external)
            with self.assertRaises(ValueError):
                verify_generated(bundle)
            receipt.unlink()  # test-owned link only
            external.rename(receipt)
            empty = bundle / "new-project"
            empty.mkdir()
            with self.assertRaises(ValueError):
                build_bundle("codex", "merlean-lite", out)
            empty.rmdir()  # test-owned empty directory
            (bundle / "src").chmod(0o700)
            with self.assertRaises(ValueError):
                build_bundle("codex", "merlean-lite", out)
            self.assertEqual((bundle / "src").stat().st_mode & 0o777, 0o700)

    def test_optional_catalogs_resolve_six_local_packages_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packages = root / "plugins"
            for provider in PROVIDERS:
                for agent in AGENTS:
                    build_bundle(provider, agent, packages)
            outputs = write_catalogs(packages)
            for path, provider in zip(outputs, ("codex", "claude")):
                catalog = json.loads(path.read_text())
                self.assertEqual(len(catalog["plugins"]), 3)
                self.assertEqual({entry["name"] for entry in catalog["plugins"]},
                                 {f"{agent}-{provider}" for agent in AGENTS})
                for entry in catalog["plugins"]:
                    relative = entry["source"]["path"] if provider == "codex" else entry["source"]
                    manifest = json.loads((root / relative / f".{provider}-plugin/plugin.json").read_text())
                    self.assertEqual(manifest["name"], entry["name"])
            write_catalogs(packages)
            outputs[0].write_text("USER CATALOG")
            with self.assertRaises(ValueError):
                write_catalogs(packages)
            self.assertEqual(outputs[0].read_text(), "USER CATALOG")


if __name__ == "__main__":
    unittest.main()
