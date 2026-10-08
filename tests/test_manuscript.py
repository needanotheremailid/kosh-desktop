"""Formatting assertions inspect generated OOXML against literal requirements."""
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET

from manuscript import parse_markdown, render_docx, render_html, render_latex, safe_math

SAMPLE = '''# Café widgets

A **bold** and *italic* sentence with [a link](https://example.test/widget).

- First item
- Second item

3. Third item
4. Fourth item

> A quoted widget.

```python
print("<literal>")
```

| Name | Count |
| :--- | ---: |
| Café | 3 |

Unsafe literal: \\input{secret} & <script>x</script>.
'''
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}


class ManuscriptTests(unittest.TestCase):
    def test_tex_table_ends_before_following_paragraph(self):
        value = render_latex('| Session | Count |\n| --- | --- |\n| Morning | 12 |\n\nAfter the table.')
        self.assertIn('\\end{tabular}\\par', value)

    def test_shared_blocks_are_semantic(self):
        blocks = parse_markdown(SAMPLE)
        self.assertEqual([b['type'] for b in blocks], ['heading', 'paragraph', 'list', 'list', 'quote', 'code', 'table', 'paragraph'])
        self.assertEqual(blocks[3]['start'], 3)
        self.assertEqual(blocks[6]['rows'], [['Café', '3']])
        self.assertEqual(blocks[6]['align'], ['left', 'right'])

    def test_docx_has_real_formatting_links_numbering_tables_and_unicode(self):
        data = render_docx(SAMPLE)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            rels = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
            numbering = ET.fromstring(archive.read('word/numbering.xml'))
        text = ''.join(root.itertext())
        self.assertIn('Café widgets', text)
        self.assertNotIn('**bold**', text)
        self.assertIsNotNone(root.find('.//w:rPr/w:b', NS))
        self.assertIsNotNone(root.find('.//w:rPr/w:i', NS))
        self.assertIsNotNone(root.find('.//w:hyperlink', NS))
        self.assertTrue(any(r.get('Target') == 'https://example.test/widget' for r in rels))
        self.assertEqual(len(root.findall('.//w:tbl', NS)), 1)
        self.assertEqual(len(root.findall('.//w:numPr', NS)), 4)
        self.assertTrue(any(x.get('{'+NS['w']+'}val') == '3' for x in numbering.findall('.//w:startOverride', NS)))
        self.assertIn('print("<literal>")', text)
        self.assertIn('\\input{secret}', text)

    def test_latex_formatting_and_inert_raw_content(self):
        value = render_latex(SAMPLE, title='Widgets & design')
        for literal in ('\\section*{Café widgets}', '\\textbf{bold}', '\\emph{italic}', '\\begin{itemize}', '\\begin{enumerate}', '\\begin{quote}', '\\begin{tabular}', '\\href{https://example.test/widget}{a link}', '\\title{Widgets \\& design}'):
            self.assertIn(literal, value)
        self.assertIn('\\setcounter{enumi}{2}', value)
        self.assertNotIn('\\input{secret}', value)
        self.assertIn('\\textbackslash{}input\\{secret\\}', value)
        self.assertIn('<script>x</script>', value)

    def test_image_callback_is_only_called_for_managed_targets(self):
        seen = []
        def resolve(target):
            seen.append(target)
            return None
        data = render_docx('![Figure](https://example.test/image.png)\n\n![Local](kosh-asset:abc)', image_resolver=resolve)
        self.assertEqual(seen, ['kosh-asset:abc'])
        from docx import Document
        document = Document(io.BytesIO(data))
        self.assertIn('[Figure: Figure]', '\n'.join(p.text for p in document.paragraphs))
        self.assertIn('[Figure: Local]', '\n'.join(p.text for p in document.paragraphs))

    def test_equations_are_allowlisted_and_executable_commands_literal(self):
        value = render_latex('Safe $x^2 + \\alpha$ and unsafe $\\input{file}$.' )
        self.assertIn('$x^2 + \\alpha$', value)
        self.assertNotIn('$\\input{file}$', value)
        self.assertIn('\\textbackslash{}input', value)
        blocks = parse_markdown('$$\nx^2 + y^2 = z^2\n$$')
        self.assertEqual(blocks[0]['type'], 'math')

    def test_nested_lists_and_escaped_table_pipes(self):
        blocks = parse_markdown('- Outer\n  - Inner\n\n| A | B |\n| --- | --- |\n| a\\|b | `c|d` |')
        self.assertEqual(blocks[0]['items'][0]['children'][0]['type'], 'list')
        self.assertEqual(blocks[1]['rows'], [['a|b', '`c|d`']])

    def test_unsafe_links_are_plain_text_and_never_external_relationships(self):
        data = render_docx('[run](javascript:alert) [file](file:///secret)')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            rels = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
        self.assertFalse(any(r.get('Target', '').startswith(('javascript:', 'file:')) for r in rels))
        self.assertNotIn('\\href{javascript:', render_latex('[run](javascript:alert)'))

    def test_invalid_url_remains_literal_and_mixed_nested_counter_is_valid(self):
        value = render_latex('[broken](https://[bad)\n\n- Outer\n  3. Inner')
        self.assertNotIn('\\href{https://[bad', value)
        self.assertIn('\\setcounter{enumi}{2}', value)
        self.assertNotIn('\\setcounter{enumii}', value)

    def test_managed_figure_bytes_create_drawing_with_alt_text(self):
        import pymupdf
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 12, 8), False)
        pixmap.clear_with(220)
        data = render_docx('![Synthetic widget](kosh-asset:figure)', image_resolver=lambda _: pixmap.tobytes('png'))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            self.assertTrue(any(name.startswith('word/media/') for name in archive.namelist()))
        drawing = root.find('.//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr')
        self.assertEqual(drawing.get('descr'), 'Synthetic widget')

    def test_math_command_allowlist_blocks_macro_definition_and_file_io(self):
        for expression in ('\\def\\alpha{bad}', '\\include{file}', '\\write18{run}', '\\csname input\\endcsname', 'x%comment', '\\end{document}'):
            source = render_latex('$' + expression + '$')
            self.assertNotIn('$' + expression + '$', source)

    def test_html_uses_shared_blocks_and_escapes_script_and_bad_urls(self):
        value = render_html(SAMPLE)
        for literal in ('<h1>Café widgets</h1>', '<strong>bold</strong>', '<em>italic</em>', '<ul>', '<ol start="3">', '<blockquote>', '<table>', '<code>print(&quot;&lt;literal&gt;&quot;)</code>'):
            self.assertIn(literal, value)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', value)
        self.assertNotIn('<script>', value)
        self.assertNotIn('href="javascript:', render_html('[bad](javascript:alert)'))

    def test_html_images_use_only_explicit_managed_callback_and_safe_local_urls(self):
        calls = []
        def image_url(target):
            calls.append(target)
            return '/api/figure?id=abc'
        value = render_html('![A](kosh-asset:abc) ![External](https://example.test/a)', image_url=image_url)
        self.assertEqual(calls, ['kosh-asset:abc'])
        self.assertIn('<img src="/api/figure?id=abc" alt="A"', value)
        self.assertNotIn('src="https://', value)
        self.assertNotIn('<img', render_html('![A](kosh-asset:abc)', image_url=lambda _: 'https://example.test/a'))

    def test_html_mathml_fraction_root_scripts_and_literal_unsafe_formula(self):
        value = render_html('$\\frac{x_1^2}{\\sqrt{y}} + \\alpha$')
        self.assertIn('<math ', value)
        self.assertIn('<mfrac>', value)
        self.assertIn('<msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>', value)
        self.assertIn('<msqrt><mrow><mi>y</mi></mrow></msqrt>', value)
        self.assertIn('<mi>α</mi>', value)
        self.assertNotIn('<math ', render_html('$\\input{file}$'))

    def test_html_data_images_only_from_managed_callback_have_captions(self):
        value = render_html('![Synthetic caption](kosh-asset:x)', image_url=lambda _: 'data:image/png;base64,aGVsbG8=')
        self.assertIn('src="data:image/png;base64,aGVsbG8="', value)
        self.assertIn('<figcaption>Synthetic caption</figcaption>', value)
        self.assertNotIn('<img', render_html('![Bad](kosh-asset:x)', image_url=lambda _: 'data:text/html;base64,PHNjcmlwdD4='))

    def test_single_line_display_math_is_a_block(self):
        blocks = parse_markdown('$$x^2 = y$$')
        self.assertEqual(blocks, [{'type': 'math', 'text': 'x^2 = y', 'safe': True}])
        self.assertIn('display="block"', render_html('$$x^2 = y$$'))
        self.assertIn('\\[x^2 = y\\]', render_latex('$$x^2 = y$$'))

    def test_bracketed_citations_remain_literal_before_a_later_link_in_all_formats(self):
        for citation in ('[1]', '[1,2]', '[1]–[3]', '[sic]', '[Unresolved source reference: missing:2]'):
            with self.subTest(citation=citation):
                source = 'Risk rose ' + citation + '. See [guide](https://example.test/guide).'
                html = render_html(source)
                self.assertIn('Risk rose ' + citation + '. See <a href="https://example.test/guide"', html)
                self.assertIn('>guide</a>', html)
                self.assertEqual(html.count('<a '), 1)
                latex = render_latex(source)
                self.assertIn('Risk rose ' + citation + '. See \\href{https://example.test/guide}{guide}.', latex)
                with zipfile.ZipFile(io.BytesIO(render_docx(source))) as archive:
                    root = ET.fromstring(archive.read('word/document.xml'))
                hyperlinks = root.findall('.//w:hyperlink', NS)
                self.assertEqual(len(hyperlinks), 1)
                self.assertEqual(''.join(hyperlinks[0].itertext()), 'guide')
                self.assertIn('Risk rose ' + citation + '. See ', ''.join(root.itertext()))

    def test_matching_link_brackets_handle_nesting_escapes_and_prior_plain_brackets(self):
        source = r'[plain]. [guide [section]](https://example.test/nested) and [a \] b](https://example.test/escaped).'
        html = render_html(source)
        self.assertIn('<p>[plain]. <a href="https://example.test/nested"', html)
        self.assertIn('>guide [section]</a>', html)
        self.assertIn('>a ] b</a>', html)
        self.assertEqual(html.count('<a '), 2)
        image = render_html('[1]. ![Local](kosh-asset:fixture)', image_url=lambda _: '/synthetic.png')
        self.assertIn('[1]. ', image)
        self.assertIn('alt="Local"', image)

    def test_tex_preprocessor_caret_sequences_are_literal_in_inline_and_display_math(self):
        for expression in ('^^5cinput{a}', '^^5e^^5cwrite18{a}', 'x^^2'):
            with self.subTest(expression=expression):
                self.assertFalse(safe_math(expression))
                for source in ('$' + expression + '$', '$$\n' + expression + '\n$$'):
                    latex = render_latex(source)
                    self.assertNotIn('^^', latex)
                    self.assertIn('\\textasciicircum{}\\textasciicircum{}', latex)
                    self.assertNotIn('\\input{a}', latex)
                    self.assertNotIn('\\write18{a}', latex)
        self.assertTrue(safe_math('x^2 + \\alpha'))

    def test_tex_link_targets_cannot_contain_raw_preprocessor_caret_sequences(self):
        latex = render_latex('[safe](https://example.test/a^^5cb)')
        self.assertIn(r'\href{https://example.test/a\%5E\%5E5cb}{safe}', latex)
        self.assertNotIn('^^', latex)

    def test_docx_abstract_numbering_precedes_every_concrete_numbering_instance(self):
        source = '- First bullet\n- Second bullet\n\nParagraph\n\n3. Third numbered\n4. Fourth numbered\n\nParagraph\n\n- Last bullet'
        with zipfile.ZipFile(io.BytesIO(render_docx(source))) as archive:
            root = ET.fromstring(archive.read('word/numbering.xml'))
            document = ET.fromstring(archive.read('word/document.xml'))
        abstract_indexes = [index for index, element in enumerate(root) if element.tag == '{'+NS['w']+'}abstractNum']
        concrete_indexes = [index for index, element in enumerate(root) if element.tag == '{'+NS['w']+'}num']
        self.assertTrue(abstract_indexes)
        self.assertTrue(concrete_indexes)
        self.assertLess(max(abstract_indexes), min(concrete_indexes))
        abstracts = {element.get('{'+NS['w']+'}abstractNumId') for element in root.findall('w:abstractNum', NS)}
        for element in root.findall('w:num', NS):
            self.assertIn(element.find('w:abstractNumId', NS).get('{'+NS['w']+'}val'), abstracts)
        self.assertEqual(len(document.findall('.//w:numPr', NS)), 5)
        self.assertTrue(any(element.get('{'+NS['w']+'}val') == '3' for element in root.findall('.//w:startOverride', NS)))


if __name__ == '__main__':
    unittest.main()
