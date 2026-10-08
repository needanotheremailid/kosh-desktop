"""Unified local backup jobs use only invented records and temporary folders."""
import base64
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_backup import AutoBackup
import auto_backup as jobs
from backend import AppError, Store
import workspace_archive as archives


class LocalBackupJobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data')
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented local job'})['id']
        self.store.dispatch('POST', '/api/import', {'workspace_id': self.workspace, 'files': [{'name': 'widgets.txt', 'data': base64.b64encode(b'Invented widgets have wheels.').decode('ascii')}]})
        self.backups = AutoBackup(self.store)
        self.destination = self.root / 'outputs'
        self.destination.mkdir()

    def tearDown(self):
        self.backups.stop()
        self.store.close()
        self.temp.cleanup()

    def wait(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.backups.job_status(job_id)
            if result['state'] in {'complete', 'failed', 'cancelled'}:
                return result
            time.sleep(0.01)
        self.fail('Local job did not finish')

    def backup(self, name='selected.zip'):
        return self.backups.start_job({'operation': 'backup', 'workspace_id': self.workspace, 'path': str(self.destination / name), 'include_history': True})

    def test_manual_backup_without_opt_in_then_selected_zip_preview_and_fresh_restore(self):
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'First'})
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': note['id'], 'version': note['version'], 'title': 'Draft', 'body': 'Second'})
        saved = self.wait(self.backup()['job_id'])
        self.assertEqual(saved['state'], 'complete')
        self.assertFalse(self.backups.status()['enabled'])
        self.assertEqual(saved['result']['counts']['revisions'], 1)
        path = saved['result']['path']
        preview = self.wait(self.backups.start_job({'operation': 'preview', 'path': path})['job_id'])
        self.assertEqual(preview['state'], 'complete')
        self.assertEqual(preview['result']['documents'], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)
        result = self.backups.restore_local({'preview_id': preview['result']['preview_id'], 'approve': True})
        self.assertNotEqual(result['workspace_id'], self.workspace)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 2)
        with self.assertRaises(AppError):
            self.backups.restore_local({'preview_id': preview['result']['preview_id'], 'approve': True})

    def test_cancel_backup_before_publication_preserves_existing_data_and_partial_output(self):
        entered, release = threading.Event(), threading.Event()
        original_copy = archives.stream_copy
        def paused(source, output=None, **kwargs):
            if output is not None:
                entered.set()
                release.wait(5)
            return original_copy(source, output, **kwargs)
        with patch.object(archives, 'stream_copy', side_effect=paused):
            job = self.backup()
            self.assertTrue(entered.wait(5))
            self.assertTrue(self.backups.status()['running'])
            self.assertTrue(self.backups.cancel_job({'job_id': job['job_id']})['accepted'])
            release.set()
            result = self.wait(job['job_id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertFalse((self.destination / 'selected.zip').exists())
        self.assertTrue(list(self.destination.iterdir()))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)
        self.assertIsNone(self.backups.status()['last_success'])

    def test_cancel_preview_creates_no_restore_token_and_leaves_records(self):
        path = self.wait(self.backup()['job_id'])['result']['path']
        entered, release = threading.Event(), threading.Event()
        original_copy = archives.stream_copy
        def paused(source, output=None, **kwargs):
            entered.set()
            release.wait(5)
            return original_copy(source, output, **kwargs)
        with patch.object(archives, 'stream_copy', side_effect=paused):
            job = self.backups.start_job({'operation': 'preview', 'path': path})
            self.assertTrue(entered.wait(5))
            self.backups.cancel_job({'job_id': job['job_id']})
            release.set()
            result = self.wait(job['job_id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertIsNone(result['result'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_no_clobber_path_bounds_extension_and_changed_preview(self):
        with self.assertRaises(AppError):
            self.backups.start_job({'operation': 'backup', 'workspace_id': self.workspace, 'path': str(self.store.root / 'bad.zip'), 'include_history': True})
        with self.assertRaises(AppError):
            self.backup('not-a-backup.txt')
        result = self.wait(self.backup('selected')['job_id'])
        self.assertTrue(result['result']['path'].endswith('.zip'))
        with self.assertRaises(AppError):
            self.backup()
        preview = self.wait(self.backups.start_job({'operation': 'preview', 'path': result['result']['path']})['job_id'])['result']
        Path(result['result']['path']).write_bytes(b'changed')
        with self.assertRaises(AppError):
            self.backups.restore_local({'preview_id': preview['preview_id'], 'approve': True})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_invalid_set_metadata_fails_before_publication(self):
        self.backups.configure({'enabled': True, 'destination': str(self.destination), 'interval_minutes': 60})
        self.backups.build = 'x' * 201
        self.assertFalse(self.backups.run_now()['ok'])
        listing = self.backups.list_sets()
        self.assertEqual(listing['sets'], [])
        self.assertEqual(listing['issues'], [])
        self.assertIsNone(self.backups.status()['last_success'])
        self.assertIn('metadata', self.backups.status()['last_error'].lower())

    def test_temporary_drive_space_checked_before_preview_copy(self):
        result = self.wait(self.backup()['job_id'])['result']
        import shutil
        with patch('workspace_archive.shutil.disk_usage', return_value=shutil._ntuple_diskusage(1, 1, 0)):
            job = self.wait(self.backups.start_job({'operation': 'preview', 'path': result['path']})['job_id'])
        self.assertEqual(job['state'], 'failed')
        self.assertIn('Temporary validation storage', job['error'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_stop_cancels_streaming_job_then_reopened_controller_can_retry(self):
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        original_copy = archives.stream_copy
        def paused(source, output=None, **kwargs):
            if output is not None:
                entered.set()
                release.wait(5)
            return original_copy(source, output, **kwargs)
        with patch.object(archives, 'stream_copy', side_effect=paused):
            job = self.backup()
            self.assertTrue(entered.wait(5))
            stopper = threading.Thread(target=lambda: (self.backups.stop(), stopped.set()))
            stopper.start()
            self.assertFalse(stopped.wait(0.05))
            release.set()
            stopper.join(5)
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.backups.job_status(job['job_id'])['state'], 'cancelled')
        self.backups = AutoBackup(self.store)
        self.assertEqual(self.wait(self.backup('retry.zip')['job_id'])['state'], 'complete')

    def test_publication_gate_refuses_cancellation_and_reports_completed(self):
        entered, release = threading.Event(), threading.Event()
        original_rename = Path.rename
        def paused_rename(path, target):
            if '.pending-' in path.name and path.parent == self.destination:
                entered.set()
                release.wait(5)
            return original_rename(path, target)
        with patch.object(Path, 'rename', new=paused_rename):
            job = self.backup()
            self.assertTrue(entered.wait(5))
            self.assertFalse(self.backups.cancel_job({'job_id': job['job_id']})['accepted'])
            release.set()
            result = self.wait(job['job_id'])
        self.assertEqual(result['state'], 'complete')
        self.assertTrue((self.destination / 'selected.zip').is_file())

    def test_queued_manual_job_makes_scheduler_busy_without_attempt_or_backoff(self):
        self.backups.configure({'enabled': True, 'destination': str(self.destination), 'interval_minutes': 60})
        with self.backups._state_lock:
            queued = self.backups._new_job('backup')
        try:
            result = self.backups.run_now()
            self.assertEqual(result['status'], 'busy')
            self.assertIsNone(self.backups.status()['last_attempt'])
            self.assertIsNone(self.backups.status()['last_failure'])
        finally:
            self.backups._jobs.pop(queued)

    def test_cleanup_stat_failure_terminalizes_job_and_releases_operation_guard(self):
        original_stat = Path.stat
        def unreadable(path, *args, **kwargs):
            if '.pending-' in path.name and path.parent == self.destination:
                raise OSError('Synthetic unavailable recovery metadata')
            return original_stat(path, *args, **kwargs)
        def failed_backup(workspace_id, path, **kwargs):
            path.write_bytes(b'Partial invented backup')
            raise OSError('Synthetic write failure')
        try:
            with patch.object(self.store, 'write_backup', side_effect=failed_backup), patch.object(Path, 'stat', new=unreadable):
                job = self.backup()
                self.backups._job_threads[job['job_id']].join(5)
            locked = self.backups._run_lock.locked()
            state = self.backups.job_status(job['job_id'])['state']
        finally:
            # Keep an intentionally failing red fixture from hanging teardown.
            if self.backups._run_lock.locked():
                self.backups._run_lock.release()
        self.assertFalse(locked, 'A failed recovery stat must never strand the operation lock.')
        self.assertEqual(state, 'failed')

    def test_approved_restore_after_stop_is_refused(self):
        path = self.wait(self.backup()['job_id'])['result']['path']
        preview = self.wait(self.backups.start_job({'operation': 'preview', 'path': path})['job_id'])['result']
        self.backups.stop()
        with self.assertRaises(AppError):
            self.backups.restore_local({'preview_id': preview['preview_id'], 'approve': True})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_legacy_restore_observes_operation_guard(self):
        self.backups.configure({'enabled': True, 'destination': str(self.destination), 'interval_minutes': 60})
        self.backups.run_now()
        saved = self.backups.list_sets()['sets'][0]
        preview = self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': self.workspace})
        self.backups._run_lock.acquire()
        try:
            with self.assertRaises(AppError):
                self.backups.restore({'preview_id': preview['preview_id'], 'approve': True})
        finally:
            self.backups._run_lock.release()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_deep_preview_cancellation_propagates_as_cancelled(self):
        path = self.wait(self.backup()['job_id'])['result']['path']
        original_checkpoint = jobs._JobControl.checkpoint
        for wanted in ('reading_source', 'verifying_source', 'validating_records'):
            def cancel_at(control, phase, **kwargs):
                if phase == wanted:
                    control.owner.cancel_job({'job_id': control.job_id})
                return original_checkpoint(control, phase, **kwargs)
            with self.subTest(phase=wanted), patch.object(jobs._JobControl, 'checkpoint', new=cancel_at):
                result = self.wait(self.backups.start_job({'operation': 'preview', 'path': path})['job_id'])
                self.assertEqual(result['state'], 'cancelled')
                self.assertIsNone(result['result'])
        self.assertEqual(self.backups._local_previews, {})

    def test_dispatch_and_streaming_callbacks_have_no_store_to_status_lock_order(self):
        original_status = self.store.auto_backups.status
        def status():
            self.assertFalse(self.store.lock._is_owned())
            return original_status()
        with patch.object(self.store.auto_backups, 'status', side_effect=status):
            self.store.dispatch('GET', '/api/auto-backup')
        test = self
        class Control:
            def checkpoint(self, phase, **kwargs):
                test.assertFalse(test.store.lock._is_owned())
        self.store.write_backup(self.workspace, self.destination / 'order.zip', control=Control())

    def test_shutdown_scheduler_race_is_not_persisted_as_backup_failure(self):
        def stopped_tick():
            self.backups._stop.set()
            self.backups._wake.set()
            raise AppError('Backups are shutting down.', 503)
        with patch.object(self.backups, 'tick', side_effect=stopped_tick):
            self.backups._loop()
        self.assertIsNone(self.backups.status()['last_failure'])
        self.assertEqual(self.backups.status()['last_error'], '')

    def test_cancel_automatic_set_mid_workspace_loop_retains_only_incomplete_set(self):
        self.backups.configure({'enabled': True, 'destination': str(self.destination), 'interval_minutes': 60})
        self.store.dispatch('POST', '/api/workspaces', {'title': 'Second invented workspace'})
        original_write, calls = self.store.write_backup, []
        def write(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                job_id = self.backups.status()['active_job']['job_id']
                self.backups.cancel_job({'job_id': job_id})
            return original_write(*args, **kwargs)
        with patch.object(self.store, 'write_backup', side_effect=write):
            result = self.wait(self.backups.start_job({'operation': 'automatic'})['job_id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.backups.list_sets()['sets'], [])
        self.assertIsNone(self.backups.status()['last_success'])
        self.assertTrue(Path(result['recovery_path']).is_dir())
        self.assertGreater(result['retained_bytes'], 0)

    def test_cancel_preview_set_keeps_no_restore_token(self):
        self.backups.configure({'enabled': True, 'destination': str(self.destination), 'interval_minutes': 60})
        self.backups.run_now()
        saved = self.backups.list_sets()['sets'][0]
        original_checkpoint = jobs._JobControl.checkpoint
        def cancel_at(control, phase, **kwargs):
            if phase == 'validating_records':
                control.owner.cancel_job({'job_id': control.job_id})
            return original_checkpoint(control, phase, **kwargs)
        with patch.object(jobs._JobControl, 'checkpoint', new=cancel_at):
            result = self.wait(self.backups.start_job({'operation':'preview-set','set_id':saved['set_id'],'workspace_id':self.workspace})['job_id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.backups._local_previews, {})

    @unittest.skipUnless(os.name == 'nt', 'The shipped target is Windows; POSIX publication is not claimed.')
    def test_windows_late_target_appearance_never_clobbers_existing_file(self):
        original_rename = Path.rename
        def appearing(path, target):
            if '.pending-' in path.name and path.parent == self.destination:
                Path(target).write_bytes(b'PREEXISTING')
            return original_rename(path, target)
        with patch.object(Path, 'rename', new=appearing):
            result = self.wait(self.backup()['job_id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual((self.destination / 'selected.zip').read_bytes(), b'PREEXISTING')


if __name__ == '__main__':
    unittest.main()
