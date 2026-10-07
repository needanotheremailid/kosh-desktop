"""Synthetic writing/export checks. No private documents or real models."""
import base64
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import agent
from backend import AppError, Store
from server import LocalServer


class WritingFeatures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Café & draft_1'})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def source(self, workspace=None, name='source.txt', content=b'Fixture source only'):
        receipt = self.store.dispatch('POST', '/api/import', {
            'workspace_id': (workspace or self.workspace)['id'],
            'files': [{'name': name, 'data': base64.b64encode(content).decode('ascii')}]})
        return receipt['results'][0]['document']

    def note(self, body):
        return self.store.dispatch('POST', '/api/notes', {
            'workspace_id': self.workspace['id'], 'title': 'Draft', 'body': body})

    def check(self, note, **changes):
        return self.store.dispatch('POST', '/api/writing-check', {
            'workspace_id': self.workspace['id'], 'note_id': note['id'],
            'version': note['version'], **changes})

    def test_tex_resolves_refs_and_escapes_commands_without_mutation(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {
            'title': 'Widgets & units', 'authors': 'Example Author', 'year': '2024'}})
        self.note('# Heading\nCafé — 10% & value_x $raw$ {text} ~ ^ \\input{private}\n\n- First item\n- Second item\n\n1. One\n2. Two\n\nCitation [[source:' + source['id'] + ':1]]\n[[source:missing:2]]')
        before = self.store.dispatch('GET', '/api/state')
        data, mime, filename = self.store.file_response('/api/export', {
            'workspace_id': self.workspace['id'], 'format': 'tex'})
        tex = data.decode('utf-8')
        self.assertEqual(mime, 'application/x-tex; charset=utf-8')
        self.assertEqual(filename, 'Research-workspace.tex')
        self.assertIn('\\documentclass[11pt]{article}', tex)
        self.assertIn('\\usepackage{fontspec}', tex)
        self.assertIn('\\section*{Café \\& draft\\_1}', tex)
        self.assertIn('Café — 10\\% \\& value\\_x $raw$ \\{text\\}', tex)
        self.assertIn('\\textbackslash{}input\\{private\\}', tex)
        self.assertNotIn('\\input{private}', tex)
        self.assertIn('\\begin{itemize}', tex)
        self.assertIn('\\begin{enumerate}', tex)
        self.assertIn('Citation (1)', tex)
        self.assertNotIn('text unit', tex)
        self.assertIn('Widgets \\& units', tex)
        self.assertIn('Unresolved source reference: missing:2', tex)
        self.assertIn('\\subsection*{References}', tex)
        self.assertNotIn('Export review notes', tex)
        self.assertNotIn('Unstructured author text retained literally', tex)
        audited = self.store.file_response('/api/export', {
            'workspace_id': self.workspace['id'], 'format': 'tex', 'audit': '1'})[0].decode('utf-8')
        self.assertIn('\\subsection*{Export review notes}', audited)
        self.assertIn('Unstructured author text retained literally; verify names.', audited)
        self.assertIn(source['id'] + ': text unit 1', audited)
        self.assertTrue(tex.rstrip().endswith('\\end{document}'))
        self.assertEqual(self.store.dispatch('GET', '/api/state'), before)

    def test_writing_check_reports_exact_saved_diagnostics_and_no_writes(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'title': 'Fixture'}})
        note = self.note('# Introduction\nCafé widgets [[source:' + source['id'] + ':1]]\n## Methods\nOne test.\n[[source:' + source['id'] + ':99]]\n[[source:missing:2]]\n[[source:unfinished')
        before = self.store.dispatch('GET', '/api/state')
        revisions = self.store.db.execute('SELECT count(*) FROM revisions').fetchone()[0]
        result = self.check(note)
        self.assertEqual(result['word_count'], 6)
        self.assertEqual(result['headings'], [
            {'level': 1, 'text': 'Introduction', 'line': 1},
            {'level': 2, 'text': 'Methods', 'line': 3}])
        self.assertEqual(result['references'][0]['page'], 1)
        self.assertEqual(result['references'][0]['kind'], 'txt')
        self.assertEqual(result['references'][0]['line'], 2)
        self.assertEqual([r['reason'] for r in result['unresolved_references']],
                         ['Page or text unit is outside this source.', 'Malformed source marker.', 'Malformed source marker.'])
        self.assertEqual(result['missing_metadata'], [{'document_id': source['id'], 'name': 'source.txt', 'fields': ['authors', 'year', 'doi']}])
        self.assertEqual(result['note_id'], note['id'])
        self.assertEqual(result['version'], 1)
        self.assertNotIn('score', result)
        self.assertEqual(self.store.dispatch('GET', '/api/state'), before)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM revisions').fetchone()[0], revisions)

    def test_writing_check_refuses_stale_wrong_type_and_foreign_note(self):
        note = self.note('Saved draft')
        for version in (0, 2, None, True, '1'):
            with self.subTest(version=version), self.assertRaises(AppError) as error:
                self.check(note, version=version)
            self.assertEqual(error.exception.status, 409)
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})
        with self.assertRaises(AppError) as error:
            self.check(note, workspace_id=other['id'])
        self.assertEqual(error.exception.status, 404)

    def test_scoped_sources_are_validated_without_reading_foreign_sources(self):
        local = self.source()
        other = self.store.dispatch('POST', '/api/workspaces', {'title': 'Other'})
        foreign = self.source(other, 'foreign.txt', b'Different fixture source')
        note = self.note('Local [[source:' + local['id'] + ':1]] Foreign [[source:' + foreign['id'] + ':1]]')
        with patch.object(self.store, '_bytes', wraps=self.store._bytes) as read:
            result = self.check(note)
        self.assertEqual([call.args[0]['id'] for call in read.call_args_list], [local['id']])
        self.assertEqual(result['unresolved_references'][0]['reason'], 'Source is not in this workspace.')
        managed = self.store.root / self.store._document(local['id'])['path']
        managed.write_bytes(b'Fixture source changed')
        for operation in (lambda: self.check(note), lambda: self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'tex'})):
            with self.assertRaises(AppError) as error:
                operation()
            self.assertEqual(error.exception.status, 409)

    def test_cli_parses_tex_and_sends_scoped_writing_check(self):
        args = agent.build_parser().parse_args(['export', '--workspace', 'w', '--format', 'tex', '--output', str(Path(self.temp.name) / 'draft.tex')])
        self.assertEqual(args.format, 'tex')
        args = agent.build_parser().parse_args(['writing-check', '--workspace', 'w', '--note', 'n', '--version', '4'])
        class Client:
            def verify(self):
                return {'app': agent.APP_ID}
            def request(self, path, body=None):
                self.called = (path, body)
                return {'note_id': 'n', 'version': 4}
        client = Client()
        result = agent.execute(args, client)
        self.assertEqual(client.called, ('/api/writing-check', {'workspace_id': 'w', 'note_id': 'n', 'version': 4}))
        self.assertEqual(result['version'], 4)
        args.version = 0
        with self.assertRaises(agent.AgentError):
            agent.execute(args, client)

    def test_real_http_cli_check_export_and_stale_conflict(self):
        source = self.source()
        note = self.note('Saved fixture [[source:' + source['id'] + ':1]]')
        server = LocalServer(('127.0.0.1', 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = agent.Client({'port': server.server_port, 'token': server.token, 'build': server.build})
        try:
            args = agent.build_parser().parse_args(['writing-check', '--workspace', self.workspace['id'], '--note', note['id'], '--version', '1'])
            result = agent.execute(args, client)
            self.assertEqual(result['word_count'], 2)
            self.assertEqual(result['references'][0]['document_id'], source['id'])
            target = Path(self.temp.name) / 'actual-export.tex'
            args = agent.build_parser().parse_args(['export', '--workspace', self.workspace['id'], '--format', 'tex', '--output', str(target)])
            result = agent.execute(args, client)
            self.assertEqual(result['content_type'], 'application/x-tex; charset=utf-8')
            self.assertIn('Saved fixture (1)', target.read_text(encoding='utf-8'))
            self.assertNotIn('text unit', target.read_text(encoding='utf-8'))
            self.store.dispatch('POST', '/api/notes', {**note, 'body': 'A newer saved note'})
            with self.assertRaises(agent.AgentError) as error:
                client.request('/api/writing-check', {'workspace_id': self.workspace['id'], 'note_id': note['id'], 'version': 1})
            self.assertEqual(error.exception.status, 409)
            client.token = 'incorrect_synthetic_session'
            with self.assertRaises(agent.AgentError) as error:
                client.request('/api/writing-check', {'workspace_id': self.workspace['id'], 'note_id': note['id'], 'version': 2})
            self.assertEqual(error.exception.status, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_numeric_citations_follow_first_use_with_same_number_on_repeat(self):
        first = self.source(name='first.txt', content=b'First imported fixture')
        second = self.source(name='second.txt', content=b'Second imported fixture')
        for source, title in ((first, 'First title'), (second, 'Second title')):
            self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'title': title, 'authors': 'Example Author', 'author_list':[{'family':'Author','given':'Example'}], 'year': '2024'}})
        body = 'Start [[source:' + second['id'] + ':1]] then [[source:' + first['id'] + ':1]] repeated [[source:' + second['id'] + ':1]]'
        note = self.note(body)
        for style in ('vancouver', 'ieee'):
            with self.subTest(style=style):
                result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': style})[0].decode()
                citation_text = 'Start (1) then (2) repeated (1)' if style == 'vancouver' else 'Start [1] then [2] repeated [1]'
                self.assertIn(citation_text, result)
                self.assertNotIn('text unit', result)
                references = result.split('## References')[1]
                self.assertLess(references.index('Second title'), references.index('First title'))
                self.assertNotIn('Export review notes', result)
                expected_reference = '1. Author E. Second title. 2024.' if style == 'vancouver' else '[1] E. Author, “Second title,” 2024.'
                self.assertIn(expected_reference, references)
        saved = self.store.dispatch('GET', '/api/state')['notes'][0]
        self.assertEqual(saved['body'], body)
        self.assertEqual(saved['version'], note['version'])

    def test_apa_entered_metadata_missing_fields_and_same_year_disambiguation(self):
        first = self.source(name='one.txt', content=b'One source')
        second = self.source(name='two.txt', content=b'Two source')
        missing = self.source(name='missing.txt', content=b'Unspecified source')
        for source, title in ((first, 'Alpha title'), (second, 'Beta title')):
            self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'title': title, 'authors': 'Example Author', 'author_list':[{'family':'Author','given':'Example'}], 'year': '2024'}})
        self.note('First [[source:' + second['id'] + ':1]] Again [[source:' + first['id'] + ':1]] Missing [[source:' + missing['id'] + ':1]]')
        result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa'})[0].decode()
        self.assertIn('(Author, 2024b)', result)
        self.assertIn('(Author, 2024a)', result)
        # CSL does not manufacture placeholder publication fields. The APA
        # date term remains visible; missing metadata stays explicit in audit.
        self.assertIn('Missing (n.d.)', result)
        self.assertIn('Author, E. (2024a). *Alpha title*.', result)
        self.assertIn('(N.d.).', result)
        audited = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa', 'audit': '1'})[0].decode()
        self.assertIn(missing['id'] + ': Author metadata missing.', audited)
        self.assertIn(missing['id'] + ': Missing bibliographic fields: title, year.', audited)
        self.assertNotIn('text unit', result)
        self.assertNotIn('Export review notes', result)

    def test_styles_propagate_through_docx_pdf_tex_and_data_exports_stay_stable(self):
        import io
        import pymupdf
        from docx import Document
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'title': 'Literal & title', 'authors': 'Example Author', 'year': '2024'}})
        self.note('Citation [[source:' + source['id'] + ':1]]')
        for format_ in ('docx', 'pdf', 'tex'):
            data = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': format_, 'citation_style': 'apa'})[0]
            if format_ == 'docx':
                text = '\n'.join(p.text for p in Document(io.BytesIO(data)).paragraphs)
            elif format_ == 'pdf':
                with pymupdf.open(stream=data, filetype='pdf') as pdf:
                    text = '\n'.join(page.get_text() for page in pdf)
                self.assertNotIn('\ufd3e', text)
                self.assertNotIn('\ufd3f', text)
            else:
                text = data.decode()
                self.assertIn('Literal \\& title', text)
            self.assertIn('Citation (Example Author, 2024)', text)
            self.assertNotIn('text unit', text)
            self.assertNotIn('Export review notes', text)
        for format_ in ('bib', 'csv'):
            baseline = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': format_})[0]
            alternate = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': format_, 'citation_style': 'apa'})[0]
            self.assertEqual(alternate, baseline)
        with self.assertRaises(AppError):
            self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'invented-style'})

    def test_real_cli_citation_style_is_transmitted(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'title': 'Fixture', 'authors': 'Example Author', 'year': '2024'}})
        self.note('Citation [[source:' + source['id'] + ':1]]')
        server = LocalServer(('127.0.0.1', 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = agent.Client({'port': server.server_port, 'token': server.token, 'build': server.build})
        try:
            target = Path(self.temp.name) / 'apa-draft.md'
            args = agent.build_parser().parse_args(['export', '--workspace', self.workspace['id'], '--format', 'md', '--citation-style', 'apa', '--output', str(target)])
            agent.execute(args, client)
            self.assertIn('Citation (Example Author, 2024)', target.read_text(encoding='utf-8'))
            self.assertNotIn('text unit', target.read_text(encoding='utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_structured_journal_metadata_formats_vancouver_and_checks_missing_fields(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {
            'title': 'Fixture article', 'authors': 'Legacy literal', 'year': '2024',
            'type': 'journal_article', 'journal': 'Fixture Journal',
            'journal_abbreviation': 'Fixture J', 'volume': '12', 'issue': '3', 'pages': '45-49',
            'doi': '10.1234/fixture',
            'author_list': [{'family': 'Smith', 'given': 'John Peter'}, {'family': 'Doe', 'given': 'Jane'}]}})
        note = self.note('Citation [[source:' + source['id'] + ':1]]')
        md = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md'})[0].decode()
        # Official NLM parent uses minimal page ranges and compact DOI prefix.
        self.assertIn('1. Smith JP, Doe J. Fixture article. Fixture J. 2024;12(3):45–9. doi:10.1234/fixture', md)
        self.assertNotIn('Author formatting needs review', md)
        self.assertEqual(self.check(note)['missing_metadata'], [])
        metadata = self.store._document(source['id'])['metadata']
        metadata['journal'] = ''
        metadata['journal_abbreviation'] = ''
        metadata['volume'] = ''
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': metadata})
        self.assertEqual(self.check(note)['missing_metadata'][0]['fields'], ['journal', 'volume'])
        md = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md'})[0].decode()
        self.assertNotIn('Fixture J.', md)
        audited = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'audit': '1'})[0].decode()
        self.assertIn(source['id'] + ': Missing bibliographic fields: journal, volume.', audited)
        with self.assertRaises(AppError):
            self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'author_list': [{'name': 'Invented shape'}]}})

    def test_clean_bibliography_separates_provenance_and_apa_doi_review(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {
            'title': 'Fixture title', 'authors': 'Literal Author', 'year': '2024', 'doi': 'doi:10.1234/example'}})
        self.note('Citation [[source:' + source['id'] + ':1]] and [[source:missing:2]]')
        result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa'})[0].decode()
        bibliography = result.split('## References')[1]
        self.assertIn('https://doi.org/10.1234/example', bibliography)
        self.assertNotIn('Imported file:', bibliography)
        self.assertNotIn('Unstructured author text retained literally', bibliography)
        self.assertNotIn('Export review notes', result)
        audited = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa', 'audit': '1'})[0].decode()
        audited_bibliography, review = audited.split('## References')[1].split('## Export review notes')
        self.assertEqual(audited_bibliography.strip(), bibliography.strip())
        self.assertIn('Unstructured author text retained literally; verify names.', review)
        self.assertIn(source['id'] + ': text unit 1', review)
        self.assertIn('Unresolved source reference: missing:2', result)
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'doi': 'invalid-entered-doi'}})
        result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa'})[0].decode()
        self.assertNotIn('https://doi.org/invalid-entered-doi', result)
        self.assertNotIn('invalid-entered-doi', result)
        self.assertNotIn('DOI format needs review', result)
        audited = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'md', 'citation_style': 'apa', 'audit': '1'})[0].decode()
        self.assertIn('DOI format needs review; entered value retained.', audited.split('## Export review notes')[1])
        self.assertIn('Entered DOI: invalid-entered-doi.', audited.split('## Export review notes')[1])
        self.assertEqual(self.store._document(source['id'])['metadata']['doi'], 'invalid-entered-doi')

    def test_bibtex_exports_entered_publication_and_structured_authors_only(self):
        source = self.source()
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {
            'type': 'journal_article', 'title': 'Fixture {article}', 'authors': 'Preserved legacy authors',
            'author_list': [{'family': 'Smith', 'given': 'John Peter'}, {'family': 'Doe', 'given': 'Jane'}],
            'year': '2024', 'journal': 'Fixture Journal', 'volume': '12', 'issue': '3', 'pages': '45-49'}})
        result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'bib'})[0].decode()
        self.assertIn('@article{Kosh' + source['id'] + ',', result)
        self.assertIn('author = {Smith, John Peter and Doe, Jane}', result)
        self.assertIn('journal = {Fixture Journal}', result)
        self.assertIn('volume = {12}', result)
        self.assertIn('number = {3}', result)
        self.assertIn('pages = {45-49}', result)
        self.assertIn('title = {Fixture \\{article\\}}', result)
        self.assertNotIn('doi =', result)
        self.assertEqual(self.store._document(source['id'])['metadata']['authors'], 'Preserved legacy authors')
        self.store.dispatch('POST', '/api/metadata', {'id': source['id'], 'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata': {'authors': 'Legacy Author A; Legacy Author B'}})
        result = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'format': 'bib'})[0].decode()
        self.assertIn('author = {{Legacy Author A; Legacy Author B}}', result)
        self.assertNotIn('journal =', result)

    def test_selected_draft_export_excludes_other_notes_matrix_and_uncited_references(self):
        cited=self.source(name='cited.txt')
        unused=self.source(name='unused.txt',content=b'Unused source')
        chosen=self.note('Chosen paragraph [[source:'+cited['id']+':1]]')
        self.note('Other secret draft [[source:'+unused['id']+':1]]')
        self.store.dispatch('POST','/api/matrix',{'workspace_id':self.workspace['id'],'document_id':unused['id'],'question':'Unrelated evidence','design':'','findings':'','limitations':''})
        data,_,filename=self.store.file_response('/api/export',{'workspace_id':self.workspace['id'],'note_id':chosen['id'],'format':'tex'})
        text=data.decode()
        self.assertEqual(filename,'Kosh-draft.tex')
        self.assertIn('Chosen paragraph (1)',text)
        self.assertNotIn('text unit',text)
        self.assertNotIn('Other secret',text)
        self.assertNotIn('Unrelated evidence',text)
        self.assertNotIn('unused.txt',text)
        self.assertIn('\\subsection*{References}\n1.',text)
        audited = self.store.file_response('/api/export', {'workspace_id': self.workspace['id'], 'note_id': chosen['id'], 'format': 'tex', 'audit': '1'})[0].decode()
        self.assertIn(cited['id'] + ': Author metadata missing.', audited)
        self.assertIn(cited['id'] + ': Missing bibliographic fields: title, year.', audited)
        self.assertNotIn(unused['id'], audited)
        other=self.store.dispatch('POST','/api/workspaces',{'title':'Other'})
        with self.assertRaises(AppError) as error:
            self.store.file_response('/api/export',{'workspace_id':other['id'],'note_id':chosen['id'],'format':'md'})
        self.assertEqual(error.exception.status,404)

    def test_matrix_source_citation_has_no_invented_locator_and_title_punctuation_is_preserved(self):
        source=self.source()
        self.store.dispatch('POST','/api/metadata',{'id':source['id'],'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata':{'title':'Does it work?','authors':'Literal Authors.','year':'2024'}})
        self.store.dispatch('POST','/api/matrix',{'workspace_id':self.workspace['id'],'document_id':source['id'],'question':'A question','design':'','findings':'','limitations':''})
        text=self.store.file_response('/api/export',{'workspace_id':self.workspace['id'],'format':'md'})[0].decode()
        self.assertIn('### source.txt (1)',text)
        self.assertNotIn('text unit',text.split('### source.txt')[1].split('## References')[0])
        self.assertIn('1. Literal Authors. Does it work? 2024.',text)
        self.assertNotIn('Authors..',text)
        self.store.dispatch('POST','/api/metadata',{'id':source['id'],'expected_metadata_version': self.store._document(source['id'])['metadata_version'], 'metadata':{'title':'A & B_2 10% # $ ~ ^','authors':'Group and Team'}})
        bib=self.store.file_response('/api/export',{'workspace_id':self.workspace['id'],'format':'bib'})[0].decode()
        self.assertIn(r'A \& B\_2 10\% \# \$ \textasciitilde{} \textasciicircum{}',bib)
        self.assertIn('author = {{Group and Team}}',bib)


if __name__ == '__main__':
    unittest.main()
