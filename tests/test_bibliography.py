"""Independent synthetic bibliography fixtures; no catalogue/network calls."""
import json
import unittest

from bibliography import BibliographyError, export_csl_json, export_ris, parse_bibliography


class BibliographyTests(unittest.TestCase):
    def test_balanced_multirecord_and_explicit_names(self):
        parsed = parse_bibliography(r'''@article{alpha,
title={A {nested, protected} title}, author={Doe, Jane and {Widget Working Group}},
year=2024, journal="Widget \"Review\"", volume={3}, number={2}, pages={10--20}, doi={10.1000/widget}}
@book(beta, title="Café & design", author={Anonymous Team}, publisher={Example Press}, year={2023})''', 'bib')
        self.assertEqual(len(parsed['records']), 2)
        first, second = parsed['records']
        self.assertEqual(first['title'], 'A nested, protected title')
        self.assertEqual(first['author_list'], [{'family': 'Doe', 'given': 'Jane'}, {'literal': 'Widget Working Group'}])
        self.assertEqual(first['journal'], 'Widget "Review"')
        self.assertEqual(first['issue'], '2')
        self.assertEqual(second['type'], 'book')
        self.assertEqual(second['publisher'], 'Example Press')
        self.assertEqual(second['author_list'], [{'literal': 'Anonymous Team'}])

    def test_macros_are_reported_and_missing_facts_not_guessed(self):
        parsed = parse_bibliography('@string{j = "Example"}\n@article{a,title={Known},journal=j,year=jan}', 'bibtex')
        self.assertEqual(parsed['records'][0]['title'], 'Known')
        self.assertEqual(parsed['records'][0]['year'], '')
        self.assertNotIn('journal', parsed['records'][0])
        self.assertIn('macro', ' '.join(parsed['warnings']).lower())
        with self.assertRaises(BibliographyError):
            parse_bibliography('@article{x,title={unclosed}', 'bib')

    def test_quoted_literals_concat_comments_and_escaped_punctuation(self):
        parsed = parse_bibliography('% leading comment\n@misc{a, title="A, title" # { and more}, note={x}, author={Doe, Jane}, url={https://example.test/a}}', 'bib')
        self.assertEqual(parsed['records'][0]['title'], 'A, title and more')
        self.assertEqual(parsed['records'][0]['url'], 'https://example.test/a')

    def test_ris_records_roundtrip_and_csl_literals(self):
        fixture = 'TY  - JOUR\nID  - widgets\nTI  - Café widgets\nAU  - Doe, Jane\nAU  - Widget Group\nPY  - 2024\nJO  - Widget Review\nVL  - 3\nIS  - 2\nSP  - 10\nEP  - 20\nDO  - 10.1000/widget\nUR  - https://example.test/widget\nER  -\n\nTY  - BOOK\nTI  - Designs\nPB  - Example Press\nER  -\n'
        result = parse_bibliography(fixture, 'ris')
        self.assertEqual(len(result['records']), 2)
        first = result['records'][0]
        self.assertEqual(first['pages'], '10-20')
        self.assertEqual(first['author_list'], [{'family': 'Doe', 'given': 'Jane'}, {'literal': 'Widget Group'}])
        roundtrip = parse_bibliography(export_ris(result['records']), 'ris')
        self.assertEqual(roundtrip['records'], result['records'])
        csl = json.loads(export_csl_json(result['records']))
        self.assertEqual(csl[0]['type'], 'article-journal')
        self.assertEqual(csl[0]['author'][1], {'literal': 'Widget Group'})
        self.assertEqual(csl[0]['issued'], {'date-parts': [[2024]]})
        self.assertEqual(csl[1]['publisher'], 'Example Press')
        self.assertNotIn('issued', csl[1])

    def test_ris_date_and_unknown_types_remain_explicit(self):
        result = parse_bibliography('TY  - UNKN\nTI  - A\nPY  - forthcoming\nER  -', 'ris')
        self.assertEqual(result['records'][0]['year'], 'forthcoming')
        self.assertEqual(result['records'][0]['type'], 'other')
        self.assertTrue(result['warnings'])
        self.assertEqual(json.loads(export_csl_json(result['records']))[0]['issued'], {'literal': 'forthcoming'})
        with self.assertRaises(BibliographyError):
            parse_bibliography('TI  - outside record', 'ris')
        with self.assertRaises(BibliographyError):
            parse_bibliography('x', 'unknown')

    def test_bibtex_duplicate_field_warns_instead_of_silently_overwriting(self):
        result = parse_bibliography('@article{a,title={First},title={Second}}', 'bib')
        self.assertEqual(result['records'][0]['title'], 'First')
        self.assertIn('duplicate', ' '.join(result['warnings']).lower())

    def test_exports_do_not_invent_missing_authors_or_dates(self):
        item = {'id': 'minimal', 'title': 'Only a title', 'authors': '', 'author_list': [], 'type': 'other', 'year': ''}
        csl = json.loads(export_csl_json([item]))[0]
        self.assertNotIn('author', csl)
        self.assertNotIn('issued', csl)
        self.assertNotIn('PY  -', export_ris([item]))

    def test_ris_page_ranges_and_literal_author_punctuation_preserved(self):
        item = {'id': 'literal', 'title': 'Test', 'authors': 'Group, Incorporated',
                'author_list': [{'literal': 'Group, Incorporated'}], 'year': '', 'type': 'other', 'pages': 'S10--S20'}
        exported = export_ris([item])
        self.assertIn('AU  - Group, Incorporated', exported)
        self.assertIn('SP  - S10\nEP  - S20', exported)
        csl = json.loads(export_csl_json([item]))[0]
        self.assertEqual(csl['author'], [{'literal': 'Group, Incorporated'}])

    def test_unclosed_quoted_field_and_limit_return_clear_errors(self):
        with self.assertRaises(BibliographyError):
            parse_bibliography('@article{a,title="Bad}', 'bib')
        with self.assertRaises(BibliographyError):
            parse_bibliography('x' * 2_000_001, 'bib')


if __name__ == '__main__':
    unittest.main()
