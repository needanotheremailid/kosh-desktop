"""Regressions from the independent source review, disposable fixtures only."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import AppError, Store, answer_source_markers, cited_answer_ids
from assistance import AssistanceError, selected_patch


class ReviewCompletion(unittest.TestCase):
    def test_answer_groups_preserve_every_known_id_and_do_not_resolve_unknowns(self):
        citations = [{'id':'C1','document_id':'a'*32,'page':2}, {'id':'C2','document_id':'b'*32,'page':3}]
        self.assertEqual(cited_answer_ids('Widgets [C1, C2]. [C9]'), {'C1','C2','C9'})
        result = answer_source_markers('Widgets [C1, C2]. Unknown [C1,C9].', citations)
        self.assertIn('[[source:' + 'a'*32 + ':2]] [[source:' + 'b'*32 + ':3]]', result)
        self.assertIn('[C1,C9]', result)

    def test_selected_edit_cannot_cut_through_a_source_marker(self):
        marker = '[[source:' + 'a'*32 + ':1]]'
        note = {'id':'n','workspace_id':'w','version':1,'body':'Before '+marker+' after.'}
        preview = {'note_id':'n','workspace_id':'w','version':1,'selected_text':'source:'+'a'*32}
        with self.assertRaisesRegex(AssistanceError, 'whole source'):
            selected_patch(note, preview, 'Replacement')

    def test_image_and_ris_originals_have_valid_download_mime(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            try:
                workspace = store.dispatch('POST','/api/workspaces',{'title':'Synthetic MIME'})['id']
                pix = pymupdf.Pixmap(pymupdf.csRGB,(0,0,10,10),0)
                pix.clear_with(255)
                files = [('figure.png',pix.tobytes('png'),'image/png'),('figure.jpg',pix.tobytes('jpeg'),'image/jpeg'),('refs.ris',b'TY  - JOUR\nTI  - Widgets\nER  -\n','text/plain; charset=utf-8')]
                for name,raw,mime in files:
                    doc = store.dispatch('POST','/api/import',{'workspace_id':workspace,'files':[{'name':name,'data':base64.b64encode(raw).decode()}]})['results'][0]['document']
                    response = store.file_response('/api/file',{'id':doc['id']})
                    self.assertEqual(response, (raw,mime,name))
            finally:
                store.close()

    def test_local_assistance_truncation_fails_once_without_saving_result(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            try:
                workspace = store.dispatch('POST','/api/workspaces',{'title':'Synthetic context'})['id']
                note = store.dispatch('POST','/api/notes',{'workspace_id':workspace,'title':'Synthetic','body':'Synthetic widgets.'})
                with patch.object(store,'models',return_value={'available':True,'models':[{'name':'synthetic-local'}]}):
                    preview = store.dispatch('POST','/api/assist/preview',{'workspace_id':workspace,'provider':'ollama','model':'synthetic-local','task':'clarity','note_id':note['id'],'version':1,'selected_text':note['body']})
                with patch('backend.ollama_request',return_value={'response':'Cut off','done_reason':'length'}) as generate:
                    for attempt in range(2):
                        with self.assertRaises(AppError):
                            store.dispatch('POST','/api/assist/run',{'preview_id':preview['preview_id'],'consent':True,'consent_version':1})
                    self.assertEqual(generate.call_count,1)
                    options = generate.call_args.args[1]['options']
                    self.assertEqual((options['num_ctx'],options['num_predict']),(32768,8192))
                job = store.assistance.get(preview['preview_id'])
                self.assertEqual(job['status'],'failed')
                self.assertIsNone(job['result'])
                self.assertEqual(store._state(workspace)['notes'][0]['body'], note['body'])
            finally:
                store.close()


if __name__ == '__main__': unittest.main()
