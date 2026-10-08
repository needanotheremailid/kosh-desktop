"""Run reviewer UI checks against the shipped JavaScript module."""
from pathlib import Path
import shutil
import subprocess
import unittest


class ReviewerUI(unittest.TestCase):
    def test_reviewer_ui(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node is required for UI checks')
        result = subprocess.run([node, str(root / 'tests/test_reviewer_ui.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
