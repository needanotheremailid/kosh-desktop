"""Synthetic CSL integration and boundary checks; no private documents."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os
import subprocess

from csl_engine import CSLError, metadata_to_csl, render


def item(identifier, title='Widgets', year='2024', **fields):
    metadata = dict(type='journal_article', title=title, year=year,
                    author_list=[{'family': 'Doe', 'given': 'Jane'}],
                    journal='Widget Review', volume='3', issue='2', pages='10-20')
    metadata.update(fields)
    return metadata_to_csl(identifier, metadata)


class CSLIntegration(unittest.TestCase):
    def test_mapping_uses_immutable_id_and_only_publication_pages(self):
        value = item('immutable', doi='https://doi.org/10.1000/widget', pages='10-20')
        self.assertEqual(value['id'], 'immutable')
        self.assertEqual(value['page'], '10-20')
        self.assertEqual(value['DOI'], '10.1000/widget')
        self.assertEqual(value['issued'], {'date-parts': [[2024]]})

    def test_real_apa_sorts_bibliography_and_retroactively_disambiguates(self):
        result = render([item('beta', 'Beta'), item('alpha', 'Alpha')], [['beta'], ['alpha']], 'apa')
        self.assertEqual(result['citations'], ['(Doe, 2024b)', '(Doe, 2024a)'])
        self.assertEqual(result['bibliography_ids'], ['alpha', 'beta'])
        self.assertIn('*Widget Review*, *3*', result['references'][0])

    def test_real_vancouver_collapses_three_consecutive_citations(self):
        # Official vancouver.csl citation collapse="citation-number"; IEEE's
        # current official style has no collapse option and lists each number.
        result = render([item(str(n)) for n in range(1, 4)], [['1', '2', '3']], 'vancouver')
        self.assertEqual(result['citations'], ['(1–3)'])
        self.assertEqual(result['item_numbers'], {'1': 1, '2': 2, '3': 3})

    def test_metadata_markup_is_literal_not_executable_or_formatting(self):
        result = render([item('x', '<script>alert(1)</script> *literal*')], [['x']], 'apa')
        self.assertNotIn('<script>', result['references'][0])
        self.assertIn('\\*literal\\*', result['references'][0])

    def test_invalid_doi_never_becomes_a_fabricated_doi_url(self):
        metadata = dict(type='journal_article', title='Widgets', doi='invalid-entered-doi')
        mapped = metadata_to_csl('x', metadata)
        self.assertNotIn('DOI', mapped)
        result = render([mapped], [['x']], 'apa')
        self.assertNotIn('https://doi.org/invalid-entered-doi', result['references'][0])
        self.assertEqual(metadata['doi'], 'invalid-entered-doi')

    def test_literal_entities_ampersands_and_angle_markup_survive_once(self):
        result = render([item('x', 'Widgets & units &amp; <script>x</script> <i>literal</i>')], [['x']], 'apa')
        self.assertIn('Widgets & units &amp;', result['references'][0])
        self.assertIn('\\<script\\>x\\</script\\>', result['references'][0])
        self.assertIn('\\<i\\>literal\\</i\\>', result['references'][0])
        self.assertNotIn('*literal*', result['references'][0])

    def test_custom_independent_style_uses_superscript(self):
        style = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text"><info><title>Synthetic</title><id>urn:synthetic</id></info><citation><layout vertical-align="sup"><text variable="citation-number"/></layout></citation><bibliography><layout><text variable="title" font-style="italic"/></layout></bibliography></style>'''
        result = render([item('x')], [['x']], style_xml=style)
        self.assertEqual(result['citations'], ['<sup>1</sup>'])
        self.assertEqual(result['references'], ['*Widgets*'])

    def test_numeric_bibliography_sort_changes_numbers_in_processor(self):
        style = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text"><info><title>Synthetic sorted numeric</title><id>urn:synthetic:sorted</id></info><citation><layout prefix="[" suffix="]"><text variable="citation-number"/></layout></citation><bibliography><sort><key variable="title"/></sort><layout><text variable="citation-number" suffix=". "/><text variable="title"/></layout></bibliography></style>'''
        result = render([item('b', 'Beta'), item('a', 'Alpha')], [['b'], ['a']], style_xml=style)
        self.assertEqual(result['citations'], ['[2]', '[1]'])
        self.assertEqual(result['item_numbers'], {'b': 2, 'a': 1})
        self.assertEqual(result['references'], ['1. Alpha', '2. Beta'])

    def test_uncited_input_never_spawns_runtime(self):
        with patch('csl_engine.subprocess.run', side_effect=AssertionError('runtime used')):
            self.assertEqual(render([], [], 'apa')['references'], [])

    def test_missing_runtime_is_explicit_error(self):
        with patch('csl_engine._node_binary', side_effect=CSLError('CSL runtime missing')):
            with self.assertRaisesRegex(CSLError, 'runtime missing'):
                render([item('x')], [['x']])

    def test_unknown_style_and_external_entity_rejected(self):
        with self.assertRaises(CSLError):
            render([], [], '../outside')
        with self.assertRaises(CSLError):
            render([item('x')], [['x']], style_xml='<!DOCTYPE style SYSTEM "file:///private"><style/>')

    def test_timeout_is_explicit_without_private_error_details(self):
        with patch('csl_engine.subprocess.run', side_effect=subprocess.TimeoutExpired('fixed runtime', 15)):
            with self.assertRaisesRegex(CSLError, 'timed out'):
                render([item('x')], [['x']])

    def test_node_startup_hooks_are_removed_and_script_is_fixed(self):
        response = SimpleNamespace(returncode=0, stdout=b'{"citations":["(1)"],"references":[],"bibliography_ids":[],"citation_format":"numeric"}')
        with patch.dict(os.environ, {'NODE_OPTIONS': '--require=untrusted.js', 'NODE_PATH': 'untrusted'}):
            with patch('csl_engine.subprocess.run', return_value=response) as runner:
                render([item('x')], [['x']])
        command = runner.call_args.args[0]
        self.assertTrue(command[-1].endswith('scripts\\csl_render.js'))
        self.assertNotIn('NODE_OPTIONS', runner.call_args.kwargs['env'])
        self.assertNotIn('NODE_PATH', runner.call_args.kwargs['env'])
        self.assertEqual(runner.call_args.kwargs['timeout'], 15)

    def test_unknown_cluster_item_is_rejected_by_real_processor(self):
        with self.assertRaises(CSLError):
            render([item('x')], [['missing']])

    def test_input_size_limit_precedes_runtime(self):
        with patch('csl_engine.subprocess.run', side_effect=AssertionError('runtime used')):
            with self.assertRaisesRegex(CSLError, 'limit'):
                render([item('x', 'x' * 8_000_001)], [['x']])


if __name__ == '__main__':
    unittest.main()
