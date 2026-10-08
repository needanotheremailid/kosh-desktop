"""Integrated loopback API/CLI/MCP checks; invented writing, no external fetches."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import agent
from backend import Store
import mcp_server
from server import LocalServer


class NoRemoteRequests:
    def __getattr__(self, name):
        raise AssertionError('Read-only local status attempted an external transport operation: ' + name)


class NextWorkflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data')
        with patch('updater.cache_root', return_value=self.root / 'updates'):
            self.server = LocalServer(('127.0.0.1', 0), self.store)
        self.server.updater.transport = NoRemoteRequests()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.session = {'port': self.server.server_port, 'token': self.server.token,
                        'build': self.server.build, 'pid': os.getpid()}
        self.client = agent.Client(self.session, timeout=5)
        (self.root / 'agent-session.json').write_text(json.dumps(self.session), encoding='utf-8')
        self.mcp = mcp_server.Server(client=self.client)
        self.mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                         'params': {'protocolVersion': '2025-06-18'}})
        self.workspace = self.client.request('/api/workspaces', {'title': 'Widget revisions'})['id']
        self.note = self.client.request('/api/notes', {'workspace_id': self.workspace, 'title': 'Widget draft',
                                                     'body': 'Widgets are blue. Widgets roll.'})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.store.close()
        self.temp.cleanup()

    def cli(self, *arguments):
        output = io.StringIO()
        status = agent.main(['--data-dir', str(self.root), '--timeout', '5', *arguments], out=output)
        self.assertNotIn(self.server.token, output.getvalue())
        return status, json.loads(output.getvalue())

    def tool(self, name, arguments):
        response = self.mcp.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                    'params': {'name': name, 'arguments': arguments}})['result']
        self.assertNotIn(self.server.token, json.dumps(response))
        result = response.get('structuredContent')
        if result is None:
            result = json.loads(response['content'][0]['text'])
        return response['isError'], result

    def selected_json(self, name, value):
        selected = self.root / name
        selected.write_text(json.dumps(value), encoding='utf-8')
        return selected

    def comment_fields(self):
        return {'note_id': self.note['id'], 'note_version': 1, 'passage_start': 0, 'passage_end': 17,
                'passage': 'Widgets are blue.', 'reviewer': 'Reviewer 1', 'comment': 'Explain the color.'}

    def reviewer_state(self, workspace=None):
        return self.client.request('/api/reviewer?workspace_id=' + (workspace or self.workspace))

    def test_verification_cannot_activate_without_completion_proof(self):
        self.server.update_verification = True
        with patch('updater.activation_ready', return_value=False), patch.object(self.store.auto_backups, 'start') as start:
            with self.assertRaises(agent.AgentError) as rejected:
                self.client.request('/api/updates/activate', {})
            self.assertEqual(rejected.exception.status, 409)
            self.assertTrue(self.server.update_verification)
            start.assert_not_called()
        with patch('updater.activation_ready', return_value=True), patch.object(self.store.auto_backups, 'start') as start:
            result = self.client.request('/api/updates/activate', {})
            self.assertTrue(result['activated'])
            self.assertFalse(self.server.update_verification)
            start.assert_called_once()

    def create_comment(self):
        selected = self.selected_json('comment.json', self.comment_fields())
        status, result = self.cli('reviewer-save', '--workspace', self.workspace, '--version', '0', '--file', str(selected))
        self.assertEqual(status, 0, result)
        self.assertEqual(result['version'], 1)
        return result['comments'][0]

    def test_six_new_tools_and_read_only_status_use_real_http_routes(self):
        manifest = self.mcp.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})['result']['tools']
        self.assertEqual(len(manifest), 63)
        actual = {tool['name']: tool for tool in manifest}
        required = {'kosh_project_review': ['workspace'], 'kosh_reviewer_state': ['workspace'],
                    'kosh_reviewer_save': ['workspace', 'version', 'file'],
                    'kosh_reviewer_export': ['workspace', 'version', 'output'],
                    'kosh_backup_status': [], 'kosh_update_status': []}
        for name, fields in required.items():
            self.assertEqual(actual[name]['inputSchema']['required'], fields)
            self.assertFalse(actual[name]['inputSchema']['additionalProperties'])
        before = self.client.request('/api/state?workspace_id=' + self.workspace)
        for command, tool, arguments in (
                ('project-review', 'kosh_project_review', {'workspace': self.workspace}),
                ('reviewer-state', 'kosh_reviewer_state', {'workspace': self.workspace}),
                ('backup-status', 'kosh_backup_status', {}),
                ('update-status', 'kosh_update_status', {})):
            flags = ['--workspace', self.workspace] if arguments else []
            status, cli = self.cli(command, *flags)
            self.assertEqual(status, 0, cli)
            failed, mcp = self.tool(tool, arguments)
            self.assertFalse(failed, mcp)
            if command == 'project-review':
                self.assertEqual(cli['totals']['drafts'], 1)
                self.assertEqual(mcp['totals']['drafts_without_reviews'], 1)
                self.assertEqual(mcp['totals']['claims'], 0)
                self.assertIn('not a readiness certification', cli['notice'])
            elif command == 'reviewer-state':
                self.assertEqual(cli['comments'], [])
                self.assertEqual(mcp['version'], 0)
            elif command == 'backup-status':
                self.assertFalse(cli['enabled'])
                self.assertFalse(mcp['running'])
                self.assertIsNone(mcp['last_success'])
            else:
                self.assertEqual(cli['phase'], 'idle')
                self.assertEqual(mcp['signature'], 'not_verified')
                self.assertFalse(mcp['activation_required'])
        self.assertEqual(self.client.request('/api/state?workspace_id=' + self.workspace), before)
        self.assertFalse((self.root / 'updates').exists())

    def test_reviewer_save_refuses_stale_scope_overrides_and_cross_workspace_notes(self):
        row = self.create_comment()
        selected = self.selected_json('response.json', {'id': row['id'], 'response': 'We clarified the description.', 'status': 'responded'})
        status, error = self.cli('reviewer-save', '--workspace', self.workspace, '--version', '0', '--file', str(selected))
        self.assertEqual(status, 1)
        self.assertEqual(error['status'], 409)
        failed, result = self.tool('kosh_reviewer_save', {'workspace': self.workspace, 'version': 1, 'file': str(selected)})
        self.assertFalse(failed, result)
        self.assertEqual(result['version'], 2)
        self.assertEqual(result['comments'][0]['history'][0]['response'], '')
        other = self.client.request('/api/workspaces', {'title': 'Another widget workspace'})['id']
        for override in ({'workspace_id': other}, {'expected_version': 9}):
            selected = self.selected_json('override.json', {'id': row['id'], 'response': 'Must not replace', **override})
            for use_mcp in (False, True):
                if use_mcp:
                    rejected, result = self.tool('kosh_reviewer_save', {'workspace': self.workspace, 'version': 2, 'file': str(selected)})
                    self.assertTrue(rejected)
                else:
                    status, result = self.cli('reviewer-save', '--workspace', self.workspace, '--version', '2', '--file', str(selected))
                    self.assertEqual(status, 1)
                self.assertIn('workspace/version flags', result['error'])
        failed, result = self.tool('kosh_reviewer_save', {'workspace': self.workspace, 'version': 2,
                                                        'file': str(selected), 'expected_version': 99})
        self.assertTrue(failed)
        self.assertIn('Unknown or missing tool arguments', result['error'])
        cross_scope = self.selected_json('cross-scope.json', self.comment_fields())
        status, error = self.cli('reviewer-save', '--workspace', other, '--version', '0', '--file', str(cross_scope))
        self.assertEqual(status, 1)
        self.assertEqual(error['status'], 404)
        self.assertEqual(self.reviewer_state()['version'], 2)
        self.assertEqual(self.reviewer_state()['comments'][0]['response'], 'We clarified the description.')
        self.assertEqual(self.reviewer_state(other)['comments'], [])
        current_note = self.client.request('/api/state?workspace_id=' + self.workspace)['notes'][0]
        self.assertEqual(current_note['body'], 'Widgets are blue. Widgets roll.')
        self.assertEqual(current_note['version'], 1)

    def test_reviewer_letter_cli_mcp_saved_content_and_no_clobber(self):
        row = self.create_comment()
        self.client.request('/api/reviewer/comment', {'workspace_id': self.workspace, 'expected_version': 1,
                                                     'id': row['id'], 'response': 'We explain blue pigment.',
                                                     'revised_text': 'Widgets have blue pigment.', 'status': 'responded'})
        output = self.root / 'Response letter.txt'
        status, result = self.cli('reviewer-export', '--workspace', self.workspace, '--version', '2', '--output', str(output))
        self.assertEqual(status, 0, result)
        content = output.read_text(encoding='utf-8')
        for expected in ('Reviewer 1', 'Explain the color.', 'We explain blue pigment.', 'Widgets are blue.',
                         'Recorded revised wording is absent from the current saved manuscript.', '1 retained earlier record'):
            self.assertIn(expected, content)
        output.write_bytes(b'Existing user response letter\r\n')
        status, error = self.cli('reviewer-export', '--workspace', self.workspace, '--version', '2', '--output', str(output))
        self.assertEqual(status, 1)
        self.assertEqual(output.read_bytes(), b'Existing user response letter\r\n')
        failed, result = self.tool('kosh_reviewer_export', {'workspace': self.workspace, 'version': 2, 'output': str(output)})
        self.assertTrue(failed)
        self.assertEqual(output.read_bytes(), b'Existing user response letter\r\n')
        fresh = self.root / 'MCP response.txt'
        failed, result = self.tool('kosh_reviewer_export', {'workspace': self.workspace, 'version': 2, 'output': str(fresh)})
        self.assertFalse(failed, result)
        self.assertEqual(fresh.read_text(encoding='utf-8'), content)
        stale = self.root / 'Stale export.txt'
        status, error = self.cli('reviewer-export', '--workspace', self.workspace, '--version', '1', '--output', str(stale))
        self.assertEqual(status, 1)
        self.assertEqual(error['status'], 409)
        self.assertFalse(stale.exists())
        self.assertFalse(list(self.root.glob('.research-export-*')))

    def test_actual_cli_backup_mcp_restore_retains_history_and_remaps_links(self):
        row = self.create_comment()
        self.client.request('/api/reviewer/comment', {'workspace_id': self.workspace, 'expected_version': 1,
                                                     'id': row['id'], 'response': 'We clarified blue pigment.',
                                                     'status': 'responded', 'archived': True})
        before = self.reviewer_state()
        backup = self.root / 'Widget workspace.zip'
        status, result = self.cli('backup', '--workspace', self.workspace, '--output', str(backup))
        self.assertEqual(status, 0, result)
        with zipfile.ZipFile(backup) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['reviewer']['comments'][0]['history'][0]['comment'], 'Explain the color.')
        self.assertFalse(manifest['history_included'])
        failed, result = self.tool('kosh_restore', {'file': str(backup)})
        self.assertFalse(failed, result)
        restored = self.reviewer_state(result['workspace_id'])
        self.assertNotEqual(result['workspace_id'], self.workspace)
        self.assertNotEqual(restored['comments'][0]['id'], row['id'])
        self.assertNotEqual(restored['comments'][0]['note_id'], self.note['id'])
        self.assertEqual(restored['comments'][0]['response'], 'We clarified blue pigment.')
        self.assertEqual(restored['comments'][0]['history'][0]['response'], '')
        self.assertTrue(restored['comments'][0]['archived'])
        self.assertFalse(restored['comments'][0]['stale'])
        restored_note = self.client.request('/api/state?workspace_id=' + result['workspace_id'])['notes'][0]
        self.assertEqual(restored['comments'][0]['note_id'], restored_note['id'])
        self.assertEqual(restored_note['body'], 'Widgets are blue. Widgets roll.')
        self.assertEqual(self.reviewer_state(), before)


if __name__ == '__main__':
    unittest.main()
