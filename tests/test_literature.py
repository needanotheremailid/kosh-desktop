import unittest
from unittest.mock import patch
import literature

class LiteratureTests(unittest.TestCase):
    def test_crossref_literal_fields_and_structured_authors(self):
        source={"message":{"total-results":1,"items":[{"DOI":"10.1234/example","title":["A catalogue record"],"author":[{"family":"Rivera","given":"Alex"}],"published":{"date-parts":[[2024]]},"container-title":["Example Journal"],"volume":"2","issue":"1","page":"10-12","type":"journal-article"}]}}
        with patch.object(literature,"json_fetch",return_value=source):
            total,items=literature.crossref("example")
        self.assertEqual(total,1);self.assertEqual(items[0]["author_list"],[{"family":"Rivera","given":"Alex"}])
        self.assertEqual(items[0]["pages"],"10-12");self.assertEqual(items[0]["url"],"https://doi.org/10.1234/example")

    def test_public_query_only_and_ephemeral_result(self):
        service=literature.SearchService()
        item=literature.record("crossref","10.1234/example","A record",url="https://doi.org/10.1234/example")
        with patch.object(literature,"crossref",return_value=(1,[item])) as run:
            result=service.search("crossref"," public topic ")
        run.assert_called_once_with("public topic")
        saved=service.get_result(result["results"][0]["result_id"])
        saved["title"]="changed"
        self.assertEqual(service.get_result(result["results"][0]["result_id"])["title"],"A record")
        with self.assertRaises(literature.LiteratureError):service.get_result("missing")
        with self.assertRaises(literature.LiteratureError):service.search("arbitrary","topic")
        with self.assertRaises(literature.LiteratureError):service.search("pubmed","\x00")

    def test_catalogue_is_not_full_text_and_bib_is_inert(self):
        item=literature.record("openalex","W12","Unsafe } \\ command",url="https://openalex.org/W12",authors="Given Family")
        data=literature.bibtex(item).decode()
        self.assertIn("not the full article",data);self.assertIn(r"\}",data);self.assertIn(r"\textbackslash{}",data)
        self.assertIn("@misc",data)

    def test_pubmed_pdf_page_is_not_publication_pagination(self):
        xml=b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12</PMID><Article><ArticleTitle>Record title</ArticleTitle><AuthorList><Author><LastName>Rivera</LastName><ForeName>Alex</ForeName></Author></AuthorList><Journal><Title>Example</Title><JournalIssue><Volume>2</Volume><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal><Pagination><MedlinePgn>50-53</MedlinePgn></Pagination></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        with patch.object(literature,"json_fetch",return_value={"esearchresult":{"idlist":["12"],"count":"1"}}),patch.object(literature,"fetch",return_value=xml),patch.object(literature.time,"sleep"):
            total,items=literature.pubmed("example")
        self.assertEqual(items[0]["pages"],"50-53");self.assertNotIn("full_text",items[0]);self.assertEqual(items[0]["url"],"https://pubmed.ncbi.nlm.nih.gov/12/")

    def test_openalex_keeps_display_name_without_guessing(self):
        with patch.object(literature,"json_fetch",return_value={"meta":{"count":1},"results":[{"id":"https://openalex.org/W12","title":"A title","authorships":[{"author":{"display_name":"Given Family"}}]}]}):
            _,items=literature.openalex("topic")
        self.assertEqual(items[0]["authors"],"Given Family");self.assertEqual(items[0]["author_list"],[{'literal':'Given Family'}])

    def test_group_authors_and_truncation_remain_explicit(self):
        source={'message':{'items':[{'DOI':'10.1234/group','title':['Group paper'],'author':[{'family':'Rivera','given':'Alex'},{'name':'Example Working Group'}]}]}}
        with patch.object(literature,'json_fetch',return_value=source):
            _,items=literature.crossref('group')
        self.assertIn('Example Working Group',items[0]['authors'])
        self.assertEqual(items[0]['author_list'],[{'family':'Rivera','given':'Alex'},{'literal':'Example Working Group'}])
        item=literature.record('crossref','id','T'*1001,authors='A'*4001,author_list=[{'family':'F','given':'G'}]*201)
        self.assertTrue(item['warnings'])
        self.assertEqual(len(item['author_list']),200)
        self.assertEqual(len(item['title']),1000)

    def test_pubmed_nlm_abbreviation_and_initials_are_distinct_fields(self):
        xml=b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12</PMID><MedlineJournalInfo><MedlineTA>Example NLM</MedlineTA></MedlineJournalInfo><Article><ArticleTitle>Record</ArticleTitle><AuthorList><Author><LastName>Rivera</LastName><Initials>AJ</Initials></Author></AuthorList><Journal><Title>Example Full</Title><ISOAbbreviation>Different ISO</ISOAbbreviation><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        with patch.object(literature,'json_fetch',return_value={'esearchresult':{'idlist':['12'],'count':'1'}}),patch.object(literature,'fetch',return_value=xml),patch.object(literature.time,'sleep'):
            _,items=literature.pubmed('topic')
        self.assertEqual(items[0]['journal_abbreviation'],'Example NLM')
        self.assertEqual(items[0]['author_list'][0]['given'],'A J')
        with patch.object(literature,'json_fetch',return_value={'hitCount':1,'resultList':{'result':[{'id':'12','source':'MED','title':'Record','journalTitle':'Full journal title'}]}}):
            _,items=literature.europepmc('topic')
        self.assertEqual(items[0]['journal_abbreviation'],'')

if __name__=="__main__":unittest.main()
