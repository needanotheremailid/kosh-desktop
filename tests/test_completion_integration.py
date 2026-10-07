"""Real temporary-store completion routes and explicit metadata parity checks."""
import base64
import io
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zlib

import agent
from backend import AppError, Store, new_id
from bibliography import export_csl_json, export_ris, parse_bibliography
from completion import _bib_bytes
import mcp_server


class CompletionIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic completion integration'})['id']

    def note(self, body='Original synthetic widgets.'):
        return self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Synthetic draft', 'body': body})

    def result(self, note, selected, replacement, task='clarity'):
        preview = {'preview_id': new_id(), 'workspace_id': self.workspace, 'provider': 'claude', 'task': task, 'prompt': 'Synthetic fixture only', 'note_id': note['id'], 'version': note['version'], 'selected_text': selected, 'expires_at': int(time.time()) + 300, 'consent_version': 1}
        self.store.assistance.register(preview)
        self.store.assistance.start(preview['preview_id'])
        result = {'result_id': new_id(), 'workspace_id': self.workspace, 'provider': 'claude', 'task': task, 'note_id': note['id'], 'version': note['version'], 'proposal': replacement}
        self.store.assistance.finish(preview['preview_id'], result)
        return result

    def apply(self, result, selected, version=None):
        return self.store.dispatch('POST', '/api/assist/apply', {'result_id': result['result_id'], 'expected_version': result['version'] if version is None else version, 'selected_text': selected})

    def test_apply_keeps_emoji_surroundings_markers_and_saved_revision(self):
        marker = '[[source:' + 'a' * 32 + ':2]]'
        selected = '🚀 Synthetic widgets ' + marker
        note = self.note('Before 🙂 ' + selected + ' after.')
        result = self.result(note, selected, '🚀 Reviewed widgets ' + marker)
        saved = self.apply(result, selected)
        self.assertEqual(saved['body'], 'Before 🙂 🚀 Reviewed widgets ' + marker + ' after.')
        self.assertEqual(saved['version'], 2)
        previous = json.loads(self.store.db.execute("SELECT payload FROM revisions WHERE entity_type='note' AND entity_id=?", (note['id'],)).fetchone()[0])
        self.assertEqual(previous['body'], note['body'])
        with self.assertRaises(AppError) as stale:
            self.apply(result, selected)
        self.assertEqual(stale.exception.status, 409)

    def test_apply_refuses_unknown_stale_wrong_selection_and_marker_changes(self):
        with self.assertRaises(AppError) as missing:
            self.apply({'result_id': 'f' * 32, 'version': 1}, 'Widgets')
        self.assertEqual(missing.exception.status, 404)
        marker = '[[source:' + 'b' * 32 + ':1]]'
        note = self.note('Widgets ' + marker)
        result = self.result(note, note['body'], 'Reviewed widgets without a marker')
        with self.assertRaises(AppError) as marker_error:
            self.apply(result, note['body'])
        self.assertEqual(marker_error.exception.status, 409)
        with self.assertRaises(AppError) as selection:
            self.apply(result, 'Different selected writing')
        self.assertEqual(selection.exception.status, 409)
        self.assertEqual(self.store.db.execute('SELECT body FROM notes WHERE id=?', (note['id'],)).fetchone()[0], note['body'])

    def test_apply_refuses_repeated_selection_and_nonreplacement_task(self):
        note = self.note('Widgets. Widgets.')
        result = self.result(note, 'Widgets.', 'Reviewed widgets.')
        with self.assertRaises(AppError) as repeated:
            self.apply(result, 'Widgets.')
        self.assertEqual(repeated.exception.status, 409)
        result = self.result(note, 'Widgets.', 'An outline', task='outline')
        with self.assertRaises(AppError) as task:
            self.apply(result, 'Widgets.')
        self.assertEqual(task.exception.status, 400)
        for task_name in ('continue', 'abstract'):
            result = self.result(note, 'Widgets.', 'A separate generated text', task=task_name)
            with self.assertRaises(AppError):
                self.apply(result, 'Widgets.')

    def figure(self):
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\x20\x40\x60')) + chunk(b'IEND', b'')
        return self.store.dispatch('POST', '/api/assets/import', {'workspace_id': self.workspace, 'name': 'synthetic figure.png', 'data': base64.b64encode(png).decode()})['results'][0]['document']

    def preview(self, note, workspace=None, version=None):
        return self.store.dispatch('POST', '/api/manuscript/preview', {'workspace_id': workspace or self.workspace, 'note_id': note['id'], 'version': note['version'] if version is None else version})['html']

    def test_manuscript_preview_is_inert_renders_owned_figure_and_writes_nothing(self):
        figure = self.figure()
        note = self.note('# Widgets\n\n<script>alert(1)</script> **bold** $x^2$\n\n![Synthetic figure](kosh-asset:' + figure['id'] + ')\n\n![Remote](https://example.invalid/private.png)')
        before = self.store._state(self.workspace)
        markup = self.preview(note)
        self.assertIn('&lt;script&gt;', markup)
        self.assertNotIn('<script>', markup)
        self.assertIn('<strong>bold</strong>', markup)
        self.assertIn('<math ', markup)
        self.assertIn('src="data:image/png;base64,', markup)
        self.assertNotIn('src="https:', markup)
        self.assertEqual(self.store._state(self.workspace), before)

    def test_manuscript_preview_refuses_foreign_missing_changed_and_oversized_figures(self):
        figure = self.figure()
        note = self.note('![Synthetic](kosh-asset:' + figure['id'] + ')')
        with self.assertRaises(AppError) as stale:
            self.preview(note, version=0)
        self.assertEqual(stale.exception.status, 409)
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other synthetic scope'})['id']
        foreign_note = self.store.dispatch('POST', '/api/notes', {'workspace_id': other, 'title': 'Foreign figure draft', 'body': note['body']})
        with self.assertRaises(AppError) as foreign:
            self.preview(foreign_note, workspace=other)
        self.assertEqual(foreign.exception.status, 404)
        missing = self.note('![Missing](kosh-asset:' + 'c' * 32 + ')')
        with self.assertRaises(AppError) as absent:
            self.preview(missing)
        self.assertEqual(absent.exception.status, 404)
        with patch('backend.FILE_LIMIT', 1):
            with self.assertRaises(AppError):
                self.preview(note)
        path = self.store.root / self.store._document(figure['id'])['path']
        path.write_bytes(b'Changed synthetic image')
        with self.assertRaises(AppError):
            self.preview(note)

    def test_explicit_editor_institution_report_and_thesis_fields_roundtrip(self):
        parsed = parse_bibliography('@techreport{r,title={Widget report},editor={Example, Ann and {Widget Group}},institution={Widget Institute},number={TR 42},type={Entered report subtype}}', 'bib')
        record = parsed['records'][0]
        self.assertEqual(record['editors'], 'Example, Ann; Widget Group')
        self.assertEqual(record['institution'], 'Widget Institute')
        self.assertEqual(record['report_number'], 'TR 42')
        self.assertEqual(record['thesis_type'], 'Entered report subtype')
        imported = self.store.dispatch('POST', '/api/bibliography/import', {'workspace_id': self.workspace, 'format': 'bib', 'text': '@mastersthesis{t,title={Widget thesis},school={Widget University},type={Entered masters thesis},editor={{Widget Editorial Group}}}'})['results'][0]['document']
        metadata = imported['metadata']
        self.assertEqual(metadata['institution'], 'Widget University')
        self.assertEqual(metadata['thesis_type'], 'Entered masters thesis')
        self.assertEqual(metadata['editors'], 'Widget Editorial Group')
        roundtrip = parse_bibliography(_bib_bytes(metadata).decode(), 'bib')['records'][0]
        for key in ('editors', 'institution', 'thesis_type'):
            self.assertEqual(roundtrip[key], metadata[key])
        csl = json.loads(export_csl_json([record]))[0]
        self.assertEqual(csl['editor'], [{'literal': 'Example, Ann; Widget Group'}])
        self.assertEqual(csl['number'], 'TR 42')

    def test_csl_editors_preserve_explicit_names_with_formatting_warning(self):
        text = json.dumps([{'id': 'book', 'type': 'book', 'title': 'Widget handbook', 'editor': [{'family': 'Example', 'given': 'Ann'}, {'literal': 'Widget Group'}], 'institution': 'Entered institute', 'number': 'R 12', 'genre': 'Entered thesis type'}])
        parsed = self.store.dispatch('POST', '/api/bibliography/preview', {'workspace_id': self.workspace, 'format': 'csljson', 'text': text})
        record = parsed['records'][0]
        self.assertEqual(record['editors'], 'Example, Ann; Widget Group')
        self.assertEqual(record['institution'], 'Entered institute')
        self.assertEqual(record['report_number'], 'R 12')
        self.assertEqual(record['thesis_type'], 'Entered thesis type')
        self.assertIn('editor', ' '.join(parsed['warnings']).lower())

    def test_book_ris_secondary_editors_are_retained_but_ambiguous_roles_are_not_guessed(self):
        book = parse_bibliography('TY  - BOOK\nTI  - Widgets\nA2  - Example, Ann\nA2  - Widget Group\nER  -', 'ris')['records'][0]
        self.assertEqual(book['editors'], 'Example, Ann; Widget Group')
        self.assertIn('A2  - Example, Ann; Widget Group', export_ris([book]))
        ambiguous = parse_bibliography('TY  - JOUR\nTI  - Widgets\nA2  - Uncertain secondary role\nER  -', 'ris')
        self.assertNotIn('editors', ambiguous['records'][0])
        self.assertTrue(ambiguous['warnings'])

    def test_cli_mcp_lookup_apply_fixed_routes_and_selected_file_bounds(self):
        class Client:
            calls = []
            def verify(self): return {'ready': True}
            def request(self, path, body=None, binary=False):
                self.calls.append((path, body))
                return {'ok': True}
            def redacted(self, value): return str(value)
        client = Client()
        args = agent.build_parser().parse_args(['literature-lookup', '--workspace', 'w', '--provider', 'crossref', '--identifier-type', 'doi', '--identifier', '10.1234/widgets'])
        agent.execute(args, client)
        self.assertEqual(client.calls[-1], ('/api/literature/lookup', {'workspace_id': 'w', 'provider': 'crossref', 'identifier_type': 'doi', 'identifier': '10.1234/widgets'}))
        selected = Path(self.temp.name) / 'selection.txt'
        selected.write_bytes('Widgets\r\n🙂'.encode())
        args = agent.build_parser().parse_args(['assist-apply', '--result', 'r', '--version', '1', '--selected-text-file', str(selected)])
        agent.execute(args, client)
        self.assertEqual(client.calls[-1][1]['selected_text'], 'Widgets\n🙂')
        result = mcp_server.Server(client=client).handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'kosh_assist_apply', 'arguments': {'result': 'r', 'version': 1, 'selected_text_file': str(selected)}}})
        self.assertFalse(result['result']['isError'])
        self.assertIn('kosh_literature_lookup', mcp_server.TOOLS)
        self.assertEqual(len(mcp_server.TOOLS), 50)
        selected.write_text('x' * 32_001, encoding='utf-8')
        with self.assertRaises(agent.AgentError):
            agent.execute(args, client)

    def test_csl_numeric_variables_and_digit_date_parts_remain_explicit(self):
        text = json.dumps([{'id': 'numeric', 'type': 'article-journal', 'title': 'Widgets', 'volume': 12, 'issue': 2.5, 'page': 101, 'edition': 3, 'issued': {'date-parts': [['2019', '3']]}}])
        parsed = self.store.dispatch('POST', '/api/bibliography/preview', {'workspace_id': self.workspace, 'format': 'csljson', 'text': text})
        self.assertEqual({key: parsed['records'][0][key] for key in ('volume', 'issue', 'pages', 'edition', 'year')}, {'volume': '12', 'issue': '2.5', 'pages': '101', 'edition': '3', 'year': '2019'})
        imported = self.store.dispatch('POST', '/api/bibliography/import', {'workspace_id': self.workspace, 'format': 'csljson', 'text': text})
        self.assertEqual(imported['imported'], 1)

    def test_csl_bad_record_does_not_drop_valid_rows_or_cross_stamp_warnings(self):
        text = json.dumps([{'id': 'first', 'type': 'article-journal', 'title': 'First widgets'},
                           {'id': 'bad', 'title': 'Invalid widgets', 'volume': True},
                           {'id': 'third', 'type': 'article-journal', 'title': 'Third widgets', 'volume': 12, 'unknown-field': 'Omitted'}])
        imported = self.store.dispatch('POST', '/api/bibliography/import', {'workspace_id': self.workspace, 'format': 'csljson', 'text': text})
        self.assertEqual([row['status'] for row in imported['results']], ['ready', 'error', 'ready'])
        self.assertEqual(imported['imported'], 2)
        first, third = imported['results'][0], imported['results'][2]
        self.assertNotIn('Record 3', first['document']['metadata']['provenance'])
        self.assertEqual(first['warnings'], [])
        self.assertIn('Record 3', third['document']['metadata']['provenance'])
        self.assertTrue(third['warnings'])

    def test_bibtex_record_warnings_are_not_copied_to_unrelated_records(self):
        imported = self.store.dispatch('POST', '/api/bibliography/import', {'workspace_id': self.workspace, 'format': 'bib', 'text': '@article{first,title={First widgets}}\n@article{second,title={Second widgets},unsupported={Omitted}}'})
        first, second = imported['results']
        self.assertEqual(first['warnings'], [])
        self.assertNotIn('second:', first['document']['metadata']['provenance'])
        self.assertIn('second:', second['document']['metadata']['provenance'])

    def test_warning_attribution_handles_macro_fields_and_colliding_record_keys(self):
        text = '@string{j = "Widget journal"}\n@article{a,title={First widgets}}\n@article{a:b,title={Second widgets},journal=j}\n@article{a/c,title={Third widgets},unsupported={Omitted}}'
        imported = self.store.dispatch('POST', '/api/bibliography/import', {'workspace_id': self.workspace, 'format': 'bib', 'text': text})
        first, second, third = imported['results']
        self.assertEqual(first['warnings'], [])
        self.assertIn('a:b/journal:', second['document']['metadata']['provenance'])
        self.assertNotIn('a/c:', second['document']['metadata']['provenance'])
        self.assertIn('a/c:', third['document']['metadata']['provenance'])
        self.assertNotIn('@string:', third['document']['metadata']['provenance'])


if __name__ == '__main__':
    unittest.main()
