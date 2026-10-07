"""Scoped agent adapters for reading tools; no server or private records."""
import json
from pathlib import Path
import tempfile
import unittest

import agent
import mcp_server


class Client:
    def __init__(self): self.calls = []
    def verify(self): return {'ready': True}
    def request(self, path, body=None, binary=False):
        self.calls.append((path, body))
        return {'version': 2}
    def redacted(self, value): return str(value)


class ReadingAgentTests(unittest.TestCase):
    def test_scoped_reads_and_geometry(self):
        client = Client()
        for command, route in [('reading-state', '/api/reading'), ('reading-duplicates', '/api/reading/duplicates')]:
            args = agent.build_parser().parse_args([command, '--workspace', 'w'])
            agent.execute(args, client)
            self.assertEqual(client.calls[-1], (route+'?workspace_id=w', None))
        args = agent.build_parser().parse_args(['reading-geometry', '--workspace', 'w', '--document', 'd', '--page', '2'])
        agent.execute(args, client)
        self.assertEqual(client.calls[-1], ('/api/reading/geometry?workspace_id=w&document_id=d&page=2', None))

    def test_fixed_writes_pin_scope_and_version(self):
        client = Client()
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary)/'change.json'
            selected.write_text(json.dumps({'document_id': 'd', 'favorite': True}), encoding='utf-8')
            args = agent.build_parser().parse_args(['reading-source-save', '--workspace', 'w', '--version', '1', '--file', str(selected)])
            agent.execute(args, client)
            self.assertEqual(client.calls[-1], ('/api/reading/source', {'workspace_id':'w', 'expected_version':1, 'document_id':'d', 'favorite':True}))
            for hostile in [{'workspace_id':'other'}, {'expected_version':99}, []]:
                selected.write_text(json.dumps(hostile), encoding='utf-8')
                count = len(client.calls)
                with self.assertRaises(agent.AgentError): agent.execute(args, client)
                self.assertEqual(len(client.calls), count)

    def test_mcp_tools_are_fixed_and_scoped(self):
        expected = {'reading_state', 'reading_duplicates', 'reading_geometry', 'reading_source_save', 'reading_resume_save', 'reading_annotation_save', 'reading_claim_save'}
        for suffix in expected:
            tool = mcp_server.TOOLS['kosh_'+suffix]
            self.assertIn('workspace', tool['inputSchema']['required'])
            self.assertFalse(tool['inputSchema']['additionalProperties'])
            self.assertNotIn('route', tool['inputSchema']['properties'])
        result = mcp_server.Server(client=Client()).call('kosh_reading_state', {'workspace':'w'})
        self.assertFalse(result['isError'])
