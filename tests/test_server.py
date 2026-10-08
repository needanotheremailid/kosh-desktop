"""Independent HTTP boundary acceptance with a synthetic store only."""
import http.client
import json
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import LocalServer


class SyntheticStore:
    def __init__(self):
        self.auto_backups = SimpleNamespace(build='')
    def dispatch(self, method, path, body):
        return {'fixture': True, 'method': method, 'path': path}
    def file_response(self, path, query):
        return b'<script>window.attacker=1</script>', 'text/plain; charset=utf-8', 'hostile.txt'


class BoundaryTests(unittest.TestCase):
    def test_unavailable_update_cache_does_not_block_local_app(self):
        from updater import UpdateError
        with patch('updater.Updater', side_effect=UpdateError('Private update cache unavailable')):
            server = LocalServer(('127.0.0.1', 0), SyntheticStore())
        try:
            self.assertIsNone(server.updater)
            self.assertIn('unavailable', server.updater_error)
        finally:
            server.server_close()
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(('127.0.0.1', 0), SyntheticStore())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def request(self, path, token=True, method='GET', origin=None, host=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Host': host or self.server.authority}
        if token: headers['X-App-Token'] = self.server.token
        if origin: headers['Origin'] = origin
        if body is not None:
            body = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        status, metadata, data = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return status, metadata, data

    def test_document_reads_require_session(self):
        self.assertEqual(self.request('/api/file?id=fixture', token=False)[0], 401)

    def test_watchdog_waits_for_background_backup(self):
        from unittest.mock import Mock
        backup = self.server.store.auto_backups
        with patch.object(backup, 'status', create=True,
                          side_effect=[{'running': True}, {'running': False}]) as status, \
                patch('server.time.sleep'), patch('server.time.monotonic', return_value=10000), \
                patch.object(self.server, 'shutdown') as shutdown, \
                patch.object(self.server, 'last_activity', 0):
            self.server.watchdog()
            self.assertEqual(status.call_count, 2)
            shutdown.assert_called_once()

    def test_unattended_verification_releases_port_soon_then_restores_normal_idle(self):
        try:
            self.server.set_verification(True)
            self.assertEqual(self.server.idle_seconds, 120)
            self.assertTrue(self.server.update_verification)
            self.server.set_verification(False)
            self.assertEqual(self.server.idle_seconds, self.server.normal_idle_seconds)
        finally:
            self.server.set_verification(False)

    def test_update_quiesces_scheduler_and_restarts_on_refusal(self):
        from unittest.mock import Mock
        from updater import UpdateError
        backup = SimpleNamespace(status=lambda: {'running': False}, stop=Mock(), start=Mock())
        events = []
        backup.stop.side_effect = lambda: events.append('stopped')
        def refuse(**kwargs):
            self.assertEqual(events, ['stopped'])
            raise UpdateError('Fixture refusal')
        with patch.object(self.server.store, 'auto_backups', backup), \
                patch.object(self.server.store, 'active_asks', 0, create=True), \
                patch.object(self.server, 'updater', SimpleNamespace(install=refuse)):
            status, _, _ = self.request('/api/updates/install', method='POST',
                                       body={'approve': True, 'accept_unsigned': True})
            self.assertEqual(status, 409)
            backup.start.assert_called_once()
            self.assertFalse(self.server.update_handoff)

    def test_foreign_origin_blocked_even_with_valid_session(self):
        self.assertEqual(self.request('/api/state', origin='https://unrelated.example')[0], 403)

    def test_dns_rebinding_host_blocked(self):
        self.assertEqual(self.request('/api/state', host='attacker.example')[0], 403)

    def test_authorized_api_succeeds_without_origin_on_get(self):
        status, _, data = self.request('/api/state')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['fixture'])

    def test_reader_identifier_survives_http_routing(self):
        import base64
        import tempfile
        from backend import Store
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            workspace = store.dispatch('POST', '/api/workspaces', {'title': 'Routing fixture'})
            imported = store.dispatch('POST', '/api/import', {'workspace_id': workspace['id'], 'files': [{'name': 'routing.txt', 'data': base64.b64encode(b'Independent reader passage').decode()}]})
            source = imported['results'][0]['document']
            original = self.server.store
            self.server.store = store
            try:
                status, _, data = self.request('/api/document?id=' + source['id'])
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(data)['text_pages'][0]['text'], 'Independent reader passage')
            finally:
                self.server.store = original
                store.close()

    def test_downloads_cannot_be_interpreted_as_html(self):
        status, headers, data = self.request('/api/file?id=fixture')
        self.assertEqual(status, 200)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
        self.assertTrue(headers['Content-Type'].startswith('text/plain'))
        self.assertIn(b'<script>', data)

    def test_static_path_traversal_not_served(self):
        self.assertEqual(self.request('/../runtime.json')[0], 404)

    def test_excessive_body_rejected_before_read(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.putrequest('POST', '/api/import')
        conn.putheader('X-App-Token', self.server.token)
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Content-Length', str(70 * 1024 * 1024))
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 413)
        response.read()
        conn.close()


if __name__ == '__main__': unittest.main()
