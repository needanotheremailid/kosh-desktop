"""File-backed backups of invented sources; no private library or network."""
import base64
import hashlib
import json
import random
import tempfile
import threading
import tracemalloc
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import backend as b
import workspace_archive as archives
from auto_backup import AutoBackup


class LargeBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = b.Store(self.root / 'data')
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented binary library'})['id']
        self.folder = self.root / 'backups'
        self.folder.mkdir()
        self.backups = AutoBackup(self.store)
        self.backups.configure({'enabled': True, 'destination': str(self.folder), 'interval_minutes': 60})

    def tearDown(self):
        self.backups.stop()
        self.store.close()
        self.temp.cleanup()

    def source(self, index, megabytes=1):
        pdf = b.pdf_lib.open()
        pdf.new_page().insert_text((40, 40), 'Invented source ' + str(index))
        pdf.embfile_add('invented.bin', random.Random(index).randbytes(megabytes * 1024 * 1024))
        data = pdf.tobytes()
        pdf.close()
        result = self.store.dispatch('POST', '/api/import', {'workspace_id': self.workspace, 'files': [{'name': 'invented-' + str(index) + '.pdf', 'data': base64.b64encode(data).decode('ascii')}]})['results'][0]
        self.assertEqual(result['status'], 'ready')
        return result['document']

    def test_greater_than_47_mib_automatic_round_trip_uses_file_io(self):
        first, second = self.source(1, 25), self.source(2, 25)
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Invented draft', 'body': 'First [[source:' + first['id'] + ':1]]'})
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': note['id'], 'version': note['version'], 'title': note['title'], 'body': 'Second [[source:' + second['id'] + ':1]]'})
        with self.assertRaises(b.AppError):
            self.store.file_response('/api/backup', {'workspace_id': self.workspace, 'history': '1'})
        before = {path.name for path in self.store.originals.iterdir()}
        with patch.object(self.store, '_backup', side_effect=AssertionError('Automatic backups must not build a whole ZIP in memory')), patch.object(self.store, '_bytes', side_effect=AssertionError('File export must stream originals rather than call the full-bytes helper')), patch.object(b, 'decode_base64', side_effect=AssertionError('File-backed restore must not use base64')):
            tracemalloc.start()
            try:
                self.assertTrue(self.backups.run_now()['ok'])
                saved = self.backups.list_sets()['sets'][0]
                entry = saved['workspaces'][0]
                self.assertGreater(entry['bytes'], 47 * 1024 * 1024)
                preview = self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': self.workspace})
                self.assertEqual(preview['documents'], 2)
                self.assertEqual(preview['revisions'], 1)
                self.assertEqual(before, {path.name for path in self.store.originals.iterdir()})
                result = self.backups.restore({'preview_id': preview['preview_id'], 'approve': True})
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        restored = self.store.dispatch('GET', '/api/state?workspace_id=' + result['workspace_id'])
        self.assertEqual(sorted(row['sha256'] for row in restored['documents']), sorted([first['sha256'], second['sha256']]))
        self.assertEqual(len(restored['notes']), 1)
        self.assertEqual(restored['notes'][0]['version'], 2)
        self.assertLess(peak, 95 * 1024 * 1024, 'Python memory must stay bounded by individual originals, not ZIP/base64/all-original collections')
        print('Large synthetic ZIP bytes:', entry['bytes'], 'tracemalloc peak bytes:', peak)

    def test_corrupt_file_restore_and_failed_write_publish_no_workspace_or_set(self):
        self.source(3)
        archive_path = self.folder / 'selected.zip'
        self.store.write_backup(self.workspace, archive_path)
        before_files = {path.name for path in self.store.originals.iterdir()}
        before_rows = self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0]
        with archive_path.open('r+b') as stream:
            stream.seek(80)
            stream.write(b'BROKEN')
        with self.assertRaises(b.AppError):
            self.store.restore_backup_file(archive_path)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], before_rows)
        self.assertEqual({path.name for path in self.store.originals.iterdir()}, before_files)
        with patch.object(self.store, 'write_backup', side_effect=OSError('Synthetic disk full')):
            self.assertFalse(self.backups.run_now()['ok'])
        self.assertEqual(self.backups.list_sets()['sets'], [])

    def test_preview_and_apply_are_bound_to_exact_archive_digest(self):
        self.source(4)
        archive_path = self.folder / 'selected.zip'
        receipt = self.store.write_backup(self.workspace, archive_path)
        self.assertEqual(self.store.restore_backup_file(archive_path, preview_only=True, expected_sha256=receipt['sha256'], expected_size=receipt['bytes'])['documents'], 1)
        with archive_path.open('r+b') as stream:
            stream.seek(80)
            stream.write(b'BROKEN')
        with self.assertRaises(b.AppError):
            self.store.restore_backup_file(archive_path, expected_sha256=receipt['sha256'], expected_size=receipt['bytes'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_changed_selected_file_during_apply_uses_verified_snapshot_and_cleans_spill(self):
        document = self.source(5)
        archive_path = self.folder / 'selected.zip'
        receipt = self.store.write_backup(self.workspace, archive_path)
        original_restore = self.store._restore_archive
        original_temporary = tempfile.TemporaryDirectory
        scratch_paths = []
        def temporary(*args, **kwargs):
            created = original_temporary(*args, **kwargs)
            scratch_paths.append(Path(created.name))
            return created
        def mutate_selected(archive, **kwargs):
            archive_path.write_bytes(b'Changed selection after verified staging')
            return original_restore(archive, **kwargs)
        with patch.object(archives.tempfile, 'TemporaryDirectory', side_effect=temporary), patch.object(self.store, '_restore_archive', side_effect=mutate_selected):
            result = self.store.restore_backup_file(archive_path, expected_sha256=receipt['sha256'], expected_size=receipt['bytes'])
        restored = self.store.dispatch('GET', '/api/state?workspace_id=' + result['workspace_id'])
        self.assertEqual(restored['documents'][0]['sha256'], document['sha256'])
        self.assertTrue(scratch_paths)
        self.assertFalse(any(path.exists() for path in scratch_paths))
        with patch.object(archives.tempfile, 'TemporaryDirectory', side_effect=temporary):
            with self.assertRaises(b.AppError):
                self.store.restore_backup_file(archive_path, expected_sha256=receipt['sha256'], expected_size=receipt['bytes'])
        self.assertFalse(any(path.exists() for path in scratch_paths))

    def test_late_member_corruption_and_extra_members_never_publish_originals(self):
        self.source(6)
        self.source(7)
        archive_path = self.folder / 'selected.zip'
        self.store.write_backup(self.workspace, archive_path)
        before_files = {path.name for path in self.store.originals.iterdir()}
        with zipfile.ZipFile(archive_path) as archive:
            entry = archive.infolist()[-1]
            offset = entry.header_offset + 30 + len(entry.filename.encode('utf-8')) + len(entry.extra) + 100
        with archive_path.open('r+b') as stream:
            stream.seek(offset)
            stream.write(b'CORRUPT')
        with self.assertRaises(b.AppError):
            self.store.restore_backup_file(archive_path)
        self.assertEqual(before_files, {path.name for path in self.store.originals.iterdir()})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)
        other = self.folder / 'extra.zip'
        self.store.write_backup(self.workspace, other)
        with zipfile.ZipFile(other, 'a') as archive:
            archive.writestr('unexpected.txt', 'Invented unexpected entry')
        with self.assertRaises(b.AppError):
            self.store.restore_backup_file(other)
        self.assertEqual(before_files, {path.name for path in self.store.originals.iterdir()})

    def test_publication_io_failure_reports_storage_and_retains_recovery(self):
        document = self.source(8)
        archive_path = self.folder / 'selected.zip'
        self.store.write_backup(self.workspace, archive_path)
        original_copy = archives.stream_copy
        def failed_write(source, output=None, **kwargs):
            if output is not None and '.pending-' in str(getattr(output, 'name', '')):
                raise OSError('Synthetic target disk failure')
            return original_copy(source, output, **kwargs)
        with patch.object(archives, 'stream_copy', side_effect=failed_write), self.assertRaises(b.AppError) as caught:
            self.store.restore_backup_file(archive_path)
        message = str(caught.exception).lower()
        self.assertIn('storage', message)
        self.assertIn('retained', message)
        self.assertNotIn('malformed', message)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)
        self.assertEqual(len(list(self.store.originals.glob('*.pending-*'))), 1)
        self.assertEqual(self.store._document(document['id'])['sha256'], document['sha256'])
        self.assertEqual(hashlib.sha256(self.store._bytes(self.store._document(document['id']))).hexdigest(), document['sha256'])

    def test_read_only_preview_spill_io_does_not_block_note_save(self):
        self.source(9)
        entered, release, saved = threading.Event(), threading.Event(), threading.Event()
        results, errors = [], []
        original_spill = archives.SpilledExtractions.__setitem__
        def paused_spill(instance, key, value):
            entered.set()
            release.wait(5)
            return original_spill(instance, key, value)
        def run():
            try:
                results.append(self.backups.run_now())
            except Exception as error:
                errors.append(error)
        def save():
            try:
                self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Concurrent invented draft', 'body': 'Saved while backup validates on disk.'})
                saved.set()
            except Exception as error:
                errors.append(error)
        with patch.object(archives.SpilledExtractions, '__setitem__', new=paused_spill):
            backup_worker = threading.Thread(target=run)
            backup_worker.start()
            self.assertTrue(entered.wait(5))
            note_worker = threading.Thread(target=save)
            note_worker.start()
            prompt_save = saved.wait(1)
            release.set()
            backup_worker.join(5)
            note_worker.join(5)
        self.assertEqual(errors, [])
        self.assertTrue(prompt_save, 'Disk-backed read-only validation must release the Store lock between native parser sections.')
        self.assertTrue(results[0]['ok'])


if __name__ == '__main__':
    unittest.main()
