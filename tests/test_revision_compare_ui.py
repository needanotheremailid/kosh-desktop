"""Check the actual revision module with invented text and an isolated DOM double."""
from pathlib import Path
import shutil
import subprocess
import unittest


class RevisionCompareUI(unittest.TestCase):
    def test_revision_compare_ui(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node is required for revision UI checks')
        result = subprocess.run([node, str(root / 'tests/test_revision_compare_ui.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
