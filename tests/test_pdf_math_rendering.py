"""Actual synthetic PDF geometry checks, independent of layout implementation."""
import unittest
import unicodedata
from unittest.mock import patch

import pymupdf

from exports import _pdf


def pdf(source):
    return pymupdf.open(stream=_pdf(source, '', {}), filetype='pdf')


def characters(page):
    return [char for block in page.get_text('rawdict')['blocks'] if block['type'] == 0
            for line in block['lines'] for span in line['spans'] for char in span['chars']]


class PdfMathRenderingTests(unittest.TestCase):
    def test_supported_math_is_typeset_without_literal_tex(self):
        with pdf(r'Before $x_1^2 + \alpha$ after.') as document:
            text = document[0].get_text()
            self.assertIn('Before', text)
            self.assertIn('after.', text)
            self.assertIn('α', text)
            for literal in ('\\alpha', '^', '_'):
                self.assertNotIn(literal, text)
            chars = {char['c']: char for char in characters(document[0]) if char['c'] in 'x12'}
            self.assertLess(chars['2']['origin'][1], chars['x']['origin'][1] - 3)
            self.assertGreater(chars['1']['origin'][1], chars['x']['origin'][1] + 2)
            prose = next(char for char in characters(document[0]) if char['c'] == 'B')
            self.assertAlmostEqual(chars['x']['origin'][1], prose['origin'][1], delta=1)

    def test_fraction_has_stacked_arguments_and_a_drawn_bar(self):
        with pdf(r'$$\frac{a}{b}$$') as document:
            page = document[0]
            self.assertNotIn('\\frac', page.get_text())
            chars = {char['c']: char for char in characters(page)}
            self.assertLess(chars['a']['bbox'][3], chars['b']['bbox'][1])
            bars = [drawing for drawing in page.get_drawings() if drawing['rect'].width > 4]
            self.assertTrue(bars)
            self.assertAlmostEqual(chars['a']['origin'][0], chars['b']['origin'][0], delta=2)

    def test_nested_indexed_root_and_greek_survive_as_glyphs_and_paths(self):
        with pdf(r'$$\sqrt[3]{\frac{\alpha_1^2}{\beta}} \leq \gamma$$') as document:
            page = document[0]
            text = page.get_text()
            for glyph in '3α12β≤γ':
                self.assertIn(glyph, text)
            self.assertNotIn('\\', text)
            self.assertGreaterEqual(len(page.get_drawings()), 2)
            self.assertTrue(all(not drawing['closePath'] for drawing in page.get_drawings()))
            for char in characters(page):
                self.assertTrue(page.rect.contains(pymupdf.Rect(char['bbox'])))

    def test_table_list_and_many_pages_keep_each_equation(self):
        source = '- Inline $x^2$\n\n| Formula | Meaning |\n| --- | --- |\n| $\\frac{a}{b}$ | Ratio |\n\n'
        source += '\n\n'.join(r'$$\sqrt{z_7}$$' for _ in range(65))
        with pdf(source) as document:
            text = unicodedata.normalize('NFKC', '\n'.join(page.get_text() for page in document))
            self.assertNotIn('\\sqrt', text)
            self.assertEqual(text.count('z'), 65)
            self.assertGreater(len(document), 1)
            for page in document:
                self.assertTrue(all(page.rect.contains(pymupdf.Rect(char['bbox'])) for char in characters(page)))

    def test_unsupported_and_unsafe_math_remain_explicit_literal(self):
        expressions = [r'\hat{x}', r'\text{widgets}', 'x^1^2', r'\input{file}', r'\sqrt[3{x}']
        with pdf('\n\n'.join('$' + expression + '$' for expression in expressions)) as document:
            text = unicodedata.normalize('NFKC', '\n'.join(page.get_text() for page in document))
            for expression in expressions:
                self.assertIn(expression, text)

    def test_fenced_math_is_not_typeset(self):
        with pdf('```tex\n\\frac{x}{y}\n```') as document:
            self.assertIn(r'\frac{x}{y}', document[0].get_text())

    def test_empty_group_is_retained_as_labelled_notation(self):
        with pdf(r'Before ${}$ after.') as document:
            self.assertIn('Equation notation: {}', document[0].get_text())

    def test_unavailable_formula_glyph_retains_labelled_original_notation(self):
        with patch('pdf_math.layout_math', side_effect=ValueError('Missing glyph')):
            with pdf(r'$\alpha^2$') as document:
                self.assertIn(r'Equation notation: \alpha^2', document[0].get_text())

    def test_long_equation_scales_without_clipping(self):
        expression = '+'.join('x_{12}^{34}' for _ in range(80))
        with pdf('$$' + expression + '$$') as document:
            page = document[0]
            self.assertEqual(page.get_text().count('x'), 80)
            for char in characters(page):
                self.assertTrue(page.rect.contains(pymupdf.Rect(char['bbox'])))

    def test_interleaved_managed_figure_does_not_take_equation_placement(self):
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 10), False)
        pixmap.clear_with(180)
        identifier = 'a'*32
        figures = {'kosh-asset:'+identifier: {'bytes': pixmap.tobytes('png'), 'path': 'figures/a.png'}}
        source = r'Before $x^2$.'+'\n\n![Synthetic figure](kosh-asset:'+identifier+')\n\n'+r'After $y_1$.'
        with pymupdf.open(stream=_pdf(source, '', figures), filetype='pdf') as document:
            page = document[0]
            chars = {char['c']: char for char in characters(page) if char['c'] in 'xy'}
            self.assertLess(chars['x']['origin'][1], chars['y']['origin'][1])
            self.assertEqual(len(page.get_image_info()), 3)

    def test_math_styles_and_named_function_keep_typeface(self):
        with pdf(r'$\mathbf{x} + \mathrm{y} + \mathit{z} + \sin{t}$') as document:
            spans = [span for block in document[0].get_text('dict')['blocks'] if block['type'] == 0
                     for line in block['lines'] for span in line['spans']]
            by_text = {char: span for span in spans for char in span['text']}
            self.assertIn('Bold', by_text['x']['font'])
            self.assertNotIn('Italic', by_text['y']['font'])
            self.assertIn('Italic', by_text['z']['font'])

    def test_inline_root_has_space_before_and_after_each_line(self):
        with pdf(r'Before $\sqrt{\frac{x}{y}}$ after.'+'\n\nFollowing paragraph.') as document:
            page = document[0]
            chars = characters(page)
            following = next(char for char in chars if char['c'] == 'F')
            equation = [char for char in chars if char['c'] in 'xy']
            self.assertLess(max(char['bbox'][3] for char in equation), following['bbox'][1])


if __name__ == '__main__':
    unittest.main()
