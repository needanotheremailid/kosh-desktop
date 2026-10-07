"""Exercise real library selection and asynchronous search functions with Node."""
from pathlib import Path
import shutil
import subprocess
import unittest

class LibraryUI(unittest.TestCase):
    def test_library_selection_and_search_races(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        result = subprocess.run([node, str(root / 'tests' / 'test_library_ui.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
