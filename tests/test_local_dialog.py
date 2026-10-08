import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import local_dialog
from backend import AppError


class LocalDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bin').mkdir()
        (self.root / 'bin' / 'ResearchDesktop.exe').write_bytes(b'fixture')

    def test_invalid_kind_and_extra_fields_never_execute(self):
        with patch('local_dialog.subprocess.run') as run:
            for body in ({}, {'kind': '../shell'}, {'kind': []}, {'kind': {}},
                         {'kind': 'folder', 'command': 'bad'}):
                with self.assertRaises(AppError):
                    local_dialog.choose(self.root, body)
            run.assert_not_called()

    def test_cancel_ignores_any_path_and_never_changes_files(self):
        result = SimpleNamespace(returncode=0, stdout=json.dumps({'cancelled': True, 'path': 'private'}).encode())
        with patch('local_dialog.subprocess.run', return_value=result) as run:
            self.assertEqual(local_dialog.choose(self.root, {'kind': 'folder'}), {'cancelled': True, 'path': ''})
            self.assertEqual(run.call_args.args[0], [str(self.root / 'bin' / 'ResearchDesktop.exe'), '--dialog', 'folder'])
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_selected_existing_file_is_not_written(self):
        target = self.root / 'existing.zip'
        target.write_bytes(b'preserve')
        response = {'cancelled': False, 'path': str(target)}
        with patch('local_dialog.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(response).encode())):
            self.assertEqual(local_dialog.choose(self.root, {'kind': 'backup-save'}), response)
        self.assertEqual(target.read_bytes(), b'preserve')

    def test_timeout_and_bad_response_leave_lock_reusable(self):
        for result in (b'not json', b'{"cancelled":false,"path":"relative.zip"}'):
            with patch('local_dialog.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=result)):
                with self.assertRaises(AppError):
                    local_dialog.choose(self.root, {'kind': 'folder'})
            self.assertFalse(local_dialog._active.locked())
        with patch('local_dialog.subprocess.run', side_effect=subprocess.TimeoutExpired('fixture', 180)):
            with self.assertRaisesRegex(AppError, 'timed out'):
                local_dialog.choose(self.root, {'kind': 'folder'})
        self.assertFalse(local_dialog._active.locked())

    def test_second_picker_refused(self):
        local_dialog._active.acquire()
        try:
            with self.assertRaisesRegex(AppError, 'already open'):
                local_dialog.choose(self.root, {'kind': 'folder'})
        finally:
            local_dialog._active.release()
