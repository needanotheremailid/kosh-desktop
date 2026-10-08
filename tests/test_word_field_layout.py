"""Nonprinting Word bibliography closure; ordinary text and fields stay intact."""
import io
import unittest
import zipfile
from lxml import etree as ET

from tests.test_exports_completion import FakeStore, MARKER, query
from exports import export_workspace
from word_citations import render_live_docx

NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


class WordFieldLayoutTests(unittest.TestCase):
    def inspect(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return ET.fromstring(archive.read('word/document.xml'))

    def test_generated_bibliography_mark_is_small_but_visible_result_is_not(self):
        store=FakeStore('A saved citation '+MARKER+'.')
        root=self.inspect(render_live_docx(store.snapshot['notes'][0]['body'],store.snapshot['documents']))
        paragraph=root.xpath('//w:p[w:r/w:instrText[contains(., "BIBLIOGRAPHY")]]',namespaces=NS)[0]
        closing=paragraph.getnext()
        self.assertEqual(closing.tag,'{'+NS['w']+'}p')
        self.assertEqual(closing.xpath('w:pPr/w:rPr/w:sz/@w:val',namespaces=NS),['2'])
        self.assertEqual(closing.xpath('w:pPr/w:rPr/w:szCs/@w:val',namespaces=NS),['2'])
        self.assertEqual(closing.xpath('w:pPr/w:spacing/@w:before',namespaces=NS),['0'])
        self.assertEqual(closing.xpath('w:pPr/w:spacing/@w:after',namespaces=NS),['0'])
        self.assertEqual(closing.xpath('.//w:t',namespaces=NS),[])
        self.assertEqual(closing.xpath('w:r/w:fldChar/@w:fldCharType',namespaces=NS),['end'])
        result=paragraph.xpath('w:r[starts-with(w:t,"1. Doe J. Widgets.")]',namespaces=NS)[0]
        self.assertEqual(result.xpath('w:rPr/w:sz/@w:val',namespaces=NS),[],'Visible field result retains the normal source font.')
        citation=root.xpath('//w:p[w:r/w:instrText[contains(., "CITATION")]]',namespaces=NS)[0]
        self.assertEqual(citation.xpath('w:pPr/w:rPr/w:sz/@w:val',namespaces=NS),[])
        self.assertEqual(len(root.xpath('//w:fldChar[@w:fldCharType="end"]',namespaces=NS)),2)

    def test_manuscript_template_keeps_nonprinting_mark_and_field_integrity(self):
        store=FakeStore('A saved citation '+MARKER+'.')
        data=export_workspace(store,query('docxlive',word_style='ieee',template={'profile':'research','line_spacing':1.5,'line_numbers':True}))[0]
        root=self.inspect(data)
        paragraph=root.xpath('//w:p[w:r/w:instrText[contains(., "BIBLIOGRAPHY")]]',namespaces=NS)[0]
        self.assertEqual(paragraph.getnext().xpath('w:pPr/w:rPr/w:sz/@w:val',namespaces=NS),['2'])
        self.assertIn('1. Doe J. Widgets.',''.join(paragraph.xpath('.//w:t/text()',namespaces=NS)))
        self.assertEqual(len(root.xpath('//w:instrText[contains(., "CITATION")]',namespaces=NS)),1)

    def test_cached_field_results_show_static_rendering_before_refresh(self):
        store=FakeStore('First '+MARKER+' then again '+MARKER+'.')
        root=self.inspect(render_live_docx(store.snapshot['notes'][0]['body'],store.snapshot['documents']))
        def results(kind):
            out=[]
            for begin in root.xpath('//w:r[w:instrText[contains(., "'+kind+'")]]',namespaces=NS):
                shown=begin.getnext().getnext()  # instr -> separate -> cached result run
                out.append(''.join(shown.xpath('w:t/text()',namespaces=NS)))
            return out
        self.assertEqual(results('CITATION'),['(1)','(1)'])
        bibliography=results('BIBLIOGRAPHY')
        self.assertEqual(len(bibliography),1)
        self.assertTrue(bibliography[0].startswith('1. Doe J. Widgets. Widget Rev. 2024'),bibliography)
        xml=ET.tostring(root).decode()
        self.assertNotIn('Update citation in Word',xml)
        self.assertNotIn('Update bibliography in Word',xml)
        self.assertNotIn(r'widget\_id',xml,'CSL Markdown escapes must not leak into field text.')

    def test_placeholder_kept_when_static_rendering_unavailable(self):
        from unittest import mock
        store=FakeStore('A saved citation '+MARKER+'.')
        with mock.patch('word_citations.render_citations',side_effect=ValueError('synthetic failure')):
            xml=ET.tostring(self.inspect(render_live_docx(store.snapshot['notes'][0]['body'],store.snapshot['documents']))).decode()
        self.assertIn('[Update citation in Word]',xml)
        self.assertIn('Update bibliography in Word.',xml)


if __name__=='__main__':unittest.main()
