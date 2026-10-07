"""Copy-only upgrades of synthetic installations; no private app/shortcut access."""
import hashlib
from contextlib import closing
import json
import os
import io
import re
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
from unittest.mock import patch

from upgrade import UpgradeError, upgrade


def installed(root, build):
    root.mkdir()
    files = []
    for name, data in [('backend.py', b'# synthetic backend'), ('server.py', b'# synthetic server'), ('runtime/python.exe', b'synthetic runtime'), ('bin/ResearchDesktop.exe', b'synthetic launcher')]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    (root / 'package-manifest.json').write_text(json.dumps({'format': 1, 'app': 'pg-research-desktop', 'build': build, 'files': files}), encoding='utf-8')
    (root / 'INSTALL_RECEIPT.json').write_text(json.dumps({'app': 'Kosh', 'build': build, 'files_verified': len(files), 'payload_bytes': sum(row['size'] for row in files), 'runtime_checked': True}), encoding='utf-8')


def synthetic_data(root):
    data = root / 'data'
    data.mkdir()
    (data / 'originals').mkdir()
    (data / 'originals' / 'source.txt').write_bytes(b'Synthetic widget original')
    (data / 'edge-profile' / 'Default').mkdir(parents=True)
    (data / 'edge-profile' / 'Default' / 'recovery.json').write_text('{"draft":"synthetic recovered widgets"}', encoding='utf-8')
    (data / 'folder-edit-recovery').mkdir()
    (data / 'folder-edit-recovery' / 'retained.txt').write_bytes(b'Synthetic old bytes')
    with closing(sqlite3.connect(data / 'research.sqlite3')) as database:
        for table in ('workspaces', 'documents', 'pages', 'notes', 'matrix', 'chats', 'revisions', 'settings'):
            database.execute('CREATE TABLE ' + table + '(id TEXT, value BLOB)')
        database.execute("INSERT INTO notes VALUES('synthetic-note', ?)", (b'widget draft',))
        database.execute("INSERT INTO revisions VALUES('synthetic-revision', ?)", (b'older widget draft',))
        database.commit()
    return data


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old, self.new = self.root / 'old', self.root / 'new'
        installed(self.old, 'a' * 64)
        installed(self.new, 'b' * 64)
        self.data = synthetic_data(self.old)
        self.process_probe = patch('upgrade._running_processes', return_value={'service': False, 'browser': False})
        self.process_probe.start()

    def tearDown(self):
        self.process_probe.stop()
        self.temp.cleanup()

    def test_dry_run_is_default_and_creates_nothing(self):
        result = upgrade(self.old, self.new)
        self.assertFalse(result['applied'])
        self.assertEqual(result['counts']['notes'], 1)
        self.assertFalse((self.new / 'data').exists())
        self.assertFalse(list(self.new.glob('upgrade-staging-*')))

    def test_verified_copy_preserves_old_and_entire_new_data(self):
        before = {path.relative_to(self.data).as_posix(): path.read_bytes() for path in self.data.rglob('*') if path.is_file()}
        result = upgrade(self.old, self.new, apply=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['counts']['revisions'], 1)
        self.assertEqual((self.new / 'data/originals/source.txt').read_bytes(), b'Synthetic widget original')
        self.assertEqual((self.new / 'data/folder-edit-recovery/retained.txt').read_bytes(), b'Synthetic old bytes')
        self.assertIn('synthetic recovered widgets', (self.new / 'data/edge-profile/Default/recovery.json').read_text())
        after = {path.relative_to(self.data).as_posix(): path.read_bytes() for path in self.data.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        receipt = json.loads((self.new / 'UPGRADE_RECEIPT.json').read_text())
        self.assertTrue(receipt['old_install_preserved'])
        self.assertEqual(receipt['database']['integrity'], 'ok')
        self.assertEqual(receipt['database']['counts']['notes'], 1)

    def test_existing_empty_new_data_is_preserved_and_refused(self):
        (self.new / 'data').mkdir()
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new, apply=True)
        self.assertTrue((self.new / 'data').is_dir())

    def test_existing_new_data_with_records_is_never_overwritten(self):
        (self.new / 'data').mkdir()
        (self.new / 'data' / 'mine.txt').write_bytes(b'preserve')
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new, apply=True)
        self.assertEqual((self.new / 'data/mine.txt').read_bytes(), b'preserve')

    def test_same_or_nested_installations_are_refused(self):
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.old)
        nested = self.old / 'nested'
        installed(nested, 'b' * 64)
        with self.assertRaises(UpgradeError):
            upgrade(self.old, nested)

    def test_missing_and_mismatched_install_receipts_refused(self):
        (self.new / 'INSTALL_RECEIPT.json').unlink()
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new)

    def test_new_installed_file_hash_mismatch_refused(self):
        (self.new / 'backend.py').write_bytes(b'tampered')
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new)

    def test_old_installed_file_hash_mismatch_refused(self):
        (self.old / 'server.py').write_bytes(b'tampered')
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new)

    def test_manifest_traversal_refused(self):
        path = self.new / 'package-manifest.json'
        value = json.loads(path.read_text())
        value['files'][0]['path'] = '../outside.py'
        path.write_text(json.dumps(value))
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new)

    def test_live_session_pid_refuses_without_reading_token_into_output(self):
        (self.data / 'agent-session.json').write_text(json.dumps({'pid': os.getpid(), 'token': 'synthetic-secret-token', 'port': 49999}))
        with self.assertRaises(UpgradeError) as captured:
            upgrade(self.old, self.new, apply=True)
        self.assertNotIn('synthetic-secret-token', str(captured.exception))
        self.assertFalse((self.new / 'data').exists())

    def test_process_probe_running_service_and_browser_refuses(self):
        for state in ({'service': True, 'browser': False}, {'service': False, 'browser': True}):
            with self.subTest(state=state), patch('upgrade._running_processes', return_value=state):
                with self.assertRaises(UpgradeError):
                    upgrade(self.old, self.new, apply=True)

    def test_corrupt_database_refused_without_published_data(self):
        (self.data / 'research.sqlite3').write_bytes(b'not sqlite')
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new, apply=True)
        self.assertFalse((self.new / 'data').exists())

    def test_newer_schema_version_refused(self):
        with closing(sqlite3.connect(self.data / 'research.sqlite3')) as database:
            database.execute('PRAGMA user_version=100')
            database.commit()
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new, apply=True)

    def test_schema_version_one_is_supported_without_migrating(self):
        with closing(sqlite3.connect(self.data / 'research.sqlite3')) as database:
            database.execute('PRAGMA user_version=1')
            database.commit()
        result = upgrade(self.old, self.new, apply=True)
        self.assertTrue(result['applied'])
        receipt = json.loads((self.new / 'UPGRADE_RECEIPT.json').read_text())
        self.assertEqual(receipt['database']['user_version'], 1)
        self.assertFalse(receipt['schema_migration_performed'])

    def test_source_mutation_during_copy_refuses_and_retains_staging(self):
        import upgrade as module
        original = module._copy_file
        def changed(source, target):
            original(source, target)
            if source.name == 'source.txt':
                source.write_bytes(b'changed during upgrade')
        with patch('upgrade._copy_file', side_effect=changed):
            with self.assertRaises(UpgradeError):
                upgrade(self.old, self.new, apply=True)
        self.assertFalse((self.new / 'data').exists())
        self.assertTrue(list(self.new.glob('upgrade-staging-*')))

    def test_destination_race_refuses_no_clobber_publish(self):
        import upgrade as module
        original = module._publish_directory
        def raced(source, target):
            target.mkdir()
            (target / 'concurrent.txt').write_bytes(b'concurrent')
            original(source, target)
        with patch('upgrade._publish_directory', side_effect=raced):
            with self.assertRaises(UpgradeError):
                upgrade(self.old, self.new, apply=True)
        self.assertEqual((self.new / 'data/concurrent.txt').read_bytes(), b'concurrent')

    def test_shortcuts_are_only_requested_explicitly_after_copy(self):
        with patch('upgrade._retarget_shortcuts', return_value={'status': 'complete', 'changed': 2}) as retarget:
            upgrade(self.old, self.new)
            retarget.assert_not_called()
            result = upgrade(self.old, self.new, apply=True, retarget_shortcuts=True)
            retarget.assert_called_once()
            self.assertEqual(result['shortcuts']['changed'], 2)

    def test_shortcut_failure_does_not_hide_successful_data_copy(self):
        with patch('upgrade._retarget_shortcuts', side_effect=UpgradeError('Shortcut support unavailable.')):
            result = upgrade(self.old, self.new, apply=True, retarget_shortcuts=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['shortcuts']['status'], 'failed')
        self.assertTrue((self.new / 'UPGRADE_RECEIPT.json').exists())

    def test_existing_receipt_is_not_overwritten(self):
        (self.new / 'UPGRADE_RECEIPT.json').write_text('existing proof')
        with self.assertRaises(UpgradeError):
            upgrade(self.old, self.new, apply=True)
        self.assertEqual((self.new / 'UPGRADE_RECEIPT.json').read_text(), 'existing proof')

    def test_crash_left_committed_wal_rows_are_consolidated_without_touching_old(self):
        with closing(sqlite3.connect(self.data / 'research.sqlite3')) as database:
            database.execute('PRAGMA journal_mode=WAL')
            database.execute("INSERT INTO notes VALUES('wal-note', ?)", (b'committed WAL widget',))
            database.commit()
            raw = {name: (self.data / name).read_bytes() for name in ('research.sqlite3', 'research.sqlite3-wal', 'research.sqlite3-shm')}
        for name, data in raw.items():
            (self.data / name).write_bytes(data)
        plan = upgrade(self.old, self.new)
        self.assertTrue(plan['requires_staged_database_check'])
        self.assertIsNone(plan['counts'])
        result = upgrade(self.old, self.new, apply=True)
        self.assertEqual(result['counts']['notes'], 2)
        self.assertFalse((self.new / 'data/research.sqlite3-wal').exists())
        self.assertEqual({name: (self.data / name).read_bytes() for name in raw}, raw)
        with closing(sqlite3.connect(self.new / 'data/research.sqlite3')) as database:
            self.assertEqual(database.execute("SELECT value FROM notes WHERE id='wal-note'").fetchone()[0], b'committed WAL widget')

    def test_occupied_saved_port_is_refused_without_http_requests(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            (self.data / 'listen-port.json').write_text(json.dumps({'port': listener.getsockname()[1]}))
            with self.assertRaises(UpgradeError):
                upgrade(self.old, self.new)

    def test_receipt_publication_failure_reports_data_already_published(self):
        with patch('upgrade.os.link', side_effect=OSError('synthetic receipt race')):
            with self.assertRaises(UpgradeError) as captured:
                upgrade(self.old, self.new, apply=True)
        self.assertTrue(captured.exception.data_published)
        self.assertTrue((self.new / 'data/research.sqlite3').exists())

    def test_cli_summary_contains_no_tokens_or_private_paths(self):
        from upgrade import main
        (self.data / 'agent-session.json').write_text(json.dumps({'pid': 999999, 'token': 'synthetic-secret-token'}))
        with patch('upgrade._pid_alive', return_value=False), patch('sys.stdout', new_callable=io.StringIO) as output:
            result = main(['--old-install', str(self.old), '--new-install', str(self.new)])
        self.assertEqual(result, 0)
        self.assertNotIn('synthetic-secret-token', output.getvalue())
        self.assertNotIn(str(self.old), output.getvalue())
        self.assertNotIn(str(self.new), output.getvalue())

    @unittest.skipUnless(os.name == 'nt', 'Synthetic PowerShell mechanics run on Windows only.')
    def test_process_matcher_handles_synthetic_edge_profile_without_process_query(self):
        import upgrade as module
        # Replace the OS query with invented records; no private process list is read.
        records = "$taskProcesses = @([pscustomobject]@{Name='msedge.exe'; CommandLine='msedge.exe --user-data-dir=\"C:\\synthetic\\old\\data\\edge-profile\"'})"
        script = re.sub(r'^\$taskProcesses = Get-CimInstance[^\n]*$', lambda _: records, module.PROCESS_SCRIPT, flags=re.M)
        value = module._powershell(script, {'data_paths': [r'C:\synthetic\old\data']})
        self.assertTrue(value['browser'])
        self.assertFalse(value['service'])

    @unittest.skipUnless(os.name == 'nt', 'Synthetic shortcut COM mechanics run on Windows only.')
    def test_shortcut_retarget_native_mechanics_only_touch_synthetic_matching_link(self):
        import upgrade as module
        directory = self.root / 'synthetic-links'
        directory.mkdir()
        desktop, start = directory / 'Desktop.lnk', directory / 'StartMenu.lnk'
        create = r'''
$ErrorActionPreference='Stop'
$taskRequest=[Console]::In.ReadToEnd() | ConvertFrom-Json
$taskShell=New-Object -ComObject WScript.Shell
$taskOne=$taskShell.CreateShortcut($taskRequest.desktop)
$taskOne.TargetPath=Join-Path $taskRequest.old_install 'bin\ResearchDesktop.exe'
$taskOne.WorkingDirectory=$taskRequest.old_install
$taskOne.Save()
$taskTwo=$taskShell.CreateShortcut($taskRequest.start)
$taskTwo.TargetPath=Join-Path $taskRequest.old_install 'unrelated.exe'
$taskTwo.Save()
@{created=2} | ConvertTo-Json -Compress
'''
        module._powershell(create, {'desktop': str(desktop), 'start': str(start), 'old_install': str(self.old)})
        preserved_hash = hashlib.sha256(start.read_bytes()).hexdigest()
        real = module._powershell
        diagnostics = []
        def scoped(script, request):
            locations = "$taskLocations = @(@{name='Desktop'; path=$taskRequest.test_desktop}, @{name='StartMenu'; path=$taskRequest.test_start})"
            script = re.sub(r'\$taskLocations = @\(.*?\n\)', lambda _: locations, script, flags=re.S)
            script = 'try {\n' + script + '\n} catch { @{error=$_.FullyQualifiedErrorId; type=$_.Exception.GetType().Name; line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json -Compress }'
            value = real(script, {**request, 'test_desktop': str(desktop), 'test_start': str(start)})
            diagnostics.append(value)
            return value
        with patch('upgrade._powershell', side_effect=scoped):
            result = upgrade(self.old, self.new, apply=True, retarget_shortcuts=True)
        self.assertEqual(result['shortcuts']['status'], 'complete', diagnostics)
        self.assertEqual(result['shortcuts']['changed'], 1)
        self.assertEqual(result['shortcuts']['locations'][1]['status'], 'preserved_unrelated')
        self.assertEqual(hashlib.sha256(start.read_bytes()).hexdigest(), preserved_hash)
        self.assertTrue(any(path.name == 'Desktop.lnk' for path in self.new.glob('upgrade-staging-*/shortcuts/Desktop.lnk')))


if __name__ == '__main__':
    unittest.main()
