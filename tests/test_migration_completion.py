"""Upgrade and restore regression checks use disposable synthetic records only."""
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend import AppError, Store


class MigrationCompletion(unittest.TestCase):
    def test_newer_schema_refuses_without_modifying_database(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'research.sqlite3'
            with closing(sqlite3.connect(database)) as db:
                db.execute('PRAGMA user_version=99')
            before = database.read_bytes()
            with self.assertRaisesRegex(AppError, 'newer Kosh'):
                Store(temp)
            self.assertEqual(before, database.read_bytes())
            self.assertFalse((Path(temp) / 'originals').exists())

    def test_legacy_database_snapshot_preserves_original_schema_and_records(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic migration'})
            store.db.execute('PRAGMA user_version=0')
            store.db.commit()
            store.close()
            upgraded = Store(temp)
            try:
                self.assertEqual(upgraded.db.execute('PRAGMA user_version').fetchone()[0], 1)
                snapshots = list((Path(temp) / 'schema-recovery').glob('*.sqlite3'))
                self.assertEqual(len(snapshots), 1)
                with closing(sqlite3.connect(snapshots[0])) as saved:
                    self.assertEqual(saved.execute('PRAGMA user_version').fetchone()[0], 0)
                    self.assertEqual(saved.execute('SELECT id FROM workspaces').fetchone()[0], workspace['id'])
            finally:
                upgraded.close()

    def test_restore_remaps_figure_and_reference_in_current_note_and_revision(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            try:
                workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic figures'})['id']
                pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 10, 10), 0)
                pix.clear_with(255)
                document = store.dispatch('POST', '/api/import', {'workspace_id': workspace, 'files': [{'name': 'figure.png', 'data': base64.b64encode(pix.tobytes('png')).decode()}]})['results'][0]['document']
                body = '![Synthetic figure](kosh-asset:' + document['id'] + ')\n[[reference:' + document['id'] + ']]'
                note = store.dispatch('POST', '/api/notes', {'workspace_id': workspace, 'title': 'Synthetic', 'body': body})
                store.dispatch('POST', '/api/notes', {**note, 'body': body + '\nRevised'})
                backup = store.file_response('/api/backup', {'workspace_id': workspace})[0]
                restored = store.dispatch('POST', '/api/restore', {'data': base64.b64encode(backup).decode()})['workspace_id']
                state = store._state(restored)
                new_id = state['documents'][0]['id']
                self.assertNotEqual(new_id, document['id'])
                history = store.dispatch('GET', '/api/notes/history?id=' + state['notes'][0]['id'])['revisions']
                self.assertEqual(len(history), 2)
                for version in history:
                    self.assertIn('kosh-asset:' + new_id, version['body'])
                    self.assertIn('[[reference:' + new_id + ']]', version['body'])
                    self.assertNotIn(document['id'], version['body'])
            finally:
                store.close()

    def test_raw_bibliography_cannot_be_selected_as_paper_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            try:
                workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic references'})['id']
                text = '@article{x,title={Synthetic widgets}}'
                document = store.dispatch('POST', '/api/import', {'workspace_id': workspace, 'files': [{'name': 'source.bib', 'data': base64.b64encode(text.encode()).decode()}]})['results'][0]['document']
                with self.assertRaisesRegex(AppError, 'not paper text'):
                    store.dispatch('POST', '/api/ask', {'workspace_id': workspace, 'question': 'Widgets?', 'selected_source': {'document_id': document['id'], 'page': 1, 'text': text}})
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
