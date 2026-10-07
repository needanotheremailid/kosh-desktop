import tempfile
from pathlib import Path
import unittest

from csl_styles import StyleError, StyleLibrary

STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text"><info><title>Example Journal</title><id>urn:test:example</id></info><citation><layout prefix="[" suffix="]"><text variable="citation-number"/></layout></citation><bibliography><layout><text variable="title"/></layout></bibliography></style>'''


class Styles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = StyleLibrary(Path(self.temp.name))

    def test_import_exact_bytes_idempotent_and_reopen(self):
        result = self.library.import_style(STYLE)
        self.assertEqual(result['title'], 'Example Journal')
        self.assertEqual(self.library.import_style(STYLE), result)
        self.assertEqual(StyleLibrary(Path(self.temp.name)).resolve(result['id']), STYLE)
        self.assertEqual(len(self.library.list_styles()), 5)

    def test_parent_style_requires_explicit_local_parent(self):
        with self.assertRaisesRegex(StyleError, 'identifier'):
            self.library.import_style('<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0"><info><title>Dependent</title><link rel="independent-parent" href="https://example.invalid/parent"/></info></style>')

    def test_dtd_script_foreign_locale_and_traversal_rejected(self):
        for value in ('<!DOCTYPE style []>' + STYLE, STYLE.replace('<citation>', '<script>x</script><citation>')):
            with self.assertRaises(StyleError):
                self.library.import_style(value)
        french = self.library.import_style(STYLE.replace('class="in-text"', 'class="in-text" default-locale="fr-FR"'))
        self.assertEqual(self.library.resolve_bundle(french['id'])['language'], 'fr-FR')
        with self.assertRaises(StyleError):
            self.library.resolve('../secret')

    def test_changed_style_file_rejected(self):
        result = self.library.import_style(STYLE)
        path = Path(self.temp.name) / 'citation-styles' / (result['id'] + '.csl')
        path.write_text(STYLE.replace('Example Journal', 'Changed Journal'), encoding='utf-8')
        with self.assertRaisesRegex(StyleError, 'hash'):
            self.library.resolve(result['id'])

    def test_authenticated_store_style_import_and_real_export(self):
        from backend import Store
        store = Store(Path(self.temp.name) / 'app')
        self.addCleanup(store.close)
        result = store.dispatch('POST', '/api/citation/styles/import', {'xml': STYLE})
        self.assertEqual(result['style']['title'], 'Example Journal')
        self.assertEqual(len(store.dispatch('GET', '/api/citation/styles')['styles']), 5)
        from test_exports_completion import FakeStore, query
        from exports import export_workspace
        fixture = FakeStore()
        fixture.root = store.root
        text = export_workspace(fixture, query(citation_style=result['style']['id']))[0].decode()
        self.assertIn('Widgets (including blue widgets) [1]', text)
        self.assertIn('## References\n\nWidgets', text)

    def test_superscript_is_formatted_and_other_html_stays_inert(self):
        from manuscript import render_html, render_docx, render_latex
        from zipfile import ZipFile
        import io
        text = 'Claim<sup>1,2</sup> and H<sub>2</sub>O <script>alert(1)</script>'
        rendered = render_html(text)
        self.assertIn('<sup>1,2</sup>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn(r'\textsuperscript{1,2}', render_latex(text))
        with ZipFile(io.BytesIO(render_docx(text))) as archive:
            xml = archive.read('word/document.xml').decode()
        self.assertIn('w:val="superscript"', xml)
        self.assertIn('w:val="subscript"', xml)
        from csl_engine import _markdown
        literal = render_html(_markdown('<div>&lt;sup&gt;not formatting&lt;/sup&gt;</div>'))
        self.assertNotIn('<sup>', literal)
        self.assertIn('&lt;sup&gt;', literal)


if __name__ == '__main__':
    unittest.main()
