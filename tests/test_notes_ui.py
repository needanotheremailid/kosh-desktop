"""Run the actual browser note-navigation helpers without a browser dependency."""
from pathlib import Path
import shutil
import subprocess
import unittest


class NotesUI(unittest.TestCase):
    def test_note_navigation(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        result = subprocess.run([node, str(root / 'tests' / 'test_notes_ui.js')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
