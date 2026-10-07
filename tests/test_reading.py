"""Reading persistence checks use invented sources and isolated temporary stores."""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend import AppError, Store


class ReadingAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'data')
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented reading'})['id']
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.store.close())

    def source(self, data=b'Invented widgets are blue. Widgets have wheels.', name='widgets.txt', workspace=None):
        return self.store.dispatch('POST', '/api/import', {'workspace_id': workspace or self.workspace, 'files': [{'name': name, 'data': base64.b64encode(data).decode()}]})['results'][0]['document']

    def get(self, workspace=None):
        return self.store.dispatch('GET', '/api/reading?workspace_id=' + (workspace or self.workspace))

    def write(self, route, **payload):
        return self.store.dispatch('POST', '/api/reading/' + route, {'workspace_id': self.workspace, 'expected_version': self.get()['version'], **payload})

    def test_source_resume_restart_conflict_and_isolation(self):
        document = self.source()
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'A saved claim.'})
        saved = self.write('source', document_id=document['id'], tags=['widgets', 'review'], collection='Methods', status='reading', favorite=True, last_page=1)
        self.assertEqual(saved['sources'][0]['collection'], 'Methods')
        self.write('resume', document_id=document['id'], page=1, note_id=note['id'], view='write', panel='claims', next_action='Check the wheel claim')
        with self.assertRaises(AppError) as error:
            self.store.dispatch('POST', '/api/reading/source', {'workspace_id': self.workspace, 'expected_version': 0, 'document_id': document['id'], 'favorite': False})
        self.assertEqual(error.exception.status, 409)
        self.store.close()
        self.store = Store(Path(self.tmp.name) / 'data')
        self.assertEqual(self.get()['resume']['next_action'], 'Check the wheel claim')
        self.assertTrue(self.get()['sources'][0]['favorite'])
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})['id']
        self.assertEqual(self.get(other)['annotations'], [])
        with self.assertRaises(AppError):
            self.store.dispatch('POST', '/api/reading/source', {'workspace_id': other, 'expected_version': 0, 'document_id': document['id'], 'status': 'read'})

    def test_annotation_immutable_quote_archive_and_nonpdf_source_validation(self):
        document = self.source()
        saved = self.write('annotation', document_id=document['id'], page=1, quote='Widgets have wheels.', comment='Compare later', color='yellow')
        annotation = saved['annotations'][0]
        self.assertEqual(annotation['rects'], [])
        with self.assertRaises(AppError):
            self.write('annotation', id=annotation['id'], quote='changed')
        with self.assertRaises(AppError):
            self.write('annotation', document_id=document['id'], page=1, quote='Invented unsupported statement', comment='', color='yellow')
        self.assertTrue(self.write('annotation', id=annotation['id'], archived=True)['annotations'][0]['archived'])
        self.assertFalse(self.write('annotation', id=annotation['id'], archived=False)['annotations'][0]['archived'])
        self.assertEqual(self.store.file_response('/api/file', {'id': document['id']})[0], b'Invented widgets are blue. Widgets have wheels.')

    def test_pdf_geometry_selection_rotation_and_original_guard(self):
        import pymupdf
        pdf = pymupdf.open()
        page = pdf.new_page(width=300, height=400)
        page.insert_text((40, 50), 'Invented blue widgets')
        page.set_rotation(90)
        document = self.source(pdf.tobytes(), 'rotated.pdf')
        pdf.close()
        geometry = self.store.dispatch('GET', '/api/reading/geometry?workspace_id=' + self.workspace + '&document_id=' + document['id'] + '&page=1')
        self.assertEqual((geometry['width'], geometry['height']), (400, 300))
        self.assertEqual([word['text'] for word in geometry['words']], ['Invented', 'blue', 'widgets'])
        first = geometry['words'][0]['rect']
        self.assertGreater(first[0], 0.8)
        self.assertAlmostEqual(first[1], 40 / 300, places=5)
        saved = self.write('annotation', document_id=document['id'], page=1, quote='Invented blue', word_indices=[0, 1], comment='', color='green')
        self.assertEqual(saved['annotations'][0]['rects'], [word['rect'] for word in geometry['words'][:2]])
        with self.assertRaises(AppError):
            self.write('annotation', document_id=document['id'], page=1, quote='Invented widgets', word_indices=[0, 2], color='yellow')
        with self.assertRaises(AppError):
            self.write('annotation', document_id=document['id'], page=1, quote='Blue false claim', word_indices=[0, 1], color='yellow')
        (self.store.root / self.store._document(document['id'])['path']).write_bytes(b'tampered')
        with self.assertRaises(AppError) as error:
            self.store.dispatch('GET', '/api/reading/geometry?workspace_id=' + self.workspace + '&document_id=' + document['id'] + '&page=1')
        self.assertEqual(error.exception.status, 409)

    def test_claim_status_requires_exact_saved_anchor_and_stales_on_note_edit(self):
        document = self.source()
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'Widgets have wheels.'})
        with self.assertRaises(AppError):
            self.write('claim', note_id=note['id'], note_version=1, claim_anchor='Not in draft', status='needs_source')
        saved = self.write('claim', note_id=note['id'], note_version=1, claim_anchor='Widgets have wheels.', status='needs_source')
        claim = saved['claims'][0]
        with self.assertRaises(AppError):
            self.write('claim', id=claim['id'], status='checked')
        saved = self.write('claim', id=claim['id'], status='attached', document_id=document['id'], page=1, excerpt='Widgets have wheels.')
        self.assertFalse(saved['claims'][0]['stale'])
        self.write('claim', id=claim['id'], status='checked')
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': note['id'], 'version': 1, 'title': 'Draft', 'body': 'Widgets might have wheels.'})
        stale = self.get()['claims'][0]
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['status'], 'checked')
        self.assertIn('note_version_changed', stale['stale_reasons'])

    def test_backup_restores_reading_ids_and_archive_state_without_touching_original(self):
        document = self.source()
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'Widgets have wheels.'})
        self.write('source', document_id=document['id'], tags=['review'], status='read', favorite=True)
        self.write('resume', document_id=document['id'], note_id=note['id'], page=1, next_action='Return here')
        self.write('annotation', document_id=document['id'], page=1, quote='Widgets have wheels.', comment='Review', color='blue')
        self.write('claim', note_id=note['id'], note_version=1, claim_anchor='Widgets have wheels.', status='checked', document_id=document['id'], page=1, excerpt='Widgets have wheels.')
        before = self.get()
        self.write('annotation', id=before['annotations'][0]['id'], archived=True)
        backup = self.store.file_response('/api/backup', {'workspace_id': self.workspace, 'history': '0'})[0]
        restored = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(backup).decode()})
        reading = self.get(restored['workspace_id'])
        self.assertNotEqual(reading['sources'][0]['document_id'], document['id'])
        self.assertNotEqual(reading['resume']['note_id'], note['id'])
        self.assertEqual(reading['annotations'][0]['document_id'], reading['resume']['document_id'])
        self.assertEqual(reading['claims'][0]['note_id'], reading['resume']['note_id'])
        self.assertFalse(reading['claims'][0]['stale'])
        self.assertTrue(reading['annotations'][0]['archived'])
        self.assertEqual(self.get()['resume']['document_id'], document['id'])
        bad = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(backup)) as original, zipfile.ZipFile(bad, 'w') as target:
            for member in original.namelist():
                content = original.read(member)
                if member == 'manifest.json':
                    manifest = json.loads(content)
                    manifest['reading']['resume']['document_id'] = 'f' * 32
                    content = json.dumps(manifest).encode()
                target.writestr(member, content)
        with self.assertRaises(AppError):
            self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(bad.getvalue()).decode()})
        self.assertEqual(len(self.store.dispatch('GET', '/api/workspaces')['workspaces']), 2)

    def test_strict_payload_limits_and_non_destructive_duplicates(self):
        first = self.source()
        second = self.source(b'A distinct original with a bibliography identity.', 'second.txt')
        for document in (first, second):
            self.store.dispatch('POST', '/api/metadata', {'id': document['id'], 'expected_metadata_version': document['metadata_version'], 'metadata': {'title': 'Invented Widget Methods', 'doi': '10.example/widget'}})
        candidates = self.store.dispatch('GET', '/api/reading/duplicates?workspace_id=' + self.workspace)['candidates']
        self.assertEqual(set(candidates[0]['document_ids']), {first['id'], second['id']})
        self.assertEqual(candidates[0]['reasons'], ['doi', 'title'])
        self.assertEqual(len(self.store.dispatch('GET', '/api/state?workspace_id=' + self.workspace)['documents']), 2)
        for payload in ({'favorite': 1}, {'status': 'verified'}, {'tags': ['x'] * 51}, {'last_page': 2}, {'arbitrary': 'x'}):
            with self.assertRaises(AppError):
                self.write('source', document_id=first['id'], **payload)
        self.assertEqual(self.get()['version'], 0)

    def test_pdf_backup_rejects_invented_geometry_before_workspace_creation(self):
        import pymupdf
        pdf = pymupdf.open()
        pdf.new_page().insert_text((40, 50), 'Invented widget passage')
        document = self.source(pdf.tobytes(), 'selection.pdf')
        pdf.close()
        self.write('annotation', document_id=document['id'], page=1, quote='Invented widget', word_indices=[0, 1])
        backup = self.store.file_response('/api/backup', {'workspace_id': self.workspace})[0]
        bad = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(backup)) as original, zipfile.ZipFile(bad, 'w') as rewritten:
            for member in original.namelist():
                content = original.read(member)
                if member == 'manifest.json':
                    manifest = json.loads(content)
                    manifest['reading']['annotations'][0]['rects'][0] = [0.1, 0.1, 0.9, 0.9]
                    content = json.dumps(manifest).encode()
                rewritten.writestr(member, content)
        with self.assertRaises(AppError):
            self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(bad.getvalue()).decode()})
        self.assertEqual(len(self.store.dispatch('GET', '/api/workspaces')['workspaces']), 1)

    def test_noop_updates_keep_version_and_resume_supports_actual_evidence_view(self):
        document = self.source()
        first = self.write('source', document_id=document['id'], status='reading')
        second = self.write('source', document_id=document['id'], status='reading')
        self.assertEqual(first['version'], second['version'])
        self.write('resume', view='evidence', panel='notes')
        self.assertEqual(self.get()['resume']['view'], 'evidence')

    def test_stale_source_claim_can_archive_and_failed_size_write_is_atomic(self):
        document = self.source()
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'Widgets have wheels.'})
        saved = self.write('claim', note_id=note['id'], note_version=1, claim_anchor='Widgets have wheels.', status='checked', document_id=document['id'], page=1, excerpt='Widgets have wheels.')
        with patch('reading.STATE_LIMIT', 200):
            with self.assertRaises(AppError) as error:
                self.write('resume', next_action='A pending larger action')
        self.assertEqual(error.exception.status, 413)
        self.assertEqual(self.get()['version'], saved['version'])
        (self.store.root / self.store._document(document['id'])['path']).write_bytes(b'tampered')
        self.assertTrue(self.get()['claims'][0]['stale'])
        archived = self.write('claim', id=saved['claims'][0]['id'], archived=True)
        self.assertTrue(archived['claims'][0]['archived'])
        self.assertTrue(archived['claims'][0]['stale'])

    def test_changed_checked_attachment_retains_history_and_stale_cannot_be_checked(self):
        first = self.source()
        second = self.source(b'Invented wheels have spokes.', 'other.txt')
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'Widgets have wheels.'})
        saved = self.write('claim', note_id=note['id'], note_version=1, claim_anchor='Widgets have wheels.', status='checked', document_id=first['id'], page=1, excerpt='Widgets have wheels.')
        claim_id = saved['claims'][0]['id']
        with self.assertRaises(AppError):
            self.write('claim', id=claim_id, document_id=second['id'], page=1, excerpt='wheels have spokes.', status='checked')
        changed = self.write('claim', id=claim_id, document_id=second['id'], page=1, excerpt='wheels have spokes.')['claims'][0]
        self.assertEqual(changed['status'], 'attached')
        self.assertEqual(changed['attachment_history'][0]['document_id'], first['id'])
        self.assertEqual(changed['attachment_history'][0]['status'], 'checked')
        backup = self.store.file_response('/api/backup', {'workspace_id': self.workspace})[0]
        restored = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(backup).decode()})
        copied = self.get(restored['workspace_id'])
        historical_id = copied['claims'][0]['attachment_history'][0]['document_id']
        self.assertNotEqual(historical_id, first['id'])
        self.assertIn(historical_id, {source['document_id'] for source in copied['sources']})
        self.assertEqual(copied['claims'][0]['status'], 'attached')
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': note['id'], 'version': 1, 'title': 'Draft', 'body': 'A new claim.'})
        with self.assertRaises(AppError) as error:
            self.write('claim', id=claim_id, status='checked')
        self.assertEqual(error.exception.status, 409)

    def test_pdf_sorted_selection_is_not_stale_from_plain_extraction_order(self):
        import pymupdf
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((40, 100), 'Bottom widgets')
        page.insert_text((40, 50), 'Top wheels')
        document = self.source(pdf.tobytes(), 'order.pdf')
        pdf.close()
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Claim', 'body': 'An invented claim.'})
        saved = self.write('claim', note_id=note['id'], note_version=1, claim_anchor='An invented claim.', status='attached', document_id=document['id'], page=1, excerpt='wheels Bottom')
        self.assertFalse(saved['claims'][0]['stale'])
