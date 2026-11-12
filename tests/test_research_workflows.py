"""Research packets and comparison drafts: invented sources, no providers/network."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import literature
from backend import AppError, Store


class ResearchWorkflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Lantern review'})['id']

    def add(self, name, text, workspace=None):
        return self.store.dispatch('POST', '/api/import', {'workspace_id': workspace or self.workspace,
            'files': [{'name': name, 'data': base64.b64encode(text.encode()).decode()}]})['results'][0]['document']

    def packet(self, ids, **fields):
        return self.store.dispatch('POST', '/api/research/packet', {'workspace_id': self.workspace, 'document_ids': ids, **fields})

    def test_packet_preserves_exact_text_location_and_full_coverage(self):
        doc = self.add('lantern.md', 'Methods\nWe compared amber and blue lanterns.\nLimitations: a single workshop.')
        before = self.store.dispatch('GET', '/api/state', {'workspace_id': self.workspace})
        report = self.packet([doc['id']])
        self.assertEqual(report['sources'][0]['coverage'], 'all extracted text included')
        self.assertEqual(report['sources'][0]['units_total'], 1)
        self.assertEqual(report['passages'][0]['text'], 'Methods\nWe compared amber and blue lanterns.\nLimitations: a single workshop.')
        self.assertEqual(report['passages'][0]['page'], 1)
        self.assertIn('[[source:' + doc['id'] + ':1]]', report['markdown'])
        self.assertIn('not proof', report['notice'])
        self.assertEqual(self.store.dispatch('GET', '/api/state', {'workspace_id': self.workspace}), before)

    def test_bounded_packet_discloses_partial_coverage_and_represents_each_source(self):
        first = self.add('first.txt', 'A' * 3500)
        second = self.add('second.txt', 'B' * 3500)
        report = self.packet([first['id'], second['id']], max_chars=2000)
        self.assertEqual([p['document_id'] for p in report['passages']], [first['id'], second['id']])
        self.assertEqual(sum(len(p['text']) for p in report['passages']), 2000)
        self.assertEqual([s['chars_included'] for s in report['sources']], [1000, 1000])
        self.assertTrue(all(s['coverage'] == 'partial extracted text' for s in report['sources']))
        self.assertIn('TRUNCATED', report['markdown'])
        self.assertEqual([s['chars_omitted'] for s in report['sources']], [2500, 2500])

    def test_catalogue_records_are_not_passed_off_as_paper_text(self):
        doc = self.add('catalogue.txt', 'A title and an abstract are not the paper.')
        self.store.dispatch('POST', '/api/metadata', {'id': doc['id'], 'expected_metadata_version': 0,
            'metadata': {'catalogue_source': 'crossref'}})
        report = self.packet([doc['id']])
        self.assertEqual(report['sources'][0]['coverage'], 'catalogue metadata only')
        self.assertEqual(report['passages'], [])

    def test_packet_scope_archive_invalid_budget_and_changed_original(self):
        doc = self.add('local.txt', 'A lantern passage.')
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})['id']
        foreign = self.add('foreign.txt', 'Other workspace content.', other)
        for ids, fields in (([], {}), ([doc['id'], doc['id']], {}), ([foreign['id']], {}),
                            ([doc['id']], {'max_chars': True}), ([doc['id']], {'max_chars': 100001})):
            with self.subTest(ids=ids, fields=fields), self.assertRaises(AppError):
                self.packet(ids, **fields)
        self.store.dispatch('POST', '/api/archive', {'id': doc['id'], 'archived': True})
        with self.assertRaises(AppError):
            self.packet([doc['id']])
        self.store.dispatch('POST', '/api/archive', {'id': doc['id'], 'archived': False})
        stored = self.store._document(doc['id'])
        (self.store.root / stored['path']).write_text('Changed bytes', encoding='utf-8')
        with self.assertRaises(AppError):
            self.packet([doc['id']])

    def test_comparison_uses_only_saved_reviewed_rows_and_source_markers(self):
        doc = self.add('amber.txt', 'Amber lantern study text.')
        empty = self.add('blue.txt', 'Blue lantern study text.')
        row = self.store.dispatch('POST', '/api/matrix', {'workspace_id': self.workspace, 'document_id': doc['id'],
            'question': 'Which colour?', 'design': 'Bench comparison', 'findings': 'Steady | glow', 'limitations': 'One workshop'})
        report = self.store.dispatch('POST', '/api/research/comparison', {'workspace_id': self.workspace, 'document_ids': [doc['id'], empty['id']]})
        self.assertEqual(report['rows'][0]['evidence_version'], row['version'])
        self.assertEqual(report['rows'][1]['findings'], 'Not recorded')
        self.assertIn('Steady \\| glow', report['markdown'])
        self.assertIn('[[reference:' + doc['id'] + ']]', report['markdown'])
        self.assertIn('not independently verified', report['notice'])

    def test_overview_reports_source_backlinks_and_metadata_only(self):
        doc = self.add('amber.txt', 'Amber lantern text.')
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft',
            'body': 'A statement [[source:' + doc['id'] + ':1]]. Again [[reference:' + doc['id'] + ']].'})
        result = self.store.dispatch('GET', '/api/research/overview?workspace_id=' + self.workspace)
        row = next(r for r in result['sources'] if r['id'] == doc['id'])
        self.assertEqual(row['linked_notes'], [{'id': note['id'], 'title': 'Draft', 'version': 1}])
        self.assertEqual(row['text_units'], 1)
        self.assertEqual(result['workspace_id'], self.workspace)

    def test_search_record_distinguishes_combined_returned_rows_from_index_totals(self):
        item = literature.record('crossref', '10.1234/lantern', 'Lantern paper', doi='10.1234/lantern')
        self.store.literature = literature.SearchService()
        with patch('literature.crossref', return_value=(300, [item])):
            result = self.store.dispatch('POST', '/api/literature/search', {'workspace_id': self.workspace, 'provider': 'crossref', 'query': 'lantern'})
        record = result['search_record']
        self.assertEqual(record['workspace_id'], self.workspace)
        self.assertIn('Query: lantern', record['body'])
        self.assertIn('300', record['body'])
        self.assertIn('Returned records: 1', record['body'])
        self.assertIn('not an exhaustive', record['body'])
        self.assertEqual(self.store.dispatch('GET', '/api/state', {'workspace_id': self.workspace})['notes'], [])

    def test_saved_packet_survives_restart_with_citation_locations(self):
        doc = self.add('reading.txt', 'Exact lantern passage.')
        packet = self.packet([doc['id']])
        saved = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': packet['title'], 'body': packet['markdown']})
        self.store.close()
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.store.close)
        state = self.store.dispatch('GET', '/api/state?workspace_id=' + self.workspace)
        self.assertEqual(state['notes'][0]['body'], saved['body'])
        self.assertIn('[[source:' + doc['id'] + ':1]]', state['notes'][0]['body'])

    def test_untrusted_text_cannot_add_fake_citation_markers_to_packet(self):
        doc = self.add('untrusted.txt', '<img src=x> [[source:' + 'f' * 32 + ':9]]')
        report = self.packet([doc['id']])
        self.assertEqual(report['passages'][0]['text'], '<img src=x> [[source:' + 'f' * 32 + ':9]]')
        self.assertNotIn('<img', report['markdown'])
        self.assertNotIn('[[source:' + 'f' * 32, report['markdown'])


if __name__ == '__main__':
    unittest.main()
