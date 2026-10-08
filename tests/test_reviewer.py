"""Reviewer records use invented writing and temporary stores only."""
import copy
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from backend import AppError, Store
from reviewer import Reviewer, validate_backup, remap_backup


class ReviewerAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'data')
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.store.close())
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented revisions'})['id']
        self.note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'Widgets are blue. Widgets roll.'})
        self.reviewer = Reviewer(self.store)

    def get(self):
        return self.reviewer.dispatch('GET', '/api/reviewer', {'workspace_id': self.workspace})

    def write(self, **changes):
        return self.reviewer.dispatch('POST', '/api/reviewer/comment', {'workspace_id': self.workspace, 'expected_version': self.get()['version'], **changes})

    def create(self, **changes):
        return self.write(note_id=self.note['id'], note_version=1, passage_start=0, passage_end=17,
                          passage='Widgets are blue.', reviewer='Reviewer 1', comment='Explain the color.', **changes)

    def test_exact_saved_passage_conflicts_isolation_and_restart(self):
        saved = self.create()
        self.assertEqual(saved['comments'][0]['passage'], 'Widgets are blue.')
        self.assertFalse(saved['comments'][0]['stale'])
        with self.assertRaises(AppError):
            self.write(note_id=self.note['id'], note_version=1, passage_start=18, passage_end=35,
                       passage='Widgets are blue.', reviewer='R', comment='Wrong offset')
        with self.assertRaises(AppError) as error:
            self.reviewer.dispatch('POST', '/api/reviewer/comment', {'workspace_id': self.workspace, 'expected_version': 0, 'id': saved['comments'][0]['id'], 'response': 'Mine'})
        self.assertEqual(error.exception.status, 409)
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})['id']
        with self.assertRaises(AppError):
            self.reviewer.dispatch('POST', '/api/reviewer/comment', {'workspace_id': other, 'expected_version': 0, 'note_id': self.note['id'], 'note_version': 1, 'passage_start': 0, 'passage_end': 17, 'passage': 'Widgets are blue.', 'reviewer': 'R', 'comment': 'Wrong workspace'})
        self.store.close()
        self.store = Store(Path(self.tmp.name) / 'data')
        self.reviewer = Reviewer(self.store)
        self.assertEqual(self.get()['comments'][0]['comment'], 'Explain the color.')

    def test_history_noop_archive_and_manuscript_unchanged(self):
        row = self.create()['comments'][0]
        saved = self.write(id=row['id'], planned_text='Describe pigment', revised_text='Widgets have blue pigment.', response='We clarified the description.', status='responded')
        revised = saved['comments'][0]
        self.assertEqual(revised['history'][0]['comment'], 'Explain the color.')
        self.assertEqual(revised['history'][0]['response'], '')
        self.assertEqual(saved['version'], 2)
        self.assertEqual(self.write(id=row['id'], response='We clarified the description.')['version'], 2)
        self.assertTrue(self.write(id=row['id'], archived=True)['comments'][0]['archived'])
        self.assertFalse(self.write(id=row['id'], archived=False)['comments'][0]['archived'])
        self.assertEqual(self.store.db.execute('SELECT body,version FROM notes WHERE id=?', (self.note['id'],)).fetchone()['body'], self.note['body'])
        self.assertEqual(len(self.get()['comments'][0]['history']), 3)

    def test_stale_link_and_explicit_relink_retains_old_passage(self):
        row = self.create()['comments'][0]
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': self.note['id'], 'version': 1, 'title': 'Draft', 'body': 'Widgets are azure. Widgets roll.'})
        stale = self.get()['comments'][0]
        self.assertTrue(stale['stale'])
        self.assertIn('note_version_changed', stale['stale_reasons'])
        with self.assertRaises(AppError) as error:
            self.write(id=row['id'], note_version=1, passage_start=0, passage_end=17, passage='Widgets are blue.')
        self.assertEqual(error.exception.status, 409)
        updated = self.write(id=row['id'], note_version=2, passage_start=0, passage_end=18, passage='Widgets are azure.')['comments'][0]
        self.assertFalse(updated['stale'])
        self.assertEqual(updated['history'][0]['passage'], 'Widgets are blue.')
        self.assertEqual(updated['history'][0]['note_version'], 1)

    def test_export_exact_saved_records_and_stale_status(self):
        row = self.create()['comments'][0]
        self.write(id=row['id'], response='We added a pigment explanation.', status='responded')
        result = self.reviewer.dispatch('POST', '/api/reviewer/export', {'workspace_id': self.workspace, 'expected_version': 2, 'title': 'Response to reviewers', 'include_archived': False})
        self.assertEqual(result['filename'], 'reviewer-response.txt')
        self.assertIn('Reviewer 1', result['content'])
        self.assertIn('Explain the color.', result['content'])
        self.assertIn('We added a pigment explanation.', result['content'])
        self.assertIn('Widgets are blue.', result['content'])
        self.assertIn('1 retained earlier record', result['content'])
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': self.note['id'], 'version': 1, 'title': 'Draft', 'body': 'Widgets are green.'})
        exported = self.reviewer.dispatch('POST', '/api/reviewer/export', {'workspace_id': self.workspace, 'expected_version': 2})
        self.assertIn('STALE', exported['content'])
        with self.assertRaises(AppError):
            self.reviewer.dispatch('POST', '/api/reviewer/export', {'workspace_id': self.workspace, 'expected_version': 1})

    def test_boundary_rejects_malformed_and_incomplete_status(self):
        for changes in ({'status': 'responded'}, {'status': 'revised'}, {'archived': 1}, {'planned_text': []}, {'status': 'done'}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.create(**changes)
        self.assertEqual(self.get()['comments'], [])
        row = self.create()['comments'][0]
        for changes in ({'history': []}, {'note_id': self.note['id']}, {'note_version': 2}, {'passage_start': True}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.write(id=row['id'], **changes)

    def test_backup_validation_remapping_history_and_stale_records(self):
        row = self.create()['comments'][0]
        self.write(id=row['id'], response='Retained answer', status='responded')
        state = self.reviewer.load(self.workspace)
        verified = validate_backup(state, self.workspace, [self.note])
        new_note = 'a' * 32
        restored = remap_backup(verified, 'b' * 32, {self.note['id']: new_note}, lambda text: text)
        self.assertEqual(restored['workspace_id'], 'b' * 32)
        self.assertEqual(restored['comments'][0]['note_id'], new_note)
        self.assertNotEqual(restored['comments'][0]['id'], row['id'])
        self.assertEqual(restored['comments'][0]['history'][0]['passage'], 'Widgets are blue.')
        for mutate in (lambda s: s['comments'].append(copy.deepcopy(s['comments'][0])),
                       lambda s: s['comments'][0].update(note_id='c' * 32),
                       lambda s: s['comments'][0]['history'][0].update(passage_end=1),
                       lambda s: s['comments'][0].update(note_version=1, passage='Wrong quote'),
                       lambda s: s['comments'][0].update(stale=False)):
            bad = copy.deepcopy(state)
            mutate(bad)
            with self.assertRaises(AppError):
                validate_backup(bad, self.workspace, [self.note])
        changed_note = {**self.note, 'version': 2, 'body': 'Changed manuscript.'}
        self.assertEqual(validate_backup(state, self.workspace, [changed_note]), state)

    def test_unicode_offsets_are_codepoints_and_failed_update_retains_history(self):
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Unicode', 'body': '🟦 Blue widgets.'})
        saved = self.write(note_id=note['id'], note_version=1, passage_start=2, passage_end=15, passage='Blue widgets.', reviewer='R', comment='Explain')
        before = self.reviewer.load(self.workspace)
        with self.assertRaises(AppError):
            self.write(id=saved['comments'][0]['id'], response='Yes', status='revised', revised_text='')
        self.assertEqual(self.reviewer.load(self.workspace), before)

    def test_revised_wording_presence_is_distinct_from_user_progress(self):
        row = self.create(revised_text='Widgets have blue pigment.', status='revised')['comments'][0]
        self.assertEqual(row['revised_verification'], 'not_present')
        letter = self.reviewer.dispatch('POST', '/api/reviewer/export', {'workspace_id': self.workspace, 'expected_version': 1})['content']
        self.assertIn('Recorded revised wording is absent from the current saved manuscript.', letter)
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': self.note['id'], 'version': 1, 'title': 'Draft', 'body': 'Widgets have blue pigment. Widgets roll.'})
        current = self.get()['comments'][0]
        self.assertTrue(current['stale'])
        self.assertEqual(current['revised_verification'], 'exact_text_present')
        self.assertEqual(current['current_note_version'], 2)
        letter = self.reviewer.dispatch('POST', '/api/reviewer/export', {'workspace_id': self.workspace, 'expected_version': 1})['content']
        self.assertIn('Exact revised wording is present in current saved manuscript version 2; confirm location and context manually.', letter)

    def test_backup_remaps_citation_markers_in_every_retained_text(self):
        old_source = 'd' * 32
        new_source = 'e' * 32
        marker = '[[source:' + old_source + ':1]]'
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Linked writing', 'body': 'Widgets. ' + marker})
        row = self.write(note_id=note['id'], note_version=1, passage_start=9, passage_end=9 + len(marker), passage=marker,
                         reviewer='R', comment='Check ' + marker, planned_text=marker, revised_text=marker, response=marker)['comments'][0]
        self.write(id=row['id'], response='Updated ' + marker)
        state = validate_backup(self.reviewer.load(self.workspace), self.workspace, [note])
        restored = remap_backup(state, 'f' * 32, {note['id']: 'a' * 32}, lambda text: text.replace(old_source, new_source))
        current = restored['comments'][0]
        for snapshot in [current] + current['history']:
            for field in ('passage', 'comment', 'planned_text', 'revised_text', 'response'):
                self.assertIn(new_source, snapshot[field])
                self.assertNotIn(old_source, snapshot[field])
        restored_note = {**note, 'id': 'a' * 32, 'body': note['body'].replace(old_source, new_source)}
        self.assertEqual(validate_backup(restored, 'f' * 32, [restored_note]), restored)

    def test_integrated_workspace_backup_restores_comments_and_retained_changes(self):
        row = self.create()['comments'][0]
        self.write(id=row['id'], response='We clarified the wording.', status='responded', archived=True)
        before = self.reviewer.load(self.workspace)
        backup = self.store.file_response('/api/backup', {'workspace_id': self.workspace, 'history': '0'})[0]
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['reviewer'], before)
        restored = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(backup).decode()})
        result = self.store.dispatch('GET', '/api/reviewer?workspace_id=' + restored['workspace_id'])
        self.assertTrue(result['comments'][0]['archived'])
        self.assertEqual(result['comments'][0]['response'], 'We clarified the wording.')
        self.assertEqual(result['comments'][0]['history'][0]['response'], '')
        self.assertNotEqual(result['comments'][0]['id'], row['id'])
        self.assertNotEqual(result['comments'][0]['note_id'], self.note['id'])
        self.assertFalse(result['comments'][0]['stale'])
        self.assertEqual(self.reviewer.load(self.workspace), before)

    def test_partial_reference_passage_survives_two_restores_and_automatic_backup(self):
        source = self.store.dispatch('POST', '/api/import', {'workspace_id': self.workspace, 'files': [
            {'name': 'widget-reference.txt', 'data': base64.b64encode(b'Invented widgets are blue.').decode()}]})['results'][0]['document']
        marker = '[[source:' + source['id'] + ':1]]'
        body = 'See ' + marker + ' here.'
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Partial marker', 'body': body})
        # Starts inside the opening marker and ends inside the source identity.
        passage = body[6:29]
        row = self.write(note_id=note['id'], note_version=1, passage_start=6, passage_end=29, passage=passage,
                         reviewer='R', comment='Check this precise selection')['comments'][0]
        self.write(id=row['id'], response='Retained earlier link', status='responded')
        first = self.store.file_response('/api/backup', {'workspace_id': self.workspace, 'history': '0'})[0]
        restored = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(first).decode()})
        saved = self.store.dispatch('GET', '/api/reviewer?workspace_id=' + restored['workspace_id'])
        self.assertFalse(saved['comments'][0]['stale'])
        new_note = self.store.dispatch('GET', '/api/state?workspace_id=' + restored['workspace_id'])['notes']
        manuscript = next(item for item in new_note if item['id'] == saved['comments'][0]['note_id'])
        self.assertEqual(saved['comments'][0]['passage'], manuscript['body'][6:29])
        self.assertEqual(saved['comments'][0]['history'][0]['passage'], manuscript['body'][6:29])
        second = self.store.file_response('/api/backup', {'workspace_id': restored['workspace_id'], 'history': '0'})[0]
        self.assertEqual(self.store._restore({'data': base64.b64encode(second).decode()}, preview_only=True)['reviewer_comments'], 1)
        again = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(second).decode()})
        final = self.store.dispatch('GET', '/api/reviewer?workspace_id=' + again['workspace_id'])
        self.assertFalse(final['comments'][0]['stale'])
        destination = Path(self.tmp.name) / 'reviewer-backups'
        destination.mkdir()
        self.store.auto_backups.configure({'enabled': True, 'destination': str(destination), 'interval_minutes': 60})
        self.assertTrue(self.store.auto_backups.run_now()['ok'])


if __name__ == '__main__':
    unittest.main()
