import base64
from pathlib import Path
import tempfile
import unittest
from backend import Store


class ProjectReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST','/api/workspaces',{'title':'Widget paper'})['id']

    def review(self):
        return self.store.dispatch('GET','/api/project-review?workspace_id='+self.workspace)

    def note(self, body):
        return self.store.dispatch('POST','/api/notes',{'workspace_id':self.workspace,'title':'Draft','body':body})

    def test_empty_is_not_ready_and_other_workspace_is_excluded(self):
        other=self.store.dispatch('POST','/api/workspaces',{'title':'Other'})['id']
        self.store.dispatch('POST','/api/notes',{'workspace_id':other,'title':'Private other','body':'[[reference:missing]]'})
        result=self.review()
        self.assertEqual(result['notes'],[])
        self.assertEqual(result['totals']['drafts'],0)
        self.assertIn('not a readiness',result['notice'])

    def test_saved_claims_references_and_staleness_reconcile(self):
        note=self.note('Widgets are blue.\n[[reference:missing]]')
        self.store.dispatch('POST','/api/reading/claim',{'workspace_id':self.workspace,'expected_version':0,'note_id':note['id'],'note_version':1,'claim_anchor':'Widgets are blue.','status':'needs_source'})
        self.note('A second draft without recorded reviews.')
        result=self.review()
        self.assertEqual(result['totals']['drafts'],2)
        self.assertEqual(result['totals']['drafts_without_reviews'],1)
        self.assertEqual(result['totals']['claims'],1)
        self.assertEqual(result['totals']['needs_source'],1)
        self.assertEqual(result['totals']['unresolved_references'],1)
        self.store.dispatch('POST','/api/notes',{'workspace_id':self.workspace,'id':note['id'],'version':1,'title':'Draft','body':'Widgets may be blue.\n[[reference:missing]]'})
        self.assertEqual(self.review()['totals']['stale_claims'],1)

    def test_failed_source_check_is_reported_not_counted_as_clean(self):
        document=self.store.dispatch('POST','/api/import',{'workspace_id':self.workspace,'files':[{'name':'widgets.txt','data':base64.b64encode(b'Widgets are blue.').decode()}]})['results'][0]['document']
        self.note('A source [[reference:'+document['id']+']]')
        (self.store.root/self.store._document(document['id'])['path']).write_bytes(b'changed')
        result=self.review()
        self.assertEqual(result['totals']['failed_checks'],1)
        self.assertIsNone(result['totals']['unresolved_references'])
        self.assertEqual(result['notes'][0]['check_status'],'failed')


if __name__=='__main__': unittest.main()
