import io
import unittest
import zipfile
from xml.etree import ElementTree as ET

from word_citations import render_live_docx, WordCitationError


class WordLiveTests(unittest.TestCase):
    def test_document_sources_and_editable_fields(self):
        source = {'id': 'a'*32, 'kind': 'pdf', 'pages': 3, 'name': 'fixture.pdf',
                  'metadata': {'type': 'journal_article', 'title': 'A & B <study>',
                               'author_list': [{'family': 'Smith', 'given': 'Alex'}],
                               'year': '2024', 'journal': 'Synthetic Journal', 'volume': '2', 'pages': '1-3'}}
        data = render_live_docx('Claim [[source:'+'a'*32+':2]].', [source], word_style='ieee')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            codes = [node.text for node in root.findall('.//w:instrText', ns)]
            self.assertEqual(codes, [' CITATION Kosh'+'a'*32+' \\l 1033 ', ' BIBLIOGRAPHY \\l 1033 '])
            source_xml = ET.fromstring(archive.read('customXml/item1.xml'))
            b = '{http://schemas.openxmlformats.org/officeDocument/2006/bibliography}'
            self.assertEqual(source_xml.find(b+'Source/'+b+'Title').text, 'A & B <study>')
            self.assertEqual(source_xml.attrib['SelectedStyle'], '\\IEEE2006OfficeOnline.xsl')
            self.assertIn('customXml', archive.read('word/_rels/document.xml.rels').decode())
            self.assertNotIn('KOSHLIVE', archive.read('word/document.xml').decode())

    def test_refuse_silent_csl_to_native_substitution(self):
        with self.assertRaises(WordCitationError):
            render_live_docx('text', [], word_style='vancouver')

    def test_invalid_source_cannot_be_live_field(self):
        with self.assertRaises(WordCitationError):
            render_live_docx('[[reference:'+'b'*32+']]', [], word_style='ieee')

    def test_doi_aliases_share_source_and_docx_roundtrip_preserves_it(self):
        from docx import Document
        first = {'id': 'a'*32, 'kind': 'pdf', 'metadata': {'title': 'First', 'doi': '10.1234/example'}}
        alias = {'id': 'b'*32, 'kind': 'pdf', 'metadata': {'title': 'Alias', 'doi': 'https://doi.org/10.1234/example'}}
        data = render_live_docx('[[reference:'+'a'*32+']] then [[reference:'+'b'*32+']]', [first, alias])
        output = io.BytesIO()
        Document(io.BytesIO(data)).save(output)
        with zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
            sources = ET.fromstring(archive.read('customXml/item1.xml'))
            self.assertEqual(len(sources), 1)
            xml = archive.read('word/document.xml').decode()
            self.assertEqual(xml.count(' CITATION Kosh'+'a'*32), 2)
            self.assertNotIn(' CITATION Kosh'+'b'*32, xml)
