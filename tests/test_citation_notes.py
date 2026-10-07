import io
import unittest
import zipfile
from lxml import etree as ET
from manuscript import render_docx
from citation_notes import apply_docx_notes, markdown_notes, tex_notes

class NoteTests(unittest.TestCase):
    def test_real_note_parts_and_references(self):
        notes=[{'number':1,'token':'KOSHNOTEREF1TOKEN','text':'Doe, *Widgets*, 2024.'}]
        for mode in ('footnote','endnote'):
            result=apply_docx_notes(render_docx('# Title\n\nA KOSHNOTEREF1TOKEN B.'),notes,mode)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                xml=archive.read('word/'+mode+'s.xml')
                self.assertIn(b'Widgets',xml)
                self.assertIn(b'<w:i',xml)
                self.assertIn((mode+'Reference').encode(),archive.read('word/document.xml'))
                self.assertNotIn(b'KOSHNOTEREF',archive.read('word/document.xml'))
                self.assertIn((mode+'s').encode(),archive.read('word/_rels/document.xml.rels'))
    def test_markdown_and_tex_keep_reference_content(self):
        notes=[{'number':1,'token':'KOSHNOTEREF1TOKEN','text':'Literal & value.'}]
        self.assertIn('[^1]: Literal & value.',markdown_notes('A KOSHNOTEREF1TOKEN',notes))
        self.assertIn(r'\footnote{Literal \& value.}',tex_notes('A KOSHNOTEREF1TOKEN',notes,'footnote'))

if __name__=='__main__': unittest.main()
