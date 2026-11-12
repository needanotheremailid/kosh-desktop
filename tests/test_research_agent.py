"""The new research reads remain explicit, workspace-scoped CLI/MCP operations."""
import unittest

import agent
import mcp_server


class Client:
    def verify(self): return {'ready': True}
    def request(self, route, body=None): return {'route': route, 'body': body}


class ResearchAgent(unittest.TestCase):
    def test_cli_read_routes_have_explicit_scope(self):
        parser = agent.build_parser()
        workspace, document = 'a' * 32, 'b' * 32
        for command in ('research-packet', 'research-comparison'):
            args = parser.parse_args([command, '--workspace', workspace, '--document', document])
            response = agent.execute(args, Client())
            self.assertEqual(response['route'], '/api/research/' + command.split('-', 1)[1])
            self.assertEqual(response['body']['document_ids'], [document])
            self.assertEqual(response['body']['workspace_id'], workspace)
        args = parser.parse_args(['research-overview', '--workspace', workspace])
        self.assertEqual(agent.execute(args, Client())['route'], '/api/research/overview?workspace_id=' + workspace)

    def test_mcp_requires_workspace_and_selected_sources(self):
        registry = mcp_server.manifest()
        for name in ('kosh_research_packet', 'kosh_research_comparison'):
            schema = registry[name]['inputSchema']
            self.assertIn('workspace', schema['required'])
            self.assertIn('documents', schema['required'])
            self.assertEqual(schema['properties']['documents']['maxItems'], 10)
            self.assertFalse(schema['additionalProperties'])


if __name__ == '__main__': unittest.main()
