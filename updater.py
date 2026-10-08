"""User-triggered updates from Kosh's single public repository; stdlib only.

Metadata never becomes a command, path, HTML or Python program. Checks, downloads
and unsigned execution are three separate approvals. Research data is not read
or written by this module. The detached worker performs the stopped copy.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

import upgrade

CURRENT_VERSION = '0.5.0'
REPOSITORY = 'needanotheremailid/kosh-desktop'
RELEASES_URL = 'https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=10'
RELEASE_BASE = 'https://github.com/' + REPOSITORY + '/releases/'
MAX_INSTALLER = 1024 * 1024 * 1024
MAX_METADATA = 1024 * 1024
MAX_CHECKSUMS = 64 * 1024
JOB_ID = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
TERMINAL = {'installed_verified', 'activation_failed', 'rolled_back', 'rollback_failed', 'failed', 'interrupted', 'download_failed'}


class UpdateError(ValueError):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})\.(?:0|[1-9][0-9]{0,2})\.(?:0|[1-9][0-9]{0,2})', value):
        raise UpdateError('Release version is invalid. Choose a published numeric Kosh release.')
    return tuple(map(int, value.split('.')))


@dataclass(frozen=True)
class Candidate:
    version: str
    prerelease: bool
    size: int
    digest: str | None

    @property
    def filename(self): return 'Kosh-' + self.version + '-Setup.exe'

    @property
    def installer_url(self): return RELEASE_BASE + 'download/v' + self.version + '/' + self.filename

    @property
    def checksum_url(self): return RELEASE_BASE + 'download/v' + self.version + '/SHA256SUMS.txt'

    def public(self):
        return {'version': self.version, 'prerelease': self.prerelease, 'size': self.size,
                'release_url': RELEASE_BASE + 'tag/v' + self.version}


def parse_release(value):
    if not isinstance(value, dict) or value.get('draft') is not False or type(value.get('prerelease')) is not bool:
        raise UpdateError('Published release metadata is invalid or still a draft.')
    tag = value.get('tag_name')
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise UpdateError('Release tag is invalid.')
    version = tag[1:]; version_tuple(version)
    if value.get('html_url') != RELEASE_BASE + 'tag/v' + version:
        raise UpdateError('Release belongs to an unexpected repository or URL.')
    assets = value.get('assets')
    if not isinstance(assets, list) or len(assets) > 30 or any(not isinstance(a, dict) for a in assets):
        raise UpdateError('Release asset list is invalid.')
    selected = {}
    for name in ('Kosh-' + version + '-Setup.exe', 'SHA256SUMS.txt'):
        matches = [asset for asset in assets if asset.get('name') == name]
        if len(matches) != 1:
            raise UpdateError('Release needs one installer and one checksum file with their exact names.')
        asset = matches[0]
        if asset.get('state') != 'uploaded' or asset.get('browser_download_url') != RELEASE_BASE + 'download/v' + version + '/' + name:
            raise UpdateError('Release asset location/state is not trusted.')
        limit = MAX_CHECKSUMS if name == 'SHA256SUMS.txt' else MAX_INSTALLER
        if type(asset.get('size')) is not int or not 0 < asset['size'] <= limit:
            raise UpdateError('Release asset exceeds the supported size limit.')
        selected[name] = asset
    asset = selected['Kosh-' + version + '-Setup.exe']
    digest = asset.get('digest')
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', digest)):
        raise UpdateError('Published installer digest is invalid.')
    return Candidate(version, value['prerelease'], asset['size'], digest[7:] if digest else None)


def parse_checksum(content, filename):
    if not isinstance(content, bytes) or len(content) > MAX_CHECKSUMS:
        raise UpdateError('Checksum file is oversized or invalid.')
    try: lines = content.decode('utf-8-sig').splitlines()
    except UnicodeError: raise UpdateError('Checksum file is not UTF-8 text.') from None
    matches = []
    for line in lines:
        if not line.strip(): continue
        row = re.fullmatch(r'([a-f0-9]{64}) [ *]([A-Za-z0-9][A-Za-z0-9._-]{0,200})', line)
        if not row:
            raise UpdateError('Checksum file contains an invalid filename or checksum.')
        if row.group(2) == filename: matches.append(row.group(1))
    if len(matches) != 1:
        raise UpdateError('Checksum file must contain exactly one entry for this installer.')
    return matches[0]


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        original = urlsplit(request.full_url)
        target = urlsplit(newurl)
        trusted_origin = original.hostname in {'github.com', 'release-assets.githubusercontent.com'}
        if (not trusted_origin or target.scheme != 'https' or target.hostname != 'release-assets.githubusercontent.com'
                or target.port not in (None, 443) or target.username or target.password
                or not re.fullmatch(r'/github-production-release-asset/[0-9]+/[a-fA-F0-9-]+', target.path)):
            raise UpdateError('Release download redirected to an unapproved source.')
        return super().redirect_request(request, fp, code, message, headers, newurl)


class GithubTransport:
    def __init__(self): self.opener = build_opener(ProxyHandler({}), ReleaseRedirects())

    def open(self, url):
        # All caller URLs are constructed by this module; no route accepts URLs.
        if url != RELEASES_URL and not re.fullmatch(re.escape(RELEASE_BASE) + r'download/v[0-9.]+/(?:Kosh-[0-9.]+-Setup\.exe|SHA256SUMS\.txt)', url):
            raise UpdateError('Unapproved release source.')
        return self.opener.open(Request(url, headers={'Accept': 'application/vnd.github+json' if url == RELEASES_URL else 'application/octet-stream', 'User-Agent': 'Kosh-explicit-updater'}), timeout=30)


def cache_root():
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute(): raise UpdateError('Per-user update cache is unavailable.')
    return Path(local) / 'Kosh' / 'updates'


def read_json(path, limit=MAX_CHECKSUMS):
    upgrade._check_chain(path)
    if not path.is_file() or path.stat().st_size > limit: raise UpdateError('Update record is missing or oversized.')
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): raise UpdateError('Update record is invalid; retained files need review.') from None


def write_receipt(directory, value):
    """Bounded append-only phase receipts plus an atomic current-state pointer."""
    upgrade._check_chain(directory)
    receipts = directory / 'receipts'; receipts.mkdir(exist_ok=True)
    rows = list(receipts.glob('*.json'))
    if len(rows) >= 80: raise UpdateError('Update receipt limit reached; retained files need review.')
    record = {'format': 1, 'app': 'Kosh', 'repository': REPOSITORY,
              'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), **value}
    encoded = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode()
    if len(encoded) > MAX_CHECKSUMS: raise UpdateError('Update receipt is oversized.')
    with (receipts / (str(len(rows) + 1).zfill(3) + '-' + uuid.uuid4().hex + '.json')).open('xb') as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    temporary = directory / ('receipt-' + uuid.uuid4().hex + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    upgrade._check_chain(directory / 'receipt.json')
    os.replace(temporary, directory / 'receipt.json')
    return record


def activation_ready(root, build=None, cache_dir=None):
    """A verification service accepts writes only after its durable worker proof.

    The caller supplies its own runtime build, never a browser-provided identity.
    Cache override is solely a trusted embedding/test hook, not an HTTP input.
    """
    root = Path(root).resolve()
    try:
        marker = read_json(root / 'UPDATE_READY.json')
        required = {'format', 'app', 'repository', 'job_id', 'version', 'build', 'new_install', 'phase'}
        if (not isinstance(marker, dict) or set(marker) != required or marker['format'] != 1
                or marker['app'] != 'Kosh' or marker['repository'] != REPOSITORY
                or marker['phase'] != 'installed_verified' or marker['new_install'] != str(root)
                or not isinstance(marker['job_id'], str) or not JOB_ID.fullmatch(marker['job_id'])
                or not isinstance(marker['build'], str) or not SHA.fullmatch(marker['build'])):
            return False
        version_tuple(marker['version'])
        if marker['version'] != CURRENT_VERSION: return False
        pending_path = root / 'UPDATE_PENDING.json'
        if pending_path.exists() or pending_path.is_symlink():
            pending = read_json(pending_path)
            if pending != {'job_id': marker['job_id'], 'new_install': str(root)}: return False
        installed = upgrade._json(root / 'INSTALL_RECEIPT.json')
        manifest = upgrade._json(root / 'package-manifest.json')
        if installed.get('runtime_checked') is not True or installed.get('build') != marker['build'] or manifest.get('build') != marker['build']:
            return False
        if build is not None and marker['build'] != build: return False
        directory = (Path(cache_dir) if cache_dir is not None else cache_root()) / marker['job_id']
        job = read_json(directory / 'job.json')
        if (job.get('new_install') != str(root) or job.get('job_id') != marker['job_id']
                or job.get('version') != marker['version'] or job.get('repository') != REPOSITORY
                or job.get('approve_install') is not True or job.get('accept_unsigned') is not True):
            return False
        upgrade._check_chain(directory / 'receipts')
        receipts = list((directory / 'receipts').glob('*.json'))
        if len(receipts) > 80: return False
        for path in receipts:
            receipt = read_json(path)
            if (receipt.get('phase') == 'installed_verified' and receipt.get('job_id') == marker['job_id']
                    and receipt.get('repository') == REPOSITORY and receipt.get('version') == marker['version']
                    and receipt.get('build') == marker['build']
                    and receipt.get('startup') == {'app': 'pg-research-desktop', 'build': marker['build'], 'ready': True}):
                return True
        return False
    except (OSError, ValueError, TypeError): return False


def verification_required(root, build, explicit=False):
    """Persist the read-only startup gate across reboot or ordinary relaunch.

    Offline upgrades have no pending marker and keep their normal launch path.
    An interrupted in-app candidate stays locked until its own completion proof
    verifies. An unreadable/malformed marker fails closed without breaking startup.
    """
    if explicit: return True
    root = Path(root)
    pending_path = root / 'UPDATE_PENDING.json'
    try:
        upgrade._check_chain(pending_path)
        if not pending_path.exists(): return False
        pending = read_json(pending_path)
        if (not isinstance(pending, dict) or set(pending) != {'job_id', 'new_install'}
                or not isinstance(pending['job_id'], str) or not JOB_ID.fullmatch(pending['job_id'])
                or pending['new_install'] != str(root.resolve())):
            return True
        return not activation_ready(root, build)
    except (OSError, ValueError, TypeError): return True


@contextmanager
def cache_guard(cache):
    """Short cross-process file lock serializes lease claim/release, not copying."""
    upgrade._check_chain(cache); cache.mkdir(parents=True, exist_ok=True)
    path = cache / 'install.guard'; upgrade._check_chain(path)
    with path.open('a+b') as stream:
        if path.stat().st_nlink > 1: raise UpdateError('Update guard is hard-linked; preserved.')
        if path.stat().st_size == 0: stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: raise UpdateError('Another process is preparing update recovery. Retry explicitly.') from None
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def active_install(cache):
    path = Path(cache) / 'install-lease.json'
    if not path.exists(): return None
    lease = read_json(path)
    if (not isinstance(lease, dict) or not isinstance(lease.get('job_id'), str)
            or not JOB_ID.fullmatch(lease['job_id']) or set(lease) != {'job_id', 'old_install', 'prepared_pid'}):
        raise UpdateError('Update lease is invalid. Retained files need review.')
    directory = Path(cache) / lease['job_id']
    receipt = read_json(directory / 'receipt.json')
    return {**lease, 'directory': directory, 'receipt': receipt}


def claim_install(directory, old):
    with cache_guard(directory.parent):
        active = active_install(directory.parent)
        path = directory.parent / 'install-lease.json'
        if active is not None:
            if active['receipt'].get('phase') not in TERMINAL:
                raise UpdateError('An update is already prepared in another Kosh session. Resume or recover that job first.')
            path.unlink()  # Our validated terminal lease, serialized by the guard.
        upgrade._write_json_new(path, {'job_id': directory.name, 'old_install': str(old), 'prepared_pid': os.getpid()})


def release_install(directory):
    with cache_guard(directory.parent):
        active = active_install(directory.parent)
        if active and active['job_id'] == directory.name and active['receipt'].get('phase') in TERMINAL:
            (directory.parent / 'install-lease.json').unlink()


class Updater:
    def __init__(self, root, cache_dir=None, transport=None, current_version=CURRENT_VERSION):
        self.root = Path(root).resolve()
        self.cache = Path(cache_dir) if cache_dir is not None else cache_root()
        if not self.cache.is_absolute(): raise UpdateError('Update cache must be an absolute private directory.')
        upgrade._check_chain(self.cache)
        self.current_version = current_version; version_tuple(current_version)
        self.transport = transport if transport is not None else GithubTransport()
        self.candidate = None; self.job_dir = None; self.phase = 'idle'
        self._lock = threading.Lock()

    def status(self):
        value = {'phase': self.phase, 'current_version': self.current_version, 'repository': REPOSITORY,
                 'signature': 'not_verified', 'candidate': self.candidate.public() if self.candidate else None,
                 'install_supported': os.name == 'nt' and (self.root / 'INSTALL_RECEIPT.json').is_file()}
        previous = self.previous_installation()
        if previous is not None: value['previous_installation'] = previous
        directory = self.job_dir
        if directory is None and self.cache.is_dir():
            # Receipts are outside research data. Only inspect generated job names.
            directories = sorted((p for p in self.cache.iterdir() if JOB_ID.fullmatch(p.name) and p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
            directory = next((p for p in directories[:100] if (p / 'receipt.json').is_file()), None)
            if directory is not None:
                latest = read_json(directory / 'receipt.json')
                value['previous_update'] = {k: latest[k] for k in ('phase', 'version', 'message', 'job_id', 'signature') if k in latest}
        if self.job_dir is not None and (self.job_dir / 'receipt.json').exists():
            receipt = read_json(self.job_dir / 'receipt.json')
            value.update({key: receipt[key] for key in ('phase', 'job_id', 'sha256', 'message', 'version') if key in receipt})
        active = active_install(self.cache)
        if active and active['receipt'].get('phase') not in TERMINAL:
            phase = active['receipt'].get('phase'); marker = active['directory'] / 'worker.json'
            alive = upgrade._pid_alive(read_json(marker).get('pid')) if marker.exists() else upgrade._pid_alive(active['prepared_pid'])
            if not alive and phase != 'close_timeout':
                phase = 'interrupted_needs_recovery'
            value['active_update'] = {'job_id': active['job_id'], 'phase': phase, 'same_installation': active['old_install'] == str(self.root)}
            if active['old_install'] == str(self.root):
                value['phase'] = phase; value['resume_available'] = not alive
        return value

    def _refuse_active_install(self):
        active = active_install(self.cache)
        if active is not None and active['receipt'].get('phase') not in TERMINAL:
            raise UpdateError('An earlier update is still prepared. Resume or recover it before starting another update.')

    def previous_installation(self):
        receipt_path = self.root / 'UPGRADE_RECEIPT.json'
        if not receipt_path.exists(): return None
        try:
            receipt = read_json(receipt_path, limit=8 * 1024 * 1024)
            if (not isinstance(receipt, dict) or receipt.get('app') != 'Kosh'
                    or receipt.get('action') != 'offline-copy-only-upgrade'
                    or Path(receipt.get('new_install', '')).resolve() != self.root):
                raise UpdateError('Previous-installation receipt does not belong to this copy.')
            previous = upgrade._root(receipt.get('old_install', ''))
            if previous == self.root or previous.parent != self.root.parent:
                raise UpdateError('Previous-installation receipt points outside this installation family.')
            return {'install_path': str(previous), 'data_path': str(previous / 'data'),
                    'current_data_path': str(self.root / 'data'), 'receipt_path': str(receipt_path),
                    'data_retained': (previous / 'data').is_dir(), 'build': receipt.get('old_build'),
                    'warning': 'Opening the previous version shows its older saved data. Newer changes in this version are not copied back. Opening both versions creates separate histories; review both data paths before choosing.'}
        except (OSError, ValueError, TypeError):
            return {'install_path': 'Unverified', 'data_path': 'Unverified', 'current_data_path': str(self.root / 'data'),
                    'receipt_path': str(receipt_path), 'data_retained': None,
                    'warning': 'Previous-installation receipt could not verify. Retained files require inspection; no automatic rollback was performed.'}

    def check(self, consent=False):
        if consent is not True: raise UpdateError('Choose Check for updates to contact the public Kosh release source.')
        if not self._lock.acquire(blocking=False): raise UpdateError('An update action is already running.')
        try:
            self._refuse_active_install()
            if self.job_dir and self.status()['phase'] in {'awaiting_close', 'installing', 'copying', 'starting', 'retargeting'}:
                raise UpdateError('Finish the prepared update before checking another release.')
            self.phase = 'checking'; self.candidate = None; self.job_dir = None
            with self.transport.open(RELEASES_URL) as response: raw = response.read(MAX_METADATA + 1)
            if len(raw) > MAX_METADATA: raise UpdateError('Release metadata is oversized.')
            values = json.loads(raw)
            if (not isinstance(values, list) or len(values) > 10
                    or any(not isinstance(v, dict) or type(v.get('draft')) is not bool for v in values)):
                raise UpdateError('Release metadata list is invalid.')
            eligible = []
            for value in values:
                tag = value.get('tag_name')
                if value['draft'] or not isinstance(tag, str) or not tag.startswith('v'): continue
                try: version = version_tuple(tag[1:])
                except UpdateError: continue
                if version > version_tuple(self.current_version): eligible.append((version, value))
            self.candidate = parse_release(max(eligible, key=lambda row: row[0])[1]) if eligible else None
            self.phase = 'available' if self.candidate else 'up_to_date'
            return self.status()
        except (OSError, ValueError) as error:
            self.phase = 'check_failed'
            if isinstance(error, UpdateError): raise
            raise UpdateError('Release check failed. No installer was downloaded; retry explicitly.') from None
        finally: self._lock.release()

    def download(self, consent=False):
        if consent is not True: raise UpdateError('Choose Download verified installer before fetching update files.')
        if not self._lock.acquire(blocking=False): raise UpdateError('An update action is already running.')
        try:
            self._refuse_active_install()
            if self.phase != 'available' or self.candidate is None: raise UpdateError('Check for an available release before downloading.')
            candidate = self.candidate
            upgrade._check_chain(self.cache); self.cache.mkdir(parents=True, exist_ok=True)
            directory = self.cache / uuid.uuid4().hex; directory.mkdir()
            self.job_dir = directory; self.phase = 'downloading'
            write_receipt(directory, {'phase': 'downloading', 'job_id': directory.name, 'version': candidate.version, 'signature': 'not_verified'})
            with self.transport.open(candidate.checksum_url) as response: sums = response.read(MAX_CHECKSUMS + 1)
            expected = parse_checksum(sums, candidate.filename)
            if candidate.digest is not None and expected != candidate.digest: raise UpdateError('GitHub asset digest and published checksum disagree.')
            (directory / 'SHA256SUMS.txt').write_bytes(sums)
            digest = hashlib.sha256(); count = 0; first = True
            with self.transport.open(candidate.installer_url) as response, (directory / (candidate.filename + '.part')).open('xb') as output:
                while block := response.read(1024 * 1024):
                    if first and not block.startswith(b'MZ'): raise UpdateError('Downloaded file is not a Windows executable.')
                    first = False; count += len(block)
                    if count > candidate.size: raise UpdateError('Installer download exceeds its published size.')
                    output.write(block); digest.update(block)
                output.flush(); os.fsync(output.fileno())
            if count != candidate.size or digest.hexdigest() != expected: raise UpdateError('Installer size/SHA-256 verification failed. It will not run.')
            os.rename(directory / (candidate.filename + '.part'), directory / candidate.filename)
            self.phase = 'downloaded'
            write_receipt(directory, {'phase': 'downloaded', 'job_id': directory.name, 'version': candidate.version,
                                     'size': count, 'sha256': expected, 'signature': 'not_verified'})
            return self.status()
        except (OSError, ValueError) as error:
            if self.job_dir is not None and self.phase == 'downloading':
                self.phase = 'download_failed'
                write_receipt(self.job_dir, {'phase': self.phase, 'job_id': self.job_dir.name, 'message': 'Download failed; retained partial files were not executed.'})
            if isinstance(error, UpdateError): raise
            raise UpdateError('Download interrupted. Partial files were retained and will not run.') from None
        finally: self._lock.release()

    def prepare_install(self, approve=False, accept_unsigned=False):
        if approve is not True or accept_unsigned is not True:
            raise UpdateError('Save and close Kosh, and explicitly accept unverified publisher identity before installing.')
        if self.phase != 'downloaded' or self.job_dir is None or self.candidate is None:
            raise UpdateError('Download and verify an available installer first.')
        # Complete current install verification before making an executable job.
        old = upgrade._root(self.root); old_build = upgrade._verify_install(old)
        receipt = read_json(self.job_dir / 'receipt.json')
        candidate = self.candidate
        if receipt.get('sha256') != upgrade._hash(self.job_dir / candidate.filename): raise UpdateError('Downloaded installer changed; it will not run.')
        new = old.parent / ('Kosh-' + candidate.version + '-' + self.job_dir.name[:8])
        upgrade._check_chain(new)
        if new.exists(): raise UpdateError('Candidate installation already exists and was preserved.')
        request = {'format': 1, 'app': 'Kosh', 'repository': REPOSITORY, 'job_id': self.job_dir.name,
                   'version': candidate.version, 'current_version': self.current_version,
                   'size': candidate.size, 'sha256': receipt['sha256'], 'old_build': old_build,
                   'old_install': str(old), 'new_install': str(new), 'approve_install': True, 'accept_unsigned': True}
        if (self.job_dir / 'job.json').exists(): raise UpdateError('This job is already prepared; use explicit resume/recovery.')
        claim_install(self.job_dir, old)
        try:
            upgrade._write_json_new(self.job_dir / 'job.json', request)
            write_receipt(self.job_dir, {'phase': 'awaiting_close', 'job_id': self.job_dir.name,
                                        'version': candidate.version, 'message': 'Save succeeded. Close the old Kosh window; copy waits for the service and its browser profile to stop.', 'signature': 'not_verified'})
        except OSError:
            write_receipt(self.job_dir, {'phase':'failed','job_id':self.job_dir.name,'message':'Job preparation did not finish. Download and all installations were retained.'})
            release_install(self.job_dir)
            raise UpdateError('Job preparation did not finish. Existing installations and download were retained.') from None
        self.phase = 'awaiting_close'
        return request

    def install(self, approve=False, accept_unsigned=False):
        if not self._lock.acquire(blocking=False): raise UpdateError('An update action is already running.')
        try:
            if approve is not True or accept_unsigned is not True:
                raise UpdateError('Explicit install and unverified-publisher approval are required.')
            if os.name != 'nt': raise UpdateError('Installed copy-only updates require Windows.')
            if not (self.root / 'updater_worker.py').is_file(): raise UpdateError('This installed package lacks its update worker; use the documented offline upgrade.')
            self.prepare_install(approve, accept_unsigned)
            try:
                self._spawn_worker()
            except OSError:
                write_receipt(self.job_dir, {'phase': 'failed', 'job_id': self.job_dir.name, 'message': 'Update worker did not start. Old installation and data were preserved.'})
                release_install(self.job_dir)
                raise UpdateError('Update worker could not start. Kosh has not been stopped.') from None
            return self.status()
        finally: self._lock.release()

    def _spawn_worker(self):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([str(self.root / 'runtime/python.exe'), '-E', '-s', str(self.root / 'updater_worker.py'), '--job-dir', str(self.job_dir)],
                         cwd=self.root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    def resume(self, approve=False, accept_unsigned=False):
        if approve is not True or accept_unsigned is not True: raise UpdateError('Explicit resume and unsigned-publisher approval are required.')
        if not self._lock.acquire(blocking=False): raise UpdateError('An update action is already running.')
        try:
            from updater_worker import validate_job
            with cache_guard(self.cache):
                active = active_install(self.cache)
                if not active or active['old_install'] != str(self.root) or active['receipt'].get('phase') in TERMINAL:
                    raise UpdateError('No recoverable update belongs to this installation.')
                directory = active['directory']; marker = directory / 'worker.json'
                if marker.exists() and upgrade._pid_alive(read_json(marker).get('pid')):
                    raise UpdateError('That update worker is still running; close the old window and wait.')
                phase = active['receipt'].get('phase')
                if phase not in {'close_timeout', 'awaiting_close', 'installing', 'copying', 'starting', 'retargeting'}:
                    raise UpdateError('Retained job requires inspection before recovery.')
                request, _, new, _ = validate_job(directory, identity_only=phase not in {'close_timeout', 'awaiting_close'})
                self.job_dir = directory
                if phase in {'close_timeout', 'awaiting_close'}:
                    if new.exists(): raise UpdateError('Candidate already exists; retained files require inspection.')
                    if marker.exists(): marker.unlink()
                    write_receipt(directory, {'phase':'awaiting_close','job_id':directory.name,'version':request['version'],'message':'Retained installer rechecked; close this Kosh window to resume without downloading again.'})
                temporary=self.cache/('install-lease-'+uuid.uuid4().hex+'.tmp')
                upgrade._write_json_new(temporary,{'job_id':directory.name,'old_install':str(self.root),'prepared_pid':os.getpid()})
                os.replace(temporary,self.cache/'install-lease.json')
            self._spawn_worker()
            return self.status()
        finally: self._lock.release()
