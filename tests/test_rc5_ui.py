"""Exercise the rc.5 interface contracts (split view, insertion, palette, stopped gate) with Node."""
from pathlib import Path
import shutil
import subprocess
import unittest

class Rc5UI(unittest.TestCase):
    def test_rc5_interface_contracts(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        result = subprocess.run([node, str(root / 'tests' / 'test_rc5_ui.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('open-intent checks passed', result.stdout)
