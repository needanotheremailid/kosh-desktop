"""Bounded history reads preserve exact versions and workspace identity."""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from backend import AppError, Store


class RevisionPages(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST','/api/workspaces',{'title':'Workshop'})['id']
        self.note = self.store.dispatch('POST','/api/notes',{'workspace_id':self.workspace,'title':'First title','body':'Original <widgets>\nहिन्दी\n[[reference:missing]]'})
        self.original = dict(self.note)
        self.note = self.store.dispatch('POST','/api/notes',{'workspace_id':self.workspace,'id':self.note['id'],'version':1,'title':'Revised title','body':'Revised widgets\nਪੰਜਾਬੀ'})

    def get(self, **extra):
        return self.store.dispatch('GET','/api/notes/history?'+urlencode({'id':self.note['id'],'workspace_id':self.workspace,'expected_version':str(self.note['version']),**extra}))

    def test_metadata_has_no_bodies_and_exact_version_preserves_characters(self):
        changes = self.store.db.total_changes
        metadata = self.get(metadata_only='1')
        self.assertEqual(metadata['current_version'],2)
        self.assertEqual(metadata['workspace_id'],self.workspace)
        self.assertEqual([row['version'] for row in metadata['revisions']],[2,1])
        self.assertTrue(all('body' not in row for row in metadata['revisions']))
        self.assertIsNone(metadata['next_before'])
        exact = self.get(version='1')
        self.assertEqual(exact['revisions'][0]['body'],self.original['body'])
        self.assertEqual(exact['revisions'][0]['title'],'First title')
        self.assertEqual(self.store.db.total_changes,changes)

    def test_metadata_paginates_without_omitting_oldest_version(self):
        with self.store.db:
            for version in range(2,152):
                payload = {**self.original,'version':version,'title':f'Widgets {version}'}
                self.store.db.execute("INSERT INTO revisions VALUES('note',?,?,?)",(self.note['id'],version,json.dumps(payload)))
            self.store.db.execute('UPDATE notes SET version=152 WHERE id=?',(self.note['id'],))
        self.note['version']=152
        page = self.get(metadata_only='1')
        self.assertEqual(len(page['revisions']),100)
        self.assertEqual(page['revisions'][0]['version'],152)
        self.assertEqual(page['revisions'][-1]['version'],53)
        self.assertEqual(page['next_before'],53)
        tail = self.get(metadata_only='1',before='53')
        self.assertEqual([row['version'] for row in tail['revisions']],list(range(52,0,-1)))
        self.assertIsNone(tail['next_before'])

    def test_scoped_reads_refuse_stale_missing_and_invalid_requests(self):
        other = self.store.dispatch('POST','/api/workspaces',{'title':'Other'})['id']
        for fields,status in [({'metadata_only':'1','workspace_id':other},404),
                              ({'metadata_only':'1','expected_version':'1'},409),
                              ({'version':'3'},404),({'version':'0'},400),
                              ({'version':'1','metadata_only':'1'},400),
                              ({'metadata_only':'1','before':'-1'},400)]:
            with self.subTest(fields=fields):
                with self.assertRaises(AppError) as error:
                    self.get(**fields)
                self.assertEqual(error.exception.status,status)

    def test_legacy_history_remains_exact_and_ascending(self):
        result=self.store.dispatch('GET','/api/notes/history?id='+self.note['id'])
        self.assertEqual([row['version'] for row in result['revisions']],[1,2])
        self.assertEqual(result['revisions'][0]['body'],self.original['body'])


if __name__=='__main__':
    unittest.main()
