"""The shipped write probe must remain inert without explicit bench intent."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / 'tools/sinvert_native_bench.py'


class NativeBenchCliTests(unittest.TestCase):
    def test_import_does_not_start_probe(self):
        spec = importlib.util.spec_from_file_location('native_bench_cli_test', TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

    def test_missing_bench_declaration_exits_before_creating_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            results = Path(temporary) / 'must-not-be-created'
            completed = subprocess.run(
                [sys.executable, str(TOOL), '--output-dir', str(results)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn('--cpu-cp-only', completed.stderr)
            self.assertFalse(results.exists())

    def test_help_does_not_create_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(TOOL), '--help'], cwd=temporary,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertIn('--cpu-cp-only', completed.stdout)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_optimized_python_cannot_disable_probe_guards(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, '-O', str(TOOL), '--cpu-cp-only'], cwd=temporary,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn('verification guards', completed.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])
