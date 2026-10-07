"""Explicit agent consent and proposal boundaries, using synthetic content only."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import AppError, Store, agent_arguments


class AssistAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title':'Synthetic assist'})['id']
        self.document = self.store.dispatch('POST', '/api/import', {'workspace_id':self.workspace,'files':[{'name':'fixture.txt','data':base64.b64encode(b'Thirty synthetic widgets were observed.').decode()}]})['results'][0]['document']['id']
        self.note = self.store.dispatch('POST', '/api/notes', {'workspace_id':self.workspace,'title':'Original','body':'A long synthetic sentence about widgets.'})
        self.providers = patch('backend.installed_agents', return_value=[{'id':'claude','available':True,'label':'Claude Code'}])
        self.providers.start()

    def tearDown(self):
        self.providers.stop()
        self.store.close()
        self.temp.cleanup()

    def preview(self, **extra):
        return self.store.dispatch('POST', '/api/assist/preview', {'workspace_id':self.workspace,'provider':'claude','task':'ask','question':'How many widgets?',**extra})

    def send(self, preview):
        return self.store.dispatch('POST', '/api/assist/run', {'preview_id':preview['preview_id'],'consent':True,'consent_version':1})

    def test_preview_contains_exact_context_without_execution(self):
        with patch('backend.run_installed_agent') as run:
            preview = self.preview()
            self.assertIn('Thirty synthetic widgets', preview['prompt'])
            self.assertNotIn('A long synthetic sentence', preview['prompt'])
            self.assertEqual(preview['citations'][0]['document_id'],self.document)
            run.assert_not_called()

    def test_consent_required_and_preview_consumed_once(self):
        preview=self.preview()
        with patch('backend.run_installed_agent',return_value='Thirty widgets. [C1]') as run:
            with self.assertRaises(AppError):
                self.store.dispatch('POST','/api/assist/run',{'preview_id':preview['preview_id']})
            result=self.send(preview)
            self.assertEqual(result['citations'][0]['id'],'C1')
            self.assertFalse(result['claim_entailment_verified'])
            self.assertEqual(self.send(preview)['result_id'], result['result_id'])
            self.assertEqual(run.call_count,1)
        self.assertEqual(len(self.store.dispatch('GET','/api/state')['notes']),1)

    def test_selected_passage_requires_exact_source_and_workspace(self):
        with self.assertRaises(AppError): self.preview(selected_source={'document_id':self.document,'page':1,'text':'Invented passage'})
        other=self.store.dispatch('POST','/api/workspaces',{'title':'Other'})['id']
        with self.assertRaises(AppError): self.preview(workspace_id=other,selected_source={'document_id':self.document,'page':1,'text':'Thirty synthetic widgets'})
        preview=self.preview(selected_source={'document_id':self.document,'page':1,'text':'Thirty synthetic widgets'})
        self.assertEqual(preview['citations'][0]['text'],'Thirty synthetic widgets')

    def test_stale_note_prevents_send_and_alternative_never_overwrites(self):
        payload={'task':'shorten','note_id':self.note['id'],'version':1,'selected_text':'A long synthetic sentence about widgets.'}
        preview=self.preview(**payload)
        self.store.dispatch('POST','/api/notes',{**self.note,'body':'Changed concurrently.'})
        with patch('backend.run_installed_agent') as run:
            with self.assertRaises(AppError): self.send(preview)
            run.assert_not_called()
        current=self.store.dispatch('GET','/api/state')['notes'][0]
        preview=self.preview(**{**payload,'version':current['version'],'selected_text':current['body']})
        with patch('backend.run_installed_agent',return_value='Short proposal.'):
            result=self.send(preview)
        saved=self.store.dispatch('POST','/api/assist/save-alternative',{'result_id':result['result_id'],'expected_version':current['version']})
        self.assertNotEqual(saved['id'],self.note['id'])
        self.assertEqual(saved['body'],'Short proposal.')
        self.assertEqual(next(n for n in self.store.dispatch('GET','/api/state')['notes'] if n['id']==self.note['id'])['body'],'Changed concurrently.')

    def test_unknown_citation_marked_unsupported(self):
        preview=self.preview()
        with patch('backend.run_installed_agent',return_value='A claim. [C99]'):
            result=self.send(preview)
        self.assertEqual(result['citations'],[])
        self.assertIn('unsupported',result['warning'].lower())

    def test_unknown_provider_and_arbitrary_command_rejected(self):
        with self.assertRaises(AppError): self.preview(provider='powershell')
        with self.assertRaises(AppError): self.preview(command='anything')

    def test_expiry_refuses_send(self):
        preview=self.preview()
        with patch('backend.time.time',return_value=10**12),patch('backend.run_installed_agent') as run:
            with self.assertRaises(AppError): self.send(preview)
            run.assert_not_called()

    def test_local_excerpt_scope_uses_exact_selection(self):
        result=self.store.dispatch('POST','/api/ask',{'workspace_id':self.workspace,'question':'What is shown?','model':'','selected_source':{'document_id':self.document,'page':1,'text':'Thirty synthetic widgets'}})
        self.assertEqual(result['mode'],'retrieval')
        self.assertEqual(result['citations'][0]['text'],'Thirty synthetic widgets')
        with self.assertRaises(AppError):
            self.store.dispatch('POST','/api/ask',{'workspace_id':self.workspace,'question':'What?','selected_source':{'document_id':self.document,'page':1,'text':'Invented'}})

    def test_fixed_agent_arguments_disable_tools_and_persistence(self):
        directory=Path(self.temp.name)
        codex=agent_arguments('codex','trusted-codex.exe',directory)
        self.assertIn('--ignore-user-config',codex)
        self.assertIn('--ephemeral',codex)
        self.assertEqual(codex[codex.index('--sandbox')+1],'read-only')
        for feature in ('shell_tool','unified_exec','hooks','multi_agent'):
            self.assertEqual(codex[codex.index(feature)-1],'--disable')
        claude=agent_arguments('claude','trusted-claude.exe',directory)
        self.assertEqual(claude[claude.index('--tools')+1],'')
        self.assertIn('--restricted',claude)
        self.assertIn('--strict-mcp-config',claude)
        self.assertIn('--no-session-persistence',claude)

    def test_catalogue_reference_preserves_metadata_and_workspace_binding(self):
        import literature
        service=literature.SearchService()
        self.store.literature=service
        item=literature.record('crossref','10.1234/example','Synthetic publication',authors='Example, Ann',author_list=[{'family':'Example','given':'Ann'}],year='2025',journal='Synthetic Journal',volume='3',pages='10-12',type='journal_article',url='https://doi.org/10.1234/example')
        with patch('literature.crossref',return_value=(1,[item])):
            results=self.store.dispatch('POST','/api/literature/search',{'workspace_id':self.workspace,'provider':'crossref','query':'synthetic widgets'})
        result_id=results['results'][0]['result_id']
        other=self.store.dispatch('POST','/api/workspaces',{'title':'Other'})['id']
        with self.assertRaises(AppError):
            self.store.dispatch('POST','/api/literature/save',{'workspace_id':other,'result_id':result_id})
        saved=self.store.dispatch('POST','/api/literature/save',{'workspace_id':self.workspace,'result_id':result_id})['document']
        self.assertEqual(saved['kind'],'bib')
        self.assertEqual(saved['metadata']['title'],'Synthetic publication')
        self.assertEqual(saved['metadata']['author_list'],[{'family':'Example','given':'Ann'}])
        self.assertIn('crossref',saved['metadata']['catalogue_source'])
        self.assertIn('https://doi.org/10.1234/example',saved['metadata']['catalogue_source'])
        self.store.dispatch('POST','/api/metadata',{'id':saved['id'],'expected_metadata_version': self.store._document(saved['id'])['metadata_version'], 'metadata':{**saved['metadata'],'title':'Corrected title'}})
        again=self.store.dispatch('POST','/api/literature/save',{'workspace_id':self.workspace,'result_id':result_id})['document']
        self.assertEqual(again['metadata']['title'],'Corrected title')
        self.assertFalse(any(r['document_id']==saved['id'] for r in self.store._search({'workspace_id':self.workspace,'query':'Synthetic publication'},evidence_only=True)))
        page=self.store.db.execute('SELECT text FROM pages WHERE document_id=?',(saved['id'],)).fetchone()[0]
        with self.assertRaises(AppError):
            self.store.dispatch('POST','/api/ask',{'workspace_id':self.workspace,'question':'What?','selected_source':{'document_id':saved['id'],'page':1,'text':page[:50]}})
        note=self.store.dispatch('POST','/api/notes',{'workspace_id':self.workspace,'title':'Catalogue draft','body':'[[source:'+saved['id']+':1]]'})
        checked=self.store.dispatch('POST','/api/writing-check',{'workspace_id':self.workspace,'note_id':note['id'],'version':note['version']})
        self.assertEqual(checked['catalogue_reference_warnings'][0]['name'],saved['name'])


if __name__=='__main__': unittest.main()
