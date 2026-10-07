import unittest
from unittest.mock import patch
import literature


class DiscoveryCompletion(unittest.TestCase):
    def test_federated_search_preserves_partial_results_and_deduplicates_doi(self):
        item = literature.record('crossref', '10.1234/widget', 'Widget paper', doi='10.1234/widget')
        same = literature.record('pubmed', '7', 'Widget paper', doi='https://doi.org/10.1234/WIDGET')
        other = literature.record('openalex', 'W8', 'Second paper')
        with patch('literature.crossref', return_value=(1, [item])), patch('literature.pubmed', return_value=(1, [same])), patch('literature.europepmc', side_effect=literature.LiteratureError('Index unavailable')), patch('literature.openalex', return_value=(1, [other])):
            service = literature.SearchService()
            result = service.search('all', 'widgets')
        self.assertEqual(len(result['results']), 2)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['errors'][0]['provider'], 'europepmc')
        self.assertEqual(set(result['results'][0]['providers']), {'pubmed', 'crossref'})
        self.assertEqual(service.get_result(result['results'][0]['result_id'])['title'], 'Widget paper')

    def test_markup_and_group_authors_are_preserved_as_text_and_literal_names(self):
        item = literature.record('crossref', '1', 'A <i>widget</i> &amp; study', author_list=[{'family':'Doe','given':'Jane'},{'literal':'Widget Group'}])
        self.assertEqual(item['title'], 'A widget & study')
        self.assertEqual(item['author_list'][1], {'literal':'Widget Group'})

    def test_crossref_keeps_mixed_author_order_and_abstract(self):
        fixture = {'message': {'total-results': 1, 'items': [{
            'DOI': '10.1234/widget', 'title': ['Widget methods'],
            'author': [{'family': 'Doe', 'given': 'Jane'}, {'name': 'Widget Consortium'}, {'family': 'Roe', 'given': 'John'}],
            'abstract': '<jats:p>A <jats:italic>bounded</jats:italic> abstract.</jats:p>'}]}}
        with patch('literature.json_fetch', return_value=fixture):
            _, results = literature.crossref('widget')
        self.assertEqual(results[0]['author_list'], [{'family': 'Doe', 'given': 'Jane'}, {'literal': 'Widget Consortium'}, {'family': 'Roe', 'given': 'John'}])
        self.assertEqual(results[0]['authors'], 'Doe, Jane; Widget Consortium; Roe, John')
        self.assertEqual(results[0]['abstract'], 'A bounded abstract.')

    def test_pubmed_keeps_collective_author_order_and_labelled_abstract(self):
        xml = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>7</PMID><Article>
            <ArticleTitle>Widget methods</ArticleTitle><AuthorList>
            <Author><CollectiveName>Widget Group</CollectiveName></Author>
            <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author></AuthorList>
            <Abstract><AbstractText Label="METHODS">Test <i>cells</i>.</AbstractText><AbstractText Label="RESULTS">No inference.</AbstractText></Abstract>
            </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
        with patch('literature.json_fetch', return_value={'esearchresult': {'count': '1', 'idlist': ['7']}}), patch('literature.fetch', return_value=xml), patch('literature.time.sleep'):
            _, results = literature.pubmed('widget')
        self.assertEqual(results[0]['author_list'], [{'literal': 'Widget Group'}, {'family': 'Doe', 'given': 'Jane'}])
        self.assertEqual(results[0]['authors'], 'Widget Group; Doe, Jane')
        self.assertEqual(results[0]['abstract'], 'METHODS: Test cells. RESULTS: No inference.')

    def test_openalex_preserves_display_names_without_guessing_name_parts(self):
        fixture = {'meta': {'count': 1}, 'results': [{'id': 'https://openalex.org/W7', 'title': 'Widgets',
            'authorships': [{'author': {'display_name': 'Widget Consortium'}}, {'author': {'display_name': 'Jane Doe'}}],
            'abstract_inverted_index': {'Exact': [0], 'abstract.': [1]}}]}
        with patch('literature.json_fetch', return_value=fixture):
            _, results = literature.openalex('widgets')
        self.assertEqual(results[0]['author_list'], [{'literal': 'Widget Consortium'}, {'literal': 'Jane Doe'}])
        self.assertEqual(results[0]['abstract'], 'Exact abstract.')

    def test_europepmc_core_metadata_keeps_group_and_personal_author_order(self):
        fixture = {'hitCount': 1, 'resultList': {'result': [{'id': '7', 'source': 'MED', 'title': 'Widget',
            'authorList': {'author': [{'collectiveName': 'Widget Group'}, {'lastName': 'Doe', 'firstName': 'Jane'}]},
            'journalInfo': {'volume': '2', 'issue': '1', 'journal': {'title': 'Widget Journal', 'medlineAbbreviation': 'Widget J'}},
            'abstractText': '<p>Exact metadata abstract.</p>'}]}}
        with patch('literature.json_fetch', return_value=fixture) as fetch:
            _, results = literature.europepmc('widget')
        self.assertIn('resultType=core', fetch.call_args.args[0])
        self.assertEqual(results[0]['author_list'], [{'literal': 'Widget Group'}, {'family': 'Doe', 'given': 'Jane'}])
        self.assertEqual(results[0]['journal'], 'Widget Journal')
        self.assertEqual(results[0]['journal_abbreviation'], 'Widget J')
        self.assertEqual(results[0]['abstract'], 'Exact metadata abstract.')

    def test_missing_and_truncated_abstract_metadata_are_explicit(self):
        absent = literature.record('crossref', '1', 'Widget')
        self.assertEqual(absent['abstract'], '')
        bounded = literature.record('crossref', '1', 'Widget', abstract='A' * 4001)
        self.assertEqual(bounded['abstract'], 'A' * 4000)
        self.assertIn('Abstract truncated to the bounded metadata field; reference needs review.', bounded['warnings'])

    def test_bibtex_mixed_literal_authors_and_identifiers_remain_metadata(self):
        item = literature.record('crossref', '10.1234/widget_part', 'Widgets',
            author_list=[{'family': 'Doe', 'given': 'Jane'}, {'literal': 'Widget & Group'}],
            doi='10.1234/widget_part', url='https://doi.org/10.1234/widget_part?x=1&y=2')
        text = literature.bibtex(item).decode('utf-8')
        self.assertIn(r'author = {Doe, Jane and {Widget \& Group}}', text)
        self.assertIn('doi = {10.1234/widget_part}', text)
        self.assertIn('url = {https://doi.org/10.1234/widget_part?x=1&y=2}', text)
        self.assertNotIn(r'widget\_part', text)

    def test_exact_doi_lookup_is_encoded_and_cached_without_fuzzy_search(self):
        fixture = {'message': {'DOI': '10.1234/widget_(a)', 'title': ['Exact widget'], 'abstract': 'Exact abstract.'}}
        with patch('literature.json_fetch', return_value=fixture) as fetch:
            service = literature.SearchService()
            result = service.lookup('crossref', 'https://doi.org/10.1234/widget_(a)', 'doi')
        fetch.assert_called_once_with('https://api.crossref.org/works/10.1234%2Fwidget_%28a%29')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['identifier'], '10.1234/widget_(a)')
        self.assertEqual(result['results'][0]['abstract'], 'Exact abstract.')
        self.assertEqual(service.get_result(result['results'][0]['result_id'])['title'], 'Exact widget')

    def test_exact_pmid_lookup_calls_only_efetch_and_checks_returned_identifier(self):
        xml = b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>7</PMID><Article><ArticleTitle>Exact widget</ArticleTitle><Abstract><AbstractText>Exact abstract.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        with patch('literature.fetch', return_value=xml) as fetch, patch('literature.json_fetch') as search:
            result = literature.SearchService().lookup('pubmed', '7', 'pmid')
        search.assert_not_called()
        fetch.assert_called_once_with('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=7&retmode=xml&tool=Kosh')
        self.assertEqual(result['results'][0]['id'], '7')
        self.assertEqual(result['results'][0]['abstract'], 'Exact abstract.')
        with patch('literature.fetch', return_value=xml):
            with self.assertRaisesRegex(literature.LiteratureError, 'requested PMID'):
                literature.SearchService().lookup('pubmed', '8', 'pmid')

    def test_lookup_refuses_invalid_or_mismatched_identifiers_without_fallback(self):
        with patch('literature.fetch') as fetch, patch('literature.json_fetch') as json_fetch:
            for provider, identifier, kind in [('crossref', 'not-a-doi', 'doi'), ('pubmed', '7&db=private', 'pmid'), ('openalex', '7', 'pmid')]:
                with self.subTest(provider=provider, identifier=identifier), self.assertRaises(literature.LiteratureError):
                    literature.SearchService().lookup(provider, identifier, kind)
        fetch.assert_not_called()
        json_fetch.assert_not_called()
        with patch('literature.json_fetch', return_value={'message': {'DOI': '10.1234/other', 'title': ['Wrong record']}}):
            with self.assertRaisesRegex(literature.LiteratureError, 'requested DOI'):
                literature.SearchService().lookup('crossref', '10.1234/widget', 'doi')


if __name__ == '__main__':
    unittest.main()
