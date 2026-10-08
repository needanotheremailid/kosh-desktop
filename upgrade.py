"""Explicit offline, copy-only Kosh upgrade between two selected installations.

Dry-run is default. --apply copies into a verified fresh install whose data
directory is absent. The old install/data never changes. Failed staging is
retained; this utility never starts/stops services, migrates schemas or deletes
an existing data tree. Optional shortcut retargeting has its own explicit flag.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import uuid


class UpgradeError(ValueError):
    def __init__(self, message, data_published=False):
        super().__init__(message)
        self.data_published = data_published


SUPPORTED_DB_USER_VERSION = 1
REQUIRED_TABLES = {'workspaces', 'documents', 'pages', 'notes', 'matrix', 'chats', 'revisions', 'settings'}
SHA = re.compile(r'^[a-f0-9]{64}$')


def _check_chain(path):
    for candidate in reversed((path, *path.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise UpgradeError('Selected paths cannot contain symlinks, junctions or other reparse points.')


def _root(value):
    path = Path(value)
    if not path.is_absolute():
        raise UpgradeError('Select explicit absolute installation paths.')
    _check_chain(path)
    path = path.resolve()
    if path == Path(path.anchor) or not path.is_dir():
        raise UpgradeError('Select existing installation directories, not drive roots.')
    return path


def _json(path):
    _check_chain(path)
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise UpgradeError('An installation or readiness record is oversized.')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise UpgradeError('A required installation or readiness record is unavailable or invalid.') from None


def _hash(path):
    _check_chain(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(root, name):
    path = PurePosixPath(name) if isinstance(name, str) else None
    if path is None or not name or path.is_absolute() or path.as_posix() != name or '\\' in name or any(part in {'.', '..', ''} or ':' in part for part in path.parts):
        raise UpgradeError('Installation manifest contains an unsafe relative path.')
    result = root.joinpath(*path.parts)
    _check_chain(result)
    if not result.resolve().is_relative_to(root):
        raise UpgradeError('Installation manifest escaped its selected root.')
    return result


def _verify_install(root):
    receipt = _json(root / 'INSTALL_RECEIPT.json')
    manifest = _json(root / 'package-manifest.json')
    if not isinstance(receipt, dict) or not isinstance(manifest, dict) or receipt.get('app') != 'Kosh' or manifest.get('app') != 'pg-research-desktop' or manifest.get('format') != 1:
        raise UpgradeError('Selected folder is not a recognised installed Kosh package.')
    build = receipt.get('build')
    files = manifest.get('files')
    if not isinstance(build, str) or not SHA.fullmatch(build) or manifest.get('build') != build or receipt.get('runtime_checked') is not True:
        raise UpgradeError('Installation receipt/build identity is not verified.')
    if not isinstance(files, list) or not files or len(files) > 20000 or receipt.get('files_verified') != len(files):
        raise UpgradeError('Installation file coverage does not match its receipt.')
    total, seen = 0, set()
    for row in files:
        if not isinstance(row, dict):
            raise UpgradeError('Installation manifest file record is invalid.')
        name, size, digest = row.get('path'), row.get('size'), row.get('sha256')
        path = _manifest_path(root, name)
        if name.casefold() in seen or not isinstance(size, int) or isinstance(size, bool) or size < 0 or not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise UpgradeError('Installation manifest file identity is invalid or duplicated.')
        seen.add(name.casefold())
        if not path.is_file() or path.stat().st_size != size or _hash(path) != digest:
            raise UpgradeError('Installed application file failed size/SHA-256 verification.')
        total += size
    if receipt.get('payload_bytes') != total or not {'backend.py', 'server.py', 'runtime/python.exe', 'bin/researchdesktop.exe'}.issubset(seen):
        raise UpgradeError('Installed package is incomplete or differs from its receipt.')
    return build


def _pid_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise UpgradeError('Readiness PID is invalid; stopped state cannot be verified.')
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:  # No process with this PID.
                return False
            raise UpgradeError('Cannot verify the recorded process; close Kosh and retry.')
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise UpgradeError('Cannot verify the recorded process state.')
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        raise UpgradeError('Cannot verify the recorded process state.') from None


def _process_identity(pid):
    """Read a process birth identity so a recycled Windows PID is not its owner."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise UpgradeError('Worker process identity is invalid.')
    if os.name == 'nt':
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle: raise UpgradeError('Cannot verify the worker process birth identity.')
        try:
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                raise UpgradeError('Cannot verify the worker process birth identity.')
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally: kernel.CloseHandle(handle)
    try:
        # Source-test portability: Linux start ticks, with the parenthesized
        # process name removed. No command line or account information is read.
        raw = (Path('/proc') / str(pid) / 'stat').read_text(encoding='utf-8')
        return str(int(raw.rsplit(')', 1)[1].split()[19]))
    except (OSError, ValueError, IndexError):
        raise UpgradeError('Worker birth identity is unavailable on this platform.') from None


PROCESS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$taskRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json
$taskService = $false
$taskBrowser = $false
$taskUnknown = $false
$taskProcesses = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='msedge.exe'"
foreach ($taskProcess in $taskProcesses) {
    if (-not $taskProcess.CommandLine) { $taskUnknown = $true; continue }
    $taskLine = $taskProcess.CommandLine.ToLowerInvariant().Replace('/', '\')
    foreach ($taskData in $taskRequest.data_paths) {
        $taskMatch = $taskData.ToLowerInvariant().Replace('/', '\')
        if ($taskProcess.Name -eq 'msedge.exe' -and $taskLine.Contains($taskMatch + '\edge-profile')) { $taskBrowser = $true }
        if ($taskProcess.Name -ne 'msedge.exe' -and $taskLine.Contains('server.py') -and $taskLine.Contains($taskMatch)) { $taskService = $true }
    }
}
@{service=$taskService; browser=$taskBrowser; unknown=$taskUnknown} | ConvertTo-Json -Compress
'''


def _powershell(script, request):
    if os.name != 'nt':
        raise UpgradeError('This installed-app helper requires Windows process/shortcut inspection.')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                input=json.dumps(request), capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            raise UpgradeError('Windows inspection/action was unavailable; no private command output was logged.')
        return json.loads(result.stdout.lstrip('\ufeff'))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise UpgradeError('Windows inspection/action was unavailable.') from None


def _running_processes(roots):
    value = _powershell(PROCESS_SCRIPT, {'data_paths': [str(root / 'data') for root in roots]})
    if not isinstance(value, dict) or set(value) != {'service', 'browser', 'unknown'} or any(type(item) is not bool for item in value.values()):
        raise UpgradeError('Cannot verify all relevant process states; close Kosh/Edge and retry.')
    if value['unknown']:
        _exclusive_data_probe(roots)
    return value


def _exclusive_data_probe(roots):
    """Unreadable unrelated processes are not evidence that these files are in use."""
    if os.name != 'nt':
        raise UpgradeError('Exclusive Windows file inspection is unavailable.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    invalid = ctypes.c_void_p(-1).value
    for root in roots:
        for relative in ('research.sqlite3', 'research.sqlite3-wal', 'research.sqlite3-shm', 'edge-profile/lockfile'):
            path = root / 'data' / relative
            if not path.exists():
                continue
            _check_chain(path)
            handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
            if handle == invalid:
                raise UpgradeError('Selected Kosh data is in use or cannot be exclusively read. Quit its app and browser before upgrading.')
            kernel.CloseHandle(handle)


def _stopped(roots):
    ports = set()
    for root in roots:
        data = root / 'data'
        for filename in ('agent-session.json', 'server.json'):
            path = data / filename
            if path.exists():
                value = _json(path)
                if not isinstance(value, dict) or _pid_alive(value.get('pid')):
                    raise UpgradeError('A recorded Kosh process is active. Quit the app before upgrading.')
                if 'port' in value:
                    ports.add(value['port'])
        port_record = data / 'listen-port.json'
        if port_record.exists():
            value = _json(port_record)
            if not isinstance(value, dict):
                raise UpgradeError('Saved port record is invalid.')
            ports.add(value.get('port'))
    for port in ports:
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise UpgradeError('Saved loopback port is invalid.')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise UpgradeError('A saved loopback port is occupied. Close the old service before upgrading.') from None
    processes = _running_processes(roots)
    if processes.get('service') or processes.get('browser'):
        raise UpgradeError('Kosh or its selected Edge profile is active. Quit both before upgrading.')


def _inventory(root):
    _check_chain(root)
    if not root.is_dir():
        raise UpgradeError('The old installation has no data directory to copy.')
    files = []
    directories = []
    for current, folder_names, filenames in os.walk(root, followlinks=False):
        current = Path(current)
        _check_chain(current)
        for folder in sorted(folder_names):
            path = current / folder
            _check_chain(path)
            directories.append(path.relative_to(root).as_posix())
        for filename in sorted(filenames):
            path = current / filename
            _check_chain(path)
            info = path.stat()
            if not path.is_file() or info.st_nlink > 1:
                raise UpgradeError('Data contains a nonregular or hard-linked file; inspect it before upgrading.')
            files.append({'path': path.relative_to(root).as_posix(), 'size': info.st_size, 'sha256': _hash(path)})
    return {'files': sorted(files, key=lambda row: row['path']), 'directories': sorted(directories)}


def _database(path, immutable=False):
    uri = path.as_uri() + '?mode=ro' + ('&immutable=1' if immutable else '')
    return sqlite3.connect(uri, uri=True)


def _database_summary(database):
    integrity = [row[0] for row in database.execute('PRAGMA integrity_check')]
    if integrity != ['ok']:
        raise UpgradeError('SQLite integrity check failed; no new data was published.')
    version = database.execute('PRAGMA user_version').fetchone()[0]
    if version > SUPPORTED_DB_USER_VERSION:
        raise UpgradeError('Database schema version is newer than this upgrade helper supports.')
    schema = database.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    names = {row[0] for row in schema}
    if not REQUIRED_TABLES.issubset(names):
        raise UpgradeError('Database lacks the expected Kosh tables.')
    counts, hashes = {}, {}
    for name, sql in schema:
        quoted = '"' + name.replace('"', '""') + '"'
        columns = [row[1] for row in database.execute('PRAGMA table_info(' + quoted + ')')]
        order = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
        digest = hashlib.sha256((sql or '').encode('utf-8'))
        count = 0
        for row in database.execute('SELECT * FROM ' + quoted + ' ORDER BY ' + order):
            values = [{'bytes': base64.b64encode(value).decode('ascii')} if isinstance(value, bytes) else value for value in row]
            digest.update(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            digest.update(b'\n')
            count += 1
        counts[name], hashes[name] = count, digest.hexdigest()
    return {'integrity': 'ok', 'user_version': version, 'counts': counts, 'table_hashes': hashes}


def _copy_file(source, target):
    _check_chain(source)
    _check_chain(target)
    with source.open('rb') as input_stream, target.open('xb') as output:
        shutil.copyfileobj(input_stream, output, 1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    shutil.copystat(source, target, follow_symlinks=False)


def _consolidate_database(stage, copied):
    raw = stage / 'sqlite-originals'
    raw.mkdir()
    for name in ('research.sqlite3', 'research.sqlite3-wal', 'research.sqlite3-shm'):
        source = copied / name
        if source.exists():
            _copy_file(source, raw / name)
    destination = stage / 'research-consolidated.sqlite3'
    try:
        with closing(_database(copied / 'research.sqlite3')) as source:
            original = _database_summary(source)
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
                verified = _database_summary(target)
        if original != verified:
            raise UpgradeError('SQLite backup changed row counts or logical hashes.')
    except sqlite3.Error:
        raise UpgradeError('SQLite snapshot/backup failed; originals remain untouched.') from None
    os.replace(destination, copied / 'research.sqlite3')  # Our own staged copy only.
    # WAL rows are consolidated into the copied database. Raw DB/sidecar bytes
    # remain in this upgrade's sqlite-originals staging recovery directory.
    for name in ('research.sqlite3-wal', 'research.sqlite3-shm'):
        owned_copy = copied / name
        _check_chain(owned_copy)
        if owned_copy.exists():
            owned_copy.unlink()
    return verified


def _publish_directory(source, target):
    _check_chain(source)
    _check_chain(target)
    if target.exists():
        raise UpgradeError('New data destination appeared during the copy and was preserved.')
    try:
        if os.name == 'nt':
            os.rename(source, target)  # Windows rename refuses an existing directory.
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            rename = getattr(libc, 'renameat2', None)
            if rename is None:
                raise UpgradeError('Atomic no-clobber directory publication is unavailable on this platform.')
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
                raise UpgradeError('No-clobber publication failed; staged copy was retained.')
    except OSError:
        raise UpgradeError('No-clobber publication failed; staged copy was retained.') from None


SHORTCUT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$taskRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json
$taskShell = New-Object -ComObject WScript.Shell
function Get-TaskShortcutHash([string]$taskHashPath) {
    $taskHashAlgorithm = [Security.Cryptography.SHA256]::Create()
    $taskHashStream = [IO.File]::OpenRead($taskHashPath)
    try { return [BitConverter]::ToString($taskHashAlgorithm.ComputeHash($taskHashStream)) }
    finally { $taskHashStream.Dispose(); $taskHashAlgorithm.Dispose() }
}
$taskOldTarget = [IO.Path]::GetFullPath((Join-Path $taskRequest.old_install 'bin\ResearchDesktop.exe'))
$taskNewTarget = [IO.Path]::GetFullPath((Join-Path $taskRequest.new_install 'bin\ResearchDesktop.exe'))
$taskLocations = @(
    @{name='Desktop'; path=(Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Kosh.lnk')},
    @{name='StartMenu'; path=(Join-Path ([Environment]::GetFolderPath('Programs')) 'Kosh\Kosh.lnk')}
)
$taskResults = @()
$taskChanged = 0
foreach ($taskLocation in $taskLocations) {
    $taskPath = $taskLocation.path
    if (-not [IO.File]::Exists($taskPath)) { $taskResults += @{name=$taskLocation.name; status='absent'}; continue }
    if (([IO.File]::GetAttributes($taskPath) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Shortcut is a reparse point.' }
    $taskLink = $taskShell.CreateShortcut($taskPath)
    $taskTarget = [IO.Path]::GetFullPath($taskLink.TargetPath)
    if ($taskTarget -eq $taskNewTarget) { $taskResults += @{name=$taskLocation.name; status='already_new'}; continue }
    if ($taskTarget -ne $taskOldTarget) { $taskResults += @{name=$taskLocation.name; status='preserved_unrelated'}; continue }
    $taskHash = Get-TaskShortcutHash $taskPath
    $taskBackup = Join-Path $taskRequest.backup_dir ($taskLocation.name + '.lnk')
    if ([IO.File]::Exists($taskBackup)) { throw 'Shortcut backup already exists.' }
    $taskTemporary = Join-Path $taskRequest.backup_dir ($taskLocation.name + '.new.lnk')
    if ([IO.File]::Exists($taskTemporary)) { throw 'Shortcut staging already exists.' }
    $taskNewLink = $taskShell.CreateShortcut($taskTemporary)
    $taskNewLink.TargetPath = $taskNewTarget
    $taskNewLink.WorkingDirectory = $taskRequest.new_install
    $taskNewLink.Arguments = $taskLink.Arguments
    $taskNewLink.Description = $taskLink.Description
    $taskNewLink.WindowStyle = $taskLink.WindowStyle
    $taskNewLink.IconLocation = (Join-Path $taskRequest.new_install 'assets\App.ico') + ',0'
    $taskNewLink.Save()
    $taskCurrent = $taskShell.CreateShortcut($taskPath)
    if ([IO.Path]::GetFullPath($taskCurrent.TargetPath) -ne $taskOldTarget -or (Get-TaskShortcutHash $taskPath) -ne $taskHash) { throw 'Shortcut changed after preview; preserved.' }
    [IO.File]::Replace($taskTemporary, $taskPath, $taskBackup, $true)
    $taskReadback = $taskShell.CreateShortcut($taskPath)
    if ([IO.Path]::GetFullPath($taskReadback.TargetPath) -ne $taskNewTarget -or [IO.Path]::GetFullPath($taskReadback.WorkingDirectory) -ne [IO.Path]::GetFullPath($taskRequest.new_install)) { throw 'Shortcut readback did not match.' }
    $taskChanged += 1
    $taskResults += @{name=$taskLocation.name; status='retargeted_verified'}
}
@{status='complete'; changed=$taskChanged; locations=$taskResults} | ConvertTo-Json -Depth 5 -Compress
'''


def _retarget_shortcuts(old, new, stage):
    backups = stage / 'shortcuts'
    backups.mkdir()
    value = _powershell(SHORTCUT_SCRIPT, {'old_install': str(old), 'new_install': str(new), 'backup_dir': str(backups)})
    if not isinstance(value, dict) or value.get('status') != 'complete':
        raise UpgradeError('Shortcut retarget readback was unavailable; retained backups require review.')
    return value


def _write_json_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())


def upgrade(old_install, new_install, apply=False, retarget_shortcuts=False):
    old, new = _root(old_install), _root(new_install)
    if old == new or old.is_relative_to(new) or new.is_relative_to(old):
        raise UpgradeError('Old/new installations must be distinct and cannot contain one another.')
    old_build, new_build = _verify_install(old), _verify_install(new)
    destination, receipt_path = new / 'data', new / 'UPGRADE_RECEIPT.json'
    if destination.exists() or destination.is_symlink():
        raise UpgradeError('New install data must be absent. Existing data, including an empty directory, was preserved.')
    if receipt_path.exists() or receipt_path.is_symlink():
        raise UpgradeError('An existing upgrade receipt was preserved; choose a fresh installation.')
    _stopped((old, new))
    inventory = _inventory(old / 'data')
    if 'research.sqlite3' not in {row['path'] for row in inventory['files']}:
        raise UpgradeError('Old installation has no research database to upgrade.')
    total = sum(row['size'] for row in inventory['files'])
    database_path = old / 'data/research.sqlite3'
    needs_staging = any(row['path'] == 'research.sqlite3-wal' and row['size'] > 0 for row in inventory['files'])
    summary = None
    if not needs_staging:
        try:
            with closing(_database(database_path, immutable=True)) as database:
                summary = _database_summary(database)
        except sqlite3.Error:
            raise UpgradeError('Old SQLite database is invalid; no data was copied.') from None
    result = {'applied': False, 'old_build': old_build, 'new_build': new_build, 'files': len(inventory['files']),
              'bytes': total, 'counts': summary['counts'] if summary else None,
              'requires_staged_database_check': needs_staging,
              'shortcuts': {'status': 'requested_after_copy' if retarget_shortcuts else 'not_requested'}}
    if not apply:
        return result
    if shutil.disk_usage(new).free < total + database_path.stat().st_size * 2:
        raise UpgradeError('New installation volume lacks space for the verified copy and SQLite recovery snapshot.')
    stage = new / ('upgrade-staging-' + uuid.uuid4().hex)
    stage.mkdir()
    copied = stage / 'data'
    copied.mkdir()
    published = False
    try:
        for directory in inventory['directories']:
            (copied / directory).mkdir(parents=True, exist_ok=True)
        for row in inventory['files']:
            source = old / 'data' / row['path']
            target = copied / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_file(source, target)
        if _inventory(copied) != inventory or _inventory(old / 'data') != inventory:
            raise UpgradeError('Copied files or source tree changed during the copy; staging was retained.')
        summary = _consolidate_database(stage, copied)
        copied_inventory = _inventory(copied)
        source_files = {row['path']: row for row in inventory['files'] if row['path'] not in {'research.sqlite3', 'research.sqlite3-wal', 'research.sqlite3-shm'}}
        copied_files = {row['path']: row for row in copied_inventory['files'] if row['path'] != 'research.sqlite3'}
        if source_files != copied_files or _inventory(old / 'data') != inventory:
            raise UpgradeError('Non-database file hashes or original data changed; staging was retained.')
        _stopped((old, new))
        if _inventory(old / 'data') != inventory:
            raise UpgradeError('Original data changed before publication; staging was retained.')
        receipt = {'format': 1, 'app': 'Kosh', 'action': 'offline-copy-only-upgrade',
                   'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'old_install': str(old), 'new_install': str(new), 'old_build': old_build, 'new_build': new_build,
                   'old_install_preserved': True, 'database': summary, 'source_files': inventory['files'],
                   'copied_files': copied_inventory['files'], 'edge_profile_included': (copied / 'edge-profile').exists(),
                   'sqlite_raw_snapshot': str(stage / 'sqlite-originals'), 'shortcuts': {'status': 'pending' if retarget_shortcuts else 'not_requested'},
                   'application_launch_verified': False, 'schema_migration_performed': False}
        _write_json_new(stage / 'UPGRADE_RECEIPT.prepublish.json', receipt)
        _publish_directory(copied, destination)
        published = True
        if retarget_shortcuts:
            try:
                receipt['shortcuts'] = _retarget_shortcuts(old, new, stage)
            except UpgradeError:
                receipt['shortcuts'] = {'status': 'failed', 'message': 'Data copy succeeded. Shortcuts may be partially retargeted; inspect retained backups/readback before continuing.'}
        _write_json_new(stage / 'UPGRADE_RECEIPT.json', receipt)
        os.link(stage / 'UPGRADE_RECEIPT.json', receipt_path)  # Atomic new receipt, never clobber.
        result.update(applied=True, counts=summary['counts'], requires_staged_database_check=False, shortcuts=receipt['shortcuts'])
        return result
    except Exception as error:
        try:
            _write_json_new(stage / 'UPGRADE_ERROR.json', {'data_published': published, 'error_type': type(error).__name__, 'old_data_modified_by_upgrade': False})
        except OSError:
            pass
        if isinstance(error, UpgradeError):
            error.data_published = published
            raise
        message = 'Verified new data was published, but the final upgrade receipt/action did not finish. Inspect retained staging before continuing.' if published else 'Upgrade did not finish. Old data and this upgrade staging were retained; inspect the new installation before retrying.'
        raise UpgradeError(message, data_published=published) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-install', type=Path, required=True)
    parser.add_argument('--new-install', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Copy and verify the old data; default only checks the plan.')
    parser.add_argument('--retarget-shortcuts', action='store_true', help='After verified copy, retarget only Kosh links pointing at the exact old launcher; retain backups.')
    args = parser.parse_args(argv)
    try:
        result = upgrade(args.old_install, args.new_install, args.apply, args.retarget_shortcuts)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except UpgradeError as error:
        print(json.dumps({'applied': error.data_published, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
