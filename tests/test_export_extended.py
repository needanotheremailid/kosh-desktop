import io
import json
import unittest
import zipfile
from unittest.mock import patch
from test_exports_completion import FakeStore, query
from exports import export_workspace, ExportError

class ExtendedExportTests(unittest.TestCase):
    def test_live_word_template_keeps_fields_sources_and_frontmatter(self):
        data,mime,name=export_workspace(FakeStore(),query('docxlive',word_style='ieee',template={'profile':'research','authors':'Synthetic Author'}))
        self.assertTrue(name.endswith('.docx'))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml=archive.read('word/document.xml')
            self.assertIn(b'CITATION',xml);self.assertIn(b'BIBLIOGRAPHY',xml);self.assertIn(b'Synthetic Author',xml)
            self.assertTrue(any(name.startswith('customXml/') for name in archive.namelist()))

    def test_chicago_actual_word_notes(self):
        data,_,_=export_workspace(FakeStore(),query('docx',citation_style='chicago-note',note_placement='footnote'))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn(b'Widgets',archive.read('word/footnotes.xml'))
            self.assertIn(b'footnoteReference',archive.read('word/document.xml'))

    def test_compiler_receives_generated_tex_and_no_raw_metadata_commands(self):
        with patch('tex_compile.compile_tex',return_value=b'%PDF-synthetic-test') as compile:
            data,mime,name=export_workspace(FakeStore(body='$$\\begin{pmatrix}1 & 2\\\\3 & 4\\end{pmatrix}$$'),query('texpdf',template={'profile':'review','authors':r'\input{private}'}))
            source=compile.call_args.args[0]
            self.assertIn(r'\begin{pmatrix}',source)
            self.assertNotIn(r'\input{private}',source)
            self.assertEqual(data,b'%PDF-synthetic-test');self.assertEqual(mime,'application/pdf');self.assertTrue(name.endswith('.pdf'))

    def test_invalid_template_is_not_ignored(self):
        with self.assertRaises(ExportError):export_workspace(FakeStore(),query('docx',template={'profile':'x'}))

if __name__=='__main__': unittest.main()
