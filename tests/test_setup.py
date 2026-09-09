"""Offline, temporary-project checks for the common runtime installer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='merlean-setup-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / 'math project'
        self.runtime = self.base / 'runtime "quoted"'

    def run_setup(self, *extra, skip_venv=True, skip_mathlib=True, extra_env=None):
        env = dict(os.environ)
        env.pop('OPENAI_API_KEY', None)
        env.update(extra_env or {})
        args = ['bash', str(ROOT / 'scripts/setup.sh'), '--project', str(self.project),
                '--runtime', str(self.runtime)]
        if skip_mathlib:
            args.append('--skip-mathlib')
        if skip_venv:
            args.append('--skip-venv')
        return subprocess.run([*args, *extra], cwd=self.base, env=env,
                              text=True, capture_output=True)

    def test_fresh_setup_and_idempotent_preservation(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.project / '.env').is_file())
        self.assertEqual((self.project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.project / 'MerLeanExperiment.lean').is_file())
        self.assertFalse((self.project / '.mcp.json').exists())
        names = ['.env', 'lakefile.toml', 'lean-toolchain', 'MerLeanExperiment.lean', '.mcp.json']
        for name in names:
            (self.project / name).write_text('existing content: ' + name)
        before = {name: (self.project / name).read_bytes() for name in names}
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(before, {name: (self.project / name).read_bytes() for name in names})
        self.assertFalse((self.project / '.venv').exists())

    def test_existing_lean_lakefile_is_not_shadowed(self):
        self.project.mkdir()
        (self.project / 'lakefile.lean').write_text('-- existing lake config')
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertFalse((self.project / 'lakefile.toml').exists())
        self.assertFalse((self.project / 'MerLeanExperiment.lean').exists())

    def test_mcp_paths_are_json_escaped_and_runtime_is_separate(self):
        interpreter = self.runtime / '.venv/bin/python'
        interpreter.parent.mkdir(parents=True)
        interpreter.symlink_to(sys.executable)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads((self.project / '.mcp.json').read_text())
        self.assertEqual(config['mcpServers']['lean-lsp']['command'], str(interpreter))
        self.assertEqual(config['mcpServers']['lean-lsp']['args'], ['-m', 'lean_lsp_mcp'])

    def test_windows_interpreter_layout(self):
        interpreter = self.runtime / '.venv/Scripts/python.exe'
        interpreter.parent.mkdir(parents=True)
        interpreter.symlink_to(sys.executable)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads((self.project / '.mcp.json').read_text())
        self.assertEqual(config['mcpServers']['lean-lsp']['command'], str(interpreter))

    def test_broken_runtime_fails_without_deleting_contents(self):
        marker = self.runtime / '.venv/keep.txt'
        marker.parent.mkdir(parents=True)
        marker.write_text('preserve me')
        result = self.run_setup(skip_venv=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('preserved', result.stderr)
        self.assertEqual(marker.read_text(), 'preserve me')

    def test_dangling_project_symlink_is_preserved(self):
        self.project.mkdir()
        target = self.base / 'absent.tex'
        (self.project / '.env').symlink_to(target)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.project / '.env').is_symlink())
        self.assertFalse(target.exists())

    def test_rejects_unknown_secret_input_and_missing_argument(self):
        self.assertEqual(self.run_setup('--openai-key', 'placeholder').returncode, 2)
        self.assertEqual(self.run_setup('--project').returncode, 2)

    def fake_lake(self):
        tools = self.base / 'tools'
        tools.mkdir()
        executable = tools / 'lake'
        executable.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$MERLEAN_TEST_LOG"
if [ "$1" = update ]; then
  if [ -f "$MERLEAN_TEST_FAIL" ]; then exit 1; fi
  mkdir -p .lake/packages/mathlib
  printf '%s\\n' '{"packages":[]}' > lake-manifest.json
  printf '%s\\n' 'leanprover/lean4:v-test' > .lake/packages/mathlib/lean-toolchain
fi
[ -f lake-manifest.json ] || exit 1
''')
        executable.chmod(0o755)
        return dict(PATH=str(tools) + os.pathsep + os.environ['PATH'],
                    MERLEAN_TEST_LOG=str(self.base / 'lake.log'),
                    MERLEAN_TEST_FAIL=str(self.base / 'fail-update'))

    def test_skipped_mathlib_resumes_owned_workspace(self):
        env = self.fake_lake()
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertTrue((self.project / '.merlean-setup-pending').is_dir())
        result = self.run_setup(skip_mathlib=False, extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'lake.log').read_text().splitlines(),
                         ['update', 'exe cache get', 'build'])
        self.assertEqual((self.project / 'lean-toolchain').read_text().strip(),
                         'leanprover/lean4:v-test')
        self.assertFalse((self.project / '.merlean-setup-pending').exists())
        manifest = (self.project / 'lake-manifest.json').read_bytes()
        result = self.run_setup(skip_mathlib=False, extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'lake.log').read_text().splitlines().count('update'), 1)
        self.assertEqual((self.project / 'lake-manifest.json').read_bytes(), manifest)

    def test_failed_mathlib_update_retries_and_preserves_user_toolchain(self):
        env = self.fake_lake()
        failure = self.base / 'fail-update'
        failure.touch()
        result = self.run_setup(skip_mathlib=False, extra_env=env)
        self.assertNotEqual(result.returncode, 0)
        (self.project / 'lean-toolchain').write_text('user-pinned-toolchain\n')
        failure.unlink()
        result = self.run_setup(skip_mathlib=False, extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'lake.log').read_text().splitlines(),
                         ['update', 'update', 'exe cache get', 'build'])
        self.assertEqual((self.project / 'lean-toolchain').read_text(), 'user-pinned-toolchain\n')

    def test_changed_starter_and_existing_manifest_are_not_updated(self):
        env = self.fake_lake()
        self.assertEqual(self.run_setup().returncode, 0)
        (self.project / 'lakefile.toml').write_text('name = "user-project"\n')
        manifest = self.project / 'lake-manifest.json'
        manifest.write_text('{"locked":true}\n')
        result = self.run_setup(skip_mathlib=False, extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'lake.log').read_text().splitlines(), ['exe cache get', 'build'])
        self.assertEqual(manifest.read_text(), '{"locked":true}\n')


if __name__ == '__main__':
    unittest.main()
