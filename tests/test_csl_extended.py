import tempfile
import unittest
from unittest.mock import patch
import io
from pathlib import Path
from csl_styles import StyleLibrary, StyleError
from csl_engine import render

NOTE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="note"><info><title>Test notes</title><id>http://www.zotero.org/styles/test-notes</id></info><citation><layout><text variable="title"/></layout></citation></style>'''
DEPENDENT = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" default-locale="fr-FR"><info><title>Child</title><id>http://www.zotero.org/styles/test-child</id><link rel="independent-parent" href="http://www.zotero.org/styles/test-notes"/></info></style>'''

class ExtendedCSLTests(unittest.TestCase):
    def test_chicago_real_style_and_localized_terms(self):
        item = {'id': 'a', 'type': 'book', 'title': 'Widgets', 'author': [{'family': 'Martin', 'given': 'Jean'}], 'issued': {'date-parts': [[2020]]}}
        result = render([item], [['a'], ['a']], style='chicago-note')
        self.assertEqual(result['style_class'], 'note')
        self.assertEqual(result['citations'][0], 'Jean Martin, *Widgets* (2020).')
        localized_style = NOTE.replace('class="note"', 'class="in-text"').replace('<text variable="title"/>', '<text term="and"/>')
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='fr-FR')['citations'], ['et'])
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='de-DE')['citations'], ['und'])
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='es-ES')['citations'], ['y'])
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='hi-IN')['citations'], ['व'])
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='ja-JP')['citations'], ['と'])
        self.assertEqual(render([item], [['a']], style_xml=localized_style, language='ar')['citations'], ['و'])

    def test_all_official_locale_files_valid_and_cache_hash_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            library = StyleLibrary(directory)
            self.assertEqual(len(library.list_locales()), 63)
            self.assertIn('sr-Cyrl-RS', library.list_locales())
            xml = '<locale xmlns="http://purl.org/net/xbiblio/csl" version="1.0" xml:lang="zz-ZZ"><terms><term name="and">synthetic</term></terms></locale>'
            receipt = library.import_locale(xml)
            self.assertIn('zz-ZZ', StyleLibrary(directory).list_locales())
            path = Path(directory) / 'citation-styles' / 'locales' / ('locale-' + receipt['sha256'] + '.xml')
            path.write_text(xml.replace('synthetic', 'changed'), encoding='utf-8')
            with self.assertRaisesRegex(StyleError, 'hash'):
                library.list_locales()

    def test_missing_locale_is_not_silently_english(self):
        from csl_engine import CSLError
        with self.assertRaisesRegex(CSLError, 'locale unavailable'):
            render([{'id': 'a', 'type': 'book', 'title': 'Widgets'}], [['a']], style_xml=NOTE, language='zz-ZZ')

    def test_note_class(self):
        with tempfile.TemporaryDirectory() as directory:
            library = StyleLibrary(directory)
            imported = library.import_style(NOTE)
            bundle = library.resolve_bundle(imported['id'])
            result = render([{'id': 'a', 'type': 'book', 'title': 'Notes'}], [['a']], style_xml=bundle['style_xml'], language=bundle['language'], locales=bundle['locales'])
            self.assertEqual(result['style_class'], 'note')
            self.assertEqual(result['citations'], ['Notes'])

    def test_dependent_resolution_and_missing_language(self):
        with tempfile.TemporaryDirectory() as directory:
            library = StyleLibrary(directory)
            child = library.import_style(DEPENDENT)
            with self.assertRaisesRegex(StyleError, 'parent'):
                library.resolve_bundle(child['id'])
            library.import_style(NOTE)
            bundle = library.resolve_bundle(child['id'])
            self.assertEqual(bundle['language'], 'fr-FR')
            self.assertEqual(bundle['style_class'], 'note')
            with self.assertRaisesRegex(StyleError, 'locale'):
                library.resolve_bundle(child['id'], language='zz-ZZ')

    def test_network_requires_explicit_approval_and_safe_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            library = StyleLibrary(directory)
            with self.assertRaises(StyleError):
                library.retrieve_official(style_id='apa')
            for identifier in ('https://127.0.0.1/a', '../apa', 'apa?x=1'):
                with self.assertRaises(StyleError):
                    library.retrieve_official(style_id=identifier, approved=True)

    def test_official_retrieval_follows_only_pinned_parent(self):
        child = DEPENDENT.replace('default-locale="fr-FR"', '')
        seen = []
        class FakeOpener:
            def open(self, request, timeout):
                seen.append(request.full_url)
                filename = request.full_url.rsplit('/', 1)[-1]
                return io.BytesIO((child if filename == 'test-child.csl' else NOTE).encode())
        with tempfile.TemporaryDirectory() as directory, patch('csl_styles.urllib.request.build_opener', return_value=FakeOpener()):
            library = StyleLibrary(directory)
            row = library.retrieve_official(style_id='test-child', approved=True)
            self.assertEqual(library.resolve_bundle(row['id'])['style_class'], 'note')
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(url.startswith('https://raw.githubusercontent.com/citation-style-language/styles/89c63834393a5f806e375b0816dc110c3be93d44/') for url in seen))

    def test_dependent_loop_fails(self):
        first = DEPENDENT.replace('http://www.zotero.org/styles/test-notes', 'http://www.zotero.org/styles/test-child')
        with tempfile.TemporaryDirectory() as directory:
            library = StyleLibrary(directory)
            row = library.import_style(first)
            with self.assertRaisesRegex(StyleError, 'loop'):
                library.resolve_bundle(row['id'])

    def test_imported_external_parent_cannot_trigger_network(self):
        malicious = DEPENDENT.replace('http://www.zotero.org/styles/test-notes', 'https://127.0.0.1/private')
        with tempfile.TemporaryDirectory() as directory, patch('csl_styles.urllib.request.build_opener') as opener:
            library = StyleLibrary(directory)
            row = library.import_style(malicious)
            with self.assertRaisesRegex(StyleError, 'official'):
                library.retrieve_dependencies(row['id'], approved=True)
            opener.assert_not_called()

if __name__ == '__main__':
    unittest.main()
