import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend
from retrieval import Retrieval


class OcrSerialization(unittest.TestCase):
    def test_ocr_enters_pdf_library_under_same_lock_as_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            store=backend.Store(Path(directory)/'data')
            try:
                workspace=store.dispatch('POST','/api/workspaces',{'title':'Widget OCR'})['id']
                with backend.pdf_lib.open() as source:
                    source.new_page().insert_text((40,40),'Widget sample')
                    data=source.tobytes()
                doc=store.dispatch('POST','/api/import',{'workspace_id':workspace,'files':[{'name':'widgets.pdf','data':base64.b64encode(data).decode()}]})['results'][0]['document']
                class EnteredSafely(Exception): pass
                def enter(*args,**kwargs):
                    self.assertTrue(store.lock._is_owned(),'OCR entered PDF library outside shared serialization lock')
                    raise EnteredSafely()
                with patch('retrieval.tessdata_for',return_value=Path(directory)),patch.object(backend.pdf_lib,'open',side_effect=enter):
                    with self.assertRaises(EnteredSafely):
                        Retrieval(store)._ocr({'workspace_id':workspace,'document_id':doc['id'],'pages':[1]})
            finally: store.close()
