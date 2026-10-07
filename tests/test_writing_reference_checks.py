"""Document-level reference checks on real synthetic temporary stores."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import AppError, Store


class WritingReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic writing references'})['id']

    def document(self, name='widgets.txt', data=b'Synthetic widgets only.', workspace=None):
        return self.store._import({'workspace_id': workspace or self.workspace, 'files': [{'name': name, 'data': base64.b64encode(data).decode()}]})['results'][0]['document']

    def note(self, body):
        return self.store._save_note({'workspace_id': self.workspace, 'title': 'Synthetic draft', 'body': body})

    def check(self, note):
        return self.store.dispatch('POST', '/api/writing-check', {'workspace_id': self.workspace, 'note_id': note['id'], 'version': note['version']})

    def test_document_marker_has_no_invented_page_and_shares_integrity_metadata_checks(self):
        doc = self.document()
        note = self.note('# Intro\nWidgets [[reference:' + doc['id'] + ']] and units [[source:' + doc['id'] + ':1]]')
        before = self.store._state(self.workspace)
        with patch.object(self.store, '_bytes', wraps=self.store._bytes) as original:
            checked = self.check(note)
        self.assertEqual(checked['word_count'], 4)
        self.assertEqual(checked['document_references'], [{'marker': '[[reference:' + doc['id'] + ']]', 'document_id': doc['id'], 'name': doc['name'], 'kind': 'txt', 'line': 2}])
        self.assertNotIn('page', checked['document_references'][0])
        self.assertEqual(checked['references'][0]['page'], 1)
        self.assertEqual(len(checked['missing_metadata']), 1)
        self.assertEqual(len(original.call_args_list), 1)
        self.assertEqual(self.store._state(self.workspace), before)

    def test_foreign_unknown_and_malformed_document_markers_are_unresolved(self):
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other synthetic scope'})['id']
        foreign = self.document(workspace=other)
        note = self.note('Widgets [[reference:' + foreign['id'] + ']] [[reference:' + 'f' * 32 + ']] [[reference:bad]] [[reference:unfinished')
        with patch.object(self.store, '_bytes', wraps=self.store._bytes) as original:
            result = self.check(note)
        self.assertEqual(result['document_references'], [])
        self.assertEqual([row['reason'] for row in result['unresolved_references']], ['Source is not in this workspace.', 'Source is not in this workspace.', 'Malformed document reference marker.', 'Malformed document reference marker.'])
        self.assertEqual(result['word_count'], 1)
        original.assert_not_called()

    def test_tampered_original_is_refused_for_document_level_reference(self):
        doc = self.document()
        note = self.note('Widgets [[reference:' + doc['id'] + ']]')
        (self.store.root / self.store._document(doc['id'])['path']).write_bytes(b'Changed synthetic data')
        with self.assertRaises(AppError) as changed:
            self.check(note)
        self.assertEqual(changed.exception.status, 409)

    def test_unclosed_markers_on_earlier_lines_do_not_inflate_word_count(self):
        note = self.note('Widgets [[reference:unfinished\nUnits [[source:unfinished\n')
        result = self.check(note)
        self.assertEqual(result['word_count'], 2)
        self.assertEqual(len(result['unresolved_references']), 2)

    def test_catalogue_document_reference_is_allowed_but_page_evidence_is_not(self):
        catalogue = self.document('widgets.bib', b'@article{x,title={Synthetic widgets}}')
        note = self.note('[[reference:' + catalogue['id'] + ']] [[source:' + catalogue['id'] + ':1]]')
        result = self.check(note)
        self.assertEqual(len(result['document_references']), 1)
        self.assertEqual(result['references'], [])
        self.assertIn('metadata', result['unresolved_references'][0]['reason'].lower())
        self.assertTrue(result['catalogue_reference_warnings'])

    def test_managed_image_is_not_a_bibliographic_or_page_reference(self):
        import pymupdf
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
        pixmap.clear_with(128)
        image = self.document('synthetic.png', pixmap.tobytes('png'))
        note = self.note('[[reference:' + image['id'] + ']] [[source:' + image['id'] + ':1]]')
        result = self.check(note)
        self.assertEqual(result['document_references'], [])
        self.assertEqual(result['references'], [])
        self.assertEqual(len(result['unresolved_references']), 2)
        self.assertEqual(result['missing_metadata'], [])
        self.assertTrue(all('figure' in row['reason'].lower() for row in result['unresolved_references']))

    def test_safe_mechanical_issues_do_not_become_scientific_verdicts(self):
        note = self.note('# Introduction\nTODO: [author input] for widgets.\n# Introduction\nTBD.\n')
        before = self.store._state(self.workspace)
        result = self.check(note)
        self.assertEqual([row['type'] for row in result['mechanical_issues']], ['placeholder', 'placeholder', 'duplicate_heading', 'placeholder'])
        self.assertNotIn('score', result)
        self.assertEqual(self.store._state(self.workspace), before)

    def test_restore_preserves_free_text_provenance_as_historical_context(self):
        original = self.document()
        provenance = 'Historical entered attribution ID ' + original['id'] + '. This arbitrary free text is not an application-generated link.'
        self.store.dispatch('POST', '/api/metadata', {'id': original['id'], 'expected_metadata_version': original['metadata_version'], 'metadata': {'title': 'Synthetic linked title', 'provenance': provenance}})
        archive = self.store.file_response('/api/backup', {'workspace_id': self.workspace})[0]
        restored = self.store.dispatch('POST', '/api/restore', {'data': base64.b64encode(archive).decode()})
        restored_doc = self.store._state(restored['workspace_id'])['documents'][0]
        self.assertNotEqual(restored_doc['id'], original['id'])
        self.assertEqual(restored_doc['metadata']['provenance'], provenance)
        self.assertIn(original['id'], restored_doc['metadata']['provenance'])


if __name__ == '__main__':
    unittest.main()
