"""Manual screening on invented sources and temporary stores."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from backend import AppError, Store


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'store')
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.store.close())
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented'})['id']

    def get(self, workspace=None):
        return self.store.dispatch('GET', '/api/screening?workspace_id=' + (workspace or self.workspace))

    def source(self, name, workspace=None):
        receipt = self.store.dispatch('POST', '/api/import', {'workspace_id': workspace or self.workspace,
            'files': [{'name': name + '.txt', 'data': base64.b64encode(('Invented ' + name).encode()).decode()}]})
        return receipt['results'][0]['document']['id']

    def decision(self, document, stage, decision, reason='', **extra):
        payload = {'workspace_id': self.workspace, 'expected_version': self.get()['version'],
                   'document_id': document, 'stage': stage, 'decision': decision, 'reason': reason}
        payload.update(extra)
        return self.store.dispatch('POST', '/api/screening/decision', payload)

    def criteria(self, criteria, **extra):
        payload = {'workspace_id': self.workspace, 'expected_version': self.get()['version'], 'criteria': criteria}
        payload.update(extra)
        return self.store.dispatch('POST', '/api/screening/criteria', payload)

    def test_defaults(self):
        state = self.get()
        self.assertEqual(state['workspace_id'], self.workspace)
        self.assertEqual(state['version'], 0)
        self.assertEqual(state['criteria'], {'include': [], 'exclude': []})
        self.assertEqual(state['records'], {})
        self.assertEqual(state['flow']['identified'], 0)

    def test_decision_rules_history_and_conflict(self):
        source = self.source('one')
        with self.assertRaises(AppError):
            self.decision(source, 'full_text', 'include')
        self.decision(source, 'title_abstract', 'maybe', 'First')
        self.decision(source, 'title_abstract', 'include', 'Second')
        state = self.get()
        self.assertEqual(state['records'][source]['history'][0]['decision'], 'maybe')
        self.assertEqual(state['records'][source]['history'][0]['reason'], 'First')
        self.assertEqual(state['records'][source]['history'][0]['stage'], 'title_abstract')
        with self.assertRaises(AppError):
            self.decision(source, 'full_text', 'exclude', '  ')
        self.decision(source, 'full_text', 'exclude', 'Wrong topic')
        self.decision(source, 'full_text', 'exclude', 'Another reason')
        history = self.get()['records'][source]['history']
        self.assertEqual(history[-1]['stage'], 'full_text')
        self.assertEqual(history[-1]['reason'], 'Wrong topic')
        self.assertTrue(history[-1]['decided_at'])
        self.assertTrue(history[-1]['replaced_at'])
        current_version = self.get()['version']
        self.assertEqual(self.decision(source, 'full_text', 'exclude', 'Another reason')['version'], current_version)
        with self.assertRaisesRegex(AppError, 'full-text decision exists'):
            self.decision(source, 'title_abstract', 'exclude')
        with self.assertRaises(AppError) as error:
            self.decision(source, 'title_abstract', 'maybe', expected_version=0)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.get()['records'][source]['title_abstract']['decision'], 'include')

    def test_validation_and_workspace_isolation(self):
        source = self.source('source')
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})['id']
        foreign = self.source('foreign', other)
        for document, stage, decision, reason in [(foreign, 'title_abstract', 'include', ''),
                (source, 'other', 'include', ''), (source, 'title_abstract', 'skip', ''),
                (source, 'title_abstract', [], ''), (source, 'title_abstract', 'include', []),
                (source, 'title_abstract', 'include', 'x' * 2001)]:
            with self.subTest(stage=stage, decision=decision), self.assertRaises(AppError):
                self.decision(document, stage, decision, reason)
        for criteria in ({'include': [], 'exclude': [], 'extra': []}, {'include': []},
                         {'include': 'text', 'exclude': []}, {'include': [''], 'exclude': []},
                         {'include': ['x' * 2001], 'exclude': []}, {'include': ['x'] * 101, 'exclude': []}):
            with self.subTest(criteria=criteria), self.assertRaises(AppError):
                self.criteria(criteria)
        with self.assertRaises(AppError):
            self.decision(source, 'title_abstract', 'include', unexpected=True)
        with self.assertRaises(AppError):
            self.criteria({'include': [], 'exclude': []}, expected_version=True)
        with self.assertRaises(AppError) as error:
            self.criteria({'include': ['Widgets'], 'exclude': []}, expected_version=1)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.get()['version'], 0)

    def test_flow_and_archive(self):
        first, second, third, fourth, fifth = [self.source(str(i)) for i in range(5)]
        self.decision(first, 'title_abstract', 'exclude')
        for item in (second, third, fourth):
            self.decision(item, 'title_abstract', 'include')
        self.decision(second, 'full_text', 'exclude', 'Wrong population')
        self.decision(third, 'full_text', 'exclude', 'Wrong population')
        self.decision(fourth, 'full_text', 'include')
        self.assertEqual(self.get()['flow'], {'identified': 5, 'title_abstract_screened': 4,
            'title_abstract_excluded': 1, 'full_text_assessed': 3, 'full_text_excluded': 2,
            'full_text_excluded_by_reason': {'Wrong population': 2}, 'included': 1, 'undecided': 1})
        with self.store.db:
            self.store.db.execute('UPDATE documents SET archived=1 WHERE id=?', (second,))
        state = self.get()
        self.assertIn(second, state['records'])
        self.assertEqual(state['flow']['identified'], 4)
        self.assertEqual(state['flow']['full_text_excluded_by_reason'], {'Wrong population': 1})

    def test_backup_roundtrip_and_legacy(self):
        source = self.source('archive')
        self.criteria({'include': ['Widgets'], 'exclude': ['Gadgets']})
        self.decision(source, 'title_abstract', 'maybe', 'Unclear')
        self.decision(source, 'title_abstract', 'include', 'Checked')
        backup = self.store.file_response('/api/backup', {'workspace_id': self.workspace})[0]
        data = {'data': base64.b64encode(backup).decode()}
        preview = self.store._restore(data, preview_only=True)
        self.assertTrue(preview['screening_present'])
        self.assertEqual(preview['screening_records'], 1)
        restored = self.store.dispatch('POST', '/api/restore', data)
        state = self.get(restored['workspace_id'])
        new_source = next(iter(state['records']))
        self.assertNotEqual(source, new_source)
        self.assertEqual(state['criteria']['include'], ['Widgets'])
        self.assertEqual(state['records'][new_source]['history'][0]['reason'], 'Unclear')
        self.assertEqual(state['flow']['title_abstract_screened'], 1)
        legacy = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(backup)) as original, zipfile.ZipFile(legacy, 'w') as rewritten:
            for member in original.namelist():
                content = original.read(member)
                if member == 'manifest.json':
                    manifest = json.loads(content)
                    del manifest['screening']
                    content = json.dumps(manifest).encode()
                rewritten.writestr(member, content)
        legacy_data = {'data': base64.b64encode(legacy.getvalue()).decode()}
        self.assertFalse(self.store._restore(legacy_data, preview_only=True)['screening_present'])
        old_restored = self.store.dispatch('POST', '/api/restore', legacy_data)
        self.assertEqual(self.get(old_restored['workspace_id'])['records'], {})

    def test_backup_rejects_malformed_records(self):
        from screening import Screening, validate_backup
        source = self.source('valid')
        self.decision(source, 'title_abstract', 'include')
        state = Screening(self.store).load(self.workspace)
        docs = [{'id': source}]
        for mutate in (lambda s: s.update(extra=1), lambda s: s.update(version=True),
                       lambda s: s.update(workspace_id='f' * 32),
                       lambda s: s.update(criteria={'include': [], 'exclude': [], 'extra': []}),
                       lambda s: s['records'][source].update(extra=1),
                       lambda s: s['records'][source]['title_abstract'].update(extra=1),
                       lambda s: s['records'][source]['title_abstract'].update(decided_at=''),
                       lambda s: s['records'][source]['title_abstract'].update(reason=1),
                       lambda s: s['records'][source].update(full_text={'decision': 'exclude', 'reason': '', 'decided_at': 'now'}),
                       lambda s: s['records'][source].update(history=[{}]),
                       lambda s: s['records'][source].update(history=[{'stage': 'other', 'decision': 'include', 'reason': '', 'decided_at': 'now', 'replaced_at': 'later'}]),
                       lambda s: s['records'].update({'f' * 32: copy.deepcopy(s['records'][source])})):
            invalid = copy.deepcopy(state)
            mutate(invalid)
            with self.assertRaises(AppError):
                validate_backup(invalid, self.workspace, docs)
