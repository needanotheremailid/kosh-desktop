"""Synthetic loopback CLI contract checks; no app/user data or model calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent

TOKEN = 'synthetic_agent_token_never_print_123456'
BUILD = 'a' * 64


class Handler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.answer()

    def do_POST(self):
        self.answer()

    def answer(self):
        size = int(self.headers.get('Content-Length', '0'))
        body = json.loads(self.rfile.read(size)) if size else None
        self.server.requests.append((self.path, self.headers.get('X-App-Token'), body))
        status = 200
        mime = 'application/json'
        if self.path == '/health':
            content = {'app': agent.APP_ID, 'ready': True, 'build': self.server.build}
        elif self.headers.get('X-App-Token') != TOKEN:
            status, content = 401, {'error': TOKEN}
        elif self.path == '/api/state' or self.path.startswith('/api/state?workspace_id='):
            content = {'workspaces': [{'id': 'w'}], 'notes': [{'id': 'n', 'workspace_id': 'w', 'version': 4}], 'matrix': []}
        elif self.path == '/api/notes':
            if body.get('version') == 1:
                status, content = 409, {'error': 'Conflict '+TOKEN}
            else:
                content = {**body, 'id': body.get('id', 'created'), 'version': 5}
        elif self.path.startswith('/api/backup?'):
            mime, content = 'application/zip', b'PK\x03\x04synthetic\x00\xffbytes'
        elif self.path == '/api/import':
            content = {'results': [{'name': body['files'][0]['name'], 'status': 'imported'}]}
        else:
            content = {'result': 'ok'}
        raw = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.build = BUILD
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.session = {'port': self.server.server_port, 'token': TOKEN, 'build': BUILD, 'pid': 123}
        (self.root / 'agent-session.json').write_text(json.dumps(self.session), encoding='utf-8')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def command(self, *args):
        output = io.StringIO()
        status = agent.main(['--data-dir', str(self.root), *args], out=output)
        self.assertNotIn(TOKEN, output.getvalue())
        return status, json.loads(output.getvalue())

    def test_health_pins_app_build_and_header_without_credential_in_url(self):
        status, result = self.command('health')
        self.assertEqual(status, 0)
        self.assertEqual(result['app'], agent.APP_ID)
        self.assertEqual(self.server.requests[0], ('/health', None, None))
        self.server.build = 'b' * 64
        status, result = self.command('health')
        self.assertEqual(status, 1)
        self.assertIn('does not match', result['error'])

    def test_stale_note_conflict_redacts_credentials_and_sends_expected_version(self):
        status, result = self.command('save-note', '--workspace', 'w', '--id', 'n', '--version', '1', '--title', 'Synthetic', '--body', 'New text')
        self.assertEqual(status, 1)
        self.assertEqual(result['status'], 409)
        self.assertIn('[redacted]', result['error'])
        self.assertEqual(self.server.requests[-1][2]['version'], 1)
        self.assertEqual(self.server.requests[-1][2]['body'], 'New text')
        self.assertEqual(self.server.requests[-1][1], TOKEN)

    def test_update_without_expected_version_never_posts(self):
        status, result = self.command('save-note', '--workspace', 'w', '--id', 'n', '--title', 'Synthetic', '--body', 'Text')
        self.assertEqual(status, 1)
        self.assertEqual(result['status'], 409)
        self.assertEqual(len(self.server.requests), 1)

    def test_binary_backup_is_exact_and_existing_output_is_preserved(self):
        target = self.root / 'backup.zip'
        status, result = self.command('backup', '--workspace', 'w', '--output', str(target))
        self.assertEqual(status, 0)
        self.assertEqual(target.read_bytes(), b'PK\x03\x04synthetic\x00\xffbytes')
        self.assertEqual(result['bytes'], len(target.read_bytes()))
        self.assertEqual(self.server.requests[-1][0], '/api/backup?workspace_id=w&history=0')
        target.write_bytes(b'Existing user output')
        status, result = self.command('backup', '--workspace', 'w', '--output', str(target))
        self.assertEqual(status, 1)
        self.assertEqual(target.read_bytes(), b'Existing user output')
        self.assertFalse(list(self.root.glob('.research-export-*')))

    def test_backup_history_is_explicitly_opt_in(self):
        target = self.root / 'backup-history.zip'
        status, result = self.command('backup', '--workspace', 'w', '--include-history', '--output', str(target))
        self.assertEqual(status, 0)
        self.assertEqual(self.server.requests[-1][0], '/api/backup?workspace_id=w&history=1')
        self.assertEqual(result['bytes'], len(target.read_bytes()))

    def test_import_reads_only_named_files_and_has_per_file_receipts(self):
        selected = self.root / 'selected.txt'
        selected.write_text('Only explicit synthetic input', encoding='utf-8')
        status, result = self.command('import', '--workspace', 'w', str(selected), str(self.root / 'missing.txt'))
        self.assertEqual(status, 1)
        self.assertEqual([r['status'] for r in result['results']], ['imported', 'error'])
        self.assertEqual(len([r for r in self.server.requests if r[0] == '/api/import']), 1)

    def test_invalid_port_and_parser_errors_are_json_and_do_not_contact_service(self):
        self.session['port'] = True
        (self.root / 'agent-session.json').write_text(json.dumps(self.session), encoding='utf-8')
        status, result = self.command('state')
        self.assertEqual(status, 1)
        self.assertIn('port', result['error'])
        self.assertEqual(self.server.requests, [])
        status, result = self.command('search')
        self.assertEqual(status, 2)
        self.assertEqual(result['status'], 2)

    def test_redirect_policy_refuses_followup(self):
        with self.assertRaises(agent.AgentError):
            agent.NoRedirects().redirect_request(None, None, 302, 'redirect', {}, 'https://unapproved.example')

    def test_scoped_list_preserves_saved_version_and_rejects_unknown_workspace(self):
        status, result = self.command('notes', '--workspace', 'w')
        self.assertEqual(status, 0)
        self.assertEqual(result['notes'][0]['version'], 4)
        status, result = self.command('evidence', '--workspace', 'missing')
        self.assertEqual(status, 1)
        self.assertEqual(result['status'], 404)


if __name__ == '__main__':
    unittest.main()
