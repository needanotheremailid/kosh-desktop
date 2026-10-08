"""Fixed CLI extension routing using fake clients and explicit synthetic files."""
import json
from pathlib import Path
import tempfile
import unittest

import agent


class Client:
    def __init__(self):
        self.calls = []

    def verify(self):
        return {'ready': True}

    def request(self, path, body=None, binary=False):
        self.calls.append((path, body, binary))
        return (b'Synthetic export', 'text/plain') if binary else {'ok': True}


class AgentExtensions(unittest.TestCase):
    def execute(self, argv):
        client = Client()
        agent.execute(agent.build_parser().parse_args(argv), client)
        exports = [call for call in client.calls if call[0] == '/api/export']
        return exports[-1] if exports else client.calls[-1]

    def test_citation_styles_list_and_import_use_fixed_local_routes(self):
        self.assertEqual(self.execute(['citation-styles']), ('/api/citation/styles', None, False))
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder) / 'selected.csl'
            selected.write_text('<style>synthetic XML</style>', encoding='utf-8')
            self.assertEqual(self.execute(['citation-style-import', '--file', str(selected)]),
                             ('/api/citation/styles/import', {'xml': '<style>synthetic XML</style>'}, False))

    def test_citation_style_import_rejects_oversize_and_non_utf8_before_request(self):
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder) / 'selected.csl'
            for content in (b'x' * (1024 * 1024 + 1), b'\xff\xfe\x80'):
                selected.write_bytes(content)
                client = Client()
                with self.assertRaises(agent.AgentError):
                    agent.execute(agent.build_parser().parse_args(['citation-style-import', '--file', str(selected)]), client)
                self.assertEqual(client.calls, [])

    def test_export_accepts_only_builtin_or_content_addressed_style_ids(self):
        style = 'csl-' + 'a' * 64
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'widgets.md'
            call=self.execute(['export', '--workspace', 'w', '--format', 'md', '--citation-style', style, '--output', str(target)])
            self.assertEqual(call[0],'/api/export')
            self.assertEqual(call[1]['citation_style'],style)
            self.assertEqual(call[1]['workspace_id'],'w')
            for bad in ('../outside.csl', 'https://styles.example/file', 'csl-' + 'a' * 63, 'csl-' + 'g' * 64):
                with self.assertRaises(agent.AgentError):
                    agent.build_parser().parse_args(['export', '--workspace', 'w', '--format', 'md', '--citation-style', bad, '--output', str(target)])

    def test_bibliography_commands_read_only_selected_utf8_file(self):
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder) / 'widgets.bib'
            selected.write_text('@article{x,title={Widgets}}', encoding='utf-8')
            for name in ('bibliography-preview', 'bibliography-import'):
                self.assertEqual(self.execute([name, '--workspace', 'w', '--format', 'bib', '--file', str(selected)]), ('/api/bibliography/' + name.split('-')[1], {'workspace_id': 'w', 'format': 'bib', 'text': '@article{x,title={Widgets}}'}, False))

    def test_scoped_recovery_and_archive_commands_use_fixed_routes(self):
        self.assertEqual(self.execute(['archive', '--document', 'd']), ('/api/archive', {'id': 'd', 'archived': True}, False))
        self.assertEqual(self.execute(['unarchive', '--document', 'd']), ('/api/archive', {'id': 'd', 'archived': False}, False))
        self.assertEqual(self.execute(['note-history', '--note', 'n']), ('/api/notes/history?id=n', None, False))
        self.assertEqual(self.execute(['assist-history', '--workspace', 'w']), ('/api/assist/history?workspace_id=w', None, False))
        self.assertEqual(self.execute(['assist-result', '--workspace', 'w', '--result', 'r']), ('/api/assist/result?workspace_id=w&result_id=r', None, False))
        self.assertEqual(self.execute(['state', '--workspace', 'w']), ('/api/state?workspace_id=w', None, False))

    def test_semantic_and_ocr_commands_preserve_model_scope_and_pages(self):
        self.assertEqual(self.execute(['retrieval-index', '--workspace', 'w', '--model', 'local:embed', '--document', 'd']), ('/api/retrieval/index', {'workspace_id': 'w', 'model': 'local:embed', 'document_ids': ['d']}, False))
        self.assertEqual(self.execute(['retrieval-search', '--workspace', 'w', '--model', 'local:embed', '--query', 'Widgets']), ('/api/retrieval/search', {'workspace_id': 'w', 'model': 'local:embed', 'query': 'Widgets'}, False))
        self.assertEqual(self.execute(['ocr', '--workspace', 'w', '--document', 'd', '--language', 'eng', '--page', '2', '--page', '4']), ('/api/ocr', {'workspace_id': 'w', 'document_id': 'd', 'language': 'eng', 'pages': [2, 4]}, False))
        self.assertEqual(self.execute(['catalogue-attach', '--workspace', 'w', '--catalogue', 'c', '--document', 'd', '--version', '2']), ('/api/catalogue/attach', {'workspace_id': 'w', 'catalogue_id': 'c', 'document_id': 'd', 'expected_metadata_version': 2}, False))

    def test_folder_agent_requires_explicit_paths_and_separate_send_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            call = self.execute(['folder-assist-preview', '--workspace', 'w', '--target', folder, '--path', 'widgets.md', '--provider', 'claude', '--instruction', 'Improve widgets.'])
        self.assertEqual(call[0], '/api/folder-assist/preview')
        self.assertEqual(call[1]['paths'], ['widgets.md'])
        self.assertEqual(call[1]['instruction'], 'Improve widgets.')
        self.assertEqual(self.execute(['folder-assist-run', '--preview', 'p', '--consent-to-provider-send']), ('/api/folder-assist/run', {'preview_id': 'p', 'consent': True, 'consent_version': 1}, False))
        with self.assertRaises(agent.AgentError):
            agent.build_parser().parse_args(['folder-assist-run', '--preview', 'p'])

    def test_explicit_asset_import_and_writing_instructions_have_no_generic_route(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'widgets.png'
            image.write_bytes(b'Synthetic transport bytes')
            route, payload, binary = self.execute(['asset-import', '--workspace', 'w', '--file', str(image)])
        self.assertEqual(route, '/api/assets/import')
        self.assertEqual(payload['name'], 'widgets.png')
        self.assertEqual(payload['workspace_id'], 'w')
        self.assertFalse(binary)
        self.assertEqual(self.execute(['assist-preview', '--workspace', 'w', '--provider', 'claude', '--question', 'Widgets?', '--custom-instructions', 'Preserve terminology.'])[1]['custom_instructions'], 'Preserve terminology.')

    def test_extended_exports_keep_no_clobber_and_transmit_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            for format in ('ris', 'csljson', 'html', 'share', 'texzip'):
                target = Path(folder) / ('widgets.' + format)
                call=self.execute(['export', '--workspace', 'w', '--format', format, '--audit', '--output', str(target)])
                self.assertEqual(call,('/api/export',{'workspace_id':'w','format':format,'citation_style':'vancouver','audit':'1','note_placement':'footnote','word_style':'ieee'},True))
                self.assertEqual(target.read_bytes(), b'Synthetic export')
                with self.assertRaises(agent.AgentError):
                    self.execute(['export', '--workspace', 'w', '--format', format, '--output', str(target)])


    def test_export_names_incomplete_references_for_draft_and_workspace(self):
        missing = {'document_id': 'a' * 32, 'name': 'invented.pdf', 'fields': ['year']}
        class Reviewing(Client):
            def request(inner, path, body=None, binary=False):
                inner.calls.append((path, body, binary))
                if binary:
                    return (b'Synthetic export', 'text/plain')
                if path.startswith('/api/project-review'):
                    return {'notes': [{'missing_metadata': [missing]}, {'missing_metadata': [missing]}], 'totals': {'failed_checks': 0}}
                if path.startswith('/api/state'):
                    return {'notes': [{'id': 'n', 'version': 4}]}
                return {'missing_metadata': [missing]}
        with tempfile.TemporaryDirectory() as folder:
            client = Reviewing()
            result = agent.execute(agent.build_parser().parse_args(['export', '--workspace', 'w', '--format', 'docx', '--output', str(Path(folder) / 'all.docx')]), client)
            self.assertEqual(result['incomplete_references'], [missing])
            self.assertIn('incomplete', result['warning'])
            self.assertTrue(client.calls[-1][0].startswith('/api/project-review?'))
            client = Reviewing()
            result = agent.execute(agent.build_parser().parse_args(['export', '--workspace', 'w', '--note', 'n', '--format', 'pdf', '--output', str(Path(folder) / 'draft.pdf')]), client)
            self.assertEqual(client.calls[-1], ('/api/writing-check', {'workspace_id': 'w', 'note_id': 'n', 'version': 4}, False))
            self.assertEqual(len(result['incomplete_references']), 1)
            client = Reviewing()
            result = agent.execute(agent.build_parser().parse_args(['export', '--workspace', 'w', '--format', 'csv', '--output', str(Path(folder) / 'evidence.csv')]), client)
            self.assertNotIn('warning', result)
            self.assertEqual(len(client.calls), 1)


if __name__ == '__main__':
    unittest.main()
