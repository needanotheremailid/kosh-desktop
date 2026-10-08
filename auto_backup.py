"""Opt-in local workspace ZIP sets, retained without pruning or OS tasks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
import time

import backend as b
from workspace_archive import FILE_ARCHIVE_LIMIT, hash_file


SET_KEY = 'auto-backup:v1'
SET_NAME = re.compile(r'kosh-backup-[0-9a-f]{32}\Z')
ZIP_NAME = re.compile(r'[0-9a-f]{32}\.zip\Z')
MANIFEST_LIMIT = 4 * 1024 * 1024
PREVIEW_LIFETIME = 15 * 60
MAX_RETRY_SECONDS = 7 * 24 * 60 * 60
new_id = b.new_id


def _defaults():
    return {'enabled': False, 'destination': '', 'interval_minutes': 1440,
            'last_attempt': None, 'last_success': None, 'last_failure': None,
            'last_error': '', 'last_set_path': '', 'last_success_destination': ''}


def _plain_directory(path):
    """No linked/reparse directory component or remote share destination."""
    raw = str(path)
    if raw.startswith(('\\\\', '//')) or not path.is_absolute():
        raise b.AppError('Choose an absolute local folder path, not a network share.')
    if os.name == 'nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(path.anchor) not in (2, 3):
            raise b.AppError('Choose a local fixed or removable drive, not a mapped network drive.')
    # Walk from the drive root: reject an ancestor link before probing anything
    # underneath it, including links that point at a network destination.
    for component in reversed((path, *path.parents)):
        try:
            attributes = component.lstat()
        except OSError:
            raise b.AppError('Backup folder is unavailable. Choose an existing local folder; no folder was created.') from None
        if component.is_symlink() or (getattr(attributes, 'st_file_attributes', 0) & 0x400):
            raise b.AppError('Backup folders cannot use symbolic links or directory junctions.')
    if not path.is_dir():
        raise b.AppError('Choose an existing local folder. No folder was created.')
    return path.resolve()


def _write_new(path, data):
    with path.open('xb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


class AutoBackup:
    def __init__(self, store, *, clock=time.time, build='unknown'):
        self.store = store
        self.clock = clock
        self.build = build
        self._run_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._running = False
        self._previews = {}
        self._retry_delay = 0
        self._retry_not_before = 0
        with store.lock:
            row = store.db.execute('SELECT value FROM settings WHERE key=?', (SET_KEY,)).fetchone()
        self._settings = _defaults()
        if row:
            try:
                saved = json.loads(row[0])
                if not isinstance(saved, dict) or set(saved) != set(self._settings):
                    raise ValueError
                if type(saved['enabled']) is not bool or type(saved['interval_minutes']) is not int or not 15 <= saved['interval_minutes'] <= 10080:
                    raise ValueError
                if any(not isinstance(saved[field], str) for field in ('destination', 'last_error', 'last_set_path', 'last_success_destination')):
                    raise ValueError
                for field in ('last_attempt', 'last_success', 'last_failure'):
                    if saved[field] is not None and (type(saved[field]) not in (int, float) or not 0 <= saved[field] < 100_000_000_000):
                        raise ValueError
                self._settings = saved
            except (ValueError, TypeError):
                # Refuse automatic writes when the persistent opt-in is corrupt.
                self._settings['last_error'] = 'Backup settings are unreadable. Review and save your backup preferences again.'
        if self._settings['last_error'] and self._settings['last_failure'] is not None:
            self._retry_delay = self._settings['interval_minutes'] * 60
            self._retry_not_before = min(self._settings['last_failure'], self.clock()) + self._retry_delay

    def _persist(self):
        with self.store.lock, self.store.db:
            self.store._ensure_open()
            self.store.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                  (SET_KEY, json.dumps(self._settings, ensure_ascii=False)))

    def _destination(self, raw):
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096:
            raise b.AppError('Choose an existing local backup folder.')
        destination = _plain_directory(Path(raw.strip()))
        for protected in (self.store.root, Path(__file__).resolve().parent):
            if destination == protected or destination.is_relative_to(protected):
                raise b.AppError('Choose a backup folder outside Kosh application and data folders.')
        for parent in (destination, *destination.parents):
            if (parent / 'runtime-files.json').is_file() and (parent / 'backend.py').is_file():
                raise b.AppError('Choose a backup folder outside all Kosh installation folders, including retained older copies.')
        return destination

    def configure(self, body):
        if not isinstance(body, dict) or set(body) != {'enabled', 'destination', 'interval_minutes'}:
            raise b.AppError('Backup preferences require enabled, destination and interval_minutes only.')
        if type(body['enabled']) is not bool:
            raise b.AppError('Automatic backup enabled must be true or false.')
        if type(body['interval_minutes']) is not int or not 15 <= body['interval_minutes'] <= 10080:
            raise b.AppError('Backup interval must be 15 minutes to 7 days.')
        if not isinstance(body['destination'], str) or len(body['destination']) > 4096:
            raise b.AppError('Backup destination must be a folder path.')
        # Turning off must remain possible when a removable drive is absent.
        destination = str(self._destination(body['destination'])) if body['enabled'] else body['destination'].strip()
        if not self._run_lock.acquire(blocking=False):
            raise b.AppError('Wait for the current backup before changing its folder or schedule.', 409)
        try:
            if self._stop.is_set():
                raise b.AppError('Backups are shutting down. Reopen Kosh before changing preferences.', 503)
            with self._state_lock:
                prior = dict(self._settings)
                self._settings.update(enabled=body['enabled'], destination=destination, interval_minutes=body['interval_minutes'])
                try:
                    self._persist()
                except Exception:
                    self._settings = prior
                    raise
                self._retry_delay = 0
                self._retry_not_before = 0
        finally:
            self._run_lock.release()
        self._wake.set()
        return self.status()

    def _due(self):
        settings = self._settings
        if not settings['enabled']:
            return None
        success = settings['last_success']
        due = success + settings['interval_minutes'] * 60 if success is not None and success <= self.clock() and settings['last_success_destination'] == settings['destination'] else 0
        # A future success gets one catch-up attempt. An outstanding failure must
        # still observe backoff, including after the system clock moves backward.
        return max(due, self._retry_not_before)

    def status(self):
        with self._state_lock:
            return {**self._settings, 'running': self._running, 'next_due': self._due(),
                    'scheduler_alive': bool(self._thread and self._thread.is_alive()),
                    'clock_warning': 'The saved backup timestamp is in the future. Check the computer clock; a fresh backup is due.' if self._settings['last_success'] is not None and self._settings['last_success'] > self.clock() else '',
                    'notice': 'Saved records and originals from every workspace, including history. Runs while Kosh is open; catches up on launch. Browser-only unsaved recovery is not included. Earlier backups are retained.'}

    def tick(self):
        with self._state_lock:
            due = self._due()
        if due is None or self.clock() < due or self._stop.is_set():
            return None
        return self.run_now()

    def run_now(self):
        if not self._run_lock.acquire(blocking=False):
            return {'ok': False, 'status': 'busy', 'error': 'A backup is already running.'}
        try:
            if self._stop.is_set():
                raise b.AppError('Backups are shutting down. Reopen Kosh before starting a backup.', 503)
            with self._state_lock:
                if not self._settings['enabled']:
                    raise b.AppError('Enable automatic local backups and choose a destination first.')
                self._running = True
                self._settings['last_attempt'] = self.clock()
                destination_text = self._settings['destination']
            published = None
            try:
                with self._state_lock:
                    self._persist()
                destination = self._destination(destination_text)
                set_id = 'kosh-backup-' + new_id()
                final = destination / set_id
                pending = destination / ('.' + set_id + '.incomplete')
                if final.exists():
                    raise b.AppError('A backup with this identity already exists. It was retained; no file was overwritten.', 409)
                with self.store.lock:
                    self.store._ensure_open()
                    workspaces = [dict(row) for row in self.store.db.execute('SELECT id,title FROM workspaces ORDER BY created_at,id')]
                if not workspaces:
                    raise b.AppError('Create a workspace before making a backup. No completed set was published.')
                if len(workspaces) > 10000:
                    raise b.AppError('There are more workspaces than the supported automatic backup set limit. No workspaces were omitted or changed.')
                pending.mkdir(exist_ok=False)
                records = []
                for workspace in workspaces:
                    filename = workspace['id'] + '.zip'
                    if not ZIP_NAME.fullmatch(filename):
                        raise b.AppError('Workspace identity cannot be represented safely in a backup set.')
                    target = pending / filename
                    receipt = self.store.write_backup(workspace['id'], target, include_history=True)
                    checked = self.store.restore_backup_file(target, preview_only=True,
                                                            expected_sha256=receipt['sha256'], expected_size=receipt['bytes'])
                    records.append({'workspace_id': workspace['id'], 'title': workspace['title'], 'file': filename,
                                    'bytes': receipt['bytes'], 'sha256': receipt['sha256'],
                                    'counts': {key: checked[key] for key in ('documents', 'notes', 'matrix', 'chats', 'revisions')}})
                manifest = {'version': 1, 'app': 'kosh-auto-backup', 'set_id': set_id,
                            'created_at': self.clock(), 'history_included': True, 'build': self.build, 'workspaces': records}
                manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
                if len(manifest_bytes) > MANIFEST_LIMIT:
                    raise b.AppError('Automatic backup set manifest exceeds the supported limit. No completed set was published or earlier backup changed.')
                _write_new(pending / 'manifest.json', manifest_bytes)
                # Windows rename refuses an existing destination; each set also has
                # a fresh UUID. Incomplete directories stay excluded and retained.
                if final.exists():
                    raise b.AppError('Backup identity collided. Existing backup retained.', 409)
                pending.rename(final)
                published = str(final)
                if (final / 'manifest.json').read_bytes() != manifest_bytes:
                    raise b.AppError('The published backup manifest failed its byte check. Completion was not recorded.')
                self._manifest(set_id)
                with self._state_lock:
                    prior = dict(self._settings)
                    self._settings.update(last_success=self.clock(), last_error='', last_set_path=str(final),
                                          last_success_destination=destination_text)
                    try:
                        self._persist()
                    except Exception:
                        self._settings = prior
                        raise
                    self._retry_delay = 0
                    self._retry_not_before = 0
                return {'ok': True, 'status': 'complete', 'set_id': set_id, 'workspaces': len(records), 'path': str(final)}
            except Exception as error:
                return self._failure(error, published)
        finally:
            with self._state_lock:
                self._running = False
            self._run_lock.release()

    def _failure(self, error, published=None):
        message = str(error) if isinstance(error, b.AppError) else 'Local backup could not be completed. Check destination availability, permissions and free space. Earlier completed backups are unchanged.'
        if published:
            message += ' A set was published at ' + published + ', but completion status could not be saved or verified. Refresh the saved sets; last success was not advanced.'
        else:
            message += ' Any incomplete output is retained.'
        with self._state_lock:
            # Retry no more frequently than the chosen normal interval, doubling
            # to a seven-day cap. A persistent bad source cannot fill the drive
            # with a partial copy every minute. Explicit run-now remains available.
            interval = self._settings['interval_minutes'] * 60
            self._retry_delay = min(MAX_RETRY_SECONDS, max(interval, self._retry_delay * 2))
            self._retry_not_before = self.clock() + self._retry_delay
            self._settings.update(last_failure=self.clock(), last_error=message)
            try:
                self._persist()
            except Exception:
                message += ' Failure status could not be saved to the data drive; it remains visible in this session. Automatic retries continue with backoff.'
                self._settings['last_error'] = message
        return {'ok': False, 'status': 'failed', 'error': message}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='local-backup', daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as error:
                # Persistence errors, including SQLite disk/lock failures, must
                # stay visible and must not silently terminate the scheduler.
                self._failure(error)
            self._wake.wait(30)
            self._wake.clear()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
        # Manual HTTP backups share this same operation guard. Wait for them too
        # before the integrator closes SQLite or begins a copy-only upgrade.
        with self._run_lock:
            pass

    def _manifest(self, set_id):
        if not isinstance(set_id, str) or not SET_NAME.fullmatch(set_id):
            raise b.AppError('Choose a valid automatic backup set.')
        with self._state_lock:
            destination = self._settings['destination']
        folder = _plain_directory(self._destination(destination) / set_id)
        path = folder / 'manifest.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MANIFEST_LIMIT:
            raise b.AppError('Backup set manifest is missing or invalid.')
        try:
            manifest = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or set(manifest) != {'version', 'app', 'set_id', 'created_at', 'history_included', 'build', 'workspaces'} or manifest['version'] != 1 or manifest['app'] != 'kosh-auto-backup' or manifest['set_id'] != set_id or manifest['history_included'] is not True or not isinstance(manifest['build'], str) or len(manifest['build']) > 200:
                raise ValueError
            if type(manifest['created_at']) not in (int, float) or not 0 <= manifest['created_at'] < 100_000_000_000:
                raise ValueError
            records = manifest['workspaces']
            if not isinstance(records, list) or not records or len(records) > 10000:
                raise ValueError
            seen = set()
            for entry in records:
                if not isinstance(entry, dict) or set(entry) != {'workspace_id', 'title', 'file', 'bytes', 'sha256', 'counts'}:
                    raise ValueError
                if not isinstance(entry['file'], str) or not ZIP_NAME.fullmatch(entry['file']) or entry['file'] != entry['workspace_id'] + '.zip' or entry['file'] in seen:
                    raise ValueError
                if not isinstance(entry['title'], str) or len(entry['title']) > 400 or type(entry['bytes']) is not int or not 1 <= entry['bytes'] <= FILE_ARCHIVE_LIMIT or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
                    raise ValueError
                if not isinstance(entry['counts'], dict) or set(entry['counts']) != {'documents', 'notes', 'matrix', 'chats', 'revisions'} or any(type(value) is not int or not 0 <= value <= 1_000_000 for value in entry['counts'].values()):
                    raise ValueError
                seen.add(entry['file'])
            return folder, manifest
        except (ValueError, TypeError, KeyError, OSError):
            raise b.AppError('Backup set manifest is malformed. No restore was performed.') from None

    def list_sets(self):
        with self._state_lock:
            destination = self._settings['destination']
        if not destination:
            return {'sets': [], 'issues': []}
        folder = self._destination(destination)
        sets, issues = [], []
        candidates = sorted((item.name for item in folder.iterdir() if SET_NAME.fullmatch(item.name)))
        for set_id in candidates:
            try:
                _, manifest = self._manifest(set_id)
                sets.append(manifest)
            except (b.AppError, OSError):
                issues.append({'set_id': set_id, 'error': 'Manifest could not be read or validated.'})
        sets.sort(key=lambda record: record['created_at'], reverse=True)
        return {'sets': sets, 'issues': issues}

    def _archive(self, set_id, workspace_id):
        folder, manifest = self._manifest(set_id)
        entry = next((item for item in manifest['workspaces'] if item['workspace_id'] == workspace_id), None)
        if entry is None:
            raise b.AppError('Workspace was not found in this backup set.', 404)
        path = folder / entry['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['bytes']:
            raise b.AppError('Backup ZIP is missing or changed. No restore was performed.')
        size, digest = hash_file(path)
        if size != entry['bytes'] or digest != entry['sha256']:
            raise b.AppError('Backup ZIP failed its SHA-256 byte check. No restore was performed.')
        return path, entry

    def preview_restore(self, body):
        if not isinstance(body, dict) or set(body) != {'set_id', 'workspace_id'}:
            raise b.AppError('Select one backup set and workspace for preview.')
        path, entry = self._archive(body['set_id'], body['workspace_id'])
        result = self.store.restore_backup_file(path, preview_only=True,
                                               expected_sha256=entry['sha256'], expected_size=entry['bytes'])
        with self._state_lock:
            self._previews = {key: value for key, value in self._previews.items() if value['expires'] > self.clock()}
            if len(self._previews) >= 32:
                raise b.AppError('Close earlier restore previews or wait for them to expire.', 409)
            preview_id = new_id()
            self._previews[preview_id] = {**body, 'sha256': entry['sha256'], 'expires': self.clock() + PREVIEW_LIFETIME,
                                          'destination': self._settings['destination']}
        return {**result, 'preview_id': preview_id, 'set_id': body['set_id'], 'sha256': entry['sha256'],
                'notice': 'Preview validated the saved ZIP without changing any workspace. Restore creates a separate workspace; existing work is retained.'}

    def restore(self, body):
        if not isinstance(body, dict) or set(body) != {'preview_id', 'approve'} or body['approve'] is not True or not isinstance(body['preview_id'], str):
            raise b.AppError('Approve this exact restore preview first.')
        with self._state_lock:
            preview = self._previews.pop(body['preview_id'], None)
            if not preview or preview['expires'] <= self.clock() or preview['destination'] != self._settings['destination']:
                raise b.AppError('Restore preview expired or changed. Preview again before restoring.', 409)
        path, entry = self._archive(preview['set_id'], preview['workspace_id'])
        if entry['sha256'] != preview['sha256']:
            raise b.AppError('Backup changed after preview. Preview it again before restoring.', 409)
        return self.store.restore_backup_file(path, expected_sha256=entry['sha256'], expected_size=entry['bytes'])
