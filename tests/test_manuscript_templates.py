import io
import unittest
import zipfile
from xml.etree import ElementTree as ET

from manuscript import render_docx
from manuscript_templates import validate_template, apply_docx_template, template_css, template_frontmatter


class TemplateTests(unittest.TestCase):
    def test_research_layout_has_real_page_geometry_title_break_and_number_fields(self):
        options = validate_template({'profile': 'research', 'authors': 'Synthetic Author', 'affiliations': 'Synthetic Lab', 'abstract': 'A supplied abstract.', 'keywords': 'widgets', 'font_size': 12, 'line_spacing': 2, 'margin_mm': 25, 'page_size': 'a4', 'line_numbers': True})
        result = apply_docx_template(render_docx('# Synthetic title\n\n## Introduction\n\nText.\n\n## References\n\nReference one.'), options, 'Synthetic title')
        with zipfile.ZipFile(io.BytesIO(result)) as archive:
            document = ET.fromstring(archive.read('word/document.xml'))
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            self.assertEqual(document.find('.//w:pgSz', ns).get('{'+ns['w']+'}w'), '11906')
            self.assertEqual(document.find('.//w:pgMar', ns).get('{'+ns['w']+'}left'), '1417')
            self.assertIsNotNone(document.find('.//w:lnNumType', ns))
            self.assertIn('Synthetic Author', ''.join(document.itertext()))
            self.assertTrue(any(node.get('{'+ns['w']+'}type') == 'page' for node in document.findall('.//w:br', ns)))
            footer = ''.join(archive.read(name).decode() for name in archive.namelist() if name.startswith('word/footer') and name.endswith('.xml'))
            self.assertIn('PAGE', footer)
            styles=ET.fromstring(archive.read('word/styles.xml'))
            heading=next(node for node in styles.findall('w:style',ns) if node.get('{'+ns['w']+'}styleId')=='Heading1')
            font=heading.find('w:rPr/w:rFonts',ns)
            self.assertIsNone(font.get('{'+ns['w']+'}asciiTheme'))
            self.assertEqual(heading.find('w:rPr/w:color',ns).get('{'+ns['w']+'}val'),'000000')

    def test_blinded_output_omits_supplied_author_fields(self):
        options=validate_template({'profile':'review','authors':'Do Not Include','affiliations':'Hidden affiliation','blinded':True})
        self.assertNotIn('Do Not Include', template_frontmatter(options,'Title'))
        with zipfile.ZipFile(io.BytesIO(apply_docx_template(render_docx('# Title\n\nBody'),options,'Title'))) as archive:
            self.assertNotIn(b'Do Not Include',archive.read('word/document.xml'))

    def test_options_reject_invalid_values_and_preserve_literal_metadata(self):
        for values in ({'profile':'madeup'}, {'profile':'research','font_size':100}, {'profile':'review','line_numbers':'yes'}, {'profile':'case-report','margin_mm':0}, {'profile':'research','unknown':'x'}):
            with self.assertRaises(ValueError): validate_template(values)
        options=validate_template({'profile':'case-report','authors':'<script> & *literal*'})
        text=template_frontmatter(options,'Title')
        self.assertIn(r'\<script\>',text)
        self.assertIn('line-height:2',template_css(options))

    def test_none_is_identity(self):
        data=render_docx('# A\n\nB')
        self.assertEqual(apply_docx_template(data,validate_template({}),'A'),data)

if __name__ == '__main__': unittest.main()
