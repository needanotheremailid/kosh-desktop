"""Native Word equation structures from independent, synthetic formulas."""
import copy
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from manuscript import omml_text, parse_markdown, render_docx, render_html, render_latex

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def xml(markdown):
    with zipfile.ZipFile(io.BytesIO(render_docx(markdown))) as archive:
        return ET.fromstring(archive.read('word/document.xml'))


def math_text(node):
    return ''.join(element.text or '' for element in node.findall('.//m:t', NS))


class ManuscriptMathTests(unittest.TestCase):
    def test_inline_math_is_omml_between_original_prose_runs(self):
        root = xml('Before $x^2$ after.')
        paragraph = root.find('.//w:p', NS)
        equation = paragraph.find('m:oMath', NS)
        self.assertIsNotNone(equation)
        self.assertIsNotNone(equation.find('m:sSup', NS))
        self.assertEqual([node.text for node in paragraph.findall('w:r/w:t', NS)], ['Before ', ' after.'])
        self.assertEqual(math_text(equation.find('m:sSup/m:e', NS)), 'x')
        self.assertEqual(math_text(equation.find('m:sSup/m:sup', NS)), '2')

    def test_display_math_has_native_math_paragraph_and_center_justification(self):
        root = xml('$$x^2 + y^2 = z^2$$')
        display = root.find('.//m:oMathPara', NS)
        self.assertIsNotNone(display)
        self.assertEqual(display.find('m:oMathParaPr/m:jc', NS).get('{'+NS['m']+'}val'), 'center')
        self.assertEqual(len(display.findall('.//m:sSup', NS)), 3)
        self.assertIsNotNone(display.find('m:oMath', NS))

    def test_fraction_has_native_numerator_and_denominator_with_scripts(self):
        root = xml(r'$\frac{x_1^2}{y}$')
        fraction = root.find('.//m:f', NS)
        self.assertIsNotNone(fraction)
        self.assertEqual(fraction.find('m:fPr/m:type', NS).get('{'+NS['m']+'}val'), 'bar')
        self.assertEqual(math_text(fraction.find('m:num/m:sSubSup/m:e', NS)), 'x')
        self.assertEqual(math_text(fraction.find('m:num/m:sSubSup/m:sub', NS)), '1')
        self.assertEqual(math_text(fraction.find('m:num/m:sSubSup/m:sup', NS)), '2')
        self.assertEqual(math_text(fraction.find('m:den', NS)), 'y')

    def test_square_root_has_hidden_degree_and_nested_fraction(self):
        root = xml(r'$\sqrt{\frac{a}{b}}$')
        radical = root.find('.//m:rad', NS)
        self.assertIsNotNone(radical)
        self.assertEqual(radical.find('m:radPr/m:degHide', NS).get('{'+NS['m']+'}val'), '1')
        self.assertIsNotNone(radical.find('m:deg', NS))
        self.assertIsNotNone(radical.find('m:e/m:f', NS))

    def test_greek_and_basic_operators_are_unicode_math_runs(self):
        equation = xml(r'$\alpha + \beta \times \gamma \leq \delta$').find('.//m:oMath', NS)
        self.assertIsNotNone(equation)
        self.assertEqual(math_text(equation), 'α+β×γ≤δ')
        self.assertFalse(any('\\' in (node.text or '') for node in equation.findall('.//m:t', NS)))

    def test_subscript_superscript_and_combined_scripts_remain_distinct(self):
        root = xml('$x_1$ and $y^2$ and $z_3^4$.')
        self.assertEqual(len(root.findall('.//m:oMath', NS)), 3)
        self.assertEqual(len(root.findall('.//m:sSub', NS)), 1)
        self.assertEqual(len(root.findall('.//m:sSup', NS)), 1)
        self.assertEqual(len(root.findall('.//m:sSubSup', NS)), 1)

    def test_math_style_uses_native_properties_and_math_font(self):
        equation = xml(r'$\mathbf{x} + \mathrm{sin}$').find('.//m:oMath', NS)
        self.assertIsNotNone(equation)
        runs = equation.findall('.//m:r', NS)
        by_text = {run.find('m:t', NS).text: run for run in runs}
        self.assertEqual(by_text['x'].find('m:rPr/m:sty', NS).get('{'+NS['m']+'}val'), 'b')
        self.assertEqual(by_text['sin'].find('m:rPr/m:sty', NS).get('{'+NS['m']+'}val'), 'p')
        self.assertEqual(by_text['x'].find('w:rPr/w:rFonts', NS).get('{'+NS['w']+'}ascii'), 'Cambria Math')

    def test_safe_but_unsupported_commands_preserve_literal_not_fake_equation(self):
        for expression in (r'\hat{x}', r'\text{widgets}', r'\operatorname{widgets}', 'x^1^2'):
            with self.subTest(expression=expression):
                root = xml('$' + expression + '$')
                self.assertEqual(root.findall('.//m:oMath', NS), [])
                text = ''.join(node.text or '' for node in root.findall('.//w:t', NS))
                self.assertIn('$' + expression + '$', text)

    def test_unsafe_commands_and_tex_character_shortcuts_stay_literal(self):
        for expression in (r'\input{file}', r'\write18{run}', r'\def\x{bad}', r'^^5cinput{file}'):
            with self.subTest(expression=expression):
                root = xml('$' + expression + '$')
                self.assertEqual(root.findall('.//m:oMath', NS), [])
                self.assertIn(expression, ''.join(node.text or '' for node in root.findall('.//w:t', NS)))

    def test_equations_in_table_and_bullet_are_native_equations(self):
        root = xml('- Value $x_1$\n\n| Equation | Meaning |\n| --- | --- |\n| $\\frac{x}{y}$ | Ratio |')
        self.assertIsNotNone(root.find('.//w:tbl//m:f', NS))
        self.assertEqual(len(root.findall('.//m:oMath', NS)), 2)
        self.assertIsNotNone(root.find('.//w:p/w:pPr/w:numPr', NS))

    def test_math_code_is_literal_and_markdown_source_is_unchanged(self):
        source = 'Before $x^2$.\n\n```tex\n\\frac{x}{y}\n```'
        blocks = parse_markdown(source)
        original_blocks = copy.deepcopy(blocks)
        root = xml(source)
        self.assertEqual(blocks, original_blocks)
        self.assertEqual(source, 'Before $x^2$.\n\n```tex\n\\frac{x}{y}\n```')
        self.assertEqual(len(root.findall('.//m:oMath', NS)), 1)
        self.assertIn(r'\frac{x}{y}', ''.join(node.text or '' for node in root.findall('.//w:t', NS)))

    def test_html_latex_existing_math_semantics_stay_the_same(self):
        source = r'$\frac{x_1^2}{\sqrt{y}} + \alpha$'
        self.assertIn('<mfrac>', render_html(source))
        self.assertIn('<msubsup>', render_html(source))
        self.assertIn('<msqrt>', render_html(source))
        self.assertIn(r'$\frac{x_1^2}{\sqrt{y}} + \alpha$', render_latex(source))

    def test_indexed_root_uses_mathml_mroot_and_explicit_word_degree(self):
        source = r'$\sqrt[3]{x}$'
        value = render_html(source)
        self.assertIn('<mroot><mrow><mi>x</mi></mrow><mrow><mn>3</mn></mrow></mroot>', value)
        radical = xml(source).find('.//m:rad', NS)
        self.assertEqual(radical.find('m:radPr/m:degHide', NS).get('{'+NS['m']+'}val'), '0')
        self.assertEqual(math_text(radical.find('m:deg', NS)), '3')
        self.assertEqual(math_text(radical.find('m:e', NS)), 'x')

    def test_missing_indexed_root_delimiter_is_literal_in_html_and_word(self):
        source = r'$\sqrt[3{x}$'
        self.assertNotIn('<math ', render_html(source))
        self.assertEqual(xml(source).findall('.//m:oMath', NS), [])

    def test_supported_equations_roundtrip_as_explicit_linear_notation(self):
        from backend import extract
        source = r'Before $\frac{x_1^2}{\sqrt{y}} + \alpha$ after.' + '\n\n' + r'$$\sqrt[3]{z}$$'
        data = render_docx(source)
        pages, notice = extract(data, 'docx')
        self.assertIn('Before (x_{1}^{2})/(sqrt(y))+α after.', pages[0][1])
        self.assertIn('root(3,z)', pages[0][1])
        self.assertIn('linear notation', notice)
        self.assertNotIn('Unsupported', notice)

    def test_omml_reader_rejects_unknown_structures_rather_than_flattening(self):
        root = ET.fromstring('<m:oMath xmlns:m="'+NS['m']+'"><m:acc><m:e><m:r><m:t>x</m:t></m:r></m:e></m:acc></m:oMath>')
        self.assertIsNone(omml_text(root))

    def test_linear_notation_retains_explicit_bold_math_style(self):
        equation = xml(r'$\mathbf{x}$').find('.//m:oMath', NS)
        self.assertEqual(omml_text(equation), 'bold(x)')

    def test_unknown_native_equation_is_omitted_with_extraction_notice(self):
        from backend import extract
        data = render_docx('$x^2$')
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as changed:
            for name in source.namelist():
                value = source.read(name)
                if name == 'word/document.xml':
                    root = ET.fromstring(value)
                    equation = root.find('.//m:oMath', NS)
                    equation.clear()
                    unknown = ET.SubElement(equation, '{'+NS['m']+'}acc')
                    ET.SubElement(unknown, '{'+NS['m']+'}t').text = 'Would be misleading alone'
                    value = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                changed.writestr(name, value)
        pages, notice = extract(output.getvalue(), 'docx')
        self.assertNotIn('Would be misleading alone', pages[0][1])
        self.assertIn('1 unsupported native equation', notice)

    def test_docx_traversal_skips_textbox_fallback_and_moved_from_text(self):
        from backend import extract
        data = render_docx('Primary $x^2$ content.')
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as changed:
            for name in source.namelist():
                value = source.read(name)
                if name == 'word/document.xml':
                    root = ET.fromstring(value)
                    paragraph = root.find('.//w:p', NS)
                    textbox = ET.SubElement(ET.SubElement(paragraph, '{'+NS['w']+'}r'), '{'+NS['w']+'}txbxContent')
                    text = ET.SubElement(ET.SubElement(ET.SubElement(textbox, '{'+NS['w']+'}p'), '{'+NS['w']+'}r'), '{'+NS['w']+'}t')
                    text.text = 'Excluded textbox text'
                    mc = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
                    alternate = ET.SubElement(paragraph, mc+'AlternateContent')
                    choice = ET.SubElement(alternate, mc+'Choice', {'Requires': 'w'})
                    ET.SubElement(ET.SubElement(choice, '{'+NS['w']+'}r'), '{'+NS['w']+'}t').text = ' Chosen text'
                    fallback = ET.SubElement(alternate, mc+'Fallback')
                    ET.SubElement(ET.SubElement(ET.SubElement(fallback, '{'+NS['w']+'}p'), '{'+NS['w']+'}r'), '{'+NS['w']+'}t').text = 'Excluded fallback text'
                    moved_from = ET.SubElement(paragraph, '{'+NS['w']+'}moveFrom')
                    ET.SubElement(ET.SubElement(moved_from, '{'+NS['w']+'}r'), '{'+NS['w']+'}t').text = 'Excluded moved-from text'
                    moved_to = ET.SubElement(paragraph, '{'+NS['w']+'}moveTo')
                    ET.SubElement(ET.SubElement(moved_to, '{'+NS['w']+'}r'), '{'+NS['w']+'}t').text = ' Current moved-to text'
                    value = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                changed.writestr(name, value)
        pages, notice = extract(output.getvalue(), 'docx')
        self.assertEqual(pages[0][1], 'Primary x^{2} content. Chosen text Current moved-to text')
        self.assertIn('linear notation', notice)

    def test_docx_nonbreaking_hyphen_positional_tab_and_unmapped_symbol_are_explicit(self):
        from backend import extract
        data = render_docx('Synthetic glyphs')
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as changed:
            for name in source.namelist():
                value = source.read(name)
                if name == 'word/document.xml':
                    root = ET.fromstring(value)
                    paragraph = root.find('.//w:p', NS)
                    for child in list(paragraph):
                        paragraph.remove(child)
                    run = ET.SubElement(paragraph, '{'+NS['w']+'}r')
                    ET.SubElement(run, '{'+NS['w']+'}t').text = 'Widget'
                    ET.SubElement(run, '{'+NS['w']+'}noBreakHyphen')
                    ET.SubElement(run, '{'+NS['w']+'}ptab')
                    ET.SubElement(run, '{'+NS['w']+'}t').text = 'Group '
                    ET.SubElement(run, '{'+NS['w']+'}sym', {'{'+NS['w']+'}font': 'Wingdings', '{'+NS['w']+'}char': 'F0E0'})
                    value = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                changed.writestr(name, value)
        pages, notice = extract(output.getvalue(), 'docx')
        self.assertEqual(pages[0][1], 'Widget\u2011\tGroup \ufffd')
        self.assertIn('1 unmapped symbol-font glyph', notice)
        self.assertIn('inspect the original', notice)


if __name__ == '__main__':
    unittest.main()
