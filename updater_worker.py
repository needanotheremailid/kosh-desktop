"""Detached, bounded Windows update worker. No network and no data migration.

Execution inputs are only a local generated job, a rehashed installer and the
manifest-verified bundled runtime. Old installation and all its data stay intact.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import upgrade
from updater import (CURRENT_VERSION, REPOSITORY, JOB_ID, SHA, MAX_INSTALLER,
                     TERMINAL, UpdateError, cache_root, cache_guard, active_install, release_install, read_json, version_tuple, write_receipt)


def validate_job(directory, identity_only=False):
    directory = Path(directory)
    if not directory.is_absolute() or not JOB_ID.fullmatch(directory.name): raise UpdateError('Update job directory is invalid.')
    upgrade._check_chain(directory)
    request = read_json(directory / 'job.json')
    expected = {'format', 'app', 'repository', 'job_id', 'version', 'current_version', 'size', 'sha256',
                'old_build', 'old_install', 'new_install', 'approve_install', 'accept_unsigned'}
    if not isinstance(request, dict) or set(request) != expected or request.get('format') != 1 or request.get('app') != 'Kosh' or request.get('repository') != REPOSITORY or request.get('job_id') != directory.name:
        raise UpdateError('Update job identity is invalid.')
    if request.get('approve_install') is not True or request.get('accept_unsigned') is not True:
        raise UpdateError('Update execution approval is missing.')
    if version_tuple(request['version']) <= version_tuple(request['current_version']): raise UpdateError('Downgrades and same-version installs are refused.')
    if type(request['size']) is not int or not 0 < request['size'] <= MAX_INSTALLER or not isinstance(request['sha256'], str) or not SHA.fullmatch(request['sha256']):
        raise UpdateError('Update installer identity is invalid.')
    old = upgrade._root(request['old_install'])
    if not isinstance(request['old_build'], str) or not SHA.fullmatch(request['old_build']): raise UpdateError('Old build identity is invalid.')
    if not identity_only and upgrade._verify_install(old) != request['old_build']: raise UpdateError('Old installation changed since approval.')
    new = old.parent / ('Kosh-' + request['version'] + '-' + directory.name[:8])
    if str(new) != request['new_install']: raise UpdateError('Candidate path does not match the fixed upgrade destination.')
    upgrade._check_chain(new)
    installer = directory / ('Kosh-' + request['version'] + '-Setup.exe')
    upgrade._check_chain(installer)
    if identity_only: return request, old, new, installer
    if not installer.is_file() or installer.stat().st_size != request['size'] or installer.stat().st_nlink > 1 or upgrade._hash(installer) != request['sha256']:
        raise UpdateError('Installer size/SHA-256 changed; it will not run.')
    with installer.open('rb') as stream:
        if stream.read(2) != b'MZ': raise UpdateError('Installer is not a Windows executable.')
    return request, old, new, installer


class CloseTimeout(UpdateError):
    pass


def wait_stopped(old, timeout=900):
    deadline = time.monotonic() + timeout
    while True:
        try: upgrade._stopped((old,)); return
        except upgrade.UpgradeError:
            if time.monotonic() >= deadline:
                raise CloseTimeout('Kosh or its browser profile stayed open. No data was copied. Resume this retained installer after closing the old window; no download is needed.') from None
            time.sleep(1)


def run_installer(installer, new):
    if os.name != 'nt': raise UpdateError('Candidate installation requires Windows.')
    if new.exists(): raise UpdateError('Candidate destination already exists and was preserved.')
    try:
        result = subprocess.run([str(installer), '--quiet', '--no-shortcuts', '--no-launch', '--install-dir', str(new)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=1800, check=False)
    except (OSError, subprocess.TimeoutExpired): raise UpdateError('Installer did not finish; its candidate folder was retained.') from None
    if result.returncode != 0: raise UpdateError('Installer failed; old installation and candidate staging were retained.')
    result = read_json(new / 'INSTALL_RESULT.json')
    if result.get('installed') is not True or result.get('status') != 'installed' or result.get('warnings') != []:
        raise UpdateError('Installer reported warnings. Candidate was retained for inspection and no data was copied.')


def candidate_identity(new, version):
    """Version/repository declarations are data, parsed without importing code."""
    build = upgrade._verify_install(new)
    manifest = upgrade._json(new / 'package-manifest.json')
    if 'updater.py' not in {row['path'] for row in manifest['files']}:
        raise UpdateError('Candidate does not include a hash-verified updater release identity.')
    path = new / 'updater.py'
    if path.stat().st_size > 256 * 1024: raise UpdateError('Candidate identity source is oversized.')
    try: tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    except (OSError, SyntaxError, UnicodeError): raise UpdateError('Candidate release identity source is invalid.') from None
    found = {}
    for row in tree.body:
        if isinstance(row, ast.Assign):
            for target in row.targets:
                if isinstance(target, ast.Name) and target.id in {'CURRENT_VERSION', 'REPOSITORY'}:
                    if target.id in found or not isinstance(row.value, ast.Constant) or not isinstance(row.value.value, str):
                        raise UpdateError('Candidate release identity is ambiguous or executable.')
                    found[target.id] = row.value.value
    if found != {'CURRENT_VERSION': version, 'REPOSITORY': REPOSITORY}:
        raise UpdateError('Candidate version/repository differs from the approved release.')
    return build


RESTORE_SHORTCUT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$taskRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json
$taskShell = New-Object -ComObject WScript.Shell
$taskOldTarget = [IO.Path]::GetFullPath((Join-Path $taskRequest.old_install 'bin\ResearchDesktop.exe'))
$taskNewTarget = [IO.Path]::GetFullPath((Join-Path $taskRequest.new_install 'bin\ResearchDesktop.exe'))
$taskLocations = @(
    @{name='Desktop'; path=(Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Kosh.lnk')},
    @{name='StartMenu'; path=(Join-Path ([Environment]::GetFolderPath('Programs')) 'Kosh\Kosh.lnk')}
)
$taskResults = @()
foreach ($taskLocation in $taskLocations) {
    $taskBackup = Join-Path $taskRequest.backup_dir ($taskLocation.name + '.lnk')
    if (-not [IO.File]::Exists($taskBackup)) { $taskResults += @{name=$taskLocation.name; status='unchanged'}; continue }
    if (-not [IO.File]::Exists($taskLocation.path)) { throw 'Changed shortcut is absent; preserved recovery backup.' }
    foreach ($taskCheckedPath in @($taskBackup, $taskLocation.path)) {
        if (([IO.File]::GetAttributes($taskCheckedPath) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Shortcut is a reparse point.' }
    }
    $taskOriginal = $taskShell.CreateShortcut($taskBackup)
    if ([IO.Path]::GetFullPath($taskOriginal.TargetPath) -ne $taskOldTarget) { throw 'Shortcut backup does not point to old Kosh.' }
    $taskCurrent = $taskShell.CreateShortcut($taskLocation.path)
    $taskCurrentTarget = [IO.Path]::GetFullPath($taskCurrent.TargetPath)
    if ($taskCurrentTarget -eq $taskOldTarget) { $taskResults += @{name=$taskLocation.name; status='already_restored'}; continue }
    if ($taskCurrentTarget -ne $taskNewTarget) { throw 'Shortcut changed by another action; preserved.' }
    $taskCurrentHash = (Get-FileHash -LiteralPath $taskLocation.path -Algorithm SHA256).Hash
    $taskTemporary = Join-Path $taskRequest.backup_dir ($taskLocation.name + '.restore.lnk')
    if ([IO.File]::Exists($taskTemporary)) { throw 'Recovery staging already exists; preserved.' }
    [IO.File]::Copy($taskBackup, $taskTemporary, $false)
    $taskReadCurrent = $taskShell.CreateShortcut($taskLocation.path)
    if ([IO.Path]::GetFullPath($taskReadCurrent.TargetPath) -ne $taskNewTarget -or (Get-FileHash -LiteralPath $taskLocation.path -Algorithm SHA256).Hash -ne $taskCurrentHash) { throw 'Shortcut changed during rollback; preserved.' }
    $taskFailedLink = Join-Path $taskRequest.backup_dir ($taskLocation.name + '.failed-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    [IO.File]::Replace($taskTemporary, $taskLocation.path, $taskFailedLink, $true)
    $taskReadback = $taskShell.CreateShortcut($taskLocation.path)
    if ([IO.Path]::GetFullPath($taskReadback.TargetPath) -ne $taskOldTarget -or (Get-FileHash -LiteralPath $taskLocation.path -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $taskBackup -Algorithm SHA256).Hash) { throw 'Shortcut rollback readback did not match.' }
    $taskResults += @{name=$taskLocation.name; status='restored_verified'}
}
@{status='restored_verified'; locations=$taskResults} | ConvertTo-Json -Depth 5 -Compress
'''


def restore_shortcuts(old, new, stage):
    backups = stage / 'shortcuts'
    upgrade._check_chain(backups)
    if not backups.exists(): return {'status': 'restored_verified', 'locations': []}
    value = upgrade._powershell(RESTORE_SHORTCUT_SCRIPT, {'old_install': str(old), 'new_install': str(new), 'backup_dir': str(backups)})
    if not isinstance(value, dict) or value.get('status') != 'restored_verified': raise UpdateError('Shortcut rollback could not be verified. Retained backups require review.')
    return value


def copy_stage(new):
    receipt = upgrade._json(new / 'UPGRADE_RECEIPT.json')
    stage = Path(receipt['sqlite_raw_snapshot']).parent
    upgrade._check_chain(stage)
    if stage.parent != new or not stage.name.startswith('upgrade-staging-') or not stage.is_dir():
        raise UpdateError('Copy recovery stage is invalid.')
    return stage


def write_pending(new, job_id):
    """Publish once; an exact existing marker is safe to reuse on recovery."""
    path = new / 'UPDATE_PENDING.json'
    upgrade._check_chain(path)
    expected = {'job_id': job_id, 'new_install': str(new)}
    try: upgrade._write_json_new(path, expected)
    except FileExistsError:
        if read_json(path) != expected:
            raise UpdateError('Existing update-pending marker belongs to another job and was preserved.') from None


def launch_and_verify(new, build):
    if os.name != 'nt': raise UpdateError('Installed application launch requires Windows.')
    from agent import Client, read_session, AgentError
    child = None
    try:
        # Start only the verified candidate's service. Its process handle is owned
        # here, so failure cleanup never terminates a PID supplied by metadata.
        child = subprocess.Popen([str(new / 'runtime/python.exe'), '-E', '-s', str(new / 'server.py'), '--data-dir', str(new / 'data'), '--ready-file', str(new / 'data/server.json'), '--update-verification'],
                                 cwd=new, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if child.poll() is not None: raise UpdateError('Candidate service exited before becoming ready.')
            try:
                session = read_session(new / 'data')
                if session['pid'] != child.pid:
                    # A stopped old install can leave a stale readiness record.
                    # Wait for this owned child to replace it; never attach to it.
                    time.sleep(0.25)
                    continue
                if session['build'] != build: raise UpdateError('Candidate startup build did not match.')
                health = Client(session, timeout=2).verify()
                expected = upgrade._json(new / 'UPGRADE_RECEIPT.json')['database']
                with upgrade.closing(upgrade._database(new / 'data/research.sqlite3')) as database:
                    if upgrade._database_summary(database) != expected: raise UpdateError('Candidate startup changed copied database records/schema.')
                # The service is ready, but no candidate user window has opened.
                # Keep the process handle for cleanup if shortcut publication fails.
                Client(session, timeout=5).request('/api/state')
                return {**health, '_process': child}
            except AgentError:
                time.sleep(0.25)
        raise UpdateError('Candidate service did not become ready within 30 seconds.')
    except BaseException:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        raise


def run_job(directory):
    directory = Path(directory); stage = None; old = None; new = None; links_attempted = False; health = None; committed = False
    def record(phase, **details):
        return write_receipt(directory, {'phase': phase, 'job_id': directory.name, 'signature': 'not_verified', **details})
    try:
        # Return terminal evidence unchanged even when retained installer/old
        # package bytes have since been removed. No execution follows this branch.
        existing = read_json(directory / 'receipt.json')
        if existing.get('phase') in TERMINAL: return existing
        with cache_guard(directory.parent):
            existing = read_json(directory / 'receipt.json')
            if existing.get('phase') in TERMINAL: return existing
            marker = directory / 'worker.json'
            if marker.exists() and upgrade._pid_alive(read_json(marker).get('pid')):
                return existing
            lease = active_install(directory.parent)
            if not lease or lease['job_id'] != directory.name: raise UpdateError('This job no longer owns the exclusive installation lease.')
            if marker.exists(): marker.unlink()  # Proven dead worker's own marker.
            upgrade._write_json_new(marker, {'pid': os.getpid()})
        recovery = existing.get('phase') != 'awaiting_close'
        request, old, new, installer = validate_job(directory, identity_only=recovery)
        if existing.get('phase') != 'awaiting_close':
            # A crashed copy is never restarted over a partially published tree.
            if existing.get('phase') in {'starting', 'retargeting'}:
                # A crashed verification service holds the copied saved port.
                # Stop only that authenticated, still-locked candidate so reopening
                # the old shortcut is usable. Never stop an activated user session.
                build = candidate_identity(new, request['version'])
                stop_verification_candidate(new, build)
            if existing.get('phase') == 'retargeting':
                stage = copy_stage(new); links_attempted = True
                require_unchanged_candidate_data(new)
                restored = restore_shortcuts(old, new, stage)
                return record('rolled_back', version=request['version'], shortcuts=restored,
                              message='Interrupted startup restored old shortcuts. Both installations and data were retained; reopen the old Kosh shortcut.')
            return record('interrupted', version=request['version'], message='Interrupted update retained its files. No automatic retry or overwrite; reopen old Kosh and review this receipt.')
        wait_stopped(old)
        old_inventory = upgrade._inventory(old / 'data')
        if new.exists(): raise UpdateError('Candidate destination appeared and was preserved.')
        record('installing', version=request['version'])
        run_installer(installer, new)
        build = candidate_identity(new, request['version'])
        if build == request['old_build']: raise UpdateError('Candidate build is identical to the old install; no copy was performed.')
        record('copying', version=request['version'], build=build)
        upgrade.upgrade(old, new, apply=True, retarget_shortcuts=False)
        stage = copy_stage(new)
        # This durable marker keeps a normal Launcher.cs relaunch read-only too.
        # It is written before starting any candidate service, and never deleted.
        write_pending(new, directory.name)
        record('starting', version=request['version'], build=build)
        health = launch_and_verify(new, build)
        if not isinstance(health, dict) or health.get('ready') is not True or health.get('build') != build or health.get('app') != 'pg-research-desktop':
            raise UpdateError('Candidate health/build did not verify.')
        verify_old_preserved(old, new, old_inventory)
        record('retargeting', version=request['version'], build=build)
        links_attempted = True
        links = upgrade._retarget_shortcuts(old, new, stage)
        if links.get('status') != 'complete' or any(row.get('status') not in {'retargeted_verified', 'already_new', 'absent'} for row in links.get('locations', [])):
            raise UpdateError('Shortcut locations did not all point to this candidate or remain absent.')
        verify_old_preserved(old, new, old_inventory)
        completed = record('installed_verified', version=request['version'], build=build, shortcuts=links,
                      startup={'app': health['app'], 'build': health['build'], 'ready': True}, old_install_preserved=True,
                      message='New installation copied and startup verified. Old installation and data remain the rollback copy.')
        committed = True
        upgrade._write_json_new(new / 'UPDATE_READY.json', {'format': 1, 'app': 'Kosh', 'repository': REPOSITORY,
                                'job_id': directory.name, 'version': request['version'], 'build': build,
                                'new_install': str(new), 'phase': 'installed_verified'})
        # Completion is durable before exposing an editable new window. Once this
        # point is reached, a later run cannot automatically roll back shortcuts.
        try: activate_candidate(new, build)
        except Exception:
            failed = record('activation_failed', version=request['version'], build=build, shortcuts=links,
                            message='Copied data and service startup passed, but activating the new service did not verify. Both copies remain. No automatic rollback follows this completion boundary. Open this updated copy and choose Finish opening this updated copy; review both data paths before switching to the old version.')
            try: open_candidate(new)
            except (OSError, UpdateError): pass
            return failed
        try: open_candidate(new)
        except (OSError, UpdateError):
            return record('installed_verified', version=request['version'], build=build, shortcuts=links,
                          message='New service/build verified and shortcuts updated, but its window could not open. Reopen Kosh from its shortcut. Old data remains retained.')
        return completed
    except CloseTimeout:
        return record('close_timeout', message='Close window wait expired. Installer stayed retained and did not run. Reopen old Kosh and explicitly resume without downloading again.')
    except Exception:
        if committed:
            return record('activation_failed', message='Startup completion was recorded, but readiness/activation did not finish. Both copies remain. No automatic rollback; inspect retained receipts and both data paths before selecting a version.')
        if isinstance(health, dict) and health.get('_process') is not None:
            stop_owned_service(health['_process'])
        if links_attempted and old is not None and new is not None and stage is not None:
            try:
                require_unchanged_candidate_data(new)
                restored = restore_shortcuts(old, new, stage)
                return record('rolled_back', shortcuts=restored, message='Candidate startup/action failed. Old shortcuts restored; old and candidate data retained. Reopen the old Kosh shortcut.')
            except Exception:
                return record('rollback_failed', message='Update failed and shortcut restoration could not verify. Old installation/data and shortcut backups remain; inspect the retained receipts before retrying.')
        return record('failed', message='Update did not finish. Old installation/data and any candidate staging were retained. No automatic retry or overwrite.')
    finally:
        try: release_install(directory)
        except (OSError, ValueError): pass  # A retained lease is safer than an unverified release.


def require_unchanged_candidate_data(new):
    baseline = upgrade._json(new / 'UPGRADE_RECEIPT.json')['database']
    with upgrade.closing(upgrade._database(new / 'data/research.sqlite3')) as database:
        if upgrade._database_summary(database) != baseline:
            raise UpdateError('Candidate records have changed. Automatic rollback is refused to protect newer work; choose versions explicitly and review both data paths.')


def verify_old_preserved(old, new, inventory=None):
    upgrade._stopped((old,))
    receipt = upgrade._json(new / 'UPGRADE_RECEIPT.json')
    actual = upgrade._inventory(old / 'data')
    if actual['files'] != receipt['source_files'] or (inventory is not None and actual != inventory):
        raise UpdateError('Old data changed after the verified copy. Completion is refused; both copies are retained for review.')


def stop_owned_service(child):
    if child.poll() is None:
        child.terminate()
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)


def open_candidate(new):
    if os.name != 'nt': raise UpdateError('Installed application window requires Windows.')
    subprocess.Popen([str(new / 'bin/ResearchDesktop.exe')], cwd=new, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def activate_candidate(new, build):
    from agent import Client, read_session
    session = read_session(new / 'data')
    if session['build'] != build: raise UpdateError('Candidate activation build does not match.')
    client = Client(session, timeout=10); client.verify()
    result = client.request('/api/updates/activate', {})
    if result.get('activated') is not True or result.get('build') != build:
        raise UpdateError('Candidate activation readback did not match.')


def stop_verification_candidate(new, build):
    from agent import Client, read_session
    try:
        upgrade._stopped((new,))
        return
    except upgrade.UpgradeError:
        pass
    session = read_session(new / 'data')
    if session['build'] != build: raise UpdateError('Interrupted verification service build did not match.')
    client = Client(session, timeout=5); client.verify()
    if client.request('/api/updates/status').get('activation_required') is not True:
        raise UpdateError('Candidate is already open for user writes. Automatic interrupted-session shutdown is refused.')
    client.request('/api/shutdown', {})
    deadline = time.monotonic() + 15
    while True:
        try: upgrade._stopped((new,)); return
        except upgrade.UpgradeError:
            if time.monotonic() >= deadline: raise UpdateError('Verification service shutdown could not be confirmed.') from None
            time.sleep(0.25)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    # CLI execution only accepts the generated per-user cache, not arbitrary paths.
    expected = cache_root().resolve()
    upgrade._check_chain(args.job_dir)
    if not args.job_dir.is_absolute() or args.job_dir.resolve().parent != expected or not JOB_ID.fullmatch(args.job_dir.name):
        return 2
    result = run_job(args.job_dir)
    return 0 if result.get('phase') == 'installed_verified' else 1


if __name__ == '__main__': sys.exit(main())
