"""Execute Synthesise page contracts with synthetic data in Node."""
from pathlib import Path
import shutil
import subprocess
import unittest


class SynthesiseUI(unittest.TestCase):
    def test_synthesise_page_contracts(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        result = subprocess.run([node, str(root / 'tests' / 'test_synthesise_ui.js')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Synthesise page, guards and search record checks passed', result.stdout)
