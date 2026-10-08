"""Private loopback HTTP shell for Research Desktop; no external HTTP service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
APP_ID = "pg-research-desktop"
MAX_BODY = 64 * 1024 * 1024


def source_hash():
    h = hashlib.sha256()
    paths = json.loads((ROOT / 'runtime-files.json').read_text(encoding='utf-8'))
    for relative in sorted(paths):
        h.update(relative.encode('utf-8'))
        h.update((ROOT / relative).read_bytes())
    return h.hexdigest()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, idle_minutes=30):
        super().__init__(address, Handler)
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.build = source_hash()
        self.store.auto_backups.build = self.build
        self.authority = f'127.0.0.1:{self.server_port}'
        self.origin = f'http://{self.authority}'
        self.last_activity = time.monotonic()
        self.active_jobs = 0
        self.job_lock = threading.Lock()
        self.idle_seconds = idle_minutes * 60
        from updater import Updater, UpdateError
        from upgrade import UpgradeError
        self.updater_error = ''
        try:
            self.updater = Updater(ROOT)
        except (UpdateError, UpgradeError, OSError):
            self.updater = None
            self.updater_error = 'In-app updates are unavailable because the local update cache could not be accessed. Your research workspace remains available.'
        self.update_handoff = False
        self.update_verification = False

    def watchdog(self):
        while True:
            time.sleep(10)
            with self.job_lock:
                stop = not self.active_jobs and time.monotonic() - self.last_activity > self.idle_seconds
            if stop:
                self.shutdown()
                return


class Handler(BaseHTTPRequestHandler):
    server: LocalServer
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        # No document names, prompts, tokens or paths in access logs.
        pass

    def send_content(self, content, status=200, content_type='application/json; charset=utf-8', filename=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if filename:
            from urllib.parse import quote
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(filename))
        self.end_headers()
        self.wfile.write(content)

    def safe_request(self):
        if self.headers.get('Host') != self.server.authority:
            self.close_connection = True
            self.send_content({'error': 'Invalid local host.'}, 403)
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            self.close_connection = True
            self.send_content({'error': 'This request did not come from this app.'}, 403)
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.close_connection = True
            self.send_content({'error': 'Cross-site access is not permitted.'}, 403)
            return False
        return True

    def handle_request(self):
        from backend import AppError
        if not self.safe_request():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if self.command == 'GET' and path == '/health':
            self.send_content({'app': APP_ID, 'build': self.server.build, 'ready': True})
            return
        if not path.startswith('/api/'):
            if self.command != 'GET':
                self.send_content({'error': 'Unsupported route.'}, 404)
                return
            allowed = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/app.css': ('app.css', 'text/css; charset=utf-8')}
            allowed.update({('/'+name): (name, 'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8') for name in ('reading.js', 'reading.css', 'writing_review.js', 'writing_review.css', 'project_review.js', 'project_review.css', 'auto_backup.js', 'auto_backup.css', 'reviewer.js', 'reviewer.css', 'maintenance.js', 'updater.js', 'updater.css')})
            if path not in allowed:
                self.send_content({'error': 'Not found.'}, 404)
                return
            name, mime = allowed[path]
            try:
                content = (ROOT / 'ui' / name).read_bytes()
                if name == 'index.html':
                    content = content.replace(b'__APP_TOKEN__', self.server.token.encode('ascii'))
                self.send_content(content, content_type=mime)
            except OSError:
                self.send_content({'error': 'The interface is not available. Rebuild the app.'}, 503)
            return
        supplied = self.headers.get('X-App-Token', '')
        if not secrets.compare_digest(supplied, self.server.token):
            self.close_connection = True
            self.send_content({'error': 'This app session expired. Reopen the app window.'}, 401)
            return
        self.server.last_activity = time.monotonic()
        body = {}
        try:
            if self.command == 'POST':
                if self.headers.get('Transfer-Encoding'):
                    raise AppError('Chunked requests are unsupported.', 400)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise AppError('Expected JSON.', 415)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise AppError('Invalid request size.', 400)
                if size <= 0 or size > MAX_BODY:
                    self.close_connection = True
                    raise AppError('Request must be below 64 MB.', 413)
                self.connection.settimeout(30)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise AppError('Incomplete request.', 400)
                try:
                    body = json.loads(raw.decode('utf-8'))
                except (ValueError, UnicodeError):
                    raise AppError('Invalid JSON request.', 400)
                if not isinstance(body, dict):
                    raise AppError('Expected an object.', 400)
            if path == '/api/heartbeat' and self.command == 'POST':
                self.send_content({'ok': True})
                return
            if path == '/api/shutdown' and self.command == 'POST':
                self.send_content({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.server.update_verification and self.command == 'POST' and path != '/api/updates/activate':
                raise AppError('Update startup is being verified. Editing is paused until activation.', 409)
            with self.server.job_lock:
                if self.server.update_handoff:
                    raise AppError('An update is starting. Close this Kosh window; existing data is retained.', 409)
                self.server.active_jobs += 1
            try:
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if path.startswith('/api/updates/'):
                    from updater import UpdateError
                    from upgrade import UpgradeError
                    try:
                        if self.server.updater is None:
                            raise AppError(self.server.updater_error, 409)
                        if self.command == 'GET' and path == '/api/updates/status':
                            result = self.server.updater.status()
                            result['activation_required'] = self.server.update_verification
                        elif self.command == 'POST' and path == '/api/updates/activate':
                            if body:
                                raise AppError('Activation expects an empty request.')
                            if self.server.update_verification:
                                from updater import activation_ready
                                if not activation_ready(ROOT, self.server.build):
                                    raise AppError('This updated copy has no verified completion receipt. Reopen the previous Kosh and resume or recover the retained update.', 409)
                            self.server.update_verification = False
                            self.server.store.auto_backups.start()
                            result = {'activated': True, 'build': self.server.build}
                        elif self.command == 'POST' and path in {'/api/updates/check', '/api/updates/download'}:
                            if set(body) != {'consent'}:
                                raise AppError('An explicit release-source consent is required.')
                            operation = self.server.updater.check if path.endswith('/check') else self.server.updater.download
                            result = operation(consent=body['consent'])
                        elif self.command == 'POST' and path in {'/api/updates/install', '/api/updates/resume'}:
                            if set(body) != {'approve', 'accept_unsigned'}:
                                raise AppError('Explicit install and unsigned-publisher approval are required.')
                            with self.server.job_lock:
                                if self.server.active_jobs != 1 or self.server.store.active_asks or self.server.store.auto_backups.status()['running']:
                                    raise AppError('Wait for current app operations to finish before installing.', 409)
                                operation = self.server.updater.resume if path.endswith('/resume') else self.server.updater.install
                                result = operation(approve=body['approve'], accept_unsigned=body['accept_unsigned'])
                                self.server.update_handoff = True
                        else:
                            raise AppError('Update operation is unavailable.', 404)
                        try:
                            self.send_content(result)
                        finally:
                            if self.server.update_handoff:
                                threading.Thread(target=self.server.shutdown, daemon=True).start()
                        return
                    except (UpdateError, UpgradeError) as error:
                        raise AppError(str(error), 409) from None
                binaries = {'/api/file', '/api/page', '/api/export', '/api/backup'}
                if (self.command == 'GET' and path in binaries) or (self.command == 'POST' and path == '/api/export'):
                    content, mime, filename = self.server.store.file_response(path, body if self.command == 'POST' else query)
                    self.send_content(content, content_type=mime, filename=filename)
                else:
                    payload = body if self.command == 'POST' else query
                    self.send_content(self.server.store.dispatch(self.command, self.path, payload))
            finally:
                with self.server.job_lock:
                    self.server.active_jobs -= 1
                self.server.last_activity = time.monotonic()
        except AppError as exc:
            if self.command == 'POST':
                self.close_connection = True
            self.send_content({'error': str(exc)}, getattr(exc, 'status', 400))
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except Exception as exc:
            # Keep full private diagnostics local; do not expose document data.
            self.send_content({'error': 'The operation failed. Your existing data is retained. Try again or reopen the app.'}, 500)
            print('Local operation failed: ' + type(exc).__name__, flush=True)

    do_GET = handle_request
    do_POST = handle_request

    def do_OPTIONS(self):
        self.send_content({'error': 'Cross-origin access is unavailable.'}, 403)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--port', type=int)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--idle-minutes', type=int, default=30)
    parser.add_argument('--update-verification', action='store_true')
    args = parser.parse_args()
    from backend import Store
    store = Store(args.data_dir.resolve())
    port_file = args.data_dir.resolve() / 'listen-port.json'
    port = args.port
    if port is None:
        try:
            port = int(json.loads(port_file.read_text(encoding='utf-8'))['port'])
            if not 1024 <= port <= 65535:
                raise ValueError('Invalid saved port')
        except FileNotFoundError:
            port = 0
        except (OSError, ValueError, KeyError, TypeError):
            store.close()
            raise SystemExit('Saved local port is invalid. Existing data was retained.')
    try:
        server = LocalServer(('127.0.0.1', port), store, args.idle_minutes)
    except OSError:
        store.close()
        raise SystemExit('The saved local port is occupied. Close the program using this port and retry; the port and draft recovery were retained.')
    if args.port is None:
        port_tmp = port_file.with_suffix('.tmp')
        port_tmp.write_text(json.dumps({'port': server.server_port}), encoding='utf-8')
        os.replace(port_tmp, port_file)
    ready = {'app': APP_ID, 'build': server.build, 'port': server.server_port, 'pid': os.getpid()}
    # Same-user automation capability; never include this token in readiness/logs.
    agent_session = args.data_dir.resolve() / 'agent-session.json'
    agent_tmp = agent_session.with_suffix('.tmp')
    agent_tmp.write_text(json.dumps({**ready, 'token': server.token}), encoding='utf-8')
    os.replace(agent_tmp, agent_session)
    if args.ready_file:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.ready_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(ready), encoding='utf-8')
        os.replace(tmp, args.ready_file)
    print(f'Research Desktop ready on port {server.server_port}', flush=True)
    from updater import verification_required
    server.update_verification = verification_required(ROOT, server.build, args.update_verification)
    threading.Thread(target=server.watchdog, daemon=True).start()
    if not server.update_verification:
        store.auto_backups.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if hasattr(store, 'close'):
            store.close()
        try:
            if json.loads(agent_session.read_text(encoding='utf-8')).get('pid') == os.getpid():
                agent_session.unlink()
        except (OSError, ValueError):
            pass
        if args.ready_file and args.ready_file.exists():
            try:
                existing = json.loads(args.ready_file.read_text(encoding='utf-8'))
                if existing.get('pid') == os.getpid():
                    args.ready_file.unlink()
            except (OSError, ValueError):
                pass


if __name__ == '__main__':
    main()
