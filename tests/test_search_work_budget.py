"""Result source integrity must remain checked without reading discarded sources."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import Store, AppError


class SearchBudgetTests(unittest.TestCase):
    def test_rank_then_verify_only_returned_originals_and_refuse_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'data')
            try:
                workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Search budget'})['id']
                for number in range(55):
                    store.dispatch('POST', '/api/import', {'workspace_id': workspace, 'files': [{
                        'name': '%03d.txt' % number,
                        'data': base64.b64encode(('Recall source number %d' % number).encode()).decode()}]})
                with patch.object(store, '_bytes', wraps=store._bytes) as reads:
                    result = store.dispatch('POST', '/api/search', {'workspace_id': workspace, 'query': 'Recall'})['results']
                self.assertEqual(len(result), 50)
                self.assertEqual(len(reads.call_args_list), 50)
                self.assertEqual({call.args[0]['id'] for call in reads.call_args_list}, {row['document_id'] for row in result})
                source = store._document(result[0]['document_id'])
                path = store.root / source['path']
                path.write_bytes(b'changed')
                with self.assertRaises(AppError):
                    store.dispatch('POST', '/api/search', {'workspace_id': workspace, 'query': 'Recall'})
            finally:
                store.close()
