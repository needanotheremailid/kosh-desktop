"""PubMed references keep their PMID and are not saved twice, using invented records only."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import literature
from backend import Store

XML = b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>4242</PMID><Article><ArticleTitle>Invented harbour lantern study</ArticleTitle><Journal><Title>Invented Journal</Title><JournalIssue><Volume>3</Volume><PubDate><Year>2021</Year></PubDate></JournalIssue></Journal><AuthorList><Author><LastName>Ng</LastName><ForeName>Ada</ForeName></Author></AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'


class PmidReferences(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented PMIDs'})['id']
        self.store.literature = literature.SearchService()

    def lookup(self):
        self.store.literature.last.clear()  # The one-second per-index guard is tested elsewhere.
        with patch('literature.fetch', return_value=XML):
            return self.store.dispatch('POST', '/api/literature/lookup', {'workspace_id': self.workspace, 'provider': 'pubmed', 'identifier': '4242', 'identifier_type': 'pmid'})

    def test_pubmed_record_carries_pmid_and_saves_once(self):
        first = self.lookup()['results'][0]
        self.assertEqual(first['pmid'], '4242')
        saved = self.store.dispatch('POST', '/api/literature/save', {'workspace_id': self.workspace, 'result_id': first['result_id']})
        self.assertEqual(saved['document']['metadata']['pmid'], '4242')
        again = self.store.dispatch('POST', '/api/literature/save', {'workspace_id': self.workspace, 'result_id': self.lookup()['results'][0]['result_id']})
        self.assertEqual(again['document']['id'], saved['document']['id'])
        self.assertIn('same DOI or PMID', again['notice'])
        self.assertEqual(sum(1 for d in self.store.dispatch('GET', '/api/state', {})['documents'] if d['workspace_id'] == self.workspace), 1)

    def test_pmid_match_finds_an_imported_source_with_that_pmid(self):
        imported = self.store.dispatch('POST', '/api/import', {'workspace_id': self.workspace, 'files': [{'name': 'notes.txt', 'data': base64.b64encode(b'Invented notes.').decode()}]})['results'][0]['document']
        self.store.dispatch('POST', '/api/metadata', {'id': imported['id'], 'expected_metadata_version': 0, 'metadata': {'pmid': '4242'}})
        again = self.store.dispatch('POST', '/api/literature/save', {'workspace_id': self.workspace, 'result_id': self.lookup()['results'][0]['result_id']})
        self.assertEqual(again['document']['id'], imported['id'])


if __name__ == '__main__':
    unittest.main()
