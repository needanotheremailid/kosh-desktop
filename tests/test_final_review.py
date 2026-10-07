"""Concrete final review regressions; synthetic inputs and no provider requests."""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import backend
import mcp_server
import upgrade
from backend import Store, AppError


class FinalReview(unittest.TestCase):
    def test_embedding_response_has_bounded_room_for_32_large_vectors(self):
        raw = json.dumps({'embeddings': [[0.12345678901234567] * 8192 for _ in range(32)]}).encode()
        self.assertGreater(len(raw), 2 * 1024 * 1024)
        with patch('backend.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(raw)
            result = backend.ollama_request('/api/embed', {'input': ['synthetic'] * 32})
        self.assertEqual(len(result['embeddings']), 32)
        self.assertEqual(len(result['embeddings'][0]), 8192)
        with patch('backend.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(raw)
            with self.assertRaisesRegex(AppError, 'size limit'):
                backend.ollama_request('/api/generate', {})

    def test_mcp_reopens_session_each_operation_without_replaying_writes(self):
        server = mcp_server.Server(data_dir=Path('synthetic-nonexistent-data'))
        first, second = Mock(), Mock()
        with patch('mcp_server.agent.read_session', side_effect=[{'token':'first'}, {'token':'second'}]) as read, patch('mcp_server.agent.Client', side_effect=[first,second]):
            self.assertIs(server._client(), first)
            self.assertIs(server._client(), second)
        self.assertEqual(read.call_count, 2)

    def test_unreadable_unrelated_process_uses_exclusive_data_probe(self):
        roots = (Path('synthetic-old'), Path('synthetic-new'))
        with patch('upgrade._powershell', return_value={'service':False,'browser':False,'unknown':True}), patch('upgrade._exclusive_data_probe') as probe:
            self.assertFalse(upgrade._running_processes(roots)['service'])
            probe.assert_called_once_with(roots)
        with patch('upgrade._powershell', return_value={'service':False,'browser':False,'unknown':True}), patch('upgrade._exclusive_data_probe', side_effect=upgrade.UpgradeError('Selected data in use')):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade._running_processes(roots)

    def test_provenance_chain_keeps_mapping_and_marks_truncation(self):
        mapping = 'Unverified local OCR derivative of retained source ' + 'a'*32 + '; 1->7'
        combined = backend.append_provenance(mapping, 'Catalogue linked', mapping)
        self.assertEqual(combined.count(mapping), 1)
        self.assertIn('Catalogue linked', combined)
        bounded = backend.append_provenance(mapping, 'x'*1200)
        self.assertLessEqual(len(bounded), 1000)
        self.assertIn(mapping, bounded)
        self.assertIn('provenance truncated', bounded)

    def test_ask_withholds_truncated_answer_and_keeps_excerpts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                workspace = store.dispatch('POST','/api/workspaces',{'title':'Synthetic bounded ask'})['id']
                store.dispatch('POST','/api/import',{'workspace_id':workspace,'files':[{'name':'widgets.txt','data':base64.b64encode(b'Thirty synthetic widgets were observed.').decode()}]})
                with patch.object(store,'models',return_value={'available':True,'models':[{'name':'synthetic-local'}]}), patch('backend.ollama_request',return_value={'response':'An incomplete claim [C1]','done_reason':'length'}):
                    answer = store.dispatch('POST','/api/ask',{'workspace_id':workspace,'question':'widgets','model':'synthetic-local'})
                self.assertEqual(answer['mode'], 'retrieval')
                self.assertNotIn('An incomplete claim',answer['answer'])
                self.assertIn('incomplete',answer['warning'])
            finally:
                store.close()


if __name__ == '__main__': unittest.main()
