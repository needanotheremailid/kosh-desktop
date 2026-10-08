"""Actual process exits around SQLite note commits, using invented data only."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend import Store


class CrashRecoveryTests(unittest.TestCase):
    def test_abrupt_exit_keeps_note_and_revision_atomic(self):
        for boundary in ('BEFORE', 'AFTER', 'COMMITTED'):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temp:
                data = Path(temp) / 'data'
                store = Store(data)
                workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Crash check'})['id']
                note = store.dispatch('POST', '/api/notes', {'workspace_id': workspace, 'title': 'Saved reading', 'body': 'Retained original'})
                store.close()
                command = r'''
import json,os,sys
from backend import Store
data,workspace,note,boundary=sys.argv[1:]
store=Store(data)
store.db.create_function('interrupt_save',0,lambda:os._exit(73))
if boundary!='COMMITTED':
    store.db.execute('CREATE TEMP TRIGGER interrupt_note '+boundary+' UPDATE ON notes BEGIN SELECT interrupt_save(); END')
store.dispatch('POST','/api/notes',{'workspace_id':workspace,'id':note,'version':1,'title':'Revised reading','body':'New complete save'})
os._exit(74)
'''
                child = subprocess.run([sys.executable, '-c', command, str(data), workspace, note['id'], boundary],
                                       cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
                self.assertEqual(child.returncode, 74 if boundary == 'COMMITTED' else 73, child.stderr.decode(errors='replace'))
                reopened = Store(data)
                try:
                    record = dict(reopened.db.execute('SELECT * FROM notes WHERE id=?', (note['id'],)).fetchone())
                    revisions = reopened.db.execute('SELECT * FROM revisions WHERE entity_id=?', (note['id'],)).fetchall()
                    self.assertEqual(record['body'], 'New complete save' if boundary == 'COMMITTED' else 'Retained original')
                    self.assertEqual(record['version'], 2 if boundary == 'COMMITTED' else 1)
                    self.assertEqual(len(revisions), 1 if boundary == 'COMMITTED' else 0)
                    self.assertEqual(reopened.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                finally:
                    reopened.close()
