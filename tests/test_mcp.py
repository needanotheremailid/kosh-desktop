"""MCP stdio contract tests; fake app client, no service/model/private files."""
import io
import json
from pathlib import Path
import tempfile
import unittest

import mcp_server


class Client:
    token = 'synthetic_private_token_12345'

    def __init__(self):
        self.calls = []

    def verify(self):
        return {'ready': True}

    def request(self, path, body=None, binary=False):
        self.calls.append((path, body, binary))
        return (b'Synthetic MCP export', 'text/plain') if binary else {'ok': True, 'fixture': self.token}

    def redacted(self, value):
        return str(value).replace(self.token, '[redacted]')


class McpTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.server = mcp_server.Server(client=self.client)

    def rpc(self, method, params=None, id=1):
        return self.server.handle({'jsonrpc': '2.0', 'id': id, 'method': method, **({'params': params} if params is not None else {})})

    def tool(self, name, arguments):
        return self.rpc('tools/call', {'name': name, 'arguments': arguments})['result']

    def test_initialize_negotiation_notifications_and_ping(self):
        initialized = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'Synthetic client', 'version': '1'}})['result']
        self.assertEqual(initialized['protocolVersion'], '2025-06-18')
        self.assertEqual(initialized['capabilities'], {'tools': {'listChanged': False}})
        self.assertIsNone(self.server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        self.assertEqual(self.rpc('ping')['result'], {})
        self.assertEqual(self.rpc('initialize', {'protocolVersion': '2099-01-01'})['result']['protocolVersion'], '2025-06-18')

    def test_tools_have_explicit_schemas_and_exclude_global_state_or_generic_routes(self):
        tools = self.rpc('tools/list')['result']['tools']
        self.assertEqual(len(tools), 63)
        self.assertNotIn('kosh_state', {tool['name'] for tool in tools})
        self.assertNotIn('request', {tool['name'] for tool in tools})
        for tool in tools:
            self.assertFalse(tool['inputSchema']['additionalProperties'])
            self.assertNotIn('route', tool['inputSchema']['properties'])
            self.assertNotIn('url', tool['inputSchema']['properties'])
        scoped = next(tool for tool in tools if tool['name'] == 'kosh_workspace_state')
        self.assertIn('workspace', scoped['inputSchema']['required'])

    def test_citation_style_tools_read_only_explicit_local_file_and_fixed_routes(self):
        self.assertFalse(self.tool('kosh_citation_styles', {})['isError'])
        self.assertEqual(self.client.calls[-1], ('/api/citation/styles', None, False))
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder) / 'selected.csl'
            selected.write_text('<style>synthetic XML</style>', encoding='utf-8')
            self.assertFalse(self.tool('kosh_citation_style_import', {'file': str(selected)})['isError'])
        self.assertEqual(self.client.calls[-1], ('/api/citation/styles/import', {'xml': '<style>synthetic XML</style>'}, False))

    def test_custom_style_export_pattern_rejects_urls_paths_and_incomplete_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'widgets.md'
            for bad in ('../outside.csl', 'https://styles.example/file', 'csl-' + 'a' * 63, 'csl-' + 'g' * 64):
                self.assertTrue(self.tool('kosh_export', {'workspace': 'w', 'format': 'md', 'citation_style': bad, 'output': str(output)})['isError'])
            self.assertEqual(self.client.calls, [])
            style = 'csl-' + 'a' * 64
            self.assertFalse(self.tool('kosh_export', {'workspace': 'w', 'format': 'md', 'citation_style': style, 'output': str(output)})['isError'])
            self.assertEqual(self.client.calls[-1][0], '/api/export')
            self.assertEqual(self.client.calls[-1][1]['citation_style'],style)

    def test_scoped_tool_routes_and_redacts_entire_result(self):
        result = self.tool('kosh_workspace_state', {'workspace': 'w'})
        self.assertEqual(self.client.calls, [('/api/state?workspace_id=w', None, False)])
        self.assertFalse(result['isError'])
        self.assertNotIn(self.client.token, json.dumps(result))
        self.assertIn('[redacted]', result['content'][0]['text'])

    def test_invalid_args_or_false_consent_never_reach_client(self):
        for name, arguments in (('kosh_workspace_state', {}), ('kosh_workspace_state', {'workspace': 'w', 'route': '/api/state'}), ('kosh_assist_send', {'preview': 'p', 'consent': False}), ('kosh_folder_apply', {'preview': 'p', 'approve': False}), ('unknown_tool', {})):
            result = self.tool(name, arguments)
            self.assertTrue(result['isError'])
        self.assertEqual(self.client.calls, [])

    def test_send_and_apply_have_required_caller_attested_approval(self):
        self.tool('kosh_folder_assist_run', {'preview': 'p', 'consent': True})
        self.assertEqual(self.client.calls[-1], ('/api/folder-assist/run', {'preview_id': 'p', 'consent': True, 'consent_version': 1}, False))
        self.tool('kosh_folder_apply', {'preview': 'p', 'approve': True})
        self.assertEqual(self.client.calls[-1], ('/api/folder-edits/apply', {'preview_id': 'p', 'approve': True, 'approval_version': 1}, False))

    def test_binary_export_requires_explicit_no_clobber_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'widgets.md'
            result = self.tool('kosh_export', {'workspace': 'w', 'format': 'md', 'output': str(output)})
            self.assertFalse(result['isError'])
            self.assertEqual(output.read_bytes(), b'Synthetic MCP export')
            result = self.tool('kosh_export', {'workspace': 'w', 'format': 'md', 'output': str(output)})
            self.assertTrue(result['isError'])
            self.assertEqual(output.read_bytes(), b'Synthetic MCP export')

    def test_stdio_bounds_parse_errors_notifications_and_serial_responses(self):
        requests = 'x' * 200 + '\nnot JSON\n' + json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n' + json.dumps({'jsonrpc': '2.0', 'id': 8, 'method': 'ping'}) + '\n'
        output = io.StringIO()
        mcp_server.serve(self.server, io.StringIO(requests), output, max_line=128)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]['error']['code'], -32600)
        self.assertEqual(responses[1]['error']['code'], -32700)
        self.assertEqual(responses[2], {'jsonrpc': '2.0', 'id': 8, 'result': {}})
        self.assertEqual(self.rpc('unknown_method')['error']['code'], -32601)


if __name__ == '__main__':
    unittest.main()
