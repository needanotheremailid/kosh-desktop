"""Run focused writing-review UI logic checks against its actual module."""
from pathlib import Path
import shutil
import subprocess
import unittest


class WritingReviewUI(unittest.TestCase):
    def test_writing_review(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime required for focused UI checks')
        result = subprocess.run([node, str(root / 'tests/test_writing_review_ui.js')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
