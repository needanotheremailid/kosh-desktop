import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent


class RecordingClient:
    def __init__(self):
        self.calls = []

    def verify(self):
        return {'ready': True}

    def request(self, path, body=None):
        self.calls.append((path, body))
        return {'workspaces': [{'id': 'w'}], 'notes': [], 'matrix': []}


class AgentCompletionTests(unittest.TestCase):
    def test_scoped_listing_never_requests_global_state(self):
        client = RecordingClient()
        agent.execute(agent.build_parser().parse_args(['notes', '--workspace', 'w']), client)
        self.assertEqual(client.calls, [('/api/state?workspace_id=w', None)])

    def test_workspace_listing_requests_no_research_bodies(self):
        client = RecordingClient()
        agent.execute(agent.build_parser().parse_args(['workspaces']), client)
        self.assertEqual(client.calls, [('/api/workspaces', None)])

    def test_default_wait_exceeds_provider_deadline(self):
        args = agent.build_parser().parse_args(['health'])
        self.assertGreater(args.timeout, 120)

    def test_metadata_update_sends_user_selected_expected_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'metadata.json'
            path.write_text(json.dumps({'title': 'Widget research'}), encoding='utf-8')
            args = agent.build_parser().parse_args(['save-metadata', '--document', 'd', '--version', '4', '--file', str(path)])
            client = RecordingClient()
            agent.execute(args, client)
            self.assertEqual(client.calls, [('/api/metadata', {'id': 'd', 'metadata': {'title': 'Widget research'}, 'expected_metadata_version': 4})])


if __name__ == '__main__':
    unittest.main()
